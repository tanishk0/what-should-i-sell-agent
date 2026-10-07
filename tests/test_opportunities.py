"""Unit tests for Step 4 candidate product opportunity generation."""
from datetime import datetime, timezone

from wsis.opportunities import CandidateOpportunity, OpportunityAnalysis, generate_candidate_opportunities
from wsis.reviews.models import ReviewCitation
from wsis.reviews.problem_models import ComplaintEvidence, ProblemAnalysis, ProblemCluster


def _make_dummy_evidence(review_id: str, quote: str) -> ComplaintEvidence:
    citation = ReviewCitation(source="amazon", engine="amazon_product", product_url="https://example.com")
    return ComplaintEvidence(
        review_id=review_id,
        product_id="prod_01",
        product_title="Test Yoga Mat Alpha",
        rating=1.0,
        original_text=f"The mat is terribly slippery when sweating. {quote}",
        evidence_quote=quote,
        evidence_verified=True,
        url="https://example.com/review",
        citation=citation,
    )


def test_generate_opportunities_from_problems():
    ev1 = _make_dummy_evidence("r1", "slippery when sweating")
    ev2 = _make_dummy_evidence("r2", "tears easily along edges")

    cluster1 = ProblemCluster(
        id="prob_01",
        name="Slippery surface when hands get sweaty",
        category="performance",
        description="Users report losing traction and sliding during intense yoga or sweaty sessions.",
        affected_products=["prod_01", "prod_02"],
        affected_product_count=2,
        total_complaints=12,
        avg_severity=2.8,
        frequency_score=0.45,
        opportunity_score=0.84,
        sample_evidence=[ev1],
    )

    cluster2 = ProblemCluster(
        id="prob_02",
        name="Material tears easily and flakes off",
        category="durability",
        description="Buyer complaints indicate the mat begins flaking and tearing within weeks of purchase.",
        affected_products=["prod_01"],
        affected_product_count=1,
        total_complaints=6,
        avg_severity=2.5,
        frequency_score=0.25,
        opportunity_score=0.35,
        sample_evidence=[ev2],
    )

    analysis = ProblemAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=50,
        total_complaints_analyzed=18,
        clusters=[cluster1, cluster2],
    )

    opp_analysis = generate_candidate_opportunities(analysis)

    assert isinstance(opp_analysis, OpportunityAnalysis)
    assert opp_analysis.total_problems_evaluated == 2
    assert len(opp_analysis.opportunities) == 2

    # Verify top opportunity addresses problem 1
    top_opp = opp_analysis.opportunities[0]
    assert isinstance(top_opp, CandidateOpportunity)
    assert top_opp.problem_id == "prob_01"
    assert "slip" in top_opp.problem_name.lower() or "grip" in top_opp.title.lower()
    assert len(top_opp.improvement_concept) > 20
    # Answers the question: What product improvement could directly solve this problem?
    assert "solve" in top_opp.improvement_concept.lower() or "traction" in top_opp.improvement_concept.lower()
    assert top_opp.priority_score > 0
    assert len(top_opp.supporting_evidence_quotes) > 0
    assert top_opp.supporting_evidence_quotes[0] == "slippery when sweating"


def test_generate_opportunities_empty():
    analysis = ProblemAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=0,
        total_complaints_analyzed=0,
        clusters=[],
    )

    opp_analysis = generate_candidate_opportunities(analysis)
    assert opp_analysis.total_problems_evaluated == 0
    assert len(opp_analysis.opportunities) == 0
    assert opp_analysis.method == "empty"


def test_opportunity_serialization():
    opp = CandidateOpportunity(
        id="opp_01",
        title="Anti-Slip Dual Texture Grip Layer",
        problem_id="prob_01",
        problem_name="Slippery when wet",
        category="performance",
        improvement_type="material_upgrade",
        improvement_concept="Directly solves slipping via laser-textured moisture-wicking polyurethane surface.",
        differentiation_angle="Zero-slip guarantee for 90-minute workouts.",
        implementation_feasibility="high",
        expected_impact="Reduces slip complaints by 90%.",
        target_price_impact="minor_premium",
        priority_score=0.966,
        affected_product_count=3,
        supporting_evidence_quotes=["slips on sweat"],
    )

    data = opp.model_dump()
    assert data["id"] == "opp_01"
    assert data["implementation_feasibility"] == "high"
    assert opp.model_dump_json() is not None
