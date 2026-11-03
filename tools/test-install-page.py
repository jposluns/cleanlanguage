#!/usr/bin/env python3
"""Tests for tools/check-install-page.py: the template mode and the /draft/ policy rule.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault to the template install page or to
site/_headers, runs the gate there as a separate process and asserts its exit
code. Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-install-page.py"
FILES = ["site/install/index.html", "site/styles.css", "site/_headers", "site/draft/install/index.html"]
DRAFT = "site/draft/install/index.html"
HEADERS = "site/_headers"
DRAFT_CSP_LINE = "  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'"


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(GATE, root / "tools" / GATE.name)
    shutil.copyfile(REPO_ROOT / "tools" / "check-headers.py", root / "tools" / "check-headers.py")
    for relative in FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


def edit(relative: str, old: str, new: str):
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(f"{old!r} is not in {relative}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return apply


def remove(relative: str):
    return lambda root: (root / relative).unlink()


CASES = [
    ("the committed tree", None, 0),
    ("a family section removed", edit(DRAFT, 'data-family-section="gemini"', 'data-family-gone="gemini"'), 1),
    ("a family section duplicated", edit(DRAFT, '<section id="copilot" data-family-section="copilot">', '<section id="copilot" data-family-section="copilot"></section><section id="copilot" data-family-section="copilot">'), 1),
    ("a family section hidden", edit(DRAFT, '<section id="claude" data-family-section="claude">', '<section id="claude" data-family-section="claude" hidden>'), 1),
    ("a family heading emptied", edit(DRAFT, "<h2>ChatGPT</h2>", "<h2>​</h2>"), 1),
    ("a picker link pointing elsewhere", edit(DRAFT, '<a href="#chatgpt" data-family-link="chatgpt">', '<a href="#gemini" data-family-link="chatgpt">'), 1),
    ("a picker link with aria-current", edit(DRAFT, '<a href="#claude" data-family-link="claude">', '<a href="#claude" data-family-link="claude" aria-current="true">'), 1),
    ("a picker link outside the list", edit(DRAFT, '<li><a href="#other-ai" data-family-link="other-ai">Other AI systems</a></li></ul>', '</ul><a href="#other-ai" data-family-link="other-ai">Other AI systems</a>'), 1),
    ("the reset button shown", edit(DRAFT, "data-picker-reset hidden>", "data-picker-reset>"), 1),
    ("the picker status removed", edit(DRAFT, " data-picker-status></p>", "></p>"), 1),
    ("the assurance id removed", edit(DRAFT, '<h2 id="assurance">', "<h2>"), 1),
    ("the get id renamed", edit(DRAFT, '<h2 id="get">', '<h2 id="cl-get">'), 1),
    ("an inline script", edit(DRAFT, "</main>", "<script>alert(1)</script></main>"), 1),
    ("an inline style", edit(DRAFT, '<p class="lbl first">', '<p style="x" class="lbl first">'), 1),
    ("an on* handler", edit(DRAFT, '<p class="lbl first">', '<p onclick="x()" class="lbl first">'), 1),
    ("baseline.css without its version token", edit(DRAFT, "baseline.css?v=", "baseline.css?x="), 1),
    ("select.js not loaded", edit(DRAFT, "select.js?v=", "select-gone.js?v="), 1),
    ("a baseline script without its version token", edit(DRAFT, "</head>", '<script src="/draft/assets/baseline/rail.js" defer></script>\n</head>'), 1),
    ("a baseline script without defer", edit(DRAFT, "</head>", '<script src="/draft/assets/baseline/rail.js?v=1.3.0"></script>\n</head>'), 1),
    ("a script from outside the baseline", edit(DRAFT, "</head>", '<script src="/draft/assets/other.js?v=1.3.0" defer></script>\n</head>'), 1),
    ("rail.js with its token and defer", edit(DRAFT, "</head>", '<script src="/draft/assets/baseline/rail.js?v=1.3.0" defer></script>\n</head>'), 0),
    ("site.css without its content token", edit(DRAFT, "</head>", '<link rel="stylesheet" href="/draft/assets/site.css?w=1">\n</head>'), 1),
    ("the draft page missing", remove(DRAFT), 3),
    ("the draft policy loosened", edit(HEADERS, "frame-ancestors 'none'\n  X-Robots-Tag", "frame-ancestors 'none'; worker-src *\n  X-Robots-Tag"), 1),
    ("the draft policy gaining unsafe-eval", edit(HEADERS, "'unsafe-inline' https://ajax", "'unsafe-inline' 'unsafe-eval' https://ajax"), 1),
    ("the draft rule without its detach", edit(HEADERS, "  ! Content-Security-Policy\n", ""), 1),
    ("the detach after the draft policy", lambda root: (
        edit(HEADERS, "  ! Content-Security-Policy\n" + DRAFT_CSP_LINE, DRAFT_CSP_LINE)(root),
        edit(HEADERS, "  X-Robots-Tag: noindex\n\n/downloads/cleanlanguage.md\n",
             "  ! Content-Security-Policy\n  X-Robots-Tag: noindex\n\n/downloads/cleanlanguage.md\n")(root),
    ), 1),
    ("the noindex detached under another draft rule", edit(HEADERS, "/sitemap.xml\n", "/draft/install/*\n  ! X-Robots-Tag\n\n/sitemap.xml\n"), 1),
    ("the noindex changed site-wide", edit(HEADERS, "/sitemap.xml\n", "/*\n  X-Robots-Tag: all\n\n/sitemap.xml\n"), 1),
    ("the noindex changed through a full URL pattern", edit(HEADERS, "/sitemap.xml\n", "https://cleanlanguage.ai/draft/*\n  X-Robots-Tag: all\n\n/sitemap.xml\n"), 1),
    ("the noindex changed under /Draft/ in another case", edit(HEADERS, "/sitemap.xml\n", "/Draft/*\n  X-Robots-Tag: all\n\n/sitemap.xml\n"), 1),
    ("the shared headers gate missing", lambda root: (root / "tools" / "check-headers.py").unlink(), 3),
    ("the noindex changed under another draft rule", edit(HEADERS, "/sitemap.xml\n", "/draft/install/*\n  X-Robots-Tag: all\n\n/sitemap.xml\n"), 1),
    ("the draft rule without X-Robots-Tag", edit(HEADERS, "  X-Robots-Tag: noindex\n\n/downloads/cleanlanguage.md\n", "\n/downloads/cleanlanguage.md\n"), 1),
    ("a policy on another rule", edit(HEADERS, "/sitemap.xml\n", "/sitemap.xml\n  Content-Security-Policy: default-src 'none'\n"), 1),
    ("the site-wide policy gaining unsafe-inline", edit(HEADERS, "script-src 'self'; img-src", "script-src 'self' 'unsafe-inline'; img-src"), 1),
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
        print("test-install-page: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-install-page: all {len(CASES)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
