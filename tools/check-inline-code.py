#!/usr/bin/env python3
"""Refuse inline code in every HTML page under site/, live and draft.

The site's own pages carry no inline code (template specification, section 5):
every script loads from a file, and every style comes from a stylesheet. The
site-wide security policy allows ``'unsafe-inline'`` scripts, because Cloudflare's
own scripts need it, so a browser no longer blocks an inline script or an inline
event handler on these pages. This gate enforces the rule instead.

What it verifies
----------------

It reads every ``.html`` and ``.htm`` file under ``site/``, at any depth, with
Python's HTML parser (``html.parser``), and refuses:

1. A ``<script>`` element without a ``src`` attribute, whatever its ``type``,
   unless its first ``type`` attribute is ``application/ld+json`` (ignoring case
   and surrounding whitespace). That is a structured-data block, which the
   browser never runs. A browser uses the first of 2 attributes with the same
   name, and so does this check. A ``<script>`` element with ``src`` that also
   holds text other than whitespace fails too: the browser ignores that text,
   so it can only be dead code or a decoy.
2. Any attribute whose name starts with ``on``, on any element. The parser reads
   ``/`` as an attribute separator, as a browser does, so
   ``<span/onclick="...">`` counts.
3. A ``javascript:`` URL in an ``href``, ``xlink:href``, ``src``, ``action`` or
   ``formaction`` attribute, after character references are decoded, leading and
   trailing control characters and spaces are removed, and every tab, line feed
   and carriage return is removed, as a browser does before it reads the scheme.
   The scheme compares without regard to case.
4. Any ``<style>`` element and any ``style`` attribute.
5. A page where the number of ``<script`` and ``<style`` start tags found by a
   plain text count, ignoring case, differs from the number the parser reports.
   This catches markup that the parser reads differently from a browser, such
   as a script the parser takes to be inside a comment.

What it does not verify
-----------------------

It reads files only; it runs no browser. ``html.parser`` is not the HTML
parsing algorithm of the specification, so markup built to make the 2 disagree
can still slip past checks 1 to 4. Check 5 narrows that for script and style
elements only; it does not cover event-handler attributes or URLs. The gate
does not judge external scripts (the ``src`` value, the files under
``site/js/`` or ``site/draft/assets/``), other URL schemes such as ``data:``,
``<iframe srcdoc>``, ``<meta http-equiv="refresh">`` or SVG animation
attributes. The security policy covers the frame, image and object cases:
``default-src 'none'`` blocks frames and objects, and ``img-src 'self'`` blocks
``data:`` images. It does not read files other than HTML pages, so a page served
from another extension is outside it.

Exit codes:
  0  no page carries inline code
  1  a page carries inline code, or the parser and the text count disagree
  3  site/ or a page could not be read, a page is not UTF-8, or no page was found
"""

from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
SUFFIXES = (".html", ".htm")

DATA_BLOCK_TYPE = "application/ld+json"
URL_ATTRIBUTES = ("href", "xlink:href", "src", "action", "formaction")
# A browser removes leading and trailing C0 controls and spaces from a URL, and
# every ASCII tab or newline inside it, before it reads the scheme.
URL_EDGES = "".join(chr(code) for code in range(0x21))
URL_REMOVED = re.compile(r"[\t\n\r]")
RAW_START = re.compile(r"<(script|style)(?=[\s/>])", re.I)

RULE = (
    "the site's own pages must not use inline code (template specification, section 5), "
    "and this gate enforces that rule"
)


def die(message: str) -> None:
    print(f"check-inline-code: {message}", file=sys.stderr)
    raise SystemExit(3)


def is_javascript_url(value: str) -> bool:
    return URL_REMOVED.sub("", value.strip(URL_EDGES)).lower().startswith("javascript:")


class InlineCodeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.starts = {"script": 0, "style": 0}
        self.external_script: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.element(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.element(tag, attrs)
        self.external_script = None

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.external_script = None

    def handle_data(self, data: str) -> None:
        if self.external_script is not None and data.strip():
            self.problems.append(f"line {self.external_script}: a <script> element with src that also holds text")
            self.external_script = None

    def element(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        if tag in self.starts:
            self.starts[tag] += 1
        names = [name for name, _ in attrs]
        if tag == "script" and "src" in names:
            self.external_script = line
        if tag == "script" and "src" not in names:
            kind = next((value or "" for name, value in attrs if name == "type"), "")
            if kind.strip(" \t\n\f\r").lower() != DATA_BLOCK_TYPE:
                self.problems.append(f"line {line}: a <script> element without src (type {kind!r})")
        if tag == "style":
            self.problems.append(f"line {line}: a <style> element")
        for name, value in attrs:
            if name.startswith("on"):
                self.problems.append(f"line {line}: an event-handler attribute {name!r} on <{tag}>")
            elif name == "style":
                self.problems.append(f"line {line}: a style attribute on <{tag}>")
            elif name in URL_ATTRIBUTES and value and is_javascript_url(value):
                self.problems.append(f"line {line}: a javascript: URL in the {name} attribute of <{tag}>")


def inline_code_problems(text: str) -> list[str]:
    """Each piece of inline code in an HTML page, as 'line N: ...', with the count check (check 5)."""
    parser = InlineCodeParser()
    parser.feed(text)
    parser.close()
    problems = list(parser.problems)
    for tag in ("script", "style"):
        raw = sum(1 for match in RAW_START.finditer(text) if match.group(1).lower() == tag)
        if raw != parser.starts[tag]:
            problems.append(
                f"a text count finds {raw} <{tag}> start tags but the parser reads {parser.starts[tag]}; "
                "the parser and a browser may read this markup differently, so it cannot be checked"
            )
    return problems


def pages() -> list[Path]:
    if not SITE.is_dir():
        die(f"{SITE.relative_to(REPO_ROOT)} is not a directory")

    def fail(error: OSError) -> None:
        die(f"could not list {error.filename}: {error.strerror}")

    found: list[Path] = []
    for folder, _, files in os.walk(SITE, onerror=fail):
        found += [Path(folder) / name for name in files if name.lower().endswith(SUFFIXES)]
    if not found:
        die("found no HTML page under site/")
    return sorted(found)


def main() -> int:
    problems: list[str] = []
    found = pages()
    for page in found:
        where = page.relative_to(REPO_ROOT)
        try:
            text = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            die(f"could not read {where} as UTF-8: {error}")
        problems += [f"{where} {problem}" for problem in inline_code_problems(text)]
    if problems:
        print(f"Inline code found; {RULE}. The security policy allows 'unsafe-inline', so a browser "
              "would run it. Move scripts to files under site/js/ and styles to a stylesheet.")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"No inline code in the {len(found)} HTML pages under site/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
