"""Models for Step 7: actionable, evidence-traceable product specification."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

EvidenceKind = Literal["review_complaint", "review_mention", "competitor_listing"]
SpecField = Literal["build", "must_have", "avoid", "target_price", "primary_customer"]


class EvidenceRef(BaseModel):
    """A pointer back to observed data collected in this run.

    Refs are always constructed from our own collected data (never from LLM text),
    so `quote` is a verbatim substring of the review when `quote_verified` is True.
    """

    kind: EvidenceKind
    review_id: Optional[str] = None
    product_id: str
    product_title: str
    quote: Optional[str] = Field(None, description="Verbatim text from the review.")
    quote_verified: bool = False
    data_point: Optional[str] = Field(None, description="Listing facts, e.g. 'price=$24.99, rating=4.5'.")
    rating: Optional[float] = None
    url: str
    serpapi_json_url: Optional[str] = None


class SpecItem(BaseModel):
    """One line of the product spec with its supporting evidence."""

    field: SpecField
    statement: str
    rationale: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    support_reviews: int = Field(0, description="Distinct reviews backing this line.")
    support_products: int = Field(0, description="Distinct competitor products backing this line.")
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Numeric claims in the statement not found in any cited evidence.",
    )

    @property
    def traceable(self) -> bool:
        return bool(self.evidence)


class DroppedItem(BaseModel):
    field: SpecField
    statement: str
    reason: str


class ProductSpec(BaseModel):
    """Output of Step 7."""

    query: str
    market: str
    currency: str
    opportunity_id: str
    opportunity_title: str
    verdict: str
    confidence: float
    build: SpecItem
    must_have: list[SpecItem] = Field(default_factory=list)
    avoid: list[SpecItem] = Field(default_factory=list)
    target_price: SpecItem
    primary_customer: SpecItem
    dropped: list[DroppedItem] = Field(default_factory=list, description="Lines removed for lacking evidence.")
    caveats: list[str] = Field(default_factory=list)
    created_at: datetime
    method: str = "heuristic"
    stats: dict[str, Any] = Field(default_factory=dict)

    def all_items(self) -> list[SpecItem]:
        return [self.build, *self.must_have, *self.avoid, self.target_price, self.primary_customer]
