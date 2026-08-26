#!/usr/bin/env python3
"""Check the install page keeps its family sections static, visible, and complete.

``site/install/index.html`` shows five AI-family setup sections (Claude, ChatGPT,
Gemini, Copilot, and other AI systems). A progressive-enhancement filter,
``site/js/install.js``, lets a reader narrow the page to one family: it sets a
``data-family`` attribute on the root element, and CSS keyed on that attribute
collapses the other family sections. The whole point is that this is an
enhancement. With JavaScript blocked by the site's Content-Security-Policy,
failed, or switched off, the attribute is never set, every hiding rule is inert,
and all five sections show. This check makes that guarantee testable, and fails
the regressions that would break it silently in a browser while passing every
other gate.

Why the page must degrade
-------------------------

The site's CSP is ``script-src 'self'; style-src 'self'`` with no
``unsafe-inline`` (``site/_headers``). An inline script or inline style is
blocked by the browser and fails only there, invisibly to a markup validator. So
the filter's mechanics live in an external script and external stylesheet, and no
family content may depend on the script to appear.

What it verifies
----------------

1. Each of the five family ids exists exactly once, on a ``<section>`` carrying a
   matching ``data-family-section``, and each contains an ``<h2>``. No other
   element carries ``data-family-section``. The general sections ``spelling``,
   ``how-to-use``, and ``assurance`` exist.
2. Each family has a picker ``<a data-family-link="X" href="#X">`` inside the
   ``.platform-actions`` group.
3. The static markup carries no pre-set filter state: the root has no
   ``data-family``, no picker link has ``aria-current``, and the ``family-reset``
   button is present and ``hidden``. This is what keeps the unscripted page whole.
4. No inline executable ``<script>`` and no inline ``style`` attribute anywhere
   (an ``application/ld+json`` block is data, not script, and is allowed).
5. The page links ``/js/install.js`` and ``/styles.css``, each with a
   ``?v=YYYYMMDD-N`` cache token.
6. In ``site/styles.css``: the collapse rule exists (some rule keyed on
   ``html[data-family`` hides a ``data-family-section``), and every rule that
   hides a family section is guarded by ``html[data-family`` in every one of its
   comma-separated selectors, and no rule hides a family by its bare id.
7. In ``site/_headers``: the CSP still names ``script-src 'self'`` and
   ``style-src 'self'`` with no ``unsafe-inline``, and ``/js/install.js`` carries
   an immutable ``Cache-Control``.

What it does not verify
-----------------------

It takes no position on section order, wording beyond the presence of an ``h2``,
the token's freshness, ``display: none`` elsewhere in the stylesheet (the
``.button[hidden]`` guard and the mobile nav are legitimate), or the behaviour of
``install.js`` in a browser. It is not a CSS engine: the rule scan assumes the
current flat, unnested stylesheet.

Exit codes:
  0  the page and its rules are static, complete, and correctly guarded
  1  a family section, picker link, guard, or header discipline regressed
  3  a file could not be read, or the expected markup was not found
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "site" / "install" / "index.html"
STYLES = REPO_ROOT / "site" / "styles.css"
HEADERS = REPO_ROOT / "site" / "_headers"

FAMILIES = ["claude", "chatgpt", "gemini", "copilot", "other-ai"]
GENERAL_IDS = ["spelling", "how-to-use", "assurance"]

SCRIPT_TAG = re.compile(r"<script([^>]*)>", re.I)
SCRIPT_ATTR = re.compile(r'([A-Za-z][\w:.-]*)\s*=\s*"([^"]*)"')
EXECUTABLE_TYPES = {"", "module", "text/javascript", "application/javascript", "text/ecmascript"}
INLINE_STYLE = re.compile(r"<[^>]+\sstyle=", re.I)
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)


def die(message: str) -> None:
    print(f"check-install-page: {message}", file=sys.stderr)
    raise SystemExit(3)


class InstallParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, str | None]] = []
        self.html_attrs: dict[str, str] = {}
        self.section_family: dict[str, str] = {}   # id -> data-family-section value
        self.family_has_h2: dict[str, bool] = {}
        self.other_family_carriers: list[str] = []  # non-section or extra carriers
        self.ids: set[str] = set()
        self.family_links: dict[str, str] = {}      # data-family-link -> href
        self.family_links_current: list[str] = []   # links carrying aria-current
        self.reset_present = False
        self.reset_hidden = False
        self.hidden_families: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k.lower(): (v if v is not None else "") for k, v in attrs_list}
        if tag == "html":
            self.html_attrs = attrs
        if "id" in attrs:
            self.ids.add(attrs["id"])
        fam_here = None
        if "data-family-section" in attrs:
            fam = attrs["data-family-section"]
            if tag == "section" and attrs.get("id") == fam and fam in FAMILIES:
                self.section_family[fam] = attrs.get("id", "")
                self.family_has_h2.setdefault(fam, False)
                fam_here = fam
                if "hidden" in attrs or "inert" in attrs or attrs.get("aria-hidden") == "true":
                    self.hidden_families.append(fam)
            else:
                self.other_family_carriers.append(
                    f"<{tag} data-family-section={attrs.get('data-family-section')!r}>"
                )
        if tag == "a" and "data-family-link" in attrs:
            self.family_links[attrs["data-family-link"]] = attrs.get("href", "")
            if "aria-current" in attrs:
                self.family_links_current.append(attrs["data-family-link"])
        if tag == "button" and attrs.get("id") == "family-reset":
            self.reset_present = True
            self.reset_hidden = "hidden" in attrs
        if tag == "h2":
            for _t, fam in reversed(self.stack):
                if fam is not None:
                    self.family_has_h2[fam] = True
                    break
        # void elements never push
        if tag not in ("meta", "link", "img", "br", "hr", "input", "source", "wbr", "col"):
            self.stack.append((tag, fam_here))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


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


def scan_css(text: str, problems: list[str]) -> None:
    stripped = CSS_COMMENT.sub("", text)
    collapse_rule_found = False
    for selector, body in CSS_RULE.findall(stripped):
        selector = selector.strip()
        if not selector:
            continue
        branches = [s.strip() for s in selector.split(",") if s.strip()]
        mentions_section = "data-family-section" in selector
        if mentions_section and "html[data-family" in selector and hides(body):
            collapse_rule_found = True
        if hides(body):
            if mentions_section:
                unguarded = [b for b in branches if "html[data-family" not in b]
                if unguarded:
                    problems.append(
                        "a stylesheet rule hides a family section without the "
                        "html[data-family] guard, so the section would vanish with "
                        f"no JavaScript: selector {unguarded[0]!r}. Guard every branch "
                        "with html[data-family] or it breaks the no-JS page."
                    )
            for fam in FAMILIES:
                if re.search(r"#" + re.escape(fam) + r"\b", selector):
                    problems.append(
                        f"a stylesheet rule hides the family section by its bare id "
                        f"(#{fam}) in selector {selector!r}; hide it only through the "
                        "guarded html[data-family] ... [data-family-section] rule."
                    )
    if not collapse_rule_found:
        problems.append(
            "no guarded collapse rule found in site/styles.css: a rule keyed on "
            "html[data-family] must hide the non-selected data-family-section, or the "
            "selector feature has silently rotted out of the stylesheet."
        )


def main() -> int:
    for path in (PAGE, STYLES, HEADERS):
        if not path.is_file():
            die(f"{path.relative_to(REPO_ROOT)} does not exist")

    page_text = PAGE.read_text(encoding="utf-8")
    parser = InstallParser()
    parser.feed(page_text)

    problems: list[str] = []

    # 1. family sections static, complete, exclusive
    for fam in FAMILIES:
        if fam not in parser.section_family:
            problems.append(
                f"no <section id=\"{fam}\" data-family-section=\"{fam}\"> found; "
                "every family section must be present and statically visible."
            )
        elif not parser.family_has_h2.get(fam):
            problems.append(f"the {fam} family section has no <h2>; it may be an empty stub.")
    for fam in parser.hidden_families:
        problems.append(
            f"the {fam} family section carries hidden, inert, or aria-hidden in the "
            "static markup, so it would not appear without JavaScript."
        )
    for extra in parser.other_family_carriers:
        problems.append(
            f"data-family-section appears on an unexpected element {extra}; only the "
            "five family <section> elements may carry it."
        )
    for gid in GENERAL_IDS:
        if gid not in parser.ids:
            problems.append(f"the general section id \"{gid}\" is missing from the page.")

    # 2. picker integrity
    for fam in FAMILIES:
        href = parser.family_links.get(fam)
        if href is None:
            problems.append(f"no picker link <a data-family-link=\"{fam}\"> found.")
        elif href != f"#{fam}":
            problems.append(
                f"the {fam} picker link points at {href!r}, not \"#{fam}\"; the deep "
                "link and the filter would disagree."
            )

    # 3. no pre-set filter state
    if "data-family" in parser.html_attrs:
        problems.append(
            "the root <html> element carries data-family in the static markup; the "
            "filter must start unset so the unscripted page shows every family."
        )
    if parser.family_links_current:
        problems.append(
            "a picker link carries aria-current in the static markup "
            f"({', '.join(parser.family_links_current)}); only install.js may set it."
        )
    if not parser.reset_present:
        problems.append('the "Show all AI systems" button (id="family-reset") is missing.')
    elif not parser.reset_hidden:
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

    # 5. script and stylesheet tokens
    if not re.search(r'src="/js/install\.js\?v=\d{8}-\d+"', page_text):
        problems.append(
            "the page does not reference /js/install.js with a ?v=YYYYMMDD-N token."
        )
    if not re.search(r'href="/styles\.css\?v=\d{8}-\d+"', page_text):
        problems.append(
            "the page does not reference /styles.css with a ?v=YYYYMMDD-N token."
        )

    # 6. CSS guard scan
    scan_css(STYLES.read_text(encoding="utf-8"), problems)

    # 7. header discipline
    headers = HEADERS.read_text(encoding="utf-8")
    csp_line = ""
    for line in headers.splitlines():
        if "Content-Security-Policy:" in line:
            csp_line = line
            break
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
    if not re.search(
        r"/js/install\.js\s*\n\s*Cache-Control:[^\n]*immutable", headers
    ):
        problems.append(
            "site/_headers has no immutable Cache-Control entry for /js/install.js; the "
            "versioned asset would not be cached correctly."
        )

    if problems:
        print("Install page problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        "The install page carries all five family sections statically and visibly, "
        "the picker and reset control are present with no pre-set filter state, and "
        "the collapse rule is guarded so the page degrades without JavaScript."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
