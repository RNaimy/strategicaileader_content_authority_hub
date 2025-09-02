SHELL := /bin/bash
PY ?= python
PORT ?= 8000
APP ?= src.main:app

.PHONY: help dev test test-api test-export graph-export recompute seed clean

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

dev:
	$(PY) -m uvicorn $(APP) --reload --port $(PORT)

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
	$(PY) - <<'PY'
import json, pathlib, sys
p = pathlib.Path('graph/export/graph.json')
try:
    data = json.loads(p.read_text())
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Failed to pretty-print JSON: {e}")
    print(p.read_text())
PY

# Call recompute endpoint and pretty-print response
recompute:
	curl -sS -X POST http://localhost:$(PORT)/graph/recompute -o /tmp/graph_recompute.json
	$(PY) - <<'PY'
import json, pathlib
p = pathlib.Path('/tmp/graph_recompute.json')
print(json.dumps(json.loads(p.read_text()), indent=2))
PY

# Seed demo content via a small helper script if present
seed:
	@echo "Seeding demo content (if seeder exists)..."
	$(PY) - <<'PY'
try:
    from src.scripts.seed_demo import run as seed_run
    seed_run()
    print("Seed complete.")
except ModuleNotFoundError:
    print("No seeder found at src/scripts/seed_demo.py. Create a run() function to enable this target.")
    raise SystemExit(0)
except Exception as e:
    print(f"Seeding failed: {e}")
    raise SystemExit(1)
PY

clean:
	rm -rf .pytest_cache **/__pycache__ build dist *.egg-info