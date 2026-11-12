#!/usr/bin/env python3
"""Test that tools/run_all_checks.sh runs the run text read here, unpiped, and fails on a failure.

Coverage. The test reads each file directly under .github/workflows whose name ends in .yml or .yaml
with PyYAML's safe loader (which reads the key on as True). From the on: value of each it selects
those that a pull request or a push to main triggers: a pull_request or pull_request_target trigger,
or a push trigger whose branches name main or hold a pattern (an entry with any of the characters *
? [ ] + !), which counts as matching main whatever it matches, or that has no branches,
branches-ignore or tags filter, or whose branches-ignore does not name main. Of a selected workflow
it reads the defaults and jobs keys, the uses, defaults and steps keys of each job, and the run and
working-directory keys of each step. Each run text, with surrounding white space stripped, must be a
command line of the script or one of EXCEPTIONS, and a failure names the workflow and the step. A
file whose reading raises an error fails, naming the file, and its steps are not compared. Such
files include one that cannot be opened, decoded as UTF-8 or loaded as 1 YAML document, and one in
which the document, jobs, a job or a step is not a mapping, steps is not a list, or the on: value is
none of a string, a list and a mapping; a jobs, job or steps value that is null, false, zero or
empty is read as holding nothing. 9 reading cases require this of 1 file of each of those kinds. A
folder that the test cannot list fails, naming it, and the comparison reads none of it, since a glob
of such a folder finds no file; 2 reading cases require this of a path that names nothing and of a
file. The behaviour cases below open plugin-validate.yml by its path, which needs no listing of the
folder, so a folder that can be entered but not listed still gives them that file. Since the script
runs each command from the repository root, a job with a uses key, which calls a reusable workflow
whose steps the test does not read, a run step with a working-directory, and a defaults key on the
workflow or on a job each fail, naming the workflow. A command line is the text after "run " on a
line of the script that starts with it, or the text before " || status=1" on a line of
plugin_manifests that starts with "  claude ", a line being the text between line feeds, as bash
reads the script, so a carriage return or another character that Python reads as a line end stays in
it; a reading case requires that. A command line that is neither such a run text nor the stand-in of
an exception fails, so does a command line that repeats, and so does an entry of EXCEPTIONS that
names no step of a selected workflow.

Behaviour. Each case copies the script into a temporary tree whose tools/ folder holds a stub in
place of each script a command line names, beside a copy of plugin-validate.yml and a skill folder
for the staged validation, and runs it with bash as a separate process. A stub records its name, its
arguments, and whether its standard output and standard error are pipes, and exits with the code the
case sets; a stub claude on PATH answers --version with the version the case sets. The script's own
output goes to regular files, so a stub sees a pipe only when the script makes one. PATH holds only
links to the commands the script and the stubs use, and to cat and tee, so a claude installed on
this machine never takes part. In every case no stub's standard output or standard error is a pipe,
apart from those of claude --version, whose output the script reads. The cases: the command lines
each run once, in order, and the script exits 0; the same holds when the script is started by a
relative path with CDPATH naming another folder that holds a tools folder; a stub exiting 1, 2 or 3
(the first, a middle and the last stub) leaves the later commands running and the script exiting 1,
naming that command; a stub claude whose validation of the repository root, of ./cleanlanguage or of
the staged skills folder exits 1 makes the script exit 1, naming plugin_manifests, while the other
validations and the other commands each run once, in order; a claude that reports another version,
or no claude, makes the script exit 1, naming plugin_manifests, without any validation, while the
other commands each run once, in order. The cases read plugin-validate.yml once, for that copy and
for the version that its CLAUDE_CODE_VERSION line pins, matched as the sed of plugin_manifests
matches it, on each line between line feeds, so a line that ends in a carriage return is not such a
line; when it cannot be read or holds no such line or more than 1, the test fails, naming it and the
cause, and runs none of these cases, and 5 reading cases require that failure of a folder, of a file
with no such line, of a file with carriage returns, of a version that starts with a dot and of a
file with 2 such lines.

The cases pin the commands, not the script's other shell text, so the test also fails unless the
sha256 of the committed script is SCRIPT_SHA256. To change the script, read the whole change,
confirm that it still runs every command line unpiped and keeps going after a failure, then record
the new digest in SCRIPT_SHA256 in the same pull request.

Residual: the test reads the run text, not what each command does. A key that the test does not
read, on the workflow, a job or a step, can set what a step runs in, or whether, when or for how
long it runs, such as its shell, runner, container, condition, environment (GH_TOKEN for the live
release checksum check), time limit or paths filter; the script runs the run text with bash, from
the repository root, in this machine's environment and on every change, whatever such a key sets,
and the test passes it. A run text is compared whole, so the same command written another way in a
workflow is reported as missing, a safe failure. A pull_request trigger selects its workflow
whatever its filters, and a branches-ignore entry is compared with main as text, so a pattern that
excludes main, such as ma*, still selects its workflow; the run text of a workflow so selected must
then be a command line, a safe failure. A file that the test does not read, a step without run text,
such as one that runs a gate through an action (uses: rather than run:), and a workflow that the
selection above does not select, such as one that only another workflow's run triggers
(workflow_run), are not compared, so the script is not required to run what they run.

Exit 0 when every case passes; 1 otherwise, naming each failing case. An error outside the reading
of a workflow file, such as a missing tools/run_all_checks.sh, ends the test with a traceback and
exit 1, after the failures found before it are printed.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "run_all_checks.sh"
# The sha256 of the committed bytes of SCRIPT; a reviewer records a new digest only after reading
# the change to SCRIPT.
SCRIPT_SHA256 = "51ee5f1528b4a13e98228dfde9f2b758ca3cf98c4fa846d8339dc2e4d4b11cad"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PIN_WORKFLOW = WORKFLOWS / "plugin-validate.yml"
STAGED_RUN = "\n".join((
    "set -euo pipefail",
    'staged="$(mktemp -d)"',
    'mkdir -p "${staged}/skills"',
    'cp -r cleanlanguage/skills/cleanlanguage "${staged}/skills/cleanlanguage"',
    'claude plugin validate "${staged}/skills" --strict',
))
# (workflow, run text): the command line of the script that stands in for that step, and why.
EXCEPTIONS = {
    ("plugin-validate.yml", 'npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"'):
        ("plugin_manifests", "the script installs nothing; it checks the pinned version instead"),
    ("plugin-validate.yml", "claude --version"):
        ("plugin_manifests", "the script reads claude --version and compares it with the pin"),
    ("plugin-validate.yml", STAGED_RUN):
        ('claude plugin validate "${staged}/skills" --strict', "the script stages the skill the same way"),
}
RUN_LINE = re.compile(r"run (.+)")
CLAUDE_LINE = re.compile(r"  (claude .+) \|\| status=1")
# The line of plugin-validate.yml that pins the CLI, as the sed of plugin_manifests matches it: a
# whole line between line feeds, so a carriage return before the line feed is part of the line.
PIN_LINE = re.compile(r'  CLAUDE_CODE_VERSION: "([0-9][0-9.]*)"')
# The commands the script and the stubs need on PATH, and cat and tee, so a script that pipes a
# command through either still runs and the pipe check, not a missing command, is what refuses it.
NEEDED = ("bash", "python3", "sed", "mktemp", "mkdir", "cp", "rm", "dirname", "env", "cat", "tee")


# The characters of GitHub's branch filter patterns; a branches entry holding any of them counts as
# matching main, a safe failure when it does not.
PATTERN = set("*?[]+!")


def names_main(branches) -> bool:
    """True when a branches filter names main or holds a pattern."""
    if isinstance(branches, str):
        branches = [branches]
    return any(b == "main" or (isinstance(b, str) and PATTERN & set(b)) for b in branches or [])


def selected(on) -> bool:
    """True when a pull request or a push to main triggers a workflow with this on: value."""
    if isinstance(on, str):
        on = {on: None}
    elif isinstance(on, list):
        on = {name: None for name in on}
    if not isinstance(on, dict):
        return False
    if "pull_request" in on or "pull_request_target" in on:
        return True
    if "push" not in on:
        return False
    push = on["push"] or {}
    if not isinstance(push, dict):
        return True
    if "branches" in push:
        return names_main(push["branches"])
    if "branches-ignore" in push:
        ignore = push["branches-ignore"]
        if isinstance(ignore, str):
            ignore = [ignore]
        return "main" not in (ignore or [])
    return "tags" not in push


def need(value, kinds: tuple, what: str):
    """value, or a TypeError naming what when value is none of kinds."""
    if not isinstance(value, kinds):
        raise TypeError(f"{what} is of type {type(value).__name__}, not {' or '.join(k.__name__ for k in kinds)}")
    return value


def read_workflow(path: Path):
    """None when the workflow at path is not selected; otherwise (failures, run steps) for it. It
    raises on a file that it cannot read; a document, jobs value or job that is not a mapping raises
    where this function reads it as one, and a steps value that is not a list raises when iterated
    or yields an item that is not a mapping, which need refuses."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not selected(need(doc.get(True, doc.get("on")), (str, list, dict), "the on: value")):
        return None
    failures, steps = [], []
    if "defaults" in doc:
        failures.append(f"{path.name}: a defaults key, which can move its run steps out of the repository root")
    for job_id, job in (doc.get("jobs") or {}).items():
        job = job or {}
        if "uses" in job:
            failures.append(f"{path.name} job {job_id}: it calls the reusable workflow {job['uses']!r}, whose "
                            "steps this test does not read")
        if "defaults" in job:
            failures.append(f"{path.name} job {job_id}: a defaults key, which can move its run steps out of the "
                            "repository root")
        for index, step in enumerate(job.get("steps") or []):
            if "run" in need(step, (dict,), f"step {index} of job {job_id}"):
                if "working-directory" in step:
                    failures.append(f"{path.name} job {job_id} step {index}: it runs in "
                                    f"{step['working-directory']!r}, not the repository root")
                steps.append((path.name, job_id, index, str(step["run"]).strip()))
    return failures, steps


def workflow_steps(failures: list, folder: Path = WORKFLOWS):
    """(workflow, job, step index, run text) for each run step of each selected workflow of folder,
    and the count of selected workflows. A reusable workflow call, a working-directory or a defaults
    key in a selected workflow is added to failures, and so is each file that cannot be read. A
    folder that cannot be listed is added to failures, and nothing of it is read, since a glob of
    such a folder finds no file and raises nothing."""
    steps, count = [], 0
    try:
        os.listdir(folder)
    except OSError as error:  # fail closed: a folder that cannot be listed fails, named
        failures.append(f"{folder}: this test cannot list the folder, so it fails closed: {type(error).__name__}: "
                        f"{' '.join(str(error).split())[:300]}")
        return steps, count
    for path in sorted([*folder.glob("*.yml"), *folder.glob("*.yaml")]):
        try:
            found = read_workflow(path)
        except Exception as error:  # fail closed: a file that cannot be read fails, named
            failures.append(f"{path.name}: this test cannot read it, so it fails closed: {type(error).__name__}: "
                            f"{' '.join(str(error).split())[:300]}")
            continue
        if found is not None:
            count += 1
            failures += found[0]
            steps += found[1]
    return steps, count


def command_lines(text: str) -> list:
    """The command lines of the script, in order, each line being the text between line feeds, as
    bash reads it."""
    found, inside = [], False
    for line in text.split("\n"):
        if line.startswith("plugin_manifests() {"):
            inside = True
        elif inside and line == "}":
            inside = False
        elif inside:
            m = CLAUDE_LINE.fullmatch(line)
            if m:
                found.append(m.group(1))
        else:
            m = RUN_LINE.fullmatch(line)
            if m:
                found.append(m.group(1))
    return found


def script_lines(path: Path = SCRIPT) -> list:
    """The command lines of the script at path, read from its bytes, so that no line end is
    translated before command_lines splits them."""
    return command_lines(path.read_bytes().decode("utf-8"))


def coverage(failures: list) -> tuple:
    steps, count = workflow_steps(failures)
    lines = script_lines()
    mirrored = set(lines)
    for line in sorted({l for l in lines if lines.count(l) > 1}):
        failures.append(f"the command line {line!r} repeats in tools/run_all_checks.sh")
    used = set()
    for workflow, job, index, run in steps:
        key = (workflow, run)
        if run in mirrored:
            used.add(run)
        elif key in EXCEPTIONS:
            stand_in = EXCEPTIONS[key][0]
            if stand_in not in mirrored:
                failures.append(f"{workflow} job {job} step {index}: its stand-in {stand_in!r} is not a command line")
            used.add(stand_in)
        else:
            failures.append(f"{workflow} job {job} step {index}: the run text {run!r} is not run by "
                            "tools/run_all_checks.sh")
    for key in EXCEPTIONS:
        if not any((w, r) == key for w, _, _, r in steps):
            failures.append(f"the exception for {key[0]} {key[1][:40]!r} names no step of a selected workflow")
    for line in lines:
        if line not in used:
            failures.append(f"the command line {line!r} of tools/run_all_checks.sh is no run text of a "
                            "selected workflow")
    return count, len(steps), lines


PY_STUB = '''import os, stat, sys
NAME = {name!r}
def pipe(fd):
    try:
        return stat.S_ISFIFO(os.fstat(fd).st_mode)
    except OSError:
        return False
with open(os.environ["RUN_ALL_CHECKS_LOG"], "a") as log:
    log.write("%s|%s|%d%d\\n" % (NAME, " ".join(sys.argv[1:]), pipe(1), pipe(2)))
codes = dict(item.split("=", 1) for item in os.environ.get("RUN_ALL_CHECKS_CODES", "").split())
sys.exit(int(codes.get(NAME, "0")))
'''
SH_STUB = '''#!/usr/bin/env bash
out=0; err=0
[ -p /dev/stdout ] && out=1
[ -p /dev/stderr ] && err=1
printf '%s|%s|%s%s\\n' {name} "$*" "$out" "$err" >> "$RUN_ALL_CHECKS_LOG"
code=0
for item in ${{RUN_ALL_CHECKS_CODES:-}}; do
  if [ "${{item%%=*}}" = {name} ]; then code="${{item#*=}}"; fi
done
exit "$code"
'''
CLAUDE_STUB = '''#!/usr/bin/env bash
out=0; err=0
[ -p /dev/stdout ] && out=1
[ -p /dev/stderr ] && err=1
printf 'claude|%s|%s%s\\n' "$*" "$out" "$err" >> "$RUN_ALL_CHECKS_LOG"
if [ "${1:-}" = --version ]; then printf '%s (Claude Code)\\n' "$CLAUDE_STUB_VERSION"; fi
if [ "${1:-}" = plugin ] && [ -n "${CLAUDE_STUB_FAIL:-}" ]; then
  case "${3:-}" in $CLAUDE_STUB_FAIL) exit 1 ;; esac
fi
exit 0
'''
# The validations of plugin_manifests, each a label and the pattern of its folder argument that
# CLAUDE_STUB_FAIL gives the stub claude, so that exactly that validation exits 1.
VALIDATIONS = (("the repository root", "."), ("./cleanlanguage", "./cleanlanguage"),
               ("the staged skills folder", "*/skills"))


def stub_name(line: str):
    """The tools/ script a command line runs and its arguments, or None for the plugin_manifests
    and claude lines."""
    words = line.split()
    if words[:2] == ["python3", "-I"] and len(words) > 2:
        return words[2], words[3:]
    if words[0] == "bash" and len(words) > 1:
        return words[1], words[2:]
    if words[0].startswith("tools/"):
        return words[0], words[1:]
    return None


def expected_calls(lines: list) -> list:
    """The calls the stubs record when every command passes, in order."""
    out = []
    for line in lines:
        if line == "plugin_manifests":
            out += ["claude|--version", "claude|plugin validate . --strict",
                    "claude|plugin validate ./cleanlanguage --strict", "claude|plugin validate STAGED --strict"]
        elif not line.startswith("claude "):
            name, args = stub_name(line)
            out.append(f"{name}|{' '.join(args)}")
    return out


def read_pin(failures: list, path: Path = PIN_WORKFLOW):
    """(bytes, version) of plugin-validate.yml, or of path, for the behaviour cases: its bytes and
    the version that its 1 CLAUDE_CODE_VERSION line pins, read as the sed of plugin_manifests reads
    it. None, with a failure that names the file and the cause, when it cannot be read or holds no
    such line or more than 1, where that sed would find no pin or more than 1."""
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except Exception as error:  # fail closed: a file that cannot be read fails, named
        failures.append(f"{path.name}: this test cannot read it for the behaviour cases, so it fails closed: "
                        f"{type(error).__name__}: {' '.join(str(error).split())[:300]}")
        return None
    pins = [m.group(1) for m in map(PIN_LINE.fullmatch, text.split("\n")) if m]
    if len(pins) != 1:
        failures.append(f"{path.name}: it holds {len(pins)} lines '  CLAUDE_CODE_VERSION: \"<version>\"', each read "
                        "between line feeds as the sed of tools/run_all_checks.sh reads it, not 1, so the "
                        "behaviour cases cannot run")
        return None
    return data, pins[0]


def make_tree(tmp: Path, lines: list, claude: bool, pin_bytes: bytes) -> dict:
    (tmp / "tools").mkdir()
    (tmp / ".github" / "workflows").mkdir(parents=True)
    (tmp / "cleanlanguage" / "skills" / "cleanlanguage").mkdir(parents=True)
    (tmp / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md").write_text("stub\n", encoding="utf-8")
    shutil.copy2(SCRIPT, tmp / "tools" / "run_all_checks.sh")
    (tmp / ".github" / "workflows" / "plugin-validate.yml").write_bytes(pin_bytes)
    for line in lines:
        stub = stub_name(line)
        if stub is None:
            continue
        path = tmp / stub[0]
        if path.suffix == ".py":
            path.write_text(PY_STUB.format(name=stub[0]), encoding="utf-8")
        else:
            path.write_text(SH_STUB.format(name=stub[0]), encoding="utf-8")
            path.chmod(0o755)
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    for name in NEEDED:
        found = shutil.which(name)
        if found is None:
            raise RuntimeError(f"{name} is not on PATH")
        (bin_dir / name).symlink_to(os.path.realpath(found))
    if claude:
        (bin_dir / "claude").write_text(CLAUDE_STUB, encoding="utf-8")
        (bin_dir / "claude").chmod(0o755)
    return {"PATH": str(bin_dir), "HOME": str(tmp), "TMPDIR": str(tmp), "RUN_ALL_CHECKS_LOG": str(tmp / "log")}


def run_case(lines: list, pinned: tuple, codes: str = "", version=None, claude: bool = True,
             cdpath: bool = False, fail: str = ""):
    """Run the script in a stub tree: (exit status, log lines, script output). With cdpath, the
    script is started by a relative path from the tree, with CDPATH naming another folder that holds
    a tools folder, where a cd that consulted CDPATH would land. With fail, the validation of the
    stub claude whose folder argument matches that pattern exits 1."""
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        env = make_tree(tmp, lines, claude, pinned[0])
        env["RUN_ALL_CHECKS_CODES"] = codes
        env["CLAUDE_STUB_VERSION"] = version if version is not None else pinned[1]
        env["CLAUDE_STUB_FAIL"] = fail
        (tmp / "log").write_text("", encoding="utf-8")
        argv, cwd = ["bash", str(tmp / "tools" / "run_all_checks.sh")], "/"
        if cdpath:
            (tmp / "elsewhere" / "tools").mkdir(parents=True)
            env["CDPATH"] = str(tmp / "elsewhere")
            argv, cwd = ["bash", "tools/run_all_checks.sh"], str(tmp)
        with open(tmp / "out", "wb") as out, open(tmp / "err", "wb") as err:
            code = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                  timeout=300).returncode
        log = (tmp / "log").read_text(encoding="utf-8").splitlines()
        output = ((tmp / "out").read_bytes() + (tmp / "err").read_bytes()).decode("utf-8", "replace")
        log = [re.sub(r"plugin validate \S+/skills --strict", "plugin validate STAGED --strict", l) for l in log]
        return code, log, output


def calls(log: list) -> list:
    return [entry.rsplit("|", 1)[0] for entry in log]


def piped(log: list) -> list:
    """The calls whose standard output or standard error was a pipe, apart from claude --version,
    whose output the script reads."""
    return [e.rsplit("|", 1)[0] for e in log if e.rsplit("|", 1)[1] != "00" and not e.startswith("claude|--version|")]


def behaviour(lines: list, failures: list, pinned: tuple) -> int:
    cases = 0
    stubs = [l for l in lines if stub_name(l) is not None]
    if not stubs:
        failures.append("tools/run_all_checks.sh has no command line to stub")
        return 0
    want = expected_calls(lines)

    cases += 1
    code, log, output = run_case(lines, pinned)
    if code != 0:
        failures.append(f"every command passing: the script exits {code}, not 0\n{output[-2000:]}")
    if calls(log) != want:
        failures.append(f"every command passing: the calls are {calls(log)!r}, not {want!r}")
    if piped(log):
        failures.append(f"every command passing: a pipe reached {piped(log)!r}")

    cases += 1
    code, log, output = run_case(lines, pinned, cdpath=True)
    label = "a CDPATH naming another tools folder"
    if code != 0 or calls(log) != want:
        failures.append(f"{label}: the script exits {code} with the calls "
                        f"{calls(log)!r}, not 0 with every command once in order\n{output[-2000:]}")
    if piped(log):
        failures.append(f"{label}: a pipe reached {piped(log)!r}")

    for status, line in ((1, stubs[0]), (2, stubs[len(stubs) // 2]), (3, stubs[-1])):
        cases += 1
        name = stub_name(line)[0]
        code, log, output = run_case(lines, pinned, codes=f"{name}={status}")
        label = f"{name} exiting {status}"
        if code != 1:
            failures.append(f"{label}: the script exits {code}, not 1")
        if calls(log) != want:
            failures.append(f"{label}: the calls are {calls(log)!r}, not every command once in order")
        if f"==> exit {status}: {line}" not in output or f"  {line} (exit {status})" not in output:
            failures.append(f"{label}: the output does not name the failed command {line!r}")
        if piped(log):
            failures.append(f"{label}: a pipe reached {piped(log)!r}")

    plugin = [l for l in lines if l == "plugin_manifests"]
    for folder, pattern in VALIDATIONS:
        cases += 1
        code, log, output = run_case(lines, pinned, fail=pattern)
        label = f"a validation of {folder} exiting 1"
        if code != 1:
            failures.append(f"{label}: the script exits {code}, not 1")
        if calls(log) != want or not plugin:
            failures.append(f"{label}: the calls are {calls(log)!r}, not every command and validation once in "
                            "order, or no plugin_manifests runs")
        if "==> exit 1: plugin_manifests" not in output or "  plugin_manifests (exit 1)" not in output:
            failures.append(f"{label}: the output does not name plugin_manifests as failed")
        if piped(log):
            failures.append(f"{label}: a pipe reached {piped(log)!r}")

    for label, kwargs in (("a claude reporting another version", {"version": pinned[1] + "1"}),
                          ("no claude", {"claude": False})):
        cases += 1
        code, log, output = run_case(lines, pinned, **kwargs)
        validations = [c for c in calls(log) if c.startswith("claude|plugin validate")]
        if code != 1:
            failures.append(f"{label}: the script exits {code}, not 1")
        if validations or not plugin:
            failures.append(f"{label}: the script ran {validations!r}, or runs no plugin_manifests")
        if "==> exit 1: plugin_manifests" not in output:
            failures.append(f"{label}: the output does not name plugin_manifests as failed")
        others = [c for c in calls(log) if not c.startswith("claude|")]
        if others != [c for c in want if not c.startswith("claude|")]:
            failures.append(f"{label}: the other commands did not all run once in order")
        if piped(log):
            failures.append(f"{label}: a pipe reached {piped(log)!r}")
    return cases


# Files that this test cannot read, 1 of each kind: (file name, its bytes, or None for a folder of
# that name). Each must add exactly 1 failure, which names it, and no run step.
UNREADABLE = (
    ("folder.yml", None),
    ("not-utf-8.yml", b"on: pull_request\njobs: {}\n# \xff\n"),
    ("not-yaml.yml", b"on: [pull_request\n"),
    ("document-list.yml", b"- on: pull_request\n"),
    ("no-on.yml", b"jobs: {}\n"),
    ("jobs-list.yml", b"on: pull_request\njobs:\n  - check\n"),
    ("job-list.yml", b"on: pull_request\njobs:\n  check:\n    - run: x\n"),
    ("steps-text.yml", b"on: pull_request\njobs:\n  check:\n    steps: echo x\n"),
    ("step-text.yml", b"on: pull_request\njobs:\n  check:\n    steps:\n      - echo x\n"),
)
# Files of UNREADABLE from which read_pin must take no pin: a folder, which it cannot read, and a
# file with no CLAUDE_CODE_VERSION line. Each must add exactly 1 failure, which names it.
NO_PIN = ("folder.yml", "no-on.yml")
# Files from which the sed of plugin_manifests takes no pin or 2, though a reading that ignored a
# carriage return, took a version that starts with a dot or took the first match would take 1, each
# a file name and its bytes. read_pin must take no pin from each, adding exactly 1 failure, which
# names the file.
SED_NO_PIN = (
    ("crlf.yml", b'env:\r\n  CLAUDE_CODE_VERSION: "2.1.310"\r\n'),
    ("dot-first.yml", b'env:\n  CLAUDE_CODE_VERSION: ".2.1"\n'),
    ("two-pins.yml", b'env:\n  CLAUDE_CODE_VERSION: "2.1.310"\n  CLAUDE_CODE_VERSION: "2.1.311"\n'),
)
# A script whose lines hold a carriage return and a vertical tab, which bash keeps inside a line,
# and the command lines that script_lines must read from it.
SCRIPT_CASE = (b"run python3 -I tools/x.py\r\nrun bash tools/y.sh\x0bz\n",
               ["python3 -I tools/x.py\r", "bash tools/y.sh\x0bz"])
# Paths that workflow_steps cannot list as a folder, 1 of each kind: (name, the bytes of a file of
# that name, or None for a path that names nothing). Each must add exactly 1 failure, which names
# it, and no run step.
UNLISTABLE = (("no-folder", None), ("file-folder", b"on: pull_request\n"))
READING_CASES = len(UNREADABLE) + len(NO_PIN) + len(SED_NO_PIN) + len(UNLISTABLE) + 1


def reading(failures: list) -> int:
    """Run workflow_steps on a folder that holds the files of UNREADABLE and on each path of
    UNLISTABLE in a folder below it, read_pin on each file of NO_PIN in it and of SED_NO_PIN in
    another folder below it, and script_lines on the script of SCRIPT_CASE."""
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        for file_name, data in UNREADABLE:
            if data is None:
                (folder / file_name).mkdir()
            else:
                (folder / file_name).write_bytes(data)
        (folder / "pins").mkdir()
        for file_name, data in SED_NO_PIN:
            (folder / "pins" / file_name).write_bytes(data)
        for path in [*(folder / f for f in NO_PIN), *(folder / "pins" / f for f, _ in SED_NO_PIN)]:
            file_name, found = path.name, []
            try:
                pinned = read_pin(found, path)
            except Exception as error:
                failures.append(f"no pin in {file_name}: reading it raised {type(error).__name__}: {error}")
                continue
            if pinned is not None or len(found) != 1 or not found[0].startswith(f"{file_name}: "):
                failures.append(f"no pin in {file_name}: read_pin gave {pinned!r} and the failures {found!r}, "
                                "not None and 1 failure naming it")
        (folder / "unlisted").mkdir()
        for path_name, data in UNLISTABLE:
            path, found = folder / "unlisted" / path_name, []
            if data is not None:
                path.write_bytes(data)
            try:
                steps, count = workflow_steps(found, path)
            except Exception as error:
                failures.append(f"a folder that cannot be listed, {path_name}: reading it raised "
                                f"{type(error).__name__}: {error}")
                continue
            if steps or count or len(found) != 1 or not found[0].startswith(f"{path}: this test cannot list"):
                failures.append(f"a folder that cannot be listed, {path_name}: {count} selected, {len(steps)} run "
                                f"steps, failures {found!r}, not 1 failure naming it")
        (folder / "script.sh").write_bytes(SCRIPT_CASE[0])
        try:
            got = script_lines(folder / "script.sh")
        except Exception as error:
            got = f"an error, {type(error).__name__}: {error}"
        if got != SCRIPT_CASE[1]:
            failures.append(f"script lines holding a carriage return and a vertical tab: script_lines gave {got!r}, "
                            f"not {SCRIPT_CASE[1]!r}")
        found = []
        try:
            steps, count = workflow_steps(found, folder)
        except Exception as error:
            failures.append(f"files that cannot be read: reading them raised {type(error).__name__}: {error}")
            return READING_CASES
        for file_name, _ in UNREADABLE:
            named = [f for f in found if f.startswith(f"{file_name}: this test cannot read it")]
            if len(named) != 1:
                failures.append(f"a file that cannot be read, {file_name}: {len(named)} failures name it, not 1")
        if steps or count or len(found) != len(UNREADABLE):
            failures.append(f"files that cannot be read: {count} selected, {len(steps)} run steps, failures {found!r}")
    return READING_CASES


def main() -> int:
    failures = []
    try:
        digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        if digest != SCRIPT_SHA256:
            failures.append(f"tools/run_all_checks.sh has sha256 {digest}, not the reviewed {SCRIPT_SHA256}")
        reads = reading(failures)
        count, steps, lines = coverage(failures)
        pinned = read_pin(failures)
        cases = behaviour(lines, failures, pinned) if pinned is not None else 0
    finally:
        # The failures found so far print also when an error ends the test, so none is lost.
        for failure in failures:
            print(f"FAIL: {failure}", flush=True)
    if failures:
        return 1
    print(f"OK: {count} workflows, {steps} run steps, {len(lines)} command lines in tools/run_all_checks.sh, "
          f"{cases} behaviour cases, {reads} reading cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
