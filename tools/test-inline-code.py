#!/usr/bin/env python3
"""Tests for tools/check-inline-code.py.

Each case copies the gate and every HTML page and SVG file under site/ into a
temporary repository (under $TMPDIR), applies 1 fault to 1 file, runs the gate
there as a separate process and asserts its exit code (and, for the switch
rules in ``SWITCH_RULES``, that the refusal names the switch's place). The cases named I1 to I7,
I2 and I2B are the inline-code mutants of the PR 206 review, and the cases named
N1, N2 and N4 are the probes of its first verification round. Exit 0 when every case passes;
1 otherwise, naming each failing case. Two further cases run the gate under a
faked Python version tuple, 1 below and 1 above its supported set, with the 17
entry points that the comment above ``VERSION_PROBE`` names replaced by a
function that exits 97, and assert exit 3, no stdout and 1 stderr line naming
the supported version and the faked one, so a guard placed after a result is
printed fails them. The probe replaces these 17 attributes (14 of modules, 3 of
the class pathlib.Path) with a function that writes 1 line to stderr if it can
and then exits 97, so a version guard placed after the point where the gate,
directly or inside another function, looks up one of these attributes and calls
it, fails both cases. It makes no claim about any other file access. Two more
cases each put 1 read, through ``os.open`` or through ``io.FileIO``, before the
version check in the gate's main() and assert that the probe stops it with
exit 97.
SUPPORTED_PYTHONS in the gate must equal the one here exactly.
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-inline-code.py"
HOME = "site/index.html"
INSTALL = "site/install/index.html"
INSTRUCTIONS = "site/instructions/index.html"
LICENSE = "site/license/index.html"
VERIFY = "site/verify/index.html"
HOLDING = "site/draft/index.html"
FAVICON = "site/assets/baseline/logos/cleanlanguage-favicon.svg"
DEMO = "site/demo/index.html"
IMG = '<img src="x" onerror="alert(1)">'
# The versions the gate must run on, kept here apart from the gate, and a faked version tuple below and above them.
SUPPORTED_PYTHONS = ((3, 14),)
VERSION_PROBES = [(3, 13, 9, "final", 0), (3, 15, 0, "final", 0)]
# Runs the gate (argv[2]) under the faked version tuple in argv[1]. It imports what the gate imports and compiles the
# gate first, then replaces these 17 entry points with a function that exits 97: os.walk, os.scandir, os.listdir,
# os.open, builtins.open, io.open, io.open_code, io.FileIO, _io.open, _io.open_code, _io.FileIO, posix.scandir,
# posix.listdir, posix.open, pathlib.Path.read_text, pathlib.Path.read_bytes and pathlib.Path.open. The _io and posix
# ones are those pathlib reaches (pathlib.io._io, pathlib._os.posix). The probe replaces these 17 attributes (14 of
# modules, 3 of the class pathlib.Path) with a function that writes 1 line to stderr if it can and then exits 97, so
# a version guard placed after the point where the gate, directly or inside another function, looks up one of these
# attributes and calls it, fails the case. It makes no claim about any other file access.
VERSION_PROBE = (
    "import __future__, _io, builtins, io, os, pathlib, platform, posix, re, sys, html.parser, xml.parsers.expat\n"
    "def trap(*args, **kwargs):\n"
    "    try:\n"
    "        os.write(2, b'the gate listed or read a file before its version check\\n')\n"
    "    finally:\n"
    "        os._exit(97)\n"
    "with io.open_code(sys.argv[2]) as source:\n"
    "    code = compile(source.read(), sys.argv[2], 'exec')\n"
    "os.walk = os.scandir = os.listdir = os.open = builtins.open = trap\n"
    "io.open = io.open_code = io.FileIO = _io.open = _io.open_code = _io.FileIO = trap\n"
    "posix.scandir = posix.listdir = posix.open = trap\n"
    "pathlib.Path.read_text = pathlib.Path.read_bytes = pathlib.Path.open = trap\n"
    "sys.version_info = tuple(int(part) if part.isdigit() else part for part in sys.argv[1].split())\n"
    "exec(code, {'__name__': '__main__', '__file__': sys.argv[2], '__builtins__': builtins})\n"
)
# Reads put before the version check in the gate's main(); the probe must stop each with exit 97.
READ_MUTANTS = [
    ("os.open", "fd = os.open(__file__, os.O_RDONLY); os.read(fd, 1); os.close(fd)"),
    ("io.FileIO", "import io; io.FileIO(__file__).read(1)"),
]
TRAPPED = "the gate listed or read a file before its version check"
# The sha256 of the light and dark switch of template specification 7.33, computed from the 1.6.0
# reference page reference/install.html line 18 (761 bytes, from <button class="scheme" to </button>).
SWITCH_SHA256 = "9cbd502757bf584b5b83c5319729a9f33310682f305597b64347bc263f586f00"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_inline_code", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate_switch() -> str:
    return load_gate().SCHEME_SWITCH


SWITCH_HEAD = '<button class="scheme" type="button" data-scheme-toggle aria-pressed="false" hidden><svg class="moon" '
SWITCH = gate_switch()
# A second working switch: scheme.js wires and shows every element with data-scheme-toggle.
TOGGLE = '<p><button class="scheme" type="button" data-scheme-toggle hidden><span class="vh">Dark mode</span></button></p>'


def duplicate_switch(relative: str):
    """Write the page's own switch a second time, right after the first."""
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        start = text.index(SWITCH_HEAD)
        end = text.index("</button>", start) + len("</button>")
        path.write_text(text[:end] + text[start:end] + text[end:], encoding="utf-8")
    return apply


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(GATE, root / "tools" / GATE.name)
    pages = list((REPO_ROOT / "site").rglob("*.htm*")) + list((REPO_ROOT / "site").rglob("*.svg"))
    for page in sorted(pages):
        target = root / page.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(page, target)
    return root


def edit(relative: str, old: str, new: str):
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(f"{old!r} is not in {relative}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return apply


def before_main_end(relative: str, markup: str):
    return edit(relative, "</main>", markup + "</main>")


def write_bytes(relative: str, data: bytes):
    return lambda root: (root / relative).write_bytes(data)


def write_text(relative: str, text: str):
    def apply(root: Path) -> None:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text, encoding="utf-8")
    return apply


def both(*faults):
    def apply(root: Path) -> None:
        for fault in faults:
            fault(root)
    return apply


def svg_with(markup: str):
    return edit(FAVICON, "</svg>", markup + "</svg>")


def remove_pages(root: Path) -> None:
    for page in (root / "site").rglob("*.htm*"):
        page.unlink()


JSON_LD = '<script type="application/ld+json">{"@context": "https://schema.org"}</script>'

CASES = [
    ("the committed tree", None, 0),
    ("I1: an application/x-javascript script on the install page",
        before_main_end(INSTALL, '<script type="application/x-javascript">alert(1)</script>'), 1),
    ("I2: a script with src that also holds code",
        before_main_end(INSTALL, '<script src="x">alert(1)</script>'), 1),
    ("I2B: src= inside another attribute's quoted value",
        before_main_end(INSTALL, "<script title='src=\"/install/\"'>alert(1)</script>"), 1),
    ("I3: an event handler after a slash", before_main_end(INSTALL, '<span/onclick="alert(1)">x</span>'), 1),
    ("I4: a javascript: link", before_main_end(INSTALL, '<a href="javascript:alert(1)">x</a>'), 1),
    ("I5: an application/x-javascript script on the instructions page",
        before_main_end(INSTRUCTIONS, '<script type="application/x-javascript">alert(1)</script>'), 1),
    ("I6: an inline script on the home page", before_main_end(HOME, "<script>alert(1)</script>"), 1),
    ("I7: an event handler on the licence page", edit(LICENSE, "<h1>", '<h1 onclick="alert(1)">'), 1),
    ("an inline script on the draft holding page", before_main_end(HOLDING, "<script>alert(1)</script>"), 1),
    ("an upper-case SCRIPT tag", before_main_end(INSTALL, "<SCRIPT>alert(1)</SCRIPT>"), 1),
    ("a module script", before_main_end(INSTALL, '<script type="module">alert(1)</script>'), 1),
    ("a script whose first type is not a data block",
        before_main_end(INSTALL, '<script type="text/javascript" type="application/ld+json">alert(1)</script>'), 1),
    ("an upper-case event handler", before_main_end(VERIFY, '<p ONMOUSEOVER="alert(1)">x</p>'), 1),
    ("an event handler on an svg element", before_main_end(INSTALL, '<svg onload="alert(1)"></svg>'), 1),
    ("a javascript: URL with an encoded tab", before_main_end(INSTALL, '<a href="java&#x09;script:alert(1)">x</a>'), 1),
    ("a javascript: URL in upper case after spaces", before_main_end(INSTALL, '<a href="  JAVASCRIPT:alert(1)">x</a>'), 1),
    ("a javascript: URL in a form action", before_main_end(INSTALL, '<form action="javascript:alert(1)"></form>'), 1),
    ("a javascript: URL in a button formaction",
        before_main_end(INSTALL, '<button formaction="javascript:alert(1)">x</button>'), 1),
    ("a javascript: URL in an iframe src", before_main_end(INSTALL, '<iframe src="javascript:alert(1)"></iframe>'), 1),
    ("a javascript: URL in an svg xlink:href",
        before_main_end(INSTALL, '<svg><a xlink:href="javascript:alert(1)"><text>x</text></a></svg>'), 1),
    ("a style element", before_main_end(VERIFY, "<style>p{color:red}</style>"), 1),
    ("a style attribute", edit(LICENSE, "<h1>", '<h1 style="color:red">'), 1),
    ("a script start tag the parser does not count",
        before_main_end(HOME, '<script type="application/ld+json">{"x": "<script>"}</script>'), 1),
    ("a structured-data block in mixed case and spaces",
        before_main_end(INSTALL, '<script type=" Application/LD+JSON ">{}</script>'), 0),
    ("a structured-data block on the draft holding page", before_main_end(HOLDING, JSON_LD), 0),
    ("an external script with no text", before_main_end(INSTALL, '<script src="/js/x.js" defer></script>'), 0),
    ("the word javascript in a text link", before_main_end(INSTALL, '<a href="/javascript-notes/">javascript:</a>'), 0),
    ("N1: an img in an svg title", before_main_end(HOME, f"<svg><title>{IMG}</title></svg>"), 1),
    ("N1: an img in an svg iframe", before_main_end(HOME, f"<svg><iframe>{IMG}</iframe></svg>"), 1),
    ("N1: an img in an svg textarea on the install page", before_main_end(INSTALL, f"<svg><textarea>{IMG}</textarea></svg>"), 1),
    ("N1: an img in a math xmp on the instructions page", before_main_end(INSTRUCTIONS, f"<math><xmp>{IMG}</xmp></math>"), 1),
    ("N1: an img after a CDATA opening", before_main_end(HOME, f"<![CDATA[>{IMG}]]>"), 1),
    ("N1: an img after a <!--> comment", before_main_end(HOME, f"<!-->{IMG}<!-- y -->"), 1),
    ("N1: an img after a <!---> comment", before_main_end(HOME, f"<!--->{IMG}<!-- y -->"), 1),
    ("a CDATA section with no handler", before_main_end(HOME, "<![CDATA[x]]>"), 1),
    ("a <!--> comment with no handler", before_main_end(HOME, "<!-->x<!-- y -->"), 1),
    ("a <!---> comment with no handler", before_main_end(HOME, "<!--->x<!-- y -->"), 1),
    ("an ordinary comment", before_main_end(HOME, "<!-- y -->"), 0),
    ("an svg element",before_main_end(LICENSE, "<svg></svg>"), 1),
    ("a math element", before_main_end(LICENSE, "<math></math>"), 1),
    ("an iframe element", before_main_end(LICENSE, '<iframe src="/"></iframe>'), 1),
    ("a textarea element", before_main_end(LICENSE, "<textarea></textarea>"), 1),
    ("an xmp element", before_main_end(LICENSE, "<xmp></xmp>"), 1),
    ("a noembed element", before_main_end(LICENSE, "<noembed></noembed>"), 1),
    ("a noframes element", before_main_end(LICENSE, "<noframes></noframes>"), 1),
    ("a plaintext element", before_main_end(LICENSE, "<PLAINTEXT>"), 1),
    ("a template element", before_main_end(LICENSE, "<template></template>"), 1),
    ("an on* attribute the parser reads as script text",
        before_main_end(HOME, '<script type="application/ld+json">{"x": "<b onclick=1>"}</script>'), 1),
    ("an on* attribute in a title the parser may read as text", edit(LICENSE, "</title>", '<b onclick="alert(1)"></b></title>'), 1),
    ("N2: a script in an SVG file", svg_with("<script>alert(1)</script>"), 1),
    ("N2: a script with src in an SVG file", svg_with('<script src="/js/x.js"></script>'), 1),
    ("N2: a script with href in an SVG file", svg_with('<script href="/js/x.js"></script>'), 1),
    ("N2: an onload attribute in an SVG file", edit(FAVICON, "<svg ", '<svg onload="alert(1)" '), 1),
    ("N2: a style element in an SVG file", svg_with("<style>rect{fill:red}</style>"), 1),
    ("N2: a style attribute in an SVG file", edit(FAVICON, "<rect ", '<rect style="fill:red" '), 1),
    ("N2: a javascript: href in an SVG file", svg_with('<a href="javascript:alert(1)"><text>x</text></a>'), 1),
    ("N2: a javascript: xlink:href in an SVG file", svg_with('<a xlink:href="javascript:alert(1)"><text>x</text></a>'), 1),
    ("N2: a javascript: URL under another xlink prefix in an SVG file",
        svg_with('<a xmlns:x="http://www.w3.org/1999/xlink" x:href="javascript:alert(1)"><text>x</text></a>'), 1),
    ("N2: an animate element targeting href in an SVG file",
        svg_with('<a><animate attributeName="href" values="javascript:alert(1)"/><text>x</text></a>'), 1),
    ("N2: a set element targeting xlink:href in an SVG file",
        svg_with('<a><set attributeName="xlink:href" to="javascript:alert(1)"/><text>x</text></a>'), 1),
    ("N2: an animate element targeting fill in an SVG file", svg_with('<animate attributeName="fill" values="red"/>'), 0),
    ("N2: a new SVG file with a script", write_text("site/images/x.svg", "<svg><script>alert(1)</script></svg>"), 1),
    ("N2: a srcdoc attribute on a page", before_main_end(LICENSE, '<div srcdoc="&lt;img src=x onerror=alert(1)&gt;"></div>'), 1),
    ("N2: a srcdoc attribute in an SVG file", svg_with('<g srcdoc="x"></g>'), 1),
    ("P1: a handler after a </noscript> inside an attribute on the demo page", before_main_end(DEMO,
        "<noscript><p title=\"</noscript><img src=x title='>' onerror=alert(1)>\"></p></noscript>"), 1),
    ("P2: a handler after a </noscript> inside an attribute on the install page", before_main_end(INSTALL,
        "<noscript><p title=\"</noscript><img src=x title='>' onerror=alert(1)>\"></p></noscript>"), 1),
    ("P3: a javascript: link after a </noscript> inside an attribute on the instructions page",
        before_main_end(INSTRUCTIONS,
        "<noscript><p title=\"</noscript><a href='javascript:alert(1)' title='>'>x</a>\"></p></noscript>"), 1),
    ("a handler after a </noscript x> inside an attribute", before_main_end(DEMO,
        "<noscript><p title=\"</noscript x><img src=x title='>' onerror=alert(1)>\"></p></noscript>"), 1),
    ("LOW-4: a style attribute after a </noscript> inside an attribute", before_main_end(DEMO,
        "<noscript><p title=\"</noscript><b style=color:red>x</b>\"></p></noscript>"), 1),
    ("a style attribute inside noscript", before_main_end(DEMO, '<noscript><b style="color:red">x</b></noscript>'), 1),
    ("a handler inside noscript", before_main_end(DEMO, '<noscript><img src="x" onerror="alert(1)"></noscript>'), 1),
    ("a javascript: link inside noscript", before_main_end(DEMO, '<noscript><a href="javascript:alert(1)">x</a></noscript>'), 1),
    ("an svg element inside noscript", before_main_end(DEMO, "<noscript><svg></svg></noscript>"), 1),
    ("an external script inside noscript", before_main_end(DEMO, '<noscript><script src="/js/x.js"></script></noscript>'), 0),
    ("a javascript: link after a </title> inside an attribute",
        edit(LICENSE, "</title>", "<a title=\"</title><a href='javascript:alert(1)'>x</a>\"></a></title>"), 1),
    ("a handler after a quoted > in a title", edit(LICENSE, "</title>", "<b title='>' onclick=alert(1)></b></title>"), 1),
    ("a javascript: link inside an SVG title", svg_with('<title><a href="javascript:alert(1)">x</a></title>'), 1),
    ("an ordinary noscript notice", before_main_end(DEMO, '<noscript><p class="notice">x</p></noscript>'), 0),
    ("LOW-2: a handler after a quoted > in a tag", before_main_end(INSTALL, "<img src=x title='>' onerror=alert(1)>"), 1),
    ("LOW-3: an internal entity in an SVG file", both(
        edit(FAVICON, "<svg ", '<!DOCTYPE svg [<!ENTITY x "&#60;script&#62;alert(1)&#60;/script&#62;">]><svg '),
        edit(FAVICON, "</svg>", "&x;</svg>")), 1),
    ("a DOCTYPE in an SVG file", edit(FAVICON, "<svg ", "<!DOCTYPE svg><svg "), 1),
    ("an ENTITY declaration in an SVG file", edit(FAVICON, "<svg ", '<!entity x "y"><svg '), 1),
    ("R3 HIGH (S1): an SVG-namespace script with a prefix",
        svg_with('<s:script xmlns:s="http://www.w3.org/2000/svg">alert(1)</s:script>'), 1),
    ("R3 HIGH (S2): an XHTML-namespace script with a prefix",
        svg_with('<h:script xmlns:h="http://www.w3.org/1999/xhtml">alert(1)</h:script>'), 1),
    ("R3 HIGH (IM3): a prefixed set element changing href",
        svg_with('<a><s:set xmlns:s="http://www.w3.org/2000/svg" attributeName="href" to="javascript:alert(1)"/><text>x</text></a>'), 1),
    ("R3 HIGH: a prefixed animate element changing xlink:href", svg_with(
        '<a xmlns:xlink="http://www.w3.org/1999/xlink"><s:animate xmlns:s="http://www.w3.org/2000/svg" '
        'attributeName="xlink:href" values="javascript:alert(1)"/><text>x</text></a>'), 1),
    ("R3 HIGH: a new SVG file whose root and script carry a prefix", write_text("site/images/x.svg",
        '<svg:svg xmlns:svg="http://www.w3.org/2000/svg"><svg:script>alert(1)</svg:script></svg:svg>'), 1),
    ("R3 HIGH: a prefixed SVG file with no code", write_text("site/images/ok.svg",
        '<s:svg xmlns:s="http://www.w3.org/2000/svg"><s:rect width="1" height="1"/></s:svg>'), 0),
    ("R3 HIGH: an event handler in another namespace in an SVG file",
        edit(FAVICON, "<rect ", '<rect xmlns:e="urn:example" e:onclick="alert(1)" '), 1),
    ("R3 HIGH: a foreignObject in an SVG file", svg_with("<foreignObject><p>x</p></foreignObject>"), 1),
    ("R3 HIGH: an element in another namespace in an SVG file", svg_with('<m:meta xmlns:m="urn:example"/>'), 1),
    ("R3 HIGH: an SVG file with no namespace", write_text("site/images/plain.svg", '<svg><rect width="1" height="1"/></svg>'), 1),
    ("R3 HIGH: an SVG file the XML parser refuses", edit(FAVICON, "</svg>", ""), 1),
    ("R3 HIGH: a processing instruction in an SVG file", edit(FAVICON, "<svg ", '<?xml-stylesheet href="/x.css"?><svg '), 1),
    ("R3 HIGH: an XML declaration and a comment in an SVG file",
        both(edit(FAVICON, "<svg ", '<?xml version="1.0" encoding="UTF-8"?>\n<svg '), svg_with("<!-- x -->")), 0),
    ("R3 L1 (S4): a javascript: link after a plaintext tag in an SVG file",
        svg_with('<plaintext><a href="javascript:alert(1)"><text>x</text></a></plaintext>'), 1),
    ("R3 MEDIUM: the report's handler tag with an unpaired quote",
        edit(HOME, "</body>", "<img src=x onerror=alert(1) title=a'b></body>"), 1),
    ("R3 MEDIUM: a handler with an unpaired quote that the parser reads as script text",
        write_text("site/extra/quote.html",
                   '<p>x</p><script type="application/ld+json">{"x": "<b onclick=1 title=a\'b>"}</script>'), 1),
    ("prose with an on*= sequence", before_main_end(LICENSE, "<p>Set onclick=go in the form.</p>"), 1),
    ("prose with the sequence written as a character reference",
        before_main_end(LICENSE, "<p>Set on&#x63;lick=go in the form.</p>"), 0),
    ("a same-origin script that also holds code on a page",
        before_main_end(LICENSE, '<script src="/js/x.js">alert(1)</script>'), 1),
    ("a srcdoc attribute with no handler on a page", before_main_end(LICENSE, '<div srcdoc="&lt;p&gt;x&lt;/p&gt;"></div>'), 1),
    ("a set element changing an href under another xlink prefix in an SVG file", svg_with(
        '<a xmlns:x="http://www.w3.org/1999/xlink"><set attributeName="x:href" to="javascript:alert(1)"/><text>x</text></a>'), 1),
    ("R3 L (IM4): a beacon script from another origin on a page", before_main_end(HOME,
        '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
        'data-cf-beacon=\'{"token": "0000"}\'></script>'), 1),
    ("a protocol-relative script on a page", before_main_end(LICENSE, '<script src="//example.com/x.js"></script>'), 1),
    ("a backslash script path on a page", before_main_end(LICENSE, '<script src="/\\example.com/x.js"></script>'), 1),
    ("a relative script path on a page", before_main_end(LICENSE, '<script src="js/x.js"></script>'), 1),
    ("a script from another origin inside noscript on a page",
        before_main_end(DEMO, '<noscript><script src="https://example.com/x.js"></script></noscript>'), 1),
    ("a script from another origin on the draft holding page",
        before_main_end(HOLDING, '<script src="https://example.com/x.js"></script>'), 1),
    ("N4: an inline script in a .htm page", write_text("site/extra/index.htm", "<p>x</p><script>alert(1)</script>"), 1),
    ("a page that is not UTF-8", write_bytes(LICENSE, b"<p>\xff</p>"), 3),
    ("no HTML page under site/", remove_pages, 3),
    ("the switch with an onload on its first svg",
        edit(INSTALL, SWITCH_HEAD, SWITCH_HEAD.replace('<svg class="moon" ', '<svg class="moon" onload="alert(1)" ')), 1),
    ("the switch with 1 byte changed", edit(INSTALL, 'stroke-width="1.8"', 'stroke-width="1.9"'), 1),
    ("the switch twice on 1 page", duplicate_switch(LICENSE), 1),
    ("a bare svg next to the switch", edit(LICENSE, '<span class="vh">Dark mode</span></button>',
                                           '<span class="vh">Dark mode</span></button><svg></svg>'), 1),
    ("a second element with data-scheme-toggle, a button in the content", before_main_end(LICENSE, TOGGLE), 1),
    ("a second element with data-scheme-toggle in upper case", before_main_end(HOME, '<div DATA-SCHEME-TOGGLE hidden></div>'), 1),
    ("a second element with data-scheme-toggle inside noscript",
        before_main_end(DEMO, "<noscript>" + TOGGLE + "</noscript>"), 1),
    ("no switch on a page", edit(LICENSE, SWITCH, ""), 1),
    ("the switch's markup again inside a comment", before_main_end(LICENSE, "<!--" + SWITCH + "-->"), 1),
    ("the switch after header.mast", edit(LICENSE, SWITCH + "</header>", "</header>" + SWITCH), 1),
    ("the switch in a header without the mast class", edit(LICENSE, '<header class="mast">', '<header class="other">'), 1),
    ("the switch in a div.mast inside header.mast", both(
        edit(LICENSE, '<header class="mast">', '<header class="mast"><div class="mast">'),
        edit(LICENSE, SWITCH + "</header>", SWITCH + "</div></header>")), 1),
    ("the switch after a nav without the nav class", edit(LICENSE, '<nav class="nav"', '<nav class="links"'), 1),
    ("the switch after a div.nav", both(edit(LICENSE, '<nav class="nav"', '<div class="nav"'),
        edit(LICENSE, "</nav>" + SWITCH, "</div>" + SWITCH)), 1),
    ("a comment after the switch in header.mast", edit(LICENSE, SWITCH + "</header>", SWITCH + "<!-- x --></header>"), 1),
    ("an end tag that closes no open element before the switch", edit(LICENSE, '<nav class="nav"', '</div><nav class="nav"'), 1),
    ("a newline between nav.nav and the switch", edit(LICENSE, "</nav>" + SWITCH, "</nav>\n" + SWITCH), 0),
    # A browser ignores the slash on an element that is neither void nor in <svg>, so the switch becomes its child.
    ("a self-closing nav.nav before the switch", edit(LICENSE, SWITCH, '<nav class="nav"/>' + SWITCH), 1),
    ("a self-closing div first in header.mast", edit(LICENSE, '<header class="mast">', '<header class="mast"><div/>'), 1),
]
# Faults that check 7's switch reading itself must refuse, whatever else also refuses them: class names split on
# ASCII whitespace only, and no switch inside an element of INERT_ELEMENTS. Its refusal names the place.
PLACE = "as the last child of header.mast"
MAST, MAST_END = '<header class="mast">', SWITCH + "</header>"
SWITCH_RULES = [
    ("a no-break space in the mast class", edit(LICENSE, MAST, '<header class="mast\u00a0x">')),
    ("a no-break space in the nav class", edit(LICENSE, '<nav class="nav"', '<nav class="nav\u00a0x"')),
] + [(f"header.mast inside {name}", both(edit(LICENSE, MAST, f"<{name}>" + MAST), edit(LICENSE, MAST_END, MAST_END + f"</{name}>")))
     for name in ("noscript", "template", "audio", "canvas", "datalist", "meter", "object", "progress", "rp", "select", "video")]


def run_version_probe(root: Path, probe: tuple) -> subprocess.CompletedProcess:
    """Run the gate copy in root through VERSION_PROBE under the faked version tuple probe."""
    return subprocess.run([sys.executable, "-I", "-c", VERSION_PROBE, " ".join(map(str, probe)),
                           str(root / "tools" / GATE.name)], capture_output=True, text=True)


def main() -> int:
    failures: list[str] = []
    switch = gate_switch()
    if hashlib.sha256(switch.encode("utf-8")).hexdigest() != SWITCH_SHA256:
        failures.append("SCHEME_SWITCH in tools/check-inline-code.py is not the 7.33 switch of the reference pages")
    if (REPO_ROOT / INSTALL).read_text(encoding="utf-8").count(switch) != 1:
        failures.append(f"{INSTALL} does not carry the switch exactly once")
    for name, fault, expected, says in [(*case, "") for case in CASES] + [(*rule, 1, PLACE) for rule in SWITCH_RULES]:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if fault:
                fault(root)
            result = subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name)], capture_output=True, text=True)
            if result.returncode != expected or says not in result.stdout:
                failures.append(f"{name}: exit {result.returncode}, expected {expected}{' with ' + repr(says) if says else ''}: "
                                f"{(result.stdout + result.stderr).strip()[:300]}")
    if load_gate().SUPPORTED_PYTHONS != SUPPORTED_PYTHONS:
        failures.append(f"SUPPORTED_PYTHONS in tools/check-inline-code.py is not exactly {SUPPORTED_PYTHONS}")
    supported = ", ".join(f"{major}.{minor}" for major, minor in SUPPORTED_PYTHONS)
    for probe in VERSION_PROBES:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            result = run_version_probe(root, probe)
            lines = result.stderr.splitlines()
            needles = (f"runs only on Python {supported}", f"this is Python {probe[0]}.{probe[1]}")
            if result.returncode != 3 or result.stdout or len(lines) != 1 or not all(n in lines[0] for n in needles):
                failures.append(f"Python {probe[0]}.{probe[1]}: exit {result.returncode}, expected 3 with no stdout and "
                                f"1 stderr line naming {' and '.join(needles)}: "
                                f"{(result.stdout + result.stderr).strip()[:300]}")
    for name, statement in READ_MUTANTS:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            edit(f"tools/{GATE.name}", "def main() -> int:\n", f"def main() -> int:\n    {statement}\n")(root)
            result = run_version_probe(root, VERSION_PROBES[0])
            if result.returncode != 97 or TRAPPED not in result.stderr:
                failures.append(f"a read through {name} before the version check: exit {result.returncode}, expected 97 "
                                f"with {TRAPPED!r}: {(result.stdout + result.stderr).strip()[:300]}")
    if failures:
        print("test-inline-code: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-inline-code: all {len(CASES) + len(SWITCH_RULES) + len(VERSION_PROBES) + len(READ_MUTANTS)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
