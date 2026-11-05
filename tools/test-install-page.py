#!/usr/bin/env python3
"""Tests for tools/check-install-page.py: the install pages' contract and the site-wide policy.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault to the install page, a family page, or
site/_headers, runs the gate there as a separate process and asserts its exit
code and, where a case gives them as (code, words), that its output holds those
words, so that a crash, which also exits 1, does not pass for a refusal. 1 more
check asserts that the gate's docstring names exactly the scripts
in ``ALLOWED_SCRIPTS``. Exit 0 when every case passes; 1 otherwise, naming
each failing case.
Each of RESIDUALS is a fault the gate passes, such as markup in which a browser
hides or empties what the gate checks; it must exit 0, and the gate's docstring
must name it, so that what the gate says it checks cannot outgrow its code
unnoticed.

It also reads the stylesheets every install page loads (fonts.css, palettes.css
and baseline.css under site/assets/baseline/) and fails when a bare single
class, such as ``.only-dark``, whose name may be any CSS identifier, is hidden
by the declarations of every rule in the 3 stylesheets whose selector list
holds it, read together, inside an at-rule or not and whatever its condition
(so ``.x { height: 3px; } .x { overflow: hidden; }`` hides ``.x``), and the
class is in neither the gate's HIDING_CLASSES nor EXEMPT_CLASSES below. It
fails closed on properties as well as values: a declaration shows only when its
property is a custom property or 1 of SHOWING_PROPERTIES, which cannot hide or
move a box, or when its value is in that property's exact list in
SHOWING_VALUES; every other declaration hides, read or not. A vendor prefix
such as ``-webkit-`` is dropped first. So any ``content-visibility``,
``zoom``, ``contain``, ``filter``, ``mask``, ``content``, ``visibility``,
``clip``, ``bottom`` or unknown property hides, as does any value the
stylesheets do not carry today: ``display: none``, a computed 1 (``calc()``,
``var()``), a CSS-wide keyword other than ``color: inherit``, an ``opacity``
of 0.5, -1 or ``0e1``, ``inset: -9999px``, ``font-size: 0``,
``max-width: 0``, ``z-index: -1``, ``color: transparent`` or
``color: var(--surface-raised)``; ``color`` and the font properties
(``font-family``, ``font-variant-numeric``, ``font-weight``,
``text-rendering`` and ``text-transform``) have such lists. A listed value
holds ``var()`` only of a custom property in VARIABLE_VALUES, whose every
value the stylesheet check also pins (each palette colour that a listed
``color`` value names among them); as the colour after a width and ``solid``
in a border or an outline, where any other token would leave the declaration
invalid; or in the middle of a ``clamp()`` between 2 positive lengths in
``rem`` (BOUNDED). The joined declarations of a class also hide when they
declare 1 of SIZES beside 1 of OVERFLOWS that holds ``hidden``
or ``clip``, whatever the values (``height: 3px; overflow: hidden``), or
beside 1 that holds ``auto`` or ``scroll`` while a value of SIZES there is not
1 of SCROLL_SIZES (``height: 3px; overflow: auto``). The
value is compared in lower case, with each run of whitespace read as 1 space
and a final ``!important`` dropped; it reads neither which declaration wins
nor its importance, so ``opacity: 0; opacity: 1`` hides, as does ``opacity: 1
!important; opacity: 0``. It does not prove that no other mix of listed values
hides. Among those it passes are the 3 negative margins, of at most 0.8rem (on
``.scheme``, ``.verified`` and ``.code-note``): beside ``top: 0``, say, 1 can
take a box off the top edge. These residuals are accepted: it passes a colour
that matches what is behind the text in context or lets it show through, such
as a listed ``color`` value whose palette colour is set, in some rule, to a
value it takes in another scheme (a dark ``--text`` in a light scheme), or a
paint property of SHOWING_PROPERTIES, which may take any value, that matches
the text's colour (``background: var(--text)``); a font that a family name or
an ``src`` URL picks, since every string reads as empty, so a font whose
glyphs show nothing passes; and a box that another covers, positioned or with
an outline or a shadow.
The parser is deliberately small: it reads no compound, descendant or attribute
selector. It reads comments and strings as CSS does, so a brace, a ``;`` or a
comment opener in a string, or a brace or a quote in a comment, delimits
nothing, and it fails when a stylesheet cannot be read, holds no rule, or holds
what it does not model: an unclosed comment, a string that a line break or its
end leaves open, a backslash outside a string, ``<!--`` or ``-->``, an unquoted
``url()`` holding a quote, a ``(``, a brace or a backslash, a brace inside
brackets or parentheses, unbalanced braces, brackets or parentheses, a rule
inside a rule, an at-rule other than those of AT_RULES (``@container``,
``@font-face``, ``@keyframes``, ``@media`` and ``@supports``), or keyframes
named by a string. It also fails when any rule sets a custom property of
VARIABLE_VALUES to a value outside its list there, when a ``@keyframes`` rule
whose name is that of an animation in KEYFRAMES (``field-in``), compared
without regard to case, holds other keyframes, and when an ``@font-face``
rule gives a descriptor a value outside FONT_FACE_VALUES, or any other
descriptor (``size-adjust: 1%`` fails). Before it reads them, it fails unless
the reading counts each of HIDING_DECLARATIONS as hiding and none of
SHOWING_DECLARATIONS, unless BOUNDED matches none of NOT_BOUNDED, and unless
it reads each of SHEET_CASES as that case expects.

It also fails unless the gate's SUPPORTED_PYTHONS is exactly 3.14 and each of
its versions is in SUPPORTED_PYTHONS of tools/check-inline-code.py, and runs the
gate under 2 faked Python versions outside that set, 3.13 and 3.15, expecting
for each exit 3, no result line, and exactly the one-line refusal of the gate's
own guard (OWN_REFUSAL below), which its catch of UnsupportedPython does not
print, so it fails when that guard is gone or admits either. A last run reaches
the version check of tools/check-inline-code.py: with a copy of that gate whose
SUPPORTED_PYTHONS leaves out this version, so that it raises UnsupportedPython,
it expects exit 3, no result line, and a one-line message from the gate that
names tools/check-inline-code.py.
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
# The hero's heading, the "pick" label and the whole button row that follows it, each a line of the committed
# install page.
HERO = "<h1>Pick the AI you use and follow the steps</h1>"
PICK = '<p class="lbl blk" id="pick">Pick your AI</p>'
ROW_LINE = "<p>" + " ".join(f'<a class="btn inline" id="{fam.lower()}" href="/install/{fam.lower()}/">{fam}</a>'
                            for fam in ("Claude", "ChatGPT", "Gemini", "Copilot")) + " " + ROW_END
# The labels that start the "Scope" section, below the button row, and the "Get Clean Language" section after it.
SCOPE = '<p class="lbl blk">Scope</p>'
GET_LABEL = '<p class="lbl sec">Get Clean Language</p>'
MAIN = '<main id="main-content">\n'
STEPS = '<ol class="steps">'
# The gate's messages for a bdo or a dir that starts before the button row or a family page's h1 ends, and for an
# html or body start tag with dir.
ROW_DIR = "an element that starts before the paragraph of family links ends is a bdo or carries dir"
H1_DIR = "an element that starts before the <h1> ends is a bdo or carries dir"
PAGE_DIR = "an html or body start tag carries dir"
# The scheme.js tag of template specification 7.33 (baseline 1.8.0), as the committed pages carry it.
SCHEME = '<script data-cfasync="false" src="/assets/baseline/scheme.js?v=1.8.0"></script>'
COPY = '<script src="/assets/baseline/copy.js?v=1.8.0" defer></script>'
FONTS = '<link rel="stylesheet" href="/assets/baseline/fonts.css?v=1.8.0">'
LATER = '<link rel="stylesheet" href="/assets/baseline/baseline.css?v=1.8.0">'
STYLESHEETS = ["site/assets/baseline/fonts.css", "site/assets/baseline/palettes.css", "site/assets/baseline/baseline.css"]
# Classes a stylesheet may hide as a bare single class although the gate does not refuse them. Add 1 only with a
# comment saying why no install page can carry it on a checked element or an ancestor. None qualifies today.
EXEMPT_CLASSES: tuple[str, ...] = ()
# A class selector whose name is any CSS identifier: "--" or an optional "-", then a letter, "_" or a character from
# U+0080 on, and then any of those, digits and "-". css_rules() refuses an escape, so no name holds 1.
BARE_CLASS = re.compile(r"\.((?:--|-?[_a-zA-Z\u0080-\U0010ffff])[_a-zA-Z0-9\u0080-\U0010ffff-]*)")
# The properties hides() reads as showing whatever their value: those fonts.css, palettes.css and baseline.css use that
# cannot hide or move a box. Each is listed with its reason; a property gets in only with 1.
SHOWING_PROPERTIES = (
    # Paint a colour, an image or a shadow behind or around the text, or in an SVG: each can hide the text only by a
    # colour that matches the text's colour or lets what is behind show through, which this test does not read (an
    # accepted residual: background: var(--text), say), and a shadow or a background covers another box only when
    # its box is positioned over it (see above). color itself has a list in SHOWING_VALUES.
    "background", "border-bottom-color", "border-color", "box-shadow", "color-scheme", "fill", "outline-color",
    "stroke", "text-decoration-color",
    # Count, point or scroll, and change no box: counters, the pointer, scrollbars, scroll chaining, touch scrolling,
    # and transitions, which only animate between values that the rules themselves give.
    "counter-increment", "counter-reset", "cursor", "overflow-scrolling", "overscroll-behavior", "scrollbar-width",
    "transition",
)
# The only values hides() reads as showing for every other property the stylesheets use; every other value of these
# properties, and every value of any other property, counts as hiding. Each is a value fonts.css, palettes.css or
# baseline.css gives that property today and that shows beside any other listed value but for SIZES beside a clip
# (see OVERFLOWS) and the 3 negative margins, of at most 0.8rem, of .scheme, .verified and .code-note, which can take
# a box that small off an edge it sits at (see above). None is display: none, an opacity below 1, a width, height,
# font size or line height of 0 or 1px, a negative top, left or z-index, a negative padding, a content, a colour
# other than var() of a pinned palette colour, or a CSS-wide keyword but color: inherit; of those that move a box
# from where the flow or the grid puts it, they list only position: absolute, relative and sticky, top: 0, 0.12rem,
# 0.8rem, 1rem and 1.5rem, left: 0 and 1rem, right: 0.8rem, a transform by 0.25rem or none, and margins of auto, of
# at most 2.5rem, or, for the 3 negative ones, of at most 0.8rem; the animation field-in, from opacity 0 to 1 in
# its keyframes (pinned by KEYFRAMES), moves no box. Left out of what
# they carry: the values only their hiding rules use (display: none; clip: rect(0 0 0 0), width: 1px, height: 1px
# and margin: -1px in .vh and .family .cards .cname; top: -4rem in .skip; opacity: 0 in @keyframes field-in); every
# content (the counters of the ::before rules, which on an element itself could replace its text); inherit (in font
# and font-size); the computed values the first lists left out (the max-height with calc() of .lrail > nav, and the
# margin-left values with calc() of .rail > .lbl); and each value that holds var() of a custom property outside
# VARIABLE_VALUES (the sizes of .family's logos and tiles, the padding-left values of .lrail > nav, the min-height of
# .family's cards, the padding of .family .slice and the widths of table columns). Kept: calc(), clamp() and max()
# of lengths alone; a clamp() between 2 positive lengths in rem whatever its middle argument (BOUNDED: .statement's
# font sizes); and var() of VARIABLE_VALUES, or as a border's or an outline's colour (BORDER_COLOUR). hides_problems()
# reads each listed value on its own as well.
SHOWING_VALUES = {
    "display": ("block", "contents", "flex", "grid", "inline", "inline-block", "inline-flex", "inline-grid",
                "table-header-group"),
    "position": ("absolute", "relative", "static", "sticky"),
    "top": ("0", "0.12rem", "0.8rem", "1rem", "1.5rem"),
    "left": ("0", "1rem"),
    "opacity": ("1",),
    "height": ("auto", "3px", "1.5rem", "2.4rem", "2.75rem"),
    "max-height": ("none", "11rem", "36rem", "75vh", "75svh"),
    "overflow": ("auto", "hidden", "visible"),
    "right": ("0.8rem",),
    "transform": ("none", "translatex(0.25rem)"),
    "animation": ("field-in 400ms ease-out both", "none"),
    "margin": ("0", "0 auto", "0 0 0 0.15rem", "0 0 0 0.4em", "0 0 0.15rem", "0 0 0.4rem", "0 0 0.5rem", "0 0 0.6rem",
               "0 0 0.8rem", "0 0 0.9rem", "0 0 1rem", "0 0 1.1rem", "0 0 1.4rem", "0 0 1.6rem", "0 0 2rem",
               "0 0.6rem 0.6rem 0", "0.2rem 0 0.4rem", "0.2rem 0 1.4rem", "0.3rem 0 0.9rem", "0.3rem 0 1.2rem",
               "0.4rem 0 0", "0.4rem 0 0.8rem", "0.4rem 0 1.4rem", "0.4rem 0 1.6rem", "0.6rem 0 0", "0.6rem 0 0.8rem",
               "1.6rem 0 0.5rem", "2rem 0 0.7rem", "2.4rem 0 0.6rem", "-0.25rem -0.625rem -0.25rem 0.6rem",
               "-0.4rem 0 1rem", "-0.8rem 0 1.6rem"),
    "margin-top": ("0", "0.15rem", "0.2rem", "0.4rem", "0.5rem", "0.8rem", "1.1rem", "1.2rem", "1.35rem", "1.4rem"),
    "margin-right": ("0", "clamp(1.2rem, 2.5vw, 2.5rem)"),
    "margin-bottom": ("0", "0.4rem", "0.45rem", "0.5rem", "0.7rem", "0.8rem", "0.9rem", "1.1rem", "1.4rem"),
    "margin-left": ("0.4rem", "auto"),
    "align-items": ("baseline", "center", "flex-start", "start", "stretch"),
    "align-self": ("center", "start", "stretch"),
    "aspect-ratio": ("1", "1 / 1"),
    "border": ("0", "1px solid var(--rule-strong)"),
    "border-bottom": ("0", "1px solid transparent", "1px solid var(--rule-strong)", "2px solid var(--brand)",
                      "3px solid var(--grp-1)", "3px solid var(--grp-2)", "3px solid var(--grp-3)",
                      "3px solid var(--grp-4)", "3px solid var(--grp-5)", "3px solid var(--grp-6)"),
    "border-bottom-width": ("2px",),
    "border-collapse": ("collapse", "separate"),
    "border-left": ("4px solid var(--brand)",),
    "border-radius": ("0.2rem", "0.3rem", "0.5rem", "2px", "50%", "999px"),
    "border-right": ("0", "1px solid var(--rule-strong)"),
    "border-spacing": ("0",),
    "border-style": ("dashed",),
    "border-top": ("1px solid var(--rule-strong)", "3px solid var(--brand)"),
    "box-sizing": ("border-box",),
    "break-inside": ("avoid",),
    "color": ("inherit", "var(--accent)", "var(--gold)", "var(--grp-1)", "var(--grp-2)", "var(--grp-3)", "var(--grp-4)",
              "var(--grp-5)", "var(--grp-6)", "var(--link)", "var(--link-hover)", "var(--ord-cost)",
              "var(--ord-progress)", "var(--ord-speed)", "var(--print-ink)", "var(--rainbow-ink-1)",
              "var(--rainbow-ink-2)", "var(--rainbow-ink-3)", "var(--rainbow-ink-4)", "var(--rainbow-ink-5)",
              "var(--rainbow-ink-6)", "var(--silver)", "var(--text)", "var(--text-muted)"),
    "column-gap": ("0", "0.4rem", "0.6rem", "1rem", "2.5rem", "2rem", "3rem", "clamp(2.5rem, 5vw, 6rem)"),
    "columns": ("1", "2", "3"),
    "container": ("footer / inline-size",),
    "container-type": ("inline-size",),
    "flex": ("1 1 0", "1 1 100%", "1 1 auto", "3 1 0", "6 1 0", "6 1 auto", "none"),
    "flex-direction": ("column",),
    "flex-wrap": ("nowrap", "wrap"),
    "font": ('300 2.3rem/1 "", serif', '300 2.6rem/1 "", serif', '300 3rem/1 "", serif',
             '400 0.72rem/1.4 "", ui-monospace, monospace', '400 0.78rem/1.5 "", system-ui, sans-serif',
             '400 0.82rem/1.8 "", ui-monospace, monospace', '400 0.85rem/1.5 "", system-ui, sans-serif',
             '400 0.85rem/1.7 "", ui-monospace, monospace', '400 0.8rem/1.4 "", ui-monospace, monospace',
             '400 0.8rem/1.5 "", ui-monospace, monospace', '400 0.8rem/1.6 "", serif',
             '400 0.8rem/1.6 "", ui-monospace, monospace', '400 0.95rem/1.45 "", system-ui, sans-serif',
             '400 0.95rem/1.5 "", system-ui, sans-serif',
             '400 0.95rem/1.55 "", ui-monospace, sfmono-regular, menlo, monospace', '400 0.95rem/1.6 "", serif',
             '400 0.9em/1.4 "", ui-monospace, monospace', '400 0.9rem/1.4 "", system-ui, sans-serif',
             '400 1.05rem/1.45 "", system-ui, sans-serif', '400 1.05rem/1.5 "", system-ui, sans-serif',
             '400 1.1875rem/1.4 "", serif', '400 1.1rem/1.5 "", ui-monospace, monospace', '400 1.25rem/1.35 "", serif',
             '400 1.25rem/1.6 "", georgia, "", serif', '400 1.5rem/1 "", cursive', '400 1.777rem/1.25 "", serif',
             '400 1rem/1.45 "", system-ui, sans-serif', '500 0.66rem/1 "", system-ui, sans-serif',
             '500 0.68rem/1.4 "", system-ui, sans-serif', '500 0.72rem/1.4 "", system-ui, sans-serif',
             '500 0.74rem/1 "", system-ui, sans-serif', '500 0.78rem/1 "", system-ui, sans-serif',
             '500 0.7rem/1 "", system-ui, sans-serif', '500 0.8rem/1.6 "", system-ui, sans-serif',
             '500 clamp(0.66rem, 0.45vw + 0.36rem, 0.74rem)/1 "", system-ui, sans-serif',
             '600 0.62rem/1.4 "", system-ui, sans-serif', '600 0.68rem/1.45 "", system-ui, sans-serif',
             '600 0.95rem/1.2 "", system-ui, sans-serif', '600 1.4rem/1.2 "", serif',
             '600 1rem/1.45 "", system-ui, sans-serif', '700 clamp(1.6rem, 1.9vw, 2.2rem)/1 "", system-ui, sans-serif'),
    "font-family": ('"", serif', '"", system-ui, sans-serif', '"", ui-monospace, monospace'),
    "font-feature-settings": ('"", ""',),
    "font-size": ("0.74rem", "0.78em", "0.85rem", "0.8rem", "0.95rem", "0.9rem", "1.05rem", "1.125rem", "1.15rem",
                  "1.1rem", "1.2rem", "1.333rem", "1.45rem", "1.5rem", "1.7rem", "11px", "12.5px", "14px", "2.2rem",
                  "2.4rem", "2.8rem", "2rem", "clamp(0.85rem, 4.6cqw - 4px, 1.05rem)",
                  "clamp(0.8rem, 0.8cqw + 4px, 0.95rem)", "clamp(1.05rem, 2.4cqw - 9.6px, 1.5rem)",
                  "clamp(1.05rem, 4.2cqw, 1.5rem)", "clamp(1.05rem, 7.2cqw - 30px, 1.5rem)",
                  "clamp(1.35rem, 1.35vw, 1.8rem)", "clamp(2.4rem, 98cqw / var(--sw), 3.2rem)",
                  "clamp(2.6rem, 98cqw / var(--sw), 5rem)"),
    "font-style": ("italic",),
    "font-variant-numeric": ("lining-nums", "lining-nums tabular-nums", "oldstyle-nums proportional-nums"),
    "font-weight": ("300", "400", "500", "600"),
    "gap": ("0", "0 clamp(1rem, 1.6vw, 2rem)", "0 clamp(2rem, 3vw, 4rem)", "0.2rem", "0.3rem", "0.3rem 1rem",
            "0.3rem 2rem", "0.4rem 1.8rem", "0.4rem 2.5rem", "0.5rem", "0.6rem", "0.6rem 0", "0.6rem 1.6rem",
            "0.6rem 2rem", "0.75rem", "0.8rem 1.6rem", "1rem", "1rem 1.2rem", "1rem 2.2rem", "1rem 3rem", "2rem",
            "clamp(0.3rem, 1.53cqw - 11.8px, 0.6rem)"),
    "grid-area": ("art", "brand", "d", "intro", "kicker", "m", "n", "pages", "scheme", "start", "t", "text", "title"),
    "grid-auto-columns": ("minmax(0, 1fr)",),
    "grid-auto-flow": ("column", "row"),
    "grid-column": ("1", "1 / -1", "1 / 3", "1 / 4", "2", "3"),
    "grid-row": ("1 / span 200", "auto", "span 7"),
    "grid-template-areas": ('""', '"" ""', '"" "" ""', '"" "" "" ""'),
    "grid-template-columns": ("1.4rem 1fr", "1fr", "1fr 1fr", "2.2rem minmax(0, 1fr)", "2.6rem minmax(0, 1fr)",
                              "2.8rem minmax(0, 1fr)", "3.2rem minmax(0, 1fr)", "5.2rem minmax(0, 1fr)",
                              "auto minmax(0, 1fr)", "auto minmax(0, 1fr) auto", "minmax(0, 1fr)",
                              "minmax(0, 1fr) 5.5rem", "minmax(0, 1fr) auto", "minmax(0, 1fr) clamp(9rem, 24vw, 13rem)",
                              "minmax(0, 1fr) var(--art)", "repeat(3, minmax(0, 1fr))",
                              "repeat(auto-fill, minmax(12rem, 1fr))", "var(--label-col) minmax(0, 1fr)",
                              "var(--label-col) minmax(0, 1fr) var(--railw)", "var(--railw) minmax(0, 1fr)"),
    "justify-content": ("center", "flex-end", "flex-start"),
    "justify-self": ("end", "start"),
    "letter-spacing": ("-0.005em", "-0.012em", "-0.015em", "0", "0.01em", "0.02em", "0.04em", "0.06em", "0.08em",
                       "0.12em", "0.14em", "0.16em", "0.18em", "0.2em", "2.2px"),
    "line-height": ("1.06", "1.1", "1.18", "1.35", "1.4", "1.45", "1.5", "1.55"),
    "list-style": ("lower-alpha", "none"),
    "max-width": ("20rem", "40rem", "52ch", "62ch", "66ch", "68ch", "72ch", "7rem", "84ch", "none"),
    "min-height": ("1.3rem",),
    "min-width": ("0", "56rem", "7rem"),
    "object-fit": ("contain",),
    "order": ("0",),
    "outline": ("3px solid var(--focus)",),
    "outline-offset": ("2px", "4px"),
    "overflow-wrap": ("anywhere", "break-word"),
    "overflow-x": ("auto",),
    "overflow-y": ("auto",),
    "padding": ("0", "0 0 2.6rem", "0 0.08em", "0 0.3rem", "0 0.4rem", "0 0.5rem", "0 0.6rem", "0 1.2rem 0.6rem 0",
                "0 var(--pad)", "0.1em 0.35em", "0.22rem 0", "0.2rem", "0.2rem 1rem 0.4rem", "0.35rem 0 0.1rem",
                "0.35rem 0 1.15rem", "0.35rem 0.55rem", "0.3rem", "0.3rem 0", "0.3rem 0.1rem", "0.3rem 0.2rem",
                "0.3rem 0.7rem", "0.3rem clamp(0.375rem, 1.73cqw - 13px, 0.7rem)", "0.4rem 0", "0.4rem 0 0.55rem",
                "0.55rem 0.8rem", "0.55rem 0.9rem", "0.5rem 0.8rem", "0.6rem 0", "0.6rem 0 2rem",
                "0.6rem 0.4rem 0.6rem 0", "0.6rem 1.2rem 0.6rem 0", "0.6rem 1rem", "0.75rem 1rem", "0.7rem 0",
                "0.7rem 1rem", "0.85rem 0.6rem 0.8rem 0.8rem", "0.9rem 1rem", "1.2rem 1.4rem",
                "1.2rem max(0px, calc(var(--art) * 0.5 - var(--pad))) 2.4rem 0", "1.3rem 1.4rem",
                "1.6rem var(--pad) 2.2rem", "1rem", "1rem 0 0", "1rem 0 2.2rem", "1rem 1rem", "1rem var(--pad) 0.9rem"),
    "padding-bottom": ("0.1rem", "1rem", "2.2rem"),
    "padding-left": ("0", "1.2rem", "1.4rem", "2.6rem"),
    "padding-right": ("0", "calc(0.5rem - 0.36em)"),
    "padding-top": ("0", "0.1rem", "0.25rem", "0.4rem", "0.55rem", "0.5rem", "0.6rem", "0.9rem", "1.1rem", "1.2rem",
                    "1.4rem", "1.75rem", "1.8rem", "3.2rem", "3rem"),
    "place-items": ("center",),
    "row-gap": ("0", "0.05rem", "0.2rem"),
    "stroke-width": ("1", "2"),
    "table-layout": ("auto", "fixed"),
    "text-align": ("center", "left", "right"),
    "text-decoration": ("none", "underline"),
    "text-decoration-thickness": ("1px", "2px"),
    "text-rendering": ("optimizelegibility",),
    "text-size-adjust": ("100%",),
    "text-transform": ("none", "uppercase"),
    "text-underline-offset": ("0.18em",),
    "text-wrap": ("balance",),
    "vertical-align": ("bottom", "top"),
    "white-space": ("normal", "nowrap", "pre", "pre-wrap"),
    "width": ("1.5rem", "10%", "100%", "11%", "14%", "15%", "16%", "17%", "2.75rem", "20%", "25%", "26%", "30%",
              "35%", "40%", "45%", "5%", "50%", "55%", "60%", "65%", "70%", "72%", "75%", "80%", "84%", "85%", "86%",
              "90%", "95%", "auto"),
    "writing-mode": ("sideways-lr", "vertical-rl"),
    "z-index": ("1", "2", "3", "50"),
}
# The custom properties a listed value of SHOWING_VALUES may name in var(), each with the only values it may take in
# any rule of the 3 stylesheets (the values they hold today); sheet_problems() fails on any other, so a listed
# value with var() stays as bounded as these. A var() as the colour after a width and solid in a border or an outline
# needs no entry: any other token there makes the declaration invalid. The palette colours that the values of color
# name are pinned too, each to every value it takes in any palette or scheme, so no rule can set 1 to transparent;
# a value from another scheme (a dark --text in a light scheme, say) still passes, an accepted residual.
VARIABLE_VALUES = {
    "--pad": ("clamp(1rem, 3vw, 3.2rem)",),
    "--art": ("clamp(11rem, 22vw, 30rem)",),
    "--label-col": ("9rem",),
    "--railw": ("clamp(13rem, 13vw, 17rem)",),
    "--accent": ("#2c6aaa", "#3b752e", "#5e9ce0", "#6faa62", "#7d6500", "#8a509c", "#a25100", "#b79400", "#b97dcc",
                 "#bc3732", "#e1791b", "#ef675c"),
    "--gold": ("#8a6a0a", "#e6c15a"),
    "--grp-1": ("#ba3630", "#bc3732", "#fd7468"),
    "--grp-2": ("#a25100", "#ef852e"),
    "--grp-3": ("#7c6300", "#7d6500", "#c6a000"),
    "--grp-4": ("#3a732c", "#3b752e", "#7bb76e"),
    "--grp-5": ("#2a68a8", "#2c6aaa", "#6aa9ed"),
    "--grp-6": ("#8a509c", "#c689d9"),
    "--link": ("#2b619a", "#386a2c", "#71a5e0", "#735c00", "#7e4b8e", "#7fb174", "#954b00", "#ab3731", "#be8bce",
               "#be9e32", "#e18846", "#ee7a6f"),
    "--link-hover": ("#154d84", "#245618", "#5c4900", "#6a3779", "#793b00", "#8dbbf0", "#931e1c", "#99c68f", "#d1b55d",
                     "#d2a4e0", "#f2a26a", "#ff968b"),
    "--ord-cost": ("#bc3732", "#ef675c"),
    "--ord-progress": ("#3b752e", "#6faa62"),
    "--ord-speed": ("#a25100", "#e1791b"),
    "--print-ink": ("#000000",),
    "--rainbow-ink-1": ("#1d1a16", "#fffaf2"),
    "--rainbow-ink-2": ("#1d1a16",),
    "--rainbow-ink-3": ("#1d1a16",),
    "--rainbow-ink-4": ("#1d1a16",),
    "--rainbow-ink-5": ("#1d1a16", "#fffaf2"),
    "--rainbow-ink-6": ("#1d1a16", "#fffaf2"),
    "--silver": ("#6a6a6a", "#cfcfcf"),
    "--text": ("#1d1f21", "#1f2017", "#231f15", "#241d20", "#261d16", "#2d181b", "#e9e9e9"),
    "--text-muted": ("#65686a", "#67695e", "#6c675b", "#6d6568", "#70655d", "#7a6062", "#989898"),
}
BORDER_COLOUR = re.compile(r"[0-9.]+px solid var\(--[\w-]+\)")
# A clamp() between 2 positive lengths in rem, whatever its middle argument, such as .statement's font sizes: a var()
# there that is invalid makes the declaration invalid, so the size inherits, and any other stays within the bounds.
# A bound of 0, or in a unit that grows with the viewport or the container, does not match (NOT_BOUNDED).
POSITIVE_REM = r"(?:[0-9]*[1-9][0-9]*(?:\.[0-9]+)?|[0-9]*\.[0-9]*[1-9][0-9]*)rem"
BOUNDED = re.compile(rf"clamp\({POSITIVE_REM}, [^,]*, {POSITIVE_REM}\)")
NOT_BOUNDED = ("clamp(0rem, var(--x), 2rem)", "clamp(1rem, var(--x), 0.0rem)", "clamp(1rem, var(--x), 500vw)",
               "clamp(.0rem, var(--x), 2rem)")
# The keyframes each animation of SHOWING_VALUES names, as baseline.css gives them today: each keyframe's selector and
# its declarations, compared in lower case with each run of whitespace read as 1 space. sheet_problems() fails on any
# @keyframes of that name (compared without regard to case) whose keyframes differ, so field-in cannot be redefined to
# end at opacity 0, and on keyframes named by a string, which it reads as empty.
KEYFRAMES = {"field-in": (("from", "opacity: 0;"), ("to", "opacity: 1;"))}
# The only values sheet_problems() accepts for each descriptor of an @font-face rule, those fonts.css gives today; any
# other descriptor (size-adjust, say, which can shrink the glyphs to nothing) or value fails. css_rules() reads every
# string as "", so a family name and the font file src names are not read (a residual the docstring states).
FONT_FACE_VALUES = {
    "font-family": ('""',),
    "font-style": ("italic", "normal"),
    "font-weight": ("100 800", "100 900", "200 800", "400 700"),
    "font-display": ("swap",),
    "src": ('url("") format("")',),
}
# The properties that set the box a clip cuts the text to (a size, a flex basis, an aspect ratio, a size containment
# by container-type, or a rounded corner), and the overflow properties: a rule that declares 1 of SIZES beside 1 of
# OVERFLOWS holding hidden or clip hides, whatever the values (height: 3px; overflow: hidden), and so does 1 holding
# auto or scroll while a value of SIZES there is not 1 of SCROLL_SIZES, which leave a scroll box at least 11rem tall
# or wide, or as large as its content. Of the committed rules, .prompt-block (max-height: 36rem; overflow: auto) is the
# only one with a bare class that scrolls beside a size.
SIZES = (
    "width", "height", "inline-size", "block-size", "max-width", "max-height", "max-inline-size", "max-block-size",
    "aspect-ratio", "flex", "flex-basis", "container", "container-type", "border-radius",
)
OVERFLOWS = ("overflow", "overflow-x", "overflow-y", "overflow-block", "overflow-inline")
SCROLL_SIZES = ("auto", "none", "11rem", "36rem", "75vh", "75svh")
# The at-rules css_rules() reads through: those the stylesheets use, which only say when the rules inside them apply
# or hold no rule for an element. Any other (@import, which loads rules it never sees, or @scope, whose :scope and
# bare declarations apply to an element its prelude names, say) makes the stylesheet unreadable.
AT_RULES = ("container", "font-face", "keyframes", "media", "supports")
URL_START = re.compile(r"url\(\s*", re.I)
# Declarations hides() must read as hiding, for each value form a reading by validity missed (a computed, clamped or
# exponent opacity, and 0 before 1), for each way to move a box off-screen, for each property that can hide and that
# a reading of only some properties missed, for each size beside a clip or a small scroll box, and for a colour, a
# font family, a weight and a letter case outside their lists; and declarations it must not: values of
# SHOWING_VALUES, 1 among them written with a line break and a tab that read as 1 space, properties of
# SHOWING_PROPERTIES, a declaration without a colon, and a custom property. Some hiding ones hide nothing in a
# browser (opacity: 0.5, visibility: visible, clip-path: none, right: 0, width: 100%; overflow: hidden, opacity: 0;
# opacity: 1): that reading over-refuses by design. hides_problems() also
# reads, for each property of SHOWING_VALUES, each listed value as showing and -9999px as hiding, -9999px for each of
# SHOWING_PROPERTIES as showing, and each listed value of SIZES beside overflow: hidden and overflow: auto.
HIDING_DECLARATIONS = (
    "display: none", "display: none !important", "display: block; display: none", "display: var(--d)",
    "display: bogus", "display: flow-root", "visibility: hidden", "visibility: collapse", "visibility: visible",
    "clip: rect(0 0 0 0)", "clip: auto", "clip-path: inset(0)", "clip-path: none", "position: fixed",
    "position: absolute; top: -4rem", "position: absolute; left: -9999px", "top: calc(1rem)", "left: auto",
    "opacity: 0", "opacity: 0.0", "opacity: 0.5", "opacity: calc(0)", "opacity: 0e1", "opacity: 0e0", "opacity: -1",
    "opacity: -0.5", "opacity: -50%", "opacity: var(--o)", "opacity: inherit", "opacity: 0; opacity: 1",
    "opacity: 0 !important; opacity: 1", "opacity: 1 !important; opacity: 0", "opacity: 1 !ie", "Opacity: 0",
    "op\\61 city: 0", "height: 0; overflow: hidden", "height: 0", "height: 1px", "height: var(--mark)",
    "max-height: 0", "max-height: calc(100vh - 3rem)", "overflow: clip", "overflow: hidden auto",
    "position: absolute; inset: -9999px", "inset: auto", "inset-block: -100vh", "inset-inline: -9999px",
    "inset-block-start: -9999px", "inset-block-end: 100%", "inset-inline-start: -9999px", "inset-inline-end: 100%",
    "position: absolute; right: 9999px", "right: 0", "bottom: 100vh", "transform: translatex(-9999px)",
    "transform: scale(0)", "-webkit-transform: translatex(-9999px)", "translate: -9999px", "rotate: 180deg",
    "scale: 0", "offset-path: path('m 0 0 h -9999')", "offset-distance: 100%", "position-area: top",
    "position-try-fallbacks: flip-block", "text-indent: -9999px", "margin: -9999px", "margin: 0 0 0 -9999px",
    "margin-top: -100vh", "margin-right: 9999px", "margin-bottom: -9999px", "margin-left: -9999px",
    "margin-block: -100vh", "margin-inline-start: -9999px", "animation: out 1s forwards", "animation: none 1s",
    "inset-area: top", "margin-trim: block", "-webkit-margin-start: -9999px", "transform-origin: -9999px 0",
    "animation-name: out", "offset-anchor: 9999px 0", "offset-inline-start: -9999px", "position-fallback: --off",
    "translate-x: -9999px", "rotate-x: 180deg", "scale-x: 0",
    "height: 3px; overflow: hidden", "overflow: hidden; height: 3px", "height: 3px; overflow: auto",
    "height: 3px; overflow-y: auto", "width: 1.5rem; overflow-x: auto", "max-height: 36rem; overflow: hidden",
    "width: 100%; overflow: hidden", "flex: 1 1 0; overflow: hidden", "aspect-ratio: 1; overflow: hidden",
    "border-radius: 50%; overflow: hidden", "container-type: inline-size; overflow: hidden",
    "content-visibility: hidden", "content-visibility: auto", "zoom: 0.01", "contain: size; overflow: hidden",
    "contain: paint", "line-height: 0; overflow: hidden", "line-height: 0", "max-block-size: 0", "max-width: 0",
    "inline-size: 0; overflow: hidden", "block-size: 0", "content: url(x.png)", "content: counter(c)",
    "position: relative; z-index: -1", "z-index: -1", "width: 0; font-size: 0", "font-size: 0", "font: 0/0 a",
    "width: 1px", "padding: 0 0 0 9999px", "padding-left: 9999px", "padding: 0 var(--other)",
    "padding: 0 var(--pad, 9999px)", "mask: none", "filter: opacity(0)", "letter-spacing: -1em", "direction: rtl",
    "unicode-bidi: bidi-override", "text-decoration: line-through 2em", "font-size: inherit", "col\\6fr: red",
    "-webkit-line-clamp: 1", "unknown-property: 0", "color: transparent", "color: var(--surface-raised)",
    "color: var(--text, transparent)", "font-family: blank", "font-weight: 1", "text-transform: full-width",
)
SHOWING_DECLARATIONS = (
    "display: block", "display: contents", "display: flex", "display: grid", "display: inline",
    "display: inline-block", "display: inline-flex", "display: inline-grid", "display: table-header-group",
    "DISPLAY: BLOCK !IMPORTANT", "position: absolute; top: 0; left: 0", "position: relative; top: 0.12rem; left: 1rem",
    "position: static; top: 0.8rem", "position: sticky; top: 1rem", "top: 1.5rem", "opacity: 1",
    "opacity: 1 !important", "opacity:1", "height: auto", "height: 3px", "height: 3px; overflow: visible",
    "height: 1.5rem", "height: 2.4rem", "height: 2.75rem", "max-height: none; overflow: auto", "max-height: 11rem",
    "max-height: 36rem; overflow: auto", "max-height: 36rem; overflow: visible", "max-height: 75vh",
    "max-height: 75svh", "overflow: hidden", "white-space: nowrap; overflow: hidden", "opacity 0", "",
    'font-family: "", serif', "margin: 0\n\t auto", "position: absolute; top: 0.8rem; right: 0.8rem", "transform: none",
    "transform: translateX(0.25rem)", "animation: field-in 400ms ease-out both", "margin: 0 auto",
    "margin: -0.8rem 0 1.6rem", "margin-right: clamp(1.2rem, 2.5vw, 2.5rem)", "-webkit-text-size-adjust: 100%",
    "transition: transform 150ms ease-out", "--inset: -9999px", "--pad: 9999px", 'grid-template-areas: "" ""',
    "color: var(--text)", "background: var(--surface-raised)", "padding: 0 var(--pad)",
    "font-size: clamp(2.6rem, 98cqw / var(--sw), 5rem)", "border: 1px solid var(--rule-strong)",
    "width: 2.75rem; height: 2.75rem", "line-height: 1.5", "height: auto; overflow: auto",
    "max-height: 11rem; overflow: auto", "max-height: 75vh; overflow-y: auto", "max-height: 75svh; overflow: auto",
)
# Stylesheets the reader must refuse, or read and report as hiding the bare class .x, with the words its 1 problem
# holds, and stylesheets it must read with no problem (""); only .vh counts as listed. A brace in a string, a
# comment, an unquoted url() or brackets opens or closes no block in a browser. The strings sit in font-family before
# serif, a listed value whatever the string, so only a misreading makes .x hide or show.
SHEET_CASES = (
    ("inset moving .x off-screen", ".x { position: absolute; inset: -9999px; }", "hide the bare class .x"),
    ("a size beside a clip", ".x { height: 3px; overflow: hidden; }", "hide the bare class .x"),
    ("a property it does not list", ".x { content-visibility: hidden; }", "hide the bare class .x"),
    ("a } in a string before display: none",
        '.x { font-family: "}", serif; display: none; font-family: "{", serif; }', "hide the bare class .x"),
    ("a { in a string before display: none", ".x { font-family: '{', serif; display: none; }", "hide the bare class .x"),
    ("an escaped quote and a } in a string", '.x { font-family: "\\"}", serif; display: none; }',
        "hide the bare class .x"),
    ("a comment opener in a string",
        '.x { font-family: "/*", serif; display: none; } .y { font-family: "*/", serif; }', "hide the bare class .x"),
    ("a quote and a } in a comment", "/* it's } */ .x { display: none; }", "hide the bare class .x"),
    # The declarations of every rule whose selector list holds the class are read together, inside an at-rule too.
    ("a size and a clip in 2 rules", ".x { height: 3px; } .x { overflow: hidden; }", "hide the bare class .x"),
    ("a size and a small scroll box in 2 rules", ".x { height: 3px; } .x { overflow: auto; }", "hide the bare class .x"),
    ("a size in @media and a clip in the base rule",
        "@media (min-width: 1px) { .x { height: 3px; } } .x { overflow: hidden; }", "hide the bare class .x"),
    ("a size in a selector list and a clip in another rule", ".y, .x { height: 3px; } .x { overflow: hidden; }",
        "hide the bare class .x"),
    # A class name is any CSS identifier.
    ("a class named --x", ".--x { display: none; }", "hide the bare class .--x"),
    ("a class named with U+00E9", ".é { display: none; }", "hide the bare class .é"),
    ("a class named x and U+00E9", ".xé { display: none; }", "hide the bare class .xé"),
    # The keyframes of a listed animation, the palette colours that color names, and @font-face are pinned.
    ("field-in redefined to end hidden", "@keyframes field-in { to { opacity: 0; } } .x { margin: 0; }",
        "other than those of KEYFRAMES"),
    ("field-in redefined in upper case",
        "@keyframes FIELD-IN { from { opacity: 0; } to { opacity: 0; } } .x { margin: 0; }",
        "other than those of KEYFRAMES"),
    ("keyframes named by a string", '@keyframes "field-in" { to { opacity: 0; } } .x { margin: 0; }',
        "names its keyframes"),
    ("a transparent colour", ".x { color: transparent; }", "hide the bare class .x"),
    ("the colour of a surface", ".x { color: var(--surface-raised); }", "hide the bare class .x"),
    ("a pinned palette colour set to transparent", ".x { color: var(--text); } :root { --text: transparent; }",
        "sets --text to 'transparent'"),
    ("an @font-face that shrinks its glyphs",
        '@font-face { font-family: "a"; src: url("a.woff2") format("woff2"); size-adjust: 1%; } .x { margin: 0; }',
        "sets the descriptor size-adjust to '1%'"),
    ("a rule after a string ended by a line break", '.y { content: "a\n} .x { display: none; } .z { content: "b"; }',
        "a line break ends"),
    ("an unclosed string", '.x { content: "a; }', "its end leaves open"),
    ("an escaped brace in a selector", ".y\\{ { color: red; } .x { display: none; }", "a backslash outside"),
    ("an escaped class name", ".\\78 { display: none; }", "a backslash outside"),
    ("a brace in brackets", ".x { a: ( } { ); display: none; }", "a brace inside brackets"),
    ("a brace in an attribute selector", '.x[title="a"], [a=b}] { display: none; }', "a brace inside brackets"),
    ("a } in an unquoted url()", ".x { background: url(a}b); display: none; }", "an unquoted url()"),
    ("a quote in an unquoted url()", '.x { background: URL(a"b); display: none; } .y { content: ""; }',
        "an unquoted url()"),
    ("a ( in an unquoted url()", ".x { background: url(a(b); }", "an unquoted url()"),
    ("a rule nested in a rule", ".x { display: none; & .y { color: red; } }", "a rule inside a rule"),
    ("@scope", "@scope (.x) { :scope { display: none; } }", "@scope"),
    ("@import", '@import "more.css"; .y { color: red; }', "@import"),
    ("an HTML comment marker", "<!-- .x { display: none; } -->", "<!-- or -->"),
    ("an unclosed comment", ".x { display: none; } /* .y { }", "an unclosed comment"),
    ("an unclosed rule", ".x { display: none;", "unbalanced braces"),
    ("a stray }", ".y { color: red; } } .x { display: none; }", "unbalanced braces"),
    ("a stray )", ".x { a: ); display: none; }", "unbalanced braces"),
    ("an unclosed parenthesis", ".x { display: none; } (", "unbalanced braces"),
    ("an @import at the end without a ;", '.y { color: red; } @import "more.css"', "@import"),
    ("no rule", "/* nothing */", "holds no rule"),
    ("a pinned custom property set outside its list",
        ".x { padding: 0 var(--pad); } :root { --pad: 9999px; }", "sets --pad to '9999px'"),
    ("a } in a string in a showing rule", '.x { font-family: "}", serif; grid-template-areas: "a b"; }', ""),
    ("a ; and display: none in a string", ".x { font-family: 'a; display: none', serif; }", ""),
    ("a listed value written over 2 lines", ".x { margin: 0\n  auto; }", ""),
    ("a listed class hidden, braces in a comment", "/* { } */ .vh { display: none; } @media print { .x { } }", ""),
    ("a quoted url() and a keyframes rule", '@font-face { src: url("a{b}.woff2") format("woff2"); } '
        "@keyframes k { from { opacity: 0; } } .x { margin: 0; }", ""),
    ("field-in as baseline.css gives it",
        "@keyframes field-in { from { opacity: 0; } to { opacity: 1; } } .x { margin: 0; }", ""),
    ("an @font-face as fonts.css gives it", '@font-face { font-family: "a"; font-style: normal; font-weight: 100 900; '
        'font-display: swap; src: url("a.woff2") format("woff2"); } .x { color: var(--text); }', ""),
    ("brackets in an unquoted url(), as CSS allows", ".x { background: url(a[b]); }", ""),
    ("a pinned custom property set to its listed value",
        ":root { --pad: clamp(1rem, 3vw, 3.2rem); } .x { padding: 0 var(--pad); }", ""),
)
# Runs the gate under a faked version tuple outside SUPPORTED_PYTHONS, 1 on each side of 3.14: 3.13.3, the
# Cloudflare Pages image default, and 3.15.0. Only the gate's own guard prints OWN_REFUSAL; the catch of
# UnsupportedPython prints its line after the pages are read.
FAKED_VERSIONS = ((3, 13, 3), (3, 15, 0))
VERSION_PROBE = (
    "import sys, runpy; "
    "sys.version_info = ({}, {}, {}, 'final', 0); "
    "runpy.run_path(sys.argv[1], run_name='__main__')"
)
OWN_REFUSAL = "check-install-page: runs only on Python 3.14, the version it is tested on; this is Python {}.{}"
INLINE_GATE = "tools/check-inline-code.py"
# The supported list of tools/check-inline-code.py, whatever it holds, and 1 that leaves this version out, so that
# inline_code_problems raises UnsupportedPython while the gate's own guard passes.
INLINE_LIST = re.compile(r"^SUPPORTED_PYTHONS = .*$", re.M)
INLINE_UNSUPPORTED = "SUPPORTED_PYTHONS = ((2, 7),)"


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


def move(relative: str, start: str, end: str, before: str):
    """Move the markup from the first start up to the first end after it, so it sits just before the first before."""
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        block = text[text.index(start):text.index(end, text.index(start))]
        text = text.replace(block, "", 1)
        path.write_text(text.replace(before, block + before, 1), encoding="utf-8")
    return apply


def into_body(first: str, before: str = "", after: str = ""):
    """Move the head's lines from first to </head> to the start of the body, in order, between before and after."""
    def apply(root: Path) -> None:
        path = root / PAGE
        text = path.read_text(encoding="utf-8")
        block = text[text.index(first):text.index("</head>")]
        text = text.replace(block, "", 1).replace("<body>\n", "<body>\n" + before + block + after, 1)
        path.write_text(text, encoding="utf-8")
    return apply


def decoy(relative: str):
    """Load baseline.css without its token, and keep the tokened tag only in a comment."""
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        tag = re.search(r'<link rel="stylesheet" href="/assets/baseline/baseline\.css\?v=[^"]*">', text).group(0)
        path.write_text(text.replace(tag, tag.replace("?v=", "?x=") + "<!-- " + tag + " -->", 1), encoding="utf-8")
    return apply


def steps_of(root: Path, relative: str) -> str:
    """The first step list of a page, from its <ol class="steps"> to the first </ol> after it."""
    text = (root / relative).read_text(encoding="utf-8")
    start = text.index(STEPS)
    return text[start:text.index("</ol>", start) + len("</ol>")]


def swap(first: str, second: str):
    """Exchange the contents of 2 pages, so each sits at the other's path."""
    def apply(root: Path) -> None:
        texts = [(root / relative).read_text(encoding="utf-8") for relative in (first, second)]
        (root / first).write_text(texts[1], encoding="utf-8")
        (root / second).write_text(texts[0], encoding="utf-8")
    return apply


CASES = [
    ("the committed tree", None, 0),
    ("a family link pointing elsewhere", edit(PAGE, 'id="chatgpt" href="/install/chatgpt/"', 'id="chatgpt" href="/install/gemini/"'), 1),
    ("a family link removed", edit(PAGE, '<a class="btn inline" id="claude" href="/install/claude/">Claude</a> ', ""), 1),
    ("a family id removed", edit(PAGE, 'id="gemini" href="/install/gemini/"', 'href="/install/gemini/"'), 1),
    ("a family link duplicated", edit(PAGE, OTHER_LINK, OTHER_LINK + ' <a class="btn inline" id="copilot" href="/install/copilot/">Copilot</a>'), 1),
    ("a family link that is not a button", edit(PAGE, '<a class="btn inline" id="copilot"', '<a id="copilot"'), 1),
    # HTML splits class names on ASCII whitespace only: btn U+00A0 inline is 1 class, and x U+00A0 vh is not vh.
    ("a family link whose btn and inline are joined by a no-break space",
        edit(PAGE, '<a class="btn inline" id="copilot"', '<a class="btn\u00a0inline" id="copilot"'), 1),
    ("a family page heading whose 1 class joins x and vh by a no-break space", edit(CLAUDE, "<h1>", '<h1 class="x\u00a0vh">'), 0),
    ("header.mast with a no-break space in its class on a family page",
        edit(CLAUDE, '<header class="mast">', '<header class="mast\u00a0x">'), 1),
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
    # With the get id moved above the pick label, the h1, the label and the row stay in place, so only the order
    # check refuses.
    ("the get id moved above the pick label", both(edit(PAGE, '<h2 id="get">', "<h2>"),
        edit(PAGE, '<p class="meta">', '<p class="meta" id="get">')), 1),
    ("the h1, the pick label and the button row after the get id", both(edit(PAGE, HERO + "\n", ""),
        edit(PAGE, PICK + "\n" + ROW_LINE + "\n", ""), edit(PAGE, '<h2 id="get">Get Clean Language</h2>',
        '<h2 id="get">Get Clean Language</h2>\n' + HERO + "\n" + PICK + "\n" + ROW_LINE)), 1),
    # The opening of the page's content is pinned (the gate's BODY_OPENING, MAIN_OPENING and DOC_OPENING), so any
    # element moved or added there fails, shown or hidden, whatever its class.
    ("the h1, the pick label and the button row moved down together, still before the get id",
        both(edit(PAGE, HERO + "\n", ""), edit(PAGE, PICK + "\n" + ROW_LINE + "\n", ""),
             edit(PAGE, GET_LABEL, HERO + "\n" + PICK + "\n" + ROW_LINE + "\n" + GET_LABEL)), 1),
    ("Scope and On a phone moved above the h1", move(PAGE, SCOPE, GET_LABEL, HERO), 1),
    ("Scope and On a phone moved above the h1, their labels given the class first", both(
        move(PAGE, SCOPE, GET_LABEL, HERO), edit(PAGE, SCOPE, SCOPE.replace("lbl blk", "lbl blk first")),
        edit(PAGE, '<p class="lbl accent blk">', '<p class="lbl accent blk first">')), 1),
    ("a second label with the class first above the h1", edit(PAGE, HERO, '<p class="lbl first">Scope</p>\n' + HERO), 1),
    ("a callout without a label above the h1", edit(PAGE, HERO, '<div class="callout"><p>Note.</p></div>\n' + HERO), 1),
    ("a paragraph in main before div.wrap", edit(PAGE, MAIN, MAIN + "<p>Note.</p>\n"), 1),
    ("a paragraph between div.wrap and div.doc", edit(PAGE, '<div class="wrap"><div class="doc">',
        '<div class="wrap"><p>Note.</p><div class="doc">'), 1),
    ("a heading inside the meta paragraph", edit(PAGE, '<p class="meta">', '<p class="meta"><h2>Scope</h2>'), 1),
    ("a label inside div.rail", edit(PAGE, '<div class="rail">', '<div class="rail">' + SCOPE), 1),
    ("a heading above the h1, outside main", edit(PAGE, "<main", "<h2>Install</h2>\n<main"), 1),
    ("main opened after the h1", both(edit(PAGE, MAIN, ""), edit(PAGE, HERO + "\n", HERO + "\n" + MAIN)), 1),
    ("a label above the h1, outside main", edit(PAGE, MAIN, '<p class="lbl">Install</p>\n' + MAIN), 1),
    # The pin reads the body's elements before main, not what header.mast holds, so a hidden heading in its nav passes.
    ("a vh heading in the nav", edit(PAGE, '<nav class="nav" aria-label="Site">',
        '<nav class="nav" aria-label="Site"><h2 class="vh">Site</h2>'), 0),
    # The class first only changes the opening label's padding (baseline.css), so a label without it is correct.
    ("the opening label without the class first", edit(PAGE, '<p class="lbl first">Install</p>', '<p class="lbl">Install</p>'), 0),
    ("the hero's h1 hidden", edit(PAGE, HERO, HERO.replace("<h1>", '<h1 class="vh">')), (1, "the hero's h1 reads as hidden")),
    ("the hero's h1 emptied", edit(PAGE, HERO, "<h1></h1>"), (1, "the hero's h1 reads as hidden or has no text")),
    ("the pick label hidden", edit(PAGE, PICK, PICK.replace("lbl blk", "lbl blk vh")), (1, 'the "pick" label reads as hidden')),
    ("the hero's h1 with a bdo", edit(PAGE, HERO, HERO.replace("<h1>Pick", '<h1><bdo dir="rtl">Pick</bdo>')),
        (1, "the hero's h1 holds a bdo element or a dir")),
    ("the hero's h1 with a dir attribute", edit(PAGE, HERO, HERO.replace("<h1>", '<h1 dir="rtl">')),
        (1, "the hero's h1 holds a bdo element or a dir")),
    # A bidi control, a bdo or a dir can reorder the letters of the hero's h1, the pick label or a family link's label.
    ("the hero's h1 with a right-to-left override", edit(PAGE, HERO, HERO.replace("Pick the", "Pick &#x202E;the")),
        (1, "the hero's h1 holds a bidi control")),
    ("the pick label with a right-to-left override",
        edit(PAGE, PICK, PICK.replace(">Pick your AI<", ">Pick &#x202E;your AI<")), (1, 'the "pick" label holds a bidi')),
    ("the pick label with a dir attribute", edit(PAGE, PICK, PICK.replace(' id="pick"', ' id="pick" dir="rtl"')),
        (1, 'the "pick" label holds a bidi')),
    ("a family link whose label a bdo reverses",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", '><bdo dir="rtl">Claude</bdo><')),
        (1, "the claude family link's label holds a bidi")),
    ("a family link with a dir attribute", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace("<a ", '<a dir="rtl" ')),
        (1, "the claude family link's label holds a bidi")),
    ("a family link whose label holds a right-to-left override",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">Cla&#x202E;ude<")),
        (1, "the claude family link's label holds a bidi")),
    # No element that starts before the button row ends, shown or hidden, may be a bdo or carry dir, in any value:
    # a dir on the row or an ancestor can show the buttons in another order, and a browser reopens a formatting
    # element that an end tag closed out of order, with its dir, around the later links.
    ("a family link beside a bdo in a hidden span",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><span>Claude</span><span hidden><bdo>x</bdo></span><")),
        (1, ROW_DIR)),
    ("the button row with a dir attribute", edit(PAGE, ROW, ROW.replace("<p>", '<p dir="rtl">')), (1, ROW_DIR)),
    ("div.doc with a dir attribute", edit(PAGE, '<div class="doc">', '<div class="doc" dir="rtl">'), (1, ROW_DIR)),
    ("div.wrap with dir=auto", edit(PAGE, '<div class="wrap">', '<div class="wrap" dir="auto">'), (1, ROW_DIR)),
    ("main with a dir attribute", edit(PAGE, MAIN, '<main id="main-content" dir="rtl">\n'), (1, ROW_DIR)),
    ("the body with a dir attribute", edit(PAGE, "<body>", '<body dir="rtl">'), (1, ROW_DIR)),
    ("the html element with dir=ltr", edit(PAGE, '<html lang="en"', '<html dir="ltr" lang="en"'), (1, ROW_DIR)),
    ("a bdo around the body", edit(PAGE, "<body>", "<bdo><body>"), (1, ROW_DIR)),
    ("the title with a dir attribute", edit(PAGE, "<title>", '<title dir="rtl">'), (1, ROW_DIR)),
    ("the skip link, hidden, with a dir attribute", edit(PAGE, '<a class="skip"', '<a class="skip" dir="rtl"'), (1, ROW_DIR)),
    ("header.mast with a dir attribute", edit(PAGE, '<header class="mast">', '<header class="mast" dir="rtl">'),
        (1, ROW_DIR)),
    ("the site navigation with a dir attribute",
        edit(PAGE, '<nav class="nav" aria-label="Site">', '<nav class="nav" aria-label="Site" dir="rtl">'), (1, ROW_DIR)),
    ("the opening label with a dir attribute",
        edit(PAGE, '<p class="lbl first">Install</p>', '<p class="lbl first" dir="rtl">Install</p>'), (1, ROW_DIR)),
    ("p.meta with a dir attribute", edit(PAGE, '<p class="meta">', '<p class="meta" dir="rtl">'), (1, ROW_DIR)),
    ("the rail image with a dir attribute", edit(PAGE, '<img class="rail-logo"', '<img dir="rtl" class="rail-logo"'),
        (1, ROW_DIR)),
    ("a b with dir closed out of order in a hidden span in a family link",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", '>Claude<span hidden><b dir="rtl"></span><')), (1, ROW_DIR)),
    # A browser adds the attributes of a later html or body start tag to the page's own element.
    ("a later body start tag with a dir attribute", edit(PAGE, "</main>", '</main><body dir="rtl">'), (1, PAGE_DIR)),
    ("the pick label emptied", edit(PAGE, PICK, PICK.replace(">Pick your AI<", "><")),
        (1, 'the "pick" label has no text that reads as visible')),
    ("the pick label of only U+200B", edit(PAGE, PICK, PICK.replace(">Pick your AI<", ">" + chr(0x200B) + "<")),
        (1, 'the "pick" label has no text that reads as visible')),
    # Text sitting directly in div.doc, div.wrap, main or the body above the button row fails as an element does.
    ("bare text between the pick label and the button row", edit(PAGE, PICK, PICK + "\nChoose one."),
        (1, "text sits directly in the body, main, div.wrap or div.doc")),
    ("bare text above the h1", edit(PAGE, HERO, "Note.\n" + HERO), (1, "text sits directly in the body")),
    ("bare text in main before div.wrap", edit(PAGE, MAIN, MAIN + "Note.\n"), (1, "text sits directly in the body")),
    ("bare text in the body before main", edit(PAGE, "<main", "Note.\n<main"), (1, "text sits directly in the body")),
    ("a blank line between the pick label and the button row", edit(PAGE, PICK, PICK + "\n \n"), 0),
    ("bare text right after the button row", edit(PAGE, ROW_END, ROW_END + "Note."), 0),
    # A hiding body start tag hides the h1 and the label whose text the parser has already read as visible.
    ("the hero's h1 hidden by a later body start tag", edit(PAGE, "</main>", "</main><body hidden>"),
        (1, "the hero's h1 reads as hidden")),
    ("the pick label hidden by a later html start tag", edit(PAGE, "</main>", '</main><html class="vh">'),
        (1, 'the "pick" label reads as hidden')),
    ("the pick label without the class lbl", edit(PAGE, PICK, PICK.replace("lbl blk", "blk")), 1),
    # div.doc then holds only the pinned opening's first 2 elements; the gate must say so, not crash.
    ("div.doc closed after the h1", edit(PAGE, HERO, HERO + '</div><div class="doc">'),
        (1, "the opening of the page's content is not")),
    ("main replaced by a div", both(edit(PAGE, MAIN, '<div id="main-content">\n'), edit(PAGE, "</main>", "</div>")), 1),
    ("the pick label without its id, beside an id elsewhere", both(edit(PAGE, PICK, PICK.replace(' id="pick"', "")),
        edit(PAGE, SCOPE, SCOPE.replace('">', '" id="pick">'))), (1, 'does not carry the "pick" id')),
    # The pick id on a paragraph that is not a label, moved with the button row above the h1.
    ("the pick paragraph without its label class and the button row moved above the h1", both(
        edit(PAGE, PICK + "\n" + ROW_LINE + "\n", ""),
        edit(PAGE, HERO, PICK.replace('class="lbl blk" ', "") + "\n" + ROW_LINE + "\n" + HERO)), 1),
    ("the button row moved down, still before the get id", both(edit(PAGE, ROW_LINE + "\n", ""),
        edit(PAGE, '<p class="lbl sec">Get Clean Language</p>', ROW_LINE + '\n<p class="lbl sec">Get Clean Language</p>')), 1),
    # Moved together below Scope and On a phone, the label and the row pass every other check.
    ("the pick label and the button row moved down together, still before the get id",
        both(edit(PAGE, PICK + "\n" + ROW_LINE + "\n", ""), edit(PAGE, '<p class="lbl sec">Get Clean Language</p>',
             PICK + "\n" + ROW_LINE + '\n<p class="lbl sec">Get Clean Language</p>')), 1),
    ("the pick label and the button row moved above the h1",
        both(edit(PAGE, PICK + "\n" + ROW_LINE + "\n", ""), edit(PAGE, HERO, PICK + "\n" + ROW_LINE + "\n" + HERO)), 1),
    # The gate must say that the h1 is missing: a crash on the missing h1 also exits 1.
    ("the install page with no h1 and no label above the pick label", both(edit(PAGE, '<p class="lbl first">Install</p>',
        "<p>Install</p>"), edit(PAGE, HERO, "<p>Pick the AI you use and follow the steps</p>")), (1, "the page has no h1")),
    # Nothing may sit between the pick label and the row, shown or hidden.
    ("a paragraph without a label between the pick label and the button row", edit(PAGE, PICK, PICK + "\n<p>Choose one.</p>"), 1),
    ("a vh heading between the pick label and the button row", edit(PAGE, PICK, PICK + '\n<h2 class="vh">Pick</h2>'), 1),
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
    # A browser with scripting on renders no markup inside noscript, so neither an id nor a link there is present.
    ("the test id only inside a noscript", both(
        edit(PAGE, '<h2 id="test">', "<h2>"), edit(PAGE, "</main>", '<noscript><span id="test"></span></noscript></main>')), 1),
    ("a duplicate id on a family page", edit(CHATGPT, '<p class="verified">', '<p class="verified" id="main-content">'), 1),
    ("a family page missing", remove(GEMINI), 3),
    ("a family page with no setup steps", edit(CLAUDE, '<ol class="steps">', "<ol>"), 1),
    ("a family page with an empty step list", edit(OTHER, STEPS, STEPS + "</ol><ol>"), 1),
    # Copilot's second step list keeps its steps, so each list must have a step, not only the page.
    ("a family page step list whose 1 setup step is empty",
        lambda root: edit(COPILOT, steps_of(root, COPILOT), STEPS + "<li><span></span></li></ol>")(root), 1),
    ("a family page whose steps are only in a hidden li",
        lambda root: edit(OTHER, steps_of(root, OTHER), STEPS + "<li hidden><span>Save the file.</span></li></ol>")(root), 1),
    # Text in a step list inside a step counts for that step too, unless it is hidden.
    ("a family page step whose only text is in a nested step list", lambda root: edit(OTHER, steps_of(root, OTHER),
        STEPS + "<li>" + STEPS + "<li>Save the file.</li></ol></li></ol>")(root), 0),
    ("a family page step whose only text is hidden in a nested step list", lambda root: edit(OTHER, steps_of(root, OTHER),
        STEPS + "<li>" + STEPS + "<li><span hidden>Save the file.</span></li></ol></li></ol>")(root), 1),
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
    ("a family page heading naming another family", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Gemini</h1>"), 1),
    ("a family page heading naming its family only in a vh span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1>Setup<span class="vh"> ChatGPT</span></h1>'), 1),
    ("the Claude and ChatGPT family pages swapped", swap(CLAUDE, CHATGPT), 1),
    ("a family page heading naming its family in a span", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1><span>ChatGPT</span></h1>"), 0),
    # The name is compared without regard to case, with U+0000 and ZERO_WIDTH but U+00A0 deleted, and each run of
    # whitespace, U+00A0 included, and each br that no element hides read as a space.
    ("a family page heading naming its family in another case",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI Systems</h1>"), 0),
    ("a family page heading naming its family with a soft hyphen", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Chat&shy;GPT</h1>"), 0),
    ("a family page heading naming its family across a br",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI<br>systems</h1>"), 0),
    ("a family page heading naming its family across a no-break space",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI\u00a0systems</h1>"), 0),
    ("a family page heading naming its family with U+034F inside it",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Chat\u034fGPT</h1>"), 1),
    ("a family page heading joining its family's name across a hidden br",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI<br hidden>systems</h1>"), 1),
    # A browser reads </br> as <br>.
    ("a family page heading naming its family across </br>",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI</br>systems</h1>"), 0),
    ("a family page heading joining its family's name across </br> in a hidden span",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI<span hidden></br></span>systems</h1>"), 1),
    # A bidi control can show the name's letters in another order: Chat, U+202E, GPT and U+202C show "ChatTPG".
    ("a family page heading whose name a right-to-left override reorders",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Chat&#x202E;GPT&#x202C;</h1>"), (1, "holds a bidi control")),
    *[(f"a family page heading naming its family beside U+{code:04X}",
        edit(CHATGPT, "<h1>ChatGPT</h1>", f"<h1>ChatGPT{chr(code)}</h1>"), (1, "holds a bidi control"))
        for code in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))],
    ("a family page heading naming its family beside a bidi control in a hidden span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>ChatGPT<span hidden>" + chr(0x202E) + "</span></h1>"), 0),
    # A bdo or a dir attribute can reorder the letters too: <bdo dir="rtl">GPT</bdo> shows "TPG".
    ("a family page heading whose name a bdo reverses in part",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1>Chat<bdo dir="rtl">GPT</bdo></h1>'), (1, "holds a bdo element or a dir")),
    ("a family page heading whose name a bdo reverses whole",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1><bdo dir="rtl">ChatGPT</bdo></h1>'), (1, "holds a bdo element or a dir")),
    ("a family page heading with a bdo and no dir",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Chat<bdo>GPT</bdo></h1>"), (1, "holds a bdo element or a dir")),
    ("a family page heading with a dir attribute on a span inside it",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1>Chat<span dir="rtl">GPT</span></h1>'), (1, "holds a bdo element or a dir")),
    ("a family page heading with a dir attribute", edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1 dir="ltr">ChatGPT</h1>'),
        (1, "holds a bdo element or a dir")),
    # As on /install/, no element that starts before the h1 ends, shown or hidden, may be a bdo or carry dir.
    ("a family page heading naming its family beside a bdo in a hidden span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1>ChatGPT<span hidden><bdo dir="rtl">x</bdo></span></h1>'), (1, H1_DIR)),
    ("a family page heading inside a bdo", wrap(OTHER, "<h1>", "</h1>", "<bdo>", "</bdo>"), (1, H1_DIR)),
    ("a family page's div.doc with a dir attribute", edit(CHATGPT, '<div class="doc">', '<div class="doc" dir="rtl">'),
        (1, H1_DIR)),
    ("a family page's main with a dir attribute", edit(GEMINI, MAIN, '<main id="main-content" dir="rtl">\n'), (1, H1_DIR)),
    ("a family page's body with a dir attribute", edit(CLAUDE, "<body>", '<body dir="rtl">'), (1, H1_DIR)),
    ("a family page's opening label with a dir attribute",
        edit(COPILOT, '<p class="lbl first">', '<p class="lbl first" dir="rtl">'), (1, H1_DIR)),
    ("a b with dir closed out of order before a family page heading",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<p><b dir="rtl"></p><h1>ChatGPT</h1>'), (1, H1_DIR)),
    ("a later html start tag with a dir attribute on a family page", edit(OTHER, "</main>", '</main><html dir="rtl">'),
        (1, PAGE_DIR)),
    ("a family page inside a hidden wrapper", edit(GEMINI, '<div class="doc">', '<div class="doc" inert>'), 1),
    ("the button row with popover", edit(PAGE, ROW, '<p popover><a class="btn inline" id="claude"'), 1),
    ("the button row inside a dialog without open", wrap(PAGE, ROW, ROW_END, "<dialog>", "</dialog>"), 1),
    ("the button row inside a closed details", wrap(PAGE, ROW, ROW_END, "<details><summary>Pick</summary>", "</details>"), 1),
    ("the button row inside a datalist", wrap(PAGE, ROW, ROW_END, "<datalist>", "</datalist>"), 1),
    ("the button row inside a noscript", wrap(PAGE, ROW, ROW_END, "<noscript>", "</noscript>"), 1),
    ("the button row inside an rp", wrap(PAGE, ROW, ROW_END, "<rp>", "</rp>"), 1),
    ("the button row inside a title", wrap(PAGE, ROW, ROW_END, "<title>", "</title>"), 1),
    ("the button row with data-popover", edit(PAGE, ROW, '<p data-popover><a class="btn inline" id="claude"'), 0),
    # The pin refuses a dialog around the whole row, so the label of 1 link sits in it.
    ("a family link whose label is in an open dialog",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><dialog open>Claude</dialog><")), 0),
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
    # The button row holds only the family links and the whitespace between them, so any other element or text in
    # it fails, a br included; the family page case below keeps a void <br/> from holding what follows.
    ("the button row with <br/> after its first link", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK + "<br/>"),
        (1, "holds the elements")),
    ("a div between 2 family links", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK + "<div></div>"), (1, "holds the elements")),
    ("a heading opening the button row's paragraph", edit(PAGE, ROW, '<p><h2>Pick</h2><a class="btn inline" id="claude"'),
        (1, "holds the elements")),
    ("an h2 between 2 family links", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK + "<h2>Pick</h2>"), (1, "holds the elements")),
    ("text between 2 family links", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK + " or "),
        (1, "text other than whitespace sits directly in the paragraph of family links")),
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
    ("a family page whose only link to #test is inside a noscript", both(
        edit(CLAUDE, 'href="/install/#test"', 'href="/install/"', every=True),
        edit(CLAUDE, "</main>", '<noscript><a href="/install/#test">Test it</a></noscript></main>')), 1),
    ("a family page whose links back to #get are hidden", edit(GEMINI, 'href="/install/#get"', 'href="/install/#get" hidden', every=True), 1),
    ("a family page whose links back to #get are empty",
        edit(GEMINI, '<a href="/install/#get">Get Clean Language</a>', '<a href="/install/#get"></a>', every=True), 1),
    ("a family page whose links to #test are hidden", edit(CLAUDE, 'href="/install/#test"', 'href="/install/#test" hidden', every=True), 1),
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
    # A script inside noscript never runs: a browser with scripting on reads it as text, and one with scripting off
    # runs no script.
    ("copy.js loaded only inside a body noscript",
        both(edit(PAGE, COPY + "\n", ""), edit(PAGE, "<body>\n", "<body>\n<noscript>" + COPY + "</noscript>\n")), 1),
    ("copy.js loaded only inside a noscript on a family page",
        both(edit(OTHER, COPY + "\n", ""), edit(OTHER, "</main>", "</main><noscript>" + COPY + "</noscript>")), 1),
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
    ("the scheme.js tag missing", edit(PAGE, SCHEME + "\n", ""), 1),
    ("the scheme.js tag with defer", edit(PAGE, SCHEME, SCHEME.replace('"></script>', '" defer></script>')), 1),
    ("the scheme.js tag with async", edit(PAGE, SCHEME, SCHEME.replace('"></script>', '" async></script>')), 1),
    ("the scheme.js tag with src before data-cfasync", edit(PAGE, SCHEME,
        '<script src="/assets/baseline/scheme.js?v=1.8.0" data-cfasync="false"></script>'), 1),
    ("the scheme.js tag after the first stylesheet", both(edit(PAGE, SCHEME + "\n", ""),
        edit(PAGE, "</head>", SCHEME + "\n</head>")), 1),
    ("the scheme.js tag twice", edit(PAGE, SCHEME, SCHEME + SCHEME), 1),
    ("a second scheme.js with defer", edit(PAGE, "</head>",
        '<script src="/assets/baseline/scheme.js?v=1.8.0" defer></script>\n</head>'), 1),
    ("a second scheme.js in upper case with a character reference", edit(PAGE, "</head>",
        '<SCRIPT SRC="/assets/baseline/sch&#101;me.js?v=1.8.0" defer></SCRIPT>\n</head>'), 1),
    ("a second scheme.js with spaces around =", edit(PAGE, "</head>",
        '<script src = "/assets/baseline/scheme.js?v=1.8.0" defer></script>\n</head>'), 1),
    ("an upper-case stylesheet before the scheme.js tag", edit(PAGE, SCHEME,
        '<LINK REL="stylesheet" HREF="/assets/baseline/fonts.css?v=1.8.0">\n' + SCHEME), 1),
    ("a stylesheet before the scheme.js tag as the first of 2 rel attributes", edit(PAGE, SCHEME,
        '<LINK REL="stylesheet" REL="icon" HREF="/assets/baseline/fonts.css?v=1.8.0">\n' + SCHEME), 1),
    ("the scheme.js tag and the stylesheets moved into the body, in order", into_body(SCHEME), 1),
    ("the stylesheets moved into the body, after the scheme.js tag", into_body(FONTS), 1),
    ("the scheme.js tag and the stylesheets in a second head inside the body", into_body(SCHEME, "<head>\n", "</head>\n"), 1),
    ("a later stylesheet moved into the body, after the first", into_body(LATER), 1),
    ("a later stylesheet in upper case at the end of the body", edit(PAGE, "</body>",
        '<LINK REL="stylesheet" HREF="/assets/baseline/baseline.css?v=1.8.0">\n</body>'), 1),
    ("a later stylesheet in a second head after the body", both(edit(PAGE, LATER + "\n", ""),
        edit(PAGE, "</body>\n", "</body>\n<head>\n" + LATER + "\n</head>\n")), 1),
    # HTML5 ends the head at text other than whitespace, a start tag a head may not hold, or </br>, and keeps a
    # self-closing title open, so all after it is its text; the loads after such a point are not in the head. A
    # comment and whitespace leave it open.
    ("text before the scheme.js tag", edit(PAGE, SCHEME, "x\n" + SCHEME), 1),
    ("a div before the scheme.js tag", edit(PAGE, SCHEME, "<div></div>\n" + SCHEME), 1),
    ("</br> before the scheme.js tag", edit(PAGE, SCHEME, "</br>\n" + SCHEME), 1),
    ("a self-closing title before the scheme.js tag, and no </head>", both(
        edit(PAGE, SCHEME, "<title/>" + SCHEME), edit(PAGE, "</head>\n", "")), 1),
    ("a comment and whitespace before the scheme.js tag", edit(PAGE, SCHEME, "<!-- x -->\n \t\n" + SCHEME), 0),
    ("a self-closing nav.nav before the switch", edit(PAGE, '<button class="scheme"', '<nav class="nav"/><button class="scheme"'), 1),
    ("a second element with data-scheme-toggle, a button in the content", edit(PAGE, "</main>",
        '<p><button class="scheme" type="button" data-scheme-toggle hidden><span class="vh">Dark mode</span></button></p></main>'), 1),
    # PR 213 replaced the family sections with family pages; this case moved from the claude section to its page.
    ("a family page heading hidden by the first of 2 class attributes", edit(CLAUDE, "<h1>",
        '<h1 class="visually-hidden" class="x">'), 1),
    ("fonts.css loaded only inside a comment", edit(PAGE, FONTS, "<!--" + FONTS + "-->"), 1),
    ("rail.js with another attribute", edit(PAGE, "</head>",
        '<script src="/assets/baseline/rail.js?v=1.3.0" type="module" defer></script>\n</head>'), 1),
    # The load and switch checks hold on the family pages too.
    ("the scheme.js tag missing on a family page", edit(GEMINI, SCHEME + "\n", ""), 1),
    ("the scheme.js tag after the first stylesheet on a family page", both(edit(COPILOT, SCHEME + "\n", ""),
        edit(COPILOT, "</head>", SCHEME + "\n</head>")), 1),
    ("a later stylesheet at the end of the body on a family page", both(edit(OTHER, LATER + "\n", ""),
        edit(OTHER, "</body>", LATER + "\n</body>")), 1),
    ("a second element with data-scheme-toggle on a family page", edit(CHATGPT, "</main>",
        '<p><button class="scheme" type="button" data-scheme-toggle hidden><span class="vh">Dark mode</span></button></p></main>'), 1),
    ("site.css without its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?w=1">\n</head>'), 1),
    ("site.css with its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?v=0123456789ab">\n</head>'), 0),
    ("site.css without its token beside a token inside a comment", edit(PAGE, "</head>",
        '<!--<link rel="stylesheet" href="/assets/site.css?v=0123456789ab">--><link rel="stylesheet" href="/assets/site.css?w=1">\n</head>'), 1),
    # Until PR 218 this was a named residual: the gate matched the tag as text, so a tag in a comment counted.
    ("the tokened baseline.css tag only in a comment", decoy(PAGE), 1),
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
    # On a family page: the pin of /install/'s opening refuses any element or text it reads between the pick label
    # and the row.
    ("a family page step list after <span hidden><div></span>", edit(OTHER, STEPS, "<span hidden><div></span>" + STEPS),
        "after ``<span hidden><div></span>`` the ``span`` stays open"),
    ("a family page step list after <p><div hidden></p>", edit(OTHER, STEPS, "<p><div hidden></p>" + STEPS),
        "after ``<p><div hidden></p>`` the ``div`` stays open"),
    ("a div inside a family link", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><div>Claude</div><")),
        "a browser closes the ``p`` at the ``div``, so the later links sit outside it"),
    ("a family link with another family's label", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">ChatGPT<")),
        "a wrong family link label (another family's, say)"),
    ("a family link labelled only with U+034F", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">" + chr(0x034F) + "<")),
        "a family link label, a step,"),
    ("a family page step of only U+034F",
        lambda root: edit(OTHER, steps_of(root, OTHER), STEPS + "<li>" + chr(0x034F) + "</li></ol>")(root),
        "a step, or a link back to the downloads or the test made only of an invisible character"),
    ("a family page whose links back to #get are labelled only U+034F", edit(GEMINI,
        '<a href="/install/#get">Get Clean Language</a>', '<a href="/install/#get">' + chr(0x034F) + "</a>", every=True),
        "a link back to the downloads or the test made only of an invisible character"),
    ("a family page with an empty verified line", edit(GEMINI, '<p class="verified">', '<p class="verified"></p><p>'),
        "an empty ``p.verified``"),
    ("a family page with 1 setup step hidden", edit(OTHER, STEPS + "<li>", STEPS + "<li hidden>"), "not its steps or their wording"),
    ("a family page with 1 setup step dropped",
        edit(OTHER, STEPS + '<li><span>Save the file, or copy everything from the <a href="/instructions/">instructions page</a>.</span></li>', STEPS),
        "not its steps or their wording"),
    # A bdo or a dir after the button row, or after a family page's h1, passes, as does a bdi.
    ("a dir attribute on the label after the button row", edit(PAGE, SCOPE, SCOPE.replace('">', '" dir="rtl">')),
        "``Scope``'s label, ``p.verified``, a step list or a link back"),
    ("a family page with a dir attribute outside its heading",
        edit(CHATGPT, '<p class="verified">', '<p class="verified" dir="ltr">'),
        "``Scope``'s label, ``p.verified``, a step list or a link back"),
    ("a family link label in a bdi", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><bdi>Claude</bdi><")),
        "a family link label in a ``bdi``"),
]


def hides(declarations: str) -> bool:
    """True when the declarations may hide, clip, or move the element off-screen, read fail closed (see above): it
    splits them at each ";", and reads each declaration with a colon, its property in lower case and without a vendor
    prefix such as -webkit-, its value in lower case, its runs of whitespace read as 1 space and a final "!important"
    dropped. One hides, wherever it sits in the block and whatever its importance, when its property is neither a
    custom property nor 1 of SHOWING_PROPERTIES and its value is not listed for that property in SHOWING_VALUES (so an
    escaped name, which no list holds, hides unless it starts with "--"; css_rules() refuses every backslash outside a
    string, so no name it gives holds 1). The block also hides when it declares 1 of SIZES beside 1 of OVERFLOWS
    whose value holds hidden or clip, or holds auto or scroll while a value of SIZES there is not 1 of SCROLL_SIZES. A
    declaration without a colon is not read, as CSS drops it."""
    read: list[tuple[str, str]] = []
    for declaration in declarations.split(";"):
        name, colon, value = declaration.partition(":")
        name = re.sub(r"^-[a-z0-9]+-", "", name.strip().lower())
        value = " ".join(re.sub(r"!\s*important$", "", value.lower().strip()).split())
        if not colon:
            continue
        if not (name.startswith("--") or name in SHOWING_PROPERTIES or value in SHOWING_VALUES.get(name, ())):
            return True
        read.append((name, value))
    overflow = {word for name, value in read if name in OVERFLOWS for word in value.split()}
    sizes = [value for name, value in read if name in SIZES]
    return bool(sizes) and bool(overflow & {"hidden", "clip"}
                                or overflow & {"auto", "scroll"} and any(value not in SCROLL_SIZES for value in sizes))


def hides_problems() -> list[str]:
    """hides() reads each of HIDING_DECLARATIONS as hiding and none of SHOWING_DECLARATIONS; each value of
    SHOWING_VALUES and -9999px for each of SHOWING_PROPERTIES as showing, and -9999px for each property of
    SHOWING_VALUES and a property neither lists as hiding; each listed value of 1 of SIZES as hiding beside overflow:
    hidden, and beside overflow: auto unless it is 1 of SCROLL_SIZES; and each var() in a listed value names a custom
    property of VARIABLE_VALUES, but as a border's or an outline's colour (BORDER_COLOUR) or inside a clamp() between
    2 positive lengths in rem (BOUNDED), which none of NOT_BOUNDED is."""
    hiding = [*HIDING_DECLARATIONS, *(f"{name}: -9999px" for name in SHOWING_VALUES), "unlisted-property: 0"]
    showing = [*SHOWING_DECLARATIONS, *(f"{name}: -9999px" for name in SHOWING_PROPERTIES),
               *(f"{name}: {value}" for name, values in SHOWING_VALUES.items() for value in values)]
    for name in SIZES:
        for value in SHOWING_VALUES.get(name, ()):
            hiding.append(f"{name}: {value}; overflow: hidden")
            (showing if value in SCROLL_SIZES else hiding).append(f"{name}: {value}; overflow: auto")
    problems = [f"hides() does not read {text!r} as hiding." for text in hiding if not hides(text)]
    problems += [f"hides() reads {text!r} as hiding." for text in showing if hides(text)]
    problems += [f"BOUNDED reads {text!r} as a clamp() between 2 positive lengths in rem." for text in NOT_BOUNDED
                 if BOUNDED.fullmatch(text)]
    return problems + [
        f"SHOWING_VALUES lists {name}: {value}, whose var({variable}) is not in VARIABLE_VALUES."
        for name, values in SHOWING_VALUES.items() for value in values
        for variable in re.findall(r"var\((--[\w-]+)", value)
        if variable not in VARIABLE_VALUES and not BORDER_COLOUR.fullmatch(value) and not BOUNDED.fullmatch(value)
    ]


def unread_at_rule(text: str) -> str:
    """The problem of a prelude or statement that starts an at-rule outside AT_RULES, or ""."""
    rule = re.match(r"\s*@([-\w]*)", text)
    if rule and rule.group(1).lower() not in AT_RULES:
        return f"holds the at-rule @{rule.group(1)}, which it does not read"
    return ""


def css_rules(css: str) -> tuple[list[tuple[str, str, str]], str]:
    """The rules of a stylesheet as (prelude, declarations, at-rule) triples, each in the order its block closes, the
    at-rule being the prelude of the at-rule whose block holds it or "", and "" or the 1 problem that makes it
    unreadable.

    It reads comments and strings as CSS does: a comment ends at the first "*/" and opens nowhere inside a string; a
    string ends at its next unescaped quote, opens nowhere inside a comment, and is read as an empty string ('""'),
    so no brace, ";" or comment opener in either delimits anything. It fails closed on what it does not model: an
    unclosed comment, a string a line break or its end leaves open, a backslash outside a string, "<!--" or "-->", an
    unquoted url() holding a quote, a "(", a brace or a backslash, a brace inside brackets or parentheses, unbalanced
    braces, brackets or parentheses, a rule inside a rule (CSS nesting), and an at-rule outside AT_RULES."""
    rules: list[tuple[str, str, str]] = []
    blocks: list[list[str]] = []
    brackets: list[str] = []
    text: list[str] = []
    index = 0
    while index < len(css):
        char = css[index]
        if css.startswith("/*", index):
            end = css.find("*/", index + 2)
            if end < 0:
                return [], "has an unclosed comment"
            index = end + 2
            continue
        if char in "\"'":
            end = index + 1
            while end < len(css) and css[end] != char and css[end] not in "\r\n\f":
                end += 2 if css[end] == "\\" else 1
            if end >= len(css):
                return [], "has a string that its end leaves open"
            if css[end] != char:
                return [], "has a string that a line break ends"
            text.append('""')
            index = end + 1
            continue
        if char == "\\":
            return [], "holds a backslash outside a string"
        if css.startswith(("<!--", "-->"), index):
            return [], "holds <!-- or -->"
        url = URL_START.match(css, index) if char in "uU" else None
        if url and not re.match(r"[\w-]", css[index - 1:index]) and css[url.end():url.end() + 1] not in ("'", '"'):
            end = css.find(")", index)
            if end < 0 or re.search(r"[\"'(\\{}]", css[index + 4:end]):
                return [], "has an unquoted url() holding a quote, a (, a brace or a backslash"
            text.append(css[index:end + 1])
            index = end + 1
            continue
        if char in "([":
            brackets.append(char)
        elif char in ")]":
            if not brackets or brackets.pop() != "(["[")]".index(char)]:
                return [], "has unbalanced braces, brackets or parentheses"
        elif char in "{}" and brackets:
            return [], "has a brace inside brackets or parentheses"
        elif char == "{":
            prelude = " ".join("".join(text).split())
            if blocks and not blocks[-1][0].startswith("@"):
                return [], "has a rule inside a rule"
            if problem := unread_at_rule(prelude):
                return [], problem
            blocks.append([prelude])
            text = []
            index += 1
            continue
        elif char == "}":
            if not blocks:
                return [], "has unbalanced braces, brackets or parentheses"
            block = blocks.pop()
            rules.append((block[0], "".join(block[1:] + text), blocks[-1][0] if blocks else ""))
            text = []
            index += 1
            continue
        elif char == ";" and not brackets:
            if problem := unread_at_rule("".join(text)):
                return [], problem
            if blocks:
                blocks[-1].append("".join(text) + ";")
            text = []
            index += 1
            continue
        text.append(char)
        index += 1
    if blocks or brackets:
        return [], "has unbalanced braces, brackets or parentheses"
    return ([], problem) if (problem := unread_at_rule("".join(text))) else (rules, "")


def sheet_problems(sheets: list[tuple[str, str]], listed: set[str]) -> list[str]:
    """For the stylesheets sheets, as (path, css) pairs read together: css_rules() can read each; no rule sets a custom
    property of VARIABLE_VALUES to a value outside its list there; each @keyframes is named by an identifier, and
    holds the keyframes of KEYFRAMES where it names 1 of them; each @font-face descriptor has a value of
    FONT_FACE_VALUES; and each bare single class that the declarations of every rule whose selector list holds it,
    read together, hide is in listed."""
    problems: list[str] = []
    joined: dict[str, list[tuple[str, str, str]]] = {}
    for relative, css in sheets:
        rules, problem = css_rules(css)
        if problem or not rules:
            problems.append(f"{relative} {problem or 'holds no rule'}; it cannot be read.")
            continue
        keyframes: list[tuple[str, str]] = []
        for prelude, declarations, at_rule in rules:
            read = []
            for declaration in declarations.split(";"):
                name, colon, value = (part.strip() for part in declaration.partition(":"))
                value = " ".join(re.sub(r"!\s*important$", "", value.lower()).split())
                if colon:
                    read.append((name, value))
            for name, value in read:
                if name in VARIABLE_VALUES and value not in VARIABLE_VALUES[name]:
                    problems.append(f"{relative}: the rule {prelude!r} sets {name} to {value!r}, outside its list in "
                                    "VARIABLE_VALUES of this test, on which listed values of SHOWING_VALUES rely.")
            if re.fullmatch(r"@font-face", prelude, re.I):
                problems += [f"{relative}: the rule {prelude!r} sets the descriptor {name} to {value!r}, outside "
                             "FONT_FACE_VALUES of this test." for name, value in read
                             if value not in FONT_FACE_VALUES.get(name.lower(), ())]
            # A @keyframes block closes after the keyframes inside it, so those read since the last 1 closed are its.
            if re.match(r"@keyframes\b", at_rule, re.I):
                keyframes.append((prelude.lower(), " ".join(declarations.lower().split())))
            elif re.match(r"@keyframes\b", prelude, re.I):
                named = re.fullmatch(r"@keyframes ([-\w]+)", prelude, re.I)
                if not named:
                    problems.append(f"{relative}: the rule {prelude!r} names its keyframes other than by an "
                                    "identifier, which this test does not read.")
                elif named.group(1).lower() in KEYFRAMES and tuple(keyframes) != KEYFRAMES[named.group(1).lower()]:
                    problems.append(f"{relative}: the rule {prelude!r} gives keyframes other than those of KEYFRAMES "
                                    "in this test, on which the listed animation relies.")
                keyframes = []
            if not prelude.startswith("@"):
                for selector in prelude.split(","):
                    bare = BARE_CLASS.fullmatch(selector.strip())
                    if bare:
                        joined.setdefault(bare.group(1), []).append((relative, prelude, declarations))
    for name, held in joined.items():
        if name not in listed and hides(";".join(declarations for _, _, declarations in held)):
            where = ", ".join(dict.fromkeys(relative for relative, _, _ in held))
            preludes = [prelude for _, prelude, _ in held]
            problems.append(
                f"{where}: read together, the rules {preludes!r} hide the bare class .{name}, which is in neither "
                f"HIDING_CLASSES of tools/{GATE.name} nor EXEMPT_CLASSES of this test."
            )
    return problems


def sheet_case_problems() -> list[str]:
    """sheet_problems() gives each of SHEET_CASES exactly 1 problem holding its words, or none where they are ""."""
    problems: list[str] = []
    for name, css, words in SHEET_CASES:
        found = sheet_problems([("the case", css)], {"vh"})
        if (len(found) != 1 or words not in found[0]) if words else found:
            problems.append(f"{name}: expected " + (f"1 problem with {words!r}" if words else "none") + f", got {found}")
    return problems


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
    sheets: list[tuple[str, str]] = []
    for relative in STYLESHEETS:
        try:
            sheets.append((relative, (REPO_ROOT / relative).read_text(encoding="utf-8")))
        except (OSError, UnicodeError) as error:
            problems.append(f"{relative} could not be read: {error}")
    return problems + sheet_problems(sheets, listed)


def version_problems() -> list[str]:
    """The gate runs only on 3.14, and under another version, 3.9 or later, exits 3 before it prints a result line."""
    problems: list[str] = []
    try:
        spec = importlib.util.spec_from_file_location("check_install_page", GATE)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        if gate.SUPPORTED_PYTHONS != ((3, 14),):
            problems.append(f"SUPPORTED_PYTHONS of tools/{GATE.name} is {gate.SUPPORTED_PYTHONS!r}, not ((3, 14),).")
    except Exception as error:
        problems.append(f"SUPPORTED_PYTHONS could not be read from tools/{GATE.name}: {error!r}")
    else:
        try:
            spec = importlib.util.spec_from_file_location("check_inline_code", REPO_ROOT / INLINE_GATE)
            inline = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(inline)
            missing = [version for version in gate.SUPPORTED_PYTHONS if version not in inline.SUPPORTED_PYTHONS]
            if missing:
                problems.append(f"SUPPORTED_PYTHONS of tools/{GATE.name} lists {missing!r}, which {INLINE_GATE} "
                                "does not support, so the gate would exit 3 only after it reads the pages.")
        except Exception as error:
            problems.append(f"SUPPORTED_PYTHONS could not be read from {INLINE_GATE}: {error!r}")
    for version in FAKED_VERSIONS:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            probe = VERSION_PROBE.format(*version)
            result = subprocess.run([sys.executable, "-I", "-c", probe, str(root / "tools" / GATE.name)],
                                    capture_output=True, text=True)
            refusal = OWN_REFUSAL.format(*version[:2])
            if result.returncode != 3 or result.stdout or result.stderr.splitlines() != [refusal]:
                problems.append(f"under Python {version[0]}.{version[1]}: exit {result.returncode}, expected 3 with no "
                                f"result line and only the gate's own refusal {refusal!r}: "
                                f"{(result.stdout + result.stderr).strip()[:300]}")
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        text, count = INLINE_LIST.subn(INLINE_UNSUPPORTED, (root / INLINE_GATE).read_text(encoding="utf-8"), count=1)
        if not count:
            problems.append(f"{INLINE_GATE} has no SUPPORTED_PYTHONS line to change.")
            return problems
        (root / INLINE_GATE).write_text(text, encoding="utf-8")
        result = subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name)], capture_output=True, text=True)
        lines = result.stderr.splitlines()
        if (result.returncode != 3 or result.stdout or len(lines) != 1
                or not lines[0].startswith(f"check-install-page: {INLINE_GATE} ")):
            problems.append(f"with {INLINE_GATE} refusing this version: exit {result.returncode}, expected 3 with no "
                            f"result line and 1 line from check-install-page naming {INLINE_GATE}: "
                            f"{(result.stdout + result.stderr).strip()[:300]}")
    return problems


def statement_problems() -> list[str]:
    """The gate's docstring names exactly the scripts that ALLOWED_SCRIPTS holds."""
    spec = importlib.util.spec_from_file_location("check_install_page", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    listed = re.search(r"``ALLOWED_SCRIPTS``: (.*?)\)", module.__doc__, re.S)
    names = tuple(re.findall(r"``([a-z]+\.js)``", listed.group(1))) if listed else ()
    if names != module.ALLOWED_SCRIPTS:
        return [f"the docstring lists ALLOWED_SCRIPTS as {names}; the code holds {module.ALLOWED_SCRIPTS}"]
    return []


def main() -> int:
    failures: list[str] = statement_problems()
    failures += [f"the stylesheets: {problem}"
                 for problem in hides_problems() + sheet_case_problems() + stylesheet_problems()]
    failures += [f"the Python version: {problem}" for problem in version_problems()]
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
            code, words = expected if isinstance(expected, tuple) else (expected, "")
            if result.returncode != code or words not in result.stdout + result.stderr:
                failures.append(f"{name}: exit {result.returncode}, expected {code}" + (f" and {words!r}" if words else "")
                                + f": {(result.stdout + result.stderr).strip()[:300]}")
    if failures:
        print("test-install-page: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-install-page: all {len(CASES)} cases, the {len(RESIDUALS)} named residuals, the docstring check of "
          "ALLOWED_SCRIPTS, the Python version checks and the stylesheet check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
