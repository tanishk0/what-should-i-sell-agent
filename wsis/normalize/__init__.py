"""Source-specific normalizers that map raw SerpAPI JSON to `Listing`s."""
from .amazon import normalize_amazon
from .google_shopping import normalize_google_shopping

__all__ = ["normalize_amazon", "normalize_google_shopping"]
