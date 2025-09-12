import os
import pytest
from starlette.testclient import TestClient

# These tests are "phase 6 scaffolding".
# They are written to pass even if the /intelligence router is not implemented yet.
# When the routes land, the assertions below will automatically start enforcing behavior.


@pytest.fixture(scope="module")
def client():
    # Ensure app imports without needing a running server
    from src.main import app

    return TestClient(app)


def _has_router(client: TestClient, prefix: str) -> bool:
    """Return True if the API root advertises the given router prefix."""
    try:
        resp = client.get("/")
    except Exception:
        return False
    if resp.status_code != 200:
        return False
    try:
        data = resp.json()
    except Exception:
        return False
    routers = data.get("routers") or []
    return prefix in routers


@pytest.mark.order(1)
def test_intelligence_router_registered(client: TestClient):
    """API root should eventually list '/intelligence' in routers.
    If not present yet, the test is skipped (scaffold behavior)."""
    if not _has_router(client, "/intelligence"):
        pytest.skip("Intelligence router not registered yet (Phase 6 scaffold)")
    # If present, ensure the health endpoint also exists
    r = client.get("/intelligence/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("module") in {"intelligence", "intel", "research"}


@pytest.mark.order(2)
def test_intelligence_health(client: TestClient):
    """Hit /intelligence/health. If route does not exist yet, mark xfail (non-strict)."""
    r = client.get("/intelligence/health")
    if r.status_code == 404:
        pytest.xfail("Intelligence health not implemented yet (Phase 6 scaffold)")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True


@pytest.mark.order(3)
def test_intelligence_brief_smoke(client: TestClient):
    """
    Smoke test for /intelligence/brief?domain=...
    Expectations (once implemented):
      - 200 OK
      - JSON with keys: domain, generated_at, summary (or 'brief'), and sources list (optional)
    Until implemented, xfail non-strict on 404.
    """
    domain = os.getenv("TEST_DOMAIN", "strategicaileader.com")
    r = client.get(f"/intelligence/brief?domain={domain}&max_items=50")
    if r.status_code == 404:
        pytest.xfail("Intelligence brief not implemented yet (Phase 6 scaffold)")
    assert r.status_code == 200
    payload = r.json()
    # Flexible schema: accept either 'summary' or 'brief' field name
    assert payload.get("domain") == domain
    assert any(
        k in payload for k in ("summary", "brief")
    ), "Expected summary/brief field"
    # If sources provided, it should be a list
    if "sources" in payload:
        assert isinstance(payload["sources"], list)
