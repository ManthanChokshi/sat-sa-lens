"""Load canonical CSVs (from the generator or an approved export) into DuckDB.

Guarantees:
  * idempotent - re-running replaces the affected entities' rows instead of
    duplicating them;
  * pseudonymised - no raw analyst name, username or IP reaches the database;
  * auditable - every source file's SHA-256 is recorded.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import RAW_DIR
from app.db import locked
from app.ingest.pseudonymise import pseudo_series, redact_series
from app.schema import normalise_severity

TABLE_COLUMNS: dict[str, list[str]] = {
    "entities": ["entity_id", "name", "sector", "size_tier", "analyst_count"],
    "commitments": ["entity_id", "metric", "threshold", "unit"],
    "assets": [
        "asset_id", "entity_id", "hostname", "ip_pseudo", "asset_type",
        "criticality", "environment",
    ],
    "alerts": [
        "alert_id", "entity_id", "asset_id", "rule_name", "category", "severity",
        "source", "created_at",
    ],
    "cases": [
        "case_id", "entity_id", "alert_id", "analyst_pseudo", "opened_at",
        "closed_at", "disposition", "closure_type", "notes",
    ],
    "escalations": [
        "escalation_id", "case_id", "entity_id", "from_tier", "to_tier",
        "escalated_at", "reason",
    ],
    "submissions": [
        "submission_id", "entity_id", "period_start", "period_end",
        "declared_alert_count", "file_hash", "uploaded_at", "integrity_status",
    ],
}

LOAD_ORDER = [
    "entities",
    "commitments",
    "assets",
    "alerts",
    "cases",
    "escalations",
    "submissions",
]

TIMESTAMP_COLUMNS = {
    "created_at", "opened_at", "closed_at", "escalated_at", "period_start",
    "period_end", "uploaded_at",
}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_hash(paths: list[Path]) -> str:
    """One hash covering the whole input set, used as the run's data_hash."""
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: x.name):
        h.update(p.name.encode())
        h.update(file_sha256(p).encode())
    return h.hexdigest()


def normalise_frame(table: str, df: pd.DataFrame) -> pd.DataFrame:
    """Rename source columns onto canonical names, pseudonymise, coerce types."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    if table == "assets":
        if "ip_address" in df.columns and "ip_pseudo" not in df.columns:
            df["ip_pseudo"] = pseudo_series(df["ip_address"], "ip")
        elif "ip_pseudo" in df.columns:
            # Already-pseudonymous input is passed through unchanged.
            pass
        else:
            df["ip_pseudo"] = "ip-unknown"

    if table == "cases":
        if "analyst_name" in df.columns and "analyst_pseudo" not in df.columns:
            df["analyst_pseudo"] = pseudo_series(df["analyst_name"], "an")
        elif "analyst_pseudo" not in df.columns:
            df["analyst_pseudo"] = "an-unknown"
        if "notes" in df.columns:
            df["notes"] = redact_series(df["notes"].fillna(""))
        else:
            df["notes"] = ""

    if table == "alerts" and "severity" in df.columns:
        df["severity"] = df["severity"].map(normalise_severity)

    for col in TABLE_COLUMNS[table]:
        if col not in df.columns:
            df[col] = None

    for col in TIMESTAMP_COLUMNS & set(df.columns):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    if table == "entities":
        df["analyst_count"] = (
            pd.to_numeric(df["analyst_count"], errors="coerce").fillna(0).astype(int)
        )
    if table == "commitments":
        df["threshold"] = pd.to_numeric(df["threshold"], errors="coerce")
    if table == "submissions":
        df["declared_alert_count"] = (
            pd.to_numeric(df["declared_alert_count"], errors="coerce").fillna(0).astype(int)
        )

    out = df[TABLE_COLUMNS[table]]
    return out


def _replace_rows(table: str, df: pd.DataFrame, entity_ids: list[str]) -> int:
    """Delete the affected entities' rows then insert the new ones (idempotent)."""
    cols = ", ".join(TABLE_COLUMNS[table])
    with locked() as conn:
        if entity_ids:
            placeholders = ", ".join(["?"] * len(entity_ids))
            conn.execute(
                f"DELETE FROM {table} WHERE entity_id IN ({placeholders})", entity_ids
            )
        conn.register("_stage", df)
        conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _stage")
        conn.unregister("_stage")
    return len(df)


def load_canonical_frames(
    frames: dict[str, pd.DataFrame], source_hashes: dict[str, str] | None = None
) -> dict[str, int]:
    """Load a set of canonical frames, replacing each entity's existing rows."""
    counts: dict[str, int] = {}
    entity_ids: list[str] = []
    if "entities" in frames and not frames["entities"].empty:
        entity_ids = sorted(set(frames["entities"]["entity_id"].astype(str)))
    else:
        for name, df in frames.items():
            if "entity_id" in df.columns:
                entity_ids = sorted(set(df["entity_id"].astype(str)))
                break

    for table in LOAD_ORDER:
        if table not in frames:
            continue
        df = normalise_frame(table, frames[table])
        counts[table] = _replace_rows(table, df, entity_ids)

    if source_hashes:
        _record_integrity(entity_ids, source_hashes)
    _refresh_submission_integrity(entity_ids)
    return counts


def _record_integrity(entity_ids: list[str], source_hashes: dict[str, str]) -> None:
    detail = "; ".join(f"{k}={v[:16]}" for k, v in sorted(source_hashes.items()))
    with locked() as conn:
        conn.execute(
            "INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                str(uuid.uuid4()),
                datetime.now(timezone.utc).replace(tzinfo=None),
                "system",
                "ingest",
                "dataset",
                ",".join(entity_ids)[:200],
                f"source file hashes: {detail}",
            ],
        )


def _refresh_submission_integrity(entity_ids: list[str]) -> None:
    """Compare each submission's declared count with the rows actually present."""
    if not entity_ids:
        return
    placeholders = ", ".join(["?"] * len(entity_ids))
    with locked() as conn:
        conn.execute(
            f"""
            UPDATE submissions s
            SET integrity_status = CASE
                WHEN s.file_hash IS NULL OR s.file_hash = '' THEN 'no_hash'
                WHEN actual.n = 0 THEN 'no_rows'
                WHEN abs(s.declared_alert_count - actual.n)
                     <= greatest(5, 0.02 * s.declared_alert_count) THEN 'ok'
                ELSE 'count_mismatch'
            END
            FROM (
                SELECT sub.submission_id AS sid, COUNT(a.alert_id) AS n
                FROM submissions sub
                LEFT JOIN alerts a
                  ON a.entity_id = sub.entity_id
                 AND a.created_at >= sub.period_start
                 AND a.created_at <  sub.period_end
                WHERE sub.entity_id IN ({placeholders})
                GROUP BY sub.submission_id
            ) AS actual
            WHERE actual.sid = s.submission_id
            """,
            entity_ids,
        )


def load_sample(raw_dir: Path | str = RAW_DIR) -> dict[str, Any]:
    """Load the generator output in data/raw into DuckDB."""
    raw = Path(raw_dir)
    paths = [raw / f"{t}.csv" for t in LOAD_ORDER]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing generator output: "
            + ", ".join(missing)
            + ". Run: python -m generator.generate --seed 42"
        )
    frames = {t: pd.read_csv(raw / f"{t}.csv") for t in LOAD_ORDER}
    hashes = {p.name: file_sha256(p) for p in paths}
    counts = load_canonical_frames(frames, hashes)
    return {
        "counts": counts,
        "data_hash": dataset_hash(paths),
        "source_files": hashes,
        "raw_dir": str(raw),
    }


def main() -> None:
    result = load_sample()
    print("Loaded rows:")
    for table, n in result["counts"].items():
        print(f"  {table:14} {n:>9,}")
    print(f"\ndata_hash = {result['data_hash']}")


if __name__ == "__main__":
    main()
