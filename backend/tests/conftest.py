"""Test configuration.

Every test runs against a throw-away DuckDB file so the developer's real
data/satsa.duckdb is never touched. The environment must be set before any
app module is imported, which is why it happens at the top of conftest.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="satsa-tests-"))
os.environ["SATSA_DB_PATH"] = str(_TMP / "test.duckdb")
os.environ["SATSA_DATA_DIR"] = str(_TMP / "data")
os.environ["SATSA_PSEUDO_SALT"] = "unit-test-salt"

import pytest  # noqa: E402

from app.db import init_schema, locked, reset_connection  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def clean_db():
    """A database with the schema created and every table empty."""
    with locked() as conn:
        init_schema(conn)
        for table in (
            "findings", "runs", "audit_log", "entity_scores", "review_samples",
            "column_mappings", "submissions", "escalations", "cases", "alerts",
            "assets", "commitments", "entities",
        ):
            conn.execute(f"DELETE FROM {table}")
    yield
    reset_connection()
