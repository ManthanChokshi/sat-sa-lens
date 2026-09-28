"""DuckDB connection and canonical schema creation."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import duckdb

from app.config import DB_PATH

_LOCK = threading.RLock()
_CONN: Optional[duckdb.DuckDBPyConnection] = None

DDL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id       VARCHAR PRIMARY KEY,
    name            VARCHAR NOT NULL,
    sector          VARCHAR NOT NULL,
    size_tier       VARCHAR NOT NULL,
    analyst_count   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS commitments (
    entity_id   VARCHAR NOT NULL,
    metric      VARCHAR NOT NULL,
    threshold   DOUBLE  NOT NULL,
    unit        VARCHAR NOT NULL,
    PRIMARY KEY (entity_id, metric)
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id    VARCHAR PRIMARY KEY,
    entity_id   VARCHAR NOT NULL,
    hostname    VARCHAR NOT NULL,
    ip_pseudo   VARCHAR NOT NULL,
    asset_type  VARCHAR NOT NULL,
    criticality VARCHAR NOT NULL,
    environment VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id    VARCHAR PRIMARY KEY,
    entity_id   VARCHAR NOT NULL,
    asset_id    VARCHAR,
    rule_name   VARCHAR NOT NULL,
    category    VARCHAR NOT NULL,
    severity    VARCHAR NOT NULL,
    source      VARCHAR NOT NULL,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    case_id        VARCHAR PRIMARY KEY,
    entity_id      VARCHAR NOT NULL,
    alert_id       VARCHAR,
    analyst_pseudo VARCHAR NOT NULL,
    opened_at      TIMESTAMP NOT NULL,
    closed_at      TIMESTAMP,
    disposition    VARCHAR NOT NULL,
    closure_type   VARCHAR NOT NULL,
    notes          VARCHAR
);

CREATE TABLE IF NOT EXISTS escalations (
    escalation_id VARCHAR PRIMARY KEY,
    case_id       VARCHAR NOT NULL,
    entity_id     VARCHAR NOT NULL,
    from_tier     VARCHAR NOT NULL,
    to_tier       VARCHAR NOT NULL,
    escalated_at  TIMESTAMP NOT NULL,
    reason        VARCHAR
);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id        VARCHAR PRIMARY KEY,
    entity_id            VARCHAR NOT NULL,
    period_start         TIMESTAMP,
    period_end           TIMESTAMP,
    declared_alert_count INTEGER,
    file_hash            VARCHAR,
    uploaded_at          TIMESTAMP,
    integrity_status     VARCHAR
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id       VARCHAR PRIMARY KEY,
    run_id           VARCHAR NOT NULL,
    entity_id        VARCHAR NOT NULL,
    detector_id      VARCHAR NOT NULL,
    detector_version VARCHAR NOT NULL,
    gap_type         VARCHAR NOT NULL,
    capability_area  VARCHAR NOT NULL,
    severity         VARCHAR NOT NULL,
    confidence       DOUBLE  NOT NULL,
    title            VARCHAR NOT NULL,
    rationale        VARCHAR NOT NULL,
    innocent_explanation VARCHAR NOT NULL,
    metrics          VARCHAR NOT NULL,
    evidence_row_ids VARCHAR NOT NULL,
    evidence_table   VARCHAR,
    status           VARCHAR NOT NULL DEFAULT 'open',
    supervisor_note  VARCHAR DEFAULT '',
    created_at       TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            VARCHAR PRIMARY KEY,
    started_at        TIMESTAMP NOT NULL,
    finished_at       TIMESTAMP,
    code_version      VARCHAR,
    rules_version     VARCHAR,
    git_commit        VARCHAR,
    data_hash         VARCHAR,
    random_seed       INTEGER,
    detector_versions VARCHAR,
    finding_count     INTEGER DEFAULT 0,
    entity_count      INTEGER DEFAULT 0,
    row_counts        VARCHAR,
    status            VARCHAR DEFAULT 'running',
    notes             VARCHAR DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id   VARCHAR PRIMARY KEY,
    ts         TIMESTAMP NOT NULL,
    actor      VARCHAR NOT NULL,
    action     VARCHAR NOT NULL,
    object_type VARCHAR,
    object_id  VARCHAR,
    detail     VARCHAR
);

CREATE TABLE IF NOT EXISTS column_mappings (
    mapping_id VARCHAR PRIMARY KEY,
    entity_id  VARCHAR NOT NULL,
    table_type VARCHAR NOT NULL,
    mapping    VARCHAR NOT NULL,
    value_map  VARCHAR DEFAULT '{}',
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS review_samples (
    sample_id   VARCHAR NOT NULL,
    entity_id   VARCHAR NOT NULL,
    run_id      VARCHAR NOT NULL,
    row_id      VARCHAR NOT NULL,
    row_table   VARCHAR NOT NULL,
    pick_reason VARCHAR NOT NULL,
    pick_bucket VARCHAR NOT NULL,
    risk_weight DOUBLE,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_scores (
    run_id         VARCHAR NOT NULL,
    entity_id      VARCHAR NOT NULL,
    window_label   VARCHAR NOT NULL,
    risk_score     DOUBLE,
    risk_band      VARCHAR,
    capability_json VARCHAR,
    PRIMARY KEY (run_id, entity_id, window_label)
);
"""

CANONICAL_TABLES = [
    "entities",
    "commitments",
    "assets",
    "alerts",
    "cases",
    "escalations",
    "submissions",
]


def get_conn() -> duckdb.DuckDBPyConnection:
    """Return the process-wide DuckDB connection, creating the schema on first use."""
    global _CONN
    with _LOCK:
        if _CONN is None:
            Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
            _CONN = duckdb.connect(str(DB_PATH))
            _CONN.execute("SET TimeZone='UTC'")
            init_schema(_CONN)
        return _CONN


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    for stmt in filter(None, (s.strip() for s in DDL.split(";"))):
        conn.execute(stmt)


@contextmanager
def locked() -> Iterator[duckdb.DuckDBPyConnection]:
    """Serialise access — DuckDB connections are not thread-safe for writes."""
    with _LOCK:
        yield get_conn()


def reset_connection() -> None:
    """Close the cached connection (used by tests)."""
    global _CONN
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
            _CONN = None


def fetch_dicts(sql: str, params: Any = None) -> list[dict[str, Any]]:
    with locked() as conn:
        cur = conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(sql: str, params: Any = None) -> Optional[dict[str, Any]]:
    rows = fetch_dicts(sql, params)
    return rows[0] if rows else None


def table_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    with locked() as conn:
        for t in CANONICAL_TABLES + ["findings", "runs"]:
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return out
