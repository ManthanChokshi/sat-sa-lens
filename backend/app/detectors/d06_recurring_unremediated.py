"""D06 - the same rule firing on the same asset forever, closed every time."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    severity_from_confidence,
)
from app.schema import Finding

MIN_OCCURRENCES = 25
MIN_DISTINCT_DAYS = 15
MIN_CLOSED_SHARE = 0.85


class D06RecurringUnremediated(Detector):
    id = "D06"
    version = "1.1.0"
    name = "recurring_unremediated"
    gap_type = "execution_gap"
    capability_area = "incident_response"
    min_sample = MIN_OCCURRENCES
    description = (
        "One rule firing repeatedly on one asset, closed every time, never escalated "
        "and never remediated - the alert is being absorbed instead of fixed."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            f"""
            SELECT cf.entity_id,
                   cf.asset_id,
                   cf.rule_name,
                   max(cf.severity)                             AS severity,
                   COUNT(*)                                     AS occurrences,
                   COUNT(DISTINCT date_trunc('day', cf.alert_created_at)) AS distinct_days,
                   SUM(CASE WHEN cf.closed_at IS NOT NULL THEN 1 ELSE 0 END) AS closed_n,
                   SUM(CASE WHEN cf.escalation_id IS NOT NULL THEN 1 ELSE 0 END) AS escalated_n,
                   min(cf.alert_created_at)                     AS first_seen,
                   max(cf.alert_created_at)                     AS last_seen
            FROM case_facts cf
            WHERE cf.asset_id IS NOT NULL AND cf.rule_name IS NOT NULL
            GROUP BY cf.entity_id, cf.asset_id, cf.rule_name
            HAVING COUNT(*) >= {MIN_OCCURRENCES}
               AND COUNT(DISTINCT date_trunc('day', cf.alert_created_at)) >= {MIN_DISTINCT_DAYS}
               AND SUM(CASE WHEN cf.escalation_id IS NOT NULL THEN 1 ELSE 0 END) = 0
            ORDER BY cf.entity_id, COUNT(*) DESC, cf.asset_id, cf.rule_name
            """
        )
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            if (r["closed_n"] or 0) / max(r["occurrences"], 1) < MIN_CLOSED_SHARE:
                continue
            grouped.setdefault(r["entity_id"], []).append(r)

        findings: list[Finding] = []
        for entity_id, pairs in grouped.items():
            top = sorted(pairs, key=lambda r: -r["occurrences"])[:20]
            total_occurrences = sum(int(p["occurrences"]) for p in pairs)
            ids: list[str] = []
            for p in top[:6]:
                ev = ctx.q(
                    """
                    SELECT case_id FROM case_facts
                    WHERE entity_id = ? AND asset_id = ? AND rule_name = ?
                    ORDER BY alert_created_at, case_id LIMIT 400
                    """,
                    [entity_id, p["asset_id"], p["rule_name"]],
                )
                ids.extend(e["case_id"] for e in ev)
            worst = top[0]
            effect = min(1.0, len(pairs) / 3.0 * 0.5 + min(1.0, worst["occurrences"] / 60) * 0.5)
            conf = confidence_from(total_occurrences, effect, MIN_OCCURRENCES)
            rationale = (
                f"{len(pairs)} rule/asset combinations fire again and again and are "
                f"closed every time without a single escalation. The worst is "
                f"'{worst['rule_name']}' on asset {worst['asset_id']}: "
                f"{worst['occurrences']} occurrences across {worst['distinct_days']} "
                f"separate days ({str(worst['first_seen'])[:10]} to "
                f"{str(worst['last_seen'])[:10]}), severity {worst['severity']}, "
                f"{worst['closed_n']} closed, 0 escalated. Repeat alerts on the same "
                "asset normally stop once the underlying cause is fixed."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Same alert recurring on the same asset, never remediated",
                    rationale=rationale,
                    innocent_explanation=(
                        "The alert may be a known, accepted-risk condition with a "
                        "documented exception, or a noisy rule awaiting tuning. Some OT "
                        "assets legitimately produce the same event daily and the team "
                        "may track remediation in a change system outside this data."
                    ),
                    metrics={
                        "recurring_pairs": len(pairs),
                        "total_occurrences": total_occurrences,
                        "worst_rule": worst["rule_name"],
                        "worst_asset": worst["asset_id"],
                        "worst_occurrences": int(worst["occurrences"]),
                        "worst_distinct_days": int(worst["distinct_days"]),
                        "min_occurrences_threshold": MIN_OCCURRENCES,
                        "pairs": [
                            {
                                "asset_id": p["asset_id"],
                                "rule_name": p["rule_name"],
                                "severity": p["severity"],
                                "occurrences": int(p["occurrences"]),
                                "distinct_days": int(p["distinct_days"]),
                            }
                            for p in top
                        ],
                    },
                    evidence_row_ids=ids,
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="recurring",
                )
            )
        return findings
