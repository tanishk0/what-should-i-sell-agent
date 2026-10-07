"""Retrieve reviews for competitors via SerpAPI detail engines.

- Amazon:  engine=amazon_product -> reviews_information (Amazon's aspect insights,
           each with example review snippets + per-review links, plus any full
           review lists SerpAPI returns).
- Google:  engine=google_product -> product_results.user_reviews (aggregated from
           retailers such as Walmart/Target, with ratings and authors).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional
from urllib.parse import parse_qsl, urlparse

from ..normalize.common import build_search_record, parse_count, to_float
from ..schema import Listing, Product, SearchRecord
from ..serp_client import SerpClient
from .models import AspectInsight, AspectTag, ProductReviews, RatingBreakdown, Review, ReviewCitation


class CreditBudget:
    """Hard cap on *uncached* SerpAPI calls (free plan = 200 credits total)."""

    def __init__(self, max_credits: int) -> None:
        self.max_credits = max_credits
        self.used = 0
        self.cached_calls = 0
        self.skipped = 0

    def allow(self, cached: bool) -> bool:
        if cached:
            return True
        if self.used >= self.max_credits:
            self.skipped += 1
            return False
        return True

    def record(self, cached: bool) -> None:
        if cached:
            self.cached_calls += 1
        else:
            self.used += 1


def params_from_serpapi_url(url: str) -> dict[str, str]:
    return {k: v for k, v in parse_qsl(urlparse(url).query) if k != "api_key"}


def _review_id(source: str, listing_id: str, link: Optional[str], *parts: Any) -> str:
    if link:
        m = re.search(r"/(R[A-Z0-9]{8,})", link)
        if m:
            return f"{source}:{m.group(1)}"
    digest = hashlib.sha1("|".join([listing_id, *(str(p) for p in parts)]).encode("utf-8")).hexdigest()[:16]
    return f"{source}:{digest}"


def _citation(record: SearchRecord, listing: Listing, review_url: Optional[str] = None) -> ReviewCitation:
    return ReviewCitation(
        source=listing.source,
        engine=record.engine,
        search_id=record.search_id,
        serpapi_json_url=record.serpapi_json_url,
        product_url=listing.url,
        review_url=review_url,
        retrieved_at=record.retrieved_at,
    )


def _make_review(product: Product, listing: Listing, record: SearchRecord, *, text: str,
                 link: Optional[str] = None, **fields: Any) -> Review:
    return Review(
        id=_review_id(listing.source, listing.source_product_id, link, fields.get("author"), text),
        product_id=product.id,
        product_title=product.title,
        source=listing.source,
        listing_id=listing.source_product_id,
        text=text,
        original_text=text,
        url=link or listing.url,
        citation=_citation(record, listing, link),
        **fields,
    )


# ---------------------------------------------------------------- Amazon
_AMAZON_REVIEW_LISTS = ("authors_reviews", "other_countries_reviews", "top_reviews", "customer_reviews")


def extract_amazon(raw: dict, product: Product, listing: Listing, record: SearchRecord, out: ProductReviews) -> None:
    info = raw.get("reviews_information", {}) or {}
    summary = info.get("summary", {}) or {}
    out.brand = out.brand or (raw.get("product_results", {}) or {}).get("brand")
    out.marketplace_summary = out.marketplace_summary or summary.get("text")

    dist = summary.get("customer_reviews")
    if isinstance(dist, dict) and dist:
        stars = {int(k.split()[0]): float(v) for k, v in dist.items() if k.split()[0].isdigit()}
        out.rating_breakdowns.append(RatingBreakdown(source="amazon", unit="percent", stars=stars,
                                                     citation=_citation(record, listing)))

    for ins in summary.get("insights", []) or []:
        mentions = ins.get("mentions", {}) or {}
        out.aspects.append(AspectInsight(
            source="amazon", aspect=ins.get("title", "?"), sentiment=ins.get("sentiment"),
            mentions_total=parse_count(mentions.get("total")),
            mentions_positive=parse_count(mentions.get("positive")),
            mentions_negative=parse_count(mentions.get("negative")),
            summary=ins.get("summary"), citation=_citation(record, listing),
        ))
        tag = AspectTag(aspect=ins.get("title", "?"), sentiment=ins.get("sentiment"))
        for ex in ins.get("examples", []) or []:
            if ex.get("snippet"):
                out.reviews.append(_make_review(product, listing, record, text=ex["snippet"],
                                                link=ex.get("link"), marketplace_aspects=[tag]))

    # Full review lists, when SerpAPI returns them for this product.
    for key in _AMAZON_REVIEW_LISTS:
        items = info.get(key)
        if not isinstance(items, list):
            continue
        for r in items:
            text = r.get("text") or r.get("body") or r.get("snippet")
            if not text:
                continue
            out.reviews.append(_make_review(
                product, listing, record, text=text, link=r.get("link"),
                title=r.get("title"), rating=to_float(r.get("rating")),
                author=(r.get("author") or {}).get("name") if isinstance(r.get("author"), dict) else r.get("author"),
                date=r.get("date"),
            ))


# ---------------------------------------------------------------- Google
def extract_google(raw: dict, product: Product, listing: Listing, record: SearchRecord, out: ProductReviews) -> None:
    pr = raw.get("product_results", {}) or {}
    out.brand = out.brand or pr.get("brand")

    ratings = pr.get("ratings")
    if isinstance(ratings, list) and ratings:
        stars = {int(r["stars"]): float(r.get("amount", 0)) for r in ratings if "stars" in r}
        out.rating_breakdowns.append(RatingBreakdown(source="google_shopping", unit="count", stars=stars,
                                                     citation=_citation(record, listing)))

    items = pr.get("user_reviews") or raw.get("user_reviews") or raw.get("reviews") or []
    for r in items if isinstance(items, list) else []:
        text = r.get("text") or r.get("content") or r.get("snippet")
        if not text:
            continue
        out.reviews.append(_make_review(
            product, listing, record, text=text, link=r.get("link"),
            title=r.get("title"), rating=to_float(r.get("rating")),
            author=r.get("user_name") or r.get("author"), date=r.get("date"),
            retailer=r.get("source"),
        ))


_EXTRACTORS = {"amazon": extract_amazon, "google_shopping": extract_google}


def _pick_listings(product: Product, sources_per_product: int) -> list[Listing]:
    """One listing per source (the one with most reviews), up to N sources."""
    best: dict[str, Listing] = {}
    for l in sorted(product.listings, key=lambda l: -(l.review_count or 0)):
        if l.detail_api_url and l.source not in best:
            best[l.source] = l
    primary_source = product.id.split(":", 1)[0]
    ordered = sorted(best.values(), key=lambda l: l.source != primary_source)
    return ordered[:sources_per_product]


def fetch_product_reviews(product: Product, rank: int, client: SerpClient, budget: CreditBudget,
                          *, sources_per_product: int = 2) -> ProductReviews:
    out = ProductReviews(product_id=product.id, product_title=product.title, product_url=product.url, rank=rank)
    for listing in _pick_listings(product, sources_per_product):
        params = params_from_serpapi_url(listing.detail_api_url)
        cached = client.is_cached(params)
        if not budget.allow(cached):
            out.errors.append(f"{listing.source}: skipped (credit budget of {budget.max_credits} reached)")
            continue
        try:
            raw, from_cache = client.search(params)
        except Exception as err:  # keep going; one bad product shouldn't kill the run
            out.errors.append(f"{listing.source}: {err}")
            continue
        budget.record(from_cache)
        record = build_search_record(listing.source, raw, from_cache)
        _EXTRACTORS[listing.source](raw, product, listing, record, out)
        out.sources_fetched.append(listing.source)
    return out
