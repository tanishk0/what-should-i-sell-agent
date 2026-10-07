"""Tests for Step 7: traceable product specification."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from wsis.challenge.models import FinalOpportunity
from wsis.opportunities.models import CandidateOpportunity, OpportunityAnalysis
from wsis.reviews.models import ProductReviews, Review, ReviewCitation, ReviewClassification, ReviewIntelligence
from wsis.reviews.problem_models import ComplaintEvidence, ProblemAnalysis, ProblemCluster
from wsis.schema import Product, ResearchSet
from wsis.spec import build_product_spec, spec_to_markdown

NOW = datetime.now(timezone.utc)


def _product(pid, title, price, rating):
    return Product(id=pid, title=title, url=f"https://ex.com/{pid}", price=price, currency="INR",
                   rating=rating, review_count=500, sources=["amazon"], listings=[])


def _review(rid, pid, text, complaint=True, issue="", quote=None):
    cit = ReviewCitation(source="amazon", engine="amazon_product", product_url=f"https://ex.com/{pid}")
    cls = ReviewClassification(
        sentiment="negative" if complaint else "positive", is_complaint=complaint,
        issues=[issue] if issue else [], categories=["performance"] if complaint else [],
        severity=3 if complaint else None, evidence_quote=quote, evidence_verified=bool(quote and quote in text),
        model="test", prompt_version="v1",
    )
    return Review(id=rid, product_id=pid, product_title=f"Box {pid}", source="amazon", listing_id=pid,
                  text=text, original_text=text, rating=2.0 if complaint else 5.0,
                  url=f"https://ex.com/{pid}#{rid}", citation=cit, classification=cls)


def _evidence(r):
    return ComplaintEvidence(review_id=r.id, product_id=r.product_id, product_title=r.product_title,
                             original_text=r.original_text, evidence_quote=r.classification.evidence_quote,
                             evidence_verified=r.classification.evidence_verified, url=r.url, citation=r.citation)


def _fixture():
    products = [
        _product("p1", "SteelFresh Compact Lunch Box 750ml", 699, 4.2),
        _product("p2", "Milton Durable 3 Container Lunch Box 900ml", 899, 4.4),
        _product("p3", "Budget Lunch Box 750ml", 599, 4.0),
        _product("p4", "Premium Insulated Tiffin 1200ml", 1299, 4.3),
        _product("p5", "Kids Bento Lunch Box 900ml", 749, 4.5),
    ]
    rs = ResearchSet(query="lunch box", market="in", currency="INR", created_at=NOW, searches=[], products=products)

    r1 = _review("r1", "p1", "Great size. But the dal leaked all over my office bag on day two.",
                 issue="lid leaks", quote="the dal leaked all over my office bag")
    r2 = _review("r2", "p3", "Seal is weak. Curry spilled in my college backpack.", issue="poor seal",
                 quote="Curry spilled in my college backpack")
    r3 = _review("r3", "p2", "Doesn't leak but way too bulky with three containers, won't fit my bag.",
                 issue="too bulky", quote="way too bulky with three containers")
    r4 = _review("r4", "p5", "I carry it to the office every day, love it.", complaint=False)

    ri = ReviewIntelligence(query="lunch box", market="in", created_at=NOW, products=[
        ProductReviews(product_id="p1", product_title="Box p1", product_url="u", rank=1, reviews=[r1]),
        ProductReviews(product_id="p3", product_title="Box p3", product_url="u", rank=2, reviews=[r2]),
        ProductReviews(product_id="p2", product_title="Box p2", product_url="u", rank=3, reviews=[r3]),
        ProductReviews(product_id="p5", product_title="Box p5", product_url="u", rank=4, reviews=[r4]),
    ])

    leak = ProblemCluster(id="prob_01", name="Lids leak liquids", category="performance",
                          description="Liquids leak through the lid seal.", affected_products=["p1", "p3"],
                          affected_product_count=2, total_complaints=2, avg_severity=3.0,
                          opportunity_score=0.8, sample_evidence=[_evidence(r1), _evidence(r2)])
    bulky = ProblemCluster(id="prob_02", name="Too bulky multi-container design", category="size_fit",
                           description="Multi-container boxes don't fit bags.", affected_products=["p2"],
                           affected_product_count=1, total_complaints=1, avg_severity=2.0,
                           opportunity_score=0.3, sample_evidence=[_evidence(r3)])
    pa = ProblemAnalysis(query="lunch box", market="in", created_at=NOW, total_reviews_analyzed=4,
                         total_complaints_analyzed=3, clusters=[leak, bulky])

    opp = CandidateOpportunity(id="opp_01", title="Silicone seal + 4-point locking lid", problem_id="prob_01",
                               problem_name="Lids leak liquids", category="performance",
                               improvement_type="mechanical_redesign", improvement_concept="Compression gasket.",
                               differentiation_angle="Leakproof.", expected_impact="Fewer returns.",
                               target_price_impact="minor_premium", priority_score=0.9)
    oa = OpportunityAnalysis(query="lunch box", market="in", created_at=NOW, total_problems_evaluated=2,
                             opportunities=[opp])
    fo = FinalOpportunity(rank=1, opportunity_id="opp_01", hypothesis_id="hyp_01", title=opp.title,
                          problem_name=opp.problem_name, category="performance",
                          improvement_type="mechanical_redesign", improvement_concept="Compression gasket.",
                          differentiation_angle="Leakproof.", verdict="CONFIRMED", final_score=0.9,
                          confidence=0.7, recommendation="PROCEED_WITH_CAUTION",
                          competitor_prevalence="2/5", agent_assessment="ok")
    return rs, ri, pa, oa, fo


def test_spec_lines_trace_to_observed_data():
    rs, ri, pa, oa, fo = _fixture()
    spec = build_product_spec(rs, ri, pa, oa, fo, max_must_have=1, use_llm=False)

    known_reviews = {r.id for pr in ri.products for r in pr.reviews}
    known_products = {p.id for p in rs.products}

    # Must-have fixes the leak, cited by the actual leak complaints with verbatim quotes.
    assert spec.must_have[0].statement.startswith("Silicone seal")
    leak_ids = {e.review_id for e in spec.must_have[0].evidence}
    assert leak_ids == {"r1", "r2"}
    assert all(e.quote_verified for e in spec.must_have[0].evidence)

    # Avoid comes from the observed bulky complaint.
    assert any("bulky" in a.statement for a in spec.avoid)
    assert any(e.review_id == "r3" for a in spec.avoid for e in a.evidence)

    # Build uses the common size token across top-rated listings.
    assert "750ml" in spec.build.statement or "900ml" in spec.build.statement
    assert not spec.build.unsupported_claims

    # Price window from observed INR prices, cited by listings inside the band.
    assert spec.target_price.statement.startswith("₹")
    assert spec.target_price.evidence and all(e.kind == "competitor_listing" for e in spec.target_price.evidence)

    # Customer from reviewer self-descriptions (office x2 incl. a target complaint > college x1).
    assert spec.primary_customer.statement.startswith("office workers")
    assert "students" in spec.primary_customer.statement

    # Every evidence ref resolves to collected data.
    for item in spec.all_items():
        assert item.evidence, item.field
        for e in item.evidence:
            assert e.product_id in known_products
            assert e.review_id is None or e.review_id in known_reviews

    md = spec_to_markdown(spec)
    assert "## Evidence" in md and "the dal leaked all over my office bag" in md


def test_llm_lines_with_fake_ids_are_dropped():
    rs, ri, pa, oa, fo = _fixture()
    fake_response = {"items": [
        {"field": "must_have", "statement": "Silicone gasket with 4 locking clips", "evidence_ids": ["r1", "r2"]},
        {"field": "must_have", "statement": "Built-in heating element", "evidence_ids": ["r999"]},
        {"field": "build", "statement": "700ml compact lunch box", "evidence_ids": ["p1"]},
    ]}
    client = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **_: SimpleNamespace(text=json.dumps(fake_response))))

    spec = build_product_spec(rs, ri, pa, oa, fo, max_must_have=1, llm_client=client)

    assert [m.statement for m in spec.must_have] == ["Silicone gasket with 4 locking clips"]
    assert any("heating" in d.statement for d in spec.dropped)
    # "700ml" is not in p1's title (750ml) -> flagged as an unsupported number.
    assert spec.build.unsupported_claims == ["700ml"]
    assert any("700ml" in c for c in spec.caveats)
