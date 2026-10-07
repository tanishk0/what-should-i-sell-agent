"""Data models for Step 6 Competitor Assessment and Market Gap Analysis."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CompetitorProfile(BaseModel):
    """Profile of an individual competitor for matrix comparison."""

    id: str = Field(..., description="Product ID or ASIN.")
    name: str = Field(..., description="Short, clean product title / brand name.")
    price_display: str = Field(..., description="Formatted price with currency symbol, e.g. '₹699' or '$24.99'.")
    price: Optional[float] = Field(None, description="Raw numeric price value.")
    currency: Optional[str] = Field("USD", description="Currency code (USD, INR, etc.).")
    rating: Optional[float] = Field(None, description="Star rating (e.g. 4.2).")
    review_count: Optional[int] = Field(None, description="Number of customer reviews.")
    main_strength: str = Field(
        ...,
        description="Core strength or primary reason buyers choose this product (e.g. 'Compact', 'Durable', 'Cheap').",
    )
    problem: str = Field(
        ...,
        description="Primary defect, limitation, or complaint (e.g. 'Leaks', 'Bulky', 'Poor seal', 'Slippery').",
    )
    url: str = Field(..., description="Product link.")


class MarketGapAnalysis(BaseModel):
    """Strategic answer to: Where is the gap?"""

    where_is_the_gap: str = Field(
        ...,
        description="Comprehensive answer to: Where is the gap in the market?",
    )
    unmet_need_summary: str = Field(
        ...,
        description="Core customer compromise that no existing competitor resolves.",
    )
    price_gap_range: str = Field(
        ...,
        description="Recommended price positioning window (e.g. '₹749 - ₹849' or '$28 - $34').",
    )
    tradeoff_to_break: str = Field(
        ...,
        description="The false dichotomy buyers are currently forced to accept (e.g. 'Compact vs Leakproof').",
    )
    winning_positioning: str = Field(
        ...,
        description="Clear positioning statement for the new entrant to win market share.",
    )


class CompetitorAssessment(BaseModel):
    """Output of Step 6: Competitor assessment matrix and strategic gap analysis."""

    query: str
    market: str
    opportunity_id: str
    opportunity_title: str
    target_problem: str
    competitors: list[CompetitorProfile] = Field(default_factory=list)
    gap_analysis: MarketGapAnalysis
    created_at: datetime
    method: str = "gemini_llm"
    stats: dict[str, Any] = Field(default_factory=dict)
