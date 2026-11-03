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

This is a TRIPWIRE for the common regressions in the STATIC MARKUP, plus a check
that the collapse rule still exists. It is deliberately NOT a CSS engine. An
earlier version tried to prove that no unguarded stylesheet rule could hide a
family section; three independent adversarial reviews each found different real
bypasses and false positives in that regex heuristic, because a regex cannot model
CSS selector matching. So that heuristic was removed: whether a NEW stylesheet rule
hides a section without the guard is left to review and the cross-family QA, and
this gate instead verifies the markup reliably and confirms the guarded collapse
rule is present.

What it verifies (reliably)
---------------------------

1. Each family id exists exactly once on a ``<section id=X data-family-section=X>``
   with an ``<h2>`` that has visible text, no id in the document is duplicated, and
   the general sections ``spelling``, ``how-to-use``, and ``assurance`` exist.
2. No family section carries, on itself, ``hidden``, ``inert``,
   ``aria-hidden="true"`` (any case), or the ``visually-hidden`` class.
3. No pre-set filter state: the root has no ``data-family``, no picker link has
   ``aria-current``, and exactly one ``family-reset`` button exists and is hidden.
4. Each family has exactly one picker ``<a data-family-link=X href="#X">`` inside
   the ``.platform-actions`` group.
5. No inline executable ``<script>``, ``style`` attribute, or ``on*`` handler.
6. The guarded collapse rule is present: some hiding rule whose selector carries a
   positive, boundary-anchored ``html[data-family]`` / ``html[data-family=...]``
   (not ``.html``/``xhtml``/``data-family-mode``) and names ``data-family-section``.
   This catches the feature being deleted or its guard being renamed.
7. ``site/_headers`` keeps ``script-src 'self'`` and ``style-src 'self'`` with no
   ``unsafe-inline``, and a ``Cache-Control`` entry for ``/js/install.js``.

What it does NOT verify (the reviewer's and cross-family QA's job)
-----------------------------------------------------------------

It is not a CSS engine or a browser. It does NOT detect a NEW stylesheet rule that
hides a family section without the guard (for example ``section[data-family-section]
{ display: none }``), nor a hiding ANCESTOR (a wrapping ``hidden`` div, a closed
``<details>``, a ``<template>``), a custom CLASS that hides/clips/zeroes
opacity/positions off-screen, a DESCENDANT wipe, or hiding by id. Those are visible
regressions a browser check, a reviewer, or the tri-family QA catches; a regex
cannot decide them without false positives that would block valid edits. The
inline-code checks and the collapse-rule scan are regex over a flat, unnested
stylesheet; an exotic heading character or attribute-string shape may still slip
through.

The template page (staged at /draft/)
------------------------------------

The site is being rebuilt on the shared template (baseline), staged at
``site/draft/`` until the owner approves promotion. The template's install page,
``site/draft/install/index.html``, meets the same contract through the selector
markup of the template specification (section 7.12), so it is checked here too:

8. Each family id exists exactly once on a ``<section id=X data-family-section=X>``
   with an ``<h2>`` that has visible text, carries none of the hiding attributes
   in check 2, and no other element carries ``data-family-section``.
9. Exactly 1 ``ul.picker[data-picker]`` holds exactly 1
   ``<a data-family-link=X href="#X">`` per family, none with ``aria-current``;
   no ``data-family-link`` sits outside it; exactly 1 ``data-picker-reset``
   button exists and is ``hidden``; exactly 1 ``data-picker-status`` region exists.
10. The ids ``pick``, ``get``, ``test``, ``how-to-use``, ``spelling`` and
    ``assurance`` exist (existing deep links), and no id is duplicated.
11. No inline executable ``<script>``, ``style`` attribute or ``on*`` handler.
12. Versioned asset tokens: ``fonts.css``, ``palettes.css``, ``baseline.css``,
    ``copy.js`` and ``select.js`` load from the draft's ``assets/baseline/`` with
    ``?v=X.Y.Z``, the scripts with ``defer``; an optional ``site.css`` loads with
    ``?v=`` and 12 hexadecimal characters. Every ``<script>`` the page loads is
    1 of the baseline's 4 scripts (``BASELINE_SCRIPTS``: ``copy.js``,
    ``select.js``, ``search.js``, ``rail.js``) from the draft's
    ``assets/baseline/``, with the same token and ``defer``.
13. ``site/_headers`` has a ``/draft/*`` rule that first detaches the site-wide
    policy (``! Content-Security-Policy``) and then sets exactly the owner's
    draft policy, ``DRAFT_CSP`` below, and ``X-Robots-Tag: noindex``. The owner
    authorized this policy for ``/draft/`` on 2026-11-03 (it carries
    ``'unsafe-inline'`` for Cloudflare's JavaScript Detections), and nothing
    looser: any other ``Content-Security-Policy`` line anywhere in the file,
    outside the first (site-wide) line, fails. The site-wide rule in check 7 is
    unchanged.

At promotion the template page moves to ``site/install/index.html`` and the
live-only checks (``.platform-actions``, ``#family-reset``, ``styles.css``,
``/js/install.js``) retire with the old page.

Exit codes:
  0  the markup is static, complete, and the guarded collapse rule is present
  1  a family section, picker link, id, reset, guard, or header discipline regressed
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

DRAFT_PAGE = REPO_ROOT / "site" / "draft" / "install" / "index.html"

FAMILIES = ["claude", "chatgpt", "gemini", "copilot", "other-ai"]
TEMPLATE_IDS = ["pick", "get", "test", "how-to-use", "spelling", "assurance"]
BASELINE_SCRIPTS = ("copy.js", "select.js", "search.js", "rail.js")
DRAFT_PATTERN = "/draft/*"
# The owner's decision of 2026-11-03 (item 5), authorized for /draft/ only (item 6).
DRAFT_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://ajax.cloudflare.com "
    "https://static.cloudflareinsights.com; connect-src 'self' https://cloudflareinsights.com; "
    "style-src 'self'; font-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
BASELINE_ASSET = r'/draft/assets/baseline/{name}\?v=[0-9]+\.[0-9]+\.[0-9]+"'
GENERAL_IDS = ["spelling", "how-to-use", "assurance"]
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "wbr", "col"}
# Invisible characters a heading might be reduced to: zero-width spaces/joiner/BOM,
# no-break and soft-hyphen, word joiner, and the bidi marks.
ZERO_WIDTH = "​‌‍﻿ ⁠‍‌­"

SCRIPT_TAG = re.compile(r"<script([^>]*)>", re.I)
SCRIPT_ATTR = re.compile(r'([A-Za-z][\w:.-]*)\s*=\s*"([^"]*)"')
EXECUTABLE_TYPES = {"", "module", "text/javascript", "application/javascript", "text/ecmascript"}
INLINE_STYLE = re.compile(r"<[^>]+\sstyle\s*=", re.I)
INLINE_HANDLER = re.compile(r"<[^>]+\son[a-z]+\s*=", re.I)
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
# A positive root guard: html[data-family] or html[data-family=...], anchored so a
# class (.html), a different element (xhtml), or a longer name (data-family-mode)
# does not count.
GUARD = re.compile(r"(?:^|[\s,>+~(])html\[data-family(?:[~^$*|]?=|\])", re.I)


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


def hides(body: str) -> bool:
    b = re.sub(r"\s+", "", body).lower()
    return "display:none" in b or "visibility:hidden" in b or "visibility:collapse" in b


def collapse_rule_present(text: str) -> bool:
    stripped = CSS_COMMENT.sub("", text)
    for selector, body in CSS_RULE.findall(stripped):
        if hides(body) and "data-family-section" in selector.lower() and GUARD.search(selector):
            return True
    return False


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


class TemplateParser(HTMLParser):
    """Collects the selector markup of the template install page (specification 7.12)."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict] = []
        self.family_count = {f: 0 for f in FAMILIES}
        self.family_has_h2 = {f: False for f in FAMILIES}
        self.family_hidden_self: list[str] = []
        self.other_family_carriers: list[str] = []
        self.id_counts: Counter = Counter()
        self.pickers = 0
        self.links: list[tuple[str, str, bool, bool]] = []
        self.resets: list[bool] = []
        self.statuses = 0
        self._h2_family: str | None = None

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k.lower(): (v if v is not None else "") for k, v in attrs_list}
        if "id" in attrs:
            self.id_counts[attrs["id"]] += 1
        fam_here = None
        if "data-family-section" in attrs:
            fam = attrs["data-family-section"]
            if tag == "section" and attrs.get("id") == fam and fam in FAMILIES:
                self.family_count[fam] += 1
                fam_here = fam
                if is_hiding_element(attrs):
                    self.family_hidden_self.append(fam)
            else:
                self.other_family_carriers.append(f"<{tag} data-family-section={fam!r}>")
        if tag == "ul" and "data-picker" in attrs and "picker" in attrs.get("class", "").split():
            self.pickers += 1
        if tag == "a" and "data-family-link" in attrs:
            in_picker = any(frame["picker"] for frame in self.stack)
            self.links.append((attrs["data-family-link"], attrs.get("href", ""), in_picker, "aria-current" in attrs))
        if tag == "button" and "data-picker-reset" in attrs:
            self.resets.append("hidden" in attrs)
        if "data-picker-status" in attrs:
            self.statuses += 1
        if tag == "h2":
            self._h2_family = next((f["family"] for f in reversed(self.stack) if f["family"]), None)
        if tag not in VOID:
            picker = tag == "ul" and "data-picker" in attrs
            self.stack.append({"tag": tag, "family": fam_here, "picker": picker})

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


def check_template_page(text: str) -> list[str]:
    parser = TemplateParser()
    parser.feed(text)
    problems: list[str] = []
    where = "site/draft/install/index.html"
    for fam in FAMILIES:
        n = parser.family_count[fam]
        if n != 1:
            problems.append(f"{where}: the {fam} family section appears {n} times; it must appear exactly once.")
        elif not parser.family_has_h2[fam]:
            problems.append(f"{where}: the {fam} family section has no <h2> with visible text.")
    for fam in parser.family_hidden_self:
        problems.append(f"{where}: the {fam} family section is hidden in the static markup.")
    for extra in parser.other_family_carriers:
        problems.append(f"{where}: data-family-section appears on an unexpected element {extra}.")
    if parser.pickers != 1:
        problems.append(f'{where}: {parser.pickers} <ul class="picker" data-picker> lists; exactly 1 is required.')
    for fam in FAMILIES:
        mine = [link for link in parser.links if link[0] == fam]
        if len(mine) != 1:
            problems.append(f"{where}: the {fam} picker link appears {len(mine)} times; it must appear exactly once.")
            continue
        _, href, in_picker, current = mine[0]
        if href != f"#{fam}":
            problems.append(f'{where}: the {fam} picker link points at {href!r}, not "#{fam}".')
        if not in_picker:
            problems.append(f"{where}: the {fam} picker link is outside the data-picker list, so select.js would not find it.")
        if current:
            problems.append(f"{where}: the {fam} picker link carries aria-current in the static markup; only select.js may set it.")
    for fam, *_ in parser.links:
        if fam not in FAMILIES:
            problems.append(f"{where}: a picker link names an unknown family {fam!r}.")
    if len(parser.resets) != 1:
        problems.append(f"{where}: {len(parser.resets)} data-picker-reset buttons; exactly 1 is required.")
    elif not parser.resets[0]:
        problems.append(f"{where}: the data-picker-reset button is not hidden in the static markup.")
    if parser.statuses != 1:
        problems.append(f"{where}: {parser.statuses} data-picker-status regions; exactly 1 is required.")
    for dup_id, count in sorted(parser.id_counts.items()):
        if count > 1:
            problems.append(f'{where}: the id "{dup_id}" appears {count} times.')
    for gid in TEMPLATE_IDS:
        if parser.id_counts.get(gid, 0) == 0:
            problems.append(f'{where}: the id "{gid}" is missing; existing deep links use it.')
    if executes_inline(text):
        problems.append(f"{where}: the page contains an inline <script>.")
    if INLINE_STYLE.search(text):
        problems.append(f"{where}: the page contains an inline style attribute.")
    if INLINE_HANDLER.search(text):
        problems.append(f"{where}: the page contains an inline on* event handler.")
    for name in ("fonts.css", "palettes.css", "baseline.css"):
        if not re.search(r'<link rel="stylesheet" href="' + BASELINE_ASSET.format(name=re.escape(name)), text):
            problems.append(f"{where}: {name} is not loaded from assets/baseline/ with a ?v=X.Y.Z token.")
    for name in ("copy.js", "select.js"):
        if not re.search(r'<script src="' + BASELINE_ASSET.format(name=re.escape(name)) + r" defer></script>", text):
            problems.append(f"{where}: {name} is not loaded from assets/baseline/ with a ?v=X.Y.Z token and defer.")
    for tag in re.findall(r"<script\b[^>]*\bsrc=[^>]*>", text):
        name = re.search(r'src="/draft/assets/baseline/([a-z]+\.js)\?v=[0-9]+\.[0-9]+\.[0-9]+"', tag)
        if name is None or name.group(1) not in BASELINE_SCRIPTS or not tag.endswith(" defer>"):
            problems.append(f"{where}: {tag} is not 1 of the baseline's scripts with a ?v=X.Y.Z token and defer.")
    if "/draft/assets/site.css" in text and not re.search(r'<link rel="stylesheet" href="/draft/assets/site\.css\?v=[0-9a-f]{12}">', text):
        problems.append(f"{where}: site.css is not loaded with a ?v= content token.")
    return problems


def header_rules(text: str) -> list[tuple[str, str]]:
    """(URL pattern, header line) for every indented line of site/_headers."""
    rules: list[tuple[str, str]] = []
    pattern = ""
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            pattern = raw.strip()
            continue
        rules.append((pattern, raw.strip()))
    return rules


def check_draft_headers(text: str) -> list[str]:
    problems: list[str] = []
    rules = header_rules(text)
    csp = [(index, pattern, line) for index, (pattern, line) in enumerate(rules) if line.lower().startswith("content-security-policy:")]
    draft = [(index, line) for index, (pattern, line) in enumerate(rules) if pattern == DRAFT_PATTERN]
    for index, pattern, line in csp[1:]:
        if pattern != DRAFT_PATTERN:
            problems.append(f"site/_headers sets a Content-Security-Policy for {pattern}; only /* and {DRAFT_PATTERN} may set one.")
        elif line.split(":", 1)[1].strip() != DRAFT_CSP:
            problems.append(f"the {DRAFT_PATTERN} Content-Security-Policy is not exactly the owner's draft policy: {line!r}")
    draft_csp = [index for index, line in draft if line.lower().startswith("content-security-policy:")]
    detach = [index for index, line in draft if re.fullmatch(r"!\s*content-security-policy", line, re.I)]
    if len(draft_csp) != 1:
        problems.append(f"the {DRAFT_PATTERN} rule sets Content-Security-Policy {len(draft_csp)} times; exactly 1 is required.")
    if len(detach) != 1 or (draft_csp and detach and detach[0] > draft_csp[0]):
        problems.append(
            f"the {DRAFT_PATTERN} rule must detach the site-wide policy once (! Content-Security-Policy) before it sets its "
            "own; otherwise Pages joins the 2 policies with a comma and the browser enforces both."
        )
    if [line for _, line in draft if line.lower().startswith("x-robots-tag:")] != ["X-Robots-Tag: noindex"]:
        problems.append(f"the {DRAFT_PATTERN} rule must set X-Robots-Tag: noindex exactly once.")
    for pattern, line in rules:
        robots = re.fullmatch(r"(!\s*)?x-robots-tag\s*(:.*)?", line, re.I)
        if robots and (robots.group(1) or (pattern != DRAFT_PATTERN and pattern.startswith("/draft"))):
            problems.append(f"{pattern} {'detaches' if robots.group(1) else 'sets'} X-Robots-Tag; only {DRAFT_PATTERN} may set it under /draft/, and no rule may detach it.")
    if csp and csp[0][1] == DRAFT_PATTERN:
        problems.append(f"the first Content-Security-Policy line belongs to {DRAFT_PATTERN}; the site-wide rule must come first.")
    return problems


def main() -> int:
    for path in (PAGE, STYLES, HEADERS, DRAFT_PAGE):
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

    # 6. the guarded collapse rule still exists
    if not collapse_rule_present(STYLES.read_text(encoding="utf-8")):
        problems.append(
            "no guarded collapse rule found in site/styles.css: a rule keyed on a "
            "positive html[data-family] must hide the non-selected data-family-section. "
            "The selector feature has rotted out, or its guard is no longer the plain "
            "html[data-family] form this gate recognizes."
        )

    # 7. header discipline
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
    if not re.search(r"/js/install\.js\s*\n\s*Cache-Control:", headers):
        problems.append("site/_headers has no Cache-Control entry for /js/install.js.")

    # 8 to 13. the template install page staged at /draft/, and its header rule
    problems += check_template_page(DRAFT_PAGE.read_text(encoding="utf-8"))
    problems += check_draft_headers(headers)

    if problems:
        print("Install page problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        "The install page carries all five family sections statically and visibly, ids are "
        "unique, the picker and single hidden reset are present with no pre-set filter state, "
        "no inline code, and the guarded collapse rule is present. The template install page "
        "under /draft/ meets the selector contract, and /draft/* carries exactly the draft policy."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
