"""Deterministic synthetic entity filler for Loghub `<*>` templates.

Loghub templates carry `<*>` placeholders where the original log lines held
concrete values (IP addresses, usernames, ports, block IDs, ...). WS1 must
turn those templates into runnable synthetic evidence WITHOUT copying any real
value from the raw logs (AGENTS.md rule 4: never commit identifiable traces).

Two guarantees make this safe and reproducible for a measurement harness:

1. **Determinism.** Filling is seeded from ``(seed, template_id, occurrence)``
   only, so the same template always yields the same synthetic line. Nothing
   depends on wall-clock time, process state, or global RNG. This is required
   so a fixture can be regenerated bit-for-bit and its provenance recorded
   (AGENTS.md rule 7).

2. **No non-synthetic IPs.** Every value the filler classifies as an IP address
   is drawn from the RFC 5737 documentation ranges, which are reserved and never
   routable. In addition, any dotted numeric run (e.g. a version string) is
   generated so it can never coincidentally read as a routable IPv4 dotted quad
   (see ``_fill_dot_run``). ``tests/test_seed_registry.py`` enforces both.

The classifier is heuristic: it infers a *kind* per placeholder from the
surrounding literal text. The inference is deterministic and side-effect free,
and ``fill_template`` returns the ordered list of inferred kinds so callers can
log exactly what was assumed for each template (task WS1 item 2).
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass

# RFC 5737 reserved-for-documentation IPv4 blocks. These /24s are guaranteed by
# the RFC never to be routed on the public Internet, so emitting them cannot
# leak or impersonate a real host. We store the first three octets; the filler
# appends a synthetic host octet in 1..254.
RFC5737_BLOCKS: tuple[str, ...] = ("192.0.2", "198.51.100", "203.0.113")

# RFC 2606 reserves these domains/TLDs for documentation and testing, so a
# synthetic hostname built from them can never resolve to a real machine.
_FAKE_DOMAINS: tuple[str, ...] = ("example.com", "example.net", "example.org", "node.invalid")

# Role-based, non-identifiable synthetic principals. Deliberately generic so no
# record can be traced to a real person (AGENTS.md rule 4).
_FAKE_USERS: tuple[str, ...] = (
    "svc_backup", "svc_deploy", "svc_index", "batchjob", "appsvc",
    "opstest", "user_a", "user_b", "sysagent", "nulluser",
)

# Synthetic path segments used where a placeholder stands in for a filesystem
# path component. None reference a real user or host directory.
_FAKE_PATH_SEGMENTS: tuple[str, ...] = (
    "var/log/app", "srv/data/part-00001", "tmp/work", "opt/service/run",
    "data/shard-03", "user/job/output", "mnt/vol1/segment",
)

# The `<*>` marker Loghub uses for every extracted variable field.
_PLACEHOLDER = "<*>"
# Split on the marker while keeping it as its own token, so we can look at the
# literal text immediately before and after each placeholder.
_SPLIT_RE = re.compile(r"(<\*>)")


@dataclass(frozen=True)
class FilledTemplate:
    """Result of filling one template: the synthetic line and what was assumed.

    ``kinds`` lists the inferred placeholder kind for each ``<*>`` in template
    order, so a caller can record (and a reviewer can audit) exactly which
    heuristic fired for every field.
    """

    text: str
    kinds: tuple[str, ...]


def _rng_for(seed: int, template_id: str, occurrence: int) -> random.Random:
    """Return a private RNG seeded only from stable inputs.

    We hash ``seed``, the template id and the placeholder's occurrence index
    into a fixed 8-byte integer. Using a per-call ``random.Random`` (never the
    module-global RNG) keeps filling deterministic and free of cross-talk
    between templates, which is what lets the whole fixture be regenerated
    reproducibly.
    """

    key = f"{seed}:{template_id}:{occurrence}".encode("utf-8")
    digest = hashlib.sha256(key).digest()[:8]
    return random.Random(int.from_bytes(digest, "big"))


def _classify_single(left: str, right: str) -> str:
    """Infer the kind of one placeholder from its surrounding literal text.

    Rules are ordered most-specific first; the first match wins. ``left`` is the
    literal immediately preceding the placeholder, ``right`` the literal
    immediately following it. The heuristics come from reading the actual
    OpenSSH/OpenStack/BGL/HDFS/Linux template sets; anything unmatched falls
    back to a bounded integer, which is always safe (it can never form an IP on
    its own because a lone number has no dotted context).
    """

    lstrip_l = left.rstrip()
    lower_l = lstrip_l.lower()
    lstrip_r = right.lstrip()
    lower_r = right.lower()

    # HDFS block identifiers: "... blk_<*> ...". The template keeps the "blk_"
    # prefix as a literal, so the placeholder is just the numeric id.
    if left.endswith("blk_"):
        return "block_id"

    # POSIX credential ids embedded as "uid=<*>", "euid=<*>".
    if lower_l.endswith(("uid=", "euid=", "ruid=", "gid=")):
        return "uid"

    # Explicit "port <*>" fields.
    if lower_l.endswith("port"):
        return "port"

    # IP addresses. These are the fields that would leak real hosts if copied
    # from raw logs, so they must be classified precisely and filled from
    # RFC 5737 only.
    if "rhost=" in left[-8:]:
        return "ip"
    if lower_l.endswith(("from", "to", "dest:", "src:")):
        # "from <*>", "to <*>", "src: /<*>", "dest: /<*>" are all addresses,
        # including "identification string from <*>", which is also a host.
        return "ip"
    if left.endswith(("/", ":")) and lstrip_r.startswith(":"):
        # First half of an "<*>:<port>" address (HDFS datanode templates).
        return "ip"
    # Second half of an "<ip>:<*>" address is a port. The IP rule above already
    # consumed the address half, so a lone trailing ":" here means a port.
    if left.endswith(":"):
        return "port"
    if lower_l.endswith("getaddrinfo for"):
        return "hostname"

    # Usernames / principals.
    if lower_l.endswith(("user", "user=")):
        return "username"
    if lower_l.endswith("for") and lower_r.lstrip().startswith("from"):
        # "Accepted password for <*> from <ip> ...": the principal.
        return "username"

    # Filesystem paths: "/<*>" or "<*>/...".
    if left.endswith("/") or lstrip_r.startswith("/"):
        return "path"

    # Everything else is a bounded synthetic integer.
    return "number"


def _fill_value(kind: str, rng: random.Random) -> str:
    """Generate one synthetic value for an inferred kind, using ``rng`` only."""

    if kind == "ip":
        block = rng.choice(RFC5737_BLOCKS)
        return f"{block}.{rng.randint(1, 254)}"
    if kind == "port":
        return str(rng.randint(1024, 65535))
    if kind == "uid":
        # Either an unprivileged account id or root (0); both are non-identifying.
        return str(rng.choice([0, rng.randint(1000, 60000)]))
    if kind == "username":
        return rng.choice(_FAKE_USERS)
    if kind == "hostname":
        return f"host-{rng.randint(1, 250)}.{rng.choice(_FAKE_DOMAINS)}"
    if kind == "block_id":
        # HDFS block ids are large signed integers; mirror that shape.
        magnitude = rng.randint(10 ** 17, 10 ** 18)
        return str(-magnitude if rng.random() < 0.5 else magnitude)
    if kind == "path":
        return rng.choice(_FAKE_PATH_SEGMENTS)
    # "number" and any unknown kind: a small bounded integer.
    return str(rng.randint(1, 4096))


def _fill_dot_run(length: int, rng: random.Random) -> list[str]:
    """Fill a run of ``length`` placeholders joined by dots (a version/decimal).

    A dotted run of four or more numeric components could, by coincidence, read
    as a routable IPv4 dotted quad (four octets each 0-255). To make that
    impossible we force the first component of any run of length >= 4 into
    256..999, which can never be a valid octet, so the rendered string can never
    be mistaken for — or leak as — an IP address. Shorter runs (versions like
    "2.6.18", decimals like "12.5") cannot form a four-octet quad at all.
    """

    components: list[str] = []
    for index in range(length):
        if index == 0 and length >= 4:
            components.append(str(rng.randint(256, 999)))
        else:
            components.append(str(rng.randint(0, 99)))
    return components


def _segment(template: str) -> list[tuple[str, object]]:
    """Break a template into ordered ('literal'|'run', payload) segments.

    A 'run' is a maximal group of placeholders separated only by empty strings
    or single dots (e.g. ``<*>.<*>.<*>``), which we fill together so dotted
    numeric strings stay coherent and IP-safe. All other placeholders are runs
    of length 1 and get per-placeholder classification.
    """

    tokens = _SPLIT_RE.split(template)
    segments: list[tuple[str, object]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token != _PLACEHOLDER:
            if token:
                segments.append(("literal", token))
            index += 1
            continue
        # Start of a placeholder run; extend while the joining literal is "" or ".".
        run_literals: list[str] = []  # literal separators inside the run
        run_length = 1
        left_literal = segments[-1][1] if segments and segments[-1][0] == "literal" else ""
        cursor = index + 1
        while cursor + 1 < len(tokens) and tokens[cursor] in ("", ".") and tokens[cursor + 1] == _PLACEHOLDER:
            run_literals.append(tokens[cursor])
            run_length += 1
            cursor += 2
        right_literal = tokens[cursor] if cursor < len(tokens) else ""
        # A run is "dotted" if any internal separator is a literal dot, i.e. it
        # renders as a dotted numeric string (version or decimal). Mixed runs
        # such as "<*>.<*>.<*><*>.<*>" (dots plus bare adjacency) count too, so
        # their dots are preserved and the length>=4 IP guard still applies.
        dotted = any(sep == "." for sep in run_literals)
        segments.append((
            "run",
            {
                "length": run_length,
                "dotted": dotted,
                "separators": run_literals,
                "left": left_literal,
                "right": right_literal,
            },
        ))
        index = cursor
    return segments


def classify_placeholders(template: str) -> tuple[str, ...]:
    """Return the inferred kind for each placeholder, in template order.

    Pure and side-effect free, so it can be used both to fill a template and to
    record — in the registry and in logs — which kinds were assumed, without
    generating any values.
    """

    kinds: list[str] = []
    for seg_type, payload in _segment(template):
        if seg_type != "run":
            continue
        payload = payload  # type: ignore[assignment]
        if payload["dotted"]:  # type: ignore[index]
            kinds.extend(["version"] * payload["length"])  # type: ignore[index]
        else:
            kind = _classify_single(payload["left"], payload["right"])  # type: ignore[index]
            kinds.extend([kind] * payload["length"])  # type: ignore[index]
    return tuple(kinds)


def fill_template(template: str, template_id: str, seed: int) -> FilledTemplate:
    """Deterministically replace every ``<*>`` with a synthetic value.

    ``template_id`` and ``seed`` fully determine the output. The returned
    ``kinds`` records the inferred kind of each placeholder so a caller can log
    exactly what was assumed (task WS1 item 2).
    """

    out_parts: list[str] = []
    kinds: list[str] = []
    occurrence = 0
    for seg_type, payload in _segment(template):
        if seg_type == "literal":
            out_parts.append(payload)  # type: ignore[arg-type]
            continue
        payload = payload  # type: ignore[assignment]
        length = payload["length"]  # type: ignore[index]
        if payload["dotted"]:  # type: ignore[index]
            rng = _rng_for(seed, template_id, occurrence)
            values = _fill_dot_run(length, rng)
            separators = payload["separators"]  # type: ignore[index]
            # Re-interleave the generated components with their "." separators.
            rendered = values[0]
            for sep, value in zip(separators, values[1:]):
                rendered += sep + value
            out_parts.append(rendered)
            kinds.extend(["version"] * length)
            occurrence += length
        else:
            kind = _classify_single(payload["left"], payload["right"])  # type: ignore[index]
            for _ in range(length):
                rng = _rng_for(seed, template_id, occurrence)
                out_parts.append(_fill_value(kind, rng))
                kinds.append(kind)
                occurrence += 1
    return FilledTemplate(text="".join(out_parts), kinds=tuple(kinds))
