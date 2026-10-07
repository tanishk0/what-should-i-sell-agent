"""Data models for Step 8 Evidence-Backed Final Opportunity Report."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EvidenceStats(BaseModel):
    """Aggregate quantitative evidence backing the opportunity."""

    unique_reviews: int = Field(0, description="Number of distinct buyer reviews documenting this problem.")
    competing_products: int = Field(0, description="Number of competing products exhibiting this problem.")
    review_share_pct: float = Field(0.0, description="Percentage of analyzed reviews mentioning the problem.")
    total_reviews_analyzed: int = Field(0, description="Total reviews analyzed in the category.")
    total_products_analyzed: int = Field(0, description="Total competitor products analyzed.")


class ReportQuote(BaseModel):
    """Verbatim customer review quote citing real experience."""

    review_id: str = Field(..., description="Unique review ID or citation key.")
    product_title: str = Field(..., description="Short product title.")
    rating: Optional[float] = Field(None, description="Star rating.")
    text: str = Field(..., description="Verbatim quote from the review.")
    url: Optional[str] = Field(None, description="Source URL.")


class CompetitorRow(BaseModel):
    """Competitor benchmark comparison row."""

    name: str = Field(..., description="Brand / Product short name.")
    price: str = Field(..., description="Formatted price (e.g. ₹699, $24.99).")
    rating: str = Field(..., description="Formatted rating (e.g. 4.2).")
    main_strength: str = Field(..., description="Primary strength (e.g. Compact, Durable).")
    problem: str = Field(..., description="Primary defect or complaint (e.g. Leaks, Bulky).")


class CitationItem(BaseModel):
    """Verifiable citation linking back to raw SerpAPI data."""

    id: str
    kind: Literal["review", "product"]
    label: str
    source: str
    url: str


class FinalOpportunityReport(BaseModel):
    """The comprehensive Step 8 final opportunity report."""

    query: str
    market: str
    created_at: datetime
    title: str = Field(..., description="Opportunity headline (e.g. COMPACT LEAKPROOF LUNCH BOX).")
    confidence: Literal["HIGH", "MODERATE", "LOW"] = Field("HIGH", description="Confidence level.")
    why_this_opportunity: str = Field(..., description="2-3 sentence strategic rationale.")
    customer_problem: str = Field(..., description="Specific buyer pain point.")
    evidence_stats: EvidenceStats
    review_quotes: list[ReportQuote] = Field(default_factory=list)
    product_gap: str = Field(..., description="Description of the unmet market compromise.")
    what_to_build: list[str] = Field(default_factory=list, description="List of positive build specifications.")
    what_to_avoid: list[str] = Field(default_factory=list, description="List of competitor failure modes to avoid.")
    target_price: str = Field(..., description="Recommended target price window.")
    primary_customer: Optional[str] = Field(None, description="Target customer segment.")
    competitors: list[CompetitorRow] = Field(default_factory=list)
    evidence_citations: list[CitationItem] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list, description="Adversarial risks and weak points.")
    metadata: dict[str, Any] = Field(default_factory=dict)
