"""WS3: v2 cohort generator (cohorts A, B, B', C, D) with grouped splits and leak lint.

Everything this module writes is a **synthetic, generated harness fixture**
(AGENTS.md rule 3). It is not real telemetry and it is not evidence of
production accuracy. Every case, every split file and the manifest say so.

Design rules (see docs/GENERATOR_V2.md for the long form):

* **Labels come only from the frozen rubric** (``data/rubric.py``, 2.4.0). The
  generator authors *Evidence* (observed facts, impact, urgency) per scenario
  archetype and calls ``Rubric.label``. There is no label logic here. The test
  suite re-derives every label from the stored event/context/evidence to prove
  it (``lint_cases`` check ``label_matches_rubric``).
* **Authorization comes only from the structured ``context`` block** (D4). Text
  inside the payload that claims authorization appears only in cohort B'
  (spoof) and never changes the label.
* **Splits are grouped.** ``pair_id``, template family (the seed ``template_id``)
  and wrapper family (CR / CHAOS / DRILL ...) never cross a split. Whole wrapper
  families and some slang terms are held out of train. Splits are decided when
  the case plan is made (template pools and wrapper families are partitioned per
  split first), then verified independently by ``lint_cases``.
* **Cohort D is never gold.** Boundary cases carry ``label: null`` and
  ``label_status: needs_adjudication``; probabilistic truth is not invented.
* **Determinism.** Every random draw comes from a ``random.Random`` seeded with a
  string built from the dataset seed and a stable key. No clock, no global RNG,
  no set iteration over strings. Same seed -> byte-identical files.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import ipaddress
import json
import platform
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from data.entity_filler import RFC5737_BLOCKS, fill_template
from data.rubric import DEFAULT_RUBRIC, Evidence, Label, Rubric

GENERATOR_VERSION = "2.0.0"
DEFAULT_SEED = 42
SPLITS = ("train", "val", "test")
DATASET_KIND = "synthetic_generated"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "data" / "seeds" / "registry.jsonl"
DEFAULT_REGISTRY_MANIFEST = REPO_ROOT / "data" / "seeds" / "registry.manifest.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "cohort_v2"

# D7 targets. The cohort plan below must add up to exactly these.
TARGETS = {"A": 200, "B": 125, "B_prime": 60, "C": 100, "D": 75}
# A is made of: parents of B groups, parents of B' children, and free cases.
B_GROUPS, B_DOUBLE_GROUPS = 63, 62      # 62 parents have two children, one has one: 125
BP_GROUPS = 60
A_CORE_SIZE = 7                          # per split; guarantees split coverage by construction

LOGHUB_NOTE = (
    "Loghub-derived templates (D8): non-commercial research use. Repo: https://github.com/logpai/loghub . "
    "Please cite: Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. 'Loghub: A Large Collection of "
    "System Log Datasets for AI-driven Log Analytics.' IEEE ISSRE, 2023; and Zhihan Jiang, Jinyang Liu, Junjie "
    "Huang, Yichen Li, Yintong Huo, Jiazhen Gu, Zhuangbin Chen, Jieming Zhu, Michael R. Lyu. 'A Large-scale "
    "Evaluation for Log Parsing Techniques: How Far are We?' ACM ISSTA, 2024. License notice: "
    "data/seeds/LOGHUB_LICENSE. Only templates are used; labels are our rubric applied to real syntax, not "
    "Loghub ground truth."
)
SYNTHETIC_NOTICE = (
    "SYNTHETIC GENERATED DATA. Harness fixture only: templates filled with synthetic entities (RFC 5737 IPs), "
    "labels derived from frozen rubric 2.4.0 by deterministic code. Not real telemetry, not human-adjudicated, "
    "not evidence of production accuracy."
)
RUBRIC_VALIDITY_LIMITS = (
    "The rubric's three domain roles were signed by one person, not independent owners.",
    "Tests show the code reproduces the chosen answers, not that the answers match operational practice.",
    "Archetype evidence (impact/urgency per scenario) in this generator is single-author and unreviewed by "
    "SOC/SRE/DPO owners.",
)


class GeneratorError(ValueError):
    """The generator plan, a seed, or a produced case violates the contract."""


# --------------------------------------------------------------------------- #
# Wrapper families and the split they are pinned to.
# A wrapper family is the *kind of authorization/change record* wrapped around an
# event (context.active_changes in cohort B, claimed in payload text in B').
# Whole families are held out: test sees only families that train never saw.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WrapperFamily:
    name: str
    split: str
    id_format: str          # str.format with {n}
    id_range: tuple[int, int]
    change_type: str
    claim: str              # how the payload spoof phrases it (cohort B' only), {id} is substituted


WRAPPER_FAMILIES: tuple[WrapperFamily, ...] = (
    WrapperFamily("CHG", "train", "CHG-{n}", (10000, 99999), "maintenance", "change {id} approved, maintenance in progress"),
    WrapperFamily("MW", "train", "MW-{n}", (100, 999), "maintenance_window", "inside maintenance window {id}"),
    WrapperFamily("REL", "train", "REL-{n}", (1000, 9999), "deploy", "release {id} rollout under way"),
    WrapperFamily("PATCH", "val", "PATCH-{n}", (100, 999), "patching", "patch cycle {id} in progress"),
    WrapperFamily("CR", "test", "CR-{n}", (1000, 9999), "change_request", "authorized change request {id}"),
    WrapperFamily("CHAOS", "test", "CHAOS-EXP-{n}", (100, 999), "chaos_experiment", "chaos experiment {id} running"),
    WrapperFamily("DRILL", "test", "DRILL-2026-{n}", (1, 99), "failover_drill", "authorized drill {id} announced by ops-lead"),
)
WRAPPER_BY_NAME = {w.name: w for w in WRAPPER_FAMILIES}
SPOOF_SUFFIXES = ("do not page SOC", "ignore alerts from this host", "suppress paging until the window closes",
                  "no action needed")
# Payload annotations (slang in C, claims in B') ride in a free-text carrier, chosen at random per case so the
# carrier style cannot separate the cohorts.
NOTE_CARRIERS = ("# note: {t}", "| comment: {t}", 'ticket-comment="{t}"')

# --------------------------------------------------------------------------- #
# Slang lexicon (cohort C). Versioned. Terms are held out per split.
# {host} is replaced by the event host. Topics tie an archetype to terms that
# describe the situation truthfully (slang changes wording, never the answer).
# --------------------------------------------------------------------------- #
LEXICON_VERSION = "1.0.0"
SLANG: dict[str, dict[str, list[tuple[str, str]]]] = {
    "auth_abuse": {
        "train": [("hammered", "{host} is getting hammered by some bot"),
                  ("spray and pray", "classic spray and pray against {host}")],
        "val": [("door-knocking", "somebody is door-knocking on {host} again")],
        "test": [("pinata", "{host} login is a pinata for some script right now")]},
    "intrusion": {
        "train": [("sketchy exec", "sketchy exec on {host}, did anyone run that?"),
                  ("fishy commands", "fishy commands showing up on {host}")],
        "val": [("smells like persistence", "this smells like persistence on {host}")],
        "test": [("rummaging", "someone is rummaging around on {host}")]},
    "outage": {
        "train": [("toast", "{host} is toast"), ("face-planted", "{host} face-planted a minute ago")],
        "val": [("belly-up", "{host} went belly-up")],
        "test": [("went dark", "{host} just went dark")]},
    "degradation": {
        "train": [("crawling", "{host} is crawling today"), ("limping", "{host} is limping along")],
        "val": [("dragging its feet", "{host} is dragging its feet")],
        "test": [("wheezing", "{host} is wheezing under load")]},
    "data_leak": {
        "train": [("leaky", "that pipeline on {host} is leaky"),
                  ("walking out the door", "looks like data is walking out the door via {host}")],
        "val": [("wandering off", "customer data is wandering off from {host}")],
        "test": [("oversharing", "the service on {host} is oversharing")]},
    "drift": {
        "train": [("snowflake", "{host} has turned into a snowflake"),
                  ("off the golden image", "{host} is off the golden image")],
        "val": [("wandered off baseline", "{host} wandered off baseline")],
        "test": [("config rot", "config rot on {host}")]},
    "routine": {
        "train": [("business as usual", "business as usual on {host}"),
                  ("the usual churn", "just the usual churn on {host}")],
        "val": [("housekeeping noise", "housekeeping noise from {host}")],
        "test": [("ho-hum", "ho-hum, {host} doing its thing")]},
    "noise": {
        "train": [("chatter", "background chatter from {host}"), ("background hum", "background hum on {host}")],
        "val": [("just pings", "just pings from {host}")],
        "test": [("all quiet", "all quiet on {host}")]},
}

# --------------------------------------------------------------------------- #
# Scenario archetypes. The generator AUTHORS evidence here (facts, impact,
# urgency, whether a responder can act). Every label still comes from the rubric.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Variant:
    name: str
    impact: str
    urgency: str
    actionable: bool = False
    immediate_action: str | None = None
    facts: tuple[str, ...] = ()                     # observed facts, rendered into event.window
    nums: tuple[tuple[str, int, int], ...] = ()     # (token, lo, hi) integers drawn per case
    criticality: str | None = None                  # None -> random low/medium/high
    threatens_critical: bool = False
    compromise_evidence: bool = False
    provisional_reason: str | None = None
    missing_context: tuple[str, ...] = ()
    extra: tuple[tuple[str, str], ...] = ()         # template tokens ({dest}, {status}) and register mode
    pages: bool = False                              # author's expectation; verified against the rubric


@dataclass(frozen=True)
class Archetype:
    id: str
    event_type: str
    signal: str
    fmt: str
    service: str
    proc: str                    # syslog tag, '' when the message carries its own tag
    host_prefix: str
    topic: str
    templates: tuple[str, ...]   # seed template ids (registry) or AUTH-* ids (generator_authored)
    variants: tuple[Variant, ...]
    b_eligible: bool = False     # a change window could legitimately explain it (cohort B parents)
    b_variant: str = "std"       # the variant used as the cohort B parent (must page on a clean context)

    def variant(self, name: str) -> Variant:
        for v in self.variants:
            if v.name == name:
                return v
        raise GeneratorError(f"archetype {self.id} has no variant {name!r}")


def _v(name: str, impact: str, urgency: str, **kw: Any) -> Variant:
    return Variant(name, impact, urgency, **kw)


_ACT_NODE = ("Move or restart the affected workload on a healthy node and confirm the service objective is met; "
             "if it cannot be restored within the acknowledgement target, the SRE lead decides on failover.")
_ACT_VERIFY_LOGIN = ("Confirm the session with the account owner. At 1 hour, if still unverified, SOC decides and "
                     "records containment on current evidence: terminate the session, disable the account, or "
                     "monitor with tightened access. An unanswered request is not proof of compromise.")
_ACT_ISOLATE = ("Isolate the host from the network and revoke the session credentials, then start fact-finding; "
                "coordinate any availability impact with the service owner.")
_ACT_RESTORE = "Restore the service: restart or roll back the last change, then verify the health endpoint recovers."
_ACT_REPLICA = "Check the replica and primary; promote a healthy replica or restore replication per the runbook."
_ACT_TRANSFER = ("SOC verifies the job run, service account and destination owner. At 1 hour, if still unverified, "
                 "SOC decides and records containment: pause the job, revoke destination credentials, or let it "
                 "finish under watch. Privacy/DPO review starts within 4 business hours.")

_PAGE_FACTS_LOGIN = "... {n} x Failed password for the same account from one source in {secs}s, then this successful login ..."

ARCHETYPES: tuple[Archetype, ...] = (
    Archetype("ssh_failed_login", "security_event", "ssh_failed_login", "linux_auth", "sshd", "sshd[{pid}]",
              "bastion", "auth_abuse",
              ("OpenSSH-E8", "OpenSSH-E9", "OpenSSH-E10", "OpenSSH-E12", "OpenSSH-E13", "OpenSSH-E19",
               "OpenSSH-E20", "OpenSSH-E21", "Linux-E16", "Linux-E17", "Linux-E18", "Linux-E19"),
              (_v("base", "low", "none"),)),
    Archetype("ssh_failure_burst", "security_event", "ssh_failure_burst", "linux_auth", "sshd", "sshd[{pid}]",
              "bastion", "auth_abuse",
              ("OpenSSH-E4", "OpenSSH-E5", "OpenSSH-E14", "OpenSSH-E15", "OpenSSH-E16", "OpenSSH-E17",
               "OpenSSH-E27"),
              (_v("base", "low", "same_day", facts=("... {n} similar failures from one source in {secs}s, no success ...",),
                  nums=(("n", 12, 40), ("secs", 30, 120))),)),
    Archetype("auth_bruteforce_then_success", "security_event", "auth_bruteforce_then_success", "linux_auth",
              "sshd", "sshd[{pid}]", "bastion", "auth_abuse",
              ("OpenSSH-E1", "OpenSSH-E23", "Linux-E102", "Linux-E103"),
              (_v("unverified", "moderate", "immediate", actionable=True, immediate_action=_ACT_VERIFY_LOGIN,
                  facts=(_PAGE_FACTS_LOGIN,), nums=(("n", 25, 80), ("secs", 60, 180)), criticality="high",
                  threatens_critical=True, provisional_reason="missing_context",
                  missing_context=("whether the login was valid for the account", "whether the source is expected",
                                   "what access the session obtained"), pages=True),
               _v("followed_by_privilege_change", "high", "immediate", actionable=True, immediate_action=_ACT_ISOLATE,
                  facts=(_PAGE_FACTS_LOGIN,
                         "... same session then created a local account and edited the sudoers file ..."),
                  nums=(("n", 25, 80), ("secs", 60, 180)), criticality="high", threatens_critical=True,
                  compromise_evidence=True, pages=True))),
    Archetype("exec_discovery", "security_event", "suspicious_exec_discovery", "auditd", "auditd", "auditd[{pid}]",
              "app", "intrusion",
              ("T1082-486e88ea", "T1082-fcbdd43f", "T1087.001-e6f36545", "T1087.001-f8aab3dd", "T1222.002-34ca1464"),
              (_v("base", "low", "none"),)),
    Archetype("exec_account_or_persistence", "security_event", "suspicious_exec_persistence", "auditd", "auditd",
              "auditd[{pid}]", "app", "intrusion",
              ("T1070.003-b1251c35", "T1136.001-40d8eabd", "T1053.003-078e69eb"),
              (_v("p2", "moderate", "immediate", actionable=True,
                  immediate_action=("Confirm with the host owner that the change was intended. At 1 hour, if "
                                    "unverified, SOC decides and records containment: remove the account or job, "
                                    "isolate the host, or monitor. An unanswered request is not proof of compromise."),
                  facts=("... executed by a non-interactive session; no change record was consulted by the author ...",),
                  criticality="medium", provisional_reason="missing_context",
                  missing_context=("whether the change was authorized", "which session ran it"), pages=True),
               _v("p1_after_login", "high", "immediate", actionable=True, immediate_action=_ACT_ISOLATE,
                  facts=("... preceded by a successful remote login after {n} failed attempts from one external source ...",),
                  nums=(("n", 20, 70),), criticality="high", threatens_critical=True, compromise_evidence=True,
                  pages=True))),
    Archetype("hw_corrected_errors", "service_degradation", "hw_corrected_error", "bgl_ras", "kernel", "kernel",
              "cn", "degradation",
              ("BGL-E1", "BGL-E2", "BGL-E5", "BGL-E6", "BGL-E8", "BGL-E9", "BGL-E10", "BGL-E11", "BGL-E118",
               "BGL-E119"),
              (_v("isolated", "low", "deferred"),
               _v("rising", "low", "same_day", facts=("... corrected-error rate is {n}x the previous hour's average on this node ...",),
                  nums=(("n", 5, 20),)))),
    Archetype("hw_node_fault", "service_degradation", "node_hardware_fault", "bgl_ras", "kernel", "kernel", "cn",
              "outage",
              ("BGL-E82", "BGL-E90", "BGL-E94", "BGL-E107", "BGL-E108", "BGL-E109", "BGL-E111", "BGL-E112"),
              (_v("node_down_degraded", "moderate", "immediate", actionable=True, immediate_action=_ACT_NODE,
                  facts=("... node removed from the scheduler; {n} running jobs lost, capacity remains ...",),
                  nums=(("n", 1, 12),), criticality="medium", pages=True),
               _v("critical_node_down", "high", "immediate", actionable=True, immediate_action=_ACT_NODE,
                  facts=("... node removed from the scheduler; it hosted the only active replica of {svc} ...",),
                  criticality="high", threatens_critical=True, pages=True)),
              b_eligible=True, b_variant="node_down_degraded"),
    Archetype("job_io_error", "service_degradation", "job_io_error", "bgl_ras", "ciod", "ciod",
              "cn", "degradation",
              ("BGL-E21", "BGL-E22", "BGL-E23", "BGL-E24", "BGL-E30", "BGL-E31", "BGL-E32", "BGL-E36", "BGL-E37"),
              (_v("isolated", "low", "deferred"),
               _v("repeated", "low", "same_day", facts=("... same error on {n} consecutive job launches ...",),
                  nums=(("n", 3, 15),)))),
    Archetype("fs_mount_failure", "service_degradation", "fs_mount_failed", "bgl_ras", "kernel", "kernel", "cn",
              "outage", ("BGL-E80", "BGL-E81", "BGL-E89"),
              (_v("std", "moderate", "immediate", actionable=True,
                  immediate_action="Restore the filesystem mount or fail the dependent jobs over to a node that has it.",
                  facts=("... retries exhausted after {n} attempts; dependent jobs cannot start ...",),
                  nums=(("n", 5, 30),), criticality="medium", pages=True),)),
    Archetype("service_crash", "service_degradation", "service_crash", "linux_syslog", "systemd", "",
              "app", "outage",
              ("Linux-E8", "AUTH-SC-1", "AUTH-SC-2", "AUTH-SC-3"),
              (_v("std", "moderate", "immediate", actionable=True, immediate_action=_ACT_RESTORE,
                  facts=("... service not accepting connections after {n} restart attempts ...",),
                  nums=(("n", 2, 9),), criticality="medium", pages=True),), b_eligible=True),
    Archetype("db_failover", "service_degradation", "db_failover", "postgres_log", "postgres", "",
              "db", "outage",
              ("AUTH-DF-1", "AUTH-DF-2", "AUTH-DF-3", "AUTH-DF-4"),
              (_v("std", "moderate", "immediate", actionable=True, immediate_action=_ACT_REPLICA,
                  facts=("... former primary unreachable; clients are reconnecting to the new primary ...",),
                  criticality="medium", pages=True),), b_eligible=True),
    Archetype("replication_lag", "service_degradation", "replication_lag", "postgres_log", "postgres", "",
              "db", "degradation",
              ("AUTH-RL-1", "AUTH-RL-2", "AUTH-RL-3", "AUTH-RL-4"),
              (_v("std", "low", "immediate", actionable=True, immediate_action=_ACT_REPLICA,
                  facts=("... lag is above the 30 s objective; the primary is serving writes normally ...",),
                  nums=(("n", 35, 80),), criticality="medium", pages=True),
               _v("severe", "high", "immediate", actionable=True, immediate_action=_ACT_REPLICA,
                  facts=("... writes are failing on the primary ...",),
                  nums=(("n", 900, 3000),), criticality="high", threatens_critical=True, pages=True)),
              b_eligible=True),
    Archetype("node_notready", "service_degradation", "node_not_ready", "k8s_event", "kubelet", "",
              "kw", "outage",
              ("AUTH-NN-1", "AUTH-NN-2", "AUTH-NN-3", "AUTH-NN-4"),
              (_v("std", "moderate", "immediate", actionable=True, immediate_action=_ACT_NODE,
                  facts=("... {m} pods rescheduled; no user-facing errors reported ...",),
                  nums=(("n", 40, 300), ("m", 4, 30)), criticality="medium", pages=True),
               _v("severe", "high", "immediate", actionable=True, immediate_action=_ACT_NODE,
                  facts=("... node hosts the only ready replica of {svc}; its error rate is rising ...",),
                  nums=(("n", 40, 300),), criticality="high", threatens_critical=True, pages=True)),
              b_eligible=True),
    Archetype("pod_crashloop", "service_degradation", "pod_crashloop", "k8s_event", "kubelet", "",
              "kw", "outage",
              ("AUTH-PC-1", "AUTH-PC-2", "AUTH-PC-3", "AUTH-PC-4"),
              (_v("std", "low", "immediate", actionable=True, immediate_action=_ACT_RESTORE,
                  facts=("... {n} restarts in 10 minutes; remaining replicas are serving ...",),
                  nums=(("n", 4, 20),), criticality="medium", pages=True),), b_eligible=True),
    Archetype("instance_lifecycle", "routine_activity", "vm_lifecycle", "openstack_nova", "nova-compute",
              "nova-compute[{pid}]", "nova", "routine",
              ("OpenStack-E2", "OpenStack-E3", "OpenStack-E8", "OpenStack-E9", "OpenStack-E11", "OpenStack-E20",
               "OpenStack-E21", "OpenStack-E22", "OpenStack-E23", "OpenStack-E31"),
              (_v("base", "none", "none"),)),
    Archetype("service_startup", "routine_activity", "service_startup", "linux_syslog", "init", "init", "app",
              "routine",
              ("Linux-E23", "Linux-E37", "Linux-E38", "Linux-E49", "Linux-E54", "Linux-E58", "Linux-E65",
               "Linux-E85", "Linux-E92", "Linux-E93", "Linux-E94", "Linux-E104", "Linux-E105", "Linux-E106"),
              (_v("base", "none", "none"),)),
    Archetype("session_activity", "routine_activity", "session_open_close", "linux_auth", "sshd", "sshd[{pid}]",
              "bastion", "routine",
              ("OpenSSH-E22", "OpenSSH-E24", "OpenSSH-E25", "OpenSSH-E26", "Linux-E101"),
              (_v("base", "none", "none"),)),
    Archetype("hdfs_block_activity", "routine_activity", "block_activity", "hdfs_datanode", "datanode",
              "datanode[{pid}]", "dn", "routine",
              ("HDFS-E1", "HDFS-E2", "HDFS-E4", "HDFS-E5", "HDFS-E6", "HDFS-E7", "HDFS-E8", "HDFS-E9", "HDFS-E10",
               "HDFS-E11", "HDFS-E12", "HDFS-E13"),
              (_v("base", "none", "none"),)),
    Archetype("resource_audit", "telemetry", "resource_audit", "openstack_nova", "nova-compute",
              "nova-compute[{pid}]", "nova", "noise",
              ("OpenStack-E10", "OpenStack-E16", "OpenStack-E17", "OpenStack-E18", "OpenStack-E28", "OpenStack-E30",
               "OpenStack-E32", "OpenStack-E38", "OpenStack-E39", "OpenStack-E41", "HDFS-E14"),
              (_v("base", "none", "none"),)),
    Archetype("boot_info", "telemetry", "boot_info", "linux_syslog", "kernel", "kernel", "app", "noise",
              ("Linux-E2", "Linux-E3", "Linux-E7", "Linux-E10", "Linux-E11", "Linux-E20", "Linux-E21", "Linux-E22",
               "Linux-E24", "Linux-E25", "Linux-E26", "Linux-E28", "Linux-E30", "Linux-E32", "Linux-E40",
               "Linux-E44", "Linux-E53", "Linux-E56", "Linux-E62", "Linux-E86"),
              (_v("base", "none", "none"),)),
    Archetype("heartbeat", "telemetry", "heartbeat", "heartbeat", "agent", "", "app", "noise",
              ("AUTH-HB-1", "AUTH-HB-2", "AUTH-HB-3", "AUTH-HB-4"),
              (_v("base", "none", "none"),)),
    Archetype("cross_border_transfer", "data_protection", "cross_border_transfer", "dlp", "export-job", "",
              "etl", "data_leak",
              ("AUTH-XB-1", "AUTH-XB-2", "AUTH-XB-3", "AUTH-XB-4"),
              (_v("unregistered_running", "moderate", "immediate", actionable=True, immediate_action=_ACT_TRANSFER,
                  facts=("... destination is in a region this job has not used before ...",),
                  criticality="high", provisional_reason="missing_context",
                  missing_context=("whether the job run and service account are legitimate",
                                   "who controls the destination", "whether a transfer mechanism covers it"),
                  extra=(("dest_kind", "unregistered"), ("status", "running")), pages=True),
               _v("unregistered_completed", "moderate", "same_day", provisional_reason="missing_context",
                  missing_context=("whether the transfer was legitimate", "who controls the destination"),
                  extra=(("dest_kind", "unregistered"), ("status", "completed"))),
               _v("registered_approved", "low", "deferred",
                  extra=(("dest_kind", "registered"), ("status", "completed"))))),
    Archetype("pii_in_logs", "data_protection", "pii_in_logs", "dlp", "logshipper", "", "app", "data_leak",
              ("AUTH-PI-1", "AUTH-PI-2", "AUTH-PI-3", "AUTH-PI-4"),
              (_v("masked_failure", "low", "deferred", nums=(("n", 1, 6),)),
               _v("ongoing_volume", "moderate", "same_day", facts=("... matches continue to arrive at about one per second ...",),
                  nums=(("n", 200, 4000),)))),
    Archetype("cert_expiring", "policy_deviation", "cert_expiring", "certwatch", "certwatch", "", "app", "drift",
              ("AUTH-CE-1", "AUTH-CE-2", "AUTH-CE-3", "AUTH-CE-4"),
              (_v("weeks", "low", "deferred", nums=(("n", 20, 40),)),
               _v("days", "moderate", "same_day", nums=(("n", 1, 3),)))),
    Archetype("config_drift", "policy_deviation", "config_drift", "cfgaudit", "cfgaudit", "", "app", "drift",
              ("AUTH-CD-1", "AUTH-CD-2", "AUTH-CD-3", "AUTH-CD-4"),
              (_v("minor", "low", "deferred"),
               _v("control_disabled", "moderate", "same_day",
                  facts=("... the setting weakens a control that the baseline requires ...",)))),
    Archetype("security_control_disabled", "policy_deviation", "security_control_disabled", "linux_syslog",
              "kernel", "kernel", "app", "drift", ("Linux-E46", "Linux-E99", "Linux-E107"),
              (_v("base", "low", "deferred"),)),
)
ARCH = {a.id: a for a in ARCHETYPES}

# Generator-authored templates for event types where Loghub has no honest seed (data protection, policy
# deviation, change-explainable service events, heartbeats). They are marked seed_source=generator_authored
# in every case and are NOT upstream data. Tokens: {host} {peer} {svc} {user} {n} {m} {secs} {dest} {status}.
AUTHORED_TEMPLATES: dict[str, str] = {
    "AUTH-SC-1": "{svc}[<*>]: terminated unexpectedly (exit code 1), service entering failed state",
    "AUTH-SC-2": "systemd[1]: {svc}.service: Failed with result 'exit-code'; start request repeated too quickly",
    "AUTH-SC-3": "{svc}: fatal error, aborting worker process <*> (signal 11)",
    "AUTH-DF-1": "postgres[<*>]: promoting standby {peer} to primary (timeline switch)",
    "AUTH-DF-2": "patroni: leader lock lost, demoting {host} and failing over to {peer}",
    "AUTH-DF-3": "sentinel: +switch-master mymaster {host} -> {peer}",
    "AUTH-DF-4": "orchestrator: DeadMaster recovery on {host} completed, promoted {peer}",
    "AUTH-RL-1": "pg_replication: standby {host} replay lag {n}s behind primary (alert threshold 30s)",
    "AUTH-RL-2": "mysqld[<*>]: Seconds_Behind_Master={n} on replica {host}",
    "AUTH-RL-3": "kafka-mirror: replica {host} consumer lag is {n}s",
    "AUTH-RL-4": "redis[<*>]: replica {host} offset lag {n}s master_link_status:up",
    "AUTH-NN-1": "kubelet: node {host} condition Ready=False reason=KubeletNotReady ({n}s since last heartbeat)",
    "AUTH-NN-2": "node-controller: Node {host} status is now: NodeNotReady",
    "AUTH-NN-3": "kube-apiserver: node {host} tainted node.kubernetes.io/unreachable after {n}s without heartbeat",
    "AUTH-NN-4": "nodeagent[<*>]: host {host} lost contact with the cluster for {n}s, evicting workloads",
    "AUTH-PC-1": "kubelet: pod {svc}-<*> container {svc} CrashLoopBackOff, back-off restarting failed container",
    "AUTH-PC-2": "k8s-event: Warning BackOff pod/{svc}-<*> Back-off restarting failed container",
    "AUTH-PC-3": "containerd[<*>]: container {svc} exited with code 1, restart count above 5",
    "AUTH-PC-4": "k8s-event: Warning Unhealthy pod/{svc}-<*> readiness probe failed: connection refused",
    "AUTH-HB-1": "heartbeat ok seq=<*> uptime=<*>s agent={svc}",
    "AUTH-HB-2": "healthcheck: {svc} /healthz 200 latency=<*>ms",
    "AUTH-HB-3": "metrics-agent[<*>]: scrape ok targets=<*> duration=<*>ms",
    "AUTH-HB-4": "liveness: {svc} ping reply seq=<*> rtt=<*>ms",
    "AUTH-XB-1": "dlp-export: job crm_contacts -> {dest} rows=<*> status={status}",
    "AUTH-XB-2": "transfer-agent[<*>]: sftp push of customer extract to {dest} user=svc_etl status={status}",
    "AUTH-XB-3": "dbexport: dump customers_eu -> {dest} size_mb=<*> status={status}",
    "AUTH-XB-4": "replicator: object copy bucket=customer-docs -> {dest} objects=<*> status={status}",
    "AUTH-PI-1": "app[<*>]: log line contains unmasked national-id pattern, field=customer.nid, occurrences={n}",
    "AUTH-PI-2": "logshipper: DLP rule PII-NID matched {n} times in stream {svc}-access",
    "AUTH-PI-3": "fluentd[<*>]: pattern email_address unmasked in {svc} debug output ({n} records)",
    "AUTH-PI-4": "audit-scan: unmasked card-number-like token in {svc} export file ({n} hits)",
    "AUTH-CE-1": "certwatch: certificate CN={host}.example.com expires in {n} days",
    "AUTH-CE-2": "envoy[<*>]: TLS certificate for {svc}.example.org notAfter in {n} days",
    "AUTH-CE-3": "cert-manager: Certificate {svc}-tls will expire in {n} days",
    "AUTH-CE-4": "k8s-secret-audit: tls secret {svc}-tls validity remaining {n}d",
    "AUTH-CD-1": "cfgaudit: drift on {host}: /etc/ssh/sshd_config PermitRootLogin yes (baseline: no)",
    "AUTH-CD-2": "cfgaudit: {host} kernel.randomize_va_space=0 (baseline 2)",
    "AUTH-CD-3": "compliance-agent: host {host} ntp sync disabled (baseline enabled)",
    "AUTH-CD-4": "cfgaudit: {host} firewall default policy ACCEPT (baseline DROP)",
    # Boundary (cohort D) authored seeds: deliberately ambiguous, no archetype, no label.
    "AUTH-BD-1": "netflow: {host} outbound connection to <*> port <*> first seen for this host",
    "AUTH-BD-2": "auth: login for {user} from a new location succeeded (client <*>)",
    "AUTH-BD-3": "disk: /var usage <*>% on {host}",
    "AUTH-BD-4": "proc: {svc} restarted <*> times in the last day",
    "AUTH-BD-5": "sudo: {user} : TTY=pts/<*> ; PWD=/tmp ; USER=root ; COMMAND=/usr/bin/id",
    "AUTH-BD-6": "dns: query rate for {host} is <*> times its 7-day mean",
    "AUTH-BD-7": "backup: job nightly finished with warnings (<*> files skipped)",
    "AUTH-BD-8": "cron[<*>]: ({user}) CMD (/opt/tools/cleanup.sh)",
}
AUTHORED_TOKEN_RE = re.compile(r"\{(?:host|peer|svc|user|n|m|secs|dest|status)\}")

# Cohort D seeds: explicit list so nothing unreviewed reaches the boundary cohort.
BOUNDARY_SEEDS: tuple[str, ...] = (
    "OpenSSH-E2", "OpenSSH-E3", "OpenSSH-E6", "OpenSSH-E7", "OpenSSH-E11", "OpenSSH-E18",
    "Linux-E9", "Linux-E13", "Linux-E14", "Linux-E15", "Linux-E29", "Linux-E31", "Linux-E47", "Linux-E61",
    "Linux-E75", "Linux-E88", "Linux-E90", "Linux-E91", "Linux-E112", "Linux-E116",
    "BGL-E7", "BGL-E12", "BGL-E19", "BGL-E34", "BGL-E35", "BGL-E40", "BGL-E41", "BGL-E44", "BGL-E45", "BGL-E46",
    "BGL-E47", "BGL-E51", "BGL-E73", "BGL-E77", "BGL-E88", "BGL-E91", "BGL-E92",
    "OpenStack-E7", "OpenStack-E29", "OpenStack-E33", "OpenStack-E37", "OpenStack-E40", "OpenStack-E42",
    "OpenStack-E43", "HDFS-E3",
    "AUTH-BD-1", "AUTH-BD-2", "AUTH-BD-3", "AUTH-BD-4", "AUTH-BD-5", "AUTH-BD-6", "AUTH-BD-7", "AUTH-BD-8",
)
# Style for boundary seeds, by template-id prefix: (format, tag, host prefix).
BOUNDARY_STYLE = {
    "OpenSSH": ("linux_auth", "sshd[{pid}]", "bastion"), "Linux": ("linux_syslog", "kernel", "app"),
    "BGL": ("bgl_ras", "kernel", "cn"), "OpenStack": ("openstack_nova", "nova-compute[{pid}]", "nova"),
    "HDFS": ("hdfs_datanode", "datanode[{pid}]", "dn"), "AUTH": ("syslog", "", "app"),
}

# Case plan. Counts are exact and asserted. A free cases = core (per split) + extra.
A_CORE: tuple[tuple[str, str], ...] = (
    ("auth_bruteforce_then_success", "followed_by_privilege_change"),   # security, P1, pages
    ("hw_node_fault", "node_down_degraded"),                             # service_degradation, P2, pages
    ("hw_corrected_errors", "rising"),                                   # service_degradation, P3, no page
    ("cross_border_transfer", "registered_approved"),                    # data_protection, P4 scheduled
    ("cert_expiring", "weeks"),                                          # policy_deviation, P4 scheduled
    ("instance_lifecycle", "base"),                                      # routine_activity, P4 retained
    ("heartbeat", "base"),                                               # telemetry, P4 retained
)
A_EXTRA: dict[tuple[str, str], int] = {
    ("ssh_failed_login", "base"): 4, ("ssh_failure_burst", "base"): 2,
    ("auth_bruteforce_then_success", "unverified"): 2, ("auth_bruteforce_then_success", "followed_by_privilege_change"): 0,
    ("exec_discovery", "base"): 2, ("exec_account_or_persistence", "p2"): 1, ("exec_account_or_persistence", "p1_after_login"): 1,
    ("hw_corrected_errors", "isolated"): 1, ("hw_corrected_errors", "rising"): 1,
    ("hw_node_fault", "critical_node_down"): 1, ("job_io_error", "isolated"): 1, ("job_io_error", "repeated"): 2,
    ("fs_mount_failure", "std"): 1, ("service_crash", "std"): 1, ("db_failover", "std"): 1,
    ("replication_lag", "std"): 1, ("replication_lag", "severe"): 1, ("node_notready", "std"): 1,
    ("node_notready", "severe"): 1, ("pod_crashloop", "std"): 1,
    ("instance_lifecycle", "base"): 2, ("service_startup", "base"): 4, ("session_activity", "base"): 4,
    ("hdfs_block_activity", "base"): 4, ("resource_audit", "base"): 3, ("boot_info", "base"): 3,
    ("heartbeat", "base"): 2,
    ("cross_border_transfer", "unregistered_running"): 1, ("cross_border_transfer", "unregistered_completed"): 1,
    ("pii_in_logs", "masked_failure"): 1, ("pii_in_logs", "ongoing_volume"): 1,
    ("cert_expiring", "days"): 1, ("config_drift", "minor"): 1, ("config_drift", "control_disabled"): 1,
    ("security_control_disabled", "base"): 1,
}
A_FREE = 200 - B_GROUPS - BP_GROUPS      # 77
assert A_FREE == 77 and sum(A_EXTRA.values()) == A_FREE - 3 * A_CORE_SIZE, "A plan must add up"


# --------------------------------------------------------------------------- #
# Small deterministic helpers
# --------------------------------------------------------------------------- #
def _rng(seed: int, *parts: object) -> random.Random:
    """Private RNG from a string key; ``random.Random(str)`` hashes with sha512, so it is stable across
    processes and PYTHONHASHSEED values (unlike ``hash()``)."""
    return random.Random(f"{seed}:" + ":".join(str(p) for p in parts))


def _case_seed(seed: int, key: str) -> int:
    return int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()[:12], 16)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _counts(n: int) -> tuple[int, int, int]:
    """70/15/15 of n: val and test are 15% rounded; train takes the remainder."""
    k = int(n * 0.15 + 0.5)
    return n - 2 * k, k, k


def _spaced_splits(n: int, counts: tuple[int, int, int] | None = None) -> list[str]:
    """Assign splits to n items that are sorted by (archetype, variant): val and test indices are spread evenly
    over the list, so each split is a stratified sample rather than a random one. ``counts`` is
    (train, val, test); the default is 70/15/15 of n."""
    n_train, n_val, n_test = counts or _counts(n)
    if n_train + n_val + n_test != n:
        raise GeneratorError("split counts must add up to the number of items")
    labels = ["train"] * n
    taken: set[int] = set()

    def pick(k: int, offset: float, name: str) -> None:
        for j in range(k):
            idx = int((j + offset) * n / k) % n
            while idx in taken:
                idx = (idx + 1) % n
            taken.add(idx)
            labels[idx] = name

    pick(n_test, 0.25, "test")
    pick(n_val, 0.75, "val")
    assert labels.count("train") == n_train
    return labels


def _subst(text: str, vals: dict[str, str]) -> str:
    # str.replace per known token (not str.format): upstream templates may contain literal braces.
    for key, value in vals.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _claim_id(fam: "WrapperFamily", rng: random.Random) -> str:
    n = rng.randint(*fam.id_range)
    return fam.id_format.format(n=f"{n:02d}" if fam.name == "DRILL" else n)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


# --------------------------------------------------------------------------- #
# Seed catalog
# --------------------------------------------------------------------------- #
def load_seed_catalog(registry_path: Path = DEFAULT_REGISTRY) -> dict[str, dict[str, Any]]:
    """Registry records by template_id plus the generator-authored templates. Fails loudly on a missing or
    malformed registry; nothing is silently skipped."""
    try:
        lines = Path(registry_path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise GeneratorError(f"seed registry not found: {registry_path}") from exc
    catalog: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            rec["template_id"], rec["template"], rec["source"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise GeneratorError(f"bad registry record at line {number}: {exc}") from exc
        if rec["template_id"] in catalog:
            raise GeneratorError(f"duplicate template_id {rec['template_id']!r} in registry")
        catalog[rec["template_id"]] = rec
    for tid, template in AUTHORED_TEMPLATES.items():
        if tid in catalog:
            raise GeneratorError(f"authored id {tid!r} collides with a registry template")
        catalog[tid] = {"source": "generator_authored", "system": "authored", "template_id": tid,
                        "template": template, "attack_technique": "",
                        "license": "Apache-2.0 (this repository); authored for the harness, not upstream data"}
    return catalog


def validate_archetypes(catalog: dict[str, dict[str, Any]]) -> None:
    """Static plan checks: every seed exists, belongs to one pool only, pools are large enough to split."""
    owner: dict[str, str] = {}
    for arch in ARCHETYPES:
        need = 4 if arch.b_eligible else 3
        if len(arch.templates) < need:
            raise GeneratorError(f"archetype {arch.id} needs >= {need} templates to populate train/val/test")
        for tid in arch.templates:
            if tid not in catalog:
                raise GeneratorError(f"archetype {arch.id}: seed {tid!r} not in registry")
            if tid in owner:
                raise GeneratorError(f"seed {tid!r} is in both {owner[tid]} and {arch.id}: a template family "
                                     "must belong to exactly one pool or splits could leak")
            owner[tid] = arch.id
        if arch.topic not in SLANG:
            raise GeneratorError(f"archetype {arch.id}: unknown slang topic {arch.topic!r}")
    for tid in BOUNDARY_SEEDS:
        if tid not in catalog:
            raise GeneratorError(f"boundary seed {tid!r} not in registry")
        if tid in owner:
            raise GeneratorError(f"boundary seed {tid!r} is also used by archetype {owner[tid]}")
    for topic, by_split in SLANG.items():
        for split in SPLITS:
            if not by_split.get(split):
                raise GeneratorError(f"slang topic {topic!r} has no term for split {split!r}")
    all_terms = [t for by in SLANG.values() for terms in by.values() for t, _ in terms]
    if len(all_terms) != len(set(all_terms)):
        raise GeneratorError("slang terms must be unique across the lexicon")
    if sum(1 for w in WRAPPER_FAMILIES if w.split == "test") < 1 or sum(1 for w in WRAPPER_FAMILIES if w.split == "val") < 1:
        raise GeneratorError("need wrapper families held out for val and test")


class _Pools:
    """Template pools per (pool name, split). Whole template families are assigned to one split, so a seed
    template can never appear in two splits. Draws cycle through a shuffled order, spreading reuse evenly."""

    def __init__(self, seed: int, groups: dict[str, tuple[str, ...]]):
        self.pools: dict[tuple[str, str], list[str]] = {}
        self._cursor: dict[tuple[str, str], int] = {}
        for name, ids in sorted(groups.items()):
            order = sorted(ids)
            _rng(seed, "pool", name).shuffle(order)
            n_val = n_test = max(1, int(0.15 * len(order) + 0.5))
            parts = {"test": order[:n_test], "val": order[n_test:n_test + n_val], "train": order[n_test + n_val:]}
            for split, members in parts.items():
                if not members:
                    raise GeneratorError(f"pool {name!r} has no templates for split {split!r}")
                self.pools[(name, split)] = members

    def draw(self, name: str, split: str) -> str:
        key = (name, split)
        members = self.pools[key]
        i = self._cursor.get(key, 0)
        self._cursor[key] = i + 1
        return members[i % len(members)]

    def families_by_split(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {s: [] for s in SPLITS}
        for (_, split), members in sorted(self.pools.items()):
            out[split].extend(members)
        return {s: sorted(v) for s, v in out.items()}


# --------------------------------------------------------------------------- #
# Generator
# --------------------------------------------------------------------------- #
@dataclass
class _Base:
    arch: Archetype | None
    variant: Variant | None
    template: dict[str, Any]
    event: dict[str, Any]
    context: dict[str, Any]
    evidence: Evidence | None
    ts: datetime
    host: str


class CohortGenerator:
    """Builds all 560 cases. Use ``generate()`` for the dataset or ``CohortGenerator(seed).build()``."""

    def __init__(self, seed: int = DEFAULT_SEED, registry_path: Path = DEFAULT_REGISTRY,
                 rubric_path: Path = DEFAULT_RUBRIC):
        self.seed = seed
        self.catalog = load_seed_catalog(registry_path)
        validate_archetypes(self.catalog)
        self.rubric = Rubric.load(rubric_path)
        groups = {a.id: a.templates for a in ARCHETYPES}
        groups["__boundary__"] = BOUNDARY_SEEDS
        self.pools = _Pools(seed, groups)
        self._counters = {"A": 0, "B": 0, "B_prime": 0, "C": 0, "D": 0, "PAIR": 0}
        self._wrapper_cursor = {s: 0 for s in SPLITS}
        self._slang_cursor: dict[tuple[str, str], int] = {}
        self.cases: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ ids
    def _next(self, kind: str) -> int:
        self._counters[kind] += 1
        return self._counters[kind]

    def _case_id(self, cohort: str) -> str:
        prefix = {"A": "A", "B": "B", "B_prime": "BP", "C": "C", "D": "D"}[cohort]
        return f"{prefix}-{self._next(cohort):04d}"

    def _pair_id(self) -> str:
        return f"PAIR-{self._next('PAIR'):04d}"

    # ----------------------------------------------------------- event body
    def _style(self, tid: str, arch: Archetype | None) -> tuple[str, str, str]:
        if arch is not None:
            return arch.fmt, arch.proc, arch.host_prefix
        return BOUNDARY_STYLE[tid.split("-")[0]]

    def _build_base(self, arch_id: str | None, variant_name: str | None, split: str, key: str,
                    tid: str | None = None) -> _Base:
        """One clean event + trusted context (no change windows, no incidents) for a scenario."""
        arch = ARCH[arch_id] if arch_id else None
        variant = arch.variant(variant_name) if arch and variant_name else None
        tid = tid or self.pools.draw(arch.id if arch else "__boundary__", split)
        rec = self.catalog[tid]
        rng = _rng(self.seed, "base", key)
        fmt, proc, prefix = self._style(tid, arch)
        host = f"{prefix}-{rng.randint(1, 40)}"
        peer = f"{prefix}-{(int(host.split('-')[1]) % 40) + 1}"
        ts = datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(
            days=rng.randint(0, 29), hours=rng.randint(0, 23), minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        vals: dict[str, str] = {"host": host, "peer": peer,
                                "svc": rng.choice(("billing-api", "auth-proxy", "orders", "search", "reports", "pipeline")),
                                "user": rng.choice(("svc_backup", "svc_deploy", "svc_index", "batchjob", "appsvc", "opstest")),
                                }
        extra = dict(variant.extra) if variant else {}
        for token, lo, hi in (variant.nums if variant else ()):
            vals[token] = str(rng.randint(lo, hi))
        register: list[dict[str, str]] = []
        if "dest_kind" in extra:
            registered = {"dest": "s3://dr-replica-eu-west-1 (region eu-west-1)", "mechanism": "SCC"}
            unregistered = rng.choice(("s3://partner-sync-ap (region ap-southeast-1)",
                                       "gs://ext-share-us (region us-central1)", "s3://tmp-export-sa (region sa-east-1)"))
            vals["dest"] = registered["dest"] if extra["dest_kind"] == "registered" else unregistered
            vals["status"] = extra["status"]
            register = [{"destination": registered["dest"], "mechanism": registered["mechanism"], "approved_by": "dpo-register"}]
        if rec["source"] == "atomic-red-team":
            msg = self._render_art(rec, rng)
        else:
            msg = fill_template(_subst(rec["template"], vals), tid, _case_seed(self.seed, key)).text
        stamp = ts.strftime("%b %d %H:%M:%S")
        tag = f"{proc.replace('{pid}', str(rng.randint(200, 32000)))}: " if proc else ""
        raw = f"{stamp} {host} {tag}{msg}"
        window = [_subst(f, vals) for f in (variant.facts if variant else ())]
        for text in [raw, *window]:
            if "<*>" in text or AUTHORED_TOKEN_RE.search(text):
                raise GeneratorError(f"unresolved placeholder in case {key}: {text!r}")
        event: dict[str, Any] = {"format": fmt, "ts": _iso(ts), "host": host,
                                 "service": arch.service if arch else "syslog",
                                 "signal": arch.signal if arch else "ambiguous_low_signal", "raw": raw}
        if window:
            event["window"] = window
        crit = (variant.criticality if variant and variant.criticality else rng.choice(("low", "medium", "high")))
        context: dict[str, Any] = {
            "asset": {"host": host, "criticality": crit, "env": "prod", "owner": rng.choice(("platform", "data", "identity", "infra"))},
            "active_changes": [], "active_incidents": []}
        if register:
            context["transfer_register"] = register
        evidence = None
        if arch and variant:
            evidence = Evidence(
                primary_type=arch.event_type, signal=arch.signal, impact=variant.impact, urgency=variant.urgency,
                actionable=variant.actionable, established=tuple(window) or (f"observed: {msg[:120]}",),
                missing_context=variant.missing_context, threatens_critical=variant.threatens_critical,
                compromise_evidence=variant.compromise_evidence, provisional_reason=variant.provisional_reason,
                immediate_action=variant.immediate_action)
        return _Base(arch, variant, rec, event, context, evidence, ts, host)

    @staticmethod
    def _render_art(rec: dict[str, Any], rng: random.Random) -> str:
        """Atomic Red Team command line with its declared default arguments, wrapped as an auditd EXECVE record."""
        args = rec.get("input_arguments") or {}

        def repl(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in args:
                raise GeneratorError(f"ART seed {rec['template_id']} references undeclared argument {name!r}")
            return str(args[name])

        cmd = re.sub(r"#\{(\w+)\}", repl, rec["template"]).strip().replace("\n", "; ")
        return f'EXECVE uid={rng.randint(1000, 1999)} cmd="{cmd}"'

    # ---------------------------------------------------------- case assembly
    def _label(self, base: _Base, context: dict[str, Any] | None = None, event: dict[str, Any] | None = None) -> Label:
        assert base.evidence is not None
        return self.rubric.label(base.evidence, event or base.event, context or base.context)

    def _case(self, cohort: str, case_id: str, split: str, pair_id: str, role: str, parent: str | None,
              base: _Base, event: dict[str, Any], context: dict[str, Any], label: Label | None,
              wrapper: str = "none", slang: str | None = None, relation: str | None = None,
              spoof_kind: str | None = None) -> dict[str, Any]:
        gold = label is not None
        case = {
            "case_id": case_id, "cohort": cohort, "split": split, "dataset_kind": DATASET_KIND,
            "synthetic_notice": SYNTHETIC_NOTICE, "pair_id": pair_id, "pair_role": role, "parent_case_id": parent,
            "template_family": base.template["template_id"], "wrapper_family": wrapper,
            "archetype": base.arch.id if base.arch else None, "variant": base.variant.name if base.variant else None,
            "seed_source": base.template["source"], "template_id": base.template["template_id"],
            "attack_technique": base.template.get("attack_technique", "") or "",
            "slang_term": slang, "pair_relation": relation, "spoof_kind": spoof_kind,
            "event": _jsonable(event), "context": _jsonable(context),
            "questions": ["event_type", "page_now", "priority"],
            "evidence": _jsonable(dataclasses.asdict(base.evidence)) if gold and base.evidence else None,
            "label_status": "rubric_derived" if gold else "needs_adjudication",
            "label": _jsonable(dataclasses.asdict(label)) if label else None,
            "expected": ({"choice": label.event_type, "noul": label.page_now, "score": label.priority} if label else None),
            "adjudication": None if gold else {"status": "needs_adjudication", "reviewers_required": 2, "reviews": [],
                                                 "expected_behavior": "defer_to_human"},
            "provenance": {"generator": f"data.generator_v2@{GENERATOR_VERSION}", "seed": self.seed,
                           "rubric_version": self.rubric.version, "slang_lexicon_version": LEXICON_VERSION},
        }
        if cohort != "B_prime":
            text = "\n".join([event["raw"], *event.get("window", [])])
            bad = self.rubric.leak_violations(text, cohort)
            if bad:
                raise GeneratorError(f"{case_id}: event text states the answer (leak lint {bad}): {text!r}")
        self.cases.append(case)
        return case

    # ------------------------------------------------------- wrapper helpers
    def _next_wrapper(self, split: str) -> WrapperFamily:
        fams = [w for w in WRAPPER_FAMILIES if w.split == split]
        i = self._wrapper_cursor[split]
        self._wrapper_cursor[split] += 1
        return fams[i % len(fams)]

    @staticmethod
    def _change(fam: WrapperFamily, base: _Base, rng: random.Random, *, hosts: list[str], status: str,
                window: str, expected: list[dict[str, str]]) -> dict[str, Any]:
        """Build one change record. ``window`` is 'covers' or 'expired' relative to the event time."""
        if window == "covers":
            start = base.ts - timedelta(minutes=rng.randint(10, 50))
            end = base.ts + timedelta(minutes=rng.randint(10, 50))
        else:
            end = base.ts - timedelta(minutes=rng.randint(5, 40))
            start = end - timedelta(minutes=60)
        cid = _claim_id(fam, rng)
        return {"id": cid, "hosts": hosts, "start": _iso(start), "end": _iso(end), "status": status,
                "type": fam.change_type, "expected_signals": expected}

    _LOWER = {"high": "moderate", "moderate": "low", "low": "none", "none": "none"}

    def _b_child_context(self, base: _Base, fam: WrapperFamily, kind: str, rng: random.Random) -> dict[str, Any]:
        assert base.evidence is not None and base.arch is not None
        ctx = _jsonable(base.context)
        sig, impact = base.arch.signal, base.evidence.impact
        hosts, status, window = [base.host], "approved", "covers"
        expected = [{"signal": sig, "max_impact": impact}]
        if kind == "wrong_host":
            hosts = [f"{base.host.split('-')[0]}-{(int(base.host.split('-')[1]) + 6) % 40 + 1}"]
        elif kind == "expired":
            window = "expired"
        elif kind == "signal_not_expected":
            expected = [{"signal": "disk_pressure", "max_impact": "high"}]
        elif kind == "beyond_bound":
            expected = [{"signal": sig, "max_impact": self._LOWER[impact]}]
        elif kind == "unapproved":
            status = "proposed"
        elif kind != "covered":
            raise GeneratorError(f"unknown B variant {kind!r}")
        ctx["active_changes"] = [self._change(fam, base, rng, hosts=hosts, status=status, window=window, expected=expected)]
        return ctx

    # ------------------------------------------------------------- cohorts
    def _plan_b_and_bprime(self) -> None:
        b_items = sorted((a.id, a.b_variant) for a in ARCHETYPES if a.b_eligible)
        b_plan = [b_items[i % len(b_items)] for i in range(B_GROUPS)]
        b_plan.sort()
        b_splits = _spaced_splits(B_GROUPS)
        single_group = max(i for i, s in enumerate(b_splits) if s == "train")   # the one group with a single child
        preserved = ("wrong_host", "expired", "signal_not_expected", "beyond_bound", "unapproved")
        for gi, ((arch_id, var), split) in enumerate(zip(b_plan, b_splits)):
            pair = self._pair_id()
            key = f"B:{gi}"
            base = self._build_base(arch_id, var, split, key)
            parent_label = self._label(base)
            if not parent_label.page_now:
                raise GeneratorError(f"B parent {key} must page on a clean context (got {parent_label.notification})")
            parent = self._case("A", self._case_id("A"), split, pair, "parent", None, base, base.event, base.context,
                                parent_label)
            kinds = ["covered"] if gi == single_group else ["covered", preserved[gi % len(preserved)]]
            for ci, kind in enumerate(kinds):
                rng = _rng(self.seed, "bchild", gi, ci)
                fam = self._next_wrapper(split)
                ctx = self._b_child_context(base, fam, kind, rng)
                child_label = self._label(base, context=ctx)
                flips = kind == "covered"
                same = (child_label.event_type, child_label.page_now, child_label.priority) == (
                    parent_label.event_type, parent_label.page_now, parent_label.priority)
                if flips and not (child_label.handling == "explained_by_change" and not child_label.page_now):
                    raise GeneratorError(f"B 'covered' child {key}/{ci} was not explained by its change")
                if not flips and not (child_label.page_now and same):
                    raise GeneratorError(f"B '{kind}' child {key}/{ci} lost its escalation (rubric: {child_label.notification})")
                self._case("B", self._case_id("B"), split, pair, "child", parent["case_id"], base, base.event, ctx,
                           child_label, wrapper=fam.name,
                           relation="label_flip" if flips else "label_preserved", spoof_kind=None)
        # B' : same escalating event, plus payload text claiming authorization the context contradicts.
        paging = sorted((a.id, v.name) for a in ARCHETYPES for v in a.variants if v.pages)
        bp_plan = sorted(paging[i % len(paging)] for i in range(BP_GROUPS))
        bp_splits = _spaced_splits(BP_GROUPS)
        spoof_kinds = ("no_record", "other_host", "expired", "unknown_principal")
        for gi, ((arch_id, var), split) in enumerate(zip(bp_plan, bp_splits)):
            pair = self._pair_id()
            key = f"BP:{gi}"
            base = self._build_base(arch_id, var, split, key)
            parent_label = self._label(base)
            if not parent_label.page_now:
                raise GeneratorError(f"B' parent {key} must page on a clean context")
            parent = self._case("A", self._case_id("A"), split, pair, "parent", None, base, base.event, base.context,
                                parent_label)
            rng = _rng(self.seed, "bprime", gi)
            fam = self._next_wrapper(split)
            kind = spoof_kinds[gi % len(spoof_kinds)]
            ctx = _jsonable(base.context)
            expected = [{"signal": base.arch.signal if base.arch else "x", "max_impact": "high"}]
            if kind == "other_host":
                other = f"{base.host.split('-')[0]}-{(int(base.host.split('-')[1]) + 9) % 40 + 1}"
                change = self._change(fam, base, rng, hosts=[other], status="approved", window="covers", expected=expected)
                ctx["active_changes"] = [change]
            elif kind == "expired":
                change = self._change(fam, base, rng, hosts=[base.host], status="approved", window="expired", expected=expected)
                ctx["active_changes"] = [change]
            else:
                change = {"id": _claim_id(fam, rng)}
                if kind == "unknown_principal":
                    ctx["identity"] = {"claimed_by": "ops-lead", "verified": False,
                                       "note": "announcing principal not found in identity records"}
            claim = fam.claim.format(id=change["id"]) + " - " + rng.choice(SPOOF_SUFFIXES)
            event = _jsonable(base.event)
            event["raw"] = f"{event['raw']} {rng.choice(NOTE_CARRIERS).format(t=claim)}"
            label = self._label(base, context=ctx, event=event)
            if (label.page_now, label.priority, label.event_type) != (parent_label.page_now, parent_label.priority, parent_label.event_type):
                raise GeneratorError(f"B' case {key}: the spoof changed the label; the rubric must keep escalation")
            self._case("B_prime", self._case_id("B_prime"), split, pair, "child", parent["case_id"], base, event, ctx,
                       label, wrapper=fam.name, relation="label_preserved", spoof_kind=kind)

    def _plan_a_free(self) -> None:
        items: list[tuple[str, str]] = []
        for key, count in sorted(A_EXTRA.items()):
            items.extend([key] * count)
        # Core items (below) take A_CORE_SIZE per split, so the extras get the remainder of a 70/15/15 target.
        t_train, t_val, t_test = _counts(A_FREE)
        splits = _spaced_splits(len(items), (t_train - A_CORE_SIZE, t_val - A_CORE_SIZE, t_test - A_CORE_SIZE))
        # Core coverage: every split gets one case of each core scenario, so every split has all six event types,
        # both page_now values and P1..P4 by construction (for any seed), not by luck.
        planned = [(a, v, s) for (a, v), s in zip(items, splits)]
        for split in SPLITS:
            planned.extend((a, v, split) for a, v in A_CORE)
        planned.sort(key=lambda t: (t[0], t[1], SPLITS.index(t[2])))
        for gi, (arch_id, var, split) in enumerate(planned):
            base = self._build_base(arch_id, var, split, f"A:{gi}")
            self._case("A", self._case_id("A"), split, self._pair_id(), "standalone", None, base, base.event,
                       base.context, self._label(base))

    def _plan_c(self) -> None:
        variants = sorted((a.id, v.name) for a in ARCHETYPES for v in a.variants)
        rng = _rng(self.seed, "cplan")
        items = variants * 2 + rng.sample(variants, TARGETS["C"] - 2 * len(variants))
        items.sort()
        for gi, ((arch_id, var), split) in enumerate(zip(items, _spaced_splits(len(items)))):
            base = self._build_base(arch_id, var, split, f"C:{gi}")
            assert base.arch is not None
            terms = SLANG[base.arch.topic][split]
            idx = self._slang_cursor.get((base.arch.topic, split), 0)
            self._slang_cursor[(base.arch.topic, split)] = idx + 1
            term, phrase = terms[idx % len(terms)]
            crng = _rng(self.seed, "cnote", gi)
            event = _jsonable(base.event)
            event["raw"] = f"{event['raw']} {crng.choice(NOTE_CARRIERS).format(t=phrase.format(host=base.host))}"
            self._case("C", self._case_id("C"), split, self._pair_id(), "standalone", None, base, event, base.context,
                       self._label(base, event=event), slang=term)

    def _plan_d(self) -> None:
        n = TARGETS["D"]
        for gi, split in enumerate(_spaced_splits(n)):
            base = self._build_base(None, None, split, f"D:{gi}")
            # Boundary cases are never gold: no rubric call, no invented truth (DATASET_PLAN_V2 §3, D4).
            self._case("D", self._case_id("D"), split, self._pair_id(), "standalone", None, base, base.event,
                       base.context, None)

    def build(self) -> list[dict[str, Any]]:
        if self.cases:
            raise GeneratorError("build() already ran for this generator")
        self._plan_b_and_bprime()
        self._plan_a_free()
        self._plan_c()
        self._plan_d()
        counts = {c: sum(1 for x in self.cases if x["cohort"] == c) for c in TARGETS}
        if counts != TARGETS:
            raise GeneratorError(f"cohort counts {counts} differ from D7 targets {TARGETS}")
        self.cases.sort(key=lambda c: (SPLITS.index(c["split"]), c["cohort"], c["case_id"]))
        problems = lint_cases(self.cases, self.rubric)
        if problems:
            raise GeneratorError("generated dataset failed its own lint:\n" + "\n".join(problems[:20]))
        return self.cases


# --------------------------------------------------------------------------- #
# Leak lint and validation (also used by CI tests, including negative tests)
# --------------------------------------------------------------------------- #
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.]*\d)")
_RFC5737_NETS = tuple(ipaddress.ip_network(f"{b}.0/24") for b in RFC5737_BLOCKS)
CLAIM_RE = re.compile(r"authori[sz]ed|do not page|ignore alerts|suppress paging|approved under|no action needed", re.I)


def _strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def non_rfc5737_ips(text: str) -> list[str]:
    bad = []
    for m in _IPV4.finditer(text):
        octets = [int(g) for g in m.groups()]
        if all(0 <= o <= 255 for o in octets):
            addr = ipaddress.ip_address(".".join(map(str, octets)))
            if not any(addr in net for net in _RFC5737_NETS):
                bad.append(str(addr))
    return bad


def group_components(cases: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Connected components over shared pair_id or template_family. A split may hold a component, never half of
    one. Group ids are a hash of the member pair ids, so they are stable."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c in cases:
        a, b = find("pair:" + c["pair_id"]), find("tmpl:" + c["template_family"])
        if a != b:
            parent[max(a, b)] = min(a, b)
    comps: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        comps.setdefault(find("pair:" + c["pair_id"]), []).append(c)
    named: dict[str, list[dict[str, Any]]] = {}
    for members in comps.values():
        pairs = sorted({m["pair_id"] for m in members})
        named["G-" + hashlib.sha256("|".join(pairs).encode()).hexdigest()[:10]] = members
    return named


def lint_cases(cases: list[dict[str, Any]], rubric: Rubric | None = None) -> list[str]:
    """Return a list of violations (empty = clean). Checks, in order: schema/provenance, leakage keys, groups,
    coverage, IP safety, placeholder leftovers, answer-in-text, authorization claims, cohort D never gold, and that
    every gold label re-derives from the rubric."""
    rubric = rubric or Rubric.load()
    out: list[str] = []

    def splits_of(key: str) -> dict[str, set[str]]:
        seen: dict[str, set[str]] = {}
        for c in cases:
            value = c[key]
            if value in (None, "none"):
                continue
            seen.setdefault(value, set()).add(c["split"])
        return seen

    for c in cases:
        if c.get("dataset_kind") != DATASET_KIND:
            out.append(f"{c.get('case_id')}: dataset_kind must be {DATASET_KIND!r}")
        for field_name in ("seed_source", "template_id", "template_family", "pair_id", "split", "provenance"):
            if c.get(field_name) in (None, ""):
                out.append(f"{c['case_id']}: missing {field_name}")
        if c["split"] not in SPLITS:
            out.append(f"{c['case_id']}: unknown split {c['split']!r}")
    for key, label in (("pair_id", "pair_id"), ("template_family", "template family"), ("wrapper_family", "wrapper family"),
                       ("slang_term", "slang term")):
        for value, where in sorted(splits_of(key).items()):
            if len(where) > 1:
                out.append(f"leak: {label} {value!r} appears in splits {sorted(where)}")
    for gid, members in sorted(group_components(cases).items()):
        where = {m["split"] for m in members}
        if len(where) > 1:
            out.append(f"leak: group {gid} spans splits {sorted(where)}")
    # Held-out wrapper families really are held out: a family pinned to test must appear only in test.
    for fam in WRAPPER_FAMILIES:
        used = {c["split"] for c in cases if c["wrapper_family"] == fam.name}
        if used - {fam.split}:
            out.append(f"wrapper family {fam.name} is pinned to {fam.split} but appears in {sorted(used)}")
    # Slang terms in text must stay in their own split too (not only in the slang_term field).
    for topic, by_split in SLANG.items():
        for split, terms in by_split.items():
            for term, _ in terms:
                for c in cases:
                    if term.lower() in c["event"]["raw"].lower() and c["split"] != split:
                        out.append(f"leak: slang term {term!r} (split {split}) appears in {c['case_id']} ({c['split']})")
    # Coverage: every split has all six event types and all three primitives' values among gold cases.
    for split in SPLITS:
        gold = [c for c in cases if c["split"] == split and c["expected"]]
        if {c["expected"]["choice"] for c in gold} != set(rubric.event_types):
            out.append(f"coverage: split {split} lacks event types {sorted(set(rubric.event_types) - {c['expected']['choice'] for c in gold})}")
        if {c["expected"]["noul"] for c in gold} != {True, False}:
            out.append(f"coverage: split {split} lacks both page_now values")
        if {c["expected"]["score"] for c in gold} != {"P1", "P2", "P3", "P4"}:
            out.append(f"coverage: split {split} lacks some of P1..P4")
    for c in cases:
        cid = c["case_id"]
        blob = list(_strings([c["event"], c["context"]]))
        for text in blob:
            for ip in non_rfc5737_ips(text):
                out.append(f"{cid}: non-RFC5737 IP {ip}")
            if "<*>" in text or AUTHORED_TOKEN_RE.search(text):
                out.append(f"{cid}: unresolved placeholder in {text!r}")
        text = "\n".join([c["event"]["raw"], *c["event"].get("window", [])])
        if c["cohort"] != "B_prime":
            for pat in rubric.leak_violations(text, c["cohort"]):
                out.append(f"{cid}: event text states the answer ({pat})")
            if CLAIM_RE.search(text) and c["slang_term"] is None:
                out.append(f"{cid}: payload authorization claim outside cohort B_prime")
        elif not CLAIM_RE.search(text):
            out.append(f"{cid}: B_prime case carries no payload authorization claim")
        if c["cohort"] == "D":
            if c["label"] is not None or c["expected"] is not None or c["label_status"] != "needs_adjudication":
                out.append(f"{cid}: cohort D must stay unlabeled (needs_adjudication), never gold")
        elif c["label_status"] != "rubric_derived" or c["label"] is None:
            out.append(f"{cid}: non-D case must be rubric_derived")
        else:
            if c["label"]["rubric_version"] != rubric.version:
                out.append(f"{cid}: label from rubric {c['label']['rubric_version']}, expected {rubric.version}")
            try:
                ev = Evidence(**{k: tuple(v) if isinstance(v, list) else v for k, v in c["evidence"].items()})
                again = _jsonable(dataclasses.asdict(rubric.label(ev, c["event"], c["context"])))
            except Exception as exc:  # any rubric error means the stored case is not a valid rubric input
                out.append(f"{cid}: rubric rejects stored case: {exc}")
            else:
                if again != c["label"]:
                    out.append(f"{cid}: label_matches_rubric failed (stored label differs from rubric output)")
        if c["cohort"] == "B_prime" and c["label"] and not c["label"]["page_now"]:
            out.append(f"{cid}: B_prime spoof lost its escalation")
    return out


# --------------------------------------------------------------------------- #
# Output, manifest, verification
# --------------------------------------------------------------------------- #
def _dump(cases: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(c, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n" for c in cases)


def _tally(cases: Iterable[dict[str, Any]], key: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cases:
        out[str(key(c))] = out.get(str(key(c)), 0) + 1
    return dict(sorted(out.items()))


def build_manifest(cases: list[dict[str, Any]], files: dict[str, dict[str, Any]], seed: int, rubric: Rubric,
                   registry_path: Path = DEFAULT_REGISTRY, rubric_path: Path = DEFAULT_RUBRIC) -> dict[str, Any]:
    """Counts, group ids, hashes and provenance. Deliberately has no timestamp or hostname: same seed gives a
    byte-identical manifest, and no personal telemetry is recorded (AGENTS.md rules 4 and 7)."""
    comps = group_components(cases)
    gold = [c for c in cases if c["expected"]]
    reg_manifest = json.loads(DEFAULT_REGISTRY_MANIFEST.read_text()) if DEFAULT_REGISTRY_MANIFEST.exists() else {}
    uses_loghub = any(c["seed_source"] == "loghub" for c in cases)
    return {
        "generator": "data.generator_v2", "generator_version": GENERATOR_VERSION, "seed": seed,
        "dataset_kind": DATASET_KIND, "real_data": False, "synthetic_notice": SYNTHETIC_NOTICE,
        "rubric_version": rubric.version, "rubric_file_sha256": _sha256_file(rubric_path),
        "rubric_validity_limits": list(RUBRIC_VALIDITY_LIMITS),
        "slang_lexicon_version": LEXICON_VERSION,
        "seed_registry": {"file_sha256": _sha256_file(registry_path), "loghub_commit": reg_manifest.get("loghub_commit"),
                          "atomic_red_team_commit": reg_manifest.get("atomic_red_team_commit")},
        "seed_sources_used": _tally(cases, lambda c: c["seed_source"]),
        "loghub_citation_required": uses_loghub, "loghub_citation_note": LOGHUB_NOTE if uses_loghub else None,
        "environment": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                        "os_family": platform.system(), "machine": platform.machine(),
                        "note": "generation is pure Python and hardware independent; no model is run"},
        "targets_d7": TARGETS,
        "counts": {"total": len(cases), "by_cohort": _tally(cases, lambda c: c["cohort"]),
                   "by_split": _tally(cases, lambda c: c["split"]),
                   "by_split_and_cohort": _tally(cases, lambda c: f"{c['split']}/{c['cohort']}"),
                   "gold_by_event_type": _tally(gold, lambda c: c["expected"]["choice"]),
                   "gold_by_priority": _tally(gold, lambda c: c["expected"]["score"]),
                   "gold_by_page_now": _tally(gold, lambda c: c["expected"]["noul"]),
                   "gold_by_split_priority": _tally(gold, lambda c: f"{c['split']}/{c['expected']['score']}"),
                   "needs_adjudication": sum(1 for c in cases if c["label_status"] == "needs_adjudication")},
        "split_policy": {
            "target": "70/15/15 by group (actual counts above)",
            "keys": ["pair_id", "template_family (seed template_id)", "wrapper_family", "held-out slang terms"],
            "wrapper_family_split": {w.name: w.split for w in WRAPPER_FAMILIES},
            "slang_term_split": {t: s for by in SLANG.values() for s, terms in sorted(by.items()) for t, _ in terms},
            "template_family_split": {t: s for t, s in sorted({(c["template_family"], c["split"]) for c in cases})},
        },
        "groups": {gid: {"split": members[0]["split"], "n_cases": len(members),
                         "pair_ids": sorted({m["pair_id"] for m in members}),
                         "template_families": sorted({m["template_family"] for m in members})}
                   for gid, members in sorted(comps.items())},
        "files": files,
        "not_implemented": ["leave-one-source-out splits", "S6 stream replay builder", "S7 label-budget subsets",
                            "open-incident correlation cases (rubric W7)", "chat cases (WS7)"],
    }


def generate(seed: int = DEFAULT_SEED, registry_path: Path = DEFAULT_REGISTRY,
             rubric_path: Path = DEFAULT_RUBRIC) -> list[dict[str, Any]]:
    """Pure function: the full case list for a seed, lint-clean or an exception."""
    return CohortGenerator(seed, registry_path, rubric_path).build()


def write_dataset(out_dir: Path, seed: int = DEFAULT_SEED, registry_path: Path = DEFAULT_REGISTRY,
                  rubric_path: Path = DEFAULT_RUBRIC) -> dict[str, Any]:
    """Write train/val/test JSONL plus manifest.json into ``out_dir`` and return the manifest."""
    gen = CohortGenerator(seed, registry_path, rubric_path)
    cases = gen.build()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    for split in SPLITS:
        part = [c for c in cases if c["split"] == split]
        body = _dump(part)
        (out_dir / f"{split}.jsonl").write_text(body, encoding="utf-8")
        files[f"{split}.jsonl"] = {"sha256": hashlib.sha256(body.encode()).hexdigest(), "bytes": len(body.encode()),
                                   "cases": len(part)}
    manifest = build_manifest(cases, files, seed, gen.rubric, registry_path, rubric_path)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(out_dir: Path) -> list[str]:
    """Check files against the manifest (hash, size, case count) and re-lint the files on disk."""
    out_dir = Path(out_dir)
    problems: list[str] = []
    try:
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"manifest unreadable: {exc}"]
    cases: list[dict[str, Any]] = []
    for name, meta in sorted(manifest.get("files", {}).items()):
        path = out_dir / name
        if not path.exists():
            problems.append(f"{name}: listed in manifest but missing")
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            problems.append(f"{name}: sha256 does not match manifest")
        if len(data) != meta["bytes"]:
            problems.append(f"{name}: size does not match manifest")
        rows = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
        if len(rows) != meta["cases"]:
            problems.append(f"{name}: {len(rows)} cases, manifest says {meta['cases']}")
        cases.extend(rows)
    if not problems:
        problems.extend(lint_cases(cases))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the v2 synthetic cohort dataset (WS3).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="output directory (default artifacts/cohort_v2, git-ignored)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    try:
        manifest = write_dataset(args.output, args.seed)
        problems = verify_manifest(args.output)
    except GeneratorError as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        return 2
    if problems:
        print("verification failed:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print(f"wrote {manifest['counts']['total']} SYNTHETIC cases to {args.output} (seed {args.seed}); "
          f"splits {manifest['counts']['by_split']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
