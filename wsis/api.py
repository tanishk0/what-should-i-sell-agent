"""FastAPI backend application for MarketGap Amazon Market Research.

Provides REST API endpoints for starting research jobs, querying real-time progress,
and retrieving evidence-backed market research reports.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import DEFAULT_MARKET, DEFAULT_LLM_MODEL, MARKETS, get_api_key
from .pipeline import build_competitor_set
from .report import build_final_report
from .report.models import MarketGapReport
from .reviews.clustering import cluster_complaints
from .reviews.pipeline import run_review_intelligence
from .serp_client import SerpClient

logger = logging.getLogger("wsis.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="MarketGap API",
    description="Evidence-backed Amazon Market-Gap Research API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Product category or search term, e.g. 'men boxers'")
    market: str = Field(default=DEFAULT_MARKET, description="Marketplace code (default: 'in')")
    limit: int = Field(default=15, ge=3, le=50, description="Competitor products to analyze")
    review_limit: int = Field(default=5, ge=1, le=15, description="Top competitors to pull reviews for")
    model: Optional[str] = Field(default=None, description="LLM model override (defaults to configured model)")


class JobState(BaseModel):
    id: str
    query: str
    market: str
    status: str  # "queued", "running", "completed", "failed"
    stage: str   # "finding_competitors", "collecting_reviews", "analyzing_complaints", "validating_evidence", "preparing_report", "done", "failed"
    progress: int  # 0 to 100
    message: str
    created_at: str
    updated_at: str
    error: Optional[str] = None
    report: Optional[dict[str, Any]] = None
    price_range: Optional[dict[str, Any]] = None
    product_details: Optional[dict[str, Any]] = None


# Thread-safe in-memory store for research jobs
_JOBS: dict[str, JobState] = {}
_JOBS_LOCK = threading.Lock()


def _update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    report: Optional[dict[str, Any]] = None,
    price_range: Optional[dict[str, Any]] = None,
    product_details: Optional[dict[str, Any]] = None,
) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        if status is not None:
            job.status = status
        if stage is not None:
            job.stage = stage
        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        if error is not None:
            job.error = error
        if report is not None:
            job.report = report
        if price_range is not None:
            job.price_range = price_range
        if product_details is not None:
            job.product_details = product_details
        job.updated_at = datetime.now(timezone.utc).isoformat()


def _run_research_task(
    job_id: str,
    query: str,
    market: str,
    limit: int,
    review_limit: int,
    model: Optional[str] = None,
) -> None:
    try:
        logger.info(f"Starting research job {job_id} for '{query}' in {market.upper()}")
        _update_job(
            job_id,
            status="running",
            stage="finding_competitors",
            progress=10,
            message=f"Searching Amazon {market.upper()} for competitor listings...",
        )

        api_key = get_api_key()
        client = SerpClient(api_key, use_cache=True)

        # Stage 1: Build competitor set
        result = build_competitor_set(
            query=query,
            client=client,
            market=market,
            limit=limit,
            amazon_pages=1,
        )

        if not result.products:
            raise RuntimeError(f"No competing products found for query '{query}' in market {market.upper()}.")

        # Compile product details map and price statistics
        product_details: dict[str, Any] = {}
        prices: list[float] = []
        for p in result.products:
            p_price = p.price if p.price is not None else p.price_min
            if p_price is not None:
                prices.append(p_price)
            product_details[p.id] = {
                "id": p.id,
                "title": p.title,
                "url": p.url,
                "price": p_price,
                "rating": p.rating,
                "review_count": p.review_count,
                "score": p.score,
                "sources": p.sources,
            }

        price_range = {
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
            "currency": result.currency,
        }

        _update_job(
            job_id,
            stage="collecting_reviews",
            progress=30,
            message=f"Found {len(result.products)} competitors. Collecting customer reviews...",
            product_details=product_details,
            price_range=price_range,
        )

        # Stage 2 & 3: Reviews fetch & classify
        def on_review_progress(msg: str) -> None:
            if "Classifying" in msg:
                _update_job(job_id, stage="analyzing_complaints", progress=60, message=msg)
            else:
                _update_job(job_id, stage="collecting_reviews", progress=40, message=msg)

        rev_intel = run_review_intelligence(
            research_set=result,
            serp_client=client,
            competitor_limit=review_limit,
            credit_budget=15,
            max_reviews_per_product=6,
            llm_model=model,
            on_progress=on_review_progress,
        )

        # Stage 4: Cluster complaints
        _update_job(
            job_id,
            stage="validating_evidence",
            progress=80,
            message="Grouping complaints into recurring problem themes and programmatically validating evidence...",
        )
        prob_analysis = cluster_complaints(rev_intel, model=model)

        # Stage 5: Build final report
        _update_job(
            job_id,
            stage="preparing_report",
            progress=95,
            message="Synthesizing evidence-backed market gap report...",
        )
        final_report: MarketGapReport = build_final_report(
            research_set=result,
            review_intel=rev_intel,
            prob_analysis=prob_analysis,
        )

        # Finalize
        report_dict = final_report.model_dump(mode="json")
        _update_job(
            job_id,
            status="completed",
            stage="done",
            progress=100,
            message="Market research report generated successfully.",
            report=report_dict,
            price_range=price_range,
            product_details=product_details,
        )
        logger.info(f"Completed research job {job_id} successfully.")

    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            message=f"Research failed: {str(e)}",
            error=str(e),
        )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "default_market": DEFAULT_MARKET,
        "default_model": DEFAULT_LLM_MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/markets")
def list_markets() -> list[dict[str, str]]:
    return [
        {
            "code": code,
            "name": m.amazon_domain.replace("amazon.", "Amazon ").title(),
            "domain": m.amazon_domain,
            "currency": m.currency,
        }
        for code, m in MARKETS.items()
    ]


@app.post("/api/research")
def start_research(payload: ResearchRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    clean_query = payload.query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    market_code = payload.market.strip().lower()
    if market_code not in MARKETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid market '{market_code}'. Supported: {list(MARKETS)}",
        )

    job_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    job = JobState(
        id=job_id,
        query=clean_query,
        market=market_code,
        status="queued",
        stage="finding_competitors",
        progress=5,
        message="Queued for analysis...",
        created_at=now_iso,
        updated_at=now_iso,
    )

    with _JOBS_LOCK:
        _JOBS[job_id] = job

    # Launch in background thread so HTTP worker doesn't block
    background_tasks.add_task(
        _run_research_task,
        job_id=job_id,
        query=clean_query,
        market=market_code,
        limit=payload.limit,
        review_limit=payload.review_limit,
        model=payload.model,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Analysis started.",
    }


@app.get("/api/research/{job_id}")
def get_research_status(job_id: str) -> dict[str, Any]:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Research job not found.")
        return job.model_dump()


# Mount frontend if built
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static_assets")

    @app.get("/{full_path:path}")
    def serve_frontend_spa(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
