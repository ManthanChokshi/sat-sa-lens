"""Detector framework: base class, shared statistics and finding construction."""
from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence

import duckdb

from app.config import MIN_PEERS, RULES_VERSION

#: Hard cap on how many evidence row IDs one finding stores. The true count is
#: always kept in metrics as evidence_rows_total.
EVIDENCE_ID_CAP = 2000
from app.schema import Finding

# Views recreated before every analysis run so detectors can stay short.
VIEW_SQL = """
CREATE OR REPLACE VIEW case_facts AS
SELECT
    c.case_id,
    c.entity_id,
    c.alert_id,
    c.analyst_pseudo,
    c.opened_at,
    c.closed_at,
    c.disposition,
    c.closure_type,
    c.notes,
    a.severity,
    a.category,
    a.rule_name,
    a.asset_id,
    a.source,
    a.created_at AS alert_created_at,
    CASE WHEN c.closed_at IS NULL THEN NULL
         ELSE date_diff('second', c.opened_at, c.closed_at) / 60.0 END AS handling_minutes,
    e.escalation_id,
    e.escalated_at,
    CASE WHEN e.escalated_at IS NULL THEN NULL
         ELSE date_diff('second', c.opened_at, e.escalated_at) / 60.0 END AS escalation_minutes
FROM cases c
LEFT JOIN alerts a ON a.alert_id = c.alert_id
LEFT JOIN (
    SELECT case_id, min(escalation_id) AS escalation_id, min(escalated_at) AS escalated_at
    FROM escalations GROUP BY case_id
) e ON e.case_id = c.case_id;

CREATE OR REPLACE VIEW entity_period AS
SELECT
    entity_id,
    min(created_at) AS first_alert,
    max(created_at) AS last_alert,
    COUNT(*)        AS alert_count
FROM alerts GROUP BY entity_id;
"""


@dataclass
class PeerIndex:
    """Peer grouping with a documented fallback ladder.

    Exact peer group is sector + size_tier. Real supervisory portfolios are
    small, so when a group has fewer than MIN_PEERS other members we widen to
    the sector, then to the size tier, then to the whole portfolio. The level
    used is reported in every finding's metrics so a supervisor can judge how
    fair the comparison is.
    """

    entities: dict[str, dict[str, Any]]

    def peers(self, entity_id: str) -> tuple[list[str], str]:
        me = self.entities.get(entity_id)
        if not me:
            return [], "none"
        ladders = [
            (
                "sector+tier",
                [
                    e
                    for e, v in self.entities.items()
                    if e != entity_id
                    and v["sector"] == me["sector"]
                    and v["size_tier"] == me["size_tier"]
                ],
            ),
            (
                "sector",
                [
                    e
                    for e, v in self.entities.items()
                    if e != entity_id and v["sector"] == me["sector"]
                ],
            ),
            (
                "size_tier",
                [
                    e
                    for e, v in self.entities.items()
                    if e != entity_id and v["size_tier"] == me["size_tier"]
                ],
            ),
            ("portfolio", [e for e in self.entities if e != entity_id]),
        ]
        for label, members in ladders:
            if len(members) >= MIN_PEERS:
                return sorted(members), label
        return sorted(ladders[-1][1]), "portfolio"

    def label(self, entity_id: str) -> str:
        me = self.entities.get(entity_id, {})
        return f"{me.get('sector', '?')}/{me.get('size_tier', '?')}"


@dataclass
class RunContext:
    """Everything a detector needs for one analysis run."""

    conn: duckdb.DuckDBPyConnection
    run_id: str
    peers: PeerIndex
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    cache: dict[str, Any] = field(default_factory=dict)

    def q(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    @property
    def entity_ids(self) -> list[str]:
        return sorted(self.peers.entities)

    def entity(self, entity_id: str) -> dict[str, Any]:
        return self.peers.entities.get(entity_id, {})


# ------------------------------------------------------------------ statistics
def median(values: Iterable[float]) -> float:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return 0.0
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def mad(values: Iterable[float]) -> float:
    """Median absolute deviation - robust spread measure."""
    vals = [v for v in values if v is not None]
    if not vals:
        return 0.0
    m = median(vals)
    return median([abs(v - m) for v in vals])


def robust_z(value: float, peer_values: Iterable[float]) -> float:
    peers = [v for v in peer_values if v is not None]
    if len(peers) < 2:
        return 0.0
    m = median(peers)
    spread = mad(peers) * 1.4826
    if spread <= 1e-9:
        # Every peer sits on the same value. Use a small floor so the score stays
        # finite and readable instead of exploding to six figures.
        spread = max(0.02, abs(m) * 0.12)
    z = (value - m) / spread
    return max(-50.0, min(50.0, z))


def wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson interval - never over-claims on small samples."""
    if total <= 0:
        return 0.0
    p = successes / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, (centre - margin) / denom)


def shrink_to_peer(rate: float, n: int, peer_rate: float, strength: float = 25.0) -> float:
    """Empirical-Bayes style shrinkage of a rate toward the peer mean."""
    if n <= 0:
        return peer_rate
    w = n / (n + strength)
    return w * rate + (1 - w) * peer_rate


def confidence_from(
    sample_size: int,
    effect: float,
    min_sample: int,
    cap: float = 0.95,
    floor: float = 0.35,
) -> float:
    """Confidence grows with sample size and with how large the effect is.

    Deliberately conservative: never returns 1.0, because every finding is a
    hypothesis for a human to confirm.
    """
    if sample_size <= 0:
        return floor
    size_term = min(1.0, math.log10(1 + sample_size) / math.log10(1 + 10 * max(min_sample, 1)))
    effect_term = min(1.0, max(0.0, effect))
    raw = 0.45 * size_term + 0.55 * effect_term
    return round(min(cap, max(floor, raw)), 2)


def severity_from_confidence(effect: float, confidence: float) -> str:
    score = effect * confidence
    if score >= 0.55:
        return "high"
    if score >= 0.28:
        return "medium"
    return "low"


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def fmt_minutes(minutes: Optional[float]) -> str:
    if minutes is None:
        return "n/a"
    if minutes < 1:
        return f"{minutes * 60:.0f} seconds"
    if minutes < 90:
        return f"{minutes:.1f} minutes"
    if minutes < 60 * 48:
        return f"{minutes / 60:.1f} hours"
    return f"{minutes / 1440:.1f} days"


# ------------------------------------------------------------------- base class
class Detector(ABC):
    """One detector = one hypothesis about a SOC weakness."""

    id: str = "D00"
    version: str = "1.0.0"
    name: str = "unnamed"
    gap_type: str = "execution_gap"
    capability_area: str = "security_operations"
    #: plain-English description used in docs and in the UI methodology panel
    description: str = ""
    #: minimum rows before the detector is allowed to speak
    min_sample: int = 30

    @abstractmethod
    def run(self, ctx: RunContext) -> list[Finding]:  # pragma: no cover - interface
        ...

    # ---------------------------------------------------------------- utilities
    def finding(
        self,
        ctx: RunContext,
        entity_id: str,
        title: str,
        rationale: str,
        innocent_explanation: str,
        metrics: dict[str, Any],
        evidence_row_ids: Sequence[str],
        evidence_table: str,
        severity: str,
        confidence: float,
        key: str = "",
    ) -> Finding:
        peers, peer_level = ctx.peers.peers(entity_id)
        enriched = dict(metrics)
        enriched.setdefault("peer_group", ctx.peers.label(entity_id))
        enriched["peer_comparison_level"] = peer_level
        enriched["peer_count"] = len(peers)
        enriched["rules_version"] = RULES_VERSION
        enriched["evidence_rows_total"] = len(evidence_row_ids)
        enriched["evidence_rows_stored"] = min(len(evidence_row_ids), EVIDENCE_ID_CAP)
        digest = hashlib.sha1(
            f"{ctx.run_id}|{self.id}|{entity_id}|{key}".encode()
        ).hexdigest()[:16]
        return Finding(
            finding_id=f"F-{digest}",
            run_id=ctx.run_id,
            entity_id=entity_id,
            detector_id=self.id,
            detector_version=self.version,
            gap_type=self.gap_type,  # type: ignore[arg-type]
            capability_area=self.capability_area,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            confidence=confidence,
            title=title,
            rationale=rationale,
            innocent_explanation=innocent_explanation,
            metrics=enriched,
            evidence_row_ids=[str(x) for x in evidence_row_ids][:EVIDENCE_ID_CAP],
            evidence_table=evidence_table,
        )


def finding_to_row(f: Finding) -> list[Any]:
    return [
        f.finding_id,
        f.run_id,
        f.entity_id,
        f.detector_id,
        f.detector_version,
        f.gap_type,
        f.capability_area,
        f.severity,
        float(f.confidence),
        f.title,
        f.rationale,
        f.innocent_explanation,
        json.dumps(f.metrics, default=str, sort_keys=True),
        json.dumps(f.evidence_row_ids),
        f.evidence_table,
        f.status,
        f.supervisor_note,
        f.created_at,
    ]
