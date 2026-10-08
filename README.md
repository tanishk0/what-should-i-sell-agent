# Amazon Market-Gap Research Agent

An evidence-backed research agent for discovering genuine customer complaints, product defects, and market gaps on Amazon India (`amazon.in`) using SerpAPI and Gemini.

---

## What This Agent Does

1. **Searches Amazon India** using SerpAPI to collect competing products.
2. **Collects Customer Reviews** for top competitor listings.
3. **Classifies Customer Complaints** using Gemini LLM strictly from actual review text (with verbatim substring verification).
4. **Clusters Recurring Problems** semantically into problem themes without hardcoded templates.
5. **Programmatically Computes Evidence Counts** directly from actual review and product arrays.
6. **Cross-Checks Problems Across Competitors** to distinguish widespread systemic market gaps from isolated defects, capturing counter-evidence.
7. **Generates an Evidence-Backed Report** with citations, verbatim quotes, and counter-evidence.

> **Zero Speculation Guarantee:** The AI never invents product solutions, fabricates numbers, or tells the seller what to build. It identifies real, verified customer problems with transparent evidence.

---

## Clean Architecture Pipeline

```text
SerpAPI (Amazon India)
  ├── 1. Products Collection & Deduplication
  │      └── SerpClient -> normalize_amazon -> merge_listings -> select_top
  ├── 2. Review Retrieval & Cleaning
  │      └── fetch_product_reviews -> clean_reviews (dedup + noise filter)
  ├── 3. LLM Review Classification
  │      └── ReviewClassifier (Gemini 3.5 Flash) -> verify_evidence (verbatim check)
  ├── 4. Semantic Complaint Clustering
  │      └── cluster_complaints (Gemini 3.5 Flash)
  ├── 5. Programmatic Aggregation (Source of Truth)
  │      ├── review_count = len(supporting_reviews)
  │      ├── product_count = len(supporting_products)
  │      ├── unaffected_products (counter-evidence)
  │      └── is_widespread_gap (cross-check across competitors)
  └── 6. Evidence-Backed Market-Gap Report
         ├── Terminal Report (Rich formatting)
         ├── Markdown Report (*-report.md)
         └── JSON Data Exports & Optional MongoDB Storage
```

---

## Quickstart

### 1. Environment Setup

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Create a `.env` file at the root:

```env
SERPAPI_KEY=your_serpapi_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
DEFAULT_MARKET=in
```

### 2. Run Market Research

```powershell
# Run full market-gap research for sunglasses on Amazon India:
.\.venv\Scripts\python -m wsis "sunglasses" --with-reviews --review-limit 5 --credit-budget 10

# Run for lunch boxes:
.\.venv\Scripts\python -m wsis "lunch box" --with-reviews --review-limit 5

# Offline mode using cached SerpAPI data:
.\.venv\Scripts\python -m wsis "yoga mat" --offline
```

### 3. Run Test Suite

```powershell
.\.venv\Scripts\python -m pytest tests/ -v
```

---

## Key Principles & Guardrails

- **Centralized Model Configuration:** Uses `gemini-3.5-flash` centralized in `wsis/config.py`.
- **Evidence as Source of Truth:** The LLM only classifies and clusters. All review counts, competitor prevalence, and share percentages are calculated programmatically from actual lists.
- **No Unsupported Claims:** Reviews are only attached to a problem if the LLM explicitly assigned that review as evidence for that problem.
- **Counter-Evidence & Cross-Checking:** Highlights competing products where the defect did NOT appear, preventing false generalizations.
- **Fail-Fast Error Handling:** Honest errors are raised immediately if keys are missing or API calls fail; no fake heuristic fallbacks or fabricated outputs.
