#!/usr/bin/env python3
"""Check the instructions page renders the portable text exactly, and statically.

``site/instructions/index.html`` shows the full Clean Language rule set so a
reader can copy it without downloading anything. The text is embedded in the
page rather than fetched at runtime, which means the page now holds a second copy
of ``site/downloads/cleanlanguage.md`` and the two can drift. This
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
  1  the text drifted, or inline code was reintroduced
  3  a file could not be read, tools/check-inline-code.py could not be loaded, the
     expected markup was not found, or the Python version is 3.7 or later and not one
     that tools/check-inline-code.py supports
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
INLINE_GATE = Path(__file__).resolve().parent / "check-inline-code.py"
INLINE_RULE = (
    "the site's own pages must not use inline code (template specification, section 5), and this "
    "check and tools/check-inline-code.py enforce that rule"
)


def die(message: str) -> None:
    print(f"check-instructions-page: {message}", file=sys.stderr)
    raise SystemExit(3)


def load_inline_gate():
    """tools/check-inline-code.py, read, compiled and run as a fresh module. The source is always read, so no cached
    bytecode stands in for it; a source that is not a regular file, or that cannot be read, compiled or run, or that
    defines no inline_code_problems or no UnsupportedPython, means that tools/check-inline-code.py could not be loaded
    (exit 3)."""
    try:
        info = os.lstat(INLINE_GATE)
    except OSError as error:
        die(f"tools/check-inline-code.py could not be read: {error}")
    if not stat.S_ISREG(info.st_mode):
        die("tools/check-inline-code.py is not a regular file")
    try:
        source = INLINE_GATE.read_bytes()
    except OSError as error:
        die(f"tools/check-inline-code.py could not be read: {error}")
    module = types.ModuleType("check_inline_code")
    module.__file__ = str(INLINE_GATE)
    try:
        exec(compile(source, str(INLINE_GATE), "exec", dont_inherit=True), module.__dict__)
    except (Exception, SystemExit) as error:
        die(f"tools/check-inline-code.py could not be loaded: {error!r}")
    for attribute in ("inline_code_problems", "UnsupportedPython"):
        if not hasattr(module, attribute):
            die(f"tools/check-inline-code.py defines no {attribute}")
    return module


def inline_code_problems(text: str) -> list[str]:
    """Check 2: each piece of inline code, read with tools/check-inline-code.py."""
    module = load_inline_gate()
    try:
        return module.inline_code_problems(text)
    except module.UnsupportedPython as error:
        die(f"tools/check-inline-code.py {error}")


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
        if not path.is_file():
            die(f"{path.relative_to(REPO_ROOT)} does not exist")

    expected = SOURCE.read_text(encoding="utf-8").rstrip("\n")
    problems: list[str] = []
    for page, button in PAGES:
        problems += check_page(page, button, expected)

    if problems:
        print("Instructions page problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"The instructions page embeds the portable text exactly "
        f"({len(expected)} characters) and carries no inline code."
    )
    return 0


def check_page(page: Path, button: str | None, expected: str) -> list[str]:
    name = page.relative_to(REPO_ROOT)
    page_text = page.read_text(encoding="utf-8")

    matches = list(EMBEDDED.finditer(page_text))
    if len(matches) != 1:
        die(
            'expected exactly one <pre id="instructions-text"> block in '
            f"{name}, found {len(matches)}"
        )

    raw = matches[0].group(1)
    problems: list[str] = []
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

    problems += [f"{name} {problem}; {INLINE_RULE}." for problem in inline_code_problems(page_text)]

    return problems


if __name__ == "__main__":
    sys.exit(main())
