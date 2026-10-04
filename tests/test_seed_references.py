"""Tests for reference-only seed sources (data/seed_references.py, D27).

No network. Every fixture below is a tiny file INVENTED for these tests; no
real vendor line appears here (the whole point of D27 is that upstream text
stays out of the repository). IP addresses in fixtures use values that would be
routable on the real internet on purpose, so the tests prove they are removed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from data import seed_references as sr
from data.seed_registry import SeedRecord

REFS_PATH = Path(__file__).resolve().parents[1] / "data" / "seeds" / "references.json"
COMMITTED_REGISTRY = Path(__file__).resolve().parents[1] / "data" / "seeds" / "registry.jsonl"

# --- invented fixtures, one per extractor format ---------------------------
SYSLOG_FIXTURE = (
    "Mar  3 04:05:06 gw1 sshd[321]: Failed password for invalid user zed from 8.8.4.4 port 2222 ssh2\n"
    "Mar  3 04:05:07 gw1 sshd[322]: Failed password for invalid user amy from 1.1.1.1 port 3333 ssh2\n"
    "Mar  3 04:05:08 gw1 kernel: [ 55.123456] link eth0 up, mac 00:11:22:33:44:55 peer host9.corp.example\n"
    "<34>1 2030-01-02T03:04:05Z gw1 appd 77 ID9 [meta k=\"v1\"] queue depth exceeded for tenant acme\n"
    "this line has no recognisable header\n"
    "\n"
)
RUBY_FIXTURE = (
    "describe 'x' do\n"
    "  # \"Mar  3 04:05:06 gw1 sshd[1]: commented out 9.9.9.9 should not be read\"\n"
    "  it 'a' do\n"
    "    m = grok \"Mar  3 04:05:06 gw1 cron[9]: session opened for user bob by (uid=0)\"\n"
    "    expect(m).to include('timestamp' => 'Mar  3 04:05:06')\n"
    "    k = grok '%FAKE-4-100200: Denied TCP from outside:7.7.7.7/1234 to inside:6.6.6.6/80'\n"
    "    j = grok \"Mar  3 04:05:06 gw1 #{tag}: interpolated\"\n"
    "  end\n"
    "end\n"
)
RUST_FIXTURE = (
    "fn t() {\n"
    "    let a = r#\"<13>Mar  3 04:05:06 gw1 prog[12]: user carol logged in from 5.5.5.5 {msg}\"#;\n"
    "    let b = r#\"<13>1 2030-01-02T03:04:05+00:00 gw1 prog 12 - {}{} {msg}\"#;\n"
    "    let c = \"just a string that is not a log line\";\n"
    "}\n"
)


def _templates(extraction: sr.Extraction) -> list[str]:
    return [t for _, _, t in extraction.templates]


# --- extractors -------------------------------------------------------------
def test_syslog_extractor_handles_rfc3164_and_5424_and_counts_skips():
    result = sr.extract_syslog_lines(SYSLOG_FIXTURE)
    templates = _templates(result)
    assert "Failed password for invalid user <*> from <*> port <*> ssh2" in templates
    # Two lines differing only in values collapse to one template.
    assert sum("Failed password" in t for t in templates) == 1 and result.duplicates == 1
    assert any(t == "[ <*>] link eth0 up, mac <*> peer <*>" for t in templates)
    assert any(t.startswith('[meta k="<*>"] queue depth exceeded for tenant') for t in templates)
    assert result.skipped_unparsed == 1  # the headerless line is counted, not silently dropped


def test_ruby_extractor_reads_literals_not_comments_or_interpolations():
    result = sr.extract_ruby_spec_literals(RUBY_FIXTURE)
    templates = _templates(result)
    assert "session opened for user <*> by (uid=<*>)" in templates
    assert any(t.startswith("%FAKE-4-100200: Denied TCP from outside:<*>:<*>") or "outside:<*>/<*>" in t
               for t in templates)
    assert all("9.9.9.9" not in t for t in templates)           # commented-out line ignored
    assert all("interpolated" not in t for t in templates)      # "#{}" literal skipped
    assert result.skipped_unparsed == 1
    # Vendor id fields are kept verbatim (they carry the message's meaning).
    assert any("%FAKE-4-100200" in t for t in templates)
    assert {s for s, _, _ in result.templates} == {"syslog", "cisco-fake"}


def test_rust_extractor_turns_format_holes_into_placeholders_and_drops_degenerate():
    result = sr.extract_rust_string_literals(RUST_FIXTURE)
    templates = _templates(result)
    assert templates == ["user <*> logged in from <*> <*>"]
    assert result.skipped_degenerate == 1      # the line that is only holes
    assert result.seen == 2                    # the plain sentence was never a candidate


def test_user_home_directory_and_failed_for_contexts():
    assert sr.normalize_body("cmd in /home/dave/work failed for erin on tty1") == \
        "cmd in /home/<*>/work failed for <*> on tty1"


# --- no-IP guarantee -----------------------------------------------------------
@pytest.mark.parametrize("fixture,extractor", [
    (SYSLOG_FIXTURE, sr.extract_syslog_lines), (RUBY_FIXTURE, sr.extract_ruby_spec_literals),
    (RUST_FIXTURE, sr.extract_rust_string_literals)])
def test_extractor_output_has_no_ips(fixture, extractor):
    for template in _templates(extractor(fixture)):
        sr.assert_no_ip(template)  # raises on any dotted quad or IPv6-looking address
        assert not re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", template)


def test_assert_no_ip_rejects_ipv4_private_and_ipv6():
    for bad in ("peer 10.0.0.1 up", "peer 203.0.113.9 up", "peer 2001:db8::1 up", "peer fe80:0:0:0:1:2:3:4 up"):
        with pytest.raises(sr.ReferenceError_):
            sr.assert_no_ip(bad)
    sr.assert_no_ip("version <*> at 12:30 port <*>")  # shapes that merely look numeric are fine


def test_ipv6_and_mac_and_url_are_scrubbed_by_normalize():
    out = sr.normalize_body("peer 2001:4860:4860::8888 mac aa:bb:cc:dd:ee:ff url https://x.example.org/p?q=1 mail a@b.io")
    assert out == "peer <*> mac <*> url <*> mail <*>"


# --- determinism and schema ------------------------------------------------------
def _make_source(tmp_path: Path, license_bytes: bytes = b"license text") -> tuple[sr.RefSource, Path]:
    workdir = tmp_path / "work"
    root = workdir / "demo"
    (root / "t").mkdir(parents=True)
    (root / "LICENSE").write_bytes(license_bytes)
    files = {"t/a.log": SYSLOG_FIXTURE, "t/b.rb": RUBY_FIXTURE, "t/c.rs": RUST_FIXTURE}
    for rel, body in files.items():
        (root / rel).write_text(body, encoding="utf-8")
    ext = {"t/a.log": "syslog_lines", "t/b.rb": "ruby_spec_literals", "t/c.rs": "rust_string_literals"}
    ref_files = tuple(sr.RefFile(rel, hashlib.sha256((root / rel).read_bytes()).hexdigest(), "x", ext[rel], "syslog")
                      for rel in files)
    source = sr.RefSource("demo", "Demo", "https://example.invalid/demo.git", "a" * 40, "Apache-2.0", "", "LICENSE",
                          hashlib.sha256(license_bytes).hexdigest(), ref_files)
    return source, workdir


def test_build_is_deterministic_and_schema_matches_registry(tmp_path):
    source, workdir = _make_source(tmp_path)
    records_1, counts_1 = sr.build_records([source], workdir)
    records_2, _ = sr.build_records([source], workdir)
    assert records_1 == records_2
    out_a, out_b = tmp_path / "a" / "r.jsonl", tmp_path / "b" / "r.jsonl"
    sr.write_registry(records_1, counts_1, out_a)
    sr.write_registry(records_2, counts_1, out_b)
    assert out_a.read_bytes() == out_b.read_bytes()

    registry_fields = list(SeedRecord.__dataclass_fields__)
    committed_first = json.loads(COMMITTED_REGISTRY.read_text().splitlines()[0])
    assert list(committed_first) == registry_fields  # sanity: the committed schema is the dataclass schema
    for record in records_1:
        assert list(record) == registry_fields + ["redistribution"]
        assert record["redistribution"] == "local-only"
        assert record["upstream_commit"] == "a" * 40 and len(record["source_file_sha256"]) == 64
        assert record["num_placeholders"] == record["template"].count("<*>") == len(record["placeholder_kinds"])
    manifest = json.loads(out_a.with_suffix(".manifest.json").read_text())
    assert manifest["contains_local_only_seed_text"] is True and manifest["redistribution"] == "local-only"
    assert manifest["record_count"] == len(records_1)
    ids = [r["template_id"] for r in records_1]
    assert len(ids) == len(set(ids))


def test_build_fails_loudly_when_an_extractor_yields_nothing(tmp_path):
    source, workdir = _make_source(tmp_path)
    (workdir / "demo" / "t/a.log").write_text("no log lines here\n", encoding="utf-8")
    with pytest.raises(sr.ReferenceError_, match="produced no templates"):
        sr.build_records([source], workdir)


def test_build_refuses_a_template_that_still_contains_an_ip(tmp_path, monkeypatch):
    source, workdir = _make_source(tmp_path)
    # Simulate an extractor regression that lets an address through.
    leaky = lambda text: sr.Extraction(templates=[("syslog", "x", "peer 8.8.8.8 is up now")], seen=1)  # noqa: E731
    monkeypatch.setitem(sr.EXTRACTORS, "syslog_lines", leaky)
    with pytest.raises(sr.ReferenceError_, match="dotted-quad"):
        sr.build_records([source], workdir)


# --- sha256 verification ----------------------------------------------------------------
def test_verify_passes_then_fails_on_tamper_missing_and_license_change(tmp_path):
    source, workdir = _make_source(tmp_path)
    assert sr.verify_source(source, workdir) == []
    target = workdir / "demo" / "t/a.log"
    target.write_text(SYSLOG_FIXTURE + "extra line\n", encoding="utf-8")
    problems = sr.verify_source(source, workdir)
    assert len(problems) == 1 and "sha256 mismatch for t/a.log" in problems[0]
    target.unlink()
    assert any("missing t/a.log" in p for p in sr.verify_source(source, workdir))
    (workdir / "demo" / "LICENSE").write_bytes(b"changed")
    assert any("sha256 mismatch for LICENSE" in p for p in sr.verify_source(source, workdir))


def _write_refs(tmp_path: Path, source: sr.RefSource) -> Path:
    doc = {"sources": [{
        "id": source.id, "name": source.name, "status": "reference-only", "repo_url": source.repo_url,
        "commit": source.commit, "license": {"spdx": source.license_spdx},
        "license_file": {"path": source.license_path, "sha256": source.license_sha256},
        "files": [{"path": f.path, "sha256": f.sha256, "format": f.format, "extractor": f.extractor,
                   "system": f.system} for f in source.files]}]}
    path = tmp_path / "refs.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_cli_verify_and_build_exit_codes_without_network(tmp_path, capsys):
    source, workdir = _make_source(tmp_path)
    refs = _write_refs(tmp_path, source)
    out = tmp_path / "out" / "registry.jsonl"
    assert sr.main(["verify", "--refs", str(refs), "--workdir", str(workdir)]) == 0
    assert sr.main(["build", "--refs", str(refs), "--workdir", str(workdir), "--out", str(out)]) == 0
    assert out.is_file() and out.with_suffix(".manifest.json").is_file()
    (workdir / "demo" / "t/c.rs").write_text("tampered", encoding="utf-8")
    out.unlink()
    assert sr.main(["build", "--refs", str(refs), "--workdir", str(workdir), "--out", str(out)]) == 1
    assert not out.exists()  # build refuses to run on unverified input
    assert "sha256 mismatch" in capsys.readouterr().err


def test_fetch_refuses_an_existing_checkout_at_another_commit(tmp_path, monkeypatch):
    source, workdir = _make_source(tmp_path)
    monkeypatch.setattr(sr, "_git", lambda dest, *args: "b" * 40)  # no git, no network
    with pytest.raises(sr.ReferenceError_, match="expected " + "a" * 40):
        sr.fetch_source(source, workdir)


def test_require_git_ignored_blocks_tracked_paths():
    repo = Path(__file__).resolve().parents[1]
    sr._require_git_ignored(repo / "data" / "seeds_local" / "anything.jsonl")  # ignored by .gitignore
    with pytest.raises(sr.ReferenceError_, match="not git-ignored"):
        sr._require_git_ignored(repo / "data" / "seeds" / "would_be_tracked.jsonl")


# --- references.json itself ---------------------------------------------------------------
def test_references_json_parses_with_pinned_commits_and_no_content():
    doc = json.loads(REFS_PATH.read_text(encoding="utf-8"))
    sources, excluded = sr.load_references(REFS_PATH)  # strict validation
    assert {s.id for s in sources} == {"logstash-patterns-core", "vector", "wazuh"}
    for s in sources:
        assert re.fullmatch(r"[0-9a-f]{40}", s.commit)
        assert s.license_spdx and re.fullmatch(r"[0-9a-f]{64}", s.license_sha256)
        for f in s.files:
            assert re.fullmatch(r"[0-9a-f]{64}", f.sha256) and f.extractor in sr.EXTRACTORS
    forbidden_keys = {"content", "sample", "samples", "lines", "text", "example", "examples", "excerpt", "body"}

    def walk(node):
        if isinstance(node, dict):
            assert not (forbidden_keys & set(node)), f"content-like key in {sorted(node)}"
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            assert len(node) < 400, "long string: references.json must not carry upstream text"
    walk(doc)
    # Only the declared keys may appear on a file entry.
    for src in doc["sources"]:
        for f in src.get("files", []):
            assert set(f) <= sr._ALLOWED_FILE_KEYS


def test_unverified_sources_are_excluded_without_fetch_instructions():
    doc = json.loads(REFS_PATH.read_text(encoding="utf-8"))
    excluded = {e["id"]: e for e in doc["sources"] if e["status"] == "unverified, excluded"}
    assert set(excluded) == {"secrepo", "openenv-sre-triage", "mitre-attack", "zenodo-loghub-full"}
    for entry in excluded.values():
        assert not ({"repo_url", "commit", "files", "url", "license_file"} & set(entry))


@pytest.mark.parametrize("mutate,message", [
    (lambda e: e.update(commit="9aee1f5"), "40-character"),
    (lambda e: e["files"][0].update(content="x"), "disallowed keys"),
    (lambda e: e["files"][0].update(extractor="nope"), "unknown extractor"),
    (lambda e: e["files"][0].update(path="../escape"), "unsafe path"),
])
def test_load_references_rejects_weak_or_unsafe_entries(tmp_path, mutate, message):
    doc = json.loads(REFS_PATH.read_text(encoding="utf-8"))
    mutate(doc["sources"][0])
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(sr.ReferenceError_, match=message):
        sr.load_references(bad)


def test_excluded_entry_with_fetch_fields_is_rejected(tmp_path):
    doc = {"sources": [{"id": "x", "name": "x", "status": "unverified, excluded", "repo_url": "https://e/x"}]}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(sr.ReferenceError_, match="must not carry fetch fields"):
        sr.load_references(bad)


# --- cohort generator compatibility (no generator edit needed) -----------------------------
def test_generator_catalog_accepts_committed_plus_local_registry(tmp_path):
    from data import generator_v2

    source, workdir = _make_source(tmp_path)
    records, _ = sr.build_records([source], workdir)
    merged = tmp_path / "merged.jsonl"
    lines = COMMITTED_REGISTRY.read_text(encoding="utf-8").splitlines() + [json.dumps(r) for r in records]
    merged.write_text("\n".join(lines) + "\n", encoding="utf-8")
    catalog = generator_v2.load_seed_catalog(merged)
    assert all(r["template_id"] in catalog for r in records)
    assert catalog[records[0]["template_id"]]["redistribution"] == "local-only"
