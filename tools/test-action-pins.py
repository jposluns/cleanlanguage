#!/usr/bin/env python3
"""Check that every `uses` in the workflows is pinned to a full commit.

Threat model: honest drift. A `uses` that names a tag or a branch runs
whatever that name points at when the job starts, so a moved tag changes what
the workflow runs without any change in this repository. The gate guards
against an honest author who writes such a reference by mistake; deliberate
evasion is a named residual.

The rule: each .github/workflows/*.yml file is loaded with UniqueKeyLoader,
taken from tools/test-workflow-launch-isolation.py as described below, and
every value of a key `uses`, in a mapping or in a key and value pair of an
`!!omap` or `!!pairs` list, at any depth of mappings, lists and pairs, so a
step `uses`, a job `uses` and one that an alias or a merge key brings in, must
be text of the form `owner/repo[/path]@<sha>`, where `<sha>` is exactly 40
lower-case hex digits. A mapping, list or pair that aliases bring in more than
once is checked once. The owner starts with an ASCII letter or digit and holds
only ASCII letters, digits and hyphens; the repo and each path part are not
empty, hold only ASCII letters, digits, `_`, `.` and `-`, and are not `.` or
`..`. Anything else is a finding: a tag or a branch, a short, long or
upper-case hex ref, a local `./` or `../` path, any `docker://` value, an
expression such as `${{ matrix.action }}`, an owner that holds `_` or `.`, an
empty repo or path part, such as `owner/@<sha>`, and a `uses` that is not
text. A workflow that cannot be read as UTF-8, one whose loading raises an
Exception of any type, such as the error on a duplicate key, the ValueError on
`!!int abc` or the RecursionError on mappings nested as deep as the recursion
limit, or a SystemExit, and a recursive node are findings, and an empty
.github/workflows/*.yml listing is a failure. A finding's path writes each
mapping key as key_text does, by no call that raises, so an integer key of
more than 4300 digits, whose decimal text raises ValueError under the default
limit, is written as its bit length. tools/test-workflow-launch-isolation.py
separately refuses local actions and local reusable workflows, and any .yml or
.yaml file under .github outside .github/workflows/*.yml, such as an
action.yml.

The gate takes UniqueKeyLoader from the launch scan without importing the
scan. It calls `os.lstat` on tools/test-workflow-launch-isolation.py and
refuses a path that is not a regular file, such as a symbolic link or a
folder; reads the source bytes; compiles them with `dont_inherit=True`; and
runs them in a fresh module namespace whose `__file__` is that path, so no
cached bytecode file in tools/__pycache__ stands in for the source. It leaves
sys.path unchanged and adds no entry for the scan to sys.modules. An lstat or
read error, a compile error, an Exception or a SystemExit raised while the
scan's module body runs, and a scan that defines no UniqueKeyLoader each stop
the gate before its self-tests, with 1 FAIL line that names the exception's
type and message, and exit status 1. Any other BaseException, such as
KeyboardInterrupt or GeneratorExit, raised while the scan's module body runs
or while UniqueKeyLoader loads a workflow, is not caught: it stops the gate
with a traceback and no FAIL line, so an interrupt stays an interrupt.

Residuals:

- deliberate evasion of any kind, including an edit to this gate;
- files outside .github/workflows/*.yml, which the launch scan refuses;
- a 40-hex commit that is the commit of a tag, or a commit in a fork, is
  accepted; the gate does not check that the commit exists or which repository
  holds it;
- GitHub Actions' own YAML reading is not checked, so a key that GitHub
  Actions reads as `uses` but PyYAML builds as other text passes;
- an owner, repo or path name that fits the form above but that GitHub may not
  accept, such as an owner with a trailing hyphen or 2 hyphens in a row, a
  long owner or repo name, or a repo named `...` or `.git`; the gate does not
  check GitHub's naming rules;
- what a pinned action does, including the actions and images it fetches in
  turn.

Usage: python3 -I tools/test-action-pins.py
Exit status: 0 when every check passes, 1 on any finding or failure, except
for the BaseException described above, which ends the gate with a traceback.
"""

from __future__ import annotations

import os
import py_compile
import re
import stat
import string
import sys
import tempfile
import types
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
SCAN = Path(__file__).resolve().parent / "test-workflow-launch-isolation.py"

SEGMENT = r"(?!\.\.?(?:/|@))[A-Za-z0-9_.-]+"
PIN = re.compile(rf"[A-Za-z0-9][A-Za-z0-9-]*/{SEGMENT}(?:/{SEGMENT})*@[0-9a-f]{{40}}")


def load_scan(path: Path = SCAN) -> tuple[type | None, str]:
    """Return (UniqueKeyLoader, "") from the scan at path, or (None, why).

    A path that `os.lstat` does not report as a regular file, such as a
    symbolic link or a folder, is refused. Otherwise the source bytes are
    read, compiled with `dont_inherit=True`, so the future imports of this
    gate do not apply to the scan, and run in a fresh module namespace whose
    `__file__` is path, so no cached bytecode stands in for the source.
    sys.path is not changed and no entry for the scan is added to sys.modules;
    the modules that the scan imports are added there as any import adds them.
    An Exception or a SystemExit raised by those steps, and a module that
    defines no UniqueKeyLoader, give (None, why), where why is the first line
    of the exception's type, a colon, a space and its message, or the type's
    name alone when building that text raises, as describe gives it. Any other
    BaseException, such as KeyboardInterrupt, is not caught.
    """
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            raise ImportError("not a regular file")
        source = path.read_bytes()
        module = types.ModuleType("workflow_launch_isolation")
        module.__file__ = str(path)
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
        if not hasattr(module, "UniqueKeyLoader"):
            raise ImportError("defines no UniqueKeyLoader")
    except (Exception, SystemExit) as exc:
        return None, describe(exc)
    return module.UniqueKeyLoader, ""


def check_uses(value) -> str | None:
    """Describe why one `uses` value is refused, or return None.

    A value that is not text is named by its type, not by its repr, since a
    repr can raise, such as the ValueError on an integer of more than 4300
    digits or the RecursionError on a mapping that an alias chain nests 60000
    deep.
    """
    if not isinstance(value, str):
        return f"a value of type {type(value).__name__} is not text"
    if not PIN.fullmatch(value):
        return f"{value!r} is not owner/repo[/path]@<40 lower-case hex>"
    return None


def key_text(key) -> str:
    """Return a mapping key as text for a finding's path, without raising.

    Text is returned as it is. An integer is written as its decimal digits,
    unless `sys.get_int_max_str_digits()` is not 0 and its bit length is more
    than 3 times that limit, since its decimal text could then exceed the
    limit and raise ValueError; it is then written as its bit length, such as
    `<int of 14768 bits>`. A limit of 0 sets no limit, so the digits are
    written. Any other key is written as its type's name, such as `<bool>`.
    """
    if type(key) is str:
        return key
    if type(key) is int:
        limit = sys.get_int_max_str_digits()
        if limit and key.bit_length() > 3 * limit:
            return f"<int of {key.bit_length()} bits>"
        return str(key)
    return f"<{type(key).__name__}>"


def walk(doc, found: list[str], checked: list[str]) -> None:
    """Check every `uses` key in doc, at any depth; record each in checked.

    A `uses` key is a mapping key or the first item of a 2-item tuple, the
    form in which PyYAML builds each key and value pair of an `!!omap` or
    `!!pairs` list. The walk keeps its own stack instead of recursing, so an
    alias chain deeper than the interpreter's recursion limit does not stop
    it. A mapping, list or tuple met again inside itself is a recursive node,
    a finding; one already walked, which an alias brings in again, is not
    walked again.
    """
    stack: list[tuple[object, str, bool]] = [(doc, "", False)]
    open_ids: set[int] = set()
    done: set[int] = set()
    while stack:
        node, where, leaving = stack.pop()
        if leaving:
            open_ids.discard(id(node))
            done.add(id(node))
            continue
        if not isinstance(node, (dict, list, tuple)):
            continue
        if id(node) in open_ids:
            found.append(f"{where}: a recursive node")
            continue
        if id(node) in done:
            continue
        open_ids.add(id(node))
        stack.append((node, where, True))
        if isinstance(node, dict):
            pairs = list(node.items())
            children = [(value, f"{where}.{key_text(key)}") for key, value in pairs]
        else:
            pairs = [tuple(node)] if isinstance(node, tuple) and len(node) == 2 else []
            children = [(item, f"{where}[{n}]") for n, item in enumerate(node)]
        for key, value in pairs:
            if type(key) is str and key == "uses":
                checked.append(where)
                reason = check_uses(value)
                if reason:
                    found.append(f"{where}.uses: {reason}")
        stack.extend((child, label, False) for child, label in reversed(children))


def describe(exc: BaseException) -> str:
    """Return the first line of "<type name>: <text>" for exc.

    The text is `str(exc)`, which can raise, such as on an instance made
    without calling `__init__` or one whose class's `__str__` raises; when
    building the line raises an Exception, the type's name alone is returned.
    """
    name = type(exc).__name__
    try:
        return f"{name}: {exc}".splitlines()[0]
    except Exception:
        return name


def check_text(text: str, label: str, loader) -> tuple[list[str], int]:
    """Return the findings for one workflow's text, and its number of uses.

    An Exception or a SystemExit raised while loader loads text is a finding
    that the text cannot be parsed, which names it as describe does.
    """
    try:
        doc = yaml.load(text, Loader=loader)
    except (Exception, SystemExit) as exc:
        return [f"{label}: cannot be parsed as YAML ({describe(exc)})"], 0
    found: list[str] = []
    checked: list[str] = []
    walk(doc, found, checked)
    return [f"{label}: {reason.lstrip('.')}" for reason in found], len(checked)


def scan_tree(root: Path, loader) -> tuple[list[str], int]:
    """Check every root/.github/workflows/*.yml; return (findings, number of uses)."""
    files = sorted((root / ".github" / "workflows").glob("*.yml"))
    if not files:
        return [f"no workflow found in {root / '.github' / 'workflows'}"], 0
    findings: list[str] = []
    count = 0
    for path in files:
        label = str(path.relative_to(root))
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{label}: cannot be read as UTF-8 ({exc})")
            continue
        found, uses = check_text(text, label, loader)
        findings += found
        count += uses
    return findings, count


# ---------------------------------------------------------------- self-tests

SHA = "11d5960a326750d5838078e36cf38b85af677262"


def step(uses: str) -> str:
    return f"jobs:\n  a:\n    steps:\n      - uses: {uses}\n"


def chain(uses: str) -> str:
    """Return a workflow whose aliases nest twice as deep as the recursion limit."""
    lines = [f"a0: &a0 {{uses: {uses}}}"]
    lines += [f"a{n}: &a{n} {{k: *a{n - 1}}}" for n in range(1, 2 * sys.getrecursionlimit())]
    return "\n".join(lines) + "\n"


# Workflow text that must be refused (True) or must pass (False).
CASES = [
    (step("actions/checkout@v4"), True),
    (step("actions/checkout@main"), True),
    (step("docker://alpine"), True),
    (step("docker://alpine@sha256:" + "0" * 64), True),
    (step(f"docker://alpine@{SHA}"), True),
    (step("actions/checkout@" + SHA[:39]), True),
    (step("actions/checkout@" + SHA + "0"), True),
    (step("actions/checkout@" + SHA.upper()), True),
    (step("./local"), True),
    (step(f"./local@{SHA}"), True),
    (step(f"../x/y@{SHA}"), True),
    (step(f"owner/../w.yml@{SHA}"), True),
    (step(f"owner/repo/./w.yml@{SHA}"), True),
    (step(f"actions@{SHA}"), True),
    (step(f"-owner/repo@{SHA}"), True),
    (step(f"'actions/checkout@{SHA} '"), True),
    (step(f'"actions/checkout@{SHA}\\n"'), True),
    (step("'${{ matrix.action }}'"), True),
    (step("5"), True),
    (step("[a]"), True),
    (step("~"), True),
    ("jobs:\n  a:\n    uses: owner/repo/.github/workflows/w.yml@v1\n", True),
    ("jobs:\n  a:\n    uses: ./.github/workflows/w.yml\n", True),
    ("jobs:\n  a:\n    strategy:\n      matrix:\n        include:\n          - uses: actions/checkout@v4\n", True),
    ("jobs:\n  a:\n    env: {V: &u actions/checkout@v4}\n    steps:\n      - uses: *u\n", True),
    ("x: &s {name: n}\njobs:\n  a:\n    steps:\n      - <<: [*s, {uses: actions/checkout@v4}]\n", True),
    ("jobs:\n  a:\n    steps: &x\n      - *x\n", True),
    (f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA}\n        uses: actions/checkout@{SHA}\n", True),
    (step(f"owner/..@{SHA}"), True),
    (step(f"owner/repo/.@{SHA}"), True),
    (step(f"owner/r\u00e9po@{SHA}"), True),
    (step(f"owner/re+po@{SHA}"), True),
    (step(f"_owner/repo@{SHA}"), True),
    (step(f"own_er/repo@{SHA}"), True),
    (step(f"own.er/repo@{SHA}"), True),
    (step(f"ow\u00f1er/repo@{SHA}"), True),
    (step(f"\u00f1wner/repo@{SHA}"), True),
    (step("owner/repo@" + "g" * 40), True),
    (step(f"owner/@{SHA}"), True),
    (step(f"owner/repo/@{SHA}"), True),
    (step(f"owner/repo//x@{SHA}"), True),
    ("jobs:\n  a:\n    steps:\n      - !!omap [{uses: actions/checkout@v4}]\n", True),
    ("jobs:\n  a:\n    steps:\n      - !!pairs [{uses: actions/checkout@v4}]\n", True),
    ("jobs:\n  a: !!omap [{steps: [{uses: actions/checkout@v4}]}]\n", True),
    ("jobs:\n  a: !!pairs [{uses: owner/repo/.github/workflows/w.yml@v1}]\n", True),
    ("jobs:\n  a: &x !!pairs [{k: *x}]\n", True),
    (chain("actions/checkout@v4"), True),
    (step(f"actions/checkout@{SHA}"), False),
    (f"jobs:\n  a:\n    steps:\n      - !!omap [{{uses: actions/checkout@{SHA}}}]\n", False),
    (f"jobs:\n  a:\n    steps:\n      - !!pairs [{{uses: actions/checkout@{SHA}}}]\n", False),
    (f"jobs:\n  a: !!omap [{{steps: [{{uses: actions/checkout@{SHA}}}]}}]\n", False),
    (f"jobs:\n  a: !!pairs [{{uses: owner/repo/.github/workflows/w.yml@{SHA}}}]\n", False),
    (chain(f"actions/checkout@{SHA}"), False),
    (step(f"actions/checkout@{SHA} # v4.4.0"), False),
    (f"jobs:\n  a:\n    uses: owner/repo/.github/workflows/w.yml@{SHA}\n", False),
    (f"jobs:\n  a:\n    uses: octo-org/.github/.github/workflows/w.yml@{SHA}\n", False),
    (f"jobs:\n  a:\n    steps:\n      - uses: owner/repo.js/sub_dir/x-y@{SHA}\n", False),
    ("jobs:\n  a:\n    steps:\n      - run: echo uses actions/checkout@v4\n", False),
    ("jobs:\n  a:\n    steps:\n      - [uses, actions/checkout@v4]\n", False),
]


def self_test(loader) -> list[str]:
    errors: list[str] = []
    for text, refused in CASES:
        try:
            found, _ = check_text(text, "case.yml", loader)
        except Exception as exc:
            errors.append(f"self-test: {text[:200]!r} let {type(exc).__name__} escape check_text")
            continue
        if bool(found) != refused:
            errors.append(f"self-test: {text[:200]!r} gave {found or 'no finding'}, expected {'a finding' if refused else 'none'}")
    # PIN must give the verdict of the rule in the docstring, as allowed
    # applies that rule from its text rather than from PIN, for every ASCII
    # character and some others, such as non-ASCII digits and letters, as the
    # owner's first or a later character, inside or as the whole of the repo
    # and a path part, and as a character of the ref. A `/` or an `@` that
    # splits a name is judged as the rule judges the whole value.
    alnum = string.ascii_letters + string.digits

    def allowed(value: str) -> bool:
        names, at, ref = value.partition("@")
        owner, *parts = names.split("/")
        return (
            at == "@"
            and len(ref) == 40
            and all(char in "0123456789abcdef" for char in ref)
            and owner[:1] != ""
            and owner[0] in alnum
            and all(char in alnum + "-" for char in owner)
            and parts != []
            and all(part not in ("", ".", "..") and all(char in alnum + "_.-" for char in part) for part in parts)
        )

    chars = [chr(n) for n in range(128)]
    chars += ["\u00a0", "\u00e9", "\u0130", "\u0131", "\u0663", "\u017f", "\u2028", "\u212a", "\uff10", "\uff21"]
    forms = ["{}wner/repo@", "o{}ner/repo@", "owner/r{}po@", "owner/{}@", "owner/repo/p{}th@", "owner/repo/{}@"]
    values = [form.format(char) + SHA for form in forms for char in chars]
    values += [f"owner/repo@{char}{SHA[1:]}" for char in chars]
    for value in values:
        if (check_uses(value) is None) != allowed(value):
            errors.append(f"self-test: {value!r} gave {check_uses(value) or 'no finding'}, but the rule {'allows' if allowed(value) else 'refuses'} it")
    for text in (step("actions/checkout@v4"), "jobs:\n  a:\n    steps:\n      - !!pairs [{uses: actions/checkout@v4}]\n"):
        _, count = check_text(text, "case.yml", loader)
        if count != 1:
            errors.append(f"self-test: {text!r} gave {count} uses, expected 1")
    found, count = check_text(f"a: &s {{uses: actions/checkout@{SHA}}}\nb: *s\nc: *s\n", "case.yml", loader)
    if found or count != 1:
        errors.append(f"self-test: a mapping that aliases bring in 3 times gave {found}, {count} uses, expected 1")

    class Exits(loader):
        pass

    def exits(_loader, _node, deep=False):
        raise SystemExit(0)

    Exits.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, exits)
    try:
        found, _ = check_text(step(f"actions/checkout@{SHA}"), "case.yml", Exits)
    except (Exception, SystemExit) as exc:
        found = [f"{type(exc).__name__} escaped check_text"]
    if found != ["case.yml: cannot be parsed as YAML (SystemExit: 0)"]:
        errors.append(f"self-test: a loader whose mapping constructor raises SystemExit(0) gave {found}")
    depth = sys.getrecursionlimit()
    try:
        found, _ = check_text("a: " + "{a: " * depth + "1" + "}" * depth + "\n", "case.yml", loader)
    except Exception as exc:
        found = [f"{type(exc).__name__} escaped check_text"]
    if len(found) != 1 or not found[0].startswith("case.yml: cannot be parsed as YAML (RecursionError: "):
        errors.append(f"self-test: mappings nested {depth} deep gave {found}")

    # A stand-in loader whose mapping constructor raises an instance of every
    # Exception subclass present when this self-test runs, found by walking
    # `type.__subclasses__` from Exception, must give 1 finding that names the
    # instance's type. Each instance is made by calling its class with no
    # arguments or, when that raises or gives another type, without calling
    # `__init__`; a subclass of BaseExceptionGroup needs a message and a list
    # of exceptions, so it is also called with them. A class that no route
    # makes is a self-test failure. Unlisted, whose finding is checked in
    # full, and Unprintable, whose `__str__` raises, are also raised on their
    # own.
    class Unlisted(Exception):
        pass

    class Unprintable(Exception):
        def __str__(self):
            raise ValueError("no text")

    raised: list[BaseException] = []

    class Raises(loader):
        pass

    def raises(_loader, _node, deep=False):
        raise raised[0]

    Raises.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, raises)
    for exc, want in (
        (Unlisted("defined in the self-test"), "Unlisted: defined in the self-test"),
        (Unprintable(), "Unprintable"),
    ):
        raised[:] = [exc]
        try:
            found, _ = check_text(step(f"actions/checkout@{SHA}"), "case.yml", Raises)
        except Exception as escaped:
            found = [f"{type(escaped).__name__} escaped check_text"]
        if found != [f"case.yml: cannot be parsed as YAML ({want})"]:
            errors.append(f"self-test: a loader whose mapping constructor raises {want.split(':')[0]} gave {found}")
    classes: dict[int, type] = {}
    todo: list[type] = [Exception]
    while todo:
        cls = todo.pop()
        if id(cls) not in classes:
            classes[id(cls)] = cls
            todo.extend(type.__subclasses__(cls))
    for cls in classes.values():
        routes = [cls, lambda: cls.__new__(cls), lambda: BaseException.__new__(cls)]
        if issubclass(cls, BaseExceptionGroup):
            routes.append(lambda: cls("self-test", [Exception()]))
        made = []
        for route in routes:
            try:
                made = [route()]
            except Exception as exc:
                why = describe(exc)
                continue
            if type(made[0]) is cls:
                break
            why = f"made a {type(made[0]).__name__}"
            made = []
        if not made:
            errors.append(f"self-test: cannot make an instance of {cls.__module__}.{cls.__qualname__} ({why})")
            continue
        raised[:] = made
        try:
            found, _ = check_text(step(f"actions/checkout@{SHA}"), "case.yml", Raises)
        except Exception as exc:
            found = [f"{type(exc).__name__} escaped check_text"]
        head = f"case.yml: cannot be parsed as YAML ({cls.__name__}"
        if len(found) != 1 or not (found[0] == head + ")" or found[0].startswith(head + ": ")):
            errors.append(f"self-test: {cls.__module__}.{cls.__qualname__} raised while loading gave {found}")
    # With Python 3.14.4 and PyYAML 6.0.3, loading each input below through
    # the real loader raised the type beside it; each must give a finding that
    # names that type. The walk above raises each Exception subclass present
    # when the self-test runs from a stand-in loader; these rows check real
    # inputs.
    for text, kind in (
        ("a: !!int abc\n", "ValueError"),
        ("a: !!bool maybe\n", "KeyError"),
        ("a: !!timestamp nope\n", "AttributeError"),
        ("a: 1" + ":00" * 200 + ".5\n", "OverflowError"),
        ("a: !!int ''\n", "IndexError"),
        ("a: !!map [a]\n", "TypeError"),
        ("a: !!binary YQ\n", "ConstructorError"),
        ("a: *x\n", "ComposerError"),
        ("a: [1\n", "ParserError"),
        ('a: "\\q"\n', "ScannerError"),
        ("a: \x07\n", "ReaderError"),
    ):
        try:
            found, _ = check_text(text, "case.yml", loader)
        except Exception as exc:
            found = [f"{type(exc).__name__} escaped check_text"]
        if len(found) != 1 or not found[0].startswith(f"case.yml: cannot be parsed as YAML ({kind}: "):
            errors.append(f"self-test: {text[:80]!r} gave {found}, expected a finding that names {kind}")
    # The text of an integer of more than 4300 digits raises ValueError under
    # the default limit. A `uses` value that is one, 60 ** 2500, must be a
    # finding that names its type; a key that is one must be written in a path
    # as its bit length, or as its digits when the limit is 0; and a key that
    # is one with no `uses` under it must give no finding.
    big = "1" + ":0" * 2500
    key = str(60**2500) if sys.get_int_max_str_digits() == 0 else "<int of 14768 bits>"
    for text, want in (
        (step(big), ["case.yml: jobs.a.steps[0].uses: a value of type int is not text"]),
        (f"? {big}\n: {{uses: actions/checkout@v4}}\n", [f"case.yml: {key}.uses: {check_uses('actions/checkout@v4')}"]),
        (f"? {big}\n: 1\n", []),
    ):
        try:
            found, _ = check_text(text, "case.yml", loader)
        except Exception as exc:
            found = [f"{type(exc).__name__} escaped check_text"]
        if found != want:
            errors.append(f"self-test: an integer of more than 4300 digits gave {[f[:200] for f in found]}, expected {[w[:200] for w in want]}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        findings, _ = scan_tree(root, loader)
        if not any("no workflow found" in f for f in findings):
            errors.append("self-test: an empty .github/workflows/*.yml listing gave no failure")
        (workflows / "ok.yml").write_text(step(f"actions/checkout@{SHA}"), encoding="utf-8")
        findings, count = scan_tree(root, loader)
        if findings or count != 1:
            errors.append(f"self-test: a clean tree gave {findings}, {count} uses")
        (workflows / "bad.yml").write_bytes(b"jobs: {a: {steps: [{uses: '\xff'}]}}\n")
        findings, _ = scan_tree(root, loader)
        if not any(".github/workflows/bad.yml: cannot be read" in f for f in findings):
            errors.append("self-test: a workflow that is not UTF-8 gave no finding")
    errors += load_self_test()
    return errors


def try_load(path: Path) -> tuple[type | None, str]:
    """Call load_scan(path); an Exception or a SystemExit that escapes it becomes why."""
    try:
        return load_scan(path)
    except (Exception, SystemExit) as exc:
        return None, f"escaped load_scan: {type(exc).__name__}: {exc}"


def load_self_test() -> list[str]:
    errors: list[str] = []
    try:
        source = SCAN.read_bytes()
    except OSError as exc:
        return [f"self-test: cannot read {SCAN} ({exc})"]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        good = folder / "good.py"
        good.write_bytes(source)
        loader, why = try_load(good)
        if getattr(loader, "__name__", None) != "UniqueKeyLoader":
            errors.append(f"self-test: a copy of the launch scan did not load ({why})")
        if "workflow_launch_isolation" in sys.modules:
            errors.append("self-test: loading the launch scan added it to sys.modules")
        cases = [
            ("exits.py", source + b"\nraise SystemExit(0)\n", "SystemExit: 0"),
            ("unprintable.py", source + b"\nclass Unprintable(Exception):\n    def __str__(self):\n        raise ValueError('no text')\n\n\nraise Unprintable()\n", "Unprintable"),
            ("none.py", b"X = 1\n", "ImportError: defines no UniqueKeyLoader"),
            ("broken.py", b"def broken(:\n", "SyntaxError: "),
            ("absent.py", None, "FileNotFoundError: "),
            # Compiled with this gate's `from __future__ import annotations`,
            # the annotation would be kept as text and raise no NameError.
            ("future.py", b"def f(x: missing): pass\nf.__annotations__\n", "NameError: "),
        ]
        for name, text, want in cases:
            if text is not None:
                (folder / name).write_bytes(text)
            loader, why = try_load(folder / name)
            if loader is not None or not why.startswith(want):
                errors.append(f"self-test: loading {name} gave {why or 'UniqueKeyLoader'}, expected {want}")
        cached = folder / "cached.py"
        cached.write_bytes(source)
        try:
            pyc = py_compile.compile(
                str(cached), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
            )
        except (OSError, py_compile.PyCompileError) as exc:
            errors.append(f"self-test: could not write a cached .pyc ({exc})")
        else:
            cached.write_bytes(b"raise RuntimeError('the source ran')\n")
            loader, why = try_load(cached)
            if not Path(pyc).is_file() or why != "RuntimeError: the source ran":
                errors.append(f"self-test: a cached .pyc beside a broken source gave {why or 'UniqueKeyLoader'}")
        (folder / "dir.py").mkdir()
        others = ["dir.py"]
        try:
            (folder / "link.py").symlink_to(good)
            others.append("link.py")
        except OSError as exc:
            errors.append(f"self-test: could not make a symbolic link ({exc})")
        for name in others:
            loader, why = try_load(folder / name)
            if loader is not None or why != "ImportError: not a regular file":
                errors.append(f"self-test: loading {name} gave {why or 'UniqueKeyLoader'}, expected a refusal")
    return errors


def main() -> int:
    # A finding can hold text that the output's encoding cannot hold, such as
    # a lone surrogate in a workflow key; it is written as a backslash escape,
    # so the line is printed instead of raising UnicodeEncodeError.
    sys.stdout.reconfigure(errors="backslashreplace")
    loader, why = load_scan()
    if loader is None:
        print(f"FAIL: cannot load UniqueKeyLoader from {SCAN} ({why})")
        return 1
    errors = self_test(loader)
    if errors:
        for error in errors:
            print(error)
        print(f"FAIL: {len(errors)} self-test failure(s)")
        return 1
    findings, count = scan_tree(REPO, loader)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s)")
        return 1
    print(f"OK: {count} uses values in .github/workflows/*.yml, every uses pinned to owner/repo[/path]@<40 lower-case hex>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
