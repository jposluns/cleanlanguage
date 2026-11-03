#!/usr/bin/env python3
"""Tests for tools/check-install-page.py: the install pages' contract and the site-wide policy.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault to the install page, a family page, or
site/_headers, runs the gate there as a separate process and asserts its exit
code. Exit 0 when every case passes; 1 otherwise, naming each failing case.
Each of RESIDUALS is a fault the gate passes, such as markup in which a browser
hides or empties what the gate checks; it must exit 0, and the gate's docstring
must name it, so that what the gate says it checks cannot outgrow its code
unnoticed.

It also reads the stylesheets every install page loads (fonts.css, palettes.css
and baseline.css under site/assets/baseline/) and fails when a rule whose
selector list holds a bare single class, such as ``.only-dark``, hides it
(``display: none``, ``visibility: hidden`` or ``collapse``, a ``clip: rect(...)``
as ``.vh`` uses, or a negative ``top`` or ``left`` on an absolute or fixed
position) and the class is in neither the gate's HIDING_CLASSES nor
EXEMPT_CLASSES below. The parser is deliberately small: it reads no compound,
descendant or attribute selector, and it fails when a stylesheet cannot be
read, has an unclosed comment or unbalanced braces, or holds no rule.
"""

from __future__ import annotations

import ast
import importlib.util
import re
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
CLAUDE_LINK = '<a class="btn inline" id="claude" href="/install/claude/">Claude</a>'
SELECT = "/assets/baseline/select.js?v=1.3.0"
ROW = '<p><a class="btn inline" id="claude"'
ROW_END = OTHER_LINK + "</p>"
STEPS = '<ol class="steps">'
STYLESHEETS = ["site/assets/baseline/fonts.css", "site/assets/baseline/palettes.css", "site/assets/baseline/baseline.css"]
# Classes a stylesheet may hide as a bare single class although the gate does not refuse them. Add 1 only with a
# comment saying why no install page can carry it on a checked element or an ancestor. None qualifies today.
EXEMPT_CLASSES: tuple[str, ...] = ()
BARE_CLASS = re.compile(r"\.(-?[_a-zA-Z][_a-zA-Z0-9-]*)")


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


def wrap(relative: str, start: str, end: str, before: str, after: str):
    """Put before ahead of the first start and after behind the first end, so the markup between sits inside."""
    return both(edit(relative, start, before + start), edit(relative, end, end + after))


def decoy(relative: str):
    """Load baseline.css without its token, and keep the tokened tag only in a comment."""
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        tag = re.search(r'<link rel="stylesheet" href="/assets/baseline/baseline\.css\?v=[^"]*">', text).group(0)
        path.write_text(text.replace(tag, tag.replace("?v=", "?x=") + "<!-- " + tag + " -->", 1), encoding="utf-8")
    return apply


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
    ("a family link with the class vh", edit(PAGE, '<a class="btn inline" id="gemini"', '<a class="btn inline vh" id="gemini"'), 1),
    ("the button row with the class vh", edit(PAGE, '<p><a class="btn inline" id="claude"', '<p class="vh"><a class="btn inline" id="claude"'), 1),
    ("the button row with the class only-dark",
        edit(PAGE, '<p><a class="btn inline" id="claude"', '<p class="only-dark"><a class="btn inline" id="claude"'), 1),
    ("the button row with the class skip",
        edit(PAGE, '<p><a class="btn inline" id="claude"', '<p class="skip"><a class="btn inline" id="claude"'), 1),
    ("a family link outside the button row", both(
        edit(PAGE, " " + OTHER_LINK, ""), edit(PAGE, '<p class="lbl blk">Scope</p>', f"<p>{OTHER_LINK}</p>\n" + '<p class="lbl blk">Scope</p>')), 1),
    ("a family link after Get Clean Language", both(
        edit(PAGE, " " + OTHER_LINK, ""), edit(PAGE, '<h2 id="get">Get Clean Language</h2>', f'<h2 id="get">Get Clean Language</h2>\n<p>{OTHER_LINK}</p>')), 1),
    ("a family link with no label", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><")), 1),
    ("a family link whose only label is in a hidden span",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><span hidden>Claude</span><")), 1),
    ("a family link whose only label is in a vh span",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", '><span class="vh">Claude</span><')), 1),
    ("a family link labelled only with U+200B", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">" + chr(0x200B) + "<")), 1),
    ("a family link labelled only with &nbsp;", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">&nbsp;<")), 1),
    ("a family link whose label is in a later link", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><a>Claude</a><")), 1),
    ("a family link whose label follows a later link", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><a></a>Claude<")), 1),
    ("a family link whose only label is a structured-data script", edit(PAGE, CLAUDE_LINK,
        CLAUDE_LINK.replace(">Claude<", '><script type="application/ld+json">"Claude"</script><')), 1),
    # A browser renders the content of each only as fallback or in a control, so it hides here.
    *[(f"a family link whose only label is in {tag}",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", f"><{tag}>Claude</{tag}><")), 1)
        for tag in ("audio", "canvas", "meter", "object", "progress", "select", "video")],
    # Check 5 refuses each of these, whose text a browser does not render.
    ("a family link whose only label is in a style element",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><style>Claude</style><")), 1),
    ("a family link whose only label is in an SVG desc",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><svg><desc>Claude</desc></svg><")), 1),
    ("a family link whose label is in a span", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><span>Claude</span><")), 0),
    ("a family link with a label and a hidden span",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", '>Claude<span class="vh"> setup</span><')), 0),
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
    ("a family page step list with the class vh", edit(CHATGPT, '<ol class="steps">', '<ol class="steps vh">'), 1),
    ("a family page step list with the class only-dark", edit(COPILOT, '<ol class="steps">', '<ol class="steps only-dark">'), 1),
    ("a family page step list with the class skip", edit(CLAUDE, '<ol class="steps">', '<ol class="skip steps">'), 1),
    ("a family page with no verified line", edit(COPILOT, '<p class="verified">', "<p>"), 1),
    ("a family page verified line with the class vh", edit(GEMINI, '<p class="verified">', '<p class="verified vh">'), 1),
    ("a family page heading hidden", edit(CLAUDE, "<h1>", '<h1 class="vh">'), 1),
    ("a family page heading inside a vh wrapper", both(
        edit(COPILOT, "<h1>", '<div class="vh"><h1>'), edit(COPILOT, "</h1>", "</h1></div>")), 1),
    ("a family page heading with the class visually-hidden", edit(OTHER, "<h1>", '<h1 class="visually-hidden">'), 1),
    ("a family page heading whose classes only contain vh", edit(CLAUDE, "<h1>", '<h1 class="vhx pre-vh">'), 0),
    ("a family page heading with the class only-dark", edit(CLAUDE, "<h1>", '<h1 class="only-dark">'), 1),
    ("a family page heading with the class skip", edit(GEMINI, "<h1>", '<h1 class="skip">'), 1),
    ("a family page heading whose classes only contain only-dark or skip", edit(CHATGPT, "<h1>", '<h1 class="only-darker skip-link">'), 0),
    ("a family page heading emptied", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>​</h1>"), 1),
    ("a family page inside a hidden wrapper", edit(GEMINI, '<div class="doc">', '<div class="doc" inert>'), 1),
    ("the button row with popover", edit(PAGE, ROW, '<p popover><a class="btn inline" id="claude"'), 1),
    ("the button row inside a dialog without open", wrap(PAGE, ROW, ROW_END, "<dialog>", "</dialog>"), 1),
    ("the button row inside a closed details", wrap(PAGE, ROW, ROW_END, "<details><summary>Pick</summary>", "</details>"), 1),
    ("the button row inside a datalist", wrap(PAGE, ROW, ROW_END, "<datalist>", "</datalist>"), 1),
    ("the button row inside a noscript", wrap(PAGE, ROW, ROW_END, "<noscript>", "</noscript>"), 1),
    ("the button row inside an rp", wrap(PAGE, ROW, ROW_END, "<rp>", "</rp>"), 1),
    ("the button row inside a title", wrap(PAGE, ROW, ROW_END, "<title>", "</title>"), 1),
    ("the button row with data-popover", edit(PAGE, ROW, '<p data-popover><a class="btn inline" id="claude"'), 0),
    ("the button row inside an open dialog", wrap(PAGE, ROW, ROW_END, "<dialog open>", "</dialog>"), 0),
    ("a family page heading with popover", edit(CLAUDE, "<h1>", '<h1 popover="manual">'), 1),
    ("a family page heading inside a dialog without open", wrap(CHATGPT, "<h1>", "</h1>", "<dialog>", "</dialog>"), 1),
    ("a family page heading inside a closed details", wrap(GEMINI, "<h1>", "</h1>", "<details>", "</details>"), 1),
    ("a family page heading inside a datalist", wrap(COPILOT, "<h1>", "</h1>", "<datalist>", "</datalist>"), 1),
    ("a family page heading inside a noscript", wrap(OTHER, "<h1>", "</h1>", "<noscript>", "</noscript>"), 1),
    ("a family page heading inside an rp", wrap(CLAUDE, "<h1>", "</h1>", "<rp>", "</rp>"), 1),
    ("a family page heading inside a title", wrap(CHATGPT, "<h1>", "</h1>", "<title>", "</title>"), 1),
    ("a family page heading in the summary of a closed details",
        wrap(GEMINI, "<h1>", "</h1>", "<details><summary>", "</summary><p>More</p></details>"), 0),
    ("a family page heading after the summary of a closed details",
        wrap(COPILOT, "<h1>", "</h1>", "<details><summary>More</summary>", "</details>"), 1),
    ("a family page heading inside an open dialog", wrap(OTHER, "<h1>", "</h1>", '<dialog open="">', "</dialog>"), 0),
    ("a family page step list with popover", edit(OTHER, STEPS, '<ol class="steps" popover>'), 1),
    ("a family page step list inside a dialog without open", wrap(OTHER, STEPS, "</ol>", "<dialog>", "</dialog>"), 1),
    ("a family page step list inside a closed details",
        wrap(OTHER, STEPS, "</ol>", "<details><summary>Steps</summary>", "</details>"), 1),
    ("a family page step list inside a datalist", wrap(OTHER, STEPS, "</ol>", "<datalist>", "</datalist>"), 1),
    ("a family page step list inside a noscript", wrap(OTHER, STEPS, "</ol>", "<noscript>", "</noscript>"), 1),
    ("a family page step list inside an rp", wrap(OTHER, STEPS, "</ol>", "<rp>", "</rp>"), 1),
    ("a family page step list inside a title", wrap(OTHER, STEPS, "</ol>", "<title>", "</title>"), 1),
    ("a family page step list inside a template", wrap(OTHER, STEPS, "</ol>", "<template>", "</template>"), 1),
    ("a family page step list hidden until found", edit(OTHER, STEPS, '<ol class="steps" hidden="until-found">'), 1),
    ("a family page step list inside an open details",
        wrap(OTHER, STEPS, "</ol>", "<details open><summary>Steps</summary>", "</details>"), 0),
    ("a family page step list with data-popover", edit(OTHER, STEPS, '<ol class="steps" data-popover="auto">'), 0),
    # A browser ignores "/>" on an element that is not void, so each of these stays open and hides what follows.
    ("the button row after <div hidden/>", edit(PAGE, ROW, "<div hidden/>" + ROW), 1),
    ('the button row after <div class="vh"/>', edit(PAGE, ROW, '<div class="vh"/>' + ROW), 1),
    ("the button row after <details/>", edit(PAGE, ROW, "<details/>" + ROW), 1),
    ("the button row after <br/>", edit(PAGE, ROW, "<br/>" + ROW), 0),
    ("a family page step list after <div hidden/>", edit(OTHER, STEPS, "<div hidden/>" + STEPS), 1),
    ('a family page step list after <div class="vh"/>', edit(GEMINI, STEPS, '<div class="vh"/>' + STEPS), 1),
    ("a family page step list after <details/>", edit(COPILOT, STEPS, "<details/>" + STEPS), 1),
    ("a family page step list after <br/>", edit(CLAUDE, STEPS, "<br/>" + STEPS), 0),
    ("a family page heading whose only text is in a hidden span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1><span hidden>ChatGPT</span></h1>"), 1),
    ("a family page heading whose only text is a structured-data script",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1><script type="application/ld+json">"ChatGPT"</script></h1>'), 1),
    ("a family page heading whose only text is a MathML annotation", edit(CHATGPT, "<h1>ChatGPT</h1>",
        "<h1><math><semantics><mi></mi><annotation>ChatGPT</annotation></semantics></math></h1>"), 1),
    ("a family page heading with visible text and a hidden span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1>ChatGPT<span class="vh"> setup</span></h1>'), 0),
    *[(f"a family page heading made only of U+{code:04X}", edit(CHATGPT, "<h1>ChatGPT</h1>", f"<h1>{chr(code)}</h1>"), 1)
        for code in (0x061C, *range(0x202A, 0x202F), *range(0x2066, 0x206A))],
    ("a family page heading made only of U+0000", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>\0</h1>"), 1),
    ("a family page heading closed by an h2 start tag", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1><h2>ChatGPT</h2></h1>"), 1),
    ("a family page heading closed by an h2 end tag", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1></h2>ChatGPT</h1>"), 1),
    ("the button row with the class vh before a second class attribute",
        edit(PAGE, ROW, '<p class="vh" class="row"><a class="btn inline" id="claude"'), 1),
    ("the install page with a later hidden body start tag", edit(PAGE, "</main>", "</main><body hidden>"), 1),
    ("a family page with a later html start tag with the class vh", edit(CLAUDE, "</main>", '</main><html class="vh">'), 1),
    ("the install page with a frameset start tag", edit(PAGE, "</head>", "</head><frameset></frameset>"), 1),
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
    ("select.js in an upper-case tag", edit(PAGE, "</head>", f'<SCRIPT SRC="{SELECT}" defer></SCRIPT>\n</head>'), 1),
    ("select.js with a space before the =", edit(PAGE, "</head>", f'<script src ="{SELECT}" defer></script>\n</head>'), 1),
    ("select.js after a > in a quoted value", edit(PAGE, "</head>", f'<script title=">" src="{SELECT}" defer></script>\n</head>'), 1),
    ("rail.js without defer in an upper-case tag", edit(PAGE, "</head>", '<SCRIPT SRC="/assets/baseline/rail.js?v=1.3.0"></SCRIPT>\n</head>'), 1),
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
# Faults the gate passes, and the words of the gate's docstring that name each (compared with runs of whitespace
# read as 1 space).
RESIDUALS = [
    ("the button row after <span hidden><div></span>", edit(PAGE, ROW, "<span hidden><div></span>" + ROW),
        "after ``<span hidden><div></span>`` the ``span`` stays open"),
    ("the button row after <p><div hidden></p>", edit(PAGE, ROW, "<p><div hidden></p>" + ROW),
        "after ``<p><div hidden></p>`` the ``div`` stays open"),
    ("a div between 2 family links", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK + "<div></div>"),
        "``<div></div>`` between 2 family links leaves the later links outside it"),
    ("a family link with another family's label", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">ChatGPT<")),
        "a wrong family link label (another family's, say)"),
    ("a family link labelled only with U+034F", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">" + chr(0x034F) + "<")),
        "or family link label made only of an invisible character"),
    ("a family page whose links back to #get are hidden", edit(GEMINI, 'href="/install/#get"', 'href="/install/#get" hidden', every=True),
        "links, hidden or not, to ``/install/#get``"),
    ("a family page whose links back to #get are empty",
        edit(GEMINI, '<a href="/install/#get">Get Clean Language</a>', '<a href="/install/#get"></a>', every=True),
        "an empty link back to the downloads or the test"),
    ("a family page with an empty verified line", edit(GEMINI, '<p class="verified">', '<p class="verified"></p><p>'),
        "an empty ``p.verified``"),
    ("a family page with an empty step list", edit(OTHER, STEPS, STEPS + "</ol><ol>"), "an empty ``ol.steps``"),
    ("a family page with 1 setup step hidden", edit(OTHER, STEPS + "<li>", STEPS + "<li hidden>"), "not its steps or their wording"),
    ("a family page with 1 setup step dropped",
        edit(OTHER, STEPS + '<li><span>Save the file, or copy everything from the <a href="/instructions/">instructions page</a>.</span></li>', STEPS),
        "not its steps or their wording"),
    ("the tokened baseline.css tag only in a comment", decoy(PAGE), "matched as text, so a tag in a comment counts"),
]


def hides(declarations: str) -> bool:
    """True when the declarations hide, clip, or move the element off-screen as the template's own rules do."""
    props: dict[str, str] = {}
    for declaration in declarations.split(";"):
        name, colon, value = declaration.partition(":")
        if colon:
            props[name.strip().lower()] = re.sub(r"!\s*important", "", value.lower()).strip()
    offscreen = any(props.get(side, "").startswith("-") for side in ("top", "left"))
    return (
        props.get("display") == "none"
        or props.get("visibility") in ("hidden", "collapse")
        or props.get("clip", "").startswith("rect(")
        or (props.get("position") in ("absolute", "fixed") and offscreen)
    )


def stylesheet_problems() -> list[str]:
    """Each bare single class the pages' stylesheets hide is in the gate's HIDING_CLASSES or in EXEMPT_CLASSES."""
    try:
        spec = importlib.util.spec_from_file_location("check_install_page", GATE)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        listed = set(gate.HIDING_CLASSES) | set(EXEMPT_CLASSES)
    except Exception as error:
        return [f"HIDING_CLASSES could not be read from tools/{GATE.name}: {error!r}"]
    problems: list[str] = []
    for relative in STYLESHEETS:
        try:
            css = (REPO_ROOT / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            problems.append(f"{relative} could not be read: {error}")
            continue
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        depth = 0
        for char in css:
            depth += {"{": 1, "}": -1}.get(char, 0)
            if depth < 0:
                break
        if "/*" in css or depth != 0:
            problems.append(f"{relative} has an unclosed comment or unbalanced braces; it cannot be read.")
            continue
        rules = re.findall(r"([^{};]*)\{([^{}]*)\}", css)
        if not rules:
            problems.append(f"{relative} holds no rule; it cannot be read.")
        for prelude, declarations in rules:
            selectors = " ".join(prelude.split())
            if selectors.startswith("@") or not hides(declarations):
                continue
            for selector in selectors.split(","):
                bare = BARE_CLASS.fullmatch(selector.strip())
                if bare and bare.group(1) not in listed:
                    problems.append(
                        f"{relative}: the rule {selectors!r} hides the bare class .{bare.group(1)}, which is in neither "
                        f"HIDING_CLASSES of tools/{GATE.name} nor EXEMPT_CLASSES of this test."
                    )
    return problems


def main() -> int:
    failures: list[str] = [f"the stylesheets: {problem}" for problem in stylesheet_problems()]
    doc = " ".join((ast.get_docstring(ast.parse(GATE.read_text(encoding="utf-8"))) or "").split())
    for name, _, words in RESIDUALS:
        if words not in doc:
            failures.append(f"{name}: the docstring of tools/{GATE.name} does not name it ({words!r}).")
    for name, fault, expected in CASES + [(name, fault, 0) for name, fault, _ in RESIDUALS]:
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
    print(f"test-install-page: all {len(CASES)} cases, the {len(RESIDUALS)} named residuals and the stylesheet check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
