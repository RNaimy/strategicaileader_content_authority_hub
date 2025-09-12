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
    sig = data["signals"]
    assert sig["entity_coverage_score"] == 0.0
    assert sig["citation_count"] == 0
    assert sig["external_link_count"] == 0
    assert sig["schema_presence"] == 0
    assert sig["author_bylines"] == 0


def test_signals_html_schema_bylines_links():
    # JSON with embedded JSON-LD must escape quotes
    html = (
        "<html><head>"
        '<meta name="author" content="Jane Doe">'
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Article","author":{"@type":"Person","name":"Jane Doe"}}'
        "</script>"
        "</head><body>"
        "<p>By Jane Doe. See sources: "
        '<a href="https://example.org/one">one</a> and '
        '<a href="https://another.example.com/two">two</a>.'
        "</p>"
        "</body></html>"
    )
    r = client.post("/authority/signals", json={"html": html})
    assert r.status_code == 200
    sig = r.json()["signals"]
    # Expect schema detected
    assert sig["schema_presence"] == 1
    # At least one byline detected (from meta/jsonld/By pattern)
    assert sig["author_bylines"] >= 1
    # Two absolute external links
    assert sig["external_link_count"] == 2


def test_score_batch_stub():
    payload = {"urls": ["https://strategicaileader.com", "https://liasflowers.com"]}
    r = client.post("/authority/score/batch", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "results" in body and len(body["results"]) == 2
    for row in body["results"]:
        assert "url" in row and "signals" in row
        sig = row["signals"]
        # The stub puts the URL text inside the HTML, so we expect 1 citation (url in text)
        assert sig["citation_count"] == 1
        assert sig["schema_presence"] == 0
