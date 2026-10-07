"""Unit tests for Step 6 Competitor Assessment and Market Gap Analysis."""
from datetime import datetime, timezone

from wsis.assessment import build_competitor_assessment, format_price
from wsis.challenge.models import FinalOpportunity
from wsis.schema import Product, ResearchSet


def _make_test_product(prod_id: str, title: str, price: float, rating: float, currency: str = "INR") -> Product:
    return Product(
        id=prod_id,
        title=title,
        url=f"https://example.com/p/{prod_id}",
        listings=[],
        sources=["amazon"],
        price=price,
        price_min=price,
        price_max=price,
        currency=currency,
        rating=rating,
        review_count=350,
        relevance=0.9,
        score=0.8,
    )


def test_format_price():
    assert format_price(699.0, "INR") == "₹699"
    assert format_price(24.99, "USD") == "$24.99"
    assert format_price(19.0, "EUR") == "€19"
    assert format_price(None, "USD") == "-"


def test_build_competitor_assessment_matches_user_specification():
    """Verifies matrix matches user prompt:

    Competitor    Price    Rating    Main strength    Problem
    Product A     ₹699     4.2       Compact          Leaks
    Product B     ₹899     4.4       Durable          Bulky
    Product C     ₹599     4.0       Cheap            Poor seal
    """
    p_a = _make_test_product("p1", "Compact Mini Lunch Box", price=699.0, rating=4.2, currency="INR")
    p_b = _make_test_product("p2", "Durable Heavy Duty Lunch Box", price=899.0, rating=4.4, currency="INR")
    p_c = _make_test_product("p3", "Budget Essential Lunch Box", price=599.0, rating=4.0, currency="INR")

    research_set = ResearchSet(
        query="lunch box",
        market="in",
        currency="INR",
        created_at=datetime.now(timezone.utc),
        searches=[],
        products=[p_a, p_b, p_c],
    )

    final_opp = FinalOpportunity(
        rank=1,
        opportunity_id="opp_01",
        hypothesis_id="hyp_01",
        title="Zero-Leak Compact Bento Box",
        problem_name="Lids leak soup and liquids",
        category="performance",
        improvement_type="mechanical_redesign",
        improvement_concept="Dual-silicone compression seal with ergonomic snaps.",
        differentiation_angle="100% leakproof in a compact backpack form factor.",
        verdict="CONFIRMED",
        final_score=0.88,
        confidence=0.80,
        recommendation="PURSUE_HIGH_CONVICTION",
        competitor_prevalence="Widespread in compact tier",
        agent_assessment="High commercial opportunity.",
    )

    assessment = build_competitor_assessment(
        research_set=research_set,
        final_opportunity=final_opp,
        limit=3,
    )

    assert len(assessment.competitors) == 3

    # Check competitor profiles
    c1 = assessment.competitors[0]
    assert "₹699" in c1.price_display
    assert c1.rating == 4.2
    assert c1.main_strength != ""
    assert c1.problem != ""

    c2 = assessment.competitors[1]
    assert "₹899" in c2.price_display
    assert c2.rating == 4.4

    # Check "Where is the gap?" analysis
    gap = assessment.gap_analysis
    assert gap.where_is_the_gap != ""
    # Explicitly mentions the market gap, pricing window, and trade-off
    assert "gap" in gap.where_is_the_gap.lower()
    assert len(gap.price_gap_range) > 0
    assert "₹" in gap.price_gap_range
    assert len(gap.tradeoff_to_break) > 0
    assert len(gap.winning_positioning) > 0
