"""Configuration: API key loading and market presets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = DATA_DIR / "runs"

load_dotenv(PROJECT_ROOT / ".env")


def get_api_key() -> str:
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        raise RuntimeError("SERPAPI_KEY is not set. Add it to .env at the project root.")
    return key


def get_gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY", "").strip() or None


def get_mongo_uri() -> str | None:
    return os.getenv("MONGODB_URI", "").strip() or os.getenv("MONGO_URI", "").strip() or None


def get_mongo_db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", "").strip() or os.getenv("MONGO_DB_NAME", "").strip() or "wsis"


@dataclass(frozen=True)
class Market:
    """Keeps Amazon and Google Shopping pointed at the same country/currency
    so that prices from both sources are comparable."""

    code: str
    amazon_domain: str
    gl: str
    hl: str
    currency: str


MARKETS: dict[str, Market] = {
    "us": Market("us", "amazon.com", "us", "en", "USD"),
    "uk": Market("uk", "amazon.co.uk", "uk", "en", "GBP"),
    "in": Market("in", "amazon.in", "in", "en", "INR"),
    "ca": Market("ca", "amazon.ca", "ca", "en", "CAD"),
    "au": Market("au", "amazon.com.au", "au", "en", "AUD"),
    "de": Market("de", "amazon.de", "de", "de", "EUR"),
    "fr": Market("fr", "amazon.fr", "fr", "fr", "EUR"),
    "jp": Market("jp", "amazon.co.jp", "jp", "ja", "JPY"),
}


def get_market(code: str) -> Market:
    try:
        return MARKETS[code.lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown market '{code}'. Choose from: {', '.join(MARKETS)}") from exc
