#!/usr/bin/env python3
"""Check the install page keeps its family sections static, visible, and complete.

``site/install/index.html`` shows five AI-family setup sections (Claude, ChatGPT,
Gemini, Copilot, and other AI systems). A progressive-enhancement filter,
``site/js/install.js``, lets a reader narrow the page to one family: it sets a
``data-family`` attribute on the root element, and CSS keyed on that attribute
collapses the other family sections. The point is that this is an enhancement.
With JavaScript blocked by the site's Content-Security-Policy, failed, or switched
off, the attribute is never set, the guarded rule is inert, and all five sections
show.

This is a TRIPWIRE for the common regressions, not a browser and not a CSS engine.
A regex cannot faithfully model CSS selector matching or the HTML tree, so this
check verifies what it can verify reliably and names the rest as the reviewer's
and the cross-family QA's job.

What it verifies
----------------

1. Each family id exists exactly once on a ``<section id=X data-family-section=X>``
   with an ``<h2>`` that has visible (non-whitespace, non-zero-width) text, no id
   in the document is duplicated, and the general sections ``spelling``,
   ``how-to-use``, and ``assurance`` exist.
2. No family section carries, on itself, ``hidden``, ``inert``,
   ``aria-hidden="true"`` (any case), or the ``visually-hidden`` class.
3. No pre-set filter state: the root has no ``data-family``, no picker link has
   ``aria-current``, and exactly one ``family-reset`` button exists and is hidden.
4. Each family has exactly one picker ``<a data-family-link=X href="#X">`` inside
   the ``.platform-actions`` group.
5. No inline executable ``<script>``, ``style`` attribute, or ``on*`` handler.
6. A guarded collapse rule is present: some rule whose root condition is a positive
   ``html[data-family]`` or ``html[data-family=...]`` (not a longer attribute name
   such as ``data-family-mode``, and not inside a negation) hides a
   ``data-family-section``.
7. Heuristic: a ``display:none`` / ``visibility:hidden`` rule whose subject names a
   family marker or is a ``section`` type selector, that does not exclude the family
   marker and is not guarded, is flagged. Selector matching is case-insensitive.
8. ``site/_headers`` keeps ``script-src 'self'`` and ``style-src 'self'`` with no
   ``unsafe-inline``, and an immutable ``Cache-Control`` for ``/js/install.js``.

What it does NOT verify (the reviewer's and cross-family QA's job)
-----------------------------------------------------------------

It is not a CSS engine or a browser. It does NOT catch: a hiding ANCESTOR (a
wrapping ``hidden`` div, a closed ``<details>``, a ``<template>``); a custom CLASS
that hides, clips, zeroes opacity, or positions a section off-screen; a DESCENDANT
wipe such as ``section[data-family-section] > * { display: none }`` that empties a
section; hiding a family by a form the heuristic does not name (``#claude``,
``[id="claude"]``, or an attribute value that only a browser resolves); a guard
written other than as the plain ``html[data-family]`` (an ``:is()``/``:where()``
guard, or a negation-of-negation, is not analyzed and should be written plainly);
an uppercase attribute VALUE (selector names are folded, values are not); or a
path-scoped header override in ``_headers`` (only the global CSP line is read). The
inline-code and CSS scans are regex over a flat, unnested stylesheet whose rule
bodies hold no literal braces; adversarial selector or attribute-string shapes may
still slip through, and a cross-family review remains the backstop.

Exit codes:
  0  the page and its rules are static, complete, and correctly guarded
  1  a family section, picker link, guard, or header discipline regressed
  3  a file could not be read, or the expected markup was not found
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "site" / "install" / "index.html"
STYLES = REPO_ROOT / "site" / "styles.css"
HEADERS = REPO_ROOT / "site" / "_headers"

FAMILIES = ["claude", "chatgpt", "gemini", "copilot", "other-ai"]
GENERAL_IDS = ["spelling", "how-to-use", "assurance"]
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "wbr", "col"}
ZERO_WIDTH = "​‌‍﻿ "

SCRIPT_TAG = re.compile(r"<script([^>]*)>", re.I)
SCRIPT_ATTR = re.compile(r'([A-Za-z][\w:.-]*)\s*=\s*"([^"]*)"')
EXECUTABLE_TYPES = {"", "module", "text/javascript", "application/javascript", "text/ecmascript"}
INLINE_STYLE = re.compile(r"<[^>]+\sstyle\s*=", re.I)
INLINE_HANDLER = re.compile(r"<[^>]+\son[a-z]+\s*=", re.I)
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
PSEUDO_ARG = re.compile(r":(?:not|is|where|matches)\([^()]*\)", re.I)
GUARD = re.compile(r"html\[data-family\s*(?:[~^$*|]?=|\])")


def die(message: str) -> None:
    print(f"check-install-page: {message}", file=sys.stderr)
    raise SystemExit(3)


def is_hiding_element(attrs: dict[str, str]) -> bool:
    classes = attrs.get("class", "").split()
    return (
        "hidden" in attrs
        or "inert" in attrs
        or attrs.get("aria-hidden", "").lower() == "true"
        or "visually-hidden" in classes
    )


def has_visible_text(data: str) -> bool:
    return bool(data.translate({ord(c): None for c in ZERO_WIDTH}).strip())


class InstallParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict] = []
        self.html_attrs: dict[str, str] = {}
        self.family_count = {f: 0 for f in FAMILIES}
        self.family_has_h2 = {f: False for f in FAMILIES}
        self.family_hidden_self: list[str] = []
        self.other_family_carriers: list[str] = []
        self.id_counts: Counter = Counter()
        self.ids: set[str] = set()
        self.family_links: dict[str, int] = {}
        self.family_link_href: dict[str, str] = {}
        self.family_links_outside_pa: set[str] = set()
        self.family_links_current: set[str] = set()
        self.reset_count = 0
        self.reset_hidden_count = 0
        self._h2_family: str | None = None

    def _nearest_family(self) -> str | None:
        for frame in reversed(self.stack):
            if frame["family"]:
                return frame["family"]
        return None

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k.lower(): (v if v is not None else "") for k, v in attrs_list}
        if tag == "html":
            self.html_attrs = attrs
        if "id" in attrs:
            self.id_counts[attrs["id"]] += 1
            self.ids.add(attrs["id"])
        in_pa = any("platform-actions" in frame["cls"].split() for frame in self.stack)
        fam_here = None

        if "data-family-section" in attrs:
            fam = attrs["data-family-section"]
            if tag == "section" and attrs.get("id") == fam and fam in FAMILIES:
                self.family_count[fam] += 1
                fam_here = fam
                if is_hiding_element(attrs):
                    self.family_hidden_self.append(fam)
            else:
                self.other_family_carriers.append(
                    f"<{tag} data-family-section={attrs.get('data-family-section')!r}>"
                )

        if tag == "a" and "data-family-link" in attrs:
            fam = attrs["data-family-link"]
            self.family_links[fam] = self.family_links.get(fam, 0) + 1
            self.family_link_href[fam] = attrs.get("href", "")
            if not in_pa:
                self.family_links_outside_pa.add(fam)
            if "aria-current" in attrs:
                self.family_links_current.add(fam)

        if tag == "button" and attrs.get("id") == "family-reset":
            self.reset_count += 1
            if "hidden" in attrs:
                self.reset_hidden_count += 1

        if tag == "h2":
            self._h2_family = self._nearest_family()

        if tag not in VOID:
            self.stack.append({"tag": tag, "family": fam_here, "cls": attrs.get("class", "")})

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._h2_family = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._h2_family and has_visible_text(data):
            self.family_has_h2[self._h2_family] = True


def executes_inline(text: str) -> bool:
    for tag in SCRIPT_TAG.finditer(text):
        attributes = {k.lower(): v for k, v in SCRIPT_ATTR.findall(tag.group(1))}
        if "src" in attributes:
            continue
        if attributes.get("type", "").strip().lower() in EXECUTABLE_TYPES:
            return True
    return False


def hides(body: str) -> bool:
    b = re.sub(r"\s+", "", body).lower()
    return "display:none" in b or "visibility:hidden" in b or "visibility:collapse" in b


def _mask(s: str):
    stash: list[str] = []

    def m(mt: "re.Match[str]") -> str:
        stash.append(mt.group(0))
        return f"\x00{len(stash) - 1}\x00"

    s = re.sub(r"\[[^\]]*\]", m, s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r":[a-zA-Z-]+\([^()]*\)", m, s)
    return s, stash


def _unmask(s: str, stash: list[str]) -> str:
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\x00(\d+)\x00", lambda x: stash[int(x.group(1))], s)
    return s


def subject(branch: str) -> str:
    masked, stash = _mask(branch.strip())
    parts = re.split(r"\s*[>+~]\s*|\s+", masked)
    last = parts[-1] if parts and parts[-1] else masked
    return _unmask(last, stash)


def positive_guard(branch: str) -> bool:
    stripped = branch
    prev = None
    while prev != stripped:
        prev = stripped
        stripped = PSEUDO_ARG.sub("", stripped)
    return bool(GUARD.search(stripped))


def excludes_family(branch: str) -> bool:
    for m in re.finditer(r":not\(([^()]*)\)", branch):
        arg = m.group(1)
        if "data-family-section" in arg or any(f"#{f}" in arg for f in FAMILIES):
            return True
    return False


def targets_family(subj: str) -> bool:
    if "data-family-section" in subj:
        return True
    return subj == "section" or subj.startswith("section:")


def scan_css(text: str, problems: list[str]) -> None:
    stripped = CSS_COMMENT.sub("", text)
    collapse_found = False
    for selector, body in CSS_RULE.findall(stripped):
        if not hides(body):
            continue
        masked_sel, stash = _mask(selector)
        for masked_branch in [b for b in masked_sel.split(",") if b.strip()]:
            branch = _unmask(masked_branch, stash).strip().lower()
            if not branch:
                continue
            if excludes_family(branch):
                continue
            if not targets_family(subject(branch)):
                continue
            if positive_guard(branch):
                collapse_found = True
            else:
                problems.append(
                    "a stylesheet rule hides a family section without the "
                    f"html[data-family] guard, so it would vanish with no JavaScript: "
                    f"selector {branch!r}. Guard it with html[data-family] ... "
                    "[data-family-section]."
                )
    if not collapse_found:
        problems.append(
            "no guarded collapse rule found in site/styles.css: a rule keyed on a "
            "positive html[data-family] must hide the non-selected data-family-section, "
            "or the selector feature has silently rotted out of the stylesheet."
        )


def main() -> int:
    for path in (PAGE, STYLES, HEADERS):
        if not path.is_file():
            die(f"{path.relative_to(REPO_ROOT)} does not exist")

    page_text = PAGE.read_text(encoding="utf-8")
    parser = InstallParser()
    parser.feed(page_text)
    problems: list[str] = []

    # 1. family sections static, complete, unique; ids unique
    for fam in FAMILIES:
        n = parser.family_count[fam]
        if n == 0:
            problems.append(
                f"no <section id=\"{fam}\" data-family-section=\"{fam}\"> found; "
                "every family section must be present and statically visible."
            )
        elif n > 1:
            problems.append(f"the {fam} family section appears {n} times; it must appear exactly once.")
        elif not parser.family_has_h2[fam]:
            problems.append(f"the {fam} family section has no <h2> with visible text; it may be an empty stub.")
    for fam in parser.family_hidden_self:
        problems.append(
            f"the {fam} family section carries hidden, inert, aria-hidden, or the "
            "visually-hidden class in the static markup, so it would not appear without JavaScript."
        )
    for extra in parser.other_family_carriers:
        problems.append(
            f"data-family-section appears on an unexpected element {extra}; only the "
            "five family <section> elements may carry it."
        )
    for dup_id, count in sorted(parser.id_counts.items()):
        if count > 1:
            problems.append(
                f"the id \"{dup_id}\" appears {count} times; ids must be unique or "
                "getElementById and the fragment anchors resolve to the wrong element."
            )
    for gid in GENERAL_IDS:
        if gid not in parser.ids:
            problems.append(f"the general section id \"{gid}\" is missing from the page.")

    # 2. picker integrity
    for fam in FAMILIES:
        count = parser.family_links.get(fam, 0)
        if count == 0:
            problems.append(f"no picker link <a data-family-link=\"{fam}\"> found.")
            continue
        if count > 1:
            problems.append(f"the {fam} picker link appears {count} times; it must appear exactly once.")
        href = parser.family_link_href.get(fam, "")
        if href != f"#{fam}":
            problems.append(
                f"the {fam} picker link points at {href!r}, not \"#{fam}\"; the deep "
                "link and the filter would disagree."
            )
    for fam in sorted(parser.family_links_outside_pa):
        problems.append(
            f"the {fam} picker link is not inside the .platform-actions group, so "
            "install.js (which queries '.platform-actions a[data-family-link]') would not find it."
        )

    # 3. no pre-set filter state; exactly one hidden reset
    if "data-family" in parser.html_attrs:
        problems.append(
            "the root <html> element carries data-family in the static markup; the "
            "filter must start unset so the unscripted page shows every family."
        )
    if parser.family_links_current:
        problems.append(
            "a picker link carries aria-current in the static markup "
            f"({', '.join(sorted(parser.family_links_current))}); only install.js may set it."
        )
    if parser.reset_count == 0:
        problems.append('the "Show all AI systems" button (id="family-reset") is missing.')
    elif parser.reset_count > 1:
        problems.append(f'the "Show all AI systems" button (id="family-reset") appears {parser.reset_count} times.')
    elif parser.reset_hidden_count != parser.reset_count:
        problems.append(
            'the "Show all AI systems" button is not hidden in the static markup; it '
            "does nothing without JavaScript and must carry the hidden attribute."
        )

    # 4. no inline code
    if executes_inline(page_text):
        problems.append(
            "the page contains an inline <script>; the CSP is script-src 'self' and it "
            "would be blocked. Move the code to site/js/."
        )
    if INLINE_STYLE.search(page_text):
        problems.append(
            "the page contains an inline style attribute; the CSP is style-src 'self'. "
            "Move the declarations to site/styles.css."
        )
    if INLINE_HANDLER.search(page_text):
        problems.append(
            "the page contains an inline on* event handler; the CSP is script-src 'self' "
            "and it would be blocked. Bind the listener in site/js/."
        )

    # 5. script and stylesheet tokens
    if not re.search(r'src="/js/install\.js\?v=\d{8}-\d+"', page_text):
        problems.append("the page does not reference /js/install.js with a ?v=YYYYMMDD-N token.")
    if not re.search(r'href="/styles\.css\?v=\d{8}-\d+"', page_text):
        problems.append("the page does not reference /styles.css with a ?v=YYYYMMDD-N token.")

    # 6/7. CSS guard scan
    scan_css(STYLES.read_text(encoding="utf-8"), problems)

    # 8. header discipline
    headers = HEADERS.read_text(encoding="utf-8")
    csp_line = next((ln for ln in headers.splitlines() if "Content-Security-Policy:" in ln), "")
    if not csp_line:
        problems.append("site/_headers has no Content-Security-Policy line.")
    else:
        if "script-src 'self'" not in csp_line or "style-src 'self'" not in csp_line:
            problems.append(
                "the CSP no longer names script-src 'self' and style-src 'self'; the "
                "no-inline guarantee this gate relies on is gone."
            )
        if "unsafe-inline" in csp_line:
            problems.append("the CSP now allows unsafe-inline, defeating the inline-code checks.")
    if not re.search(r"/js/install\.js\s*\n\s*Cache-Control:[^\n]*immutable", headers):
        problems.append("site/_headers has no immutable Cache-Control entry for /js/install.js.")

    if problems:
        print("Install page problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        "The install page carries all five family sections statically and visibly, the "
        "picker and reset control are present with no pre-set filter state, no inline code, "
        "and the collapse rule is guarded so the page degrades without JavaScript."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
