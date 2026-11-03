#!/usr/bin/env python3
"""Refuse inline code in every HTML page and SVG file under site/, live and draft.

The site's own pages carry no inline code (template specification, section 5):
every script loads from a file, and every style comes from a stylesheet. The
site-wide security policy allows ``'unsafe-inline'`` scripts, because Cloudflare's
own scripts need it, so a browser no longer blocks an inline script or an inline
event handler on these pages. This gate enforces the rule instead.

What it verifies
----------------

It reads every ``.html``, ``.htm`` and ``.svg`` file under ``site/``, at any
depth, with Python's HTML parser (``html.parser``). In an HTML page the parser
reads the content of ``script``, ``style``, ``noscript``, ``title``,
``textarea``, ``xmp``, ``iframe``, ``noembed`` and ``noframes`` as raw text on
every Python version, as a browser with scripting on does
(``RAW_TEXT_ELEMENTS`` below). It then reads the raw text of each
``<noscript>`` element again as markup, with checks 1 to 6 below, because a
browser with scripting off reads it that way; checks 7 to 9 read the whole
file's text, which holds that content. An SVG file is XML, which has no
raw-text elements, so the parser reads all of it as markup. In every file it
refuses:

1. A ``<script>`` element without a ``src`` attribute, whatever its ``type``,
   unless its first ``type`` attribute is ``application/ld+json`` (ignoring case
   and surrounding whitespace). That is a structured-data block, which the
   browser never runs. A browser uses the first of 2 attributes with the same
   name, and so does this check. A ``<script>`` element with ``src`` that also
   holds text other than whitespace fails too: the browser ignores that text,
   so it can only be dead code or a decoy. In an SVG file every ``<script>``
   element fails, with or without ``src``.
2. Any attribute whose name starts with ``on``, on any element. The parser reads
   ``/`` as an attribute separator, as a browser does, so
   ``<span/onclick="...">`` counts.
3. A ``javascript:`` URL in an ``href``, ``src``, ``action`` or ``formaction``
   attribute, or in any attribute whose name ends in ``:href`` (such as
   ``xlink:href``), after character references are decoded, leading and trailing
   control characters and spaces are removed, and every tab, line feed and
   carriage return is removed, as a browser does before it reads the scheme.
   The scheme compares without regard to case.
4. Any ``<style>`` element and any ``style`` attribute.
5. Any ``srcdoc`` attribute, on any element.
6. An ``<animate>`` or ``<set>`` element whose first ``attributeName`` is
   ``href`` or ends in ``:href``, ignoring case and surrounding whitespace,
   because it can change a link to a ``javascript:`` URL after the page loads.
7. A file where a plain text count differs from what the parser reports: the
   number of ``<script`` and ``<style`` start tags, ignoring case, or the number
   of ``on`` attributes, counted as ``on`` followed by letters and ``=`` (with
   optional whitespace before the ``=``), ignoring case, after whitespace, a
   ``/`` or a quote inside a tag. A tag, for this count, is a ``<`` and an ASCII
   letter up to the next ``>`` that is not inside a pair of single or double
   quotes, so a quoted ``>`` does not end it. The parser's counts include those
   of each ``<noscript>`` content read as markup. This catches markup that the
   parser reads differently from a browser, such as an element the parser takes
   to be text.

In an HTML page it also refuses markup that ``html.parser`` reads differently
from a browser, and that no page uses, anywhere in the file's text:

8. The elements ``svg``, ``math``, ``iframe``, ``textarea``, ``xmp``,
   ``noembed``, ``noframes``, ``plaintext`` and ``template``, found in the
   text as ``<`` and the name, ignoring case, followed by whitespace, ``/``,
   ``>`` or the end of the text.
9. Any ``<![CDATA[`` in the text, ignoring case, and any comment that opens as
   ``<!-->`` or ``<!--->``.

In an SVG file it also refuses:

10. Any ``<!DOCTYPE`` or ``<!ENTITY``, ignoring case, because an XML internal
    entity can carry markup that this parser never expands.

Python versions
---------------

The gate prints the Python version it ran under. The raw-text element list above
is set on the parser, so the reading of those elements does not depend on the
version. Other ``html.parser`` behaviour does change between versions: how a
comment ends (``--!>``), how a ``<!`` declaration or a ``<![CDATA[`` section is
read, which end tags close a raw-text element, and how an unfinished tag at the
end of a file is reported (3.14 changed these). Checks 7 to 9 are plain text
checks, which read the same on every version, and they refuse or count the cases
where those changes matter for script, style and ``on`` attributes. A
``javascript:`` URL or a ``srcdoc`` attribute inside such markup stays
version-dependent, as the next section states.

What it does not verify
-----------------------

It reads files only; it runs no browser. ``html.parser`` is not the HTML
parsing algorithm of the specification, nor an XML parser, so markup built to
make them disagree can still slip past checks 1 to 6. Checks 7 to 10 narrow that:
check 7 compares counts only for script and style start tags and for ``on``
attributes, so a ``javascript:`` URL or a ``srcdoc`` attribute that the parser
reads as text is outside it. The gate does not judge external scripts (the
``src`` value, the files under ``site/js/`` or ``site/draft/assets/``), other
URL schemes such as ``data:``, ``<meta http-equiv="refresh">``, or SVG
animation of attributes other than ``href``. The security policy covers some of
those cases: ``default-src 'none'`` blocks frames and objects, and ``img-src
'self'`` blocks ``data:`` images. It does not read files other than HTML pages
and SVG files, so a document served from another extension is outside it.

Exit codes:
  0  no file carries inline code
  1  a file carries inline code or refused markup, or the parser and a text count disagree
  3  site/ or a file could not be read, a file is not UTF-8, or no HTML page was found
"""

from __future__ import annotations

import os
import platform
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
PAGE_SUFFIXES = (".html", ".htm")
SVG_SUFFIX = ".svg"

DATA_BLOCK_TYPE = "application/ld+json"
URL_ATTRIBUTES = ("href", "src", "action", "formaction")
ANIMATION_ELEMENTS = ("animate", "set")
# Elements whose content the parser reads as raw text, on every Python version. A browser with
# scripting on reads noscript this way; title and textarea are RCDATA in a browser, which holds no
# tags either. Python 3.14 reads title and textarea as RCDATA and xmp, iframe, noembed and noframes
# as raw text by default; earlier versions read only script and style as raw text.
RAW_TEXT_ELEMENTS = ("script", "style", "noscript", "title", "textarea", "xmp", "iframe", "noembed", "noframes")
# A browser removes leading and trailing C0 controls and spaces from a URL, and
# every ASCII tab or newline inside it, before it reads the scheme.
URL_EDGES = "".join(chr(code) for code in range(0x21))
URL_REMOVED = re.compile(r"[\t\n\r]")
RAW_START = re.compile(r"<(script|style)(?=[\s/>])", re.I)
RAW_TAG = re.compile(r"<[A-Za-z](?:[^>\"']|\"[^\"]*\"|'[^']*')*>")
RAW_HANDLER = re.compile(r"(?<=[\s/\"'])on[a-z]+\s*=", re.I)
REFUSED_ELEMENTS = ("svg", "math", "iframe", "textarea", "xmp", "noembed", "noframes", "plaintext", "template")
RAW_REFUSED_ELEMENT = re.compile(r"<(" + "|".join(REFUSED_ELEMENTS) + r")(?=[\s/>]|$)", re.I)
RAW_CDATA = re.compile(r"<!\[CDATA\[", re.I)
RAW_SHORT_COMMENT = re.compile(r"<!---?>")
RAW_SVG_DECLARATION = re.compile(r"<!(DOCTYPE|ENTITY)", re.I)

RULE = (
    "the site's own pages must not use inline code (template specification, section 5), "
    "and this gate enforces that rule"
)


def die(message: str) -> None:
    print(f"check-inline-code: {message}", file=sys.stderr)
    raise SystemExit(3)


def is_javascript_url(value: str) -> bool:
    return URL_REMOVED.sub("", value.strip(URL_EDGES)).lower().startswith("javascript:")


def is_href_name(name: str) -> bool:
    return name == "href" or name.endswith(":href")


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


class InlineCodeParser(HTMLParser):
    CDATA_CONTENT_ELEMENTS = RAW_TEXT_ELEMENTS
    RCDATA_CONTENT_ELEMENTS = ()

    def __init__(self, svg: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.svg = svg
        if svg:
            # XML has no raw-text elements, so an SVG file is read as markup throughout.
            self.CDATA_CONTENT_ELEMENTS = ()
        self.problems: list[str] = []
        self.starts = {"script": 0, "style": 0}
        self.handlers = 0
        self.external_script: int | None = None
        self.noscript: int | None = None
        self.noscript_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.element(tag, attrs)
        if tag == "noscript":
            self.noscript = self.getpos()[0]
            self.noscript_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.element(tag, attrs)
        self.external_script = None

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.external_script = None
        if tag == "noscript":
            self.read_noscript()

    def handle_data(self, data: str) -> None:
        if self.noscript is not None:
            self.noscript_text.append(data)
        if self.external_script is not None and data.strip():
            self.problems.append(f"line {self.external_script}: a <script> element with src that also holds text")
            self.external_script = None

    def close(self) -> None:
        super().close()
        self.read_noscript()

    def read_noscript(self) -> None:
        """Read the raw text of the open <noscript> again as markup, as a browser with scripting off does."""
        if self.noscript is None:
            return
        line, text = self.noscript, "".join(self.noscript_text)
        self.noscript, self.noscript_text = None, []
        inner = scan(text, svg=False)
        self.starts = {tag: count + inner.starts[tag] for tag, count in self.starts.items()}
        self.handlers += inner.handlers
        # Checks 7 to 9 read the whole file's text, which holds this content, so only checks 1 to 6 run here.
        for problem in inner.problems:
            self.problems.append(f"line {line}: inside <noscript>, read as markup, {problem}")

    def element(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        if tag in self.starts:
            self.starts[tag] += 1
        self.handlers += sum(1 for name, _ in attrs if name.startswith("on"))
        names = [name for name, _ in attrs]
        if tag == "script" and self.svg:
            self.problems.append(f"line {line}: a <script> element in an SVG file")
        elif tag == "script" and "src" in names:
            self.external_script = line
        elif tag == "script":
            kind = next((value or "" for name, value in attrs if name == "type"), "")
            if kind.strip(" \t\n\f\r").lower() != DATA_BLOCK_TYPE:
                self.problems.append(f"line {line}: a <script> element without src (type {kind!r})")
        if tag == "style":
            self.problems.append(f"line {line}: a <style> element")
        if tag in ANIMATION_ELEMENTS:
            target = next((value or "" for name, value in attrs if name == "attributename"), "")
            if is_href_name(target.strip().lower()):
                self.problems.append(f"line {line}: an <{tag}> element that animates {target!r}")
        for name, value in attrs:
            if name.startswith("on"):
                self.problems.append(f"line {line}: an event-handler attribute {name!r} on <{tag}>")
            elif name == "style":
                self.problems.append(f"line {line}: a style attribute on <{tag}>")
            elif name == "srcdoc":
                self.problems.append(f"line {line}: a srcdoc attribute on <{tag}>")
            elif (name in URL_ATTRIBUTES or is_href_name(name)) and value and is_javascript_url(value):
                self.problems.append(f"line {line}: a javascript: URL in the {name} attribute of <{tag}>")


def scan(text: str, svg: bool) -> InlineCodeParser:
    parser = InlineCodeParser(svg)
    parser.feed(text)
    parser.close()
    return parser


def count_problems(text: str, parser: InlineCodeParser) -> list[str]:
    """Check 7: the plain text counts against the parser's counts."""
    problems = []
    for tag in ("script", "style"):
        raw = sum(1 for match in RAW_START.finditer(text) if match.group(1).lower() == tag)
        if raw != parser.starts[tag]:
            problems.append(
                f"a text count finds {raw} <{tag}> start tags but the parser reads {parser.starts[tag]}; "
                "the parser and a browser may read this markup differently, so it cannot be checked"
            )
    raw_handlers = sum(len(RAW_HANDLER.findall(tag.group(0))) for tag in RAW_TAG.finditer(text))
    if raw_handlers != parser.handlers:
        problems.append(
            f"a text count finds {raw_handlers} on* attributes inside tags but the parser reads "
            f"{parser.handlers}; the parser and a browser may read this markup differently, so it cannot be checked"
        )
    return problems


def markup_problems(text: str) -> list[str]:
    """Checks 8 and 9: markup that the parser reads differently from a browser, in an HTML page."""
    problems = []
    for match in RAW_REFUSED_ELEMENT.finditer(text):
        problems.append(
            f"line {line_of(text, match.start())}: a <{match.group(1).lower()}> element, which the parser "
            "may read differently from a browser and which no page uses"
        )
    for match in RAW_CDATA.finditer(text):
        problems.append(f"line {line_of(text, match.start())}: a <![CDATA[ section in an HTML page")
    for match in RAW_SHORT_COMMENT.finditer(text):
        problems.append(f"line {line_of(text, match.start())}: a comment that opens as {match.group(0)!r}")
    return problems


def inline_code_problems(text: str, svg: bool = False) -> list[str]:
    """Each piece of inline code or refused markup in a file, as 'line N: ...', with the count checks."""
    parser = scan(text, svg)
    problems = parser.problems + count_problems(text, parser)
    if svg:
        for match in RAW_SVG_DECLARATION.finditer(text):
            problems.append(f"line {line_of(text, match.start())}: a <!{match.group(1).upper()} declaration in an SVG file")
    else:
        problems += markup_problems(text)
    return problems


def files() -> tuple[list[Path], list[Path]]:
    if not SITE.is_dir():
        die(f"{SITE.relative_to(REPO_ROOT)} is not a directory")

    def fail(error: OSError) -> None:
        die(f"could not list {error.filename}: {error.strerror}")

    pages: list[Path] = []
    svgs: list[Path] = []
    for folder, _, names in os.walk(SITE, onerror=fail):
        pages += [Path(folder) / name for name in names if name.lower().endswith(PAGE_SUFFIXES)]
        svgs += [Path(folder) / name for name in names if name.lower().endswith(SVG_SUFFIX)]
    if not pages:
        die("found no HTML page under site/")
    return sorted(pages), sorted(svgs)


def main() -> int:
    problems: list[str] = []
    pages, svgs = files()
    for path in pages + svgs:
        where = path.relative_to(REPO_ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            die(f"could not read {where} as UTF-8: {error}")
        svg = path.name.lower().endswith(SVG_SUFFIX)
        problems += [f"{where} {problem}" for problem in inline_code_problems(text, svg)]
    version = f"Python {platform.python_version()}"
    if problems:
        print(f"Inline code found ({version}); {RULE}. The security policy allows 'unsafe-inline', so a "
              "browser would run it. Move scripts to files under site/js/ and styles to a stylesheet.")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"No inline code in the {len(pages)} HTML pages and {len(svgs)} SVG files under site/ ({version}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
