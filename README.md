# StrategicAILeader Content Authority Hub

A FastAPI-based tool for crawling, embedding, clustering, and analyzing content for SEO and internal linking optimization.  

## Requirements
- Python 3.11+
- SQLite (bundled) or a Postgres URL for `DATABASE_URL`
- (Optional) OpenAI API key if using OpenAI embeddings

- Google API libraries: `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, and `google-auth-httplib2`


## Setup
cd ~/Documents/python-projects/strategicaileader_content_authority_hub
### Install
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
### Starting the App
pkill -f "uvicorn.*8001" || true
kill -9 $(lsof -ti:8001) 2>/dev/null || true
cd ~/Documents/python-projects/strategicaileader_content_authority_hub
source venv/bin/activate
export DATABASE_URL=sqlite:///./data/app.db
python -m uvicorn src.main:app --reload --port 8001

### Environment Variables
Set at least the following (examples shown for the hash test provider):
```bash
export DATABASE_URL=sqlite:///./data/app.db
export EMBEDDING_PROVIDER=hash128     # options: openai | hash128
export EMBEDDING_DIM=128              # 3072 for OpenAI, 128/256 for hash128
export APP_DEBUG=1                    # optional: verbose logs
# If using OpenAI:
# export OPENAI_API_KEY=sk-...
# --- Google Analytics 4 (GA4) OAuth ---
export GA4_CLIENT_ID=...
export GA4_CLIENT_SECRET=...
export GA4_REFRESH_TOKEN=...

# --- Google Search Console (GSC) OAuth ---
export GSC_CLIENT_ID=...
export GSC_CLIENT_SECRET=...
export GSC_REFRESH_TOKEN=...

# If using service accounts:
# export GOOGLE_APPLICATION_CREDENTIALS=./keys/ga4-service.json
```

### Database & Migrations
Initialize the database schema via Alembic:
```bash
export DATABASE_URL=sqlite:///./data/app.db
alembic upgrade head
```

## Running Locally
```bash
export DATABASE_URL=sqlite:///./data/app.db
export EMBEDDING_PROVIDER=hash128
export EMBEDDING_DIM=128
python -m uvicorn src.main:app --reload --port 8001
```

Open the docs at: `http://127.0.0.1:8001/docs`

## Retrieval (Phase 9 — Semantic Search & RAG)

> Phase 9 adds a minimal-but-usable retrieval layer with a simple RAG-lite answer endpoint. It works with SQLite or Postgres and does **not** require an embeddings service for the demo path (it falls back to a deterministic hash embeddings provider by default).

### Enable & Run
```bash
# Choose your DB (SQLite shown)
export DATABASE_URL=sqlite:///./data/app.db

# Retrieval defaults
export ENABLE_RETRIEVAL=1
export EMBEDDING_PROVIDER=hash128   # options: hash128 | openai
export EMBEDDING_DIM=128            # 128/256 for hash128, 3072 for OpenAI

# Start API on port 8001
pkill -f "uvicorn.*8001" || true
python -m uvicorn src.main:app --reload --port 8001
```

### Demo Data (seed)
```bash
# Seed a tiny site (creates 6 nodes / 6 edges)
PYTHONPATH=.:src python scripts/seed_demo.py --domain example.com --flush
```

### Endpoints
- `GET /retrieval/health` → `{ "status": "ok", "ok": true }`
- `GET /retrieval/search` → hybrid-ready search (currently heuristic; Phase 9 will add BM25 + embeddings blend)
  - Params: `q` (required), `top_k` (default 10), `site_id` or `domain`, `since_days`, `content_type`, `offset`
- `POST /retrieval/reindex` → accept reindex request (idempotent)
  - Body: `{ "domain": "example.com", "refresh_embeddings": false }`
- `POST /retrieval/answer` → RAG‑lite extractive answer using top search results
  - Body: `{ "q": "...", "top_k": 5, "site_id": 3, "max_tokens": 200, "since_days": 30, "content_type": "post" }`

### Copy‑paste Examples
```bash
BASE="http://127.0.0.1:8001"

# Health
curl -s "$BASE/retrieval/health" | jq .

# Reindex a domain (Phase 9 accepts and responds; background indexing to follow)
curl -s -X POST "$BASE/retrieval/reindex" \
  -H 'Content-Type: application/json' \
  -d '{"domain":"example.com","refresh_embeddings":false}' | jq .

# Search within a domain
curl -s "$BASE/retrieval/search?q=pillar&domain=example.com&top_k=5" | jq .

# Date/content filters
curl -s "$BASE/retrieval/search?q=deep&domain=example.com&since_days=7&content_type=post" | jq .

# Ask for an answer (RAG‑lite)
curl -s -X POST "$BASE/retrieval/answer" \
  -H 'Content-Type: application/json' \
  -d '{"q":"pillar page","domain":"example.com","top_k":3,"max_tokens":120}' | jq .
```

### Makefile targets (Phase 9)
> If you see `*** missing separator. Stop.`, ensure Makefile recipe lines are indented with **Tabs**, not spaces.
```make
# Start API with retrieval enabled on port 8001
dev-retrieval:
	@export ENABLE_RETRIEVAL=1; \
	export DATABASE_URL?=sqlite:///./data/app.db; \
	uvicorn src.main:app --reload --port 8001

# Seed the demo content (6 docs)
demo-seed:
	@PYTHONPATH=.:src python scripts/seed_demo.py --domain example.com --flush

# Quick search example
retrieval-search:
	@curl -s "http://127.0.0.1:8001/retrieval/search?q=$${Q:-pillar}&domain=$${DOMAIN:-example.com}&top_k=$${TOPK:-5}" | jq .

# Quick answer example
retrieval-answer:
	@curl -s -X POST "http://127.0.0.1:8001/retrieval/answer" \
	  -H 'Content-Type: application/json' \
	  -d '{"q":"'$${Q:-pillar page}'","domain":"'$${DOMAIN:-example.com}'","top_k":'$${TOPK:-3}',"max_tokens":'$${TOK:-120}'}' | jq .
```

### Notes & Roadmap
- Current ranking is a lightweight heuristic. Phase 9 increments will:
  - add **sparse** (BM25/FTS) + **dense** (embeddings) hybrid scoring with configurable blend,
  - add **recency boost** and better snippets,
  - add **observability**: `took_ms`, cache flags, hit counts,
  - wire a background **indexer** for embeddings & FTS rebuilds.

## Key Endpoints

### Service & Health
- `GET /` – service metadata
- `GET /health` – overall health + DB check
- `GET /clusters/health` – clustering subsystem check

### Clustering
- `GET /clusters/preview?domain=...&k=8&top_n=3&max_items=300`  
  Returns k-means preview (no DB writes).
- `GET /clusters/topics?domain=...&k=8&top_n=6&samples_per_cluster=5&seed=42&stopwords_extra=ai,seo,saas&dedupe_substrings=true`  
  Returns topic labels per cluster using TF‑IDF over titles/content with options:
  - `top_n` – number of top terms for the label.
  - `samples_per_cluster` – example titles returned.
  - `seed` – deterministic sampling.
  - `stopwords_extra` – comma‑separated custom stopwords to suppress brand/generic words.
  - `dedupe_substrings` – when true, removes near‑duplicate terms like `"leader"` vs `"leadership"`.
- `POST /clusters/commit`  
  Body:
  ```json
  {"domain":"example.com","k":8,"seed":42,"max_items":800}
  ```
  Commits `cluster_id` to `content_items`.
- `POST /clusters/clear`  
  Body:
  ```json
  {"domain":"example.com"}
  ```
  Clears `cluster_id` for the domain.
- `GET /clusters/status?domain=...`  
  Returns totals: items, with embeddings, with cluster_id, distinct clusters, dim.

- `GET /clusters/internal-links?domain=...&per_item=3&min_sim=0.45&max_items=500&fallback_when_empty=false`  
  Suggests internal links based on cosine similarity over embeddings.  
  Supports `per_item`, `min_sim`, `max_items`, `fallback_when_empty`, and `exclude_regex` (URL‑encode it). Example to exclude tag/category pages:
  ```
  GET /clusters/internal-links?domain=...&per_item=3&min_sim=0.5&exclude_regex=%5E/tag/|/category/
  ```

### Embeddings
- `POST /content/reembed`  
  Regenerate embeddings.
  Body examples:
  ```json
  {"domain":"example.com","scope":"all"}
  {"domain":"example.com","scope":"missing","batch_size":400}
  {"domain":"example.com","scope":"all","provider":"openai"}
  ```
- `GET /content/embedding-info`  
  Reports active provider & dimension. Accepts optional overrides to *simulate* settings:
  - `GET /content/embedding-info?provider=openai&dim=3072`
  - `GET /content/embedding-info?provider=hash128&dim=256`


### Analytics Endpoints
- `POST /analytics/ingest/ga4`  
  Ingest Google Analytics 4 data. Requires OAuth credentials in live mode.
- `POST /analytics/ingest/gsc`  
  Ingest Google Search Console data. Requires OAuth credentials in live mode.
- `GET /analytics/snapshots?domain=...&limit=5`  
  Retrieve recent analytics snapshots for the domain.
- `GET /analytics/latest?domain=...`  
  Retrieve the latest analytics snapshot for the domain.
- `GET /analytics/summary?domain=...`  
  Get summarized analytics for the domain.
- `GET /analytics/config`  
  Retrieve current analytics configuration and OAuth status.

### Graph Export
- `GET /graph/export` — returns a JSON object with `nodes`, `edges`, and `meta`.
- `POST /graph/recompute` — recomputes graph metrics (e.g., PageRank, hub/authority) and returns fresh JSON.

Example to export the graph to a local file:
```bash
mkdir -p graph/export
curl -s http://localhost:8000/graph/export -o graph/export/graph.json
```

### Phase 10: Semantic Overlap & Density (SOD + Extractability)

Phase 10 adds semantic content scoring to evaluate how well pages perform for both search engines and LLMs.  
You can now measure overlap, density, and extractability per chunk and export results for analysis.

- `POST /content/chunk` — split content into chunks for scoring.
- `POST /semantic/score` — compute overlap, density, and extractability scores for all chunks of a domain.
- `GET /semantic/page/{id}` — inspect chunk-level scores for a single content item.
- `GET /semantic/dashboard?domain=...` — summary view with page counts, quick wins, and scoring distribution.
- `GET /semantic/export?domain=...` — export scores to CSV with columns: url, title, avg_overlap, avg_density, extractability, chunks.

Example export to CSV:
```bash
curl -s -D headers.txt "http://127.0.0.1:8001/semantic/export?domain=strategicaileader.com" -o phase10_semantic_export.csv
head -n 5 phase10_semantic_export.csv
```

## Quickstart (happy path)
```bash
# 1) Migrate DB
export DATABASE_URL=sqlite:///./data/app.db
alembic upgrade head

# 2) Run API
export EMBEDDING_PROVIDER=hash128
export EMBEDDING_DIM=128
python -m uvicorn src.main:app --reload --port 8001

# 3) Sanity checks
curl -s http://127.0.0.1:8001/health | jq
curl -s "http://127.0.0.1:8001/clusters/status?domain=strategicaileader.com" | jq

# 4) (Optional) Re-embed
curl -s -X POST "http://127.0.0.1:8001/content/reembed" \
  -H "Content-Type: application/json" \
  -d '{"domain":"strategicaileader.com","scope":"all"}' | jq

# 5) Cluster
curl -s "http://127.0.0.1:8001/clusters/preview?domain=strategicaileader.com&k=8&top_n=3&max_items=300" | jq
curl -s -X POST "http://127.0.0.1:8001/clusters/commit" \
  -H "Content-Type: application/json" \
  -d '{"domain":"strategicaileader.com","k":8,"seed":42,"max_items":800}' | jq

# 6) Internal linking suggestions
curl -s "http://127.0.0.1:8001/clusters/internal-links?domain=strategicaileader.com&per_item=3&min_sim=0.45&max_items=500" | jq


# 7) Graph Export
curl -s http://127.0.0.1:8001/graph/export | jq .
curl -s -X POST http://127.0.0.1:8001/graph/recompute | jq .
```

## Refresh Token Setup

To generate refresh tokens for Google Analytics 4 (GA4) and Google Search Console (GSC), run the following script:

```bash
python scripts/get_refresh_token.py
```

Follow the prompts to authorize access and generate refresh tokens. Paste the resulting tokens into your `.env` file or environment variables under `GA4_REFRESH_TOKEN` and `GSC_REFRESH_TOKEN` respectively.


## Verification & Diagnostics (copy‑paste)

Once the API is running, you can verify deterministic behavior and link suggestions with the commands below.

```bash
# Set base URL and domain once
BASE="http://127.0.0.1:8001"
DOMAIN="strategicaileader.com"

echo "== Health checks =="
curl -s "$BASE/health" | jq .
curl -s "$BASE/clusters/health" | jq .
curl -s "$BASE/content/embedding-info" | jq .

echo
echo "== Deterministic preview (k=8, seed=42) =="
curl -s "$BASE/clusters/preview?domain=$DOMAIN&k=8&seed=42" | jq '.k_effective'

echo
echo "== Deterministic topics (extra stopwords: ai, seo, saas) =="
curl -s "$BASE/clusters/topics?domain=$DOMAIN&k=8&seed=42&stopwords_extra=ai,seo,saas&dedupe_substrings=true" | jq '.clusters[0]'

echo
echo "== Internal links excluding tag/category pages =="
# exclude_regex is URL-encoded: ^/tag/|/category/
curl -s "$BASE/clusters/internal-links?domain=$DOMAIN&per_item=3&min_sim=0.5&exclude_regex=%5E/tag/|/category/" | jq '.suggestions[:10]'

echo
echo "== Commit cluster assignments (k=8, seed=42) =="
curl -s -X POST "$BASE/clusters/commit" \
  -H "Content-Type: application/json" \
  -d "{\"domain\":\"$DOMAIN\",\"k\":8,\"seed\":42,\"max_items\":1000}" | jq .

echo
echo "== Cluster status (after commit) =="
curl -s "$BASE/clusters/status?domain=$DOMAIN" | jq .

echo
echo "== Clear cluster assignments (cleanup) =="
curl -s -X POST "$BASE/clusters/clear" \
  -H "Content-Type: application/json" \
  -d "{\"domain\":\"$DOMAIN\"}" | jq .

echo
echo "== Cluster status (after clear) =="
curl -s "$BASE/clusters/status?domain=$DOMAIN" | jq .
```

### Notes
- **Determinism**: Passing `seed=42` produces stable cluster assignments for previews, topic labels, and internal link sampling.
- **Stopwords**: Use `stopwords_extra` to add comma‑separated terms (e.g., `ai,seo,saas,strategic`) and reduce noisy labels.
- **Dedupe**: Set `dedupe_substrings=true` on `/clusters/topics` to collapse near‑duplicate label terms (`leader` vs `leadership`, `ops` vs `operations`).
- **Exclusions**: Use `exclude_regex` (URL‑encoded) to filter out non‑article pages (e.g., `/tag/`, `/category/`) in link suggestions.
- **Commit vs Preview**: `preview` never writes to DB. `commit` writes `cluster_id` onto `content_items`. `clear` sets `cluster_id=NULL`.

- **Graph Export**: Orphan nodes (with no edges) are included with metrics; duplicate/self-loop edges are filtered.


## Running Tests

The repo includes smoke tests for routing and clustering flows.

```bash
# Make sure your virtualenv is active and the API is not already bound to 8001
pkill -f "uvicorn.*8001" || true

# Start the API in one terminal
DATABASE_URL=sqlite:///./data/app.db EMBEDDING_PROVIDER=hash128 EMBEDDING_DIM=128 \
python -m uvicorn src.main:app --reload --port 8001

# In another terminal, run tests:
pytest -q
```


# Focused graph tests
pytest -q tests/test_graph_api.py tests/test_graph_export.py

Focused examples you can run manually:
```bash
# Topics with custom stopwords and dedupe
curl -s "$BASE/clusters/topics?domain=$DOMAIN&k=8&seed=42&stopwords_extra=ai,seo,saas&dedupe_substrings=true" | jq '.clusters[0]'

# Internal links excluding tag/category pages
curl -s "$BASE/clusters/internal-links?domain=$DOMAIN&per_item=3&min_sim=0.5&exclude_regex=%5E/tag/|/category/" | jq '.suggestions[:10]'
```

## Provider Notes
- **`hash128`**: fast, deterministic test provider (great for local/dev); dimensions 128 or 256.
- **`openai`**: production-quality semantic embeddings; set `EMBEDDING_DIM=3072` and `OPENAI_API_KEY`.

## Troubleshooting
- **`Address already in use` when starting Uvicorn**  
  A previous server is running. Stop it:
  ```bash
  pkill -f "uvicorn.*8001" || true
  ```
- **SQLite constraint/DDL errors in Alembic**  
  We use SQLite-safe batch migrations. Ensure you ran `alembic upgrade head` with the correct `DATABASE_URL`.
- **No internal link suggestions**  
  Lower `min_sim` or increase `per_item`. Ensure content has embeddings (`/clusters/status`).

- **Generating Google OAuth Refresh Tokens**  
  Use the provided script to generate refresh tokens for GA4 and GSC:
  ```bash
  python scripts/get_refresh_token.py
  ```
  Then paste the tokens into your environment variables (`GA4_REFRESH_TOKEN`, `GSC_REFRESH_TOKEN`).


MIT License

Copyright (c) 2025 Richard Naimy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.