#!/usr/bin/env python3
"""Refuse inline code in every HTML page and SVG file under site/.

The site's own pages carry no inline code (template specification, section 5):
every script loads from a file, and every style comes from a stylesheet. The
site-wide security policy allows ``'unsafe-inline'`` scripts, because Cloudflare's
own scripts need it, so a browser no longer blocks an inline script or an inline
event handler on these pages. This gate enforces the rule instead.

It reads every ``.html`` and ``.htm`` file under ``site/``, at any depth, with
Python's HTML parser (``html.parser``), and every ``.svg`` file with Python's XML
parser (``xml.parsers.expat``), because a browser reads an SVG file as XML.

HTML pages
----------

The parser reads the content of ``script``, ``style``, ``noscript``, ``title``,
``textarea``, ``xmp``, ``iframe``, ``noembed`` and ``noframes`` as raw text on
every Python version, as a browser with scripting on does (``RAW_TEXT_ELEMENTS``
below). It then reads the raw text of each ``<noscript>`` element again as
markup, with checks 1 to 5 and 10, because a browser with scripting off reads it
that way; checks 6 to 9 read the whole file's text, which holds that content. In
every HTML page it refuses:

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
3. A ``javascript:`` URL in an ``href``, ``src``, ``action`` or ``formaction``
   attribute, or in any attribute whose name ends in ``:href`` (such as
   ``xlink:href``), after character references are decoded, leading and trailing
   control characters and spaces are removed, and every tab, line feed and
   carriage return is removed, as a browser does before it reads the scheme.
   The scheme compares without regard to case.
4. Any ``<style>`` element and any ``style`` attribute.
5. Any ``srcdoc`` attribute, on any element. (An ``<animate>`` or ``<set>``
   element can change a link only inside ``<svg>``, which check 7 refuses.)
6. A page where a plain text count differs from what the parser reports: the
   number of ``<script`` and ``<style`` start tags, ignoring case, or the number
   of ``on`` attributes, counted anywhere in the file's text as ``on`` followed by
   ASCII letters and ``=`` (with optional whitespace before the ``=``), ignoring
   case, after whitespace, a ``/`` or a quote. The parser's counts include those
   of each ``<noscript>`` content read as markup. This catches markup that the
   parser reads differently from a browser, such as an element the parser takes
   to be text, whatever the shape of the tag around it. Prose that contains such
   a sequence also fails this check; write it with a character reference (for
   example ``on&#x63;lick=``).
7. The elements ``svg``, ``math``, ``iframe``, ``textarea``, ``xmp``,
   ``noembed``, ``noframes``, ``plaintext`` and ``template``, found in the
   text as ``<`` and the name, ignoring case, followed by whitespace, ``/``,
   ``>`` or the end of the text. The parser reads them differently from a
   browser, and no page uses them.
8. Any ``<![CDATA[`` in the text, ignoring case.
9. Any comment that opens as ``<!-->`` or ``<!--->``.
10. On every page, a ``<script>`` element whose first ``src`` is not a
    same-origin path: after the URL clean-up of check 3, it must start with
    ``/`` and not with ``//`` or ``/\\``. This check reads the committed source
    files only. Cloudflare injects its own scripts into the pages it serves (the
    Web Analytics beacon from ``https://static.cloudflareinsights.com`` and the
    JavaScript Detections loader), which the site-wide security policy allows,
    so a served page does load a script from another origin; no committed page
    may. The install pages keep their own list of allowed scripts
    (``tools/check-install-page.py`` check 6).

SVG files
---------

A file that holds ``<!DOCTYPE`` or ``<!ENTITY``, ignoring case, fails before it
is parsed, because an XML internal entity can carry markup, so no entity is ever
expanded. The XML parser then reads the file with namespaces resolved; a file it
refuses fails, and so does any processing instruction. Each check below applies
to an element's or attribute's local name, whatever its namespace prefix:

11. Any element outside the SVG namespace (``http://www.w3.org/2000/svg``),
    including one with no namespace. That covers an XHTML ``<script>`` or any
    other element from a second vocabulary.
12. Any ``script``, ``style`` or ``foreignObject`` element.
13. Any attribute whose local name starts with ``on``, ignoring case, any
    attribute whose local name is ``style`` or ``srcdoc``, and a ``javascript:``
    URL (cleaned up as in check 3) in any attribute whose local name is
    ``href``, ``src``, ``action`` or ``formaction``, in any namespace (so
    ``xlink:href`` and any other prefix count).
14. An ``animate`` or ``set`` element whose ``attributeName`` is ``href`` or
    ends in ``:href``, ignoring case and surrounding whitespace, because it can
    change a link to a ``javascript:`` URL after the file loads.

Python versions
---------------

The gate runs only on Python 3.14 (``SUPPORTED_PYTHONS`` below), the version its
guarantees are stated for; on any other version, 3.7 or later, it exits 3
before it reads a file. Python 3.6 and older cannot compile the file, which
imports ``annotations`` from ``__future__``, so they exit 1 instead. The gate
prints the Python version it ran under. The raw-text element list is
set on the HTML parser, so the reading of those elements does not depend on the
version. Other ``html.parser`` behaviour does change between versions: how a
comment ends (``--!>``), how a ``<!`` declaration or a ``<![CDATA[`` section is
read, which end tags close a raw-text element, and how an unfinished tag at the
end of a file is reported (3.14 changed these). Checks 6 to 9 are plain text
checks, which read the same on every version, and they refuse or count the cases
where those changes matter for script, style and ``on`` attributes. A
``javascript:`` URL or a ``srcdoc`` attribute inside such markup stays
version-dependent. The XML parser follows the XML specification on every
version.

``inline_code_problems`` makes the same version check and raises
``UnsupportedPython``, so the tools that load it as a module refuse another
version too, each with exit 3 and its own message from Python 3.7 on (3.9 for
``tools/check-install-page.py``, whose docstring says why).
``tools/check-instructions-page.py`` refuses through that exception.
``tools/check-install-page.py`` has its own version guard, which fires first,
before it reads a file; it catches the exception too, should the two lists of
supported versions part (its docstring, Python versions).

The check reads the minor version only, so it admits every 3.14 release, and
``html.parser`` has changed within a minor version before. A pass of
``tools/test-inline-code.py`` is evidence only for the interpreter it ran on.
The Site hardening workflow runs the suite on the same interpreter just before
the gate; the Pages build and the tools that load the module do not.

What it does not verify
-----------------------

It reads files only; it runs no browser. ``html.parser`` is not the HTML
parsing algorithm of the specification, so markup built to make them disagree
can still slip past checks 1 to 5 in an HTML page. Checks 6 to 9 narrow that:
check 6 compares counts only for script and style start tags and for ``on``
attributes, so a ``javascript:`` URL or a ``srcdoc`` attribute that the parser
reads as text is outside it. The gate does not judge the files that external
scripts load (under ``site/assets/baseline/``), other URL schemes such as
``data:``, ``<meta
http-equiv="refresh">``, or animation of attributes other than ``href``. The
security policy covers some of those cases: ``default-src 'none'`` blocks
frames and objects, and ``img-src 'self'`` blocks ``data:`` images. It does not
read files other than HTML pages and SVG files, so a document served from
another extension is outside it.

Exit codes:
  0  no file carries inline code
  1  a file carries inline code or refused markup, the parser and a text count disagree, or the XML parser refuses an SVG file
  3  site/ or a file could not be read, a file is not UTF-8, no HTML page was found, or the Python
     version is 3.7 or later and not a supported one
"""

from __future__ import annotations

import os
import platform
import re
import sys
import xml.parsers.expat
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
PAGE_SUFFIXES = (".html", ".htm")
SVG_SUFFIX = ".svg"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
# The (major, minor) versions the gate runs on: the versions the docstring's guarantees
# are stated for. main() and inline_code_problems() refuse every other version, so the
# module loaders in check-install-page.py and check-instructions-page.py refuse it too.
# Every patch release of these versions passes the check; tools/test-inline-code.py is
# evidence only for the interpreter it ran on (docstring, Python versions).
SUPPORTED_PYTHONS = ((3, 14),)

DATA_BLOCK_TYPE = "application/ld+json"
URL_ATTRIBUTES = ("href", "src", "action", "formaction")
ANIMATION_ELEMENTS = ("animate", "set")
SVG_REFUSED_ELEMENTS = ("script", "style", "foreignObject")
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


class UnsupportedPython(Exception):
    """Raised by inline_code_problems on a Python version outside SUPPORTED_PYTHONS."""


def die(message: str) -> None:
    print(f"check-inline-code: {message}", file=sys.stderr)
    raise SystemExit(3)


def python_problem() -> str | None:
    """Why this Python version is not a supported one, or None when it is."""
    if sys.version_info[:2] in SUPPORTED_PYTHONS:
        return None
    supported = ", ".join(f"{major}.{minor}" for major, minor in SUPPORTED_PYTHONS)
    return (f"runs only on Python {supported}, the versions its guarantees are stated for; "
            f"this is Python {sys.version_info[0]}.{sys.version_info[1]}")


def clean_url(value: str) -> str:
    return URL_REMOVED.sub("", value.strip(URL_EDGES))


def is_javascript_url(value: str) -> bool:
    return clean_url(value).lower().startswith("javascript:")


def is_same_origin_path(value: str) -> bool:
    url = clean_url(value)
    return url.startswith("/") and not url.startswith(("//", "/\\"))


def is_href_name(name: str) -> bool:
    return name == "href" or name.endswith(":href")


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


class InlineCodeParser(HTMLParser):
    CDATA_CONTENT_ELEMENTS = RAW_TEXT_ELEMENTS
    RCDATA_CONTENT_ELEMENTS = ()

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
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
        inner = scan(text)
        self.starts = {tag: count + inner.starts[tag] for tag, count in self.starts.items()}
        self.handlers += inner.handlers
        # Checks 6 to 9 read the whole file's text, which holds this content, so only the parser checks run here.
        for problem in inner.problems:
            self.problems.append(f"line {line}: inside <noscript>, read as markup, {problem}")

    def element(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        if tag in self.starts:
            self.starts[tag] += 1
        self.handlers += sum(1 for name, _ in attrs if name.startswith("on"))
        names = [name for name, _ in attrs]
        if tag == "script" and "src" in names:
            self.external_script = line
            src = next(value or "" for name, value in attrs if name == "src")
            if not is_same_origin_path(src):
                self.problems.append(f"line {line}: a <script> loads {src!r}, which is not a same-origin path")
        elif tag == "script":
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
            elif name == "srcdoc":
                self.problems.append(f"line {line}: a srcdoc attribute on <{tag}>")
            elif (name in URL_ATTRIBUTES or is_href_name(name)) and value and is_javascript_url(value):
                self.problems.append(f"line {line}: a javascript: URL in the {name} attribute of <{tag}>")


def scan(text: str) -> InlineCodeParser:
    parser = InlineCodeParser()
    parser.feed(text)
    parser.close()
    return parser


def count_problems(text: str, parser: InlineCodeParser) -> list[str]:
    """Check 6: the plain text counts against the parser's counts."""
    problems = []
    for tag in ("script", "style"):
        raw = sum(1 for match in RAW_START.finditer(text) if match.group(1).lower() == tag)
        if raw != parser.starts[tag]:
            problems.append(
                f"a text count finds {raw} <{tag}> start tags but the parser reads {parser.starts[tag]}; "
                "the parser and a browser may read this markup differently, so it cannot be checked"
            )
    raw_handlers = len(RAW_HANDLER.findall(text))
    if raw_handlers != parser.handlers:
        problems.append(
            f"a text count finds {raw_handlers} on* attributes in the file's text but the parser reads "
            f"{parser.handlers}; the parser and a browser may read this markup differently, so it cannot be checked"
        )
    return problems


def markup_problems(text: str) -> list[str]:
    """Checks 7 to 9: markup that the parser reads differently from a browser, in an HTML page."""
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


def split_name(name: str) -> tuple[str, str]:
    """(namespace, local name) of an expat name; the namespace is '' when there is none."""
    namespace, _, local = name.rpartition(" ")
    return namespace, local


def svg_problems(text: str) -> list[str]:
    """Checks 11 to 14: an SVG file read with the XML parser, namespaces resolved, entities never expanded."""
    declarations = [
        f"line {line_of(text, match.start())}: a <!{match.group(1).upper()} declaration in an SVG file"
        for match in RAW_SVG_DECLARATION.finditer(text)
    ]
    if declarations:
        return declarations
    problems: list[str] = []
    parser = xml.parsers.expat.ParserCreate(namespace_separator=" ")

    def where() -> str:
        return f"line {parser.CurrentLineNumber}"

    def declaration(*_) -> None:
        problems.append(f"{where()}: a document type or entity declaration in an SVG file")

    def instruction(target: str, _data: str) -> None:
        problems.append(f"{where()}: a processing instruction <?{target} ...?> in an SVG file")

    def start(name: str, attrs: dict[str, str]) -> None:
        namespace, local = split_name(name)
        if namespace != SVG_NAMESPACE:
            problems.append(f"{where()}: an element <{local}> in the namespace {namespace or '(none)'!r}; "
                            "an SVG file may hold only SVG elements")
        if local in SVG_REFUSED_ELEMENTS:
            problems.append(f"{where()}: a <{local}> element in an SVG file")
        if local in ANIMATION_ELEMENTS:
            target = next((value for key, value in attrs.items() if split_name(key) == ("", "attributeName")), "")
            if is_href_name(target.strip().lower()):
                problems.append(f"{where()}: an <{local}> element that animates {target!r}")
        for key, value in attrs.items():
            lower = split_name(key)[1].lower()
            if lower.startswith("on"):
                problems.append(f"{where()}: an event-handler attribute {key!r} on <{local}>")
            elif lower in ("style", "srcdoc"):
                problems.append(f"{where()}: a {lower} attribute on <{local}>")
            elif lower in URL_ATTRIBUTES and is_javascript_url(value):
                problems.append(f"{where()}: a javascript: URL in the {key!r} attribute of <{local}>")

    parser.StartDoctypeDeclHandler = declaration
    parser.EntityDeclHandler = declaration
    parser.ProcessingInstructionHandler = instruction
    parser.StartElementHandler = start
    try:
        parser.Parse(text.encode("utf-8"), True)
    except xml.parsers.expat.ExpatError as error:
        problems.append(f"line {error.lineno}: the XML parser refuses the file ({xml.parsers.expat.ErrorString(error.code)})")
    return problems


def inline_code_problems(text: str, svg: bool = False) -> list[str]:
    """Each piece of inline code or refused markup in a file, as 'line N: ...'; raises UnsupportedPython."""
    unsupported = python_problem()
    if unsupported:
        raise UnsupportedPython(unsupported)
    if svg:
        return svg_problems(text)
    parser = scan(text)
    return parser.problems + count_problems(text, parser) + markup_problems(text)


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
    unsupported = python_problem()
    if unsupported:
        die(unsupported)
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
              "browser would run it. Load scripts from files under site/assets/baseline/ and styles from a stylesheet.")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"No inline code in the {len(pages)} HTML pages and {len(svgs)} SVG files under site/ ({version}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
