"""Tests for Step 8 Evidence-Backed Final Opportunity Report."""
from __future__ import annotations

from datetime import datetime, timezone

from wsis.assessment.models import CompetitorAssessment, CompetitorProfile, MarketGapAnalysis
from wsis.challenge.models import ChallengeEvaluation, ChallengeLoopAnalysis, EvidenceItem, FinalOpportunity
from wsis.report.builder import build_final_report, render_markdown_report, render_terminal_report
from wsis.report.models import FinalOpportunityReport
from wsis.reviews.models import ReviewCitation
from wsis.reviews.problem_models import ComplaintEvidence, ProblemAnalysis, ProblemCluster
from wsis.schema import Product, ResearchSet
from wsis.spec.models import ProductSpec, SpecItem


def _make_mock_fixture():
    now = datetime.now(timezone.utc)
    cit = ReviewCitation(source="amazon", engine="amazon_product", product_url="https://amazon.com/dp/B001")

    p1 = Product(
        id="prod_01",
        title="Milton Compact Lunch Box 800ml",
        url="https://amazon.com/dp/B001",
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
        url="https://amazon.com/dp/B002",
        price=899.0,
        currency="INR",
        rating=4.4,
        review_count=95,
        sources=["amazon"],
        listings=[],
    )

    rs = ResearchSet(
        query="lunch box",
        market="in",
        currency="INR",
        created_at=now,
        searches=[],
        products=[p1, p2],
    )

    prob = ProblemAnalysis(
        query="lunch box",
        market="in",
        created_at=now,
        total_reviews_analyzed=100,
        total_complaints_analyzed=35,
        clusters=[
            ProblemCluster(
                id="prob_01",
                name="Liquid leakage when carried sideways",
                category="durability",
                description="Leakage when carrying liquids sideways in backpacks.",
                affected_products=["prod_01", "prod_02"],
                affected_product_count=2,
                total_complaints=23,
                frequency_score=0.23,
                opportunity_score=0.88,
                sample_evidence=[
                    ComplaintEvidence(
                        review_id="rev_01",
                        product_id="prod_01",
                        product_title="Milton Compact Lunch Box",
                        rating=1.0,
                        original_text="Lid snaps open inside backpack and soup leaks everywhere.",
                        evidence_quote="Lid snaps open inside backpack and soup leaks everywhere.",
                        evidence_verified=True,
                        url="https://amazon.com/rev1",
                        citation=cit,
                    ),
                    ComplaintEvidence(
                        review_id="rev_02",
                        product_id="prod_02",
                        product_title="Cello Max Fresh",
                        rating=2.0,
                        original_text="Cannot put dal or curry, it leaks through the corner gasket.",
                        evidence_quote="it leaks through the corner gasket.",
                        evidence_verified=True,
                        url="https://amazon.com/rev2",
                        citation=cit,
                    ),
                ],
            )
        ],
    )

    challenge = ChallengeLoopAnalysis(
        query="lunch box",
        market="in",
        created_at=now,
        hypotheses_evaluated=1,
        evaluations=[
            ChallengeEvaluation(
                hypothesis_id="hyp_01",
                opportunity_id="opp_01",
                title="Compact Leakproof Lunch Box",
                problem_name="Liquid leakage",
                total_competitors_checked=15,
                competitors_with_complaint=8,
                prevalence_ratio=0.53,
                verdict="STRENGTHENED",
                initial_confidence=0.70,
                final_confidence=0.88,
                initial_score=0.85,
                final_score=1.06,
                contradictory_evidence=[
                    EvidenceItem(
                        type="isolated_defect",
                        summary="Gasket degradation over time",
                        detail="High-temperature dishwasher cycles degrade the silicone gasket elasticity after 6 months.",
                        evidence_quotes=["Gasket became loose after hot wash."],
                        affected_products=["prod_01"],
                    )
                ],
                corroborating_evidence=[],
                agent_reasoning="Widespread defect across 53% of competitors creates substantial opportunity.",
                recommendation="PURSUE_HIGH_CONVICTION",
            )
        ],
        final_opportunities=[
            FinalOpportunity(
                rank=1,
                opportunity_id="opp_01",
                hypothesis_id="hyp_01",
                title="Compact Leakproof Lunch Box",
                problem_name="Liquid leakage",
                category="durability",
                improvement_type="structural",
                improvement_concept="Reinforced silicone seal + 4-point snap lock",
                differentiation_angle="True leakproofing in a slim office-friendly profile",
                verdict="STRENGTHENED",
                final_score=1.06,
                confidence=0.88,
                recommendation="PURSUE_HIGH_CONVICTION",
                competitor_prevalence="8/15 competitors (53.3%)",
                agent_assessment="High conviction whitespace for leakproof slim profile.",
                supporting_evidence_quotes=[],
            )
        ],
    )

    assessment = CompetitorAssessment(
        query="lunch box",
        market="in",
        currency="INR",
        created_at=now,
        opportunity_id="opp_01",
        opportunity_title="Compact Leakproof Lunch Box",
        target_problem="Liquid leakage",
        competitors=[
            CompetitorProfile(
                id="prod_01",
                name="Milton Compact",
                price_display="₹699",
                price=699.0,
                rating=4.2,
                main_strength="Compact",
                problem="Leaks",
                url="https://amazon.com/dp/B001",
            ),
            CompetitorProfile(
                id="prod_02",
                name="Cello Max Fresh",
                price_display="₹899",
                price=899.0,
                rating=4.4,
                main_strength="Durable",
                problem="Bulky",
                url="https://amazon.com/dp/B002",
            ),
        ],
        gap_analysis=MarketGapAnalysis(
            where_is_the_gap="Whitespace exists between ₹699 and ₹899 for compact leakproof containers.",
            unmet_need_summary="Existing products solve portability OR leak resistance, but few combine both without increasing bulk.",
            price_gap_range="₹699–₹899",
            tradeoff_to_break="Portability vs Leak Resistance",
            winning_positioning="The only slim-profile lunch box guaranteed leakproof under sideways tilt.",
        ),
    )

    spec = ProductSpec(
        query="lunch box",
        market="in",
        currency="INR",
        opportunity_id="opp_01",
        opportunity_title="Compact Leakproof Lunch Box",
        verdict="STRENGTHENED",
        confidence=0.88,
        build=SpecItem(field="build", statement="700–900ml compact lunch box"),
        must_have=[
            SpecItem(field="must_have", statement="improved silicone seal"),
            SpecItem(field="must_have", statement="locking lid"),
        ],
        avoid=[SpecItem(field="avoid", statement="bulky multi-container design")],
        target_price=SpecItem(field="target_price", statement="₹699–₹899"),
        primary_customer=SpecItem(field="primary_customer", statement="office and college users carrying liquids"),
        created_at=now,
    )

    return rs, prob, challenge, assessment, spec


def test_build_final_report_structure():
    rs, prob, challenge, assessment, spec = _make_mock_fixture()

    report = build_final_report(
        research_set=rs,
        prob_analysis=prob,
        challenge_analysis=challenge,
        assessment=assessment,
        spec=spec,
    )

    assert isinstance(report, FinalOpportunityReport)
    assert report.title == "COMPACT LEAKPROOF LUNCH BOX"
    assert report.confidence == "HIGH"
    assert "leakage" in report.customer_problem.lower()

    # Evidence stats
    assert report.evidence_stats.unique_reviews == 23
    assert report.evidence_stats.competing_products == 2
    assert report.evidence_stats.review_share_pct == 23.0
    assert report.evidence_stats.total_reviews_analyzed == 100

    # Quotes
    assert len(report.review_quotes) == 2
    assert any("soup leaks" in q.text for q in report.review_quotes)

    # What to build & avoid
    assert any("700–900ml" in b for b in report.what_to_build)
    assert any("silicone seal" in b for b in report.what_to_build)
    assert any("bulky" in a for a in report.what_to_avoid)

    # Price & Customer
    assert report.target_price == "₹699–₹899"
    assert "office" in report.primary_customer.lower()

    # Competitors
    assert len(report.competitors) == 2
    assert report.competitors[0].name == "Milton Compact"
    assert report.competitors[0].problem == "Leaks"

    # Counter-Evidence
    assert len(report.counter_evidence) >= 1
    assert any("silicone gasket" in ce.lower() or "dishwasher" in ce.lower() for ce in report.counter_evidence)


def test_render_terminal_and_markdown():
    rs, prob, challenge, assessment, spec = _make_mock_fixture()
    report = build_final_report(
        research_set=rs,
        prob_analysis=prob,
        challenge_analysis=challenge,
        assessment=assessment,
        spec=spec,
    )

    terminal_text = render_terminal_report(report)

    # Validate exact UI sections requested in Step 8
    assert "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" in terminal_text
    assert "PRODUCT OPPORTUNITY" in terminal_text
    assert "COMPACT LEAKPROOF LUNCH BOX" in terminal_text
    assert "Opportunity confidence: HIGH" in terminal_text
    assert "Why this opportunity?" in terminal_text
    assert "CUSTOMER PROBLEM" in terminal_text
    assert "Evidence" in terminal_text
    assert "• 23 unique reviews" in terminal_text
    assert "• 2 competing products" in terminal_text
    assert "• 23.0% of analyzed reviews mentioning defect" in terminal_text
    assert "PRODUCT GAP" in terminal_text
    assert "WHAT TO BUILD" in terminal_text
    assert "✓" in terminal_text
    assert "✕" in terminal_text
    assert "PRICE" in terminal_text
    assert "₹699–₹899" in terminal_text
    assert "COMPETITORS" in terminal_text
    assert "EVIDENCE" in terminal_text
    assert "COUNTER-EVIDENCE" in terminal_text

    # Markdown format
    md_text = render_markdown_report(report)
    assert "# Product Opportunity Report: COMPACT LEAKPROOF LUNCH BOX" in md_text
    assert "## What to Build" in md_text
    assert "## Competitor Matrix" in md_text
    assert "## Counter-Evidence & Risks" in md_text
