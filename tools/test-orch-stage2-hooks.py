#!/usr/bin/env python3
"""Behavioural change-carries-check for the item 28.2 stage-2 arming of the orchestrator backlog guards.

This suite proves that each stage-2 `.aiqt/orchestration.json` key (`enumerator`, `yield_tools`, `mode`,
`staleness`, `escape`, and the optional `attestations` and `mistakes_register`) actually changes the
installed hook behaviour, and pins the runtime posture the hook takes on a malformed value of each. It
drives the REAL installed hook script exactly as tools/test-orch-stage1-hooks.py does: per case it builds a
throwaway git repo and a temporary stand-in store, writes a fixture registry into the repo, and invokes

    python3 -I <plugin>/hooks/scripts/aiqt_hooks.py <hook-action>

with a JSON stdin payload, then asserts the exit code, any stdout verdict JSON, and the state files the
hook wrote under the temporary store. It NEVER touches the real /opt/cleanlanguage/private store, so it
runs in CI.

The backlog is produced by a minimal FIXTURE enumerator written into each test temp directory: it reads a
JSON list of AEI items and prints the AEI v1 envelope (version 1, generated_at_utc from the clock, a
source locator, the items). It deliberately does not depend on the project enumerator
tools/orch-enumerate-backlog.py, which has its own suite; this file tests what the HOOK does with an
enumeration, not how TODO.md is parsed.

Every armed-behaviour proof (T1 to T15 of the item 28.2 stage-2 plan, section 3, PR1-g) runs against the
stage-2 fixture (behaviour PRESENT) and against a contrast without the key (behaviour ABSENT): the
stage-1 fixture (the committed registry shape at d191071), or the stage-2 fixture with only the key under test
removed where the stage-1 fixture would fail for an unrelated reason (NO_ENUMERATOR). Each contrast test
asserts the OTHER verdict, so the stage-2 assertion is red without its key. That dual run is the
change-carries-check.

Optional keys: T6 (`attestations`, open point P5) and T12 (`mistakes_register`, open point P6) cover keys
the plan may defer. They are implemented and run, not skipped; they pin the hook behaviour the key would
arm whichever way P5 and P6 are decided.

Single-uid limit (unchanged from stage 1): the escape sentinel HONOUR leg needs a file owned by another
uid and cannot run here; T11 proves the declared path is the one consulted (spoof-recorded) and that a
malformed declaration disables the release, and the honour leg is verified on the host.

Grounding: every hook-behaviour assertion is read from
plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py at source; cited line numbers are in the
per-test comments. The PR1-f doctor tests at the end drive tools/orch_doctor.py the same way. A
missing required input (the installed hook or the doctor) fails the test rather than skipping it, so
an absent file can never read as a green run. The doctor tests also prove that a preflight out of
scope, or for idle out of the roster, runs no enumerator, as the hook runs none there (finding R3),
and that the doctor re-executes itself under python3 -I and exits 2 with a message when that
re-execution fails (finding R6). The doctor reads the resume barrier only as a regular file: a
barrier that is a FIFO with no writer, a directory, or a symlink to /dev/null is reported as
cannot-evaluate, exit 2, within a short timeout and naming the path and the file type, and the audit
is not run, and a class probe scans the doctor source so that every path it opens goes through its
checked helper (finding S3). Before any hook reader is called, a registry file or a declared read path
(the mode and lease paths, the record paths, the enumerator operands) that exists and is not a regular
file, a FIFO, a directory, or a symlink to a FIFO, is reported as cannot-evaluate, exit 2, within a
short timeout, with no enumerator run and no hook state written (round 5 T1). The writes-nothing test
runs a fresh copy of the doctor and the hook, in a tree that never held a __pycache__, and asserts no
bytecode file appears anywhere under it (round 5 T3). The fixed hook state files each command opens
with a plain blocking open are checked the same way before the reader that opens them: for preflight
turn-state.json, dispatch-ledger.jsonl, backlog-checkpoint.json and, with attestations declared,
attestations-validated.json and guard-events.jsonl; for the resume audit guard-events.jsonl,
escape-spoof.json, the forced-exit files and the attestation snapshot temporary file, and with an
unreadable registry resume-barrier.json.unused (round 6 U1). Each command checks only what its own
hook call path opens: a FIFO backlog operand, mode record, lease or preview state file does not refuse
the resume audit, which runs and rewrites the barrier, and a FIFO audit-only record or state file, or
an out-of-scope preview with a FIFO turn-state.json, does not refuse the preview (round 6 U2).
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
HOOK = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts" / "aiqt_hooks.py"
DOCTOR = HERE / "orch_doctor.py"
ZERO64 = "0" * 64

# The fixture enumerator: argv[1] is a JSON file holding the items list. It prints one AEI v1 envelope
# that validate_enumeration accepts (aiqt_hooks.py:7904-7959) and exits 0.
ENUM_FIXTURE = """import json
import sys
from datetime import datetime, timezone

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    items = json.load(fh)
print(json.dumps({"version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                  "source": {"locator": path}, "items": items}))
"""


# The fixture enumerator, also appending one line to the file named by argv[2] each time it runs, so
# a test can observe that the declared enumerator ran and that its write is its own.
WRITING_ENUM_FIXTURE = ENUM_FIXTURE.replace(
    "path = sys.argv[1]\n",
    "path = sys.argv[1]\nwith open(sys.argv[2], \"a\", encoding=\"utf-8\") as mark:\n"
    "    mark.write(\"ran\\n\")\n", 1)

# Runs in a separate python3 -I process: load the doctor by path, replace the hook resume audit with
# a writer that rewrites the barrier with new content but a ts from before the run, and return the
# doctor exit status for that audit.
STALE_TS_PROG = """
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("orch_doctor_under_test", sys.argv[1])
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
hook = doctor._load_hook()
root = sys.argv[2]


def stale_writer(data):
    path = os.path.join(hook._orch_state_dir_for_root(root), "resume-barrier.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"active": False, "findings": [], "ts": "2000-01-01T00:00:00+00:00",
                   "warned": False}, fh)


hook.orch_resume_audit = stale_writer
sys.exit(doctor._resume_audit(hook, root))
"""

# Runs WITHOUT -I, so the doctor takes its re-execution branch, with sys.executable pointed at a path
# that does not exist: os.execv then raises OSError, which the doctor reports and exits 2 on.
FAILED_REEXEC_PROG = """
import runpy, sys
sys.executable = sys.argv[2]
sys.argv = [sys.argv[1], "--help"]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(delta_hours=0.0) -> str:
    return (_now() + timedelta(hours=delta_hours)).isoformat()


def item(iid, state="open", granted=True, blocker=None, title=None):
    out = {"id": iid, "state": state, "granted": granted, "blocker": blocker}
    if title is not None:
        out["title"] = title
    return out


def chain_lines(rows):
    """Serialize rows as a chained register (aiqt_hooks.py:9453-9481): seq is the line number and prev is
    the sha256 of the prior raw line, 64 zeros for the first."""
    lines, prev = [], None
    for n, row in enumerate(rows, 1):
        obj = dict(row)
        obj["seq"] = n
        obj["prev"] = ZERO64 if prev is None else _sha256_hex(prev)
        line = json.dumps(obj, sort_keys=True)
        lines.append(line)
        prev = line
    return lines


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def tree_state(path):
    """Every entry under path with mode, size, mtime_ns, and (for files) a content digest, so a single
    created, deleted, or rewritten file or directory shows as a difference."""
    out = {}
    for p in sorted(Path(path).rglob("*")):
        st = p.lstat()
        entry = (st.st_mode, st.st_size, st.st_mtime_ns)
        if p.is_file() and not p.is_symlink():
            entry += (hashlib.sha256(p.read_bytes()).hexdigest(),)
        out[str(p.relative_to(path))] = entry
    return out


class Stage2Harness(unittest.TestCase):
    """A throwaway git repo, a temporary stand-in store, and a fixture enumerator, torn down per test."""

    def setUp(self):
        if not HOOK.exists():
            self.fail("installed hook not found: {}".format(HOOK))
        self._tmp = Path(tempfile.mkdtemp(prefix="orch-stage2-"))
        self.repo = self._tmp / "repo"
        self.store = self._tmp / "store"
        self.repo.mkdir()
        self.store.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(self.repo)],
                       capture_output=True, text=True, check=True)
        _git(self.repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-m", "init")
        # A repo-relative file that a register pointer can resolve to (aiqt_hooks.py:9555-9578).
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "evidence.md").write_text("evidence\n", encoding="utf-8")
        self.enum_script = self._tmp / "enum_fixture.py"
        self.enum_script.write_text(ENUM_FIXTURE, encoding="utf-8")
        self.backlog = self._tmp / "backlog.json"
        self.set_items([])
        self.write_mode("attended")
        self.write_record_files()

    def tearDown(self):
        for dirpath, _dirs, _files in os.walk(self._tmp):
            try:
                os.chmod(dirpath, 0o755)
            except OSError:
                pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    # --- registry fixtures ---------------------------------------------------------------------------
    def _p(self, *parts):
        return str(self.store.joinpath(*parts))

    def state_dir(self):
        return self.store / "orch-state"

    def stage1(self):
        """The committed stage-1 shape (.aiqt/orchestration.json at d191071), store paths substituted."""
        return {
            "version": 1,
            "companion_stores": [str(self.store)],
            "record": {
                "findings": self._p("open-findings.md"),
                "pending_decisions": self._p("pending-decisions.md"),
                "handoff": self._p("session-handoff.md"),
            },
            "lease": {"path": self._p("session-state.md"), "max_age_hours": 24},
            "state_dir": str(self.state_dir()),
            "dispatch_tools": [],
        }

    def stage2(self, drop=(), **overrides):
        """The stage-2 shape of plan section 1 (without the optional attestations and mistakes_register,
        which T6 and T12 add). drop removes keys; overrides replace or add them."""
        reg = self.stage1()
        reg.update({
            "enumerator": {"argv": [sys.executable, "-I", str(self.enum_script), str(self.backlog)],
                           "timeout": 5},
            "yield_tools": ["ScheduleWakeup", "CronCreate"],
            "mode": {"path": self._p("operating-mode.md")},
            "staleness": {"task_hours": 24, "external_hours": 72},
            "escape": {"path": "ESCAPE-ALLOW-YIELD"},
        })
        reg.update(overrides)
        for key in drop:
            reg.pop(key, None)
        return reg

    # --- fixture builders ----------------------------------------------------------------------------
    def write_registry(self, obj):
        aiqt = self.repo / ".aiqt"
        aiqt.mkdir(exist_ok=True)
        (aiqt / "orchestration.json").write_text(json.dumps(obj), encoding="utf-8")

    def set_items(self, items):
        self.backlog.write_text(json.dumps(items), encoding="utf-8")

    def write_mode(self, value):
        Path(self._p("operating-mode.md")).write_text(
            "Session mode record.\nOperating-mode: {}\n".format(value), encoding="utf-8")

    def arm_lease(self, age_seconds=0):
        lease = Path(self._p("session-state.md"))
        lease.write_text("held by the orchestrator\n", encoding="utf-8")
        if age_seconds:
            t = time.time() - age_seconds
            os.utime(lease, (t, t))
        return lease

    def write_record_files(self, handoff="Session handoff, no markers here.\n", findings="", pending=""):
        Path(self._p("session-handoff.md")).write_text(handoff, encoding="utf-8")
        Path(self._p("open-findings.md")).write_text(findings, encoding="utf-8")
        Path(self._p("pending-decisions.md")).write_text(pending, encoding="utf-8")

    def seed_state(self, name, obj):
        sd = self.state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        (sd / name).write_text(json.dumps(obj), encoding="utf-8")

    def seed_ledger(self, rows):
        sd = self.state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "dispatch-ledger.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def self_owned_sentinel(self, name):
        sd = self.state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        path = sd / name
        path.write_text("", encoding="utf-8")
        os.chmod(path, 0o644)
        self.assertEqual(os.stat(path).st_uid, os.geteuid(), "precondition: self-owned sentinel")
        return path

    # --- invocation ----------------------------------------------------------------------------------
    def _env(self):
        env = dict(os.environ)
        env["HOME"] = str(self.store / "home")
        env["XDG_STATE_HOME"] = str(self.store / "xdg")
        return env

    def run_hook(self, action, payload=None):
        """Invoke python3 -I aiqt_hooks.py <action> with the JSON payload on stdin (HOME and
        XDG_STATE_HOME pinned inside the throwaway tree, as in the stage-1 harness)."""
        payload = dict(payload or {})
        payload.setdefault("cwd", str(self.repo))
        return subprocess.run([sys.executable, "-I", str(HOOK), action],
                              input=json.dumps(payload), capture_output=True, text=True,
                              env=self._env(), timeout=120)

    def run_doctor(self, *args):
        return subprocess.run([sys.executable, "-I", str(DOCTOR), *args, "--root", str(self.repo)],
                              capture_output=True, text=True, env=self._env(), timeout=120)

    def stop(self, **payload):
        return self.run_hook("orch_stop_guard", payload)

    def schedule(self, tool_input=None, tool="ScheduleWakeup"):
        return self.run_hook("orch_yield_tool", {
            "tool_name": tool,
            "tool_input": tool_input if tool_input is not None
            else {"prompt": "recheck the work queue", "delaySeconds": 60},
        })

    def human_prompt(self):
        """A genuine human prompt zeroes the stop and schedule denial counters (aiqt_hooks.py:9327-9332)."""
        r = self.run_hook("orch_prompt_stamp", {"prompt": "please continue"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def stdout_json(self, result):
        out = result.stdout.strip()
        if not out:
            return None
        return json.loads(out.splitlines()[0])

    def verdict_json(self, result):
        out = self.stdout_json(result)
        self.assertIsNotNone(out, "expected a JSON verdict on stdout, got none (exit {}, stderr {!r})"
                             .format(result.returncode, result.stderr[:300]))
        return out

    def state_json(self, name):
        obj = self.read_json(name)
        self.assertIsNotNone(obj, "expected {} under the state dir".format(name))
        return obj

    def read_jsonl(self, name):
        path = self.state_dir() / name
        if not path.exists():
            return None
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read_json(self, name):
        path = self.state_dir() / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def find_anywhere(self, name):
        return [str(p) for p in self._tmp.rglob(name)]

    def assert_no_enumerator_deny(self, r):
        # The stage-1 posture under a live lease (aiqt_hooks.py:7966-7968, 8208-8213; stage-1 T1:639-646).
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("NO_ENUMERATOR", r.stderr)


# =====================================================================================================
# T1. Stop with one open granted unblocked item denies, naming the id (aiqt_hooks.py:8253-8262)
# =====================================================================================================
class T01StopActionable(Stage2Harness):
    def test_stage2_denies_naming_the_item(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("42", title="Ship the widget")])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("42 (Ship the widget: no blocker recorded)", r.stderr)
        self.assertNotIn("NO_ENUMERATOR", r.stderr)

    def test_stage1_contrast(self):
        # Without the enumerator the same backlog is never read: NO_ENUMERATOR, and the id is not named.
        self.write_registry(self.stage1())
        self.arm_lease()
        self.set_items([item("42", title="Ship the widget")])
        r = self.stop()
        self.assert_no_enumerator_deny(r)
        self.assertNotIn("Ship the widget", r.stderr)


# =====================================================================================================
# T2. Stop with every item closed or proposed allows (aiqt_hooks.py:8116-8120, 8246-8247)
# =====================================================================================================
class T02StopNothingActionable(Stage2Harness):
    ITEMS = [item("1", state="closed"), item("2", state="proposed"), item("3", granted=False)]

    def test_stage2_allows(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items(self.ITEMS)
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "a clean ALLOW is silent")
        last = self.read_jsonl("guard-events.jsonl")[-1]
        self.assertEqual((last["kind"], last["decision"]), ("Stop", "allow"))

    def test_stage1_contrast(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        self.set_items(self.ITEMS)
        self.assert_no_enumerator_deny(self.stop())


# =====================================================================================================
# T3. human-decision blockers against the declared pending-decisions record (aiqt_hooks.py:8138-8150)
# =====================================================================================================
class T03HumanDecision(Stage2Harness):
    def _run(self, ref, pending, registry=None):
        self.write_registry(registry or self.stage2())
        self.arm_lease()
        self.write_record_files(pending=pending)
        self.set_items([item("5", blocker={"kind": "human-decision", "ref": ref})])
        return self.stop()

    def test_table_row_blocks(self):
        r = self._run("PD-7", "| ID | Decision |\n| PD-7 | Choose the colour |\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_colon_line_blocks(self):
        r = self._run("PD-7", "PD-7: choose the colour\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_row_absent_is_actionable(self):
        # A free-text mention is not a row-id position (aiqt_hooks.py:8145-8150).
        r = self._run("PD-7", "| PD-8 | Another decision |\nWe discussed PD-7 in passing.\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ref PD-7 is not at a pending-decision row-id position", r.stderr)

    def test_lowercase_ref_is_not_a_decision_id(self):
        r = self._run("pd-7", "| pd-7 | lowercase row |\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("is not a decision id", r.stderr)

    def test_unreadable_pending_surface_holds(self):
        # An unreadable declared surface is cannot-evaluate, which denies the Stop
        # (aiqt_hooks.py:8139-8141, 8240-8245).
        self.write_registry(self.stage2())
        self.arm_lease()
        os.remove(self._p("pending-decisions.md"))
        self.set_items([item("5", blocker={"kind": "human-decision", "ref": "PD-7"})])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("cannot-evaluate", r.stderr)

    def test_stage1_contrast(self):
        r = self._run("PD-7", "| PD-7 | Choose the colour |\n", registry=self.stage1())
        self.assert_no_enumerator_deny(r)


# =====================================================================================================
# T4. not-before blockers (aiqt_hooks.py:8170-8176)
# =====================================================================================================
class T04NotBefore(Stage2Harness):
    def _run(self, when, registry=None):
        self.write_registry(registry or self.stage2())
        self.arm_lease()
        self.set_items([item("6", blocker={"kind": "not-before", "ref": when})])
        return self.stop()

    def test_future_blocks(self):
        self.assertEqual(self._run(_iso(24)).returncode, 0)

    def test_past_is_actionable(self):
        r = self._run(_iso(-24))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("not-before constraint unparseable or already met", r.stderr)

    def test_stage1_contrast(self):
        self.assert_no_enumerator_deny(self._run(_iso(24), registry=self.stage1()))


# =====================================================================================================
# T5. Anti-shrinkage checkpoint (aiqt_hooks.py:8335-8431)
# =====================================================================================================
class T05Checkpoint(Stage2Harness):
    def test_vanished_id_is_held_until_closed(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        # Window 1: item 9 open and actionable; the checkpoint and its init marker are written
        # (aiqt_hooks.py:8413-8427).
        self.set_items([item("9")])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.state_json("backlog-checkpoint.json")["ids"], {"9": "eligible"})
        self.assertIsNotNone(self.read_json("checkpoint-init.marker"))
        # Window 2: item 9 deleted with no closed receipt is held as vanished (aiqt_hooks.py:8393-8395).
        self.human_prompt()
        self.set_items([])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("cannot-evaluate", r.stderr)
        self.assertEqual(self.state_json("backlog-checkpoint.json")["ids"], {"9": "eligible"},
                         "the union keeps a vanished id (aiqt_hooks.py:8401-8402)")
        # Window 3: item 9 present as closed is the receipt; the Stop allows and the id leaves.
        self.human_prompt()
        self.set_items([item("9", state="closed")])
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("9", self.state_json("backlog-checkpoint.json")["ids"])

    def test_deleted_checkpoint_with_marker_is_possible_reset(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="proposed")])
        self.assertEqual(self.stop().returncode, 0)
        os.remove(self.state_dir() / "backlog-checkpoint.json")
        self.human_prompt()
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)  # aiqt_hooks.py:8376-8380
        self.assertIn("cannot-evaluate", r.stderr)

    def test_deleted_checkpoint_and_marker_is_a_first_window(self):
        # In-suite contrast: removing BOTH is a legitimate first window, so the marker is load-bearing.
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="proposed")])
        self.assertEqual(self.stop().returncode, 0)
        os.remove(self.state_dir() / "backlog-checkpoint.json")
        os.remove(self.state_dir() / "checkpoint-init.marker")
        self.human_prompt()
        self.assertEqual(self.stop().returncode, 0)

    def test_stage1_contrast(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        self.set_items([item("9")])
        self.assert_no_enumerator_deny(self.stop())
        self.assertEqual(self.find_anywhere("backlog-checkpoint.json"), [],
                         "without an enumerator no checkpoint is written")


# =====================================================================================================
# T6. attestations (OPTIONAL KEY, open point P5; aiqt_hooks.py:8050-8098, 8155-8164, 9625-9661)
# =====================================================================================================
class T06Attestations(Stage2Harness):
    def _register(self, rows, anchor=True):
        path = Path(self._p("attestations.jsonl"))
        lines = chain_lines(rows)
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        if anchor:
            Path(str(path) + ".anchor").write_text(json.dumps({"seq": 0, "digest": ZERO64}),
                                                   encoding="utf-8")
        return path

    def _row(self):
        return {"id": "AT-1", "status": "accepted", "ref": "vendor-x",
                "check_ref": "docs/evidence.md", "ts": _iso()}

    def _external_item(self):
        return item("7", blocker={"kind": "external", "ref": "vendor-x",
                                  "evidence": "awaiting the vendor release", "observed_at_utc": _iso()})

    def _arm(self, rows, anchor=True, declare=True):
        reg = self.stage2(attestations=self._p("attestations.jsonl")) if declare else self.stage2()
        self.write_registry(reg)
        self.arm_lease()
        self._register(rows, anchor=anchor)
        audit = self.run_hook("orch_resume_audit", {})
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.set_items([self._external_item()])

    def test_empty_register_zero_anchor_audits_ok(self):
        self._arm([])
        snap = self.state_json("attestations-validated.json")
        self.assertEqual((snap["status"], snap["seq"], snap["digest"], snap["refs"]),
                         ("ok", 0, ZERO64, []))

    def test_approved_row_blocks(self):
        self._arm([self._row()])
        self.assertEqual(self.state_json("attestations-validated.json")["refs"], ["vendor-x"])
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_without_row_is_actionable(self):
        self._arm([])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("is covered by no fresh validated attestation", r.stderr)

    def test_without_anchor_holds(self):
        self._arm([self._row()])
        os.remove(self._p("attestations.jsonl.anchor"))
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)  # aiqt_hooks.py:9546-9547 -> 8155-8160
        self.assertIn("cannot-evaluate", r.stderr)

    def test_undeclared_contrast_free_text_evidence_blocks(self):
        # Without the key, fresh free-text evidence blocks (aiqt_hooks.py:8165-8166) and no snapshot is
        # written, so test_without_row_is_actionable is red without the key.
        self._arm([], declare=False)
        self.assertIsNone(self.read_json("attestations-validated.json"))
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)


# =====================================================================================================
# T7. staleness horizons (aiqt_hooks.py:8022, 8152-8154, 8294-8301)
# =====================================================================================================
class T07Staleness(Stage2Harness):
    def _tracked(self, staleness, age_hours=30, drop=()):
        self.write_registry(self.stage2(staleness=staleness, drop=drop))
        self.arm_lease()
        self.seed_ledger([{"event": "launch", "task_id": "task-1", "tool": "Bash", "wake": True,
                           "ts": _iso(-age_hours)}])
        self.set_items([item("8", blocker={"kind": "tracked-task", "ref": "task-1"})])
        return self.stop()

    def _external(self, staleness, drop=()):
        self.write_registry(self.stage2(staleness=staleness, drop=drop))
        self.arm_lease()
        self.set_items([item("8", blocker={"kind": "external", "ref": "vendor-y",
                                           "evidence": "status page checked",
                                           "observed_at_utc": _iso(-48)})])
        return self.stop()

    def test_task_hours_48_keeps_a_30h_launch_live(self):
        self.assertEqual(self._tracked({"task_hours": 48, "external_hours": 72}).returncode, 0)

    def test_task_hours_24_ages_a_30h_launch_out(self):
        r = self._tracked({"task_hours": 24, "external_hours": 72})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("resolves to no live ledger row", r.stderr)

    def test_external_hours_72_accepts_a_48h_observation(self):
        self.assertEqual(self._external({"task_hours": 24, "external_hours": 72}).returncode, 0)

    def test_external_hours_24_rejects_a_48h_observation(self):
        r = self._external({"task_hours": 24, "external_hours": 24})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("has no fresh (non-future) evidence", r.stderr)

    def test_undeclared_contrast_uses_the_24h_defaults(self):
        # Without the key both horizons are 24 h (aiqt_hooks.py:8300-8301), so the two allows above flip.
        self.assertEqual(self._tracked(None, drop=("staleness",)).returncode, 2)
        self.assertEqual(self._external(None, drop=("staleness",)).returncode, 2)

    def test_stage1_contrast(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        self.set_items([item("8", blocker={"kind": "tracked-task", "ref": "task-1"})])
        self.assert_no_enumerator_deny(self.stop())


# =====================================================================================================
# T8. orch_yield_tool over the scheduling tools (aiqt_hooks.py:8646-8721)
# =====================================================================================================
class T08YieldTool(Stage2Harness):
    def _arm(self, registry=None):
        self.write_registry(registry or self.stage2())
        self.arm_lease()
        self.set_items([item("42", title="Ship the widget")])

    def test_declared_roster_denies_with_actionable_work(self):
        self._arm()
        r = self.schedule()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.verdict_json(r)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")  # aiqt_hooks.py:8694-8698
        self.assertIn("42 (Ship the widget", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_cron_create_is_in_the_roster(self):
        self._arm()
        out = self.verdict_json(self.schedule(tool="CronCreate"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_undeclared_roster_contrast_allows(self):
        self._arm(self.stage2(drop=("yield_tools",)))
        r = self.schedule()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "outside the roster the call is allowed unjudged")

    def test_stage1_contrast_allows(self):
        self._arm(self.stage1())
        r = self.schedule()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_stop_true_follows_the_stop_kind(self):
        # tool_input stop true is judged as kind "stop" (aiqt_hooks.py:8669): with the stop counter at the
        # loop bound it yields with findings, where the schedule kind (next test) denies.
        self._arm()
        self.seed_state("turn-state.json", {"stop_denials": 2})
        r = self.schedule({"stop": True, "prompt": "end the loop"})
        out = self.verdict_json(r)
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("loop bound", out["systemMessage"])

    def test_without_stop_flag_the_same_state_denies(self):
        self._arm()
        self.seed_state("turn-state.json", {"stop_denials": 2})
        out = self.verdict_json(self.schedule({"prompt": "end the loop"}))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_three_denials_on_an_unchanged_basis_release_with_findings(self):
        # aiqt_hooks.py:8248-8252 (the cap) and 8704-8718 (the forced-exit record).
        self._arm()
        for n in range(1, 4):
            out = self.verdict_json(self.schedule())
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", "call {}".format(n))
            self.assertEqual(self.state_json("turn-state.json")["schedule_denials"], n)
        out = self.verdict_json(self.schedule())
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("3 schedule denials on an unchanged basis", out["systemMessage"])
        rows = self.read_jsonl("forced-exit.jsonl")
        self.assertIsNotNone(rows, "a cap release past open work is recorded")
        self.assertEqual(rows[-1]["event"], "yield-tool")
        self.assertIn("42", rows[-1]["open_ids"])


# =====================================================================================================
# T9. orch_ask_guard against the declared mode record (aiqt_hooks.py:8724-8766)
# =====================================================================================================
class T09AskGuard(Stage2Harness):
    def _ask(self):
        return self.run_hook("orch_ask_guard", {
            "tool_name": "AskUserQuestion", "session_id": "s1", "tool_use_id": "tu1",
            "tool_input": {"questions": [{"question": "Which option?"}]},
        })

    def test_unattended_denies_and_records_pending(self):
        self.write_registry(self.stage2())
        self.write_mode("unattended")
        r = self._ask()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.verdict_json(r)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        rows = self.read_jsonl("pending-asks.jsonl")
        self.assertEqual([row["key"] for row in rows], ["s1::tu1"])

    def test_attended_allows(self):
        self.write_registry(self.stage2())
        self.write_mode("attended")
        r = self._ask()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIsNone(self.read_jsonl("pending-asks.jsonl"))

    def test_stage1_contrast_fails_open_with_event(self):
        # No mode key: the unattended record on disk is never read; allow plus a fail-open guard event.
        self.write_registry(self.stage1())
        self.write_mode("unattended")
        r = self._ask()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        events = self.read_jsonl("guard-events.jsonl")
        self.assertEqual((events[-1]["kind"], events[-1]["decision"]), ("ask-guard", "fail-open"))


# =====================================================================================================
# T10. Scope by mode record when the lease is stale (aiqt_hooks.py:7779-7817)
# =====================================================================================================
class T10ScopeByMode(Stage2Harness):
    def _arm(self, registry):
        self.write_registry(registry)
        self.arm_lease(age_seconds=2 * 24 * 3600)
        self.set_items([item("42")])

    def test_stale_lease_with_mode_line_is_judged(self):
        self._arm(self.stage2())
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("42", r.stderr)

    def test_stale_lease_without_mode_key_contrast_allows(self):
        self._arm(self.stage2(drop=("mode",)))
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.find_anywhere("backlog-checkpoint.json"), [], "scope never went live")

    def test_stale_lease_with_mode_file_lacking_a_mode_line_allows(self):
        self._arm(self.stage2())
        Path(self._p("operating-mode.md")).write_text("no mode line here\n", encoding="utf-8")
        self.assertEqual(self.stop().returncode, 0)


# =====================================================================================================
# T11. escape declaration (aiqt_hooks.py:7841-7901, 8511-8526)
# =====================================================================================================
class T11Escape(Stage2Harness):
    def _arm(self, registry):
        self.write_registry(registry)
        self.arm_lease()
        self.set_items([item("42")])

    def test_declared_relative_path_is_the_one_consulted(self):
        self._arm(self.stage2(escape={"path": "RELEASE-STOP"}))
        self.self_owned_sentinel("RELEASE-STOP")
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        spoof = self.read_json("escape-spoof.json")
        self.assertIsNotNone(spoof, "a self-owned sentinel at the declared path is spoof-recorded")
        self.assertIn("own effective uid", spoof["detail"])

    def test_undeclared_contrast_ignores_the_other_name(self):
        self._arm(self.stage2(drop=("escape",)))
        self.self_owned_sentinel("RELEASE-STOP")
        self.assertEqual(self.stop().returncode, 2)
        self.assertIsNone(self.read_json("escape-spoof.json"), "the default name is consulted instead")

    def test_empty_and_non_string_declarations_disable_the_release_silently(self):
        for value in ("", 5):
            with self.subTest(escape=value):
                self._arm(self.stage2(escape={"path": value}))
                self.self_owned_sentinel("ESCAPE-ALLOW-YIELD")
                spoof = self.state_dir() / "escape-spoof.json"
                if spoof.exists():
                    spoof.unlink()
                self.human_prompt()
                self.assertEqual(self.stop().returncode, 2)
                self.assertFalse(spoof.exists(), "no release and no spoof record (aiqt_hooks.py:7861-7862)")

    def test_undeclared_contrast_consults_the_default_name(self):
        self._arm(self.stage2(drop=("escape",)))
        self.self_owned_sentinel("ESCAPE-ALLOW-YIELD")
        self.assertEqual(self.stop().returncode, 2)
        self.assertIsNotNone(self.read_json("escape-spoof.json"))

    def test_absolute_path_outside_the_anchor_is_rejected(self):
        self._arm(self.stage2(escape={"path": self._p("elsewhere", "SENTINEL")}))
        self.assertEqual(self.stop().returncode, 2)
        spoof = self.state_json("escape-spoof.json")
        self.assertIn("outside the operator-trusted anchor", spoof["detail"])  # aiqt_hooks.py:7870-7871


# =====================================================================================================
# T12. mistakes_register (OPTIONAL KEY, open point P6; aiqt_hooks.py:9677-9693)
# =====================================================================================================
class T12MistakesRegister(Stage2Harness):
    def _audit(self, lines, declare=True):
        path = Path(self._p("mistakes-register.jsonl"))
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        reg = self.stage2(mistakes_register=str(path)) if declare else self.stage2()
        self.write_registry(reg)
        self.arm_lease()
        r = self.run_hook("orch_resume_audit", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, self.state_json("resume-barrier.json")

    @staticmethod
    def _rows(lapse_pointer=None):
        rows = [{"id": "MR-1", "class": "process", "summary": "a recorded mistake"}]
        if lapse_pointer is not None:
            rows.append({"id": "MR-2", "class": "systemic-lapse", "check_ref": lapse_pointer})
        return rows

    def _broken(self):
        lines = chain_lines(self._rows("docs/evidence.md"))
        row = json.loads(lines[1])
        row["prev"] = "f" * 64
        lines[1] = json.dumps(row, sort_keys=True)
        return lines

    def test_valid_chain_audits_clean(self):
        r, barrier = self._audit(chain_lines(self._rows("docs/evidence.md")))
        self.assertEqual(r.stdout.strip(), "")
        self.assertFalse(barrier["active"])

    def test_empty_register_audits_clean(self):
        _r, barrier = self._audit([])
        self.assertFalse(barrier["active"])

    def test_broken_chain_arms_the_barrier(self):
        _r, barrier = self._audit(self._broken())
        self.assertTrue(barrier["active"])
        self.assertTrue(any("mistakes register fails its inline chain" in f for f in barrier["findings"]))

    def test_unresolvable_lapse_pointer_is_a_finding(self):
        _r, barrier = self._audit(chain_lines(self._rows("docs/missing.md")))
        self.assertTrue(barrier["active"])
        self.assertTrue(any("systemic-lapse row MR-2 is unsubstantiated" in f
                            for f in barrier["findings"]))

    def test_undeclared_contrast_audits_clean(self):
        _r, barrier = self._audit(self._broken(), declare=False)
        self.assertFalse(barrier["active"], "an undeclared register is never audited")


# =====================================================================================================
# T13. TeammateIdle mirrors the Stop decision (aiqt_hooks.py:8624-8627)
# =====================================================================================================
class T13TeammateIdle(Stage2Harness):
    def test_actionable_denies(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("42", title="Ship the widget")])
        r = self.run_hook("orch_teammate_idle", {})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("42 (Ship the widget", r.stderr)

    def test_nothing_actionable_allows(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed"), item("2", state="proposed")])
        self.assertEqual(self.run_hook("orch_teammate_idle", {}).returncode, 0)

    def test_stage1_contrast(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        self.assert_no_enumerator_deny(self.run_hook("orch_teammate_idle", {}))


# =====================================================================================================
# T14. Runtime posture pins on malformed stage-2 values inside a registry the hook reads as ok
# =====================================================================================================
class T14PosturePins(Stage2Harness):
    def test_enumerator_argv_not_a_list_denies_closed(self):
        self.write_registry(self.stage2(enumerator={"argv": "python3 -I enum.py", "timeout": 5}))
        self.arm_lease()
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)  # aiqt_hooks.py:7969-7972
        self.assertIn("ENUMERATOR_ERROR", r.stderr)
        self.assertIn("not a list of non-empty strings", r.stderr)

    def test_enumerator_timeout_malformed_still_runs(self):
        # A malformed timeout silently becomes 60 (aiqt_hooks.py:7974); the enumerator still runs.
        self.write_registry(self.stage2(enumerator={
            "argv": [sys.executable, "-I", str(self.enum_script), str(self.backlog)], "timeout": "fast"}))
        self.arm_lease()
        self.set_items([item("42")])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("42 (42: no blocker recorded)", r.stderr)

    def test_yield_tools_not_a_list_allows(self):
        self.write_registry(self.stage2(yield_tools="ScheduleWakeup"))
        self.arm_lease()
        self.set_items([item("42")])
        r = self.schedule()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "a non-list roster is out of scope (aiqt_hooks.py:8666-8667)")

    def test_staleness_malformed_uses_24h(self):
        for age, expected in ((23, 0), (25, 2)):
            with self.subTest(age_hours=age):
                self.write_registry(self.stage2(staleness="x"))
                self.arm_lease()
                self.human_prompt()
                self.seed_ledger([{"event": "launch", "task_id": "task-1", "tool": "Bash", "wake": True,
                                   "ts": _iso(-age)}])
                self.set_items([item("8", blocker={"kind": "tracked-task", "ref": "task-1"})])
                self.assertEqual(self.stop().returncode, expected)

    def test_escape_non_string_gives_no_release_and_no_record(self):
        self.write_registry(self.stage2(escape={"path": 5}))
        self.arm_lease()
        self.set_items([item("42")])
        self.self_owned_sentinel("ESCAPE-ALLOW-YIELD")
        self.assertEqual(self.stop().returncode, 2)
        self.assertIsNone(self.read_json("escape-spoof.json"))

    def test_stage1_contrast(self):
        # The stage-1 registry has no enumerator: NO_ENUMERATOR, never ENUMERATOR_ERROR, and the 23 h
        # launch that stage 2 accepts cannot excuse the Stop.
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.stop()
        self.assert_no_enumerator_deny(r)
        self.assertNotIn("ENUMERATOR_ERROR", r.stderr)


# =====================================================================================================
# T15. Enumerator timeout yields ENUMERATOR_ERROR, never a hang (aiqt_hooks.py:7974-7978)
# =====================================================================================================
class T15EnumeratorTimeout(Stage2Harness):
    def test_sleeping_enumerator_times_out_and_denies(self):
        self.write_registry(self.stage2(enumerator={
            "argv": [sys.executable, "-I", "-c", "import time; time.sleep(30)"], "timeout": 1}))
        self.arm_lease()
        started = time.monotonic()
        r = self.stop()
        elapsed = time.monotonic() - started
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ENUMERATOR_ERROR", r.stderr)
        self.assertIn("failed to run", r.stderr)
        self.assertLess(elapsed, 15, "the declared timeout bounds the hook")

    def test_stage1_contrast(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.stop()
        self.assert_no_enumerator_deny(r)
        self.assertNotIn("failed to run", r.stderr)


# =====================================================================================================
# PR1-f. tools/orch_doctor.py: preflight writes nothing; --resume-audit rewrites the barrier
# =====================================================================================================
class Doctor(Stage2Harness):
    def setUp(self):
        super().setUp()
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))

    def _fresh_doctor_root(self):
        """A copy of the doctor in <fresh>/tools beside a copy of the hook at the path the doctor
        derives from its own location, in a directory that has never held a __pycache__, so a bytecode
        cache the doctor import writes beside the hook is observable (finding T3). Returns (fresh root,
        doctor copy)."""
        fresh = self._tmp / "fresh-root"
        tooldir = fresh / "tools"
        hookdir = fresh / HOOK.relative_to(REPO_ROOT).parent
        tooldir.mkdir(parents=True)
        hookdir.mkdir(parents=True)
        shutil.copyfile(HOOK, hookdir / HOOK.name)
        copy = tooldir / DOCTOR.name
        shutil.copyfile(DOCTOR, copy)
        return fresh, copy

    @staticmethod
    def _bytecode_under(path):
        return sorted(os.path.join(d, f) for d, _dirs, files in os.walk(path)
                      for f in files if f.endswith((".pyc", ".pyo")))

    def test_preflight_writes_nothing(self):
        # The doctor runs from a fresh copy whose tree has never held a __pycache__, so an import of the
        # hook that wrote bytecode (sys.dont_write_bytecode unset in _load_hook) shows as a new .pyc
        # file anywhere under it, and as a change in the tree state.
        fresh, copy = self._fresh_doctor_root()
        self.assertEqual(self._bytecode_under(fresh), [], "precondition: no bytecode in the fresh tree")
        self.assertFalse(any(Path(d).name == "__pycache__" for d, _s, _f in os.walk(fresh)),
                         "precondition: no __pycache__ in the fresh tree")
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("9")])
        self.assertEqual(self.stop().returncode, 2)  # a real window: checkpoint, marker, turn-state
        self.set_items([])  # item 9 now vanishes without a receipt
        before = tree_state(self._tmp)
        for kind in ("stop", "idle"):
            with self.subTest(kind=kind):
                r = subprocess.run([sys.executable, "-I", str(copy), "preflight", kind,
                                    "--root", str(self.repo)],
                                   capture_output=True, text=True, env=self._env(), timeout=120)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("judged verdict: DENY", r.stdout)
                self.assertIn("verdict without the escape sentinel: DENY", r.stdout)
                self.assertIn("vanished from the enumeration without a close receipt", r.stdout)
        self.assertEqual(self._bytecode_under(fresh), [], "preflight wrote a bytecode cache")
        self.assertEqual(tree_state(self._tmp), before, "preflight changed a file or directory")

    # --- T1: a declared read path that is not a regular file is cannot-evaluate, before any hook reader
    SPECIAL_TIMEOUT = 30

    def _doctor_bounded(self, *args):
        try:
            return subprocess.run([sys.executable, "-I", str(DOCTOR), *args, "--root", str(self.repo)],
                                  capture_output=True, text=True, env=self._env(),
                                  timeout=self.SPECIAL_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the doctor did not exit within {} s: a hook reader blocked on a special file"
                      .format(self.SPECIAL_TIMEOUT))

    def _make_special(self, path, kind):
        """Replace path with a FIFO, a directory, or a symlink to a FIFO; return the type the doctor
        must name (os.stat follows the symlink, as the hook open would)."""
        path = Path(path)
        if path.is_symlink() or path.is_file():
            path.unlink()
        if kind == "fifo":
            os.mkfifo(path)
            return "FIFO"
        if kind == "directory":
            path.mkdir()
            return "directory"
        target = self._tmp / "fifo-target"
        os.mkfifo(target)
        os.symlink(target, path)
        return "FIFO"

    def _assert_special_refused(self, label, path, kind, *doctor_args):
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(reg)
        self.set_items([item("42")])
        named = self._make_special(path, kind)
        before = tree_state(self._tmp)
        r = self._doctor_bounded(*doctor_args)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("cannot evaluate: the declared {} {} is not a regular file (it is a {})"
                      .format(label, path, named), r.stdout)
        self.assertIn("the hook reader that opens it was not called and no enumerator ran", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(marker.exists(), "the enumerator ran")
        self.assertFalse(self.state_dir().exists(), "a hook state write happened")
        self.assertEqual(tree_state(self._tmp), before, "the doctor changed a file or directory")

    def test_preflight_special_mode_path_is_cannot_evaluate(self):
        # No lease, so scope falls through to the mode read, a plain blocking open
        # (aiqt_hooks.py:7817 and 7771): a FIFO there would hang the doctor.
        for kind in ("fifo", "directory", "symlink-to-fifo"):
            with self.subTest(kind=kind):
                self.tearDown()
                self.setUp()
                self._assert_special_refused("mode.path", self._p("operating-mode.md"), kind,
                                             "preflight", "stop")

    def test_preflight_special_lease_path_is_cannot_evaluate(self):
        for kind in ("fifo", "directory", "symlink-to-fifo"):
            with self.subTest(kind=kind):
                self.tearDown()
                self.setUp()
                self._assert_special_refused("lease.path", self._p("session-state.md"), kind,
                                             "preflight", "stop")

    def test_preflight_idle_special_mode_path_is_cannot_evaluate(self):
        self._assert_special_refused("mode.path", self._p("operating-mode.md"), "fifo",
                                     "preflight", "idle")

    def test_preflight_special_backlog_operand_is_cannot_evaluate(self):
        self._assert_special_refused("enumerator.argv[3]", str(self.backlog), "fifo",
                                     "preflight", "stop")

    def test_resume_audit_special_handoff_is_cannot_evaluate(self):
        # The resume probes open the declared handoff with a plain blocking open
        # (aiqt_hooks.py:9356-9359), so a FIFO there would hang the audit.
        self._assert_special_refused("record.handoff", self._p("session-handoff.md"), "fifo",
                                     "--resume-audit")

    # --- round 6 U1: the fixed hook state files are checked too, per command -----------------------
    # The state files _orch_build_ctx opens with a plain blocking open (turn-state.json at
    # aiqt_hooks.py:7745, dispatch-ledger.jsonl at 7998 and 7678, backlog-checkpoint.json at 8365, and
    # with attestations declared attestations-validated.json at 8073 and guard-events.jsonl at 9566).
    PREFLIGHT_STATE_FILES = ("turn-state.json", "dispatch-ledger.jsonl", "backlog-checkpoint.json",
                             "attestations-validated.json", "guard-events.jsonl")
    # The state files orch_resume_audit opens with a plain blocking open (guard-events.jsonl at 9566 and
    # 7667, escape-spoof.json at 9748, forced-exit.jsonl at 9705 and 7678, forced-exit-surfaced.json at
    # 9717, and the temporary files _orch_write_json_atomic opens for writing at 7720, via 9734 and,
    # with attestations declared, via 9670).
    AUDIT_STATE_FILES = ("guard-events.jsonl", "escape-spoof.json", "forced-exit.jsonl",
                         "forced-exit-surfaced.json", "forced-exit-surfaced.json.tmp",
                         "attestations-validated.json.tmp")

    def _with_attestations(self, reg):
        # A declared attestations register, absent on disk (an open the hook raises on, never blocks
        # on): the condition the hook tests before it opens the attestation state files
        # (aiqt_hooks.py:8068-8070 for the preview, 9638-9640 for the audit).
        reg["attestations"] = self._p("attestations.jsonl")
        return reg

    def _make_state_fifo(self, name):
        self.state_dir().mkdir(parents=True, exist_ok=True)
        path = self.state_dir() / name
        os.mkfifo(path)
        return path

    def _assert_state_special_refused(self, name, *doctor_args):
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(self._with_attestations(reg))
        self.set_items([item("42")])
        path = self._make_state_fifo(name)
        before = tree_state(self._tmp)
        r = self._doctor_bounded(*doctor_args)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("cannot evaluate: the hook state file {} {} is not a regular file (it is a "
                      "FIFO)".format(name, path), r.stdout)
        self.assertIn("the hook reader that opens it was not called and no enumerator ran", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(marker.exists(), "the enumerator ran")
        self.assertEqual(tree_state(self._tmp), before, "a file or directory changed")

    def test_preflight_special_state_file_is_cannot_evaluate(self):
        # Scope is live through the mode line, so the preview reaches _orch_build_ctx, whose readers
        # would block on each of these (a FIFO turn-state.json made the preview hang before round 6).
        for kind in ("stop", "idle"):
            for name in self.PREFLIGHT_STATE_FILES:
                with self.subTest(kind=kind, name=name):
                    self.tearDown()
                    self.setUp()
                    self._assert_state_special_refused(name, "preflight", kind)

    def test_resume_audit_special_state_file_is_cannot_evaluate(self):
        for name in self.AUDIT_STATE_FILES:
            with self.subTest(name=name):
                self.tearDown()
                self.setUp()
                self._assert_state_special_refused(name, "--resume-audit")

    def test_resume_audit_on_an_unreadable_registry_checks_its_state_files(self):
        # On an unreadable registry the hook appends to resume-barrier.json.unused beside the barrier
        # (aiqt_hooks.py:9777, opened at 7667) under the default state directory (9775).
        (self.repo / ".aiqt").mkdir(exist_ok=True)
        (self.repo / ".aiqt" / "orchestration.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.run_hook("orch_resume_audit", {}).returncode, 0)
        barriers = self.find_anywhere("resume-barrier.json")
        self.assertEqual(len(barriers), 1, "precondition: the hook wrote one barrier")
        path = Path(barriers[0]).parent / "resume-barrier.json.unused"
        path.unlink()
        os.mkfifo(path)
        r = self._doctor_bounded("--resume-audit")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("cannot evaluate: the hook state file resume-barrier.json.unused {} is not a "
                      "regular file (it is a FIFO)".format(path), r.stdout)

    # --- round 6 U2: each command checks only what its own hook call path opens --------------------
    def test_fifo_backlog_operand_refuses_preflight_but_not_the_resume_audit(self):
        # The resume probes run no enumerator (aiqt_hooks.py:9351-9413), so the hook audits with a
        # FIFO backlog operand, and so must the doctor; the preview runs the enumerator (7976), so it
        # still refuses.
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(reg)
        self.backlog.unlink()
        os.mkfifo(self.backlog)
        r = self._doctor_bounded("--resume-audit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("cannot evaluate", r.stdout)
        self.assertIn("barrier: clear", r.stdout)
        self.assertFalse(self.state_json("resume-barrier.json")["active"])
        self.assertTrue(self.backlog.is_fifo(), "the audit left the operand alone")
        self.assertFalse(marker.exists(), "the audit ran the enumerator")
        p = self._doctor_bounded("preflight", "stop")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("cannot evaluate: the declared enumerator.argv[3] {} is not a regular file "
                      "(it is a FIFO)".format(self.backlog), p.stdout)
        self.assertFalse(marker.exists(), "the refused preview ran the enumerator")

    def test_resume_audit_runs_past_paths_only_the_preview_opens(self):
        # The audit stats the lease only (aiqt_hooks.py:9398) and never opens the mode record or the
        # preview state files, so a FIFO at any of them leaves the audit to run and rewrite the barrier.
        cases = [("mode.path", lambda: Path(self._p("operating-mode.md"))),
                 ("lease.path", lambda: Path(self._p("session-state.md")))]
        cases += [(name, lambda name=name: self.state_dir() / name)
                  for name in ("turn-state.json", "dispatch-ledger.jsonl", "backlog-checkpoint.json")]
        for label, where in cases:
            with self.subTest(path=label):
                self.tearDown()
                self.setUp()
                self.write_registry(self.stage2())
                path = where()
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    path.unlink()
                os.mkfifo(path)
                r = self._doctor_bounded("--resume-audit")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn("cannot evaluate", r.stdout)
                self.assertIn("barrier: clear", r.stdout)
                self.assertTrue(path.is_fifo(), "the audit left the FIFO alone")

    def test_preflight_runs_past_paths_only_the_audit_opens(self):
        # The preview never opens the handoff or findings records, the mistakes register, or the audit
        # state files, so a FIFO at any of them leaves the preview to judge (here a DENY on item 42).
        cases = [("record.handoff", lambda: Path(self._p("session-handoff.md"))),
                 ("record.findings", lambda: Path(self._p("open-findings.md"))),
                 ("mistakes_register", lambda: Path(self._p("mistakes.jsonl")))]
        cases += [(name, lambda name=name: self.state_dir() / name)
                  for name in ("escape-spoof.json", "forced-exit.jsonl", "forced-exit-surfaced.json",
                               "resume-barrier.json")]
        for label, where in cases:
            for kind in ("stop", "idle"):
                with self.subTest(path=label, kind=kind):
                    self.tearDown()
                    self.setUp()
                    self.write_registry(self.stage2(mistakes_register=self._p("mistakes.jsonl")))
                    self.set_items([item("42")])
                    path = where()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        path.unlink()
                    os.mkfifo(path)
                    r = self._doctor_bounded("preflight", kind)
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertNotIn("cannot evaluate", r.stdout)
                    self.assertIn("judged verdict: DENY", r.stdout)

    def test_out_of_scope_preflight_runs_past_a_fifo_turn_state(self):
        # Out of scope the hook returns before _orch_build_ctx (aiqt_hooks.py:8584-8585 and
        # 8662-8663), so it never opens turn-state.json, and the preview reports the same ALLOW.
        reg, marker = self._arm_writing_enumerator()
        reg.pop("mode")
        self.write_registry(reg)
        self.arm_lease(age_seconds=2 * 24 * 3600)
        self.set_items([item("42")])
        self._make_state_fifo("turn-state.json")
        for kind in ("stop", "idle"):
            with self.subTest(kind=kind):
                r = self._doctor_bounded("preflight", kind)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn("cannot evaluate", r.stdout)
                self.assertIn("effective verdict: ALLOW (out of scope)", r.stdout)
                self.assertFalse(marker.exists())

    def test_special_registry_file_is_cannot_evaluate(self):
        # The hook reads the registry with a plain blocking open (aiqt_hooks.py:7606-7620), the
        # machine-local file first (aiqt_hooks.py:7548).
        self.write_registry(self.stage2())
        local = self.repo / ".aiqt" / "orchestration.local.json"
        os.mkfifo(local)
        for args in (("preflight", "stop"), ("--resume-audit",)):
            with self.subTest(args=args):
                r = self._doctor_bounded(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("cannot evaluate: the registry file {} is not a regular file (it is a "
                              "FIFO)".format(local), r.stdout)
                self.assertFalse(self.state_dir().exists(), "a hook state write happened")

    def test_absent_declared_paths_are_left_to_the_hook(self):
        # Contrast: absent mode, lease, and record paths are not special files, so the doctor reaches
        # the hook readers and reports the out-of-scope ALLOW the hook gives.
        self.write_registry(self.stage2())
        for name in ("operating-mode.md", "session-handoff.md", "open-findings.md",
                     "pending-decisions.md"):
            Path(self._p(name)).unlink()
        r = self._doctor_bounded("preflight", "stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("scope: not live", r.stdout)
        self.assertNotIn("cannot evaluate", r.stdout)

    def test_preflight_does_not_create_the_state_dir(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("effective verdict: ALLOW", r.stdout)
        self.assertFalse(self.state_dir().exists())

    def test_preflight_out_of_scope_allows(self):
        self.write_registry(self.stage2(drop=("mode",)))
        self.arm_lease(age_seconds=2 * 24 * 3600)
        self.set_items([item("42")])
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("scope: not live", r.stdout)
        self.assertIn("effective verdict: ALLOW", r.stdout)

    # --- R3: the doctor decides scope first and, out of scope, runs no enumerator ----------------
    def _arm_writing_enumerator(self, **overrides):
        script = self._tmp / "enum_writing.py"
        script.write_text(WRITING_ENUM_FIXTURE, encoding="utf-8")
        marker = self._tmp / "enumerator-ran.txt"
        reg = self.stage2(enumerator={
            "argv": [sys.executable, "-I", str(script), str(self.backlog), str(marker)],
            "timeout": 5}, **overrides)
        return reg, marker

    def test_preflight_out_of_scope_runs_no_enumerator(self):
        # The Stop hook returns before it enumerates when scope is not live (aiqt_hooks.py:8584-8585),
        # and so does the scheduling hook (aiqt_hooks.py:8662-8663); a preview that ran the
        # enumerator there could change what a later Stop decides.
        reg, marker = self._arm_writing_enumerator()
        reg.pop("mode")
        self.write_registry(reg)
        self.arm_lease(age_seconds=2 * 24 * 3600)
        self.set_items([item("42")])
        # Precondition: out of scope the hook allows both calls and runs no enumerator.
        self.assertEqual(self.stop().returncode, 0)
        self.assertEqual(self.schedule().stdout.strip(), "")
        self.assertFalse(marker.exists(), "precondition: the hook runs no enumerator out of scope")
        for kind in ("stop", "idle"):
            with self.subTest(kind=kind):
                r = self.run_doctor("preflight", kind)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("scope: not live", r.stdout)
                self.assertIn("enumeration: not run", r.stdout)
                self.assertIn("effective verdict: ALLOW", r.stdout)
                self.assertFalse(marker.exists(), "an out-of-scope preflight ran the enumerator")

    def test_preflight_idle_out_of_the_roster_runs_no_enumerator(self):
        # The scheduling hook returns before it enumerates for a tool outside the roster
        # (aiqt_hooks.py:8664-8667).
        reg, marker = self._arm_writing_enumerator(yield_tools=["CronCreate"])
        self.write_registry(reg)
        self.arm_lease()
        self.set_items([item("42")])
        # Precondition: the hook allows the call unjudged and runs no enumerator.
        self.assertEqual(self.schedule(tool="ScheduleWakeup").stdout.strip(), "")
        self.assertFalse(marker.exists(), "precondition: the hook runs no enumerator out of roster")
        r = self.run_doctor("preflight", "idle")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tool ScheduleWakeup: not in the roster", r.stdout)
        self.assertIn("enumeration: not run", r.stdout)
        self.assertIn("effective verdict: ALLOW", r.stdout)
        self.assertFalse(marker.exists(), "an out-of-roster preflight ran the enumerator")

    def test_preflight_in_scope_runs_the_enumerator_contrast(self):
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(reg)
        self.arm_lease()
        self.set_items([item("42")])
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("scope: live", r.stdout)
        self.assertEqual(marker.read_text(encoding="utf-8"), "ran\n")

    # --- R6: the doctor re-executes itself isolated, and a failed re-execution exits 2 ------------
    def test_reexecutes_isolated_so_a_planted_module_cannot_shadow_the_stdlib(self):
        # A copy of the doctor in a tools/ directory beside a copy of the hook at the path the
        # doctor derives from its own location, with a planted json.py next to the copy.
        fake = self._tmp / "fake-root"
        tooldir = fake / "tools"
        hookdir = fake / HOOK.relative_to(REPO_ROOT).parent
        tooldir.mkdir(parents=True)
        hookdir.mkdir(parents=True)
        shutil.copyfile(HOOK, hookdir / HOOK.name)
        copy = tooldir / DOCTOR.name
        shutil.copyfile(DOCTOR, copy)
        (tooldir / "json.py").write_text("raise SystemExit(97)\n", encoding="utf-8")
        (tooldir / "probe.py").write_text("import json\n", encoding="utf-8")
        env = self._env()
        env.pop("PYTHONSAFEPATH", None)
        probe = subprocess.run([sys.executable, str(tooldir / "probe.py")], capture_output=True,
                               text=True, env=env, timeout=60)
        self.assertEqual(probe.returncode, 97, "precondition: the planted module shadows json")
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        r = subprocess.run([sys.executable, str(copy), "preflight", "stop", "--root", str(self.repo)],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("effective verdict: ALLOW", r.stdout)

    def test_a_failed_reexecution_exits_2_with_a_message(self):
        missing = self._tmp / "no-such-python"
        self.assertFalse(missing.exists(), "precondition: the interpreter path is absent")
        env = self._env()
        env.pop("PYTHONSAFEPATH", None)
        r = subprocess.run([sys.executable, "-c", FAILED_REEXEC_PROG, str(DOCTOR), str(missing)],
                           capture_output=True, text=True, env=env, cwd=str(self._tmp), timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("orch_doctor.py: cannot re-execute under python3 -I", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_resume_audit_clean_clears_the_barrier(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.seed_state("resume-barrier.json", {"active": True, "findings": ["seeded"],
                                                "ts": _iso(), "warned": False})
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.state_json("resume-barrier.json")["active"])

    def test_resume_audit_wrong_branch_arms_the_barrier(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.write_record_files(handoff="Branch: some-other-branch\n")
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("some-other-branch", r.stdout)
        self.assertTrue(self.state_json("resume-barrier.json")["active"])

    def test_usage_error(self):
        r = subprocess.run([sys.executable, "-I", str(DOCTOR)], capture_output=True, text=True,
                           env=self._env(), timeout=60)
        self.assertEqual(r.returncode, 2)

    # --- F4: the doctor writes nothing itself; the declared enumerator runs as the hook runs it ---
    def test_preflight_discloses_that_the_declared_enumerator_runs(self):
        self.assertIn("mark.write", WRITING_ENUM_FIXTURE, "precondition: the fixture writes")
        script = self._tmp / "enum_writing.py"
        script.write_text(WRITING_ENUM_FIXTURE, encoding="utf-8")
        marker = self._tmp / "enumerator-ran.txt"
        self.write_registry(self.stage2(enumerator={
            "argv": [sys.executable, "-I", str(script), str(self.backlog), str(marker)],
            "timeout": 5}))
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("writes: the doctor itself wrote nothing; the registry enumerator ran as the "
                      "hook runs it", r.stdout)
        self.assertEqual(marker.read_text(encoding="utf-8"), "ran\n",
                         "the declared enumerator ran once, and its write is its own")
        self.assertFalse(self.state_dir().exists(), "the doctor wrote nothing under state_dir")

    # --- F5: roster membership exactly as the hook tests it; the quiet claim is not previewed -----
    def _arm_idle(self, roster):
        self.write_registry(self.stage2(yield_tools=roster))
        self.arm_lease()
        self.set_items([item("42", title="Ship the widget")])

    def test_preflight_idle_tool_outside_the_roster_allows_as_the_hook_does(self):
        self._arm_idle(["CronCreate"])
        r = self.run_doctor("preflight", "idle")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tool ScheduleWakeup: not in the roster", r.stdout)
        self.assertIn("effective verdict: ALLOW", r.stdout)
        h = self.schedule(tool="ScheduleWakeup")
        self.assertEqual(h.returncode, 0, h.stderr)
        self.assertEqual(h.stdout.strip(), "", "the hook allows the same call unjudged")

    def test_preflight_idle_named_tool_in_the_roster_denies_as_the_hook_does(self):
        self._arm_idle(["CronCreate"])
        r = self.run_doctor("preflight", "idle", "--tool", "CronCreate")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("tool CronCreate: in the roster, judged", r.stdout)
        self.assertIn("effective verdict: DENY", r.stdout)
        out = self.verdict_json(self.schedule(tool="CronCreate"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_preflight_idle_empty_roster_allows_as_the_hook_does(self):
        self._arm_idle([])
        r = self.run_doctor("preflight", "idle")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("yield_tools roster: (empty)", r.stdout)
        self.assertIn("effective verdict: ALLOW", r.stdout)
        self.assertEqual(self.schedule().stdout.strip(), "")

    def test_preflight_idle_quiet_claim_is_not_previewed(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        self.seed_state("turn-state.json", {"last_human_input_utc": _iso(-5 / 60.0)})
        claim = "quiet for 90 minutes, recheck the queue"
        r = self.run_doctor("preflight", "idle", "--wake-text", claim)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("quiet-claim check: NOT PREVIEWED", r.stdout)
        self.assertIn("effective verdict: UNPREVIEWED (ALLOW", r.stdout)
        # The real hook denies the same call on the claim, so an ALLOW preview would be false.
        out = self.verdict_json(self.schedule({"prompt": claim, "delaySeconds": 60}))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("quiet minutes", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_preflight_idle_without_a_quiet_claim_allows(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        r = self.run_doctor("preflight", "idle", "--wake-text", "recheck the queue in 5 minutes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the check does not fire", r.stdout)
        self.assertIn("effective verdict: ALLOW", r.stdout)

    def test_tool_outside_preflight_idle_is_a_usage_error(self):
        self.write_registry(self.stage2())
        for args in (("preflight", "stop", "--tool", "CronCreate"),
                     ("--resume-audit", "--tool", "CronCreate"),
                     ("preflight", "idle", "--tool", "")):
            with self.subTest(args=args):
                r = self.run_doctor(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("--tool", r.stderr)

    # --- G4: a Stop DENY whose denial counter cannot be saved fails open in the hook ------------
    def _arm_actionable_stop(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("7", title="Ship the widget")])

    def _assert_doctor_reports_the_fail_open_allow(self):
        before = tree_state(self._tmp)
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(tree_state(self._tmp), before, "preflight changed a file or directory")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("judged verdict: DENY", r.stdout)
        self.assertIn("denial counter: could NOT be saved", r.stdout)
        self.assertIn("effective verdict: ALLOW_WITH_FINDINGS (the fail-open allow", r.stdout)
        self.assertNotIn("effective verdict: DENY", r.stdout)
        # The real hook on the same state: exit 0 with the fail-open warning, not the exit 2 deny
        # (aiqt_hooks.py:8590-8596).
        h = self.stop()
        self.assertEqual(h.returncode, 0, h.stderr)
        self.assertIn("the denial counter could not be persisted",
                      self.verdict_json(h)["systemMessage"])

    def test_preflight_stop_with_an_unwritable_state_dir_reports_the_fail_open_allow(self):
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0555 directory, so the save cannot fail here")
        self._arm_actionable_stop()
        sd = self.state_dir()
        sd.mkdir(parents=True)
        os.chmod(sd, 0o555)
        self._assert_doctor_reports_the_fail_open_allow()

    def test_preflight_stop_with_a_read_only_turn_state_reports_the_fail_open_allow(self):
        if os.geteuid() == 0:
            self.skipTest("root writes a mode-0444 file, so the save cannot fail here")
        self._arm_actionable_stop()
        self.seed_state("turn-state.json", {})
        os.chmod(self.state_dir() / "turn-state.json", 0o444)
        self._assert_doctor_reports_the_fail_open_allow()

    def test_preflight_stop_with_a_saveable_counter_reports_the_deny(self):
        # Contrast: the state dir is absent but creatable, so the hook saves the counter and denies.
        self._arm_actionable_stop()
        self.assertFalse(self.state_dir().exists(), "precondition: no state dir yet")
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("denial counter: could be saved", r.stdout)
        self.assertIn("effective verdict: DENY", r.stdout)
        self.assertFalse(self.state_dir().exists(), "the doctor created no state dir")
        self.assertEqual(self.stop().returncode, 2)

    # --- G7: the help text says what preflight writes, and what it runs -------------------------
    def test_help_text_says_the_doctor_writes_nothing_and_the_enumerator_runs(self):
        r = subprocess.run([sys.executable, "-I", str(DOCTOR), "--help"], capture_output=True,
                           text=True, env=self._env(), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = " ".join(r.stdout.split())
        self.assertIn("the doctor itself writes nothing", text)
        self.assertIn("the declared enumerator runs as the hook runs it", text)
        self.assertNotIn("without writing anything", text)

    # --- F2: the resume audit requires that the hook rewrote the barrier during this run ---------
    def _read_only_stale_barrier(self, active):
        self.seed_state("resume-barrier.json", {"active": active,
                                                "findings": ["seeded"] if active else [],
                                                "ts": _iso(-48), "warned": False})
        path = self.state_dir() / "resume-barrier.json"
        os.chmod(path, 0o444)
        return path, path.read_bytes()

    def test_resume_audit_read_only_stale_clear_barrier_is_unverified(self):
        if os.geteuid() == 0:
            self.skipTest("root writes a mode-0444 file, so the read-only case cannot arise")
        self.write_registry(self.stage2())
        self.arm_lease()
        self.write_record_files(handoff="Branch: some-other-branch\n")  # a real audit would arm
        path, before = self._read_only_stale_barrier(False)
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("NOT rewritten by this audit", r.stdout)
        self.assertNotIn("barrier: clear", r.stdout)
        self.assertEqual(path.read_bytes(), before, "precondition: the hook could not rewrite it")

    def test_resume_audit_read_only_stale_active_barrier_is_unverified(self):
        if os.geteuid() == 0:
            self.skipTest("root writes a mode-0444 file, so the read-only case cannot arise")
        self.write_registry(self.stage2())
        self.arm_lease()
        path, before = self._read_only_stale_barrier(True)
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("NOT rewritten by this audit", r.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_resume_audit_rewrite_with_a_ts_outside_the_run_is_unverified(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        r = subprocess.run([sys.executable, "-I", "-c", STALE_TS_PROG, str(DOCTOR), str(self.repo)],
                           capture_output=True, text=True, env=self._env(), timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("is not from this audit run", r.stdout)
        self.assertFalse(self.state_json("resume-barrier.json")["active"],
                         "precondition: the barrier was rewritten, and reads clear")

    # --- S3: the barrier is read only as a regular file, without blocking -------------------------
    BARRIER_TIMEOUT = 60

    def _audit_bounded(self):
        try:
            return subprocess.run([sys.executable, "-I", str(DOCTOR), "--resume-audit", "--root",
                                   str(self.repo)], capture_output=True, text=True, env=self._env(),
                                  timeout=self.BARRIER_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the doctor did not exit within {} s: the barrier open blocked"
                      .format(self.BARRIER_TIMEOUT))

    def _assert_barrier_refused(self, kind):
        r = self._audit_bounded()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("barrier: cannot be recorded before the audit", r.stdout)
        self.assertIn("{} is not a regular file (it is a {})".format(
            self.state_dir() / "resume-barrier.json", kind), r.stdout)
        return r

    def _barrier_path(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.state_dir().mkdir(parents=True, exist_ok=True)
        return self.state_dir() / "resume-barrier.json"

    def test_resume_audit_fifo_barrier_fails_closed_promptly(self):
        path = self._barrier_path()
        os.mkfifo(path)
        self._assert_barrier_refused("FIFO")
        self.assertFalse(os.path.isfile(path), "the audit did not run, so nothing replaced the FIFO")

    def test_resume_audit_directory_barrier_fails_closed(self):
        path = self._barrier_path()
        path.mkdir()
        self._assert_barrier_refused("directory")

    def test_resume_audit_dev_null_barrier_fails_closed(self):
        if not os.path.exists(os.devnull):
            self.fail("{} is absent, so the device case cannot run".format(os.devnull))
        path = self._barrier_path()
        os.symlink(os.devnull, path)
        self._assert_barrier_refused("character device")
        self.assertTrue(os.path.islink(path), "the audit did not run, so the symlink is untouched")


# Every name that opens or reads a path; a reference to any of them, called, aliased or imported,
# counts, so a bare alias such as "f = os.open" cannot slip past the probe.
OPENERS = ("open", "fdopen", "read_text", "read_bytes", "write_text", "write_bytes")


def opener_references(source):
    """(enclosing function, dotted name) for every reference to an opener in source, in order."""
    found = []

    def dotted(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return dotted(node.value) + "." + node.attr
        return "?"

    def visit(node, func):
        for child in ast.iter_child_nodes(node):
            inner = func
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = child.name
            if isinstance(child, ast.Name) and child.id in OPENERS:
                found.append((func, child.id))
            elif isinstance(child, ast.Attribute) and child.attr in OPENERS:
                found.append((func, dotted(child)))
            elif isinstance(child, ast.alias) and child.name.split(".")[-1] in OPENERS:
                found.append((func, "import " + child.name))
            visit(child, inner)

    visit(ast.parse(source), "<module>")
    return found


def opener_call_tokens(source):
    """The number of opener names followed by "(" in the code tokens (strings and comments are not
    code), an independent count of the textual open( calls."""
    toks = [t for t in tokenize.generate_tokens(io.StringIO(source).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                              tokenize.DEDENT)]
    return sum(1 for a, b in zip(toks, toks[1:])
               if a.type == tokenize.NAME and a.string in OPENERS
               and b.type == tokenize.OP and b.string == "(")


class DoctorSourceProbe(unittest.TestCase):
    """Class probe for finding S3: every path the doctor itself opens goes through _read_regular."""

    def test_every_open_in_the_doctor_goes_through_the_checked_helper(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        source = DOCTOR.read_text(encoding="utf-8")
        self.assertEqual(opener_references(source), [("_read_regular", "os.open")],
                         "an open outside the checked helper _read_regular")
        self.assertEqual(opener_call_tokens(source), 1, "a textual open( call outside the helper")
        helper = next(node for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.FunctionDef) and node.name == "_read_regular")
        names = {n.attr for n in ast.walk(helper) if isinstance(n, ast.Attribute)}
        for needed in ("O_NONBLOCK", "O_CLOEXEC", "fstat", "S_ISREG", "set_blocking"):
            self.assertIn(needed, names, "the checked helper no longer uses {}".format(needed))


if __name__ == "__main__":
    unittest.main()
