"""D13 - broken evidence chains between alerts, cases and escalations."""
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

MIN_ORPHANS = 10
MIN_TP_SHARE = 0.35
PEER_MULTIPLE = 2.5
MIN_TP_CASES = 25


class D13BrokenChain(Detector):
    id = "D13"
    version = "1.1.0"
    name = "broken_chain"
    gap_type = "negative_space"
    capability_area = "incident_response"
    min_sample = MIN_ORPHANS
    description = (
        "Records that should link and do not: cases with no parent alert, escalations "
        "whose case is missing, and confirmed true positives that were never escalated."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        orphan_cases = {
            r["entity_id"]: r
            for r in ctx.q(
                """
                SELECT c.entity_id, COUNT(*) AS n
                FROM cases c LEFT JOIN alerts a ON a.alert_id = c.alert_id
                WHERE c.alert_id IS NULL OR a.alert_id IS NULL
                GROUP BY c.entity_id
                """
            )
        }
        ghost_escalations = {
            r["entity_id"]: r
            for r in ctx.q(
                """
                SELECT e.entity_id, COUNT(*) AS n
                FROM escalations e LEFT JOIN cases c ON c.case_id = e.case_id
                WHERE c.case_id IS NULL
                GROUP BY e.entity_id
                """
            )
        }
        tp_rows = {
            r["entity_id"]: r
            for r in ctx.q(
                """
                SELECT entity_id,
                       COUNT(*) AS tp_n,
                       SUM(CASE WHEN escalation_id IS NULL THEN 1 ELSE 0 END) AS tp_no_esc
                FROM case_facts
                WHERE disposition = 'true_positive' AND severity IN ('critical', 'high')
                GROUP BY entity_id
                """
            )
        }
        tp_shares = {
            e: (r["tp_no_esc"] or 0) / r["tp_n"]
            for e, r in tp_rows.items()
            if (r["tp_n"] or 0) >= MIN_TP_CASES
        }

        findings: list[Finding] = []
        for entity_id in ctx.entity_ids:
            orphans = int((orphan_cases.get(entity_id) or {}).get("n") or 0)
            ghosts = int((ghost_escalations.get(entity_id) or {}).get("n") or 0)
            tp = tp_rows.get(entity_id) or {}
            tp_n = int(tp.get("tp_n") or 0)
            tp_bad = int(tp.get("tp_no_esc") or 0)
            tp_share = tp_shares.get(entity_id)
            peers, _ = ctx.peers.peers(entity_id)
            peer_tp_share = median([tp_shares[p] for p in peers if p in tp_shares])

            structural = orphans + ghosts >= MIN_ORPHANS
            behavioural = (
                tp_share is not None
                and tp_share >= max(MIN_TP_SHARE, peer_tp_share * PEER_MULTIPLE)
            )
            if not structural and not behavioural:
                continue

            ev: list[str] = []
            table = "cases"
            if orphans:
                ev.extend(
                    r["case_id"]
                    for r in ctx.q(
                        """
                        SELECT c.case_id FROM cases c
                        LEFT JOIN alerts a ON a.alert_id = c.alert_id
                        WHERE c.entity_id = ? AND (c.alert_id IS NULL OR a.alert_id IS NULL)
                        ORDER BY c.case_id LIMIT 800
                        """,
                        [entity_id],
                    )
                )
            if behavioural:
                ev.extend(
                    r["case_id"]
                    for r in ctx.q(
                        """
                        SELECT case_id FROM case_facts
                        WHERE entity_id = ? AND disposition = 'true_positive'
                          AND severity IN ('critical', 'high') AND escalation_id IS NULL
                        ORDER BY case_id LIMIT 800
                        """,
                        [entity_id],
                    )
                )
            parts = []
            if orphans:
                parts.append(f"{orphans:,} cases have no parent alert in the data")
            if ghosts:
                parts.append(f"{ghosts:,} escalations point at a case that is not present")
            if behavioural:
                parts.append(
                    f"{tp_bad:,} of {tp_n:,} confirmed true positives on critical or high "
                    f"alerts ({pct(tp_share or 0)}) have no escalation at all, against a "
                    f"peer figure of {pct(peer_tp_share)}"
                )
            effect = min(
                1.0,
                0.5 * min(1.0, (orphans + ghosts) / 60)
                + 0.5 * min(1.0, (tp_share or 0) / 0.6),
            )
            conf = confidence_from(max(orphans + ghosts, tp_n), effect, MIN_ORPHANS)
            rationale = (
                "The evidence chain does not hold together: "
                + "; ".join(parts)
                + ". A supervisor cannot reconstruct what happened from records that do "
                "not join up."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Broken links between alerts, cases and escalations",
                    rationale=rationale,
                    innocent_explanation=(
                        "Export boundaries explain a lot of this: a case opened just "
                        "before the reporting window will reference an alert outside it. "
                        "Manually raised cases legitimately have no alert, and some teams "
                        "record escalation only in a bridge-call log."
                    ),
                    metrics={
                        "orphan_cases_without_alert": orphans,
                        "escalations_without_case": ghosts,
                        "true_positive_cases": tp_n,
                        "true_positives_without_escalation": tp_bad,
                        "share_true_positives_unescalated": (
                            round(tp_share, 4) if tp_share is not None else None
                        ),
                        "peer_median_share_unescalated": round(peer_tp_share, 4),
                        "structural_signal": structural,
                        "behavioural_signal": behavioural,
                    },
                    evidence_row_ids=ev,
                    evidence_table=table,
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="broken_chain",
                )
            )
        return findings
