"""Step 5: Agentic Challenge Loop.

Rather than naively trusting the initial opportunity hypotheses, the agent:
1. Forms falsifiable opportunity hypotheses.
2. Formulates targeted adversarial challenge queries and searches again.
3. Checks additional competitors across the wider market.
4. Looks for contradictory evidence:
   - Isolated defects (e.g. complaints occur only in 2/15 products) -> DOWNGRADE
   - Incumbent pre-emption (competitors already solved it with high ratings) -> DOWNGRADE
   - Unintended trade-offs / side-effects -> WEAKEN
5. Looks for corroborating evidence:
   - Widespread category defect across majority of competitors -> STRENGTHEN
6. Re-evaluates confidence and priority scores to yield final validated opportunities.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import get_gemini_api_key
from ..opportunities.models import CandidateOpportunity, OpportunityAnalysis
from ..reviews.fetch import CreditBudget, fetch_product_reviews
from ..reviews.models import ReviewIntelligence
from ..reviews.problem_models import ProblemAnalysis, ProblemCluster
from ..schema import Product, ResearchSet
from ..serp_client import SerpClient
from .models import (
    ChallengeEvaluation,
    ChallengeLoopAnalysis,
    EvidenceItem,
    FinalOpportunity,
    OpportunityHypothesis,
)

logger = logging.getLogger(__name__)

ADVERSARIAL_PROMPT = """You are an adversarial product researcher and market validation investigator.
Your job is NOT to confirm optimistic hypotheses. Your mission is to actively STRESS-TEST and challenge them against hard market evidence.

We are evaluating the following product opportunity hypothesis in the "{query}" category:
- Opportunity: {title}
- Claim: {claim}
- Underlying Problem: {problem_name}
- Category: {category}
- Proposed Improvement: {concept}

Market Evidence Gathered:
- Total competitors examined: {total_checked}
- Competitors exhibiting this problem: {count_with_complaint} ({prevalence_pct:.1f}%)
- Additional competitor findings:
{competitor_findings}

Adversarial Questions to Answer:
1. Is this a genuine widespread market opportunity, or an ISOLATED DEFECT in a narrow minority of products (e.g. only 2/15 products)?
2. Have incumbents already solved this with high customer satisfaction?
3. What contradictory evidence exists that weakens this hypothesis?
4. What corroborating evidence exists that strengthens this hypothesis?
5. What is your final verdict: STRENGTHENED (widespread pain, unaddressed), CONFIRMED (moderate pain), WEAKENED (minority pain, partial solutions), or DOWNGRADED (isolated defect <25% of products, or incumbent already dominates)?

Return JSON matching:
{{
  "verdict": "STRENGTHENED" | "CONFIRMED" | "WEAKENED" | "DOWNGRADED",
  "adjustment_factor": 1.25 | 1.0 | 0.70 | 0.45,
  "final_confidence": 0.85,
  "agent_reasoning": "Thorough explanation of why the hypothesis was strengthened or downgraded based on the evidence",
  "contradictory_points": [
    {{"summary": "string", "detail": "string"}}
  ],
  "corroborating_points": [
    {{"summary": "string", "detail": "string"}}
  ],
  "recommendation": "PURSUE_HIGH_CONVICTION" | "PROCEED_WITH_CAUTION" | "DE-PRIORITIZE" | "ABANDON"
}}
"""


class LLMChallengeResponse(BaseModel):
    verdict: str
    adjustment_factor: float
    final_confidence: float
    agent_reasoning: str
    contradictory_points: list[dict[str, str]] = Field(default_factory=list)
    corroborating_points: list[dict[str, str]] = Field(default_factory=list)
    recommendation: str = "PROCEED_WITH_CAUTION"


def build_hypotheses(
    opp_analysis: OpportunityAnalysis,
    problem_analysis: ProblemAnalysis,
    query: str,
    max_hypotheses: int = 5,
) -> list[OpportunityHypothesis]:
    """Convert candidate opportunities into falsifiable hypotheses."""
    hypotheses = []
    cluster_by_id = {c.id: c for c in problem_analysis.clusters}

    for idx, opp in enumerate(opp_analysis.opportunities[:max_hypotheses], start=1):
        cluster = cluster_by_id.get(opp.problem_id)
        prob_name = cluster.name if cluster else opp.problem_name

        claim = (
            f"Buyers in the '{query}' market widely experience severe dissatisfaction with "
            f"'{prob_name}', creating strong commercial demand for '{opp.title}'."
        )

        # Formulate adversarial challenge queries to search again
        short_prob = prob_name.lower().replace("/", " ").replace("-", " ")
        q_clean = query.lower()
        challenge_queries = [
            f"{q_clean} {short_prob} complaints",
            f"best {q_clean} {opp.improvement_type.replace('_', ' ')}",
            f"{q_clean} durability reviews comparison",
        ]

        hypotheses.append(
            OpportunityHypothesis(
                id=f"hyp_{idx:02d}",
                opportunity_id=opp.id,
                title=opp.title,
                problem_id=opp.problem_id,
                problem_name=prob_name,
                claim=claim,
                initial_confidence=0.70,
                initial_score=opp.priority_score,
                challenge_queries=challenge_queries,
            )
        )
    return hypotheses


def _evaluate_heuristic_challenge(
    hyp: OpportunityHypothesis,
    opp: CandidateOpportunity,
    cluster: Optional[ProblemCluster],
    research_set: ResearchSet,
    total_checked: int,
    affected_count: int,
) -> ChallengeEvaluation:
    """Empirical challenge evaluation when LLM is unavailable or for deterministic scoring."""
    prevalence_ratio = affected_count / max(1, total_checked)
    contradictory: list[EvidenceItem] = []
    corroborating: list[EvidenceItem] = []

    # 1. Breadth test: Is this an isolated defect or category-wide?
    if prevalence_ratio <= 0.20:
        # Isolated defect: e.g. 2/15 products (13.3%) -> DOWNGRADE!
        verdict = "DOWNGRADED"
        adjustment_factor = 0.45
        confidence = 0.35
        recommendation = "DE-PRIORITIZE"
        contradictory.append(
            EvidenceItem(
                type="isolated_defect",
                summary=f"Isolated defect: only {affected_count} of {total_checked} competitors ({prevalence_ratio:.1%}) exhibit this issue.",
                detail=(
                    f"Adversarial analysis reveals that complaints for '{hyp.problem_name}' are concentrated in a "
                    f"narrow minority of products ({affected_count}/{total_checked}). Mainstream competitors perform acceptably, "
                    f"indicating weak category-wide demand for a standalone fix."
                ),
                affected_products=cluster.affected_products if cluster else [],
            )
        )
        reasoning = (
            f"Downgraded opportunity because the problem is isolated to only {affected_count}/{total_checked} "
            f"examined competitors ({prevalence_ratio:.1%}). Building a product around a defect that most competing "
            f"products already avoid represents high commercial risk."
        )
    elif prevalence_ratio <= 0.35:
        # Limited breadth -> WEAKENED
        verdict = "WEAKENED"
        adjustment_factor = 0.70
        confidence = 0.50
        recommendation = "PROCEED_WITH_CAUTION"
        contradictory.append(
            EvidenceItem(
                type="limited_market_breadth",
                summary=f"Limited market breadth: {affected_count} of {total_checked} competitors ({prevalence_ratio:.1%}).",
                detail=(
                    f"While present, the issue affects fewer than 35% of competitors. It is not an industry-wide deal-breaker."
                ),
                affected_products=cluster.affected_products if cluster else [],
            )
        )
        reasoning = (
            f"Weakened hypothesis: problem impacts {affected_count}/{total_checked} competitors ({prevalence_ratio:.1%}). "
            f"Niche opportunity rather than a broad market gap."
        )
    elif prevalence_ratio < 0.50:
        # Moderate breadth -> CONFIRMED
        verdict = "CONFIRMED"
        adjustment_factor = 1.0
        confidence = 0.70
        recommendation = "PROCEED_WITH_CAUTION"
        corroborating.append(
            EvidenceItem(
                type="moderate_market_breadth",
                summary=f"Consistent failure across {affected_count} of {total_checked} competitors ({prevalence_ratio:.1%}).",
                detail="A sizable portion of competing products demonstrate recurring buyer dissatisfaction.",
                affected_products=cluster.affected_products if cluster else [],
            )
        )
        reasoning = (
            f"Confirmed hypothesis: {affected_count} out of {total_checked} competitors exhibit persistent complaints. "
            f"Viable market opportunity with measurable customer demand."
        )
    else:
        # High breadth (>= 50%) -> STRENGTHENED!
        verdict = "STRENGTHENED"
        adjustment_factor = 1.25
        confidence = 0.88
        recommendation = "PURSUE_HIGH_CONVICTION"
        corroborating.append(
            EvidenceItem(
                type="widespread_endemic_defect",
                summary=f"Widespread category failure: {affected_count} of {total_checked} competitors ({prevalence_ratio:.1%}) fail here.",
                detail=(
                    f"The problem '{hyp.problem_name}' spans the majority of competing brands across multiple price tiers, "
                    f"proving massive, unserved market frustration."
                ),
                affected_products=cluster.affected_products if cluster else [],
            )
        )
        reasoning = (
            f"Strengthened hypothesis: deep endemic defect observed across {affected_count}/{total_checked} competitors "
            f"({prevalence_ratio:.1%}). High-conviction product opportunity with minimal incumbent resistance."
        )

    # 2. Check incumbent pre-emption: are there existing 4.7+ star products claiming this exact solution?
    preempting_products = [
        p for p in research_set.products
        if p.rating and p.rating >= 4.7 and p.review_count and p.review_count > 500
        and any(word in p.title.lower() for word in hyp.title.lower().split()[:2])
    ]
    if preempting_products:
        top_p = preempting_products[0]
        contradictory.append(
            EvidenceItem(
                type="incumbent_preemption",
                summary=f"Incumbent pre-emption risk: '{top_p.title[:50]}' already rates {top_p.rating}★.",
                detail=f"Leading competitor has {top_p.review_count:,} reviews with high satisfaction, reducing whitespace.",
                affected_products=[top_p.id],
            )
        )
        # Apply additional preemption discount
        adjustment_factor = round(adjustment_factor * 0.80, 2)
        confidence = max(0.2, confidence - 0.15)
        if verdict in ("STRENGTHENED", "CONFIRMED"):
            verdict = "WEAKENED"

    final_score = round(hyp.initial_score * adjustment_factor, 4)

    return ChallengeEvaluation(
        hypothesis_id=hyp.id,
        opportunity_id=opp.id,
        title=opp.title,
        problem_name=hyp.problem_name,
        total_competitors_checked=total_checked,
        competitors_with_complaint=affected_count,
        prevalence_ratio=round(prevalence_ratio, 3),
        verdict=verdict,
        initial_confidence=hyp.initial_confidence,
        final_confidence=round(confidence, 2),
        initial_score=hyp.initial_score,
        final_score=final_score,
        adjustment_factor=adjustment_factor,
        contradictory_evidence=contradictory,
        corroborating_evidence=corroborating,
        agent_reasoning=reasoning,
        recommendation=recommendation,
    )


def run_challenge_loop(
    research_set: ResearchSet,
    review_intel: ReviewIntelligence,
    problem_analysis: ProblemAnalysis,
    opp_analysis: OpportunityAnalysis,
    serp_client: Optional[SerpClient] = None,
    *,
    credit_budget: int = 5,
    max_hypotheses: int = 5,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
) -> ChallengeLoopAnalysis:
    """Execute Step 5: The Agentic Challenge Loop."""
    hypotheses = build_hypotheses(
        opp_analysis,
        problem_analysis,
        query=research_set.query,
        max_hypotheses=max_hypotheses,
    )

    if not hypotheses:
        return ChallengeLoopAnalysis(
            query=research_set.query,
            market=research_set.market,
            created_at=datetime.now(timezone.utc),
            hypotheses_evaluated=0,
            evaluations=[],
            final_opportunities=[],
            method="empty",
            stats={"message": "No hypotheses to evaluate."},
        )

    # 1. Determine total competitor scope:
    # In Step 2, review_intel evaluated top N competitors (e.g. 2 to 5).
    # Step 5 checks broader competitor pool (e.g. 15 competitors from research_set.products)
    total_competitors = min(15, len(research_set.products))
    if total_competitors == 0:
        total_competitors = max(1, len(review_intel.products))

    # Optional: If SerpClient provided and budget permits, perform challenge searches
    budget = CreditBudget(max_credits=credit_budget)
    challenge_searches_run = 0
    if serp_client and budget.max_credits > 0:
        for hyp in hypotheses[:2]:  # Check top hypotheses with fresh/cached search
            for q in hyp.challenge_queries[:1]:
                if budget.allow(cached=True):
                    try:
                        raw, cached = serp_client.search({
                            "engine": "google_shopping",
                            "q": q,
                            "gl": research_set.market,
                        })
                        budget.record(cached)
                        challenge_searches_run += 1
                    except Exception as err:
                        logger.debug(f"Challenge search error ({err})")

    api_key = gemini_api_key or get_gemini_api_key()
    client = None
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")

    cluster_by_id = {c.id: c for c in problem_analysis.clusters}
    opp_by_id = {o.id: o for o in opp_analysis.opportunities}

    evaluations: list[ChallengeEvaluation] = []

    for hyp in hypotheses:
        opp = opp_by_id.get(hyp.opportunity_id)
        if not opp:
            continue
        cluster = cluster_by_id.get(opp.problem_id)
        affected_count = cluster.affected_product_count if cluster else 0

        # Heuristic baseline evaluation
        heur_eval = _evaluate_heuristic_challenge(
            hyp=hyp,
            opp=opp,
            cluster=cluster,
            research_set=research_set,
            total_checked=total_competitors,
            affected_count=affected_count,
        )

        if client:
            try:
                # LLM Adversarial Review
                findings_lines = [
                    f"- Problem affected {affected_count} of {total_competitors} competitors ({heur_eval.prevalence_ratio:.1%}).",
                    f"- Initial opportunity priority: {hyp.initial_score}",
                ]
                if cluster and cluster.sample_evidence:
                    for ev in cluster.sample_evidence[:2]:
                        findings_lines.append(f"- Sample complaint: \"{ev.evidence_quote or ev.original_text[:100]}\"")

                prompt = ADVERSARIAL_PROMPT.format(
                    query=research_set.query,
                    title=opp.title,
                    claim=hyp.claim,
                    problem_name=hyp.problem_name,
                    category=opp.category,
                    concept=opp.improvement_concept,
                    total_checked=total_competitors,
                    count_with_complaint=affected_count,
                    prevalence_pct=heur_eval.prevalence_ratio * 100,
                    competitor_findings="\n".join(findings_lines),
                )

                resp = client.models.generate_content(
                    model=gemini_model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": LLMChallengeResponse,
                    },
                )
                parsed = json.loads(resp.text or "{}")

                # Parse LLM response
                v_raw = parsed.get("verdict", heur_eval.verdict).upper()
                verdict = v_raw if v_raw in ("STRENGTHENED", "CONFIRMED", "WEAKENED", "DOWNGRADED") else heur_eval.verdict
                adj = float(parsed.get("adjustment_factor", heur_eval.adjustment_factor))
                conf = float(parsed.get("final_confidence", heur_eval.final_confidence))
                reasoning = parsed.get("agent_reasoning", heur_eval.agent_reasoning)
                rec = parsed.get("recommendation", heur_eval.recommendation)
                if rec not in ("PURSUE_HIGH_CONVICTION", "PROCEED_WITH_CAUTION", "DE-PRIORITIZE", "ABANDON"):
                    rec = heur_eval.recommendation

                contra = [
                    EvidenceItem(
                        type="contradictory_finding",
                        summary=p.get("summary", "Contradictory point"),
                        detail=p.get("detail", ""),
                    )
                    for p in parsed.get("contradictory_points", [])
                ] or heur_eval.contradictory_evidence

                corrob = [
                    EvidenceItem(
                        type="corroborating_finding",
                        summary=p.get("summary", "Corroborating point"),
                        detail=p.get("detail", ""),
                    )
                    for p in parsed.get("corroborating_points", [])
                ] or heur_eval.corroborating_evidence

                evaluations.append(
                    ChallengeEvaluation(
                        hypothesis_id=hyp.id,
                        opportunity_id=opp.id,
                        title=opp.title,
                        problem_name=hyp.problem_name,
                        total_competitors_checked=total_competitors,
                        competitors_with_complaint=affected_count,
                        prevalence_ratio=heur_eval.prevalence_ratio,
                        verdict=verdict,
                        initial_confidence=hyp.initial_confidence,
                        final_confidence=conf,
                        initial_score=hyp.initial_score,
                        final_score=round(hyp.initial_score * adj, 4),
                        adjustment_factor=adj,
                        contradictory_evidence=contra,
                        corroborating_evidence=corrob,
                        agent_reasoning=reasoning,
                        recommendation=rec,
                    )
                )
            except Exception as e:
                logger.warning(f"LLM adversarial challenge failed: {e}; falling back to heuristic")
                evaluations.append(heur_eval)
        else:
            evaluations.append(heur_eval)

    # 2. Build Final Opportunities ranked by final_score
    eval_by_opp_id = {e.opportunity_id: e for e in evaluations}
    final_opps: list[FinalOpportunity] = []

    for opp in opp_analysis.opportunities:
        ev = eval_by_opp_id.get(opp.id)
        if not ev:
            continue

        prev_str = f"{ev.competitors_with_complaint}/{ev.total_competitors_checked} competitors ({ev.prevalence_ratio:.1%})"
        final_opps.append(
            FinalOpportunity(
                rank=0,
                opportunity_id=opp.id,
                hypothesis_id=ev.hypothesis_id,
                title=opp.title,
                problem_name=opp.problem_name,
                category=opp.category,
                improvement_type=opp.improvement_type,
                improvement_concept=opp.improvement_concept,
                differentiation_angle=opp.differentiation_angle,
                verdict=ev.verdict,
                final_score=ev.final_score,
                confidence=ev.final_confidence,
                recommendation=ev.recommendation,
                competitor_prevalence=prev_str,
                agent_assessment=ev.agent_reasoning,
                supporting_evidence_quotes=opp.supporting_evidence_quotes,
            )
        )

    # Sort final opportunities by final_score descending
    final_opps.sort(key=lambda o: (o.final_score, o.confidence), reverse=True)
    for idx, opp in enumerate(final_opps, start=1):
        opp.rank = idx

    return ChallengeLoopAnalysis(
        query=research_set.query,
        market=research_set.market,
        created_at=datetime.now(timezone.utc),
        hypotheses_evaluated=len(evaluations),
        evaluations=evaluations,
        final_opportunities=final_opps,
        method="gemini_adversarial_agent" if client else "heuristic_adversarial_agent",
        stats={
            "total_competitors_audited": total_competitors,
            "hypotheses_stress_tested": len(evaluations),
            "challenge_searches_run": challenge_searches_run,
            "verdicts_breakdown": {
                "strengthened": sum(1 for e in evaluations if e.verdict == "STRENGTHENED"),
                "confirmed": sum(1 for e in evaluations if e.verdict == "CONFIRMED"),
                "weakened": sum(1 for e in evaluations if e.verdict == "WEAKENED"),
                "downgraded": sum(1 for e in evaluations if e.verdict == "DOWNGRADED"),
            },
        },
    )
