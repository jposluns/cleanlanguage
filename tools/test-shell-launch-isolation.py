#!/usr/bin/env python3
"""Check that every Python launch in the shell scripts the workflows run is isolated.

tools/test-workflow-launch-isolation.py reads the run text of the workflows.
This scan reads the shell scripts that run text starts: every tools/<name>.sh
named in a step's run text, and every tools/<name>.sh that a covered script
names outside its comment lines, until no new script is found.

Threat model: honest drift, as in the workflow scan. An author who sets out to
run python without -I can also edit this scan.

The rules, applied to each line of a covered script except its comment lines,
with every backslash-newline removed (a finding names the first line of the
joined line). A comment, on a line of its own or after a command, ends at its
line even when it ends in a backslash, as in bash, so it joins no line:

1. Every python command name, a lower-case `python` with any digits and dots
   after it, no letter or dot straight before it and no letter, digit,
   underscore or hyphen straight after those, starts `python3 -I ` (single
   spaces), directly after the start of the line, a space, a tab, a quote, a
   backquote, or one of ( | & ; !. So `python3 -I tools/<name>.py`,
   `python3 -I -c`, `python3 -I -` and a grep pattern that names the isolated
   form pass, and `python3 tools/x.py`, `python3 -c`, `"python3" -I`,
   `${PYTHON:-python3}`, `$bin/python3` and `python3 -X utf8` are findings. A
   `python` inside a longer name, as in tools/check-python-version.py,
   docs.python.org or ipython3, is not a command name.
2. A .py or .pyz path in command position, run by its shebang, is a finding.
   Command position is the start of the line or what follows ; & | ( ! $(
   or a backquote, a ) or { followed by a space or tab (a case pattern, a
   brace group), one of then, do, else, elif, if, while and until, or one of
   the launchers exec, time, nice, env and command with any option words
   after it, each option word optionally followed by 1 argument word
   (`nice -n 5`, `env -u NAME`), and any NAME=value words and redirection
   words (`2>/dev/null`, `> "$log"`) before the path. A NAME=value word with
   no command word after it is an assignment, so `gate=tools/x.py` is not a
   finding.

The body of a here-document is read as shell text, line by line, unless its
opening line launches `python3 -I` with `-` as the program, so that the body
is the program that launch reads; the opening line is always read. When a
line leaves a single quote open and that quote follows `python3 -I` options
ending in `-c`, the lines up to the next one holding a single quote are the
program of that -c launch and are not read; of that next line, only the text
after its first single quote is read. No other line is skipped. Whether a
quote is left open follows the shell's rules for single quotes, double
quotes, $'...', a backslash, a $(...) inside double quotes, and a # that
starts a comment, so an apostrophe inside double quotes opens nothing.

EXCEPTIONS names each line that breaks a rule on purpose, with its file, the
pattern the whole line must match, the here-documents it may sit in (none
means outside any here-document), and the reason. An exception that matches
no line is a finding, so the table cannot keep an entry for a line that is
gone. EXPECTED_SCRIPTS names the scripts the discovery must find, so a change
that stops the discovery from reaching one is a finding.

Residuals: the scan reads shell, an open grammar, as text, to catch honest
drift. It cannot be complete: it can miss or misread forms that these rules
and the self-tests do not name. The known misses are a launch held in a
variable (`$PY tools/x.py`, `"$real_py"`), a launch through a function or
alias named python3, a `python` spelt in other letter cases, an interpreter
name with a letter or dot before its `python` (`ipython3`) or a letter or
hyphen after its digits (`python3m`), a .py path after a launcher it does
not name (such as xargs or timeout) or after a launcher option that takes
more than 1 argument word, a .py path after a redirection word that holds a
space (`2> "a b" tools/x.py`), a .py path written straight after a case
pattern's ) with no space or tab between, a line after one that ends in an
escaped backslash (`echo \\`), which the scan joins to it, a -c program that
holds a single quote (as `'\''`), a case pattern inside $(...) that misleads
the quote reading, text built at run time, Python launched from Python (such
as subprocess with sys.executable), and a script that a covered script
reaches only through a variable or a path the discovery does not match. The
known misreadings, each a false finding, are a `python` word after a slash or
a hyphen in a path or URL (`github.com/python/cpython`), a .py argument after
a closing backquote or after `&>` (`true &>f x.py`), and a line inside a
quoted string that spans lines, which is read as shell.

Usage: python3 -I tools/test-shell-launch-isolation.py
Exit status: 0 when every check passes, 1 on any finding or failure.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent

EXPECTED_SCRIPTS = (
    "tools/check-portable-text-sync.sh",
    "tools/ci-status.sh",
    "tools/pages-build.sh",
    "tools/release-dry-run.sh",
    "tools/release-package.sh",
    "tools/test-ci-status.sh",
    "tools/test-portable-text-release-date.sh",
    "tools/test-version-selectors.sh",
)

# (file, pattern of the whole stripped line, here-documents it may sit in, reason)
EXCEPTIONS = (
    ("tools/pages-build.sh",
     r'echo "pages-build: Python 3\.11 or later is required \(tomllib\); found \$\(python3 --version 2>&1\)\." >&2',
     (), "python3 --version prints the interpreter version and runs no script"),
    ("tools/pages-build.sh", r'echo "pages-build: \$\(python3 --version 2>&1\)"', (),
     "python3 --version prints the interpreter version and runs no script"),
    ("tools/test-portable-text-release-date.sh",
     r'(?:.* )?tools/skill-release-date(?:-client)?\.py (?:--)?baseline', ("PROBES", "CLIENTPROBES"),
     "launch forms written to a fixture file that the test appends to a copy of the sync gate and expects "
     "its mention check to refuse; the shell does not run them"),
    ("tools/test-version-selectors.sh",
     r'''got="\$\(grep -Ec 'python3\( -I\)\? tools/skill-version\\\.py' "\$\{site\}" \|\| true\)"''', (),
     "a grep pattern that counts the calls of tools/skill-version.py with and without -I, so that an "
     "unisolated call changes the count; the shell does not run it"),
    ("tools/test-ci-status.sh", r'local (real|swap)_py; \1_py="\$\(command -v python3\)"', (),
     "finds the real python3 for a stand-in python3 that a case puts first on PATH"),
    ("tools/test-ci-status.sh", r'(?:cat > |chmod \+x )"\$(?:bin|tmp/swapbin)/python3"(?: <<PY| ;;)?', (),
     "writes and marks executable a stand-in python3 that a case puts first on PATH"),
)

SCRIPT_NAME = re.compile(r"([\w.-]+)\.sh(?![\w.-])")
# A python after a letter or a dot is part of another word, such as docs.python.org.
PYTHON_WORD = re.compile(r"(?<![A-Za-z.])python[0-9.]*(?![\w-])")
ISOLATED = "python3 -I "
LAUNCH_BEFORE = set(" \t(|&;!`\"'")
AFTER_LAUNCH_BEFORE = r"(?<![^ \t(|&;!`\"'])"
COMMAND_START = (
    r"(?:^|[;&|(!`]|\$\(|(?<!\$)[{)](?=[ \t])|(?<![\w-])(?:then|do|else|elif|if|while|until)\s"
    r"|(?<![\w-])(?:exec|time|nice|env|command)\s+(?:-\S*\s+(?:\S+\s+)?)*)"
)
# A redirection word, such as 2>/dev/null, >&2 or < "$f", which may come before the command word.
REDIRECTION = r"[0-9]*(?:&>>?|<>|>>|>\||[<>]&?)\s*[^\s|;&()<>]+"
# A word of the form NAME=value is an assignment, not a command, so the path must not start with one.
SHEBANG_RUN = re.compile(COMMAND_START + r"\s*(?:(?:\w+=\S*|" + REDIRECTION + r")\s+)*(?!\w+=)[\"']?[^\s\"'|;&()]*\.pyz?(?![\w.-])")
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*([\"']?)([A-Za-z_]\w*)\2")
# A python3 -I launch that reads its program from a here-document on standard input.
STDIN_PROGRAM = re.compile(AFTER_LAUNCH_BEFORE + r"python3 -I (?:-[A-Za-z]+ )*-(?=\s|$)")
# The text before a single quote that opens the program of a python3 -I -c launch.
C_PROGRAM = re.compile(AFTER_LAUNCH_BEFORE + r"python3 -I (?:-[A-Za-z]+ )*-c $")


def line_findings(line: str) -> list[str]:
    """Return the rules one shell line breaks."""
    found = []
    for match in PYTHON_WORD.finditer(line):
        at = match.start()
        if not line.startswith(ISOLATED, at) or (at and line[at - 1] not in LAUNCH_BEFORE):
            found.append("python other than python3 -I")
            break
    if SHEBANG_RUN.search(line):
        found.append("a .py path run by its shebang")
    return found


def open_single_quote(line: str) -> int | None:
    """Return where a single quote that the line leaves open starts, or None."""
    stack, _ = quote_state(line)
    return stack[-1][1] if stack and stack[-1][0] == "'" else None


def comment_start(line: str) -> int | None:
    """Return where a comment on the line starts, or None."""
    return quote_state(line)[1]


def quote_state(line: str) -> tuple[list[tuple[str, int]], int | None]:
    """Return the quotes and parentheses the line leaves open, and where a comment starts, or None."""
    stack: list[tuple[str, int]] = []
    i = 0
    while i < len(line):
        c = line[i]
        state = stack[-1][0] if stack else "("
        if state == "'":
            if c == "'":
                stack.pop()
        elif c == "\\":
            i += 1
        elif state == "$'":
            if c == "'":
                stack.pop()
        elif state == '"':
            if c == '"':
                stack.pop()
            elif line.startswith("$(", i):
                stack.append(("(", i))
                i += 1
        elif c == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
            return stack, i
        elif line.startswith("$'", i):
            stack.append(("$'", i))
            i += 1
        elif c in "'\"(":
            stack.append((c, i))
        elif c == ")" and stack:
            stack.pop()
        i += 1
    return stack, None


def script_lines(text: str):
    """Yield (line number, line, here-document delimiter or None) for each line read as shell."""
    lines = text.split("\n")
    heredocs: list[tuple[str, bool, bool]] = []
    in_program = False
    i = 0
    while i < len(lines):
        line = lines[i]
        number = i + 1
        i += 1
        if heredocs:
            delim, strip_tabs, skip = heredocs[0]
            if (line.lstrip("\t") if strip_tabs else line) == delim:
                heredocs.pop(0)
            elif not skip and not line.lstrip(" \t").startswith("#"):
                yield number, line, delim
            continue
        resumed = in_program
        if in_program:
            if "'" not in line:
                continue
            in_program = False
            # The leading quote keeps a path just after the program from reading as a command.
            line = "'" + line.split("'", 1)[1]
        # Bash does not continue a comment, so a backslash that ends one joins no line.
        while line.endswith("\\") and i < len(lines) and comment_start(line[1:] if resumed else line) is None:
            line = line[:-1] + lines[i]
            i += 1
        if line.lstrip(" \t").startswith("#"):
            continue
        yield number, line, None
        openers = list(HEREDOC.finditer(line))
        stdin = STDIN_PROGRAM.search(line)
        first = next((m for m in openers if stdin and m.start() > stdin.start()), None)
        heredocs += [(m.group(3), m.group(1) == "-", m is first) for m in openers]
        shell_text = line[1:] if resumed else line
        quote = open_single_quote(shell_text)
        if not openers and quote is not None and C_PROGRAM.search(shell_text[:quote]):
            in_program = True


def discover(root: Path) -> tuple[list[str], list[str]]:
    """Return (covered scripts, findings) from the workflows' run text."""
    findings: list[str] = []
    queue: list[str] = []
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        findings.append("no workflow found")
    for path in workflows:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            findings.append(f"{path.relative_to(root)}: cannot be read ({exc})")
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        for job in (jobs or {}).values():
            for step in (job.get("steps") or []) if isinstance(job, dict) else []:
                run = step.get("run") if isinstance(step, dict) else None
                if isinstance(run, str):
                    queue += [f"tools/{m.group(1)}.sh" for m in SCRIPT_NAME.finditer(run)
                              if (root / "tools" / f"{m.group(1)}.sh").is_file()]
    covered: list[str] = []
    while queue:
        rel = queue.pop(0)
        if rel in covered:
            continue
        covered.append(rel)
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{rel}: cannot be read ({exc})")
            continue
        for _, line, _ in script_lines(text):
            queue += [f"tools/{m.group(1)}.sh" for m in SCRIPT_NAME.finditer(line)
                      if (root / "tools" / f"{m.group(1)}.sh").is_file()]
    return sorted(covered), findings


def scan_tree(root: Path, expected=EXPECTED_SCRIPTS, exceptions=EXCEPTIONS) -> tuple[list[str], list[str]]:
    """Return (findings, covered scripts)."""
    covered, findings = discover(root)
    findings += [f"{rel}: a script the workflows run that the discovery did not reach"
                 for rel in expected if rel not in covered]
    used = [False] * len(exceptions)
    for rel in covered:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line, heredoc in script_lines(text):
            reasons = line_findings(line)
            if not reasons:
                continue
            excused = False
            for n, (path, pattern, heredocs, _) in enumerate(exceptions):
                if path == rel and re.fullmatch(pattern, line.strip()) and (heredoc in heredocs if heredocs else heredoc is None):
                    used[n] = excused = True
            if not excused:
                findings += [f"{rel}:{number}: {reason}: {line.strip()[:100]}" for reason in reasons]
    findings += [f"{path}: the exception for {pattern!r} matches no line" for (path, pattern, _, _), hit
                 in zip(exceptions, used) if not hit]
    return findings, covered


# ---------------------------------------------------------------- self-tests

# Shell lines that must be refused (True) or must pass (False).
LINE_CASES = [
    ("python3 tools/x.py", True),
    ("python3 -c 'print(1)'", True),
    ('python3 - "$1" <<\'PY\'', True),
    ("x=$(git show HEAD:f | python3 tools/x.py)", True),
    ('"python3" -I tools/x.py', True),
    ('"${PYTHON:-python3}" -I tools/x.py', True),
    ('cat > "$bin/python3" <<PY', True),
    ("python3 -X utf8 tools/x.py", True),
    ("python3  -I tools/x.py", True),
    ("python3 --version", True),
    ("tools/x.py --check", True),
    ("  tools/x.py", True),
    ('"tools/x.py"', True),
    ("v=$(tools/x.py)", True),
    ("true && tools/x.py", True),
    ("if ! tools/x.py; then exit 1; fi", True),
    ("LC_ALL=C tools/x.py", True),
    ("exec ./x.py", True),
    ("env A=b tools/x.pyz", True),
    ("  *) tools/x.py ;;", True),
    ("{ tools/x.py; }", True),
    ("nice -n 5 tools/x.py", True),
    ("env -i A=b tools/x.py", True),
    ("time -p ./x.py", True),
    ("python3 -I tools/x.py; python3.12 tools/y.py", True),
    ("2>/dev/null tools/x.py", True),
    ("> \"$log\" LC_ALL=C tools/x.py", True),
    ("echo `tools/x.py`", True),
    ("x=`python3 tools/x.py`", True),
    ('"gate=tools/x.py"', True),
    ("python3 -I tools/check-python-version.py", False),
    ('echo "see https://docs.python.org/3/"', False),
    ("ipython3 -I tools/x.py", False),
    ("gate=tools/x.py", False),
    ("gate=tools/x.py next=tools/y.py", False),
    ('test -f .python-version && python3 -I tools/x.py', False),
    ('cp "$(dirname "$0")/x.py" "${dir}/x.py"', False),
    ('case "${tag}" in', False),
    ("nice -n 5 python3 -I tools/x.py", False),
    ("python3 -I tools/x.py", False),
    ("python3 -I -c 'print(1)'", False),
    ('python3 -I - "$1" <<\'PY\'', False),
    ("x=$(git show HEAD:f | python3 -I tools/x.py)", False),
    ('entry=(python3 -I "$tmp/x.py")', False),
    ('exec python3 -I "${here}x.py" "$@"', False),
    ('PATH="$bin:$PATH" python3 -I -B -c "$launch"', False),
    ('echo "pages-build: python3 -I $*"', False),
    ('fail "tools/x.py is unavailable"', False),
    ('cp tools/x.py "${dir}/tools/x.py"', False),
    ('[ ! -f "${here}x.py" ] || [ -L "${here}x.py" ]', False),
    ("grep -Fc 'python3 -I tools/x.py' f", False),
    ("PYTHONPATH=x bash tools/a.sh", False),
    ("echo Python 3.11 is required", False),
]

# (script text, wanted findings as (line number, rule start)).
SCRIPT_CASES = [
    ("# python3 tools/x.py\necho ok\n", []),
    ("python3 -I \\\n  tools/x.py\n", []),
    ("python3 \\\n  -I tools/x.py\n", [(1, "python")]),
    ("python3 -I - <<'PY'\nimport x\nrun('python3 y.py')\nPY\npython3 y.py\n", [(5, "python")]),
    ("cat > f <<'EOF'\npython3 tools/x.py\nEOF\n", [(2, "python")]),
    ("cat > f <<-EOF\n\tpython3 tools/x.py\n\tEOF\npython3 z.py\n", [(2, "python"), (4, "python")]),
    ("python3 -I -c '\nimport os\nos.system(\"python3 y.py\")\n' tools/x.py\n", []),
    ("python3 -I -c '\nprint(1)\n' && tools/x.py\n", [(3, "a .py")]),
    ("python3 -I -c '\nprint(1)' \\\n  \"$f/x.py\" && python3 y.py\n", [(2, "python")]),
    ("python3 -I -c '\nprint(1)\n' \"$f\" && python3 y.py\n", [(3, "python")]),
    ("read -r a <<<\"$b\"\npython3 y.py\n", [(2, "python")]),
    ("case \"$t\" in\n  *) tools/x.py ;;\nesac\n", [(2, "a .py")]),
    ("echo \"python3 -I can't be skipped\"\npython3 y.py\n", [(2, "python")]),
    ("python3 -I x.py # it's read\npython3 y.py\n", [(2, "python")]),
    ("python3 -I x.py; bash -c '\npython3 y.py\n'\n", [(2, "python")]),
    ("v=\"$(python3 -I -c '\nimport os\nos.system(\"python3 y.py\")\n')\"\n", []),
    ("cat > \"$b/python3\" <<PY\npython3 y.py\nPY\n", [(1, "python"), (2, "python")]),
    ("python3 -I tools/x.py <<EOF\npython3 y.py\nEOF\n", [(2, "python")]),
    ("python3 -I -B - \"$1\" <<\"PY\"\nimport x\nPY\n", []),
    ("# note \\\npython3 tools/x.py\n", [(2, "python")]),
    ("# note \\\ntools/x.py\n", [(2, "a .py")]),
    ("echo x # note \\\ntools/x.py\n", [(2, "a .py")]),
    ("python3 -I \\\n  x.py # note \\\npython3 y.py\n", [(3, "python")]),
]


def self_test() -> list[str]:
    errors: list[str] = []
    for line, want in LINE_CASES:
        if bool(line_findings(line)) != want:
            errors.append(f"self-test: line {line!r}: expected {'a finding' if want else 'none'}")
    for text, want in SCRIPT_CASES:
        got = [(n, reason) for n, line, _ in script_lines(text) for reason in line_findings(line)]
        if [(n, r.split()[0]) for n, r in got] != [(n, w.split()[0]) for n, w in want]:
            errors.append(f"self-test: script {text!r}: expected {want!r}, got {got!r}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "tools").mkdir()
        (root / ".github" / "workflows" / "w.yml").write_text(
            "on: push\njobs:\n  j:\n    steps:\n      - run: bash tools/a.sh\n", encoding="utf-8")
        (root / "tools" / "a.sh").write_text("#!/usr/bin/env bash\n# tools/c.sh\n# a comment ends at its line, backslash or not \\\ntools/b.sh\n", encoding="utf-8")
        (root / "tools" / "b.sh").write_text("python3 -I tools/x.py\nprobe=$(python3 --version)\n", encoding="utf-8")
        (root / "tools" / "c.sh").write_text("python3 tools/x.py\n", encoding="utf-8")
        exception = (("tools/b.sh", r"probe=\$\(python3 --version\)", (), "r"),)
        findings, covered = scan_tree(root, ("tools/a.sh", "tools/b.sh"), exception)
        if covered != ["tools/a.sh", "tools/b.sh"] or findings:
            errors.append(f"self-test: discovery gave {covered!r} and {findings!r}")
        findings, _ = scan_tree(root, ("tools/a.sh", "tools/c.sh"), exception)
        if not any("tools/c.sh: a script the workflows run" in f for f in findings):
            errors.append("self-test: an expected script the discovery missed gave no finding")
        findings, _ = scan_tree(root, ("tools/a.sh",), ())
        if not any(f.startswith("tools/b.sh:2: python") for f in findings):
            errors.append("self-test: a line outside the exceptions gave no finding")
        findings, _ = scan_tree(root, ("tools/a.sh",), exception + (("tools/b.sh", r"gone", (), "r"),))
        if not any("matches no line" in f for f in findings):
            errors.append("self-test: an exception that matches no line gave no finding")
        findings, _ = scan_tree(root, ("tools/a.sh",), (("tools/b.sh", r"probe=\$\(python3 --version\)", ("EOF",), "r"),))
        if not any(f.startswith("tools/b.sh:2:") for f in findings):
            errors.append("self-test: an exception for a here-document excused a line outside it")
    return errors


def main() -> int:
    errors = self_test()
    if errors:
        for error in errors:
            print(error)
        print(f"FAIL: {len(errors)} self-test failure(s)")
        return 1
    findings, covered = scan_tree(REPO)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s) in {len(covered)} shell scripts")
        return 1
    print(f"OK: {len(covered)} shell scripts the workflows run, every Python launch python3 -I")
    return 0


if __name__ == "__main__":
    sys.exit(main())
