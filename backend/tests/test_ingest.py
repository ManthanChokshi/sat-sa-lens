"""Ingest: row counts, pseudonymisation and idempotency."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.db import fetch_dicts, fetch_one
from app.ingest.loader import LOAD_ORDER, load_sample
from app.ingest.pseudonymise import contains_raw_identifier, pseudo, redact_text
from generator.generate import generate


def _load(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    generate(seed=42, n_entities=4, days=30, out_dir=raw)
    load_sample(raw)
    return raw


def test_row_counts_match_csvs(clean_db, tmp_path: Path):
    raw = _load(tmp_path)
    for table in LOAD_ORDER:
        expected = len(pd.read_csv(raw / f"{table}.csv"))
        actual = fetch_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        assert actual == expected, table


def test_ingest_is_idempotent(clean_db, tmp_path: Path):
    raw = _load(tmp_path)
    before = {t: fetch_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in LOAD_ORDER}
    load_sample(raw)
    load_sample(raw)
    after = {t: fetch_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in LOAD_ORDER}
    assert before == after


def test_no_raw_analyst_names_or_ips_in_database(clean_db, tmp_path: Path):
    raw = _load(tmp_path)
    source_names = set(pd.read_csv(raw / "cases.csv")["analyst_name"].dropna().unique())
    stored = {r["analyst_pseudo"] for r in fetch_dicts("SELECT DISTINCT analyst_pseudo FROM cases")}
    assert not (source_names & stored)
    assert all(s.startswith("an-") for s in stored)

    ips = fetch_dicts("SELECT DISTINCT ip_pseudo FROM assets LIMIT 200")
    for row in ips:
        assert not contains_raw_identifier(row["ip_pseudo"])
        assert row["ip_pseudo"].startswith("ip-")

    notes = fetch_dicts("SELECT notes FROM cases WHERE notes IS NOT NULL LIMIT 3000")
    offenders = [n["notes"] for n in notes if contains_raw_identifier(n["notes"])]
    assert offenders == [], offenders[:2]


def test_pseudonyms_are_stable_and_one_way():
    a = pseudo("Priya Sharma", "an")
    b = pseudo("priya sharma ", "an")
    assert a == b
    assert "priya" not in a.lower()


def test_redaction_keeps_artefact_shape():
    text = "Host NGT-SRV-00012 at 10.20.30.40 for user first.last blocked."
    out = redact_text(text)
    assert "10.20.30.40" not in out
    assert "first.last" not in out
    assert "NGT-SRV-00012" in out  # hostnames are not personal data
    assert "ip-" in out and "usr-" in out
    assert "blocked" in out


def test_declared_count_mismatch_is_marked_on_ingest(clean_db, tmp_path: Path):
    _load(tmp_path)
    statuses = {
        r["integrity_status"]
        for r in fetch_dicts("SELECT DISTINCT integrity_status FROM submissions")
    }
    assert statuses <= {"ok", "count_mismatch", "no_rows", "no_hash"}
