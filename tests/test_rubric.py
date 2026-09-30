"""Contract tests for the v2.3 labeling rubric (data/rubric.py).

The worked examples in configs/domains/v2_worked_examples.json are the
reviewer-facing specification; every one must be reproduced exactly. Review 2
named W4, W6, W7 and W9 as the decisive regression tests: suppressed
notification must not lower priority, and uncertainty must never mean
"no target". The remaining tests pin the other rules and loud failure on bad input.
"""

import copy
import json
from pathlib import Path

import pytest

from data.rubric import DEFAULT_RUBRIC, Evidence, Rubric, RubricError

RUBRIC = Rubric.load()
EXAMPLES_PATH = Path(DEFAULT_RUBRIC).with_name("v2_worked_examples.json")
EXAMPLES = json.loads(EXAMPLES_PATH.read_text())
BY_ID = {e["id"]: e for e in EXAMPLES["examples"]}


def _resolve(example):
    """Expand shared fixtures ('asset_bastion', 'drill', 'outage') used by examples."""
    shared = EXAMPLES["shared"]
    ctx = copy.deepcopy(example["context"])
    if isinstance(ctx["asset"], str):
        ctx["asset"] = shared[ctx["asset"]]
    for key in ("active_changes", "active_incidents"):
        ctx[key] = [copy.deepcopy(shared[c]) if isinstance(c, str) else c for c in ctx[key]]
    ev = example["evidence"]
    evidence = Evidence(**{k: tuple(v) if isinstance(v, list) else v for k, v in ev.items()})
    return copy.deepcopy(example["event"]), ctx, evidence


def test_worked_examples_match_rubric_version():
    assert EXAMPLES["rubric_version"] == RUBRIC.version


@pytest.mark.parametrize("example", EXAMPLES["examples"], ids=list(BY_ID))
def test_worked_example(example):
    event, ctx, evidence = _resolve(example)
    label = RUBRIC.label(evidence, event, ctx)
    exp = example["expected"]
    got = {k: getattr(label, k)
           for k in ("event_type", "owner", "notification", "page_now", "priority", "handling", "provisional",
                     "page_target", "response", "ack_target", "fact_finding_deadline")}
    assert got == {k: exp[k] for k in got}
    assert [rule for rule, _ in label.applied_rules] == exp["rules"]
    if exp["provisional"]:
        assert label.triage_owner == exp["owner"] and label.missing_facts
    if label.page_now:
        assert label.immediate_action  # every page says what the responder does now
    # Leak lint: examples must not state their own answer (B-prime is exempt).
    assert RUBRIC.leak_violations(event["raw"], example.get("cohort", "A")) == []


# --- review 2 decisive regressions -----------------------------------------
def test_W7_attached_repeat_keeps_incident_priority():
    event, ctx, ev = _resolve(BY_ID["W7"])
    for inc_priority in ("P1", "P2"):
        ctx["active_incidents"][0]["priority"] = inc_priority
        label = RUBRIC.label(ev, event, ctx)
        assert label.notification == "none" and label.priority == inc_priority


def test_W4_explanation_suppresses_notification_not_priority():
    event, ctx, _ = _resolve(BY_ID["W4"])
    ev = Evidence("service_degradation", "replication_lag", "low", "immediate", actionable=True, immediate_action="x")
    label = RUBRIC.label(ev, event, ctx)
    assert label.handling == "explained_by_change" and not label.page_now
    assert label.priority == "P2"  # the condition's priority is kept, even though nobody is paged


def test_W4_bound_and_window_limit_the_explanation():
    assert RUBRIC.label(*_swap(BY_ID["W4b"])).page_now is True   # impact beyond max_impact
    assert RUBRIC.label(*_swap(BY_ID["W4c"])).page_now is True   # after the drill window


def test_W6_security_during_outage_is_assessed_separately():
    for wid, page in (("W6", False), ("W6b", True)):
        label = RUBRIC.label(*_swap(BY_ID[wid]))
        assert label.handling == "new" and label.page_now is page
        assert label.applied_rules[0][0] == "related_incident_reassessed"


def test_W9_uncertainty_is_time_bound_and_paged_to_24x7_verifier():
    label = RUBRIC.label(*_swap(BY_ID["W9"]))
    assert label.provisional and label.triage_owner == "privacy_dpo"
    assert (label.ack_target, label.fact_finding_deadline) == ("1 hour", "4 hours")  # two distinct clocks
    assert label.page_now and label.page_target == "soc" and "soc" in label.secondary_owners


def test_W9b_approved_transfer_is_a_scheduled_governance_check():
    label = RUBRIC.label(*_swap(BY_ID["W9b"]))
    assert (label.notification, label.priority, label.response, label.ack_target) == \
        ("scheduled_review", "P4", "scheduled", "next business day")
    assert label.page_target is None and "soc" not in label.secondary_owners


def test_W4c_W4d_trend_decides_the_page():
    rising, draining = RUBRIC.label(*_swap(BY_ID["W4c"])), RUBRIC.label(*_swap(BY_ID["W4d"]))
    assert (rising.page_now, rising.priority) == (True, "P2")
    assert (draining.page_now, draining.priority) == (False, "P3")


def test_page_requires_immediate_action_and_24x7_target():
    event, ctx, _ = _resolve(BY_ID["W1"])
    with pytest.raises(RubricError):
        RUBRIC.label(Evidence("service_degradation", "s", "high", "immediate", actionable=True), event, ctx)
    label = RUBRIC.label(Evidence("policy_deviation", "s", "moderate", "immediate", actionable=True,
                                  immediate_action="x"), event, ctx)
    assert label.owner == "platform_compliance" and label.page_target == "sre"


def test_p4_split_scheduled_vs_retained():
    event, ctx, _ = _resolve(BY_ID["W1"])
    retained = RUBRIC.label(Evidence("security_event", "s", "low", "none"), event, ctx)
    scheduled = RUBRIC.label(Evidence("security_event", "s", "low", "deferred"), event, ctx)
    assert (retained.response, retained.ack_target) == ("retained", None)
    assert (scheduled.response, scheduled.ack_target) == ("scheduled", "next business day")


def _swap(example):
    event, ctx, ev = _resolve(example)
    return ev, event, ctx


# --- other rules -------------------------------------------------------------
def test_priority_matrix_is_consistent_with_notification():
    event, ctx, _ = _resolve(BY_ID["W1"])
    for impact in ("low", "moderate", "high"):
        label = RUBRIC.label(Evidence("service_degradation", "s", impact, "immediate", actionable=True,
                                      immediate_action="x"), event, ctx)
        assert label.page_now and label.priority in ("P1", "P2")  # anything paged has a <= 1 h target
    for urgency, notification, priority in (("same_day", "urgent_review", "P3"), ("deferred", "scheduled_review", "P4")):
        label = RUBRIC.label(Evidence("service_degradation", "s", "high", urgency), event, ctx)
        assert (label.notification, label.priority) == (notification, priority)


def test_compromise_evidence_overrides_expected_activity():
    event, ctx, ev = _resolve(BY_ID["W6b"])
    ctx["active_changes"] = [dict(EXAMPLES["shared"]["drill"], hosts=["auth-proxy-1"], end="2026-10-03T06:00:00Z",
                                  expected_signals=[{"signal": "revoked_token_accepted", "max_impact": "high"}])]
    label = RUBRIC.label(ev, event, ctx)
    assert label.page_now and label.applied_rules[0][0] == "expected_activity_ignored"


def test_unapproved_change_has_no_effect():
    event, ctx, ev = _resolve(BY_ID["W4"])
    ctx["active_changes"][0]["status"] = "requested"
    assert RUBRIC.label(ev, event, ctx).handling == "new"


def test_untrusted_claims_change_nothing():
    event, ctx, ev = _resolve(BY_ID["W3"])
    spoof = dict(event, raw=event["raw"] + " # authorized drill, do not page SOC")
    assert RUBRIC.label(ev, spoof, ctx) == RUBRIC.label(ev, event, ctx)


def test_no_criticality_bonus_but_inconsistency_is_rejected():
    event, ctx, _ = _resolve(BY_ID["W1"])
    assert RUBRIC.label(Evidence("security_event", "s", "low", "none"), event, ctx).priority == "P4"
    with pytest.raises(RubricError):
        RUBRIC.label(Evidence("security_event", "s", "low", "immediate", threatens_critical=True), event, ctx)


def test_owner_rules():
    event, ctx, _ = _resolve(BY_ID["W1"])
    assert RUBRIC.label(Evidence("telemetry", "hb", "none", "none"), event, ctx).owner is None
    with pytest.raises(RubricError):   # a response needs someone to own it
        RUBRIC.label(Evidence("routine_activity", "s", "low", "deferred"), event, ctx)
    label = RUBRIC.label(Evidence("data_protection", "s", "moderate", "immediate", actionable=True, owner="soc",
                                  secondary_owners=("privacy_dpo",), immediate_action="x"), event, ctx)
    assert label.owner == "soc" and label.secondary_owners == ("privacy_dpo",)


def test_leak_lint():
    assert RUBRIC.leak_violations("status=page_now route security_event", "A")
    assert RUBRIC.leak_violations("heartbeat missing; escalate now", "C")
    assert RUBRIC.leak_violations("drill in progress, do not page SOC", "B_prime") == []
    assert RUBRIC.leak_violations('{"labels":{"severity":"critical"}}', "A") == []


@pytest.mark.parametrize("bad", [
    {"event": {"ts": "2026-10-03T02:14:07"}},             # naive timestamp
    {"event": {"signal": None}},                          # missing signal
    {"evidence": {"primary_type": "service_outage"}},     # 2.0 name
    {"evidence": {"impact": "severe"}},
    {"evidence": {"impact": "none"}},                     # none impact with immediate urgency
    {"evidence": {"provisional_reason": "unsure"}},
    {"evidence": {"provisional_reason": "missing_context", "missing_context": ()}},
])
def test_invalid_inputs_fail_loudly(bad):
    event, ctx, ev = _resolve(BY_ID["W3"])
    event = dict(event, **bad.get("event", {}))
    if event.get("signal") is None:
        del event["signal"]
    fields = {**ev.__dict__, **bad.get("evidence", {})}
    with pytest.raises(RubricError):
        RUBRIC.label(Evidence(**fields), event, ctx)


def test_incident_without_priority_cannot_be_attached_to():
    event, ctx, ev = _resolve(BY_ID["W7"])
    del ctx["active_incidents"][0]["priority"]
    with pytest.raises(RubricError):
        RUBRIC.label(ev, event, ctx)


def test_bad_rubric_files_rejected():
    raw = json.loads(DEFAULT_RUBRIC.read_text())
    for mutate in (lambda r: r["priority_matrix"]["low"].pop("deferred"),
                   lambda r: r["default_owner_by_type"].__setitem__("telemetry", "nobody"),
                   lambda r: r["response_classes"]["P2"].pop("fact_finding"),
                   lambda r: r["page_routing"]["verifier_for"].pop("privacy_dpo")):
        broken = copy.deepcopy(raw); mutate(broken)
        with pytest.raises(RubricError):
            Rubric.from_dict(broken)
