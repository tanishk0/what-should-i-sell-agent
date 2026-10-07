from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from wsis.db import MongoStorage
from wsis.reviews.models import (
    AspectInsight,
    ProductReviews,
    Review,
    ReviewCitation,
    ReviewIntelligence,
)
from wsis.reviews.problem_models import ProblemAnalysis, ProblemCluster
from wsis.schema import Citation, Listing, Product, ResearchSet, SearchRecord


def _make_dummy_research_set() -> ResearchSet:
    cit = Citation(source="amazon", engine="amazon", search_id="s1")
    listing = Listing(
        source="amazon",
        source_product_id="B001",
        title="Test Yoga Mat",
        url="https://amazon.com/dp/B001",
        price=29.99,
        currency="USD",
        citation=cit,
    )
    product = Product(
        id="B001",
        title="Test Yoga Mat",
        url="https://amazon.com/dp/B001",
        price=29.99,
        sources=["amazon"],
        listings=[listing],
        relevance=1.0,
        score=0.9,
    )
    search = SearchRecord(
        source="amazon",
        engine="amazon",
        params={"q": "yoga mat"},
    )
    return ResearchSet(
        query="yoga mat",
        market="us",
        currency="USD",
        created_at=datetime.now(timezone.utc),
        searches=[search],
        products=[product],
    )


def test_mongo_from_env_none(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)
    assert MongoStorage.from_env() is None


def test_mongo_from_env_configured(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "custom_wsis")
    storage = MongoStorage.from_env()
    assert storage is not None
    assert storage.uri == "mongodb://localhost:27017"
    assert storage.db_name == "custom_wsis"


def test_mongo_save_research_set():
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    storage = MongoStorage(uri="mongodb://localhost:27017", db_name="test_db", client=mock_client)

    rs = _make_dummy_research_set()
    run_id = storage.save_research_set(rs, run_id="run-123")

    assert run_id == "run-123"
    # Verify research_runs replacement
    mock_db.research_runs.replace_one.assert_called_once()
    args, kwargs = mock_db.research_runs.replace_one.call_args
    assert args[0] == {"_id": "run-123"}
    assert args[1]["query"] == "yoga mat"
    assert kwargs.get("upsert") is True

    # Verify products replacement
    mock_db.products.replace_one.assert_called_once()
    prod_args, prod_kwargs = mock_db.products.replace_one.call_args
    assert prod_args[0] == {"run_id": "run-123", "id": "B001"}
    assert prod_args[1]["title"] == "Test Yoga Mat"


def test_mongo_save_reviews_and_problems():
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    storage = MongoStorage(uri="mongodb://localhost:27017", db_name="test_db", client=mock_client)

    rev_cit = ReviewCitation(
        source="amazon",
        engine="amazon_product",
        product_url="https://amazon.com/dp/B001",
    )
    rev_intel = ReviewIntelligence(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        llm_model="test-model",
        products=[
            ProductReviews(
                product_id="B001",
                product_title="Test Yoga Mat",
                product_url="https://amazon.com/dp/B001",
                rank=1,
            )
        ],
    )
    prob_analysis = ProblemAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=10,
        total_complaints_analyzed=5,
        clusters=[
            ProblemCluster(
                id="prob-1",
                name="Slippery surface",
                category="performance",
                description="Mat becomes slippery when sweaty.",
                total_complaints=5,
                opportunity_score=0.85,
            )
        ],
    )

    rev_doc_id = storage.save_review_intelligence(rev_intel, run_id="run-123")
    assert rev_doc_id == "run-123_reviews"
    mock_db.review_intelligence.replace_one.assert_called_once()

    prob_doc_id = storage.save_problem_analysis(prob_analysis, run_id="run-123")
    assert prob_doc_id == "run-123_problems"
    mock_db.problem_analyses.replace_one.assert_called_once()
    mock_db.problem_clusters.replace_one.assert_called_once()

    from wsis.opportunities.models import CandidateOpportunity, OpportunityAnalysis

    opp_analysis = OpportunityAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_problems_evaluated=1,
        opportunities=[
            CandidateOpportunity(
                id="opp_01",
                title="Non-Slip Grip Layer",
                problem_id="prob-1",
                problem_name="Slippery surface",
                category="performance",
                improvement_type="material_upgrade",
                improvement_concept="Laser-textured moisture wicking surface.",
                differentiation_angle="Zero slip guarantee.",
                implementation_feasibility="high",
                expected_impact="High rating lift.",
                target_price_impact="cost_neutral",
                priority_score=0.92,
            )
        ],
    )

    opp_doc_id = storage.save_opportunity_analysis(opp_analysis, run_id="run-123")
    assert opp_doc_id == "run-123_opportunities"
    mock_db.opportunity_analyses.replace_one.assert_called_once()
    mock_db.candidate_opportunities.replace_one.assert_called_once()

    from wsis.challenge.models import ChallengeLoopAnalysis, FinalOpportunity

    challenge_analysis = ChallengeLoopAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        hypotheses_evaluated=1,
        final_opportunities=[
            FinalOpportunity(
                rank=1,
                opportunity_id="opp_01",
                hypothesis_id="hyp_01",
                title="Non-Slip Grip Layer",
                problem_name="Slippery surface",
                category="performance",
                improvement_type="material_upgrade",
                improvement_concept="Laser textured.",
                differentiation_angle="Zero slip.",
                verdict="STRENGTHENED",
                final_score=1.15,
                confidence=0.88,
                recommendation="PURSUE_HIGH_CONVICTION",
                competitor_prevalence="9/15 competitors (60.0%)",
                agent_assessment="Confirmed endemic failure.",
            )
        ],
    )

    chal_doc_id = storage.save_challenge_analysis(challenge_analysis, run_id="run-123")
    assert chal_doc_id == "run-123_challenge"
    mock_db.challenge_runs.replace_one.assert_called_once()
    mock_db.final_opportunities.replace_one.assert_called_once()

    from wsis.assessment.models import CompetitorAssessment, CompetitorProfile, MarketGapAnalysis

    assessment = CompetitorAssessment(
        query="yoga mat",
        market="us",
        opportunity_id="opp_01",
        opportunity_title="Non-Slip Grip Layer",
        target_problem="Slippery surface",
        competitors=[
            CompetitorProfile(
                id="p1",
                name="Brand Alpha",
                price_display="$24.99",
                price=24.99,
                rating=4.2,
                review_count=120,
                main_strength="Compact",
                problem="Slippery",
                url="https://example.com/p1",
            )
        ],
        gap_analysis=MarketGapAnalysis(
            where_is_the_gap="The gap is at the $28-$35 range.",
            unmet_need_summary="High grip without bulk.",
            price_gap_range="$28 - $35",
            tradeoff_to_break="Comfort vs Grip",
            winning_positioning="Zero-slip guarantee.",
        ),
        created_at=datetime.now(timezone.utc),
    )

    assess_doc_id = storage.save_competitor_assessment(assessment, run_id="run-123")
    assert assess_doc_id == "run-123_assessment"
    mock_db.competitor_assessments.replace_one.assert_called_once()
    mock_db.competitor_profiles.replace_one.assert_called_once()

    from wsis.spec.models import ProductSpec, SpecItem

    spec = ProductSpec(
        query="yoga mat",
        market="us",
        currency="USD",
        opportunity_id="opp_01",
        opportunity_title="Non-Slip Grip Layer",
        verdict="CONFIRMED",
        confidence=0.8,
        build=SpecItem(field="build", statement="6mm textured yoga mat"),
        must_have=[SpecItem(field="must_have", statement="Non-slip polyurethane grip")],
        avoid=[SpecItem(field="avoid", statement="Chemical odor")],
        target_price=SpecItem(field="target_price", statement="$28–$34"),
        primary_customer=SpecItem(field="primary_customer", statement="hot-yoga practitioners"),
        created_at=datetime.now(timezone.utc),
    )

    spec_doc_id = storage.save_product_spec(spec, run_id="run-123")
    assert spec_doc_id == "run-123_spec"
    mock_db.product_specs.replace_one.assert_called_once()

    from wsis.report.models import EvidenceStats, FinalOpportunityReport

    report = FinalOpportunityReport(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        title="NON-SLIP DUAL-LAYER YOGA MAT",
        confidence="HIGH",
        why_this_opportunity="High demand for non-slip traction during hot yoga.",
        customer_problem="Slippery surface when wet.",
        evidence_stats=EvidenceStats(
            unique_reviews=15,
            competing_products=4,
            review_share_pct=25.0,
            total_reviews_analyzed=60,
            total_products_analyzed=8,
        ),
        product_gap="Portability vs grip compromise.",
        what_to_build=["6mm thickness", "laser-etched alignment"],
        what_to_avoid=["pungent odor"],
        target_price="$28–$34",
    )

    report_doc_id = storage.save_final_report(report, run_id="run-123")
    assert report_doc_id == "run-123_report"
    mock_db.final_reports.replace_one.assert_called_once()


def test_mongo_ping():
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1}
    storage = MongoStorage(uri="mongodb://localhost:27017", client=mock_client)
    assert storage.ping() is True

    from pymongo.errors import ConnectionFailure

    mock_client.admin.command.side_effect = ConnectionFailure("network error")
    assert storage.ping() is False
