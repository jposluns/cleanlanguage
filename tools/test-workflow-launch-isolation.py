#!/usr/bin/env python3
"""Check that every Python launch in .github/workflows runs isolated.

A Python-launched gate that finds a planted file on its module path can import
that file in place of a standard-library module and turn the gate into a green
run that checked nothing. `python3 -I` keeps the script folder off the module
path and ignores the user site directory and every PYTHON* variable.

This check is an allowlist over the text of every workflow file. It reads each
file as UTF-8, splits it on newlines only, and scans every line, comments
included. A file fails when:

- it holds a character that Python, YAML or some other reader treats as a line
  break where bash does not: carriage return, vertical tab, form feed, U+001C
  to U+001E, U+0085, U+2028 or U+2029;
- the text `python` appears anywhere except as an allowed launch;
- a `tools/<name>.py` appears anywhere except in an allowed launch, a paths
  filter entry, a comment line, or the double-quoted message of an `echo`;
- a `<name>.py` appears anywhere except in those places, or anywhere as
  `./<name>.py`;
- a line ending in a backslash is followed by a line starting with `#`, which
  would join the comment onto a command;
- a line that is not a comment leaves a shell quote open at its end;
- a `working-directory` names `tools`, or a step uses a local action outside
  .github/workflows;
- a launched script cannot be read, or changes sys.path in its code;
- there are fewer allowed launches than LAUNCH_FLOOR, so an empty or misread
  scan cannot pass.

An allowed launch is exactly `python3 -I tools/<name>.py`, followed by the end of
the line, a space or `)`, and preceded on its line by nothing but indentation,
`run: ` or `- run: `, or by `$(` or a single `| `. Only allowed launches count
toward the floor.

It then plants tempfile.py, msvcrt.py, nt.py and _winapi.py beside a copy of
each script in PROBE_SCRIPTS, runs the copy under `-I`, and fails if a planted
module ran.

It runs its own self-tests first and stops on any failure. They cover the line
rules, the floor, a read failure, a missing workflow folder, the sys.path
detector, the comment and continuation rules, and the planted-module probe,
each on a whole temporary tree.

Residuals. This is a text scan of the workflow files as they sit in the pull
request's own checkout, so it cannot see:

- a shell function or alias defined earlier under an obfuscated name and then
  called as `python3` (a definition that spells `python` is caught);
- a command assembled at run time, such as through `eval`, `bash -c` with
  built text, or an interpreter held in a variable;
- a composite action from another repository, or a remote action;
- a pull request that edits this scan, its floor or its workflow, which only
  review can catch;
- how GitHub parses the YAML: this scan reads lines, not YAML, so a YAML form
  that GitHub reads differently from its line text (for example escapes in a
  double-quoted scalar) is judged by its line text;
- a launch made by a shell script the workflows run, or through a launcher
  that names no `.py` path (such as `pytest` with no path, `py`, `uv run` or
  `pipx`);
- an allowed launch in text bash never runs, such as a here-document, which
  still counts toward the floor;
- a sys.path change made other than by a statement on `sys.path` or
  `from sys import path`, such as through getattr or an imported alias.

The floor is a floor: adding launches never breaks it, removing them below it
does, so lower it when launches are deliberately removed.

Usage: python3 -I tools/test-workflow-launch-isolation.py
Exit status: 0 when every check passes, 1 on any finding or failure.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The number of allowed launches in the workflows when this check landed.
LAUNCH_FLOOR = 51

# Launched scripts that load sibling modules, checked with planted modules.
PROBE_SCRIPTS = (
    "tools/check-page-metadata.py",
    "tools/generate-sitemap.py",
    "tools/test-sitemap.py",
)

# Module names planted beside each probed script: one the scripts import, and
# ones they look for and do not find on Linux.
PLANTED_MODULES = ("tempfile", "msvcrt", "nt", "_winapi")
PLANT_MARKER = "PLANTED-MODULE-RAN"

BAD_BREAKS = {
    "\r": "carriage return",
    "\x0b": "vertical tab",
    "\x0c": "form feed",
    "\x1c": "U+001C",
    "\x1d": "U+001D",
    "\x1e": "U+001E",
    "\x85": "U+0085",
    " ": "U+2028",
    " ": "U+2029",
}

LAUNCH = re.compile(r"python3 -I (tools/[\w.-]+\.py)(?=$|[\s)])")
LAUNCH_PREFIX = re.compile(r"^\s*(?:-\s+)?(?:run:\s+)?$|\$\($|(?<!\|)\| $")
TOOLS_PATH = re.compile(r"tools/[\w.-]+\.py")
PY_WORD = re.compile(r"\.py(?![\w])")
DOT_SLASH_PY = re.compile(r"\./[\w./-]*\.py(?![\w])")
PATHS_ENTRY = re.compile(r'^\s*- "tools/[\w.-]+\.py"\s*$')
ECHO_MESSAGE = re.compile(r'^\s*(?:[\w*|]+\)\s+)?echo\s+"([^"]*)"')
WORKING_DIR = re.compile(r"^\s*(?:-\s+)?working-directory:.*tools")
LOCAL_ACTION = re.compile(r"""^\s*(?:-\s+)?uses:\s*["']?\./(?!\.github/workflows/)""")


def is_comment_line(line: str) -> bool:
    return line.lstrip().startswith("#")


def open_quote(line: str) -> bool:
    """Return True when a shell reading this line alone ends inside a quote."""
    state = None
    i = 0
    while i < len(line):
        c = line[i]
        if state is None:
            if c == "\\":
                i += 1
            elif c in "'\"":
                state = c
            elif c == "#" and (i == 0 or line[i - 1] in " \t"):
                break
        elif state == "'":
            if c == "'":
                state = None
        else:
            if c == "\\":
                i += 1
            elif c == '"':
                state = None
        i += 1
    return state is not None


def launches_in(line: str) -> list[tuple[int, int, str]]:
    """Return (start, end, script) for each allowed launch on the line."""
    found = []
    for match in LAUNCH.finditer(line):
        if LAUNCH_PREFIX.search(line[: match.start()]):
            found.append((match.start(), match.end(), match.group(1)))
    return found


def prose_spans(line: str) -> list[tuple[int, int]]:
    """Return the spans of the line where a script name is prose, not a command."""
    if is_comment_line(line) or PATHS_ENTRY.match(line):
        return [(0, len(line))]
    echo = ECHO_MESSAGE.match(line)
    if echo and not re.search(r"\$\(|`|\\|'", echo.group(1)):
        return [echo.span(1)]
    return []


def inside(start: int, end: int, spans) -> bool:
    return any(a <= start and end <= b for a, b in spans)


def scan_text(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (findings, launches) for one file's text, as (line, detail) pairs."""
    findings: list[tuple[int, str]] = []
    launches: list[tuple[int, str]] = []
    lines = text.split("\n")
    for number, line in enumerate(lines, 1):
        for char, name in BAD_BREAKS.items():
            if char in line:
                findings.append((number, f"holds a {name}, which some readers take as a line break"))
        allowed = launches_in(line)
        launch_spans = [(a, b) for a, b, _ in allowed]
        prose = prose_spans(line)
        launches += [(number, script) for _, _, script in allowed]
        for match in re.finditer("python", line):
            if not any(a == match.start() for a, _ in launch_spans):
                findings.append((number, "python appears other than as python3 -I tools/<name>.py"))
        for match in TOOLS_PATH.finditer(line):
            if not inside(match.start(), match.end(), launch_spans + prose):
                findings.append((number, f"{match.group(0)} appears other than as an allowed launch"))
        for match in PY_WORD.finditer(line):
            if not inside(match.start(), match.end(), launch_spans + prose):
                findings.append((number, "a .py name appears other than as an allowed launch"))
        if DOT_SLASH_PY.search(line):
            findings.append((number, "a ./<name>.py path"))
        if WORKING_DIR.match(line):
            findings.append((number, "a working-directory that names tools"))
        if LOCAL_ACTION.match(line):
            findings.append((number, "a local action outside .github/workflows"))
        if not is_comment_line(line) and open_quote(line):
            findings.append((number, "the line leaves a shell quote open"))
        if line.rstrip().endswith("\\") and number < len(lines) and is_comment_line(lines[number]):
            findings.append((number, "a backslash continuation onto a comment line"))
    return findings, launches


def mutates_sys_path(source: str) -> bool:
    """Return True when Python source changes sys.path in its code (not its strings)."""
    tokens = [
        ";" if t.type == tokenize.NEWLINE else t.string
        for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type in (tokenize.NAME, tokenize.OP, tokenize.NEWLINE)
    ]
    for i in range(len(tokens) - 2):
        if tokens[i : i + 3] == ["sys", ".", "path"]:
            following = tokens[i + 3 : i + 5]
            if following[:1] in (["["], ["="], ["+="]):
                return True
            if following[:1] == ["."] and following[1:2] and following[1] in (
                "insert", "append", "extend", "remove", "pop", "clear", "reverse", "sort",
            ):
                return True
        if tokens[i : i + 3] == ["from", "sys", "import"]:
            j = i + 3
            while j < len(tokens) and tokens[j] != ";":
                if tokens[j] == "path":
                    return True
                j += 1
        if tokens[i : i + 3] == ["import", "sys", "as"]:
            return True
        if tokens[i : i + 2] == ["site", "."] and tokens[i + 2] == "addsitedir":
            return True
    return False


def planted_module_runs(root: Path, script: str) -> str | None:
    """Run a copy of `script` under -I beside planted modules; describe a failure."""
    with tempfile.TemporaryDirectory() as tmp:
        tools = Path(tmp) / "tools"
        tools.mkdir()
        for source in (root / "tools").glob("*.py"):
            shutil.copy2(source, tools / source.name)
        for name in PLANTED_MODULES:
            (tools / f"{name}.py").write_text(
                f"import os\nos.write(1, b'{PLANT_MARKER} {name}\\n')\nos._exit(97)\n",
                encoding="utf-8",
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
            return f"{script}: a module planted beside it ran under python3 -I"
    return None


def scan_tree(root: Path, floor: int, probe_scripts) -> tuple[list[str], int]:
    """Scan the workflows under root; return (findings, number of allowed launches)."""
    workflows = root / ".github" / "workflows"
    try:
        names = sorted(os.listdir(workflows))
    except OSError as exc:
        return [f"cannot list {workflows}: {exc}"], 0
    files = [workflows / name for name in names if name.endswith((".yml", ".yaml"))]
    if not files:
        return [f"no workflow file found in {workflows}"], 0

    findings: list[str] = []
    launches: list[tuple[str, int, str]] = []
    for path in files:
        rel = path.relative_to(root)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{rel}: cannot be read as UTF-8 ({exc})")
            continue
        file_findings, file_launches = scan_text(text)
        findings += [f"{rel}:{number}: {reason}" for number, reason in file_findings]
        launches += [(str(rel), number, script) for number, script in file_launches]

    for rel, number, script in launches:
        try:
            body = (root / script).read_text(encoding="utf-8")
            changes_path = mutates_sys_path(body)
        except (OSError, UnicodeDecodeError, SyntaxError, tokenize.TokenError) as exc:
            findings.append(f"{rel}:{number}: launched script {script} cannot be read ({exc})")
            continue
        if changes_path:
            findings.append(f"{rel}:{number}: {script} changes sys.path")

    if len(launches) < floor:
        findings.append(f"only {len(launches)} allowed launches found, below the floor of {floor}")

    for script in probe_scripts:
        failure = planted_module_runs(root, script)
        if failure:
            findings.append(failure)
    return findings, len(launches)


# (workflow text, True when the scan must report a finding)
LINE_CASES = [
    ("run: python3 tools/x.py", True),
    ("run: /usr/bin/python3 -I tools/x.py", True),
    ("run: .venv/bin/python3 -I tools/x.py", True),
    ('run: "$pythonLocation/bin/python3" -I tools/x.py', True),
    ("run: python3.13t -I tools/x.py", True),
    ("run: python3.12 tools/x.py", True),
    ("run: python tools/x.py", True),
    ("run: env python3 -I tools/x.py", True),
    ("run: python3 -E tools/x.py", True),
    ("run: python3 -X utf8 -I tools/x.py", True),
    ("run: python3 -I -X utf8 tools/x.py", True),
    ('run: python3 -I "tools/x.py"', True),
    ("run: python3 -I -c 'x'", True),
    ("run: python3 -I ./tools/x.py", True),
    ("run: tools/x.py", True),
    ('run: "tools/x.py"', True),
    ('run: out="$(tools/x.py)"', True),
    ('run: ENV="ci" tools/x.py', True),
    ("run: exec tools/x.py", True),
    ("run: pytest tools/x.py", True),
    ("run: py -3 tools/x.py", True),
    ("run: tools/x.py # note", True),
    ("run: true # ; tools/x.py", True),
    ("run: cd tools && ./x.py", True),
    ("run: for f in tools/x-*.py; do \"$f\"; done", True),
    ('run: echo "python3 -I tools/x.py"', True),
    ("run: bash -c 'python3 -I tools/x.py'", True),
    ('run: echo "$(tools/x.py)"', True),
    ("run: p\"\"ython3 -I tools/x.py", True),
    ("run: python3 -I tools/a.py; python3 tools/b.py", True),
    ("run: python3 -I tools/a.py || python3 -I tools/b.py", True),
    ("        shell: python", True),
    ("      working-directory: tools", True),
    ("      - uses: ./.github/actions/x", True),
    ('run: x="', True),
    ("run: true  # ; tools/x.py", True),
    ("run: true\x0b# ; tools/x.py", True),
    ("run: true  ", True),
    ("run: true \x0c", True),
    ("run: true \r", True),
    ("# (python3 -I) in a comment", True),
    ("run: python3 -I tools/x.py", False),
    ("      - run: python3 -I tools/x.py --flag", False),
    ("          python3 -I tools/x.py arg >/dev/null || rc=$?", False),
    ('          v="$(python3 -I tools/x.py a)" || rc=$?', False),
    ('          if ! v="$(git show X | python3 -I tools/x.py)"; then', False),
    ('      - "tools/x.py"', False),
    ("# See tools/x.py and check-x.py for scope.", False),
    ('          1) echo "tools/x.py rejected ${V} (see above)." >&2; exit 1 ;;', False),
    ("run: bash tools/x.sh", False),
    ("  # the Python gates", False),
]

# Whole files, as (name, workflow text, True when the scan must report a finding).
FILE_CASES = [
    ("comment-continuation", "run: |\n  true\\\n  # ; tools/x.py\n", True),
    ("yaml-escaped-break", 'run: "x=1\\\n  #;python3 -I tools/x.py"\n', True),
    ("comment-prose", "run: |\n  true\n  # See tools/x.py for scope.\n", False),
    ("open-string", 'run: |\n  x="\n  echo "a; tools/x.py"\n  "\n', True),
]


def self_test() -> list[str]:
    errors = []
    for text, want in LINE_CASES + [(t, w) for _, t, w in FILE_CASES]:
        got = bool(scan_text(text)[0])
        if got != want:
            errors.append(f"self-test: {text!r}: expected {'a finding' if want else 'none'}")
    if scan_text("run: python3 -I tools/x.py\n  python3 -I tools/y.py arg")[1] != [
        (1, "tools/x.py"), (2, "tools/y.py"),
    ]:
        errors.append("self-test: launch recording")

    detector = [
        ("sys.path.insert(0, d)\n", True),
        ("sys.path[:0] = [d]\n", True),
        ("sys.path.append(d)\n", True),
        ("sys.path += [d]\n", True),
        ("from sys import argv, path\n", True),
        ("import sys as s\n", True),
        ("site.addsitedir(d)\n", True),
        ('x = "sys.path.insert(0, d)"\n', False),
        ("# sys.path.insert(0, d)\n", False),
        ("print(sys.path)\n", False),
        ("from sys import argv\npath = 1\n", False),
    ]
    for source, want in detector:
        if mutates_sys_path(source) != want:
            errors.append(f"self-test: sys.path detector on {source!r}: expected {want}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tools").mkdir()
        missing, _ = scan_tree(root, 1, ())
        if not any("cannot list" in f for f in missing):
            errors.append("self-test: a missing workflow folder gave no finding")
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (root / "tools" / "a.py").write_text("import tempfile\n", encoding="utf-8")
        (root / "tools" / "b.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parent))\n",
            encoding="utf-8",
        )
        (root / "tools" / "shadow.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "setattr(sys, 'path', [str(Path(__file__).resolve().parent)] + sys.path)\n"
            "import tempfile\n",
            encoding="utf-8",
        )
        (root / "tools" / "absent.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "setattr(sys, 'path', sys.path + [str(Path(__file__).resolve().parent)])\n"
            "try:\n    import msvcrt\nexcept ImportError:\n    pass\n",
            encoding="utf-8",
        )
        good = workflows / "good.yml"
        good.write_text("run: python3 -I tools/a.py\n", encoding="utf-8")
        findings, count = scan_tree(root, 1, ())
        if findings or count != 1:
            errors.append(f"self-test: a clean tree gave {findings!r} and {count} launches")
        findings, _ = scan_tree(root, 2, ())
        if not any("below the floor" in f for f in findings):
            errors.append("self-test: a launch count below the floor gave no finding")
        for name, text, want in FILE_CASES:
            good.write_text(text + "run: python3 -I tools/a.py\n", encoding="utf-8")
            if bool(scan_tree(root, 1, ())[0]) != want:
                errors.append(f"self-test: whole-file case {name} gave the wrong verdict")
        good.write_text("run: python3 -I tools/a.py\nrun: python3 -I tools/b.py\n", encoding="utf-8")
        if not any("changes sys.path" in f for f in scan_tree(root, 1, ())[0]):
            errors.append("self-test: a launched script that inserts into sys.path gave no finding")
        good.write_text("run: python3 -I tools/a.py\n", encoding="utf-8")
        (workflows / "bad.yml").write_bytes(b"run: \xff\n")
        if not any("cannot be read" in f for f in scan_tree(root, 1, ())[0]):
            errors.append("self-test: an unreadable workflow file gave no finding")
        (workflows / "bad.yml").unlink()
        for script in ("tools/shadow.py", "tools/absent.py"):
            if planted_module_runs(root, script) is None:
                errors.append(f"self-test: the planted-module probe missed {script}")
        if planted_module_runs(root, "tools/a.py") is not None:
            errors.append("self-test: the planted-module probe flagged a clean script")
        if not any("planted" in f for f in scan_tree(root, 1, ("tools/shadow.py",))[0]):
            errors.append("self-test: the scan did not report the planted-module probe")
    return errors


def main() -> int:
    errors = self_test()
    if errors:
        for error in errors:
            print(error)
        print(f"FAIL: {len(errors)} self-test failure(s)")
        return 1
    findings, count = scan_tree(REPO, LAUNCH_FLOOR, PROBE_SCRIPTS)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s), {count} allowed launches")
        return 1
    print(f"OK: {count} Python launches in the workflows, every one isolated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
