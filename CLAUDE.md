# SAT-SA Lens — Supervisory Analytics Tool for SOC Assessment

Smart India Hackathon 2026 — Problem Statement **SIH26157** (NTRO / NCIIPC).

## What this project is

An **offline web application** for NCIIPC supervisors (the cyber-security auditors of India's critical-sector organisations: power, banking, telecom, oil & gas, etc.).

Each organisation (a "CSE" — Critical Sector Entity) runs a Security Operations Centre (SOC). Periodically, CSEs submit their SOC records: alerts, case-management records, escalations, and asset inventory. Today NCIIPC experts review samples of these by hand. This tool does the first pass automatically and tells the supervisor **which organisations, processes and alert samples need human review, and why**.

It detects two kinds of weakness:

- **Execution gaps** — the organisation claims/looks effective, but the operational evidence says otherwise (critical alerts closed in seconds, no escalation, copy-paste investigation notes, metric gaming).
- **Negative space** — evidence that *should* exist is missing (critical assets producing no alerts, alert categories every peer has but this one doesn't, sudden drops in activity, cases with no escalation records).

The tool **supports** human supervisors. It never gives a final verdict — every finding is a *hypothesis* with a reason, a confidence level, a possible innocent explanation, and the exact evidence rows.

It is **not** a SOC, not a SIEM, not real-time monitoring, and does not collect logs continuously. It analyses periodic submissions.

## HARD RULES (never break these)

1. **Fully offline.** The running app must work with no internet connection. No calls to OpenAI, Anthropic, Hugging Face, or any external API at runtime. No CDN links in the frontend (no Google Fonts, no unpkg/jsdelivr scripts). All models and fonts are bundled in the repo/image.
2. **Every finding is explainable.** A finding must always include: `rationale` (plain English), `metrics` (the numbers behind it), `evidence_row_ids` (the exact records), `confidence`, and `innocent_explanation`. A score with no reason is a bug.
3. **Reproducible.** Same input data + same code version → identical results. Every analysis run records `run_id`, code/rule version, input data hash, and timestamp. Use fixed random seeds.
4. **Human in control.** Findings have a status (`open` / `valid` / `not_valid`) that only a supervisor changes. Never auto-conclude that an entity "failed".
5. **Minimise sensitive data.** Pseudonymise analyst names, usernames and IP addresses on ingest (stable salted hash). Never display raw personal identifiers in the UI.
6. **Fair comparison.** Compare entities only within peer groups (sector + size tier), normalise by assets/analysts/alert volume, and don't flag entities on tiny sample sizes (require a minimum count and show confidence).
7. **Don't break validation.** After changing any detector, run the validation harness (`pytest` + `python -m app.validation.run`) and report whether recall/precision went up or down.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Data engine | DuckDB (single file `data/satsa.duckdb`), pandas for small transforms |
| ML | scikit-learn (IsolationForest), sentence-transformers `all-MiniLM-L6-v2` loaded from local folder `models/all-MiniLM-L6-v2` (downloaded once by `scripts/download_model.py`, then never fetched again) |
| PDF | reportlab |
| Frontend | React 18 + Vite + TypeScript, Tailwind CSS, Recharts, React Router, TanStack Table. Fonts bundled locally. |
| Tests | pytest (backend), vitest optional (frontend) |
| Packaging | Docker Compose (backend + frontend served by nginx), must run with network disabled |

## Repository layout

```
sat-sa-lens/
├── CLAUDE.md
├── docs/                    # BUILD_GUIDE.md, ARCHITECTURE.md, DEMO_SCRIPT.md
├── generator/               # synthetic data generator
│   ├── generate.py          # entry point: python -m generator.generate --seed 42
│   ├── entities.py          # entity profiles (healthy + faulty)
│   └── faults.py            # planted-problem injectors, each writes to ground truth
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + routers
│   │   ├── db.py            # DuckDB connection + schema creation
│   │   ├── schema.py        # Pydantic models (canonical schema, Finding)
│   │   ├── ingest/          # upload, column mapping, normalisation, pseudonymisation, integrity checks
│   │   ├── detectors/       # one file per detector, all registered in registry.py
│   │   ├── scoring/         # peer groups, capability scorecard, entity risk score
│   │   ├── sampling/        # review-sample picker
│   │   ├── audit/           # run log, hashes
│   │   ├── reports/         # PDF evidence packs
│   │   └── validation/      # compares findings vs generator ground truth
│   └── tests/
├── frontend/
├── models/                  # bundled ML model (git-ignored if large; downloaded by script)
├── data/                    # generated data + duckdb file (git-ignored)
├── scripts/
└── docker-compose.yml
```

## Canonical data schema (all ingested data is converted into this)

- **entities**: `entity_id, name, sector (power|banking|telecom|oil_gas|transport), size_tier (small|medium|large), analyst_count`
- **commitments** (what the entity *claims*): `entity_id, metric, threshold, unit` — e.g. `critical_escalation_minutes, 15, minutes`; `critical_asset_monitoring_coverage, 100, percent`; `high_alert_investigation_minutes, 30, minutes`
- **assets**: `asset_id, entity_id, hostname, ip_pseudo, asset_type (server|db|workstation|network|ot|cloud), criticality (critical|high|medium|low), environment (prod|dev|ot)`
- **alerts**: `alert_id, entity_id, asset_id, rule_name, category (MITRE-style tactic: initial_access|execution|persistence|privilege_escalation|defense_evasion|credential_access|discovery|lateral_movement|collection|exfiltration|command_and_control|impact|phishing|malware|policy_violation), severity (critical|high|medium|low|info), source (edr|siem|ids|email_gateway|firewall|ot_monitor), created_at`
- **cases**: `case_id, entity_id, alert_id, analyst_pseudo, opened_at, closed_at, disposition (true_positive|false_positive|benign|duplicate|unresolved), closure_type (manual|automated), notes`
- **escalations**: `escalation_id, case_id, entity_id, from_tier, to_tier, escalated_at, reason`
- **submissions**: `submission_id, entity_id, period_start, period_end, declared_alert_count, file_hash, uploaded_at, integrity_status`

Severity normalisation map (extend as needed): `P1|Sev1|5|crit|Critical → critical`, `P2|Sev2|4|High → high`, `P3|3|Medium → medium`, `P4|2|Low → low`, `P5|1|Info → info`.

## Finding object (output of every detector)

```
finding_id, run_id, entity_id, detector_id, detector_version,
gap_type (execution_gap | negative_space | anomaly | data_quality),
capability_area (threat_detection | investigation | escalation | incident_response |
                 security_operations | governance_oversight | operational_discipline | cyber_resilience),
severity (high | medium | low), confidence (0.0–1.0),
title, rationale, innocent_explanation,
metrics (JSON: the numbers, incl. peer baseline), evidence_row_ids (list), evidence_table,
status (open | valid | not_valid), supervisor_note, created_at
```

## Detectors (IDs are stable — reference them everywhere)

Execution gaps:
- **D01 fast_critical_closure** — critical/high alerts closed faster than threshold or far faster than peer median (manual closures only; automated closures reported separately).
- **D02 critical_no_escalation** — critical alerts closed without an escalation record.
- **D03 commitment_breach** — actual performance vs the entity's own declared commitments.
- **D04 template_notes** — near-duplicate investigation notes (embedding cosine similarity clusters).
- **D05 shallow_investigation** — notes lacking any concrete artefact (IP, hash, host, user, action taken).
- **D06 recurring_unremediated** — same rule firing repeatedly on the same asset, repeatedly closed, never escalated/remediated.
- **D07 effort_severity_mismatch** — investigation time does not increase with severity (flat/inverted relationship).
- **D08 threshold_gaming** — abnormal pile-up of closures just inside an SLA threshold.
- **D09 analyst_workload_implausible** — per-analyst closures per shift that are not humanly plausible.

Negative space:
- **D10 silent_critical_assets** — critical assets with zero/near-zero alerts in the period.
- **D11 missing_alert_categories** — categories common in the peer group (>= 80% of peers) absent for this entity.
- **D12 volume_drop** — sudden drop vs the entity's own historical baseline.
- **D13 broken_chain** — cases with no alert, escalations with no case, true-positives with no escalation.

Anomaly / unknown patterns:
- **D14 entity_anomaly** — IsolationForest on per-entity feature vectors; report top contributing features as rationale.

Data quality (on ingest):
- **Q01 id_gaps**, **Q02 time_gaps**, **Q03 declared_count_mismatch**, **Q04 timestamp_regularity**, **Q05 file_hash_recorded**.

## Scoring

- Peer group = sector + size_tier. Rates normalised per asset / per analyst / per 1,000 alerts.
- Small-sample protection: minimum N per metric; use Wilson intervals / empirical-Bayes shrinkage toward peer mean.
- Capability scorecard: each detector maps to one capability area → 0–100 score per area per entity (radar chart).
- Entity risk score = weighted sum of finding severity × confidence, shown with the top 3 contributing findings.

## Review-sample picker

For a chosen entity: return N alert/case records to review — 70% highest-risk (from findings evidence), 30% uniform random (seeded) — and report coverage.

## Validation

`generator` writes `data/ground_truth.json` listing every planted problem (`entity_id, detector_id expected, description, evidence ids`). `app.validation.run` compares findings to ground truth and prints per-detector recall, precision, and an overall "planted X, caught Y" number. The UI Validation page shows the same.

## Commands

- Generate data: `python -m generator.generate --seed 42 --entities 10 --days 90`
- Backend: `cd backend && uvicorn app.main:app --reload --port 8000`
- Tests: `cd backend && pytest -q`
- Validation: `cd backend && python -m app.validation.run`
- Frontend: `cd frontend && npm run dev`
- Full offline stack: `docker compose up --build`

## Working conventions

- Build one phase at a time; don't start the next phase until the current one runs and tests pass.
- Each detector lives in its own file, has a unit test using a tiny hand-made dataset, and returns `list[Finding]`.
- Keep functions small and typed. Prefer DuckDB SQL for aggregations over Python loops.
- Plain-English rationales written for a non-technical supervisor, e.g. "78% of this entity's critical alerts (143 of 183) were closed manually in under 2 minutes. Peer median: 11%."
- After finishing a phase, update the "Progress" section below.

## Progress

- [x] Phase 1 — Scaffold
- [x] Phase 2 — Synthetic data generator + ground truth
- [x] Phase 3 — Database + ingest of generator data
- [x] Phase 4 — Detector framework + D01, D02, D10, D11 + validation harness
- [x] Phase 5 — Scoring + API
- [x] Phase 6 — Frontend: overview + entity page
- [x] Phase 7 — Remaining detectors D03–D09, D12–D14
- [x] Phase 8 — Finding drill-down, negative-space view, supervisor feedback
- [x] Phase 9 — Upload of foreign formats: column mapping + integrity checks
- [x] Phase 10 — Review-sample picker, audit log, PDF export
- [x] Phase 11 — Validation page
- [x] Phase 12 — Offline Docker packaging + Wi-Fi-off test
- [x] Phase 13 — Polish, README, architecture doc, demo script

### Current state (seed 42, 12 entities, 90 days)

- 186,548 alerts / 173,666 cases / 3,629 assets across 12 organisations
- 19 detectors implemented (D01–D14, Q01–Q05), 37 findings on the reference corpus
- Validation: **planted 28, caught 28 — 100% recall, 100% precision, 0 false positives**
- Both innocent look-alikes and all three healthy organisations: correctly not flagged
- Backend tests: 62 passing (`pytest -q`); frontend: 7 passing (`npm test`)
- Air-gap verified: `docker-compose.offline.yml` leaves the backend with no route
  off the host; outbound connections fail with `Network is unreachable`
