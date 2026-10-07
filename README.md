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

## Step 4: Generate candidate opportunities ✅
Goal: Convert recurring buyer problems into actionable, differentiated product opportunities.

For each major problem cluster discovered in Step 3, the agent queries the model:
> *"What product improvement could directly solve this problem?"*

```powershell
# Full pipeline: research competitors -> fetch reviews -> discover problems -> generate opportunities:
.\.venv\Scripts\python -m wsis "yoga mat" --with-reviews --review-limit 5 --max-opportunities 10
```

### Opportunity Generation Pipeline ([wsis/opportunities/generator.py](wsis/opportunities/generator.py))
1. **Core Problem Prompting**:
   - Evaluates top problem clusters ranked by `opportunity_score`.
   - Uses **Google Gemini** (`gemini-2.5-flash`) via structured JSON schema to formulate targeted solutions.
   - Offline heuristic fallback provides domain-tailored improvements based on complaint category & keywords.
2. **Candidate Opportunity Schema ([wsis/opportunities/models.py](wsis/opportunities/models.py))**:
   - `title`: Benefit-driven, memorable product improvement concept.
   - `problem_id` & `problem_name`: Linked directly to the root problem cluster.
   - `improvement_type`: Innovation classification (`material_upgrade`, `mechanical_redesign`, `manufacturing_process`, `feature_addition`, `ergonomic_enhancement`, `bundle_accessory`).
   - `improvement_concept`: Direct engineering and design answer to what solves the problem.
   - `differentiation_angle`: Marketing and positioning angle against incumbent competitors.
   - `implementation_feasibility`: Feasibility rating (`high`, `medium`, `low`).
   - `target_price_impact`: Pricing tiers (`cost_neutral`, `minor_premium`, `premium_tier`).
   - `priority_score`: Calculated from problem opportunity score × feasibility multiplier.
   - `supporting_evidence_quotes`: Direct verbatim buyer quotes grounding the opportunity.
3. **Output Artifacts**:
   - Saved locally to `data/runs/<query>-<timestamp>-opportunities.json`.

---

## Step 5: Agentic challenge loop (The Hackathon Core) ⚡
Instead of naively prompting an LLM *"What should I sell?"*, WSIS executes an adversarial validation loop:

```
Research competitors
        ↓
Find recurring problem
        ↓
Form opportunity hypothesis
        ↓
Search again
        ↓
Look for contradictory evidence
        ↓
Check additional competitors
        ↓
Strengthen / weaken hypothesis
        ↓
Final opportunity
```

```powershell
# Run full end-to-end pipeline with agentic challenge loop:
.\.venv\Scripts\python -m wsis "yoga mat" --with-reviews --review-limit 5
```

### The Challenge Mechanism ([wsis/challenge/loop.py](wsis/challenge/loop.py))
1. **Hypothesis Formulation**: Converts Step 4 candidates into testable, falsifiable claims and generates adversarial search queries.
2. **Search Again & Broader Cohort Audit**: Audits expanded competitors (e.g., 15 competitors across the category) and executes targeted verification queries.
3. **Contradictory Evidence Mining**:
   - **Isolated Defect Check**: If complaints occur in only a small minority of competitors (e.g. **2/15 products** or <25%), the agent recognizes this as an isolated vendor issue rather than an industry gap, and **downgrades** the opportunity.
   - **Incumbent Pre-emption Check**: Checks whether high-rated competitors (≥4.7★) already solve this problem with high satisfaction.
   - **Trade-off Detection**: Flags negative side-effects caused by proposed improvements.
4. **Corroborating Evidence Mining**:
   - **Widespread Category Failure**: If complaints span ≥50% of competitors, the agent **strengthens** the opportunity.
5. **Verdict & Score Recalibration**:
   - `STRENGTHENED`: +25% score boost, high conviction (`PURSUE_HIGH_CONVICTION`).
   - `CONFIRMED`: Maintained score, moderate conviction (`PROCEED_WITH_CAUTION`).
   - `WEAKENED`: -30% score discount (`PROCEED_WITH_CAUTION`).
   - `DOWNGRADED`: -55% score discount, flagged as high risk (`DE-PRIORITIZE`).
6. **Artifact Output**:
   - Saved locally to `data/runs/<query>-<timestamp>-challenge.json`.

---

## Step 6: Build competitor assessment & market gap analysis ✅
For the validated opportunity, the agent builds a head-to-head competitor matrix and answers:
> **"Where is the gap?"**

```powershell
# Full pipeline through competitor assessment:
.\.venv\Scripts\python -m wsis "yoga mat" --with-reviews --review-limit 5
```

### Competitor Matrix Output ([wsis/assessment/builder.py](wsis/assessment/builder.py))
```
Competitor     Price     Rating    Main Strength    Problem
Product A      ₹699      4.2       Compact          Leaks
Product B      ₹899      4.4       Durable          Bulky
Product C      ₹599      4.0       Cheap            Poor seal
```

### Strategic Gap Analysis
- **Where is the gap?**: Synthesizes the exact price and performance whitespace across price tiers.
- **Unmet Need**: Pinpoints what combination of benefits no existing competitor delivers.
- **Target Price Window**: Identifies the margin-healthy pricing window (e.g. `₹749 - ₹849` or `$28 - $35`).
- **Trade-off to Break**: Identifies false compromises buyers currently make (e.g. `Compact vs Leakproof`, `Soft cushioning vs High traction`).
- **Winning Positioning**: Concise value proposition for market entry.
- Output saved to `data/runs/<query>-<timestamp>-assessment.json`.

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
- **`opportunity_analyses`**: Step 4 candidate product opportunities runs.
- **`candidate_opportunities`**: Individual product improvement opportunities indexed by `(query, priority_score)`, `problem_id`, and `category`.
- **`challenge_runs`**: Step 5 agentic challenge loop runs stress-testing hypotheses.
- **`final_opportunities`**: Validated and re-ranked final product opportunities indexed by `(query, final_score)`, `verdict`, and `recommendation`.
- **`competitor_assessments`**: Step 6 competitive matrices and strategic market gap analyses.
- **`competitor_profiles`**: Individual competitor benchmarks indexed by `(run_id, id)`.

*Note: If `MONGODB_URI` is omitted, WSIS safely operates in file-only mode writing to `data/runs/`.*
