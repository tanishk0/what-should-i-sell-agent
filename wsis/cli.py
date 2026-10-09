"""CLI entry point for Amazon Market-Gap Research Agent.

Usage:
    python -m wsis "sunglasses" [--market in] [--limit 20] [--with-reviews] [--review-limit 5] [--credit-budget 10]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import DEFAULT_MARKET, MARKETS, get_api_key
from .pipeline import build_competitor_set
from .report import build_final_report, render_markdown_report, render_terminal_report
from .reviews.clustering import cluster_complaints
from .reviews.pipeline import run_review_intelligence
from .serp_client import SerpClient


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(
        prog="wsis",
        description="Amazon Market-Gap Research Agent: Collect competitors, extract customer complaints, and generate evidence-backed market-gap reports.",
    )
    ap.add_argument("query", help="Product query/category on Amazon (e.g. 'sunglasses', 'lunch box')")
    ap.add_argument("--market", default=DEFAULT_MARKET, choices=list(MARKETS), help=f"Market code (default: {DEFAULT_MARKET})")
    ap.add_argument("--limit", type=int, default=20, help="Number of competitor products to collect.")
    ap.add_argument("--min-relevance", type=float, default=0.5, help="Minimum title relevance score.")
    ap.add_argument("--amazon-pages", type=int, default=1, help="Number of Amazon search pages to scrape.")
    ap.add_argument("--sources", default="amazon", help="Search engines (default: 'amazon').")
    ap.add_argument("--no-cache", action="store_true", help="Always hit SerpAPI live (bypass cache).")
    ap.add_argument("--offline", action="store_true", help="Use cached SerpAPI responses only.")
    ap.add_argument("--with-reviews", action="store_true", help="Analyze customer reviews to uncover market gaps.")
    ap.add_argument("--review-limit", type=int, default=5, help="Number of top competitors to fetch reviews for.")
    ap.add_argument("--max-reviews-per-product", type=int, default=6, help="Max reviews per competitor to send to LLM (default: 6).")
    ap.add_argument("--model", default=None, help="LLM model (default: nvidia/nemotron-3-ultra-550b-a55b).")
    ap.add_argument("--credit-budget", type=int, default=10, help="Max fresh SerpAPI credits to spend on reviews.")
    ap.add_argument("--out", help="Custom output JSON path.")
    ap.add_argument("--no-mongo", action="store_true", help="Skip saving to MongoDB even if MONGODB_URI is set.")
    args = ap.parse_args(argv)

    console = Console()
    client = SerpClient(
        None if args.offline else get_api_key(),
        use_cache=not args.no_cache,
        offline=args.offline,
    )

    # Step 1: Collect competitor products from Amazon
    with console.status(f"Searching Amazon for '{args.query}' in market {args.market.upper()}..."):
        result = build_competitor_set(
            args.query,
            client,
            market=args.market,
            limit=args.limit,
            min_relevance=args.min_relevance,
            sources=args.sources.split(","),
            amazon_pages=args.amazon_pages,
        )

    # Display initial competitors table
    table = Table(title=f"Competitors for '{result.query}' (Amazon {result.market.upper()}, {result.currency})")
    table.add_column("#", width=3)
    table.add_column("Title", overflow="fold")
    table.add_column("Price", width=10)
    table.add_column("Rating", width=8)
    table.add_column("Reviews", width=10)
    table.add_column("Score", width=8)

    for i, p in enumerate(result.products, 1):
        price = f"{p.price:.2f}" if p.price is not None else "-"
        if p.price_min is not None and p.price_max != p.price_min:
            price += f" ({p.price_min:.2f}-{p.price_max:.2f})"
        table.add_row(
            str(i),
            p.title[:75],
            price,
            f"{p.rating:.1f}" if p.rating else "-",
            f"{p.review_count:,}" if p.review_count else "-",
            f"{p.score:.3f}",
        )
    console.print(table)
    console.print(f"[bold]Search Stats:[/bold] {result.stats}\n")

    rev_intel = None
    prob_analysis = None
    final_report = None

    if args.with_reviews:
        # Step 2: Fetch and classify customer reviews
        with console.status("Starting review intelligence...", spinner="dots") as status:
            rev_intel = run_review_intelligence(
                result,
                client,
                competitor_limit=args.review_limit,
                credit_budget=args.credit_budget,
                max_reviews_per_product=args.max_reviews_per_product,
                llm_model=args.model,
                on_progress=lambda msg: status.update(f"[cyan]{msg}[/cyan]"),
            )

        # Step 3: Cluster complaints semantically with NVIDIA Nemotron & derive programmatic evidence
        with console.status("Clustering complaints into recurring problem themes & deriving evidence..."):
            prob_analysis = cluster_complaints(rev_intel, model=args.model)

        # Step 4: Build evidence-backed market gap report
        with console.status("Synthesizing evidence-backed market gap report..."):
            final_report = build_final_report(
                result,
                review_intel=rev_intel,
                prob_analysis=prob_analysis,
            )

        # Render terminal report
        console.print(render_terminal_report(final_report))

    # Persistence: Local file output (only if explicitly requested via --out)
    slug = re.sub(r"[^a-z0-9]+", "-", args.query.lower()).strip("-")
    run_timestamp = datetime.now()
    run_id = f"{slug}-{run_timestamp:%Y%m%d-%H%M%S}"

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if final_report and out.suffix.lower() == ".md":
            out.write_text(render_markdown_report(final_report), encoding="utf-8")
            console.print(f"[bold green]Saved market-gap markdown report ->[/bold green] {out}")
        elif final_report:
            out.write_text(final_report.model_dump_json(indent=2), encoding="utf-8")
            console.print(f"[bold green]Saved market-gap JSON report ->[/bold green] {out}")
        else:
            out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            console.print(f"[green]Saved {len(result.products)} products ->[/green] {out}")

    # Persistence: MongoDB (optional)
    if not args.no_mongo:
        try:
            from .db import MongoStorage
            storage = MongoStorage.from_env()
            if storage and storage.ping():
                storage.init_indexes()
                saved_id = storage.save_research_set(result, run_id=run_id)
                if rev_intel:
                    storage.save_review_intelligence(rev_intel, run_id=saved_id)
                if prob_analysis:
                    storage.save_problem_analysis(prob_analysis, run_id=saved_id)
                if final_report:
                    storage.save_final_report(final_report, run_id=saved_id)
                storage.close()
                console.print(f"[bold green]Saved to MongoDB database: '{storage.db_name}'[/bold green]")
        except Exception as e:
            console.print(f"[dim]MongoDB save skipped: {e}[/dim]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
