"""D12 - a sudden drop against the entity's own historical baseline."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    pct,
    severity_from_confidence,
)
from app.schema import Finding

RECENT_DAYS = 30
MIN_BASELINE_PER_DAY = 5.0
MIN_DROP = 0.45


class D12VolumeDrop(Detector):
    id = "D12"
    version = "1.1.0"
    name = "volume_drop"
    gap_type = "negative_space"
    capability_area = "security_operations"
    min_sample = 30
    description = (
        "Alert volume in the most recent window collapsing against the same "
        "organisation's earlier baseline - telemetry that used to arrive and no "
        "longer does."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            f"""
            WITH bounds AS (
                SELECT entity_id, max(created_at) AS last_seen, min(created_at) AS first_seen
                FROM alerts GROUP BY entity_id
            )
            SELECT a.entity_id,
                   b.first_seen,
                   b.last_seen,
                   SUM(CASE WHEN a.created_at >= b.last_seen - INTERVAL {RECENT_DAYS} DAY
                            THEN 1 ELSE 0 END) AS recent_n,
                   SUM(CASE WHEN a.created_at <  b.last_seen - INTERVAL {RECENT_DAYS} DAY
                            THEN 1 ELSE 0 END) AS prior_n,
                   date_diff('day', b.first_seen, b.last_seen - INTERVAL {RECENT_DAYS} DAY) AS prior_days
            FROM alerts a JOIN bounds b USING (entity_id)
            GROUP BY a.entity_id, b.first_seen, b.last_seen
            """
        )
        findings: list[Finding] = []
        for r in rows:
            prior_days = int(r["prior_days"] or 0)
            if prior_days < RECENT_DAYS:
                continue
            recent_rate = int(r["recent_n"] or 0) / RECENT_DAYS
            prior_rate = int(r["prior_n"] or 0) / prior_days
            if prior_rate < MIN_BASELINE_PER_DAY:
                continue
            drop = 1.0 - (recent_rate / prior_rate)
            if drop < MIN_DROP:
                continue
            weekly = ctx.q(
                """
                SELECT date_trunc('week', created_at) AS week, COUNT(*) AS n
                FROM alerts WHERE entity_id = ?
                GROUP BY 1 ORDER BY 1
                """,
                [r["entity_id"]],
            )
            ev = ctx.q(
                f"""
                SELECT alert_id FROM alerts
                WHERE entity_id = ?
                  AND created_at >= (SELECT max(created_at) FROM alerts WHERE entity_id = ?)
                                    - INTERVAL {RECENT_DAYS} DAY
                ORDER BY created_at, alert_id LIMIT 2000
                """,
                [r["entity_id"], r["entity_id"]],
            )
            effect = min(1.0, drop / 0.8)
            conf = confidence_from(int(r["prior_n"] or 0), effect, 500)
            rationale = (
                f"Alert volume in the last {RECENT_DAYS} days fell {pct(drop)} against "
                f"this organisation's own earlier baseline: {recent_rate:.1f} alerts per "
                f"day now versus {prior_rate:.1f} per day over the preceding "
                f"{prior_days} days. Nothing in the submission explains the change. A "
                "drop like this usually means a collector, log source or forwarder "
                "stopped - not that the threat landscape improved."
            )
            findings.append(
                self.finding(
                    ctx,
                    r["entity_id"],
                    title="Alert volume collapsed against the entity's own baseline",
                    rationale=rationale,
                    innocent_explanation=(
                        "A genuine and welcome reduction can follow rule tuning, a "
                        "network segmentation project, or decommissioning noisy assets. "
                        "The most recent period may also simply be incomplete at the "
                        "time of export."
                    ),
                    metrics={
                        "recent_window_days": RECENT_DAYS,
                        "recent_alerts_per_day": round(recent_rate, 2),
                        "baseline_alerts_per_day": round(prior_rate, 2),
                        "drop_share": round(drop, 4),
                        "baseline_days": prior_days,
                        "weekly_counts": [
                            {"week": str(w["week"])[:10], "alerts": int(w["n"])}
                            for w in weekly
                        ],
                    },
                    evidence_row_ids=[e["alert_id"] for e in ev],
                    evidence_table="alerts",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="volume_drop",
                )
            )
        return findings
