"""D11 - alert categories every peer reports, but this organisation never does."""
from __future__ import annotations

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    severity_from_confidence,
)
from app.schema import Finding

PEER_PRESENCE_THRESHOLD = 0.80  # present for >= 80% of peers
PEER_MIN_ALERTS_FOR_PRESENT = 5
MIN_ENTITY_ALERTS = 300


class D11MissingAlertCategories(Detector):
    id = "D11"
    version = "1.1.0"
    name = "missing_alert_categories"
    gap_type = "negative_space"
    capability_area = "threat_detection"
    min_sample = MIN_ENTITY_ALERTS
    description = (
        "Attack categories that essentially every peer organisation detects, but which "
        "are completely absent from this organisation's submission."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            "SELECT entity_id, category, COUNT(*) AS n FROM alerts "
            "GROUP BY entity_id, category"
        )
        by_entity: dict[str, dict[str, int]] = {}
        for r in rows:
            by_entity.setdefault(r["entity_id"], {})[r["category"]] = int(r["n"])
        totals = {e: sum(v.values()) for e, v in by_entity.items()}

        findings: list[Finding] = []
        for entity_id in ctx.entity_ids:
            mine = by_entity.get(entity_id, {})
            total = totals.get(entity_id, 0)
            if total < MIN_ENTITY_ALERTS:
                continue
            peers, _peer_level = ctx.peers.peers(entity_id)
            peers = [p for p in peers if totals.get(p, 0) >= MIN_ENTITY_ALERTS]
            if len(peers) < 2:
                continue

            missing: list[dict] = []
            for category in sorted(
                {c for p in peers for c in by_entity.get(p, {})}
            ):
                present_for = [
                    p
                    for p in peers
                    if by_entity.get(p, {}).get(category, 0) >= PEER_MIN_ALERTS_FOR_PRESENT
                ]
                presence = len(present_for) / len(peers)
                if presence < PEER_PRESENCE_THRESHOLD:
                    continue
                if mine.get(category, 0) > 0:
                    continue
                peer_rates = [
                    by_entity.get(p, {}).get(category, 0) / max(totals.get(p, 1), 1)
                    for p in peers
                ]
                expected = sorted(peer_rates)[len(peer_rates) // 2] * total
                missing.append(
                    {
                        "category": category,
                        "peers_reporting": f"{len(present_for)}/{len(peers)}",
                        "expected_alerts_if_typical": int(round(expected)),
                    }
                )
            if not missing:
                continue

            expected_total = sum(m["expected_alerts_if_typical"] for m in missing)
            effect = min(1.0, expected_total / max(total * 0.05, 30))
            conf = confidence_from(total, effect, MIN_ENTITY_ALERTS)
            cat_txt = ", ".join(m["category"].replace("_", " ") for m in missing)
            rationale = (
                f"This organisation reported {total:,} alerts but not a single one in "
                f"these categories: {cat_txt}. Every comparable peer reports them. On "
                f"peer rates, a submission of this size would be expected to contain "
                f"roughly {expected_total:,} such alerts. The gap is in the detection "
                "coverage, not in the volume."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Whole attack categories missing from the submission",
                    rationale=rationale,
                    innocent_explanation=(
                        "The organisation may genuinely not run the technology that "
                        "produces these detections (for example no corporate email, so "
                        "no phishing alerts), or those alerts may be handled by a "
                        "separate team or tool whose output was not submitted. Category "
                        "labelling conventions may also differ."
                    ),
                    metrics={
                        "entity_alert_total": total,
                        "missing_categories": missing,
                        "expected_alerts_if_typical_total": expected_total,
                        "peer_presence_threshold": PEER_PRESENCE_THRESHOLD,
                        "peers_used": len(peers),
                    },
                    evidence_row_ids=[m["category"] for m in missing],
                    evidence_table="alerts_categories",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="missing_categories",
                )
            )
        return findings
