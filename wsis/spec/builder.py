"""Step 7: turn the validated opportunity into an actionable, traceable product spec.

Output shape (per the brief):
    Build:            what to make (form factor / spec class)
    Must have:        features that fix observed complaints
    Avoid:            failure modes observed in competitors
    Target price:     window derived from observed competitor prices
    Primary customer: segment derived from who reviewers say they are

Traceability is enforced in code:
- Every evidence ref is built from collected data (review IDs / product IDs from
  this run), never from LLM text. Quotes are verbatim substrings of reviews.
- An LLM (optional) may only phrase lines and must cite IDs; unknown IDs are
  discarded and lines left without evidence are moved to `dropped`.
- Numeric claims in a statement (e.g. "700ml") that don't appear in any cited
  evidence are flagged in `unsupported_claims`.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field

from ..assessment.builder import format_price
from ..assessment.models import CompetitorAssessment
from ..challenge.models import FinalOpportunity
from ..config import get_gemini_api_key
from ..normalize.common import query_tokens
from ..opportunities.models import OpportunityAnalysis
from ..reviews.models import Review, ReviewIntelligence
from ..reviews.problem_models import ProblemAnalysis, ProblemCluster
from ..schema import Product, ResearchSet
from .models import DroppedItem, EvidenceRef, ProductSpec, SpecItem

logger = logging.getLogger(__name__)

MAX_REFS_PER_ITEM = 5

# Spec tokens like "6mm", "1/2-inch", "750 ml", "1.2L", "32 oz".
UNIT_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?(?:/\d+)?)\s*-?\s*(mm|cm|ml|ltr|litre|liter|l|oz|inches|inch|lbs|lb|kg)\b",
    re.IGNORECASE,
)
_UNIT_NORMAL = {"inches": "inch", "ltr": "L", "litre": "L", "liter": "L", "l": "L", "lbs": "lb"}

# Who reviewers say they are / where they use it. Keyword -> segment label.
SEGMENTS: dict[str, list[str]] = {
    "office workers / commuters": ["office", "work", "commute", "commuting", "desk"],
    "students": ["college", "school", "student", "students", "campus", "dorm", "university"],
    "parents buying for kids": ["kid", "kids", "child", "children", "son", "daughter", "toddler"],
    "home-workout users": ["at home", "home workout", "living room", "apartment"],
    "beginners": ["beginner", "beginners", "new to", "first time"],
    "high-sweat / hot-class users": ["hot yoga", "sweat", "sweaty", "bikram", "sweating"],
    "travelers": ["travel", "traveling", "trip", "trips", "portable"],
    "people with joint pain / older adults": ["knee", "knees", "joint", "joints", "back pain", "arthritis", "senior"],
    "gym-goers": ["gym"],
    "pilates practitioners": ["pilates"],
}


# --------------------------------------------------------------------------- helpers

def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _best_sentence(text: str, keywords: Iterable[str], max_len: int = 220) -> str:
    """Most keyword-relevant sentence of `text` (always a verbatim substring)."""
    kws = [k.lower() for k in keywords if len(k) > 2]
    best, best_score = "", -1
    for s in _sentences(text):
        low = s.lower()
        score = sum(1 for k in kws if k in low)
        if score > best_score:
            best, best_score = s, score
    best = best or text
    return best[:max_len]


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", text.lower()) if len(t) > 3}


def _ref_from_review(r: Review, kind: str, keywords: Iterable[str] = ()) -> EvidenceRef:
    c = r.classification
    if c and c.evidence_verified and c.evidence_quote:
        quote = c.evidence_quote
    else:
        quote = _best_sentence(r.original_text, keywords)
    return EvidenceRef(
        kind=kind,  # type: ignore[arg-type]
        review_id=r.id,
        product_id=r.product_id,
        product_title=r.product_title,
        quote=quote,
        quote_verified=bool(quote) and quote in r.original_text,
        rating=r.rating,
        url=r.citation.review_url or r.url,
        serpapi_json_url=r.citation.serpapi_json_url,
    )


def _ref_from_product(p: Product, currency: str) -> EvidenceRef:
    facts = [f"price={format_price(p.price or p.price_min, currency)}"]
    if p.rating:
        facts.append(f"rating={p.rating}")
    if p.review_count:
        facts.append(f"reviews={p.review_count:,}")
    serp = p.listings[0].citation.serpapi_json_url if p.listings else None
    return EvidenceRef(
        kind="competitor_listing",
        product_id=p.id,
        product_title=p.title,
        data_point=", ".join(facts),
        rating=p.rating,
        url=p.url,
        serpapi_json_url=serp,
    )


def _finalize(item: SpecItem) -> SpecItem:
    """Dedupe/cap refs, compute support counts, flag unsupported numeric claims."""
    seen: set[str] = set()
    refs: list[EvidenceRef] = []
    for e in item.evidence:
        key = e.review_id or f"product:{e.product_id}"
        if key not in seen:
            seen.add(key)
            refs.append(e)
    item.support_reviews = len({e.review_id for e in refs if e.review_id})
    item.support_products = len({e.product_id for e in refs})
    item.evidence = refs[:MAX_REFS_PER_ITEM]

    corpus = " ".join(
        " ".join(filter(None, [e.quote, e.data_point, e.product_title])) for e in refs
    ).lower().replace(" ", "")
    item.unsupported_claims = [
        m.group(0) for m in UNIT_RE.finditer(item.statement)
        if m.group(0).lower().replace(" ", "").replace("-", "") not in corpus.replace("-", "")
    ]
    return item


def _price(p: Product) -> Optional[float]:
    return p.price if p.price is not None else p.price_min


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = q * (len(sorted_vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _round_price(v: float, currency: str) -> float:
    if currency.upper() in ("INR", "JPY"):
        return float(int(round(v / 50.0) * 50) - 1 if v > 100 else int(round(v)))
    return float(int(round(v)) - 0.01) if v >= 5 else round(v, 2)


# --------------------------------------------------------------------------- spec lines

def _cluster_reviews(cluster: ProblemCluster, review_index: dict[str, Review]) -> list[Review]:
    out = []
    for ev in cluster.sample_evidence:
        r = review_index.get(ev.review_id)
        if r:
            out.append(r)
    return out


def _cluster_item(
    field: str,
    statement: str,
    rationale: str,
    cluster: ProblemCluster,
    review_index: dict[str, Review],
) -> SpecItem:
    kws = _tokens(cluster.name) | _tokens(cluster.description)
    refs = [_ref_from_review(r, "review_complaint", kws) for r in _cluster_reviews(cluster, review_index)]
    item = SpecItem(field=field, statement=statement, rationale=rationale, evidence=refs)  # type: ignore[arg-type]
    item = _finalize(item)
    # Count the cluster's full complaint volume, not just the sampled evidence.
    item.support_reviews = max(item.support_reviews, cluster.total_complaints)
    item.support_products = max(item.support_products, cluster.affected_product_count)
    return item


def _build_item(
    query: str,
    final_opp: FinalOpportunity,
    research_set: ResearchSet,
) -> SpecItem:
    """Form factor / spec class taken from the most common spec among top-rated competitors."""
    products = research_set.products
    rated = sorted([p.rating for p in products if p.rating], reverse=True)
    median = rated[len(rated) // 2] if rated else 0.0
    reference = [p for p in products if (p.rating or 0) >= median] or products

    token_count: Counter[str] = Counter()
    token_products: dict[str, list[Product]] = {}
    for p in reference:
        seen: set[str] = set()
        for m in UNIT_RE.finditer(p.title):
            unit = _UNIT_NORMAL.get(m.group(2).lower(), m.group(2).lower())
            tok = f"{m.group(1)}{'' if unit in ('mm', 'cm', 'ml', 'L', 'oz') else ' '}{unit}"
            if tok not in seen:
                seen.add(tok)
                token_count[tok] += 1
                token_products.setdefault(tok, []).append(p)

    common = [t for t, n in token_count.most_common(3) if n >= 2][:2]
    if common:
        spec_str = " / ".join(common)
        statement = f"{query} in the {spec_str} class, built around: {final_opp.title}"
        rationale = (
            f"{spec_str} is the most common spec among {len(reference)} competitors rated ≥{median:.1f}★ "
            f"({', '.join(f'{t}: {token_count[t]} listings' for t in common)})."
        )
        refs = [_ref_from_product(p, research_set.currency) for t in common for p in token_products[t]]
    else:
        statement = f"{query} built around: {final_opp.title}"
        rationale = "No consistent size/spec token found in top-rated competitor titles."
        refs = [_ref_from_product(p, research_set.currency) for p in reference[:MAX_REFS_PER_ITEM]]
    return _finalize(SpecItem(field="build", statement=statement, rationale=rationale, evidence=refs))


def _price_item(final_opp_price_impact: str, research_set: ResearchSet) -> SpecItem:
    """Price window from the observed competitor price distribution."""
    cur = research_set.currency
    priced = sorted([p for p in research_set.products if _price(p) is not None], key=lambda p: _price(p))  # type: ignore[arg-type,return-value]
    vals = [_price(p) for p in priced]  # type: ignore[misc]
    if len(vals) < 3:
        return SpecItem(
            field="target_price",
            statement="Insufficient price data",
            rationale=f"Only {len(vals)} priced competitors observed.",
        )
    band = {
        "cost_neutral": (0.40, 0.60),
        "minor_premium": (0.50, 0.75),
        "premium_tier": (0.70, 0.90),
    }.get(final_opp_price_impact, (0.50, 0.75))
    lo = _round_price(_percentile(vals, band[0]), cur)
    hi = _round_price(_percentile(vals, band[1]), cur)
    in_band = [p for p in priced if lo * 0.9 <= _price(p) <= hi * 1.1]  # type: ignore[operator]
    in_band.sort(key=lambda p: -(p.rating or 0))
    return _finalize(SpecItem(
        field="target_price",
        statement=f"{format_price(lo, cur)}–{format_price(hi, cur)}",
        rationale=(
            f"{int(band[0]*100)}th–{int(band[1]*100)}th percentile of {len(vals)} observed competitor prices "
            f"(range {format_price(vals[0], cur)}–{format_price(vals[-1], cur)}, median "
            f"{format_price(_percentile(vals, 0.5), cur)}); band chosen for '{final_opp_price_impact}' positioning."
        ),
        evidence=[_ref_from_product(p, cur) for p in in_band],
    ))


def _customer_item(
    query: str,
    review_intel: ReviewIntelligence,
    target_reviews: set[str],
) -> SpecItem:
    """Segment = who reviewers say they are / how they use it. Mentions in reviews that
    complain about the target problem count double."""
    q_toks = set(query_tokens(query))
    seg_hits: dict[str, list[tuple[Review, str]]] = {}
    for pr in review_intel.products:
        for r in pr.reviews:
            low = r.original_text.lower()
            for seg, kws in SEGMENTS.items():
                if any(k in q_toks for k in kws):
                    continue  # "yoga" in yoga-mat reviews says nothing about the buyer
                for kw in kws:
                    if re.search(rf"\b{re.escape(kw)}\b", low):
                        seg_hits.setdefault(seg, []).append((r, kw))
                        break

    if not seg_hits:
        return SpecItem(
            field="primary_customer",
            statement="Insufficient evidence — no reviewer self-descriptions found",
            rationale="Collect more reviews before committing to a target segment.",
        )

    def weight(seg: str) -> float:
        return sum(2.0 if r.id in target_reviews else 1.0 for r, _ in seg_hits[seg])

    ranked = sorted(seg_hits, key=weight, reverse=True)
    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    n_top = len({r.id for r, _ in seg_hits[top]})
    statement = top if not second else f"{top} (secondary: {second})"
    refs = [_ref_from_review(r, "review_mention", [kw]) for r, kw in seg_hits[top]]
    if second:
        refs += [_ref_from_review(r, "review_mention", [kw]) for r, kw in seg_hits[second][:2]]
    return _finalize(SpecItem(
        field="primary_customer",
        statement=statement,
        rationale=(
            f"'{top}' self-identified/use-context in {n_top} review(s)"
            + (f"; '{second}' in {len({r.id for r, _ in seg_hits[second]})}" if second else "")
            + ". Mentions inside target-problem complaints weighted 2x."
        ),
        evidence=refs,
    ))


def _avoid_from_assessment(
    assessment: Optional[CompetitorAssessment],
    review_intel: ReviewIntelligence,
    covered: set[str],
) -> tuple[list[SpecItem], list[DroppedItem]]:
    """Competitor failure labels are only kept when backed by that competitor's complaint reviews."""
    items: list[SpecItem] = []
    dropped: list[DroppedItem] = []
    if not assessment:
        return items, dropped
    reviews_by_pid = {pr.product_id: pr.reviews for pr in review_intel.products}
    by_label: dict[str, list[Any]] = {}
    for comp in assessment.competitors:
        by_label.setdefault(comp.problem.strip().lower(), []).append(comp)

    for label, comps in by_label.items():
        if not label or label in covered or any(label in c or c in label for c in covered):
            continue
        refs: list[EvidenceRef] = []
        kws = _tokens(label) or {label}
        for comp in comps:
            for r in reviews_by_pid.get(comp.id, []):
                cls = r.classification
                if not (cls and cls.is_complaint):
                    continue
                blob = " ".join(cls.issues).lower() + " " + r.original_text.lower()
                if any(k in blob for k in kws):
                    refs.append(_ref_from_review(r, "review_complaint", kws))
        names = ", ".join(c.name for c in comps)
        if refs:
            items.append(_finalize(SpecItem(
                field="avoid",
                statement=f"{label} (seen in: {names})",
                rationale="Competitor weakness confirmed by that competitor's own complaint reviews.",
                evidence=refs,
            )))
        else:
            dropped.append(DroppedItem(
                field="avoid",
                statement=f"{label} (seen in: {names})",
                reason="Step 6 label has no matching complaint review for that competitor.",
            ))
    return items, dropped


# --------------------------------------------------------------------------- LLM phrasing (optional)

LLM_PROMPT = """You are writing a product spec for a seller entering the "{query}" market.
Opportunity: {opp_title} — {concept}

Draft spec (every line already has evidence):
{draft}

Evidence you may cite (ID -> text):
{evidence}

Rewrite each line into a concrete, buildable instruction (dimensions, materials, mechanisms) in the
style: "Build: 700–900ml compact lunch box", "Must have: improved silicone seal + locking mechanism".
Rules:
- Every line MUST list evidence_ids chosen ONLY from the IDs above. Lines you cannot support, omit.
- Do not invent numbers that are not present in the cited evidence.
- Keep "field" exactly as given (build, must_have, avoid, primary_customer).

Return JSON: {{"items": [{{"field": "...", "statement": "...", "rationale": "...", "evidence_ids": ["..."]}}]}}
"""


class _LLMItem(BaseModel):
    field: str
    statement: str
    rationale: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class _LLMResponse(BaseModel):
    items: list[_LLMItem]


def _llm_rephrase(
    client: Any,
    model: str,
    spec: ProductSpec,
    review_index: dict[str, Review],
    product_index: dict[str, Product],
    final_opp: FinalOpportunity,
) -> ProductSpec:
    draft_items = [spec.build, *spec.must_have, *spec.avoid, spec.primary_customer]
    draft = "\n".join(
        f"- {it.field}: {it.statement} | evidence_ids: "
        + ", ".join(e.review_id or e.product_id for e in it.evidence)
        for it in draft_items if it.evidence
    )
    ev_lines = {}
    for it in draft_items:
        for e in it.evidence:
            key = e.review_id or e.product_id
            ev_lines[key] = (e.quote or "") + (f" [{e.data_point}] {e.product_title[:80]}" if e.data_point else "")
    prompt = LLM_PROMPT.format(
        query=spec.query,
        opp_title=final_opp.title,
        concept=final_opp.improvement_concept,
        draft=draft,
        evidence="\n".join(f"{k}: {v}" for k, v in ev_lines.items()),
    )
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": _LLMResponse},
    )
    parsed = json.loads(resp.text or "{}")

    new: dict[str, list[SpecItem]] = {"build": [], "must_have": [], "avoid": [], "primary_customer": []}
    for raw in parsed.get("items", []):
        field = raw.get("field")
        if field not in new or not raw.get("statement"):
            continue
        refs: list[EvidenceRef] = []
        for eid in raw.get("evidence_ids", []):
            if eid in review_index:
                kind = "review_mention" if field == "primary_customer" else "review_complaint"
                refs.append(_ref_from_review(review_index[eid], kind, _tokens(raw["statement"])))
            elif eid in product_index:
                refs.append(_ref_from_product(product_index[eid], spec.currency))
        if not refs:
            spec.dropped.append(DroppedItem(field=field, statement=raw["statement"],
                                            reason="LLM line cited no IDs that exist in collected data."))
            continue
        new[field].append(_finalize(SpecItem(field=field, statement=raw["statement"],
                                             rationale=raw.get("rationale", ""), evidence=refs)))

    # Only replace a section if the LLM produced a traceable version of it.
    if new["build"]:
        spec.build = new["build"][0]
    if new["must_have"]:
        spec.must_have = new["must_have"]
    if new["avoid"]:
        spec.avoid = new["avoid"]
    if new["primary_customer"]:
        spec.primary_customer = new["primary_customer"][0]
    return spec


# --------------------------------------------------------------------------- entry point

def build_product_spec(
    research_set: ResearchSet,
    review_intel: ReviewIntelligence,
    problem_analysis: ProblemAnalysis,
    opp_analysis: OpportunityAnalysis,
    final_opportunity: FinalOpportunity,
    assessment: Optional[CompetitorAssessment] = None,
    *,
    max_must_have: int = 3,
    use_llm: bool = True,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
    llm_client: Any = None,
) -> ProductSpec:
    query = research_set.query
    review_index = {r.id: r for pr in review_intel.products for r in pr.reviews}
    product_index = {p.id: p for p in research_set.products}
    opp_by_problem = {o.problem_id: o for o in opp_analysis.opportunities}
    target_opp = next((o for o in opp_analysis.opportunities if o.id == final_opportunity.opportunity_id), None)
    target_pid = target_opp.problem_id if target_opp else None

    clusters = sorted(problem_analysis.clusters, key=lambda c: c.opportunity_score, reverse=True)
    if target_pid:
        clusters.sort(key=lambda c: c.id != target_pid)  # stable: target first

    must_have: list[SpecItem] = []
    avoid: list[SpecItem] = []
    dropped: list[DroppedItem] = []
    covered: set[str] = set()

    for i, cl in enumerate(clusters):
        opp = opp_by_problem.get(cl.id)
        if i < max_must_have:
            stmt = f"{opp.title} — fixes \"{cl.name}\"" if opp else f"Solve \"{cl.name}\""
            item = _cluster_item("must_have", stmt, opp.improvement_concept if opp else cl.description, cl, review_index)
        else:
            stmt = f"{cl.name.lower()} ({cl.total_complaints} complaint(s) across {cl.affected_product_count} product(s))"
            item = _cluster_item("avoid", stmt, cl.description, cl, review_index)
        covered |= {cl.name.lower()} | {w for w in _tokens(cl.name)}
        if item.evidence:
            (must_have if item.field == "must_have" else avoid).append(item)
        else:
            dropped.append(DroppedItem(field=item.field, statement=item.statement,
                                       reason="Problem cluster has no resolvable review evidence."))

    a_items, a_dropped = _avoid_from_assessment(assessment, review_intel, covered)
    avoid += a_items
    dropped += a_dropped

    target_reviews = {ev.review_id for c in clusters[:1] for ev in c.sample_evidence}
    price_impact = target_opp.target_price_impact if target_opp else "minor_premium"

    reviewed_products = sum(1 for pr in review_intel.products if pr.reviews)
    total_reviews = len(review_index)
    caveats = [
        f"Evidence base: {total_reviews} reviews from {reviewed_products} of {len(research_set.products)} "
        f"competitors; complaint counts are lower bounds for unreviewed competitors.",
    ]
    if final_opportunity.verdict in ("WEAKENED", "DOWNGRADED"):
        caveats.append(
            f"Step 5 verdict for this opportunity is {final_opportunity.verdict} "
            f"(confidence {final_opportunity.confidence:.0%}); validate demand before tooling."
        )

    spec = ProductSpec(
        query=query,
        market=research_set.market,
        currency=research_set.currency,
        opportunity_id=final_opportunity.opportunity_id,
        opportunity_title=final_opportunity.title,
        verdict=final_opportunity.verdict,
        confidence=final_opportunity.confidence,
        build=_build_item(query, final_opportunity, research_set),
        must_have=must_have,
        avoid=avoid,
        target_price=_price_item(price_impact, research_set),
        primary_customer=_customer_item(query, review_intel, target_reviews),
        dropped=dropped,
        caveats=caveats,
        created_at=datetime.now(timezone.utc),
        method="heuristic",
    )

    client = llm_client
    if use_llm and client is None:
        key = gemini_api_key or get_gemini_api_key()
        if key:
            try:
                from google import genai
                client = genai.Client(api_key=key)
            except Exception as err:  # pragma: no cover
                logger.warning(f"Gemini init failed: {err}")
    if use_llm and client is not None:
        try:
            spec = _llm_rephrase(client, gemini_model, spec, review_index, product_index, final_opportunity)
            spec.method = "gemini_llm+traceability_check"
        except Exception as err:
            logger.warning(f"LLM spec phrasing failed ({err}); keeping heuristic spec")

    for item in spec.all_items():
        if not item.evidence:
            spec.caveats.append(f"'{item.field}' has no supporting evidence: {item.statement}")
        if item.unsupported_claims:
            spec.caveats.append(f"'{item.field}' contains numbers not found in cited evidence: {item.unsupported_claims}")

    items = spec.all_items()
    spec.stats = {
        "lines": len(items),
        "traceable_lines": sum(1 for it in items if it.evidence),
        "dropped_lines": len(spec.dropped),
        "evidence_refs": sum(len(it.evidence) for it in items),
        "verified_quotes": sum(1 for it in items for e in it.evidence if e.quote_verified),
    }
    return spec


def spec_to_markdown(spec: ProductSpec) -> str:
    """Human-readable spec with numbered citations back to reviews/listings."""
    lines = [f"# Product spec: {spec.query} ({spec.market.upper()})", "",
             f"Opportunity: **{spec.opportunity_title}** — verdict {spec.verdict}, confidence {spec.confidence:.0%}", ""]
    refs: list[EvidenceRef] = []

    def cite(item: SpecItem) -> str:
        nums = []
        for e in item.evidence:
            refs.append(e)
            nums.append(f"[{len(refs)}]")
        return " " + "".join(nums) if nums else " _(no evidence)_"

    lines.append(f"- **Build:** {spec.build.statement}{cite(spec.build)}")
    for it in spec.must_have:
        lines.append(f"- **Must have:** {it.statement}{cite(it)}")
    for it in spec.avoid:
        lines.append(f"- **Avoid:** {it.statement}{cite(it)}")
    lines.append(f"- **Target price:** {spec.target_price.statement}{cite(spec.target_price)}")
    lines.append(f"- **Primary customer:** {spec.primary_customer.statement}{cite(spec.primary_customer)}")
    if spec.caveats:
        lines += ["", "## Caveats", *[f"- {c}" for c in spec.caveats]]
    if spec.dropped:
        lines += ["", "## Dropped (no evidence)", *[f"- {d.field}: {d.statement} — {d.reason}" for d in spec.dropped]]
    lines += ["", "## Evidence"]
    for i, e in enumerate(refs, 1):
        body = f"\"{e.quote}\"" if e.quote else e.data_point
        who = f"review {e.review_id}" if e.review_id else "listing"
        lines.append(f"{i}. {who} — {e.product_title[:70]}: {body} ({e.url})")
    return "\n".join(lines) + "\n"
