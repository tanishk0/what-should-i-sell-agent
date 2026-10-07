"""Step 7: evidence-traceable product specification."""
from .builder import build_product_spec, spec_to_markdown
from .models import DroppedItem, EvidenceRef, ProductSpec, SpecItem

__all__ = [
    "EvidenceRef",
    "SpecItem",
    "DroppedItem",
    "ProductSpec",
    "build_product_spec",
    "spec_to_markdown",
]
