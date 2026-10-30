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
plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py at source, and the per-test comments and
docstrings cite the code each relies on by symbol, never by line number: the file name aiqt_hooks.py, a
colon and a top-level name of the hook, optionally followed by a backticked clause, which
tools/test-hook-citations.py resolves against the vendored hook. The PR1-f doctor tests at the end drive
tools/orch_doctor.py the same way. A
missing required input (the installed hook or the doctor) fails the test rather than skipping it, so
an absent file can never read as a green run. The doctor tests also prove that a preflight out of
scope, or for idle out of the roster, runs no enumerator, as the hook runs none there,
and that the doctor re-executes itself under python3 -I and exits 2 with a message when that
re-execution fails. The doctor reads the resume barrier only as a regular file: a
barrier that is a FIFO with no writer, a directory, or a symlink to /dev/null is reported as
cannot-evaluate, exit 2, within a short timeout and naming the path and the file type, and the audit
is not run, and a class probe scans the doctor source so that every path it opens goes through its
checked helper. Before any hook reader is called, a registry file or a declared read path
(the mode and lease paths, the record paths, the enumerator operands) that exists and is not a regular
file, a FIFO, a directory, or a symlink to a FIFO, is reported as cannot-evaluate, exit 2, within a
short timeout, with no enumerator run and no hook state written. The writes-nothing test
runs a fresh copy of the doctor and the hook, in a tree that never held a __pycache__, and asserts no
bytecode file appears anywhere under it. The fixed hook state files each command opens
with a plain blocking open are checked the same way before the reader that opens them: for preflight
turn-state.json, dispatch-ledger.jsonl, backlog-checkpoint.json and, with attestations declared,
attestations-validated.json and guard-events.jsonl; for the resume audit guard-events.jsonl,
escape-spoof.json, the forced-exit files and the attestation snapshot temporary file, and with an
unreadable registry resume-barrier.json.unused. Each command checks only what its own
hook call path opens: a FIFO backlog operand, mode record, lease or preview state file does not refuse
the resume audit, which runs and rewrites the barrier, and a FIFO audit-only record or state file, or
an out-of-scope preview with a FIFO turn-state.json, does not refuse the preview.
Each pre-check site checks its path only when the hook call path reaches the open: the
PRECHECK_SITES table lists every _site call in the doctor with its reachability
condition and hook citation, a source probe keeps the table and the doctor in step, and for each
site with an earlier exit a contrast case puts a FIFO where the hook takes that exit and requires
that the doctor runs and that the same hook call path completes, beside the case in which the open
is reached and the doctor refuses. The DoctorScopeMargin cases prove that a lease within
SCOPE_MARGIN seconds of either freshness bound the hook applies, the max_age_hours upper bound and
the clock-skew lower bound for a future mtime, makes the doctor check both scope opens, the holder
lease and the mode record, refusing a special file at either; each case goes red with
SCOPE_MARGIN = 0.0. The DoctorEventFields cases prove that the doctor previews every
event field that can change the verdict exactly as the hook reads it: a Stop whose stop_hook_active
is true, a scheduling call whose tool_input stop is true (judged as kind stop), both together, and
stop_hook_active on a schedule_idle call, which is no loop signal, each compared with the verdict
of the real hook on the same state, and a scheduling DENY on the stop kind that stands when the
denial counter cannot be saved. The DoctorEventFieldProbe case is the class probe for that finding:
it scans the hook source, from each previewed handler through every module function the event data
is passed to, for every field of the event and of its tool_input that is read, and requires the set
of fields and the hook functions that read them to equal the reviewed EVENT_FIELDS table, each field either
modelled by a named doctor input or unpreviewed with a reason; any other use of the event data (a
computed key, an alias, a pass to an unknown callee) fails it, and it proves that it refuses one
mutation of each kind.
The DoctorCheckpointWrites cases prove that the doctor previews the hook writes inside the context
build whose failure changes the verdict, without making them. The hook writer creates its temporary
file under a fresh random name with O_EXCL and O_NOFOLLOW, so a FIFO, a directory or a symbolic link
to a FIFO at the fixed temporary paths an earlier writer opened (backlog-checkpoint.json.tmp and
checkpoint-init.marker.tmp) is never opened: with an empty backlog, a live lease and no init marker,
the doctor predicts both writes to succeed, and the real hook allows the Stop and the scheduling call
without blocking and writes the marker, as the doctor reports. A state directory the hook cannot
write fails the checkpoint rewrite, which skips the marker write, and a present marker is not
rewritten, so the hook allows and so does the doctor. Once the checkpoint rewrite in the same
directory has succeeded, no arrangement of the tree makes the marker write fail, so the
DoctorMarkerWriteFault case injects that failure in one process, into the doctor prediction and into
the hook writer alike, and proves that the preview and the hook inject the same cannot-evaluate row
and reach the same DENY, and that without the fault neither injects it. The DoctorStandInRestore
cases load the doctor in one process and prove that the two hook functions the preview replaces
are the original objects again after a normal return, after the not-previewed exception and after a
KeyboardInterrupt raised inside the stand-in. The DoctorWriteSiteProbe case is
the class probe for that finding: it scans the
hook source from _orch_build_ctx through every module function it calls for every write (a write
primitive, an open for writing, an os or shutil call that changes the file system, a write method),
requires the set of sites to equal the reviewed WRITE_SITES table, each modelled by the doctor or of
no verdict effect with a reason, requires the doctor to replace exactly the primitives the table
names, and proves that it refuses one added write of each kind.
The DoctorBlockingWrites cases run the REAL hook beside the doctor on the writes the judged handler makes
with a plain blocking open: guard-events.jsonl, which every judged verdict appends to, a clean ALLOW
included, and escape-spoof.json and forced-exit.jsonl where the handler reaches them. With a FIFO at the
path the real hook blocks and the doctor reports cannot-evaluate; without it both complete and agree. The
DoctorCreatedStateDir cases run the doctor and the real hook under the same umask with the state directory
absent, in a store cleared of any default ACL: under umask 0o777 the denial counter cannot be saved and both
report the fail-open allow, under umask 0o022 both deny, and a default ACL whose owner entry lacks write
replaces the umask. The LinkedStateFiles cases pin the post-gate aliasing residual of the registry gate: a
record hard-linked at the resume barrier keeps its content, and one hard-linked at guard-events.jsonl is
appended to.
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
# that validate_enumeration accepts (aiqt_hooks.py:validate_enumeration) and exits 0.
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
    """Serialize rows as a chained register (aiqt_hooks.py:_orch_chained_rows): seq is the line number and prev is
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
        # A repo-relative file that a register pointer can resolve to (aiqt_hooks.py:_orch_pointer_resolves).
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
        """A genuine human prompt zeroes the stop and schedule denial counters (aiqt_hooks.py:orch_prompt_stamp)."""
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
        # The stage-1 posture under a live lease (aiqt_hooks.py:_orch_enumerate, aiqt_hooks.py:decide_yield; stage-1 T1:639-646).
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("NO_ENUMERATOR", r.stderr)


# =====================================================================================================
# T1. Stop with one open granted unblocked item denies, naming the id (aiqt_hooks.py:decide_yield)
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
# T2. Stop with every item closed or proposed allows (aiqt_hooks.py:classify_backlog, aiqt_hooks.py:decide_yield)
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
# T3. human-decision blockers against the declared pending-decisions record (aiqt_hooks.py:classify_backlog)
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
        # A free-text mention is not a row-id position (aiqt_hooks.py:classify_backlog).
        r = self._run("PD-7", "| PD-8 | Another decision |\nWe discussed PD-7 in passing.\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ref PD-7 is not at a pending-decision row-id position", r.stderr)

    def test_lowercase_ref_is_not_a_decision_id(self):
        r = self._run("pd-7", "| pd-7 | lowercase row |\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("is not a decision id", r.stderr)

    def test_unreadable_pending_surface_holds(self):
        # An unreadable declared surface is cannot-evaluate, which denies the Stop
        # (aiqt_hooks.py:classify_backlog, aiqt_hooks.py:decide_yield).
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
# T4. not-before blockers (aiqt_hooks.py:classify_backlog)
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
# T5. Anti-shrinkage checkpoint (aiqt_hooks.py:_orch_checkpoint_union)
# =====================================================================================================
class T05Checkpoint(Stage2Harness):
    def test_vanished_id_is_held_until_closed(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        # Window 1: item 9 open and actionable; the checkpoint and its init marker are written
        # (aiqt_hooks.py:_orch_checkpoint_union).
        self.set_items([item("9")])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.state_json("backlog-checkpoint.json")["ids"], {"9": "eligible"})
        self.assertIsNotNone(self.read_json("checkpoint-init.marker"))
        # Window 2: item 9 deleted with no closed receipt is held as vanished (aiqt_hooks.py:_orch_checkpoint_union).
        self.human_prompt()
        self.set_items([])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("cannot-evaluate", r.stderr)
        self.assertEqual(self.state_json("backlog-checkpoint.json")["ids"], {"9": "eligible"},
                         "the union keeps a vanished id (aiqt_hooks.py:_orch_checkpoint_union)")
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
        self.assertEqual(r.returncode, 2, r.stderr)  # aiqt_hooks.py:_orch_checkpoint_union
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
# T6. attestations (OPTIONAL KEY, open point P5; aiqt_hooks.py:_orch_attestation_refs, aiqt_hooks.py:classify_backlog, aiqt_hooks.py:_orch_validate_attestations)
# =====================================================================================================
class T06Attestations(Stage2Harness):
    def _register(self, rows, anchor=True):
        # The register lives in the store, outside the repository, so the authority is its anchor
        # (aiqt_hooks.py:_orch_register_authority `anchor = path +`). A well-formed anchor names a row: seq is
        # its line number, at least 1, and digest the sha256 of that line (aiqt_hooks.py:_orch_register_authority
        # `if _orch_sha256_hex(lines[n - 1]) != digest:`), so the anchor written here names the last row. An
        # empty register has no row to name and gets the zero anchor {seq 0, 64 zeros}, which the hook
        # rejects as malformed (aiqt_hooks.py:_orch_register_authority `n < 1`).
        path = Path(self._p("attestations.jsonl"))
        lines = chain_lines(rows)
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        if anchor:
            tip = {"seq": len(lines), "digest": _sha256_hex(lines[-1])} if lines else \
                {"seq": 0, "digest": ZERO64}
            Path(str(path) + ".anchor").write_text(json.dumps(tip), encoding="utf-8")
        return path

    def _row(self, ref="vendor-x"):
        return {"id": "AT-1", "status": "accepted", "ref": ref,
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

    def test_empty_register_zero_anchor_holds(self):
        # A zero anchor names no row, so the authority holds (aiqt_hooks.py:_orch_register_authority `n < 1`) and
        # the audit writes the hold snapshot (aiqt_hooks.py:_orch_validate_attestations `snap = hold_snap`).
        self._arm([])
        snap = self.state_json("attestations-validated.json")
        self.assertEqual((snap["status"], snap["seq"], snap["digest"], snap["refs"]),
                         ("unreadable", None, None, []))

    def test_anchored_register_audits_ok(self):
        rows = [self._row()]
        self._arm(rows)
        snap = self.state_json("attestations-validated.json")
        self.assertEqual((snap["status"], snap["seq"], snap["digest"]),
                         ("ok", 1, _sha256_hex(chain_lines(rows)[-1])))

    def test_approved_row_blocks(self):
        self._arm([self._row()])
        self.assertEqual(self.state_json("attestations-validated.json")["refs"], ["vendor-x"])
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_without_row_is_actionable(self):
        # A valid register whose only row attests another ref covers nothing for vendor-x.
        self._arm([self._row(ref="vendor-other")])
        self.assertEqual(self.state_json("attestations-validated.json")["status"], "ok")
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("is covered by no fresh validated attestation", r.stderr)

    def test_without_anchor_holds(self):
        self._arm([self._row()])
        os.remove(self._p("attestations.jsonl.anchor"))
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)  # aiqt_hooks.py:_orch_register_authority -> aiqt_hooks.py:classify_backlog `if attestations ==`
        self.assertIn("cannot-evaluate", r.stderr)

    def test_undeclared_contrast_free_text_evidence_blocks(self):
        # Without the key, fresh free-text evidence blocks (aiqt_hooks.py:classify_backlog) and no snapshot is
        # written, so test_without_row_is_actionable is red without the key.
        self._arm([], declare=False)
        self.assertIsNone(self.read_json("attestations-validated.json"))
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)


# =====================================================================================================
# T7. staleness horizons (aiqt_hooks.py:_orch_live_ledger_ids, aiqt_hooks.py:classify_backlog, aiqt_hooks.py:_schema_staleness)
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
        # Without the key both horizons are 24 h (aiqt_hooks.py:_schema_staleness), so the two allows above flip.
        self.assertEqual(self._tracked(None, drop=("staleness",)).returncode, 2)
        self.assertEqual(self._external(None, drop=("staleness",)).returncode, 2)

    def test_stage1_contrast(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        self.set_items([item("8", blocker={"kind": "tracked-task", "ref": "task-1"})])
        self.assert_no_enumerator_deny(self.stop())


# =====================================================================================================
# T8. orch_yield_tool over the scheduling tools (aiqt_hooks.py:orch_yield_tool)
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
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")  # aiqt_hooks.py:orch_yield_tool
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
        # tool_input stop true is judged as kind "stop" (aiqt_hooks.py:orch_yield_tool): with the stop counter at the
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
        # aiqt_hooks.py:decide_yield (the cap) and aiqt_hooks.py:orch_yield_tool `forced = ((kind ==` (the forced-exit record).
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
# T9. orch_ask_guard against the declared mode record (aiqt_hooks.py:orch_ask_guard)
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
# T10. Scope by mode record when the lease is stale (aiqt_hooks.py:_orch_scope_live)
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
# T11. escape declaration (aiqt_hooks.py:_orch_escape_active, aiqt_hooks.py:_orch_record_escape_spoof)
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
                self.assertFalse(spoof.exists(), "no release and no spoof record (aiqt_hooks.py:_orch_escape_active)")

    def test_undeclared_contrast_consults_the_default_name(self):
        self._arm(self.stage2(drop=("escape",)))
        self.self_owned_sentinel("ESCAPE-ALLOW-YIELD")
        self.assertEqual(self.stop().returncode, 2)
        self.assertIsNotNone(self.read_json("escape-spoof.json"))

    def test_absolute_path_outside_the_anchor_is_rejected(self):
        self._arm(self.stage2(escape={"path": self._p("elsewhere", "SENTINEL")}))
        self.assertEqual(self.stop().returncode, 2)
        spoof = self.state_json("escape-spoof.json")
        self.assertIn("outside the operator-trusted anchor", spoof["detail"])  # aiqt_hooks.py:_orch_escape_active


# =====================================================================================================
# T12. mistakes_register (OPTIONAL KEY, open point P6; aiqt_hooks.py:_orch_validate_attestations)
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
# T13. TeammateIdle mirrors the Stop decision (aiqt_hooks.py:orch_teammate_idle)
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
        self.assertEqual(r.returncode, 2, r.stderr)  # aiqt_hooks.py:_orch_enumerate
        self.assertIn("ENUMERATOR_ERROR", r.stderr)
        self.assertIn("not a list of non-empty strings", r.stderr)

    def test_enumerator_timeout_malformed_still_runs(self):
        # A malformed timeout silently becomes 60 (aiqt_hooks.py:_orch_enumerate); the enumerator still runs.
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
        self.assertEqual(r.stdout.strip(), "", "a non-list roster is out of scope (aiqt_hooks.py:orch_yield_tool)")

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
# T15. Enumerator timeout yields ENUMERATOR_ERROR, never a hang (aiqt_hooks.py:_orch_enumerate)
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
        cache the doctor import writes beside the hook is observable. Returns (fresh root,
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

    # --- a declared read path that is not a regular file is cannot-evaluate, before any hook reader
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

    def _assert_special_mode_read_as_armed(self, kind, *doctor_args):
        # No lease, so scope falls through to the mode read. _orch_mode_read opens the record non-blocking and
        # reads a file that is not a regular file as bad (aiqt_hooks.py:_orch_mode_read
        # `result = ("bad", "the mode file is not a regular file")`), which fails closed to the guards-armed
        # posture (aiqt_hooks.py:_orch_mode_detail `return (_ORCH_MODE_ARMED, text)`), so scope is live. The
        # doctor must not refuse the path; it previews the judged verdict, and the special file is untouched.
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(reg)
        self.set_items([item("42")])
        path = Path(self._p("operating-mode.md"))
        self._make_special(path, kind)
        r = self._doctor_bounded(*doctor_args)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("cannot evaluate", r.stdout)
        self.assertIn("scope: live", r.stdout)
        self.assertIn("judged verdict: DENY", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(marker.exists(), "the enumerator ran, as the hook runs it in scope")
        self.assertTrue(path.is_symlink() or path.is_fifo() or path.is_dir(), "the special file was replaced")

    def test_preflight_special_mode_path_reads_as_armed(self):
        for kind in ("fifo", "directory", "symlink-to-fifo"):
            with self.subTest(kind=kind):
                self.tearDown()
                self.setUp()
                self._assert_special_mode_read_as_armed(kind, "preflight", "stop")

    def test_preflight_special_lease_path_is_cannot_evaluate(self):
        # The hook opens the lease only for holder scoping, on a lease that os.stat reaches, that is
        # non-empty and fresh, and with a session id given (aiqt_hooks.py:_orch_scope_live). A FIFO has size 0
        # and so is never opened (see DoctorPrecheckSites); the special file the hook does
        # open here is a non-empty directory.
        reg, marker = self._arm_writing_enumerator()
        reg["lease"]["holder_is_session_id"] = True
        self.write_registry(reg)
        self.set_items([item("42")])
        lease = Path(self._p("session-state.md"))
        lease.mkdir()
        (lease / "entry").write_text("held\n", encoding="utf-8")
        self.assertGreater(os.stat(lease).st_size, 0, "precondition: a non-empty directory")
        before = tree_state(self._tmp)
        r = self._doctor_bounded("preflight", "stop", "--session-id", "sess-1")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("cannot evaluate: the declared lease.path {} is not a regular file (it is a "
                      "directory)".format(lease), r.stdout)
        self.assertFalse(marker.exists(), "the enumerator ran")
        self.assertEqual(tree_state(self._tmp), before, "the doctor changed a file or directory")

    def test_preflight_idle_special_mode_path_reads_as_armed(self):
        self._assert_special_mode_read_as_armed("fifo", "preflight", "idle")

    def test_preflight_special_backlog_operand_is_cannot_evaluate(self):
        self._assert_special_refused("enumerator.argv[3]", str(self.backlog), "fifo",
                                     "preflight", "stop")

    def test_resume_audit_special_handoff_is_cannot_evaluate(self):
        # The resume probes open the declared handoff with a plain blocking open
        # (aiqt_hooks.py:_orch_resume_probes), so a FIFO there would hang the audit.
        self._assert_special_refused("record.handoff", self._p("session-handoff.md"), "fifo",
                                     "--resume-audit")

    # --- the fixed hook state files are checked too, per command -----------------------
    # The state files _orch_build_ctx opens with a plain blocking open (turn-state.json at
    # aiqt_hooks.py:_orch_turn_state, dispatch-ledger.jsonl at aiqt_hooks.py:_orch_live_ledger_ids `rows, bad = _orch_read_jsonl(os.path.join(` and aiqt_hooks.py:_orch_read_jsonl `with open(path,`, backlog-checkpoint.json at aiqt_hooks.py:_orch_checkpoint_union `with open(path,`, and
    # with attestations declared attestations-validated.json at aiqt_hooks.py:_orch_attestation_refs `with open(path,` and guard-events.jsonl at aiqt_hooks.py:_orch_pointer_resolves `rows, _bad = _orch_read_jsonl(os.path.join(sd,`).
    PREFLIGHT_STATE_FILES = ("turn-state.json", "dispatch-ledger.jsonl", "backlog-checkpoint.json",
                             "attestations-validated.json", "guard-events.jsonl")
    # The state files orch_resume_audit opens with a plain blocking open (guard-events.jsonl at aiqt_hooks.py:_orch_pointer_resolves `rows, _bad = _orch_read_jsonl(os.path.join(sd,` and
    # aiqt_hooks.py:_orch_append_jsonl `with open(path,`, escape-spoof.json at aiqt_hooks.py:_orch_pending_artefact_findings `with open(path,`, forced-exit.jsonl at aiqt_hooks.py:_orch_forced_exit_findings `rows, bad = _orch_read_jsonl(log)` and aiqt_hooks.py:_orch_read_jsonl `with open(path,`, and forced-exit-surfaced.json at
    # aiqt_hooks.py:_orch_forced_exit_findings `with open(surfaced_path,`). The saves of the surfaced set and the attestation snapshot write
    # a temporary file under a random name created with O_EXCL and O_NOFOLLOW (aiqt_hooks.py:_orch_write_json_at
    # `tmp = "{}.{}.tmp".format(name, os.urandom(8).hex())`), so the fixed names in AUDIT_TEMP_NAMES are never opened.
    AUDIT_STATE_FILES = ("guard-events.jsonl", "escape-spoof.json", "forced-exit.jsonl",
                         "forced-exit-surfaced.json")
    AUDIT_TEMP_NAMES = ("forced-exit-surfaced.json.tmp", "attestations-validated.json.tmp")

    def _with_attestations(self, reg):
        # A declared attestations register, absent on disk (an open the hook raises on, never blocks
        # on): the condition the hook tests before it opens the attestation state files
        # (aiqt_hooks.py:_orch_attestation_refs for the preview, aiqt_hooks.py:_orch_validate_attestations `at_path = _orch_path(root, reg.get(` for the audit).
        reg["attestations"] = self._p("attestations.jsonl")
        return reg

    def _make_state_fifo(self, name):
        self.state_dir().mkdir(parents=True, exist_ok=True)
        path = self.state_dir() / name
        os.mkfifo(path)
        return path

    def _seed_reach(self, name, command):
        # Seed the state the hook needs to reach the open of name. The preview reads
        # guard-events.jsonl only past a snapshot open (aiqt_hooks.py:_orch_attestation_refs) and a register open
        # (aiqt_hooks.py:_orch_register_authority `with open(path,`); the audit opens the surfaced set and its temporary file only for a forced-exit
        # log that holds rows (aiqt_hooks.py:_orch_forced_exit_findings `rows, bad = _orch_read_jsonl(log)`).
        if command == "preflight" and name == "guard-events.jsonl":
            self.seed_state("attestations-validated.json", {})
            Path(self._p("attestations.jsonl")).write_text("", encoding="utf-8")
        if command == "--resume-audit" and name.startswith("forced-exit-surfaced.json"):
            self.seed_ledger_like("forced-exit.jsonl", [{"key": "k1", "ts": _iso(), "open_ids": ["42"]}])

    def seed_ledger_like(self, name, rows):
        sd = self.state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        (sd / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def _assert_state_special_refused(self, name, *doctor_args):
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(self._with_attestations(reg))
        self.set_items([item("42")])
        self._seed_reach(name, doctor_args[0])
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
        # would block on each of these (a FIFO turn-state.json made the preview hang before this check).
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

    def test_resume_audit_runs_past_a_fifo_at_a_fixed_temp_name(self):
        # The hook never opens these names (AUDIT_TEMP_NAMES above), so the doctor must not refuse the audit
        # over a FIFO there, and the audit must leave it in place.
        for name in self.AUDIT_TEMP_NAMES:
            with self.subTest(name=name):
                self.tearDown()
                self.setUp()
                reg, marker = self._arm_writing_enumerator()
                self.write_registry(self._with_attestations(reg))
                self.set_items([item("42")])
                self._seed_reach("forced-exit-surfaced.json", "--resume-audit")
                path = self._make_state_fifo(name)
                r = self._doctor_bounded("--resume-audit")
                self.assertNotIn("Traceback", r.stderr)
                self.assertNotIn("cannot evaluate", r.stdout)
                self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)
                self.assertTrue(path.is_fifo(), "the audit replaced the FIFO")
                self.assertFalse(marker.exists(), "the audit ran the enumerator")

    def test_resume_audit_on_an_unreadable_registry_checks_its_state_files(self):
        # On an unreadable registry the hook appends to resume-barrier.json.unused beside the barrier
        # (aiqt_hooks.py:orch_resume_audit, opened at aiqt_hooks.py:_orch_append_jsonl `with open(path,`) under the default state directory (aiqt_hooks.py:orch_resume_audit `barrier_path = os.path.join(_orch_state_dir_for_root(`).
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

    # --- each command checks only what its own hook call path opens --------------------
    def test_fifo_backlog_operand_refuses_preflight_but_not_the_resume_audit(self):
        # The resume probes run no enumerator (aiqt_hooks.py:_orch_resume_probes), so the hook audits with a
        # FIFO backlog operand, and so must the doctor; the preview runs the enumerator (aiqt_hooks.py:_orch_enumerate `result = subprocess.run(argv, capture_output=True,`), so it
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
        # The audit stats the lease only (aiqt_hooks.py:_orch_resume_probes) and never opens the mode record or the
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
        # Out of scope the hook returns before _orch_build_ctx (aiqt_hooks.py:_orch_stop_family and
        # aiqt_hooks.py:orch_yield_tool `scope = _orch_scope_live(reg, root, data.get(`), so it never opens turn-state.json, and the preview reports the same ALLOW.
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

    def test_special_registry_file_reads_as_unreadable(self):
        # The hook opens each registry file non-blocking and checks its type on the open descriptor
        # (aiqt_hooks.py:_orch_registry `return ("bad", "{}: not a regular file".format(rel))`), the machine-local file
        # first (aiqt_hooks.py:_ORCH_REGISTRY_FILES), so a FIFO there is an unreadable registry at once. The doctor
        # reports it from the hook reader: the preview refuses with the unreadable posture, and the resume
        # audit runs as the hook runs it, arming the barrier on the unreadable registry.
        self.write_registry(self.stage2())
        local = self.repo / ".aiqt" / "orchestration.local.json"
        os.mkfifo(local)
        r = self._doctor_bounded("preflight", "stop")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("cannot evaluate", r.stdout)
        self.assertIn("registry: unreadable (.aiqt/orchestration.local.json: not a regular file)", r.stdout)
        r = self._doctor_bounded("--resume-audit")
        self.assertNotIn("cannot evaluate", r.stdout)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("finding: the orchestration registry could not be read (.aiqt/orchestration.local.json: "
                      "not a regular file)", r.stdout)
        self.assertTrue(local.is_fifo(), "the FIFO was replaced")

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

    # --- the doctor decides scope first and, out of scope, runs no enumerator ----------------
    def _arm_writing_enumerator(self, **overrides):
        script = self._tmp / "enum_writing.py"
        script.write_text(WRITING_ENUM_FIXTURE, encoding="utf-8")
        marker = self._tmp / "enumerator-ran.txt"
        reg = self.stage2(enumerator={
            "argv": [sys.executable, "-I", str(script), str(self.backlog), str(marker)],
            "timeout": 5}, **overrides)
        return reg, marker

    def test_preflight_out_of_scope_runs_no_enumerator(self):
        # The Stop hook returns before it enumerates when scope is not live (aiqt_hooks.py:_orch_stop_family),
        # and so does the scheduling hook (aiqt_hooks.py:orch_yield_tool); a preview that ran the
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
        # (aiqt_hooks.py:orch_yield_tool).
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

    # --- the doctor re-executes itself isolated, and a failed re-execution exits 2 ------------
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

    # --- the doctor writes nothing itself; the declared enumerator runs as the hook runs it ---
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

    # --- roster membership exactly as the hook tests it; the quiet claim is not previewed -----
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

    # --- a Stop DENY whose denial counter cannot be saved fails open in the hook ------------
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
        # (aiqt_hooks.py:_orch_stop_family).
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

    def test_preflight_stop_with_a_read_only_turn_state_reports_the_deny(self):
        # The hook saves the counter through a temporary file in the state directory that it then
        # replaces onto turn-state.json (aiqt_hooks.py:_orch_save_turn_state, aiqt_hooks.py:_orch_write_json_at
        # `os.replace(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)`), so a read-only turn-state.json in a writable
        # state directory is replaced and the DENY holds; the doctor must report that DENY.
        self._arm_actionable_stop()
        self.seed_state("turn-state.json", {})
        path = self.state_dir() / "turn-state.json"
        os.chmod(path, 0o444)
        before = tree_state(self._tmp)
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(tree_state(self._tmp), before, "preflight changed a file or directory")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("denial counter: could be saved", r.stdout)
        self.assertIn("effective verdict: DENY", r.stdout)
        h = self.stop()
        self.assertEqual(h.returncode, 2, h.stderr)
        self.assertEqual(self.state_json("turn-state.json").get("stop_denials"), 1,
                         "the hook replaced the read-only file with the counted state")

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

    def test_preflight_stop_with_an_unusable_lease_horizon_reports_the_cannot_evaluate_deny(self):
        # A declared max_age_hours of 0 is not a usable horizon, so scope answers cannot-evaluate
        # (aiqt_hooks.py:_orch_scope_live `return "cannot" if cannot else False`) and the Stop guard adds a
        # cannot-evaluate row before it decides (aiqt_hooks.py:_orch_stop_family `if scope == "cannot":`), so a
        # backlog with nothing actionable is still denied. The doctor must add the same row.
        reg = self.stage2()
        reg.pop("mode")
        reg["lease"]["max_age_hours"] = 0
        self.write_registry(reg)
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("scope: cannot be evaluated", r.stdout)
        self.assertIn("judged verdict: DENY", r.stdout)
        self.assertIn("lease:max_age_hours", r.stdout)
        self.assertEqual(self.stop().returncode, 2)

    # --- the help text says what preflight writes, and what it runs -------------------------
    def test_help_text_says_the_doctor_writes_nothing_and_the_enumerator_runs(self):
        r = subprocess.run([sys.executable, "-I", str(DOCTOR), "--help"], capture_output=True,
                           text=True, env=self._env(), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = " ".join(r.stdout.split())
        self.assertIn("the doctor itself writes nothing", text)
        self.assertIn("the declared enumerator runs as the hook runs it", text)
        self.assertNotIn("without writing anything", text)

    # --- the resume audit requires that the hook rewrote the barrier during this run ---------
    def _seed_stale_barrier(self, active):
        self.seed_state("resume-barrier.json", {"active": active,
                                                "findings": ["seeded"] if active else [],
                                                "ts": _iso(-48), "warned": False})
        return self.state_dir() / "resume-barrier.json"

    def _unwritable_stale_barrier(self, active):
        # The hook replaces the barrier through a temporary file beside it (aiqt_hooks.py:_orch_barrier_write
        # `with open(tmp, "x", encoding="utf-8") as fh:`), so only a state directory it cannot write keeps the
        # stale barrier in place.
        path = self._seed_stale_barrier(active)
        os.chmod(self.state_dir(), 0o555)
        return path, path.read_bytes()

    def test_resume_audit_read_only_barrier_is_replaced(self):
        # Contrast: a read-only barrier file in a writable state directory is replaced whole
        # (aiqt_hooks.py:_orch_barrier_write `os.replace(tmp, path)`), so the doctor reports the state this audit wrote.
        self.write_registry(self.stage2())
        self.arm_lease()
        self.write_record_files(handoff="Branch: some-other-branch\n")
        path = self._seed_stale_barrier(False)
        os.chmod(path, 0o444)
        before = path.read_bytes()
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("barrier: active", r.stdout)
        self.assertNotIn("NOT rewritten by this audit", r.stdout)
        self.assertNotEqual(path.read_bytes(), before)

    def test_resume_audit_read_only_stale_clear_barrier_is_unverified(self):
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0555 directory, so the barrier cannot stay stale")
        self.write_registry(self.stage2())
        self.arm_lease()
        self.write_record_files(handoff="Branch: some-other-branch\n")  # a real audit would arm
        path, before = self._unwritable_stale_barrier(False)
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("NOT rewritten by this audit", r.stdout)
        self.assertNotIn("barrier: clear", r.stdout)
        self.assertEqual(path.read_bytes(), before, "precondition: the hook could not rewrite it")

    def test_resume_audit_read_only_stale_active_barrier_is_unverified(self):
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0555 directory, so the barrier cannot stay stale")
        self.write_registry(self.stage2())
        self.arm_lease()
        path, before = self._unwritable_stale_barrier(True)
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

    # --- the barrier is read only as a regular file, without blocking -------------------------
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


# Class probe: every pre-check site in tools/orch_doctor.py (each _site call), the condition
# under which the hook call path reaches the open of that path, and the hook lines that decide it. A
# site with an early exit (True in the second column) has a contrast case below in which the hook
# takes the earlier exit, so the doctor must NOT refuse a FIFO there, beside the case in which the
# open is reached and the doctor must refuse. Citations name symbols of
# plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py.
PRECHECK_SITES = {
    "scope.lease": (
        "preflight", True,
        "os.stat succeeds, the lease is non-empty and fresh, holder_is_session_id is set and a "
        "session id is given",
        "aiqt_hooks.py:_orch_scope_live `lease = reg.get(`: stat aiqt_hooks.py:_orch_scope_live `st = os.stat(path)`, size and freshness aiqt_hooks.py:_orch_scope_live `fresh = True`, holder aiqt_hooks.py:_orch_scope_live `if lease.get(`, "
        "session id aiqt_hooks.py:_orch_scope_live `if not (isinstance(session_id, str) and session_id):`, open aiqt_hooks.py:_orch_scope_live `with open(path,`"),
    "ctx.turn_state": (
        "preflight", True,
        "scope live (and for idle the tool in the roster); then always",
        "orch_stop_guard aiqt_hooks.py:_orch_stop_family `scope = _orch_scope_live(reg, root, data.get(`, aiqt_hooks.py:orch_yield_tool `scope = _orch_scope_live(reg, root, data.get(`; aiqt_hooks.py:_orch_turn_state `if not os.path.lexists(path):` via aiqt_hooks.py:_orch_build_ctx `ts = _orch_turn_state(root)`"),
    "ctx.enumerator_operand": (
        "preflight", True,
        "the enumerator runs: an object with a non-empty argv of non-empty strings",
        "aiqt_hooks.py:_orch_enumerate `if not isinstance(spec, dict):`, subprocess aiqt_hooks.py:_orch_enumerate `result = subprocess.run(argv, capture_output=True,` via aiqt_hooks.py:_orch_build_ctx `status, payload = _orch_enumerate(reg, root)`"),
    "ctx.ledger": (
        "preflight", True,
        "the enumerator runs (its success is not modelled)",
        "aiqt_hooks.py:_orch_build_ctx `if status ==`, aiqt_hooks.py:_orch_live_ledger_ids `rows, bad = _orch_read_jsonl(os.path.join(`, open aiqt_hooks.py:_orch_read_jsonl `with open(path,`"),
    "ctx.pending_decisions": (
        "preflight", True,
        "the enumerator runs and record.pending_decisions is declared",
        "aiqt_hooks.py:_orch_build_ctx `if status ==`, aiqt_hooks.py:_orch_pending_haystack `declared = _orch_path(root, rec.get(`"),
    "ctx.attestation_snapshot": (
        "preflight", True,
        "the enumerator runs and attestations is declared",
        "aiqt_hooks.py:_orch_attestation_refs `at_path = _orch_path(root, reg.get(` via aiqt_hooks.py:_orch_build_ctx `attestations=_orch_attestation_refs(reg, root,`"),
    "ctx.attestations": (
        "preflight", True,
        "as the snapshot, and os.stat succeeds on the snapshot (its content is not modelled)",
        "aiqt_hooks.py:_orch_attestation_refs `with open(path,` return on a failed snapshot open; aiqt_hooks.py:_orch_register_authority `with open(path,` via aiqt_hooks.py:_orch_attestation_refs `astatus, aseq, adigest = _orch_register_authority(root,`, "
        "aiqt_hooks.py:_orch_chained_rows `with open(path,` via aiqt_hooks.py:_orch_attestation_refs `rows, _detail = _orch_chained_rows(at_path,`"),
    "ctx.guard_events": (
        "preflight", True,
        "scope live (and for idle the tool in the roster); then always: every judged verdict appends a "
        "guard-events row (the read inside the build, past the snapshot and the register, is covered too)",
        "aiqt_hooks.py:_orch_stop_family `_orch_guard_event(root, event_name, verdict.lower(), reason)`, aiqt_hooks.py:orch_yield_tool `_orch_guard_event(root,`, "
        "append aiqt_hooks.py:_orch_append_jsonl `with open(path,`; read aiqt_hooks.py:_orch_pointer_resolves `rows, _bad = _orch_read_jsonl(os.path.join(sd,`"),
    "verdict.escape_spoof": (
        "preflight", True,
        "the context records an ignored escape sentinel",
        "aiqt_hooks.py:_orch_stop_family `spoof_warn = (_orch_record_escape_spoof(root, ctx[`, aiqt_hooks.py:_orch_record_escape_spoof `ok_file = _orch_write_json(`, "
        "open aiqt_hooks.py:_orch_write_json `with open(path,`"),
    "verdict.forced_exit": (
        "preflight", True,
        "an ALLOW_WITH_FINDINGS released by the loop bound, the loop signal or the schedule cap past "
        "open work",
        "aiqt_hooks.py:_orch_stop_family `extra = _orch_record_forced_exit(root, event_name, ctx, reason)`, aiqt_hooks.py:_orch_record_forced_exit `ok_file = _orch_append_jsonl(`, "
        "append aiqt_hooks.py:_orch_append_jsonl `with open(path,`"),
    "ctx.checkpoint": (
        "preflight", True,
        "the enumerator runs",
        "aiqt_hooks.py:_orch_build_ctx `if status ==` and aiqt_hooks.py:_orch_build_ctx `_orch_checkpoint_union(root, payload,`, aiqt_hooks.py:_orch_checkpoint_union `present = os.path.lexists(path)`"),
    "audit.handoff": (
        "--resume-audit", False, "record.handoff is declared", "aiqt_hooks.py:_orch_resume_probes `handoff_path = _orch_path(root, rec.get(`"),
    "audit.findings": (
        "--resume-audit", False, "record.findings is declared", "aiqt_hooks.py:_orch_resume_probes `path = _orch_path(root, rec.get(key))`, and aiqt_hooks.py:_orch_merge_pending_findings `rec = reg.get(` via aiqt_hooks.py:_orch_resume_probes `findings.extend(_orch_merge_pending_findings(reg, root))`"),
    "audit.pending_decisions": (
        "--resume-audit", False, "record.pending_decisions is declared", "aiqt_hooks.py:_orch_resume_probes `path = _orch_path(root, rec.get(key))`"),
    "audit.attestations": (
        "--resume-audit", False, "attestations is declared",
        "aiqt_hooks.py:_orch_validate_attestations `if at_path:`, aiqt_hooks.py:_orch_chained_rows `with open(path,` via aiqt_hooks.py:_orch_validate_attestations `rows, detail = _orch_chained_rows(at_path,`, "
        "aiqt_hooks.py:_orch_register_authority `with open(path,` via aiqt_hooks.py:_orch_validate_attestations `astatus, aseq, adigest = _orch_register_authority(root,`"),
    "audit.mistakes_register": (
        "--resume-audit", False, "mistakes_register is declared", "aiqt_hooks.py:_orch_validate_attestations `mr_path = _orch_path(root, reg.get(`, open aiqt_hooks.py:_orch_chained_rows `with open(path,`"),
    "audit.guard_events": (
        "--resume-audit", False,
        "always checked: both opens depend on file content (a guard-events pointer, findings to "
        "record)",
        "aiqt_hooks.py:_orch_pointer_resolves `rows, _bad = _orch_read_jsonl(os.path.join(sd,` via aiqt_hooks.py:_orch_validate_attestations `refs, unsub, dfindings = _orch_attestation_derive(reg,` and aiqt_hooks.py:_orch_validate_attestations `if not _orch_pointer_resolves(root, sd, pointer):`; _orch_guard_event aiqt_hooks.py:_orch_append_jsonl `with open(path,` via aiqt_hooks.py:orch_resume_audit `if findings:`"),
    "audit.escape_spoof": (
        "--resume-audit", False, "always (lexists, then open)",
        "aiqt_hooks.py:_orch_pending_artefact_findings `if os.path.lexists(path):`"),
    "audit.forced_exit": (
        "--resume-audit", False, "always", "aiqt_hooks.py:_orch_forced_exit_findings `log = os.path.join(sd,`, open aiqt_hooks.py:_orch_read_jsonl `with open(path,`"),
    "audit.forced_exit_surfaced": (
        "--resume-audit", True,
        "os.stat succeeds on forced-exit.jsonl and it is not empty (its rows are not modelled)",
        "aiqt_hooks.py:_orch_read_jsonl `with open(path,`, no rows return aiqt_hooks.py:_orch_forced_exit_findings `if not rows:`, open aiqt_hooks.py:_orch_forced_exit_findings `with open(surfaced_path,`"),
    "audit_bad.unused": (
        "--resume-audit", False, "an unreadable registry; then always",
        "aiqt_hooks.py:orch_resume_audit `_orch_append_jsonl(barrier_path +`, open aiqt_hooks.py:_orch_append_jsonl `with open(path,`"),
}

# (site, expectation, case method of DoctorPrecheckSites). "reach": the hook opens the path, so the
# doctor must refuse a special file there; "skip": the hook takes an earlier exit, so the doctor must
# run, and the real hook, run after it, must complete within the timeout with the FIFO in place.
PRECHECK_CASES = [
    ("scope.lease", "reach", "case_lease_holder_directory"),
    ("scope.lease", "skip", "case_lease_holder_fifo_is_empty"),
    ("scope.lease", "skip", "case_lease_holder_without_session_id"),
    ("ctx.turn_state", "reach", "case_turn_state"),
    ("ctx.turn_state", "skip", "case_turn_state_out_of_scope"),
    ("ctx.enumerator_operand", "reach", "case_operand"),
    ("ctx.enumerator_operand", "skip", "case_operand_argv_cannot_run"),
    ("ctx.ledger", "reach", "case_ledger"),
    ("ctx.ledger", "skip", "case_ledger_argv_cannot_run"),
    ("ctx.pending_decisions", "reach", "case_ctx_pending"),
    ("ctx.pending_decisions", "skip", "case_ctx_pending_argv_cannot_run"),
    ("ctx.attestation_snapshot", "reach", "case_snapshot"),
    ("ctx.attestation_snapshot", "skip", "case_snapshot_argv_cannot_run"),
    ("ctx.attestation_snapshot", "skip", "case_snapshot_undeclared"),
    ("ctx.attestations", "reach", "case_ctx_register"),
    ("ctx.attestations", "skip", "case_ctx_register_without_snapshot"),
    ("ctx.guard_events", "reach", "case_ctx_guard_events"),
    ("ctx.guard_events", "reach", "case_ctx_guard_events_without_register"),
    ("ctx.guard_events", "reach", "case_ctx_guard_events_undeclared"),
    ("ctx.guard_events", "skip", "case_ctx_guard_events_out_of_scope"),
    ("verdict.escape_spoof", "reach", "case_verdict_escape_spoof"),
    ("verdict.escape_spoof", "skip", "case_verdict_escape_spoof_without_sentinel"),
    ("verdict.forced_exit", "reach", "case_verdict_forced_exit"),
    ("verdict.forced_exit", "skip", "case_verdict_forced_exit_without_loop_signal"),
    ("ctx.checkpoint", "reach", "case_checkpoint"),
    ("ctx.checkpoint", "skip", "case_checkpoint_argv_cannot_run"),
    ("audit.handoff", "reach", "case_audit_handoff"),
    ("audit.findings", "reach", "case_audit_findings"),
    ("audit.pending_decisions", "reach", "case_audit_pending"),
    ("audit.attestations", "reach", "case_audit_register"),
    ("audit.mistakes_register", "reach", "case_audit_mistakes"),
    ("audit.guard_events", "reach", "case_audit_guard_events"),
    ("audit.escape_spoof", "reach", "case_audit_escape_spoof"),
    ("audit.forced_exit", "reach", "case_audit_forced_exit"),
    ("audit.forced_exit_surfaced", "reach", "case_audit_surfaced"),
    ("audit.forced_exit_surfaced", "skip", "case_audit_surfaced_without_log"),
    ("audit.forced_exit_surfaced", "skip", "case_audit_surfaced_with_empty_log"),
    ("audit_bad.unused", "reach", "case_bad_registry_unused"),
    ("audit.guard_events", "reach", "case_bad_registry_guard_events"),
    ("audit.escape_spoof", "reach", "case_bad_registry_escape_spoof"),
    ("audit.forced_exit", "reach", "case_bad_registry_forced_exit"),
]

# Paths the old pre-check refused that the hook no longer opens with a blocking open, each with the
# case that puts a FIFO there: the registry files and the mode record (opened non-blocking, a special
# file reads as bad), the register anchor (opened non-blocking without following a final symlink, a
# special anchor is a hold), and the fixed .tmp names (the saves create a random temporary name with
# O_EXCL). For each, the doctor must not refuse, and the hook call path must complete within the
# timeout with the FIFO in place (expectation "nonblock" in _run_case).
NONBLOCKING_CASES = [
    ("registry file, machine-local", "case_registry_local"),
    ("registry file, committed", "case_registry_committed_without_local"),
    ("mode record", "case_mode_without_lease"),
    ("register anchor, preview", "case_ctx_anchor"),
    ("register anchor, audit", "case_audit_anchor"),
    ("snapshot temporary name", "case_audit_snapshot_tmp"),
    ("surfaced-set temporary name", "case_audit_surfaced_tmp"),
]


# Runs in a separate python3 -I process: the hook call path the preflight runs, and nothing else (the
# registry, the scope test, then _orch_build_ctx in the preview posture, aiqt_hooks.py:_orch_build_ctx and
# aiqt_hooks.py:_orch_checkpoint_union `record=False is the PREVIEW posture (`), so a skip case can show that path completes with the FIFO in place. The Stop hook itself
# also writes a guard event, the denial counter and the checkpoint, which the preview never does.
PREVIEW_PATH_PROG = """
import importlib.util, sys
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("aiqt_hooks_preview_path", sys.argv[1])
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
root = hook._recovery_toplevel(sys.argv[2])
sid = sys.argv[3] or None
status, reg = hook._orch_registry(root)
if status == "ok" and hook._orch_scope_live(reg, root, sid):
    hook._orch_build_ctx(reg, root, "stop", {"session_id": sid} if sid else {},
                         record_checkpoint=False)
print("completed")
"""


class DoctorPrecheckSites(Stage2Harness):
    """The doctor checks a path only when the hook call path reaches its open.
    Each case method arranges the fixture and returns (path, made, doctor args, hook payload): path
    is where the special file goes; made is None for a FIFO the runner creates, or the type of the
    special file the case made itself; the hook payload drives the real hook in a skip case."""

    ROW = [{"key": "k1", "ts": _iso(), "open_ids": ["42"]}]

    SPECIAL_TIMEOUT = Doctor.SPECIAL_TIMEOUT
    _doctor_bounded = Doctor._doctor_bounded

    def setUp(self):
        super().setUp()
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))

    def _reg(self, **overrides):
        reg = self.stage2(**overrides)
        self.write_registry(reg)
        self.set_items([item("42")])
        return reg

    def _argv_cannot_run(self):
        # A non-string element: _orch_enumerate returns ENUMERATOR_ERROR unrun (aiqt_hooks.py:_orch_enumerate).
        return {"argv": [sys.executable, "-I", str(self.enum_script), str(self.backlog), 5],
                "timeout": 5}

    def _rows_file(self, path, rows):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def _at(self):
        return self._p("attestations.jsonl")

    def _sd(self, name):
        return self.state_dir() / name

    STOP = ("preflight", "stop")
    AUDIT = ("--resume-audit",)

    # --- non-blocking opens (NONBLOCKING_CASES): the registry files
    def case_registry_local(self):
        self._reg()
        return self.repo / ".aiqt" / "orchestration.local.json", None, self.STOP, {}

    def case_registry_committed_without_local(self):
        (self.repo / ".aiqt").mkdir(exist_ok=True)
        return self.repo / ".aiqt" / "orchestration.json", None, self.AUDIT, {}

    # --- scope.lease
    def _holder(self):
        reg = self.stage2()
        reg["lease"]["holder_is_session_id"] = True
        self.write_registry(reg)
        self.set_items([item("42")])

    def case_lease_holder_directory(self):
        self._holder()
        lease = Path(self._p("session-state.md"))
        lease.mkdir()
        (lease / "entry").write_text("held\n", encoding="utf-8")
        self.assertGreater(os.stat(lease).st_size, 0, "precondition: a non-empty directory")
        return lease, "directory", self.STOP + ("--session-id", "sess-1"), {"session_id": "sess-1"}

    def case_lease_holder_fifo_is_empty(self):
        # A FIFO has size 0, so the lease is not live (aiqt_hooks.py:_orch_scope_live `if st.st_size > 0 and (fresh or cannot):`) and the hook reads the mode record.
        self._holder()
        return (Path(self._p("session-state.md")), None, self.STOP + ("--session-id", "sess-1"),
                {"session_id": "sess-1"})

    def case_lease_holder_without_session_id(self):
        # No session id: the hook returns False at aiqt_hooks.py:_orch_scope_live `if not (isinstance(session_id, str) and session_id):` before the open at aiqt_hooks.py:_orch_scope_live `with open(path,`.
        self._holder()
        lease = Path(self._p("session-state.md"))
        lease.mkdir()
        (lease / "entry").write_text("held\n", encoding="utf-8")
        self.assertGreater(os.stat(lease).st_size, 0, "precondition: a non-empty directory")
        return lease, "directory", self.STOP, {}

    # --- non-blocking opens (NONBLOCKING_CASES): the mode record
    def case_mode_without_lease(self):
        self._reg()
        return Path(self._p("operating-mode.md")), None, self.STOP, {}

    # --- ctx.*
    def case_turn_state(self):
        self._reg()
        return self._sd("turn-state.json"), None, self.STOP, {}

    def case_turn_state_out_of_scope(self):
        self._reg(drop=("mode",))
        return self._sd("turn-state.json"), None, self.STOP, {}

    def case_operand(self):
        self._reg()
        return self.backlog, None, self.STOP, {}

    def case_operand_argv_cannot_run(self):
        self._reg(enumerator=self._argv_cannot_run())
        return self.backlog, None, self.STOP, {}

    def case_ledger(self):
        self._reg()
        return self._sd("dispatch-ledger.jsonl"), None, self.STOP, {}

    def case_ledger_argv_cannot_run(self):
        self._reg(enumerator=self._argv_cannot_run())
        return self._sd("dispatch-ledger.jsonl"), None, self.STOP, {}

    def case_ctx_pending(self):
        self._reg()
        return Path(self._p("pending-decisions.md")), None, self.STOP, {}

    def case_ctx_pending_argv_cannot_run(self):
        self._reg(enumerator=self._argv_cannot_run())
        return Path(self._p("pending-decisions.md")), None, self.STOP, {}

    def case_checkpoint(self):
        self._reg()
        return self._sd("backlog-checkpoint.json"), None, self.STOP, {}

    def case_checkpoint_argv_cannot_run(self):
        self._reg(enumerator=self._argv_cannot_run())
        return self._sd("backlog-checkpoint.json"), None, self.STOP, {}

    def case_snapshot(self):
        self._reg(attestations=self._at())
        return self._sd("attestations-validated.json"), None, self.STOP, {}

    def case_snapshot_argv_cannot_run(self):
        self._reg(attestations=self._at(), enumerator=self._argv_cannot_run())
        return self._sd("attestations-validated.json"), None, self.STOP, {}

    def case_snapshot_undeclared(self):
        self._reg()
        return self._sd("attestations-validated.json"), None, self.STOP, {}

    def case_ctx_register(self):
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        return Path(self._at()), None, self.STOP, {}

    def case_ctx_register_without_snapshot(self):
        # No snapshot: the open at aiqt_hooks.py:_orch_attestation_refs `with open(path,` fails and the reader returns at
        # aiqt_hooks.py:_orch_attestation_refs `except (OSError, ValueError):`.
        self._reg(attestations=self._at())
        return Path(self._at()), None, self.STOP, {}

    def case_ctx_anchor(self):
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        Path(self._at()).write_text("", encoding="utf-8")
        return Path(self._at() + ".anchor"), None, self.STOP, {}

    def case_ctx_guard_events(self):
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        Path(self._at()).write_text("", encoding="utf-8")
        return self._sd("guard-events.jsonl"), None, self.STOP, {}

    def case_ctx_guard_events_without_register(self):
        # No register: the read inside the build is not reached, but the append after the verdict is.
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        return self._sd("guard-events.jsonl"), None, self.STOP, {}

    def case_ctx_guard_events_undeclared(self):
        self._reg()
        return self._sd("guard-events.jsonl"), None, self.STOP, {}

    def case_ctx_guard_events_out_of_scope(self):
        self._reg(drop=("mode",))
        return self._sd("guard-events.jsonl"), None, self.STOP, {}

    # --- verdict.*: the writes after the verdict
    def case_verdict_escape_spoof(self):
        # A self-owned sentinel at the declared escape path is ignored and spoof-recorded, as the escape tests above show.
        self._reg()
        self.self_owned_sentinel("ESCAPE-ALLOW-YIELD")
        return self._sd("escape-spoof.json"), None, self.STOP, {}

    def case_verdict_escape_spoof_without_sentinel(self):
        self._reg()
        return self._sd("escape-spoof.json"), None, self.STOP, {}

    def case_verdict_forced_exit(self):
        # stop_hook_active sets the loop signal, so the open item 42 is released with findings and the
        # exit is recorded as forced (aiqt_hooks.py:_orch_record_forced_exit).
        self._reg()
        return (self._sd("forced-exit.jsonl"), None, self.STOP + ("--stop-hook-active",),
                {"stop_hook_active": True})

    def case_verdict_forced_exit_without_loop_signal(self):
        self._reg()
        return self._sd("forced-exit.jsonl"), None, self.STOP, {}

    # --- audit.*
    def case_audit_handoff(self):
        self._reg()
        return Path(self._p("session-handoff.md")), None, self.AUDIT, {}

    def case_audit_findings(self):
        self._reg()
        return Path(self._p("open-findings.md")), None, self.AUDIT, {}

    def case_audit_pending(self):
        self._reg()
        return Path(self._p("pending-decisions.md")), None, self.AUDIT, {}

    def case_audit_register(self):
        self._reg(attestations=self._at())
        return Path(self._at()), None, self.AUDIT, {}

    def case_audit_anchor(self):
        self._reg(attestations=self._at())
        Path(self._at()).write_text("", encoding="utf-8")
        return Path(self._at() + ".anchor"), None, self.AUDIT, {}

    def case_audit_snapshot_tmp(self):
        self._reg(attestations=self._at())
        return self._sd("attestations-validated.json.tmp"), None, self.AUDIT, {}

    def case_audit_mistakes(self):
        self._reg(mistakes_register=self._p("mistakes.jsonl"))
        return Path(self._p("mistakes.jsonl")), None, self.AUDIT, {}

    def case_audit_guard_events(self):
        self._reg()
        return self._sd("guard-events.jsonl"), None, self.AUDIT, {}

    def case_audit_escape_spoof(self):
        self._reg()
        return self._sd("escape-spoof.json"), None, self.AUDIT, {}

    def case_audit_forced_exit(self):
        self._reg()
        return self._sd("forced-exit.jsonl"), None, self.AUDIT, {}

    def case_audit_surfaced(self):
        self._reg()
        self._rows_file(self._sd("forced-exit.jsonl"), self.ROW)
        return self._sd("forced-exit-surfaced.json"), None, self.AUDIT, {}

    def case_audit_surfaced_without_log(self):
        self._reg()
        return self._sd("forced-exit-surfaced.json"), None, self.AUDIT, {}

    def case_audit_surfaced_with_empty_log(self):
        self._reg()
        self._rows_file(self._sd("forced-exit.jsonl"), [])
        return self._sd("forced-exit-surfaced.json"), None, self.AUDIT, {}

    def case_audit_surfaced_tmp(self):
        self._reg()
        self._rows_file(self._sd("forced-exit.jsonl"), self.ROW)
        return self._sd("forced-exit-surfaced.json.tmp"), None, self.AUDIT, {}

    def _bad_registry_state(self, name):
        (self.repo / ".aiqt").mkdir(exist_ok=True)
        (self.repo / ".aiqt" / "orchestration.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.run_hook("orch_resume_audit", {}).returncode, 0)
        barriers = self.find_anywhere("resume-barrier.json")
        self.assertEqual(len(barriers), 1, "precondition: the hook wrote one barrier")
        return Path(barriers[0]).parent / name

    def case_bad_registry_unused(self):
        return self._bad_registry_state("resume-barrier.json.unused"), None, self.AUDIT, {}

    def case_bad_registry_guard_events(self):
        return self._bad_registry_state("guard-events.jsonl"), None, self.AUDIT, {}

    def case_bad_registry_escape_spoof(self):
        # On an unreadable registry the hook runs the resume probes over an empty registry
        # (aiqt_hooks.py:_orch_resume_audit_findings `reg = {}`), which open escape-spoof.json and forced-exit.jsonl
        # (aiqt_hooks.py:_orch_pending_artefact_findings `if os.path.lexists(path):`).
        return self._bad_registry_state("escape-spoof.json"), None, self.AUDIT, {}

    def case_bad_registry_forced_exit(self):
        return self._bad_registry_state("forced-exit.jsonl"), None, self.AUDIT, {}

    # --- the runner
    def _hook_bounded(self, args, payload):
        # The resume audit runs orch_resume_audit itself, exactly as the doctor does; the preflight
        # runs the preview call path (PREVIEW_PATH_PROG), the hook functions the doctor calls.
        if args[0] == "--resume-audit":
            argv = [sys.executable, "-I", str(HOOK), "orch_resume_audit"]
            body = json.dumps({"cwd": str(self.repo)})
        else:
            argv = [sys.executable, "-I", "-c", PREVIEW_PATH_PROG, str(HOOK), str(self.repo),
                    payload.get("session_id", "")]
            body = ""
        try:
            h = subprocess.run(argv, input=body, capture_output=True, text=True, env=self._env(),
                               timeout=self.SPECIAL_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the hook call path did not exit within {} s: it does reach this open"
                      .format(self.SPECIAL_TIMEOUT))
        if args[0] != "--resume-audit":
            self.assertEqual(h.returncode, 0, h.stdout + h.stderr)
            self.assertIn("completed", h.stdout)
        return h

    def _run_case(self, expect, case):
        path, made, args, payload = getattr(self, case)()
        path = Path(path)
        if made is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink() or path.exists():
                path.unlink()
            os.mkfifo(path)
            made = "FIFO"
        r = self._doctor_bounded(*args)
        self.assertNotIn("Traceback", r.stderr)
        if expect == "reach":
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("cannot evaluate: the ", r.stdout)
            self.assertIn("{} is not a regular file (it is a {})".format(path, made), r.stdout)
            return
        self.assertNotIn("cannot evaluate", r.stdout)
        # A nonblock case may end in the unreadable-registry exit 2 the hook reader itself gives.
        self.assertIn(r.returncode, (0, 1, 2) if expect == "nonblock" else (0, 1), r.stdout + r.stderr)
        h = self._hook_bounded(args, payload)
        self.assertNotIn("Traceback", h.stderr)
        if made == "FIFO":
            self.assertTrue(path.is_fifo(), "the FIFO was replaced, so the contrast proves nothing")

    def test_every_case_against_the_doctor_and_the_hook(self):
        for site, expect, case in PRECHECK_CASES:
            with self.subTest(site=site, expect=expect, case=case):
                self.tearDown()
                self.setUp()
                self._run_case(expect, case)

    def test_every_nonblocking_open_runs_past_a_fifo(self):
        for label, case in NONBLOCKING_CASES:
            with self.subTest(open=label, case=case):
                self.tearDown()
                self.setUp()
                self._run_case("nonblock", case)


class DoctorBlockingWrites(Stage2Harness):
    """The judged handler appends a guard-events row on every verdict, a clean ALLOW included
    (aiqt_hooks.py:_orch_stop_family `_orch_guard_event(root, event_name, verdict.lower(), reason)`,
    aiqt_hooks.py:orch_yield_tool `_orch_guard_event(root, "yield-tool", verdict.lower(), reason)`), with a
    plain blocking open (aiqt_hooks.py:_orch_append_jsonl `with open(path,`), and writes escape-spoof.json
    and forced-exit.jsonl the same way when it reaches them. Each case runs the REAL hook on the same state
    as the doctor: with a FIFO at the path the hook blocks (it does not exit within HOOK_TIMEOUT) and the
    doctor reports cannot-evaluate, exit 2, naming the path; without the FIFO both complete, and the
    doctor reports the verdict the hook gives."""

    HOOK_TIMEOUT = 8
    SPECIAL_TIMEOUT = Doctor.SPECIAL_TIMEOUT
    _doctor_bounded = Doctor._doctor_bounded

    def setUp(self):
        super().setUp()
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))

    def _real_hook_blocks(self, action, payload):
        payload = dict(payload)
        payload.setdefault("cwd", str(self.repo))
        try:
            subprocess.run([sys.executable, "-I", str(HOOK), action], input=json.dumps(payload),
                           capture_output=True, text=True, env=self._env(), timeout=self.HOOK_TIMEOUT)
        except subprocess.TimeoutExpired:
            return True
        return False

    def _fifo(self, name):
        self.state_dir().mkdir(parents=True, exist_ok=True)
        path = self.state_dir() / name
        os.mkfifo(path)
        return path

    def _clean(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed")])

    def test_clean_allow_without_a_fifo_agrees(self):
        self._clean()
        for kind in ("stop", "idle"):
            with self.subTest(kind=kind):
                r = self._doctor_bounded("preflight", kind)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("effective verdict: ALLOW", r.stdout)
        self.assertEqual(self.stop().returncode, 0)
        self.assertEqual(self.schedule().returncode, 0)

    def test_fifo_guard_events_blocks_a_clean_allow_and_the_doctor_refuses(self):
        self._clean()
        path = self._fifo("guard-events.jsonl")
        for kind, action, payload in (("stop", "orch_stop_guard", {}),
                                      ("idle", "orch_yield_tool",
                                       {"tool_name": "ScheduleWakeup",
                                        "tool_input": {"prompt": "recheck", "delaySeconds": 60}})):
            with self.subTest(kind=kind):
                r = self._doctor_bounded("preflight", kind)
                self.assertNotIn("Traceback", r.stderr)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("cannot evaluate: the hook state file guard-events.jsonl {} is not a regular "
                              "file (it is a FIFO)".format(path), r.stdout)
                self.assertNotIn("effective verdict: ALLOW", r.stdout)
                self.assertTrue(self._real_hook_blocks(action, payload),
                                "the real hook completed, so the FIFO is not reached")
                self.assertTrue(path.is_fifo())

    def test_fifo_escape_spoof_blocks_and_the_doctor_refuses_after_the_verdict(self):
        self._clean()
        self.self_owned_sentinel("ESCAPE-ALLOW-YIELD")
        path = self._fifo("escape-spoof.json")
        r = self._doctor_bounded("preflight", "stop")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("cannot evaluate: the hook state file escape-spoof.json {} is not a regular file (it "
                      "is a FIFO); the hook would open it with a blocking open after its verdict".format(path),
                      r.stdout)
        self.assertTrue(self._real_hook_blocks("orch_stop_guard", {}))

    def test_fifo_forced_exit_blocks_and_the_doctor_refuses_after_the_verdict(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("42")])
        path = self._fifo("forced-exit.jsonl")
        r = self._doctor_bounded("preflight", "stop", "--stop-hook-active")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("judged verdict: ALLOW_WITH_FINDINGS", r.stdout)
        self.assertIn("cannot evaluate: the hook state file forced-exit.jsonl {} is not a regular file (it "
                      "is a FIFO); the hook would open it with a blocking open after its verdict".format(path),
                      r.stdout)
        self.assertTrue(self._real_hook_blocks("orch_stop_guard", {"stop_hook_active": True}))
        # Contrast: without the loop signal the verdict is a DENY, no forced exit is recorded, and the hook
        # completes with the FIFO in place.
        r = self._doctor_bounded("preflight", "stop")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("effective verdict: DENY", r.stdout)
        self.assertFalse(self._real_hook_blocks("orch_stop_guard", {}))
        self.assertTrue(path.is_fifo())


class LinkedStateFiles(Stage2Harness):
    """The disclosed post-gate aliasing residual of tools/check-orchestration-registry.py, case (d), pinned
    against the real hook. A record file hard-linked at the resume barrier keeps its content: the barrier
    write replaces the directory entry (aiqt_hooks.py:_orch_barrier_write `os.replace(tmp, path)`), so the
    link is replaced. A record file hard-linked at guard-events.jsonl is appended to, since that append
    opens the path in place (aiqt_hooks.py:_orch_append_jsonl `with open(path,`)."""

    def _record(self):
        record = Path(self._p("open-findings.md"))
        record.write_text("the record\n", encoding="utf-8")
        self.state_dir().mkdir(parents=True, exist_ok=True)
        return record

    def test_hard_link_at_the_barrier_is_replaced_not_clobbered(self):
        self.write_registry(self.stage2())
        record = self._record()
        barrier = self.state_dir() / "resume-barrier.json"
        os.link(record, barrier)
        self.assertEqual(self.run_hook("orch_resume_audit", {}).returncode, 0)
        self.assertEqual(record.read_text(encoding="utf-8"), "the record\n")
        self.assertNotEqual(os.stat(record).st_ino, os.stat(barrier).st_ino, "the link was not replaced")
        self.assertIn("active", json.loads(barrier.read_text(encoding="utf-8")))

    def test_hard_link_at_guard_events_is_appended_to(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        record = self._record()
        os.link(record, self.state_dir() / "guard-events.jsonl")
        self.assertEqual(self.stop().returncode, 0)
        text = record.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("the record\n") and len(text) > len("the record\n"),
                        "the guard-events append did not reach the linked record")


# The default ACL in its extended-attribute form: version 2, then (tag, permission, id) entries for the
# owner, the owning group and others, each r-x, so a directory created under it lacks owner write.
_ACL_NO_OWNER_WRITE = (b"\x02\x00\x00\x00"
                       + b"\x01\x00\x05\x00\xff\xff\xff\xff"
                       + b"\x04\x00\x05\x00\xff\xff\xff\xff"
                       + b"\x20\x00\x05\x00\xff\xff\xff\xff")
_ACL_DEFAULT = "system.posix_acl_default"


class DoctorCreatedStateDir(Stage2Harness):
    """For a state directory that does not exist, the hook creates it with os.makedirs, whose directories
    get mode 0o777 less the process umask, or, under an ancestor with a default ACL, the owner entry of
    that ACL in place of the umask. The doctor and the REAL hook run in subprocesses under the same umask,
    with the state directory absent each time. The store (the nearest existing ancestor) is first cleared
    of any default ACL it inherited from the host temporary directory, since a default ACL masks the
    umask (the host TMPDIR of this repository carries one). Under umask 0o777 the hook cannot save the
    denial counter and fails open with findings, and the doctor must predict exactly that; under umask
    0o022 both reach the DENY. Under a default ACL whose owner entry lacks write, the same holds even with
    umask 0o022."""

    SPECIAL_TIMEOUT = Doctor.SPECIAL_TIMEOUT

    def setUp(self):
        super().setUp()
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        if _ACL_DEFAULT in os.listxattr(self.store):
            os.removexattr(self.store, _ACL_DEFAULT)
        self.assertNotIn(_ACL_DEFAULT, os.listxattr(self.store), "precondition: no default ACL on the store")
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("42")])

    def _under(self, mask, argv, stdin=""):
        return subprocess.run(argv, input=stdin, capture_output=True, text=True, env=self._env(),
                              timeout=self.SPECIAL_TIMEOUT, preexec_fn=lambda: os.umask(mask))

    def _reset_state_dir(self):
        sd = self.state_dir()
        if sd.exists():
            for dirpath, _dirs, _files in os.walk(sd):
                os.chmod(dirpath, 0o755)
            shutil.rmtree(sd)
        self.assertFalse(sd.exists())

    def _pair(self, mask):
        self._reset_state_dir()
        d = self._under(mask, [sys.executable, "-I", str(DOCTOR), "preflight", "stop", "--root", str(self.repo)])
        self.assertNotIn("Traceback", d.stderr)
        self.assertFalse(self.state_dir().exists(), "the doctor created the state directory")
        h = self._under(mask, [sys.executable, "-I", str(HOOK), "orch_stop_guard"],
                        json.dumps({"cwd": str(self.repo)}))
        self.assertNotIn("Traceback", h.stderr)
        return d, h

    def test_umask_0777_fails_the_counter_save_in_the_hook_and_the_doctor(self):
        d, h = self._pair(0o777)
        self.assertEqual(h.returncode, 0, h.stdout + h.stderr)
        self.assertIn("the denial counter could not be persisted", h.stdout)
        self.assertIn("effective verdict: ALLOW_WITH_FINDINGS", d.stdout)
        self.assertIn("denial counter: could NOT be saved", d.stdout)
        self.assertIn("the process umask 0o777", d.stdout)
        self.assertIn("checkpoint rewrite (aiqt_hooks.py:_orch_checkpoint_union): would FAIL", d.stdout)

    def test_umask_0022_contrast_denies_in_the_hook_and_the_doctor(self):
        d, h = self._pair(0o022)
        self.assertEqual(h.returncode, 2, h.stdout + h.stderr)
        self.assertIn("effective verdict: DENY", d.stdout)
        self.assertIn("denial counter: could be saved", d.stdout)

    def test_default_acl_without_owner_write_replaces_the_umask(self):
        os.setxattr(self.store, _ACL_DEFAULT, _ACL_NO_OWNER_WRITE)
        self.assertIn(_ACL_DEFAULT, os.listxattr(self.store))
        d, h = self._pair(0o022)
        self.assertEqual(h.returncode, 0, h.stdout + h.stderr)
        self.assertIn("the denial counter could not be persisted", h.stdout)
        self.assertIn("effective verdict: ALLOW_WITH_FINDINGS", d.stdout)
        self.assertIn("the default ACL of {}".format(self.store), d.stdout)


class DoctorScopeMargin(Stage2Harness):
    """The hook judges lease freshness by one classifier (aiqt_hooks.py:_orch_lease_age_class:
    fresh when -_ORCH_CLOCK_SKEW <= age <= max_age_hours * 3600), and the doctor samples that same
    classifier at the clock now and SCOPE_MARGIN seconds later (orch_doctor.py _lease_live_states), so a
    lease near a bound counts as possibly on either side, and the holder lease open (scope.lease,
    aiqt_hooks.py:_orch_scope_live `with open(path,`) is checked whenever either sample reads it live. The
    mode record is read non-blocking (aiqt_hooks.py:_orch_mode_read) and is no longer a pre-check site.
    Each case sets the lease mtime NEAR seconds from a bound: just inside max_age_hours at the upper
    bound (live now, stale after the margin: the open is checked on the first sample), and just beyond
    the skew tolerance into the future at the lower bound (future now, fresh after the margin: the open
    is checked only on the second sample, so with SCOPE_MARGIN = 0.0 the lower case misses the lease).
    The special lease is a non-empty directory, which the hook does open (a FIFO has size 0 and is
    never live, case_lease_holder_fifo_is_empty). The skew is read from the hook source and
    max_age_hours from the fixture registry, not restated here."""

    NEAR = 4.5  # seconds from the bound; the case needs the doctor to check within this time

    SPECIAL_TIMEOUT = Doctor.SPECIAL_TIMEOUT
    _doctor_bounded = Doctor._doctor_bounded

    def setUp(self):
        super().setUp()
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))

    def _hook_constant(self, name):
        for node in ast.parse(HOOK.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name \
                    and isinstance(node.value, ast.Constant):
                return node.value.value
        self.fail("{} is not a module constant of {}".format(name, HOOK))

    def _registry(self):
        reg = self.stage2()
        reg["lease"]["holder_is_session_id"] = True
        self.write_registry(reg)
        self.set_items([item("42")])
        return reg

    def _lease_age(self, reg, bound):
        if bound == "upper":
            return reg["lease"]["max_age_hours"] * 3600 - self.NEAR
        skew = self._hook_constant("_ORCH_CLOCK_SKEW")
        self.assertIsInstance(skew, (int, float))
        return -skew - self.NEAR

    def _assert_refused_near(self, bound):
        reg = self._registry()
        lease = Path(self._p("session-state.md"))
        lease.mkdir()
        (lease / "entry").write_text("held\n", encoding="utf-8")
        path, label, kind = lease, "lease.path", "directory"
        self.assertGreater(os.stat(lease).st_size, 0, "precondition: a non-empty lease")
        age = self._lease_age(reg, bound)
        start = time.time()
        os.utime(lease, (start - age, start - age))
        r = self._doctor_bounded("preflight", "stop", "--session-id", "sess-1")
        elapsed = time.time() - start
        self.assertLess(elapsed, self.NEAR, "the doctor took {:.1f} s, so the lease may have crossed "
                        "the bound before the check and the case proves nothing".format(elapsed))
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("cannot evaluate: the declared {} {} is not a regular file (it is a {})"
                      .format(label, path, kind), r.stdout)

    def test_near_the_max_age_bound_the_lease_open_is_checked(self):
        self._assert_refused_near("upper")

    def test_near_the_clock_skew_bound_the_lease_open_is_checked(self):
        self._assert_refused_near("lower")


# =====================================================================================================
# Every event field the previewed handlers read is previewed as the hook reads it
# =====================================================================================================
# (container, field) -> (status, doctor input or reason, the hook functions that read it). "data" is the
# event payload and "tool_input" its tool_input object; the field "values()" is the read of every
# value of tool_input. A modelled field names the doctor input that passes it exactly as the hook
# reads it; an unpreviewed field gives the reason no input is needed. The probe below requires the
# functions to equal those its scan finds, so the citations are checked, not narrated.
EVENT_FIELDS = {
    # _orch_root, reached from _orch_stop_family and orch_yield_tool
    ("data", "cwd"): ("modelled", "--root", ("_orch_root",)),
    ("data", "session_id"): ("modelled", "--session-id", ("_orch_stop_family", "orch_yield_tool")),
    # _orch_build_ctx, reached from the context build of each handler
    ("data", "stop_hook_active"): ("modelled", "--stop-hook-active", ("_orch_build_ctx",)),
    ("data", "tool_name"): ("modelled", "--tool", ("orch_yield_tool",)),
    ("data", "tool_input"): ("modelled", "--tool-stop and --wake-text", ("orch_yield_tool",)),
    ("tool_input", "stop"): ("modelled", "--tool-stop", ("orch_yield_tool",)),
    ("tool_input", "values()"): ("modelled", "--wake-text", ("orch_yield_tool",)),
    ("tool_input", "prompt"): ("unpreviewed", "read only after an allowed schedule verdict, for the "
                               "wake-digest write (_orch_register_wake, aiqt_hooks.py:_orch_register_wake); "
                               "it never changes the verdict", ("orch_yield_tool",)),
}
# The handlers the doctor previews: preflight stop (Stop) and preflight idle (a scheduling call).
PREVIEWED_HANDLERS = ("orch_stop_guard", "orch_yield_tool")
# The event fields whose value is an object the hook reads field by field.
CONTAINER_FIELDS = ("tool_input",)


def event_field_reads(source, handlers=PREVIEWED_HANDLERS):
    """(reads, unreviewed) over the hook source. reads maps (container, field) to the set of module
    functions that read it, traced from the event parameter of each handler through every module function the
    event data is passed to, positionally or by keyword; a local assigned from a read of a container
    field is followed as that container. unreviewed lists (line, text) for every other use of the
    event data or of a container (a computed key, an alias, a pass to a callee that is not a module
    function, an iteration), so a field read in a form the scan does not model fails rather than
    going unseen."""
    tree = ast.parse(source)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def literal_read(node):
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            call = parents.get(parent)
            if isinstance(call, ast.Call) and call.func is parent:
                first = call.args[0] if call.args else None
                if parent.attr == "get" and isinstance(first, ast.Constant) \
                        and isinstance(first.value, str):
                    return first.value
                if parent.attr == "values" and not call.args and not call.keywords:
                    return "values()"
            return None
        if isinstance(parent, ast.Subscript) and parent.value is node \
                and isinstance(parent.slice, ast.Constant) and isinstance(parent.slice.value, str):
            return parent.slice.value
        return None

    reads, unreviewed, seen = {}, [], set()
    work = [(name, funcs[name].args.args[0].arg) for name in handlers]
    while work:
        fname, param = work.pop()
        if (fname, param) in seen:
            continue
        seen.add((fname, param))
        fn = funcs[fname]
        aliases = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                for inner in ast.walk(node.value):
                    if isinstance(inner, ast.Name) and inner.id == param \
                            and literal_read(inner) in CONTAINER_FIELDS:
                        aliases[node.targets[0].id] = literal_read(inner)
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)):
                continue
            if node.id == param:
                container = "data"
            elif node.id in aliases:
                container = aliases[node.id]
            else:
                continue
            field = literal_read(node)
            if field is not None:
                reads.setdefault((container, field), set()).add(fname)
                continue
            parent = parents.get(node)
            holder = parents.get(parent) if isinstance(parent, ast.keyword) else parent
            if container == "data" and isinstance(holder, ast.Call) \
                    and isinstance(holder.func, ast.Name) and holder.func.id in funcs:
                params = [a.arg for a in funcs[holder.func.id].args.args]
                if isinstance(parent, ast.keyword) and parent.arg in params:
                    work.append((holder.func.id, parent.arg))
                    continue
                index = next((i for i, a in enumerate(holder.args) if a is node), None)
                if index is not None and index < len(params):
                    work.append((holder.func.id, params[index]))
                    continue
            unreviewed.append((node.lineno, ast.unparse(parent) if parent is not None else node.id))
    return reads, unreviewed


# One mutation of each kind the probe must refuse, as (name, anchor, replacement) over the hook
# source: a new data field, a new tool_input field, an alias of the event data, and a computed key.
CTX_ANCHOR = "    staleness = _orch_validate(\"staleness\", reg.get(\"staleness\"))[1]\n"
YIELD_ANCHOR = "    kind = \"stop\" if tool_input.get(\"stop\") is True else \"schedule_idle\"\n"
EVENT_FIELD_MUTATIONS = (
    ("a new data field read in the context", CTX_ANCHOR,
     CTX_ANCHOR + "    _probe = data.get(\"transcript_path\")\n", "field"),
    ("a new tool_input field read", YIELD_ANCHOR,
     YIELD_ANCHOR + "    _probe = tool_input.get(\"delaySeconds\")\n", "field"),
    ("an alias of the event data", CTX_ANCHOR, CTX_ANCHOR + "    _probe = data\n", "unreviewed"),
    ("a computed key", CTX_ANCHOR, CTX_ANCHOR + "    _probe = data[kind]\n", "unreviewed"),
)


class DoctorEventFieldProbe(unittest.TestCase):
    """Class probe: the hook event fields read on the previewed paths equal the reviewed
    table, each modelled by a doctor input or unpreviewed with a reason."""

    def source(self):
        if not HOOK.exists():
            self.fail("installed hook not found: {}".format(HOOK))
        return HOOK.read_text(encoding="utf-8")

    def test_every_event_field_read_on_the_previewed_paths_is_reviewed(self):
        reads, unreviewed = event_field_reads(self.source())
        self.assertEqual(unreviewed, [], "an event-data use the probe does not model")
        self.assertEqual(sorted(reads), sorted(EVENT_FIELDS),
                         "the event fields the hook reads and the reviewed table differ")
        for key, (status, detail, symbols) in EVENT_FIELDS.items():
            with self.subTest(field=key):
                self.assertIn(status, ("modelled", "unpreviewed"))
                self.assertTrue(detail, "no doctor input or reason")
                self.assertEqual(reads[key], set(symbols), "the cited hook functions are stale")

    def test_every_modelled_input_is_a_doctor_option(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        r = subprocess.run([sys.executable, "-I", str(DOCTOR), "--help"], capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        source = DOCTOR.read_text(encoding="utf-8")
        for key, (status, detail, _lines) in EVENT_FIELDS.items():
            if status != "modelled":
                continue
            for option in detail.split(" and "):
                with self.subTest(field=key, option=option):
                    self.assertIn(option, r.stdout)
        # Each field has its row in the doctor docstring table, naming the same hook functions.
        table = {}
        for row in source.splitlines():
            parts = row.split()
            if len(parts) >= 3 and parts[0] in ("data", "tool_input") and row.startswith("    "):
                table.setdefault((parts[0], parts[1]), row)
        for (container, field), (_status, _detail, symbols) in EVENT_FIELDS.items():
            with self.subTest(row=(container, field)):
                row = table.get((container, field.replace("()", "")))
                self.assertIsNotNone(row, "the doctor docstring table omits a field")
                self.assertIn(" " + ", ".join(symbols) + " ", row,
                              "the doctor docstring table cites other hook functions")

    def test_the_probe_refuses_each_mutation(self):
        source = self.source()
        for name, anchor, replacement, kind in EVENT_FIELD_MUTATIONS:
            with self.subTest(mutation=name):
                self.assertEqual(source.count(anchor), 1, "the mutation anchor is not unique")
                reads, unreviewed = event_field_reads(source.replace(anchor, replacement))
                if kind == "field":
                    self.assertNotEqual(sorted(reads), sorted(EVENT_FIELDS),
                                        "the probe missed {}".format(name))
                    self.assertEqual(unreviewed, [])
                else:
                    self.assertNotEqual(unreviewed, [], "the probe accepted {}".format(name))


class DoctorEventFields(Stage2Harness):
    """The doctor previews stop_hook_active and tool_input stop exactly as the hook reads
    them, so its verdict equals that of the real hook on the same state. Each case resets the state
    directory, runs the doctor first (it writes nothing) and then the hook."""

    def setUp(self):
        super().setUp()
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))

    def _arm(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("7", title="Ship the widget")])

    def _reset(self, seed=None):
        shutil.rmtree(self.state_dir(), ignore_errors=True)
        if seed is not None:
            self.seed_state("turn-state.json", seed)

    def _doctor_verdict(self, *args):
        r = self.run_doctor("preflight", *args)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("effective verdict: ")]
        self.assertEqual(len(lines), 1, r.stdout + r.stderr)
        verdict = lines[0][len("effective verdict: "):].split()[0]
        self.assertEqual(r.returncode, 0 if verdict == "ALLOW" else 1, r.stdout + r.stderr)
        return verdict, r.stdout

    def _hook_verdict(self, action, payload):
        r = self.run_hook(action, payload)
        if action == "orch_stop_guard" and r.returncode == 2:
            return "DENY"
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        if out is None:
            return "ALLOW"
        if out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
            return "DENY"
        return "ALLOW_WITH_FINDINGS"

    def _yield_payload(self, tool_input, **extra):
        payload = {"tool_name": "ScheduleWakeup", "tool_input": tool_input}
        payload.update(extra)
        return payload

    def test_the_doctor_verdict_equals_the_hook_verdict_for_each_event_field(self):
        self._arm()
        bound = {"stop_denials": 2}
        cases = (
            ("a Stop with stop_hook_active true", None, ("stop", "--stop-hook-active"),
             "orch_stop_guard", {"stop_hook_active": True}, "ALLOW_WITH_FINDINGS"),
            ("a Stop without it (contrast)", None, ("stop",), "orch_stop_guard", {}, "DENY"),
            ("a scheduling call with tool_input stop true at the loop bound", bound,
             ("idle", "--tool-stop", "--wake-text", "end the loop"), "orch_yield_tool",
             self._yield_payload({"stop": True, "prompt": "end the loop"}), "ALLOW_WITH_FINDINGS"),
            ("the same call without stop (contrast)", bound,
             ("idle", "--wake-text", "end the loop"), "orch_yield_tool",
             self._yield_payload({"prompt": "end the loop"}), "DENY"),
            ("tool_input stop true with stop_hook_active true", None,
             ("idle", "--tool-stop", "--stop-hook-active", "--wake-text", "end the loop"),
             "orch_yield_tool", self._yield_payload({"stop": True, "prompt": "end the loop"},
                                                    stop_hook_active=True),
             "ALLOW_WITH_FINDINGS"),
            ("tool_input stop true below the bound", None,
             ("idle", "--tool-stop", "--wake-text", "end the loop"), "orch_yield_tool",
             self._yield_payload({"stop": True, "prompt": "end the loop"}), "DENY"),
            ("stop_hook_active on a schedule_idle call is no loop signal", None,
             ("idle", "--stop-hook-active", "--wake-text", "recheck the queue"), "orch_yield_tool",
             self._yield_payload({"prompt": "recheck the queue"}, stop_hook_active=True), "DENY"),
        )
        for name, seed, doctor_args, action, payload, expected in cases:
            with self.subTest(case=name):
                self._reset(seed)
                before = tree_state(self._tmp)
                verdict, stdout = self._doctor_verdict(*doctor_args)
                self.assertEqual(tree_state(self._tmp), before, "preflight changed a file")
                self._reset(seed)
                self.assertEqual(self._hook_verdict(action, payload), expected,
                                 "precondition: the hook verdict")
                self.assertEqual(verdict, expected, stdout)
                if "--tool-stop" in doctor_args:
                    self.assertIn("judged kind: stop (tool_input stop is true", stdout)
                    self.assertIn("quiet-claim check: not applicable", stdout)
                if "--stop-hook-active" in doctor_args and doctor_args[0] == "stop":
                    self.assertIn("loop signal: set", stdout)

    def test_a_stop_kind_scheduling_deny_stands_with_an_unsaved_counter(self):
        # aiqt_hooks.py:orch_yield_tool: the scheduling path reports a failed counter save on its DENY,
        # which stands on the stop kind too, unlike the Stop event (aiqt_hooks.py:_orch_stop_family). The
        # hook writer replaces turn-state.json whatever its mode, so the save is made to fail with a
        # state directory the hook can search but not write.
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0500 directory, so the save cannot fail here")
        self._arm()
        self.seed_state("turn-state.json", {})
        os.chmod(self.state_dir(), 0o500)
        verdict, stdout = self._doctor_verdict("idle", "--tool-stop", "--wake-text", "end the loop")
        self.assertEqual(verdict, "DENY", stdout)
        self.assertIn("denial counter: not checked; a scheduling DENY stands", stdout)
        self.assertEqual(self._hook_verdict("orch_yield_tool", self._yield_payload(
            {"stop": True, "prompt": "end the loop"})), "DENY")

    def test_inputs_outside_their_preflight_kind_are_usage_errors(self):
        self.write_registry(self.stage2())
        for args in (("preflight", "stop", "--tool-stop"), ("preflight", "stop", "--wake-text", "x"),
                     ("--resume-audit", "--tool-stop"), ("--resume-audit", "--stop-hook-active")):
            with self.subTest(args=args):
                r = self.run_doctor(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("only to preflight", r.stderr)


class DoctorCheckpointWrites(Stage2Harness):
    """The checkpoint union rewrites the checkpoint (aiqt_hooks.py:_orch_checkpoint_union
    `unsaved = _orch_write_json_atomic(path,`) and, when that succeeds and no init marker exists, writes
    the marker (aiqt_hooks.py:_orch_checkpoint_union `unsaved = _orch_write_json_atomic(marker,`), whose
    failure injects a cannot-evaluate row. Both go through the hook writer, which creates its temporary
    file under a fresh random name with O_EXCL and O_NOFOLLOW (aiqt_hooks.py:_orch_write_json_at). The
    doctor predicts each outcome without writing, so its verdict equals that of the real hook on the
    same state. Each case arranges a fresh tree per kind, runs the doctor first (it writes nothing) and
    then the hook."""

    TIMEOUT = 30

    def setUp(self):
        super().setUp()
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))

    def _base(self):
        # A live lease, an empty backlog and no init marker: the hook allows unless a write fails.
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([])
        self.state_dir().mkdir(parents=True, exist_ok=True)

    def _doctor(self, kind):
        args = ["preflight", kind]
        if kind == "idle":
            args += ["--wake-text", "recheck the work queue"]
        try:
            return subprocess.run([sys.executable, "-I", str(DOCTOR), *args, "--root", str(self.repo)],
                                  capture_output=True, text=True, env=self._env(),
                                  timeout=self.TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the doctor did not exit within {} s".format(self.TIMEOUT))

    def _hook(self, kind):
        # An ALLOW whose only output is the recording-failure warnings the hook appends (each begins
        # "Additionally,") is still an ALLOW: the hook surfaces a failed write without changing the
        # verdict (aiqt_hooks.py:_orch_warn_tail).
        r = self.stop() if kind == "stop" else self.schedule()
        if kind == "stop" and r.returncode == 2:
            return "DENY", r
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        if out is None:
            return "ALLOW", r
        if out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
            return "DENY", r
        _head, _sep, rest = str(out.get("systemMessage", "")).partition(": ")
        if rest.startswith("Additionally,"):
            return "ALLOW", r
        return "ALLOW_WITH_FINDINGS", r

    def _fresh(self, arrange):
        self.tearDown()
        self.setUp()
        self._base()
        arrange()

    def _assert_agrees(self, arrange, expected, *needles):
        for kind in ("stop", "idle"):
            with self.subTest(kind=kind):
                self._fresh(arrange)
                before = tree_state(self._tmp)
                r = self._doctor(kind)
                self.assertEqual(tree_state(self._tmp), before, "preflight changed a file")
                lines = [ln for ln in r.stdout.splitlines() if ln.startswith("effective verdict: ")]
                self.assertEqual(len(lines), 1, r.stdout + r.stderr)
                verdict = lines[0][len("effective verdict: "):].split()[0]
                self.assertEqual(r.returncode, 0 if verdict == "ALLOW" else 1, r.stdout + r.stderr)
                hook_verdict, h = self._hook(kind)
                self.assertEqual(hook_verdict, expected,
                                 "precondition: the hook verdict ({})".format(h.stdout + h.stderr))
                self.assertEqual(verdict, expected, r.stdout)
                for needle in needles:
                    self.assertIn(needle, r.stdout)

    def test_a_file_at_a_fixed_temporary_path_is_never_opened(self):
        # An earlier hook writer opened <path>.tmp for writing, so a FIFO there blocked it and a
        # directory there failed it. The vendored writer never opens a file already present, so each
        # of these leaves both writes to succeed: the doctor predicts that, and the hook allows
        # without blocking, writes the marker and leaves the planted entries as they were.
        def fifo():
            os.mkfifo(self.state_dir() / "backlog-checkpoint.json.tmp")
            os.mkfifo(self.state_dir() / "checkpoint-init.marker.tmp")

        def directory():
            (self.state_dir() / "backlog-checkpoint.json.tmp").mkdir()
            (self.state_dir() / "checkpoint-init.marker.tmp").mkdir()

        def symlink_to_fifo():
            target = self._tmp / "elsewhere.fifo"
            os.mkfifo(target)
            os.symlink(target, self.state_dir() / "backlog-checkpoint.json.tmp")
            os.symlink(target, self.state_dir() / "checkpoint-init.marker.tmp")
        for name, arrange in (("a FIFO", fifo), ("a directory", directory),
                              ("a symbolic link to a FIFO", symlink_to_fifo)):
            with self.subTest(planted=name):
                self._assert_agrees(arrange, "ALLOW",
                                    "checkpoint rewrite (aiqt_hooks.py:_orch_checkpoint_union): would succeed",
                                    "init-marker write (aiqt_hooks.py:_orch_checkpoint_union): would succeed")
                sd = self.state_dir()
                self.assertTrue((sd / "checkpoint-init.marker").is_file(), "the hook wrote the marker")
                for planted in ("backlog-checkpoint.json.tmp", "checkpoint-init.marker.tmp"):
                    self.assertTrue(os.path.lexists(sd / planted), "the planted entry is untouched")
                self.assertEqual(self._marker_events(), [])

    def _marker_events(self):
        rows = self.read_jsonl("guard-events.jsonl") or []
        return [row for row in rows if row.get("kind") == "checkpoint-marker-unwritable"]

    def test_a_failed_checkpoint_rewrite_skips_the_marker_write_as_the_hook_does(self):
        # A state directory the hook can search but not write fails the checkpoint rewrite, so the
        # hook never reaches the marker write and allows; it adds a recording-failure warning only.
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0500 directory, so the rewrite cannot fail here")
        self._assert_agrees(lambda: os.chmod(self.state_dir(), 0o500), "ALLOW",
                            "checkpoint rewrite (aiqt_hooks.py:_orch_checkpoint_union): would FAIL",
                            "init-marker write (aiqt_hooks.py:_orch_checkpoint_union): not reached")
        self.assertFalse(os.path.lexists(self.state_dir() / "checkpoint-init.marker"))

    def test_a_present_marker_is_not_rewritten_as_the_hook_does(self):
        # Contrast: with a checkpoint and a marker present, the hook skips the marker write.
        def arrange():
            self.seed_state("backlog-checkpoint.json", {"version": 1, "ts": _iso(), "ids": {}})
            self.seed_state("checkpoint-init.marker", {"version": 1, "ts": _iso()})
        self._assert_agrees(arrange, "ALLOW",
                            "init-marker write (aiqt_hooks.py:_orch_checkpoint_union): not reached")


# Runs in a separate python3 -I process: load the doctor by path, build the preview context with
# _atomic_write_outcome failing the init-marker write when the case is fail, then build the hook
# context with the hook writer failing that same write, and report the cannot-evaluate rows and the
# verdict of each.
FAULT_PROG = """
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("orch_doctor_under_test", sys.argv[1])
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
hook = doctor._load_hook()
root = hook._recovery_toplevel(sys.argv[2])
fail = sys.argv[3] == "fail"
status, reg = hook._orch_registry(root)
marker = os.path.join(hook._orch_state_dir_for_root(root), "checkpoint-init.marker")
real_outcome = doctor._atomic_write_outcome


def outcome(path):
    if fail and path == marker:
        return False, "an injected failure"
    return real_outcome(path)


doctor._atomic_write_outcome = outcome
ctx, notes = doctor._build_ctx_previewed(hook, reg, root, "stop", {}, None)
real_write = hook._orch_write_json_atomic


def write(path, obj):
    if fail and path == marker:
        return "OSError"
    return real_write(path, obj)


hook._orch_write_json_atomic = write
hctx, _ts, _basis = hook._orch_build_ctx(reg, root, "stop", {})
print(json.dumps({"status": status, "notes": notes,
                  "preview": [list(row) for row in ctx["cannot_evaluate"]],
                  "preview_verdict": hook.decide_yield(ctx)[0],
                  "hook": [list(row) for row in hctx["cannot_evaluate"]],
                  "hook_verdict": hook.decide_yield(hctx)[0]}))
"""


class DoctorMarkerWriteFault(Stage2Harness):
    """A failed init-marker write injects a cannot-evaluate row (aiqt_hooks.py:_orch_checkpoint_union
    `checkpoint-init marker unwritable; a later deletion would go`). Once the checkpoint rewrite in the
    same directory has succeeded, no arrangement of the tree makes that write fail, so the failure is
    injected in one process into the doctor prediction and into the hook writer alike: the preview and
    the hook must carry the same rows and reach the same verdict, with the fault and without it. This
    also pins the stand-in return contract, None on success, which the hook reads as a saved write."""

    def _run(self, case):
        r = subprocess.run([sys.executable, "-I", "-c", FAULT_PROG, str(DOCTOR), str(self.repo), case],
                           capture_output=True, text=True, env=self._env(), timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_a_failed_marker_write_injects_the_row_the_hook_injects(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        for case, verdict in (("fail", "DENY"), ("succeed", "ALLOW")):
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                self.write_registry(self.stage2())
                self.arm_lease()
                self.set_items([])
                self.state_dir().mkdir(parents=True, exist_ok=True)
                out = self._run(case)
                self.assertEqual(out["status"], "ok", out)
                self.assertEqual(out["preview"], out["hook"], out)
                rows = [row for row in out["hook"] if row[0] == "backlog-checkpoint"]
                if case == "fail":
                    self.assertEqual(len(rows), 1, out)
                    self.assertIn("checkpoint-init marker unwritable", rows[0][2])
                    self.assertTrue(any("init-marker write" in n and "would FAIL" in n
                                        for n in out["notes"]), out)
                else:
                    self.assertEqual(rows, [], out)
                self.assertEqual(out["preview_verdict"], verdict, out)
                self.assertEqual(out["hook_verdict"], verdict, out)


# Runs in a separate python3 -I process: load the doctor by path and call its preview path
# (_build_ctx_previewed) in that process, with _atomic_write_outcome wrapped by a spy that records
# whether both stand-ins are installed when the stand-in write runs and, for the unpreviewed and
# interrupt cases, raises the not-previewed exception or KeyboardInterrupt there; then report
# whether the two hook functions are the original objects again.
RESTORE_PROG = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("orch_doctor_under_test", sys.argv[1])
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
hook = doctor._load_hook()
root = hook._recovery_toplevel(sys.argv[2])
case = sys.argv[3]
status, reg = hook._orch_registry(root)
orig_write, orig_event = hook._orch_write_json_atomic, hook._orch_guard_event
real_outcome = doctor._atomic_write_outcome
seen = []


def spy(path):
    seen.append(hook._orch_write_json_atomic is not orig_write
                and hook._orch_guard_event is not orig_event)
    if case == "interrupt":
        raise KeyboardInterrupt
    if case == "unpreviewed":
        raise doctor._Unpreviewed("a write this probe does not model")
    return real_outcome(path)


doctor._atomic_write_outcome = spy
try:
    doctor._build_ctx_previewed(hook, reg, root, "stop", {}, None)
    ended = "returned"
except doctor._Unpreviewed:
    ended = "unpreviewed"
except KeyboardInterrupt:
    ended = "interrupted"
print(json.dumps({"status": status, "ended": ended, "seen": seen,
                  "write_restored": hook._orch_write_json_atomic is orig_write,
                  "event_restored": hook._orch_guard_event is orig_event}))
"""


class DoctorStandInRestore(Stage2Harness):
    """The preview replaces hook._orch_write_json_atomic and
    hook._orch_guard_event for the context build only, and restores both however the build ends: a
    normal return, the not-previewed exception, or a KeyboardInterrupt raised inside the stand-in."""

    def _run(self, case):
        r = subprocess.run([sys.executable, "-I", "-c", RESTORE_PROG, str(DOCTOR), str(self.repo),
                            case], capture_output=True, text=True, env=self._env(), timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_the_stand_ins_are_restored_however_the_preview_ends(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        cases = (("normal", "returned"), ("unpreviewed", "unpreviewed"), ("interrupt", "interrupted"))
        for case, ended in cases:
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                self.write_registry(self.stage2())
                self.arm_lease()
                self.set_items([])
                self.state_dir().mkdir(parents=True, exist_ok=True)
                out = self._run(case)
                self.assertEqual(out["status"], "ok", out)
                self.assertEqual(out["ended"], ended, out)
                self.assertTrue(out["seen"], "the stand-in write was never reached: {}".format(out))
                self.assertTrue(all(out["seen"]), "a stand-in was not installed: {}".format(out))
                self.assertTrue(out["write_restored"], out)
                self.assertTrue(out["event_restored"], out)


# Every write the hook makes inside _orch_build_ctx and the module functions it
# calls, keyed (function, callee, text), text being the stripped source line of the call. "modelled"
# is a write whose failure changes the verdict and whose outcome the doctor predicts
# (_atomic_write_outcome through _build_ctx_previewed); "no verdict effect" is a write whose failure
# leaves the verdict unchanged, with the reason.
WRITE_SITES = {
    ("_orch_checkpoint_union", "_orch_write_json_atomic",
     "unsaved = _orch_write_json_atomic(path, {\"version\": 1, \"ts\": _orch_now().isoformat(),"): (
        "modelled", "the checkpoint rewrite; a failure skips the init-marker write and adds a "
        "recording-failure warning"),
    ("_orch_checkpoint_union", "_orch_write_json_atomic",
     "unsaved = _orch_write_json_atomic(marker, {\"version\": 1, \"ts\": _orch_now().isoformat()})"): (
        "modelled", "the init-marker write; a failure injects a cannot-evaluate row"),
    ("_orch_event_warn", "_orch_guard_event", "if _orch_guard_event(root, kind, decision, detail):"): (
        "no verdict effect", "a guard event of the checkpoint union, reached through _orch_event_warn; "
        "a failure adds only a recording-failure warning"),
}
# The hook helpers that write, each a leaf of the scan (its own body is the write).
WRITE_PRIMITIVES = ("_orch_write_json_atomic", "_orch_write_json", "_orch_append_jsonl",
                    "_orch_save_turn_state", "_orch_guard_event", "_orch_record_denial",
                    "_orch_record_escape_spoof", "_orch_record_forced_exit", "_orch_register_wake")
# os and shutil calls that change the file system, and write methods on any object.
FS_WRITERS = ("replace", "rename", "renames", "remove", "unlink", "makedirs", "mkdir", "rmdir",
              "removedirs", "truncate", "symlink", "link", "chmod", "chown", "utime", "mkfifo",
              "mknod", "rmtree", "copyfile", "copy", "copy2", "copytree", "move")
WRITE_METHODS = ("write", "writelines", "write_text", "write_bytes", "truncate")
WRITE_FLAGS = ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND")


def ctx_write_sites(source, start="_orch_build_ctx"):
    """The set of (function, callee, text) for every write reached from start through the module
    functions it calls, text being the stripped source line of the call: a call of a write primitive
    (not followed further), an open whose mode is not a literal read mode, an os.open with a write
    flag, an os or shutil call in FS_WRITERS, and a call of a write method."""
    tree = ast.parse(source)
    lines = source.splitlines()

    def text(node):
        return lines[node.lineno - 1].strip()
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    sites, seen, work = set(), set(), [start]
    while work:
        name = work.pop()
        if name in seen:
            continue
        seen.add(name)
        for node in ast.walk(funcs[name]):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Name):
                if f.id in WRITE_PRIMITIVES:
                    sites.add((name, f.id, text(node)))
                elif f.id == "open":
                    mode = node.args[1] if len(node.args) > 1 else next(
                        (k.value for k in node.keywords if k.arg == "mode"), None)
                    if not (mode is None or (isinstance(mode, ast.Constant)
                                             and mode.value in ("r", "rb", "rt"))):
                        sites.add((name, "open", text(node)))
                elif f.id in funcs:
                    work.append(f.id)
            elif isinstance(f, ast.Attribute):
                owner = f.value.id if isinstance(f.value, ast.Name) else None
                if owner in ("os", "shutil") and f.attr in FS_WRITERS:
                    sites.add((name, owner + "." + f.attr, text(node)))
                elif owner == "os" and f.attr == "open":
                    flags = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
                    if flags.intersection(WRITE_FLAGS):
                        sites.add((name, "os.open", text(node)))
                elif f.attr in WRITE_METHODS:
                    sites.add((name, "." + f.attr, text(node)))
    return sites


# One added write of each kind the probe must see, as (name, anchor, replacement) over the hook
# source: a write primitive, a raw file-system call and a write method, each in a reader.
LEDGER_ANCHOR = "    schema_bad = 0\n"
PENDING_ANCHOR = "    declared = _orch_path(root, rec.get(\"pending_decisions\"))\n"
WRITE_SITE_MUTATIONS = (
    ("a write primitive in the pending-decisions reader", PENDING_ANCHOR,
     PENDING_ANCHOR + "    _orch_write_json(declared, {})\n"),
    ("a raw os.replace in the ledger reader", LEDGER_ANCHOR,
     LEDGER_ANCHOR + "    os.replace(root, root)\n"),
    ("a write method in the ledger reader", LEDGER_ANCHOR,
     LEDGER_ANCHOR + "    sys.stderr.write(root)\n"),
)


class DoctorWriteSiteProbe(unittest.TestCase):
    """Class probe: the writes the hook makes inside the context build equal the
    reviewed table, and the doctor replaces exactly the primitives the table names."""

    def source(self):
        if not HOOK.exists():
            self.fail("installed hook not found: {}".format(HOOK))
        return HOOK.read_text(encoding="utf-8")

    def test_every_write_in_the_context_build_is_reviewed(self):
        sites = ctx_write_sites(self.source())
        self.assertEqual(sorted(sites), sorted(WRITE_SITES),
                         "the writes the hook makes in the context build and the table differ")
        for key, (status, reason) in WRITE_SITES.items():
            with self.subTest(site=key):
                self.assertIn(status, ("modelled", "no verdict effect"))
                self.assertTrue(reason)

    def test_the_doctor_replaces_exactly_the_reviewed_primitives(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        source = DOCTOR.read_text(encoding="utf-8")
        replaced = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    for leaf in (target.elts if isinstance(target, ast.Tuple) else [target]):
                        if isinstance(leaf, ast.Attribute) and isinstance(leaf.value, ast.Name) \
                                and leaf.value.id == "hook":
                            replaced.add(leaf.attr)
        self.assertEqual(replaced, {callee for _f, callee, _l in WRITE_SITES},
                         "the doctor replaces other hook functions than the reviewed writes")
        for func, _callee, _text in WRITE_SITES:
            self.assertIn("{}:{}".format(HOOK.name, func), source,
                          "the doctor docstring omits a cited hook function")

    def test_the_probe_refuses_each_added_write(self):
        source = self.source()
        for name, anchor, replacement in WRITE_SITE_MUTATIONS:
            with self.subTest(mutation=name):
                self.assertEqual(source.count(anchor), 1, "the mutation anchor is not unique")
                sites = ctx_write_sites(source.replace(anchor, replacement))
                self.assertNotEqual(sorted(sites), sorted(WRITE_SITES),
                                    "the probe missed {}".format(name))


def doctor_precheck_sites(source):
    """The site id of every _site call in the doctor source, in order, and every reference to the
    name _site that is not the callee of a call (so an alias cannot add an unlisted site)."""
    ids, stray = [], []
    tree = ast.parse(source)
    callees = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_site":
            callees.add(id(node.func))
            first = node.args[0] if node.args else None
            ids.append(first.value if isinstance(first, ast.Constant)
                       and isinstance(first.value, str) else None)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_site" and id(node) not in callees:
            stray.append(node.lineno)
    return ids, stray


class DoctorPrecheckSiteProbe(unittest.TestCase):
    """Class probe: the reachability table covers every pre-check site in the doctor, every
    checked path reaches _special_path only through _first_special over _site entries, and every
    site has a reach case and, where it has an early exit, a contrast case."""

    def test_the_table_covers_every_precheck_site_in_the_doctor(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        source = DOCTOR.read_text(encoding="utf-8")
        ids, stray = doctor_precheck_sites(source)
        self.assertNotIn(None, ids, "a _site call without a literal site id")
        self.assertEqual(stray, [], "a reference to _site that is not a call")
        self.assertEqual(sorted(set(ids)), sorted(PRECHECK_SITES),
                         "the doctor pre-check sites and the reachability table differ")
        tree = ast.parse(source)
        callers = set()
        for func in ast.walk(tree):
            if isinstance(func, ast.FunctionDef):
                for node in ast.walk(func):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                            and node.func.id == "_special_path":
                        callers.add(func.name)
        self.assertEqual(callers, {"_first_special"},
                         "_special_path is called outside _first_special, so a path can bypass _site")

    def test_every_site_has_its_cases(self):
        for site, (_command, early_exit, _condition, citation) in PRECHECK_SITES.items():
            with self.subTest(site=site):
                expects = {e for s, e, _c in PRECHECK_CASES if s == site}
                self.assertIn("reach", expects, "no case where the hook reaches the open")
                if early_exit:
                    self.assertIn("skip", expects, "no contrast case for the early exit")
                self.assertTrue(citation, "no hook citation")
        for _site_id, _expect, case in PRECHECK_CASES:
            self.assertTrue(callable(getattr(DoctorPrecheckSites, case, None)), case)
        for _label, case in NONBLOCKING_CASES:
            self.assertTrue(callable(getattr(DoctorPrecheckSites, case, None)), case)


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
    """Class probe: every path the doctor itself opens goes through _read_regular."""

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
