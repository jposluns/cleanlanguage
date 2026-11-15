#!/usr/bin/env python3
"""Check the instructions page renders the portable text exactly, and statically.

``site/instructions/index.html`` shows the full Clean Language rule set so a
reader can copy it without downloading anything. The text is embedded in the
page rather than fetched at runtime, which means the page now holds a second copy
of ``site/downloads/cleanlanguage.md`` and the 2 can drift. This
check makes that drift fail.

Why the page is static
----------------------

The page used to fetch the text with an inline ``<script>``. The site's
Content-Security-Policy was then ``script-src 'self'`` with no
``'unsafe-inline'``, nonce, or hash, so a compliant browser blocked that script
and the page showed "Loading the instructions..." and nothing else. Its only inline ``style``
attribute was blocked by ``style-src 'self'`` for the same reason. Embedding the
text removes both problems, works with JavaScript switched off, and needs no
loosening of the policy. Since the owner's decision of 2026-11-03 the site-wide
policy is the shared template policy, which allows ``'unsafe-inline'`` scripts
because Cloudflare's own scripts need it, so a browser no longer blocks an inline
script here. The site's own pages must not use inline code (template
specification, section 5), and this check enforces that rule on this page, as
``tools/check-inline-code.py`` does on every page. ``style-src 'self'``
still blocks an inline style attribute in the browser, so one would break the
page again in a way that the valid markup does not show.

What it verifies
----------------

It checks the page that ``tools/build-site.py`` generates on the shared
template:

1. The page embeds the portable text exactly, character for character, once HTML
   escaping is undone.
2. The page contains no inline code and no refused markup, as checks 1 to 10
   of ``tools/check-inline-code.py`` define them for an HTML page, with that
   gate's own code: among them, no ``<script>`` without ``src`` other than a
   structured-data block, no ``on*`` attribute, no ``javascript:`` URL, no
   ``<style>`` element or ``style`` attribute, and none of the elements that
   the parser reads differently from a browser.
3. The page states the character count of ``site/downloads/cleanlanguage.md``
   as saved, its bytes decoded as UTF-8 with no newline translation and nothing
   stripped, parsed from the sentence's fixed words (``the same content the
   full download saves (N characters)``), which must occur exactly once in the
   page source, and counted independently of ``tools/build-site.py``. The
   stated digits are compared as text with the count written in decimal, as
   the generator writes it, so a count with a leading zero is a problem, and
   so is a count of more than 4300 digits, which int() would refuse with a
   traceback.

The template puts the page's copy button inside the block (template
specification 7.11). Exactly that button, ``<button class="copy" type="button"
data-copy="instructions-text" hidden>Copy</button>``, is required as the first
thing in the block and is removed before the comparison; any other markup
inside the block still fails the comparison.

A ``<script type="application/ld+json">`` block is not an inline script for this
purpose. The browser never executes it and CSP ``script-src`` does not apply, which
is why structured data elsewhere on the site works under the same policy.

What it does not verify
-----------------------

It compares the page against the portable text file. It says nothing about
whether that file agrees with the packaged skill: that is the separate concern of
check-portable-text-sync.sh, which gates the skill against the portable text by
recorded hash and deliberate review.

Exit codes:
  0  the page matches and is static
  1  every check was evaluated, and the embedded text drifted, the copy button
     is missing or not first in the block, the stated count is wrong, or inline
     code was reintroduced
  3  a check could not be evaluated. Before any check runs, the gate stops on
     2 conditions: the download or the page is missing or not a regular file,
     or the download could not be read or decoded. While the checks run, it
     collects these refusals: the embedded block was not found exactly once;
     the stated count was not found exactly once; tools/check-inline-code.py is
     not a regular file, could not be read, raised an exception while it
     loaded, defines no inline_code_problems, or defines no UnsupportedPython
     that is an exception class; tools/check-inline-code.py raised an
     exception while it checked the page or while its problems were read, or
     gave a problem that str() does not turn into text; or the Python version
     is 3.7 or later and not one that tools/check-inline-code.py supports

A symbolic link is not followed: a download, a page or
tools/check-inline-code.py that is a symbolic link is not a regular file,
whatever the link points to, as tools/build-site.py also refuses such a
download.

An exception from tools/check-inline-code.py, while it loads or while it
checks the page, is a refusal whatever its class: SystemExit with any code
and any other BaseException subclass included, apart from KeyboardInterrupt,
which is not caught, so that Ctrl-C still stops the gate. An exception whose
repr or str raises is named by its class instead. The gate reads
inline_code_problems and UnsupportedPython from the module's own namespace,
so the gate never calls a module __getattr__.

What still ends otherwise: the page read is not guarded, so a page that
cannot be read or decoded ends in a traceback with exit 1; a KeyboardInterrupt
ends the gate as Python ends on Ctrl-C; and code in tools/check-inline-code.py
that ends the process itself, for example by os._exit, ends the gate with the
code it gives.

Where each report goes: a problem found by a check that was evaluated is
printed on stdout under "Instructions page problems found:", and a check that
could not be evaluated is reported on stderr, prefixed "check-instructions-page: ".
Apart from the 3 paths named in the paragraph above, the gate runs every
check it can evaluate and prints every problem it found before it exits, so a
problem is never hidden behind a refusal collected while the checks run, and
it exits 3 when a check could not be evaluated, whatever else it found. The 2
conditions that stop the gate before any check runs are reported on stderr in
the same way, and no check runs after them.
"""

from __future__ import annotations

import html
import os
import re
import stat
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "site" / "downloads" / "cleanlanguage.md"
PAGE = REPO_ROOT / "site" / "instructions" / "index.html"
# (page, the copy button the template puts first in the block, or None)
COPY_BUTTON = '<button class="copy" type="button" data-copy="instructions-text" hidden>Copy</button>'
PAGES = [(PAGE, COPY_BUTTON)]

# The embedded block. Matched on its id so a class or attribute change does not
# quietly stop this check from finding anything to compare.
EMBEDDED = re.compile(r'<pre id="instructions-text"[^>]*>(.*?)</pre>', re.S)
# The stated count. Matched on the sentence's fixed words over the whole page
# source, so a number in another form beside the sentence is not read as the
# stated count.
STATED = re.compile(r"the same content the full download saves \((\d+) characters\)")
INLINE_GATE = Path(__file__).resolve().parent / "check-inline-code.py"
INLINE_RULE = (
    "the site's own pages must not use inline code (template specification, section 5), and this "
    "check and tools/check-inline-code.py enforce that rule"
)


def die(message: str) -> None:
    print(f"check-instructions-page: {message}", file=sys.stderr)
    raise SystemExit(3)


class Refused(Exception):
    """A check that could not be evaluated. check_page() records it and goes on
    with the other checks; main() reports it on stderr and exits 3."""


def described(error: BaseException, form=repr) -> str:
    """The error as text, by repr or by str. An exception whose repr or str raises, or gives something other than
    text, is named by its class instead, so that describing a refusal never ends in a traceback."""
    try:
        text = form(error)
    except KeyboardInterrupt:
        raise
    except BaseException as inner:
        return f"{type(error).__name__} (its {form.__name__} raised {type(inner).__name__})"
    return text if type(text) is str else type(error).__name__


def load_inline_gate():
    """tools/check-inline-code.py, read, compiled and run as a fresh module; returns its inline_code_problems and its
    UnsupportedPython. The source is always read, so no cached bytecode stands in for it. A source that is not a
    regular file, that cannot be read or compiled, or that raises any exception other than KeyboardInterrupt while it
    runs, SystemExit included, means that tools/check-inline-code.py could not be loaded (Refused, exit 3). Both
    names are read from the module's own namespace, so this function never calls a module __getattr__; a namespace
    without either name, or whose UnsupportedPython is not an exception class, is refused too."""
    try:
        info = os.lstat(INLINE_GATE)
    except OSError as error:
        raise Refused(f"tools/check-inline-code.py could not be read: {error}")
    if not stat.S_ISREG(info.st_mode):
        raise Refused("tools/check-inline-code.py is not a regular file")
    try:
        source = INLINE_GATE.read_bytes()
    except OSError as error:
        raise Refused(f"tools/check-inline-code.py could not be read: {error}")
    module = types.ModuleType("check_inline_code")
    module.__file__ = str(INLINE_GATE)
    try:
        exec(compile(source, str(INLINE_GATE), "exec", dont_inherit=True), module.__dict__)
    except KeyboardInterrupt:
        raise
    except BaseException as error:
        raise Refused(f"tools/check-inline-code.py could not be loaded: {described(error)}")
    namespace = module.__dict__
    for attribute in ("inline_code_problems", "UnsupportedPython"):
        if attribute not in namespace:
            raise Refused(f"tools/check-inline-code.py defines no {attribute}")
    unsupported = namespace["UnsupportedPython"]
    # type() and issubclass() on classes run none of the file's code, which isinstance() could through __class__.
    if not (issubclass(type(unsupported), type) and issubclass(unsupported, BaseException)):
        raise Refused("tools/check-inline-code.py defines an UnsupportedPython that is not an exception class")
    return namespace["inline_code_problems"], unsupported


def inline_code_problems(text: str) -> list[str]:
    """Check 2: each piece of inline code, read with tools/check-inline-code.py. Its UnsupportedPython is a refusal in
    that file's own words. Any other exception raised while it checks the page or while its problems are read and
    turned into text by str(), SystemExit and other BaseException subclasses included, and a problem that str() does
    not turn into text, means that check 2 could not be evaluated (Refused, exit 3), so a wrong count found by check 3
    is still printed. KeyboardInterrupt is not caught, so that Ctrl-C still stops the gate."""
    reader, unsupported = load_inline_gate()
    try:
        problems = []
        for problem in reader(text):
            problem = str(problem)
            if type(problem) is not str:
                raise TypeError(f"a problem is {type(problem).__name__}, not str")
            problems.append(problem)
        return problems
    except KeyboardInterrupt:
        raise
    except unsupported as error:
        raise Refused(f"tools/check-inline-code.py {described(error, str)}")
    except BaseException as error:
        raise Refused(f"tools/check-inline-code.py could not check the page: {described(error)}")


def first_difference(a: str, b: str) -> str:
    for index, (left, right) in enumerate(zip(a, b)):
        if left != right:
            line = a.count("\n", 0, index) + 1
            return (
                f"first difference at character {index}, line {line}: "
                f"page has {left!r}, file has {right!r}"
            )
    longer = "page" if len(a) > len(b) else "file"
    return f"one is a prefix of the other; the {longer} is longer by {abs(len(a) - len(b))} characters"


def main() -> int:
    for path in (SOURCE, *(page for page, _ in PAGES)):
        try:
            info = os.lstat(path)
        except OSError:
            die(f"{path.relative_to(REPO_ROOT)} does not exist")
        if not stat.S_ISREG(info.st_mode):
            die(f"{path.relative_to(REPO_ROOT)} is not a regular file")

    try:
        saved = len(SOURCE.read_bytes().decode("utf-8"))
        expected = SOURCE.read_text(encoding="utf-8").rstrip("\n")
    except (OSError, UnicodeError) as error:
        die(f"{SOURCE.relative_to(REPO_ROOT)} could not be read: {error}")
    problems: list[str] = []
    refusals: list[str] = []
    for page, button in PAGES:
        page_problems, page_refusals = check_page(page, button, expected, saved)
        problems += page_problems
        refusals += page_refusals

    if problems:
        print("Instructions page problems found:")
        for problem in problems:
            print(f"  - {problem}")
    for refusal in refusals:
        print(f"check-instructions-page: {refusal}", file=sys.stderr)
    if refusals:
        return 3
    if problems:
        return 1

    print(
        f"The instructions page embeds the portable text exactly "
        f"({len(expected)} characters without the final newline), states the "
        f"download's {saved} characters and carries no inline code."
    )
    return 0


def check_page(page: Path, button: str | None, expected: str, saved: int) -> tuple[list[str], list[str]]:
    """The problems found on the page, and the refusals: the checks that could
    not be evaluated. A refusal never stops the checks that can still be
    evaluated."""
    name = page.relative_to(REPO_ROOT)
    page_text = page.read_text(encoding="utf-8")
    problems: list[str] = []
    refusals: list[str] = []

    matches = list(EMBEDDED.finditer(page_text))
    if len(matches) != 1:
        refusals.append(
            'expected exactly 1 <pre id="instructions-text"> block in '
            f"{name}, found {len(matches)}"
        )
    else:
        raw = matches[0].group(1)
        if button is not None:
            if not raw.startswith(button):
                problems.append(f"{name}: the block does not start with the template's copy button {button!r}.")
            else:
                raw = raw[len(button):]
        embedded = html.unescape(raw).rstrip("\n")

        if embedded != expected:
            problems.append(
                f"{name}: the embedded text does not match "
                f"{SOURCE.relative_to(REPO_ROOT)} ({len(embedded)} characters embedded, "
                f"{len(expected)} in the file); {first_difference(embedded, expected)}. "
                "Re-embed the file's contents in the page."
            )

    stated = STATED.findall(page_text)
    if len(stated) != 1:
        refusals.append(f"expected exactly 1 stated count of the full download in {name}, found {len(stated)}")
    # Compared as text, not by int(), which refuses more than 4300 digits by raising ValueError.
    elif stated[0] != str(saved):
        shown = stated[0] if len(stated[0]) <= 40 else f"{stated[0][:20]}... ({len(stated[0])} digits)"
        problems.append(
            f"{name}: the page states {shown} characters for the full download, but "
            f"{SOURCE.relative_to(REPO_ROOT)} holds {saved}. Rebuild the page with tools/build-site.py."
        )

    try:
        problems += [f"{name} {problem}; {INLINE_RULE}." for problem in inline_code_problems(page_text)]
    except Refused as refusal:
        refusals.append(str(refusal))

    return problems, refusals


if __name__ == "__main__":
    sys.exit(main())
