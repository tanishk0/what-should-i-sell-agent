"""Common product schema shared by every data source.

Design rule: every number shown to the user must be traceable to a SerpAPI
search. Each `Listing` therefore carries a `Citation` that points at the
archived SerpAPI JSON plus the original marketplace search URL.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Source = Literal["amazon", "google_shopping"]


class Citation(BaseModel):
    """Verifiable pointer to the exact search result a datum came from."""

    source: Source
    engine: str
    search_id: Optional[str] = None
    serpapi_json_url: Optional[str] = Field(
        None, description="Archived SerpAPI JSON for the search (re-checkable)."
    )
    origin_search_url: Optional[str] = Field(
        None, description="The marketplace search page SerpAPI scraped."
    )
    position: Optional[int] = Field(None, description="Rank of the result on that page.")
    retrieved_at: Optional[datetime] = None


class Listing(BaseModel):
    """One product listing as seen on one source, normalized."""

    source: Source
    source_product_id: str = Field(..., description="ASIN for Amazon, product_id for Google.")
    title: str
    url: str
    seller: Optional[str] = None
    price: Optional[float] = None
    price_raw: Optional[str] = None
    original_price: Optional[float] = None
    currency: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    bought_last_month: Optional[int] = Field(
        None, description="Amazon 'N+ bought in past month' lower bound."
    )
    sponsored: bool = False
    position: Optional[int] = None
    thumbnail: Optional[str] = None
    badges: list[str] = Field(default_factory=list)
    detail_api_url: Optional[str] = Field(
        None, description="SerpAPI endpoint for product details/reviews (used in later steps)."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation: Citation


class Product(BaseModel):
    """A competing product, possibly merged from several listings/sources."""

    id: str
    title: str
    url: str
    price: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    bought_last_month: Optional[int] = None
    sources: list[Source]
    sponsored_only: bool = False
    relevance: float = 0.0
    score: float = 0.0
    listings: list[Listing] = Field(..., description="Evidence: every listing merged into this product.")


class SearchRecord(BaseModel):
    """Metadata about one SerpAPI call (the root of every citation)."""

    source: Source
    engine: str
    params: dict[str, Any]
    search_id: Optional[str] = None
    serpapi_json_url: Optional[str] = None
    origin_search_url: Optional[str] = None
    total_results: Optional[int] = None
    raw_result_count: int = 0
    retrieved_at: Optional[datetime] = None
    from_cache: bool = False


class ResearchSet(BaseModel):
    """Output of the research foundation step: a clean competitor set."""

    query: str
    market: str
    currency: str
    created_at: datetime
    searches: list[SearchRecord]
    products: list[Product]
    stats: dict[str, Any] = Field(default_factory=dict)
