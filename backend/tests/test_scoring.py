"""Scoring behaviour: monotonicity, bands and supervisor exclusion."""
from __future__ import annotations

from app.scoring.score import (
    band_for,
    capability_scores,
    entity_risk,
    finding_weight,
    normalise_risk,
)
from app.schema import CAPABILITY_AREAS


def make(severity: str, confidence: float, area: str = "investigation", n: int = 1):
    return [
        {
            "finding_id": f"F{area}{severity}{i}",
            "entity_id": "E1",
            "detector_id": "D01",
            "gap_type": "execution_gap",
            "capability_area": area,
            "severity": severity,
            "confidence": confidence,
            "title": "t",
            "status": "open",
        }
        for i in range(n)
    ]


def test_more_findings_never_lower_the_risk_score():
    scores = [entity_risk(make("high", 0.9, n=k))["risk_score"] for k in range(0, 6)]
    assert scores == sorted(scores)
    assert scores[0] == 0.0


def test_higher_severity_scores_higher():
    low = entity_risk(make("low", 0.9))["risk_score"]
    med = entity_risk(make("medium", 0.9))["risk_score"]
    high = entity_risk(make("high", 0.9))["risk_score"]
    assert low < med < high


def test_higher_confidence_scores_higher():
    a = entity_risk(make("high", 0.4))["risk_score"]
    b = entity_risk(make("high", 0.9))["risk_score"]
    assert a < b


def test_healthy_entity_is_low_risk():
    result = entity_risk([])
    assert result["risk_score"] == 0.0
    assert result["risk_band"] == "Low"
    assert result["top_contributors"] == []


def test_bands_are_ordered():
    assert band_for(0) == "Low"
    assert band_for(45) == "Medium"
    assert band_for(85) == "High"


def test_capability_scores_start_at_100_and_only_drop_where_flagged():
    caps = capability_scores(make("high", 0.9, area="escalation", n=3))
    assert set(caps) == set(CAPABILITY_AREAS)
    assert caps["escalation"] < 60
    assert caps["threat_detection"] == 100.0


def test_top_three_contributors_are_the_heaviest():
    findings = make("low", 0.5) + make("high", 0.95) + make("medium", 0.8)
    result = entity_risk(findings)
    assert len(result["top_contributors"]) == 3
    weights = [c["weight"] for c in result["top_contributors"]]
    assert weights == sorted(weights, reverse=True)


def test_risk_score_is_bounded():
    assert normalise_risk(0) == 0.0
    assert normalise_risk(10_000) <= 100.0
    assert finding_weight("high", 1.0) > finding_weight("high", 0.5)
