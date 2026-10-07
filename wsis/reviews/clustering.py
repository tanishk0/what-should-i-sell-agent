"""Cluster complaints into recurring problem themes.

Takes individual classified complaints across all competitors, groups them
by semantic similarity using Gemini (with an offline embedding/category heuristic fallback),
and ranks problem clusters by severity, frequency, and market breadth.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from ..config import get_gemini_api_key
from .models import Review, ReviewIntelligence
from .problem_models import ComplaintEvidence, ProblemAnalysis, ProblemCluster

logger = logging.getLogger(__name__)

CLUSTER_PROMPT = """You are an elite product market researcher.
Analyze the following list of customer complaints and frustrations collected from competing products in the "{query}" category.

Your mission is to turn these individual complaints into distinct, recurring PROBLEMS (clusters) that represent genuine market frustrations.

Instructions:
1. Group similar complaints into cohesive problem clusters.
2. For each cluster:
   - name: A punchy, descriptive name (e.g., "Slipping and lack of traction during sweaty workouts", "Premature flaking and edge peeling").
   - category: One of "performance", "durability", "materials_safety", "comfort_ergonomics", "size_fit", "quality_defects", "ease_of_use", "design_aesthetics", "value_price", "shipping_packaging", "other".
   - description: 2-3 sentences explaining the root customer pain point and why it hurts buyer satisfaction.
   - assigned_complaint_ids: List of complaint IDs belonging to this cluster.
   - avg_severity: Estimated average severity 1.0 - 3.0 (3 = dangerous/deal-breaker, 2 = major dissatisfaction, 1 = annoyance).

Complaints data:
{complaints_payload}

Return JSON with a single key "clusters" mapping to a list of cluster objects matching this structure:
{{
  "clusters": [
    {{
      "name": "string",
      "category": "string",
      "description": "string",
      "assigned_complaint_ids": ["string"],
      "avg_severity": 2.5
    }}
  ]
}}
"""


class LLMClusterItem(BaseModel):
    name: str
    category: str
    description: str
    assigned_complaint_ids: list[str] = Field(default_factory=list)
    avg_severity: float = 2.0


class LLMClusterResponse(BaseModel):
    clusters: list[LLMClusterItem]


def _build_complaint_evidence(r: Review) -> ComplaintEvidence:
    q = r.classification.evidence_quote if r.classification else None
    verified = r.classification.evidence_verified if r.classification else False
    return ComplaintEvidence(
        review_id=r.id,
        product_id=r.product_id,
        product_title=r.product_title,
        rating=r.rating,
        original_text=r.original_text,
        evidence_quote=q,
        evidence_verified=verified,
        url=r.url,
        citation=r.citation,
    )


def cluster_complaints(
    review_intel: ReviewIntelligence,
    *,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
    max_evidence_per_cluster: int = 5,
) -> ProblemAnalysis:
    """Cluster complaints from a ReviewIntelligence run into ranked recurring problems."""
    # Collect all complaint reviews across all products
    all_complaints: list[Review] = []
    total_reviews = 0

    for pr in review_intel.products:
        total_reviews += len(pr.reviews)
        for r in pr.reviews:
            if r.classification and r.classification.is_complaint and not r.classification.noise:
                all_complaints.append(r)

    if not all_complaints:
        return ProblemAnalysis(
            query=review_intel.query,
            market=review_intel.market,
            created_at=datetime.now(timezone.utc),
            total_reviews_analyzed=total_reviews,
            total_complaints_analyzed=0,
            clusters=[],
            method="empty",
            stats={"message": "No complaints found to cluster."},
        )

    api_key = gemini_api_key or get_gemini_api_key()
    client = None
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")

    clusters = []
    method = "gemini_llm"

    if client:
        try:
            clusters = _cluster_with_gemini(
                client=client,
                model_name=gemini_model,
                query=review_intel.query,
                complaints=all_complaints,
            )
        except Exception as e:
            logger.warning(f"LLM clustering failed: {e}; falling back to heuristic clustering")
            clusters = _cluster_heuristic(all_complaints)
            method = "heuristic_fallback"
    else:
        clusters = _cluster_heuristic(all_complaints)
        method = "heuristic_fallback"

    # Post-process, compute scores, attach evidence
    review_by_id = {r.id: r for r in all_complaints}
    final_clusters: list[ProblemCluster] = []
    total_complaints_count = len(all_complaints)

    for idx, c_data in enumerate(clusters, start=1):
        assigned_ids = c_data["assigned_complaint_ids"]
        matching_reviews = [review_by_id[cid] for cid in assigned_ids if cid in review_by_id]
        if not matching_reviews:
            continue

        affected_prods = sorted({r.product_id for r in matching_reviews})
        count = len(matching_reviews)
        freq = count / max(1, total_complaints_count)

        # Average severity
        severities = [
            r.classification.severity
            for r in matching_reviews
            if r.classification and r.classification.severity is not None
        ]
        avg_sev = sum(severities) / len(severities) if severities else c_data.get("avg_severity", 2.0)
        avg_sev = round(float(avg_sev), 2)

        # Opportunity score combines frequency, severity (scaled 1-3 -> 0.33-1.0), and breadth across competitors
        breadth_ratio = len(affected_prods) / max(1, len(review_intel.products))
        opportunity = round(freq * (avg_sev / 3.0) * (1.0 + breadth_ratio), 4)

        # Attach citations/evidence samples
        evidence_samples = [
            _build_complaint_evidence(r)
            for r in matching_reviews[:max_evidence_per_cluster]
        ]

        final_clusters.append(
            ProblemCluster(
                id=f"prob_{idx:02d}",
                name=c_data["name"],
                category=c_data["category"],
                description=c_data["description"],
                affected_products=affected_prods,
                affected_product_count=len(affected_prods),
                total_complaints=count,
                avg_severity=avg_sev,
                frequency_score=round(freq, 3),
                opportunity_score=opportunity,
                sample_evidence=evidence_samples,
            )
        )

    # Sort clusters by opportunity_score descending
    final_clusters.sort(key=lambda c: c.opportunity_score, reverse=True)

    return ProblemAnalysis(
        query=review_intel.query,
        market=review_intel.market,
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=total_reviews,
        total_complaints_analyzed=total_complaints_count,
        clusters=final_clusters,
        method=method,
        stats={
            "total_clusters": len(final_clusters),
            "unassigned_complaints": total_complaints_count - sum(c.total_complaints for c in final_clusters),
            "top_problem": final_clusters[0].name if final_clusters else None,
        },
    )


def _cluster_with_gemini(
    client,
    model_name: str,
    query: str,
    complaints: list[Review],
) -> list[dict]:
    payload = []
    for r in complaints:
        issues = r.classification.issues if r.classification else []
        cats = r.classification.categories if r.classification else []
        payload.append({
            "id": r.id,
            "product_title": r.product_title[:60],
            "rating": r.rating,
            "categories": cats,
            "issues": issues,
            "snippet": r.text[:250],
        })

    prompt = CLUSTER_PROMPT.format(
        query=query,
        complaints_payload=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": LLMClusterResponse,
        },
    )
    data = json.loads(response.text)
    return [item for item in data.get("clusters", [])]


def _cluster_heuristic(complaints: list[Review]) -> list[dict]:
    """Semantic category & issue clustering fallback."""
    by_category_and_issue = defaultdict(list)

    category_default_names = {
        "performance": "Grip, traction & slippage issues",
        "durability": "Premature wear, peeling & tearing",
        "comfort_ergonomics": "Insufficient cushioning & joint discomfort",
        "materials_safety": "Strong odor & chemical smells",
        "quality_defects": "Manufacturing defects & poor finish",
        "size_fit": "Inaccurate thickness or dimensions",
        "ease_of_use": "Difficult to roll, pack, or carry",
        "value_price": "Poor value for money compared to alternatives",
    }

    for r in complaints:
        cats = r.classification.categories if r.classification else []
        issues = r.classification.issues if r.classification else []
        primary_cat = cats[0] if cats else "performance"
        primary_issue = issues[0] if issues else category_default_names.get(primary_cat, "General product dissatisfaction")
        by_category_and_issue[(primary_cat, primary_issue)].append(r.id)

    clusters = []
    for (cat, issue), r_ids in by_category_and_issue.items():
        clusters.append({
            "name": issue,
            "category": cat,
            "description": f"Buyers report recurring frustrations related to {cat.replace('_', ' ')}: specifically, {issue.lower()}.",
            "assigned_complaint_ids": r_ids,
            "avg_severity": 2.0,
        })
    return clusters
