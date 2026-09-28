"""Q01-Q05 - data-quality and submission-integrity checks.

These run with every analysis and also immediately after any upload, so a
supervisor sees straight away whether the submission can be trusted at all.
"""
from __future__ import annotations

import re

from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    pct,
    severity_from_confidence,
)
from app.schema import Finding

TRAILING_DIGITS = re.compile(r"(\d+)\s*$")


def _numeric_suffix(value: str) -> int | None:
    m = TRAILING_DIGITS.search(str(value))
    return int(m.group(1)) if m else None


class QualityDetector(Detector):
    gap_type = "data_quality"
    capability_area = "governance_oversight"


class Q01IdGaps(QualityDetector):
    id = "Q01"
    version = "1.1.0"
    name = "id_gaps"
    min_sample = 500
    description = (
        "Blocks of missing record IDs in an otherwise dense sequence, which suggests "
        "rows were removed from the extract."
    )
    #: a run of missing IDs must be at least this long to be reported
    MIN_RUN = 60
    #: and the rest of the ID space must be at least this dense, otherwise the
    #: submission is simply sparse and Q01 is not the right lens
    MIN_DENSITY = 0.97

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q("SELECT entity_id, alert_id FROM alerts ORDER BY entity_id, alert_id")
        per_entity: dict[str, list[int]] = {}
        for r in rows:
            n = _numeric_suffix(r["alert_id"])
            if n is not None:
                per_entity.setdefault(r["entity_id"], []).append(n)

        findings: list[Finding] = []
        for entity_id, ids in per_entity.items():
            if len(ids) < self.min_sample:
                continue
            ids = sorted(set(ids))
            span = ids[-1] - ids[0] + 1
            density = len(ids) / span
            longest, gap_start, gap_end = 0, None, None
            gaps: list[dict] = []
            for a, b in zip(ids, ids[1:]):
                run = b - a - 1
                if run <= 0:
                    continue
                if run >= 10:
                    gaps.append({"from_id": a + 1, "to_id": b - 1, "missing": run})
                if run > longest:
                    longest, gap_start, gap_end = run, a + 1, b - 1
            if longest < self.MIN_RUN or density < self.MIN_DENSITY:
                continue
            missing_total = span - len(ids)
            effect = min(1.0, longest / 400.0)
            conf = confidence_from(len(ids), effect, self.min_sample)
            rationale = (
                f"Alert IDs in this submission run from {ids[0]} to {ids[-1]} and are "
                f"{pct(density)} dense, so the numbering is clearly sequential - but "
                f"{missing_total:,} IDs are absent, including one unbroken block of "
                f"{longest:,} (IDs {gap_start} to {gap_end}). Either those records were "
                "removed before submission or the export failed part-way."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Block of alert IDs missing from the submission",
                    rationale=rationale,
                    innocent_explanation=(
                        "Many systems allocate IDs to more than one table, or reserve "
                        "ranges per collector, so gaps can be entirely normal. Records "
                        "deleted under a retention policy leave the same trace.",
                    )[0],
                    metrics={
                        "min_id": ids[0],
                        "max_id": ids[-1],
                        "rows_present": len(ids),
                        "ids_missing_total": missing_total,
                        "longest_missing_run": longest,
                        "longest_run_from": gap_start,
                        "longest_run_to": gap_end,
                        "density": round(density, 4),
                        "significant_gaps": gaps[:20],
                    },
                    evidence_row_ids=[f"{gap_start}-{gap_end}"],
                    evidence_table="alerts",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="id_gaps",
                )
            )
        return findings


class Q02TimeGaps(QualityDetector):
    id = "Q02"
    version = "1.1.0"
    name = "time_gaps"
    min_sample = 200
    description = "Calendar days inside the reporting period with no records at all."
    MIN_GAP_DAYS = 3

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT entity_id, date_trunc('day', created_at) AS d, COUNT(*) AS n
            FROM alerts GROUP BY 1, 2 ORDER BY 1, 2
            """
        )
        per_entity: dict[str, list] = {}
        for r in rows:
            per_entity.setdefault(r["entity_id"], []).append(r["d"])

        findings: list[Finding] = []
        for entity_id, days in per_entity.items():
            total = sum(1 for _ in days)
            if total < 20:
                continue
            gaps: list[dict] = []
            for a, b in zip(days, days[1:]):
                missing = (b - a).days - 1
                if missing >= self.MIN_GAP_DAYS:
                    gaps.append(
                        {
                            "from": str(a.date() if hasattr(a, "date") else a)[:10],
                            "to": str(b.date() if hasattr(b, "date") else b)[:10],
                            "missing_days": missing,
                        }
                    )
            if not gaps:
                continue
            worst = max(gaps, key=lambda g: g["missing_days"])
            missing_days = sum(g["missing_days"] for g in gaps)
            effect = min(1.0, missing_days / 14.0)
            conf = confidence_from(total * 10, effect, self.min_sample)
            rationale = (
                f"{missing_days} calendar days inside the reporting period contain no "
                f"alerts at all. The longest single gap is {worst['missing_days']} days, "
                f"between {worst['from']} and {worst['to']}. A live SOC does not go "
                "silent for days at a time, so part of the submission is missing."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Days with no records at all inside the period",
                    rationale=rationale,
                    innocent_explanation=(
                        "A planned maintenance window, a public-holiday shutdown of a "
                        "plant, or a collector outage the organisation already knows "
                        "about would all produce this. It may also be an export that ran "
                        "in parts."
                    ),
                    metrics={
                        "days_with_data": total,
                        "missing_days_total": missing_days,
                        "gaps": gaps[:20],
                        "longest_gap_days": worst["missing_days"],
                        "min_gap_days_reported": self.MIN_GAP_DAYS,
                    },
                    evidence_row_ids=[f"{g['from']}..{g['to']}" for g in gaps[:20]],
                    evidence_table="alerts",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="time_gaps",
                )
            )
        return findings


class Q03DeclaredCountMismatch(QualityDetector):
    id = "Q03"
    version = "1.1.0"
    name = "declared_count_mismatch"
    min_sample = 1
    description = (
        "The alert count declared in the submission header does not match the number "
        "of alert rows actually supplied."
    )
    TOLERANCE = 0.02

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT s.entity_id, s.submission_id, s.declared_alert_count AS declared,
                   COUNT(a.alert_id) AS actual,
                   s.period_start, s.period_end
            FROM submissions s
            LEFT JOIN alerts a
                   ON a.entity_id = s.entity_id
                  AND a.created_at >= s.period_start
                  AND a.created_at <  s.period_end
            GROUP BY 1, 2, 3, 5, 6
            ORDER BY 1, 2
            """
        )
        by_entity: dict[str, list[dict]] = {}
        for r in rows:
            declared = int(r["declared"] or 0)
            actual = int(r["actual"] or 0)
            if declared <= 0:
                continue
            if abs(declared - actual) <= max(5, self.TOLERANCE * declared):
                continue
            by_entity.setdefault(r["entity_id"], []).append(
                {
                    "submission_id": r["submission_id"],
                    "declared": declared,
                    "actual": actual,
                    "difference": declared - actual,
                    "period": f"{str(r['period_start'])[:10]} to {str(r['period_end'])[:10]}",
                }
            )

        findings: list[Finding] = []
        for entity_id, bad in by_entity.items():
            declared = sum(b["declared"] for b in bad)
            actual = sum(b["actual"] for b in bad)
            diff_share = abs(declared - actual) / max(declared, 1)
            effect = min(1.0, diff_share / 0.3)
            conf = confidence_from(len(bad) * 50, effect, 50)
            rationale = (
                f"{len(bad)} of this organisation's submissions declare a different "
                f"number of alerts than they contain. Across those periods the header "
                f"declares {declared:,} alerts but only {actual:,} rows were supplied - "
                f"a difference of {declared - actual:+,} ({pct(diff_share)}). Until that "
                "is reconciled, every rate computed for this organisation is uncertain."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Declared alert count does not match the rows supplied",
                    rationale=rationale,
                    innocent_explanation=(
                        "The declared figure may count alerts the organisation chose not "
                        "to export (for example suppressed or duplicate alerts), or it "
                        "may have been taken from a dashboard on a different date. Time "
                        "zone handling at period boundaries also shifts counts."
                    ),
                    metrics={
                        "submissions_mismatched": len(bad),
                        "declared_total": declared,
                        "actual_total": actual,
                        "difference": declared - actual,
                        "difference_share": round(diff_share, 4),
                        "tolerance": self.TOLERANCE,
                        "details": bad,
                    },
                    evidence_row_ids=[b["submission_id"] for b in bad],
                    evidence_table="submissions",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="declared_mismatch",
                )
            )
        return findings


class Q04TimestampRegularity(QualityDetector):
    id = "Q04"
    version = "1.1.0"
    name = "timestamp_regularity"
    min_sample = 500
    description = (
        "Timestamps that are suspiciously round - for example every alert landing "
        "exactly on the hour - which indicates re-created rather than captured data."
    )
    SHARE_THRESHOLD = 0.15

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT entity_id,
                   COUNT(*) AS n,
                   SUM(CASE WHEN extract('minute' FROM created_at) = 0
                             AND extract('second' FROM created_at) = 0
                            THEN 1 ELSE 0 END) AS on_the_hour,
                   SUM(CASE WHEN extract('second' FROM created_at) = 0
                            THEN 1 ELSE 0 END) AS zero_seconds
            FROM alerts GROUP BY entity_id
            """
        )
        findings: list[Finding] = []
        for r in rows:
            n = int(r["n"] or 0)
            if n < self.min_sample:
                continue
            hourly = int(r["on_the_hour"] or 0)
            share = hourly / n
            if share < self.SHARE_THRESHOLD:
                continue
            expected = n / 3600.0
            ev = ctx.q(
                """
                SELECT alert_id FROM alerts
                WHERE entity_id = ? AND extract('minute' FROM created_at) = 0
                  AND extract('second' FROM created_at) = 0
                ORDER BY created_at, alert_id LIMIT 2000
                """,
                [r["entity_id"]],
            )
            effect = min(1.0, share / 0.5)
            conf = confidence_from(n, effect, self.min_sample)
            rationale = (
                f"{hourly:,} of {n:,} alert timestamps ({pct(share)}) fall exactly on the "
                f"hour with zero minutes and zero seconds. In captured telemetry you "
                f"would expect around {expected:.0f} such rows. Timestamps have been "
                "rounded, re-created or generated rather than recorded."
            )
            findings.append(
                self.finding(
                    ctx,
                    r["entity_id"],
                    title="Timestamps look generated rather than captured",
                    rationale=rationale,
                    innocent_explanation=(
                        "Some log pipelines bucket events into hourly windows, and a "
                        "batch importer may stamp everything with the batch time. That "
                        "would make the data less precise without anyone falsifying it."
                    ),
                    metrics={
                        "alerts": n,
                        "on_the_hour": hourly,
                        "share_on_the_hour": round(share, 4),
                        "expected_if_random": round(expected, 1),
                        "zero_second_rows": int(r["zero_seconds"] or 0),
                        "share_threshold": self.SHARE_THRESHOLD,
                    },
                    evidence_row_ids=[e["alert_id"] for e in ev],
                    evidence_table="alerts",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="timestamp_regularity",
                )
            )
        return findings


class Q05FileHashRecorded(QualityDetector):
    id = "Q05"
    version = "1.1.0"
    name = "file_hash_recorded"
    min_sample = 1
    description = (
        "Submissions with no recorded file hash, so the data cannot later be proven to "
        "be the data that was assessed."
    )

    def run(self, ctx: RunContext) -> list[Finding]:
        rows = ctx.q(
            """
            SELECT entity_id, COUNT(*) AS n,
                   SUM(CASE WHEN file_hash IS NULL OR length(trim(file_hash)) < 32
                            THEN 1 ELSE 0 END) AS missing
            FROM submissions GROUP BY entity_id
            """
        )
        findings: list[Finding] = []
        for r in rows:
            missing = int(r["missing"] or 0)
            n = int(r["n"] or 0)
            if missing == 0 or n == 0:
                continue
            ev = ctx.q(
                """
                SELECT submission_id FROM submissions
                WHERE entity_id = ?
                  AND (file_hash IS NULL OR length(trim(file_hash)) < 32)
                ORDER BY submission_id
                """,
                [r["entity_id"]],
            )
            share = missing / n
            effect = min(1.0, share)
            conf = confidence_from(n * 30, effect, 30)
            rationale = (
                f"{missing} of {n} submissions from this organisation carry no usable "
                "file hash. Without one, nobody can later prove which file was assessed, "
                "so the audit trail for this assessment is incomplete."
            )
            findings.append(
                self.finding(
                    ctx,
                    r["entity_id"],
                    title="Submission has no recorded file hash",
                    rationale=rationale,
                    innocent_explanation=(
                        "Hashes may have been recorded outside this system, or the data "
                        "may have been supplied through a channel (a live API, a shared "
                        "database view) where a file hash does not apply."
                    ),
                    metrics={
                        "submissions": n,
                        "submissions_without_hash": missing,
                        "share_without_hash": round(share, 4),
                    },
                    evidence_row_ids=[e["submission_id"] for e in ev],
                    evidence_table="submissions",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="file_hash",
                )
            )
        return findings
