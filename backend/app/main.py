"""FastAPI application entry point.

Fully offline: the app binds locally, talks only to a DuckDB file on disk and a
bundled model folder, and never issues an outbound request.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.db import get_conn
from app.runner import create_views

logging.basicConfig(
    level=os.environ.get("SATSA_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
)
log = logging.getLogger("satsa")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_conn()  # creates the schema on first start
    create_views()
    log.info("SAT-SA Lens backend %s ready (offline mode)", __version__)
    if os.environ.get("SATSA_AUTO_BOOTSTRAP") == "1":
        _bootstrap()
    yield


def _bootstrap() -> None:
    """First-run convenience for the packaged container: generate, ingest, analyse.

    Each step is guarded separately so an interrupted first start (a container
    stopped mid-analysis, say) is repaired on the next start rather than leaving
    the app with data but no findings.
    """
    from app.db import fetch_one

    try:
        from app.config import RAW_DIR
        from app.ingest.loader import load_sample
        from app.runner import run_analysis

        entities = (fetch_one("SELECT COUNT(*) AS n FROM entities") or {}).get("n", 0)
        if not entities:
            if not (RAW_DIR / "alerts.csv").exists():
                log.info("Generating sample corpus (seed 42)...")
                from generator.generate import generate

                generate(seed=42, n_entities=12, days=90, out_dir=RAW_DIR)
            log.info("Ingesting sample corpus...")
            load_sample()
        else:
            log.info("Database already holds %s organisations", entities)

        complete = (
            fetch_one("SELECT COUNT(*) AS n FROM runs WHERE status = 'complete'") or {}
        ).get("n", 0)
        if complete:
            log.info("%s completed analysis run(s) already present", complete)
            return
        log.info("Running first analysis...")
        result = run_analysis(actor="system", notes="first-start bootstrap")
        log.info("Bootstrap complete: %s findings", result["finding_count"])
    except Exception as exc:  # pragma: no cover - never block startup
        log.warning("Bootstrap skipped: %s", exc)


app = FastAPI(
    title="SAT-SA Lens",
    description=(
        "Supervisory Analytics Tool for SOC Assessment (SIH26157). Offline-only "
        "first-pass review of Critical Sector Entity SOC submissions."
    ),
    version=__version__,
    lifespan=lifespan,
)

# The frontend is served from the same host in production; these origins only
# cover the local Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "SAT-SA Lens",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
    }
