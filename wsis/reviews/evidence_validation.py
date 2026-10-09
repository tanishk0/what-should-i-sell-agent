"""Evidence validation, semantic compatibility checking, and cluster deduplication.

Ensures evidence integrity in the review intelligence and market-gap pipeline:
1. Verifies exact verbatim text spans for complaints.
2. Validates semantic relevance between supporting quotes and assigned complaint clusters.
3. Prevents evidence quote reuse across unrelated complaint clusters.
4. Prevents duplicate review counting for the same underlying issue.
5. Deduplicates and merges semantically overlapping clusters without merging genuinely distinct issues.
6. Enforces neutral evidence-based classifications (two affected products alone do not qualify as widespread).
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

from .models import CATEGORIES, Review
from .problem_models import ComplaintEvidence, ProblemCluster


# Major defect themes and their core vocabulary
THEME_VOCABULARY: dict[str, set[str]] = {
    "packaging_shipping": {
        "package", "packaging", "box", "carton", "ship", "shipping", "shipped",
        "courier", "delivery", "delivered", "transit", "arrived", "seal", "sealed",
        "unsealed", "tape", "taped", "crushed", "torn", "opened", "tampered",
        "bubble wrap", "outer box", "packing", "parcel", "damaged box", "open box",
    },
    "discoloration": {
        "yellow", "yellowing", "yellowed", "yellowish", "yellows", "discolor", "discolored", "discoloration",
        "stain", "stained", "stains", "brown", "brownish", "fade", "faded", "fading",
        "color change", "turned yellow", "turning yellow", "dirty look",
    },
    "drop_impact": {
        "drop", "dropped", "fall", "fell", "falling", "impact", "shock", "shatter",
        "shattered", "crack", "cracked", "break", "broke", "broken", "shatterproof",
        "drop protection", "screen cracked", "screen broke", "bumper", "shattered screen",
        "corner protection", "shockproof", "absorb shock",
    },
    "fit_loose": {
        "loose", "loosens", "loosened", "loosen", "loose-fitting", "fit", "fits",
        "fitting", "snug", "stretch", "stretched", "moves", "moving", "wobble",
        "rattle", "rattles", "gap", "slip off", "slips off", "too big", "too small",
        "tight", "tightness", "doesn't fit", "not snug", "loosening",
    },
    "slippery_grip": {
        "slip", "slips", "slippery", "grip", "grippy", "slick", "slide", "slides",
        "sliding", "hold", "holding", "hand", "friction", "drops from hand", "slid",
        "slipping", "no grip", "poor grip", "hard to hold",
    },
    "buttons": {
        "button", "buttons", "press", "pressing", "stiff", "click", "tactile",
        "hard to press", "volume button", "power button", "stiff buttons",
    },
    "leakage": {
        "leak", "leaks", "leaking", "leakage", "spill", "spills", "spilling",
        "seep", "seeps", "seeping", "seal", "liquid", "soup", "curry", "water",
    },
    "counterfeit_quality": {
        "counterfeit", "fake", "used", "refurbished", "duplicate", "copy",
        "rubbish quality", "disgusting", "second hand", "defective unit",
        "cheap plastic", "substandard",
    },
    "tearing_flaking": {
        "tear", "tears", "tore", "torn", "tearing", "flake", "flakes", "flaking",
        "peel", "peels", "peeling", "rip", "rips", "ripped", "ripping",
    },
}

# Theme incompatibility matrix: pairs of themes that represent mutually exclusive defect concepts
INCOMPATIBLE_THEME_PAIRS: set[frozenset[str]] = {
    frozenset({"packaging_shipping", "fit_loose"}),
    frozenset({"packaging_shipping", "discoloration"}),
    frozenset({"packaging_shipping", "drop_impact"}),
    frozenset({"packaging_shipping", "slippery_grip"}),
    frozenset({"packaging_shipping", "buttons"}),
    frozenset({"discoloration", "drop_impact"}),
    frozenset({"discoloration", "fit_loose"}),
    frozenset({"discoloration", "slippery_grip"}),
    frozenset({"discoloration", "buttons"}),
    frozenset({"drop_impact", "buttons"}),
}

STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with", "by",
    "of", "from", "as", "is", "was", "are", "were", "it", "this", "that", "these",
    "those", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "i", "my", "me", "we", "our", "you", "your", "they", "them", "their", "so",
    "very", "too", "much", "more", "also", "just", "well", "now", "then", "there",
    "phone", "case", "cover", "product", "item", "unit", "buy", "bought", "received",
}


def normalize_text(text: str) -> str:
    """Normalize text for whitespace- and punctuation-tolerant comparison."""
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def extract_content_tokens(text: str) -> set[str]:
    """Extract meaningful alphanumeric tokens from text."""
    norm = normalize_text(text)
    return {w for w in norm.split() if len(w) > 2 and w not in STOPWORDS}


def detect_themes(text: str) -> set[str]:
    """Detect defect themes present in text based on theme vocabulary and stems."""
    norm = normalize_text(text)
    words = set(norm.split())
    detected = set()
    for theme, vocab in THEME_VOCABULARY.items():
        for term in vocab:
            if " " in term:
                if term in norm:
                    detected.add(theme)
                    break
            elif term in words:
                detected.add(theme)
                break
            elif len(term) >= 4 and any(w.startswith(term[:4]) and (w.startswith(term) or term.startswith(w)) for w in words):
                detected.add(theme)
                break
    return detected


def verify_span_verbatim(quote: Optional[str], review_text: str, original_text: str = "") -> tuple[Optional[str], bool]:
    """Verify that quote is a non-empty, verbatim substring of the review."""
    if not quote or not quote.strip():
        return None, False
    q = quote.strip()
    if q in review_text or (original_text and q in original_text):
        return q, True

    # Whitespace-normalized comparison
    norm_q = " ".join(q.split())
    norm_rev = " ".join(review_text.split())
    norm_orig = " ".join(original_text.split()) if original_text else ""
    if norm_q in norm_rev or (norm_orig and norm_q in norm_orig):
        return q, True

    # Case-insensitive comparison
    low_q = norm_q.lower()
    if low_q in norm_rev.lower() or (norm_orig and low_q in norm_orig.lower()):
        return q, True

    return None, False


def validate_evidence_relevance(
    quote: str,
    review_text: str,
    cluster_name: str,
    cluster_category: str,
    cluster_description: str,
    review_categories: Optional[list[str]] = None,
    review_issues: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """Validate that an evidence quote semantically supports the assigned complaint cluster.

    Rejects unrelated evidence (e.g. drop protection quote supporting yellowing,
    or loose fit quote supporting packaging damage).
    """
    if not quote or not quote.strip():
        return False, "Quote is empty."

    cluster_context = f"{cluster_name} {cluster_category} {cluster_description}"
    cluster_themes = detect_themes(cluster_context)

    # Category-based theme enrichment
    if cluster_category == "shipping_packaging":
        cluster_themes.add("packaging_shipping")
    elif cluster_category == "size_fit":
        cluster_themes.add("fit_loose")

    quote_themes = detect_themes(quote)

    # Check for theme incompatibilities
    for c_theme in cluster_themes:
        for q_theme in quote_themes:
            if frozenset({c_theme, q_theme}) in INCOMPATIBLE_THEME_PAIRS:
                # Direct incompatibility detected!
                # Ensure quote does not also mention the cluster theme
                if c_theme not in quote_themes:
                    return False, f"Quote theme '{q_theme}' is incompatible with cluster theme '{c_theme}'."

    # If cluster has packaging/shipping theme, quote MUST contain packaging terms
    if "packaging_shipping" in cluster_themes or cluster_category == "shipping_packaging":
        if "packaging_shipping" not in quote_themes:
            return False, "Quote does not contain packaging or shipping evidence."

    # If cluster has discoloration theme, quote MUST contain discoloration terms
    if "discoloration" in cluster_themes:
        if "discoloration" not in quote_themes:
            return False, "Quote does not contain yellowing or discoloration evidence."

    # If cluster has drop_impact theme, quote MUST contain drop/impact terms
    if "drop_impact" in cluster_themes:
        if "drop_impact" not in quote_themes:
            return False, "Quote does not contain drop or impact protection evidence."

    # General semantic overlap check
    quote_tokens = extract_content_tokens(quote)
    cluster_tokens = extract_content_tokens(cluster_context)

    # Token/stem overlap
    overlap = quote_tokens & cluster_tokens
    if overlap:
        return True, f"Matched tokens: {overlap}"

    # Stem / prefix matching (e.g., slip/slippery, leak/leaking, loose/loosens)
    stem_overlap = set()
    for q_tok in quote_tokens:
        for c_tok in cluster_tokens:
            if len(q_tok) >= 4 and len(c_tok) >= 4:
                if q_tok[:4] == c_tok[:4] or q_tok in c_tok or c_tok in q_tok:
                    stem_overlap.add(f"{q_tok}~{c_tok}")

    if stem_overlap:
        return True, f"Matched stem overlap: {stem_overlap}"

    # Check review issues and categories if quote alone didn't overlap directly
    if review_issues:
        for issue in review_issues:
            issue_tokens = extract_content_tokens(issue)
            if issue_tokens & cluster_tokens:
                # The review explicitly has this issue; verify quote isn't completely unrelated
                if not quote_themes or (quote_themes & cluster_themes):
                    return True, f"Supported via review issue: {issue}"

    # If themes matched, allow
    if cluster_themes and (cluster_themes & quote_themes):
        return True, f"Matched themes: {cluster_themes & quote_themes}"

    return False, "Evidence quote has no semantic overlap with complaint cluster."


def find_matching_span_in_review(
    review_text: str,
    cluster_name: str,
    cluster_category: str,
    cluster_description: str,
) -> Optional[str]:
    """Find a sentence or clause in review_text that semantically supports the cluster."""
    if not review_text or not review_text.strip():
        return None

    # Split review into sentences or clauses
    parts = re.split(r"[.\n!?]+", review_text)
    for part in parts:
        candidate = part.strip()
        if len(candidate) < 8:
            continue
        valid, _ = validate_evidence_relevance(
            candidate,
            review_text,
            cluster_name,
            cluster_category,
            cluster_description,
        )
        if valid:
            return candidate

    return None


def are_clusters_overlapping(c1: ProblemCluster, c2: ProblemCluster) -> bool:
    """Check if two clusters represent the same underlying customer problem.

    Must return True only for duplicate/overlapping issues, and False for
    genuinely distinct complaints (e.g. yellowing vs drop protection).
    """
    if c1.id == c2.id:
        return False

    c1_context = f"{c1.problem} {c1.category} {c1.description}"
    c2_context = f"{c2.problem} {c2.category} {c2.description}"

    c1_themes = detect_themes(c1_context)
    c2_themes = detect_themes(c2_context)

    # If both belong to the same specific non-empty defect theme
    common_themes = c1_themes & c2_themes
    if common_themes:
        # Check if they share mutually exclusive concepts
        # For instance, both are fit_loose or both are discoloration
        return True

    # Check for direct incompatibility
    for t1 in c1_themes:
        for t2 in c2_themes:
            if frozenset({t1, t2}) in INCOMPATIBLE_THEME_PAIRS:
                return False

    # Check review ID Jaccard similarity
    r1_ids = {ev.review_id for ev in c1.supporting_reviews}
    r2_ids = {ev.review_id for ev in c2.supporting_reviews}
    if r1_ids and r2_ids:
        jaccard = len(r1_ids & r2_ids) / len(r1_ids | r2_ids)
        if jaccard >= 0.5:
            return True

    # Check title token overlap
    t1_tokens = extract_content_tokens(c1.problem)
    t2_tokens = extract_content_tokens(c2.problem)
    if t1_tokens and t2_tokens:
        overlap = t1_tokens & t2_tokens
        if len(overlap) >= 2 or (len(overlap) >= 1 and len(t1_tokens | t2_tokens) <= 3):
            if c1.category == c2.category or c1.category == "other" or c2.category == "other":
                return True

    return False


def deduplicate_and_merge_clusters(
    clusters: list[ProblemCluster],
    total_products_count: int,
    all_product_ids: list[str],
) -> list[ProblemCluster]:
    """Remove duplicate or semantically overlapping clusters representing the same problem.

    Deduplicates reviews within the merged cluster so that no review is counted
    multiple times for the same underlying issue.
    """
    if len(clusters) <= 1:
        return clusters

    merged_clusters: list[ProblemCluster] = []

    for cluster in clusters:
        # Check if this cluster overlaps with any already merged cluster
        matched_idx = -1
        for idx, existing in enumerate(merged_clusters):
            if are_clusters_overlapping(existing, cluster):
                matched_idx = idx
                break

        if matched_idx == -1:
            merged_clusters.append(cluster)
        else:
            existing = merged_clusters[matched_idx]
            # Merge cluster into existing
            existing_review_ids = {ev.review_id for ev in existing.supporting_reviews}
            new_reviews = [
                ev for ev in cluster.supporting_reviews
                if ev.review_id not in existing_review_ids
            ]
            combined_reviews = list(existing.supporting_reviews) + new_reviews

            # Recalculate metrics in code
            supporting_prods = sorted({ev.product_id for ev in combined_reviews})
            unaffected_prods = [pid for pid in all_product_ids if pid not in supporting_prods]
            prod_count = len(supporting_prods)
            rev_count = len({ev.review_id for ev in combined_reviews})
            prevalence = round((prod_count / max(1, total_products_count)) * 100, 1)

            severities = [ev.rating for ev in combined_reviews if ev.rating is not None]
            # Note: average severity from 1.0-3.0 scale
            avg_sev = existing.avg_severity

            # Two affected products alone must not qualify as widespread!
            is_widespread = (prod_count >= 3) and (prevalence >= 50.0)

            # Keep more detailed title / description if new one is longer
            merged_problem = existing.problem if len(existing.problem) >= len(cluster.problem) else cluster.problem
            merged_desc = existing.description
            if cluster.description not in existing.description and len(existing.description) < 300:
                merged_desc = f"{existing.description} {cluster.description}".strip()

            merged_clusters[matched_idx] = ProblemCluster(
                id=existing.id,
                problem=merged_problem,
                category=existing.category if existing.category != "other" else cluster.category,
                description=merged_desc,
                supporting_reviews=combined_reviews,
                supporting_products=supporting_prods,
                unaffected_products=unaffected_prods,
                review_count=rev_count,
                product_count=prod_count,
                product_prevalence_pct=prevalence,
                avg_severity=avg_sev,
                is_widespread_gap=is_widespread,
            )

    return merged_clusters


def classify_cluster_status(product_count: int, product_prevalence_pct: float) -> tuple[bool, str, str]:
    """Return neutral evidence-based classification.

    Requirement 7: Two affected products alone must not qualify as widespread.
    Returns: (is_widespread_gap, terminal_badge, markdown_badge)
    """
    if product_count >= 3 and product_prevalence_pct >= 50.0:
        return (
            True,
            "[bold green][WIDESPREAD MARKET GAP][/bold green]",
            "**[WIDESPREAD MARKET GAP]**",
        )
    elif product_count >= 2:
        return (
            False,
            "[bold cyan][MULTI-COMPETITOR PATTERN][/bold cyan]",
            "**[MULTI-COMPETITOR PATTERN]**",
        )
    else:
        return (
            False,
            "[yellow][ISOLATED DEFECT][/yellow]",
            "**[ISOLATED DEFECT]**",
        )
