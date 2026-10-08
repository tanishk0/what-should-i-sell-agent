"""Unit tests for complaint clustering and problem discovery."""
from datetime import datetime, timezone

from wsis.reviews.clustering import cluster_complaints
from wsis.reviews.models import (
    AspectTag,
    ProductReviews,
    Review,
    ReviewCitation,
    ReviewClassification,
    ReviewIntelligence,
)


def _make_dummy_complaint(review_id: str, product_id: str, title: str, text: str, category: str, issue: str, severity: int = 2):
    citation = ReviewCitation(source="amazon", engine="amazon_product", product_url="https://example.com")
    return Review(
        id=review_id,
        product_id=product_id,
        product_title=title,
        source="amazon",
        listing_id="LISTING123",
        text=text,
        original_text=text,
        url="https://example.com/rev",
        citation=citation,
        classification=ReviewClassification(
            sentiment="negative",
            is_complaint=True,
            noise=False,
            categories=[category],
            issues=[issue],
            severity=severity,
            evidence_quote=text[:30],
            evidence_verified=True,
            model="test",
            prompt_version="v1",
        ),
    )


def test_clustering_groups_complaints():
    r1 = _make_dummy_complaint("r1", "p1", "Mat Alpha", "Slippery surface, slides on floor", "performance", "Slippery / poor grip", 3)
    r2 = _make_dummy_complaint("r2", "p2", "Mat Beta", "Zero grip when hands get sweaty", "performance", "Slippery / poor grip", 3)
    r3 = _make_dummy_complaint("r3", "p1", "Mat Alpha", "Tore along edge after 1 week", "durability", "Material tears quickly", 2)

    pr1 = ProductReviews(product_id="p1", product_title="Mat Alpha", product_url="https://example.com", rank=1, reviews=[r1, r3])
    pr2 = ProductReviews(product_id="p2", product_title="Mat Beta", product_url="https://example.com", rank=2, reviews=[r2])

    intel = ReviewIntelligence(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        products=[pr1, pr2],
    )

    import json

    class MockResponse:
        text = json.dumps({
            "clusters": [
                {
                    "name": "Slippery surface / poor grip",
                    "category": "performance",
                    "description": "Users report slipping on the mat during workouts.",
                    "complaint_ids": ["r1", "r2"],
                    "avg_severity": 3.0,
                },
                {
                    "name": "Material tears easily",
                    "category": "durability",
                    "description": "Mat tears along edges quickly.",
                    "complaint_ids": ["r3"],
                    "avg_severity": 2.0,
                },
            ]
        })

    class MockClient:
        class models:
            @staticmethod
            def generate_content(*args, **kwargs):
                return MockResponse()

    analysis = cluster_complaints(intel, llm_client=MockClient())
    assert len(analysis.clusters) >= 2
    assert analysis.total_complaints_analyzed == 3

    # Programmatic evidence source of truth verification
    top = analysis.clusters[0]
    assert top.problem == "Slippery surface / poor grip"
    assert top.review_count == len(top.supporting_reviews) == 2
    assert top.product_count == len(top.supporting_products) == 2
    assert top.supporting_products == ["p1", "p2"]
    assert top.unaffected_products == []
    assert top.is_widespread_gap is True
    assert top.avg_severity == 3.0
    assert len(top.sample_evidence) == 2
    assert all(ev.evidence_verified for ev in top.sample_evidence)

    # Problem 2 was isolated to product p1 only
    second = analysis.clusters[1]
    assert second.problem == "Material tears easily"
    assert second.review_count == 1
    assert second.product_count == 1
    assert second.supporting_products == ["p1"]
    assert second.unaffected_products == ["p2"]  # Counter-evidence!
    assert second.is_widespread_gap is False


def test_clustering_handles_empty():
    intel = ReviewIntelligence(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        products=[],
    )
    analysis = cluster_complaints(intel)
    assert analysis.total_complaints_analyzed == 0
    assert len(analysis.clusters) == 0
