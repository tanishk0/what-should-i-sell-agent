"""Generate candidate product opportunities from recurring buyer problems (Step 4).

For each major problem identified in Step 3, queries the model:
'What product improvement could directly solve this problem?'
and derives actionable product improvements, differentiation angles, and feasibility scores.
Includes an intelligent offline heuristic generator fallback.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import get_gemini_api_key
from ..reviews.problem_models import ProblemAnalysis, ProblemCluster
from .models import CandidateOpportunity, OpportunityAnalysis

logger = logging.getLogger(__name__)

OPPORTUNITY_PROMPT = """You are an elite consumer product developer and industrial designer.
We analyzed customer reviews across competing products in the "{query}" market.
We uncovered the following major recurring problems and buyer frustrations across competing products.

Your mission is: Convert these problems into high-potential, actionable candidate product opportunities.

For each major problem, answer the central question:
"What product improvement could directly solve this problem?"

Major Problems Identified:
{problems_payload}

Instructions:
1. For each problem, invent a practical, highly differentiated, and commercially viable product improvement that directly eliminates the root cause of the complaint.
2. Formulate:
   - title: A concise, benefit-driven product improvement title (e.g., "Dual-Density Anti-Slip Grip Layer with Laser Alignment").
   - problem_id: The exact ID of the problem being solved (e.g., "prob_01").
   - problem_name: The exact name of the problem cluster.
   - category: Category of improvement (e.g. "materials_safety", "performance", "durability", "comfort_ergonomics", "design_aesthetics", etc.).
   - improvement_type: One of "material_upgrade", "mechanical_redesign", "feature_addition", "manufacturing_process", "ergonomic_enhancement", "bundle_accessory", "packaging_redesign".
   - improvement_concept: Thorough 2-3 sentence technical and design description answering: What product improvement could directly solve this problem?
   - differentiation_angle: Compelling value proposition and market positioning showing why this beats incumbent competitors.
   - implementation_feasibility: "high", "medium", or "low".
   - expected_impact: Expected customer reception, return reduction, or rating improvement.
   - target_price_impact: "cost_neutral", "minor_premium", or "premium_tier".

Return JSON with a single key "opportunities" mapping to a list of opportunity objects matching this structure:
{{
  "opportunities": [
    {{
      "title": "string",
      "problem_id": "string",
      "problem_name": "string",
      "category": "string",
      "improvement_type": "string",
      "improvement_concept": "string",
      "differentiation_angle": "string",
      "implementation_feasibility": "high",
      "expected_impact": "string",
      "target_price_impact": "cost_neutral"
    }}
  ]
}}
"""


class LLMOpportunityItem(BaseModel):
    title: str
    problem_id: str
    problem_name: str
    category: str
    improvement_type: str = "material_upgrade"
    improvement_concept: str
    differentiation_angle: str
    implementation_feasibility: str = "medium"
    expected_impact: str
    target_price_impact: str = "cost_neutral"


class LLMOpportunityResponse(BaseModel):
    opportunities: list[LLMOpportunityItem]


FEASIBILITY_WEIGHTS = {
    "high": 1.15,
    "medium": 1.0,
    "low": 0.85,
}


def _extract_evidence_quotes(cluster: ProblemCluster, limit: int = 3) -> list[str]:
    quotes = []
    for ev in cluster.sample_evidence:
        if ev.evidence_quote:
            quotes.append(ev.evidence_quote)
        elif ev.original_text:
            quotes.append(ev.original_text[:120].strip())
    return quotes[:limit]


def _heuristic_generate_opportunity(cluster: ProblemCluster, index: int) -> dict[str, Any]:
    """Offline heuristic rule-based opportunity generation when LLM is unavailable."""
    name_lower = cluster.name.lower()
    cat = cluster.category.lower()

    if any(k in name_lower for k in ["slip", "grip", "traction", "slide", "sweat"]):
        return {
            "title": "Hydro-Lock Micro-Textured Anti-Slip Surface",
            "category": "performance",
            "improvement_type": "material_upgrade",
            "improvement_concept": (
                "Directly solve slipping by implementing a dual-layer closed-cell TPE/polyurethane surface "
                "with laser-etched micro-ridges that wick moisture and dramatically increase traction when wet."
            ),
            "differentiation_angle": "Marketed as 'Guaranteed Zero-Slip' even in 90-minute hot sweat sessions.",
            "implementation_feasibility": "high",
            "expected_impact": "Eliminates ~90% of grip-related negative reviews and returns.",
            "target_price_impact": "minor_premium",
        }
    elif any(k in name_lower for k in ["tear", "flaking", "peel", "durable", "rip", "broken"]):
        return {
            "title": "Ripstop Composite Mesh Reinforcement Core",
            "category": "durability",
            "improvement_type": "mechanical_redesign",
            "improvement_concept": (
                "Directly solve tearing and flaking by embedding an internal tear-resistant polyester scrim "
                "surrounded by high-density bonded polymer, preventing edge splits and surface degradation."
            ),
            "differentiation_angle": "Promoted with a 2-year anti-rip warranty that incumbent brands cannot match.",
            "implementation_feasibility": "high",
            "expected_impact": "Drastically reduces durability complaints and extends product lifespan by 3x.",
            "target_price_impact": "cost_neutral",
        }
    elif any(k in name_lower for k in ["smell", "odor", "chemical", "toxic", "off-gas"]):
        return {
            "title": "Zero-VOC Aerated Eco-Pure Construction",
            "category": "materials_safety",
            "improvement_type": "manufacturing_process",
            "improvement_concept": (
                "Directly solve chemical odor complaints by replacing petroleum vulcanization with an "
                "organic curing protocol and a 48-hour thermal chamber aeration phase prior to packaging."
            ),
            "differentiation_angle": "Certified non-toxic, latex-free, and odorless right out of the box.",
            "implementation_feasibility": "high",
            "expected_impact": "Wipes out immediate return triggers caused by harsh initial chemical odor.",
            "target_price_impact": "cost_neutral",
        }
    elif any(k in name_lower for k in ["cushion", "thin", "pain", "joint", "wrist", "knee", "hard"]):
        return {
            "title": "Ergonomic Multi-Density Responsive Cushioning Core",
            "category": "comfort_ergonomics",
            "improvement_type": "material_upgrade",
            "improvement_concept": (
                "Directly solve joint and knee pain by layering a firm 3mm high-density stabilization base "
                "with a responsive 4mm memory shock-absorbing top foam that protects joints without bottoming out."
            ),
            "differentiation_angle": "Endorsed by physical therapists for joint-safe workouts.",
            "implementation_feasibility": "medium",
            "expected_impact": "Significantly lifts ratings among beginners and older demographics.",
            "target_price_impact": "minor_premium",
        }
    elif any(k in name_lower for k in ["curl", "roll", "edge", "flat", "lay flat"]):
        return {
            "title": "Anti-Memory Lay-Flat Boundary Architecture",
            "category": "design_aesthetics",
            "improvement_type": "mechanical_redesign",
            "improvement_concept": (
                "Directly solve curling edges by molding weighted low-profile perimeter corners and "
                "utilizing a cross-laminated non-directional polymer matrix that naturally resists roll-memory."
            ),
            "differentiation_angle": "Zero curl setup: lies 100% flat the instant it is unrolled.",
            "implementation_feasibility": "high",
            "expected_impact": "Eliminates initial setup frustration and creates immediate buyer delight.",
            "target_price_impact": "cost_neutral",
        }
    elif any(k in name_lower for k in ["carry", "strap", "heavy", "portable", "travel"]):
        return {
            "title": "Integrated Ultra-Light Quick-Latch Carry System",
            "category": "ease_of_use",
            "improvement_type": "bundle_accessory",
            "improvement_concept": (
                "Directly solve transport friction by bundling an ergonomic, breathable padded carry harness "
                "with magnetic quick-release clasps that fit into custom mat eyelets."
            ),
            "differentiation_angle": "All-in-one gym-to-commute portability included at no extra cost.",
            "implementation_feasibility": "high",
            "expected_impact": "Boosts perceived bundle value and spontaneous gift purchases.",
            "target_price_impact": "minor_premium",
        }
    else:
        return {
            "title": f"Targeted Product Redesign for {cluster.name[:35]}",
            "category": cat or "quality_defects",
            "improvement_type": "mechanical_redesign",
            "improvement_concept": (
                f"Directly solve '{cluster.name}' through an upgraded material formulation and reinforced structural "
                f"specifications specifically targeted at eliminating customer friction points."
            ),
            "differentiation_angle": f"Specifically engineered to resolve {cluster.name.lower()} found across market competitors.",
            "implementation_feasibility": "medium",
            "expected_impact": "Directly targets and neutralizes the primary negative review vector.",
            "target_price_impact": "cost_neutral",
        }


def _generate_with_gemini(
    client: Any,
    model_name: str,
    query: str,
    clusters: list[ProblemCluster],
) -> list[dict[str, Any]]:
    """Query Gemini to generate candidate opportunities for each problem."""
    payload = [
        {
            "problem_id": c.id,
            "name": c.name,
            "category": c.category,
            "description": c.description,
            "affected_product_count": c.affected_product_count,
            "avg_severity": c.avg_severity,
            "sample_evidence_quotes": _extract_evidence_quotes(c, limit=2),
        }
        for c in clusters
    ]

    prompt = OPPORTUNITY_PROMPT.format(
        query=query,
        problems_payload=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": LLMOpportunityResponse,
        },
    )

    raw_text = response.text or "{}"
    parsed = json.loads(raw_text)
    items = parsed.get("opportunities", [])
    results = []
    for item in items:
        if isinstance(item, dict) and item.get("title") and item.get("problem_id"):
            results.append(item)
    return results


def generate_candidate_opportunities(
    problem_analysis: ProblemAnalysis,
    *,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
    max_problems: int = 10,
) -> OpportunityAnalysis:
    """Step 4: Generate candidate product opportunities addressing major problems."""
    major_clusters = problem_analysis.clusters[:max_problems]

    if not major_clusters:
        return OpportunityAnalysis(
            query=problem_analysis.query,
            market=problem_analysis.market,
            created_at=datetime.now(timezone.utc),
            total_problems_evaluated=0,
            opportunities=[],
            method="empty",
            stats={"message": "No problem clusters provided for opportunity generation."},
        )

    api_key = gemini_api_key or get_gemini_api_key()
    client = None
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")

    raw_opportunities: list[dict[str, Any]] = []
    method = "gemini_llm"

    if client:
        try:
            raw_opportunities = _generate_with_gemini(
                client=client,
                model_name=gemini_model,
                query=problem_analysis.query,
                clusters=major_clusters,
            )
        except Exception as e:
            logger.warning(f"LLM opportunity generation failed: {e}; using heuristic generator")
            method = "heuristic_fallback"
    else:
        method = "heuristic_generator"

    # If LLM didn't return opportunities or was not available, run heuristic
    cluster_by_id = {c.id: c for c in major_clusters}
    if not raw_opportunities:
        for idx, cluster in enumerate(major_clusters, start=1):
            h_data = _heuristic_generate_opportunity(cluster, idx)
            h_data["problem_id"] = cluster.id
            h_data["problem_name"] = cluster.name
            raw_opportunities.append(h_data)

    # Post-process, compute priority score, attach quotes
    final_opportunities: list[CandidateOpportunity] = []
    for idx, item in enumerate(raw_opportunities, start=1):
        pid = item.get("problem_id", "")
        cluster = cluster_by_id.get(pid)
        if not cluster:
            # Fallback matching by name or position
            cluster = major_clusters[min(idx - 1, len(major_clusters) - 1)]

        feasibility = item.get("implementation_feasibility", "medium").lower()
        if feasibility not in FEASIBILITY_WEIGHTS:
            feasibility = "medium"

        weight = FEASIBILITY_WEIGHTS.get(feasibility, 1.0)
        # Priority score = Problem opportunity_score * feasibility multiplier
        priority = round(cluster.opportunity_score * weight, 4)

        quotes = _extract_evidence_quotes(cluster, limit=3)

        opp = CandidateOpportunity(
            id=f"opp_{idx:02d}",
            title=item["title"],
            problem_id=cluster.id,
            problem_name=cluster.name,
            category=item.get("category", cluster.category),
            improvement_type=item.get("improvement_type", "material_upgrade"),
            improvement_concept=item["improvement_concept"],
            differentiation_angle=item.get("differentiation_angle", ""),
            implementation_feasibility=feasibility,
            expected_impact=item.get("expected_impact", "Significant reduction in negative reviews."),
            target_price_impact=item.get("target_price_impact", "cost_neutral"),
            priority_score=priority,
            affected_product_count=cluster.affected_product_count,
            supporting_evidence_quotes=quotes,
        )
        final_opportunities.append(opp)

    # Sort opportunities by priority_score descending
    final_opportunities.sort(key=lambda o: o.priority_score, reverse=True)

    # Re-index IDs in sorted order
    for idx, opp in enumerate(final_opportunities, start=1):
        opp.id = f"opp_{idx:02d}"

    return OpportunityAnalysis(
        query=problem_analysis.query,
        market=problem_analysis.market,
        created_at=datetime.now(timezone.utc),
        total_problems_evaluated=len(major_clusters),
        opportunities=final_opportunities,
        method=method,
        stats={
            "problems_evaluated": len(major_clusters),
            "opportunities_generated": len(final_opportunities),
            "avg_priority_score": round(
                sum(o.priority_score for o in final_opportunities) / max(1, len(final_opportunities)),
                4,
            ),
        },
    )
