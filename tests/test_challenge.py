"""Unit tests for Step 5 Agentic Challenge Loop."""
from datetime import datetime, timezone

from wsis.challenge import build_hypotheses, run_challenge_loop
from wsis.opportunities.models import CandidateOpportunity, OpportunityAnalysis
from wsis.reviews.models import ProductReviews, ReviewIntelligence
from wsis.reviews.problem_models import ProblemAnalysis, ProblemCluster
from wsis.schema import Product, ResearchSet


def _make_dummy_product(prod_id: str, title: str, rating: float = 4.2, review_count: int = 150) -> Product:
    return Product(
        id=prod_id,
        title=title,
        url=f"https://example.com/products/{prod_id}",
        listings=[],
        sources=["amazon"],
        rating=rating,
        review_count=review_count,
        price_min=19.99,
        price_max=19.99,
        relevance=0.9,
        score=0.8,
    )


def test_challenge_loop_downgrades_isolated_defect_2_of_15():
    """Matches hackathon example:

    Hypothesis: buyers want leakproof lunch boxes.
    Agent discovers complaints occur only in 2/15 products.
    Agent downgrades the opportunity!
    """
    # 15 total competitors in market
    products = [_make_dummy_product(f"p_{i}", f"Lunch Box Brand {i}") for i in range(1, 16)]
    research_set = ResearchSet(
        query="lunch box",
        market="us",
        currency="USD",
        created_at=datetime.now(timezone.utc),
        searches=[],
        products=products,
    )

    # Problem cluster where complaints were only found in 2 products
    cluster = ProblemCluster(
        id="prob_leak",
        name="Lids leak soup and liquids",
        category="performance",
        description="Lids leak when transported inside backpacks.",
        affected_products=["p_1", "p_2"],
        affected_product_count=2,
        total_complaints=5,
        avg_severity=2.5,
        opportunity_score=0.65,
    )

    problem_analysis = ProblemAnalysis(
        query="lunch box",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=100,
        total_complaints_analyzed=5,
        clusters=[cluster],
    )

    opp = CandidateOpportunity(
        id="opp_01",
        title="Zero-Leak Dual-Silicone Seal Lunch Box",
        problem_id="prob_leak",
        problem_name="Lids leak soup and liquids",
        category="performance",
        improvement_type="mechanical_redesign",
        improvement_concept="Double silicone compression gasket with 4-corner snap locks.",
        differentiation_angle="Guaranteed leakproof soup container.",
        implementation_feasibility="high",
        expected_impact="High return reduction.",
        target_price_impact="minor_premium",
        priority_score=0.7475,
        affected_product_count=2,
    )

    opp_analysis = OpportunityAnalysis(
        query="lunch box",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_problems_evaluated=1,
        opportunities=[opp],
    )

    rev_intel = ReviewIntelligence(
        query="lunch box",
        market="us",
        created_at=datetime.now(timezone.utc),
        products=[ProductReviews(product_id="p_1", product_title="Box 1", product_url="https://example.com", rank=1)],
    )

    challenge_result = run_challenge_loop(
        research_set=research_set,
        review_intel=rev_intel,
        problem_analysis=problem_analysis,
        opp_analysis=opp_analysis,
        max_hypotheses=1,
    )

    assert challenge_result.hypotheses_evaluated == 1
    eval_item = challenge_result.evaluations[0]

    # Verify adversarial challenge behavior
    assert eval_item.total_competitors_checked == 15
    assert eval_item.competitors_with_complaint == 2
    assert eval_item.prevalence_ratio == round(2 / 15, 3)

    # CRITICAL: Agent downgraded the opportunity!
    assert eval_item.verdict == "DOWNGRADED"
    assert eval_item.adjustment_factor < 0.60
    assert eval_item.final_score < eval_item.initial_score
    assert eval_item.final_confidence < eval_item.initial_confidence
    assert eval_item.recommendation == "DE-PRIORITIZE"

    # Contradictory evidence exists
    assert len(eval_item.contradictory_evidence) > 0
    assert eval_item.contradictory_evidence[0].type == "isolated_defect"
    assert "2 of 15" in eval_item.contradictory_evidence[0].summary

    # Final opportunity reflects downgrade
    final_opp = challenge_result.final_opportunities[0]
    assert final_opp.verdict == "DOWNGRADED"
    assert final_opp.recommendation == "DE-PRIORITIZE"
    assert "2/15 competitors" in final_opp.competitor_prevalence


def test_challenge_loop_strengthens_widespread_defect_9_of_15():
    """When a defect spans 9/15 competitors (60%), agent STRENGTHENS the opportunity!"""
    products = [_make_dummy_product(f"p_{i}", f"Yoga Mat Brand {i}") for i in range(1, 16)]
    research_set = ResearchSet(
        query="yoga mat",
        market="us",
        currency="USD",
        created_at=datetime.now(timezone.utc),
        searches=[],
        products=products,
    )

    # Problem cluster where complaints span 9 products
    cluster = ProblemCluster(
        id="prob_slip",
        name="Slippery surface when sweating",
        category="performance",
        description="Sweat causes loss of grip.",
        affected_products=[f"p_{i}" for i in range(1, 10)],
        affected_product_count=9,
        total_complaints=42,
        avg_severity=2.9,
        opportunity_score=0.85,
    )

    problem_analysis = ProblemAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=100,
        total_complaints_analyzed=42,
        clusters=[cluster],
    )

    opp = CandidateOpportunity(
        id="opp_01",
        title="Laser-Textured Moisture Wicking Mat",
        problem_id="prob_slip",
        problem_name="Slippery surface when sweating",
        category="performance",
        improvement_type="material_upgrade",
        improvement_concept="Laser-textured grip layer.",
        differentiation_angle="Zero slip guarantee.",
        implementation_feasibility="high",
        expected_impact="Massive rating boost.",
        target_price_impact="minor_premium",
        priority_score=0.9775,
        affected_product_count=9,
    )

    opp_analysis = OpportunityAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_problems_evaluated=1,
        opportunities=[opp],
    )

    rev_intel = ReviewIntelligence(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        products=[],
    )

    challenge_result = run_challenge_loop(
        research_set=research_set,
        review_intel=rev_intel,
        problem_analysis=problem_analysis,
        opp_analysis=opp_analysis,
        max_hypotheses=1,
    )

    eval_item = challenge_result.evaluations[0]
    assert eval_item.total_competitors_checked == 15
    assert eval_item.competitors_with_complaint == 9
    assert eval_item.prevalence_ratio == 0.6

    # CRITICAL: Agent strengthened the opportunity!
    assert eval_item.verdict == "STRENGTHENED"
    assert eval_item.adjustment_factor > 1.0
    assert eval_item.final_score > eval_item.initial_score
    assert eval_item.recommendation == "PURSUE_HIGH_CONVICTION"
    assert len(eval_item.corroborating_evidence) > 0
    assert eval_item.corroborating_evidence[0].type == "widespread_endemic_defect"


def test_challenge_empty_handling():
    research_set = ResearchSet(
        query="test",
        market="us",
        currency="USD",
        created_at=datetime.now(timezone.utc),
        searches=[],
        products=[],
    )
    problem_analysis = ProblemAnalysis(
        query="test",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=0,
        total_complaints_analyzed=0,
        clusters=[],
    )
    opp_analysis = OpportunityAnalysis(
        query="test",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_problems_evaluated=0,
        opportunities=[],
    )
    rev_intel = ReviewIntelligence(
        query="test",
        market="us",
        created_at=datetime.now(timezone.utc),
        products=[],
    )

    result = run_challenge_loop(
        research_set=research_set,
        review_intel=rev_intel,
        problem_analysis=problem_analysis,
        opp_analysis=opp_analysis,
    )
    assert result.hypotheses_evaluated == 0
    assert len(result.final_opportunities) == 0
    assert result.method == "empty"
