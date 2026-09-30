"""Generate grouped operational examples for harness smoke tests.

This intentionally uses templates with transparent labels. Paired inversions
remain in the same split, preventing a nearly identical phrase from appearing
on both sides of a train/test boundary. Real-world accuracy requires a new,
independently labeled dataset.
"""

import argparse
import json
import random
from pathlib import Path

from models.base import DecisionCase

LABELS = ("security_alert", "schema_mismatch", "telemetry_heartbeat", "audit_log")
QUESTION_CHOICE = "Which operational category best matches this record?"
QUESTION_NOUL = "Does this event require immediate containment?"
QUESTION_SCORE = "How severe is this operational event on a scale from 0 to 100?"

CHOICE_PAIRS = (
    ("Unauthorized port probe detected on host {n}.", "security_alert",
     "Authorized port probe completed on host {n}; this is an audit entry.", "audit_log"),
    ("Payload violated the schema for service {n}.", "schema_mismatch",
     "Payload matched the schema for service {n}; routine audit record.", "audit_log"),
    ("Heartbeat received from service {n}.", "telemetry_heartbeat",
     "Heartbeat missing from service {n}; security alert opened.", "security_alert"),
    ("Audit record saved for service {n}.", "audit_log",
     "Audit record rejected due to schema mismatch in service {n}.", "schema_mismatch"),
)
NOUL_PAIRS = (
    ("Unauthorized privileged login and data export on host {n}; contain immediately.", True,
     "Authorized privileged login with approved change ticket on host {n}; no containment.", False),
    ("Active credential theft detected for account {n}; contain immediately.", True,
     "Routine health ping failed once for account {n} and recovered; do not escalate.", False),
)
SCORE_PAIRS = (
    ("Critical privilege escalation and exfiltration on host {n}.", 100.0,
     "Benign scheduled audit completed on host {n}.", 0.0),
    ("High severity malware alert on host {n}.", 75.0,
     "Low severity transient telemetry delay on host {n}.", 25.0),
)

# Entire wording families are held out at test time. This makes a lexical
# baseline work harder than memorizing identical templates with new host IDs.
TEST_PAIRS = {
    "choice": (
        ("Probe at node {n} was not authorized; investigate as a security alert.", "security_alert",
         "Probe at node {n} was authorized; file the ordinary audit log.", "audit_log"),
        ("Schema validation at node {n} failed for the submitted payload.", "schema_mismatch",
         "Schema validation at node {n} passed; normal telemetry heartbeat.", "telemetry_heartbeat"),
    ),
    "noul": (
        ("Do not dismiss the unauthorized export at node {n}; immediate containment is required.", True,
         "Do not escalate the recovered health ping at node {n}; containment is unnecessary.", False),
        ("The account {n} is actively compromised; stop access now.", True,
         "The account {n} completed a routine scheduled audit; no containment needed.", False),
    ),
    "score": (
        ("Node {n} suffered active privileged data theft.", 100.0,
         "Node {n} recorded a harmless scheduled inspection.", 0.0),
        ("Node {n} has a severe unresolved malware incident.", 75.0,
         "Node {n} had a minor transient telemetry delay.", 25.0),
    ),
}


def generate(count: int = 1000, seed: int = 42) -> dict[str, list[DecisionCase]]:
    """Create exactly count cases, provided count is even and at least ten."""
    if count < 10 or count % 2:
        raise ValueError("count must be an even integer of at least 10")
    rng = random.Random(seed)
    groups: dict[str, list[list[DecisionCase]]] = {"train": [], "val": [], "test": []}
    kinds = ("choice", "noul", "score")
    for group_index in range(count // 2):
        split = ("train" if group_index < int(count // 2 * 0.8) else
                 "val" if group_index < int(count // 2 * 0.9) else "test")
        kind = kinds[group_index % len(kinds)]
        pairs = (TEST_PAIRS[kind] if split == "test" else
                 {"choice": CHOICE_PAIRS, "noul": NOUL_PAIRS, "score": SCORE_PAIRS}[kind])
        left, left_target, right, right_target = pairs[group_index % len(pairs)]
        identifier = f"g{group_index:04d}"
        number = rng.randrange(1000, 9999)
        question = {"choice": QUESTION_CHOICE, "noul": QUESTION_NOUL, "score": QUESTION_SCORE}[kind]
        options = LABELS if kind == "choice" else ()
        groups[split].append([
            DecisionCase(f"{identifier}-a", identifier, left.format(n=number), question,
                         kind, left_target, options),
            DecisionCase(f"{identifier}-b", identifier, right.format(n=number), question,
                         kind, right_target, options, True),
        ])
    # Shuffle only within splits, preserving every pair and held-out family.
    for split_groups in groups.values():
        rng.shuffle(split_groups)
    return {split: [case for group in split_groups for case in group]
            for split, split_groups in groups.items()}


def write_splits(output: Path, count: int = 1000, seed: int = 42) -> dict[str, int]:
    output.mkdir(parents=True, exist_ok=True)
    splits = generate(count, seed)
    for name, cases in splits.items():
        with (output / f"{name}.jsonl").open("w", encoding="utf-8") as stream:
            for case in cases:
                stream.write(json.dumps(vars(case), ensure_ascii=False) + "\n")
    (output / "manifest.json").write_text(
        json.dumps({"kind": "synthetic", "seed": seed, "count": count,
                    "splits": {key: len(value) for key, value in splits.items()}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return {key: len(value) for key, value in splits.items()}


def read_cases(path: Path) -> list[DecisionCase]:
    with path.open(encoding="utf-8") as stream:
        return [DecisionCase.from_dict(json.loads(line)) for line in stream if line.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/splits"))
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(write_splits(args.output, args.count, args.seed))
