#!/usr/bin/env python3
"""Tests for the adopter hook .claude/hooks/shell_heredoc_detach_guard.py (items 38 and 40, the
heredoc lifting reduction).

1. Every case in tools/shell-heredoc-detach-guard-cases.txt is sent to the hook as a PreToolUse Bash
   payload, and the verdict must match the case: deny and over (the disclosed over-refusal) must be
   denied, allow must be allowed.
2. The flip: a copy of the hook with its deny rule (the line marked DENY-RULE) replaced by a pass must
   turn every deny and over case red (allowed). A flip that changes nothing fails.
3. The oracle self-test: the bash oracle must count a positive control as executed, and must not count a
   syntax-error body, an echo of the marker command, a run that exits non-zero, or escaped data as
   executed.
4. The bash oracle: every case named in ORACLE_CASES must be present with an expectation its kind allows,
   and real bash must agree with the kind. Each such command is run by bash -c in a fresh directory
   with its backgrounded sleep (sleep, a number and an ampersand) replaced by ORACLE_COMMAND, which
   backgrounds true and then writes a computed value, 42, to the file oracle.out, ending with a
   semicolon so a command that followed the ampersand stays separate. A case counts as
   executed only when bash exits 0 and that file holds exactly 42: only execution of the redirection
   creates the file, and the value is computed, so text that bash merely prints (an echoed command or a
   syntax error) never counts. A runs case must be executed and denied; an inert case must not be
   executed (its verdict may be an allow or an over-refusal); a residual case must be executed and
   allowed, which pins a disclosed residual as real.

Exit 0 only when all four hold. Launch with python3 -I. Temporary files go under TMPDIR.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
HOOK_REL = (".claude", "hooks", "shell_heredoc_detach_guard.py")
HOOK = os.path.join(ROOT, *HOOK_REL)
CASES = os.path.join(TOOLS, "shell-heredoc-detach-guard-cases.txt")
MARK = "# DENY-RULE"
EXPECTS = ("deny", "over", "allow")
AMP = "\x26"
APOS = "\x27"
ORACLE_FILE = "oracle.out"
ORACLE_VALUE = "42\n"
ORACLE_COMMAND = "true " + AMP + " echo $((6*7)) >" + ORACLE_FILE + ";"
SWAPS = ("sleep 0.1 " + AMP, "sleep 100 " + AMP)
# The cases the bash oracle runs (check 4), by kind: runs (bash executes the backgrounded command, and
# the hook must deny), inert (bash does not execute it), residual (bash executes it and the hook allows
# it, as the residual discloses). Shells absent from a plain runner (zsh, ksh) are left out.
ORACLE_CASES = {
    "d01-bash-single-quoted-delimiter": "runs",
    "d02-sh-double-quoted-delimiter": "runs",
    "d03-env-bash": "runs",
    "d04-absolute-bin-bash": "runs",
    "d05-body-with-several-commands": "runs",
    "d08-cat-piped-to-bash": "runs",
    "d10-nested-shell-heredoc-in-body": "runs",
    "d12-command-wrapper-bash-s": "runs",
    "d17-pipe-newline-later-shell": "runs",
    "d18-pipe-newline-blank-and-comment-lines": "runs",
    "d19-stderr-pipe-newline": "runs",
    "d20-pipe-newline-through-later-stages": "runs",
    "d21-pipe-newline-inside-shell-body": "runs",
    "d22-unquoted-data-heredoc-substitution-in-body": "runs",
    "d23-unquoted-data-heredoc-backquote-in-body": "runs",
    "d24-unquoted-data-heredoc-substitution-inside-literal-quotes": "runs",
    "d25-unquoted-data-heredoc-parameter-expansion-in-body": "runs",
    "d26-unquoted-heredoc-fed-to-shell-in-body": "runs",
    "d27-unquoted-heredoc-piped-to-shell-in-body": "runs",
    "d28-unquoted-tab-strip-heredoc-fed-to-shell-in-body": "runs",
    "d29-recursive-quoted-unquoted-quoted": "runs",
    "d30-unquoted-heredoc-in-substitution-in-body": "runs",
    "d31-shell-heredoc-in-substitution-of-unquoted-body": "runs",
    "d32-piped-shell-body-with-unquoted-nested-substitution": "runs",
    "d34-backslash-newline-inside-nested-delimiter": "runs",
    "d35-quoted-heredoc-piped-to-while-running-a-shell": "runs",
    "d36-quoted-heredoc-piped-to-if-running-a-shell": "runs",
    "d37-quoted-heredoc-piped-to-case-running-a-shell": "runs",
    "d38-quoted-heredoc-piped-to-for-running-a-shell": "runs",
    "d39-bash-c-with-a-substitution": "runs",
    "d40-echo-substitution-piped-to-bash": "runs",
    "d41-partly-quoted-delimiter": "runs",
    "d42-ansi-c-quoted-delimiter": "runs",
    "d43-operator-split-by-a-line-continuation": "runs",
    "d44-shell-name-split-by-quotes": "runs",
    "d45-shell-variable": "runs",
    "a02-cat-to-stdout-data": "inert",
    "a19-pipe-newline-to-non-shell": "inert",
    "o05-script-written-to-file-with-a-shebang": "inert",
    "o06-double-ampersand-newline-then-separate-shell": "inert",
    "o08-unquoted-data-heredoc-escaped-substitutions": "inert",
    "o10-quoted-nested-data-heredoc-substitution-text": "inert",
    "a32-residual-here-string-not-judged": "residual",
    "a33-residual-eval-without-shell-name": "residual",
}
KIND_EXPECTS = {"runs": ("deny",), "inert": ("allow", "over"), "residual": ("allow",)}


def load_cases(path=CASES):
    """The (expect, name, command) cases of the case file, in order; raises ValueError on a malformed file."""
    cases, current = [], None
    with open(path, encoding="ascii") as handle:
        for line in handle.read().split("\n"):
            if line.startswith("=== "):
                parts = line[4:].split(" ")
                if len(parts) != 2 or parts[0] not in EXPECTS:
                    raise ValueError("malformed case header: " + line)
                current = [parts[0], parts[1], []]
                cases.append(current)
            elif current is None:
                if line and not line.startswith("#"):
                    raise ValueError("text before the first case: " + line)
            else:
                current[2].append(line)
    out, names = [], set()
    for expect, name, lines in cases:
        while lines and lines[-1] == "":
            lines.pop()
        if not lines:
            raise ValueError("empty case " + name)
        if name in names:
            raise ValueError("duplicate case name " + name)
        names.add(name)
        out.append((expect, name, "\n".join(lines).replace("<TAB>", "\t") + "\n"))
    if not out:
        raise ValueError("no cases in " + path)
    return out


def run_hook(hook, command, cwd=None):
    """The hook verdict for one Bash command: deny, allow-note, allow, or a string starting with error."""
    payload = {"session_id": "test", "hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": cwd or ROOT}
    proc = subprocess.run([sys.executable, "-I", hook], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=60, cwd=cwd or ROOT)
    if proc.returncode == 2:
        return "deny"
    if proc.returncode != 0:
        return "error: exit {} stderr {}".format(proc.returncode, proc.stderr.strip())
    out = proc.stdout.strip()
    if not out:
        return "allow"
    try:
        obj = json.loads(out)
    except ValueError:
        return "error: stdout is not JSON: " + out
    decision = (obj.get("hookSpecificOutput") or {}).get("permissionDecision")
    if decision == "deny":
        return "deny"
    if decision is not None:
        return "error: unexpected permissionDecision {}".format(decision)
    return "allow-note" if obj.get("systemMessage") else "allow"


def expected_ok(expect, verdict):
    if expect in ("deny", "over"):
        return verdict == "deny"
    return verdict in ("allow", "allow-note")


def check_cases(hook, cases):
    failures = []
    for expect, name, command in cases:
        verdict = run_hook(hook, command)
        status = "ok" if expected_ok(expect, verdict) else "FAIL"
        print("{:4} {:6} {:10} {}".format(status, expect, verdict, name))
        if status != "ok":
            failures.append(name)
    return failures


def check_payloads(hook):
    """The disclosed unreadable-payload handling: allowed with a note."""
    failures = []
    for label, raw in (("not JSON", "{not json"), ("no command string",
                       json.dumps({"tool_name": "Bash", "tool_input": {"command": 7}}))):
        proc = subprocess.run([sys.executable, "-I", hook], input=raw, capture_output=True, text=True,
                              timeout=60, cwd=ROOT)
        try:
            obj = json.loads(proc.stdout)
        except ValueError:
            obj = {}
        message = str(obj.get("systemMessage", ""))
        ok = (proc.returncode == 0 and "hookSpecificOutput" not in obj
              and ("could not be read" in message or "no command string" in message))
        print("{:4} payload {}".format("ok" if ok else "FAIL", label))
        if not ok:
            failures.append("unreadable payload ({}) was not allowed with a note".format(label))
    return failures


def flipped_hook(workdir):
    """A copy of the hook, laid out under workdir as in the repository, with the deny rule removed."""
    with open(HOOK, encoding="ascii") as handle:
        lines = handle.read().split("\n")
    marked = [k for k, line in enumerate(lines) if line.rstrip().endswith(MARK)]
    if len(marked) != 1:
        raise ValueError("expected exactly one {} line, found {}".format(MARK, len(marked)))
    line = lines[marked[0]]
    lines[marked[0]] = line[:len(line) - len(line.lstrip())] + "pass  # DENY-RULE removed by the flip"
    target = os.path.join(workdir, *HOOK_REL)
    os.makedirs(os.path.dirname(target))
    with open(target, "w", encoding="ascii") as handle:
        handle.write("\n".join(lines))
    return target


def check_flip(cases):
    """Every deny and over case must come back allowed from the flipped hook."""
    failures, red, total = [], 0, 0
    workdir = tempfile.mkdtemp(prefix="shdg-flip-")
    try:
        hook = flipped_hook(workdir)
        for expect, name, command in cases:
            if expect == "allow":
                continue
            total += 1
            verdict = run_hook(hook, command)
            turned_red = verdict in ("allow", "allow-note")
            red += turned_red
            print("{:4} flip {:10} {}".format("red" if turned_red else "FAIL", verdict, name))
            if not turned_red:
                failures.append("flip did not turn " + name + " red")
    finally:
        shutil.rmtree(workdir)
    if red == 0:
        failures.append("the flip turned no deny case red")
    return failures, red, total


def oracle_executed(bash, command):
    """(executed, detail): executed only when bash exits 0 and the file oracle.out holds exactly 42."""
    workdir = tempfile.mkdtemp(prefix="shdg-oracle-")
    try:
        proc = subprocess.run([bash, "-c", command], capture_output=True, text=True, timeout=30,
                              cwd=workdir, stdin=subprocess.DEVNULL)
        path = os.path.join(workdir, ORACLE_FILE)
        content = None
        if os.path.isfile(path) and not os.path.islink(path):
            with open(path, encoding="ascii", errors="replace") as handle:
                content = handle.read()
    finally:
        shutil.rmtree(workdir)
    executed = proc.returncode == 0 and content == ORACLE_VALUE
    return executed, "exit {}, {} {!r}".format(proc.returncode, ORACLE_FILE, content)


def check_oracle_self(bash):
    """Check 3: the oracle counts real execution only."""
    q = APOS
    probes = (
        ("positive control", ORACLE_COMMAND + "\n", True),
        ("syntax-error body (unclosed parenthesis)",
         "bash <<" + q + "EOF" + q + "\n( " + ORACLE_COMMAND + "\nEOF\n", False),
        ("syntax-error body (if without then)",
         "bash <<" + q + "EOF" + q + "\nif " + ORACLE_COMMAND + "\nEOF\n", False),
        ("the marker command echoed as text", "echo " + q + ORACLE_COMMAND + q + "\n", False),
        ("the marker command echoed to stderr", "echo " + q + ORACLE_COMMAND + q + " 1>" + AMP + "2\n", False),
        ("executed, then a non-zero exit", ORACLE_COMMAND + " false\n", False),
        ("escaped substitution in an unquoted body",
         "cat <<INNER\n\\$(" + ORACLE_COMMAND + ")\nINNER\n", False),
    )
    failures = []
    for label, command, want in probes:
        executed, detail = oracle_executed(bash, command)
        ok = executed == want
        print("{:4} oracle self-test {:8} {} ({})".format("ok" if ok else "FAIL",
                                                         "executed" if executed else "inert", label, detail))
        if not ok:
            failures.append("oracle self-test: {} counted {}".format(label, "executed" if executed else "inert"))
    return failures


def check_oracle(cases, hook, bash):
    """Check 4: each ORACLE_CASES case is present with an expectation its kind allows, and bash executes
    its backgrounded command exactly when its kind says so."""
    failures, by_name = [], {name: (expect, command) for expect, name, command in cases}
    for name, kind in sorted(ORACLE_CASES.items()):
        if name not in by_name:
            failures.append("oracle case missing from the case file: " + name)
            continue
        expect, command = by_name[name]
        if expect not in KIND_EXPECTS[kind]:
            failures.append("oracle case {} is {} but the case file expects {}".format(name, kind, expect))
            continue
        swapped = command
        for old in SWAPS:
            swapped = swapped.replace(old, ORACLE_COMMAND)
        if swapped == command:
            failures.append("oracle case {} has no backgrounded sleep to replace".format(name))
            continue
        executed, detail = oracle_executed(bash, swapped)
        verdict = run_hook(hook, command)
        want = kind in ("runs", "residual")
        ok = executed == want and expected_ok(expect, verdict)
        print("{:4} oracle {:8} bash {:12} hook {:6} {} ({})".format(
            "ok" if ok else "FAIL", kind, "executed it" if executed else "did not", verdict, name, detail))
        if not ok:
            failures.append("oracle case {} ({}): bash {}, hook {}".format(
                name, kind, "executed it" if executed else "did not execute it", verdict))
    return failures


def main():
    cases = load_cases()
    failures = check_cases(HOOK, cases)
    failures += check_payloads(HOOK)
    flip_failures, red, total = check_flip(cases)
    failures += flip_failures
    bash = shutil.which("bash")
    if bash is None:
        failures.append("bash is not on PATH, so the oracle cannot run")
    else:
        failures += check_oracle_self(bash)
        failures += check_oracle(cases, HOOK, bash)
    counts = {e: sum(1 for x, _n, _c in cases if x == e) for e in EXPECTS}
    print("cases {} (deny {}, over {}, allow {}), deny and over cases turned red by the flip {} of {}, "
          "oracle cases {}, failures {}".format(len(cases), counts["deny"], counts["over"], counts["allow"],
                                                red, total, len(ORACLE_CASES), len(failures)))
    for failure in failures:
        print("FAILURE: " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
