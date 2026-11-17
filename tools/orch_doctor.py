#!/usr/bin/env python3
"""Project-owned operator tool for the AIQT orchestration hooks (item 28.2 stage 2, PR1-f).

The vendored hook names this file in its resume banners (aiqt_hooks.py:33337 and :33343, "python3
tools/orch_doctor.py --resume-audit"). The pack ships its own orch_doctor.py, but that copy imports
symbols absent from the hook vendored here, so this repository carries its own. It imports the
VENDORED hook by path and reuses its functions, so it never reimplements a decision:

  preflight [stop|idle]  Preview what a Stop (stop) or a scheduling call (idle) would decide now. It
                         follows the hook order exactly: registry, then scope (_orch_scope_live at
                         aiqt_hooks.py:23577-23579 for a Stop, _orch_scope_live at :23684-23686 for a
                         scheduling call), then for idle the roster test (yield_tools at :23687-23690),
                         and only then the context and the enumeration (_orch_build_ctx at :23580,
                         _orch_build_ctx at :23694).
                         Out of scope, or for idle out of the roster, it reports the ALLOW the hook
                         gives there WITHOUT building the context or running the enumerator, since
                         the hook does neither, and an enumerator the preview ran could change what
                         a later Stop decides. In scope it
                         calls _orch_build_ctx(reg, root, kind, data, record_checkpoint=True)
                         (aiqt_hooks.py:23412), the posture of the hook itself, with the two write
                         primitives that call reaches replaced, for that call only, by stand-ins
                         that write nothing (the checkpoint writes, below), and decide_yield
                         (aiqt_hooks.py:23041), then prints
                         the verdict, the reason, the disposition table, and the verdict with the
                         escape sentinel forced off, so the operator sees what the Stop would do
                         without the sentinel. A Stop DENY holds only when the hook can save the
                         denial counter to turn-state.json; when it cannot, the hook fails open with
                         a warning instead (_orch_record_denial at aiqt_hooks.py:23591-23597, the
                         save at :22353-22362, through _orch_write_json_atomic). The doctor
                         therefore checks, with lstat
                         and os.access and without writing, whether that save could succeed, and
                         when it could not it reports the fail-open ALLOW_WITH_FINDINGS the hook
                         would give, with the reason. A scheduling DENY stands whether or not the
                         counter is saved (_orch_record_denial at aiqt_hooks.py:23730-23747), so the
                         check applies to stop only.
                         The checkpoint writes: the checkpoint union
                         (_orch_checkpoint_union, aiqt_hooks.py:23289-23409, via :23442) makes the
                         only other hook writes inside _orch_build_ctx and its callees: the guard
                         events of _orch_event_warn (:22316), whose result adds at most a warning
                         and never changes the decision; the checkpoint rewrite at :23376, whose
                         failure changes no verdict by itself but skips the marker write and adds a
                         recording-failure warning; and, only when that rewrite succeeds and no init
                         marker exists (os.path.lexists at :23387), the init-marker write at :23392,
                         whose failure injects a cannot-evaluate row (injected.append at :23397), so
                         that a Stop the hook would otherwise allow is denied. Both writes go through
                         _orch_write_json_atomic (aiqt_hooks.py:22207-22298: os.makedirs of the state
                         directory at :22243, the open of that directory at :22244, the lstat of the
                         target (os.stat at :22262), a temporary file created under a random name
                         with O_CREAT|O_EXCL|O_NOFOLLOW
                         at :22266-22267, os.replace at :22287; None on success, else a failure
                         detail). Its stand-in decides each outcome with lstat, stat and os.access
                         only (_atomic_write_outcome), without writing, and returns it to the hook
                         code in the hook writer's own form, so the hook itself decides whether the
                         marker write is reached, what it injects and which recording-failure
                         warnings it adds; the stand-in for _orch_guard_event writes nothing and
                         reports success. The predicted outcome of each write is printed. Because
                         the hook writer creates its temporary file under a fresh random name and
                         never opens an existing entry, no entry at a temporary-like path can block,
                         obstruct or redirect the write, and every outcome is decided from the state
                         directory and the target. A write to any other path, which this preview
                         does not model, is reported as not previewed, exit 2. An ALLOW that the
                         hook would give with a recording-failure warning (a failed checkpoint
                         rewrite, or for a schedule_idle call a wake digest that cannot be saved to
                         turn-state.json, _orch_register_wake, :23641-23663, called at :23751) is
                         reported as ALLOW_WITH_FINDINGS, as the hook surfaces it (:23621-23624 for
                         a Stop, :23775-23779 for a scheduling call). The doctor itself WRITES
                         NOTHING: no checkpoint, no init marker, no guard event, no turn-state, no spoof
                         record, and no bytecode cache. It does run the enumerator the registry declares,
                         exactly as the hook runs it (_orch_enumerate, aiqt_hooks.py:22815-22848: the
                         declared argv as a subprocess with cwd = the root, no shell). That program
                         is outside this tool, and anything it writes is its own, not the doctor's;
                         the output says so.
                         For idle, roster membership is modelled exactly as the hook tests it
                         (aiqt_hooks.py:23687-23690): a tool outside a list-valued yield_tools roster,
                         or any tool when yield_tools is not a list, is allowed unjudged. The
                         quiet-duration check (aiqt_hooks.py:23703-23722) runs inline in the hook before
                         the verdict and writes a guard event, so it cannot be called without
                         writing and is NOT previewed: when the wake text carries a quiet-duration
                         claim (the hook regex _ORCH_QUIET_CLAIM_RE plus the word "quiet"), a verdict
                         other than DENY is reported as unpreviewed, exit 2.
                         The event fields: the previewed handler (orch_stop_guard through
                         _orch_stop_family, aiqt_hooks.py:23562-23625, for stop; orch_yield_tool,
                         :23666-23780, for idle), traced into _orch_root and _orch_build_ctx, reads
                         these fields of the event, and the doctor passes each exactly as the hook
                         reads it, from one input (_event_data):
                           data cwd               :21725          --root
                           data session_id        :23577, :23684  --session-id
                           data stop_hook_active  :23468          --stop-hook-active (true only)
                           data tool_name         :23687          --tool (idle)
                           data tool_input        :23691          built from the two inputs below
                           tool_input stop        :23692          --tool-stop (true only, idle)
                           tool_input values      :23693          --wake-text, as tool_input prompt
                           tool_input prompt      :23751          not previewed (see below)
                         The hook tests stop_hook_active and stop with "is True", so an absent
                         field stands for every other value. With --tool-stop the scheduling call
                         is judged as kind stop, as the hook judges it (:23692): the loop signal
                         and the stop counter apply, the quiet-claim check (for kind
                         "schedule_idle" at :23709 only) does not, and the denial-counter check does
                         not, since a scheduling DENY stands
                         (:23730-23747). tool_input prompt is read at :23751 only after an allowed
                         schedule verdict, for the wake-digest write (_orch_register_wake,
                         :23641-23663); it never changes the verdict, so it needs no input. The test
                         suite scans the hook source for every event field these paths read and
                         holds each to a reviewed table, so a new field fails the suite.
                         Before each hook reader is called, the doctor checks the paths that
                         reader would open, most with a plain blocking open; the hook opens the
                         registry files, mode.path, record.pending_decisions and the attestations
                         anchor without blocking (see below), and the enumerator, not the hook,
                         opens its operands. Each path is resolved as the hook
                         resolves it (_orch_path, aiqt_hooks.py:22125-22130; the state directory by
                         _orch_state_dir_for_root, :22149-22154), and a path is checked only when
                         the hook call path would reach its open, each earlier exit the hook takes
                         modelled from its source. The registry files come
                         first (:22084-22121): the machine-local file is always reached, and the
                         committed file only when the lstat of the local file raised
                         FileNotFoundError (:22087-22089), since a present local file returns at
                         :22096-22121 (os.open) whatever its content and an lstat fault returns at
                         :22090-22095 (`except OSError as exc`).
                         Before the scope test (_orch_scope_live, :22596-22656) it checks lease.path
                         only when the hook would open the lease for holder scoping (:22640: the
                         stat at :22617 succeeds, the lease is non-empty and fresh, :22618-22632,
                         holder_is_session_id is set, :22633, and a session id is given, :22637),
                         and mode.path (os.open with O_NONBLOCK at :22445, via _orch_mode at
                         :22654, which reads a file that is not regular as unattended) only when no
                         earlier return is taken (a live lease returns at :22632-22644, an
                         unstattable holder lease, holder_is_session_id at :22651-22652). Before the
                         context is built (_orch_build_ctx, :23412-23475) it checks turn-state.json
                         (:22346, via _orch_turn_state at :23420) and then, only when the enumerator
                         would run (a dict with a non-empty argv of non-empty strings,
                         :22820-22828), the enumerator argv from argv[2] on (run with cwd = the
                         root, subprocess.run at :22833) and the paths read after a successful
                         enumeration (`status == "ok"` at :23433): dispatch-ledger.jsonl
                         (_orch_live_ledger_ids at :22857, opened by _orch_read_jsonl at :22173),
                         record.pending_decisions
                         (:22905), backlog-checkpoint.json (:23324) and, when attestations is
                         declared (`reg.get("attestations")` at :22929-22931),
                         attestations-validated.json (:22934); the register
                         (_orch_register_authority at :32921 via :22947, and `open` at :32876 via
                         _orch_chained_rows at :22954) only when os.stat succeeds on that snapshot (a
                         failed snapshot open takes `return "unreadable"` at :22936-22937), and its
                         <path>.anchor (os.open at :32968) and guard-events.jsonl (:33020) only when
                         os.stat succeeds on the register too (a failed register open takes
                         `return ("hold"` at :32924, so the reader returns at :22948-22950 on
                         `astatus != "ok"`). Each is checked with os.stat only, never opened. One
                         that exists
                         and is not a regular file (a FIFO, which would block a blocking open
                         indefinitely; a directory; a device; or a symlink to one of these) is
                         reported as cannot-evaluate, exit 2, naming the path and its type, and no
                         hook reader is called on it and no enumerator runs. The report
                         then says whether and how the hook would open that path: for the registry
                         files, mode.path, record.pending_decisions and the attestations anchor,
                         that the hook would not block on it, naming the reader that opens it with
                         O_NONBLOCK and what that reader makes of a file that is not regular; for
                         an enumerator operand, that the hook does not open it; and for every
                         other path, that the hook would open it with a blocking open. It ends
                         by saying that the hook reader that opens the path was not called and
                         no enumerator ran, or, at an enumerator operand, which no hook reader
                         opens, only that no enumerator ran. An
                         absent path is left to the hook, whose open raises rather than blocks. The
                         paths only the resume audit opens (the handoff and findings records,
                         mistakes_register and the audit state files) are not checked here, since
                         the preview never opens them, and the escape sentinel, which the hook
                         opens non-blocking (os.open at :22670) and judges on the open descriptor,
                         is not checked.

  --resume-audit         Run the resume audit on demand. It delegates to orch_resume_audit in the
                         vendored hook (aiqt_hooks.py:33270-33354), so the probes (_orch_resume_probes,
                         aiqt_hooks.py:32738-32822, including the attestation snapshot refresh,
                         _orch_validate_attestations at :32820), the resume-barrier.json write
                         (:33323-33325), and the findings guard event are exactly those of the hook.
                         The same kind of special-file check runs first, over the paths the audit
                         opens, each checked only when the audit would reach its open; it opens
                         the record surfaces and the anchor without blocking, the others with a
                         blocking open: record.handoff (_orch_record_surface_read at :32760),
                         record.findings (:32790 and _orch_record_surface_read at :32837),
                         record.pending_decisions (:32790), when declared (at_path at :33094) the
                         attestations register (`open` at :32876 via _orch_chained_rows at :33096,
                         `open` at :32921 via _orch_register_authority at :33097) and, only when
                         os.stat succeeds on the register (a failed register open takes
                         `return ("hold"` at :32924), its <path>.anchor (os.open at :32968),
                         mistakes_register (:33134), and the state files guard-events.jsonl (read at
                         :33020, appended by _orch_append_jsonl at :22162 through _orch_event_warn at
                         :33334), escape-spoof.json (:33212), forced-exit.jsonl (:33160),
                         and forced-exit-surfaced.json (:33172) only when os.stat succeeds on
                         forced-exit.jsonl and it is not empty (no rows return at :33168-33169).
                         The hook's rewrites of the surfaced set and of the attestation snapshot
                         open no fixed path: _orch_write_json_atomic (via :33191 and :33124)
                         writes a new <name>.<16 hex>.tmp file (os.urandom at :22266, os.open
                         with O_EXCL at :22267), so the doctor checks neither the old fixed
                         forced-exit-surfaced.json.tmp nor attestations-validated.json.tmp
                         path. With an unreadable registry the hook
                         opens only resume-barrier.json.unused (_orch_append_jsonl at :33317) and
                         guard-events.jsonl (_orch_event_warn at :33334). A special file at one of
                         these is reported as
                         cannot-evaluate, exit 2, and the audit is not run. The audit runs no
                         enumerator and does not open the lease (os.stat only, :32800), the mode
                         record, turn-state.json, dispatch-ledger.jsonl or
                         backlog-checkpoint.json, so a special file at one of those, or at an
                         enumerator operand, does not refuse the audit. The hook swallows a failed
                         barrier write (`except (OSError, ValueError) as exc` at
                         aiqt_hooks.py:33326-33332), so the doctor records the barrier
                         mtime and content BEFORE the audit and requires that the audit rewrote it:
                         the file must have changed and its ts must fall within this run. A barrier
                         the hook could not rewrite (for example one in a state directory the hook
                         cannot write; a read-only barrier file is replaced, not opened, by the
                         hook writer, aiqt_hooks.py:33229-33260) is reported as
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
                     (_orch_root -> _recovery_toplevel, aiqt_hooks.py:21723-21728).
  --session-id ID    preflight only: the session id used for holder-scoped lease checks
                     (holder_is_session_id at aiqt_hooks.py:22633-22644). Default: none.
  --stop-hook-active preflight only: preview an event whose stop_hook_active is true, which sets
                     the loop signal (aiqt_hooks.py:23468) and so, for the stop kind, the loop-bound
                     release ("loop_signal" at aiqt_hooks.py:23063-23066). Default: absent.
  --tool-stop        preflight idle only: preview a scheduling call whose tool_input stop is true,
                     which the hook judges as kind stop (aiqt_hooks.py:23692). Default: absent.
  --wake-text TEXT   preflight idle only: the text a scheduling call would carry (the hook joins
                     the string values of tool_input, aiqt_hooks.py:23693), used for the wake-hygiene
                     check (wake_named at aiqt_hooks.py:23461-23463) and to detect a quiet-duration
                     claim that is not previewed. Default: none.
  --tool NAME        preflight idle only: the scheduling tool whose call is previewed, matched
                     against yield_tools as the hook matches it. Default: ScheduleWakeup.

Exit status:
  preflight      0 when the effective verdict is ALLOW (including out of scope or out of roster),
                 1 when it is DENY or ALLOW_WITH_FINDINGS, 2 on a usage error, an unresolvable root,
                 an absent or unreadable registry, a registry file or a path the preview
                 checks (see above) that exists and is not a regular file, an idle verdict that
                 hangs on the quiet-claim check, which is not previewed, or a hook write that the
                 preview does not model.
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
race with another writer, or an effective uid that differs from the real one; and like the
special-file check it is a point-in-time lstat and stat, so a state directory or target changed
between the prediction and the hook write can change the outcome. The enumerator is a
program the registry declares; whatever it writes is outside the
control of this tool. The quiet-duration check is not previewed (see above). The rewrite check on
the barrier detects a write that did not happen; it cannot tell the hook from another writer that
rewrites the file inside the same run. The special-file check is a point-in-time os.stat: a path
replaced by a FIFO between the check and the hook open can still block. It covers, per command, the
registry files, the declared paths and the fixed state files that the hook call path opens, with a
blocking open or without blocking, and the enumerator operands, as listed above. It models every earlier exit that a stat or the registry content decides (an
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
# aiqt_hooks.py:23632 and :23638; a scheduling call that parks the run uses "schedule_idle", :23692,
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
    """A hook write that this preview does not model; the preview reports it as not previewed,
    exit 2."""


def _atomic_write_outcome(path, o_walk=None):
    """(outcome, reason) for _orch_write_json_atomic(path, obj) (aiqt_hooks.py:22207-22253, the save
    itself in _orch_write_json_at, :22256-22298), decided with lstat, stat and os.access only, so
    nothing is written. outcome is True when the write would succeed and False when it would fail
    (reason says why). It follows the steps of the hook: os.makedirs of the parent (:22243), which
    fails when the parent, or the nearest existing ancestor of an absent parent, is not a directory
    or cannot be written; the open of the parent directory (os.open at :22244, with O_PATH where it
    exists, else O_RDONLY, which also needs read permission on the parent); the lstat of the target
    through that descriptor (os.stat at :22262), which needs search permission on the parent and
    fails on any error other than an absent target; the create of a temporary file under a random
    name with O_CREAT|O_EXCL|O_NOFOLLOW (:22266-22267), which needs write and search permission on
    the parent and opens no existing file, so no entry at any fixed temporary-like name can block
    it, obstruct it or be followed; and os.replace onto the target (:22287), which fails when the
    target is a directory and replaces any other entry there (a read-only file or a symbolic link
    included) without opening it. The write therefore cannot block, and every outcome is decided here. o_walk
    is the flag the hook opens the parent with (hook._ORCH_O_WALK); None means O_PATH where the
    platform has it. os.access is an approximation (see Residuals)."""
    parent = os.path.dirname(path)
    if os.path.lexists(parent) and not os.path.isdir(parent):
        return False, ("{} exists but is not a directory, so os.makedirs raises "
                       "(aiqt_hooks.py:22243)".format(parent))
    if not os.path.isdir(parent):
        # os.makedirs would create it under the nearest existing ancestor, and then the temporary
        # file and the replace land in a new empty directory this process created.
        ancestor = os.path.dirname(parent)
        while ancestor and not os.path.lexists(ancestor) and ancestor != os.path.dirname(ancestor):
            ancestor = os.path.dirname(ancestor)
        if not os.path.isdir(ancestor) or not os.access(ancestor, os.W_OK | os.X_OK):
            return False, ("{} is absent and cannot be created under {} "
                           "(os.makedirs at aiqt_hooks.py:22243)".format(parent, ancestor))
        return True, None
    if o_walk is None:
        o_walk = getattr(os, "O_PATH", os.O_RDONLY)
    if o_walk == os.O_RDONLY and not os.access(parent, os.R_OK):
        return False, ("{} is not readable, and the hook opens it with O_RDONLY where O_PATH is "
                       "absent (os.open at aiqt_hooks.py:22244)".format(parent))
    if not os.access(parent, os.X_OK):
        return False, ("{} is not searchable, so the lstat of the target raises "
                       "(os.stat at aiqt_hooks.py:22262)".format(parent))
    try:
        target = os.lstat(path)
    except FileNotFoundError:
        target = None
    except OSError as exc:
        return False, ("{} cannot be examined ({}), so the lstat of the target raises "
                       "(os.stat at aiqt_hooks.py:22262)".format(path, exc))
    if not os.access(parent, os.W_OK):
        return False, ("{} is not writable, so the temporary file cannot be created in it "
                       "(os.open at aiqt_hooks.py:22266-22267)".format(parent))
    if target is not None and stat.S_ISDIR(target.st_mode):
        return False, ("{} is a directory, so the replace onto it raises "
                       "(os.replace at aiqt_hooks.py:22287)".format(path))
    return True, None


def _build_ctx_previewed(hook, reg, root, kind, data, wake_text):
    """(ctx, notes): the context exactly as the hook builds it, _orch_build_ctx with
    record_checkpoint=True (aiqt_hooks.py:23412), with hook._orch_write_json_atomic and
    hook._orch_guard_event replaced for this call only by stand-ins that write nothing. The
    stand-in write returns what the hook writer returns for the outcome _atomic_write_outcome
    predicts (None on success, else a short failure detail, aiqt_hooks.py:22207-22212) for the
    checkpoint rewrite (:23376) and the init-marker write (:23392), so the hook code itself decides
    whether the marker write is reached (os.path.lexists at :23387), whether it injects the
    cannot-evaluate row (injected.append at :23397) and which recording-failure warnings it adds to
    ctx["record_warn"]; notes lists the predicted writes. Raises _Unpreviewed for a write the
    preview does not model."""
    sd = hook._orch_state_dir_for_root(root)
    checkpoint = os.path.join(sd, "backlog-checkpoint.json")
    marker = os.path.join(sd, "checkpoint-init.marker")
    o_walk = getattr(hook, "_ORCH_O_WALK", None)
    notes = []

    def write(path, _obj):
        if path not in (checkpoint, marker):
            raise _Unpreviewed("the hook would write {}, a write this preview does not model"
                               .format(path))
        outcome, reason = _atomic_write_outcome(path, o_walk)
        if path == checkpoint:  # the checkpoint rewrite, the first _orch_write_json_atomic call
            notes.append("checkpoint rewrite (aiqt_hooks.py:23376): {}".format(
                "would succeed" if outcome else "would FAIL ({}); the hook then skips the "
                "init-marker write (os.path.lexists at aiqt_hooks.py:23387) and adds a "
                "recording-failure warning".format(reason)))
        else:  # the init-marker write, the second _orch_write_json_atomic call of the union
            notes.append("init-marker write (aiqt_hooks.py:23392): {}".format(
                "would succeed" if outcome else "would FAIL ({}); the hook then injects a "
                "cannot-evaluate row (injected.append at aiqt_hooks.py:23397)".format(reason)))
        # The hook writer returns None on success, else a failure detail
        # (_orch_write_json_atomic at aiqt_hooks.py:22211-22212).
        return None if outcome else "predicted failure: {}".format(reason)

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


def _counter_save_blocker(state_dir, o_walk=None):
    """None when the hook could plausibly save the denial counter, else the reason it could not.
    The hook saves it through _orch_save_turn_state (aiqt_hooks.py:22353-22362), which writes
    turn-state.json through _orch_write_json_atomic, so the outcome is the one
    _atomic_write_outcome predicts for that path: the state directory decides it, and a read-only
    turn-state.json is replaced, not opened. It uses lstat and os.access only, so it writes nothing.
    os.access is an approximation (see Residuals)."""
    ok, reason = _atomic_write_outcome(os.path.join(state_dir, "turn-state.json"), o_walk)
    return None if ok else reason


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
    """The registry files _orch_registry (aiqt_hooks.py:22084-22121) opens, in the order of
    _ORCH_REGISTRY_FILES (21652). A file is opened (os.open at 22098) only when its lstat succeeds
    (os.lstat at 22087), and the loop moves on to the next file only when that lstat raised
    FileNotFoundError (22088-22089): a present file returns at 22096-22121 (os.open) whatever its
    content, and an lstat fault returns bad at 22090-22095 (`except OSError as exc`), so no later
    registry file is reached."""
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
    """The first registry file the hook would open that is present but not a regular file, as the
    refusal that _first_special words, or None."""
    return _first_special(_registry_read_paths(hook, root))


def _section(reg, key):
    """The registry section key when it is an object, else an empty dict (as the hook reads it)."""
    value = reg.get(key)
    return value if isinstance(value, dict) else {}


def _state_path(hook, root, name):
    """A fixed hook state file under the state directory, resolved exactly as every hook reader
    resolves it (_orch_state_dir_for_root, aiqt_hooks.py:22149-22154)."""
    return os.path.join(hook._orch_state_dir_for_root(root), name)


def _lease_fresh_states(hook, lease, st):
    """The freshness values the hook can compute for this lease (aiqt_hooks.py:22618-22630): {True}
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
    """The paths _orch_scope_live(reg, root, session_id) (aiqt_hooks.py:22596-22656) opens, each only
    when the hook reaches that open:
      lease.path  opened with a plain blocking open at 22639-22641 only when the lease section is a
                  non-empty object (22611-22613),
                  its path resolves (_orch_path at 22614-22615), os.stat succeeds (22617), the lease
                  is non-empty and fresh (_orch_lease_age_class at 22618-22632),
                  holder_is_session_id is set (22633) and the session id is a non-empty string
                  (22637-22638; otherwise the hook returns False unopened).
      mode.path   opened by _orch_mode_read at 22444-22457, which _orch_mode reaches through
                  _orch_mode_detail, via 22654 unless the hook returned first: a live lease returns
                  (st.st_size at 22632-22644), and a lease os.stat cannot reach returns False in
                  holder mode (holder_is_session_id at 22649-22652). A stat that succeeds on a
                  stale or empty lease, or a failed stat without holder mode, falls through to the
                  mode read. _orch_mode_read opens the path with O_NONBLOCK (22445-22446), so a FIFO
                  there does not block it, and it reads a file that is not regular as unattended,
                  fail-closed (22453-22454); the doctor does not model that reader and refuses a
                  special file there as it does at a blocking open, with a message that says so
                  (SITE_OPEN).
    The lease is never opened otherwise (the os.stat at 22617 does not block), so a FIFO there, whose
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
    """True when _orch_enumerate (aiqt_hooks.py:22815-22848) reaches the subprocess at 22833: the
    enumerator is an object (22820-22823) whose argv is a non-empty list of non-empty strings
    (22827-22829). Otherwise it returns NO_ENUMERATOR or ENUMERATOR_ERROR unrun, and _orch_build_ctx
    skips every reader after the enumeration (23433)."""
    spec = reg.get("enumerator")
    if not isinstance(spec, dict):
        return False
    argv = spec.get("argv")
    return isinstance(argv, list) and bool(argv) and all(isinstance(a, str) and a for a in argv)


def _ctx_read_paths(hook, reg, root):
    """The paths _orch_build_ctx (aiqt_hooks.py:23412-23475) opens for reading, traced through every
    reader it calls, each only when the call reaches it. Each is opened with a plain blocking open,
    except record.pending_decisions and attestations.anchor, which the hook opens without blocking,
    and the enumerator operands, which the enumerator opens, not the hook (SITE_OPEN):
      turn-state.json              _orch_turn_state, lexists then open at 22344-22346 (via 23420), always
      enumerator argv[2] on        opened by the enumerator, run with cwd = the root (22833, via 23431),
                                   only when the enumerator runs (_enumerator_runs)
      dispatch-ledger.jsonl        _orch_live_ledger_ids 22857-22858, opened at 22173 (via 23434)
      record.pending_decisions     _orch_pending_haystack, opened at 22905-22908 (via 23436)
      attestations-validated.json  _orch_attestation_refs, opened at 22933-22935 (via 23437), when
                                   attestations is declared (22929-22931)
      attestations                 _orch_register_authority 32921 (via 22947) and _orch_chained_rows
                                   32876 (via 22954), only when os.stat succeeds on the snapshot
                                   (a failed snapshot open takes `return "unreadable"` at 22936-22937)
      attestations.anchor          _orch_register_authority 32968, and guard-events.jsonl
      guard-events.jsonl           (_orch_pointer_resolves 33020, opened at 22173, via 22957 and 33070),
                                   only when os.stat succeeds on the register too (a failed register
                                   open takes `return ("hold"` at 32923-32924, returned at
                                   22948-22950 (`astatus != "ok"`))
      backlog-checkpoint.json      _orch_checkpoint_union, lexists then open at 23321-23324 (via 23442)
    Every reader after the enumeration runs only on a successful enumeration (`status == "ok"` at
    23433); the doctor models the part a registry read decides (_enumerator_runs) and checks the rest
    whenever the enumerator runs, since only running it decides whether it succeeds. Not modelled, so
    checked conservatively: the snapshot content (22937-22945), whether git tracks the register
    (`ls-files` at 32930-32961), and a guard-events pointer in a register row (pointer.startswith at
    33018). Not checked here: the checkpoint-init marker (read by os.path.lexists at 23335 and 23387
    only, never opened) and the escape sentinel (opened non-blocking by os.open at 22670-22671, via
    _orch_escape_active at 23465, and judged on the open descriptor). The writes
    (_orch_write_json_atomic at 23372-23399) are modelled by _build_ctx_previewed and
    _atomic_write_outcome instead."""
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
    open at 22173 raises and returns ([], 0) or (None, 0) (22175-22178), or the file is empty, so
    there are no lines; either way _orch_forced_exit_findings returns at 33161-33169 before the
    surfaced set. A non-empty file may still hold no rows, which only reading it decides, so it
    counts as possibly having rows."""
    try:
        return os.stat(log).st_size != 0
    except OSError:
        return False


def _audit_read_paths(hook, reg, root):
    """The paths orch_resume_audit (aiqt_hooks.py:33270-33354) opens on a readable registry, traced
    through _orch_resume_probes (32738-32822) and every reader it calls, each only when the audit
    reaches it. Each is opened with a plain blocking open, except record.handoff, record.findings,
    record.pending_decisions and attestations.anchor, which the hook opens without blocking
    (SITE_OPEN):
      record.handoff                  opened at 32760-32768, when declared
      record.findings                 opened at 32790, and at 32837-32842 (via 32819), when declared
      record.pending_decisions        opened at 32790, when declared
      attestations                    _orch_chained_rows 32876 (via 33096) and _orch_register_authority
                                      32921 (via 33097), when declared (at_path at 33092-33094)
      attestations.anchor             _orch_register_authority 32968, only when os.stat succeeds
                                      on the register (a failed register open takes
                                      `return ("hold"` at 32923-32924)
      mistakes_register               _orch_chained_rows 32875-32877 (via 33132-33134), when declared
      guard-events.jsonl              read by _orch_pointer_resolves at 33020 (via 33111 and 33144),
                                      opened by _orch_read_jsonl at 22173; appended by _orch_guard_event
                                      at 22162 (via 33334); both depend on file content, so always
                                      checked
      escape-spoof.json               lexists then open at 33211-33212 (via
                                      _orch_pending_artefact_findings at 32821)
      forced-exit.jsonl               _orch_forced_exit_findings 33159-33160, opened at 22173
      forced-exit-surfaced.json       opened at 33171-33172, only when the log may hold rows
                                      (_forced_exit_may_have_rows; no rows return at 33168-33169)
    The hook's rewrites of the attestation snapshot (via 33124) and of the surfaced set (via 33191)
    go through _orch_write_json_atomic, which opens a new random name, <name>.<16 hex>.tmp, with
    O_EXCL at 22266-22267 and so opens no existing entry; neither old fixed path
    (attestations-validated.json.tmp, forced-exit-surfaced.json.tmp) is checked.
    resume-barrier.json (written at 33324) is read before the audit by _barrier_snapshot, which
    refuses a special file there. The audit runs no enumerator and does not open the lease (os.stat
    only, 32800), the mode record, turn-state.json, dispatch-ledger.jsonl or backlog-checkpoint.json,
    so none of those is checked here. Not modelled, so checked conservatively: whether git tracks the
    register (`ls-files` at 32930-32961), the rows and pointers a register holds (pointer.startswith
    at 33018, _orch_attestation_derive at 33111, _orch_pointer_resolves at 33144), the rows the
    forced-exit log and the surfaced set hold (_orch_forced_exit_findings at 33161-33188), and
    whether there are findings to record (`if findings` at 33333-33334)."""
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
    return out


def _audit_bad_registry_paths(hook, root):
    """On an unreadable registry the audit opens only resume-barrier.json.unused (appended by
    _orch_append_jsonl at 22162, via 33317) and guard-events.jsonl (appended by _orch_append_jsonl
    at 22162, via _orch_event_warn at 33334, since the unreadable registry is itself a finding,
    _orch_resume_audit_findings at 33321), beside the barrier, under the state directory the hook
    resolves for that registry (_orch_state_dir_for_root at aiqt_hooks.py:33315). Both are always
    reached."""
    return [_site("audit_bad.unused", "hook state file resume-barrier.json.unused",
                  _state_path(hook, root, "resume-barrier.json.unused")),
            _site("audit_bad.guard_events", "hook state file guard-events.jsonl",
                  _state_path(hook, root, "guard-events.jsonl"))]


# How the hook opens the path of a pre-check site, where that is not a plain blocking open; every other
# site is opened with one. tools/test-orch-stage2-hooks.py holds each site to the hook reader and line
# that open its path (PRECHECK_OPENS, also by a run of the hook), holds each text here to an exact
# expected text whose every cited hook line it checks at source (OPEN_ACCOUNTS), and checks the whole
# refusal in every case in which the doctor refuses a special file.
_RECORD_SURFACE_OPEN = ("the hook would not block on it: _orch_record_surface_read opens the path with "
                        "O_NONBLOCK (aiqt_hooks.py:32703-32704) and returns no data for a file that is "
                        "not regular, without a read (32709-32710, 32725-32726), but the doctor refuses "
                        "it without calling that reader")
_ANCHOR_OPEN = ("the hook would not block on it: _orch_register_authority opens the path with O_NONBLOCK "
                "and O_NOFOLLOW (aiqt_hooks.py:32968-32969) and holds on a file that is not regular "
                "(32975-32976) or a symlink (32971-32972), but the doctor refuses it without calling "
                "that reader")
SITE_OPEN = {
    "registry.file": ("the hook would not block on it: _orch_registry opens the path with O_NONBLOCK "
                      "(aiqt_hooks.py:22096-22098) and reads a file that is not regular as a bad registry "
                      "(22102-22103), but the doctor refuses it without calling that reader"),
    "scope.mode": ("the hook's mode reader would not block on it: _orch_mode_read opens the path with "
                   "O_NONBLOCK (aiqt_hooks.py:22445-22446) and gives a file that is not regular the "
                   "status bad, without a read (22453-22454), which _orch_mode_detail takes as "
                   "unattended, fail-closed (22529-22530), but the doctor does not model that reader"),
    "ctx.enumerator_operand": ("the hook does not open it: the declared enumerator, which the hook runs "
                               "(subprocess.run at aiqt_hooks.py:22833), takes it as an operand, and the "
                               "doctor does not model how that program opens it"),
    "ctx.pending_decisions": _RECORD_SURFACE_OPEN,
    "ctx.attestations_anchor": _ANCHOR_OPEN,
    "audit.handoff": _RECORD_SURFACE_OPEN,
    "audit.findings": _RECORD_SURFACE_OPEN,
    "audit.pending_decisions": _RECORD_SURFACE_OPEN,
    "audit.attestations_anchor": _ANCHOR_OPEN,
}
BLOCKING_OPEN = "the hook would open it with a blocking open"
# What the refusal says was not run: the hook reader that opens the path, and any enumerator. No hook
# reader opens an enumerator operand, so its refusal names the enumerator alone.
REFUSAL_END = "so the hook reader that opens it was not called and no enumerator ran"
SITE_END = {
    "ctx.enumerator_operand": "so no enumerator ran",
}


def _first_special(entries):
    """The first _site entry whose path is present but not a regular file, as a _special_path
    message followed by how the hook opens that path (SITE_OPEN, else BLOCKING_OPEN) and what was
    not run (SITE_END, else REFUSAL_END), or None. An entry with no path (an undeclared key) is
    skipped."""
    for site_id, label, path in entries:
        if not path:
            continue
        found = _special_path(label, path)
        if found is not None:
            return "{}; {}, {}".format(found, SITE_OPEN.get(site_id, BLOCKING_OPEN),
                                       SITE_END.get(site_id, REFUSAL_END))
    return None


def _refuse_special(found):
    """Report the refusal _first_special words for a special file at a pre-check site, as
    cannot-evaluate, exit 2."""
    print("cannot evaluate: {}".format(found))
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
    (aiqt_hooks.py:21723-21728). A flag that is off leaves its field absent, which the hook reads
    exactly as any value other than true (its tests are "is True", aiqt_hooks.py:23468 and 23692)."""
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
              "(aiqt_hooks.py:23572-23576); a scheduling call is denied "
              "(_deny at aiqt_hooks.py:23676-23683)")
        return 2
    print("registry: ok")
    # The session id exactly as both handlers read it: "session_id" at aiqt_hooks.py:23577 for a
    # Stop and "session_id" at 23684 for a scheduling call.
    session_id = data.get("session_id")
    special = _first_special(_scope_read_paths(hook, reg, root, session_id))
    if special is not None:
        # _orch_scope_live opens the lease with a plain blocking open, so a FIFO there would hang the
        # preview; its mode reader would not block, but a special file there is refused too (see
        # _scope_read_paths). The scope reader is not called.
        return _refuse_special(special)
    scope_live = hook._orch_scope_live(reg, root, session_id)
    print("scope: {}".format("live" if scope_live else
                             "not live (the hook allows without judging)"))
    if not scope_live:
        # The hook returns here, before the context is built or the enumerator runs
        # (_orch_scope_live at aiqt_hooks.py:23577-23579 for a Stop, _orch_scope_live at
        # :23684-23686 for a scheduling call), so neither does the preview: an enumerator run here
        # could change what a later Stop decides.
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
        # (aiqt_hooks.py:23687-23690).
        in_roster = isinstance(declared, list) and tool in declared
        if isinstance(declared, list):
            print("yield_tools roster: {}".format(", ".join(str(t) for t in declared) or "(empty)"))
        else:
            print("yield_tools roster: not a declared list")
        print("tool {}: {}".format(tool, "in the roster, judged" if in_roster else
                                   "not in the roster; the hook allows it unjudged "
                                   "(aiqt_hooks.py:23687-23690)"))
        if not in_roster:
            # The hook returns here too, before the context or the enumeration
            # (_allow at aiqt_hooks.py:23690).
            print("enumeration: not run (out of the roster, the hook allows before it enumerates)")
            print("writes: the doctor itself wrote nothing, and no enumerator ran")
            print("effective verdict: ALLOW (out of the roster)")
            return 0
        # Exactly the hook derivation of the kind and the wake text from the event
        # (tool_input at aiqt_hooks.py:23691-23693).
        tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        kind = "stop" if tool_input.get("stop") is True else "schedule_idle"
        wake_text = " ".join(str(v) for v in tool_input.values() if isinstance(v, str))
        print("judged kind: {}".format(
            "stop (tool_input stop is true, aiqt_hooks.py:23692)" if kind == "stop"
            else "schedule_idle (aiqt_hooks.py:23692)"))
        if kind != "schedule_idle":
            print("quiet-claim check: not applicable; the hook runs it only for the schedule_idle "
                  "kind (aiqt_hooks.py:23709)")
        else:
            quiet_claim = (bool(hook._ORCH_QUIET_CLAIM_RE.search(wake_text))
                           and "quiet" in wake_text.lower())
            if quiet_claim:
                print("quiet-claim check: NOT PREVIEWED; the wake text carries a quiet-duration "
                      "claim, which the hook judges inline against the measured gap since the last "
                      "human input before the verdict below "
                      "(_ORCH_QUIET_CLAIM_RE at aiqt_hooks.py:23703-23722); it cannot be called "
                      "without writing a guard event")
            else:
                print("quiet-claim check: not previewed "
                      "(_ORCH_QUIET_CLAIM_RE at aiqt_hooks.py:23703-23722); the wake text carries no "
                      "quiet-duration claim, so the check does not fire")
    special = _first_special(_ctx_read_paths(hook, reg, root))
    if special is not None:
        # _orch_build_ctx opens most of these with a plain blocking open (see _ctx_read_paths), so a
        # FIFO there would hang the preview; a special file at any of them is refused, the context
        # is not built and no enumerator runs.
        return _refuse_special(special)
    # The context as each handler builds it: a Stop passes no wake text (_orch_build_ctx at
    # aiqt_hooks.py:23580), a scheduling call the joined tool_input text (:23694); both pass the
    # event data, whose stop_hook_active sets the loop signal (:23468).
    try:
        ctx, notes = _build_ctx_previewed(hook, reg, root, kind, data, wake_text)
    except _Unpreviewed as exc:
        print("writes: the doctor itself wrote nothing; the registry enumerator ran as the hook runs "
              "it (_orch_enumerate at aiqt_hooks.py:22815-22848), and anything that program writes "
              "is its own")
        print("hook write: NOT PREVIEWED; {}".format(exc))
        print("effective verdict: UNPREVIEWED (the verdict depends on a hook write that cannot be "
              "decided without writing)")
        return 2
    if ctx["enum_status"] == "ok":
        print("enumeration: ok")
    else:
        print("enumeration: {}: {}".format(ctx["enum_status"], ctx["enum_detail"]))
    print("writes: the doctor itself wrote nothing; the registry enumerator ran as the hook runs it "
          "(_orch_enumerate at aiqt_hooks.py:22815-22848), and anything that program writes is its "
          "own")
    if ctx["enum_status"] != "ok":
        print("checkpoint writes: none; the hook reaches the checkpoint union only after a "
              "successful enumeration (_orch_build_ctx at aiqt_hooks.py:23433)")
    for note in notes:
        print("predicted hook write, not made: {}".format(note))
    if ctx["enum_status"] == "ok" and not any(n.startswith("init-marker") for n in notes):
        # The init-marker write is the second _orch_write_json_atomic call of the union.
        print("predicted hook write, not made: init-marker write (aiqt_hooks.py:23392): not "
              "reached (the marker exists, or the checkpoint rewrite would fail)")
    print("loop signal: {}".format("set (stop_hook_active is true, aiqt_hooks.py:23468)"
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
    o_walk = getattr(hook, "_ORCH_O_WALK", None)
    blocker = _counter_save_blocker(hook._orch_state_dir_for_root(root), o_walk)
    if kind_name == "stop":
        if blocker is None:
            print("denial counter: could be saved (an os.access check; the hook saves it on a DENY)")
        else:
            print("denial counter: could NOT be saved ({}; an os.access check)".format(blocker))
            if effective == "DENY":
                # _orch_record_denial at aiqt_hooks.py:23591-23597: an unsaved counter never
                # reaches the loop bound, so the Stop fails open with a warning rather than
                # re-denying.
                print("effective verdict: ALLOW_WITH_FINDINGS (the fail-open allow the hook gives "
                      "when the denial counter cannot be saved, "
                      "_orch_record_denial at aiqt_hooks.py:23591-23597; the "
                      "judged DENY would not hold. Underlying: {})".format(reason))
                _print_disposition(disposition)
                return 1
    else:
        print("denial counter: not checked; a scheduling DENY stands whether or not the counter "
              "is saved (_orch_record_denial at aiqt_hooks.py:23730-23747)")
    # The hook adds a recording-failure warning to an allow when a checkpoint write fails
    # (ctx["record_warn"], aiqt_hooks.py:23442, surfaced at :23621-23624 for a Stop and :23775-23779
    # for a scheduling call), and, for an allowed schedule_idle call, when the wake digest cannot be
    # saved to turn-state.json (_orch_register_wake, :23641-23663); the ALLOW stands, with that
    # warning as a finding.
    record_warn = list(ctx.get("record_warn") or [])
    if kind == "schedule_idle" and effective != "DENY" and blocker is not None:
        record_warn.append("the wake digest could not be saved to turn-state.json ({})"
                           .format(blocker))
    if quiet_claim and effective != "DENY":
        # The quiet-claim check runs before decide_yield and may deny; a DENY stands either way.
        print("effective verdict: UNPREVIEWED ({} unless the quiet-claim check denies)"
              .format(effective))
        _print_disposition(disposition)
        return 2
    if effective == "ALLOW" and record_warn:
        print("recording failures the hook would report: {}".format(" ".join(record_warn)))
        print("effective verdict: ALLOW_WITH_FINDINGS (the ALLOW stands, and the hook reports the "
              "recording failures above with it)")
        _print_disposition(disposition)
        return 1
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
    # The audit opens most of these with a plain blocking open (see _audit_read_paths), so a FIFO
    # there would hang it; a special file at any of them is refused, and the audit is not run.
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
              "the run); the hook could not replace it (for example its state directory cannot be "
              "written), so the "
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
        # A Stop event carries no tool_input (_orch_build_ctx at aiqt_hooks.py:23580 passes no
        # wake text), so an input the previewed handler never reads is refused rather than
        # silently ignored.
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
