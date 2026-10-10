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
    """Extract and parse clean JSON from LLM text output with resilient repair."""
    t = text.strip()
    # Strip markdown fenced code blocks if present
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    t = t.strip()

    try:
        return json.loads(t, strict=False)
    except Exception:
        pass

    # Fallback regex to locate the outermost {...} object
    m = re.search(r"(\{.*\})", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1), strict=False)
        except Exception:
            pass

    # Fallback: Truncated JSON repair for unclosed objects or cutoffs
    last_brace = t.rfind("}")
    while last_brace > 0:
        candidate = t[:last_brace + 1].strip()
        for suffix in ["", "}", "]}", "\n  ]\n}"]:
            try:
                res = json.loads(candidate + suffix, strict=False)
                if isinstance(res, dict):
                    logger.warning("Repaired truncated JSON ending at character index %d.", last_brace)
                    return res
            except Exception:
                continue
        last_brace = t.rfind("}", 0, last_brace)

    # Re-try json.loads to raise informative error if all fallbacks fail
    return json.loads(t, strict=False)


def _parse_single_cluster_block(block: str) -> Optional[dict]:
    """Parse a single cluster object block with strict=False and regex field fallback."""
    b = block.strip().rstrip(",")
    try:
        data = json.loads(b, strict=False)
        if isinstance(data, dict) and "name" in data:
            return data
    except Exception:
        pass

    # Fallback: Extract fields individually via regex even if unescaped quotes broke strict JSON
    name_m = re.search(r'"name"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', b)
    if not name_m:
        name_m = re.search(r'"name"\s*:\s*"(.*?)"\s*,\s*"', b, re.DOTALL)
    if not name_m:
        return None

    cat_m = re.search(r'"category"\s*:\s*"([^"]+)"', b)
    desc_m = re.search(r'"description"\s*:\s*"(.*?)"(?:\s*,\s*"|\s*\})', b, re.DOTALL)

    # Extract complaint IDs
    ids = re.findall(r'"([a-zA-Z0-9_\-:]+:[a-zA-Z0-9_\-]+)"', b)
    if not ids:
        ids = re.findall(r'"(rev_[a-zA-Z0-9_\-]+)"', b) or re.findall(r'"(r\d+)"', b)

    return {
        "name": name_m.group(1).strip(),
        "category": cat_m.group(1).strip() if cat_m else "other",
        "description": desc_m.group(1).strip() if desc_m else "",
        "assigned_complaint_ids": list(dict.fromkeys(ids)),
    }


def extract_clusters_from_json(text: str) -> list[dict]:
    """Extract cluster items from JSON with resilient fallback for cutoffs, unescaped quotes, and delimiters."""
    try:
        data = clean_json_response(text)
        if isinstance(data, dict) and "clusters" in data:
            return data["clusters"]
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Fallback 1: Truncated JSON repair by closing open clusters array
    try:
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```(?:json)?\s*", "", t)
            t = re.sub(r"\s*```$", "", t).strip()

        last_brace = t.rfind("}")
        while last_brace > 0:
            candidate = t[:last_brace + 1].strip()
            for suffix in ["]}", "}", "\n  ]\n}"]:
                try:
                    data = json.loads(candidate + suffix, strict=False)
                    if isinstance(data, dict) and "clusters" in data and len(data["clusters"]) > 0:
                        logger.warning("Recovered %d clusters by repairing truncated JSON.", len(data["clusters"]))
                        return data["clusters"]
                except Exception:
                    continue
            last_brace = t.rfind("}", 0, last_brace)
    except Exception:
        pass

    # Fallback 2: Balanced-brace parser to isolate individual cluster objects
    clusters: list[dict] = []
    idx = text.find('"clusters"')
    if idx == -1:
        idx = text.find("'clusters'")
    start_search = text.find("[", idx) if idx != -1 else text.find("[")

    if start_search != -1:
        i = start_search + 1
        n = len(text)
        while i < n:
            while i < n and text[i] != "{":
                if text[i] == "]":
                    break
                i += 1
            if i >= n or text[i] == "]":
                break

            obj_start = i
            brace_count = 0
            in_str = False
            esc = False

            while i < n:
                c = text[i]
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = not in_str
                elif not in_str:
                    if c == "{":
                        brace_count += 1
                    elif c == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            block = text[obj_start : i + 1]
                            parsed = _parse_single_cluster_block(block)
                            if parsed:
                                clusters.append(parsed)
                            break
                i += 1
            i += 1

    if clusters:
        logger.warning("Recovered %d clusters using balanced-brace block parser.", len(clusters))
        return clusters

    # Fallback 3: Regex match on individual blocks
    pattern = re.compile(r'\{[^{}]*?"name"\s*:\s*"[^"]+?"[^{}]*?\}', re.DOTALL)
    for match in pattern.finditer(text):
        parsed = _parse_single_cluster_block(match.group(0))
        if parsed:
            clusters.append(parsed)

    if clusters:
        logger.warning("Recovered %d clusters using regex fallback.", len(clusters))
        return clusters

    # Fallback 4: Sequential block extraction splitting by '"name":'
    matches = list(re.finditer(r'"name"\s*:\s*"', text))
    for i, match in enumerate(matches):
        start_pos = match.start()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start_pos:end_pos]

        m_name = re.search(r'"name"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', chunk)
        if not m_name:
            m_name = re.search(r'"name"\s*:\s*"(.*?)"\s*,\s*"', chunk, re.DOTALL)
        if not m_name:
            continue

        m_cat = re.search(r'"category"\s*:\s*"([^"]+)"', chunk)
        category = m_cat.group(1).strip() if m_cat else "other"

        m_desc = re.search(r'"description"\s*:\s*"(.*?)"(?:\s*,\s*"|\s*\]|\s*\})', chunk, re.DOTALL)
        if not m_desc:
            m_desc = re.search(r'"description"\s*:\s*"(.*)', chunk, re.DOTALL)
        desc = m_desc.group(1).strip().rstrip('",\n }') if m_desc else ""

        ids = re.findall(r'"([a-zA-Z0-9_\-:]+:[a-zA-Z0-9_\-]+)"', chunk)
        if not ids:
            ids = re.findall(r'"(rev_[a-zA-Z0-9_\-]+)"', chunk) or re.findall(r'"(r\d+)"', chunk)

        clusters.append({
            "name": m_name.group(1).strip(),
            "category": category,
            "description": desc,
            "assigned_complaint_ids": list(dict.fromkeys(ids)),
        })

    if clusters:
        logger.warning("Recovered %d clusters using sequential block fallback.", len(clusters))
        return clusters

    try:
        return clean_json_response(text).get("clusters", [])
    except Exception:
        logger.warning("Could not extract any clusters from text of length %d.", len(text))
        return []


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
            item = json.loads(match.group(0), strict=False)
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
    max_tokens: int = 6144,
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
