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

The backlog is produced by a minimal FIXTURE enumerator, a -c program that the registry argv carries:
it reads a JSON list of AEI items and prints the AEI v1 envelope (version 1, generated_at_utc from the
clock, a source locator, the items). It deliberately does not depend on the project enumerator
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
scope, or for idle out of the roster, runs no enumerator, as the hook runs none there,
and that the doctor re-executes itself under python3 -I and exits 2 with a message when that
re-execution fails. The doctor reads the resume barrier only as a regular file: a
barrier that is a FIFO with no writer, a directory, or a symlink to /dev/null is reported as
cannot-evaluate, exit 2, within a short timeout and naming the path and the file type, and the audit
is not run, and a class probe scans the doctor source so that every path it opens goes through its
checked helper. Before any hook reader is called, a registry file or a declared read path
(the mode and lease paths, the record paths, the enumerator operands) that exists and is not a regular
file, a FIFO, a directory, or a symlink to a FIFO, is reported as cannot-evaluate, exit 2, within
RUN_TIMEOUT, with no enumerator run and no hook state written. The writes-nothing test
runs a fresh copy of the doctor and the hook, in a tree that never held a __pycache__, and asserts no
bytecode file appears anywhere under it. The fixed hook state files each command opens
with a plain blocking open are checked the same way before the reader that opens them: for preflight
turn-state.json, dispatch-ledger.jsonl, backlog-checkpoint.json and, with attestations declared,
attestations-validated.json and guard-events.jsonl; for the resume audit guard-events.jsonl,
escape-spoof.json and the forced-exit files, and with an unreadable registry
resume-barrier.json.unused. Each refusal says how the hook would open the path: with a blocking
open, without blocking (naming the reader that opens it with O_NONBLOCK), or not at all, for an
enumerator operand; then that the hook reader that opens it was not called and no enumerator ran,
or, at an enumerator operand, only that no enumerator ran. PRECHECK_OPENS gives, for each pre-check
site, the hook function and lines that open its path; a source probe checks each of those opens at
source, and the reach case of each site runs the hook call path with open, os.open and
subprocess.run wrapped and requires that the hook first opens that site's path, or runs the
enumerator that takes it, by one of those opens, and each open of the table must be that first open
in at least 1 reach case of its site. OPEN_ACCOUNTS gives the exact text of each refusal
that is not a blocking open, and a claim for each hook line or range it cites; the probe requires
the doctor's texts to equal those texts, each text to cite exactly the ranges of its claims, and
each claim to hold at source, and DoctorOpenAccountHolders fails when a word of that account appears
in a string or comment of the doctor outside the tables that word it, also where a line break, a
concatenation or an escape splits it; a phrase that the doctor assembles at run time from separate
strings or names is not found. Every process that this file starts goes through 1 launcher,
run_doctor_recorded, apart from the launches of the self-test that are there to be refused: an audit
hook that the module adds and that cannot be removed (_admit) refuses any other start of a process in
the test process's interpreter (subprocess, os.system, os.exec*, os.posix_spawn, os.spawn*, os.fork,
os.forkpty, and native code loaded by ctypes), and refuses the load of each module that can make a
subinterpreter (INTERPRETER_MODULES), whose audit hooks would be its own. It tells the recorder's own
launch by the identity of the code of the frames that raise its events, not by a name or a mark that
a case could set, refuses that code as the code of another function, reads what it checks from its
own defaults, fixed when the module loads, and refuses a change to its own code or defaults. It also
refuses, in the test process, any code object that holds a string constant that starts with a doctor
refusal, in it or in a nested code object, tuple, frozenset or slice constant, or that holds a
constant of a type that the compiler does not make, when it runs by exec, eval or import, when a
function is built from it, and when it is assigned as the code of a function, so the doctor's code
cannot run here by any of those routes under any name. The recorder registers a run's output with its
case when a doctor refusal (REFUSAL_PREFIXES) occurs anywhere in its captured stdout, also when the run
timed out or failed its check; it refuses a run whose stdout is not captured before the run starts,
and fails a run whose output holds a refusal when it has no case or its case is not running. A
cleanup fails a case in which a run printed a pre-check refusal that assert_refusal did not check as a
whole line, the label of the path included (PRECHECK_LABELS in the reach cases), or a refusal of the
resume audit to report the barrier that assert_barrier_refusal did not check as the only line of its
output that starts "barrier: ", whole. A partial check beside those helpers is not refused, but it
cannot replace them. Not seen: doctor output that reaches a case other than through the captured
stdout of the recorder (a file, a socket, stderr, or an encoding that hides every refusal prefix), a
process that native code starts without an audit event, a subinterpreter that native code makes
other than through INTERPRETER_MODULES, code run in this process by a route that raises none of the
events exec, function.__new__ and object.__setattr__, a doctor loaded in this process whose refusal
text is not a string constant of its code, and a case that replaces a built-in, replaces with native
code a function that the recorder's launch calls, rebinds or changes what the registration and the
cleanup read (REFUSAL_PREFIXES, _register_refusal, refusal_outputs and its lists), or gives an object
that is not running the state by which unittest marks a running case (_outcome). A
secondary source probe flags a string literal of this file that holds a part
of such a refusal outside assert_refusal, the arguments that name the path in a call of it, and the
tables that word the refusal: a piece of the literal that lines up with a stretch of the refusal line,
the label included, and touches 2 or more of its words, a stretch of 4 or more of its whole words, or
1 of its opening fragments. Each command checks only what its own
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
of fields and the lines that read them to equal the reviewed EVENT_FIELDS table, each field either
modelled by a named doctor input or unpreviewed with a reason; any other use of the event data (a
computed key, an alias, a pass to an unknown callee) fails it, and it proves that it refuses one
mutation of each kind.
The DoctorCheckpointWrites cases prove that the doctor previews the hook writes inside the context
build whose failure changes the verdict, without making them: with an empty backlog, a live lease
and no init marker, a failed marker write makes the real hook deny the Stop and the scheduling call
(aiqt_hooks.py:23387-23399), and the doctor reports the same DENY (the failure is injected
identically into both, since the hook writer leaves no file arrangement in which the checkpoint
rewrite succeeds and the marker write fails); an entry of any type at a legacy fixed temporary
path (<name>.tmp) is ignored by the hook writer, which creates a randomly named file of its own,
so the hook writes both files and allows and so does the doctor, promptly; a state directory the
hook cannot write fails the checkpoint rewrite, which skips the marker write, and the hook allows
with the recording failure, as does the doctor; a present marker is not rewritten; and a write the
preview does not model is reported as not previewed, exit 2. The DoctorStandInRestore
cases load the doctor in one process and prove that the two hook functions the preview replaces
are the original objects again after a normal return, after the not-previewed exception and after a
KeyboardInterrupt raised inside the stand-in. The DoctorWriteSiteProbe case is
the class probe for that finding: it scans the
hook source from _orch_build_ctx through every module function it calls for every write (a write
primitive, an open for writing, an os or shutil call that changes the file system, a write method),
requires the set of sites to equal the reviewed WRITE_SITES table, each modelled by the doctor or of
no verdict effect with a reason, requires the doctor to replace exactly the primitives the table
names, and proves that it refuses one added write of each kind.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import tokenize
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# A process that ignores SIGCHLD cannot read a child's exit status: the kernel reaps each child as it
# exits, so subprocess gives it the status 0, and each process that it starts keeps the ignored
# disposition across exec. This file reads the exit status of the processes that it starts, and of
# theirs, so it sets SIGCHLD to SIG_DFL before it starts any, whatever disposition it inherited
# (T15EnumeratorTimeout.test_stage1_contrast_when_sigchld_is_ignored).
signal.signal(signal.SIGCHLD, signal.SIG_DFL)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
HOOK = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts" / "aiqt_hooks.py"
DOCTOR = HERE / "orch_doctor.py"
ZERO64 = "0" * 64
# The whole line that a preview out of scope or out of the roster prints for what it wrote and ran
# (tools/orch_doctor.py, _preflight).
NOT_RUN_WRITES = "writes: the doctor itself wrote nothing, and the enumerator was not run"

# The environment variable in which run_doctor_recorded names a file of each launch's own, and the
# statements with which every enumerator that a case declares through Stage2Harness.write_registry
# begins, so that it records each of its starts in that file before anything else runs. The hook
# starts the enumerator with the hook's own environment (`subprocess.run` at aiqt_hooks.py:22833 passes
# no env), and the doctor runs the hook in its own process, so a launch of either passes the file on to
# the enumerator. Of the enumerators that the hook would start, write_registry accepts only one whose
# argv is exactly this interpreter (sys.executable), -I, -c and 1 of ENUM_PROGRAMS, each a separate
# element, followed by any operands, and whose timeout, as the hook reads it, is at most ENUM_TIMEOUT
# (declared_enumerator_defect). Each program of ENUM_PROGRAMS begins with these statements. It writes
# unchecked an enumerator that the hook refuses before it starts anything. The residuals are stated
# above enumerator_bound_defect.
ENUM_RUNS_VAR = "ORCH_STAGE2_ENUMERATOR_RUNS"
ENUM_RUN_MARK = """import os
_runs = os.environ.get("ORCH_STAGE2_ENUMERATOR_RUNS")
if _runs:
    with open(_runs, "a", encoding="utf-8") as _record:
        _record.write("run\\n")
"""


def runs_enum_run_mark_first(program):
    """Whether the first statements of program, read from its syntax tree, are those of ENUM_RUN_MARK,
    and the program compiles, so that the program records its start before any other statement runs.
    A program that holds the mark only as text, or that runs other statements before it, does not;
    neither does one that does not parse, or one that parses but does not compile, such as the mark
    followed by a top-level return, a top-level break or a misplaced future import, since the
    interpreter refuses it before any of its statements runs. program is the source text (str) of a
    -c program, the argv element that the interpreter compiles."""
    try:
        body = ast.parse(program).body
        compile(program, "<enumerator>", "exec", dont_inherit=True)
    except (SyntaxError, ValueError):
        return False
    mark = ast.parse(ENUM_RUN_MARK).body
    return [ast.dump(node) for node in body[:len(mark)]] == [ast.dump(node) for node in mark]


# The fixture enumerator, a -c program (so sys.argv[0] is "-c"): sys.argv[1] is a JSON file holding the
# items list. It records its start (ENUM_RUN_MARK), prints 1 AEI v1 envelope that validate_enumeration
# accepts (aiqt_hooks.py:22754-22812) and exits 0.
ENUM_FIXTURE = ENUM_RUN_MARK + """import json
import sys
from datetime import datetime, timezone

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    items = json.load(fh)
print(json.dumps({"version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                  "source": {"locator": path}, "items": items}))
"""


# The fixture enumerator, also appending 1 line to the file named by sys.argv[2] each time it runs, so
# a test can observe that the declared enumerator ran and that its write is its own.
WRITING_ENUM_FIXTURE = ENUM_FIXTURE.replace(
    "path = sys.argv[1]\n",
    "path = sys.argv[1]\nwith open(sys.argv[2], \"a\", encoding=\"utf-8\") as mark:\n"
    "    mark.write(\"ran\\n\")\n", 1)

# The enumerator of the enumerator timeout case: it records its start, then sleeps past any timeout.
SLEEPING_ENUM_FIXTURE = ENUM_RUN_MARK + "import time\ntime.sleep(100)\n"

# The only programs that write_registry accepts in a declared enumerator that the hook would start,
# compared as exact text. Each begins with the statements of ENUM_RUN_MARK and compiles
# (runs_enum_run_mark_first), and after them names neither the record nor the environment
# (program_leaves_record); EnumeratorBounds checks both of each. They are short, they are read in
# review, and after the mark none of them opens, removes or writes any path but its own operands, so an
# accepted program leaves the count to the mark. In such an enumerator, a program that is not 1 of
# these is refused however it begins, since a check of a program's text cannot see every way in which
# a program can reach the record (EnumeratorBounds.SEARCHES).
ENUM_PROGRAMS = (ENUM_FIXTURE, WRITING_ENUM_FIXTURE, SLEEPING_ENUM_FIXTURE)


def program_leaves_record(program):
    """Whether program, after the statements of ENUM_RUN_MARK, names none of the names that the mark
    binds (_runs, _record), no os.environ, os.getenv or os.putenv, and no string that holds
    ENUM_RUNS_VAR, read from its syntax tree; so it cannot reach the record that the mark appends to
    other than by a path that it builds from no name of the mark and no variable of the environment."""
    body = ast.parse(program).body[len(ast.parse(ENUM_RUN_MARK).body):]
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Name) and node.id in ("_runs", "_record", "environ", "getenv", "putenv"):
            return False
        if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv", "putenv"):
            return False
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and ENUM_RUNS_VAR in node.value:
            return False
    return True


def declared_enumerator_defect(enumerator):
    """The defect of a declared enumerator, as the hook reads it from the registry file (the value that
    json.loads gives for the text written, so a tuple is read as the list that json writes, and a str
    subclass as its text); None when it has none. An argv that the hook would start (a list of non-empty
    strings, aiqt_hooks.py:22826-22829) must be exactly this interpreter (sys.executable), "-I", "-c",
    1 of ENUM_PROGRAMS and then any operands, each element compared on its own; and its timeout, as the
    hook reads it (aiqt_hooks.py:22830-22831), must be at most ENUM_TIMEOUT, so enumerator_bound_defect
    holds a launch to enough. An argv that the hook refuses starts no enumerator and has no defect. This
    is the 1 place that decides the shape: write_registry calls it on every registry that it writes."""
    argv = enumerator.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        return None
    if not (len(argv) > 3 and argv[0] == sys.executable and argv[1] == "-I" and argv[2] == "-c"
            and argv[3] in ENUM_PROGRAMS):
        return "the enumerator {!r} is not this interpreter, -I, -c and 1 of ENUM_PROGRAMS".format(argv)
    timeout = enumerator.get("timeout")
    timeout = timeout if isinstance(timeout, (int, float)) and 0 < timeout <= 600 else 60
    if timeout > ENUM_TIMEOUT:
        return "the enumerator timeout {!r} is over ENUM_TIMEOUT".format(timeout)
    return None

# The enumerator timeout of every fixture registry whose enumerator should end normally. The hook starts
# this clock when it starts the enumerator (`subprocess.run` at aiqt_hooks.py:22833), so it also covers
# the interpreter start-up, which a loaded host can stretch past 5 seconds and turn a normal end into
# ENUMERATOR_ERROR. 60 seconds is the hook's own default (aiqt_hooks.py:22831). The gate caps a
# committed value at 8 seconds (ENUMERATOR_TIMEOUT_MAX); these registries are never gated. The timeout
# test sets its own 1 second timeout for an enumerator that does not end.
ENUM_TIMEOUT = 60

# The bound on a test run that can start the enumerator of a fixture registry once: run_hook, run_doctor
# and the bounded doctor and hook runs (Doctor.SPECIAL_TIMEOUT, DoctorCheckpointWrites.TIMEOUT and
# DoctorStandInRestore.TIMEOUT). It exceeds ENUM_TIMEOUT by ENUM_MARGIN, so the hook's own timeout ends
# an enumerator that hangs, and the case reads what the hook reports, before this bound ends the run.
# A run that can start it twice has twice this bound. run_doctor_recorded holds the timeout of every
# launch to that margin for each enumerator run that the launch recorded (enumerator_bound_defect).
RUN_TIMEOUT = 120
ENUM_MARGIN = 60

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

# The same process shape: the hook resume audit is replaced with a stand-in that leaves the barrier as
# argv[3] says: absent, holding text that is not JSON, or malformed (a ts from the run, and an active
# that is not a boolean).
AUDIT_LEAVES_PROG = """
import importlib.util, json, os, sys
from datetime import datetime, timezone
spec = importlib.util.spec_from_file_location("orch_doctor_under_test", sys.argv[1])
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
hook = doctor._load_hook()
root, leaves = sys.argv[2], sys.argv[3]


def leaving(data):
    path = os.path.join(hook._orch_state_dir_for_root(root), "resume-barrier.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if leaves == "absent":
        if os.path.lexists(path):
            os.unlink(path)
        return
    with open(path, "w", encoding="utf-8") as fh:
        if leaves == "not-json":
            fh.write("not json\\n")
        else:
            json.dump({"active": "yes", "findings": [], "ts": datetime.now(timezone.utc).isoformat(),
                       "warned": False}, fh)


hook.orch_resume_audit = leaving
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
    """Serialize rows as a chained register (`_orch_chained_rows` at aiqt_hooks.py:32867-32895): seq is
    the line number and prev is the sha256 of the prior raw line, 64 zeros for the first."""
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
    return run_doctor_recorded(None, ["git", "-C", str(repo), *args], capture_output=True, text=True,
                               check=True)


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


# Every time limit that applies to a test in this process, checked when it is applied. A limit is
# applied at 1 of 3 sinks: a launch through run_doctor_recorded, whose timeout argument is the limit
# (_admit refuses every other launch in this interpreter, so every process that a test starts takes
# its limit there); the bound of an assertLess or assertLessEqual call, its argument b, by position or
# by keyword, which every such call in this process is taken to be; and the timeout of
# threading.Thread.join. When the module loads, it wraps unittest.TestCase.assertLess and
# assertLessEqual and threading.Thread.join, each with its own parameters, and run_doctor_recorded
# makes 1 call, so that each sink gives _time_limit_applied the limit that it is about to apply,
# whatever way the value was bound. A timeout of None at a launch or a join sets no
# limit and is not checked. The site of a limit is the innermost frame of the call stack that runs the
# code of a function at the top level of this file or of a method defined in the body of a class of
# this file, at any depth, keyed by that class ("" at the top level) and that function, each told by
# the identity of its code; code nested in such a function, such as a lambda, a nested function or a
# method of a class that it defines, has its site, and the sinks and the wrapper of
# unittest.TestCase.run have none, so a limit applied where no other frame runs the code of this file,
# such as by a cleanup that is a sink or by a test of another module, has no site. A site of a
# Stage2Harness test is a site whose class is "", Stage2Harness, a class that derives from it, or a
# class of the file that such a class derives from (TIME_LIMIT_SCOPE). _time_limit_applied refuses,
# raising TimeLimitViolation before the sink runs: a value that is not an int or a float; anywhere in
# the process, a value below TIME_LIMIT_FLOOR, the least value of this table, also where no frame has
# a site, which is checked against that floor only; and, at a site of a Stage2Harness test, a site
# that this table does not list, or a value below the value that it gives the site. It compares by
# "not value >= floor", so it refuses NaN. It records each limit that it is given, and each refusal,
# and unittest.TestCase.run is wrapped so that each test in the process gets a cleanup that fails it
# for each refusal recorded while it ran: also one raised in a thread, which stops only that thread,
# and one that the test caught. A refusal raised after the cleanup of the test that started its thread
# fails the test that is running then. When none is, tearDownModule fails the run for it if it was
# raised before tearDownModule read TIME_LIMIT_REFUSALS; one raised later while no test runs, such as
# in a thread that is still running once tearDownModule has run, is read by nothing, so it fails the
# run only as its own TimeLimitViolation does, which in a thread stops only that thread, and the run's
# result and exit status are then as they would be without it. Once every test of this module, as a
# new unittest.TestLoader finds them, has run in this process (time_limit_full_run), so not in a run
# that a -k option narrows, tearDownModule also fails the run for each entry whose site admitted no
# limit, and for each entry whose value is not the least value admitted at
# its site, so each value below is the least that its site applies in a whole run. Not checked: a limit
# that reaches none of the 3 sinks, such as an elapsed time compared in an if statement or bounded by
# another assertion, such as assertGreater, or the timeout of signal.alarm, select.select, the get of
# a queue or the acquire of a lock; code that bypasses the wrappers, such as code that reloads
# unittest.case, or native code, apart from launches, which _admit polices; a limit on a path that no
# run takes, until a run takes it; and a limit inside a program string of this file, such as the hook
# bound and the cleanup bound of REAPER_PROG, which runs in another process.
TEST_TIME_LIMITS = {
    ("Stage2Harness", "run_hook"): 120,
    ("Stage2Harness", "run_doctor"): 120,
    ("T15EnumeratorTimeout", "run_reaped"): 60,
    ("T15EnumeratorTimeout", "test_stage1_contrast_when_sigchld_is_ignored"): 300,
    ("Doctor", "test_preflight_writes_nothing"): 120,
    ("Doctor", "_doctor_bounded"): 120,
    ("Doctor", "test_reexecutes_isolated_so_a_planted_module_cannot_shadow_the_stdlib"): 60,
    ("Doctor", "test_a_failed_reexecution_exits_2_with_a_message"): 60,
    ("Doctor", "test_usage_error"): 60,
    ("Doctor", "test_help_text_says_the_doctor_writes_nothing_and_the_enumerator_runs"): 60,
    ("Doctor", "test_resume_audit_rewrite_with_a_ts_outside_the_run_is_unverified"): 120,
    ("Doctor", "test_resume_audit_refuses_a_barrier_that_it_cannot_read_back"): 120,
    ("Doctor", "_audit_bounded"): 60,
    ("DoctorPrecheckSites", "_hook_bounded"): 120,
    ("DoctorPrecheckSites", "_assert_hook_reader"): 120,
    ("DoctorScopeMargin", "_assert_refused_near"): 4.5,
    ("DoctorCheckpointWrites", "_doctor"): 120,
    ("DoctorCheckpointWrites", "_faulted"): 240,
    ("DoctorStandInRestore", "_run"): 120,
    ("EnumeratorBounds", "test_a_launch_under_its_bound_fails_its_case"): 119,
    ("EnumeratorBounds", "test_the_pin_holds_in_a_fresh_interpreter"): 120,
}
# The least value of TEST_TIME_LIMITS, which _time_limit_applied requires of every limit in the process.
TIME_LIMIT_FLOOR = min(TEST_TIME_LIMITS.values())
# Filled once every definition of the module is made (_time_limit_sites): {id of a code object: (that
# code object, its site)}, and the classes, by name, whose sites are sites of a Stage2Harness test.
TIME_LIMIT_SITES = {}
TIME_LIMIT_SCOPE = set()
# Each limit given to _time_limit_applied, as (sink, site, value, refusal or None), in the order given;
# the refusals that no cleanup has read yet; and the ids of the tests that have run in this process.
# Each change of the 3 is made with TIME_LIMIT_LOCK held. It is reentrant, so TimeLimitTeardownProbe
# can hold it while it replaces the 3 for a call of tearDownModule, which takes it too.
TIME_LIMIT_CHECKS = []
TIME_LIMIT_REFUSALS = []
TESTS_RUN = set()
TIME_LIMIT_LOCK = threading.RLock()


class TimeLimitViolation(AssertionError):
    """A time limit that _time_limit_applied refuses, as the comment on TEST_TIME_LIMITS states."""


def time_limit_refusal(site, value):
    """Why _time_limit_applied refuses value at site ((class, function), or None where no frame has a
    site), as the comment on TEST_TIME_LIMITS states; None when it admits it."""
    if not isinstance(value, (int, float)):
        return "not an int or a float"
    if not value >= TIME_LIMIT_FLOOR:
        return "below TIME_LIMIT_FLOOR, {:g} s".format(TIME_LIMIT_FLOOR)
    if site is not None and site[0] in TIME_LIMIT_SCOPE:
        if site not in TEST_TIME_LIMITS:
            return "a site of a Stage2Harness test that TEST_TIME_LIMITS does not list"
        if not value >= TEST_TIME_LIMITS[site]:
            return "below {:g} s, the value that TEST_TIME_LIMITS gives its site".format(TEST_TIME_LIMITS[site])
    return None


def _time_limit_applied(sink, value, getframe=sys._getframe):
    """Check value, the time limit that sink ("launch", "assertLess", "assertLessEqual" or "join") is
    about to apply, at the site of the frames of its caller, as the comment on TEST_TIME_LIMITS states:
    record it in TIME_LIMIT_CHECKS, and when time_limit_refusal refuses it, record the refusal in
    TIME_LIMIT_REFUSALS and raise TimeLimitViolation."""
    if value is None and sink in ("launch", "join"):
        return
    frame, site = getframe(2), None
    while frame is not None:
        found = TIME_LIMIT_SITES.get(id(frame.f_code))
        if found is not None and found[0] is frame.f_code:
            site = found[1]
            break
        frame = frame.f_back
    refusal = time_limit_refusal(site, value)
    text = "{} limit {!r} at {}: {}".format(sink, value, "no site" if site is None else
                                            "{}.{}".format(*site) if site[0] else site[1], refusal)
    with TIME_LIMIT_LOCK:
        TIME_LIMIT_CHECKS.append((sink, site, value, refusal))
        if refusal is not None:
            TIME_LIMIT_REFUSALS.append(text)
    if refusal is not None:
        raise TimeLimitViolation(text)


def _checked_sink(sink, method):
    """method, a sink of the standard library, wrapped with its own parameters to give
    _time_limit_applied the limit that it is about to apply: the timeout of threading.Thread.join, or
    the bound b of assertLess or assertLessEqual."""
    if sink == "join":
        def checked(thread, timeout=None):
            _time_limit_applied(sink, timeout)
            return method(thread, timeout)
    else:
        def checked(case, a, b, msg=None):
            _time_limit_applied(sink, b)
            return method(case, a, b, msg)
    checked.__name__, checked.__qualname__, checked.__doc__ = method.__name__, method.__qualname__, method.__doc__
    return checked


def _checked_run(run):
    """unittest.TestCase.run, wrapped to add the test's id to TESTS_RUN and to give the test, before it
    runs, the cleanup that fails it for each time limit refused while it ran."""
    def checked(case, result=None):
        with TIME_LIMIT_LOCK:
            TESTS_RUN.add(case.id())
            start = len(TIME_LIMIT_REFUSALS)
        case.addCleanup(_fail_refused_time_limits, case, start)
        return run(case, result)
    checked.__name__, checked.__qualname__, checked.__doc__ = run.__name__, run.__qualname__, run.__doc__
    return checked


def _fail_refused_time_limits(case, start):
    with TIME_LIMIT_LOCK:
        refused = TIME_LIMIT_REFUSALS[start:]
        del TIME_LIMIT_REFUSALS[start:]
    if refused:
        case.fail("{} time limit(s) refused while this test ran: {!r}".format(len(refused), refused))


unittest.TestCase.assertLess = _checked_sink("assertLess", unittest.TestCase.assertLess)
unittest.TestCase.assertLessEqual = _checked_sink("assertLessEqual", unittest.TestCase.assertLessEqual)
threading.Thread.join = _checked_sink("join", threading.Thread.join)
unittest.TestCase.run = _checked_run(unittest.TestCase.run)


def _time_limit_sites(namespace, sinks):
    """({id of a code object: (that code object, its site)}, the names of the classes of the sites of
    Stage2Harness tests, "" included) for this module's namespace, as the comment on TEST_TIME_LIMITS
    states: each function at its top level, and each method defined in the body of a class of it at any
    depth, told by its __qualname__, with each code object nested in it; the code of each function of
    sinks, the sinks and the wrapper of unittest.TestCase.run, and the code nested in it, has no site."""
    module = namespace["__name__"]
    classes, pending = [], [value for value in namespace.values() if isinstance(value, type)]
    while pending:
        cls = pending.pop()
        if cls.__module__ == module and not any(cls is seen for seen in classes):
            classes.append(cls)
            pending += [value for value in vars(cls).values() if isinstance(value, type)]
    harness = namespace["Stage2Harness"]
    scope = {""} | {base.__name__ for cls in classes if issubclass(cls, harness)
                    for base in cls.__mro__ if any(base is seen for seen in classes)}
    unsited, codes = set(), [sink.__code__ for sink in sinks]
    while codes:
        code = codes.pop()
        unsited.add(id(code))
        codes += [const for const in code.co_consts if isinstance(const, types.CodeType)]
    sites = {}
    for owner, members in [(None, namespace)] + [(cls, vars(cls)) for cls in classes]:
        for value in list(members.values()):
            function = getattr(value, "__func__", value)
            if not isinstance(function, types.FunctionType) or function.__module__ != module:
                continue
            if function.__qualname__ != ("" if owner is None else owner.__qualname__ + ".") + function.__name__:
                continue
            site = ("" if owner is None else owner.__name__, function.__name__)
            codes = [function.__code__]
            while codes:
                code = codes.pop()
                if id(code) not in unsited and id(code) not in sites:
                    sites[id(code)] = (code, site)
                codes += [const for const in code.co_consts if isinstance(const, types.CodeType)]
    return sites, scope


def time_limit_table_mismatches(checks, table):
    """What differs between table, in the form of TEST_TIME_LIMITS, and checks, in the form of
    TIME_LIMIT_CHECKS: each entry whose site admitted no limit, and each entry whose value is not the
    least limit admitted at its site; [] when nothing does."""
    least = {}
    for _sink, site, value, refusal in checks:
        if refusal is None and site in table:
            least[site] = min(least.get(site, value), value)
    out = []
    for site, value in sorted(table.items()):
        if site not in least:
            out.append("{!r}: its site admitted no limit in this run".format(site))
        elif least[site] != value:
            out.append("{!r}: TEST_TIME_LIMITS gives {:g}, the least limit admitted at its site is {:g}".format(
                site, value, least[site]))
    return out


def time_limit_full_run(module, run):
    """Whether run, a set of test ids, holds every test of module as a new unittest.TestLoader finds
    them, whatever name patterns unittest.defaultTestLoader has: a -k option of unittest.main gives it
    its patterns, so in a run that -k narrows it finds only the tests that the run selects."""
    pending, ids = [unittest.TestLoader().loadTestsFromModule(module)], set()
    while pending:
        for test in pending.pop():
            if isinstance(test, unittest.TestSuite):
                pending.append(test)
            else:
                ids.add(test.id())
    return ids <= run


def tearDownModule():
    """Fail the run for each time limit refusal that no cleanup read, of those recorded before it reads
    TIME_LIMIT_REFUSALS (one recorded later is read by nothing, as the comment on TEST_TIME_LIMITS
    states) and, once every test of this module has run in this process (time_limit_full_run), so not
    in a run that a -k option narrows, for each entry of TEST_TIME_LIMITS that
    time_limit_table_mismatches reports."""
    with TIME_LIMIT_LOCK:
        problems = ["refused outside a test: {}".format(text) for text in TIME_LIMIT_REFUSALS]
        del TIME_LIMIT_REFUSALS[:]
    if time_limit_full_run(sys.modules[__name__], TESTS_RUN):
        problems += time_limit_table_mismatches(TIME_LIMIT_CHECKS, TEST_TIME_LIMITS)
    if problems:
        raise AssertionError("time limits: {}".format(problems))


# Timeouts of the hook. A test of a Stage2Harness class that runs the hook, through run_hook or a
# program of this file that loads the hook and calls its functions, or that runs the doctor, which
# loads the hook too, runs the unchanged hook with its own timeouts, as the platform runs it; this
# file does not shorten or remove them there. Such a test fails a correct hook when one of them fires
# and that changes what the test checks, and passes when the test requires only what the hook also
# does after that timeout, as T04NotBefore.test_future_blocks requires only exit 0, which the hook
# also gives when the git call of _recovery_toplevel times out. The timeouts are:
# - the 5 s timeout of the git call in _recovery_toplevel (aiqt_hooks.py:10540), which each orch_
#   action that a test runs, and the doctor, make to find the repo root; on a timeout they get no
#   root, which the hook takes as out of scope;
# - the timeout of any other git call of the hook, such as the 5 s one in _orch_resume_probes
#   (32780) and the 10 s ones in _orch_merge_pending_findings (32853) and _orch_register_authority
#   (32938, 32947 and 32952), which the resume audit can reach;
# - the timeout that the registry declares for the enumerator, which the hook passes at
#   aiqt_hooks.py:22833, ENUM_TIMEOUT, 60 s, in stage2() (also 60 s, the hook's fallback at
#   aiqt_hooks.py:22831, where a T14PosturePins case declares "fast"), on which the hook reports
#   ENUMERATOR_ERROR;
# - for a PreToolUse action run through run_hook (orch_yield_tool and orch_ask_guard here), the 8 s
#   deadline (PRETOOL_BUDGET_SECONDS, HOOK_TIMEOUT_SECONDS 10 less 2.0, aiqt_hooks.py:347-348) in
#   which main() runs it and past which it fails closed, exit 2.
# Reason: these tests check what the installed hook does when it runs as the platform runs it, and a
# recorder that dropped the timeouts would no longer run it so.
# Limits of the tests. Such a test also sets time limits of its own, which TEST_TIME_LIMITS lists by
# the site that applies each, with the least value that the site applies, and against which
# _time_limit_applied checks each limit when it is applied. The least of them is 4.5 s, at
# DoctorScopeMargin._assert_refused_near. That site puts NEAR on the time from just before it sets the
# lease mtime NEAR seconds from a freshness bound of the hook to the return of the doctor call, as a
# later check could see the lease on the other side of that bound. The others are 120 s, RUN_TIMEOUT,
# on 1 doctor or hook program call that can run the stage-2 enumerator (Doctor.SPECIAL_TIMEOUT, which
# DoctorPrecheckSites and DoctorScopeMargin take too, DoctorCheckpointWrites.TIMEOUT and
# DoctorStandInRestore.TIMEOUT), 240 s on the fault-injection call of DoctorCheckpointWrites, which
# can run it twice, 60 s or 120 s on 1 other call, 119 s, 120 s, 179 s and 180 s on the launches of
# EnumeratorBounds.test_a_launch_under_its_bound_fails_its_case, each 1 s under or at the bound that
# enumerator_bound_defect requires, and 60 s or 240 s on a wrapper call of
# T15EnumeratorTimeout, whose REAPER_PROG also bounds the hook at 120 s, or 10 s for the stand-in
# hook, and its own cleanup at 30 s, and 300 s on its nested run of test_stage1_contrast.
# DoctorCheckpointWrites.PROMPT, 15, is read by no check.
# Bound, derived from the 2 lists: the least hook timeout above is 5 s and the least test limit is
# 4.5 s. So such a test can fail a correct hook on a host slow enough that the doctor call of a
# DoctorScopeMargin case, with the os.utime before it, takes 4.5 s, while its git call in
# _recovery_toplevel is still inside its 5 s timeout; otherwise only when 1 git call takes 5 s, or
# 10 s for a 10 s call, a declared enumerator takes its declared timeout, a PreToolUse action takes
# 8 s, or 1 call reaches its limit, which is at least the value that TEST_TIME_LIMITS gives its site.
# The bound counts these timeouts and limits only. A fixture time that a slow host could carry across a
# bound of the hook is not counted: DoctorScopeMargin sets its lease 4.5 s from a bound by design,
# which NEAR covers, and whether any other fixture time is within reach of a slow host is not
# established. Whether a timeout that fires can also let such a test pass a wrong hook is not
# established. A process that the hook leaves running after a run_hook call is neither detected nor
# stopped. The 2 wrapper tests of T15EnumeratorTimeout do not run the hook, and its other 4 tests run
# it through RECORDING_HOOK_PROG under REAPER_PROG, so in them no timeout of the hook can fire but the
# enumerator's in the enforcement test, and the wrapper kills what the hook leaves running, within
# the limits that REAPER_PROG and run_reaped state; a fifth runs test_stage1_contrast in a nested
# process of this file that starts with SIGCHLD ignored.
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
        run_doctor_recorded(self, ["git", "init", "-b", "main", str(self.repo)],
                            capture_output=True, text=True, check=True)
        _git(self.repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-m", "init")
        # A repo-relative file that a register pointer can resolve to
        # (`_orch_pointer_resolves` at aiqt_hooks.py:33009-33032).
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "evidence.md").write_text("evidence\n", encoding="utf-8")
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
            "enumerator": {"argv": [sys.executable, "-I", "-c", ENUM_FIXTURE, str(self.backlog)],
                           "timeout": ENUM_TIMEOUT},
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
        """Write obj as the registry, after failing the case when its enumerator, read back from the
        text to be written as the hook reads it, has a defect (declared_enumerator_defect). Of the
        enumerators that the hook would start, it accepts only one whose argv is exactly this
        interpreter (sys.executable), -I, -c and 1 of ENUM_PROGRAMS, each a separate element, followed
        by any operands, and whose timeout, as the hook reads it, is at most ENUM_TIMEOUT. The program
        is the argv element itself, so the check reads the text that the interpreter compiles; no file
        is read. Every program file in an enumerator that the hook would start is refused, since what
        the interpreter runs for a file operand depends on the operand's name and content, on how the
        path resolves, and on the file at each run, not only on the text that a check reads. An
        enumerator that the hook refuses before it starts anything (one that is not an object, or whose
        argv is not a list of non-empty strings) is written unchecked."""
        text = json.dumps(obj)
        written = json.loads(text)
        enumerator = written.get("enumerator") if isinstance(written, dict) else None
        if isinstance(enumerator, dict):
            defect = declared_enumerator_defect(enumerator)
            if defect is not None:
                self.fail(defect)
        aiqt = self.repo / ".aiqt"
        aiqt.mkdir(exist_ok=True)
        (aiqt / "orchestration.json").write_text(text, encoding="utf-8")

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
        return run_doctor_recorded(self, [sys.executable, "-I", str(HOOK), action],
                                   input=json.dumps(payload), capture_output=True, text=True,
                                   env=self._env(), timeout=RUN_TIMEOUT)

    def run_doctor(self, *args):
        return run_doctor_recorded(self, [sys.executable, "-I", str(DOCTOR), *args, "--root", str(self.repo)],
                                   capture_output=True, text=True, env=self._env(), timeout=RUN_TIMEOUT)

    def stop(self, **payload):
        return self.run_hook("orch_stop_guard", payload)

    def schedule(self, tool_input=None, tool="ScheduleWakeup"):
        return self.run_hook("orch_yield_tool", {
            "tool_name": tool,
            "tool_input": tool_input if tool_input is not None
            else {"prompt": "recheck the work queue", "delaySeconds": 60},
        })

    def human_prompt(self):
        """A genuine human prompt zeroes the stop and schedule denial counters (aiqt_hooks.py:32530-32539)."""
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
        # Stage-1 T1:650-658 posture (`NO_ENUMERATOR` aiqt_hooks.py:22820-22825, `enum_status` 23095-23100).
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("NO_ENUMERATOR", r.stderr)


# =====================================================================================================
# T1. Stop with one open granted unblocked item denies, naming the id (aiqt_hooks.py:23179-23210)
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
# T2. Nothing actionable: Stop allows (`classify_backlog` :22977-22981, `decide_yield` :23167-23168)
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
# T3. `human-decision` (aiqt_hooks.py:22999-23011) blockers against the pending-decisions record
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
        # A free-text mention is not a row-id position
        # (`re.search` at aiqt_hooks.py:23006-23011).
        r = self._run("PD-7", "| PD-8 | Another decision |\nWe discussed PD-7 in passing.\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ref PD-7 is not at a pending-decision row-id position", r.stderr)

    def test_lowercase_ref_is_not_a_decision_id(self):
        r = self._run("pd-7", "| pd-7 | lowercase row |\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("is not a decision id", r.stderr)

    def test_unreadable_pending_surface_holds(self):
        # An unreadable declared surface is cannot-evaluate (`pending_haystack` at
        # aiqt_hooks.py:23000-23002), which denies the Stop (`cannot_evaluate` at
        # aiqt_hooks.py:23154-23166).
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
# T4. `not-before` (aiqt_hooks.py:23031-23037) blockers
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
# T5. Anti-shrinkage checkpoint `_orch_checkpoint_union` (aiqt_hooks.py:23289-23409)
# =====================================================================================================
class T05Checkpoint(Stage2Harness):
    def test_vanished_id_is_held_until_closed(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        # Window 1: item 9 open and actionable; the checkpoint and its init marker are written
        # (aiqt_hooks.py:23376-23392).
        self.set_items([item("9")])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.state_json("backlog-checkpoint.json")["ids"], {"9": "eligible"})
        self.assertIsNotNone(self.read_json("checkpoint-init.marker"))
        # Window 2: item 9 deleted with no closed receipt is held as vanished
        # (`vanished from the enumeration` at aiqt_hooks.py:23352-23354).
        self.human_prompt()
        self.set_items([])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("cannot-evaluate", r.stderr)
        self.assertEqual(self.state_json("backlog-checkpoint.json")["ids"], {"9": "eligible"},
                         "the union keeps a vanished id (aiqt_hooks.py:23360-23361)")
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
        self.assertEqual(r.returncode, 2, r.stderr)  # aiqt_hooks.py:23335-23339
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
# T6. attestations (OPTIONAL KEY, open point P5)
# T6: `_orch_attestation_refs` and `cannot-evaluate` (aiqt_hooks:22911-22959, 23016-23025, 33079-33115)
# =====================================================================================================
class T06Attestations(Stage2Harness):
    def _register(self, rows, anchor=True):
        path = Path(self._p("attestations.jsonl"))
        lines = chain_lines(rows)
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        if anchor:
            # An untracked register is verified against its anchor, an object whose seq is the
            # number of rows (an int of at least 1) and whose digest is the sha256 of the last row
            # (`_orch_register_tip` aiqt_hooks.py:32898-32904 and `a.get("seq")` at :32995-33005).
            # An empty register has no anchor of that shape, so it keeps the zero form, which the
            # hook holds (see the empty-register case).
            tip = ({"seq": len(lines), "digest": hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()}
                   if lines else {"seq": 0, "digest": ZERO64})
            Path(str(path) + ".anchor").write_text(json.dumps(tip), encoding="utf-8")
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

    def test_empty_register_zero_anchor_holds(self):
        # A seq of 0 is not a valid anchor (the seq must be an int of at least 1,
        # `isinstance(n, int)` at aiqt_hooks.py:32997-33001), so the surface is held
        # fail-closed: the snapshot reads unreadable with no refs, never ok.
        self._arm([])
        snap = self.state_json("attestations-validated.json")
        self.assertEqual((snap["status"], snap["seq"], snap["digest"], snap["refs"]),
                         ("unreadable", None, None, []))

    def test_one_anchored_row_audits_ok(self):
        # Contrast: a 1-row register whose anchor names that row validates.
        rows = [self._row()]
        self._arm(rows)
        snap = self.state_json("attestations-validated.json")
        last = chain_lines(rows)[-1]
        self.assertEqual((snap["status"], snap["seq"], snap["digest"]),
                         ("ok", 1, hashlib.sha256(last.encode("utf-8")).hexdigest()))

    def test_approved_row_blocks(self):
        self._arm([self._row()])
        self.assertEqual(self.state_json("attestations-validated.json")["refs"], ["vendor-x"])
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_without_row_is_actionable(self):
        # A validated register whose only row covers another ref: the item's ref is uncovered
        # (`is covered by no fresh validated` at aiqt_hooks.py:23024-23025).
        self._arm([dict(self._row(), ref="vendor-y")])
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("is covered by no fresh validated attestation", r.stderr)

    def test_without_anchor_holds(self):
        self._arm([self._row()])
        os.remove(self._p("attestations.jsonl.anchor"))
        r = self.stop()
        # No anchor: the register authority holds (`no readable anchor authority` at
        # aiqt_hooks.py:32970-32973), so the item is `cannot-evaluate` at 23016-23021.
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("cannot-evaluate", r.stderr)

    def test_undeclared_contrast_free_text_evidence_blocks(self):
        # Without the key, fresh free-text evidence blocks (`blocker.get("evidence")` at
        # aiqt_hooks.py:23026-23027) and no snapshot is written, so
        # test_without_row_is_actionable is red without the key.
        self._arm([], declare=False)
        self.assertIsNone(self.read_json("attestations-validated.json"))
        r = self.stop()
        self.assertEqual(r.returncode, 0, r.stderr)


# =====================================================================================================
# T7. staleness horizons `task_hours` and `ext_hours` (aiqt_hooks.py:22881, 23013-23015, 23242-23249)
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
        # Without the key both horizons are 24 h (`task_hours` and `external_hours` at
        # aiqt_hooks.py:23248-23249), so the two allows above flip.
        self.assertEqual(self._tracked(None, drop=("staleness",)).returncode, 2)
        self.assertEqual(self._external(None, drop=("staleness",)).returncode, 2)

    def test_stage1_contrast(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        self.set_items([item("8", blocker={"kind": "tracked-task", "ref": "task-1"})])
        self.assert_no_enumerator_deny(self.stop())


# =====================================================================================================
# T8. orch_yield_tool over the scheduling tools (aiqt_hooks.py:23666-23780)
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
        # The scheduling deny (`_deny` at aiqt_hooks.py:23724-23747).
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
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
        # tool_input stop true is judged as kind "stop" (aiqt_hooks.py:23692): with the stop counter at the
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
        # The cap (`_ORCH_SCHEDULE_CAP` at aiqt_hooks.py:23174-23178) and the
        # forced-exit record (`_orch_record_forced_exit` at aiqt_hooks.py:23752-23765).
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
# T9. orch_ask_guard against the declared mode record (aiqt_hooks.py:23783-23855)
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

    def test_json_mode_record_reads_as_unattended(self):
        # The host operating-mode file is one JSON line. The vendored reader accepts a structured
        # operating-mode record whose mode key names the mode (`_orch_mode_object_ok` admits its keys
        # at aiqt_hooks.py:22403-22404, and `_orch_mode_detail` classifies its mode at 22557-22559),
        # so a JSON record that says unattended denies the question and records it as pending, as the
        # text line does (`AskUserQuestion BLOCKED` at aiqt_hooks.py:23840-23846).
        self.write_registry(self.stage2())
        Path(self._p("operating-mode.md")).write_text(
            '{"mode": "unattended", "phase": "dispatch", "set_by": "orch-operator", '
            '"set_at": "2026-11-07T00:00:00Z"}\n', encoding="utf-8")
        r = self._ask()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.verdict_json(r)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("unattended", out["hookSpecificOutput"]["permissionDecisionReason"])
        rows = self.read_jsonl("pending-asks.jsonl")
        self.assertEqual([row["key"] for row in rows], ["s1::tu1"])

    def test_json_mode_record_reads_as_attended(self):
        # The contrast of the case above. A reader that refused the structured record (its phase, set_by
        # and set_at keys, `_ORCH_MODE_RECORD_KEYS` at aiqt_hooks.py:22403) would fail it closed to
        # unattended, and the case above would still pass; the same record that says attended-autonomous
        # is read as attended only when the record is read, so the question is allowed with no pending row.
        self.write_registry(self.stage2())
        Path(self._p("operating-mode.md")).write_text(
            '{"mode": "attended-autonomous", "phase": "dispatch", "set_by": "orch-operator", '
            '"set_at": "2026-11-07T00:00:00Z"}\n', encoding="utf-8")
        r = self._ask()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIsNone(self.read_jsonl("pending-asks.jsonl"))

    def test_json_mode_record_with_another_key_fails_closed(self):
        # The same attended-autonomous record with 1 key outside `_ORCH_MODE_RECORD_KEYS` (aiqt_hooks.py:
        # 22403) is not an accepted mode object, so the reader fails it closed to unattended: deny, and the
        # question is recorded as pending. A reader that took any keys would allow it.
        self.write_registry(self.stage2())
        Path(self._p("operating-mode.md")).write_text(
            '{"mode": "attended-autonomous", "phase": "dispatch", "set_by": "orch-operator", '
            '"set_at": "2026-11-07T00:00:00Z", "note": "x"}\n', encoding="utf-8")
        r = self._ask()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.verdict_json(r)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        rows = self.read_jsonl("pending-asks.jsonl")
        self.assertEqual([row["key"] for row in rows], ["s1::tu1"])


# =====================================================================================================
# T10. Scope by mode record when the lease is stale (`_orch_scope_live` aiqt_hooks.py:22596-22656)
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
# T11. escape: `_orch_escape_active` and `escape-spoof` (aiqt_hooks.py:22680-22740, 23500-23519)
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
                # An empty or non-string path is refused (`isinstance(declared, str)` at
                # aiqt_hooks.py:22700-22701).
                self.assertFalse(spoof.exists(), "no release and no spoof record")

    def test_undeclared_contrast_consults_the_default_name(self):
        self._arm(self.stage2(drop=("escape",)))
        self.self_owned_sentinel("ESCAPE-ALLOW-YIELD")
        self.assertEqual(self.stop().returncode, 2)
        self.assertIsNotNone(self.read_json("escape-spoof.json"))

    def test_absolute_path_outside_the_anchor_is_rejected(self):
        self._arm(self.stage2(escape={"path": self._p("elsewhere", "SENTINEL")}))
        self.assertEqual(self.stop().returncode, 2)
        spoof = self.state_json("escape-spoof.json")
        self.assertIn("outside the operator-trusted anchor", spoof["detail"])  # aiqt_hooks.py:22709-22710


# =====================================================================================================
# T12. mistakes_register (OPTIONAL KEY, open point P6; aiqt_hooks.py:33132-33148)
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
# T13. TeammateIdle mirrors the Stop decision (aiqt_hooks.py:23635-23638)
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
        self.assertEqual(r.returncode, 2, r.stderr)  # `spec.get("argv")` at aiqt_hooks.py:22826-22829
        self.assertIn("ENUMERATOR_ERROR", r.stderr)
        self.assertIn("not a list of non-empty strings", r.stderr)

    def test_enumerator_timeout_malformed_still_runs(self):
        # The hook reads a timeout that is not an int or a float (a bool counts as an int, so a JSON true
        # is kept, as a 1 second timeout), is not over 0 or is over 600 as 60
        # (`isinstance(timeout, (int, float)) and 0 < timeout <= 600 else 60` at aiqt_hooks.py:22831),
        # so the timeout "fast" silently becomes 60 and the enumerator still runs.
        self.write_registry(self.stage2(enumerator={
            "argv": [sys.executable, "-I", "-c", ENUM_FIXTURE, str(self.backlog)], "timeout": "fast"}))
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
        # A non-list roster is out of scope (`isinstance(declared, list)` at aiqt_hooks.py:23689-23690).
        self.assertEqual(r.stdout.strip(), "", "a non-list roster is out of scope")

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
# T15. Enumerator timeout yields ENUMERATOR_ERROR; the hook exits within 120 s (aiqt_hooks.py:22831-22836)
# =====================================================================================================
# The sleeping enumerator of these tests is SLEEPING_ENUM_FIXTURE, 1 of ENUM_PROGRAMS, since
# write_registry accepts no other program in a declared enumerator that the hook would start
# (declared_enumerator_defect): 1 process that records its start (ENUM_RUN_MARK) and then sleeps 100 s,
# far past the 1 s timeout that the enforcement test declares and below the 120 s hook bound. It does
# nothing else, so a test that uses it asks it to do nothing but record its start before the declared
# timeout fires. A hook that waits the sleep out sees it end by itself after 100 s, and the call check
# of the enforcement test refuses that call, as its outcome is not TimeoutExpired, if the hook still
# exits within the 120 s hook bound; if the hook does not, the "exited" check of that test, which
# comes first, refuses the hook.

# Runs in a separate python3 -I process: argv[1] is the report file, argv[2] the hook bound and argv[3]
# the cleanup bound, both in seconds, and argv[4:] the command that runs the hook. It makes itself the
# child subreaper (Linux prctl PR_SET_CHILD_SUBREAPER), so every process that the hook starts stays
# its descendant: a process whose parent exits becomes its child, and the kernel makes that move
# before it reports the parent's exit, so the reading below does not depend on timing. It runs the
# command in a new session with this process's stdin and waits up to the hook bound for it to exit,
# and kills it with SIGKILL if it has not. It then notes whether a process that the hook started is
# still alive. To clean up, it reads its own children from /proc/self/task/*/children, sends each
# SIGKILL, reaps each that has ended, and repeats until it has no child left: once a process ends,
# its children become children of this process and are killed in the next pass. It signals only its
# own children, and a child keeps its process id until it is reaped, so no signal can reach an
# unrelated process. The cleanup bound counts from the reap just after the hook has ended, and each
# pass checks it before it sends any signal, so cleanup stops with a child still alive if the bound
# passes first: when a process outlasts SIGKILL that long, such as one in uninterruptible sleep, or
# when the wrapper itself does not run for that long, such as when it is stopped or kept off the CPU,
# in which case it can stop before it has signalled any child. It then lists its children that are
# still alive in the report and leaves them, and their descendants, running. It writes the report as
# JSON: "exited" (the hook exited within its bound), "left_running" (a process that the hook started
# was alive once the hook had ended) and "not_reaped" (the process ids of its children still alive
# when cleanup stopped), and then passes on the hook's stdout, stderr and exit status. A process that
# the hook gets some other program to start, such as a service manager, is not its descendant, and
# the wrapper does not reach it.
REAPER_PROG = """
import ctypes, glob, json, os, signal, subprocess, sys, tempfile, time

report, hook_bound, cleanup_bound = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:
    sys.exit("prctl PR_SET_CHILD_SUBREAPER failed, errno {}".format(ctypes.get_errno()))
if not os.path.exists("/proc/self/task/{}/children".format(os.getpid())):
    sys.exit("/proc/self/task/{}/children is missing".format(os.getpid()))


def children():
    pids = set()
    for path in glob.glob("/proc/self/task/*/children"):
        with open(path, encoding="ascii") as fh:
            pids.update(int(pid) for pid in fh.read().split())
    return sorted(pids)


def reap():
    # Reaps every child that has ended; returns False once no child is left.
    while True:
        try:
            pid = os.waitpid(-1, os.WNOHANG)[0]
        except ChildProcessError:
            return False
        if pid == 0:
            return True


with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
    proc = subprocess.Popen(sys.argv[4:], stdout=out, stderr=err, start_new_session=True)
    try:
        proc.wait(timeout=hook_bound)
        exited = True
    except subprocess.TimeoutExpired:
        exited = False
        proc.kill()
        proc.wait()
    left = alive = reap()
    deadline = time.monotonic() + cleanup_bound
    while alive and time.monotonic() < deadline:
        for pid in children():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.01)
        alive = reap()
    with open(report, "w", encoding="utf-8") as fh:
        json.dump({"exited": exited, "left_running": left,
                   "not_reaped": children() if alive else []}, fh)
    out.seek(0)
    err.seek(0)
    sys.stdout.buffer.write(out.read())
    sys.stderr.buffer.write(err.read())
sys.exit(proc.returncode)
"""

# A stand-in hook for the wrapper's own tests: argv[1] is a lock file, argv[2] a ready file and argv[3]
# "exit" or "hang". It takes a shared flock on the lock file and starts a child that calls setsid,
# so the child is in another session and process group, and that child starts a grandchild; the
# child and the grandchild inherit the lock and sleep 90 s. Once the grandchild has started, the
# stand-in writes "ready" to the ready file, and then it exits at once ("exit") or sleeps 90 s
# ("hang"). The lock stays taken while any of the 3 processes is alive, so a test that can take it
# exclusively knows that none is.
STANDIN_HOOK = """
import fcntl, os, sys, time

lock, ready, mode = sys.argv[1:4]
fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_SH)
r, w = os.pipe()
if os.fork() == 0:
    os.setsid()
    if os.fork() == 0:
        os.write(w, b"x")
    time.sleep(90)
    os._exit(0)
os.close(w)
os.read(r, 1)
with open(ready, "w", encoding="utf-8") as fh:
    fh.write("ready\\n")
if mode == "hang":
    time.sleep(90)
"""

# Runs in a separate python3 -I process: argv[1] is the hook file, argv[2] the record file, argv[3]
# the hook action, argv[4] the mode, "strip" or "keep", and with "keep" argv[5] the enumerator argv
# as JSON. It replaces subprocess.run with a recorder that appends a JSON line for each call: the
# argv, and the timeout argument or "absent" when none is passed. With "strip", and with "keep" for
# each call whose argv is not the enumerator argv, it writes the line and then makes the real call
# with the same arguments except the timeout, so a slow host cannot cut the call short. With "keep",
# for each call whose argv is the enumerator argv, it makes the real call with the same arguments,
# timeout included, and writes the line once the call has ended, adding "outcome": "returned", or
# the type name of the exception that the call raised, such as "TimeoutExpired", which it then raises
# again unchanged. So in neither mode can a timeout of the hook other than the enumerator's fire. In
# the enforcement test the hook's only other call is git rev-parse --show-toplevel in
# _recovery_toplevel, with a 5 s timeout; if that timeout fired, as it can on a loaded host,
# _orch_stop_family would allow the stop without running the enumerator, and the test would fail.
# test_stage1_contrast runs the hook in "strip" mode, and there the same git call is the hook's only
# call; if its timeout fired, the hook would allow the stop without its NO_ENUMERATOR deny. In both
# modes it also adds an audit hook that appends a JSON line to the file named by argv[2] with
# ".starts" added for each audit event that starts a process (START_EVENTS, the events of
# LAUNCH_EVENTS but ctypes.dlopen, which loads native code and starts no process itself): the event
# name, and for subprocess.Popen the argv. A call of subprocess.run raises 1 subprocess.Popen event
# and then 1 os.posix_spawn or _posixsubprocess.fork_exec event, so a process that the hook starts
# other than through subprocess.run, by subprocess.Popen, os.system, os.exec*, os.posix_spawn,
# os.spawn* or os.fork, adds a line that no call of the run record matches. A process that native
# code starts without an audit event adds none. It runs the unchanged hook file as __main__, so the
# hook reads its stdin payload and exits as it does when the platform runs it.
RECORDING_HOOK_PROG = """
import json, runpy, subprocess, sys

hook, record, action, mode = sys.argv[1:5]
enumerator = json.loads(sys.argv[5]) if mode == "keep" else None
real_run = subprocess.run
START_EVENTS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
                "_posixsubprocess.fork_exec")


def write(row, path=record):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=repr) + "\\n")


def record_start(event, args):
    if event.startswith(START_EVENTS):
        write({"event": event, "argv": args[1] if event == "subprocess.Popen" else None},
              record + ".starts")


def recording_run(*args, **kwargs):
    row = {"argv": args[0] if args else kwargs.get("args"), "timeout": kwargs.get("timeout", "absent")}
    if mode == "strip" or json.loads(json.dumps(row["argv"], default=repr)) != enumerator:
        kwargs.pop("timeout", None)
        write(row)
        return real_run(*args, **kwargs)
    try:
        result = real_run(*args, **kwargs)
    except BaseException as exc:
        row["outcome"] = type(exc).__name__
        raise
    else:
        row["outcome"] = "returned"
        return result
    finally:
        write(row)


subprocess.run = recording_run
sys.addaudithook(record_start)
sys.argv = [hook, action]
runpy.run_path(hook, run_name="__main__")
"""

# RECORDING_HOOK_PROG with a start that makes the first call of os.fork in the hook's process do what
# CPython's os.fork does when fork() fails: raise the os.fork audit event, then BlockingIOError
# (EAGAIN). Every later call forks. So main()'s first child-status probe refuses with "could not fork"
# after 1 os.fork event, and main(), as orch_stop_guard fails open, restores SIGCHLD to SIG_DFL and
# probes again, which forks.
FIRST_FORK_FAILS_PROG = """
import errno, os, sys

real_fork = os.fork
forks = []


def first_fork_fails():
    forks.append(1)
    if len(forks) == 1:
        sys.audit("os.fork")
        raise BlockingIOError(errno.EAGAIN, os.strerror(errno.EAGAIN))
    return real_fork()


os.fork = first_fork_fails
""" + RECORDING_HOOK_PROG

# Runs in a separate python3 -I process: argv[1] is a Python executable and argv[2:] the arguments
# that it runs with -I. It sets SIGCHLD to SIG_IGN, writes "SIGCHLD ignored" to stdout once
# signal.getsignal reads that back, and execs the executable, which keeps the ignored disposition
# across exec, as a process does that a parent that ignores SIGCHLD starts.
SIGCHLD_IGNORED_PROG = """
import os, signal, sys

signal.signal(signal.SIGCHLD, signal.SIG_IGN)
if signal.getsignal(signal.SIGCHLD) is signal.SIG_IGN:
    print("SIGCHLD ignored", flush=True)
os.execv(sys.argv[1], [sys.argv[1], "-I"] + sys.argv[2:])
"""

# The end of the note that main() writes to stderr when its first child-status probe
# (_child_status_refusal) has refused, it has restored SIGCHLD to SIG_DFL and its second probe has read
# a child's status (aiqt_hooks.py:38211), after the reason that the first probe gave; and the reasons
# that the first probe gives before it calls os.fork, as SIGCHLD is not at SIG_DFL (aiqt_hooks.py:38120
# and 38121).
PROBE_RESTORED_NOTE = ("; SIGCHLD restored to SIG_DFL for this hook process and the probe then read "
                       "its child's status")
PROBE_REFUSALS_BEFORE_FORK = ("SIGCHLD is ignored (SIG_IGN) in this process",
                              "SIGCHLD is not at its default disposition in this process")


def probe_forks(stderr):
    """The os.fork events that main()'s child-status probes raise in a hook run, from the run's stderr:
    1 when it holds no restore note, as the first probe then read its child's status; with 1 note, 1
    for the second probe, and 1 more when the reason before the note is not one that the first probe
    gives before it calls os.fork (it could not fork, its child was reaped before it, or its child's
    status could not be read or was not 77); None when the note is there more than once."""
    notes = [line for line in stderr.splitlines() if line.endswith(PROBE_RESTORED_NOTE)]
    if not notes:
        return ["os.fork"]
    if len(notes) > 1:
        return None
    reason = notes[0][:-len(PROBE_RESTORED_NOTE)]
    return ["os.fork"] if reason.endswith(PROBE_REFUSALS_BEFORE_FORK) else ["os.fork", "os.fork"]


class T15EnumeratorTimeout(Stage2Harness):
    HOOK_BOUND = 120
    CLEANUP_BOUND = 30
    WALL_CLOCK_BOUND = 240
    STANDIN_HOOK_BOUND = 10
    STANDIN_WALL_CLOCK_BOUND = 60
    NESTED_WALL_CLOCK_BOUND = 300
    # The largest value is ENUM_TIMEOUT, as write_registry refuses a declared timeout over it.
    DECLARED_TIMEOUTS = (0.001, 1, 7.5, ENUM_TIMEOUT)

    def run_reaped(self, cmd, report, hook_bound=None, wall_clock_bound=None):
        """Run cmd through REAPER_PROG with the JSON stdin payload and return (the completed wrapper,
        or None if it reached the wall-clock bound, and the report, or None if the wrapper wrote
        none). The hook bound defaults to HOOK_BOUND and the wall-clock bound to WALL_CLOCK_BOUND,
        which leaves the wrapper 90 s beyond its 2 bounds; the 2 wrapper tests pass 10 s and 60 s,
        which leaves it 20 s. What can outlive the test: every process under the wrapper when the
        wrapper ends before its cleanup has finished, which happens when the wall-clock bound kills
        it (that bound kills only the wrapper; in a wrapper test those processes include the
        stand-in hook's child and grandchild), when another signal ends it, such as one that the
        hook sends it, or when an error ends it; the children that REAPER_PROG lists as still alive
        when cleanup stops at its bound, and their descendants; and a process that the hook gets
        another program, such as a service manager, to start. In each case but the last the test
        fails, as this method then returns no completed wrapper, no report, or a report that lists
        a child."""
        hook_bound = self.HOOK_BOUND if hook_bound is None else hook_bound
        try:
            r = run_doctor_recorded(self, [sys.executable, "-I", "-c", REAPER_PROG, str(report),
                                           str(hook_bound), str(self.CLEANUP_BOUND), *cmd],
                                    input=json.dumps({"cwd": str(self.repo)}), capture_output=True,
                                    text=True, env=self._env(),
                                    timeout=wall_clock_bound or self.WALL_CLOCK_BOUND)
        except subprocess.TimeoutExpired:
            r = None
        rep = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
        return r, rep

    def assert_reaped(self, r, rep, hook_bound=None):
        """The wrapper ended within the wall-clock bound, wrote its report, left no process alive,
        and the hook exited within its bound."""
        if r is None:
            self.fail("the wrapper hit the {} s wall-clock bound".format(self.WALL_CLOCK_BOUND))
        if rep is None:
            self.fail("the wrapper wrote no report; exit {}, stderr: {}".format(r.returncode,
                                                                                 r.stderr))
        self.assertEqual(rep["not_reaped"], [], "processes that the hook started outlasted SIGKILL "
                         "for {} s".format(self.CLEANUP_BOUND))
        self.assertTrue(rep["exited"], "the hook did not exit within {} s and was killed".format(
            self.HOOK_BOUND if hook_bound is None else hook_bound))

    def assert_lock_free(self, lock):
        import fcntl
        fd = os.open(str(lock), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fail("a process that the stand-in hook started outlived the wrapper")
        finally:
            os.close(fd)

    def run_standin(self, mode):
        lock = self._tmp / "standin.lock"
        ready = self._tmp / "standin.ready"
        r, rep = self.run_reaped([sys.executable, "-I", "-c", STANDIN_HOOK, str(lock), str(ready),
                                  mode], self._tmp / "standin-report.json",
                                 hook_bound=self.STANDIN_HOOK_BOUND,
                                 wall_clock_bound=self.STANDIN_WALL_CLOCK_BOUND)
        self.assertEqual(ready.read_text(encoding="utf-8") if ready.exists() else "", "ready\n",
                         "precondition: the stand-in hook started its child and grandchild")
        self.assert_lock_free(lock)
        return r, rep

    def test_wrapper_kills_processes_in_another_session(self):
        # Catches: the stand-in hook exits at once and leaves a child in another session and process
        # group, and that child's child, both alive. Once the wrapper has returned, the test requires
        # that it can take the stand-in's lock exclusively, so none of the 3 processes is alive, and
        # then a report with "left_running" true, "exited" true and "not_reaped" empty. A wrapper
        # that kills only the hook's process group, as the earlier one did, misses both processes
        # and then waits for them to end; the 60 s wall-clock bound kills it, and the lock check
        # fails. A wrapper that kills its children once and does not repeat misses the grandchild.
        r, rep = self.run_standin("exit")
        self.assertIsNotNone(r, "the wrapper hit the {} s wall-clock bound".format(
            self.STANDIN_WALL_CLOCK_BOUND))
        self.assertEqual(rep, {"exited": True, "left_running": True, "not_reaped": []})

    def test_wrapper_kills_a_hook_that_does_not_exit(self):
        # Catches: the stand-in hook leaves the same 2 processes and then sleeps 90 s itself, past
        # the 10 s hook bound. Once the wrapper has returned, the test requires that it can take the
        # lock exclusively and then a report with "exited" false and "not_reaped" empty. A wrapper
        # that waits for the hook without a bound, as the earlier one did, is killed by the 60 s
        # wall-clock bound while the hook and its 2 processes are alive, and the lock check fails.
        r, rep = self.run_standin("hang")
        self.assertIsNotNone(r, "the wrapper hit the {} s wall-clock bound".format(
            self.STANDIN_WALL_CLOCK_BOUND))
        self.assertEqual(rep, {"exited": False, "left_running": True, "not_reaped": []})

    def test_sleeping_enumerator_times_out_and_denies(self):
        # Catches: the sleeping enumerator runs under a declared timeout of 1 s, and the unchanged
        # hook runs through RECORDING_HOOK_PROG in its "keep" mode, itself run through REAPER_PROG.
        # The recorder keeps the timeout argument of the enumerator call only, so no other timeout of
        # the hook, such as the 5 s one of its git call in _recovery_toplevel, can fire.
        # Once the wrapper call ends, the test requires, in this order:
        # - that the wrapper call ended within the 240 s wall-clock bound (temporal) and that the
        #   wrapper wrote its report (logical);
        # - that "not_reaped" is empty, so no process that the hook started was alive when cleanup
        #   stopped, which it does once no process is left or once the 30 s cleanup bound has passed
        #   (temporal; a hook that leaves no process running leaves cleanup nothing to do, and the
        #   list is then empty without it);
        # - that the hook exited within the 120 s hook bound (temporal);
        # - that the calls whose argv is the declared enumerator argv are exactly 1 call, with the
        #   timeout argument 1 and the outcome TimeoutExpired (logical);
        # - that no process that the hook started was still running when it ended (logical);
        # - exit 2, ENUMERATOR_ERROR and 'failed to run' in stderr (logical).
        # The test asks the enumerator to do nothing but record its start before the timeout fires,
        # and the enumerator sleeps 100 s, so a call that passes it a timeout of 1 s raises
        # TimeoutExpired once that timeout fires, unless the enumerator cannot be started or the
        # 120 s bound kills the hook first. A correct hook leaves no process running, so for such a
        # hook only the 240 s and 120 s bounds can make a check's result depend on how loaded the
        # host is. A hook that passes no timeout argument waits the 100 s sleep out and fails the
        # call check if it still exits within the 120 s bound, as its call then records no timeout
        # argument and the outcome "returned", and fails the "exited" check first if it does not. A
        # hook that passes a timeout argument other than 1 fails the call check if it still exits
        # within the 120 s bound, as with a fixed 20 s, 60 s or 180 s, max(timeout, 30) or
        # timeout * 2, and fails the "exited" check first if it does not. A hook that runs the
        # enumerator again after a timeout records 2 or more calls and fails the call check if it
        # still exits within 120 s, and fails the
        # "exited" check first if its runs take it past 120 s. A hook that starts the enumerator
        # with Popen and returns without stopping it, in or out of a new session, records no call
        # and fails the call check, and the test ends there: such a hook also leaves the enumerator
        # running, but the "left_running" check comes after the call check and is not reached. A
        # hook that takes the timeout as success or gives another verdict fails the last check. The
        # wrapper kills every process that the hook started and left running, within the limits
        # that REAPER_PROG and run_reaped state.
        # Misses: the test does not time the effective timeout. Enforcement rests on subprocess.run
        # honouring its timeout argument, seen once here as TimeoutExpired. A hook that passes 1 s
        # whatever is declared, or changes only values other than 1, such as round(timeout), passes;
        # test_declared_timeout_reaches_the_enumerator_call catches each such change to 0.001, 7.5
        # or 60. A stall after the timeout, or before the hook starts the enumerator, passes if the
        # hook still exits within 120 s; the 15 s bound on the whole call that this test had at
        # d649a24 caught such a stall only when the whole call then passed 15 s, which a 5 s stall
        # after the 1 s timeout need not bring about, and it also failed the correct hook when a
        # loaded host took the whole call past 15 s. PR 284 widened that bound to 90 s (TODO 254),
        # measured from before the hook starts and below the enumerator's sleep; the 120 s hook bound
        # is wider still, also covers the hook's start-up, and, as with the 90 s bound, a hook that
        # waits the sleep out fails, here by the call check if it still exits within 120 s and by
        # the "exited" check first if it does not. A hook that starts the enumerator other
        # than through subprocess.run records no call and fails here even if it stops the
        # enumerator at the declared time. The unchanged hook's timeout stops only the enumerator's
        # own process, and the sleeping enumerator is 1 process, so this test says nothing about
        # processes that an enumerator starts. This test declares only 1 s, so of the changes to the
        # hook's check of the declared value (a number, above 0, at most 600) it catches only one
        # that rejects 1: such a hook passes the 60 s fallback as the timeout and fails the call check
        # if it still exits within 120 s, and the "exited" check first if it does not.
        record = self._tmp / "run-calls-enforced.jsonl"
        argv = [sys.executable, "-I", "-c", SLEEPING_ENUM_FIXTURE]
        self.write_registry(self.stage2(enumerator={"argv": argv, "timeout": 1}))
        self.arm_lease()
        r, rep = self.run_reaped([sys.executable, "-I", "-c", RECORDING_HOOK_PROG, str(HOOK),
                                  str(record), "orch_stop_guard", "keep", json.dumps(argv)],
                                 self._tmp / "reaper-report.json")
        self.assert_reaped(r, rep)
        rows = [json.loads(line) for line in
                (record.read_text(encoding="utf-8") if record.exists() else "").splitlines()]
        calls = [(row["timeout"], row.get("outcome")) for row in rows if row["argv"] == argv]
        self.assertEqual(calls, [(1, "TimeoutExpired")], "timeout arguments and outcomes of the "
                         "enumerator calls for a declared 1 s: {}; hook exit {}, stderr: {}".format(
                             calls, r.returncode, r.stderr))
        self.assertFalse(rep["left_running"], "a process that the hook started was still running "
                         "when the hook call ended; exit {}, stderr: {}".format(r.returncode,
                                                                                r.stderr))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ENUMERATOR_ERROR", r.stderr)
        self.assertIn("failed to run", r.stderr)

    def test_declared_timeout_reaches_the_enumerator_call(self):
        # The unchanged hook runs through RECORDING_HOOK_PROG in its "strip" mode, itself run through
        # REAPER_PROG, once for each value in DECLARED_TIMEOUTS, with the writing fixture, a -c
        # program of ENUM_PROGRAMS, as the enumerator under that declared timeout. For each value
        # the test requires, in this order,
        # that the wrapper call ended within the 240 s wall-clock bound (temporal) and that the
        # wrapper wrote its report (logical), that no process that the hook started was alive when
        # cleanup stopped, once no process was left or once the 30 s cleanup bound had passed
        # (temporal; a hook that leaves no process running leaves cleanup nothing to do), and that
        # the hook exited within the 120 s hook bound (temporal), then that the calls whose argv is
        # the declared enumerator argv passed exactly that value: 1 call, with the timeout argument
        # equal to the declared value, then that the enumerator ran once (both logical). The test
        # does not check "left_running". No 2 of the 4 values are equal, so a hook that passes the
        # same timeout whatever is declared, such as a fixed 1 s, 20 s or 60 s,
        # fails for at least 3 of them, and a hook that passes timeout * 2, timeout * 3 or no
        # timeout argument fails for all 4. The value 0.001 fails a floor above it, such as
        # max(timeout, 1) or max(timeout, 30), 60 fails a cap below it, and 7.5 fails rounding to
        # a whole number. The recorder makes the real call without the timeout, so the fixture
        # always runs to its end and the test checks no elapsed time apart from the 3 bounds above,
        # of which the 120 s and 240 s bounds include the fixture's run; the fixture's mark file
        # must then hold 'ran\n', so the recorded call ran the real enumerator and nothing else ran
        # it. Residuals: the test does not check that the timeout is enforced or the hook's verdict
        # (test_sleeping_enumerator_times_out_and_denies checks both, and the single call, for a
        # declared 1 s); a hook that starts the enumerator other than through subprocess.run
        # records no call and fails here even if it enforces the declared value. It passes a hook
        # that passes each declared value unchanged and changes others, so it misses: a floor of
        # 0.001 or below, such as max(timeout, 0.001); a cap of 60 or above, such as
        # min(timeout, 60) or min(timeout, 300), which changes only a value over 60, which the test
        # cannot declare, as write_registry refuses a declared timeout over ENUM_TIMEOUT (60 s) (a
        # cap of 600 or above, such as min(timeout, 600), changes nothing, as the hook's check
        # already rejects a value above 600); rounding to 3 or more decimal places, such as
        # round(timeout, 3); a change to a value that the test does not declare, such as 60 s for
        # any value from 10 to 599; and a hook that runs the enumerator again after a timeout, as
        # no call here times out (test_sleeping_enumerator_times_out_and_denies catches that). No
        # declared value is one that the hook's check rejects (not a number, 0 or below, or above
        # 600), so it also misses a change to the 60 s fallback for such a value, such as 30 s, and
        # a change to which values the check rejects that still accepts 0.001, 1, 7.5 and 60, such
        # as one that rejects JSON true, which the unchanged hook takes as 1 s, or one that rejects
        # each value over 60. A change that rejects 0.001, 1 or 7.5, such as one that accepts only
        # an int, fails for that value, as the hook then passes the 60 s fallback. It also misses a
        # change that rejects 60 and still accepts 0.001, 1 and 7.5, such as 0 < timeout < 60, as
        # the hook then passes the 60 s fallback for the declared 60, the same value.
        for declared in self.DECLARED_TIMEOUTS:
            with self.subTest(declared=declared):
                mark = self._tmp / "enumerator-ran-{}.txt".format(declared)
                record = self._tmp / "run-calls-{}.jsonl".format(declared)
                argv = [sys.executable, "-I", "-c", WRITING_ENUM_FIXTURE, str(self.backlog), str(mark)]
                self.write_registry(self.stage2(enumerator={"argv": argv, "timeout": declared}))
                self.arm_lease()
                r, rep = self.run_reaped([sys.executable, "-I", "-c", RECORDING_HOOK_PROG,
                                          str(HOOK), str(record), "orch_stop_guard", "strip"],
                                         self._tmp / "reaper-report-{}.json".format(declared))
                self.assert_reaped(r, rep)
                rows = [json.loads(line) for line in
                        (record.read_text(encoding="utf-8") if record.exists() else "").splitlines()]
                timeouts = [row["timeout"] for row in rows if row["argv"] == argv]
                self.assertEqual(timeouts, [declared], "timeout arguments of the enumerator call "
                                 "for a declared {}: {}; hook exit {}, stderr: {}".format(
                                     declared, timeouts, r.returncode, r.stderr))
                self.assertEqual(mark.read_text(encoding="utf-8") if mark.exists() else "", "ran\n",
                                 "the recorded call did not run the enumerator once")

    def test_stage1_contrast(self):
        # The stage 1 registry declares no enumerator. The unchanged hook runs through
        # RECORDING_HOOK_PROG in its "strip" mode, itself run through REAPER_PROG, so no timeout of
        # the hook can fire, and the wrapper kills every process that the hook started and left
        # running, within the limits that REAPER_PROG and run_reaped state. Once the wrapper call
        # ends, the test requires, in this order:
        # - that the wrapper call ended within the 240 s wall-clock bound (temporal), that the
        #   wrapper wrote its report (logical), that "not_reaped" is empty, so no process that the
        #   hook started was alive when cleanup stopped, which it does once no process is left or
        #   once the 30 s cleanup bound has passed (temporal), and that the hook exited within the
        #   120 s hook bound (temporal);
        # - that no process that the hook started was still running when it ended (logical);
        # - that the hook's only subprocess.run call was git rev-parse --show-toplevel in
        #   _recovery_toplevel, whose timeout argument the recorder dropped (logical);
        # - that the process starts that the recorder's audit hook saw are that call's and the
        #   child-status probes': 1 subprocess.Popen event with the same argv and 1 os.posix_spawn
        #   or _posixsubprocess.fork_exec event, and the os.fork events of the children that main()
        #   forks to check that it can read a child's exit status (_child_status_refusal at
        #   aiqt_hooks.py:38112-38139; the child exits at once with status 77 and main() waits for
        #   it), and no other (logical). Those are the events that probe_forks reads from stderr: 1
        #   when the first probe reads its child's status; when it refuses, main() of this fail-open
        #   mode restores SIGCHLD to SIG_DFL, probes again and notes the restore, and then 1 for
        #   the second probe and 1 more when the first refused after it called os.fork, as when the
        #   fork failed, and none more when it refused as SIGCHLD was not at SIG_DFL;
        # - exit 2, NO_ENUMERATOR and no 'failed to run' in stderr (logical).
        # So the hook started no process but its git call and those children by subprocess,
        # os.system, os.exec*, os.posix_spawn, os.spawn* or os.fork, and left none running. A hook
        # that also starts a process by one of those routes, such as an enumerator, and leaves it
        # running fails the "left_running" check, and one whose process has ended fails the start
        # check. test_stage1_contrast_after_the_first_probe_fork_fails makes the same checks when
        # the first probe's fork fails, and test_stage1_contrast_when_sigchld_is_ignored runs this
        # test in a process of this file that starts with SIGCHLD ignored. Run through run_hook,
        # without the recorder, the hook allows the stop when the git call's 5 s timeout fires, as it
        # can on a loaded host, and the test would then fail a correct hook. Misses: a process that
        # native code starts without an audit event passes the start check, though the "left_running"
        # check still fails it if it outlives the hook; a process that the hook gets another program,
        # such as a service manager, to start is seen by neither check; and the start check takes the
        # hook's restore note as the account of what its first probe met, so it passes a hook that
        # writes that note and forks as it states.
        self._stage1_contrast(RECORDING_HOOK_PROG, "stage1")

    def test_stage1_contrast_after_the_first_probe_fork_fails(self):
        # Catches: a start check that counts 1 os.fork event of the child-status probes whatever the
        # first probe met, which fails a correct hook whose first probe could not fork. The hook runs
        # as in test_stage1_contrast, with RECORDING_HOOK_PROG started by FIRST_FORK_FAILS_PROG, so
        # the first os.fork call of the hook's process raises its audit event and then
        # BlockingIOError. The test makes the checks of test_stage1_contrast, under which the start
        # check requires 2 os.fork events, and then requires the restore note after the reason
        # "could not fork (BlockingIOError)" in stderr, so main() probed again and its second probe
        # read the child's status.
        r = self._stage1_contrast(FIRST_FORK_FAILS_PROG, "first-fork-fails")
        self.assertIn("the child-status probe could not fork (BlockingIOError)" + PROBE_RESTORED_NOTE,
                      r.stderr)

    def test_stage1_contrast_when_sigchld_is_ignored(self):
        # Catches: a test file that keeps the SIGCHLD disposition that it inherits. When the process
        # that starts this file ignores SIGCHLD, so does the test process, which then reads the exit
        # status of each process that it starts as 0, and so do the wrapper and the hook, as they
        # keep it across exec; test_stage1_contrast then failed a correct hook, reading exit 0 for
        # its exit 2 deny. The test runs test_stage1_contrast in a nested python3 -I process of this
        # file, started through SIGCHLD_IGNORED_PROG, so it starts with SIGCHLD ignored, and
        # requires, in this order, that the call ended within the 300 s NESTED_WALL_CLOCK_BOUND, 60 s
        # past the 240 s bound of the nested test's wrapper call (temporal), that SIGCHLD_IGNORED_PROG
        # read SIG_IGN back before the exec, and that the nested run ran 1 test and exited 0
        # (logical). Misses: a start in which SIGCHLD is at SIG_DFL with SA_NOCLDWAIT set, which this
        # test does not arrange.
        try:
            r = run_doctor_recorded(self, [sys.executable, "-I", "-c", SIGCHLD_IGNORED_PROG,
                                           sys.executable, str(Path(__file__).resolve()),
                                           "T15EnumeratorTimeout.test_stage1_contrast"],
                                    capture_output=True, text=True,
                                    timeout=self.NESTED_WALL_CLOCK_BOUND)
        except subprocess.TimeoutExpired:
            self.fail("the nested run hit the {} s wall-clock bound".format(
                self.NESTED_WALL_CLOCK_BOUND))
        self.assertEqual(r.stdout, "SIGCHLD ignored\n",
                         "precondition: the nested run starts with SIGCHLD ignored; stderr: {}".format(
                             r.stderr))
        self.assertIn("Ran 1 test", r.stderr)
        self.assertEqual(r.returncode, 0, r.stderr)

    def _stage1_contrast(self, prog, name):
        """Run the hook for the stage 1 registry through prog, which is RECORDING_HOOK_PROG or ends
        with it, in its "strip" mode under REAPER_PROG, make the checks that test_stage1_contrast
        states, in its order, and return the completed wrapper."""
        record = self._tmp / "run-calls-{}.jsonl".format(name)
        starts_record = Path(str(record) + ".starts")
        self.write_registry(self.stage1())
        self.arm_lease()
        r, rep = self.run_reaped([sys.executable, "-I", "-c", prog, str(HOOK), str(record),
                                  "orch_stop_guard", "strip"],
                                 self._tmp / "reaper-report-{}.json".format(name))
        self.assert_reaped(r, rep)
        self.assertFalse(rep["left_running"], "a process that the hook started was still running "
                         "when the hook call ended; exit {}, stderr: {}".format(r.returncode,
                                                                                r.stderr))
        git_argv = ["git", "-C", str(self.repo), "rev-parse", "--show-toplevel"]
        rows = [json.loads(line) for line in
                (record.read_text(encoding="utf-8") if record.exists() else "").splitlines()]
        calls = [row["argv"] for row in rows]
        self.assertEqual(calls, [git_argv],
                         "calls of the hook for the stage 1 registry: {}; hook exit {}, stderr: {}"
                         .format(calls, r.returncode, r.stderr))
        starts = [json.loads(line) for line in (starts_record.read_text(encoding="utf-8")
                                                if starts_record.exists() else "").splitlines()]
        popen = [row["argv"] for row in starts if row["event"] == "subprocess.Popen"]
        spawns = [row["event"] for row in starts
                  if row["event"] in ("os.posix_spawn", "_posixsubprocess.fork_exec")]
        others = [row["event"] for row in starts
                  if row["event"] not in ("subprocess.Popen", "os.posix_spawn",
                                          "_posixsubprocess.fork_exec")]
        self.assertEqual((popen, len(spawns), others), ([git_argv], 1, probe_forks(r.stderr)),
                         "process starts of the hook for the stage 1 registry: {}; hook exit {}, "
                         "stderr: {}".format(starts, r.returncode, r.stderr))
        self.assert_no_enumerator_deny(r)
        self.assertNotIn("failed to run", r.stderr)
        return r


class EnumeratorBounds(Stage2Harness):
    """run_doctor_recorded holds the timeout of every launch, when the launch has run, to at least
    ENUM_TIMEOUT for each enumerator start that the launch recorded, plus ENUM_MARGIN
    (enumerator_bound_defect), so the hook's own timeout ends an enumerator that hangs, and the case
    reads what the hook reports, before the bound ends the run. It reads the timeout that the launch
    was given, however the case bound it. These cases require that a start reaches the record through
    the hook and through the doctor, that a launch 1 second under its bound fails its case and a launch
    at its bound passes, for 1 start and for 2, also when check=True fails after the start, that a
    launch with no running case fails at once, with the exception that the launch raised as the cause,
    also when the launch printed a doctor refusal as well, that each of ENUM_PROGRAMS records its start
    first and leaves the record alone after it, and that each branch of those 2 checks
    (runs_enum_run_mark_first and program_leaves_record) refuses a program of its own, that
    write_registry checks the enumerator as the hook reads it from the file written, so a tuple or a
    str subclass is checked as the text that json writes, and refuses an enumerator that the hook
    would start and whose argv is not exactly this interpreter (sys.executable), -I, -c and 1 of
    ENUM_PROGRAMS, each a separate element, followed by any operands (one run by another interpreter
    or without -I, one whose -I and -c are joined, swapped or apart, and one whose program is not 1 of
    ENUM_PROGRAMS: one without the statements of ENUM_RUN_MARK, also when its timeout is absent or one
    that the hook reads as 60, one that holds them only as text or after an exit, one that begins with
    them but does not compile, and one that begins with them and then removes the record or adds a
    start), or whose timeout, as the hook reads it, is over ENUM_TIMEOUT, that for each of the
    interpreter, -I, -c and the program it refuses a named value that begins with, ends with or holds
    an accepted value, and a named value that an accepted value begins or ends with, that it refuses
    every program-file form found so far, each with a recording file in place, that write_registry,
    declared_enumerator_defect, runs_enum_run_mark_first and program_leaves_record each have exactly
    the body of PINNED_CHECKS, and that ENUM_PROGRAMS is its 3 reviewed programs, by sha256, both in
    the test process and in a new python3 -I process that parses the text of this file and does not
    import it (PIN_PROGRAM), which also requires that its scan of the file finds no binding of a name
    that those bodies read, of the forms that the scan models, but its definition, though code of the
    file can defeat that scan by routes that it does not model, as stated above PIN_PROGRAM, and that
    write_registry refuses every near miss that near_misses generates for each element and each other
    path to the interpreter that the case builds. The named rows and the near misses are finite: each
    refuses the values it holds and shows nothing about any other value. The exact checks are required
    by the pin of PINNED_CHECKS, and what the pin does not see, among it a rebinding that names its
    target only at run time, is stated above PIN_PROGRAM. This suite no longer drives a program-file
    enumerator through the hook: the hook passes the argv to subprocess.run unchanged
    (aiqt_hooks.py:22833), so what the hook does with it does not depend on its form. What the check
    does not see is stated above enumerator_bound_defect."""

    # A child that runs the program that its operands name twice, and one that runs it once and exits 1.
    TWICE = ("import subprocess, sys\n"
             "for _ in range(2):\n"
             "    subprocess.run(sys.argv[1:], check=True, stdout=subprocess.DEVNULL)\n")
    FAILS = ("import subprocess, sys\n"
             "subprocess.run(sys.argv[1:], check=True, stdout=subprocess.DEVNULL)\n"
             "sys.exit(1)\n")

    def test_each_launch_records_the_enumerator_starts_that_it_made(self):
        # A stage-2 Stop and a stage-2 preflight each start the fixture enumerator once, the first through
        # the hook and the second through the doctor; a stage-1 Stop starts none.
        self.write_registry(self.stage2())
        self.arm_lease()
        take_enumerator_launches(self)
        self.assertEqual(self.stop().returncode, 0)
        self.assertEqual(self.run_doctor("preflight", "stop").returncode, 0)
        self.write_registry(self.stage1())
        self.assert_no_enumerator_deny(self.stop())
        self.assertEqual([(timeout, runs) for _argv, timeout, runs in take_enumerator_launches(self)],
                         [(RUN_TIMEOUT, 1), (RUN_TIMEOUT, 1), (RUN_TIMEOUT, 0)])

    def test_a_launch_under_its_bound_fails_its_case(self):
        once = [sys.executable, "-I", "-c", ENUM_FIXTURE, str(self.backlog)]
        twice = [sys.executable, "-I", "-c", self.TWICE] + once
        fails = [sys.executable, "-I", "-c", self.FAILS] + once
        need_once, need_twice = ENUM_TIMEOUT + ENUM_MARGIN, 2 * ENUM_TIMEOUT + ENUM_MARGIN

        class Probe(unittest.TestCase):
            argv, timeout, check = once, None, False

            def test_launch(inner):
                try:
                    run_doctor_recorded(inner, inner.argv, capture_output=True, text=True,
                                        timeout=inner.timeout, check=inner.check)
                except subprocess.CalledProcessError:
                    inner.assertTrue(inner.check, "the launch failed")

        rows = (("1 start, 1 s under", once, need_once - 1, False, "under 1 enumerator start(s)"),
                ("1 start, at the bound", once, need_once, False, None),
                ("2 starts, 1 s under", twice, need_twice - 1, False, "under 2 enumerator start(s)"),
                ("2 starts, at the bound", twice, need_twice, False, None),
                ("1 start, no timeout", once, None, False, None),
                ("1 start, then check=True fails", fails, need_once - 1, True, "under 1 enumerator start(s)"))
        for name, argv, timeout, check, wanted in rows:
            with self.subTest(launch=name):
                Probe.argv, Probe.timeout, Probe.check = argv, timeout, check
                result = unittest.TestResult()
                Probe("test_launch").run(result)
                self.assertEqual(result.errors, [])
                self.assertEqual(len(result.failures), 0 if wanted is None else 1, result.failures)
                if wanted is not None:
                    self.assertIn(wanted, result.failures[0][1])
        with self.subTest(launch="no running case"):
            with self.assertRaisesRegex(AssertionError, "no running case.*under 1 enumerator start"):
                run_doctor_recorded(None, once, capture_output=True, text=True, timeout=need_once - 1)
            run_doctor_recorded(None, once, capture_output=True, text=True, timeout=need_once)
        # The bound failure keeps the exception that the launch raised as its cause.
        with self.subTest(launch="no running case, then check=True fails"):
            wanted = "no running case.*under 1 enumerator start"
            with self.assertRaisesRegex(AssertionError, wanted) as caught:
                run_doctor_recorded(None, fails, capture_output=True, text=True, timeout=need_once - 1,
                                    check=True)
            self.assertIsInstance(caught.exception.__cause__, subprocess.CalledProcessError)
        # The same when the launch also printed a doctor refusal, which no case can register: the bound
        # failure keeps the exception of the launch as its cause, and the failed registration is its
        # context. The refusal reaches the child as an operand, so no literal here holds it.
        prints = ("import subprocess, sys\n"
                  "subprocess.run(sys.argv[2:], check=True, stdout=subprocess.DEVNULL)\n"
                  "print(sys.argv[1])\n"
                  "sys.exit(1)\n")
        with self.subTest(launch="no running case, a doctor refusal, then check=True fails"):
            with self.assertRaisesRegex(AssertionError, wanted) as caught:
                run_doctor_recorded(None, [sys.executable, "-I", "-c", prints, REFUSAL_PREFIX] + once,
                                    capture_output=True, text=True, timeout=need_once - 1, check=True)
            self.assertIsInstance(caught.exception.__cause__, subprocess.CalledProcessError)
            self.assertIsInstance(caught.exception.__context__, AssertionError)
            self.assertIn("printed a doctor refusal", str(caught.exception.__context__))

    def test_each_accepted_program_records_first_and_leaves_its_record(self):
        # Each program that write_registry accepts records its start before any other statement runs
        # and, after that, names neither the record nor the environment; the check refuses a program
        # that removes the record, adds a start or reads the environment after the mark. Through the
        # hook, the 2 fixture programs that end each record exactly 1 start.
        for program in ENUM_PROGRAMS:
            self.assertTrue(runs_enum_run_mark_first(program), program)
            self.assertTrue(program_leaves_record(program), program)
        for program in (self.ERASES, self.FORGES, self.READS_ENVIRONMENT):
            self.assertTrue(runs_enum_run_mark_first(program), program)
            self.assertFalse(program_leaves_record(program), program)
        # The check reads names, so a program can reach the record without them; that is why, in an
        # enumerator that the hook would start, write_registry accepts no program but 1 of ENUM_PROGRAMS,
        # which refuses this one.
        self.assertTrue(program_leaves_record(self.SEARCHES), "precondition: no name of the record")
        self.assertNotIn(self.SEARCHES, ENUM_PROGRAMS)
        # Each branch of the 2 checks refuses a program of its own: runs_enum_run_mark_first refuses
        # the record followed by a statement that does not compile, and program_leaves_record refuses
        # the record followed by a program that holds exactly 1 of the names, 1 of the attributes or a
        # string that holds ENUM_RUNS_VAR, a row for each member of each list. The lists are written
        # here, not read from the check, so a member dropped from the check fails its row.
        for tail in ("return\n", "break\n", "from __future__ import annotations\n"):
            self.assertFalse(runs_enum_run_mark_first(ENUM_RUN_MARK + tail), tail)
        names = ("_runs", "_record", "environ", "getenv", "putenv")
        attributes = ("environ", "getenv", "putenv")
        rows = ((("name", "_runs"), "_runs.strip()\n"), (("name", "_record"), "_record.close()\n"),
                (("name", "environ"), "from os import environ\nenviron.clear()\n"),
                (("name", "getenv"), "from os import getenv\ngetenv(\"HOME\")\n"),
                (("name", "putenv"), "from os import putenv\nputenv(\"A\", \"1\")\n"),
                (("attribute", "environ"), "os.environ.clear()\n"),
                (("attribute", "getenv"), "os.getenv(\"HOME\")\n"),
                (("attribute", "putenv"), "os.putenv(\"A\", \"1\")\n"),
                (("string", ENUM_RUNS_VAR), "_name = \"" + ENUM_RUNS_VAR + "\"\n"))
        self.assertEqual({member for member, _tail in rows},
                         {("name", name) for name in names} | {("attribute", name) for name in attributes}
                         | {("string", ENUM_RUNS_VAR)}, "precondition: a row for each member")
        for member, tail in rows:
            nodes = list(ast.walk(ast.parse(tail)))
            hits = ({("name", node.id) for node in nodes if isinstance(node, ast.Name) and node.id in names}
                    | {("attribute", node.attr) for node in nodes
                       if isinstance(node, ast.Attribute) and node.attr in attributes}
                    | {("string", ENUM_RUNS_VAR) for node in nodes if isinstance(node, ast.Constant)
                       and isinstance(node.value, str) and ENUM_RUNS_VAR in node.value})
            self.assertEqual(hits, {member}, "precondition: the row holds only its own member")
            program = ENUM_RUN_MARK + tail
            with self.subTest(member=member):
                self.assertTrue(runs_enum_run_mark_first(program), program)
                self.assertFalse(program_leaves_record(program), program)
        marker = self._tmp / "enumerator-ran.txt"
        self.arm_lease()
        for argv in ([sys.executable, "-I", "-c", ENUM_FIXTURE, str(self.backlog)],
                     [sys.executable, "-I", "-c", WRITING_ENUM_FIXTURE, str(self.backlog), str(marker)]):
            with self.subTest(program=argv[3][len(ENUM_RUN_MARK):][:40]):
                self.write_registry(self.stage2(enumerator={"argv": argv, "timeout": ENUM_TIMEOUT}))
                take_enumerator_launches(self)
                self.assertEqual(self.stop().returncode, 0)
                self.assertEqual([runs for _argv, _timeout, runs in take_enumerator_launches(self)], [1])

    # 3 programs that begin with the record and then reach it: 1 removes it, 1 adds a start that did not
    # happen, and 1 opens the file that the environment names.
    ERASES = ENUM_FIXTURE.replace("import json\n", "os.remove(_runs)\nimport json\n", 1)
    FORGES = ENUM_FIXTURE.replace(
        "import json\n", "open(_runs, \"a\", encoding=\"utf-8\").write(\"run\\n\")\nimport json\n", 1)
    READS_ENVIRONMENT = ENUM_FIXTURE.replace(
        "import json\n", "open(os.environ[\"" + ENUM_RUNS_VAR + "\"], \"w\").close()\nimport json\n", 1)
    # A program that begins with the record and removes it, found by the name of its folder
    # (_new_starts_folder), so program_leaves_record finds nothing; only ENUM_PROGRAMS refuses it.
    SEARCHES = ENUM_FIXTURE.replace(
        "import json\n", "import glob, tempfile\n"
        "for _found in glob.glob(tempfile.gettempdir() + \"/orch-stage2-starts-*/starts\"):\n"
        "    os.remove(_found)\nimport json\n", 1)

    # The words of the refusal of a declared enumerator that the hook would start and whose argv is not
    # exactly this interpreter (sys.executable), -I, -c and 1 of ENUM_PROGRAMS, each a separate element,
    # followed by any operands (declared_enumerator_defect).
    REFUSED = "is not this interpreter, -I, -c and 1 of ENUM_PROGRAMS"

    def test_write_registry_refuses_an_enumerator_that_would_not_be_held(self):
        # 2 programs that hold ENUM_RUN_MARK as text but do not run it first: as a string constant, and
        # after an exit.
        as_text = "_text = '''" + ENUM_RUN_MARK + "'''\n"
        after_exit = "import sys\nsys.exit(0)\n" + ENUM_RUN_MARK
        for program in (as_text, after_exit):
            self.assertIn(ENUM_RUN_MARK, program, "precondition: the record is in the program text")
        # 3 programs whose syntax tree begins with the statements of ENUM_RUN_MARK but that do not
        # compile, so the interpreter refuses each before the record runs.
        uncompiled = {name: ENUM_RUN_MARK + tail for name, tail in (
            ("a top-level return", "return\n"), ("a top-level break", "break\n"),
            ("a misplaced future import", "from __future__ import annotations\n"))}
        mark = [ast.dump(node) for node in ast.parse(ENUM_RUN_MARK).body]
        for program in uncompiled.values():
            self.assertEqual([ast.dump(node) for node in ast.parse(program).body][:len(mark)], mark,
                             "precondition: the syntax tree begins with the record")
        fixture = [sys.executable, "-I", "-c", ENUM_FIXTURE, str(self.backlog)]

        class EqualToAll(str):
            """A str that equals every value but that json writes as its own text."""

            def __eq__(self, other):
                return True

            __hash__ = str.__hash__

        rows = (("a -c program without the record", [sys.executable, "-I", "-c", "pass"], ENUM_TIMEOUT,
                 self.REFUSED),
                ("a tuple argv, which json writes as a list that the hook runs",
                 (sys.executable, "-I", "-c", "pass"), ENUM_TIMEOUT, self.REFUSED),
                ("a str subclass that equals -c but is written as -cpass",
                 [sys.executable, "-I", EqualToAll("-cpass")] + fixture[3:], ENUM_TIMEOUT, self.REFUSED),
                ("a joined -c and command before the program", [sys.executable, "-I", "-cpass"] + fixture[3:],
                 ENUM_TIMEOUT, self.REFUSED),
                ("-I and -c joined", [sys.executable, "-Ic"] + fixture[3:], ENUM_TIMEOUT, self.REFUSED),
                ("-c before -I", [sys.executable, "-c", "-I"] + fixture[3:], ENUM_TIMEOUT, self.REFUSED),
                ("another option in place of -I", [sys.executable, "-u"] + fixture[2:], ENUM_TIMEOUT,
                 self.REFUSED),
                ("an option between -I and -c", fixture[:2] + ["-u"] + fixture[2:], ENUM_TIMEOUT,
                 self.REFUSED),
                ("the record followed by a removal of the record",
                 [sys.executable, "-I", "-c", self.ERASES, str(self.backlog)], ENUM_TIMEOUT, self.REFUSED),
                ("the record followed by a start that did not happen",
                 [sys.executable, "-I", "-c", self.FORGES, str(self.backlog)], ENUM_TIMEOUT, self.REFUSED),
                ("the record followed by an open of the file that the environment names",
                 [sys.executable, "-I", "-c", self.READS_ENVIRONMENT, str(self.backlog)], ENUM_TIMEOUT,
                 self.REFUSED),
                ("the record followed by a removal of the record found by its folder name",
                 [sys.executable, "-I", "-c", self.SEARCHES, str(self.backlog)], ENUM_TIMEOUT, self.REFUSED),
                ("a -c program that holds the record only as text", [sys.executable, "-I", "-c", as_text],
                 ENUM_TIMEOUT, self.REFUSED),
                ("a -c program that holds the record after an exit",
                 [sys.executable, "-I", "-c", after_exit], ENUM_TIMEOUT, self.REFUSED),
                ("a -c program run without -I", [sys.executable] + fixture[2:], ENUM_TIMEOUT, self.REFUSED),
                ("a -c program run by another interpreter", ["python3"] + fixture[1:], ENUM_TIMEOUT,
                 self.REFUSED),
                ("a timeout over ENUM_TIMEOUT", fixture, ENUM_TIMEOUT + 1, "over ENUM_TIMEOUT"))
        rows += tuple(("the record followed by " + name, [sys.executable, "-I", "-c", program], ENUM_TIMEOUT,
                       self.REFUSED) for name, program in uncompiled.items())
        # For each of the interpreter, -I, -c and the program, these rows hold a value that begins with,
        # ends with or holds an accepted value, and a value that an accepted value begins or ends with,
        # so a check that took an accepted value as a prefix, a suffix or a part of the value, or the
        # value as a prefix, a suffix or a part of an accepted value, accepts at least 1 of these rows.
        # They catch those loosenings only; test_the_checks_on_the_path_to_acceptance_are_pinned pins the
        # exact comparison itself, and test_write_registry_refuses_every_generated_near_miss drives near
        # misses of other kinds.
        first_line = ENUM_FIXTURE.split("\n", 1)[0] + "\n"
        unmarked = ENUM_FIXTURE[len(ENUM_RUN_MARK):]
        interpreter_name = os.path.basename(sys.executable)
        self.assertTrue(os.path.isabs(sys.executable) and interpreter_name != sys.executable,
                        "precondition: the interpreter path has a directory")
        self.assertTrue(ENUM_FIXTURE.startswith(first_line) and first_line != ENUM_FIXTURE
                        and not runs_enum_run_mark_first(first_line),
                        "precondition: the first line is a part of the fixture without the record")
        self.assertTrue(ENUM_FIXTURE.endswith(unmarked) and not runs_enum_run_mark_first(unmarked),
                        "precondition: the rest is a part of the fixture without the record")
        rest = fixture[2:]
        loose = (
            ("a path that begins with this interpreter's path", [sys.executable + "-other"] + fixture[1:]),
            ("a relative path that ends with this interpreter's path", ["." + sys.executable] + fixture[1:]),
            ("a path with which this interpreter's path begins", [sys.executable[:-1]] + fixture[1:]),
            ("the name of this interpreter without its directory", [interpreter_name] + fixture[1:]),
            ("a command joined to -I before -c and an accepted program",
             [sys.executable, "-Icpass"] + rest),
            ("an -X option whose value is -I, which leaves isolation off", [sys.executable, "-X-I"] + rest),
            ("- in place of -I", [sys.executable, "-"] + rest),
            ("I in place of -I", [sys.executable, "I"] + rest),
            ("an -X option whose value is -c, in place of -c", fixture[:2] + ["-X-c"] + fixture[3:]),
            ("- in place of -c", fixture[:2] + ["-"] + fixture[3:]),
            ("c in place of -c", fixture[:2] + ["c"] + fixture[3:]),
            ("an accepted program followed by a removal of the record",
             fixture[:3] + [ENUM_FIXTURE + "os.remove(_runs)\n"] + fixture[4:]),
            ("an exit followed by an accepted program",
             fixture[:3] + ["import sys\nsys.exit(0)\n" + ENUM_FIXTURE] + fixture[4:]),
            ("the first line of an accepted program alone", fixture[:3] + [first_line] + fixture[4:]),
            ("an accepted program without its record", fixture[:3] + [unmarked] + fixture[4:]))
        rows += tuple((name, argv, ENUM_TIMEOUT, self.REFUSED) for name, argv in loose)
        for name, argv, timeout, wanted in rows:
            with self.subTest(enumerator=name):
                with self.assertRaisesRegex(self.failureException, wanted):
                    self.write_registry(self.stage2(enumerator={"argv": argv, "timeout": timeout}))
        # The hook reads an absent timeout, and one that is not an int or a float (a bool counts as an
        # int), is not over 0 or is over 600, as 60 and still starts the enumerator
        # (aiqt_hooks.py:22830-22831), so write_registry checks the argv whatever the timeout holds: it
        # refuses a -c program without the record and accepts the fixture with each of those, an absent
        # timeout included. It refuses each timeout that the hook reads as over ENUM_TIMEOUT, whole or
        # not, up to 600, and accepts each that it reads as at most ENUM_TIMEOUT.
        absent = object()
        for timeout in (absent, None, "fast", "120", 0, -1, 601):
            unmarked_enumerator = {"argv": [sys.executable, "-I", "-c", "pass"]}
            if timeout is not absent:
                unmarked_enumerator["timeout"] = timeout
            with self.subTest(timeout="absent" if timeout is absent else timeout):
                with self.assertRaisesRegex(self.failureException, self.REFUSED):
                    self.write_registry(self.stage2(enumerator=unmarked_enumerator))
                self.write_registry(self.stage2(enumerator=dict(unmarked_enumerator, argv=fixture)))
        for timeout in (ENUM_TIMEOUT + 1, ENUM_TIMEOUT + 2, 600, ENUM_TIMEOUT + 0.5, ENUM_TIMEOUT + 1.5):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(self.failureException, "over ENUM_TIMEOUT"):
                    self.write_registry(self.stage2(enumerator={"argv": fixture, "timeout": timeout}))
        for timeout in (1, ENUM_TIMEOUT - 0.5, ENUM_TIMEOUT, float(ENUM_TIMEOUT)):
            with self.subTest(timeout=timeout):
                self.write_registry(self.stage2(enumerator={"argv": fixture, "timeout": timeout}))
        # The fixture registry passes, so does the sleeping program of ENUM_PROGRAMS, and so does the
        # fixture argv as a tuple, since the hook reads the list that json writes; an argv that the hook
        # refuses starts nothing and is not held.
        self.write_registry(self.stage2())
        self.write_registry(self.stage2(enumerator={
            "argv": [sys.executable, "-I", "-c", SLEEPING_ENUM_FIXTURE], "timeout": 1}))
        self.write_registry(self.stage2(enumerator={"argv": tuple(fixture), "timeout": ENUM_TIMEOUT}))
        self.write_registry(self.stage2(enumerator={"argv": "python3 -I enum.py", "timeout": 600}))

    # Every function on the path from write_registry to its acceptance of a declared enumerator, and the
    # 2 checks that EnumeratorBounds applies to each program of ENUM_PROGRAMS, each with its parameters
    # and, as source text, the statements of its whole body after its docstring: write_registry (the
    # read back, the branch that calls the check, the handling of its result and the write),
    # declared_enumerator_defect (the argv as the hook reads it, the comparison of each of its first 4
    # elements with == or, for the program, by membership in ENUM_PROGRAMS, and the timeout as the hook
    # reads it, aiqt_hooks.py:22830-22831), runs_enum_run_mark_first and program_leaves_record.
    # test_the_checks_on_the_path_to_acceptance_are_pinned requires each body exactly, compared as
    # syntax trees, so any edit to 1 of its statements, and any statement added or removed anywhere in
    # it, fails it, whatever values the edit would accept. It reads the function that each name holds
    # when the case runs, and requires that every Stage2Harness class of this file resolves
    # write_registry and fail, as class attributes, to the functions of Stage2Harness and
    # unittest.TestCase. It also requires, as the test process holds them when the case runs, that each
    # module that the bodies read is the module itself, that no global of this file shadows a builtin,
    # that ENUM_TIMEOUT and ENUM_RUNS_VAR have the values below, and that ENUM_RUN_MARK and each of the
    # 3 programs of ENUM_PROGRAMS, in order, have the sha256 of their UTF-8 text below, so a program
    # added, removed, reordered or changed in the text fails it. Code of this file can rebind those
    # names at run time in ways that this case does not see; PIN_PROGRAM below checks the text in a new
    # process, and states what neither case sees. Neither sees an edit made to the pin and to the code
    # together, or a change outside this file to a name that the bodies read (the builtins module, an
    # attribute of the ast or json module, or sys.executable rebound while the suite runs);
    # test_write_registry_refuses_every_generated_near_miss and the named rows drive write_registry, so
    # they see such a change only when it accepts a value that they hold.
    PINNED_CHECKS = (
        ("write_registry", "self, obj", '''
text = json.dumps(obj)
written = json.loads(text)
enumerator = written.get("enumerator") if isinstance(written, dict) else None
if isinstance(enumerator, dict):
    defect = declared_enumerator_defect(enumerator)
    if defect is not None:
        self.fail(defect)
aiqt = self.repo / ".aiqt"
aiqt.mkdir(exist_ok=True)
(aiqt / "orchestration.json").write_text(text, encoding="utf-8")
'''),
        ("declared_enumerator_defect", "enumerator", '''
argv = enumerator.get("argv")
if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
    return None
if not (len(argv) > 3 and argv[0] == sys.executable and argv[1] == "-I" and argv[2] == "-c"
        and argv[3] in ENUM_PROGRAMS):
    return "the enumerator {!r} is not this interpreter, -I, -c and 1 of ENUM_PROGRAMS".format(argv)
timeout = enumerator.get("timeout")
timeout = timeout if isinstance(timeout, (int, float)) and 0 < timeout <= 600 else 60
if timeout > ENUM_TIMEOUT:
    return "the enumerator timeout {!r} is over ENUM_TIMEOUT".format(timeout)
return None
'''),
        ("runs_enum_run_mark_first", "program", '''
try:
    body = ast.parse(program).body
    compile(program, "<enumerator>", "exec", dont_inherit=True)
except (SyntaxError, ValueError):
    return False
mark = ast.parse(ENUM_RUN_MARK).body
return [ast.dump(node) for node in body[:len(mark)]] == [ast.dump(node) for node in mark]
'''),
        ("program_leaves_record", "program", '''
body = ast.parse(program).body[len(ast.parse(ENUM_RUN_MARK).body):]
for node in ast.walk(ast.Module(body=body, type_ignores=[])):
    if isinstance(node, ast.Name) and node.id in ("_runs", "_record", "environ", "getenv", "putenv"):
        return False
    if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv", "putenv"):
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and ENUM_RUNS_VAR in node.value:
        return False
return True
'''))
    PINNED_MODULES = ("ast", "json", "sys")
    PINNED_BUILTINS = ("SyntaxError", "ValueError", "all", "compile", "dict", "float", "int", "isinstance",
                       "len", "list", "str")
    PINNED_VALUES = (("ENUM_TIMEOUT", 60), ("ENUM_RUNS_VAR", "ORCH_STAGE2_ENUMERATOR_RUNS"))
    ENUM_RUN_MARK_SHA256 = "10c11bf2a18766e23aa9fafa66cd3cccbdce9e1c52a361da13031a49d24e981a"
    ENUM_PROGRAMS_SHA256 = ("9c88bd9211b6e35dd6b52e512ab8690f215060899bf0141ff4a1abe0a7d17a21",
                            "315b094aebc85e63844978cf269182615c347eadb7375fbc9fa537426eb57773",
                            "a273ed8a976cc9643664fe1970d32ef904f6f210b9eaf87613e36b52cba43aad")

    def test_the_checks_on_the_path_to_acceptance_are_pinned(self):
        names = globals()
        functions = {name: Stage2Harness.write_registry if name == "write_registry" else names[name]
                     for name, _parameters, _body in self.PINNED_CHECKS}
        read = set()
        for name, parameters, body in self.PINNED_CHECKS:
            function = functions[name]
            self.assertIsInstance(function, types.FunctionType, name)
            self.assertIs(function.__globals__, names, name)
            self.assertFalse(hasattr(function, "__wrapped__"), "the check {} is wrapped".format(name))
            tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            self.assertEqual(len(tree.body), 1, name)
            node = tree.body[0]
            self.assertIsInstance(node, ast.FunctionDef, name)
            self.assertEqual(node.name, function.__code__.co_name)
            self.assertEqual(node.decorator_list, [], "the check {} is decorated".format(name))
            self.assertEqual(ast.dump(node.args),
                             ast.dump(ast.parse("def f({}):\n    pass\n".format(parameters)).body[0].args), name)
            docstring = node.body[0]
            self.assertTrue(isinstance(docstring, ast.Expr) and isinstance(docstring.value, ast.Constant)
                            and isinstance(docstring.value.value, str),
                            "precondition: the check {} has a docstring".format(name))
            self.assertEqual([ast.dump(statement) for statement in node.body[1:]],
                             [ast.dump(statement) for statement in ast.parse(body).body],
                             "{} is not as PINNED_CHECKS holds it".format(name))
            bound = {argument.arg for argument in node.args.args}
            bound |= {sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)
                      and not isinstance(sub.ctx, ast.Load)}
            read |= {sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)
                     and isinstance(sub.ctx, ast.Load)} - bound
        for case in [value for value in names.values()
                     if isinstance(value, type) and issubclass(value, Stage2Harness)]:
            self.assertIs(case.write_registry, Stage2Harness.write_registry, case.__name__)
            self.assertIs(case.fail, unittest.TestCase.fail, case.__name__)
        pinned = (set(self.PINNED_MODULES) | set(self.PINNED_BUILTINS) | dict(self.PINNED_VALUES).keys()
                  | {"ENUM_RUN_MARK", "ENUM_PROGRAMS"} | functions.keys())
        self.assertEqual(read - pinned, set(), "a pinned check reads a name that is not pinned")
        for module in self.PINNED_MODULES:
            self.assertIs(names[module], __import__(module))
        for builtin in self.PINNED_BUILTINS:
            self.assertNotIn(builtin, names, "a global shadows the builtin " + builtin)
        for name, value in self.PINNED_VALUES:
            self.assertIs(type(names[name]), type(value), name)
            self.assertEqual(names[name], value, name)
        self.assertIs(type(names["ENUM_RUN_MARK"]), str)
        self.assertEqual(hashlib.sha256(names["ENUM_RUN_MARK"].encode("utf-8")).hexdigest(),
                         self.ENUM_RUN_MARK_SHA256, "ENUM_RUN_MARK is not as pinned")
        programs = names["ENUM_PROGRAMS"]
        self.assertIs(type(programs), tuple)
        self.assertTrue(all(type(program) is str for program in programs),
                        "ENUM_PROGRAMS is not a tuple of str")
        self.assertEqual(tuple(hashlib.sha256(program.encode("utf-8")).hexdigest() for program in programs),
                         self.ENUM_PROGRAMS_SHA256, "ENUM_PROGRAMS is not its 3 reviewed programs")

    # The pin above runs in the test process, where code of this file can rebind at run time any name
    # that the pin or the checks read, so no check in this process can hold them: a check replaced by a
    # function of the same source that closes over another ENUM_PROGRAMS, a code object given other
    # names, a global rebound for the cases of 1 class, write_registry bound on an instance, or
    # unittest.TestCase.fail rebound each passes it. PIN_PROGRAM checks the pin again in a new python3 -I
    # process that parses the text of this file, which it reads from the path that it is given, and
    # does not import it, so the names of the test process reach what it computes only through what
    # the test process gives it, which includes its program, that path, the interpreter and the
    # environment; the test process also reads its result. It requires the bodies of PINNED_CHECKS as
    # written; it runs the module-level assignments of ENUM_RUNS_VAR, ENUM_RUN_MARK, the 3 programs,
    # ENUM_PROGRAMS and ENUM_TIMEOUT alone, with no builtins, and requires the values and sha256 of the
    # pin; it compiles the 3 module-level checks with those values, the modules of PINNED_MODULES (ast,
    # json and sys) as that process imports them and the builtins of that process, and requires that
    # they accept each program and refuse a 4th program and a timeout over ENUM_TIMEOUT; and it scans
    # the syntax tree of the file for the forms of binding listed here of a name that the path reads
    # (the 4 checks, those values, the modules ast, json, sys and unittest, the builtins of
    # PINNED_BUILTINS, Stage2Harness and fail) or of the attribute write_registry or fail, and requires
    # that it finds none but the 1 definition of each check, of each of those values and of
    # Stage2Harness, and the 1 plain module-level import of each module. These are the forms, and the
    # only ones, that it finds: the name as a bare name that is stored or deleted, which covers the
    # target of an assignment, an augmented or annotated assignment, del, for, with, := or a
    # comprehension, and the name of a type statement; the name of a def, async def, class, type
    # parameter or except clause, or a name that a match pattern binds (a capture, an as, a star or a
    # mapping rest); a parameter, of a lambda as well; an import that binds the name by its own text
    # (import of the name or of a submodule of it, or from ... import of the name, or any import as the
    # name), but not a star import (from ... import *), which can bind it and which the scan does not
    # see; a global or nonlocal statement that names it; a store or del of the attribute
    # write_registry or fail of any object; a store or del of the code, globals, closure, defaults,
    # keyword defaults, dictionary or __wrapped__ of a check written as its name or as an attribute
    # write_registry or fail; a store or del of any attribute of a module written as the bare name ast,
    # json, sys or unittest; a subscript store or del whose key is the name or attribute as a string
    # constant; a call of setattr, delattr, __setattr__ or __delattr__ whose first or second argument is
    # the name or attribute as a string constant, or the code, globals and so on as a string constant
    # with a check as above; and a call of update, setdefault, pop, __setitem__ or __delitem__ that
    # names it as a keyword, as a string constant first argument, or as a constant key of a dictionary
    # display first argument. No check that runs from this file holds against all code of this file:
    # that code runs in the test process, so it can edit this case, what it starts or how it reads the
    # result, and it can defeat the scan by any route that the scan does not model, so of bindings the
    # case shows only that the file holds none of the forms above. Routes that defeat it include a
    # store through the module object of this file (sys.modules[__name__].ENUM_PROGRAMS = ...),
    # setattr(json, "loads", ...) or setattr(sys, "executable", ...), whose attribute is not 1 that the
    # scan names, a store through another name for a module (import json under another name, then a
    # store of its loads), a store into the dictionary of a module (json.__dict__["loads"] = ...), and
    # a __getattribute__ of a case class that gives write_registry another value on its instances:
    # each, scoped to 1 case, passes both pins while write_registry, as that case reaches it, accepts a
    # program outside ENUM_PROGRAMS or an argv[0] other than the interpreter's own path. So do a
    # binding that names its target only at run time (a name built from parts, a variable passed to
    # setattr, exec or eval of a built string, a mapping built elsewhere), a store through an alias of
    # a check (another name bound to the function) and native code. Neither pin sees an edit made to
    # PIN_PROGRAM or to the pin together with the code.
    PIN_PROGRAM = r'''
import ast, hashlib, sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    tree = ast.parse(fh.read(), path)
found = []


def finish():
    for text in found:
        print("pin: " + text)
    print("pin: {} defect(s)".format(len(found)))
    sys.exit(1 if found else 0)


def single(body, kind, name):
    hits = [node for node in body if isinstance(node, kind) and (
        node.name == name if kind is not ast.Assign else len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name)]
    if len(hits) != 1:
        found.append("{} has {} definition(s) at its level".format(name, len(hits)))
        return None
    return hits[0]


harness = single(tree.body, ast.ClassDef, "Stage2Harness")
bounds = single(tree.body, ast.ClassDef, "EnumeratorBounds")
if harness is None or bounds is None:
    finish()
pin = {}
for name in ("PINNED_CHECKS", "PINNED_MODULES", "PINNED_BUILTINS", "PINNED_VALUES", "ENUM_RUN_MARK_SHA256",
             "ENUM_PROGRAMS_SHA256"):
    node = single(bounds.body, ast.Assign, name)
    pin[name] = None if node is None else ast.literal_eval(node.value)
if found:
    finish()
CHECKS = [name for name, _parameters, _body in pin["PINNED_CHECKS"]]
VALUES = ["ENUM_RUNS_VAR", "ENUM_RUN_MARK", "ENUM_FIXTURE", "WRITING_ENUM_FIXTURE", "SLEEPING_ENUM_FIXTURE",
          "ENUM_PROGRAMS", "ENUM_TIMEOUT"]
MODULES = list(pin["PINNED_MODULES"]) + ["unittest"]
NAMES = set(CHECKS) | set(VALUES) | set(MODULES) | set(pin["PINNED_BUILTINS"]) | {"Stage2Harness", "fail"}
ATTRIBUTES = {"write_registry", "fail"}
FUNCTION_ATTRIBUTES = {"__code__", "__globals__", "__closure__", "__defaults__", "__kwdefaults__",
                       "__dict__", "__wrapped__"}
definitions = {name: single(harness.body if name == "write_registry" else tree.body, ast.FunctionDef, name)
               for name in CHECKS}
values = {name: single(tree.body, ast.Assign, name) for name in VALUES}
imports = {}
for node in tree.body:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname is None and alias.name in MODULES:
                imports.setdefault(alias.name, []).append(alias)
for module in MODULES:
    if len(imports.get(module, [])) != 1:
        found.append("{} has {} import(s) at module level".format(module, len(imports.get(module, []))))
allowed = {id(node) for node in definitions.values() if node is not None}
allowed |= {id(node.targets[0]) for node in values.values() if node is not None}
allowed |= {id(alias) for aliases in imports.values() for alias in aliases} | {id(harness)}

# The bodies of PINNED_CHECKS, as the in-process pin compares them.
for name, parameters, body in pin["PINNED_CHECKS"]:
    node = definitions[name]
    if node is None:
        continue
    if node.decorator_list:
        found.append("{} is decorated".format(name))
    if ast.dump(node.args) != ast.dump(ast.parse("def f({}):\n    pass\n".format(parameters)).body[0].args):
        found.append("{} has other parameters".format(name))
    if [ast.dump(statement) for statement in node.body[1:]] != [ast.dump(statement)
                                                                 for statement in ast.parse(body).body]:
        found.append("{} is not as PINNED_CHECKS holds it".format(name))

# Each binding of a name or attribute that the path reads, other than its 1 definition.
def where(node, text):
    found.append("line {}: {}".format(getattr(node, "lineno", "?"), text))


def checked(node):
    return (isinstance(node, ast.Name) and node.id in CHECKS) or (
        isinstance(node, ast.Attribute) and node.attr in ATTRIBUTES)


def constant(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


binders = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler, ast.MatchAs, ast.MatchStar)
type_parameters = tuple(getattr(ast, kind) for kind in ("TypeVar", "ParamSpec", "TypeVarTuple")
                        if hasattr(ast, kind))
for node in ast.walk(tree):
    if id(node) in allowed:
        continue
    if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load) and node.id in NAMES:
        where(node, "binds " + node.id)
    elif isinstance(node, binders + type_parameters) and getattr(node, "name", None) in NAMES:
        where(node, "binds " + node.name)
    elif isinstance(node, ast.MatchMapping) and node.rest in NAMES:
        where(node, "binds " + node.rest)
    elif isinstance(node, ast.arg) and node.arg in NAMES:
        where(node, "binds the parameter " + node.arg)
    elif isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) in NAMES:
        where(node, "imports " + (node.asname or node.name))
    elif isinstance(node, (ast.Global, ast.Nonlocal)) and set(node.names) & NAMES:
        where(node, "declares " + ", ".join(sorted(set(node.names) & NAMES)))
    elif isinstance(node, ast.Attribute) and not isinstance(node.ctx, ast.Load) and (
            node.attr in ATTRIBUTES or (node.attr in FUNCTION_ATTRIBUTES and checked(node.value))
            or (isinstance(node.value, ast.Name) and node.value.id in MODULES)):
        where(node, "stores the attribute " + node.attr)
    elif isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Load) and (
            constant(node.slice) in NAMES | ATTRIBUTES):
        where(node, "stores the key " + constant(node.slice))
    elif isinstance(node, ast.Call):
        callee = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else None)
        texts = [constant(argument) for argument in node.args[:2]]
        if callee in ("setattr", "delattr", "__setattr__", "__delattr__") and (
                set(texts) & (NAMES | ATTRIBUTES) or (set(texts) & FUNCTION_ATTRIBUTES
                                                      and any(checked(a) for a in node.args[:2]))):
            where(node, "calls {} naming {}".format(callee, ", ".join(sorted(
                set(texts) & (NAMES | ATTRIBUTES | FUNCTION_ATTRIBUTES)))))
        elif callee in ("update", "setdefault", "pop", "__setitem__", "__delitem__"):
            keys = {keyword.arg for keyword in node.keywords} | set(texts[:1])
            for argument in node.args[:1]:
                if isinstance(argument, ast.Dict):
                    keys |= {constant(key) for key in argument.keys if key is not None}
            if keys & (NAMES | ATTRIBUTES):
                where(node, "calls {} naming {}".format(
                    callee, ", ".join(sorted(keys & (NAMES | ATTRIBUTES)))))

# The values, run alone with no builtins, and the pinned checks, compiled with those values, the
# modules of PINNED_MODULES and the builtins of this process.
namespace = {"__builtins__": {}}
try:
    for name in VALUES:
        if values[name] is not None:
            exec(compile(ast.Module(body=[values[name]], type_ignores=[]), path, "exec", dont_inherit=True),
                 namespace)
except Exception as exc:
    found.append("the values do not run alone: {!r}".format(exc))
    finish()
for name, value in pin["PINNED_VALUES"]:
    if type(namespace.get(name)) is not type(value) or namespace.get(name) != value:
        found.append("{} is not as pinned".format(name))
mark, programs = namespace.get("ENUM_RUN_MARK"), namespace.get("ENUM_PROGRAMS")
if type(mark) is not str or hashlib.sha256(mark.encode("utf-8")).hexdigest() != pin["ENUM_RUN_MARK_SHA256"]:
    found.append("ENUM_RUN_MARK is not as pinned")
if type(programs) is not tuple or not all(type(program) is str for program in programs) or tuple(
        hashlib.sha256(program.encode("utf-8")).hexdigest()
        for program in programs) != pin["ENUM_PROGRAMS_SHA256"]:
    found.append("ENUM_PROGRAMS is not its 3 reviewed programs")
if found:
    finish()
run = {name: namespace[name] for name in VALUES}
run.update({module: __import__(module) for module in pin["PINNED_MODULES"]})
module = ast.Module(body=[definitions[name] for name in CHECKS if name != "write_registry"], type_ignores=[])
exec(compile(module, path, "exec", dont_inherit=True), run)
for program in programs:
    argv = [sys.executable, "-I", "-c", program]
    if not (run["runs_enum_run_mark_first"](program) and run["program_leaves_record"](program)
            and run["declared_enumerator_defect"]({"argv": argv, "timeout": run["ENUM_TIMEOUT"]}) is None):
        found.append("a program of ENUM_PROGRAMS is refused")
    if run["declared_enumerator_defect"]({"argv": argv, "timeout": run["ENUM_TIMEOUT"] + 1}) is None:
        found.append("a timeout over ENUM_TIMEOUT is accepted")
if run["declared_enumerator_defect"]({"argv": [sys.executable, "-I", "-c", programs[0] + "pass\n"]}) is None:
    found.append("a 4th program is accepted")
finish()
'''

    def test_the_pin_holds_in_a_fresh_interpreter(self):
        result = run_doctor_recorded(self, [sys.executable, "-I", "-c", self.PIN_PROGRAM,
                                            str(Path(__file__).resolve())],
                                     capture_output=True, text=True, timeout=RUN_TIMEOUT)
        self.assertEqual((result.returncode, result.stdout), (0, "pin: 0 defect(s)\n"), result.stderr)

    @staticmethod
    def near_misses(value):
        """Values that differ from value, generated from it: for each position, value without that
        character, with that character's code point with its lowest bit flipped, with that character's
        case swapped, with a space before that character, and, when that character is 1 of "!" to "~"
        (the printable ASCII characters other than the space), with that character in its full-width
        form, its code point plus 0xFEE0; value with a space after it; value upper-cased, lower-cased
        and case-swapped; and value with a space, a tab, a line feed, a carriage return and a line
        feed, a vertical tab, a form feed or a no-break space before it, after it, and both. Each is
        non-empty and differs from value. So a check that compares a part of the value, strips or folds
        it, or normalizes its characters accepts at least 1 of them."""
        found = []
        for i, char in enumerate(value):
            head, tail = value[:i], value[i + 1:]
            found += [head + tail, head + chr(ord(char) ^ 1) + tail, head + char.swapcase() + tail,
                      head + " " + char + tail]
            if "!" <= char <= "~":
                found.append(head + chr(ord(char) + 0xFEE0) + tail)
        found += [value + " ", value.upper(), value.lower(), value.swapcase()]
        for space in (" ", "\t", "\n", "\r\n", "\v", "\f", "\xa0"):
            found += [space + value, value + space, space + value + space]
        return [near for near in dict.fromkeys(found) if near and near != value]

    def test_write_registry_refuses_every_generated_near_miss(self):
        # For each of the interpreter, -I, -c and each program of ENUM_PROGRAMS, write_registry refuses
        # every value that near_misses generates from it, and for the interpreter each of the 5 paths
        # below that differs from sys.executable and names the same file. The values are generated, not
        # chosen for 1 loosening, but they are finite: a check that accepted some other value would pass
        # this case.
        directory, name = os.path.split(sys.executable)
        aliases = [os.path.join(directory, ".", name), directory + "//" + name,
                   os.path.join(directory, "..", os.path.basename(directory), name),
                   os.path.realpath(sys.executable), os.path.relpath(sys.executable)]
        aliases = [alias for alias in aliases
                   if alias != sys.executable and os.path.samefile(alias, sys.executable)]
        self.assertGreaterEqual(len(aliases), 2, "precondition: at least 2 other paths name this interpreter")
        accepted, tried = [], 0
        for program in ENUM_PROGRAMS:
            fixture = [sys.executable, "-I", "-c", program, str(self.backlog)]
            self.write_registry(self.stage2(enumerator={"argv": fixture, "timeout": ENUM_TIMEOUT}))
            elements = [(3, [near for near in self.near_misses(program) if near not in ENUM_PROGRAMS])]
            if program is ENUM_FIXTURE:
                elements += [(0, self.near_misses(sys.executable) + aliases), (1, self.near_misses("-I")),
                             (2, self.near_misses("-c"))]
            for position, values in elements:
                for value in values:
                    argv = list(fixture)
                    argv[position] = value
                    tried += 1
                    try:
                        self.write_registry(self.stage2(enumerator={"argv": argv, "timeout": ENUM_TIMEOUT}))
                    except self.failureException as refusal:
                        if self.REFUSED not in str(refusal):
                            accepted.append((position, value, str(refusal)))
                    else:
                        accepted.append((position, value))
        self.assertGreater(tried, 1000, "precondition: the near misses were generated")
        self.assertEqual(accepted, [], "write_registry accepted a near miss")

    def test_write_registry_refuses_every_program_file(self):
        # What the interpreter runs for a file operand depends on the operand's name and content, on how
        # the path resolves, and on the file at each run, so write_registry refuses every program file
        # in an enumerator that the hook would start.
        # Each row has a recording program file in place, so a check that read that file would accept
        # it, and the refusal is of the form, not of the file. The rows are the forms found so far: a
        # plain file, a relative file under the root, an option word (-u, -- or -) in the operand
        # position, a directory, a .pyc name and a trailing slash.
        recording = self.repo / "enum_recording.py"
        pyc = self.repo / "enum_recording.pyc"
        package = self.repo / "enum_package"
        package.mkdir()
        for path in (recording, pyc, package / "__main__.py"):
            path.write_text(ENUM_FIXTURE, encoding="utf-8")
            self.assertTrue(runs_enum_run_mark_first(path.read_text(encoding="utf-8")),
                            "precondition: {} records its runs".format(path.name))
        rest = [str(self.backlog)]
        rows = (("a plain recording program file", [str(recording)] + rest),
                ("a relative recording program file under the root", [recording.name] + rest),
                ("-u before a recording program file", ["-u", str(recording)] + rest),
                ("-- before a recording program file", ["--", str(recording)] + rest),
                ("- before a recording program file", ["-", str(recording)] + rest),
                ("a directory that holds a recording __main__.py", [str(package)] + rest),
                ("a recording source file with a .pyc name", [str(pyc)] + rest),
                ("a recording program file with a trailing slash", [str(recording) + "/"] + rest))
        for name, operands in rows:
            with self.subTest(enumerator=name):
                with self.assertRaisesRegex(self.failureException, self.REFUSED):
                    self.write_registry(self.stage2(enumerator={
                        "argv": [sys.executable, "-I"] + operands, "timeout": ENUM_TIMEOUT}))


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
                r = run_doctor_recorded(self, [sys.executable, "-I", str(copy), "preflight", kind,
                                               "--root", str(self.repo)],
                                        capture_output=True, text=True, env=self._env(), timeout=RUN_TIMEOUT)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("judged verdict: DENY", r.stdout)
                self.assertIn("verdict without the escape sentinel: DENY", r.stdout)
                self.assertIn("vanished from the enumeration without a close receipt", r.stdout)
        self.assertEqual(self._bytecode_under(fresh), [], "preflight wrote a bytecode cache")
        self.assertEqual(tree_state(self._tmp), before, "preflight changed a file or directory")

    # --- a declared read path that is not a regular file is cannot-evaluate, before any hook reader
    # A preflight under this bound can run the stage-2 enumerator, so the bound is RUN_TIMEOUT.
    SPECIAL_TIMEOUT = RUN_TIMEOUT

    def _doctor_bounded(self, *args):
        try:
            return run_doctor_recorded(self, [sys.executable, "-I", str(DOCTOR), *args, "--root",
                                              str(self.repo)],
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

    def _assert_special_refused(self, site, label, path, kind, *doctor_args):
        # The report must word the refusal at site exactly (assert_refusal), as the hook opens these
        # paths in different ways (PRECHECK_OPENS).
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(reg)
        self.set_items([item("42")])
        named = self._make_special(path, kind)
        before = tree_state(self._tmp)
        r = self._doctor_bounded(*doctor_args)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        assert_refusal(self, r.stdout, site, "declared " + label, path, named)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(marker.exists(), "the enumerator ran")
        self.assertFalse(self.state_dir().exists(), "a hook state write happened")
        self.assertEqual(tree_state(self._tmp), before, "the doctor changed a file or directory")
        return r

    def test_preflight_special_mode_path_is_cannot_evaluate(self):
        # No lease, so scope falls through to the mode read (`_orch_mode` at
        # aiqt_hooks.py:22654, then `os.open` with O_NONBLOCK at 22445); the doctor refuses each
        # special file there as cannot-evaluate, and its report says that the hook's reader would
        # not block on it, never that the hook would open it with a blocking open.
        for kind in ("fifo", "directory", "symlink-to-fifo"):
            with self.subTest(kind=kind):
                self.tearDown()
                self.setUp()
                r = self._assert_special_refused("scope.mode", "mode.path",
                                                 self._p("operating-mode.md"), kind, "preflight", "stop")
                self.assertNotIn("blocking open", r.stdout)

    def test_preflight_special_lease_path_is_cannot_evaluate(self):
        # The hook opens the lease only for holder scoping, on a lease that os.stat reaches, that is
        # non-empty and fresh, and with a session id given (aiqt_hooks.py:22617-22641). A FIFO has size 0
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
        assert_refusal(self, r.stdout, "scope.lease", "declared lease.path", lease, "directory")
        self.assertFalse(marker.exists(), "the enumerator ran")
        self.assertEqual(tree_state(self._tmp), before, "the doctor changed a file or directory")

    def test_preflight_idle_special_mode_path_is_cannot_evaluate(self):
        self._assert_special_refused("scope.mode", "mode.path", self._p("operating-mode.md"), "fifo",
                                     "preflight", "idle")

    def test_preflight_special_backlog_operand_is_cannot_evaluate(self):
        # The hook runs the enumerator (`subprocess.run` at aiqt_hooks.py:22833), which takes the
        # backlog as an operand; the hook itself never opens it, so the refusal names no hook reader.
        self._assert_special_refused("ctx.enumerator_operand", "enumerator.argv[4]", str(self.backlog),
                                     "fifo", "preflight", "stop")

    def test_preflight_special_file_at_the_c_option_is_cannot_evaluate(self):
        # The doctor checks each element of the argv from argv[2] on as an operand path
        # (_ctx_read_paths, orch_doctor.py:623-625), as for a committed registry, whose argv[2] the
        # registry gate requires to be a script (check-orchestration-registry.py:589-591). So for the
        # -c registries of this suite it also checks <root>/-c, and refuses a special file there,
        # running no enumerator, where the hook runs the enumerator. This case pins that refusal.
        self._assert_special_refused("ctx.enumerator_operand", "enumerator.argv[2]", str(self.repo / "-c"),
                                     "directory", "preflight", "stop")
        marker = self._tmp / "enumerator-ran.txt"
        self.arm_lease()
        r = self.stop()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("42 (42: no blocker recorded)", r.stderr)
        self.assertTrue(marker.exists(), "the hook did not run the enumerator")

    def test_resume_audit_special_handoff_is_cannot_evaluate(self):
        # The resume probes read the declared handoff
        # (`_orch_record_surface_read` at aiqt_hooks.py:32760), which opens it with
        # O_NONBLOCK (32703); the doctor refuses a FIFO there as cannot-evaluate, and its report says
        # that the hook would not block on it, never that it would open it with a blocking open.
        r = self._assert_special_refused("audit.handoff", "record.handoff", self._p("session-handoff.md"),
                                         "fifo", "--resume-audit")
        self.assertNotIn("blocking open", r.stdout)

    # --- the fixed hook state files are checked too, per command -----------------------
    # The state files _orch_build_ctx opens with a plain blocking open (turn-state.json at
    # aiqt_hooks.py:22346, dispatch-ledger.jsonl at 22857-22858 and `_orch_read_jsonl` at 22173,
    # backlog-checkpoint.json at 23324, and with attestations declared attestations-validated.json at
    # 22934 and guard-events.jsonl at 33020).
    PREFLIGHT_STATE_FILES = ("turn-state.json", "dispatch-ledger.jsonl", "backlog-checkpoint.json",
                             "attestations-validated.json", "guard-events.jsonl")
    # The state files orch_resume_audit opens with a plain blocking open (guard-events.jsonl at 33020 and
    # `_orch_append_jsonl` at 22162, escape-spoof.json at 33212, forced-exit.jsonl at 33160 and
    # `_orch_read_jsonl` at 22173, and forced-exit-surfaced.json at 33172). Its rewrites open no fixed
    # temporary path: _orch_write_json_atomic, via 33191 and, with attestations declared, via 33124,
    # names a new random <name>.<16 hex>.tmp at 22266 and opens it at 22267-22268, so the doctor
    # checks neither old fixed path (test_resume_audit_ignores_the_old_fixed_temporary_paths).
    AUDIT_STATE_FILES = ("guard-events.jsonl", "escape-spoof.json", "forced-exit.jsonl",
                         "forced-exit-surfaced.json")

    def _with_attestations(self, reg):
        # A declared attestations register, absent on disk (an open the hook raises on, never blocks
        # on): the condition the hook tests before it opens the attestation state files
        # (`reg.get("attestations")` at aiqt_hooks.py:22929-22931 for the preview,
        # `at_path` at 33092-33094 for the audit).
        reg["attestations"] = self._p("attestations.jsonl")
        return reg

    def _make_state_fifo(self, name):
        self.state_dir().mkdir(parents=True, exist_ok=True)
        path = self.state_dir() / name
        os.mkfifo(path)
        return path

    def _seed_reach(self, name, command):
        # Seed the state the hook needs to reach the open of name. The preview reads
        # guard-events.jsonl only past a snapshot open (`_orch_attestation_refs` at
        # aiqt_hooks.py:22934-22937) and a register open (`_orch_register_authority` at 32921-32924);
        # the audit opens the surfaced set only for a forced-exit log that holds rows
        # (`_orch_forced_exit_findings` at 33160-33169).
        if command == "preflight" and name == "guard-events.jsonl":
            self.seed_state("attestations-validated.json", {})
            Path(self._p("attestations.jsonl")).write_text("", encoding="utf-8")
        if command == "--resume-audit" and name.startswith("forced-exit-surfaced.json"):
            self.seed_ledger_like("forced-exit.jsonl", [{"key": "k1", "ts": _iso(), "open_ids": ["42"]}])

    def seed_ledger_like(self, name, rows):
        sd = self.state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        (sd / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    # The pre-check site of each state file, by command.
    STATE_FILE_SITES = {
        ("preflight", "turn-state.json"): "ctx.turn_state",
        ("preflight", "dispatch-ledger.jsonl"): "ctx.ledger",
        ("preflight", "backlog-checkpoint.json"): "ctx.checkpoint",
        ("preflight", "attestations-validated.json"): "ctx.attestation_snapshot",
        ("preflight", "guard-events.jsonl"): "ctx.guard_events",
        ("--resume-audit", "guard-events.jsonl"): "audit.guard_events",
        ("--resume-audit", "escape-spoof.json"): "audit.escape_spoof",
        ("--resume-audit", "forced-exit.jsonl"): "audit.forced_exit",
        ("--resume-audit", "forced-exit-surfaced.json"): "audit.forced_exit_surfaced",
    }

    def _assert_state_special_refused(self, name, *doctor_args):
        reg, marker = self._arm_writing_enumerator()
        self.write_registry(self._with_attestations(reg))
        self.set_items([item("42")])
        self._seed_reach(name, doctor_args[0])
        path = self._make_state_fifo(name)
        before = tree_state(self._tmp)
        r = self._doctor_bounded(*doctor_args)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        assert_refusal(self, r.stdout, self.STATE_FILE_SITES[(doctor_args[0], name)],
                       "hook state file " + name, path, "FIFO")
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

    def test_resume_audit_ignores_the_old_fixed_temporary_paths(self):
        # Contrast: the hook's _orch_write_json_atomic opens a new random <name>.<16 hex>.tmp with
        # O_EXCL (aiqt_hooks.py:22267-22268), via 33124 for the attestation snapshot and via 33191
        # for the surfaced set, so a FIFO at the old fixed attestations-validated.json.tmp or
        # forced-exit-surfaced.json.tmp neither blocks the audit nor makes the doctor refuse it.
        for name in ("attestations-validated.json.tmp", "forced-exit-surfaced.json.tmp"):
            with self.subTest(name=name):
                self.tearDown()
                self.setUp()
                reg, _marker = self._arm_writing_enumerator()
                self.write_registry(self._with_attestations(reg))
                self.set_items([item("42")])
                self._seed_reach("forced-exit-surfaced.json", "--resume-audit")
                path = self._make_state_fifo(name)
                r = self._doctor_bounded("--resume-audit")
                self.assertNotEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("cannot evaluate", r.stdout)
                self.assertNotIn("Traceback", r.stderr)
                h = self.run_hook("orch_resume_audit", {})
                self.assertEqual(h.returncode, 0, h.stdout + h.stderr)
                self.assertTrue(path.is_fifo(), "the hook left the old fixed entry alone")

    def test_resume_audit_on_an_unreadable_registry_checks_its_state_files(self):
        # On an unreadable registry the hook appends to resume-barrier.json.unused beside the barrier
        # (`_orch_append_jsonl` at aiqt_hooks.py:33317, `open(path, "a"` at 22162) under the default
        # state directory (`_orch_state_dir_for_root` at 33315).
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
        assert_refusal(self, r.stdout, "audit_bad.unused", "hook state file resume-barrier.json.unused",
                       path, "FIFO")

    # --- each command checks only what its own hook call path opens --------------------
    def test_fifo_backlog_operand_refuses_preflight_but_not_the_resume_audit(self):
        # The resume probes run no enumerator (`_orch_resume_probes` at aiqt_hooks.py:32738-32822), so
        # the hook audits with a FIFO backlog operand, and so must the doctor; the preview runs the
        # enumerator (`subprocess.run` at 22833), so it still refuses.
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
        assert_refusal(self, p.stdout, "ctx.enumerator_operand", "declared enumerator.argv[4]",
                       self.backlog, "FIFO")
        self.assertFalse(marker.exists(), "the refused preview ran the enumerator")

    def test_resume_audit_runs_past_paths_only_the_preview_opens(self):
        # The audit stats the lease only (`os.stat` at aiqt_hooks.py:32800) and never opens the mode
        # record or the preview state files, so a FIFO at any of them leaves the audit to run and
        # rewrite the barrier.
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
        # Out of scope the hook returns before _orch_build_ctx (`_orch_scope_live` at
        # aiqt_hooks.py:23577-23579 and 23684-23686), so it never opens turn-state.json, and the
        # preview reports the same ALLOW.
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
        # The hook reads the registry with a non-blocking open (O_NONBLOCK at aiqt_hooks.py:22096,
        # `os.open` at 22098, in `_orch_registry` at 22084-22121) and reads a file that is not regular
        # as a bad registry (22102-22103), the machine-local file first (`_ORCH_REGISTRY_FILES` at
        # aiqt_hooks.py:21652); the doctor refuses a special file there before it calls that reader.
        self.write_registry(self.stage2())
        local = self.repo / ".aiqt" / "orchestration.local.json"
        os.mkfifo(local)
        for args in (("preflight", "stop"), ("--resume-audit",)):
            with self.subTest(args=args):
                r = self._doctor_bounded(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                assert_refusal(self, r.stdout, "registry.file", "registry file", local, "FIFO")
                self.assertNotIn("blocking open", r.stdout)
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

    # --- the doctor decides scope first and, out of scope, runs no enumerator ----------------
    def _arm_writing_enumerator(self, **overrides):
        marker = self._tmp / "enumerator-ran.txt"
        reg = self.stage2(enumerator={
            "argv": [sys.executable, "-I", "-c", WRITING_ENUM_FIXTURE, str(self.backlog), str(marker)],
            "timeout": ENUM_TIMEOUT}, **overrides)
        return reg, marker

    def test_preflight_out_of_scope_runs_no_enumerator(self):
        # The Stop hook returns before it enumerates when scope is not live (`_orch_scope_live` at
        # aiqt_hooks.py:23577-23579), and so does the scheduling hook (`_orch_scope_live` at
        # aiqt_hooks.py:23684-23686); a preview that ran the enumerator there could change what a later
        # Stop decides.
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
                self.assertIn(NOT_RUN_WRITES, r.stdout.split("\n"))
                self.assertIn("effective verdict: ALLOW", r.stdout)
                self.assertFalse(marker.exists(), "an out-of-scope preflight ran the enumerator")

    def test_preflight_idle_out_of_the_roster_runs_no_enumerator(self):
        # The scheduling hook returns before it enumerates for a tool outside the roster
        # (`reg.get("yield_tools")` at aiqt_hooks.py:23688-23690).
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
        self.assertIn(NOT_RUN_WRITES, r.stdout.split("\n"))
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
        probe = run_doctor_recorded(self, [sys.executable, str(tooldir / "probe.py")], capture_output=True,
                                    text=True, env=env, timeout=60)
        self.assertEqual(probe.returncode, 97, "precondition: the planted module shadows json")
        self.write_registry(self.stage2())
        self.arm_lease()
        self.set_items([item("1", state="closed")])
        r = run_doctor_recorded(self, [sys.executable, str(copy), "preflight", "stop", "--root",
                                       str(self.repo)],
                                capture_output=True, text=True, env=env, timeout=RUN_TIMEOUT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("effective verdict: ALLOW", r.stdout)

    def test_a_failed_reexecution_exits_2_with_a_message(self):
        missing = self._tmp / "no-such-python"
        self.assertFalse(missing.exists(), "precondition: the interpreter path is absent")
        env = self._env()
        env.pop("PYTHONSAFEPATH", None)
        r = run_doctor_recorded(self, [sys.executable, "-c", FAILED_REEXEC_PROG, str(DOCTOR), str(missing)],
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

    def test_resume_audit_rewrite_takes_a_new_file_mode_today(self):
        # The vendored barrier writer creates a temporary file and replaces the barrier with it
        # (`open(tmp, "x"` at aiqt_hooks.py:33251, `os.replace` at 33256), so the barrier takes the
        # mode of a new file in the state folder, not the mode of the file it replaces: 0o666 less
        # the umask, or, where the folder has a default ACL, the mode that the ACL gives a new file,
        # as .aiqt/config.md states. Without such an ACL, a barrier restricted to 0o600 is 0o644
        # after an audit under umask 0o022. The host's TMPDIR can pass a default ACL down to the
        # temporary folder, so this case expects the mode of a fresh file that it creates the
        # same way in the same folder under the same umask, not a literal mode. It restricts the
        # barrier to 0o600, or to 0o400 where a fresh file is 0o600, so the 2 modes always differ.
        # This case goes red once a re-vendored hook keeps the mode; .aiqt/config.md and this case
        # then change with it.
        self.write_registry(self.stage2())
        self.arm_lease()
        self.seed_state("resume-barrier.json", {"active": True, "findings": ["seeded"],
                                                "ts": _iso(), "warned": False})
        barrier = self.state_dir() / "resume-barrier.json"
        probe = self.state_dir() / "fresh-file-mode-probe"
        old = os.umask(0o022)
        try:
            with open(probe, "x", encoding="utf-8"):
                pass
            fresh = os.stat(probe).st_mode & 0o777
            probe.unlink()
            restricted = 0o400 if fresh == 0o600 else 0o600
            os.chmod(barrier, restricted)
            self.assertEqual(os.stat(barrier).st_mode & 0o777, restricted, "precondition: a restricted barrier")
            r = self.run_hook("orch_resume_audit", {})
        finally:
            os.umask(old)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.state_json("resume-barrier.json")["active"], "the audit rewrote the barrier")
        self.assertEqual(os.stat(barrier).st_mode & 0o777, fresh,
                         "the barrier keeps mode {:o}, not the mode of a new file".format(restricted))

    def test_usage_error(self):
        r = run_doctor_recorded(self, [sys.executable, "-I", str(DOCTOR)], capture_output=True, text=True,
                                env=self._env(), timeout=60)
        self.assertEqual(r.returncode, 2)

    # --- the doctor writes nothing itself; the declared enumerator runs as the hook runs it ---
    def test_preflight_discloses_that_the_declared_enumerator_runs(self):
        self.assertIn("mark.write", WRITING_ENUM_FIXTURE, "precondition: the fixture writes")
        marker = self._tmp / "enumerator-ran.txt"
        self.write_registry(self.stage2(enumerator={
            "argv": [sys.executable, "-I", "-c", WRITING_ENUM_FIXTURE, str(self.backlog), str(marker)],
            "timeout": ENUM_TIMEOUT}))
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
        # (`_orch_record_denial` at aiqt_hooks.py:23591-23597).
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

    def test_preflight_stop_with_a_read_only_turn_state_reports_the_deny_as_the_hook_does(self):
        # The hook saves turn-state.json through its atomic writer, which replaces the file from a
        # temporary file in the state directory and never opens the target (aiqt_hooks.py:22362,
        # `os.replace` at :22287), so a mode-0444 turn-state.json in a writable state
        # directory does not stop the save: the hook denies, and the doctor must predict the saved
        # counter and the DENY on the same state. The fail-open leg of the same check, a state
        # directory the hook cannot write, is the case above; together they hold the doctor's
        # counter-save answer to the hook's verdict on both sides.
        self._arm_actionable_stop()
        self.seed_state("turn-state.json", {})
        os.chmod(self.state_dir() / "turn-state.json", 0o444)
        before = tree_state(self._tmp)
        r = self.run_doctor("preflight", "stop")
        self.assertEqual(tree_state(self._tmp), before, "preflight changed a file or directory")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("judged verdict: DENY", r.stdout)
        self.assertIn("denial counter: could be saved", r.stdout)
        self.assertIn("effective verdict: DENY", r.stdout)
        h = self.stop()
        self.assertEqual(h.returncode, 2, h.stdout + h.stderr)
        self.assertEqual(self.state_json("turn-state.json")["stop_denials"], 1,
                         "the hook saved the counter over the read-only file")

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

    # --- the help text says what preflight writes, and what it runs -------------------------
    def test_help_text_says_the_doctor_writes_nothing_and_the_enumerator_runs(self):
        r = run_doctor_recorded(self, [sys.executable, "-I", str(DOCTOR), "--help"], capture_output=True,
                                text=True, env=self._env(), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = " ".join(r.stdout.split())
        self.assertIn("the doctor itself writes nothing", text)
        self.assertIn("the declared enumerator runs as the hook runs it", text)
        self.assertNotIn("without writing anything", text)

    # --- the resume audit requires that the hook rewrote the barrier during this run ---------
    def _read_only_stale_barrier(self, active):
        # The hook replaces the barrier from a temporary file in the state directory
        # (aiqt_hooks.py:33229-33260), so a read-only barrier file no longer stops the rewrite; a
        # state directory the hook cannot write does. The doctor's check is unchanged: a barrier
        # this audit did not rewrite is reported as unverified, never as the stale state it holds.
        self.seed_state("resume-barrier.json", {"active": active,
                                                "findings": ["seeded"] if active else [],
                                                "ts": _iso(-48), "warned": False})
        path = self.state_dir() / "resume-barrier.json"
        os.chmod(self.state_dir(), 0o555)
        return path, path.read_bytes()

    @staticmethod
    def _not_rewritten(path):
        # The whole line with which the resume audit refuses a barrier that it did not rewrite.
        return ("barrier: NOT rewritten by this audit ({} has the same mtime and content as before the run); "
                "the hook could not replace it (for example its state directory cannot be written), so the "
                "state it holds is stale and the audit result is unverified".format(path))

    def test_resume_audit_read_only_stale_clear_barrier_is_unverified(self):
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0555 directory, so the read-only case cannot "
                          "arise")
        self.write_registry(self.stage2())
        self.arm_lease()
        self.write_record_files(handoff="Branch: some-other-branch\n")  # a real audit would arm
        path, before = self._read_only_stale_barrier(False)
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        assert_barrier_refusal(self, r.stdout, path, line=self._not_rewritten(path))
        self.assertNotIn("barrier: clear", r.stdout)
        self.assertEqual(path.read_bytes(), before, "precondition: the hook could not rewrite it")

    def test_resume_audit_read_only_stale_active_barrier_is_unverified(self):
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0555 directory, so the read-only case cannot "
                          "arise")
        self.write_registry(self.stage2())
        self.arm_lease()
        path, before = self._read_only_stale_barrier(True)
        r = self.run_doctor("--resume-audit")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        assert_barrier_refusal(self, r.stdout, path, line=self._not_rewritten(path))
        self.assertEqual(path.read_bytes(), before)

    def test_resume_audit_rewrite_with_a_ts_outside_the_run_is_unverified(self):
        self.write_registry(self.stage2())
        self.arm_lease()
        start = _now()
        r = run_doctor_recorded(self, [sys.executable, "-I", "-c", STALE_TS_PROG, str(DOCTOR),
                                       str(self.repo)],
                                capture_output=True, text=True, env=self._env(), timeout=120)
        end = _now()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        # The line names the times of the audit run, which the case reads back and bounds by its own.
        stale = re.compile(r"barrier: its ts '2000-01-01T00:00:00\+00:00' is not from this audit run \((\S+) "
                           r"to (\S+)\); it was not rewritten by this audit, so the audit result is "
                           r"unverified")
        assert_barrier_refusal(self, r.stdout, "resume-barrier.json", line=stale)
        times = [datetime.fromisoformat(found) for found in stale.search(r.stdout).groups()]
        self.assertTrue(start <= times[0] <= times[1] <= end, times)
        self.assertFalse(self.state_json("resume-barrier.json")["active"],
                         "precondition: the barrier was rewritten, and reads clear")

    def test_resume_audit_refuses_a_barrier_that_it_cannot_read_back(self):
        # A stand-in for the hook's audit (AUDIT_LEAVES_PROG) leaves no barrier, a barrier that is not
        # JSON, or a fresh barrier whose active is not a boolean; each refusal is checked whole.
        self.write_registry(self.stage2())
        self.arm_lease()
        path = self.state_dir() / "resume-barrier.json"
        try:
            json.loads("not json\n")
        except ValueError as exc:
            not_json = str(exc)
        unread = "barrier: cannot be read back from {} ({}); the audit result is unverified"
        for leaves, line in (("absent", unread.format(path, "absent")),
                             ("not-json", unread.format(path, not_json)),
                             ("malformed", "barrier: malformed at {}; the audit result is unverified"
                                           .format(path))):
            with self.subTest(leaves=leaves):
                path.unlink(missing_ok=True)
                r = run_doctor_recorded(self, [sys.executable, "-I", "-c", AUDIT_LEAVES_PROG, str(DOCTOR),
                                               str(self.repo), leaves],
                                        capture_output=True, text=True, env=self._env(), timeout=120)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                assert_barrier_refusal(self, r.stdout, path, line=line)

    # --- the barrier is read only as a regular file, without blocking -------------------------
    BARRIER_TIMEOUT = 60

    def _audit_bounded(self):
        try:
            return run_doctor_recorded(self, [sys.executable, "-I", str(DOCTOR), "--resume-audit",
                                              "--root", str(self.repo)],
                                       capture_output=True, text=True, env=self._env(),
                                       timeout=self.BARRIER_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the doctor did not exit within {} s: the barrier open blocked"
                      .format(self.BARRIER_TIMEOUT))

    def _assert_barrier_refused(self, kind):
        r = self._audit_bounded()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        assert_barrier_refusal(self, r.stdout, self.state_dir() / "resume-barrier.json", kind)
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
# open is reached and the doctor must refuse. Line numbers cite
# plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py.
PRECHECK_SITES = {
    "registry.file": (
        "both", True,
        "the machine-local file always; the committed file only when the lstat of the local file "
        "raised FileNotFoundError (a present local file returns whatever its content, an lstat "
        "fault returns bad)",
        "_orch_registry 22084-22121: lstat 22087, next file 22088-22089, "
        "fault `cannot stat registry path` 22090-22095, os.open 22098, "
        "the read and returns after the open, through json.loads, 22099-22121; "
        "order _ORCH_REGISTRY_FILES 21652"),
    "scope.lease": (
        "preflight", True,
        "os.stat succeeds, the lease is non-empty and fresh, holder_is_session_id is set and a "
        "session id is given",
        "_orch_scope_live 22611-22645: stat 22617, size and freshness 22618-22632, holder 22633, "
        "session_id 22637-22638, open 22640"),
    "scope.mode": (
        "preflight", True,
        "no earlier return: not a live lease (st.st_size 22632-22649) and not an unstattable holder lease "
        "(22650-22652)",
        "_orch_scope_live 22654, _orch_mode_read os.open 22445"),
    "ctx.turn_state": (
        "preflight", True,
        "scope live (and for idle the tool in the roster); then always",
        "orch_stop_guard 23577-23579, orch_yield_tool 23684-23690; _orch_turn_state 22344-22346 via 23420"),
    "ctx.enumerator_operand": (
        "preflight", True,
        "the enumerator runs: an object with a non-empty argv of non-empty strings",
        "_orch_enumerate 22820-22829, subprocess 22833 via 23431"),
    "ctx.ledger": (
        "preflight", True,
        "the enumerator runs (its success is not modelled)",
        "_orch_build_ctx 23433-23434, _orch_live_ledger_ids 22857, open 22173"),
    "ctx.pending_decisions": (
        "preflight", True,
        "the enumerator runs and record.pending_decisions is declared",
        "_orch_build_ctx 23433-23436, _orch_pending_haystack 22902-22908"),
    "ctx.attestation_snapshot": (
        "preflight", True,
        "the enumerator runs and attestations is declared",
        "_orch_attestation_refs 22929-22935 via 23437"),
    "ctx.attestations": (
        "preflight", True,
        "as the snapshot, and os.stat succeeds on the snapshot (its content is not modelled)",
        "_orch_attestation_refs 22934-22937 return on a failed snapshot open; "
        "_orch_register_authority 32921 via 22947, _orch_chained_rows 32876 via 22954"),
    "ctx.attestations_anchor": (
        "preflight", True,
        "as the register, and os.stat succeeds on the register (git tracking is not modelled)",
        "_orch_register_authority 32921-32924 hold on a failed register open, returned by "
        "_orch_attestation_refs at 22948-22950; anchor os.open 32968-32969"),
    "ctx.guard_events": (
        "preflight", True,
        "as the anchor (the guard-events pointer in a register row is not modelled)",
        "_orch_attestation_refs 22947-22956, _orch_attestation_derive via 22957, "
        "_orch_pointer_resolves 33018-33020, open 22173"),
    "ctx.checkpoint": (
        "preflight", True,
        "the enumerator runs",
        "_orch_build_ctx 23433 and 23442, _orch_checkpoint_union 23321-23324"),
    "audit.handoff": (
        "--resume-audit", False, "record.handoff is declared", "_orch_resume_probes 32758-32768"),
    "audit.findings": (
        "--resume-audit", False, "record.findings is declared",
        "_orch_resume_probes 32788-32790, and _orch_merge_pending_findings 32833-32842 via 32819"),
    "audit.pending_decisions": (
        "--resume-audit", False, "record.pending_decisions is declared", "32788-32790"),
    "audit.attestations": (
        "--resume-audit", False, "attestations is declared",
        "_orch_validate_attestations 33094, _orch_chained_rows 32876 via 33096, "
        "_orch_register_authority 32921 via 33097"),
    "audit.attestations_anchor": (
        "--resume-audit", True,
        "attestations is declared and os.stat succeeds on the register (git tracking is not "
        "modelled)",
        "_orch_register_authority 32921-32924 hold on a failed register open; "
        "anchor os.open 32968-32969 via _orch_validate_attestations 33097"),
    "audit.mistakes_register": (
        "--resume-audit", False, "mistakes_register is declared", "33132-33134, open 32876"),
    "audit.guard_events": (
        "--resume-audit", False,
        "always checked: both opens depend on file content (a guard-events pointer, findings to "
        "record)",
        "_orch_pointer_resolves 33020 via 33111 and 33144; _orch_guard_event 22162 via 33334-33335"),
    "audit.escape_spoof": (
        "--resume-audit", False, "always (lexists, then open)",
        "_orch_pending_artefact_findings 33211-33212"),
    "audit.forced_exit": (
        "--resume-audit", False, "always", "_orch_forced_exit_findings 33159-33160, open 22173"),
    "audit.forced_exit_surfaced": (
        "--resume-audit", True,
        "os.stat succeeds on forced-exit.jsonl and it is not empty (its rows are not modelled)",
        "_orch_read_jsonl 22173-22178, no rows return _orch_forced_exit_findings 33168-33169, open 33172"),
    "audit_bad.unused": (
        "--resume-audit", False, "an unreadable registry; then always",
        "orch_resume_audit 33316-33317, open 22162"),
    "audit_bad.guard_events": (
        "--resume-audit", False, "an unreadable registry; then always (the registry is a finding)",
        "_orch_resume_audit_findings 33321, _orch_guard_event 22162 via 33334"),
}

# (site, expectation, case method of DoctorPrecheckSites). "reach": the hook opens the path, so the
# doctor must refuse a special file there; "skip": the hook takes an earlier exit, so the doctor must
# run, and the real hook, run after it, must complete within the timeout with the FIFO in place.
PRECHECK_CASES = [
    ("registry.file", "reach", "case_registry_local"),
    ("registry.file", "reach", "case_registry_committed_without_local"),
    ("registry.file", "skip", "case_registry_committed_behind_valid_local"),
    ("scope.lease", "reach", "case_lease_holder_directory"),
    ("scope.lease", "skip", "case_lease_holder_fifo_is_empty"),
    ("scope.lease", "skip", "case_lease_holder_without_session_id"),
    ("scope.mode", "reach", "case_mode_without_lease"),
    ("scope.mode", "skip", "case_mode_behind_live_lease"),
    ("scope.mode", "skip", "case_mode_behind_unstattable_holder_lease"),
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
    ("ctx.attestations_anchor", "reach", "case_ctx_anchor"),
    ("ctx.attestations_anchor", "skip", "case_ctx_anchor_without_register"),
    ("ctx.guard_events", "reach", "case_ctx_guard_events"),
    ("ctx.guard_events", "skip", "case_ctx_guard_events_without_register"),
    ("ctx.checkpoint", "reach", "case_checkpoint"),
    ("ctx.checkpoint", "skip", "case_checkpoint_argv_cannot_run"),
    ("audit.handoff", "reach", "case_audit_handoff"),
    ("audit.findings", "reach", "case_audit_findings"),
    ("audit.pending_decisions", "reach", "case_audit_pending"),
    ("audit.attestations", "reach", "case_audit_register"),
    ("audit.attestations_anchor", "reach", "case_audit_anchor"),
    ("audit.attestations_anchor", "skip", "case_audit_anchor_without_register"),
    ("audit.mistakes_register", "reach", "case_audit_mistakes"),
    ("audit.guard_events", "reach", "case_audit_guard_events"),
    ("audit.guard_events", "reach", "case_audit_guard_events_pointer"),
    ("audit.escape_spoof", "reach", "case_audit_escape_spoof"),
    ("audit.forced_exit", "reach", "case_audit_forced_exit"),
    ("audit.forced_exit_surfaced", "reach", "case_audit_surfaced"),
    ("audit.forced_exit_surfaced", "skip", "case_audit_surfaced_without_log"),
    ("audit.forced_exit_surfaced", "skip", "case_audit_surfaced_with_empty_log"),
    ("audit_bad.unused", "reach", "case_bad_registry_unused"),
    ("audit_bad.guard_events", "reach", "case_bad_registry_guard_events"),
]

# How the hook opens the path of each pre-check site: (kind, ((hook function, first line, last line of
# the open), ...)). "blocking": a plain open() that waits on a FIFO with no writer; "non-blocking": an
# os.open with O_NONBLOCK, so the hook would not block there; "enumerator": the hook does not open the
# path, the enumerator it runs does. The opens given for a site are those by which the hook first opens
# that site's path, or runs the enumerator that takes it. DoctorPrecheckSiteProbe checks each open
# against the hook source, and the reach case of each site in DoctorPrecheckSites runs the hook call
# path (OPEN_TRACE_PROG) and requires that the hook function and line at which the hook first opens that
# site's path, or runs the enumerator that takes it, are one of the opens given here; every open given
# here must be that first open in at least 1 reach case of its site. Line numbers cite
# plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py.
_SURFACE_READ = ("non-blocking", (("_orch_record_surface_read", 32703, 32704),))
_ANCHOR_READ = ("non-blocking", (("_orch_register_authority", 32968, 32969),))
PRECHECK_OPENS = {
    "registry.file": ("non-blocking", (("_orch_registry", 22096, 22098),)),
    "scope.lease": ("blocking", (("_orch_scope_live", 22640, 22640),)),
    "scope.mode": ("non-blocking", (("_orch_mode_read", 22445, 22446),)),
    "ctx.turn_state": ("blocking", (("_orch_turn_state", 22346, 22346),)),
    "ctx.enumerator_operand": ("enumerator", (("_orch_enumerate", 22833, 22833),)),
    "ctx.ledger": ("blocking", (("_orch_read_jsonl", 22173, 22173),)),
    "ctx.pending_decisions": _SURFACE_READ,
    "ctx.attestation_snapshot": ("blocking", (("_orch_attestation_refs", 22934, 22934),)),
    "ctx.attestations": ("blocking", (("_orch_register_authority", 32921, 32921),)),
    "ctx.attestations_anchor": _ANCHOR_READ,
    "ctx.guard_events": ("blocking", (("_orch_read_jsonl", 22173, 22173),)),
    "ctx.checkpoint": ("blocking", (("_orch_checkpoint_union", 23324, 23324),)),
    "audit.handoff": _SURFACE_READ,
    "audit.findings": _SURFACE_READ,
    "audit.pending_decisions": _SURFACE_READ,
    "audit.attestations": ("blocking", (("_orch_chained_rows", 32876, 32876),)),
    "audit.attestations_anchor": _ANCHOR_READ,
    "audit.mistakes_register": ("blocking", (("_orch_chained_rows", 32876, 32876),)),
    "audit.guard_events": ("blocking", (("_orch_read_jsonl", 22173, 22173),
                                        ("_orch_append_jsonl", 22162, 22162))),
    "audit.escape_spoof": ("blocking", (("_orch_pending_artefact_findings", 33212, 33212),)),
    "audit.forced_exit": ("blocking", (("_orch_read_jsonl", 22173, 22173),)),
    "audit.forced_exit_surfaced": ("blocking", (("_orch_forced_exit_findings", 33172, 33172),)),
    "audit_bad.unused": ("blocking", (("_orch_append_jsonl", 22162, 22162),)),
    "audit_bad.guard_events": ("blocking", (("_orch_append_jsonl", 22162, 22162),)),
}

# The words with which the doctor names the path of each pre-check site in its refusal ("cannot
# evaluate: the <label> <path> ..."), which the reach case of each site checks. An enumerator operand is
# named by its index in the declared argv, and the fixture enumerator, a -c program in argv[3], takes
# the backlog as argv[4].
PRECHECK_LABELS = {
    "registry.file": "registry file",
    "scope.lease": "declared lease.path",
    "scope.mode": "declared mode.path",
    "ctx.turn_state": "hook state file turn-state.json",
    "ctx.enumerator_operand": "declared enumerator.argv[4]",
    "ctx.ledger": "hook state file dispatch-ledger.jsonl",
    "ctx.pending_decisions": "declared record.pending_decisions",
    "ctx.attestation_snapshot": "hook state file attestations-validated.json",
    "ctx.attestations": "declared attestations",
    "ctx.attestations_anchor": "declared attestations.anchor",
    "ctx.guard_events": "hook state file guard-events.jsonl",
    "ctx.checkpoint": "hook state file backlog-checkpoint.json",
    "audit.handoff": "declared record.handoff",
    "audit.findings": "declared record.findings",
    "audit.pending_decisions": "declared record.pending_decisions",
    "audit.attestations": "declared attestations",
    "audit.attestations_anchor": "declared attestations.anchor",
    "audit.mistakes_register": "declared mistakes_register",
    "audit.guard_events": "hook state file guard-events.jsonl",
    "audit.escape_spoof": "hook state file escape-spoof.json",
    "audit.forced_exit": "hook state file forced-exit.jsonl",
    "audit.forced_exit_surfaced": "hook state file forced-exit-surfaced.json",
    "audit_bad.unused": "hook state file resume-barrier.json.unused",
    "audit_bad.guard_events": "hook state file guard-events.jsonl",
}

# The doctor's whole account of how the hook opens a path that it does not open with a blocking open,
# by the hook function that PRECHECK_OPENS names for the site: (exact text, claims). The text must be
# the doctor's SITE_OPEN text for each such site, and every hook line or range it cites must be the
# range of 1 claim, and the reverse. A claim is (hook function, first line, last line, check), checked
# at source by DoctorPrecheckSiteProbe: ("open", flags) is an os.open call in the function whose
# statements span exactly those lines and whose flags name each of flags; ("if", test, start,
# constants) is an if statement of the function that starts on the first line, whose test reads test,
# whose body starts with start, ends on the last line and calls no os.read, and each module constant in
# constants holds the given value; ("run",) is a subprocess.run call on that line.
OPEN_ACCOUNTS = {
    "_orch_registry": (
        "the hook would not block on it: _orch_registry opens the path with O_NONBLOCK "
        "(aiqt_hooks.py:22096-22098) and reads a file that is not regular as a bad registry "
        "(22102-22103), but the doctor refuses it without calling that reader",
        (("_orch_registry", 22096, 22098, ("open", ("O_NONBLOCK",))),
         ("_orch_registry", 22102, 22103,
          ("if", "not stat.S_ISREG(os.fstat(fd).st_mode)", "return ('bad', ", {})))),
    "_orch_mode_read": (
        "the hook's mode reader would not block on it: _orch_mode_read opens the path with "
        "O_NONBLOCK (aiqt_hooks.py:22445-22446) and gives a file that is not regular the status bad, "
        "without a read (22453-22454), which _orch_mode_detail takes as unattended, fail-closed "
        "(22529-22530), but the doctor does not model that reader",
        (("_orch_mode_read", 22445, 22446, ("open", ("O_NONBLOCK",))),
         ("_orch_mode_read", 22453, 22454,
          ("if", "not stat.S_ISREG(os.fstat(fd).st_mode)", "result = ('bad', ", {})),
         ("_orch_mode_detail", 22529, 22530,
          ("if", "status != 'ok'", "return (_ORCH_MODE_ARMED, ", {"_ORCH_MODE_ARMED": "unattended"})))),
    "_orch_record_surface_read": (
        "the hook would not block on it: _orch_record_surface_read opens the path with O_NONBLOCK "
        "(aiqt_hooks.py:32703-32704) and returns no data for a file that is not regular, without a "
        "read (32709-32710, 32725-32726), but the doctor refuses it without calling that reader",
        (("_orch_record_surface_read", 32703, 32704, ("open", ("O_NONBLOCK",))),
         ("_orch_record_surface_read", 32709, 32710,
          ("if", "not stat.S_ISREG(os.fstat(fd).st_mode)", "detail = 'not a regular file'", {})),
         ("_orch_record_surface_read", 32725, 32726,
          ("if", "detail is not None", "return (None, detail)", {})))),
    "_orch_register_authority": (
        "the hook would not block on it: _orch_register_authority opens the path with O_NONBLOCK "
        "and O_NOFOLLOW (aiqt_hooks.py:32968-32969) and holds on a file that is not regular "
        "(32975-32976) or a symlink (32971-32972), but the doctor refuses it without calling "
        "that reader",
        (("_orch_register_authority", 32968, 32969, ("open", ("O_NONBLOCK", "O_NOFOLLOW"))),
         ("_orch_register_authority", 32975, 32976,
          ("if", "not stat.S_ISREG(os.fstat(fd).st_mode)", "return ('hold', ", {})),
         ("_orch_register_authority", 32971, 32972,
          ("if", "exc.errno == errno.ELOOP", "return ('hold', ", {})))),
    "_orch_enumerate": (
        "the hook does not open it: the declared enumerator, which the hook runs "
        "(subprocess.run at aiqt_hooks.py:22833), takes it as an operand, and the doctor does not "
        "model how that program opens it",
        (("_orch_enumerate", 22833, 22833, ("run",)),)),
}
BLOCKING_TEXT = "the hook would open it with a blocking open"
# What the refusal says was not run: the hook reader that opens the path and any enumerator, or, at a
# path that no hook reader opens (an enumerator operand), the enumerator alone.
READER_END = "so the hook reader that opens it was not called and no enumerator ran"
ENUMERATOR_END = "so no enumerator ran"
HOOK_CITATION = re.compile(r"(?<![\d-])(\d{5})(?:-(\d{5}))?(?![\d-])")


def expected_open_text(site):
    """The doctor's text for how the hook opens the path of site, as OPEN_ACCOUNTS words it."""
    kind, opens = PRECHECK_OPENS[site]
    return BLOCKING_TEXT if kind == "blocking" else OPEN_ACCOUNTS[opens[0][0]][0]


def expected_tail(site):
    """The whole refusal at site after "(it is a <type>); ": how the hook opens the path, then what
    was not run."""
    end = ENUMERATOR_END if PRECHECK_OPENS[site][0] == "enumerator" else READER_END
    return "{}, {}".format(expected_open_text(site), end)


def assert_open_wording(case, site, tail):
    """Assert that tail, the doctor's refusal text after "(it is a <type>); " to the end of its line,
    is exactly expected_tail(site): how the hook opens the path of site, in the words of
    OPEN_ACCOUNTS for a site the hook does not open with a blocking open, then what was not run."""
    case.assertEqual(tail, expected_tail(site), "site {}".format(site))


def assert_refusal(case, stdout, site, label, path, made):
    """Assert that stdout holds the doctor's whole refusal of the special file at path, of type made,
    at the pre-check site site, as 1 line: exactly "cannot evaluate: the <label> <path> is not a
    regular file (it is a <made>); " and then exactly expected_tail(site), to the end of the line.
    label is the doctor's name for the path, which every caller gives. Once the line holds, stdout is
    marked as checked, so the cleanup of run_doctor_recorded does not fail the case for it."""
    head = "cannot evaluate: the {} {} is not a regular file (it is a {}); ".format(label, path, made)
    lines = [line for line in stdout.split("\n") if line.startswith(head)]
    case.assertEqual(len(lines), 1, "site {}: no single refusal of {} in {!r}".format(site, path, stdout))
    assert_open_wording(case, site, lines[0][len(head):])
    refusal_outputs(case)[1].append(stdout)


def assert_barrier_refusal(case, stdout, path, made=None, line=None):
    """Assert that stdout holds 1 refusal of the resume audit to report the barrier at path, as the only
    line of stdout that starts with "barrier: ", and that it is the whole line: without line, the
    refusal of a barrier that is not a regular file, of type made, exactly BARRIER_REFUSAL_PREFIX, then
    "<path> (<path> is not a regular file (it is a <made>)); a rewrite could not be confirmed, so the
    audit is not run"; else line, the whole text of another refusal (AUDIT_REFUSAL_PREFIXES), or a
    compiled pattern that the whole line must match, for a refusal that holds a time of the run. Each is
    a line that _resume_audit in tools/orch_doctor.py prints. Once the line holds, stdout is marked as
    checked, as assert_refusal marks it."""
    if line is None:
        line = ("{}{} ({} is not a regular file (it is a {})); a rewrite could not be confirmed, so the "
                "audit is not run".format(BARRIER_REFUSAL_PREFIX, path, path, made))
    lines = [found for found in stdout.split("\n") if found.startswith("barrier: ")]
    whole = (len(lines) == 1 and line.fullmatch(lines[0]) is not None) if isinstance(line, re.Pattern) \
        else lines == [line]
    case.assertTrue(whole, "no single whole barrier refusal of {}: {!r} in {!r}".format(path, line, stdout))
    refusal_outputs(case)[1].append(stdout)


# Every process that this file starts goes through 1 launcher, run_doctor_recorded; the launches of the
# self-test outside it are there to be refused. _admit, an audit hook that the module adds at its end and
# that cannot be removed, refuses every other start of a process in this interpreter: an event of
# LAUNCH_EVENTS that the recorder's own call of subprocess.run did not raise, which it tells by the
# identity of the code of the frames that raise the event (_launch_frames), not by a name or a mark that
# a case could set; it refuses that code as the code of a function built from it or given it, and the
# load of each module that can make a subinterpreter (INTERPRETER_MODULES), whose audit hooks would be
# its own. It also refuses, in this process, any code object that holds a string constant that starts
# with 1 of REFUSAL_PREFIXES, in it or in a nested code object, tuple, frozenset or slice constant, or
# that holds a constant of a type that the compiler does not make, when it runs by exec, eval or import
# (the exec event), when a function is built from it (function.__new__) and when it is assigned as the
# code of a function (object.__setattr__ of __code__), so the doctor's code cannot run in this process
# by any of those routes under any name. Neither depends on how a launch or the doctor is named. _admit
# reads the event list, the modules, the prefixes and the frames from its own defaults,
# fixed when the module loads, so a case that rebinds a name of this module does not change what it
# checks, and it refuses a change of the code or the defaults of itself or of _holds_refusal. The
# recorder registers a run's output with its case when 1 of REFUSAL_PREFIXES occurs anywhere in its
# captured stdout, not only at the start of a line, so a refusal that a child program wraps in JSON is
# registered; so is the output of a run that timed out or failed check=True. REFUSAL_PREFIX starts a
# pre-check refusal (the only print of such a line is _refuse_special in tools/orch_doctor.py),
# BARRIER_REFUSAL_PREFIX the resume audit's refusal of a barrier that it cannot record, and
# AUDIT_REFUSAL_PREFIXES each other refusal of the resume audit to report the barrier (each printed only
# in _resume_audit; DoctorRefusalCoverage holds the 2 to the doctor's barrier texts). The recorder
# refuses a run whose stdout is not captured before the run starts, and fails at once a run whose output
# holds a refusal when it has no case or its case is not running, since that case's cleanup would never
# run. assert_refusal and assert_barrier_refusal mark the output that they check as a whole line. A
# cleanup then fails the case for each registered output that neither marked, whatever else the case
# checked in it. A partial check beside those helpers is not refused, but it cannot replace them. Not
# seen: doctor output that reaches a case other than through the captured stdout of the recorder (a
# file, a socket, stderr, or an encoding that hides every prefix), a process that native code starts
# without an audit event, a subinterpreter that native code makes other than through
# INTERPRETER_MODULES, code run in this process by a route that raises none of those 3 events, a doctor
# loaded in this process whose refusal text is not a string constant of its code, and a case that
# replaces a built-in, replaces with native code a function that the recorder's launch calls, rebinds or
# changes what the registration and the cleanup read (REFUSAL_PREFIXES, _register_refusal,
# refusal_outputs and its lists), or gives an object that is not running the state by which unittest
# marks a running case (_outcome).
REFUSAL_PREFIX = "cannot evaluate: "
BARRIER_REFUSAL_PREFIX = "barrier: cannot be recorded before the audit at "
AUDIT_REFUSAL_PREFIXES = ("barrier: cannot be read back from ", "barrier: NOT rewritten by this audit (",
                          "barrier: its ts ", "barrier: malformed at ")
REFUSAL_PREFIXES = (REFUSAL_PREFIX, BARRIER_REFUSAL_PREFIX) + AUDIT_REFUSAL_PREFIXES
# The audit events with which the standard library of Python 3.14 on Linux starts a process, and
# ctypes.dlopen, with which ctypes loads native code that can start one. Each is matched as the start of
# an event's name, so "os.fork" also matches os.forkpty, which therefore is not a member of its own. An
# extension module that the test process imports raises none of them. _admit refuses each outside the
# recorder's own launch.
LAUNCH_EVENTS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
                 "_posixsubprocess.fork_exec", "ctypes.dlopen")
# The extension modules of Python 3.14.4 on Linux whose dynamic symbols name a C function that makes a
# subinterpreter: _interpreters, which concurrent.interpreters imports, and the 2 test modules of
# CPython. A subinterpreter has audit hooks of its own, so _admit would see neither a process that it
# starts nor code that it runs, and its creation raises no event in this interpreter; _admit refuses
# the load of each of these modules (the import event, which every load of an extension module raises),
# so no subinterpreter can be made through them.
INTERPRETER_MODULES = ("_interpreters", "_testcapi", "_testinternalcapi")


def literal_text(node):
    """The text of a string expression as Python evaluates it: a str constant (escapes resolved, and
    adjacent literals joined by the parser), a bytes constant read as latin-1, an f-string with "{}" for
    each replacement field, and a + of such parts with "{}" for each other operand; None for any other
    node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return node.value
        return node.value.decode("latin-1") if isinstance(node.value, bytes) else None
    if isinstance(node, ast.JoinedStr):
        return "".join(literal_text(value) if isinstance(value, ast.Constant) else "{}"
                       for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = literal_text(node.left), literal_text(node.right)
        if left is not None or right is not None:
            return (left if left is not None else "{}") + (right if right is not None else "{}")
    return None


def run_doctor_recorded(case, argv, **kwargs):
    """subprocess.run(argv, **kwargs), the 1 launcher of this file: every process that the file starts,
    a doctor run or not, goes through it, and _admit refuses any other launch in this interpreter and
    the load of a module that can make a subinterpreter, telling this launch by the identity of the code
    of its frames (_launch_frames). The name is kept from when it ran the doctor alone. stdout must be
    captured (capture_output=True or stdout=subprocess.PIPE), else ValueError, before the run starts.
    The output is registered (_register_refusal) when the run returns, and also when it times out
    (TimeoutExpired) or fails check=True (CalledProcessError), before that exception goes on. The
    design names only the timeout; a doctor that refuses exits 2, so a run with check=True raises before
    it returns, and a case that caught that exception would otherwise hold an output that nothing
    registered. Before the run starts, it gives its timeout argument to _time_limit_applied, as the
    comment on TEST_TIME_LIMITS states, so a refused limit starts no run and makes no file of starts.
    The run's environment also names, in ENUM_RUNS_VAR, a new file of the run's own, in
    which each enumerator that the run starts records its start (ENUM_RUN_MARK); however the run ends,
    the recorder counts those starts and holds the timeout that the run was given to them
    (_hold_enumerator_bound). With no running case, a run with a defect raises AssertionError at once,
    and when subprocess.run raised an exception, that exception is its cause (__cause__), so it stays
    visible; when the registration of that exception's output failed as well, the cause is still the
    exception of subprocess.run, and the AssertionError of the registration is the context
    (__context__) of the bound failure."""
    if not kwargs.get("capture_output") and kwargs.get("stdout") is not subprocess.PIPE:
        raise ValueError("run_doctor_recorded needs the stdout of {!r} captured".format(argv))
    _time_limit_applied("launch", kwargs.get("timeout"))
    # A call such as tempfile.mkdtemp(...) compiles otherwise in this module than in the source of this
    # function alone, which the namesake check of DoctorRefusalCoverage compiles, so the calls of module
    # functions are in the helpers.
    folder = _new_starts_folder()
    kwargs["env"] = _env_naming_starts(kwargs.get("env"), folder)
    launched = None
    try:
        try:
            r = subprocess.run(argv, **kwargs)
        except BaseException as exc:
            launched = exc
            if isinstance(exc, (subprocess.TimeoutExpired, subprocess.CalledProcessError)):
                _register_refusal(case, exc.stdout)
            raise
    except BaseException:
        _hold_enumerator_bound(case, argv, kwargs.get("timeout"), folder, launched)
        raise
    _hold_enumerator_bound(case, argv, kwargs.get("timeout"), folder, None)
    _register_refusal(case, r.stdout)
    return r


def _new_starts_folder():
    """A new folder outside every case tree, for the file of the starts of 1 launch."""
    return tempfile.mkdtemp(prefix="orch-stage2-starts-")


def _env_naming_starts(env, folder):
    """A copy of env (of os.environ for None) that names the file of starts in folder in ENUM_RUNS_VAR."""
    named = dict(os.environ if env is None else env)
    named[ENUM_RUNS_VAR] = os.path.join(folder, "starts")
    return named


# The residuals of the bound check that run_doctor_recorded makes. It counts only the starts that an
# enumerator records: of the declared enumerators that the hook would start, Stage2Harness.write_registry
# accepts only one whose argv is exactly this interpreter (sys.executable), -I, -c and 1 of ENUM_PROGRAMS,
# each a separate element, followed by any operands, and whose timeout, as the hook reads it, is at most
# ENUM_TIMEOUT (declared_enumerator_defect), and refuses every program file. The record is a file that
# any process of this user can write, so its count holds only because each accepted program leaves
# the record alone after the mark (program_leaves_record), and a program that the 1 launcher starts
# directly, not through a registry, is trusted as the code of this file is. Code that the interpreter
# runs before any program under -I (site: .pth import lines and sitecustomize) is not seen, a registry
# written another way is not seen, a child that starts the enumerator with an environment that drops
# ENUM_RUNS_VAR is not counted (EnumeratorBounds shows that the hook and the doctor pass it on), and a
# start that ends before its program runs is not counted.
# The doctor checks each element of the argv from argv[2] on as an operand path, as for a committed
# registry, whose argv[2] the registry gate requires to be a script, so for these registries it also
# checks -c and the program; a special file at <root>/-c makes it refuse where the hook runs the
# enumerator (Doctor.test_preflight_special_file_at_the_c_option_is_cannot_evaluate pins that; the
# refusal runs no enumerator). It holds a launch
# only for the starts that it made when a case ran it: a launch that could start the enumerator but did
# not in that run, or that no case runs, is not held, and a start recorded after the recorder has read
# the file, by an enumerator that outlives a launch whose timeout ended it, is not counted. A launch
# with no timeout is not held, since no bound of the test can end it before the hook's own timeout
# does. The bound is ENUM_TIMEOUT for each start, and write_registry refuses a declared enumerator
# timeout over ENUM_TIMEOUT, as the hook reads it.
def enumerator_bound_defect(argv, timeout, starts):
    """The defect of a launch with argv that was given timeout (None for none) and in which an
    enumerator recorded starts starts: a timeout under starts times ENUM_TIMEOUT, plus ENUM_MARGIN;
    None when there is no such defect."""
    need = starts * ENUM_TIMEOUT + ENUM_MARGIN
    if starts and timeout is not None and timeout < need:
        shown = [part if len(part) <= 80 else part[:77] + "..." for part in map(str, argv)]
        return ("{!r}: timeout {} s, under {} enumerator start(s) of ENUM_TIMEOUT ({} s) plus "
                "ENUM_MARGIN ({} s), {} s".format(shown, timeout, starts, ENUM_TIMEOUT, ENUM_MARGIN, need))
    return None


def _enumerator_starts(path):
    """The number of starts recorded in path, 0 when nothing created it."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().count("run\n")
    except FileNotFoundError:
        return 0


def _hold_enumerator_bound(case, argv, timeout, folder, cause):
    """Count the starts recorded in folder, remove it, and keep the launch for the cleanup of case
    (enumerator_launches); with case None, or a case that unittest is not running, whose cleanup would
    never run, a launch with a defect (enumerator_bound_defect) fails at once (AssertionError), with
    cause, the exception that the launch raised (None for none), as its cause."""
    try:
        starts = _enumerator_starts(os.path.join(folder, "starts"))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if getattr(case, "_outcome", None) is None:
        defect = enumerator_bound_defect(argv, timeout, starts)
        if defect is None:
            return
        message = "a run with no running case: {}".format(defect)
        if cause is None:
            raise AssertionError(message)
        raise AssertionError(message) from cause
    enumerator_launches(case).append((argv, timeout, starts))


def enumerator_launches(case):
    """The launches of case as (argv, timeout, starts); the first call for a case adds the cleanup that
    fails it for each launch with a defect (enumerator_bound_defect)."""
    found = case.__dict__.get("_enumerator_launches")
    if found is None:
        found = case._enumerator_launches = []
        case.addCleanup(_fail_short_enumerator_bounds, case)
    return found


def take_enumerator_launches(case):
    """The launches of case so far, which its cleanup then no longer holds."""
    found = list(enumerator_launches(case))
    del case._enumerator_launches[:]
    return found


def _fail_short_enumerator_bounds(case):
    launches = case.__dict__.pop("_enumerator_launches", [])
    defects = [defect for defect in (enumerator_bound_defect(*launch) for launch in launches)
               if defect is not None]
    if defects:
        case.fail("{} run(s) with a timeout under the bound for their enumerator starts: {}"
                  .format(len(defects), defects))


def _register_refusal(case, stdout):
    """Register stdout with case (refusal_outputs) when 1 of REFUSAL_PREFIXES occurs anywhere in it,
    bytes read as latin-1; with case None, or a case that unittest is not running (its _outcome is
    None, so its cleanup would never run), such an output fails at once (AssertionError)."""
    out = stdout.decode("latin-1") if isinstance(stdout, bytes) else (stdout or "")
    if any(prefix in out for prefix in REFUSAL_PREFIXES):
        if getattr(case, "_outcome", None) is None:
            raise AssertionError("a run with no running case printed a doctor refusal: {!r}".format(out))
        refusal_outputs(case)[0].append(stdout)


def _holds_refusal(code, prefixes):
    """Whether code, or a code object, tuple, frozenset or slice among its constants at any depth (each
    container in which the compiler of Python 3.14 keeps a constant), holds a string that starts with 1
    of prefixes; a constant of any type that this compiler does not make, which only a code object built
    by hand holds, is taken as holding one."""
    pending = [code.co_consts]
    while pending:
        for const in pending.pop():
            kind = type(const)
            if kind is str:
                if const.startswith(prefixes):
                    return True
            elif kind is tuple or kind is frozenset:
                pending.append(const)
            elif kind is slice:
                pending.append((const.start, const.stop, const.step))
            elif kind is type(code):
                pending.append(const.co_consts)
            elif kind not in (bytes, int, float, complex, bool, type(None), type(Ellipsis)):
                return True
    return False


def _launch_frames():
    """For each event that the recorder's own call of subprocess.run raises (Python 3.14 on Linux), the
    code objects of the frames that raise it, innermost first: subprocess.Popen in
    Popen._execute_child; os.posix_spawn in Popen._posix_spawn, which _execute_child calls; and
    _posixsubprocess.fork_exec in _execute_child where posix_spawn cannot serve (a cwd or a preexec_fn,
    for 2); then, for each, Popen.__init__, subprocess.run and run_doctor_recorded. _admit reads them
    once, when the module loads."""
    popen = subprocess.Popen
    tail = tuple(function.__code__ for function in (popen._execute_child, popen.__init__, subprocess.run,
                                                    run_doctor_recorded))
    return (("subprocess.Popen", tail), ("os.posix_spawn", (popen._posix_spawn.__code__,) + tail),
            ("_posixsubprocess.fork_exec", tail))


def _admit(event, args, launch_events=LAUNCH_EVENTS, prefixes=REFUSAL_PREFIXES,
           launch_frames=_launch_frames(), getframe=sys._getframe, holds=_holds_refusal,
           code_type=types.CodeType, function_type=types.FunctionType,
           interpreter_modules=INTERPRETER_MODULES):
    """The audit hook of this file. What it reads is in its own defaults, fixed when the module loads,
    so a case that rebinds a name of this module does not change what it checks. It raises RuntimeError
    on an event of launch_events (LAUNCH_EVENTS) unless the frames that raise it, innermost first, run
    exactly the code objects that launch_frames gives for that event, each told by its identity, as
    only the recorder's own call of subprocess.run does, in any thread; on the load of a module of
    interpreter_modules (INTERPRETER_MODULES), which makes a subinterpreter that this hook does not see;
    on a code object that holds a doctor refusal (holds, with prefixes), or that is 1 of the code
    objects of launch_frames, when it runs by exec, eval or import (the exec event), when a function is
    built from it (function.__new__) and when it is assigned as the __code__ of a function
    (object.__setattr__), since a function with that code and other globals would launch as the
    recorder does but past its registration; and on a change of the code or the defaults of _admit or
    of holds (object.__setattr__, or object.__delattr__ for defaults set to None)."""
    if event.startswith(launch_events):
        frame, frames = getframe(1), None
        for name, codes in launch_frames:
            if name == event:
                frames = codes
        while frames and frame is not None and frame.f_code is frames[0]:
            frame, frames = frame.f_back, frames[1:]
        if frames != ():
            raise RuntimeError("{} outside run_doctor_recorded, the only launcher of this file".format(event))
        return
    if event == "import" and args and args[0] in interpreter_modules:
        raise RuntimeError("a load of {}, which makes a subinterpreter that the audit hook of this file "
                           "does not see".format(args[0]))
    code = None
    if event in ("object.__setattr__", "object.__delattr__") and len(args) >= 2 \
            and isinstance(args[0], function_type):
        changed = args[0].__code__
        if changed is getframe(0).f_code or changed is holds.__code__:
            raise RuntimeError("a change of {} of the audit hook of this file".format(args[1]))
    if event == "object.__setattr__" and len(args) == 3 and args[1] == "__code__":
        code = args[2]
    elif event in ("exec", "function.__new__") and args:
        code = args[0]
    if isinstance(code, code_type) and holds(code, prefixes):
        raise RuntimeError("code that holds a doctor refusal, run in the test process: {}"
                           .format(code.co_filename))
    if isinstance(code, code_type) \
            and any(code is known for _name, codes in launch_frames for known in codes):
        raise RuntimeError("the code of the recorder's launch, given to another function: {}"
                           .format(code.co_qualname))


def refusal_outputs(case):
    """(registered, checked) for case: the outputs of its runs that hold a doctor refusal (a pre-check
    refusal or a barrier refusal of the resume audit, REFUSAL_PREFIXES), and the outputs that
    assert_refusal or assert_barrier_refusal checked. The first
    call for a case adds the cleanup that fails it for a registered output that neither checked."""
    found = case.__dict__.get("_refusal_outputs")
    if found is None:
        found = case._refusal_outputs = ([], [])
        case.addCleanup(_fail_unchecked_refusals, case)
    return found


def unchecked_refusals(case):
    """The registered outputs of case that neither assert_refusal nor assert_barrier_refusal checked,
    each matched by identity, so 1 checked output does not stand for another run with the same text."""
    registered, checked = refusal_outputs(case)
    return [out for out in registered if not any(out is seen for seen in checked)]


def _fail_unchecked_refusals(case):
    missed = unchecked_refusals(case)
    del case._refusal_outputs
    if missed:
        case.fail("{} doctor run(s) printed a refusal that neither assert_refusal nor assert_barrier_refusal "
                  "checked as a whole line: {!r}".format(len(missed), missed))


# Runs in a separate python3 -I process: the hook call path that the command runs (the resume audit,
# or the preview path of PREVIEW_PATH_PROG), with open, os.open and subprocess.run wrapped. At the first
# open of the target path, or the first subprocess.run whose argv names it, it prints the hook function
# and line that made the call and exits at once, so a FIFO there cannot block it; "none" when the call
# path ends without either.
OPEN_TRACE_PROG = r"""
import builtins, importlib.util, json, os, subprocess, sys
sys.dont_write_bytecode = True
hook_file, repo, sid, command, target = sys.argv[1:6]
spec = importlib.util.spec_from_file_location("aiqt_hooks_open_trace", hook_file)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
hook_code = os.path.realpath(hook_file)


def norm(path, base=None):
    path = os.fsdecode(os.fspath(path))
    if not os.path.isabs(path):
        if base is None:
            return None
        path = os.path.join(os.fsdecode(os.fspath(base)), path)
    path = os.path.abspath(path)
    return os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))


want = norm(target)


def names_target(path, base=None):
    try:
        return norm(path, base) == want
    except (TypeError, ValueError):
        return False


def found(how):
    frame = sys._getframe(2)
    while frame is not None and os.path.realpath(frame.f_code.co_filename) != hook_code:
        frame = frame.f_back
    print(json.dumps([how, frame.f_code.co_name if frame else None, frame.f_lineno if frame else None]),
          flush=True)
    os._exit(0)


real_open, real_os_open, real_run = builtins.open, os.open, subprocess.run


def traced_open(file, *args, **kwargs):
    if not isinstance(file, int) and names_target(file):
        found("open")
    return real_open(file, *args, **kwargs)


def traced_os_open(path, *args, **kwargs):
    if kwargs.get("dir_fd") is None and names_target(path):
        found("os.open")
    return real_os_open(path, *args, **kwargs)


def traced_run(argv, *args, **kwargs):
    if isinstance(argv, (list, tuple)) and any(names_target(a, kwargs.get("cwd")) for a in argv
                                               if isinstance(a, (str, bytes, os.PathLike))):
        found("subprocess.run")
    return real_run(argv, *args, **kwargs)


builtins.open, os.open, subprocess.run = traced_open, traced_os_open, traced_run
if command == "--resume-audit":
    hook.orch_resume_audit({"cwd": repo})
else:
    root = hook._recovery_toplevel(repo)
    status, reg = hook._orch_registry(root)
    if status == "ok" and hook._orch_scope_live(reg, root, sid or None):
        hook._orch_build_ctx(reg, root, "stop", {"session_id": sid} if sid else {},
                             record_checkpoint=False)
print(json.dumps(["none", None, None]), flush=True)
"""
# The wrapper that each kind of open goes through in OPEN_TRACE_PROG.
TRACE_HOW = {"blocking": "open", "non-blocking": "os.open", "enumerator": "subprocess.run"}


# Runs in a separate python3 -I process: the hook call path the preflight runs, and nothing else (the
# registry, the scope test, then _orch_build_ctx in the preview posture, aiqt_hooks.py:23412 and
# 23303-23305), so a skip case can show that path completes with the FIFO in place. The Stop hook itself
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
        # A non-string element: _orch_enumerate returns ENUMERATOR_ERROR unrun (aiqt_hooks.py:22827-22829).
        return {"argv": [sys.executable, "-I", "-c", ENUM_FIXTURE, str(self.backlog), 5],
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

    # --- registry.file
    def case_registry_local(self):
        self._reg()
        return self.repo / ".aiqt" / "orchestration.local.json", None, self.STOP, {}

    def case_registry_committed_without_local(self):
        (self.repo / ".aiqt").mkdir(exist_ok=True)
        return self.repo / ".aiqt" / "orchestration.json", None, self.AUDIT, {}

    def case_registry_committed_behind_valid_local(self):
        reg = self._reg()
        (self.repo / ".aiqt" / "orchestration.local.json").write_text(json.dumps(reg),
                                                                       encoding="utf-8")
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
        # A FIFO has size 0, so the lease is not live (`st.st_size` at 22632) and the hook reads
        # the mode record.
        self._holder()
        return (Path(self._p("session-state.md")), None, self.STOP + ("--session-id", "sess-1"),
                {"session_id": "sess-1"})

    def case_lease_holder_without_session_id(self):
        # No session id (`session_id` at 22637-22638): the hook returns False before
        # the open at 22640.
        self._holder()
        lease = Path(self._p("session-state.md"))
        lease.mkdir()
        (lease / "entry").write_text("held\n", encoding="utf-8")
        self.assertGreater(os.stat(lease).st_size, 0, "precondition: a non-empty directory")
        return lease, "directory", self.STOP, {}

    # --- scope.mode
    def case_mode_without_lease(self):
        self._reg()
        return Path(self._p("operating-mode.md")), None, self.STOP, {}

    def case_mode_behind_live_lease(self):
        # A present, non-empty, fresh lease makes scope live (`st.st_size` at 22632-22649),
        # before _orch_mode.
        self._reg()
        self.arm_lease()
        return Path(self._p("operating-mode.md")), None, self.STOP, {}

    def case_mode_behind_unstattable_holder_lease(self):
        # Holder mode with no lease on disk: the hook returns False
        # (`holder_is_session_id` at 22651-22652), before _orch_mode.
        self._holder()
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
        # No snapshot: the open at 22934 fails, and the reader then returns
        # (`return "unreadable"` at 22936-22937).
        self._reg(attestations=self._at())
        return Path(self._at()), None, self.STOP, {}

    def case_ctx_anchor(self):
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        Path(self._at()).write_text("", encoding="utf-8")
        return Path(self._at() + ".anchor"), None, self.STOP, {}

    def case_ctx_anchor_without_register(self):
        # No register: the open at 32921 fails, so the authority holds
        # (`register unreadable` at 32924) before the anchor.
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        return Path(self._at() + ".anchor"), None, self.STOP, {}

    def case_ctx_guard_events(self):
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        Path(self._at()).write_text("", encoding="utf-8")
        return self._sd("guard-events.jsonl"), None, self.STOP, {}

    def case_ctx_guard_events_without_register(self):
        self._reg(attestations=self._at())
        self.seed_state("attestations-validated.json", {})
        return self._sd("guard-events.jsonl"), None, self.STOP, {}

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

    def case_audit_anchor_without_register(self):
        self._reg(attestations=self._at())
        return Path(self._at() + ".anchor"), None, self.AUDIT, {}

    def case_audit_mistakes(self):
        self._reg(mistakes_register=self._p("mistakes.jsonl"))
        return Path(self._p("mistakes.jsonl")), None, self.AUDIT, {}

    def case_audit_guard_events(self):
        self._reg()
        return self._sd("guard-events.jsonl"), None, self.AUDIT, {}

    def case_audit_guard_events_pointer(self):
        # The register is absent when the doctor runs and is written before the trace
        # (TRACE_ARRANGE), so the audit reads guard-events for the register row's pointer
        # (`_orch_pointer_resolves` at 33018-33020, via 33111) before any guard event is appended.
        self._reg(attestations=self._at())
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
            h = run_doctor_recorded(self, argv, input=body, capture_output=True, text=True, env=self._env(),
                                    timeout=self.SPECIAL_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the hook call path did not exit within {} s: it does reach this open"
                      .format(self.SPECIAL_TIMEOUT))
        if args[0] != "--resume-audit":
            self.assertEqual(h.returncode, 0, h.stdout + h.stderr)
            self.assertIn("completed", h.stdout)
        return h

    # File content that the doctor does not model (see PRECHECK_SITES) but that the hook needs before it
    # reaches the open in these reach cases, arranged after the doctor's refusal and before the trace,
    # with the special file left in place.
    TRACE_ARRANGE = {
        "case_ctx_register": "_arrange_fresh_snapshot",
        "case_ctx_anchor": "_arrange_fresh_snapshot",
        "case_ctx_guard_events": "_arrange_guard_events_pointer",
        "case_audit_guard_events": "_arrange_audit_finding",
        "case_audit_guard_events_pointer": "_arrange_guard_events_pointer",
    }

    def _arrange_fresh_snapshot(self):
        # A snapshot that passes the checks before the register is read (aiqt_hooks.py:22938-22945).
        self.seed_state("attestations-validated.json", {"status": "ok", "refs": [], "ts": _iso()})

    def _arrange_guard_events_pointer(self):
        # An anchored 1-row register whose row points at guard-events, and a fresh snapshot bound to
        # its tip (22947-22950), so the derivation resolves the pointer (`_orch_pointer_resolves` at
        # 33018-33020).
        at = Path(self._at())
        lines = chain_lines([{"id": "AT-1", "status": "accepted", "ref": "vendor-x",
                              "check_ref": "guard-events:trace", "ts": _iso()}])
        at.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        digest = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()
        Path(str(at) + ".anchor").write_text(json.dumps({"seq": len(lines), "digest": digest}),
                                             encoding="utf-8")
        self.seed_state("attestations-validated.json",
                        {"status": "ok", "refs": [], "ts": _iso(), "register": os.path.realpath(at),
                         "seq": len(lines), "digest": digest})

    def _arrange_audit_finding(self):
        # No handoff: a declared handoff that cannot be read is a finding (aiqt_hooks.py:32763-32765),
        # so the audit records a guard event (33334-33335).
        Path(self._p("session-handoff.md")).unlink(missing_ok=True)

    def _assert_hook_reader(self, site, args, payload, path):
        # The real hook call path, run to its first open of path (OPEN_TRACE_PROG), must open it by
        # one of the opens that PRECHECK_OPENS gives for site, in that function and within that
        # range, and by the kind of call that site's kind names. Returns that open.
        argv = [sys.executable, "-I", "-c", OPEN_TRACE_PROG, str(HOOK), str(self.repo),
                payload.get("session_id", ""), args[0], str(path)]
        try:
            h = run_doctor_recorded(self, argv, capture_output=True, text=True, env=self._env(),
                                    timeout=self.SPECIAL_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the traced hook call path did not exit within {} s".format(self.SPECIAL_TIMEOUT))
        self.assertEqual(h.returncode, 0, h.stdout + h.stderr)
        how, reader, line = json.loads(h.stdout.strip().split("\n")[-1])
        kind, opens = PRECHECK_OPENS[site]
        self.assertEqual(how, TRACE_HOW[kind], "site {}: the hook reached {} by {} ({} at {})"
                         .format(site, path, how, reader, line))
        hits = [entry for entry in opens if reader == entry[0] and entry[1] <= line <= entry[2]]
        self.assertTrue(hits, "site {}: the hook opens {} in {} at {}, not by an open of PRECHECK_OPENS {}"
                        .format(site, path, reader, line, opens))
        return hits[0]

    def _run_case(self, site, expect, case, reached):
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
            assert_refusal(self, r.stdout, site, PRECHECK_LABELS[site], path, made)
            if case in self.TRACE_ARRANGE:
                getattr(self, self.TRACE_ARRANGE[case])()
            reached.add((site,) + self._assert_hook_reader(site, args, payload, path))
            return
        self.assertNotIn("cannot evaluate", r.stdout)
        self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)
        h = self._hook_bounded(args, payload)
        self.assertNotIn("Traceback", h.stderr)
        if made == "FIFO":
            self.assertTrue(path.is_fifo(), "the FIFO was replaced, so the contrast proves nothing")

    def test_every_case_against_the_doctor_and_the_hook(self):
        reached = set()
        for site, expect, case in PRECHECK_CASES:
            with self.subTest(site=site, expect=expect, case=case):
                self.tearDown()
                self.setUp()
                self._run_case(site, expect, case, reached)
        # Every open that PRECHECK_OPENS gives for a site is the first open of that site's path in at
        # least 1 reach case, so no open in the table stands without a run that ties it to the path.
        for site, (_kind, opens) in PRECHECK_OPENS.items():
            for entry in opens:
                with self.subTest(site=site, open=entry):
                    self.assertIn((site,) + entry, reached,
                                  "no reach case of site {} first opens its path by {} at {}-{}"
                                  .format(site, *entry))


class DoctorScopeMargin(Stage2Harness):
    """The hook judges a lease fresh when -_ORCH_CLOCK_SKEW <= age <= max_age_hours *
    3600 (aiqt_hooks.py:22618-22630), and the doctor treats a lease within SCOPE_MARGIN seconds of
    either bound as possibly on either side (orch_doctor.py _lease_fresh_states), so it checks both
    the holder lease open (scope.lease, `_orch_scope_live` at 22640) and the mode record open
    (scope.mode, `_orch_mode` at 22654). Each case sets the lease mtime NEAR seconds from a bound,
    on the side where the doctor sample at the clock now gives one answer and the sample
    SCOPE_MARGIN seconds later gives the other: just
    inside max_age_hours at the upper bound, and just beyond the skew tolerance into the future at
    the lower bound. A special file goes at one site at a time and must be refused there. With
    SCOPE_MARGIN = 0.0 the doctor samples one side only, so the upper case misses the mode record
    and the lower case misses the lease. A FIFO has size 0, so a FIFO lease is never live and never
    opened (case_lease_holder_fifo_is_empty): the special lease is a non-empty directory, which the
    hook does open, and the special mode record is a FIFO. The skew is read from the hook source and
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

    def _assert_refused_near(self, bound, site):
        reg = self._registry()
        lease = Path(self._p("session-state.md"))
        mode = Path(self._p("operating-mode.md"))
        if site == "scope.lease":
            lease.mkdir()
            (lease / "entry").write_text("held\n", encoding="utf-8")
            path, label, kind = lease, "lease.path", "directory"
        else:
            lease.write_text("held by sess-1\n", encoding="utf-8")
            mode.unlink()
            os.mkfifo(mode)
            path, label, kind = mode, "mode.path", "FIFO"
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
        assert_refusal(self, r.stdout, site, "declared " + label, path, kind)

    def _both_sites(self, bound):
        for site in ("scope.lease", "scope.mode"):
            with self.subTest(bound=bound, site=site):
                self.tearDown()
                self.setUp()
                self._assert_refused_near(bound, site)

    def test_near_the_max_age_bound_both_scope_opens_are_checked(self):
        self._both_sites("upper")

    def test_near_the_clock_skew_bound_both_scope_opens_are_checked(self):
        self._both_sites("lower")


# =====================================================================================================
# Every event field the previewed handlers read is previewed as the hook reads it
# =====================================================================================================
# (container, field) -> (status, doctor input or reason, the hook lines that read it). "data" is the
# event payload and "tool_input" its tool_input object; the field "values()" is the read of every
# value of tool_input. A modelled field names the doctor input that passes it exactly as the hook
# reads it; an unpreviewed field gives the reason no input is needed. The probe below requires the
# lines to equal those its scan finds, so the citations are checked, not narrated.
EVENT_FIELDS = {
    ("data", "cwd"): ("modelled", "--root", (21725,)),  # _orch_root, via 23566 and 23670
    ("data", "session_id"): ("modelled", "--session-id", (23577, 23684)),
    ("data", "stop_hook_active"): ("modelled", "--stop-hook-active", (23468,)),  # via 23580, 23694
    ("data", "tool_name"): ("modelled", "--tool", (23687,)),
    ("data", "tool_input"): ("modelled", "--tool-stop and --wake-text", (23691,)),
    ("tool_input", "stop"): ("modelled", "--tool-stop", (23692,)),
    ("tool_input", "values()"): ("modelled", "--wake-text", (23693,)),
    ("tool_input", "prompt"): ("unpreviewed", "read only after an allowed schedule verdict, for the "
                               "wake-digest write (_orch_register_wake, aiqt_hooks.py:23641-23663); "
                               "it never changes the verdict", (23751,)),
}
# The handlers the doctor previews: preflight stop (Stop) and preflight idle (a scheduling call).
PREVIEWED_HANDLERS = ("orch_stop_guard", "orch_yield_tool")
# The event fields whose value is an object the hook reads field by field.
CONTAINER_FIELDS = ("tool_input",)


def event_field_reads(source, handlers=PREVIEWED_HANDLERS):
    """(reads, unreviewed) over the hook source. reads maps (container, field) to the set of lines
    that read it, traced from the event parameter of each handler through every module function the
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
                reads.setdefault((container, field), set()).add(node.lineno)
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
        for key, (status, detail, lines) in EVENT_FIELDS.items():
            with self.subTest(field=key):
                self.assertIn(status, ("modelled", "unpreviewed"))
                self.assertTrue(detail, "no doctor input or reason")
                self.assertEqual(reads[key], set(lines), "the cited hook lines are stale")

    def test_every_modelled_input_is_a_doctor_option(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        r = run_doctor_recorded(self, [sys.executable, "-I", str(DOCTOR), "--help"], capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        source = DOCTOR.read_text(encoding="utf-8")
        for key, (status, detail, _lines) in EVENT_FIELDS.items():
            if status != "modelled":
                continue
            for option in detail.split(" and "):
                with self.subTest(field=key, option=option):
                    self.assertIn(option, r.stdout)
        for _key, (_status, _detail, lines) in EVENT_FIELDS.items():
            for line in lines:
                self.assertIn(":{}".format(line), source, "the doctor docstring omits a cited line")

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
        # `counter_warn` at aiqt_hooks.py:23724-23747: the scheduling path ignores a failed counter
        # save, so its DENY stands on the stop kind too, unlike the Stop event
        # (`_orch_record_denial` at aiqt_hooks.py:23591-23597).
        if os.geteuid() == 0:
            self.skipTest("root writes a mode-0444 file, so the save cannot fail here")
        self._arm()
        self.seed_state("turn-state.json", {})
        os.chmod(self.state_dir() / "turn-state.json", 0o444)
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
    """The checkpoint union writes the checkpoint (`_orch_write_json_atomic` at
    aiqt_hooks.py:23376) and, when that succeeds and no init marker exists (`os.path.lexists` at
    23387), the marker (`_orch_write_json_atomic` at 23392), whose failure injects a
    cannot-evaluate row (`injected.append` at 23397). The doctor predicts each outcome without
    writing, so its verdict equals that of the real hook on the same state. Each case arranges a
    fresh tree per kind, runs the doctor first (it writes nothing) and then the hook."""

    # Each preflight runs the stage-2 enumerator, so the bound is RUN_TIMEOUT. The fault-injection run,
    # a preflight and then a hook call, runs it twice and has twice the bound.
    TIMEOUT = RUN_TIMEOUT
    # A doctor that refuses a write that could block must do so well inside this bound.
    PROMPT = 15

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
            return run_doctor_recorded(self, [sys.executable, "-I", str(DOCTOR), *args, "--root",
                                              str(self.repo)],
                                       capture_output=True, text=True, env=self._env(),
                                       timeout=self.TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the doctor did not exit within {} s".format(self.TIMEOUT))

    def _hook(self, kind):
        r = self.stop() if kind == "stop" else self.schedule()
        if kind == "stop" and r.returncode == 2:
            return "DENY", r
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        if out is None:
            return "ALLOW", r
        if out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
            return "DENY", r
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

    def _marker_events(self):
        rows = self.read_jsonl("guard-events.jsonl") or []
        return [row for row in rows if row.get("kind") == "checkpoint-marker-unwritable"]

    def _faulted(self, kind, prog=None):
        """Run FAULT_PROG on the current tree: the doctor and then the hook, in one python3 -I
        process, each with the same injected failure of the init-marker write. Returns its JSON
        report."""
        try:
            r = run_doctor_recorded(self, [sys.executable, "-I", "-c", prog or FAULT_PROG, str(DOCTOR),
                                           str(self.repo), kind], capture_output=True, text=True,
                                    env=self._env(), timeout=self.TIMEOUT * 2)
        except subprocess.TimeoutExpired:
            self.fail("the fault-injection run did not exit within {} s".format(self.TIMEOUT * 2))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_a_failed_marker_write_denies_as_the_hook_does(self):
        # The hook rewrites the checkpoint, finds no marker, and its marker write fails, so it
        # injects a cannot-evaluate row and denies (aiqt_hooks.py:23387-23399). The pack writer
        # creates its temporary file under a random name and the two writes share one directory,
        # so no arrangement of files makes the checkpoint rewrite succeed and the marker write
        # fail; the failure is therefore injected, identically, into the doctor's prediction for
        # the marker path and into the real hook's writer for that path (it returns a failure
        # detail, the writer's own failure form, and writes nothing). The doctor's verdict is then
        # held to the real hook's verdict on the same state, as the file-based case was.
        for kind in ("stop", "idle"):
            with self.subTest(kind=kind):
                self._fresh(lambda: None)
                out = self._faulted(kind)
                self.assertEqual(out["doctor_rc"], 1, out["doctor_out"])
                self.assertIn("effective verdict: DENY", out["doctor_out"])
                self.assertIn("init-marker write (aiqt_hooks.py:23392): would FAIL (",
                              out["doctor_out"])
                self.assertIn("checkpoint-init marker unwritable", out["doctor_out"])
                self.assertEqual(out["hook_verdict"], "DENY", out)
                self.assertIn("(cannot-evaluate): backlog-checkpoint", out["hook_text"])
                self.assertIn("checkpoint-init marker checkpoint-init.marker could not be written",
                              out["hook_text"])
                self.assertEqual(len(self._marker_events()), 1,
                                 "the hook recorded the failed marker write")
                self.assertFalse((self.state_dir() / "checkpoint-init.marker").exists())
                self.assertTrue((self.state_dir() / "backlog-checkpoint.json").exists(),
                                "precondition: the checkpoint rewrite succeeded")

    def _assert_legacy_entries_harmless(self, makers):
        # The hook writer never opens a fixed temporary path: it creates a fresh randomly named
        # file with O_CREAT|O_EXCL|O_NOFOLLOW and replaces the target with it
        # (aiqt_hooks.py:22266-22287). An entry at the old fixed sibling <name>.tmp is therefore
        # ignored: the hook writes the checkpoint and the marker and allows, and the doctor must
        # predict both writes and the same ALLOW, on the same state. The hook runs under a timeout
        # here, so a write that did block would fail the case rather than hang it.
        for what, make in makers:
            for name in ("checkpoint-init.marker.tmp", "backlog-checkpoint.json.tmp"):
                with self.subTest(entry=what, path=name):
                    self._assert_agrees(lambda: make(name), "ALLOW",  # both via _orch_write_json_atomic
                                        "checkpoint rewrite (aiqt_hooks.py:23376): would succeed",
                                        "init-marker write (aiqt_hooks.py:23392): would succeed")
                    self.assertEqual(self._marker_events(), [], "no failed marker write")
                    self.assertTrue((self.state_dir() / "checkpoint-init.marker").is_file(),
                                    "the hook wrote the marker")
                    self.assertTrue(os.path.lexists(self.state_dir() / name),
                                    "the hook left the legacy entry alone")

    def test_an_obstruction_at_a_legacy_temporary_path_no_longer_fails_a_write(self):
        # A directory or a read-only file at <name>.tmp made the earlier writer's open for writing
        # fail, so the marker write failed and the hook denied. The vendored writer never opens
        # that path, so the hook now allows, and the doctor must agree.
        def directory(name):
            (self.state_dir() / name).mkdir()

        def read_only(name):
            tmp = self.state_dir() / name
            tmp.write_text("", encoding="utf-8")
            os.chmod(tmp, 0o444)
        self._assert_legacy_entries_harmless((("a directory", directory),
                                              ("a read-only file", read_only)))

    def test_a_blocking_or_linked_legacy_temporary_path_is_previewed_promptly(self):
        # A FIFO, a symbolic link to a FIFO or a symbolic link to a regular file at <name>.tmp
        # could block the earlier writer's open or be followed by it, so the doctor refused to
        # preview them. The vendored writer opens no existing entry (O_EXCL on a fresh name), so
        # the hook neither blocks nor follows, and the doctor previews the same ALLOW, inside the
        # timeout of _doctor.
        def fifo(name):
            os.mkfifo(self.state_dir() / name)

        def link_to_fifo(name):
            target = self._tmp / "elsewhere.fifo"
            os.mkfifo(target)
            os.symlink(target, self.state_dir() / name)

        def link_to_file(name):
            target = self._tmp / "elsewhere.json"
            target.write_text("", encoding="utf-8")
            os.symlink(target, self.state_dir() / name)
        self._assert_legacy_entries_harmless((("a FIFO", fifo),
                                              ("a symbolic link to a FIFO", link_to_fifo),
                                              ("a symbolic link to a regular file", link_to_file)))

    def test_a_failed_checkpoint_rewrite_skips_the_marker_write_as_the_hook_does(self):
        # Contrast: the state directory cannot be written, so the checkpoint rewrite fails first
        # and the hook never reaches the marker write (aiqt_hooks.py:23376-23387), though the
        # marker write would fail too; the hook allows and reports the failed rewrite with the
        # allow (`_stop_warn` at :23622-23624, `_allow_note` at :23776-23779), and the doctor must
        # report the same.
        if os.geteuid() == 0:
            self.skipTest("root writes into a mode-0555 directory, so the rewrite cannot fail here")

        def arrange():
            os.chmod(self.state_dir(), 0o555)
        self._assert_agrees(arrange, "ALLOW_WITH_FINDINGS",  # the rewrite: _orch_write_json_atomic
                            "checkpoint rewrite (aiqt_hooks.py:23376): would FAIL",
                            "init-marker write (aiqt_hooks.py:23392): not reached")

    def test_a_present_marker_is_not_rewritten_as_the_hook_does(self):
        # Contrast: with a checkpoint and a marker present, the hook skips the marker write
        # (`os.path.lexists` at 23387).
        def arrange():
            self.seed_state("backlog-checkpoint.json", {"version": 1, "ts": _iso(), "ids": {}})
            self.seed_state("checkpoint-init.marker", {"version": 1, "ts": _iso()})
        self._assert_agrees(arrange, "ALLOW", "init-marker write (aiqt_hooks.py:23392): not reached")

    def test_a_write_the_preview_does_not_model_is_not_previewed(self):
        # The doctor models exactly the two writes the WRITE_SITES table marks modelled. A hook
        # whose context build wrote any other path would reach the stand-in with that path, and
        # the doctor must then refuse to give a verdict (exit 2) and write nothing, as it refused an
        # undecidable write before. The added write is injected into the hook the doctor loads.
        for kind in ("stop", "idle"):
            with self.subTest(kind=kind):
                self._fresh(lambda: None)
                before = tree_state(self._tmp)
                out = self._faulted(kind, UNMODELLED_PROG)
                self.assertEqual(tree_state(self._tmp), before, "preflight changed a file")
                self.assertEqual(out["doctor_rc"], 2, out["doctor_out"])
                self.assertIn("hook write: NOT PREVIEWED; the hook would write ", out["doctor_out"])
                self.assertIn("a write this preview does not model", out["doctor_out"])
                self.assertIn("effective verdict: UNPREVIEWED", out["doctor_out"])


# Runs in a separate python3 -I process: argv is the doctor path, the repository and the preflight
# kind. It runs the doctor (main) with the init-marker write predicted to fail, then the real hook
# handler on the same event with its writer failing that one write (it returns a failure detail and
# writes nothing; every other write is real), and reports both.
FAULT_PROG = """
import contextlib, importlib.util, io, json, sys
spec = importlib.util.spec_from_file_location("orch_doctor_under_test", sys.argv[1])
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
repo, kind = sys.argv[2], sys.argv[3]
MARKER = "checkpoint-init.marker"
real_outcome = doctor._atomic_write_outcome


def predicted(path, *args):
    if path.endswith("/" + MARKER):
        return False, "injected failure of the marker write"
    return real_outcome(path, *args)


doctor._atomic_write_outcome = predicted
args = ["preflight", kind, "--root", repo]
if kind == "idle":
    args[2:2] = ["--wake-text", "recheck the work queue"]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    doctor_rc = doctor.main(args)
hook = doctor._load_hook()
real_write = hook._orch_write_json_atomic


def failing(path, obj):
    if path.endswith("/" + MARKER):
        return "OSError"
    return real_write(path, obj)


hook._orch_write_json_atomic = failing
if kind == "stop":
    code, out, err = hook.orch_stop_guard({"cwd": repo})
else:
    code, out, err = hook.orch_yield_tool({"cwd": repo, "tool_name": "ScheduleWakeup",
                                           "tool_input": {"prompt": "recheck the work queue",
                                                          "delaySeconds": 60}})
if code == 2:
    verdict = "DENY"
elif out is None:
    verdict = "ALLOW"
elif out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
    verdict = "DENY"
else:
    verdict = "ALLOW_WITH_FINDINGS"
print(json.dumps({"doctor_rc": doctor_rc, "doctor_out": buf.getvalue(), "hook_verdict": verdict,
                  "hook_text": json.dumps(out) + str(err)}))
"""

# The same process shape: the doctor runs on a hook whose checkpoint union first writes a state path
# the preview does not model; the hook handler is not run.
UNMODELLED_PROG = """
import contextlib, importlib.util, io, json, os, sys
spec = importlib.util.spec_from_file_location("orch_doctor_under_test", sys.argv[1])
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)
repo, kind = sys.argv[2], sys.argv[3]
real_load = doctor._load_hook


def load():
    hook = real_load()
    union = hook._orch_checkpoint_union

    def extra(root, *a, **k):
        hook._orch_write_json_atomic(
            os.path.join(hook._orch_state_dir_for_root(root), "unmodelled.json"), {})
        return union(root, *a, **k)
    hook._orch_checkpoint_union = extra
    return hook


doctor._load_hook = load
args = ["preflight", kind, "--root", repo]
if kind == "idle":
    args[2:2] = ["--wake-text", "recheck the work queue"]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    doctor_rc = doctor.main(args)
print(json.dumps({"doctor_rc": doctor_rc, "doctor_out": buf.getvalue()}))
"""


# Runs in a separate python3 -I process: load the doctor by path and call its preview path
# (_build_ctx_previewed) in that process, with _atomic_write_outcome wrapped by a spy that records
# whether both stand-ins are installed when the stand-in write runs and, for the interrupt case,
# raises KeyboardInterrupt there; then report whether the two hook functions are the original
# objects again.
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


def spy(path, *args):
    seen.append(hook._orch_write_json_atomic is not orig_write
                and hook._orch_guard_event is not orig_event)
    if case == "interrupt":
        raise KeyboardInterrupt
    if case == "unpreviewed":
        raise doctor._Unpreviewed("raised inside the stand-in write")
    return real_outcome(path, *args)


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

    # The context build runs the stage-2 enumerator, so the bound is RUN_TIMEOUT.
    TIMEOUT = RUN_TIMEOUT

    def _run(self, case):
        r = run_doctor_recorded(self, [sys.executable, "-I", "-c", RESTORE_PROG, str(DOCTOR),
                                       str(self.repo), case],
                                capture_output=True, text=True, env=self._env(), timeout=self.TIMEOUT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_the_stand_ins_are_restored_however_the_preview_ends(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        # The pack writer leaves no file arrangement that the preview cannot decide, so the
        # not-previewed exception is raised inside the stand-in write, as the interrupt is; the
        # restore must hold however the stand-in ends.
        cases = (("normal", None, "returned"), ("unpreviewed", None, "unpreviewed"),
                 ("interrupt", None, "interrupted"))
        for case, arrange, ended in cases:
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                self.write_registry(self.stage2())
                self.arm_lease()
                self.set_items([])
                self.state_dir().mkdir(parents=True, exist_ok=True)
                if arrange is not None:
                    arrange()
                out = self._run(case)
                self.assertEqual(out["status"], "ok", out)
                self.assertEqual(out["ended"], ended, out)
                self.assertTrue(out["seen"], "the stand-in write was never reached: {}".format(out))
                self.assertTrue(all(out["seen"]), "a stand-in was not installed: {}".format(out))
                self.assertTrue(out["write_restored"], out)
                self.assertTrue(out["event_restored"], out)


# Every write the hook makes inside _orch_build_ctx and the module functions it
# calls, keyed (function, callee, line). "modelled" is a write whose failure changes the verdict and
# whose outcome the doctor predicts (_atomic_write_outcome through _build_ctx_previewed); "no
# verdict effect" is a write whose result no caller on the path reads, with the reason.
WRITE_SITES = {
    ("_orch_checkpoint_union", "_orch_write_json_atomic", 23376): (
        "modelled", "the checkpoint rewrite; a failure skips the init-marker write "
        "(os.path.lexists 23387) and adds a recording-failure warning"),
    ("_orch_checkpoint_union", "_orch_write_json_atomic", 23392): (
        "modelled", "the init-marker write; a failure injects a cannot-evaluate row (injected.append 23397)"),
    ("_orch_event_warn", "_orch_guard_event", 22316): (
        "no verdict effect", "the guard-events row of each checkpoint event; a failed append "
        "adds a warning to the output and never changes the decision (22311-22319)"),
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
    """The set of (function, callee, line) for every write reached from start through the module
    functions it calls: a call of a write primitive (not followed further), an open whose mode is
    not a literal read mode, an os.open with a write flag, an os or shutil call in FS_WRITERS, and a
    call of a write method."""
    tree = ast.parse(source)
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
                    sites.add((name, f.id, node.lineno))
                elif f.id == "open":
                    mode = node.args[1] if len(node.args) > 1 else next(
                        (k.value for k in node.keywords if k.arg == "mode"), None)
                    if not (mode is None or (isinstance(mode, ast.Constant)
                                             and mode.value in ("r", "rb", "rt"))):
                        sites.add((name, "open", node.lineno))
                elif f.id in funcs:
                    work.append(f.id)
            elif isinstance(f, ast.Attribute):
                owner = f.value.id if isinstance(f.value, ast.Name) else None
                if owner in ("os", "shutil") and f.attr in FS_WRITERS:
                    sites.add((name, owner + "." + f.attr, node.lineno))
                elif owner == "os" and f.attr == "open":
                    flags = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
                    if flags.intersection(WRITE_FLAGS):
                        sites.add((name, "os.open", node.lineno))
                elif f.attr in WRITE_METHODS:
                    sites.add((name, "." + f.attr, node.lineno))
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
        for _func, _callee, line in WRITE_SITES:
            self.assertIn(":{}".format(line), source, "the doctor docstring omits a cited line")

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


def hook_claim_problem(functions, constants, hook_lines, func_name, first, last, check):
    """None when the claim of OPEN_ACCOUNTS holds in the hook source, else what is wrong with it."""
    func = functions.get(func_name)
    if func is None:
        return "no top-level function {}".format(func_name)
    if not func.lineno <= first <= last <= func.end_lineno:
        return "the lines are not in {}".format(func_name)
    if check[0] == "run":
        if first != last or "subprocess.run(" not in hook_lines[first - 1]:
            return "no subprocess.run call on the line"
        return None
    if check[0] == "open":
        calls = [node for node in ast.walk(func) if isinstance(node, ast.Call)
                 and ast.unparse(node.func) == "os.open" and first <= node.lineno <= last]
        if len(calls) != 1:
            return "{} os.open calls in the lines".format(len(calls))
        call = calls[0]
        flag_nodes = [call]
        for name in {n.id for arg in call.args for n in ast.walk(arg) if isinstance(n, ast.Name)}:
            flag_nodes += [node for node in ast.walk(func) if isinstance(node, ast.Assign)
                           and [ast.unparse(t) for t in node.targets] == [name]
                           and first <= node.lineno <= last]
        flags = set()
        for top in flag_nodes:
            for node in ast.walk(top):
                if isinstance(node, ast.Attribute) and ast.unparse(node.value) == "os":
                    flags.add(node.attr)
                elif isinstance(node, ast.Call) and ast.unparse(node.func) == "getattr" \
                        and len(node.args) >= 2 and ast.unparse(node.args[0]) == "os" \
                        and isinstance(node.args[1], ast.Constant):
                    flags.add(node.args[1].value)
        missing = [flag for flag in check[1] if flag not in flags]
        if missing:
            return "the open does not carry {}".format(missing)
        span = (min(node.lineno for node in flag_nodes), max(node.end_lineno for node in flag_nodes))
        if span != (first, last):
            return "the open and its flags span {}-{}".format(*span)
        return None
    _kind, test, start, needed = check
    ifs = [node for node in ast.walk(func) if isinstance(node, ast.If) and node.lineno == first]
    if len(ifs) != 1:
        return "no if statement starts on the line"
    node = ifs[0]
    if ast.unparse(node.test) != test:
        return "the test reads {!r}".format(ast.unparse(node.test))
    if not ast.unparse(node.body[0]).startswith(start):
        return "the body starts {!r}".format(ast.unparse(node.body[0]))
    if node.body[-1].end_lineno != last:
        return "the body ends on {}".format(node.body[-1].end_lineno)
    if any(isinstance(n, ast.Call) and ast.unparse(n.func) == "os.read" for s in node.body
           for n in ast.walk(s)):
        return "the body reads the file"
    for name, value in needed.items():
        if constants.get(name) != value:
            return "{} is {!r}, not {!r}".format(name, constants.get(name), value)
    return None


class DoctorPrecheckSiteProbe(unittest.TestCase):
    """Class probe: the reachability table covers every pre-check site in the doctor, every
    checked path reaches _special_path only through _first_special over _site entries, every
    site has a reach case and, where it has an early exit, a contrast case, each open of
    PRECHECK_OPENS and each claim of OPEN_ACCOUNTS holds at source, the doctor's refusal texts equal
    those of OPEN_ACCOUNTS, the label table covers every site, and every string literal of this file
    that holds a part of a pre-check refusal is in assert_refusal or a table that words the refusal."""

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
        self.assertEqual(sorted(PRECHECK_LABELS), sorted(PRECHECK_SITES),
                         "the label table and the reachability table differ")
        for site, (_command, early_exit, _condition, citation) in PRECHECK_SITES.items():
            with self.subTest(site=site):
                expects = {e for s, e, _c in PRECHECK_CASES if s == site}
                self.assertIn("reach", expects, "no case where the hook reaches the open")
                if early_exit:
                    self.assertIn("skip", expects, "no contrast case for the early exit")
                self.assertTrue(citation, "no hook citation")
        for _site_id, _expect, case in PRECHECK_CASES:
            self.assertTrue(callable(getattr(DoctorPrecheckSites, case, None)), case)

    def test_each_site_open_follows_the_hook(self):
        # PRECHECK_OPENS covers every site, each open it gives is in the named hook function and
        # opens the path as its kind says, every claim of OPEN_ACCOUNTS holds at source, each account
        # cites exactly the lines of its claims, and the doctor words each site exactly as
        # OPEN_ACCOUNTS, BLOCKING_TEXT, READER_END and ENUMERATOR_END say.
        self.assertEqual(sorted(PRECHECK_OPENS), sorted(PRECHECK_SITES),
                         "the open table and the reachability table differ")
        hook_source = HOOK.read_text(encoding="utf-8")
        hook_lines = hook_source.split("\n")
        hook_tree = ast.parse(hook_source)
        functions = {node.name: node for node in hook_tree.body if isinstance(node, ast.FunctionDef)}
        constants = {node.targets[0].id: node.value.value for node in hook_tree.body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1
                     and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)}
        for site, (kind, opens) in PRECHECK_OPENS.items():
            for reader, first, last in opens:
                with self.subTest(site=site, line=first):
                    if kind == "blocking":
                        self.assertEqual(first, last, "a blocking open is cited by its line")
                        self.assertIn(reader, functions)
                        func = functions[reader]
                        self.assertTrue(func.lineno <= first <= func.end_lineno,
                                        "the cited line is not in {}".format(reader))
                        self.assertRegex(hook_lines[first - 1], r"\bwith open\(")
                        self.assertNotIn("O_NONBLOCK", hook_lines[first - 1])
                    else:
                        account = OPEN_ACCOUNTS.get(reader)
                        self.assertIsNotNone(account, "no account of {}".format(reader))
                        self.assertEqual(account[1][0][:3], (reader, first, last),
                                         "the account of {} does not start with this open".format(reader))
                        self.assertEqual(account[1][0][3][0], "open" if kind == "non-blocking" else "run")
        for reader, (text, claims) in OPEN_ACCOUNTS.items():
            with self.subTest(account=reader):
                cited = {(int(a), int(b or a)) for a, b in HOOK_CITATION.findall(text)}
                self.assertEqual(cited, {(first, last) for _f, first, last, _c in claims},
                                 "the account cites a line that no claim checks, or a claim is not cited")
                self.assertEqual(len(cited), len(claims), "2 claims share a range")
                for func_name, first, last, check in claims:
                    problem = hook_claim_problem(functions, constants, hook_lines, func_name, first, last,
                                                 check)
                    self.assertIsNone(problem, "{} {}-{}: {}".format(func_name, first, last, problem))
        tree = ast.parse(DOCTOR.read_text(encoding="utf-8"))
        texts, site_open, site_end = {}, None, None
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    texts[name] = value.value
                elif name in ("SITE_OPEN", "SITE_END") and isinstance(value, ast.Dict):
                    table = {}
                    for key, item_node in zip(value.keys, value.values):
                        self.assertIsInstance(key, ast.Constant, "a {} key is not a literal".format(name))
                        if isinstance(item_node, ast.Name):
                            self.assertIn(item_node.id, texts, "an unresolved {} value".format(name))
                            table[key.value] = texts[item_node.id]
                        else:
                            self.assertIsInstance(item_node, ast.Constant, "a {} value".format(name))
                            table[key.value] = item_node.value
                    if name == "SITE_OPEN":
                        site_open = table
                    else:
                        site_end = table
        self.assertIsNotNone(site_open, "the doctor defines no SITE_OPEN table")
        self.assertIsNotNone(site_end, "the doctor defines no SITE_END table")
        self.assertEqual(sorted(site_open),
                         sorted(site for site, (kind, _o) in PRECHECK_OPENS.items() if kind != "blocking"),
                         "SITE_OPEN words a different set of sites than the non-blocking and "
                         "enumerator sites of PRECHECK_OPENS")
        self.assertEqual(sorted(site_end),
                         sorted(site for site, (kind, _o) in PRECHECK_OPENS.items() if kind == "enumerator"),
                         "SITE_END ends the refusal differently at a site that a hook reader opens")
        self.assertEqual(texts.get("BLOCKING_OPEN"), BLOCKING_TEXT)
        self.assertEqual(texts.get("REFUSAL_END"), READER_END)
        for site, (kind, _opens) in PRECHECK_OPENS.items():
            with self.subTest(site=site):
                self.assertEqual(site_open.get(site, texts.get("BLOCKING_OPEN")), expected_open_text(site))
                self.assertEqual(site_end.get(site, texts.get("REFUSAL_END")),
                                 ENUMERATOR_END if kind == "enumerator" else READER_END)
                # No refusal says both that the hook does not open the path and that a hook reader
                # opens it.
                tail = expected_tail(site)
                if kind == "enumerator":
                    self.assertNotIn("reader that opens it", tail)
                else:
                    self.assertNotIn("does not open it", tail)

    # Where a string may hold a part of a pre-check refusal: the helper that checks the whole line, the
    # tables that word the refusal (the labels included), the words of the doctor's open account that
    # DoctorOpenAccountHolders searches for and the samples of them in its self-test, the recorder's
    # prefix and the self-test of its cleanup, and this probe.
    REFUSAL_HOLDERS = {"assert_refusal", "PRECHECK_LABELS", "OPEN_ACCOUNTS", "BLOCKING_TEXT", "READER_END",
                       "ENUMERATOR_END", "OPEN_ACCOUNT_WORDS", "REFUSAL_PREFIX", "REFUSAL_HEAD",
                       "REFUSAL_MIDDLE",
                       "refusal_skeleton", "refusal_pieces", "refusal_reach", "refusal_fragments_outside",
                       "test_every_refusal_check_reads_the_whole_wording",
                       "test_the_cleanup_fails_a_refusal_that_assert_refusal_did_not_check",
                       "test_the_open_account_is_worded_only_in_its_tables"}
    # The fragments that open every pre-check refusal ("cannot evaluate: the <label> <path> is not a
    # regular file (it is a <made>); <tail>"), which a string that holds any of them anywhere holds a
    # part of the refusal by, and the words of the line between the path and the type.
    # assert_barrier_refusal checks the barrier refusal of the resume audit, which is not a pre-check
    # refusal but also says "<path> is not a regular file (it is a <made>)", so there only "cannot
    # evaluate" of the fragments counts, and the words of REFUSAL_MIDDLE count for no rule.
    REFUSAL_HEAD = ("cannot evaluate", "is not a regular file", "(it is a ")
    REFUSAL_MIDDLE = " is not a regular file (it is a "
    BARRIER_HELPER = "assert_barrier_refusal"
    # The gaps of the refusal line that the path and the file type fill: the path is any text without
    # white space, and the type any text without ";".
    PATH_GAP = "<path>"
    TYPE_GAP = "<made>"
    # A piece of a string (refusal_pieces) holds a part of the refusal at a site when, as a whole, it
    # lines up with a stretch of the refusal line and touches PIECE_WORDS or more of the line's words, or
    # when a stretch of it lines up with SPAN_WORDS or more whole words of the line (refusal_reach).
    PIECE_WORDS = 2
    SPAN_WORDS = 4

    def refusal_skeleton(self, site, barrier):
        """The refusal line at site as a tuple of (char, word): char is a character of its fixed text, in
        lower case, or PATH_GAP or TYPE_GAP for the gap that the path or the file type fills; word numbers
        each run of the fixed text without white space that holds a letter or a digit, and is None for
        white space, a gap, a run without a letter or a digit, and, with barrier (in BARRIER_HELPER), the
        words of REFUSAL_MIDDLE."""
        parts = (("cannot evaluate: the " + PRECHECK_LABELS[site] + " ", True), (self.PATH_GAP, None),
                 (self.REFUSAL_MIDDLE, not barrier), (self.TYPE_GAP, None),
                 ("); " + expected_tail(site), True))
        skeleton, words = [], 0
        for text, counted in parts:
            if counted is None:
                skeleton.append((text, None))
                continue
            for run in re.findall(r"\s+|\S+", text.lower()):
                word = None
                if counted and not run.isspace() and any(ch.isalnum() for ch in run):
                    words += 1
                    word = words
                skeleton.extend((ch, word) for ch in run)
        return tuple(skeleton)

    @staticmethod
    def refusal_pieces(text):
        """The pieces of text, each in lower case with each run of white space made 1 space: text split at
        each line break and at each regular-expression anchor (^ or $), alternation (|), inline group
        ("(?" to ")"), wildcard (".*", ".+" or ".?") and escape of a letter or a digit, other than "\\s",
        "\\s+" and "\\s*", which stand for a space; any other escaped character stands for itself."""
        def token(match):
            found = match.group(0)
            if re.fullmatch(r"\\s[*+?]?", found):
                return " "
            if re.fullmatch(r"\\[^0-9A-Za-z]", found):
                return found[1]
            return "\n"
        flat = re.sub(r"\\s[*+?]?|\\[0-9A-Za-z][*+?]?|\\.|\.[*+?]|\(\?[^)]*\)|[\^$|]", token, text)
        return [" ".join(piece.split()).lower() for piece in flat.splitlines() if piece.strip()]

    def refusal_reach(self, piece, skeleton):
        """(whole, span) for piece against skeleton (refusal_skeleton). whole is the most words of the
        line that piece touches at a letter or a digit when the whole of piece lines up with a stretch of
        the line, and 0 when it does not; span is the most whole words of the line that a stretch of piece
        lines up with, from the start of a word of the line to the end of one."""
        size = len(skeleton)
        gaps = [k for k, (char, _word) in enumerate(skeleton) if char in (self.PATH_GAP, self.TYPE_GAP)]
        starts = [k for k, (_char, word) in enumerate(skeleton)
                  if word is not None and (k == 0 or skeleton[k - 1][1] != word)]
        ends = {k + 1 for k, (_char, word) in enumerate(skeleton)
                if word is not None and (k + 1 == size or skeleton[k + 1][1] != word)}

        def keep(states, k, value):
            if k not in states or states[k][0] < value[0]:
                states[k] = value

        def advance(states, ch):
            # states maps a position of the line to (words touched, last word touched).
            for k in gaps:
                if k in states:   # a gap may hold no text
                    keep(states, k + 1, states[k])
            after = {}
            for k, (count, last) in states.items():
                if k == size:
                    continue
                char, word = skeleton[k]
                if char == self.PATH_GAP:
                    if not ch.isspace():
                        keep(after, k, (count, last))
                elif char == self.TYPE_GAP:
                    if ch != ";":
                        keep(after, k, (count, last))
                elif char == ch:
                    touches = word is not None and word != last and ch.isalnum()
                    keep(after, k + 1, (count + 1, word) if touches else (count, last))
            return after

        whole = {k: (0, None) for k in range(size + 1)}
        spans, span = {}, 0
        for ch in piece:
            whole = advance(whole, ch)
            for k in starts:
                keep(spans, k, (0, None))
            spans = advance(spans, ch)
            span = max([span] + [count for k, (count, _last) in spans.items() if k in ends])
        return (max([count for count, _last in whole.values()], default=0), span)

    def refusal_fragments_outside(self, source):
        """A secondary check, a lexical tripwire beside the recorder (run_doctor_recorded), which is the
        check that a refusal case reads the whole line. (enclosing name, line, text) for every string or
        bytes literal of source that holds a part of a pre-check refusal outside REFUSAL_HOLDERS, other than a docstring, what an assertNotIn call
        (its member) or an assertNotRegex call (its unexpected_regex) looks for, a check that a refusal
        is absent, and the label, path and type given to assert_refusal, which checks the whole line
        with them. A literal holds a part of a pre-check refusal when it holds a fragment of
        REFUSAL_HEAD, or when a piece of it (refusal_pieces) reaches PIECE_WORDS as a whole or
        SPAN_WORDS in a stretch (refusal_reach) against the refusal line at any site
        (refusal_skeleton), the label and the tail of the site included."""
        tree = ast.parse(source)
        looked_for = {"assertNotIn": (0, "member"), "assertNotRegex": (1, "unexpected_regex")}
        exempt = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                exempt.add(id(node.value))
            elif isinstance(node, ast.Call):
                kept = []
                if isinstance(node.func, ast.Attribute) and node.func.attr in looked_for:
                    index, name = looked_for[node.func.attr]
                    kept = node.args[index:index + 1] + [k.value for k in node.keywords if k.arg == name]
                elif isinstance(node.func, ast.Name) and node.func.id == "assert_refusal":
                    kept = node.args[3:] + [k.value for k in node.keywords
                                            if k.arg in ("label", "path", "made")]
                for arg in kept:
                    exempt.update(id(n) for n in ast.walk(arg))
        skeletons = {barrier: {self.refusal_skeleton(site, barrier) for site in PRECHECK_OPENS}
                     for barrier in (False, True)}
        outside = []

        def holds(text, chain):
            barrier = self.BARRIER_HELPER in chain
            pieces = self.refusal_pieces(text)
            if any(fragment in candidate for fragment in self.REFUSAL_HEAD
                   if not barrier or fragment == "cannot evaluate"
                   for candidate in [" ".join(text.lower().split())] + pieces):
                return True
            for piece in pieces:
                if " " not in piece:   # neither rule can hold without a space
                    continue
                for skeleton in skeletons[barrier]:
                    whole, span = self.refusal_reach(piece, skeleton)
                    if whole >= self.PIECE_WORDS or span >= self.SPAN_WORDS:
                        return True
            return False

        def visit(node, chain):
            for child in ast.iter_child_nodes(node):
                inner = chain
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    inner = chain + (child.name,)
                elif isinstance(child, ast.Assign):
                    inner = chain + tuple(t.id for t in child.targets if isinstance(t, ast.Name))
                if isinstance(child, ast.Constant) and isinstance(child.value, (str, bytes)) \
                        and id(child) not in exempt and not self.REFUSAL_HOLDERS & set(chain):
                    text = child.value if isinstance(child.value, str) else child.value.decode("latin-1")
                    if holds(text, chain):
                        outside.append((chain[-1] if chain else "<module>", child.lineno, child.value))
                visit(child, inner)

        visit(tree, ())
        return outside

    def test_every_refusal_check_reads_the_whole_wording(self):
        # A secondary check. The check that each case reads the whole refusal line is the recorder
        # (run_doctor_recorded and DoctorRefusalCoverage), which does not read the text of a check.
        # This lexical tripwire flags a string literal of this file that holds a part of a doctor
        # refusal at a pre-check site (refusal_fragments_outside) outside assert_refusal, the label, path
        # and type given to it, the tables that word the refusal and this probe. Beyond it: a check
        # that names a holder of such text (such as READER_END) rather than a literal, a check that
        # builds its text from pieces that each hold less than a part, such as 1 word of the line, or 2
        # or 3 of its words beside other text, and a regular expression that spells the words with
        # other constructs than those that refusal_pieces reads. The self-test below shows it flagging
        # the listed partial checks and passing the listed checks that a refusal is absent.
        self.assertEqual(self.refusal_fragments_outside(Path(__file__).read_text(encoding="utf-8")), [],
                         "a refusal checked outside assert_refusal")
        tail = expected_tail("scope.lease")
        for partial in ('self.assertIn("cannot evaluate: the declared lease.path", r.stdout)',
                        'self.assertIn("is not a regular file (it is a directory)", r.stdout)',
                        'self.assertIn("(it is a directory); ", r.stdout)',
                        'self.assertIn({!r}, r.stdout)'.format(tail),
                        'self.assertIn({!r}, r.stdout)'.format(READER_END),
                        'self.assertIn("would open it with", r.stdout)',
                        'self.assertTrue("no enumerator ran" in r.stdout)',
                        # Parts with none of the fragments of REFUSAL_HEAD: the middle, the label, the
                        # middle with the type, the type with the start of the tail, a bytes literal, a
                        # regular expression, a part inside other text, and the text and the pattern of
                        # an assertNotRegex call swapped.
                        'self.assertIn("not a regular file", r.stdout)',
                        'self.assertIn("the declared lease.path", r.stdout)',
                        'self.assertIn("a regular file (it is", r.stdout)',
                        'self.assertIn("it is a directory); the hook", r.stdout)',
                        'self.assertIn(b"declared lease.path", r.stdout)',
                        'self.assertRegex(r.stdout, r"^the declared lease\\.path\\s+\\S+ is")',
                        'self.assertIn("error: the declared lease.path /x is not a", r.stdout)',
                        'self.assertNotRegex("cannot evaluate", r.stdout)'):
            with self.subTest(partial=partial):
                source = "def test_partial(self, r):\n    {}\n".format(partial)
                self.assertEqual(len(self.refusal_fragments_outside(source)), 1)
        for fine in ('self.assertNotIn("cannot evaluate", r.stdout)',
                     'self.assertNotIn("blocking open", r.stdout)',
                     'self.assertFalse(marker.exists(), "the enumerator ran")',
                     'self.assertNotRegex(r.stdout, "cannot evaluate")',
                     'self.assertNotIn(member="cannot evaluate", container=r.stdout)',
                     'self.assertNotRegex(r.stdout, unexpected_regex="cannot evaluate")',
                     'assert_refusal(self, r.stdout, "scope.lease", "declared lease.path", lease, "directory")',
                     'self.assertIn("is not a decision id", r.stdout)'):
            with self.subTest(fine=fine):
                source = "def test_fine(self, r):\n    {}\n".format(fine)
                self.assertEqual(self.refusal_fragments_outside(source), [])
        # The barrier helper may hold the words of REFUSAL_MIDDLE, and nothing else of the refusal.
        helper = "def {}(self, r):\n    self.assertIn({!r}, r.stdout)\n"
        self.assertEqual(self.refusal_fragments_outside(
            helper.format(self.BARRIER_HELPER, "{} is not a regular file (it is a {})")), [])
        self.assertEqual(len(self.refusal_fragments_outside(
            helper.format(self.BARRIER_HELPER, "cannot evaluate: the {}"))), 1)


class DoctorRefusalCoverage(unittest.TestCase):
    """Every process that this file starts goes through run_doctor_recorded, its 1 launcher: _admit
    refuses any other launch in this interpreter, in any thread, told by the identity of the code of its
    frames, that code given to another function, the load of a module that can make a subinterpreter,
    and, in this process, code that holds a doctor refusal (also in a tuple, frozenset or slice
    constant) or a constant of a type that the compiler does not make, when it runs by exec, eval or
    import, when a function is built from it and when it is assigned as the code of a function, and a
    change of its own code or defaults. The recorder registers each output that holds a doctor refusal
    anywhere, fails one whose case is absent or not running, and its cleanup fails a case in which a
    run printed a pre-check refusal or a barrier refusal of the resume audit that assert_refusal or
    assert_barrier_refusal did not check as a whole line. Not seen, as the comment above REFUSAL_PREFIX
    states: output on another channel, a process that native code starts without an audit event, a
    subinterpreter that native code makes other than through INTERPRETER_MODULES, code run in this
    process by a route that raises none of the 3 events, refusal text that is not a string constant,
    and a case that replaces a built-in, replaces with native code a function that the recorder's
    launch calls, changes what the registration and the cleanup read, or gives an object that is not
    running the state of a running case."""

    # The prefixes as the module writes them out, so that a prefix dropped from REFUSAL_PREFIXES fails.
    PREFIXES = (REFUSAL_PREFIX, BARRIER_REFUSAL_PREFIX) + AUDIT_REFUSAL_PREFIXES
    # A child that prints its first operand inside 1 JSON line, sleeps its second and exits with its third.
    PROG = ("import json, sys, time; print(json.dumps({'out': sys.argv[1]}), flush=True); "
            "time.sleep(float(sys.argv[2])); sys.exit(int(sys.argv[3]))")

    def child(self, text, sleep="0", code="0"):
        return [sys.executable, "-I", "-c", self.PROG, text, sleep, code]

    def test_every_launch_goes_through_the_recorder(self):
        # Outside the recorder, a launch by subprocess, os.system or os.fork is refused before it starts
        # anything, in this thread and in a new thread in which the recorder never ran, and the recorder
        # runs in that thread as well. The child of os.fork is told only by the pid 0 that os.fork itself
        # returns, so a launch that is not refused cannot end the test process.
        def fork():
            pid = os.fork()
            if pid == 0:
                os._exit(0)
            os.waitpid(pid, 0)

        plain = self.child("the doctor ran")
        launches = (("subprocess.run", lambda: subprocess.run(plain, capture_output=True, timeout=60)),
                    ("os.system", lambda: os.system("true")),
                    ("os.fork", fork))
        for name, launch in launches:
            with self.subTest(launch=name):
                with self.assertRaisesRegex(RuntimeError, "outside run_doctor_recorded"):
                    launch()

        def in_thread(outcomes):
            for name, launch in launches:
                try:
                    launch()
                    outcomes.append((name, "ran"))
                except RuntimeError as exc:
                    refused = "outside run_doctor_recorded" in str(exc)
                    outcomes.append((name, "refused" if refused else str(exc)))
            r = run_doctor_recorded(None, plain, capture_output=True, text=True, timeout=60)
            outcomes.append(("recorder", r.returncode))

        with self.subTest(thread="new"):
            outcomes = []
            worker = threading.Thread(target=in_thread, args=(outcomes,))
            worker.start()
            worker.join(120)
            self.assertEqual(outcomes, [(name, "refused") for name, _launch in launches] + [("recorder", 0)])
        # Only the frames of the recorder's own call of subprocess.run are admitted, not other code that
        # it calls: os.system in a preexec_fn, which runs in the child before the program starts, is
        # refused there, and subprocess reports that preexec_fn raised.
        with self.subTest(launch="os.system in a preexec_fn"):
            with self.assertRaisesRegex(subprocess.SubprocessError, "preexec_fn"):
                run_doctor_recorded(self, plain, capture_output=True, text=True, timeout=60,
                                    preexec_fn=lambda: os.system("true"))
        # Each frame is told by the identity of its code, not by a name or an equal copy: a namesake of
        # the recorder, compiled from its own source at its own file and line, so that its code equals
        # the recorder's (name, file and line included) but is another object, is refused.
        with self.subTest(launch="a namesake of the recorder"):
            recorder = run_doctor_recorded.__code__
            namespace = dict(globals())
            exec(compile("\n" * (recorder.co_firstlineno - 1) + inspect.getsource(run_doctor_recorded),
                         recorder.co_filename, "exec"), namespace)
            namesake = namespace["run_doctor_recorded"].__code__
            self.assertTrue(namesake == recorder and namesake is not recorder, "not an equal copy")
            self.assertEqual((namesake.co_qualname, namesake.co_filename), (recorder.co_qualname,
                                                                           recorder.co_filename))
            with self.assertRaisesRegex(RuntimeError, "outside run_doctor_recorded"):
                namespace["run_doctor_recorded"](None, plain, capture_output=True, timeout=60)
        # A subinterpreter has audit hooks of its own, so _admit would see neither a process that it
        # starts nor code that it runs: the load of each module that can make one is refused, the list
        # written out, so that a module dropped from INTERPRETER_MODULES fails, and none of them was
        # loaded before the hook was added.
        for name in ("_interpreters", "_testcapi", "_testinternalcapi", "concurrent.interpreters"):
            with self.subTest(subinterpreter=name):
                self.assertNotIn(name, sys.modules)
                with self.assertRaisesRegex(RuntimeError, "makes a subinterpreter"):
                    __import__(name)
                self.assertNotIn(name, sys.modules)
        # A launch raises more than 1 of these events (subprocess.run raises subprocess.Popen and then
        # os.posix_spawn, or _posixsubprocess.fork_exec where posix_spawn cannot serve), so each event is
        # also raised alone here, the list written out, so that an event dropped from LAUNCH_EVENTS
        # fails; os.forkpty is refused because it starts with the member os.fork. An event that starts
        # no process passes.
        for event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
                      "os.forkpty", "_posixsubprocess.fork_exec", "ctypes.dlopen"):
            with self.subTest(event=event):
                with self.assertRaisesRegex(RuntimeError, "outside run_doctor_recorded"):
                    sys.audit(event)
        sys.audit("os.listdir", ".")

    def test_a_case_cannot_switch_the_admission_off(self):
        # _admit reads what it checks from its own defaults: with the names of this module rebound, a
        # launch and code that holds a refusal are still refused.
        module, snippet = globals(), "def outer():\n    def f(x):\n        print({!r} + x)\n    return f\n"
        saved = {name: module[name] for name in ("LAUNCH_EVENTS", "REFUSAL_PREFIXES", "_holds_refusal")}
        try:
            module.update(LAUNCH_EVENTS=(), REFUSAL_PREFIXES=(), _holds_refusal=lambda code, prefixes: False)
            with self.subTest(rebound="launch"):
                with self.assertRaisesRegex(RuntimeError, "outside run_doctor_recorded"):
                    os.system("true")
            with self.subTest(rebound="code"):
                with self.assertRaisesRegex(RuntimeError, "holds a doctor refusal"):
                    exec(compile(snippet.format(REFUSAL_PREFIX), "unrelated.py", "exec"), {})
        finally:
            module.update(saved)
        # A change of the code or the defaults of _admit or of _holds_refusal is refused. Each is given
        # its own value back, so a change that is let through changes nothing.
        for function in (_admit, _holds_refusal):
            for attribute in ("__code__", "__defaults__"):
                with self.subTest(function=function.__name__, attribute=attribute):
                    with self.assertRaisesRegex(RuntimeError, "audit hook of this file"):
                        setattr(function, attribute, getattr(function, attribute))
        # The code of each frame of the recorder's launch, the list written out, is refused as the code
        # of a function built from it with other globals and as the code assigned to a function: either
        # would launch with the frames that _admit admits, past the recorder's registration.
        def target():
            pass

        for function in (run_doctor_recorded, subprocess.run, subprocess.Popen.__init__,
                         subprocess.Popen._execute_child, subprocess.Popen._posix_spawn):
            for run, how in (("function", lambda code: types.FunctionType(code, dict(globals()))),
                             ("__code__", lambda code: setattr(target, "__code__", code))):
                with self.subTest(code=function.__qualname__, run=run):
                    with self.assertRaisesRegex(RuntimeError, "code of the recorder's launch"):
                        how(function.__code__)
        # A run whose output holds a refusal fails at once when its case is not running, before it is
        # registered with a case whose cleanup would never run: a case never run, and a case whose run
        # has ended.
        ended = unittest.FunctionTestCase(lambda: None)
        ended.run(unittest.TestResult())
        for name, case in (("never run", unittest.TestCase()), ("ended", ended)):
            with self.subTest(case=name):
                with self.assertRaisesRegex(AssertionError, "no running case"):
                    run_doctor_recorded(case, self.child(REFUSAL_PREFIX + "the x"), capture_output=True,
                                        text=True, timeout=60)

    def test_code_that_holds_a_refusal_cannot_run_here(self):
        # Code that holds a doctor refusal, in a function nested in another, under an unrelated file
        # name, is refused when it runs by exec, when a function is built from it (types.FunctionType
        # runs a module's code without an exec event) and when it is assigned as the code of a function;
        # the same code with other text passes each, in each form below. Each prefix is also refused when
        # the code holds it only inside a tuple, a frozenset or a slice constant: Python 3.14 keeps the
        # bare string beside a folded tuple or frozenset, so the case replaces that string and checks
        # that only the container holds the prefix. A constant of a type that the compiler does not make,
        # which only code built by hand holds, is refused whatever it holds.
        def target():
            pass

        def replaced(code, text):
            # code with each constant equal to text, in it or in a code object at any depth, made "x".
            return code.replace(co_consts=tuple(
                replaced(const, text) if isinstance(const, types.CodeType)
                else "x" if const == text else const for const in code.co_consts))

        def bare(code, text):
            # Whether text is a constant of code or of a code object in it, outside any container.
            return any(const == text or isinstance(const, types.CodeType) and bare(const, text)
                       for const in code.co_consts)

        nested = "def outer():\n    def f(x):\n        {}\n    return f\n"
        forms = (("print", "print({!r} + x)"), ("tuple", "return x in ({!r}, 'y')"),
                 ("frozenset", "return x in {{{!r}, 'y'}}"), ("slice", "return x[{!r}:]"))
        runs = (("exec", lambda code: exec(code, {})),
                ("function", lambda code: types.FunctionType(code, {})),
                ("__code__", lambda code: setattr(target, "__code__", code)))
        for prefix in self.PREFIXES:
            text = prefix + "the x"
            for form, body in forms:
                code = compile(nested.format(body.format(text)), "unrelated.py", "exec")
                if form != "print":
                    code = replaced(code, text)
                    self.assertFalse(bare(code, text), "the {} form still holds the bare text".format(form))
                for run, how in runs:
                    with self.subTest(prefix=prefix, form=form, run=run):
                        with self.assertRaisesRegex(RuntimeError, "holds a doctor refusal"):
                            how(code)
        for form, body in forms:
            for run, how in runs:
                how(compile(nested.format(body.format("the doctor ran: ")), "unrelated.py", "exec"))
        plain = compile("x = 1", "unrelated.py", "exec")
        for run, how in runs:
            with self.subTest(form="a list constant", run=run):
                with self.assertRaisesRegex(RuntimeError, "holds a doctor refusal"):
                    how(plain.replace(co_consts=plain.co_consts + (["the doctor ran: "],)))

    def test_the_recorder_registers_every_refusal(self):
        # The recorder registers each of the refusal prefixes inside a child's JSON line, and the output
        # of a run that times out and of a run that fails check=True (a doctor that refuses exits 2); it
        # fails a run with no case whose output holds a refusal; a run without a refusal registers
        # nothing.
        text = REFUSAL_PREFIX + "the x"

        class Probe(unittest.TestCase):
            printed = text

            def test_wrapped(inner):
                r = run_doctor_recorded(inner, self.child(inner.printed), capture_output=True, text=True,
                                        timeout=60)
                inner.assertEqual(r.returncode, 0, r.stderr)

            def test_timed_out(inner):
                with inner.assertRaises(subprocess.TimeoutExpired):
                    run_doctor_recorded(inner, self.child(text, "60"), capture_output=True, text=True,
                                        timeout=5)

            def test_failed_check(inner):
                with inner.assertRaises(subprocess.CalledProcessError):
                    run_doctor_recorded(inner, self.child(text, "0", "2"), capture_output=True, text=True,
                                        timeout=60, check=True)

            def test_no_case(inner):
                with inner.assertRaises(AssertionError):
                    run_doctor_recorded(None, self.child(text), stdout=subprocess.PIPE, text=True, timeout=60)

            def test_plain(inner):
                r = run_doctor_recorded(inner, self.child("the doctor ran"), capture_output=True, text=True,
                                        timeout=60)
                inner.assertEqual(r.returncode, 0, r.stderr)

        cleanup = "neither assert_refusal nor assert_barrier_refusal checked as a whole line"
        cases = [("test_wrapped", prefix, (cleanup,)) for prefix in self.PREFIXES]
        cases += [("test_timed_out", None, (cleanup,)), ("test_failed_check", None, (cleanup,)),
                  ("test_no_case", None, ()), ("test_plain", None, ())]
        for name, prefix, failures in cases:
            with self.subTest(case=name, prefix=prefix):
                Probe.printed = text if prefix is None else prefix + "x"
                result = unittest.TestResult()
                Probe(name).run(result)
                self.assertEqual(result.errors, [])
                self.assertEqual(len(result.failures), len(failures), result.failures)
                for (_test, message), wanted in zip(result.failures, failures):
                    self.assertIn(wanted, message)
        # A run whose stdout is not captured (capture_output=True or stdout=subprocess.PIPE) is refused
        # with ValueError before it starts: the child would create marker.
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryFile() as sink:
            marker = Path(folder) / "ran"
            touch = [sys.executable, "-I", "-c", "import sys; open(sys.argv[1], 'w').close()", str(marker)]
            for name, kwargs in (("nothing", {}), ("capture_output=False", {"capture_output": False}),
                                 ("stdout=DEVNULL", {"stdout": subprocess.DEVNULL}),
                                 ("stdout=file", {"stdout": sink}), ("stderr=PIPE", {"stderr": subprocess.PIPE})):
                with self.subTest(uncaptured=name):
                    with self.assertRaises(ValueError):
                        run_doctor_recorded(self, touch, timeout=60, **kwargs)
                    self.assertFalse(marker.exists(), "an uncaptured run started")

    def test_every_barrier_refusal_of_the_audit_is_registered(self):
        # Every string of the doctor that starts "barrier: " is the barrier's state line or starts with
        # 1 of the barrier refusals that the recorder registers, and each of those starts 1 or more of
        # them, so a barrier refusal added to the doctor is registered or fails here. A barrier refusal
        # that the doctor builds without such a string is not found.
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        texts = [node.value for node in ast.walk(ast.parse(DOCTOR.read_text(encoding="utf-8")))
                 if isinstance(node, ast.Constant) and isinstance(node.value, str)
                 and node.value.startswith("barrier: ")]
        prefixes = (BARRIER_REFUSAL_PREFIX,) + AUDIT_REFUSAL_PREFIXES
        self.assertEqual([text for text in texts
                          if text != "barrier: {} ({})" and not text.startswith(prefixes)], [],
                         "a barrier text of the doctor that the recorder does not register")
        self.assertEqual([prefix for prefix in prefixes
                          if not any(text.startswith(prefix) for text in texts)], [],
                         "a registered barrier refusal that the doctor no longer prints")

    def test_the_cleanup_fails_a_refusal_that_assert_refusal_did_not_check(self):
        # A run through the recorder that prints the whole refusal at scope.lease: a case that checks
        # it with assert_refusal passes, and a case that checks only a part of it, by a literal or by
        # a holder name, fails in the cleanup of the recorder. The same holds for the barrier refusal
        # of the resume audit and assert_barrier_refusal, which fails a line with another ending, given a
        # pattern, a line that the pattern matches only in part, and, in each form, a line that is not the
        # only line of stdout that starts with "barrier: ".
        line = "cannot evaluate: the declared lease.path /x is not a regular file (it is a directory); {}" \
            .format(expected_tail("scope.lease"))
        argv = [sys.executable, "-I", "-c", "import sys; print(sys.argv[1])", line]
        barrier = ("barrier: cannot be recorded before the audit at /b (/b is not a regular file (it is a "
                   "FIFO)); a rewrite could not be confirmed, so the audit is not run")
        barrier_argv = argv[:-1] + [barrier]
        other_end = argv[:-1] + [barrier.replace("so the audit is not run", "so the audit ran")]
        # A refusal that holds a time of the run, checked by a pattern: the pattern must match the whole
        # line.
        stale = "barrier: its ts 'T' is not from this audit run (1 to 2); it was not rewritten by this audit"
        stale_argv = argv[:-1] + [stale]
        stale_whole = re.compile(r"barrier: its ts '[^']*' is not from this audit run \(1 to 2\); it was not "
                                 r"rewritten by this audit")
        stale_start = re.compile(r"barrier: its ts '[^']*'")

        class Probe(unittest.TestCase):
            # What test_beside prints and gives to assert_barrier_refusal.
            printed, given = barrier, {}

            def test_pattern_whole(inner):
                r = run_doctor_recorded(inner, stale_argv, capture_output=True, text=True, timeout=60)
                assert_barrier_refusal(inner, r.stdout, "/b", line=stale_whole)

            def test_pattern_start(inner):
                r = run_doctor_recorded(inner, stale_argv, capture_output=True, text=True, timeout=60)
                assert_barrier_refusal(inner, r.stdout, "/b", line=stale_start)

            def test_beside(inner):
                r = run_doctor_recorded(inner, argv[:-1] + [inner.printed], capture_output=True, text=True,
                                        timeout=60)
                assert_barrier_refusal(inner, r.stdout, "/b", **inner.given)

            def test_barrier_whole(inner):
                r = run_doctor_recorded(inner, barrier_argv, capture_output=True, text=True, timeout=60)
                assert_barrier_refusal(inner, r.stdout, "/b", "FIFO")

            def test_barrier_part(inner):
                r = run_doctor_recorded(inner, barrier_argv, capture_output=True, text=True, timeout=60)
                inner.assertIn("barrier: cannot be recorded before the audit at /b", r.stdout)

            def test_barrier_other_end(inner):
                r = run_doctor_recorded(inner, other_end, capture_output=True, text=True, timeout=60)
                assert_barrier_refusal(inner, r.stdout, "/b", "FIFO")

            def test_whole(inner):
                r = run_doctor_recorded(inner, argv, capture_output=True, text=True, timeout=60)
                assert_refusal(inner, r.stdout, "scope.lease", "declared lease.path", "/x", "directory")

            def test_holder(inner):
                r = run_doctor_recorded(inner, argv, capture_output=True, text=True, timeout=60)
                inner.assertIn(READER_END, r.stdout)

            def test_literal(inner):
                r = run_doctor_recorded(inner, argv, capture_output=True, text=True, timeout=60)
                inner.assertIn("is not a regular file (it is a directory)", r.stdout)

            def test_twice(inner):
                # 2 runs with the same text: checking 1 of them does not stand for the other.
                first = run_doctor_recorded(inner, argv, capture_output=True, text=True, timeout=60)
                run_doctor_recorded(inner, argv, capture_output=True, text=True, timeout=60)
                assert_refusal(inner, first.stdout, "scope.lease", "declared lease.path", "/x", "directory")

        # The failures that each case gives, in order, each by a part of its message.
        cleanup = "neither assert_refusal nor assert_barrier_refusal checked as a whole line"
        for name, failures in (("test_whole", ()), ("test_holder", (cleanup,)), ("test_literal", (cleanup,)),
                               ("test_twice", (cleanup,)), ("test_barrier_whole", ()),
                               ("test_barrier_part", (cleanup,)),
                               ("test_barrier_other_end", ("no single whole barrier refusal", cleanup)),
                               ("test_pattern_whole", ()),
                               ("test_pattern_start", ("no single whole barrier refusal", cleanup))):
            with self.subTest(case=name):
                result = unittest.TestResult()
                Probe(name).run(result)
                self.assertEqual(result.errors, [])
                self.assertEqual(len(result.failures), len(failures), result.failures)
                for (_test, text), wanted in zip(result.failures, failures):
                    self.assertIn(wanted, text)
        # The refusal must be the only line of stdout that starts with "barrier: ", for each form in which
        # a case gives it (by its type, as the whole line, as a pattern), with another such line before it
        # and after it; alone, each form passes.
        other = "barrier: clear (/b)"
        for form, refusal, given in (("type", barrier, {"made": "FIFO"}), ("line", stale, {"line": stale}),
                                     ("pattern", stale, {"line": stale_whole})):
            for order, printed, failures in (
                    ("alone", refusal, ()),
                    ("other before", other + "\n" + refusal, ("no single whole barrier refusal", cleanup)),
                    ("other after", refusal + "\n" + other, ("no single whole barrier refusal", cleanup))):
                with self.subTest(form=form, order=order):
                    Probe.printed, Probe.given = printed, given
                    result = unittest.TestResult()
                    Probe("test_beside").run(result)
                    self.assertEqual(result.errors, [])
                    self.assertEqual(len(result.failures), len(failures), result.failures)
                    for (_test, text), wanted in zip(result.failures, failures):
                        self.assertIn(wanted, text)


# The words with which the doctor says how the hook opens a pre-check path and what was not run, as 1
# regular expression in any letter case. `rg -n -i` with this expression over tools/orch_doctor.py lists
# the same words line by line; open_account_outside also finds a phrase of them that a line break, a
# concatenation or an escape splits. OPEN_ACCOUNT_HOLDERS are the doctor's tables that word that
# account: SITE_OPEN with the 2 texts that it gives several sites, BLOCKING_OPEN, REFUSAL_END and
# SITE_END. A mention of the name of one of them is a pointer to it, not a restatement.
OPEN_ACCOUNT_WORDS = re.compile(r"(?i)blocking|O_NONBLOCK|would not block|unattended|not regular|"
                                r"reader that opens|no enumerator ran|does not open")
OPEN_ACCOUNT_HOLDERS = ("SITE_OPEN", "_RECORD_SURFACE_OPEN", "_ANCHOR_OPEN", "BLOCKING_OPEN",
                        "REFUSAL_END", "SITE_END")


def open_account_outside(source):
    """(line, word) for every match of OPEN_ACCOUNT_WORDS in the prose of source outside the tables of
    OPEN_ACCOUNT_HOLDERS, after the names of those tables are taken out of it and each run of white
    space, line breaks included, is made 1 space. The prose is each string expression as Python
    evaluates it (literal_text: escapes resolved, adjacent literals joined, a + of strings joined, an
    f-string with "{}" for each field), each expression inside an f-string field or beside a string in
    a + read the same way, and each block of comments on consecutive lines, joined; line is where that
    string or block starts. The tables are the values of the first top-level assignment of each holder
    name, so a later binding of that name is read, and a comment is never inside a table. Code tokens,
    such as os.O_NONBLOCK in the doctor's own open, are not read. A phrase that the doctor assembles at
    run time from separate strings or names (by format, join or a variable) is not found."""
    tree = ast.parse(source)
    inside, assigned = set(), set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in OPEN_ACCOUNT_HOLDERS and node.targets[0].id not in assigned:
            assigned.add(node.targets[0].id)
            inside.update(id(part) for part in ast.walk(node.value))
    units = []

    def visit(node):
        text = literal_text(node)
        if text is None:
            for child in ast.iter_child_nodes(node):
                visit(child)
            return
        if id(node) not in inside:
            units.append((node.lineno, text))
        within(node)

    def within(part):
        # The expressions inside the string expression part that literal_text does not read as text.
        if isinstance(part, ast.BinOp) and literal_text(part) is not None:
            within(part.left)
            within(part.right)
        elif isinstance(part, ast.JoinedStr):
            for value in part.values:
                if isinstance(value, ast.FormattedValue):
                    visit(value.value)
                    if value.format_spec is not None:
                        visit(value.format_spec)
        elif literal_text(part) is None:
            visit(part)

    visit(tree)
    block = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        if block and tok.start[0] != block[-1][0] + 1:
            units.append((block[0][0], " ".join(text for _line, text in block)))
            block = []
        block.append((tok.start[0], tok.string.lstrip("#")))
    if block:
        units.append((block[0][0], " ".join(text for _line, text in block)))
    names = re.compile(r"\b(?:{})\b".format("|".join(OPEN_ACCOUNT_HOLDERS)))
    found = []
    for line, text in sorted(units):
        flat = " ".join(names.sub(" | ", text).split())
        found.extend((line, match.group(0)) for match in OPEN_ACCOUNT_WORDS.finditer(flat))
    return found


class DoctorOpenAccountHolders(unittest.TestCase):
    """The doctor states how the hook opens a pre-check path only in OPEN_ACCOUNT_HOLDERS, which
    DoctorPrecheckSiteProbe holds to OPEN_ACCOUNTS and the hook source."""

    def test_the_open_account_is_worded_only_in_its_tables(self):
        if not DOCTOR.exists():
            self.fail("doctor not found: {}".format(DOCTOR))
        self.assertEqual(open_account_outside(DOCTOR.read_text(encoding="utf-8")), [],
                         "the doctor words how the hook opens a path outside its tables")
        # The check finds each of the 8 terms of OPEN_ACCOUNT_WORDS alone, in a docstring, a comment or
        # another string outside the tables, so a term dropped from the expression fails here, and each
        # also with the letter case of every letter of the term swapped, so the rule that a word counts
        # in any letter case fails here too.
        for term, outside in (("blocking", 'def f():\n    """Opened by a blocking reader."""\n'),
                              ("O_NONBLOCK", '# read with O_NONBLOCK\nX = 1\n'),
                              ("would not block", 'X = "the hook would not block on it"\n'),
                              ("unattended", 'X = ("a mode file it reads as unattended")\n'),
                              ("not regular", '# a file that is not regular\nX = 1\n'),
                              ("reader that opens", 'X = f"the {name} reader that opens it"\n'),
                              ("no enumerator ran", 'def f():\n    """So no enumerator ran."""\n'),
                              ("does not open", 'X = b"the hook does not open it"\n')):
            for sample in (outside, outside.replace(term, term.swapcase())):
                with self.subTest(term=term, sample=sample):
                    self.assertEqual([word.lower() for _line, word in open_account_outside(sample)],
                                     [term.lower()])
        # It finds a phrase of the account that a line break, a concatenation or an escape splits, and
        # a word in a comment beside, or in the value of, a second binding of a table's name.
        for outside in ('def f():\n    """The hook would not\n    block on it."""\n',
                        '# the hook would not\n# block on it\nX = 1\n',
                        'X = ("the hook would not "\n     "block on it")\n',
                        'X = "the hook would not " + "block on it"\n',
                        'X = f"the hook would not " + "block on it" + f"{z}"\n',
                        'def f():\n    """A file that is not\n    regular."""\n',
                        'X = "a bl\\x6fcking open"\n',
                        'X = "a bl\\u006fcking open"\n',
                        'X = "the reader that\\nopens it"\n',
                        'X = g("so no enumerator ran")\n',
                        'SITE_END = {"a": "b"}\nSITE_END = dict(SITE_END)  # a blocking open\n',
                        'SITE_END = {"a": "b"}\nSITE_END = "a blocking open"\n'):
            with self.subTest(outside=outside):
                self.assertEqual(len(open_account_outside(outside)), 1)
        # It passes the words inside a table and a mention of a table's name. The last 2 show the
        # stated residual: a phrase assembled at run time from separate strings is not found.
        for fine in ('BLOCKING_OPEN = "blocking"\nREFUSAL_END = ("unattended"\n               " reader")\n',
                     'def f():\n    """See SITE_OPEN, else BLOCKING_OPEN."""\n',
                     'X = os.O_NONBLOCK\n',
                     'X = "the hook would not"\nY = X + " " + Z\nZ = "block on it"\n',
                     'X = " ".join(("the hook would not", "block on it"))\n'):
            with self.subTest(fine=fine):
                self.assertEqual(open_account_outside(fine), [])


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


def stage2_comment_mismatches(source, table):
    """What differs between the comment directly above class Stage2Harness in source and table, in the
    form of TEST_TIME_LIMITS, with the comment's lines joined by a space, V the least value of table as
    "{:g}" gives it, and a phrase found in any case, with any white space between its words and no
    letter, digit, underscore or dot before it: [] when the comment holds the phrase "least of them is"
    exactly once, as "The least of them is V s, at L.", where L, up to the first full stop that a space
    or the end of the comment follows, names the sites of exactly the entries that hold V, each once,
    in any order, joined by ", and ", ", " or " and ", and when each phrase "least of them is" and
    "least test limit is" in it is followed by " V s" and then by no letter, digit or underscore, alone
    or after a dot."""
    out = []
    lines = source.splitlines()
    end = next((n for n, line in enumerate(lines) if line.startswith("class Stage2Harness(")), 0)
    start = end
    while start > 0 and lines[start - 1].startswith("#"):
        start -= 1
    comment = " ".join(line[1:].strip() for line in lines[start:end])
    least = min(table.values()) if table else None
    value = "{:g}".format(least)
    names = sorted("{}.{}".format(*key) if key[0] else key[1] for key, limit in table.items()
                   if limit == least)
    stated = list(re.finditer(r"(?i)(?<![\w.])least\s+(?:(of\s+them)|test\s+limit)\s+is", comment))
    for found in stated:
        if not re.match(r" " + re.escape(value) + r" s(?![\w]|\.\w)", comment[found.end():]):
            out.append("the comment above Stage2Harness states another least value: {!r}".format(
                comment[found.start():found.end() + 12]))
    held = sum(1 for found in stated if found.group(1))
    if held != 1:
        out.append("the comment above Stage2Harness states 'least of them is' {} times, not once".format(held))
    sites = re.search(r"The least of them is " + re.escape(value) + r" s, at (.*?)\.(?: |$)", comment)
    if sites is None:
        out.append("the comment above Stage2Harness does not state 'The least of them is {} s, at' and the "
                   "sites that hold it".format(value))
    elif sorted(re.split(r", and |, | and ", sites.group(1))) != names:
        out.append("the comment above Stage2Harness names {!r} as the sites of the least value, not {!r}"
                   .format(sites.group(1), names))
    return out


class Stage2TimeLimitProbe(unittest.TestCase):
    """Class probe: each entry of TEST_TIME_LIMITS is a site of a Stage2Harness test, and the comment
    above Stage2Harness states the least value of the table once, with the sites of exactly the entries
    that hold it, and states no other least value, in the forms that stage2_comment_mismatches reads.
    _time_limit_applied checks each limit against the table when it is applied, and tearDownModule
    checks, once the whole file has run, that each entry is the least value admitted at its site."""

    def test_each_entry_is_a_site_of_a_stage2harness_test(self):
        sites = {key for _code, key in TIME_LIMIT_SITES.values()}
        self.assertEqual([key for key in TEST_TIME_LIMITS if key not in sites or key[0] not in TIME_LIMIT_SCOPE],
                         [], "an entry that names no function or method of this file, or no site of a "
                         "Stage2Harness test")

    def test_the_comment_states_the_least_limit(self):
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertEqual(stage2_comment_mismatches(source, TEST_TIME_LIMITS), [])

    def test_it_refuses_a_comment_or_a_table_that_disagrees(self):
        # A comment that states another least value, or a second one, or states it again at another
        # site or in a line that it comments out, that names, in place of the site that holds the least
        # value, another site, such as one whose name holds the name of that site, or that names a
        # second site or the same site twice as holding it, a table whose least value changes, a table
        # whose least value moves to another site, and a table whose least value is held by a site that
        # the comment does not name each disagree. Controls: a comment that also names the site in
        # another sentence, 2 sites that hold the least value named in either order, and a least value
        # that is an int.
        source = Path(__file__).read_text(encoding="utf-8")
        stated = "The least of them is 4.5 s"
        named = "# DoctorScopeMargin._assert_refused_near. That"
        bound = "the least test limit is\n# 4.5 s"
        other = "# DoctorCheckpointWrites.PROMPT, 15, is read by no check."
        near, doctor = ("DoctorScopeMargin", "_assert_refused_near"), ("Doctor", "_doctor_bounded")
        end = source.index("\nclass Stage2Harness(")
        begin = source.rindex("\n\n", 0, end)
        for text in (stated, named, bound, other):
            self.assertTrue(begin < source.find(text) < end,
                            "precondition: {!r} first in the comment above Stage2Harness".format(text))
        self.assertEqual(TEST_TIME_LIMITS.get(near), 4.5, "precondition: the entry that holds the least value")

        def sited(text):
            return source.replace(named, text, 1)

        also = source.replace(other, other + " DoctorScopeMargin._assert_refused_near sets NEAR.", 1)
        whole = source.replace(stated, "The least of them is 4 s", 1).replace(bound, "the least test limit is\n# 4 s", 1)
        admitted = {
            "the comment unchanged": (source, TEST_TIME_LIMITS),
            "a comment that also names the site in another sentence": (also, TEST_TIME_LIMITS),
            "2 sites named": (sited("# Doctor._doctor_bounded and DoctorScopeMargin._assert_refused_near. That"),
                              {**TEST_TIME_LIMITS, doctor: 4.5}),
            "2 sites named in the other order": (
                sited("# DoctorScopeMargin._assert_refused_near and Doctor._doctor_bounded. That"),
                {**TEST_TIME_LIMITS, doctor: 4.5}),
            "a least value that is an int": (whole, {**TEST_TIME_LIMITS, near: 4}),
        }
        planted = {
            "a comment that states another value": (source.replace(stated, "The least of them is 5 s", 1),
                                                    TEST_TIME_LIMITS),
            "a comment that states a second least value": (
                source.replace(stated, "The least of them is 3 s. " + stated, 1), TEST_TIME_LIMITS),
            "a comment whose bound states another least value": (
                source.replace(bound, "the least test limit is\n# 3 s", 1), TEST_TIME_LIMITS),
            "a comment that states the least value again, at another site": (
                source.replace(other, other + " " + stated + ", at Doctor._doctor_bounded.", 1), TEST_TIME_LIMITS),
            "a comment that states another value and the least value in a line that it comments out": (
                source.replace(stated, "The least of them is 9 s", 1).replace(other, other + "\n# # " + stated, 1),
                TEST_TIME_LIMITS),
            "a comment that names a site whose name starts with that of the site": (
                sited("# DoctorScopeMargin._assert_refused_nearby. That"), TEST_TIME_LIMITS),
            "a comment that names a site whose name ends with that of the site": (
                sited("# XDoctorScopeMargin._assert_refused_near. That"), TEST_TIME_LIMITS),
            "a comment that names another site, and the site in another sentence": (
                also.replace(named, "# Doctor._doctor_bounded. That", 1), TEST_TIME_LIMITS),
            "a comment that names a second site": (
                sited("# DoctorScopeMargin._assert_refused_near and Doctor._doctor_bounded. That"), TEST_TIME_LIMITS),
            "a comment that names the site twice": (
                sited("# DoctorScopeMargin._assert_refused_near and DoctorScopeMargin._assert_refused_near. That"),
                TEST_TIME_LIMITS),
            "a new least value": (source, {**TEST_TIME_LIMITS, near: 4.0}),
            "the least value at another site": (source, {**TEST_TIME_LIMITS, near: 30, doctor: 4.5}),
            "the least value also at another site": (source, {**TEST_TIME_LIMITS, doctor: 4.5}),
        }
        for kind, (text, table) in admitted.items():
            with self.subTest(kind=kind):
                self.assertEqual(stage2_comment_mismatches(text, table), [])
        for kind, (text, table) in planted.items():
            with self.subTest(kind=kind):
                self.assertNotEqual((text, table), (source, TEST_TIME_LIMITS), "precondition: the change")
                self.assertNotEqual(stage2_comment_mismatches(text, table), [])

    def test_a_full_run_holds_each_entry_to_its_site(self):
        # time_limit_table_mismatches, which tearDownModule applies to TIME_LIMIT_CHECKS once every
        # test of this module has run: an entry whose site admitted no limit, or whose value is not the
        # least value admitted there, is reported; a refused limit counts for none.
        table = {("A", "f"): 5, ("A", "g"): 5, ("A", "h"): 5}
        checks = [("launch", ("A", "f"), 6, None), ("join", ("A", "f"), 5, None),
                  ("launch", ("A", "g"), 1, "refused"), ("launch", ("A", "h"), 7, None)]
        self.assertEqual(time_limit_table_mismatches(checks, table),
                         ["('A', 'g'): its site admitted no limit in this run",
                          "('A', 'h'): TEST_TIME_LIMITS gives 5, the least limit admitted at its site is 7"])

    def test_only_a_full_run_holds_the_entries_to_their_sites(self):
        # time_limit_full_run, which tells tearDownModule whether to apply time_limit_table_mismatches.
        # A run that a -k option narrows gives unittest.defaultTestLoader its name patterns. With such
        # a pattern on it, the 1 test that the pattern selects must not be a full run, and every test of
        # the module must be one (control); with no pattern, the same 2 answers (controls).
        module = sys.modules[__name__]

        def found(loader):
            pending, ids = [loader.loadTestsFromModule(module)], set()
            while pending:
                for test in pending.pop():
                    if isinstance(test, unittest.TestSuite):
                        pending.append(test)
                    else:
                        ids.add(test.id())
            return ids

        narrowed = unittest.TestLoader()
        narrowed.testNamePatterns = ["*test_each_site_takes_its_floor*"]
        selected, every = found(narrowed), found(unittest.TestLoader())
        self.assertEqual(len(selected), 1, "precondition: the pattern selects 1 test")
        self.assertTrue(selected < every, "precondition: the module holds other tests")
        patterns = unittest.defaultTestLoader.testNamePatterns
        for given in (narrowed.testNamePatterns, None):
            with self.subTest(patterns=given):
                unittest.defaultTestLoader.testNamePatterns = given
                try:
                    answers = time_limit_full_run(module, selected), time_limit_full_run(module, every)
                finally:
                    unittest.defaultTestLoader.testNamePatterns = patterns
                self.assertEqual(answers, (False, True), "(the selected test, every test) as a full run")


# The program that a planted case of TimeLimitSinkProbe runs through REAPER_PROG: it creates the file
# that its operand names, so a launch that a check refuses leaves no such file.
MARK_PROG = "import sys; open(sys.argv[1], 'w').close()"


class TimeLimitSinkProbe(unittest.TestCase):
    """Class probe: each sink gives _time_limit_applied the limit that it is about to apply, whatever way
    a test binds it, and a refusal fails the test that ran it, also when it is raised in a thread or
    caught, and a limit applied where no other frame runs the code of this file has no site and takes
    TIME_LIMIT_FLOOR only. Each form is a planted case, a class defined in the test, run in this process
    through unittest with its own setUp and tearDown."""

    def test_each_form_is_checked_at_its_sink(self):
        # Each form binds a limit of 1 s unless its name gives another value. A refused form must fail
        # its case with the refusal that _time_limit_applied gives for that sink, value and site, and
        # a launch through run_reaped must not start: REAPER_PROG would run MARK_PROG, which creates the
        # form's marker file. A control must pass its case, its limit must be in TIME_LIMIT_CHECKS as
        # admitted at its site, and a control through run_reaped must start, so a sink that is not
        # checked fails a control too. Each of the first 17 forms binds the limit of a launch through
        # run_reaped, DoctorCheckpointWrites._doctor or run_doctor_recorded other than by a call that
        # names the method and the value plainly; the 18th is such a plain call, through the class. The
        # forms after them apply 60 s and 30 s through run_reaped, NaN through run_reaped, 1 s to
        # assertLess, assertLessEqual and Thread.join outside every Stage2Harness test, where only
        # TIME_LIMIT_FLOOR applies, 4.5 s and 4.4 s there, and a refusal that the case catches or
        # that is raised in a thread.
        import functools
        import gc
        import operator
        import string
        folder = Path(tempfile.mkdtemp(prefix="orch-time-limits-"))
        self.addCleanup(shutil.rmtree, folder, True)
        here = ("TimeLimitSinkProbe", "test_each_form_is_checked_at_its_sink")
        reaped = "launch limit 1 at T15EnumeratorTimeout.run_reaped: "
        floor = "at TimeLimitSinkProbe.test_each_form_is_checked_at_its_sink: below TIME_LIMIT_FLOOR"
        doctor = "launch limit 1 at DoctorCheckpointWrites._doctor: "
        forms = []

        def form(name, expected, launches=None):
            # expected: a part of the refusal that the case must fail with, or the (sink, site, value)
            # that a control must apply and have admitted; launches: whether REAPER_PROG must start.
            def add(cls):
                forms.append((name, cls, expected, launches))
                return cls
            return add

        class Reaped(T15EnumeratorTimeout):
            marker = None

            def args(test):
                return ([sys.executable, "-I", "-c", MARK_PROG, str(test.marker)],
                        test._tmp / "planted-report.json")

        @form("a dict display that a dict display of a ** argument unpacks", reaped, False)
        class Unpacked(Reaped):
            def planted(test):
                test.run_reaped(*test.args(), **{**{"wall_clock_bound": 1}})

        @form("a dict passed by position and forwarded with ** to run_doctor_recorded", "launch limit 1 " + floor,
              False)
        class Forwarded(Reaped):
            def forward(test, argv, options):
                return run_doctor_recorded(test, argv, capture_output=True, **options)

            def planted(test):
                test.forward(test.args()[0], {"timeout": 1})

        # _doctor takes no timeout argument and launches with self.TIMEOUT, so the 2 forms of _doctor
        # bind that attribute.
        @form("a value that an except clause binds in a class body, as TIMEOUT, read by _doctor", doctor)
        class Excepted(DoctorCheckpointWrites):
            try:
                raise LookupError(1)
            except LookupError as caught:
                TIMEOUT = caught.args[0]

            def planted(test):
                test._doctor("idle")

        @form("super()", reaped, False)
        class Super(Reaped):
            def planted(test):
                super().run_reaped(*test.args(), wall_clock_bound=1)

        @form("an alias of the bound method", reaped, False)
        class Alias(Reaped):
            def planted(test):
                run = test.run_reaped
                run(*test.args(), wall_clock_bound=1)

        @form("getattr with the name of the method", reaped, False)
        class Named(Reaped):
            def planted(test):
                getattr(test, "run_reaped")(*test.args(), wall_clock_bound=1)

        @form("functools.partial", reaped, False)
        class Partial(Reaped):
            def planted(test):
                functools.partial(test.run_reaped, wall_clock_bound=1)(*test.args())

        @form("another name for the instance", reaped, False)
        class Other(Reaped):
            def planted(test):
                other = test
                other.run_reaped(*test.args(), wall_clock_bound=1)

        @form("type(self)", reaped, False)
        class Typed(Reaped):
            def planted(test):
                type(test).run_reaped(test, *test.args(), wall_clock_bound=1)

        @form("an override whose default is 1, passed on through super()", reaped, False)
        class Override(Reaped):
            def run_reaped(test, cmd, report, hook_bound=None, wall_clock_bound=1):
                return super().run_reaped(cmd, report, hook_bound, wall_clock_bound)

            def planted(test):
                test.run_reaped(*test.args())

        @form("a TIMEOUT of the instance, read by _doctor through super()", doctor)
        class SuperDoctor(DoctorCheckpointWrites):
            def planted(test):
                test.TIMEOUT = 1
                super()._doctor("idle")

        @form("a class pattern of a match statement", reaped, False)
        class Matched(Reaped):
            def planted(test):
                match test:
                    case T15EnumeratorTimeout(run_reaped=run):
                        run(*test.args(), wall_clock_bound=1)

        @form("inspect.getmembers with a prefix of the name", reaped, False)
        class Members(Reaped):
            def planted(test):
                for name, member in inspect.getmembers(test, inspect.ismethod):
                    if name.startswith("run_re"):
                        member(*test.args(), wall_clock_bound=1)

        @form("string.Formatter.get_field with a built name", reaped, False)
        class Field(Reaped):
            def planted(test):
                string.Formatter().get_field("0.run_" + "reaped", (test,), {})[0](*test.args(), wall_clock_bound=1)

        @form("a method that returns the bound method", reaped, False)
        class Returned(Reaped):
            def runner(test):
                return test.run_reaped

            def planted(test):
                test.runner()(*test.args(), wall_clock_bound=1)

        @form("operator.methodcaller with a built name", reaped, False)
        class Caller(Reaped):
            def planted(test):
                operator.methodcaller("run_" + "reaped", *test.args(), wall_clock_bound=1)(test)

        @form("gc.get_objects matched by repr", reaped, False)
        class Collected(Reaped):
            def planted(test):
                found = next(o for o in gc.get_objects() if isinstance(o, types.FunctionType)
                             and repr(o).startswith("<function T15EnumeratorTimeout.run_reaped "))
                found(test, *test.args(), wall_clock_bound=1)

        @form("the method called through its class, by keyword", reaped, False)
        class Plain(Reaped):
            def planted(test):
                T15EnumeratorTimeout.run_reaped(test, *test.args(), wall_clock_bound=1)

        @form("60 s through run_reaped (control)",
              ("launch", ("T15EnumeratorTimeout", "run_reaped"), 60), True)
        class Admitted(Reaped):
            def planted(test):
                r, rep = test.run_reaped(*test.args(), wall_clock_bound=60)
                test.assert_reaped(r, rep)

        @form("30 s through run_reaped, above the floor and below the value of its site",
              "launch limit 30 at T15EnumeratorTimeout.run_reaped: below 60 s", False)
        class Short(Reaped):
            def planted(test):
                test.run_reaped(*test.args(), wall_clock_bound=30)

        @form("NaN through run_reaped", "launch limit nan at T15EnumeratorTimeout.run_reaped: ", False)
        class NotANumber(Reaped):
            def planted(test):
                test.run_reaped(*test.args(), wall_clock_bound=float("nan"))

        @form("assertLess called through unittest.TestCase", "assertLess limit 1 " + floor)
        class Bound(unittest.TestCase):
            def planted(test):
                unittest.TestCase.assertLess(test, 0, 1)

        @form("an assertLessEqual bound passed by keyword", "assertLessEqual limit 1 " + floor)
        class BoundByKeyword(unittest.TestCase):
            def planted(test):
                test.assertLessEqual(0, b=1)

        @form("a positional timeout of Thread.join", "join limit 1 " + floor)
        class Joined(unittest.TestCase):
            def planted(test):
                worker = threading.Thread(target=lambda: None)
                worker.start()
                worker.join(1)

        @form("4.5 s, the floor, as an assertLess bound outside a Stage2Harness test (control)",
              ("assertLess", here, 4.5))
        class AtTheFloor(unittest.TestCase):
            def planted(test):
                test.assertLess(0, 4.5)

        @form("4.4 s, below the floor, as an assertLess bound outside a Stage2Harness test",
              "assertLess limit 4.4 " + floor)
        class BelowTheFloor(unittest.TestCase):
            def planted(test):
                test.assertLess(0, 4.4)

        @form("4.5 s, the floor, as the timeout of Thread.join outside a Stage2Harness test (control)",
              ("join", here, 4.5))
        class JoinedAtTheFloor(unittest.TestCase):
            def planted(test):
                worker = threading.Thread(target=lambda: None)
                worker.start()
                worker.join(4.5)

        @form("a refusal that the test catches", reaped, False)
        class Caught(Reaped):
            def planted(test):
                try:
                    test.run_reaped(*test.args(), wall_clock_bound=1)
                except AssertionError:
                    pass

        @form("a refusal in a thread whose target binds 1 s, which the test joins", reaped, False)
        class Threaded(Reaped):
            def planted(test):
                hook, threading.excepthook = threading.excepthook, lambda args: None
                try:
                    worker = threading.Thread(target=test.run_reaped, args=test.args(),
                                              kwargs={"wall_clock_bound": 1})
                    worker.start()
                    worker.join(60)
                finally:
                    threading.excepthook = hook

        self.assertEqual(len(forms), 29, "precondition: every form above is listed")
        for number, (name, cls, expected, launches) in enumerate(forms):
            with self.subTest(form=name):
                cls.marker = folder / "launched-{}".format(number)
                start = len(TIME_LIMIT_CHECKS)
                result = unittest.TestResult()
                cls("planted").run(result)
                checks = TIME_LIMIT_CHECKS[start:]
                texts = "\n".join(text for _test, text in result.errors + result.failures)
                if isinstance(expected, str):
                    self.assertFalse(result.wasSuccessful(), "the form was not refused")
                    self.assertIn(expected, texts)
                else:
                    self.assertTrue(result.wasSuccessful(), texts)
                    self.assertIn(expected + (None,), checks, "the control was not checked and admitted")
                if launches is not None:
                    self.assertEqual(cls.marker.exists(), launches, "REAPER_PROG started" if not launches
                                     else "REAPER_PROG did not start")

    def test_each_site_takes_its_floor(self):
        # time_limit_refusal for each kind of site: a listed site of a Stage2Harness test at and below
        # its value, an unlisted one, a site outside every Stage2Harness test and no site at and below
        # TIME_LIMIT_FLOOR, NaN, and a value that is not a number.
        cases = [
            (("T15EnumeratorTimeout", "run_reaped"), 60, None),
            (("T15EnumeratorTimeout", "run_reaped"), 59.5, "below 60 s, the value that TEST_TIME_LIMITS gives"),
            (("DoctorScopeMargin", "_assert_refused_near"), 4.5, None),
            (("Stage2Harness", "planted"), 120, "a site of a Stage2Harness test that TEST_TIME_LIMITS does not"),
            (("", "planted"), 120, "a site of a Stage2Harness test that TEST_TIME_LIMITS does not"),
            (("DoctorRefusalCoverage", "planted"), 4.5, None),
            (("DoctorRefusalCoverage", "planted"), 4.4, "below TIME_LIMIT_FLOOR, 4.5 s"),
            (None, 4.5, None),
            (None, 4.4, "below TIME_LIMIT_FLOOR, 4.5 s"),
            (None, float("nan"), "below TIME_LIMIT_FLOOR, 4.5 s"),
            (("T15EnumeratorTimeout", "run_reaped"), "60", "not an int or a float"),
        ]
        for site, value, wanted in cases:
            with self.subTest(site=site, value=value):
                refusal = time_limit_refusal(site, value)
                if wanted is None:
                    self.assertIsNone(refusal)
                else:
                    self.assertIn(wanted, refusal or "")

    def test_a_limit_with_no_other_frame_of_the_file_takes_the_floor_only(self):
        # A sink that a cleanup calls directly applies its limit with no frame of this file on the
        # stack but the wrappers of the sink and of unittest.TestCase.run, as a test of another module
        # does; the case runs in a thread of its own, so no frame of this test is on that stack either.
        # Such a limit has no site and only TIME_LIMIT_FLOOR applies: 60 s at Thread.join and at
        # assertLess must pass the case and be recorded as admitted at no site, and 4.4 s at
        # Thread.join, a refusal, must fail it with the refusal at that floor.
        class Cleanup(unittest.TestCase):
            sink, value = None, None

            def planted(test):
                if test.sink == "join":
                    worker = threading.Thread(target=lambda: None)
                    worker.start()
                    test.addCleanup(worker.join, test.value)
                else:
                    test.addCleanup(test.assertLess, 0, test.value)

        floor = "below TIME_LIMIT_FLOOR, {:g} s".format(TIME_LIMIT_FLOOR)
        for sink, value, refusal in (("join", 60, None), ("assertLess", 60, None), ("join", 4.4, floor)):
            with self.subTest(sink=sink, value=value):
                Cleanup.sink, Cleanup.value = sink, value
                start, result = len(TIME_LIMIT_CHECKS), unittest.TestResult()
                runner = threading.Thread(target=Cleanup("planted").run, args=(result,))
                runner.start()
                runner.join(60)
                self.assertFalse(runner.is_alive(), "the case did not end within 60 s")
                texts = "\n".join(text for _test, text in result.errors + result.failures)
                if refusal is None:
                    self.assertTrue(result.wasSuccessful(), texts)
                    self.assertIn((sink, None, value, None), TIME_LIMIT_CHECKS[start:],
                                  "the limit was not admitted at no site")
                else:
                    self.assertFalse(result.wasSuccessful(), "the limit was not refused")
                    self.assertIn("{} limit {!r} at ".format(sink, value), texts)
                    self.assertIn(refusal, texts)

    def test_each_function_of_the_file_is_a_site(self):
        # A method is the site of the class that defines it, also where another class takes it; code
        # nested in a function has the site of that function; the sinks and the wrappers that the file
        # installs in unittest and threading have no site; and the classes of the sites of
        # Stage2Harness tests are "" and the classes related to Stage2Harness only.
        def site(function):
            found = TIME_LIMIT_SITES.get(id(function.__code__))
            return found[1] if found is not None and found[0] is function.__code__ else None

        self.assertEqual(site(DoctorScopeMargin._doctor_bounded), ("Doctor", "_doctor_bounded"))
        self.assertEqual(site(T15EnumeratorTimeout.run_reaped), ("T15EnumeratorTimeout", "run_reaped"))
        self.assertEqual(site(_git), ("", "_git"))
        nested = [c for c in TimeLimitSinkProbe.test_each_form_is_checked_at_its_sink.__code__.co_consts
                  if isinstance(c, types.CodeType)]
        self.assertTrue(nested, "precondition: code nested in the method")
        self.assertEqual({TIME_LIMIT_SITES[id(code)][1] for code in nested},
                         {("TimeLimitSinkProbe", "test_each_form_is_checked_at_its_sink")})
        for sink in (run_doctor_recorded, _time_limit_applied, unittest.TestCase.assertLess,
                     unittest.TestCase.assertLessEqual, threading.Thread.join, unittest.TestCase.run):
            with self.subTest(sink=sink.__qualname__):
                self.assertIsNone(site(sink))
        for name in ("", "Stage2Harness", "T15EnumeratorTimeout", "Doctor", "DoctorScopeMargin"):
            self.assertIn(name, TIME_LIMIT_SCOPE)
        for name in ("DoctorRefusalCoverage", "TimeLimitSinkProbe", "Stage2TimeLimitProbe"):
            self.assertNotIn(name, TIME_LIMIT_SCOPE)


class TimeLimitTeardownProbe(unittest.TestCase):
    """Class probe: tearDownModule fails a full run for each entry of TEST_TIME_LIMITS that
    time_limit_table_mismatches reports, and a run that is not full for none, and in a full run each
    entry is the least limit admitted at its site. Its test is the last test of the file that a
    unittest.TestLoader finds, so in a full run every other test of the file has run before it."""

    def test_teardown_holds_the_entries_to_their_sites_only_in_a_full_run(self):
        # tearDownModule, called with TESTS_RUN, TIME_LIMIT_CHECKS and TIME_LIMIT_REFUSALS replaced for
        # the call and restored after it, with TIME_LIMIT_LOCK held from before the replacement until
        # after the restore, so a limit that a thread applies meanwhile waits for the lock and is
        # recorded in the lists that are restored, and TEST_TIME_LIMITS as it is: in a full run, with
        # every test of the file in TESTS_RUN, it must fail with the mismatch of an entry whose site
        # admitted a greater least limit and of an entry whose site admitted none; in a run that is
        # not full, with 1 test of the file missing from TESTS_RUN or with this test only, it must
        # fail for neither. Controls: limits that agree with the table must fail neither run. Then,
        # once every test of the file has run in this process, as in a full run, where this test runs
        # last, each entry must be the least limit admitted at its site, which tearDownModule checks
        # only after this test.
        module = sys.modules[__name__]

        def ids(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from ids(test)
                else:
                    yield test.id()

        every = list(ids(unittest.TestLoader().loadTestsFromModule(module)))
        self.assertEqual(every[-1], self.id(), "precondition: this test is the last test of the file")
        site = ("Doctor", "_audit_bounded")
        value = TEST_TIME_LIMITS[site]
        agree = [("launch", key, limit, None) for key, limit in TEST_TIME_LIMITS.items()]
        missing = [check for check in agree if check[1] != site]
        greater = missing + [("join", site, value + 30, None)]
        stale = "{!r}: TEST_TIME_LIMITS gives {:g}, the least limit admitted at its site is {:g}".format(
            site, value, value + 30)
        unreached = "{!r}: its site admitted no limit in this run".format(site)
        full, short, alone = set(every), set(every[1:]), {self.id()}

        def teardown(run, checks):
            names = ("TESTS_RUN", "TIME_LIMIT_CHECKS", "TIME_LIMIT_REFUSALS")
            with TIME_LIMIT_LOCK:
                saved = {name: globals()[name] for name in names}
                globals().update(TESTS_RUN=set(run), TIME_LIMIT_CHECKS=list(checks), TIME_LIMIT_REFUSALS=[])
                try:
                    tearDownModule()
                except AssertionError as error:
                    return str(error)
                finally:
                    globals().update(saved)
            return None

        cases = {
            "a full run whose limits agree with the table": (full, agree, None),
            "a run without 1 test whose limits agree with the table": (short, agree, None),
            "a full run whose least limit at a site is greater than its entry": (
                full, greater, "time limits: {}".format([stale])),
            "a full run in which a site admitted no limit": (full, missing, "time limits: {}".format([unreached])),
            "a run without 1 test whose least limit at a site is greater than its entry": (short, greater, None),
            "a run without 1 test in which a site admitted no limit": (short, missing, None),
            "a run of this test alone in which a site admitted no limit": (alone, missing, None),
        }
        for kind, (run, checks, wanted) in cases.items():
            with self.subTest(kind=kind):
                self.assertEqual(teardown(run, checks), wanted)
        if time_limit_full_run(module, TESTS_RUN):
            with TIME_LIMIT_LOCK:
                checks = list(TIME_LIMIT_CHECKS)
            self.assertEqual(time_limit_table_mismatches(checks, TEST_TIME_LIMITS), [],
                             "an entry of TEST_TIME_LIMITS that is not the least limit admitted at its site")


# The hook line ranges A-B that this file and tools/test-orch-stage1-hooks.py cite, as HOOK_CITATION
# reads them, that do not start on the first line of a statement of the hook or end on the last line
# of one, each with the lines that it cites on purpose. Every other range that the 2 files cite starts
# and ends on a statement or an except clause of the hook.
PART_RANGES = {
    (22344, 22346): "the lexists check and the header of the with statement that opens turn-state.json",
    (22618, 22632): "the freshness statements and the header of the if statement on the size",
    (22630, 22632): "the fresh and cannot assignments and the header of the if statement on the size",
    (23024, 23025): "the lines of a string",
    (23303, 23305): "lines of a docstring",
    (23321, 23324): "the lexists check and the header of the with statement that opens the checkpoint",
    (23376, 23387): "the checkpoint write and the header of the elif statement on the marker",
    (23433, 23436): "the if statement to the argument of classify_backlog that reads the pending record",
    (33092, 33094): "the at_path assignment and the header of the if statement on it",
    (33211, 33212): "the header of the if statement on lexists and of the with statement that opens it",
}


def hook_statement_lines(source):
    """({the first line of each statement and except clause of source}, {the last line of each})."""
    nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.stmt, ast.ExceptHandler))]
    return {n.lineno for n in nodes}, {n.end_lineno for n in nodes}


class HookRangeProbe(unittest.TestCase):
    """Class probe: each hook line range that this file or tools/test-orch-stage1-hooks.py cites starts
    on the first line of a statement or an except clause of the hook and ends on the last line of one,
    apart from PART_RANGES."""

    def test_each_cited_range_starts_and_ends_on_a_statement(self):
        starts, ends = hook_statement_lines(HOOK.read_text(encoding="utf-8"))
        text = "\n".join(path.read_text(encoding="utf-8")
                         for path in (Path(__file__), HERE / "test-orch-stage1-hooks.py"))
        cited = {(int(a), int(b)) for a, b in HOOK_CITATION.findall(text) if b}
        off = sorted(r for r in cited if r[0] not in starts or r[1] not in ends)
        self.assertEqual(off, sorted(PART_RANGES),
                         "a cited range that does not start or end on a statement, or a stale PART_RANGES")


# Read once every definition of the module is made: the sites of time limits, the sinks and the wrapper
# of unittest.TestCase.run without one.
_sites, _scope = _time_limit_sites(globals(), (run_doctor_recorded, _time_limit_applied, _checked_sink,
                                               _checked_run))
TIME_LIMIT_SITES.update(_sites)
TIME_LIMIT_SCOPE.update(_scope)
# Added once every definition of the module is made; an audit hook cannot be removed.
sys.addaudithook(_admit)

if __name__ == "__main__":
    unittest.main()
