"""Markdown and JSON report for the v2 cohort evaluation (WS4).

Every report states, at the top, what the data is (synthetic and generated, or
otherwise), why the numbers are or are not evidence, and that a scorecard pass
is not deployment approval. Provenance fields the caller did not supply are
printed as "not recorded"; nothing is filled in by guessing (AGENTS.md rule 7).
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from evaluation.scorecard import NOT_DEPLOYMENT_APPROVAL, evaluate_candidate
from evaluation.v2_data import (COHORTS, PAGE_THRESHOLD, PRIORITY_BINS, QUESTION_TEXT, STATE_RENDER_VERSION, TASK_KIND,
                                TASKS, V2Dataset, dataset_label, event_types)
from evaluation.v2_metrics import (PAIRED_METRICS, Proportion, build_cohort_matrix, calibration_summary,
                                   consequential_errors, latency_summary, metric_vector, paired_bootstrap_diff)
from evaluation.v2_runner import TIMING_METHOD, CandidateRun

REPORT_VERSION = "v2-report-1"
NOT_RECORDED = "not recorded"
PROVENANCE_FIELDS = ("model_id", "revision", "precision", "prompt_template", "seed", "arm_description")

LOGHUB_URL = "https://github.com/logpai/loghub"
# Same wording as README.md "Data credits" (a test keeps them in step). D8.
LOGHUB_CITATIONS = (
    "Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. *Loghub: A Large Collection of System Log "
    "Datasets for AI-driven Log Analytics.* IEEE ISSRE, 2023.",
    "Zhihan Jiang, Jinyang Liu, Junjie Huang, Yichen Li, Yintong Huo, Jiazhen Gu, Zhuangbin Chen, Jieming Zhu, "
    "Michael R. Lyu. *A Large-scale Evaluation for Log Parsing Techniques: How Far are We?* ACM ISSTA, 2024.",
)

PURPOSE_NOTES = {
    "plumbing_check": ("PLUMBING CHECK ON SYNTHETIC DATA. These numbers show that the harness runs end to end. They "
                       "are not evidence about any model and must not be quoted as results."),
    "measurement": ("Measurement run on the synthetic fixture. It measures this generated dataset only; it does not "
                    "establish real-world accuracy, calibration or safety."),
}

CELL_ORDER = (("A", "A"), ("B", "B"), ("B_prime", "B'"), ("C", "C"), ("D", "D"), ("pooled", "pooled"))

METRIC_TABLES = (
    ("event_type_accuracy", "Event type accuracy (answered calls)"),
    ("page_now_accuracy", "Page-now accuracy (answered calls)"),
    ("must_page_recall", "Must-page recall (answered calls)"),
    ("must_page_recall_strict", "Must-page recall, strict (non-answers count as misses)"),
    ("false_page_rate", "False-page rate (gold not-page, answered)"),
    ("priority_accuracy", "Priority exact accuracy P1-P4 (answered calls)"),
    ("priority_within_one", "Priority within one level"),
    ("paired_inversion", "Paired-inversion accuracy (B pairs: page-now right on both members)"),
    ("paired_inversion_flip_only", "Paired-inversion accuracy, label-flip pairs only"),
    ("spoof_escalation_kept", "B' escalation kept (HARD GATE input; answered calls)"),
    ("spoof_escalation_kept_strict", "B' escalation kept, strict (HARD GATE input; non-answers count as not kept)"),
    ("schema_failure_rate", "Schema-failure rate (attempted calls)"),
    ("exception_rate", "Backend-exception rate (attempted calls)"),
    ("unsupported_rate", "Unsupported rate (N/A, not approximated)"),
    ("coverage", "Coverage (answered / all calls)"),
)


def _ser(obj: Any) -> Any:
    if isinstance(obj, Proportion):
        return obj.to_dict()
    if is_dataclass(obj) and not isinstance(obj, type):
        return _ser(asdict(obj))
    if isinstance(obj, dict):
        return {str(k) if not isinstance(k, tuple) else "/".join(k): _ser(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_ser(v) for v in obj]
    return obj


def _candidate_block(run: CandidateRun) -> dict[str, Any]:
    prov = {k: run.spec.provenance.get(k, NOT_RECORDED) for k in PROVENANCE_FIELDS}
    extra = {k: v for k, v in run.spec.provenance.items() if k not in PROVENANCE_FIELDS}
    return {"key": run.spec.key, "name": run.spec.name, "arm": run.spec.arm, "status": run.status,
            "provenance": prov, "provenance_extra": extra,
            "operational_inputs": {k: run.spec.operational.get(k, NOT_RECORDED)
                                   for k in ("offline_verified", "license_ok", "peak_memory_gb", "baseline_other_gb",
                                             "memory_pressure_normal", "swap_grew")},
            "calibration_fit": run.calibration, "timing": run.timing, "first_errors": run.first_errors,
            "note": run.note}


def build_report(dataset: V2Dataset, runs: list[CandidateRun], cfg: dict[str, Any], seed: int,
                 environment: dict[str, Any], purpose: str = "plumbing_check", include_signal: bool = True,
                 chat: dict[str, Any] | None = None, n_boot: int = 2000) -> dict[str, Any]:
    """Assemble the full report dict from verified data and finished runs."""
    if purpose not in PURPOSE_NOTES:
        raise ValueError(f"purpose must be one of {sorted(PURPOSE_NOTES)}")
    keys = [r.spec.key for r in runs]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate candidate/arm rows: {keys}")
    manifest = dataset.manifest
    test = dataset.test
    by_cohort = {c: sum(1 for x in test if x["cohort"] == c) for c in COHORTS}
    measured = [r for r in runs if r.test is not None]

    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "dataset_label": f"dataset: {dataset_label(dataset.dataset_kind)}",
        "purpose": purpose, "purpose_note": PURPOSE_NOTES[purpose],
        "not_deployment_approval": NOT_DEPLOYMENT_APPROVAL,
        "headline_split": "test",
        "split_policy": "Headline metrics use the test split only. Validation is used only to fit calibration "
                        "(and, later, thresholds). Train is never scored.",
        "dataset": {
            "dataset_kind": dataset.dataset_kind, "real_data": manifest["real_data"],
            "directory_name": dataset.directory.name, "generator_version": manifest["generator_version"],
            "generator": manifest["generator"], "dataset_seed": manifest["seed"],
            "rubric_version": manifest["rubric_version"], "rubric_file_sha256_manifest": manifest["rubric_file_sha256"],
            "rubric_file_sha256_now": dataset.rubric_sha256_now, "manifest_sha256": dataset.manifest_sha256,
            "files": manifest["files"], "counts_by_split": manifest["counts"]["by_split"],
            "test_cases_by_cohort": by_cohort, "seed_sources_used": manifest.get("seed_sources_used", {}),
            "slang_lexicon_version": manifest.get("slang_lexicon_version"),
            "seed_registry": manifest.get("seed_registry"),
            "validity_limits": manifest.get("rubric_validity_limits", []),
            "not_implemented": manifest.get("not_implemented", []),
        },
        "citations": ({"required": True, "reference": LOGHUB_URL, "items": list(LOGHUB_CITATIONS),
                       "license_notice": "data/seeds/LOGHUB_LICENSE",
                       "note": "Loghub-derived templates (D8): non-commercial research use. Labels are this "
                               "project's rubric applied to real log syntax, not Loghub ground truth."}
                      if dataset.uses_loghub else {"required": False}),
        "environment": environment,
        "run": {"seed": seed, "bootstrap_resamples": n_boot, "include_event_signal": include_signal,
                "state_render_version": STATE_RENDER_VERSION, "page_threshold": PAGE_THRESHOLD,
                "timing_method": TIMING_METHOD,
                "seed_note": "The seed drives the bootstrap. Adapter-side randomness, if any, is the adapter's "
                             "responsibility and is recorded in its provenance when supplied."},
        "task_mapping": {t: {"adapter_kind": TASK_KIND[t], "question": QUESTION_TEXT[t]} for t in TASKS}
                        | {"event_types": list(event_types()),
                           "priority_bins": [list(b) for b in PRIORITY_BINS],
                           "priority_note": "0-100 adapter score binned into P1-P4 by the harness; a measurement "
                                            "convention, not an answer key"},
        "candidates": [_candidate_block(r) for r in runs],
    }

    matrices, errors, calibration, latency = {}, {}, {}, {}
    for r in measured:
        matrices[r.spec.key] = build_cohort_matrix(test, r.test)
        errors[r.spec.key] = consequential_errors(test, r.test)
        calibration[r.spec.key] = {
            "fit": r.calibration,
            "val": calibration_summary(dataset.val, r.val),
            "test": calibration_summary(test, r.test),
            "val_note": ("validation, in-sample for a calibrated arm (fitted here); out-of-sample is the test row"
                         if r.calibration else "validation, the split calibration is fitted on"),
        }
        latency[r.spec.key] = latency_summary(r.latencies) | {"timing": r.timing,
                                                              "hardware": environment.get("hardware")}
    report["raw_outcomes"] = {r.spec.key: {"test": [o.to_dict() for _, o in sorted(r.test.items())],
                                           "val": [o.to_dict() for _, o in sorted(r.val.items())]}
                              for r in measured}
    report["cohort_matrix"] = matrices
    report["consequential_errors"] = errors
    report["calibration"] = calibration
    report["latency"] = latency

    clusters = {c["case_id"]: dataset.group_of_pair.get(c["pair_id"], c["pair_id"]) for c in test}
    diffs = []
    for i, a in enumerate(measured):
        for b in measured[i + 1:]:
            if a.spec.name == b.spec.name:
                continue                       # raw and calibrated arms share decisions
            for metric in PAIRED_METRICS:
                diffs.append({"metric": metric, "a": a.spec.key, "b": b.spec.key} | paired_bootstrap_diff(
                    metric_vector(metric, test, a.test), metric_vector(metric, test, b.test), clusters, seed, n_boot))
    report["paired_differences"] = diffs

    rows = [evaluate_candidate(cfg, r, test, str(environment.get("hardware", "")), purpose, chat) for r in runs]
    report["scorecard"] = {"config_version": cfg["scorecard_version"], "config_status": cfg["status"],
                           "gate_rule": cfg["gate_rule"], "cost_matrix": cfg["cost_matrix"],
                           "cost_matrix_status": "PLACEHOLDER (D13): relative costs, owner to set after the pilot",
                           "weights": cfg["weights"], "rows": rows}
    report["chat_s9"] = (chat if chat else {"status": "no S9 chat results supplied (no S9 runner yet); not pooled "
                                                      "with the core suites"})
    report["caveats"] = [
        f"Test split has {len(test)} cases ({by_cohort}); intervals are wide and rankings between close candidates "
        "are not reliable.",
        "Wilson intervals assume independent cases; cases sharing a pair or template group are correlated, so they "
        "are optimistic. The paired bootstrap resamples whole groups.",
        "Labels are derived by code from frozen rubric 2.4.0; they are not human-adjudicated. Cohort D has no gold: "
        "no accuracy or ECE is computed for it.",
        "Cohort-level ECE is not reported; calibration is pooled, with bin counts.",
        "Memory, offline operation and latency on the target Mac were not measured by this run unless shown "
        "otherwise in the gate table.",
    ]
    return _ser(report)


# --------------------------------------------------------------------------- markdown
def _p(cell: dict[str, Any] | None) -> str:
    if not cell or cell.get("den", 0) == 0 or cell.get("rate") is None:
        return "N/A"
    return f"{cell['rate']:.2f} ({cell['num']}/{cell['den']}) [{cell['ci_low']:.2f}, {cell['ci_high']:.2f}]"


def _num(value: float | None, digits: int = 3) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out + [""]


def render_markdown(report: dict[str, Any]) -> str:
    d, run = report["dataset"], report["run"]
    L: list[str] = ["# v2 decision-model evaluation report", "",
                    f"## **{report['dataset_label']}**", "",
                    f"> **{report['purpose_note']}**", "",
                    f"> {report['not_deployment_approval']}", "",
                    f"Report version `{report['report_version']}`. {report['split_policy']}", ""]
    if report["citations"]["required"]:
        c = report["citations"]
        L += ["## Loghub citation (D8)", "",
              f"This dataset contains Loghub-derived templates. Reference: <{c['reference']}>. Please cite:", ""]
        L += [f"- {item}" for item in c["items"]]
        L += ["", c["note"] + f" Licence notice: `{c['license_notice']}`.", ""]

    L += ["## Provenance", "", "### Dataset", "",
          f"- Kind: `{d['dataset_kind']}` (real_data: {d['real_data']}); directory `{d['directory_name']}`",
          f"- Generator: `{d['generator']}` version `{d['generator_version']}`, dataset seed {d['dataset_seed']}",
          f"- Rubric: version `{d['rubric_version']}`, file sha256 (manifest) `{d['rubric_file_sha256_manifest']}`, "
          f"current file sha256 `{d['rubric_file_sha256_now']}`",
          f"- Manifest sha256: `{d['manifest_sha256']}` (file hashes verified with the generator's own check)",
          f"- Split counts: {d['counts_by_split']}; test cases by cohort: {d['test_cases_by_cohort']}",
          f"- Seed sources used: {d['seed_sources_used']}",
          "- Dataset files: " + "; ".join(f"{n} sha256 `{m['sha256'][:16]}...` ({m['cases']} cases)"
                                           for n, m in d["files"].items()),
          "- Validity limits: " + " | ".join(d["validity_limits"]), "",
          "### Run", "",
          f"- Harness seed: {run['seed']} (bootstrap, {run['bootstrap_resamples']} cluster resamples)",
          f"- Model input: `{run['state_render_version']}` (event + context only), event.signal shown: "
          f"{run['include_event_signal']}; page threshold {run['page_threshold']}",
          f"- Timing method: {run['timing_method']}", ""]
    env = report["environment"]
    L += [f"- Hardware: {env['hardware']}; platform {env['platform']}; Python {env['python']}; power mode: "
          f"{env['power_mode']}", f"- Memory sampling: {env['memory_sampling']}",
          "- Packages: " + ", ".join(f"{k} {v or 'not installed'}" for k, v in env["packages"].items()), "",
          "### Candidates", ""]
    rows = []
    for c in report["candidates"]:
        p = c["provenance"]
        rows.append([c["key"], c["status"], str(p["model_id"]), str(p["revision"]), str(p["precision"]),
                     str(p["prompt_template"]), str(p["seed"]), c["note"] or ""])
    L += _table(["Candidate/arm", "Status", "Model id", "Revision", "Precision", "Prompt/template", "Seed", "Note"], rows)
    for c in report["candidates"]:
        if c["provenance_extra"]:
            L.append(f"- {c['key']} extra provenance: {json.dumps(c['provenance_extra'], sort_keys=True)}")
        if c["first_errors"]:
            L.append(f"- {c['key']} first errors: " + " | ".join(c["first_errors"]))
    L.append("")

    tm = report["task_mapping"]
    L += ["## Task mapping", "",
          "A v2 case lists three questions; each becomes one adapter call. "
          + "; ".join(f"`{t}` -> {tm[t]['adapter_kind']}" for t in TASKS) + ". "
          f"Event types: {', '.join(tm['event_types'])}. {tm['priority_note']}: "
          + ", ".join(f"{p} >= {lo:g}" for p, lo in tm["priority_bins"]) + ".", ""]

    keys = list(report["cohort_matrix"])
    L += ["## Cohort matrix", "",
          "Rows are candidate x arm; columns are cohort groups (n = test cases). Each cell: rate (numerator/denominator) "
          "[Wilson 95%]. `N/A` is never zero: it means unsupported, unmeasured, or not defined (reasons in the JSON). "
          "Cohort D has no gold, so no accuracy appears for it. `pooled` is A+B+B'+C.", ""]
    n_by = d["test_cases_by_cohort"]
    heads = ["Candidate/arm"] + [f"{lbl} (n={n_by.get(c, sum(v for k, v in n_by.items() if k != 'D'))})"
                                 for c, lbl in CELL_ORDER]
    for metric, title in METRIC_TABLES:
        L += [f"### {title}", ""]
        L += _table(heads, [[k] + [_p(report["cohort_matrix"][k][c].get(metric)) for c, _ in CELL_ORDER] for k in keys])
    L += ["### Priority mean absolute error (ordinal levels, P1=1 .. P4=4)", ""]
    L += _table(heads, [[k] + [(lambda m: "N/A" if m["mean"] is None else f"{m['mean']:.2f} (n={m['n']})")(
        report["cohort_matrix"][k][c]["priority_mae_levels"]) for c, _ in CELL_ORDER] for k in keys])
    L += ["### Cohort D (boundary, unlabeled)", "",
          "Coverage and failures are in the tables above. Agreement with provisional labels is shown only when such "
          "labels exist (none are shipped). Abstention cannot be observed through the current adapter interface.", ""]
    L += _table(["Candidate/arm", "Coverage D", "Provisional agreement", "Abstention"],
                [[k, _p(report["cohort_matrix"][k]["D"]["coverage"]),
                  ("N/A (" + report["cohort_matrix"][k]["D"]["provisional_agreement"]["na_reason"] + ")")
                  if report["cohort_matrix"][k]["D"]["provisional_agreement"]["na_reason"]
                  else json.dumps(report["cohort_matrix"][k]["D"]["provisional_agreement"]["per_task"]),
                  "N/A (no abstain output)"] for k in keys])

    L += ["## Consequential errors (listed first by the reporting rules; counts and case ids)", ""]
    for k in keys:
        e = report["consequential_errors"][k]
        L.append(f"- **{k}**: missed must-page {e['missed_must_page']['count']} "
                 f"{[c['case_id'] for c in e['missed_must_page']['cases']]}; improper suppression "
                 f"{e['improper_suppression']['count']} {[c['case_id'] for c in e['improper_suppression']['cases']]}; "
                 f"unanswered must-page {e['unanswered_must_page']['count']} "
                 f"{[c['case_id'] for c in e['unanswered_must_page']['cases']]}")
    L.append("")

    L += ["## Paired differences between candidates (identical cases, seeded cluster bootstrap)", ""]
    if report["paired_differences"]:
        L += _table(["Metric", "A", "B", "n", "A - B", "95% CI", "clusters", "note"],
                    [[x["metric"], x["a"], x["b"], str(x["n"]), _num(x["diff"]),
                      "N/A" if x["ci_low"] is None else f"[{x['ci_low']:.3f}, {x['ci_high']:.3f}]",
                      str(x["n_clusters"]), x["na_reason"] or ""] for x in report["paired_differences"]])
    else:
        L += ["Fewer than two measured candidates; no paired comparison.", ""]

    L += ["## Calibration (separate table; pooled only)", "",
          "Brier and ECE over pooled graded A/B/B'/C cases, with bin counts. Only real model probabilities count: a "
          "hard label or a generated claim is N/A. Validation is shown because calibration is fitted there; the test "
          "row is the out-of-sample figure. Raw and calibrated arms are separate rows.", ""]
    crow = []
    for k in keys:
        for split in ("val", "test"):
            s = report["calibration"][k][split]
            crow.append([k, split, str(s["n"]), _num(s["brier"]), _num(s["ece"]),
                         s["na_reason"] or (s["warning"] or "")])
    L += _table(["Candidate/arm", "Split", "n", "Brier", "ECE", "Note"], crow)
    for k in keys:
        fit = report["calibration"][k]["fit"]
        if fit:
            L.append(f"- {k}: temperature {fit['temperature']:.2f} fitted on {fit['fit_split']} (n={fit['fit_n']}), "
                     f"fit_on_test={fit['fit_on_test']}. {report['calibration'][k]['val_note']}.")
        s = report["calibration"][k]["test"]
        if s["bins"]:
            L.append(f"- {k} test bin counts (confidence bins of width 0.1): "
                     + ", ".join(f"[{b['low']:.1f},{b['high']:.1f}) n={b['n']}" for b in s["bins"] if b["n"]))
    L.append("")

    L += ["## Latency (separate table)", "",
          "Batch size 1, per call. Latency taken off the target Mac is a plumbing figure, not a target-hardware result.", ""]
    lrows = []
    for k in keys:
        s = report["latency"][k]
        lrows.append([k, str(s["n"]), _num(s["p50_ms"], 2), _num(s["p95_ms"], 2), str(s["hardware"]),
                      s["na_reason"] or s["timing"].get("status", "")])
    L += _table(["Candidate/arm", "Samples", "p50 ms", "p95 ms", "Hardware", "Note"], lrows)

    sc = report["scorecard"]
    L += ["## Selection scorecard", "", f"> {report['not_deployment_approval']}", "",
          f"Config `{sc['config_version']}`: {sc['config_status']}. Gate rule: `{sc['gate_rule']}`.",
          f"**Cost matrix is a PLACEHOLDER (D13):** {json.dumps(sc['cost_matrix'])}. Weights: {json.dumps(sc['weights'])}.", ""]
    L += _table(["Candidate/arm", "Verdict", "Weight evaluated", "Partial score (not comparable to a full score)"],
                [[f"{r['candidate']}/{r['arm']}", r["verdict"], f"{r['weight_coverage']:.0%}",
                  _num(r["partial_score"])] for r in sc["rows"]])
    for r in sc["rows"]:
        L += [f"### {r['candidate']}/{r['arm']}: {r['verdict']}", ""]
        L += [f"- {x}" for x in r["reasons"]] + [""]
        if r["gates"]:
            L += _table(["Gate", "Status", "Detail"], [[g["name"], g["status"], g["detail"]] for g in r["gates"]])
        if r["components"]:
            L += _table(["Component", "Weight", "Score", "Note"],
                        [[n, f"{c['weight']:.3f}", _num(c["score"]), c["note"]] for n, c in r["components"].items()])
        if r.get("cost"):
            c = r["cost"]
            L.append(f"- Cost-weighted (PLACEHOLDER matrix), cohorts {c['cohorts']}: total {_num(c['total_cost'], 1)}, "
                     f"mean per case {_num(c['mean_cost_per_case'], 2)}, normalized error {_num(c['normalized_error'])}"
                     + (f" ({c['na_reason']})" if c["na_reason"] else ""))
        if r["worst_failures"]:
            L.append("- Three worst failures: " + "; ".join(
                f"{f['case_id']} {f['task']} gold={f['gold']} predicted={f['predicted']} cost={f['cost']}"
                for f in r["worst_failures"]))
        L.append("")

    L += ["## S9 chat module (reported separately, never pooled)", ""]
    chat = report["chat_s9"]
    L += [chat["status"] if "status" in chat else json.dumps(chat, sort_keys=True), ""]
    L += ["## Caveats", ""] + [f"- {c}" for c in report["caveats"]] + [""]
    return "\n".join(L)


def write_report(report: dict[str, Any], markdown_path: Path, json_path: Path) -> None:
    """Write both files. JSON refuses NaN/Infinity so a bad number cannot slip through."""
    Path(markdown_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    Path(markdown_path).write_text(render_markdown(report), encoding="utf-8")
