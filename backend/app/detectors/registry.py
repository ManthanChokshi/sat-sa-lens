"""Detector registry - the single list of everything the analysis runs."""
from __future__ import annotations

from app.detectors.base import Detector
from app.detectors.d01_fast_critical_closure import D01FastCriticalClosure
from app.detectors.d02_critical_no_escalation import D02CriticalNoEscalation
from app.detectors.d03_commitment_breach import D03CommitmentBreach
from app.detectors.d04_template_notes import D04TemplateNotes
from app.detectors.d05_shallow_investigation import D05ShallowInvestigation
from app.detectors.d06_recurring_unremediated import D06RecurringUnremediated
from app.detectors.d07_effort_severity_mismatch import D07EffortSeverityMismatch
from app.detectors.d08_threshold_gaming import D08ThresholdGaming
from app.detectors.d09_analyst_workload import D09AnalystWorkloadImplausible
from app.detectors.d10_silent_critical_assets import D10SilentCriticalAssets
from app.detectors.d11_missing_alert_categories import D11MissingAlertCategories
from app.detectors.d12_volume_drop import D12VolumeDrop
from app.detectors.d13_broken_chain import D13BrokenChain
from app.detectors.d14_entity_anomaly import D14EntityAnomaly
from app.detectors.quality import (
    Q01IdGaps,
    Q02TimeGaps,
    Q03DeclaredCountMismatch,
    Q04TimestampRegularity,
    Q05FileHashRecorded,
)

#: Order matters only for readability of the output; detectors are independent.
DETECTORS: list[Detector] = [
    D01FastCriticalClosure(),
    D02CriticalNoEscalation(),
    D03CommitmentBreach(),
    D04TemplateNotes(),
    D05ShallowInvestigation(),
    D06RecurringUnremediated(),
    D07EffortSeverityMismatch(),
    D08ThresholdGaming(),
    D09AnalystWorkloadImplausible(),
    D10SilentCriticalAssets(),
    D11MissingAlertCategories(),
    D12VolumeDrop(),
    D13BrokenChain(),
    D14EntityAnomaly(),
    Q01IdGaps(),
    Q02TimeGaps(),
    Q03DeclaredCountMismatch(),
    Q04TimestampRegularity(),
    Q05FileHashRecorded(),
]

DETECTOR_BY_ID: dict[str, Detector] = {d.id: d for d in DETECTORS}

#: Detectors that run as part of data-quality checking on import.
QUALITY_DETECTOR_IDS = ["Q01", "Q02", "Q03", "Q04", "Q05"]


def implemented_detector_ids() -> list[str]:
    return [d.id for d in DETECTORS]


def detector_versions() -> dict[str, str]:
    return {d.id: d.version for d in DETECTORS}


def capability_map() -> dict[str, str]:
    return {d.id: d.capability_area for d in DETECTORS}


def catalogue() -> list[dict]:
    """Machine-readable methodology table, used by the UI and the docs."""
    return [
        {
            "detector_id": d.id,
            "name": d.name,
            "version": d.version,
            "gap_type": d.gap_type,
            "capability_area": d.capability_area,
            "min_sample": d.min_sample,
            "description": d.description,
        }
        for d in DETECTORS
    ]
