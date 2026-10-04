"""Report provenance, labels, citation block, N/A handling and the CLI. Stub candidates only."""

import dataclasses
import json
from pathlib import Path

import pytest

from evaluation import v2_cli, v2_report as rep
from evaluation import v2_runner as r
from evaluation.scorecard import load_config
from evaluation.v2_data import load_v2_dataset
from v2_fixtures import StubAlwaysPage, StubDeclared, StubFailures, StubHardLabel, StubKeyword

ROOT = Path(__file__).resolve().parent.parent
PROV = {"model_id": "stub-keyword@test", "revision": "r0", "precision": "n/a", "prompt_template": "none", "seed": 1}


@pytest.fixture(scope="module")
def built(v2_master):
    ds = load_v2_dataset(v2_master)
    stub = r.CandidateSpec("keyword", "raw", StubKeyword(), PROV, {"offline_verified": True})
    raw = r.run_candidate(stub, ds, iterations=5, warmup=1, clock=lambda: 0)
    runs = [raw, r.fit_calibrated_arm(raw, ds),
            r.run_candidate(r.CandidateSpec("always", "raw", StubAlwaysPage()), ds),
            r.run_candidate(r.CandidateSpec("declared", "raw", StubDeclared()), ds),
            r.run_candidate(r.CandidateSpec("hard", "raw", StubHardLabel()), ds),
            r.run_candidate(r.CandidateSpec("mac_only", "raw", None, unavailable_reason="needs the Mac"), ds)]
    env = r.collect_environment()
    report = rep.build_report(ds, runs, load_config(), seed=11, environment=env, purpose="plumbing_check",
                              n_boot=200)
    return ds, runs, report, env


def test_top_of_report_labels_the_data_and_the_purpose(built):
    _, _, report, _ = built
    md = rep.render_markdown(report)
    assert report["dataset_label"] == "dataset: SYNTHETIC (generated), not real data"
    assert md.splitlines()[2] == "## **dataset: SYNTHETIC (generated), not real data**"
    assert "PLUMBING CHECK ON SYNTHETIC DATA" in md
    assert "A pass is not deployment approval" in md and "AGENTS.md rule 5" in md
    assert "Headline metrics use the test split only" in md


def test_provenance_fields_present_and_unrecorded_marked(built):
    ds, _, report, env = built
    d = report["dataset"]
    assert d["manifest_sha256"] == ds.manifest_sha256 and d["generator_version"] == "2.0.0"
    assert d["rubric_version"] == "2.4.0" and len(d["rubric_file_sha256_manifest"]) == 64
    assert d["rubric_file_sha256_manifest"] == d["rubric_file_sha256_now"]
    assert d["dataset_seed"] == 42 and d["real_data"] is False
    assert report["environment"] == env and report["environment"]["hardware"]
    assert report["run"]["seed"] == 11 and report["run"]["state_render_version"] == "v2-state-render-1"
    assert "perf_counter_ns" in report["run"]["timing_method"]
    cand = {c["key"]: c for c in report["candidates"]}
    assert cand["keyword/raw"]["provenance"]["model_id"] == "stub-keyword@test"
    assert cand["keyword/raw"]["provenance"]["revision"] == "r0"
    assert cand["always/raw"]["provenance"]["model_id"] == rep.NOT_RECORDED         # not invented
    assert cand["always/raw"]["provenance"]["precision"] == rep.NOT_RECORDED
    assert cand["keyword/calibrated"]["calibration_fit"]["fit_split"] == "val"
    assert report["task_mapping"]["page_now"]["adapter_kind"] == "noul"
    md = rep.render_markdown(report)
    for needle in (ds.manifest_sha256, "2.4.0", "stub-keyword@test", "not recorded", "Timing method",
                   "Harness seed: 11", env["hardware"]):
        assert needle in md


def test_loghub_citation_block_is_automatic(built):
    ds, runs, report, env = built
    assert report["citations"]["required"] is True and report["citations"]["reference"] == "https://github.com/logpai/loghub"
    md = rep.render_markdown(report)
    assert "## Loghub citation (D8)" in md and "https://github.com/logpai/loghub" in md
    assert "ISSRE, 2023" in md and "ISSTA, 2024" in md
    # a manifest with no Loghub seeds gets no block
    manifest = dict(ds.manifest, loghub_citation_required=False, seed_sources_used={"generator_authored": 560})
    clean = dataclasses.replace(ds, manifest=manifest)
    assert not clean.uses_loghub
    report2 = rep.build_report(clean, runs[:1], load_config(), 1, env, n_boot=20)
    assert report2["citations"] == {"required": False}
    assert "Loghub citation" not in rep.render_markdown(report2)


def test_citations_match_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for citation in rep.LOGHUB_CITATIONS:
        assert citation in readme
    assert rep.LOGHUB_URL in readme


def test_matrix_shape_and_na_handling(built):
    _, _, report, _ = built
    matrix = report["cohort_matrix"]
    assert set(matrix) == {"keyword/raw", "keyword/calibrated", "always/raw", "declared/raw", "hard/raw"}
    assert "mac_only/raw" not in matrix                      # unavailable rows have no cells, only a status
    assert set(matrix["keyword/raw"]) == {"A", "B", "B_prime", "C", "D", "pooled"}
    cell = matrix["keyword/raw"]["A"]["page_now_accuracy"]
    assert {"num", "den", "rate", "ci_low", "ci_high", "na_reason"} <= set(cell) and cell["den"] == 30
    declared = matrix["declared/raw"]["pooled"]
    assert declared["priority_accuracy"]["rate"] is None and "unsupported" in declared["priority_accuracy"]["na_reason"]
    assert declared["priority_mae_levels"]["mean"] is None
    assert matrix["keyword/raw"]["D"]["page_now_accuracy"]["rate"] is None
    assert matrix["keyword/raw"]["B"]["paired_inversion"]["den"] > 0
    md = rep.render_markdown(report)
    assert "| declared/raw |" in md and "N/A" in md
    assert next(c for c in report["candidates"] if c["key"] == "mac_only/raw")["status"] == "unavailable"


def test_calibration_and_latency_are_separate_pooled_tables(built):
    _, _, report, _ = built
    cal = report["calibration"]
    assert cal["keyword/raw"]["test"]["n"] > 0 and cal["keyword/raw"]["test"]["bins"]
    assert cal["keyword/calibrated"]["fit"]["temperature"] > 0
    assert cal["hard/raw"]["test"]["brier"] is None and "not 'model'" in cal["hard/raw"]["test"]["na_reason"]
    assert "cohort D excluded" in cal["keyword/raw"]["test"]["scope"]
    lat = report["latency"]["keyword/raw"]
    assert lat["n"] == 5 and lat["hardware"]
    assert report["latency"]["always/raw"]["p50_ms"] is None and "not measured" in report["latency"]["always/raw"]["na_reason"]
    md = rep.render_markdown(report)
    assert "## Calibration (separate table; pooled only)" in md and "## Latency (separate table)" in md
    assert "test bin counts" in md and "temperature" in md


def test_paired_differences_skip_arms_of_the_same_candidate(built):
    _, _, report, _ = built
    pairs = {(x["a"], x["b"]) for x in report["paired_differences"]}
    assert ("keyword/raw", "keyword/calibrated") not in pairs
    assert ("keyword/raw", "always/raw") in pairs
    row = next(x for x in report["paired_differences"]
               if (x["a"], x["b"], x["metric"]) == ("keyword/raw", "always/raw", "page_now_accuracy"))
    assert row["n"] > 0 and row["ci_low"] is not None and row["seed"] == 11 and row["n_boot"] == 200
    assert row["method"] == "cluster percentile bootstrap" and row["n_clusters"] > 1


def test_scorecard_section(built):
    _, _, report, _ = built
    sc = report["scorecard"]
    assert "PLACEHOLDER" in sc["cost_matrix_status"] and sc["config_version"] == "placeholder-1"
    by = {f"{x['candidate']}/{x['arm']}": x for x in sc["rows"]}
    assert all(x["verdict"] == "insufficient evidence" for x in by.values())
    assert by["mac_only/raw"]["reasons"][0].startswith("candidate unavailable")
    assert [g for g in by["keyword/raw"]["gates"] if g["name"] == "p95_ms_max"][0]["status"] == "not_evaluated"
    md = rep.render_markdown(report)
    assert md.count("A pass is not deployment approval") >= 2
    assert "**Cost matrix is a PLACEHOLDER (D13)" in md and "budget unset (Q4 is open)" in md


def test_consequential_errors_and_raw_outcomes_are_preserved(built):
    ds, _, report, _ = built
    assert report["consequential_errors"]["always/raw"]["missed_must_page"]["count"] == 0   # it pages everything
    assert len(report["raw_outcomes"]["keyword/raw"]["test"]) == 83 * 3
    assert len(report["raw_outcomes"]["keyword/raw"]["val"]) == 83 * 3
    assert "Consequential errors" in rep.render_markdown(report)


def test_json_is_strict_and_roundtrips(built, tmp_path):
    _, _, report, _ = built
    md, js = tmp_path / "sub" / "r.md", tmp_path / "other" / "r.json"
    rep.write_report(report, md, js)
    assert json.loads(js.read_text()) == report and md.read_text().startswith("# v2 decision-model evaluation report")
    bad = dict(report, oops=float("nan"))
    with pytest.raises(ValueError):
        rep.write_report(bad, md, js)


def test_chat_section_is_separate(built):
    ds, runs, _, env = built
    none = rep.render_markdown(rep.build_report(ds, runs[:1], load_config(), 1, env, n_boot=20))
    assert "no S9 chat results supplied" in none
    chat = {"dataset_kind": "synthetic", "rows": {"keyword/raw": {"must_page_recall": {"num": 1, "den": 2}}}}
    report = rep.build_report(ds, runs[:1], load_config(), 1, env, n_boot=20, chat=chat)
    assert report["chat_s9"]["dataset_kind"] == "synthetic" and "S9 chat module (reported separately" in rep.render_markdown(report)


def test_build_report_input_validation(built):
    ds, runs, _, env = built
    with pytest.raises(ValueError, match="purpose"):
        rep.build_report(ds, runs, load_config(), 1, env, purpose="vibes")
    with pytest.raises(ValueError, match="duplicate"):
        rep.build_report(ds, [runs[0], runs[0]], load_config(), 1, env)


def test_failure_stub_row_shows_unsupported_and_exceptions(v2_master):
    ds = load_v2_dataset(v2_master)
    run = r.run_candidate(r.CandidateSpec("fail", "raw", StubFailures()), ds)
    report = rep.build_report(ds, [run], load_config(), 1, r.collect_environment(), n_boot=20)
    pooled = report["cohort_matrix"]["fail/raw"]["pooled"]
    assert pooled["exception_rate"]["num"] > 0 and pooled["unsupported_rate"]["num"] > 0
    assert pooled["page_now_accuracy"]["rate"] is None and pooled["priority_accuracy"]["rate"] is None
    assert report["scorecard"]["rows"][0]["cost"]["na_reason"].startswith("task page_now is unsupported")


# ----------------------------------------------------------------------------- CLI
def test_cli_end_to_end_plumbing(v2_dir, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")             # registered so the CLI's forced "1" is undone after the test
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    out_md, out_json = tmp_path / "o.md", tmp_path / "o.json"
    code = v2_cli.main(["--data-dir", str(v2_dir), "--models", "lexical,laya", "--report", str(out_md),
                        "--raw", str(out_json), "--iterations", "3", "--warmup", "1", "--bootstrap", "50"])
    assert code == 0
    report = json.loads(out_json.read_text())
    assert report["purpose"] == "plumbing_check" and "SYNTHETIC" in report["dataset_label"]
    assert out_md.read_text().count("PLUMBING CHECK ON SYNTHETIC DATA") >= 1
    keys = {c["key"]: c["status"] for c in report["candidates"]}
    assert keys["lexical/raw"] != "unavailable" and keys["laya/raw"] == "unavailable"
    assert keys["lexical/calibrated"] == "unavailable"                      # hard labels cannot be calibrated
    # on this Linux host the Apple extra is absent: an honest unavailable row with the adapter's own reason
    assert "Apple extra" in next(c["note"] for c in report["candidates"] if c["key"] == "laya/raw")
    assert report["cohort_matrix"]["lexical/raw"]["pooled"]["coverage"]["den"] == 72 * 3
    assert report["latency"]["lexical/raw"]["n"] == 3
    assert "wrote" in capsys.readouterr().out


def test_cli_refuses_tampered_data_and_bad_arguments(v2_dir, tmp_path, capsys):
    with (v2_dir / "test.jsonl").open("a") as f:
        f.write("\n")
    assert v2_cli.main(["--data-dir", str(v2_dir), "--report", str(tmp_path / "a.md"),
                        "--raw", str(tmp_path / "a.json")]) == 2
    assert "refusing to run" in capsys.readouterr().err and not (tmp_path / "a.md").exists()
    with pytest.raises(SystemExit):
        v2_cli.main(["--models", "gpt"])
    with pytest.raises(SystemExit):
        v2_cli.main(["--models", ","])


def test_cli_refuses_a_bad_scorecard_config(v2_dir, tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("scorecard_version: x\n")
    assert v2_cli.main(["--data-dir", str(v2_dir), "--config", str(bad), "--report", str(tmp_path / "b.md"),
                        "--raw", str(tmp_path / "b.json")]) == 2
    assert "config keys" in capsys.readouterr().err


def test_cli_missing_lexical_dependency_is_reported_not_hidden(v2_dir, tmp_path, monkeypatch):
    import models.lexical_bm25 as lex

    def boom(self, examples):
        raise lex.ModelUnavailable("rank-bm25 missing (test)")

    monkeypatch.setattr(lex.LexicalBM25, "__init__", boom)
    specs = v2_cli.build_specs(["lexical"], v2_dir, True)
    assert specs[0].model is None and "rank-bm25 missing" in specs[0].unavailable_reason


def test_v1_adapter_specs_force_offline_and_report_load_failures(tmp_path, monkeypatch):
    import evaluation.benchmark_runner as br
    from models.base import ModelUnavailable
    cfg = tmp_path / "v1.yaml"
    cfg.write_text("laya_checkpoint: local/laya\nmps_checkpoint: local/mps.pt\ngenerative_checkpoint: local/gen\n")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    seen = {}

    def fake_load(name, config, train):
        seen[name] = (config, train)
        if name == "mps":
            raise ModelUnavailable("no trained checkpoint")
        if name == "generative":
            raise RuntimeError("OOM at load")
        return StubAlwaysPage()

    monkeypatch.setattr(br, "load_model", fake_load)
    ok = v2_cli._v1_spec("laya", cfg)
    assert ok.model is not None and ok.provenance["model_id"] == "local/laya"
    assert "WITHOUT retargeting" in ok.provenance["arm_description"] and ok.provenance["revision"].startswith("not recorded")
    import os
    assert os.environ["HF_HUB_OFFLINE"] == "1" and os.environ["TRANSFORMERS_OFFLINE"] == "1"   # downloads forbidden
    assert seen["laya"][1] == []                                                  # no train data given to non-lexical adapters
    gone = v2_cli._v1_spec("mps", cfg)
    assert gone.model is None and gone.unavailable_reason == "unavailable: no trained checkpoint"
    err = v2_cli._v1_spec("generative", cfg)
    assert err.model is None and err.unavailable_reason == "load error: RuntimeError: OOM at load"
    missing = v2_cli._v1_spec("laya", tmp_path / "nope.yaml")
    assert missing.model is None and missing.unavailable_reason.startswith("load error: FileNotFoundError")


def test_candidate_info_merges_real_provenance_and_rejects_typos(v2_dir, tmp_path, capsys):
    spec = r.CandidateSpec("lexical", "raw", StubKeyword(), {"model_id": "m"})
    v2_cli.apply_candidate_info([spec], {"lexical": {"provenance": {"revision": "abc123"},
                                                      "operational": {"peak_memory_gb": 12.5}}})
    assert spec.provenance == {"model_id": "m", "revision": "abc123"} and spec.operational == {"peak_memory_gb": 12.5}
    for bad, message in (({"nope": {}}, "not in --models"),
                         ({"lexical": {"operational": {"peak_mem": 1}}}, "unknown operational keys"),
                         ({"lexical": {"notes": {}}}, "may only hold")):
        with pytest.raises(ValueError, match=message):
            v2_cli.apply_candidate_info([spec], bad)
    info = tmp_path / "info.json"
    info.write_text(json.dumps({"lexical": {"provenance": {"revision": "rev-from-caller"},
                                             "operational": {"offline_verified": True}}}))
    code = v2_cli.main(["--data-dir", str(v2_dir), "--candidate-info", str(info), "--bootstrap", "20",
                        "--report", str(tmp_path / "i.md"), "--raw", str(tmp_path / "i.json")])
    report = json.loads((tmp_path / "i.json").read_text())
    lex = next(c for c in report["candidates"] if c["key"] == "lexical/raw")
    assert code == 0 and lex["provenance"]["revision"] == "rev-from-caller"
    assert lex["operational_inputs"]["offline_verified"] is True
    info.write_text(json.dumps({"ghost": {}}))
    assert v2_cli.main(["--data-dir", str(v2_dir), "--candidate-info", str(info),
                        "--report", str(tmp_path / "j.md"), "--raw", str(tmp_path / "j.json")]) == 2
    assert "refusing to run" in capsys.readouterr().err
    assert v2_cli.main(["--data-dir", str(v2_dir), "--candidate-info", str(tmp_path / "missing.json"),
                        "--report", str(tmp_path / "k.md"), "--raw", str(tmp_path / "k.json")]) == 2


def test_cli_hide_signal_and_chat_results(v2_dir, tmp_path):
    chat = tmp_path / "chat.json"
    chat.write_text(json.dumps({"dataset_kind": "synthetic", "rows": {}}))
    code = v2_cli.main(["--data-dir", str(v2_dir), "--hide-event-signal", "--chat-results", str(chat),
                        "--report", str(tmp_path / "c.md"), "--raw", str(tmp_path / "c.json"), "--bootstrap", "20"])
    report = json.loads((tmp_path / "c.json").read_text())
    assert code == 0 and report["run"]["include_event_signal"] is False and report["chat_s9"]["dataset_kind"] == "synthetic"


def test_extra_provenance_and_first_errors_are_rendered(v2_master):
    ds = load_v2_dataset(v2_master)
    spec = r.CandidateSpec("fail", "raw", StubFailures(), {"model_id": "m", "quantization": "q4_k_m"})
    report = rep.build_report(ds, [r.run_candidate(spec, ds)], load_config(), 1, r.collect_environment(), n_boot=20)
    md = rep.render_markdown(report)
    assert report["candidates"][0]["provenance_extra"] == {"quantization": "q4_k_m"}
    assert "extra provenance" in md and "q4_k_m" in md and "first errors" in md and "stub backend failure" in md


def test_serializer_handles_dataclasses_and_tuple_keys():
    out = rep._ser({("a", "b"): [r.Outcome("c", "page_now", "ok", True)], "t": (1, 2)})
    assert out["a/b"][0]["status"] == "ok" and out["t"] == [1, 2]
