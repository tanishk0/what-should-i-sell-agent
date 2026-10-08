"""Evidence-Backed Market-Gap Research Report package."""
from .builder import (
    build_final_report,
    clean_brand_name,
    format_price,
    render_markdown_report,
    render_terminal_report,
)
from .models import (
    CitationItem,
    CompetitorRow,
    MarketGapReport,
)

__all__ = [
    "MarketGapReport",
    "CompetitorRow",
    "CitationItem",
    "build_final_report",
    "render_terminal_report",
    "render_markdown_report",
    "format_price",
    "clean_brand_name",
]
