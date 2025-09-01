from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_health():
    r = client.get("/authority/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True

def test_signals_empty():
    r = client.post("/authority/signals", json={"text": ""})
    assert r.status_code == 200
    data = r.json()
    assert "signals" in data
