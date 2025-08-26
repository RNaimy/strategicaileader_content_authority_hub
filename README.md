# StrategicAILeader Content Authority Hub

A FastAPI-based tool for crawling, embedding, clustering, and analyzing content for SEO and internal linking optimization.  

## Requirements
- Python 3.11+
- SQLite (bundled) or a Postgres URL for `DATABASE_URL`
- (Optional) OpenAI API key if using OpenAI embeddings

## Setup

### Install
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables
Set at least the following (examples shown for the hash test provider):
```bash
export DATABASE_URL=sqlite:///./data/app.db
export EMBEDDING_PROVIDER=hash128     # options: openai | hash128
export EMBEDDING_DIM=128              # 3072 for OpenAI, 128/256 for hash128
export APP_DEBUG=1                    # optional: verbose logs
# If using OpenAI:
# export OPENAI_API_KEY=sk-...
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

## Key Endpoints

### Service & Health
- `GET /` – service metadata
- `GET /health` – overall health + DB check
- `GET /clusters/health` – clustering subsystem check

### Clustering
- `GET /clusters/preview?domain=...&k=8&top_n=3&max_items=300`  
  Returns k-means preview (no DB writes).
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