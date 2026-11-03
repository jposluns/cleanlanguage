#!/usr/bin/env python3
"""Check that every Python launch in the workflows and local actions runs isolated.

Scope. This check catches an honest or accidental Python launch without `-I`.
It reads the YAML structurally, so prose such as a step name or an issue form
is never scanned, and it reads each run string as text, so a launch is found
wherever it sits: behind any wrapper, keyword or option, or in a
here-document. It is a scan of the pull request's own checkout, so it is no
defence against deliberate obfuscation: the author of such a change can also
edit this scan, and only review catches that.

A Python-launched gate that finds a planted file on its module path can import
that file in place of a standard-library module and turn the gate into a green
run that checked nothing. `python3 -I` keeps the script folder off the module
path and ignores the user site directory and every PYTHON* variable.

What is checked:

1. Every .yml and .yaml file under .github, in every subfolder, is parsed with
   PyYAML's safe loader. A folder or file that cannot be listed or read as
   UTF-8, a file that cannot be parsed, a repeated mapping key, a symbolic link
   under .github, and U+0085, U+2028 or U+2029 (which YAML 1.1 and 1.2 read
   differently) are findings. With no YAML file at all, the floor fails too.
2. A file directly in .github/workflows must be a workflow with a jobs mapping,
   and a file named action.yml or action.yaml anywhere under .github must be a
   local action with `runs.using: composite`; a Docker or JavaScript entry
   point is refused rather than read. Other YAML files, such as issue forms,
   are only parsed. From workflows and actions the scan collects every `run`,
   `uses` and `shell` of a step, each job's `uses`, and each `defaults.run`
   shell. A jobs or job value that is not a mapping, a steps value that is not
   a list, and a step that is not a mapping are findings; a missing steps
   list is not, and keys other than those named here are not read.
3. Each `uses` must be `<owner>/<repo>[/<path>]@<40 hex digits>`, or
   `./.github/<path>` with no `..` that names an existing file or a folder
   holding action.yml or action.yaml. Each `shell` must start with bash or
   sh, since run text is read as bash; pwsh, powershell and cmd are refused.
4. In each run string, with every backslash-newline removed and nothing else
   dropped (comments and here-document bodies included):
   - Interpreter rule: every word matching
     `(?<![\\w./\\\\-])(?:\\S*[/\\\\])?python[0-9.]*[a-z]?(?:\\.exe)?(?![\\w.-])`
     must be followed by whitespace and then `-I` as a whole word, unless it
     stands at the start of its line, directly after `|`, or after `in ` or
     `;;`, and is directly followed by `)` or `|`, where it is read as a
     case pattern.
   - Script rule: every `tools/<name>.py` must be preceded on its line by
     `python3 -I`, then only words that start with `-`, then whitespace and an
     optional quote. A line that is not a launch, such as an echo message that
     names a tool, passes only when the exact line, stripped of surrounding
     spaces, is listed for its file in ALLOWED_LINES. A listed line that no
     longer exists is a finding, so the list stays exact.
   - A word holding `python` or a `.py` name only once its quotes and
     backslashes are removed, the word `eval`, a `./<name>.py`, and a pipe
     into sh, bash, dash, zsh or ksh other than one that runs a `.sh` file,
     are findings; a `|` inside quotes on its line is not a pipe.
   - Each launch the script rule accepts on a line that is not a shell comment
     counts toward LAUNCH_FLOOR, and its script must exist.
5. Every .py file under tools/ is read as tokens, and it fails when its code
   changes `sys.path`: assignment, augmented assignment, item assignment or
   deletion, or any method other than copy, index and count, on `sys.path`
   written through `sys` or any `sys as` alias, with or without parentheses.
   Any reference to meta_path, path_hooks or path_importer_cache, any import
   of those names or `path` from sys, and site.addsitedir also fail.
6. Tempfile.py, msvcrt.py, nt.py and _winapi.py are planted beside a copy of
   each script in PROBE_SCRIPTS, the copy runs under `-I`, and the scan fails
   if a planted module ran.

It runs its own self-tests first and stops on any failure. They run the whole
scan on temporary trees, with a case only each rule catches, the honest forms
the reviewers listed, which must pass, and their unisolated forms, which must
fail.

Residuals, named here because the scan reads text the pull request controls:

- a launch built from parts or variables, such as an interpreter or script
  name held in a variable, a glob, brace or parameter expansion, a `${{ }}`
  expression, or a file written and then run;
- other launchers, such as py, pytest, coverage, uv, pipx or an extensionless
  script, and shell scripts the workflows run;
- remote actions and reusable workflows, which are outside this repository;
- obfuscation, such as ANSI-C strings, YAML escapes the line text hides, or a
  function or alias under a name that does not spell python;
- an accepted launch in text bash never runs, such as a quoted message or a
  here-document body, which still counts toward the floor;
- isolated launches written another way, such as `python3 -B -I`,
  `python3 -IB`, `python -I` or `python3 -I ./tools/<name>.py`, and a line that
  names tools/<name>.py without launching it unless it is listed, are refused;
  write a launch as `python3 -I tools/<name>.py`;
- a launch written like a case pattern, such as `python|grep x` at the start
  of a line, which the case-pattern reading lets through; a message that
  names `python3` without `-I` is refused although it launches nothing;
- a sys.path change made other than in the forms above, such as through
  getattr or a list bound to sys.path.

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

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent

# The number of accepted launches under .github when this check landed.
LAUNCH_FLOOR = 51

# Lines that name a tool without launching it, by file, exactly as they stand
# once stripped of surrounding spaces.
ALLOWED_LINES: dict[str, tuple[str, ...]] = {
    ".github/workflows/release-skill.yml": (
        "# extractor, tools/skill-version.py, reads and validates it for every",
        "# published_at, interpreted only by tools/skill-release-date.py",
        'echo "tools/skill-release-date.py is unavailable or crashed (exit $1) while $2, so the release date cannot be checked." >&2',
        '1) echo "tools/skill-release-date.py rejected the version ${VERSION} (see the error above)." >&2; exit 1 ;;',
        '*) echo "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for ${VERSION}." >&2; exit 1 ;;',
        "# left before UTC midnight (tools/skill-release-date.py",
        'echo "tools/skill-release-date.py is unavailable or crashed (exit $1) while $2." >&2',
        "# Released day, decided only by tools/skill-release-date.py",
        "# observation that tools/check-release-checksum-live.py defers to.",
        "# (tools/test-release-skill-workflow.py fails if the workflow names",
        'echo "The published zip carries Released: ${RELEASE_DATE}, and an immutable release cannot be '
        "republished, so the remedy is a corrective new version whose Released line names its own "
        'publication day; tools/check-release-checksum-live.py reports the same disagreement until then." >&2',
    ),
}

# Launched scripts that load sibling modules, checked with planted modules.
PROBE_SCRIPTS = (
    "tools/check-page-metadata.py",
    "tools/generate-sitemap.py",
    "tools/test-sitemap.py",
)
PLANTED_MODULES = ("tempfile", "msvcrt", "nt", "_winapi")
PLANT_MARKER = "PLANTED-MODULE-RAN"

YAML_DISAGREEMENT = {"\x85": "U+0085", "\u2028": "U+2028", "\u2029": "U+2029"}
REMOTE_USES = re.compile(r"[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}")
LOCAL_USES = re.compile(r"\./\.github/[\w./-]+")
SHELLS_ALLOWED = ("bash", "sh")

INTERPRETER = re.compile(r"(?<![\w./\\-])(?:\S*[/\\])?python[0-9.]*[a-z]?(?:\.exe)?(?![\w.-])")
CASE_PATTERN_BEFORE = re.compile(r"(?:^[ \t]*|\||\bin[ \t]+|;;[ \t]*)$")
ISOLATED = re.compile(r"\s+-I(?=\s|$)")
SCRIPT = re.compile(r"tools/[\w.-]+\.py(?![\w])")
LAUNCH_BEFORE = re.compile(r"(?<![\w./-])(?:\S*/)?python3 -I(?:\s+-\S*)*\s+[\"']?$")
PY_NAME = re.compile(r"\.py(?![\w])")
DOT_SLASH = re.compile(r"(?<![\w.-])\./[\w./-]*\.py(?![\w])")
EVAL = re.compile(r"(?<![\w./-])eval(?![\w.-])")
PIPE_TO_SHELL = re.compile(r"(?<!\|)\|(?!\|)\s*(?:\S*/)?(?:ba|da|z|k)?sh(?![\w.-])(?!\s+[\w./-]+\.sh(?=\s|$))")


def quoted(line: str, index: int) -> bool:
    """Return True when the character at `index` sits inside quotes on its line."""
    state = None
    i = 0
    while i < index:
        c = line[i]
        if state != "'" and c == "\\":
            i += 2
            continue
        if state is None and c in "'\"":
            state = c
        elif c == state:
            state = None
        i += 1
    return state is not None


def check_run(text: str) -> tuple[list[str], list[tuple[str, str, bool]]]:
    """Return (findings, launches) for one run string.

    Each launch is (script, line, counted); a launch is counted unless its line
    is a shell comment.
    """
    findings: list[str] = []
    launches: list[tuple[str, str, bool]] = []
    for line in text.replace("\\\n", "").split("\n"):
        comment = line.lstrip(" \t").startswith("#")
        for match in INTERPRETER.finditer(line):
            if line[match.end() : match.end() + 1] in (")", "|") and CASE_PATTERN_BEFORE.search(line[: match.start()]):
                continue
            if not ISOLATED.match(line, match.end()):
                findings.append(f"{match.group(0)} is not followed by -I: {line.strip()[:100]}")
        for match in SCRIPT.finditer(line):
            if LAUNCH_BEFORE.search(line[: match.start()]):
                launches.append((match.group(0), line.strip(), not comment))
            else:
                launches.append((match.group(0), line.strip(), None))
        for word in line.split():
            plain = re.sub(r"[\"'\\]", "", word)
            if ("python" in plain and "python" not in word) or (PY_NAME.search(plain) and not PY_NAME.search(word)):
                findings.append(f"a quote or backslash inside python or a .py name: {word}")
        if DOT_SLASH.search(line):
            findings.append(f"a ./<name>.py: {line.strip()[:100]}")
        if EVAL.search(line):
            findings.append(f"eval runs text the scan cannot read: {line.strip()[:100]}")
        if any(not quoted(line, m.start()) for m in PIPE_TO_SHELL.finditer(line)):
            findings.append(f"a pipe into a shell: {line.strip()[:100]}")
    return findings, launches


class UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses a mapping with a repeated key."""


def _construct_mapping(loader, node, deep=False):
    keys = []
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        keys.append(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


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
            if (Path(folder) / name).is_symlink():
                errors.append(f"{(Path(folder) / name).relative_to(root)}: a symbolic link under .github")
        files += [Path(folder) / n for n in names if n.endswith((".yml", ".yaml"))]
    return sorted(files), errors


def collect_steps(steps, where: str, found: list, items: dict) -> None:
    if steps is None:
        return
    if not isinstance(steps, list):
        found.append(f"{where}.steps: not a list")
        return
    for n, step in enumerate(steps):
        label = f"{where}.steps[{n}]"
        if not isinstance(step, dict):
            found.append(f"{label}: not a mapping")
            continue
        for key in ("run", "uses", "shell"):
            if key in step:
                items[key].append((label, step[key]))


def collect_shell_default(node, where: str, items: dict) -> None:
    if isinstance(node, dict) and isinstance(node.get("defaults"), dict):
        run = node["defaults"].get("run")
        if isinstance(run, dict) and "shell" in run:
            items["shell"].append((f"{where}.defaults.run", run["shell"]))


def collect(path: Path, doc, workflows: Path, found: list, items: dict) -> None:
    if path.name in ("action.yml", "action.yaml"):
        runs = doc.get("runs") if isinstance(doc, dict) else None
        if not isinstance(runs, dict):
            found.append("runs: a local action with no runs mapping")
        elif runs.get("using") != "composite":
            found.append(f"runs.using: {runs.get('using')!r}, not composite, so its code cannot be read")
        else:
            collect_steps(runs.get("steps"), "runs", found, items)
    elif path.parent == workflows:
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        if not isinstance(jobs, dict):
            found.append("jobs: a workflow with no jobs mapping")
            return
        collect_shell_default(doc, "workflow", items)
        for job_id, job in jobs.items():
            where = f"jobs.{job_id}"
            if not isinstance(job, dict):
                found.append(f"{where}: not a mapping")
                continue
            if "uses" in job:
                items["uses"].append((where, job["uses"]))
            collect_shell_default(job, where, items)
            collect_steps(job.get("steps"), where, found, items)


def scan_tree(root: Path, floor: int, probe_scripts, allowed: dict) -> tuple[list[str], int]:
    """Scan the YAML under root/.github; return (findings, number of counted launches)."""
    files, findings = list_yaml(root)
    if not files:
        findings.append(f"no YAML file found under {root / '.github'}")
    workflows = root / ".github" / "workflows"
    counted = 0
    seen_allowed: set[tuple[str, str]] = set()
    for path in files:
        rel = str(path.relative_to(root))
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{rel}: cannot be read as UTF-8 ({exc})")
            continue
        for char, name in YAML_DISAGREEMENT.items():
            if char in text:
                findings.append(f"{rel}: holds {name}, which YAML 1.1 and 1.2 read differently")
        try:
            doc = yaml.load(text, Loader=UniqueKeyLoader)
        except yaml.YAMLError as exc:
            findings.append(f"{rel}: cannot be parsed as YAML ({str(exc).splitlines()[0]})")
            continue
        found: list[str] = []
        items: dict = {"run": [], "uses": [], "shell": []}
        collect(path, doc, workflows, found, items)
        for where, value in items["uses"]:
            if not isinstance(value, str):
                found.append(f"{where}.uses: not a string")
            elif LOCAL_USES.fullmatch(value) and ".." not in value.split("/"):
                target = root / value
                if not (target.is_file() or any((target / n).is_file() for n in ("action.yml", "action.yaml"))):
                    found.append(f"{where}.uses: {value} names no action or workflow file")
            elif not REMOTE_USES.fullmatch(value):
                found.append(f"{where}.uses: {value!r} is neither pinned to a full commit nor a path under .github")
        for where, value in items["shell"]:
            first = value.split()[0].rsplit("/", 1)[-1] if isinstance(value, str) and value.split() else None
            if first not in SHELLS_ALLOWED:
                found.append(f"{where}.shell: {value!r} is not bash or sh, the shells this scan reads")
        for where, value in items["run"]:
            if isinstance(value, (bool, int, float)):
                value = str(value)
            if not isinstance(value, str):
                found.append(f"{where}.run: not text")
                continue
            run_findings, run_launches = check_run(value)
            found += [f"{where}.run: {reason}" for reason in run_findings]
            for script, line, count in run_launches:
                if count is None:
                    if line in allowed.get(rel, ()):
                        seen_allowed.add((rel, line))
                    else:
                        found.append(f"{where}.run: {script} is not launched as python3 -I: {line[:100]}")
                    continue
                if not (root / script).is_file():
                    found.append(f"{where}.run: launched script {script} does not exist")
                counted += 1 if count else 0
        findings += [f"{rel}: {reason}" for reason in found]

    for rel, lines in allowed.items():
        for line in lines:
            if (rel, line) not in seen_allowed:
                findings.append(f"{rel}: the allowed line is no longer present: {line[:100]}")

    tools = root / "tools"
    for path in sorted(tools.rglob("*.py")) if tools.is_dir() else []:
        if "__pycache__" in path.parts:
            continue
        try:
            changes = mutates_sys_path(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError, tokenize.TokenError) as exc:
            findings.append(f"{path.relative_to(root)}: cannot be read as Python ({exc})")
            continue
        if changes:
            findings.append(f"{path.relative_to(root)}: changes sys.path")

    if counted < floor:
        findings.append(f"only {counted} accepted launches found, below the floor of {floor}")

    for script in probe_scripts:
        failure = planted_module_runs(root, script)
        if failure:
            findings.append(failure)
    return findings, counted


PATH_NAMES = ("path", "meta_path", "path_hooks", "path_importer_cache")
READ_ONLY = ("copy", "index", "count")


def mutates_sys_path(source: str) -> bool:
    """Return True when Python source changes sys.path in its code (not its strings)."""
    tokens = [
        ";" if t.type == tokenize.NEWLINE else t.string
        for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type in (tokenize.NAME, tokenize.OP, tokenize.NEWLINE)
    ]
    changed = True
    while changed:
        changed = False
        for i, token in enumerate(tokens):
            if token != "(" or (i and (tokens[i - 1] in (")", "]") or tokens[i - 1].isidentifier())):
                continue
            j = i + 1
            while j + 1 < len(tokens) and tokens[j].isidentifier() and tokens[j + 1] == ".":
                j += 2
            if j + 1 < len(tokens) and tokens[j].isidentifier() and tokens[j + 1] == ")":
                tokens = tokens[:i] + tokens[i + 1 : j + 1] + tokens[j + 2 :]
                changed = True
                break
    aliases = {"sys"}
    for i, token in enumerate(tokens):
        if tokens[i : i + 2] == ["sys", "as"] and i + 2 < len(tokens):
            aliases.add(tokens[i + 2])
        if tokens[i : i + 3] == ["from", "sys", "import"]:
            j = i + 3
            while j < len(tokens) and tokens[j] != ";":
                if tokens[j] in PATH_NAMES + ("*",):
                    return True
                j += 1
        if tokens[i : i + 3] == ["site", ".", "addsitedir"]:
            return True
    for i, token in enumerate(tokens):
        if token not in aliases or tokens[i + 1 : i + 2] != ["."] or i + 2 >= len(tokens):
            continue
        attr = tokens[i + 2]
        if attr not in PATH_NAMES:
            continue
        if attr != "path" or (i and tokens[i - 1] == "del"):
            return True
        following = tokens[i + 3 : i + 5]
        if following[:1] in (["="], ["+="], ["-="], ["|="], ["*="]):
            return True
        if following[:1] == ["."] and following[1:2] and following[1] not in READ_ONLY:
            return True
        if following[:1] == ["["]:
            depth, j = 0, i + 3
            while j < len(tokens):
                depth += {"[": 1, "]": -1}.get(tokens[j], 0)
                if depth == 0:
                    break
                j += 1
            if tokens[j + 1 : j + 2] and tokens[j + 1] in ("=", "+=", "-=", "|=", "*="):
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


# ---------------------------------------------------------------- self-tests

PIN = "11d5960a326750d5838078e36cf38b85af677262"
X = "tools/x.py"

# Run text that must give a finding (True) or must pass (False).
RUN_CASES = [
    # Interpreter rule
    (f"python3 {X}", True),
    (f"python {X}", True),
    (f".venv/bin/python3 {X}", True),
    (f'"$pythonLocation/bin/python3" -I {X}', True),
    (f"python3.13t {X}", True),
    (f"python3 -B -I {X}", True),
    (f"python3 -XI {X}", True),
    ("python3 --version", True),
    (f"nice -n 10 python3 {X}", True),
    (f"timeout -k 5 300 python3 {X}", True),
    (f"env -u PYTHONPATH python3 {X}", True),
    (f"sudo -u runner python3 {X}", True),
    (f"time -p python3 {X}", True),
    (f"xargs -n 1 python3 {X}", True),
    (f"/usr/bin/env python3 {X}", True),
    (f"command python3 {X}", True),
    (f"coproc python3 {X}", True),
    (f"function gate {{ python3 {X}; }}", True),
    (f"links=${{LINKS:-$(python3 {X})}}", True),
    (f'cat <<EOF >> "$GITHUB_STEP_SUMMARY"\nLinks: $(python3 {X})\nEOF', True),
    (f"cat <<EOF\nLinks: `python3 {X}`\nEOF", True),
    (f"python3 \\\n  {X}", True),
    (f"true\\\n# || python3 {X}", True),
    ("PY=python3", True),
    ("C:\\Python312\\python.exe tools/x.py", True),
    ('& "$env:pythonLocation\\python.exe" tools/x.py', True),
    ("python3.exe -c 'x'", True),
    ("C:\\Python312\\python.exe -c 'x'", True),
    ("echo x | python)", True),
    ("$(python)", True),
    ("python3 -E -c 'x'", True),
    (".venv/bin/python3 -c 'x'", True),
    ("python3.12 -c 'x'", True),
    ("python3.13t -c 'x'", True),
    ("p''ython3 -c 'x'", True),
    (f"# python3 {X} in a comment", True),
    # Script rule
    (X, True),
    (f'"{X}"', True),
    (f'out="$({X})"', True),
    (f"exec {X}", True),
    (f"python3 -I -X utf8 {X}", True),
    (f"echo {X}", True),
    # Cheap closes
    (f"p''ython3 -I {X}", True),
    (f"pyth\\on3 -I {X}", True),
    ("cp tools/x.p''y out", True),
    ("cd tools && ./x.py", True),
    ("eval true", True),
    ("echo true | sh", True),
    ("echo true | bash -s", True),
    # Honest forms that must pass
    (f"python3 -I {X}", False),
    (f"python3 -I -B {X}", False),
    (f"/usr/bin/python3 -I {X}", False),
    (f'python3 -I "{X}"', False),
    (f"python3 -I {X};", False),
    (f"python3 -I {X}\t--flag", False),
    (f"python3 -I \\\n  {X}", False),
    (f"if python3 -I {X}; then echo ok; fi", False),
    (f"if ! python3 -I {X}; then exit 1; fi", False),
    (f"LC_ALL=C python3 -I {X}", False),
    (f"test -f site/x || python3 -I {X}", False),
    (f"true && python3 -I {X} && python3 -I {X}", False),
    (f"timeout 300 python3 -I {X}", False),
    (f"nice -n 10 python3 -I {X}", False),
    (f"timeout -k 5 300 python3 -I {X}", False),
    (f"env -u PYTHONPATH python3 -I {X}", False),
    (f"sudo -u runner python3 -I {X}", False),
    (f"time -p python3 -I {X}", False),
    (f"xargs -n 1 python3 -I {X}", False),
    (f"/usr/bin/env python3 -I {X}", False),
    (f"command python3 -I {X}", False),
    (f"coproc python3 -I {X}", False),
    (f"function gate {{ python3 -I {X}; }}", False),
    (f"links=${{LINKS:-$(python3 -I {X})}}", False),
    (f'cat <<EOF >> "$GITHUB_STEP_SUMMARY"\nLinks: $(python3 -I {X})\nEOF', False),
    (f"diff <(python3 -I {X}) site/y", False),
    (f"python3 -I {X} site/x.py", False),
    ("python3 -I tools/check-python-version.py", False),
    (f'v="$(git show X | python3 -I {X})"', False),
    (f"python3 -I {X} --a \"$(date -u +%Y)\" >/dev/null || rc=$?", False),
    ('printf "%s\\n" "${x}"', False),
    ('grep -Eq "^v[0-9]+\\.[0-9]+$" <<< "${v}"', False),
    ('echo "notes<<EOF" >> "$GITHUB_OUTPUT"', False),
    ("cat <<EOF >> \"$GITHUB_STEP_SUMMARY\"\nIt's done.\nEOF", False),
    ('cp out.txt "$RUNNER_TEMP"/out.txt', False),
    ('gh release create "v${{ env.VERSION }}"', False),
    ("jq -n '{a: {b: 1}}'", False),
    ('echo "It\'s done"', False),
    ("cd x && bash tools/y.sh", False),
    ("echo input | bash tools/x.sh", False),
    ('echo "pipe it | sh" >&2', False),
    ("# it's a comment that names Python", False),
    ('case "$f" in *.py) echo yes ;; esac', False),
    ("echo $(( 1 << 2 ))", False),
    ('case "$f" in\n  *.py) echo "a .py file" ;;\n  python|python3) echo "an interpreter" ;;\nesac', False),
    ('out="$(case "$e" in push) echo push ;; *.py) echo py ;; esac)"', False),
    ('case "$x" in python3) echo yes ;; python|py) echo no ;; esac', False),
    (f'out="$(case "$e" in push) python3 {X} ;; *) echo skip ;; esac)"', True),
    ('gh release download x \\\n  --pattern "a.zip"', False),
    ("awk '$2 ~ /\\^\\{\\}$/ { print $1 }' f", False),
    ("python3 -I -c 'print(1)'", False),
]

STEP_CASES = [
    ("name: Check the site's links\n        run: echo ok", False),
    ("name: Check the source links\n        run: echo ok", False),
    ("name: Confirm the release uses the pinned checksum\n        run: echo ok", False),
    ("name: Run the bash selector tests with python3\n        run: echo ok", False),
    ("name: Check \u2014 headers\n        run: echo ok", False),
    ("shell: bash\n        run: python3 -I tools/x.py", False),
    ("shell: bash # strict\n        run: echo ok", False),
    ("shell: bash -e {0}\n        run: echo ok", False),
    ("shell: sh\n        run: echo ok", False),
    ("shell: pwsh\n        run: echo ok", True),
    ("shell: cmd\n        run: echo ok", True),
    (f"uses: actions/setup-python@{PIN}\n        with:\n          python-version: \"3.12\"", False),
    (f'uses: "actions/checkout@{PIN}"', False),
    (f"uses: actions/checkout@{PIN}\n        with:\n          ref: v${{{{ inputs.version }}}}", False),
    ("if: hashFiles('**/*.py') != ''\n        run: echo ok", False),
    ("run: 12", False),
    ("shell: python\n        run: print(1)", True),
    ("shell: /usr/bin/python {0}\n        run: print(1)", True),
    ("uses: actions/checkout@v4", True),
    ("uses: docker://alpine:3", True),
    ("uses: ./actions/m", True),
    ("uses: ./.github/workflows/../actions/m", True),
    ("uses: ./.github/actions/none", True),
    ("uses: [a]", True),
    ("run: [a, b]", True),
    ("run: echo ok\n        run: python3 tools/x.py", True),
]


def self_test() -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = root / "tools"
        tools.mkdir()
        for name in ("a", "x", "check-python-version"):
            (tools / f"{name}.py").write_text("import tempfile\n", encoding="utf-8")
        missing, _ = scan_tree(root, 1, (), {})
        if not any("cannot list" in f for f in missing):
            errors.append("self-test: a missing .github folder gave no finding")
        github = root / ".github"
        workflows = github / "workflows"
        workflows.mkdir(parents=True)
        empty, _ = scan_tree(root, 1, (), {})
        if not any("no YAML file" in f for f in empty) or not any("below the floor" in f for f in empty):
            errors.append("self-test: an empty .github did not report both no YAML and the floor")
        case = workflows / "case.yml"
        rel = ".github/workflows/case.yml"
        head = "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python3 -I tools/a.py\n"

        def scan(floor: int = 1, probe=(), allowed=None) -> list[str]:
            return scan_tree(root, floor, probe, allowed or {})[0]

        def run_case(text: str, **kw) -> list[str]:
            body = "".join(f"          {line}\n" for line in text.split("\n"))
            case.write_text(head + "      - shell: bash\n        run: |\n" + body, encoding="utf-8")
            return scan(**kw)

        for text, want in RUN_CASES:
            if bool(run_case(text)) != want:
                errors.append(f"self-test: run {text!r}: expected {'a finding' if want else 'none'}")
        for text, want in STEP_CASES:
            case.write_text(head + f"      - {text}\n", encoding="utf-8")
            if bool(scan()) != want:
                errors.append(f"self-test: step {text!r}: expected {'a finding' if want else 'none'}")

        message = 'echo "tools/x.py is unavailable (exit $1)." >&2'
        if not run_case(message):
            errors.append("self-test: an unlisted line naming a tool gave no finding")
        if run_case(message, allowed={rel: (message,)}):
            errors.append("self-test: a listed line naming a tool gave a finding")
        if not any("no longer present" in f for f in run_case("echo ok", allowed={rel: (message,)})):
            errors.append("self-test: a stale allowed line gave no finding")

        case.write_text(head, encoding="utf-8")
        if scan():
            errors.append(f"self-test: a clean tree gave {scan()!r}")
        if not any("below the floor" in f for f in scan(floor=2)):
            errors.append("self-test: a launch count below the floor gave no finding")
        case.write_text(head + "      - run: |\n          # python3 -I tools/a.py\n", encoding="utf-8")
        if not any("below the floor" in f for f in scan(floor=2)):
            errors.append("self-test: a launch in a comment counted toward the floor")
        case.write_text(head + "      - run: python3 -I tools/gone.py\n", encoding="utf-8")
        if not any("does not exist" in f for f in scan()):
            errors.append("self-test: a missing launched script gave no finding")

        whole = [
            ("parse error", "on: [push\n", "cannot be parsed"),
            ("duplicate key", head + "jobs: {}\n", "cannot be parsed"),
            ("no jobs", "on: push\n", "no jobs"),
            ("U+2028", head + "      - run: echo \u2028\n", "U+2028"),
            ("U+0085", head + "      - run: echo \x85\n", "U+0085"),
            ("U+2029", head + "      - run: echo \u2029\n", "U+2029"),
            ("steps not a list", "on: push\njobs:\n  j:\n    steps: 1\n", "not a list"),
            ("step not a mapping", head + "      - 1\n", "not a mapping"),
            ("job not a mapping", "on: push\njobs:\n  j: 1\n", "not a mapping"),
            ("job uses unpinned", "on: push\njobs:\n  j:\n    uses: o/r/.github/workflows/w.yml@main\n", "pinned"),
            ("defaults shell python", "on: push\ndefaults:\n  run:\n    shell: python\n" + head[9:], "shell"),
            ("job defaults shell python", head.replace("    runs-on", "    defaults:\n      run:\n        shell: python\n    runs-on"), "shell"),
        ]
        for name, text, needle in whole:
            case.write_text(text, encoding="utf-8")
            if not any(needle in f for f in scan()):
                errors.append(f"self-test: whole file {name} gave no finding naming {needle!r}")
        merge = ("x: &c\n  runs-on: ubuntu-latest\non: push\njobs:\n  j:\n    <<: *c\n    steps:\n"
                 "      - run: python3 -I tools/a.py\n")
        case.write_text(merge, encoding="utf-8")
        if scan():
            errors.append(f"self-test: a YAML merge key gave {scan()!r}")
        case.write_bytes(b"\xef\xbb\xbf" + head.encode())
        if scan():
            errors.append("self-test: a byte-order mark gave a finding")
        case.write_text(head, encoding="utf-8")
        (workflows / "bad.yml").write_bytes(b"on: \xff\n")
        if not any("cannot be read" in f for f in scan()):
            errors.append("self-test: an unreadable workflow file gave no finding")
        (workflows / "bad.yml").unlink()

        form = github / "ISSUE_TEMPLATE"
        form.mkdir()
        (form / "bug.yml").write_text(
            "name: Bug\ndescription: Paste the output; we'll read it. Run python3 tools/x.py | sh.\nbody: []\n",
            encoding="utf-8",
        )
        if scan():
            errors.append("self-test: an issue form's prose gave a finding")
        shutil.rmtree(form)

        good = github / "actions" / "ok"
        good.mkdir(parents=True)
        composite = "name: ok\nruns:\n  using: composite\n  steps:\n    - shell: bash\n      run: python3 {}tools/a.py\n"
        (good / "action.yml").write_text(composite.format("-I "), encoding="utf-8")
        case.write_text(head + "      - uses: ./.github/actions/ok\n", encoding="utf-8")
        if scan():
            errors.append(f"self-test: a correct composite action gave {scan()!r}")
        (good / "action.yml").write_text(composite.format(""), encoding="utf-8")
        if not any("actions/ok/action.yml" in f for f in scan()):
            errors.append("self-test: a composite action's run text was not scanned")
        case.write_text(head + "      - uses: ./.github/workflows/../actions/ok\n", encoding="utf-8")
        if not any("neither pinned" in f for f in scan()):
            errors.append("self-test: a local uses through .. gave no finding")
        case.write_text(head + "      - uses: ./.github/actions/ok\n", encoding="utf-8")
        (good / "action.yml").write_text("name: ok\n", encoding="utf-8")
        if not any("no runs mapping" in f for f in scan()):
            errors.append("self-test: a local action with no runs gave no finding")
        (good / "action.yml").write_text("name: ok\nruns:\n  using: docker\n  image: Dockerfile\n", encoding="utf-8")
        if not any("not composite" in f for f in scan()):
            errors.append("self-test: a Docker local action gave no finding")
        shutil.rmtree(github / "actions")
        case.write_text(head, encoding="utf-8")

        sub = workflows / "sub"
        sub.mkdir()
        (sub / "action.yml").write_text(composite.format(""), encoding="utf-8")
        if not any("sub/action.yml" in f for f in scan()):
            errors.append("self-test: an action in a subfolder was not scanned")
        sub.chmod(0)
        real_scandir = os.scandir
        try:
            if os.access(sub, os.R_OK):
                # Running as root: make the folder unreadable to the walk instead.
                def denied(target="."):
                    if Path(target) == sub:
                        raise PermissionError(13, "Permission denied", str(sub))
                    return real_scandir(target)
                os.scandir = denied
            if not any("cannot list" in f for f in scan()):
                errors.append("self-test: an unreadable subfolder gave no finding")
        finally:
            os.scandir = real_scandir
            sub.chmod(0o700)
        shutil.rmtree(sub)

        outside = root / "outside"
        outside.mkdir()
        try:
            (github / "linked").symlink_to(outside, target_is_directory=True)
            (workflows / "link.yml").symlink_to(case)
        except OSError as exc:
            errors.append(f"self-test: could not make a symbolic link ({exc})")
        else:
            findings = scan()
            for name in (".github/linked", "workflows/link.yml"):
                if not any(name in f for f in findings):
                    errors.append(f"self-test: the symbolic link {name} gave no finding")
            (github / "linked").unlink()
            (workflows / "link.yml").unlink()

        detector = [
            ("import sys\nsys.path.insert(0, d)\n", True),
            ("import sys\nsys.path[:0] = [d]\n", True),
            ("import sys\nsys.path = [d]\n", True),
            ("import sys\nsys.path += [d]\n", True),
            ("import sys\ndel sys.path[0]\n", True),
            ("import sys\n(sys).path.append(d)\n", True),
            ("import sys\n(sys.path).insert(0, d)\n", True),
            ("import sys\nsys.path.__setitem__(slice(0, 0), [d])\n", True),
            ("import sys\nsys.meta_path.insert(0, f)\n", True),
            ("import sys\nsys.path_hooks.append(f)\n", True),
            ("import os, sys as s\ns.path.insert(0, d)\n", True),
            ("if True: import sys as s\ns.path.append(d)\n", True),
            ("from sys import argv, path\n", True),
            ("from sys import path as p\n", True),
            ("import site\nsite.addsitedir(d)\n", True),
            ('x = "sys.path.insert(0, d)"\n', False),
            ("# sys.path.insert(0, d)\n", False),
            ("import sys\nprint(sys.path, sys.path[0], sys.path.index(d))\n", False),
            ("from sys import argv\npath = 1\n", False),
        ] + [
            (f"import sys\nsys.path.{method}(d)\n", True)
            for method in ("insert", "append", "extend", "remove", "pop", "clear", "reverse", "sort")
        ]
        for source, want in detector:
            if mutates_sys_path(source) != want:
                errors.append(f"self-test: sys.path detector on {source!r}: expected {want}")
        (tools / "sibling.py").write_text("import sys\nsys.path.insert(0, '.')\n", encoding="utf-8")
        if not any("tools/sibling.py: changes sys.path" in f for f in scan()):
            errors.append("self-test: a sibling module that changes sys.path gave no finding")
        (tools / "sibling.py").write_bytes(b"x = '\xff'\n")
        if not any("tools/sibling.py: cannot be read" in f for f in scan()):
            errors.append("self-test: an unreadable module under tools gave no finding")
        (tools / "sibling.py").unlink()

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
        if not any("planted" in f for f in scan(probe=("tools/shadow.py",))):
            errors.append("self-test: the scan did not report the planted-module probe")
    return errors


def main() -> int:
    errors = self_test()
    if errors:
        for error in errors:
            print(error)
        print(f"FAIL: {len(errors)} self-test failure(s)")
        return 1
    findings, count = scan_tree(REPO, LAUNCH_FLOOR, PROBE_SCRIPTS, ALLOWED_LINES)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s), {count} accepted launches")
        return 1
    print(f"OK: {count} Python launches under .github, every one isolated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
