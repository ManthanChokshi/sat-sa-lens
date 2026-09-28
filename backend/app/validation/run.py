"""Validation harness: detector findings versus the generator's ground truth.

How it scores
-------------
A planted problem is `(entity_id, expected_detector_id)`. It is **caught** when
the run produced at least one finding for that pair.

A finding is a **false positive** only when its `(entity_id, detector_id)` pair is
neither planted nor *acceptable* for that entity. Acceptable pairs exist because
one planted defect can legitimately trip more than one detector - copy-paste
notes have no artefacts either, so a D04 plant also trips D05. Those links are
declared by the generator itself (`acceptable_detector_ids`), never inferred
here. In addition, D14 (unsupervised outlier) is acceptable on any entity that
carries two or more planted problems: such an entity genuinely is an outlier.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.audit.runlog import latest_run
from app.config import GROUND_TRUTH_PATH
from app.db import fetch_dicts
from app.detectors.registry import implemented_detector_ids

#: detectors that may fire on any multi-problem entity without being a false positive
OUTLIER_DETECTORS = {"D14"}
OUTLIER_MIN_PROBLEMS = 2


def load_ground_truth(path: Optional[str] = None) -> dict[str, Any]:
    p = path or GROUND_TRUTH_PATH
    with open(p) as fh:
        return json.load(fh)


def validate(run_id: Optional[str] = None, path: Optional[str] = None) -> dict[str, Any]:
    gt = load_ground_truth(path)
    problems = gt["problems"]
    run = None
    if run_id is None:
        run = latest_run()
        run_id = run["run_id"] if run else None
    if run_id is None:
        return {"error": "No analysis run found. Run POST /api/runs first."}

    findings = fetch_dicts(
        "SELECT finding_id, entity_id, detector_id, severity, confidence, title, "
        "gap_type FROM findings WHERE run_id = ? ORDER BY detector_id, entity_id",
        [run_id],
    )
    implemented = set(implemented_detector_ids())

    planted_pairs: dict[tuple[str, str], list[dict]] = {}
    problems_per_entity: dict[str, int] = {}
    acceptable: dict[str, set[str]] = {}
    for p in problems:
        key = (p["entity_id"], p["expected_detector_id"])
        planted_pairs.setdefault(key, []).append(p)
        problems_per_entity[p["entity_id"]] = problems_per_entity.get(p["entity_id"], 0) + 1
        acc = acceptable.setdefault(p["entity_id"], set())
        acc.update(p.get("acceptable_detector_ids") or [])
    for entity_id, n in problems_per_entity.items():
        if n >= OUTLIER_MIN_PROBLEMS:
            acceptable.setdefault(entity_id, set()).update(OUTLIER_DETECTORS)

    found_pairs: dict[tuple[str, str], list[dict]] = {}
    for f in findings:
        found_pairs.setdefault((f["entity_id"], f["detector_id"]), []).append(f)

    detector_ids = sorted({d for _, d in planted_pairs} | {f["detector_id"] for f in findings})
    per_detector: list[dict[str, Any]] = []
    total_planted = total_caught = total_fp = 0

    for det in detector_ids:
        planted = [k for k in planted_pairs if k[1] == det]
        caught, missed = [], []
        for key in planted:
            if key in found_pairs:
                caught.append(key[0])
            else:
                missed.append(key[0])
        false_positives = []
        for key, fs in found_pairs.items():
            if key[1] != det or key in planted_pairs:
                continue
            if det in acceptable.get(key[0], set()):
                continue
            false_positives.append(key[0])
        recall = len(caught) / len(planted) if planted else None
        flagged = len(caught) + len(false_positives)
        precision = len(caught) / flagged if flagged else None
        per_detector.append(
            {
                "detector_id": det,
                "implemented": det in implemented,
                "planted": len(planted),
                "caught": len(caught),
                "missed": len(missed),
                "false_positives": len(false_positives),
                "recall": round(recall, 3) if recall is not None else None,
                "precision": round(precision, 3) if precision is not None else None,
                "caught_entities": sorted(caught),
                "missed_entities": sorted(missed),
                "false_positive_entities": sorted(false_positives),
                "findings_produced": sum(
                    1 for f in findings if f["detector_id"] == det
                ),
            }
        )
        if det in implemented:
            total_planted += len(planted)
            total_caught += len(caught)
            total_fp += len(false_positives)

    lookalikes = []
    for la in gt.get("innocent_lookalikes", []):
        flagged_by = sorted(
            {f["detector_id"] for f in findings if f["entity_id"] == la["entity_id"]}
        )
        lookalikes.append(
            {
                **la,
                "flagged_by": flagged_by,
                "correctly_not_flagged": len(flagged_by) == 0,
            }
        )
    healthy = []
    for entity_id in gt.get("healthy_entities", []):
        flagged_by = sorted(
            {f["detector_id"] for f in findings if f["entity_id"] == entity_id}
        )
        healthy.append(
            {
                "entity_id": entity_id,
                "flagged_by": flagged_by,
                "correctly_not_flagged": len(flagged_by) == 0,
            }
        )

    overall_recall = total_caught / total_planted if total_planted else 0.0
    overall_precision = (
        total_caught / (total_caught + total_fp) if (total_caught + total_fp) else 0.0
    )
    return {
        "run_id": run_id,
        "run": run,
        "generator_seed": gt.get("seed"),
        "planted_total": total_planted,
        "caught_total": total_caught,
        "missed_total": total_planted - total_caught,
        "false_positive_total": total_fp,
        "recall": round(overall_recall, 4),
        "precision": round(overall_precision, 4),
        "per_detector": per_detector,
        "innocent_lookalikes": lookalikes,
        "healthy_entities": healthy,
        "findings_total": len(findings),
        "implemented_detectors": sorted(implemented),
        "methodology": (
            "Validation compares the tool's findings against a synthetic corpus in "
            "which every weakness was planted deliberately, so the correct answer is "
            "known exactly. This mirrors how an NCIIPC expert reviews a sample by hand "
            "and then checks whether the tool reached the same conclusion. Recall is "
            "the share of planted weaknesses that were detected. Precision counts a "
            "finding as wrong only when it is not planted for that organisation and is "
            "not a documented knock-on effect of a planted weakness. Two 'innocent "
            "look-alike' organisations are included specifically to prove the tool does "
            "not flag fast-but-automated closures or genuinely small estates."
        ),
    }


def print_report(result: dict[str, Any]) -> None:
    if "error" in result:
        print(result["error"])
        return
    hdr = (
        f"{'det':5} {'planted':>8} {'caught':>7} {'missed':>7} {'FP':>4} "
        f"{'recall':>7} {'precision':>10}  notes"
    )
    print("=" * 96)
    print(f"SAT-SA Lens validation - run {result['run_id']}")
    print("=" * 96)
    print(hdr)
    print("-" * 96)
    for row in result["per_detector"]:
        rec = "-" if row["recall"] is None else f"{row['recall'] * 100:.0f}%"
        pre = "-" if row["precision"] is None else f"{row['precision'] * 100:.0f}%"
        note = ""
        if row["missed_entities"]:
            note += f"missed: {', '.join(row['missed_entities'])} "
        if row["false_positive_entities"]:
            note += f"FP: {', '.join(row['false_positive_entities'])}"
        print(
            f"{row['detector_id']:5} {row['planted']:>8} {row['caught']:>7} "
            f"{row['missed']:>7} {row['false_positives']:>4} {rec:>7} {pre:>10}  {note}"
        )
    print("-" * 96)
    print(
        f"PLANTED {result['planted_total']}, CAUGHT {result['caught_total']} "
        f"({result['recall'] * 100:.1f}% recall), "
        f"precision {result['precision'] * 100:.1f}%, "
        f"false positives {result['false_positive_total']}"
    )
    print("\nInnocent look-alikes (these must NOT be flagged):")
    for la in result["innocent_lookalikes"]:
        mark = "OK " if la["correctly_not_flagged"] else "FLAGGED"
        print(f"  [{mark}] {la['entity_id']} {la['name']}: {la['flagged_by'] or 'no findings'}")
    print("\nHealthy entities (these should be clean):")
    for h in result["healthy_entities"]:
        mark = "OK " if h["correctly_not_flagged"] else "FLAGGED"
        print(f"  [{mark}] {h['entity_id']}: {h['flagged_by'] or 'no findings'}")


def main() -> None:
    print_report(validate())


if __name__ == "__main__":
    main()
