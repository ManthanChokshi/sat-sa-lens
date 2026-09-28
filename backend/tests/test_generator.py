"""Generator determinism and ground-truth completeness."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from generator.entities import PROFILES, select_profiles
from generator.faults import INJECTORS
from generator.generate import TABLES, generate


def _hash_dir(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.glob("*.csv")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def test_same_seed_produces_identical_output(tmp_path: Path):
    out_a, out_b = tmp_path / "a" / "raw", tmp_path / "b" / "raw"
    generate(seed=7, n_entities=4, days=20, out_dir=out_a)
    generate(seed=7, n_entities=4, days=20, out_dir=out_b)
    assert _hash_dir(out_a) == _hash_dir(out_b)
    gt_a = json.loads((out_a.parent / "ground_truth.json").read_text())
    gt_b = json.loads((out_b.parent / "ground_truth.json").read_text())
    assert gt_a == gt_b


def test_different_seed_produces_different_output(tmp_path: Path):
    out_a, out_b = tmp_path / "a" / "raw", tmp_path / "b" / "raw"
    generate(seed=1, n_entities=4, days=20, out_dir=out_a)
    generate(seed=2, n_entities=4, days=20, out_dir=out_b)
    assert _hash_dir(out_a) != _hash_dir(out_b)


def test_every_planted_fault_appears_in_ground_truth(tmp_path: Path):
    out = tmp_path / "raw"
    result = generate(seed=42, n_entities=12, days=90, out_dir=out)
    problems = result["ground_truth"]["problems"]
    recorded = {(p["entity_id"], p["fault_code"]) for p in problems}
    expected = {
        (p.entity_id, code) for p in select_profiles(12) for code in p.faults
    }
    assert expected == recorded
    for p in problems:
        assert p["description"]
        assert p["expected_detector_id"]
        assert p["evidence_count"] >= 1
        assert isinstance(p["acceptable_detector_ids"], list)


def test_every_detector_id_has_an_injector():
    planted = {code for p in PROFILES for code in p.faults}
    assert planted <= set(INJECTORS)
    # Every detector D01-D14 and Q01-Q04 is exercised somewhere in the corpus.
    assert {f"D{i:02d}" for i in range(1, 15)} <= planted
    assert {f"Q{i:02d}" for i in range(1, 5)} <= planted


def test_all_tables_written_and_non_empty(tmp_path: Path):
    out = tmp_path / "raw"
    generate(seed=42, n_entities=4, days=30, out_dir=out)
    for table in TABLES:
        path = out / f"{table}.csv"
        assert path.exists(), table
        assert path.stat().st_size > 0, table


def test_healthy_and_lookalike_entities_are_declared(tmp_path: Path):
    out = tmp_path / "raw"
    result = generate(seed=42, n_entities=12, days=30, out_dir=out)
    gt = result["ground_truth"]
    assert len(gt["healthy_entities"]) >= 3
    assert len(gt["innocent_lookalikes"]) == 2
