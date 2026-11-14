#!/usr/bin/env python3
"""Tests for tools/check-instructions-page.py on the instructions page generated on the template.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault, runs the gate there as a separate process and
asserts its exit code and, where the case names them, the words of the gate's
refusal. Exit 0 when every case passes; 1 otherwise. One further case runs the
gate under a faked Python version tuple outside the supported set of
tools/check-inline-code.py and asserts exit 3 with the gate's own message.

A case may also name words that the gate must print on stdout, so a case with
2 faults shows that a check the gate could not evaluate hides no problem it
found. A fixture that cannot be built, for example because an edit's anchor is
not on the page, is a failing case named with the reason, and every other case
still runs. If the download cannot be read or decoded, the suite names it and
exits 1 before any case runs.

3 further cases run a copy of this suite in a temporary repository: with the
download missing, with the download undecodable, and with a page that states 1
character fewer than the download holds. Each asserts exit 1, the refusal or
the failure list, and no traceback. The copy is run with --inner, which leaves
these 3 cases out, so it never runs a copy of itself; each run of the copy has
a timeout.
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
SUITE = Path(__file__).resolve()
# Given to a copy of this suite, so that the copy leaves out SUITE_CASES and never runs a copy of itself.
INNER = "--inner"
SUITE_TIMEOUT = 600
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


def faults(*steps):
    def apply(root: Path) -> None:
        for step in steps:
            step(root)
    return apply


def build(scratch: str, fault, name: str, failures: list[str]) -> Path | None:
    """The fixture of a case, or None, with a failure recorded, when it cannot be built."""
    try:
        root = make_root(Path(scratch))
        if fault:
            fault(root)
    except Exception as error:
        failures.append(f"{name}: the fixture could not be built: {type(error).__name__}: {error}")
        return None
    return root


def load_faults(defined: str, renamed: str, attribute: str) -> list[tuple[str, object, str]]:
    """6 of the ways a sibling tool can fail to load, each a fault on 1 file
    with the words of the refusal it gives: the file missing, its mode 000, its
    mode 000 beside a valid cached file, a syntax error, the definition of
    attribute renamed, and a syntax error beside a cached file of the unbroken
    source that the normal loader runs without comparing it with the source (an
    unchecked hash-based file). The tool must always read the source, so that
    no cached file stands in for it. Root reads a file whatever its mode, so
    under root the 2 mode-000 cases are not run, and main() names them as
    skipped."""
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


def saved_count() -> int:
    """The full download's character count as saved: its bytes decoded as UTF-8, nothing stripped. Every case
    copies the download, so a download that cannot be read or decoded stops the suite with its name and exit 1."""
    try:
        return len((REPO_ROOT / FILES[0]).read_bytes().decode("utf-8"))
    except (OSError, UnicodeError) as error:
        print(f"test-instructions-page: {FILES[0]} could not be read: {error}", file=sys.stderr)
        raise SystemExit(1)


SAVED = saved_count()
COUNT_WORDS = f"check-instructions-page: expected exactly 1 stated count of the full download in {PAGE}, found"
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
    ("a second block on the page", edit(PAGE, "</main>", '<pre id="instructions-text">x</pre></main>'),
        (3, f'check-instructions-page: expected exactly 1 <pre id="instructions-text"> block in {PAGE}, found 2')),
    ("the stated count wrong", edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"), 1),
    ("the stated count wrong beside the right number elsewhere", edit(PAGE, f"saves ({SAVED} characters). Copy",
        f"saves ({SAVED - 1} characters). See {SAVED}. Copy"), 1),
    ("the stated count removed", edit(PAGE, f" ({SAVED} characters)", ""), (3, f"{COUNT_WORDS} 0")),
    ("a second stated count", edit(PAGE, "</main>",
        f"<p>the same content the full download saves ({SAVED} characters)</p></main>"), (3, f"{COUNT_WORDS} 2")),
    ("the download undecodable",
        lambda root: (root / "site/downloads/cleanlanguage.md").write_bytes(b"\xff"), (3, "could not be read")),
    ("the text drifted and the stated count removed",
        faults(edit(PAGE, "Apply the precedence order", "Apply the precedence orders"),
               edit(PAGE, f" ({SAVED} characters)", "")),
        (3, f"{COUNT_WORDS} 0", "the embedded text does not match")),
    ("the stated count wrong and the inline-code gate missing",
        faults(edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"),
               lambda root: (root / "tools/check-inline-code.py").unlink()),
        (3, "check-instructions-page: tools/check-inline-code.py could not be read",
         f"the page states {SAVED - 1} characters for the full download")),
]
LOAD_CASES = [(f"tools/check-inline-code.py {name}",
               lambda root, fault=fault: fault(root / "tools/check-inline-code.py"),
               (3, f"check-instructions-page: tools/check-inline-code.py {words}"))
              for name, fault, words in load_faults("def inline_code_problems(",
                                                    "def inline_code_problems_unused(", "inline_code_problems")]
# Root reads a file whatever its mode, so under root a mode-000 case cannot
# fail to read: it is left out of CASES, and main() names it as skipped.
SKIPPED = [case[0] for case in LOAD_CASES if "mode 000" in case[0] and os.geteuid() == 0]
CASES += [case for case in LOAD_CASES if case[0] not in SKIPPED]


def copy_suite(root: Path) -> None:
    shutil.copyfile(SUITE, root / "tools" / SUITE.name)


# (name, fault, the words the copy of the suite must print); each copy must exit 1 with no traceback.
SUITE_CASES = [
    ("the suite with the download missing", faults(copy_suite, lambda root: (root / FILES[0]).unlink()),
        [f"test-instructions-page: {FILES[0]} could not be read"]),
    ("the suite with the download undecodable", faults(copy_suite, lambda root: (root / FILES[0]).write_bytes(b"\xff")),
        [f"test-instructions-page: {FILES[0]} could not be read"]),
    ("the suite with a page that states 1 character fewer",
        faults(copy_suite, edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)")),
        ["test-instructions-page: failures:", "the committed tree: exit 1, expected 0",
         "the stated count wrong: the fixture could not be built: AssertionError"]),
]


def main() -> int:
    inner = INNER in sys.argv[1:]
    failures: list[str] = []
    for name, fault, expected in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = build(scratch, fault, name, failures)
            if root is None:
                continue
            result = subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name)], capture_output=True, text=True)
            code, words, out_words = (expected + ("",) * 2)[:3] if isinstance(expected, tuple) else (expected, "", "")
            if result.returncode != code or words not in result.stderr or out_words not in result.stdout:
                failures.append(f"{name}: exit {result.returncode}, expected {code}" + (f" and {words!r}" if words else "")
                                + (f" and {out_words!r} on stdout" if out_words else "")
                                + f": {(result.stdout + result.stderr).strip()[:300]}")
    with tempfile.TemporaryDirectory() as scratch:
        root = build(scratch, None, "another Python version", failures)
        if root is not None:
            result = subprocess.run([sys.executable, "-I", "-c", VERSION_PROBE, str(root / "tools" / GATE.name)],
                                    capture_output=True, text=True)
            if result.returncode != 3 or not result.stderr.startswith("check-instructions-page: "):
                failures.append(f"another Python version: exit {result.returncode}, "
                                "expected 3 from check-instructions-page: "
                                f"{(result.stdout + result.stderr).strip()[:300]}")
    for name, fault, words in [] if inner else SUITE_CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = build(scratch, fault, name, failures)
            if root is None:
                continue
            try:
                result = subprocess.run([sys.executable, "-I", str(root / "tools" / SUITE.name), INNER],
                                        capture_output=True, text=True, timeout=SUITE_TIMEOUT)
            except subprocess.TimeoutExpired:
                failures.append(f"{name}: the copy of the suite did not finish within {SUITE_TIMEOUT} s")
                continue
            output = result.stdout + result.stderr
            missing = [word for word in words if word not in output]
            if result.returncode != 1 or missing or "Traceback" in output:
                failures.append(f"{name}: exit {result.returncode}, expected 1 with {missing!r} and no traceback: "
                                f"{output.strip()[-300:]}")
    for name in SKIPPED:
        print(f"test-instructions-page: skipped {name}: root reads a file whatever its mode")
    if failures:
        print("test-instructions-page: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-instructions-page: all {len(CASES) + 1 + (0 if inner else len(SUITE_CASES))} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
