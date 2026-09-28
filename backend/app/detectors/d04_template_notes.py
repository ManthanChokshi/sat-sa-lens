"""D04 - near-duplicate ("copy-paste") investigation notes.

Two-stage, so it stays fast on a full submission:
  1. collapse identical note text (a template family collapses to one row);
  2. embed the distinct texts and cluster them greedily at cosine > 0.92,
     weighting each cluster by how many cases used that text.
"""
from __future__ import annotations

import numpy as np

from app.config import RANDOM_SEED
from app.detectors.base import (
    Detector,
    RunContext,
    confidence_from,
    median,
    pct,
    severity_from_confidence,
)
from app.ml.embeddings import embed, greedy_cosine_clusters
from app.schema import Finding

SIMILARITY_THRESHOLD = 0.92
SAMPLE_LIMIT = 5000          # cases sampled per entity (seeded)
DISTINCT_LIMIT = 2500        # distinct texts embedded per entity
MIN_NOTES = 50
MIN_SHARE = 0.45
PEER_MARGIN = 0.18
MIN_CLUSTER_SIZE = 3


class D04TemplateNotes(Detector):
    id = "D04"
    version = "1.2.0"
    name = "template_notes"
    gap_type = "execution_gap"
    capability_area = "operational_discipline"
    min_sample = MIN_NOTES
    description = (
        "Investigation notes that are near-duplicates of each other, which suggests "
        "cases are being closed with a template rather than an investigation."
    )

    def _entity_share(self, ctx: RunContext, entity_id: str) -> dict | None:
        rows = ctx.q(
            """
            SELECT case_id, notes FROM case_facts
            WHERE entity_id = ? AND closure_type = 'manual'
              AND notes IS NOT NULL AND length(trim(notes)) > 0
            ORDER BY case_id
            """,
            [entity_id],
        )
        if len(rows) < MIN_NOTES:
            return None
        rng = np.random.default_rng(RANDOM_SEED)
        if len(rows) > SAMPLE_LIMIT:
            pick = np.sort(rng.choice(len(rows), size=SAMPLE_LIMIT, replace=False))
            rows = [rows[i] for i in pick]

        # Stage 1: collapse identical text.
        groups: dict[str, list[str]] = {}
        for r in rows:
            groups.setdefault(r["notes"], []).append(r["case_id"])
        texts = sorted(groups)
        truncated = False
        if len(texts) > DISTINCT_LIMIT:
            # Keep the most-used texts: they are what a template looks like.
            texts = sorted(texts, key=lambda t: (-len(groups[t]), t))[:DISTINCT_LIMIT]
            truncated = True
        weights = np.array([len(groups[t]) for t in texts], dtype=float)
        total_weight = float(weights.sum())

        # Stage 2: embed distinct texts and cluster.
        result = embed(texts)
        labels = greedy_cosine_clusters(result.vectors, SIMILARITY_THRESHOLD)
        sizes: dict[int, float] = {}
        for lab, w in zip(labels, weights):
            sizes[lab] = sizes.get(lab, 0.0) + w
        duplicated = sum(w for w in sizes.values() if w >= MIN_CLUSTER_SIZE)
        share = duplicated / total_weight

        top = sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        examples, members = [], []
        for lab, size in top:
            if size < MIN_CLUSTER_SIZE:
                continue
            idxs = [i for i, l in enumerate(labels) if l == lab]
            examples.append(
                {
                    "cases_in_cluster": int(size),
                    "distinct_texts_in_cluster": len(idxs),
                    "share_of_notes": round(size / total_weight, 4),
                    "example_note": texts[idxs[0]][:220],
                }
            )
            for i in idxs[:50]:
                members.extend(groups[texts[i]][:40])
        return {
            "cases_analysed": int(total_weight),
            "distinct_note_texts": len(texts),
            "clusters": len(sizes),
            "share_in_duplicate_clusters": round(share, 4),
            "largest_cluster_share": round(max(sizes.values()) / total_weight, 4),
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "min_cluster_size": MIN_CLUSTER_SIZE,
            "embedding_method": result.method,
            "embedding_model": result.model_name,
            "embedding_dimensions": result.dimensions,
            "distinct_texts_truncated": truncated,
            "top_clusters": examples,
            "_share": share,
            "_members": members[:2000],
        }

    def run(self, ctx: RunContext) -> list[Finding]:
        computed: dict[str, dict] = {}
        for entity_id in ctx.entity_ids:
            res = self._entity_share(ctx, entity_id)
            if res:
                computed[entity_id] = res
        shares = {e: r["_share"] for e, r in computed.items()}

        findings: list[Finding] = []
        for entity_id, res in computed.items():
            share = res["_share"]
            peers, _ = ctx.peers.peers(entity_id)
            peer_share = median([shares[p] for p in peers if p in shares])
            if share < max(MIN_SHARE, peer_share + PEER_MARGIN):
                continue
            metrics = {k: v for k, v in res.items() if not k.startswith("_")}
            metrics["peer_median_share"] = round(peer_share, 4)
            effect = min(1.0, share / 0.8)
            conf = confidence_from(res["cases_analysed"], effect, MIN_NOTES)
            biggest = res["top_clusters"][0] if res["top_clusters"] else {}
            rationale = (
                f"{pct(share)} of manually closed cases here carry an investigation "
                f"note that is a near-duplicate of other notes (cosine similarity above "
                f"{SIMILARITY_THRESHOLD}). Peers sit at {pct(peer_share)}. Only "
                f"{res['distinct_note_texts']:,} distinct note texts cover "
                f"{res['cases_analysed']:,} cases. The largest single template covers "
                f"{pct(res['largest_cluster_share'])} of notes"
                + (f': "{biggest.get("example_note", "")}".' if biggest else ".")
            )
            findings.append(
                self.finding(
                    ctx,
                    entity_id,
                    title="Investigation notes are copy-paste templates",
                    rationale=rationale,
                    innocent_explanation=(
                        "High-volume, well-understood alert types are legitimately closed "
                        "with a standard phrase, and some case-management tools insert "
                        "boiler-plate text automatically. A repeated note is only a "
                        "problem if the underlying alerts actually differed."
                    ),
                    metrics=metrics,
                    evidence_row_ids=res["_members"],
                    evidence_table="cases",
                    severity=severity_from_confidence(effect, conf),
                    confidence=conf,
                    key="template_notes",
                )
            )
        return findings
