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

    analysis = cluster_complaints(intel)
    assert len(analysis.clusters) >= 2
    assert analysis.total_complaints_analyzed == 3

    # Check top problem
    top = analysis.clusters[0]
    assert top.name == "Slippery / poor grip"
    assert top.total_complaints == 2
    assert top.affected_product_count == 2
    assert top.avg_severity == 3.0
    assert len(top.sample_evidence) == 2
    assert all(ev.evidence_verified for ev in top.sample_evidence)


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
