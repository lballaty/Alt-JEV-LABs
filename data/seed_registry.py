"""Build a provenance-tracked seed registry from pinned upstream sources.

WS1 of ``docs/DATASET_PLAN_V2.md``. This module produces
``data/seeds/registry.jsonl`` — one JSON record per seed template — from two
upstream projects pinned at exact commits:

* **Loghub** (``logpai/loghub``): we copy ONLY the ``*_templates.csv`` files,
  which contain de-identified event *templates* with ``<*>`` placeholders. We
  never read or copy the raw ``*.log`` or ``*_structured.csv`` files, because
  those carry real IP addresses and usernames (AGENTS.md rule 4). Loghub is
  research/academic-use only and must be cited.

* **Atomic Red Team** (``redcanaryco/atomic-red-team``, MIT): we copy a small,
  explicitly enumerated set of Linux test *command lines* mapped to ATT&CK
  technique IDs. These are public test definitions, not captured telemetry.

Every record records its upstream commit, the sha256 of the source file it came
from, and a license string, so the fixture's provenance is fully reconstructable
(AGENTS.md rule 7). Network fetches fail loudly with a clear error — there is no
silent fallback to stale or partial data (AGENTS.md rule 2).

CLI::

    python -m data.seed_registry --out data/seeds --loghub-rev <commit>

``--loghub-path`` / ``--art-path`` reuse an existing local checkout instead of
cloning (used to rebuild the committed artifact offline and in tests). The
extraction functions themselves never touch the network, so they are unit
tested against tiny fixtures with no clone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - dependency is declared in pyproject
    raise ModuleNotFoundError(
        "PyYAML is required to parse Atomic Red Team definitions. Install the "
        "project dependencies (e.g. `uv sync`) before building the registry."
    ) from exc

from data.entity_filler import classify_placeholders

logger = logging.getLogger("seed_registry")

# --- Pinned upstream identity -------------------------------------------------

LOGHUB_URL = "https://github.com/logpai/loghub.git"
# Default Loghub commit verified on this host (2026-09-30). Overridable via
# --loghub-rev so a reviewer can pin a different, independently verified commit.
LOGHUB_DEFAULT_REV = "dd61d0952749ee7963bde24220d1be5ede023033"
LOGHUB_LICENSE = "Loghub: research/academic use; cite https://github.com/logpai/loghub"

ART_URL = "https://github.com/redcanaryco/atomic-red-team.git"
# Default Atomic Red Team commit verified on this host (2026-09-30).
ART_DEFAULT_REV = "388942adbd9641f4dfdcf079d7efe9a75ec0ac43"
ART_LICENSE = "Atomic Red Team: MIT; https://github.com/redcanaryco/atomic-red-team"

# The five Loghub systems WS1 covers. Values are the per-system template file,
# relative to the Loghub repo root. We use the 2k sampled template sets, which
# are the parsed template catalogues shipped in-repo.
LOGHUB_SYSTEMS: dict[str, str] = {
    "OpenSSH": "OpenSSH/OpenSSH_2k.log_templates.csv",
    "OpenStack": "OpenStack/OpenStack_2k.log_templates.csv",
    "BGL": "BGL/BGL_2k.log_templates.csv",
    "HDFS": "HDFS/HDFS_2k.log_templates.csv",
    "Linux": "Linux/Linux_2k.log_templates.csv",
}

# Explicitly enumerated Atomic Red Team seeds: (technique, auto_generated_guid).
# Pinning the exact test GUID (not just the technique) keeps the seed stable
# across upstream reorderings and edits within a technique file. The selection
# is a small, benign set of Linux discovery/persistence command lines; each is
# recorded with its ATT&CK technique ID. Add to this list to grow coverage.
ART_SELECTED_TESTS: tuple[tuple[str, str], ...] = (
    ("T1087.001", "f8aab3dd-5990-4bf8-b8ab-2226c951696f"),  # Enumerate local accounts
    ("T1087.001", "e6f36545-dc1e-47f0-9f48-7f730f54a02e"),  # Enumerate users and groups
    ("T1082", "486e88ea-4f56-470f-9b57-3f4d73f39133"),      # Hostname discovery
    ("T1082", "fcbdd43f-f4ad-42d5-98f3-0218097e2720"),      # Environment variable discovery
    ("T1070.003", "b1251c35-dcd3-4ea1-86da-36d27b54f31f"),  # Clear bash history (cat /dev/null)
    ("T1136.001", "40d8eabd-e394-46f6-8785-b9bfa1d011d2"),  # Create a Linux user account
    ("T1222.002", "34ca1464-de9d-40c6-8c77-690adf36a135"),  # chmod (numeric mode)
    ("T1053.003", "078e69eb-d9fb-450e-b9d0-2e118217c846"),  # Add script to /etc/cron.d
)


@dataclass
class SeedRecord:
    """One registry row. Provenance fields are mandatory; the rest are metadata.

    The field order here is the JSON key order in the emitted file. Optional
    fields default to empty and are only populated for the source that has them
    (e.g. ATT&CK fields for Atomic Red Team rows), so every record is a complete,
    self-describing object regardless of source.
    """

    source: str
    system: str
    template_id: str
    template: str
    upstream_commit: str
    source_file: str
    source_file_sha256: str
    license: str
    # Loghub metadata: which placeholder kinds the filler will infer. Recorded
    # here so the assumptions are auditable without re-running the filler.
    num_placeholders: int = 0
    placeholder_kinds: list[str] = field(default_factory=list)
    # Atomic Red Team metadata.
    attack_technique: str = ""
    attack_test_name: str = ""
    attack_guid: str = ""
    executor: str = ""
    input_arguments: dict = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    """Return the hex sha256 of a file's bytes, read in chunks."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clone_at_commit(url: str, rev: str, dest: Path) -> None:
    """Shallow-clone ``url`` at exactly ``rev`` into ``dest``.

    We init an empty repo and fetch only the single requested commit (depth 1),
    which avoids downloading history and pins the content exactly. Any failure
    raises ``RuntimeError`` with the underlying git output — there is no silent
    fallback to a different revision or a partial checkout (AGENTS.md rule 2).
    """

    dest.mkdir(parents=True, exist_ok=True)

    def run(*args: str) -> None:
        result = subprocess.run(
            ["git", "-C", str(dest), *args],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed for {url}@{rev} "
                f"(exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
            )

    run("init", "-q")
    # Fetch the exact commit by SHA. GitHub serves reachable SHAs on fetch; if a
    # host refuses this, the error is surfaced rather than masked.
    run("remote", "add", "origin", url)
    try:
        run("fetch", "-q", "--depth", "1", "origin", rev)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Could not fetch commit {rev} from {url}. The commit must exist and "
            f"the host must allow fetching it by SHA. Original error: {exc}"
        ) from exc
    run("checkout", "-q", "FETCH_HEAD")


def _parse_templates_csv(text: str) -> list[tuple[str, str]]:
    """Parse a Loghub ``*_templates.csv`` into (EventId, EventTemplate) rows.

    We use the csv module (not a naive split) because some templates are quoted
    and contain commas. Rows missing either column are a malformed source and
    raise, rather than being silently dropped.
    """

    import csv
    import io

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "EventId" not in reader.fieldnames or "EventTemplate" not in reader.fieldnames:
        raise ValueError(
            f"Unexpected templates CSV header: {reader.fieldnames!r}; "
            "expected columns 'EventId' and 'EventTemplate'."
        )
    rows: list[tuple[str, str]] = []
    for line_no, row in enumerate(reader, start=2):
        event_id = (row.get("EventId") or "").strip()
        template = row.get("EventTemplate")
        if not event_id or template is None:
            raise ValueError(f"Malformed templates CSV row at line {line_no}: {row!r}")
        rows.append((event_id, template))
    return rows


def extract_loghub(loghub_dir: Path, commit: str) -> list[SeedRecord]:
    """Extract template records from a Loghub checkout at ``commit``.

    Reads ONLY the ``*_templates.csv`` files listed in ``LOGHUB_SYSTEMS``. It
    never opens ``*.log`` or ``*_structured.csv``, so no raw (potentially
    identifying) log line can enter the registry. Missing files raise loudly.
    """

    records: list[SeedRecord] = []
    for system, rel_path in LOGHUB_SYSTEMS.items():
        source_path = loghub_dir / rel_path
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Expected Loghub template file not found: {source_path}. "
                f"Is the checkout at commit {commit} complete?"
            )
        file_sha = sha256_file(source_path)
        text = source_path.read_text(encoding="utf-8")
        for event_id, template in _parse_templates_csv(text):
            kinds = list(classify_placeholders(template))
            records.append(
                SeedRecord(
                    source="loghub",
                    system=system,
                    template_id=f"{system}-{event_id}",
                    template=template,
                    upstream_commit=commit,
                    source_file=rel_path,
                    source_file_sha256=file_sha,
                    license=LOGHUB_LICENSE,
                    num_placeholders=len(kinds),
                    placeholder_kinds=kinds,
                )
            )
        logger.info("loghub %s: %d templates from %s", system, len(records), rel_path)
    return records


def _first_linux_command(test: dict) -> tuple[str, str, dict]:
    """Return (executor_name, command, input_argument_defaults) for a test.

    Atomic tests declare an executor block with a ``command``; input arguments
    carry default values. We keep the command verbatim (with its ``#{arg}``
    tokens) as the seed and record the declared defaults so a downstream
    generator can substitute them deterministically.
    """

    executor = test.get("executor") or {}
    command = executor.get("command")
    if not command:
        raise ValueError(
            f"Atomic test {test.get('auto_generated_guid')!r} has no executor command; "
            "it cannot be used as a command-line seed."
        )
    defaults = {
        name: (spec or {}).get("default", "")
        for name, spec in (test.get("input_arguments") or {}).items()
    }
    return executor.get("name", ""), command, defaults


def extract_art(art_dir: Path, commit: str) -> list[SeedRecord]:
    """Extract the enumerated Atomic Red Team seeds from a checkout at ``commit``.

    Each ``(technique, guid)`` in ``ART_SELECTED_TESTS`` must resolve to exactly
    one atomic test in ``atomics/<technique>/<technique>.yaml``; a missing
    technique file or GUID raises loudly so the pinned selection can never
    silently drift.
    """

    records: list[SeedRecord] = []
    # Index the selected GUIDs by technique so we parse each YAML once.
    wanted: dict[str, set[str]] = {}
    for technique, guid in ART_SELECTED_TESTS:
        wanted.setdefault(technique, set()).add(guid)

    for technique, guids in wanted.items():
        rel_path = f"atomics/{technique}/{technique}.yaml"
        source_path = art_dir / rel_path
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Expected Atomic Red Team file not found: {source_path}. "
                f"Is the checkout at commit {commit} complete and sparse-set to include {technique}?"
            )
        file_sha = sha256_file(source_path)
        document = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        by_guid = {t.get("auto_generated_guid"): t for t in document.get("atomic_tests", [])}
        for guid in sorted(guids):
            test = by_guid.get(guid)
            if test is None:
                raise KeyError(
                    f"Atomic Red Team test GUID {guid} not found in {rel_path}. "
                    "The pinned selection is out of date with this commit."
                )
            executor_name, command, defaults = _first_linux_command(test)
            records.append(
                SeedRecord(
                    source="atomic-red-team",
                    system="linux",
                    template_id=f"{technique}-{guid[:8]}",
                    template=command,
                    upstream_commit=commit,
                    source_file=rel_path,
                    source_file_sha256=file_sha,
                    license=ART_LICENSE,
                    attack_technique=technique,
                    attack_test_name=test.get("name", ""),
                    attack_guid=guid,
                    executor=executor_name,
                    input_arguments=defaults,
                )
            )
        logger.info("atomic-red-team %s: %d selected tests", technique, len(guids))
    return records


def build_registry(
    out_dir: Path,
    loghub_rev: str,
    art_rev: str,
    loghub_path: Path | None = None,
    art_path: Path | None = None,
) -> list[SeedRecord]:
    """Clone (or reuse) both sources and return the combined seed records.

    When ``loghub_path``/``art_path`` are given, that existing checkout is used
    and no network access occurs; otherwise each source is shallow-cloned at its
    pinned revision into a temporary directory.
    """

    with tempfile.TemporaryDirectory(prefix="seed_registry_") as tmp:
        tmp_dir = Path(tmp)

        if loghub_path is not None:
            loghub_dir = loghub_path
            logger.info("using existing Loghub checkout at %s", loghub_dir)
        else:
            loghub_dir = tmp_dir / "loghub"
            logger.info("cloning Loghub %s@%s", LOGHUB_URL, loghub_rev)
            clone_at_commit(LOGHUB_URL, loghub_rev, loghub_dir)

        if art_path is not None:
            art_dir = art_path
            logger.info("using existing Atomic Red Team checkout at %s", art_dir)
        else:
            art_dir = tmp_dir / "atomic-red-team"
            logger.info("cloning Atomic Red Team %s@%s", ART_URL, art_rev)
            clone_at_commit(ART_URL, art_rev, art_dir)

        records = extract_loghub(loghub_dir, loghub_rev)
        records += extract_art(art_dir, art_rev)

    _log_placeholder_summary(records)
    return records


def _log_placeholder_summary(records: list[SeedRecord]) -> None:
    """Log the distribution of inferred placeholder kinds (task WS1 item 2)."""

    kinds = Counter(
        kind for record in records for kind in record.placeholder_kinds
    )
    if kinds:
        logger.info(
            "inferred placeholder kinds across %d loghub templates: %s",
            sum(1 for r in records if r.source == "loghub"),
            ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())),
        )


def write_jsonl(records: list[SeedRecord], path: Path) -> None:
    """Write records as newline-delimited JSON with stable key order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=False))
            handle.write("\n")


def write_manifest(records: list[SeedRecord], path: Path, loghub_rev: str, art_rev: str) -> None:
    """Write a small provenance manifest summarising the registry build."""

    by_source: Counter[str] = Counter(r.source for r in records)
    by_system: Counter[str] = Counter(f"{r.source}/{r.system}" for r in records)
    source_files = sorted({(r.source_file, r.source_file_sha256) for r in records})
    manifest = {
        "generator": "data.seed_registry",
        "loghub_commit": loghub_rev,
        "atomic_red_team_commit": art_rev,
        "record_count": len(records),
        "counts_by_source": dict(sorted(by_source.items())),
        "counts_by_system": dict(sorted(by_system.items())),
        "source_files": [{"path": p, "sha256": h} for p, h in source_files],
        "licenses": sorted({r.license for r in records}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the pinned, provenance-tracked seed registry (WS1).",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output directory for registry.jsonl.")
    parser.add_argument("--loghub-rev", default=LOGHUB_DEFAULT_REV, help="Loghub commit to pin.")
    parser.add_argument("--art-rev", default=ART_DEFAULT_REV, help="Atomic Red Team commit to pin.")
    parser.add_argument(
        "--loghub-path",
        type=Path,
        default=None,
        help="Use an existing Loghub checkout instead of cloning (no network).",
    )
    parser.add_argument(
        "--art-path",
        type=Path,
        default=None,
        help="Use an existing Atomic Red Team checkout instead of cloning (no network).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _build_arg_parser().parse_args(argv)

    records = build_registry(
        out_dir=args.out,
        loghub_rev=args.loghub_rev,
        art_rev=args.art_rev,
        loghub_path=args.loghub_path,
        art_path=args.art_path,
    )

    registry_path = args.out / "registry.jsonl"
    manifest_path = args.out / "registry.manifest.json"
    write_jsonl(records, registry_path)
    write_manifest(records, manifest_path, args.loghub_rev, args.art_rev)
    logger.info("wrote %d records to %s", len(records), registry_path)
    logger.info("wrote manifest to %s", manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
