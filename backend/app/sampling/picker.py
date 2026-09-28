"""Review-sample picker: which records a human should actually look at."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from app.config import RANDOM_SEED
from app.db import fetch_dicts, locked
from app.scoring.score import finding_weight
from app.services import current_run_id, findings

RISK_SHARE = 0.70


def generate_sample(
    entity_id: str,
    size: int = 50,
    seed: int = RANDOM_SEED,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    """70% highest-risk evidence records, 30% seeded uniform random.

    The random third is what lets a supervisor say something about the records the
    tool did *not* flag, which is the only way to estimate what was missed.
    """
    run_id = run_id or current_run_id()
    if not run_id:
        return {"error": "No analysis run yet."}
    rng = np.random.default_rng(seed)
    fs = [
        f
        for f in findings(
            run_id=run_id, entity_id=entity_id, include_evidence_ids=True, limit=10_000
        )
        if f["status"] in ("open", "valid")
    ]

    # ------------------------------------------------------- risk-weighted picks
    weights: dict[tuple[str, str], float] = {}
    reasons: dict[tuple[str, str], list[str]] = {}
    for f in fs:
        w = finding_weight(f["severity"], f["confidence"])
        table = f["evidence_table"]
        if table not in ("cases", "alerts"):
            continue
        ids = f["evidence_row_ids"]
        if not ids:
            continue
        # Spread a finding's weight over its evidence so a finding with three
        # damning rows does not lose out to one with three thousand.
        per_row = w / np.sqrt(len(ids))
        for rid in ids:
            key = (table, str(rid))
            weights[key] = weights.get(key, 0.0) + per_row
            reasons.setdefault(key, []).append(f"{f['detector_id']}: {f['title']}")

    n_risk = int(round(size * RISK_SHARE))
    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    risk_rows = ranked[:n_risk]

    # ------------------------------------------------------------ random picks
    n_random = size - len(risk_rows)
    pool = fetch_dicts(
        "SELECT case_id FROM cases WHERE entity_id = ? ORDER BY case_id", [entity_id]
    )
    chosen_random: list[str] = []
    if pool and n_random > 0:
        taken = {rid for (_, rid) in [k for k, _ in risk_rows]}
        available = [r["case_id"] for r in pool if r["case_id"] not in taken]
        if available:
            pick = rng.choice(
                len(available), size=min(n_random, len(available)), replace=False
            )
            chosen_random = [available[int(i)] for i in np.sort(pick)]

    sample_id = f"SMP-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows: list[list[Any]] = []
    items: list[dict[str, Any]] = []
    for (table, rid), w in risk_rows:
        reason = "; ".join(sorted(set(reasons[(table, rid)]))[:3])
        rows.append([sample_id, entity_id, run_id, rid, table, reason, "highest_risk", w, now])
        items.append(
            {
                "row_id": rid,
                "row_table": table,
                "bucket": "highest_risk",
                "risk_weight": round(w, 2),
                "pick_reason": reason,
            }
        )
    for rid in chosen_random:
        reason = (
            "Uniform random control sample (seeded) - included so the review can also "
            "measure what the tool did not flag."
        )
        rows.append([sample_id, entity_id, run_id, rid, "cases", reason, "random", 0.0, now])
        items.append(
            {
                "row_id": rid,
                "row_table": "cases",
                "bucket": "random",
                "risk_weight": 0.0,
                "pick_reason": reason,
            }
        )

    with locked() as conn:
        conn.executemany(
            "INSERT INTO review_samples VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )

    total_cases = len(pool)
    flagged_rows = len({rid for (t, rid) in weights if t == "cases"})
    return {
        "sample_id": sample_id,
        "entity_id": entity_id,
        "run_id": run_id,
        "requested_size": size,
        "actual_size": len(items),
        "seed": seed,
        "risk_share": RISK_SHARE,
        "items": items,
        "coverage": {
            "entity_cases_total": total_cases,
            "cases_referenced_by_findings": flagged_rows,
            "share_of_cases_flagged": round(flagged_rows / max(total_cases, 1), 4),
            "risk_picks": len(risk_rows),
            "random_picks": len(chosen_random),
            "share_of_flagged_cases_sampled": round(
                len(risk_rows) / max(flagged_rows, 1), 4
            ),
        },
    }


def sample_rows(sample_id: str) -> list[dict[str, Any]]:
    return fetch_dicts(
        "SELECT * FROM review_samples WHERE sample_id = ? ORDER BY pick_bucket, row_id",
        [sample_id],
    )


def sample_csv(sample_id: str) -> str:
    import csv
    import io

    rows = sample_rows(sample_id)
    buf = io.StringIO()
    if not rows:
        return "sample_id,entity_id,run_id,row_id,row_table,pick_reason,pick_bucket\n"
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
