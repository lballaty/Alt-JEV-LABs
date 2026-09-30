"""WS1 seed-registry tests: no network, small in-repo fixtures only.

These cover the four guarantees WS1 must hold (``docs/DATASET_PLAN_V2.md``):

* the synthetic entity filler is deterministic,
* the filler never emits an IP outside the RFC 5737 documentation ranges,
* the registry records carry a complete, well-typed provenance schema, and
* extraction reads templates only — no raw log line can leak into the registry.

Extraction is exercised against tiny fixtures built in ``tmp_path`` (including
decoy raw-log files that must never be read), so nothing here touches the
network or the real upstream repos.
"""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path

import pytest

import data.seed_registry as seed_registry
from data.entity_filler import (
    RFC5737_BLOCKS,
    classify_placeholders,
    fill_template,
)

# Dotted-quad matcher used by the leak checks. Word boundaries stop it matching
# inside a longer digit run, and we further require every octet be 0-255 before
# treating a match as a real IPv4 address.
_IPV4_RE = re.compile(r"(?<!\d)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\d)")

# A representative spread of real Loghub templates (verbatim) so the filler is
# tested against the syntax it will actually see, without cloning anything.
_SAMPLE_TEMPLATES: dict[str, str] = {
    "OpenSSH-E9": "Failed password for <*> from <*> port <*> ssh2",
    "OpenSSH-E20": "pam_unix(sshd:auth): authentication failure; logname= uid=<*> euid=<*> tty=ssh ruser= rhost=<*> user=<*>",
    "HDFS-E12": "Received block blk_<*> src: /<*>:<*> dest: /<*>:<*> of size <*>",
    "HDFS-E1": "<*>:<*> Served block blk_<*> to /<*>",
    "Linux-E68": "Linux version <*>.<*>.<*><*>.<*> (bhcompile@bugs) #<*>",
    "OpenStack-E10": "[instance: <*>] memory limit: <*>.<*> MB, free: <*>.<*> MB",
    "BGL-E1": "<*> ddr error(s) detected and corrected on rank <*>, symbol <*> over <*> seconds",
}


def _all_ipv4(text: str) -> list[str]:
    """Return every substring of ``text`` that reads as a real IPv4 dotted quad."""

    found: list[str] = []
    for match in _IPV4_RE.finditer(text):
        if all(0 <= int(octet) <= 255 for octet in match.groups()):
            found.append(match.group())
    return found


def test_filler_is_deterministic():
    """Same (template, template_id, seed) must always yield the same fill."""

    for template_id, template in _SAMPLE_TEMPLATES.items():
        first = fill_template(template, template_id, 42)
        second = fill_template(template, template_id, 42)
        assert first == second
        # A different seed should generally change the output; a different
        # template id must too (fills are keyed on both).
        assert fill_template(template, template_id, 43).text != first.text or "<*>" not in template
        # The reported kinds match the standalone classifier exactly.
        assert first.kinds == classify_placeholders(template)


def test_filler_emits_only_rfc5737_ips():
    """No fill of any sample template, over many seeds, may contain a routable IP.

    Every dotted quad the filler produces must fall inside an RFC 5737 block —
    both the IP-classified placeholders and any coincidental quad from a version
    or decimal run (which the filler guards against forming a valid octet range).
    """

    allowed_networks = [ipaddress.ip_network(f"{block}.0/24") for block in RFC5737_BLOCKS]
    for template_id, template in _SAMPLE_TEMPLATES.items():
        for seed in range(100):
            text = fill_template(template, template_id, seed).text
            for quad in _all_ipv4(text):
                address = ipaddress.ip_address(quad)
                assert any(address in net for net in allowed_networks), (
                    f"{template_id} seed {seed} emitted non-RFC5737 IP {quad} in: {text}"
                )


def test_filler_infers_expected_kinds():
    """Spot-check that the context heuristics classify the obvious fields."""

    assert classify_placeholders("Failed password for <*> from <*> port <*> ssh2") == (
        "username",
        "ip",
        "port",
    )
    assert classify_placeholders("Received block blk_<*> src: /<*>:<*> of size <*>") == (
        "block_id",
        "ip",
        "port",
        "number",
    )
    assert classify_placeholders("uid=<*> euid=<*>") == ("uid", "uid")
    # A dotted numeric run is a version, regardless of how many components.
    assert set(classify_placeholders("agpgart interface v<*>.<*>")) == {"version"}


def _write_loghub_fixture(root: Path) -> None:
    """Build a one-system Loghub-like tree with a decoy raw log beside it.

    The raw ``*.log`` and ``*_structured.csv`` files contain a sentinel real IP
    and username that must never enter the registry: extraction must read only
    the ``*_templates.csv`` file.
    """

    system_dir = root / "OpenSSH"
    system_dir.mkdir(parents=True)
    (system_dir / "OpenSSH_2k.log_templates.csv").write_text(
        "EventId,EventTemplate\n"
        "E1,Accepted password for <*> from <*> port <*> ssh2\n"
        'E2,"Connection closed by <*> [preauth]"\n',
        encoding="utf-8",
    )
    # Decoy raw files with identifiable content that MUST NOT be read/copied.
    (system_dir / "OpenSSH_2k.log").write_text(
        "Dec 10 06:55:46 host sshd[24200]: Accepted password for realuser from 8.8.8.8 port 22 ssh2\n",
        encoding="utf-8",
    )
    (system_dir / "OpenSSH_2k.log_structured.csv").write_text(
        "LineId,Content\n1,Accepted password for realuser from 8.8.8.8 port 22 ssh2\n",
        encoding="utf-8",
    )


# Sentinels that appear only in the decoy raw files, never in templates.
_RAW_SENTINELS = ("realuser", "8.8.8.8")


def test_extract_loghub_reads_templates_only_and_no_raw_leak(tmp_path, monkeypatch):
    """Loghub extraction must use only the templates CSV and leak no raw content."""

    _write_loghub_fixture(tmp_path)
    # Restrict the system map to the single fixture system so extraction does not
    # demand the other four files.
    monkeypatch.setattr(
        seed_registry,
        "LOGHUB_SYSTEMS",
        {"OpenSSH": "OpenSSH/OpenSSH_2k.log_templates.csv"},
    )

    records = seed_registry.extract_loghub(tmp_path, "deadbeef")

    assert len(records) == 2
    blob = json.dumps([record.__dict__ for record in records])
    for sentinel in _RAW_SENTINELS:
        assert sentinel not in blob, f"raw sentinel {sentinel!r} leaked into registry"
    for record in records:
        # Templates keep placeholders; the extracted text is a template, not a
        # concrete log line.
        assert "<*>" in record.template
        assert record.source == "loghub"
        assert record.upstream_commit == "deadbeef"
        assert record.source_file == "OpenSSH/OpenSSH_2k.log_templates.csv"
        assert len(record.source_file_sha256) == 64


def test_registry_schema_is_complete_and_typed(tmp_path, monkeypatch):
    """Every emitted record must carry the mandatory provenance fields."""

    _write_loghub_fixture(tmp_path)
    monkeypatch.setattr(
        seed_registry,
        "LOGHUB_SYSTEMS",
        {"OpenSSH": "OpenSSH/OpenSSH_2k.log_templates.csv"},
    )
    records = seed_registry.extract_loghub(tmp_path, "deadbeef")
    required = {
        "source": str,
        "system": str,
        "template_id": str,
        "template": str,
        "upstream_commit": str,
        "source_file": str,
        "source_file_sha256": str,
        "license": str,
        "num_placeholders": int,
        "placeholder_kinds": list,
    }
    for record in records:
        data = record.__dict__
        for key, expected_type in required.items():
            assert key in data, f"missing field {key}"
            assert isinstance(data[key], expected_type), f"{key} has wrong type"
        assert data["num_placeholders"] == len(data["placeholder_kinds"])
        assert "loghub" in data["license"]


def _write_art_fixture(root: Path) -> None:
    """Build a minimal Atomic Red Team atomics tree for one technique."""

    tech_dir = root / "atomics" / "T9999"
    tech_dir.mkdir(parents=True)
    (tech_dir / "T9999.yaml").write_text(
        "attack_technique: T9999\n"
        "atomic_tests:\n"
        "  - name: Example discovery command\n"
        "    auto_generated_guid: 11111111-2222-3333-4444-555555555555\n"
        "    supported_platforms: [linux]\n"
        "    input_arguments:\n"
        "      output_file:\n"
        "        default: /tmp/out.txt\n"
        "    executor:\n"
        "      name: sh\n"
        "      command: 'cat /etc/passwd > #{output_file}'\n",
        encoding="utf-8",
    )


def test_extract_art_records_command_technique_and_guid(tmp_path, monkeypatch):
    """Atomic Red Team extraction records the command, technique and GUID."""

    _write_art_fixture(tmp_path)
    guid = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setattr(seed_registry, "ART_SELECTED_TESTS", (("T9999", guid),))

    records = seed_registry.extract_art(tmp_path, "cafef00d")

    assert len(records) == 1
    record = records[0]
    assert record.source == "atomic-red-team"
    assert record.attack_technique == "T9999"
    assert record.attack_guid == guid
    assert record.template == "cat /etc/passwd > #{output_file}"
    assert record.executor == "sh"
    assert record.input_arguments == {"output_file": "/tmp/out.txt"}
    assert "MIT" in record.license
    assert record.upstream_commit == "cafef00d"


def test_extract_art_missing_guid_fails_loudly(tmp_path, monkeypatch):
    """A pinned GUID that is absent from the file must raise, never be skipped."""

    _write_art_fixture(tmp_path)
    monkeypatch.setattr(
        seed_registry,
        "ART_SELECTED_TESTS",
        (("T9999", "00000000-0000-0000-0000-000000000000"),),
    )
    with pytest.raises(KeyError):
        seed_registry.extract_art(tmp_path, "cafef00d")


def test_committed_registry_contains_templates_only():
    """Guard the committed artifact: templates only, no routable IPs, schema intact."""

    registry_path = Path(__file__).resolve().parent.parent / "data" / "seeds" / "registry.jsonl"
    if not registry_path.is_file():
        pytest.skip("registry.jsonl has not been generated in this checkout")

    records = [json.loads(line) for line in registry_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert records, "committed registry is empty"
    for record in records:
        # No committed template may contain a routable-looking IPv4 address.
        assert not _all_ipv4(record["template"]), (
            f"{record['template_id']} contains a dotted-quad IP: {record['template']}"
        )
        # Mandatory provenance fields are present on every committed record.
        for key in ("source", "system", "template_id", "template", "upstream_commit", "source_file_sha256", "license"):
            assert record.get(key), f"{record.get('template_id')} missing {key}"
    # Loghub is present and predominantly parameterised: most templates keep a
    # `<*>` placeholder (some events are genuinely constant strings, so we do not
    # require every one to have a placeholder — the leak guard is the IP check
    # above plus test_extract_loghub_reads_templates_only_and_no_raw_leak).
    loghub = [r for r in records if r["source"] == "loghub"]
    assert loghub
    assert sum("<*>" in r["template"] for r in loghub) > len(loghub) // 2
