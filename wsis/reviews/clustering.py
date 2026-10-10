"""Cluster complaints into recurring problem themes using Gemini or NVIDIA Nemotron.

Takes individual classified complaints across competitors, groups them
by semantic similarity, and programmatically computes evidence counts from actual review objects.
Enforces rigorous evidence integrity, semantic relevance validation, quote reuse prevention,
and cluster deduplication.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import DEFAULT_LLM_MODEL, require_gemini_api_key, require_nvidia_api_key
from ..llm_client import call_llm, clean_json_response, extract_clusters_from_json
from .evidence_validation import (
    deduplicate_and_merge_clusters,
    detect_themes,
    find_matching_span_in_review,
    normalize_text,
    validate_evidence_relevance,
    verify_span_verbatim,
)
from .models import Review, ReviewIntelligence
from .problem_models import ComplaintEvidence, ProblemAnalysis, ProblemCluster

logger = logging.getLogger(__name__)

CLUSTER_PROMPT = """You are an elite product market researcher.
Analyze the following customer complaints and frustrations collected from competing products in the "{query}" category on Amazon.

Your mission is to group these individual complaints into distinct, recurring customer PROBLEMS (clusters).

Rules:
1. Group complaints that share the same underlying defect, frustration, or friction.
2. Group into at most 5-7 distinct recurring problems. Do not create duplicate or overlapping clusters.
3. For each cluster:
   - name: Concise, descriptive title of the customer problem (e.g. "Frame hinges break easily", "Lenses peel and scratch quickly").
   - category: One of "performance", "durability", "materials_safety", "comfort_ergonomics", "size_fit", "quality_defects", "ease_of_use", "design_aesthetics", "value_price", "shipping_packaging", "other".
   - description: 1-2 concise sentences explaining the root customer pain point.
   - assigned_complaint_ids: List of exact complaint IDs (from the data below) that belong to this problem.
4. CRITICAL EVIDENCE INTEGRITY:
   - Only assign review IDs that actually express this specific problem.
   - Never assign a loose-fit complaint to a packaging damage problem.
   - Never assign a drop-protection complaint to a yellowing problem.
   - Do NOT use unescaped double quotes inside descriptions or strings.

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


class LLMAssignedComplaint(BaseModel):
    review_id: str
    quote: Optional[str] = None


class LLMClusterItem(BaseModel):
    name: str
    category: str = "other"
    description: str
    assigned_complaint_ids: list[str] = Field(default_factory=list)
    assigned_complaints: list[LLMAssignedComplaint] = Field(default_factory=list)


class LLMClusterResponse(BaseModel):
    clusters: list[LLMClusterItem]


def _build_complaint_evidence(r: Review, quote: Optional[str] = None, verified: bool = False) -> ComplaintEvidence:
    q = quote or (r.classification.evidence_quote if r.classification else None)
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
    api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    llm_client: Optional[Any] = None,
) -> ProblemAnalysis:
    """Cluster complaints from a ReviewIntelligence run into ranked recurring problems.

    All evidence counts (review_count, product_count, prevalence) are derived programmatically.
    Strictly validates evidence spans, prevents quote reuse, rejects unrelated evidence,
    and merges duplicate clusters.
    """
    model_name = model or gemini_model or DEFAULT_LLM_MODEL
    effective_key = api_key or gemini_api_key

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

    # 2. Call LLM to cluster complaints semantically
    try:
        raw_clusters = _cluster_with_llm(
            client=llm_client,
            model_name=model_name,
            api_key=effective_key,
            query=review_intel.query,
            complaints=all_complaints,
        )
    except Exception as e:
        raise RuntimeError(
            f"Complaint clustering failed using {model_name}: {e}"
        ) from e

    # 3. Programmatic Validation & Aggregation
    review_by_id = {r.id: r for r in all_complaints}
    candidate_clusters: list[ProblemCluster] = []
    total_products_count = max(1, len(review_intel.products))

    # Global tracking of evidence quotes to prevent reuse across unrelated clusters (Requirement 4)
    # quote_norm -> (cluster_id, cluster_category, cluster_theme_set)
    used_quotes: dict[str, tuple[str, str, frozenset[str]]] = {}

    for idx, c_data in enumerate(raw_clusters, start=1):
        cluster_id = f"prob_{idx:02d}"
        cluster_name = c_data.get("name", "Unnamed Problem")
        cluster_cat = c_data.get("category", "other")
        cluster_desc = c_data.get("description", "")
        cluster_themes = frozenset(detect_themes(f"{cluster_name} {cluster_cat} {cluster_desc}"))

        # Build map of candidate quotes per review_id from LLM output
        candidate_quotes_map: dict[str, Optional[str]] = {}

        # 1. Check explicit "assigned_complaints"
        for ac in c_data.get("assigned_complaints", []):
            if isinstance(ac, dict) and "review_id" in ac:
                candidate_quotes_map[ac["review_id"]] = ac.get("quote")
            elif hasattr(ac, "review_id"):
                candidate_quotes_map[ac.review_id] = getattr(ac, "quote", None)

        # 2. Check "assigned_complaint_ids" / "complaint_ids"
        assigned_ids = c_data.get("assigned_complaint_ids") or c_data.get("complaint_ids") or []
        for cid in assigned_ids:
            if cid not in candidate_quotes_map:
                candidate_quotes_map[cid] = None

        validated_ev_list: list[ComplaintEvidence] = []
        seen_reviews_in_cluster: set[str] = set()

        for rid, cand_quote in candidate_quotes_map.items():
            if rid not in review_by_id:
                continue

            # Requirement 3: Prevent one review from being counted multiple times for the same cluster
            if rid in seen_reviews_in_cluster:
                continue

            r = review_by_id[rid]

            # Determine the quote to test
            test_quote = cand_quote
            if not test_quote and r.classification and r.classification.evidence_quote:
                test_quote = r.classification.evidence_quote

            # Try to validate the candidate quote
            quote_verified = False
            final_quote = None

            if test_quote:
                clean_q, is_verbatim = verify_span_verbatim(test_quote, r.text, r.original_text)
                if is_verbatim and clean_q:
                    # Semantic relevance check (Requirement 2)
                    cats = r.classification.categories if r.classification else []
                    issues = r.classification.issues if r.classification else []
                    rel_ok, rel_msg = validate_evidence_relevance(
                        clean_q,
                        r.text,
                        cluster_name,
                        cluster_cat,
                        cluster_desc,
                        review_categories=cats,
                        review_issues=issues,
                    )
                    if rel_ok:
                        final_quote = clean_q
                        quote_verified = True

            # If initial quote was not semantically relevant or missing, check if review has another matching span
            if not quote_verified:
                matching_span = find_matching_span_in_review(
                    r.text,
                    cluster_name,
                    cluster_cat,
                    cluster_desc,
                )
                if matching_span:
                    clean_span, is_verb = verify_span_verbatim(matching_span, r.text, r.original_text)
                    if is_verb and clean_span:
                        final_quote = clean_span
                        quote_verified = True

            # Requirement 1 & 10: If evidence cannot be validated as a verbatim, semantically relevant span, exclude it!
            if not quote_verified or not final_quote:
                logger.debug(
                    "Excluded review %s from cluster '%s': no validated semantic evidence span.",
                    rid, cluster_name,
                )
                continue

            # Requirement 4: Do not reuse evidence quotes across unrelated complaint clusters
            norm_q = normalize_text(final_quote)
            if norm_q in used_quotes:
                prev_cid, prev_cat, prev_themes = used_quotes[norm_q]
                if prev_cid != cluster_id:
                    # Check if clusters are related (same category or overlapping theme)
                    is_related = (prev_cat == cluster_cat and prev_cat != "other") or bool(prev_themes & cluster_themes)
                    if not is_related:
                        logger.warning(
                            "Rejected quote reuse: '%s' was already used in unrelated cluster %s (%s).",
                            final_quote, prev_cid, prev_cat,
                        )
                        continue

            used_quotes[norm_q] = (cluster_id, cluster_cat, cluster_themes)
            seen_reviews_in_cluster.add(rid)

            ev = _build_complaint_evidence(r, quote=final_quote, verified=True)
            validated_ev_list.append(ev)

        # Requirement 10: If cluster has no validated evidence, exclude it
        if not validated_ev_list:
            continue

        supporting_prods = sorted({ev.product_id for ev in validated_ev_list})
        unaffected_prods = [pid for pid in all_product_ids if pid not in supporting_prods]
        rev_count = len({ev.review_id for ev in validated_ev_list})
        prod_count = len(supporting_prods)
        prevalence = round((prod_count / total_products_count) * 100, 1)

        matching_review_objs = [review_by_id[ev.review_id] for ev in validated_ev_list]
        severities = [
            ro.classification.severity
            for ro in matching_review_objs
            if ro.classification and ro.classification.severity is not None
        ]
        avg_sev = round(sum(severities) / len(severities), 2) if severities else 2.0

        # Requirement 7: Two affected products alone must not qualify as widespread!
        is_widespread = (prod_count >= 3) and (prevalence >= 50.0)

        candidate_clusters.append(
            ProblemCluster(
                id=cluster_id,
                problem=cluster_name,
                category=cluster_cat,
                description=cluster_desc,
                supporting_reviews=validated_ev_list,
                supporting_products=supporting_prods,
                unaffected_products=unaffected_prods,
                review_count=rev_count,
                product_count=prod_count,
                product_prevalence_pct=prevalence,
                avg_severity=avg_sev,
                is_widespread_gap=is_widespread,
            )
        )

    # 4. Cluster Deduplication & Semantic Merging (Requirement 8)
    final_clusters = deduplicate_and_merge_clusters(
        candidate_clusters,
        total_products_count=total_products_count,
        all_product_ids=all_product_ids,
    )

    # Sort clusters by evidence breadth and depth:
    # 1. Number of affected products (market prevalence)
    # 2. Number of supporting reviews
    # 3. Severity
    final_clusters.sort(key=lambda c: (c.product_count, c.review_count, c.avg_severity), reverse=True)

    # Re-index IDs in sorted order
    for idx, c in enumerate(final_clusters, start=1):
        c.id = f"prob_{idx:02d}"

    widespread_count = sum(1 for c in final_clusters if c.is_widespread_gap)
    multi_count = sum(1 for c in final_clusters if not c.is_widespread_gap and c.product_count >= 2)
    isolated_count = sum(1 for c in final_clusters if c.product_count == 1)

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
            "widespread_market_gaps": widespread_count,
            "multi_competitor_patterns": multi_count,
            "isolated_defects": isolated_count,
            "unassigned_complaints": len(all_complaints) - sum(c.review_count for c in final_clusters),
            "top_problem": final_clusters[0].problem if final_clusters else None,
        },
    )


def _cluster_with_llm(
    client: Any,
    model_name: str,
    api_key: Optional[str],
    query: str,
    complaints: list[Review],
) -> list[dict]:
    # Cap to top 30 complaints to avoid giant payloads and preserve context budget
    sample_complaints = complaints[:30]
    payload = []
    for r in sample_complaints:
        issues = r.classification.issues if r.classification else []
        cats = r.classification.categories if r.classification else []
        q = r.classification.evidence_quote if r.classification else None
        payload.append({
            "id": r.id,
            "product_title": (r.product_title or "Product")[:50],
            "rating": r.rating,
            "categories": cats,
            "issues": issues,
            "evidence_quote": q,
            "snippet": r.text[:250],
        })

    prompt = CLUSTER_PROMPT.format(
        query=query,
        complaints_payload=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    raw_text = call_llm(
        prompt=prompt,
        model=model_name,
        api_key=api_key,
        client=client,
    )
    return extract_clusters_from_json(raw_text)
