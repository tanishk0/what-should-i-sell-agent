"""End-to-end review intelligence pipeline: fetch, clean, classify, and summarize."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import DEFAULT_LLM_MODEL, get_gemini_api_key
from ..schema import Product, ResearchSet
from ..serp_client import SerpClient
from .classify import ReviewClassifier
from .clean import clean_reviews
from .fetch import CreditBudget, fetch_product_reviews
from .models import ProductReviews, ReviewIntelligence


def _prioritize_reviews_for_complaints(reviews: list[Review], limit: int) -> list[Review]:
    """Prioritizes reviews most likely to contain defects or friction,
    filtering out generic 5-star praise to minimize LLM token usage and avoid quota limits."""
    if len(reviews) <= limit:
        return reviews

    def _priority_key(r: Review) -> tuple[int, int]:
        rating = r.rating if r.rating is not None else 3.0
        has_neg_aspect = any(
            getattr(a, "sentiment", "").upper() == "NEGATIVE"
            for a in (r.marketplace_aspects or [])
        )
        if rating <= 2 or has_neg_aspect:
            score = 0
        elif rating <= 3:
            score = 1
        elif rating <= 4:
            score = 2
        else:
            score = 3
        return (score, -min(len(r.text), 400))

    sorted_revs = sorted(reviews, key=_priority_key)
    return sorted_revs[:limit]


def run_review_intelligence(
    research_set: ResearchSet,
    serp_client: SerpClient,
    *,
    competitor_limit: int = 10,
    credit_budget: int = 15,
    sources_per_product: int = 1,
    max_reviews_per_product: int = 6,
    llm_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    llm_model: Optional[str] = None,
    gemini_model: Optional[str] = None,
    classifier: Optional[ReviewClassifier] = None,
    on_progress: Optional[Any] = None,
) -> ReviewIntelligence:
    """Analyze reviews for the top competitors in a research set using NVIDIA Nemotron (or Gemini).

    Honors SerpAPI free-plan budget limits strictly and uses cached responses whenever available.
    """
    model_name = llm_model or gemini_model or DEFAULT_LLM_MODEL
    effective_key = llm_api_key or gemini_api_key
    if classifier is None:
        classifier = ReviewClassifier(api_key=effective_key, model=model_name)
    budget = CreditBudget(max_credits=credit_budget)

    target_products = research_set.products[:competitor_limit]
    product_review_list: list[ProductReviews] = []
    all_raw_reviews = []

    for rank, product in enumerate(target_products, start=1):
        if on_progress:
            on_progress(f"[{rank}/{len(target_products)}] Fetching reviews for '{product.title[:45]}'...")
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

    # Collect prioritized reviews across all products to classify in consolidated batches of 20-30
    all_focused_reviews: list[Review] = []
    for pr in product_review_list:
        raw_p_reviews = reviews_by_product.get(pr.product_id, [])
        p_reviews = _prioritize_reviews_for_complaints(raw_p_reviews, max_reviews_per_product)
        pr.reviews = p_reviews
        all_focused_reviews.extend(p_reviews)

    # Run LLM classification in consolidated batches of 15 (safe within token and memory limits)
    if all_focused_reviews:
        if on_progress:
            batches_count = (len(all_focused_reviews) + 14) // 15
            on_progress(f"Classifying {len(all_focused_reviews)} customer reviews with NVIDIA Nemotron in {batches_count} batch(es)...")
        classifier.classify_batch(all_focused_reviews, chunk_size=15)

    total_complaints = 0
    total_verified_quotes = 0
    complaint_category_counter = Counter()

    for pr in product_review_list:
        for r in pr.reviews:
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
        llm_model=classifier.model_name,
        products=product_review_list,
        stats=stats,
    )
