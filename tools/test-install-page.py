#!/usr/bin/env python3
"""Tests for tools/check-install-page.py: the install pages' contract and the site-wide policy.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault to the install page, a family page, or
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
PAGE = "site/install/index.html"
CLAUDE = "site/install/claude/index.html"
CHATGPT = "site/install/chatgpt/index.html"
GEMINI = "site/install/gemini/index.html"
COPILOT = "site/install/copilot/index.html"
OTHER = "site/install/other-ai/index.html"
HEADERS = "site/_headers"
FILES = [PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER, HEADERS, "tools/check-headers.py", "tools/check-inline-code.py"]
SHARED_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://ajax.cloudflare.com "
    "https://static.cloudflareinsights.com; connect-src 'self' https://cloudflareinsights.com; "
    "style-src 'self'; font-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
NEXT_RULE = "\n\n/downloads/cleanlanguage.md"
SITE_LINE = "/*\n  X-Frame-Options: DENY"
SITE_CSP = f"  Content-Security-Policy: {SHARED_CSP}" + NEXT_RULE
DRAFT_RULE = f"\n/draft/*\n  ! Content-Security-Policy\n  Content-Security-Policy: {SHARED_CSP}\n  X-Robots-Tag: noindex\n"
OTHER_LINK = '<a class="btn inline" id="other-ai" href="/install/other-ai/">Other AI systems</a>'


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(GATE, root / "tools" / GATE.name)
    for relative in FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


def edit(relative: str, old: str, new: str, every: bool = False):
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(f"{old!r} is not in {relative}")
        path.write_text(text.replace(old, new) if every else text.replace(old, new, 1), encoding="utf-8")
    return apply


def append(relative: str, text: str):
    def apply(root: Path) -> None:
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")
    return apply


def remove(relative: str):
    return lambda root: (root / relative).unlink()


def both(*faults):
    return lambda root: [fault(root) for fault in faults][-1]


CASES = [
    ("the committed tree", None, 0),
    ("a family link pointing elsewhere", edit(PAGE, 'id="chatgpt" href="/install/chatgpt/"', 'id="chatgpt" href="/install/gemini/"'), 1),
    ("a family link removed", edit(PAGE, '<a class="btn inline" id="claude" href="/install/claude/">Claude</a> ', ""), 1),
    ("a family id removed", edit(PAGE, 'id="gemini" href="/install/gemini/"', 'href="/install/gemini/"'), 1),
    ("a family link duplicated", edit(PAGE, OTHER_LINK, OTHER_LINK + ' <a class="btn inline" id="copilot" href="/install/copilot/">Copilot</a>'), 1),
    ("a family link that is not a button", edit(PAGE, '<a class="btn inline" id="copilot"', '<a id="copilot"'), 1),
    ("a family link with aria-current", edit(PAGE, 'id="claude" href="/install/claude/"', 'id="claude" href="/install/claude/" aria-current="page"'), 1),
    ("a family link hidden", edit(PAGE, 'id="gemini" href="/install/gemini/"', 'id="gemini" href="/install/gemini/" hidden'), 1),
    ("a family link aria-hidden", edit(PAGE, 'id="gemini" href="/install/gemini/"', 'id="gemini" href="/install/gemini/" aria-hidden="TRUE"'), 1),
    ("a family link outside the button row", both(
        edit(PAGE, " " + OTHER_LINK, ""), edit(PAGE, '<p class="lbl blk">Scope</p>', f"<p>{OTHER_LINK}</p>\n" + '<p class="lbl blk">Scope</p>')), 1),
    ("a family link after Get Clean Language", both(
        edit(PAGE, " " + OTHER_LINK, ""), edit(PAGE, '<h2 id="get">Get Clean Language</h2>', f'<h2 id="get">Get Clean Language</h2>\n<p>{OTHER_LINK}</p>')), 1),
    ("the family links out of order", both(
        edit(PAGE, 'id="claude" href="/install/claude/">Claude', 'id="tmp" href="/install/claude/">Claude'),
        edit(PAGE, 'id="chatgpt" href="/install/chatgpt/">ChatGPT', 'id="claude" href="/install/claude/">ChatGPT'),
        edit(PAGE, 'id="tmp" href="/install/claude/">Claude', 'id="chatgpt" href="/install/chatgpt/">Claude')), 1),
    ("data-picker reintroduced", edit(PAGE, '<p class="lbl first">', '<p data-picker class="lbl first">'), 1),
    ("data-family-link reintroduced", edit(PAGE, '<a class="btn inline" id="claude"', '<a class="btn inline" data-family-link="claude" id="claude"'), 1),
    ("data-family-section on a family page", edit(COPILOT, '<p class="lbl first">', '<p data-family-section="copilot" class="lbl first">'), 1),
    ("a picker reset on a family page", edit(GEMINI, "</main>", '<button class="btn" type="button" data-picker-reset hidden>x</button></main>'), 1),
    ("the assurance id removed", edit(PAGE, '<h2 id="assurance">', "<h2>"), 1),
    ("the get id renamed", edit(PAGE, '<h2 id="get">', '<h2 id="cl-get">'), 1),
    ("the pick id removed", edit(PAGE, 'id="pick"', 'id="pick-gone"'), 1),
    ("the technical id removed", edit(PAGE, '<h2 id="technical">', "<h2>"), 1),
    ("a duplicate id on the install page", edit(PAGE, '<h2 id="spelling">', '<h2 id="spelling"><span id="test"></span>'), 1),
    ("a duplicate id on a family page", edit(CHATGPT, '<p class="verified">', '<p class="verified" id="main-content">'), 1),
    ("a family page missing", remove(GEMINI), 3),
    ("a family page with no setup steps", edit(CLAUDE, '<ol class="steps">', "<ol>"), 1),
    ("a family page step list hidden", edit(OTHER, '<ol class="steps">', '<ol class="steps" hidden>'), 1),
    ("a family page with no verified line", edit(COPILOT, '<p class="verified">', "<p>"), 1),
    ("a family page heading hidden", edit(CLAUDE, "<h1>", '<h1 class="visually-hidden">'), 1),
    ("a family page heading emptied", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>​</h1>"), 1),
    ("a family page inside a hidden wrapper", edit(GEMINI, '<div class="doc">', '<div class="doc" inert>'), 1),
    ("a family page with a second h1", edit(GEMINI, "</main>", "<h1>Again</h1></main>"), 1),
    ("a family page without its link back to #get", edit(OTHER, 'href="/install/#get"', 'href="/install/"', every=True), 1),
    ("a family page without its link to #test", edit(CLAUDE, 'href="/install/#test"', 'href="/install/"', every=True), 1),
    ("an inline script", edit(PAGE, "</main>", "<script>alert(1)</script></main>"), 1),
    ("an inline script on a family page", edit(COPILOT, "</main>", "<script>alert(1)</script></main>"), 1),
    ("an inline style", edit(PAGE, '<p class="lbl first">', '<p style="x" class="lbl first">'), 1),
    ("an on* handler", edit(PAGE, '<p class="lbl first">', '<p onclick="x()" class="lbl first">'), 1),
    ("an on* handler on a family page", edit(OTHER, '<p class="lbl first">', '<p onclick="x()" class="lbl first">'), 1),
    ("I1: an application/x-javascript script",
        edit(PAGE, "</main>", '<script type="application/x-javascript">alert(1)</script></main>'), 1),
    ("I2B: src= inside another attribute's quoted value",
        edit(PAGE, "</main>", "<script title='src=\"/install/\"'>alert(1)</script></main>"), 1),
    ("I3: an event handler after a slash", edit(PAGE, "</main>", '<span/onclick="alert(1)">x</span></main>'), 1),
    ("P2: a handler after a </noscript> inside an attribute", edit(PAGE, "</main>",
        "<noscript><p title=\"</noscript><img src=x title='>' onerror=alert(1)>\"></p></noscript></main>"), 1),
    ("a script from another origin", edit(PAGE, "</head>", '<script src="https://example.com/x.js" defer></script>\n</head>'), 1),
    ("baseline.css without its version token", edit(PAGE, "baseline.css?v=", "baseline.css?x="), 1),
    ("baseline.css without its version token on a family page", edit(CHATGPT, "baseline.css?v=", "baseline.css?x="), 1),
    ("copy.js not loaded", edit(PAGE, "copy.js?v=", "copy-gone.js?v="), 1),
    ("copy.js not loaded on a family page", edit(OTHER, "copy.js?v=", "copy-gone.js?v="), 1),
    ("select.js loaded", edit(PAGE, "</head>", '<script src="/assets/baseline/select.js?v=1.3.0" defer></script>\n</head>'), 1),
    ("select.js loaded on a family page", edit(CLAUDE, "</head>", '<script src="/assets/baseline/select.js?v=1.3.0" defer></script>\n</head>'), 1),
    ("a baseline script without its version token", edit(PAGE, "</head>", '<script src="/assets/baseline/rail.js" defer></script>\n</head>'), 1),
    ("a baseline script without defer", edit(PAGE, "</head>", '<script src="/assets/baseline/rail.js?v=1.3.0"></script>\n</head>'), 1),
    ("a script from outside the baseline", edit(PAGE, "</head>", '<script src="/assets/other.js?v=1.3.0" defer></script>\n</head>'), 1),
    ("the retired install script", edit(PAGE, "</head>", '<script src="/js/install.js?v=20260101-1" defer></script>\n</head>'), 1),
    ("a baseline script under the old draft path", edit(PAGE, "</head>", '<script src="/draft/assets/baseline/rail.js?v=1.3.0" defer></script>\n</head>'), 1),
    ("rail.js with its token and defer", edit(PAGE, "</head>", '<script src="/assets/baseline/rail.js?v=1.3.0" defer></script>\n</head>'), 0),
    ("site.css without its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?w=1">\n</head>'), 1),
    ("site.css with its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?v=0123456789ab">\n</head>'), 0),
    ("the install page missing", remove(PAGE), 3),
    ("the headers file missing", remove(HEADERS), 3),
    ("a policy on another rule", edit(HEADERS, "/sitemap.xml\n", "/sitemap.xml\n  Content-Security-Policy: default-src 'none'\n"), 1),
    ("the site-wide policy widened", edit(HEADERS, "frame-ancestors 'none'" + NEXT_RULE, "frame-ancestors 'none'; worker-src *" + NEXT_RULE), 1),
    ("the site-wide policy gaining unsafe-eval", edit(HEADERS,
        "Cross-Origin-Opener-Policy: same-origin\n  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'",
        "Cross-Origin-Opener-Policy: same-origin\n  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval'"), 1),
    ("the site-wide policy allowing data: images", edit(HEADERS, "frame-ancestors 'none'" + NEXT_RULE,
        "frame-ancestors 'none'; img-src 'self' data:" + NEXT_RULE), 1),
    ("H5: a lower-case header name on a wider site-wide policy",
        edit(HEADERS, SITE_CSP, "  content-security-policy: default-src *" + NEXT_RULE), 1),
    ("H6: a comment decoy above a wider site-wide policy", lambda root: (
        edit(HEADERS, SITE_LINE, f"# Content-Security-Policy: {SHARED_CSP}\n" + SITE_LINE)(root),
        edit(HEADERS, SITE_CSP, "  Content-Security-Policy: default-src *" + NEXT_RULE)(root))[-1], 1),
    ("H7: an X-Content-Security-Policy decoy beside a wider site-wide policy",
        edit(HEADERS, SITE_CSP, f"  X-Content-Security-Policy: {SHARED_CSP}\n  Content-Security-Policy: default-src *" + NEXT_RULE), 1),
    ("an X-Content-Security-Policy line beside the shared policy",
        edit(HEADERS, SITE_CSP, f"  X-Content-Security-Policy: {SHARED_CSP}\n" + SITE_CSP), 1),
    ("the site-wide policy set twice", edit(HEADERS, SITE_CSP, f"  Content-Security-Policy: {SHARED_CSP}\n" + SITE_CSP), 1),
    ("the site-wide policy missing", edit(HEADERS, SITE_CSP, NEXT_RULE.lstrip("\n")), 1),
    ("R3 L2 (P4): the /* rule detaching its own policy after setting it",
        edit(HEADERS, SITE_CSP, f"  Content-Security-Policy: {SHARED_CSP}\n  ! Content-Security-Policy" + NEXT_RULE), 1),
    ("the headers gate missing", lambda root: (root / "tools/check-headers.py").unlink(), 3),
    ("the inline-code gate missing", lambda root: (root / "tools/check-inline-code.py").unlink(), 3),
    ("N3 (H1): /install/* detaching the policy", append(HEADERS, "\n/install/*\n  ! Content-Security-Policy\n"), 1),
    ("a staged /draft/* rule with its own detach", append(HEADERS, DRAFT_RULE), 0),
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
