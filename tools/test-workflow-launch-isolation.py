#!/usr/bin/env python3
"""Check that every Python launch in .github/workflows runs isolated.

A Python-launched gate puts its own script folder first on the module path, so a
file beside the script can shadow a standard-library import and turn the gate into
a green run that checked nothing. `python3 -I` drops the script folder, the user
site directory and every PYTHON* variable. This check reads every workflow file as
text, line by line, and fails on:

- an interpreter word (`python`, `python3` or `python3.N`, with or without a path
  prefix, anywhere on a line that is not a comment) whose next word is not
  exactly `-I`;
- a `shell: python` step;
- a `tools/<name>.py` at the head of a command, which would run by its shebang
  line rather than under `python3 -I`;
- a launched `tools/<name>.py` that is missing or has a line starting with
  `sys.path.insert(`, which would put a folder back ahead of the standard
  library;
- fewer interpreter words than LAUNCH_FLOOR, so an empty or misread scan cannot
  pass.

It then plants a `tempfile.py` beside a copy of each script in SYS_PATH_SCRIPTS,
runs the copy under `-I`, and fails if the planted module ran.

It runs its own snippet self-tests first and stops on any mismatch. It fails
closed, naming the cause, when the workflow folder cannot be listed, a file cannot
be read as UTF-8, or no workflow is found.

Residuals (this is a text scan): it cannot see an interpreter held in a
variable, built by `bash -c`, or run by a composite or remote action; a launch
split across a backslash continuation reads as missing `-I` (the safe
direction); a `python3` word inside a string on a line that is not a comment is
flagged (the safe direction); a bare `tools/x.py` launched after `&&`, `;` or
`|` in the middle of a line is not seen; the `-P -E -s` equivalent of `-I` is
not accepted; a sys.path change written any other way than a line starting
with `sys.path.insert(` or `sys.path.append(` is not seen. The shell scripts the
workflows run are outside the scan. The floor is a floor: adding launches never
breaks it, removing them below it does, so lower it when launches are
deliberately removed.

Usage: python3 -I tools/test-workflow-launch-isolation.py
Exit status: 0 when every check passes, 1 on any finding or failure.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"

# The number of interpreter words in the workflows when this check landed.
LAUNCH_FLOOR = 51

# Launched scripts that append their own folder to sys.path to import a sibling.
SYS_PATH_SCRIPTS = (
    "tools/check-page-metadata.py",
    "tools/generate-sitemap.py",
    "tools/test-sitemap.py",
)

PLANT_MARKER = "PLANTED-MODULE-RAN"

INTERP = re.compile(r"(?<![\w./-])(?:/\S*/)?python(?:3(?:\.\d+)?)?(?![\w.-])")
AFTER = re.compile(r"\s+-I(?=\s|$|[\"')|;&>])")
# The script an interpreter word launches, after any options.
SCRIPT = re.compile(r"(?:\s+-[\w-]+)*\s+(?:\./)?(tools/[\w.-]+\.py)(?=\s|$|[\"')|;&>])")
# A script at the head of a command: an optional `run:` or `- run:`, `if`, `!`,
# plain VAR=value words and `$(` before it. An assignment value holds no quote,
# `$` or bracket, so it cannot swallow an interpreter word. A paths filter entry
# (`- "tools/x.py"` or `- tools/x.py`) never matches.
BARE = re.compile(
    r"^\s*(?:-\s+run:|run:)?\s*(?:if\s+)?(?:!\s*)?(?:\w+=[^\s\"'$`()]*\s+)*"
    r"(?:\$\()?(?:\./)?tools/[\w.-]+\.py(?=\s|$|[\"')|;&>])"
)
SHELL = re.compile(r"^\s*shell:\s*python")
# A statement that puts a folder on sys.path, at the start of a line of code.
PATH_INSERT = re.compile(r"^\s*sys\.path\.insert\(", re.MULTILINE)
PATH_APPEND = re.compile(r"^\s*sys\.path\.append\(", re.MULTILINE)


def scan_text(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str | None]]]:
    """Return (findings, launches) for one file's text, as (line, detail) pairs."""
    findings: list[tuple[int, str]] = []
    launches: list[tuple[int, str | None]] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if SHELL.match(line):
            findings.append((number, "shell: python step"))
            continue
        if BARE.match(line):
            findings.append((number, "a tools/*.py launched without python3 -I"))
        for match in INTERP.finditer(line):
            if AFTER.match(line, match.end()) is None:
                findings.append((number, "interpreter not followed by -I"))
            script = SCRIPT.match(line, match.end())
            launches.append((number, script.group(1) if script else None))
    return findings, launches


# (snippet, expected number of findings)
SELF_TESTS = [
    ("python3 tools/x.py", 1),
    ("/usr/bin/python3 tools/x.py", 1),
    ("python3.12 tools/x.py", 1),
    ("x=$(python3 tools/x.py)", 1),
    ('X="$(python3 tools/x.py)"', 1),
    ("cat f | python3 tools/x.py", 1),
    ("python3 -E tools/x.py", 1),
    ("python3 -P -E -s tools/x.py", 1),
    ("python3 -c 'print(1)'", 1),
    ("python3 -m tools.x", 1),
    ("python3 -Ic 'x'", 1),
    ("shell: python", 1),
    ("tools/x.py --flag", 1),
    ("./tools/x.py", 1),
    ("env python3 tools/x.py", 1),
    ('if ! v="$(python3 tools/x.py a)"; then', 1),
    ("python tools/x.py", 1),
    ("run: tools/x.py", 1),
    ("  - run: tools/x.py", 1),
    ("if ! tools/x.py; then", 1),
    ("X=1 tools/x.py", 1),
    ("python3 tools/a.py | python3 tools/b.py", 2),
    ("python3 -I tools/x.py", 0),
    ("# python3 tools/x.py", 0),
    ("run: python3 -I tools/x.py arg", 0),
    ('echo "see tools/x.py for details; tools/y.py too"', 0),
    ("- run: python3 -I tools/x.py", 0),
    ('  if ! v="$(python3 -I tools/x.py a)"; then', 0),
    ("git show X | python3 -I tools/x.py", 0),
    ('python3 -I tools/x.py --a "$(date -u +%Y)" >/dev/null || rc=$?', 0),
    ('  - "tools/x.py"', 0),
    ("  - tools/x.py", 0),
    ("python3 -I -c 'x'", 0),
    ("  # the Python gates", 0),
    ("run: bash tools/x.sh", 0),
    ("run: tools/x.sh", 0),
]


def self_test() -> list[str]:
    errors = []
    for snippet, want in SELF_TESTS:
        got = len(scan_text(snippet)[0])
        if got != want:
            errors.append(f"self-test: {snippet!r}: expected {want} finding(s), got {got}")
    sample = "run: python3 -I ./tools/x.py\nrun: python3 -I -c 'x'\npython3 -E tools/y.py"
    launches = scan_text(sample)[1]
    if launches != [(1, "tools/x.py"), (2, None), (3, "tools/y.py")]:
        errors.append(f"self-test: launch recording gave {launches!r}")
    return errors


def list_workflows() -> list[Path]:
    try:
        entries = sorted(os.listdir(WORKFLOWS))
    except OSError as exc:
        raise SystemExit(f"cannot list {WORKFLOWS}: {exc}") from exc
    files = [WORKFLOWS / name for name in entries if name.endswith((".yml", ".yaml"))]
    if not files:
        raise SystemExit(f"no workflow file found in {WORKFLOWS}")
    return files


def planted_module_runs(script: str) -> str | None:
    """Run a copy of `script` under -I beside a planted tempfile.py; describe a failure."""
    with tempfile.TemporaryDirectory() as tmp:
        tools = Path(tmp) / "tools"
        tools.mkdir()
        for source in (REPO / "tools").glob("*.py"):
            shutil.copy2(source, tools / source.name)
        (tools / "tempfile.py").write_text(
            f"import os\nos.write(1, b'{PLANT_MARKER}\\n')\nos._exit(97)\n", encoding="utf-8"
        )
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=tmp)
        try:
            run = subprocess.run(
                [sys.executable, "-I", "-B", str(tools / Path(script).name)],
                cwd=tmp, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"{script}: the planted-module run did not complete ({exc})"
        if PLANT_MARKER.encode() in run.stdout + run.stderr or run.returncode == 97:
            return f"{script}: a tempfile.py planted beside it ran under python3 -I"
    return None


def main() -> int:
    errors = self_test()
    if errors:
        for error in errors:
            print(error)
        return 1

    findings: list[str] = []
    launches: list[tuple[str, int, str | None]] = []
    for path in list_workflows():
        rel = path.relative_to(REPO)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{rel}: cannot be read as UTF-8 ({exc})")
            continue
        file_findings, file_launches = scan_text(text)
        findings += [f"{rel}:{number}: {reason}" for number, reason in file_findings]
        launches += [(str(rel), number, script) for number, script in file_launches]

    appenders = set()
    for rel, number, script in launches:
        if script is None:
            continue
        try:
            body = (REPO / script).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{rel}:{number}: launched script {script} cannot be read ({exc})")
            continue
        if PATH_INSERT.search(body):
            findings.append(f"{rel}:{number}: {script} inserts a folder into sys.path")
        if PATH_APPEND.search(body):
            appenders.add(script)
    for script in sorted(appenders - set(SYS_PATH_SCRIPTS)):
        findings.append(f"{script} appends to sys.path but is not in SYS_PATH_SCRIPTS")

    if len(launches) < LAUNCH_FLOOR:
        findings.append(f"only {len(launches)} Python launches found, below the floor of {LAUNCH_FLOOR}")

    for script in SYS_PATH_SCRIPTS:
        failure = planted_module_runs(script)
        if failure:
            findings.append(failure)

    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s), {len(launches)} launches")
        return 1
    print(f"OK: {len(launches)} Python launches in the workflows, every one isolated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
