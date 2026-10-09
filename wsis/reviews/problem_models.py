"""Models for recurring problem clusters backed by programmatic evidence."""
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
    """A recurring buyer problem aggregated from multiple competitor reviews.

    Evidence is the source of truth: counts are strictly derived from supporting arrays.
    """

    id: str
    problem: str = Field(..., description="Actionable name/theme of the customer problem.")
    category: str = Field("other", description="High-level category (e.g. durability, performance).")
    description: str = Field(..., description="Detailed explanation of the root buyer pain point.")

    # Core evidence arrays (Source of Truth)
    supporting_reviews: list[ComplaintEvidence] = Field(
        default_factory=list,
        description="Reviews explicitly classified and assigned as evidence for this problem.",
    )
    supporting_products: list[str] = Field(
        default_factory=list,
        description="IDs of products that suffer from this problem.",
    )
    unaffected_products: list[str] = Field(
        default_factory=list,
        description="IDs of analyzed competitor products where this complaint was not observed in sampled reviews.",
    )

    # Programmatically computed metrics
    review_count: int = Field(0, description="Derived programmatically from len(supporting_reviews).")
    product_count: int = Field(0, description="Derived programmatically from len(supporting_products).")
    product_prevalence_pct: float = Field(0.0, description="Percentage of analyzed products affected.")
    avg_severity: float = Field(0.0, description="Mean severity rating (1.0 to 3.0) of supporting reviews.")
    is_widespread_gap: bool = Field(False, description="True if problem is cross-checked across at least 3 competitors with >=50% prevalence.")

    @property
    def classification_label(self) -> str:
        """Neutral evidence-based classification label (Requirement 7)."""
        if self.product_count >= 3 and self.product_prevalence_pct >= 50.0:
            return "Widespread Market Gap"
        elif self.product_count >= 2:
            return "Multi-Competitor Pattern"
        else:
            return "Isolated Defect"

    @property
    def name(self) -> str:
        return self.problem

    @property
    def total_complaints(self) -> int:
        return self.review_count

    @property
    def affected_products(self) -> list[str]:
        return self.supporting_products

    @property
    def affected_product_count(self) -> int:
        return self.product_count

    @property
    def sample_evidence(self) -> list[ComplaintEvidence]:
        return self.supporting_reviews


class ProblemAnalysis(BaseModel):
    """Clustered recurring problems with programmatic evidence counts and counter-evidence."""

    query: str
    market: str
    created_at: datetime
    total_reviews_analyzed: int
    total_complaints_analyzed: int
    clusters: list[ProblemCluster] = Field(default_factory=list)
    method: str = "gemini_clustering"
    stats: dict[str, Any] = Field(default_factory=dict)
