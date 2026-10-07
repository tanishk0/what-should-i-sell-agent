"""End-to-end review intelligence pipeline: fetch, clean, classify, and summarize."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import RUNS_DIR, get_gemini_api_key
from ..schema import Product, ResearchSet
from ..serp_client import SerpClient
from .classify import ReviewClassifier
from .clean import clean_reviews
from .fetch import CreditBudget, fetch_product_reviews
from .models import ProductReviews, ReviewIntelligence


def run_review_intelligence(
    research_set: ResearchSet,
    serp_client: SerpClient,
    *,
    competitor_limit: int = 10,
    credit_budget: int = 15,
    sources_per_product: int = 2,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
) -> ReviewIntelligence:
    """Analyze reviews for the top competitors in a research set.

    Honors SerpAPI free-plan budget limits strictly and uses cached responses whenever available.
    """
    api_key = gemini_api_key or get_gemini_api_key()
    classifier = ReviewClassifier(api_key=api_key, model=gemini_model)
    budget = CreditBudget(max_credits=credit_budget)

    target_products = research_set.products[:competitor_limit]
    product_review_list: list[ProductReviews] = []
    all_raw_reviews = []

    for rank, product in enumerate(target_products, start=1):
        pr = fetch_product_reviews(
            product,
            rank=rank,
            client=serp_client,
            budget=budget,
            sources_per_product=sources_per_product,
        )
        product_review_list.append(pr)
        all_raw_reviews.extend(pr.reviews)

    # Clean and deduplicate reviews across the batch
    cleaned_reviews, clean_stats = clean_reviews(all_raw_reviews)

    # Re-associate cleaned reviews with their corresponding ProductReviews container
    reviews_by_product: dict[str, list] = {}
    for r in cleaned_reviews:
        reviews_by_product.setdefault(r.product_id, []).append(r)

    # Run LLM classification per product batch
    total_complaints = 0
    total_verified_quotes = 0
    complaint_category_counter = Counter()

    for pr in product_review_list:
        p_reviews = reviews_by_product.get(pr.product_id, [])
        pr.reviews = p_reviews
        if p_reviews:
            classifier.classify_batch(p_reviews, product_title=pr.product_title)
            for r in p_reviews:
                if r.classification and r.classification.is_complaint:
                    total_complaints += 1
                    complaint_category_counter.update(r.classification.categories)
                    if r.classification.evidence_verified:
                        total_verified_quotes += 1

    stats = {
        "products_evaluated": len(target_products),
        "credit_budget_max": budget.max_credits,
        "credits_spent": budget.used,
        "cached_calls": budget.cached_calls,
        "calls_skipped_budget": budget.skipped,
        "cleaning": dict(clean_stats),
        "total_cleaned_reviews": len(cleaned_reviews),
        "total_complaints_found": total_complaints,
        "verified_evidence_quotes": total_verified_quotes,
        "top_frustration_categories": dict(complaint_category_counter.most_common(5)),
    }

    return ReviewIntelligence(
        query=research_set.query,
        market=research_set.market,
        source_run=f"{research_set.query} ({research_set.created_at})",
        created_at=datetime.now(timezone.utc),
        llm_model=classifier.model_name if classifier.client else "heuristic_fallback",
        products=product_review_list,
        stats=stats,
    )
