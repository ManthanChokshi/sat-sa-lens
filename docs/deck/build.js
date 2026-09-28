/**
 * SAT-SA Lens — SIH 2026 idea-submission deck (6 slides, 16:9).
 * Visual language matched to the reference deck: white ground, navy #10256D
 * headings, #004AAD accent, Roboto-style sans (Arial for portability).
 */
const PptxGenJS = require("pptxgenjs");
const fs = require("fs");
const { Deck, C } = require("./lib");

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pptx.author = "SAT-SA Lens team";
pptx.company = "Smart India Hackathon 2026";
pptx.title = "SAT-SA Lens — SIH26157 Idea Submission";

const D = new Deck(pptx);

const M = 0.42;
const CW = 12.49;
const TEAM = "<TEAM NAME>";
const TEAM_ID = "<TEAM ID>";
const INSTITUTE = "<COLLEGE / INSTITUTE>";
const PS_TITLE =
  "Supervisory Analytics Tool for Assessment of Security Operations Centre (SOC) " +
  "Capability and Effectiveness of Critical Sector Entities";

/* ------------------------------------------------------------------ helpers */
function head(rec, title, sub) {
  D.text(rec, [{ text: title }], {
    x: M, y: 0.30, w: CW, h: 0.42, size: 23, color: C.navy, lineSpacingPt: 27,
  });
  if (sub) {
    D.text(rec, [{ text: sub }], {
      x: M, y: 0.76, w: CW, h: 0.30, size: 10, color: C.muted, lineSpacingPt: 13,
    });
  }
}

function foot(rec, n) {
  D.line(rec, { x: M, y: 6.99, w: CW, h: 0.008, color: C.line });
  D.text(rec, [{ text: "Smart India Hackathon 2026  ·  Idea Submission  ·  Problem Statement SIH26157" }], {
    x: M, y: 7.08, w: 7.0, h: 0.24, size: 8, color: C.muted, lineSpacingPt: 10,
  });
  D.text(rec, [{ text: `SAT-SA LENS   ·   ${TEAM}   ·   ${n} / 6` }], {
    x: M + CW - 5.0, y: 7.08, w: 5.0, h: 0.24, size: 8, color: C.muted, align: "right", lineSpacingPt: 10,
  });
}

/** Tinted panel with a heading, returns the inner y where content starts. */
function panel(rec, o) {
  D.rect(rec, {
    x: o.x, y: o.y, w: o.w, h: o.h,
    fill: o.fill || C.tint, radius: 0.05,
    line: o.line || C.line, lineW: 0.75,
  });
  D.text(rec, [{ text: o.heading }], {
    x: o.x + 0.20, y: o.y + 0.16, w: o.w - 0.40, h: 0.26,
    size: o.headingSize || 11, color: o.headingColor || C.navy, lineSpacingPt: 13,
  });
  return o.y + 0.50;
}

/** Bullet list rendered with a literal marker so HTML and PPTX agree. */
function bullets(rec, items, o) {
  const size = o.size || 9;
  const runs = [];
  items.forEach((it, i) => {
    runs.push({ text: "▪  " + it, size, color: o.color || C.body, breakLine: i < items.length - 1 });
  });
  D.text(rec, runs, {
    x: o.x, y: o.y, w: o.w, h: o.h, size,
    color: o.color || C.body,
    lineSpacingPt: o.lineSpacingPt || size * 1.45,
    paraSpaceAfter: o.gap === undefined ? 4 : o.gap,
  });
}

function statTile(rec, o) {
  D.rect(rec, { x: o.x, y: o.y, w: o.w, h: o.h, fill: o.fill || C.navy, radius: 0.05 });
  D.text(rec, [{ text: o.value }], {
    x: o.x + 0.16, y: o.y + 0.10, w: o.w - 0.32, h: 0.40,
    size: 21, color: C.white, lineSpacingPt: 24,
  });
  D.text(rec, [{ text: o.label }], {
    x: o.x + 0.16, y: o.y + 0.50, w: o.w - 0.32, h: 0.34,
    size: 8, color: "C5D5F2", lineSpacingPt: 10.5,
  });
}

function chip(rec, o) {
  D.rect(rec, { x: o.x, y: o.y, w: o.w, h: o.h, fill: o.fill || C.white, radius: 0.04, line: C.line, lineW: 0.75 });
  D.text(rec, [{ text: o.text, bold: o.bold }], {
    x: o.x + 0.08, y: o.y + 0.055, w: o.w - 0.16, h: o.h - 0.11,
    size: o.size || 8, color: o.color || C.navy, align: "center", valign: "middle",
    lineSpacingPt: (o.size || 8) * 1.2,
  });
}

/* =========================================================== SLIDE 1 — TITLE */
{
  const r = D.addSlide(C.navyDeep);

  D.text(r, [{ text: "SMART INDIA HACKATHON 2026" }], {
    x: 0.9, y: 0.62, w: 11.53, h: 0.34, size: 15, color: "9FBEEE", align: "center", lineSpacingPt: 18,
  });

  D.text(r, [{ text: "SAT-SA LENS" }], {
    x: 0.9, y: 1.02, w: 11.53, h: 1.10, size: 54, color: C.white, align: "center", lineSpacingPt: 60,
  });
  D.text(
    r,
    [{ text: "Supervisory analytics that tell an NCIIPC assessor which SOC, which process and which alert sample to look at — and why" }],
    { x: 1.6, y: 2.16, w: 10.13, h: 0.56, size: 13, color: "CBD9F2", align: "center", lineSpacingPt: 19 },
  );

  const cards = [
    ["PROBLEM STATEMENT ID", "SIH26157"],
    ["THEME", "Blockchain & Cybersecurity"],
    ["PS CATEGORY", "Software"],
    ["TEAM ID", TEAM_ID],
    ["TEAM NAME", TEAM],
    ["INSTITUTE", INSTITUTE],
  ];
  const cw = 3.72, gap = 0.185;
  cards.forEach((c, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = 0.9 + col * (cw + gap);
    const y = 2.86 + row * 1.10;
    D.rect(r, { x, y, w: cw, h: 0.94, fill: "18306F", radius: 0.05, line: "2F4C93", lineW: 0.75 });
    D.text(r, [{ text: c[0] }], {
      x: x + 0.18, y: y + 0.15, w: cw - 0.36, h: 0.22, size: 8, color: "8FAEE4", lineSpacingPt: 10,
    });
    D.text(r, [{ text: c[1], bold: true }], {
      x: x + 0.18, y: y + 0.40, w: cw - 0.36, h: 0.40, size: 13, color: C.white, lineSpacingPt: 17,
    });
  });

  D.rect(r, { x: 0.9, y: 5.16, w: 11.53, h: 1.06, fill: "14285F", radius: 0.05, line: "2F4C93", lineW: 0.75 });
  D.text(r, [{ text: "PROBLEM STATEMENT TITLE" }], {
    x: 1.10, y: 5.30, w: 11.13, h: 0.22, size: 8, color: "8FAEE4", lineSpacingPt: 10,
  });
  D.text(r, [{ text: PS_TITLE }], {
    x: 1.10, y: 5.56, w: 11.13, h: 0.52, size: 12, color: C.white, lineSpacingPt: 16,
  });

  D.text(
    r,
    [{ text: "Proposed for NTRO  ·  National Critical Information Infrastructure Protection Centre (NCIIPC)  ·  Runs fully offline inside the assessor's enclave" }],
    { x: 0.9, y: 6.62, w: 11.53, h: 0.30, size: 9.5, color: "7E97C8", align: "center", lineSpacingPt: 12 },
  );

  D.notes(
    r,
    "SIH26157, NTRO/NCIIPC. NCIIPC supervises the SOCs of India's critical sector entities — power, banking, " +
      "telecom, oil & gas, transport. Today experts hand-sample each periodic submission. SAT-SA Lens does that " +
      "first pass automatically, fully offline, and hands back a ranked, evidence-linked review queue.",
  );
}

/* ================================================ SLIDE 2 — PROPOSED SOLUTION */
{
  const r = D.addSlide();
  head(
    r,
    "PROPOSED SOLUTION — SAT-SA LENS",
    "Three detection engines, one peer-normalised capability scorecard, and a human supervisor who has the final word.",
  );

  const LX = M, LW = 7.16, RX = 7.75, RW = 5.16;

  const modules = [
    {
      n: "1",
      title: "EXECUTION-GAP ENGINE   ·   D01–D09",
      lines: [
        "Tests what the entity claims against what its own alert, case and escalation records actually show.",
        "Critical alerts closed manually in seconds, criticals with no escalation record, breach of the entity's own declared SLA, copy-paste investigation notes, notes with no artefact, recurring unremediated alerts, effort that never rises with severity, closures bunched inside the SLA, implausible per-analyst workload.",
      ],
    },
    {
      n: "2",
      title: "NEGATIVE-SPACE ENGINE   ·   D10–D13",
      lines: [
        "Detects evidence that should exist and does not — the blind spot no SIEM or GRC dashboard reports.",
        "Critical and OT assets producing zero telemetry, MITRE ATT&CK categories every peer reports but this entity never does, alert volume collapsing against its own baseline, and broken alert → case → escalation chains.",
      ],
    },
    {
      n: "3",
      title: "UNKNOWN-PATTERN & INTEGRITY ENGINE   ·   D14 + Q01–Q05",
      lines: [
        "Unsupervised IsolationForest over 13 size-invariant features, reported only with the deviating features named in plain English.",
        "Submission integrity: missing record-ID blocks, missing days, declared-versus-actual counts, machine-generated timestamps, and file-hash custody.",
      ],
    },
  ];

  modules.forEach((m, i) => {
    const y = 1.12 + i * 1.65;
    D.rect(r, { x: LX, y, w: LW, h: 1.50, fill: C.tint, radius: 0.05, line: C.line, lineW: 0.75 });
    D.circle(r, { x: LX + 0.20, y: y + 0.17, d: 0.36, fill: C.blue, label: m.n, labelSize: 13 });
    D.text(r, [{ text: m.title }], {
      x: LX + 0.68, y: y + 0.18, w: LW - 0.90, h: 0.26, size: 10.5, color: C.navy, lineSpacingPt: 13,
    });
    bullets(r, m.lines, { x: LX + 0.68, y: y + 0.50, w: LW - 0.90, h: 0.92, size: 8.5, lineSpacingPt: 12, gap: 3 });
  });

  let y = panel(r, { x: RX, y: 1.12, w: RW, h: 2.28, heading: "HOW IT ADDRESSES THE PROBLEM" });
  bullets(
    r,
    [
      "Replaces hand-sampling with a 100% first pass over every submitted record.",
      "Ranks entities by peer-normalised risk, so scarce expert time goes where it matters.",
      "Names the weak process and the exact sample to review — not just a maturity score.",
      "Every finding links to the precise rows, so a claim is verified in seconds.",
      "Runs air-gapped inside the assessor's enclave; no data ever leaves it.",
    ],
    { x: RX + 0.20, y, w: RW - 0.40, h: 1.72, size: 8.5, lineSpacingPt: 11.5, gap: 3 },
  );

  y = panel(r, { x: RX, y: 3.55, w: RW, h: 2.37, heading: "INNOVATION & UNIQUENESS" });
  bullets(
    r,
    [
      "Absence treated as evidence — negative space is a first-class signal, not an afterthought.",
      "Every finding ships a possible innocent explanation: the tool argues against itself.",
      "Hypothesis, never verdict — status changes only on supervisor sign-off.",
      "Deterministic and hash-anchored: the same data and code version reproduce identical findings months later.",
      "Peer-fairness ladder plus Wilson bounds, so a small entity is never punished for being small.",
      "Proven against planted ground truth instead of opinion.",
    ],
    { x: RX + 0.20, y, w: RW - 0.40, h: 1.80, size: 8.5, lineSpacingPt: 11.5, gap: 3 },
  );

  const stats = [
    { value: "19", label: "detectors mapped to 8 capability areas of SOC effectiveness" },
    { value: "186,548", label: "alerts and 173,666 cases assessed in 35 seconds on 2 vCPU" },
    { value: "100%", label: "recall and precision against deliberately planted weaknesses" },
    { value: "0", label: "false positives — 3 healthy and 2 look-alike entities left clean" },
  ];
  stats.forEach((s, i) => {
    statTile(r, { x: M + i * 3.16, y: 6.06, w: 2.99, h: 0.90, value: s.value, label: s.label });
  });

  foot(r, 2);
  D.notes(
    r,
    "Three engines, one message: execution gaps catch the entity that looks effective but isn't; negative space " +
      "catches what is missing; the integrity engine catches a submission that cannot be trusted at all. " +
      "The stats strip is the proof line — say it out loud.",
  );
}

/* =============================================== SLIDE 3 — TECHNICAL APPROACH */
{
  const r = D.addSlide();
  head(
    r,
    "TECHNICAL APPROACH",
    "Offline by construction: a single-file analytical database, 19 explainable detectors and two locally bundled models \u2014 no runtime call ever leaves the machine.",
  );

  /* technology stack */
  const SX = M, SW = 5.46;
  let y = panel(r, { x: SX, y: 1.12, w: SW, h: 3.12, heading: "TECHNOLOGY STACK" });
  const stack = [
    ["FRONTEND", "React 18 · TypeScript · Vite · Tailwind · Recharts · TanStack Table"],
    ["BACKEND", "Python 3.11 · FastAPI · Uvicorn · Pydantic v2"],
    ["DATA ENGINE", "DuckDB single-file OLAP · pandas · SQL-first aggregation"],
    ["ANALYTICS & ML", "scikit-learn IsolationForest · sentence-transformers MiniLM (local) · Wilson interval · robust z"],
    ["REPORTING", "ReportLab evidence pack · seeded CSV review sample"],
    ["PACKAGING", "Docker Compose · nginx · internal-only container network"],
    ["SECURITY & PRIVACY", "Salted SHA-256 pseudonymisation · file-hash custody · append-only audit log"],
  ];
  stack.forEach(([k, v], i) => {
    const ry = y + i * 0.355;
    D.text(r, [{ text: k, bold: true }], {
      x: SX + 0.20, y: ry, w: 1.50, h: 0.30, size: 8, color: C.blue, lineSpacingPt: 10,
    });
    D.text(r, [{ text: v }], {
      x: SX + 1.74, y: ry, w: SW - 1.96, h: 0.34, size: 8, color: C.body, lineSpacingPt: 10,
    });
  });

  /* assessment model */
  const AX = 6.06, AW = 6.85;
  y = panel(r, { x: AX, y: 1.12, w: AW, h: 3.12, heading: "ASSESSMENT & SCORING MODEL" });
  const areas = [
    "Threat detection", "Investigation", "Escalation", "Incident response",
    "Security operations", "Governance & oversight", "Operational discipline", "Cyber resilience",
  ];
  areas.forEach((a, i) => {
    const col = i % 4, row = Math.floor(i / 4);
    chip(r, {
      x: AX + 0.20 + col * 1.63, y: y + row * 0.40, w: 1.55, h: 0.32, text: a, size: 7.5,
    });
  });
  D.text(
    r,
    [
      { text: "PEER GROUP   ", bold: true, size: 7.6, color: C.blue },
      { text: "sector + size tier, widened to sector → tier → portfolio when a group is too small; the level used is on every finding.", size: 7.6, color: C.body, breakLine: true },
      { text: "SCORING   ", bold: true, size: 7.6, color: C.blue },
      { text: "weight = severity (30/18/9) × confidence · capability = 100·e^(−Σw/34) · entity risk = 100·(1−e^(−Σw/62)) → High / Medium / Low.", size: 7.6, color: C.body, breakLine: true },
      { text: "FAIRNESS   ", bold: true, size: 7.6, color: C.blue },
      { text: "minimum sample counts, Wilson lower bound and empirical-Bayes shrinkage; confidence is capped below 1.0 by design.", size: 7.6, color: C.body, breakLine: true },
      { text: "TREND   ", bold: true, size: 7.6, color: C.blue },
      { text: "weight spread across 30-day windows by where its evidence falls in time.", size: 7.6, color: C.body, breakLine: false },
    ],
    { x: AX + 0.20, y: y + 0.92, w: AW - 0.40, h: 1.62, size: 7.6, lineSpacingPt: 10.4, paraSpaceAfter: 3 },
  );

  /* workflow */
  D.rect(r, { x: M, y: 4.34, w: CW, h: 1.54, fill: C.white, radius: 0.05, line: C.line, lineW: 0.75 });
  D.text(r, [{ text: "END-TO-END WORKFLOW" }], {
    x: M + 0.20, y: 4.45, w: 6.0, h: 0.26, size: 11, color: C.navy, lineSpacingPt: 13,
  });
  D.text(r, [{ text: "Same input + same code version → byte-identical findings (enforced by test)" }], {
    x: M + CW - 6.2, y: 4.47, w: 6.0, h: 0.24, size: 8, color: C.muted, align: "right", lineSpacingPt: 10,
  });

  const steps = [
    ["SUBMISSION", "Periodic CSV / JSON export in any vendor schema"],
    ["PROFILE & MAP", "Auto column match + P1–P5 severity mapping, saved per entity"],
    ["NORMALISE", "Canonical schema, pseudonymisation, SHA-256 custody"],
    ["DETECT", "19 detectors over DuckDB views; one failure never stops the run"],
    ["SCORE", "Peer normalisation, capability scorecard, risk band, trend"],
    ["REVIEW", "Evidence table, valid / not valid, 70-30 review sample"],
    ["EVIDENCE PACK", "PDF with run ID + data hash, and an append-only audit trail"],
  ];
  const bw = 1.579, bgap = 0.18, bx0 = 0.60;
  steps.forEach(([t, d], i) => {
    const x = bx0 + i * (bw + bgap);
    D.rect(r, { x, y: 4.82, w: bw, h: 1.00, fill: C.tint, radius: 0.05, line: C.line, lineW: 0.75 });
    D.circle(r, { x: x + bw / 2 - 0.13, y: 4.89, d: 0.26, fill: C.navy, label: String(i + 1), labelSize: 9 });
    D.text(r, [{ text: t }], {
      x: x + 0.06, y: 5.19, w: bw - 0.12, h: 0.20, size: 7.5, color: C.navy, align: "center", lineSpacingPt: 9,
    });
    D.text(r, [{ text: d }], {
      x: x + 0.07, y: 5.39, w: bw - 0.14, h: 0.42, size: 6.8, color: C.body, align: "center", lineSpacingPt: 8.4,
    });
    if (i < steps.length - 1) {
      D.text(r, [{ text: "›", bold: true }], {
        x: x + bw, y: 5.16, w: bgap, h: 0.30, size: 15, color: C.blue, align: "center", lineSpacingPt: 17,
      });
    }
  });

  /* detector families */
  const fams = [
    ["EXECUTION GAPS   ·   D01–D09", "Fast critical closure · no escalation · commitment breach · template notes · shallow notes · recurring unremediated · effort–severity mismatch · SLA gaming · analyst workload"],
    ["NEGATIVE SPACE   ·   D10–D13", "Silent critical assets · missing ATT&CK categories · volume collapse · broken alert–case–escalation chains"],
    ["UNKNOWN PATTERNS   ·   D14", "IsolationForest on size-invariant features, explained feature by feature against the peer median"],
    ["SUBMISSION INTEGRITY   ·   Q01–Q05", "ID gaps · missing days · declared vs actual counts · timestamp granularity · file-hash custody"],
  ];
  fams.forEach(([t, d], i) => {
    const x = M + i * 3.165;
    D.rect(r, { x, y: 5.98, w: 2.995, h: 0.92, fill: C.tintDeep, radius: 0.05 });
    D.text(r, [{ text: t }], {
      x: x + 0.14, y: 6.07, w: 2.72, h: 0.20, size: 7.5, color: C.navy, lineSpacingPt: 9,
    });
    D.text(r, [{ text: d }], {
      x: x + 0.14, y: 6.28, w: 2.72, h: 0.58, size: 6.8, color: C.body, lineSpacingPt: 8.2,
    });
  });

  foot(r, 3);
  D.notes(
    r,
    "Key line for judges: 19 detectors, every one SQL-first and explainable; the two ML components are gated behind " +
      "explicit thresholds and peer comparison, so neither can raise a finding on its own numbers alone.",
  );
}

/* ========================================== SLIDE 4 — FEASIBILITY & VIABILITY */
{
  const r = D.addSlide();
  head(
    r,
    "FEASIBILITY AND VIABILITY",
    "A working end-to-end prototype today: generated corpus, ingest, 19 detectors, scoring, dashboard, evidence pack — " +
      "and an air-gap that has been demonstrated, not just asserted.",
  );

  const feas = [
    {
      title: "TECHNICAL FEASIBILITY",
      lines: [
        "Working prototype, not a mock-up: ingest → detect → score → report runs end to end.",
        "186,548 alerts and 173,666 cases across 12 entities analysed in 35 seconds on 2 vCPU.",
        "62 backend and 7 frontend tests green; every detector has a must-not-flag test.",
        "Re-running on unchanged data reproduces byte-identical findings — proven by test.",
      ],
    },
    {
      title: "OPERATIONAL FEASIBILITY",
      lines: [
        "One command to stand up: docker compose up. First start seeds, ingests and analyses on its own.",
        "Air-gapped operation verified — the backend container has no network route at all.",
        "CPU-only, no GPU, no accelerator, no external service dependency.",
        "Foreign vendor exports are profiled and mapped automatically; the mapping is saved per entity.",
      ],
    },
    {
      title: "ECONOMIC FEASIBILITY",
      lines: [
        "Entirely open-source stack — zero licence cost, no per-seat or per-GB pricing.",
        "Commodity host: 2 vCPU / 4 GB minimum, 4 GB disk. No specialised hardware.",
        "Replaces manual sampling effort that scales linearly with the number of entities.",
        "Reusable across sectors, States and UTs; rules are version-controlled centrally.",
      ],
    },
  ];
  const fw = 4.043;
  feas.forEach((f, i) => {
    const x = M + i * (fw + 0.18);
    const iy = panel(r, { x, y: 1.12, w: fw, h: 2.00, heading: f.title });
    bullets(r, f.lines, { x: x + 0.20, y: iy, w: fw - 0.40, h: 1.42, size: 8, lineSpacingPt: 10.5, gap: 2 });
  });

  /* standards */
  D.rect(r, { x: M, y: 3.24, w: CW, h: 0.84, fill: C.tintDeep, radius: 0.05 });
  D.text(r, [{ text: "STANDARDS & FRAMEWORK ALIGNMENT" }], {
    x: M + 0.20, y: 3.33, w: 4.0, h: 0.22, size: 9, color: C.navy, lineSpacingPt: 11,
  });
  const stds = [
    "NIST CSF 2.0", "ISO/IEC 27001:2022", "ISO/IEC 27035", "MITRE ATT&CK",
    "CERT-In Directions 2022", "NCIIPC CII Guidelines", "DPDP Act 2023", "SOC-CMM",
  ];
  const sw = (CW - 0.40 - 7 * 0.10) / 8;
  stds.forEach((s, i) => {
    chip(r, { x: M + 0.20 + i * (sw + 0.10), y: 3.62, w: sw, h: 0.32, text: s, size: 7.5, bold: true });
  });

  /* risks */
  const ry0 = 4.18;
  D.rect(r, { x: M, y: ry0, w: CW, h: 2.74, fill: C.white, radius: 0.05, line: C.line, lineW: 0.75 });
  D.text(r, [{ text: "POTENTIAL CHALLENGES & RISKS" }], {
    x: M + 0.20, y: ry0 + 0.13, w: 5.0, h: 0.24, size: 10, color: C.navy, lineSpacingPt: 12,
  });
  D.text(r, [{ text: "STRATEGY TO OVERCOME" }], {
    x: M + 6.30, y: ry0 + 0.13, w: 5.0, h: 0.24, size: 10, color: C.green, lineSpacingPt: 12,
  });

  const risks = [
    ["A peer group can be too small to compare fairly",
     "Documented fallback ladder — sector + tier → sector → tier → portfolio — with minimum sample counts and a Wilson lower bound; the comparison level used is printed on every finding."],
    ["Every entity exports a different schema",
     "The file is profiled on upload and columns plus P1–P5 severity labels are matched automatically; the confirmed mapping is stored per entity and reused next time."],
    ["A wrong flag could unfairly damage an entity",
     "Nothing is a verdict. Each finding carries a stated innocent explanation and stays a hypothesis until a supervisor marks it valid; dismissing it re-scores immediately."],
    ["An entity could tune detections down to look clean",
     "That is precisely what the negative-space and integrity detectors are for: silence, missing ATT&CK categories and a collapsing baseline are themselves the signal."],
    ["Submissions may carry personal data",
     "Analyst names, usernames and IP addresses are pseudonymised with a salted SHA-256 at ingest — inside free-text notes too — before any row is stored. Enforced by test."],
    ["No internet inside the assessment enclave",
     "Fully offline: bundled model and fonts, internal-only container network, and a build-time scan that fails if any fetchable external URL appears in the shipped code."],
  ];
  risks.forEach(([q, a], i) => {
    const ry = ry0 + 0.44 + i * 0.380;
    if (i % 2 === 0) D.rect(r, { x: M + 0.12, y: ry - 0.035, w: CW - 0.24, h: 0.37, fill: "F6F8FD", radius: 0.03 });
    D.text(r, [{ text: q }], {
      x: M + 0.20, y: ry + 0.02, w: 5.55, h: 0.34, size: 8, color: C.ink, lineSpacingPt: 10,
    });
    D.text(r, [{ text: "→", bold: true }], {
      x: M + 5.90, y: ry + 0.02, w: 0.30, h: 0.24, size: 10, color: C.blue, align: "center", lineSpacingPt: 12,
    });
    D.text(r, [{ text: a }], {
      x: M + 6.30, y: ry, w: CW - 6.52, h: 0.38, size: 7.8, color: C.body, lineSpacingPt: 9.6,
    });
  });

  foot(r, 4);
  D.notes(
    r,
    "The risk table is the credibility slide. Each mitigation is already implemented, not planned — the air-gap, " +
      "the pseudonymisation and the reproducibility all have tests behind them.",
  );
}

/* ============================================== SLIDE 5 — IMPACT AND BENEFITS */
{
  const r = D.addSlide();
  head(
    r,
    "IMPACT AND BENEFITS",
    "The same submission serves three audiences: the assessor gets a ranked queue, the entity gets a specific and checkable " +
      "instruction, and the sector gets comparable evidence over time.",
  );

  const groups = [
    {
      title: "NCIIPC / NTRO ASSESSOR",
      lines: [
        "Full-population first pass instead of a hand-picked sample — nothing is reviewed by chance.",
        "Entities ranked by peer-normalised risk with the top three reasons in plain English.",
        "A 50-record review sample: 70% highest-risk evidence, 30% seeded random control.",
        "Court-and-audit-grade evidence pack: run ID, rule version and data hash on every page.",
      ],
    },
    {
      title: "CRITICAL SECTOR ENTITY",
      lines: [
        "Receives a specific, checkable instruction instead of a generic 'improve your SOC'.",
        "Sees exactly which capability area is weak and against which comparable peers.",
        "Can rebut with evidence — the innocent explanation is offered, not withheld.",
        "Repeat assessments are comparable, so genuine improvement is visible.",
      ],
    },
    {
      title: "SECTOR & NATIONAL RESILIENCE",
      lines: [
        "Systemic blind spots become visible across a sector, not one entity at a time.",
        "Unmonitored critical and OT assets are surfaced before an incident finds them.",
        "Consistent supervisory yardstick across sectors, States and UTs.",
        "Strengthens assurance for CERT-In and NCIIPC reporting duties.",
      ],
    },
  ];
  const gw = 4.043;
  groups.forEach((g, i) => {
    const x = M + i * (gw + 0.18);
    const iy = panel(r, { x, y: 1.12, w: gw, h: 1.98, heading: g.title });
    bullets(r, g.lines, { x: x + 0.20, y: iy, w: gw - 0.40, h: 1.40, size: 8, lineSpacingPt: 10.5, gap: 2 });
  });

  const impacts = [
    ["SOCIETAL", "Better-defended power, banking, telecom, transport and oil & gas services for citizens; fewer outages caused by a weakness that was visible in the data all along."],
    ["ECONOMIC", "Licence-free and hardware-light. Supervisory effort scales with findings, not with the number of entities onboarded."],
    ["STRATEGIC", "A national, repeatable yardstick for SOC effectiveness, with an audit trail that survives a change of officer or of government."],
    ["OPERATIONAL", "Turns a subjective review into a hypothesis-driven, evidence-linked one — and keeps the human decision where it belongs."],
  ];
  impacts.forEach(([t, d], i) => {
    const x = M + i * 3.165;
    D.rect(r, { x, y: 3.26, w: 2.995, h: 1.18, fill: C.tint, radius: 0.05, line: C.line, lineW: 0.75 });
    D.text(r, [{ text: t }], {
      x: x + 0.16, y: 3.37, w: 2.68, h: 0.22, size: 9, color: C.blue, lineSpacingPt: 11,
    });
    D.text(r, [{ text: d }], {
      x: x + 0.16, y: 3.62, w: 2.68, h: 0.74, size: 7.6, color: C.body, lineSpacingPt: 9.6,
    });
  });

  /* user story */
  D.rect(r, { x: M, y: 4.58, w: 8.55, h: 2.34, fill: C.navy, radius: 0.05 });
  D.text(r, [{ text: "USER STORY   ·   A POWER-SECTOR ENTITY, QUARTERLY SUBMISSION" }], {
    x: M + 0.24, y: 4.70, w: 8.07, h: 0.24, size: 9, color: "A9C4F0", lineSpacingPt: 11,
  });
  D.text(
    r,
    [
      { text: "The entity uploads its quarterly SOC extract in its vendor's own format. SAT-SA Lens maps the columns automatically, pseudonymises every analyst name and IP on the way in, and ranks the entity third of twelve.", breakLine: true },
      { text: "Its capability radar shows Escalation at 29 / 100. The reason is one sentence: 42.6% of closed critical alerts (1,253 of 2,939) carry no escalation record at all, against 5.1% across its peer group — while the entity's own declared commitment is fifteen minutes.", breakLine: true },
      { text: "The assessor opens the 1,253 case IDs behind that number, reads the possible innocent explanation, generates a 50-record review sample and exports the evidence pack. Six months later the same data and the same rule version reproduce that finding exactly.", breakLine: false },
    ],
    { x: M + 0.24, y: 5.02, w: 8.07, h: 1.78, size: 8.6, color: "E4ECFA", lineSpacingPt: 12, paraSpaceAfter: 5 },
  );

  const outs = [
    ["28,545 → 50", "cases in the submission versus records the assessor actually has to read"],
    ["35 seconds", "to assess an entire twelve-entity portfolio end to end"],
    ["100%", "of submitted records covered by the first pass, not a sample"],
  ];
  outs.forEach(([v, l], i) => {
    const y = 4.58 + i * 0.80;
    D.rect(r, { x: 9.25, y, w: 3.66, h: 0.72, fill: C.tint, radius: 0.05, line: C.line, lineW: 0.75 });
    D.text(r, [{ text: v }], {
      x: 9.41, y: y + 0.09, w: 3.34, h: 0.28, size: 15, color: C.navy, lineSpacingPt: 18,
    });
    D.text(r, [{ text: l }], {
      x: 9.41, y: y + 0.37, w: 3.34, h: 0.30, size: 7.5, color: C.body, lineSpacingPt: 9,
    });
  });

  foot(r, 5);
  D.notes(
    r,
    "Land the user story: a specific, checkable instruction beats a maturity score. The 28,545 → 50 number is the " +
      "single most quotable statistic in the deck.",
  );
}

/* ========================================== SLIDE 6 — RESEARCH AND REFERENCES */
{
  const r = D.addSlide();
  head(
    r,
    "RESEARCH AND REFERENCES",
    "Built on published supervisory practice, open standards and reproducible methods — and measured against a corpus " +
      "in which the correct answer is known exactly.",
  );

  const LX = M, LW = 5.30;
  let y = panel(r, { x: LX, y: 1.12, w: LW, h: 2.18, heading: "STANDARDS, LAW & GUIDELINES" });
  bullets(
    r,
    [
      "NCIIPC — Guidelines for Protection of Critical Information Infrastructure; Roles & Responsibilities of CISOs.",
      "CERT-In Directions under §70B(6), 28 April 2022 — logging, incident reporting timelines.",
      "NIST CSF 2.0 (2024); NIST SP 800-61r3 — incident handling.",
      "ISO/IEC 27001:2022 · ISO/IEC 27035-1/2 — incident management.",
      "MITRE ATT&CK Enterprise — tactic taxonomy used for category coverage.",
      "Digital Personal Data Protection Act, 2023 — data minimisation on ingest.",
    ],
    { x: LX + 0.20, y, w: LW - 0.40, h: 1.62, size: 8, lineSpacingPt: 10.4, gap: 2 },
  );

  y = panel(r, { x: LX, y: 3.45, w: LW, h: 2.35, heading: "RESEARCH & TECHNICAL BASIS" });
  bullets(
    r,
    [
      "SOC-CMM (Van Os) — capability dimensions behind the eight assessment areas.",
      "Liu, Ting & Zhou, Isolation Forest, ICDM 2008 — unsupervised outlier detection.",
      "Reimers & Gurevych, Sentence-BERT, EMNLP 2019 — all-MiniLM-L6-v2 note similarity.",
      "Wilson (1927) score interval — small-sample protection on every rate.",
      "Efron & Morris — empirical-Bayes shrinkage toward the peer mean.",
      "Benford / granularity tests — inspiration for the timestamp-regularity check.",
      "DuckDB (Raasveldt & Mühleisen) — in-process OLAP for single-file analytics.",
    ],
    { x: LX + 0.20, y, w: LW - 0.40, h: 1.78, size: 8, lineSpacingPt: 10.4, gap: 2 },
  );

  /* comparison table */
  const TX = 6.00, TW = 6.91;
  const cols = [2.43, 1.12, 1.12, 1.12, 1.12];
  const colX = [];
  cols.reduce((acc, w, i) => { colX[i] = acc; return acc + w; }, TX);

  D.text(r, [{ text: "COMPARISON WITH EXISTING APPROACHES" }], {
    x: TX, y: 1.12, w: TW, h: 0.24, size: 11, color: C.navy, lineSpacingPt: 13,
  });

  const heads = ["Capability", "SIEM / SOAR\ndashboards", "GRC & audit\nplatforms", "SOC-CMM\nself-assessment", "SAT-SA\nLens"];
  const hy = 1.44;
  D.rect(r, { x: TX, y: hy, w: TW, h: 0.50, fill: C.navy, radius: 0.04 });
  heads.forEach((h, i) => {
    const parts = h.split("\n");
    D.text(r, parts.map((p, k) => ({ text: p, breakLine: k < parts.length - 1 })), {
      x: colX[i] + 0.08, y: hy + 0.08, w: cols[i] - 0.16, h: 0.36,
      size: 7.4, color: C.white, align: i === 0 ? "left" : "center", lineSpacingPt: 8.8,
    });
  });

  const rows = [
    ["Full-population review of every submitted record", "P", "N", "N", "Y"],
    ["Detects missing evidence (negative space)", "N", "N", "N", "Y"],
    ["Peer-normalised comparison across entities", "N", "P", "P", "Y"],
    ["Exact evidence rows attached to every finding", "P", "P", "N", "Y"],
    ["States a possible innocent explanation", "N", "N", "N", "Y"],
    ["Reproducible + hash-anchored for audit", "N", "P", "N", "Y"],
    ["Runs fully air-gapped with no external service", "P", "P", "Y", "Y"],
    ["Validated against known planted weaknesses", "N", "N", "N", "Y"],
  ];
  const mark = { Y: ["Yes", C.green, C.greenBg], P: ["Partial", C.amber, C.amberBg], N: ["No", C.red, C.redBg] };
  rows.forEach((row, i) => {
    const ry = hy + 0.50 + i * 0.335;
    if (i % 2 === 0) D.rect(r, { x: TX, y: ry, w: TW, h: 0.335, fill: "F6F8FD" });
    D.text(r, [{ text: row[0] }], {
      x: colX[0] + 0.08, y: ry + 0.055, w: cols[0] - 0.16, h: 0.25, size: 7.6, color: C.ink, lineSpacingPt: 9,
    });
    for (let k = 1; k <= 4; k++) {
      const [label, col, bg] = mark[row[k]];
      D.rect(r, { x: colX[k] + 0.16, y: ry + 0.055, w: cols[k] - 0.32, h: 0.225, fill: bg, radius: 0.03 });
      D.text(r, [{ text: label, bold: k === 4 }], {
        x: colX[k] + 0.16, y: ry + 0.088, w: cols[k] - 0.32, h: 0.18,
        size: 7, color: col, align: "center", lineSpacingPt: 8.4,
      });
    }
  });
  D.line(r, { x: TX, y: hy + 0.50 + rows.length * 0.335, w: TW, h: 0.008, color: C.line });
  D.text(r, [{ text: "Category-level comparison of typical tooling, not of any single product." }], {
    x: TX, y: hy + 0.50 + rows.length * 0.335 + 0.06, w: TW, h: 0.20, size: 6.8, color: C.muted, lineSpacingPt: 8,
  });

  /* validation */
  D.rect(r, { x: TX, y: 5.00, w: TW, h: 0.88, fill: C.navy, radius: 0.05 });
  D.text(r, [{ text: "VALIDATION RESULT" }], {
    x: TX + 0.20, y: 5.10, w: 3.0, h: 0.20, size: 8, color: "A9C4F0", lineSpacingPt: 10,
  });
  D.text(
    r,
    [
      { text: "28 planted weaknesses  ·  28 detected  ·  100% recall  ·  100% precision  ·  0 false positives", bold: true, size: 10.5, color: C.white, breakLine: true },
      { text: "Three healthy entities and two innocent look-alikes — one that closes alerts in seconds but only through automation, one that is simply small — were correctly left unflagged.", size: 7.6, color: "CBD9F2", breakLine: false },
    ],
    { x: TX + 0.20, y: 5.32, w: TW - 0.40, h: 0.54, size: 8, lineSpacingPt: 11, paraSpaceAfter: 2 },
  );

  /* project links */
  D.rect(r, { x: M, y: 5.95, w: CW, h: 0.97, fill: C.tintDeep, radius: 0.05 });
  D.text(r, [{ text: "PROJECT LINKS" }], {
    x: M + 0.20, y: 6.08, w: 2.0, h: 0.22, size: 9, color: C.navy, lineSpacingPt: 11,
  });
  D.text(r, [{ text: "Replace each placeholder with your published URL before submission." }], {
    x: M + 2.30, y: 6.09, w: 4.6, h: 0.22, size: 7.4, color: C.muted, lineSpacingPt: 9,
  });
  const links = [
    ["SOURCE CODE REPOSITORY", "<GITHUB URL>"],
    ["DEMO VIDEO (2 MINUTES)", "<VIDEO URL>"],
    ["ARCHITECTURE & VALIDATION REPORT", "<REPORT URL>"],
  ];
  links.forEach(([t, u], i) => {
    const x = M + 0.20 + i * 4.06;
    D.rect(r, { x, y: 6.36, w: 3.86, h: 0.42, fill: C.white, radius: 0.05, line: C.blue, lineW: 1 });
    D.text(r, [
      { text: t + "   ", bold: true, size: 7.6, color: C.navy, breakLine: false },
      { text: u, size: 7.6, color: C.blue, breakLine: false },
    ], {
      x: x + 0.10, y: 6.47, w: 3.66, h: 0.22, size: 7.6, align: "center", lineSpacingPt: 9.5,
    });
  });

  foot(r, 6);
  D.notes(
    r,
    "Close on the validation line. The comparison table answers 'why not just use a SIEM dashboard' before it is asked.",
  );
}

/* --------------------------------------------------------------------- write */
const OUT = process.argv[2] || "SAT-SA-Lens-SIH26157.pptx";
fs.writeFileSync("preview.html", D.toHtml());
// one file per slide: the preview pane renders reliably on navigate, not on scroll
D.slides.forEach((rec, i) => {
  fs.writeFileSync(
    `preview-${i + 1}.html`,
    `<!doctype html><html><head><meta charset="utf-8"><title>slide ${i + 1}</title>` +
      `<style>body{margin:0;background:#555}</style></head><body>` +
      `<section style="position:relative;width:1280px;height:720px;background:#${rec.bg};overflow:hidden">` +
      rec.html.join("") + `</section></body></html>`,
  );
});
pptx.writeFile({ fileName: OUT }).then(() => {
  console.log("wrote", OUT, "and preview.html");
});
