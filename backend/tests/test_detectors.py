"""Unit tests for every detector on a tiny hand-made dataset.

Each test contains at least one entity that MUST be flagged and one that MUST
NOT, so a detector that simply fires on everything fails the suite.
"""
from __future__ import annotations

from tests.factories import MiniWorld, healthy_entity


def flagged(findings) -> set[str]:
    return {f.entity_id for f in findings}


# ------------------------------------------------------------------------- D01
def test_d01_flags_fast_manual_closure_and_spares_automation():
    from app.detectors.d01_fast_critical_closure import D01FastCriticalClosure

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        healthy_entity(w, peer)
    # BAD: closes criticals by hand in seconds.
    w.entity("BAD")
    a_bad = w.asset("BAD", criticality="critical")
    for i in range(60):
        a = w.alert("BAD", "critical", asset_id=a_bad, minutes_offset=i * 20)
        w.case("BAD", a, handling_minutes=0.5, minutes_offset=i * 20 + 1)
    # INNOCENT: equally fast, but every closure is automated.
    w.entity("AUTO")
    a_auto = w.asset("AUTO", criticality="critical")
    for i in range(60):
        a = w.alert("AUTO", "critical", asset_id=a_auto, minutes_offset=i * 20)
        w.case(
            "AUTO", a, handling_minutes=0.5, closure_type="automated",
            minutes_offset=i * 20 + 1,
        )

    out = D01FastCriticalClosure().run(w.ctx())
    assert "BAD" in flagged(out)
    assert "AUTO" not in flagged(out)
    assert "P1" not in flagged(out)
    bad = next(f for f in out if f.entity_id == "BAD")
    assert bad.metrics["share_closed_under_2_min"] > 0.9
    assert bad.evidence_row_ids
    assert bad.rationale and bad.innocent_explanation


# ------------------------------------------------------------------------- D02
def test_d02_flags_missing_escalations_only():
    from app.detectors.d02_critical_no_escalation import D02CriticalNoEscalation

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        healthy_entity(w, peer)
    w.entity("BAD")
    asset = w.asset("BAD", criticality="critical")
    for i in range(50):
        a = w.alert("BAD", "critical", asset_id=asset, minutes_offset=i * 25)
        w.case("BAD", a, handling_minutes=120, minutes_offset=i * 25 + 2)

    out = D02CriticalNoEscalation().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["share_without_escalation"] == 1.0


# ------------------------------------------------------------------------- D03
def test_d03_flags_only_the_breached_commitment():
    from app.detectors.d03_commitment_breach import D03CommitmentBreach

    w = MiniWorld()
    for eid in ("GOOD", "BAD"):
        healthy_entity(w, eid)
        w.commitment(eid, "critical_escalation_minutes", 15.0, "minutes")
        w.commitment(eid, "critical_alert_investigation_minutes", 240.0, "minutes")
    # BAD escalates its criticals three hours late.
    w.conn.execute(
        "UPDATE escalations SET escalated_at = escalated_at + INTERVAL 180 MINUTE "
        "WHERE entity_id = 'BAD'"
    )
    out = D03CommitmentBreach().run(w.ctx())
    assert flagged(out) == {"BAD"}
    f = next(iter(out))
    assert f.metrics["metric"] == "critical_escalation_minutes"
    assert f.metrics["actual_value"] > 15


# ------------------------------------------------------------------------- D04
def test_d04_flags_template_notes_only():
    from app.detectors.d04_template_notes import D04TemplateNotes

    w = MiniWorld()
    varied = [
        "Triaged alert on HOST-0001 (ip-0000000a) for usr-0000000b. "
        "Confirmed approved change window. Host isolated via EDR.",
        "Reviewed proxy logs for HOST-0002 (ip-0000000c). Sandbox verdict benign. "
        "Added hash 0123456789abcdef0 to the block list.",
        "Escalated to tier2 after finding lateral movement from HOST-0003 "
        "(ip-0000000d) by usr-0000000e. Account disabled.",
        "Correlated with the vulnerability scanner schedule on HOST-0004. "
        "No second stage download. Rule tuned.",
    ]
    for peer in ("P1", "P2", "P3"):
        w.entity(peer)
        for i in range(60):
            a = w.alert(peer, "medium", minutes_offset=i * 11)
            w.case(peer, a, notes=f"{varied[i % 4]} Case sequence {i} unique detail {i * 7}.")
    w.entity("BAD")
    for i in range(60):
        a = w.alert("BAD", "medium", minutes_offset=i * 11)
        w.case("BAD", a, notes="checked, false positive")

    out = D04TemplateNotes().run(w.ctx())
    assert "BAD" in flagged(out)
    assert "P1" not in flagged(out)
    f = next(f for f in out if f.entity_id == "BAD")
    assert f.metrics["share_in_duplicate_clusters"] > 0.9
    assert f.metrics["embedding_method"]


# ------------------------------------------------------------------------- D05
def test_d05_flags_notes_without_artefacts_only():
    from app.detectors.d05_shallow_investigation import D05ShallowInvestigation

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        w.entity(peer)
        for i in range(60):
            a = w.alert(peer, "medium", minutes_offset=i * 9)
            w.case(
                peer, a,
                notes=f"Checked HOST-{i:04d} at ip-0000{i:04x} for usr-0000000b; blocked.",
            )
    w.entity("BAD")
    for i in range(60):
        a = w.alert("BAD", "medium", minutes_offset=i * 9)
        w.case("BAD", a, notes="looked into it, seems fine")

    out = D05ShallowInvestigation().run(w.ctx())
    assert flagged(out) == {"BAD"}


# ------------------------------------------------------------------------- D06
def test_d06_flags_recurring_unremediated_pair_only():
    from app.detectors.d06_recurring_unremediated import D06RecurringUnremediated

    w = MiniWorld()
    healthy_entity(w, "GOOD")
    w.entity("BAD")
    asset = w.asset("BAD", criticality="critical")
    for day in range(40):
        a = w.alert(
            "BAD", "high", asset_id=asset, rule_name="Registry Run key modified",
            minutes_offset=day * 24 * 60,
        )
        w.case("BAD", a, handling_minutes=10, minutes_offset=day * 24 * 60 + 5)

    out = D06RecurringUnremediated().run(w.ctx())
    assert flagged(out) == {"BAD"}
    f = next(iter(out))
    assert f.metrics["worst_occurrences"] >= 40
    assert f.metrics["worst_distinct_days"] >= 40


# ------------------------------------------------------------------------- D07
def test_d07_flags_flat_effort_only():
    from app.detectors.d07_effort_severity_mismatch import D07EffortSeverityMismatch

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        healthy_entity(w, peer)
    w.entity("BAD")
    for i in range(40):
        a = w.alert("BAD", "critical", minutes_offset=i * 21)
        w.case("BAD", a, handling_minutes=25, minutes_offset=i * 21 + 1)
        b = w.alert("BAD", "medium", minutes_offset=i * 23)
        w.case("BAD", b, handling_minutes=25, minutes_offset=i * 23 + 1)

    out = D07EffortSeverityMismatch().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["critical_to_medium_ratio"] < 1.35


# ------------------------------------------------------------------------- D08
def test_d08_flags_sla_pileup_only():
    from app.detectors.d08_threshold_gaming import D08ThresholdGaming

    w = MiniWorld()
    for eid in ("GOOD", "BAD"):
        w.entity(eid)
        w.commitment(eid, "high_alert_investigation_minutes", 30.0, "minutes")
    # GOOD: a natural spread of handling times around the SLA.
    for i in range(200):
        a = w.alert("GOOD", "high", minutes_offset=i * 7)
        w.case("GOOD", a, handling_minutes=5 + (i % 60), minutes_offset=i * 7 + 1)
    # BAD: everything lands at 28-29 minutes, just inside the 30-minute SLA.
    for i in range(200):
        a = w.alert("BAD", "high", minutes_offset=i * 7)
        w.case(
            "BAD", a,
            handling_minutes=28.0 + (i % 20) * 0.09,
            minutes_offset=i * 7 + 1,
        )

    out = D08ThresholdGaming().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["pileup_ratio"] >= 3


# ------------------------------------------------------------------------- D09
def test_d09_flags_implausible_workload_only():
    from app.detectors.d09_analyst_workload import D09AnalystWorkloadImplausible

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        w.entity(peer)
        for i in range(60):
            a = w.alert(peer, "medium", minutes_offset=i * 60)
            w.case(peer, a, analyst=f"an-{i % 6}", minutes_offset=i * 60)
    w.entity("BAD")
    day = 24 * 60
    # 30 ordinary days of work...
    for d in range(30):
        for k in range(6):
            a = w.alert("BAD", "medium", minutes_offset=d * day + k * 90)
            w.case("BAD", a, analyst=f"an-{k % 5}", minutes_offset=d * day + k * 90)
    # ...then one analyst closing 400 cases inside a single shift.
    for i in range(400):
        a = w.alert("BAD", "medium", minutes_offset=31 * day + i)
        w.case("BAD", a, handling_minutes=1, analyst="an-hero", minutes_offset=31 * day + i)

    out = D09AnalystWorkloadImplausible().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["worst_closures"] >= 110


# ------------------------------------------------------------------------- D10
def test_d10_flags_silent_critical_assets_only():
    from app.detectors.d10_silent_critical_assets import D10SilentCriticalAssets

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        w.entity(peer)
        for i in range(10):
            asset = w.asset(peer, criticality="critical")
            for j in range(3):
                w.alert(peer, "high", asset_id=asset, minutes_offset=i * 60 + j)
    w.entity("BAD")
    loud = w.asset("BAD", criticality="critical")
    for j in range(5):
        w.alert("BAD", "high", asset_id=loud, minutes_offset=j)
    for _ in range(9):
        w.asset("BAD", criticality="critical", asset_type="db")

    out = D10SilentCriticalAssets().run(w.ctx())
    assert flagged(out) == {"BAD"}
    f = next(iter(out))
    assert f.metrics["silent_critical_assets"] == 9
    assert f.evidence_table == "assets"


# ------------------------------------------------------------------------- D11
def test_d11_flags_missing_categories_only():
    from app.detectors.d11_missing_alert_categories import D11MissingAlertCategories

    w = MiniWorld()
    cats = ["phishing", "malware", "execution", "credential_access"]
    for peer in ("P1", "P2", "P3"):
        w.entity(peer)
        for i in range(400):
            w.alert(peer, "medium", category=cats[i % len(cats)], minutes_offset=i)
    w.entity("BAD")
    for i in range(400):
        w.alert("BAD", "medium", category=cats[1 + i % 3], minutes_offset=i)

    out = D11MissingAlertCategories().run(w.ctx())
    assert flagged(out) == {"BAD"}
    f = next(iter(out))
    assert [m["category"] for m in f.metrics["missing_categories"]] == ["phishing"]


# ------------------------------------------------------------------------- D12
def test_d12_flags_volume_collapse_only():
    from app.detectors.d12_volume_drop import D12VolumeDrop

    w = MiniWorld()
    day = 24 * 60
    for eid, recent_per_day in (("GOOD", 20), ("BAD", 2)):
        w.entity(eid)
        for d in range(60):
            for k in range(20):
                w.alert(eid, "medium", minutes_offset=d * day + k * 5)
        for d in range(60, 90):
            for k in range(recent_per_day):
                w.alert(eid, "medium", minutes_offset=d * day + k * 5)

    out = D12VolumeDrop().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["drop_share"] > 0.8


# ------------------------------------------------------------------------- D13
def test_d13_flags_broken_chains_only():
    from app.detectors.d13_broken_chain import D13BrokenChain

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        healthy_entity(w, peer)
    w.entity("BAD")
    asset = w.asset("BAD", criticality="critical")
    for i in range(40):
        a = w.alert("BAD", "critical", asset_id=asset, minutes_offset=i * 30)
        w.case(
            "BAD", a, handling_minutes=90, disposition="true_positive",
            minutes_offset=i * 30 + 1,
        )
    for i in range(20):
        w.case("BAD", None, handling_minutes=30, minutes_offset=5000 + i)

    out = D13BrokenChain().run(w.ctx())
    assert "BAD" in flagged(out)
    assert "P1" not in flagged(out)
    f = next(f for f in out if f.entity_id == "BAD")
    assert f.metrics["orphan_cases_without_alert"] == 20
    assert f.metrics["behavioural_signal"] is True


# ------------------------------------------------------------------------- D14
def test_d14_needs_enough_entities_and_explains_itself():
    from app.detectors.d14_entity_anomaly import D14EntityAnomaly

    w = MiniWorld()
    for i in range(8):
        healthy_entity(w, f"P{i}", n_critical=25, n_medium=25)
    w.entity("ODD")
    asset = w.asset("ODD", criticality="critical")
    for _ in range(9):
        w.asset("ODD", criticality="critical", asset_type="db")
    for i in range(25):
        a = w.alert("ODD", "critical", asset_id=asset, minutes_offset=i * 30)
        w.case(
            "ODD", a, handling_minutes=1, notes="checked, false positive",
            minutes_offset=i * 30 + 1,
        )
    for i in range(25):
        a = w.alert("ODD", "medium", asset_id=asset, minutes_offset=i * 33)
        w.case(
            "ODD", a, handling_minutes=60, notes="checked, false positive",
            minutes_offset=i * 33 + 1,
        )

    out = D14EntityAnomaly().run(w.ctx())
    assert "ODD" in flagged(out)
    f = next(f for f in out if f.entity_id == "ODD")
    assert len(f.metrics["top_features"]) >= 2
    assert all("plain_english" in t for t in f.metrics["top_features"])


def test_d14_silent_with_too_few_entities():
    from app.detectors.d14_entity_anomaly import D14EntityAnomaly

    w = MiniWorld()
    healthy_entity(w, "ONLY")
    assert D14EntityAnomaly().run(w.ctx()) == []


# ------------------------------------------------------------------ Q01 - Q05
def test_q01_flags_contiguous_id_block_only():
    from app.detectors.quality import Q01IdGaps

    w = MiniWorld()
    # Q01 only speaks when the ID space is otherwise dense, so the fixture needs
    # enough rows for a 100-ID block to be the exception rather than the rule.
    w.entity("GOOD")
    for i in range(5000):
        w.alert("GOOD", "medium", alert_id=f"GOOD-A{i:06d}", minutes_offset=i)
    w.entity("BAD")
    for i in range(5000):
        if 3000 <= i < 3100:
            continue
        w.alert("BAD", "medium", alert_id=f"BAD-A{i:06d}", minutes_offset=i)

    out = Q01IdGaps().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["longest_missing_run"] == 100


def test_q02_flags_missing_week_only():
    from app.detectors.quality import Q02TimeGaps

    day = 24 * 60
    w = MiniWorld()
    w.entity("GOOD")
    for d in range(40):
        for k in range(6):
            w.alert("GOOD", "medium", minutes_offset=d * day + k * 60)
    w.entity("BAD")
    for d in range(40):
        if 15 <= d < 22:
            continue
        for k in range(6):
            w.alert("BAD", "medium", minutes_offset=d * day + k * 60)

    out = Q02TimeGaps().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["longest_gap_days"] == 7


def test_q03_flags_declared_count_mismatch_only():
    from app.detectors.quality import Q03DeclaredCountMismatch

    w = MiniWorld()
    for eid, declared in (("GOOD", 100), ("BAD", 400)):
        w.entity(eid)
        for i in range(100):
            w.alert(eid, "medium", minutes_offset=i * 10)
        w.submission(eid, declared)

    out = Q03DeclaredCountMismatch().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["difference"] == 300


def test_q04_flags_rounded_timestamps_only():
    from app.detectors.quality import Q04TimestampRegularity

    w = MiniWorld()
    w.entity("GOOD")
    for i in range(1000):
        w.alert("GOOD", "medium", minutes_offset=i * 7 + (i % 53))
    w.entity("BAD")
    for i in range(1000):
        w.alert("BAD", "medium", minutes_offset=i * 60)

    out = Q04TimestampRegularity().run(w.ctx())
    assert flagged(out) == {"BAD"}
    assert next(iter(out)).metrics["share_on_the_hour"] > 0.9


def test_q05_flags_missing_file_hash_only():
    from app.detectors.quality import Q05FileHashRecorded

    w = MiniWorld()
    w.entity("GOOD")
    w.submission("GOOD", 10, file_hash="b" * 64)
    w.entity("BAD")
    w.submission("BAD", 10, file_hash="")

    out = Q05FileHashRecorded().run(w.ctx())
    assert flagged(out) == {"BAD"}


# ----------------------------------------------------------- framework contract
def test_every_finding_is_explainable():
    """Rule 2 of the charter, enforced as a test."""
    from app.detectors.d01_fast_critical_closure import D01FastCriticalClosure

    w = MiniWorld()
    for peer in ("P1", "P2", "P3"):
        healthy_entity(w, peer)
    w.entity("BAD")
    asset = w.asset("BAD", criticality="critical")
    for i in range(60):
        a = w.alert("BAD", "critical", asset_id=asset, minutes_offset=i * 20)
        w.case("BAD", a, handling_minutes=0.4, minutes_offset=i * 20 + 1)

    for f in D01FastCriticalClosure().run(w.ctx()):
        assert f.rationale.strip()
        assert f.innocent_explanation.strip()
        assert f.metrics
        assert f.evidence_row_ids
        assert 0.0 < f.confidence <= 1.0
        assert f.severity in ("high", "medium", "low")
        assert f.metrics["peer_comparison_level"]
