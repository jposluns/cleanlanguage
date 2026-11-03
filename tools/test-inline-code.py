#!/usr/bin/env python3
"""Tests for tools/check-inline-code.py.

Each case copies the gate and every HTML page and SVG file under site/ into a
temporary repository (under $TMPDIR), applies 1 fault to 1 file, runs the gate
there as a separate process and asserts its exit code. The cases named I1 to I7,
I2 and I2B are the inline-code mutants of the PR 206 review, and the cases named
N1, N2 and N4 are the probes of its first verification round. Exit 0 when every case passes;
1 otherwise, naming each failing case.
"""

from __future__ import annotations

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
PRIVACY = "site/privacy/index.html"
DRAFT_INSTALL = "site/draft/install/index.html"
DRAFT_HOME = "site/draft/index.html"
FAVICON = "site/favicon.svg"
IMG = '<img src="x" onerror="alert(1)">'


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
    ("I7: an event handler on the privacy page", edit(PRIVACY, "<h1>", '<h1 onclick="alert(1)">'), 1),
    ("an inline script on a draft page", before_main_end(DRAFT_HOME, "<script>alert(1)</script>"), 1),
    ("an upper-case SCRIPT tag", before_main_end(INSTALL, "<SCRIPT>alert(1)</SCRIPT>"), 1),
    ("a module script", before_main_end(INSTALL, '<script type="module">alert(1)</script>'), 1),
    ("a script whose first type is not a data block",
        before_main_end(INSTALL, '<script type="text/javascript" type="application/ld+json">alert(1)</script>'), 1),
    ("an upper-case event handler", before_main_end(DRAFT_INSTALL, '<p ONMOUSEOVER="alert(1)">x</p>'), 1),
    ("an event handler on an svg element", before_main_end(INSTALL, '<svg onload="alert(1)"></svg>'), 1),
    ("a javascript: URL with an encoded tab", before_main_end(INSTALL, '<a href="java&#x09;script:alert(1)">x</a>'), 1),
    ("a javascript: URL in upper case after spaces", before_main_end(INSTALL, '<a href="  JAVASCRIPT:alert(1)">x</a>'), 1),
    ("a javascript: URL in a form action", before_main_end(INSTALL, '<form action="javascript:alert(1)"></form>'), 1),
    ("a javascript: URL in a button formaction",
        before_main_end(INSTALL, '<button formaction="javascript:alert(1)">x</button>'), 1),
    ("a javascript: URL in an iframe src", before_main_end(INSTALL, '<iframe src="javascript:alert(1)"></iframe>'), 1),
    ("a javascript: URL in an svg xlink:href",
        before_main_end(INSTALL, '<svg><a xlink:href="javascript:alert(1)"><text>x</text></a></svg>'), 1),
    ("a style element", before_main_end(DRAFT_INSTALL, "<style>p{color:red}</style>"), 1),
    ("a style attribute", edit(PRIVACY, "<h1>", '<h1 style="color:red">'), 1),
    ("a script start tag the parser does not count",
        before_main_end(HOME, '<script type="application/ld+json">{"x": "<script>"}</script>'), 1),
    ("a structured-data block in mixed case and spaces",
        before_main_end(INSTALL, '<script type=" Application/LD+JSON ">{}</script>'), 0),
    ("a structured-data block on a draft page", before_main_end(DRAFT_HOME, JSON_LD), 0),
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
    ("an svg element",before_main_end(PRIVACY, "<svg></svg>"), 1),
    ("a math element", before_main_end(PRIVACY, "<math></math>"), 1),
    ("an iframe element", before_main_end(PRIVACY, '<iframe src="/"></iframe>'), 1),
    ("a textarea element", before_main_end(PRIVACY, "<textarea></textarea>"), 1),
    ("an xmp element", before_main_end(PRIVACY, "<xmp></xmp>"), 1),
    ("a noembed element", before_main_end(PRIVACY, "<noembed></noembed>"), 1),
    ("a noframes element", before_main_end(PRIVACY, "<noframes></noframes>"), 1),
    ("a plaintext element", before_main_end(PRIVACY, "<PLAINTEXT>"), 1),
    ("a template element", before_main_end(PRIVACY, "<template></template>"), 1),
    ("an on* attribute the parser reads as script text",
        before_main_end(HOME, '<script type="application/ld+json">{"x": "<b onclick=1>"}</script>'), 1),
    ("an on* attribute in a title the parser may read as text", edit(PRIVACY, "</title>", '<b onclick="alert(1)"></b></title>'), 1),
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
    ("N2: a srcdoc attribute on a page", before_main_end(PRIVACY, '<div srcdoc="&lt;img src=x onerror=alert(1)&gt;"></div>'), 1),
    ("N2: a srcdoc attribute in an SVG file", svg_with('<g srcdoc="x"></g>'), 1),
    ("N4: an inline script in a .htm page", write_text("site/extra/index.htm", "<p>x</p><script>alert(1)</script>"), 1),
    ("a page that is not UTF-8", write_bytes(PRIVACY, b"<p>\xff</p>"), 3),
    ("no HTML page under site/", remove_pages, 3),
]


def main() -> int:
    failures: list[str] = []
    for name, fault, expected in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if fault:
                fault(root)
            result = subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name)], capture_output=True, text=True)
            if result.returncode != expected:
                failures.append(f"{name}: exit {result.returncode}, expected {expected}: {(result.stdout + result.stderr).strip()[:300]}")
    if failures:
        print("test-inline-code: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-inline-code: all {len(CASES)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
