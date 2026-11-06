#!/usr/bin/env python3
"""Generate the cleanlanguage.ai site on the shared template (baseline), with a base path.

The site is generated from ``site-src/`` into the folder its base path names:
``/`` writes ``site/`` (the published site, the current setting in
``site-src/site.json`` since promotion), and ``/draft/`` writes ``site/draft/``
(staging a new version for review). Cloudflare Pages publishes ``site/`` as
committed, so the output is committed and this tool's ``--check`` mode proves
that the committed output is exactly what the sources produce.

Sources
-------

- ``site-src/site.json``: base path, site class, navigation, page list (each
  page with its ``modified`` date, the ``article:modified_time`` of the ``/``
  build, and its ``published`` date), the fixed root paths a draft page may
  link to (``root_allowlist``), the files committed by hand beside the
  generated ones at ``site/`` (``static_files``), the family footer order, and
  the pages allowed to link the Disclosure and Licence pages.
- ``.baseline/pin.toml``: the baseline version (for the ``?v=`` asset tokens)
  and the pinned file list, the one source of both (``tools/copy-baseline.py``
  writes it, ``tools/check-baseline-pin.py`` checks the copied files). Only the
  keys under ``assets/baseline/`` are served; the pinned build tool
  ``.baseline/check_palette.py`` is not, so no link may resolve to it.
- ``site-src/release.json``: the release version, tag and checksum, written by
  ``tools/set-release-links.py``. Every version string the pages show comes
  from here, and the build refuses to run if it disagrees with the ``Version:``
  line of ``cleanlanguage/skills/cleanlanguage/SKILL.md``. While its checksum
  is the zero placeholder of a version bump, the verify page shows no checksum
  and says that it appears once that version is published (``sum_tokens()``).
  ``verify_download_block()`` renders the verify page's download block alone,
  which ``tools/check-release-links.py`` and
  ``tools/check-release-checksum-live.py`` require on the page, and
  ``verify_page()`` renders the whole verify page, which both gates require
  the committed page to equal and ``tools/test-build-site.py`` pins.
- ``site-src/pages/<page>.html``: the hand-written content of each page, with
  ``{{token}}`` placeholders.
- ``site-src/assets/site.css``, optional: only the measured per-site constants
  ``--sw`` and ``--logo-inset`` (baseline README, "Per-site constants"),
  loaded after ``baseline.css``, when the statement or the logo changes. This
  site uses the values shipped in ``baseline.css``, so there is no such file.
- Generated from the skill's own files: the Examples pairs
  (``references/examples.md``), the By channel lists
  (``references/context-modes.md``), the checklist (``references/qa-checklist.md``)
  and the Instructions block (``site/downloads/cleanlanguage.md``, exactly).

Every page loads ``scheme.js`` in ``<head>`` before the stylesheets, with
``data-cfasync="false"`` and no ``defer``, and ends ``header.mast`` with the
light and dark switch (``SCHEME_SWITCH``), as template specification 7.33
(baseline 1.6.0) requires.

The baseline files under ``<out>/assets/baseline/`` are copied and pinned by
``tools/copy-baseline.py`` and ``tools/check-baseline-pin.py``; this tool reads
them but never writes them.

Refusals (any one stops the build, exit 1)
-----------------------------------------

An unbalanced element (a closing tag with no open element, or an element left
open), content after the document grid ``.doc`` closes inside ``main``, or
tag text such as ``<code>`` shown inside a ``pre`` block (each a defect found
in the 1.2.1 reference demo page);
an en or em dash; an inline ``style`` attribute or ``<style>`` element; an
inline executable ``<script>`` (a ``application/ld+json`` data block is
allowed, and emitted only at base ``/``); an ``on*`` attribute; an attribute
repeated on 1 tag, which a browser reads by its first value; "what this is"
framing; not exactly 1 ``h1``; a missing skip link, ``main#main-content``,
family footer or ``#copy-status``; a duplicate ``id``; an unreplaced token; an
in-page fragment with no target; a root-relative link or asset outside the base
path that is not in ``root_allowlist``; a relative link; an external link
without ``target="_blank" rel="noopener noreferrer"`` and the "(opens in a new
tab)" text; a draft page, or a ``noindex`` page at base ``/``, without
exactly 1 ``noindex, nofollow`` robots meta, and an indexable page at base
``/`` with one; a JSON-LD block on a draft page or a ``noindex`` page; a page
of the ``/`` build with no ``modified`` date (and no ``--date``), or a date
that is not ``YYYY-MM-DD``; a page without exactly 1 light and dark switch
(``SCHEME_SWITCH``, exactly, as the last child of ``header.mast``, after
``nav.nav``, and the only element with a ``data-scheme-toggle`` attribute,
each of which ``scheme.js`` wires and shows), without exactly 1 ``scheme.js``
script tag before the first stylesheet, it and every stylesheet inside
``<head>``, or with any other ``<svg``; a page source, the landing page's
included, with an element whose class names include ``about``, since the
generator writes the About block of template specification 7.24 (baseline
1.7.0) itself; a landing page source without exactly 1 ``p.value``, or with
that ``p.value`` inside an element of ``INERT_TAGS`` (which holds every
element of ``tools/check-install-page.py``'s ``HIDING_ELEMENTS``), or carrying
a ``hidden`` attribute (in any value) or inside an element that carries one,
or with no ``div.region`` among its ancestors; a landing page whose output
lacks exactly 1 such ``p.value`` and, once and byte for byte, the whole About
block (``about_block()``: ``ABOUT_BLOCK``, the ``div.region`` with its label
and its ``div`` around the row ``about_line()`` gives, 1 ordinary space after
each dot span and none before it) directly after the end tag of that
paragraph's region, the ``div.region`` nearest it among its ancestors, with
no byte between that ``</div>`` and the block, as the generator writes them,
or that carries any other element whose class names include ``about``; any
other page with one; and a release version that disagrees with SKILL.md. The
About rules read the About block's label only as part of that block: a
hand-written ``About this project`` text or label region without the
``about`` class, on any page, is not refused. They count a ``hidden``
attribute on the value paragraph itself or on any of its ancestors, but do
not model the other ways ``tools/check-install-page.py`` reads an element as
hidden (``inert``, ``aria-hidden="true"``, ``popover``, a ``dialog`` or
``details`` without ``open``, or a class in its ``HIDING_CLASSES``) nor any
stylesheet, so a value paragraph hidden only by one of those passes them and
the block follows it; nor markup inside an element whose content Python's
parser reads as text (``script`` and ``style``, and, depending on the Python
version, other raw-text and RCDATA elements such as ``textarea``); nor a
``hidden`` attribute that HTML5 copies from a stray ``<body>`` or ``<html>``
start tag onto the page's body or html element. The switch, its place and the
head are read as parsed elements: each element with ``data-scheme-toggle`` (an
attribute name in any letter case), the switch's parent, the element before it
and the end of its parent, and ``html > head``, the first head or body the page
opens. As in a browser, a self-closing tag leaves an element that is neither
void nor in ``<svg>`` open, class names split on ASCII whitespace only
(``class="mast&nbsp;x"`` is not ``mast``), and the head ends at the first text
other than whitespace, start tag other than those HTML5 allows in a head
(``HEAD_TAGS``), or ``</body>``, ``</html>`` or ``</br>``; a script or
stylesheet after that point is outside it. No element with
``data-scheme-toggle`` may sit inside an element whose content a browser with
scripting on, the only case in which ``scheme.js`` runs, does not render as
page elements (``INERT_TAGS``: ``noscript``, ``template``, ``plaintext``, the
raw-text and RCDATA elements, and the elements ``tools/check-install-page.py``
hides for that reason, ``audio``, ``canvas``, ``datalist``, ``meter``,
``object``, ``progress``, ``rp``, ``select`` and ``video``, whose content a
browser renders only as fallback, only in its control or not at all, so this
refuses more than a browser hides); a script or stylesheet inside one is not in
``html > head``, and an ``h1``, a robots meta, the skip link,
``main#main-content``, the family footer, ``#copy-status`` or the landing
page's value paragraph inside one fails, as does a fragment whose only target
is inside one. The reading fails closed where it does not model HTML5: such a
start tag inside a ``<template>`` or ``<noscript>`` in the head ends the head,
and a self-closing tag in ``<math>`` leaves its element open. It is not a full
HTML5 tree builder, so each page must also carry, once and byte for byte, the
markup from the body start tag to the end of ``header.mast`` as the generator
writes it: ``<body>``, the skip link and the header block ``MAST_BLOCK`` pins
with the values from ``site-src/site.json``, each on its own line. That
``<body>`` must be the page's first body, parsed as a child of ``html`` right
after its only head closes (whitespace and comments apart), before the head
ends. As far as the parsed reading models HTML5, no element can then wrap the
header, nor precede it in the body other than the skip link, and a change to
``mast()`` or to the lines around it that alters that markup fails. That pin
covers neither the head nor anything after ``header.mast``, which only the
parsed reading checks (and, on the landing page, the About block pin), and it
is only as right as ``MAST_BLOCK``, ``SKIP_LINK`` and ``SCHEME_SWITCH``: a
change to one of them made together with the same change to the generator
passes. The About block pin is only as right as ``ABOUT_BLOCK`` and
``about_line()``, from which the generator both writes and checks the block,
so a change to either alone passes it; ``tools/test-build-site.py`` reads the
block apart from them, from section 7.24 of the pinned template's
``SPECIFICATION.md`` (``.baseline/SPECIFICATION.md``, checked against
``.baseline/SHA256SUMS``). What guarantees the committed
pages is ``--check``, a deploy gate, which compares them byte for byte with a
fresh build that passed these refusals.

Modes
-----

    python3 -I tools/build-site.py            write the configured base path's output
    python3 -I tools/build-site.py --check    regenerate in memory and compare byte for byte
    python3 -I tools/build-site.py --out DIR [--base B] [--date YYYY-MM-DD]
                                             render into DIR instead (tests); --date
                                             replaces every page's modified date

``--check`` fails on any missing, extra or different file under the output
folder outside ``assets/baseline/``, on any file there that is neither
generated nor listed in ``static_files`` (at ``site/`` only), on a listed static
file that is missing, and on any internal link that does not resolve to a
generated page, a generated anchor, a pinned baseline file or an allowlisted
root file. Writing a ``--base /`` override into ``site/`` while
``site-src/site.json`` names another base needs ``--promote``, so a promotion
cannot happen by accident before the owner approves; once the configured base
is ``/``, a plain run writes ``site/``. The build never deletes a stale file at
``site/``; remove an old page with ``git rm``.

Exit codes:
  0  written, or the check passed
  1  a refusal, a drift or an unresolved link
  3  an input could not be read or is malformed
"""

from __future__ import annotations

import argparse
import hashlib
import tomllib
import html
import json
import os
import re
import stat
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = Path("site-src")
SKILL = Path("cleanlanguage/skills/cleanlanguage/SKILL.md")
REFS = Path("cleanlanguage/skills/cleanlanguage/references")
DOWNLOADS = Path("site/downloads")
REPO_SLUG = "jposluns/cleanlanguage"

SKILL_VERSION = re.compile(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$")
TOKEN = re.compile(r"\{\{([a-z0-9_.:-]+)\}\}")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
H2_ID = re.compile(r'<h2(?: class="[^"]*")? id="([^"]+)"[^>]*>(.*?)</h2>', re.S)
TAGS = re.compile(r"<[^>]+>")
NEW_TAB = "<span class=\"vh\"> (opens in a new tab)</span>"
EXECUTABLE_TYPES = {"", "module", "text/javascript", "application/javascript", "text/ecmascript"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# The start tags HTML5 allows in a head; any other start tag ends it, as text other than whitespace does.
HEAD_TAGS = {"base", "basefont", "bgsound", "link", "meta", "noframes", "noscript", "script", "style", "template", "title"}
# The elements whose content a browser with scripting on (the only case in which scheme.js runs) does not render
# as page elements (noscript, template, plaintext, the raw-text and RCDATA elements) or renders only as fallback,
# only in its control or not at all (the other elements of tools/check-install-page.py's HIDING_ELEMENTS: audio,
# canvas, datalist, meter, object, progress, rp, select and video). No switch counts as placed inside one.
INERT_TAGS = {"noscript", "template", "script", "style", "title", "textarea", "xmp", "iframe", "noembed", "noframes", "plaintext",
              "audio", "canvas", "datalist", "meter", "object", "progress", "rp", "select", "video"}
# HTML separates class names by ASCII whitespace only; str.split() also splits on U+00A0 and other spaces.
ASCII_WHITESPACE = re.compile(r"[ \t\n\f\r]+")
SKIP_LINK = '<a class="skip" href="#main-content">Skip to content</a>'
COPY_STATUS = '<p class="vh" id="copy-status" role="status" aria-live="polite"></p>'
# The light and dark switch of template specification 7.33 (baseline 1.6.0), byte for byte as in the
# reference pages (reference/install.html line 18): the last child of header.mast on every page. Its 2
# glyphs are the only inline <svg> elements a page may carry; tools/check-inline-code.py admits exactly
# this string, once.
SCHEME_SWITCH = (
    '<button class="scheme" type="button" data-scheme-toggle aria-pressed="false" hidden>'
    '<svg class="moon" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7z"/></svg>'
    '<svg class="sun" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="4.2"/>'
    '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/>'
    '</svg><span class="vh">Dark mode</span></button>'
)
# The header block as mast() is meant to write it, held apart from mast() so that validate() refuses a change to
# either that the parsed reading misses: the markup is pinned here, and only the values come from site.json (the
# base path, name, tld, GitHub URL and nav pages, with aria-current on the page's own entry).
MAST_BLOCK = (
    '<header class="mast"><a class="brand" href="{base}"><span class="name">{name}<span class="tld">{tld}</span></span>'
    '<span class="rule" aria-hidden="true"></span></a><nav class="nav" aria-label="Site">{items}'
    '<a href="{github}" target="_blank" rel="noopener noreferrer">GitHub<span class="vh"> (opens in a new tab)</span></a>'
    "</nav>{switch}</header>"
)
MAST_ITEM = '<a href="{href}"{current}>{label}</a>'
# The dot between 2 links of the About row of template specification 7.24 (baseline 1.7.0); about_line() gives the row.
ABOUT_DOT = '<span class="dot" aria-hidden="true">&middot;</span>'
# The whole About block of specification 7.24 (baseline 1.7.0), byte for byte as SPECIFICATION.md section 7.24 gives
# it: the region, its label and the div around the About row, which about_line() gives. The generator writes it on the
# landing page only, directly after the end tag of the value paragraph's region, and validate() requires it there once.
ABOUT_BLOCK = '<div class="region"><p class="lbl">About this project</p><div>{row}</div></div>'
SLICE_COUNT = 6
# The checksum a version bump writes into site-src/release.json until the post-release flip sets the published one.
PLACEHOLDER_CHECKSUM = "0" * 64
# The verify page's download block in its source: steps 1 to 3, from the step 1 label to the end of the step 3 token
# (verify_download_block()).
VERIFY_SOURCE = SRC / "pages" / "verify.html"
DOWNLOAD_START = '<p class="lbl blk">Step 1</p>\n'
DOWNLOAD_END = "{{release.sum_compare}}"
# The verify page among the outputs of the / build (verify_page()).
VERIFY_OUTPUT = "verify/index.html"


class BuildError(Exception):
    """A refusal or a drift: exit 1."""


class Unreadable(Exception):
    """An input could not be read or is malformed: exit 3."""


# Reading inputs -------------------------------------------------------------

def read_text(root: Path, relative: Path | str) -> str:
    path = root / relative
    try:
        info = os.lstat(path)
    except OSError as error:
        raise Unreadable(f"{relative} could not be read: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise Unreadable(f"{relative} is not a regular file")
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        raise Unreadable(f"{relative} could not be read: {error}") from error


def read_json(root: Path, relative: Path) -> dict:
    try:
        value = json.loads(read_text(root, relative))
    except ValueError as error:
        raise Unreadable(f"{relative} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise Unreadable(f"{relative} is not a JSON object")
    return value


def skill_version(root: Path) -> str:
    for line in read_text(root, SKILL).splitlines():
        if line.startswith("Version:"):
            match = SKILL_VERSION.match(line)
            if match is None:
                raise Unreadable("the first Version: line of SKILL.md is not a bare X.Y.Z version")
            return match.group(1)
    raise Unreadable("SKILL.md has no Version: line")


def load_release(root: Path, override: dict | None = None, any_version: bool = False) -> dict:
    """Release values from site-src/release.json, or from ``override`` (the release writer's new values). With
    ``any_version`` (verify_page() for given values only), the version need not be the SKILL.md version."""
    release = override if override is not None else read_json(root, SRC / "release.json")
    version, tag, checksum = release.get("version"), release.get("tag"), release.get("checksum")
    if not isinstance(version, str) or not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", version):
        raise Unreadable(f"site-src/release.json version {version!r} is not X.Y.Z")
    if tag != f"v{version}":
        raise BuildError(f"site-src/release.json tag {tag!r} is not v{version}")
    if not isinstance(checksum, str) or not HEX64.match(checksum):
        raise BuildError("site-src/release.json checksum is not a 64 character lower-case SHA-256")
    expected = version if any_version else skill_version(root)
    if version != expected:
        raise BuildError(
            f"site-src/release.json names version {version}, but SKILL.md says {expected}; "
            "run tools/set-release-links.py for the release, never edit one without the other"
        )
    return release_tokens(version, tag, checksum)


def release_tokens(version: str, tag: str, checksum: str) -> dict:
    """The release.* tokens of these release values, which load_release() gives every page and
    verify_download_block() the verify page's download block."""
    zip_name = f"cleanlanguage-{version}.zip"
    zip_url = f"https://github.com/{REPO_SLUG}/releases/download/{tag}/{zip_name}"
    return {
        "release.version": version,
        "release.tag": tag,
        "release.checksum": checksum,
        "release.zip_name": zip_name,
        "release.zip_url": zip_url,
        "release.sum_url": f"{zip_url}.sha256",
        **sum_tokens(version, checksum, f"{zip_url}.sha256"),
    }


def sum_tokens(version: str, checksum: str, sum_url: str) -> dict:
    """The verify page's checksum wording in each state of release.json, which tools/check-release-links.py and
    tools/check-release-checksum-live.py read: the published checksum, its file and the step that compares them;
    or, while the checksum is the zero placeholder, a note that it appears once the version is published, with no
    value called the published checksum, no link to the checksum file and no step that rejects the download."""
    if checksum == PLACEHOLDER_CHECKSUM:
        return {
            "release.sum_lead": "",
            "release.sum_block": f'<p class="lbl size">zip, version {version}</p>'
                                 f"<p>The checksum for version {version} appears here once that version is published.</p>",
            "release.sum_compare": "",
        }
    return {
        "release.sum_lead": " The published checksum is shown under the link.",
        "release.sum_block": (
            f'<p class="lbl size">zip, version {version}, SHA-256</p><p>The published checksum for version {version} is:</p>'
            f'<code class="sum" id="published-checksum">{checksum}</code><p>The same value is in the '
            f"{external(sum_url, 'published checksum file')}, if you would rather compare files than read.</p>"
        ),
        "release.sum_compare": (
            '<p class="lbl blk">Step 3</p>\n'
            "<p>Compare the value your computer prints with the published checksum shown in step 1. Letter case does "
            "not matter: PowerShell prints the hash in upper case, while the published value is lower case, so compare "
            "the letters and digits and ignore the case. A match means your copy matches the published release.</p>\n"
            "<p>If the two differ, delete the file, download it again, and check once more. If the values still differ "
            "after a fresh download, do not install the file and "
            f"{external('https://github.com/jposluns/cleanlanguage/issues', 'report it on GitHub')}.</p>\n"
        ),
    }


def verify_download_block(root: Path, version: str, tag: str, checksum: str) -> str:
    """The verify page's download block, byte for byte as build() writes it for these release values: steps 1 to 3
    of site-src/pages/verify.html, from DOWNLOAD_START to the end of DOWNLOAD_END, with the release.* tokens
    replaced. tools/check-release-links.py and tools/check-release-checksum-live.py render it here and require it
    on the verify page exactly once."""
    source = read_text(root, VERIFY_SOURCE)
    start, end = source.find(DOWNLOAD_START), source.find(DOWNLOAD_END)
    if source.count(DOWNLOAD_START) != 1 or source.count(DOWNLOAD_END) != 1 or end < start:
        raise Unreadable(f"{VERIFY_SOURCE} does not hold the download block once, from its step 1 label to {DOWNLOAD_END}")
    return substitute(source[start:end + len(DOWNLOAD_END)], release_tokens(version, tag, checksum), str(VERIFY_SOURCE))


def verify_page(root: Path, release: dict | None = None, date: str | None = None) -> bytes:
    """The whole verify page, byte for byte as build() writes site/verify/index.html at base / from the sources under
    ``root`` and their site-src/release.json, or, given ``release`` (its version, tag and checksum), for those values,
    whatever version SKILL.md names; ``date`` replaces every page's modified date, as --date does.
    tools/check-release-links.py requires the committed page to equal the render for release.json, and
    tools/check-release-checksum-live.py the render for the version and checksum it reads from the page;
    tools/test-build-site.py pins the render for a stand-in release in each state (VERIFY_PAGE_PIN). Raises
    BuildError or Unreadable when build() does, for any page."""
    _, outputs, _ = build(root, "/", date, release, any_version=release is not None)
    return outputs[VERIFY_OUTPUT]


# Markdown subset for the skill's reference files ------------------------------

UNSUPPORTED_MARKDOWN = re.compile(r"\*\*|__|\]\(|^\s*[>|]|^\s*```|<", re.M)


def inline(text: str, where: str) -> str:
    """Escape a line of reference Markdown and turn `code` spans into <code>."""
    if UNSUPPORTED_MARKDOWN.search(text) or text.count("`") % 2:
        raise BuildError(f"{where}: unsupported Markdown in {text!r}; extend the generator before using it")
    parts = text.split("`")
    out = []
    for index, part in enumerate(parts):
        escaped = html.escape(part, quote=False)
        out.append(f"<code>{escaped}</code>" if index % 2 else escaped)
    return "".join(out)


def parse_sections(markdown: str, where: str) -> tuple[list[str], list[dict]]:
    """Split a reference file into its intro paragraphs and its ## sections.

    Each section holds an ordered list of blocks: ("p", text), ("ul", [items]),
    ("ol", [items]) or ("h3", heading).
    """
    intro: list[str] = []
    sections: list[dict] = []
    current: list | None = None
    lines = markdown.splitlines()
    index = 0
    seen_title = False
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("# "):
            if seen_title:
                raise BuildError(f"{where}: more than 1 title line")
            seen_title = True
            index += 1
            continue
        if line.startswith("## "):
            sections.append({"title": line[3:].strip(), "blocks": []})
            current = sections[-1]["blocks"]
            index += 1
            continue
        if line.startswith("### "):
            if current is None:
                raise BuildError(f"{where}: a ### heading before any ## section")
            current.append(("h3", line[4:].strip()))
            index += 1
            continue
        if line.startswith("- ") or re.match(r"^[0-9]+\. ", line):
            kind = "ul" if line.startswith("- ") else "ol"
            items = []
            while index < len(lines) and lines[index].strip():
                item = lines[index]
                if kind == "ul" and item.startswith("- "):
                    items.append(item[2:].strip())
                elif kind == "ol" and re.match(r"^[0-9]+\. ", item):
                    items.append(item.split(" ", 1)[1].strip())
                else:
                    raise BuildError(f"{where}: list continued by {item!r}")
                index += 1
            target = current if current is not None else None
            if target is None:
                raise BuildError(f"{where}: a list before any ## section")
            target.append((kind, items))
            continue
        if line.startswith("#"):
            raise BuildError(f"{where}: unsupported heading {line!r}")
        paragraph = []
        while index < len(lines) and lines[index].strip() and not lines[index].startswith(("#", "- ")):
            paragraph.append(lines[index].strip())
            index += 1
        text = " ".join(paragraph)
        if current is None:
            intro.append(text)
        else:
            current.append(("p", text))
    return intro, sections


def slug(prefix: str, title: str) -> str:
    return prefix + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def render_list(kind: str, items: list[str], where: str) -> str:
    return f"<{kind}>" + "".join(f"<li>{inline(item, where)}</li>" for item in items) + f"</{kind}>"


def render_clauses(sections: list[dict], where: str) -> str:
    """Render ## sections of bullet questions as numbered clauses (specification 7.22, the checklist page)."""
    out = []
    for number, section in enumerate(sections, start=1):
        anchor = slug("", section["title"])
        out.append(f'<p class="lbl sec">Section {number}</p>')
        out.append(f'<h2 class="clause" id="{anchor}"><span class="num">{number}</span><span>{inline(section["title"], where)}</span></h2>')
        if [kind for kind, _ in section["blocks"]] != ["ul"]:
            raise BuildError(f"{where}: section {section['title']!r} must be exactly 1 bullet list to render as clauses")
        items = section["blocks"][0][1]
        out.append(
            '<ol class="clauses">'
            + "".join(f'<li><span class="n">{number}.{index}</span><div><p>{inline(item, where)}</p></div></li>' for index, item in enumerate(items, start=1))
            + "</ol>"
        )
    return "\n".join(out)


def render_reference_sections(sections: list[dict], prefix: str, label: str, where: str) -> str:
    """Render ## sections of a reference file as labelled document sections."""
    out = []
    for number, section in enumerate(sections, start=1):
        anchor = slug(prefix, section["title"])
        out.append(f'<p class="lbl sec">{html.escape(label, quote=False)} {number}</p>')
        out.append(f'<h2 id="{anchor}">{inline(section["title"], where)}</h2>')
        for kind, value in section["blocks"]:
            if kind == "p":
                out.append(f"<p>{inline(value, where)}</p>")
            elif kind in ("ul", "ol"):
                out.append(render_list(kind, value, where))
            else:
                raise BuildError(f"{where}: unexpected ### heading {value!r} in {section['title']!r}")
    return "\n".join(out)


LABELS = {"Weak": "Before", "Source": "Source", "Preferred": "After"}


def render_examples(root: Path, commentary: dict) -> tuple[str, int]:
    where = str(REFS / "examples.md")
    _, sections = parse_sections(read_text(root, REFS / "examples.md"), where)
    unknown = set(commentary) - {s["title"] for s in sections}
    if unknown:
        raise BuildError(f"site-src/examples-commentary.json names sections examples.md does not have: {sorted(unknown)}")
    out = []
    for number, section in enumerate(sections, start=1):
        anchor = slug("ex-", section["title"])
        out.append(f'<p class="lbl sec">Example {number}</p>')
        out.append(f'<h2 id="{anchor}">{inline(section["title"], where)}</h2>')
        blocks: list[dict] = []
        pending_paragraphs: list[str] = []
        for kind, value in section["blocks"]:
            if kind == "h3":
                blocks.append({"heading": value, "paras": []})
            elif kind == "p":
                if blocks:
                    blocks[-1]["paras"].append(value)
                else:
                    pending_paragraphs.append(value)
            else:
                raise BuildError(f"{where}: a list inside example {section['title']!r}")
        for paragraph in pending_paragraphs:
            out.append(f"<p>{inline(paragraph, where)}</p>")
        extra = commentary.get(section["title"])
        if extra is not None and (not isinstance(extra, str) or "<" in extra or "{{" in extra):
            raise BuildError(f"site-src/examples-commentary.json: {section['title']!r} must be plain text")
        index = 0
        while index < len(blocks):
            block = blocks[index]
            if not block["paras"]:
                raise BuildError(f"{where}: ### {block['heading']} in {section['title']!r} has no text")
            if block["heading"].startswith("Preferred"):
                raise BuildError(f"{where}: ### {block['heading']} in {section['title']!r} has no example before it")
            afters = []
            index += 1
            while index < len(blocks) and blocks[index]["heading"].startswith("Preferred"):
                if not blocks[index]["paras"]:
                    raise BuildError(f"{where}: ### {blocks[index]['heading']} has no text")
                afters.append(blocks[index])
                index += 1
            before_label = html.escape(LABELS.get(block["heading"], block["heading"]), quote=False)
            if not afters:
                out.append(
                    f'<div class="wide"><div class="callout"><p class="lbl">{before_label}</p>'
                    f"<p>{inline(block['paras'][0], where)}</p></div></div>"
                )
                notes = block["paras"][1:]
            else:
                if len(block["paras"]) != 1:
                    raise BuildError(f"{where}: ### {block['heading']} has notes before its preferred version")
                after_html = "".join(
                    f'<p class="lbl">{html.escape(LABELS.get(a["heading"], a["heading"]), quote=False)}</p>'
                    f"<p>{inline(a['paras'][0], where)}</p>"
                    for a in afters
                )
                out.append(
                    f'<div class="wide"><div class="pair"><div class="before"><p class="lbl">{before_label}</p>'
                    f"<p>{inline(block['paras'][0], where)}</p></div>"
                    f'<div class="after">{after_html}</div></div></div>'
                )
                notes = [p for a in afters for p in a["paras"][1:]]
            if extra:
                # The site's own commentary follows the section's first pair, before the source's notes.
                out.append(f"<p>{html.escape(extra, quote=False)}</p>")
                extra = None
            for note in notes:
                out.append(f"<p>{inline(note, where)}</p>")
    return "\n".join(out), len(sections)


def load_pin(root: Path) -> tuple[str, set[str]]:
    """The baseline version and the pinned paths from .baseline/pin.toml, the one source of both."""
    try:
        pin = tomllib.loads(read_text(root, Path(".baseline/pin.toml")))
    except tomllib.TOMLDecodeError as error:
        raise Unreadable(f".baseline/pin.toml is not valid TOML: {error}") from error
    version, files = pin.get("version"), pin.get("files")
    if not isinstance(version, str) or not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", version):
        raise Unreadable(".baseline/pin.toml version is not X.Y.Z")
    if not isinstance(files, dict) or not files:
        raise Unreadable(".baseline/pin.toml pins no files")
    # Only the copied files under assets/baseline/ are served; the pinned build tool is not.
    return version, {path for path in files if path.startswith("assets/baseline/")}


def operating_mode_count(root: Path) -> int:
    text = read_text(root, SKILL)
    match = re.search(r"^## Select the operating mode\n(.*?)(?=^## )", text, re.S | re.M)
    if match is None:
        raise Unreadable("SKILL.md has no 'Select the operating mode' section")
    count = len(re.findall(r"^- \*\*[A-Z][a-z]+:\*\*", match.group(1), re.M))
    if count == 0:
        raise Unreadable("SKILL.md lists no operating modes")
    return count


# Page assembly ----------------------------------------------------------------

def page_date(page: dict, override: str | None) -> str | None:
    """The page's modified date: ``--date`` when given, else its ``modified`` entry in site.json."""
    return override if override is not None else page.get("modified")


def head(config: dict, page: dict, base: str, asset_tokens: dict, date: str | None) -> str:
    title = f"{page['title']} | {config['name']}{config['tld']}"
    lines = [
        "<!doctype html>",
        f'<html lang="en" class="{config["site_class"]}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
    ]
    draft = base != "/"
    if draft or page.get("noindex"):
        lines.append('<meta name="robots" content="noindex, nofollow">')
    lines.append(f"<title>{html.escape(title, quote=False)}</title>")
    if not draft and not page.get("noindex"):
        lines += promotion_metadata(config, page, page_date(page, date))
    key = config["site_key"]
    lines.append(f'<link rel="icon" href="{base}assets/baseline/logos/{key}-favicon.svg" type="image/svg+xml">')
    lines.append(f'<link rel="apple-touch-icon" href="{base}assets/baseline/logos/{key}-touch.png">')
    lines.append(f'<script data-cfasync="false" src="{base}assets/baseline/scheme.js?v={asset_tokens["baseline"]}"></script>')
    for sheet in ("fonts.css", "palettes.css", "baseline.css"):
        lines.append(f'<link rel="stylesheet" href="{base}assets/baseline/{sheet}?v={asset_tokens["baseline"]}">')
    if "site.css" in asset_tokens:
        lines.append(f'<link rel="stylesheet" href="{base}assets/site.css?v={asset_tokens["site.css"]}">')
    names = list(page["scripts"]) + (["rail.js"] if page.get("rail") == "list" else [])
    scripts = "".join(
        f'<script src="{base}assets/baseline/{name}?v={asset_tokens["baseline"]}" defer></script>'
        for name in names
    )
    if scripts:
        lines.append(scripts)
    lines.append("</head>")
    return "\n".join(lines)


def promotion_metadata(config: dict, page: dict, date: str | None) -> list[str]:
    """The metadata the page-metadata gate requires, emitted only at base /."""
    if not isinstance(date, str) or not DATE.match(date):
        raise BuildError(
            f"{page['source']}: the / build needs a modified date YYYY-MM-DD for article:modified_time; "
            f"set \"modified\" for page {page['id']!r} in site-src/site.json (found {date!r})"
        )
    published = page.get("published") or date
    if not DATE.match(published):
        raise BuildError(f"{page['source']}: published date {published!r} is not YYYY-MM-DD")
    url = f"{config['origin']}/{page['path']}"
    full_title = f"{page['title']} | {config['name']}{config['tld']}"
    description = page.get("description", "")
    person = {
        "@type": "Person",
        "@id": f"{config['origin']}/#jeffposluns",
        "name": config["author"],
        "url": config["author_url"],
        "sameAs": config["author_same_as"],
    }
    entity = {
        "@context": "https://schema.org",
        "@type": "CreativeWork" if page["id"] == "home" else "WebPage",
        "name": full_title,
        "url": url,
        "description": description,
        "license": "https://creativecommons.org/licenses/by-sa/4.0/",
        "datePublished": published,
        "dateModified": date,
        "author": person,
        "publisher": person,
    }
    esc = lambda value: html.escape(value, quote=True)  # noqa: E731
    return [
        f'<meta name="description" content="{esc(description)}">',
        f'<meta name="author" content="{esc(config["author"])}">',
        f'<link rel="canonical" href="{esc(url)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{esc(full_title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<meta property="og:site_name" content="{esc(config["name"] + config["tld"])}">',
        f'<meta property="og:image" content="{esc(config["card_image"])}">',
        f'<meta property="og:image:alt" content="{esc(config["card_image_alt"])}">',
        f'<meta property="article:published_time" content="{published}">',
        f'<meta property="article:modified_time" content="{date}">',
        f'<meta property="article:author" content="{esc(config["article_author"])}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(full_title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
        f'<meta name="twitter:image" content="{esc(config["card_image"])}">',
        f'<meta name="twitter:image:alt" content="{esc(config["card_image_alt"])}">',
        '<script type="application/ld+json">',
        json.dumps(entity, indent=2, ensure_ascii=False).replace("</", "<\\/"),
        "</script>",
    ]


def external(href: str, text: str) -> str:
    return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{text}{NEW_TAB}</a>'


def mast(config: dict, page: dict, base: str, pages_by_id: dict) -> str:
    items = []
    for page_id in config["nav"]:
        target = pages_by_id[page_id]
        current = ' aria-current="page"' if target["id"] == page["id"] else ""
        items.append(f'<a href="{base}{target["path"]}"{current}>{html.escape(target["nav_label"], quote=False)}</a>')
    items.append(external(config["github"], "GitHub"))
    return (
        f'<header class="mast"><a class="brand" href="{base}"><span class="name">{config["name"]}'
        f'<span class="tld">{config["tld"]}</span></span><span class="rule" aria-hidden="true"></span></a>'
        f'<nav class="nav" aria-label="Site">{"".join(items)}</nav>{SCHEME_SWITCH}</header>'
    )


def footer(config: dict, base: str) -> str:
    family = config["family"]
    keys = [site["key"] for site in family]
    if len(family) != SLICE_COUNT or config["site_key"] not in keys:
        raise Unreadable("site-src/site.json family must list the 6 sites, this one included")
    start = keys.index(config["site_key"])
    logos = f"{base}assets/baseline/logos"
    marks = f"{base}assets/baseline/marks"
    cards = []
    for offset in range(SLICE_COUNT):
        index = (start + offset) % SLICE_COUNT
        site = family[index]
        name = f'<span class="cname">{site["name"]}<span class="tld">.ai</span></span>'
        image = f'<img src="{logos}/{site["key"]}.svg" alt="">'
        if offset == 0:
            link = f'<a class="card" href="{base}" aria-current="page">{image}{name}<span class="vh"> (this site)</span></a>'
        else:
            link = (
                f'<a class="card" href="{site["url"]}" target="_blank" rel="noopener noreferrer">'
                f"{image}{name}{NEW_TAB}</a>"
            )
        cards.append(f'<li class="slice slice-{index + 1}">{link}</li>')
    tail = (
        '<ul class="tail" aria-label="Jeff Posluns elsewhere">'
        '<li class="tile tile-1"><a class="card" href="https://github.com/jposluns" target="_blank" rel="noopener noreferrer">'
        f'<img class="only-light" src="{marks}/github-invertocat-black.svg" alt="">'
        f'<img class="only-dark" src="{marks}/github-invertocat-white.svg" alt="">'
        f'<span class="cname vh">GitHub</span>{NEW_TAB}</a></li>'
        '<li class="tile tile-2"><a class="card" href="https://www.linkedin.com/in/jposluns/" target="_blank" rel="noopener noreferrer">'
        f'<img src="{marks}/linkedin-in-bug.png" alt=""><span class="cname vh">LinkedIn</span>{NEW_TAB}</a></li>'
        '<li class="tile tile-3"><a class="card" href="https://orcid.org/0009-0000-7775-2233" target="_blank" rel="noopener noreferrer">'
        f'<img src="{marks}/orcid-id.svg" alt=""><span class="cname vh">ORCID</span>{NEW_TAB}</a></li></ul>'
    )
    signature = (
        '<div class="tile sigtile"><a class="sig" href="https://posluns.ca/" target="_blank" rel="noopener noreferrer" '
        'aria-label="A Jeff at Posluns dot ca project: posluns.ca (opens in a new tab)"><span class="pre">A </span>'
        'Jeff<span class="gold">@</span>Posluns<span class="gold">.ca</span><span class="post"> Project</span></a></div>'
    )
    return (
        '<footer class="family wrap"><div class="bar"><ul class="cards rainbow" aria-label="The 6 project sites">'
        + "".join(cards)
        + "</ul>"
        + tail
        + signature
        + "</div></footer>"
    )


def rail(config: dict, page: dict, base: str, content: str) -> str:
    image = f'<img class="rail-logo" src="{base}assets/baseline/logos/{config["site_key"]}.svg" alt="{html.escape(config["logo_alt"])}">'
    if page.get("rail") != "list":
        return f'<div class="rail">{image}</div>'
    entries = H2_ID.findall(content)
    if len(entries) < 2:
        raise BuildError(f"{page['source']}: a list rail needs at least 2 h2 sections with ids")
    items = []
    for anchor, label in entries:
        # A numbered clause heading carries its number in <span class="num">; the rail lists the title only.
        text = " ".join(TAGS.sub("", re.sub(r'<span class="num">[^<]*</span>', "", label)).split())
        # No link is marked in the markup; rail.js marks the reader's section with aria-current="location".
        items.append(f'<li><a href="#{anchor}">{text}</a></li>')
    return f'<nav class="rail" aria-label="On this page">{image}<p class="lbl">On this page</p><ol>{"".join(items)}</ol></nav>'


def substitute(text: str, values: dict, where: str) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            raise BuildError(f"{where}: unknown token {{{{{name}}}}}")
        return values[name]

    result = TOKEN.sub(replace, text)
    if "{{" in result or "}}" in result:
        raise BuildError(f"{where}: an unreplaced or malformed token remains")
    return result


# Validation -------------------------------------------------------------------

class PageScan(HTMLParser):
    """The parsed reading validate() checks, which build() also reads on each page source. Not a full HTML5 tree
    builder: it models the open elements as tags nest, void elements, the slash only in <svg>, the head's end, class
    names split on ASCII whitespace, and the INERT_TAGS ancestors of each element with data-scheme-toggle, h1, robots
    meta and id, and of each element start validate() requires, the element starts that carry a hidden attribute or
    have an ancestor that does, where each value paragraph starts and where the region of the first one ends, where
    each element whose classes include about starts, and where the page's body starts. validate() also pins the
    markup from <body> to the end of header.mast, and the landing page's About block; --check compares the committed
    pages with a build that passed it."""

    def __init__(self, switch_at: tuple[int, int] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.h1 = 0
        self.problems: list[str] = []
        self.anchor: dict | None = None
        self.scripts: list[dict] = []
        # Where each script with a src, each stylesheet, and each element with data-scheme-toggle (the elements
        # scheme.js wires and shows) start: (line, column), as getpos() reports.
        self.loads: list[tuple[tuple[int, int], str]] = []
        self.sheets: list[tuple[int, int]] = []
        self.toggles: list[tuple[int, int]] = []
        # Whether an element with data-scheme-toggle, an h1 or a robots meta starts inside an element of INERT_TAGS;
        # the ids outside them, which a fragment may target; and where each element outside them starts.
        self.inert_toggle = False
        self.inert_h1 = False
        self.inert_robots = False
        self.live_ids: set[str] = set()
        self.live_starts: set[tuple[int, int]] = set()
        # Where each script and link starts outside the page's head: html > head, the first head or body opened,
        # until the head ends where HTML5 ends it.
        self.outside_head: set[tuple[int, int]] = set()
        self.heads = 0
        self.head_ended = False
        # Where the page's body starts: a body start tag in html right after the page's only head closes, with no
        # element or text between them, before the head ends.
        self.body_at: tuple[int, int] | None = None
        self.robots: list[str] = []
        # Where each element whose classes include about starts, inside an element of INERT_TAGS or not: on the
        # landing page, the row of the About block the generator writes; anywhere else, About markup.
        self.about_classes: list[tuple[int, int]] = []
        # Where each element that carries a hidden attribute (in any value), or has an open ancestor that does, starts,
        # and the depth in open of each such ancestor.
        self.hidden_starts: set[tuple[int, int]] = set()
        self.hiding: list[int] = []
        # Where each p.value starts; the depth in open of the first one's region, the div.region nearest it among its
        # open elements, while that region is open; and where the end tag of that region starts.
        self.values: list[tuple[int, int]] = []
        self.value_region: int | None = None
        self.value_region_end: tuple[int, int] | None = None
        # Each open element's name and classes, and the element that ended last (or a void one) since the last
        # start tag: the previous sibling of the next element.
        self.open: list[tuple[str, list[str]]] = []
        self.previous: tuple[str, list[str]] | None = None
        # The switch, the button that starts at switch_at: its parent, its previous sibling, its depth, and where
        # the end tag of its parent starts.
        self.switch_at = switch_at
        self.switch_parent: tuple[str, list[str]] | None = None
        self.switch_previous: tuple[str, list[str]] | None = None
        self.switch_depth = 0
        self.switch_parent_end: tuple[int, int] | None = None
        self.doc_closed = False
        self.in_main = False
        self.in_pre = 0

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k.lower(): (v or "") for k, v in attrs_list}
        if len(attrs) != len(attrs_list):
            # A browser reads the first of 2 attributes with the same name, and this dict the last.
            self.problems.append(f"<{tag}> carries an attribute twice")
        classes = [name for name in ASCII_WHITESPACE.split(attrs.get("class", "")) if name]
        if "about" in classes:
            self.about_classes.append(self.getpos())
        if (tag == "body" and [name for name, _ in self.open] == ["html"] and self.heads == 1 and not self.head_ended
                and self.previous is not None and self.previous[0] == "head"):
            self.body_at = self.getpos()
        if tag in ("head", "body"):
            self.heads += 1
        if tag not in HEAD_TAGS and tag not in ("html", "head"):
            self.head_ended = True
        if tag in ("script", "link") and ([name for name, _ in self.open] != ["html", "head"] or self.heads != 1
                                          or self.head_ended):
            self.outside_head.add(self.getpos())
        inert = any(name in INERT_TAGS for name, _ in self.open)
        if not inert:
            self.live_starts.add(self.getpos())
        if self.hiding or "hidden" in attrs:
            self.hidden_starts.add(self.getpos())
        if tag == "p" and "value" in classes:
            self.values.append(self.getpos())
            regions = [depth for depth, (name, names) in enumerate(self.open) if name == "div" and "region" in names]
            if len(self.values) == 1 and regions:
                self.value_region = regions[-1]
        if "data-scheme-toggle" in attrs:
            self.toggles.append(self.getpos())
            self.inert_toggle = self.inert_toggle or inert
        if tag == "button" and self.getpos() == self.switch_at:
            self.switch_parent = self.open[-1] if self.open else None
            self.switch_previous = self.previous
            self.switch_depth = len(self.open)
        self.previous = (tag, classes) if tag in VOID_TAGS else None
        if tag not in VOID_TAGS:
            self.open.append((tag, classes))
            if "hidden" in attrs:
                self.hiding.append(len(self.open) - 1)
        if self.doc_closed and self.in_main:
            self.problems.append(f"<{tag}> follows the end of .doc inside main; .doc closes early")
        if tag == "main":
            self.in_main = True
        if tag == "pre":
            self.in_pre += 1
        for name in attrs:
            if name.startswith("on"):
                self.problems.append(f"an {name} attribute on <{tag}>")
            if name == "style":
                self.problems.append(f"an inline style attribute on <{tag}>")
        if tag == "style":
            self.problems.append("a <style> element")
        if "id" in attrs:
            self.ids.append(attrs["id"])
            if not inert:
                self.live_ids.add(attrs["id"])
        if tag == "h1":
            self.h1 += 1
            self.inert_h1 = self.inert_h1 or inert
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots.append(attrs.get("content", ""))
            self.inert_robots = self.inert_robots or inert
        if tag == "script":
            self.scripts.append(attrs)
            if "src" in attrs:
                self.loads.append((self.getpos(), attrs["src"]))
        if tag == "link" and "stylesheet" in attrs.get("rel", "").lower().split():
            self.sheets.append(self.getpos())
        canonical = tag == "link" and attrs.get("rel") == "canonical"
        for name in ("href", "src"):
            if name in attrs and not canonical:
                self.links.append((tag, attrs[name]))
        if tag == "a" and attrs.get("href", "").startswith(("http://", "https://")):
            self.anchor = {"href": attrs["href"], "attrs": attrs, "text": ""}

    def handle_startendtag(self, tag, attrs):
        # A browser honours the slash only in <svg> (foreign content); any other element that is not void stays open.
        foreign = tag == "svg" or any(name == "svg" for name, _ in self.open)
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and foreign:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if data.strip(" \t\n\f\r") and [name for name, _ in self.open] in ([], ["html"], ["html", "head"]):
            # Text other than whitespace in or before the head ends it (HTML5).
            self.head_ended = True
        if self.anchor is not None:
            self.anchor["text"] += data
        if self.in_pre and re.search(r"</?[a-z][a-z0-9]*[\s>]", data):
            self.problems.append("tag text such as <code> shown inside a <pre> block")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("body", "html", "br"):
            # HTML5 ends the head at each of these end tags (</br> reads as <br>).
            self.head_ended = True
        if tag in VOID_TAGS:
            return
        if not self.open or self.open[-1][0] != tag:
            self.problems.append(f"</{tag}> does not close the open element {self.open[-1][0] if self.open else 'none'}")
        else:
            self.previous = self.open.pop()
            if tag == "div" and "doc" in self.previous[1]:
                self.doc_closed = True
            if len(self.open) == self.value_region:
                self.value_region, self.value_region_end = None, self.getpos()
            while self.hiding and self.hiding[-1] >= len(self.open):
                self.hiding.pop()
            if self.switch_parent is not None and self.switch_parent_end is None and len(self.open) < self.switch_depth:
                self.switch_parent_end = self.getpos()
        if tag == "main":
            self.in_main = False
        if tag == "pre":
            self.in_pre -= 1
        if tag == "a" and self.anchor is not None:
            attrs = self.anchor["attrs"]
            label = self.anchor["text"] + attrs.get("aria-label", "")
            if attrs.get("target") != "_blank" or attrs.get("rel") != "noopener noreferrer" or "(opens in a new tab)" not in label:
                self.problems.append(f"the external link {self.anchor['href']} lacks target, rel or the new-tab text")
            self.anchor = None


def line_column(text: str, index: int) -> tuple[int, int]:
    """The (line, column) of index in text, as HTMLParser.getpos() reports where a tag starts."""
    return text.count("\n", 0, index) + 1, index - text.rfind("\n", 0, index) - 1


def pinned_mast(config: dict, page: dict, base: str) -> str:
    """The header block MAST_BLOCK pins for 1 page, with the values site.json gives."""
    pages_by_id = {entry["id"]: entry for entry in config["pages"]}
    items = "".join(
        MAST_ITEM.format(href=base + pages_by_id[page_id]["path"], current=' aria-current="page"' if page_id == page["id"]
                         else "", label=html.escape(pages_by_id[page_id]["nav_label"], quote=False))
        for page_id in config["nav"]
    )
    return MAST_BLOCK.format(base=base, name=config["name"], tld=config["tld"], items=items, github=config["github"],
                             switch=SCHEME_SWITCH)


def about_line(base: str) -> str:
    """The landing page's About row at base, as specification 7.24 (baseline 1.7.0) gives it: 1 ordinary space
    after each dot span and none before it, so a line breaks only after a dot."""
    links = (f'<a href="{base}disclosure/">Disclosure</a>', f'<a href="{base}license/">Licence</a>',
             f'<a href="https://posluns.ca/privacy/" target="_blank" rel="noopener noreferrer">Privacy{NEW_TAB}</a>',
             f'<a href="https://posluns.ca/security/" target="_blank" rel="noopener noreferrer">Security{NEW_TAB}</a>')
    return '<p class="about">' + (ABOUT_DOT + " ").join(links) + "</p>"


def about_block(base: str) -> str:
    """The landing page's whole About block at base: ABOUT_BLOCK around about_line(), as specification 7.24 gives it."""
    return ABOUT_BLOCK.format(row=about_line(base))


def with_about(content: str, page: dict, base: str) -> str:
    """A page's content with, on the landing page only, the About block of specification 7.24 written in directly
    after the end tag of the value paragraph's region. It refuses a source with an element whose classes include
    about, and a landing page source without exactly 1 p.value, with that p.value inside an element of INERT_TAGS,
    carrying a hidden attribute or inside an element with one, or with no div.region among its ancestors."""
    where = page["source"]
    scan = PageScan()
    scan.feed(content)
    scan.close()
    if scan.about_classes:
        raise BuildError(f"{where}: an element whose classes include about; the generator writes the About block of "
                         "specification 7.24 itself, on the landing page only")
    if page["path"] != "":
        return content
    if len(scan.values) != 1 or scan.values[0] not in scan.live_starts or scan.values[0] in scan.hidden_starts:
        raise BuildError(f"{where}: the landing page source must carry exactly 1 p.value, with no hidden attribute, "
                         "outside every element of INERT_TAGS and every element with a hidden attribute; the About "
                         "block goes after its region")
    if scan.value_region_end is None:
        raise BuildError(f"{where}: the value paragraph has no enclosing div.region, after which the About block goes")
    line, column = scan.value_region_end
    # The index of that end tag in content: the lines before it, each with its "\n", then the column.
    end = sum(len(part) + 1 for part in content.split("\n")[:line - 1]) + column
    at = content.index(">", end) + 1
    return content[:at] + about_block(base) + content[at:]


def validate(page_html: str, page: dict, config: dict, base: str) -> PageScan:
    where = page["source"]
    problems = []
    if 'aria-current="true"' in page_html:
        problems.append('a static aria-current="true"; the rail is marked by rail.js')
    if "\u2013" in page_html or "\u2014" in page_html:
        problems.append("an en or em dash")
    if re.search(r"what this is", TAGS.sub(" ", page_html), re.I):
        problems.append('"what this is" framing')
    switch = page_html.find(SCHEME_SWITCH)
    scan = PageScan(line_column(page_html, switch) if switch != -1 else None)
    scan.feed(page_html)
    scan.close()
    # Each required block starts as a parsed element outside every element of INERT_TAGS.
    for required in (SKIP_LINK, '<main id="main-content">', '<footer class="family wrap">', COPY_STATUS):
        if page_html.count(required) != 1 or line_column(page_html, page_html.find(required)) not in scan.live_starts:
            problems.append(f"{required!r} must appear exactly once, outside every element of INERT_TAGS")
    # The switch is the only parsed element with data-scheme-toggle; the element it sits in and the one before it;
    # the end tag of its parent starts where it ends.
    parent, previous = scan.switch_parent or ("", []), scan.switch_previous or ("", [])
    if (page_html.count(SCHEME_SWITCH) != 1 or scan.toggles != [line_column(page_html, switch)] or scan.inert_toggle
            or parent[0] != "header" or "mast" not in parent[1]
            or previous[0] != "nav" or "nav" not in previous[1]
            or scan.switch_parent_end != line_column(page_html, switch + len(SCHEME_SWITCH))):
        problems.append("the light and dark switch must appear exactly once, as the last child of header.mast, after nav.nav, "
                        "outside every element of INERT_TAGS, and no other element may carry data-scheme-toggle")
    # The page's body opens with the skip link and the header block, each on its own line as the generator writes
    # them, so no element wraps header.mast and only the skip link precedes it in the body.
    block = pinned_mast(config, page, base)
    top = "<body>\n" + SKIP_LINK + "\n" + block
    if (page_html.count(block) != 1 or page_html.count(top) != 1
            or line_column(page_html, page_html.find(top)) != scan.body_at):
        problems.append("the header block is not, once and byte for byte, the header.mast markup MAST_BLOCK pins, "
                        "after the skip link at the start of the page's body")
    if re.search(r"<svg", page_html.replace(SCHEME_SWITCH, "", 1), re.I):
        problems.append("an inline <svg> other than the light and dark switch")
    scheme_tags = {line_column(page_html, match.start()) for match in re.finditer(
        r'<script data-cfasync="false" src="' + re.escape(base)
        + r'assets/baseline/scheme\.js\?v=[0-9]+\.[0-9]+\.[0-9]+"></script>', page_html)}
    # Each script element that loads scheme.js, read with character references decoded and names in lower
    # case, so another spelling of a second load counts; PageScan refuses a tag that carries an attribute
    # twice, and resolve_links refuses a root-relative src that names no generated, pinned or allowlisted
    # path, such as a percent-encoded one.
    scheme_loads = [at for at, src in scan.loads
                    if src.split("#", 1)[0].split("?", 1)[0] == base + "assets/baseline/scheme.js"]
    if len(scheme_loads) != 1 or scheme_loads[0] not in scheme_tags or page_html.count("scheme.js") != 1:
        problems.append("scheme.js must load exactly once, with data-cfasync=\"false\" and no defer")
    elif not scan.sheets or scan.sheets[0] < scheme_loads[0]:
        problems.append("scheme.js must load before the first stylesheet")
    elif scheme_loads[0] in scan.outside_head or any(at in scan.outside_head for at in scan.sheets):
        problems.append("scheme.js and every stylesheet must load inside <head>")
    problems += scan.problems
    if scan.open:
        problems.append(f"elements left open: {[tag for tag, _ in scan.open]}")
    if scan.h1 != 1 or scan.inert_h1:
        problems.append(f"{scan.h1} h1 elements; exactly 1 is required, outside every element of INERT_TAGS")
    duplicates = sorted({i for i in scan.ids if scan.ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate ids {duplicates}")
    for attrs in scan.scripts:
        kind = attrs.get("type", "").strip().lower()
        if "src" not in attrs and kind in EXECUTABLE_TYPES:
            problems.append("an inline executable <script>")
        if kind == "application/ld+json" and base != "/":
            problems.append("a JSON-LD block on a draft page")
        elif kind == "application/ld+json" and page.get("noindex"):
            problems.append("a JSON-LD block on a noindex page")
    if base != "/" and scan.robots != ["noindex, nofollow"]:
        problems.append("a draft page must carry exactly 1 robots meta, noindex, nofollow")
    elif base == "/" and page.get("noindex") and scan.robots != ["noindex, nofollow"]:
        problems.append("a noindex page must carry exactly 1 robots meta, noindex, nofollow")
    elif base == "/" and not page.get("noindex") and scan.robots:
        problems.append("an indexable page carries a robots meta")
    if scan.inert_robots:
        problems.append("a robots meta inside an element of INERT_TAGS")
    allow = set(config["root_allowlist"])
    if page["id"] not in config["about_linkers"]:
        for tag, value in scan.links:
            if tag == "a" and any(value.split("#", 1)[0] == base + config_path for config_path in config["about_paths"]):
                problems.append(f"{value} links a page only the landing page links (specification 7.24)")
    # On the landing page, exactly 1 p.value starts as a parsed element outside every element of INERT_TAGS, as the
    # required blocks do, carries no hidden attribute and starts outside every element with one; the whole About
    # block, once and byte for byte, starts where the end tag of its region ends, so the block's ancestors are the
    # region's, none of which is an element of INERT_TAGS or carries a hidden attribute, and ABOUT_BLOCK holds
    # neither. The block's row is then the only parsed element whose classes include about. On any other page, no
    # such element appears, inside an element of INERT_TAGS or not. The label is read only as part of the block.
    if page["path"] == "":
        block, value = about_block(base), scan.values[0] if len(scan.values) == 1 else None
        at = page_html.find(block)
        if (value is None or value not in scan.live_starts or value in scan.hidden_starts
                or page_html.count(block) != 1 or not page_html.startswith("</div>", at - len("</div>"))
                or line_column(page_html, at - len("</div>")) != scan.value_region_end
                or len(scan.about_classes) != 1):
            problems.append("the About block must appear exactly once, byte for byte as specification 7.24 gives it "
                            "(ABOUT_BLOCK), directly after the end tag of the region of the only p.value, which "
                            "carries no hidden attribute and starts outside every element of INERT_TAGS and every "
                            "element with a hidden attribute, and no other About markup may appear")
    elif scan.about_classes:
        problems.append("About markup (an element whose classes include about), which only the landing page's About "
                        "block carries (specification 7.24)")
    for tag, value in scan.links:
        if value.startswith(("https://", "http://")):
            if tag != "a":
                problems.append(f"<{tag}> loads an external resource {value}")
            continue
        if value.startswith("#"):
            if value[1:] not in scan.live_ids:
                problems.append(f"the in-page link {value} has no target outside every element of INERT_TAGS")
            continue
        if value.startswith("/"):
            path = value.split("#", 1)[0].split("?", 1)[0]
            if path in allow and tag == "a":
                continue
            if not value.startswith(base):
                problems.append(f"{value} is outside the base path {base}")
            continue
        problems.append(f"{value!r} is neither a base-path link nor an external link")
    if problems:
        raise BuildError(f"{where}: " + "; ".join(problems))
    return scan


# Build ------------------------------------------------------------------------

def out_dir_for(base: str) -> Path:
    if base == "/":
        return Path("site")
    if not re.match(r"^/[a-z0-9-]+/$", base):
        raise Unreadable(f"base {base!r} must be / or a single folder such as /draft/")
    return Path("site") / base.strip("/")


def check_sitemap_exclusion(root: Path, base: str, pages: list) -> None:
    """The page-metadata and sitemap gates read */index.html, so each noindex page there must be excluded.

    While a draft is staged, tools/sitemap-config.json must exclude the draft's home page
    (recorded exclusion E1). At base /, it must exclude exactly the noindex pages whose output
    is a */index.html (the /draft/ holding page), so every indexable page is checked and no
    noindex page is.
    """
    config = read_json(root, Path("tools/sitemap-config.json"))
    exclude = config.get("exclude")
    if not isinstance(exclude, list):
        raise Unreadable("tools/sitemap-config.json has no exclude list")
    stray = [entry for entry in exclude if isinstance(entry, str) and entry.endswith("/index.html") and entry != "404.html"]
    if base == "/":
        wanted = sorted(
            page["path"] + "index.html"
            for page in pages
            if page.get("noindex") and page["path"].endswith("/") and page["path"].count("/") == 1
        )
    else:
        wanted = [base.strip("/") + "/index.html"]
    if sorted(stray) != wanted:
        raise BuildError(
            f"tools/sitemap-config.json excludes {sorted(stray)}, but base {base} needs exactly {wanted}; "
            "a noindex page that the gates would read as */index.html is excluded, and no other page is"
        )


def static_files(config: dict) -> list[str]:
    """The files committed by hand beside the generated ones at site/ (site.json static_files)."""
    listed = config.get("static_files", [])
    if not isinstance(listed, list) or not all(isinstance(name, str) and name for name in listed):
        raise Unreadable("site-src/site.json static_files must be a list of file paths")
    if len(set(listed)) != len(listed):
        raise Unreadable("site-src/site.json static_files lists a file twice")
    for name in listed:
        parts = name.split("/")
        if name.startswith("/") or "" in parts or "." in parts or ".." in parts or name.startswith("assets/baseline/"):
            raise Unreadable(f"site-src/site.json static_files entry {name!r} is not a plain path under site/")
    return listed


def file_kb(root: Path, name: str) -> str:
    path = root / DOWNLOADS / name
    try:
        size = os.stat(path).st_size
    except OSError as error:
        raise Unreadable(f"{DOWNLOADS / name} could not be read: {error}") from error
    return f"{round(size / 1000)} KB"


def build(
    root: Path,
    base: str | None = None,
    date: str | None = None,
    release: dict | None = None,
    config: dict | None = None,
    any_version: bool = False,
) -> tuple[Path, dict[str, bytes], dict]:
    """Render every output file in memory.

    ``release`` replaces site-src/release.json and ``config`` replaces site-src/site.json when
    given (the release writer's new values, before it writes them). ``any_version`` lets the
    release name a version other than SKILL.md's (verify_page() for given values only).
    """
    if config is None:
        config = read_json(root, SRC / "site.json")
    elif not isinstance(config, dict):
        raise Unreadable("the site.json override is not a JSON object")
    base = base or config.get("base")
    if not isinstance(base, str):
        raise Unreadable("site-src/site.json has no base")
    out = out_dir_for(base)
    pages = config.get("pages")
    if not isinstance(pages, list) or not pages:
        raise Unreadable("site-src/site.json lists no pages")
    for page in pages:
        modified = page.get("modified")
        if modified is not None and (not isinstance(modified, str) or not DATE.match(modified)):
            raise Unreadable(f"site-src/site.json page {page.get('id')!r} modified {modified!r} is not YYYY-MM-DD")
    if date is not None and not DATE.match(date):
        raise BuildError(f"--date {date!r} is not YYYY-MM-DD")
    check_sitemap_exclusion(root, base, pages)
    statics = static_files(config) if out == Path("site") else []
    release = load_release(root, release, any_version)
    baseline_version, pinned = load_pin(root)
    config["pinned"] = pinned
    asset_tokens = {"baseline": baseline_version}
    outputs: dict[str, bytes] = {}
    if (root / SRC / "assets" / "site.css").exists():
        site_css = read_text(root, SRC / "assets" / "site.css")
        asset_tokens["site.css"] = hashlib.sha256(site_css.encode("utf-8")).hexdigest()[:12]
        outputs["assets/site.css"] = site_css.encode("utf-8")
    commentary = read_json(root, SRC / "examples-commentary.json")
    examples_html, example_count = render_examples(root, commentary)
    _, channel_sections = parse_sections(read_text(root, REFS / "context-modes.md"), str(REFS / "context-modes.md"))
    _, checklist_sections = parse_sections(read_text(root, REFS / "qa-checklist.md"), str(REFS / "qa-checklist.md"))
    instructions = read_text(root, DOWNLOADS / "cleanlanguage.md").rstrip("\n")
    # Each AI family has its own setup page under install/; the home page counts them.
    families = sum(1 for page in pages if str(page.get("path", "")).startswith("install/") and page.get("path") != "install/")
    if families == 0:
        raise BuildError("site-src/site.json lists no family install pages under install/; the home page would read 0 assistants")
    values = {
        "base": base,
        **release,
        "size.full": file_kb(root, "cleanlanguage.md"),
        "chars.full": str(len(instructions)),
        "count.examples": str(example_count),
        "count.channels": str(len(channel_sections)),
        "count.modes": str(operating_mode_count(root)),
        "count.families": str(families),
        "examples": examples_html,
        "channels": render_reference_sections(channel_sections, "", "Channel", str(REFS / "context-modes.md")),
        "checklist": render_clauses(checklist_sections, str(REFS / "qa-checklist.md")),
        "instructions": html.escape(instructions, quote=False),
    }
    pages_by_id = {page["id"]: page for page in pages}
    for page_id in config.get("nav", []):
        if page_id not in pages_by_id:
            raise Unreadable(f"site-src/site.json nav names unknown page {page_id!r}")
    scans: dict[str, PageScan] = {}
    the_footer = footer(config, base)
    for page in pages:
        fragment = read_text(root, SRC / "pages" / page["source"])
        content = substitute(fragment, values, page["source"])
        content = content.replace("<!--rail-->", rail(config, page, base, content))
        content = with_about(content, page, base)
        document = "\n".join(
            [
                head(config, page, base, asset_tokens, date),
                "<body>",
                SKIP_LINK,
                mast(config, page, base, pages_by_id),
                '<main id="main-content">',
                f'<div class="wrap">{content.strip()}</div>',
                "</main>",
                the_footer,
                COPY_STATUS,
                "</body>",
                "</html>",
                "",
            ]
        )
        scans[page["path"]] = validate(document, page, config, base)
        name = page["path"] + "index.html" if not page["path"].endswith(".html") else page["path"]
        outputs[name] = document.encode("utf-8")
    clashes = sorted(set(statics) & set(outputs))
    if clashes:
        raise BuildError(f"site-src/site.json static_files names generated files {clashes}")
    config["static_files_in_out"] = statics
    resolve_links(root, out, base, config, outputs, scans)
    return out, outputs, config


def resolve_links(root: Path, out: Path, base: str, config: dict, outputs: dict, scans: dict) -> None:
    """Every internal link resolves to a generated page and anchor, a pinned baseline file or an allowlisted root file."""
    ids_by_file = {}
    for path, scan in scans.items():
        name = path + "index.html" if not path.endswith(".html") else path
        ids_by_file[name] = scan.live_ids
    problems = []
    for path, scan in scans.items():
        for tag, value in scan.links:
            if not value.startswith("/"):
                continue
            target, _, fragment = value.partition("#")
            target = target.split("?", 1)[0]
            if target in config["root_allowlist"]:
                if not (root / "site" / target.lstrip("/")).is_file():
                    problems.append(f"{path or 'index'}: allowlisted root file {target} does not exist")
                continue
            relative = target[len(base):]
            name = relative + "index.html" if relative == "" or relative.endswith("/") else relative
            if name in outputs:
                if fragment and fragment not in ids_by_file.get(name, set()):
                    problems.append(f"{path or 'index'}: {value} names an anchor the target page lacks")
                continue
            if name in config["pinned"]:
                continue  # a pinned baseline file; tools/check-baseline-pin.py checks it on disk
            problems.append(f"{path or 'index'}: {value} does not resolve inside {base}")
    if problems:
        raise BuildError("; ".join(problems))


def existing_files(directory: Path) -> list[str]:
    found = []
    if not directory.exists():
        return found
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            raise Unreadable(f"{current} could not be listed: {error}") from error
        for entry in entries:
            relative = Path(entry.path).relative_to(directory).as_posix()
            if relative == "assets/baseline":
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            else:
                found.append(relative)
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the site on the shared template.")
    parser.add_argument("--check", action="store_true", help="compare the committed output with a fresh build")
    parser.add_argument("--base", help="override the base path (/ renders the promotion build)")
    parser.add_argument("--out", help="write into this folder instead (with --base, for tests)")
    parser.add_argument("--date", help="replace every page's modified date in the / build, YYYY-MM-DD")
    parser.add_argument("--promote", action="store_true", help="allow a --base / build to write into site/ while site.json names another base")
    parser.add_argument("--root", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else REPO_ROOT
    try:
        out, outputs, config = build(root, args.base, args.date)
        target = Path(args.out) if args.out else root / out
        if args.check:
            if args.out or args.base:
                raise BuildError("--check compares the configured base path's committed output only")
            present = existing_files(target)
            statics = config["static_files_in_out"]
            problems = [f"{out / name} is listed in static_files but missing" for name in statics if name not in present]
            for name in sorted(set(present) | set(outputs)):
                if name in statics:
                    continue
                if name not in outputs:
                    problems.append(f"{out / name} is not generated or listed in static_files; remove it or add it to the sources")
                elif name not in present:
                    problems.append(f"{out / name} is missing; run tools/build-site.py")
                elif (target / name).read_bytes() != outputs[name]:
                    problems.append(f"{out / name} differs from a fresh build; run tools/build-site.py")
            if problems:
                print("Generated site problems found:")
                for problem in problems:
                    print(f"  - {problem}")
                return 1
            print(
                f"The committed {out}/ matches a fresh build ({len(outputs)} files, beside {len(statics)} listed static files) "
                f"and every internal link resolves inside {config['base']}."
            )
            return 0
        if out == Path("site") and not args.out and config.get("base") != "/" and not args.promote:
            raise BuildError(
                f"refusing to write the / build into site/ while site-src/site.json names base {config.get('base')!r}, without --promote"
            )
        for name, data in outputs.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        removed = [name for name in existing_files(target) if name not in outputs] if not args.out and out != Path("site") else []
        for name in removed:
            (target / name).unlink()
        print(f"wrote {len(outputs)} files to {target}" + (f" and removed {len(removed)} stale files" if removed else ""))
        return 0
    except BuildError as error:
        print(f"build-site: {error}", file=sys.stderr)
        return 1
    except Unreadable as error:
        print(f"build-site: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
