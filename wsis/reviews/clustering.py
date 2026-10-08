"""Cluster complaints into recurring problem themes using Gemini.

Takes individual classified complaints across competitors, groups them
by semantic similarity, and programmatically computes evidence counts from actual review objects.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import DEFAULT_GEMINI_MODEL, require_gemini_api_key
from .models import Review, ReviewIntelligence
from .problem_models import ComplaintEvidence, ProblemAnalysis, ProblemCluster

logger = logging.getLogger(__name__)

CLUSTER_PROMPT = """You are an elite product market researcher.
Analyze the following customer complaints and frustrations collected from competing products in the "{query}" category on Amazon.

Your mission is to group these individual complaints into distinct, recurring customer PROBLEMS (clusters).

Rules:
1. Group complaints that share the same underlying defect, frustration, or friction.
2. For each cluster:
   - name: Concise, descriptive title of the customer problem (e.g. "Frame hinges break easily", "Lenses peel and scratch quickly").
   - category: One of "performance", "durability", "materials_safety", "comfort_ergonomics", "size_fit", "quality_defects", "ease_of_use", "design_aesthetics", "value_price", "shipping_packaging", "other".
   - description: 2-3 sentences explaining the root customer pain point and why it frustrates buyers.
   - assigned_complaint_ids: List of exact complaint IDs (from the data below) that belong to this problem.
3. Do NOT invent complaints. Only assign IDs that actually express this problem.

Complaints data:
{complaints_payload}

Return JSON with a single key "clusters" mapping to a list of cluster objects matching:
{{
  "clusters": [
    {{
      "name": "string",
      "category": "string",
      "description": "string",
      "assigned_complaint_ids": ["string"]
    }}
  ]
}}
"""


class LLMClusterItem(BaseModel):
    name: str
    category: str = "other"
    description: str
    assigned_complaint_ids: list[str] = Field(default_factory=list)


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
    gemini_model: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> ProblemAnalysis:
    """Cluster complaints from a ReviewIntelligence run into ranked recurring problems using Gemini.

    All evidence counts (review_count, product_count, prevalence) are derived programmatically.
    """
    model_name = gemini_model or DEFAULT_GEMINI_MODEL

    # 1. Collect all complaint reviews across all products
    all_complaints: list[Review] = []
    total_reviews = 0
    all_product_ids = [pr.product_id for pr in review_intel.products]

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

    # 2. Get LLM client
    if llm_client is not None:
        client = llm_client
    else:
        api_key = gemini_api_key or require_gemini_api_key()
        try:
            from google import genai
            from google.genai import types
            http_options = types.HttpOptions(
                timeout=90000,
                retry_options=types.HttpRetryOptions(attempts=1),
            )
            client = genai.Client(api_key=api_key, http_options=http_options)
        except Exception as e:
            raise RuntimeError(f"Could not initialize Gemini client: {e}") from e

    # 3. Call Gemini
    try:
        raw_clusters = _cluster_with_gemini(
            client=client,
            model_name=model_name,
            query=review_intel.query,
            complaints=all_complaints,
        )
    except Exception as e:
        raise RuntimeError(
            f"Gemini complaint clustering failed using {model_name}: {e}"
        ) from e

    # 4. Programmatic Aggregation: Evidence is the Source of Truth
    review_by_id = {r.id: r for r in all_complaints}
    final_clusters: list[ProblemCluster] = []
    total_products_count = max(1, len(review_intel.products))

    for idx, c_data in enumerate(raw_clusters, start=1):
        assigned_ids = c_data.get("assigned_complaint_ids") or c_data.get("complaint_ids") or []
        # Filter strictly to reviews that exist in the classified dataset
        matching_reviews = [review_by_id[cid] for cid in assigned_ids if cid in review_by_id]
        if not matching_reviews:
            continue

        # Programmatically derive supporting evidence arrays
        supporting_ev = [_build_complaint_evidence(r) for r in matching_reviews]
        supporting_prods = sorted({r.product_id for r in matching_reviews})
        unaffected_prods = [pid for pid in all_product_ids if pid not in supporting_prods]

        # Programmatically derive counts
        rev_count = len(supporting_ev)
        prod_count = len(supporting_prods)
        prevalence = round((prod_count / total_products_count) * 100, 1)

        # Average severity from actual review objects
        severities = [
            r.classification.severity
            for r in matching_reviews
            if r.classification and r.classification.severity is not None
        ]
        avg_sev = round(sum(severities) / len(severities), 2) if severities else 2.0

        is_widespread = prod_count >= 2 and len(review_intel.products) >= 2

        final_clusters.append(
            ProblemCluster(
                id=f"prob_{idx:02d}",
                problem=c_data["name"],
                category=c_data.get("category", "other"),
                description=c_data["description"],
                supporting_reviews=supporting_ev,
                supporting_products=supporting_prods,
                unaffected_products=unaffected_prods,
                review_count=rev_count,
                product_count=prod_count,
                product_prevalence_pct=prevalence,
                avg_severity=avg_sev,
                is_widespread_gap=is_widespread,
            )
        )

    # Sort clusters by evidence breadth and depth:
    # 1. Number of affected products (market prevalence)
    # 2. Number of supporting reviews
    # 3. Severity
    final_clusters.sort(key=lambda c: (c.product_count, c.review_count, c.avg_severity), reverse=True)

    # Re-index IDs in sorted order
    for idx, c in enumerate(final_clusters, start=1):
        c.id = f"prob_{idx:02d}"

    return ProblemAnalysis(
        query=review_intel.query,
        market=review_intel.market,
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=total_reviews,
        total_complaints_analyzed=len(all_complaints),
        clusters=final_clusters,
        method="gemini_clustering",
        stats={
            "total_clusters": len(final_clusters),
            "widespread_market_gaps": sum(1 for c in final_clusters if c.is_widespread_gap),
            "isolated_defects": sum(1 for c in final_clusters if not c.is_widespread_gap),
            "unassigned_complaints": len(all_complaints) - sum(c.review_count for c in final_clusters),
            "top_problem": final_clusters[0].problem if final_clusters else None,
        },
    )


def _cluster_with_gemini(
    client: Any,
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
