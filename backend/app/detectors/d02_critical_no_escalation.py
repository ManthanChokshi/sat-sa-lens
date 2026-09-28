"""D02 - critical alerts closed with no escalation record at all."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    median,
    pct,
    severity_from_confidence,
    wilson_lower_bound,
)
from app.schema import Finding

MIN_SHARE = 0.30
PEER_MULTIPLE = 3.0


class D02CriticalNoEscalation(Detector):
    id = "D02"
    version = "1.1.0"
    name = "critical_no_escalation"
    gap_type = "execution_gap"
    capability_area = "escalation"
    min_sample = 25
    description = (
        "Critical alerts that were closed without any escalation row, meaning the "
        "organisation's own escalation process left no trace."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT entity_id,
                   COUNT(*) AS crit_n,
                   SUM(CASE WHEN escalation_id IS NULL THEN 1 ELSE 0 END) AS no_esc_n
            FROM case_facts
            WHERE severity = 'critical' AND closed_at IS NOT NULL
            GROUP BY entity_id
            """
        )
        stats = {r["entity_id"]: r for r in rows}
        shares = {
            e: (r["no_esc_n"] or 0) / r["crit_n"]
            for e, r in stats.items()
            if (r["crit_n"] or 0) > 0
        }

        findings: list[Finding] = []
        for entity_id, r in stats.items():
            n = int(r["crit_n"] or 0)
            miss = int(r["no_esc_n"] or 0)
            if n < self.min_sample:
                continue
            share = miss / n
            peers, _ = ctx.peers.peers(entity_id)
            peer_share = median([shares[p] for p in peers if p in shares])
            lower = wilson_lower_bound(miss, n)
            if lower < MIN_SHARE or share < max(MIN_SHARE, peer_share * PEER_MULTIPLE):
                continue

            ev = ctx.q(
                """
                SELECT case_id FROM case_facts
                WHERE entity_id = ? AND severity = 'critical'
                  AND closed_at IS NOT NULL AND escalation_id IS NULL
                ORDER BY case_id LIMIT 2000
                """,
                [entity_id],
            )
            commitment = ctx.q(
                "SELECT threshold FROM commitments WHERE entity_id = ? "
                "AND metric = 'critical_escalation_minutes'",
                [entity_id],
            )
            effect = min(1.0, share / 0.8)
            conf = confidence_from(n, effect, self.min_sample)
            declared = commitment[0]["threshold"] if commitment else None
            metrics = {
                "critical_cases_closed": n,
                "critical_cases_without_escalation": miss,
                "share_without_escalation": round(share, 4),
                "wilson_lower_bound": round(lower, 4),
                "peer_median_share": round(peer_share, 4),
                "declared_escalation_minutes": declared,
            }
            rationale = (
                f"{pct(share)} of closed critical alerts ({miss} of {n}) have no "
                f"escalation record of any kind. Peers in the same group leave "
                f"{pct(peer_share)} of their criticals unescalated."
                + (
                    f" This organisation declares that criticals are escalated within "
                    f"{declared:.0f} minutes."
                    if declared
                    else ""
                )
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Critical alerts closed with no escalation record",
                    rationale=rationale,
                    innocent_explanation=(
                        "The organisation may escalate verbally, over a bridge call or "
                        "in a ticketing system that was not part of this submission. It "
                        "is also possible that a Tier-1 analyst is authorised to close "
                        "certain critical rules without escalation under an approved "
                        "playbook."
                    ),
                    metrics=metrics,
                    evidence_row_ids=[r2["case_id"] for r2 in ev],
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="no_escalation",
                )
            )
        return findings
