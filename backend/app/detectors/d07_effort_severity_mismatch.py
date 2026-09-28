"""D07 - investigation effort that does not increase with severity."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    fmt_minutes,
    median,
    severity_from_confidence,
)
from app.schema import Finding

MIN_PER_SEVERITY = 20
FLAT_RATIO = 1.35  # critical median should be well above medium median


class D07EffortSeverityMismatch(Detector):
    id = "D07"
    version = "1.1.0"
    name = "effort_severity_mismatch"
    gap_type = "execution_gap"
    capability_area = "investigation"
    min_sample = MIN_PER_SEVERITY
    description = (
        "Handling time that is flat or inverted across severity levels: a critical "
        "alert gets no more analyst time than a medium or low one."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT entity_id, severity,
                   median(handling_minutes) AS med,
                   COUNT(*)                 AS n
            FROM case_facts
            WHERE handling_minutes IS NOT NULL AND closure_type = 'manual'
              AND severity IS NOT NULL
            GROUP BY entity_id, severity
            """
        )
        per_entity: dict[str, dict[str, dict]] = {}
        for r in rows:
            per_entity.setdefault(r["entity_id"], {})[r["severity"]] = r

        ratios: dict[str, float] = {}
        for entity_id, sev in per_entity.items():
            crit, med = sev.get("critical"), sev.get("medium")
            if not crit or not med:
                continue
            if crit["n"] < MIN_PER_SEVERITY or med["n"] < MIN_PER_SEVERITY:
                continue
            if not med["med"]:
                continue
            ratios[entity_id] = crit["med"] / med["med"]

        findings: list[Finding] = []
        for entity_id, ratio in ratios.items():
            if ratio >= FLAT_RATIO:
                continue
            peers, _ = ctx.peers.peers(entity_id)
            peer_ratio = median([ratios[p] for p in peers if p in ratios])
            sev = per_entity[entity_id]
            ladder = {
                s: {
                    "median_minutes": round(sev[s]["med"], 2) if sev.get(s) else None,
                    "cases": int(sev[s]["n"]) if sev.get(s) else 0,
                }
                for s in ("critical", "high", "medium", "low", "info")
                if s in sev
            }
            inverted = ratio < 1.0
            total = sum(int(v["cases"]) for v in ladder.values())
            effect = min(1.0, max(0.0, (FLAT_RATIO - ratio) / FLAT_RATIO))
            conf = confidence_from(total, effect, MIN_PER_SEVERITY * 3)
            ev = ctx.q(
                """
                SELECT case_id FROM case_facts
                WHERE entity_id = ? AND severity = 'critical'
                  AND closure_type = 'manual' AND handling_minutes IS NOT NULL
                ORDER BY handling_minutes, case_id LIMIT 1000
                """,
                [entity_id],
            )
            rationale = (
                "Analyst time does not rise with severity here. Median manual handling "
                f"time is {fmt_minutes(sev['critical']['med'])} for critical alerts "
                f"versus {fmt_minutes(sev['medium']['med'])} for medium alerts - a ratio "
                f"of {ratio:.2f}"
                + (" (inverted: criticals get LESS time)." if inverted else " (essentially flat).")
                + f" Peers in the same group show a ratio of {peer_ratio:.2f}, i.e. "
                "criticals take several times longer, as you would expect."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title=(
                        "Critical alerts get less analyst time than routine ones"
                        if inverted
                        else "Investigation time does not increase with severity"
                    ),
                    rationale=rationale,
                    innocent_explanation=(
                        "A mature team can genuinely triage criticals faster because it "
                        "has better playbooks and automation for exactly those rules. "
                        "Severity may also be re-graded after the case is closed, or the "
                        "timestamps may measure queue time rather than analyst effort."
                    ),
                    metrics={
                        "critical_to_medium_ratio": round(ratio, 3),
                        "peer_median_ratio": round(peer_ratio, 3),
                        "inverted": inverted,
                        "median_minutes_by_severity": ladder,
                        "flat_ratio_threshold": FLAT_RATIO,
                    },
                    evidence_row_ids=[e["case_id"] for e in ev],
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="effort_mismatch",
                )
            )
        return findings
