"""LLM review classifier with citation/evidence verification.

Classifies reviews for buyer frustrations, sentiments, and complaint categories.
Verifies that any evidence quote is a verbatim substring of the original review text,
preventing hallucinated quotations.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import DEFAULT_LLM_MODEL, require_gemini_api_key, require_nvidia_api_key
from ..llm_client import call_llm, clean_json_response, extract_results_from_json
from .models import CATEGORIES, Review, ReviewClassification

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

CLASSIFY_PROMPT = """You are an expert market research analyst studying competitor reviews to understand buyer frustrations and defects.
Analyze the following batch of customer reviews{context_info}.

For each review, determine:
1. sentiment: "positive", "negative", "mixed", or "neutral"
2. is_complaint: true if the reviewer expresses disappointment, dissatisfaction, friction, or a defect.
3. noise: true if the review is off-topic, spam, or gibberish.
4. categories: list of applicable complaint categories from the list below:
{categories_formatted}
5. issues: short, specific bullet points summarizing buyer frustrations or friction (e.g. "tears easily along edges", "slips on wood floors").
6. severity: integer rating (1 = minor annoyance, 2 = significant defect/issue, 3 = dangerous or deal-breaker return reason). Null if not a complaint.
7. evidence_quote: An EXACT, verbatim phrase extracted word-for-word from the review that proves the primary complaint. If no clear quote or not a complaint, return null.

Reviews to classify:
{reviews_payload}

Return JSON with a single key "results" mapping to a list of classification objects in the exact same order as the input reviews.
Each object must have fields:
- review_id: string
- sentiment: "positive" | "negative" | "mixed" | "neutral"
- is_complaint: boolean
- noise: boolean
- categories: list of strings
- issues: list of strings
- severity: integer (1-3) or null
- evidence_quote: string or null
"""


class BatchClassificationItem(BaseModel):
    review_id: str
    sentiment: str = "neutral"
    is_complaint: bool = False
    noise: bool = False
    categories: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    severity: Optional[int] = None
    evidence_quote: Optional[str] = None


class BatchClassificationResponse(BaseModel):
    results: list[BatchClassificationItem]


def verify_evidence(quote: Optional[str], review_text: str, original_text: str) -> tuple[Optional[str], bool]:
    """Verify that evidence_quote is a verbatim substring of the review."""
    if not quote or not quote.strip():
        return None, False
    q = quote.strip()
    if q in review_text or q in original_text:
        return q, True
    # Case-insensitive / whitespace-normalized fallback search
    q_norm = " ".join(q.lower().split())
    if q_norm in " ".join(review_text.lower().split()) or q_norm in " ".join(original_text.lower().split()):
        return q, True
    # Quote failed verbatim verification
    return q, False


class ReviewClassifier:
    """Classifies reviews using NVIDIA Nemotron LLM (or Gemini) without fake fallbacks."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.model_name = model or DEFAULT_LLM_MODEL
        self.client = client
        if client is not None:
            self.api_key = api_key
        elif "gemini" in self.model_name.lower():
            self.api_key = api_key or require_gemini_api_key()
        else:
            self.api_key = api_key or require_nvidia_api_key()

    def classify_batch(
        self,
        reviews: list[Review],
        product_title: Optional[str] = None,
        chunk_size: int = 15,
    ) -> None:
        """Classify a list of reviews in-place in batches of 15 to prevent token limits and server overloads."""
        if not reviews:
            return

        for i in range(0, len(reviews), chunk_size):
            chunk = reviews[i : i + chunk_size]
            self._classify_chunk(chunk, product_title=product_title)
            if i + chunk_size < len(reviews):
                time.sleep(2.0)

    def _classify_chunk(self, reviews: list[Review], product_title: Optional[str] = None) -> None:
        categories_fmt = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
        context_info = f" for the product: '{product_title}'" if product_title else " across competitor products"

        # Truncate text to 350 chars to substantially reduce token payload while keeping complaints intact
        payload = [
            {
                "review_id": r.id,
                "product_title": (r.product_title or "Competitor")[:50],
                "text": r.text[:350],
                "rating": r.rating,
            }
            for r in reviews
        ]

        prompt = CLASSIFY_PROMPT.format(
            context_info=context_info,
            categories_formatted=categories_fmt,
            reviews_payload=json.dumps(payload, ensure_ascii=False, indent=2),
        )

        label = product_title or f"batch of {len(reviews)} reviews"
        try:
            raw_text = call_llm(
                prompt=prompt,
                model=self.model_name,
                api_key=self.api_key,
                client=self.client,
            )
        except Exception as e:
            raise RuntimeError(
                f"Review classification failed for '{label}' using {self.model_name}: {e}"
            ) from e

        try:
            results_list = extract_results_from_json(raw_text)
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse classification JSON for '{label}': {e}\nRaw output: {raw_text}"
            ) from e

        classified_items = {
            item["review_id"]: item for item in results_list
        }

        for r in reviews:
            item = classified_items.get(r.id)
            if not item:
                # Fallback: if LLM missed a review_id, assign neutral so pipeline does not crash
                r.classification = ReviewClassification(
                    sentiment="neutral",
                    is_complaint=False,
                    noise=False,
                    categories=[],
                    issues=[],
                    model=self.model_name,
                    prompt_version=PROMPT_VERSION,
                )
                continue
            quote, verified = verify_evidence(item.get("evidence_quote"), r.text, r.original_text)
            valid_cats = [c for c in item.get("categories", []) if c in CATEGORIES]
            r.classification = ReviewClassification(
                sentiment=item.get("sentiment", "neutral"),
                is_complaint=item.get("is_complaint", False),
                noise=item.get("noise", False),
                categories=valid_cats,
                issues=item.get("issues", []),
                severity=item.get("severity"),
                evidence_quote=quote,
                evidence_verified=verified,
                model=self.model_name,
                prompt_version=PROMPT_VERSION,
            )

