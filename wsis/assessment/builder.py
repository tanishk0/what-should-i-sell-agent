"""Build competitor assessment matrix and answer: Where is the gap? (Step 6)"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import get_gemini_api_key
from ..challenge.models import FinalOpportunity
from ..reviews.models import ReviewIntelligence
from ..schema import Product, ResearchSet
from .models import CompetitorAssessment, CompetitorProfile, MarketGapAnalysis

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

ASSESSMENT_PROMPT = """You are an elite product strategist and competitive intelligence analyst.
We are analyzing the competitive landscape for "{query}" to launch:
- Proposed Opportunity: {opp_title}
- Solves Problem: {target_problem}
- Proposed Improvement: {concept}

Competitors Data:
{competitors_payload}

Your Mission:
1. For each competitor, distill:
   - id: The competitor's exact product ID.
   - main_strength: 1-3 words capturing what buyers like or its primary selling appeal (e.g., 'Compact', 'Durable', 'Cheap', 'Thick cushion', 'Lightweight').
   - problem: 1-3 words capturing its primary defect, limitation, or complaint (e.g., 'Leaks', 'Bulky', 'Poor seal', 'Slippery', 'Tears fast', 'Chemical odor').

2. Strategic Market Gap Analysis:
   Directly answer the central strategic question:
   "Where is the gap?"
   - where_is_the_gap: Thorough 3-4 sentence synthesis explaining exactly where the whitespace exists in the market (e.g. price vs performance, feature combinations, or unmet customer segments).
   - unmet_need_summary: The exact customer compromise that no current competitor solves.
   - price_gap_range: Recommended price window (e.g. '₹699 - ₹799' or '$28 - $34').
   - tradeoff_to_break: The false choice buyers are currently forced into (e.g. 'Compact vs Leakproof', 'Soft cushioning vs Durability').
   - winning_positioning: Concise, actionable positioning statement for the new product to capture market share.

Return JSON matching:
{{
  "competitors": [
    {{
      "id": "string",
      "main_strength": "string",
      "problem": "string"
    }}
  ],
  "gap_analysis": {{
    "where_is_the_gap": "string",
    "unmet_need_summary": "string",
    "price_gap_range": "string",
    "tradeoff_to_break": "string",
    "winning_positioning": "string"
  }}
}}
"""


class LLMCompetitorItem(BaseModel):
    id: str
    main_strength: str
    problem: str


class LLMGapAnalysis(BaseModel):
    where_is_the_gap: str
    unmet_need_summary: str
    price_gap_range: str
    tradeoff_to_break: str
    winning_positioning: str


class LLMAssessmentResponse(BaseModel):
    competitors: list[LLMCompetitorItem]
    gap_analysis: LLMGapAnalysis


def format_price(price: Optional[float], currency: Optional[str] = "USD") -> str:
    """Format numeric price with appropriate currency symbol (e.g. ₹699, $24.99)."""
    if price is None:
        return "-"
    curr = (currency or "USD").upper()
    symbol = CURRENCY_SYMBOLS.get(curr, f"{curr} ")
    if curr in ("INR", "JPY") or price.is_integer():
        return f"{symbol}{int(price)}"
    return f"{symbol}{price:.2f}"


def clean_brand_name(title: str) -> str:
    """Extract a concise readable product/brand name from a long marketplace title."""
    parts = title.split()
    if len(parts) <= 4:
        return title
    # Take first 4 words or up to first punctuation
    clean = re.split(r"[,|\-–/:]", title)[0].strip()
    words = clean.split()
    if len(words) > 4:
        return " ".join(words[:4])
    return clean or " ".join(parts[:4])


def _heuristic_strength_and_problem(
    product: Product,
    pr_reviews: Optional[list[Any]],
    target_problem: str,
    median_price: float,
) -> tuple[str, str]:
    """Derive heuristic strength and problem when LLM is unavailable."""
    title_lower = product.title.lower()
    price = product.price or product.price_min or median_price

    # Strength derivation
    if any(k in title_lower for k in ["compact", "mini", "portable", "travel", "small"]):
        strength = "Compact"
    elif any(k in title_lower for k in ["thick", "extra thick", "cushion", "comfort", "density"]):
        strength = "High cushion"
    elif any(k in title_lower for k in ["durable", "heavy duty", "pro", "premium", "sturdy"]):
        strength = "Durable"
    elif any(k in title_lower for k in ["lightweight", "feather", "ultra light", "slim"]):
        strength = "Lightweight"
    elif price < median_price * 0.8:
        strength = "Affordable"
    elif product.rating and product.rating >= 4.5:
        strength = "High rated"
    else:
        strength = "Standard build"

    # Problem derivation
    complaint_issues: list[str] = []
    if pr_reviews:
        for r in pr_reviews:
            if getattr(r, "classification", None) and r.classification.is_complaint:
                complaint_issues.extend(r.classification.issues)

    if complaint_issues:
        first_issue = complaint_issues[0].lower()
        if any(k in first_issue for k in ["slip", "grip", "traction"]):
            problem = "Slippery"
        elif any(k in first_issue for k in ["tear", "rip", "peel", "flake"]):
            problem = "Tears fast"
        elif any(k in first_issue for k in ["leak", "spill"]):
            problem = "Leaks"
        elif any(k in first_issue for k in ["seal", "closure", "lid"]):
            problem = "Poor seal"
        elif any(k in first_issue for k in ["smell", "odor", "scent"]):
            problem = "Chemical odor"
        elif any(k in first_issue for k in ["thin", "hard", "joint"]):
            problem = "Too thin"
        else:
            problem = complaint_issues[0][:15].title()
    elif price > median_price * 1.3:
        problem = "Expensive"
    elif any(k in target_problem.lower() for k in ["slip", "grip"]):
        problem = "Slippery"
    elif any(k in target_problem.lower() for k in ["leak"]):
        problem = "Leaks"
    elif price < median_price * 0.75:
        problem = "Cheap finish"
    else:
        problem = "Bulky"

    return strength, problem


def _build_heuristic_gap_analysis(
    query: str,
    opp_title: str,
    target_problem: str,
    competitors: list[CompetitorProfile],
    currency: str,
) -> MarketGapAnalysis:
    """Generate deterministic strategic gap analysis."""
    prices = [c.price for c in competitors if c.price is not None]
    min_p = min(prices) if prices else 20.0
    max_p = max(prices) if prices else 50.0
    mid_low = round(min_p + (max_p - min_p) * 0.25)
    mid_high = round(min_p + (max_p - min_p) * 0.55)

    symbol = CURRENCY_SYMBOLS.get(currency.upper(), "$")
    price_gap = f"{symbol}{mid_low} - {symbol}{mid_high}"

    tradeoff = f"High performance vs Affordable pricing"
    if any("leak" in c.problem.lower() for c in competitors) or "leak" in target_problem.lower():
        tradeoff = "Compact portability vs Guaranteed leakproof seal"
    elif any("slip" in c.problem.lower() for c in competitors) or "slip" in target_problem.lower():
        tradeoff = "Soft joint cushioning vs High-traction anti-slip grip"
    elif any("tear" in c.problem.lower() for c in competitors):
        tradeoff = "Lightweight build vs Long-term tear durability"

    where_gap = (
        f"The primary market gap sits in the accessible sweet spot at {price_gap}. "
        f"Existing low-cost competitors suffer from widespread '{target_problem.lower()}', "
        f"while premium incumbent alternatives are either overly expensive or bulky. "
        f"No current competitor successfully resolves '{tradeoff}' without charging an excessive premium. "
        f"Introducing '{opp_title}' directly fills this void."
    )

    unmet_need = (
        f"A product that delivers reliable protection against '{target_problem}' while maintaining "
        f"an accessible price point and high build quality."
    )

    winning_pos = (
        f"Position as the category's first 'Zero-Compromise' solution at {price_gap}: "
        f"delivering premium reliability while directly targeting incumbent flaws."
    )

    return MarketGapAnalysis(
        where_is_the_gap=where_gap,
        unmet_need_summary=unmet_need,
        price_gap_range=price_gap,
        tradeoff_to_break=tradeoff,
        winning_positioning=winning_pos,
    )


def build_competitor_assessment(
    research_set: ResearchSet,
    final_opportunity: FinalOpportunity,
    review_intel: Optional[ReviewIntelligence] = None,
    *,
    limit: int = 5,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
) -> CompetitorAssessment:
    """Step 6: Build competitor assessment matrix and answer: Where is the gap?"""
    products = research_set.products[:limit]
    currency = research_set.currency or "USD"

    # Precalculate prices for heuristic fallback
    valid_prices = [p.price for p in products if p.price is not None]
    median_price = sum(valid_prices) / max(1, len(valid_prices)) if valid_prices else 30.0

    # Index reviews by product_id
    reviews_by_pid: dict[str, list[Any]] = {}
    if review_intel:
        for pr in review_intel.products:
            reviews_by_pid[pr.product_id] = pr.reviews

    # Build raw competitor items
    competitor_items = []
    for p in products:
        c_name = clean_brand_name(p.title)
        price_val = p.price or p.price_min
        p_disp = format_price(price_val, currency)
        pr_revs = reviews_by_pid.get(p.id, [])
        strength, problem = _heuristic_strength_and_problem(
            p, pr_revs, final_opportunity.problem_name, median_price
        )
        competitor_items.append({
            "id": p.id,
            "name": c_name,
            "full_title": p.title,
            "price_display": p_disp,
            "price": price_val,
            "currency": currency,
            "rating": p.rating,
            "review_count": p.review_count,
            "main_strength": strength,
            "problem": problem,
            "url": p.url,
        })

    api_key = gemini_api_key or get_gemini_api_key()
    client = None
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning(f"Could not initialize Gemini client: {e}")

    method = "gemini_llm"
    gap_analysis: Optional[MarketGapAnalysis] = None

    if client:
        try:
            payload = [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "price": item["price_display"],
                    "rating": item["rating"],
                    "review_count": item["review_count"],
                    "full_title": item["full_title"][:80],
                }
                for item in competitor_items
            ]

            prompt = ASSESSMENT_PROMPT.format(
                query=research_set.query,
                opp_title=final_opportunity.title,
                target_problem=final_opportunity.problem_name,
                concept=final_opportunity.improvement_concept,
                competitors_payload=json.dumps(payload, ensure_ascii=False, indent=2),
            )

            resp = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": LLMAssessmentResponse,
                },
            )
            parsed = json.loads(resp.text or "{}")

            llm_comps = {c["id"]: c for c in parsed.get("competitors", [])}
            for item in competitor_items:
                if item["id"] in llm_comps:
                    item["main_strength"] = llm_comps[item["id"]].get("main_strength", item["main_strength"]).title()
                    item["problem"] = llm_comps[item["id"]].get("problem", item["problem"]).title()

            ga_raw = parsed.get("gap_analysis")
            if ga_raw and isinstance(ga_raw, dict):
                gap_analysis = MarketGapAnalysis(
                    where_is_the_gap=ga_raw.get("where_is_the_gap", ""),
                    unmet_need_summary=ga_raw.get("unmet_need_summary", ""),
                    price_gap_range=ga_raw.get("price_gap_range", ""),
                    tradeoff_to_break=ga_raw.get("tradeoff_to_break", ""),
                    winning_positioning=ga_raw.get("winning_positioning", ""),
                )
        except Exception as err:
            logger.warning(f"LLM competitor assessment failed ({err}); using heuristic fallback")
            method = "heuristic_assessment"
    else:
        method = "heuristic_assessment"

    # Fallback gap analysis if LLM was skipped or failed
    final_profiles = [
        CompetitorProfile(
            id=item["id"],
            name=item["name"],
            price_display=item["price_display"],
            price=item["price"],
            currency=item["currency"],
            rating=item["rating"],
            review_count=item["review_count"],
            main_strength=item["main_strength"],
            problem=item["problem"],
            url=item["url"],
        )
        for item in competitor_items
    ]

    if not gap_analysis:
        gap_analysis = _build_heuristic_gap_analysis(
            query=research_set.query,
            opp_title=final_opportunity.title,
            target_problem=final_opportunity.problem_name,
            competitors=final_profiles,
            currency=currency,
        )

    return CompetitorAssessment(
        query=research_set.query,
        market=research_set.market,
        opportunity_id=final_opportunity.opportunity_id,
        opportunity_title=final_opportunity.title,
        target_problem=final_opportunity.problem_name,
        competitors=final_profiles,
        gap_analysis=gap_analysis,
        created_at=datetime.now(timezone.utc),
        method=method,
        stats={
            "competitors_compared": len(final_profiles),
            "price_gap_range": gap_analysis.price_gap_range,
        },
    )
