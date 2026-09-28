"""Synthetic SOC corpus generator.

    python -m generator.generate --seed 42 --entities 12 --days 90

Writes one CSV per canonical table into data/raw/ plus data/ground_truth.json.
Fully deterministic for a given seed: the same seed always produces byte-identical
CSVs. No wall-clock time is used anywhere; the reporting window ends on a fixed
date (generator.entities.PERIOD_END).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from faker import Faker

from generator.content import (
    CATEGORY_LIBRARY,
    CATEGORIES,
    ESCALATION_REASONS,
    SECTOR_CATEGORY_BIAS,
    build_note,
)
from generator.entities import PERIOD_END, TIER_SPECS, select_profiles
from generator.faults import APPLY_ORDER, INJECTORS, EntityData

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "raw"

ASSET_TYPE_WEIGHTS = {
    "default": {
        "workstation": 0.44,
        "server": 0.24,
        "db": 0.06,
        "network": 0.12,
        "ot": 0.07,
        "cloud": 0.07,
    },
    "ot_heavy": {
        "workstation": 0.30,
        "server": 0.21,
        "db": 0.05,
        "network": 0.13,
        "ot": 0.26,
        "cloud": 0.05,
    },
}
CRITICALITY_BY_TYPE = {
    "db": [0.34, 0.40, 0.21, 0.05],
    "ot": [0.30, 0.38, 0.25, 0.07],
    "server": [0.12, 0.33, 0.40, 0.15],
    "network": [0.09, 0.28, 0.43, 0.20],
    "cloud": [0.08, 0.30, 0.42, 0.20],
    "workstation": [0.01, 0.07, 0.36, 0.56],
}
CRITICALITY_LEVELS = ["critical", "high", "medium", "low"]

# Alerts are more likely on high-value, noisy assets.
ASSET_ALERT_WEIGHT = {"critical": 2.4, "high": 1.9, "medium": 1.0, "low": 0.55}

# Baseline handling time in minutes; grows with severity for healthy entities.
BASE_MINUTES = {"critical": 148.0, "high": 74.0, "medium": 41.0, "low": 21.0, "info": 8.5}
AUTOMATION_PROB = {"critical": 0.0, "high": 0.01, "medium": 0.05, "low": 0.32, "info": 0.58}
AUTOMATION_PROB_HEAVY = {
    "critical": 0.0,
    "high": 0.02,
    "medium": 0.10,
    "low": 0.55,
    "info": 0.93,
}
TRUE_POSITIVE_PROB = {
    "critical": 0.36,
    "high": 0.24,
    "medium": 0.12,
    "low": 0.06,
    "info": 0.02,
}
ESCALATION_PROB = {"critical": 0.93, "high": 0.56, "medium": 0.14, "low": 0.02, "info": 0.0}
WEEKDAY_FACTOR = np.array([1.16, 1.20, 1.18, 1.15, 1.04, 0.58, 0.48])
HOUR_WEIGHTS = np.array(
    [
        0.35, 0.28, 0.24, 0.22, 0.26, 0.38,  # 00-05 night shift dip
        0.62, 0.95, 1.35, 1.75, 1.85, 1.70,  # 06-11 morning peak
        1.45, 1.60, 1.72, 1.68, 1.50, 1.25,  # 12-17 afternoon
        1.00, 0.85, 0.72, 0.62, 0.52, 0.42,  # 18-23 evening taper
    ]
)
HOUR_P = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

COMMITMENTS_TEMPLATE = [
    ("critical_escalation_minutes", 15.0, "minutes"),
    ("critical_alert_investigation_minutes", 240.0, "minutes"),
    ("high_alert_investigation_minutes", 120.0, "minutes"),
    ("critical_asset_monitoring_coverage", 100.0, "percent"),
    ("mean_time_to_close_hours", 24.0, "hours"),
]

TABLES = [
    "entities",
    "commitments",
    "assets",
    "alerts",
    "cases",
    "escalations",
    "submissions",
]


# --------------------------------------------------------------------- helpers
def _abbrev(name: str) -> str:
    parts = [p for p in name.replace(".", " ").replace(",", " ").split() if p[:1].isalpha()]
    letters = "".join(p[0] for p in parts)[:3].upper()
    return letters or "ORG"


def _category_probabilities(sector: str) -> np.ndarray:
    bias = SECTOR_CATEGORY_BIAS.get(sector, {})
    base = np.array([1.0 + 0.35 * ((i * 7) % 5) / 4 for i in range(len(CATEGORIES))])
    for i, cat in enumerate(CATEGORIES):
        base[i] *= bias.get(cat, 1.0)
    return base / base.sum()


def _weighted_index(rng: np.random.Generator, probs: np.ndarray, n: int) -> np.ndarray:
    return rng.choice(len(probs), size=n, p=probs)


# --------------------------------------------------------- per-entity builders
def _build_assets(
    rng: np.random.Generator, fake: Faker, profile: Any, prefix: str
) -> pd.DataFrame:
    lo, hi = TIER_SPECS[profile.size_tier]["assets"]
    n = int(rng.integers(lo, hi + 1))
    weights = (
        ASSET_TYPE_WEIGHTS["ot_heavy"]
        if profile.sector in ("power", "oil_gas", "transport")
        else ASSET_TYPE_WEIGHTS["default"]
    )
    types = list(weights)
    probs = np.array([weights[t] for t in types])
    probs = probs / probs.sum()
    type_idx = _weighted_index(rng, probs, n)
    rows = []
    octet_b = int(rng.integers(10, 250))
    for i in range(n):
        atype = types[type_idx[i]]
        crit = CRITICALITY_LEVELS[
            _weighted_index(rng, np.array(CRITICALITY_BY_TYPE[atype]), 1)[0]
        ]
        if atype == "ot":
            env = "ot"
        else:
            env = ["prod", "prod", "prod", "dev"][int(rng.integers(0, 4))]
        rows.append(
            {
                "asset_id": f"{profile.entity_id}-AS{i:05d}",
                "entity_id": profile.entity_id,
                "hostname": f"{prefix}-{atype[:3].upper()}-{i:05d}",
                "ip_address": f"10.{octet_b}.{(i // 250) % 250}.{i % 250 + 1}",
                "asset_type": atype,
                "criticality": crit,
                "environment": env,
            }
        )
    df = pd.DataFrame(rows)
    # Guarantee a meaningful number of critical assets to reason about.
    if (df["criticality"] == "critical").sum() < 8:
        promote = df.index[df["asset_type"].isin(["db", "ot", "server"])][:8]
        df.loc[promote, "criticality"] = "critical"
    return df


def _build_alerts(
    rng: np.random.Generator,
    profile: Any,
    assets: pd.DataFrame,
    period_start: datetime,
    days: int,
) -> pd.DataFrame:
    lo, hi = TIER_SPECS[profile.size_tier]["alerts_per_day"]
    base_rate = float(rng.uniform(lo, hi)) * float(profile.volume_factor)
    day_idx = np.arange(days)
    dow = (np.array([(period_start + timedelta(days=int(d))).weekday() for d in day_idx]))
    # Slow organic drift plus weekday shape plus Poisson noise.
    drift = 1.0 + 0.12 * np.sin(day_idx / 14.0)
    lam = base_rate * WEEKDAY_FACTOR[dow] * drift
    counts = rng.poisson(lam)
    total = int(counts.sum())
    if total == 0:
        return pd.DataFrame(
            columns=[
                "alert_id", "entity_id", "asset_id", "rule_name", "category",
                "severity", "source", "created_at",
            ]
        )
    day_of = np.repeat(day_idx, counts)
    hours = rng.choice(24, size=total, p=HOUR_P)
    minutes = rng.integers(0, 60, size=total)
    seconds = rng.integers(0, 60, size=total)
    created = (
        np.datetime64(period_start)
        + day_of.astype("timedelta64[D]")
        + hours.astype("timedelta64[h]")
        + minutes.astype("timedelta64[m]")
        + seconds.astype("timedelta64[s]")
    )

    cat_probs = _category_probabilities(profile.sector)
    cat_idx = _weighted_index(rng, cat_probs, total)
    categories = np.array(CATEGORIES)[cat_idx]

    rule_names = np.empty(total, dtype=object)
    severities = np.empty(total, dtype=object)
    sources = np.empty(total, dtype=object)
    sev_levels = np.array(["critical", "high", "medium", "low", "info"])
    for ci, cat in enumerate(CATEGORIES):
        sel = cat_idx == ci
        k = int(sel.sum())
        if k == 0:
            continue
        lib = CATEGORY_LIBRARY[cat]
        rules = np.array(lib["rules"], dtype=object)
        rule_names[sel] = rules[rng.integers(0, len(rules), size=k)]
        sev_p = np.array(lib["sev"], dtype=float)
        sev_p = sev_p / sev_p.sum()
        severities[sel] = sev_levels[rng.choice(5, size=k, p=sev_p)]
        srcs = np.array(lib["sources"], dtype=object)
        sources[sel] = srcs[rng.integers(0, len(srcs), size=k)]

    aw = assets["criticality"].map(ASSET_ALERT_WEIGHT).to_numpy(dtype=float)
    aw = aw / aw.sum()
    asset_ids = assets["asset_id"].to_numpy()[rng.choice(len(assets), size=total, p=aw)]

    order = np.argsort(created, kind="stable")
    df = pd.DataFrame(
        {
            "alert_id": [f"{profile.entity_id}-A{i:07d}" for i in range(total)],
            "entity_id": profile.entity_id,
            "asset_id": asset_ids[order],
            "rule_name": rule_names[order],
            "category": categories[order],
            "severity": severities[order],
            "source": sources[order],
            "created_at": pd.to_datetime(created[order]),
        }
    )
    return df


def _build_cases(
    rng: np.random.Generator,
    fake: Faker,
    profile: Any,
    alerts: pd.DataFrame,
    assets: pd.DataFrame,
    analysts: list[str],
    usernames: list[str],
) -> pd.DataFrame:
    if alerts.empty:
        return pd.DataFrame(
            columns=[
                "case_id", "entity_id", "alert_id", "analyst_name", "opened_at",
                "closed_at", "disposition", "closure_type", "notes",
            ]
        )
    # ~93% of alerts get a case; the rest are still in the queue.
    has_case = rng.random(len(alerts)) < 0.93
    sub = alerts.loc[has_case].reset_index(drop=True)
    n = len(sub)
    sev = sub["severity"].to_numpy()

    triage_delay = rng.gamma(shape=2.0, scale=6.0, size=n).clip(0.5, 180)
    opened = sub["created_at"] + pd.to_timedelta(triage_delay, unit="m")

    base = np.array([BASE_MINUTES[s] for s in sev])
    duration = base * rng.lognormal(mean=0.0, sigma=0.55, size=n)
    duration = duration.clip(3.0, 60 * 72)
    # 4% of cases are still open at the end of the period.
    still_open = rng.random(n) < 0.04
    closed = opened + pd.to_timedelta(duration, unit="m")
    closed = closed.where(~still_open)

    auto_table = (
        AUTOMATION_PROB_HEAVY
        if profile.flags.get("automation_heavy")
        else AUTOMATION_PROB
    )
    auto_p = np.array([auto_table[s] for s in sev])
    is_auto = rng.random(n) < auto_p
    closure_type = np.where(is_auto, "automated", "manual")
    # Automated closures are fast by construction - this is the innocent pattern.
    auto_minutes = rng.uniform(0.2, 3.0, size=n)
    closed = pd.Series(
        np.where(
            is_auto & ~still_open,
            (opened + pd.to_timedelta(auto_minutes, unit="m")).to_numpy(),
            closed.to_numpy(),
        )
    )

    tp_p = np.array([TRUE_POSITIVE_PROB[s] for s in sev])
    roll = rng.random(n)
    # Object dtype on purpose: fixed-width numpy string arrays would truncate
    # the longer labels.
    disposition = np.empty(n, dtype=object)
    disposition[:] = "true_positive"
    rest = roll >= tp_p
    other = np.array(["false_positive", "benign", "duplicate"], dtype=object)
    disposition[rest] = other[rng.choice(3, size=int(rest.sum()), p=[0.55, 0.33, 0.12])]
    disposition[is_auto & ~still_open] = "false_positive"
    disposition[still_open] = "unresolved"

    analyst_arr = np.array(analysts, dtype=object)
    analyst_pick = analyst_arr[rng.integers(0, len(analyst_arr), size=n)]

    host_map = assets.set_index("asset_id")["hostname"]
    ip_map = assets.set_index("asset_id")["ip_address"]
    hosts = sub["asset_id"].map(host_map).fillna("unknown-host").to_numpy()
    ips = sub["asset_id"].map(ip_map).fillna("10.0.0.1").to_numpy()
    user_arr = np.array(usernames, dtype=object)
    users = user_arr[rng.integers(0, len(user_arr), size=n)]
    hashes = [f"{rng.integers(0, 2**63):016x}{rng.integers(0, 2**63):016x}" for _ in range(n)]
    rules = sub["rule_name"].to_numpy()

    notes: list[str] = []
    for i in range(n):
        if closure_type[i] == "automated":
            notes.append(
                f"Auto-closed by correlation rule AUTO-{(i % 37) + 1:02d}: "
                f"{rules[i]} on {hosts[i]} matched an approved allow-list entry."
            )
        else:
            notes.append(
                build_note(rng, hosts[i], users[i], ips[i], hashes[i], sev[i], rules[i])
            )

    return pd.DataFrame(
        {
            "case_id": [f"{profile.entity_id}-C{i:07d}" for i in range(n)],
            "entity_id": profile.entity_id,
            "alert_id": sub["alert_id"],
            "analyst_name": analyst_pick,
            "opened_at": opened,
            "closed_at": pd.to_datetime(closed),
            "disposition": disposition,
            "closure_type": closure_type,
            "notes": notes,
        }
    )


def _build_escalations(
    rng: np.random.Generator, profile: Any, alerts: pd.DataFrame, cases: pd.DataFrame
) -> pd.DataFrame:
    if cases.empty:
        return pd.DataFrame(
            columns=[
                "escalation_id", "case_id", "entity_id", "from_tier", "to_tier",
                "escalated_at", "reason",
            ]
        )
    sev_map = alerts.set_index("alert_id")["severity"]
    sev = cases["alert_id"].map(sev_map).fillna("info")
    p = sev.map(ESCALATION_PROB).fillna(0.0).to_numpy(dtype=float)
    # A healthy SOC escalates criticals on sight; confirmed true positives are
    # escalated even more reliably.
    is_tp = cases["disposition"].to_numpy() == "true_positive"
    p = np.clip(np.where(is_tp, p * 1.5, p), 0.0, 0.985)
    take = rng.random(len(cases)) < p
    sel = cases.loc[take]
    k = len(sel)
    if k == 0:
        return pd.DataFrame(
            columns=[
                "escalation_id", "case_id", "entity_id", "from_tier", "to_tier",
                "escalated_at", "reason",
            ]
        )
    delay = rng.gamma(2.0, 3.0, size=k).clip(0.5, 60)
    to_tier = np.array(["tier2", "tier3", "ciso_office"])[
        rng.choice(3, size=k, p=[0.66, 0.29, 0.05])
    ]
    reasons = np.array(ESCALATION_REASONS, dtype=object)[
        rng.integers(0, len(ESCALATION_REASONS), size=k)
    ]
    return pd.DataFrame(
        {
            "escalation_id": [f"{profile.entity_id}-E{i:06d}" for i in range(k)],
            "case_id": sel["case_id"].to_numpy(),
            "entity_id": profile.entity_id,
            "from_tier": "tier1",
            "to_tier": to_tier,
            "escalated_at": sel["opened_at"].to_numpy()
            + pd.to_timedelta(delay, unit="m").to_numpy(),
            "reason": reasons,
        }
    )


def _build_submissions(
    profile: Any, alerts: pd.DataFrame, period_start: datetime, period_end: datetime
) -> pd.DataFrame:
    rows = []
    window = 30
    idx = 0
    cursor = period_start
    while cursor < period_end:
        nxt = min(cursor + timedelta(days=window), period_end)
        mask = (alerts["created_at"] >= cursor) & (alerts["created_at"] < nxt)
        ids = sorted(alerts.loc[mask, "alert_id"])
        digest = hashlib.sha256("|".join(ids).encode()).hexdigest()
        rows.append(
            {
                "submission_id": f"{profile.entity_id}-SUB{idx:02d}",
                "entity_id": profile.entity_id,
                "period_start": cursor,
                "period_end": nxt,
                "declared_alert_count": len(ids),
                "file_hash": digest,
                "uploaded_at": nxt + timedelta(days=2, hours=9),
                "integrity_status": "declared",
            }
        )
        cursor = nxt
        idx += 1
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ orchestrator
def generate(
    seed: int = 42,
    n_entities: int = 12,
    days: int = 90,
    out_dir: Path | str = DEFAULT_OUT,
    foreign_format: bool = False,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    profiles = select_profiles(n_entities)
    period_end = datetime.fromisoformat(PERIOD_END)
    period_start = period_end - timedelta(days=days)

    Faker.seed(seed)
    fake = Faker("en_IN")

    entity_rows, all_tables = [], {t: [] for t in TABLES if t != "entities"}
    ground_truth: list[dict] = []
    summary_rows: list[dict] = []

    for idx, profile in enumerate(profiles):
        rng = np.random.default_rng(seed * 1_000 + idx)
        prefix = _abbrev(profile.name)
        lo, hi = TIER_SPECS[profile.size_tier]["analysts"]
        analyst_count = int(rng.integers(lo, hi + 1))
        analysts = [f"{fake.first_name()} {fake.last_name()}" for _ in range(analyst_count)]
        usernames = [
            f"{a.split()[0].lower()}.{a.split()[-1].lower()}" for a in analysts
        ] + [f"{fake.first_name().lower()}.{fake.last_name().lower()}" for _ in range(25)]

        assets = _build_assets(rng, fake, profile, prefix)
        alerts = _build_alerts(rng, profile, assets, period_start, days)
        cases = _build_cases(rng, fake, profile, alerts, assets, analysts, usernames)
        escalations = _build_escalations(rng, profile, alerts, cases)
        commitments = pd.DataFrame(
            [
                {
                    "entity_id": profile.entity_id,
                    "metric": m,
                    "threshold": t,
                    "unit": u,
                }
                for m, t, u in COMMITMENTS_TEMPLATE
            ]
        )
        submissions = _build_submissions(profile, alerts, period_start, period_end)

        ctx = EntityData(
            entity_id=profile.entity_id,
            profile=profile,
            rng=rng,
            period_start=period_start,
            period_end=period_end,
            assets=assets,
            alerts=alerts,
            cases=cases,
            escalations=escalations,
            commitments=commitments,
            submissions=submissions,
            analysts=analysts,
            next_alert_seq=len(alerts),
        )

        codes = [c for c in APPLY_ORDER if c in profile.faults]
        for code in codes:
            if code in ("Q03", "D14"):
                continue
            ground_truth.extend(INJECTORS[code](ctx))

        # Declared counts must reflect the data actually shipped, unless Q03
        # deliberately breaks that link.
        ctx.submissions = _build_submissions(profile, ctx.alerts, period_start, period_end)
        for code in ("Q03", "D14"):
            if code in profile.faults:
                ground_truth.extend(INJECTORS[code](ctx))

        ctx.alerts = ctx.alerts.sort_values("created_at").reset_index(drop=True)
        ctx.cases = ctx.cases.sort_values("case_id").reset_index(drop=True)
        ctx.escalations = ctx.escalations.sort_values("escalation_id").reset_index(drop=True)

        entity_rows.append(
            {
                "entity_id": profile.entity_id,
                "name": profile.name,
                "sector": profile.sector,
                "size_tier": profile.size_tier,
                "analyst_count": analyst_count,
            }
        )
        all_tables["assets"].append(ctx.assets)
        all_tables["alerts"].append(ctx.alerts)
        all_tables["cases"].append(ctx.cases)
        all_tables["escalations"].append(ctx.escalations)
        all_tables["commitments"].append(ctx.commitments)
        all_tables["submissions"].append(ctx.submissions)

        summary_rows.append(
            {
                "entity_id": profile.entity_id,
                "name": profile.name[:32],
                "sector": profile.sector,
                "tier": profile.size_tier,
                "role": profile.role,
                "assets": len(ctx.assets),
                "alerts": len(ctx.alerts),
                "cases": len(ctx.cases),
                "escalations": len(ctx.escalations),
                "planted": ",".join(profile.faults) or "-",
            }
        )

    frames = {"entities": pd.DataFrame(entity_rows)}
    for name, parts in all_tables.items():
        frames[name] = (
            pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        )

    for name in TABLES:
        path = out / f"{name}.csv"
        frames[name].to_csv(path, index=False, date_format="%Y-%m-%d %H:%M:%S")

    gt_path = out.parent / "ground_truth.json"
    payload = {
        "seed": seed,
        "entities": len(profiles),
        "days": days,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generator_version": "1.0.0",
        "innocent_lookalikes": [
            {
                "entity_id": p.entity_id,
                "name": p.name,
                "why": p.notes,
            }
            for p in profiles
            if p.role == "innocent_lookalike"
        ],
        "healthy_entities": [p.entity_id for p in profiles if p.role == "healthy"],
        "problems": ground_truth,
    }
    gt_path.write_text(json.dumps(payload, indent=2, default=str))

    if foreign_format:
        _write_foreign_format(frames, out.parent / "foreign", profiles[3].entity_id)

    _print_summary(summary_rows, frames, ground_truth, seed, days)
    return {"frames": frames, "ground_truth": payload, "summary": summary_rows}


def _write_foreign_format(
    frames: dict[str, pd.DataFrame], out_dir: Path, entity_id: str
) -> None:
    """Export one entity's alerts and cases with vendor-specific column names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sev_to_p = {
        "critical": "P1",
        "high": "P2",
        "medium": "P3",
        "low": "P4",
        "info": "P5",
    }
    alerts = frames["alerts"]
    alerts = alerts[alerts["entity_id"] == entity_id].copy()
    foreign_alerts = pd.DataFrame(
        {
            "Ticket No": alerts["alert_id"],
            "Device": alerts["asset_id"],
            "Detection Rule": alerts["rule_name"],
            "Attack Stage": alerts["category"],
            "Sev": alerts["severity"].map(sev_to_p),
            "Feed": alerts["source"],
            "Opened": alerts["created_at"],
        }
    )
    cases = frames["cases"]
    cases = cases[cases["entity_id"] == entity_id].copy()
    foreign_cases = pd.DataFrame(
        {
            "Ref": cases["case_id"],
            "Ticket No": cases["alert_id"],
            "Assignee": cases["analyst_name"],
            "Opened": cases["opened_at"],
            "Resolved": cases["closed_at"],
            "Outcome": cases["disposition"].str.replace("_", " ").str.title(),
            "How Closed": cases["closure_type"].str.title(),
            "Comments": cases["notes"],
        }
    )
    foreign_alerts.to_csv(out_dir / f"{entity_id}_alerts_foreign.csv", index=False)
    foreign_cases.to_csv(out_dir / f"{entity_id}_cases_foreign.csv", index=False)
    foreign_alerts.to_json(
        out_dir / f"{entity_id}_alerts_foreign.json", orient="records", indent=2,
        date_format="iso",
    )
    print(f"\nForeign-format export for {entity_id} written to {out_dir}")


def _print_summary(
    rows: list[dict],
    frames: dict[str, pd.DataFrame],
    ground_truth: list[dict],
    seed: int,
    days: int,
) -> None:
    hdr = (
        f"{'entity':7} {'name':34} {'sector':9} {'tier':7} {'role':19} "
        f"{'assets':>7} {'alerts':>8} {'cases':>7} {'escal':>6}  planted"
    )
    print("\n" + "=" * len(hdr))
    print(f"SAT-SA Lens synthetic corpus - seed {seed}, {days} days")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['entity_id']:7} {r['name']:34} {r['sector']:9} {r['tier']:7} "
            f"{r['role']:19} {r['assets']:>7} {r['alerts']:>8} {r['cases']:>7} "
            f"{r['escalations']:>6}  {r['planted']}"
        )
    print("-" * len(hdr))
    print("\nRow counts per table:")
    for name in TABLES:
        print(f"  {name:14} {len(frames[name]):>9,}")
    print(f"\nPlanted problems: {len(ground_truth)}")
    by_det: dict[str, int] = {}
    for p in ground_truth:
        by_det[p["expected_detector_id"]] = by_det.get(p["expected_detector_id"], 0) + 1
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(by_det.items())))


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic SOC submissions")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--entities", type=int, default=12)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument(
        "--foreign-format",
        action="store_true",
        help="also export one entity with vendor column names (CSV + JSON)",
    )
    args = ap.parse_args()
    generate(
        seed=args.seed,
        n_entities=args.entities,
        days=args.days,
        out_dir=args.out,
        foreign_format=args.foreign_format,
    )


if __name__ == "__main__":
    main()
