"""Read models: everything the API and the PDF report need, in one place."""
from __future__ import annotations

import json
from typing import Any, Optional

from app.audit.runlog import latest_run
from app.db import fetch_dicts, fetch_one
from app.detectors.registry import catalogue
from app.scoring.peers import build_peer_index, peer_groups
from app.scoring.score import compute_and_store
from app.schema import CAPABILITY_AREAS

_SCORE_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TOKEN: dict[str, str] = {}


def _status_token(run_id: str) -> str:
    row = fetch_one(
        "SELECT COUNT(*) AS n, coalesce(sum(hash(status || supervisor_note)), 0) AS h "
        "FROM findings WHERE run_id = ?",
        [run_id],
    )
    return f"{row['n']}:{row['h']}" if row else "0:0"


def scores_for_run(run_id: str) -> dict[str, Any]:
    """Scores for a run, recomputed whenever a supervisor changes a finding."""
    token = _status_token(run_id)
    if _CACHE_TOKEN.get(run_id) != token or run_id not in _SCORE_CACHE:
        _SCORE_CACHE[run_id] = compute_and_store(run_id)
        _CACHE_TOKEN[run_id] = token
    return _SCORE_CACHE[run_id]


def invalidate_scores(run_id: str) -> None:
    _CACHE_TOKEN.pop(run_id, None)
    _SCORE_CACHE.pop(run_id, None)


def current_run_id() -> Optional[str]:
    run = latest_run()
    return run["run_id"] if run else None


def entity_rows() -> list[dict[str, Any]]:
    return fetch_dicts(
        """
        SELECT e.entity_id, e.name, e.sector, e.size_tier, e.analyst_count,
               (SELECT COUNT(*) FROM assets a WHERE a.entity_id = e.entity_id) AS assets,
               (SELECT COUNT(*) FROM alerts al WHERE al.entity_id = e.entity_id) AS alerts,
               (SELECT COUNT(*) FROM cases c WHERE c.entity_id = e.entity_id) AS cases,
               (SELECT COUNT(*) FROM escalations es WHERE es.entity_id = e.entity_id) AS escalations,
               (SELECT COUNT(*) FROM submissions s WHERE s.entity_id = e.entity_id) AS submissions
        FROM entities e ORDER BY e.entity_id
        """
    )


def stats() -> dict[str, Any]:
    counts = fetch_one(
        """
        SELECT (SELECT COUNT(*) FROM entities)    AS entities,
               (SELECT COUNT(*) FROM assets)      AS assets,
               (SELECT COUNT(*) FROM alerts)      AS alerts,
               (SELECT COUNT(*) FROM cases)       AS cases,
               (SELECT COUNT(*) FROM escalations) AS escalations,
               (SELECT COUNT(*) FROM commitments) AS commitments,
               (SELECT COUNT(*) FROM submissions) AS submissions,
               (SELECT COUNT(*) FROM findings)    AS findings,
               (SELECT COUNT(*) FROM runs)        AS runs
        """
    ) or {}
    period = fetch_one("SELECT min(created_at) AS start, max(created_at) AS end FROM alerts")
    run = latest_run()
    return {
        "counts": counts,
        "period": period,
        "latest_run": run,
        "detectors": len(catalogue()),
    }


def _decode(f: dict[str, Any]) -> dict[str, Any]:
    out = dict(f)
    if isinstance(out.get("metrics"), str):
        try:
            out["metrics"] = json.loads(out["metrics"])
        except json.JSONDecodeError:
            out["metrics"] = {}
    if isinstance(out.get("evidence_row_ids"), str):
        try:
            out["evidence_row_ids"] = json.loads(out["evidence_row_ids"])
        except json.JSONDecodeError:
            out["evidence_row_ids"] = []
    out["evidence_count"] = len(out.get("evidence_row_ids") or [])
    out["confidence"] = round(float(out.get("confidence") or 0), 2)
    return out


def findings(
    run_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    detector_id: Optional[str] = None,
    gap_type: Optional[str] = None,
    status: Optional[str] = None,
    capability_area: Optional[str] = None,
    include_evidence_ids: bool = False,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    run_id = run_id or current_run_id()
    if not run_id:
        return []
    clauses = ["run_id = ?"]
    params: list[Any] = [run_id]
    for col, val in (
        ("entity_id", entity_id),
        ("detector_id", detector_id),
        ("gap_type", gap_type),
        ("status", status),
        ("capability_area", capability_area),
    ):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    params.append(limit)
    rows = fetch_dicts(
        "SELECT f.*, e.name AS entity_name, e.sector, e.size_tier FROM findings f "
        "LEFT JOIN entities e USING (entity_id) WHERE "
        + " AND ".join(clauses)
        + " ORDER BY CASE f.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,"
        " f.confidence DESC, f.detector_id LIMIT ?",
        params,
    )
    out = [_decode(r) for r in rows]
    if not include_evidence_ids:
        for r in out:
            r["evidence_row_ids"] = r["evidence_row_ids"][:50]
    return out


def finding_detail(finding_id: str) -> Optional[dict[str, Any]]:
    row = fetch_one(
        "SELECT f.*, e.name AS entity_name, e.sector, e.size_tier FROM findings f "
        "LEFT JOIN entities e USING (entity_id) WHERE f.finding_id = ?",
        [finding_id],
    )
    if not row:
        return None
    out = _decode(row)
    det = {d["detector_id"]: d for d in catalogue()}.get(out["detector_id"])
    out["detector"] = det
    return out


EVIDENCE_QUERIES: dict[str, tuple[str, str]] = {
    "cases": (
        """
        SELECT c.case_id AS row_id, c.case_id, c.alert_id, a.rule_name, a.category,
               a.severity, a.asset_id, c.analyst_pseudo, c.opened_at, c.closed_at,
               CASE WHEN c.closed_at IS NULL THEN NULL
                    ELSE round(date_diff('second', c.opened_at, c.closed_at) / 60.0, 2)
               END AS handling_minutes,
               c.disposition, c.closure_type,
               (SELECT COUNT(*) FROM escalations e WHERE e.case_id = c.case_id) AS escalations,
               c.notes
        FROM cases c LEFT JOIN alerts a ON a.alert_id = c.alert_id
        WHERE c.case_id IN ({ph})
        ORDER BY c.case_id
        """,
        "case_id",
    ),
    "alerts": (
        """
        SELECT a.alert_id AS row_id, a.alert_id, a.rule_name, a.category, a.severity,
               a.source, a.asset_id, a.created_at,
               (SELECT COUNT(*) FROM cases c WHERE c.alert_id = a.alert_id) AS cases
        FROM alerts a WHERE a.alert_id IN ({ph}) ORDER BY a.created_at
        """,
        "alert_id",
    ),
    "assets": (
        """
        SELECT a.asset_id AS row_id, a.asset_id, a.hostname, a.ip_pseudo, a.asset_type,
               a.criticality, a.environment,
               (SELECT COUNT(*) FROM alerts al WHERE al.asset_id = a.asset_id) AS alerts
        FROM assets a WHERE a.asset_id IN ({ph}) ORDER BY a.asset_id
        """,
        "asset_id",
    ),
    "escalations": (
        """
        SELECT e.escalation_id AS row_id, e.escalation_id, e.case_id, e.from_tier,
               e.to_tier, e.escalated_at, e.reason,
               c.opened_at,
               CASE WHEN c.opened_at IS NULL THEN NULL
                    ELSE round(date_diff('second', c.opened_at, e.escalated_at) / 60.0, 2)
               END AS minutes_to_escalate
        FROM escalations e LEFT JOIN cases c ON c.case_id = e.case_id
        WHERE e.escalation_id IN ({ph}) ORDER BY e.escalation_id
        """,
        "escalation_id",
    ),
    "submissions": (
        """
        SELECT s.submission_id AS row_id, s.submission_id, s.period_start, s.period_end,
               s.declared_alert_count, s.file_hash, s.uploaded_at, s.integrity_status,
               (SELECT COUNT(*) FROM alerts a WHERE a.entity_id = s.entity_id
                  AND a.created_at >= s.period_start AND a.created_at < s.period_end)
                  AS actual_alert_count
        FROM submissions s WHERE s.submission_id IN ({ph}) ORDER BY s.submission_id
        """,
        "submission_id",
    ),
}


def finding_evidence(finding_id: str, limit: int = 500, offset: int = 0) -> dict[str, Any]:
    f = finding_detail(finding_id)
    if not f:
        return {"error": "not found"}
    ids = f["evidence_row_ids"]
    table = f["evidence_table"]
    total = len(ids)
    page = ids[offset : offset + limit]
    if table not in EVIDENCE_QUERIES or not page:
        return {
            "finding_id": finding_id,
            "evidence_table": table,
            "total": total,
            "rows": [{"row_id": i, "value": i} for i in page],
            "columns": ["row_id", "value"],
            "note": (
                "This finding's evidence is a list of identifiers rather than data rows "
                "(for example missing categories or ID ranges)."
            ),
        }
    sql, _ = EVIDENCE_QUERIES[table]
    ph = ", ".join(["?"] * len(page))
    rows = fetch_dicts(sql.format(ph=ph), page)
    return {
        "finding_id": finding_id,
        "evidence_table": table,
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": rows,
        "columns": list(rows[0].keys()) if rows else [],
    }


def overview() -> dict[str, Any]:
    run_id = current_run_id()
    entities = entity_rows()
    if not run_id:
        return {
            "run": None,
            "entities": [
                {**e, "risk_score": None, "risk_band": None, "finding_count": 0}
                for e in entities
            ],
            "kpis": {
                "entities_assessed": len(entities),
                "high_risk_entities": 0,
                "open_findings": 0,
                "execution_gaps": 0,
                "negative_space": 0,
                "anomalies": 0,
                "data_quality": 0,
            },
            "capability_areas": CAPABILITY_AREAS,
        }
    scores = scores_for_run(run_id)
    all_findings = findings(run_id=run_id, limit=100_000)
    by_entity: dict[str, list[dict]] = {}
    for f in all_findings:
        by_entity.setdefault(f["entity_id"], []).append(f)

    rows = []
    for e in entities:
        s = scores.get(e["entity_id"], {})
        mine = by_entity.get(e["entity_id"], [])
        counted = [f for f in mine if f["status"] in ("open", "valid")]
        rows.append(
            {
                **e,
                "risk_score": s.get("risk_score", 0.0),
                "risk_band": s.get("risk_band", "Low"),
                "finding_count": len(counted),
                "counts_by_gap_type": s.get("counts_by_gap_type", {}),
                "counts_by_severity": s.get("counts_by_severity", {}),
                "capability_scores": s.get("capability_scores", {}),
                "trend": s.get("trend", []),
                "trend_direction": s.get("trend_direction", "flat"),
                "top_contributors": s.get("top_contributors", []),
                "dismissed_findings": len(mine) - len(counted),
            }
        )
    rows.sort(key=lambda r: (-(r["risk_score"] or 0), r["entity_id"]))

    counted_all = [f for f in all_findings if f["status"] in ("open", "valid")]
    kpis = {
        "entities_assessed": len(entities),
        "high_risk_entities": sum(1 for r in rows if r["risk_band"] == "High"),
        "medium_risk_entities": sum(1 for r in rows if r["risk_band"] == "Medium"),
        "open_findings": sum(1 for f in counted_all if f["status"] == "open"),
        "validated_findings": sum(1 for f in counted_all if f["status"] == "valid"),
        "dismissed_findings": sum(1 for f in all_findings if f["status"] == "not_valid"),
        "execution_gaps": sum(1 for f in counted_all if f["gap_type"] == "execution_gap"),
        "negative_space": sum(1 for f in counted_all if f["gap_type"] == "negative_space"),
        "anomalies": sum(1 for f in counted_all if f["gap_type"] == "anomaly"),
        "data_quality": sum(1 for f in counted_all if f["gap_type"] == "data_quality"),
        "high_severity_findings": sum(1 for f in counted_all if f["severity"] == "high"),
    }
    return {
        "run": latest_run(),
        "entities": rows,
        "kpis": kpis,
        "capability_areas": CAPABILITY_AREAS,
        "sectors": sorted({e["sector"] for e in entities}),
    }


def entity_detail(entity_id: str) -> Optional[dict[str, Any]]:
    entity = fetch_one(
        "SELECT * FROM entities WHERE entity_id = ?", [entity_id]
    )
    if not entity:
        return None
    run_id = current_run_id()
    scores = scores_for_run(run_id) if run_id else {}
    mine = scores.get(entity_id, {})
    peers_idx = build_peer_index()
    peer_ids, peer_level = peers_idx.peers(entity_id)

    peer_caps: dict[str, list[float]] = {a: [] for a in CAPABILITY_AREAS}
    for p in peer_ids:
        caps = (scores.get(p) or {}).get("capability_scores", {})
        for area, val in caps.items():
            peer_caps.setdefault(area, []).append(val)
    radar = [
        {
            "area": area,
            "label": area.replace("_", " ").title(),
            "entity": (mine.get("capability_scores") or {}).get(area, 100.0),
            "peer_average": (
                round(sum(peer_caps[area]) / len(peer_caps[area]), 1)
                if peer_caps.get(area)
                else 100.0
            ),
        }
        for area in CAPABILITY_AREAS
    ]

    entity_findings = findings(run_id=run_id, entity_id=entity_id, limit=10_000)
    grouped: dict[str, list[dict]] = {a: [] for a in CAPABILITY_AREAS}
    for f in entity_findings:
        grouped.setdefault(f["capability_area"], []).append(f)

    timeline = fetch_dicts(
        """
        SELECT date_trunc('day', created_at) AS day, COUNT(*) AS alerts,
               SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical,
               SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) AS high
        FROM alerts WHERE entity_id = ? GROUP BY 1 ORDER BY 1
        """,
        [entity_id],
    )
    commitments = fetch_dicts(
        "SELECT metric, threshold, unit FROM commitments WHERE entity_id = ? ORDER BY metric",
        [entity_id],
    )
    submissions = fetch_dicts(
        "SELECT * FROM submissions WHERE entity_id = ? ORDER BY period_start", [entity_id]
    )
    counts = fetch_one(
        """
        SELECT (SELECT COUNT(*) FROM assets WHERE entity_id = ?)      AS assets,
               (SELECT COUNT(*) FROM assets WHERE entity_id = ? AND criticality = 'critical')
                    AS critical_assets,
               (SELECT COUNT(*) FROM alerts WHERE entity_id = ?)      AS alerts,
               (SELECT COUNT(*) FROM cases WHERE entity_id = ?)       AS cases,
               (SELECT COUNT(*) FROM escalations WHERE entity_id = ?) AS escalations
        """,
        [entity_id] * 5,
    )
    return {
        "entity": entity,
        "counts": counts,
        "run": latest_run(),
        "scores": mine,
        "radar": radar,
        "peer_group": {
            "label": peers_idx.label(entity_id),
            "comparison_level": peer_level,
            "peers": [
                {
                    "entity_id": p,
                    "name": peers_idx.entities[p]["name"],
                    "risk_score": (scores.get(p) or {}).get("risk_score", 0.0),
                }
                for p in peer_ids
            ],
        },
        "findings": entity_findings,
        "findings_by_capability": {k: v for k, v in grouped.items() if v},
        "timeline": timeline,
        "commitments": commitments,
        "submissions": submissions,
    }


def negative_space(entity_id: str) -> dict[str, Any]:
    """Coverage matrices behind the negative-space view."""
    critical_assets = fetch_dicts(
        """
        SELECT a.asset_id, a.hostname, a.asset_type, a.criticality, a.environment,
               coalesce(al.n, 0) AS alerts, al.last_alert
        FROM assets a
        LEFT JOIN (SELECT asset_id, COUNT(*) AS n, max(created_at) AS last_alert
                   FROM alerts GROUP BY asset_id) al ON al.asset_id = a.asset_id
        WHERE a.entity_id = ? AND a.criticality IN ('critical', 'high')
        ORDER BY coalesce(al.n, 0), a.asset_id
        """,
        [entity_id],
    )
    cats = fetch_dicts(
        "SELECT entity_id, category, COUNT(*) AS n FROM alerts GROUP BY 1, 2"
    )
    totals: dict[str, int] = {}
    per_entity: dict[str, dict[str, int]] = {}
    for r in cats:
        per_entity.setdefault(r["entity_id"], {})[r["category"]] = int(r["n"])
        totals[r["entity_id"]] = totals.get(r["entity_id"], 0) + int(r["n"])
    idx = build_peer_index()
    peer_ids, level = idx.peers(entity_id)
    all_categories = sorted({c for v in per_entity.values() for c in v})
    mine = per_entity.get(entity_id, {})
    category_rows = []
    for cat in all_categories:
        peers_with = [p for p in peer_ids if per_entity.get(p, {}).get(cat, 0) >= 5]
        peer_share = len(peers_with) / len(peer_ids) if peer_ids else 0.0
        category_rows.append(
            {
                "category": cat,
                "entity_alerts": mine.get(cat, 0),
                "entity_share": round(
                    mine.get(cat, 0) / max(totals.get(entity_id, 1), 1), 4
                ),
                "peers_reporting": len(peers_with),
                "peer_count": len(peer_ids),
                "peer_presence": round(peer_share, 3),
                "missing": mine.get(cat, 0) == 0 and peer_share >= 0.8,
            }
        )
    related = findings(entity_id=entity_id, gap_type="negative_space", limit=100)
    return {
        "entity_id": entity_id,
        "comparison_level": level,
        "critical_assets": critical_assets,
        "silent_critical_assets": [a for a in critical_assets if a["alerts"] <= 1],
        "categories": category_rows,
        "missing_categories": [c for c in category_rows if c["missing"]],
        "related_findings": related,
    }


def methodology() -> dict[str, Any]:
    return {"detectors": catalogue(), "peer_groups": peer_groups()}
