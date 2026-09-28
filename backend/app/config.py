"""Central configuration. Everything is local-only; no network hosts appear here."""
from __future__ import annotations

import os
from pathlib import Path

# repo root = .../sat-sa-lens
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("SATSA_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = Path(os.environ.get("SATSA_DB_PATH", DATA_DIR / "satsa.duckdb"))
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.json"
MODEL_DIR = Path(os.environ.get("SATSA_MODEL_DIR", ROOT / "models" / "all-MiniLM-L6-v2"))

# Pseudonymisation salt. Override in production via env var.
PSEUDO_SALT = os.environ.get("SATSA_PSEUDO_SALT", "satsa-dev-salt-2026")

# Determinism
RANDOM_SEED = int(os.environ.get("SATSA_SEED", "42"))

# Rule/code version stamped on every finding + run.
RULES_VERSION = "1.0.0"

# Small-sample protection: global floors.
MIN_SAMPLE_ALERTS = 30
MIN_SAMPLE_CASES = 20
MIN_PEERS = 3

for _d in (DATA_DIR, RAW_DIR, UPLOAD_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
