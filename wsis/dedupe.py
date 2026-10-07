"""Merge listings that describe the same product into canonical `Product`s.

Three conservative rules (false merges are worse than missed merges, because a
false merge would attach one product's numbers to another):

1. Same source + same native id (ASIN / Google product_id).
2. Variant families: Amazon and Google Shopping both share one review pool
   across colour/size variants, so same source + same brand token + identical
   rating + identical review_count (>= 20) means the same parent product.
3. Cross-source: same leading brand token, every distinctive (non-query) token
   of the shorter title appears in the longer one, at least 2 distinctive
   tokens, and prices within 35% of each other.
"""
from __future__ import annotations

from collections import defaultdict

from .normalize.common import tokenize
from .schema import Listing, Product


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _same_variant_family(a: Listing, b: Listing) -> bool:
    if a.source != b.source:
        return False
    if not a.review_count or a.review_count < 20 or a.review_count != b.review_count:
        return False
    if a.rating != b.rating:
        return False
    ta, tb = tokenize(a.title), tokenize(b.title)
    return bool(ta and tb and ta[0] == tb[0])


def _same_cross_source(a: Listing, b: Listing, q_tokens: set[str]) -> bool:
    if a.source == b.source:
        return False
    ta, tb = tokenize(a.title), tokenize(b.title)
    if not ta or not tb or ta[0] != tb[0]:
        return False
    da, db = set(ta) - q_tokens, set(tb) - q_tokens
    short, long_ = (da, db) if len(da) <= len(db) else (db, da)
    if len(short) < 2 or not short <= long_:
        return False
    if a.price and b.price:
        lo, hi = sorted((a.price, b.price))
        if hi > lo * 1.35:
            return False
    return True


def _primary(listings: list[Listing]) -> Listing:
    """Listing with the most evidence: most reviews, then organic, then best rank."""
    return sorted(
        listings,
        key=lambda l: (-(l.review_count or 0), l.sponsored, l.position or 10_000),
    )[0]


def merge_listings(listings: list[Listing], q_tokens: set[str]) -> list[Product]:
    uf = _UnionFind(len(listings))

    by_id: dict[tuple[str, str], int] = {}
    for i, l in enumerate(listings):
        key = (l.source, l.source_product_id)
        if key in by_id:
            uf.union(i, by_id[key])
        else:
            by_id[key] = i

    for i in range(len(listings)):
        for j in range(i + 1, len(listings)):
            a, b = listings[i], listings[j]
            if _same_variant_family(a, b) or _same_cross_source(a, b, q_tokens):
                uf.union(i, j)

    groups: dict[int, list[Listing]] = defaultdict(list)
    for i, l in enumerate(listings):
        groups[uf.find(i)].append(l)

    products = []
    for group in groups.values():
        # Drop exact duplicate listings (same id seen twice), keep the best-ranked copy.
        uniq: dict[tuple[str, str], Listing] = {}
        for l in sorted(group, key=lambda l: (l.sponsored, l.position or 10_000)):
            uniq.setdefault((l.source, l.source_product_id), l)
        group = list(uniq.values())
        p = _primary(group)
        prices = [l.price for l in group if l.price is not None]
        products.append(
            Product(
                id=f"{p.source}:{p.source_product_id}",
                title=p.title,
                url=p.url,
                price=p.price,
                price_min=min(prices) if prices else None,
                price_max=max(prices) if prices else None,
                currency=p.currency,
                rating=p.rating,
                review_count=p.review_count,
                bought_last_month=max((l.bought_last_month or 0) for l in group) or None,
                sources=sorted({l.source for l in group}),
                sponsored_only=all(l.sponsored for l in group),
                listings=group,
            )
        )
    return products
