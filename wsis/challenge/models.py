"""Data models for Step 5 Agentic Challenge Loop."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class OpportunityHypothesis(BaseModel):
    """An empirical hypothesis to be stress-tested against the market."""

    id: str = Field(..., description="Unique hypothesis identifier (e.g. 'hyp_01').")
    opportunity_id: str = Field(..., description="Linked candidate opportunity ID.")
    title: str = Field(..., description="Product opportunity title.")
    problem_id: str = Field(..., description="Original problem cluster ID.")
    problem_name: str = Field(..., description="Name of the problem being solved.")
    claim: str = Field(
        ...,
        description="Falsifiable claim: e.g. 'Buyers widely experience X, creating a market gap for Y.'",
    )
    initial_confidence: float = Field(0.70, description="Initial confidence before adversarial search.")
    initial_score: float = Field(..., description="Starting opportunity priority score from Step 4.")
    challenge_queries: list[str] = Field(
        default_factory=list,
        description="Targeted adversarial search queries to execute on SerpAPI.",
    )


class EvidenceItem(BaseModel):
    """A piece of supporting or contradictory evidence uncovered during challenge searches."""

    type: str = Field(..., description="Evidence category (e.g. 'isolated_defect', 'widespread_defect', 'incumbent_preemption').")
    summary: str = Field(..., description="Concise finding headline.")
    detail: str = Field(..., description="Detailed explanation of the market finding.")
    evidence_quotes: list[str] = Field(default_factory=list, description="Verbatim buyer quotes.")
    affected_products: list[str] = Field(default_factory=list, description="IDs of products showing this pattern.")


class ChallengeEvaluation(BaseModel):
    """The result of challenging a single hypothesis through additional search & review analysis."""

    hypothesis_id: str
    opportunity_id: str
    title: str
    problem_name: str
    total_competitors_checked: int = Field(0, description="Total competitors checked across original + challenge cohorts.")
    competitors_with_complaint: int = Field(0, description="Number of competitors actually exhibiting this complaint.")
    prevalence_ratio: float = Field(0.0, description="Fraction of checked competitors exhibiting the problem.")
    verdict: Literal["STRENGTHENED", "CONFIRMED", "WEAKENED", "DOWNGRADED"] = Field(
        ...,
        description="Adversarial verdict on the hypothesis.",
    )
    initial_confidence: float
    final_confidence: float
    initial_score: float
    final_score: float
    adjustment_factor: float = Field(1.0, description="Score multiplier applied based on challenge evidence.")
    contradictory_evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence undermining the hypothesis (e.g. isolated defect, incumbent pre-emption).",
    )
    corroborating_evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence confirming the hypothesis across broad market competitors.",
    )
    agent_reasoning: str = Field(
        ...,
        description="The agent's adversarial reasoning explaining why it strengthened or downgraded the opportunity.",
    )
    recommendation: Literal["PURSUE_HIGH_CONVICTION", "PROCEED_WITH_CAUTION", "DE-PRIORITIZE", "ABANDON"] = Field(
        "PROCEED_WITH_CAUTION",
        description="Actionable strategic decision for the seller.",
    )


class FinalOpportunity(BaseModel):
    """A finalized product opportunity after surviving the adversarial challenge loop."""

    rank: int
    opportunity_id: str
    hypothesis_id: str
    title: str
    problem_name: str
    category: str
    improvement_type: str
    improvement_concept: str
    differentiation_angle: str
    verdict: Literal["STRENGTHENED", "CONFIRMED", "WEAKENED", "DOWNGRADED"]
    final_score: float
    confidence: float
    recommendation: Literal["PURSUE_HIGH_CONVICTION", "PROCEED_WITH_CAUTION", "DE-PRIORITIZE", "ABANDON"]
    competitor_prevalence: str = Field(..., description="e.g. '2/15 competitors (13.3%)'")
    agent_assessment: str = Field(..., description="Synthesis of adversarial findings.")
    supporting_evidence_quotes: list[str] = Field(default_factory=list)


class ChallengeLoopAnalysis(BaseModel):
    """Output of Step 5: complete record of the agentic challenge loop."""

    query: str
    market: str
    created_at: datetime
    hypotheses_evaluated: int
    evaluations: list[ChallengeEvaluation] = Field(default_factory=list)
    final_opportunities: list[FinalOpportunity] = Field(default_factory=list)
    method: str = "agentic_challenge_loop"
    stats: dict[str, Any] = Field(default_factory=dict)
