"""End-to-end: generate -> ingest -> analyse -> validate.

This is the test that proves the headline claim, so it runs the real corpus
rather than a fixture. It is slow by design; deselect with -m "not slow".
"""
from __future__ import annotations

import pytest

from app.config import RAW_DIR
from app.db import fetch_dicts
from app.ingest.loader import load_sample
from app.runner import run_analysis
from app.sampling.picker import generate_sample
from app.services import entity_detail, overview
from app.validation.run import validate
from generator.generate import generate

pytestmark = pytest.mark.slow

MIN_RECALL = 0.85
MIN_PRECISION = 0.80


@pytest.fixture(scope="module")
def pipeline():
    generate(seed=42, n_entities=12, days=90, out_dir=RAW_DIR)
    load_sample(RAW_DIR)
    first = run_analysis(notes="pytest first run")
    second = run_analysis(notes="pytest second run")
    return {"first": first, "second": second}


def _comparable(run_id: str) -> list[tuple]:
    rows = fetch_dicts(
        "SELECT entity_id, detector_id, detector_version, severity, confidence, title, "
        "rationale, metrics, evidence_row_ids FROM findings WHERE run_id = ? "
        "ORDER BY entity_id, detector_id, title",
        [run_id],
    )
    return [tuple(r.values()) for r in rows]


def test_reruns_on_the_same_data_are_identical(pipeline):
    """Charter rule 3: same input + same code version -> identical results."""
    a = _comparable(pipeline["first"]["run_id"])
    b = _comparable(pipeline["second"]["run_id"])
    assert a == b
    assert pipeline["first"]["data_hash"] == pipeline["second"]["data_hash"]


def test_no_detector_errored(pipeline):
    errors = [d for d in pipeline["second"]["per_detector"] if d["error"]]
    assert errors == [], errors


def test_validation_recall_and_precision(pipeline):
    result = validate(pipeline["second"]["run_id"])
    assert result["planted_total"] >= 25
    assert result["recall"] >= MIN_RECALL, result["per_detector"]
    assert result["precision"] >= MIN_PRECISION, result["per_detector"]


def test_innocent_lookalikes_are_not_flagged(pipeline):
    result = validate(pipeline["second"]["run_id"])
    bad = [la for la in result["innocent_lookalikes"] if not la["correctly_not_flagged"]]
    assert bad == [], bad


def test_healthy_entities_stay_low_risk(pipeline):
    result = validate(pipeline["second"]["run_id"])
    healthy = {h["entity_id"] for h in result["healthy_entities"]}
    rows = {r["entity_id"]: r for r in overview()["entities"]}
    for eid in healthy:
        assert rows[eid]["risk_band"] == "Low", (eid, rows[eid]["risk_score"])
        assert rows[eid]["finding_count"] == 0


def test_faulty_entities_rank_above_healthy_ones(pipeline):
    rows = overview()["entities"]
    scores = {r["entity_id"]: r["risk_score"] for r in rows}
    result = validate(pipeline["second"]["run_id"])
    healthy = [h["entity_id"] for h in result["healthy_entities"]]
    worst_healthy = max(scores[e] for e in healthy)
    assert scores["E002"] > worst_healthy
    assert scores["E004"] > worst_healthy
    assert rows[0]["risk_score"] >= rows[-1]["risk_score"]


def test_every_stored_finding_is_explainable(pipeline):
    rows = fetch_dicts(
        "SELECT * FROM findings WHERE run_id = ?", [pipeline["second"]["run_id"]]
    )
    assert rows
    for r in rows:
        assert r["rationale"].strip()
        assert r["innocent_explanation"].strip()
        assert r["metrics"] and r["metrics"] != "{}"
        assert 0 < r["confidence"] <= 1
        assert r["status"] == "open"


def test_entity_detail_and_review_sample(pipeline):
    detail = entity_detail("E004")
    assert detail is not None
    assert len(detail["radar"]) == 8
    assert detail["findings"]
    assert detail["timeline"]

    sample = generate_sample("E004", size=40, seed=42)
    assert sample["actual_size"] == 40
    buckets = {i["bucket"] for i in sample["items"]}
    assert buckets == {"highest_risk", "random"}
    n_risk = sum(1 for i in sample["items"] if i["bucket"] == "highest_risk")
    assert n_risk == 28  # 70% of 40
    assert all(i["pick_reason"] for i in sample["items"])

    again = generate_sample("E004", size=40, seed=42)
    assert [i["row_id"] for i in again["items"]] == [i["row_id"] for i in sample["items"]]


def test_pdf_report_renders(pipeline):
    from app.reports.pdf import build_entity_report

    pdf = build_entity_report("E004")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 10_000
