"""Candidate product opportunities package (Step 4)."""
from .generator import generate_candidate_opportunities
from .models import CandidateOpportunity, OpportunityAnalysis

__all__ = [
    "CandidateOpportunity",
    "OpportunityAnalysis",
    "generate_candidate_opportunities",
]
