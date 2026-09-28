"""D01 - critical/high alerts closed far too quickly to have been investigated."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    fmt_minutes,
    median,
    pct,
    severity_from_confidence,
    wilson_lower_bound,
)
from app.schema import Finding

FAST_MINUTES = 2.0
MIN_SHARE = 0.12
PEER_MULTIPLE = 3.0


class D01FastCriticalClosure(Detector):
    id = "D01"
    version = "1.2.0"
    name = "fast_critical_closure"
    gap_type = "execution_gap"
    capability_area = "investigation"
    min_sample = 30
    description = (
        "Critical and high alerts that were closed by a human faster than any real "
        "investigation could take, or far faster than the peer group's median."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT entity_id,
                   COUNT(*)                                            AS manual_n,
                   SUM(CASE WHEN handling_minutes <= ? THEN 1 ELSE 0 END) AS fast_n,
                   median(handling_minutes)                            AS median_minutes
            FROM case_facts
            WHERE severity IN ('critical', 'high')
              AND closure_type = 'manual'
              AND closed_at IS NOT NULL
            GROUP BY entity_id
            """,
            [FAST_MINUTES],
        )
        auto = {
            r["entity_id"]: r
            for r in ctx.q(
                """
                SELECT entity_id,
                       COUNT(*) AS auto_n,
                       SUM(CASE WHEN handling_minutes <= ? THEN 1 ELSE 0 END) AS auto_fast_n
                FROM case_facts
                WHERE closure_type = 'automated' AND closed_at IS NOT NULL
                GROUP BY entity_id
                """,
                [FAST_MINUTES],
            )
        }
        stats = {r["entity_id"]: r for r in rows}
        shares = {
            e: (r["fast_n"] or 0) / r["manual_n"]
            for e, r in stats.items()
            if (r["manual_n"] or 0) > 0
        }

        findings: list[Finding] = []
        for entity_id, r in stats.items():
            n = int(r["manual_n"] or 0)
            fast = int(r["fast_n"] or 0)
            if n < self.min_sample:
                continue
            share = fast / n
            peers, _ = ctx.peers.peers(entity_id)
            peer_shares = [shares[p] for p in peers if p in shares]
            peer_share = median(peer_shares)
            lower = wilson_lower_bound(fast, n)
            threshold = max(MIN_SHARE, peer_share * PEER_MULTIPLE)
            if lower < MIN_SHARE or share < threshold:
                continue

            ev = ctx.q(
                """
                SELECT case_id FROM case_facts
                WHERE entity_id = ? AND severity IN ('critical', 'high')
                  AND closure_type = 'manual' AND closed_at IS NOT NULL
                  AND handling_minutes <= ?
                ORDER BY handling_minutes, case_id
                LIMIT 2000
                """,
                [entity_id, FAST_MINUTES],
            )
            a = auto.get(entity_id, {})
            effect = min(1.0, share / 0.45)
            conf = confidence_from(n, effect, self.min_sample)
            metrics = {
                "manual_critical_high_cases": n,
                "closed_under_2_min": fast,
                "share_closed_under_2_min": round(share, 4),
                "wilson_lower_bound": round(lower, 4),
                "peer_median_share": round(peer_share, 4),
                "entity_median_handling_minutes": round(r["median_minutes"] or 0, 2),
                "automated_closures_total": int(a.get("auto_n") or 0),
                "automated_closures_under_2_min": int(a.get("auto_fast_n") or 0),
                "fast_threshold_minutes": FAST_MINUTES,
            }
            rationale = (
                f"{pct(share)} of this organisation's critical and high alerts "
                f"({fast} of {n}) were closed **by a person** in under two minutes. "
                f"The peer median for the same measure is {pct(peer_share)}. "
                f"Its median handling time for these alerts is "
                f"{fmt_minutes(r['median_minutes'])}. Automated closures are excluded "
                f"from this count: {int(a.get('auto_n') or 0)} automated closures were "
                "reported separately."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Critical alerts closed too fast to have been investigated",
                    rationale=rationale,
                    innocent_explanation=(
                        "Some of these closures may be genuine duplicates of an alert "
                        "already being worked, or the result of a tuned suppression rule "
                        "that the team applies manually. Closures recorded as automated "
                        "are already excluded here; if this team closes automation "
                        "output by hand, the closure_type field may simply be wrong."
                    ),
                    metrics=metrics,
                    evidence_row_ids=[r2["case_id"] for r2 in ev],
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="fast_closure",
                )
            )
        return findings
