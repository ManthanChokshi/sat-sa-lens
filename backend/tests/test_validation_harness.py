"""The validation harness itself must score correctly."""
from __future__ import annotations

import json

from app.validation.run import validate


def test_validation_reports_missing_run(tmp_path, clean_db):
    gt = tmp_path / "gt.json"
    gt.write_text(json.dumps({"problems": [], "innocent_lookalikes": []}))
    result = validate(path=str(gt))
    assert "error" in result


def test_acceptable_detectors_are_not_counted_as_false_positives(tmp_path, clean_db):
    """A D04 plant legitimately trips D05 too; that is not a false positive."""
    from datetime import datetime

    from app.db import locked

    gt = {
        "seed": 1,
        "healthy_entities": ["H1"],
        "innocent_lookalikes": [{"entity_id": "L1", "name": "Look-alike", "why": "small"}],
        "problems": [
            {
                "problem_id": "X-D04",
                "entity_id": "X",
                "expected_detector_id": "D04",
                "fault_code": "D04",
                "description": "template notes",
                "evidence_ids": [],
                "evidence_count": 1,
                "acceptable_detector_ids": ["D05"],
            },
            {
                "problem_id": "X-D10",
                "entity_id": "X",
                "expected_detector_id": "D10",
                "fault_code": "D10",
                "description": "silent assets",
                "evidence_ids": [],
                "evidence_count": 1,
                "acceptable_detector_ids": [],
            },
        ],
    }
    path = tmp_path / "gt.json"
    path.write_text(json.dumps(gt))

    with locked() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, started_at, status) VALUES ('R1', ?, 'complete')",
            [datetime(2026, 5, 1)],
        )
        for i, (entity, detector) in enumerate(
            [("X", "D04"), ("X", "D05"), ("X", "D14"), ("Y", "D01")]
        ):
            conn.execute(
                "INSERT INTO findings VALUES (?, 'R1', ?, ?, '1', 'execution_gap', "
                "'investigation', 'high', 0.9, 't', 'r', 'i', '{}', '[]', 'cases', "
                "'open', '', ?)",
                [f"F{i}", entity, detector, datetime(2026, 5, 1)],
            )

    result = validate("R1", path=str(path))
    per = {r["detector_id"]: r for r in result["per_detector"]}
    assert per["D04"]["caught"] == 1
    assert per["D05"]["false_positives"] == 0        # declared knock-on effect
    assert per["D14"]["false_positives"] == 0        # X has 2 planted problems
    assert per["D01"]["false_positives"] == 1        # Y has nothing planted
    assert per["D10"]["missed"] == 1
    assert result["recall"] == 0.5
    assert result["planted_total"] == 2
