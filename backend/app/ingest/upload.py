"""Two-step upload of a foreign-format submission: stage, then commit.

Step 1 (stage) stores the raw file, profiles it and proposes a column mapping.
Step 2 (commit) applies the confirmed mapping, pseudonymises, loads the rows,
records the file hash as a submission, and runs the Q01-Q05 integrity checks so
the supervisor gets a data-quality report card straight away.
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.audit.runlog import log_action
from app.config import UPLOAD_DIR
from app.db import fetch_dicts, fetch_one, locked
from app.detectors.registry import QUALITY_DETECTOR_IDS
from app.ingest.loader import TABLE_COLUMNS, file_sha256, normalise_frame
from app.ingest.mapping import (
    apply_mapping,
    load_mapping,
    new_upload_id,
    save_mapping,
    suggest_mapping,
)

STAGE_DIR = UPLOAD_DIR / "staged"
STAGE_DIR.mkdir(parents=True, exist_ok=True)

QUALITY_LABELS = {
    "Q01": "Record IDs complete",
    "Q02": "No missing days",
    "Q03": "Declared count matches rows",
    "Q04": "Timestamps look captured",
    "Q05": "File hash recorded",
}


def read_tabular(filename: str, content: bytes) -> pd.DataFrame:
    """Read CSV, TSV or JSON bytes into a DataFrame."""
    name = filename.lower()
    if name.endswith(".json"):
        payload = json.loads(content.decode("utf-8-sig"))
        if isinstance(payload, dict):
            for key in ("rows", "data", "records", "items"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
            else:
                payload = [payload]
        return pd.DataFrame(payload)
    sep = "\t" if name.endswith((".tsv", ".tab")) else ","
    return pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, keep_default_na=False)


def stage_upload(
    entity_id: str, table_type: str, filename: str, content: bytes
) -> dict[str, Any]:
    if table_type not in TABLE_COLUMNS and table_type != "cases":
        raise ValueError(f"Unsupported table type '{table_type}'")
    upload_id = new_upload_id()
    safe = "".join(c for c in Path(filename).name if c.isalnum() or c in "._-")
    path = STAGE_DIR / f"{upload_id}__{safe}"
    path.write_bytes(content)

    df = read_tabular(filename, content)
    suggestion = suggest_mapping(table_type, df)
    saved = load_mapping(entity_id, table_type)
    if saved:
        # A confirmed mapping for this organisation wins over the guess.
        for field, source in saved["mapping"].items():
            if source in df.columns:
                suggestion["mapping"][field] = source
        suggestion["value_map"] = saved["value_map"] or suggestion["value_map"]
        suggestion["reused_saved_mapping"] = True
        suggestion["missing_required"] = [
            f
            for f in suggestion["missing_required"]
            if not suggestion["mapping"].get(f)
        ]
    else:
        suggestion["reused_saved_mapping"] = False

    meta = {
        "upload_id": upload_id,
        "entity_id": entity_id,
        "table_type": table_type,
        "filename": filename,
        "stored_path": str(path),
        "file_sha256": file_sha256(path),
        "rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "uploaded_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }
    (STAGE_DIR / f"{upload_id}.meta.json").write_text(json.dumps(meta, indent=2))
    preview = df.head(20).fillna("").astype(str).to_dict(orient="records")
    log_action(
        "supervisor", "upload_staged", "upload", upload_id,
        f"{entity_id}/{table_type} {filename} rows={len(df)} sha256={meta['file_sha256'][:16]}",
    )
    return {**meta, "suggestion": suggestion, "preview": preview}


def load_staged(upload_id: str) -> dict[str, Any]:
    meta_path = STAGE_DIR / f"{upload_id}.meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Unknown upload {upload_id}")
    return json.loads(meta_path.read_text())


def commit_upload(
    upload_id: str,
    mapping: dict[str, Optional[str]],
    value_map: dict[str, Any] | None = None,
    remember_mapping: bool = True,
    actor: str = "supervisor",
) -> dict[str, Any]:
    meta = load_staged(upload_id)
    entity_id, table_type = meta["entity_id"], meta["table_type"]
    path = Path(meta["stored_path"])
    df = read_tabular(meta["filename"], path.read_bytes())

    canonical = apply_mapping(df, table_type, mapping, value_map, entity_id)
    frame = normalise_frame(table_type, canonical)
    before = fetch_one(
        f"SELECT COUNT(*) AS n FROM {table_type} WHERE entity_id = ?", [entity_id]
    )
    cols = ", ".join(TABLE_COLUMNS[table_type])
    with locked() as conn:
        conn.execute(f"DELETE FROM {table_type} WHERE entity_id = ?", [entity_id])
        conn.register("_up", frame)
        conn.execute(f"INSERT INTO {table_type} ({cols}) SELECT {cols} FROM _up")
        conn.unregister("_up")

    submission_id = _record_submission(entity_id, table_type, meta, frame)
    if remember_mapping:
        save_mapping(entity_id, table_type, mapping, value_map)
    log_action(
        actor, "upload_committed", "upload", upload_id,
        f"{entity_id}/{table_type}: replaced {before['n'] if before else 0} rows with "
        f"{len(frame)}; sha256={meta['file_sha256'][:16]}",
    )
    report = quality_report(entity_id)
    return {
        "upload_id": upload_id,
        "entity_id": entity_id,
        "table_type": table_type,
        "rows_loaded": len(frame),
        "rows_replaced": int(before["n"]) if before else 0,
        "submission_id": submission_id,
        "file_sha256": meta["file_sha256"],
        "quality_report": report,
    }


def _record_submission(
    entity_id: str, table_type: str, meta: dict[str, Any], frame: pd.DataFrame
) -> Optional[str]:
    """Register the uploaded file as a submission with its hash."""
    if table_type != "alerts":
        return None
    submission_id = f"{entity_id}-UP{uuid.uuid4().hex[:6].upper()}"
    start = pd.to_datetime(frame["created_at"], errors="coerce").min()
    end = pd.to_datetime(frame["created_at"], errors="coerce").max()
    if pd.isna(start) or pd.isna(end):
        return None
    with locked() as conn:
        conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                submission_id,
                entity_id,
                start.to_pydatetime(),
                (end + pd.Timedelta(seconds=1)).to_pydatetime(),
                int(len(frame)),
                meta["file_sha256"],
                datetime.now(timezone.utc).replace(tzinfo=None),
                "uploaded",
            ],
        )
    return submission_id


def quality_report(entity_id: str) -> dict[str, Any]:
    """Run Q01-Q05 for this entity and turn the result into a traffic-light card."""
    from app.runner import run_analysis

    result = run_analysis(
        only=QUALITY_DETECTOR_IDS,
        actor="system",
        notes=f"quality_check:{entity_id}",
        run_status="quality_only",
    )
    findings = fetch_dicts(
        "SELECT detector_id, severity, confidence, title, rationale, metrics "
        "FROM findings WHERE run_id = ? AND entity_id = ? ORDER BY detector_id",
        [result["run_id"], entity_id],
    )
    by_detector = {f["detector_id"]: f for f in findings}
    checks = []
    for det in QUALITY_DETECTOR_IDS:
        hit = by_detector.get(det)
        if not hit:
            status = "green"
        elif hit["severity"] == "high":
            status = "red"
        else:
            status = "amber"
        checks.append(
            {
                "check": det,
                "label": QUALITY_LABELS[det],
                "status": status,
                "title": hit["title"] if hit else "No issue detected",
                "rationale": hit["rationale"] if hit else "",
                "metrics": json.loads(hit["metrics"]) if hit else {},
            }
        )
    worst = "red" if any(c["status"] == "red" for c in checks) else (
        "amber" if any(c["status"] == "amber" for c in checks) else "green"
    )
    return {
        "entity_id": entity_id,
        "run_id": result["run_id"],
        "overall": worst,
        "checks": checks,
    }
