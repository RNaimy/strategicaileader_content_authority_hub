# Project Map

This file is auto-generated. Regenerate whenever files change.

## Routers

- `src/api/brands_api.py`  prefix: `/brands`
- `src/api/clustering_api.py`  prefix: `/clusters`
- `src/api/content_api.py`  prefix: `/content`
- `src/api/inventory_api.py`  prefix: `/inventory`
- `src/api/scraper_api.py`  prefix: `/scraper`

## Models

- `src/db/models.py`
- `src/utils/db.py`

## CRUD Modules
*(none yet; endpoints query via SQLAlchemy in routers)*

## API Modules (non-router helpers included)

- `src/api/__init__.py`
- `src/api/brands_api.py`
- `src/api/clustering_api.py`
- `src/api/content_api.py`
- `src/api/inventory_api.py`
- `src/api/npl/clustering.py`
- `src/api/scraper_api.py`
- `src/embeddings/provider.py`

## Alembic Migrations

- `alembic/env.py`
- `alembic/versions/90816bc247c2_init_schema.py`
- `alembic/versions/bdb2e742e062_initial_migration.py`
- `alembic/versions/53fe0cf91ebc_add_content_items_table.py`
- `alembic/versions/cd3e89114a5c_index_url_cluster_id_add_timestamps_to_.py`
- `alembic/versions/eac32663f359_add_meta_description_to_content_items.py`
- `alembic/versions/212dfe6733db_add_embedding_cluster_id_to_content_.py`

## Environment & Running

### Environment Variables
- `DATABASE_URL` — e.g. `sqlite:///./data/app.db`
- `APP_DEBUG` — set to `1` to enable `/content/debug/*` routes

### Start the API (dev)
```bash
export PYTHONPATH=.
export DATABASE_URL=sqlite:///./data/app.db
export APP_DEBUG=1
python -m uvicorn src.main:app --port 8001
```

## Smoke Tests (curl)

### Health
```bash
curl -s http://127.0.0.1:8001/health | jq
```

### Inventory
```bash
curl -s http://127.0.0.1:8001/inventory/health | jq
curl -s "http://127.0.0.1:8001/inventory/stats?domain=strategicaileader.com" | jq
curl -s "http://127.0.0.1:8001/inventory/list?domain=strategicaileader.com&limit=3" | jq
```

### Content
```bash
curl -s http://127.0.0.1:8001/content/health | jq
curl -s "http://127.0.0.1:8001/content/search?q=ai&domain=strategicaileader.com&limit=3" | jq
curl -s "http://127.0.0.1:8001/content/embedding-info" | jq
curl -s "http://127.0.0.1:8001/content/embedding-info?provider=openai&dim=3072" | jq
```

### Clusters
```bash
curl -s "http://127.0.0.1:8001/clusters/health" | jq
curl -s "http://127.0.0.1:8001/clusters/preview?domain=strategicaileader.com&k=8&top_n=3&max_items=300" | jq
curl -s -X POST "http://127.0.0.1:8001/clusters/commit" \
  -H "Content-Type: application/json" \
  -d '{"domain":"strategicaileader.com","k":8,"seed":42,"max_items":800}' | jq
curl -s "http://127.0.0.1:8001/clusters/internal-links?domain=strategicaileader.com&per_item=2&min_sim=0.55&max_items=500" | jq
```

## Database Reference

**Tables (key fields)**
- `sites` — `id`, `domain`, `created_at`, `updated_at`
- `content_items` — `id`, `site_id`, `url (unique per site)`, `title`, `status_code`, `word_count`, `schema_types (JSON)`, `lastmod`, `date_published`, `date_modified`, `freshness_score`, `freshness_source`, `first_seen`, `last_seen`, `content_hash`, `notes`, `created_at`, `updated_at`, `meta_description`, `embedding (JSON)`

## Alembic Workflow

Show current / head:
```bash
alembic history
alembic heads
alembic current
```

Create + apply migration:
```bash
alembic revision --autogenerate -m "your message"
alembic upgrade head
```

If the database has a stale/unknown revision:
```bash
alembic stamp head
alembic upgrade head
```

## Other Python Files

- `src/__init__.py`
- `src/analysis/authority_score.py`
- `src/analysis/keyword_gap.py`
- `src/analysis/optimization_ai.py`
- `src/analysis/topic_clustering.py`
- `src/app.py`
- `src/crawlers/blog_scraper.py`
- `src/crawlers/competitor_scraper.py`
- `src/crawlers/sitemap_parser.py`
- `src/dashboards/app.py`
- `src/dashboards/charts.py`
- `src/dashboards/components.py`
- `src/db/__init__.py`
- `src/db/init.py`
- `src/db/session.py`
- `src/db_init.py`
- `src/generation/brands.py`
- `src/generation/prompts.py`
- `src/gsc/gsc_client.py`
- `src/gsc/gsc_fetch.py`
- `src/gsc/gsc_parser.py`
- `src/main.py`
- `src/reports/build_csv.py`
- `src/reports/export_notion.py`
- `src/reports/generate_pdf.py`
- `src/utils/__init__.py`
- `src/utils/gsc_helpers.py`
- `src/utils/logger.py`
- `src/utils/nlp.py`
- `src/utils/seo_rules.py`
