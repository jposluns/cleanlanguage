#!/usr/bin/env python3
"""Check the instructions page renders the portable text exactly, and statically.

``site/instructions/index.html`` shows the full Clean Language rule set so a
reader can copy it without downloading anything. The text is embedded in the
page rather than fetched at runtime, which means the page now holds a second copy
of ``site/downloads/cleanlanguage-instructions.txt`` and the two can drift. This
check makes that drift fail.

Why the page is static
----------------------

The page used to fetch the text with an inline ``<script>``. The site's
Content-Security-Policy is ``script-src 'self'`` with no ``'unsafe-inline'``,
nonce, or hash, so a compliant browser blocked that script and the page showed
"Loading the instructions..." and nothing else. Its only inline ``style``
attribute was blocked by ``style-src 'self'`` for the same reason. Embedding the
text removes both problems, works with JavaScript switched off, and needs no
loosening of the policy.

So this check also refuses to let that regress: the page must carry no inline
script and no inline style attribute. Reintroducing either would break the page
again in a way that is invisible to every other gate, because the markup is
perfectly valid and the failure happens only in a browser enforcing the policy.

What it verifies
----------------

1. The page embeds the portable text exactly, character for character, once HTML
   escaping is undone.
2. The page contains no inline ``<script>`` element.
3. The page contains no inline ``style`` attribute.

What it does not verify
-----------------------

It compares the page against the portable text file. It says nothing about
whether that file agrees with the packaged skill: that is the separate concern of
check-portable-text-sync.sh, which gates the skill against the portable text by
recorded hash and deliberate review.

Exit codes:
  0  the page matches and is static
  1  the text drifted, or an inline script or style was reintroduced
  3  a file could not be read, or the expected markup was not found
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "site" / "downloads" / "cleanlanguage-instructions.txt"
PAGE = REPO_ROOT / "site" / "instructions" / "index.html"

# The embedded block. Matched on its id so a class or attribute change does not
# quietly stop this check from finding anything to compare.
EMBEDDED = re.compile(r'<pre id="instructions-text"[^>]*>(.*?)</pre>', re.S)
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)
INLINE_STYLE = re.compile(r"<[^>]+\sstyle=", re.I)


def die(message: str) -> None:
    print(f"check-instructions-page: {message}", file=sys.stderr)
    raise SystemExit(3)


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
    for path in (SOURCE, PAGE):
        if not path.is_file():
            die(f"{path.relative_to(REPO_ROOT)} does not exist")

    expected = SOURCE.read_text(encoding="utf-8").rstrip("\n")
    page_text = PAGE.read_text(encoding="utf-8")

    match = EMBEDDED.search(page_text)
    if match is None:
        die(
            'no <pre id="instructions-text"> block found in '
            f"{PAGE.relative_to(REPO_ROOT)}; the page is expected to embed the text"
        )

    embedded = html.unescape(match.group(1)).rstrip("\n")

    problems: list[str] = []

    if embedded != expected:
        problems.append(
            "the embedded text does not match "
            f"{SOURCE.relative_to(REPO_ROOT)} ({len(embedded)} characters embedded, "
            f"{len(expected)} in the file); {first_difference(embedded, expected)}. "
            "Re-embed the file's contents in the page."
        )

    if INLINE_SCRIPT.search(page_text):
        problems.append(
            "the page contains an inline <script>. The site's CSP is "
            "script-src 'self', which blocks it, and the page silently fails to "
            "work in the browser. Move the code to a file under site/js/."
        )

    if INLINE_STYLE.search(page_text):
        problems.append(
            "the page contains an inline style attribute. The site's CSP is "
            "style-src 'self', which blocks it. Move the declarations to "
            "site/styles.css."
        )

    if problems:
        print("Instructions page problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"The instructions page embeds the portable text exactly "
        f"({len(expected)} characters) and carries no inline script or style."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
