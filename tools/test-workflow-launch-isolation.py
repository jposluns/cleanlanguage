#!/usr/bin/env python3
"""Check that every Python launch in the workflows and local actions runs isolated.

Purpose and limit. This check catches an honest or accidental Python launch
without `-I` in the YAML files under .github. It is a text scan of the pull
request's own checkout, so it is not a defence against a deliberate attempt to
hide a launch: the author of such a change can also edit this scan, its floor
or its workflow, and only review catches that. It closes every structural gap
an honest change could hit, and it fails closed on forms it cannot classify.

A Python-launched gate that finds a planted file on its module path can import
that file in place of a standard-library module and turn the gate into a green
run that checked nothing. `python3 -I` keeps the script folder off the module
path and ignores the user site directory and every PYTHON* variable.

What it reads. Every .yml and .yaml file under .github, in every subfolder,
including composite actions. Each file is read as UTF-8, split on newlines only,
and every line is scanned, comments included. A comment line is one whose first
character after spaces and tabs is `#`.

The allowed launch is exactly `python3 -I tools/<name>.py`, followed by the end
of the line, a space or `)`, and preceded on its line by nothing but spaces and
tabs, `run: ` or `- run: `, or by `$(` or a single `| `. Only allowed launches
count toward LAUNCH_FLOOR.

A file fails when any line:

- holds a carriage return, vertical tab, form feed, U+001C to U+001E, or any
  character outside ASCII;
- has the text `python` anywhere except as an allowed launch;
- has a `tools/<name>.py` or a `<name>.py` anywhere except in an allowed launch,
  a paths filter entry written `- "tools/<name>.py"`, a comment line, or an
  `echo` line that is only a double-quoted message with no `$(`, backtick,
  backslash or `'` inside (after an optional `run: ` or `- run: ` and an
  optional case label such as `1)`, and followed by nothing but an optional
  `>&2` and an optional `; exit N ;;`);
- has a `./<name>.py`, or a word holding `tools/` or `.p` with a glob character;
- feeds text to a shell: a pipe into sh, bash, dash, zsh or ksh, any use of
  those shells other than the line `shell: bash` or `bash tools/<name>.sh` at
  the head of a command, `eval`, `source`, a `.` command, `xargs`, or a
  here-document;
- has a backtick, an ANSI-C `$'` string, a quote inside a word, a backslash
  outside single quotes other than a line-end continuation after a space, or a
  `${{ }}` expression next to a word character;
- leaves a shell quote or `$(` open at its end (for a line that is not a
  comment);
- ends in a backslash before a comment line, with or without blank lines
  between;
- uses a YAML form this line scan cannot classify: a flow mapping, a quoted key,
  a quoted `run` value, or a folded scalar (`>`);
- has `uses` other than `uses: <owner>/<repo>[/<path>]@<40 hex digits>`,
  optionally with a comment, or `uses: ./.github/<path>` with no `..`;
- has a `working-directory` that names tools.

On a comment line only the character, `python`, `./<name>.py`, glob,
working-directory and continuation rules apply.

The scan also fails when a file under .github is a symbolic link, when a
launched script cannot be read or changes sys.path in its code, and when there
are fewer allowed launches than LAUNCH_FLOOR. It then plants tempfile.py,
msvcrt.py, nt.py and _winapi.py beside a copy of each script in PROBE_SCRIPTS,
runs the copy under `-I`, and fails if a planted module ran.

It runs its own self-tests first and stops on any failure. Every line case
runs the whole scan on a temporary tree, and further tree cases cover the
floor, an unreadable workflow, a missing folder, a subfolder, a symbolic link,
local actions, a missing launched script, the sys.path detector and the
planted-module probe.

Residuals: deliberate obfuscation that a line scan cannot see, named here
because the author of such a change can edit the scan anyway:

- shell quote removal and escapes beyond the forms above, such as a quote pair
  between a word and a space;
- a glob outside a `tools/` or `.p` word, such as on an interpreter path;
- a `${{ }}` expression that GitHub expands into a whole command;
- a shell function or alias defined under a name that does not spell python;
- a command assembled at run time, or an interpreter held in a variable;
- splitting a launch across continuation lines between words (this reads as
  a launch without `-I`, the safe direction);
- YAML anchors, aliases, tags and merge keys, and how GitHub decodes YAML in
  general, since this scan reads lines, not YAML;
- a remote action or reusable workflow, which is outside this repository;
- a launch made by a shell script the workflows run, or by a launcher that
  names no `.py` path (such as `pytest` with a folder, `py`, `uv run` or `pipx`);
- an allowed launch in a step that never runs, such as under `if: false`,
  which still counts toward the floor;
- a sys.path change made other than by a statement on `sys.path`, `meta_path`
  or `path_hooks`, or by `from sys import path`, such as through getattr.

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

# The number of allowed launches under .github when this check landed.
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

ASCII_BREAKS = {
    "\r": "carriage return",
    "\x0b": "vertical tab",
    "\x0c": "form feed",
    "\x1c": "U+001C",
    "\x1d": "U+001D",
    "\x1e": "U+001E",
}
NON_ASCII = re.compile(r"[^\x00-\x7f]")

LAUNCH = re.compile(r"python3 -I (tools/[\w.-]+\.py)(?=$|[\s)])")
LINE_HEAD = r"^[ \t]*(?:-[ \t]+run:[ \t]+|run:[ \t]+)?"
LAUNCH_PREFIX = re.compile(LINE_HEAD + r"$|\$\($|(?<!\|)\| $")
PY_WORD = re.compile(r"[\w./-]*\.py(?![\w])")
DOT_SLASH_PY = re.compile(r"\./[\w./-]*\.py(?![\w])")
GLOB_WORD = re.compile(r"[^\s\"'=]*(?:tools/|\.p)[^\s\"'=]*[?*\[]|[?*\[][^\s\"'=]*\.py")
PATHS_ENTRY = re.compile(r'^[ \t]*- "tools/[\w.-]+\.py"[ \t]*$')
ECHO_MESSAGE = re.compile(
    LINE_HEAD + r'(?:[\w*|]+\)[ \t]+)?echo[ \t]+"([^"]*)"[ \t]*(?:>&2)?[ \t]*'
    r"(?:;[ \t]*exit[ \t]+\d+[ \t]*;;)?[ \t]*$"
)
SHELL_WORD = re.compile(r"(?<![\w./-])(?:ba|da|z|k)?sh(?![\w./-])")
SHELL_KEY = re.compile(r"^[ \t]*shell:[ \t]*bash[ \t]*$")
SHELL_SCRIPT = re.compile(r"bash tools/[\w.-]+\.sh(?=$|\s)")
FED_SHELL = re.compile(
    r"(?<![\w./-])(?:eval|source|xargs)(?![\w.-])"
    r"|(?:^[ \t]*(?:-[ \t]+run:[ \t]+|run:[ \t]+)?|[;&|(][ \t]*)\.[ \t]+\S"
    r"|(?<!<)<<(?!<)"
)
QUOTE_IN_WORD = re.compile(r"[\w./-][\"']+[\w./-]")
EXPRESSION_NEXT_TO_WORD = re.compile(r"[\w.]\$\{\{|\}\}[\w.]")
FLOW_MAPPING = re.compile(r"^[ \t]*(?:-[ \t]+)?\{|:[ \t]*\{")
QUOTED_KEY = re.compile(r"""^[ \t]*(?:-[ \t]+)?["'][^"']*["'][ \t]*:""")
QUOTED_RUN = re.compile(r"""^[ \t]*(?:-[ \t]+)?run:[ \t]*["']""")
FOLDED = re.compile(r":[ \t]*>[-+0-9]*[ \t]*(?:#.*)?$")
USES_WORD = re.compile(r"\buses\b")
USES_REMOTE = re.compile(r"^[ \t]*(?:-[ \t]+)?uses:[ \t]+[\w.-]+/[\w./-]+@[0-9a-f]{40}(?:[ \t]+#.*)?$")
USES_LOCAL = re.compile(r"^[ \t]*(?:-[ \t]+)?uses:[ \t]+\./\.github/[\w./-]+[ \t]*$")
WORKING_DIR = re.compile(r"^[ \t]*(?:-[ \t]+)?working-directory:.*tools")


def is_comment_line(line: str) -> bool:
    return line.lstrip(" \t").startswith("#")


def shell_reading(line: str) -> tuple[bool, list[int]]:
    """Read the line as a shell would, alone.

    Return (open, backslashes): whether a quote or `$(` is still open at the end,
    and the index of each backslash that sits outside single quotes.
    """
    stack = ["N"]
    depth = [0]
    backslashes = []
    i = 0
    while i < len(line):
        c = line[i]
        top = stack[-1]
        if top == "'":
            if c == "'":
                stack.pop()
                depth.pop()
        elif top == '"':
            if c == "\\":
                backslashes.append(i)
                i += 1
            elif c == '"':
                stack.pop()
                depth.pop()
            elif line.startswith("$(", i):
                stack.append("N")
                depth.append(0)
                i += 1
        else:
            if c == "\\":
                backslashes.append(i)
                i += 1
            elif c in "'\"":
                stack.append(c)
                depth.append(0)
            elif line.startswith("$(", i):
                stack.append("N")
                depth.append(0)
                i += 1
            elif c == "(":
                depth[-1] += 1
            elif c == ")":
                if depth[-1]:
                    depth[-1] -= 1
                elif len(stack) > 1:
                    stack.pop()
                    depth.pop()
            elif c == "#" and (i == 0 or line[i - 1] in " \t("):
                break
        i += 1
    return len(stack) > 1, backslashes


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


def next_nonblank(lines: list[str], index: int) -> str | None:
    for line in lines[index:]:
        if line.strip(" \t"):
            return line
    return None


def scan_text(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (findings, launches) for one file's text, as (line, detail) pairs."""
    findings: list[tuple[int, str]] = []
    launches: list[tuple[int, str]] = []
    lines = text.split("\n")
    for number, line in enumerate(lines, 1):
        def find(reason: str) -> None:
            findings.append((number, reason))

        comment = is_comment_line(line)
        for char, name in ASCII_BREAKS.items():
            if char in line:
                find(f"holds a {name}, which some readers take as a line break")
        if NON_ASCII.search(line):
            find("holds a character outside ASCII")
        allowed = launches_in(line)
        launch_spans = [(a, b) for a, b, _ in allowed]
        prose = prose_spans(line)
        launches += [(number, script) for _, _, script in allowed]
        for match in re.finditer("python", line):
            if not any(a == match.start() for a, _ in launch_spans):
                find("python appears other than as python3 -I tools/<name>.py")
        for match in PY_WORD.finditer(line):
            if not inside(match.start(), match.end(), launch_spans + prose):
                find(f"{match.group(0)} appears other than as an allowed launch")
        if DOT_SLASH_PY.search(line):
            find("a ./<name>.py path")
        if GLOB_WORD.search(line):
            find("a glob in a word that names tools/ or .p")
        if WORKING_DIR.match(line):
            find("a working-directory that names tools")
        if line.rstrip(" \t").endswith("\\"):
            following = next_nonblank(lines, number)
            if following is not None and is_comment_line(following):
                find("a backslash continuation onto a comment line")
        if comment:
            continue
        for match in SHELL_WORD.finditer(line):
            if inside(match.start(), match.end(), prose) or SHELL_KEY.match(line):
                continue
            head = re.match(LINE_HEAD + r"$", line[: match.start()])
            if not (head and SHELL_SCRIPT.match(line, match.start())):
                find("a shell is run other than as bash tools/<name>.sh")
        for match in FED_SHELL.finditer(line):
            if not inside(match.start(), match.end(), prose):
                find("text is fed to a shell (eval, source, a . command, xargs or a here-document)")
        if "`" in line:
            find("a backtick")
        if "$'" in line:
            find("an ANSI-C $' string")
        if QUOTE_IN_WORD.search(line):
            find("a quote inside a word")
        if EXPRESSION_NEXT_TO_WORD.search(line):
            find("a ${{ }} expression next to a word")
        is_open, backslashes = shell_reading(line)
        if is_open:
            find("the line leaves a shell quote or $( open")
        for index in backslashes:
            if line[index + 1 :].strip(" \t") == "":
                if index == 0 or line[index - 1] not in " \t":
                    find("a line-end backslash with no space before it, which splits a word")
            else:
                find("a backslash outside single quotes")
        if FLOW_MAPPING.search(line):
            find("a YAML flow mapping")
        if QUOTED_KEY.match(line):
            find("a quoted YAML key")
        if QUOTED_RUN.match(line):
            find("a run value in YAML quotes")
        if FOLDED.search(line):
            find("a folded YAML scalar")
        if USES_WORD.search(line):
            if not (USES_REMOTE.match(line) or (USES_LOCAL.match(line) and "/../" not in line + "/")):
                find("a uses form the scan cannot classify")
    return findings, launches


METHODS = ("insert", "append", "extend", "remove", "pop", "clear", "reverse", "sort")


def mutates_sys_path(source: str) -> bool:
    """Return True when Python source changes sys.path in its code (not its strings)."""
    raw = [
        ";" if t.type == tokenize.NEWLINE else t.string
        for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type in (tokenize.NAME, tokenize.OP, tokenize.NEWLINE)
    ]
    tokens = []
    i = 0
    while i < len(raw):
        if raw[i] == "(" and i + 2 < len(raw) and raw[i + 1] == "sys" and raw[i + 2] == ")":
            tokens.append("sys")
            i += 3
            continue
        tokens.append(raw[i])
        i += 1
    for i, token in enumerate(tokens):
        window = tokens[i : i + 5]
        if window[:2] == ["sys", "."] and window[2:3] in (["meta_path"], ["path_hooks"]):
            return True
        if window[:3] == ["sys", ".", "path"]:
            following = window[3:5]
            if following[:1] in (["["], ["="], ["+="]):
                return True
            if following[:1] == ["."] and following[1:2] and (
                following[1] in METHODS or following[1].startswith("__")
            ):
                return True
        if window[:3] == ["from", "sys", "import"]:
            j = i + 3
            while j < len(tokens) and tokens[j] != ";":
                if tokens[j] in ("path", "meta_path", "path_hooks"):
                    return True
                j += 1
        if window[:3] == ["import", "sys", "as"]:
            return True
        if window[:3] == ["site", ".", "addsitedir"]:
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


def list_yaml(root: Path) -> tuple[list[Path], list[str]]:
    """Return every .yml and .yaml file under root/.github, and listing failures."""
    base = root / ".github"
    errors: list[str] = []
    files: list[Path] = []
    if not base.is_dir():
        return [], [f"cannot list {base}: not a folder"]

    def failed(exc: OSError) -> None:
        errors.append(f"cannot list {exc.filename}: {exc.strerror}")

    for folder, dirs, names in os.walk(base, onerror=failed):
        for name in sorted(dirs + names):
            path = Path(folder) / name
            if path.is_symlink():
                errors.append(f"{path.relative_to(root)}: a symbolic link under .github")
        files += [Path(folder) / n for n in names if n.endswith((".yml", ".yaml"))]
    return sorted(files), errors


def scan_tree(root: Path, floor: int, probe_scripts) -> tuple[list[str], int]:
    """Scan the YAML under root/.github; return (findings, number of allowed launches)."""
    files, findings = list_yaml(root)
    if not files and not findings:
        findings.append(f"no workflow file found under {root / '.github'}")
    if not files:
        return findings, 0

    launches: list[tuple[str, int, str]] = []
    for path in files:
        rel = path.relative_to(root)
        try:
            # Raw bytes, so a carriage return is not translated into a newline.
            text = path.read_bytes().decode("utf-8")
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


# (workflow text, True when the scan must report a finding). Each runs the
# whole scan on a temporary tree, with one allowed launch added for the floor.
LINE_CASES = [
    ("run: python3 tools/x.py", True),
    ("run: /usr/bin/python3 -I tools/x.py", True),
    ("run: .venv/bin/python3 -I tools/x.py", True),
    ("run: python3.13t -I tools/x.py", True),
    ("run: python tools/x.py", True),
    ("run: env python3 -I tools/x.py", True),
    ("run: python3 -E tools/x.py", True),
    ("run: python3 -X utf8 -I tools/x.py", True),
    ("run: python3 -I -X utf8 tools/x.py", True),
    ('run: python3 -I "tools/x.py"', True),
    ("run: python3 -I -c 'x'", True),
    ("run: python3 -I ./tools/x.py", True),
    ("      - python3 -I tools/x.py", True),
    ("run: tools/x.py", True),
    ('out="$(tools/x.py)"', True),
    ("ENV=ci tools/x.py", True),
    ("run: exec tools/x.py", True),
    ("run: pytest tools/x.py", True),
    ("run: py -3 tools/x.py", True),
    ("run: tools/x.py # note", True),
    ("run: true # ; tools/x.py", True),
    ("# run ./x.py from the folder", True),
    ("run: tools/check-x.p?", True),
    ("run: echo x | sh", True),
    ("run: bash -c true", True),
    ("run: bash run.sh", True),
    ("run: sed s/x/y/ <<EOF", True),
    ("run: eval true", True),
    ("run: source env.sh", True),
    ("run: . env.sh", True),
    ("run: echo x | xargs true", True),
    ('run: echo "tools/x.py" | sh', True),
    ('run: echo "tools/x.py" > run.txt', True),
    ("run: echo `true`", True),
    ("run: true $'x'", True),
    ("run: p''ython3 -I tools/x.py", True),
    ('run: p""ython3 -I tools/x.py', True),
    ("run: pyth\\on3 -I tools/x.py", True),
    ("run: py\\", True),
    ("run: check-x.py", True),
    ("run: echo ${{ x }}y", True),
    ("        env: {A: b}", True),
    ("run: echo a\\b", True),
    ("run: echo a''b", True),
    ('      "name": x', True),
    ('run: "true"', True),
    ("\x1f# || tools/x.py", True),
    ("run: ${{ 'p' }}ython3 -I tools/x.py", True),
    ('run: "pyth\\x6fn3 -I tools/x.py"', True),
    ("run: python3 -I tools/a.py; python3 tools/b.py", True),
    ("run: python3 -I tools/a.py || python3 -I tools/b.py", True),
    ("        shell: python", True),
    ("      working-directory: tools", True),
    ("      - {uses: ./.github/actions/x}", True),
    ('      - "uses": ./.github/actions/x', True),
    ("      - uses: ./.github/workflows/../actions/x", True),
    ("      - uses: ./actions/x", True),
    ("      - uses: actions/checkout@v4", True),
    ("defaults: {run: {shell: bash}}", True),
    ("        run: >", True),
    ("run: x=\"", True),
    ("run: x=\"$(true", True),
    ('run: echo "a \' tools/x.py" >&2', True),
    ('run: echo "see tools/x.py \\n" >&2', True),
    ('run: echo "$(true) tools/x.py" >&2', True),
    ("run: true  ", True),
    (" # || tools/x.py", True),
    ("# (python3 -I) in a comment", True),
    ("run: python3 -I tools/x.py", False),
    ("      - run: python3 -I tools/x.py --flag", False),
    ("          python3 -I tools/x.py arg >/dev/null || rc=$?", False),
    ('          v="$(python3 -I tools/x.py a)" || rc=$?', False),
    ('          if ! v="$(git show X | python3 -I tools/x.py)"; then', False),
    ("          v=\"$(printf '%s\\n' \"${a}\" | sort -V | tail -1)\"", False),
    ("          gh release create x \\", False),
    ('      - "tools/x.py"', False),
    ("# See tools/x.py and check-x.py for scope.", False),
    ('          1) echo "tools/x.py rejected ${V} (see above)." >&2; exit 1 ;;', False),
    ('          echo "tools/x.py is unavailable (exit $1) while $2." >&2', False),
    ("        run: bash tools/x.sh", False),
    ("        shell: bash", False),
    ("        run: |", False),
    ("        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0", False),
    ("      - uses: ./.github/actions/x", False),
    ('          grep -qxF -- "${a}" <<< "${b}" || {', False),
    ("  # the Python gates", False),
]

# Characters checked one by one, listed apart from the scan's own table.
BREAK_CHARS = "\r\x0b\x0c\x1c\x1d\x1e\x85  "

# Whole files, as (name, workflow text, True when the scan must report a finding).
FILE_CASES = [
    ("comment-continuation", "run: |\n  true \\\n  # ; tools/x.py\n", True),
    ("comment-continuation-after-blank", "run: |\n  true \\\n\n  # ; tools/x.py\n", True),
    ("yaml-escaped-break", 'run: "x=1\\\n  #;python3 -I tools/x.py"\n', True),
    ("comment-prose", "run: |\n  true\n  # See tools/x.py for scope.\n", False),
    ("open-string", 'run: |\n  x="\n  echo "a; tools/x.py"\n  "\n', True),
    ("continuation", "run: |\n  gh release create x \\\n    --title y\n", False),
]


def self_test() -> list[str]:
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = root / "tools"
        tools.mkdir()
        missing, _ = scan_tree(root, 1, ())
        if not any("cannot list" in f for f in missing):
            errors.append("self-test: a missing .github folder gave no finding")
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        for name in ("a", "b", "x", "y"):
            (tools / f"{name}.py").write_text("import tempfile\n", encoding="utf-8")
        case = workflows / "case.yml"
        anchor = "run: python3 -I tools/a.py\n"

        def verdict(text: str, floor: int = 1, probe=()) -> list[str]:
            case.write_text(text + "\n" + anchor, encoding="utf-8")
            return scan_tree(root, floor, probe)[0]

        for text, want in LINE_CASES:
            if bool(verdict(text)) != want:
                errors.append(f"self-test: {text!r}: expected {'a finding' if want else 'none'}")
        for char in BREAK_CHARS:
            if not verdict(f"run: true {char}"):
                errors.append(f"self-test: U+{ord(char):04X} gave no finding")
        for name, text, want in FILE_CASES:
            if bool(verdict(text)) != want:
                errors.append(f"self-test: whole-file case {name}: expected {'a finding' if want else 'none'}")

        findings = verdict("")
        if findings:
            errors.append(f"self-test: a clean tree gave {findings!r}")
        if scan_text("run: python3 -I tools/x.py\n  python3 -I tools/y.py arg")[1] != [
            (1, "tools/x.py"), (2, "tools/y.py"),
        ]:
            errors.append("self-test: launch recording")
        if not any("below the floor" in f for f in verdict("", floor=2)):
            errors.append("self-test: a launch count below the floor gave no finding")
        if not any("cannot be read" in f for f in verdict("run: python3 -I tools/gone.py")):
            errors.append("self-test: a missing launched script gave no finding")
        (tools / "b.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parent))\n",
            encoding="utf-8",
        )
        if not any("changes sys.path" in f for f in verdict("run: python3 -I tools/b.py")):
            errors.append("self-test: a launched script that inserts into sys.path gave no finding")

        bad = workflows / "bad.yml"
        bad.write_bytes(b"run: \xff\n")
        if not any("cannot be read" in f for f in verdict("")):
            errors.append("self-test: an unreadable workflow file gave no finding")
        bad.unlink()

        sub = workflows / "sub"
        sub.mkdir()
        (sub / "nested.yaml").write_text("run: python3 tools/x.py\n", encoding="utf-8")
        if not any("nested.yaml" in f for f in verdict("")):
            errors.append("self-test: a workflow in a subfolder was not scanned")
        shutil.rmtree(sub)

        action = root / ".github" / "actions" / "m"
        action.mkdir(parents=True)
        (action / "action.yml").write_text(
            "runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: python3 tools/x.py\n",
            encoding="utf-8",
        )
        if not any("action.yml" in f for f in verdict("      - uses: ./.github/actions/m")):
            errors.append("self-test: a local composite action was not scanned")
        shutil.rmtree(root / ".github" / "actions")

        try:
            (workflows / "link.yml").symlink_to(case)
        except OSError as exc:
            errors.append(f"self-test: could not make a symbolic link ({exc})")
        else:
            if not any("symbolic link" in f for f in verdict("")):
                errors.append("self-test: a symbolic link under .github gave no finding")
            (workflows / "link.yml").unlink()

        detector = [
            ("sys.path.insert(0, d)\n", True),
            ("sys.path[:0] = [d]\n", True),
            ("sys.path = [d]\n", True),
            ("sys.path += [d]\n", True),
            ("(sys).path.append(d)\n", True),
            ("sys.path.__setitem__(slice(0, 0), [d])\n", True),
            ("sys.meta_path.insert(0, f)\n", True),
            ("sys.path_hooks.append(f)\n", True),
            ("from sys import argv, path\n", True),
            ("import sys as s\n", True),
            ("site.addsitedir(d)\n", True),
            ('x = "sys.path.insert(0, d)"\n', False),
            ("# sys.path.insert(0, d)\n", False),
            ("print(sys.path)\n", False),
            ("from sys import argv\npath = 1\n", False),
        ] + [
            (f"sys.path.{method}(d)\n", True)
            for method in ("insert", "append", "extend", "remove", "pop", "clear", "reverse", "sort")
        ]
        for source, want in detector:
            if mutates_sys_path(source) != want:
                errors.append(f"self-test: sys.path detector on {source!r}: expected {want}")

        (tools / "shadow.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "setattr(sys, 'path', [str(Path(__file__).resolve().parent)] + sys.path)\n"
            "import tempfile\n",
            encoding="utf-8",
        )
        (tools / "absent.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "setattr(sys, 'path', sys.path + [str(Path(__file__).resolve().parent)])\n"
            "try:\n    import msvcrt\nexcept ImportError:\n    pass\n",
            encoding="utf-8",
        )
        for script in ("tools/shadow.py", "tools/absent.py"):
            if planted_module_runs(root, script) is None:
                errors.append(f"self-test: the planted-module probe missed {script}")
        if planted_module_runs(root, "tools/a.py") is not None:
            errors.append("self-test: the planted-module probe flagged a clean script")
        if not any("planted" in f for f in verdict("", probe=("tools/shadow.py",))):
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
    print(f"OK: {count} Python launches under .github, every one isolated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
