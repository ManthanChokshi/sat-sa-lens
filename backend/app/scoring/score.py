"""Capability scorecard, entity risk score and 30-day trend.

Design rules:
  * only findings a supervisor has not rejected count (status open or valid);
  * every number is traceable to the findings that produced it;
  * scores are monotone - adding a finding, or raising its severity or
    confidence, can only make the risk score worse.
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable

from app.db import fetch_dicts, locked
from app.schema import CAPABILITY_AREAS

SEVERITY_WEIGHT = {"high": 30.0, "medium": 18.0, "low": 9.0}
#: Larger K = a gentler curve. Chosen so that one high-severity, high-confidence
#: finding lands in "medium" and three land in "high".
RISK_K = 62.0
BAND_HIGH = 60.0
BAND_MEDIUM = 30.0
COUNTED_STATUSES = ("open", "valid")
WINDOW_DAYS = 30


def finding_weight(severity: str, confidence: float) -> float:
    return SEVERITY_WEIGHT.get(severity, 9.0) * max(0.0, min(1.0, float(confidence)))


def normalise_risk(total_weight: float) -> float:
    """Map an unbounded penalty sum onto 0-100, monotonically."""
    return round(100.0 * (1.0 - math.exp(-max(0.0, total_weight) / RISK_K)), 1)


def band_for(score: float) -> str:
    if score >= BAND_HIGH:
        return "High"
    if score >= BAND_MEDIUM:
        return "Medium"
    return "Low"


def _load_findings(run_id: str) -> list[dict]:
    rows = fetch_dicts(
        """
        SELECT finding_id, entity_id, detector_id, gap_type, capability_area, severity,
               confidence, title, status, metrics, evidence_table, evidence_row_ids
        FROM findings WHERE run_id = ? ORDER BY entity_id, detector_id, finding_id
        """,
        [run_id],
    )
    return [r for r in rows if r["status"] in COUNTED_STATUSES]


def capability_scores(findings: Iterable[dict]) -> dict[str, float]:
    """0-100 per capability area; 100 means nothing was flagged there."""
    penalty = {area: 0.0 for area in CAPABILITY_AREAS}
    for f in findings:
        area = f["capability_area"]
        if area in penalty:
            penalty[area] += finding_weight(f["severity"], f["confidence"])
    return {
        area: round(max(0.0, 100.0 * math.exp(-p / 34.0)), 1)
        for area, p in penalty.items()
    }


def capability_explanations(findings: Iterable[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {area: [] for area in CAPABILITY_AREAS}
    for f in findings:
        area = f["capability_area"]
        if area in out:
            out[area].append(
                {
                    "finding_id": f["finding_id"],
                    "detector_id": f["detector_id"],
                    "title": f["title"],
                    "severity": f["severity"],
                    "confidence": round(float(f["confidence"]), 2),
                    "points_deducted": round(finding_weight(f["severity"], f["confidence"]), 1),
                }
            )
    for area in out:
        out[area].sort(key=lambda d: -d["points_deducted"])
    return out


def entity_risk(findings: list[dict]) -> dict[str, Any]:
    total = sum(finding_weight(f["severity"], f["confidence"]) for f in findings)
    score = normalise_risk(total)
    contributors = sorted(
        (
            {
                "finding_id": f["finding_id"],
                "detector_id": f["detector_id"],
                "title": f["title"],
                "severity": f["severity"],
                "confidence": round(float(f["confidence"]), 2),
                "gap_type": f["gap_type"],
                "capability_area": f["capability_area"],
                "weight": round(finding_weight(f["severity"], f["confidence"]), 1),
            }
            for f in findings
        ),
        key=lambda d: -d["weight"],
    )
    counts_by_gap: dict[str, int] = {}
    counts_by_severity: dict[str, int] = {}
    for f in findings:
        counts_by_gap[f["gap_type"]] = counts_by_gap.get(f["gap_type"], 0) + 1
        counts_by_severity[f["severity"]] = counts_by_severity.get(f["severity"], 0) + 1
    return {
        "risk_score": score,
        "risk_band": band_for(score),
        "total_weight": round(total, 1),
        "finding_count": len(findings),
        "counts_by_gap_type": counts_by_gap,
        "counts_by_severity": counts_by_severity,
        "top_contributors": contributors[:3],
        "all_contributors": contributors,
    }


# ------------------------------------------------------------------------ trend
def _evidence_timestamps(run_id: str) -> dict[str, list]:
    """For each finding, the timestamps of its evidence rows (cases or alerts)."""
    out: dict[str, list] = {}
    for table, id_col, ts_col in (
        ("cases", "case_id", "opened_at"),
        ("alerts", "alert_id", "created_at"),
    ):
        rows = fetch_dicts(
            f"""
            WITH f AS (
                SELECT finding_id, unnest(from_json(evidence_row_ids, '["VARCHAR"]')) AS rid
                FROM findings WHERE run_id = ? AND evidence_table = '{table}'
                  AND status IN ('open', 'valid')
            )
            SELECT f.finding_id, t.{ts_col} AS ts
            FROM f JOIN {table} t ON t.{id_col} = f.rid
            """,
            [run_id],
        )
        for r in rows:
            out.setdefault(r["finding_id"], []).append(r["ts"])
    return out


def trend_by_window(run_id: str, findings: list[dict]) -> dict[str, list[dict]]:
    """Allocate each finding's weight across 30-day windows using its evidence.

    A finding whose evidence all sits in the last month pushes only the last
    window's score up, which is what makes the trend arrow meaningful.
    """
    bounds = fetch_dicts("SELECT min(created_at) AS lo, max(created_at) AS hi FROM alerts")
    if not bounds or bounds[0]["lo"] is None:
        return {}
    lo, hi = bounds[0]["lo"], bounds[0]["hi"]
    total_days = max(1, (hi - lo).days + 1)
    n_windows = max(1, math.ceil(total_days / WINDOW_DAYS))
    labels = []
    for i in range(n_windows):
        start = lo + _days(i * WINDOW_DAYS)
        end = min(hi, start + _days(WINDOW_DAYS))
        labels.append((f"W{i + 1}", start, end))

    ts_map = _evidence_timestamps(run_id)
    per_entity: dict[str, dict[str, float]] = {}
    for f in findings:
        w = finding_weight(f["severity"], f["confidence"])
        stamps = ts_map.get(f["finding_id"], [])
        buckets = {lab: 0 for lab, _, _ in labels}
        for ts in stamps:
            for lab, start, end in labels:
                if start <= ts <= end:
                    buckets[lab] += 1
                    break
        total = sum(buckets.values())
        ent = per_entity.setdefault(f["entity_id"], {lab: 0.0 for lab, _, _ in labels})
        if total == 0:
            # No datable evidence (e.g. an asset or category level finding):
            # spread it evenly so it still counts.
            for lab in ent:
                ent[lab] += w / len(ent)
        else:
            for lab, count in buckets.items():
                ent[lab] += w * count / total

    out: dict[str, list[dict]] = {}
    for entity_id, buckets in per_entity.items():
        series = []
        for lab, start, end in labels:
            score = normalise_risk(buckets[lab])
            series.append(
                {
                    "window": lab,
                    "period_start": str(start)[:10],
                    "period_end": str(end)[:10],
                    "risk_score": score,
                    "risk_band": band_for(score),
                }
            )
        out[entity_id] = series
    return out


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


def trend_direction(series: list[dict]) -> str:
    if len(series) < 2:
        return "flat"
    delta = series[-1]["risk_score"] - series[-2]["risk_score"]
    if delta > 3:
        return "worsening"
    if delta < -3:
        return "improving"
    return "flat"


# -------------------------------------------------------------------- persistence
def compute_and_store(run_id: str) -> dict[str, dict[str, Any]]:
    """Recompute every entity's scores for a run and persist them."""
    findings = _load_findings(run_id)
    by_entity: dict[str, list[dict]] = {}
    for f in findings:
        by_entity.setdefault(f["entity_id"], []).append(f)

    entities = fetch_dicts("SELECT entity_id FROM entities ORDER BY entity_id")
    trends = trend_by_window(run_id, findings)

    result: dict[str, dict[str, Any]] = {}
    rows: list[list[Any]] = []
    for e in entities:
        eid = e["entity_id"]
        mine = by_entity.get(eid, [])
        risk = entity_risk(mine)
        caps = capability_scores(mine)
        series = trends.get(eid, [])
        payload = {
            **risk,
            "capability_scores": caps,
            "capability_explanations": capability_explanations(mine),
            "trend": series,
            "trend_direction": trend_direction(series),
        }
        result[eid] = payload
        rows.append(
            [run_id, eid, "overall", risk["risk_score"], risk["risk_band"], json.dumps(caps)]
        )
        for point in series:
            rows.append(
                [
                    run_id,
                    eid,
                    point["window"],
                    point["risk_score"],
                    point["risk_band"],
                    json.dumps({}),
                ]
            )

    with locked() as conn:
        conn.execute("DELETE FROM entity_scores WHERE run_id = ?", [run_id])
        conn.executemany(
            "INSERT INTO entity_scores VALUES (?, ?, ?, ?, ?, ?)", rows
        )
    return result
