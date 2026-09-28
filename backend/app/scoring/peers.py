"""Peer-group construction."""
from __future__ import annotations

from app.db import fetch_dicts
from app.detectors.base import PeerIndex


def build_peer_index() -> PeerIndex:
    rows = fetch_dicts(
        "SELECT entity_id, name, sector, size_tier, analyst_count FROM entities "
        "ORDER BY entity_id"
    )
    return PeerIndex({r["entity_id"]: r for r in rows})


def peer_groups() -> list[dict]:
    """Human-readable summary of the groups, for the UI methodology panel."""
    idx = build_peer_index()
    out = []
    for entity_id in sorted(idx.entities):
        peers, level = idx.peers(entity_id)
        out.append(
            {
                "entity_id": entity_id,
                "peer_group": idx.label(entity_id),
                "comparison_level": level,
                "peers": peers,
            }
        )
    return out
