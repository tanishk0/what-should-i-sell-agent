"""Unified LLM client supporting NVIDIA Nemotron-3-Ultra-550B and Google Gemini."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional

from .config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_NVIDIA_BASE_URL,
    DEFAULT_NVIDIA_MODEL,
    get_gemini_api_key,
    get_nvidia_api_key,
    require_nvidia_api_key,
)

logger = logging.getLogger(__name__)


def clean_json_response(text: str) -> dict:
    """Extract and parse clean JSON from LLM text output."""
    t = text.strip()
    # Strip markdown fenced code blocks if present
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        # Fallback regex to locate the outermost {...} object
        m = re.search(r"(\{.*\})", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        raise


def extract_results_from_json(text: str) -> list[dict]:
    """Extract review classification results from JSON with resilient fallback for cutoffs."""
    try:
        data = clean_json_response(text)
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Resilient fallback: parse individual {...} objects that contain "review_id"
    pattern = re.compile(r'\{[^{}]*?"review_id"\s*:\s*"[^"]+?"[^{}]*?\}', re.DOTALL)
    results = []
    for match in pattern.finditer(text):
        try:
            item = json.loads(match.group(0))
            if "review_id" in item:
                results.append(item)
        except Exception:
            continue

    if results:
        logger.warning("Recovered %d classification items from partially truncated response.", len(results))
        return results

    # Re-raise standard JSON error if nothing could be recovered
    return clean_json_response(text).get("results", [])


def call_nvidia_nemotron(
    prompt: str,
    *,
    model: str = DEFAULT_NVIDIA_MODEL,
    api_key: Optional[str] = None,
    base_url: str = DEFAULT_NVIDIA_BASE_URL,
    enable_thinking: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    max_retries: int = 4,
) -> str:
    """Call NVIDIA Nemotron via OpenAI client with retry."""
    from openai import OpenAI

    key = api_key or require_nvidia_api_key()
    client = OpenAI(base_url=base_url, api_key=key)

    for attempt in range(max_retries + 1):
        try:
            extra_body = {
                "chat_template_kwargs": {"enable_thinking": bool(enable_thinking)}
            }

            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                top_p=0.95,
                max_tokens=max_tokens,
                extra_body=extra_body,
                stream=True,
            )

            reasoning_chunks = []
            content_chunks = []

            for chunk in completion:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    reasoning_chunks.append(reasoning)
                if delta.content is not None:
                    content_chunks.append(delta.content)

            output = "".join(content_chunks).strip()
            if not output and reasoning_chunks:
                # If content was empty, fallback to reasoning output
                output = "".join(reasoning_chunks).strip()

            return output

        except Exception as e:
            err_str = str(e)
            is_auth_or_bad_request = any(
                code in err_str.lower()
                for code in ["401", "invalid_api_key", "unauthorized"]
            )
            is_transient = not is_auth_or_bad_request or any(
                term in err_str.lower()
                for term in ["429", "503", "504", "502", "500", "overloaded", "temporarily", "ratelimit", "quota", "timeout", "connection"]
            )
            if not is_transient or attempt == max_retries:
                logger.error(f"NVIDIA API call failed: {e}")
                raise

            delay = 5.0 * (2 ** attempt)
            logger.warning(
                f"NVIDIA API transient error ({e}). Attempt {attempt + 1}/{max_retries}. Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    raise RuntimeError("NVIDIA API call exceeded maximum retries.")


def call_llm(
    prompt: str,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    client: Optional[Any] = None,
) -> str:
    """Generic LLM call router: defaults to NVIDIA Nemotron, supports Gemini when explicitly specified."""
    effective_model = model or DEFAULT_LLM_MODEL

    # If mock client is passed (e.g. in unit tests)
    if client is not None and hasattr(client, "models"):
        resp = client.models.generate_content(model=effective_model, contents=prompt)
        return resp.text

    # Route based on model prefix
    if "gemini" in effective_model.lower():
        from google import genai
        effective_key = api_key or get_gemini_api_key()
        g_client = genai.Client(api_key=effective_key)
        resp = g_client.models.generate_content(model=effective_model, contents=prompt)
        return resp.text

    # Default: NVIDIA Nemotron
    return call_nvidia_nemotron(
        prompt=prompt,
        model=effective_model,
        api_key=api_key or get_nvidia_api_key(),
    )
