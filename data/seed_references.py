"""Reference-only seed sources: fetch, verify and locally derive templates.

Owner decision D27 (docs/TRACKER.md): any seed source whose license does not
clearly allow us to publish its content is NOT committed to this repository.
We publish only a *reference* (``data/seeds/references.json``: repo URL, pinned
commit, exact file paths, expected sha256, license, file format, extractor
name). Each user fetches the pinned files themselves and derives a
git-ignored, local-only registry from them. Nothing fetched and nothing derived
is ever committed or published (see ``docs/SEED_REFERENCES.md``).

CLI::

    python -m data.seed_references fetch  --refs data/seeds/references.json --workdir data/seeds_local/fetched
    python -m data.seed_references verify --refs data/seeds/references.json --workdir data/seeds_local/fetched
    python -m data.seed_references build  --refs data/seeds/references.json --workdir data/seeds_local/fetched

* ``fetch``  pinned, shallow, sparse fetch by full commit sha (network).
* ``verify`` sha256 of every listed file (and each license file) against the
  references file. Any mismatch or missing file is a hard failure.
* ``build``  verifies first, then runs one extractor per file format that turns
  sample log lines into ``<*>`` templates, and writes
  ``data/seeds_local/references_registry.jsonl`` with the same record schema as
  ``data/seeds/registry.jsonl`` plus ``redistribution: "local-only"``.

Design rules (AGENTS.md): no silent fallbacks (every failure raises or exits
non-zero), no network in the extractors (so they are unit tested on invented
fixtures), and deterministic output (same inputs give a byte-identical file).
The extractors are *best effort scrubbers*: they cannot prove that every
username or hostname is gone. That is exactly why the output stays local-only.
The one hard guarantee we do enforce is that no dotted-quad IP (and no
IPv6-looking address) survives in any template.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from data.entity_filler import classify_placeholders
from data.seed_registry import SeedRecord, sha256_file

logger = logging.getLogger("seed_references")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFS = REPO_ROOT / "data" / "seeds" / "references.json"
DEFAULT_OUT = REPO_ROOT / "data" / "seeds_local" / "references_registry.jsonl"
REDISTRIBUTION = "local-only"

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Keys a file entry in references.json may carry. Anything else (for example a
# "content" or "sample" key) is rejected so fetched text can never be pasted in.
_ALLOWED_FILE_KEYS = {"path", "sha256", "format", "format_description", "extractor", "system"}
_REFERENCE_STATUS = "reference-only"
_EXCLUDED_STATUS = "unverified, excluded"


class ReferenceError_(RuntimeError):
    """Any failure in the reference pipeline. Raised, never swallowed."""


# --------------------------------------------------------------------------- #
# references.json loading and validation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RefFile:
    path: str
    sha256: str
    format: str
    extractor: str
    system: str


@dataclass(frozen=True)
class RefSource:
    id: str
    name: str
    repo_url: str
    commit: str
    license_spdx: str
    license_note: str
    license_path: str
    license_sha256: str
    files: tuple[RefFile, ...]


def _safe_rel_path(path: str) -> str:
    """Reject absolute paths and ``..`` so a references file cannot read or write outside the workdir."""
    parts = Path(path).parts
    if not path or path.startswith("/") or ".." in parts:
        raise ReferenceError_(f"unsafe path in references file: {path!r}")
    return path


def load_references(refs_path: Path) -> tuple[list[RefSource], list[dict]]:
    """Parse and validate the references file.

    Returns (reference-only sources, excluded entries). Validation is strict on
    purpose: a malformed pin (short sha, missing hash, unknown extractor, extra
    content-like key) must stop the run rather than produce a weaker registry.
    """
    try:
        doc = json.loads(Path(refs_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReferenceError_(f"references file not found: {refs_path}") from exc
    except json.JSONDecodeError as exc:
        raise ReferenceError_(f"references file is not valid JSON: {exc}") from exc

    sources: list[RefSource] = []
    excluded: list[dict] = []
    seen_ids: set[str] = set()
    for entry in doc.get("sources", []):
        sid = entry.get("id")
        if not sid or sid in seen_ids:
            raise ReferenceError_(f"missing or duplicate source id: {sid!r}")
        seen_ids.add(sid)
        status = entry.get("status")
        if status == _EXCLUDED_STATUS:
            # Excluded sources must carry no fetch instructions at all.
            forbidden = {"repo_url", "commit", "files", "url"} & set(entry)
            if forbidden:
                raise ReferenceError_(f"excluded source {sid!r} must not carry fetch fields: {sorted(forbidden)}")
            excluded.append(entry)
            continue
        if status != _REFERENCE_STATUS:
            raise ReferenceError_(f"source {sid!r}: unknown status {status!r}")
        if not _FULL_SHA.match(entry.get("commit", "")):
            raise ReferenceError_(f"source {sid!r}: commit must be a full 40-character lowercase sha")
        lic = entry.get("license") or {}
        lic_file = entry.get("license_file") or {}
        if not lic.get("spdx") or not _SHA256.match(lic_file.get("sha256", "")):
            raise ReferenceError_(f"source {sid!r}: license spdx and license_file.sha256 are required")
        files: list[RefFile] = []
        for f in entry.get("files", []):
            extra = set(f) - _ALLOWED_FILE_KEYS
            if extra:
                raise ReferenceError_(f"source {sid!r}: file entry has disallowed keys {sorted(extra)}")
            if f.get("extractor") not in EXTRACTORS:
                raise ReferenceError_(f"source {sid!r}: unknown extractor {f.get('extractor')!r}")
            if not _SHA256.match(f.get("sha256", "")):
                raise ReferenceError_(f"source {sid!r}: file {f.get('path')!r} needs a sha256")
            files.append(RefFile(_safe_rel_path(f["path"]), f["sha256"], f["format"], f["extractor"],
                                 f.get("system", "syslog")))
        if not files:
            raise ReferenceError_(f"source {sid!r} lists no files")
        sources.append(RefSource(
            id=sid, name=entry["name"], repo_url=entry["repo_url"], commit=entry["commit"],
            license_spdx=lic["spdx"], license_note=lic.get("note", ""),
            license_path=_safe_rel_path(lic_file.get("path", "LICENSE")), license_sha256=lic_file["sha256"],
            files=tuple(files)))
    return sources, excluded


# --------------------------------------------------------------------------- #
# Guard: never write fetched or derived text into a tracked location
# --------------------------------------------------------------------------- #
def _require_git_ignored(path: Path) -> None:
    """Fail unless ``path`` is git-ignored (or lies outside any git repository).

    Fetched upstream files and the derived registry must never be committed
    (D27). An accidental ``git add`` is the realistic failure, so we refuse to
    write anywhere git would track. Outside a repository there is nothing to
    commit, so that case is allowed (this is what the unit tests use).
    """
    path = Path(path).resolve()
    probe = path if path.exists() else path.parent
    while not probe.exists():
        probe = probe.parent
    toplevel = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True)
    if toplevel.returncode != 0:
        return
    result = subprocess.run(["git", "-C", toplevel.stdout.strip(), "check-ignore", "-q", str(path)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise ReferenceError_(
            f"{path} is inside a git repository and is not git-ignored. Fetched or derived seed text must "
            "never be committed (docs/SEED_REFERENCES.md). Use a path under data/seeds_local/ or add it to .gitignore.")


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def _git(dest: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(dest), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise ReferenceError_(f"git {' '.join(args)} failed in {dest} (exit {result.returncode}): "
                              f"{result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def fetch_source(source: RefSource, workdir: Path) -> Path:
    """Pinned sparse shallow fetch of ``source`` into ``workdir/<id>``.

    Only the listed files plus the license file are checked out. The commit is
    fetched by full sha (depth 1, blobs on demand), then HEAD is compared with
    the pin, so a host that answers with something else fails loudly instead of
    silently giving us a different revision (AGENTS.md rule 2).
    """
    dest = Path(workdir) / source.id
    if dest.exists():
        # Reuse only an exact, already-pinned checkout; anything else is an error
        # the user must resolve by deleting the directory.
        head = _git(dest, "rev-parse", "HEAD")
        if head != source.commit:
            raise ReferenceError_(f"{dest} exists at {head}, expected {source.commit}. Delete it and re-run fetch.")
        logger.info("%s: already fetched at pinned commit %s", source.id, source.commit)
        return dest
    dest.mkdir(parents=True)
    _git(dest, "init", "-q")
    _git(dest, "remote", "add", "origin", source.repo_url)
    wanted = [source.license_path] + [f.path for f in source.files]
    # --no-cone takes exact file paths; cone mode would pull whole directories.
    _git(dest, "sparse-checkout", "set", "--no-cone", *[f"/{p}" for p in wanted])
    try:
        _git(dest, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", source.commit)
    except ReferenceError_ as exc:
        raise ReferenceError_(f"could not fetch {source.commit} from {source.repo_url}: the commit must exist and "
                              f"the host must allow fetching by sha. {exc}") from exc
    _git(dest, "checkout", "-q", "FETCH_HEAD")
    head = _git(dest, "rev-parse", "HEAD")
    if head != source.commit:
        raise ReferenceError_(f"fetched {head} but the pin is {source.commit}")
    return dest


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def verify_source(source: RefSource, workdir: Path) -> list[str]:
    """Return a list of problems (empty means every listed file matches its pinned sha256)."""
    root = Path(workdir) / source.id
    problems: list[str] = []
    expected = [(source.license_path, source.license_sha256)] + [(f.path, f.sha256) for f in source.files]
    for rel, want in expected:
        path = root / rel
        if not path.is_file():
            problems.append(f"{source.id}: missing {rel} (run fetch)")
            continue
        got = sha256_file(path)
        if got != want:
            problems.append(f"{source.id}: sha256 mismatch for {rel}: expected {want}, got {got}")
    return problems


# --------------------------------------------------------------------------- #
# Template normalisation (shared by every extractor)
# --------------------------------------------------------------------------- #
PLACEHOLDER = "<*>"

# Order matters: longer, more specific shapes first so a timestamp is not eaten
# by the generic number rule, and an IP with a port is handled as one unit.
_URL = re.compile(r"\bhttps?://[^\s\"'<>]+")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_ISO_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?\b")
# Six bytes is a MAC; netfilter "MAC=" fields carry 14 bytes (dst, src, ethertype), so accept 6 or more.
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5,}[0-9A-Fa-f]{2}\b")
_IPV6_CANDIDATE = re.compile(r"(?<![\w:.])[0-9A-Fa-f:]{3,}(?![\w:])")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b(?:(?P<sep>[:/])(?P<port>\d{1,5})\b)?")
# A hostname is only treated as one when its last label is a real TLD-like word.
# Dotted identifiers such as reverse-DNS service names end in a non-TLD label and stay.
_TLDS = ("com|net|org|edu|gov|mil|int|io|local|lan|localdomain|internal|corp|home|example|test|invalid|"
         "se|de|uk|us|fr|nl|jp|cn|ru|ch|cz|pl")
_FQDN = re.compile(rf"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+(?:{_TLDS})\b", re.IGNORECASE)
_HEX = re.compile(r"\b0[xX][0-9A-Fa-f]+\b")
_DECIMAL = re.compile(r"(?<![\w%.-])\d+(?:\.\d+)+(?![\w-])")
_NUMBER = re.compile(r"(?<![\w%.-])\d+(?![\w-])")
# Structured-data blocks (RFC 5424 style): [id key="value" ...]. Values are free text.
_SD_BLOCK = re.compile(r'\[[A-Za-z][\w.@-]*(?: [\w.@-]+="[^"]*")+\]')
_SD_VALUE = re.compile(r'(="[^"]*")')

# Username contexts. Each pattern keeps group 1 (the literal context) and
# replaces group 2 (the name). Best effort: unknown contexts are left alone.
_USER_CONTEXTS = [
    re.compile(r"(\b(?:for )?(?:invalid |illegal )?user[ =]\s*)([^\s<>;,)\]'\"]+)", re.IGNORECASE),
    re.compile(r"(\b(?:logname|ruser|euser|acct|suser|duser|username)=\s*)([^\s<>;,)\]'\"]+)", re.IGNORECASE),
    re.compile(r"(\b(?:for|failed for) )(?!user\b|invalid\b|illegal\b)([A-Za-z_][\w.-]*)(?= (?:from|on)\b)"),
    # Home directories embed the account name.
    re.compile(r"(/home/|/Users/)([^/\s;:]+)"),
    re.compile(r"(^)([A-Za-z_][\w.-]*)(?= : TTY=)"),
    re.compile(r"(^\()([A-Za-z_][\w.-]*)(?=\) CMD)"),
]
_RHOST = re.compile(r"(\brhost=)(?!<\*>)([^\s;,)\]]+)")


def _scrub_ipv6(match: re.Match) -> str:
    token = match.group(0)
    try:
        ipaddress.IPv6Address(token)
    except ValueError:
        return token
    return PLACEHOLDER


def _scrub_ipv4(match: re.Match) -> str:
    sep, port = match.group("sep"), match.group("port")
    # Keep the "<ip>:<port>" / "<ip>/<port>" shape: it tells the entity filler
    # (data/entity_filler.py) that the second placeholder is a port.
    return f"{PLACEHOLDER}{sep}{PLACEHOLDER}" if sep else PLACEHOLDER


def normalize_body(body: str) -> str:
    """Turn one sample message body into a template with ``<*>`` placeholders.

    Replaces: URLs, e-mail addresses, timestamps, MACs, IPv6 and IPv4 addresses
    (with ports), hostnames with a TLD, user names in known contexts, hex values
    and numbers. Vendor message ids such as ``%ASA-4-402117`` are protected by
    the number rule's look-behinds. This is heuristic and best effort: the
    mandatory safety check is :func:`assert_no_ip`, not this function.
    """
    text = body
    text = _URL.sub(PLACEHOLDER, text)
    text = _EMAIL.sub(PLACEHOLDER, text)
    # MAC before clock: "00:11:22" inside a MAC must not be read as a time of day.
    text = _MAC.sub(PLACEHOLDER, text)
    text = _ISO_TS.sub(PLACEHOLDER, text)
    text = _CLOCK.sub(PLACEHOLDER, text)
    text = _IPV6_CANDIDATE.sub(_scrub_ipv6, text)
    text = _IPV4.sub(_scrub_ipv4, text)
    text = _FQDN.sub(PLACEHOLDER, text)
    # Structured-data values first, so the user rules do not see quoted text.
    text = _SD_BLOCK.sub(lambda m: _SD_VALUE.sub(f'="{PLACEHOLDER}"', m.group(0)), text)
    for pattern in _USER_CONTEXTS:
        text = pattern.sub(lambda m: m.group(1) + PLACEHOLDER, text)
    text = _RHOST.sub(lambda m: m.group(1) + PLACEHOLDER, text)
    text = _HEX.sub(PLACEHOLDER, text)
    text = _DECIMAL.sub(PLACEHOLDER, text)
    text = _NUMBER.sub(PLACEHOLDER, text)
    # Adjacent placeholders carry no information and confuse the filler.
    text = re.sub(r"(?:<\*>){2,}", PLACEHOLDER, text)
    return text.strip()


_DOTTED_QUAD = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
_IPV6_ANY = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}(?![\w:])")


def assert_no_ip(template: str, where: str = "") -> None:
    """Hard failure if a template contains ANY dotted-quad IPv4 or IPv6-looking address.

    Stricter than "no routable IP": private and documentation addresses are also
    rejected, so the check never depends on a range table being right.
    """
    suffix = f" in {where}" if where else ""
    for pattern, kind in ((_DOTTED_QUAD, "dotted-quad IP"), (_IPV6_ANY, "IPv6-looking address")):
        found = pattern.search(template)
        if found:
            raise ReferenceError_(f"template contains a {kind} ({found.group(0)!r}){suffix}; "
                                  "refusing to write the registry")
    # Compressed IPv6 ("2001:db8::1") has no fixed group count, so ask the parser.
    for candidate in _IPV6_CANDIDATE.finditer(template):
        try:
            ipaddress.IPv6Address(candidate.group(0))
        except ValueError:
            continue
        raise ReferenceError_(f"template contains an IPv6 address ({candidate.group(0)!r}){suffix}; "
                              "refusing to write the registry")


def _is_informative(template: str) -> bool:
    """Drop templates that are only placeholders and punctuation (nothing to classify).

    We need at least two alphabetic words of literal text outside placeholders.
    """
    literal = template.replace(PLACEHOLDER, " ")
    return len(re.findall(r"[A-Za-z]{2,}", literal)) >= 2


# --------------------------------------------------------------------------- #
# Syslog header parsing (RFC 3164 / RFC 5424 shapes and vendor message ids)
# --------------------------------------------------------------------------- #
_TS_3164 = r"[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?"
_TS_ISO = r"\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})"
_RFC5424 = re.compile(r"^<\d{1,3}>1\s+\S+\s+\S+\s+(?P<app>\S+)\s+\S+\s+\S+\s+(?P<rest>.*)$")
_RFC3164 = re.compile(
    rf"^(?:<\d{{1,3}}>)?(?:{_TS_3164}|{_TS_ISO})\s+(?:(?P<host>\S+)\s+)?(?P<tag>[^\s:\[\]]+)(?:\[\d+\])?:\s*(?P<body>.*)$")
_VENDOR_ID = re.compile(r"%(?P<fac>[A-Z][A-Z0-9_]*)-\d-[A-Za-z0-9_]+:")
# A literal only counts as a candidate log line if something follows its timestamp.
# Bare timestamps are expected-value strings in tests, not log lines.
_LINE_SHAPE = re.compile(
    rf"^(?:<\d{{1,3}}>(?:1\s+)?)?(?:(?:{_TS_3164}|{_TS_ISO})\s+\S|%[A-Z][A-Z0-9_]*-\d-[A-Za-z0-9_]+:)")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24] or "msg"


def split_syslog(line: str) -> tuple[str, str, str] | None:
    """Split one log line into (system, slug, body), or None if it is not a recognised shape.

    The header (priority, timestamp, host, process id) is dropped, as Loghub's
    templates do; the cohort generator adds its own synthetic header (see
    docs/GENERATOR_V2.md, assumption 4). Vendor message ids (Cisco ``%ASA-4-...``)
    are kept because they are the semantic key of the message.
    """
    s = line.strip()
    if not s:
        return None
    vendor = _VENDOR_ID.search(s[:80])
    if vendor:
        return f"cisco-{vendor.group('fac').lower()}", _slug(vendor.group(0).strip("%:")), s[vendor.start():]
    m = _RFC5424.match(s)
    if m:
        rest = m.group("rest")
        rest = rest[2:] if rest.startswith("- ") else rest  # "-" is the nil structured-data marker
        return "syslog", _slug(m.group("app")), rest
    m = _RFC3164.match(s)
    if m:
        return "syslog", _slug(m.group("tag")), m.group("body")
    return None


@dataclass
class Extraction:
    """Result of one extractor on one file: templates plus counts for the build manifest."""

    templates: list[tuple[str, str, str]] = field(default_factory=list)  # (system, slug, template)
    seen: int = 0               # candidate lines or literals examined
    skipped_unparsed: int = 0   # not a recognised log shape
    skipped_degenerate: int = 0  # became all placeholders / no literal text
    duplicates: int = 0         # identical template already produced from this file


def _add(result: Extraction, system: str, slug: str, body: str, seen_templates: set[str]) -> None:
    template = normalize_body(body)
    if not _is_informative(template):
        result.skipped_degenerate += 1
        return
    if template in seen_templates:
        result.duplicates += 1
        return
    seen_templates.add(template)
    result.templates.append((system, slug, template))


# --------------------------------------------------------------------------- #
# Extractors (one per file format)
# --------------------------------------------------------------------------- #
def extract_syslog_lines(text: str) -> Extraction:
    """Plain text, one syslog line per line (RFC 3164 or 5424, or a vendor message id)."""
    result, seen = Extraction(), set()
    for raw in text.splitlines():
        if not raw.strip():
            continue
        result.seen += 1
        parts = split_syslog(raw)
        if parts is None:
            result.skipped_unparsed += 1
            continue
        _add(result, *parts, seen)
    return result


_RUBY_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'')
_RUBY_ESCAPE = re.compile(r"\\([\"'\\])")


def extract_ruby_spec_literals(text: str) -> Extraction:
    """Ruby spec files: string literals that look like a log line.

    Scans each non-comment line for single- and double-quoted literals and keeps
    those whose start matches a log-line shape. Literals with ``#{...}``
    interpolation are skipped (their value is not the literal text).
    """
    result, seen = Extraction(), set()
    for raw in text.splitlines():
        if raw.lstrip().startswith("#"):
            continue
        for m in _RUBY_STRING.finditer(raw):
            literal = m.group(1) if m.group(1) is not None else m.group(2)
            literal = _RUBY_ESCAPE.sub(r"\1", literal)
            if not _LINE_SHAPE.match(literal.strip()):
                continue  # ordinary strings (matcher names, field keys) are not log lines
            result.seen += 1
            if "#{" in literal:
                result.skipped_unparsed += 1
                continue
            parts = split_syslog(literal)
            if parts is None:
                result.skipped_unparsed += 1
                continue
            _add(result, *parts, seen)
    return result


_RUST_STRING = re.compile(r'r(?P<h>#*)"(?P<raw>.*?)"(?P=h)|"(?P<cooked>(?:[^"\\\n]|\\.)*)"', re.DOTALL)
_RUST_HOLE = re.compile(r"\{[A-Za-z0-9_:?#]*\}")


def extract_rust_string_literals(text: str) -> Extraction:
    """Rust source: raw and ordinary string literals that look like a log line.

    ``format!`` holes (``{}``, ``{msg}``) mark where the test inserts a value,
    so they become ``<*>`` placeholders. Literals that are nothing but holes are
    dropped as degenerate.
    """
    result, seen = Extraction(), set()
    for m in _RUST_STRING.finditer(text):
        literal = m.group("raw") if m.group("raw") is not None else m.group("cooked")
        if not _LINE_SHAPE.match(literal.strip()):
            continue
        result.seen += 1
        parts = split_syslog(literal)
        if parts is None:
            result.skipped_unparsed += 1
            continue
        system, slug, body = parts
        _add(result, system, slug, _RUST_HOLE.sub(PLACEHOLDER, body), seen)
    return result


EXTRACTORS: dict[str, Callable[[str], Extraction]] = {
    "syslog_lines": extract_syslog_lines,
    "ruby_spec_literals": extract_ruby_spec_literals,
    "rust_string_literals": extract_rust_string_literals,
}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _template_id(source_id: str, slug: str, system: str, template: str) -> str:
    digest = hashlib.sha256(f"{system}\0{template}".encode("utf-8")).hexdigest()[:8]
    return f"{source_id}-{slug}-{digest}"


def build_records(sources: list[RefSource], workdir: Path) -> tuple[list[dict], dict]:
    """Run each file's extractor and return (records, per-file counts).

    Records use the registry schema (``data.seed_registry.SeedRecord``) plus
    ``redistribution``. A file that yields zero templates is an error: an empty
    result means the extractor no longer matches the file, and a silently thin
    registry would bias any dataset built from it.
    """
    records: list[dict] = []
    counts: dict[str, dict] = {}
    for source in sources:
        license_text = f"{source.license_spdx}; {source.repo_url} (reference-only, local-only)"
        seen_in_source: set[str] = set()
        for ref in source.files:
            path = Path(workdir) / source.id / ref.path
            try:
                text = path.read_text(encoding="utf-8")
            except (FileNotFoundError, UnicodeDecodeError) as exc:
                raise ReferenceError_(f"cannot read {path}: {exc}") from exc
            extraction = EXTRACTORS[ref.extractor](text)
            if not extraction.templates:
                raise ReferenceError_(f"{source.id}:{ref.path}: extractor {ref.extractor!r} produced no templates "
                                      f"({extraction.seen} candidates, {extraction.skipped_unparsed} unparsed)")
            file_sha = sha256_file(path)
            kept = 0
            for system, slug, template in extraction.templates:
                assert_no_ip(template, f"{source.id}:{ref.path}")
                if template in seen_in_source:
                    extraction.duplicates += 1
                    continue
                seen_in_source.add(template)
                kinds = list(classify_placeholders(template))
                record = asdict(SeedRecord(
                    source=source.id, system=system, template_id=_template_id(source.id, slug, system, template),
                    template=template, upstream_commit=source.commit, source_file=ref.path,
                    source_file_sha256=file_sha, license=license_text,
                    num_placeholders=len(kinds), placeholder_kinds=kinds))
                record["redistribution"] = REDISTRIBUTION
                records.append(record)
                kept += 1
            counts[f"{source.id}:{ref.path}"] = {
                "extractor": ref.extractor, "candidates": extraction.seen, "templates": kept,
                "skipped_unparsed": extraction.skipped_unparsed, "skipped_degenerate": extraction.skipped_degenerate,
                "duplicates": extraction.duplicates}
    records.sort(key=lambda r: (r["source"], r["source_file"], r["template_id"]))
    ids = [r["template_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ReferenceError_("duplicate template_id in derived registry")
    return records, counts


def write_registry(records: list[dict], counts: dict, out_path: Path) -> Path:
    """Write the JSONL registry and a counts-only manifest next to it."""
    out_path = Path(out_path)
    _require_git_ignored(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    out_path.write_text(body, encoding="utf-8")
    manifest = {
        "generator": "data.seed_references",
        "redistribution": REDISTRIBUTION,
        "contains_local_only_seed_text": True,
        "notice": "Derived from reference-only sources. Do not commit or publish this file, or any dataset built "
                  "from it (docs/SEED_REFERENCES.md, D27).",
        "record_count": len(records),
        "registry_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "counts_by_source": {s: sum(1 for r in records if r["source"] == s) for s in sorted({r["source"] for r in records})},
        "per_file": dict(sorted(counts.items())),
    }
    manifest_path = out_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _select(sources: list[RefSource], only: list[str] | None) -> list[RefSource]:
    if not only:
        return sources
    known = {s.id for s in sources}
    unknown = set(only) - known
    if unknown:
        raise ReferenceError_(f"unknown source id(s) {sorted(unknown)}; known: {sorted(known)}")
    return [s for s in sources if s.id in set(only)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch, verify and derive reference-only seed sources (D27).")
    parser.add_argument("command", choices=["fetch", "verify", "build"])
    parser.add_argument("--refs", type=Path, default=DEFAULT_REFS, help="references.json (default: data/seeds/references.json)")
    parser.add_argument("--workdir", type=Path, required=True,
                        help="git-ignored directory for fetched files (for example data/seeds_local/fetched)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="build: output registry (git-ignored)")
    parser.add_argument("--only", action="append", help="limit to a source id (repeatable)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        sources, excluded = load_references(args.refs)
        sources = _select(sources, args.only)
        for entry in excluded:
            logger.info("excluded (%s): %s", entry["status"], entry["id"])
        _require_git_ignored(args.workdir)
        if args.command == "fetch":
            args.workdir.mkdir(parents=True, exist_ok=True)
            for source in sources:
                fetch_source(source, args.workdir)
                logger.info("%s: fetched %s", source.id, source.commit)
            return 0
        problems = [p for s in sources for p in verify_source(s, args.workdir)]
        if problems:
            print("verification failed:\n" + "\n".join(problems), file=sys.stderr)
            return 1
        if args.command == "verify":
            print(f"verified {sum(len(s.files) + 1 for s in sources)} files for {len(sources)} sources")
            return 0
        records, counts = build_records(sources, args.workdir)
        write_registry(records, counts, args.out)
        print(f"wrote {len(records)} LOCAL-ONLY records to {args.out} (do not commit or publish)")
        return 0
    except ReferenceError_ as exc:
        print(f"seed_references failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
