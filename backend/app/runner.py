"""The analysis runner: one call produces one fully audited, reproducible run."""
from __future__ import annotations

import time
from typing import Any, Optional, Sequence

from app.audit.runlog import current_data_hash, finish_run, log_action, new_run_id, start_run
from app.db import locked
from app.detectors.base import VIEW_SQL, RunContext, finding_to_row
from app.detectors.registry import DETECTORS, detector_versions
from app.scoring.peers import build_peer_index
from app.scoring.score import compute_and_store
from app.schema import Finding


def create_views() -> None:
    with locked() as conn:
        for stmt in filter(None, (s.strip() for s in VIEW_SQL.split(";"))):
            conn.execute(stmt)


def run_analysis(
    only: Optional[Sequence[str]] = None,
    actor: str = "system",
    notes: str = "",
    run_status: str = "complete",
) -> dict[str, Any]:
    """Run every registered detector, store findings, recompute scores."""
    create_views()
    run_id = new_run_id()
    versions = detector_versions()
    data_hash = current_data_hash()
    start_run(run_id, data_hash, versions, notes)

    peers = build_peer_index()
    detectors = [d for d in DETECTORS if not only or d.id in set(only)]
    per_detector: list[dict[str, Any]] = []
    all_findings: list[Finding] = []

    with locked() as conn:
        ctx = RunContext(conn=conn, run_id=run_id, peers=peers)
        for detector in detectors:
            t0 = time.perf_counter()
            error = ""
            findings: list[Finding] = []
            try:
                findings = detector.run(ctx)
            except Exception as exc:  # a broken detector must not kill the run
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - t0
            all_findings.extend(findings)
            per_detector.append(
                {
                    "detector_id": detector.id,
                    "version": detector.version,
                    "findings": len(findings),
                    "entities_flagged": sorted({f.entity_id for f in findings}),
                    "seconds": round(elapsed, 3),
                    "error": error,
                }
            )
            if error:
                log_action("system", "detector_error", "detector", detector.id, error)

        if all_findings:
            conn.executemany(
                "INSERT INTO findings VALUES (" + ", ".join(["?"] * 18) + ")",
                [finding_to_row(f) for f in all_findings],
            )

    scores = compute_and_store(run_id) if run_status == "complete" else {}
    finish_run(run_id, len(all_findings), len(peers.entities), status=run_status)
    log_action(
        actor,
        "run_analysis",
        "run",
        run_id,
        f"{len(all_findings)} findings from {len(detectors)} detectors; "
        f"data_hash={data_hash[:16]}",
    )
    return {
        "run_id": run_id,
        "data_hash": data_hash,
        "detector_versions": versions,
        "finding_count": len(all_findings),
        "entity_count": len(peers.entities),
        "per_detector": per_detector,
        "status": run_status,
        "scores": {k: v["risk_score"] for k, v in scores.items()},
    }


def main() -> None:  # pragma: no cover - CLI convenience
    result = run_analysis()
    print(f"run_id       = {result['run_id']}")
    print(f"data_hash    = {result['data_hash'][:32]}")
    print(f"findings     = {result['finding_count']}")
    print("\nPer detector:")
    for row in result["per_detector"]:
        flag = ", ".join(row["entities_flagged"]) or "-"
        err = f"  ERROR {row['error']}" if row["error"] else ""
        print(
            f"  {row['detector_id']:4} v{row['version']:7} "
            f"{row['findings']:>3} findings  {row['seconds']:>6.2f}s  {flag}{err}"
        )


if __name__ == "__main__":
    main()
