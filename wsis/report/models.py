"""Data models for Evidence-Backed Market-Gap Research Report."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..reviews.problem_models import ProblemCluster


class CompetitorRow(BaseModel):
    """Competitor benchmark comparison row."""

    rank: int
    title: str
    price: str
    rating: str
    review_count: str
    complaints_count: int
    url: str


class CitationItem(BaseModel):
    """Verifiable citation linking back to raw SerpAPI data."""

    id: str
    kind: Literal["review", "product", "search"]
    label: str
    source: str
    url: str


class MarketGapReport(BaseModel):
    """The evidence-backed Amazon market-gap research report.

    Zero product inventions. Pure evidence-derived competitor problems, counts, citations, and counter-evidence.
    """

    query: str
    market: str
    currency: str
    created_at: datetime

    # Quantitative Scope (Programmatic)
    total_competitors_found: int
    total_competitors_analyzed: int
    total_reviews_analyzed: int
    total_complaints_found: int

    # Executive Synthesis
    summary: str
    has_insufficient_evidence: bool = False

    # Core Evidence-Derived Data
    competitors: list[CompetitorRow] = Field(default_factory=list)
    problems: list[ProblemCluster] = Field(default_factory=list)
    citations: list[CitationItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
