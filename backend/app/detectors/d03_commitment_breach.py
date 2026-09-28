"""D03 - actual performance measured against the entity's own declared commitments."""
from __future__ import annotations

from typing import Any

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    fmt_minutes,
    severity_from_confidence,
)
from app.schema import Finding

#: Actuals must exceed the declared threshold by this factor before we call it a
#: breach, so ordinary noise never produces a finding.
BREACH_MARGIN = 1.15
COVERAGE_TOLERANCE_PP = 5.0


class D03CommitmentBreach(Detector):
    id = "D03"
    version = "1.1.0"
    name = "commitment_breach"
    gap_type = "execution_gap"
    capability_area = "escalation"
    min_sample = 20
    description = (
        "Measured performance against the commitments the organisation itself "
        "declared, for example 'criticals escalated within 15 minutes'."
    )

    # ------------------------------------------------------------------ actuals
    def _actuals(self, ctx: RunContext) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}

        def put(entity_id: str, key: str, value: Any, n: int) -> None:
            out.setdefault(entity_id, {})[key] = {"value": value, "n": n}

        for r in ctx.q(
            """
            SELECT entity_id, median(escalation_minutes) AS v, COUNT(*) AS n
            FROM case_facts
            WHERE severity = 'critical' AND escalation_minutes IS NOT NULL
            GROUP BY entity_id
            """
        ):
            put(r["entity_id"], "critical_escalation_minutes", r["v"], int(r["n"]))

        for sev, metric in (
            ("critical", "critical_alert_investigation_minutes"),
            ("high", "high_alert_investigation_minutes"),
        ):
            for r in ctx.q(
                """
                SELECT entity_id, median(handling_minutes) AS v, COUNT(*) AS n
                FROM case_facts
                WHERE severity = ? AND handling_minutes IS NOT NULL
                GROUP BY entity_id
                """,
                [sev],
            ):
                put(r["entity_id"], metric, r["v"], int(r["n"]))

        for r in ctx.q(
            """
            SELECT entity_id, avg(handling_minutes) / 60.0 AS v, COUNT(*) AS n
            FROM case_facts WHERE handling_minutes IS NOT NULL GROUP BY entity_id
            """
        ):
            put(r["entity_id"], "mean_time_to_close_hours", r["v"], int(r["n"]))

        for r in ctx.q(
            """
            SELECT a.entity_id,
                   COUNT(*)                                        AS n,
                   100.0 * SUM(CASE WHEN al.n > 0 THEN 1 ELSE 0 END) / COUNT(*) AS v
            FROM assets a
            LEFT JOIN (SELECT asset_id, COUNT(*) AS n FROM alerts GROUP BY asset_id) al
                   ON al.asset_id = a.asset_id
            WHERE a.criticality = 'critical'
            GROUP BY a.entity_id
            """
        ):
            put(r["entity_id"], "critical_asset_monitoring_coverage", r["v"], int(r["n"]))
        return out

    def _evidence(self, ctx: RunContext, entity_id: str, metric: str, threshold: float):
        if metric == "critical_escalation_minutes":
            rows = ctx.q(
                """
                SELECT escalation_id AS id FROM case_facts
                WHERE entity_id = ? AND severity = 'critical'
                  AND escalation_minutes > ? AND escalation_id IS NOT NULL
                ORDER BY escalation_minutes DESC, escalation_id LIMIT 2000
                """,
                [entity_id, threshold],
            )
            return [r["id"] for r in rows], "escalations"
        if metric == "critical_asset_monitoring_coverage":
            rows = ctx.q(
                """
                SELECT a.asset_id AS id FROM assets a
                LEFT JOIN (SELECT asset_id, COUNT(*) AS n FROM alerts GROUP BY asset_id) al
                       ON al.asset_id = a.asset_id
                WHERE a.entity_id = ? AND a.criticality = 'critical'
                  AND coalesce(al.n, 0) = 0
                ORDER BY a.asset_id LIMIT 2000
                """,
                [entity_id],
            )
            return [r["id"] for r in rows], "assets"
        sev = {
            "critical_alert_investigation_minutes": "critical",
            "high_alert_investigation_minutes": "high",
        }.get(metric)
        if sev:
            rows = ctx.q(
                """
                SELECT case_id AS id FROM case_facts
                WHERE entity_id = ? AND severity = ? AND handling_minutes > ?
                ORDER BY handling_minutes DESC, case_id LIMIT 2000
                """,
                [entity_id, sev, threshold],
            )
            return [r["id"] for r in rows], "cases"
        rows = ctx.q(
            """
            SELECT case_id AS id FROM case_facts
            WHERE entity_id = ? AND handling_minutes > ?
            ORDER BY handling_minutes DESC, case_id LIMIT 2000
            """,
            [entity_id, threshold * 60.0],
        )
        return [r["id"] for r in rows], "cases"

    # ---------------------------------------------------------------------- run
    def run(self, ctx: RunContext) -> list[Finding]:
        actuals = self._actuals(ctx)
        commitments = ctx.q(
            "SELECT entity_id, metric, threshold, unit FROM commitments "
            "ORDER BY entity_id, metric"
        )
        findings: list[Finding] = []
        for c in commitments:
            entity_id, metric = c["entity_id"], c["metric"]
            threshold = float(c["threshold"] or 0)
            actual = actuals.get(entity_id, {}).get(metric)
            if not actual or actual["value"] is None:
                continue
            value, n = float(actual["value"]), int(actual["n"])
            if n < self.min_sample:
                continue

            higher_is_better = metric.endswith("coverage")
            if higher_is_better:
                breached = value < threshold - COVERAGE_TOLERANCE_PP
                ratio = (threshold - value) / max(threshold, 1.0)
            else:
                breached = value > threshold * BREACH_MARGIN
                ratio = (value - threshold) / max(threshold, 1e-6)
            if not breached:
                continue

            evidence, table = self._evidence(ctx, entity_id, metric, threshold)
            effect = min(1.0, ratio / 2.0 if not higher_is_better else ratio / 0.5)
            conf = confidence_from(n, effect, self.min_sample)
            pretty = metric.replace("_", " ")
            if c["unit"] == "minutes":
                actual_txt, target_txt = fmt_minutes(value), fmt_minutes(threshold)
            elif c["unit"] == "hours":
                actual_txt, target_txt = f"{value:.1f} hours", f"{threshold:.0f} hours"
            else:
                actual_txt, target_txt = f"{value:.1f}%", f"{threshold:.0f}%"
            rationale = (
                f"This organisation declared a commitment of {target_txt} for "
                f"'{pretty}'. Measured across {n:,} records in this submission the "
                f"actual figure is {actual_txt}"
                + (
                    f", i.e. {value / max(threshold, 1e-6):.1f} times its own target."
                    if not higher_is_better
                    else f", i.e. {threshold - value:.1f} percentage points short of its own target."
                )
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title=f"Declared commitment not met: {pretty}",
                    rationale=rationale,
                    innocent_explanation=(
                        "The commitment may have been signed for a different scope or "
                        "period than this submission covers, or the organisation may "
                        "measure the same metric from a different start point (for "
                        "example from triage rather than from alert creation)."
                    ),
                    metrics={
                        "metric": metric,
                        "declared_threshold": threshold,
                        "unit": c["unit"],
                        "actual_value": round(value, 2),
                        "sample_size": n,
                        "breach_ratio": round(ratio, 3),
                        "records_beyond_threshold": len(evidence),
                    },
                    evidence_row_ids=evidence,
                    evidence_table=table,
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key=f"commitment:{metric}",
                )
            )
        return findings
