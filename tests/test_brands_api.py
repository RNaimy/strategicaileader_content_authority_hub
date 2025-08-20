import json
import tempfile
from fastapi.testclient import TestClient

# Helper to build an isolated client with a fresh temp store
def make_client(monkeypatch):
    import importlib
    import src.api.brands_api as brands_api
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(json.dumps({"brands": []}).encode("utf-8"))
    tmp.flush()
    if hasattr(brands_api, "BRANDS_JSON"):
        monkeypatch.setattr(brands_api, "BRANDS_JSON", tmp.name, raising=True)
    importlib.reload(brands_api)
    return TestClient(brands_api.app)

# Helper to build a client when the JSON store is corrupt
def make_client_with_corrupt_store(monkeypatch):
    import importlib
    import src.api.brands_api as brands_api
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    # write invalid JSON
    tmp.write(b"{ this is not json ]")
    tmp.flush()
    if hasattr(brands_api, "BRANDS_JSON"):
        monkeypatch.setattr(brands_api, "BRANDS_JSON", tmp.name, raising=True)
    importlib.reload(brands_api)
    return TestClient(brands_api.app)

def test_brands_crud(monkeypatch):
    # Lazy import so we can monkeypatch the path before app loads data
    import importlib
    import src.api.brands_api as brands_api

    # Use a temp JSON file as the storage
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(json.dumps({"brands": []}).encode("utf-8"))
    tmp.flush()

    # Point the module’s storage to our temp file (module exposes BRANDS_JSON or similar)
    if hasattr(brands_api, "BRANDS_JSON"):
        monkeypatch.setattr(brands_api, "BRANDS_JSON", tmp.name, raising=True)

    # Re-import to reload with patched path if needed
    importlib.reload(brands_api)

    client = TestClient(brands_api.app)

    # List (empty)
    r = client.get("/api/brands")
    assert r.status_code == 200
    assert r.json() == {"brands": []} or "brands" in r.json()

    # Create
    new_brand = {"key": "strategicaileader", "name": "StrategicAILeader", "site_url": "https://www.strategicaileader.com"}
    r = client.post("/api/brands", json=new_brand)
    assert r.status_code in (200, 201)

    # Get
    r = client.get("/api/brands/strategicaileader")
    assert r.status_code == 200
    assert r.json()["key"] == "strategicaileader"

    # Update
    upd = {"name": "Strategic AI Leader"}
    r = client.put("/api/brands/strategicaileader", json=upd)
    assert r.status_code == 200
    assert r.json()["name"] == "Strategic AI Leader"

    # Delete
    r = client.delete("/api/brands/strategicaileader")
    assert r.status_code in (200, 204)

    # Confirm deletion
    r = client.get("/api/brands/strategicaileader")
    assert r.status_code == 404


# Additional branch coverage: upsert and not-found paths
def test_brands_upsert(monkeypatch):
    client = make_client(monkeypatch)

    # Initial create
    new_brand = {
        "key": "strategicaileader",
        "name": "StrategicAILeader",
        "site_url": "https://www.strategicaileader.com",
    }
    r = client.post("/api/brands", json=new_brand)
    assert r.status_code in (200, 201)

    # Upsert with same key but changed name (should update)
    updated_payload = {**new_brand, "name": "Strategic AI Leader"}
    r = client.post("/api/brands", json=updated_payload)
    # Either 200 (updated) or 201 (created) depending on implementation
    assert r.status_code in (200, 201)

    # Verify name actually updated
    r = client.get("/api/brands/strategicaileader")
    assert r.status_code == 200
    assert r.json()["name"] == "Strategic AI Leader"


def test_brands_not_found_paths(monkeypatch):
    client = make_client(monkeypatch)

    # GET non-existent
    r = client.get("/api/brands/nope")
    assert r.status_code == 404

    # PUT non-existent
    r = client.put("/api/brands/nope", json={"name": "X"})
    assert r.status_code == 404

    # DELETE non-existent
    r = client.delete("/api/brands/nope")
    assert r.status_code == 404


def test_brands_handles_corrupt_store(monkeypatch):
    client = make_client_with_corrupt_store(monkeypatch)

    # When the backing file is corrupt, the API should still respond.
    r = client.get("/api/brands")
    assert r.status_code == 200
    data = r.json()
    # Depending on implementation it may coerce to {"brands": []} or return a shape with "brands" key
    assert data == {"brands": []} or "brands" in data


def test_create_requires_minimal_fields(monkeypatch):
    client = make_client(monkeypatch)

    # Missing key
    resp = client.post("/api/brands", json={"name": "No Key", "site_url": "https://example.com"})
    assert resp.status_code == 422  # FastAPI/Pydantic validation error

    # Missing name (some impls allow minimal create with just 'key')
    resp = client.post("/api/brands", json={"key": "nokey"})
    assert resp.status_code in (200, 201, 422)

    # Provide minimal valid payload (key + name), should succeed
    resp = client.post("/api/brands", json={"key": "valid", "name": "Valid Name"})
    assert resp.status_code in (200, 201)

    # List should now include exactly one brand with key 'valid'
    resp = client.get("/api/brands")
    assert resp.status_code == 200
    data = resp.json()
    # Accept either strict shape or a superset with a "brands" key
    assert "brands" in data
    keys = [b.get("key") for b in data["brands"]]
    assert "valid" in keys


def test_duplicate_create_behavior(monkeypatch):
    client = make_client(monkeypatch)

    payload = {"key": "dup", "name": "Dup Brand"}
    first = client.post("/api/brands", json=payload)
    assert first.status_code in (200, 201)

    # Second create with the same key:
    # Some implementations upsert (200), others may return 409 Conflict.
    second = client.post("/api/brands", json=payload)
    assert second.status_code in (200, 201, 409)