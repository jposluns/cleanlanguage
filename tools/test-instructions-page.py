#!/usr/bin/env python3
"""Tests for tools/check-instructions-page.py on the instructions page generated on the template.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies the case's fault (none for the committed tree; for
some cases a sequence of 2 or 3 changes), runs the gate there as a separate
process and asserts its exit code, that the gate wrote no traceback on stderr
(apart from the KeyboardInterrupt cases below), and, where the case names
them, the words of the gate's refusal. Exit 0 when every case passes; 1 otherwise. 1 further case
runs the gate under a faked Python version tuple outside the supported set of
tools/check-inline-code.py and asserts exit 3 with the refusal in that file's
own words, so a gate that reports the version through its general refusal for
an exception fails it. 1 more case holds the first-character guard of the
leading-content fixtures to PLAIN_STARTS.

Some cases change the download so that only the stated count decides the
result; in each, the embedded text still matches as the gate compares it. The
2 non-ASCII cases give the download and the block the same 2 characters, so a
gate that counts bytes fails them. The astral case gives both U+1F600, which
lies outside the Basic Multilingual Plane, and an e followed by U+0301, so a
gate that counts UTF-16 code units or NFC-normalized text fails it. The CR LF
case gives the download a CR LF where the block keeps LF, which the gate's
comparison still matches, so a gate that counts newline-translated text fails
it. The 2 final-line-end cases remove the download's final LF or make it CR
LF, and each asserts that the download ended in exactly 1 LF before the edit:
a gate that strips the final line end and adds 1 for it fails the first, and a
gate that also strips a final CR fails both. The 5 leading-content cases put
U+FEFF, LF, a space, a tab or U+00A0 before the download's first character and
the same character before the block's text, right after the copy button, so the
block still matches; each asserts that the download decoded as UTF-8 and that
its first character, not its first byte, was neither U+FEFF nor whitespace
before the edit. A gate that decodes the download as utf-8-sig fails the
first, and a gate that strips a leading set of characters that holds U+FEFF,
LF, the space, the tab or U+00A0 fails the case of that character. The CR
LF, final-line-end and leading-content fixtures are written byte for byte.

Some cases replace or extend tools/check-inline-code.py, each on a page that
states a wrong count: its reader raising ValueError, SystemExit(0),
SystemExit(5) or a BaseException subclass, returning None, raising an
exception whose repr raises, or giving a problem whose str raises; the file
raising SystemExit(0) or a BaseException subclass while it loads; an
UnsupportedPython that is not an exception class; a module __getattr__
that raises ValueError beside a renamed inline_code_problems; and, from
description_faults(), a step of describing an exception or naming a problem
raising SystemExit(0) or ValueError, among them a class whose metaclass
raises when its name is read; and inline_code_problems or UnsupportedPython
stored under a key of a str subclass whose __eq__ raises SystemExit(0) or
ValueError, or gives a value whose __bool__ raises SystemExit(0). Each
asserts exit 3, the refusal on stderr and the count problem on stdout. 1
more case, in which the file gives its own module a class whose attribute
reads raise SystemExit(0), asserts exit 1 and the count problem, since the
gate reads the namespace it took before the file ran. 1 more case removes
the file's own from __future__ import annotations and has it read, while it
loads, an annotation that names an undefined name. Compiled without the
gate's own future import, as the file runs alone, that read raises NameError,
so the case asserts exit 3, the refusal and the count problem; a gate whose
compile inherits that import lets the file load and exit 1, and fails it.

5 cases raise KeyboardInterrupt from tools/check-inline-code.py, on a page
that states 1 character fewer, at each place where the gate catches every
other exception: while the file loads, while a name is looked up under such
a key, in its reader, in the repr of an exception that the reader raises, and
in the class name of an exception whose repr raises. Each asserts exit
-SIGINT, a last line of stderr that is KeyboardInterrupt, and nothing on
stdout, so a gate that catches it at any of these places fails.

The case of the committed tree also asserts both numbers of the gate's
success line: the download without its final newline, read with its line
ends translated, and the download as saved.

1 case sets the mode of the download to 000, and 2 set the mode of the
folder that holds the download or the page to 000. Each asserts exit 3 with
"could not be read" and the permission error, so a gate that lets the
download's read error escape, or reports such a lookup error as a missing
file, fails them. Like the other mode-000 cases, they are skipped under root.

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
import signal
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
# The start of the gate's refusal under that version, in the words of tools/check-inline-code.py.
VERSION_WORDS = "check-instructions-page: tools/check-inline-code.py runs only on Python "


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


def edit_bytes(relative: str, old: bytes, new: bytes):
    """Like edit, but on the file's bytes, with no newline translation, and the old bytes must occur exactly once."""
    def apply(root: Path) -> None:
        path = root / relative
        data = path.read_bytes()
        if data.count(old) != 1:
            raise AssertionError(f"{old!r} occurs {data.count(old)} times in {relative}, expected 1")
        path.write_bytes(data.replace(old, new))
    return apply


def final_line_end(relative: str, new: bytes):
    """Replace the file's final line end, which must be exactly 1 LF, by the new bytes, with no newline translation."""
    def apply(root: Path) -> None:
        path = root / relative
        data = path.read_bytes()
        if not data.endswith(b"\n") or data.endswith((b"\n\n", b"\r\n")):
            raise AssertionError(f"{relative} does not end in exactly 1 LF: {data[-2:]!r}")
        path.write_bytes(data[:-1] + new)
    return apply


def begins_plainly(data: bytes) -> bool:
    """Whether the data decodes as UTF-8 and its first character, not its first byte, is neither U+FEFF nor
    whitespace as str.isspace() reads it, so that U+00A0, U+3000 and U+001C count as whitespace."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return bool(text) and text[0] != "\N{ZERO WIDTH NO-BREAK SPACE}" and not text[0].isspace()


# (data, whether begins_plainly accepts it): the first-character guard's own cases.
PLAIN_STARTS = [(b"x", True), ("\xe9".encode("utf-8"), True), (b"", False), (b"\xff", False),
                (b"\xef\xbb\xbfx", False), (b" x", False), (b"\tx", False), (b"\nx", False),
                ("\xa0x".encode("utf-8"), False), ("\N{IDEOGRAPHIC SPACE}x".encode("utf-8"), False),
                (b"\x1cx", False)]


def leading(relative: str, new: bytes):
    """Put the new bytes before the file's first byte, with no newline translation; the file must decode as UTF-8
    and begin with a character that is neither U+FEFF nor whitespace (begins_plainly)."""
    def apply(root: Path) -> None:
        path = root / relative
        data = path.read_bytes()
        if not begins_plainly(data):
            raise AssertionError(f"{relative} does not begin with a character other than U+FEFF and whitespace: "
                                 f"{data[:4]!r}")
        path.write_bytes(new + data)
    return apply


def appended(code: str):
    """Add the code to tools/check-inline-code.py after every other definition of the file, so that a name it
    defines replaces the file's own."""
    def apply(root: Path) -> None:
        path = root / "tools/check-inline-code.py"
        path.write_bytes(path.read_bytes() + b"\n\n" + code.encode("utf-8"))
    return apply


raising = appended('def inline_code_problems(text, svg=False):\n    raise ValueError("inline check failed")\n')


def symlinked(relative: str):
    """Move a file to a regular copy beside it and put a symbolic link to that copy in its place."""
    def apply(root: Path) -> None:
        path = root / relative
        copy = path.with_name(path.name + ".copy")
        path.rename(copy)
        os.symlink(copy.name, path)
    return apply


def directory(relative: str):
    """Replace a file by an empty directory of the same name."""
    def apply(root: Path) -> None:
        (root / relative).unlink()
        (root / relative).mkdir()
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


def saved_text() -> str:
    """The full download as saved: its bytes decoded as UTF-8, nothing stripped. Every case copies the download, so
    a download that cannot be read or decoded stops the suite with its name and exit 1."""
    try:
        return (REPO_ROOT / FILES[0]).read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        print(f"test-instructions-page: {FILES[0]} could not be read: {error}", file=sys.stderr)
        raise SystemExit(1)


SAVED_TEXT = saved_text()
SAVED = len(SAVED_TEXT)
# The other number of the gate's success line: the download read with its line ends translated to LF, as Python
# reads text, without its final LFs.
TRIMMED_LENGTH = len(SAVED_TEXT.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n"))
SUCCESS_WORDS = (f"({TRIMMED_LENGTH} characters without the final newline), states the download's {SAVED} "
                 "characters and carries no inline code.")
COUNT_WORDS = f"check-instructions-page: expected exactly 1 stated count of the full download in {PAGE}, found"
# 3 characters more than "Apply the precedence order": U+1F600, which UTF-16 writes as 2 code units, a space, and
# U+0301 after the e, which NFC joins to it.
ASTRAL = "Apply the \U0001f600 precedence orde\N{COMBINING ACUTE ACCENT}r"
CASES = [
    ("the committed tree", None, (0, "", SUCCESS_WORDS)),
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
    ("the inline-code gate missing", lambda root: (root / "tools/check-inline-code.py").unlink(),
        (3, "check-instructions-page: tools/check-inline-code.py could not be read")),
    ("P3: a javascript: link after a </noscript> inside an attribute", edit(PAGE, "</main>",
        "<noscript><p title=\"</noscript><a href='javascript:alert(1)' title='>'>x</a>\"></p></noscript></main>"), 1),
    ("the page missing", lambda root: (root / PAGE).unlink(), (3, f"check-instructions-page: {PAGE} does not exist")),
    ("the download a directory", directory(FILES[0]),
        (3, f"check-instructions-page: {FILES[0]} is not a regular file")),
    ("the download a symbolic link to a regular copy", symlinked(FILES[0]),
        (3, f"check-instructions-page: {FILES[0]} is not a regular file")),
    ("the page a symbolic link to a regular copy", symlinked(PAGE),
        (3, f"check-instructions-page: {PAGE} is not a regular file")),
    ("a second block on the page", edit(PAGE, "</main>", '<pre id="instructions-text">x</pre></main>'),
        (3, f'check-instructions-page: expected exactly 1 <pre id="instructions-text"> block in {PAGE}, found 2')),
    ("no embedded block and the stated count wrong",
        faults(edit(PAGE, '<pre id="instructions-text"', '<pre id="instructions-gone"'),
               edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)")),
        (3, f'check-instructions-page: expected exactly 1 <pre id="instructions-text"> block in {PAGE}, found 0',
         f"the page states {SAVED - 1} characters for the full download")),
    ("the stated count wrong", edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"), 1),
    ("the stated count 1 too high", edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED + 1} characters)"),
        (1, "", f"the page states {SAVED + 1} characters for the full download")),
    ("the stated count wrong beside the right number elsewhere", edit(PAGE, f"saves ({SAVED} characters). Copy",
        f"saves ({SAVED - 1} characters). See ({SAVED} characters). Copy"), 1),
    ("the stated count removed", edit(PAGE, f" ({SAVED} characters)", ""), (3, f"{COUNT_WORDS} 0")),
    ("the fixed word saves changed", edit(PAGE, f"download saves ({SAVED} characters)",
        f"download holds ({SAVED} characters)"), (3, f"{COUNT_WORDS} 0")),
    ("a second stated count", edit(PAGE, "</main>",
        f"<p>the same content the full download saves ({SAVED} characters)</p></main>"), (3, f"{COUNT_WORDS} 2")),
    ("2 non-ASCII characters in the download and the block",
        faults(edit(FILES[0], "Apply the precedence order", "Apply the pr\u00e9c\u00e9dence order"),
               edit(PAGE, "Apply the precedence order", "Apply the pr\u00e9c\u00e9dence order")), 0),
    ("2 non-ASCII characters in the download and the block, the page stating the byte count",
        faults(edit(FILES[0], "Apply the precedence order", "Apply the pr\u00e9c\u00e9dence order"),
               edit(PAGE, "Apply the precedence order", "Apply the pr\u00e9c\u00e9dence order"),
               edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED + 2} characters)")),
        (1, "", f"the page states {SAVED + 2} characters for the full download")),
    ("a CR LF in the download, LF in the block, the page stating the count as saved",
        faults(edit_bytes(FILES[0], b"Apply the precedence order", b"Apply the precedence\r\norder"),
               edit_bytes(PAGE, b"Apply the precedence order", b"Apply the precedence\norder"),
               edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED + 1} characters)")), 0),
    ("the download without its final newline, the page stating the count as saved",
        faults(final_line_end(FILES[0], b""),
               edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)")), 0),
    ("the download ending in CR LF, the page stating the count as saved",
        faults(final_line_end(FILES[0], b"\r\n"),
               edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED + 1} characters)")), 0),
    ("the download beginning with U+FEFF, the page stating the count as saved",
        faults(leading(FILES[0], b"\xef\xbb\xbf"),
               edit_bytes(PAGE, BUTTON.encode("utf-8"), BUTTON.encode("utf-8") + b"\xef\xbb\xbf"),
               edit_bytes(PAGE, f"saves ({SAVED} characters)".encode("utf-8"),
                          f"saves ({SAVED + 1} characters)".encode("utf-8"))), 0),
    ("the download beginning with a blank line, the page stating the count as saved",
        faults(leading(FILES[0], b"\n"),
               edit_bytes(PAGE, BUTTON.encode("utf-8"), BUTTON.encode("utf-8") + b"\n"),
               edit_bytes(PAGE, f"saves ({SAVED} characters)".encode("utf-8"),
                          f"saves ({SAVED + 1} characters)".encode("utf-8"))), 0),
    ("the download beginning with a space, the page stating the count as saved",
        faults(leading(FILES[0], b" "),
               edit_bytes(PAGE, BUTTON.encode("utf-8"), BUTTON.encode("utf-8") + b" "),
               edit_bytes(PAGE, f"saves ({SAVED} characters)".encode("utf-8"),
                          f"saves ({SAVED + 1} characters)".encode("utf-8"))), 0),
    ("the download beginning with a tab, the page stating the count as saved",
        faults(leading(FILES[0], b"\t"),
               edit_bytes(PAGE, BUTTON.encode("utf-8"), BUTTON.encode("utf-8") + b"\t"),
               edit_bytes(PAGE, f"saves ({SAVED} characters)".encode("utf-8"),
                          f"saves ({SAVED + 1} characters)".encode("utf-8"))), 0),
    ("the download beginning with U+00A0, the page stating the count as saved",
        faults(leading(FILES[0], "\xa0".encode("utf-8")),
               edit_bytes(PAGE, BUTTON.encode("utf-8"), BUTTON.encode("utf-8") + "\xa0".encode("utf-8")),
               edit_bytes(PAGE, f"saves ({SAVED} characters)".encode("utf-8"),
                          f"saves ({SAVED + 1} characters)".encode("utf-8"))), 0),
    ("U+1F600 and a combining accent in the download and the block, the page stating the count as saved",
        faults(edit(FILES[0], "Apply the precedence order", ASTRAL),
               edit(PAGE, "Apply the precedence order", ASTRAL),
               edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED + 3} characters)")), 0),
    ("a stated count of 5000 digits", edit(PAGE, f"saves ({SAVED} characters)", f"saves ({'9' * 5000} characters)"),
        (1, "", f"the page states {'9' * 20}... (5000 digits) characters for the full download")),
    ("the stated count with a leading zero", edit(PAGE, f"saves ({SAVED} characters)", f"saves (0{SAVED} characters)"),
        (1, "", f"the page states 0{SAVED} characters for the full download")),
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
LOAD_CASES += [
    ("tools/check-inline-code.py a symbolic link to a regular copy", symlinked("tools/check-inline-code.py"),
        (3, "check-instructions-page: tools/check-inline-code.py is not a regular file")),
    ("tools/check-inline-code.py raising ValueError while it checks the page, and the stated count wrong",
        faults(edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"), raising),
        (3, "check-instructions-page: tools/check-inline-code.py could not check the page: "
            "ValueError('inline check failed')",
         f"the page states {SAVED - 1} characters for the full download")),
]
STOP = "class Stop(BaseException):\n    pass\n\n"
# (name, fault in tools/check-inline-code.py, the words of the refusal after "tools/check-inline-code.py "); each
# runs on a page that states 1 character fewer, so the case also asserts that the count problem is printed.
INLINE_FAULTS = [
    ("its reader raising SystemExit(0)",
        appended("def inline_code_problems(text, svg=False):\n    raise SystemExit(0)\n"),
        "could not check the page: SystemExit(0)"),
    ("its reader raising SystemExit(5)",
        appended("def inline_code_problems(text, svg=False):\n    raise SystemExit(5)\n"),
        "could not check the page: SystemExit(5)"),
    ("its reader raising a BaseException subclass",
        appended(STOP + "def inline_code_problems(text, svg=False):\n    raise Stop('stop')\n"),
        "could not check the page: Stop('stop')"),
    ("its reader returning None", appended("def inline_code_problems(text, svg=False):\n    return None\n"),
        "could not check the page: TypeError(\"'NoneType' object is not iterable\")"),
    ("its reader raising an exception whose repr raises",
        appended("class BadRepr(Exception):\n    def __repr__(self):\n        raise ValueError('repr')\n\n"
                 "def inline_code_problems(text, svg=False):\n    raise BadRepr()\n"),
        "could not check the page: BadRepr (its repr raised ValueError)"),
    ("its reader giving a problem whose str raises",
        appended("class BadText:\n    def __str__(self):\n        raise ValueError('text')\n\n"
                 "def inline_code_problems(text, svg=False):\n    return [BadText()]\n"),
        "could not check the page: ValueError('text')"),
    ("raising SystemExit(0) while it loads", appended("raise SystemExit(0)\n"), "could not be loaded: SystemExit(0)"),
    ("raising a BaseException subclass while it loads", appended(STOP + "raise Stop('at load')\n"),
        "could not be loaded: Stop('at load')"),
    ("with an UnsupportedPython that is not an exception class", appended("UnsupportedPython = 5\n"),
        "defines an UnsupportedPython that is not an exception class"),
    ("with a module __getattr__ that raises ValueError and inline_code_problems renamed",
        faults(edit("tools/check-inline-code.py", "def inline_code_problems(", "def inline_code_problems_unused("),
               appended("def __getattr__(name):\n    raise ValueError('getattr')\n")),
        "defines no inline_code_problems"),
]
# The gate's words for a class whose name cannot be read.
UNNAMED = "an object of a class whose name could not be read"
# (its name in a case name, its class name in the refusal, the code that raises it): each is raised at 1 step of a
# description.
RAISED = [("SystemExit(0)", "SystemExit", "SystemExit(0)"), ("ValueError", "ValueError", "ValueError('raised')")]


def unnamed(raised: str) -> str:
    """A metaclass whose classes raise the given exception when their __name__ is read."""
    return f"class Unnamed(type):\n    @property\n    def __name__(cls):\n        raise {raised}\n\n"


# (where the description is made, the base class of the raised exception, the code that raises it, the method the
# gate calls to describe it, the words of the refusal before the description).
DESCRIBED_AT = [
    ("while it loads", "Exception", "raise Boom()\n", "__repr__", "could not be loaded: "),
    ("in its reader", "Exception", "def inline_code_problems(text, svg=False):\n    raise Boom()\n", "__repr__",
     "could not check the page: "),
    ("as an UnsupportedPython in its reader", "UnsupportedPython",
     "def inline_code_problems(text, svg=False):\n    raise Boom()\n", "__str__", ""),
]


def description_faults() -> list[tuple[str, object, str]]:
    """For each place where the gate describes an exception, and for SystemExit(0) and ValueError, 1 fault at each
    step of the description: the exception's repr or str raising, its class name raising after that, the class name
    of the exception that its repr or str raised raising, its repr or str giving a str subclass while its class name
    raises, and its repr or str giving a str subclass whose own class name raises. The existing case of the reader's
    repr raising ValueError is not repeated."""
    found = []
    for where, base, raiser, method, before in DESCRIBED_AT:
        how = method.strip("_")
        for label, words, raised in RAISED:
            steps = [
                (f"its {how} raising {label}", f"class Boom({base}):\n    def {method}(self):\n        raise {raised}\n\n",
                 f"Boom (its {how} raised {words})"),
                (f"its class name raising {label}",
                 unnamed(raised) + f"class Boom({base}, metaclass=Unnamed):\n    def {method}(self):\n"
                 "        raise ValueError('text')\n\n", f"{UNNAMED} (its {how} raised ValueError)"),
                (f"the class name of what its {how} raised raising {label}",
                 unnamed(raised) + "class Inner(Exception, metaclass=Unnamed):\n    pass\n\n"
                 f"class Boom({base}):\n    def {method}(self):\n        raise Inner()\n\n",
                 f"Boom (its {how} raised {UNNAMED})"),
                (f"its {how} giving a str subclass and its class name raising {label}",
                 unnamed(raised) + "class Text(str):\n    pass\n\n"
                 f"class Boom({base}, metaclass=Unnamed):\n    def {method}(self):\n        return Text('text')\n\n",
                 f"{UNNAMED} (its {how} gave Text, not str)"),
                (f"its {how} giving a str subclass whose class name raises {label}",
                 unnamed(raised) + "class Text(str, metaclass=Unnamed):\n    pass\n\n"
                 f"class Boom({base}):\n    def {method}(self):\n        return Text('text')\n\n",
                 f"Boom (its {how} gave {UNNAMED}, not str)"),
            ]
            found += [(f"raising an exception {where}, {step}", appended(code + raiser), before + description)
                      for step, code, description in steps
                      if (where, step) != ("in its reader", "its repr raising ValueError")]
    for label, words, raised in RAISED:
        found.append((f"its reader giving a problem whose class name raises {label}",
                      appended(unnamed(raised) + "class Text(str, metaclass=Unnamed):\n    def __str__(self):\n"
                               "        return self\n\n"
                               "def inline_code_problems(text, svg=False):\n    return [Text('text')]\n"),
                      f"could not check the page: TypeError('a problem is {UNNAMED}, not str')"))
    found.append(("its reader giving a problem whose str raises SystemExit(0)",
                  appended("class BadText:\n    def __str__(self):\n        raise SystemExit(0)\n\n"
                           "def inline_code_problems(text, svg=False):\n    return [BadText()]\n"),
                  "could not check the page: SystemExit(0)"))
    return found


INLINE_FAULTS += description_faults()


def keyed(name: str, compare: str, prelude: str = "") -> str:
    """Code that stores the file's name under a key of a str subclass with the same hash, whose __eq__ runs the
    given code, so that looking the name up runs it."""
    return (f"{prelude}class Key(str):\n    __hash__ = str.__hash__\n\n    def __eq__(self, other):\n"
            f"        {compare}\n\n"
            f"globals()[Key({name!r})] = globals().pop({name!r})\n")


# A __bool__ that raises, for the value that a key's __eq__ returns.
FALSY = "class Falsy:\n    def __bool__(self):\n        raise SystemExit(0)\n\n"
INLINE_FAULTS += [
    (f"with {name} under a key whose __eq__ raises {label}", appended(keyed(name, f"raise {raised}")),
     f"raised an exception while its names were read: {raised}")
    for name in ("inline_code_problems", "UnsupportedPython")
    for label, raised in [("SystemExit(0)", "SystemExit(0)"), ("ValueError", "ValueError('eq')")]
]
INLINE_FAULTS.append(("with inline_code_problems under a key whose __eq__ gives a value whose __bool__ raises "
                      "SystemExit(0)", appended(keyed("inline_code_problems", "return Falsy()", FALSY)),
                      "raised an exception while its names were read: SystemExit(0)"))
LOAD_CASES += [(f"tools/check-inline-code.py {name}, and the stated count wrong",
                faults(edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"), fault),
                (3, f"check-instructions-page: tools/check-inline-code.py {words}",
                 f"the page states {SAVED - 1} characters for the full download"))
               for name, fault, words in INLINE_FAULTS]


def unsearchable(relative: str):
    """Set the mode of the folder that holds the file to 000, so that looking the file up fails with a permission
    error and not because the file is missing."""
    def apply(root: Path) -> None:
        os.chmod((root / relative).parent, 0)
    return apply


# A lookup error other than a missing file, here a folder that cannot be searched, is reported as could not be
# read, not as not existing.
LOAD_CASES += [
    ("the download with mode 000", lambda root: os.chmod(root / FILES[0], 0),
        (3, f"check-instructions-page: {FILES[0]} could not be read: [Errno 13] Permission denied")),
    ("the download in a folder with mode 000", unsearchable(FILES[0]),
        (3, f"check-instructions-page: {FILES[0]} could not be read: [Errno 13] Permission denied")),
    ("the page in a folder with mode 000", unsearchable(PAGE),
        (3, f"check-instructions-page: {PAGE} could not be read: [Errno 13] Permission denied")),
]
# Root reads a file whatever its mode, so under root a mode-000 case cannot
# fail to read: it is left out of CASES, and main() names it as skipped.
SKIPPED = [case[0] for case in LOAD_CASES if "mode 000" in case[0] and os.geteuid() == 0]
CASES += [case for case in LOAD_CASES if case[0] not in SKIPPED]
# The file finds its own module and gives it a class whose attribute reads raise, so a gate that reads the module
# after the file has run, rather than the namespace it took before, ends there.
SWAPPED = ("import gc, types\n\nclass Swapped(types.ModuleType):\n    def __getattribute__(self, name):\n"
           "        raise SystemExit(0)\n\nfor holder in gc.get_referrers(globals()):\n"
           "    if type(holder) is types.ModuleType:\n        holder.__class__ = Swapped\n")
CASES.append(("tools/check-inline-code.py giving its module a class whose attribute reads raise SystemExit(0), and "
              "the stated count wrong",
              faults(edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"), appended(SWAPPED)),
              (1, "", f"the page states {SAVED - 1} characters for the full download")))
# Without its own future import, the file evaluates the annotation when it reads it, and the name is undefined. A gate
# whose compile inherits its own from __future__ import annotations leaves the annotation a string, and the file loads.
UNRESOLVED = "def annotated(value: UndefinedName):\n    pass\n\n\nannotated.__annotations__\n"
CASES.append(("tools/check-inline-code.py without its own future import, reading an annotation that names an "
              "undefined name while it loads, and the stated count wrong",
              faults(edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"),
                     edit("tools/check-inline-code.py", "\nfrom __future__ import annotations\n", "\n"),
                     appended(UNRESOLVED)),
              (3, "check-instructions-page: tools/check-inline-code.py could not be loaded: "
                  "NameError(\"name 'UndefinedName' is not defined\")",
               f"the page states {SAVED - 1} characters for the full download")))
# (name, fault in tools/check-inline-code.py): each raises KeyboardInterrupt at 1 place where the gate catches every
# other exception, on a page that states 1 character fewer. The gate must end as Python ends on Ctrl-C, with the
# KeyboardInterrupt traceback, exit -SIGINT and nothing on stdout.
INTERRUPTS = [
    ("raising KeyboardInterrupt while it loads", appended("raise KeyboardInterrupt\n")),
    ("with inline_code_problems under a key whose __eq__ raises KeyboardInterrupt",
        appended(keyed("inline_code_problems", "raise KeyboardInterrupt"))),
    ("its reader raising KeyboardInterrupt",
        appended("def inline_code_problems(text, svg=False):\n    raise KeyboardInterrupt\n")),
    ("its reader raising an exception whose repr raises KeyboardInterrupt",
        appended("class Boom(Exception):\n    def __repr__(self):\n        raise KeyboardInterrupt\n\n"
                 "def inline_code_problems(text, svg=False):\n    raise Boom()\n")),
    ("its reader raising an exception whose repr raises and whose class name raises KeyboardInterrupt",
        appended(unnamed("KeyboardInterrupt") + "class Boom(Exception, metaclass=Unnamed):\n"
                 "    def __repr__(self):\n        raise ValueError('repr')\n\n"
                 "def inline_code_problems(text, svg=False):\n    raise Boom()\n")),
]
INTERRUPTS = [(f"tools/check-inline-code.py {name}, and the stated count wrong",
               faults(edit(PAGE, f"saves ({SAVED} characters)", f"saves ({SAVED - 1} characters)"), fault))
              for name, fault in INTERRUPTS]


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
            traceback = "Traceback" in result.stderr
            if result.returncode != code or words not in result.stderr or out_words not in result.stdout or traceback:
                failures.append(f"{name}: exit {result.returncode}, expected {code}" + (f" and {words!r}" if words else "")
                                + (f" and {out_words!r} on stdout" if out_words else "")
                                + (" and no traceback" if traceback else "")
                                + f": {(result.stdout + result.stderr).strip()[:300]}")
    for name, fault in INTERRUPTS:
        with tempfile.TemporaryDirectory() as scratch:
            root = build(scratch, fault, name, failures)
            if root is None:
                continue
            result = subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name)], capture_output=True, text=True)
            lines = result.stderr.splitlines()
            if result.returncode != -signal.SIGINT or not lines or lines[-1] != "KeyboardInterrupt" or result.stdout:
                failures.append(f"{name}: exit {result.returncode}, expected {-signal.SIGINT} with stderr ending in "
                                f"KeyboardInterrupt and nothing on stdout: {(result.stdout + result.stderr).strip()[-300:]}")
    with tempfile.TemporaryDirectory() as scratch:
        root = build(scratch, None, "another Python version", failures)
        if root is not None:
            result = subprocess.run([sys.executable, "-I", "-c", VERSION_PROBE, str(root / "tools" / GATE.name)],
                                    capture_output=True, text=True)
            if result.returncode != 3 or not result.stderr.startswith(VERSION_WORDS) or "Traceback" in result.stderr:
                failures.append(f"another Python version: exit {result.returncode}, "
                                f"expected 3 and stderr starting {VERSION_WORDS!r} with no traceback: "
                                f"{(result.stdout + result.stderr).strip()[:300]}")
    wrong = [data for data, accepted in PLAIN_STARTS if begins_plainly(data) != accepted]
    if wrong:
        failures.append(f"the first-character guard: wrong for {wrong!r}")
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
    total = len(CASES) + len(INTERRUPTS) + 2 + (0 if inner else len(SUITE_CASES))
    print(f"test-instructions-page: all {total} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
