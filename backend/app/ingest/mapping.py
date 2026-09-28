"""Column mapping for foreign-format uploads.

A CSE rarely exports the canonical schema. This module profiles an uploaded file,
proposes a mapping onto canonical columns using both column-name similarity and
the shape of the values, and remembers the confirmed mapping per entity so the
next upload from the same organisation needs no human work.
"""
from __future__ import annotations

import difflib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from app.db import fetch_one, locked
from app.schema import SEVERITY_MAP, normalise_severity

TABLE_TYPES = ["alerts", "cases", "assets", "escalations", "entities", "commitments", "submissions"]

#: canonical field -> (required?, synonyms, value pattern)
FIELD_SPECS: dict[str, dict[str, dict[str, Any]]] = {
    "alerts": {
        "alert_id": {
            "required": True,
            "synonyms": ["alert id", "ticket no", "ticket number", "event id", "id",
                         "alertid", "incident id", "ref", "reference"],
            "pattern": r"^[A-Za-z0-9\-_/]{3,}$",
        },
        "asset_id": {
            "required": False,
            "synonyms": ["asset id", "device", "host id", "hostname", "device id",
                         "endpoint", "machine"],
            "pattern": r"^[A-Za-z0-9\-_.]{2,}$",
        },
        "rule_name": {
            "required": True,
            "synonyms": ["rule name", "detection rule", "signature", "rule", "alert name",
                         "title", "detection"],
            "pattern": r"^.{5,}$",
        },
        "category": {
            "required": False,
            "synonyms": ["category", "attack stage", "tactic", "mitre tactic", "class",
                         "alert type", "type"],
            "pattern": r"^[A-Za-z_ \-]{3,}$",
        },
        "severity": {
            "required": True,
            "synonyms": ["severity", "sev", "priority", "criticality", "risk", "level"],
            "pattern": r"^(p[1-5]|sev ?[1-5]|critical|high|medium|low|info\w*|[0-5])$",
        },
        "source": {
            "required": False,
            "synonyms": ["source", "feed", "sensor", "tool", "product", "detector"],
            "pattern": r"^[A-Za-z_ \-]{2,}$",
        },
        "created_at": {
            "required": True,
            "synonyms": ["created at", "opened", "timestamp", "event time", "detected at",
                         "first seen", "date", "time", "raised"],
            "pattern": "datetime",
        },
    },
    "cases": {
        "case_id": {
            "required": True,
            "synonyms": ["case id", "ref", "reference", "incident id", "case", "id",
                         "ticket ref"],
            "pattern": r"^[A-Za-z0-9\-_/]{3,}$",
        },
        "alert_id": {
            "required": False,
            "synonyms": ["alert id", "ticket no", "event id", "source alert", "alert"],
            "pattern": r"^[A-Za-z0-9\-_/]{3,}$",
        },
        "analyst_name": {
            "required": False,
            "synonyms": ["analyst", "assignee", "owner", "handled by", "assigned to",
                         "user", "operator", "analyst name"],
            "pattern": r"^[A-Za-z][A-Za-z .'\-]{2,}$",
        },
        "opened_at": {
            "required": True,
            "synonyms": ["opened", "opened at", "created", "start", "assigned at"],
            "pattern": "datetime",
        },
        "closed_at": {
            "required": False,
            "synonyms": ["closed", "resolved", "closed at", "end", "completed",
                         "resolution time"],
            "pattern": "datetime",
        },
        "disposition": {
            "required": False,
            "synonyms": ["disposition", "outcome", "verdict", "resolution", "result",
                         "conclusion"],
            "pattern": r"^[A-Za-z ]{3,}$",
        },
        "closure_type": {
            "required": False,
            "synonyms": ["closure type", "how closed", "close method", "closed by",
                         "automation"],
            "pattern": r"^(manual|automated|auto|automatic|human)$",
        },
        "notes": {
            "required": False,
            "synonyms": ["notes", "comments", "investigation notes", "remarks",
                         "description", "summary", "analysis"],
            "pattern": r"^.{10,}$",
        },
    },
    "assets": {
        "asset_id": {"required": True, "synonyms": ["asset id", "device id", "id", "ci id"],
                     "pattern": r"^[A-Za-z0-9\-_.]{2,}$"},
        "hostname": {"required": True, "synonyms": ["hostname", "host", "device", "name",
                                                    "computer name"],
                     "pattern": r"^[A-Za-z0-9\-_.]{2,}$"},
        "ip_address": {"required": False, "synonyms": ["ip", "ip address", "address",
                                                      "ipv4"],
                       "pattern": r"^(\d{1,3}\.){3}\d{1,3}$"},
        "asset_type": {"required": False, "synonyms": ["asset type", "type", "class",
                                                      "device type", "category"],
                       "pattern": r"^[A-Za-z ]{2,}$"},
        "criticality": {"required": False, "synonyms": ["criticality", "importance",
                                                       "business criticality", "tier"],
                        "pattern": r"^[A-Za-z0-9 ]{1,}$"},
        "environment": {"required": False, "synonyms": ["environment", "env", "zone",
                                                       "network"],
                        "pattern": r"^[A-Za-z ]{2,}$"},
    },
    "escalations": {
        "escalation_id": {"required": True, "synonyms": ["escalation id", "id", "ref"],
                          "pattern": r"^[A-Za-z0-9\-_/]{3,}$"},
        "case_id": {"required": True, "synonyms": ["case id", "ref", "incident id", "case"],
                    "pattern": r"^[A-Za-z0-9\-_/]{3,}$"},
        "from_tier": {"required": False, "synonyms": ["from tier", "from", "source tier",
                                                     "raised by"],
                      "pattern": r"^[A-Za-z0-9 _\-]{2,}$"},
        "to_tier": {"required": False, "synonyms": ["to tier", "to", "target tier",
                                                   "escalated to"],
                    "pattern": r"^[A-Za-z0-9 _\-]{2,}$"},
        "escalated_at": {"required": True, "synonyms": ["escalated at", "escalated",
                                                       "timestamp", "time"],
                         "pattern": "datetime"},
        "reason": {"required": False, "synonyms": ["reason", "justification", "comment",
                                                  "notes"],
                   "pattern": r"^.{5,}$"},
    },
    "entities": {
        "entity_id": {"required": True, "synonyms": ["entity id", "org id", "cse id", "id"],
                      "pattern": r"^[A-Za-z0-9\-_]{2,}$"},
        "name": {"required": True, "synonyms": ["name", "organisation", "organization",
                                               "entity name", "cse"],
                 "pattern": r"^.{3,}$"},
        "sector": {"required": True, "synonyms": ["sector", "industry", "vertical"],
                   "pattern": r"^[A-Za-z_ ]{3,}$"},
        "size_tier": {"required": True, "synonyms": ["size tier", "tier", "size"],
                      "pattern": r"^[A-Za-z ]{3,}$"},
        "analyst_count": {"required": False, "synonyms": ["analyst count", "analysts",
                                                         "headcount", "soc staff"],
                          "pattern": r"^\d+$"},
    },
    "commitments": {
        "metric": {"required": True, "synonyms": ["metric", "kpi", "measure",
                                                 "commitment"],
                   "pattern": r"^[A-Za-z_ ]{3,}$"},
        "threshold": {"required": True, "synonyms": ["threshold", "target", "value",
                                                    "sla", "limit"],
                      "pattern": r"^[\d.]+$"},
        "unit": {"required": False, "synonyms": ["unit", "units", "uom"],
                 "pattern": r"^[A-Za-z%]{1,}$"},
    },
    "submissions": {
        "submission_id": {"required": True, "synonyms": ["submission id", "id", "batch id"],
                          "pattern": r"^[A-Za-z0-9\-_/]{3,}$"},
        "period_start": {"required": True, "synonyms": ["period start", "from", "start"],
                         "pattern": "datetime"},
        "period_end": {"required": True, "synonyms": ["period end", "to", "end"],
                       "pattern": "datetime"},
        "declared_alert_count": {"required": False,
                                 "synonyms": ["declared alert count", "alert count",
                                              "total alerts", "declared"],
                                 "pattern": r"^\d+$"},
        "file_hash": {"required": False, "synonyms": ["file hash", "sha256", "hash",
                                                     "checksum"],
                      "pattern": r"^[0-9a-fA-F]{32,}$"},
        "uploaded_at": {"required": False, "synonyms": ["uploaded at", "submitted",
                                                       "received"],
                        "pattern": "datetime"},
    },
}

SEVERITY_FIELDS = {"severity", "criticality"}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(name).lower()).strip()


def _looks_like_datetime(values: list[str]) -> float:
    if not values:
        return 0.0
    ok = 0
    for v in values:
        try:
            parsed = pd.to_datetime(v, errors="raise")
            if pd.notna(parsed):
                ok += 1
        except Exception:
            continue
    return ok / len(values)


def _pattern_score(spec: dict[str, Any], values: list[str]) -> float:
    pattern = spec.get("pattern")
    if not pattern or not values:
        return 0.0
    if pattern == "datetime":
        return _looks_like_datetime(values)
    rx = re.compile(pattern, re.IGNORECASE)
    hits = sum(1 for v in values if rx.match(str(v).strip()))
    return hits / len(values)


def profile_file(df: pd.DataFrame, sample: int = 25) -> list[dict[str, Any]]:
    """Describe each column: name, sample values, null share, inferred kind."""
    out = []
    for col in df.columns:
        series = df[col]
        values = [str(v) for v in series.dropna().head(sample).tolist()]
        distinct = int(series.nunique(dropna=True))
        kind = "text"
        if _looks_like_datetime(values[:10]) > 0.8:
            kind = "datetime"
        elif all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in values[:10] or ["x"]):
            kind = "number"
        out.append(
            {
                "column": str(col),
                "samples": values[:8],
                "distinct_values": distinct,
                "null_share": round(float(series.isna().mean()), 4),
                "inferred_kind": kind,
                "is_low_cardinality": distinct <= 12,
                "distinct_list": (
                    sorted({str(v) for v in series.dropna().unique()})[:30]
                    if distinct <= 30
                    else []
                ),
            }
        )
    return out


def suggest_mapping(table_type: str, df: pd.DataFrame) -> dict[str, Any]:
    """Propose canonical_field -> source column, with a confidence per field."""
    specs = FIELD_SPECS.get(table_type)
    if not specs:
        raise ValueError(f"Unknown table type '{table_type}'")
    columns = [str(c) for c in df.columns]
    values_by_col = {
        c: [str(v) for v in df[c].dropna().head(40).tolist()] for c in columns
    }

    scores: dict[str, dict[str, float]] = {}
    for field, spec in specs.items():
        names = [_norm(field.replace("_", " "))] + [_norm(s) for s in spec["synonyms"]]
        scores[field] = {}
        for col in columns:
            cn = _norm(col)
            name_score = max(
                (difflib.SequenceMatcher(None, cn, n).ratio() for n in names), default=0.0
            )
            if any(cn == n for n in names):
                name_score = 1.0
            elif any(n in cn or cn in n for n in names if len(n) > 3):
                name_score = max(name_score, 0.85)
            pattern_score = _pattern_score(spec, values_by_col[col])
            scores[field][col] = 0.65 * name_score + 0.35 * pattern_score

    # Greedy assignment, best score first, one source column per canonical field.
    pairs = sorted(
        ((f, c, s) for f, cs in scores.items() for c, s in cs.items()),
        key=lambda t: -t[2],
    )
    mapping: dict[str, Optional[str]] = {f: None for f in specs}
    used: set[str] = set()
    for field, col, score in pairs:
        if mapping[field] is not None or col in used or score < 0.45:
            continue
        mapping[field] = col
        used.add(col)

    confidences = {
        f: round(scores[f].get(mapping[f], 0.0), 3) if mapping[f] else 0.0
        for f in specs
    }
    missing_required = [f for f, spec in specs.items() if spec["required"] and not mapping[f]]
    value_map = {}
    for field in specs:
        if field in SEVERITY_FIELDS and mapping.get(field):
            value_map[field] = suggest_value_map(df[mapping[field]])
    return {
        "table_type": table_type,
        "mapping": mapping,
        "confidence": confidences,
        "unmapped_columns": [c for c in columns if c not in used],
        "missing_required": missing_required,
        "value_map": value_map,
        "profile": profile_file(df),
    }


def suggest_value_map(series: pd.Series) -> dict[str, str]:
    """Map vendor severity labels (P1, Sev2, 4, ...) onto the canonical scale."""
    out: dict[str, str] = {}
    for raw in sorted({str(v) for v in series.dropna().unique()})[:50]:
        key = str(raw).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        out[raw] = SEVERITY_MAP.get(key, normalise_severity(raw))
    return out


def apply_mapping(
    df: pd.DataFrame,
    table_type: str,
    mapping: dict[str, Optional[str]],
    value_map: dict[str, dict[str, str]] | None = None,
    entity_id: Optional[str] = None,
) -> pd.DataFrame:
    """Rename and coerce an uploaded frame into canonical column names."""
    out = pd.DataFrame(index=df.index)
    for field, source in mapping.items():
        if source and source in df.columns:
            out[field] = df[source]
        else:
            out[field] = None
    if entity_id:
        out["entity_id"] = entity_id
    for field, vmap in (value_map or {}).items():
        if field in out.columns and vmap:
            out[field] = out[field].map(lambda v: vmap.get(str(v), normalise_severity(v)))
    if table_type == "cases":
        for col in ("disposition", "closure_type"):
            if col in out.columns:
                out[col] = out[col].map(_normalise_enum(col))
    return out


_DISPOSITION_ALIASES = {
    "true positive": "true_positive", "tp": "true_positive", "confirmed": "true_positive",
    "malicious": "true_positive",
    "false positive": "false_positive", "fp": "false_positive", "not an issue": "false_positive",
    "benign": "benign", "benign true positive": "benign", "expected": "benign",
    "duplicate": "duplicate", "dupe": "duplicate",
    "unresolved": "unresolved", "open": "unresolved", "in progress": "unresolved",
}
_CLOSURE_ALIASES = {
    "manual": "manual", "human": "manual", "analyst": "manual",
    "automated": "automated", "auto": "automated", "automatic": "automated",
    "automation": "automated", "playbook": "automated",
}


def _normalise_enum(col: str):
    table = _DISPOSITION_ALIASES if col == "disposition" else _CLOSURE_ALIASES
    default = "unresolved" if col == "disposition" else "manual"

    def _one(value: object) -> str:
        if value is None:
            return default
        key = str(value).strip().lower().replace("_", " ")
        return table.get(key, default)

    return _one


# ------------------------------------------------------------------ persistence
def save_mapping(
    entity_id: str,
    table_type: str,
    mapping: dict[str, Optional[str]],
    value_map: dict[str, Any] | None = None,
) -> str:
    mapping_id = f"MAP-{entity_id}-{table_type}"
    with locked() as conn:
        conn.execute("DELETE FROM column_mappings WHERE mapping_id = ?", [mapping_id])
        conn.execute(
            "INSERT INTO column_mappings VALUES (?, ?, ?, ?, ?, ?)",
            [
                mapping_id,
                entity_id,
                table_type,
                json.dumps(mapping, sort_keys=True),
                json.dumps(value_map or {}, sort_keys=True),
                datetime.now(timezone.utc).replace(tzinfo=None),
            ],
        )
    return mapping_id


def load_mapping(entity_id: str, table_type: str) -> Optional[dict[str, Any]]:
    row = fetch_one(
        "SELECT * FROM column_mappings WHERE entity_id = ? AND table_type = ?",
        [entity_id, table_type],
    )
    if not row:
        return None
    return {
        "mapping_id": row["mapping_id"],
        "entity_id": row["entity_id"],
        "table_type": row["table_type"],
        "mapping": json.loads(row["mapping"]),
        "value_map": json.loads(row["value_map"] or "{}"),
        "created_at": row["created_at"],
    }


def new_upload_id() -> str:
    return f"UP-{uuid.uuid4().hex[:10]}"
