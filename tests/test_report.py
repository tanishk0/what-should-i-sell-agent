"""Tests for Evidence-Backed Market-Gap Research Report."""
from __future__ import annotations

from datetime import datetime, timezone

from wsis.report.builder import build_final_report, render_markdown_report, render_terminal_report
from wsis.report.models import MarketGapReport
from wsis.reviews.models import ProductReviews, Review, ReviewCitation, ReviewClassification, ReviewIntelligence
from wsis.reviews.problem_models import ComplaintEvidence, ProblemAnalysis, ProblemCluster
from wsis.schema import Product, ResearchSet


def _make_mock_fixture():
    now = datetime.now(timezone.utc)
    cit = ReviewCitation(source="amazon", engine="amazon_product", product_url="https://amazon.in/dp/B001")

    p1 = Product(
        id="prod_01",
        title="Milton Compact Lunch Box 800ml",
        url="https://amazon.in/dp/B001",
        price=699.0,
        currency="INR",
        rating=4.2,
        review_count=120,
        sources=["amazon"],
        listings=[],
    )
    p2 = Product(
        id="prod_02",
        title="Cello Max Fresh Heavy Lunch Box",
        url="https://amazon.in/dp/B002",
        price=899.0,
        currency="INR",
        rating=4.4,
        review_count=95,
        sources=["amazon"],
        listings=[],
    )
    p3 = Product(
        id="prod_03",
        title="Signoraware Best Seal Lunch Box",
        url="https://amazon.in/dp/B003",
        price=799.0,
        currency="INR",
        rating=4.5,
        review_count=210,
        sources=["amazon"],
        listings=[],
    )

    rs = ResearchSet(
        query="lunch box",
        market="in",
        currency="INR",
        created_at=now,
        searches=[],
        products=[p1, p2, p3],
    )

    ev1 = ComplaintEvidence(
        review_id="rev_01",
        product_id="prod_01",
        product_title="Milton Compact Lunch Box",
        rating=1.0,
        original_text="Lid snaps open inside backpack and soup leaks everywhere.",
        evidence_quote="Lid snaps open inside backpack and soup leaks everywhere.",
        evidence_verified=True,
        url="https://amazon.in/rev1",
        citation=cit,
    )
    ev2 = ComplaintEvidence(
        review_id="rev_02",
        product_id="prod_02",
        product_title="Cello Max Fresh",
        rating=2.0,
        original_text="Cannot put dal or curry, it leaks through the corner gasket.",
        evidence_quote="it leaks through the corner gasket.",
        evidence_verified=True,
        url="https://amazon.in/rev2",
        citation=cit,
    )

    cluster1 = ProblemCluster(
        id="prob_01",
        problem="Liquid leakage when carried sideways",
        category="durability",
        description="Leakage when carrying liquids sideways in backpacks.",
        supporting_reviews=[ev1, ev2],
        supporting_products=["prod_01", "prod_02"],
        unaffected_products=["prod_03"],
        review_count=2,
        product_count=2,
        product_prevalence_pct=66.7,
        avg_severity=2.8,
        is_widespread_gap=False,
    )

    prob = ProblemAnalysis(
        query="lunch box",
        market="in",
        created_at=now,
        total_reviews_analyzed=100,
        total_complaints_analyzed=2,
        clusters=[cluster1],
    )

    r1 = Review(
        id="rev_01",
        product_id="prod_01",
        product_title="Milton Compact",
        source="amazon",
        listing_id="L1",
        text="Lid snaps open",
        original_text="Lid snaps open",
        url="https://amazon.in/rev1",
        citation=cit,
        classification=ReviewClassification(
            sentiment="negative",
            is_complaint=True,
            severity=3,
            model="test",
            prompt_version="v1",
        ),
    )
    r2 = Review(
        id="rev_02",
        product_id="prod_02",
        product_title="Cello Max",
        source="amazon",
        listing_id="L2",
        text="it leaks",
        original_text="it leaks",
        url="https://amazon.in/rev2",
        citation=cit,
        classification=ReviewClassification(
            sentiment="negative",
            is_complaint=True,
            severity=2,
            model="test",
            prompt_version="v1",
        ),
    )
    pr1 = ProductReviews(product_id="prod_01", product_title="Milton Compact", product_url="https://amazon.in/dp/B001", rank=1, reviews=[r1])
    pr2 = ProductReviews(product_id="prod_02", product_title="Cello Max", product_url="https://amazon.in/dp/B002", rank=2, reviews=[r2])
    pr3 = ProductReviews(product_id="prod_03", product_title="Signoraware", product_url="https://amazon.in/dp/B003", rank=3, reviews=[])

    rev_intel = ReviewIntelligence(
        query="lunch box",
        market="in",
        created_at=now,
        products=[pr1, pr2, pr3],
    )

    return rs, rev_intel, prob


def test_build_final_report_structure():
    rs, rev_intel, prob = _make_mock_fixture()

    report = build_final_report(
        research_set=rs,
        review_intel=rev_intel,
        prob_analysis=prob,
    )

    assert isinstance(report, MarketGapReport)
    assert report.query == "lunch box"
    assert report.market == "in"
    assert report.currency == "INR"
    assert report.total_competitors_found == 3
    assert report.total_competitors_analyzed == 3
    assert report.total_reviews_analyzed == 100
    assert report.total_complaints_found == 2
    assert report.has_insufficient_evidence is False

    # Check that counts are derived strictly from arrays
    assert len(report.problems) == 1
    p = report.problems[0]
    assert p.review_count == len(p.supporting_reviews) == 2
    assert p.product_count == len(p.supporting_products) == 2
    # Two affected products alone must not qualify as widespread
    assert p.is_widespread_gap is False
    assert p.classification_label == "Multi-Competitor Pattern"
    assert p.unaffected_products == ["prod_03"]

    # Verify competitor benchmark rows
    assert len(report.competitors) == 3
    assert report.competitors[0].complaints_count == 1
    assert report.competitors[1].complaints_count == 1
    assert report.competitors[2].complaints_count == 0


def test_build_final_report_insufficient_evidence():
    now = datetime.now(timezone.utc)
    rs = ResearchSet(
        query="lunch box",
        market="in",
        currency="INR",
        created_at=now,
        searches=[],
        products=[],
    )
    report = build_final_report(rs, review_intel=None, prob_analysis=None)
    assert report.has_insufficient_evidence is True
    assert "Insufficient" in report.summary


def test_render_terminal_and_markdown():
    rs, rev_intel, prob = _make_mock_fixture()
    report = build_final_report(rs, review_intel=rev_intel, prob_analysis=prob)

    term = render_terminal_report(report)
    assert "MARKET-GAP RESEARCH REPORT" in term
    assert "Liquid leakage when carried sideways" in term
    assert "MULTI-COMPETITOR PATTERN" in term
    assert "Not observed in sampled reviews" in term
    assert "Signoraware" in term or "prod_03" in term
    assert "rev_01" in term  # References specific review ID

    md = render_markdown_report(report)
    assert "# Amazon Market-Gap Research Report: Lunch Box" in md
    assert "Liquid leakage when carried sideways" in md
    assert "MULTI-COMPETITOR PATTERN" in md
    assert "Not observed in sampled reviews" in md
    assert "Milton Compact" in md
    assert "Review ID: `rev_01`" in md
