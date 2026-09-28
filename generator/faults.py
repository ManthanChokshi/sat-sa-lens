"""Planted-problem injectors.

Every injector mutates one entity's data in place and returns the ground-truth
records it created. One injector per detector ID where it makes sense, plus the
data-quality checks Q01-Q04.

Contract for each injector:
    fn(ctx: EntityData) -> list[dict]
and each returned dict is a ground-truth problem:
    {problem_id, entity_id, expected_detector_id, description,
     evidence_ids, evidence_table, selector}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable

import numpy as np
import pandas as pd

from generator.content import SHALLOW_NOTES, TEMPLATE_NOTES

EVIDENCE_CAP = 600


@dataclass
class EntityData:
    """Mutable bundle of one entity's generated tables."""

    entity_id: str
    profile: object
    rng: np.random.Generator
    period_start: object
    period_end: object
    assets: pd.DataFrame
    alerts: pd.DataFrame
    cases: pd.DataFrame
    escalations: pd.DataFrame
    commitments: pd.DataFrame
    submissions: pd.DataFrame
    analysts: list[str] = field(default_factory=list)
    next_alert_seq: int = 0

    # ---------------------------------------------------------------- helpers
    def problem(
        self,
        code: str,
        detector_id: str,
        description: str,
        evidence_ids: list[str],
        evidence_table: str,
        selector: str = "",
        also: tuple[str, ...] = (),
    ) -> dict:
        ids = [str(i) for i in evidence_ids][:EVIDENCE_CAP]
        return {
            "problem_id": f"{self.entity_id}-{code}",
            "entity_id": self.entity_id,
            "expected_detector_id": detector_id,
            "fault_code": code,
            "description": description,
            "evidence_table": evidence_table,
            "evidence_ids": ids,
            "evidence_count": len(evidence_ids),
            "selector": selector,
            # Other detectors that this same planted defect legitimately trips.
            # Validation must not score those as false positives.
            "acceptable_detector_ids": list(also),
        }

    def prune_alerts(self, drop_alert_ids: set[str]) -> tuple[set[str], set[str]]:
        """Remove alerts and cascade to their cases and escalations."""
        if not drop_alert_ids:
            return set(), set()
        self.alerts = self.alerts[~self.alerts["alert_id"].isin(drop_alert_ids)]
        dead_cases = set(
            self.cases.loc[self.cases["alert_id"].isin(drop_alert_ids), "case_id"]
        )
        self.cases = self.cases[~self.cases["case_id"].isin(dead_cases)]
        self.escalations = self.escalations[
            ~self.escalations["case_id"].isin(dead_cases)
        ]
        return drop_alert_ids, dead_cases

    def case_severity(self) -> pd.Series:
        """Severity of each case, joined through its alert."""
        sev = self.alerts.set_index("alert_id")["severity"]
        return self.cases["alert_id"].map(sev)

    def new_alert_ids(self, n: int) -> list[str]:
        start = self.next_alert_seq
        self.next_alert_seq += n
        return [f"{self.entity_id}-A{start + i:07d}" for i in range(n)]


def _set_duration(ctx: EntityData, mask: pd.Series, minutes: np.ndarray) -> None:
    idx = ctx.cases.index[mask]
    if len(idx) == 0:
        return
    opened = ctx.cases.loc[idx, "opened_at"]
    ctx.cases.loc[idx, "closed_at"] = opened + pd.to_timedelta(minutes, unit="m")


# --------------------------------------------------------------------- D01
def inject_d01_fast_critical_closure(ctx: EntityData) -> list[dict]:
    sev = ctx.case_severity()
    mask = (
        sev.isin(["critical", "high"])
        & (ctx.cases["closure_type"] == "manual")
        & ctx.cases["closed_at"].notna()
    )
    candidates = ctx.cases.index[mask]
    if len(candidates) == 0:
        return []
    take = ctx.rng.permutation(len(candidates))[: int(len(candidates) * 0.78)]
    chosen = candidates[np.sort(take)]
    seconds = ctx.rng.integers(4, 115, size=len(chosen))
    ctx.cases.loc[chosen, "closed_at"] = ctx.cases.loc[
        chosen, "opened_at"
    ] + pd.to_timedelta(seconds, unit="s")
    # A rushed closure is almost never recorded as a true positive.
    ctx.cases.loc[chosen, "disposition"] = "false_positive"
    ids = list(ctx.cases.loc[chosen, "case_id"])
    return [
        ctx.problem(
            "D01",
            "D01",
            f"{len(ids)} critical/high alerts closed manually in under 2 minutes.",
            ids,
            "cases",
            "severity in (critical,high) and closure_type=manual",
            also=("D07",),
        )
    ]


# --------------------------------------------------------------------- D02
def inject_d02_critical_no_escalation(ctx: EntityData) -> list[dict]:
    sev = ctx.case_severity()
    crit_cases = set(ctx.cases.loc[sev == "critical", "case_id"])
    if not crit_cases:
        return []
    keep_frac = 0.05
    have = ctx.escalations["case_id"].isin(crit_cases)
    esc_idx = ctx.escalations.index[have]
    keep_n = int(len(esc_idx) * keep_frac)
    keep = set(ctx.escalations.loc[esc_idx, "case_id"].iloc[:keep_n])
    ctx.escalations = ctx.escalations[
        ~(ctx.escalations["case_id"].isin(crit_cases - keep))
    ]
    remaining = set(ctx.escalations["case_id"])
    ids = sorted(crit_cases - remaining)
    return [
        ctx.problem(
            "D02",
            "D02",
            f"{len(ids)} critical alerts were closed with no escalation record at all.",
            ids,
            "cases",
            "severity=critical and no matching escalation",
            also=("D13",),
        )
    ]


# --------------------------------------------------------------------- D03
def inject_d03_commitment_breach(ctx: EntityData) -> list[dict]:
    """Declared 15-minute critical escalation, real median around 3 hours."""
    sev = ctx.case_severity()
    crit = set(ctx.cases.loc[sev == "critical", "case_id"])
    opened = ctx.cases.set_index("case_id")["opened_at"]
    mask = ctx.escalations["case_id"].isin(crit)
    idx = ctx.escalations.index[mask]
    if len(idx) == 0:
        return []
    mins = ctx.rng.integers(150, 320, size=len(idx))
    base = ctx.escalations.loc[idx, "case_id"].map(opened)
    ctx.escalations.loc[idx, "escalated_at"] = base + pd.to_timedelta(mins, unit="m")
    ids = list(ctx.escalations.loc[idx, "escalation_id"])
    return [
        ctx.problem(
            "D03",
            "D03",
            "Declared commitment: escalate criticals within 15 minutes. "
            "Actual median escalation delay is roughly 3.9 hours.",
            ids,
            "escalations",
            "commitment critical_escalation_minutes",
        )
    ]


# --------------------------------------------------------------------- D04
def inject_d04_template_notes(ctx: EntityData) -> list[dict]:
    mask = (ctx.cases["closure_type"] == "manual") & ctx.cases["notes"].notna()
    idx = ctx.cases.index[mask]
    if len(idx) == 0:
        return []
    take = idx[ctx.rng.random(len(idx)) < 0.88]
    picks = ctx.rng.integers(0, len(TEMPLATE_NOTES), size=len(take))
    ctx.cases.loc[take, "notes"] = [TEMPLATE_NOTES[i] for i in picks]
    ids = list(ctx.cases.loc[take, "case_id"])
    return [
        ctx.problem(
            "D04",
            "D04",
            f"{len(ids)} investigation notes are copy-paste variants of five short "
            "phrases such as 'checked, false positive'.",
            ids,
            "cases",
            "near-duplicate notes",
            also=("D05",),
        )
    ]


# --------------------------------------------------------------------- D05
def inject_d05_shallow_investigation(ctx: EntityData) -> list[dict]:
    mask = ctx.cases["closure_type"] == "manual"
    idx = ctx.cases.index[mask]
    if len(idx) == 0:
        return []
    take = idx[ctx.rng.random(len(idx)) < 0.82]
    picks = ctx.rng.integers(0, len(SHALLOW_NOTES), size=len(take))
    ctx.cases.loc[take, "notes"] = [SHALLOW_NOTES[i] for i in picks]
    ids = list(ctx.cases.loc[take, "case_id"])
    return [
        ctx.problem(
            "D05",
            "D05",
            f"{len(ids)} notes contain no concrete artefact - no IP, hash, host, "
            "user or action taken.",
            ids,
            "cases",
            "notes without artefacts",
            also=("D04",),
        )
    ]


# --------------------------------------------------------------------- D06
def inject_d06_recurring_unremediated(ctx: EntityData) -> list[dict]:
    crit_assets = ctx.assets[ctx.assets["criticality"].isin(["critical", "high"])]
    if crit_assets.empty:
        crit_assets = ctx.assets
    picks = crit_assets.sample(n=min(3, len(crit_assets)), random_state=7)
    days = (ctx.period_end - ctx.period_start).days
    new_alerts, new_cases = [], []
    evidence: list[str] = []
    rules = [
        ("Registry Run key modified", "persistence", "high", "edr"),
        ("OT setpoint changed outside change window", "impact", "critical", "ot_monitor"),
        ("USB mass storage device connected", "policy_violation", "low", "edr"),
    ]
    for k, (_, asset) in enumerate(picks.iterrows()):
        rule, category, severity, source = rules[k % len(rules)]
        aids = ctx.new_alert_ids(days)
        for d, aid in enumerate(aids):
            ts = ctx.period_start + timedelta(days=d, hours=9, minutes=17 + k)
            new_alerts.append(
                {
                    "alert_id": aid,
                    "entity_id": ctx.entity_id,
                    "asset_id": asset["asset_id"],
                    "rule_name": rule,
                    "category": category,
                    "severity": severity,
                    "source": source,
                    "created_at": ts,
                }
            )
            cid = f"{ctx.entity_id}-C9{k}{d:04d}"
            new_cases.append(
                {
                    "case_id": cid,
                    "entity_id": ctx.entity_id,
                    "alert_id": aid,
                    "analyst_name": ctx.analysts[d % len(ctx.analysts)],
                    "opened_at": ts + timedelta(minutes=4),
                    "closed_at": ts + timedelta(minutes=11),
                    "disposition": "false_positive",
                    "closure_type": "manual",
                    "notes": "Known recurring alert on this host, closing as before.",
                }
            )
            evidence.append(cid)
    ctx.alerts = pd.concat([ctx.alerts, pd.DataFrame(new_alerts)], ignore_index=True)
    ctx.cases = pd.concat([ctx.cases, pd.DataFrame(new_cases)], ignore_index=True)
    return [
        ctx.problem(
            "D06",
            "D06",
            f"{len(picks)} asset/rule pairs fire every single day for {days} days and "
            "are closed each time with no escalation or remediation.",
            evidence,
            "cases",
            "same rule + same asset, repeatedly closed",
            also=("D02",),
        )
    ]


# --------------------------------------------------------------------- D07
def inject_d07_effort_severity_mismatch(ctx: EntityData) -> list[dict]:
    mask = ctx.cases["closed_at"].notna() & (ctx.cases["closure_type"] == "manual")
    n = int(mask.sum())
    if n == 0:
        return []
    flat = ctx.rng.normal(20.0, 2.6, size=n).clip(9, 26.4)
    _set_duration(ctx, mask, flat)
    ids = list(ctx.cases.loc[mask, "case_id"])
    return [
        ctx.problem(
            "D07",
            "D07",
            "Investigation time is flat (about 20 minutes) for every severity, so "
            "critical alerts get no more effort than informational ones.",
            ids,
            "cases",
            "median handling time by severity",
        )
    ]


# --------------------------------------------------------------------- D08
def inject_d08_threshold_gaming(ctx: EntityData) -> list[dict]:
    """SLA is 30 minutes, so closures pile up at 27-29.9 minutes."""
    # This entity declares an aggressive 30-minute SLA for high alerts.
    ctx.commitments.loc[
        ctx.commitments["metric"] == "high_alert_investigation_minutes", "threshold"
    ] = 30.0
    sev = ctx.case_severity()
    mask = (
        sev.isin(["high", "medium"])
        & (ctx.cases["closure_type"] == "manual")
        & ctx.cases["closed_at"].notna()
    )
    idx = ctx.cases.index[mask]
    if len(idx) == 0:
        return []
    take = idx[ctx.rng.random(len(idx)) < 0.62]
    mins = ctx.rng.uniform(27.0, 29.93, size=len(take))
    ctx.cases.loc[take, "closed_at"] = ctx.cases.loc[
        take, "opened_at"
    ] + pd.to_timedelta(mins, unit="m")
    ids = list(ctx.cases.loc[take, "case_id"])
    return [
        ctx.problem(
            "D08",
            "D08",
            f"{len(ids)} closures land in the last three minutes before the declared "
            "30-minute SLA, which is not a natural distribution.",
            ids,
            "cases",
            "closure duration histogram near SLA",
        )
    ]


# --------------------------------------------------------------------- D09
def inject_d09_analyst_workload(ctx: EntityData) -> list[dict]:
    if not ctx.analysts:
        return []
    hero = ctx.analysts[0]
    closed = ctx.cases[ctx.cases["closed_at"].notna()].copy()
    if closed.empty:
        return []
    closed["day"] = closed["closed_at"].dt.floor("D")
    days = sorted(closed["day"].unique())
    target_days = days[: max(1, len(days) // 3)]
    idx = closed.index[closed["day"].isin(target_days)]
    # Give the "hero" analyst ~420 closures per day on the affected days.
    per_day_target = 420
    chosen: list[int] = []
    for d in target_days:
        day_idx = closed.index[closed["day"] == d]
        chosen.extend(list(day_idx[:per_day_target]))
    ctx.cases.loc[chosen, "analyst_name"] = hero
    ids = list(ctx.cases.loc[chosen, "case_id"])
    return [
        ctx.problem(
            "D09",
            "D09",
            f"A single analyst records up to {per_day_target} case closures on one "
            "day, which is not humanly plausible.",
            ids,
            "cases",
            "closures per analyst per day",
        )
    ]


# --------------------------------------------------------------------- D10
def inject_d10_silent_critical_assets(ctx: EntityData) -> list[dict]:
    crit = ctx.assets[ctx.assets["criticality"] == "critical"]
    if crit.empty:
        return []
    n_silent = max(3, int(len(crit) * 0.65))
    silent = crit.sample(n=min(n_silent, len(crit)), random_state=11)
    silent_ids = set(silent["asset_id"])
    drop = set(ctx.alerts.loc[ctx.alerts["asset_id"].isin(silent_ids), "alert_id"])
    ctx.prune_alerts(drop)
    return [
        ctx.problem(
            "D10",
            "D10",
            f"{len(silent_ids)} critical assets (including database and OT hosts) "
            "produced zero alerts for the whole period.",
            sorted(silent_ids),
            "assets",
            "critical assets with zero alerts",
            also=("D03",),
        )
    ]


# --------------------------------------------------------------------- D11
def inject_d11_missing_categories(ctx: EntityData) -> list[dict]:
    sector = getattr(ctx.profile, "sector", "power")
    drop_cats = {
        "banking": ["phishing", "credential_access"],
        "oil_gas": ["phishing", "exfiltration"],
        "power": ["phishing", "collection"],
        "telecom": ["phishing", "collection"],
        "transport": ["phishing", "exfiltration"],
    }.get(sector, ["phishing"])
    drop = set(ctx.alerts.loc[ctx.alerts["category"].isin(drop_cats), "alert_id"])
    ctx.prune_alerts(drop)
    return [
        ctx.problem(
            "D11",
            "D11",
            "Alert categories that every peer reports are completely absent here: "
            + ", ".join(drop_cats),
            drop_cats,
            "alerts",
            "categories missing vs peer group",
        )
    ]


# --------------------------------------------------------------------- D12
def inject_d12_volume_drop(ctx: EntityData) -> list[dict]:
    cutoff = ctx.period_end - timedelta(days=30)
    late = ctx.alerts["created_at"] >= cutoff
    late_ids = list(ctx.alerts.loc[late, "alert_id"])
    if not late_ids:
        return []
    keep_mask = ctx.rng.random(len(late_ids)) < 0.18
    drop = {aid for aid, keep in zip(late_ids, keep_mask) if not keep}
    ctx.prune_alerts(drop)
    return [
        ctx.problem(
            "D12",
            "D12",
            "Alert volume in the final 30 days fell by about 82% against this "
            "entity's own earlier baseline, with no stated reason.",
            sorted(drop),
            "alerts",
            "last 30 days vs prior baseline",
        )
    ]


# --------------------------------------------------------------------- D13
def inject_d13_broken_chain(ctx: EntityData) -> list[dict]:
    evidence: list[str] = []
    # (a) true positives with no escalation
    sev = ctx.case_severity()
    tp = ctx.cases.index[(sev.isin(["critical", "high"]))]
    take = tp[: max(1, int(len(tp) * 0.4))]
    ctx.cases.loc[take, "disposition"] = "true_positive"
    tp_ids = set(ctx.cases.loc[take, "case_id"])
    ctx.escalations = ctx.escalations[~ctx.escalations["case_id"].isin(tp_ids)]
    evidence.extend(sorted(tp_ids))
    # (b) cases pointing at an alert that does not exist
    orphan_idx = ctx.cases.index[-60:]
    ctx.cases.loc[orphan_idx, "alert_id"] = None
    evidence.extend(list(ctx.cases.loc[orphan_idx, "case_id"]))
    # (c) escalations pointing at a case that does not exist
    ghost = pd.DataFrame(
        [
            {
                "escalation_id": f"{ctx.entity_id}-EGHOST{i:03d}",
                "case_id": f"{ctx.entity_id}-C-MISSING-{i:03d}",
                "entity_id": ctx.entity_id,
                "from_tier": "tier1",
                "to_tier": "tier2",
                "escalated_at": ctx.period_start + timedelta(days=10 + i),
                "reason": "Escalation logged against a case that is not in the extract",
            }
            for i in range(12)
        ]
    )
    ctx.escalations = pd.concat([ctx.escalations, ghost], ignore_index=True)
    evidence.extend(list(ghost["escalation_id"]))
    return [
        ctx.problem(
            "D13",
            "D13",
            "Broken evidence chains: true positives with no escalation, cases with no "
            "parent alert, and escalations whose case is missing from the extract.",
            evidence,
            "cases",
            "referential integrity across alerts/cases/escalations",
            also=("D02",),
        )
    ]


# --------------------------------------------------------------------- D14
def inject_d14_marker(ctx: EntityData) -> list[dict]:
    """No mutation. The entity is already a multi-dimensional outlier."""
    return [
        ctx.problem(
            "D14",
            "D14",
            "This entity deviates from its peer group on several unrelated metrics at "
            "once and should surface as an unsupervised outlier.",
            [ctx.entity_id],
            "entities",
            "IsolationForest on per-entity features",
        )
    ]


# --------------------------------------------------------------------- Q01
def inject_q01_id_gaps(ctx: EntityData) -> list[dict]:
    ids = sorted(ctx.alerts["alert_id"])
    if len(ids) < 1200:
        start = len(ids) // 3
        span = max(20, len(ids) // 12)
    else:
        start, span = 800, 180
    missing = set(ids[start : start + span])
    ctx.prune_alerts(missing)
    return [
        ctx.problem(
            "Q01",
            "Q01",
            f"A contiguous block of {len(missing)} alert IDs is missing from the "
            "submission, which suggests records were removed or never exported.",
            sorted(missing),
            "alerts",
            "sequential alert_id gaps",
        )
    ]


# --------------------------------------------------------------------- Q02
def inject_q02_time_gaps(ctx: EntityData) -> list[dict]:
    gap_start = ctx.period_start + timedelta(days=40)
    gap_end = gap_start + timedelta(days=7)
    mask = (ctx.alerts["created_at"] >= gap_start) & (ctx.alerts["created_at"] < gap_end)
    drop = set(ctx.alerts.loc[mask, "alert_id"])
    ctx.prune_alerts(drop)
    return [
        ctx.problem(
            "Q02",
            "Q02",
            f"No alerts at all between {gap_start.date()} and {gap_end.date()} - a "
            "full week of the submission is missing.",
            sorted(drop),
            "alerts",
            "calendar gap in alert timestamps",
            also=("Q01",),
        )
    ]


# --------------------------------------------------------------------- Q03
def inject_q03_declared_mismatch(ctx: EntityData) -> list[dict]:
    if ctx.submissions.empty:
        return []
    ctx.submissions["declared_alert_count"] = (
        ctx.submissions["declared_alert_count"] * 1.42
    ).astype(int)
    ids = list(ctx.submissions["submission_id"])
    return [
        ctx.problem(
            "Q03",
            "Q03",
            "The declared alert count in the submission header is about 42% higher "
            "than the number of alert rows actually supplied.",
            ids,
            "submissions",
            "declared vs actual row counts",
        )
    ]


# --------------------------------------------------------------------- Q04
def inject_q04_timestamp_regularity(ctx: EntityData) -> list[dict]:
    idx = ctx.alerts.index
    take = idx[ctx.rng.random(len(idx)) < 0.72]
    ctx.alerts.loc[take, "created_at"] = ctx.alerts.loc[take, "created_at"].dt.floor("h")
    ids = list(ctx.alerts.loc[take, "alert_id"])
    return [
        ctx.problem(
            "Q04",
            "Q04",
            f"{len(ids)} alert timestamps fall exactly on the hour with zero minutes "
            "and seconds, which real telemetry does not do.",
            ids,
            "alerts",
            "timestamp granularity",
        )
    ]


INJECTORS: dict[str, Callable[[EntityData], list[dict]]] = {
    "D01": inject_d01_fast_critical_closure,
    "D02": inject_d02_critical_no_escalation,
    "D03": inject_d03_commitment_breach,
    "D04": inject_d04_template_notes,
    "D05": inject_d05_shallow_investigation,
    "D06": inject_d06_recurring_unremediated,
    "D07": inject_d07_effort_severity_mismatch,
    "D08": inject_d08_threshold_gaming,
    "D09": inject_d09_analyst_workload,
    "D10": inject_d10_silent_critical_assets,
    "D11": inject_d11_missing_categories,
    "D12": inject_d12_volume_drop,
    "D13": inject_d13_broken_chain,
    "D14": inject_d14_marker,
    "Q01": inject_q01_id_gaps,
    "Q02": inject_q02_time_gaps,
    "Q03": inject_q03_declared_mismatch,
    "Q04": inject_q04_timestamp_regularity,
}

#: Injectors are applied in this order so that mutations happen before the
#: structural deletions that would otherwise hide them.
APPLY_ORDER = [
    "D03",
    "D07",
    "D08",
    "D01",
    "D04",
    "D05",
    "D06",
    "D09",
    "D02",
    "D13",
    "D11",
    "D10",
    "D12",
    "Q01",
    "Q02",
    "Q04",
    "Q03",
    "D14",
]
