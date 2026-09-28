"""D09 - per-analyst closure counts that no human could achieve."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    median,
    severity_from_confidence,
)
from app.schema import Finding

#: A 12-hour shift at 3 minutes of genuine work per case is ~240 cases; anything
#: above this is treated as implausible before peer comparison even starts.
IMPLAUSIBLE_PER_DAY = 110
PEER_MULTIPLE = 4.0


class D09AnalystWorkloadImplausible(Detector):
    id = "D09"
    version = "1.1.0"
    name = "analyst_workload_implausible"
    gap_type = "execution_gap"
    capability_area = "security_operations"
    min_sample = 30
    description = (
        "A single analyst closing more cases in one day than a person could "
        "realistically review, which usually means bulk closure under one account."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT entity_id, analyst_pseudo, date_trunc('day', closed_at) AS day,
                   COUNT(*) AS closures,
                   median(handling_minutes) AS med_minutes
            FROM case_facts
            WHERE closed_at IS NOT NULL AND closure_type = 'manual'
            GROUP BY entity_id, analyst_pseudo, date_trunc('day', closed_at)
            """
        )
        per_entity: dict[str, list[dict]] = {}
        for r in rows:
            per_entity.setdefault(r["entity_id"], []).append(r)
        typical = {
            e: median([float(r["closures"]) for r in rs]) for e, rs in per_entity.items()
        }

        findings: list[Finding] = []
        for entity_id, rs in per_entity.items():
            if len(rs) < self.min_sample:
                continue
            peers, _ = ctx.peers.peers(entity_id)
            peer_typical = median([typical[p] for p in peers if p in typical]) or 1.0
            bar = max(IMPLAUSIBLE_PER_DAY, peer_typical * PEER_MULTIPLE)
            offenders = [r for r in rs if float(r["closures"]) > bar]
            if not offenders:
                continue
            # Stable tie-break so repeated runs emit identical evidence.
            offenders.sort(key=lambda r: (-float(r["closures"]), r["analyst_pseudo"], str(r["day"])))
            worst = offenders[0]
            analysts = sorted({r["analyst_pseudo"] for r in offenders})
            ids: list[str] = []
            for r in offenders[:25]:
                ev = ctx.q(
                    """
                    SELECT case_id FROM case_facts
                    WHERE entity_id = ? AND analyst_pseudo = ?
                      AND date_trunc('day', closed_at) = ?
                    ORDER BY case_id LIMIT 200
                    """,
                    [entity_id, r["analyst_pseudo"], r["day"]],
                )
                ids.extend(e["case_id"] for e in ev)
            effect = min(1.0, float(worst["closures"]) / (bar * 3))
            conf = confidence_from(len(offenders) * 10, effect, 30)
            rationale = (
                f"On {len(offenders)} analyst-days a single account closed more than "
                f"{bar:.0f} cases. The worst is {worst['analyst_pseudo']} with "
                f"{int(worst['closures'])} manual closures on "
                f"{str(worst['day'])[:10]} - about "
                f"{int(worst['closures']) / 8:.0f} per hour across an eight-hour shift, "
                f"with a median recorded handling time of "
                f"{float(worst['med_minutes'] or 0):.0f} minutes each. The typical "
                f"analyst-day in the peer group is {peer_typical:.0f} closures."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="One analyst closing an implausible number of cases per day",
                    rationale=rationale,
                    innocent_explanation=(
                        "A shared or service account used by a whole shift, or a bulk "
                        "close-out after a tuning change, would look exactly like this. "
                        "Automation running under a human account is another common and "
                        "innocent cause."
                    ),
                    metrics={
                        "analyst_days_over_threshold": len(offenders),
                        "threshold_used": round(bar, 1),
                        "peer_typical_closures_per_day": round(peer_typical, 1),
                        "worst_analyst": worst["analyst_pseudo"],
                        "worst_day": str(worst["day"])[:10],
                        "worst_closures": int(worst["closures"]),
                        "distinct_analysts_involved": len(analysts),
                        "implausible_floor": IMPLAUSIBLE_PER_DAY,
                    },
                    evidence_row_ids=ids,
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="workload",
                )
            )
        return findings
