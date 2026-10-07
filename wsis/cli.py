"""CLI: python -m wsis "yoga mat" [--market us] [--limit 30]"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import MARKETS, RUNS_DIR, get_api_key
from .pipeline import build_competitor_set
from .serp_client import SerpClient


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="wsis", description="Collect a clean, cited competitor set.")
    ap.add_argument("query", help="Product category, e.g. 'yoga mat'")
    ap.add_argument("--market", default="us", choices=list(MARKETS))
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--min-relevance", type=float, default=0.5)
    ap.add_argument("--amazon-pages", type=int, default=1)
    ap.add_argument("--sources", default="amazon,google_shopping")
    ap.add_argument("--no-cache", action="store_true", help="Always hit SerpAPI.")
    ap.add_argument("--offline", action="store_true", help="Use cached responses only.")
    ap.add_argument("--out", help="Output JSON path (default: data/runs/<query>-<ts>.json)")
    args = ap.parse_args(argv)

    console = Console()
    client = SerpClient(
        None if args.offline else get_api_key(), use_cache=not args.no_cache, offline=args.offline
    )
    with console.status(f"Researching '{args.query}'..."):
        result = build_competitor_set(
            args.query,
            client,
            market=args.market,
            limit=args.limit,
            min_relevance=args.min_relevance,
            sources=args.sources.split(","),
            amazon_pages=args.amazon_pages,
        )

    table = Table(title=f"Competitors for '{result.query}' ({result.market.upper()}, {result.currency})")
    for col in ("#", "Title", "Price", "Rating", "Reviews", "Sources", "Score"):
        table.add_column(col, overflow="fold")
    for i, p in enumerate(result.products, 1):
        price = f"{p.price:.2f}" if p.price is not None else "-"
        if p.price_min is not None and p.price_max != p.price_min:
            price += f" ({p.price_min:.2f}-{p.price_max:.2f})"
        table.add_row(
            str(i),
            p.title[:70],
            price,
            f"{p.rating:.1f}" if p.rating else "-",
            f"{p.review_count:,}" if p.review_count else "-",
            "+".join("AMZ" if s == "amazon" else "GS" for s in p.sources)
            + (" (ad)" if p.sponsored_only else ""),
            f"{p.score:.3f}",
        )
    console.print(table)
    console.print(f"[bold]Stats:[/bold] {result.stats}")
    for s in result.searches:
        console.print(f"[dim]Source {s.engine}: {s.serpapi_json_url} (cached={s.from_cache})[/dim]")

    slug = re.sub(r"[^a-z0-9]+", "-", args.query.lower()).strip("-")
    out = Path(args.out) if args.out else RUNS_DIR / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]Saved {len(result.products)} products ->[/green] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
