"""Review cleaning: normalize text, drop noise, remove duplicates.

`original_text` is never modified; only `text` (the analysis copy) is cleaned.
"""
from __future__ import annotations

import html
import re
from collections import Counter

from .models import Review

MIN_WORDS = 4
MIN_CHARS = 20
NEAR_DUP_JACCARD = 0.8


def clean_text(raw: str) -> tuple[str, bool]:
    """Returns (clean_text, truncated)."""
    t = html.unescape(raw).replace("\u200b", "")
    t = re.sub(r"\s+", " ", t).strip()
    truncated = t.startswith(("...", "…")) or t.endswith(("...", "…"))
    t = re.sub(r"^(\.{3}|…)\s*", "", t)
    t = re.sub(r"\s*(\.{3}|…)$", "", t)
    t = re.sub(r"\s*(Read more|See more)$", "", t, flags=re.I)
    return t.strip(), truncated


def _norm_key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _shingles(text: str, n: int = 3) -> set[str]:
    w = _norm_key(text).split()
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def is_noise(text: str) -> str | None:
    if len(text) < MIN_CHARS or len(text.split()) < MIN_WORDS:
        return "too_short"
    if not re.search(r"[A-Za-z\u00C0-\u024F]{3,}", text):
        return "no_words"
    if len(set(_norm_key(text).split())) <= 2:
        return "repetitive"
    return None


def _merge_into(keep: Review, dup: Review) -> None:
    """Fold a duplicate into the kept review without losing evidence."""
    for tag in dup.marketplace_aspects:
        if tag not in keep.marketplace_aspects:
            keep.marketplace_aspects.append(tag)
    if len(dup.text) > len(keep.text):
        keep.text, keep.original_text, keep.truncated = dup.text, dup.original_text, dup.truncated
    for field in ("rating", "author", "date", "title", "retailer"):
        if getattr(keep, field) is None and getattr(dup, field) is not None:
            setattr(keep, field, getattr(dup, field))


def clean_reviews(reviews: list[Review]) -> tuple[list[Review], Counter]:
    """Clean + dedupe. Order matters: callers pass reviews in product-rank order,
    so a cross-product duplicate stays attached to the higher-ranked product."""
    stats: Counter = Counter(raw=len(reviews))

    # 1. Normalize text, drop noise.
    staged: list[Review] = []
    for r in reviews:
        r.text, r.truncated = clean_text(r.original_text)
        reason = is_noise(r.text)
        if reason:
            stats[f"noise_{reason}"] += 1
        else:
            staged.append(r)

    # 2. Same review id (e.g. one Amazon review shown under several aspects).
    by_id: dict[str, Review] = {}
    for r in staged:
        key = f"{r.product_id}|{r.id}"
        if key in by_id:
            _merge_into(by_id[key], r)
            stats["dup_same_id"] += 1
        else:
            by_id[key] = r

    # 3. Exact text duplicates (also across products: shared review pools).
    by_text: dict[str, Review] = {}
    for r in by_id.values():
        k = _norm_key(r.text)
        if k in by_text:
            if by_text[k].product_id == r.product_id:
                _merge_into(by_text[k], r)
                stats["dup_exact_text"] += 1
            else:
                stats["dup_cross_product"] += 1
        else:
            by_text[k] = r

    # 4. Near duplicates / snippet-contained-in-full-review, within a product.
    kept: list[Review] = []
    for r in by_text.values():
        rk, rs = _norm_key(r.text), _shingles(r.text)
        match = None
        for k in kept:
            if k.product_id != r.product_id:
                continue
            kk = _norm_key(k.text)
            if rk in kk or kk in rk:
                match = k
                break
            ks = _shingles(k.text)
            if len(rs & ks) / max(1, len(rs | ks)) >= NEAR_DUP_JACCARD:
                match = k
                break
        if match:
            _merge_into(match, r)
            stats["dup_near"] += 1
        else:
            kept.append(r)

    stats["kept"] = len(kept)
    return kept, stats
