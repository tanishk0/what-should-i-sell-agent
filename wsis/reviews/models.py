"""Schema for review intelligence.

Every `Review` keeps the untouched `original_text`, a link to the review (or
the product page when the marketplace exposes no per-review link), and a
citation back to the SerpAPI search that returned it. LLM output is attached
as `classification`, and its `evidence_quote` is verified in code to be a
verbatim substring of the review.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..schema import Source

Sentiment = Literal["positive", "negative", "mixed", "neutral"]

# Category-agnostic complaint taxonomy (works for yoga mats and standing desks alike).
CATEGORIES: dict[str, str] = {
    "durability": "breaks, tears, wears out, stops working over time",
    "quality_defects": "arrived damaged/defective, poor build or finish, inconsistent quality",
    "performance": "doesn't do its core job well (e.g. grip, stability, power, accuracy)",
    "size_fit": "dimensions, thickness, weight, fit are wrong or not as expected",
    "comfort_ergonomics": "uncomfortable, causes pain, awkward to use physically",
    "ease_of_use": "hard to use, clean, store, adjust, or operate",
    "assembly_setup": "difficult assembly/installation, missing parts, bad instructions",
    "materials_safety": "smell, chemicals, allergens, toxicity, unsafe materials",
    "design_aesthetics": "looks, color, style, finish differs from expectations",
    "value_price": "overpriced, not worth the money, cheaper alternatives better",
    "accuracy_vs_listing": "product differs from photos/description/claims",
    "shipping_packaging": "late, damaged in transit, poor packaging",
    "customer_service": "returns, warranty, seller support problems",
    "other": "a real complaint that fits none of the above",
}


class ReviewCitation(BaseModel):
    source: Source
    engine: str
    search_id: Optional[str] = None
    serpapi_json_url: Optional[str] = Field(None, description="Archived SerpAPI JSON containing this review.")
    product_url: str
    review_url: Optional[str] = Field(None, description="Direct link to the review if the marketplace provides one.")
    retrieved_at: Optional[datetime] = None


class AspectTag(BaseModel):
    """Aspect the marketplace itself grouped this review under (Amazon insights)."""

    aspect: str
    sentiment: Optional[str] = None


class ReviewClassification(BaseModel):
    sentiment: Sentiment
    is_complaint: bool
    noise: bool = Field(False, description="Off-topic, spam, or not about the product.")
    categories: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list, description="Short, specific frustrations.")
    severity: Optional[int] = Field(None, description="1=minor annoyance, 2=significant, 3=deal-breaker.")
    evidence_quote: Optional[str] = None
    evidence_verified: bool = Field(False, description="True if evidence_quote is a verbatim substring of the review.")
    model: str
    prompt_version: str


class Review(BaseModel):
    id: str
    product_id: str = Field(..., description="Product.id from the research set.")
    product_title: str
    source: Source
    listing_id: str = Field(..., description="ASIN / Google product_id the review was fetched for.")
    text: str = Field(..., description="Cleaned text used for analysis.")
    original_text: str = Field(..., description="Exactly as returned by SerpAPI.")
    title: Optional[str] = None
    rating: Optional[float] = None
    author: Optional[str] = None
    date: Optional[str] = None
    retailer: Optional[str] = Field(None, description="Where the review was written (Google aggregates stores).")
    truncated: bool = Field(False, description="Marketplace returned only a snippet.")
    marketplace_aspects: list[AspectTag] = Field(default_factory=list)
    url: str = Field(..., description="Review link, or product page if no per-review link exists.")
    citation: ReviewCitation
    classification: Optional[ReviewClassification] = None


class AspectInsight(BaseModel):
    """Marketplace-computed aspect stats (e.g. Amazon: 'Grip' 974 negative mentions)."""

    source: Source
    aspect: str
    sentiment: Optional[str] = None
    mentions_total: Optional[int] = None
    mentions_positive: Optional[int] = None
    mentions_negative: Optional[int] = None
    summary: Optional[str] = None
    citation: ReviewCitation


class RatingBreakdown(BaseModel):
    source: Source
    unit: Literal["percent", "count"]
    stars: dict[int, float]
    citation: ReviewCitation


class ProductReviews(BaseModel):
    product_id: str
    product_title: str
    product_url: str
    brand: Optional[str] = None
    rank: int
    sources_fetched: list[Source] = Field(default_factory=list)
    marketplace_summary: Optional[str] = None
    rating_breakdowns: list[RatingBreakdown] = Field(default_factory=list)
    aspects: list[AspectInsight] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ReviewIntelligence(BaseModel):
    query: str
    market: str
    source_run: Optional[str] = None
    created_at: datetime
    llm_model: Optional[str] = None
    products: list[ProductReviews]
    stats: dict[str, Any] = Field(default_factory=dict)
