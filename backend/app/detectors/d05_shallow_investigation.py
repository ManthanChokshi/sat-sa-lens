"""D05 - investigation notes that cite no concrete artefact."""
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

# Artefact patterns. Pseudonymised identifiers keep their shape on ingest
# (ip-xxxxxxxx / usr-xxxxxxxx) precisely so this check still works.
ARTEFACT_PATTERNS: list[tuple[str, str]] = [
    ("ip_address", r"(ip-[0-9a-f]{6,}|\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b)"),
    ("username", r"(usr-[0-9a-f]{6,}|\buser(name)?\s*[:=]\s*\S+)"),
    ("file_hash", r"\b[0-9a-f]{16,}\b"),
    ("hostname", r"\b[A-Z]{2,5}-[A-Z]{2,4}-[0-9]{3,6}\b"),
    (
        "action_taken",
        r"(?i)\b(blocked|isolat(ed|ion)|quarantin(ed|e)|reset|revoked|escalat(ed|ion)"
        r"|disabled|killed|re-?imaged|patched|contained|block list|blocklist|tuned"
        r"|suppressed|sinkholed|remediated)\b",
    ),
]

ARTEFACT_SQL = " OR ".join(
    f"regexp_matches(notes, '{pattern}')" for _, pattern in ARTEFACT_PATTERNS
)

MIN_NOTES = 50
MIN_SHARE = 0.40
PEER_MULTIPLE = 2.5


class D05ShallowInvestigation(Detector):
    id = "D05"
    version = "1.1.0"
    name = "shallow_investigation"
    gap_type = "execution_gap"
    capability_area = "investigation"
    min_sample = MIN_NOTES
    description = (
        "Notes that record no artefact at all - no address, host, account, hash or "
        "action taken - so the closure cannot be checked by anyone later."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            f"""
            SELECT entity_id,
                   COUNT(*) AS n,
                   SUM(CASE WHEN {ARTEFACT_SQL} THEN 0 ELSE 1 END) AS no_artefact
            FROM case_facts
            WHERE closure_type = 'manual' AND notes IS NOT NULL
            GROUP BY entity_id
            """
        )
        stats = {r["entity_id"]: r for r in rows}
        shares = {
            e: (r["no_artefact"] or 0) / r["n"] for e, r in stats.items() if r["n"]
        }
        findings: list[Finding] = []
        for entity_id, r in stats.items():
            n = int(r["n"] or 0)
            bad = int(r["no_artefact"] or 0)
            if n < MIN_NOTES:
                continue
            share = bad / n
            peers, _ = ctx.peers.peers(entity_id)
            peer_share = median([shares[p] for p in peers if p in shares])
            lower = wilson_lower_bound(bad, n)
            if lower < MIN_SHARE or share < max(MIN_SHARE, peer_share * PEER_MULTIPLE):
                continue
            ev = ctx.q(
                f"""
                SELECT case_id, notes FROM case_facts
                WHERE entity_id = ? AND closure_type = 'manual' AND notes IS NOT NULL
                  AND NOT ({ARTEFACT_SQL})
                ORDER BY case_id LIMIT 2000
                """,
                [entity_id],
            )
            effect = min(1.0, share / 0.7)
            conf = confidence_from(n, effect, MIN_NOTES)
            samples = [e["notes"][:120] for e in ev[:3]]
            rationale = (
                f"{pct(share)} of manually closed cases ({bad:,} of {n:,}) have a note "
                f"with no checkable artefact in it - no address, host, account, file "
                f"hash or action taken. Peers sit at {pct(peer_share)}. Examples: "
                + "; ".join(f'"{s}"' for s in samples)
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Investigation notes contain no evidence of investigation",
                    rationale=rationale,
                    innocent_explanation=(
                        "The artefacts may live in a separate forensic tool or in "
                        "attachments that were not part of this submission, and some "
                        "teams deliberately keep free-text notes short. The note field "
                        "may also have been truncated during export."
                    ),
                    metrics={
                        "manual_notes": n,
                        "notes_without_artefact": bad,
                        "share_without_artefact": round(share, 4),
                        "wilson_lower_bound": round(lower, 4),
                        "peer_median_share": round(peer_share, 4),
                        "artefact_types_searched": [k for k, _ in ARTEFACT_PATTERNS],
                    },
                    evidence_row_ids=[e["case_id"] for e in ev],
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="shallow_notes",
                )
            )
        return findings
