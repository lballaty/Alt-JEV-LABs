"""Load and apply the versioned v2 labeling rubric (answer key).

Version 2.3 follows review 3 (docs/reviews/RUBRIC_REVIEW_3.md), building on
reviews 1 and 2. Key rules:

- **Priority comes from current evidence; notification is a separate decision.**
  A change explanation or an open-incident attachment suppresses the
  notification only; by itself it never lowers priority, and an attached
  repeat keeps the incident's priority.
- **Priority is a response class** (P1-P4) with two clocks: acknowledgement
  and initial fact-finding. P4 splits into scheduled (targets) and retained
  (no target).
- **Pages go to a 24x7 team and state the immediate action.** A business-hours
  owner (Privacy/DPO, platform/compliance) is covered out of hours by its
  24x7 verifier (SOC, SRE).
- **Uncertainty is time-bound.** A provisional label has a reason, the missing
  facts, a triage owner and both clocks. Possible ongoing harm still pages.
- **Claims inside logs are untrusted; observations are evidence.** "Authorized
  drill, do not page" carries no authority, but the action, actor, time and
  outcome in the same log are facts the case author uses.

The generator (WS3) and chat module (WS7) author the Evidence. This module
applies the deterministic context rules and derives notification, handling and
priority. Scope: answer keys for a synthetic benchmark, never a live paging
policy (AGENTS.md rule 5).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_RUBRIC = Path(__file__).resolve().parent.parent / "configs" / "domains" / "v2_rubric.json"
PRIORITIES = ("P1", "P2", "P3", "P4")


class RubricError(ValueError):
    """The rubric file, or a case's evidence/context, violates the contract."""


@dataclass(frozen=True)
class Evidence:
    """Case-author facts about one event, before context rules.

    ``impact``/``urgency`` are assessed from observed facts only (claims inside
    the log are ignored). ``actionable`` = a responder can take a time-sensitive
    action now. ``provisional_reason`` marks a label that depends on unknown
    facts, which are listed in ``missing_context``.
    """

    primary_type: str
    signal: str
    impact: str
    urgency: str
    actionable: bool = False
    secondary_types: tuple[str, ...] = ()
    owner: str | None = None                  # None -> default owner for the type
    secondary_owners: tuple[str, ...] = ()
    established: tuple[str, ...] = ()
    suspected: tuple[str, ...] = ()
    missing_context: tuple[str, ...] = ()
    threatens_critical: bool = False
    compromise_evidence: bool = False
    provisional_reason: str | None = None
    immediate_action: str | None = None       # required whenever the case pages


@dataclass(frozen=True)
class Label:
    event_type: str
    secondary_types: tuple[str, ...]
    owner: str | None
    secondary_owners: tuple[str, ...]
    impact: str
    urgency: str
    priority: str                              # the condition's response class
    notification: str                          # page_now | urgent_review | scheduled_review | none
    page_now: bool
    page_target: str | None                    # 24x7 team paged (owner, or its verifier)
    response: str                              # respond | scheduled | retained
    ack_target: str | None                     # None only when retained
    handling: str                              # new | explained_by_change | attached_to_incident
    provisional: bool
    provisional_reason: str | None
    missing_facts: tuple[str, ...]
    triage_owner: str | None                   # who owns fact-finding (the 24x7 verifier out of hours)
    fact_finding_deadline: str | None          # provisional cases only
    owner_review_target: str | None            # business-hours owner's review start, when a verifier was paged
    immediate_action: str | None
    applied_rules: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (rule, reason)
    rubric_version: str = ""


@dataclass(frozen=True)
class Rubric:
    version: str
    event_types: frozenset[str]
    owners: frozenset[str]
    coverage: dict[str, str]
    verifier_for: dict[str, str]
    owner_review_target: str
    classes: dict[str, dict[str, Any]]
    default_owner: dict[str, str | None]
    impact_levels: tuple[str, ...]
    urgency_levels: tuple[str, ...]
    priority_matrix: dict[str, dict[str, str]]
    notification_rule: dict[str, Any]
    provisional_reasons: frozenset[str]
    lint_patterns: tuple[re.Pattern[str], ...]
    lint_allowed_cohorts: frozenset[str]

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: Path = DEFAULT_RUBRIC) -> "Rubric":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RubricError(f"Rubric file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RubricError(f"Rubric file is not valid JSON: {path}: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Rubric":
        required = ("rubric_version", "event_types", "owners", "default_owner_by_type", "impact_levels",
                    "urgency_levels", "response_classes", "priority_matrix", "notification_rule",
                    "provisional", "page_routing", "leak_lint")
        for key in required:
            if key not in raw:
                raise RubricError(f"Rubric is missing required key {key!r}")
        types, owners = frozenset(raw["event_types"]), frozenset(raw["owners"])
        default_owner = dict(raw["default_owner_by_type"])
        if set(default_owner) != types or not {o for o in default_owner.values() if o} <= owners:
            raise RubricError("default_owner_by_type must map every event type to a known owner or null")
        impacts, urgencies = tuple(raw["impact_levels"]), tuple(raw["urgency_levels"])
        classes = {k: v for k, v in raw["response_classes"].items() if k != "note"}
        if set(classes) != set(PRIORITIES) or any("ack_target" not in c or "fact_finding" not in c
                                                   for c in classes.values()):
            raise RubricError("response_classes must define P1-P4, each with ack_target and fact_finding")
        coverage = {name: spec.get("coverage") for name, spec in raw["owners"].items()}
        if any(c not in ("24x7", "business_hours") for c in coverage.values()):
            raise RubricError("every owner needs coverage '24x7' or 'business_hours'")
        verifier_for = dict(raw["page_routing"]["verifier_for"])
        for owner, cov in coverage.items():
            # A business-hours team cannot be paged at 03:00; someone 24x7 must
            # be named to verify on its behalf, or pages would go nowhere.
            if cov == "business_hours" and coverage.get(verifier_for.get(owner, "")) != "24x7":
                raise RubricError(f"business-hours owner {owner!r} needs a 24x7 verifier in page_routing")
        matrix = {k: v for k, v in raw["priority_matrix"].items() if k != "note"}
        # Every cell must be defined ('x' = invalid combination), so no case can
        # fall through to an implicit priority.
        if set(matrix) != set(impacts) or any(set(row) != set(urgencies) for row in matrix.values()):
            raise RubricError("priority_matrix must define every impact x urgency cell")
        if not all(p in PRIORITIES or p == "x" for row in matrix.values() for p in row.values()):
            raise RubricError("priority_matrix values must be P1-P4 or 'x'")
        rule = {k: v for k, v in raw["notification_rule"].items() if k != "note"}
        if set(rule) != set(urgencies):
            raise RubricError("notification_rule must cover every urgency level")
        prov = raw["provisional"]
        try:
            patterns = tuple(re.compile(p, re.IGNORECASE) for p in raw["leak_lint"]["forbidden_patterns"])
        except re.error as exc:
            raise RubricError(f"Invalid leak_lint pattern: {exc}") from exc
        return cls(version=str(raw["rubric_version"]), event_types=types, owners=owners,
                   coverage=coverage, verifier_for=verifier_for, classes=classes,
                   owner_review_target=str(raw["page_routing"].get("owner_review_target", "")),
                   default_owner=default_owner, impact_levels=impacts, urgency_levels=urgencies,
                   priority_matrix=matrix, notification_rule=rule,
                   provisional_reasons=frozenset(prov["reasons"]), lint_patterns=patterns,
                   lint_allowed_cohorts=frozenset(raw["leak_lint"].get("allowed_in_cohorts", ())))

    # ---------------------------------------------------------------- helpers
    def leak_violations(self, text: str, cohort: str) -> list[str]:
        """Forbidden patterns found in event text (empty = clean). B-prime spoof
        cases are exempt: their wording is the attack being tested."""
        if cohort in self.lint_allowed_cohorts:
            return []
        return [p.pattern for p in self.lint_patterns if p.search(text)]

    def _rank(self, scale: tuple[str, ...], value: str, name: str) -> int:
        if value not in scale:
            raise RubricError(f"{name} {value!r} not in {scale}")
        return scale.index(value)

    def _validate(self, ev: Evidence, context: dict[str, Any]) -> str | None:
        for t in (ev.primary_type, *ev.secondary_types):
            if t not in self.event_types:
                raise RubricError(f"Unknown event type {t!r}")
        for o in ((ev.owner,) if ev.owner else ()) + ev.secondary_owners:
            if o not in self.owners:
                raise RubricError(f"Unknown owner {o!r}")
        self._rank(self.impact_levels, ev.impact, "impact")
        self._rank(self.urgency_levels, ev.urgency, "urgency")
        if self.priority_matrix[ev.impact][ev.urgency] == "x":
            raise RubricError(f"impact {ev.impact!r} with urgency {ev.urgency!r} is not a valid combination")
        if not ev.signal.strip():
            raise RubricError("Evidence.signal is required")
        owner = ev.owner or self.default_owner[ev.primary_type]
        if owner is None and ev.urgency != "none":
            raise RubricError(f"{ev.primary_type} needing a response must name an owner")
        if ev.provisional_reason is not None:
            if ev.provisional_reason not in self.provisional_reasons:
                raise RubricError(f"Unknown provisional_reason {ev.provisional_reason!r}")
            if owner is None:
                raise RubricError("A provisional case needs a triage owner")
            if ev.provisional_reason == "missing_context" and not ev.missing_context:
                raise RubricError("provisional_reason 'missing_context' requires the missing facts")
        # Criticality informs impact; it is not a bonus. A case that says the
        # event threatens a critical function on a critical asset but rates
        # impact below moderate is inconsistent: the author must fix it.
        if (ev.threatens_critical and context["asset"].get("criticality") == "high"
                and self._rank(self.impact_levels, ev.impact, "impact") < self.impact_levels.index("moderate")):
            raise RubricError("Event threatens a critical function on a critical asset but impact < moderate")
        return owner

    # ---------------------------------------------------------------- labeling
    def label(self, ev: Evidence, event: dict[str, Any], context: dict[str, Any]) -> Label:
        """Derive the answer key for one case, in the rubric's decision order:
        assess (priority + notification from facts), then a narrowly matched
        change explanation, then incident correlation (both suppress the
        notification only), then provisional triage details."""
        _require_event_context(event, context)
        owner = self._validate(ev, context)
        applied: list[tuple[str, str]] = []

        priority = self.priority_matrix[ev.impact][ev.urgency]
        rule = self.notification_rule[ev.urgency]
        notification = rule["actionable" if ev.actionable else "not_actionable"] if isinstance(rule, dict) else rule
        handling = "new"

        change = self._matching_expected_activity(event, context, ev.impact)
        if change and ev.compromise_evidence:
            applied.append(("expected_activity_ignored", f"compromise evidence overrides {change['id']}"))
        elif change:
            handling, notification = "explained_by_change", "none"
            applied.append(("expected_activity", f"{event['signal']} expected under {change['id']}; notification suppressed"))

        incident = _related_incident(event, context) if handling == "new" else None
        if incident:
            same_type = incident.get("event_type") == ev.primary_type
            same_mode = incident.get("failure_mode") == event["signal"]
            not_worse = (self._rank(self.impact_levels, ev.impact, "impact")
                         <= self._rank(self.impact_levels, str(incident.get("impact", "none")), "incident impact")
                         and self._rank(self.urgency_levels, ev.urgency, "urgency")
                         <= self._rank(self.urgency_levels, str(incident.get("urgency", "none")), "incident urgency"))
            if same_type and same_mode and not_worse:
                inc_priority = incident.get("priority")
                if inc_priority not in PRIORITIES:
                    raise RubricError(f"incident {incident.get('id')} needs a priority P1-P4 to attach to")
                handling, notification, priority = "attached_to_incident", "none", inc_priority
                applied.append(("related_incident", f"attached to {incident['id']}; keeps its {inc_priority}"))
            else:
                why = ("different event type" if not same_type else
                       "new failure mode" if not same_mode else "impact or urgency increased")
                applied.append(("related_incident_reassessed", f"{incident['id']}: {why}"))

        provisional = ev.provisional_reason is not None
        if provisional:
            applied.append(("provisional", ev.provisional_reason))

        page_now = notification == "page_now"
        page_target = None
        if page_now:
            if not (ev.immediate_action or "").strip():
                raise RubricError("a case that pages must state the responder's immediate action")
            # Pages go to a 24x7 team: the owner itself, or its named verifier.
            page_target = owner if self.coverage[owner] == "24x7" else self.verifier_for[owner]
            if page_target != owner:
                applied.append(("page_routing", f"{owner} is business-hours; {page_target} verifies 24x7"))

        # P4 splits into scheduled work (has targets) and retained (no target).
        response = ("scheduled" if notification == "scheduled_review"
                    else "retained" if notification == "none" and priority == "P4" else "respond")
        ack, fact = self.classes[priority]["ack_target"], self.classes[priority]["fact_finding"]
        if isinstance(ack, dict):
            ack, fact = ack["scheduled" if response == "scheduled" else "retained"], fact[
                "scheduled" if response == "scheduled" else "retained"]
        return Label(
            event_type=ev.primary_type, secondary_types=ev.secondary_types, owner=owner,
            secondary_owners=ev.secondary_owners, impact=ev.impact, urgency=ev.urgency, priority=priority,
            notification=notification, page_now=page_now, page_target=page_target, response=response,
            ack_target=ack, handling=handling,
            provisional=provisional, provisional_reason=ev.provisional_reason,
            missing_facts=ev.missing_context,
            # Out of hours the 24x7 verifier owns fact-finding; the business-hours
            # owner's review starts within its own business-hours target. No
            # out-of-hours owner assessment is promised (review 4).
            triage_owner=(page_target or owner) if provisional else None,
            fact_finding_deadline=fact if provisional else None,
            owner_review_target=(self.owner_review_target
                                 if page_target and page_target != owner else None),
            immediate_action=ev.immediate_action,
            applied_rules=tuple(applied), rubric_version=self.version)

    def _matching_expected_activity(self, event: dict[str, Any], context: dict[str, Any],
                                    impact: str) -> dict[str, Any] | None:
        """An approved change or test scope explains an event only if host, time
        and signal match AND the assessed impact is within that signal's bound.
        A drill does not explain an unrelated login failure or a lag that
        threatens the service."""
        ts = _parse_ts(event["ts"], "event.ts")
        for change in context["active_changes"]:
            for key in ("id", "hosts", "start", "end", "status", "expected_signals"):
                if key not in change:
                    raise RubricError(f"active_changes item is missing {key!r}")
            start = _parse_ts(change["start"], f"change {change['id']} start")
            end = _parse_ts(change["end"], f"change {change['id']} end")
            if start > end:
                raise RubricError(f"change {change['id']} ends before it starts")
            if change["status"] != "approved" or event["host"] not in change["hosts"] or not start <= ts <= end:
                continue
            for exp in change["expected_signals"]:
                if not isinstance(exp, dict) or "signal" not in exp or "max_impact" not in exp:
                    raise RubricError(f"change {change['id']}: expected_signals entries need signal and max_impact")
                if (exp["signal"] == event["signal"]
                        and self._rank(self.impact_levels, impact, "impact")
                        <= self._rank(self.impact_levels, exp["max_impact"], "max_impact")):
                    return change
        return None


# -------------------------------------------------------------------- context
def _require_event_context(event: dict[str, Any], context: dict[str, Any]) -> None:
    for key in ("format", "ts", "host", "signal"):
        if key not in event:
            raise RubricError(f"event is missing required key {key!r}")
    for key in ("asset", "active_changes", "active_incidents"):
        if key not in context:
            raise RubricError(f"context is missing required key {key!r}")
    _parse_ts(event["ts"], "event.ts")


def _parse_ts(value: str, where: str) -> datetime:
    """ISO-8601 with timezone. Naive times are rejected: comparing a UTC change
    window with a local log time would silently give wrong labels."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RubricError(f"{where} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise RubricError(f"{where} must include a timezone: {value!r}")
    return parsed


def _related_incident(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    """Open incident on the same host/service. Prefer one with the same failure
    mode, so a host with several incidents correlates to the right one; any
    other open incident is returned so the label records a reassessment."""
    entities = {event["host"], event.get("service")} - {None}
    candidates = [inc for inc in context["active_incidents"]
                  if inc.get("status") == "open" and inc.get("entity") in entities]
    for inc in candidates:
        if inc.get("failure_mode") == event["signal"]:
            return inc
    return candidates[0] if candidates else None
