"""Canonical Pydantic models for SAT-SA Lens."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Sector = Literal["power", "banking", "telecom", "oil_gas", "transport"]
SizeTier = Literal["small", "medium", "large"]
AssetType = Literal["server", "db", "workstation", "network", "ot", "cloud"]
Criticality = Literal["critical", "high", "medium", "low"]
Environment = Literal["prod", "dev", "ot"]
Severity = Literal["critical", "high", "medium", "low", "info"]
Source = Literal["edr", "siem", "ids", "email_gateway", "firewall", "ot_monitor"]
Disposition = Literal["true_positive", "false_positive", "benign", "duplicate", "unresolved"]
ClosureType = Literal["manual", "automated"]

ALERT_CATEGORIES = [
    "initial_access",
    "execution",
    "persistence",
    "privilege_escalation",
    "defense_evasion",
    "credential_access",
    "discovery",
    "lateral_movement",
    "collection",
    "exfiltration",
    "command_and_control",
    "impact",
    "phishing",
    "malware",
    "policy_violation",
]

GapType = Literal["execution_gap", "negative_space", "anomaly", "data_quality"]
CapabilityArea = Literal[
    "threat_detection",
    "investigation",
    "escalation",
    "incident_response",
    "security_operations",
    "governance_oversight",
    "operational_discipline",
    "cyber_resilience",
]
CAPABILITY_AREAS: list[str] = [
    "threat_detection",
    "investigation",
    "escalation",
    "incident_response",
    "security_operations",
    "governance_oversight",
    "operational_discipline",
    "cyber_resilience",
]
FindingSeverity = Literal["high", "medium", "low"]
FindingStatus = Literal["open", "valid", "not_valid"]

SEVERITY_MAP: dict[str, str] = {
    "p1": "critical", "sev1": "critical", "severity1": "critical", "5": "critical",
    "crit": "critical", "critical": "critical", "cri": "critical", "urgent": "critical",
    "p2": "high", "sev2": "high", "4": "high", "high": "high", "hi": "high", "major": "high",
    "p3": "medium", "sev3": "medium", "3": "medium", "medium": "medium", "med": "medium",
    "moderate": "medium",
    "p4": "low", "sev4": "low", "2": "low", "low": "low", "minor": "low",
    "p5": "info", "sev5": "info", "1": "info", "info": "info", "informational": "info",
    "0": "info",
}


def normalise_severity(raw: Any) -> str:
    """Map any vendor severity label onto the canonical five-level scale."""
    if raw is None:
        return "info"
    key = str(raw).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    return SEVERITY_MAP.get(key, "info")


class Entity(BaseModel):
    entity_id: str
    name: str
    sector: Sector
    size_tier: SizeTier
    analyst_count: int


class Commitment(BaseModel):
    entity_id: str
    metric: str
    threshold: float
    unit: str


class Asset(BaseModel):
    asset_id: str
    entity_id: str
    hostname: str
    ip_pseudo: str
    asset_type: AssetType
    criticality: Criticality
    environment: Environment


class Alert(BaseModel):
    alert_id: str
    entity_id: str
    asset_id: Optional[str] = None
    rule_name: str
    category: str
    severity: Severity
    source: Source
    created_at: datetime


class Case(BaseModel):
    case_id: str
    entity_id: str
    alert_id: Optional[str] = None
    analyst_pseudo: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    disposition: Disposition
    closure_type: ClosureType
    notes: str = ""


class Escalation(BaseModel):
    escalation_id: str
    case_id: str
    entity_id: str
    from_tier: str
    to_tier: str
    escalated_at: datetime
    reason: str = ""


class Submission(BaseModel):
    submission_id: str
    entity_id: str
    period_start: datetime
    period_end: datetime
    declared_alert_count: int
    file_hash: str
    uploaded_at: datetime
    integrity_status: str = "unknown"


class Finding(BaseModel):
    """The single output object of every detector. Explainability fields are required."""

    finding_id: str
    run_id: str
    entity_id: str
    detector_id: str
    detector_version: str
    gap_type: GapType
    capability_area: CapabilityArea
    severity: FindingSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    title: str
    rationale: str
    innocent_explanation: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence_row_ids: list[str] = Field(default_factory=list)
    evidence_table: str = ""
    status: FindingStatus = "open"
    supervisor_note: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FindingUpdate(BaseModel):
    status: Optional[FindingStatus] = None
    supervisor_note: Optional[str] = None
    actor: str = "supervisor"
