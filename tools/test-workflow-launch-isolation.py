#!/usr/bin/env python3
"""Check that every Python launch in the workflows has the one isolated form.

Row 95 asks that every gate or tool launch in the workflows runs `python3 -I`,
pinned by a test.

Threat model: honest drift. The scan guards against an honest author who
writes a workflow launch without -I, or in some other form, by mistake. An
author who sets out to run python without -I is outside its model: such an
author can also edit this scan, and deliberate evasion is a named residual.

This scan pins the launch form with one literal rule and refuses every
other form by design. In the run text it reads, a line passes only when each
python word and .py name written on it is part of the one form. No line is
exempt: a comment or a message that names python or a .py file is a finding
like any other, so the workflows name a tool in words (for example "the
release-date extractor") wherever they mention it outside a launch. The rule
can err by refusing an honest form. The scan reads text: it does not know
command position or what bash will run. So a launch without -I can pass when
the scan does not see it (outside the run text, or written so that python or
a .py name appears only after bash or GitHub expands it), and also when the
scan sees its text but a deliberate author has written it so that the text
rules misread it. Residuals, below, names each such case.

A Python-launched gate that finds a planted file on its module path can import
that file in place of a standard-library module and turn the gate into a green
run that checked nothing. `python3 -I` keeps the script folder off the module
path and ignores the user site directory and every PYTHON* variable.

The rule:

1. Scope. The scan reads .github/workflows/*.yml. Any other .yml or .yaml file
   anywhere under .github, in any letter case, such as an action.yml or a .YML
   workflow, is a finding, as is a symbolic link under .github, a folder that
   cannot be listed, a file that cannot be read as UTF-8 or parsed with
   PyYAML's safe loader, and U+0085, U+2028 or U+2029 (which YAML 1.1 and 1.2
   read differently). The scan loads each workflow with UniqueKeyLoader, and a
   file whose loading raises any exception is a finding:
   `cannot be parsed as YAML`, then in parentheses the exception's type, a
   colon, a space and the first line of its message, such as
   `(OverflowError: int too large to convert to float)`. UniqueKeyLoader's
   mapping constructor skips each merge key (`<<`), builds each other key with
   `loader.construct_object(key_node, deep=deep)`, raises a ConstructorError
   when a built key is `in` the list of the keys built before it, and returns
   `yaml.SafeLoader.construct_mapping(loader, node, deep=deep)`. Loading with
   UniqueKeyLoader refuses some documents and loads others; UniqueKeyLoader's
   docstring gives examples of each that the self-tests record. Each workflow
   must have a jobs mapping; a job that is not a mapping, a steps value that
   is not a list and a step that is not a mapping are findings. A job or step
   `uses:` value that starts with ./ or ../, a local action or a local
   reusable workflow, is a finding, since the scan does not read it.
2. Shell and environment. Every step `shell`, and every `defaults.run.shell`
   at workflow and job level, must be exactly `bash`, and every step with
   run text must have one of them (its own, its job's, or the workflow's), so
   no step runs under a runner's default shell. A job's default counts only
   for that job's steps. An `env` key BASH_ENV, ENV or PATH at workflow, job
   or step level is a finding, and so is a run line that holds BASH_ENV or
   GITHUB_PATH as a whole word, or holds ENV or PATH directly followed by
   `=` or `+=` and not directly preceded by a letter, digit, underscore or
   `$` (so MYPATH=x and `$PATH=` pass, and a quoted name such as
   `export 'PATH'=x` is not matched). A run line that holds both a shell
   word and a -c cluster is a finding, whether or not it names python,
   since a shell run with -c takes its command text as a string the scan
   cannot read as commands. A shell word is bash, sh, dash, zsh or ksh,
   alone or as the last part of a path such as /bin/bash, with no letter,
   digit, underscore, dot or hyphen directly before the word, and no letter,
   digit, underscore, dot, slash or hyphen directly after it (so sha256sum,
   ssh, fish and a.sh are not shell words, and a quoted `"bash"` is one). A -c
   cluster is a hyphen and letters that include a lower-case c
   (`-[A-Za-z]*c[A-Za-z]*`, such as `-c`, `-ec` or `-ce`), with no letter,
   digit, underscore or hyphen directly before or after it (so `--norc` and
   `-cache-dir` are not one). Both may stand anywhere on the line, in either
   order: the rule does not read command position, so it refuses some honest
   lines, such as `shfmt -ln bash -ci`, `bash tools/a.sh -c config`,
   `grep bash -c file` or a message that mentions `bash -c`, and an author
   rephrases such a line. These are cheap checks of the common ways to
   redirect `python3` or hide a launch; they are not complete, and Residuals
   names what they miss.
3. Launch. In each step's `run` text, with every backslash-newline removed and
   nothing else dropped, every exact `python3 -I tools/<name>.py`, with single
   spaces, `<name>` holding no `/`, no character of a path and no `$` directly
   before `python3`, and `.py` directly followed by the end of the line, a
   space, a tab, `|`, `&`, `;`, `(`, `)`, or a `<` or `>` not directly
   followed by `(`, is a launch (so `$python3 -I tools/x.py` is not one, and
   nor are `python3 -I tools/x.py"w"`, which bash runs as `tools/x.pyw`, and
   `python3 -I tools/x.py<(echo w)`, whose script word bash ends with the path
   of a process substitution). The rule reads the form before each character
   of that list as a launch, and refuses the line at a `<(` or `>(` and at
   every other character directly after `.py`, among them a character that
   closes a construct holding the launch: for example a closing backquote,
   which ends a command substitution written with backquotes, a `}` that ends
   a parameter expansion, or a `"` or `'` that ends a quoted string. For
   `${v:+python3 -I tools/x.py} --flag`, with `v=1`, and for
   `eval "python3 -I tools/x.py"`, bash passes tools/x.py as the script, and
   for `${v:+python3 -I tools/x.py}w`, with `v=1`, and for
   `eval "python3 -I tools/x.py"w`, it passes tools/x.pyw. With the launches
   removed, a line that still holds the word python, or a `.py`, `.pyz` or
   `.pyw` name with no letter, digit or underscore directly after it (so
   `x.pyc` is not one), in any letter case, is a finding, whether it is a
   command, a comment or a message.
4. A word that holds python or a `.py`, `.pyz` or `.pyw` name only once its
   quotes, its backslashes and each `$` directly before a quote are removed is
   a finding (so `p$"y"thon3` is one).
5. Every launched script must exist, and the launches on lines that are not
   shell comments must number at least LAUNCH_FLOOR.
6. Tempfile.py, msvcrt.py, nt.py and _winapi.py are planted beside a copy of
   each script in PROBE_SCRIPTS, the copy runs under `-I`, and the scan fails
   if a planted module ran.

Refused by design, although some of them would run isolated: `python3.12 -I`,
`/usr/bin/python3 -I`, `python3 -I -B`, `python3 -I -W error`, the
`python3 -P -E -s` equivalent, a quoted script path, a character directly
after `.py` that is not in rule 3's list, as in `tools/x.py''` or
`tools/x.py$EMPTY`, among them a character that closes a construct holding the
launch (such as a closing backquote, which ends a command substitution written
with backquotes, a `}` that ends a parameter expansion, as in
`${v:+python3 -I tools/x.py} --flag`, or a `"` or `'` that ends a quoted
string, as in `eval "python3 -I tools/x.py"`; a `)` that closes `$(...)` or a
subshell is in that list, and the form before it reads as a launch), 2 spaces
before `-I`, a launch whose words are split across continued lines,
`(python3)` and other case arms naming python, a message or comment that names
python or a .py file, an expression such as `${{ env.PY }}`,
`${{ matrix.Py }}`, `${{ env.PYZ }}` or `${{ vars.PYW }}`, which rule 3 reads
as a `.py`, `.pyz` or `.pyw` name, and `shell: sh` or `bash -e {0}`. Write a
launch as `python3 -I tools/<name>.py`, and a command substitution that holds
one as `$(...)`.

Out of this scan's scope: a check that the tools do not change sys.path, the
pinning of `uses`, and local actions and local reusable workflows, which
rule 1 refuses rather than reads.

Residuals, named here because the scan reads text the pull request controls:

- deliberate evasion of any kind: the scan reads text, not commands, so an
  author who means to run python without -I can write a line whose text the
  scan sees but misreads, and can also edit this scan, which only review
  catches;
- a repeated mapping key that loading with UniqueKeyLoader does not refuse,
  such as `x: {<<: {p: 1, p: 2}}`, which the self-tests record as loading;
- a PATH or ENV assignment whose name is quoted or escaped, such as
  `export 'PATH'=x`;
- a shell run with -c whose shell is not a shell word on the line: a shell
  held in a variable, such as `"$SHELL" -c` or `$BASH -c`; a shell name
  broken by quotes or escapes so that no shell word is left, such as
  `b''ash -c` (a break that leaves a shell word, as the `sh` of
  `ba''sh -c`, is still refused); a shell other than the five, such as
  fish, rbash or `busybox ash`; and a command that runs its argument
  through a shell it does not name, such as `su -c`, `flock -c` or
  `script -c`;
- a shell run with -c whose -c is not a -c cluster on the same line as
  the shell word, such as one held in a variable (`bash $OPTS`) or one on
  a line of its own that no backslash-newline joins to the shell's line;
- a variable holding the interpreter or the script, such as `$PY tools/x`,
  and a shell function or alias named python3, that redirects the literal
  `python3`;
- what rule 2 does not catch: any other environment variable (for example
  LD_PRELOAD or LD_LIBRARY_PATH), an exported function (BASH_FUNC_*), a
  multi-line GITHUB_ENV write, or a PATH change made by other means (for
  example `read`) can change what `python3` runs, and the scan does not
  catch it;
- the shell scripts the workflows run, such as tools/release-dry-run.sh;
  tools/test-shell-launch-isolation.py reads the tools/*.sh scripts among
  them that it finds by name, and names in its residuals those it does not
  read;
- other launchers, such as `uv run`, pytest or pipx;
- a script run by its shebang whose name ends in none of `.py`, `.pyz` and
  `.pyw`, such as an extensionless script;
- a compiled file run directly, such as a `.pyc` file, which the scan does not
  read;
- a workflow whose job id or `shell` value, or whose step `run` value given as
  a number, cannot be turned into text, such as an integer written in hex
  whose value has more than 4300 decimal digits, which stops the scan with a
  traceback rather than a finding;
- text built at run time, such as `eval`, a file written and then run, or a
  pipe into a shell;
- a launch written inside a parameter expansion, such as
  `${v:+python3 -I tools/x.py|w}`, which the scan counts as a launch of
  tools/x.py, while with `v=1` bash passes `tools/x.py|w` as the script; with
  `;`, `&`, `<`, `>`, `(` or `)` in place of `|`, the scan also counts
  tools/x.py, and bash passes tools/x.py followed by that character and `w`;
- an edit to rule 3's right edge that the self-tests do not reach. The
  character and pair self-tests put after `.py` each character of a sample
  (each ASCII character, each code point that `str.isspace()` accepts or whose
  Unicode category is Cf, and 6 non-ASCII letters of 6 scripts, whose UTF-8
  lengths span 2 to 4 bytes), and each character of the edge followed by each
  character of the sample, each time followed by `w`. An edit whose verdict
  differs from the edge's only on text after `.py` that no self-test scans
  passes every self-test. Such an edit can, for example, change the verdict
  only for a code point outside the sample, only where the text beyond the
  second character after `.py` differs, or only where a character outside the
  edge is followed by anything but `w`, if no case holds that text, and the
  scan can then count a launch while bash passes another script word, or
  refuse an honest one;
- obfuscation that spells python or a `.py` name only once bash or GitHub
  expands it, such as an escape in an ANSI-C string, a glob, brace or
  parameter expansion, or a `${{ }}` expression;
- remote actions and remote reusable workflows, including composite ones,
  which are outside this repository;
- a correct launch in a context that never runs, such as an echo message or a
  here-document body, which still counts toward the floor.

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
import unicodedata
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent

# The number of launches under .github/workflows after row 95 was rebased
# onto row 89 (fix round 8).
LAUNCH_FLOOR = 53

# Launched scripts that load sibling modules, checked with planted modules.
PROBE_SCRIPTS = (
    "tools/check-page-metadata.py",
    "tools/generate-sitemap.py",
    "tools/test-sitemap.py",
)
PLANTED_MODULES = ("tempfile", "msvcrt", "nt", "_winapi")
PLANT_MARKER = "PLANTED-MODULE-RAN"

YAML_DISAGREEMENT = {"\x85": "U+0085", "\u2028": "U+2028", "\u2029": "U+2029"}
LAUNCH = re.compile(r"(?<![\w./\\$-])python3 -I (tools/[\w.-]+\.py)(?=[ \t|&;()]|[<>](?!\()|\Z)")
PYTHON = re.compile(r"python", re.IGNORECASE)
PY_NAME = re.compile(r"\.py[zw]?(?![\w])", re.IGNORECASE)
SHIM = re.compile(r"\bBASH_ENV\b|\bGITHUB_PATH\b|(?<![\w$])(?:ENV|PATH)\+?=")
SHIM_ENV_KEYS = ("BASH_ENV", "ENV", "PATH")
SHELL_WORD = re.compile(r"(?<![\w.-])(?:bash|sh|dash|zsh|ksh)(?![\w./-])")
C_CLUSTER = re.compile(r"(?<![\w-])-[A-Za-z]*c[A-Za-z]*(?![\w-])")
LOCAL_USES = ("./", "../")


def runs_shell_c(line: str) -> bool:
    """True when the line names a shell word and carries a -c cluster, anywhere."""
    return bool(SHELL_WORD.search(line)) and bool(C_CLUSTER.search(line))


def check_run(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, bool]]]:
    """Return (refused lines as (reason, line), launches as (script, counted))."""
    refused: list[tuple[str, str]] = []
    launches: list[tuple[str, bool]] = []
    for line in text.replace("\\\n", "").split("\n"):
        comment = line.lstrip(" \t").startswith("#")
        launches += [(m.group(1), not comment) for m in LAUNCH.finditer(line)]
        rest = LAUNCH.sub(" ", line)
        if SHIM.search(line):
            refused.append(("BASH_ENV, GITHUB_PATH, or an ENV or PATH assignment, which can redirect python3", line.strip()))
        if runs_shell_c(line):
            refused.append(("a line that names a shell and carries a -c option cluster", line.strip()))
        if PYTHON.search(rest) or PY_NAME.search(rest):
            refused.append(("python or a .py name other than python3 -I tools/<name>.py", line.strip()))
        for word in line.split():
            plain = re.sub(r"\$(?=[\"'])|[\"'\\]", "", word)
            if (PYTHON.search(plain) and not PYTHON.search(word)) or (PY_NAME.search(plain) and not PY_NAME.search(word)):
                refused.append(("a quote or backslash inside python or a .py name", line.strip()))
    return refused, launches


class UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader whose mapping constructor checks each key that it builds.

    Its own code is `_construct_mapping`, registered as the constructor for
    the plain mapping tag, tag:yaml.org,2002:map, and for no other tag. Called
    on a mapping node, it skips each key whose tag is tag:yaml.org,2002:merge
    (`<<`). It builds each other key with
    `loader.construct_object(key_node, deep=deep)`, raises a ConstructorError
    when the built key is `in` the list of the keys built before it, and
    appends the key to that list otherwise. Then it returns
    `yaml.SafeLoader.construct_mapping(loader, node, deep=deep)`.

    Loading with UniqueKeyLoader refuses some documents and loads others. The
    self-tests hold a case for each document below, with its outcome on PyYAML
    6.0.3 and Python 3.14.4; these are examples, not a rule for which
    documents are refused. Each document is written as its top-level lines
    joined by "then". How GitHub Actions reads any of these documents is not
    checked.

    - Refused with a message that holds `duplicate key`: the keys `1` and
      `1.0`, `true` and `yes`, `~` and `null`, `a` and `'a'`, and `.nan` and
      `.nan`, each pair in 1 mapping.
    - Refused with a message that holds `duplicate key 'p'`:
      `m: {<<: &b {<<: {p: 1}, p: 2}}` then `n: *b`.
    - Refused with a message that holds `tag:yaml.org,2002:value`:
      `x: {=: a}`, `x: {!!value a: b}`, and `l: [{<<: &b {=: a}}]` then
      `n: *b`.
    - Refused with a message that holds `duplicate key []`:
      `x: {? [a]: 1, ? [b]: 2}`.
    - Refused with a message that holds `recursive node`: `a: &x {b: *x}` and
      `a: &x {b: {<<: *x}}`.
    - Refused with a message that holds `maximum recursion depth`:
      `x: {a: {a: ... 1}}`, with mappings nested 300 deep.
    - Loaded: `on` and `'on'`, as 2 keys, True and a string;
      `x: {<<: {p: 1}, p: 2}`; `x: {<<: {p: 1}, <<: {p: 2}}`;
      `x: {<<: {p: 1, p: 2}}`; `x: !!set {a, a}`;
      `l: [{<<: &b {<<: {p: 1}, p: 2}}]` then `n: *b`;
      `m: {s: [{<<: &b {<<: {p: 1}, p: 2}}]}` then `n: *b`;
      `m: {<<: &b {=: a}}` then `n: *b`; and `x: {y: &b {=: a}, <<: *b}`.
    """


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

    def local_uses(node, where):
        uses = node.get("uses")
        if isinstance(uses, str) and uses.strip().startswith(LOCAL_USES):
            found.append(f"{where}.uses: {uses!r} is a local action or workflow, which this scan does not read")

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
        local_uses(job, where)
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
            local_uses(step, label)
            if "run" in step:
                runs.append((label, step["run"]))
                if "shell" not in step and not job_shell:
                    found.append(f"{label}: run text with no explicit shell: bash at step, job or workflow level")
            if "shell" in step:
                shells.append((label, step["shell"]))
    return runs, shells


def scan_tree(root: Path, floor: int, probe_scripts) -> tuple[list[str], int]:
    """Scan root/.github; return (findings, number of counted launches)."""
    files, findings = list_workflows(root)
    if not files:
        findings.append(f"no workflow found in {root / '.github' / 'workflows'}")
    counted = 0
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
        except Exception as exc:
            first = f"{type(exc).__name__}: {exc}".splitlines()[0]
            findings.append(f"{rel}: cannot be parsed as YAML ({first})")
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
            for reason, line in refused:
                found.append(f"{where}.run: {reason}: {line[:100]}")
            for script, count in launches:
                if not (root / script).is_file():
                    found.append(f"{where}.run: launched script {script} does not exist")
                counted += 1 if count else 0
        findings += [f"{rel}: {reason}" for reason in found]

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

# The sample that the character and pair self-tests of rule 3's right edge put
# after `.py`, which the comment on the character self-test describes. It is
# built once, at import, since building it reads every code point.
EDGE_WIDE = [c for c in map(chr, range(128, sys.maxunicode + 1)) if c.isspace() or unicodedata.category(c) == "Cf"]
EDGE_SAMPLE = [chr(n) for n in range(128)] + EDGE_WIDE + ["\u00e9", "\u03b1", "\u0436", "\u05d0", "\u4e00", "\U00010400"]

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
    # Comments and messages have no exemption (fix round 7). The round 6
    # reproduction: a ")" in a message closes a "$(" opened on the line above.
    ("# see tools/x.py", True),
    ("# the Python gates", True),
    ('echo "tools/x.py is unavailable (exit $1)." >&2', True),
    ('11) echo "tools/x.py rejected it." >&2; exit 1 ;;', True),
    (f'v="$(\necho "a) {X}"', True),
    (f': "\necho "{X}"\n"', True),
    # Each rule's own case
    ("echo the Python gates", True),
    ("echo check.py", True),
    ("p''ython3 -c 'x'", True),
    ("pyth\\on3 -c 'x'", True),
    ("cp a.p''y b", True),
    ('p"y"thon3 -c \'x\'', True),
    ('cp a.p"y" b', True),
    ("PYTHON3 -c 'x'", True),
    ("echo pYthon", True),
    (f"$python3 -I {X}", True),
    (f'v="$python3 -I {X}"', True),
    ("bash -c true", True),
    ("sh -c 'echo ok'", True),
    ('bash -c "$CMD"', True),
    ("/bin/sh -c true", True),
    ("/usr/bin/env bash -c true", True),
    ("bash -o pipefail -c true", True),
    ("bash -e +x -c true", True),
    ("bash --norc -c true", True),
    ("bash -ec true", True),
    ("bash -ce true", True),
    ("bash +o pipefail -c true", True),
    ("bash -eo pipefail -c true", True),
    ("bash -euo pipefail -c true", True),
    ("bash --noprofile --norc -eo pipefail -c true", True),
    (f"bash -eo pipefail -c python3 -I {X} <<EOF", True),
    (f"timeout 300 bash -eo pipefail -c python3 -I {X} <<EOF", True),
    ("nice -n 10 bash -c true", True),
    ("STAMP=$(date) bash -c true", True),
    ("f() { bash -c true; }", True),
    ("x) bash -c true ;;", True),
    ("sleep 1 & bash -c true", True),
    ('A="a b" bash -c true', True),
    ("/usr/bin/bash -ce true", True),
    ('"bash" -c true', True),
    ("bash -c", True),
    ("-c x; bash", True),
    # Accepted false positives: each is refused, and an author rephrases it.
    ("shfmt -ln bash -ci -d tools", True),
    ("bash tools/a.sh -c config", True),
    ("grep bash -c file", True),
    ('echo "use bash -c to run it"', True),
    # Other cases, each marked: True is refused, False passes.
    ("bash --noprofile --norc -eo pipefail tools/a.sh", False),
    ("bash tools/a.sh -cache-dir d", False),
    ("bash tools/a.sh -C dir", False),
    ("bash tools/a.sh", False),
    ("sha256sum -c sums", False),
    ("ssh -c aes128 host", False),
    ("git commit -m x", False),
    ("run a.sh -c x", False),
    ("v=$(dash -c true)", True),
    ("zsh -c true", True),
    ("ksh -xc true", True),
    ("bash tools/test-version-selectors.sh", False),
    ("bash -e -o pipefail tools/a.sh", False),
    ("sha256sum -c SHA256SUMS", False),
    ("ssh -c aes128-ctr host true", False),
    ("fish -c true", False),
    ("git commit -C HEAD", False),
    ("echo bash is the shell", False),
    ("# this step sets BASH_ENV", True),
    ('PATH+=":/x"', True),
    ('export PATH+=":/x"', True),
    ("ENV+=x", True),
    ("MYPATH=x", False),
    ("OLD_ENV=x", False),
    ('echo "$PATH=x"', False),
    ('echo "$ENV="', False),
    # The characters before and after a shell word or a -c cluster, and the
    # letters of a cluster: each case fails when the part of SHELL_WORD or
    # C_CLUSTER that decides it is removed or weakened.
    ("x_bash -c true", False),
    ("a.bash -c true", False),
    ("a-bash -c true", False),
    ("bash_x -c true", False),
    ("bash.x -c true", False),
    ("bash/x -c true", False),
    ("bash-x -c true", False),
    ("bash -Ec true", True),
    ("bash -cE true", True),
    ("bash -xec true", True),
    ("bash -cex true", True),
    ("bash -AZazcAZaz true", True),
    ("bash --c", False),
    ("bash -c_x", False),
    ("bash -c-x", False),
    ("bash a-c", False),
    ("bash x-c", False),
    # An upper-case letter, a digit, a non-ASCII letter or an underscore
    # directly before or after a shell word or a -c cluster: each case fails
    # when the `\w` of the lookaround that decides it no longer holds that
    # class. In `bash -cA1` the 1 keeps `-cA` from being a cluster, so the A
    # after `-c` decides the case.
    ("Abash -c true", False),
    ("1bash -c true", False),
    ("\u00e9bash -c true", False),
    ("bashA -c true", False),
    ("bash1 -c true", False),
    ("bash\u00e9 -c true", False),
    ("bash A-c", False),
    ("bash 1-c", False),
    ("bash \u00e9-c", False),
    ("bash _-c", False),
    ("bash -cA1", False),
    ("bash -c1", False),
    ("bash -c\u00e9", False),
    # A shell word as the last part of a path, whose folders may hold a dot
    # or a hyphen, and a quote directly after a -c cluster. These pin
    # behaviour rather than a part of either pattern: a slash may stand
    # directly before a shell word, and a quote directly after a cluster.
    ("./bash -c true", True),
    ("/opt/a.b/bash -c true", True),
    ("/opt/my-tools/bash -c true", True),
    ("/a/b/c/bash -c true", True),
    ("bash -c'true'", True),
    ('bash -c"true"', True),
    # Rule 3 reads .pyw as well as .py and .pyz, in any letter case, and only
    # when no letter, digit or underscore follows the suffix, so x.pyc, x.py3,
    # x.py_, x.py followed by U+00E9 (a non-ASCII letter) and a property named
    # pyenv pass. Each passing case fails when the `\w` of the lookahead no
    # longer holds the class of the character after the suffix.
    ("./tools/x.pyw", True),
    ("./tools/x.PY", True),
    ("./tools/x.PYZ", True),
    ("echo x.pyc", False),
    ("echo x.py3", False),
    ("echo x.py_", False),
    ("echo x.py\u00e9", False),
    ('echo "${{ steps.pyenv.outputs.v }}"', False),
    # Rule 3 reads these names in any letter case, so it also refuses an
    # expression that names a property PY, Py, PYZ or PYW.
    ('echo "${{ env.PY }}"', True),
    ('echo "${{ matrix.Py }}"', True),
    ('echo "${{ env.PYZ }}"', True),
    ('echo "${{ vars.PYW }}"', True),
    # Rule 4 drops a $ directly before either quote, so p$"y"thon3 and
    # p$'y'thon3 read as python3, and keeps any other $, so py$thon3 does not.
    ('p$"y"thon3 -c \'x\'', True),
    ("p$'y'thon3 -c 'x'", True),
    ('cp a.p$"y" b', True),
    ('echo "$HOME"', False),
    ("echo $'a b'", False),
    ("echo py$thon3", False),
    # Rule 3's right edge. The scan refuses a character directly after `.py`
    # that is not in the edge, rather than read what bash would run:
    # tools/x.py"w" runs tools/x.pyw, and tools/x.py'' runs tools/x.py. That
    # includes a backquote, since the scan cannot tell a closing backquote
    # from an opening one: v=`python3 -I tools/x.py` runs tools/x.py, and
    # tools/x.py`echo w` runs tools/x.pyw. It also refuses a `<(` or `>(`
    # directly after `.py`: tools/x.py<(echo w) runs a script whose name ends
    # with the path of a process substitution. `python3 -I tools/x.py`
    # directly followed by the end of the line, a space, a tab, `|`, `&`, `;`,
    # `(`, `)`, or a `<` or `>` not directly followed by `(`, still reads as a
    # launch, as it does before an operator that starts with one of them, such
    # as `>>`, `<<<`, `>&`, `|&`, `&>` or `;;`.
    (f'python3 -I {X}"w"', True),
    (f"python3 -I {X}'w'", True),
    (f"python3 -I {X}$'w'", True),
    (f'python3 -I {X}"c"', True),
    (f'python3 -I {X}$"w"', True),
    (f"python3 -I {X}$W", True),
    (f"python3 -I {X}*", True),
    (f"python3 -I {X}?", True),
    (f"python3 -I {X}[w]", True),
    (f"python3 -I {X}{{,w}}", True),
    (f"python3 -I {X}`echo w`", True),
    (f"python3 -I {X}~", True),
    (f"python3 -I {X},w", True),
    (f"python3 -I {X}#w", True),
    (f"python3 -I {X}:w", True),
    (f"python3 -I {X}''", True),
    (f"python3 -I {X}\u00a0w", True),
    (f"python3 -I {X}<(echo w)", True),
    (f"python3 -I {X}>(cat)", True),
    (f"v=`python3 -I {X}`", True),
    (f"python3 -I {X}\tw", False),
    (f"python3 -I {X}|cat", False),
    (f"python3 -I {X}&", False),
    (f"python3 -I {X}<f", False),
    (f"python3 -I {X}>f", False),
    (f"python3 -I {X}(", False),
    (f"python3 -I {X}>>f", False),
    (f"python3 -I {X}<<EOF\nw\nEOF", False),
    (f"python3 -I {X}<<<w", False),
    (f"python3 -I {X}>&2", False),
    (f"python3 -I {X}<&0", False),
    (f"python3 -I {X}>|f", False),
    (f"python3 -I {X}|&cat", False),
    (f"python3 -I {X}&>f", False),
    (f'case "$v" in a) python3 -I {X};; esac', False),
    (f"python3 -I {X}>2", False),
    # A character of the edge directly after `.py`, then text that bash reads
    # as another command, an argument or the body of a process substitution.
    # The pair self-test follows each pair with `w`, so these cases fail under
    # edits that it passes, such as one that refuses `&&` only before `t`, or
    # one that counts a `<(` before a space.
    (f"python3 -I {X}&&true", False),
    (f"python3 -I {X}|xargs echo", False),
    (f"python3 -I {X} -x", False),
    (f"python3 -I {X}<( echo w)", True),
    (f"python3 -I {X}>( echo w)", True),
    (f"python3 -I {X}<(xargs echo)", True),
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
    ('echo "The release-date extractor is unavailable (exit $1)." >&2', False),
    ("# the release-date client runs the extractor", False),
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
    # A carriage return reaches run text only through a YAML double-quoted
    # escape. The scan refuses one directly after `.py`: for
    # `python3 -I tools/x.py` followed by a carriage return and `w`, bash
    # passes tools/x.py, the carriage return and `w` as the script.
    ('run: "python3 -I tools/x.py\\rw"', True),
    ("uses: ./tools/action", True),
    ("uses: ../other/action", True),
    ("uses: actions/checkout@" + "a" * 40, False),
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
        missing, _ = scan_tree(root, 1, ())
        if not any("cannot list" in f for f in missing):
            errors.append("self-test: a missing .github folder gave no finding")
        github = root / ".github"
        workflows = github / "workflows"
        workflows.mkdir(parents=True)
        empty, _ = scan_tree(root, 1, ())
        if not any("no workflow" in f for f in empty) or not any("below the floor" in f for f in empty):
            errors.append("self-test: an empty .github did not report both no workflow and the floor")
        case = workflows / "case.yml"
        head = ("on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    defaults:\n      run:\n        shell: bash\n"
                "    steps:\n      - run: python3 -I tools/a.py\n")

        def scan(floor: int = 1, probe=()) -> list[str]:
            return scan_tree(root, floor, probe)[0]

        def run_case(text: str) -> list[str]:
            body = "".join(f"          {line}\n" for line in text.split("\n"))
            case.write_text(head + "      - shell: bash\n        run: |\n" + body, encoding="utf-8")
            return scan()

        for text, want in RUN_CASES:
            if bool(run_case(text)) != want:
                errors.append(f"self-test: run {text!r}: expected {'a finding' if want else 'none'}")
        for text, want in STEP_CASES:
            case.write_text(head + f"      - {text}\n", encoding="utf-8")
            if bool(scan()) != want:
                errors.append(f"self-test: step {text!r}: expected {'a finding' if want else 'none'}")

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
        for text in (f"python3 -I {X}", f"python3 -I {X} --flag", f'v="$(python3 -I {X})"'):
            if check_run(text) != ([], [(X, True)]):
                errors.append(f"self-test: {text!r}: expected no finding and exactly 1 counted launch of {X}")
        # Rule 3's right edge, character by character, over a sample: each
        # ASCII character, each code point that str.isspace() accepts or whose
        # Unicode category is Cf (format), as the Python that runs this reads
        # its Unicode data, and 6 non-ASCII letters of 6 scripts, whose UTF-8
        # lengths span 2 to 4 bytes. Each character of the edge, and a
        # newline, which check_run reads as the end of a line, gives no
        # finding and exactly 1 counted launch, and every other character of
        # the sample gives a finding and no counted launch. The whitespace and
        # format code points are there so that an edit that widens the class
        # by `\s`, which matches what str.isspace() accepts, or by any
        # whitespace or format code point but a newline, fails here. A newline
        # added to the class passes every self-test, an equivalent edit:
        # check_run splits the run text on newlines before LAUNCH reads a
        # line. The loop pins the verdict on each sampled character before
        # `w`, not on every edit: the comment on the pair self-test below
        # names the edits that can pass it, a residual.
        edge = " \t|&;()<>\n"
        for c in EDGE_SAMPLE:
            refused, launches = check_run(f"python3 -I {X}{c}w")
            if c in edge and (refused, launches) != ([], [(X, True)]):
                errors.append(f"self-test: {c!r} after {X}: expected no finding and exactly 1 counted launch of {X}")
            elif c not in edge and (not refused or (X, True) in launches):
                errors.append(f"self-test: {c!r} after {X}: expected a finding and no counted launch of {X}")
        # Rule 3's right edge, pair by pair, over the same sample. As written,
        # the edge reads at most 2 characters after `.py`: a character of its
        # class, or a `<` or `>` and then the character that its lookahead
        # tests. This loop puts each character of the edge, followed by each
        # character of the sample, between `python3 -I tools/x.py` and `w`,
        # and so pins the verdict on each such pair before `w`, not on every
        # edit. An edit whose verdict differs from the edge's only on text
        # after `.py` that no self-test scans passes every self-test, a
        # residual. Such an edit can, for example, change the verdict only for
        # a code point outside the sample, only where the text beyond the
        # second character after `.py` differs, or only where a character
        # outside the edge is followed by anything but `w`, if no case holds
        # that text. Each pair gives no finding and exactly 1 counted launch,
        # except `<(` and `>(`, which give a finding and no counted launch.
        # The edge here leaves out the newline: check_run splits the run text
        # on newlines before LAUNCH reads a line, so the edge never reads a
        # character after one.
        for e in " \t|&;()<>":
            for c in EDGE_SAMPLE:
                refused, launches = check_run(f"python3 -I {X}{e}{c}w")
                pair = f"self-test: {e!r} then {c!r} after {X}"
                if e + c not in ("<(", ">(") and (refused, launches) != ([], [(X, True)]):
                    errors.append(f"{pair}: expected no finding and exactly 1 counted launch of {X}")
                elif e + c in ("<(", ">(") and (not refused or (X, True) in launches):
                    errors.append(f"{pair}: expected a finding and no counted launch of {X}")

        two_jobs = ("on: push\njobs:\n  a:\n    defaults:\n      run:\n        shell: bash\n    steps:\n"
                    "      - run: python3 -I tools/a.py\n  b:\n    steps:\n      - run: echo ok\n")
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
            ("a second job without the first job's shell", two_jobs, "jobs.b.steps[0]: run text with no explicit shell"),
            ("a job that uses a local reusable workflow", head + "  k:\n    uses: ./.github/workflows/w.yml\n",
             "jobs.k.uses: './.github/workflows/w.yml' is a local action"),
            ("keys 1 and 1.0", "x:\n  1: a\n  1.0: b\n" + head, "duplicate key"),
            ("keys true and yes", "x:\n  true: a\n  yes: b\n" + head, "duplicate key"),
            ("keys ~ and null", "x:\n  ~: a\n  null: b\n" + head, "duplicate key"),
            ("keys a and 'a'", "x:\n  a: 1\n  'a': 2\n" + head, "duplicate key"),
            ("an anchored mapping with a merge and an override, merged and then reused as an alias",
             "m: {<<: &b {<<: {p: 1}, p: 2}}\nn: *b\n" + head, "duplicate key 'p'"),
            ("a mapping with a repeated key, merged and then reused as an alias",
             "m: {<<: &b {p: 1, p: 2}}\nn: *b\n" + head, "duplicate key"),
            ("an anchored mapping whose 2 merge keys supply the same key, merged and then reused as an alias",
             "m: {<<: &b {<<: {p: 1}, <<: {p: 2}}}\nn: *b\n" + head, "duplicate key"),
            ("an anchored mapping whose merge list repeats a key, merged and then reused as an alias",
             "m: {<<: &b {<<: [{p: 1}, {p: 2}]}}\nn: *b\n" + head, "duplicate key"),
            ("a mapping with a merge and an override, held and merged by the same mapping",
             "m: {a: &b {<<: {p: 1}, p: 2}, <<: *b}\n" + head, "duplicate key"),
            ("keys .nan and .nan", "x:\n  .nan: a\n  .nan: b\n" + head, "duplicate key"),
            ("a plain = key", "x:\n  =: a\n" + head, "tag:yaml.org,2002:value"),
            ("a key tagged !!value", "x:\n  !!value a: b\n" + head, "tag:yaml.org,2002:value"),
            ("a plain = key in a flow mapping", "x: {=: a}\n" + head, "tag:yaml.org,2002:value"),
            ("a key tagged !!value in a flow mapping", "x: {!!value a: b}\n" + head, "tag:yaml.org,2002:value"),
            ("2 sequence keys", "x: {? [a]: 1, ? [b]: 2}\n" + head,
             "duplicate key []"),
            ("a mapping that holds an alias to itself", "a: &x {b: *x}\n" + head, "recursive node"),
            ("a mapping merged into one of its own values", "a: &x {b: {<<: *x}}\n" + head,
             "recursive node"),
            ("a mapping with a merge and an override, held in a sequence and merged by a later key",
             "m: [&b {<<: {p: 1}, p: 2}]\no: {<<: *b}\n" + head, "duplicate key 'p'"),
            ("a plain = key in a mapping merged in a sequence and reused as a later alias",
             "l: [{<<: &b {=: a}}]\nn: *b\n" + head, "tag:yaml.org,2002:value"),
            ("a mapping with a merge and an override, held in a sequence in a mapping and merged by a later key",
             "m: {s: [&b {<<: {p: 1}, p: 2}]}\no: {<<: *b}\n" + head, "duplicate key 'p'"),
            ("a mapping nested 300 deep", "x: " + "{a: " * 300 + "1" + "}" * 300 + "\n" + head,
             "cannot be parsed as YAML (RecursionError: maximum recursion depth"),
            # Loading these raises, in turn, a ValueError, a ValueError, an
            # IndexError, a KeyError, an AttributeError, a TypeError and an
            # OverflowError, none of them a YAML error, and scan_tree turns
            # any exception raised while loading into a finding that names its
            # type.
            ("an impossible date", "x: 2001-02-30\n" + head,
             "cannot be parsed as YAML (ValueError: day 30 must be in range 1..28 for month 2 in year 2001)"),
            ("a !!int tag on a word", "x: !!int a\n" + head,
             "cannot be parsed as YAML (ValueError: invalid literal for int() with base 10: 'a')"),
            ("a !!int tag on an empty string", "x: !!int ''\n" + head,
             "cannot be parsed as YAML (IndexError: string index out of range)"),
            ("a !!bool tag on a word", "x: !!bool a\n" + head, "cannot be parsed as YAML (KeyError: 'a')"),
            ("a !!timestamp tag on a word", "x: !!timestamp a\n" + head,
             "cannot be parsed as YAML (AttributeError: 'NoneType' object has no attribute 'groupdict')"),
            ("a !!map tag on a sequence", "x: !!map [a]\n" + head,
             "cannot be parsed as YAML (TypeError: cannot unpack non-iterable ScalarNode object)"),
            ("a float scalar of 175 colon-separated parts", "x: 1" + ":0" * 173 + ":0.5\n" + head,
             "cannot be parsed as YAML (OverflowError: int too large to convert to float)"),
        ]
        for name, text, needle in whole:
            case.write_text(text, encoding="utf-8")
            if not any(needle in f for f in scan()):
                errors.append(f"self-test: whole file {name} gave no finding naming {needle!r}")
        # An exception whose message is empty must still give a finding that
        # names its type. A constructor for a private tag raises one, and is
        # removed afterwards so that no later case loads the tag.
        def raise_empty(loader, node):
            raise ValueError()

        UniqueKeyLoader.add_constructor("!empty", raise_empty)
        case.write_text("x: !empty a\n" + head, encoding="utf-8")
        try:
            findings = scan()
        except Exception as exc:
            findings = [f"a crash with {type(exc).__name__}"]
        finally:
            del UniqueKeyLoader.yaml_constructors["!empty"]
        if not any("cannot be parsed as YAML (ValueError: )" in f for f in findings):
            errors.append(f"self-test: an exception with an empty message gave {findings!r}")
        clean = [
            ("a YAML merge key",
             "x: &c\n  runs-on: ubuntu-latest\n  defaults:\n    run:\n      shell: bash\non: push\njobs:\n"
             "  j:\n    <<: *c\n    steps:\n      - run: python3 -I tools/a.py\n"),
            ("a workflow-level shell: bash",
             "on: push\ndefaults:\n  run:\n    shell: bash\njobs:\n  j:\n    steps:\n"
             "      - run: python3 -I tools/a.py\n"),
            ("a step-level shell: bash with no job or workflow shell",
             "on: push\njobs:\n  j:\n    steps:\n      - shell: bash\n        run: python3 -I tools/a.py\n"),
            ("a job that uses a remote reusable workflow",
             head + "  k:\n    uses: octo/repo/.github/workflows/w.yml@" + "a" * 40 + "\n"),
            ("a job-level shell: bash for each of two jobs",
             two_jobs.replace("  b:\n    steps:", "  b:\n    defaults:\n      run:\n        shell: bash\n    steps:")),
            ("a merge with an override", "x: {<<: {p: 1}, p: 2}\n" + head),
            ("a mapping with 2 merge keys", "x: {<<: {p: 1}, <<: {q: 2}}\n" + head),
            ("a mapping with 2 merge keys that supply the same key", "x: {<<: {p: 1}, <<: {p: 2}}\n" + head),
            ("a repeated key in a merge source", "x: {<<: {p: 1, p: 2}}\n" + head),
            ("a repeated key in a merge list's source", "x: {<<: [{p: 1, p: 2}]}\n" + head),
            ("a top-level mapping with a merge and an override, then merged and reused as an alias",
             "a: &b {<<: {p: 1}, p: 2}\nm: {<<: *b}\nn: *b\n" + head),
            ("a mapping with a merge and an override, merged by 2 mappings",
             "m: {<<: &b {<<: {p: 1}, p: 2}}\no: {<<: *b}\n" + head),
            ("a !!set with a repeated member", "x: !!set {a, a}\n" + head),
            ("keys on and 'on'", "'on': x\n" + head, {True: "push", "on": "x"}),
            ("an !!omap with a repeated key", "x: !!omap [{a: 1}, {a: 2}]\n" + head),
            ("a !!pairs with a repeated key", "x: !!pairs [{a: 1}, {a: 2}]\n" + head),
            ("a plain = key in a merged mapping reused as an alias", "m: {<<: &b {=: a}}\nn: *b\n" + head,
             {"m": {"=": "a"}, "n": {"=": "a"}}),
            ("a mapping that holds an alias to itself through a list", "a: &x {b: [*x]}\n" + head),
            ("a mapping that is its own merge source", "a: &x {<<: *x}\n" + head, {"a": {}}),
            ("a mapping that holds a key and is its own merge source", "a: &x {b: 1, <<: *x}\n" + head, {"a": {"b": 1}}),
            ("a mapping whose merge list holds only itself", "a: &x {<<: [*x]}\n" + head, {"a": {}}),
            ("a mapping with a merge and an override, merged in a sequence and reused as a later alias",
             "l: [{<<: &b {<<: {p: 1}, p: 2}}]\nn: *b\n" + head, {"l": [{"p": 2}], "n": {"p": 2}}),
            ("a mapping with a merge and an override, merged in a sequence in a mapping and reused as a later alias",
             "m: {s: [{<<: &b {<<: {p: 1}, p: 2}}]}\nn: *b\n" + head, {"m": {"s": [{"p": 2}]}, "n": {"p": 2}}),
            ("a mapping with a merge and an override, held in a sequence, reused as an alias and merged in the same mapping",
             "m: {s: [&b {<<: {p: 1}, p: 2}], t: *b, u: {<<: *b}}\n" + head,
             {"m": {"s": [{"p": 2}], "t": {"p": 2}, "u": {"p": 2}}}),
            ("a plain = key in a merge source", "x: {<<: {=: a}}\n" + head, {"x": {"=": "a"}}),
            ("a plain = key in a mapping held and merged by the same mapping", "x: {y: &b {=: a}, <<: *b}\n" + head,
             {"x": {"=": "a", "y": {"=": "a"}}}),
        ]
        # A third member maps top-level keys to the values they must load to,
        # since a case can pass the scan and still load to another value.
        for name, text, *value in clean:
            case.write_text(text, encoding="utf-8")
            if scan():
                errors.append(f"self-test: {name} gave {scan()!r}")
            elif value:
                doc = yaml.load(text, Loader=UniqueKeyLoader)
                if {key: doc.get(key) for key in value[0]} != value[0]:
                    errors.append(f"self-test: {name} loaded {doc!r}, not {value[0]!r}")
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
    findings, count = scan_tree(REPO, LAUNCH_FLOOR, PROBE_SCRIPTS)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s), {count} launches")
        return 1
    print(f"OK: {count} Python launches in the workflows, every one python3 -I tools/<name>.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
