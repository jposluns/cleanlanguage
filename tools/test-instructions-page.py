#!/usr/bin/env python3
"""Tests for tools/check-instructions-page.py on the instructions page generated on the template.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault, runs the gate there as a separate process and
asserts its exit code and, where the case names them, the words of the gate's
refusal. Exit 0 when every case passes; 1 otherwise. One further case runs the
gate under a faked Python version tuple outside the supported set of
tools/check-inline-code.py and asserts exit 3 with the gate's own message.
"""

from __future__ import annotations

import importlib.util
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-instructions-page.py"
PAGE = "site/instructions/index.html"
FILES = ["site/downloads/cleanlanguage.md", PAGE, "tools/check-inline-code.py"]
BUTTON = '<button class="copy" type="button" data-copy="instructions-text" hidden>Copy</button>'
# Runs the gate under a faked version tuple outside SUPPORTED_PYTHONS of tools/check-inline-code.py.
VERSION_PROBE = (
    "import sys, runpy; "
    "sys.version_info = (3, 13, 9, 'final', 0); "
    "runpy.run_path(sys.argv[1], run_name='__main__')"
)


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(GATE, root / "tools" / GATE.name)
    for relative in FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


def edit(relative: str, old: str, new: str):
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(f"{old!r} is not in {relative}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return apply


def load_faults(defined: str, renamed: str, attribute: str) -> list[tuple[str, object, str]]:
    """The 6 ways a sibling tool can fail to load, each a fault on 1 file with the words of the refusal it gives: the
    file missing, its mode 000, its mode 000 beside a valid cached file, a syntax error, the definition of attribute
    renamed, and a syntax error beside a cached file of the unbroken source that the normal loader runs without
    comparing it with the source (an unchecked hash-based file). The tool must always read the source, so that no
    cached file stands in for it."""
    def missing(path: Path) -> None:
        path.unlink()

    def locked(path: Path) -> None:
        os.chmod(path, 0)

    def cached_locked(path: Path) -> None:
        py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        os.chmod(path, 0)

    def broken(path: Path) -> None:
        path.write_bytes(path.read_bytes() + b"\ndef (\n")

    def rename(path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        if defined not in text:
            raise AssertionError(f"{defined!r} is not in {path.name}")
        path.write_text(text.replace(defined, renamed, 1), encoding="utf-8")

    def stale(path: Path) -> None:
        py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        broken(path)

    return [("missing", missing, "could not be read"), ("with mode 000", locked, "could not be read"),
            ("with mode 000 beside a valid cached file", cached_locked, "could not be read"),
            ("with a syntax error", broken, "could not be loaded"),
            (f"with {attribute} renamed", rename, f"defines no {attribute}"),
            ("with a syntax error beside a stale cached file", stale, "could not be loaded")]


CASES = [
    ("the committed tree", None, 0),
    ("1 character changed in the block", edit(PAGE, "Apply the precedence order", "Apply the precedence orders"), 1),
    ("the copy button removed", edit(PAGE, BUTTON, ""), 1),
    ("the copy button shown", edit(PAGE, BUTTON, BUTTON.replace(" hidden", "")), 1),
    ("markup added inside the block", edit(PAGE, BUTTON, BUTTON + "<span>x</span>"), 1),
    ("a second copy button in the block", edit(PAGE, BUTTON, BUTTON + BUTTON), 1),
    ("an inline script", edit(PAGE, "</main>", "<script>x()</script></main>"), 1),
    ("an inline style", edit(PAGE, "<h1>", '<h1 style="x">'), 1),
    ("I5: an application/x-javascript script",
        edit(PAGE, "</main>", '<script type="application/x-javascript">alert(1)</script></main>'), 1),
    ("I2B: src= inside another attribute's quoted value",
        edit(PAGE, "</main>", "<script title='src=\"/install/\"'>alert(1)</script></main>"), 1),
    ("I3: an event handler after a slash", edit(PAGE, "</main>", '<span/onclick="alert(1)">x</span></main>'), 1),
    ("I4: a javascript: link", edit(PAGE, "</main>", '<a href="javascript:alert(1)">x</a></main>'), 1),
    ("a script from another origin", edit(PAGE, "</main>", '<script src="https://example.com/x.js"></script></main>'), 1),
    ("the inline-code gate missing", lambda root: (root / "tools/check-inline-code.py").unlink(), 3),
    ("P3: a javascript: link after a </noscript> inside an attribute", edit(PAGE, "</main>",
        "<noscript><p title=\"</noscript><a href='javascript:alert(1)' title='>'>x</a>\"></p></noscript></main>"), 1),
    ("the page missing", lambda root: (root / PAGE).unlink(), 3),
    ("a second block on the page", edit(PAGE, "</main>", '<pre id="instructions-text">x</pre></main>'), 3),
] + [(f"tools/check-inline-code.py {name}", lambda root, fault=fault: fault(root / "tools/check-inline-code.py"),
      (3, f"check-instructions-page: tools/check-inline-code.py {words}"))
     for name, fault, words in load_faults("def inline_code_problems(", "def inline_code_problems_unused(",
                                           "inline_code_problems")]


def main() -> int:
    failures: list[str] = []
    for name, fault, expected in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if fault:
                fault(root)
            result = subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name)], capture_output=True, text=True)
            code, words = expected if isinstance(expected, tuple) else (expected, "")
            if result.returncode != code or words not in result.stderr:
                failures.append(f"{name}: exit {result.returncode}, expected {code}" + (f" and {words!r}" if words else "")
                                + f": {(result.stdout + result.stderr).strip()[:300]}")
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        result = subprocess.run([sys.executable, "-I", "-c", VERSION_PROBE, str(root / "tools" / GATE.name)],
                                capture_output=True, text=True)
        if result.returncode != 3 or not result.stderr.startswith("check-instructions-page: "):
            failures.append(f"another Python version: exit {result.returncode}, expected 3 from check-instructions-page: "
                            f"{(result.stdout + result.stderr).strip()[:300]}")
    if failures:
        print("test-instructions-page: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-instructions-page: all {len(CASES) + 1} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
