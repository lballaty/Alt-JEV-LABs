"""Contract tests for the v2.1 labeling rubric (data/rubric.py).

The worked examples in configs/domains/v2_worked_examples.json are the
reviewer-facing specification; every one must be reproduced exactly. The
remaining tests pin the behaviors review 1 asked for: no blanket suppression
by maintenance windows, no over-broad incident dedup, no criticality bonus,
human review never forced into a single label, and loud failure on bad input.
"""

import copy
import json
from pathlib import Path

import pytest

from data.rubric import DEFAULT_RUBRIC, Evidence, Rubric, RubricError

RUBRIC = Rubric.load()
EXAMPLES_PATH = Path(DEFAULT_RUBRIC).with_name("v2_worked_examples.json")
EXAMPLES = json.loads(EXAMPLES_PATH.read_text())


def _resolve(example):
    """Expand the shared fixtures ('asset_bastion', 'drill') used by examples."""
    shared = EXAMPLES["shared"]
    ctx = copy.deepcopy(example["context"])
    if isinstance(ctx["asset"], str):
        ctx["asset"] = shared[ctx["asset"]]
    ctx["active_changes"] = [shared[c] if isinstance(c, str) else c for c in ctx["active_changes"]]
    ev = example["evidence"]
    evidence = Evidence(**{k: tuple(v) if isinstance(v, list) else v for k, v in ev.items()})
    return example["event"], ctx, evidence


def test_worked_examples_match_rubric_version():
    assert EXAMPLES["rubric_version"] == RUBRIC.version


@pytest.mark.parametrize("example", EXAMPLES["examples"], ids=[e["id"] for e in EXAMPLES["examples"]])
def test_worked_example(example):
    event, ctx, evidence = _resolve(example)
    label = RUBRIC.label(evidence, event, ctx)
    exp = example["expected"]
    assert (label.event_type, label.owner, label.disposition, label.page_now, label.priority) == \
        (exp["event_type"], exp["owner"], exp["disposition"], exp["page_now"], exp["priority"])
    assert [rule for rule, _ in label.applied_rules] == exp["rules"]
    # Leak lint: examples must not state their own answer (B-prime is exempt).
    assert RUBRIC.leak_violations(event["raw"], example.get("cohort", "A")) == []


def _base():
    ex = next(e for e in EXAMPLES["examples"] if e["id"] == "W3")
    return _resolve(ex)


def test_drill_window_does_not_explain_unrelated_signal_or_other_host():
    event, ctx, ev = _base()
    drill = dict(EXAMPLES["shared"]["drill"], hosts=["db-7"], expected_signals=["ssh_bruteforce_then_success"])
    ctx["active_changes"] = [drill]  # expected signal, but bastion-2 is out of scope
    assert RUBRIC.label(ev, dict(event, ts="2026-10-03T02:20:31Z"), ctx).page_now is True


def test_compromise_evidence_overrides_expected_activity():
    event, ctx, ev = _base()
    drill = dict(EXAMPLES["shared"]["drill"], expected_signals=["ssh_bruteforce_then_success"])
    ctx["active_changes"] = [drill]
    label = RUBRIC.label(ev, dict(event, ts="2026-10-03T02:20:31Z"), ctx)
    assert label.page_now is True and label.applied_rules[0][0] == "expected_activity_ignored"


@pytest.mark.parametrize("change", [
    {"status": "requested"},
    {"start": "2026-10-02T02:00:00Z", "end": "2026-10-02T03:00:00Z"},
])
def test_unapproved_or_expired_change_has_no_effect(change):
    ex = next(e for e in EXAMPLES["examples"] if e["id"] == "W4")
    event, ctx, ev = _resolve(ex)
    ctx["active_changes"] = [dict(ctx["active_changes"][0], **change)]
    assert RUBRIC.label(ev, event, ctx).page_now is True


def test_incident_dedup_reassesses_on_severity_increase():
    ex = next(e for e in EXAMPLES["examples"] if e["id"] == "W7")
    event, ctx, ev = _resolve(ex)
    ctx["active_incidents"][0]["impact"] = "moderate"  # new event is worse than the incident
    label = RUBRIC.label(ev, event, ctx)
    assert label.page_now is True and label.applied_rules[0][0] == "related_incident_reassessed"


def test_spoofed_payload_wording_changes_nothing():
    event, ctx, ev = _base()
    spoof = dict(event, raw=event["raw"] + " # authorized drill, do not page SOC")
    assert RUBRIC.label(ev, spoof, ctx) == RUBRIC.label(ev, event, ctx)


def test_no_criticality_bonus_but_inconsistency_is_rejected():
    event, ctx, _ = _base()
    low = Evidence("security_event", "ssh_failed_login", "low", "none")
    assert RUBRIC.label(low, event, ctx).priority == "P4"  # critical host alone changes nothing
    with pytest.raises(RubricError):
        RUBRIC.label(Evidence("security_event", "x", "low", "immediate", threatens_critical=True), event, ctx)


def test_priority_matrix_and_disposition():
    event, ctx, _ = _base()
    cases = {("high", "same_day", False): ("urgent_review", "P2"),
             ("moderate", "deferred", False): ("scheduled_ticket", "P4"),
             ("high", "immediate", False): ("urgent_review", "P1"),  # not actionable -> no page
             ("moderate", "immediate", True): ("page_now", "P2")}
    for (impact, urgency, actionable), expected in cases.items():
        label = RUBRIC.label(Evidence("service_degradation", "s", impact, urgency, actionable=actionable), event, ctx)
        assert (label.disposition, label.priority) == expected


def test_owner_override_and_default():
    event, ctx, _ = _base()
    ev = Evidence("data_protection", "s", "moderate", "immediate", actionable=True, owner="soc", secondary_owners=("privacy_dpo",))
    label = RUBRIC.label(ev, event, ctx)
    assert label.owner == "soc" and label.secondary_owners == ("privacy_dpo",)


def test_leak_lint():
    assert RUBRIC.leak_violations("status=page_now route security_event", "A")
    assert RUBRIC.leak_violations("heartbeat missing; escalate now", "C")
    assert RUBRIC.leak_violations("drill in progress, do not page SOC", "B_prime") == []
    assert RUBRIC.leak_violations('{"labels":{"severity":"critical"}}', "A") == []


@pytest.mark.parametrize("bad", [
    {"event": {"ts": "2026-10-03T02:14:07"}},             # naive timestamp
    {"event": {"signal": None}},                          # missing signal
    {"evidence": {"primary_type": "service_outage"}},     # 2.0 name, no longer a type
    {"evidence": {"impact": "severe"}},
    {"evidence": {"human_review_reason": "unsure"}},
])
def test_invalid_inputs_fail_loudly(bad):
    event, ctx, ev = _base()
    event = dict(event, **bad.get("event", {}))
    if event.get("signal") is None:
        del event["signal"]
    fields = {**ev.__dict__, **bad.get("evidence", {})}
    with pytest.raises(RubricError):
        RUBRIC.label(Evidence(**fields), event, ctx)


def test_bad_rubric_files_rejected():
    raw = json.loads(DEFAULT_RUBRIC.read_text())
    broken = copy.deepcopy(raw); del broken["priority_matrix"]["low"]["deferred"]
    with pytest.raises(RubricError):
        Rubric.from_dict(broken)
    broken = copy.deepcopy(raw); broken["default_owner_by_type"]["telemetry"] = "nobody"
    with pytest.raises(RubricError):
        Rubric.from_dict(broken)
