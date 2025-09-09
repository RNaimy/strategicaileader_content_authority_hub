import os
import json
import time
import pytest
from fastapi.testclient import TestClient

# Import the app so we can call endpoints without running a server
from src.main import app

# DB helpers to ensure a Site exists for domain-based lookups
from src.db.session import SessionLocal
from src.db.models import Site

DOMAIN = "strategicaileader.com"

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

@pytest.fixture(scope="module")
def db():
    return SessionLocal()


def _has_table(db, table_name: str) -> bool:
    try:
        db.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
        return True
    except Exception:
        return False


def _ensure_site(db, domain: str) -> int:
    site = db.query(Site).filter(Site.domain == domain).first()
    if site:
        return site.id
    # create if not exists
    site = Site(name="Strategic AI Leader", domain=domain)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site.id


@pytest.mark.integration
def test_analytics_health(client):
    r = client.get("/analytics/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("module") == "analytics"


@pytest.mark.integration
@pytest.mark.order(1)
def test_ingest_and_fetch_snapshots(client, db):
    # Skip gracefully if the analytics table is not present (e.g., dev didn't run Alembic)
    if not _has_table(db, "analytics_snapshots"):
        pytest.skip("analytics_snapshots table not found; run Alembic migrations first")

    site_id = _ensure_site(db, DOMAIN)

    # Ingest stub GSC snapshot by domain
    r1 = client.post("/analytics/ingest/gsc", json={"domain": DOMAIN})
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["ok"] is True and j1["source"] == "gsc" and j1["site_id"] == site_id

    # Ingest stub GA4 snapshot by site_id and notes
    r2 = client.post("/analytics/ingest/ga4", json={"site_id": site_id, "notes": {"run": "pytest"}})
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["ok"] is True and j2["source"] == "ga4" and j2["site_id"] == site_id

    # Fetch latest per-source
    r3 = client.get(f"/analytics/latest?domain={DOMAIN}")
    assert r3.status_code == 200
    latest = r3.json().get("latest", {})
    assert "gsc" in latest and "ga4" in latest

    # Fetch rolling list
    r4 = client.get(f"/analytics/snapshots?domain={DOMAIN}&limit=5")
    assert r4.status_code == 200
    rows = r4.json()
    assert isinstance(rows, list) and len(rows) >= 2

    # Summary endpoint
    r5 = client.get(f"/analytics/summary?domain={DOMAIN}")
    assert r5.status_code == 200
    summary = r5.json()
    assert set(summary.get("sources_present", [])) >= {"gsc", "ga4"}


# ---
# Live-mode wiring tests (mocked): ensure analytics_api uses OAuth clients when tokens are present
# ---
import os
import types
from src.services.ga4_client import GA4Client
from src.services.gsc_client import GSCClient


@pytest.mark.unit
@pytest.mark.order(2)
def test_ingest_ga4_live_uses_client(monkeypatch, client, db):
    """When live=True and GA4_* env vars exist, the endpoint should instantiate
    GA4Client.from_oauth_refresh_token and use its fetch method. We mock the client
    to avoid real network calls."""
    # Ensure site exists
    site_id = _ensure_site(db, DOMAIN)

    # Provide fake env so code-path chooses OAuth client
    monkeypatch.setenv("GA4_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GA4_CLIENT_SECRET", "fake-secret")
    monkeypatch.setenv("GA4_REFRESH_TOKEN", "fake-refresh")

    # Stub client returned by GA4Client.from_oauth_refresh_token
    class StubGA4:
        def fetch_daily_metrics(self, property_id: str, days: int = 7):
            # minimal dict covering fields used in ingestion
            return {
                "organic_sessions": 111,
                "conversions": 9,
                "revenue": 12.34,
                "period_start": "2025-01-01T00:00:00Z",
                "period_end": "2025-01-07T00:00:00Z",
            }

    def _stub_from_token(client_id, client_secret, refresh_token):
        return StubGA4()

    # Monkeypatch the factory classmethod
    monkeypatch.setattr(GA4Client, "from_oauth_refresh_token", staticmethod(_stub_from_token))

    # Call live endpoint
    resp = client.post(
        "/analytics/ingest/ga4",
        json={"domain": DOMAIN, "live": True, "ga4_property_id": "354557242", "notes": {"via": "unit"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("source") == "ga4"
    assert body.get("site_id") == site_id


@pytest.mark.unit
@pytest.mark.order(3)
def test_ingest_gsc_live_uses_client(monkeypatch, client, db):
    """When live=True and GSC_* env vars exist, the endpoint should instantiate
    GSCClient.from_oauth_refresh_token and use its fetch method. We mock the client
    to avoid real network calls."""
    # Ensure site exists
    site_id = _ensure_site(db, DOMAIN)

    # Provide fake env so code-path chooses OAuth client
    monkeypatch.setenv("GSC_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GSC_CLIENT_SECRET", "fake-secret")
    monkeypatch.setenv("GSC_REFRESH_TOKEN", "fake-refresh")

    # Stub client returned by GSCClient.from_oauth_refresh_token
    class StubGSC:
        def fetch_site_summary(self, site_url: str, days: int = 7):
            # minimal dict covering fields used in ingestion
            return {
                "clicks": 222,
                "impressions": 3333,
                "ctr": 0.0666,
                "position": 10.5,
                "period_start": "2025-01-01T00:00:00Z",
                "period_end": "2025-01-07T00:00:00Z",
            }

    def _stub_from_token(client_id, client_secret, refresh_token):
        return StubGSC()

    # Monkeypatch the factory classmethod
    monkeypatch.setattr(GSCClient, "from_oauth_refresh_token", staticmethod(_stub_from_token))

    # Call live endpoint
    resp = client.post(
        "/analytics/ingest/gsc",
        json={"domain": DOMAIN, "live": True, "gsc_site_url": "https://www.strategicaileader.com/", "notes": {"via": "unit"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("source") == "gsc"
    assert body.get("site_id") == site_id