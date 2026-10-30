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
                         calls _orch_build_ctx(reg, root, kind, {}, record_checkpoint=False)
                         (aiqt_hooks.py:8434; the preview posture of the checkpoint union,
                         aiqt_hooks.py:8349-8351) and decide_yield (aiqt_hooks.py:8180), then prints
                         the verdict, the reason, the disposition table, and the verdict with the
                         escape sentinel forced off, so the operator sees what the Stop would do
                         without the sentinel. A Stop DENY holds only when the hook can save the
                         denial counter to turn-state.json; when it cannot, the hook fails open with
                         a warning instead (aiqt_hooks.py:8590-8596, the save at :7752-7760). The
                         doctor therefore checks, with os.access and without writing, whether that
                         save could succeed, and when it could not it reports the fail-open
                         ALLOW_WITH_FINDINGS the hook would give, with the reason. A scheduling DENY
                         stands whether or not the counter is saved (aiqt_hooks.py:8694-8698), so
                         the check applies to stop only. The doctor itself WRITES NOTHING: no
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

  --resume-audit         Run the resume audit on demand. It delegates to orch_resume_audit in the
                         vendored hook (aiqt_hooks.py:9765-9794), so the probes (_orch_resume_probes,
                         aiqt_hooks.py:9351-9413, including the attestation snapshot refresh at
                         :9411), the resume-barrier.json write (:9781-9785), and the findings guard
                         event are exactly those of the hook. The hook swallows a failed barrier
                         write (aiqt_hooks.py:9786-9787), so the doctor records the barrier mtime and
                         content BEFORE the audit and requires that the audit rewrote it: the file
                         must have changed and its ts must fall within this run. A barrier the hook
                         could not rewrite (for example a read-only file) is reported as unverified,
                         exit 2, never as the stale state it still holds. Otherwise it reports the
                         observed rewritten state, never the return value of the call. The barrier
                         is read only as a regular file: it is opened non-blocking and its type is
                         checked with fstat on the open descriptor, so a FIFO (which would block a
                         plain open indefinitely), a directory or a device at that path is reported
                         as cannot-evaluate, exit 2, naming the path and the file type, and before
                         the audit that means the audit is not run. This is the only path the
                         doctor itself opens (_read_regular); the test suite scans the source to
                         keep it so.

Options:
  --root DIR         The repository whose registry is read. Default: the git top level of the
                     current working directory, resolved the same way the hook resolves data["cwd"]
                     (_orch_root -> _recovery_toplevel, aiqt_hooks.py:7590-7595).
  --session-id ID    preflight only: the session id used for holder-scoped lease checks
                     (aiqt_hooks.py:7800-7811). Default: none.
  --wake-text TEXT   preflight idle only: the text a scheduling call would carry (the hook joins
                     the string values of tool_input, aiqt_hooks.py:8670), used for the wake-hygiene
                     check (aiqt_hooks.py:8476-8478) and to detect a quiet-duration claim that is
                     not previewed. Default: none.
  --tool NAME        preflight idle only: the scheduling tool whose call is previewed, matched
                     against yield_tools as the hook matches it. Default: ScheduleWakeup.

Exit status:
  preflight      0 when the effective verdict is ALLOW (including out of scope or out of roster),
                 1 when it is DENY or ALLOW_WITH_FINDINGS, 2 on a usage error, an unresolvable root,
                 an absent or unreadable registry, or an idle verdict that hangs on the quiet-claim
                 check, which is not previewed.
  --resume-audit 0 when the barrier this audit rewrote reads active false, 1 when it reads active
                 true, 2 on a usage error, an unresolvable root, an absent registry, a barrier that
                 cannot be recorded before or read back after the audit, or a barrier that this
                 audit did not rewrite (unchanged, or a ts outside this run).

Residuals (disclosed): the preview is a point-in-time reading. A later edit to the backlog, the
ledger, the pending-decisions record, the sentinel, or the clock can change what the real hook
decides. The counter-save check is an approximation: os.access tests the permission bits, ACLs and
read-only mounts for the real uid, and it cannot foresee a full disk, a quota, a race with another
writer, or an effective uid that differs from the real one, so its answer can be wrong in either
direction. The enumerator is a program the registry declares; whatever it writes is outside the
control of this tool. The quiet-duration check is not previewed (see above). The rewrite check on
the barrier detects a write that did not happen; it cannot tell the hook from another writer that
rewrites the file inside the same run. The tool runs isolated (it re-executes itself under python3 -I when started
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
# aiqt_hooks.py:8621 and :8627; a scheduling call that parks the run uses "schedule_idle", :8669).
KINDS = {"stop": "stop", "idle": "schedule_idle"}
DEFAULT_TOOL = "ScheduleWakeup"
# The barrier ts must fall inside this run, widened by this much for clock granularity.
TS_SKEW = datetime.timedelta(seconds=1)
READ_CHUNK = 1 << 20


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


def _print_disposition(disposition):
    if not disposition:
        print("disposition: (empty)")
        return
    print("disposition:")
    for cls, iid, col3, col4 in disposition:
        print("  {:<16} {:<12} {} {}".format(cls, iid, col3, col4).rstrip())


def _preflight(hook, root, kind_name, session_id, wake_text, tool):
    kind = KINDS[kind_name]
    status, reg = hook._orch_registry(root)
    print("orch_doctor preflight {}: root {}".format(kind_name, root))
    if status == "absent":
        print("registry: absent; the orchestration suite is inert here, nothing to preview")
        return 2
    if status == "bad":
        print("registry: unreadable ({})".format(reg))
        print("posture on an unreadable registry: a Stop fails open with a warning "
              "(aiqt_hooks.py:8579-8583); a scheduling call is denied (aiqt_hooks.py:8654-8661)")
        return 2
    print("registry: ok")
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
    if kind == "schedule_idle":
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
        text = wake_text or ""
        quiet_claim = bool(hook._ORCH_QUIET_CLAIM_RE.search(text)) and "quiet" in text.lower()
        if quiet_claim:
            print("quiet-claim check: NOT PREVIEWED; the wake text carries a quiet-duration claim, "
                  "which the hook judges inline against the measured gap since the last human "
                  "input before the verdict below (aiqt_hooks.py:8675-8692); it cannot be called "
                  "without writing a guard event")
        else:
            print("quiet-claim check: not previewed (aiqt_hooks.py:8675-8692); the wake text "
                  "carries no quiet-duration claim, so the check does not fire")
    data = {"session_id": session_id} if session_id else {}
    ctx, _ts, _basis = hook._orch_build_ctx(reg, root, kind, data, wake_text=wake_text,
                                            record_checkpoint=False)
    if ctx["enum_status"] == "ok":
        print("enumeration: ok")
    else:
        print("enumeration: {}: {}".format(ctx["enum_status"], ctx["enum_detail"]))
    print("writes: the doctor itself wrote nothing; the registry enumerator ran as the hook runs it "
          "(aiqt_hooks.py:7962-7989), and anything that program writes is its own")
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
    if kind == "stop":
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
    status, _reg = hook._orch_registry(root)
    print("orch_doctor resume-audit: root {}".format(root))
    if status == "absent":
        print("registry: absent; the orchestration suite is inert here, nothing to audit")
        return 2
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
    parser.add_argument("--wake-text", default=None, help="preflight idle: the wake text to judge")
    parser.add_argument("--tool", default=None,
                        help="preflight idle: the scheduling tool (default {})".format(DEFAULT_TOOL))
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
    return _preflight(hook, root, args.kind, args.session_id, args.wake_text,
                      args.tool if args.tool is not None else DEFAULT_TOOL)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
