"""Command line entry for the v2 cohort evaluation (WS4).

    uv run python -m data.generator_v2 --output artifacts/cohort_v2 --seed 42
    uv run python -m evaluation.v2_cli --data-dir artifacts/cohort_v2 --models lexical

Defaults write under ``artifacts/`` (git-ignored). ``--purpose`` defaults to
``plumbing_check`` so a casual run cannot be mistaken for a measurement; pass
``--purpose measurement`` deliberately, on the target hardware, with the
candidate provenance filled in.

The Laya, MPS and generative adapters are the v1 adapters, NOT retargeted to
the v2 six event types and priority task (WS8 owns that). They are driven
unchanged through the v2 mapping when requested. What they cannot do surfaces
as ``unsupported`` (N/A with coverage), e.g. the fixed four-label MPS head
refuses the six-type option set with ``ModelUnavailable``; a load failure
(missing checkpoint, missing MLX on this host) is an "unavailable" row with the
reason. The runner forces HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 first so
nothing is downloaded. The non-lexical paths are NOT exercised on this Linux
host beyond the failure path; see docs/EVALUATION_V2.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from evaluation.scorecard import ScorecardConfigError, load_config
from models.base import ModelUnavailable
from evaluation.v2_data import STATE_RENDER_VERSION, DatasetIntegrityError, load_v2_dataset, to_decision_cases
from evaluation.v2_report import build_report, write_report
from evaluation.v2_runner import (OPERATIONAL_KEYS, CandidateRun, CandidateSpec, collect_environment, fit_calibrated_arm,
                                  run_candidate)

KNOWN = ("lexical", "laya", "mps", "generative", "generative_finite")
DEFAULT_V1_CONFIG = Path("configs/benchmark_config.yaml")
V1_CHECKPOINT_KEY = {"laya": "laya_checkpoint", "mps": "mps_checkpoint", "generative": "generative_checkpoint",
                     "generative_finite": "generative_checkpoint"}
V1_NOTE = ("v1 adapter driven through the v2 task mapping WITHOUT retargeting (WS8). Tasks it cannot do show as "
           "unsupported (N/A) with coverage; its output on this mapping is unverified on this host")


def _force_offline() -> None:
    """A benchmark run must never download weights (AGENTS.md rule 4): force the Hugging Face offline switches
    before any adapter resolves an identifier, so an unresolved ID fails locally."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def _v1_spec(name: str, config_path: Path) -> CandidateSpec:
    """Load a v1 adapter from the v1 config. A load failure is an unavailable row with its reason, never a score."""
    from evaluation.benchmark_runner import load_model
    _force_offline()
    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        model = load_model(name, config, [])
    except ModelUnavailable as exc:
        return CandidateSpec(name, "raw", None, unavailable_reason=f"unavailable: {exc}")
    except Exception as exc:        # a backend/load error is reported as such, not as a prediction
        return CandidateSpec(name, "raw", None, unavailable_reason=f"load error: {type(exc).__name__}: {exc}")
    return CandidateSpec(name, "raw", model, {
        "model_id": str(config.get(V1_CHECKPOINT_KEY[name], "not recorded")),
        "revision": "not recorded (resolve from the model-manager manifest; WS8)",
        "precision": "not recorded", "seed": "not recorded", "prompt_template": "v1 adapter prompt, not retargeted",
        "arm_description": V1_NOTE, "offline_env": "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 set by the runner"})


def build_specs(names: list[str], dataset_dir: Path, include_signal: bool,
                v1_config: Path = DEFAULT_V1_CONFIG) -> list[CandidateSpec]:
    """Candidate rows. Train is loaded only for a candidate that indexes or fits on it."""
    specs: list[CandidateSpec] = []
    for name in names:
        if name != "lexical":
            specs.append(_v1_spec(name, v1_config))
            continue
        train = load_v2_dataset(dataset_dir, splits=("train",)).split("train")
        train_cases = [dc for case in train if case["expected"]
                       for dc in to_decision_cases(case, with_target=True, include_signal=include_signal).values()]
        from models.lexical_bm25 import LexicalBM25
        try:
            model = LexicalBM25(train_cases)
        except Exception as exc:          # ModelUnavailable (rank-bm25 missing) or unusable data: say so, do not hide it
            specs.append(CandidateSpec(name, "raw", None, unavailable_reason=f"{type(exc).__name__}: {exc}"))
            continue
        specs.append(CandidateSpec(
            name, "raw", model,
            {"model_id": "rank_bm25.BM25Okapi nearest labeled train example (no weights)",
             "revision": "not applicable (no checkpoint); library version in environment",
             "precision": "not applicable", "seed": "deterministic, no randomness",
             "prompt_template": f"no prompt; retrieval over {STATE_RENDER_VERSION} text",
             "arm_description": "hard labels from the nearest train example; probabilities are not calibrated"}))
    return specs


def apply_candidate_info(specs: list[CandidateSpec], info: dict) -> None:
    """Merge caller-supplied provenance and gate inputs into the specs, by candidate name.

    ``info`` is ``{"laya": {"provenance": {...}, "operational": {...}}, ...}``. The caller (for example the
    Mac session) is the only party that knows the real revision, precision and measured memory; nothing is
    guessed. An unknown candidate name or operational key raises ``ValueError`` instead of being ignored.
    """
    by_name = {s.name: s for s in specs}
    for name, entry in info.items():
        if name not in by_name:
            raise ValueError(f"--candidate-info names {name!r}, which is not in --models {sorted(by_name)}")
        if set(entry) - {"provenance", "operational"}:
            raise ValueError(f"--candidate-info[{name!r}] may only hold provenance and operational")
        unknown = set(entry.get("operational", {})) - set(OPERATIONAL_KEYS)
        if unknown:
            raise ValueError(f"--candidate-info[{name!r}] has unknown operational keys {sorted(unknown)}")
        by_name[name].provenance.update(entry.get("provenance", {}))
        by_name[name].operational.update(entry.get("operational", {}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path("artifacts/cohort_v2"))
    parser.add_argument("--models", default="lexical")
    parser.add_argument("--config", type=Path, default=None,
                        help="scorecard config (default configs/selection_scorecard.yaml)")
    parser.add_argument("--v1-config", type=Path, default=DEFAULT_V1_CONFIG,
                        help="v1 benchmark config naming local checkpoints for laya/mps/generative")
    parser.add_argument("--iterations", type=int, default=0, help="timed calls; 0 skips timing")
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0, help="bootstrap seed")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--purpose", choices=("plumbing_check", "measurement"), default="plumbing_check")
    parser.add_argument("--hide-event-signal", action="store_true", help="omit event.signal from the model input")
    parser.add_argument("--candidate-info", type=Path, default=None,
                        help="JSON {name: {provenance: {...}, operational: {...}}} with real revisions, precision, "
                             "measured memory and attested offline/licence status")
    parser.add_argument("--chat-results", type=Path, default=None,
                        help="optional S9 results JSON (reported separately, never pooled)")
    parser.add_argument("--report", type=Path, default=Path("artifacts/v2_report.md"))
    parser.add_argument("--raw", type=Path, default=Path("artifacts/v2_report.json"))
    args = parser.parse_args(argv)
    names = [n for n in args.models.split(",") if n]
    bad = [n for n in names if n not in KNOWN]
    if bad or not names:
        parser.error(f"choose from {', '.join(KNOWN)}")
    include_signal = not args.hide_event_signal
    try:
        cfg = load_config(args.config)
        dataset = load_v2_dataset(args.data_dir, splits=("val", "test"))      # verify before loading any model
        specs = build_specs(names, args.data_dir, include_signal, args.v1_config)
        if args.candidate_info:
            apply_candidate_info(specs, json.loads(args.candidate_info.read_text(encoding="utf-8")))
    except (DatasetIntegrityError, ScorecardConfigError, ValueError, OSError) as exc:
        print(f"refusing to run: {exc}", file=sys.stderr)
        return 2
    chat = json.loads(args.chat_results.read_text(encoding="utf-8")) if args.chat_results else None
    runs: list[CandidateRun] = []
    for spec in specs:
        raw = run_candidate(spec, dataset, args.iterations, args.warmup, include_signal)
        runs.append(raw)
        runs.append(fit_calibrated_arm(raw, dataset))
        print(f"{spec.name}: {raw.status}" + (f" ({raw.note})" if raw.note else ""))
    report = build_report(dataset, runs, cfg, args.seed, collect_environment(), args.purpose, include_signal, chat,
                          args.bootstrap)
    write_report(report, args.report, args.raw)
    print(f"wrote {args.report} and {args.raw} (dataset: SYNTHETIC, purpose: {args.purpose})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
