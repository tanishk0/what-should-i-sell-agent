"""Thin SerpAPI HTTP client with an on-disk cache.

The cache saves credits during development and makes runs reproducible:
the raw JSON that backs every citation is kept locally.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from .config import CACHE_DIR

SERPAPI_URL = "https://serpapi.com/search.json"


class SerpApiError(RuntimeError):
    pass


class SerpClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        offline: bool = False,
        timeout: float = 90.0,
        retries: int = 2,
    ) -> None:
        if not api_key and not offline:
            raise SerpApiError("An API key is required unless offline=True.")
        self.api_key = api_key
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self.offline = offline
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    @staticmethod
    def cache_key(params: dict[str, Any]) -> str:
        clean = {k: v for k, v in sorted(params.items()) if k != "api_key"}
        return hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()[:24]

    def _cache_path(self, params: dict[str, Any]) -> Path:
        return self.cache_dir / str(params.get("engine", "unknown")) / f"{self.cache_key(params)}.json"

    def search(self, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Run a search. Returns (response_json, served_from_cache)."""
        path = self._cache_path(params)
        if (self.use_cache or self.offline) and path.exists():
            return json.loads(path.read_text(encoding="utf-8")), True
        if self.offline:
            raise SerpApiError(f"Offline mode and no cached response for {params}.")

        data = self._request({**params, "api_key": self.api_key})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data, False

    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(SERPAPI_URL, params=params, timeout=self.timeout)
                data = resp.json()
                if resp.status_code >= 500:
                    raise SerpApiError(f"SerpAPI {resp.status_code}: {data.get('error')}")
                if "error" in data and not _is_empty_result_error(data["error"]):
                    raise SerpApiError(f"SerpAPI error ({params.get('engine')}): {data['error']}")
                return data
            except (requests.RequestException, ValueError, SerpApiError) as err:
                last_err = err
                # Client-side errors (bad key, bad params) won't fix themselves.
                if isinstance(err, SerpApiError) and "SerpAPI 5" not in str(err):
                    break
                time.sleep(1.5 * (attempt + 1))
        raise SerpApiError(str(last_err))


def _is_empty_result_error(msg: str) -> bool:
    return "hasn't returned any results" in msg.lower()
