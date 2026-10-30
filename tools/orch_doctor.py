#!/usr/bin/env python3
"""Project-owned operator tool for the AIQT orchestration hooks (item 28.2 stage 2, PR1-f).

The vendored hook names this file in two banners (aiqt_hooks.py:9792 and :9844, "python3
tools/orch_doctor.py --resume-audit"). The pack ships its own orch_doctor.py, but that copy imports
symbols absent from the hook vendored here, so this repository carries its own. It imports the
VENDORED hook by path and reuses its functions, so it never reimplements a decision:

  preflight [stop|idle]  Preview what a Stop (stop) or a scheduling call (idle) would decide now. It
                         follows the hook order exactly: registry, then scope (aiqt_hooks.py:8584-8585
                         for a Stop, :8662-8663 for a scheduling call), then for idle the roster test
                         (:8664-8667), and only then the context and the enumeration (:8586, :8671).
                         Out of scope, or for idle out of the roster, it reports the ALLOW the hook
                         gives there WITHOUT building the context or running the enumerator, since
                         the hook does neither, and an enumerator the preview ran could change what
                         a later Stop decides. In scope it
                         calls _orch_build_ctx(reg, root, kind, data, record_checkpoint=True)
                         (aiqt_hooks.py:8434), the posture of the hook itself, with the two write
                         primitives that call reaches replaced, for that call only, by stand-ins
                         that write nothing (the checkpoint writes, below), and decide_yield
                         (aiqt_hooks.py:8180), then prints
                         the verdict, the reason, the disposition table, and the verdict with the
                         escape sentinel forced off, so the operator sees what the Stop would do
                         without the sentinel. A Stop DENY holds only when the hook can save the
                         denial counter to turn-state.json; when it cannot, the hook fails open with
                         a warning instead (aiqt_hooks.py:8590-8596, the save at :7752-7760). The
                         doctor therefore checks, with os.access and without writing, whether that
                         save could succeed, and when it could not it reports the fail-open
                         ALLOW_WITH_FINDINGS the hook would give, with the reason. A scheduling DENY
                         stands whether or not the counter is saved (aiqt_hooks.py:8694-8698), so
                         the check applies to stop only.
                         The checkpoint writes (fix round 16, M1): the checkpoint union
                         (_orch_checkpoint_union, aiqt_hooks.py:8335-8431, via :8457) makes the
                         only other hook writes inside _orch_build_ctx and its callees: a guard
                         event at :8410, :8416 and :8425, whose result is ignored; the checkpoint
                         rewrite at :8414, whose failure changes no verdict by itself but skips the
                         marker write; and, only when that rewrite succeeds and no init marker
                         exists (:8419), the init-marker write at :8424, whose failure injects a
                         cannot-evaluate row (:8428), so that a Stop the hook would otherwise allow
                         is denied. Both writes go through _orch_write_json_atomic
                         (aiqt_hooks.py:7712-7725: os.makedirs of the state directory at :7718, an
                         open for writing of <path>.tmp at :7720, os.replace at :7722). Its
                         stand-in decides each outcome with lstat, stat and os.access only
                         (_atomic_write_outcome), without writing, and returns it to the hook code,
                         so the hook itself decides whether the marker write is reached and what it
                         injects; the stand-in for _orch_guard_event writes nothing and reports
                         success, since no caller on this path reads its result. The predicted
                         outcome of each write is printed. A write that only writing could decide,
                         a symbolic link, a FIFO or another special file at the temporary path
                         (which the open would follow, block on, or write through), is reported as
                         not previewed, exit 2, whenever its outcome could change the verdict, and
                         a write to any other path, which this preview does not model, is reported
                         the same way. The doctor itself WRITES NOTHING: no
                         checkpoint, no init marker, no guard event, no turn-state, no spoof record,
                         and no bytecode cache. It does run the enumerator the registry declares,
                         exactly as the hook runs it (_orch_enumerate, aiqt_hooks.py:7962-7989: the
                         declared argv as a subprocess with cwd = the root, no shell). That program
                         is outside this tool, and anything it writes is its own, not the doctor's;
                         the output says so.
                         For idle, roster membership is modelled exactly as the hook tests it
                         (aiqt_hooks.py:8664-8667): a tool outside a list-valued yield_tools roster,
                         or any tool when yield_tools is not a list, is allowed unjudged. The
                         quiet-duration check (aiqt_hooks.py:8675-8692) runs inline in the hook before
                         the verdict and writes a guard event, so it cannot be called without
                         writing and is NOT previewed: when the wake text carries a quiet-duration
                         claim (the hook regex _ORCH_QUIET_CLAIM_RE plus the word "quiet"), a verdict
                         other than DENY is reported as unpreviewed, exit 2.
                         The event fields: the previewed handler (orch_stop_guard through
                         _orch_stop_family, aiqt_hooks.py:8569-8614, for stop; orch_yield_tool,
                         :8646-8721, for idle), traced into _orch_root and _orch_build_ctx, reads
                         these fields of the event, and the doctor passes each exactly as the hook
                         reads it, from one input (_event_data):
                           data cwd               :7592         --root
                           data session_id        :8584, :8662  --session-id
                           data stop_hook_active  :8482         --stop-hook-active (true only)
                           data tool_name         :8664         --tool (idle)
                           data tool_input        :8668         built from the two inputs below
                           tool_input stop        :8669         --tool-stop (true only, idle)
                           tool_input values      :8670         --wake-text, as tool_input prompt
                           tool_input prompt      :8702         not previewed (see below)
                         The hook tests stop_hook_active and stop with "is True", so an absent
                         field stands for every other value. With --tool-stop the scheduling call
                         is judged as kind stop, as the hook judges it (:8669): the loop signal
                         and the stop counter apply, the quiet-claim check does not (:8681), and
                         the denial-counter check does not, since a scheduling DENY stands
                         (:8694-8698). tool_input prompt is read at :8702 only after an allowed
                         schedule verdict, for the wake-digest write (_orch_register_wake,
                         :8630-8643); it never changes the verdict, so it needs no input. The test
                         suite scans the hook source for every event field these paths read and
                         holds each to a reviewed table, so a new field fails the suite.
                         Before each hook reader is called, the doctor checks every path that
                         reader would open with a plain blocking open, each resolved as the hook
                         resolves it (_orch_path, aiqt_hooks.py:7630-7635; the state directory by
                         _orch_state_dir_for_root, :7654-7659), and a path is checked only when
                         the hook call path would reach its open, each earlier exit the hook takes
                         modelled from its source (round 8 W1 and W2). The registry files come
                         first (:7606-7626): the machine-local file is always reached, and the
                         committed file only when the lstat of the local file raised
                         FileNotFoundError (:7609-7611), since a present local file returns at
                         :7617-7626 whatever its content and an lstat fault returns at :7612-7617.
                         Before the scope test (_orch_scope_live, :7779-7817) it checks lease.path
                         only when the hook would open the lease for holder scoping (:7807: the
                         stat at :7791 succeeds, the lease is non-empty and fresh, :7792-7799,
                         holder_is_session_id is set, :7800, and a session id is given, :7804),
                         and mode.path (opened at :7771 via :7817) only when no earlier return is
                         taken (a live lease returns at :7799-7811, an unstattable holder lease at
                         :7814-7815). Before the context is built (_orch_build_ctx, :8434-8489) it
                         checks turn-state.json (:7745, via :8441) and then, only when the
                         enumerator would run (a dict with a non-empty argv of non-empty strings,
                         :7967-7971), the enumerator argv from argv[2] on (run with cwd = the root,
                         :7976) and the paths read after a successful enumeration (:8448):
                         dispatch-ledger.jsonl (:7998, opened at :7678), record.pending_decisions
                         (:8044), backlog-checkpoint.json (:8365) and, when attestations is
                         declared (:8068-8070), attestations-validated.json (:8073); the register
                         (:9507 via :8086, :9462 via :8093) only when os.stat succeeds on that
                         snapshot (a failed snapshot open returns at :8075-8076), and its
                         <path>.anchor (:9543) and guard-events.jsonl (:9566) only when os.stat
                         succeeds on the register too (a failed register open holds at :9510, so
                         the reader returns at :8087-8089). Each is checked with os.stat only,
                         never opened. One that exists
                         and is not a regular file (a FIFO, which would block the hook open
                         indefinitely; a directory; a device; or a symlink to one of these) is
                         reported as cannot-evaluate, exit 2, naming the path and its type, and the
                         hook reader that would open it is not called and no enumerator runs. An
                         absent path is left to the hook, whose open raises rather than blocks. The
                         paths only the resume audit opens (the handoff and findings records,
                         mistakes_register and the audit state files) are not checked here, since
                         the preview never opens them, and the escape sentinel is opened
                         non-blocking (:7831) and needs no check.

  --resume-audit         Run the resume audit on demand. It delegates to orch_resume_audit in the
                         vendored hook (aiqt_hooks.py:9765-9794), so the probes (_orch_resume_probes,
                         aiqt_hooks.py:9351-9413, including the attestation snapshot refresh at
                         :9411), the resume-barrier.json write (:9781-9785), and the findings guard
                         event are exactly those of the hook. The same kind of special-file check
                         runs first, over the paths the audit opens with a blocking open, each
                         checked only when the audit would reach its open: record.handoff (:9359),
                         record.findings (:9387 and :9425), record.pending_decisions (:9387), when
                         declared (:9640) the attestations register (:9462 via :9642, :9507 via
                         :9643) and, only when os.stat succeeds on the register (a failed register
                         open holds at :9510), its <path>.anchor (:9543), mistakes_register
                         (:9679), and the state files guard-events.jsonl (read at :9566, appended
                         at :7667 through :9789), escape-spoof.json (:9748), forced-exit.jsonl
                         (:9705), forced-exit-surfaced.json (:9717) only when os.stat succeeds on
                         forced-exit.jsonl and it is not empty (no rows return at :9713-9714),
                         forced-exit-surfaced.json.tmp (written at :7720 through :9734) only when
                         the surfaced file is reached and its stat raises nothing other than
                         FileNotFoundError (any other open error returns at :9721-9724) and, when
                         attestations is declared, attestations-validated.json.tmp (:7720 through
                         :9670). With an unreadable
                         registry the hook opens only resume-barrier.json.unused (:9777) and
                         guard-events.jsonl (:9789). A special file at one of these is reported as
                         cannot-evaluate, exit 2, and the audit is not run. The audit runs no
                         enumerator and does not open the lease (os.stat only, :9398), the mode
                         record, turn-state.json, dispatch-ledger.jsonl or
                         backlog-checkpoint.json, so a special file at one of those, or at an
                         enumerator operand, does not refuse the audit. The hook swallows a failed
                         barrier write (aiqt_hooks.py:9786-9787), so the doctor records the barrier
                         mtime and content BEFORE the audit and requires that the audit rewrote it:
                         the file must have changed and its ts must fall within this run. A barrier
                         the hook could not rewrite (for example a read-only file) is reported as
                         unverified, exit 2, never as the stale state it still holds. Otherwise it
                         reports the observed rewritten state, never the return value of the call.
                         The barrier is read only as a regular file: it is opened non-blocking and
                         its type is checked with fstat on the open descriptor, so a FIFO (which
                         would block a plain open indefinitely), a directory or a device at that path
                         is reported as cannot-evaluate, exit 2, naming the path and the file type,
                         and before the audit that means the audit is not run. This is the only path
                         the doctor itself opens (_read_regular); the test suite scans the source to
                         keep it so.

Options:
  --root DIR         The repository whose registry is read. Default: the git top level of the
                     current working directory, resolved the same way the hook resolves data["cwd"]
                     (_orch_root -> _recovery_toplevel, aiqt_hooks.py:7590-7595).
  --session-id ID    preflight only: the session id used for holder-scoped lease checks
                     (aiqt_hooks.py:7800-7811). Default: none.
  --stop-hook-active preflight only: preview an event whose stop_hook_active is true, which sets
                     the loop signal (aiqt_hooks.py:8482) and so, for the stop kind, the loop-bound
                     release (aiqt_hooks.py:8192-8195). Default: absent.
  --tool-stop        preflight idle only: preview a scheduling call whose tool_input stop is true,
                     which the hook judges as kind stop (aiqt_hooks.py:8669). Default: absent.
  --wake-text TEXT   preflight idle only: the text a scheduling call would carry (the hook joins
                     the string values of tool_input, aiqt_hooks.py:8670), used for the wake-hygiene
                     check (aiqt_hooks.py:8476-8478) and to detect a quiet-duration claim that is
                     not previewed. Default: none.
  --tool NAME        preflight idle only: the scheduling tool whose call is previewed, matched
                     against yield_tools as the hook matches it. Default: ScheduleWakeup.

Exit status:
  preflight      0 when the effective verdict is ALLOW (including out of scope or out of roster),
                 1 when it is DENY or ALLOW_WITH_FINDINGS, 2 on a usage error, an unresolvable root,
                 an absent or unreadable registry, a registry file or a path the preview would
                 open (see above) that exists and is not a regular file, an idle verdict that
                 hangs on the quiet-claim check, which is not previewed, or a checkpoint write
                 whose outcome could change the verdict and cannot be decided without writing.
  --resume-audit 0 when the barrier this audit rewrote reads active false, 1 when it reads active
                 true, 2 on a usage error, an unresolvable root, an absent registry, a registry
                 file or a path the audit would open (see above) that exists and is not a regular
                 file, a barrier that cannot be recorded before or read back after the audit, or a
                 barrier that this audit did not rewrite (unchanged, or a ts outside this run).

Residuals (disclosed): the preview is a point-in-time reading. A later edit to the backlog, the
ledger, the pending-decisions record, the sentinel, or the clock can change what the real hook
decides. The counter-save check is an approximation: os.access tests the permission bits, ACLs and
read-only mounts for the real uid, and it cannot foresee a full disk, a quota, a race with another
writer, or an effective uid that differs from the real one, so its answer can be wrong in either
direction. The checkpoint-write prediction (_atomic_write_outcome) is the same kind of
approximation: it cannot foresee a full disk, a quota, a sticky directory owned by another user, a
race with another writer, or an effective uid that differs from the real one. The enumerator is a
program the registry declares; whatever it writes is outside the
control of this tool. The quiet-duration check is not previewed (see above). The rewrite check on
the barrier detects a write that did not happen; it cannot tell the hook from another writer that
rewrites the file inside the same run. The special-file check is a point-in-time os.stat: a path
replaced by a FIFO between the check and the hook open can still block. It covers, per command, the
declared paths and the fixed state files that the hook call path opens with a plain blocking open,
as listed above. It models every earlier exit that a stat or the registry content decides (an
absent or unstattable file, a file size, a lease age, a declared key, an enumerator argv that cannot
run). A condition that only an open or a program run can decide is not modelled, and the path is
checked whenever the call could reach its open: an enumeration that succeeds, the content of a
regular snapshot, forced-exit log or surfaced set, whether git tracks the attestations register, a
guard-events pointer in a register row, and findings for the audit to record. Where one of those
decides against the open, the doctor can still refuse a run in which the hook would not have opened
that path. The lease age is read from the clock at the check; a lease within SCOPE_MARGIN seconds of
a freshness bound is treated as possibly on either side, so both opens that side decides are
checked. Files read through git (the index, objects
and configuration) and any file the enumerator opens beyond its argv operands are not checked. The
tool runs isolated (it re-executes itself under python3 -I when started
without -I), so a file planted beside it cannot shadow a standard-library import; a failed
re-execution exits 2 with a message.
"""
import os
import sys

if not sys.flags.isolated:
    # Isolated mode keeps this script directory and the environment off the import path, so a file
    # written beside the script cannot shadow a standard-library module (SECI config rule).
    try:
        os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
    except OSError as exc:
        print("orch_doctor.py: cannot re-execute under python3 -I: {}".format(exc), file=sys.stderr)
        sys.exit(2)

import argparse
import datetime
import importlib.util
import json
import stat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "plugin", "aiqt-guardrails-hooks", "hooks", "scripts", "aiqt_hooks.py")

# preflight kind -> the decide_yield kind the hook passes (Stop and TeammateIdle use "stop",
# aiqt_hooks.py:8621 and :8627; a scheduling call that parks the run uses "schedule_idle", :8669,
# unless its tool_input stop is true, which _preflight derives from the event data as the hook
# does).
KINDS = {"stop": "stop", "idle": "schedule_idle"}
DEFAULT_TOOL = "ScheduleWakeup"
# The barrier ts must fall inside this run, widened by this much for clock granularity.
TS_SKEW = datetime.timedelta(seconds=1)
READ_CHUNK = 1 << 20
# A lease within this many seconds of a freshness bound is treated as possibly on either side of it
# when the doctor decides which scope opens the hook reaches (_lease_fresh_states).
SCOPE_MARGIN = 5.0


def _load_hook():
    """Import the vendored hook by path. Bytecode writing is switched off first, so the import leaves
    no __pycache__ beside the hook (preflight writes nothing). Returns the module, or raises
    RuntimeError naming the path when it cannot be loaded (fail closed, never a silent default)."""
    if not os.path.isfile(HOOK):
        raise RuntimeError("vendored hook not found: {}".format(HOOK))
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("aiqt_hooks_vendored", HOOK)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot build an import spec for {}".format(HOOK))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_root(hook, root_arg):
    """The repository root, resolved by the primitive the hook itself uses, so the two agree."""
    start = root_arg if root_arg is not None else os.getcwd()
    if not os.path.isdir(start):
        return None
    return hook._recovery_toplevel(os.path.abspath(start))


class _Unpreviewed(Exception):
    """A hook write whose outcome could change the verdict and that cannot be decided without
    writing; the preview reports it as not previewed, exit 2."""


def _atomic_write_outcome(path):
    """(outcome, reason) for _orch_write_json_atomic(path, obj) (aiqt_hooks.py:7712-7725), decided
    with lstat, stat and os.access only, so nothing is written. outcome is True when the write would
    succeed, False when it would fail (reason says why), and None when only the write itself could
    decide (reason says why). It follows the three steps of the hook: os.makedirs of the parent
    (7718), which fails when the parent, or the nearest existing ancestor of an absent parent, is not
    a directory or cannot be written; the open for writing of path + ".tmp" (7720), which fails on a
    directory there, on a regular file that is not writable, or when it must create the file in a
    directory that cannot be written, and which could follow, block on or write through a symbolic
    link, a FIFO or another special file there (undecided); and os.replace (7722), which fails when
    the directory cannot be written or path is a directory. os.access is an approximation (see
    Residuals)."""
    parent = os.path.dirname(path)
    tmp = path + ".tmp"
    if os.path.lexists(parent) and not os.path.isdir(parent):
        return False, ("{} exists but is not a directory, so os.makedirs raises (aiqt_hooks.py:7718)"
                       .format(parent))
    if not os.path.isdir(parent):
        # os.makedirs would create it under the nearest existing ancestor, and then the temporary
        # file and the rename land in a new empty directory this process created.
        ancestor = os.path.dirname(parent)
        while ancestor and not os.path.lexists(ancestor) and ancestor != os.path.dirname(ancestor):
            ancestor = os.path.dirname(ancestor)
        if not os.path.isdir(ancestor) or not os.access(ancestor, os.W_OK | os.X_OK):
            return False, ("{} is absent and cannot be created under {} (aiqt_hooks.py:7718)"
                           .format(parent, ancestor))
        return True, None
    if not os.access(parent, os.X_OK):
        return False, "{} is not searchable (aiqt_hooks.py:7720)".format(parent)
    writable = os.access(parent, os.W_OK)
    try:
        st = os.lstat(tmp)
    except FileNotFoundError:
        st = None
    except OSError as exc:
        return None, "{} cannot be examined ({})".format(tmp, exc)
    if st is None:
        if not writable:
            return False, ("{} cannot be created in {}, which is not writable (aiqt_hooks.py:7720)"
                           .format(tmp, parent))
    elif stat.S_ISLNK(st.st_mode):
        return None, ("{} is a symbolic link, which the open for writing at aiqt_hooks.py:7720 "
                      "would follow".format(tmp))
    elif stat.S_ISDIR(st.st_mode):
        return False, ("{} is a directory, so the open for writing raises (aiqt_hooks.py:7720)"
                       .format(tmp))
    elif not stat.S_ISREG(st.st_mode):
        return None, ("{} is a {}, which the open for writing at aiqt_hooks.py:7720 could block on "
                      "or write through".format(tmp, _kind_of(st.st_mode)))
    elif not os.access(tmp, os.W_OK):
        return False, "{} is not writable (aiqt_hooks.py:7720)".format(tmp)
    if not writable:
        return False, ("{} is not writable, so the rename at aiqt_hooks.py:7722 raises"
                       .format(parent))
    try:
        target = os.lstat(path)
    except FileNotFoundError:
        target = None
    except OSError as exc:
        return None, "{} cannot be examined ({})".format(path, exc)
    if target is not None and stat.S_ISDIR(target.st_mode):
        return False, ("{} is a directory, so the rename over it raises (aiqt_hooks.py:7722)"
                       .format(path))
    return True, None


def _build_ctx_previewed(hook, reg, root, kind, data, wake_text):
    """(ctx, notes): the context exactly as the hook builds it, _orch_build_ctx with
    record_checkpoint=True (aiqt_hooks.py:8434), with hook._orch_write_json_atomic and
    hook._orch_guard_event replaced for this call only by stand-ins that write nothing. The
    stand-in write returns the outcome _atomic_write_outcome predicts for the checkpoint rewrite
    (aiqt_hooks.py:8414) and the init-marker write (8424), so the hook code itself decides whether
    the marker write is reached (8419) and whether it injects the cannot-evaluate row (8428); notes
    lists the predicted writes. Raises _Unpreviewed for a write the preview does not model, or for
    an undecided write whose outcome could change the verdict: an undecided checkpoint rewrite is
    accepted only when the marker exists or its write would succeed, since either outcome of the
    rewrite then injects nothing, and an undecided marker write is never accepted."""
    sd = hook._orch_state_dir_for_root(root)
    checkpoint = os.path.join(sd, "backlog-checkpoint.json")
    marker = os.path.join(sd, "checkpoint-init.marker")
    notes = []

    def write(path, _obj):
        if path not in (checkpoint, marker):
            raise _Unpreviewed("the hook would write {}, a write this preview does not model"
                               .format(path))
        outcome, reason = _atomic_write_outcome(path)
        if outcome is None and path == checkpoint and (
                os.path.lexists(marker) or _atomic_write_outcome(marker)[0] is True):
            # Either outcome leaves the verdict unchanged: with a marker present the write at 8424
            # is skipped, and with a marker write that would succeed nothing is injected.
            notes.append("checkpoint rewrite (aiqt_hooks.py:8414): undecided ({}); either outcome "
                         "leaves the verdict unchanged".format(reason))
            return True
        if outcome is None:
            what = "checkpoint rewrite" if path == checkpoint else "init-marker write"
            raise _Unpreviewed("the {} could change the verdict and cannot be decided without "
                               "writing: {}".format(what, reason))
        if path == checkpoint:
            notes.append("checkpoint rewrite (aiqt_hooks.py:8414): {}".format(
                "would succeed" if outcome else "would FAIL ({}); the hook then skips the "
                "init-marker write (aiqt_hooks.py:8419)".format(reason)))
        else:
            notes.append("init-marker write (aiqt_hooks.py:8424): {}".format(
                "would succeed" if outcome else "would FAIL ({}); the hook then injects a "
                "cannot-evaluate row (aiqt_hooks.py:8428)".format(reason)))
        return outcome

    def event(*_args, **_kwargs):
        return True

    saved = (hook._orch_write_json_atomic, hook._orch_guard_event)
    hook._orch_write_json_atomic, hook._orch_guard_event = write, event
    try:
        ctx, _ts, _basis = hook._orch_build_ctx(reg, root, kind, data, wake_text=wake_text,
                                                record_checkpoint=True)
    finally:
        hook._orch_write_json_atomic, hook._orch_guard_event = saved
    return ctx, notes


def _counter_save_blocker(state_dir):
    """None when the hook could plausibly save the denial counter, else the reason it could not.
    It mirrors _orch_save_turn_state (aiqt_hooks.py:7752-7760: os.makedirs(state_dir), then open
    turn-state.json for writing) with os.access only, so it writes nothing. os.access is an
    approximation (see Residuals)."""
    path = os.path.join(state_dir, "turn-state.json")
    if os.path.lexists(state_dir) and not os.path.isdir(state_dir):
        return "the state directory {} exists but is not a directory".format(state_dir)
    if not os.path.isdir(state_dir):
        # os.makedirs would create it under the nearest existing ancestor.
        ancestor = os.path.dirname(state_dir)
        while ancestor and not os.path.lexists(ancestor) and ancestor != os.path.dirname(ancestor):
            ancestor = os.path.dirname(ancestor)
        if not os.path.isdir(ancestor) or not os.access(ancestor, os.W_OK | os.X_OK):
            return ("the state directory {} is absent and cannot be created under {}"
                    .format(state_dir, ancestor))
        return None
    if os.path.isdir(path):
        return "{} is a directory".format(path)
    if os.path.exists(path):
        if not os.access(path, os.W_OK):
            return "{} is not writable".format(path)
        if not os.access(state_dir, os.X_OK):
            return "the state directory {} is not searchable".format(state_dir)
        return None
    # Absent, or a dangling symlink, which the open would create at its target.
    parent = os.path.dirname(os.path.realpath(path))
    if not os.path.isdir(parent) or not os.access(parent, os.W_OK | os.X_OK):
        return "{} is absent and cannot be created in {}".format(path, parent)
    return None


def _special_path(label, path):
    """None when path is absent, unreachable by os.stat, or a regular file, else a message naming it
    and its type. It uses os.stat only, never an open, so a FIFO cannot block the check itself;
    os.stat follows a symlink, as the hook open would, so a symlink to a FIFO reports the FIFO. An
    absent or unreachable path is left to the hook, whose open raises rather than blocks."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    if stat.S_ISREG(st.st_mode):
        return None
    return "the {} {} is not a regular file (it is a {})".format(label, path, _kind_of(st.st_mode))


def _site(site, label, path):
    """One pre-check entry: site is the fixed id of the pre-check site (the class-probe table in
    tools/test-orch-stage2-hooks.py lists every id with its reachability condition and hook
    citation), label names the path in the message, and path is the resolved path or None (skipped,
    as the hook skips an undeclared path). Every path the doctor checks passes through here."""
    return (site, label, path)


def _stat_fails(path):
    """True when os.stat raises on path. A path os.stat cannot reach is one the hook open cannot
    open either (the open resolves the same path, so it raises too), which is how the doctor decides
    an earlier exit the hook takes on a failed open without opening anything."""
    try:
        os.stat(path)
    except OSError:
        return True
    return False


def _registry_read_paths(hook, root):
    """The registry files _orch_registry (aiqt_hooks.py:7606-7626) opens, in the order of
    _ORCH_REGISTRY_FILES (7548). A file is opened (7619) only when its lstat succeeds (7609), and
    the loop moves on to the next file only when that lstat raised FileNotFoundError (7610-7611): a
    present file returns at 7617-7626 whatever its content, and an lstat fault returns bad at
    7612-7617, so no later registry file is reached (round 8 W1)."""
    out = []
    for rel in hook._ORCH_REGISTRY_FILES:
        path = os.path.join(root, *rel.split("/"))
        out.append(_site("registry.file", "registry file", path))
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError:
            pass
        break
    return out


def _special_registry_file(hook, root):
    """The first registry file the hook would open that is present but not a regular file, as a
    _special_path message, or None."""
    return _first_special(_registry_read_paths(hook, root))


def _section(reg, key):
    """The registry section key when it is an object, else an empty dict (as the hook reads it)."""
    value = reg.get(key)
    return value if isinstance(value, dict) else {}


def _state_path(hook, root, name):
    """A fixed hook state file under the state directory, resolved exactly as every hook reader
    resolves it (_orch_state_dir_for_root, aiqt_hooks.py:7654-7659)."""
    return os.path.join(hook._orch_state_dir_for_root(root), name)


def _lease_fresh_states(hook, lease, st):
    """The freshness values the hook can compute for this lease (aiqt_hooks.py:7792-7798): {True}
    without a positive max_age_hours, else the value at the clock now and SCOPE_MARGIN seconds later,
    so a lease that crosses a bound of the window between this check and the hook call is treated as
    possibly either side (the window is at least _ORCH_CLOCK_SKEW wide, more than the margin, so the
    two samples cover every value in between)."""
    max_age = lease.get("max_age_hours")
    if not (isinstance(max_age, (int, float)) and max_age > 0):
        return {True}
    age = hook._orch_now().timestamp() - st.st_mtime
    return {-hook._ORCH_CLOCK_SKEW <= a <= max_age * 3600 for a in (age, age + SCOPE_MARGIN)}


def _scope_read_paths(hook, reg, root, session_id):
    """The paths _orch_scope_live(reg, root, session_id) (aiqt_hooks.py:7779-7817) opens with a plain
    blocking open, each only when the hook reaches that open (round 8 W2):
      lease.path  opened at 7806-7808 only when the lease section is a non-empty object (7786-7787),
                  its path resolves (7788-7789), os.stat succeeds (7791), the lease is non-empty and
                  fresh (7792-7799), holder_is_session_id is set (7800) and the session id is a
                  non-empty string (7804-7805; otherwise the hook returns False unopened).
      mode.path   opened by _orch_mode at 7770-7772 via 7817 unless the hook returned first: a live
                  lease returns at 7799-7811, and a lease os.stat cannot reach returns False in
                  holder mode (7812-7815). A stat that succeeds on a stale or empty lease, or a
                  failed stat without holder mode, falls through to the mode read.
    The lease is never opened otherwise (the os.stat at 7791 does not block), so a FIFO there, whose
    size is 0, is not checked."""
    lease = reg.get("lease") if isinstance(reg.get("lease"), dict) else None
    lease_path = hook._orch_path(root, lease.get("path")) if lease else None
    reach_lease, reach_mode = False, True
    if lease_path:
        holder = bool(lease.get("holder_is_session_id"))
        try:
            st = os.stat(lease_path)
        except OSError:
            reach_mode = not holder
        else:
            live = {st.st_size > 0 and fresh for fresh in _lease_fresh_states(hook, lease, st)}
            reach_lease = (True in live and holder and isinstance(session_id, str)
                           and bool(session_id))
            reach_mode = False in live
    out = []
    if reach_lease:
        out.append(_site("scope.lease", "declared lease.path", lease_path))
    if reach_mode:
        out.append(_site("scope.mode", "declared mode.path",
                         hook._orch_path(root, _section(reg, "mode").get("path"))))
    return out


def _enumerator_runs(reg):
    """True when _orch_enumerate (aiqt_hooks.py:7962-7989) reaches the subprocess at 7976: the
    enumerator is an object (7967-7968) whose argv is a non-empty list of non-empty strings
    (7970-7972). Otherwise it returns NO_ENUMERATOR or ENUMERATOR_ERROR unrun, and _orch_build_ctx
    skips every reader after the enumeration (8448)."""
    spec = reg.get("enumerator")
    if not isinstance(spec, dict):
        return False
    argv = spec.get("argv")
    return isinstance(argv, list) and bool(argv) and all(isinstance(a, str) and a for a in argv)


def _ctx_read_paths(hook, reg, root):
    """The paths _orch_build_ctx (aiqt_hooks.py:8434-8489) opens with a plain blocking open for
    reading, traced through every reader it calls, each only when the call reaches it:
      turn-state.json              _orch_turn_state, lexists then open at 7743-7745 (via 8441), always
      enumerator argv[2] on        opened by the enumerator, run with cwd = the root (7976, via 8447),
                                   only when the enumerator runs (_enumerator_runs)
      dispatch-ledger.jsonl        _orch_live_ledger_ids 7998-7999, opened at 7678 (via 8449)
      record.pending_decisions     _orch_pending_haystack, opened at 8043-8045 (via 8451)
      attestations-validated.json  _orch_attestation_refs, opened at 8072-8074 (via 8452), when
                                   attestations is declared (8068-8070)
      attestations                 _orch_register_authority 9507 (via 8086) and _orch_chained_rows
                                   9462 (via 8093), only when os.stat succeeds on the snapshot
                                   (a failed snapshot open returns at 8075-8076)
      attestations.anchor          _orch_register_authority 9543, and guard-events.jsonl
      guard-events.jsonl           (_orch_pointer_resolves 9566, opened at 7678, via 8096 and 9616),
                                   only when os.stat succeeds on the register too (a failed
                                   register open holds at 9509-9510, returned at 8087-8089)
      backlog-checkpoint.json      _orch_checkpoint_union, lexists then open at 8362-8365 (via 8457)
    Every reader after the enumeration runs only on a successful enumeration (8448); the doctor
    models the part a registry read decides (_enumerator_runs) and checks the rest whenever the
    enumerator runs, since only running it decides whether it succeeds. Not modelled, so checked
    conservatively: the snapshot content (8076-8084), whether git tracks the register (9516-9540),
    and a guard-events pointer in a register row (9564). Not opened for reading with a blocking open,
    so not checked here: the checkpoint-init marker (lexists only at 8376 and 8419) and the escape
    sentinel (opened non-blocking at 7831-7832, via 8480). The writes at 8413-8430 are modelled by
    _build_ctx_previewed and _atomic_write_outcome instead."""
    out = [_site("ctx.turn_state", "hook state file turn-state.json",
                 _state_path(hook, root, "turn-state.json"))]
    if not _enumerator_runs(reg):
        return out
    argv = reg["enumerator"]["argv"]
    out += [_site("ctx.enumerator_operand", "declared enumerator.argv[{}]".format(i),
                  hook._orch_path(root, arg)) for i, arg in enumerate(argv[2:], 2)]
    out.append(_site("ctx.ledger", "hook state file dispatch-ledger.jsonl",
                     _state_path(hook, root, "dispatch-ledger.jsonl")))
    out.append(_site("ctx.pending_decisions", "declared record.pending_decisions",
                     hook._orch_path(root, _section(reg, "record").get("pending_decisions"))))
    at_path = hook._orch_path(root, reg.get("attestations"))
    if at_path:
        snapshot = _state_path(hook, root, "attestations-validated.json")
        out.append(_site("ctx.attestation_snapshot", "hook state file attestations-validated.json",
                         snapshot))
        if not _stat_fails(snapshot):
            out.append(_site("ctx.attestations", "declared attestations", at_path))
            if not _stat_fails(at_path):
                out.append(_site("ctx.attestations_anchor", "declared attestations.anchor",
                                 at_path + ".anchor"))
                out.append(_site("ctx.guard_events", "hook state file guard-events.jsonl",
                                 _state_path(hook, root, "guard-events.jsonl")))
    out.append(_site("ctx.checkpoint", "hook state file backlog-checkpoint.json",
                     _state_path(hook, root, "backlog-checkpoint.json")))
    return out


def _forced_exit_may_have_rows(log):
    """False when _orch_read_jsonl(forced-exit.jsonl) cannot return a row: os.stat fails, so the
    open at 7678 raises and returns ([], 0) or (None, 0) (7680-7683), or the file is empty, so
    there are no lines; either way _orch_forced_exit_findings returns at 9706-9714 before the
    surfaced set. A non-empty file may still hold no rows, which only reading it decides, so it
    counts as possibly having rows."""
    try:
        return os.stat(log).st_size != 0
    except OSError:
        return False


def _open_fails_other_than_absent(path):
    """True when os.stat on path raises an error other than FileNotFoundError: the open at 9717
    then raises that error too, and _orch_forced_exit_findings returns at 9721-9724 before the
    surfaced-set rewrite, whereas FileNotFoundError reads as an empty set (9719-9720)."""
    try:
        os.stat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return False


def _audit_read_paths(hook, reg, root):
    """The paths orch_resume_audit (aiqt_hooks.py:9765-9794) opens with a plain blocking open on a
    readable registry, traced through _orch_resume_probes (9351-9413) and every reader it calls,
    each only when the audit reaches it:
      record.handoff                  opened at 9358-9360, when declared
      record.findings                 opened at 9386-9388, and at 9424-9426 (via 9410), when declared
      record.pending_decisions        opened at 9386-9388, when declared
      attestations                    _orch_chained_rows 9462 (via 9642) and _orch_register_authority
                                      9507 (via 9643), when declared (9638-9640)
      attestations.anchor             _orch_register_authority 9543, only when os.stat succeeds on
                                      the register (a failed register open holds at 9509-9510)
      attestations-validated.json.tmp written by _orch_write_json_atomic at 7719-7720 (via 9670),
                                      when attestations is declared
      mistakes_register               _orch_chained_rows 9461-9463 (via 9677-9679), when declared
      guard-events.jsonl              read by _orch_pointer_resolves at 9566 (via 9657 and 9689),
                                      opened at 7678; appended by _orch_guard_event at 7667 (via
                                      9789); both depend on file content, so always checked
      escape-spoof.json               lexists then open at 9747-9748 (via 9412)
      forced-exit.jsonl               _orch_forced_exit_findings 9704-9705, opened at 7678
      forced-exit-surfaced.json       opened at 9716-9717, only when the log may hold rows
                                      (_forced_exit_may_have_rows; no rows return at 9713-9714)
      forced-exit-surfaced.json.tmp   written at 7719-7720 (via 9734), only when the surfaced file
                                      is reached and its open does not fail other than as absent
                                      (_open_fails_other_than_absent; 9721-9724)
    resume-barrier.json (written at 9783) is read before the audit by _barrier_snapshot, which
    refuses a special file there. The audit runs no enumerator and does not open the lease (os.stat
    only, 9398), the mode record, turn-state.json, dispatch-ledger.jsonl or backlog-checkpoint.json,
    so none of those is checked here. Not modelled, so checked conservatively: whether git tracks the
    register (9516-9540), the rows and pointers a register holds (9564, 9657, 9689), the rows the
    forced-exit log and the surfaced set hold (9706-9733), and whether there are findings to record
    (9788-9789)."""
    rec = _section(reg, "record")
    out = [_site("audit.handoff", "declared record.handoff", hook._orch_path(root, rec.get("handoff"))),
           _site("audit.findings", "declared record.findings",
                 hook._orch_path(root, rec.get("findings"))),
           _site("audit.pending_decisions", "declared record.pending_decisions",
                 hook._orch_path(root, rec.get("pending_decisions")))]
    at_path = hook._orch_path(root, reg.get("attestations"))
    if at_path:
        out.append(_site("audit.attestations", "declared attestations", at_path))
        if not _stat_fails(at_path):
            out.append(_site("audit.attestations_anchor", "declared attestations.anchor",
                             at_path + ".anchor"))
        out.append(_site("audit.snapshot_tmp", "hook state file attestations-validated.json.tmp",
                         _state_path(hook, root, "attestations-validated.json.tmp")))
    out.append(_site("audit.mistakes_register", "declared mistakes_register",
                     hook._orch_path(root, reg.get("mistakes_register"))))
    out.append(_site("audit.guard_events", "hook state file guard-events.jsonl",
                     _state_path(hook, root, "guard-events.jsonl")))
    out.append(_site("audit.escape_spoof", "hook state file escape-spoof.json",
                     _state_path(hook, root, "escape-spoof.json")))
    log = _state_path(hook, root, "forced-exit.jsonl")
    out.append(_site("audit.forced_exit", "hook state file forced-exit.jsonl", log))
    if _forced_exit_may_have_rows(log):
        surfaced = _state_path(hook, root, "forced-exit-surfaced.json")
        out.append(_site("audit.forced_exit_surfaced", "hook state file forced-exit-surfaced.json",
                         surfaced))
        if not _open_fails_other_than_absent(surfaced):
            out.append(_site("audit.forced_exit_surfaced_tmp",
                             "hook state file forced-exit-surfaced.json.tmp", surfaced + ".tmp"))
    return out


def _audit_bad_registry_paths(hook, root):
    """On an unreadable registry the audit opens only resume-barrier.json.unused (appended at 7667,
    via 9777) and guard-events.jsonl (appended at 7667, via 9789, since the unreadable registry is
    itself a finding, 9778), beside the barrier, under the state directory the hook resolves for
    that registry (aiqt_hooks.py:9775). Both are always reached."""
    return [_site("audit_bad.unused", "hook state file resume-barrier.json.unused",
                  _state_path(hook, root, "resume-barrier.json.unused")),
            _site("audit_bad.guard_events", "hook state file guard-events.jsonl",
                  _state_path(hook, root, "guard-events.jsonl"))]


def _first_special(entries):
    """The first _site entry whose path is present but not a regular file, as a _special_path
    message, or None. An entry with no path (an undeclared key) is skipped."""
    for _site_id, label, path in entries:
        if not path:
            continue
        found = _special_path(label, path)
        if found is not None:
            return found
    return None


def _refuse_special(found):
    """Report a special file at a path the hook would open, as cannot-evaluate, exit 2."""
    print("cannot evaluate: {}; the hook would open it with a blocking open, so the hook reader that "
          "opens it was not called and no enumerator ran".format(found))
    return 2


def _print_disposition(disposition):
    if not disposition:
        print("disposition: (empty)")
        return
    print("disposition:")
    for cls, iid, col3, col4 in disposition:
        print("  {:<16} {:<12} {} {}".format(cls, iid, col3, col4).rstrip())


def _event_data(kind_name, session_id, stop_hook_active, tool, tool_stop, wake_text):
    """The event payload the previewed handler would receive, built from the doctor inputs, with
    each field in the form the hook reads it (the event-field table in the module docstring; the
    class probe in tools/test-orch-stage2-hooks.py keeps it in step with the hook source). cwd is
    not carried: --root stands for it, resolved as _orch_root resolves data["cwd"]
    (aiqt_hooks.py:7590-7595). A flag that is off leaves its field absent, which the hook reads
    exactly as any value other than true (its tests are "is True", aiqt_hooks.py:8482 and 8669)."""
    data = {}
    if session_id:
        data["session_id"] = session_id
    if stop_hook_active:
        data["stop_hook_active"] = True
    if kind_name == "idle":
        tool_input = {}
        if wake_text is not None:
            tool_input["prompt"] = wake_text
        if tool_stop:
            tool_input["stop"] = True
        data["tool_name"] = tool
        data["tool_input"] = tool_input
    return data


def _preflight(hook, root, kind_name, data):
    status, reg = hook._orch_registry(root)
    print("orch_doctor preflight {}: root {}".format(kind_name, root))
    print("event data previewed: {}".format(json.dumps(data, sort_keys=True)))
    if status == "absent":
        print("registry: absent; the orchestration suite is inert here, nothing to preview")
        return 2
    if status == "bad":
        print("registry: unreadable ({})".format(reg))
        print("posture on an unreadable registry: a Stop fails open with a warning "
              "(aiqt_hooks.py:8579-8583); a scheduling call is denied (aiqt_hooks.py:8654-8661)")
        return 2
    print("registry: ok")
    # The session id exactly as both handlers read it (aiqt_hooks.py:8584 and 8662).
    session_id = data.get("session_id")
    special = _first_special(_scope_read_paths(hook, reg, root, session_id))
    if special is not None:
        # _orch_scope_live opens these with a plain blocking open (see _scope_read_paths), so a FIFO
        # there would hang the preview; the scope reader is not called.
        return _refuse_special(special)
    scope_live = hook._orch_scope_live(reg, root, session_id)
    print("scope: {}".format("live" if scope_live else
                             "not live (the hook allows without judging)"))
    if not scope_live:
        # The hook returns here, before the context is built or the enumerator runs
        # (aiqt_hooks.py:8584-8585 for a Stop, :8662-8663 for a scheduling call), so neither does
        # the preview: an enumerator run here could change what a later Stop decides.
        print("enumeration: not run (out of scope, the hook allows before it enumerates)")
        print("writes: the doctor itself wrote nothing, and no enumerator ran")
        print("effective verdict: ALLOW (out of scope)")
        return 0
    quiet_claim = False
    kind, wake_text = KINDS[kind_name], None
    if kind_name == "idle":
        tool = data.get("tool_name")
        declared = reg.get("yield_tools")
        # Exactly the hook test: allowed unjudged unless yield_tools is a list holding the tool
        # (aiqt_hooks.py:8664-8667).
        in_roster = isinstance(declared, list) and tool in declared
        if isinstance(declared, list):
            print("yield_tools roster: {}".format(", ".join(str(t) for t in declared) or "(empty)"))
        else:
            print("yield_tools roster: not a declared list")
        print("tool {}: {}".format(tool, "in the roster, judged" if in_roster else
                                   "not in the roster; the hook allows it unjudged "
                                   "(aiqt_hooks.py:8664-8667)"))
        if not in_roster:
            # The hook returns here too, before the context or the enumeration (aiqt_hooks.py:8667).
            print("enumeration: not run (out of the roster, the hook allows before it enumerates)")
            print("writes: the doctor itself wrote nothing, and no enumerator ran")
            print("effective verdict: ALLOW (out of the roster)")
            return 0
        # Exactly the hook derivation of the kind and the wake text (aiqt_hooks.py:8668-8670).
        tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        kind = "stop" if tool_input.get("stop") is True else "schedule_idle"
        wake_text = " ".join(str(v) for v in tool_input.values() if isinstance(v, str))
        print("judged kind: {}".format(
            "stop (tool_input stop is true, aiqt_hooks.py:8669)" if kind == "stop"
            else "schedule_idle (aiqt_hooks.py:8669)"))
        if kind != "schedule_idle":
            print("quiet-claim check: not applicable; the hook runs it only for the schedule_idle "
                  "kind (aiqt_hooks.py:8681)")
        else:
            quiet_claim = (bool(hook._ORCH_QUIET_CLAIM_RE.search(wake_text))
                           and "quiet" in wake_text.lower())
            if quiet_claim:
                print("quiet-claim check: NOT PREVIEWED; the wake text carries a quiet-duration "
                      "claim, which the hook judges inline against the measured gap since the last "
                      "human input before the verdict below (aiqt_hooks.py:8675-8692); it cannot "
                      "be called without writing a guard event")
            else:
                print("quiet-claim check: not previewed (aiqt_hooks.py:8675-8692); the wake text "
                      "carries no quiet-duration claim, so the check does not fire")
    special = _first_special(_ctx_read_paths(hook, reg, root))
    if special is not None:
        # _orch_build_ctx opens these with a plain blocking open (see _ctx_read_paths), so a FIFO
        # there would hang the preview; the context is not built and no enumerator runs.
        return _refuse_special(special)
    # The context as each handler builds it: a Stop passes no wake text (aiqt_hooks.py:8586), a
    # scheduling call the joined tool_input text (:8671); both pass the event data, whose
    # stop_hook_active sets the loop signal (:8482).
    try:
        ctx, notes = _build_ctx_previewed(hook, reg, root, kind, data, wake_text)
    except _Unpreviewed as exc:
        print("writes: the doctor itself wrote nothing; the registry enumerator ran as the hook runs "
              "it (aiqt_hooks.py:7962-7989), and anything that program writes is its own")
        print("hook write: NOT PREVIEWED; {}".format(exc))
        print("effective verdict: UNPREVIEWED (the verdict depends on a hook write that cannot be "
              "decided without writing)")
        return 2
    if ctx["enum_status"] == "ok":
        print("enumeration: ok")
    else:
        print("enumeration: {}: {}".format(ctx["enum_status"], ctx["enum_detail"]))
    print("writes: the doctor itself wrote nothing; the registry enumerator ran as the hook runs it "
          "(aiqt_hooks.py:7962-7989), and anything that program writes is its own")
    if ctx["enum_status"] != "ok":
        print("checkpoint writes: none; the hook reaches the checkpoint union only after a "
              "successful enumeration (aiqt_hooks.py:8448)")
    for note in notes:
        print("predicted hook write, not made: {}".format(note))
    if ctx["enum_status"] == "ok" and not any(n.startswith("init-marker") for n in notes):
        print("predicted hook write, not made: init-marker write (aiqt_hooks.py:8424): not "
              "reached (the marker exists, or the checkpoint rewrite would fail)")
    print("loop signal: {}".format("set (stop_hook_active is true, aiqt_hooks.py:8482)"
                                   if ctx["loop_signal"] else "not set"))
    if ctx["escape"]:
        print("escape sentinel: active (an operator release is open)")
    elif ctx.get("escape_spoof"):
        print("escape sentinel: ignored ({}); the hook would record this as a spoof"
              .format(ctx["escape_spoof"]))
    else:
        print("escape sentinel: absent")
    verdict, reason, disposition = hook.decide_yield(ctx)
    no_escape = dict(ctx)
    no_escape["escape"] = False
    verdict_ne, reason_ne, _disp_ne = hook.decide_yield(no_escape)
    # Scope and roster were settled above, so every verdict that reaches this point is judged.
    effective = verdict
    print("judged verdict: {}".format(verdict))
    print("judged reason: {}".format(reason))
    print("verdict without the escape sentinel: {}".format(verdict_ne))
    print("reason without the escape sentinel: {}".format(reason_ne))
    if kind_name == "stop":
        blocker = _counter_save_blocker(hook._orch_state_dir_for_root(root))
        if blocker is None:
            print("denial counter: could be saved (an os.access check; the hook saves it on a DENY)")
        else:
            print("denial counter: could NOT be saved ({}; an os.access check)".format(blocker))
            if effective == "DENY":
                # aiqt_hooks.py:8590-8596: an unsaved counter never reaches the loop bound, so the
                # Stop fails open with a warning rather than re-denying.
                print("effective verdict: ALLOW_WITH_FINDINGS (the fail-open allow the hook gives "
                      "when the denial counter cannot be saved, aiqt_hooks.py:8590-8596; the judged "
                      "DENY would not hold. Underlying: {})".format(reason))
                _print_disposition(disposition)
                return 1
    else:
        print("denial counter: not checked; a scheduling DENY stands whether or not the counter "
              "is saved (aiqt_hooks.py:8694-8698)")
    if quiet_claim and effective != "DENY":
        # The quiet-claim check runs before decide_yield and may deny; a DENY stands either way.
        print("effective verdict: UNPREVIEWED ({} unless the quiet-claim check denies)"
              .format(effective))
        _print_disposition(disposition)
        return 2
    print("effective verdict: {}".format(effective))
    _print_disposition(disposition)
    return 0 if effective == "ALLOW" else 1


def _kind_of(mode):
    """The file type of an st_mode that is not a regular file, for the cannot-evaluate message."""
    for test, name in ((stat.S_ISDIR, "directory"), (stat.S_ISCHR, "character device"),
                       (stat.S_ISBLK, "block device"), (stat.S_ISFIFO, "FIFO"),
                       (stat.S_ISSOCK, "socket"), (stat.S_ISLNK, "symbolic link")):
        if test(mode):
            return name
    return "file of unknown type (st_mode {:o})".format(stat.S_IFMT(mode))


def _read_regular(path):
    """(stat result, bytes) of path, read only when it is a regular file. The open is non-blocking,
    so a FIFO with no writer cannot hang the doctor, and fstat checks the open descriptor, so the
    stat and the bytes describe the same file. An absent path raises FileNotFoundError; a path that
    is not a regular file raises OSError naming the path and its type."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("{} is not a regular file (it is a {})".format(path, _kind_of(st.st_mode)))
        os.set_blocking(fd, True)
        chunks = []
        while True:
            chunk = os.read(fd, READ_CHUNK)
            if not chunk:
                break
            chunks.append(chunk)
        return st, b"".join(chunks)
    finally:
        os.close(fd)


def _barrier_snapshot(path):
    """(mtime_ns, content bytes) of the barrier, None when it is absent; OSError on any other
    failure, including a barrier that is not a regular file, which the caller reports as
    cannot-evaluate."""
    try:
        st, data = _read_regular(path)
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, data)


def _resume_audit(hook, root):
    status, reg = hook._orch_registry(root)
    print("orch_doctor resume-audit: root {}".format(root))
    if status == "absent":
        print("registry: absent; the orchestration suite is inert here, nothing to audit")
        return 2
    # The audit opens these with a plain blocking open (see _audit_read_paths), so a FIFO there would
    # hang it; the audit is not run.
    if status == "ok":
        special = _first_special(_audit_read_paths(hook, reg, root))
    else:
        special = _first_special(_audit_bad_registry_paths(hook, root))
    if special is not None:
        return _refuse_special(special)
    barrier_path = os.path.join(hook._orch_state_dir_for_root(root), "resume-barrier.json")
    try:
        before = _barrier_snapshot(barrier_path)
    except OSError as exc:
        print("barrier: cannot be recorded before the audit at {} ({}); a rewrite could not be "
              "confirmed, so the audit is not run".format(barrier_path, exc))
        return 2
    start = hook._orch_now()
    hook.orch_resume_audit({"cwd": root})
    end = hook._orch_now()
    try:
        after = _barrier_snapshot(barrier_path)
    except OSError as exc:
        after, read_error = None, exc
    else:
        read_error = "absent"
    if after is None:
        print("barrier: cannot be read back from {} ({}); the audit result is unverified"
              .format(barrier_path, read_error))
        return 2
    if before is not None and after == before:
        print("barrier: NOT rewritten by this audit ({} has the same mtime and content as before "
              "the run); the hook could not write it (for example the file is read-only), so the "
              "state it holds is stale and the audit result is unverified".format(barrier_path))
        return 2
    try:
        barrier = json.loads(after[1].decode("utf-8"))
    except ValueError as exc:
        print("barrier: cannot be read back from {} ({}); the audit result is unverified"
              .format(barrier_path, exc))
        return 2
    stamp = hook._orch_parse_utc(barrier.get("ts")) if isinstance(barrier, dict) else None
    if stamp is None or stamp < start - TS_SKEW or stamp > end + TS_SKEW:
        print("barrier: its ts {!r} is not from this audit run ({} to {}); it was not rewritten by "
              "this audit, so the audit result is unverified".format(
                  barrier.get("ts") if isinstance(barrier, dict) else None,
                  start.isoformat(), end.isoformat()))
        return 2
    if not isinstance(barrier, dict) or not isinstance(barrier.get("active"), bool):
        print("barrier: malformed at {}; the audit result is unverified".format(barrier_path))
        return 2
    findings = barrier.get("findings") if isinstance(barrier.get("findings"), list) else []
    print("barrier: {} ({})".format("active" if barrier["active"] else "clear", barrier_path))
    for finding in findings:
        print("  finding: {}".format(finding))
    return 1 if barrier["active"] else 0


def main(argv):
    parser = argparse.ArgumentParser(
        prog="orch_doctor.py",
        description="Preview the orchestration stop and yield verdicts, or run the resume audit.")
    parser.add_argument("command", nargs="?", choices=["preflight"],
                        help="preflight: preview a verdict; the doctor itself writes nothing, and "
                             "the declared enumerator runs as the hook runs it")
    parser.add_argument("kind", nargs="?", choices=sorted(KINDS), default="stop",
                        help="preflight boundary: stop (default) or idle")
    parser.add_argument("--resume-audit", action="store_true",
                        help="run the resume audit and rewrite resume-barrier.json")
    parser.add_argument("--root", default=None, help="repository root (default: git top level of cwd)")
    parser.add_argument("--session-id", default=None, help="preflight: session id for holder scoping")
    parser.add_argument("--stop-hook-active", action="store_true",
                        help="preflight: preview an event whose stop_hook_active is true")
    parser.add_argument("--wake-text", default=None, help="preflight idle: the wake text to judge")
    parser.add_argument("--tool", default=None,
                        help="preflight idle: the scheduling tool (default {})".format(DEFAULT_TOOL))
    parser.add_argument("--tool-stop", action="store_true",
                        help="preflight idle: preview a call whose tool_input stop is true")
    args = parser.parse_args(argv)
    if bool(args.resume_audit) == bool(args.command):
        parser.print_usage(sys.stderr)
        print("orch_doctor.py: give exactly one of: preflight [stop|idle], or --resume-audit",
              file=sys.stderr)
        return 2
    if args.tool is not None and (args.resume_audit or args.kind != "idle" or not args.tool):
        parser.print_usage(sys.stderr)
        print("orch_doctor.py: --tool takes a non-empty name and applies only to preflight idle",
              file=sys.stderr)
        return 2
    if (args.tool_stop or args.wake_text is not None) \
            and (args.resume_audit or args.kind != "idle"):
        # A Stop event carries no tool_input (aiqt_hooks.py:8586 passes no wake text), so an input
        # the previewed handler never reads is refused rather than silently ignored.
        parser.print_usage(sys.stderr)
        print("orch_doctor.py: --tool-stop and --wake-text apply only to preflight idle",
              file=sys.stderr)
        return 2
    if args.stop_hook_active and args.resume_audit:
        parser.print_usage(sys.stderr)
        print("orch_doctor.py: --stop-hook-active applies only to preflight", file=sys.stderr)
        return 2
    try:
        hook = _load_hook()
    except Exception as exc:  # an unloadable hook is a cannot-evaluate, reported, never a pass
        print("orch_doctor.py: cannot load the vendored hook ({})".format(exc), file=sys.stderr)
        return 2
    root = _resolve_root(hook, args.root)
    if root is None:
        print("orch_doctor.py: cannot resolve a git top level from {}".format(
            args.root if args.root is not None else os.getcwd()), file=sys.stderr)
        return 2
    special = _special_registry_file(hook, root)
    if special is not None:
        print("orch_doctor.py: root {}".format(root))
        return _refuse_special(special)
    if args.resume_audit:
        return _resume_audit(hook, root)
    data = _event_data(args.kind, args.session_id, args.stop_hook_active,
                       args.tool if args.tool is not None else DEFAULT_TOOL, args.tool_stop,
                       args.wake_text)
    return _preflight(hook, root, args.kind, data)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
