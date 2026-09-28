"""D14 - unsupervised outlier detection over per-entity feature vectors.

IsolationForest with a fixed seed. Size-invariant features only (shares and
ratios), so a genuinely small organisation is not flagged just for being small.
An entity is only reported when the forest isolates it AND at least three
individual features are far from the peer median, and those three features are
what the rationale explains.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from app.config import RANDOM_SEED
from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    robust_z,
    severity_from_confidence,
)
from app.schema import Finding

MIN_ENTITIES = 6
MIN_DEVIANT_FEATURES = 2
DEVIATION_Z = 2.5
CONTAMINATION = 0.30

FEATURE_LABELS: dict[str, str] = {
    "share_critical_fast_manual": "share of critical alerts closed by hand in under 2 minutes",
    "share_critical_no_escalation": "share of critical alerts with no escalation record",
    "log_effort_ratio": "how much longer a critical alert takes than a medium one",
    "share_true_positive": "share of cases confirmed as true positives",
    "share_automated_closure": "share of closures done by automation",
    "share_notes_no_artefact": "share of notes with no checkable artefact",
    "note_diversity": "variety of investigation notes",
    "silent_critical_share": "share of critical assets producing no alerts",
    "category_coverage": "share of attack categories ever detected",
    "recent_volume_ratio": "recent alert volume against its own baseline",
    "escalation_delay_vs_commitment": "escalation delay against its own declared target",
    "analyst_concentration": "busiest analyst-day against the typical analyst-day",
    "median_note_length": "typical length of an investigation note",
}


class D14EntityAnomaly(Detector):
    id = "D14"
    version = "1.1.0"
    name = "entity_anomaly"
    gap_type = "anomaly"
    capability_area = "cyber_resilience"
    min_sample = MIN_ENTITIES
    description = (
        "An unsupervised check for organisations whose overall profile does not look "
        "like anyone else's, used to surface weaknesses no hand-written rule covers."
    )

    # ------------------------------------------------------------------ features
    def features(self, ctx: RunContext) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {e: {} for e in ctx.entity_ids}

        def setv(entity_id: str, key: str, value: Any) -> None:
            if entity_id in out:
                out[entity_id][key] = float(value if value is not None else 0.0)

        for r in ctx.q(
            """
            SELECT entity_id,
                   COUNT(*) AS crit_n,
                   SUM(CASE WHEN closure_type = 'manual' AND handling_minutes <= 2
                            THEN 1 ELSE 0 END) AS fast_n,
                   SUM(CASE WHEN escalation_id IS NULL THEN 1 ELSE 0 END) AS no_esc
            FROM case_facts WHERE severity = 'critical' GROUP BY entity_id
            """
        ):
            n = max(int(r["crit_n"] or 0), 1)
            setv(r["entity_id"], "share_critical_fast_manual", (r["fast_n"] or 0) / n)
            setv(r["entity_id"], "share_critical_no_escalation", (r["no_esc"] or 0) / n)

        med: dict[str, dict[str, float]] = {}
        for r in ctx.q(
            """
            SELECT entity_id, severity, median(handling_minutes) AS m
            FROM case_facts WHERE handling_minutes IS NOT NULL AND closure_type = 'manual'
            GROUP BY entity_id, severity
            """
        ):
            med.setdefault(r["entity_id"], {})[r["severity"]] = float(r["m"] or 0)
        for e, sev in med.items():
            ratio = (sev.get("critical") or 0) / max(sev.get("medium") or 1.0, 1e-6)
            setv(e, "log_effort_ratio", np.log1p(max(ratio, 0.0)))

        for r in ctx.q(
            """
            SELECT entity_id,
                   COUNT(*) AS n,
                   SUM(CASE WHEN disposition = 'true_positive' THEN 1 ELSE 0 END) AS tp,
                   SUM(CASE WHEN closure_type = 'automated' THEN 1 ELSE 0 END) AS auto_n,
                   COUNT(DISTINCT notes) AS distinct_notes,
                   median(length(notes)) AS note_len
            FROM case_facts GROUP BY entity_id
            """
        ):
            n = max(int(r["n"] or 0), 1)
            setv(r["entity_id"], "share_true_positive", (r["tp"] or 0) / n)
            setv(r["entity_id"], "share_automated_closure", (r["auto_n"] or 0) / n)
            setv(r["entity_id"], "note_diversity", (r["distinct_notes"] or 0) / n)
            setv(r["entity_id"], "median_note_length", (r["note_len"] or 0) / 200.0)

        from app.detectors.d05_shallow_investigation import ARTEFACT_SQL

        for r in ctx.q(
            f"""
            SELECT entity_id, COUNT(*) AS n,
                   SUM(CASE WHEN {ARTEFACT_SQL} THEN 0 ELSE 1 END) AS bad
            FROM case_facts WHERE closure_type = 'manual' AND notes IS NOT NULL
            GROUP BY entity_id
            """
        ):
            setv(
                r["entity_id"],
                "share_notes_no_artefact",
                (r["bad"] or 0) / max(int(r["n"] or 0), 1),
            )

        for r in ctx.q(
            """
            SELECT a.entity_id, COUNT(*) AS n,
                   SUM(CASE WHEN coalesce(al.n, 0) <= 1 THEN 1 ELSE 0 END) AS silent
            FROM assets a
            LEFT JOIN (SELECT asset_id, COUNT(*) AS n FROM alerts GROUP BY asset_id) al
                   ON al.asset_id = a.asset_id
            WHERE a.criticality = 'critical' GROUP BY a.entity_id
            """
        ):
            setv(
                r["entity_id"],
                "silent_critical_share",
                (r["silent"] or 0) / max(int(r["n"] or 0), 1),
            )

        total_categories = max(
            int(
                (ctx.q("SELECT COUNT(DISTINCT category) AS n FROM alerts")[0]["n"]) or 1
            ),
            1,
        )
        for r in ctx.q(
            "SELECT entity_id, COUNT(DISTINCT category) AS n FROM alerts GROUP BY entity_id"
        ):
            setv(r["entity_id"], "category_coverage", int(r["n"] or 0) / total_categories)

        for r in ctx.q(
            """
            WITH bounds AS (SELECT entity_id, max(created_at) AS last_seen,
                                   min(created_at) AS first_seen
                            FROM alerts GROUP BY entity_id)
            SELECT a.entity_id,
                   SUM(CASE WHEN a.created_at >= b.last_seen - INTERVAL 30 DAY
                            THEN 1 ELSE 0 END) AS recent_n,
                   SUM(CASE WHEN a.created_at <  b.last_seen - INTERVAL 30 DAY
                            THEN 1 ELSE 0 END) AS prior_n,
                   greatest(date_diff('day', b.first_seen,
                            b.last_seen - INTERVAL 30 DAY), 1) AS prior_days
            FROM alerts a JOIN bounds b USING (entity_id)
            GROUP BY a.entity_id, b.first_seen, b.last_seen
            """
        ):
            recent = int(r["recent_n"] or 0) / 30.0
            prior = int(r["prior_n"] or 0) / max(int(r["prior_days"] or 1), 1)
            setv(r["entity_id"], "recent_volume_ratio", recent / max(prior, 1e-6))

        commitment = {
            r["entity_id"]: float(r["threshold"] or 15.0)
            for r in ctx.q(
                "SELECT entity_id, threshold FROM commitments "
                "WHERE metric = 'critical_escalation_minutes'"
            )
        }
        for r in ctx.q(
            """
            SELECT entity_id, median(escalation_minutes) AS m
            FROM case_facts WHERE severity = 'critical' AND escalation_minutes IS NOT NULL
            GROUP BY entity_id
            """
        ):
            target = commitment.get(r["entity_id"], 15.0) or 15.0
            setv(
                r["entity_id"],
                "escalation_delay_vs_commitment",
                float(r["m"] or 0) / target,
            )

        day_rows = ctx.q(
            """
            SELECT entity_id, analyst_pseudo, date_trunc('day', closed_at) AS d,
                   COUNT(*) AS n
            FROM case_facts WHERE closed_at IS NOT NULL AND closure_type = 'manual'
            GROUP BY 1, 2, 3
            """
        )
        per_entity: dict[str, list[float]] = {}
        for r in day_rows:
            per_entity.setdefault(r["entity_id"], []).append(float(r["n"]))
        for e, vals in per_entity.items():
            vals_sorted = sorted(vals)
            typical = vals_sorted[len(vals_sorted) // 2] or 1.0
            setv(e, "analyst_concentration", max(vals) / typical)

        for e in out:
            for key in FEATURE_LABELS:
                out[e].setdefault(key, 0.0)
        return out

    # ---------------------------------------------------------------------- run
    def run(self, ctx: RunContext) -> list[Finding]:
        feats = self.features(ctx)
        entities = [e for e in ctx.entity_ids if e in feats]
        if len(entities) < MIN_ENTITIES:
            return []
        keys = list(FEATURE_LABELS)
        matrix = np.array([[feats[e][k] for k in keys] for e in entities], dtype=float)

        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

        scaled = StandardScaler().fit_transform(matrix)
        forest = IsolationForest(
            n_estimators=300,
            contamination=CONTAMINATION,
            random_state=RANDOM_SEED,
            bootstrap=False,
        )
        labels = forest.fit_predict(scaled)
        scores = forest.score_samples(scaled)

        findings: list[Finding] = []
        for i, entity_id in enumerate(entities):
            peers, _ = ctx.peers.peers(entity_id)
            peer_pool = [p for p in entities if p != entity_id]
            zs: list[tuple[str, float, float, float]] = []
            for k in keys:
                peer_vals = [feats[p][k] for p in peer_pool]
                z = robust_z(feats[entity_id][k], peer_vals)
                peer_med = float(np.median(peer_vals)) if peer_vals else 0.0
                zs.append((k, z, feats[entity_id][k], peer_med))
            deviant = [z for z in zs if abs(z[1]) >= DEVIATION_Z]
            if labels[i] != -1 or len(deviant) < MIN_DEVIANT_FEATURES:
                continue
            deviant.sort(key=lambda t: -abs(t[1]))
            top = deviant[:3]
            effect = min(1.0, len(deviant) / 6.0 + min(1.0, abs(top[0][1]) / 8.0) * 0.4)
            conf = confidence_from(len(entities) * 20, effect, MIN_ENTITIES * 20)
            bullets = "; ".join(
                f"{FEATURE_LABELS[k]} is {value:.2f} against a peer median of {pm:.2f} "
                f"(z={z:+.1f})"
                for k, z, value, pm in top
            )
            rationale = (
                "An unsupervised model compared this organisation's whole profile with "
                f"the rest of the portfolio and isolated it as unusual (anomaly score "
                f"{scores[i]:.3f}; lower is more unusual). {len(deviant)} separate "
                f"measures sit far from the peer median. The three largest: {bullets}. "
                "This finding does not name a specific failure - it says the shape of "
                "this organisation's data is unlike its peers and deserves a look."
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Overall profile is an outlier against the portfolio",
                    rationale=rationale,
                    innocent_explanation=(
                        "Being different is not the same as being deficient. A distinct "
                        "technology stack, an unusual business model, or a recent merger "
                        "can all make an organisation's numbers look unlike its peers "
                        "while its SOC is perfectly sound."
                    ),
                    metrics={
                        "anomaly_score": round(float(scores[i]), 4),
                        "contamination": CONTAMINATION,
                        "model": "IsolationForest(n_estimators=300, random_state=42)",
                        "entities_compared": len(entities),
                        "deviant_feature_count": len(deviant),
                        "deviation_z_threshold": DEVIATION_Z,
                        "top_features": [
                            {
                                "feature": k,
                                "plain_english": FEATURE_LABELS[k],
                                "value": round(value, 4),
                                "peer_median": round(pm, 4),
                                "robust_z": round(z, 2),
                            }
                            for k, z, value, pm in deviant[:6]
                        ],
                        "all_features": {
                            k: round(feats[entity_id][k], 4) for k in keys
                        },
                    },
                    evidence_row_ids=[entity_id],
                    evidence_table="entities",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="entity_anomaly",
                )
            )
        return findings
