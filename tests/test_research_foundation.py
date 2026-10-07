"""Offline tests against real SerpAPI responses captured for 'yoga mat' (US)."""
import json
from pathlib import Path

import pytest

from wsis.normalize import normalize_amazon, normalize_google_shopping
from wsis.normalize.common import build_search_record, parse_count, to_float
from wsis.pipeline import build_competitor_set
from wsis.serp_client import SerpClient

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FixtureClient(SerpClient):
    """Serves fixtures instead of hitting the network."""

    def __init__(self):
        super().__init__(None, offline=True)

    def search(self, params):
        name = {"amazon": "amazon_yoga_mat.json", "google_shopping": "google_shopping_yoga_mat.json"}
        return load(name[params["engine"]]), True


def test_parsers():
    assert parse_count("1.2K+ bought in past month") == 1200
    assert parse_count("50+ bought in past month") == 50
    assert parse_count("46,700") == 46700
    assert to_float("$1,299.99") == 1299.99
    assert parse_count(None) is None


def test_amazon_normalization():
    raw = load("amazon_yoga_mat.json")
    rec = build_search_record("amazon", raw, True)
    items = normalize_amazon(raw, rec, currency="USD")
    assert len(items) >= 40
    first = items[0]
    assert first.url.startswith("https://www.amazon.com/dp/")
    assert first.citation.serpapi_json_url and first.citation.position == 1
    assert rec.origin_search_url.startswith("https://www.amazon.com/s")
    assert any(i.sponsored for i in items) and any(not i.sponsored for i in items)


def test_google_normalization():
    raw = load("google_shopping_yoga_mat.json")
    rec = build_search_record("google_shopping", raw, True)
    items = normalize_google_shopping(raw, rec, currency="USD")
    assert len(items) >= 30
    assert all(i.seller for i in items)
    assert all(i.citation.search_id for i in items)


def test_pipeline_produces_clean_set():
    rs = build_competitor_set("yoga mat", FixtureClient(), limit=30)
    assert 20 <= len(rs.products) <= 30
    ids = [p.id for p in rs.products]
    assert len(ids) == len(set(ids)), "duplicate products"
    # Same ASIN must never appear in two products.
    asins = [l.source_product_id for p in rs.products for l in p.listings if l.source == "amazon"]
    assert len(asins) == len(set(asins))
    for p in rs.products:
        assert p.price is not None and p.currency == "USD"
        assert p.listings and all(l.citation.serpapi_json_url for l in p.listings)
        assert p.relevance >= 0.5
    assert {"amazon", "google_shopping"} <= {s for p in rs.products for s in p.sources}
    # Sorted by score
    assert [p.score for p in rs.products] == sorted((p.score for p in rs.products), reverse=True)


def test_offline_client_without_cache_raises():
    from wsis.serp_client import SerpApiError

    c = SerpClient(None, offline=True, cache_dir=FIX / "_does_not_exist")
    with pytest.raises(SerpApiError):
        c.search({"engine": "amazon", "k": "nothing"})
