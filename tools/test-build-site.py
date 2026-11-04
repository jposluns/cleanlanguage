#!/usr/bin/env python3
"""Tests for tools/build-site.py: each refusal fires on a deliberate fault.

Every case copies the generator's inputs into a temporary folder (under
$TMPDIR), applies 1 fault, runs the generator there as a separate process and
asserts its exit code, and for the passing cases, what the output contains.
The first case runs ``--check`` on this repository. The configured base is
``/``; the staged cases first set the base back to ``/draft/`` and drop the
``/draft/`` holding page, as a staging round would. Exit 0 when every case
passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "tools" / "build-site.py"
INPUTS = [
    "site-src",
    "cleanlanguage/skills/cleanlanguage/SKILL.md",
    "cleanlanguage/skills/cleanlanguage/references",
    "site/downloads",
    "site/assets/baseline",
    "site/_headers",
    "site/_redirects",
    "site/robots.txt",
    "site/sitemap.xml",
    "site/.well-known",
    "site/README.md",
    "site/images",
    ".baseline/pin.toml",
    "tools/sitemap-config.json",
]


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    for relative in INPUTS:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)
    return root


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(GENERATOR), "--root", str(root), *args],
        capture_output=True,
        text=True,
    )


def edit(root: Path, relative: str, old: str, new: str, count: int = 1) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if text.count(old) < 1:
        raise AssertionError(f"{old!r} not in {relative}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")


# The sha256 of the light and dark switch of template specification 7.33 (baseline 1.6.0), computed from
# the reference page reference/install.html line 18 (761 bytes, from <button class="scheme" to </button>).
SWITCH_SHA256 = "9cbd502757bf584b5b83c5319729a9f33310682f305597b64347bc263f586f00"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_switch(path: Path) -> str:
    """SCHEME_SWITCH as a tool defines it; tools/build-site.py and tools/check-inline-code.py each hold a copy."""
    return load_module(path).SCHEME_SWITCH


SWITCH = module_switch(GENERATOR)


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# The start tags HTML5 allows in a head; any other start tag ends it, as text other than whitespace does.
HEAD_TAGS = {"base", "basefont", "bgsound", "link", "meta", "noframes", "noscript", "script", "style", "template", "title"}
# The elements whose content a browser with scripting on (the only case in which scheme.js runs) does not render as
# page elements (noscript, template, plaintext, the raw-text and RCDATA elements) or renders only as fallback,
# only in its control or not at all (the other elements of tools/check-install-page.py's HIDING_ELEMENTS: audio,
# canvas, datalist, meter, object, progress, rp, select and video). No switch counts as placed inside one.
ADDED_INERT = ("audio", "canvas", "datalist", "meter", "object", "progress", "rp", "select", "video")
INERT = {"noscript", "template", "script", "style", "title", "textarea", "xmp", "iframe", "noembed", "noframes", "plaintext",
         *ADDED_INERT}
# HTML separates class names by ASCII whitespace only; str.split() also splits on U+00A0 and other spaces.
ASCII_WHITESPACE = re.compile(r"[ \t\n\f\r]+")
# The header block as the generator's mast() is meant to write it, pinned here apart from the generator: only the
# values come from site.json (base path, name, tld, GitHub URL and nav pages, aria-current on the page's own entry).
MAST_BLOCK = (
    '<header class="mast"><a class="brand" href="{base}"><span class="name">{name}<span class="tld">{tld}</span></span>'
    '<span class="rule" aria-hidden="true"></span></a><nav class="nav" aria-label="Site">{items}'
    '<a href="{github}" target="_blank" rel="noopener noreferrer">GitHub<span class="vh"> (opens in a new tab)</span></a>'
    "</nav>{switch}</header>"
)
SKIP_LINK = '<a class="skip" href="#main-content">Skip to content</a>'


def class_names(value: str) -> list[str]:
    return [name for name in ASCII_WHITESPACE.split(value) if name]


def pinned_mast(config: dict, page: str, base: str) -> str:
    """MAST_BLOCK for the generated page at page (such as license/index.html), with the values site.json gives."""
    pages_by_id = {entry["id"]: entry for entry in config["pages"]}
    own = next((entry["id"] for entry in config["pages"]
                if (entry["path"] if entry["path"].endswith(".html") else entry["path"] + "index.html") == page), None)
    current = ' aria-current="page"'
    items = "".join(
        f'<a href="{base}{pages_by_id[page_id]["path"]}"{current if page_id == own else ""}>'
        f'{html.escape(pages_by_id[page_id]["nav_label"], quote=False)}</a>' for page_id in config["nav"])
    return MAST_BLOCK.format(base=base, name=config["name"], tld=config["tld"], items=items, github=config["github"],
                             switch=SWITCH)


class Placement(HTMLParser):
    """Each start tag's name, attributes (the first of 2 with the same name, as a browser reads them), open
    elements (name, classes), the element before it (name, classes) and whether it starts in html > head, the
    first head or body the page opens, before the head ends where HTML5 ends it (text other than whitespace, a
    start tag not in HEAD_TAGS, or </body>, </html> or </br>); and each end tag's closed element (name, classes,
    depth); keyed by where the tag starts: (line, column), as getpos() reports. A self-closing tag leaves an
    element that is neither void nor in <svg> open, as in a browser, and class names split on ASCII whitespace
    only. It fails closed where it does not model HTML5: a start tag not in HEAD_TAGS inside <template> or
    <noscript> in the head ends the head, and a self-closing tag in <math> leaves its element open. It is not a
    full HTML5 tree builder: it models the open elements as tags nest, void elements, the slash only in <svg> and
    the head's end, so scheme_problems also holds each page's markup from <body> to the end of header.mast, byte for
    byte, to the body start tag, the skip link and MAST_BLOCK, at the start of the page's body (body: a body start
    tag in html right after the only head closes, with no element or text between them, before the head ends). It
    pins nothing after header.mast; the committed pages rest on build-site.py --check and the generator's
    validator."""

    def __init__(self) -> None:
        super().__init__()
        self.open: list[tuple[str, list[str]]] = []
        self.previous: tuple[str, list[str]] | None = None
        self.heads = 0
        self.head_ended = False
        self.body: tuple[int, int] | None = None
        self.starts: dict[tuple[int, int], tuple[str, dict, list[tuple[str, list[str]]], tuple | None, bool]] = {}
        self.ends: dict[tuple[int, int], tuple[str, list[str], int]] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        first = {name: value or "" for name, value in reversed(attrs)}
        if (tag == "body" and [name for name, _ in self.open] == ["html"] and self.heads == 1 and not self.head_ended
                and self.previous is not None and self.previous[0] == "head"):
            self.body = self.getpos()
        if tag in ("head", "body"):
            self.heads += 1
        if tag not in HEAD_TAGS and tag not in ("html", "head"):
            self.head_ended = True
        in_head = [name for name, _ in self.open] == ["html", "head"] and self.heads == 1 and not self.head_ended
        self.starts[self.getpos()] = (tag, first, list(self.open), self.previous, in_head)
        self.previous = (tag, class_names(first.get("class", ""))) if tag in VOID else None
        if tag not in VOID:
            self.open.append((tag, class_names(first.get("class", ""))))

    def handle_startendtag(self, tag: str, attrs) -> None:
        foreign = tag == "svg" or any(name == "svg" for name, _ in self.open)
        self.handle_starttag(tag, attrs)
        if tag not in VOID and foreign:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("body", "html", "br"):
            self.head_ended = True
        if self.open and self.open[-1][0] == tag:
            self.previous = self.open.pop()
            self.ends[self.getpos()] = (*self.previous, len(self.open))

    def handle_data(self, data: str) -> None:
        if data.strip(" \t\n\f\r") and [name for name, _ in self.open] in ([], ["html"], ["html", "head"]):
            self.head_ended = True


def position(text: str, index: int) -> tuple[int, int]:
    return text.count("\n", 0, index) + 1, index - text.rfind("\n", 0, index) - 1


def scheme_problems(page: str, text: str, base: str, config: dict) -> list[str]:
    """Specification 7.33 on 1 generated page, read as parsed elements: the scheme.js line, the only scheme.js
    load, before the stylesheets, it and every stylesheet in html > head; and the switch, the only element with
    data-scheme-toggle (scheme.js wires and shows each), once, the last child of header.mast after nav.nav, with no
    INERT ancestor; and the page's body opening with the skip link and the header.mast block, once and byte for byte
    as MAST_BLOCK pins it."""
    problems = []
    parsed = Placement()
    parsed.feed(text)
    parsed.close()
    line = re.compile(r'^<script data-cfasync="false" src="' + re.escape(base)
                      + r'assets/baseline/scheme\.js\?v=[0-9]+\.[0-9]+\.[0-9]+"></script>$', re.M)
    found = list(line.finditer(text))
    loads = [at for at, (tag, attrs, *_) in parsed.starts.items() if tag == "script"
             and attrs.get("src", "").split("#", 1)[0].split("?", 1)[0] == base + "assets/baseline/scheme.js"]
    sheets = [at for at, (tag, attrs, *_) in parsed.starts.items()
              if tag == "link" and "stylesheet" in attrs.get("rel", "").lower().split()]
    if len(found) != 1 or loads != [position(text, found[0].start())] or text.count("scheme.js") != 1:
        problems.append(f"{page} does not load scheme.js exactly once, with data-cfasync and no defer")
    elif not sheets or loads[0] > sheets[0]:
        problems.append(f"{page} loads scheme.js after the first stylesheet")
    elif not all(parsed.starts[at][4] for at in loads + sheets):
        problems.append(f"{page} loads scheme.js or a stylesheet outside html > head")
    toggles = [at for at, (_, attrs, *_) in parsed.starts.items() if "data-scheme-toggle" in attrs]
    at = text.find(SWITCH)
    _, _, around, before, _ = parsed.starts.get(position(text, at), ("", {}, [], None, False))
    around, before = around or [("", [])], before or ("", [])
    after = parsed.ends.get(position(text, at + len(SWITCH)), ("", [], -1))
    inert = any(name in INERT for start in toggles for name, _ in parsed.starts[start][2])
    if (text.count(SWITCH) != 1 or toggles != [position(text, at)] or inert
            or around[-1][0] != "header" or "mast" not in around[-1][1] or before[0] != "nav" or "nav" not in before[1]
            or after[0] != "header" or after[2] != len(around) - 1):
        problems.append(f"{page} does not end header.mast with the light and dark switch, the only element with "
                        "data-scheme-toggle, exactly once, after nav.nav, outside every element of INERT")
    block = pinned_mast(config, page, base)
    top = "<body>\n" + SKIP_LINK + "\n" + block
    if text.count(block) != 1 or text.count(top) != 1 or position(text, text.find(top)) != parsed.body:
        problems.append(f"{page} does not carry the header block once, byte for byte as MAST_BLOCK pins it, after the "
                        "skip link at the start of the page's body")
    return problems


PAGE = "site-src/pages/demo.html"
ANCHOR = "<p>This pair preserves every fact; only the style changes.</p>"
# A second working switch: scheme.js wires and shows every element with data-scheme-toggle.
TOGGLE = '<p><button class="scheme" type="button" data-scheme-toggle hidden><span class="vh">Dark mode</span></button></p>'


def inject(snippet: str):
    return lambda root: edit(root, PAGE, ANCHOR, ANCHOR + snippet)


HOME = "site-src/pages/home.html"
ABOUT_DOT = '<span class="dot" aria-hidden="true">&middot;</span>'


def about_line(base: str) -> str:
    """The landing page's About row of template specification 7.24 (baseline 1.7.0) at base, spelled out as the
    template owner's notice gives it: 1 ordinary space after each dot span and none before it."""
    new_tab = '<span class="vh"> (opens in a new tab)</span>'
    return (f'<p class="about"><a href="{base}disclosure/">Disclosure</a>{ABOUT_DOT} <a href="{base}license/">Licence</a>{ABOUT_DOT} '
            f'<a href="https://posluns.ca/privacy/" target="_blank" rel="noopener noreferrer">Privacy{new_tab}</a>{ABOUT_DOT} '
            f'<a href="https://posluns.ca/security/" target="_blank" rel="noopener noreferrer">Security{new_tab}</a></p>')


ABOUT_ROW = about_line("{{base}}")


def about_row(row: str):
    """Replace the About row in the landing page's source with row."""
    def apply(root: Path) -> None:
        path = root / HOME
        text, count = re.subn(r'<p class="about">.*?</p>', lambda _: row, path.read_text(encoding="utf-8"), count=1)
        if count != 1:
            raise AssertionError(f"no About row in {HOME}")
        path.write_text(text, encoding="utf-8")
    return apply


def about_problems(page: str, text: str, base: str) -> list[str]:
    """The About row of specification 7.24: exactly once on the landing page, byte for byte, with no INERT ancestor,
    and on no other page."""
    if page != "index.html":
        return [f"{page} carries an About row, which only the landing page may"] if 'class="about"' in text else []
    row = about_line(base)
    if text.count('class="about"') != 1 or text.count(row) != 1 or "&middot;</span><a" in text:
        return [f"{page} lacks the About row with 1 ordinary space after each dot and none before it (specification 7.24)"]
    parsed = Placement()
    parsed.feed(text)
    parsed.close()
    start = parsed.starts.get(position(text, text.find(row)))
    if start is None or any(name in INERT for name, _ in start[2]):
        return [f"{page} carries its About row inside an element of INERT (specification 7.24)"]
    return []


def set_page(root: Path, page_id: str, **changes) -> None:
    """Change (or with None, remove) fields of 1 page entry in site.json."""
    path = root / "site-src" / "site.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for page in data["pages"]:
        if page["id"] == page_id:
            for key, value in changes.items():
                if value is None:
                    page.pop(key, None)
                else:
                    page[key] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def staged(root: Path) -> None:
    """Set the base back to /draft/ and drop the holding page, as a staging round would."""
    path = root / "site-src" / "site.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["base"] = "/draft/"
    data["pages"] = [page for page in data["pages"] if page["id"] != "draft"]
    path.write_text(json.dumps(data), encoding="utf-8")


def set_release(root: Path, **changes: str) -> None:
    path = root / "site-src" / "release.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


REFUSALS = [
    ("an en dash", inject("<p>pages 1\u20132</p>")),
    ("an em dash", inject("<p>a pause\u2014here</p>")),
    ("an inline style attribute", inject('<p style="color: red">x</p>')),
    ("a style element", inject("<style>p { color: red; }</style>")),
    ("an inline script", inject("<script>alert(1)</script>")),
    ("a second light and dark switch", inject(SWITCH)),
    ("a second element with data-scheme-toggle, a button in the content", inject(TOGGLE)),
    ("a second element with data-scheme-toggle in upper case", inject('<div DATA-SCHEME-TOGGLE hidden></div>')),
    ("a later stylesheet in the body", inject('<link rel="stylesheet" href="{{base}}assets/baseline/baseline.css?v=1.7.0">')),
    ("a stylesheet in upper case in the body", inject('<LINK REL="stylesheet" HREF="{{base}}assets/baseline/baseline.css?v=1.7.0">')),
    ("a bare svg outside the switch", inject("<svg></svg>")),
    ("an upper-case SVG outside the switch", inject("<SVG></SVG>")),
    ("a second scheme.js load in another spelling",
        inject('<SCRIPT SRC="{{base}}assets/baseline/sch&#101;me.js?v=1.7.0" defer></SCRIPT>')),
    ("a second scheme.js load as the first of 2 src attributes", inject(
        '<SCRIPT SRC="{{base}}assets/baseline/sch&#101;me.js?v=1.7.0" src="{{base}}assets/baseline/copy.js?v=1.7.0" defer></SCRIPT>')),
    ("an attribute repeated on any other tag", inject('<p class="lead" class="x">x</p>')),
    ("a link to the pinned build tool, which is never served",
        inject('<p><a href="/.baseline/check_palette.py">palette gate</a></p>')),
    ("a module script", inject('<script type="module">alert(1)</script>')),
    ("an on* handler", inject('<p onclick="x()">x</p>')),
    ("what this is framing", inject("<p>What this is not: a filter.</p>")),
    ("a second h1", inject("<h1>Another</h1>")),
    ("a duplicate id", inject('<p id="watch">again</p>')),
    ("an unknown token", inject("<p>{{nonsense}}</p>")),
    ("a malformed token", inject("<p>{{ base }}</p>")),
    ("a root asset that is neither generated nor pinned", inject('<img src="/favicon.svg" alt="">')),
    ("a relative link", inject('<p><a href="install/">relative</a></p>')),
    ("an external link without target", inject('<p><a href="https://example.org/">x<span class="vh"> (opens in a new tab)</span></a></p>')),
    ("an external link without the new-tab text", inject('<p><a href="https://example.org/" target="_blank" rel="noopener noreferrer">x</a></p>')),
    ("an external image", inject('<img src="https://example.org/x.png" alt="">')),
    ("a JSON-LD block on a noindex page", lambda root: edit(
        root, "site-src/pages/draft.html", "</h1>", '</h1><script type="application/ld+json">{}</script>')),
    ("a page with no modified date", lambda root: set_page(root, "demo", modified=None)),
    ("the holding page without noindex", lambda root: set_page(root, "draft", noindex=None)),
    ("a static file that is also generated", lambda root: edit(
        root, "site-src/site.json", '"README.md",', '"README.md", "404.html",')),
    ("an in-page link with no target", inject('<p><a href="#nowhere">x</a></p>')),
    ("a link to a page that is not generated", inject('<p><a href="{{base}}nope/">x</a></p>')),
    ("a link to an anchor the target lacks", inject('<p><a href="{{base}}install/#nowhere">x</a></p>')),
    # A browser with scripting on renders no markup inside noscript: an h1 or a link target there is not present.
    ("the only h1 inside noscript", lambda root: (
        edit(root, PAGE, "<h1>", "<noscript><h1>"), edit(root, PAGE, "</h1>", "</h1></noscript>"))),
    ("an in-page link whose only target is inside noscript",
        inject('<noscript><p id="inert-target">x</p></noscript><p><a href="#inert-target">x</a></p>')),
    ("a link to an anchor the target page has only inside noscript", lambda root: (
        edit(root, "site-src/pages/install.html", 'id="test">', 'id="test"><noscript><span id="inert-anchor"></span></noscript>'),
        inject('<p><a href="{{base}}install/#inert-anchor">x</a></p>')(root),
    )),
    ("an allowlisted root link to a missing file", lambda root: (
        edit(root, "site-src/site.json", '"/downloads/cleanlanguage-8k.md"', '"/downloads/cleanlanguage-8k.md", "/downloads/gone.md"'),
        inject('<p><a href="/downloads/gone.md">x</a></p>')(root),
    )),
    ("release.json disagrees with SKILL.md", lambda root: set_release(root, version="1.0.99", tag="v1.0.99")),
    ("release.json tag is not v<version>", lambda root: set_release(root, tag="1.0.14")),
    ("release.json checksum is malformed", lambda root: set_release(root, checksum="abc")),
    ("unsupported Markdown in examples.md", lambda root: edit(
        root, "cleanlanguage/skills/cleanlanguage/references/examples.md",
        "The vendor contract expires on 31 March.", "The **vendor** contract expires on 31 March.")),
    ("commentary for a section examples.md lacks", lambda root: edit(
        root, "site-src/examples-commentary.json", '"Incident status":', '"Incident report":')),
    ("a Preferred block with no example before it", lambda root: edit(
        root, "cleanlanguage/skills/cleanlanguage/references/examples.md", "### Weak\n\nThe team has been", "### Preferred\n\nThe team has been")),
    ("the sitemap config no longer excludes the draft holding page", lambda root: edit(
        root, "tools/sitemap-config.json", ', "draft/index.html"', "")),
    ("an extra closing div (the reference demo's defect)", lambda root: edit(
        root, PAGE, "untested recovery path.</p></div></div>", "untested recovery path.</p></div></div></div>")),
    ("an unclosed div", inject('<div class="callout"><p>x</p>')),
    ("content after .doc closes", lambda root: edit(
        root, PAGE, "</a></div></div>\n", "</a></div></div>\n<p>after the document</p>\n")),
    ("code-tag text inside the prompt (the reference demo's defect)", lambda root: edit(
        root, PAGE, "hidden>Copy</button>First, read", "hidden>Copy</button>&lt;code id=&quot;demo-prompt&quot;&gt;First, read")),
    ("a static aria-current=true mark", inject('<p><a href="#watch" aria-current="true">x</a></p>')),
    ("an inner page linking the Licence page", inject('<p><a href="{{base}}license/">x</a></p>')),
    ("an inner page linking the Disclosure page", inject('<p><a href="{{base}}disclosure/#d-1">x</a></p>')),
    ("the About row with no space after each dot (the 1.6.1 markup)", about_row(ABOUT_ROW.replace(ABOUT_DOT + " ", ABOUT_DOT))),
    ("the About row with a space before a dot", about_row(ABOUT_ROW.replace("</a>" + ABOUT_DOT, "</a> " + ABOUT_DOT, 1))),
    ("the About row with &nbsp; in place of 1 space", about_row(ABOUT_ROW.replace(ABOUT_DOT + " ", ABOUT_DOT + "&nbsp;", 1))),
    ("the About row with 2 spaces after a dot", about_row(ABOUT_ROW.replace(ABOUT_DOT + " ", ABOUT_DOT + "  ", 1))),
    ("an About row on an inner page", inject('<p class="about"><a href="{{base}}install/">Install</a></p>')),
    ("a baseline asset the pin does not list", inject('<img src="{{base}}assets/baseline/logos/missing.svg" alt="">')),
    ("a checklist group that is not 1 bullet list", lambda root: edit(
        root, "cleanlanguage/skills/cleanlanguage/references/qa-checklist.md", "## Tone\n\n", "## Tone\n\nA paragraph.\n\n")),
    ("a list rail with fewer than 2 sections", lambda root: edit(
        root, "site-src/site.json", '"source": "404.html", ', '"source": "404.html", "rail": "list", ')),
    ("a family page linking #get in-page, left on /install/", lambda root: edit(
        root, "site-src/pages/install-claude.html", 'href="{{base}}install/#get"', 'href="#get"')),
    ("a family page linking an anchor /install/ lacks", lambda root: edit(
        root, "site-src/pages/install-gemini.html", 'href="{{base}}install/#test"', 'href="{{base}}install/#gemini-test"')),
]


# Refusals that only a staged base can raise: the base path is a folder, so a root link leaves it.
STAGED_REFUSALS = [
    ("a root link outside the staged base", inject('<p><a href="/install/">live page</a></p>')),
    ("a JSON-LD block on a draft page", inject('<script type="application/ld+json">{}</script>')),
    ("the staged sitemap config no longer excludes the draft home page", lambda root: edit(
        root, "tools/sitemap-config.json", ', "draft/index.html"', "")),
]


def check_refusals(failures: list[str]) -> int:
    ran = 0
    for group, cases in (("", REFUSALS), ("staged ", STAGED_REFUSALS)):
        for name, fault in cases:
            with tempfile.TemporaryDirectory() as scratch:
                root = make_root(Path(scratch))
                if group:
                    staged(root)
                fault(root)
                result = run(root, "--out", str(Path(scratch) / "out"))
                ran += 1
                if result.returncode != 1:
                    failures.append(f"{group}refusal '{name}': exit {result.returncode}, expected 1 ({result.stderr.strip()[:200]})")
    return ran


def check_scheme_validation(failures: list[str]) -> int:
    """The generator's 7.33 refusals, called directly on the committed licence page with 1 fault each."""
    generator = load_module(GENERATOR)
    config = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))
    page = next(entry for entry in config["pages"] if entry["id"] == "license")
    text = (REPO_ROOT / "site/license/index.html").read_text(encoding="utf-8")
    tag = re.search(r'<script data-cfasync="false" src="/assets/baseline/scheme\.js\?v=[0-9.]+"></script>\n', text).group(0)
    sheet = text.index('<link rel="stylesheet"')
    # The head's lines from the scheme.js line, and from the first stylesheet, to </head>; and its last stylesheet.
    loads, sheets = text[text.index(tag):text.index("</head>")], text[sheet:text.index("</head>")]
    later = re.findall(r'<link rel="stylesheet"[^>]*>\n', text)[-1]
    cases = [
        ("the committed licence page", text, True),
        ("no switch", text.replace(SWITCH, "", 1), False),
        ("the switch after header.mast", text.replace(SWITCH + "</header>", "</header>" + SWITCH, 1), False),
        ("the switch in a header without the mast class", text.replace('<header class="mast">', '<header class="other">', 1), False),
        ("the switch after a nav without the nav class", text.replace('<nav class="nav"', '<nav class="links"', 1), False),
        ("the switch in a div at the end of header.mast", text.replace(
            SWITCH + "</header>", "<div>" + SWITCH + "</div></header>", 1), False),
        ("a comment after the switch in header.mast", text.replace(SWITCH + "</header>", SWITCH + "<!-- x --></header>", 1), False),
        ("the scheme.js line and the stylesheets moved into the body, in order", text.replace(loads, "", 1).replace(
            "<body>\n", "<body>\n" + loads, 1), False),
        ("the stylesheets moved into the body, after the scheme.js line", text.replace(sheets, "", 1).replace(
            "<body>\n", "<body>\n" + sheets, 1), False),
        ("the scheme.js line and the stylesheets in a second head inside the body", text.replace(loads, "", 1).replace(
            "<body>\n", "<body>\n<head>\n" + loads + "</head>\n", 1), False),
        ("no scheme.js line", text.replace(tag, "", 1), False),
        ("the scheme.js line with defer", text.replace(tag, tag.replace('"></script>', '" defer></script>'), 1), False),
        ("the scheme.js line after the first stylesheet", text.replace(tag, "", 1).replace("</head>", tag + "</head>", 1), False),
        ("a second scheme.js line", text[:sheet] + tag + text[sheet:], False),
        ("a second scheme.js in upper case with a character reference", text.replace(
            "</head>", '<SCRIPT SRC="/assets/baseline/sch&#101;me.js?v=1.7.0" defer></SCRIPT></head>', 1), False),
        ("the scheme.js line inside a comment, loaded in another spelling", text.replace(tag, "<!--" + tag.rstrip("\n")
            + '--><script data-cfasync="false" src="/assets/baseline/sch&#101;me.js?v=1.7.0"></script>\n', 1), False),
        ("an upper-case stylesheet before the scheme.js line", text.replace(
            tag, '<LINK REL="stylesheet" HREF="/assets/baseline/fonts.css?v=1.7.0">\n' + tag, 1), False),
        ("a second scheme.js load as the first of 2 src attributes", text.replace("</head>", '<SCRIPT SRC='
            '"/assets/baseline/sch&#101;me.js?v=1.7.0" src="/assets/baseline/copy.js?v=1.7.0" defer></SCRIPT></head>', 1), False),
        ("a stylesheet before the scheme.js line as the first of 2 rel attributes", text.replace(
            tag, '<LINK REL="stylesheet" REL="icon" HREF="/assets/baseline/fonts.css?v=1.7.0">\n' + tag, 1), False),
        # The parsed reading allows it, but the header block must be byte for byte what mast() is meant to write.
        ("a newline between nav.nav and the switch", text.replace("</nav>" + SWITCH, "</nav>\n" + SWITCH, 1), False),
        ("a second element with data-scheme-toggle after header.mast", text.replace(
            SWITCH + "</header>", SWITCH + "</header>" + TOGGLE, 1), False),
        ("a second element with data-scheme-toggle in upper case", text.replace(
            SWITCH + "</header>", SWITCH + '</header><div DATA-SCHEME-TOGGLE hidden></div>', 1), False),
        ("a later stylesheet moved into the body", text.replace(later, "", 1).replace("<body>\n", "<body>\n" + later, 1), False),
        ("a later stylesheet in upper case at the end of the body", text.replace(
            "</body>", '<LINK REL="stylesheet" HREF="/assets/baseline/baseline.css?v=1.7.0">\n</body>', 1), False),
        ("a later stylesheet in a second head after the body", text.replace(later, "", 1).replace(
            "</body>\n", "</body>\n<head>\n" + later + "</head>\n", 1), False),
        # HTML5 ends the head at text other than whitespace, a start tag a head may not hold, or </br>; the loads
        # after it are in the body. A comment and whitespace leave it open.
        ("text before the scheme.js line", text.replace(tag, "x\n" + tag, 1), False),
        ("a no-break space before the scheme.js line", text.replace(tag, "&nbsp;\n" + tag, 1), False),
        ("a div before the scheme.js line", text.replace(tag, "<div></div>\n" + tag, 1), False),
        ("</br> before the scheme.js line", text.replace(tag, "</br>\n" + tag, 1), False),
        ("a comment and whitespace before the scheme.js line", text.replace(tag, "<!-- x -->\n \t\n" + tag, 1), True),
        # A browser ignores the slash on an element that is neither void nor in <svg>: it stays open, so the switch
        # becomes its child.
        ("a self-closing nav.nav before the switch", text.replace(SWITCH, '<nav class="nav"/>' + SWITCH, 1), False),
        ("a self-closing div first in header.mast", text.replace(
            '<header class="mast">', '<header class="mast"><div/>', 1), False),
    ]
    for name, page_html, passes in cases:
        try:
            generator.validate(page_html, page, config, "/")
            passed = True
        except generator.BuildError:
            passed = False
        if passed != passes:
            failures.append(f"scheme validation '{name}': {'passed' if passed else 'refused'}, expected the opposite")
        # The build test's helper must judge each case as the generator should.
        if (not scheme_problems("license/index.html", page_html, "/", config)) != passes:
            failures.append(f"scheme helper '{name}': {'refused' if passes else 'passed'}, expected the opposite")
    # Each case below must be refused by the rule it names, whatever else refuses it: the switch's place (class names
    # split on ASCII whitespace only, no INERT ancestor), or the pinned header block at the start of the body.
    mast, end = '<header class="mast">', SWITCH + "</header>"
    placed = ("as the last child of header.mast", "does not end header.mast")
    pinned = ("the header block", "the header block")
    ruled = [
        ("a no-break space in the mast class", text.replace(mast, '<header class="mast\u00a0x">', 1), placed),
        ("a no-break space in the nav class", text.replace('<nav class="nav"', '<nav class="nav\u00a0x"', 1), placed),
        ("header.mast inside noscript", text.replace(mast, "<noscript>" + mast, 1).replace(end, end + "</noscript>", 1), placed),
        ("header.mast inside template", text.replace(mast, "<template>" + mast, 1).replace(end, end + "</template>", 1), placed),
        ("a header 1 byte from the pinned markup", text.replace('aria-label="Site"', 'aria-label="site"', 1), pinned),
        # HTML5 closes the button and the header in it where the switch's button starts, so the switch leaves header.mast.
        ("header.mast wrapped in a button", text.replace(mast, "<button>" + mast, 1).replace(end, end + "</button>", 1),
         pinned),
        ("a div between the head and the body, around the header", text.replace("</head>\n", "</head>\n<div>", 1).replace(
            "</body>\n", "</body>\n</div>", 1), pinned),
    ] + [(f"header.mast inside {name}", text.replace(mast, f"<{name}>" + mast, 1).replace(end, end + f"</{name}>", 1),
          placed) for name in ADDED_INERT]
    for name, page_html, (generator_says, helper_says) in ruled:
        try:
            generator.validate(page_html, page, config, "/")
            refusal = ""
        except generator.BuildError as error:
            refusal = str(error)
        if generator_says not in refusal:
            failures.append(f"scheme validation '{name}': not refused by its rule ({refusal[:200] or 'passed'})")
        if not any(helper_says in problem for problem in scheme_problems("license/index.html", page_html, "/", config)):
            failures.append(f"scheme helper '{name}': not refused by its rule")
    return 2 * len(cases) + 2 * len(ruled)


def check_inert_validation(failures: list[str]) -> int:
    """The blocks, the h1, the robots meta and the landing page's About row validate() requires, called directly on
    committed pages, each moved inside noscript, raw text or canvas, whose content a browser with scripting on does
    not render as page elements."""
    generator = load_module(GENERATOR)
    config = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))
    pages = {entry["id"]: entry for entry in config["pages"]}
    texts = {page_id: (REPO_ROOT / f"site/{page_id}/index.html").read_text(encoding="utf-8") for page_id in ("license", "draft")}
    texts["home"] = (REPO_ROOT / "site/index.html").read_text(encoding="utf-8")
    skip, status, robots = generator.SKIP_LINK, generator.COPY_STATUS, '<meta name="robots" content="noindex, nofollow">'
    h1 = re.search(r"<h1>[^<]*</h1>", texts["license"]).group(0)
    about = about_line("/")
    cases = [
        ("the committed home page", "home", None, None, True),
        ("the About row only inside noscript", "home", about, f"<noscript>{about}</noscript>", False),
        ("the About row only inside canvas", "home", about, f"<canvas>{about}</canvas>", False),
        ("the h1 only inside canvas", "license", h1, f"<canvas>{h1}</canvas>", False),
        ("the committed licence page", "license", None, None, True),
        ("the committed draft page", "draft", None, None, True),
        ("the skip link only inside noscript", "license", skip, f"<noscript>{skip}</noscript>", False),
        ("the skip link only inside a title", "license", skip, f"<title>{skip}</title>", False),
        ("#copy-status only inside noscript", "license", status, f"<noscript>{status}</noscript>", False),
        ("the robots meta only inside noscript in the head", "draft", robots, f"<noscript>{robots}</noscript>", False),
    ]
    for name, page_id, old, new, passes in cases:
        page_html = texts[page_id] if old is None else texts[page_id].replace(old, new, 1)
        if old is not None and old not in texts[page_id]:
            failures.append(f"inert validation '{name}': {old!r} is not in site/{page_id}/index.html")
        try:
            generator.validate(page_html, pages[page_id], config, "/")
            passed = True
        except generator.BuildError:
            passed = False
        if passed != passes:
            failures.append(f"inert validation '{name}': {'passed' if passed else 'refused'}, expected the opposite")
        # The build test's helper must judge each About row case as the generator should.
        if page_id == "home" and (not about_problems("index.html", page_html, "/")) != passes:
            failures.append(f"About helper '{name}': {'refused' if passes else 'passed'}, expected the opposite")
    return len(cases) + sum(1 for _, page_id, *_ in cases if page_id == "home")


def check_generator_header(failures: list[str]) -> int:
    """A generator whose header function writes 1 byte other than the pinned header block, or wraps the unchanged
    block in a button, refuses to build."""
    source = GENERATOR.read_text(encoding="utf-8")
    at = source.index("\ndef mast(")
    mutants = [
        ("a 1-byte change to mast()", source[at:].replace('aria-label="Site"', 'aria-label="site"', 1)),
        ("mast() wrapping the header block in a button", source[at:].replace(
            "f'<header class=\"mast\">", "f'<button><header class=\"mast\">", 1).replace(
            "{SCHEME_SWITCH}</header>'", "{SCHEME_SWITCH}</header></button>'", 1)),
    ]
    for name, tail in mutants:
        if tail == source[at:]:
            failures.append(f"generator header: {name} changed nothing in tools/build-site.py")
            continue
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            mutant = root / "tools" / GENERATOR.name
            mutant.write_text(source[:at] + tail, encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(mutant), "--root", str(root), "--out", str(Path(scratch) / "out")],
                                    capture_output=True, text=True)
            if result.returncode != 1 or "the header block" not in result.stderr:
                failures.append(f"generator header: {name} gave exit {result.returncode}, expected 1 with the "
                                f"header block refusal ({result.stderr.strip()[:200]})")
    return len(mutants)


def check_unreadable(failures: list[str]) -> int:
    ran = 0
    for name, fault in (
        ("static_files is not a list", lambda root: edit(root, "site-src/site.json", '"static_files": [', '"static_files": "none", "unused": [')),
        ("a static file outside site/", lambda root: edit(root, "site-src/site.json", '"README.md",', '"../README.md",')),
        ("a malformed modified date", lambda root: set_page(root, "demo", modified="3 November 2026")),
    ):
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            fault(root)
            result = run(root, "--check")
            ran += 1
            if result.returncode != 3:
                failures.append(f"unreadable '{name}': exit {result.returncode}, expected 3 ({result.stderr.strip()[:200]})")
    return ran


def check_clean_build(failures: list[str]) -> int:
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"clean build: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        pages = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html"))
        if len(pages) != 19:
            failures.append(f"clean build: {len(pages)} pages, expected 19: {pages}")
        config = json.loads((root / "site-src/site.json").read_text(encoding="utf-8"))
        noindex = {p["path"] if p["path"].endswith(".html") else p["path"] + "index.html"
                   for p in config["pages"] if p.get("noindex")}
        if noindex != {"404.html", "draft/index.html"}:
            failures.append(f"clean build: the noindex pages are {sorted(noindex)}, expected 404.html and draft/index.html")
        modified = {p["id"]: p.get("modified") for p in config["pages"]}
        for page in pages:
            text = (out / page).read_text(encoding="utf-8")
            if '<link rel="apple-touch-icon" href="/assets/baseline/logos/cleanlanguage-touch.png">' not in text:
                failures.append(f"clean build: {page} lacks the touch icon")
            list_rail = '<nav class="rail" aria-label="On this page">' in text
            if list_rail != ('assets/baseline/rail.js?v=' in text):
                failures.append(f"clean build: {page} loads rail.js {'without' if not list_rail else 'not on'} a list rail")
            if "aria-current=" in text.split('<nav class="rail"', 1)[-1].split("</nav>", 1)[0] and list_rail:
                failures.append(f"clean build: {page} marks a rail link in the markup")
            robots = text.count('<meta name="robots" content="noindex, nofollow">')
            metadata = "application/ld+json" in text or 'rel="canonical"' in text
            if page in noindex and (robots != 1 or metadata):
                failures.append(f"clean build: {page} must carry 1 noindex meta and no publish metadata")
            if page not in noindex and (robots or not metadata or "noindex" in text):
                failures.append(f"clean build: {page} must carry publish metadata and no noindex")
            for value in re.findall(r'(?:href|src)="(/[^"]*)"', text):
                if value.startswith("/draft/"):
                    failures.append(f"clean build: {page} links the draft holding page {value}")
            failures += [f"clean build: {problem}" for problem in scheme_problems(page, text, "/", config)]
            failures += [f"clean build: {problem}" for problem in about_problems(page, text, "/")]
        for page_id, page in (("home", "index.html"), ("install", "install/index.html"), ("license", "license/index.html")):
            stamp = f'<meta property="article:modified_time" content="{modified[page_id]}">'
            if stamp not in (out / page).read_text(encoding="utf-8"):
                failures.append(f"clean build: {page} lacks its site.json modified date {stamp!r}")
        holding = (out / "draft/index.html").read_text(encoding="utf-8")
        for needed in ('<h1>Draft review</h1>', '<a class="start" href="/">Home', '<div class="rail"><img class="rail-logo"',
                       "Nothing is staged here now; the published site is at the home page."):
            if needed not in holding:
                failures.append(f"clean build: the holding page lacks {needed!r}")
        scheme_line = re.search(r'^<script data-cfasync="false" src="/assets/baseline/scheme\.js\?v=[0-9]+\.[0-9]+\.[0-9]+"></script>$',
                                holding, re.M)
        if 'property="og:' in holding or 'name="description"' in holding or holding.count("<script") != 1 or scheme_line is None:
            failures.append("clean build: the holding page carries social metadata or a script other than the scheme.js line")
        sitemap_config = json.loads((root / "tools/sitemap-config.json").read_text(encoding="utf-8"))
        if "draft/index.html" not in sitemap_config["exclude"]:
            failures.append("clean build: the sitemap config does not exclude the holding page")
        checklist = (out / "checklist/index.html").read_text(encoding="utf-8")
        rail_labels = re.findall(r'<li><a href="#[^"]+">([^<]*)</a></li>', checklist.split('<nav class="rail"', 1)[1].split("</nav>", 1)[0])
        if rail_labels[:2] != ["Accuracy", "Directness"] or any(label[:1].isdigit() for label in rail_labels):
            failures.append(f"clean build: the checklist rail labels carry the clause numbers: {rail_labels}")
        examples_md = (root / "cleanlanguage/skills/cleanlanguage/references/examples.md").read_text(encoding="utf-8")
        examples = (out / "examples/index.html").read_text(encoding="utf-8")
        sections = re.findall(r"^## (.+)$", examples_md, re.M)
        if examples.count('<p class="lbl sec">Example ') != len(sections):
            failures.append("clean build: the examples page does not show every section of examples.md")
        for paragraph in re.findall(r"^### .+\n\n(.+)$", examples_md, re.M):
            rendered = html.escape(paragraph, quote=False)
            rendered = re.sub(r"`([^`]*)`", r"<code>\1</code>", rendered)
            if rendered not in examples:
                failures.append(f"clean build: example text missing: {paragraph[:60]!r}")
        instructions = (out / "instructions/index.html").read_text(encoding="utf-8")
        source = (root / "site/downloads/cleanlanguage.md").read_text(encoding="utf-8").rstrip("\n")
        match = re.search(r'<pre id="instructions-text" class="hascopy prompt-flow"><button class="copy" type="button" data-copy="instructions-text" hidden>Copy</button>(.*?)</pre>', instructions, re.S)
        if match is None or html.unescape(match.group(1)) != source:
            failures.append("clean build: the instructions page does not embed cleanlanguage.md exactly")
    return 1


FAMILY_TITLES = {
    "claude": "Install in Claude",
    "chatgpt": "Install in ChatGPT",
    "gemini": "Install in Gemini",
    "copilot": "Install in Copilot",
    "other-ai": "Install in other AI systems",
}


def check_family_pages(failures: list[str]) -> int:
    """The 5 family install pages build with publish metadata, and the home page counts them."""
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"family pages: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        for family, title in FAMILY_TITLES.items():
            path = out / "install" / family / "index.html"
            if not path.is_file():
                failures.append(f"family pages: install/{family}/index.html was not generated")
                continue
            text = path.read_text(encoding="utf-8")
            for needed in (f"<title>{title} | CleanLanguage.ai</title>", f'<link rel="canonical" href="https://cleanlanguage.ai/install/{family}/">',
                           '<meta property="article:published_time" content="', 'href="/install/#get"', 'href="/install/#test"'):
                if needed not in text:
                    failures.append(f"family pages: install/{family}/index.html lacks {needed!r}")
        home = (out / "index.html").read_text(encoding="utf-8")
        if '<span class="n">5 assistants</span>' not in home:
            failures.append("family pages: the home page does not count 5 assistants")
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        path = root / "site-src" / "site.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["pages"] = [page for page in data["pages"] if not page["path"].startswith("install/") or page["path"] == "install/"]
        path.write_text(json.dumps(data), encoding="utf-8")
        result = run(root, "--out", str(Path(scratch) / "out"))
        if result.returncode != 1 or "no family install pages" not in result.stderr:
            failures.append(f"family pages: no family pages gave exit {result.returncode}, expected 1 with the count refusal: {result.stderr.strip()[:200]}")
    return 2


def check_release_flip(failures: list[str]) -> int:
    """Every version string on the install and verify pages follows release.json (the known version-text issue)."""
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        skill = root / "cleanlanguage/skills/cleanlanguage/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(re.sub(r"^Version: [0-9.]+", "Version: 9.8.7", text, count=1, flags=re.M), encoding="utf-8")
        set_release(root, version="9.8.7", tag="v9.8.7", checksum="a" * 64)
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"release flip: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        for page in ("install/index.html", "verify/index.html"):
            body = (out / page).read_text(encoding="utf-8")
            stale = sorted(set(re.findall(r"cleanlanguage-([0-9][0-9.]*[0-9])\.zip|version ([0-9]+\.[0-9]+\.[0-9]+)", body)))
            names = {v for pair in stale for v in pair if v}
            if names != {"9.8.7"}:
                failures.append(f"release flip: {page} names versions {sorted(names)}, expected only 9.8.7")
        verify = (out / "verify/index.html").read_text(encoding="utf-8")
        for needed in ("published checksum for version 9.8.7 is", 'id="published-checksum">' + "a" * 64, "releases/download/v9.8.7/cleanlanguage-9.8.7.zip.sha256",
                       "Get-FileHash cleanlanguage-9.8.7.zip", "shasum -a 256 cleanlanguage-9.8.7.zip", "sha256sum cleanlanguage-9.8.7.zip"):
            if needed not in verify:
                failures.append(f"release flip: verify page lacks {needed!r}")
        install = (out / "install/index.html").read_text(encoding="utf-8")
        for needed in ("zip, version 9.8.7", "for example <code>cleanlanguage-9.8.7.zip</code>"):
            if needed not in install:
                failures.append(f"release flip: install page lacks {needed!r}")
    return 1


def check_check_mode(failures: list[str]) -> int:
    ran = 0
    def leave(relative: str):
        def apply(d: Path) -> None:
            (d / relative).parent.mkdir(parents=True, exist_ok=True)
            (d / relative).write_text("x", encoding="utf-8")
        return apply
    for name, fault in (
        ("a changed output byte", lambda d: (d / "verify/index.html").write_text((d / "verify/index.html").read_text(encoding="utf-8") + " ", encoding="utf-8")),
        ("an extra output file", leave("stale.html")),
        ("a missing output file", lambda d: (d / "demo/index.html").unlink()),
        ("a missing static file", lambda d: (d / "robots.txt").unlink()),
        ("an old live page left behind", leave("privacy/index.html")),
        ("an old stylesheet left behind", leave("styles.css")),
        ("a staged draft page left behind", leave("draft/install/index.html")),
    ):
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if run(root).returncode != 0 or run(root, "--check").returncode != 0:
                failures.append(f"check mode '{name}': the clean tree did not build and check")
                continue
            fault(root / "site")
            code = run(root, "--check").returncode
            ran += 1
            if code != 1:
                failures.append(f"check mode '{name}': exit {code}, expected 1")
    return ran


def check_promotion_build(failures: list[str]) -> int:
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        staged(root)
        edit(root, "tools/sitemap-config.json", ', "draft/index.html"', "")
        result = run(root, "--base", "/")
        if result.returncode != 1 or "--promote" not in result.stderr:
            failures.append("promotion build: a --base / override of a staged base wrote into site/ without --promote")
        result = run(root, "--base", "/", "--promote")
        if result.returncode != 0 or not (root / "site/index.html").is_file():
            failures.append(f"promotion build: --base / --promote did not write site/: {result.stderr.strip()[:200]}")
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        result = run(root)
        if result.returncode != 0:
            failures.append(f"promotion build: the configured base / did not write site/ without --promote: {result.stderr.strip()[:200]}")
        result = run(root, "--out", str(Path(scratch) / "bad"), "--date", "2026/11/03")
        if result.returncode != 1:
            failures.append(f"promotion build: a malformed --date gave exit {result.returncode}, expected 1")
        out = Path(scratch) / "root"
        result = run(root, "--out", str(out), "--date", "2026-11-02")
        if result.returncode != 0:
            failures.append(f"promotion build: exit {result.returncode}: {result.stderr.strip()}")
            return 3
        home = (out / "index.html").read_text(encoding="utf-8")
        for needed in ('<link rel="canonical" href="https://cleanlanguage.ai/">', '<link rel="apple-touch-icon" href="/assets/baseline/logos/cleanlanguage-touch.png">', '<meta name="author" content="Jeff Posluns">',
                       '<meta property="article:modified_time" content="2026-11-02">', '"@type": "Person"', 'href="/install/"'):
            if needed not in home:
                failures.append(f"promotion build: the home page lacks {needed!r}")
        if "noindex" in home or "/draft/" in home:
            failures.append("promotion build: the home page still carries draft paths or noindex")
        for page in ("404.html", "draft/index.html"):
            text = (out / page).read_text(encoding="utf-8")
            if '<meta name="robots" content="noindex, nofollow">' not in text or "application/ld+json" in text:
                failures.append(f"promotion build: {page} must stay noindex without publish metadata")
        config = json.loads((root / "site-src/site.json").read_text(encoding="utf-8"))
        for page in sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html")):
            text = (out / page).read_text(encoding="utf-8")
            failures += [f"promotion build: {problem}" for problem in scheme_problems(page, text, "/", config)]
    return 5


def check_staged_build(failures: list[str]) -> int:
    """A staging round still builds: every page noindex, nothing linked outside /draft/."""
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        staged(root)
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"staged build: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        pages = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html"))
        config = json.loads((root / "site-src/site.json").read_text(encoding="utf-8"))
        if len(pages) != 18:
            failures.append(f"staged build: {len(pages)} pages, expected 18: {pages}")
        for page in pages:
            text = (out / page).read_text(encoding="utf-8")
            if text.count('<meta name="robots" content="noindex, nofollow">') != 1:
                failures.append(f"staged build: {page} lacks the noindex meta")
            if "application/ld+json" in text or 'rel="canonical"' in text:
                failures.append(f"staged build: {page} carries publish metadata in the draft")
            failures += [f"staged build: {problem}" for problem in scheme_problems(page, text, "/draft/", config)]
            failures += [f"staged build: {problem}" for problem in about_problems(page, text, "/draft/")]
            for value in re.findall(r'(?:href|src)="(/[^"]*)"', text):
                if not value.startswith("/draft/") and not value.startswith("/downloads/"):
                    failures.append(f"staged build: {page} links {value} outside /draft/")
    return 1


def main() -> int:
    failures: list[str] = []
    ran = 0
    code = subprocess.run([sys.executable, "-I", str(GENERATOR), "--check"], capture_output=True, text=True).returncode
    ran += 1
    if code != 0:
        failures.append(f"this repository: --check exit {code}, expected 0")
    for tool in (GENERATOR, REPO_ROOT / "tools" / "check-inline-code.py"):
        ran += 1
        if hashlib.sha256(module_switch(tool).encode("utf-8")).hexdigest() != SWITCH_SHA256:
            failures.append(f"{tool.name}: SCHEME_SWITCH is not the 7.33 switch of the 1.6.0 reference pages")
    # Every reader holds the same inert set, and it holds every element the install gate hides for its content.
    ran += 1
    inline = set(load_module(REPO_ROOT / "tools" / "check-inline-code.py").INERT_ELEMENTS)
    hiding = set(load_module(REPO_ROOT / "tools" / "check-install-page.py").HIDING_ELEMENTS)
    if not load_module(GENERATOR).INERT_TAGS == INERT == inline >= hiding:
        failures.append("INERT_TAGS, check-inline-code.py's INERT_ELEMENTS and INERT here differ, or leave out an element "
                        "of check-install-page.py's HIDING_ELEMENTS")
    ran += check_refusals(failures)
    ran += check_unreadable(failures)
    ran += check_scheme_validation(failures)
    ran += check_inert_validation(failures)
    ran += check_generator_header(failures)
    ran += check_clean_build(failures)
    ran += check_staged_build(failures)
    ran += check_family_pages(failures)
    ran += check_release_flip(failures)
    ran += check_check_mode(failures)
    ran += check_promotion_build(failures)
    if failures:
        print("test-build-site: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-build-site: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
