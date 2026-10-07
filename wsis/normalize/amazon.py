"""Amazon Search (engine=amazon) -> Listing."""
from __future__ import annotations

from typing import Any, Optional

from ..schema import Citation, Listing, SearchRecord
from .common import currency_from_price, parse_count, to_float

# Fields promoted into the schema; everything else useful goes to metadata.
_METADATA_KEYS = ("options", "variants", "offers", "delivery", "save_with_coupon",
                  "more_buying_choices", "climate_pledge_friendly", "small_business",
                  "sustainability_features")


def normalize_amazon(
    raw: dict[str, Any], record: SearchRecord, *, currency: Optional[str] = None
) -> list[Listing]:
    domain = record.params.get("amazon_domain", "amazon.com")
    listings: list[Listing] = []
    for item in raw.get("organic_results", []) or []:
        asin = item.get("asin")
        title = (item.get("title") or "").strip()
        if not asin or not title:
            continue
        price_raw = item.get("price")
        listings.append(
            Listing(
                source="amazon",
                source_product_id=asin,
                title=title,
                url=item.get("link_clean") or f"https://www.{domain}/dp/{asin}",
                seller="Amazon",
                price=to_float(item.get("extracted_price", price_raw)),
                price_raw=price_raw,
                original_price=to_float(item.get("extracted_old_price")),
                currency=currency_from_price(price_raw, currency),
                rating=to_float(item.get("rating")),
                review_count=parse_count(item.get("reviews")),
                bought_last_month=parse_count(item.get("bought_last_month")),
                sponsored=bool(item.get("sponsored")),
                position=item.get("position"),
                thumbnail=item.get("thumbnail"),
                badges=list(item.get("badges") or []),
                detail_api_url=item.get("serpapi_link"),
                metadata={k: item[k] for k in _METADATA_KEYS if k in item},
                citation=Citation(
                    source="amazon",
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
