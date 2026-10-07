# What Should I Sell — SerpAPI market research agent

## Step 1: Research foundation ✅
One query → a clean, deduplicated, **cited** set of ~20–30 competing products from
**Amazon** (`engine=amazon`) and **Google Shopping** (`engine=google_shopping`).

```powershell
python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements.txt
# .env  ->  SERPAPI_KEY=...
.\.venv\Scripts\python -m wsis "yoga mat" --market us --limit 30
.\.venv\Scripts\python -m pytest            # offline, uses real captured responses
```

Flags: `--market us|uk|in|ca|au|de|fr|jp`, `--amazon-pages N`, `--min-relevance 0.5`,
`--no-cache` (force fresh), `--offline` (cache only). Output → `data/runs/*.json`.

### Pipeline
`fetch (2 SerpAPI calls, disk-cached)` → `normalize → Listing` → `drop no-price / wrong currency`
→ `merge duplicates → Product` → `relevance filter` → `score & pick top N (both sources guaranteed)`

### Schema ([wsis/schema.py](wsis/schema.py))
- **Listing**: one result on one source: id (ASIN / Google product_id), title, url, seller,
  price, original_price, currency, rating, review_count, bought_last_month, sponsored,
  position, badges, `detail_api_url` (for the reviews step), metadata, **citation**.
- **Citation**: engine, search_id, `serpapi_json_url` (archived raw JSON), the marketplace
  search URL, the result's position, and when it was retrieved.
- **Product**: canonical competitor merged from ≥1 listings (price min/max, sources, relevance, score).
- **ResearchSet**: query, market, searches[], products[], funnel stats.

---

## Step 2: Review intelligence ✅
Goal: Understand what buyers actually dislike across competitors without hallucination.

```powershell
# In .env:
# SERPAPI_KEY=...
# GEMINI_API_KEY=... (optional, falls back to heuristic classifier if omitted)

# Run research + review intelligence for top 5 competitors:
.\.venv\Scripts\python -m wsis "yoga mat" --with-reviews --review-limit 5 --credit-budget 10
```

### Review Intelligence Pipeline ([wsis/reviews/pipeline.py](wsis/reviews/pipeline.py))
1. **Credit Budget Guard (`CreditBudget`)**:
   - Enforces a hard budget limit on *fresh* SerpAPI calls (cached calls cost 0 credits).
   - Essential for free tier / 200 credits quota.
2. **Review Retrieval (`fetch.py`)**:
   - Amazon: retrieves `reviews_information` (aspect insights, customer sentiment summaries, reviewer quotes with permalinks).
   - Google Shopping: retrieves `user_reviews` aggregated across retailers (Target, Walmart, etc.) with ratings and reviewer names.
   - Retains original review text, URLs, and SerpAPI citations.
3. **Cleaning & Deduplication (`clean.py`)**:
   - Trims boilerplate ("Read more..."), drops noise/gibberish.
   - Deduplicates identical review IDs, exact text across multiple aspect tags, and near-duplicates.
   - Merges metadata without losing citations.
4. **LLM Classification with Verbatim Evidence Verification (`classify.py`)**:
   - Uses **Google Gemini** (`gemini-2.5-flash`) via `google-genai` SDK with structured JSON schemas.
   - Categorizes complaints into structured frustration buckets (`durability`, `performance`, `comfort_ergonomics`, `materials_safety`, etc.).
   - Extracts specific issues and severity ratings (1-3).
   - **Zero Hallucination Guarantee**: Extracts `evidence_quote` and programmatically validates that it is an exact, verbatim substring of the customer's review text (`evidence_verified: True`).
   - Graceful fallback: If `GEMINI_API_KEY` is not present, runs an offline heuristic classifier.

---

## Step 3: Discover recurring problems (Clustering) ✅
Goal: Turn thousands of individual complaints into meaningful, ranked problem themes.

```powershell
# Evaluates competitors, extracts reviews, and clusters recurring pain points:
.\.venv\Scripts\python -m wsis "yoga mat" --with-reviews --review-limit 5
```

### Clustering Pipeline ([wsis/reviews/clustering.py](wsis/reviews/clustering.py))
1. **Complaint Synthesis**: Aggregates verified buyer complaints across all evaluated competitors.
2. **Semantic Clustering**:
   - Uses **Google Gemini** (`gemini-2.5-flash`) to group complaints into root pain point clusters with actionable names, category taxonomy, and 2-3 sentence problem explanations.
   - Offline heuristic fallback groups complaints based on classification taxonomy and key issue tags.
3. **Opportunity & Severity Scoring**:
   - Computes average severity (1.0 - 3.0), complaint frequency share, and competitor breadth (how many competing brands exhibit this failure).
   - Generates an `opportunity_score` indexing the highest potential areas for a new product to solve.
4. **Verbatim Evidence Linking**:
   - Every `ProblemCluster` stores verified complaint citations (`ComplaintEvidence`) including review ID, original text, star rating, product URL, and SerpAPI search endpoint.
   - Output saved to `data/runs/<query>-<timestamp>-problems.json`.

---

## MongoDB Persistence

WSIS automatically persists research runs to MongoDB when configured via `.env`:

```env
# In .env:
MONGODB_URI=mongodb://localhost:27017/  # or MongoDB Atlas URI
MONGO_DB_NAME=wsis                      # optional, defaults to wsis
```

### Collections Schema:
- **`research_runs`**: Complete `ResearchSet` runs with query, market, citations, and stats.
- **`products`**: Canonical competitor products indexed by `(run_id, id)` and `(query, score)` for easy cross-run queries.
- **`review_intelligence`**: Detailed buyer sentiment and verified complaints per competitor.
- **`problem_analyses`**: Clustered problem summaries with methodology and metadata.
- **`problem_clusters`**: Individual problem themes indexed by `(query, opportunity_score)` and `category`.

*Note: If `MONGODB_URI` is omitted, WSIS safely operates in file-only mode writing to `data/runs/`.*
