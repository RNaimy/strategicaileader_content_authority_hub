SHELL := /bin/bash
PY ?= python
PORT ?= 8000
APP ?= src.main:app
DOMAIN ?= example.com
ENABLE_RETRIEVAL ?= 0

.PHONY: help dev dev-retrieval test test-api test-export graph-export recompute seed clean debug-routes retrieval-search retrieval-answer retrieval-reindex retrieval-index open-docs open-root open-routes

help:
	@echo "Common targets:"
	@echo "  dev            - run the API locally with uvicorn (PORT=$(PORT))"
	@echo "  test           - run full test suite"
	@echo "  test-api       - run API tests only"
	@echo "  test-export    - run graph export tests only"
	@echo "  graph-export   - export graph JSON to graph/export/graph.json"
	@echo "  recompute      - trigger recompute via POST /graph/recompute and pretty-print"
	@echo "  seed           - insert demo content (looks for src/scripts/seed_demo.py:run)"
	@echo "  clean          - remove caches and build artifacts"
	@echo "  dev-retrieval  - run API with retrieval enabled (ENABLE_RETRIEVAL=1)"
	@echo "  debug-routes   - list mounted routes from /_debug/routes"
	@echo "  retrieval-search  - query /retrieval/search (Q, DOMAIN, TOPK vars)"
	@echo "  retrieval-answer  - POST /retrieval/answer (Q, DOMAIN, TOPK, MAXTOKENS)"
	@echo "  retrieval-reindex - POST /retrieval/reindex (DOMAIN, REFRESH)"
	@echo "  open-docs       - open FastAPI Swagger UI (/docs) in your browser"
	@echo "  open-root       - open site root (/) in your browser"
	@echo "  open-routes     - open the route list in your browser (/_debug/routes)"

dev: kill-port
	ENABLE_RETRIEVAL=$(ENABLE_RETRIEVAL) $(PY) -m uvicorn $(APP) --reload --port $(PORT)

dev-retrieval: kill-port
	ENABLE_RETRIEVAL=1 $(PY) -m uvicorn $(APP) --reload --port $(PORT)

#
# Ensure nothing is listening on PORT before starting uvicorn
kill-port:
	@PIDS=$$(lsof -ti :$(PORT) || true); \
	if [ -n "$$PIDS" ]; then \
	  echo "Killing processes on port $(PORT): $$PIDS"; \
	  kill -9 $$PIDS || true; \
	else \
	  echo "No processes on port $(PORT)"; \
	fi

test:
	pytest -q tests

test-api:
	pytest -q tests/test_graph_api.py

test-export:
	pytest -q tests/test_graph_export.py

# Export the current graph to graph/export/graph.json without requiring jq
graph-export:
	mkdir -p graph/export
	curl -sS http://localhost:$(PORT)/graph/export -o graph/export/graph.json
	$(PY) -c "import json, pathlib, sys; p=pathlib.Path('graph/export/graph.json'); s=p.read_text();\
try:\
    print(json.dumps(json.loads(s), indent=2))\
except Exception as e:\
    print(f'Failed to pretty-print JSON: {e}'); print(s)"

# Call recompute endpoint and pretty-print response
recompute:
	curl -sS -X POST http://localhost:$(PORT)/graph/recompute -o /tmp/graph_recompute.json
	$(PY) -c "import json, pathlib; p=pathlib.Path('/tmp/graph_recompute.json'); print(json.dumps(json.loads(p.read_text()), indent=2))"

debug-routes:
	curl -sS http://localhost:$(PORT)/_debug/routes | $(PY) -m json.tool

open-docs:
	$(PY) -m webbrowser "http://127.0.0.1:$(PORT)/docs"

open-root:
	$(PY) -m webbrowser "http://127.0.0.1:$(PORT)/"

open-routes:
	$(PY) -m webbrowser "http://127.0.0.1:$(PORT)/_debug/routes"

# Seed demo content via a small helper script if present
seed:
	@echo "Seeding demo content for DOMAIN=$(DOMAIN) ..."
	PYTHONPATH=".:src" $(PY) scripts/seed_demo.py --domain $(DOMAIN) --flush

clean:
	rm -rf .pytest_cache **/__pycache__ build dist *.egg-info

# -------- Retrieval helpers (Phase 9) --------
Q ?= hello world
TOPK ?= 5
MAXTOKENS ?= 160
REFRESH ?= false

retrieval-search:
	@echo "GET /retrieval/search?q=$${Q} (DOMAIN=$(DOMAIN) TOPK=$(TOPK))"
	curl -sS "http://localhost:$(PORT)/retrieval/search?q=$${Q}&domain=$(DOMAIN)&top_k=$(TOPK)" | $(PY) -m json.tool

retrieval-answer:
	@echo "POST /retrieval/answer (Q=$(Q) DOMAIN=$(DOMAIN) TOPK=$(TOPK) MAXTOKENS=$(MAXTOKENS))"
	@DATA='{"q":"'$${Q}'","domain":"$(DOMAIN)","top_k":$(TOPK),"max_tokens":$(MAXTOKENS)}'; \
	  curl -sS -X POST http://localhost:$(PORT)/retrieval/answer \
	    -H 'Content-Type: application/json' \
	    -d "$${DATA}" | $(PY) -m json.tool

retrieval-reindex:
	@echo "POST /retrieval/reindex (DOMAIN=$(DOMAIN) REFRESH=$(REFRESH))"
	@DATA='{"domain":"$(DOMAIN)","refresh_embeddings":'$(REFRESH)'}'; \
	  curl -sS -X POST http://localhost:$(PORT)/retrieval/reindex \
	    -H 'Content-Type: application/json' \
	    -d "$${DATA}" | $(PY) -m json.tool

# Alias to reindex everything (same as retrieval-reindex for now)
retrieval-index: retrieval-reindex