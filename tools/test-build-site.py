#!/usr/bin/env python3
"""Tests for tools/build-site.py: each refusal fires on a deliberate fault.

Each build case copies the generator's inputs into a temporary folder (under
$TMPDIR), leaves the copy as it is or changes it (a refused case with a
fault the generator must refuse, a passing case with a valid change it must
accept), runs the generator there as a separate process and asserts its
exit code; some passing cases, such as the clean, staged and promotion
builds, also check what the output contains. A further
case runs a copy of this file, without the install gate, as a separate
process. The others run in this process: they call the
generator's functions, loaded as a module (such as ``validate()``,
``with_about()`` and ``install_gate()``), on committed pages or snippets, or
check this file's own readers (such as the stylesheet coverage check and the
About helper) against stylesheet texts, the pinned specification and committed
pages. The first case runs ``--check`` on this repository. The configured
base is ``/``; the staged cases first set the base to ``/draft/`` and exclude
the draft's home page from the sitemap, as a staging round on the ``draft``
branch would (template 1.11.0: the live site carries no ``/draft/``). Exit 0
when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import itertools
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
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
    "tools/check-install-page.py",
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
    start tag not in HEAD_TAGS, or </body>, </html> or </br>), and in lineage where its open elements start; and
    each end tag's closed element (name, classes, depth, where it starts); keyed by where the tag starts: (line,
    column), as getpos() reports. A self-closing tag leaves an element that is neither void nor in <svg> open, as
    in a browser, and class names split on ASCII whitespace only. It fails closed where it does not model HTML5: a
    start tag not in HEAD_TAGS inside <template> or <noscript> in the head ends the head, and a self-closing tag in
    <math> leaves its element open. It is not a
    full HTML5 tree builder: it models the open elements as tags nest, void elements, the slash only in <svg> and
    the head's end, so scheme_problems also holds each page's markup from <body> to the end of header.mast, byte for
    byte, to the body start tag, the skip link and MAST_BLOCK, at the start of the page's body (body: a body start
    tag in html right after the only head closes, with no element or text between them, before the head ends).
    scheme_problems pins nothing after header.mast, and about_problems only the landing page's About block; the
    committed pages rest on build-site.py --check and the generator's validator."""

    def __init__(self) -> None:
        super().__init__()
        self.open: list[tuple[str, list[str]]] = []
        self.previous: tuple[str, list[str]] | None = None
        self.heads = 0
        self.head_ended = False
        self.body: tuple[int, int] | None = None
        self.starts: dict[tuple[int, int], tuple[str, dict, list[tuple[str, list[str]]], tuple | None, bool]] = {}
        self.ends: dict[tuple[int, int], tuple[str, list[str], int, tuple[int, int]]] = {}
        self.open_at: list[tuple[int, int]] = []
        self.lineage: dict[tuple[int, int], list[tuple[int, int]]] = {}
        # The text the parser reads, in order, in upper case where the stylesheets show it so (shown_upper()), as a
        # browser shows it, and each piece as read with where its open elements start; attribute values and comments
        # are not text, but an img's alt text is, held by the img. Whether each open element's text shows in upper
        # case.
        self.text: list[str] = []
        self.text_at: list[tuple[str, list[tuple[int, int]]]] = []
        self.upper: list[bool] = []
        # The hero's narrow-width order (at 600 px and below, the hero image sits in the kicker's row, before the
        # statement), as the generator's PageScan reads it: the length of text where the first child of the first
        # div.hero-text in a section.hero ends when that child is the kicker (a p.lbl), and otherwise where that
        # div.hero-text starts (hero_start); and the index in text of the alt text of the first img in a div.hero-art
        # in a section.hero.
        self.hero_start: int | None = None
        self.kicker_end: int | None = None
        self.hero_alt: int | None = None

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
        self.lineage[self.getpos()] = list(self.open_at)
        if tag == "img" and first.get("alt"):
            # A browser shows an img's alt text in its place when the image does not load: text, held by the img.
            upper = shown_upper([*self.open, (tag, class_names(first.get("class", "")))],
                                bool(self.upper) and self.upper[-1])
            self.text.append(first["alt"].upper() if upper else first["alt"])
            self.text_at.append((first["alt"], [*self.open_at, self.getpos()]))
            if (self.hero_alt is None and len(self.open) >= 2 and self.open[-1][0] == "div"
                    and "hero-art" in self.open[-1][1] and self.open[-2][0] == "section"
                    and "hero" in self.open[-2][1]):
                self.hero_alt = len(self.text) - 1
        if (self.kicker_end is None and tag == "div" and "hero-text" in class_names(first.get("class", ""))
                and self.open and self.open[-1][0] == "section" and "hero" in self.open[-1][1]):
            self.hero_start = len(self.text)
        self.previous = (tag, class_names(first.get("class", ""))) if tag in VOID else None
        if tag not in VOID:
            self.open.append((tag, class_names(first.get("class", ""))))
            self.open_at.append(self.getpos())
            self.upper.append(shown_upper(self.open, bool(self.upper) and self.upper[-1]))

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
            self.upper.pop()
            self.ends[self.getpos()] = (*self.previous, len(self.open), self.open_at.pop())
            if (self.kicker_end is None and len(self.open) >= 2 and self.open[-1][0] == "div"
                    and "hero-text" in self.open[-1][1] and self.open[-2][0] == "section"
                    and "hero" in self.open[-2][1]):
                kicker = self.previous[0] == "p" and "lbl" in self.previous[1]
                self.kicker_end = len(self.text) if kicker else self.hero_start

    def handle_data(self, data: str) -> None:
        self.text.append(data.upper() if self.upper and self.upper[-1] else data)
        self.text_at.append((data, list(self.open_at)))
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


# The pinned template's specification, which tools/copy-baseline.py copies to .baseline/ (never served) and
# tools/check-baseline-pin.py checks against .baseline/SHA256SUMS; its section 7.24 gives the About block at base /.
SPECIFICATION = REPO_ROOT / ".baseline" / "SPECIFICATION.md"
SUMS = REPO_ROOT / ".baseline" / "SHA256SUMS"
ABOUT_HEADING = "### 7.24 About this project (landing page)"
ABOUT_MARKUP = "Markup, directly after the value paragraph's region: `"
ABOUT_START = '<p class="about">'


def specification_about(specification: Path = SPECIFICATION, sums: Path = SUMS) -> tuple[str, list[str]]:
    """The About block of section 7.24 at base /, the backtick span that opens the first line under its heading
    starting with ABOUT_MARKUP, read from .baseline/SPECIFICATION.md only when it hashes to its line in
    .baseline/SHA256SUMS; and site.json's about_paths, each of whose hrefs the block carries once. A ValueError
    names what is missing otherwise."""
    data = specification.read_bytes()
    listed = [line.split("  ", 1)[0] for line in sums.read_text(encoding="utf-8").split("\n")
              if line.endswith("  SPECIFICATION.md")]
    if listed != [hashlib.sha256(data).hexdigest()]:
        raise ValueError(".baseline/SPECIFICATION.md does not hash to its 1 line in .baseline/SHA256SUMS")
    lines = data.decode("utf-8").split("\n")
    if lines.count(ABOUT_HEADING) != 1:
        raise ValueError(f".baseline/SPECIFICATION.md does not carry the heading {ABOUT_HEADING!r} once")
    section = lines[lines.index(ABOUT_HEADING) + 1:]
    section = section[:next((at for at, line in enumerate(section) if line.startswith("#")), len(section))]
    markup = next((line[len(ABOUT_MARKUP):] for line in section if line.startswith(ABOUT_MARKUP)), "")
    if "`" not in markup:
        raise ValueError(f"section 7.24 has no line starting {ABOUT_MARKUP!r} with a closing backtick")
    block = markup.split("`", 1)[0]
    paths = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))["about_paths"]
    if block.count(ABOUT_START) != 1 or any(block.count(f'href="/{path}"') != 1 for path in paths):
        raise ValueError(f"section 7.24's block does not carry {ABOUT_START} and each about_paths href once")
    return block, paths


try:
    specification_about()
except (OSError, UnicodeError, ValueError, KeyError) as error:
    print(f"test-build-site: failures:\n  - the About block of specification 7.24: {error}")
    raise SystemExit(1)


def about_block(base: str, specification: Path = SPECIFICATION, sums: Path = SUMS) -> str:
    """The landing page's whole About block of specification 7.24 at base: the region, its label and the div around
    the About row, read by specification_about() from the specification, the pinned template's SPECIFICATION.md
    unless given, apart from the generator's ABOUT_BLOCK and about_line(), with base in place of the leading / of
    each about_paths href."""
    block, paths = specification_about(specification, sums)
    for path in paths:
        block = block.replace(f'href="/{path}"', f'href="{base}{path}"')
    return block


def about_line(base: str) -> str:
    """The landing page's About row of specification 7.24 at base: the p.about element of about_block()."""
    block = about_block(base)
    start = block.index(ABOUT_START)
    return block[start:block.index("</p>", start) + len("</p>")]


ABOUT_ROW = about_line("{{base}}")
ABOUT_BLOCK = about_block("{{base}}")
LABEL = "About this project"
# The label as written and in upper case: no page source's text carries either, and the landing page's 1, in its block.
LABELS = (LABEL, LABEL.upper())
# The ancestors, outermost first, of the landing page's value region and of its About block, as (name, classes): html
# (with site.json's site_class), body, main#main-content and div.wrap, as the generator writes them around the source.
SITE_CLASS = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))["site_class"]
ANCESTORS = [("html", class_names(SITE_CLASS)), ("body", []), ("main", []), ("div", ["wrap"])]
# The children of the landing page's value region, as (name, sorted classes), as the committed page orders them:
# .region shows its first child in its label column, so a value paragraph there would sit in that column.
REGION_CHILDREN = [("p", ["lbl"]), ("div", [])]


# The stylesheets every page loads, in the order the generator links them: the pinned baseline's 3, and the optional
# per-site one when it exists.
STYLESHEETS = [REPO_ROOT / "site/assets/baseline" / name for name in ("fonts.css", "palettes.css", "baseline.css")] + [
    path for path in [REPO_ROOT / "site-src/assets/site.css"] if path.exists()]
# A selector, whitespace collapsed, that matches() here and the generator's selector_matches() read: compound
# selectors, each a name or *, then .class parts, or .class parts alone, joined by descendant or child (>) combinators.
COMPOUND = r"(?:(?:[a-z][a-z0-9]*|\*)(?:\.[A-Za-z0-9_-]+)*|(?:\.[A-Za-z0-9_-]+)+)"
SIMPLE_SELECTOR = re.compile(rf"{COMPOUND}(?: > {COMPOUND}| {COMPOUND})*")
# The properties that can show text in small capitals, which the label rule does not read, and what in their value
# (lower case, whitespace collapsed) fails closed: a caps keyword (small-caps, all-small-caps, petite-caps,
# all-petite-caps, titling-caps) or unicase, a small-capital OpenType feature (smcp, c2sc, pcap, c2pc, unic, titl), a
# value this cannot read (var(), env(), attr() or an escape), or a system font, which sets every font property.
CAPS_PROPERTIES = ("font", "font-variant", "font-variant-caps", "font-feature-settings")
CAPS_VALUE = re.compile(r"caps|unicase|smcp|c2sc|pcap|c2pc|unic|titl|\b(?:var|env|attr)\(|\\"
                        r"|^(?:caption|icon|menu|message-box|small-caption|status-bar)$")


def transform_rules(sheets: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Each selector, whitespace collapsed, of each rule in sheets (stylesheet texts) that sets text-transform, with
    the value it sets, uppercase or none, in order (comments removed, a selector list split at commas); and what this
    does not read, each a failure: a text-transform of any other value (such as full-width uppercase, var(--tt) or
    uppercase !important), a rule nested in a style rule, a text-transform in an at-rule other than @media and
    @supports, a text-transform: none inside any at-rule, and a property name in a style rule that holds a backslash
    (a CSS escape, which can spell text-transform). A rule inside @media or @supports that sets uppercase
    is read as if it always applied, which shows at least what a browser shows in upper case. Small capitals, which
    show the label in capital letters and which the label rule does not read, fail too: in any rule or at-rule (such
    as @font-face), a declaration of CAPS_PROPERTIES whose value CAPS_VALUE matches, a font-variant-caps other than
    normal, and a property name in an at-rule that holds a backslash."""
    found, unread = [], []
    for sheet in sheets:
        # The preludes of the open blocks, outermost first, and the text since the last brace.
        blocks, text = [], ""
        for piece in re.split(r"([{}])", re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)):
            if piece == "{":
                if blocks and not blocks[-1].startswith("@"):
                    unread.append(f"a rule nested in the style rule {blocks[-1]!r}")
                blocks.append(" ".join(text.split()))
            elif piece == "}":
                prelude, at_rules = (blocks.pop(), blocks) if blocks else ("", [])
                for declaration in text.split(";") if prelude else []:
                    name, _, value = declaration.partition(":")
                    name, value = name.strip().lower(), " ".join(value.lower().split())
                    if prelude.startswith("@") and "\\" in name:
                        unread.append(f"a property name with an escape, {name!r}, in {prelude!r}")
                    elif name in CAPS_PROPERTIES and (CAPS_VALUE.search(value)
                                                      or (name == "font-variant-caps" and value != "normal")):
                        unread.append(f"{name}: {value} in {prelude!r}" + (f" inside {at_rules[-1]!r}"
                                                                            if at_rules else ""))
                for declaration in text.split(";") if prelude and not prelude.startswith("@") else []:
                    name, _, value = declaration.partition(":")
                    if "\\" in name:
                        # An escape can spell text-transform (text\2d transform), which the name test below misses.
                        unread.append(f"a property name with an escape, {name.strip()!r}, in {prelude!r}")
                        continue
                    if name.strip().lower() != "text-transform":
                        continue
                    value = " ".join(value.lower().split())
                    outside = [rule for rule in at_rules if not rule.lower().startswith(("@media", "@supports"))]
                    if value not in ("uppercase", "none") or outside or (at_rules and value == "none"):
                        unread.append(f"text-transform: {value} in {prelude!r}" + (f" inside {at_rules[-1]!r}"
                                                                                     if at_rules else ""))
                    else:
                        found += [(" ".join(selector.split()), value) for selector in prelude.split(",")]
            if piece in "{}":
                text = ""
            else:
                text += piece
    return found, unread


def specificity(selector: str) -> tuple[int, int]:
    """The specificity of selector, a SIMPLE_SELECTOR, as (.class parts, names other than *)."""
    return len(re.findall(r"\.[A-Za-z0-9_-]+", selector)), len(re.findall(r"(?:^|[ >])[a-z]", selector))


def shown_upper(open_elements: list[tuple[str, list[str]]], inherited: bool) -> bool:
    """Whether a browser shows the text of the last of open_elements in upper case, by the stylesheets' rules, as
    UPPERCASE and RESET give them: the matching selector of highest specificity decides, an uppercase one on a tie
    (which shows at least what a browser shows in upper case); with none matching, inherited, as its parent's."""
    upper, reset = ([specificity(selector) for selector in selectors if matches(selector, open_elements)]
                    for selectors in (UPPERCASE, RESET))
    if reset and (not upper or max(reset) > max(upper)):
        return False
    return bool(upper) or inherited


def matches(selector: str, open_elements: list[tuple[str, list[str]]]) -> bool:
    """Whether selector, a SIMPLE_SELECTOR, matches the last of open_elements, (name, classes) outermost first, given
    the others as its ancestors."""
    *rest, subject = selector.replace(">", " > ").split()
    name, *classes = subject.split(".")
    if not open_elements or name not in ("", "*", open_elements[-1][0]):
        return False
    if not set(classes) <= set(open_elements[-1][1]):
        return False
    if not rest:
        return True
    if rest[-1] == ">":
        return matches(" ".join(rest[:-1]), open_elements[:-1])
    return any(matches(" ".join(rest), open_elements[:depth]) for depth in range(len(open_elements) - 1, 0, -1))


def uppercase_coverage(listed: list[str], resets: list[str], sheets: list[str]) -> list[str]:
    """What keeps listed and resets, lists such as the generator's UPPERCASE_SELECTORS and RESET_SELECTORS, from
    naming exactly the selectors of the text-transform: uppercase and text-transform: none rules of sheets
    (stylesheet texts), each a SIMPLE_SELECTOR, and each text-transform that transform_rules() does not read."""
    rules, problems = transform_rules(sheets)
    problems = [f"the stylesheets set {problem}, which the generator does not read" for problem in problems]
    for value, given, name in (("uppercase", listed, "UPPERCASE_SELECTORS"), ("none", resets, "RESET_SELECTORS")):
        found = [selector for selector, set_to in rules if set_to == value]
        problems += [f"a text-transform: {value} rule names {selector!r}, which {name} lacks"
                     for selector in found if selector not in given]
        problems += [f"{name} names {selector!r}, which no text-transform: {value} rule names"
                     for selector in given if selector not in found]
    return problems + [f"{selector!r} is not a selector that selector_matches() reads"
                       for selector in [selector for selector, _ in rules] + listed + resets
                       if not SIMPLE_SELECTOR.fullmatch(selector)]


def label_text(joined: str) -> str:
    """joined with each character of general category Cf, each Default_Ignorable_Code_Point (the generator's
    DEFAULT_IGNORABLE ranges), each character of the install gate's ZERO_WIDTH other than U+00A0, and U+0000 deleted,
    then decomposed by NFKD (a fullwidth letter reads as its Latin letter), with each Latin small capital (named
    LATIN LETTER SMALL CAPITAL and 1 letter) read as that capital, and each character other than a letter or a
    digit (general category L or N) deleted."""
    deleted = {ord(character): None for character in set(joined)
               if unicodedata.category(character) == "Cf" or character in GATE.ZERO_WIDTH.replace("\u00a0", "") + "\0"
               or any(first <= ord(character) <= last for first, last in LOADED.DEFAULT_IGNORABLE)}
    joined = unicodedata.normalize("NFKD", joined.translate(deleted))
    read = {}
    for character in set(joined):
        name = unicodedata.name(character, "")
        if re.fullmatch(r"LATIN LETTER SMALL CAPITAL [A-Z]", name):
            read[ord(character)] = name[-1]
        elif unicodedata.category(character)[0] not in "LN":
            read[ord(character)] = None
    return joined.translate(read)


def labels(text: str) -> tuple[int, int, int, int, int]:
    """How many times the parsed text of text (attribute values and comments apart, character references decoded),
    joined across elements and read by label_text(), carries LABELS, case-sensitive, but with the text that a
    browser shows in upper case (shown_upper()) in upper case, so there in any letter case: in all of it, and twice
    in the text that shows, outside every INERT element and every element the install gate reads as hiding, first
    with an element that only aria-hidden="true" hides read as shown (a browser shows it), then with it read as
    hidden; and those 2 again as a browser with scripting off shows the page, with the content of each noscript kept
    (its hiding rules applying), as the generator's scripting_off() reads it. In every choice for the reading, each
    details without open is read closed (its content other than its first summary left out) or opened, and each
    img's alt text kept or left out (a browser shows one only when its image does not load), and each reading counts
    the most that a choice gives, its labels counted together. Each reading is also read in the hero's narrow-width
    order, as the generator reads it, with the hero image's alt text moved to the end of the kicker, or to the start
    of the hero's text when its first child is not a p.lbl (Placement.kicker_end, hero_alt), and counts the more of
    its 2 orders."""
    parsed = Placement()
    parsed.feed(text)
    parsed.close()
    whole = list(zip(parsed.text, (around for _, around in parsed.text_at)))
    orders = [list(range(len(whole)))]
    kicker, alt = parsed.kicker_end, parsed.hero_alt
    if kicker is not None and alt is not None and kicker <= alt:
        orders.append([*range(kicker), alt, *range(kicker, alt), *range(alt + 1, len(whole))])
    counts = []
    for visual, scripting in ((None, True), (True, True), (False, True), (True, False), (False, False)):
        most = 0
        for order in orders:
            reading = [whole[index] for index in order
                       if visual is None or shows(parsed, whole[index][1], visual, True, scripting)]
            # For each piece, the details that fold it and, for an alt text, its img: it shows when all of them do.
            needs = [folding(parsed, around) | ({around[-1]} if around and parsed.starts[around[-1]][0] == "img"
                                                else set()) for _, around in reading]
            options = sorted(set().union(*needs))
            for kept in itertools.product((True, False), repeat=len(options)):
                left = {option for option, keep in zip(options, kept) if not keep}
                joined = label_text("".join(read for (read, _), need in zip(reading, needs) if not need & left))
                most = max(most, sum(joined.count(label_text(label)) for label in LABELS))
        counts.append(most)
    return tuple(counts)


def folding(parsed: Placement, around: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """Where each details without open starts that folds text whose open elements (and, for an img's alt text, the
    img) start at around, outermost first: it holds the text directly, or by a child other than its first summary."""
    folds = {at for at, child in zip(around, around[1:]) if closed_details(parsed, [at, child])}
    if around and parsed.starts[around[-1]][0] == "details" and "open" not in parsed.starts[around[-1]][1]:
        folds.add(around[-1])
    return folds


def shows(parsed: Placement, around: list[tuple[int, int]], visual: bool = False, opened: bool = False,
          scripting: bool = True) -> bool:
    """Whether text whose open elements start at around, outermost first, shows: no INERT element (with scripting
    off, no INERT element but noscript, whose content a browser then renders, and which then hides only by its
    attributes, read as on a span), no element the install gate reads as hiding (given visual, with its aria-hidden
    attribute left out, since aria-hidden="true" hides an element from assistive technology only) and, unless opened
    (a reader opens every details), no details without open (directly, or by a child other than its first summary)
    holds it."""
    return not (any(parsed.starts[at][0] in (INERT if scripting else INERT - {"noscript"})
                    or IS_HIDING("span" if not scripting and parsed.starts[at][0] == "noscript"
                                 else parsed.starts[at][0],
                                 {name: value for name, value in parsed.starts[at][1].items()
                                  if not (visual and name == "aria-hidden")})
                    for at in around)
                or (not opened and closed_details(parsed, around))
                or (not opened and around and parsed.starts[around[-1]][0] == "details"
                    and "open" not in parsed.starts[around[-1]][1]))


# The install gate as the generator reads it, by its own install_gate(), from the same source bytes and never from
# cached bytecode: the hiding reader its value paragraph rule applies and the ZERO_WIDTH its label rule deletes. A gate
# the generator cannot read fails this test with exit 1, rather than stopping it with a traceback.
LOADED = load_module(GENERATOR)
try:
    GATE = LOADED.install_gate()
except LOADED.Unreadable as error:
    print(f"test-build-site: failures:\n  - the install gate, read by the generator's install_gate(): {error}")
    raise SystemExit(1)
IS_HIDING = GATE.is_hiding_element
# The selectors of the rules that set text-transform to uppercase and to none, read from the stylesheets themselves,
# apart from the generator's UPPERCASE_SELECTORS and RESET_SELECTORS (check_uppercase_selectors() compares them). A
# stylesheet that cannot be read fails this test with exit 1, rather than stopping it with a traceback.
try:
    RULES = transform_rules([path.read_text(encoding="utf-8") for path in STYLESHEETS])[0]
except (OSError, UnicodeError) as error:
    print(f"test-build-site: failures:\n  - the stylesheets every page loads: {error}")
    raise SystemExit(1)
UPPERCASE = [selector for selector, value in RULES if value == "uppercase"]
RESET = [selector for selector, value in RULES if value == "none"]


def closed_details(parsed: Placement, path: list[tuple[int, int]]) -> bool:
    """Whether the element whose ancestors and own start are path, outermost first, is hidden by a details without
    open: it or an ancestor is a child of one other than its first summary child, as the install gate's PageParser
    reads it."""
    for at, child in zip(path, path[1:]):
        tag, attrs, *_ = parsed.starts[at]
        if tag == "details" and "open" not in attrs:
            summaries = sorted(start for start, (name, *_) in parsed.starts.items()
                               if name == "summary" and parsed.lineage[start] == [*parsed.lineage[at], at])
            if summaries[:1] != [child]:
                return True
    return False


def about_problems(page: str, text: str, base: str) -> list[str]:
    """The About block of specification 7.24, which the generator writes: on the landing page, exactly 1 p.value,
    with no INERT ancestor, not hidden by itself or by an ancestor as tools/check-install-page.py reads hiding (its
    is_hiding_element(), and a details without open outside its first summary child), holding no element but an a
    with no attribute but href or an em with no attribute and no character but those of VALUE_SPACES, VALUE_SIGNS
    and VALUE_CATEGORIES after NFC, with at least 1 letter, no dot span followed directly
    by a link (the 1.6.1 markup, refused apart from about_line()), and the whole About block once, byte for byte,
    starting where the end tag of that paragraph's region (the div.region nearest it among its open elements) ends,
    the region and the block each with exactly the ancestors ANCESTORS, the region holding exactly REGION_CHILDREN
    (a p.lbl whose text that shows, aria-hidden and alt text apart, holds a letter or a digit, then the div that
    holds the
    p.value) and no text directly, its row the only parsed element whose classes include about, and the page's
    text, and its text that shows in both readings with scripting on and off, each carrying LABELS once, inside the
    block, in either hero order (labels(): with the block's label taken out, none; in any letter case where
    shown_upper() reads upper case); on
    any other page, no such element, with an INERT ancestor or not, and no LABELS in its text.
    Of the stylesheets' rules it models only the install gate's HIDING_CLASSES, the rules that set text-transform
    (shown_upper(), through labels()) and the hero's narrow-width order (labels()); it does not model any other
    stylesheet rule, such as one that hides or moves an element by a descendant selector, or a hidden attribute
    that HTML5 copies from a stray body or html start tag onto the page's body or html element. The generator
    refuses such a start tag in a page source, and any page source outside the page source grammar, on which its
    parser and a browser read the same tokens (no raw-text or escapable raw-text element, whose content a browser can
    read as markup inside math or svg, among them); and it refuses a math start tag in a page source or page and any
    <svg other than the switch in a page."""
    parsed = Placement()
    parsed.feed(text)
    parsed.close()
    abouts = [at for at, (_, attrs, *_) in parsed.starts.items() if "about" in class_names(attrs.get("class", ""))]
    if page != "index.html":
        if abouts:
            return [f"{page} carries About markup, which only the landing page's About block may"]
        if any(labels(text)):
            return [f"{page} carries the About block's label in its text; only the landing page's About block may"]
        return []
    values = [at for at, (tag, attrs, *_) in parsed.starts.items()
              if tag == "p" and "value" in class_names(attrs.get("class", ""))]
    if len(values) != 1:
        return [f"{page} carries {len(values)} p.value elements; exactly 1 is required (specification 7.24)"]
    if any(name in INERT for name, _ in parsed.starts[values[0]][2]):
        return [f"{page} carries its value paragraph inside an element of INERT (specification 7.24)"]
    path = [*parsed.lineage[values[0]], values[0]]
    if any(IS_HIDING(*parsed.starts[at][:2]) for at in path) or closed_details(parsed, path):
        return [f"{page} carries its value paragraph hidden, by itself or by an ancestor (specification 7.24)"]
    # Its content is pinned: no element but an a with no attribute but href or an em with no attribute, and text of
    # VALUE_CATEGORIES and VALUE_SPACES only after NFC, with at least 1 letter.
    inside = [start for at, start in parsed.starts.items() if values[0] in parsed.lineage[at]]
    text_in = unicodedata.normalize("NFC", "".join(data for data, around in parsed.text_at if values[0] in around))
    if (any(tag not in ("a", "em") or set(attrs) - ({"href"} if tag == "a" else set()) for tag, attrs, *_ in inside)
            or any(character not in VALUE_SPACES + VALUE_SIGNS
                   and unicodedata.category(character) not in VALUE_CATEGORIES for character in text_in)
            or not any(unicodedata.category(character) in ("Lu", "Ll", "Lt") for character in text_in)):
        return [f"{page} carries its value paragraph with markup or text outside its pin (specification 7.24)"]
    if "&middot;</span><a" in text:
        return [f"{page} carries an About row dot with no space after it, the 1.6.1 markup (specification 7.24)"]
    block = about_block(base)
    at = text.find(block)
    # The end tag that ends where the block starts, as the generator's END_TAG reads it: </div>, its name in any ASCII
    # letter case, with ASCII whitespace before its > if any.
    closing = re.search(r"</[dD][iI][vV][ \t\n\f\r]*>\Z", text[:at]) if text.count(block) == 1 else None
    if closing is None:
        return [f"{page} lacks the whole About block once, byte for byte, right after a div end tag (specification 7.24)"]
    region = parsed.ends.get(position(text, closing.start()))
    nearest = [ancestor for ancestor in parsed.lineage[values[0]] if parsed.starts[ancestor][0] == "div"
               and "region" in class_names(parsed.starts[ancestor][1].get("class", ""))][-1:]
    if region is None or [region[3]] != nearest:
        return [f"{page} carries its About block other than directly after the value paragraph's region (specification 7.24)"]
    if parsed.starts[nearest[0]][2] != ANCESTORS or parsed.starts[position(text, at)][2] != ANCESTORS:
        return [f"{page} carries its value region or its About block with ancestors other than html, body, main and "
                "div.wrap (specification 7.24)"]
    # The value region holds exactly REGION_CHILDREN, as the committed landing page does: a p.lbl whose text that
    # shows (aria-hidden apart) holds a letter or a digit, then the div that holds the p.value, and no text directly.
    inner = [*parsed.lineage[nearest[0]], nearest[0]]
    children = [at for at in parsed.starts if parsed.lineage[at] == inner]
    # Text, not an img's alt text (held by the img), which a browser shows only when the image does not load.
    label_shown = "".join(data for data, around in parsed.text_at if children and children[0] in around
                          and parsed.starts[around[-1]][0] != "img" and shows(parsed, around, True))
    if (any(data.strip(" \t\n\f\r") for data, around in parsed.text_at if around == inner)
            or [(parsed.starts[at][0], sorted(set(class_names(parsed.starts[at][1].get("class", "")))))
                for at in children] != REGION_CHILDREN
            or children[1] not in parsed.lineage[values[0]] or not label_text(label_shown)):
        return [f"{page} carries its value region with text or children other than a p.lbl with text that shows, "
                "then the div that holds its value paragraph"]
    if len(abouts) != 1:
        return [f"{page} carries About markup outside its About block (specification 7.24)"]
    if labels(text) != (1,) * 5 or any(labels(text.replace(block, block.replace(f">{LABEL}<", "><", 1), 1))):
        return [f"{page} carries the About block's label in its text other than once, inside its About block "
                "(specification 7.24)"]
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
    """Set the base to /draft/ and exclude the draft's home page from the sitemap, as the draft branch would."""
    path = root / "site-src" / "site.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["base"] = "/draft/"
    path.write_text(json.dumps(data), encoding="utf-8")
    exclude_draft_home(root)


def exclude_draft_home(root: Path) -> None:
    """Exclude the draft's home page from the sitemap (recorded exclusion E1), once, as the draft branch does."""
    path = root / "tools" / "sitemap-config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["exclude"] = [entry for entry in data["exclude"] if entry != "draft/index.html"] + ["draft/index.html"]
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
    ("a later stylesheet in the body", inject('<link rel="stylesheet" href="{{base}}assets/baseline/baseline.css?v=1.11.1">')),
    ("a stylesheet in upper case in the body", inject('<LINK REL="stylesheet" HREF="{{base}}assets/baseline/baseline.css?v=1.11.1">')),
    ("a bare svg outside the switch", inject("<svg></svg>")),
    ("an upper-case SVG outside the switch", inject("<SVG></SVG>")),
    ("a second scheme.js load in another spelling",
        inject('<SCRIPT SRC="{{base}}assets/baseline/sch&#101;me.js?v=1.11.1" defer></SCRIPT>')),
    ("a second scheme.js load as the first of 2 src attributes", inject(
        '<SCRIPT SRC="{{base}}assets/baseline/sch&#101;me.js?v=1.11.1" src="{{base}}assets/baseline/copy.js?v=1.11.1" defer></SCRIPT>')),
    ("an attribute repeated on any other tag", inject('<p class="lead" class="x">x</p>')),
    ("a link to the pinned build tool, which is never served",
        inject('<p><a href="/.baseline/check_palette.py">palette gate</a></p>')),
    ("a module script", inject('<script type="module">alert(1)</script>')),
    ("an on* handler", inject('<p onclick="x()">x</p>')),
    ("what this is framing", inject("<p>What this is not: a filter.</p>")),
    ("what this is framing with a character reference", inject("<p>What&#32;this is not: a filter.</p>")),
    ("an em dash as a character reference", inject("<p>x &mdash; y</p>")),
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
        root, "site-src/pages/404.html", "</h1>", '</h1><script type="application/ld+json">{}</script>')),
    ("a page with no modified date", lambda root: set_page(root, "demo", modified=None)),
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
    ("the sitemap config still excludes the removed draft holding page", exclude_draft_home),
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


# The generator writes the About block of 7.24 itself, so a page source with About markup of its own, or a landing
# page source whose value paragraph gives it no single, live place, is refused before the output is read.
CLASS_RULE = "an element whose classes include about; the generator writes the About block"
VALUE_RULE = "the landing page source must carry exactly 1 p.value"
REGION_RULE = "the value paragraph has no enclosing div.region"
# The generator writes each page's html, head and body, so a page source may carry none: HTML5 copies the attributes
# of a stray html or body start tag, such as hidden, onto the page's own. Nor may it carry a frameset start tag, which
# tools/check-install-page.py reads as hiding the whole page.
DOCUMENT_RULE = "the generator writes the page's html, head and body"
# Inside math, a browser can read a title or textarea's content as markup, which the generator's parser reads as text.
MATH_RULE = "; inside math, a browser can read"
# The generator reads each page again for a math start tag, as its parser reads it.
PAGE_MATH_RULE = "a <math> start tag in the page"
# Markup outside the page source grammar, on which the generator's parser and a browser read the same tokens: a < in
# text, a comment whose text holds <, > or --, an attribute value holding < or >, a raw-text or escapable raw-text
# element, template, a CDATA section, a processing instruction or a DOCTYPE.
GRAMMAR_RULE = "a page source holds only markup on which Python's parser and a browser read the same tokens"
# A start tag outside the generator's SOURCE_ELEMENTS, such as select or input, at which a browser ends an open select
# and places what follows outside it; and a noscript inside a noscript, which a browser with scripting on ends at the
# inner one's end tag. Each moved the value paragraph out of the first summary of a closed details as a browser reads
# it, while the parser read it inside.
ELEMENT_RULE = "a page source carries only the elements of SOURCE_ELEMENTS"
NOSCRIPT_RULE = "a <noscript> start tag inside a noscript"
# An attribute name outside the generator's SOURCE_ATTRIBUTES, such as name, at which a browser closes all but 1 open
# details of a name group, or open, inert or popover; and an end tag of an element outside SOURCE_ELEMENTS, such as
# </br>, which a browser reads as a br start tag and moves to before a table it is directly inside.
ATTRIBUTE_RULE = "a page source carries only the attributes of SOURCE_ATTRIBUTES"
END_TAG_RULE = "an end tag in a page source names an element of SOURCE_ELEMENTS"
# The generator's page source tree rules: a summary only as the first element child of a details, since a browser
# moves an earlier summary inside a p or a table in a closed details out to be the details' first summary, hiding the
# value paragraph in the next one; and no start tag or text at which a browser ends an open p, heading, li, a or button,
# or that it moves out of a table part or ignores outside one, where the parser reads it as written.
SUMMARY_RULE = "a summary is allowed only as the first element child of a details"
P_RULE = "start tag inside an open p at"
HEADING_RULE = "a browser ends the heading there"
LI_RULE = "a <li> start tag inside an open li"
TABLE_RULE = "a table holds only caption, thead and tbody"
TABLE_TEXT_RULE = "text other than whitespace directly inside a"
# The About block's label in a page source's text: the generator writes it, in the block, on the landing page only.
LABEL_RULE = "the About block's label in the page source's text"
# Characters the label rule deletes beyond the install gate's ZERO_WIDTH and U+0000: the format characters (Cf)
# U+2061, U+2063, U+180E and U+E0020, and the default-ignorable U+034F and U+FE0F (Mn).
LABEL_IGNORED = ("\u2061", "\u2063", "\u180e", "\U000e0020", "\u034f", "\ufe0f")
VALUE = '<p class="value">'
VALUE_REGION = '<div class="region" id="what-it-fixes">'
VALUE_END = "outside its aim.</p></div></div>"
# The value paragraph holds markup or text outside its pin (row 145): it may hold no element but an a
# with no attribute but href or an em with no attribute, and no character but those of VALUE_SPACES (the ordinary
# space, U+0009, U+000A, U+000D and U+00A0) and VALUE_CATEGORIES (letters, decimal digits, punctuation, and currency
# and math symbols, apart from the generator's own lists), with at least 1 letter.
VALUE_PIN_RULE = "the value paragraph holds markup or text outside its pin"
VALUE_CATEGORIES = {"Lu", "Ll", "Lt", "Nd", "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po", "Sc", "Sm"}
VALUE_SPACES = " \t\n\r\u00a0"
# The pin also admits these visible signs by name: the copyright, registered, trade mark and service mark signs, the
# degree sign, the superscript digits, and every character named VULGAR FRACTION.
VALUE_SIGNS = ("\u00a9\u00ae\u2122\u2120\u00b0\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
               "\u00bc\u00bd\u00be\u2150\u2151\u2152\u2153\u2154\u2155\u2156\u2157\u2158\u2159\u215a\u215b\u215c"
               "\u215d\u215e\u2189")
# A page source carries no hidden=until-found, and no text in a details before its summary.
UNTIL_FOUND_RULE = "a browser shows the content of an element with hidden=until-found"
SUMMARY_ORDER_RULE = "a browser shows a details' summary before the rest of its content"
# A table's children in the order a browser shows them, and at most 1 hero on a page.
TABLE_ORDER_RULE = "a browser shows a table's caption first and its thead before its tbody"
HEROES_RULE = "a page source carries at most 1 hero"
LOGO = "{{base}}assets/baseline/logos/cleanlanguage.svg"
# A page source carries no class name outside the generator's SOURCE_CLASSES, and the value paragraph's region none
# outside VALUE_REGION_CLASSES; nor may a page source (with_about()) or a page (validate()) carry a bidi formatting
# character, each refused by its own message.
CLASS_PIN_RULE = "a page source carries only the class names of SOURCE_CLASSES"
REGION_CLASS_RULE = "there a page source carries only the class names of VALUE_REGION_CLASSES"
# The value paragraph's region holds other than its committed children: a p.lbl with text
# that shows, then the div that holds the p.value, and no text; .region shows its first child in its label column.
# The source cases match the part of the message that only with_about() writes (it names where the region starts),
# since validate() refuses the same built page; validate()'s cases match the reason both give.
REGION_CHILDREN_RULE = "the value paragraph's region at line"
REGION_PIN_RULE = "so it holds only a p.lbl with text that shows, then the div that holds the p.value"
REGION_LABEL = '<p class="lbl">What it gives you</p>'
# A class name of VALUE_REGION_CLASSES away from its 1 place in the value region: region only
# on the region, lbl only on its label and value only on the p.value, since .region sets display: grid.
REGION_PLACE_RULE = "is away from its place in the value paragraph's region"
# A class of the generator's PLACED_CLASSES, which a stylesheet rule uses to place an element out of its source order,
# outside the place the committed sources use it; an element of PLACED_CHILDREN whose children are outside their
# order; a hero image whose alt text is not site.json's logo_alt; and a class that only the generator's rail carries.
PLACED_RULE = "is outside its pinned place"
DATA_COPY_RULE = "outside the copy button's pinned form"
ORDER_RULE = "holds text or children outside its pinned order"
HERO_ALT_RULE = "has an alt text other than site.json's logo_alt"
RAIL_RULE = "which only the rail the generator writes at <!--rail--> carries"
RAILS_RULE = "more than 1 <!--rail-->"
HERO_KICKER = '<p class="lbl gold">A skill you install once, anywhere.</p>'
HERO_ALT = 'alt="A document with a green check mark and a pen, the Clean Language mark"'
HERO_STATEMENT = '<h1 class="statement">Precise, direct, natural <em>AI writing.</em></h1>'
BIDI_RULE = "the page source holds a bidi formatting character, U+"
PAGE_BIDI_RULE = "the page holds a bidi formatting character, U+"
BIDI = "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
# Text that a browser shows as nothing: U+200B, a soft hyphen, U+2060, U+034F, a space, U+00A0 and U+200D.
INVISIBLE = "&#8203;&shy;\u2060\u034f &nbsp;\u200d"
# The label in mixed case, which a stylesheet that sets text-transform: uppercase shows as the label in upper case.
MIXED_LABEL = "About This Project"
LABEL_TH = f"<table><caption>c</caption><thead><tr><th>{MIXED_LABEL}</th></tr></thead></table>"
# Wrappers around the value paragraph that tools/check-install-page.py reads as hiding it, and wrappers it reads as
# showing it, by is_hiding_element() and, for details, as its PageParser reads one: (name, start, end).
HIDING_WRAPPERS = [
    ("an inert div", "<div inert>", "</div>"),
    ('a div with aria-hidden="true"', '<div aria-hidden="true">', "</div>"),
    ('a div with aria-hidden="TRUE"', '<div aria-hidden="TRUE">', "</div>"),
    ("a div with popover", "<div popover>", "</div>"),
    ('a div with popover="manual"', '<div popover="manual">', "</div>"),
    ("a dialog without open", "<dialog>", "</dialog>"),
    ("a dialog with open and popover", "<dialog open popover>", "</dialog>"),
    ("a details without open", "<details>", "</details>"),
    ("a details without open, after its first summary", "<details><summary>x</summary>", "</details>"),
    # A browser, and the install gate, read the first of 2 attributes with the same name.
    ('a div with aria-hidden="true" before aria-hidden="false"', '<div aria-hidden="true" aria-hidden="false">',
     "</div>"),
] + [(f"a div with the {name} class", f'<div class="{name}">', "</div>")
     for name in ("vh", "visually-hidden", "only-dark", "skip")]
SHOWING_WRAPPERS = [
    ('a div with aria-hidden="false"', '<div aria-hidden="false">', "</div>"),
    ("a dialog with open", "<dialog open>", "</dialog>"),
    ("a details with open", "<details open>", "</details>"),
    ("a div with the vh-x class", '<div class="vh-x">', "</div>"),
    ("the first summary of a details without open", "<details><summary>", "</summary></details>"),
    # A details without open stops hiding at its end tag: a div after one, and the value paragraph in it, show.
    ("a div after a closed details without open", "<details><summary></summary></details><div>", "</div>"),
]


def wrapper_rule(start: str) -> str:
    """The rule by which the generator refuses a landing page source with start around the value paragraph: no dialog
    (SOURCE_ELEMENTS), no inert, popover or open attribute (SOURCE_ATTRIBUTES), and otherwise the value paragraph's."""
    if start.startswith("<dialog"):
        return ELEMENT_RULE
    if re.search(r"[ \t](?:inert|popover|open)\b", start):
        return ATTRIBUTE_RULE
    return VALUE_RULE


def after_value(snippet: str):
    """Put snippet in the landing page's source directly after the end tag of the value paragraph's region."""
    return lambda root: edit(root, HOME, VALUE_END, VALUE_END + snippet)


def wrap_value(start: str, end: str):
    """Wrap the landing page's value paragraph in start and end."""
    return lambda root: (edit(root, HOME, VALUE, start + VALUE),
                         edit(root, HOME, VALUE_END, VALUE_END.replace("</p>", "</p>" + end, 1)))


def wrap_value_content(start: str, end: str):
    """Wrap the whole content of the landing page's value paragraph, its link included, in start and end."""
    return lambda root: (edit(root, HOME, VALUE, VALUE + start),
                         edit(root, HOME, VALUE_END, VALUE_END.replace("</p>", end + "</p>", 1)))


def value_content(content: str):
    """Put content in place of the whole content of the landing page's value paragraph."""
    def apply(root: Path) -> None:
        path = root / HOME
        text = path.read_text(encoding="utf-8")
        start = text.index(VALUE) + len(VALUE)
        path.write_text(text[:start] + content + text[text.index("</p>", start):], encoding="utf-8")
    return apply


def at_end(snippet: str):
    """Put snippet at the end of the demo page's source, where the generator's own markup follows it."""
    def apply(root: Path) -> None:
        path = root / PAGE
        path.write_text(path.read_text(encoding="utf-8") + snippet, encoding="utf-8")
    return apply


SOURCE_REFUSALS = [
    ("the whole About block put back in home.html", after_value(ABOUT_BLOCK), CLASS_RULE),
    ("the About row alone put back in home.html", after_value(ABOUT_ROW), CLASS_RULE),
    ("an about class added to the intro paragraph in home.html", lambda root: edit(
        root, HOME, '<p class="intro">', '<p class="intro about">'), CLASS_RULE),
    ("an about class in single quotes inside noscript in home.html",
        after_value("<noscript><p class='x about'>x</p></noscript>"), CLASS_RULE),
    ("an About row on an inner page", inject('<p class="about"><a href="{{base}}install/">Install</a></p>'), CLASS_RULE),
    ("an About row with an unquoted class on an inner page",
        inject('<p class=about><a href="{{base}}install/">Install</a></p>'), CLASS_RULE),
    ("an About row with a single-quoted class on an inner page",
        inject("<p class='about'><a href=\"{{base}}install/\">Install</a></p>"), CLASS_RULE),
    ("an About row with 2 classes on an inner page",
        inject('<p class="about x"><a href="{{base}}install/">Install</a></p>'), CLASS_RULE),
    ("an About row with 2 classes inside noscript on an inner page",
        inject('<noscript><p class="about x"><a href="{{base}}install/">Install</a></p></noscript>'), CLASS_RULE),
    ("a second p.value in the hero", lambda root: edit(
        root, HOME, '<div class="hero-text">', '<div class="hero-text"><p class="value">x</p>'), VALUE_RULE),
    ("a second p.value in its own region after the value region",
        after_value('<div class="region"><p class="value">x</p></div>'), VALUE_RULE),
    ("a second p.value that carries a hidden attribute", after_value('<p class="value" hidden>x</p>'), VALUE_RULE),
    ("a second p.value region inside a hidden div",
        after_value('<div hidden><div class="region"><p class="value">x</p></div></div>'), VALUE_RULE),
    ("a second p.value region inside noscript",
        after_value('<noscript><div class="region"><p class="value">x</p></div></noscript>'), VALUE_RULE),
    ("no p.value", lambda root: edit(root, HOME, VALUE, '<p class="lead">'), VALUE_RULE),
    ("the value paragraph inside noscript", wrap_value("<noscript>", "</noscript>"), VALUE_RULE),
    ("the value paragraph inside canvas", wrap_value("<canvas>", "</canvas>"), ELEMENT_RULE),
    # The until-found rule refuses these before the value paragraph rule reads them as hidden.
    ("the value paragraph inside a div with hidden=until-found", wrap_value('<div hidden="until-found">', "</div>"),
        UNTIL_FOUND_RULE),
    ("the value paragraph with a hidden attribute", lambda root: edit(root, HOME, VALUE, '<p class="value" hidden>'),
        VALUE_RULE),
    ("the value paragraph with hidden=until-found", lambda root: edit(
        root, HOME, VALUE, '<p class="value" hidden="until-found">'), UNTIL_FOUND_RULE),
    ("the value paragraph's region with a hidden attribute", lambda root: edit(
        root, HOME, VALUE_REGION, VALUE_REGION.replace(">", " hidden>")), VALUE_RULE),
    ("a p.value with no region", lambda root: edit(root, HOME, VALUE_REGION, '<div id="what-it-fixes">'), REGION_RULE),
    ("a p.value whose nearest region is a section", lambda root: (
        edit(root, HOME, VALUE_REGION, '<section class="region" id="what-it-fixes">'),
        edit(root, HOME, VALUE_END, VALUE_END[:-len("</div>")] + "</section>")), REGION_RULE),
    ("the value paragraph with the vh class", lambda root: edit(root, HOME, VALUE, '<p class="value vh">'), VALUE_RULE),
    ("a body start tag with a hidden attribute in a page source", inject("<body hidden>"), DOCUMENT_RULE),
    ("a closed body element with a hidden attribute in a page source", inject("<body hidden></body>"), DOCUMENT_RULE),
    ("an html start tag with a hidden attribute in a page source", inject("<html hidden>"), DOCUMENT_RULE),
    ("a closed html element with a hidden attribute in a page source", inject("<html hidden></html>"), DOCUMENT_RULE),
    ("a head start tag in a page source", inject("<head>"), DOCUMENT_RULE),
    ("a closed head element in a page source", inject("<head></head>"), DOCUMENT_RULE),
    ("a body start tag in upper case in a page source", inject("<BODY HIDDEN>"), DOCUMENT_RULE),
    ("a self-closing body start tag in a page source", inject("<body/>"), DOCUMENT_RULE),
    ("a body start tag inside noscript in a page source", inject("<noscript><body hidden></noscript>"), DOCUMENT_RULE),
    ("an html start tag after the value paragraph's region in home.html", after_value("<html hidden>"), DOCUMENT_RULE),
    ("a frameset element in a page source", inject("<frameset></frameset>"), DOCUMENT_RULE),
    ("a frameset start tag in upper case in a page source", inject("<FRAMESET>"), DOCUMENT_RULE),
    ("a body start tag inside a math title in a page source", inject("<math><title><body hidden></title></math>"),
        MATH_RULE),
    ("a body start tag inside a math textarea in a page source",
        inject("<math><textarea><body hidden></textarea></math>"), MATH_RULE),
    ("a math element in upper case in a page source", inject("<MATH></MATH>"), MATH_RULE),
    ("a math element with an attribute in a page source", inject('<math display="block"></math>'), MATH_RULE),
    ("a self-closing math start tag in a page source", inject("<math/>"), MATH_RULE),
    # Python's parser and a browser can read a math or body start tag in each of these differently (a comment, a
    # CDATA section, an attribute value or text to one, a tag to the other); the grammar refuses each, read or not.
    ("a math title after a comment that --!> ends", inject("<!-- x --!><math><title><body hidden></title></math>"),
        GRAMMAR_RULE),
    ("a math title after a comment that <!--> ends",
        inject("<!--><math><title><body hidden></title></math>-->"), GRAMMAR_RULE),
    ("a body start tag after a comment that <!---> ends", inject("<!---><body hidden>-->"), GRAMMAR_RULE),
    ("a math title after a CDATA start in a page source",
        inject("<![CDATA[><math><title><body hidden></title></math>]]>"), GRAMMAR_RULE),
    ("a math title after a noscript end tag in a comment",
        inject("<noscript><!-- </noscript><math><title><body hidden></title></math> --></noscript>"), GRAMMAR_RULE),
    ("a body start tag after a noscript end tag in an attribute value",
        inject('<noscript><p title="</noscript><body hidden>">x</p></noscript>'), GRAMMAR_RULE),
    ("a body start tag after a noscript end tag in a title",
        inject("<noscript><title></noscript><body hidden></title></noscript>"), GRAMMAR_RULE),
    ("a page source that ends inside a math start tag", at_end("<math/"), GRAMMAR_RULE),
    # A noscript end tag in a comment or an attribute value outside any noscript: the grammar refuses both, since a
    # comment's text and an attribute value hold no <.
    ("a comment that holds a noscript end tag, outside noscript", inject("<!-- </noscript> -->"), GRAMMAR_RULE),
    ("an attribute value that holds a noscript end tag, outside noscript", inject('<p title="</noscript>">x</p>'),
        GRAMMAR_RULE),
    ("a JSON script with a comment opener and a script before the value paragraph", lambda root: edit(
        root, HOME, VALUE, '<script type="application/json"><!--<script></script>' + VALUE), GRAMMAR_RULE),
    # A browser, with scripting on, ends the outer noscript at the inner end tag, so </summary> closes the summary and
    # the value paragraph becomes a hidden child of the closed details; under legacy select parsing, a nested select
    # or an input ends the select, with the same effect. The parser read the paragraph inside the first summary.
    ("the value paragraph after a noscript inside a noscript in a summary", wrap_value(
        "<details><summary><noscript><summary><noscript></noscript></summary></noscript>", "</summary></details>"),
        NOSCRIPT_RULE),
    ("a noscript inside a noscript", inject("<noscript><noscript><p>x</p></noscript></noscript>"), NOSCRIPT_RULE),
    ("a noscript in upper case inside a noscript", inject("<noscript><p>x</p><NOSCRIPT></NOSCRIPT></noscript>"),
        NOSCRIPT_RULE),
    ("a self-closing noscript inside a noscript", inject("<noscript><noscript/></noscript>"), NOSCRIPT_RULE),
    ("the value paragraph after a select inside a select in a summary", wrap_value(
        "<details><summary><select><summary><select></select></summary></select>", "</summary></details>"),
        ELEMENT_RULE),
    ("the value paragraph after an input inside a select in a summary", wrap_value(
        "<details><summary><select><summary><input></summary></select>", "</summary></details>"), ELEMENT_RULE),
    ("an input in a page source", inject('<p><input type="text"></p>'), ELEMENT_RULE),
    ("a select in upper case in a page source", inject("<SELECT></SELECT>"), ELEMENT_RULE),
    # In each, a browser reads the earlier summary, moved out of the p or the table, as the closed details' first
    # summary; and, in the third, ends the outer li and the div at the inner li, so that </div> ends the div around
    # the open details and </summary> ends the outer summary, before the paragraph.
    ("the value paragraph after a summary inside a p in a closed details", wrap_value(
        "<details><p><summary>x</summary></p><summary>", "</summary></details>"), SUMMARY_RULE),
    ("the value paragraph after a summary inside a table in a closed details", wrap_value(
        "<details><table><summary>x</summary></table><summary>", "</summary></details>"), SUMMARY_RULE),
    # The reported form carries an open attribute, which SOURCE_ATTRIBUTES now refuses first; without it, the li rule.
    ("the value paragraph after an li inside an li in a summary", wrap_value(
        "<details><summary><div><details open><summary><li><div><li></li></div></li></summary>",
        "</details></div></summary></details>"), ATTRIBUTE_RULE),
    ("the value paragraph after an li inside an li in a summary, with no open attribute", wrap_value(
        "<details><summary><div><details><summary><li><div><li></li></div></li></summary>",
        "</details></div></summary></details>"), LI_RULE),
    ("a summary after a div in a details", inject("<details><div>x</div><summary>y</summary></details>"),
        SUMMARY_RULE),
    ("a summary outside a details", inject("<div><summary>x</summary></div>"), SUMMARY_RULE),
    ("a summary inside a summary", inject("<details><summary>x<summary>y</summary></summary></details>"),
        SUMMARY_RULE),
    ("a div inside a p", inject("<p>x<div>y</div></p>"), P_RULE),
    ("a table inside a span in a p", inject("<p><span><table><tbody></tbody></table></span></p>"), P_RULE),
    ("an h3 directly inside an h2", inject("<h2>x<h3>y</h3></h2>"), HEADING_RULE),
    ("an a inside an a", inject("<p><a>x<a>y</a></a></p>"), "a <a> start tag inside an open a"),
    ("a button inside a button", inject('<p><button type="button">x<button type="button">y</button></button></p>'),
        "a <button> start tag inside an open button"),
    ("a div directly inside a table", inject("<table><div>x</div></table>"), TABLE_RULE),
    ("a tr directly inside a table", inject("<table><tr><td>x</td></tr></table>"), TABLE_RULE),
    ("a td outside a table", inject("<div><td>x</td></div>"), TABLE_RULE),
    ("text directly inside a tr", inject("<table><tbody><tr>x<td>y</td></tr></tbody></table>"), TABLE_TEXT_RULE),
    ("the value paragraph inside a dialog with open", wrap_value("<dialog open>", "</dialog>"), ELEMENT_RULE),
    ("the value paragraph inside a details with open", wrap_value("<details open>", "</details>"), ATTRIBUTE_RULE),
    # A browser closes all but 1 open details of a name group, here the later one, so the value paragraph inside it
    # is hidden, where the parser reads both as open.
    ("the value paragraph in the second of 2 open details of 1 name group", wrap_value(
        '<details name="g" open><summary>x</summary></details><details name="g" open><summary>y</summary>',
        "</details>"), ATTRIBUTE_RULE),
    ("a name attribute in upper case on a details", inject('<details NAME="g"><summary>x</summary></details>'),
        "a NAME attribute on a <details> start tag"),
    ("a title attribute", inject('<p title="x">y</p>'), ATTRIBUTE_RULE),
    # A browser's adoption agency moves the About block out of the a around the value region, and its label into a
    # new a, where the parser reads the block inside the a. The value paragraph's own link is written as text, so no
    # a starts inside the a.
    ("an a around the value region", lambda root: (
        edit(root, HOME, '<a href="{{base}}license/">free to use under CC BY-SA 4.0</a>',
             "free to use under CC BY-SA 4.0"),
        edit(root, HOME, VALUE_REGION, '<a href="{{base}}install/">' + VALUE_REGION),
        edit(root, HOME, VALUE_END, VALUE_END + "</a>")), "the region and the block each with exactly the ancestors"),
    ("a div around the value region", lambda root: (
        edit(root, HOME, VALUE_REGION, "<div>" + VALUE_REGION), edit(root, HOME, VALUE_END, VALUE_END + "</div>")),
        "the region and the block each with exactly the ancestors"),
    ("</br> directly inside a tr", inject("<table><tbody><tr></br><td>x</td></tr></tbody></table>"), END_TAG_RULE),
    ("</BR> in a paragraph", inject("<p>x</BR></p>"), END_TAG_RULE),
    ("a comment that holds <math>", inject("<!-- a <math> element -->"), GRAMMAR_RULE),
    ("a comment that holds --", inject("<!-- a -- b -->"), GRAMMAR_RULE),
    ("a comment that holds >", inject("<!-- a > b -->"), GRAMMAR_RULE),
    ("a comment that does not end", at_end("<!-- x"), GRAMMAR_RULE),
    ("an attribute value that holds <math>", inject('<p title="a <math> element">x</p>'), GRAMMAR_RULE),
    ("an attribute value that holds >", inject('<p title="a>b">x</p>'), GRAMMAR_RULE),
    ("a single-quoted attribute value that holds <", inject("<p title='a<b'>x</p>"), GRAMMAR_RULE),
    ("an unquoted attribute value that holds a slash", inject("<p title=a/b>x</p>"), GRAMMAR_RULE),
    ("a < in text", inject("<p>1 < 2</p>"), GRAMMAR_RULE),
    ("an end tag with an attribute", inject('<p>x</p class="y">'), GRAMMAR_RULE),
    ("a DOCTYPE in a page source", inject("<!DOCTYPE html>"), GRAMMAR_RULE),
    ("a processing instruction in a page source", inject("<?xml version='1.0'?>"), GRAMMAR_RULE),
] + [(f"a {name} element in a page source", inject(f"<{name}></{name}>"), GRAMMAR_RULE) for name in (
    "script", "style", "template", "textarea", "title", "xmp", "iframe", "noembed", "noframes", "plaintext", "SCRIPT")
] + [
    # The About block's label in a page source's text, split across elements or lines, written with a character
    # reference or in upper case, or interrupted by a character of the install gate's ZERO_WIDTH other than U+00A0
    # (whitespace here, as str.split() reads it), by U+0000, by another character of general category Cf or by a
    # Default_Ignorable_Code_Point of another category (U+034F and U+FE0F are Mn); never in other letter cases.
    ("the label in a paragraph on another page", inject(f"<p>{LABEL}</p>"), LABEL_RULE),
    ("the label split across inline elements", inject("<p>About <em>this</em> project</p>"), LABEL_RULE),
    ("the label split by an element with an attribute", inject('<p>About <span class="a b">this</span> project</p>'),
        LABEL_RULE),
    ("the label split across lines", inject("<p>About\n  this project</p>"), LABEL_RULE),
    ("the label with a character reference", inject("<p>About th&#105;s project</p>"), LABEL_RULE),
    ("the label with a soft hyphen reference", inject("<p>About this pro&shy;ject</p>"), LABEL_RULE),
    ("the label with a soft hyphen", inject("<p>About this pro\u00adject</p>"), LABEL_RULE),
    ("the label with a zero-width joiner", inject("<p>About\u200d this project</p>"), LABEL_RULE),
    ("the label with U+0000", inject("<p>About this\u0000 project</p>"), LABEL_RULE),
    ("the label in upper case", inject("<p>ABOUT THIS PROJECT</p>"), LABEL_RULE),
    ("the label in a paragraph in home.html", after_value(f"<p>{LABEL}</p>"), LABEL_RULE),
    ("a label region without the about class in home.html",
        after_value(f'<div class="region"><p class="lbl">{LABEL}</p></div>'), LABEL_RULE),
    # The stylesheets show the text of a p.lbl and a th in upper case, so where an uppercase rule applies
    # (uppercase_here()), the label counts in any letter case; that includes an uppercase rule inside an element a
    # reset rule (such as .lbl.file) sets back to none.
    ("the label in mixed case in a p.lbl after the value region in home.html",
        after_value(f'<p class="lbl">{MIXED_LABEL}</p>'), LABEL_RULE),
    ("the label in mixed case in a p.lbl", inject(f'<p class="lbl">{MIXED_LABEL}</p>'), LABEL_RULE),
    ("the label in mixed case in a th", inject(LABEL_TH), LABEL_RULE),
    ("the label in mixed case split by a span inside a p.lbl",
        inject('<p class="lbl">About <span>This</span> Project</p>'), LABEL_RULE),
    ("the label in lower case in a link inside .chips",
        inject('<p class="chips"><a href="{{base}}install/">about this project</a></p>'), LABEL_RULE),
    ("the label in mixed case in a span.tag inside a p.lbl.file",
        inject(f'<p class="lbl file"><span class="tag">{MIXED_LABEL}</span></p>'), LABEL_RULE),
    # .note > .label and .lbl.file tie in specificity (2 classes each); a tie reads as upper case.
    ("the label in mixed case in a p.lbl.file.label inside a div.note",
        inject(f'<div class="note"><p class="lbl file label">{MIXED_LABEL}</p></div>'), LABEL_RULE),
    ("the label in mixed case in a span.lbl inside a table.matrix tbody th", inject(
        f'<table class="matrix"><caption>c</caption><tbody><tr><th><span class="lbl">{MIXED_LABEL}</span></th></tr>'
        "</tbody></table>"), LABEL_RULE),
    # The label counts when split by a hidden element, which a browser does not show, or by U+2800 between its words,
    # which a browser shows as a blank.
    ("the label in mixed case split by a hidden span inside a p.lbl after the value region in home.html",
        after_value('<p class="lbl">About <span hidden>x</span>This Project</p>'), LABEL_RULE),
    ("the label split by a hidden span in prose", inject("<p>About <span hidden>x</span>this project</p>"), LABEL_RULE),
    ("the label split by an aria-hidden span in prose",
        inject('<p>About <span aria-hidden="true">x</span>this project</p>'), LABEL_RULE),
    ("the label split by a noscript in prose", inject("<p>About <noscript>x</noscript>this project</p>"), LABEL_RULE),
    ("the label with U+2800 between its words", inject("<p>About&#x2800;this project</p>"), LABEL_RULE),
    # Hidden content, invisible characters or U+2800 can leave the value paragraph showing nothing, so the pin refuses
    # any element in it but an a with only href or an em with no attribute, and any character outside its list.
    ("the value paragraph's whole content in a hidden span", wrap_value_content("<span hidden>", "</span>"),
        VALUE_PIN_RULE),
    ("the value paragraph's whole content in an aria-hidden span",
        wrap_value_content('<span aria-hidden="true">', "</span>"), VALUE_PIN_RULE),
    ("the value paragraph's whole content in a span with the vh class",
        wrap_value_content('<span class="vh">', "</span>"), VALUE_PIN_RULE),
    ("the value paragraph holding only invisible characters", value_content(INVISIBLE), VALUE_PIN_RULE),
    ("an empty value paragraph", value_content(""), VALUE_PIN_RULE),
    ("the value paragraph holding only U+2800", value_content("&#x2800;"), VALUE_PIN_RULE),
    ("the value paragraph with U+2800 before a hidden span around its whole content",
        wrap_value_content("&#x2800;<span hidden>", "</span>"), VALUE_PIN_RULE),
    ("one word of the value paragraph outside a hidden span", wrap_value_content("Rules <span hidden>", "</span>"),
        VALUE_PIN_RULE),
    ("a class attribute on the value paragraph's link", lambda root: edit(
        root, HOME, '<a href="{{base}}license/">free', '<a href="{{base}}license/" class="x">free'), VALUE_PIN_RULE),
    ("a value paragraph of digits only", value_content("2026"), VALUE_PIN_RULE),
    # The pin admits an em with no attribute, whitespace a browser shows as a space, and currency and math symbols,
    # but no other element, no So outside VALUE_SIGNS (So holds U+2800), no Lo (which holds the Hangul fillers) and
    # no other whitespace.
    ("an em with a class in the value paragraph", value_content('Rules <em class="lbl">apply</em>'), VALUE_PIN_RULE),
    ("a strong in the value paragraph", value_content("Rules <strong>apply</strong>"), VALUE_PIN_RULE),
    ("a black star (So, outside VALUE_SIGNS) in the value paragraph", value_content("Rules &#x2605; 2026"),
        VALUE_PIN_RULE),
    ("2 CJK ideographs (Lo) in the value paragraph", value_content("Rules \u89c4\u5219"), VALUE_PIN_RULE),
    ("a value paragraph of only whitespace", value_content(" \n\t&nbsp; "), VALUE_PIN_RULE),
    ("U+000C in the value paragraph", value_content("Rules\x0capply"), VALUE_PIN_RULE),
    # The pin reads the text after NFC, which composes a letter and a combining mark that has a
    # precomposed form; a mark with none, and an invisible mark such as U+034F or a variation selector, stay refused.
    ("q and U+0301 in the value paragraph", value_content("Rules q\u0301"), VALUE_PIN_RULE),
    ("e and U+034F in the value paragraph", value_content("Cafe\u034f rules"), VALUE_PIN_RULE),
    ("e and U+FE0F in the value paragraph", value_content("Cafe\ufe0f rules"), VALUE_PIN_RULE),
    ("U+0301 alone in the value paragraph", value_content("Rules \u0301"), VALUE_PIN_RULE),
    # U+202E shows the text after it reversed, so a browser shows this p.lbl as the label in upper case, where the
    # label rule reads the text in its stored order. A page source carries no bidi formatting character, as written or
    # as a character reference, wherever it sits.
    ("the label reversed by U+202E in a p.lbl after the value region in home.html",
        after_value('<p class="lbl">&#x202E;tcejorp siht tuobA</p>'), BIDI_RULE),
    ("U+200F as &rlm; in prose", inject("<p>x&rlm;y</p>"), BIDI_RULE),
    ("U+2067 in an alt attribute value",
        inject('<p><img src="{{base}}assets/baseline/logos/cleanlanguage.svg" alt="x\u2067y"></p>'), BIDI_RULE),
] + [(f"U+{ord(character):04X} in prose", inject(f"<p>x{character}y</p>"), BIDI_RULE) for character in BIDI] + [
    # A stylesheet rule hides or moves an element by a class that a descendant or compound selector names
    # (.figure .stack and .scheme .sun set display: none, .copy and .btn position: absolute), which the rules do not
    # read. The value region carries only region, lbl and value; a page source only the class
    # names of SOURCE_CLASSES.
    ("the value paragraph inside a div.figure and a div.stack",
        wrap_value('<div class="figure"><div class="stack">', "</div></div>"), REGION_CLASS_RULE),
    ("the value paragraph with the copy class", lambda root: edit(root, HOME, VALUE, '<p class="value copy">'),
        REGION_CLASS_RULE),
    ("the value paragraph with the sun class inside a div.scheme", lambda root: (
        edit(root, HOME, VALUE, '<div class="scheme"><p class="value sun">'),
        edit(root, HOME, VALUE_END, VALUE_END.replace("</p>", "</p></div>", 1))), REGION_CLASS_RULE),
    ("the value paragraph inside a div with the vh-x class", wrap_value('<div class="vh-x">', "</div>"),
        REGION_CLASS_RULE),
    ("the btn class on the value region's label", lambda root: edit(
        root, HOME, '<p class="lbl">What it gives you', '<p class="lbl btn">What it gives you'), REGION_CLASS_RULE),
    ("the label in mixed case split by a span.sun in a p.lbl.scheme after the value region in home.html",
        after_value('<p class="lbl scheme">About <span class="sun">x</span>This Project</p>'), CLASS_PIN_RULE),
    ("the label split by a span.sun inside a div.scheme in prose",
        inject('<div class="scheme"><p>About <span class="sun">x</span>this project</p></div>'), CLASS_PIN_RULE),
    ("a class name of SOURCE_CLASSES in upper case", inject('<p class="LBL">x</p>'), CLASS_PIN_RULE),
    # .copy and .btn set position: absolute, so a browser shows the label that an element with either splits; and at
    # 1000 px and below the grid areas of .entries a show a span.t before a span.d written ahead of it. Each class
    # that places an element out of its source order is pinned to the element, companion classes, attributes and
    # parent the committed sources use it with (PLACED_CLASSES), and the children of each grid placed by area to their
    # committed order (PLACED_CHILDREN).
    ("the label in mixed case split by a span.btn in a p.lbl after the value region in home.html",
        after_value('<p class="lbl">About <span class="btn">x</span>This Project</p>'), PLACED_RULE),
    ("the label split by a span.copy in prose", inject('<p>About <span class="copy">x</span>this project</p>'),
        PLACED_RULE),
    ("an a.btn without inline", inject('<p><a class="btn" href="{{base}}install/">x</a></p>'), PLACED_RULE),
    ("a span.copy with hidden, first in a pre.hascopy",
        inject('<pre class="hascopy"><span class="copy" hidden>x</span>y</pre>'), PLACED_RULE),
    ("a button.copy without hidden, first in a pre.hascopy",
        inject('<pre class="hascopy"><button class="copy" type="button">x</button>y</pre>'), PLACED_RULE),
    ("a button.copy with hidden, after text in a pre.hascopy",
        inject('<pre class="hascopy">x<button class="copy" type="button" hidden>y</button></pre>'), PLACED_RULE),
    # The hiding reader reads a button.copy with hidden as hidden, so the label rule joins the text around it.
    ("the label split by a button.copy with hidden, first in a pre.hascopy", inject(
        '<p>About</p><pre class="hascopy"><button class="copy" type="button" hidden>x</button>this project</pre>'),
        LABEL_RULE),
    ("a button.copy with hidden, first in a pre without hascopy",
        inject('<pre><button class="copy" type="button" hidden>x</button>y</pre>'), PLACED_RULE),
    ("the entries class on a ul", inject(
        '<ul class="entries"><li><a href="{{base}}install/"><span class="t">x</span></a></li></ul>'), PLACED_RULE),
    ("a span.t in an li", inject('<ol class="entries"><li><span class="t">x</span></li></ol>'), PLACED_RULE),
    ("a span.n in a p", inject('<p><span class="n">x</span></p>'), PLACED_RULE),
    ("a span.d in a p", inject('<p><span class="d">x</span></p>'), PLACED_RULE),
    ("a section.hero inside the page's div.doc", inject('<section class="hero"></section>'), PLACED_RULE),
    ("a div.hero-text outside a section.hero", inject('<div class="hero-text"></div>'), PLACED_RULE),
    ("a div.hero-art outside a section.hero", inject('<div class="hero-art"></div>'), PLACED_RULE),
    ("a p.statement", inject('<p class="statement">x</p>'), PLACED_RULE),
    ("a p.intro outside the hero", inject('<p class="intro">x</p>'), PLACED_RULE),
    ("an a.start in a p", inject('<p><a class="start" href="{{base}}install/">x</a></p>'), PLACED_RULE),
    ("the label in an ol.entries link with its span.d before its span.t", inject(
        '<ol class="entries"><li><a href="{{base}}install/"><span class="d">project</span>'
        '<span class="t">About this</span></a></li></ol>'), ORDER_RULE),
    ("text directly in an ol.entries link", inject(
        '<ol class="entries"><li><a href="{{base}}install/">x<span class="t">y</span></a></li></ol>'), ORDER_RULE),
    ("an ol.entries link with 2 span.t", inject(
        '<ol class="entries"><li><a href="{{base}}install/"><span class="t">x</span><span class="t">y</span></a></li>'
        "</ol>"), ORDER_RULE),
    ("the hero's start link before its kicker in home.html", lambda root: edit(
        root, HOME, HERO_KICKER, '<a class="start" href="{{base}}install/">x</a>' + HERO_KICKER), ORDER_RULE),
    ("a p without a class in the hero text in home.html", lambda root: edit(
        root, HOME, HERO_KICKER, "<p>x</p>" + HERO_KICKER), ORDER_RULE),
    ("the hero's art before its text in home.html", lambda root: (
        edit(root, HOME, '<section class="hero" aria-label="Introduction">',
             '<section class="hero" aria-label="Introduction"><div class="hero-art"></div>'),
        edit(root, HOME, '<div class="hero-art"><img', '<div><img')), ORDER_RULE),
    ("the hero image's alt text changed in home.html", lambda root: edit(root, HOME, HERO_ALT, 'alt="this project"'),
        HERO_ALT_RULE),
    ("a rail written in a page source", inject('<div class="rail"><p>x</p></div>'), RAIL_RULE),
    ("a rail-logo written in a page source",
        inject('<p><img class="rail-logo" src="{{base}}assets/baseline/logos/cleanlanguage.svg" alt="x"></p>'),
        RAIL_RULE),
    ("a second <!--rail--> in a page source", inject("<!--rail-->"), RAILS_RULE),
    # A browser shows an img's alt text in its place when the image does not load, in upper case under .lbl; the label
    # rule reads it as text.
    ("the label as an img's alt text in a p.lbl after the value region in home.html",
        after_value('<p class="lbl"><img src="{{base}}instructions/" alt="About this project"></p>'), LABEL_RULE),
    ("the label in mixed case as an img's alt text in a p.lbl", inject(
        '<p class="lbl"><img src="{{base}}assets/baseline/logos/cleanlanguage.svg" alt="About This Project"></p>'),
        LABEL_RULE),
    ("the label split by an img's alt text in prose",
        inject('<p>About <img src="{{base}}assets/baseline/logos/cleanlanguage.svg" alt="this"> project</p>'),
        LABEL_RULE),
    # Latin small capitals and fullwidth Latin letters show as the label's letters; the label rule reads text after
    # NFKD, with each Latin small capital as its capital letter.
    ("the label in Latin small capitals", inject(
        "<p>\u1d00\u0299\u1d0f\u1d1c\u1d1b \u1d1b\u029c\u026a\ua731 \u1d18\u0280\u1d0f\u1d0a\u1d07\u1d04\u1d1b</p>"),
        LABEL_RULE),
    ("the label in fullwidth Latin letters", inject(
        "<p>\uff21\uff42\uff4f\uff55\uff54 \uff54\uff48\uff49\uff53 \uff50\uff52\uff4f\uff4a\uff45\uff43\uff54</p>"),
        LABEL_RULE),
    ("the label in mixed case in fullwidth Latin letters in a p.lbl after the value region in home.html",
        after_value('<p class="lbl">\uff21bout \uff34his \uff30roject</p>'), LABEL_RULE),
    # Above 1000 px .region shows its first child in its label column, so with the value region's label removed,
    # moved, repeated or hidden, or its div closed before the p.value, a browser shows the value paragraph there. The
    # region holds exactly its committed children.
    ("the value region without its label", lambda root: edit(root, HOME, REGION_LABEL, ""), REGION_CHILDREN_RULE),
    ("the value region's label after its div", lambda root: (
        edit(root, HOME, REGION_LABEL, ""),
        edit(root, HOME, VALUE_END, VALUE_END.replace("</div></div>", "</div>" + REGION_LABEL + "</div>"))),
        REGION_CHILDREN_RULE),
    ("the value region's label twice", lambda root: edit(root, HOME, REGION_LABEL, REGION_LABEL * 2),
        REGION_CHILDREN_RULE),
    ("the value region's label hidden", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl" hidden>What it gives you</p>'), REGION_CHILDREN_RULE),
    ("the value region's div closed before the value paragraph", lambda root: (
        edit(root, HOME, "<div>" + VALUE, "<div></div>" + VALUE),
        edit(root, HOME, VALUE_END, VALUE_END.replace("</div></div>", "</div>"))), REGION_CHILDREN_RULE),
    ("an empty label in the value region", lambda root: edit(root, HOME, REGION_LABEL, '<p class="lbl"></p>'),
        REGION_CHILDREN_RULE),
    ("the value region's label text in a hidden span", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl"><span hidden>What it gives you</span></p>'), REGION_CHILDREN_RULE),
    ("text directly in the value region", lambda root: edit(root, HOME, VALUE_REGION, VALUE_REGION + "x"),
        REGION_CHILDREN_RULE),
    ("the value region's label as a p without the lbl class", lambda root: edit(
        root, HOME, REGION_LABEL, "<p>What it gives you</p>"), REGION_CHILDREN_RULE),
    ("a paragraph after the value region's div", lambda root: edit(
        root, HOME, VALUE_END, VALUE_END.replace("</div></div>", "</div><p>x</p></div>")), REGION_CHILDREN_RULE),
    # The vh class on the value region's label: the region's class pin refuses it first, since VALUE_REGION_CLASSES
    # leaves out vh, and the region's children pin, whose label slot admits only p.lbl, refuses it too.
    ("the vh class on the value region's label", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl vh">What it gives you</p>'), REGION_CLASS_RULE),
    # aria-hidden="true" hides an element from assistive technology only, so a browser shows this p.lbl as the label
    # in upper case; the text that shows keeps such an element.
    ("the label split by an aria-hidden span and a vh span in a p.lbl after the value region in home.html",
        after_value('<p class="lbl"><span aria-hidden="true">About this</span><span class="vh">Read more</span> '
                    "project</p>"), LABEL_RULE),
    # The label split by an img's alt text that only the text that shows leaves out: hidden, so a browser shows no alt
    # text; and with only aria-hidden="true", which assistive technology skips, as the second reading of it does.
    ("the label split by a hidden img's alt text and an aria-hidden span in prose", inject(
        '<p>About <img src="{{base}}assets/baseline/logos/cleanlanguage.svg" alt="x" hidden>'
        '<span aria-hidden="true">this</span> project</p>'), LABEL_RULE),
    ("the label split by an aria-hidden img's alt text in prose", inject(
        '<p>About <img src="{{base}}assets/baseline/logos/cleanlanguage.svg" alt="x" aria-hidden="true">this project'
        "</p>"), LABEL_RULE),
    # The grammar admits ASCII whitespace around an attribute's = and before an end tag's >;
    # the attribute list still reads each name.
    ("a title attribute with spaces around its =", inject('<p title = "x">y</p >'), ATTRIBUTE_RULE),
    # A browser drops only the line feed that is the next token after a pre start tag: a second one, or one after a
    # comment, is text before the button.copy.
    ("a button.copy with hidden after 2 line feeds in a pre.hascopy",
        inject('<pre class="hascopy">\n\n<button class="copy" type="button" hidden>Copy</button>text</pre>'),
        PLACED_RULE),
    ("a button.copy with hidden after a comment and a line feed in a pre.hascopy",
        inject('<pre class="hascopy"><!--x-->\n<button class="copy" type="button" hidden>Copy</button>text</pre>'),
        PLACED_RULE),
    # A browser keeps the ol open after a self-closing ol start tag, so the link stays in its ol.entries; the placement
    # pins read PageScan, which keeps it open too.
    ("the label in an ol.entries link after a self-closing ol start tag, its span.d before its span.t", inject(
        '<ol class="entries"/><li><a href="{{base}}install/"><span class="d">project</span>'
        '<span class="t">About this</span></a></li></ol>'), ORDER_RULE),
    # The region, lbl or value class away from its place in the value region, where .region lays out the value
    # paragraph as a grid.
    ("the value paragraph with the region class", lambda root: edit(root, HOME, VALUE, '<p class="value region">'),
        REGION_PLACE_RULE),
    ("the value paragraph with the region class and its content in an em", lambda root: (
        edit(root, HOME, VALUE, '<p class="value region"><em>'),
        edit(root, HOME, VALUE_END, VALUE_END.replace("</p>", "</em></p>", 1))), REGION_PLACE_RULE),
    ("the value paragraph with the lbl class", lambda root: edit(root, HOME, VALUE, '<p class="value lbl">'),
        REGION_PLACE_RULE),
    ("a span.lbl in the value region's label", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl"><span class="lbl">What it gives you</span></p>'), REGION_PLACE_RULE),
    ("a span.value in the value region's label", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl"><span class="value">What</span> it gives you</p>'),
        REGION_PLACE_RULE),
    # At 600 px and below the hero image sits beside the kicker, before the statement, so a label split between the
    # kicker and site.json's logo_alt shows as the label; the label rule also reads the hero in that order.
    ("the label split between the hero's kicker and logo_alt in home.html", lambda root: (
        edit(root, HOME, HERO_KICKER, '<p class="lbl gold">About this</p>'),
        edit(root, HOME, HERO_ALT, 'alt="PROJECT"'),
        edit(root, "site-src/site.json", f'"logo_alt": "{HERO_ALT[5:-1]}"', '"logo_alt": "PROJECT"')), LABEL_RULE),
    # With no kicker, at 600 px and below the hero image still sits before the statement, so the label rule reads the
    # image's alt text before the statement.
    ("the label split between logo_alt and the statement of a hero with no kicker in home.html", lambda root: (
        edit(root, HOME, HERO_KICKER + HERO_STATEMENT, '<h1 class="statement">project</h1>'),
        edit(root, HOME, HERO_ALT, 'alt="About this"'),
        edit(root, "site-src/site.json", f'"logo_alt": "{HERO_ALT[5:-1]}"', '"logo_alt": "About this"')), LABEL_RULE),
    # The value region's label as an img alone, whose alt text a browser shows only when it does not load; and an
    # img's alt text splitting the label, which a browser shows without it when the image loads. The region's label
    # holds text, and each alt text is read kept and left out.
    ("the value region's label as an img with its text as alt text", lambda root: edit(
        root, HOME, REGION_LABEL, f'<p class="lbl"><img src="{LOGO}" alt="What it gives you"></p>'),
        REGION_CHILDREN_RULE),
    ("the label split by an img's alt text in a p.lbl after the value region in home.html",
        after_value(f'<p class="lbl">About <img src="{LOGO}" alt="x">this project</p>'), LABEL_RULE),
    ("the label from 1 img's alt text, split by another's, in prose", inject(
        f'<p>About <img src="{LOGO}" alt="this"> <img src="{LOGO}" alt="x"> project</p>'), LABEL_RULE),
    # A browser shows a table's caption first and its thead before its tbody, so text in a caption or thead after a
    # tbody joins the body's text in another order than the source's.
    ("the label split between a caption after a tbody and that tbody", inject(
        "<table><tbody><tr><td>project</td></tr></tbody><caption>About this</caption></table>"), TABLE_ORDER_RULE),
    ("a thead after a tbody", inject(
        "<table><caption>c</caption><tbody><tr><td>project</td></tr></tbody><thead><tr><td>About this</td></tr></thead>"
        "</table>"), TABLE_ORDER_RULE),
    ("a caption after a thead", inject(
        "<table><thead><tr><th>h</th></tr></thead><caption>c</caption><tbody><tr><td>d</td></tr></tbody></table>"),
        TABLE_ORDER_RULE),
    ("2 captions in a table", inject("<table><caption>c</caption><caption>d</caption></table>"), TABLE_ORDER_RULE),
    ("2 theads in a table", inject(
        "<table><thead><tr><th>h</th></tr></thead><thead><tr><th>i</th></tr></thead></table>"), TABLE_ORDER_RULE),
    # A label inside a closed details, which shows once a reader opens it; the label rule reads a details both closed
    # and opened.
    ("the label split by a hidden span in a p.lbl in a closed details", inject(
        '<details><summary>x</summary><p class="lbl">About<span hidden>y</span>this project</p></details>'),
        LABEL_RULE),
    ("the label split by a hidden span directly in a closed details",
        inject("<details>About <span hidden>y</span>this project</details>"), LABEL_RULE),
    # A second hero, whose narrow-width order the label rule does not read: it reads that order for 1 hero only.
    ("a second hero in home.html", lambda root: edit(
        root, HOME, "</section>", '</section><section class="hero" aria-label="x"><div class="hero-text">'
        '<p class="lbl">About this</p><p class="intro">x</p></div><div class="hero-art">'
        f"<img src=\"{LOGO}\" {HERO_ALT}></div></section>"), HEROES_RULE),
    # A closed details shows its summary and not the rest, so the label reads across it. The label rule reads each
    # details both closed and opened.
    ("the label across a closed details whose body is a paragraph", inject(
        "<details><summary>About this</summary><p>More information</p></details><p>project</p>"), LABEL_RULE),
    ("the label across a closed details whose body is text", inject(
        "<details><summary>About this</summary>More information</details><p>project</p>"), LABEL_RULE),
    # The label shows with an opened details around a closed one.
    ("the label across a closed details inside an opened one", inject(
        "<details><summary>x</summary><p>About this</p><details><summary></summary><p>z</p></details></details>"
        "<p>project</p>"), LABEL_RULE),
    # The value region's label as folded text alone, which shows only once a reader opens the details.
    ("the value region's label folded in a closed details in a button", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl"><button type="button"><details><summary></summary>'
        "<p>What it gives you</p></details></button></p>"), REGION_CHILDREN_RULE),
    # Find-in-page shows the content of hidden=until-found.
    ("the label split by a hidden span in a p with hidden=until-found",
        inject('<p hidden="until-found">About <span hidden>y</span>this project</p>'), UNTIL_FOUND_RULE),
    ("hidden=Until-Found in mixed case", inject('<p hidden="Until-Found">x</p>'), UNTIL_FOUND_RULE),
    ("hidden=until-found with a character reference", inject('<p hidden="until&#45;found">x</p>'), UNTIL_FOUND_RULE),
    # A browser shows a details' summary first, so this shows the label.
    ("the label from a summary after text in its details",
        inject("<details>this project<summary>About</summary></details>"), SUMMARY_ORDER_RULE),
    ("a summary after text in a details",
        inject("<details>x <summary>y</summary><p>z</p></details>"), SUMMARY_ORDER_RULE),
    # Each choice of the alt text carries 1 label, and the count is 1.
    ("the label with and without an alt text that carries it in upper case",
        inject(f'<p>About this<img src="{LOGO}" alt="ABOUT THIS PROJECT">project</p>'), LABEL_RULE),
    # Characters of No outside VALUE_SIGNS are refused.
    ("a fraction numerator one (U+215F, No) in the value paragraph", value_content("Rules &#x215F;3"),
        VALUE_PIN_RULE),
    ("a subscript two (U+2082, No) in the value paragraph", value_content("Rules H&#x2082;O"), VALUE_PIN_RULE),
    # copy.js shows every button with data-copy, whatever its classes, and replaces its content with plain text on a
    # copy, so data-copy sits only on the copy button.
    ("a hidden unclassed button with data-copy holding the label split by a hidden span", after_value(
        '<button type="button" data-copy="what-it-fixes" hidden>About <span hidden>x</span>this project</button>'),
        DATA_COPY_RULE),
    ("the value paragraph in an unclassed button with data-copy",
        wrap_value('<button type="button" data-copy="what-it-fixes">', "</button>"), DATA_COPY_RULE),
    ("data-copy on a span", inject('<p><span data-copy="x">y</span></p>'), DATA_COPY_RULE),
    ("a button.copy whose data-copy names another pre", inject(
        '<pre id="c1" class="hascopy"><button class="copy" type="button" data-copy="c2" hidden>Copy</button>x</pre>'
        '<pre id="c2">y</pre>'), DATA_COPY_RULE),
    ("a button.copy with data-copy holding other text", inject(
        '<pre id="c1" class="hascopy"><button class="copy" type="button" data-copy="c1" hidden>Copy it</button>'
        "x</pre>"), DATA_COPY_RULE),
    ("a button.copy with data-copy holding an element", inject(
        '<pre id="c1" class="hascopy"><button class="copy" type="button" data-copy="c1" hidden><span>Copy</span>'
        "</button>x</pre>"), DATA_COPY_RULE),
    # Each meets every condition of the data-copy pin but 1 (a button.copy; no child element), so a pin without that
    # condition admits it.
    ("an unclassed hidden button with data-copy holding Copy first in its pre.hascopy", inject(
        '<pre id="c1" class="hascopy"><button type="button" data-copy="c1" hidden>Copy</button>x</pre>'),
        DATA_COPY_RULE),
    ("a button.copy with data-copy holding Copy and a hidden span", inject(
        '<pre id="c1" class="hascopy"><button class="copy" type="button" data-copy="c1" hidden>Copy<span hidden>x'
        "</span></button>x</pre>"), DATA_COPY_RULE),
    # A browser with scripting off shows a noscript's content, so the label rule also reads the text that shows with
    # scripting off, hiding inside the noscript applying.
    ("the label split by a hidden span in a noscript paragraph",
        inject("<noscript><p>About <span hidden>x</span>this project</p></noscript>"), LABEL_RULE),
    ("the label split by a hidden span in a noscript p.lbl",
        inject('<noscript><p class="lbl">About <span hidden>x</span>this project</p></noscript>'), LABEL_RULE),
    ("the label across a hidden span and a noscript paragraph",
        inject("<p>About <span hidden>x</span></p><noscript><p>this project</p></noscript>"), LABEL_RULE),
    # An accepted residual: open stays outside SOURCE_ATTRIBUTES, since the rules read a details with open as opened
    # only, where a reader can close it.
    ("an ordinary open details outside the value region",
        inject("<details open><summary>Help</summary><p>More information</p></details>"), ATTRIBUTE_RULE),
] + [(f"the label with U+{ord(character):04X}", inject(f"<p>About th{character}is project</p>"), LABEL_RULE)
     for character in LABEL_IGNORED] + [
    # A page source carries no dialog (SOURCE_ELEMENTS) and no inert or popover (SOURCE_ATTRIBUTES);
    # check_about_block() holds validate() to each such wrapper.
    (f"the value paragraph inside {name}", wrap_value(start, end), wrapper_rule(start))
    for name, start, end in HIDING_WRAPPERS
]


# Page sources that build: inside the grammar, a comment or an attribute value names math or carries the About
# block's label, a noscript holds a plain paragraph, prose in lower or mixed case names the project, the label in
# mixed case sits where a reset rule sets text-transform back to none, or the value paragraph holds 1 word or its link.
SOURCE_PASSES = [
    ("a comment that names math", inject("<!-- a math element, with a single - between words -->")),
    ("an attribute value that names <math> by character references",
        inject('<p aria-label="a &lt;math&gt; element">x</p>')),
    ("a single quote in a double-quoted attribute value", inject("<p aria-label=\"the project's aim\">x</p>")),
    ("a noscript around a plain paragraph", inject("<noscript><p>x</p></noscript>")),
    ("a noscript after a noscript", inject("<noscript><p>x</p></noscript><noscript><p>y</p></noscript>")),
    # Inside the page source tree rules: a div in a button in a p, a list in an li, and a table whose parts hold only
    # their own children, with whitespace between them. SOURCE_REFUSALS refuses text before a details' first summary.
    ("a div inside a button inside a p", inject('<p><button type="button"><div>x</div></button></p>')),
    ("a list inside an li", inject("<ul><li>x<ul><li>y</li></ul></li></ul>")),
    ("a table with a caption, a thead and a tbody", inject(
        "<table>\n<caption>c</caption>\n<thead><tr><th>h</th></tr></thead>\n<tbody><tr><td>d</td></tr></tbody>\n"
        "</table>")),
    ("lower-case prose about this project", inject("<p>Send questions about this project to the maintainer.</p>")),
    ("mixed-case prose about this project", inject(f"<p>Send questions {MIXED_LABEL} to the maintainer.</p>")),
    ("the label in mixed case in a link outside .chips and .picker",
        inject(f'<p><a href="{{{{base}}}}install/">{MIXED_LABEL}</a></p>')),
    # A reset rule of higher specificity sets text-transform back to none, so the label in mixed case does not count.
    # A page source carries no matrix, org, reg-cap or count class (SOURCE_CLASSES), so the other 3
    # reset rules are checked through validate() and the helper (check_about_block(), RESET_PASSES).
    ("the label in mixed case in a p.lbl.file", inject(f'<p class="lbl file">{MIXED_LABEL}</p>')),
    ("a value paragraph of 1 word", value_content("Rules")),
    ("a value paragraph of only its link", value_content('<a href="{{base}}license/">Licence</a>')),
    # A line break and a tab, which a browser collapses to a space, a no-break space, currency and math
    # symbols, and an em with no attribute.
    ("a value paragraph with a line break and a tab", value_content("Rules\n\tapply")),
    ("a value paragraph with a no-break space", value_content("Rules&nbsp;apply")),
    ("a value paragraph with $ and +", value_content("Rules cost $0 + 0")),
    ("a value paragraph with an em", value_content("Rules <em>apply</em>")),
    ("the label in mixed case as an img's alt text in prose",
        inject('<p><img src="{{base}}assets/baseline/logos/cleanlanguage.svg" alt="About This Project"></p>')),
    ("the label in a comment", inject(f"<!-- {LABEL} -->")),
    ("the label in an attribute value", inject(f'<p aria-label="{LABEL}">x</p>')),
    ("an attribute of SOURCE_ATTRIBUTES in upper case", inject('<p CLASS="lead" ARIA-LABEL="x">y</p>')),
    ("the label in a comment in home.html", after_value(f"<!-- {LABEL} -->")),
    # Each class of PLACED_CLASSES where the committed sources use it, and a value paragraph with a
    # combining accent after a letter that NFC composes (e and U+0301 read as U+00E9), as a precomposed letter does.
    ("an a.btn.inline in a p", inject('<p><a class="btn inline" href="{{base}}install/">Install</a></p>')),
    ("a button.copy with hidden, first in a pre.hascopy",
        inject('<pre class="hascopy"><button class="copy" type="button" hidden>Copy</button>text</pre>')),
    ("an ol.entries link with its spans in order", inject(
        '<ol class="entries"><li><a href="{{base}}install/"><span class="t">Install</span><span class="n">5</span>'
        '<span class="d">Steps.</span></a></li></ol>')),
    ("an ol.entries link with a span.t and a span.d only", inject(
        '<ol class="entries"><li><a href="{{base}}install/"> <span class="t">Install</span> <span class="d">Steps.'
        "</span></a></li></ol>")),
    ("a span.n in an li", inject('<ol class="clauses"><li><span class="n">1</span><p>x</p></li></ol>')),
    ("a value paragraph with e and U+0301", value_content("Cafe\u0301 rules")),
    ("a value paragraph with U+00E9", value_content("Caf\u00e9 rules")),
    # ASCII whitespace around an attribute's = and before an end tag's >, which a browser and the parser read alike,
    # with the attribute list reading each name and not the value's words; a line feed directly after a pre start tag,
    # which a browser drops; and an aria-hidden label in the value region, which a browser shows.
    ("the value paragraph's start tag with spaces around its = and its end tag with a space", lambda root: (
        edit(root, HOME, VALUE, '<p class = "value">'),
        edit(root, HOME, VALUE_END, VALUE_END.replace("</p>", "</p >", 1)))),
    ("spaces and line breaks around attributes' = and before an end tag's >",
        inject('<p aria-label = "a title" class=\n"lead">x</p\n>')),
    ("a button.copy with hidden after a line feed, first in a pre.hascopy",
        inject('<pre class="hascopy">\n<button class="copy" type="button" hidden>Copy</button>text</pre>')),
    ("an aria-hidden label in the value region", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl" aria-hidden="true">What it gives you</p>')),
    # The About block goes where the value region's end tag ends as the parser reads it, with ASCII whitespace before
    # its >, which the grammar admits; validate() reads it there too.
    ("the value region's end tag with a space before its >",
        lambda root: edit(root, HOME, VALUE_END, VALUE_END[:-1] + " >")),
    ("the value region's end tag with a line feed before its >",
        lambda root: edit(root, HOME, VALUE_END, VALUE_END[:-1] + "\n>")),
    # That end tag in upper case, which the grammar admits (check_about_block() holds the
    # test's About helper to it).
    ("the value region's end tag in upper case",
        lambda root: edit(root, HOME, VALUE_END, VALUE_END[:-6] + "</DIV>")),
    # With no kicker, the label rule places the hero image's alt text where the hero's text starts, before the
    # statement, as the grid does at 600 px and below.
    ("a hero with no kicker", lambda root: edit(root, HOME, HERO_KICKER, "")),
    ("a hero with no kicker, its statement About this and logo_alt project", lambda root: (
        edit(root, HOME, HERO_KICKER + HERO_STATEMENT, '<h1 class="statement">About this</h1>'),
        edit(root, HOME, HERO_ALT, 'alt="project"'),
        edit(root, "site-src/site.json", f'"logo_alt": "{HERO_ALT[5:-1]}"', '"logo_alt": "project"'))),
    # Each sign of VALUE_SIGNS in the value paragraph, as written and as a character reference; and, inside the table
    # order and region children pins, a table with 2 tbody elements after its caption and thead, and an img beside
    # the text of the value region's label.
    ("a value paragraph with the signs of VALUE_SIGNS", value_content(f"Rules{VALUE_SIGNS} 2026")),
    ("a value paragraph with the signs of VALUE_SIGNS as character references",
        value_content("Rules&trade; &copy; &reg; 20&deg;, &frac14; &frac12; &frac34;")),
    ("a table with a caption, a thead and 2 tbody elements", inject(
        "<table><caption>c</caption><thead><tr><th>h</th></tr></thead><tbody><tr><td>d</td></tr></tbody>"
        "<tbody><tr><td>e</td></tr></tbody></table>")),
    ("an img beside the text of the value region's label", lambda root: edit(
        root, HOME, REGION_LABEL, f'<p class="lbl"><img src="{LOGO}" alt="x">What it gives you</p>')),
    # The service mark, the superscript digits and further vulgar fractions of VALUE_SIGNS, as character references;
    # and, inside the summary order and region children rules, whitespace in a details before its summary and the
    # value region's label beside a closed details.
    ("a value paragraph with the added signs of VALUE_SIGNS as character references",
        value_content("Rules&#x2120; x&sup2; y&sup1; &#x2070; &frac13; &frac23; &frac18; &#x2189;")),
    ("whitespace in a details before its summary", inject("<details>\n <summary>x</summary>y</details>")),
    ("the value region's label beside a closed details", lambda root: edit(
        root, HOME, REGION_LABEL, '<p class="lbl">What it gives you<button type="button"><details><summary>'
        "</summary><p>x</p></details></button></p>")),
    # The copy button as the committed sources write it, its data-copy naming its pre.
    ("a button.copy with data-copy naming its pre.hascopy", inject(
        '<pre id="c1" class="hascopy"><button class="copy" type="button" data-copy="c1" hidden>Copy</button>x</pre>')),
]


# The label in mixed case where a reset rule of higher specificity than every uppercase rule that matches sets
# text-transform back to none, with classes that SOURCE_CLASSES leaves out of page sources: validate() and the helper
# pass each after the landing page's About block (check_about_block()).
RESET_PASSES = [
    ("the label in mixed case in a table.matrix tbody th after the block",
        f'<table class="matrix"><caption>c</caption><tbody><tr><th>{MIXED_LABEL}</th></tr></tbody></table>'),
    ("the label in mixed case in a span.org inside a table.matrix th after the block",
        f'<table class="matrix"><caption>c</caption><thead><tr><th>x <span class="org">{MIXED_LABEL}</span></th></tr>'
        "</thead></table>"),
    ("the label in mixed case in a span.count inside a p.reg-cap after the block",
        f'<p class="reg-cap">x <span class="count">{MIXED_LABEL}</span></p>'),
]


def check_rail_reader(failures: list[str]) -> int:
    """The rail reads each h2 with an id as the generator's parser does, not as a regex that needs exactly id=" and
    </h2>, which would drop an entry or run one into the prose: with spaces around an h2's =, a space before its end
    tag's >, or its id attribute in upper case after a class, the demo page builds with the rail that its committed
    source gives."""
    cases = [
        ("spaces around an h2's =", '<h2 id="try">', '<h2 id = "try">'),
        ("a space before an h2's end tag's >", "Watch it work</h2>", "Watch it work</h2 >"),
        ("an h2's id attribute in upper case after a class", '<h2 id="default">', '<h2 class="sec" ID="default">'),
    ]
    rails = []
    for name, old, new in [("the committed demo page", "", "")] + cases:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if old:
                edit(root, PAGE, old, new)
            result = run(root, "--out", str(Path(scratch) / "out"))
            built = Path(scratch) / "out" / "demo" / "index.html"
            rail = re.search(r'<nav class="rail".*?</nav>', built.read_text(encoding="utf-8")) if built.is_file() else None
            rails.append(rail.group(0) if rail else None)
            if result.returncode != 0 or rail is None or (old and rails[-1] != rails[0]):
                failures.append(f"rail reader '{name}': exit {result.returncode}, expected 0 with the committed rail "
                                f"({result.stderr.strip()[:200] or (rails[-1] or 'no rail')[-200:]})")
    return len(cases)


def check_source_refusals(failures: list[str]) -> int:
    """Each source refusal fires by its own rule, whatever the output check would say."""
    for name, fault, rule in SOURCE_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            fault(root)
            result = run(root, "--out", str(Path(scratch) / "out"))
            if result.returncode != 1 or rule not in result.stderr:
                failures.append(f"source refusal '{name}': exit {result.returncode}, expected 1 with {rule!r} "
                                f"({result.stderr.strip()[:200]})")
    return len(SOURCE_REFUSALS)


def check_source_passes(failures: list[str]) -> int:
    """Each wrapper of SHOWING_WRAPPERS but the open dialog and the open details, which no page source may carry
    (SOURCE_ELEMENTS, SOURCE_ATTRIBUTES), and the div with the vh-x class, which the value region may not carry
    (VALUE_REGION_CLASSES), around the landing page source's value paragraph builds, and so does each case of
    SOURCE_PASSES."""
    cases = [(f"the value paragraph inside {name}", wrap_value(start, end)) for name, start, end in SHOWING_WRAPPERS
             if wrapper_rule(start) == VALUE_RULE and "class=" not in start]
    for name, fault in cases + SOURCE_PASSES:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            fault(root)
            result = run(root, "--out", str(Path(scratch) / "out"))
            if result.returncode != 0:
                failures.append(f"source pass '{name}': exit {result.returncode}, expected 0 "
                                f"({result.stderr.strip()[:200]})")
    return len(cases) + len(SOURCE_PASSES)


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
            "</head>", '<SCRIPT SRC="/assets/baseline/sch&#101;me.js?v=1.11.1" defer></SCRIPT></head>', 1), False),
        ("the scheme.js line inside a comment, loaded in another spelling", text.replace(tag, "<!--" + tag.rstrip("\n")
            + '--><script data-cfasync="false" src="/assets/baseline/sch&#101;me.js?v=1.11.1"></script>\n', 1), False),
        ("an upper-case stylesheet before the scheme.js line", text.replace(
            tag, '<LINK REL="stylesheet" HREF="/assets/baseline/fonts.css?v=1.11.1">\n' + tag, 1), False),
        ("a second scheme.js load as the first of 2 src attributes", text.replace("</head>", '<SCRIPT SRC='
            '"/assets/baseline/sch&#101;me.js?v=1.11.1" src="/assets/baseline/copy.js?v=1.11.1" defer></SCRIPT></head>', 1), False),
        ("a stylesheet before the scheme.js line as the first of 2 rel attributes", text.replace(
            tag, '<LINK REL="stylesheet" REL="icon" HREF="/assets/baseline/fonts.css?v=1.11.1">\n' + tag, 1), False),
        # The parsed reading allows it, but the header block must be byte for byte what mast() is meant to write.
        ("a newline between nav.nav and the switch", text.replace("</nav>" + SWITCH, "</nav>\n" + SWITCH, 1), False),
        ("a second element with data-scheme-toggle after header.mast", text.replace(
            SWITCH + "</header>", SWITCH + "</header>" + TOGGLE, 1), False),
        ("a second element with data-scheme-toggle in upper case", text.replace(
            SWITCH + "</header>", SWITCH + '</header><div DATA-SCHEME-TOGGLE hidden></div>', 1), False),
        ("a later stylesheet moved into the body", text.replace(later, "", 1).replace("<body>\n", "<body>\n" + later, 1), False),
        ("a later stylesheet in upper case at the end of the body", text.replace(
            "</body>", '<LINK REL="stylesheet" HREF="/assets/baseline/baseline.css?v=1.11.1">\n</body>', 1), False),
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
    files = {"home": "site/index.html", "license": "site/license/index.html", "404": "site/404.html"}
    texts = {page_id: (REPO_ROOT / path).read_text(encoding="utf-8") for page_id, path in files.items()}
    skip, status, robots = generator.SKIP_LINK, generator.COPY_STATUS, '<meta name="robots" content="noindex, nofollow">'
    h1 = re.search(r"<h1>[^<]*</h1>", texts["license"]).group(0)
    about = about_line("/")
    cases = [
        ("the committed home page", "home", None, None, True),
        ("the About row only inside noscript", "home", about, f"<noscript>{about}</noscript>", False),
        ("the About row only inside canvas", "home", about, f"<canvas>{about}</canvas>", False),
        ("the h1 only inside canvas", "license", h1, f"<canvas>{h1}</canvas>", False),
        ("the committed licence page", "license", None, None, True),
        ("the committed 404 page", "404", None, None, True),
        ("the skip link only inside noscript", "license", skip, f"<noscript>{skip}</noscript>", False),
        ("the skip link only inside a title", "license", skip, f"<title>{skip}</title>", False),
        ("#copy-status only inside noscript", "license", status, f"<noscript>{status}</noscript>", False),
        ("the robots meta only inside noscript in the head", "404", robots, f"<noscript>{robots}</noscript>", False),
    ]
    for name, page_id, old, new, passes in cases:
        page_html = texts[page_id] if old is None else texts[page_id].replace(old, new, 1)
        if old is not None and old not in texts[page_id]:
            failures.append(f"inert validation '{name}': {old!r} is not in {files[page_id]}")
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


def check_inner_about_rows(failures: list[str]) -> int:
    """About markup on an inner page, read as the parsed class names of every element (split on ASCII whitespace
    only), with an INERT ancestor or not: validate(), called directly on the committed licence page, refuses it by
    its rule, and so does the build test's helper; a class name that only starts with about passes both. Both also
    refuse the About block's label in the page's text, split across elements (one with an attribute value that holds
    >, which a reader that strips tags misreads, included), written with a character reference or in upper case,
    interrupted by a soft hyphen, a zero-width joiner or a character of LABEL_IGNORED (format characters and
    default-ignorable code points), or split by a hidden element inside a noscript, where only the readings with
    scripting off show it (the generator's scripting_off() and the helper's labels()), the generator by its own rule
    (row 144, for which the paragraph case here flipped from passing); in an attribute value (one that holds >
    included), a comment or lower-case prose, the label passes both. A page is not held to the page source grammar,
    so > in a value can reach this reading."""
    generator = load_module(GENERATOR)
    config = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))
    page = next(entry for entry in config["pages"] if entry["id"] == "license")
    text = (REPO_ROOT / "site/license/index.html").read_text(encoding="utf-8")
    h1 = re.search(r"<h1>[^<]*</h1>", text).group(0)
    link = '<a href="/install/">Install</a>'
    class_rule, label_rule = "About markup (an element whose classes include about", "the About block's label in"
    cases = [
        (f'<p class="about">{link}</p>', class_rule),
        (f"<p class=about>{link}</p>", class_rule),
        (f"<p class='about'>{link}</p>", class_rule),
        (f'<p class="about x">{link}</p>', class_rule),
        (f"<noscript><p class=about>{link}</p></noscript>", class_rule),
        (f'<p class="about-us">{link}</p>', None),
        (f'<p class="about&nbsp;x">{link}</p>', None),
        (f"<p>{LABEL}</p>", label_rule),
        ("<p>About <em>this</em> project</p>", label_rule),
        ('<p>About <span title="a>b">this</span> project</p>', label_rule),
        ("<p>About th&#105;s project</p>", label_rule),
        ("<p>About this pro&shy;ject</p>", label_rule),
        ("<p>About this pro\u00adject</p>", label_rule),
        ("<p>About\u200d this project</p>", label_rule),
        *[(f"<p>About th{character}is project</p>", label_rule) for character in LABEL_IGNORED],
        ("<p>ABOUT THIS PROJECT</p>", label_rule),
        (f'<div class="region"><p class="lbl">{LABEL}</p></div>', label_rule),
        ("<noscript><p>About <span hidden>x</span>this project</p></noscript>", label_rule),
        (f'<p title="{LABEL}">x</p>', None),
        (f'<p title="x>{LABEL}">y</p>', None),
        (f"<!-- {LABEL} -->", None),
        ("<p>Send questions about this project to the maintainer.</p>", None),
    ]
    for row, rule in cases:
        passes = rule is None
        page_html = text.replace(h1, h1 + row, 1)
        try:
            generator.validate(page_html, page, config, "/")
            refusal = ""
        except generator.BuildError as error:
            refusal = str(error)
        if passes and refusal:
            failures.append(f"inner About row {row!r}: refused, expected to pass ({refusal[:200]})")
        elif not passes and rule not in refusal:
            failures.append(f"inner About row {row!r}: not refused by its rule ({refusal[:200] or 'passed'})")
        if (not about_problems("license/index.html", page_html, "/")) != passes:
            failures.append(f"About helper, inner About row {row!r}: {'refused' if passes else 'passed'}, expected the opposite")
    return 2 * len(cases)


def check_label_count(failures: list[str]) -> int:
    """The generator's label_count(), called directly: it counts the labels of 1 choice of
    its optional groups together, each group read left out and shown, a group inside another shown only with it. The
    keys stand for where a details or an img starts."""
    details, inner, img = (1, 0), (2, 0), (3, 0)
    cases = [
        # Each choice of the alt text carries 1 label (in upper case kept, as written left out): 1, not 2.
        ("an alt text that carries the label between its halves", ["About this", "ABOUT THIS PROJECT", "project"],
            [(), (img,), ()], 1),
        ("the label with the alt text left out, and once more after it", ["About this", "x", "project",
            "ABOUT THIS PROJECT"], [(), (img,), (), ()], 2),
        ("the label across a closed details", ["About this", "More information", "project"], [(), (details,), ()], 1),
        ("the label in an opened details", ["x", "About this project"], [(), (details,)], 1),
        ("the label across a closed details in an opened one", ["About this", "z", "project"],
            [(details,), (details, inner), ()], 1),
        ("no label in either state", ["About this", "x", "y", "project"], [(), (), (details,), ()], 0),
    ]
    for name, parts, chains, count in cases:
        if LOADED.label_count(parts, chains) != count:
            failures.append(f"label_count '{name}': {LOADED.label_count(parts, chains)}, expected {count}")
    return len(cases)


def check_value_signs(failures: list[str]) -> int:
    """VALUE_SIGNS, the generator's and the test's copy alike, holds only visible signs of So and No that NFC leaves
    as they are, none whitespace or a Default_Ignorable_Code_Point."""
    if LOADED.VALUE_SIGNS != VALUE_SIGNS:
        failures.append("the generator's VALUE_SIGNS differs from the test's copy")
    for sign in VALUE_SIGNS:
        if (unicodedata.category(sign) not in ("So", "No") or unicodedata.normalize("NFC", sign) != sign
                or sign.isspace() or any(first <= ord(sign) <= last for first, last in LOADED.DEFAULT_IGNORABLE)):
            failures.append(f"VALUE_SIGNS holds U+{ord(sign):04X}, which is not a visible sign of So or No")
    return 1 + len(VALUE_SIGNS)


def check_about_block(failures: list[str]) -> int:
    """The whole About block of specification 7.24 on the landing page: validate(), called directly on the committed
    landing page with 1 fault each, refuses by the block's rule (exactly 1 p.value, with no INERT ancestor, not
    hidden by itself or by an ancestor as tools/check-install-page.py reads hiding; the block once, byte for byte,
    directly after the end tag of that paragraph's region; the region and the block each with exactly the ancestors
    html, body, main and div.wrap; no other element whose classes include about), by the
    label's rule (the page's text, an img's alt text among it, and its text that shows, carry the block's label once,
    inside the block, in any letter case where the stylesheets show text in upper case, read after NFKD and with
    Latin small capitals as capitals, with an element that only aria-hidden="true" hides read as shown in 1 of the
    readings of the text that shows, each also with scripting off, and in either hero order), by the value
    paragraph's pin (no element but an a with only href or an em
    with no attribute, no character outside its lists after NFC, at least 1 letter) or by its region's (a p.lbl
    with text that shows, then the div that holds the p.value, and no text), and the build test's helper
    judges each case as the generator should. The label in an attribute value, a comment, prose in lower or mixed
    case, or a p.lbl.file in mixed case passes both, and so do the cases of RESET_PASSES, each wrapper of
    SHOWING_WRAPPERS around the value paragraph, a value paragraph of 1 word, one with whitespace, symbols and an em
    that its pin admits, one with e and U+0301, and an aria-hidden label in the value region."""
    generator = load_module(GENERATOR)
    config = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))
    page = next(entry for entry in config["pages"] if entry["path"] == "")
    text = (REPO_ROOT / "site/index.html").read_text(encoding="utf-8")
    row, block, label = about_line("/"), about_block("/"), f'<p class="lbl">{LABEL}</p>'
    hero, value = '<div class="hero-text">', VALUE_REGION
    decoy = '<div class="region"><p class="value">x</p></div>'
    block_rule, label_rule = "the About block must appear exactly once", "the About block's label must appear"
    value_rule, region_rule = VALUE_PIN_RULE, REGION_PIN_RULE
    # The end of the value paragraph's text and its end tag, and its whole content up to that end tag.
    end, content = "outside its aim.</p>", text[text.index(VALUE) + len(VALUE):text.index("</p>", text.index(VALUE))]

    def end_in(close: str) -> str:
        return end.replace("</p>", close + "</p>", 1)
    cases = [
        ("the committed landing page", [], None),
        ("the row without its region and label", [(block, row)], block_rule),
        ("the block without its label", [(label, "")], block_rule),
        ("the row moved into the hero", [(block, block.replace(row, "", 1)), (hero, hero + row)], block_rule),
        ("the whole block moved into the hero", [(block, ""), (hero, hero + block)], block_rule),
        ("the block before the value paragraph's region", [(block, ""), (value, block + value)], block_rule),
        ("a line break before the block", [(block, "\n" + block)], block_rule),
        ("the exact row wrapped in a hidden div", [(row, f"<div hidden>{row}</div>")], block_rule),
        ("the value region and the block inside 1 hidden div", [(value, "<div hidden>" + value), (block, block + "</div>")],
            block_rule),
        ("the value region and the block inside 1 div with hidden=until-found",
            [(value, '<div hidden="until-found">' + value), (block, block + "</div>")], block_rule),
        ("the value region and the block inside noscript", [(value, "<noscript>" + value), (block, block + "</noscript>")],
            block_rule),
        ("the value paragraph with a hidden attribute", [('<p class="value">', '<p class="value" hidden>')], block_rule),
        ("the value paragraph with hidden=until-found", [('<p class="value">', '<p class="value" hidden="until-found">')],
            block_rule),
        ("a second exact row after the block", [(block, block + '<p class="about">x</p>')], block_rule),
        # A decoy p.value region authorized the boundary while any value paragraph's region could; now only the
        # page's one p.value may.
        ("the block moved after a decoy p.value region in the hero", [(block, ""), (hero, hero + decoy + block)],
            block_rule),
        ("a decoy p.value region directly before the block", [(block, decoy + block)], block_rule),
        ("a hidden decoy p.value region directly before the block",
            [(block, decoy.replace('"region"', '"region" hidden', 1) + block)], block_rule),
        ("a second p.value after the block", [(block, block + '<p class="value">x</p>')], block_rule),
        ("no p.value", [('<p class="value">', "<p>")], block_rule),
        ("the value paragraph's region without its class", [(value, '<div id="what-it-fixes">')], block_rule),
        # A browser's adoption agency moves the block out of an a around the value region and the block, and its
        # label into a new a; no element may wrap either, the a, a details or any other.
        ("an a around the value region and the block", [
            ('<a href="/license/">free to use under CC BY-SA 4.0</a>', "free to use under CC BY-SA 4.0"),
            (value, '<a href="/install/">' + value), (block, block + "</a>")], block_rule),
        ("an open details around the value region and the block",
            [(value, "<details open><summary>x</summary>" + value), (block, block + "</details>")], block_rule),
        ("a div around the value region and the block", [(value, "<div>" + value), (block, block + "</div>")],
            block_rule),
        # The page's text carries the block's label once, inside the block: a copy elsewhere is refused, and so is the
        # label moved out of the block, which only the condition that it come from inside the block refuses by the
        # label's rule.
        ("a second label region after the block", [(block, block + f'<div class="region">{label}</div>')], label_rule),
        ("a second label in a paragraph in the hero", [(hero, hero + f"<p>{LABEL}</p>")], label_rule),
        ("a second label in upper case after the block", [(block, block + f"<p>{LABEL.upper()}</p>")], label_rule),
        ("a second label split across inline elements after the block",
            [(block, block + "<p>About <em>this</em> project</p>")], label_rule),
        ("a second label split by an element whose attribute value holds >, after the block",
            [(block, block + '<p>About <span title="a>b">this</span> project</p>')], label_rule),
        ("a second label with a soft hyphen after the block", [(block, block + "<p>About this pro&shy;ject</p>")],
            label_rule),
        ("the block's label moved into the hero",
            [(label, '<p class="lbl"></p>'), (hero, hero + f"<p>{LABEL}</p>")], label_rule),
        ("a second label in an attribute", [(hero, hero + f'<p title="{LABEL}">x</p>')], None),
        ("a second label in an attribute value that holds >", [(hero, hero + f'<p title="x>{LABEL}">y</p>')], None),
        ("a second label in a comment", [(hero, hero + f"<!-- {LABEL} -->")], None),
        ("lower-case prose about this project",
            [(hero, hero + "<p>Send questions about this project to the maintainer.</p>")], None),
        # In an element that the stylesheets show in upper case, the label counts in any letter case; in prose, not.
        ("a second label in mixed case in a p.lbl after the block",
            [(block, block + f'<p class="lbl">{MIXED_LABEL}</p>')], label_rule),
        ("a second label in mixed case in a th after the block", [(block, block + LABEL_TH)], label_rule),
        ("mixed-case prose about this project",
            [(hero, hero + f"<p>Send questions {MIXED_LABEL} to the maintainer.</p>")], None),
        # A hidden element inside the label does not split it (the text that shows carries it), and where a reset
        # rule of higher specificity sets text-transform back to none, the label in mixed case does not count.
        ("a second label in mixed case split by a hidden span in a p.lbl after the block",
            [(block, block + '<p class="lbl">About <span hidden>x</span>This Project</p>')], label_rule),
        ("a second label in mixed case in a span.tag inside a p.lbl.file after the block",
            [(block, block + f'<p class="lbl file"><span class="tag">{MIXED_LABEL}</span></p>')], label_rule),
        ("the label in mixed case in a p.lbl.file after the block",
            [(block, block + f'<p class="lbl file">{MIXED_LABEL}</p>')], None),
        # The value paragraph holds no element but an a with only href, and no character outside its list. A details
        # in it is refused by the pin (and in a page source by the tree rules first), so whether a browser shows the
        # first summary of a closed one there no longer arises.
        ("the value paragraph's content in a hidden span", [(VALUE, VALUE + "<span hidden>"), (end, end_in("</span>"))],
            value_rule),
        ("the value paragraph's content in an aria-hidden span",
            [(VALUE, VALUE + '<span aria-hidden="true">'), (end, end_in("</span>"))], value_rule),
        ("the value paragraph's content in noscript", [(VALUE, VALUE + "<noscript>"), (end, end_in("</noscript>"))],
            value_rule),
        ("the value paragraph's content in a details without open, after its summary",
            [(VALUE, VALUE + "<details><summary></summary>"), (end, end_in("</details>"))], value_rule),
        ("the value paragraph's content directly in a details without open",
            [(VALUE, VALUE + "<details>"), (end, end_in("</details>"))], value_rule),
        ("the value paragraph's content in the first summary of a details without open",
            [(VALUE, VALUE + "<details><summary>"), (end, end_in("</summary></details>"))], value_rule),
        ("the value paragraph holding only invisible characters", [(VALUE + content, VALUE + INVISIBLE)], value_rule),
        ("the value paragraph holding only U+2800", [(VALUE + content, VALUE + "&#x2800;")], value_rule),
        ("one word of the value paragraph outside a hidden span",
            [(VALUE, VALUE + "Rules <span hidden>"), (end, end_in("</span>"))], value_rule),
        ("a value paragraph of 1 word", [(VALUE + content, VALUE + "Rules")], None),
        # Whitespace a browser shows as a space, currency and math symbols and an em with no attribute
        # pass; an em with an attribute and So outside VALUE_SIGNS do not. An img's alt text, Latin small capitals
        # and fullwidth Latin letters carry the label.
        ("a value paragraph with whitespace, symbols and an em",
            [(VALUE + content, VALUE + "Rules\r\n\tcost&nbsp;$1 + <em>tax</em>")], None),
        ("an em with a class in the value paragraph", [(VALUE + content, VALUE + 'Rules <em class="x">tax</em>')],
            value_rule),
        ("a black star in the value paragraph", [(VALUE + content, VALUE + "Rules &#x2605; 2026")], value_rule),
        # The signs of VALUE_SIGNS pass; an img alone is no label text in the value region; an img's alt text is read
        # kept and left out; and a closed details is read both closed and opened for the label.
        ("the signs of VALUE_SIGNS in the value paragraph",
            [(VALUE + content, VALUE + "Rules &copy; &reg; &trade; 20&deg; &frac14; &frac12; &frac34;")], None),
        ("the value region's label as an img with its text as alt text",
            [(REGION_LABEL, '<p class="lbl"><img src="/assets/baseline/logos/cleanlanguage.svg" '
                            'alt="What it gives you"></p>')], region_rule),
        ("a second label split by an img's alt text in a p.lbl after the block",
            [(block, block + '<p class="lbl">About <img src="/instructions/" alt="x">this project</p>')], label_rule),
        ("a second label split by a hidden span in a p.lbl in a closed details after the block",
            [(block, block + '<details><summary>x</summary><p class="lbl">About<span hidden>y</span>this project</p>'
                             "</details>")], label_rule),
        # A closed details is read closed and opened for the label, its folded content is no
        # text that shows of the value region's label, and the added signs of VALUE_SIGNS pass.
        ("a second label across a closed details after the block",
            [(block, block + "<details><summary>About this</summary><p>More information</p></details><p>project</p>")],
            label_rule),
        ("the value region's label folded in a closed details in a button",
            [(REGION_LABEL, '<p class="lbl"><button type="button"><details><summary></summary><p>What it gives you</p>'
                            "</details></button></p>")], region_rule),
        ("the added signs of VALUE_SIGNS in the value paragraph",
            [(VALUE + content, VALUE + "Rules&#x2120; x&sup2; &frac13; &frac23; &#x2189;")], None),
        # The pin reads the text after NFC: e and U+0301 pass; e and U+034F do not.
        ("a value paragraph with e and U+0301", [(VALUE + content, VALUE + "Cafe\u0301 rules")], None),
        ("a value paragraph with e and U+034F", [(VALUE + content, VALUE + "Cafe\u034f rules")], value_rule),
        ("a second label as an img's alt text in a p.lbl after the block",
            [(block, block + '<p class="lbl"><img src="/instructions/" alt="About This Project"></p>')], label_rule),
        ("a second label in Latin small capitals after the block",
            [(block, block + "<p>\u1d00\u0299\u1d0f\u1d1c\u1d1b \u1d1b\u029c\u026a\ua731 \u1d18\u0280\u1d0f\u1d0a\u1d07"
                              "\u1d04\u1d1b</p>")], label_rule),
        ("a second label in fullwidth Latin letters after the block",
            [(block, block + "<p>\uff21bout this \uff50roject</p>")], label_rule),
        # The value region holds exactly a p.lbl with text that shows, then the div that
        # holds the p.value, and no text; aria-hidden="true" alone hides nothing that a browser shows.
        ("the value region without its label", [(REGION_LABEL, "")], region_rule),
        ("the value region's label after its div", [(REGION_LABEL, ""), (VALUE_END, VALUE_END.replace(
            "</div></div>", "</div>" + REGION_LABEL + "</div>"))], region_rule),
        ("the value region's label twice", [(REGION_LABEL, REGION_LABEL * 2)], region_rule),
        ("the value region's label hidden", [(REGION_LABEL, '<p class="lbl" hidden>What it gives you</p>')],
            region_rule),
        ("the value region's label text in a span with the vh class",
            [(REGION_LABEL, '<p class="lbl"><span class="vh">What it gives you</span></p>')], region_rule),
        ("an empty label in the value region", [(REGION_LABEL, '<p class="lbl"></p>')], region_rule),
        ("the value region's div closed before the value paragraph",
            [("<div>" + VALUE, "<div></div>" + VALUE), (VALUE_END, VALUE_END.replace("</div></div>", "</div>"))],
            region_rule),
        ("text directly in the value region", [(value, value + "x")], region_rule),
        ("the value region's label as a p without the lbl class", [(REGION_LABEL, "<p>What it gives you</p>")],
            region_rule),
        ("a paragraph after the value region's div",
            [(VALUE_END, VALUE_END.replace("</div></div>", "</div><p>x</p></div>"))], region_rule),
        # A page source cannot carry this (a browser ends the p.lbl at the p.value's start tag), but validate() reads
        # a built page as the parser nests it.
        ("the value paragraph inside the value region's label", [
            ("What it gives you</p><div>" + VALUE, "What it gives you" + VALUE),
            (VALUE_END, VALUE_END.replace("</p></div></div>", "</p></p><div></div></div>"))], region_rule),
        ("an aria-hidden label in the value region",
            [(REGION_LABEL, '<p class="lbl" aria-hidden="true">What it gives you</p>')], None),
        # The block starts where the region's end tag ends as the parser reads that tag,
        # which may hold ASCII whitespace before its >.
        ("the value region's end tag with a space before its >", [("</div>" + block, "</div >" + block)], None),
        ("the value region's end tag with a line feed before its >", [("</div>" + block, "</div\n>" + block)], None),
        # The helper reads that end tag's name in any ASCII letter case, as the grammar does.
        ("the value region's end tag in upper case", [("</div>" + block, "</DIV>" + block)], None),
        ("a second label split by an aria-hidden span and a vh span in a p.lbl after the block",
            [(block, block + '<p class="lbl"><span aria-hidden="true">About this</span><span class="vh">Read more'
                              "</span> project</p>")], label_rule),
        ("a second label split by an aria-hidden img's alt text after the block",
            [(block, block + '<p>About <img src="/instructions/" alt="x" aria-hidden="true">this project</p>')],
            label_rule),
        # The helper reads the hero's narrow-width order, as the generator does, and both read the text that shows
        # with scripting off.
        ("a second label from the hero kicker About this and its image's alt text PROJECT",
            [(HERO_KICKER, '<p class="lbl gold">About this</p>'), (HERO_ALT, 'alt="PROJECT"')], label_rule),
        ("a second label split by a hidden span in a noscript paragraph after the block",
            [(block, block + "<noscript><p>About <span hidden>x</span>this project</p></noscript>")], label_rule),
    ] + [(name, [(block, block + snippet)], None) for name, snippet in RESET_PASSES] + [
        (f"the value paragraph inside {name}",
         [(VALUE, start + VALUE), (VALUE_END, VALUE_END.replace("</p>", "</p>" + end, 1))], rule)
        for wrappers, rule in ((HIDING_WRAPPERS, block_rule), (SHOWING_WRAPPERS, None)) for name, start, end in wrappers
    ]
    for name, edits, rule in cases:
        page_html = text
        for old, new in edits:
            if page_html.count(old) != 1:
                failures.append(f"About block '{name}': {old[:60]!r} is not once in site/index.html")
            page_html = page_html.replace(old, new, 1)
        try:
            generator.validate(page_html, page, config, "/")
            refusal = ""
        except generator.BuildError as error:
            refusal = str(error)
        if rule is None and refusal:
            failures.append(f"About block '{name}': refused, expected to pass ({refusal[:200]})")
        elif rule is not None and rule not in refusal:
            failures.append(f"About block '{name}': not refused by its rule ({refusal[:200] or 'passed'})")
        if (not about_problems("index.html", page_html, "/")) != (rule is None):
            failures.append(f"About helper, block '{name}': {'refused' if rule is None else 'passed'}, expected the opposite")
    return 2 * len(cases)


def check_uppercase_selectors(failures: list[str]) -> int:
    """The generator's UPPERCASE_SELECTORS and RESET_SELECTORS name exactly the selectors of the text-transform:
    uppercase and text-transform: none rules of the stylesheets every page loads, read here from those stylesheets,
    each a selector that selector_matches() reads; uppercase_coverage() refuses either list without any 1 of its
    selectors or with 1 that no such rule names, the stylesheets with 1 more such rule, at the top level or inside
    @media, and each text-transform that transform_rules() does not read, a property name with an escape (such as
    text\\2d transform) among them, and each small-capitals value of CAPS_PROPERTIES, or one it cannot read, so a
    coverage check that passes an incomplete or stale list, or a stylesheet it cannot read, fails here. Every
    Default_Ignorable_Code_Point falls outside the generator's VALUE_CATEGORIES."""
    listed, resets = list(LOADED.UPPERCASE_SELECTORS), list(LOADED.RESET_SELECTORS)
    sheets = [path.read_text(encoding="utf-8") for path in STYLESHEETS]
    unread = "which the generator does not read"
    # (name, the 2 lists, the stylesheet texts, the text of the problem expected, or None for none).
    cases = [("the generator's lists and the stylesheets", listed, resets, sheets, None)] + [
        (f"the list without {selector!r}", [other for other in listed if other != selector], resets, sheets,
            f"names {selector!r}, which UPPERCASE_SELECTORS lacks") for selector in listed] + [
        (f"the reset list without {selector!r}", listed, [other for other in resets if other != selector], sheets,
            f"names {selector!r}, which RESET_SELECTORS lacks") for selector in resets] + [
        ("1 more rule", listed, resets, sheets + [".added  >  b, .lbl { color: red; TEXT-TRANSFORM: UPPERCASE; }"],
            "names '.added > b', which UPPERCASE_SELECTORS lacks"),
        ("1 more rule inside @media", listed, resets,
            sheets + ["@media print { /* x */ .added { text-transform: uppercase } }"],
            "names '.added', which UPPERCASE_SELECTORS lacks"),
        ("1 more reset rule", listed, resets, sheets + [".added .x { text-transform: none }"],
            "names '.added .x', which RESET_SELECTORS lacks"),
        ("a stale selector in the list", listed + [".stale"], resets, sheets, "UPPERCASE_SELECTORS names '.stale'"),
        ("a stale selector in the reset list", listed, resets + [".stale"], sheets, "RESET_SELECTORS names '.stale'"),
        ("a full-width uppercase rule", listed, resets, sheets + [".added { text-transform: full-width uppercase }"],
            f"full-width uppercase in '.added', {unread}"),
        ("a text-transform from a custom property", listed, resets, sheets + [".added { text-transform: var(--tt) }"],
            f"var(--tt) in '.added', {unread}"),
        ("an important uppercase rule", listed, resets, sheets + [".added { text-transform: uppercase !important }"],
            f"uppercase !important in '.added', {unread}"),
        # A declaration before a nested rule is read as part of the nested rule's selector, so only the nesting
        # problem names it.
        ("a nested rule", listed, resets, sheets + [".added { text-transform: uppercase; .x { color: red } }"],
            f"a rule nested in the style rule '.added', {unread}"),
        ("a reset rule inside @media", listed, resets, sheets + ["@media print { .added { text-transform: none } }"],
            f"none in '.added' inside '@media print', {unread}"),
        ("an uppercase rule inside @layer", listed, resets,
            sheets + ["@layer x { .added { text-transform: uppercase } }"],
            f"uppercase in '.added' inside '@layer x', {unread}"),
        # A CSS escape spells text-transform here; a browser reads it as that property.
        ("an escaped property name", listed, resets, sheets + [".added { text\\2d transform: uppercase }"],
            "a property name with an escape, 'text\\\\2d transform', in '.added', " + unread),
        # Small capitals show the label in capital letters, which the label rule does not read, so a
        # caps value, or a value that cannot be read, of a property that can set them fails, in any rule or at-rule.
        ("a small-caps rule", listed, resets, sheets + [".added { font-variant: Small-Caps }"],
            f"font-variant: small-caps in '.added', {unread}"),
        ("an all-small-caps rule inside @media", listed, resets,
            sheets + ["@media print { .added { font-variant-caps: all-small-caps } }"],
            f"font-variant-caps: all-small-caps in '.added' inside '@media print', {unread}"),
        ("a font-variant-caps other than normal", listed, resets, sheets + [".added { font-variant-caps: unset }"],
            f"font-variant-caps: unset in '.added', {unread}"),
        ("a font shorthand with small-caps", listed, resets,
            sheets + ['.added { font: small-caps 500 1rem/1 "Public Sans", serif }'],
            f"font: small-caps 500 1rem/1 \"public sans\", serif in '.added', {unread}"),
        ("a system font", listed, resets, sheets + [".added { font: small-caption }"],
            f"font: small-caption in '.added', {unread}"),
        ("a small-capital font feature", listed, resets, sheets + ['.added { font-feature-settings: "smcp" 1 }'],
            f"font-feature-settings: \"smcp\" 1 in '.added', {unread}"),
        ("a font-variant from a custom property", listed, resets, sheets + [".added { font-variant: var(--fv) }"],
            f"font-variant: var(--fv) in '.added', {unread}"),
        ("a small-caps descriptor in @font-face", listed, resets,
            sheets + ["@font-face { font-family: x; font-variant: small-caps }"],
            f"font-variant: small-caps in '@font-face', {unread}"),
        ("an escaped property name in @font-face", listed, resets,
            sheets + ["@font-face { font-family: x; font\\2d variant: small-caps }"],
            "a property name with an escape, 'font\\\\2d variant', in '@font-face', " + unread),
        ("a font shorthand and a font-variant-caps that show no small capitals", listed, resets,
            sheets + ['.added { font: 500 clamp(1rem, 2vw, 2rem)/1 "Public Sans", serif; font-variant-caps: normal }'],
            None),
    ]
    for name, given, given_resets, texts, expected in cases:
        problems = uppercase_coverage(given, given_resets, texts)
        if expected is None and problems:
            failures.append(f"uppercase selectors, {name}: {problems}")
        elif expected is not None and not any(expected in problem for problem in problems):
            failures.append(f"uppercase selectors, {name}: {expected!r} not reported ({problems})")
    ignorable = [code for first, last in LOADED.DEFAULT_IGNORABLE for code in range(first, last + 1)
                 if unicodedata.category(chr(code)) in LOADED.VALUE_CATEGORIES]
    if ignorable:
        failures.append(f"VALUE_CATEGORIES admits Default_Ignorable_Code_Points: {[f'U+{c:04X}' for c in ignorable]}")
    return len(cases) + 1


def check_about_spacing(failures: list[str]) -> int:
    """The About row's spacing of specification 7.24 (1 ordinary space after each dot span and none before it) on the
    committed landing page, 1 fault each: validate(), called directly, refuses by the block's rule, and the build
    test's helper by its own rule. The 1.6.1 markup, no space after a dot, must also be refused by the helper's dot
    check, which reads no copy of the row; the row itself the helper reads from the pinned specification."""
    generator = load_module(GENERATOR)
    config = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))
    page = next(entry for entry in config["pages"] if entry["path"] == "")
    text = (REPO_ROOT / "site/index.html").read_text(encoding="utf-8")
    row, block_rule = about_line("/"), "the About block must appear exactly once"
    spaced, pinned = "with no space after it, the 1.6.1 markup", "lacks the whole About block"
    cases = [
        ("no space after a dot (the 1.6.1 markup)", row.replace(ABOUT_DOT + " ", ABOUT_DOT), spaced),
        ("a space before a dot", row.replace("</a>" + ABOUT_DOT, "</a> " + ABOUT_DOT, 1), pinned),
        ("&nbsp; in place of a space", row.replace(ABOUT_DOT + " ", ABOUT_DOT + "&nbsp;", 1), pinned),
        ("2 spaces after a dot", row.replace(ABOUT_DOT + " ", ABOUT_DOT + "  ", 1), pinned),
    ]
    for name, new, helper_says in cases:
        if text.count(row) != 1 or new == row:
            failures.append(f"About spacing '{name}': the row is not once in site/index.html, or the fault is a no-op")
        page_html = text.replace(row, new, 1)
        try:
            generator.validate(page_html, page, config, "/")
            refusal = ""
        except generator.BuildError as error:
            refusal = str(error)
        if block_rule not in refusal:
            failures.append(f"About spacing '{name}': not refused by the block's rule ({refusal[:200] or 'passed'})")
        if not any(helper_says in problem for problem in about_problems("index.html", page_html, "/")):
            failures.append(f"About helper, spacing '{name}': not refused by its rule")
    return 2 * len(cases)


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


def check_generator_about(failures: list[str]) -> int:
    """A generator whose about_line() writes 1 byte other than specification 7.24 (a space after the row's start tag,
    which passed while this test kept its own copy of the row and both copies carried it) builds, since it checks
    the block against itself, and the build test's helper, which reads the row from the pinned specification,
    refuses the landing page it writes."""
    source = GENERATOR.read_text(encoding="utf-8")
    old = f"return '{ABOUT_START}' + "
    if source.count(old) != 1:
        failures.append(f"generator About: {old!r} is not once in tools/build-site.py")
        return 1
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        mutant = root / "tools" / GENERATOR.name
        mutant.write_text(source.replace(old, f"return '{ABOUT_START} ' + ", 1), encoding="utf-8")
        out = Path(scratch) / "out"
        result = subprocess.run([sys.executable, "-I", str(mutant), "--root", str(root), "--out", str(out)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            failures.append(f"generator About: the mutant gave exit {result.returncode}, expected 0 "
                            f"({result.stderr.strip()[:200]})")
        elif not about_problems("index.html", (out / "index.html").read_text(encoding="utf-8"), "/"):
            failures.append("generator About: the helper passes an About row 1 byte off specification 7.24")
    return 1


def check_about_source(failures: list[str]) -> int:
    """The build test's helper gives the About block that the pinned .baseline/SPECIFICATION.md carries, read here
    as text: at base /, it is the backtick span of the 1 line starting with ABOUT_MARKUP. A helper that keeps a copy
    of the block, changed along with the generator's, fails this case and check_about_reader()."""
    block = about_block("/")
    lines = SPECIFICATION.read_bytes().decode("utf-8").split("\n")
    if sum(line.startswith(f"{ABOUT_MARKUP}{block}`") for line in lines) != 1:
        failures.append("About source: the helper's About block is not the one .baseline/SPECIFICATION.md gives")
    return 1


def check_about_reader(failures: list[str]) -> int:
    """The helper's About block comes only from specification_about(): on a copy of the pinned specification whose
    7.24 block is altered, with a SHA256SUMS that lists the copy's digest, the helper gives the altered block at
    base / and at /draft/. A helper that keeps a literal copy of today's block fails this case."""
    block = about_block("/")
    old = f"{ABOUT_MARKUP}{block}`"
    altered = block.replace(f">{LABEL}</p>", ">About this altered project</p>", 1)
    text = SPECIFICATION.read_bytes().decode("utf-8")
    if text.count(old) != 1 or altered == block:
        failures.append("About reader: the 7.24 block or its label is not once in .baseline/SPECIFICATION.md")
        return 1
    data = text.replace(old, f"{ABOUT_MARKUP}{altered}`", 1).encode("utf-8")
    sums = SUMS.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as scratch:
        changed, changed_sums = Path(scratch) / SPECIFICATION.name, Path(scratch) / SUMS.name
        changed.write_bytes(data)
        changed_sums.write_text(sums.replace(hashlib.sha256(SPECIFICATION.read_bytes()).hexdigest(),
                                             hashlib.sha256(data).hexdigest(), 1), encoding="utf-8")
        draft = altered
        for path in json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))["about_paths"]:
            draft = draft.replace(f'href="/{path}"', f'href="/draft/{path}"')
        try:
            given = about_block("/", changed, changed_sums), about_block("/draft/", changed, changed_sums)
        except ValueError as error:
            failures.append(f"About reader: the altered specification is refused ({error})")
        else:
            if given != (altered, draft):
                failures.append("About reader: the helper's About block does not follow the specification's 7.24")
    return 1


def check_specification_digest(failures: list[str]) -> int:
    """The helper reads section 7.24 only from a specification that hashes to its line in .baseline/SHA256SUMS: a
    copy of the pinned one with 1 byte added after its end, its block unchanged, is refused."""
    with tempfile.TemporaryDirectory() as scratch:
        changed = Path(scratch) / SPECIFICATION.name
        changed.write_bytes(SPECIFICATION.read_bytes() + b"\n")
        try:
            specification_about(changed, SUMS)
        except ValueError as error:
            if "does not hash to its 1 line" not in str(error):
                failures.append(f"specification digest: refused by another rule ({error})")
        else:
            failures.append("specification digest: the helper reads a specification that does not match its digest")
    return 1


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


def check_unreadable_reader(failures: list[str]) -> int:
    """A copy of the generator, beside a check-install-page.py that is missing, unreadable (with a cache of its
    bytecode or without), a FIFO (not a regular file, on which a read would wait for a writer), not Python, without
    is_hiding_element() or a ZERO_WIDTH string, whose is_hiding_element() fails when called (as when it takes 1
    argument), or whose is_hiding_element() returns anything but True or False,
    exits 3: the hiding reader is an input. A reader that this
    test cannot make unreadable, as when it runs as root, or a FIFO it cannot make, as where os.mkfifo() is missing,
    fails the case rather than skipping it, and so does a generator that has not exited within 60 seconds."""
    def unreadable(cache: bool):
        def apply(reader: Path) -> None:
            if cache:
                # A timestamp cache, which an import trusts on the source's size and mtime alone, without reading it.
                py_compile.compile(str(reader), doraise=True,
                                   invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
                if not Path(importlib.util.cache_from_source(str(reader))).is_file():
                    raise AssertionError("no bytecode cache was written")
            reader.chmod(0)
            try:
                reader.read_bytes()
            except PermissionError:
                return
            raise AssertionError("the reader is still readable after chmod 0 (running as root?)")
        return apply

    cases = [
        ("a missing reader", lambda reader: reader.unlink()),
        ("an unreadable reader with a cache of its bytecode", unreadable(True)),
        ("an unreadable reader without a cache", unreadable(False)),
        ("a FIFO in place of the reader", lambda reader: (reader.unlink(), os.mkfifo(reader))),
        ("a reader with a syntax error", lambda reader: reader.write_bytes(b"def is_hiding_element(:\n")),
        ("a reader without is_hiding_element()", lambda reader: reader.write_bytes(b"HIDING_CLASSES = ()\n")),
        ("a reader without ZERO_WIDTH", lambda reader: reader.write_bytes(
            b"def is_hiding_element(tag, attrs):\n    return False\n")),
        ("a reader whose is_hiding_element() takes 1 argument", lambda reader: reader.write_bytes(
            b'ZERO_WIDTH = "\\u200b"\ndef is_hiding_element(tag):\n    return False\n')),
        ("a reader whose is_hiding_element() returns None", lambda reader: reader.write_bytes(
            b'ZERO_WIDTH = "\\u200b"\ndef is_hiding_element(tag, attrs):\n    return None\n')),
    ]
    for name, fault in cases:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            generator = root / "tools" / GENERATOR.name
            shutil.copyfile(GENERATOR, generator)
            try:
                fault(root / "tools" / "check-install-page.py")
            except (AssertionError, AttributeError, OSError, py_compile.PyCompileError) as error:
                failures.append(f"unreadable reader '{name}': the fault could not be made ({error})")
                continue
            try:
                result = subprocess.run([sys.executable, "-I", str(generator), "--root", str(root), "--out",
                                         str(Path(scratch) / "out")], capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                failures.append(f"unreadable reader '{name}': no exit within 60 seconds, expected 3")
                continue
            if result.returncode != 3 or "whose hiding reader" not in result.stderr:
                failures.append(f"unreadable reader '{name}': exit {result.returncode}, expected 3 "
                                f"({result.stderr.strip()[:200]})")
    return len(cases)


def check_helper_reader(failures: list[str]) -> int:
    """This test, copied beside the generator, the pinned specification and site.json but no check-install-page.py,
    fails with exit 1 and a failure naming the reader, rather than stopping with a traceback: its About helper reads
    the install gate only through the generator's install_gate()."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        for relative in ("tools/build-site.py", "tools/test-build-site.py", ".baseline/SPECIFICATION.md",
                         ".baseline/SHA256SUMS", "site-src/site.json"):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / relative, root / relative)
        try:
            result = subprocess.run([sys.executable, "-I", str(root / "tools" / "test-build-site.py")],
                                    capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            failures.append("helper reader: no exit within 60 seconds, expected 1")
            return 1
        if (result.returncode != 1 or "check-install-page.py, whose hiding reader" not in result.stdout
                or "could not be read" not in result.stdout or "Traceback" in result.stderr):
            failures.append(f"helper reader: exit {result.returncode}, expected 1 with a failure naming the missing "
                            f"reader and no traceback ({(result.stdout + result.stderr).strip()[:200]})")
    return 1


def check_page_rules(failures: list[str]) -> int:
    """The rules validate() holds for markup that the page source grammar keeps out of every page source, so that
    only the generator's own markup could carry it, for a bidi formatting character, which with_about() refuses
    in a page source and validate() in any text the generator writes, and for an en or em dash and "what this is"
    written with character references: called directly on committed pages with 1 snippet after the h1, validate()
    refuses each by its rule."""
    generator = load_module(GENERATOR)
    config = json.loads((REPO_ROOT / "site-src/site.json").read_text(encoding="utf-8"))
    pages = {entry["id"]: entry for entry in config["pages"]}
    files = {"license": "site/license/index.html", "404": "site/404.html"}
    texts = {page_id: (REPO_ROOT / path).read_text(encoding="utf-8") for page_id, path in files.items()}
    cases = [
        ("a style element", "license", "/", "<style>p { color: red; }</style>", "a <style> element"),
        ("an inline script", "license", "/", "<script>alert(1)</script>", "an inline executable <script>"),
        ("a module script", "license", "/", '<script type="module">alert(1)</script>', "an inline executable <script>"),
        ("a JSON-LD block on a noindex page", "404", "/", '<script type="application/ld+json">{}</script>',
            "a JSON-LD block on a noindex page"),
        ("a JSON-LD block on a draft page", "license", "/draft/", '<script type="application/ld+json">{}</script>',
            "a JSON-LD block on a draft page"),
        ("a math element", "license", "/", "<math></math>", PAGE_MATH_RULE),
        ("a bare svg outside the switch", "license", "/", "<svg></svg>", "an inline <svg> other than the light and dark"),
        ("U+202E as a character reference", "license", "/", "<p>&#x202E;x</p>", PAGE_BIDI_RULE),
        ("U+2067 as written", "license", "/", "<p>x\u2067y</p>", PAGE_BIDI_RULE),
        # The dash refusal reads character references too, and "what this is" is read in the
        # text the parser reads, character references decoded.
        ("an em dash as a character reference", "license", "/", "<p>x &mdash; y</p>", "an en or em dash"),
        ("an en dash as a numeric character reference", "license", "/", "<p>1&#8211;2</p>", "an en or em dash"),
        ("what this is framing with a character reference", "license", "/", "<p>What&#32;this is not.</p>",
            '"what this is" framing'),
    ]
    for name, page_id, base, snippet, rule in cases:
        h1 = re.search(r"<h1>[^<]*</h1>", texts[page_id]).group(0)
        try:
            generator.validate(texts[page_id].replace(h1, h1 + snippet, 1), pages[page_id], config, base)
            refusal = ""
        except generator.BuildError as error:
            refusal = str(error)
        if rule not in refusal:
            failures.append(f"page rule '{name}': not refused by its rule ({refusal[:200] or 'passed'})")
    return len(cases)


def check_source_positions(failures: list[str]) -> int:
    """Each source refusal names where the refused markup starts in the source as the generator reads it, with its
    tokens and rail written in (the line counted from 1, the column from 0, as getpos() counts them): called directly
    on 2 lines for each kind (through with_about() for the tree rules), and once through a build, where a < in text on
    line 11 of instructions.html is reported on a later line, after the lines that {{instructions}} writes in."""
    cases = [
        ("a < in text", "<p>x</p>\n<p>1 < 2</p>"),
        ("a body start tag", "<p>x</p>\n<p>1 <body hidden></p>"),
        ("a math start tag", "<p>x</p>\n<p>1 <math></math></p>"),
        ("a script start tag", "<p>x</p>\n<p>1 <script></script></p>"),
        ("a select start tag", "<p>x</p>\n<p>1 <select></select></p>"),
        ("a noscript inside a noscript", "<noscript>\n<p>1 <noscript></noscript></p></noscript>"),
        ("an attribute outside SOURCE_ATTRIBUTES", '<p>x</p>\n<p>1 <span title="x"></span></p>'),
        ("a </br> end tag", "<p>x</p>\n<p>1 </br></p>"),
    ]
    where = "at line 2, column 5 of the source with its tokens and rail written in"
    for name, content in cases:
        problem = LOADED.source_problem(content) or ""
        if where not in problem:
            failures.append(f"source position '{name}': {where!r} is not in the refusal ({problem[:200] or 'none'})")
    tree_cases = [
        ("a summary inside a p in a details", "<details><p>x</p>\n<p>1 <summary></summary></p></details>"),
        ("a div inside a p", "<p>x</p>\n<p>1 <div></div></p>"),
    ]
    for name, content in tree_cases:
        try:
            LOADED.with_about(content, {"source": "case.html", "path": "case/"}, "/")
            problem = ""
        except LOADED.BuildError as error:
            problem = str(error)
        if where not in problem:
            failures.append(f"source position '{name}': {where!r} is not in the refusal ({problem[:200] or 'none'})")
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        path = root / "site-src" / "pages" / "instructions.html"
        lines = path.read_text(encoding="utf-8").split("\n")
        lines[10] += "<p>1 < 2</p>"
        path.write_text("\n".join(lines), encoding="utf-8")
        result = run(root, "--out", str(Path(scratch) / "out"))
        reported = re.search(r"a < that begins no start tag, end tag or comment of the grammar at line ([0-9]+), "
                             r"column [0-9]+ of the source with its tokens and rail written in", result.stderr)
        if result.returncode != 1 or reported is None or int(reported.group(1)) <= 11:
            failures.append(f"source position 'a < in text on line 11 of instructions.html': exit {result.returncode}, "
                            f"expected 1 with a later line ({result.stderr.strip()[:200]})")
    return len(cases) + len(tree_cases) + 1


def check_clean_build(failures: list[str]) -> int:
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"clean build: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        pages = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html"))
        if len(pages) != 18:
            failures.append(f"clean build: {len(pages)} pages, expected 18: {pages}")
        config = json.loads((root / "site-src/site.json").read_text(encoding="utf-8"))
        noindex = {p["path"] if p["path"].endswith(".html") else p["path"] + "index.html"
                   for p in config["pages"] if p.get("noindex")}
        if noindex != {"404.html"}:
            failures.append(f"clean build: the noindex pages are {sorted(noindex)}, expected only 404.html")
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
                    failures.append(f"clean build: {page} links {value}, under /draft/, which the live site does not carry")
            failures += [f"clean build: {problem}" for problem in scheme_problems(page, text, "/", config)]
            failures += [f"clean build: {problem}" for problem in about_problems(page, text, "/")]
        for page_id, page in (("home", "index.html"), ("install", "install/index.html"), ("license", "license/index.html")):
            stamp = f'<meta property="article:modified_time" content="{modified[page_id]}">'
            if stamp not in (out / page).read_text(encoding="utf-8"):
                failures.append(f"clean build: {page} lacks its site.json modified date {stamp!r}")
        # Template 1.11.0: a draft is reviewed on the draft branch's own deployment, so the live build has no /draft/.
        if (out / "draft").exists():
            failures.append("clean build: the / build wrote draft/, which the live site no longer carries")
        sitemap_config = json.loads((root / "tools/sitemap-config.json").read_text(encoding="utf-8"))
        if "draft/index.html" in sitemap_config["exclude"]:
            failures.append("clean build: the sitemap config still excludes the removed draft holding page")
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


VENDORREPLIES_LOGO = "assets/baseline/logos/vendorreplies.png"
# The seventh footer card of template specification 7.19 (baseline 1.11.0), byte for byte as the footer of the 1.11.1
# package's reference/landing.html gives it, apart from the logo path: ../logos/ there, /assets/baseline/logos/ here.
# It is written out here, not read from the generator's SEVENTH_CARD, so that a change to any byte of that card fails.
REFERENCE_CARD = (
    '<li class="slice slice-vr"><a class="card" href="https://vendorreplies.ai/" target="_blank" rel="noopener noreferrer">'
    '<img src="/assets/baseline/logos/vendorreplies.png" alt=""><span class="cname">VendorReplies<span class="tld">.ai</span></span>'
    '<span class="vh"> (opens in a new tab)</span></a></li>'
)


def check_footer(failures: list[str]) -> int:
    """The footer holds the 6 rotated cards and the seventh card of specification 7.19 (baseline 1.11.0).

    This guards a partial adoption: a copy of baseline 1.11.0 or later without the generator's seventh card passes
    every other gate while the footer silently keeps 6 cards. On every generated page, the card list holds 7 cards and
    ends with REFERENCE_CARD, byte for byte, and no other slice-vr card.
    """
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"footer: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        home = (out / "index.html").read_text(encoding="utf-8")
        match = re.search(r'<ul class="cards rainbow" aria-label="([^"]*)">(.*?)</ul>', home, re.S)
        if match is None:
            failures.append("footer: the home page has no card list")
            return 1
        label, cards = match.groups()
        if label != "The 7 project sites":
            failures.append(f"footer: the card list is labelled {label!r}, expected 'The 7 project sites'")
        slices = re.findall(r'<li class="slice ([^"]*)">(.*?)</li>', cards, re.S)
        if len(slices) != 7 or cards.count('<li class="slice ') != 7:
            failures.append(f"footer: the home page holds {len(slices)} cards, expected 7")
        if not slices or slices[0][0] != "slice-4" or 'aria-current="page"' not in slices[0][1]:
            failures.append("footer: the first card is not slice-4 with aria-current=\"page\"")
        pages = sorted(path.relative_to(out).as_posix() for path in out.rglob("*.html"))
        wrong = []
        for page in pages:
            text = (out / page).read_text(encoding="utf-8")
            lists = re.findall(r'<ul class="cards rainbow" aria-label="[^"]*">(.*?)</ul>', text, re.S)
            if (len(lists) != 1 or lists[0].count('<li class="slice ') != 7 or not lists[0].endswith(REFERENCE_CARD)
                    or text.count('<li class="slice slice-vr">') != 1):
                wrong.append(page)
        if "index.html" not in pages or wrong:
            failures.append(f"footer: {len(wrong)} of {len(pages)} generated pages do not end a card list of 7 with the "
                            f"seventh card of specification 7.19, byte for byte: {', '.join(wrong) or 'no home page'}")
        pinned = tomllib.loads((root / ".baseline/pin.toml").read_text(encoding="utf-8")).get("files", {})
        if VENDORREPLIES_LOGO not in pinned:
            failures.append(f"footer: {VENDORREPLIES_LOGO} is not pinned in .baseline/pin.toml")
    return 1


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
        ("the removed draft holding page left behind", leave("draft/index.html")),
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
        text = (out / "404.html").read_text(encoding="utf-8")
        if '<meta name="robots" content="noindex, nofollow">' not in text or "application/ld+json" in text:
            failures.append("promotion build: 404.html must stay noindex without publish metadata")
        if (out / "draft").exists():
            failures.append("promotion build: the / build wrote draft/, which the live site no longer carries")
        config = json.loads((root / "site-src/site.json").read_text(encoding="utf-8"))
        for page in sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html")):
            text = (out / page).read_text(encoding="utf-8")
            failures += [f"promotion build: {problem}" for problem in scheme_problems(page, text, "/", config)]
            failures += [f"promotion build: {problem}" for problem in about_problems(page, text, "/")]
    return 5


def check_staged_build(failures: list[str]) -> int:
    """A staging round on the draft branch still builds: every page noindex, and every root-relative href and src
    under /draft/ or /downloads/."""
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
                    failures.append(f"staged build: {page} links {value} outside /draft/ and /downloads/")
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
    hiding = set(GATE.HIDING_ELEMENTS)
    if not load_module(GENERATOR).INERT_TAGS == INERT == inline >= hiding:
        failures.append("INERT_TAGS, check-inline-code.py's INERT_ELEMENTS and INERT here differ, or leave out an element "
                        "of check-install-page.py's HIDING_ELEMENTS")
    ran += check_refusals(failures)
    ran += check_source_refusals(failures)
    ran += check_source_passes(failures)
    ran += check_rail_reader(failures)
    ran += check_unreadable(failures)
    ran += check_unreadable_reader(failures)
    ran += check_helper_reader(failures)
    ran += check_page_rules(failures)
    ran += check_source_positions(failures)
    ran += check_scheme_validation(failures)
    ran += check_inert_validation(failures)
    ran += check_inner_about_rows(failures)
    ran += check_label_count(failures)
    ran += check_value_signs(failures)
    ran += check_about_block(failures)
    ran += check_uppercase_selectors(failures)
    ran += check_about_spacing(failures)
    ran += check_generator_header(failures)
    ran += check_generator_about(failures)
    ran += check_about_source(failures)
    ran += check_about_reader(failures)
    ran += check_specification_digest(failures)
    ran += check_clean_build(failures)
    ran += check_staged_build(failures)
    ran += check_family_pages(failures)
    ran += check_footer(failures)
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
