"""Models for recurring problem clusters."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .models import ReviewCitation


class ComplaintEvidence(BaseModel):
    """Citation & exact text for a complaint in a problem cluster."""

    review_id: str
    product_id: str
    product_title: str
    rating: Optional[float] = None
    original_text: str
    evidence_quote: Optional[str] = None
    evidence_verified: bool = False
    url: str
    citation: ReviewCitation


class ProblemCluster(BaseModel):
    """A recurring buyer problem aggregated from multiple competitor reviews."""

    id: str
    name: str = Field(..., description="Concise, actionable problem name (e.g. 'Slippery when wet/sweaty').")
    category: str = Field(..., description="High-level category (e.g. 'performance', 'durability').")
    description: str = Field(..., description="Detailed explanation of what buyers experience and why it frustrates them.")
    affected_products: list[str] = Field(default_factory=list, description="List of product IDs impacted.")
    affected_product_count: int = 0
    total_complaints: int = 0
    avg_severity: float = Field(0.0, description="Mean severity rating (1.0 to 3.0).")
    frequency_score: float = Field(0.0, description="Share of complaints belonging to this cluster.")
    opportunity_score: float = Field(0.0, description="Combined index of frequency, severity, and product breadth.")
    sample_evidence: list[ComplaintEvidence] = Field(default_factory=list, description="Verbatim cited evidence backing this problem.")


class ProblemAnalysis(BaseModel):
    """Output of Step 3: clustered recurring problems with evidence citations."""

    query: str
    market: str
    created_at: datetime
    total_reviews_analyzed: int
    total_complaints_analyzed: int
    clusters: list[ProblemCluster] = Field(default_factory=list)
    method: str = "llm_cluster"
    stats: dict[str, Any] = Field(default_factory=dict)
