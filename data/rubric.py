"""Load and apply the versioned v2 labeling rubric (answer key).

Version 2.1 follows review 1 (docs/reviews/RUBRIC_REVIEW_1.md). The main
change from 2.0: event type, owner, impact, urgency, disposition and priority
are separate facts. The generator (WS3) and chat module (WS7) *author* the
evidence for each case: what the event establishes, its type(s), impact,
urgency and whether a responder can act. This module then applies the few
deterministic context rules and derives disposition and priority.

Nothing here ranks one event type above another, adds a flat criticality
bonus, or turns a maintenance window into a blanket suppression. Those were
the 2.0 defects the review identified.

Scope: labels for a synthetic benchmark fixture, never a live paging policy
(AGENTS.md rule 5).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_RUBRIC = Path(__file__).resolve().parent.parent / "configs" / "domains" / "v2_rubric.json"


class RubricError(ValueError):
    """The rubric file, or a case's evidence/context, violates the contract."""


@dataclass(frozen=True)
class Evidence:
    """Case-author facts about one event, before context rules.

    ``signal`` is a stable name for what happened (e.g. ``ssh_failed_login``)
    and is how expected activities and open incidents are matched.
    ``impact``/``urgency`` are the author's assessment WITHOUT context
    modifiers. ``actionable`` = a responder can take a time-sensitive action
    now. ``compromise_evidence`` = evidence of real compromise, which no
    expected activity can explain away.
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
    human_review_reason: str | None = None


@dataclass(frozen=True)
class Label:
    event_type: str
    secondary_types: tuple[str, ...]
    owner: str
    secondary_owners: tuple[str, ...]
    impact: str
    urgency: str                              # after context rules
    disposition: str
    page_now: bool | None                     # None only for human_review
    priority: str | None                      # None only for human_review
    human_review_reason: str | None
    applied_rules: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (rule, reason)
    rubric_version: str = ""


@dataclass(frozen=True)
class Rubric:
    version: str
    event_types: frozenset[str]
    owners: frozenset[str]
    default_owner: dict[str, str]
    impact_levels: tuple[str, ...]
    urgency_levels: tuple[str, ...]
    disposition_rule: dict[str, Any]
    priority_matrix: dict[str, dict[str, str]]
    review_reasons: frozenset[str]
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
                    "urgency_levels", "disposition_rule", "priority_matrix", "human_review_reasons", "leak_lint")
        for key in required:
            if key not in raw:
                raise RubricError(f"Rubric is missing required key {key!r}")
        types, owners = frozenset(raw["event_types"]), frozenset(raw["owners"])
        default_owner = dict(raw["default_owner_by_type"])
        if set(default_owner) != types or not set(default_owner.values()) <= owners:
            raise RubricError("default_owner_by_type must map every event type to a known owner")
        impacts, urgencies = tuple(raw["impact_levels"]), tuple(raw["urgency_levels"])
        matrix = {k: v for k, v in raw["priority_matrix"].items() if k != "note"}
        # Every impact x urgency cell must be defined, so no case can fall
        # through to an implicit priority.
        if set(matrix) != set(impacts) or any(set(row) != set(urgencies) for row in matrix.values()):
            raise RubricError("priority_matrix must define every impact x urgency cell")
        if not all(p in ("P1", "P2", "P3", "P4") for row in matrix.values() for p in row.values()):
            raise RubricError("priority_matrix values must be P1-P4")
        rule = raw["disposition_rule"]
        if set(rule) != set(urgencies):
            raise RubricError("disposition_rule must cover every urgency level")
        try:
            patterns = tuple(re.compile(p, re.IGNORECASE) for p in raw["leak_lint"]["forbidden_patterns"])
        except re.error as exc:
            raise RubricError(f"Invalid leak_lint pattern: {exc}") from exc
        return cls(version=str(raw["rubric_version"]), event_types=types, owners=owners,
                   default_owner=default_owner, impact_levels=impacts, urgency_levels=urgencies,
                   disposition_rule=rule, priority_matrix=matrix,
                   review_reasons=frozenset(raw["human_review_reasons"]), lint_patterns=patterns,
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

    def _validate(self, ev: Evidence, context: dict[str, Any]) -> None:
        for t in (ev.primary_type, *ev.secondary_types):
            if t not in self.event_types:
                raise RubricError(f"Unknown event type {t!r}")
        for o in ((ev.owner,) if ev.owner else ()) + ev.secondary_owners:
            if o not in self.owners:
                raise RubricError(f"Unknown owner {o!r}")
        self._rank(self.impact_levels, ev.impact, "impact")
        self._rank(self.urgency_levels, ev.urgency, "urgency")
        if not ev.signal.strip():
            raise RubricError("Evidence.signal is required")
        if ev.human_review_reason is not None and ev.human_review_reason not in self.review_reasons:
            raise RubricError(f"Unknown human_review_reason {ev.human_review_reason!r}")
        # Criticality informs impact; it is not a bonus. A case that says the
        # event threatens a critical function on a critical asset but rates
        # impact below moderate is inconsistent, so the author must fix it.
        if (ev.threatens_critical and context["asset"].get("criticality") == "high"
                and self._rank(self.impact_levels, ev.impact, "impact") < self.impact_levels.index("moderate")):
            raise RubricError("Event threatens a critical function on a critical asset but impact < moderate")

    # ---------------------------------------------------------------- labeling
    def label(self, ev: Evidence, event: dict[str, Any], context: dict[str, Any]) -> Label:
        """Apply the context rules and derive disposition and priority.

        Fixed, auditable order:
        1. human review short-circuits (no forced single answer);
        2. expected activity (exact host + time + signal match) may retain;
        3. a genuinely related open incident may correlate;
        4. disposition from urgency/actionability, priority from impact x urgency.
        """
        _require_event_context(event, context)
        self._validate(ev, context)
        owner = ev.owner or self.default_owner[ev.primary_type]
        applied: list[tuple[str, str]] = []
        urgency, impact = ev.urgency, ev.impact

        if ev.human_review_reason:
            return Label(ev.primary_type, ev.secondary_types, owner, ev.secondary_owners, impact, urgency,
                         "human_review", None, None, ev.human_review_reason,
                         (("human_review", ev.human_review_reason),), self.version)

        change = _matching_expected_activity(event, context)
        if change and not ev.compromise_evidence:
            urgency = "none"
            applied.append(("expected_activity", f"{event['signal']} expected under {change['id']}"))
        elif change and ev.compromise_evidence:
            applied.append(("expected_activity_ignored", f"compromise evidence overrides {change['id']}"))

        incident = _related_incident(event, context)
        if incident and urgency != "none":
            same_type = incident.get("event_type") == ev.primary_type
            same_mode = incident.get("failure_mode") == event["signal"]
            not_worse = (self._rank(self.impact_levels, impact, "impact")
                         <= self._rank(self.impact_levels, str(incident.get("impact", "none")), "incident impact")
                         and self._rank(self.urgency_levels, urgency, "urgency")
                         <= self._rank(self.urgency_levels, str(incident.get("urgency", "none")), "incident urgency"))
            if same_type and same_mode and not_worse:
                urgency = "none"
                applied.append(("related_incident", f"correlated into {incident['id']}"))
            else:
                why = ("different event type" if not same_type else
                       "new failure mode" if not same_mode else "impact or urgency increased")
                applied.append(("related_incident_reassessed", f"{incident['id']}: {why}"))

        rule = self.disposition_rule[urgency]
        disposition = (rule["actionable" if ev.actionable else "not_actionable"] if isinstance(rule, dict) else rule)
        priority = self.priority_matrix[impact][urgency]
        return Label(ev.primary_type, ev.secondary_types, owner, ev.secondary_owners, impact, urgency,
                     disposition, disposition == "page_now", priority, None, tuple(applied), self.version)


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


def _matching_expected_activity(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    """An approved change/exercise explains an event only if host, time AND
    signal all match. A drill does not explain an unrelated login failure."""
    ts = _parse_ts(event["ts"], "event.ts")
    for change in context["active_changes"]:
        for key in ("id", "hosts", "start", "end", "status", "expected_signals"):
            if key not in change:
                raise RubricError(f"active_changes item is missing {key!r}")
        start = _parse_ts(change["start"], f"change {change['id']} start")
        end = _parse_ts(change["end"], f"change {change['id']} end")
        if start > end:
            raise RubricError(f"change {change['id']} ends before it starts")
        if (change["status"] == "approved" and event["host"] in change["hosts"]
                and start <= ts <= end and event["signal"] in change["expected_signals"]):
            return change
    return None


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
