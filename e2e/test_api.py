"""API endpoint tests for the unified server."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_dashboard_serves_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "Alpha SRE" in res.text


def test_analyze_bad_payload():
    res = client.post("/api/analyze", json={"bad": "data"})
    assert res.status_code == 400


def test_health():
    res = client.get("/health")
    assert res.json()["status"] == "ok"
