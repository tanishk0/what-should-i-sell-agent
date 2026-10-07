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
    ap.add_argument("--with-reviews", action="store_true", help="Run review intelligence on top competitors.")
    ap.add_argument("--review-limit", type=int, default=5, help="Number of competitors to fetch reviews for.")
    ap.add_argument("--credit-budget", type=int, default=10, help="Max fresh SerpAPI credits to spend on reviews.")
    ap.add_argument("--max-opportunities", type=int, default=10, help="Max candidate opportunities to generate.")
    ap.add_argument("--skip-challenge", action="store_true", help="Skip Step 5 adversarial challenge loop.")
    ap.add_argument("--out", help="Output JSON path (default: data/runs/<query>-<ts>.json)")
    ap.add_argument("--no-mongo", action="store_true", help="Skip saving results to MongoDB even if MONGODB_URI is set.")
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

    rev_intel = None
    prob_analysis = None
    opp_analysis = None
    challenge_analysis = None
    assessment = None
    if args.with_reviews:
        from .reviews.pipeline import run_review_intelligence
        with console.status(f"Analyzing reviews for top {args.review_limit} competitors (credit budget: {args.credit_budget})..."):
            rev_intel = run_review_intelligence(
                result,
                client,
                competitor_limit=args.review_limit,
                credit_budget=args.credit_budget,
            )

        rev_table = Table(title=f"Review Intelligence ({rev_intel.llm_model})")
        rev_table.add_column("Rank", width=4)
        rev_table.add_column("Product", overflow="fold")
        rev_table.add_column("Reviews", width=8)
        rev_table.add_column("Complaints", width=10)
        rev_table.add_column("Key Frustrations / Buyer Dislikes", overflow="fold")

        for pr in rev_intel.products:
            complaints = [r for r in pr.reviews if r.classification and r.classification.is_complaint]
            issues = []
            for r in complaints:
                issues.extend(r.classification.issues)
            top_issues = list(dict.fromkeys(issues))[:3]
            issues_str = "; ".join(top_issues) if top_issues else "No major frustrations detected"
            rev_table.add_row(
                str(pr.rank),
                pr.product_title[:60],
                str(len(pr.reviews)),
                str(len(complaints)),
                issues_str,
            )
        console.print(rev_table)
        console.print(f"[bold]Review Intelligence Stats:[/bold] {rev_intel.stats}")

        # Step 3: Discover recurring problems (Clustering)
        from .reviews.clustering import cluster_complaints
        with console.status("Clustering complaints into recurring problem themes..."):
            prob_analysis = cluster_complaints(rev_intel)

        prob_table = Table(title=f"Recurring Problem Clusters ({prob_analysis.method})")
        prob_table.add_column("#", width=3)
        prob_table.add_column("Problem Theme", style="bold yellow", overflow="fold")
        prob_table.add_column("Category", width=16)
        prob_table.add_column("Complaints", width=10)
        prob_table.add_column("Breadth", width=8)
        prob_table.add_column("Avg Sev", width=8)
        prob_table.add_column("Opportunity", width=12)

        for i, cluster in enumerate(prob_analysis.clusters, start=1):
            prob_table.add_row(
                str(i),
                cluster.name,
                cluster.category,
                str(cluster.total_complaints),
                f"{cluster.affected_product_count} prods",
                f"{cluster.avg_severity:.1f}/3",
                f"{cluster.opportunity_score:.3f}",
            )
        console.print(prob_table)
        console.print(f"[bold]Clustering Stats:[/bold] {prob_analysis.stats}")

        # Step 4: Generate candidate opportunities
        from .opportunities import generate_candidate_opportunities
        with console.status("Generating candidate product opportunities from major problems..."):
            opp_analysis = generate_candidate_opportunities(
                prob_analysis,
                max_problems=args.max_opportunities,
            )

        opp_table = Table(title=f"Candidate Product Opportunities ({opp_analysis.method})")
        opp_table.add_column("#", width=3)
        opp_table.add_column("Product Opportunity / Improvement", style="bold green", overflow="fold")
        opp_table.add_column("Solves Problem", style="yellow", overflow="fold")
        opp_table.add_column("Type", width=18)
        opp_table.add_column("Feasibility", width=12)
        opp_table.add_column("Price Impact", width=14)
        opp_table.add_column("Priority", width=10)

        for i, opp in enumerate(opp_analysis.opportunities, start=1):
            opp_table.add_row(
                str(i),
                opp.title,
                opp.problem_name,
                opp.improvement_type.replace("_", " ").title(),
                opp.implementation_feasibility.capitalize(),
                opp.target_price_impact.replace("_", " ").title(),
                f"{opp.priority_score:.3f}",
            )
        console.print(opp_table)
        console.print(f"[bold]Opportunity Generation Stats:[/bold] {opp_analysis.stats}")

        # Step 5: Agentic Challenge Loop
        if not args.skip_challenge and opp_analysis:
            from .challenge import run_challenge_loop
            with console.status("Executing agentic challenge loop (stress-testing hypotheses)..."):
                challenge_analysis = run_challenge_loop(
                    result,
                    rev_intel,
                    prob_analysis,
                    opp_analysis,
                    serp_client=client,
                    max_hypotheses=args.max_opportunities,
                )

            chal_table = Table(title=f"Final Validated Opportunities ({challenge_analysis.method})")
            chal_table.add_column("Rank", width=4)
            chal_table.add_column("Product Opportunity", style="bold green", overflow="fold")
            chal_table.add_column("Solves Problem", overflow="fold")
            chal_table.add_column("Breadth / Prevalence", width=22)
            chal_table.add_column("Verdict", width=14)
            chal_table.add_column("Final Score", width=11)
            chal_table.add_column("Recommendation", width=22)

            for opp in challenge_analysis.final_opportunities:
                verdict_style = (
                    "bold green" if opp.verdict == "STRENGTHENED"
                    else "bold blue" if opp.verdict == "CONFIRMED"
                    else "bold yellow" if opp.verdict == "WEAKENED"
                    else "bold red"
                )
                chal_table.add_row(
                    str(opp.rank),
                    opp.title,
                    opp.problem_name,
                    opp.competitor_prevalence,
                    f"[{verdict_style}]{opp.verdict}[/{verdict_style}]",
                    f"{opp.final_score:.3f}",
                    opp.recommendation.replace("_", " ").title(),
                )
            console.print(chal_table)
            console.print(f"[bold]Challenge Loop Stats:[/bold] {challenge_analysis.stats}")

        # Step 6: Build competitor assessment matrix & gap analysis
        from .assessment import build_competitor_assessment
        top_opp = (
            challenge_analysis.final_opportunities[0]
            if challenge_analysis and challenge_analysis.final_opportunities
            else None
        )
        if not top_opp and opp_analysis and opp_analysis.opportunities:
            from .challenge.models import FinalOpportunity
            o = opp_analysis.opportunities[0]
            top_opp = FinalOpportunity(
                rank=1,
                opportunity_id=o.id,
                hypothesis_id="hyp_01",
                title=o.title,
                problem_name=o.problem_name,
                category=o.category,
                improvement_type=o.improvement_type,
                improvement_concept=o.improvement_concept,
                differentiation_angle=o.differentiation_angle,
                verdict="CONFIRMED",
                final_score=o.priority_score,
                confidence=0.70,
                recommendation="PROCEED_WITH_CAUTION",
                competitor_prevalence="Initial sample",
                agent_assessment=o.improvement_concept,
                supporting_evidence_quotes=o.supporting_evidence_quotes,
            )

        if top_opp:
            with console.status("Building competitor assessment and gap analysis..."):
                assessment = build_competitor_assessment(
                    result,
                    top_opp,
                    review_intel=rev_intel,
                    limit=5,
                )

            matrix_table = Table(title=f"Competitor Assessment ({assessment.opportunity_title})")
            matrix_table.add_column("Competitor", style="bold cyan", overflow="fold")
            matrix_table.add_column("Price", width=12)
            matrix_table.add_column("Rating", width=8)
            matrix_table.add_column("Main Strength", style="bold green", width=18)
            matrix_table.add_column("Problem", style="bold red", width=18)

            for comp in assessment.competitors:
                matrix_table.add_row(
                    comp.name,
                    comp.price_display,
                    f"{comp.rating:.1f}" if comp.rating else "-",
                    comp.main_strength,
                    comp.problem,
                )
            console.print(matrix_table)

            from rich.panel import Panel
            gap_text = (
                f"[bold yellow]Where is the gap?[/bold yellow]\n\n"
                f"{assessment.gap_analysis.where_is_the_gap}\n\n"
                f"[bold]Target Price Window:[/bold] {assessment.gap_analysis.price_gap_range}\n"
                f"[bold]Trade-off to Break:[/bold] {assessment.gap_analysis.tradeoff_to_break}\n"
                f"[bold]Winning Positioning:[/bold] [green]{assessment.gap_analysis.winning_positioning}[/green]"
            )
            console.print(Panel(gap_text, title="[bold]Strategic Gap Analysis[/bold]", expand=False))

    slug = re.sub(r"[^a-z0-9]+", "-", args.query.lower()).strip("-")
    run_timestamp = datetime.now()
    run_id = f"{slug}-{run_timestamp:%Y%m%d-%H%M%S}"
    out = Path(args.out) if args.out else RUNS_DIR / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]Saved {len(result.products)} products ->[/green] {out}")

    if rev_intel:
        rev_out = out.parent / f"{out.stem}-reviews.json"
        rev_out.write_text(rev_intel.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Saved review intelligence ->[/green] {rev_out}")

        prob_out = out.parent / f"{out.stem}-problems.json"
        prob_out.write_text(prob_analysis.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Saved recurring problems ->[/green] {prob_out}")

        if opp_analysis:
            opp_out = out.parent / f"{out.stem}-opportunities.json"
            opp_out.write_text(opp_analysis.model_dump_json(indent=2), encoding="utf-8")
            console.print(f"[green]Saved candidate opportunities ->[/green] {opp_out}")

        if challenge_analysis:
            chal_out = out.parent / f"{out.stem}-challenge.json"
            chal_out.write_text(challenge_analysis.model_dump_json(indent=2), encoding="utf-8")
            console.print(f"[green]Saved final validated opportunities ->[/green] {chal_out}")

        if assessment:
            assess_out = out.parent / f"{out.stem}-assessment.json"
            assess_out.write_text(assessment.model_dump_json(indent=2), encoding="utf-8")
            console.print(f"[green]Saved competitor assessment ->[/green] {assess_out}")

    if not args.no_mongo:
        from .db import MongoStorage

        storage = MongoStorage.from_env()
        if storage:
            if storage.ping():
                try:
                    storage.init_indexes()
                    storage.save_research_set(result, run_id=run_id)
                    console.print(
                        f"[bold green]Saved research run to MongoDB ->[/bold green] "
                        f"collection: research_runs (db: {storage.db_name}, run_id: {run_id})"
                    )
                    if rev_intel:
                        storage.save_review_intelligence(rev_intel, run_id=run_id)
                        console.print(
                            f"[bold green]Saved review intelligence to MongoDB ->[/bold green] "
                            f"collection: review_intelligence"
                        )
                        storage.save_problem_analysis(prob_analysis, run_id=run_id)
                        console.print(
                            f"[bold green]Saved recurring problems to MongoDB ->[/bold green] "
                            f"collections: problem_analyses, problem_clusters"
                        )
                        if opp_analysis:
                            storage.save_opportunity_analysis(opp_analysis, run_id=run_id)
                            console.print(
                                f"[bold green]Saved candidate opportunities to MongoDB ->[/bold green] "
                                f"collections: opportunity_analyses, candidate_opportunities"
                            )
                        if challenge_analysis:
                            storage.save_challenge_analysis(challenge_analysis, run_id=run_id)
                            console.print(
                                f"[bold green]Saved challenge loop results to MongoDB ->[/bold green] "
                                f"collections: challenge_runs, final_opportunities"
                            )
                        if assessment:
                            storage.save_competitor_assessment(assessment, run_id=run_id)
                            console.print(
                                f"[bold green]Saved competitor assessment to MongoDB ->[/bold green] "
                                f"collections: competitor_assessments, competitor_profiles"
                            )
                except Exception as err:
                    console.print(f"[yellow]Warning: Failed to save to MongoDB ({err}). File outputs remain intact.[/yellow]")
                finally:
                    storage.close()
            else:
                console.print(f"[yellow]MongoDB configured ({storage.uri}) but server unreachable. Local files saved.[/yellow]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
