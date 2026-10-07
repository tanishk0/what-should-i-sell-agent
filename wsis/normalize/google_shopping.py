"""Google Shopping (engine=google_shopping) -> Listing."""
from __future__ import annotations

from typing import Any, Optional

from ..schema import Citation, Listing, SearchRecord
from .common import currency_from_price, parse_count, to_float

_METADATA_KEYS = ("extensions", "tag", "delivery", "multiple_sources", "old_price")


def _iter_results(raw: dict[str, Any]):
    """Main shopping_results, then items inside categorized blocks."""
    for item in raw.get("shopping_results", []) or []:
        yield item, None
    for block in raw.get("categorized_shopping_results", []) or []:
        for item in block.get("shopping_results", []) or []:
            yield item, block.get("title")


def normalize_google_shopping(
    raw: dict[str, Any], record: SearchRecord, *, currency: Optional[str] = None
) -> list[Listing]:
    listings: list[Listing] = []
    for item, category in _iter_results(raw):
        pid = item.get("product_id")
        title = (item.get("title") or "").strip()
        url = item.get("link") or item.get("product_link")
        if not pid or not title or not url:
            continue
        price_raw = item.get("price")
        metadata = {k: item[k] for k in _METADATA_KEYS if k in item}
        if category:
            metadata["google_category_block"] = category
        tag = item.get("tag")
        listings.append(
            Listing(
                source="google_shopping",
                source_product_id=str(pid),
                title=title,
                url=url,
                seller=item.get("source"),
                price=to_float(item.get("extracted_price", price_raw)),
                price_raw=price_raw,
                original_price=to_float(item.get("extracted_old_price")),
                currency=currency_from_price(price_raw, currency),
                rating=to_float(item.get("rating")),
                review_count=parse_count(item.get("reviews")),
                sponsored=False,
                position=item.get("position"),
                thumbnail=item.get("thumbnail") or item.get("serpapi_thumbnail"),
                badges=[tag] if tag else [],
                detail_api_url=item.get("serpapi_product_api") or item.get("serpapi_immersive_product_api"),
                metadata=metadata,
                citation=Citation(
                    source="google_shopping",
                    engine=record.engine,
                    search_id=record.search_id,
                    serpapi_json_url=record.serpapi_json_url,
                    origin_search_url=record.origin_search_url,
                    position=item.get("position"),
                    retrieved_at=record.retrieved_at,
                ),
            )
        )
    return listings
