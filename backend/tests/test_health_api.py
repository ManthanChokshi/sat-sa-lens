"""API contract tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["offline"] is True
    assert "row_counts" in body


def test_root(client: TestClient):
    assert client.get("/").json()["service"] == "SAT-SA Lens"


def test_detector_catalogue_is_complete(client: TestClient):
    cat = client.get("/api/detectors").json()
    ids = {d["detector_id"] for d in cat}
    expected = {f"D{i:02d}" for i in range(1, 15)} | {f"Q{i:02d}" for i in range(1, 6)}
    assert expected <= ids
    for d in cat:
        assert d["description"], f"{d['detector_id']} has no description"
        assert d["capability_area"]
        assert d["gap_type"]


def test_run_requires_data(client: TestClient, clean_db):
    r = client.post("/api/runs", json={})
    assert r.status_code == 400
    assert "No data loaded" in r.json()["detail"]


def test_unknown_entity_is_404(client: TestClient):
    assert client.get("/api/entities/NOPE").status_code == 404
