#!/usr/bin/env python3
"""Tests for tools/check-install-page.py: the install page's selector contract and the site-wide policy.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault to the install page or to site/_headers, runs
the gate there as a separate process and asserts its exit code. 1 more case
asserts that the gate's docstring names exactly the scripts in
``BASELINE_SCRIPTS``. Exit 0 when every case passes; 1 otherwise, naming each
failing case.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-install-page.py"
FILES = ["site/install/index.html", "site/_headers", "tools/check-headers.py", "tools/check-inline-code.py"]
PAGE = "site/install/index.html"
HEADERS = "site/_headers"
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


# The scheme.js tag of template specification 7.33 (baseline 1.6.0), as the committed page carries it.
SCHEME = '<script data-cfasync="false" src="/assets/baseline/scheme.js?v=1.6.0"></script>'
FONTS = '<link rel="stylesheet" href="/assets/baseline/fonts.css?v=1.6.0">'
LATER = '<link rel="stylesheet" href="/assets/baseline/baseline.css?v=1.6.0">'


def both(*faults):
    def apply(root: Path) -> None:
        for fault in faults:
            fault(root)
    return apply


def append(relative: str, text: str):
    def apply(root: Path) -> None:
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")
    return apply


def remove(relative: str):
    return lambda root: (root / relative).unlink()


def into_body(first: str, before: str = "", after: str = ""):
    """Move the head's lines from first to </head> to the start of the body, in order, between before and after."""
    def apply(root: Path) -> None:
        path = root / PAGE
        text = path.read_text(encoding="utf-8")
        block = text[text.index(first):text.index("</head>")]
        text = text.replace(block, "", 1).replace("<body>\n", "<body>\n" + before + block + after, 1)
        path.write_text(text, encoding="utf-8")
    return apply


CASES = [
    ("the committed tree", None, 0),
    ("a family section removed", edit(PAGE, 'data-family-section="gemini"', 'data-family-gone="gemini"'), 1),
    ("a family section duplicated", edit(PAGE, '<section id="copilot" data-family-section="copilot">', '<section id="copilot" data-family-section="copilot"></section><section id="copilot" data-family-section="copilot">'), 1),
    ("a family section hidden", edit(PAGE, '<section id="claude" data-family-section="claude">', '<section id="claude" data-family-section="claude" hidden>'), 1),
    ("a family section aria-hidden", edit(PAGE, '<section id="claude" data-family-section="claude">', '<section id="claude" data-family-section="claude" aria-hidden="TRUE">'), 1),
    ("a family heading emptied", edit(PAGE, "<h2>ChatGPT</h2>", "<h2>​</h2>"), 1),
    ("data-family-section on another element", edit(PAGE, '<p class="lbl first">', '<p data-family-section="claude" class="lbl first">'), 1),
    ("a picker link pointing elsewhere", edit(PAGE, '<a href="#chatgpt" data-family-link="chatgpt">', '<a href="#gemini" data-family-link="chatgpt">'), 1),
    ("a picker link with aria-current", edit(PAGE, '<a href="#claude" data-family-link="claude">', '<a href="#claude" data-family-link="claude" aria-current="true">'), 1),
    ("a picker link outside the list", edit(PAGE, '<li><a href="#other-ai" data-family-link="other-ai">Other AI systems</a></li></ul>', '</ul><a href="#other-ai" data-family-link="other-ai">Other AI systems</a>'), 1),
    ("the reset button shown", edit(PAGE, "data-picker-reset hidden>", "data-picker-reset>"), 1),
    ("the picker status removed", edit(PAGE, " data-picker-status></p>", "></p>"), 1),
    ("the assurance id removed", edit(PAGE, '<h2 id="assurance">', "<h2>"), 1),
    ("the get id renamed", edit(PAGE, '<h2 id="get">', '<h2 id="cl-get">'), 1),
    ("the pick id removed", edit(PAGE, 'id="pick"', 'id="pick-gone"'), 1),
    ("an inline script", edit(PAGE, "</main>", "<script>alert(1)</script></main>"), 1),
    ("an inline style", edit(PAGE, '<p class="lbl first">', '<p style="x" class="lbl first">'), 1),
    ("an on* handler", edit(PAGE, '<p class="lbl first">', '<p onclick="x()" class="lbl first">'), 1),
    ("I1: an application/x-javascript script",
        edit(PAGE, "</main>", '<script type="application/x-javascript">alert(1)</script></main>'), 1),
    ("I2B: src= inside another attribute's quoted value",
        edit(PAGE, "</main>", "<script title='src=\"/install/\"'>alert(1)</script></main>"), 1),
    ("I3: an event handler after a slash", edit(PAGE, "</main>", '<span/onclick="alert(1)">x</span></main>'), 1),
    ("P2: a handler after a </noscript> inside an attribute", edit(PAGE, "</main>",
        "<noscript><p title=\"</noscript><img src=x title='>' onerror=alert(1)>\"></p></noscript></main>"), 1),
    ("a script from another origin", edit(PAGE, "</head>", '<script src="https://example.com/x.js" defer></script>\n</head>'), 1),
    ("baseline.css without its version token", edit(PAGE, "baseline.css?v=", "baseline.css?x="), 1),
    ("select.js not loaded", edit(PAGE, "select.js?v=", "select-gone.js?v="), 1),
    ("a baseline script without its version token", edit(PAGE, "</head>", '<script src="/assets/baseline/rail.js" defer></script>\n</head>'), 1),
    ("a baseline script without defer", edit(PAGE, "</head>", '<script src="/assets/baseline/rail.js?v=1.3.0"></script>\n</head>'), 1),
    ("a script from outside the baseline", edit(PAGE, "</head>", '<script src="/assets/other.js?v=1.3.0" defer></script>\n</head>'), 1),
    ("the retired install script", edit(PAGE, "</head>", '<script src="/js/install.js?v=20260101-1" defer></script>\n</head>'), 1),
    ("a baseline script under the old draft path", edit(PAGE, "</head>", '<script src="/draft/assets/baseline/rail.js?v=1.3.0" defer></script>\n</head>'), 1),
    ("rail.js with its token and defer", edit(PAGE, "</head>", '<script src="/assets/baseline/rail.js?v=1.3.0" defer></script>\n</head>'), 0),
    ("the scheme.js tag missing", edit(PAGE, SCHEME + "\n", ""), 1),
    ("the scheme.js tag with defer", edit(PAGE, SCHEME, SCHEME.replace('"></script>', '" defer></script>')), 1),
    ("the scheme.js tag with async", edit(PAGE, SCHEME, SCHEME.replace('"></script>', '" async></script>')), 1),
    ("the scheme.js tag with src before data-cfasync", edit(PAGE, SCHEME,
        '<script src="/assets/baseline/scheme.js?v=1.6.0" data-cfasync="false"></script>'), 1),
    ("the scheme.js tag after the first stylesheet", both(edit(PAGE, SCHEME + "\n", ""),
        edit(PAGE, "</head>", SCHEME + "\n</head>")), 1),
    ("the scheme.js tag twice", edit(PAGE, SCHEME, SCHEME + SCHEME), 1),
    ("a second scheme.js with defer", edit(PAGE, "</head>",
        '<script src="/assets/baseline/scheme.js?v=1.6.0" defer></script>\n</head>'), 1),
    ("a second scheme.js in upper case with a character reference", edit(PAGE, "</head>",
        '<SCRIPT SRC="/assets/baseline/sch&#101;me.js?v=1.6.0" defer></SCRIPT>\n</head>'), 1),
    ("a second scheme.js with spaces around =", edit(PAGE, "</head>",
        '<script src = "/assets/baseline/scheme.js?v=1.6.0" defer></script>\n</head>'), 1),
    ("an upper-case stylesheet before the scheme.js tag", edit(PAGE, SCHEME,
        '<LINK REL="stylesheet" HREF="/assets/baseline/fonts.css?v=1.6.0">\n' + SCHEME), 1),
    ("a stylesheet before the scheme.js tag as the first of 2 rel attributes", edit(PAGE, SCHEME,
        '<LINK REL="stylesheet" REL="icon" HREF="/assets/baseline/fonts.css?v=1.6.0">\n' + SCHEME), 1),
    ("the scheme.js tag and the stylesheets moved into the body, in order", into_body(SCHEME), 1),
    ("the stylesheets moved into the body, after the scheme.js tag", into_body(FONTS), 1),
    ("the scheme.js tag and the stylesheets in a second head inside the body", into_body(SCHEME, "<head>\n", "</head>\n"), 1),
    ("a later stylesheet moved into the body, after the first", into_body(LATER), 1),
    ("a later stylesheet in upper case at the end of the body", edit(PAGE, "</body>",
        '<LINK REL="stylesheet" HREF="/assets/baseline/baseline.css?v=1.6.0">\n</body>'), 1),
    ("a later stylesheet in a second head after the body", both(edit(PAGE, LATER + "\n", ""),
        edit(PAGE, "</body>\n", "</body>\n<head>\n" + LATER + "\n</head>\n")), 1),
    ("a second element with data-scheme-toggle, a button in the content", edit(PAGE, "</main>",
        '<p><button class="scheme" type="button" data-scheme-toggle hidden><span class="vh">Dark mode</span></button></p></main>'), 1),
    ("a family section hidden by the first of 2 class attributes", edit(PAGE, '<section id="claude" data-family-section="claude">',
        '<section id="claude" data-family-section="claude" class="visually-hidden" class="x">'), 1),
    ("fonts.css loaded only inside a comment", edit(PAGE, FONTS, "<!--" + FONTS + "-->"), 1),
    ("rail.js with another attribute", edit(PAGE, "</head>",
        '<script src="/assets/baseline/rail.js?v=1.3.0" type="module" defer></script>\n</head>'), 1),
    ("site.css without its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?w=1">\n</head>'), 1),
    ("site.css with its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?v=0123456789ab">\n</head>'), 0),
    ("site.css without its token beside a token inside a comment", edit(PAGE, "</head>",
        '<!--<link rel="stylesheet" href="/assets/site.css?v=0123456789ab">--><link rel="stylesheet" href="/assets/site.css?w=1">\n</head>'), 1),
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


def statement_problems() -> list[str]:
    """The gate's docstring names exactly the scripts that BASELINE_SCRIPTS holds."""
    spec = importlib.util.spec_from_file_location("check_install_page", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    listed = re.search(r"``BASELINE_SCRIPTS``: (.*?)\)", module.__doc__, re.S)
    names = tuple(re.findall(r"``([a-z]+\.js)``", listed.group(1))) if listed else ()
    if names != module.BASELINE_SCRIPTS:
        return [f"the docstring lists BASELINE_SCRIPTS as {names}; the code holds {module.BASELINE_SCRIPTS}"]
    return []


def main() -> int:
    failures: list[str] = statement_problems()
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
    print(f"test-install-page: all {len(CASES) + 1} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
