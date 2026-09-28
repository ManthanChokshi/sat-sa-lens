"""Tiny hand-made datasets for detector unit tests."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import duckdb

from app.db import init_schema
from app.detectors.base import VIEW_SQL, PeerIndex, RunContext

BASE = datetime(2026, 4, 1, 9, 0, 0)


class MiniWorld:
    """An in-memory canonical database you can build row by row."""

    def __init__(self) -> None:
        self.conn = duckdb.connect(":memory:")
        init_schema(self.conn)
        self._case_seq = 0
        self._alert_seq = 0
        self._esc_seq = 0
        self._asset_seq = 0

    # ------------------------------------------------------------------ writers
    def entity(
        self,
        entity_id: str,
        sector: str = "power",
        size_tier: str = "medium",
        analysts: int = 10,
        name: Optional[str] = None,
    ) -> str:
        self.conn.execute(
            "INSERT INTO entities VALUES (?, ?, ?, ?, ?)",
            [entity_id, name or f"Entity {entity_id}", sector, size_tier, analysts],
        )
        return entity_id

    def commitment(self, entity_id: str, metric: str, threshold: float, unit: str) -> None:
        self.conn.execute(
            "INSERT INTO commitments VALUES (?, ?, ?, ?)",
            [entity_id, metric, threshold, unit],
        )

    def asset(
        self,
        entity_id: str,
        criticality: str = "medium",
        asset_type: str = "server",
        environment: str = "prod",
        asset_id: Optional[str] = None,
    ) -> str:
        self._asset_seq += 1
        asset_id = asset_id or f"{entity_id}-AS{self._asset_seq:04d}"
        self.conn.execute(
            "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                asset_id,
                entity_id,
                f"HOST-{self._asset_seq:04d}",
                f"ip-{self._asset_seq:08x}",
                asset_type,
                criticality,
                environment,
            ],
        )
        return asset_id

    def alert(
        self,
        entity_id: str,
        severity: str = "critical",
        category: str = "malware",
        asset_id: Optional[str] = None,
        rule_name: str = "Test rule",
        minutes_offset: int = 0,
        source: str = "edr",
        alert_id: Optional[str] = None,
    ) -> str:
        self._alert_seq += 1
        alert_id = alert_id or f"{entity_id}-A{self._alert_seq:06d}"
        self.conn.execute(
            "INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                alert_id,
                entity_id,
                asset_id,
                rule_name,
                category,
                severity,
                source,
                BASE + timedelta(minutes=minutes_offset),
            ],
        )
        return alert_id

    def case(
        self,
        entity_id: str,
        alert_id: Optional[str],
        handling_minutes: float = 60.0,
        closure_type: str = "manual",
        disposition: str = "false_positive",
        notes: str = "Investigated on HOST-0001 (ip-0000000a) for usr-0000000b. Host isolated.",
        analyst: str = "an-1",
        minutes_offset: int = 0,
        closed: bool = True,
        case_id: Optional[str] = None,
    ) -> str:
        self._case_seq += 1
        case_id = case_id or f"{entity_id}-C{self._case_seq:06d}"
        opened = BASE + timedelta(minutes=minutes_offset)
        closed_at = opened + timedelta(minutes=handling_minutes) if closed else None
        self.conn.execute(
            "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                case_id,
                entity_id,
                alert_id,
                analyst,
                opened,
                closed_at,
                disposition,
                closure_type,
                notes,
            ],
        )
        return case_id

    def escalation(
        self,
        entity_id: str,
        case_id: str,
        minutes_after_open: float = 5.0,
        from_tier: str = "tier1",
        to_tier: str = "tier2",
    ) -> str:
        self._esc_seq += 1
        esc_id = f"{entity_id}-E{self._esc_seq:05d}"
        row = self.conn.execute(
            "SELECT opened_at FROM cases WHERE case_id = ?", [case_id]
        ).fetchone()
        opened = row[0] if row else BASE
        self.conn.execute(
            "INSERT INTO escalations VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                esc_id,
                case_id,
                entity_id,
                from_tier,
                to_tier,
                opened + timedelta(minutes=minutes_after_open),
                "Confirmed true positive",
            ],
        )
        return esc_id

    def submission(
        self,
        entity_id: str,
        declared: int,
        days: int = 30,
        file_hash: str = "a" * 64,
        submission_id: Optional[str] = None,
    ) -> str:
        self._case_seq += 0
        sid = submission_id or f"{entity_id}-SUB{declared}"
        self.conn.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                sid,
                entity_id,
                BASE - timedelta(days=1),
                BASE + timedelta(days=days),
                declared,
                file_hash,
                BASE + timedelta(days=days + 1),
                "declared",
            ],
        )
        return sid

    # --------------------------------------------------------------- run context
    def ctx(self, run_id: str = "RUN-TEST") -> RunContext:
        for stmt in filter(None, (s.strip() for s in VIEW_SQL.split(";"))):
            self.conn.execute(stmt)
        rows = self.conn.execute(
            "SELECT entity_id, name, sector, size_tier, analyst_count FROM entities"
        ).fetchall()
        entities = {
            r[0]: {
                "entity_id": r[0],
                "name": r[1],
                "sector": r[2],
                "size_tier": r[3],
                "analyst_count": r[4],
            }
            for r in rows
        }
        return RunContext(conn=self.conn, run_id=run_id, peers=PeerIndex(entities))


def healthy_entity(
    world: MiniWorld,
    entity_id: str,
    n_critical: int = 40,
    n_medium: int = 40,
    escalate: bool = True,
) -> None:
    """A clean reference entity used as a peer baseline in unit tests."""
    world.entity(entity_id)
    asset = world.asset(entity_id, criticality="critical")
    other = world.asset(entity_id, criticality="medium")
    for i in range(n_critical):
        a = world.alert(entity_id, "critical", asset_id=asset, minutes_offset=i * 31)
        c = world.case(entity_id, a, handling_minutes=150, minutes_offset=i * 31 + 2)
        if escalate:
            world.escalation(entity_id, c)
    for i in range(n_medium):
        a = world.alert(entity_id, "medium", asset_id=other, minutes_offset=i * 37)
        world.case(entity_id, a, handling_minutes=40, minutes_offset=i * 37 + 2)
