"""Loader and task mapping for the v2 cohort dataset (WS4).

The v2 dataset is produced by ``data/generator_v2.py`` as a *synthetic,
generated* harness fixture. This module:

* loads cases only after the generator's own ``verify_manifest`` passes and the
  hashes are re-checked on the exact bytes parsed (so a file changed between
  verification and parsing is still caught). Any mismatch raises
  ``DatasetIntegrityError``; nothing is repaired or skipped.
* maps one v2 case (one event, three questions) to three ``DecisionCase``
  objects, one per scored primitive, through an explicit and documented table
  (``TASK_KIND`` below). Nothing here edits the frozen rubric or the generator.
* renders the model input from an allow-list (``event`` and ``context`` only), so
  labels, evidence, archetype names, spoof/pair metadata and the manifest cannot
  reach an adapter.

Split discipline (AGENTS.md rule 3): ``test`` is the measured split, ``val`` is
for calibration and threshold choice only, ``train`` is loaded only on request
(a retrieval or trained candidate needs it) and is never scored for a headline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data.generator_v2 import DATASET_KIND, SPLITS, verify_manifest
from data.rubric import DEFAULT_RUBRIC, PRIORITIES
from models.base import DecisionCase

# Version of the text rendering below. It is part of the prompt/template
# provenance (AGENTS.md rule 7): changing the rendering changes this string.
STATE_RENDER_VERSION = "v2-state-render-1"

# The three scored primitives, in the order the generator lists them in
# ``case["questions"]``. A case whose ``questions`` differ is rejected loudly
# instead of being guessed at.
TASKS = ("event_type", "page_now", "priority")

# Explicit mapping from a v2 question to the v1 adapter primitive.
#   event_type -> "choice"  (one of the six rubric event types)
#   page_now   -> "noul"    (probability that the answer is "page now"; the
#                            harness thresholds it at 0.5 for a hard decision)
#   priority   -> "score"   (0-100 urgency, binned into P1-P4 by the harness)
TASK_KIND = {"event_type": "choice", "page_now": "noul", "priority": "score"}

# Gold key inside ``case["expected"]`` for each task. The generator calls the
# three primitives choice / noul / score for backward compatibility.
GOLD_KEY = {"event_type": "choice", "page_now": "noul", "priority": "score"}

# Priority is an ordinal, not a number. The v1 adapter contract returns a
# 0-100 score, so the harness uses four equal-width bins where higher means
# more urgent. This is a measurement convention, not an answer key
# (PRACTICAL_EVAL_V2 section 1). ``PRIORITY_ANCHOR`` is the bin centre.
PRIORITY_BINS = (("P1", 75.0), ("P2", 50.0), ("P3", 25.0), ("P4", 0.0))
PRIORITY_ANCHOR = {"P1": 87.5, "P2": 62.5, "P3": 37.5, "P4": 12.5}
PRIORITY_INDEX = {p: i + 1 for i, p in enumerate(PRIORITIES)}

# Cohort names exactly as the generator writes them.
COHORTS = ("A", "B", "B_prime", "C", "D")
GRADED_COHORTS = ("A", "B", "B_prime", "C")      # D is never gold

PAGE_THRESHOLD = 0.5

QUESTION_TEXT = {
    "event_type": "Which event type best describes this event?",
    "page_now": "Does this event require paging the on-call human now?",
    "priority": ("Rate the response urgency from 0 to 100, where higher is more urgent: "
                 "75-100 is P1, 50-74 is P2, 25-49 is P3 and 0-24 is P4."),
}

_DATASET_LABELS = {DATASET_KIND: "SYNTHETIC (generated), not real data"}


class DatasetIntegrityError(ValueError):
    """The dataset on disk does not match its manifest, or violates the v2 contract."""


def event_types() -> tuple[str, ...]:
    """The six rubric event types, read from the frozen rubric file (read-only)."""
    rubric = json.loads(Path(DEFAULT_RUBRIC).read_text(encoding="utf-8"))
    return tuple(rubric["event_types"])


def level_from_score(score: float) -> str:
    """Bin a 0-100 urgency score into P1-P4 (``PRIORITY_BINS``); 75.0 is P1."""
    for level, floor in PRIORITY_BINS:
        if score >= floor:
            return level
    raise ValueError(f"score {score!r} below 0")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def dataset_label(kind: str) -> str:
    """Human label for the report banner. Unknown kinds raise: a report must never
    guess whether data is real."""
    try:
        return _DATASET_LABELS[kind]
    except KeyError:
        raise DatasetIntegrityError(
            f"unsupported dataset_kind {kind!r}; the v2 loader reads only {sorted(_DATASET_LABELS)}") from None


def gold(case: dict[str, Any]) -> dict[str, Any] | None:
    """Gold answers by task name, or None for an ungraded case (cohort D)."""
    expected = case.get("expected")
    if not expected:
        return None
    return {task: expected[GOLD_KEY[task]] for task in TASKS}


def render_state(case: dict[str, Any], include_signal: bool = True) -> str:
    """Model-visible text for a case: the event and the trusted context only.

    Allow-list on purpose. ``label``, ``evidence``, ``expected``, ``archetype``,
    ``variant``, ``spoof_kind``, ``pair_relation``, ``slang_term``, template and
    wrapper ids are never rendered. ``event.signal`` is the detector name the
    rubric's expected-activity rule matches against a change's
    ``expected_signals``; it is shown by default because without it a model
    cannot apply that rule, and it can be hidden to test lexical shortcuts. The
    choice is recorded in provenance as ``include_event_signal``.
    """
    event = case["event"]
    lines = [f"EVENT format={event.get('format', 'unknown')}", event["raw"]]
    lines.extend(event.get("window", []))
    fields = {k: event[k] for k in ("host", "service", "ts") if k in event}
    if include_signal and "signal" in event:
        fields["signal"] = event["signal"]
    lines.append("EVENT FIELDS " + json.dumps(fields, sort_keys=True))
    lines.append("CONTEXT " + json.dumps(case["context"], sort_keys=True))
    return "\n".join(lines)


def to_decision_cases(case: dict[str, Any], *, with_target: bool,
                      include_signal: bool = True) -> dict[str, DecisionCase]:
    """The three adapter-facing cases for one v2 case, keyed by task.

    ``with_target`` is True only when the cases will be used to fit or index a
    candidate (train split). For val/test the target is ``None`` so an adapter
    cannot read the answer; the harness scores from the v2 case itself.
    """
    state = render_state(case, include_signal)
    answers = gold(case) if with_target else None
    if with_target and answers is None:
        raise DatasetIntegrityError(f"{case['case_id']}: ungraded case cannot be used as a training target")
    out: dict[str, DecisionCase] = {}
    for task in TASKS:
        kind = TASK_KIND[task]
        target: Any = None
        if answers is not None:
            target = PRIORITY_ANCHOR[answers[task]] if task == "priority" else answers[task]
        out[task] = DecisionCase(
            id=f"{case['case_id']}::{task}", pair_id=case["pair_id"], state=state,
            question=QUESTION_TEXT[task], kind=kind, target=target,
            options=event_types() if kind == "choice" else (),
            adversarial=case["cohort"] == "B_prime",
        )
    return out


@dataclass(frozen=True)
class V2Dataset:
    directory: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    cases: dict[str, list[dict[str, Any]]]
    rubric_sha256_now: str
    group_of_pair: dict[str, str] = field(default_factory=dict)

    @property
    def test(self) -> list[dict[str, Any]]:
        return self.split("test")

    @property
    def val(self) -> list[dict[str, Any]]:
        return self.split("val")

    def split(self, name: str) -> list[dict[str, Any]]:
        if name not in self.cases:
            raise KeyError(f"split {name!r} was not loaded; loaded: {sorted(self.cases)}")
        return self.cases[name]

    @property
    def by_id(self) -> dict[str, dict[str, Any]]:
        return {c["case_id"]: c for rows in self.cases.values() for c in rows}

    @property
    def dataset_kind(self) -> str:
        return self.manifest["dataset_kind"]

    @property
    def uses_loghub(self) -> bool:
        used = self.manifest.get("seed_sources_used", {})
        return bool(self.manifest.get("loghub_citation_required")) or used.get("loghub", 0) > 0


def _check_expected_matches_label(row: dict[str, Any]) -> None:
    """The generator's lint re-derives ``label`` from the rubric but does not compare ``expected`` with it.
    Scoring reads ``expected``, so a hand-edited ``expected`` must fail here, loudly."""
    label, expected = row.get("label"), row.get("expected")
    if label is None and expected is None:
        return
    if label is None or expected is None or (
            expected.get("choice"), expected.get("noul"), expected.get("score")) != (
            label["event_type"], label["page_now"], label["priority"]):
        raise DatasetIntegrityError(f"{row['case_id']}: expected answers do not match the stored label")


def load_v2_dataset(directory: Path, splits: tuple[str, ...] = ("val", "test"),
                    allow_rubric_drift: bool = False) -> V2Dataset:
    """Verify the manifest with the generator's function, then load ``splits``.

    Raises ``DatasetIntegrityError`` on any problem. Default loads val and test
    only; ask for ``"train"`` explicitly when a candidate needs it.
    """
    directory = Path(directory)
    bad = [s for s in splits if s not in SPLITS]
    if bad:
        raise ValueError(f"unknown splits {bad}; choose from {SPLITS}")
    problems = verify_manifest(directory)
    if problems:
        raise DatasetIntegrityError("dataset failed manifest verification: " + "; ".join(problems))
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    label = dataset_label(manifest.get("dataset_kind", ""))          # raises on an unknown kind
    if manifest.get("real_data") is not False:
        raise DatasetIntegrityError(f"manifest real_data is {manifest.get('real_data')!r}; expected False "
                                    f"for a {label} fixture")
    cases: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for split in splits:
        meta = manifest["files"][f"{split}.jsonl"]
        data = (directory / f"{split}.jsonl").read_bytes()
        # Re-hash the bytes about to be parsed: closes the gap between verify and read.
        if sha256_bytes(data) != meta["sha256"]:
            raise DatasetIntegrityError(f"{split}.jsonl changed after verification")
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        for row in rows:
            if row.get("split") != split:
                raise DatasetIntegrityError(f"{row.get('case_id')}: split {row.get('split')!r} found in {split}.jsonl")
            if list(row.get("questions", [])) != list(TASKS):
                raise DatasetIntegrityError(f"{row.get('case_id')}: questions {row.get('questions')!r} "
                                            f"do not match the mapped tasks {list(TASKS)}")
            if row["cohort"] not in COHORTS:
                raise DatasetIntegrityError(f"{row['case_id']}: unknown cohort {row['cohort']!r}")
            if row["case_id"] in seen:
                raise DatasetIntegrityError(f"duplicate case_id {row['case_id']}")
            seen.add(row["case_id"])
            if row["cohort"] == "D" and row.get("label") is not None:
                raise DatasetIntegrityError(f"{row['case_id']}: cohort D must be ungraded")
            _check_expected_matches_label(row)
        cases[split] = rows
    rubric_now = sha256_file(Path(DEFAULT_RUBRIC))
    if rubric_now != manifest.get("rubric_file_sha256") and not allow_rubric_drift:
        raise DatasetIntegrityError(
            "rubric file hash differs from the manifest (rubric changed since generation): "
            f"manifest {manifest.get('rubric_file_sha256')}, now {rubric_now}")
    group_of_pair = {pid: gid for gid, g in manifest.get("groups", {}).items() for pid in g["pair_ids"]}
    return V2Dataset(directory, manifest, sha256_bytes(manifest_bytes), cases, rubric_now, group_of_pair)
