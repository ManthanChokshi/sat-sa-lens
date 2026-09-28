# SAT-SA Lens — 2-minute demo script

**Before you start:** `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`,
wait for the first analysis to finish (about 90 seconds), open
<http://localhost:8080>, and **turn your Wi-Fi off**. Leave it off for the whole
demo. Have the foreign-format file ready at
`data/foreign/E004_alerts_foreign.csv`.

---

### 0:00–0:12 — The problem, in one breath

> "NCIIPC supervises the SOCs of India's power, banking, telecom and oil-and-gas
> operators. Today an expert reads a sample of each submission by hand. We do
> that first pass automatically and tell the supervisor where to look and why."

*(Overview page on screen.)*

### 0:12–0:30 — Upload a real-world export

Go to **Upload**. Pick *Coastal Commercial Bank*, record type *Alerts*, choose
`E004_alerts_foreign.csv`, press **Profile file**.

> "This is a vendor export: 'Ticket No', 'Sev', 'Opened' — not our schema. The
> tool profiled it and mapped every column on its own, and mapped P1 to P5 onto
> our severity scale. The supervisor confirms once; the next upload from this
> organisation is automatic."

Press **Import**. Point at the green data-quality card.

> "On the way in it pseudonymises analyst names and IPs, records the file hash,
> and runs five integrity checks."

### 0:30–0:42 — Run the analysis

Press **Run analysis** in the header.

> "Nineteen detectors over 186,000 alerts and 173,000 cases: thirty-five
> seconds."

### 0:42–0:58 — The ranked overview

> "Twelve organisations ranked by risk. Seven high risk. The heatmap shows which
> of the eight capability areas is weak in each one. This is triage — where does
> the supervisor's next hour go."

Click **Coastal Commercial Bank**.

### 0:58–1:12 — The organisation page

> "Score 92, High. Three reasons in plain English. The radar compares it with
> its peer group, not with an absolute ideal — a large bank is never penalised
> for volume."

Click the first finding: *Declared commitment not met*.

### 1:12–1:30 — A finding, with its evidence and its counter-argument

> "This organisation declared it escalates criticals within fifteen minutes. The
> real median is 3.9 hours — nearly sixteen times its own target. Here are the
> numbers, including the peer baseline. Here are the 1,751 escalation records,
> sortable and exportable."

Point at the amber box.

> "And here is the part that matters for a regulator: every finding carries a
> possible innocent explanation. The tool argues against itself. It never says
> 'this organisation failed'."

### 1:30–1:42 — Negative space

Sidebar → **Negative Space**, pick *Western Offshore Petro*.

> "This is the part a KPI dashboard can never show. Fifty-five critical assets —
> OT controllers, database servers — produced zero alerts all period. And two
> whole attack categories that every peer reports are simply absent. We detect
> the evidence that *should* be there and isn't."

### 1:42–1:52 — The supervisor stays in control, and takes the pack away

Back to the finding → type a note → **Not valid**.

> "The supervisor decides. Dismiss it and the score drops immediately, and the
> decision goes to the audit log with who and when."

Organisation page → **Download evidence pack (PDF)**.

> "Cover, scorecard, every finding with its rationale, its innocent explanation
> and up to twenty evidence rows, and the run ID and data hash in the footer, so
> this is defensible six months later."

### 1:52–2:00 — The number, and the punchline

Sidebar → **Validation**.

> "We validate against a synthetic corpus where we planted the weaknesses
> ourselves, so the right answer is known. Twenty-eight planted, twenty-eight
> caught: 100% recall, 100% precision. Two 'innocent look-alike' organisations —
> one that closes alerts in seconds but only through automation, one that is
> simply small — were correctly *not* flagged."

Pause. Point at the Wi-Fi icon.

> "And all of that just ran with the Wi-Fi off. The whole thing is air-gapped by
> design."

---

## Likely questions, short answers

| Question | Answer |
|---|---|
| "Is this a black box?" | No. Every finding states its numbers, its peer baseline and the exact record IDs. Two ML components are used and both are gated behind explicit thresholds and explained feature-by-feature. |
| "What if you're wrong?" | Then the supervisor dismisses it in one click and the score recomputes. The tool produces hypotheses, not verdicts. |
| "Would it flag a small entity unfairly?" | Every detector has a minimum sample size and a Wilson lower bound, and the anomaly model uses only size-invariant features. There is a deliberately small organisation in the corpus to test exactly that, and it is not flagged. |
| "Does it handle our format?" | It profiled a vendor export live in this demo and mapped every column with no manual work. |
| "Personal data?" | Analyst names, usernames and IPs are pseudonymised with a salted hash before anything is stored, including inside free-text notes. A test asserts that no raw identifier survives ingest. |
| "Will two runs agree?" | Byte-for-byte, on the same data and the same code version. The run ID, rule version, seed and data hash are on every finding and in the PDF footer. |
| "Can it run air-gapped?" | It just did. The backend container has no network route at all — `docker compose exec backend` proves the connection fails. |
