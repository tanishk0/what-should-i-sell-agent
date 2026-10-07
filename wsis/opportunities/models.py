"""Data models for candidate product opportunities (Step 4)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CandidateOpportunity(BaseModel):
    """A concrete product improvement opportunity derived from a recurring buyer problem."""

    id: str = Field(..., description="Unique opportunity identifier (e.g. 'opp_01').")
    title: str = Field(
        ...,
        description="Punchy, actionable title for the product improvement / innovation concept.",
    )
    problem_id: str = Field(..., description="ID of the problem cluster this opportunity solves.")
    problem_name: str = Field(..., description="Name of the problem cluster being addressed.")
    category: str = Field(
        ...,
        description="High-level category (e.g. 'performance', 'durability', 'materials_safety').",
    )
    improvement_type: str = Field(
        ...,
        description="Type of improvement (e.g. 'material_upgrade', 'mechanical_redesign', 'feature_addition').",
    )
    improvement_concept: str = Field(
        ...,
        description="Detailed answer to: What product improvement could directly solve this problem?",
    )
    differentiation_angle: str = Field(
        ...,
        description="Value proposition explaining how this beats incumbent competitors in marketing & positioning.",
    )
    implementation_feasibility: str = Field(
        "medium",
        description="Feasibility level: 'high' (easy/standard manufacturing), 'medium', or 'low' (custom R&D).",
    )
    expected_impact: str = Field(
        ...,
        description="Expected reduction in negative reviews, return rates, and increase in buyer satisfaction.",
    )
    target_price_impact: str = Field(
        "cost_neutral",
        description="Price positioning impact: 'cost_neutral', 'minor_premium', or 'premium_tier'.",
    )
    priority_score: float = Field(
        0.0,
        description="Priority index combining problem opportunity score and implementation feasibility.",
    )
    affected_product_count: int = Field(
        0,
        description="Number of competing products impacted by the underlying problem.",
    )
    supporting_evidence_quotes: list[str] = Field(
        default_factory=list,
        description="Verbatim buyer quotes illustrating the pain point this improvement solves.",
    )


class OpportunityAnalysis(BaseModel):
    """Output of Step 4: generated candidate opportunities addressing major problems."""

    query: str
    market: str
    created_at: datetime
    total_problems_evaluated: int
    opportunities: list[CandidateOpportunity] = Field(default_factory=list)
    method: str = "gemini_llm"
    stats: dict[str, Any] = Field(default_factory=dict)
