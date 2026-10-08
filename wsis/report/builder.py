"""Builder and formatting logic for Evidence-Backed Market-Gap Research Report."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..reviews.models import ReviewIntelligence
from ..reviews.problem_models import ProblemAnalysis, ProblemCluster
from ..schema import ResearchSet
from .models import CitationItem, CompetitorRow, MarketGapReport

logger = logging.getLogger(__name__)

CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "GBP": "£",
    "EUR": "€",
    "JPY": "¥",
    "CAD": "CA$",
    "AUD": "A$",
}


def format_price(price: Optional[float], currency: Optional[str] = "INR") -> str:
    """Format numeric price with appropriate currency symbol (e.g. ₹699, $24.99)."""
    if price is None:
        return "-"
    curr = (currency or "INR").upper()
    symbol = CURRENCY_SYMBOLS.get(curr, f"{curr} ")
    if curr in ("INR", "JPY") or price.is_integer():
        return f"{symbol}{int(price)}"
    return f"{symbol}{price:.2f}"


def clean_brand_name(title: str) -> str:
    """Extract a concise readable product name from a long marketplace title."""
    parts = title.split()
    if len(parts) <= 4:
        return title
    clean = re.split(r"[,|\-–/:]", title)[0].strip()
    words = clean.split()
    if len(words) > 5:
        return " ".join(words[:5])
    return clean or " ".join(parts[:5])


def build_final_report(
    research_set: ResearchSet,
    review_intel: Optional[ReviewIntelligence] = None,
    prob_analysis: Optional[ProblemAnalysis] = None,
) -> MarketGapReport:
    """Synthesize pipeline data into an evidence-backed market gap report.

    Derives all counts programmatically from actual review objects.
    """
    total_found = len(research_set.products)
    total_analyzed = len(review_intel.products) if review_intel else 0
    total_reviews = prob_analysis.total_reviews_analyzed if prob_analysis else (
        review_intel.total_reviews_analyzed if review_intel else 0
    )
    total_complaints = prob_analysis.total_complaints_analyzed if prob_analysis else 0

    problems = prob_analysis.clusters if prob_analysis else []
    has_insufficient = len(problems) == 0 or total_complaints == 0

    # Build competitor rows
    competitors: list[CompetitorRow] = []
    prod_complaint_map: dict[str, int] = {}
    if review_intel:
        for pr in review_intel.products:
            c_count = sum(1 for r in pr.reviews if r.classification and r.classification.is_complaint)
            prod_complaint_map[pr.product_id] = c_count

    for rank, p in enumerate(research_set.products[:total_analyzed], start=1):
        price_val = p.price or p.price_min
        price_str = format_price(price_val, research_set.currency)
        r_str = f"{p.rating:.1f}" if p.rating else "-"
        rc_str = f"{p.review_count:,}" if p.review_count else "-"
        complaints_count = prod_complaint_map.get(p.id, 0)

        competitors.append(
            CompetitorRow(
                rank=rank,
                title=clean_brand_name(p.title),
                price=price_str,
                rating=r_str,
                review_count=rc_str,
                complaints_count=complaints_count,
                url=p.url,
            )
        )

    # Build executive synthesis summary
    query_str = research_set.query.strip().title()
    market_str = research_set.market.upper()
    if has_insufficient:
        summary = (
            f"Insufficient customer complaint evidence found for '{query_str}' on Amazon {market_str}. "
            f"Across {total_analyzed} competitor listings and {total_reviews} reviews analyzed, no recurring "
            f"functional defects or systematic buyer dissatisfaction themes were detected."
        )
    else:
        top_prob = problems[0]
        widespread_count = sum(1 for p in problems if p.is_widespread_gap)
        summary = (
            f"Analysis of {total_analyzed} competitor products and {total_reviews} customer reviews on Amazon {market_str} "
            f"identified {len(problems)} customer problem clusters for '{query_str}'. "
            f"{widespread_count} problem(s) represent widespread market gaps affecting multiple competitors. "
            f"The primary gap is '{top_prob.problem}', supported by {top_prob.review_count} verified buyer complaints "
            f"across {top_prob.product_count} of {total_analyzed} competing products ({top_prob.product_prevalence_pct}% market prevalence)."
        )

    # Build citations list
    citations: list[CitationItem] = []
    for s in research_set.searches:
        if s.serpapi_json_url:
            citations.append(
                CitationItem(
                    id=s.search_id or f"search_{len(citations)+1}",
                    kind="search",
                    label=f"SerpAPI {s.engine} search query: '{research_set.query}'",
                    source="serpapi",
                    url=s.serpapi_json_url,
                )
            )

    for p in research_set.products[:total_analyzed]:
        citations.append(
            CitationItem(
                id=f"prod_{p.id}",
                kind="product",
                label=clean_brand_name(p.title),
                source=p.sources[0] if p.sources else "amazon",
                url=p.url,
            )
        )

    return MarketGapReport(
        query=research_set.query,
        market=research_set.market,
        currency=research_set.currency,
        created_at=datetime.now(timezone.utc),
        total_competitors_found=total_found,
        total_competitors_analyzed=total_analyzed,
        total_reviews_analyzed=total_reviews,
        total_complaints_found=total_complaints,
        summary=summary,
        has_insufficient_evidence=has_insufficient,
        competitors=competitors,
        problems=problems,
        citations=citations,
        metadata={
            "run_at": datetime.now(timezone.utc).isoformat(),
            "sources": research_set.stats.get("listings_normalized", {}),
        },
    )


def render_terminal_report(report: MarketGapReport) -> str:
    """Render the evidence-backed market gap report using rich formatting."""
    console = Console(width=100, record=True)

    # 1. Header & Summary Panel
    header_title = f"[bold cyan]AMAZON MARKET-GAP RESEARCH REPORT: {report.query.upper()} ({report.market.upper()})[/bold cyan]"
    summary_text = (
        f"[bold]Scope:[/bold] {report.total_competitors_analyzed} competitors analyzed | "
        f"{report.total_reviews_analyzed} customer reviews | "
        f"{report.total_complaints_found} verified complaints\n\n"
        f"{report.summary}"
    )
    console.print(Panel(summary_text, title=header_title, expand=False))
    console.print()

    # 2. Competitors Benchmark Table
    if report.competitors:
        comp_table = Table(title="[bold]Competitor Benchmark Landscape[/bold]")
        comp_table.add_column("#", width=3)
        comp_table.add_column("Competitor", style="cyan", overflow="fold")
        comp_table.add_column("Price", width=10)
        comp_table.add_column("Rating", width=8)
        comp_table.add_column("Reviews", width=10)
        comp_table.add_column("Verified Complaints", width=20)

        for c in report.competitors:
            comp_table.add_row(
                str(c.rank),
                c.title,
                c.price,
                c.rating,
                c.review_count,
                str(c.complaints_count),
            )
        console.print(comp_table)
        console.print()

    # 3. Market Gaps & Recurring Customer Problems
    if report.problems:
        console.print("[bold yellow]════════════════════════════════════════════════════════════════════════════════════════════════════[/bold yellow]")
        console.print("[bold yellow]  IDENTIFIED CUSTOMER PROBLEMS & MARKET GAPS (EVIDENCE-BACKED)[/bold yellow]")
        console.print("[bold yellow]════════════════════════════════════════════════════════════════════════════════════════════════════[/bold yellow]")
        console.print()

        for idx, prob in enumerate(report.problems, start=1):
            gap_badge = (
                "[bold green][WIDESPREAD MARKET GAP][/bold green]"
                if prob.is_widespread_gap
                else "[yellow][ISOLATED DEFECT][/yellow]"
            )
            prob_title = f"[bold white]Problem {idx}: {prob.problem}[/bold white]  {gap_badge}"
            
            lines = [
                f"[bold]Category:[/bold] {prob.category.replace('_', ' ').title()}",
                f"[bold]Evidence:[/bold] [bold cyan]{prob.review_count}[/bold cyan] buyer complaints across [bold cyan]{prob.product_count}[/bold cyan] of {report.total_competitors_analyzed} competitors ({prob.product_prevalence_pct}% market prevalence)",
                f"[bold]Severity:[/bold] {prob.avg_severity:.1f}/3.0",
                f"[bold]Root Pain Point:[/bold] {prob.description}",
            ]

            # Verbatim Quotes
            if prob.supporting_reviews:
                lines.append("\n[bold]Verbatim Customer Evidence Quotes:[/bold]")
                for ev in prob.supporting_reviews[:3]:
                    quote_txt = ev.evidence_quote or ev.original_text[:140]
                    verified_mark = " [green]✓ verbatim[/green]" if ev.evidence_verified else ""
                    rating_mark = f" ({ev.rating}★)" if ev.rating else ""
                    lines.append(f'  • "{quote_txt}"{rating_mark} — [dim]{clean_brand_name(ev.product_title)}[/dim]{verified_mark}')

            # Counter-Evidence / Competitor Contrast
            if prob.unaffected_products:
                unaffected_names = []
                for pid in prob.unaffected_products:
                    match = next((c.title for c in report.competitors if pid in c.url or c.title in pid), pid)
                    unaffected_names.append(match)
                lines.append(
                    f"\n[bold]Counter-Evidence (Competitor Contrast):[/bold] "
                    f"This complaint was NOT reported on {len(prob.unaffected_products)} competitors in the sample: "
                    f"[dim]{', '.join(unaffected_names[:3])}[/dim]"
                )

            console.print(Panel("\n".join(lines), title=prob_title, expand=False))
            console.print()
    else:
        console.print("[bold yellow]No customer problem clusters identified.[/bold yellow]\n")

    return console.export_text()


def render_markdown_report(report: MarketGapReport) -> str:
    """Render the evidence-backed market gap report as GitHub-flavored Markdown."""
    lines = [
        f"# Amazon Market-Gap Research Report: {report.query.title()}",
        "",
        f"**Market:** Amazon {report.market.upper()} ({report.currency})  ",
        f"**Generated:** {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Scope:** {report.total_competitors_analyzed} competitors analyzed | {report.total_reviews_analyzed} customer reviews | {report.total_complaints_found} verified complaints  ",
        "",
        "## Executive Summary",
        "",
        report.summary,
        "",
        "## Competitor Benchmark Landscape",
        "",
        "| # | Competitor | Price | Rating | Reviews | Verified Complaints |",
        "|---|---|---|---|---|---|",
    ]

    for c in report.competitors:
        lines.append(f"| {c.rank} | [{c.title}]({c.url}) | {c.price} | {c.rating} | {c.review_count} | {c.complaints_count} |")

    lines.extend([
        "",
        "## Identified Customer Problems & Market Gaps",
        "",
    ])

    if not report.problems:
        lines.append("_No customer problem clusters identified._\n")
    else:
        for idx, prob in enumerate(report.problems, start=1):
            badge = "**[WIDESPREAD MARKET GAP]**" if prob.is_widespread_gap else "**[ISOLATED DEFECT]**"
            lines.extend([
                f"### {idx}. {prob.problem} {badge}",
                "",
                f"- **Category:** {prob.category.replace('_', ' ').title()}",
                f"- **Evidence Counts:** {prob.review_count} buyer complaints across {prob.product_count}/{report.total_competitors_analyzed} competitors ({prob.product_prevalence_pct}% prevalence)",
                f"- **Average Severity:** {prob.avg_severity:.1f} / 3.0",
                f"- **Root Pain Point:** {prob.description}",
                "",
                "#### Verbatim Customer Evidence Quotes",
                "",
            ])

            for ev in prob.supporting_reviews[:4]:
                quote_txt = ev.evidence_quote or ev.original_text[:160]
                rating_str = f"({ev.rating}★) " if ev.rating else ""
                verified_str = " *(verified verbatim)*" if ev.evidence_verified else ""
                lines.append(f"> \"{quote_txt}\"  \n> — {rating_str}[{clean_brand_name(ev.product_title)}]({ev.url}){verified_str}")
                lines.append("")

            if prob.unaffected_products:
                lines.extend([
                    "#### Counter-Evidence (Competitor Contrast)",
                    "",
                    f"This complaint did not appear in {len(prob.unaffected_products)} analyzed competitor products in the sample, indicating this defect is not universal across all alternatives.",
                    "",
                ])

    lines.extend([
        "## Verifiable Citations",
        "",
    ])
    for c in report.citations[:10]:
        lines.append(f"- [{c.label}]({c.url}) ({c.source})")
    lines.append("")

    return "\n".join(lines)
