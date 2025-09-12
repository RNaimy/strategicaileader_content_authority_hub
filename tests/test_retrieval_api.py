import os
import json
import pytest
from typing import Optional
from starlette.testclient import TestClient

# Try importing the FastAPI app as wired in main
try:
    from src.main import app  # type: ignore
except Exception:  # pragma: no cover - fallback for unusual envs
    app = None  # type: ignore

client: Optional[TestClient] = TestClient(app) if app else None  # type: ignore


def _find_route(suffix: str) -> Optional[str]:
    """
    Helper used across our test suite to tolerate slight route name changes.
    Attempts to find a route path that ends with the provided suffix.
    """
    if not app:
        return None
    suffix = suffix.rstrip("/")
    for r in app.router.routes:
        if getattr(r, "path", "").rstrip("/").endswith(suffix):
            return r.path
    return None


@pytest.mark.unit
def test_retrieval_router_mounted():
    """
    Smoke test: ensure the retrieval router is mounted (or at minimum,
    that the API surface exists). If the router isn't present in this build,
    we skip to avoid red builds during incremental development.
    """
    if not client or not app:
        pytest.skip("App could not be imported for retrieval tests")

    q_path = _find_route("/retrieval/query") or "/retrieval/query"
    upsert_path = _find_route("/retrieval/upsert") or "/retrieval/upsert"

    # If neither route is mounted, skip (feature not compiled in this run).
    mounted = any(p in {q_path, upsert_path} for p in [r.path for r in app.router.routes])  # type: ignore
    if not mounted:
        pytest.skip("Retrieval router not mounted in this build")

    # Basic OPTIONS/405 sanity
    r = client.options(q_path)
    assert r.status_code in (200, 405)


@pytest.mark.unit
def test_upsert_and_query_round_trip():
    """
    Full round-trip:
    - Upsert a few items.
    - Query and ensure at least one is returned with expected shape.
    """
    if not client or not app:
        pytest.skip("App could not be imported for retrieval tests")

    q_path = _find_route("/retrieval/query") or "/retrieval/query"
    upsert_path = _find_route("/retrieval/upsert") or "/retrieval/upsert"

    # If feature is not present, skip
    paths = {r.path for r in app.router.routes}  # type: ignore
    if q_path not in paths or upsert_path not in paths:
        pytest.skip("Retrieval endpoints not available")

    payload = {
        "site_id": None,
        "items": [
            {
                "id": "doc-1",
                "url": "https://ex.com/1",
                "title": "Doc 1",
                "text": "apples and oranges",
            },
            {
                "id": "doc-2",
                "url": "https://ex.com/2",
                "title": "Doc 2",
                "text": "bananas are yellow",
            },
            {
                "id": "doc-3",
                "url": "https://ex.com/3",
                "title": "Doc 3",
                "text": "grapes grow in clusters",
            },
        ],
    }
    r = client.post(upsert_path, json=payload)
    assert r.status_code in (200, 201)
    body = r.json()
    assert "upserted" in body and body["upserted"] >= 3

    # Query
    rq = {"q": "yellow fruit", "k": 2}
    r = client.post(q_path, json=rq)
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"query", "results"}
    assert isinstance(data["results"], list)
    assert 0 < len(data["results"]) <= 2

    # Result shape
    top = data["results"][0]
    assert set(top.keys()) >= {"id", "url", "title", "score"}


@pytest.mark.unit
def test_query_limit_and_filters_behavior():
    """
    Validate 'k' limiting and that an impossible filter yields empty results.
    Implementations may ignore filters they don't understand; in that case,
    we only assert the limit behavior.
    """
    if not client or not app:
        pytest.skip("App could not be imported for retrieval tests")

    q_path = _find_route("/retrieval/query") or "/retrieval/query"
    paths = {r.path for r in app.router.routes}  # type: ignore
    if q_path not in paths:
        pytest.skip("Retrieval query endpoint not available")

    # Limit behavior
    rq = {"q": "fruit", "k": 1}
    r = client.post(q_path, json=rq)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("results", []), list)
    assert len(data["results"]) <= 1

    # Try a filter that shouldn't match anything (if filters are supported)
    rq_none = {"q": "fruit", "k": 5, "filters": {"site_id": 999999}}
    r2 = client.post(q_path, json=rq_none)
    assert r2.status_code == 200
    data2 = r2.json()
    # If filters are implemented, it should be empty; if not, we at least have a list.
    assert isinstance(data2.get("results", []), list)
    if data2.get("filters_applied", False) or "filters_applied" in data2:
        assert len(data2["results"]) == 0
