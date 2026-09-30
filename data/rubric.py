"""Load and apply the versioned v2 labeling rubric.

The v2 generator (WS3) and the chat module (WS7) must not decide labels ad hoc.
They describe *evidence* (which routes a template supports, a base severity) and
this module turns evidence plus the structured context block into the ground
truth: primary route, page-now, score and priority.

Keeping the rules in one place, driven by `configs/domains/v2_rubric.json`,
means a reviewer can audit the labels without reading generator code, and a
rubric change is visible as a version bump rather than a silent drift.

Scope: this is a labeling rubric for a synthetic benchmark fixture. It is not a
production paging or containment policy (AGENTS.md rule 5).
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
    """The rubric file or a case's evidence/context violates the contract."""


@dataclass(frozen=True)
class Evidence:
    """What a generated event supports, before context rules are applied.

    `routes` lists every route the event text supports (usually one). The
    rubric's precedence picks the primary route; the rest become secondary tags.
    `base_score` is the template author's severity inside the route band.
    `needs_human` marks deliberately ambiguous (Cohort D) cases.
    """

    routes: tuple[str, ...]
    base_score: float
    needs_human: bool = False


@dataclass(frozen=True)
class Label:
    route: str
    secondary_tags: tuple[str, ...]
    page_now: bool | None          # None only when adjudication == "needs_human"
    score: float
    priority: str
    adjudication: str               # "deterministic" or "needs_human"
    applied_rules: tuple[str, ...] = field(default_factory=tuple)
    rubric_version: str = ""


@dataclass(frozen=True)
class Rubric:
    version: str
    routes: dict[str, dict[str, Any]]
    precedence: tuple[str, ...]
    bands: tuple[tuple[str, float], ...]       # (priority, min score), highest first
    downgradable: frozenset[str]
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
        for key in ("rubric_version", "routes", "primary_route_precedence",
                    "priority_bands", "context_rules", "leak_lint"):
            if key not in raw:
                raise RubricError(f"Rubric is missing required key {key!r}")
        routes = raw["routes"]
        precedence = tuple(raw["primary_route_precedence"])
        # Every route must be ranked exactly once; otherwise a multi-route event
        # could have no defined primary route.
        if sorted(precedence) != sorted(routes) or len(set(precedence)) != len(precedence):
            raise RubricError("primary_route_precedence must list every route exactly once")
        for name, spec in routes.items():
            low, high = spec.get("default_score", (None, None))
            if not (isinstance(low, (int, float)) and isinstance(high, (int, float)) and 0 <= low <= high <= 100):
                raise RubricError(f"Route {name!r} needs default_score [low, high] within 0..100")
            if not isinstance(spec.get("default_page_now"), bool):
                raise RubricError(f"Route {name!r} needs boolean default_page_now")

        bands = sorted(((b["priority"], float(b["min"])) for b in raw["priority_bands"]),
                       key=lambda item: item[1], reverse=True)
        # Bands must cover 0..100 with no gap: the lowest band starts at 0.
        if not bands or bands[-1][1] != 0:
            raise RubricError("priority_bands must include a band starting at 0")

        change_rule = raw["context_rules"].get("approved_change_window", {})
        downgradable = frozenset(change_rule.get("downgradable_routes", ()))
        if not downgradable <= set(routes):
            raise RubricError("downgradable_routes contains unknown routes")

        try:
            patterns = tuple(re.compile(p, re.IGNORECASE) for p in raw["leak_lint"]["forbidden_patterns"])
        except re.error as exc:
            raise RubricError(f"Invalid leak_lint pattern: {exc}") from exc

        return cls(version=str(raw["rubric_version"]), routes=routes, precedence=precedence,
                   bands=tuple(bands), downgradable=downgradable, lint_patterns=patterns,
                   lint_allowed_cohorts=frozenset(raw["leak_lint"].get("allowed_in_cohorts", ())))

    # ---------------------------------------------------------------- helpers
    def priority(self, score: float) -> str:
        if not 0 <= score <= 100:
            raise RubricError(f"Score {score} outside 0..100")
        for name, minimum in self.bands:
            if score >= minimum:
                return name
        raise RubricError(f"No priority band covers score {score}")  # unreachable after validation

    def leak_violations(self, text: str, cohort: str) -> list[str]:
        """Return forbidden patterns found in event text (empty list = clean).

        B-prime spoof cases are exempt: their wording is deliberately the kind
        of text an attacker could inject, and the label ignores it.
        """
        if cohort in self.lint_allowed_cohorts:
            return []
        return [p.pattern for p in self.lint_patterns if p.search(text)]

    # ---------------------------------------------------------------- labeling
    def label(self, evidence: Evidence, event: dict[str, Any], context: dict[str, Any]) -> Label:
        """Apply precedence and context rules to produce ground truth.

        Order matters and is fixed here so it is auditable:
        1. primary route by precedence; 2. approved change window may downgrade;
        3. asset criticality may raise the score of paging routes;
        4. an open incident suppresses a duplicate page.
        """
        _require_event_context(event, context)
        unknown = [r for r in evidence.routes if r not in self.routes]
        if not evidence.routes or unknown:
            raise RubricError(f"Evidence routes missing or unknown: {unknown or evidence.routes}")
        if not 0 <= evidence.base_score <= 100:
            raise RubricError("base_score must be within 0..100")

        ordered = sorted(set(evidence.routes), key=self.precedence.index)
        route, secondary = ordered[0], tuple(ordered[1:])
        score = float(evidence.base_score)
        page = self.routes[route]["default_page_now"]
        applied: list[str] = []

        if route in self.downgradable and _approved_change_covers(event, context):
            # The change calendar, not the payload text, is what authorizes.
            secondary = tuple(r for r in (route, *secondary) if r != "routine_audit")
            route = "routine_audit"
            low, high = self.routes[route]["default_score"]
            score = min(max(score, low), high)
            page = False
            applied.append("approved_change_window")
        elif page and context["asset"].get("criticality") == "high":
            score = min(100.0, score + 10)
            applied.append("asset_criticality")

        if page and _open_incident_matches(event, context):
            page = False
            applied.append("open_incident_dedup")

        adjudication = "needs_human" if evidence.needs_human else "deterministic"
        return Label(route=route, secondary_tags=secondary,
                     page_now=None if evidence.needs_human else page,
                     score=score, priority=self.priority(score), adjudication=adjudication,
                     applied_rules=tuple(applied), rubric_version=self.version)


# -------------------------------------------------------------------- context
def _require_event_context(event: dict[str, Any], context: dict[str, Any]) -> None:
    for key in ("format", "ts", "host"):
        if key not in event:
            raise RubricError(f"event is missing required key {key!r}")
    for key in ("asset", "active_changes", "active_incidents"):
        if key not in context:
            raise RubricError(f"context is missing required key {key!r}")
    _parse_ts(event["ts"], "event.ts")


def _parse_ts(value: str, where: str) -> datetime:
    """Parse ISO-8601 with timezone. Naive times are rejected on purpose:
    comparing a UTC change window to a local log time gives wrong labels."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RubricError(f"{where} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise RubricError(f"{where} must include a timezone: {value!r}")
    return parsed


def _approved_change_covers(event: dict[str, Any], context: dict[str, Any]) -> bool:
    ts = _parse_ts(event["ts"], "event.ts")
    for change in context["active_changes"]:
        for key in ("id", "hosts", "start", "end", "status"):
            if key not in change:
                raise RubricError(f"active_changes item is missing {key!r}")
        if change["status"] != "approved" or event["host"] not in change["hosts"]:
            continue
        start = _parse_ts(change["start"], f"change {change['id']} start")
        end = _parse_ts(change["end"], f"change {change['id']} end")
        if start > end:
            raise RubricError(f"change {change['id']} ends before it starts")
        if start <= ts <= end:
            return True
    return False


def _open_incident_matches(event: dict[str, Any], context: dict[str, Any]) -> bool:
    entities = {event["host"], event.get("service")} - {None}
    return any(inc.get("status") == "open" and inc.get("entity") in entities
               for inc in context["active_incidents"])
