# SAT-SA Lens — Step-by-step build guide (Claude Code)

Follow the steps in order. Each phase has:
- **Prompt**: copy it into Claude Code exactly
- **Check**: what you should see before moving on
- **Commit**: save your progress

Rules that apply to every phase:
- **Start each phase fresh:** type `/clear` in Claude Code before pasting the next phase's prompt. CLAUDE.md is re-read automatically, so nothing is lost and the context stays clean.
- **Plan first, then build:** switch Claude Code to plan mode (Shift+Tab until it says "plan mode") and paste the prompt. Read the plan. If it looks right, approve it and let it build.
- **Don't skip a Check.** If something fails, use the fix prompt at the bottom of this guide.

---

## Step 0 — Install tools (one time)

Install these if you don't have them:

| Tool | Check it works |
|---|---|
| Python 3.11+ | `python --version` |
| Node.js 20+ | `node --version` |
| Git | `git --version` |
| Docker Desktop (needed at Phase 12) | `docker --version` |
| Claude Code | `claude --version` |

## Step 1 — Create the project folder on your Desktop

**Windows (PowerShell):**
```powershell
cd $HOME\Desktop
mkdir sat-sa-lens
cd sat-sa-lens
mkdir docs
git init
```

**Mac / Linux (Terminal):**
```bash
cd ~/Desktop
mkdir sat-sa-lens
cd sat-sa-lens
mkdir docs
git init
```

Now copy the two files into the folder:
- `CLAUDE.md` goes to `sat-sa-lens/CLAUDE.md` (the project root)
- `BUILD_GUIDE.md` goes to `sat-sa-lens/docs/BUILD_GUIDE.md`

Then start Claude Code inside the folder:
```bash
claude
```

First prompt, to confirm it read the file:
```
Read CLAUDE.md and summarise in 5 bullet points what we are building and the hard rules. Don't write any code yet.
```
If its summary mentions: offline, explainable findings, execution gaps + negative space, and the detector list, you're set.

---

## Phase 1 — Scaffold the project

**Prompt:**
```
Phase 1 from CLAUDE.md: scaffold the repository exactly as in the "Repository layout" section.
- backend: FastAPI app with a /api/health endpoint, requirements.txt (fastapi, uvicorn, duckdb, pandas, scikit-learn, sentence-transformers, reportlab, pydantic, pytest, python-multipart, faker), a pytest that calls /api/health.
- frontend: Vite + React + TypeScript + Tailwind + React Router + Recharts + TanStack Table. One placeholder page that calls /api/health through a Vite proxy and shows "Backend: OK". No CDN links, no Google Fonts.
- .gitignore (data/, models/, node_modules, venv, __pycache__, *.duckdb)
- scripts/dev.sh and scripts/dev.ps1 that start backend and frontend together.
- A short README with setup commands.
Create a Python virtual environment in backend/.venv and install everything. Run the test. Tell me the exact commands I use to start both servers.
```

**Check:** open http://localhost:5173 in your browser and it shows "Backend: OK". `pytest` passes.

**Commit:**
```
Commit everything with message "Phase 1: scaffold". Tick Phase 1 in CLAUDE.md Progress.
```

---

## Phase 2 — Fake-data generator with planted problems

This is the most important phase. Every later part is tested against this data.

**Prompt:**
```
Phase 2 from CLAUDE.md: build the synthetic data generator in generator/.

Requirements:
1. `python -m generator.generate --seed 42 --entities 10 --days 90` writes CSVs for every table in the canonical schema to data/raw/ plus data/ground_truth.json. Fully deterministic for a given seed.
2. 10 entities across sectors power, banking, telecom, oil_gas with small/medium/large tiers (at least 2 entities per sector so peer comparison works). Realistic volumes: 50–600 assets, 3–40 analysts, 2k–60k alerts over 90 days, realistic daily/weekly patterns (more alerts on weekdays, night-shift dips).
3. Realistic alert rule names per category (e.g. "Suspicious PowerShell EncodedCommand", "Multiple failed logins – RDP", "Phishing URL clicked"), severity distributions, and realistic investigation notes for healthy analysts (varied text that mentions IPs, hosts, hashes, users, actions taken). Use faker with a fixed seed.
4. Healthy entities: reasonable closure times that grow with severity, critical alerts escalated, varied notes, every critical asset produces some telemetry, ~10–20% automated closures of low/info alerts.
5. Faulty entities get planted problems from faults.py — one injector function per detector in CLAUDE.md (D01–D14 where it makes sense, plus Q01–Q04). Distribute 3–6 problems per faulty entity; keep 3 entities fully healthy. Examples: fast manual closure of criticals (D01), criticals with no escalation (D02), declared commitment "escalate in 15 min" but actual median 3 hours (D03), 90% copy-paste notes like "checked, false positive" (D04), notes with no artefacts (D05), same rule on same asset every day closed each time (D06), flat effort across severities (D07), closures piling up at 28–29 min when SLA is 30 (D08), one analyst closing 400 alerts per shift (D09), critical DB servers with zero alerts (D10), a bank with no phishing alerts (D11), alert volume falling 80% in the last month (D12), true-positives with no escalation (D13), missing alert ID ranges (Q01), a missing week of data (Q02).
6. Also plant 2 "innocent look-alikes" that should NOT be flagged as bad: an entity whose fast closures are all closure_type=automated on info alerts, and a small entity with very few alerts.
7. ground_truth.json: list of {problem_id, entity_id, expected_detector_id, description, evidence ids or selector}.
8. Print a summary table at the end: entities, sectors, row counts per table, planted problems per entity.
Add pytest tests: determinism (same seed = same output hash) and that every planted problem appears in ground truth.
```

**Check:** run the generator. You should see a summary table with 10 entities and a list of planted problems. Open a CSV in Excel and it should look like real data.

**Commit:**
```
Commit with message "Phase 2: synthetic data generator with ground truth". Tick Phase 2.
```

---

## Phase 3 — Database and data loading

**Prompt:**
```
Phase 3 from CLAUDE.md: database and ingest of canonical data.
- backend/app/db.py: create all canonical tables in DuckDB (data/satsa.duckdb) with proper types.
- backend/app/ingest/: a loader that imports the generator's CSVs from data/raw/, pseudonymises analyst names, usernames and IPs with a stable salted hash (salt from env var, default for dev), records each file's SHA-256 in the submissions table, and is idempotent (re-running doesn't duplicate rows).
- API: POST /api/ingest/sample (loads data/raw), GET /api/entities (list with row counts), GET /api/stats.
- CLI: python -m app.ingest.load_sample
- pytest: row counts match CSVs, no raw analyst names or IPs remain in the database, idempotency.
```

**Check:** http://localhost:8000/api/entities lists 10 entities with row counts. `pytest` passes.

**Commit:**
```
Commit "Phase 3: database and ingest". Tick Phase 3.
```

---

## Phase 4 — Detector framework, first 4 detectors, validation

**Prompt:**
```
Phase 4 from CLAUDE.md.
1. Build the detector framework: base Detector class (id, version, gap_type, capability_area, run(conn, run_id) -> list[Finding]), a registry, and an analysis runner that creates a run_id, records run metadata (code version from git, data hash, timestamp, seeds) in an audit table, runs all registered detectors, and stores findings in a findings table.
2. Implement D01 fast_critical_closure, D02 critical_no_escalation, D10 silent_critical_assets, D11 missing_alert_categories exactly as described in CLAUDE.md. Use DuckDB SQL. Compare against peer group (sector + size_tier) medians. Respect small-sample protection. Every finding must fill rationale (plain English with numbers and peer baseline), metrics, evidence_row_ids, confidence and innocent_explanation. D01 must exclude automated closures and mention them in the innocent_explanation.
3. Build app/validation/run.py: match findings to ground_truth.json (by entity + detector), print a table per detector with planted / caught / missed / false positives, recall and precision, and an overall "Planted X, caught Y" line. Only count detectors that are implemented.
4. API: POST /api/runs (run analysis), GET /api/runs/latest, GET /api/findings?entity_id=&detector_id=.
5. Unit test for each detector with a tiny hand-made dataset, including one case that must NOT be flagged.
Run the analysis and the validation and show me the results table.
```

**Check:** validation prints something like "D01: planted 2, caught 2". The "innocent look-alike" entity should NOT be flagged. If recall is low, use the tuning prompt below.

**Tuning prompt (use whenever a detector misses or over-flags):**
```
Validation shows detector <ID> has recall <x> / precision <y>. Look at the missed and false-positive cases, explain in simple words why each happened, then fix the detector logic (not the ground truth). Re-run validation and show before/after.
```

**Commit:**
```
Commit "Phase 4: detector framework, D01 D02 D10 D11, validation". Tick Phase 4.
```

---

## Phase 5 — Scoring and API

**Prompt:**
```
Phase 5 from CLAUDE.md: scoring.
- Capability scorecard: map each detector to its capability area, compute a 0–100 score per area per entity (100 = no concerns), explainable (list which findings reduced it).
- Entity risk score: weighted sum of severity x confidence of open findings, normalised 0–100, with risk band (High/Medium/Low) and top 3 contributing findings.
- Trend: compute the same scores per 30-day window so we can show trend arrows.
- API: GET /api/overview (all entities ranked by risk with band, sector, score, finding counts by gap_type, 8 capability scores, trend), GET /api/entities/{id} (entity detail: scores, radar data, findings grouped by capability area, timeline data of alerts per day).
- Tests for score monotonicity (more/higher findings -> higher risk) and that healthy entities score low risk.
```

**Check:** http://localhost:8000/api/overview returns faulty entities at the top and healthy ones at the bottom.

**Commit:**
```
Commit "Phase 5: scoring and API". Tick Phase 5.
```

---

## Phase 6 — Dashboard: overview and organisation pages

**Prompt:**
```
Phase 6 from CLAUDE.md: frontend.
Design: clean, serious government-analytics look. Dark navy sidebar, light content area, one accent colour, red/amber/green only for risk bands. Bundled local font (e.g. Inter via @fontsource), no CDN.
Pages:
1. Layout with sidebar: Overview, Entities, Negative Space, Upload, Validation, Audit Log. Header shows latest run id + time and a "Run analysis" button (POST /api/runs).
2. Overview: KPI tiles (entities assessed, high-risk entities, open findings, execution gaps vs negative space); ranked table of entities (name, sector, tier, risk score with band chip, trend arrow, finding counts); heatmap of 8 capability areas x entities (Recharts or a CSS grid).
3. Entity page (/entities/:id): header with risk score + top 3 reasons in plain English; radar chart of 8 capability scores vs peer average; alerts-per-day timeline; findings list grouped by capability area showing title, severity, confidence, gap type chip.
Handle loading and empty states. Make "Run analysis" refresh the data.
```

**Check:** the whole flow works in the browser: Overview → click an organisation → radar chart + findings. **This is your first demo-able version.** Record a quick screen video as a backup.

**Commit:**
```
Commit "Phase 6: overview and entity dashboard". Tick Phase 6.
```

---

## Phase 7 — Remaining detectors

Do these in 3 batches. Use `/clear` between batches.

**Prompt A:**
```
Phase 7a from CLAUDE.md: implement D03 commitment_breach, D06 recurring_unremediated, D07 effort_severity_mismatch, D08 threshold_gaming, D09 analyst_workload_implausible. Same quality bar as D01: SQL-based, peer baselines, small-sample protection, full explainability fields, a unit test each including a must-not-flag case. Re-run analysis and validation and show the before/after table.
```

**Prompt B:**
```
Phase 7b: implement D04 template_notes and D05 shallow_investigation.
- Add scripts/download_model.py that downloads sentence-transformers all-MiniLM-L6-v2 once into models/all-MiniLM-L6-v2. The app must load ONLY from that local path, with HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 set, and fail with a clear message if the model folder is missing.
- D04: embed notes per entity (sample up to 5k for speed, seeded), cluster near-duplicates (cosine > 0.92), flag entities where a large share of notes fall in a few clusters; evidence = example notes + case ids.
- D05: regex/heuristic artefact extraction (IPv4, hash, hostname, username, action verbs like blocked/isolated/reset/escalated); flag entities with a high share of notes containing no artefact vs peers.
Tests + re-run validation.
```

**Prompt C:**
```
Phase 7c: implement D12 volume_drop, D13 broken_chain, D14 entity_anomaly.
- D14: build a per-entity feature vector (normalised rates from the other detectors' metrics and basic stats), IsolationForest with fixed seed, and explain each anomalous entity with the top 3 features that deviate most from peers (z-scores) in plain English.
Tests + re-run validation. Then show me the full validation table for all detectors and the overall "Planted X, caught Y".
```

**Check:** overall recall is 85% or higher, and the innocent look-alikes are not flagged. If not, use the tuning prompt.

**Commit:**
```
Commit "Phase 7: all detectors". Tick Phase 7.
```

---

## Phase 8 — Finding details, negative-space view, supervisor feedback

**Prompt:**
```
Phase 8 from CLAUDE.md.
1. Finding page (/findings/:id): title, gap type, capability area, severity, confidence bar, plain-English rationale, "Possible innocent explanation" box, metrics shown as small stat cards incl. peer baseline, and an evidence table (TanStack Table, paginated, sortable) loaded from GET /api/findings/{id}/evidence which returns the exact rows from evidence_table filtered by evidence_row_ids.
2. Supervisor feedback: buttons "Valid", "Not valid", and a note field -> PATCH /api/findings/{id}. Store who/when in the audit log. Risk scores should only count open + valid findings (not_valid excluded) and recalculate.
3. Negative Space page: per entity, a coverage matrix of critical assets vs alert activity (silent assets highlighted), and a category-coverage grid of this entity vs peer group (missing categories highlighted), each linking to the related findings.
4. Link findings from the entity page to the finding page.
```

**Check:** click a finding and you see the evidence rows. Mark one "Not valid" and the organisation's risk score drops.

**Commit:**
```
Commit "Phase 8: finding drill-down, negative space, feedback". Tick Phase 8.
```

---

## Phase 9 — Uploading other formats (column mapping + integrity checks)

**Prompt:**
```
Phase 9 from CLAUDE.md: real-world upload.
1. Extend the generator with a --foreign-format flag that exports one entity's data with different column names (e.g. "Ticket No", "Sev", "Opened", "Resolved", "Assignee", "Comments") and severity labels like P1–P5, as both CSV and JSON.
2. Upload page: choose entity + table type + file -> backend profiles the file, auto-suggests a mapping to canonical columns (name similarity + value patterns), shows a mapping screen with dropdowns + preview of first 20 rows + severity value mapping. Save the mapping per entity so the next upload is automatic.
3. On import run data-quality checks Q01–Q05 from CLAUDE.md and store them as data_quality findings; show a data-quality report card after upload (green/amber/red per check).
4. Pseudonymise on import like Phase 3.
Tests for mapping suggestion and each Q check.
```

**Check:** upload the foreign-format file, map the columns, and the data appears with a quality report.

**Commit:**
```
Commit "Phase 9: upload, mapping, integrity checks". Tick Phase 9.
```

---

## Phase 10 — Review sample, audit log, PDF report

**Prompt:**
```
Phase 10 from CLAUDE.md.
1. Review-sample picker: on the entity page a "Generate review sample" panel (sample size N, default 50) -> 70% highest-risk evidence records, 30% seeded random; show the list with why each record was picked; export CSV.
2. Audit Log page: table of runs (run_id, time, code version, data hash, detector versions, counts) and supervisor actions. Re-running on the same data must produce identical findings — add a test that proves it.
3. PDF evidence pack per entity (reportlab, bundled font): cover with risk score and band, capability scorecard, each finding with rationale, innocent explanation, metrics and up to 20 evidence rows, supervisor status/notes, run id and data hash in the footer. Button on the entity page.
```

**Check:** the PDF downloads and looks professional. Run the analysis twice: same findings both times.

**Commit:**
```
Commit "Phase 10: sampling, audit, PDF". Tick Phase 10.
```

---

## Phase 11 — Validation page

**Prompt:**
```
Phase 11 from CLAUDE.md: Validation page in the UI.
GET /api/validation returns the same data as app/validation/run.py. Page shows: a big headline "Planted X problems — detected Y (Z% recall), precision P%", a per-detector table (planted, caught, missed, false positives, recall, precision), a list of innocent look-alikes and whether they were correctly NOT flagged, and a short methodology note explaining how validation works (synthetic data with known planted weaknesses, mirroring expert manual review).
```

**Check:** the page shows your detection score. This is the key slide/screen in the demo.

**Commit:**
```
Commit "Phase 11: validation page". Tick Phase 11.
```

---

## Phase 12 — Offline packaging (Docker)

**Prompt:**
```
Phase 12 from CLAUDE.md: offline deployment.
- Dockerfile for backend (copies the local model folder; sets HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1), Dockerfile for frontend (build with Vite, serve with nginx, proxy /api to backend), docker-compose.yml.
- On first start, if the database is empty, auto-generate sample data (seed 42), ingest it, and run the analysis.
- Add a compose override or instructions to run with networking disabled for the app containers (internal network only) to prove air-gapped operation.
- Scan the whole codebase and built frontend for any external URL usage (http/https to anything other than localhost) and report/remove them.
- scripts/export_offline_bundle.sh: docker save images to a .tar so it can be carried to an air-gapped machine on a USB drive; and matching load instructions.
- Document minimum hardware requirements (CPU, RAM, disk) based on measured resource use.
```

**Check (important):** turn off Wi-Fi, run `docker compose up`, open the app, run the analysis, and check everything works, including the note-similarity detector. Now you can honestly say it works air-gapped.

**Commit:**
```
Commit "Phase 12: offline docker packaging". Tick Phase 12.
```

---

## Phase 13 — Polish and submission files

**Prompt:**
```
Phase 13 from CLAUDE.md: final polish.
1. Go through every page and fix visual inconsistencies, empty states, loading states, and error messages. Make sure every finding rationale reads well to a non-technical supervisor.
2. README.md: what it is, screenshots placeholders, one-command start (docker compose up), dev setup, how validation works, offline guarantees, hardware requirements.
3. docs/ARCHITECTURE.md (max 2 pages): architecture diagram (Mermaid), data flow, detector methodology table (ID, what it catches, method, capability area), ML model details required by the PS (architecture, hardware, offline training/inference, update mechanism via signed offline bundle, explainability and auditability controls), validation methodology.
4. docs/DEMO_SCRIPT.md: a 2-minute demo script, second by second, following: upload -> run -> ranked overview -> entity radar -> finding with evidence and innocent explanation -> negative space -> mark valid -> PDF -> validation score -> "and it all ran with Wi-Fi off".
5. Run all tests and the validation one final time and report results.
```

**Commit:**
```
Commit "Phase 13: polish and docs". Tick Phase 13. Then help me push this repo to a new private GitHub repository.
```

---

## When something breaks: fix prompt

```
This is broken: <paste the error or describe what you see>.
Find the root cause first and explain it in 2–3 simple sentences, then fix it. Run the relevant tests and show that it works. Don't change unrelated code.
```

## Useful everyday prompts

- "Where are we? Read CLAUDE.md Progress and git log and tell me what's done and what's next."
- "Run all tests and the validation and give me a one-screen status report."
- "Explain how detector D07 works in simple words, like I'm new to this." (Useful before judges ask you.)
- "Act as an SIH judge from NCIIPC. Use the app's API and docs, then give me the 10 hardest questions you'd ask, with short answers."

## Tips

- If Claude Code goes off track mid-phase, press Esc, tell it what's wrong, and continue. Don't let it wander.
- Commit after every phase. If something goes badly wrong, you can go back.
- Phases 1–6 give you a demo-able product. Do those first, then the rest.
- Before the demo: generate fresh data, run the analysis, and test once with Wi-Fi off.
