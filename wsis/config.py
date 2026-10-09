"""Configuration: API key loading and market presets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"

load_dotenv(PROJECT_ROOT / ".env")


def get_api_key() -> str:
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        raise RuntimeError("SERPAPI_KEY is not set. Add it to .env at the project root.")
    return key


DEFAULT_NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b").strip() or "nvidia/nemotron-3-ultra-550b-a55b"
DEFAULT_NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip() or "https://integrate.api.nvidia.com/v1"
DEFAULT_GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip() or "gemini-3.5-flash"
DEFAULT_LLM_MODEL: str = DEFAULT_NVIDIA_MODEL


def get_nvidia_api_key() -> str | None:
    return os.getenv("NVIDIA_API_KEY", "").strip() or None


def require_nvidia_api_key() -> str:
    key = get_nvidia_api_key()
    if not key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set. Add NVIDIA_API_KEY to your .env file at the project root."
        )
    return key


def get_gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY", "").strip() or None


def require_gemini_api_key() -> str:
    key = get_gemini_api_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add GEMINI_API_KEY to your .env file at the project root."
        )
    return key


def get_llm_api_key() -> str | None:
    return get_nvidia_api_key() or get_gemini_api_key()


def require_llm_api_key() -> str:
    key = get_llm_api_key()
    if not key:
        raise RuntimeError(
            "Neither NVIDIA_API_KEY nor GEMINI_API_KEY is set. Add NVIDIA_API_KEY to your .env file."
        )
    return key



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

DEFAULT_MARKET: str = os.getenv("DEFAULT_MARKET", "in").strip().lower() or "in"


def get_market(code: str) -> Market:
    try:
        return MARKETS[code.lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown market '{code}'. Choose from: {', '.join(MARKETS)}") from exc
