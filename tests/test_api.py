"""Unit and integration tests for FastAPI backend."""
from __future__ import annotations

from fastapi.testclient import TestClient
from wsis.api import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "default_market" in data
    assert "default_model" in data


def test_markets_endpoint():
    resp = client.get("/api/markets")
    assert resp.status_code == 200
    markets = resp.json()
    assert len(markets) >= 5
    codes = [m["code"] for m in markets]
    assert "in" in codes
    assert "us" in codes


def test_research_validation():
    # Empty query should fail with 400 or 422
    resp = client.post("/api/research", json={"query": "   "})
    assert resp.status_code in (400, 422)

    # Invalid market should fail with 400
    resp = client.post("/api/research", json={"query": "sunglasses", "market": "invalid_market"})
    assert resp.status_code == 400


def test_job_not_found():
    resp = client.get("/api/research/nonexistent-job-uuid-123")
    assert resp.status_code == 404
