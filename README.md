# SAT-SA Lens

**Supervisory Analytics Tool for SOC Assessment** — Smart India Hackathon 2026,
problem statement **SIH26157** (NTRO / NCIIPC).

An **offline** web application that gives an NCIIPC supervisor an automated
first pass over the SOC records that Critical Sector Entities submit, and tells
them **which organisations, processes and alert samples need human review, and
why**.

It looks for two things that a spreadsheet of KPIs will never show:

- **Execution gaps** — the organisation looks effective, but the operational
  evidence disagrees: critical alerts closed in seconds, nothing escalated,
  copy-paste investigation notes, closures bunched against an SLA deadline.
- **Negative space** — evidence that *should* exist and does not: critical
  assets producing no telemetry, attack categories every peer reports, alert
  volume that collapses, records that do not join up.

It is **not** a SOC, not a SIEM and not real-time monitoring. It analyses
periodic submissions, and it never returns a verdict — every finding is a
hypothesis with a reason, a confidence, a possible innocent explanation and the
exact evidence rows, for a human to confirm or dismiss.

---

## One-command start (recommended)

```bash
docker compose up --build
```

Open <http://localhost:8080>. On first start the backend generates a realistic
sample corpus (seed 42), ingests it and runs the first analysis — about 90
seconds — then the dashboard is fully populated.

To prove air-gapped operation, add the offline override. The backend then has
no network route at all, not even DNS:

```bash
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d
docker compose exec backend python -c "import socket; socket.create_connection(('1.1.1.1',53),3)"
# must fail: OSError [Errno 101] Network is unreachable
```

To carry it to a machine that has never been online:

```bash
./scripts/export_offline_bundle.sh      # writes dist/offline-bundle/
```

---

## Development setup

```bash
./scripts/dev.sh          # macOS / Linux
.\scripts\dev.ps1         # Windows PowerShell
```

That creates the virtual environment, installs dependencies, generates and
ingests the sample corpus if needed, and starts both servers:

- backend  <http://127.0.0.1:8000> (interactive API docs at `/docs`)
- frontend <http://localhost:5173>

### Doing it by hand

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# 1. generate the synthetic corpus with known, planted weaknesses
backend/.venv/bin/python -m generator.generate --seed 42 --entities 12 --days 90

# 2. load it (pseudonymising analysts, usernames and IPs on the way in)
cd backend && .venv/bin/python -m app.ingest.load_sample

# 3. run every detector and score every organisation
.venv/bin/python -m app.runner

# 4. score the detectors against the planted ground truth
.venv/bin/python -m app.validation.run

# 5. tests
.venv/bin/python -m pytest -q                  # everything
.venv/bin/python -m pytest -q -m "not slow"    # skip the end-to-end corpus run
```

```bash
cd frontend && npm install && npm run dev
```

---

## What you see

| Page | What it is for |
|---|---|
| **Overview** | Every organisation ranked by risk, with a capability heatmap across the eight capability areas. Triage: where does the next hour go? |
| **Organisation** | Risk score with the top three reasons in plain English, a capability radar against the peer average, alert volume over time, findings grouped by capability area, and the review-sample picker. |
| **Finding** | The rationale, the numbers behind it (including the peer baseline), a possible innocent explanation, the exact evidence rows, and the Valid / Not valid decision. |
| **Negative Space** | Critical assets with no telemetry, and the entity-vs-peer category coverage grid. |
| **Upload** | Bring in a submission in whatever format the organisation exports. The tool profiles the file, proposes a column mapping, maps vendor severity labels, and returns a data-quality report card. |
| **Validation** | "Planted X problems — detected Y" against a corpus where the right answer is known. |
| **Methodology** | What every detector does, and how peer comparison works. |
| **Audit Log** | Every run with its code version, rule version and input data hash; every supervisor action. |

---

## How validation works

The generator plants specific, documented weaknesses in specific organisations
and writes them to `data/ground_truth.json`. The validation harness compares the
findings to that file and reports recall and precision per detector.

The corpus also contains **three healthy organisations** and **two innocent
look-alikes** built specifically to catch an over-eager tool:

- one closes alerts in seconds — but every one of them is `closure_type =
  automated` on informational alerts;
- one is a genuinely small estate where every rate has a tiny sample.

Neither may be flagged. Current result on seed 42:

```
PLANTED 28, CAUGHT 28 (100.0% recall), precision 100.0%, false positives 0
Innocent look-alikes: both correctly not flagged
Healthy organisations: all three clean
```

Precision counts a finding as wrong only when it is not planted for that
organisation **and** is not a declared knock-on effect of a planted weakness —
copy-paste notes have no artefacts either, so a D04 plant legitimately trips
D05. Those links are declared by the generator, not inferred by the scorer.

---

## Offline guarantees

1. No runtime call ever leaves the machine. `python scripts/scan_external_urls.py`
   scans the source **and the built frontend** and fails if it finds a fetchable
   external URL.
2. Fonts are bundled from npm (`@fontsource/inter`), not Google Fonts. No CDN
   script or stylesheet anywhere; nginx serves a `default-src 'self'` CSP.
3. The ML model is loaded from the local `models/` folder only, with
   `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`. If it is missing, detector
   D04 falls back to a deterministic character n-gram method and says so in the
   finding; `SATSA_REQUIRE_MODEL=1` makes a missing model a hard error instead.
   `scripts/download_model.py` is the only file permitted to use the network,
   and only when a person runs it.
4. `docker-compose.offline.yml` puts the backend on an `internal` network so the
   claim is enforced, not just asserted.

## Privacy

Analyst names, usernames and IP addresses are pseudonymised on ingest with a
stable salted SHA-256 (`SATSA_PSEUDO_SALT`), before anything is written to the
database. Free-text notes are redacted the same way, while keeping artefact
*shape* so the "did this analyst cite any evidence?" check still works. No raw
personal identifier is ever stored or displayed — there is a test for it.

## Reproducibility

Every run records the code version, rule-set version, git commit, random seed
and a hash of the exact input data. Re-running on unchanged data produces
byte-for-byte identical findings; `tests/test_pipeline.py` proves it.

---

## Hardware requirements

Measured on the bundled 12-organisation, 90-day corpus (186,548 alerts,
173,666 cases):

| | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 4 GB | 10 GB |
| GPU | none | none — inference is CPU-only |

Observed at rest: backend 446 MB RSS, frontend 14 MB. Images: backend 949 MB,
frontend 79 MB. Database plus generated CSVs: 122 MB. A full analysis of the
whole corpus takes about 35 seconds; generation and ingest add about 20.
With the transformer model bundled (`SATSA_WITH_ML=1`) allow a further ~2.5 GB
of image size and ~1 GB of RAM.

---

## Repository layout

```
sat-sa-lens/
├── generator/          synthetic corpus + planted-problem injectors + ground truth
├── backend/app/
│   ├── detectors/      one file per detector, all registered in registry.py
│   ├── ingest/         loading, pseudonymisation, column mapping, uploads
│   ├── scoring/        peer groups, capability scorecard, risk score, trend
│   ├── sampling/       review-sample picker
│   ├── reports/        PDF evidence pack
│   ├── validation/     findings vs ground truth
│   └── api/            HTTP routes
├── frontend/src/       React + TypeScript dashboard
├── docs/               ARCHITECTURE.md, DEMO_SCRIPT.md, BUILD_GUIDE.md
└── scripts/            dev servers, model download, URL scan, offline bundle
```

## Licence and status

Built for SIH 2026 evaluation. The data in `data/` is entirely synthetic; no
real CSE submission is included.
