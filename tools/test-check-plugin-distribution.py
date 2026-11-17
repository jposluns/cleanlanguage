#!/usr/bin/env python3
"""Tests for tools/check-plugin-distribution.py.

The gate's docstring states its behaviour; this docstring does not list the
cases, whose names and comments say what each sets up.

Each case of PluginDistributionTest starts from a temporary tree that holds
the files the gate reads and a copy of the real tools/skill-version.py, with
the gate's REPO_ROOT pointed at it. expect runs the gate's main and requires
the exit status, each text given and the lines of that status (assert_lines).
test_gate_runs_as_a_command runs a copy of the gate as a command,
test_loading_a_gate_that_raises_stops_the_test and
test_loading_a_gate_that_prints_stops_the_test each run a copy of this test as
a command, and RepositoryTreeTest runs the gate on the repository itself. The
permission cases are skipped when the test runs as root, the case of a file
swapped for a FIFO where os.mkfifo or signal.SIGALRM is missing, and the case
of a source that reaches a folder named like the plugin's own but for letter
case where the file system folds letter case.

Loading the gate must write nothing to sys.stdout or sys.stderr and raise
nothing; a gate that does either while this test loads it stops the test with
exit 1 before any case runs. The exception's type name and message are shown
as the gate shows them: each made into a str of its own type with its output
dropped, and a stand-in for one whose making raises an exception of any class
or for a name that is not a str.

Usage: python3 -I tools/test-check-plugin-distribution.py
Exit status: 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import ast
import builtins
import collections
import contextlib
import errno
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parent / "check-plugin-distribution.py"
REAL_EXTRACTOR = Path(__file__).resolve().parent / "skill-version.py"
EXTRACTOR_REL = "tools/skill-version.py"
# Written out, not read from the gate.
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
# Written out, not read from the gate.
MAX_JSON_DEPTH = 64
# The tags of the 4 checks, written out, not read from the gate.
TAGS = ("D1", "D2", "D3", "D4")
# The stand-ins for a message and for a type name that cannot be made, written out.
UNSHOWN_MESSAGE = "(a message that cannot be shown)"
UNSHOWN_NAME = "(a name that cannot be shown)"
# Line breaks that str.splitlines honours, to put into paths and names.
BREAKS = ("\n", "\r", "\x0b", "\x85", "\u2028")
# A folder name that holds a line break and, after it, the start of a forged FAIL line; and how the
# gate shows it.
BROKEN = "h\nFAIL D9: k"
BROKEN_SHOWN = "h\\nFAIL D9: k"
# The arguments that make a copy of this test, once its gate has loaded, run 1 short case, so that a copy
# whose loader lets a gate load ends with that case's exit status, never with a run of the whole test.
LOADED_ONLY = ("-k", "test_conforming_tree_passes")


def _made(make, stand_in: str) -> str:
    """What make returns, as a str of its own type, with what make writes to sys.stdout and sys.stderr
    dropped; or stand_in when make raises an exception of any class or returns no str."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return str.__str__(make())
    except BaseException:
        return stand_in


spec = importlib.util.spec_from_file_location("check_plugin_distribution", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
_loaded = io.StringIO()
try:
    with contextlib.redirect_stdout(_loaded), contextlib.redirect_stderr(_loaded):
        spec.loader.exec_module(gate)
except BaseException as error:
    # A gate that raises while it loads would end this test before any case runs, with the gate's own
    # exit status; stop with exit 1 instead, whatever making the exception's name or message does.
    _name = _made(lambda: type(error).__name__, UNSHOWN_NAME)
    _message = _made(lambda: str(error), UNSHOWN_MESSAGE)
    raise SystemExit(f"loading {MODULE_PATH} raised {_name}: {_message}") from None
if _loaded.getvalue():
    # The gate's main prints at least 2 lines, so a gate that runs it while it loads prints.
    raise SystemExit(f"loading {MODULE_PATH} printed {_loaded.getvalue()!r}")

VERSION = "1.0.15"


class OwnBaseException(BaseException):
    """An exception class of this test's own, outside the Exception tree."""


class OwnException(Exception):
    """An exception class of this test's own."""


# Every exception class that builtins holds, and the 2 of this test's own, in order of name.
RAISED = sorted({value for value in vars(builtins).values()
                 if isinstance(value, type) and issubclass(value, BaseException)} | {OwnBaseException, OwnException},
                key=lambda cls: cls.__name__)


def built(cls) -> BaseException:
    """An instance of the exception class cls, whatever its constructor asks for."""
    if issubclass(cls, BaseExceptionGroup):
        return cls("no text", [ValueError() if issubclass(cls, Exception) else KeyboardInterrupt()])
    return cls.__new__(cls)


def loud(text: str):
    """A __str__ that prints a forged FAIL line to standard output and a forged last line to standard
    error, then returns text."""
    def __str__(self):
        print("FAIL D9: forged")
        print("UNREADABLE: exit 3", file=sys.stderr)
        return text
    return __str__


def raising(cls):
    """A __str__ that raises an instance of the exception class cls."""
    def __str__(self):
        raise built(cls)
    return __str__


class HookedText(str):
    """A str subclass whose own methods for format, str and iteration raise SystemExit(0)."""

    def __format__(self, spec):
        raise SystemExit(0)

    def __iter__(self):
        raise SystemExit(0)

    def __str__(self):
        raise SystemExit(0)


class Replaced:
    """A module with some of its attributes replaced: each name given reads its value here, and any
    other name is read from the module."""

    def __init__(self, module, **values):
        self.module, self.values = module, values

    def __getattr__(self, name):
        return self.values[name] if name in self.values else getattr(self.module, name)


def marketplace() -> dict:
    return {
        "name": "cleanlanguage",
        "owner": {"name": "Jeff Posluns", "url": "https://cleanlanguage.ai/"},
        "description": "d",
        "plugins": [{"name": "cleanlanguage", "source": "./cleanlanguage", "category": "productivity"}],
    }


def vendored() -> dict:
    return {
        "name": "aiqt-guardrails",
        "owner": {"name": "Jeff Posluns"},
        "plugins": [{"name": "aiqt-guardrails-hooks", "source": "./aiqt-guardrails-hooks"}],
    }


def manifest(name: str = "cleanlanguage", version: str = VERSION) -> dict:
    return {"name": name, "version": version, "description": "d"}


# The methods of dict that read a key, or every key, of the dict they are called on; KEYED_METHODS of
# them take the key as their first argument.
MAPPING_METHODS = frozenset({"get", "pop", "setdefault", "items", "keys", "values", "popitem", "copy",
                             "__getitem__", "__contains__", "__iter__", "__reversed__", "__or__", "__ror__"})
KEYED_METHODS = frozenset({"get", "pop", "setdefault", "__getitem__", "__contains__"})
# The functions of the operator module that read a key: getitem and contains of the object given first,
# itemgetter of the object the function it makes is called on.
OPERATOR_READS = frozenset({"getitem", "contains", "itemgetter"})
# The builtins and methods that iterate each positional argument, which reads every key of a dict; map
# and filter take a function first.
ITERATING = frozenset({"iter", "list", "tuple", "set", "frozenset", "sorted", "reversed", "dict", "enumerate", "zip",
                       "map", "filter", "min", "max", "sum", "any", "all", "join", "extend", "update", "union",
                       "intersection", "difference", "symmetric_difference", "issubset", "issuperset", "isdisjoint",
                       "fromkeys"})
# Calls whose result, iterated, is not recorded there: their own reads are recorded at the call.
NOT_ITERATED_CALLS = ITERATING | MAPPING_METHODS


def key_reads(source: str) -> list:
    """Each place the Python source may read a key of a dict, as (function, object, key): the top-level
    function or class that holds it ("<module>" for none), the object read as ast.unparse writes it, and
    the key as a str where it is written as a string constant or as a name that the module binds once, to
    a string constant; else None, as for a place that reads every key.

    The places: a subscript, an augmented assignment to one among them; an in or not in test, at each
    link of a chain; a method of MAPPING_METHODS called on the object, called through dict or type(...)
    with the object first, or taken as an attribute without a call; getattr of such a method, or of a
    name not written as a string constant; a function of OPERATOR_READS; each key of a mapping pattern of
    match, and its **rest; ** and * unpacking; and iteration: a for loop, a comprehension, yield from, an
    assignment that unpacks, and each positional argument of a call of ITERATING. A subscript by an int or
    a slice and an in test of a literal read no key. Where an object is iterated, a literal, a display, a
    comprehension, a lambda, an f-string and a call of NOT_ITERATED_CALLS are not recorded, and each
    branch of a conditional expression or of and or or is recorded on its own.

    Residual: code outside the source, given an object, is not scanned, such as str, repr or json.dumps
    given a dict; and the scan does not tell a dict from another object."""
    tree = ast.parse(source)
    owner, parent = {}, {}
    for top in tree.body:
        name = top.name if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "<module>"
        for node in ast.walk(top):
            owner[id(node)] = name
            for child in ast.iter_child_nodes(node):
                parent[id(child)] = node
    bound = collections.Counter(node.id for node in ast.walk(tree)
                                if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load))
    bound.update(node.arg for node in ast.walk(tree) if isinstance(node, ast.arg))
    constants = {target.id: top.value.value for top in tree.body if isinstance(top, ast.Assign)
                 and isinstance(top.value, ast.Constant) and isinstance(top.value.value, str)
                 for target in top.targets if isinstance(target, ast.Name) and bound[target.id] == 1}

    def text(node) -> str | None:
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        return constants.get(node.id) if isinstance(node, ast.Name) else None

    def literal(node) -> bool:
        try:
            ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return False
        return True

    def node_name(node) -> str | None:
        """The name a call, or the name or attribute it calls, is written with."""
        node = node.func if isinstance(node, ast.Call) else node
        return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None

    def objects(node) -> list:
        """The objects that iterating node may iterate."""
        if isinstance(node, ast.IfExp):
            return [*objects(node.body), *objects(node.orelse)]
        if isinstance(node, ast.BoolOp):
            return [found for value in node.values for found in objects(value)]
        if isinstance(node, ast.NamedExpr):
            return objects(node.value)
        if (literal(node) or isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.ListComp, ast.SetComp,
                                               ast.DictComp, ast.GeneratorExp, ast.Lambda, ast.JoinedStr))
                or isinstance(node, ast.Call)
                and node_name(node) in NOT_ITERATED_CALLS):
            return []
        return [node]

    reads = []

    def add(place, obj, key):
        reads.append((owner[id(place)], obj if isinstance(obj, str) else ast.unparse(obj), key))

    def iterated(place, node):
        for obj in objects(node):
            add(place, obj, None)

    def pattern(place, node, obj: str):
        if isinstance(node, ast.MatchMapping):
            for key, value in zip(node.keys, node.patterns):
                add(place, obj, text(key))
                pattern(place, value, f"{obj}[{ast.unparse(key)}]")
            if node.rest is not None:
                add(place, obj, None)
        elif isinstance(node, ast.MatchSequence):
            for index, value in enumerate(node.patterns):
                pattern(place, value, f"{obj}[{index}]")
        elif isinstance(node, ast.MatchClass):
            for value in node.patterns:
                pattern(place, value, obj)
            for attr, value in zip(node.kwd_attrs, node.kwd_patterns):
                pattern(place, value, f"{obj}.{attr}")
        elif isinstance(node, ast.MatchOr):
            for value in node.patterns:
                pattern(place, value, obj)
        elif isinstance(node, ast.MatchAs) and node.pattern is not None:
            pattern(place, node.pattern, obj)

    for node in ast.walk(tree):
        # Keys read by name.
        if isinstance(node, ast.Subscript) and (
                isinstance(node.ctx, ast.Load) or isinstance(parent.get(id(node)), ast.AugAssign)) and not (
                isinstance(node.slice, ast.Slice)) and not (literal(node.slice) and text(node.slice) is None):
            add(node, node.value, text(node.slice))
        elif isinstance(node, ast.Compare):
            left = node.left
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)) and not literal(right):
                    add(node, right, text(left))
                left = right
        elif isinstance(node, ast.Attribute) and node.attr in MAPPING_METHODS and isinstance(node.ctx, ast.Load):
            call = parent.get(id(node))
            if isinstance(call, ast.Call) and call.func is node:
                through_class = (isinstance(node.value, ast.Name) and node.value.id == "dict"
                                 or isinstance(node.value, ast.Call) and node_name(node.value) == "type")
                keyed = node.attr in KEYED_METHODS and len(call.args) > (1 if through_class else 0)
                key = text(call.args[1 if through_class else 0]) if keyed else None
                add(node, call.args[0] if through_class and call.args else node.value, key)
            else:
                add(node, node.value, None)
        elif isinstance(node, ast.Call) and node_name(node) == "getattr" and len(node.args) >= 2:
            name = node.args[1].value if isinstance(node.args[1], ast.Constant) else None
            if name is None or name in MAPPING_METHODS:
                add(node, node.args[0], None)
        elif isinstance(node, (ast.Name, ast.Attribute)) and node_name(node) in OPERATOR_READS:
            call = parent.get(id(node))
            if isinstance(call, ast.Call) and call.func is node and node_name(node) == "itemgetter":
                for key in call.args:
                    add(node, node, text(key))
            elif isinstance(call, ast.Call) and call.func is node and call.args:
                add(node, call.args[0], text(call.args[1]) if len(call.args) > 1 else None)
            else:
                add(node, node, None)
        elif isinstance(node, ast.Match):
            for case in node.cases:
                pattern(node, case.pattern, ast.unparse(node.subject))
        # Every key read: unpacking.
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if key is None:
                    iterated(node, value)
        elif isinstance(node, ast.keyword) and node.arg is None:
            iterated(node, node.value)
        elif isinstance(node, ast.Starred) and isinstance(node.ctx, ast.Load):
            iterated(node, node.value)
        # Every key read: iteration.
        if isinstance(node, (ast.For, ast.AsyncFor)):
            iterated(node, node.iter)
        elif isinstance(node, ast.comprehension):
            iterated(node, node.iter)
        elif isinstance(node, ast.YieldFrom):
            iterated(node, node.value)
        elif isinstance(node, ast.Assign) and any(
                isinstance(target, (ast.Tuple, ast.List)) for target in node.targets):
            iterated(node, node.value)
        elif isinstance(node, ast.Call) and node_name(node) in ITERATING:
            first = 1 if node_name(node) in ("map", "filter") else 0
            for value in node.args[first:]:
                if not isinstance(value, ast.Starred):
                    iterated(node, value)
    return reads


# The places key_reads finds in the gate that read no key of a JSON object, each as often as the gate
# reads it there: the pairs the decoder gives and the object _unique_object builds from them; a str, a
# list of str, a list of lines, a tuple of patterns, the extractor's namespace, the folder list of
# os.listdir, a str split in 3; the dict of the 2 marketplaces by path; the gate's own lists, sets and
# dicts of labels, values, names and folders, and the (index, entry) pairs of plugin_entries; and a JSON
# array of plugins or of dependencies that the gate iterates only once it is a list.
NOT_JSON_READS = (
    ("_unique_object", "pairs", None), ("_unique_object", "result", None),
    ("one_line", "text", None),
    ("walk", "parts", None), ("walk", "os.listdir(parent)", None),
    ("read_bytes", "blocks", None),
    ("exceeds_depth", "text", None),
    ("extractor_patterns", "namespace", None), ("extractor_patterns", "patterns", None),
    ("skill_version", "extractor_patterns()", None),
    ("plugin_entries", "plugins", None),
    ("check_names", "markets", ".claude-plugin/marketplace.json"), ("check_names", "markets", None),
    ("check_names", "pairs", None), ("check_names", "held", None), ("check_names", "listed", None),
    ("check_names", "listed", None), ("check_names", "names", None), ("check_names", "repeats", None),
    ("resolve_source", "parts", None), ("resolve_source", "parts", None), ("resolve_source", "parts", None),
    ("resolve_source", "base", None), ("resolve_source", "base", None), ("resolve_source", "steps", None),
    ("resolve_source", "os.listdir(parent)", None),
    ("check_sources", "markets", None), ("check_sources", "plugin_entries(rel, data, failures, 'D2')", None),
    ("check_reach", "folders", None),
    ("check_versions", "markets", ".claude-plugin/marketplace.json"), ("check_versions", "held", None),
    ("check_versions", "found", None), ("check_versions", "found", None), ("check_versions", "found", None),
    ("check_dependencies", "markets", None), ("check_dependencies", "entries", None),
    ("check_dependencies", "entries", None), ("check_dependencies", "folders", None),
    ("check_dependencies", "folders", None), ("check_dependencies", "lists", None),
    ("check_dependencies", "deps", None), ("check_dependencies", "dep.partition('@')", None),
    ("check_dependencies", "names", None), ("check_dependencies", "seen", None),
    ("run", "failures", None), ("run", "CHECKS", None), ("run", "CHECKS", None),
)


class FoldingOs:
    """The os module as the gate meets it on a file system that folds letter case, as macOS does by
    default: os.lstat, os.open and os.listdir find a path whose names are missing as spelled under
    another letter case, while os.listdir lists each name as its folder holds it."""

    def __init__(self, root: Path):
        self.root = root

    def __getattr__(self, name):
        return getattr(os, name)

    def fold(self, path) -> Path:
        path = Path(path)
        if os.path.lexists(path):
            return path
        current = self.root
        for part in path.relative_to(self.root).parts:
            held = os.listdir(current) if os.path.isdir(current) else []
            current = current / next((name for name in held if name.lower() == part.lower()), part)
        return current

    def lstat(self, path):
        return os.lstat(self.fold(path))

    def open(self, path, flags, mode=0o777):
        return os.open(self.fold(path), flags, mode)

    def listdir(self, path):
        return os.listdir(self.fold(path))


class FaultyOs:
    """The os module with 1 function that raises an OSError on each path that holds marker (on every
    call when marker is None): the one that error makes when it is given; else with the errno and
    strerror given, as a device fault gives one, or with no strerror, as an OSError built by hand has,
    and the errno given."""

    def __init__(self, name: str, marker: str | None, number: int | None = None, strerror: str | None = None,
                 error=None):
        self.name, self.marker, self.number, self.strerror, self.error = name, marker, number, strerror, error

    def __getattr__(self, name):
        real = getattr(os, name)
        if name != self.name:
            return real

        def faulty(*args, **kwargs):
            if self.marker is None or self.marker in str(args[0]):
                if self.error is not None:
                    raise self.error()
                if self.strerror is not None:
                    raise OSError(self.number, self.strerror)
                error = OSError("no text")
                error.errno = self.number
                raise error
            return real(*args, **kwargs)
        return faulty


class PluginDistributionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._saved = gate.REPO_ROOT
        gate.REPO_ROOT = self.root
        self.write_json(gate.MARKETPLACE, marketplace())
        self.write_json(gate.VENDORED_MARKETPLACE, vendored())
        self.write_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                        manifest("aiqt-guardrails-hooks", "0.4.0"))
        self.write_json(gate.CLAUDE_MANIFEST, {**manifest(), "skills": ["./skills/cleanlanguage"]})
        self.write_json(gate.AGENT_MANIFEST, manifest())
        self.write_json(gate.SITE_JSON, {"schema": 1, "site_key": "cleanlanguage"})
        self.write_text(gate.SKILL_MD, f"---\nname: cleanlanguage\n---\n\n# Clean Language\n\nVersion: {VERSION}  \n")
        (self.root / "tools").mkdir()
        shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)

    def tearDown(self):
        gate.REPO_ROOT = self._saved
        self._tmp.cleanup()

    def write_text(self, rel: str, text: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_json(self, rel: str, data: dict):
        self.write_text(rel, json.dumps(data, indent=2) + "\n")

    def edit_json(self, rel: str, change):
        data = json.loads((self.root / rel).read_text(encoding="utf-8"))
        change(data)
        self.write_json(rel, data)

    def run_gate(self):
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = gate.main()
        except BaseException as error:
            self.fail(f"the gate's main let {_made(lambda: type(error).__name__, UNSHOWN_NAME)} escape, a traceback "
                      f"in place of an exit status\n{out.getvalue()}{err.getvalue()}")
        return code, out.getvalue(), err.getvalue()

    def assert_lines(self, code: int, out: str, err: str):
        """The lines of each exit status, split as str.splitlines splits them, at every line break
        Python knows: for exit 1, 1 "FAIL <tag>: " line under a tag of TAGS that the gate's CHECKS
        holds, for each inconsistency the count line names, then the count line and that line; for exit 0, the count line and the
        "OK: " line; for exit 3, nothing on standard output and 2 lines on standard error."""
        lines, problems = out.splitlines(), err.splitlines()
        if code == 3:
            self.assertEqual(lines, [], out + err)
            self.assertEqual(len(problems), 2, out + err)
            self.assertTrue(problems[0].startswith("check-plugin-distribution: "), out + err)
            self.assertEqual(problems[1], "UNREADABLE: exit 3", out + err)
            return
        self.assertEqual(problems, [], out + err)
        self.assertGreaterEqual(len(lines), 2, out + err)
        self.assertRegex(lines[-2], r"^check-plugin-distribution: \d+ relative sources? resolved, \d+ "
                                    r"dependenc(y|ies) read$")
        if code == 0:
            self.assertEqual(len(lines), 2, out + err)
            self.assertTrue(lines[-1].startswith("OK: "), out + err)
            return
        failures = lines[:-2]
        self.assertTrue(failures, out + err)
        for line in failures:
            self.assertTrue(line.startswith(tuple(f"FAIL {tag}: " for tag in TAGS)), f"{line!r}\n{out}")
            self.assertIn(line[len("FAIL "):].split(":")[0], gate.CHECKS, f"{line!r}\n{out}")
        noun = "inconsistency" if len(failures) == 1 else "inconsistencies"
        self.assertEqual(lines[-1], f"FAIL: {len(failures)} {noun}", out + err)

    def expect(self, code: int, *needles: str, count: int | None = None):
        """Run the gate's main: the exit status, each needle, the last line and the lines of the status,
        and with count, a count line of exactly count inconsistencies."""
        got, out, err = self.run_gate()
        output = out + err
        self.assertEqual(got, code, output)
        for needle in needles:
            self.assertIn(needle, output)
        if count is not None:
            self.assertEqual(out.splitlines()[-1], f"FAIL: {count} inconsistenc{'y' if count == 1 else 'ies'}", output)
        stream, start = {0: (out, "OK: "), 1: (out, "FAIL: "), 3: (err, "UNREADABLE: exit 3")}[code]
        last = (stream.splitlines() or [""])[-1]
        self.assertTrue(last.startswith(start), f"last line {last!r} does not start {start!r}\n{output}")
        self.assert_lines(code, out, err)
        return output

    def add_vendored(self, name: str):
        """Add a plugin entry to the vendored marketplace, with a manifest of the same name."""
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"].append({"name": name, "source": f"./{name}"}))
        self.write_json(f"plugin/{name}/.claude-plugin/plugin.json", manifest(name, "0.4.0"))

    def edit_extractor(self, old: str, new: str):
        path = self.root / EXTRACTOR_REL
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_conforming_tree_passes(self):
        output = self.expect(0, "OK: D1 to D4 hold", "2 relative sources resolved", "0 dependencies read")
        self.assertNotIn("FAIL", output)

    def test_marketplace_named_jposluns_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d.update(name="jposluns"))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json name is 'jposluns', not 'cleanlanguage'")

    def test_entry_name_differs_from_manifest_name_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(name="clean-language"))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is 'clean-language'")

    def test_manifest_name_differs_fails_d1(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.update(name="clean-language"))
        self.expect(1, "FAIL D1: cleanlanguage/.claude-plugin/plugin.json name is 'clean-language'")

    def test_second_plugin_entry_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append(dict(d["plugins"][0])))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1")

    def test_reserved_prefix_fails_d1(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name="claude-guardrails"))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json name 'claude-guardrails' starts with a "
                       "reserved prefix")

    def test_missing_source_folder_fails_d2(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source="./absent"))
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './absent' does not "
                       "resolve: plugin/absent is missing")

    def test_source_with_dotdot_in_each_marketplace_fails_d2(self):
        for rel, folder in ((gate.MARKETPLACE, "cleanlanguage"), (gate.VENDORED_MARKETPLACE, "aiqt-guardrails-hooks")):
            source = f"./x/../{folder}"
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                try:
                    self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' has an empty, '.' or '..' "
                                   "component", "1 relative source resolved", count=1)
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_symlinked_source_fails_d2(self):
        os.symlink(self.root / "cleanlanguage", self.root / "linked")
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./linked"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './linked' does not resolve: "
                       "linked is a symlink", count=1)

    def test_claude_manifest_version_differs_fails_d3(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.update(version="1.0.16"))
        self.expect(1, "FAIL D3: the versions differ", "cleanlanguage/.claude-plugin/plugin.json version '1.0.16'")

    def test_agent_manifest_version_differs_fails_d3(self):
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(version="1.0.16"))
        self.expect(1, "FAIL D3: the versions differ", "cleanlanguage/plugin.json version '1.0.16'")

    def test_skill_version_differs_fails_d3(self):
        self.write_text(gate.SKILL_MD, "# Clean Language\n\nVersion: 1.0.16\n")
        self.expect(1, "FAIL D3: the versions differ", "SKILL.md Version: line '1.0.16'")

    def test_marketplace_entry_version_differs_fails_d3(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(version="1.0.16"))
        self.expect(1, "FAIL D3: the versions differ", "plugins[0].version '1.0.16'")

    def test_unresolved_dependency_fails_d4(self):
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(dependencies=["cleanlanguage"]))
        self.expect(1, "FAIL D4: plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json dependency "
                       "'cleanlanguage' names no plugin", "1 dependency read")

    def test_resolved_dependency_is_counted(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"].append(
            {"name": "aiqt-skill", "source": "./aiqt-skill", "dependencies": ["aiqt-guardrails-hooks@aiqt-guardrails"]}))
        self.write_json("plugin/aiqt-skill/.claude-plugin/plugin.json", manifest("aiqt-skill", "0.4.0"))
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(dependencies=["aiqt-skill"]))
        self.expect(0, "2 dependencies read", "3 relative sources resolved")

    def test_duplicate_json_key_exits_3(self):
        self.write_text(gate.AGENT_MANIFEST, '{"name": "cleanlanguage", "version": "1.0.15", "version": "1.0.15"}\n')
        self.expect(3, "cleanlanguage/plugin.json repeats the key 'version'")

    def test_json_keys_alike_but_for_letter_case_pass(self):
        # 2 keys of 1 object that differ only in letter case are 2 keys, not 1 key repeated.
        self.write_text(gate.AGENT_MANIFEST, '{"name": "cleanlanguage", "version": "1.0.15", "Version": "2"}\n')
        self.expect(0, "OK: D1 to D4 hold")

    def key_setups(self) -> list:
        """The setups of test_keys_in_another_letter_case_are_not_read, each (reads, rel, change, lines):
        places the gate reads a JSON key, as key_reads names them, that this setup pins, since a read of
        the key written in another letter case at any one of them would change the gate's output in this
        setup; the file the setup changes and how; and the FAIL lines the gate gives, each without its
        "FAIL " (none: exit 0). Such a read at a place a setup does not name can change its output too;
        each place is named by at least 1 setup."""
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        root, vend = ".claude-plugin/marketplace.json", "plugin/.claude-plugin/marketplace.json"

        def reach(rel, index, name, manifest_rel, reached):
            return (f"D1: {rel} plugins[{index}].name is {name!r}, but the manifest its source reaches, "
                    f"{manifest_rel}, is named {reached!r}")

        def other(key, value=None, entry=False):
            """The key written in another letter case in the JSON object, or in its first plugin entry:
            renamed with its value kept when value is None, else added with value."""
            def change(data):
                held = data["plugins"][0] if entry else data
                held[key.title()] = held.pop(key) if value is None else value
            return change

        def plugins_other(**values):
            """The plugins list held under Plugins, its first entry with the values given."""
            def change(data):
                data["Plugins"] = data.pop("plugins")
                data["Plugins"][0].update(values)
            return change

        def name_other(index, dependency, added=None):
            """The marketplace's name held under Name, and a dependency of plugins[index], added first
            when given."""
            def change(data):
                data["Name"] = data.pop("name")
                if added is not None:
                    data["plugins"].append(added)
                data["plugins"][index]["dependencies"] = [dependency]
            return change

        def entry_other(added=None, dependency=None):
            """An entry whose name is held under Name: plugins[0], or the entry added; a dependency of
            plugins[0], when given."""
            def change(data):
                if added is None:
                    data["plugins"][0]["Name"] = data["plugins"][0].pop("name")
                else:
                    data["plugins"].append(added)
                if dependency is not None:
                    data["plugins"][0]["dependencies"] = [dependency]
            return change

        names = ("check_names", "data", "name")
        sources = ("check_sources", "entry", "source")
        reaches = ("check_reach", "entry", "name")
        manifest_name = ("check_reach", "load_json(manifest)", "name")
        entry_deps = ("check_dependencies", "entry", "dependencies")
        manifest_deps = ("check_dependencies", "reached", "dependencies")
        plugin_reads = [("check_names", "data", "plugins"), ("check_dependencies", "data", "plugins")]
        return [
            # Each key, in each file and plugin entry where the gate reads it.
            ([("check_names", "root", "name"), names], root, other("name"),
             [f"D1: {root} name is None, not 'cleanlanguage'", f"D1: {root} name is None, not a name"]),
            ([("check_names", "root", "plugins"), ("plugin_entries", "data", "plugins")], root, other("plugins"),
             [f"D1: {root} lists no plugins, not exactly 1", f"D2: {root} has no plugins list"]),
            ([("check_names", "first", "name"), ("check_names", "entry", "name"), reaches], root,
             other("name", entry=True),
             [f"D1: {root} plugins[0].name is None, not 'cleanlanguage'", f"D1: {root} plugins[0].name is None, not a name",
              reach(root, 0, None, gate.CLAUDE_MANIFEST, "cleanlanguage")]),
            ([sources], root, other("source", entry=True), [f"D2: {root} plugins[0] has no source"]),
            ([("check_versions", "entry", "version")], root, other("version", "9.9.9", True), []),
            ([entry_deps], root, other("dependencies", ["no-such-plugin"], True), []),
            ([names], vend, other("name"), [f"D1: {vend} name is None, not a name"]),
            ([("plugin_entries", "data", "plugins")], vend, other("plugins"), [f"D2: {vend} has no plugins list"]),
            ([("check_names", "entry", "name"), reaches], vend, other("name", entry=True),
             [f"D1: {vend} plugins[0].name is None, not a name", reach(vend, 0, None, hooks, "aiqt-guardrails-hooks")]),
            ([sources], vend, other("source", entry=True), [f"D2: {vend} plugins[0] has no source"]),
            ([entry_deps], vend, other("dependencies", ["no-such-plugin"], True), []),
            ([("check_names", "claude", "name"), manifest_name], gate.CLAUDE_MANIFEST, other("name"),
             [f"D1: {gate.CLAUDE_MANIFEST} name is None, not 'cleanlanguage'",
              reach(root, 0, "cleanlanguage", gate.CLAUDE_MANIFEST, None)]),
            ([("check_versions", "claude", "version")], gate.CLAUDE_MANIFEST, other("version"),
             [f"D3: {gate.CLAUDE_MANIFEST} version is None, not a version"]),
            ([manifest_deps], gate.CLAUDE_MANIFEST, other("dependencies", ["no-such-plugin"]), []),
            ([("check_names", "agent", "name")], gate.AGENT_MANIFEST, other("name"),
             [f"D1: {gate.AGENT_MANIFEST} name is None, not 'cleanlanguage'"]),
            ([("check_versions", "agent", "version")], gate.AGENT_MANIFEST, other("version"),
             [f"D3: {gate.AGENT_MANIFEST} version is None, not a version"]),
            ([("check_names", "site", "site_key")], gate.SITE_JSON, other("site_key"),
             [f"D1: {gate.SITE_JSON} site_key is None, not 'cleanlanguage'"]),
            ([manifest_name], hooks, other("name"), [reach(vend, 0, "aiqt-guardrails-hooks", hooks, None)]),
            ([manifest_deps], hooks, other("dependencies", ["no-such-plugin"]), []),
            # Each place that reads a key the setups above change, but whose output those setups leave
            # alone: the plugins list as the names, versions and dependencies checks read it; the
            # marketplace name as a dependency's marketplace; and an entry's name as a dependency names
            # it and as the plugin a list belongs to.
            ([*plugin_reads, ("check_versions", "root", "plugins")], root,
             plugins_other(name="claude-x", version="9.9.9", dependencies=["no-such-plugin"]),
             [f"D1: {root} lists no plugins, not exactly 1", f"D2: {root} has no plugins list"]),
            (plugin_reads, vend, plugins_other(name="claude-x", dependencies=["no-such-plugin"]),
             [f"D2: {vend} has no plugins list"]),
            ([("check_dependencies", "data", "name")], root, name_other(0, "cleanlanguage@cleanlanguage"),
             [f"D1: {root} name is None, not 'cleanlanguage'", f"D1: {root} name is None, not a name",
              f"D4: {root} plugins[0] dependency 'cleanlanguage@cleanlanguage' names no plugin of the marketplace "
              f"None in {root}"]),
            ([("check_dependencies", "data", "name")], vend,
             name_other(1, "aiqt-guardrails-hooks@aiqt-guardrails", {"name": "aiqt-skill", "source": "./aiqt-skill"}),
             [f"D1: {vend} name is None, not a name",
              f"D4: {vend} plugins[1] dependency 'aiqt-guardrails-hooks@aiqt-guardrails' names no plugin of the "
              f"marketplace None in {vend}"]),
            ([("check_dependencies", "e", "name")], root, entry_other(dependency="cleanlanguage"),
             [f"D1: {root} plugins[0].name is None, not 'cleanlanguage'", f"D1: {root} plugins[0].name is None, not a name",
              reach(root, 0, None, gate.CLAUDE_MANIFEST, "cleanlanguage"),
              f"D4: {root} plugins[0] dependency 'cleanlanguage' names no plugin of the marketplace 'cleanlanguage' "
              f"in {root}"]),
            ([("check_dependencies", "e", "name")], vend,
             entry_other({"Name": "aiqt-skill", "source": "./aiqt-skill"}, "aiqt-skill"),
             [f"D1: {vend} plugins[1].name is None, not a name",
              reach(vend, 1, None, "plugin/aiqt-skill/.claude-plugin/plugin.json", "aiqt-skill"),
              f"D4: {vend} plugins[0] dependency 'aiqt-skill' names no plugin of the marketplace 'aiqt-guardrails' "
              f"in {vend}"]),
            ([("check_dependencies", "entry", "name")], root,
             entry_other({"Name": "cleanlanguage", "source": "./cleanlanguage", "dependencies": ["cleanlanguage"]}),
             [f"D1: {root} lists 2 plugins, not exactly 1", f"D1: {root} plugins[1].name is None, not a name",
              reach(root, 1, None, gate.CLAUDE_MANIFEST, "cleanlanguage")]),
            ([("check_dependencies", "entry", "name")], vend,
             entry_other({"Name": "aiqt-guardrails-hooks", "source": "./aiqt-guardrails-hooks",
                          "dependencies": ["aiqt-guardrails-hooks"]}),
             [f"D1: {vend} plugins[1].name is None, not a name", reach(vend, 1, None, hooks, "aiqt-guardrails-hooks")]),
        ]

    def test_keys_in_another_letter_case_are_not_read(self):
        # Each place the gate reads a JSON key, with the key written in another letter case in a setup
        # whose output that place would change if it read the key. The gate reads a key exactly as
        # written, so a key it requires is missing, and a key it reads only where present, given a value
        # that fails when read, is not read. The manifest of a vendored entry that only 2 setups list.
        self.write_json("plugin/aiqt-skill/.claude-plugin/plugin.json", manifest("aiqt-skill", "0.4.0"))
        for reads, rel, change, lines in self.key_setups():
            with self.subTest(rel=rel, reads=reads):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    if lines:
                        output = self.expect(1, count=len(lines))
                        self.assertEqual(output.splitlines()[:-2], [f"FAIL {line}" for line in lines], output)
                    else:
                        self.expect(0, "0 dependencies read")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_each_place_the_gate_reads_a_key_has_a_setup(self):
        # The places key_reads finds in the gate, each counted as often as it is found, are exactly the
        # places the setups of test_keys_in_another_letter_case_are_not_read name, each once, and those of
        # NOT_JSON_READS, each as often as listed. So a read added in any form key_reads finds, moved, or
        # made twice at 1 place fails here until a setup or NOT_JSON_READS names it; and a read whose key
        # is not a string constant, or that reads every key, fails unless NOT_JSON_READS lists it.
        reads = collections.Counter(key_reads(MODULE_PATH.read_text(encoding="utf-8")))
        named = collections.Counter({read for setup_reads, _, _, _ in self.key_setups() for read in setup_reads})
        self.assertEqual(set(named) & set(NOT_JSON_READS), set())
        listed = named + collections.Counter(NOT_JSON_READS)
        self.assertEqual((sorted((reads - listed).elements(), key=repr), sorted((listed - reads).elements(), key=repr)),
                         ([], []))

    def test_key_reads_finds_each_form_of_key_read(self):
        # Each form in which Python source reads a key of a dict, in a function f, with KEY bound once at
        # module level, and what key_reads finds for it; then forms that read no key of a dict.
        one = [("f", "obj", "Version")]
        every = [("f", "obj", None)]
        forms = [
            ('obj.get("Version")', one), ('obj.get("Version", None)', one), ('obj["Version"]', one),
            ('obj["Version"] += "x"', one), ('"Version" in obj', one), ('"Version" not in obj', one),
            ('"a" == "Version" in obj', one), ('"Version" in load(obj)', [("f", "load(obj)", "Version")]),
            ('dict.get(obj, "Version")', one),
            ('type(obj).get(obj, "Version")', one), ('obj.pop("Version")', one), ('obj.setdefault("Version")', one),
            ('obj.__getitem__("Version")', one), ('obj.__contains__("Version")', one),
            ('operator.getitem(obj, "Version")', one), ('operator.contains(obj, "Version")', one),
            ('operator.itemgetter("Version")(obj)', [("f", "operator.itemgetter", "Version")]),
            ('obj.get(KEY)', one), ('obj[KEY]', one),
            ('match obj:\n        case {"Version": _}:\n            pass', one),
            ('match obj:\n        case [{"Version": {"Inner": _}}]:\n            pass',
             [("f", "obj[0]", "Version"), ("f", "obj[0]['Version']", "Inner")]),
            ('obj.get(key)', every), ('obj.get(KEY.lower())', every), ('obj[key]', every), ('key in obj', every),
            ('obj.items()', every), ('obj.keys()', every), ('obj.values()', every), ('obj.copy()', every),
            ('obj.popitem()', every), ('obj.__iter__()', every), ('getter = obj.get', every),
            ('getattr(obj, "get")("Version")', every), ('getattr(obj, key)', every),
            ('operator.getitem', [("f", "operator.getitem", None)]),
            ('match obj:\n        case {**rest}:\n            pass', every),
            ('for key in obj:\n        pass', every), ('[key for key in obj]', every), ('{**obj}', every),
            ('dict(**obj)', every), ('[*obj]', every), ('first, *rest = obj', every), ('yield from obj', every),
            ('list(obj)', every), ('sorted(obj)', every), ('enumerate(obj)', every), ('map(str, obj)', every),
            ('"".join(obj)', every), ('for key in (obj if key else []):\n        pass', every),
            ('for key in key or obj:\n        pass', [("f", "key", None), ("f", "obj", None)]),
            ('for key in load(obj):\n        pass', [("f", "load(obj)", None)]),
            ('obj[0]', []), ('obj[-1]', []), ('obj[1:]', []), ('"a" in "abc"', []), ('"a" in ("a", "b")', []),
            ('for key in ("a", "b"):\n        pass', []), ('getattr(obj, "real", 0)', []), ('x = {"a": obj}', []),
            ('len(obj)', []), ('for key, value in obj.items():\n        pass', every),
        ]
        for statement, expected in forms:
            with self.subTest(statement=statement):
                source = f'import operator\nKEY = "Version"\n\n\ndef f(obj, key, load):\n    {statement}\n'
                self.assertEqual(sorted(key_reads(source), key=repr), sorted(expected, key=repr))
        # A name bound more than once is not read as a string constant.
        source = 'KEY = "Version"\n\n\ndef f(obj):\n    KEY = "x"\n    obj.get(KEY)\n'
        self.assertEqual(key_reads(source), [("f", "obj", None)])

    def test_unreadable_file_exits_3(self):
        (self.root / gate.SITE_JSON).unlink()
        (self.root / gate.SITE_JSON).mkdir()
        self.expect(3, "site-src/site.json could not be read: it is not a regular file")

    def test_missing_file_exits_3(self):
        (self.root / gate.VENDORED_MARKETPLACE).unlink()
        # The exact cause line: a refusal of the gate is shown as it is, not as an exception that stopped it.
        self.expect(3, "check-plugin-distribution: plugin/.claude-plugin/marketplace.json could not be read: "
                       f"{os.strerror(errno.ENOENT)}\nUNREADABLE: exit 3\n")

    def test_source_reaching_another_plugin_fails_d2_and_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./plugin/aiqt-guardrails-hooks"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './plugin/aiqt-guardrails-hooks' "
                       "reaches plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, not "
                       "cleanlanguage/.claude-plugin/plugin.json",
                    "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is 'cleanlanguage', but the manifest "
                    "its source reaches, plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, is named "
                    "'aiqt-guardrails-hooks'")

    def test_source_reaching_a_copy_of_the_plugin_fails_d2(self):
        self.write_json("copy/.claude-plugin/plugin.json", manifest())
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./copy"))
        output = self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './copy' reaches "
                                "copy/.claude-plugin/plugin.json, not cleanlanguage/.claude-plugin/plugin.json")
        self.assertNotIn("FAIL D1", output)

    def test_source_reaching_a_folder_named_in_another_letter_case_fails_d2(self):
        # A folder of its own, named like the plugin's folder but for letter case, that holds a manifest
        # of the project's name; a file system that folds letter case cannot hold both folders.
        if (self.root / "CleanLanguage").exists():
            self.skipTest("the file system folds letter case")
        self.write_json("CleanLanguage/.claude-plugin/plugin.json", manifest())
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./CleanLanguage"))
        output = self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './CleanLanguage' reaches "
                                "CleanLanguage/.claude-plugin/plugin.json, not cleanlanguage/.claude-plugin/plugin.json",
                             count=1)
        self.assertNotIn("FAIL D1", output)

    def test_object_source_fails_d2(self):
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source={"source": "github", "repo": "someone/else"}))
                try:
                    self.expect(1, f"FAIL D2: {rel} plugins[0].source {{'source': 'github', 'repo': 'someone/else'}} is "
                                   "not a string, so this gate cannot read where it leads", "1 relative source resolved")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_null_source_fails_d2(self):
        # An explicit JSON null is a source that is not a string, not a missing source.
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=None))
                try:
                    self.expect(1, f"FAIL D2: {rel} plugins[0].source None is not a string, so this gate cannot read "
                                   "where it leads", "1 relative source resolved", count=1)
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_vendored_entry_named_unlike_its_manifest_fails_d1(self):
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json", lambda d: d.update(name="aiqt-hooks"))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is 'aiqt-guardrails-hooks', "
                       "but the manifest its source reaches, plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, "
                       "is named 'aiqt-hooks'")

    def test_empty_plugins_list_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d.update(plugins=[]))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 0 plugins, not exactly 1")

    def test_agent_manifest_name_differs_fails_d1(self):
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(name="clean-language"))
        self.expect(1, "FAIL D1: cleanlanguage/plugin.json name is 'clean-language', not 'cleanlanguage'")

    def test_site_key_differs_fails_d1(self):
        self.edit_json(gate.SITE_JSON, lambda d: d.update(site_key="jposluns"))
        self.expect(1, "FAIL D1: site-src/site.json site_key is 'jposluns', not 'cleanlanguage'")

    def test_source_without_dot_slash_fails_d2(self):
        # Sources whose first 2 characters are not "./", among them some that start with "." or "/", and 1
        # whose characters after the first 2 name the plugin's folder.
        for rel, folder in ((gate.MARKETPLACE, "cleanlanguage"), (gate.VENDORED_MARKETPLACE, "aiqt-guardrails-hooks")):
            for source in (folder, "", ".", "/", f"/{folder}", f".x{folder}", f"../{folder}", f".\\{folder}",
                           f"/./{folder}"):
                with self.subTest(rel=rel, source=source):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source {source!r} does not start with './'")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_source_that_is_a_file_fails_d2(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./cleanlanguage/plugin.json"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './cleanlanguage/plugin.json' "
                       "does not resolve: cleanlanguage/plugin.json is not a directory")

    def test_manifest_that_is_a_directory_fails_d2(self):
        path = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        path.unlink()
        path.mkdir()
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' "
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json is not a regular "
                       "file")

    def test_entry_without_source_fails_d2(self):
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].pop("source"))
                try:
                    output = self.expect(1, f"FAIL D2: {rel} plugins[0] has no source", "1 relative source resolved")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_missing_manifest_version_fails_d3(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.pop("version"))
        self.expect(1, "FAIL D3: cleanlanguage/.claude-plugin/plugin.json version is None, not a version")

    def test_entry_version_not_a_string_fails_d3(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(version=1.0))
        self.expect(1, "FAIL D3: .claude-plugin/marketplace.json plugins[0].version is 1.0, not a version", count=1)

    def test_skill_without_version_line_fails_d3(self):
        self.write_text(gate.SKILL_MD, "---\nname: cleanlanguage\n---\n\n# Clean Language\n")
        self.expect(1, "FAIL D3: cleanlanguage/skills/cleanlanguage/SKILL.md Version: line is None, not a version")

    def test_dependency_of_another_marketplace_fails_d4(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage@jposluns"]))
        self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependency 'cleanlanguage@jposluns' "
                       "names no plugin of the marketplace 'cleanlanguage'")

    def test_dependencies_not_a_list_fails_d4(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies="cleanlanguage"))
        self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependencies is not a list")

    def test_dependency_not_a_name_fails_d4(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=[{"name": "x"}]))
        self.expect(1, "FAIL D4: cleanlanguage/.claude-plugin/plugin.json names the dependency {'name': 'x'}, not "
                       "a plugin name")

    def test_nan_exits_3(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.write_text(gate.SITE_JSON, '{"schema": ' + constant + ', "site_key": "cleanlanguage"}\n')
                self.expect(3, f"site-src/site.json could not be decoded as JSON: non-standard JSON constant "
                               f"{constant!r}")

    def test_json_that_is_not_an_object_exits_3(self):
        self.write_text(gate.AGENT_MANIFEST, '["cleanlanguage"]\n')
        self.expect(3, "cleanlanguage/plugin.json is not a JSON object")

    def test_json_not_utf8_exits_3(self):
        (self.root / gate.MARKETPLACE).write_bytes(b'{"name": "clean\xfflanguage"}\n')
        self.expect(3, ".claude-plugin/marketplace.json is not UTF-8")

    def test_skill_not_utf8_exits_3(self):
        (self.root / gate.SKILL_MD).write_bytes(b"Version: 1.0.15\n\xff\n")
        self.expect(3, "cleanlanguage/skills/cleanlanguage/SKILL.md is not UTF-8")

    def test_symlinked_input_file_exits_3(self):
        target = self.root / "site.json.real"
        (self.root / gate.SITE_JSON).rename(target)
        os.symlink(target, self.root / gate.SITE_JSON)
        self.expect(3, "site-src/site.json could not be read: the component 'site.json' is a symlink")

    def test_each_reserved_prefix_fails_d1(self):
        for prefix in RESERVED_PREFIXES:
            with self.subTest(prefix=prefix):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=f"{prefix}guardrails"))
                self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name '{prefix}guardrails' starts "
                               "with a reserved prefix")

    def test_reserved_prefix_in_entry_name_fails_d1(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(name="cc-plugin-hooks"))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name 'cc-plugin-hooks' starts "
                       "with a reserved prefix")

    def test_marketplace_name_missing_or_empty_fails_d1(self):
        for change, shown in ((lambda d: d.pop("name"), "None"), (lambda d: d.update(name=""), "''")):
            with self.subTest(name=shown):
                self.write_json(gate.VENDORED_MARKETPLACE, vendored())
                self.edit_json(gate.VENDORED_MARKETPLACE, change)
                self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name is {shown}, not a name")

    def test_symlinked_manifest_folder_fails_d2(self):
        folder = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin"
        folder.rename(folder.with_name("real-claude-plugin"))
        os.symlink(folder.with_name("real-claude-plugin"), folder)
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' "
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin is a symlink", count=1)

    def test_symlinked_manifest_fails_d2(self):
        path = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        path.rename(path.with_name("real.json"))
        os.symlink(path.with_name("real.json"), path)
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' "
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json is a symlink", count=1)

    def test_symlinked_input_folder_exits_3(self):
        (self.root / "site-src").rename(self.root / "site-src.real")
        os.symlink(self.root / "site-src.real", self.root / "site-src")
        self.expect(3, "site-src/site.json could not be read: the component 'site-src' is a symlink")

    def test_byte_order_mark_passes(self):
        path = self.root / gate.MARKETPLACE
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.expect(0, "OK: D1 to D4 hold")

    def test_vendored_entry_not_an_object_fails_d2(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(plugins=["aiqt-guardrails-hooks"]))
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0] is not a JSON object")

    def test_vendored_marketplace_without_plugins_list_fails_d2(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.pop("plugins"))
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json has no plugins list")

    def test_empty_version_fails_d3(self):
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(version=""))
        self.expect(1, "FAIL D3: cleanlanguage/plugin.json version is '', not a version", count=1)

    def test_failure_count_line(self):
        self.edit_json(gate.SITE_JSON, lambda d: d.update(site_key="jposluns"))
        output = self.expect(1)
        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(name="clean-language"))
        output = self.expect(1)
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_unreadable_last_line(self):
        (self.root / gate.SITE_JSON).unlink()
        got, out, err = self.run_gate()
        self.assertEqual(got, 3, out + err)
        self.assertEqual(err.splitlines()[-1], "UNREADABLE: exit 3")

    def test_deeply_nested_json_exits_3(self):
        # A conforming site object whose "deep" member nests arrays to the given total depth (the object
        # is level 1). Its string holds escaped quotes and brackets, which the bound must not count.
        def site(depth: int) -> str:
            inner = depth - 1
            return ('{"schema": 1, "site_key": "cleanlanguage", "note": "' + '\\"[{' * 100 + '", "deep": '
                    + "[" * inner + "]" * inner + "}\n")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH))
        self.expect(0, "OK: D1 to D4 hold")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH + 1))
        self.expect(3, f"site-src/site.json is nested too deeply to decode: more than {MAX_JSON_DEPTH} levels")

    def test_source_with_empty_component_fails_d2(self):
        for rel, folder in ((gate.MARKETPLACE, "cleanlanguage"), (gate.VENDORED_MARKETPLACE, "aiqt-guardrails-hooks")):
            for source in (f"./{folder}/", f".//{folder}"):
                with self.subTest(rel=rel, source=source):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' has an empty, '.' or "
                                                "'..' component", "1 relative source resolved")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_extractor_without_a_pattern_exits_3(self):
        for name in ("VERSION_LINE", "SKILL_VERSION"):
            with self.subTest(name=name):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor(f"{name} = re.compile", f"{name}_GONE = re.compile")
                self.expect(3, f"the extractor tools/skill-version.py could not be used: it has no {name} "
                               "pattern of text")

    def test_extractor_raising_while_it_loads_exits_3(self):
        # BaseException and 5 of its subclasses, among them 1 message that holds a line break and 1
        # that cannot be shown; the cause line holds each on 1 line.
        unshowable = ("class Unshowable(Exception):\n    def __str__(self):\n        raise ValueError('no text')\n"
                      "raise Unshowable()")
        for statement, shown in (("raise RuntimeError('broken')", "RuntimeError: broken"),
                                 ("raise SystemExit(0)", "SystemExit: 0"),
                                 ("raise BaseException('boom')", "BaseException: boom"),
                                 ("raise GeneratorExit", "GeneratorExit: "),
                                 ("raise KeyboardInterrupt", "KeyboardInterrupt: "),
                                 ("raise RuntimeError('a\\nUNREADABLE: exit 3')", "RuntimeError: a\\nUNREADABLE: exit 3"),
                                 (unshowable, "Unshowable: (a message that cannot be shown)")):
            with self.subTest(statement=statement):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor('PROG = "skill-version"\n', f'PROG = "skill-version"\n{statement}\n')
                self.expect(3, f"the extractor tools/skill-version.py could not be loaded: {shown}")

    def test_any_exception_in_the_gate_exits_3_on_1_line(self):
        # An exception raised in the gate itself, not in the extractor: BaseException and 4 of its
        # subclasses, 2 messages with a line break and 1 that cannot be shown; exit 3 and 1 cause line.
        class Unshowable(Exception):
            def __str__(self):
                raise ValueError("no text")

        for error, shown in ((TypeError("a\nFAIL D1: x"), "TypeError: a\\nFAIL D1: x"),
                             (BaseException("b\r\nUNREADABLE: exit 3"), "BaseException: b\\r\\nUNREADABLE: exit 3"),
                             (KeyboardInterrupt(), "KeyboardInterrupt: "),
                             (SystemExit(0), "SystemExit: 0"),
                             (Unshowable(), "Unshowable: (a message that cannot be shown)")):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(gate, "check_versions", side_effect=error):
                    output = self.expect(3, f"check-plugin-distribution: the gate stopped on {shown}\n")
                self.assertNotIn("Traceback", output)

    def test_missing_extractor_exits_3(self):
        (self.root / EXTRACTOR_REL).unlink()
        self.expect(3, "tools/skill-version.py could not be read")

    def test_symlinked_extractor_exits_3(self):
        path = self.root / EXTRACTOR_REL
        path.rename(path.with_name("real-skill-version.py"))
        os.symlink(path.with_name("real-skill-version.py"), path)
        self.expect(3, "tools/skill-version.py could not be read: the component 'skill-version.py' is a symlink")

    def test_reserved_prefix_in_any_case_fails_d1(self):
        for name in ("Claude-x", "ANTHROPIC-x", "Anthropics-x", "CC-Plugin-x"):
            with self.subTest(name=name):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=name))
                self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name '{name}' starts with a "
                               "reserved prefix")

    def test_count_lines_read_for_1(self):
        # An empty vendored list resolves no source and is no failure; the 1 dependency is the 1 failure.
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(plugins=[]))
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage"]))
        output = self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependency 'cleanlanguage' "
                                "names the plugin itself")
        self.assertIn("check-plugin-distribution: 1 relative source resolved, 1 dependency read\n", output)
        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")

    def test_count_lines_read_for_more_than_1(self):
        self.add_vendored("aiqt-skill")
        self.add_vendored("aiqt-docs")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(
            dependencies=["aiqt-skill", "aiqt-docs@aiqt-guardrails"]))
        output = self.expect(0)
        self.assertIn("check-plugin-distribution: 4 relative sources resolved, 2 dependencies read\n", output)

    def test_entry_name_that_is_an_array_fails_d1(self):
        # Read by the names check, by the reach check and by the dependencies check's set of names.
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(name=["x"]))
        output = self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is ['x'], not a name",
                             "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is ['x'], but the "
                             "manifest its source reaches",
                             "check-plugin-distribution: 2 relative sources resolved, 0 dependencies read\n")
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_entry_name_that_is_an_object_fails_d1(self):
        # The repository's second entry: read by the names check and by the dependencies check.
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append({"name": {"a": 1}, "source": "./absent"}))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1",
                    "FAIL D1: .claude-plugin/marketplace.json plugins[1].name is {'a': 1}, not a name")

    def test_marketplace_name_that_is_an_array_fails_d1_and_d4(self):
        # Read by the names check and by a qualified dependency.
        self.add_vendored("aiqt-skill")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=["x"]))
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["aiqt-skill@x"]))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json name is ['x'], not a name",
                    "FAIL D4: plugin/.claude-plugin/marketplace.json plugins[0] dependency 'aiqt-skill@x' names no "
                    "plugin of the marketplace ['x']")

    def test_manifest_name_that_is_an_array_fails_d1(self):
        # Read by the reach check, and by the dependencies check as the manifest's own name.
        self.add_vendored("aiqt-skill")
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(name=["x"], dependencies=["aiqt-skill"]))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is 'aiqt-guardrails-hooks', "
                       "but the manifest its source reaches, plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, "
                       "is named ['x']", "1 dependency read")

    def test_project_name_in_another_letter_case_fails_d1(self):
        for rel, key, label in ((gate.MARKETPLACE, "name", ".claude-plugin/marketplace.json name"),
                                (gate.CLAUDE_MANIFEST, "name", "cleanlanguage/.claude-plugin/plugin.json name"),
                                (gate.AGENT_MANIFEST, "name", "cleanlanguage/plugin.json name"),
                                (gate.SITE_JSON, "site_key", "site-src/site.json site_key")):
            with self.subTest(label=label):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d.update({key: "CleanLanguage"}))
                self.expect(1, f"FAIL D1: {label} is 'CleanLanguage', not 'cleanlanguage'")
                (self.root / rel).write_bytes(saved)
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(name="CleanLanguage"))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is 'CleanLanguage', not "
                       "'cleanlanguage'")

    def test_dependency_with_an_empty_marketplace_fails_d4(self):
        self.add_vendored("aiqt-skill")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["aiqt-skill@"]))
        self.expect(1, "FAIL D4: plugin/.claude-plugin/marketplace.json plugins[0] dependency 'aiqt-skill@' names no "
                       "plugin of the marketplace 'aiqt-guardrails'")

    def test_empty_dependency_fails_d4(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=[""]))
        self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] names the dependency '', not a plugin name")

    def test_extractor_pattern_of_bytes_exits_3(self):
        for name in ("VERSION_LINE", "SKILL_VERSION"):
            with self.subTest(name=name):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor(f'{name} = re.compile(r"', f'{name} = re.compile(rb"')
                self.expect(3, f"the extractor tools/skill-version.py could not be used: it has no {name} "
                               "pattern of text")

    def test_self_dependency_fails_d4(self):
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        for rel, change, label, dep in (
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage"]),
                 ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage"),
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage@cleanlanguage"]),
                 ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage@cleanlanguage"),
                (gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=["cleanlanguage"]),
                 "cleanlanguage/.claude-plugin/plugin.json", "cleanlanguage"),
                (gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["aiqt-guardrails-hooks"]),
                 "plugin/.claude-plugin/marketplace.json plugins[0]", "aiqt-guardrails-hooks"),
                (hooks, lambda d: d.update(dependencies=["aiqt-guardrails-hooks@aiqt-guardrails"]),
                 hooks, "aiqt-guardrails-hooks@aiqt-guardrails")):
            with self.subTest(label=label, dep=dep):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                output = self.expect(1, f"FAIL D4: {label} dependency {dep!r} names the plugin itself, which this "
                                        "gate refuses")
                self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                (self.root / rel).write_bytes(saved)

    def test_repeated_dependency_fails_d4(self):
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        self.add_vendored("aiqt-skill")
        for rel, change, label, dep in (
                (gate.VENDORED_MARKETPLACE,
                 lambda d: d["plugins"][0].update(dependencies=["aiqt-skill", "aiqt-skill"]),
                 "plugin/.claude-plugin/marketplace.json plugins[0]", "aiqt-skill"),
                (gate.VENDORED_MARKETPLACE,
                 lambda d: d["plugins"][0].update(dependencies=["aiqt-skill", "aiqt-skill@aiqt-guardrails"]),
                 "plugin/.claude-plugin/marketplace.json plugins[0]", "aiqt-skill@aiqt-guardrails"),
                (hooks, lambda d: d.update(dependencies=["aiqt-skill@aiqt-guardrails", "aiqt-skill"]),
                 hooks, "aiqt-skill")):
            with self.subTest(label=label, dep=dep):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    output = self.expect(1, f"FAIL D4: {label} dependency {dep!r} names the plugin 'aiqt-skill' a "
                                            "second time, which this gate refuses", "2 dependencies read")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_source_that_is_no_path_fails_d2(self):
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            for source, shown in (("./a\x00b", "'./a\\x00b'"), ("./\ud800", "'./\\ud800'")):
                with self.subTest(rel=rel, source=shown):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source {shown} is not a path the "
                                                "operating system accepts", "1 relative source resolved")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_source_with_dot_component_fails_d2(self):
        for rel, folder in ((gate.MARKETPLACE, "cleanlanguage"), (gate.VENDORED_MARKETPLACE, "aiqt-guardrails-hooks")):
            for source in (f"././{folder}", f"./{folder}/."):
                with self.subTest(rel=rel, source=source):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' has an empty, '.' "
                                                "or '..' component", "1 relative source resolved")
                        self.assertNotIn("reaches", output)
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_source_with_too_long_component_fails_d2(self):
        source = "./" + "a" * 300
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                try:
                    output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' is not a path the operating "
                                            f"system accepts: {os.strerror(errno.ENAMETOOLONG)}\n",
                                         "1 relative source resolved")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_null_dependencies_fails_d4(self):
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        for rel, change, label in (
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=None),
                 ".claude-plugin/marketplace.json plugins[0]"),
                (gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=None),
                 "cleanlanguage/.claude-plugin/plugin.json"),
                (gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=None),
                 "plugin/.claude-plugin/marketplace.json plugins[0]"),
                (hooks, lambda d: d.update(dependencies=None), hooks)):
            with self.subTest(label=label):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    output = self.expect(1, f"FAIL D4: {label} dependencies is not a list")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_many_sibling_arrays_within_the_depth_bound_pass(self):
        # 3 levels deep, but more than MAX_JSON_DEPTH arrays and objects in all: the bound counts nesting.
        siblings = ", ".join(["[]"] * (MAX_JSON_DEPTH + 6))
        self.write_text(gate.SITE_JSON, '{"schema": 1, "site_key": "cleanlanguage", "deep": [' + siblings + "]}\n")
        self.expect(0, "OK: D1 to D4 hold")

    def test_many_sibling_objects_within_the_depth_bound_pass(self):
        # The same with objects: each closing brace lowers the count, as each closing bracket does.
        siblings = ", ".join(['{"a": 1}'] * (MAX_JSON_DEPTH + 6))
        self.write_text(gate.SITE_JSON, '{"schema": 1, "site_key": "cleanlanguage", "deep": [' + siblings + "]}\n")
        self.expect(0, "OK: D1 to D4 hold")

    def test_deeply_nested_objects_exit_3(self):
        # A conforming site object whose "deep" member nests objects to the given total depth.
        def site(depth: int) -> str:
            inner = depth - 1
            return ('{"schema": 1, "site_key": "cleanlanguage", "deep": ' + '{"a": ' * (inner - 1) + "{}"
                    + "}" * (inner - 1) + "}\n")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH))
        self.expect(0, "OK: D1 to D4 hold")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH + 1))
        self.expect(3, f"site-src/site.json is nested too deeply to decode: more than {MAX_JSON_DEPTH} levels")

    def test_plugin_listed_twice_in_the_repository_marketplace_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append(dict(d["plugins"][0])))
        output = self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1",
                             "FAIL D1: .claude-plugin/marketplace.json plugins[1].name 'cleanlanguage' lists the "
                             "plugin of plugins[0] a second time, which this gate refuses",
                             "3 relative sources resolved")
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_plugin_listed_twice_in_the_vendored_marketplace_fails_d1(self):
        # The second listing comes after another plugin; in another letter case it reaches a manifest
        # of its own name, so the repeated name is the 1 failure.
        self.add_vendored("aiqt-skill")
        self.write_json("plugin/aiqt-hooks-copy/.claude-plugin/plugin.json", manifest("AIQT-Guardrails-Hooks", "0.4.0"))
        for name, source in (("aiqt-guardrails-hooks", "./aiqt-guardrails-hooks"),
                             ("AIQT-Guardrails-Hooks", "./aiqt-hooks-copy")):
            with self.subTest(name=name):
                saved = (self.root / gate.VENDORED_MARKETPLACE).read_bytes()
                self.edit_json(gate.VENDORED_MARKETPLACE,
                               lambda d: d["plugins"].append({"name": name, "source": source}))
                try:
                    output = self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json plugins[2].name {name!r} "
                                            "lists the plugin of plugins[0] a second time, which this gate refuses",
                                            "4 relative sources resolved")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / gate.VENDORED_MARKETPLACE).write_bytes(saved)

    def test_source_in_another_letter_case_fails_d2(self):
        # Each spelling reaches its folder through a folding os.lstat, but is not how the folder lists it.
        # A stored name is renamed for the last 2: the .claude-plugin folder and the manifest's final file name.
        folder = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin"
        for rel, source, rename, shown in (
                (gate.MARKETPLACE, "./CleanLanguage", None, "CleanLanguage"),
                (gate.VENDORED_MARKETPLACE, "./AIQT-Guardrails-Hooks", None, "plugin/AIQT-Guardrails-Hooks"),
                (gate.VENDORED_MARKETPLACE, "./aiqt-guardrails-hooks", (folder, ".Claude-Plugin"),
                 "plugin/aiqt-guardrails-hooks/.claude-plugin"),
                (gate.VENDORED_MARKETPLACE, "./aiqt-guardrails-hooks", (folder / "plugin.json", "Plugin.json"),
                 "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json")):
            with self.subTest(source=source, rename=rename and rename[1]):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                if rename:
                    rename[0].rename(rename[0].with_name(rename[1]))
                try:
                    with mock.patch.object(gate, "os", FoldingOs(self.root)):
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' does not resolve: {shown} "
                                                "is not spelled as its folder lists it", "1 relative source resolved")
                    self.assertNotIn("reaches", output)
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)
                    if rename:
                        rename[0].with_name(rename[1]).rename(rename[0])

    def test_input_folder_in_another_letter_case_exits_3(self):
        (self.root / "site-src").rename(self.root / "Site-Src")
        with mock.patch.object(gate, "os", FoldingOs(self.root)):
            self.expect(3, "site-src/site.json could not be read: the component 'site-src' is not spelled as its "
                           "folder lists it")

    def test_lists_naming_the_same_plugin_pass(self):
        # An entry's list, its manifest's list and another entry's list each name aiqt-skill once.
        self.add_vendored("aiqt-skill")
        self.add_vendored("aiqt-docs")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: (d["plugins"][0].update(dependencies=["aiqt-skill"]),
                                                             d["plugins"][2].update(dependencies=["aiqt-skill"])))
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(dependencies=["aiqt-skill@aiqt-guardrails"]))
        output = self.expect(0, "OK: D1 to D4 hold", "4 relative sources resolved, 3 dependencies read")
        self.assertNotIn("FAIL", output)

    @contextlib.contextmanager
    def denied(self, rel: str, kept: int = 0):
        """rel with every permission but those of kept taken away, given back before the tree is removed."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root is not refused by file permissions")
        path = self.root / rel
        mode = path.stat().st_mode
        path.chmod(kept)
        try:
            yield
        finally:
            path.chmod(mode)

    def test_input_file_denying_permission_exits_3(self):
        with self.denied(gate.SITE_JSON):
            self.expect(3, "site-src/site.json could not be read: Permission denied")

    def test_source_folder_denying_permission_exits_3(self):
        with self.denied("plugin/aiqt-guardrails-hooks"):
            self.expect(3, "plugin/aiqt-guardrails-hooks/.claude-plugin could not be read: Permission denied")

    def test_source_folder_that_cannot_be_listed_exits_3(self):
        # Mode 0111: os.lstat reaches the .claude-plugin folder inside, but os.listdir of the folder fails.
        with self.denied("plugin/aiqt-guardrails-hooks", 0o111):
            self.expect(3, "plugin/aiqt-guardrails-hooks could not be listed: Permission denied")

    def test_input_folder_that_cannot_be_listed_exits_3(self):
        # Mode 0111: os.lstat reaches site.json, but os.listdir of site-src fails.
        with self.denied("site-src", 0o111):
            self.expect(3, "site-src/site.json could not be read: Permission denied")

    def test_malformed_first_version_line_fails_d3(self):
        # The first Version: line is not a bare X.Y.Z, alone and before a valid one, which is never read.
        for lines in (f"Version: {VERSION} beta\n", f"Version: {VERSION} beta\n\nVersion: {VERSION}\n"):
            with self.subTest(lines=lines):
                self.write_text(gate.SKILL_MD, "---\nname: cleanlanguage\n---\n\n# Clean Language\n\n" + lines)
                output = self.expect(1, "FAIL D3: cleanlanguage/skills/cleanlanguage/SKILL.md Version: line is None, "
                                        "not a version")
                self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")

    def test_input_file_name_in_another_letter_case_exits_3(self):
        (self.root / gate.SITE_JSON).rename(self.root / "site-src/Site.json")
        with mock.patch.object(gate, "os", FoldingOs(self.root)):
            self.expect(3, "site-src/site.json could not be read: the component 'site.json' is not spelled as its "
                           "folder lists it")

    def test_names_equal_under_case_folding_fail_d1(self):
        # The long s (U+017F) folds to "s", while str.lower keeps it.
        name = "anthropic\u017f-hooks"
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=name))
        self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name {name!r} starts with a reserved prefix")
        self.write_json(gate.VENDORED_MARKETPLACE, vendored())
        name = "aiqt-\u017fkill"
        self.add_vendored("aiqt-skill")
        self.write_json("plugin/aiqt-skill-copy/.claude-plugin/plugin.json", manifest(name, "0.4.0"))
        self.edit_json(gate.VENDORED_MARKETPLACE,
                       lambda d: d["plugins"].append({"name": name, "source": "./aiqt-skill-copy"}))
        output = self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json plugins[2].name {name!r} lists the "
                                "plugin of plugins[1] a second time, which this gate refuses",
                             "4 relative sources resolved")
        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")

    def test_repeated_dependency_in_the_repository_marketplace_fails_d4(self):
        # A second plugin there, so that its entry and manifest can name a plugin other than their own; the
        # second entry and the source it reaches are the 2 other failures.
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append({"name": "helper", "source": "./helper"}))
        self.write_json("helper/.claude-plugin/plugin.json", manifest("helper"))
        for rel, change, label, dep in (
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["helper", "helper@cleanlanguage"]),
                 ".claude-plugin/marketplace.json plugins[0]", "helper@cleanlanguage"),
                (gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=["helper@cleanlanguage", "helper"]),
                 "cleanlanguage/.claude-plugin/plugin.json", "helper")):
            with self.subTest(label=label):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    output = self.expect(1, f"FAIL D4: {label} dependency {dep!r} names the plugin 'helper' a second "
                                            "time, which this gate refuses",
                                         "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1",
                                         "FAIL D2: .claude-plugin/marketplace.json plugins[1].source './helper' reaches "
                                         "helper/.claude-plugin/plugin.json, not cleanlanguage/.claude-plugin/plugin.json",
                                         "3 relative sources resolved, 2 dependencies read")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 3 inconsistencies")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_extractor_pattern_without_group_1_exits_3(self):
        for old, new, shown in (
                (r"([0-9]+\.[0-9]+\.[0-9]+)", r"(?:[0-9]+\.[0-9]+\.[0-9]+)", "its SKILL_VERSION pattern has no group 1"),
                ('SKILL_VERSION = re.compile(r"^Version:', 'SKILL_VERSION = re.compile(r"^(unused)?Version:',
                 f"its SKILL_VERSION pattern matched 'Version: {VERSION}  ' with no text in group 1")):
            with self.subTest(new=new):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor(old, new)
                self.expect(3, f"the extractor tools/skill-version.py could not be used: {shown}")

    def test_extractor_output_while_it_loads_is_dropped(self):
        self.edit_extractor('PROG = "skill-version"\n', 'PROG = "skill-version"\nimport sys\nprint("FAIL D9: forged")\n'
                            'print("UNREADABLE: exit 3", file=sys.stderr)\n')
        output = self.expect(0, "OK: D1 to D4 hold")
        self.assertNotIn("D9", output)
        self.assertNotIn("UNREADABLE", output)

    def test_line_break_in_a_missing_source_stays_on_1_line(self):
        for rel, base in ((gate.MARKETPLACE, ""), (gate.VENDORED_MARKETPLACE, "plugin/")):
            for brk in BREAKS:
                source, shown = f"./a{brk}FAIL D9: forged", repr(brk)[1:-1]
                with self.subTest(rel=rel, brk=shown):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source {source!r} does not resolve: "
                                                f"{base}a{shown}FAIL D9: forged is missing")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def point_vendored_entry(self, folder: str):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source=f"./{folder}"))

    def test_line_break_in_a_source_that_is_a_file_stays_on_1_line(self):
        self.write_text(f"plugin/{BROKEN}", "x")
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"does not resolve: plugin/{BROKEN_SHOWN} is not a directory")

    def test_line_break_in_a_symlinked_source_stays_on_1_line(self):
        os.symlink(self.root / "plugin/aiqt-guardrails-hooks", self.root / f"plugin/{BROKEN}")
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"does not resolve: plugin/{BROKEN_SHOWN} is a symlink")

    def test_line_break_in_a_source_in_another_letter_case_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json", manifest("aiqt-guardrails-hooks", "0.4.0"))
        self.point_vendored_entry(BROKEN.upper())
        with mock.patch.object(gate, "os", FoldingOs(self.root)):
            self.expect(1, f"does not resolve: plugin/{repr(BROKEN.upper())[1:-1]} is not spelled as its folder lists "
                           "it")

    def test_line_break_in_a_path_another_plugin_reaches_stays_on_1_line(self):
        self.write_json(f"{BROKEN}/.claude-plugin/plugin.json", manifest())
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source=f"./{BROKEN}"))
        self.expect(1, f"reaches {BROKEN_SHOWN}/.claude-plugin/plugin.json, not cleanlanguage/.claude-plugin/plugin.json")

    def test_line_break_in_a_manifest_path_of_the_names_check_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json", manifest("other", "0.4.0"))
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is 'aiqt-guardrails-hooks', "
                       f"but the manifest its source reaches, plugin/{BROKEN_SHOWN}/.claude-plugin/plugin.json, is "
                       "named 'other'")

    def test_line_break_in_a_manifest_path_of_the_dependencies_check_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json",
                        {**manifest("aiqt-guardrails-hooks", "0.4.0"), "dependencies": ["nope"]})
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"FAIL D4: plugin/{BROKEN_SHOWN}/.claude-plugin/plugin.json dependency 'nope' names no plugin")

    def test_line_break_in_an_unreadable_source_path_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json", manifest("aiqt-guardrails-hooks", "0.4.0"))
        self.point_vendored_entry(BROKEN)
        for kept, shown in ((0, f"plugin/{BROKEN_SHOWN}/.claude-plugin could not be read: Permission denied"),
                            (0o111, f"plugin/{BROKEN_SHOWN} could not be listed: Permission denied")):
            with self.subTest(kept=oct(kept)):
                with self.denied(f"plugin/{BROKEN}", kept):
                    self.expect(3, shown)

    def test_line_break_in_a_name_or_value_stays_on_1_line(self):
        for rel, change, needle in (
                (gate.MARKETPLACE, lambda d: d.update(name="clean\nlanguage"),
                 "FAIL D1: .claude-plugin/marketplace.json name is 'clean\\nlanguage', not 'cleanlanguage'"),
                (gate.VENDORED_MARKETPLACE, lambda d: d.update(name="claude-\nFAIL D9: x"),
                 "FAIL D1: plugin/.claude-plugin/marketplace.json name 'claude-\\nFAIL D9: x' starts with a reserved prefix"),
                (gate.AGENT_MANIFEST, lambda d: d.update(version="1.0.15\nFAIL D9: x"),
                 "cleanlanguage/plugin.json version '1.0.15\\nFAIL D9: x'"),
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["a\nFAIL D9: b"]),
                 "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependency 'a\\nFAIL D9: b' names no plugin"),
                (gate.VENDORED_MARKETPLACE, lambda d: (d.update(name="m\nFAIL D9: n"),
                                                       d["plugins"][0].update(dependencies=["x@y"])),
                 "names no plugin of the marketplace 'm\\nFAIL D9: n'")):
            with self.subTest(needle=needle):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    self.expect(1, needle)
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_reserved_prefix_in_each_name_fails_d1(self):
        # Each prefix in lower case, upper case and title case, and "anthropics-" with a long s, as a
        # marketplace name and as a plugin entry name in each marketplace. A vendored entry's manifest
        # takes the same name, so the prefix is the 1 failure there.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        spellings = [form for prefix in RESERVED_PREFIXES for form in (prefix, prefix.upper(), prefix.title())]
        spellings.append("anthropic\u017f-")
        for spelling in spellings:
            name = f"{spelling}x"
            for rel, label, change in (
                    (gate.MARKETPLACE, f"{gate.MARKETPLACE} name", lambda d: d.update(name=name)),
                    (gate.MARKETPLACE, f"{gate.MARKETPLACE} plugins[0].name", lambda d: d["plugins"][0].update(name=name)),
                    (gate.VENDORED_MARKETPLACE, f"{gate.VENDORED_MARKETPLACE} name", lambda d: d.update(name=name)),
                    (gate.VENDORED_MARKETPLACE, f"{gate.VENDORED_MARKETPLACE} plugins[0].name",
                     lambda d: d["plugins"][0].update(name=name))):
                with self.subTest(label=label, name=name):
                    saved = {path: (self.root / path).read_bytes() for path in (rel, hooks)}
                    self.edit_json(rel, change)
                    if label == f"{gate.VENDORED_MARKETPLACE} plugins[0].name":
                        self.edit_json(hooks, lambda d: d.update(name=name))
                    try:
                        output = self.expect(1, f"FAIL D1: {label} {name!r} starts with a reserved prefix")
                        if rel == gate.VENDORED_MARKETPLACE:
                            self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        for path, data in saved.items():
                            (self.root / path).write_bytes(data)

    def test_dependency_faults_fail_d4_in_each_place(self):
        # A dependency that names no plugin, is qualified with another marketplace or an empty one, or is
        # not a name, from an entry and from a plugin manifest of each marketplace.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        for rel, entry, label, plugin, market in (
                (gate.MARKETPLACE, True, ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage", "cleanlanguage"),
                (gate.CLAUDE_MANIFEST, False, gate.CLAUDE_MANIFEST, "cleanlanguage", "cleanlanguage"),
                (gate.VENDORED_MARKETPLACE, True, "plugin/.claude-plugin/marketplace.json plugins[0]",
                 "aiqt-guardrails-hooks", "aiqt-guardrails"),
                (hooks, False, hooks, "aiqt-guardrails-hooks", "aiqt-guardrails")):
            for dep, fault in (("no-such-plugin", "names no plugin"), (f"{plugin}@other", "names no plugin"),
                               (f"{plugin}@", "names no plugin"), ({"name": "x"}, "not a name"), ("", "not a name")):
                with self.subTest(label=label, dep=dep):
                    saved = (self.root / rel).read_bytes()
                    if entry:
                        self.edit_json(rel, lambda d: d["plugins"][0].update(dependencies=[dep]))
                    else:
                        self.edit_json(rel, lambda d: d.update(dependencies=[dep]))
                    if fault == "names no plugin":
                        needle = f"FAIL D4: {label} dependency {dep!r} names no plugin of the marketplace {market!r}"
                    else:
                        needle = f"FAIL D4: {label} names the dependency {dep!r}, not a plugin name"
                    try:
                        output = self.expect(1, needle, "1 dependency read")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_repository_plugins_not_a_list_fails_d1_and_d2(self):
        # A missing plugins list and an object in its place: the FAIL lines, never a traceback.
        for change in (lambda d: d.pop("plugins"), lambda d: d.update(plugins={"name": "cleanlanguage"})):
            with self.subTest(change=change):
                self.write_json(gate.MARKETPLACE, marketplace())
                self.edit_json(gate.MARKETPLACE, change)
                output = self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists no plugins, not exactly 1",
                                     "FAIL D2: .claude-plugin/marketplace.json has no plugins list")
                self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_repository_entry_that_is_a_string_fails_d1_and_d2(self):
        # A string that holds "version": the versions check reads only an entry that is an object.
        self.edit_json(gate.MARKETPLACE, lambda d: d.update(plugins=["version"]))
        output = self.expect(1, "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is None, not 'cleanlanguage'",
                             "FAIL D2: .claude-plugin/marketplace.json plugins[0] is not a JSON object")
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_empty_name_listed_twice_fails_d1_once_each(self):
        # 2 entries named "", whose manifest is named "" too: each is not a name, and neither is a plugin
        # listed a second time.
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json", lambda d: d.update(name=""))
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(plugins=[
            {"name": "", "source": "./aiqt-guardrails-hooks"}, {"name": "", "source": "./aiqt-guardrails-hooks"}]))
        output = self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is '', not a name",
                             "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[1].name is '', not a name")
        self.assertNotIn("a second time", output)
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_input_folder_that_is_a_file_exits_3(self):
        shutil.rmtree(self.root / "site-src")
        self.write_text("site-src", "x\n")
        self.expect(3, "site-src/site.json could not be read: the component 'site-src' is not a directory")

    def test_os_error_is_shown_by_its_strerror_or_its_message(self):
        # At each place the gate turns an OSError into a refusal: an OSError with no strerror, as one built
        # by hand has, is shown by its message; a fault while a file is read, by its strerror alone.
        with mock.patch.object(gate, "os", FaultyOs("read", None, errno.EIO, "Input/output error")):
            self.expect(3, "check-plugin-distribution: .claude-plugin/marketplace.json could not be read: "
                           "Input/output error\nUNREADABLE: exit 3\n")
        for name, marker, number, code, line in (
                ("lstat", "site-src", None, 3, "site-src/site.json could not be read: no text"),
                ("listdir", "site-src", None, 3, "site-src/site.json could not be read: no text"),
                ("open", "site-src", None, 3, "site-src/site.json could not be read: no text"),
                ("fstat", None, None, 3, ".claude-plugin/marketplace.json could not be read: no text"),
                ("read", None, None, 3, ".claude-plugin/marketplace.json could not be read: no text"),
                ("lstat", "aiqt-guardrails-hooks", None, 3, "plugin/aiqt-guardrails-hooks could not be read: no text"),
                ("listdir", "aiqt-guardrails-hooks", None, 3,
                 "plugin/aiqt-guardrails-hooks could not be listed: no text"),
                ("lstat", "aiqt-guardrails-hooks", errno.ENAMETOOLONG, 1,
                 "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' is not "
                 "a path the operating system accepts: no text")):
            with self.subTest(name=name, marker=marker, number=number):
                with mock.patch.object(gate, "os", FaultyOs(name, marker, number)):
                    if code == 3:
                        self.expect(3, f"check-plugin-distribution: {line}\nUNREADABLE: exit 3\n")
                    else:
                        self.expect(1, f"{line}\n", count=1)

    def test_os_error_whose_strerror_or_message_misbehaves_is_shown_guarded(self):
        # At each place the gate shows an OSError, in a refusal or in a FAIL line: a strerror made by code
        # that prints, a strerror whose own methods raise, a strerror whose making, through its str or
        # its truth value, raises an exception of each class, a message made by code that prints, and a
        # message whose making raises an exception of each class.
        loud_text = type("LoudText", (str,), {"__str__": loud("loud")})
        for name, marker, number, code, line in (
                ("lstat", "site-src", None, 3, "site-src/site.json could not be read: "),
                ("listdir", "site-src", None, 3, "site-src/site.json could not be read: "),
                ("open", "site-src", None, 3, "site-src/site.json could not be read: "),
                ("fstat", None, None, 3, ".claude-plugin/marketplace.json could not be read: "),
                ("read", None, None, 3, ".claude-plugin/marketplace.json could not be read: "),
                ("lstat", "aiqt-guardrails-hooks", None, 3, "plugin/aiqt-guardrails-hooks could not be read: "),
                ("listdir", "aiqt-guardrails-hooks", None, 3, "plugin/aiqt-guardrails-hooks could not be listed: "),
                ("lstat", "aiqt-guardrails-hooks", errno.ENAMETOOLONG, 1,
                 "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' is not "
                 "a path the operating system accepts: ")):
            def with_message(method, number=number):
                # An OSError subclass with no strerror, whose __str__ is method.
                def make():
                    error = type("Misbehaving", (OSError,), {"__str__": method})("no text")
                    error.errno = number
                    return error
                return make

            kinds = [("loud strerror", lambda number=number: OSError(number, loud_text("x")), "loud"),
                     ("hooked strerror", lambda number=number: OSError(number, HookedText("x")), UNSHOWN_MESSAGE),
                     ("loud message", with_message(loud("loud")), "loud")]
            kinds += [(f"message raising {raised.__name__}", with_message(raising(raised)), UNSHOWN_MESSAGE)
                      for raised in RAISED]
            for method in ("__str__", "__bool__"):
                # A strerror that is no str, whose str or whose truth value raises.
                kinds += [(f"strerror whose {method} raises {raised.__name__}",
                           lambda number=number, method=method, raised=raised: OSError(
                               number, type("Unshowable", (), {method: raising(raised)})()), UNSHOWN_MESSAGE)
                          for raised in RAISED]
            for kind, make, shown in kinds:
                with self.subTest(name=name, marker=marker, number=number, kind=kind):
                    with mock.patch.object(gate, "os", FaultyOs(name, marker, error=make)):
                        if code == 3:
                            output = self.expect(3, f"check-plugin-distribution: {line}{shown}\nUNREADABLE: exit 3\n")
                        else:
                            output = self.expect(1, f"{line}{shown}\n", count=1)
                    self.assertNotIn("D9", output)

    def test_os_error_whose_errno_misbehaves_is_read_guarded(self):
        # At each place the gate meets an OSError: an errno read by code that prints, an errno that is an
        # int subclass whose own methods print and raise, an errno whose reading raises an exception of
        # each class, and an errno that is not an int. The first 2 are read as their int; the others are
        # no errno, so a source name too long for the operating system then stops the gate as any other
        # fault of a source folder does.
        def shout(*args):
            print("FAIL D9: forged")
            print("UNREADABLE: exit 3", file=sys.stderr)
            raise SystemExit(0)

        class LoudNumber(int):
            __eq__ = __ne__ = __index__ = __int__ = shout
            __hash__ = int.__hash__

        def numbered(read):
            # An OSError subclass with the strerror x, whose errno is read through read.
            return lambda: type("Numbered", (OSError,), {"errno": property(read)})(None, "x")

        def loud_number(value):
            def read(self):
                print("FAIL D9: forged")
                print("UNREADABLE: exit 3", file=sys.stderr)
                return value
            return read

        too_long = ("FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' is "
                    "not a path the operating system accepts: x")
        for name, marker, number, line in (
                ("lstat", "site-src", errno.EIO, "site-src/site.json could not be read: x"),
                ("listdir", "site-src", errno.EIO, "site-src/site.json could not be read: x"),
                ("open", "site-src", errno.EIO, "site-src/site.json could not be read: x"),
                ("fstat", None, errno.EIO, ".claude-plugin/marketplace.json could not be read: x"),
                ("read", None, errno.EIO, ".claude-plugin/marketplace.json could not be read: x"),
                ("lstat", "aiqt-guardrails-hooks", errno.EIO, "plugin/aiqt-guardrails-hooks could not be read: x"),
                ("listdir", "aiqt-guardrails-hooks", errno.EIO, "plugin/aiqt-guardrails-hooks could not be listed: x"),
                ("lstat", "aiqt-guardrails-hooks", errno.ENAMETOOLONG,
                 "plugin/aiqt-guardrails-hooks could not be read: x")):
            # What an errno read as its int gives: the FAIL line of a name too long, or the refusal.
            read_as_int = (1, too_long) if number == errno.ENAMETOOLONG else (3, line)
            kinds = [("errno read by code that prints", numbered(loud_number(number)), read_as_int),
                     ("errno an int subclass whose methods print and raise",
                      numbered(lambda self, number=number: LoudNumber(number)), read_as_int),
                     ("errno that is not an int", numbered(lambda self, number=number: float(number)), (3, line))]
            kinds += [(f"errno raising {raised.__name__}", numbered(raising(raised)), (3, line)) for raised in RAISED]
            for kind, make, (code, shown) in kinds:
                with self.subTest(name=name, marker=marker, number=number, kind=kind):
                    with mock.patch.object(gate, "os", FaultyOs(name, marker, error=make)):
                        if code == 3:
                            output = self.expect(3, f"check-plugin-distribution: {shown}\nUNREADABLE: exit 3\n")
                        else:
                            output = self.expect(1, f"{shown}\n", count=1)
                    self.assertNotIn("D9", output)

    def test_decoding_error_whose_message_misbehaves_is_shown_guarded(self):
        # The UnicodeError of a JSON input, the ValueError of json.loads and the UnicodeDecodeError of
        # SKILL.md, each with a message made by code that prints or whose making raises an exception of
        # each class.
        read_bytes = gate.read_bytes

        def undecodable(make):
            # site.json read as bytes whose decode raises.
            class Undecodable(bytes):
                def decode(self, *args, **kwargs):
                    raise make()

            def read(rel):
                data = read_bytes(rel)
                return Undecodable(data) if rel == gate.SITE_JSON else data
            return mock.patch.object(gate, "read_bytes", read)

        def undecoded(make):
            def loads(*args, **kwargs):
                raise make()
            return mock.patch.object(gate, "json", Replaced(json, loads=loads))

        def unread(make):
            class Reader:
                def __init__(self, *args, **kwargs):
                    pass

                def read(self):
                    raise make()
            return mock.patch.object(gate, "io", Replaced(io, TextIOWrapper=Reader))

        kinds = [("prints", loud("loud"), "loud")]
        kinds += [(f"raises {raised.__name__}", raising(raised), UNSHOWN_MESSAGE) for raised in RAISED]
        for patch, base, args, line in (
                (undecodable, UnicodeError, (), "site-src/site.json is not UTF-8: "),
                (undecoded, ValueError, (), ".claude-plugin/marketplace.json could not be decoded as JSON: "),
                (unread, UnicodeDecodeError, ("utf-8", b"\xff", 0, 1, "invalid start byte"),
                 "cleanlanguage/skills/cleanlanguage/SKILL.md is not UTF-8: ")):
            for kind, method, shown in kinds:
                cls = type("Misbehaving", (base,), {"__str__": method})
                with self.subTest(error=base.__name__, kind=kind):
                    with patch(lambda: cls(*args)):
                        output = self.expect(3, f"check-plugin-distribution: {line}{shown}\nUNREADABLE: exit 3\n")
                    self.assertNotIn("D9", output)

    def test_skill_line_endings_pass(self):
        # Universal newlines: CR LF and a lone CR each end a line as LF does.
        text = f"---\nname: cleanlanguage\n---\n\n# Clean Language\n\nVersion: {VERSION}  \nReleased: 2026-11-08\n"
        for ending in ("\r\n", "\r"):
            with self.subTest(ending=repr(ending)):
                (self.root / gate.SKILL_MD).write_bytes(text.replace("\n", ending).encode("utf-8"))
                self.expect(0, f"at version {VERSION}")

    def test_vendored_entry_versions_are_not_read(self):
        # Other plugins, with versions of their own: neither compared nor required to be a string.
        for version in ("0.4.0", 1, ""):
            with self.subTest(version=version):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(version=version))
                self.expect(0, "OK: D1 to D4 hold")

    def test_one_line_escapes_every_character_str_isprintable_refuses(self):
        # Every code point: one str.isprintable accepts is kept, any other is written as its backslash
        # escape, and the result is printable, so it is 1 line.
        wrong = []
        for point in range(sys.maxunicode + 1):
            char = chr(point)
            want = char if char.isprintable() else repr(char)[1:-1]
            got = gate.one_line(f"a{char}b")
            if got != f"a{want}b" or not got.isprintable():
                wrong.append(hex(point))
        self.assertEqual(wrong, [])

    def test_every_line_is_printed_through_emit(self):
        # No print call and no write or writelines call outside emit, which prints through one_line.
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        emit = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "emit")
        inside = {id(node) for node in ast.walk(emit)}
        outside = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and id(node) not in inside
                   and ((isinstance(node.func, ast.Name) and node.func.id == "print")
                        or (isinstance(node.func, ast.Attribute) and node.func.attr in ("write", "writelines")))]
        self.assertEqual(outside, [])

    def test_message_that_cannot_be_shown_exits_3_on_1_line(self):
        # A message whose __str__ raises an exception of each class: every exception class of builtins
        # and 2 of this test's own. In an exception that stops the gate and in a refusal of the gate.
        for raised in RAISED:
            class Unshowable(Exception):
                def __str__(self, raised=raised):
                    raise built(raised)

            for error, cause in ((Unshowable(), f"the gate stopped on Unshowable: {UNSHOWN_MESSAGE}"),
                                 (gate.Unreadable(Unshowable()), UNSHOWN_MESSAGE)):
                with self.subTest(raised=raised.__name__, error=type(error).__name__):
                    with mock.patch.object(gate, "check_versions", side_effect=error):
                        self.expect(3, f"check-plugin-distribution: {cause}\nUNREADABLE: exit 3\n")

    def test_type_name_that_cannot_be_shown_exits_3_on_1_line(self):
        # An exception that stops the gate, whose type's metaclass makes __name__ raise an exception of
        # each class, among them an instance of that type itself.
        for raised in (*RAISED, None):
            class Meta(type):
                @property
                def __name__(cls, raised=raised):
                    raise built(raised) if raised else cls("again")

            class Hidden(Exception, metaclass=Meta):
                pass

            with self.subTest(raised=raised and raised.__name__):
                with mock.patch.object(gate, "check_versions", side_effect=Hidden("x")):
                    self.expect(3, f"check-plugin-distribution: the gate stopped on {UNSHOWN_NAME}: x\n"
                                   "UNREADABLE: exit 3\n")

    def test_name_or_message_made_by_code_that_prints_or_gives_no_plain_str_exits_3(self):
        # The type name and the message of an exception that stops the gate, and the message of a refusal:
        # made by code that prints to standard output and standard error, that gives a str subclass whose
        # own methods raise, or, for the name, that gives no str.
        class Loud(Exception):
            def __str__(self):
                print("FAIL D9: forged")
                print("UNREADABLE: exit 3", file=sys.stderr)
                return "loud"

        class LoudMeta(type):
            @property
            def __name__(cls):
                print("FAIL D9: forged")
                print("UNREADABLE: exit 3", file=sys.stderr)
                return "Named"

        class Hooked(str):
            def __format__(self, spec):
                raise SystemExit(0)

            def __iter__(self):
                raise SystemExit(0)

            def __str__(self):
                raise SystemExit(0)

        class HookedMessage(Exception):
            def __str__(self):
                return Hooked("hooked")

        class HookedMeta(type):
            @property
            def __name__(cls):
                return Hooked("Named")

        class NumberMeta(type):
            @property
            def __name__(cls):
                return 42

        loud_name = LoudMeta("LoudName", (Exception,), {})
        hooked_name = HookedMeta("HookedName", (Exception,), {})
        number_name = NumberMeta("NumberName", (Exception,), {})
        for error, cause in ((Loud(), "the gate stopped on Loud: loud"),
                             (gate.Unreadable(Loud()), "loud"),
                             (loud_name("x"), "the gate stopped on Named: x"),
                             (HookedMessage(), "the gate stopped on HookedMessage: hooked"),
                             (gate.Unreadable(HookedMessage()), "hooked"),
                             (hooked_name("x"), "the gate stopped on Named: x"),
                             (number_name("x"), f"the gate stopped on {UNSHOWN_NAME}: x")):
            with self.subTest(cause=cause):
                with mock.patch.object(gate, "check_versions", side_effect=error):
                    output = self.expect(3, f"check-plugin-distribution: {cause}\nUNREADABLE: exit 3\n")
                self.assertNotIn("D9", output)

    def test_extractor_exception_whose_name_or_message_misbehaves_exits_3(self):
        # The extractor raises, while it loads, an exception whose type name raises an instance of that
        # type, whose message raises GeneratorExit, or whose message prints.
        meta = ("class Meta(type):\n    @property\n    def __name__(cls):\n        raise cls('again')\n"
                "class Hidden(Exception, metaclass=Meta):\n    pass\nraise Hidden('x')")
        unshowable = ("class Unshowable(Exception):\n    def __str__(self):\n        raise GeneratorExit\n"
                      "raise Unshowable()")
        loud = ("import sys\nclass Loud(Exception):\n    def __str__(self):\n        print('FAIL D9: forged')\n"
                "        print('UNREADABLE: exit 3', file=sys.stderr)\n        return 'loud'\nraise Loud()")
        for statement, shown in ((meta, f"{UNSHOWN_NAME}: x"), (unshowable, f"Unshowable: {UNSHOWN_MESSAGE}"),
                                 (loud, "Loud: loud")):
            with self.subTest(shown=shown):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor('PROG = "skill-version"\n', f'PROG = "skill-version"\n{statement}\n')
                output = self.expect(3, f"check-plugin-distribution: the extractor tools/skill-version.py could not be "
                                        f"loaded: {shown}\nUNREADABLE: exit 3\n")
                self.assertNotIn("D9", output)

    def test_loading_a_gate_that_raises_stops_the_test(self):
        # A copy of this test beside a copy of the gate that raises, while it loads, an exception whose
        # message raises SystemExit(0), whose type name raises SystemExit(0), whose message prints, whose
        # type name is not a str, or whose message or type name is a str subclass whose own methods raise
        # SystemExit(0).
        tools = self.root / "tools"
        test = tools / Path(__file__).name
        shutil.copyfile(Path(__file__).resolve(), test)
        copy = tools / MODULE_PATH.name
        hooked = ("class Hooked(str):\n    def __format__(self, spec):\n        raise SystemExit(0)\n"
                  "    def __iter__(self):\n        raise SystemExit(0)\n    def __str__(self):\n        raise SystemExit(0)\n")
        for statement, shown in (
                (hooked + "class Raised(Exception):\n    def __str__(self):\n        return Hooked('hooked')\n"
                 "raise Raised()", "Raised: hooked"),
                (hooked + "class Meta(type):\n    @property\n    def __name__(cls):\n        return Hooked('Named')\n"
                 "class Raised(Exception, metaclass=Meta):\n    pass\nraise Raised('x')", "Named: x"),
                ("class Raised(Exception):\n    def __str__(self):\n        raise SystemExit(0)\nraise Raised()",
                 f"Raised: {UNSHOWN_MESSAGE}"),
                ("class Meta(type):\n    @property\n    def __name__(cls):\n        raise SystemExit(0)\n"
                 "class Raised(Exception, metaclass=Meta):\n    pass\nraise Raised('x')", f"{UNSHOWN_NAME}: x"),
                ("class Raised(Exception):\n    def __str__(self):\n        print('printed')\n        return 'loud'\n"
                 "raise Raised()", "Raised: loud"),
                ("class Meta(type):\n    @property\n    def __name__(cls):\n        return 42\n"
                 "class Raised(Exception, metaclass=Meta):\n    pass\nraise Raised('x')", f"{UNSHOWN_NAME}: x")):
            with self.subTest(shown=shown):
                copy.write_text(MODULE_PATH.read_text(encoding="utf-8") + f"\n{statement}\n", encoding="utf-8")
                done = subprocess.run([sys.executable, "-I", str(test), *LOADED_ONLY], cwd=self.root,
                                      capture_output=True, text=True, errors="backslashreplace", timeout=120)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertEqual(done.stdout, "", done.stdout + done.stderr)
                self.assertEqual(done.stderr, f"loading {copy.resolve()} raised {shown}\n", done.stdout + done.stderr)

    def test_loading_a_gate_that_prints_stops_the_test(self):
        # A copy of this test beside a copy of the gate that, while it loads, raises nothing and prints
        # to standard output or to standard error.
        tools = self.root / "tools"
        test = tools / Path(__file__).name
        shutil.copyfile(Path(__file__).resolve(), test)
        copy = tools / MODULE_PATH.name
        printed = repr("printed\n")
        for statement in ("print('printed')", "import sys\nprint('printed', file=sys.stderr)"):
            with self.subTest(statement=statement):
                copy.write_text(MODULE_PATH.read_text(encoding="utf-8") + f"\n{statement}\n", encoding="utf-8")
                done = subprocess.run([sys.executable, "-I", str(test), *LOADED_ONLY], cwd=self.root,
                                      capture_output=True, text=True, errors="backslashreplace", timeout=120)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertEqual(done.stdout, "", done.stdout + done.stderr)
                self.assertEqual(done.stderr, f"loading {copy.resolve()} printed {printed}\n", done.stdout + done.stderr)

    def test_loader_helper_gives_a_plain_str_or_the_stand_in(self):
        # The helper the loader makes a name and a message with: a str subclass whose own methods raise
        # comes back a str of its own type, what the making prints is dropped, and making that raises an
        # exception of each class gives the stand-in.
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            hooked = _made(lambda: HookedText("hooked"), "stand-in")
            printed = _made(lambda: (print("printed"), print("printed", file=sys.stderr), "loud")[-1], "stand-in")
        self.assertIs(type(hooked), str)
        self.assertEqual(hooked, "hooked")
        self.assertEqual(printed, "loud")
        self.assertEqual(out.getvalue() + err.getvalue(), "")
        escaped = []
        for raised in RAISED:
            def make(raised=raised):
                raise built(raised)
            try:
                if _made(make, "stand-in") != "stand-in":
                    escaped.append(raised.__name__)
            except BaseException:
                escaped.append(raised.__name__)
        self.assertEqual(escaped, [])

    def test_emit_writes_each_character_as_one_line_does(self):
        # Every code point in 1 line given to emit, printed to standard output and to a stream given.
        text = "".join(chr(point) for point in range(sys.maxunicode + 1))
        want = "".join(char if char.isprintable() else repr(char)[1:-1] for char in text) + "\n"
        out, given = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out):
            gate.emit(text)
        gate.emit(text, given)
        for name, got in (("standard output", out.getvalue()), ("the stream given", given.getvalue())):
            with self.subTest(stream=name):
                first = next((index for index, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
                self.assertTrue(got == want, f"emit wrote {got[first:first + 20]!r} at index {first}, not "
                                             f"{want[first:first + 20]!r}")

    def test_dependency_part_in_another_letter_case_fails_d4(self):
        # NAME, and the marketplace of NAME@<marketplace name>, in another letter case, from an entry and
        # from the manifest its source reaches, in each marketplace.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        self.add_vendored("aiqt-skill")
        for rel, entry, label, market, deps in (
                (gate.MARKETPLACE, True, ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage",
                 ("CleanLanguage", "cleanlanguage@CleanLanguage")),
                (gate.CLAUDE_MANIFEST, False, gate.CLAUDE_MANIFEST, "cleanlanguage",
                 ("CleanLanguage", "cleanlanguage@CleanLanguage")),
                (gate.VENDORED_MARKETPLACE, True, "plugin/.claude-plugin/marketplace.json plugins[0]",
                 "aiqt-guardrails", ("AIQT-SKILL", "aiqt-skill@AIQT-Guardrails")),
                (hooks, False, hooks, "aiqt-guardrails", ("AIQT-SKILL", "aiqt-skill@AIQT-Guardrails"))):
            for dep in deps:
                with self.subTest(label=label, dep=dep):
                    saved = (self.root / rel).read_bytes()
                    if entry:
                        self.edit_json(rel, lambda d: d["plugins"][0].update(dependencies=[dep]))
                    else:
                        self.edit_json(rel, lambda d: d.update(dependencies=[dep]))
                    try:
                        self.expect(1, f"FAIL D4: {label} dependency {dep!r} names no plugin of the marketplace "
                                       f"{market!r}", "1 dependency read", count=1)
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_entry_and_manifest_names_in_another_letter_case_fail_d1(self):
        # A vendored entry and the manifest its source reaches, named alike but for letter case, each way
        # round; and the repository's entry named so, where the project name differs too.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        for entry_name, manifest_name in (("AIQT-Guardrails-Hooks", "aiqt-guardrails-hooks"),
                                          ("aiqt-guardrails-hooks", "AIQT-Guardrails-Hooks")):
            with self.subTest(entry=entry_name, manifest=manifest_name):
                saved = {path: (self.root / path).read_bytes() for path in (gate.VENDORED_MARKETPLACE, hooks)}
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(name=entry_name))
                self.edit_json(hooks, lambda d: d.update(name=manifest_name))
                try:
                    self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is "
                                   f"{entry_name!r}, but the manifest its source reaches, {hooks}, is named "
                                   f"{manifest_name!r}", count=1)
                finally:
                    for path, data in saved.items():
                        (self.root / path).write_bytes(data)
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(name="CleanLanguage"))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is 'CleanLanguage', but the manifest "
                       "its source reaches, cleanlanguage/.claude-plugin/plugin.json, is named 'cleanlanguage'",
                    count=2)

    @contextlib.contextmanager
    def swapped(self, rel: str, swap):
        """rel replaced by swap(path) after the gate's walk reaches it and before the gate opens it."""
        walk = gate.walk

        def walk_then_swap(name):
            path = walk(name)
            if name == rel:
                swap(path)
            return path
        with mock.patch.object(gate, "walk", walk_then_swap):
            yield

    def test_input_file_swapped_for_a_symlink_after_the_walk_exits_3(self):
        # A symlink to a copy of the same file, so that following it would read a conforming site.json.
        copy = self.root / "site.json.copy"
        shutil.copyfile(self.root / gate.SITE_JSON, copy)

        def to_symlink(path):
            path.unlink()
            os.symlink(copy, path)
        with self.swapped(gate.SITE_JSON, to_symlink):
            self.expect(3, f"check-plugin-distribution: site-src/site.json could not be read: "
                           f"{os.strerror(errno.ELOOP)}\nUNREADABLE: exit 3\n")

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(signal, "SIGALRM"), "needs os.mkfifo and signal.SIGALRM")
    def test_input_file_swapped_for_a_fifo_after_the_walk_exits_3(self):
        # A FIFO that no process writes to. An alarm 5 s on raises in an open that waits for a writer.
        class Alarm(Exception):
            pass

        def ring(signum, frame):
            raise Alarm("the open waited 5 s for a writer")

        def to_fifo(path):
            path.unlink()
            os.mkfifo(path)
        previous = signal.signal(signal.SIGALRM, ring)
        try:
            signal.alarm(5)
            with self.swapped(gate.SITE_JSON, to_fifo):
                self.expect(3, "check-plugin-distribution: site-src/site.json could not be read: it is not a regular "
                               "file\nUNREADABLE: exit 3\n")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    def test_entry_version_that_is_null_fails_d3(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(version=None))
        self.expect(1, "FAIL D3: .claude-plugin/marketplace.json plugins[0].version is None, not a version", count=1)

    def test_dependency_in_another_letter_case_fails_d4(self):
        # In another letter case a dependency names no plugin, also where it would name the plugin itself.
        self.add_vendored("aiqt-skill")
        for rel, dep, label, market in (
                (gate.VENDORED_MARKETPLACE, "AIQT-SKILL", "plugin/.claude-plugin/marketplace.json plugins[0]",
                 "aiqt-guardrails"),
                (gate.MARKETPLACE, "CleanLanguage", ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage")):
            with self.subTest(dep=dep):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(dependencies=[dep]))
                try:
                    self.expect(1, f"FAIL D4: {label} dependency {dep!r} names no plugin of the marketplace "
                                   f"{market!r}", count=1)
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_dependency_on_its_own_name_in_another_letter_case_is_not_the_plugin_itself(self):
        # A list whose entry is named like the plugin entry its dependency names, but for letter case: the
        # list of that entry and of the manifest its source reaches, in each marketplace. The names check
        # counts the failures each setup has of its own; no dependency fails.
        upper = "plugin/aiqt-skill-upper/.claude-plugin/plugin.json"
        self.add_vendored("aiqt-skill")
        self.write_json(upper, manifest("AIQT-SKILL", "0.4.0"))
        self.write_json("cleanlanguage-upper/.claude-plugin/plugin.json", manifest("CleanLanguage"))
        for changes, count in (
                ([(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"].append(
                    {"name": "AIQT-SKILL", "source": "./aiqt-skill-upper", "dependencies": ["aiqt-skill"]}))], 1),
                ([(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"].append(
                    {"name": "AIQT-SKILL", "source": "./aiqt-skill-upper"})),
                  (upper, lambda d: d.update(dependencies=["aiqt-skill"]))], 1),
                ([(gate.MARKETPLACE, lambda d: d["plugins"].append(
                    {"name": "CleanLanguage", "source": "./cleanlanguage", "dependencies": ["cleanlanguage"]}))], 3),
                # The second entry reaches a manifest other than the plugin's, which the sources check counts.
                ([(gate.MARKETPLACE, lambda d: d["plugins"].append(
                    {"name": "CleanLanguage", "source": "./cleanlanguage-upper"})),
                  ("cleanlanguage-upper/.claude-plugin/plugin.json", lambda d: d.update(dependencies=["cleanlanguage"]))],
                 3)):
            with self.subTest(rels=[rel for rel, _ in changes]):
                saved = {rel: (self.root / rel).read_bytes() for rel, _ in changes}
                for rel, change in changes:
                    self.edit_json(rel, change)
                try:
                    output = self.expect(1, "1 dependency read", count=count)
                    self.assertNotIn("FAIL D4", output)
                finally:
                    for rel, data in saved.items():
                        (self.root / rel).write_bytes(data)

    def test_manifest_list_belongs_to_the_entry_its_source_reaches(self):
        # The manifest a source reaches, named unlike its entry, in each marketplace: a dependency on that
        # entry, by its name alone and with the marketplace, names the plugin itself; a dependency on the
        # manifest's own name, which is another plugin entry, does not. The names check reports each
        # manifest named unlike its entry.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        claude = gate.CLAUDE_MANIFEST
        self.add_vendored("aiqt-skill")
        self.write_json("helper/.claude-plugin/plugin.json", manifest("helper"))
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append({"name": "helper", "source": "./helper"}))
        # The setup's own failures: 2 repository entries, and the second reaching another manifest.
        setup = 2
        for rel, name, dep, entry, itself in (
                (hooks, "AIQT-Guardrails-Hooks", "aiqt-guardrails-hooks", "aiqt-guardrails-hooks", True),
                (hooks, "other-name", "aiqt-guardrails-hooks@aiqt-guardrails", "aiqt-guardrails-hooks", True),
                (hooks, "aiqt-skill", "aiqt-skill", "aiqt-guardrails-hooks", False),
                (claude, "CleanLanguage", "cleanlanguage", "cleanlanguage", True),
                (claude, "other-name", "cleanlanguage@cleanlanguage", "cleanlanguage", True),
                (claude, "helper", "helper", "cleanlanguage", False)):
            with self.subTest(rel=rel, name=name, dep=dep):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d.update(name=name, dependencies=[dep]))
                market = gate.MARKETPLACE if rel == claude else gate.VENDORED_MARKETPLACE
                # The manifest named unlike its entry, and for the plugin's own manifest, unlike the project.
                count = setup + 1 + (rel == claude) + itself
                try:
                    output = self.expect(1, f"FAIL D1: {market} plugins[0].name is {entry!r}, but the manifest its "
                                            f"source reaches, {rel}, is named {name!r}", "1 dependency read",
                                         count=count)
                    line = f"FAIL D4: {rel} dependency {dep!r} names the plugin itself, which this gate refuses"
                    if itself:
                        self.assertIn(line, output)
                    else:
                        self.assertNotIn("FAIL D4", output)
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_dependencies_named_alike_but_for_letter_case_are_not_a_second_time(self):
        # 2 plugin entries named alike but for letter case in each marketplace, which the names check
        # refuses; a list that names both, from an entry and from the manifest its source reaches, in
        # each marketplace, names 2 plugins, so no dependency fails.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        self.add_vendored("aiqt-skill")
        self.write_json("plugin/aiqt-skill-upper/.claude-plugin/plugin.json", manifest("AIQT-SKILL", "0.4.0"))
        self.edit_json(gate.VENDORED_MARKETPLACE,
                       lambda d: d["plugins"].append({"name": "AIQT-SKILL", "source": "./aiqt-skill-upper"}))
        self.write_json("helper/.claude-plugin/plugin.json", manifest("helper"))
        self.write_json("helper-upper/.claude-plugin/plugin.json", manifest("HELPER"))
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].extend(
            [{"name": "helper", "source": "./helper"}, {"name": "HELPER", "source": "./helper-upper"}]))
        # The setup's own failures: a second listing in each marketplace, 3 repository entries and 2 of
        # them reaching a manifest other than the plugin's.
        self.expect(1, "6 relative sources resolved, 0 dependencies read", count=5)
        for rel, entry, deps in ((gate.VENDORED_MARKETPLACE, True, ["aiqt-skill", "AIQT-SKILL"]),
                                 (hooks, False, ["aiqt-skill", "AIQT-SKILL"]),
                                 (gate.MARKETPLACE, True, ["helper", "HELPER"]),
                                 (gate.CLAUDE_MANIFEST, False, ["helper", "HELPER"])):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                if entry:
                    self.edit_json(rel, lambda d: d["plugins"][0].update(dependencies=deps))
                else:
                    self.edit_json(rel, lambda d: d.update(dependencies=deps))
                try:
                    output = self.expect(1, "6 relative sources resolved, 2 dependencies read", count=5)
                    self.assertNotIn("FAIL D4", output)
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_count_lines_read_for_0(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d.update(plugins=[]))
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(plugins=[]))
        self.expect(1, "check-plugin-distribution: 0 relative sources resolved, 0 dependencies read\n")

    def test_json_the_decoder_refuses_exits_3(self):
        # Valid JSON past a limit of the decoder: an integer of 5000 digits.
        self.write_text(gate.SITE_JSON, '{"schema": ' + "9" * 5000 + ', "site_key": "cleanlanguage"}\n')
        self.expect(3, "check-plugin-distribution: site-src/site.json could not be decoded as JSON: ")

    def test_gate_runs_as_a_command(self):
        # A copy of the gate in the tree, so its REPO_ROOT is the tree, run as CI runs it.
        script = self.root / "tools" / "check-plugin-distribution.py"
        shutil.copyfile(MODULE_PATH, script)

        def command():
            done = subprocess.run([sys.executable, "-I", str(script)], cwd=self.root, capture_output=True,
                                  text=True, errors="backslashreplace", timeout=120)
            return done.returncode, done.stdout, done.stderr

        code, out, err = command()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.splitlines()[-1].startswith("OK: D1 to D4 hold"), out + err)
        self.assert_lines(code, out, err)
        self.edit_json(gate.SITE_JSON, lambda d: d.update(site_key="jposluns"))
        code, out, err = command()
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAIL D1: site-src/site.json site_key is 'jposluns', not 'cleanlanguage'\n", out)
        self.assertEqual(out.splitlines()[-1], "FAIL: 1 inconsistency")
        self.assert_lines(code, out, err)
        # A missing source whose path holds a line break and a lone surrogate, which printed raw is no
        # UTF-8 text: 1 FAIL line, with both written as escapes.
        self.write_json(gate.SITE_JSON, {"schema": 1, "site_key": "cleanlanguage"})
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source="./a\nFAIL D9: \udcff"))
        code, out, err = command()
        self.assertEqual(code, 1, out + err)
        self.assertIn("does not resolve: plugin/a\\nFAIL D9: \\udcff is missing\n", out)
        self.assert_lines(code, out, err)
        self.write_json(gate.VENDORED_MARKETPLACE, vendored())
        (self.root / gate.SITE_JSON).unlink()
        code, out, err = command()
        self.assertEqual(code, 3, out + err)
        self.assertIn("site-src/site.json could not be read", err)
        self.assertEqual(err.splitlines()[-1], "UNREADABLE: exit 3")
        self.assert_lines(code, out, err)


class RepositoryTreeTest(unittest.TestCase):
    def test_repository_is_consistent(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gate.main()
        output = out.getvalue() + err.getvalue()
        self.assertEqual(code, 0, output)
        self.assertTrue(out.getvalue().splitlines()[-1].startswith("OK: D1 to D4 hold"), output)
        self.assertNotIn("FAIL", output)


if __name__ == "__main__":
    unittest.main()
