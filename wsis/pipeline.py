"""Research foundation pipeline: query -> clean, cited competitor set."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

from .config import Market, get_market
from .dedupe import merge_listings
from .normalize import normalize_amazon, normalize_google_shopping
from .normalize.common import build_search_record, query_tokens
from .ranking import product_relevance, score, select_top
from .schema import Listing, ResearchSet, SearchRecord
from .serp_client import SerpClient


def _fetch_amazon(client: SerpClient, query: str, market: Market, pages: int):
    for page in range(1, pages + 1):
        params = {"engine": "amazon", "k": query, "amazon_domain": market.amazon_domain}
        if page > 1:
            params["page"] = page
        raw, cached = client.search(params)
        record = build_search_record("amazon", raw, cached)
        listings = normalize_amazon(raw, record, currency=market.currency)
        record.raw_result_count = len(raw.get("organic_results", []) or [])
        yield record, listings


def _fetch_google(client: SerpClient, query: str, market: Market):
    params = {"engine": "google_shopping", "q": query, "gl": market.gl, "hl": market.hl}
    raw, cached = client.search(params)
    record = build_search_record("google_shopping", raw, cached)
    record.raw_result_count = len(raw.get("shopping_results", []) or [])
    yield record, normalize_google_shopping(raw, record, currency=market.currency)


def build_competitor_set(
    query: str,
    client: SerpClient,
    *,
    market: str = "us",
    limit: int = 30,
    min_relevance: float = 0.5,
    sources: Iterable[str] = ("amazon", "google_shopping"),
    amazon_pages: int = 1,
) -> ResearchSet:
    mkt = get_market(market)
    q_tokens = query_tokens(query)
    sources = set(sources)

    searches: list[SearchRecord] = []
    listings: list[Listing] = []
    fetchers = []
    if "amazon" in sources:
        fetchers.append(_fetch_amazon(client, query, mkt, amazon_pages))
    if "google_shopping" in sources:
        fetchers.append(_fetch_google(client, query, mkt))
    for fetcher in fetchers:
        for record, items in fetcher:
            searches.append(record)
            listings.extend(items)

    stats: dict = {"listings_normalized": dict(Counter(l.source for l in listings))}

    # Drop listings we can't use for price analysis, and foreign-currency noise.
    dropped = Counter()
    usable: list[Listing] = []
    for l in listings:
        if l.price is None:
            dropped["no_price"] += 1
        elif l.currency and l.currency != mkt.currency:
            dropped["other_currency"] += 1
        else:
            usable.append(l)

    products = merge_listings(usable, q_tokens)
    stats["unique_products"] = len(products)

    relevant = []
    for p in products:
        p.relevance = round(product_relevance(p, q_tokens), 3)
        if p.relevance < min_relevance:
            dropped["low_relevance"] += 1
            continue
        p.score = score(p)
        relevant.append(p)

    top = select_top(relevant, limit=limit, min_per_source=max(1, limit // 4))
    stats.update(
        dropped=dict(dropped),
        relevant_products=len(relevant),
        selected=len(top),
        selected_by_source=dict(Counter(s for p in top for s in p.sources)),
        multi_source_products=sum(len(p.sources) > 1 for p in top),
    )
    return ResearchSet(
        query=query,
        market=mkt.code,
        currency=mkt.currency,
        created_at=datetime.now(timezone.utc),
        searches=searches,
        products=top,
        stats=stats,
    )
