"""Offline unit tests for review intelligence."""
import json
from pathlib import Path

import pytest

from wsis.reviews.classify import ReviewClassifier, verify_evidence
from wsis.reviews.clean import clean_reviews, clean_text, is_noise
from wsis.reviews.fetch import CreditBudget, extract_amazon, extract_google
from wsis.reviews.models import ProductReviews, Review, ReviewCitation
from wsis.schema import Citation, Listing, Product, SearchRecord

FIX = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def make_dummy_listing(source="amazon", product_id="TEST1234"):
    return Listing(
        source=source,
        source_product_id=product_id,
        title="Test Yoga Mat 1/2-Inch Extra Thick",
        url="https://example.com/item",
        price=20.0,
        currency="USD",
        citation=Citation(source=source, engine=f"{source}_product"),
    )


def make_dummy_product(listing: Listing):
    return Product(
        id=f"{listing.source}:{listing.source_product_id}",
        title=listing.title,
        url=listing.url,
        price=listing.price,
        currency=listing.currency,
        sources=[listing.source],
        listings=[listing],
    )


def test_clean_text_and_noise():
    clean, truncated = clean_text("... Slippery when sweaty! Read more ...")
    assert clean == "Slippery when sweaty!"
    assert truncated is True

    assert is_noise("ok") == "too_short"
    assert is_noise("12345 67890 12345 67890") == "no_words"
    assert is_noise("good good good good good good") == "repetitive"
    assert is_noise("The yoga mat began flaking after two sessions on hardwood floor.") is None


def test_review_deduplication():
    citation = ReviewCitation(source="amazon", engine="amazon_product", product_url="https://example.com")
    r1 = Review(
        id="amazon:1",
        product_id="amazon:TEST",
        product_title="Yoga Mat",
        source="amazon",
        listing_id="TEST",
        text="The mat is very slippery when wet. Not safe.",
        original_text="The mat is very slippery when wet. Not safe.",
        url="https://example.com/rev1",
        citation=citation,
    )
    # duplicate by id
    r2 = r1.model_copy()
    # duplicate by exact text
    r3 = Review(
        id="amazon:2",
        product_id="amazon:TEST",
        product_title="Yoga Mat",
        source="amazon",
        listing_id="TEST",
        text="The mat is very slippery when wet. Not safe.",
        original_text="The mat is very slippery when wet. Not safe.",
        url="https://example.com/rev2",
        citation=citation,
    )

    cleaned, stats = clean_reviews([r1, r2, r3])
    assert len(cleaned) == 1
    assert stats["raw"] == 3
    assert stats["kept"] == 1


def test_evidence_verification():
    original = "This mat started flaking and slipping during hot yoga. Very dangerous."
    # Verbatim match
    q, ok = verify_evidence("started flaking and slipping", original, original)
    assert ok is True

    # Hallucinated quote
    q_fake, ok_fake = verify_evidence("The mat completely snapped in half immediately", original, original)
    assert ok_fake is False


def test_amazon_and_google_extractors():
    raw_amz = load_fixture("amazon_product_yoga_mat.json")
    listing_amz = make_dummy_listing("amazon", "B0DY88PCV4")
    product_amz = make_dummy_product(listing_amz)
    record_amz = SearchRecord(source="amazon", engine="amazon_product", params={})
    pr_amz = ProductReviews(
        product_id=product_amz.id,
        product_title=product_amz.title,
        product_url=product_amz.url,
        rank=1,
    )
    extract_amazon(raw_amz, product_amz, listing_amz, record_amz, pr_amz)
    assert len(pr_amz.reviews) > 0
    assert len(pr_amz.aspects) > 0
    assert pr_amz.marketplace_summary is not None
    assert all(r.product_id == product_amz.id for r in pr_amz.reviews)

    raw_g = load_fixture("google_product_yoga_mat.json")
    listing_g = make_dummy_listing("google_shopping", "17994186126052308366")
    product_g = make_dummy_product(listing_g)
    record_g = SearchRecord(source="google_shopping", engine="google_product", params={})
    pr_g = ProductReviews(
        product_id=product_g.id,
        product_title=product_g.title,
        product_url=product_g.url,
        rank=2,
    )
    extract_google(raw_g, product_g, listing_g, record_g, pr_g)
    assert len(pr_g.reviews) > 0
    assert all(r.product_id == product_g.id for r in pr_g.reviews)
    assert all(r.url is not None for r in pr_g.reviews)


def test_credit_budget():
    budget = CreditBudget(max_credits=2)
    assert budget.allow(cached=True) is True
    budget.record(cached=True)
    assert budget.used == 0

    assert budget.allow(cached=False) is True
    budget.record(cached=False)
    assert budget.allow(cached=False) is True
    budget.record(cached=False)
    # Exceeded budget
    assert budget.allow(cached=False) is False
    assert budget.skipped == 1


def test_classifier_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not set"):
        ReviewClassifier(api_key=None)
