import uuid
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.db.models import Site, ContentItem, ContentLink


client = TestClient(app)


def _find_route(path_endswith: str):
    # Return the first route path that ends with the given suffix and contains 'graph'
    for r in app.routes:
        try:
            p = r.path  # FastAPI route object
        except AttributeError:
            continue
        if p.endswith(path_endswith) and "graph" in p:
            return p
    return None


@pytest.fixture()
def seed_site(db):
    domain = f"api-{uuid.uuid4().hex}.local"
    s = Site(name=f"API {domain}", domain=domain)
    db.add(s); db.commit()
    return s


def test_graph_export_endpoint_smoke(db, seed_site):
    a = ContentItem(site_id=seed_site.id, url=f"https://{seed_site.domain}/a", title="A")
    b = ContentItem(site_id=seed_site.id, url=f"https://{seed_site.domain}/b", title="B")
    db.add_all([a, b]); db.commit()
    db.add(ContentLink(from_content_id=a.id, to_url="/b", is_internal=True)); db.commit()

    path = _find_route("/export") or "/graph/export"
    r = client.get(path)
    assert r.status_code == 200
    payload = r.json()
    assert set(payload.keys()) >= {"nodes", "edges", "meta"}
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)


def test_graph_recompute_endpoint_smoke(db, seed_site):
    a = ContentItem(site_id=seed_site.id, url=f"https://{seed_site.domain}/c", title="C")
    b = ContentItem(site_id=seed_site.id, url=f"https://{seed_site.domain}/d", title="D")
    db.add_all([a, b]); db.commit()
    db.add(ContentLink(from_content_id=a.id, to_url="/d", is_internal=True)); db.commit()

    path = _find_route("/recompute") or "/graph/recompute"
    r = client.post(path)
    assert r.status_code == 200
    payload = r.json()
    assert set(payload.keys()) >= {"nodes", "edges", "meta"}


def test_graph_export_no_metrics_query_param(db, seed_site):
    a = ContentItem(site_id=seed_site.id, url=f"https://{seed_site.domain}/e", title="E")
    db.add(a); db.commit()

    path = _find_route("/export") or "/graph/export"
    r = client.get(path, params={"include_metrics": False})
    assert r.status_code == 200
    payload = r.json()
    if payload["nodes"]:
        assert "metrics" not in payload["nodes"][0]


def test_graph_export_shape_when_empty():
    path = _find_route("/export") or "/graph/export"
    r = client.get(path)
    assert r.status_code in (200, 204, 404)
    if r.status_code == 204:
        return
    payload = r.json()
    assert "nodes" in payload and isinstance(payload["nodes"], list)
    assert "edges" in payload and isinstance(payload["edges"], list)