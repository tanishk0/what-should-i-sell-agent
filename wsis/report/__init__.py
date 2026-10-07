"""Step 8 Evidence-Backed Final Opportunity Report package."""
from .builder import (
    build_final_report,
    render_markdown_report,
    render_terminal_report,
)
from .models import (
    CitationItem,
    CompetitorRow,
    EvidenceStats,
    FinalOpportunityReport,
    ReportQuote,
)

__all__ = [
    "FinalOpportunityReport",
    "EvidenceStats",
    "ReportQuote",
    "CompetitorRow",
    "CitationItem",
    "build_final_report",
    "render_terminal_report",
    "render_markdown_report",
]
