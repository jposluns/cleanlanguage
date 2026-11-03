#!/usr/bin/env python3
"""Check that every Python launch in the workflows and local actions runs isolated.

Scope. This check catches an honest or accidental Python launch without `-I`.
It reads the YAML structurally, so prose such as a step name, a description or
an issue form is never scanned. It is a scan of the pull request's own
checkout, so it is no defence against deliberate obfuscation: the author of
such a change can also edit this scan, its floor or its workflow, and only
review catches that.

A Python-launched gate that finds a planted file on its module path can import
that file in place of a standard-library module and turn the gate into a green
run that checked nothing. `python3 -I` keeps the script folder off the module
path and ignores the user site directory and every PYTHON* variable.

What is checked:

1. Every .yml and .yaml file under .github, in every subfolder, is parsed with
   PyYAML's safe loader. A file that cannot be listed, read as UTF-8 or parsed,
   a duplicate mapping key, a symbolic link under .github, and a file holding
   U+0085, U+2028 or U+2029 (which YAML 1.1 and 1.2 read differently) are
   findings. With no YAML file at all, the floor below fails too.
2. A file directly in .github/workflows is a workflow; a file named action.yml
   or action.yaml anywhere under .github is a local action. From workflows the
   scan collects each job's `uses`, the `shell` of `defaults.run` at workflow
   and job level, and the `run`, `uses` and `shell` of every step. A local
   action must have `runs.using: composite`, since a Docker or JavaScript
   entry point would launch code the scan cannot read; its steps are collected
   the same way. Other YAML files, such as issue forms, are only parsed. A
   structure the scan cannot classify is a finding.
3. Each `uses` must be `<owner>/<repo>[/<path>]@<40 hex digits>` or
   `./.github/<path>` with no `..` that names an existing action or workflow.
   Each `shell` must start with bash, sh, pwsh, powershell or cmd.
4. Each `run` string is read as bash: line continuations are joined, comments
   and here-document bodies are dropped, quotes are removed, and the text is
   split into simple commands, including those inside `$( )`, `<( )` and
   backticks. Quoted text is data. In each command, leading `if`, `then`,
   `else`, `elif`, `do`, `while`, `until`, `!`, `{`, `time`, VAR=value words,
   and the wrappers env, exec, nohup, nice, sudo, xargs, stdbuf and timeout
   (with their options and a duration) are skipped to find the command word.
   - A command word whose name starts with `python` must be written exactly
     `python3`, then `-I`, then any options of letters without c, m, Q, W or
     X, then `tools/<name>.py` with nothing joined to it. That is an allowed
     launch, and only allowed launches count toward LAUNCH_FLOOR.
   - A command word that ends in `.py` (a script run by its first line) is a
     finding.
   - A shell (sh, bash, dash, zsh, ksh) must run a `.sh` file, with no `-c`
     or `-s`; a shell that reads its commands from a pipe, a here-document,
     `-c` or stdin is a finding. So is `eval`.
   - A word whose text, once quotes and backslashes are removed, holds
     `python` or a `<name>.py` that its written form does not hold (a quote
     or backslash inside the word) is a finding.
   - A quote, `$'` string, `${`, `$(`, backtick or here-document left open
     is a finding.
5. A launched script must exist. Every .py file under tools/ is read as
   tokens, and it fails when its code changes `sys.path`: assignment,
   augmented assignment, item assignment or deletion, or any method other
   than copy, index and count, on `sys.path` written through `sys` or any
   alias from `import sys as`, with or without parentheses around it. Any
   reference to meta_path, path_hooks or path_importer_cache, any import
   of those names or `path` from sys, and site.addsitedir also fail.
6. Tempfile.py, msvcrt.py, nt.py and _winapi.py are planted beside a copy of
   each script in PROBE_SCRIPTS, the copy runs under `-I`, and the scan fails
   if a planted module ran.

It runs its own self-tests first and stops on any failure. They run the whole
scan on temporary trees, with a case that only each rule catches and a set of
honest forms that must pass.

Residuals, named here because the scan reads text the pull request controls:

- obfuscation inside run text, such as a glob, `${{ }}` expressions that
  GitHub expands before bash runs, brace expansion and parameter expansion;
- run text built at run time, such as a file written and then run, a
  variable holding a command, or `source` and `.` of a generated file;
- launchers that are not a command word named python, or that name no `.py`
  path, such as pytest, coverage, a wrapper not listed above, or an
  extensionless script;
- a `cd` before a launch, after which `tools/<name>.py` names another file;
- shell scripts the workflows run, which this scan does not read;
- Docker and JavaScript entry points, which are refused rather than read, and
  remote actions and reusable workflows, which are outside this repository;
- a sys.path change made other than in the forms above, such as through
  getattr or a list bound to sys.path;
- an allowed launch in a step that never runs, which still counts toward the
  floor.

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

# The number of allowed launches under .github when this check landed.
LAUNCH_FLOOR = 51

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
SHELLS_ALLOWED = ("bash", "sh", "pwsh", "powershell", "cmd")
SHELLS = ("sh", "bash", "dash", "zsh", "ksh")
KEYWORDS = ("if", "then", "else", "elif", "do", "while", "until", "!", "{", "time")
WRAPPERS = ("env", "exec", "nohup", "nice", "sudo", "xargs", "stdbuf", "timeout")
ASSIGNMENT = re.compile(r"[A-Za-z_]\w*\+?=")
DURATION = re.compile(r"\d+(?:\.\d+)?[smhd]?")
OPTION = re.compile(r"-[A-Za-z]+")
SCRIPT = re.compile(r"tools/[\w.-]+\.py")
PY_NAME = re.compile(r"[\w./-]*\.py(?![\w])")


class Word:
    def __init__(self) -> None:
        self.raw = ""
        self.text = ""
        self.target = False


class ShellReader:
    """Split bash text into simple commands of words, as bash would read them.

    Quotes are removed from each word's `text` and kept in its `raw` form.
    Comments and here-document bodies are dropped. Problems the reader cannot
    resolve, such as an unterminated quote, are collected in `problems`.
    """

    def __init__(self, source: str) -> None:
        self.s = source
        self.i = 0
        self.commands: list[list[Word]] = []
        self.problems: list[str] = []
        self.heredocs: list[tuple[str, bool]] = []
        self.frame(None)
        if self.heredocs:
            self.problems.append("an unterminated here-document")

    def peek(self, k: int = 0) -> str:
        return self.s[self.i + k : self.i + k + 1]

    def frame(self, closer: str | None) -> None:
        words: list[Word] = []
        word: Word | None = None
        depth = 0
        next_role = None

        def end_word() -> None:
            nonlocal word, next_role
            if word is not None:
                if next_role == "heredoc":
                    self.heredocs.append((word.text, self._strip))
                    word.target = True
                elif next_role == "target":
                    word.target = True
                words.append(word)
                next_role = None
            word = None

        def end_command() -> None:
            nonlocal words
            end_word()
            if words:
                self.commands.append(words)
            words = []

        def add(raw: str, text: str) -> None:
            nonlocal word
            if word is None:
                word = Word()
            word.raw += raw
            word.text += text

        while self.i < len(self.s):
            c = self.peek()
            if closer == "`" and c == "`":
                self.i += 1
                end_command()
                return
            if c == "\\":
                following = self.peek(1)
                if following == "\n":
                    self.i += 2
                    continue
                add(c + following, following)
                self.i += 2
                continue
            if c == "'":
                self.single(add)
                continue
            if c == "$" and self.peek(1) == "'":
                self.ansi_c(add)
                continue
            if c == '"':
                self.double(add)
                continue
            if c == "$" and self.peek(1) == "(":
                self.i += 2
                add("$(", "$(")
                self.frame(")")
                add(")", ")")
                continue
            if c == "$" and self.peek(1) == "{":
                self.braces(add)
                continue
            if c == "`":
                self.i += 1
                add("`", "`")
                self.frame("`")
                continue
            if c in "<>" and self.peek(1) == "(":
                self.i += 2
                add(c + "(", c + "(")
                self.frame(")")
                add(")", ")")
                continue
            if c == "#" and word is None:
                while self.i < len(self.s) and self.peek() != "\n":
                    self.i += 1
                continue
            if c in " \t":
                end_word()
                self.i += 1
                continue
            if c == "\n":
                end_command()
                self.i += 1
                self.read_heredocs()
                continue
            if c == ")" and closer == ")":
                self.i += 1
                if depth == 0:
                    end_command()
                    return
                depth -= 1
                end_command()
                continue
            if c == "(":
                depth += 1
                self.i += 1
                end_command()
                continue
            if c == ")":
                self.i += 1
                end_command()
                continue
            if c == "&" and self.peek(1) == ">":
                end_word()
                self.i += 3 if self.peek(2) == ">" else 2
                next_role = "target"
                continue
            if c in ";&|":
                for op in (";;&", ";;", ";&", "&&", "||", "|&", "|", ";", "&"):
                    if self.s.startswith(op, self.i):
                        break
                self.i += len(op)
                end_command()
                continue
            if c in "<>":
                if word is not None and word.raw.isdigit():
                    word = None
                end_word()
                for op in ("<<<", "<<-", "<<", ">>", ">&", ">|", "<&", "<>", ">", "<"):
                    if self.s.startswith(op, self.i):
                        break
                self.i += len(op)
                if op in ("<<", "<<-"):
                    next_role = "heredoc"
                    self._strip = op == "<<-"
                else:
                    next_role = "target"
                if op.endswith("&"):
                    while self.peek() and (self.peek().isdigit() or self.peek() == "-"):
                        self.i += 1
                    next_role = None
                continue
            add(c, c)
            self.i += 1
        if closer is not None:
            self.problems.append(f"an unterminated {'$(' if closer == ')' else '`'}")
        end_command()

    _strip = False

    def single(self, add) -> None:
        end = self.s.find("'", self.i + 1)
        if end < 0:
            self.problems.append("an unterminated single quote")
            add(self.s[self.i :], self.s[self.i + 1 :])
            self.i = len(self.s)
            return
        add(self.s[self.i : end + 1], self.s[self.i + 1 : end])
        self.i = end + 1

    def ansi_c(self, add) -> None:
        start = self.i
        self.i += 2
        text = ""
        escapes = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", '"': '"', "a": "\a", "e": "\x1b"}
        while self.i < len(self.s):
            c = self.peek()
            if c == "'":
                self.i += 1
                add(self.s[start : self.i], text)
                return
            if c == "\\":
                code = self.peek(1)
                match = re.match(r"x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|([0-7]{1,3})", self.s[self.i + 1 :])
                if match:
                    digits = match.group(1) or match.group(2)
                    text += chr(int(digits, 16)) if digits else chr(int(match.group(3), 8))
                    self.i += 1 + len(match.group(0))
                    continue
                text += escapes.get(code, code)
                self.i += 2
                continue
            text += c
            self.i += 1
        self.problems.append("an unterminated $' string")
        add(self.s[start:], text)

    def double(self, add) -> None:
        add('"', "")
        self.i += 1
        while self.i < len(self.s):
            c = self.peek()
            if c == '"':
                add('"', "")
                self.i += 1
                return
            if c == "\\":
                following = self.peek(1)
                if following == "\n":
                    self.i += 2
                elif following in '$`"\\':
                    add(c + following, following)
                    self.i += 2
                else:
                    add(c, c)
                    self.i += 1
                continue
            if c == "$" and self.peek(1) == "(":
                self.i += 2
                add("$(", "$(")
                self.frame(")")
                add(")", ")")
                continue
            if c == "`":
                self.i += 1
                add("`", "`")
                self.frame("`")
                continue
            add(c, c)
            self.i += 1
        self.problems.append("an unterminated double quote")

    def braces(self, add) -> None:
        depth = 0
        start = self.i
        self.i += 1
        while self.i < len(self.s):
            c = self.peek()
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    add(self.s[start : self.i], self.s[start : self.i])
                    return
            self.i += 1
        self.problems.append("an unterminated ${")
        add(self.s[start:], self.s[start:])

    def read_heredocs(self) -> None:
        while self.heredocs:
            delimiter, strip = self.heredocs.pop(0)
            while True:
                end = self.s.find("\n", self.i)
                line = self.s[self.i :] if end < 0 else self.s[self.i : end]
                self.i = len(self.s) if end < 0 else end + 1
                if (line.lstrip("\t") if strip else line) == delimiter:
                    break
                if end < 0:
                    self.problems.append(f"an unterminated here-document ({delimiter})")
                    return


def command_word(words: list[Word]) -> int:
    """Return the index of the command word, after keywords, assignments and wrappers."""
    k = 0
    while k < len(words):
        raw = words[k].raw
        if raw in KEYWORDS or ASSIGNMENT.match(raw):
            k += 1
            continue
        if raw in WRAPPERS:
            k += 1
            while k < len(words) and (words[k].raw.startswith("-") or ASSIGNMENT.match(words[k].raw)):
                k += 1
            if raw == "timeout" and k < len(words) and DURATION.fullmatch(words[k].raw):
                k += 1
            continue
        break
    return k


def check_run(text: str) -> tuple[list[str], list[str]]:
    """Return (findings, launched scripts) for one run string."""
    reader = ShellReader(text)
    findings = list(reader.problems)
    launches: list[str] = []
    for all_words in reader.commands:
        for w in all_words:
            if "python" in w.text and "python" not in w.raw:
                findings.append(f"a quote or backslash inside the word python: {w.raw!r}")
            for name in PY_NAME.findall(w.text):
                if name not in w.raw:
                    findings.append(f"a quote or backslash inside a .py name: {w.raw!r}")
        words = [w for w in all_words if not w.target]
        k = command_word(words)
        if k >= len(words):
            continue
        head = words[k]
        name = head.text.rsplit("/", 1)[-1]
        if name.startswith("python"):
            launch = head.raw == "python3" and k + 1 < len(words) and words[k + 1].raw == "-I"
            j = k + 2
            while launch and j < len(words) and OPTION.fullmatch(words[j].raw) and not set("cmQWX") & set(words[j].raw):
                j += 1
            if launch and j < len(words) and SCRIPT.fullmatch(words[j].raw):
                launches.append(words[j].raw)
            else:
                shown = " ".join(w.raw for w in words[k : k + 4])
                findings.append(f"python is launched other than as python3 -I tools/<name>.py: {shown}")
        elif head.text.endswith(".py"):
            findings.append(f"a .py file is run directly: {head.raw}")
        elif name in SHELLS:
            j = k + 1
            fed = False
            while j < len(words) and OPTION.fullmatch(words[j].raw):
                fed = fed or bool(set("cs") & set(words[j].raw))
                j += 1
            if fed or j >= len(words) or not words[j].text.endswith(".sh"):
                findings.append(f"a shell is fed text rather than a .sh file: {' '.join(w.raw for w in words[k:k + 3])}")
        elif head.raw == "eval":
            findings.append("eval runs text the scan cannot read")
    return findings, launches


class UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses a mapping with a repeated key."""


def _construct_mapping(loader, node, deep=False):
    keys = []
    for key_node, _ in node.value:
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


def local_target_exists(root: Path, value: str) -> bool:
    target = root / value
    if target.is_file():
        return True
    return any((target / name).is_file() for name in ("action.yml", "action.yaml"))


def scan_tree(root: Path, floor: int, probe_scripts) -> tuple[list[str], int]:
    """Scan the YAML under root/.github; return (findings, number of allowed launches)."""
    files, findings = list_yaml(root)
    if not files:
        findings.append(f"no YAML file found under {root / '.github'}")
    workflows = root / ".github" / "workflows"
    launches: list[tuple[str, str]] = []
    for path in files:
        rel = path.relative_to(root)
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
            else:
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
        for where, value in items["uses"]:
            if not isinstance(value, str):
                found.append(f"{where}.uses: not a string")
            elif LOCAL_USES.fullmatch(value) and ".." not in value.split("/"):
                if not local_target_exists(root, value):
                    found.append(f"{where}.uses: {value} names no action or workflow file")
            elif not REMOTE_USES.fullmatch(value):
                found.append(f"{where}.uses: {value!r} is neither pinned to a full commit nor a path under .github")
        for where, value in items["shell"]:
            first = value.split()[0].rsplit("/", 1)[-1] if isinstance(value, str) and value.split() else None
            if first not in SHELLS_ALLOWED:
                found.append(f"{where}.shell: {value!r} is not a bash, sh, pwsh, powershell or cmd shell")
        for where, value in items["run"]:
            if isinstance(value, (bool, int, float)):
                value = str(value)
            if not isinstance(value, str):
                found.append(f"{where}.run: not text")
                continue
            run_findings, run_launches = check_run(value)
            found += [f"{where}.run: {reason}" for reason in run_findings]
            launches += [(f"{rel}: {where}", script) for script in run_launches]
        findings += [f"{rel}: {reason}" for reason in found]

    for where, script in launches:
        if not (root / script).is_file():
            findings.append(f"{where}: launched script {script} does not exist")

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

    if len(launches) < floor:
        findings.append(f"only {len(launches)} allowed launches found, below the floor of {floor}")

    for script in probe_scripts:
        failure = planted_module_runs(root, script)
        if failure:
            findings.append(failure)
    return findings, len(launches)


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
        if token == "import" and (i == 0 or tokens[i - 1] == ";"):
            j = i + 1
            while j < len(tokens) and tokens[j] != ";":
                if tokens[j] == "sys" and tokens[j + 1 : j + 2] == ["as"]:
                    aliases.add(tokens[j + 2])
                j += 1
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

# Run text that must give a finding (True) or must pass (False).
RUN_CASES = [
    ("python3 tools/x.py", True),
    ("python tools/x.py", True),
    ("/usr/bin/python3 -I tools/x.py", True),
    (".venv/bin/python3 -I tools/x.py", True),
    ('"$pythonLocation/bin/python3" -I tools/x.py', True),
    ("python3.13t -I tools/x.py", True),
    ("env python3 tools/x.py", True),
    ("sudo python3 tools/x.py", True),
    ("python3-coverage run tools/x.py", True),
    ("python3 -E -s tools/x.py", True),
    ("python3 -X utf8 -I tools/x.py", True),
    ("python3 -I -X utf8 tools/x.py", True),
    ('python3 -I "tools/x.py"', True),
    ("python3 -I -c 'x'", True),
    ("python3 -I -m tools.x", True),
    ("python3 -I tools/x.pyc", True),
    ("timeout 300 python3 tools/x.py", True),
    ("python3 -I -m tools/x.py", True),
    ("bash -c tools/x.sh", True),
    ("echo 'open", True),
    ("echo $'open", True),
    ("echo ${open", True),
    ("cp tools/x.p''y out", True),
    ("python3 -I scripts/x.py", True),
    ('"python3" -I tools/x.py', True),
    ("p''ython3 -I tools/x.py", True),
    ("pyth\\on3 -I tools/x.py", True),
    ("$'\\x70ython3' -I tools/x.py", True),
    ("python3 -I tools/x.p''y", True),
    ("PY=py''thon3", True),
    ("python3() { command python3 \"$@\"; }", True),
    ("py\\\nthon3 tools/x.py", True),
    ("true\\\n# || python3 tools/x.py", True),
    ("true $'\\'\n# '; tools/x.py", True),
    ("tools/x.py", True),
    ("./x.py", True),
    ('"tools/x.py"', True),
    ('out="$(tools/x.py)"', True),
    ("exec tools/x.py", True),
    ("echo a | xargs tools/x.py", True),
    ("if python3 tools/x.py; then true; fi", True),
    ("echo x | sh", True),
    ('echo "tools/x.py" | bash', True),
    ("bash -c 'python3 -I tools/x.py'", True),
    ("bash <<EOF\npython3 tools/x.py\nEOF", True),
    ("sed 's/^# //' <<'EOF' | sh\n# tools/x.py\nEOF", True),
    ("eval true", True),
    ('echo "open', True),
    ("echo $(true", True),
    ("cat <<EOF\nno end", True),
    ("python3 -I tools/x.py", False),
    ("python3 -I -B tools/x.py", False),
    ("python3 -I tools/x.py;", False),
    ("python3 -I tools/x.py\t--flag", False),
    ("python3 -I \\\n  tools/x.py", False),
    ("if python3 -I tools/x.py; then echo ok; fi", False),
    ("if ! python3 -I tools/x.py; then exit 1; fi", False),
    ("LC_ALL=C python3 -I tools/x.py", False),
    ("test -f site/x || python3 -I tools/x.py", False),
    ("true && python3 -I tools/x.py", False),
    ("timeout 300 python3 -I tools/x.py", False),
    ("diff <(python3 -I tools/x.py) site/y", False),
    ("python3 -I tools/x.py site/x.py", False),
    ("python3 -I tools/check-python-version.py", False),
    ('v="$(git show X | python3 -I tools/x.py)"', False),
    ("python3 -I tools/x.py --a \"$(date -u +%Y)\" >/dev/null || rc=$?", False),
    ('printf "%s\\n" "${x}"', False),
    ('grep -Eq "^v[0-9]+\\.[0-9]+$" <<< "${v}"', False),
    ('echo "notes<<EOF" >> "$GITHUB_OUTPUT"', False),
    ("cat <<EOF >> \"$GITHUB_STEP_SUMMARY\"\nIt's done; python3 tools/x.py is only text.\nEOF", False),
    ('cp out.txt "$RUNNER_TEMP"/out.txt', False),
    ('gh release create "v${{ env.VERSION }}"', False),
    ("jq -n '{a: {b: 1}}'", False),
    ('echo "It\'s done"', False),
    ("cd x && bash tools/y.sh", False),
    ("true && bash tools/x.sh", False),
    ("echo input | bash tools/x.sh", False),
    ('echo "pipe it | sh" >&2', False),
    ("# it's a comment naming python3 tools/x.py", False),
    ('echo "tools/x.py is unavailable (exit $1)" >&2', False),
    ('case "$rc" in 0) ;; *) echo "bad" >&2; exit 1 ;; esac', False),
    ('gh release download x \\\n  --pattern "a.zip"', False),
    ("awk '$2 ~ /\\^\\{\\}$/ { print $1 }' f", False),
]

STEP_CASES = [
    # (step lines under "- ", True when a finding is expected)
    ("name: Check the site's links\n        run: python3 -I tools/x.py", False),
    ("name: Check the source links\n        run: echo ok", False),
    ("name: Confirm the release uses the pinned checksum\n        run: echo ok", False),
    ("name: Run the bash selector tests\n        run: echo ok", False),
    ("name: Check \u2014 headers\n        run: echo ok", False),
    ("shell: bash\n        run: python3 -I tools/x.py", False),
    ("shell: bash # strict\n        run: echo ok", False),
    ("shell: bash -e {0}\n        run: echo ok", False),
    (f"uses: actions/setup-python@{PIN}\n        with:\n          python-version: \"3.12\"", False),
    (f'uses: "actions/checkout@{PIN}"', False),
    (f"uses: actions/checkout@{PIN}\n        with:\n          ref: v${{{{ inputs.version }}}}", False),
    ("if: hashFiles('**/*.py') != ''\n        run: echo ok", False),
    ("shell: python\n        run: print(1)", True),
    ("shell: /usr/bin/python {0}\n        run: print(1)", True),
    ("uses: actions/checkout@v4", True),
    ("uses: docker://alpine:3", True),
    ("uses: ./actions/m", True),
    ("uses: ./.github/workflows/../actions/m", True),
    ("uses: ./.github/actions/none", True),
    ("run: 12", False),
    ("run: [a, b]", True),
    ("uses: [a]", True),
    ("run: cat <<EOF", True),
    ("run: |\n          true\n        run: python3 tools/x.py", True),
]


def self_test() -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = root / "tools"
        tools.mkdir()
        for name in ("a", "x", "y", "check-python-version"):
            (tools / f"{name}.py").write_text("import tempfile\n", encoding="utf-8")
        (tools / "x.pyc").write_bytes(b"")
        missing, _ = scan_tree(root, 1, ())
        if not any("cannot list" in f for f in missing):
            errors.append("self-test: a missing .github folder gave no finding")
        github = root / ".github"
        workflows = github / "workflows"
        workflows.mkdir(parents=True)
        empty, _ = scan_tree(root, 1, ())
        if not any("no YAML file" in f for f in empty) or not any("below the floor" in f for f in empty):
            errors.append("self-test: an empty .github did not report both no YAML and the floor")
        case = workflows / "case.yml"
        head = "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python3 -I tools/a.py\n"

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

        whole = [
            ("parse error", "on: [push\n", "cannot be parsed"),
            ("duplicate key", head + "jobs: {}\n", "cannot be parsed"),
            ("no jobs", "on: push\n", "no jobs"),
            ("U+2028", head + "      - run: true \u2028\n", "U+2028"),
            ("U+0085", head + "      - run: true \x85\n", "U+0085"),
            ("U+2029", head + "      - run: true \u2029\n", "U+2029"),
            ("steps not a list", "on: push\njobs:\n  j:\n    steps: 1\n", "not a list"),
            ("step not a mapping", head + "      - 1\n", "not a mapping"),
            ("job not a mapping", "on: push\njobs:\n  j: 1\n", "not a mapping"),
            ("job uses unpinned", "on: push\njobs:\n  j:\n    uses: o/r/.github/workflows/w.yml@main\n", "pinned"),
            ("defaults shell python", "on: push\ndefaults:\n  run:\n    shell: python\n" + head[9:], "shell"),
        ]
        for name, text, needle in whole:
            case.write_text(text, encoding="utf-8")
            if not any(needle in f for f in scan()):
                errors.append(f"self-test: whole file {name} gave no finding naming {needle!r}")
        case.write_text(head, encoding="utf-8")
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

        actions = github / "actions"
        good = actions / "ok"
        good.mkdir(parents=True)
        (good / "action.yml").write_text(
            "name: ok\nruns:\n  using: composite\n  steps:\n    - shell: bash\n      run: python3 -I tools/a.py\n",
            encoding="utf-8",
        )
        case.write_text(head + "      - uses: ./.github/actions/ok\n", encoding="utf-8")
        if scan():
            errors.append(f"self-test: a correct composite action gave {scan()!r}")
        (good / "action.yml").write_text(
            "name: ok\nruns:\n  using: composite\n  steps:\n    - shell: bash\n      run: python3 tools/a.py\n",
            encoding="utf-8",
        )
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
        shutil.rmtree(actions)

        sub = workflows / "sub"
        sub.mkdir()
        (sub / "action.yml").write_text(
            "runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: python3 tools/a.py\n",
            encoding="utf-8",
        )
        if not any("sub/action.yml" in f for f in scan()):
            errors.append("self-test: an action in a subfolder was not scanned")
        sub.chmod(0)
        try:
            if not any("cannot list" in f for f in scan()):
                errors.append("self-test: an unreadable subfolder gave no finding")
        finally:
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
            for name in ("linked", "link.yml"):
                if not any(f".github/{name}" in f or f"workflows/{name}" in f for f in findings):
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
        (tools / "sibling.py").write_text(
            "import sys\nsys.path.insert(0, '.')\n", encoding="utf-8"
        )
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
