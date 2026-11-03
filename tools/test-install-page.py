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
FILES = ["site/install/index.html", "site/styles.css", "site/_headers", "site/draft/install/index.html",
         "tools/check-headers.py", "tools/check-inline-code.py"]
DRAFT = "site/draft/install/index.html"
HEADERS = "site/_headers"
DRAFT_CSP_LINE = "  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'"
LIVE = "site/install/index.html"
SHARED_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://ajax.cloudflare.com "
    "https://static.cloudflareinsights.com; connect-src 'self' https://cloudflareinsights.com; "
    "style-src 'self'; font-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
SITE_LINE = "/*\n  X-Frame-Options: DENY"
SITE_CSP = f"  Content-Security-Policy: {SHARED_CSP}\n\n/draft/*"


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(GATE, root / "tools" / GATE.name)
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
    ("the draft policy gaining unsafe-eval", edit(HEADERS, "  ! Content-Security-Policy\n  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline' https://ajax",
        "  ! Content-Security-Policy\n  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://ajax"), 1),
    ("the draft rule without its detach", edit(HEADERS, "  ! Content-Security-Policy\n", ""), 1),
    ("the detach after the draft policy", lambda root: (
        edit(HEADERS, "  ! Content-Security-Policy\n" + DRAFT_CSP_LINE, DRAFT_CSP_LINE)(root),
        edit(HEADERS, "  X-Robots-Tag: noindex\n\n/downloads/cleanlanguage.md\n",
             "  ! Content-Security-Policy\n  X-Robots-Tag: noindex\n\n/downloads/cleanlanguage.md\n")(root),
    ), 1),
    ("the draft rule without X-Robots-Tag", edit(HEADERS, "  X-Robots-Tag: noindex\n\n/downloads/cleanlanguage.md\n", "\n/downloads/cleanlanguage.md\n"), 1),
    ("a policy on another rule", edit(HEADERS, "/sitemap.xml\n", "/sitemap.xml\n  Content-Security-Policy: default-src 'none'\n"), 1),
    ("the site-wide policy widened", edit(HEADERS, "frame-ancestors 'none'\n\n/draft/*", "frame-ancestors 'none'; worker-src *\n\n/draft/*"), 1),
    ("the site-wide policy gaining unsafe-eval", edit(HEADERS,
        "Cross-Origin-Opener-Policy: same-origin\n  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'",
        "Cross-Origin-Opener-Policy: same-origin\n  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval'"), 1),
    ("the site-wide policy allowing data: images", edit(HEADERS, "frame-ancestors 'none'\n\n/draft/*",
        "frame-ancestors 'none'; img-src 'self' data:\n\n/draft/*"), 1),
    ("H5: a lower-case header name on a wider site-wide policy",
        edit(HEADERS, SITE_CSP, "  content-security-policy: default-src *\n\n/draft/*"), 1),
    ("H6: a comment decoy above a wider site-wide policy", lambda root: (
        edit(HEADERS, SITE_LINE, f"# Content-Security-Policy: {SHARED_CSP}\n" + SITE_LINE)(root),
        edit(HEADERS, SITE_CSP, "  Content-Security-Policy: default-src *\n\n/draft/*")(root))[-1], 1),
    ("H7: an X-Content-Security-Policy decoy beside a wider site-wide policy",
        edit(HEADERS, SITE_CSP, f"  X-Content-Security-Policy: {SHARED_CSP}\n  Content-Security-Policy: default-src *\n\n/draft/*"), 1),
    ("an X-Content-Security-Policy line beside the shared policy",
        edit(HEADERS, SITE_CSP, f"  X-Content-Security-Policy: {SHARED_CSP}\n" + SITE_CSP), 1),
    ("the site-wide policy set twice", edit(HEADERS, SITE_CSP, f"  Content-Security-Policy: {SHARED_CSP}\n" + SITE_CSP), 1),
    ("the site-wide policy missing", edit(HEADERS, SITE_CSP, "\n/draft/*"), 1),
    ("I1: an application/x-javascript script on the live page",
        edit(LIVE, "</main>", '<script type="application/x-javascript">alert(1)</script></main>'), 1),
    ("I2B: src= inside another attribute's quoted value on the draft page",
        edit(DRAFT, "</main>", "<script title='src=\"/install/\"'>alert(1)</script></main>"), 1),
    ("I3: an event handler after a slash on the live page",
        edit(LIVE, "</main>", '<span/onclick="alert(1)">x</span></main>'), 1),
    ("the headers gate missing", lambda root: (root / "tools/check-headers.py").unlink(), 3),
    ("P2: a handler after a </noscript> inside an attribute on the live page", edit(LIVE, "</main>",
        "<noscript><p title=\"</noscript><img src=x title='>' onerror=alert(1)>\"></p></noscript></main>"), 1),
    ("N3 (H1): /install/* detaching the policy",
        lambda root: (root / HEADERS).write_text((root / HEADERS).read_text(encoding="utf-8")
                                                  + "\n/install/*\n  ! Content-Security-Policy\n", encoding="utf-8"), 1),
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
