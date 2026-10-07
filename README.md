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
