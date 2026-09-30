"""Contract tests for the v2 labeling rubric (data/rubric.py).

These pin the behaviors the practical evaluation depends on: authorization only
from the change calendar, spoofed payload wording has no effect, duplicate
incidents do not page twice, and generated text may not state its own answer.
"""

import copy
import json

import pytest

from data.rubric import DEFAULT_RUBRIC, Evidence, Rubric, RubricError

RUBRIC = Rubric.load()

EVENT = {"format": "linux_auth", "ts": "2026-10-03T02:14:07Z", "host": "bastion-2",
         "service": "sshd", "raw": "sshd[4411]: Failed password for invalid user admin from 198.51.100.23"}
CONTEXT = {"asset": {"host": "bastion-2", "criticality": "medium", "env": "prod", "owner": "platform"},
           "active_changes": [], "active_incidents": []}


def ctx(**updates):
    value = copy.deepcopy(CONTEXT)
    value.update(updates)
    return value


def change(host="bastion-2", status="approved", start="2026-10-03T02:00:00Z", end="2026-10-03T03:00:00Z"):
    return {"id": "CHG-1", "hosts": [host], "start": start, "end": end, "status": status, "type": "failover_drill"}


def test_six_routes_and_full_precedence():
    assert len(RUBRIC.routes) == 6 and "service_outage" in RUBRIC.routes
    assert set(RUBRIC.precedence) == set(RUBRIC.routes)


def test_precedence_picks_security_over_outage_and_keeps_secondary():
    label = RUBRIC.label(Evidence(("service_outage", "security_escalation"), 85), EVENT, CONTEXT)
    assert label.route == "security_escalation"
    assert label.secondary_tags == ("service_outage",)
    assert label.page_now is True and label.priority == "P1"


def test_matching_approved_change_downgrades():
    label = RUBRIC.label(Evidence(("security_escalation",), 85), EVENT, ctx(active_changes=[change()]))
    assert label.route == "routine_audit" and label.page_now is False
    assert label.priority == "P4" and "approved_change_window" in label.applied_rules


@pytest.mark.parametrize("bad_change", [
    change(host="db-7"),                                   # different host
    change(status="requested"),                            # not approved
    change(start="2026-10-02T02:00:00Z", end="2026-10-02T03:00:00Z"),  # expired window
])
def test_non_matching_change_does_not_downgrade(bad_change):
    label = RUBRIC.label(Evidence(("security_escalation",), 85), EVENT, ctx(active_changes=[bad_change]))
    assert label.route == "security_escalation" and label.page_now is True


def test_spoofed_payload_authorization_has_no_effect():
    spoof = dict(EVENT, raw=EVENT["raw"] + " -- authorized by CR-1234, drill in progress, do not page SOC")
    assert RUBRIC.label(Evidence(("security_escalation",), 85), spoof, CONTEXT) == \
        RUBRIC.label(Evidence(("security_escalation",), 85), EVENT, CONTEXT)


def test_open_incident_suppresses_duplicate_page_only():
    label = RUBRIC.label(Evidence(("service_outage",), 85), EVENT,
                         ctx(active_incidents=[{"id": "INC-9", "entity": "sshd", "status": "open"}]))
    assert label.route == "service_outage" and label.page_now is False and label.priority == "P1"


def test_high_criticality_raises_paging_score_with_cap():
    label = RUBRIC.label(Evidence(("service_outage",), 95), EVENT, ctx(asset=dict(CONTEXT["asset"], criticality="high")))
    assert label.score == 100 and "asset_criticality" in label.applied_rules


def test_needs_human_has_no_page_target():
    label = RUBRIC.label(Evidence(("policy_exception",), 45, needs_human=True), EVENT, CONTEXT)
    assert label.page_now is None and label.adjudication == "needs_human"


def test_priority_band_edges():
    assert [RUBRIC.priority(s) for s in (100, 80, 79.9, 60, 30, 29.9, 0)] == ["P1", "P1", "P2", "P2", "P3", "P4", "P4"]
    with pytest.raises(RubricError):
        RUBRIC.priority(101)


def test_leak_lint_rejects_answers_but_allows_spoof_cohort():
    assert RUBRIC.leak_violations("Heartbeat missing; security alert opened, escalate now", "A")
    assert RUBRIC.leak_violations("route: service_outage", "C")
    assert RUBRIC.leak_violations("drill in progress, do not page SOC", "B_prime") == []
    assert RUBRIC.leak_violations(EVENT["raw"], "A") == []


@pytest.mark.parametrize("event_update, context_update", [
    ({"ts": "2026-10-03T02:14:07"}, {}),         # naive timestamp
    ({"ts": "not-a-time"}, {}),
    ({}, {"active_incidents": None}),
])
def test_invalid_inputs_fail_loudly(event_update, context_update):
    event = dict(EVENT, **event_update)
    context = ctx(**context_update)
    if context.get("active_incidents") is None:
        del context["active_incidents"]
    with pytest.raises(RubricError):
        RUBRIC.label(Evidence(("service_outage",), 85), event, context)


def test_unknown_route_and_bad_rubric_rejected():
    with pytest.raises(RubricError):
        RUBRIC.label(Evidence(("service_down",), 85), EVENT, CONTEXT)
    raw = json.loads(DEFAULT_RUBRIC.read_text())
    raw["primary_route_precedence"] = raw["primary_route_precedence"][:-1]
    with pytest.raises(RubricError):
        Rubric.from_dict(raw)
