"""D10 - critical assets that produced no telemetry at all (negative space)."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    median,
    pct,
    severity_from_confidence,
)
from app.schema import Finding

SILENT_ALERT_THRESHOLD = 1  # <= this many alerts in the whole period counts as silent
MIN_CRITICAL_ASSETS = 8
MIN_SHARE = 0.15
PEER_MARGIN_PP = 0.10


class D10SilentCriticalAssets(Detector):
    id = "D10"
    version = "1.1.0"
    name = "silent_critical_assets"
    gap_type = "negative_space"
    capability_area = "threat_detection"
    min_sample = MIN_CRITICAL_ASSETS
    description = (
        "Assets the organisation itself classifies as critical, but which generated "
        "no alerts during the reporting period - evidence that should exist and does "
        "not."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            f"""
            SELECT a.entity_id,
                   COUNT(*)                                                AS crit_assets,
                   SUM(CASE WHEN coalesce(al.n, 0) <= {SILENT_ALERT_THRESHOLD}
                            THEN 1 ELSE 0 END)                             AS silent,
                   median(coalesce(al.n, 0))                               AS median_alerts
            FROM assets a
            LEFT JOIN (SELECT asset_id, COUNT(*) AS n FROM alerts GROUP BY asset_id) al
                   ON al.asset_id = a.asset_id
            WHERE a.criticality = 'critical'
            GROUP BY a.entity_id
            """
        )
        stats = {r["entity_id"]: r for r in rows}
        shares = {
            e: (r["silent"] or 0) / r["crit_assets"]
            for e, r in stats.items()
            if (r["crit_assets"] or 0) > 0
        }

        findings: list[Finding] = []
        for entity_id, r in stats.items():
            total = int(r["crit_assets"] or 0)
            silent = int(r["silent"] or 0)
            if total < MIN_CRITICAL_ASSETS or silent < 3:
                continue
            share = silent / total
            peers, _ = ctx.peers.peers(entity_id)
            peer_share = median([shares[p] for p in peers if p in shares])
            if share < max(MIN_SHARE, peer_share + PEER_MARGIN_PP):
                continue

            ev = ctx.q(
                f"""
                SELECT a.asset_id, a.hostname, a.asset_type, a.environment
                FROM assets a
                LEFT JOIN (SELECT asset_id, COUNT(*) AS n FROM alerts GROUP BY asset_id) al
                       ON al.asset_id = a.asset_id
                WHERE a.entity_id = ? AND a.criticality = 'critical'
                  AND coalesce(al.n, 0) <= {SILENT_ALERT_THRESHOLD}
                ORDER BY a.asset_id LIMIT 2000
                """,
                [entity_id],
            )
            by_type: dict[str, int] = {}
            for row in ev:
                by_type[row["asset_type"]] = by_type.get(row["asset_type"], 0) + 1
            coverage = ctx.q(
                "SELECT threshold FROM commitments WHERE entity_id = ? AND metric = "
                "'critical_asset_monitoring_coverage'",
                [entity_id],
            )
            effect = min(1.0, share / 0.5)
            conf = confidence_from(total, effect, MIN_CRITICAL_ASSETS)
            type_txt = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items()))
            rationale = (
                f"{silent} of {total} assets this organisation classifies as critical "
                f"({pct(share)}) produced no alerts at all during the period "
                f"({type_txt}). Peer organisations leave {pct(peer_share)} of their "
                f"critical assets silent. The median critical asset here produced "
                f"{int(r['median_alerts'] or 0)} alerts, so silence is not a "
                "portfolio-wide pattern."
                + (
                    f" The organisation declares {coverage[0]['threshold']:.0f}% "
                    "monitoring coverage of critical assets."
                    if coverage
                    else ""
                )
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Critical assets produced no alerts in the period",
                    rationale=rationale,
                    innocent_explanation=(
                        "These hosts may be genuinely quiet - newly built, isolated in an "
                        "air-gapped OT segment, powered down for maintenance, or covered "
                        "by a monitoring tool whose output was not included in this "
                        "submission. The asset inventory may also be stale."
                    ),
                    metrics={
                        "critical_assets": total,
                        "silent_critical_assets": silent,
                        "share_silent": round(share, 4),
                        "peer_median_share": round(peer_share, 4),
                        "median_alerts_per_critical_asset": int(r["median_alerts"] or 0),
                        "silent_by_asset_type": by_type,
                        "silence_threshold_alerts": SILENT_ALERT_THRESHOLD,
                    },
                    evidence_row_ids=[r2["asset_id"] for r2 in ev],
                    evidence_table="assets",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="silent_critical_assets",
                )
            )
        return findings
