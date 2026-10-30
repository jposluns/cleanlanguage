#!/usr/bin/env python3
"""Project-owned operator tool for the AIQT orchestration hooks (item 28.2 stage 2, PR1-f).

The vendored hook names this file in two banners (aiqt_hooks.py:orch_resume_audit and aiqt_hooks.py:orch_resume_barrier, "python3
tools/orch_doctor.py --resume-audit"). The pack ships its own orch_doctor.py, but that copy imports
symbols absent from the hook vendored here, so this repository carries its own. It imports the
VENDORED hook by path and reuses its functions, so it never reimplements a decision:

  preflight [stop|idle]  Preview what a Stop (stop) or a scheduling call (idle) would decide now. It
                         follows the hook order exactly: registry, then scope (aiqt_hooks.py:_orch_stop_family
                         for a Stop, aiqt_hooks.py:orch_yield_tool for a scheduling call), then for idle the roster test
                         (aiqt_hooks.py:orch_yield_tool), and only then the context and the enumeration (aiqt_hooks.py:_orch_stop_family, aiqt_hooks.py:orch_yield_tool).
                         Out of scope, or for idle out of the roster, it reports the ALLOW the hook
                         gives there WITHOUT building the context or running the enumerator, since
                         the hook does neither, and an enumerator the preview ran could change what
                         a later Stop decides. In scope it
                         calls _orch_build_ctx(reg, root, kind, data, record_checkpoint=True)
                         (aiqt_hooks.py:_orch_build_ctx), the posture of the hook itself, with the two write
                         primitives that call reaches replaced, for that call only, by stand-ins
                         that write nothing (the checkpoint writes, below), and decide_yield
                         (aiqt_hooks.py:decide_yield), then prints
                         the verdict, the reason, the disposition table, and the verdict with the
                         escape sentinel forced off, so the operator sees what the Stop would do
                         without the sentinel. Where the scope test answers cannot-evaluate (a
                         declared lease max_age_hours horizon that is not usable, aiqt_hooks.py:_orch_scope_live
                         `return "cannot" if cannot else False`), the doctor adds to the context the same
                         cannot-evaluate row the hook adds before it decides (aiqt_hooks.py:_orch_stop_family
                         `if scope == "cannot":`, aiqt_hooks.py:orch_yield_tool `if scope == "cannot":`), so the preview
                         judges the same input. A Stop DENY holds only when the hook can save the
                         denial counter to turn-state.json; when it cannot, the hook fails open with
                         a warning instead (aiqt_hooks.py:_orch_stop_family `failing OPEN with findings rather than re-denying`).
                         The save goes through _orch_write_json_atomic (aiqt_hooks.py:_orch_save_turn_state): a
                         temporary file created in the state directory, then replaced onto turn-state.json
                         (aiqt_hooks.py:_orch_write_json_at), so it needs a state directory that can be created, or
                         written and searched, and never a writable turn-state.json. The doctor therefore
                         checks, with os.access and without writing, whether that save could succeed,
                         and for a state directory that does not exist yet it also models the
                         permission bits os.makedirs gives the directories it creates
                         (_created_dir_owner_bits): the process umask applied to mode 0o777, or,
                         under a nearest existing ancestor that carries a default ACL, the owner
                         entry of that ACL, which replaces the umask; without write and search
                         permission for the owner the save fails, as under umask 0o777 (the umask is
                         read by setting it and restoring it at once, which changes no file). When
                         it could not succeed it reports the fail-open
                         ALLOW_WITH_FINDINGS the hook would give, with the reason. A scheduling DENY
                         stands whether or not the counter is saved (aiqt_hooks.py:orch_yield_tool), so
                         the check applies to stop only.
                         The checkpoint writes: the checkpoint union
                         (_orch_checkpoint_union, aiqt_hooks.py:_orch_checkpoint_union, via
                         aiqt_hooks.py:_orch_build_ctx `_orch_checkpoint_union(root, payload,`) makes the
                         only other hook writes inside _orch_build_ctx and its callees: guard
                         events (aiqt_hooks.py:_orch_checkpoint_union `warn = _orch_event_warn(root, ev_kind,`,
                         through aiqt_hooks.py:_orch_event_warn),
                         whose failure adds only a recording-failure warning; the checkpoint
                         rewrite (aiqt_hooks.py:_orch_checkpoint_union `unsaved = _orch_write_json_atomic(path,`),
                         whose failure changes no verdict by itself (the hook adds a warning to its
                         output) but skips the marker write; and, only when that rewrite succeeds
                         and no init marker exists (aiqt_hooks.py:_orch_checkpoint_union
                         `elif not os.path.lexists(marker):`), the init-marker write, whose failure
                         injects a cannot-evaluate row (aiqt_hooks.py:_orch_checkpoint_union
                         `checkpoint-init marker unwritable; a later deletion would go`), so that a Stop
                         the hook would otherwise allow is denied. Both writes go through
                         _orch_write_json_atomic (aiqt_hooks.py:_orch_write_json_atomic
                         `os.makedirs(directory, exist_ok=True)`: os.makedirs of the state directory,
                         an open of that directory, then a temporary file under a random name
                         created with O_EXCL and O_NOFOLLOW and replaced onto the target,
                         aiqt_hooks.py:_orch_write_json_at `os.replace(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)`).
                         Its stand-in decides each outcome with lstat and os.access only
                         (_atomic_write_outcome), without writing, and returns it to the hook code
                         as the hook writer would (None on success, else a failure detail), so the
                         hook itself decides whether the marker write is reached and what it
                         injects; the stand-in for _orch_guard_event writes nothing and reports
                         success. The predicted outcome of each write is printed. The temporary
                         file is created under a fresh random name, exclusively and without
                         following a symbolic link, so no file already present at a temporary path
                         can block the write or redirect it, and each outcome is decided by the
                         state directory and the target alone. A write to any other path, which
                         this preview does not model, is reported as not previewed, exit 2. The
                         doctor itself WRITES NOTHING: no
                         checkpoint, no init marker, no guard event, no turn-state, no spoof record,
                         and no bytecode cache. It does run the enumerator the registry declares,
                         exactly as the hook runs it (_orch_enumerate, aiqt_hooks.py:_orch_enumerate: the
                         declared argv as a subprocess with cwd = the root, no shell). That program
                         is outside this tool, and anything it writes is its own, not the doctor's;
                         the output says so.
                         For idle, roster membership is modelled exactly as the hook tests it
                         (aiqt_hooks.py:orch_yield_tool): a tool outside a list-valued yield_tools roster,
                         or any tool when yield_tools is not a list, is allowed unjudged. The
                         quiet-duration check (aiqt_hooks.py:orch_yield_tool) runs inline in the hook before
                         the verdict and writes a guard event, so it cannot be called without
                         writing and is NOT previewed: when the wake text carries a quiet-duration
                         claim (the hook regex _ORCH_QUIET_CLAIM_RE plus the word "quiet"), a verdict
                         other than DENY is reported as unpreviewed, exit 2.
                         The event fields: the previewed handler (orch_stop_guard through
                         _orch_stop_family, aiqt_hooks.py:_orch_stop_family, for stop;
                         orch_yield_tool, aiqt_hooks.py:orch_yield_tool, for idle), traced into
                         _orch_root and _orch_build_ctx, reads these fields of the event, and the
                         doctor passes each exactly as the hook reads it, from one input
                         (_event_data):
                           data cwd               _orch_root                         --root
                           data session_id        _orch_stop_family, orch_yield_tool --session-id
                           data stop_hook_active  _orch_build_ctx                    --stop-hook-active (true only)
                           data tool_name         orch_yield_tool                    --tool (idle)
                           data tool_input        orch_yield_tool                    built from the two inputs below
                           tool_input stop        orch_yield_tool                    --tool-stop (true only, idle)
                           tool_input values      orch_yield_tool                    --wake-text, as tool_input prompt
                           tool_input prompt      orch_yield_tool                    not previewed (see below)
                         The hook tests stop_hook_active and stop with "is True", so an absent
                         field stands for every other value. With --tool-stop the scheduling call
                         is judged as kind stop, as the hook judges it (aiqt_hooks.py:orch_yield_tool
                         `kind = "stop" if tool_input.get(`): the loop signal and the stop counter
                         apply, the quiet-claim check does not (aiqt_hooks.py:orch_yield_tool
                         `if kind == "schedule_idle" and claim and`), and the denial-counter check
                         does not, since a scheduling DENY stands (aiqt_hooks.py:orch_yield_tool
                         `unsaved = _orch_record_denial(root, ts, kind, basis)`). tool_input prompt is
                         read only after an allowed schedule verdict, for the wake-digest write
                         (aiqt_hooks.py:orch_yield_tool `wake_warn = _orch_register_wake(root, ts,`,
                         _orch_register_wake, aiqt_hooks.py:_orch_register_wake); it never changes the
                         verdict, so it needs no input. The test
                         suite scans the hook source for every event field these paths read and
                         holds each to a reviewed table, so a new field fails the suite.
                         Before each hook reader is called, the doctor checks every path that
                         reader would open with a plain blocking open, each resolved as the hook
                         resolves it (_orch_path, aiqt_hooks.py:_orch_path; the state directory by
                         _orch_state_dir_for_root, aiqt_hooks.py:_orch_state_dir_for_root), and a path is checked only when
                         the hook call path would reach its open, each earlier exit the hook takes
                         modelled from its source. The registry files are not
                         checked: _orch_registry opens each one non-blocking and checks its type on the
                         open descriptor (aiqt_hooks.py:_orch_registry `flags = os.O_RDONLY | os.O_NONBLOCK`,
                         aiqt_hooks.py:_orch_registry `return ("bad", "{}: not a regular file".format(rel))`), so a
                         special file there reads as an unreadable registry at once, which the doctor
                         reports from the hook reader itself (exit 2). Before the scope test
                         (_orch_scope_live, aiqt_hooks.py:_orch_scope_live) it checks lease.path only when the hook
                         would open the lease for holder scoping (aiqt_hooks.py:_orch_scope_live `with open(path,`): the
                         stat succeeds (aiqt_hooks.py:_orch_scope_live `st = os.stat(path)`), the lease is non-empty and
                         fresh or its declared horizon cannot be evaluated, classified by the hook
                         classifier itself (aiqt_hooks.py:_orch_lease_age_class, aiqt_hooks.py:_orch_scope_live
                         `if st.st_size > 0 and (fresh or cannot):`), holder_is_session_id is set and a session id is
                         given (aiqt_hooks.py:_orch_scope_live `if not (isinstance(session_id, str) and session_id):`).
                         The mode record is not checked: _orch_mode_read opens it non-blocking and reads
                         a file that is not a regular file as a bad record, which fails closed to the
                         guards-armed posture (aiqt_hooks.py:_orch_mode_read `result = ("bad", "the mode file is not a regular file")`,
                         aiqt_hooks.py:_orch_mode_detail `return (_ORCH_MODE_ARMED, text)`), so a special file there cannot
                         block the preview. Before the context is built (_orch_build_ctx, aiqt_hooks.py:_orch_build_ctx) it
                         checks turn-state.json (aiqt_hooks.py:_orch_turn_state, via aiqt_hooks.py:_orch_build_ctx) and then, only when the
                         enumerator would run (a dict with a non-empty argv of non-empty strings,
                         aiqt_hooks.py:_orch_enumerate), the enumerator argv from argv[2] on (run with cwd = the root,
                         aiqt_hooks.py:_orch_enumerate) and the paths read after a successful enumeration (aiqt_hooks.py:_orch_build_ctx):
                         dispatch-ledger.jsonl (aiqt_hooks.py:_orch_live_ledger_ids, opened at aiqt_hooks.py:_orch_read_jsonl), record.pending_decisions
                         (aiqt_hooks.py:_orch_pending_haystack), backlog-checkpoint.json (aiqt_hooks.py:_orch_checkpoint_union) and, when attestations is
                         declared (aiqt_hooks.py:_orch_attestation_refs), attestations-validated.json (aiqt_hooks.py:_orch_attestation_refs); the register
                         (aiqt_hooks.py:_orch_register_authority via aiqt_hooks.py:_orch_attestation_refs, aiqt_hooks.py:_orch_chained_rows via aiqt_hooks.py:_orch_attestation_refs) only when os.stat succeeds on that
                         snapshot (a failed snapshot open returns at aiqt_hooks.py:_orch_attestation_refs), and
                         guard-events.jsonl (aiqt_hooks.py:_orch_pointer_resolves) only when os.stat succeeds on the
                         register too (a failed register open holds at aiqt_hooks.py:_orch_register_authority, so the
                         reader returns at aiqt_hooks.py:_orch_attestation_refs). The register <path>.anchor is not
                         checked: the hook opens it non-blocking without following a final symlink and
                         checks its type on the open descriptor (aiqt_hooks.py:_orch_register_authority
                         `fd = os.open(anchor, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW`), so a special anchor is a
                         hold, never a blocked hook. Each is checked with os.stat only,
                         never opened. One that exists
                         and is not a regular file (a FIFO, which would block the hook open
                         indefinitely; a directory; a device; or a symlink to one of these) is
                         reported as cannot-evaluate, exit 2, naming the path and its type, and the
                         hook reader that would open it is not called and no enumerator runs. An
                         absent path is left to the hook, whose open raises rather than blocks. The
                         paths only the resume audit opens (the handoff and findings records,
                         mistakes_register and the audit state files) are not checked here, since
                         the preview never opens them, and the escape sentinel is opened
                         non-blocking (aiqt_hooks.py:_orch_escape_stat) and needs no check.
                         The writes the judged handler makes with a plain blocking open are
                         checked the same way. guard-events.jsonl, which every judged verdict of
                         either handler appends to (aiqt_hooks.py:_orch_stop_family
                         `_orch_guard_event(root, event_name, verdict.lower(), reason)`,
                         aiqt_hooks.py:orch_yield_tool `_orch_guard_event(root, "yield-tool", verdict.lower(), reason)`,
                         through aiqt_hooks.py:_orch_append_jsonl `with open(path,`), is checked
                         before the context is built, whatever the attestations declaration, so a
                         FIFO there, at which the real call would block even on a clean ALLOW, is
                         cannot-evaluate, exit 2. After the verdict (_verdict_write_paths) it checks
                         escape-spoof.json where the context records an ignored escape sentinel,
                         and forced-exit.jsonl where the verdict is an ALLOW_WITH_FINDINGS that the
                         loop bound, the loop signal or the schedule cap releases past open work;
                         a special file at either is cannot-evaluate, exit 2, and the output says
                         that the enumerator has run by then.

  --resume-audit         Run the resume audit on demand. It delegates to orch_resume_audit in the
                         vendored hook (aiqt_hooks.py:orch_resume_audit), so the probes (_orch_resume_probes,
                         aiqt_hooks.py:_orch_resume_probes, including the attestation snapshot refresh at
                         aiqt_hooks.py:_orch_resume_probes), the resume-barrier.json write (aiqt_hooks.py:orch_resume_audit), and the findings guard
                         event are exactly those of the hook. The same kind of special-file check
                         runs first, over the paths the audit opens with a blocking open, each
                         checked only when the audit would reach its open: record.handoff (aiqt_hooks.py:_orch_resume_probes),
                         record.findings (aiqt_hooks.py:_orch_resume_probes and aiqt_hooks.py:_orch_merge_pending_findings), record.pending_decisions (aiqt_hooks.py:_orch_resume_probes), when
                         declared (aiqt_hooks.py:_orch_validate_attestations) the attestations register (aiqt_hooks.py:_orch_chained_rows via aiqt_hooks.py:_orch_validate_attestations, aiqt_hooks.py:_orch_register_authority via
                         aiqt_hooks.py:_orch_validate_attestations), mistakes_register
                         (aiqt_hooks.py:_orch_validate_attestations), and the state files guard-events.jsonl (read at aiqt_hooks.py:_orch_pointer_resolves, appended
                         at aiqt_hooks.py:_orch_append_jsonl through aiqt_hooks.py:orch_resume_audit), escape-spoof.json (aiqt_hooks.py:_orch_pending_artefact_findings), forced-exit.jsonl
                         (aiqt_hooks.py:_orch_forced_exit_findings), and forced-exit-surfaced.json (aiqt_hooks.py:_orch_forced_exit_findings) only when os.stat succeeds on
                         forced-exit.jsonl and it is not empty (no rows return at aiqt_hooks.py:_orch_forced_exit_findings).
                         The register anchor is not checked, as for the preview. Nor are the temporary
                         files the audit writes: each has a random name, created with O_EXCL and
                         O_NOFOLLOW (aiqt_hooks.py:_orch_write_json_at `tmp = "{}.{}.tmp".format(name, os.urandom(8).hex())`)
                         or with open mode "x" (aiqt_hooks.py:_orch_barrier_write `with open(tmp, "x", encoding="utf-8") as fh:`),
                         so no file already present is ever opened in its place. With an unreadable
                         registry the hook appends to resume-barrier.json.unused (aiqt_hooks.py:orch_resume_audit
                         `_orch_append_jsonl(barrier_path +`) and then runs the resume probes over an empty registry
                         (aiqt_hooks.py:_orch_resume_audit_findings `reg = {}`), which reach the fixed state files
                         above (guard-events.jsonl, escape-spoof.json, forced-exit.jsonl and
                         forced-exit-surfaced.json) under the state directory the hook resolves for that
                         registry, checked as for a readable registry that declares nothing. A special file at one of these is reported as
                         cannot-evaluate, exit 2, and the audit is not run. The audit runs no
                         enumerator and does not open the lease (os.stat only, aiqt_hooks.py:_orch_resume_probes), the mode
                         record, turn-state.json, dispatch-ledger.jsonl or
                         backlog-checkpoint.json, so a special file at one of those, or at an
                         enumerator operand, does not refuse the audit. The hook swallows a failed
                         barrier write (aiqt_hooks.py:orch_resume_audit), so the doctor records the barrier
                         mtime and content BEFORE the audit and requires that the audit rewrote it:
                         the file must have changed and its ts must fall within this run. The hook
                         replaces the barrier whole (aiqt_hooks.py:_orch_barrier_write `os.replace(tmp, path)`), so a
                         read-only barrier file is still rewritten; a barrier the hook could not
                         rewrite (for example in a state directory it cannot write) is reported as
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
                     (_orch_root -> _recovery_toplevel, aiqt_hooks.py:_orch_root).
  --session-id ID    preflight only: the session id used for holder-scoped lease checks
                     (aiqt_hooks.py:_orch_scope_live). Default: none.
  --stop-hook-active preflight only: preview an event whose stop_hook_active is true, which sets
                     the loop signal (aiqt_hooks.py:_orch_build_ctx `"loop_signal": data.get(`) and so,
                     for the stop kind, the loop-bound release (aiqt_hooks.py:decide_yield). Default: absent.
  --tool-stop        preflight idle only: preview a scheduling call whose tool_input stop is true,
                     which the hook judges as kind stop (aiqt_hooks.py:orch_yield_tool). Default: absent.
  --wake-text TEXT   preflight idle only: the text a scheduling call would carry (the hook joins
                     the string values of tool_input, aiqt_hooks.py:orch_yield_tool), used for the wake-hygiene
                     check (aiqt_hooks.py:_orch_build_ctx) and to detect a quiet-duration claim that is
                     not previewed. Default: none.
  --tool NAME        preflight idle only: the scheduling tool whose call is previewed, matched
                     against yield_tools as the hook matches it. Default: ScheduleWakeup.

Exit status:
  preflight      0 when the effective verdict is ALLOW (including out of scope or out of roster),
                 1 when it is DENY or ALLOW_WITH_FINDINGS, 2 on a usage error, an unresolvable root,
                 an absent or unreadable registry (a registry file that is not a regular file
                 included), a path the preview would open with a blocking open (see above) that
                 exists and is not a regular file, an idle verdict that
                 hangs on the quiet-claim check, which is not previewed, or a checkpoint write
                 to a path this preview does not model.
  --resume-audit 0 when the barrier this audit rewrote reads active false, 1 when it reads active
                 true, 2 on a usage error, an unresolvable root, an absent registry, a path the
                 audit would open with a blocking open (see above) that exists and is not a regular
                 file, a barrier that cannot be recorded before or read back after the audit, or a
                 barrier that this audit did not rewrite (unchanged, or a ts outside this run).

Residuals (disclosed): the preview is a point-in-time reading. A later edit to the backlog, the
ledger, the pending-decisions record, the sentinel, or the clock can change what the real hook
decides. The counter-save check is an approximation: os.access tests the permission bits, ACLs and
read-only mounts for the real uid, and it cannot foresee a full disk, a quota, a race with another
writer, or an effective uid that differs from the real one, so its answer can be wrong in either
direction. The bits of a directory os.makedirs would create are read from the nearest existing
ancestor: the owner entry of its default ACL, else the process umask; a default ACL that cannot be
parsed falls back to the umask, and named user and group entries are not modelled, since the hook
writes as the owner of what it creates. The checkpoint-write prediction (_atomic_write_outcome) is the
same kind of approximation: it cannot foresee a full disk, a quota, a sticky directory owned by another user, a
race with another writer, or an effective uid that differs from the real one; and it is a
point-in-time lstat, so a state directory or target changed between the prediction and the hook
write can change the outcome. The enumerator is a
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
# aiqt_hooks.py:orch_stop_guard and aiqt_hooks.py:orch_teammate_idle; a scheduling call that parks the run
# uses "schedule_idle", aiqt_hooks.py:orch_yield_tool, unless its tool_input stop is true, which
# _preflight derives from the event data as the hook does).
KINDS = {"stop": "stop", "idle": "schedule_idle"}
DEFAULT_TOOL = "ScheduleWakeup"
# The barrier ts must fall inside this run, widened by this much for clock granularity.
TS_SKEW = datetime.timedelta(seconds=1)
READ_CHUNK = 1 << 20
# A lease within this many seconds of a freshness bound is treated as possibly on either side of it
# when the doctor decides whether the hook reaches the holder lease open (_lease_live_states).
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
    """A hook write this preview does not model; the preview reports it as not previewed, exit 2."""


_ACL_DEFAULT_XATTR = "system.posix_acl_default"
_ACL_VERSION = 2
_ACL_USER_OBJ = 0x01


def _process_umask():
    """The process umask, read by the os.umask round trip (set to 0o077, then restored at once). It
    changes no file and no permission of any existing file."""
    mask = os.umask(0o077)
    os.umask(mask)
    return mask


def _default_acl_user_obj(raw):
    """The owner permission bits (0 to 7) of a POSIX default ACL in its extended-attribute form (a
    little-endian version word, then 8-byte entries of tag, permission and id), or None when raw is
    not such an ACL or holds no owner entry."""
    if len(raw) < 4 or (len(raw) - 4) % 8 or int.from_bytes(raw[0:4], "little") != _ACL_VERSION:
        return None
    for k in range(4, len(raw), 8):
        if int.from_bytes(raw[k:k + 2], "little") == _ACL_USER_OBJ:
            return int.from_bytes(raw[k + 2:k + 4], "little") & 0o7
    return None


def _created_dir_owner_bits(ancestor):
    """(bits, source): the owner permission bits of every directory os.makedirs(mode 0o777) would
    create under ancestor, and what decides them. With a default ACL on ancestor the kernel does not
    apply the umask: the new directory takes the owner entry of that ACL and inherits the ACL, so each
    created level gets the same bits. Without one the bits are 0o777 less the process umask."""
    getxattr = getattr(os, "getxattr", None)
    raw = None
    if getxattr is not None:
        try:
            raw = getxattr(ancestor, _ACL_DEFAULT_XATTR)
        except OSError:
            raw = None
    if raw:
        bits = _default_acl_user_obj(raw)
        if bits is not None:
            return bits, "the default ACL of {}".format(ancestor)
    mask = _process_umask()
    return (0o777 & ~mask) >> 6 & 0o7, "the process umask 0o{:03o}".format(mask)


def _created_dir_blocker(ancestor, directory):
    """None when the directories os.makedirs would create for directory under ancestor let the owner
    create the next level and then write and search the last one (read too where O_PATH is absent),
    as the hook writer needs; else the reason it would fail."""
    bits, source = _created_dir_owner_bits(ancestor)
    need = 0o3 | (0 if hasattr(os, "O_PATH") else 0o4)
    if bits & need == need:
        return None
    return ("{} is absent, and the directories os.makedirs would create for it under {} get owner "
            "permission bits {:o} from {}, without the write and search{} permission the save needs"
            .format(directory, ancestor, bits, source, "" if hasattr(os, "O_PATH") else " and read"))


def _atomic_write_outcome(path):
    """(outcome, reason) for _orch_write_json_atomic(path, obj) (aiqt_hooks.py:_orch_write_json_atomic),
    decided with lstat and os.access only, so nothing is written. outcome is True when the write would
    succeed and False when it would fail (reason says why). It follows the steps of the hook writer:
    os.makedirs of the parent (aiqt_hooks.py:_orch_write_json_atomic `os.makedirs(directory, exist_ok=True)`),
    which fails when the parent, or the nearest existing ancestor of an absent parent, is not a
    directory or cannot be written; an open of the parent with O_PATH where it exists, else O_RDONLY,
    which then needs read permission on it too; the create of a temporary file under a fresh random
    name with O_EXCL and O_NOFOLLOW (aiqt_hooks.py:_orch_write_json_at `tmp = "{}.{}.tmp".format(name,`),
    which needs write and search permission on the parent and never opens a file already present, so
    nothing at a temporary path can block it or redirect it; and os.replace onto path
    (aiqt_hooks.py:_orch_write_json_at `os.replace(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)`), which fails
    when path is a directory and replaces a symbolic link there rather than following it. os.access
    is an approximation (see Residuals)."""
    parent = os.path.dirname(path)
    if os.path.lexists(parent) and not os.path.isdir(parent):
        return False, ("{} exists but is not a directory, so os.makedirs raises "
                       "(aiqt_hooks.py:_orch_write_json_atomic)".format(parent))
    if not os.path.isdir(parent):
        # os.makedirs would create it under the nearest existing ancestor, and then the temporary
        # file and the rename land in a new empty directory this process created.
        ancestor = os.path.dirname(parent)
        while ancestor and not os.path.lexists(ancestor) and ancestor != os.path.dirname(ancestor):
            ancestor = os.path.dirname(ancestor)
        if not os.path.isdir(ancestor) or not os.access(ancestor, os.W_OK | os.X_OK):
            return False, ("{} is absent and cannot be created under {} "
                           "(aiqt_hooks.py:_orch_write_json_atomic)".format(parent, ancestor))
        blocker = _created_dir_blocker(ancestor, parent)
        if blocker is not None:
            return False, "{} (aiqt_hooks.py:_orch_write_json_atomic)".format(blocker)
        return True, None
    need = os.W_OK | os.X_OK | (0 if hasattr(os, "O_PATH") else os.R_OK)
    if not os.access(parent, need):
        return False, ("{} cannot be written and searched{}, so the temporary file cannot be "
                       "created there (aiqt_hooks.py:_orch_write_json_at)".format(
                           parent, "" if hasattr(os, "O_PATH") else " and read"))
    try:
        target = os.lstat(path)
    except FileNotFoundError:
        return True, None
    except OSError as exc:
        return False, ("{} cannot be examined ({}), so the hook writer fails "
                       "(aiqt_hooks.py:_orch_write_json_at)".format(path, exc))
    if stat.S_ISDIR(target.st_mode):
        return False, ("{} is a directory, so the replace over it raises "
                       "(aiqt_hooks.py:_orch_write_json_at)".format(path))
    return True, None


def _build_ctx_previewed(hook, reg, root, kind, data, wake_text):
    """(ctx, notes): the context exactly as the hook builds it, _orch_build_ctx with
    record_checkpoint=True (aiqt_hooks.py:_orch_build_ctx), with hook._orch_write_json_atomic and
    hook._orch_guard_event replaced for this call only by stand-ins that write nothing. The
    stand-in write returns what the hook writer returns for the outcome _atomic_write_outcome
    predicts (None on success, else a failure detail) for the checkpoint rewrite
    (aiqt_hooks.py:_orch_checkpoint_union `unsaved = _orch_write_json_atomic(path,`) and the init-marker
    write (aiqt_hooks.py:_orch_checkpoint_union `unsaved = _orch_write_json_atomic(marker,`), so the hook
    code itself decides whether the marker write is reached and whether it injects the
    cannot-evaluate row; notes lists the predicted writes. Raises _Unpreviewed for a write the
    preview does not model."""
    sd = hook._orch_state_dir_for_root(root)
    checkpoint = os.path.join(sd, "backlog-checkpoint.json")
    marker = os.path.join(sd, "checkpoint-init.marker")
    notes = []

    def write(path, _obj):
        if path not in (checkpoint, marker):
            raise _Unpreviewed("the hook would write {}, a write this preview does not model"
                               .format(path))
        outcome, reason = _atomic_write_outcome(path)
        if path == checkpoint:
            notes.append("checkpoint rewrite (aiqt_hooks.py:_orch_checkpoint_union): {}".format(
                "would succeed" if outcome else "would FAIL ({}); the hook then skips the "
                "init-marker write and adds a warning to its output".format(reason)))
        else:
            notes.append("init-marker write (aiqt_hooks.py:_orch_checkpoint_union): {}".format(
                "would succeed" if outcome else "would FAIL ({}); the hook then injects a "
                "cannot-evaluate row".format(reason)))
        return None if outcome else "predicted: {}".format(reason)

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
    It mirrors _orch_save_turn_state, which saves through _orch_write_json_atomic (aiqt_hooks.py:_orch_save_turn_state,
    aiqt_hooks.py:_orch_write_json_atomic `os.makedirs(directory, exist_ok=True)`): os.makedirs(state_dir), an open of
    the state directory with O_PATH where it exists, else O_RDONLY, then a temporary file created in that
    directory and replaced onto turn-state.json (aiqt_hooks.py:_orch_write_json_at `os.replace(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)`).
    The save therefore needs write and search permission on the state directory (and read permission
    too where O_PATH is absent); the permission bits of turn-state.json itself do not matter, and a
    symlink there is replaced, not followed, but a directory there cannot be replaced. It checks this
    with os.access and os.lstat only, so it writes nothing. os.access is an approximation (see
    Residuals)."""
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
        return _created_dir_blocker(ancestor, "the state directory " + state_dir)
    need = os.W_OK | os.X_OK | (0 if hasattr(os, "O_PATH") else os.R_OK)
    if not os.access(state_dir, need):
        return ("the state directory {} cannot be written and searched{}, so the temporary file "
                "cannot be created there".format(state_dir, "" if hasattr(os, "O_PATH") else " and read"))
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return "{} cannot be examined ({})".format(path, exc)
    if stat.S_ISDIR(st.st_mode):
        return "{} is a directory, which the replace cannot overwrite".format(path)
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


def _section(reg, key):
    """The registry section key when it is an object, else an empty dict (as the hook reads it)."""
    value = reg.get(key)
    return value if isinstance(value, dict) else {}


def _state_path(hook, root, name):
    """A fixed hook state file under the state directory, resolved exactly as every hook reader
    resolves it (_orch_state_dir_for_root, aiqt_hooks.py:_orch_state_dir_for_root)."""
    return os.path.join(hook._orch_state_dir_for_root(root), name)


def _lease_live_states(hook, lease, st):
    """The values the hook can compute, for this lease, of the test that leads to the holder lease open
    (aiqt_hooks.py:_orch_scope_live `if st.st_size > 0 and (fresh or cannot):`): the lease age class is taken
    from the hook classifier itself (aiqt_hooks.py:_orch_lease_age_class), at the clock now and SCOPE_MARGIN
    seconds later, so a lease that crosses a bound of the freshness window between this check and the
    hook call is treated as possibly either side (the window is at least _ORCH_CLOCK_SKEW wide, more
    than the margin, so the two samples cover every value in between)."""
    max_age = lease.get("max_age_hours")
    age = hook._orch_now().timestamp() - st.st_mtime
    return {st.st_size > 0 and hook._orch_lease_age_class(a, max_age) in ("fresh", "cannot")
            for a in (age, age + SCOPE_MARGIN)}


def _scope_read_paths(hook, reg, root, session_id):
    """The paths _orch_scope_live(reg, root, session_id) (aiqt_hooks.py:_orch_scope_live) opens with a plain
    blocking open, each only when the hook reaches that open:
      lease.path  opened at aiqt_hooks.py:_orch_scope_live `with open(path,` only when the lease section is a non-empty object (aiqt_hooks.py:_orch_scope_live `lease = reg.get(`),
                  its path resolves (aiqt_hooks.py:_orch_scope_live `path = _orch_path(root, lease.get(`), os.stat succeeds (aiqt_hooks.py:_orch_scope_live `st = os.stat(path)`), the lease is non-empty and
                  fresh or its horizon cannot be evaluated (aiqt_hooks.py:_orch_scope_live `if st.st_size > 0 and (fresh or cannot):`), holder_is_session_id is set (aiqt_hooks.py:_orch_scope_live `if lease.get(`) and the session id is a
                  non-empty string (aiqt_hooks.py:_orch_scope_live `if not (isinstance(session_id, str) and session_id):`; otherwise the hook returns False unopened).
    The lease is never opened otherwise (the os.stat at aiqt_hooks.py:_orch_scope_live `st = os.stat(path)` does not block), so a FIFO there, whose
    size is 0, is not checked. The mode record is read by _orch_mode_read, which opens it non-blocking and
    reads a special file as a bad record (aiqt_hooks.py:_orch_mode_read `fd = os.open(path, os.O_RDONLY | getattr(os,`), so it is not checked."""
    lease = reg.get("lease") if isinstance(reg.get("lease"), dict) else None
    lease_path = hook._orch_path(root, lease.get("path")) if lease else None
    out = []
    if lease_path and lease.get("holder_is_session_id") and isinstance(session_id, str) and session_id:
        try:
            st = os.stat(lease_path)
        except OSError:
            st = None
        if st is not None and True in _lease_live_states(hook, lease, st):
            out.append(_site("scope.lease", "declared lease.path", lease_path))
    return out


def _enumerator_runs(reg):
    """True when _orch_enumerate (aiqt_hooks.py:_orch_enumerate) reaches the subprocess at aiqt_hooks.py:_orch_enumerate `result = subprocess.run(argv, capture_output=True,`: the
    enumerator is an object (aiqt_hooks.py:_orch_enumerate `if not isinstance(spec, dict):`) whose argv is a non-empty list of non-empty strings
    (aiqt_hooks.py:_orch_enumerate `if not isinstance(argv, list) or not argv or not all(`). Otherwise it returns NO_ENUMERATOR or ENUMERATOR_ERROR unrun, and _orch_build_ctx
    skips every reader after the enumeration (aiqt_hooks.py:_orch_build_ctx `if status ==`)."""
    spec = reg.get("enumerator")
    if not isinstance(spec, dict):
        return False
    argv = spec.get("argv")
    return isinstance(argv, list) and bool(argv) and all(isinstance(a, str) and a for a in argv)


def _ctx_read_paths(hook, reg, root):
    """The paths _orch_build_ctx (aiqt_hooks.py:_orch_build_ctx) opens with a plain blocking open for
    reading, traced through every reader it calls, each only when the call reaches it:
      turn-state.json              _orch_turn_state, lexists then open at aiqt_hooks.py:_orch_turn_state `if not os.path.lexists(path):` (via aiqt_hooks.py:_orch_build_ctx `ts = _orch_turn_state(root)`), always
      enumerator argv[2] on        opened by the enumerator, run with cwd = the root (aiqt_hooks.py:_orch_enumerate `result = subprocess.run(argv, capture_output=True,`, via aiqt_hooks.py:_orch_build_ctx `status, payload = _orch_enumerate(reg, root)`),
                                   only when the enumerator runs (_enumerator_runs)
      dispatch-ledger.jsonl        aiqt_hooks.py:_orch_live_ledger_ids `rows, bad = _orch_read_jsonl(os.path.join(`, opened at aiqt_hooks.py:_orch_read_jsonl `with open(path,` (via aiqt_hooks.py:_orch_build_ctx `live_ids, ledger_readable, _detail =`)
      record.pending_decisions     _orch_pending_haystack, opened at aiqt_hooks.py:_orch_pending_haystack `with open(declared,` (via aiqt_hooks.py:_orch_build_ctx `_orch_pending_haystack(reg, root), staleness,`)
      attestations-validated.json  _orch_attestation_refs, opened at aiqt_hooks.py:_orch_attestation_refs `with open(path,` (via aiqt_hooks.py:_orch_build_ctx `attestations=_orch_attestation_refs(reg, root,`), when
                                   attestations is declared (aiqt_hooks.py:_orch_attestation_refs `at_path = _orch_path(root, reg.get(`)
      attestations                 aiqt_hooks.py:_orch_register_authority `with open(path,` (via aiqt_hooks.py:_orch_attestation_refs `astatus, aseq, adigest = _orch_register_authority(root,`) and _orch_chained_rows
                                   aiqt_hooks.py:_orch_chained_rows `with open(path,` (via aiqt_hooks.py:_orch_attestation_refs `rows, _detail = _orch_chained_rows(at_path,`), only when os.stat succeeds on the snapshot
                                   (a failed snapshot open returns at aiqt_hooks.py:_orch_attestation_refs `except (OSError, ValueError):`)
      guard-events.jsonl           always: every judged verdict appends a row after the context is built (aiqt_hooks.py:_orch_stop_family
                                   `_orch_guard_event(root, event_name, verdict.lower(), reason)`, aiqt_hooks.py:orch_yield_tool `_orch_guard_event(root, "yield-tool", verdict.lower(), reason)`,
                                   opened at aiqt_hooks.py:_orch_append_jsonl `with open(path,`), and it is also read inside the build
                                   (aiqt_hooks.py:_orch_pointer_resolves `rows, _bad = _orch_read_jsonl(os.path.join(sd,`, via aiqt_hooks.py:_orch_attestation_derive `elif not _orch_pointer_resolves(root, sd, pointer):`)
                                   when os.stat succeeds on the snapshot and the register
      backlog-checkpoint.json      _orch_checkpoint_union, lexists then open at aiqt_hooks.py:_orch_checkpoint_union `present = os.path.lexists(path)` (via aiqt_hooks.py:_orch_build_ctx `_orch_checkpoint_union(root, payload,`)
    Every reader after the enumeration runs only on a successful enumeration (aiqt_hooks.py:_orch_build_ctx `if status ==`); the doctor
    models the part a registry read decides (_enumerator_runs) and checks the rest whenever the
    enumerator runs, since only running it decides whether it succeeds. Not modelled, so checked
    conservatively: the snapshot content (aiqt_hooks.py:_orch_attestation_refs `if not isinstance(snap, dict) or snap.get(`), whether git tracks the register (aiqt_hooks.py:_orch_register_authority `if rel and not rel.startswith(os.pardir + os.sep) and`),
    and a guard-events pointer in a register row (aiqt_hooks.py:_orch_pointer_resolves `if pointer.startswith(`). Not opened for reading with a blocking open,
    so not checked here: the checkpoint-init marker (lexists only at aiqt_hooks.py:_orch_checkpoint_union `if not present and os.path.lexists(marker):`
    and aiqt_hooks.py:_orch_checkpoint_union `elif not os.path.lexists(marker):`), the register anchor (opened non-blocking at
    aiqt_hooks.py:_orch_register_authority `fd = os.open(anchor, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW`, its type checked on the
    descriptor) and the escape sentinel (opened non-blocking at aiqt_hooks.py:_orch_escape_stat `fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW`, via aiqt_hooks.py:_orch_build_ctx `escape_active, escape_spoof = _orch_escape_active(reg,`).
    The checkpoint writes (aiqt_hooks.py:_orch_checkpoint_union `unsaved = _orch_write_json_atomic(path,`) are modelled by
    _build_ctx_previewed and _atomic_write_outcome instead."""
    out = [_site("ctx.turn_state", "hook state file turn-state.json",
                 _state_path(hook, root, "turn-state.json")),
           _site("ctx.guard_events", "hook state file guard-events.jsonl",
                 _state_path(hook, root, "guard-events.jsonl"))]
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
    out.append(_site("ctx.checkpoint", "hook state file backlog-checkpoint.json",
                     _state_path(hook, root, "backlog-checkpoint.json")))
    return out


def _forced_exit_reached(hook, kind, ctx, verdict):
    """True when the judged handler records a forced exit: an ALLOW_WITH_FINDINGS released by the loop
    bound or the loop signal (the stop kind, aiqt_hooks.py:_orch_stop_family
    `if (ctx["counter"] >= _ORCH_LOOP_BOUND or ctx["loop_signal"])`) or by the schedule cap on an
    unchanged basis (schedule_idle, aiqt_hooks.py:orch_yield_tool
    `forced = ((kind == "stop" and (ctx["counter"] >= _ORCH_LOOP_BOUND or ctx["loop_signal"]))`), past an
    open disposition or a failed enumeration (aiqt_hooks.py:_orch_open_dispositions)."""
    if verdict != "ALLOW_WITH_FINDINGS":
        return False
    if kind == "stop":
        forced = ctx["counter"] >= hook._ORCH_LOOP_BOUND or ctx["loop_signal"]
    else:
        forced = ctx["schedule_denials"] >= hook._ORCH_SCHEDULE_CAP and ctx["basis_unchanged"]
    return bool(forced) and bool(hook._orch_open_dispositions(ctx) or ctx["enum_status"] != "ok")


def _verdict_write_paths(hook, root, kind, ctx, verdict):
    """The paths the judged handler opens with a plain blocking open for writing once its context is
    built, other than guard-events.jsonl (checked before the build, ctx.guard_events), each only when the
    handler reaches it:
      escape-spoof.json   written at aiqt_hooks.py:_orch_write_json `with open(path, "w", encoding="utf-8") as fh:` (via
                          aiqt_hooks.py:_orch_record_escape_spoof `ok_file = _orch_write_json(`), when the context records an
                          ignored escape sentinel (aiqt_hooks.py:_orch_stop_family `if ctx.get("escape_spoof") else ""`)
      forced-exit.jsonl   appended at aiqt_hooks.py:_orch_append_jsonl `with open(path,` (via
                          aiqt_hooks.py:_orch_record_forced_exit `ok_file = _orch_append_jsonl(`), when _forced_exit_reached
    The saves of turn-state.json (the denial counter, the wake digest) replace their target and never
    open it, so they are modelled by _counter_save_blocker, not here."""
    out = []
    if ctx.get("escape_spoof"):
        out.append(_site("verdict.escape_spoof", "hook state file escape-spoof.json",
                         _state_path(hook, root, "escape-spoof.json")))
    if _forced_exit_reached(hook, kind, ctx, verdict):
        out.append(_site("verdict.forced_exit", "hook state file forced-exit.jsonl",
                         _state_path(hook, root, "forced-exit.jsonl")))
    return out


def _forced_exit_may_have_rows(log):
    """False when _orch_read_jsonl(forced-exit.jsonl) cannot return a row: os.stat fails, so the
    open at aiqt_hooks.py:_orch_read_jsonl `with open(path,` raises and returns ([], 0) or (None, 0) (aiqt_hooks.py:_orch_read_jsonl `except FileNotFoundError:`), or the file is empty, so
    there are no lines; either way _orch_forced_exit_findings returns at aiqt_hooks.py:_orch_forced_exit_findings `if rows is None:` before the
    surfaced set. A non-empty file may still hold no rows, which only reading it decides, so it
    counts as possibly having rows."""
    try:
        return os.stat(log).st_size != 0
    except OSError:
        return False


def _audit_read_paths(hook, reg, root):
    """The paths orch_resume_audit (aiqt_hooks.py:orch_resume_audit) opens with a plain blocking open on a
    readable registry, traced through _orch_resume_probes (aiqt_hooks.py:_orch_resume_probes) and every reader it calls,
    each only when the audit reaches it:
      record.handoff                  opened at aiqt_hooks.py:_orch_resume_probes `with open(handoff_path,`, when declared
      record.findings                 opened at aiqt_hooks.py:_orch_resume_probes `with open(path,`, and at aiqt_hooks.py:_orch_merge_pending_findings `with open(path,` (via aiqt_hooks.py:_orch_resume_probes `findings.extend(_orch_merge_pending_findings(reg, root))`), when declared
      record.pending_decisions        opened at aiqt_hooks.py:_orch_resume_probes `with open(path,`, when declared
      attestations                    aiqt_hooks.py:_orch_chained_rows `with open(path,` (via aiqt_hooks.py:_orch_validate_attestations `rows, detail = _orch_chained_rows(at_path,`) and _orch_register_authority
                                      aiqt_hooks.py:_orch_register_authority `with open(path,` (via aiqt_hooks.py:_orch_validate_attestations `astatus, aseq, adigest = _orch_register_authority(root,`), when declared (aiqt_hooks.py:_orch_validate_attestations `at_path = _orch_path(root, reg.get(`)
      mistakes_register               aiqt_hooks.py:_orch_chained_rows `with open(path,` (via aiqt_hooks.py:_orch_validate_attestations `mr_path = _orch_path(root, reg.get(`), when declared
      guard-events.jsonl              read by aiqt_hooks.py:_orch_pointer_resolves `rows, _bad = _orch_read_jsonl(os.path.join(sd,` (via aiqt_hooks.py:_orch_validate_attestations `refs, unsub, dfindings = _orch_attestation_derive(reg,` and aiqt_hooks.py:_orch_validate_attestations `if not _orch_pointer_resolves(root, sd, pointer):`),
                                      opened at aiqt_hooks.py:_orch_read_jsonl `with open(path,`; appended by _orch_guard_event at aiqt_hooks.py:_orch_append_jsonl `with open(path,` (via
                                      aiqt_hooks.py:orch_resume_audit `_orch_event_warn(root, "resume-audit", "findings",`); both depend on file content, so always checked
      escape-spoof.json               lexists then open at aiqt_hooks.py:_orch_pending_artefact_findings `if os.path.lexists(path):` (via aiqt_hooks.py:_orch_resume_probes `findings.extend(_orch_pending_artefact_findings(root))`)
      forced-exit.jsonl               aiqt_hooks.py:_orch_forced_exit_findings `log = os.path.join(sd,`, opened at aiqt_hooks.py:_orch_read_jsonl `with open(path,`
      forced-exit-surfaced.json       opened at aiqt_hooks.py:_orch_forced_exit_findings `with open(surfaced_path,`, only when the log may hold rows
                                      (_forced_exit_may_have_rows; no rows return at aiqt_hooks.py:_orch_forced_exit_findings `if not rows:`)
    Not checked, since the hook never opens them with a blocking open: the register anchor (aiqt_hooks.py:_orch_register_authority
    `fd = os.open(anchor, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW`), and the temporary files of the snapshot and surfaced-set saves,
    created under a random name with O_EXCL and O_NOFOLLOW (aiqt_hooks.py:_orch_write_json_at `tmp = "{}.{}.tmp".format(name, os.urandom(8).hex())`).
    resume-barrier.json (replaced at aiqt_hooks.py:_orch_barrier_write `os.replace(tmp, path)`, via aiqt_hooks.py:orch_resume_audit `_orch_barrier_write(barrier_path,`) is read before the audit by _barrier_snapshot, which
    refuses a special file there. The audit runs no enumerator and does not open the lease (os.stat
    only, aiqt_hooks.py:_orch_resume_probes `st = os.stat(path)`), the mode record, turn-state.json, dispatch-ledger.jsonl or backlog-checkpoint.json,
    so none of those is checked here. Not modelled, so checked conservatively: whether git tracks the
    register (aiqt_hooks.py:_orch_register_authority `if rel and not rel.startswith(os.pardir + os.sep) and`), the rows and pointers a register holds (aiqt_hooks.py:_orch_pointer_resolves `if pointer.startswith(`, aiqt_hooks.py:_orch_validate_attestations `refs, unsub, dfindings = _orch_attestation_derive(reg,`, aiqt_hooks.py:_orch_validate_attestations `if not _orch_pointer_resolves(root, sd, pointer):`), the rows the
    forced-exit log and the surfaced set hold (aiqt_hooks.py:_orch_forced_exit_findings), and whether there are findings to record
    (aiqt_hooks.py:orch_resume_audit `if findings:`)."""
    rec = _section(reg, "record")
    out = [_site("audit.handoff", "declared record.handoff", hook._orch_path(root, rec.get("handoff"))),
           _site("audit.findings", "declared record.findings",
                 hook._orch_path(root, rec.get("findings"))),
           _site("audit.pending_decisions", "declared record.pending_decisions",
                 hook._orch_path(root, rec.get("pending_decisions")))]
    at_path = hook._orch_path(root, reg.get("attestations"))
    if at_path:
        out.append(_site("audit.attestations", "declared attestations", at_path))
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
    """On an unreadable registry the audit appends to resume-barrier.json.unused (appended at aiqt_hooks.py:_orch_append_jsonl `with open(path,`,
    via aiqt_hooks.py:orch_resume_audit `_orch_append_jsonl(barrier_path +`), always reached, and then runs the resume probes over an empty
    registry (aiqt_hooks.py:_orch_resume_audit_findings `reg = {}`), so it reaches every fixed state file _audit_read_paths lists for a
    registry that declares nothing, guard-events.jsonl included (appended through aiqt_hooks.py:_orch_event_warn, via
    aiqt_hooks.py:orch_resume_audit `_orch_event_warn(root, "resume-audit", "findings",`, since the unreadable registry is itself a
    finding, aiqt_hooks.py:_orch_resume_audit_findings `findings.append("the orchestration registry could not be read ({})".format(reg))`), each under
    the state directory the hook resolves for that registry."""
    return [_site("audit_bad.unused", "hook state file resume-barrier.json.unused",
                  _state_path(hook, root, "resume-barrier.json.unused"))] + _audit_read_paths(hook, {}, root)


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


def _refuse_special_after_verdict(found):
    """Report a special file at a path the judged handler would write after its verdict, as
    cannot-evaluate, exit 2."""
    print("cannot evaluate: {}; the hook would open it with a blocking open after its verdict, so the "
          "call would block there; the context was built and the registry enumerator ran as the hook "
          "runs it, and the doctor itself wrote nothing".format(found))
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
    (aiqt_hooks.py:_orch_root). A flag that is off leaves its field absent, which the hook reads
    exactly as any value other than true (its tests are "is True", aiqt_hooks.py:_orch_build_ctx and
    aiqt_hooks.py:orch_yield_tool)."""
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
              "(aiqt_hooks.py:_orch_stop_family); a scheduling call is denied (aiqt_hooks.py:orch_yield_tool)")
        return 2
    print("registry: ok")
    # The session id exactly as both handlers read it (aiqt_hooks.py:_orch_stop_family and
    # aiqt_hooks.py:orch_yield_tool `scope = _orch_scope_live(reg, root, data.get(`).
    session_id = data.get("session_id")
    special = _first_special(_scope_read_paths(hook, reg, root, session_id))
    if special is not None:
        # _orch_scope_live opens these with a plain blocking open (see _scope_read_paths), so a FIFO
        # there would hang the preview; the scope reader is not called.
        return _refuse_special(special)
    scope_live = hook._orch_scope_live(reg, root, session_id)
    if scope_live == "cannot":
        print("scope: cannot be evaluated ({}); the hook judges the call with a cannot-evaluate row "
              "for it".format(hook._ORCH_SCOPE_CANNOT_DETAIL))
    else:
        print("scope: {}".format("live" if scope_live else
                                 "not live (the hook allows without judging)"))
    if not scope_live:
        # The hook returns here, before the context is built or the enumerator runs
        # (aiqt_hooks.py:_orch_stop_family for a Stop, aiqt_hooks.py:orch_yield_tool for a scheduling call), so neither does
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
        # (aiqt_hooks.py:orch_yield_tool).
        in_roster = isinstance(declared, list) and tool in declared
        if isinstance(declared, list):
            print("yield_tools roster: {}".format(", ".join(str(t) for t in declared) or "(empty)"))
        else:
            print("yield_tools roster: not a declared list")
        print("tool {}: {}".format(tool, "in the roster, judged" if in_roster else
                                   "not in the roster; the hook allows it unjudged "
                                   "(aiqt_hooks.py:orch_yield_tool)"))
        if not in_roster:
            # The hook returns here too, before the context or the enumeration (aiqt_hooks.py:orch_yield_tool).
            print("enumeration: not run (out of the roster, the hook allows before it enumerates)")
            print("writes: the doctor itself wrote nothing, and no enumerator ran")
            print("effective verdict: ALLOW (out of the roster)")
            return 0
        # Exactly the hook derivation of the kind and the wake text (aiqt_hooks.py:orch_yield_tool
        # `kind = "stop" if tool_input.get(`).
        tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        kind = "stop" if tool_input.get("stop") is True else "schedule_idle"
        wake_text = " ".join(str(v) for v in tool_input.values() if isinstance(v, str))
        print("judged kind: {}".format(
            "stop (tool_input stop is true, aiqt_hooks.py:orch_yield_tool)" if kind == "stop"
            else "schedule_idle (aiqt_hooks.py:orch_yield_tool)"))
        if kind != "schedule_idle":
            print("quiet-claim check: not applicable; the hook runs it only for the schedule_idle "
                  "kind (aiqt_hooks.py:orch_yield_tool)")
        else:
            quiet_claim = (bool(hook._ORCH_QUIET_CLAIM_RE.search(wake_text))
                           and "quiet" in wake_text.lower())
            if quiet_claim:
                print("quiet-claim check: NOT PREVIEWED; the wake text carries a quiet-duration "
                      "claim, which the hook judges inline against the measured gap since the last "
                      "human input before the verdict below (aiqt_hooks.py:orch_yield_tool); it cannot "
                      "be called without writing a guard event")
            else:
                print("quiet-claim check: not previewed (aiqt_hooks.py:orch_yield_tool); the wake text "
                      "carries no quiet-duration claim, so the check does not fire")
    special = _first_special(_ctx_read_paths(hook, reg, root))
    if special is not None:
        # _orch_build_ctx opens these with a plain blocking open (see _ctx_read_paths), so a FIFO
        # there would hang the preview; the context is not built and no enumerator runs.
        return _refuse_special(special)
    # The context as each handler builds it: a Stop passes no wake text (aiqt_hooks.py:_orch_stop_family
    # `ctx, ts, basis = _orch_build_ctx(reg, root, kind, data)`), a scheduling call the joined tool_input
    # text (aiqt_hooks.py:orch_yield_tool `ctx, ts, basis = _orch_build_ctx(reg, root, kind, data, wake_text=wake_text)`);
    # both pass the event data, whose stop_hook_active sets the loop signal (aiqt_hooks.py:_orch_build_ctx
    # `"loop_signal": data.get(`).
    try:
        ctx, notes = _build_ctx_previewed(hook, reg, root, kind, data, wake_text)
    except _Unpreviewed as exc:
        print("writes: the doctor itself wrote nothing; the registry enumerator ran as the hook runs "
              "it (aiqt_hooks.py:_orch_enumerate), and anything that program writes is its own")
        print("hook write: NOT PREVIEWED; {}".format(exc))
        print("effective verdict: UNPREVIEWED (the verdict depends on a hook write that cannot be "
              "decided without writing)")
        return 2
    if scope_live == "cannot":
        # The row the hook adds before it decides (aiqt_hooks.py:_orch_stop_family and aiqt_hooks.py:orch_yield_tool
        # `ctx["cannot_evaluate"] = list(ctx.get("cannot_evaluate", [])) + [`), so the preview judges the same input.
        ctx["cannot_evaluate"] = list(ctx.get("cannot_evaluate", [])) + [
            ("lease:max_age_hours", "cannot-evaluate", hook._ORCH_SCOPE_CANNOT_DETAIL)]
    if ctx["enum_status"] == "ok":
        print("enumeration: ok")
    else:
        print("enumeration: {}: {}".format(ctx["enum_status"], ctx["enum_detail"]))
    print("writes: the doctor itself wrote nothing; the registry enumerator ran as the hook runs it "
          "(aiqt_hooks.py:_orch_enumerate), and anything that program writes is its own")
    if ctx["enum_status"] != "ok":
        print("checkpoint writes: none; the hook reaches the checkpoint union only after a "
              "successful enumeration (aiqt_hooks.py:_orch_build_ctx `if status ==`)")
    for note in notes:
        print("predicted hook write, not made: {}".format(note))
    if ctx["enum_status"] == "ok" and not any(n.startswith("init-marker") for n in notes):
        print("predicted hook write, not made: init-marker write (aiqt_hooks.py:_orch_checkpoint_union): not "
              "reached (the marker exists, or the checkpoint rewrite would fail)")
    print("loop signal: {}".format("set (stop_hook_active is true, aiqt_hooks.py:_orch_build_ctx)"
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
    special = _first_special(_verdict_write_paths(hook, root, kind, ctx, verdict))
    if special is not None:
        return _refuse_special_after_verdict(special)
    if kind_name == "stop":
        blocker = _counter_save_blocker(hook._orch_state_dir_for_root(root))
        if blocker is None:
            print("denial counter: could be saved (an os.access check; the hook saves it on a DENY)")
        else:
            print("denial counter: could NOT be saved ({}; an os.access check)".format(blocker))
            if effective == "DENY":
                # aiqt_hooks.py:_orch_stop_family: an unsaved counter never reaches the loop bound, so the
                # Stop fails open with a warning rather than re-denying.
                print("effective verdict: ALLOW_WITH_FINDINGS (the fail-open allow the hook gives "
                      "when the denial counter cannot be saved, aiqt_hooks.py:_orch_stop_family; the judged "
                      "DENY would not hold. Underlying: {})".format(reason))
                _print_disposition(disposition)
                return 1
    else:
        print("denial counter: not checked; a scheduling DENY stands whether or not the counter "
              "is saved (aiqt_hooks.py:orch_yield_tool)")
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
              "the run); the hook could not write it (for example its state directory cannot be "
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
        # A Stop event carries no tool_input (aiqt_hooks.py:_orch_stop_family passes no wake text), so an input
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
    if args.resume_audit:
        return _resume_audit(hook, root)
    data = _event_data(args.kind, args.session_id, args.stop_hook_active,
                       args.tool if args.tool is not None else DEFAULT_TOOL, args.tool_stop,
                       args.wake_text)
    return _preflight(hook, root, args.kind, data)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
