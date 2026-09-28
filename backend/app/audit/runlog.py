"""Run metadata and the supervisor audit trail."""
from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app import __version__
from app.config import RANDOM_SEED, ROOT, RULES_VERSION
from app.db import fetch_dicts, locked, table_counts


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "unversioned"
    except Exception:  # pragma: no cover - git may be absent in a container
        return "unversioned"


def new_run_id() -> str:
    return f"RUN-{utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


def start_run(
    run_id: str, data_hash: str, detector_versions: dict[str, str], notes: str = ""
) -> None:
    counts = table_counts()
    with locked() as conn:
        conn.execute(
            """
            INSERT INTO runs (run_id, started_at, code_version, rules_version, git_commit,
                              data_hash, random_seed, detector_versions, row_counts,
                              status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            [
                run_id,
                utcnow(),
                __version__,
                RULES_VERSION,
                git_commit(),
                data_hash,
                RANDOM_SEED,
                json.dumps(detector_versions, sort_keys=True),
                json.dumps(counts, sort_keys=True),
                notes,
            ],
        )


def finish_run(run_id: str, finding_count: int, entity_count: int, status: str = "complete") -> None:
    with locked() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = ?, finding_count = ?, entity_count = ?, "
            "status = ? WHERE run_id = ?",
            [utcnow(), finding_count, entity_count, status, run_id],
        )


def log_action(
    actor: str,
    action: str,
    object_type: str = "",
    object_id: str = "",
    detail: str = "",
) -> str:
    audit_id = str(uuid.uuid4())
    with locked() as conn:
        conn.execute(
            "INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?, ?)",
            [audit_id, utcnow(), actor, action, object_type, object_id, detail],
        )
    return audit_id


def latest_run() -> Optional[dict[str, Any]]:
    rows = fetch_dicts(
        "SELECT * FROM runs WHERE status = 'complete' ORDER BY started_at DESC LIMIT 1"
    )
    if not rows:
        rows = fetch_dicts("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1")
    return rows[0] if rows else None


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    return fetch_dicts(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", [limit]
    )


def list_actions(limit: int = 200) -> list[dict[str, Any]]:
    return fetch_dicts(
        "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?", [limit]
    )


def current_data_hash() -> str:
    """Hash of the canonical tables currently in the database.

    Used when an analysis is run over data that did not come from a single set of
    files (for example after an upload), so a run is always tied to its input.
    """
    import hashlib

    h = hashlib.sha256()
    with locked() as conn:
        for table in (
            "entities", "commitments", "assets", "alerts", "cases", "escalations",
            "submissions",
        ):
            row = conn.execute(
                f"SELECT COUNT(*), coalesce(sum(hash(t::VARCHAR)), 0) FROM {table} t"
            ).fetchone()
            h.update(f"{table}:{row[0]}:{row[1]}".encode())
    return h.hexdigest()
