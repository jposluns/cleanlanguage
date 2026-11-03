#!/usr/bin/env python3
"""Check that every Python launch in the workflows has the one isolated form.

Row 95 asks that every gate or tool launch in the workflows runs `python3 -I`,
pinned by a test. This scan pins it with one literal rule and refuses every
other form by design. In the run text it reads, a line passes only when each
python word and .py name written on it is part of the one form, or the line
is a listed comment or echo that cannot run a command. For those lines the
rule errs only by refusing an honest form. A launch can still pass when the
scan does not see it: outside the run text, or written so that python or a
.py name appears only after bash or GitHub expands it. Residuals, below,
names each such case.

A Python-launched gate that finds a planted file on its module path can import
that file in place of a standard-library module and turn the gate into a green
run that checked nothing. `python3 -I` keeps the script folder off the module
path and ignores the user site directory and every PYTHON* variable.

The rule:

1. Scope. The scan reads .github/workflows/*.yml. Any other .yml or .yaml
   file anywhere under .github, in any letter case, such as an action.yml or
   a .YML workflow, is a finding, as is a symbolic link under .github, a
   folder that cannot be listed, a file that cannot be read as UTF-8 or
   parsed with PyYAML's safe loader, a repeated mapping key, and U+0085,
   U+2028 or U+2029 (which YAML 1.1 and 1.2 read differently). Each workflow
   must have a jobs mapping; a job that is not a mapping, a steps value that
   is not a list and a step that is not a mapping are findings.
2. Shell and environment. Every step `shell`, and every `defaults.run.shell`
   at workflow and job level, must be exactly `bash`, and every step with
   run text must have one of them, so no step runs under a runner's default
   shell. An `env` key BASH_ENV, ENV or PATH at workflow, job or step level
   is a finding, and so is a run line that names BASH_ENV or GITHUB_PATH or
   assigns ENV or PATH, since each can redirect `python3` to another program.
   A listed line does not excuse these findings, nor those of rule 4.
3. Launch. In each step's `run` text, with every backslash-newline removed and
   nothing else dropped, every exact `python3 -I tools/<name>.py`, with single
   spaces, `<name>` holding no `/`, and no character of a path directly
   before `python3` or after `.py`, is a launch. With the launches removed, a
   line that still holds the word python in any case, or a `.py` or `.pyz`
   name, is a finding, unless that exact line, stripped of surrounding
   spaces, is listed for its file in ALLOWED_LINES. A listed line that no
   longer exists is a finding, so the list stays exact. A listed line must
   be a comment that holds no quote, backtick, backslash or `$(`, or a single
   `echo` of one double-quoted message (optionally after a case label such
   as `1)`, and optionally followed by `>&2` and `; exit N ;;`) whose message
   holds none of `; & | < >`, a backtick, `$(`, a quote or a backslash; any
   other listed line is a finding. So a listed line cannot run a command,
   even when a quote opened on the line above puts its text outside quotes:
   with no command separator, its words stay arguments, and an unquoted
   parenthesis makes bash stop with a syntax error.
4. A word that holds python or a `.py` name only once its quotes and
   backslashes are removed is a finding.
5. Every launched script must exist, and the launches on lines that are not
   shell comments must number at least LAUNCH_FLOOR.
6. Tempfile.py, msvcrt.py, nt.py and _winapi.py are planted beside a copy of
   each script in PROBE_SCRIPTS, the copy runs under `-I`, and the scan fails
   if a planted module ran.

Refused by design, although some of them would run isolated: `python3.12 -I`,
`/usr/bin/python3 -I`, `python3 -I -B`, `python3 -I -W error`, the
`python3 -P -E -s` equivalent, a quoted script path, two spaces before `-I`, a
launch whose words are split across continued lines, `(python3)` and other
case arms naming python, a message or comment that names python, and
`shell: sh` or `bash -e {0}`. Write a launch as `python3 -I tools/<name>.py`.

Out of this scan's scope: a check that the tools do not change sys.path, the
pinning of `uses`, and local or composite actions, which are refused here
rather than read.

Residuals, named here because the scan reads text the pull request controls:

- a variable holding the interpreter or the script, such as `$PY tools/x`,
  and a shell function or alias named python3, or a PATH change made in a
  way the rule above does not name, that redirects the literal `python3`;
- the shell scripts the workflows run, such as tools/release-dry-run.sh and
  tools/check-portable-text-sync.sh, which launch python3 without -I in
  places and are carried as a separate backlog row;
- other launchers, such as `uv run`, pytest, pipx or an extensionless script;
- text built at run time, such as `eval`, a file written and then run, or a
  pipe into a shell;
- obfuscation that spells python or a `.py` name only once bash or GitHub
  expands it, such as an ANSI-C string, a glob, brace or parameter expansion,
  or a `${{ }}` expression;
- remote actions and reusable workflows, which are outside this repository;
- a correct launch in a context that never runs, such as an echo message or a
  here-document body, which still counts toward the floor.

The scan is a check of the pull request's own checkout: the author of a change
can also edit this scan, and only review catches that.

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

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent

# The number of launches under .github/workflows when this check landed.
LAUNCH_FLOOR = 51

# Lines that name Python or a tool without launching it, by file, exactly as
# they stand once stripped of surrounding spaces.
ALLOWED_LINES: dict[str, tuple[str, ...]] = {
    ".github/workflows/release-skill.yml": (
        "# extractor, tools/skill-version.py, reads and validates it for every",
        "# site, so the workflow, the dry run, and the Python gates agree byte",
        "# stripped). skill-version.py reads the whole file, so there is no",
        "# blob is piped straight in: skill-version.py reads all of stdin, so git",
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
        'publication day, and tools/check-release-checksum-live.py reports the same disagreement until then." >&2',
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
LAUNCH = re.compile(r"(?<![\w./\\-])python3 -I (tools/[\w.-]+\.py)(?![\w./\\-])")
PYTHON = re.compile(r"python", re.IGNORECASE)
PY_NAME = re.compile(r"\.pyz?(?![\w])")
SHIM = re.compile(r"\bBASH_ENV\b|\bGITHUB_PATH\b|(?<![\w$])(?:ENV|PATH)\+?=")
SHIM_ENV_KEYS = ("BASH_ENV", "ENV", "PATH")
ALLOWED_COMMENT = re.compile(r"#[^\"'`\\]*")
ALLOWED_ECHO = re.compile(
    r'(?:[\w*|]+\) )?echo "([^"]*)"(?: >&2)?(?:; exit \d+ ;;)?'
)
UNSAFE_MESSAGE = re.compile(r"[;&|<>`\"'\\]|\$\(")


def allowed_shape_problem(line: str) -> str | None:
    """Return why a line may not be listed, or None when its shape is safe."""
    if ALLOWED_COMMENT.fullmatch(line) and "$(" not in line:
        return None
    echo = ALLOWED_ECHO.fullmatch(line)
    if echo and not UNSAFE_MESSAGE.search(echo.group(1)):
        return None
    return "is neither a plain comment nor one echo of a message with no shell control character"


def check_run(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, bool]]]:
    """Return (refused lines, launches as (script, counted)).

    Each refused line is (reason, line, listable); a line that is not listable
    is a finding even when ALLOWED_LINES holds it.
    """
    refused: list[tuple[str, str, bool]] = []
    launches: list[tuple[str, bool]] = []
    for line in text.replace("\\\n", "").split("\n"):
        comment = line.lstrip(" \t").startswith("#")
        launches += [(m.group(1), not comment) for m in LAUNCH.finditer(line)]
        rest = LAUNCH.sub(" ", line)
        if SHIM.search(line):
            refused.append(("BASH_ENV, GITHUB_PATH, or an ENV or PATH assignment, which can redirect python3", line.strip(), False))
        if PYTHON.search(rest) or PY_NAME.search(rest):
            refused.append(("python or a .py name other than python3 -I tools/<name>.py", line.strip(), True))
        for word in line.split():
            plain = re.sub(r"[\"'\\]", "", word)
            if (PYTHON.search(plain) and not PYTHON.search(word)) or (PY_NAME.search(plain) and not PY_NAME.search(word)):
                refused.append(("a quote or backslash inside python or a .py name", line.strip(), False))
    return refused, launches


class UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses a mapping with a repeated key."""


def _construct_mapping(loader, node, deep=False):
    keys = []
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        keys.append(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def list_workflows(root: Path) -> tuple[list[Path], list[str]]:
    """Return the .github/workflows/*.yml files, and findings for anything else in scope."""
    base = root / ".github"
    workflows = base / "workflows"
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
        for name in sorted(names):
            path = Path(folder) / name
            lower = name.lower()
            if path.parent == workflows and name.endswith(".yml"):
                files.append(path)
            elif lower.endswith((".yml", ".yaml")):
                errors.append(f"{path.relative_to(root)}: outside this scan's scope (.github/workflows/*.yml only)")
    return files, errors


def collect(doc, found: list) -> tuple[list, list]:
    """Return the (where, run) and (where, shell) values of one workflow."""
    runs: list = []
    shells: list = []
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        found.append("jobs: a workflow with no jobs mapping")
        return runs, shells

    def defaults(node, where):
        if isinstance(node.get("defaults"), dict) and isinstance(node["defaults"].get("run"), dict):
            if "shell" in node["defaults"]["run"]:
                shells.append((f"{where}.defaults.run", node["defaults"]["run"]["shell"]))

    def env_keys(node, where):
        env = node.get("env")
        if isinstance(env, dict):
            for key in env:
                if key in SHIM_ENV_KEYS:
                    found.append(f"{where}.env: {key} can redirect python3 to another program")

    defaults(doc, "workflow")
    env_keys(doc, "workflow")
    workflow_shell = bool(shells)
    for job_id, job in jobs.items():
        where = f"jobs.{job_id}"
        if not isinstance(job, dict):
            found.append(f"{where}: not a mapping")
            continue
        before = len(shells)
        defaults(job, where)
        env_keys(job, where)
        job_shell = workflow_shell or len(shells) > before
        steps = job.get("steps")
        if steps is None:
            continue
        if not isinstance(steps, list):
            found.append(f"{where}.steps: not a list")
            continue
        for n, step in enumerate(steps):
            label = f"{where}.steps[{n}]"
            if not isinstance(step, dict):
                found.append(f"{label}: not a mapping")
                continue
            env_keys(step, label)
            if "run" in step:
                runs.append((label, step["run"]))
                if "shell" not in step and not job_shell:
                    found.append(f"{label}: run text with no explicit shell: bash at step, job or workflow level")
            if "shell" in step:
                shells.append((label, step["shell"]))
    return runs, shells


def scan_tree(root: Path, floor: int, probe_scripts, allowed: dict) -> tuple[list[str], int]:
    """Scan root/.github; return (findings, number of counted launches)."""
    files, findings = list_workflows(root)
    if not files:
        findings.append(f"no workflow found in {root / '.github' / 'workflows'}")
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
        runs, shells = collect(doc, found)
        for where, value in shells:
            if value != "bash":
                found.append(f"{where}.shell: {value!r} is not exactly bash")
        for where, value in runs:
            if isinstance(value, (bool, int, float)):
                value = str(value)
            if not isinstance(value, str):
                found.append(f"{where}.run: not text")
                continue
            refused, launches = check_run(value)
            for reason, line, listable in refused:
                if listable and line in allowed.get(rel, ()):
                    seen_allowed.add((rel, line))
                else:
                    found.append(f"{where}.run: {reason}: {line[:100]}")
            for script, count in launches:
                if not (root / script).is_file():
                    found.append(f"{where}.run: launched script {script} does not exist")
                counted += 1 if count else 0
        findings += [f"{rel}: {reason}" for reason in found]

    for rel, lines in allowed.items():
        for line in lines:
            problem = allowed_shape_problem(line)
            if problem:
                findings.append(f"{rel}: the allowed line {problem}: {line[:100]}")
            if (rel, line) not in seen_allowed:
                findings.append(f"{rel}: the allowed line is no longer present: {line[:100]}")

    if counted < floor:
        findings.append(f"only {counted} launches found, below the floor of {floor}")

    for script in probe_scripts:
        failure = planted_module_runs(root, script)
        if failure:
            findings.append(failure)
    return findings, counted


def planted_module_runs(root: Path, script: str) -> str | None:
    """Run a copy of `script` under -I beside planted modules; describe a failure."""
    with tempfile.TemporaryDirectory() as tmp:
        tools = Path(tmp) / "tools"
        tools.mkdir()
        for source in (root / "tools").glob("*.py"):
            shutil.copy2(source, tools / source.name)
        for name in PLANTED_MODULES:
            (tools / f"{name}.py").write_text(
                f"import os\nos.write(1, b'{PLANT_MARKER} {name}\\n')\nos._exit(97)\n", encoding="utf-8"
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

X = "tools/x.py"

# Run text that must be refused (True) or must pass (False).
RUN_CASES = [
    # Round 4 misses
    ("tools/sub/x.py", True),
    ("python3 -I tools/sub/x.py", True),
    (f"python3 -I {X}c", True),
    (f"python3 -E {X}", True),
    (f"ipython3 -I {X}", True),
    (f"x.python3 -I {X}", True),
    (f"my-python3 -I {X}", True),
    (f"a\\python3 -I {X}", True),
    (f"python3 -I {X}.bak", True),
    (f"python3 -I {X}/y", True),
    (f"python3 -I {X}\\y", True),
    (f"python3 -I {X}-old", True),
    ("./tools/app.pyz", True),
    ("echo app.pyz", True),
    ('export PATH="$PWD/.github/bin:$PATH"', True),
    (f'PATH="$PWD/bin:$PATH" python3 -I {X}', True),
    ('echo "$PWD/bin" >> "$GITHUB_PATH"', True),
    ('echo "BASH_ENV=f" >> "$GITHUB_ENV"', True),
    ("ENV=f bash -c true", True),
    ('echo "$PATH"', False),
    ('echo "A=b" >> "$GITHUB_ENV"', False),
    ("scripts/x.py", True),
    ("python3 -I scripts/x.py", True),
    ("cat f|python3|tee o", True),
    ("python3.12-dbg -c 'x'", True),
    (f"python3.12-dbg {X}", True),
    # Formerly accepted forms that are not the one form
    (f"/usr/bin/python3 -I {X}", True),
    (f"python3.12 -I {X}", True),
    (f"python3 -I -B {X}", True),
    (f"python3 -I -W error {X}", True),
    (f"python3 -P -E -s {X}", True),
    (f'python3 -I "{X}"', True),
    (f"python3  -I {X}", True),
    (f"python3 -I \\\n  {X}", True),
    (f"${{pythonLocation}}/bin/python3 -I {X}", True),
    ('case "$x" in\n  (python3) echo yes ;;\nesac', True),
    ('case "$x" in python3) echo yes ;; esac', True),
    ('case "$f" in *.py) echo yes ;; esac', True),
    ("python3 -I -c 'x'", True),
    ("python3 --version", True),
    # Unisolated forms
    (f"python3 {X}", True),
    (f"python {X}", True),
    (f"nice -n 10 python3 {X}", True),
    (f"cat <<EOF\nLinks: $(python3 {X})\nEOF", True),
    (X, True),
    (f'"{X}"', True),
    ("./x.py", True),
    ("py\\\nthon3 -c 'x'", True),
    ("tools/x.\\\npy", True),
    # Each rule's own case
    ("echo the Python gates", True),
    ("echo check.py", True),
    ("p''ython3 -c 'x'", True),
    ("pyth\\on3 -c 'x'", True),
    ("cp a.p''y b", True),
    # The one form, in its usual contexts
    (f"python3 -I {X}", False),
    (f"python3 -I {X} --flag \"$(date -u +%Y)\" >/dev/null || rc=$?", False),
    (f'v="$(python3 -I {X})"', False),
    (f"(python3 -I {X})", False),
    (f"git show HEAD:f | python3 -I {X}", False),
    (f"true && python3 -I {X}", False),
    (f"false || python3 -I {X}", False),
    (f"if ! python3 -I {X}; then exit 1; fi", False),
    (f"LC_ALL=C python3 -I {X}", False),
    (f"timeout 300 python3 -I {X}", False),
    (f"python3 -I {X};", False),
    (f"python3 -I {X} \\\n  --flag", False),
    (f'cat <<EOF >> "$GITHUB_STEP_SUMMARY"\nLinks: $(python3 -I {X})\nEOF', False),
    ("echo ok", False),
]

STEP_CASES = [
    ("name: Check the Python gates\n        run: echo ok", False),
    ("shell: bash\n        run: echo ok", False),
    ("run: 12", False),
    ("shell: sh\n        run: echo ok", True),
    ("shell: bash -e {0}\n        run: echo ok", True),
    ("shell: bash # strict\n        run: echo ok", False),
    ('shell: bash -c "python3 {0}"\n        run: print(1)', True),
    ("shell: pwsh\n        run: echo ok", True),
    ("run: [a, b]", True),
    ("env:\n          BASH_ENV: .github/shell-init\n        run: echo ok", True),
    ("env:\n          ENV: .github/shell-init\n        run: echo ok", True),
    ("env:\n          PATH: /x\n        run: echo ok", True),
    ("env:\n          FOO: bar\n        run: echo ok", False),
    ("run: echo ok\n        run: python3 tools/x.py", True),
]


def self_test() -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = root / "tools"
        tools.mkdir()
        for name in ("a", "x", "sub/x"):
            (tools / name).parent.mkdir(parents=True, exist_ok=True)
            (tools / f"{name}.py").write_text("import tempfile\n", encoding="utf-8")
        (tools / "x.pyc").write_bytes(b"")
        missing, _ = scan_tree(root, 1, (), {})
        if not any("cannot list" in f for f in missing):
            errors.append("self-test: a missing .github folder gave no finding")
        github = root / ".github"
        workflows = github / "workflows"
        workflows.mkdir(parents=True)
        empty, _ = scan_tree(root, 1, (), {})
        if not any("no workflow" in f for f in empty) or not any("below the floor" in f for f in empty):
            errors.append("self-test: an empty .github did not report both no workflow and the floor")
        case = workflows / "case.yml"
        rel = ".github/workflows/case.yml"
        head = ("on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    defaults:\n      run:\n        shell: bash\n"
                "    steps:\n      - run: python3 -I tools/a.py\n")

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
        if run_case(f': "\n{message}\n"', allowed={rel: (message,)}):
            errors.append("self-test: a listed echo between quote lines gave a finding")
        for bad in ('echo "a, then; tools/x.py runs." >&2', 'echo "a | tools/x.py" >&2',
                    'echo "a & tools/x.py" >&2', 'echo "a `tools/x.py`" >&2', 'echo "a $(tools/x.py)" >&2',
                    'echo "a > tools/x.py" >&2', 'echo "a \\" tools/x.py" >&2', 'echo "a \' tools/x.py" >&2',
                    'echo "a \\ tools/x.py" >&2', "# a $(tools/x.py)", "# it's tools/x.py", '# a "tools/x.py"', "# a \\ tools/x.py",
                    'echo "tools/x.py" && echo "tools/x.py"', 'printf "tools/x.py"'):
            if not any("is neither a plain comment" in f for f in run_case(bad, allowed={rel: (bad,)})):
                errors.append(f"self-test: the listed line {bad!r} was not refused by its shape")
        shim = 'echo "$PWD/bin" >> "$GITHUB_PATH"'
        if not run_case(shim, allowed={rel: (shim,)}):
            errors.append("self-test: a listed line that writes GITHUB_PATH gave no finding")
        named = "# this step sets BASH_ENV for tools/x.py"
        if not any("redirect python3" in f for f in run_case(named, allowed={rel: (named,)})):
            errors.append("self-test: a listed comment that names BASH_ENV was excused")

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
            ("workflow defaults shell sh", "on: push\ndefaults:\n  run:\n    shell: sh\n" + head[9:], "not exactly bash"),
            ("job defaults shell sh", head.replace("shell: bash", "shell: sh"), "not exactly bash"),
            ("job env BASH_ENV", head.replace("    runs-on", "    env:\n      BASH_ENV: x\n    runs-on"), "can redirect"),
            ("workflow env PATH", "on: push\nenv:\n  PATH: /x\n" + head[9:], "can redirect"),
            ("no shell anywhere", "on: push\njobs:\n  j:\n    runs-on: windows-latest\n    steps:\n      - run: echo ok\n",
             "no explicit shell"),
        ]
        for name, text, needle in whole:
            case.write_text(text, encoding="utf-8")
            if not any(needle in f for f in scan()):
                errors.append(f"self-test: whole file {name} gave no finding naming {needle!r}")
        case.write_text(
            "x: &c\n  runs-on: ubuntu-latest\n  defaults:\n    run:\n      shell: bash\non: push\njobs:\n"
            "  j:\n    <<: *c\n    steps:\n      - run: python3 -I tools/a.py\n", encoding="utf-8")
        if scan():
            errors.append(f"self-test: a YAML merge key gave {scan()!r}")
        case.write_text("on: push\ndefaults:\n  run:\n    shell: bash\njobs:\n  j:\n    steps:\n"
                        "      - run: python3 -I tools/a.py\n", encoding="utf-8")
        if scan():
            errors.append(f"self-test: a workflow-level shell: bash gave {scan()!r}")
        case.write_text(head, encoding="utf-8")
        (workflows / "bad.yml").write_bytes(b"on: \xff\n")
        if not any("cannot be read" in f for f in scan()):
            errors.append("self-test: an unreadable workflow file gave no finding")
        (workflows / "bad.yml").unlink()

        for rel_path in ("workflows/x.yaml", "workflows/evil.YML", "workflows/x.Yaml",
                         "actions/m/action.yml", "actions/m/action.yaml",
                         "ISSUE_TEMPLATE/bug.yml", "workflows/sub/w.yml", "dependabot.yml"):
            target = github / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(head, encoding="utf-8")
            if not any(f".github/{rel_path}: outside" in f for f in scan()):
                errors.append(f"self-test: .github/{rel_path} was not refused as out of scope")
            target.unlink()
        for folder in ("actions/m", "actions", "ISSUE_TEMPLATE", "workflows/sub"):
            (github / folder).rmdir()
        (github / "CODEOWNERS").write_text("* @owner\n", encoding="utf-8")
        if scan():
            errors.append("self-test: a file under .github that is not YAML gave a finding")
        (github / "CODEOWNERS").unlink()

        sub = workflows / "sub"
        sub.mkdir()
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
        sub.rmdir()

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
                if not any(f"{name}: a symbolic link" in f for f in findings):
                    errors.append(f"self-test: the symbolic link {name} gave no finding")
            (github / "linked").unlink()
            (workflows / "link.yml").unlink()

        (tools / "shadow.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "setattr(sys, 'path', [str(Path(__file__).resolve().parent)] + sys.path)\n"
            "import tempfile\n", encoding="utf-8")
        (tools / "absent.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "setattr(sys, 'path', sys.path + [str(Path(__file__).resolve().parent)])\n"
            "try:\n    import msvcrt\nexcept ImportError:\n    pass\n", encoding="utf-8")
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
        print(f"FAIL: {len(findings)} finding(s), {count} launches")
        return 1
    print(f"OK: {count} Python launches in the workflows, every one python3 -I tools/<name>.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
