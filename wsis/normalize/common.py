"""Parsing helpers shared by normalizers."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from ..schema import SearchRecord, Source

_SYMBOL_CURRENCY = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "¥": "JPY", "C$": "CAD", "A$": "AUD"}


def to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"\d[\d,]*\.?\d*", str(value))
    return float(m.group().replace(",", "")) if m else None


def parse_count(value: Any) -> Optional[int]:
    """'1.2K+ bought in past month' -> 1200, '46,700' -> 46700, 385 -> 385."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"(\d[\d,]*\.?\d*)\s*([kKmM])?", str(value))
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    mult = {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return int(num * mult)


def currency_from_price(price_raw: Optional[str], fallback: Optional[str]) -> Optional[str]:
    if price_raw:
        for sym in sorted(_SYMBOL_CURRENCY, key=len, reverse=True):
            if sym in price_raw:
                return _SYMBOL_CURRENCY[sym]
    return fallback


def parse_serpapi_time(value: Optional[str]) -> Optional[datetime]:
    """SerpAPI format: '2026-10-07 10:50:00 UTC'."""
    if not value:
        return None
    try:
        return datetime.strptime(value.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def origin_url(metadata: dict[str, Any]) -> Optional[str]:
    """Find the marketplace URL SerpAPI scraped (amazon_url, google_shopping_url, ...)."""
    for key, val in metadata.items():
        if key.endswith("_url") and isinstance(val, str) and "serpapi.com" not in val:
            return val
    return None


def build_search_record(source: Source, raw: dict[str, Any], from_cache: bool) -> SearchRecord:
    meta = raw.get("search_metadata", {}) or {}
    params = {k: v for k, v in (raw.get("search_parameters", {}) or {}).items() if k != "api_key"}
    info = raw.get("search_information", {}) or {}
    return SearchRecord(
        source=source,
        engine=params.get("engine", source),
        params=params,
        search_id=meta.get("id"),
        serpapi_json_url=meta.get("json_endpoint"),
        origin_search_url=origin_url(meta),
        total_results=parse_count(info.get("total_results")),
        retrieved_at=parse_serpapi_time(meta.get("processed_at") or meta.get("created_at")),
        from_cache=from_cache,
    )


_STOPWORDS = {"a", "an", "the", "for", "and", "with", "of", "to", "in", "on", "by", "best", "cheap", "top"}


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens with naive singularization."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    out = []
    for t in tokens:
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def query_tokens(query: str) -> set[str]:
    return {t for t in tokenize(query) if t not in _STOPWORDS}
