"""LLM review classifier with citation/evidence verification.

Classifies reviews for buyer frustrations, sentiments, and complaint categories.
Verifies that any evidence quote is a verbatim substring of the original review text,
preventing hallucinated quotations.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field

from .models import CATEGORIES, Review, ReviewClassification

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

CLASSIFY_PROMPT = """You are an expert market research analyst studying competitor reviews to understand buyer frustrations.
Analyze the following batch of customer reviews for the product: "{product_title}".

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
    """Classifies reviews using Gemini LLM, with fallback when API key is missing or calls fail."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.model_name = model
        self.client = None
        if api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

    def classify_batch(self, reviews: list[Review], product_title: str) -> None:
        """Classify a list of reviews in-place."""
        if not reviews:
            return

        if not self.client:
            self._heuristic_classify(reviews)
            return

        categories_fmt = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
        payload = [
            {"review_id": r.id, "text": r.text, "rating": r.rating}
            for r in reviews
        ]

        prompt = CLASSIFY_PROMPT.format(
            product_title=product_title,
            categories_formatted=categories_fmt,
            reviews_payload=json.dumps(payload, ensure_ascii=False, indent=2),
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": BatchClassificationResponse,
                },
            )
            raw_text = response.text
            parsed = json.loads(raw_text)
            classified_items = {
                item["review_id"]: item for item in parsed.get("results", [])
            }

            for r in reviews:
                item = classified_items.get(r.id)
                if item:
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
                else:
                    self._heuristic_single(r)
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}; falling back to heuristics")
            self._heuristic_classify(reviews)

    def _heuristic_classify(self, reviews: list[Review]) -> None:
        """Rule-based fallback when Gemini is unavailable, ensuring the pipeline never breaks."""
        for r in reviews:
            self._heuristic_single(r)

    def _heuristic_single(self, r: Review) -> None:
        text_lower = r.text.lower()
        rating = r.rating

        is_negative = (rating is not None and rating <= 2.0) or any(
            w in text_lower for w in ["terrible", "horrible", "awful", "waste of money", "disappointed", "poor", "broken"]
        )
        is_mixed = (rating == 3.0) or any(
            w in text_lower for w in ["however", "but", "although", "mixed"]
        )
        is_positive = (rating is not None and rating >= 4.0) and not is_negative

        sentiment = "negative" if is_negative else ("positive" if is_positive else ("mixed" if is_mixed else "neutral"))
        is_complaint = is_negative or is_mixed

        cats = []
        issues = []
        if any(w in text_lower for w in ["slip", "slide", "grip", "traction"]):
            cats.append("performance")
            issues.append("Slippery surface / lack of grip")
        if any(w in text_lower for w in ["rip", "tear", "peel", "flaking", "durab"]):
            cats.append("durability")
            issues.append("Material rips, tears or wears out quickly")
        if any(w in text_lower for w in ["smell", "odor", "chemical", "toxic"]):
            cats.append("materials_safety")
            issues.append("Strong chemical or rubber odor")
        if any(w in text_lower for w in ["thin", "cushion", "knees hurt", "pain"]):
            cats.append("comfort_ergonomics")
            issues.append("Too thin or insufficient joint cushioning")

        r.classification = ReviewClassification(
            sentiment=sentiment,
            is_complaint=is_complaint,
            noise=False,
            categories=cats,
            issues=issues,
            severity=2 if is_negative else (1 if is_mixed else None),
            evidence_quote=None,
            evidence_verified=False,
            model="heuristic_fallback",
            prompt_version="rule_v1",
        )
