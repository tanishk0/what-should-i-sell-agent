"""Relevance filtering and competitor ranking."""
from __future__ import annotations

import math

from .normalize.common import tokenize
from .schema import Product


def relevance(title: str, q_tokens: set[str]) -> float:
    """Share of query tokens present in the title (0..1)."""
    if not q_tokens:
        return 1.0
    return len(q_tokens & set(tokenize(title))) / len(q_tokens)


def product_relevance(p: Product, q_tokens: set[str]) -> float:
    return max(relevance(l.title, q_tokens) for l in p.listings)


def score(p: Product) -> float:
    """Competitive weight: proven demand (reviews), quality (rating),
    multi-source presence; penalize sponsored-only placements."""
    demand = min(math.log10(1 + (p.review_count or 0)) / 5.0, 1.0)  # 100k reviews -> 1.0
    quality = (p.rating or 0) / 5.0
    multi = 1.0 if len(p.sources) > 1 else 0.0
    s = p.relevance * (0.6 * demand + 0.25 * quality + 0.15 * multi)
    if p.sponsored_only:
        s -= 0.05
    return round(s, 4)


def select_top(products: list[Product], limit: int, min_per_source: int) -> list[Product]:
    """Top-N by score while guaranteeing each source some representation."""
    ranked = sorted(products, key=lambda p: p.score, reverse=True)
    chosen: list[Product] = []
    for src in ("amazon", "google_shopping"):
        for p in ranked:
            if sum(src in c.sources for c in chosen) >= min_per_source:
                break
            if src in p.sources and p not in chosen:
                chosen.append(p)
    for p in ranked:
        if len(chosen) >= limit:
            break
        if p not in chosen:
            chosen.append(p)
    return sorted(chosen[:limit], key=lambda p: p.score, reverse=True)
