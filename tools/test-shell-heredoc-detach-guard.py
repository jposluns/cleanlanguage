#!/usr/bin/env python3
"""Tests for the adopter hook .claude/hooks/shell_heredoc_detach_guard.py (items 38 and 40, the
heredoc lifting reduction).

1. Every case in tools/shell-heredoc-detach-guard-cases.txt is sent to the hook as a PreToolUse Bash
   payload, and the verdict (deny, or allow with or without a note) must match the case.
2. The second reader the hook loads, the vendored lexer, must be reachable and must read a backgrounding
   ampersand and not a double ampersand.
3. The flip: a copy of the hook with its deny rule (the line marked DENY-RULE) removed must turn every
   deny case red (allowed), while the fail-closed denies still deny. A flip that changes nothing fails.
4. The bash oracle: every case named in ORACLE_CASES must be present with its expectation, and real bash
   must agree with it. Each such command is run by bash -c in a fresh directory with its backgrounded
   command (sleep, a number and an ampersand) replaced by a command that writes a marker to stderr and
   detaches nothing; the marker must appear exactly for the deny cases, so each deny is a body bash does
   run as commands (a pipeline continued past a newline, an unquoted nested body whose expansions run,
   an unquoted nested body fed to a shell) and each allow is one it does not.

Exit 0 only when all four hold. Launch with python3 -I. Temporary files go under TMPDIR.
"""

import importlib.util
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
VENDORED_REL = ("plugin", "aiqt-guardrails-hooks", "hooks", "scripts", "aiqt_hooks.py")
VENDORED = os.path.join(ROOT, *VENDORED_REL)
MARK = "# DENY-RULE"
EXPECTS = ("deny", "deny-closed", "allow")
# The cases the bash oracle runs (check 4): the line continuation of a pipeline past a newline, and every
# here-document nested in a shell-fed body, quoted or not, with its siblings that must stay allowed. An
# allow case whose body holds no backgrounded command (a21, a23, a25) has nothing for the oracle to run.
ORACLE_CASES = {
    "d17-pipe-newline-later-shell": "deny",
    "d18-pipe-newline-blank-and-comment-lines": "deny",
    "d19-stderr-pipe-newline": "deny",
    "d20-pipe-newline-through-later-stages": "deny",
    "d21-pipe-newline-inside-shell-body": "deny",
    "d22-unquoted-data-heredoc-substitution-in-body": "deny",
    "d23-unquoted-data-heredoc-backquote-in-body": "deny",
    "d24-unquoted-data-heredoc-substitution-inside-literal-quotes": "deny",
    "d25-unquoted-data-heredoc-parameter-expansion-in-body": "deny",
    "d26-unquoted-heredoc-fed-to-shell-in-body": "deny",
    "d27-unquoted-heredoc-piped-to-shell-in-body": "deny",
    "d28-unquoted-tab-strip-heredoc-fed-to-shell-in-body": "deny",
    "d29-recursive-quoted-unquoted-quoted": "deny",
    "d30-unquoted-heredoc-in-substitution-in-body": "deny",
    "d31-shell-heredoc-in-substitution-of-unquoted-body": "deny",
    "d32-piped-shell-body-with-unquoted-nested-substitution": "deny",
    "a19-pipe-newline-to-non-shell": "allow",
    "a20-double-ampersand-newline-then-separate-shell": "allow",
    "a22-unquoted-data-heredoc-escaped-substitutions": "allow",
    "a24-quoted-nested-data-heredoc-substitution-text": "allow",
}
ORACLE_MARK = "ORACLE-RAN"


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
    out = []
    for expect, name, lines in cases:
        while lines and lines[-1] == "":
            lines.pop()
        if not lines:
            raise ValueError("empty case " + name)
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
    if expect in ("deny", "deny-closed"):
        return verdict == "deny"
    return verdict in ("allow", "allow-note")


def check_cases(hook, cases):
    failures = []
    for expect, name, command in cases:
        verdict = run_hook(hook, command)
        status = "ok" if expected_ok(expect, verdict) else "FAIL"
        print("{:4} {:12} {:9} {}".format(status, expect, verdict, name))
        if status != "ok":
            failures.append(name)
    return failures


def check_vendored_reader():
    """The hook second reader: the vendored lexer must load and judge a backgrounding ampersand."""
    if not os.path.isfile(VENDORED):
        return ["vendored hook module absent at " + VENDORED]
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("_shdg_hook_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func, reason = module.vendored_lexer()
    if func is None:
        return ["vendored lexer unavailable: " + reason]
    amp, notes, failures = module.AMP, [], []
    if module.vendored_background("sleep 1 " + amp + "\n", notes) is not True:
        failures.append("vendored reader missed a backgrounding ampersand")
    if module.vendored_background("true " + amp + amp + " echo ok\n", notes) is not False:
        failures.append("vendored reader read a double ampersand as a background")
    if module.vendored_background("case x in x) echo a ;" + amp + " y) echo b ;; esac\n", notes) is not False:
        failures.append("vendored reader read a case fall-through terminator as a background")
    if module.vendored_background("(sleep 1) " + amp + "\n", notes) is not True:
        failures.append("vendored reader missed a backgrounded subshell")
    if notes:
        failures.append("vendored reader notes: " + "; ".join(notes))
    print("{:4} vendored second reader".format("ok" if not failures else "FAIL"))
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
    if os.path.isfile(VENDORED):
        vend = os.path.join(workdir, *VENDORED_REL)
        os.makedirs(os.path.dirname(vend))
        os.symlink(VENDORED, vend)
    return target


def check_flip(cases):
    """Every deny case must come back allowed from the flipped hook; every deny-closed case still denied."""
    failures, red = [], 0
    workdir = tempfile.mkdtemp(prefix="shdg-flip-")
    try:
        hook = flipped_hook(workdir)
        for expect, name, command in cases:
            if expect == "allow":
                continue
            verdict = run_hook(hook, command)
            if expect == "deny":
                turned_red = verdict in ("allow", "allow-note")
                red += turned_red
                print("{:4} flip {:9} {}".format("red" if turned_red else "FAIL", verdict, name))
                if not turned_red:
                    failures.append("flip did not turn " + name + " red")
            elif verdict != "deny":
                failures.append("flip changed the fail-closed case " + name)
    finally:
        shutil.rmtree(workdir)
    if red == 0:
        failures.append("the flip turned no deny case red")
    return failures, red


def check_oracle(cases):
    """Check 4: each ORACLE_CASES case is present with its expectation, and bash runs its backgrounded
    command exactly when the case is a deny."""
    failures, by_name = [], {name: (expect, command) for expect, name, command in cases}
    bash = shutil.which("bash")
    if bash is None:
        return ["bash is not on PATH, so the oracle cannot run"]
    amp = "\x26"
    marker = "echo {} >/dev/stderr".format(ORACLE_MARK)
    for name, expect in sorted(ORACLE_CASES.items()):
        if name not in by_name:
            failures.append("oracle case missing from the case file: " + name)
            continue
        if by_name[name][0] != expect:
            failures.append("oracle case {} expects {}, the case file says {}".format(
                name, expect, by_name[name][0]))
            continue
        command = by_name[name][1]
        swapped = command.replace("sleep 0.1 " + amp, marker).replace("sleep 100 " + amp, marker)
        if swapped == command:
            failures.append("oracle case {} has no backgrounded sleep to replace".format(name))
            continue
        workdir = tempfile.mkdtemp(prefix="shdg-oracle-")
        try:
            proc = subprocess.run([bash, "-c", swapped], capture_output=True, text=True, timeout=30,
                                  cwd=workdir, stdin=subprocess.DEVNULL)
        finally:
            shutil.rmtree(workdir)
        ran = ORACLE_MARK in proc.stderr
        ok = ran == (expect == "deny")
        print("{:4} oracle {:5} bash {:13} {}".format("ok" if ok else "FAIL", expect,
                                                      "ran it" if ran else "did not run it", name))
        if not ok:
            failures.append("bash {} the backgrounded command of {} ({})".format(
                "ran" if ran else "did not run", name, expect))
    return failures


def main():
    cases = load_cases()
    failures = check_cases(HOOK, cases)
    failures += check_vendored_reader()
    flip_failures, red = check_flip(cases)
    failures += flip_failures
    failures += check_oracle(cases)
    denies = sum(1 for expect, _n, _c in cases if expect == "deny")
    print("cases {}, deny cases turned red by the flip {} of {}, failures {}".format(
        len(cases), red, denies, len(failures)))
    for failure in failures:
        print("FAILURE: " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
