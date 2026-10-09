"""Automated tests for evidence integrity in the review intelligence pipeline.

Covers:
1. Rejection of drop-protection quote incorrectly supporting yellowing.
2. Rejection of loose-fit quote supporting packaging damage.
3. One review supporting multiple unrelated clusters via distinct spans.
4. Prevention of quote reuse across unrelated clusters.
5. Deduplication and merging of overlapping clusters representing the same underlying issue.
6. Prevention of double-counting a review for the same underlying issue.
7. Neutral evidence-based classifications (two affected products alone do not qualify as widespread).
8. Counter-evidence renamed to 'Not observed in sampled reviews' without inferring competitor is defect-free.
9. Exclusion of unvalidated evidence without fabricating replacements.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from wsis.report.builder import build_final_report, render_markdown_report, render_terminal_report
from wsis.reviews.clustering import cluster_complaints
from wsis.reviews.evidence_validation import (
    are_clusters_overlapping,
    classify_cluster_status,
    deduplicate_and_merge_clusters,
    validate_evidence_relevance,
    verify_span_verbatim,
)
from wsis.reviews.models import (
    ProductReviews,
    Review,
    ReviewCitation,
    ReviewClassification,
    ReviewIntelligence,
)
from wsis.reviews.problem_models import ProblemCluster
from wsis.schema import Product, ResearchSet


def _make_review(
    review_id: str,
    product_id: str,
    text: str,
    quote: str,
    categories: list[str],
    issues: list[str],
    rating: float = 1.0,
    severity: int = 3,
) -> Review:
    cit = ReviewCitation(source="amazon", engine="amazon_product", product_url="https://example.com/p")
    return Review(
        id=review_id,
        product_id=product_id,
        product_title=f"Competitor Product {product_id}",
        source="amazon",
        listing_id=product_id,
        text=text,
        original_text=text,
        rating=rating,
        url=f"https://example.com/r/{review_id}",
        citation=cit,
        classification=ReviewClassification(
            sentiment="negative",
            is_complaint=True,
            noise=False,
            categories=categories,
            issues=issues,
            severity=severity,
            evidence_quote=quote,
            evidence_verified=True,
            model="test",
            prompt_version="v1",
        ),
    )


class MockResponse:
    def __init__(self, text: str):
        self.text = text


class MockLLMClient:
    """Mock LLM client returning scripted clusters."""

    def __init__(self, clusters: list[dict]):
        self.clusters = clusters

        class _Models:
            def __init__(self, outer):
                self._outer = outer

            def generate_content(self, *args, **kwargs):
                return MockResponse(json.dumps({"clusters": self._outer.clusters}))

        self.models = _Models(self)


def test_reject_drop_protection_quote_supporting_yellowing():
    """Requirement 9: Drop-protection quote incorrectly supporting yellowing must be rejected."""
    drop_quote = "Dropped the phone from 2 feet and screen shattered, zero protection."
    review_text = f"{drop_quote} Terrible case."

    # Validate semantic relevance against a yellowing cluster
    is_valid, reason = validate_evidence_relevance(
        quote=drop_quote,
        review_text=review_text,
        cluster_name="Clear case turns yellow within weeks",
        cluster_category="design_aesthetics",
        cluster_description="Transparent cases discolor and turn yellow prematurely.",
        review_categories=["durability", "performance"],
        review_issues=["poor drop protection", "screen shattered"],
    )

    assert is_valid is False
    assert "incompatible" in reason.lower() or "discoloration" in reason.lower() or "no semantic overlap" in reason.lower()


def test_reject_loose_fit_quote_supporting_packaging_damage():
    """Requirement 9: Loose-fit quote supporting packaging damage must be rejected (regression case)."""
    loose_quote = "It fits bit loose. I think it won't protect the Phone"
    review_text = f"{loose_quote} Needs better grip."

    # Validate semantic relevance against packaging arrives open/damaged cluster
    is_valid, reason = validate_evidence_relevance(
        quote=loose_quote,
        review_text=review_text,
        cluster_name="Packaging arrives open or damaged",
        cluster_category="shipping_packaging",
        cluster_description="Products are delivered with packaging that is visibly opened, torn, or crushed.",
        review_categories=["durability", "size_fit"],
        review_issues=["case loosens and stretches out"],
    )

    assert is_valid is False
    assert "incompatible" in reason.lower() or "packaging" in reason.lower() or "no semantic overlap" in reason.lower()


def test_one_review_supporting_multiple_unrelated_clusters_with_distinct_spans():
    """Requirement 3, 4, 9: One review supporting multiple unrelated clusters.

    Allowed only when the review explicitly supports distinct complaints with distinct spans.
    No quote reuse across unrelated clusters.
    """
    yellow_span = "The clear case turned yellow after just two weeks."
    slippery_span = "Extremely slippery and constantly slides out of hand."
    full_text = f"{yellow_span} Also, {slippery_span}"

    r_multi = _make_review(
        review_id="rev_multi_01",
        product_id="prod_alpha",
        text=full_text,
        quote=yellow_span,
        categories=["design_aesthetics", "comfort_ergonomics"],
        issues=["turns yellow quickly", "slippery surface"],
    )

    pr1 = ProductReviews(
        product_id="prod_alpha",
        product_title="Alpha Case",
        product_url="https://example.com/alpha",
        rank=1,
        reviews=[r_multi],
    )

    intel = ReviewIntelligence(
        query="iphone case",
        market="us",
        created_at=datetime.now(timezone.utc),
        products=[pr1],
    )

    # Mock LLM returning two distinct clusters assigning the same review with distinct quotes
    mock_clusters = [
        {
            "name": "Clear case yellows quickly",
            "category": "design_aesthetics",
            "description": "Cases turn yellow within weeks.",
            "assigned_complaints": [
                {"review_id": "rev_multi_01", "quote": yellow_span}
            ],
        },
        {
            "name": "Excessively slippery surface",
            "category": "comfort_ergonomics",
            "description": "Phone slides easily from hand.",
            "assigned_complaints": [
                {"review_id": "rev_multi_01", "quote": slippery_span}
            ],
        },
        {
            "name": "Packaging arrives damaged",
            "category": "shipping_packaging",
            "description": "Packaging delivered torn or crushed.",
            "assigned_complaints": [
                # Hallucinated assignment: review does NOT support packaging damage
                {"review_id": "rev_multi_01", "quote": yellow_span}
            ],
        },
    ]

    analysis = cluster_complaints(intel, llm_client=MockLLMClient(mock_clusters))

    # The packaging cluster must be excluded (0 valid evidence)
    assert len(analysis.clusters) == 2
    c_yellow = next(c for c in analysis.clusters if "yellow" in c.problem.lower())
    c_slip = next(c for c in analysis.clusters if "slippery" in c.problem.lower())

    # Review supports both distinct clusters
    assert len(c_yellow.supporting_reviews) == 1
    assert c_yellow.supporting_reviews[0].review_id == "rev_multi_01"
    assert c_yellow.supporting_reviews[0].evidence_quote == yellow_span

    assert len(c_slip.supporting_reviews) == 1
    assert c_slip.supporting_reviews[0].review_id == "rev_multi_01"
    assert c_slip.supporting_reviews[0].evidence_quote == slippery_span

    # Distinct quotes were used; quotes were NOT reused across clusters
    assert c_yellow.supporting_reviews[0].evidence_quote != c_slip.supporting_reviews[0].evidence_quote


def test_quote_reuse_across_unrelated_clusters_is_rejected():
    """Requirement 4: Do not reuse evidence quotes across unrelated complaint clusters."""
    loose_quote = "It fits bit loose. I think it won't protect the Phone"
    r1 = _make_review(
        review_id="rev_01",
        product_id="prod_01",
        text=loose_quote,
        quote=loose_quote,
        categories=["durability"],
        issues=["loose fit"],
    )

    pr = ProductReviews(product_id="prod_01", product_title="Case 1", product_url="https://example.com", rank=1, reviews=[r1])
    intel = ReviewIntelligence(query="case", market="us", created_at=datetime.now(timezone.utc), products=[pr])

    # LLM assigns the exact same loose-fit quote to both fit and packaging
    mock_clusters = [
        {
            "name": "Case loosens and stretches out",
            "category": "durability",
            "description": "Case fits loosely over time.",
            "assigned_complaints": [{"review_id": "rev_01", "quote": loose_quote}],
        },
        {
            "name": "Packaging arrives open or damaged",
            "category": "shipping_packaging",
            "description": "Packaging arrives damaged in delivery.",
            "assigned_complaints": [{"review_id": "rev_01", "quote": loose_quote}],
        },
    ]

    analysis = cluster_complaints(intel, llm_client=MockLLMClient(mock_clusters))

    # Only the semantically matching cluster should survive
    assert len(analysis.clusters) == 1
    assert analysis.clusters[0].problem == "Case loosens and stretches out"
    assert analysis.clusters[0].supporting_reviews[0].evidence_quote == loose_quote


def test_two_affected_products_alone_do_not_qualify_as_widespread():
    """Requirement 7: Two affected products alone must not qualify as widespread."""
    r1 = _make_review("r1", "p1", "Phone slips out of hand easily", "slips out of hand", ["comfort_ergonomics"], ["slippery"], 2)
    r2 = _make_review("r2", "p2", "Slick material has zero grip", "zero grip", ["comfort_ergonomics"], ["slippery"], 2)

    pr1 = ProductReviews(product_id="p1", product_title="P1", product_url="https://ex.com/1", rank=1, reviews=[r1])
    pr2 = ProductReviews(product_id="p2", product_title="P2", product_url="https://ex.com/2", rank=2, reviews=[r2])
    pr3 = ProductReviews(product_id="p3", product_title="P3", product_url="https://ex.com/3", rank=3, reviews=[])
    pr4 = ProductReviews(product_id="p4", product_title="P4", product_url="https://ex.com/4", rank=4, reviews=[])
    pr5 = ProductReviews(product_id="p5", product_title="P5", product_url="https://ex.com/5", rank=5, reviews=[])

    intel = ReviewIntelligence(query="phone case", market="us", created_at=datetime.now(timezone.utc), products=[pr1, pr2, pr3, pr4, pr5])

    mock_clusters = [
        {
            "name": "Slippery surface / poor grip",
            "category": "comfort_ergonomics",
            "description": "Users report lack of friction and slipping.",
            "assigned_complaint_ids": ["r1", "r2"],
        }
    ]

    analysis = cluster_complaints(intel, llm_client=MockLLMClient(mock_clusters))
    cluster = analysis.clusters[0]

    # Affected 2 out of 5 competitors (40%)
    assert cluster.product_count == 2
    assert cluster.is_widespread_gap is False
    assert cluster.classification_label == "Multi-Competitor Pattern"


def test_widespread_market_gap_requires_at_least_three_competitors_and_fifty_percent():
    """Requirement 7: Widespread requires >=3 affected products and >=50% prevalence."""
    r1 = _make_review("r1", "p1", "Case turns yellow rapidly", "turns yellow", ["design_aesthetics"], ["yellowing"])
    r2 = _make_review("r2", "p2", "Clear case yellowed within days", "yellowed within days", ["design_aesthetics"], ["yellowing"])
    r3 = _make_review("r3", "p3", "Yellowing along the bumper", "Yellowing along", ["design_aesthetics"], ["yellowing"])

    pr1 = ProductReviews(product_id="p1", product_title="P1", product_url="https://ex.com/1", rank=1, reviews=[r1])
    pr2 = ProductReviews(product_id="p2", product_title="P2", product_url="https://ex.com/2", rank=2, reviews=[r2])
    pr3 = ProductReviews(product_id="p3", product_title="P3", product_url="https://ex.com/3", rank=3, reviews=[r3])
    pr4 = ProductReviews(product_id="p4", product_title="P4", product_url="https://ex.com/4", rank=4, reviews=[])

    intel = ReviewIntelligence(query="case", market="us", created_at=datetime.now(timezone.utc), products=[pr1, pr2, pr3, pr4])

    mock_clusters = [
        {
            "name": "Clear case turns yellow prematurely",
            "category": "design_aesthetics",
            "description": "Cases turn yellow rapidly.",
            "assigned_complaint_ids": ["r1", "r2", "r3"],
        }
    ]

    analysis = cluster_complaints(intel, llm_client=MockLLMClient(mock_clusters))
    cluster = analysis.clusters[0]

    # Affected 3 of 4 competitors (75%)
    assert cluster.product_count == 3
    assert cluster.product_prevalence_pct == 75.0
    assert cluster.is_widespread_gap is True
    assert cluster.classification_label == "Widespread Market Gap"


def test_remove_duplicate_overlapping_clusters_without_merging_distinct_issues():
    """Requirement 8: Remove duplicate or overlapping clusters for the same underlying issue.

    Prevent one review from being counted multiple times for the same underlying issue.
    Preserve genuinely distinct issues as separate clusters.
    """
    r1 = _make_review("r1", "p1", "Case stretches and fits loose after 1 month", "stretches and fits loose", ["durability"], ["loose fit"])
    r2 = _make_review("r2", "p1", "Now it doesn't fit snug, phone moves inside", "doesn't fit snug", ["durability"], ["loose fit"])
    r3 = _make_review("r3", "p2", "Turns yellow very quickly", "Turns yellow", ["design_aesthetics"], ["yellowing"])

    pr1 = ProductReviews(product_id="p1", product_title="P1", product_url="https://ex.com/1", rank=1, reviews=[r1, r2])
    pr2 = ProductReviews(product_id="p2", product_title="P2", product_url="https://ex.com/2", rank=2, reviews=[r3])

    intel = ReviewIntelligence(query="case", market="us", created_at=datetime.now(timezone.utc), products=[pr1, pr2])

    # LLM produces TWO overlapping clusters for loose fit, plus ONE distinct cluster for yellowing
    mock_clusters = [
        {
            "name": "Case loosens and stretches out quickly",
            "category": "durability",
            "description": "Case loses elasticity and fits loosely.",
            "assigned_complaint_ids": ["r1"],
        },
        {
            "name": "Loose fit compromises protection",
            "category": "durability",
            "description": "Loose fitting case allows phone to rattle.",
            "assigned_complaint_ids": ["r1", "r2"],  # r1 assigned to both duplicate clusters!
        },
        {
            "name": "Clear case turns yellow",
            "category": "design_aesthetics",
            "description": "Material discolors over time.",
            "assigned_complaint_ids": ["r3"],
        },
    ]

    analysis = cluster_complaints(intel, llm_client=MockLLMClient(mock_clusters))

    # The two loose fit clusters must be merged into one
    # Yellowing must remain separate
    assert len(analysis.clusters) == 2

    loose_cluster = next(c for c in analysis.clusters if "loos" in c.problem.lower() or "stretch" in c.problem.lower())
    yellow_cluster = next(c for c in analysis.clusters if "yellow" in c.problem.lower())

    # r1 must only be counted ONCE in the merged cluster!
    assert loose_cluster.review_count == 2
    assert {ev.review_id for ev in loose_cluster.supporting_reviews} == {"r1", "r2"}

    assert yellow_cluster.review_count == 1
    assert yellow_cluster.supporting_reviews[0].review_id == "r3"


def test_unvalidated_evidence_excluded_never_fabricated():
    """Requirement 10: Unvalidated evidence excluded; never fabricate replacement evidence."""
    r1 = _make_review("r1", "p1", "Buttons are slightly stiff.", "Buttons are slightly stiff.", ["comfort_ergonomics"], ["stiff buttons"])
    pr = ProductReviews(product_id="p1", product_title="P1", product_url="https://ex.com/1", rank=1, reviews=[r1])
    intel = ReviewIntelligence(query="case", market="us", created_at=datetime.now(timezone.utc), products=[pr])

    # LLM returns a hallucinated quote that does not appear in the review text
    mock_clusters = [
        {
            "name": "Stiff buttons",
            "category": "comfort_ergonomics",
            "description": "Buttons require excessive force.",
            "assigned_complaints": [
                {"review_id": "r1", "quote": "Completely impossible to click any buttons at all"}
            ],
        }
    ]

    analysis = cluster_complaints(intel, llm_client=MockLLMClient(mock_clusters))

    # It will fall back to r1's classified quote or review text span ("Buttons are slightly stiff.")
    # which IS verbatim in the review.
    assert len(analysis.clusters) == 1
    ev = analysis.clusters[0].supporting_reviews[0]
    assert "Buttons are slightly stiff" in ev.evidence_quote
    assert ev.evidence_verified is True
    # Hallucinated quote was NEVER fabricated or included
    assert "impossible to click" not in ev.evidence_quote


def test_counter_evidence_renamed_to_not_observed_in_sampled_reviews():
    """Requirement 6: Rename counter-evidence to 'Not observed in sampled reviews.'"""
    r1 = _make_review("r1", "p1", "Loose fit", "Loose fit", ["size_fit"], ["loose fit"])
    pr1 = ProductReviews(product_id="p1", product_title="Brand Alpha", product_url="https://ex.com/p1", rank=1, reviews=[r1])
    pr2 = ProductReviews(product_id="p2", product_title="Brand Beta", product_url="https://ex.com/p2", rank=2, reviews=[])

    p1 = Product(id="p1", title="Brand Alpha Case", url="https://ex.com/p1", price=10.0, currency="USD", sources=["amazon"], listings=[])
    p2 = Product(id="p2", title="Brand Beta Case", url="https://ex.com/p2", price=12.0, currency="USD", sources=["amazon"], listings=[])

    rs = ResearchSet(query="case", market="us", currency="USD", created_at=datetime.now(timezone.utc), searches=[], products=[p1, p2])
    intel = ReviewIntelligence(query="case", market="us", created_at=datetime.now(timezone.utc), products=[pr1, pr2])

    mock_clusters = [
        {
            "name": "Case fits loosely",
            "category": "size_fit",
            "description": "Loose fit.",
            "assigned_complaints": [{"review_id": "r1", "quote": "Loose fit"}],
        }
    ]

    analysis = cluster_complaints(intel, llm_client=MockLLMClient(mock_clusters))
    report = build_final_report(rs, review_intel=intel, prob_analysis=analysis)

    term = render_terminal_report(report)
    md = render_markdown_report(report)

    # Must contain "Not observed in sampled reviews"
    assert "Not observed in sampled reviews" in term
    assert "Not observed in sampled reviews" in md

    # Must not contain "Counter-Evidence"
    assert "Counter-Evidence" not in term
    assert "Counter-Evidence" not in md

    # Clarification that absence does not infer competitor lacks the issue
    assert "does not infer" in term.lower()
    assert "does not infer" in md.lower()
