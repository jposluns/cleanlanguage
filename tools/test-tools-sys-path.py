#!/usr/bin/env python3
"""Check that no tools/*.py script refers to the module search path.

Threat model: honest drift. A script that puts a folder on sys.path, ahead of
the standard library or after it, lets a file in that folder stand in for a
module: inserted first, a planted tempfile.py replaces the standard one;
appended last, a planted msvcrt.py runs on Linux, whose standard library lacks
that module. `python3 -I` keeps the script folder off sys.path, so a script
that adds a folder back undoes it. The gate guards against an honest author
who does so by mistake; deliberate evasion is a named residual.

The rule, over the syntax tree of every tools/*.py file, so string literals,
docstrings and comments are not read:

1. Any reference, read or write, to sys.path, sys.meta_path, sys.path_hooks or
   sys.path_importer_cache is a finding, including a keyword of one of those 4
   names in any class pattern of a `match` statement whose subject is sys,
   such as `case types.ModuleType(path=p)`. Here sys is any attribute named
   sys, such as `os.sys`, and each of these names wherever it stands in the
   file, whatever its scope: the name sys, any name that
   `import sys as <alias>` binds, and any name that `from <module> import sys`
   binds, with or without `as`, whatever that module is. An attribute named
   meta_path, path_hooks, path_importer_cache or addsitedir, and a keyword of
   one of those names in any class pattern, are findings on any object.
2. `from sys import` of any of those 4 names, or of `*`, is a finding.
3. `import site`, in any form, and `from site import` are findings.
4. A call to setattr or delattr whose first argument is sys is a finding. A
   call to setattr, delattr, getattr or vars whose first argument is starred,
   such as `getattr(*args)`, is a finding whatever the starred value holds.
5. A call to getattr whose first argument is sys is a finding unless its
   second argument is a string literal other than the 4 names, so
   `getattr(sys, "get_int_max_str_digits", None)` passes. `vars(sys)` and
   `sys.__dict__` are findings unless subscripted directly with a string
   literal other than the 4 names.
6. A tools/*.py file that cannot be read or parsed is a finding, and an empty
   tools/*.py listing is a failure.

Out of the rule's scope: writes to sys.modules, which 3 tools use to load a
sibling by its explicit path (`sys.modules[name] = module`); that loads a
named file and adds no folder to the search path.

Residuals:

- deliberate evasion of any kind, including an edit to this gate;
- `exec`, `eval` and `compile` of text, and Python held in strings and run by
  `-c`, such as the runner text of tools/test-skill-release-date.py;
- sys reached by other means: `__import__("sys")`,
  `importlib.import_module("sys")`, `sys.modules["sys"]`,
  `getattr(os, "sys")`, `globals()["sys"]`, a name bound to sys other than by
  an import, such as `s = sys`, `(s := sys)`, a for, comprehension, `with` or
  match target, or a lambda default, sys passed to a function,
  `getattr(sys, "__dict__")`, and a class pattern that reaches sys through a
  keyword named sys, such as `case object(sys=object(path=p))`;
- computed attribute names, such as `sys.__getattribute__("path")`, and
  setattr, getattr, delattr or vars reached under another name, such as
  `builtins.setattr` or `f = setattr`;
- site reached without an import statement, such as `__import__("site")`;
- .pth files in site-packages, which -I does not stop;
- third-party and C-extension code;
- PYTHONPATH handed to a child launched without -I;
- scripts outside tools/*.py, including subfolders of tools/ and names that
  end in .pyw or .pyz.

Usage: python3 -I tools/test-tools-sys-path.py
Exit status: 0 when every check passes, 1 on any finding or failure.
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

GUARDED = ("path", "meta_path", "path_hooks", "path_importer_cache")
ANY_OBJECT = ("meta_path", "path_hooks", "path_importer_cache", "addsitedir")
SETTERS = ("setattr", "delattr")
STARRED = ("setattr", "delattr", "getattr", "vars")


def sys_names(tree: ast.AST) -> set[str]:
    """Return the names taken as the sys module.

    These are sys and each name that an import of the name sys binds, such as
    `import sys as s` or `from os import sys as s`, collected from the whole
    file without regard to scope.
    """
    names = {"sys"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "sys":
                    names.add(alias.asname or alias.name)
    return names


def is_sys(node: ast.AST, names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names
    return isinstance(node, ast.Attribute) and node.attr == "sys"


def literal_clean(node: ast.AST | None) -> bool:
    """True when node is a string literal other than the 4 guarded names."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value not in GUARDED


def check_source(source: bytes, label: str) -> list[str]:
    """Return the findings for one file's source."""
    try:
        tree = ast.parse(source, filename=label)
    except Exception as exc:
        return [f"{label}: cannot be parsed ({type(exc).__name__}: {exc})"]
    names = sys_names(tree)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    # A class-pattern keyword reads that attribute of the match subject.
    on_sys = {
        pattern
        for node in ast.walk(tree)
        if isinstance(node, ast.Match) and is_sys(node.subject, names)
        for case in node.cases
        for pattern in ast.walk(case.pattern)
    }
    found: list[tuple[int, str]] = []

    def dict_access(node: ast.AST, text: str) -> None:
        parent = parents.get(node)
        if not (isinstance(parent, ast.Subscript) and parent.value is node and literal_clean(parent.slice)):
            found.append((node.lineno, f"{text} with a subscript that is not a string literal other than {', '.join(GUARDED)}"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in GUARDED and is_sys(node.value, names):
                found.append((node.lineno, f"a reference to sys.{node.attr}"))
            elif node.attr in ANY_OBJECT:
                found.append((node.lineno, f"a reference to an attribute named {node.attr}"))
            if node.attr == "__dict__" and is_sys(node.value, names):
                dict_access(node, "sys.__dict__")
        elif isinstance(node, ast.MatchClass):
            for name in node.kwd_attrs:
                if name in GUARDED and node in on_sys:
                    found.append((node.lineno, f"a reference to sys.{name} in a class pattern"))
                elif name in ANY_OBJECT:
                    found.append((node.lineno, f"a class-pattern keyword named {name}"))
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "sys":
                for alias in node.names:
                    if alias.name in GUARDED or alias.name == "*":
                        found.append((node.lineno, f"from sys import {alias.name}"))
            if node.module == "site" or (node.module or "").startswith("site."):
                found.append((node.lineno, "an import from site"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "site" or alias.name.startswith("site."):
                    found.append((node.lineno, "an import of site"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args:
            func = node.func.id
            if func in STARRED and isinstance(node.args[0], ast.Starred):
                found.append((node.lineno, f"{func} with a starred first argument"))
            elif func in SETTERS and is_sys(node.args[0], names):
                found.append((node.lineno, f"{func} on sys"))
            elif func == "getattr" and is_sys(node.args[0], names):
                if not (len(node.args) > 1 and literal_clean(node.args[1])):
                    found.append((node.lineno, f"getattr on sys with a name that is not a string literal other than {', '.join(GUARDED)}"))
            elif func == "vars" and is_sys(node.args[0], names):
                dict_access(node, "vars(sys)")
    return [f"{label}:{line}: {reason}" for line, reason in sorted(found)]


def scan_tree(root: Path) -> tuple[list[str], int]:
    """Check every root/tools/*.py; return (findings, number of files)."""
    files = sorted((root / "tools").glob("*.py"))
    if not files:
        return [f"no tools/*.py file found in {root / 'tools'}"], 0
    findings: list[str] = []
    for path in files:
        label = str(path.relative_to(root))
        try:
            source = path.read_bytes()
        except OSError as exc:
            findings.append(f"{label}: cannot be read ({exc.strerror})")
            continue
        findings += check_source(source, label)
    return findings, len(files)


# ---------------------------------------------------------------- self-tests

# Source that must be refused (True) or must pass (False).
CASES = [
    ("import sys\nsys.path.insert(0, 'x')\n", True),
    ("import sys\nsys.path.append('x')\n", True),
    ("import sys\nsys.path[:0] = ['x']\n", True),
    ("import sys\nsys.path += ['x']\n", True),
    ("import sys\nsys.path = ['x']\n", True),
    ("import sys\ndel sys.path[0]\n", True),
    ("import sys\nprint(sys.path)\n", True),
    ("import sys\nprint(f'{sys.path}')\n", True),
    ("import sys\nsys.meta_path.insert(0, f)\n", True),
    ("import sys\nsys.path_hooks.append(h)\n", True),
    ("import sys\nsys.path_importer_cache.clear()\n", True),
    ("import sys as s\ns.path.insert(0, 'x')\n", True),
    ("import os\nos.sys.path.insert(0, 'x')\n", True),
    ("x.meta_path.append(f)\n", True),
    ("x.path_hooks.append(h)\n", True),
    ("x.path_importer_cache.clear()\n", True),
    ("x.addsitedir('d')\n", True),
    ("from sys import path\npath.insert(0, 'x')\n", True),
    ("from sys import path as p\n", True),
    ("from sys import meta_path\n", True),
    ("from sys import path_hooks\n", True),
    ("from sys import path_importer_cache\n", True),
    ("from sys import *\n", True),
    ("import site\n", True),
    ("import site as s\n", True),
    ("from site import addsitedir as a\n", True),
    ("import sys\nsetattr(sys, 'path', ['x'])\n", True),
    ("import sys\nsetattr(sys, 'flags', 1)\n", True),
    ("import sys\ndelattr(sys, 'path')\n", True),
    ("import sys\ngetattr(sys, 'path').insert(0, 'x')\n", True),
    ("import sys\ngetattr(sys, 'meta_path')\n", True),
    ("import sys\ngetattr(sys, name)\n", True),
    ("import sys\ngetattr(sys)\n", True),
    ("import sys\nvars(sys)['path'].insert(0, 'x')\n", True),
    ("import sys\nvars(sys)[name]\n", True),
    ("import sys\nd = vars(sys)\n", True),
    ("import sys\nsys.__dict__['path'].insert(0, 'x')\n", True),
    ("import sys\nsys.__dict__.get('path')\n", True),
    ("def broken(:\n", True),
    ("import site.x\n", True),
    ("from site.x import y\n", True),
    ("import sys\ngetattr(sys, b'path')\n", True),
    ("from os import sys as s\ns.path.insert(0, 'x')\n", True),
    ("import sys\nsetattr(*(sys, 'path'), ['x'])\n", True),
    ("import sys\ndelattr(*(sys, 'path'))\n", True),
    ("import sys\ngetattr(*(sys, 'path')).insert(0, 'x')\n", True),
    ("import sys\nvars(*(sys,))['path'].insert(0, 'x')\n", True),
    ("def f(sys):\n    return sys.path\n", True),
    ("def f():\n    from config import sys as cfg\n    return cfg\ndef g(cfg):\n    return cfg.path\n", True),
    ("import sys, types\nmatch sys:\n    case types.ModuleType(path=p):\n        p.insert(0, 'x')\n", True),
    ("import sys\nmatch sys:\n    case object(meta_path=m):\n        pass\n", True),
    ("import sys\nmatch sys:\n    case object(path_hooks=h):\n        pass\n", True),
    ("match x:\n    case C(path_importer_cache=c):\n        pass\n", True),
    ("match x:\n    case C(addsitedir=a):\n        pass\n", True),
    ("match p:\n    case Point(x=0):\n        pass\n", False),
    ("match request:\n    case Request(path=p):\n        pass\n", False),
    ("a.b.path.join('x')\n", False),
    ("d = obj.__dict__\n", False),
    ("setattr(obj, 'x', 1)\n", False),
    ("getattr(obj, name)\n", False),
    ("d = vars(obj)\n", False),
    ("x = vars()\n", False),
    ("print(*args)\n", False),
    ("import os as s\ns.path.join('a', 'b')\n", False),
    ("from .sys import path\n", False),
    ("from .site import x\n", False),
    ("from os import path\n", False),
    ("import sys\nget_limit = getattr(sys, \"get_int_max_str_digits\", None)\n", False),
    ("import sys\nvars(sys)['flags']\n", False),
    ("import sys\nsys.__dict__['flags']\n", False),
    ("import sys\nsys.modules[name] = module\n", False),
    ("import os\nos.path.join('a', 'b')\n", False),
    ('"""Docstring that names sys.path.insert(0, x) and import site."""\n', False),
    ("x = 'import sys\\nsys.path.insert(0, d)\\n'\n", False),
    ("# sys.path.insert(0, d)\nimport sys\nsys.exit(0)\n", False),
    ("import sys\nfrom sys import argv\n", False),
    ("path = 'p'\nobj.path = path\n", False),
]


def self_test() -> list[str]:
    errors: list[str] = []
    for source, refused in CASES:
        found = check_source(source.encode("utf-8"), "case.py")
        if bool(found) != refused:
            errors.append(f"self-test: {source!r} gave {found or 'no finding'}, expected {'a finding' if refused else 'none'}")
    # The parser raises MemoryError, not SyntaxError, on a source this deep,
    # so this case holds the parse catch at Exception.
    try:
        found = check_source(b"x = " + b"-" * 100000 + b"1\n", "deep.py")
    except Exception as exc:
        found = [f"{type(exc).__name__} escaped check_source"]
    if len(found) != 1 or not found[0].startswith("deep.py: cannot be parsed (MemoryError: "):
        errors.append(f"self-test: a source too complex to parse gave {found}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = root / "tools"
        tools.mkdir()
        findings, _ = scan_tree(root)
        if not any("no tools/*.py file found" in f for f in findings):
            errors.append("self-test: an empty tools/*.py listing gave no failure")
        (tools / "clean.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        findings, count = scan_tree(root)
        if findings or count != 1:
            errors.append(f"self-test: a clean tree gave {findings}, {count} files")
        (tools / "folder.py").mkdir()
        findings, _ = scan_tree(root)
        if not any("tools/folder.py: cannot be read" in f for f in findings):
            errors.append("self-test: an unreadable tools/*.py gave no finding")
        (tools / "folder.py").rmdir()
        (tools / "bad.py").write_bytes(b"x = '\xff'\n")
        findings, _ = scan_tree(root)
        if not any("tools/bad.py: cannot be parsed" in f for f in findings):
            errors.append("self-test: a tools/*.py that does not parse gave no finding")
    return errors


def main() -> int:
    errors = self_test()
    if errors:
        for error in errors:
            print(error)
        print(f"FAIL: {len(errors)} self-test failure(s)")
        return 1
    findings, count = scan_tree(REPO)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s) in {count} tools/*.py files")
        return 1
    print(f"OK: {count} tools/*.py files; none refers to sys.path, sys.meta_path, sys.path_hooks or sys.path_importer_cache, or imports site")
    return 0


if __name__ == "__main__":
    sys.exit(main())
