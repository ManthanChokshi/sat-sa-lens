"""Foreign-format column mapping and value normalisation."""
from __future__ import annotations

import pandas as pd

from app.ingest.mapping import apply_mapping, suggest_mapping, suggest_value_map
from app.schema import normalise_severity

FOREIGN_ALERTS = pd.DataFrame(
    {
        "Ticket No": ["T-1", "T-2", "T-3"],
        "Device": ["E1-AS001", "E1-AS002", "E1-AS003"],
        "Detection Rule": [
            "Suspicious PowerShell EncodedCommand",
            "Phishing URL clicked",
            "Beaconing to known C2 infrastructure",
        ],
        "Attack Stage": ["execution", "phishing", "command_and_control"],
        "Sev": ["P1", "P3", "P2"],
        "Feed": ["edr", "email_gateway", "ids"],
        "Opened": ["2026-04-01 09:15:00", "2026-04-01 11:20:10", "2026-04-02 03:00:00"],
    }
)

FOREIGN_CASES = pd.DataFrame(
    {
        "Ref": ["C-1", "C-2"],
        "Ticket No": ["T-1", "T-2"],
        "Assignee": ["Priya Sharma", "Rahul Verma"],
        "Opened": ["2026-04-01 09:20:00", "2026-04-01 11:30:00"],
        "Resolved": ["2026-04-01 09:21:00", "2026-04-01 13:05:00"],
        "Outcome": ["False Positive", "True Positive"],
        "How Closed": ["Manual", "Automated"],
        "Comments": ["checked, closing", "Escalated to tier2 after host isolation"],
    }
)


def test_alert_mapping_is_suggested_correctly():
    s = suggest_mapping("alerts", FOREIGN_ALERTS)
    assert s["mapping"]["alert_id"] == "Ticket No"
    assert s["mapping"]["rule_name"] == "Detection Rule"
    assert s["mapping"]["severity"] == "Sev"
    assert s["mapping"]["created_at"] == "Opened"
    assert s["mapping"]["category"] == "Attack Stage"
    assert s["missing_required"] == []
    assert s["value_map"]["severity"]["P1"] == "critical"


def test_case_mapping_handles_ambiguous_opened_column():
    s = suggest_mapping("cases", FOREIGN_CASES)
    assert s["mapping"]["case_id"] == "Ref"
    assert s["mapping"]["analyst_name"] == "Assignee"
    assert s["mapping"]["opened_at"] == "Opened"
    assert s["mapping"]["closed_at"] == "Resolved"
    assert s["mapping"]["notes"] == "Comments"


def test_apply_mapping_normalises_values():
    s = suggest_mapping("alerts", FOREIGN_ALERTS)
    out = apply_mapping(FOREIGN_ALERTS, "alerts", s["mapping"], s["value_map"], "E1")
    assert list(out["severity"]) == ["critical", "medium", "high"]
    assert set(out["entity_id"]) == {"E1"}

    sc = suggest_mapping("cases", FOREIGN_CASES)
    out_cases = apply_mapping(FOREIGN_CASES, "cases", sc["mapping"], sc["value_map"], "E1")
    assert list(out_cases["disposition"]) == ["false_positive", "true_positive"]
    assert list(out_cases["closure_type"]) == ["manual", "automated"]


def test_severity_value_map_covers_vendor_scales():
    series = pd.Series(["P1", "Sev2", "3", "Low", "informational", "CRITICAL"])
    vmap = suggest_value_map(series)
    assert vmap["P1"] == "critical"
    assert vmap["Sev2"] == "high"
    assert vmap["3"] == "medium"
    assert vmap["Low"] == "low"
    assert vmap["informational"] == "info"
    assert vmap["CRITICAL"] == "critical"


def test_unknown_severity_falls_back_to_info():
    assert normalise_severity("banana") == "info"
    assert normalise_severity(None) == "info"
