"""D08 - closures piling up just inside a declared SLA threshold."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    pct,
    severity_from_confidence,
)
from app.schema import Finding

#: metric name -> severity the SLA applies to
SLA_METRICS = {
    "high_alert_investigation_minutes": "high",
    "critical_alert_investigation_minutes": "critical",
    "medium_alert_investigation_minutes": "medium",
}
BAND = 0.10  # compare the 10% window just below the SLA with the one just above
MIN_IN_BAND = 25
MIN_RATIO = 3.0
MIN_SHARE = 0.12


class D08ThresholdGaming(Detector):
    id = "D08"
    version = "1.1.0"
    name = "threshold_gaming"
    gap_type = "execution_gap"
    capability_area = "operational_discipline"
    min_sample = MIN_IN_BAND
    description = (
        "An unnatural pile-up of closures in the last minutes before a declared SLA "
        "expires, which is the signature of closing to the clock rather than to the "
        "evidence."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        commitments = ctx.q(
            "SELECT entity_id, metric, threshold FROM commitments "
            "WHERE metric IN ('high_alert_investigation_minutes', "
            "'critical_alert_investigation_minutes', 'medium_alert_investigation_minutes') "
            "ORDER BY entity_id, metric"
        )
        findings: list[Finding] = []
        for c in commitments:
            entity_id = c["entity_id"]
            severity = SLA_METRICS[c["metric"]]
            t = float(c["threshold"] or 0)
            if t <= 0:
                continue
            lo, hi = t * (1 - BAND), t * (1 + BAND)
            row = ctx.q(
                """
                SELECT
                  COUNT(*) AS n,
                  SUM(CASE WHEN handling_minutes >= ? AND handling_minutes < ? THEN 1 ELSE 0 END) AS just_inside,
                  SUM(CASE WHEN handling_minutes >= ? AND handling_minutes < ? THEN 1 ELSE 0 END) AS just_outside
                FROM case_facts
                WHERE entity_id = ? AND severity = ? AND closure_type = 'manual'
                  AND handling_minutes IS NOT NULL
                """,
                [lo, t, t, hi, entity_id, severity],
            )[0]
            n = int(row["n"] or 0)
            inside = int(row["just_inside"] or 0)
            outside = int(row["just_outside"] or 0)
            if n < 100 or inside < MIN_IN_BAND:
                continue
            share = inside / n
            ratio = inside / max(outside, 1)
            if ratio < MIN_RATIO or share < MIN_SHARE:
                continue
            ev = ctx.q(
                """
                SELECT case_id FROM case_facts
                WHERE entity_id = ? AND severity = ? AND closure_type = 'manual'
                  AND handling_minutes >= ? AND handling_minutes < ?
                ORDER BY handling_minutes DESC, case_id LIMIT 2000
                """,
                [entity_id, severity, lo, t],
            )
            effect = min(1.0, share / 0.4)
            conf = confidence_from(n, effect, 100)
            rationale = (
                f"This organisation declares that {severity} alerts are handled within "
                f"{t:.0f} minutes. {inside:,} closures ({pct(share)} of all {severity} "
                f"closures) land in the final {t * BAND:.0f} minutes before that "
                f"deadline, against only {outside:,} in the equivalent window just "
                f"after it - a {ratio:.1f}x pile-up. A genuine workload does not bunch "
                "up against a target like this."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title=f"Closures bunched just inside the {t:.0f}-minute SLA",
                    rationale=rationale,
                    innocent_explanation=(
                        "Teams reasonably prioritise work that is about to breach an SLA, "
                        "so some bunching is normal. An automated reminder that fires a "
                        "few minutes before the deadline would produce the same shape "
                        "without anyone gaming the metric."
                    ),
                    metrics={
                        "sla_metric": c["metric"],
                        "sla_minutes": t,
                        "severity": severity,
                        "closures_considered": n,
                        "closures_just_inside_sla": inside,
                        "closures_just_outside_sla": outside,
                        "pileup_ratio": round(ratio, 2),
                        "share_just_inside": round(share, 4),
                        "band_fraction": BAND,
                    },
                    evidence_row_ids=[e["case_id"] for e in ev],
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key=f"gaming:{c['metric']}",
                )
            )
        return findings
