"""HTTP API. Thin layer over app.services, app.runner and app.ingest."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from app import __version__
from app.audit.runlog import list_actions, list_runs, latest_run, log_action
from app.config import RULES_VERSION
from app.db import fetch_one, locked, table_counts
from app.detectors.registry import catalogue
from app.ingest.loader import load_sample
from app.ingest.mapping import load_mapping, save_mapping
from app.ingest.upload import commit_upload, quality_report, stage_upload
from app.reports.pdf import build_entity_report
from app.runner import run_analysis
from app.sampling.picker import generate_sample, sample_csv, sample_rows
from app.schema import FindingUpdate
from app.services import (
    entity_detail,
    entity_rows,
    finding_detail,
    finding_evidence,
    findings,
    invalidate_scores,
    methodology,
    negative_space,
    overview,
    stats,
)
from app.validation.run import validate

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------- health/meta
@router.get("/health")
def health() -> dict[str, Any]:
    try:
        counts = table_counts()
        db_ok = True
    except Exception as exc:  # pragma: no cover
        counts, db_ok = {"error": str(exc)}, False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "sat-sa-lens-backend",
        "version": __version__,
        "rules_version": RULES_VERSION,
        "database": "duckdb",
        "offline": True,
        "row_counts": counts,
    }


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    return stats()


@router.get("/methodology")
def get_methodology() -> dict[str, Any]:
    return methodology()


@router.get("/detectors")
def get_detectors() -> list[dict[str, Any]]:
    return catalogue()


# ---------------------------------------------------------------------- entities
@router.get("/entities")
def get_entities() -> list[dict[str, Any]]:
    return entity_rows()


@router.get("/overview")
def get_overview() -> dict[str, Any]:
    return overview()


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str) -> dict[str, Any]:
    detail = entity_detail(entity_id)
    if not detail:
        raise HTTPException(404, f"Unknown entity {entity_id}")
    return detail


@router.get("/entities/{entity_id}/negative-space")
def get_negative_space(entity_id: str) -> dict[str, Any]:
    if not fetch_one("SELECT 1 AS x FROM entities WHERE entity_id = ?", [entity_id]):
        raise HTTPException(404, f"Unknown entity {entity_id}")
    return negative_space(entity_id)


@router.get("/entities/{entity_id}/report.pdf")
def get_entity_report(entity_id: str) -> Response:
    try:
        pdf = build_entity_report(entity_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    log_action("supervisor", "export_pdf", "entity", entity_id, "evidence pack downloaded")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="satsa-{entity_id}-evidence-pack.pdf"'
        },
    )


# ----------------------------------------------------------------------- runs
class RunRequest(BaseModel):
    only: Optional[list[str]] = None
    notes: str = ""
    actor: str = "supervisor"


@router.post("/runs")
def post_run(body: RunRequest | None = None) -> dict[str, Any]:
    body = body or RunRequest()
    if not fetch_one("SELECT COUNT(*) AS n FROM entities")["n"]:
        raise HTTPException(
            400, "No data loaded. POST /api/ingest/sample first, or upload a submission."
        )
    return run_analysis(only=body.only, actor=body.actor, notes=body.notes)


@router.get("/runs")
def get_runs(limit: int = 50) -> list[dict[str, Any]]:
    return list_runs(limit)


@router.get("/runs/latest")
def get_latest_run() -> dict[str, Any]:
    run = latest_run()
    if not run:
        raise HTTPException(404, "No analysis run yet")
    return run


@router.get("/audit")
def get_audit(limit: int = 200) -> dict[str, Any]:
    return {"runs": list_runs(limit), "actions": list_actions(limit)}


# -------------------------------------------------------------------- findings
@router.get("/findings")
def get_findings(
    entity_id: Optional[str] = None,
    detector_id: Optional[str] = None,
    gap_type: Optional[str] = None,
    status: Optional[str] = None,
    capability_area: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = Query(500, le=10_000),
) -> list[dict[str, Any]]:
    return findings(
        run_id=run_id,
        entity_id=entity_id,
        detector_id=detector_id,
        gap_type=gap_type,
        status=status,
        capability_area=capability_area,
        limit=limit,
    )


@router.get("/findings/{finding_id}")
def get_finding(finding_id: str) -> dict[str, Any]:
    f = finding_detail(finding_id)
    if not f:
        raise HTTPException(404, f"Unknown finding {finding_id}")
    return f


@router.get("/findings/{finding_id}/evidence")
def get_finding_evidence(
    finding_id: str,
    limit: int = Query(100, le=2000),
    offset: int = 0,
) -> dict[str, Any]:
    result = finding_evidence(finding_id, limit=limit, offset=offset)
    if result.get("error"):
        raise HTTPException(404, f"Unknown finding {finding_id}")
    return result


@router.patch("/findings/{finding_id}")
def patch_finding(finding_id: str, body: FindingUpdate) -> dict[str, Any]:
    current = fetch_one(
        "SELECT run_id, status, supervisor_note FROM findings WHERE finding_id = ?",
        [finding_id],
    )
    if not current:
        raise HTTPException(404, f"Unknown finding {finding_id}")
    status = body.status or current["status"]
    note = current["supervisor_note"] if body.supervisor_note is None else body.supervisor_note
    with locked() as conn:
        conn.execute(
            "UPDATE findings SET status = ?, supervisor_note = ? WHERE finding_id = ?",
            [status, note, finding_id],
        )
    log_action(
        body.actor,
        "finding_status_change",
        "finding",
        finding_id,
        f"{current['status']} -> {status}" + (f"; note: {note}" if note else ""),
    )
    invalidate_scores(current["run_id"])
    return finding_detail(finding_id) or {}


# --------------------------------------------------------------------- sampling
class SampleRequest(BaseModel):
    size: int = Field(50, ge=5, le=500)
    seed: int = 42


@router.post("/entities/{entity_id}/review-sample")
def post_review_sample(entity_id: str, body: SampleRequest | None = None) -> dict[str, Any]:
    body = body or SampleRequest()
    result = generate_sample(entity_id, size=body.size, seed=body.seed)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    log_action(
        "supervisor", "review_sample", "entity", entity_id,
        f"sample {result['sample_id']} size={result['actual_size']} seed={body.seed}",
    )
    return result


@router.get("/samples/{sample_id}")
def get_sample(sample_id: str) -> dict[str, Any]:
    rows = sample_rows(sample_id)
    if not rows:
        raise HTTPException(404, f"Unknown sample {sample_id}")
    return {"sample_id": sample_id, "rows": rows}


@router.get("/samples/{sample_id}/export.csv", response_class=PlainTextResponse)
def get_sample_csv(sample_id: str) -> Response:
    csv_text = sample_csv(sample_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{sample_id}.csv"'},
    )


# ----------------------------------------------------------------------- ingest
@router.post("/ingest/sample")
def post_ingest_sample() -> dict[str, Any]:
    try:
        result = load_sample()
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    log_action(
        "supervisor", "ingest_sample", "dataset", "data/raw",
        f"data_hash={result['data_hash'][:16]}",
    )
    return result


@router.post("/upload/stage")
async def post_upload_stage(
    entity_id: str = Form(...),
    table_type: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    try:
        return stage_upload(entity_id, table_type, file.filename or "upload.csv", content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class CommitRequest(BaseModel):
    mapping: dict[str, Optional[str]]
    value_map: dict[str, Any] = Field(default_factory=dict)
    remember_mapping: bool = True
    actor: str = "supervisor"


@router.post("/upload/{upload_id}/commit")
def post_upload_commit(upload_id: str, body: CommitRequest) -> dict[str, Any]:
    try:
        return commit_upload(
            upload_id,
            mapping=body.mapping,
            value_map=body.value_map,
            remember_mapping=body.remember_mapping,
            actor=body.actor,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/upload/mapping")
def get_saved_mapping(entity_id: str, table_type: str) -> dict[str, Any]:
    saved = load_mapping(entity_id, table_type)
    return saved or {"entity_id": entity_id, "table_type": table_type, "mapping": None}


class MappingRequest(BaseModel):
    entity_id: str
    table_type: str
    mapping: dict[str, Optional[str]]
    value_map: dict[str, Any] = Field(default_factory=dict)


@router.post("/upload/mapping")
def post_saved_mapping(body: MappingRequest) -> dict[str, Any]:
    mapping_id = save_mapping(body.entity_id, body.table_type, body.mapping, body.value_map)
    return {"mapping_id": mapping_id}


@router.get("/entities/{entity_id}/quality")
def get_quality(entity_id: str) -> dict[str, Any]:
    return quality_report(entity_id)


# ------------------------------------------------------------------- validation
@router.get("/validation")
def get_validation(run_id: Optional[str] = None) -> dict[str, Any]:
    result = validate(run_id)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result
