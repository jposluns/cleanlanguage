#!/usr/bin/env python3
"""Project-owned operator tool for the AIQT orchestration hooks (item 28.2 stage 2, PR1-f).

The vendored hook names this file in two banners (aiqt_hooks.py:9792 and :9844, "python3
tools/orch_doctor.py --resume-audit"). The pack ships its own orch_doctor.py, but that copy imports
symbols absent from the hook vendored here, so this repository carries its own. It imports the
VENDORED hook by path and reuses its functions, so it never reimplements a decision:

  preflight [stop|idle]  Preview what a Stop (stop) or a scheduling call (idle) would decide now. It
                         calls _orch_build_ctx(reg, root, kind, {}, record_checkpoint=False)
                         (aiqt_hooks.py:8434; the preview posture of the checkpoint union,
                         aiqt_hooks.py:8349-8351) and decide_yield (aiqt_hooks.py:8180), then prints
                         the verdict, the reason, the disposition table, and the verdict with the
                         escape sentinel forced off, so the operator sees what the Stop would do
                         without the sentinel. It WRITES NOTHING: no checkpoint, no init marker, no
                         guard event, no turn-state, no spoof record, and no bytecode cache. The only
                         side effect is running the enumerator the registry declares, which the hook
                         runs too.

  --resume-audit         Run the resume audit on demand. It delegates to orch_resume_audit in the
                         vendored hook (aiqt_hooks.py:9765-9794), so the probes (_orch_resume_probes,
                         aiqt_hooks.py:9351-9413, including the attestation snapshot refresh at
                         :9411), the resume-barrier.json write (:9781-9785), and the findings guard
                         event are exactly those of the hook. It then re-reads the barrier it wrote
                         and reports that observed state, never the return value of the call.

Options:
  --root DIR         The repository whose registry is read. Default: the git top level of the
                     current working directory, resolved the same way the hook resolves data["cwd"]
                     (_orch_root -> _recovery_toplevel, aiqt_hooks.py:7590-7595).
  --session-id ID    preflight only: the session id used for holder-scoped lease checks
                     (aiqt_hooks.py:7800-7811). Default: none.
  --wake-text TEXT   preflight idle only: the text a scheduling call would carry, used for the
                     wake-hygiene check (aiqt_hooks.py:8476-8478). Default: none.

Exit status:
  preflight      0 when the effective verdict is ALLOW (including out of scope or out of roster),
                 1 when it is DENY or ALLOW_WITH_FINDINGS, 2 on a usage error, an unresolvable root,
                 or an absent or unreadable registry.
  --resume-audit 0 when the barrier it wrote reads active false, 1 when it reads active true, 2 on a
                 usage error, an unresolvable root, an absent registry, or a barrier that cannot be
                 read back after the audit.

Residuals (disclosed): the preview is a point-in-time reading. A later edit to the backlog, the
ledger, the pending-decisions record, the sentinel, or the clock can change what the real hook
decides. The enumerator is a program the registry declares; whatever it writes is outside the
control of this tool. The tool runs isolated (it re-executes itself under python3 -I when started
without -I), so a file planted beside it cannot shadow a standard-library import.
"""
import os
import sys

if not sys.flags.isolated:
    # Isolated mode keeps this script directory and the environment off the import path, so a file
    # written beside the script cannot shadow a standard-library module (SECI config rule).
    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])

import argparse
import importlib.util
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "plugin", "aiqt-guardrails-hooks", "hooks", "scripts", "aiqt_hooks.py")

# preflight kind -> the decide_yield kind the hook passes (Stop and TeammateIdle use "stop",
# aiqt_hooks.py:8621 and :8627; a scheduling call that parks the run uses "schedule_idle", :8669).
KINDS = {"stop": "stop", "idle": "schedule_idle"}


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


def _print_disposition(disposition):
    if not disposition:
        print("disposition: (empty)")
        return
    print("disposition:")
    for cls, iid, col3, col4 in disposition:
        print("  {:<16} {:<12} {} {}".format(cls, iid, col3, col4).rstrip())


def _preflight(hook, root, kind_name, session_id, wake_text):
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
    in_roster = True
    if kind == "schedule_idle":
        roster = reg.get("yield_tools")
        if isinstance(roster, list) and roster:
            print("yield_tools roster: {}".format(", ".join(str(t) for t in roster)))
        else:
            in_roster = False
            print("yield_tools roster: none declared (the hook allows every scheduling call "
                  "unjudged, aiqt_hooks.py:8665-8667)")
    data = {"session_id": session_id} if session_id else {}
    ctx, _ts, _basis = hook._orch_build_ctx(reg, root, kind, data, wake_text=wake_text,
                                            record_checkpoint=False)
    if ctx["enum_status"] == "ok":
        print("enumeration: ok")
    else:
        print("enumeration: {}: {}".format(ctx["enum_status"], ctx["enum_detail"]))
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
    effective = verdict if (scope_live and in_roster) else "ALLOW"
    print("judged verdict: {}".format(verdict))
    print("judged reason: {}".format(reason))
    print("verdict without the escape sentinel: {}".format(verdict_ne))
    print("reason without the escape sentinel: {}".format(reason_ne))
    print("effective verdict: {}".format(effective))
    _print_disposition(disposition)
    return 0 if effective == "ALLOW" else 1


def _resume_audit(hook, root):
    status, _reg = hook._orch_registry(root)
    print("orch_doctor resume-audit: root {}".format(root))
    if status == "absent":
        print("registry: absent; the orchestration suite is inert here, nothing to audit")
        return 2
    hook.orch_resume_audit({"cwd": root})
    barrier_path = os.path.join(hook._orch_state_dir_for_root(root), "resume-barrier.json")
    try:
        with open(barrier_path, "r", encoding="utf-8") as fh:
            barrier = json.load(fh)
    except (OSError, ValueError) as exc:
        print("barrier: cannot be read back from {} ({}); the audit result is unverified"
              .format(barrier_path, exc))
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
                        help="preflight: preview a verdict without writing anything")
    parser.add_argument("kind", nargs="?", choices=sorted(KINDS), default="stop",
                        help="preflight boundary: stop (default) or idle")
    parser.add_argument("--resume-audit", action="store_true",
                        help="run the resume audit and rewrite resume-barrier.json")
    parser.add_argument("--root", default=None, help="repository root (default: git top level of cwd)")
    parser.add_argument("--session-id", default=None, help="preflight: session id for holder scoping")
    parser.add_argument("--wake-text", default=None, help="preflight idle: the wake text to judge")
    args = parser.parse_args(argv)
    if bool(args.resume_audit) == bool(args.command):
        parser.print_usage(sys.stderr)
        print("orch_doctor.py: give exactly one of: preflight [stop|idle], or --resume-audit",
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
    return _preflight(hook, root, args.kind, args.session_id, args.wake_text)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
