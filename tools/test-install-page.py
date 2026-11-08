#!/usr/bin/env python3
"""Tests for tools/check-install-page.py: the install pages' contract and the site-wide policy.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault to the install page, a family page,
site/_headers or site/_redirects, runs the gate there as a separate process
and asserts its exit code and, where a case gives them as (code, words), that
its output holds those words, so that a crash, which also exits 1, does not
pass for a refusal. 1 more check asserts that the gate's docstring names
exactly the scripts in ``ALLOWED_SCRIPTS``, and 1 that this file's own source
carries no ``?v=`` token starting with a digit apart from those KEPT_TOKENS
names, since a case writes the current baseline version as BASELINE, read
from ``.baseline/pin.toml``, and 1 that its syntax tree binds BASELINE only
there. Exit 0 when every case passes; 1 otherwise, naming each failing case.
Each of RESIDUALS is a fault the gate passes, such as markup in which a browser
may hide or empty what the gate checks; it must exit 0, and the gate's docstring
must name it, so that what the gate says it checks cannot outgrow its code
unnoticed.

It also fails unless the gate's CLASS_PIN (check 8) holds exactly the classes
that the 6 committed pages give each kind of checked element, each of its
ancestors and each element it holds, by tag, so that the class pin cannot be
widened unnoticed, and unless the gate's RULE_ATTRIBUTES (check 8) holds
exactly the attributes, ``hidden`` aside (HIDING_ATTRIBUTE), that the
attribute selectors of the rules rule_pins() holds name, read from each rule's
name with its strings blanked, so that the gate cannot drop one unnoticed,
and unless the gate's INSTALL_HEADERS (check 7) holds exactly the headers
and values that the committed site/_headers sets under each URL pattern that
the gate's reaches_page() reads as able to match an install page or a file
the pages load, so that the header pin cannot be widened unnoticed. It also
fails unless the gate's
ATTRIBUTE_PIN (check 8) holds exactly the attributes that the 6 committed
pages give each kind of checked element, each of its ancestors and each
element it holds, by tag, and unless the gate's HEAD_PIN (check 9) holds
exactly the meta, link and base elements that the 6 committed pages carry, by
the gate's head_key(), each with its attributes and their values, None only
where FREE_HEAD_VALUES below leaves a value free, so that neither pin can be
widened unnoticed. It also fails unless the gate's TAG_PIN (check 8) holds
exactly the tags that the 6 committed pages give each kind of checked
element, each of its ancestors and each element it holds; unless its
PAGE_ATTRIBUTES (check 8) holds exactly the attributes that they give an
element of each tag anywhere on them, and its PAGE_TAGS (check 8) exactly the
tags of their elements; unless its LOADED_SEGMENTS (checks
6 and 7) holds exactly the first path segments of every file they load (each
src, each href of a link other than the canonical link, and each url() of
the 3 stylesheets, read from the stylesheet's address), and its load_path()
reads each of those as 1 of the files that tools/check-baseline-pin.py pins
(check 6); and unless its parse() and name_text(), run in this process on
fragments apart from the pins, read a br, a </br> and a hidden br in a heading,
and its has_visible_text() text of only U+034F, as check 4 says; and unless
its P_PARENTS, IMPLIED_ENDS, TABLE_PARTS and SVG_SHAPES hold exactly what
this test states and its parse(), run in this process on fragments, reads no
misnested end tag where a fragment leaves out an end tag that its IMPLIED_ENDS
holds in a parent that counts as opened, and 1 where a browser may keep open an
element that the parser closes, where a table part sits outside the parents of
its TABLE_PARTS, where a table start tag ends the table around it, where a
self-closing tag in an svg is not 1 of SVG_SHAPES directly in it, or where the
parser keeps any element but an li directly in an li open around a sibling
(check 8). On a family
page the checks of CLASS_PIN, ATTRIBUTE_PIN and TAG_PIN read the checked
elements through the gate's family_checked(), as the gate holds them, so of
the links to #get and #test they read the required link back to each and,
for the pins of a link back, each other link that can become it once the
links before it are gone (paragraph_links(): shown, with visible text and no
class, and in no li, such as the ChatGPT page's link to #get in its
div.callout), and they must also pass with a further link back to #get in a
Gemini step, which the gate passes. And it fails unless
each of the 2 path lists of .github/workflows/install-page.yml covers every
file the gate, this test and that workflow read and each path of the gate's SERVER_ENTRIES
(check 10), as a file and at any depth under a directory, and holds no
negative pattern (1 that starts with !, which GitHub reads in order as
excluding what the patterns before it include; this check reads no order, so
it refuses every one) and no line that it cannot read (it reads only an item
written - "PATTERN" or - 'PATTERN', with no backslash or quote of that kind in
it and nothing after the closing quote but spaces and a comment, so any other
form fails, as does a list in any form it does not read as a list),
and unless that check refuses the workflow with
site/_redirects removed from 1 list or from both, with functions/** narrowed
to functions/* in 1 list or in both, or with !functions/** after
functions/** in 1 list or in both, double-quoted, single-quoted, escaped as
\\x21functions/** or followed by a comment, refuses those other forms, and
passes it with a blank line and a comment line after functions/** in both, or
with an item single-quoted or followed by a comment.

It also pins the stylesheets every install page loads (fonts.css,
palettes.css and baseline.css under site/assets/baseline/): it fails unless
the rules that rule_pins() holds are exactly those of RULE_PIN
(tools/install-page-rules.txt), in its order, naming each rule added, changed,
moved or removed. rule_pins() holds every rule whose selector can match an
element with a name and the classes of CLASS_PIN (any element may carry no
class), read by can_match() from the last compound selector of each selector
in its list, inside an at-rule or not: a type selector, or ``*``, and the class
selectors decide, and what it does not read by names and classes (a combinator
and what comes before it, an attribute selector, an id, a pseudo-class with or
without arguments, :has(), :is() and :not() among them, and a pseudo-element)
counts as matching, as does a namespace; a class name, a bracket or a comma
in a string counts for nothing. It also holds every keyframe and
@font-face rule, and every rule that sets a custom property that a rule it
holds names in var(), compared with regard to case, as CSS compares them, until
no more is added. Each rule is held verbatim, by the first 16 hexadecimal
digits of the sha256 of its text with the preludes of the at-rules around it,
beside its file name and preludes, which name it (pin_lines()), after
css_rules() normalizes only CSS whitespace and comments: each
run of CSS whitespace (space, tab, line feed, carriage return and form feed,
and no other character) outside a string reads as 1 space, a comment reads as
nothing where deleting it joins no 2 tokens (beside CSS whitespace, at either
end of a prelude or a declaration, or beside a parenthesis, a bracket, a
brace, a comma, a colon or a semicolon, but a ``(`` after a character of
names), and elsewhere as an empty comment, ``/**/``, so that the boundary it
keeps stays (``var/**/(--pad)``, which CSS reads as an invalid value, does not
read as ``var(--pad)``), and a string stays as written. So
``.fresh { --PAD: 9999px; padding: 0 var(--PAD); }`` passes here, and the
gate refuses ``<h1 class="fresh">``, while ``.btn { writing-mode:
vertical-rl; }`` fails here. It judges no value: what a pinned rule does is
what a reviewer accepted when it was pinned.

To update the pin after a deliberate change to the 3 stylesheets (a baseline
update re-pinned by tools/check-baseline-pin.py, say): read each rule this test
names and confirm that it hides, clips, zeroes the opacity of and moves no
checked element, then run
``python3 -I tools/test-install-page.py --print-rule-pin``, which prints the
pin of the rules rule_pins() holds, 1 per line, write its output to
tools/install-page-rules.txt, and review the diff of that file in the same pull
request. A new class on a checked element, an ancestor or an element it holds
needs CLASS_PIN of the gate and the committed pages changed together, which
widens the rule pin in turn.

The reader is deliberately small. It reads comments and strings as CSS does,
a backslash in a string escaping the character after it (a quote after an odd
run of backslashes ends no string), so a brace, a ``;``, a comma, a bracket or
a comment opener in a string, or a brace or a quote in a comment, delimits
nothing, and it fails when a stylesheet cannot be read, holds
no rule, or holds what it does not model: an unclosed comment, a comment
between 2 characters of names in a selector, where CSS reads no space
(``.a/**/b`` is not ``.a b``), or a run of adjacent comments there
(``.a/**//**/b``), a string that a line break, escaped or not, or its end leaves
open, a backslash outside a string, ``<!--`` or ``-->``, an unquoted ``url()``
holding a quote, a ``(``, a brace, a backslash or a line break, a brace inside
brackets or parentheses, unbalanced braces, brackets or parentheses, a rule
inside a rule, or an at-rule other than those of AT_RULES (``@container``, ``@font-face``,
``@keyframes``, ``@media`` and ``@supports``). Before it reads them, it fails
unless sheet_problems() reads each of SHEET_CASES as that case expects, and
unless stylesheet_problems(), which compares the committed stylesheets with
RULE_PIN, gives each of PIN_CASES, on a copy of the 3 stylesheets and RULE_PIN
with its fault, the problems that case expects: the copy as committed passes,
and a pinned rule changed, removed or moved, a rule the pin must hold added,
a comment between ``var`` and its ``(`` in a pinned rule (``.wrap``),
a pin entry with another digest, and 4 rules that the pin must hold only
because a string is read as CSS reads it (``h1[title="].fresh"]``,
``h1[title="\\"].fresh"]``, ``[title="\\\\"] .fresh, h1`` and a used custom
property set after ``content: "\\\\";``) each fail, naming the rule.

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
import difflib
import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-install-page.py"


def pinned_baseline() -> str:
    """The baseline version in .baseline/pin.toml, read by the load_pin() of tools/check-baseline-pin.py, the reader
    the gate uses."""
    spec = importlib.util.spec_from_file_location("check_baseline_pin", REPO_ROOT / "tools" / "check-baseline-pin.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    return reader.load_pin(REPO_ROOT)[0]


# The version that the pages' ?v= tokens carry. A case that writes the current version writes this one, so a move of
# the baseline needs no edit here; a pin that cannot be read fails this test with exit 1, rather than with a traceback.
try:
    BASELINE = pinned_baseline()
except Exception as error:
    print(f"test-install-page: failures:\n  - the baseline version could not be read from .baseline/pin.toml: {error!r}")
    raise SystemExit(1)
# The names that hold the version read from the pin. version_binding_problems() refuses any binding of them in this
# file's syntax tree but the one above, and any star import, whose names the tree does not show: any other binding can
# give a case or check that reads the name a value other than the version, or lead a reader to take it for the version.
VERSION_NAMES = ("BASELINE",)
# The ?v= tokens that start with a digit and that this file keeps as literals on purpose, each with its reason;
# version_literal_problems() refuses any other, so that no case carries a baseline version that goes stale at a move.
KEPT_TOKENS = {
    "?v=20260101-1": "the retired install script's own token, which its case refuses for the path, not the version",
    "?v=0123456789ab": "the stand-in content token of site.css, which is not a baseline version",
}
VERSION_LITERAL = re.compile(r"\?v=[0-9][^\"'\s<>]*")
PAGE = "site/install/index.html"
CLAUDE = "site/install/claude/index.html"
CHATGPT = "site/install/chatgpt/index.html"
GEMINI = "site/install/gemini/index.html"
COPILOT = "site/install/copilot/index.html"
OTHER = "site/install/other-ai/index.html"
HEADERS = "site/_headers"
REDIRECTS = "site/_redirects"
FILES = [PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER, HEADERS, REDIRECTS, "tools/check-headers.py",
         "tools/check-inline-code.py", "tools/check-baseline-pin.py", ".baseline/pin.toml"]
# The meta and link elements, by the gate's head_key(), whose attribute here the gate's HEAD_PIN leaves free (None):
# the page's own text, address and dates, which the gate treats as metadata only and which change with each page and
# release, and the address of a stylesheet, which check 6 holds to its exact form. Any other value is pinned.
FREE_HEAD_VALUES = {
    ("meta", "name", "description"): "content",
    ("link", "rel", "canonical"): "href",
    ("meta", "property", "og:title"): "content",
    ("meta", "property", "og:description"): "content",
    ("meta", "property", "og:url"): "content",
    ("meta", "property", "article:published_time"): "content",
    ("meta", "property", "article:modified_time"): "content",
    ("meta", "name", "twitter:title"): "content",
    ("meta", "name", "twitter:description"): "content",
    ("link", "rel", "stylesheet"): "href",
}
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
SELECT = f"/assets/baseline/select.js?v={BASELINE}"
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
# The gate's messages for a class outside its CLASS_PIN, an attribute of its RULE_ATTRIBUTES, a later html or body
# start tag with attributes, and a stylesheet other than the 3 the rule pin reads.
PINNED = "which the committed pages do not give"
RULE_NAMED = "which a pinned stylesheet rule names"
LATER_TAG = "a later html or body start tag carries attributes"
OTHER_SHEET = "the only stylesheets that the rule pin reads"
# The gate's messages for an html or body start tag with attributes that is not an ancestor of every checked element,
# a page without the doctype, a Link header in site/_headers, and a header outside INSTALL_HEADERS under a URL pattern
# that can match an install page; and the opening lines that the generator writes.
NOT_ANCESTOR = "an html or body start tag that is not an ancestor of every checked element carries attributes"
NO_DOCTYPE = "the page does not begin with <!doctype html>"
LINK_SET = "sets a Link header"
INSTALL_HEADER = "which can match an install page"
# The gate's messages for an attribute outside its ATTRIBUTE_PIN, a meta, link or base element outside its HEAD_PIN,
# and a rule of site/_redirects whose source can match an install page or a file the pages load.
GIVEN = "which the committed pages do not give"
HEAD_PINNED = "(HEAD_PIN)"
REDIRECT = "which can match an install page or a file the install pages load; a rule there can send the reader away"
# The gate's messages for a tag outside its TAG_PIN, an attribute outside its PAGE_ATTRIBUTES, a src outside its
# LOADED_SEGMENTS and 1 of its SERVER_ENTRIES that exists.
TAG_GIVEN = "a tag that the committed pages do not give an element there (TAG_PIN)"
NONE_GIVEN = "which the committed pages give no"
OUTSIDE_LOADS = "(LOADED_SEGMENTS)"
SERVER_ENTRY = "exists; Cloudflare Pages runs it, or reads it"
PIN_UNREAD = "check-install-page: tools/check-baseline-pin.py could not read the baseline pin"
# The gate's words for a load outside the baseline pin, an element of a tag that the committed pages do not use, a
# family link whose label is not its family's name, and a switch that is not exactly the template's.
OUTSIDE_PIN = "which is not 1 of the files tools/check-baseline-pin.py pins"
PAGE_TAG = "a tag that the committed pages do not use (PAGE_TAGS)"
WRONG_LABEL = "the claude family link's visible label is not \"Claude\""
SWITCH = "the page carries the light and dark switch 0 times"
MISNESTED = "open inside it; a browser can keep that element open, reopen it or ignore the end tag"
# The words of a Gemini step, which a case extends with a link; the step stays found when it holds 1 already.
GEMINI_STEP = "<strong>New Gem</strong>"
VERIFIED = '<p class="verified">'
MODIFIED = '<meta property="article:modified_time" content="'
REFRESH = '<meta http-equiv="refresh" content="0; url=/">'
DOCTYPE = "<!doctype html>\n"
HTML = '<html lang="en" class="site-cleanlanguage">\n'
# The scheme.js tag of template specification 7.33, with the pinned baseline version, as the committed pages carry it.
SCHEME = f'<script data-cfasync="false" src="/assets/baseline/scheme.js?v={BASELINE}"></script>'
COPY = f'<script src="/assets/baseline/copy.js?v={BASELINE}" defer></script>'
FONTS = f'<link rel="stylesheet" href="/assets/baseline/fonts.css?v={BASELINE}">'
LATER = f'<link rel="stylesheet" href="/assets/baseline/baseline.css?v={BASELINE}">'
STYLESHEETS = ["site/assets/baseline/fonts.css", "site/assets/baseline/palettes.css", "site/assets/baseline/baseline.css"]
# The rule pin: each rule of STYLESHEETS that rule_pins() keeps, as a digest of its text and its name (pin_lines()),
# 1 per line, in the order the stylesheets give them. Update it only as the docstring says.
PIN_FILE = "tools/install-page-rules.txt"
RULE_PIN = REPO_ROOT / PIN_FILE
# The workflow that runs this test and the gate, and the files it reads besides those of the gate and this test; each of
# its 2 path lists must cover all of them (workflow_path_problems).
WORKFLOW = ".github/workflows/install-page.yml"
WORKFLOW_ALSO = ("tools/check-python-version.py", ".python-version", WORKFLOW)
# A url() of a stylesheet, quoted or not, for the files that STYLESHEETS load (loaded_segment_problems).
CSS_URL = re.compile(r"""url\(\s*["']?([^"')\s]+)""", re.I)
PRINT_PIN = "--print-rule-pin"
# CSS whitespace: space, tab, line feed, carriage return and form feed. str.split() and str.strip() also take U+00A0
# and other spaces, which CSS reads as part of a name or a value (.fresh U+00A0 name is 1 class), so the reader
# normalizes with these alone.
CSS_SPACE = " \t\n\r\f"
CSS_WHITESPACE = re.compile(r"[ \t\n\r\f]+")
# A character of a CSS name, number or unit. Without a comment between 2 of them they read as 1 token, so css_rules()
# refuses such a comment in a selector, where CSS reads the selector as invalid (.a/**/b is neither .ab nor .a b), and
# a run of adjacent comments there too (.a/**//**/b).
NAME_CHAR = re.compile(r"[\w\u0080-\U0010ffff-]")
# The characters CSS always reads as a token of their own. A comment beside 1 of them separates no 2 tokens that its
# deletion would join, so css_rules() reads it as nothing, unless a "(" follows a character of names, which CSS reads
# with that name as 1 function (var( is not var/**/( ). Between any other 2 characters other than CSS whitespace it
# reads as an empty comment, /**/, which keeps the boundary: deleted, it could join 2 tokens, and as a space it could
# add 1 (calc(1px/**/-/**/2px) is not calc(1px - 2px)).
OWN_TOKENS = "()[]{},:;"
# A custom property that a var() names, compared with regard to case, as CSS compares them (--PAD is not --pad).
VAR_NAME = re.compile(r"var\([ \t\n\r\f]*(--[\w\u0080-\U0010ffff-]+)")
# The class selectors of a compound selector, and the type selector or * that starts it, once what sits in its
# brackets and parentheses is dropped (can_match); an id, a pseudo-class or a pseudo-element constrains nothing here.
CLASS_NAME = re.compile(r"\.([\w\u0080-\U0010ffff-]+)")
TYPE_NAME = re.compile(r"[\w\u0080-\U0010ffff-]+|\*")
# The at-rules css_rules() reads through: those the stylesheets use, which only say when the rules inside them apply
# or hold no rule for an element. Any other (@import, which loads rules it never sees, or @scope, whose :scope and
# bare declarations apply to an element its prelude names, say) makes the stylesheet unreadable.
AT_RULES = ("container", "font-face", "keyframes", "media", "supports")
URL_START = re.compile(r"url\(\s*", re.I)
# A string as css_rules() reads it: a backslash escapes the character after it, so a quote after an odd run of
# backslashes ends no string ("\\" holds 1 backslash, and ends at its second quote).
STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", re.S)
# The attribute that an attribute selector names, with or without a namespace, once its strings are blanked; HTML
# reads attribute names in a selector without regard to case.
ATTRIBUTE_NAME = re.compile(r"\[[ \t\n\r\f]*(?:(?:[\w\u0080-\U0010ffff-]+|\*)?\|)?([\w\u0080-\U0010ffff-]+)")
# The attribute the pinned rules name that the gate's RULE_ATTRIBUTES leaves out, because the gate reads it as hiding.
HIDING_ATTRIBUTE = "hidden"
# Stylesheets for sheet_problems() with CASE_CLASSES and the pin of CASE_RULES in place of the gate's CLASS_PIN and
# RULE_PIN: an h1 that may carry the class x, and a pin of the 3 rules of CASE_SHEET (the second and third set the custom property
# the first uses, and 1 it uses). Each case gives the words that 1 of its problems holds, or "" for none; a brace in a
# string or a comment opens or closes no block as CSS reads it, so only a misreading makes a pinned rule appear there.
CASE_CLASSES = {"h1": {"x"}}
CASE_SHEET = 'h1 { margin: 0 var(--pad); font-family: "a  b", serif; } .y { --pad: var(--q); } .z { --q: 1rem; }'
CASE_RULES = (("the case: h1", 'the case: h1 { margin: 0 var(--pad); font-family: "a  b", serif; }'),
              ("the case: .y", "the case: .y { --pad: var(--q); }"), ("the case: .z", "the case: .z { --q: 1rem; }"))
ADDED = "which the pin does not hold there"
GONE = "no longer give the pinned rule"
SHEET_CASES = (
    ("the pinned rules as pinned", CASE_SHEET, ""),
    ("the pinned rules with only whitespace and comments changed", '/* note */ h1  {\n  margin: 0\tvar(--pad); /* } */\n'
        '  font-family: "a  b",\n serif;\n}\n.y{--pad: var(--q);}/* a { b } c */.z { --q: 1rem; }', ""),
    ("a comment in place of a space in a pinned rule", CASE_SHEET.replace("--q: 1rem", "--q:/**/1rem"), GONE),
    # Deleted, a comment between a name and "(" would join them into 1 function, which CSS does not.
    ("a comment between a function's name and its ( in a pinned rule",
        CASE_SHEET.replace("var(--pad)", "var/**/(--pad)"), GONE),
    ("2 adjacent comments between a function's name and its ( in a pinned rule",
        CASE_SHEET.replace("var(--pad)", "var/**//**/(--pad)"), GONE),
    ("a comment after a function's ( in a pinned rule", CASE_SHEET.replace("var(--pad)", "var(/**/--pad)"), ""),
    # A rule whose subject, the last compound selector, can match an h1 that carries only x, or any element that
    # carries no class, is pinned, read conservatively where the selector says more than names and classes.
    ("a rule for an unpinned class", CASE_SHEET + " .fresh { display: none; }", ""),
    ("a rule for a pinned class", CASE_SHEET + " .x { display: none; }", ADDED),
    ("a rule for a pinned element name in upper case", CASE_SHEET + " H1.x { display: none; }", ADDED),
    ("a pinned class in another case", CASE_SHEET + " .X { display: none; }", ""),
    ("a compound selector of pinned names", CASE_SHEET + " h1.x { position: absolute; top: -9999px; }", ADDED),
    ("a compound selector with an unpinned class", CASE_SHEET + " h1.x.fresh { display: none; }", ""),
    ("a descendant selector ending in a pinned name", CASE_SHEET + " .fresh h1 { display: none; }", ADDED),
    ("a child selector without spaces", CASE_SHEET + " .fresh>.x { display: none; }", ADDED),
    ("a sibling selector ending in an unpinned class", CASE_SHEET + " h1 ~ .fresh { display: none; }", ""),
    ("a pseudo-element of a pinned class", CASE_SHEET + ' .x::before { content: "a"; }', ADDED),
    ("a pseudo-class of a pinned name", CASE_SHEET + " h1:hover { opacity: 0; }", ADDED),
    ("a selector of only :has()", CASE_SHEET + " :has(.fresh) { display: none; }", ADDED),
    ("a selector of only an attribute selector", CASE_SHEET + " [class~=fresh] { display: none; }", ADDED),
    ("an id selector", CASE_SHEET + " #main-content { display: none; }", ADDED),
    ("the universal selector", CASE_SHEET + " * { opacity: 0; }", ADDED),
    ("an unpinned class only in :is()", CASE_SHEET + " :is(.fresh) { display: none; }", ADDED),
    ("an element of another name", CASE_SHEET + " section { display: none; }", ADDED),
    ("another element name with a class", CASE_SHEET + " section.x { display: none; }", ""),
    ("a namespace", CASE_SHEET + " svg|section.x { display: none; }", ADDED),
    ("a selector list with a pinned class first", CASE_SHEET + " .x, .fresh { display: none; }", ADDED),
    ("a comma inside :is()", CASE_SHEET + " :is(.fresh, .y) .fresh { display: none; }", ""),
    ("a pinned class in @media", CASE_SHEET + " @media print { .x { display: none; } }", "@media print { .x {"),
    ("a pinned class in @media in @supports",
        CASE_SHEET + " @supports (display: grid) { @media print { .x { display: none; } } }",
        "@supports (display: grid) { @media print { .x {"),
    # A comment keeps 2 names apart; in a selector, where CSS reads it as no space, it is refused.
    ("@media and a comment with no space", CASE_SHEET + " @media/**/screen { .fresh { margin: 0; } }", ""),
    ("@media and a comment with no space, around a pinned class", CASE_SHEET + " @media/**/screen { .x { margin: 0; } }",
        "@media/**/screen { .x {"),
    ("a comment inside a compound selector", CASE_SHEET + " h1/**/.fresh { display: none; }", ""),
    ("a comment between 2 names in a selector", CASE_SHEET + " .fresh/**/h1 { display: none; }", "a comment between"),
    # The character before a comment is read past the empty comments that adjacent comments left.
    ("2 adjacent comments between 2 names in a selector", CASE_SHEET + " .fresh/**//**/h1 { display: none; }",
        "a comment between"),
    ("3 adjacent comments between 2 names in a selector", CASE_SHEET + " .fresh/**//**//**/h1 { display: none; }",
        "a comment between"),
    ("a comment between 2 names in a value", CASE_SHEET + " .fresh { margin: 0/**/auto; }", ""),
    ("a comment between 2 numbers in an @font-face", CASE_SHEET + " @font-face { font-weight: 100/**/900; }", ADDED),
    ("a custom property name in a string", CASE_SHEET + ' .fresh { content: "a; --pad: 1px"; }', ""),
    # A pinned rule changed, moved or removed, and a custom property a pinned rule uses, or 1 that uses, set elsewhere.
    ("a pinned rule changed", CASE_SHEET.replace("serif; }", "serif; display: none; }"), GONE),
    ("a string in a pinned rule respaced", CASE_SHEET.replace('"a  b"', '"a b"'), GONE),
    ("a string in a pinned rule in other quotes", CASE_SHEET.replace('"a  b"', "'a  b'"), GONE),
    ("a pinned rule respaced", CASE_SHEET.replace("margin: 0", "margin:0"), GONE),
    ("a pinned rule removed", CASE_SHEET.replace(".z { --q: 1rem; }", ""), GONE),
    ("pinned rules swapped", CASE_SHEET.replace(" .y { --pad: var(--q); } .z { --q: 1rem; }", "")
        .replace("h1", ".z { --q: 1rem; } .y { --pad: var(--q); } h1", 1), GONE),
    ("a used custom property set in an unpinned rule", CASE_SHEET + " .fresh { --pad: 9999px; }", ADDED),
    ("a custom property that a used 1 uses set in an unpinned rule", CASE_SHEET + " .fresh { --q: 9999px; }", ADDED),
    ("a custom property of another case", CASE_SHEET + " .fresh { --PAD: 9999px; padding: 0 var(--PAD); }", ""),
    ("keyframes", CASE_SHEET + " @keyframes k { to { opacity: 0; } }", ADDED),
    ("an @font-face that shrinks its glyphs", CASE_SHEET + ' @font-face { font-family: "a"; size-adjust: 1%; }', ADDED),
    # Comments and strings delimit nothing.
    ("a rule for a pinned name in a string", CASE_SHEET + ' .fresh { content: "} h1 { display: none; }"; }', ""),
    ("a rule for a pinned name between comment openers in strings",
        CASE_SHEET + ' .fresh { content: "/*"; } .x { display: none; } .fresh { content: "*/"; }', ADDED),
    ("a quote and a rule in a comment", "/* it's } h1 { display: none; } */ " + CASE_SHEET, ""),
    ("brackets in an unquoted url(), as CSS allows", CASE_SHEET + " .fresh { background: url(a[b]); }", ""),
    # Forms the reader does not model are refused.
    ("a string that an escaped line break continues", CASE_SHEET + ' .fresh { content: "a\\\n}"; }', "a line break ends"),
    ("a rule after a string ended by a line break", '.y { content: "a\n} h1 { display: none; } .z { content: "b"; }',
        "a line break ends"),
    ("an unclosed string", '.x { content: "a; }', "its end leaves open"),
    ("an escaped brace in a selector", ".y\\{ { color: red; } h1 { display: none; }", "a backslash outside"),
    ("an escaped class name", ".\\78 { display: none; }", "a backslash outside"),
    ("a brace in brackets", ".x { a: ( } { ); display: none; }", "a brace inside brackets"),
    ("a brace in an attribute selector", '.x[title="a"], [a=b}] { display: none; }', "a brace inside brackets"),
    ("a } in an unquoted url()", ".x { background: url(a}b); display: none; }", "an unquoted url()"),
    ("a quote in an unquoted url()", '.x { background: URL(a"b); display: none; } .y { content: ""; }',
        "an unquoted url()"),
    ("a ( in an unquoted url()", ".x { background: url(a(b); }", "an unquoted url()"),
    ("a line break in an unquoted url()", ".x { background: url(a\nb); }", "an unquoted url()"),
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


def create(relative: str, text: str):
    """Write a new file, and any directory it needs, that the copy does not hold."""
    def apply(root: Path) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise AssertionError(f"{relative} already exists")
        path.write_text(text, encoding="utf-8")
    return apply


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


def span_of(root: Path, relative: str, start: str, end: str) -> str:
    """The text of a page from the first start to the first end after it, end included, so that a case finds an
    element without the date or the words it holds now (a release restamps the modified date)."""
    text = (root / relative).read_text(encoding="utf-8")
    at = text.index(start)
    return text[at:text.index(end, at + len(start)) + len(end)]


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


def repin(name: str):
    """Change the first digit of the digest of the entry of PIN_FILE that names the rule name, so the entry no longer
    matches that rule."""
    def apply(root: Path) -> None:
        path = root / PIN_FILE
        lines = path.read_text(encoding="utf-8").split("\n")
        at = [line.partition(" ")[2] for line in lines].index(name)
        lines[at] = ("1" if lines[at].startswith("0") else "0") + lines[at][1:]
        path.write_text("\n".join(lines), encoding="utf-8")
    return apply


# The ChatGPT page's link to #test in its prose, its required link back to #test; dropped, its a.start is its only
# link to #test.
PROSE_TEST = '<a href="/install/#test">Test it</a>'
ONLY_START = edit(CHATGPT, PROSE_TEST, "Test it")
# A further link back to #get in a Gemini step, which the gate passes, held by the pins of a step; the inventories of
# the pins pass with it too (inventory_case_problems).
STEP_LINK = edit(GEMINI, GEMINI_STEP, GEMINI_STEP + ', from <a href="/install/#get">Get Clean Language</a>')
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
    ("a family page heading whose 1 class joins x and vh by a no-break space", edit(CLAUDE, "<h1>", '<h1 class="x\u00a0vh">'),
        (1, "the <h1> carries the class 'x\\xa0vh'")),
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
    # The pin reads the body's elements before main, not what header.mast holds, so a hidden span in its nav passes.
    ("a vh span in the nav", edit(PAGE, '<nav class="nav" aria-label="Site">',
        '<nav class="nav" aria-label="Site"><span class="vh">Site</span>'), 0),
    # The committed pages give no h2 a class (PAGE_ATTRIBUTES), so a vh heading fails wherever it sits.
    ("a vh heading in the nav", edit(PAGE, '<nav class="nav" aria-label="Site">',
        '<nav class="nav" aria-label="Site"><h2 class="vh">Site</h2>'), (1, "a h2 carries the attribute 'class', " + NONE_GIVEN)),
    # baseline.css declares only padding-top for the class first (.lbl.first), 0.9rem at top level and 0 inside its
    # @media (max-width: 1000px) rules, so a label without it is correct.
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
    # a dir on the row or an ancestor can show the buttons in another order, and a browser may reopen a formatting
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
    # A browser may add the attributes of a later html or body start tag to the page's own element.
    ("a later body start tag with a dir attribute", edit(PAGE, "</main>", '</main><body dir="rtl">'), (1, PAGE_DIR)),
    # The class pin reads the page's own html and body; a browser may add a later tag's attributes to them, so a later
    # html or body start tag may carry none.
    ("a later body start tag with a class", edit(PAGE, "</main>", '</main><body class="fresh">'), (1, LATER_TAG)),
    ("a later html start tag with a class on a family page", edit(CLAUDE, "</main>", '</main><html class="fresh">'),
        (1, LATER_TAG)),
    ("a later body start tag with no attribute", edit(PAGE, "</main>", "</main><body>"), 0),
    # Nor may an html or body start tag that is not an ancestor of every checked element, as the parser holds it open,
    # carry any, the first of each included: on a page whose opening body is gone, a browser may open the body itself.
    ("a family page whose opening body is gone, with a later body start tag with data-preset",
        both(edit(CHATGPT, "<body>\n", ""), edit(CHATGPT, "</main>", "</main><body data-preset>")), (1, NOT_ANCESTOR)),
    ("a family page whose opening body is gone, with a later body start tag with a class",
        both(edit(CHATGPT, "<body>\n", ""), edit(CHATGPT, "</main>", '</main><body class="fresh">')), (1, NOT_ANCESTOR)),
    ("a family page whose opening body is gone, with a later body start tag with no attribute",
        both(edit(CHATGPT, "<body>\n", ""), edit(CHATGPT, "</main>", "</main><body>")), 0),
    # With its opening html start tag gone, a page's head is not html > head, which check 6 refuses, and a later html
    # start tag with an attribute is not an ancestor of every checked element, which check 8 refuses.
    ("the install page whose opening html is gone, with a later html start tag with a class",
        both(edit(PAGE, HTML, ""), edit(PAGE, "</main>", '</main><html class="fresh">')), (1, NOT_ANCESTOR)),
    ("a family page whose opening html is gone, with a later html start tag with a class",
        both(edit(GEMINI, HTML, ""), edit(GEMINI, "</main>", '</main><html class="fresh">')), (1, NOT_ANCESTOR)),
    # Without the doctype a browser may match class names without regard to case; the class pin and the rule pin do not.
    ("the install page without its doctype", edit(PAGE, DOCTYPE, ""), (1, NO_DOCTYPE)),
    ("a family page without its doctype", edit(CHATGPT, DOCTYPE, ""), (1, NO_DOCTYPE)),
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
    # A browser may move into the body, above its first element, what sits between the head and the body, and what
    # follows a start tag a head may not hold; the pin reads only the body's elements, so these are refused apart.
    ("a paragraph between the head and the body", edit(PAGE, "</head>\n<body>", "</head>\n<p>Note.</p>\n<body>"),
        (1, "sit outside the head and the body, or in the head")),
    ("bare text between the head and the body", edit(PAGE, "</head>\n<body>", "</head>\nNote.\n<body>"),
        (1, "text other than whitespace sits outside the head and the body")),
    ("a paragraph at the end of the head", edit(PAGE, "</head>", "<p>Note.</p>\n</head>"),
        (1, "sit outside the head and the body, or in the head")),
    ("a hidden heading at the end of the head", edit(PAGE, "</head>", '<h2 class="vh">Install</h2>\n</head>'),
        (1, "sit outside the head and the body, or in the head")),
    ("bare text at the end of the head", edit(PAGE, "</head>", "Note.\n</head>"),
        (1, "text other than whitespace sits outside the head and the body")),
    ("a paragraph before the html start tag", edit(PAGE, "<html ", "<p>Note.</p>\n<html "),
        (1, "sit outside the head and the body, or in the head")),
    ("bare text before the html start tag", edit(PAGE, "<html ", "Note.\n<html "),
        (1, "text other than whitespace sits outside the head and the body")),
    ("a blank line between the pick label and the button row", edit(PAGE, PICK, PICK + "\n \n"), 0),
    ("bare text right after the button row", edit(PAGE, ROW_END, ROW_END + "Note."), 0),
    # A browser may add the attributes of a later html or body start tag to the page's own element, so the gate reads
    # a hiding one as hiding the h1 and the label whose text the parser has already read as visible.
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
    # A browser may render the content of each only as fallback or in a control, so it hides here.
    *[(f"a family link whose only label is in {tag}",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", f"><{tag}>Claude</{tag}><")), 1)
        for tag in ("audio", "canvas", "meter", "object", "progress", "select", "video")],
    # Check 5 refuses each of these, whose text a browser might not render.
    ("a family link whose only label is in a style element",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><style>Claude</style><")), 1),
    ("a family link whose only label is in an SVG desc",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><svg><desc>Claude</desc></svg><")), 1),
    # The committed pages put no element inside a family link (TAG_PIN).
    ("a family link whose label is in a span", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><span>Claude</span><")),
        (1, "a span inside a family link is a span, " + TAG_GIVEN)),
    ("a family link with a label and a hidden span",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", '>Claude<span class="vh"> setup</span><')), (1, PINNED)),
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
    # A browser with scripting on may render no markup inside noscript, so neither an id nor a link there counts.
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
    # Text in a list inside a step counts for that step too, unless it is hidden; but the committed pages put no list
    # inside a step (TAG_PIN), and a step list inside a step carries a class that they do not give an ol there
    # (CLASS_PIN).
    ("a family page step whose only text is in a nested list", lambda root: edit(OTHER, steps_of(root, OTHER),
        STEPS + "<li><ol><li>Save the file.</li></ol></li></ol>")(root), (1, "an ol inside a step is an ol, " + TAG_GIVEN)),
    ("a family page step whose only text is hidden in a nested list", lambda root: edit(OTHER, steps_of(root, OTHER),
        STEPS + "<li><ol><li><span hidden>Save the file.</span></li></ol></li></ol>")(root), 1),
    ("a family page step list nested in a step", lambda root: edit(OTHER, steps_of(root, OTHER),
        STEPS + "<li>" + STEPS + "<li>Save the file.</li></ol></li></ol>")(root),
        (1, "an ol inside a step list carries the class 'steps'")),
    # Each checked element, each of its ancestors and each element it holds carries only the classes the committed
    # pages give it there (the gate's CLASS_PIN), so no stylesheet rule outside the rule pin can reach it.
    ("the hero's h1 with a class", edit(PAGE, HERO, HERO.replace("<h1>", '<h1 class="fresh">')),
        (1, "the hero's h1 carries the class 'fresh'")),
    ("the pick label with a further class", edit(PAGE, PICK, PICK.replace("lbl blk", "lbl blk fresh")),
        (1, "the \"pick\" label carries the class 'fresh'")),
    ("the button row with a class", edit(PAGE, ROW, ROW.replace("<p>", '<p class="fresh">')),
        (1, "the paragraph of family links carries the class 'fresh'")),
    ("a family link with a further class", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace("btn inline", "btn inline fresh")),
        (1, "a family link carries the class 'fresh'")),
    ("div.doc with a further class", edit(PAGE, '<div class="doc">', '<div class="doc fresh">'),
        (1, "a div around the hero's h1 carries the class 'fresh'")),
    ("a family link whose label is in a span with a class",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", '><span class="fresh">Claude</span><')),
        (1, "a span inside a family link carries the class 'fresh'")),
    ("a family page heading with a class", edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1 class="fresh">ChatGPT</h1>'),
        (1, "the <h1> carries the class 'fresh'")),
    ("a family page heading in a section with a class",
        wrap(CHATGPT, "<h1>", "</h1>", '<section class="fresh">', "</section>"),
        (1, "a section around the <h1> carries the class 'fresh'")),
    ("a family page heading naming its family in a span with a class",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1><span class="fresh">ChatGPT</span></h1>'),
        (1, "a span inside the <h1> carries the class 'fresh'")),
    ("a family page verified line with a further class", edit(GEMINI, '<p class="verified">', '<p class="verified fresh">'),
        (1, "a verified line carries the class 'fresh'")),
    ("a family page step list with a further class", edit(CLAUDE, STEPS, '<ol class="steps fresh">'),
        (1, "a step list carries the class 'fresh'")),
    ("a family page step with a class", edit(OTHER, STEPS + "<li>", STEPS + '<li class="fresh">'),
        (1, "a step carries the class 'fresh'")),
    # The pins hold, for each target, the required link back, which on each committed page is a link with no class in
    # a paragraph, so each of these changes the ChatGPT page's link to #test in its prose; a change to its a.start, a
    # further link, passes, and its a.start alone, with the class start, fails the pins of a link back.
    ("a family page link back with a class", edit(CHATGPT, PROSE_TEST, PROSE_TEST.replace("<a ", '<a class="fresh" ')),
        (1, "a link back carries the class 'fresh'")),
    ("a family page further link back with a further class",
        edit(CHATGPT, '<a class="start" href="/install/#test">', '<a class="start fresh" href="/install/#test">'), 0),
    ("a family page whose only link back to #test is its a.start", ONLY_START,
        (1, "a link back carries the class 'start'")),
    ("a family page link back holding a span", edit(CHATGPT, PROSE_TEST, PROSE_TEST.replace(">Test it<", "><span>Test it</span><")),
        (1, "a span inside a link back is a span, " + TAG_GIVEN)),
    # The committed pages also put a link with no class in a paragraph in a div.callout, which the pins of a link back
    # allow: with the ChatGPT page's link to #get in its prose gone, the 1 in its callout is its required link back.
    ("a family page whose link back to #get sits in a callout",
        edit(CHATGPT, '<a href="/install/#get">Get Clean Language</a>.</p>', "Get Clean Language.</p>"), 0),
    # Nor may any of them carry an attribute that a pinned rule names (the gate's RULE_ATTRIBUTES): the print rules of
    # baseline.css set display: none for [data-preset] and [data-col-toggles].
    ("a family page heading with data-preset", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1 data-preset>ChatGPT</h1>"),
        (1, "the <h1> carries the attribute 'data-preset', " + RULE_NAMED)),
    ("div.doc with data-col-toggles", edit(PAGE, '<div class="doc">', '<div class="doc" data-col-toggles>'),
        (1, "a div around the hero's h1 carries the attribute 'data-col-toggles', " + RULE_NAMED)),
    ("a family link whose label is in a span with data-preset",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", '><span data-preset="x">Claude</span><')),
        (1, "a span inside a family link carries the attribute 'data-preset', " + RULE_NAMED)),
    # Nor any other attribute that the committed pages do not give that element there (the gate's ATTRIBUTE_PIN): a
    # presentation attribute can colour, size or move it with no stylesheet change, whatever element carries it.
    ("a family page heading with an attribute no pinned rule names",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1 data-note="x">ChatGPT</h1>'),
        (1, "the <h1> carries the attribute 'data-note', " + GIVEN)),
    ("a family page heading in a font with the light background colour",
        wrap(CHATGPT, "<h1>", "</h1>", '<font color="#f6f4e7">', "</font>"),
        (1, "a font around the <h1> carries the attribute 'color', " + GIVEN)),
    # Nor any tag that the committed pages do not give an element there (the gate's TAG_PIN), with or without a class
    # or an attribute: a font or a marquee around a family page's h1, and a div or a bdi in a family link.
    ("a family page heading in a font with no attribute", wrap(CHATGPT, "<h1>", "</h1>", "<font>", "</font>"),
        (1, "a font around the <h1> is a font, " + TAG_GIVEN)),
    ("a family page heading in a marquee", wrap(CHATGPT, "<h1>", "</h1>", "<marquee>", "</marquee>"),
        (1, "a marquee around the <h1> is a marquee, " + TAG_GIVEN)),
    ("a div inside a family link", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><div>Claude</div><")),
        (1, "a div inside a family link is a div, " + TAG_GIVEN)),
    ("a family link label in a bdi", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><bdi>Claude</bdi><")),
        (1, "a bdi inside a family link is a bdi, " + TAG_GIVEN)),
    ("a step list holding a span, as committed", lambda root: edit(OTHER, steps_of(root, OTHER),
        STEPS + "<li><span>Save the file.</span></li></ol>")(root), 0),
    # Nor, on any element of the 6 pages, checked or not, an attribute that the committed pages give no element of
    # its tag (the gate's PAGE_ATTRIBUTES): a presentation attribute can size a box that moves a checked element.
    ("the rail's img with a height", edit(PAGE, '<div class="rail"><img ', '<div class="rail"><img height="3000" '),
        (1, "an img carries the attribute 'height', " + NONE_GIVEN)),
    ("a dir attribute on the label after the button row", edit(PAGE, SCOPE, SCOPE.replace('">', '" dir="rtl">')),
        (1, "a p carries the attribute 'dir', " + NONE_GIVEN)),
    ("a family page with a dir attribute on a label after its heading", edit(CHATGPT,
        '<p class="lbl accent blk">Team', '<p class="lbl accent blk" dir="rtl">Team'),
        (1, "a p carries the attribute 'dir', " + NONE_GIVEN)),
    ("a family page step list after <span hidden><div></span>", edit(OTHER, STEPS, "<span hidden><div></span>" + STEPS),
        (1, "a span carries the attribute 'hidden', " + NONE_GIVEN)),
    ("a family page step list after <p><div hidden></p>", edit(OTHER, STEPS, "<p><div hidden></p>" + STEPS),
        (1, "a div carries the attribute 'hidden', " + NONE_GIVEN)),
    ("an unknown element with an attribute below the steps", edit(OTHER, "</main>", '<x-note data-x="1"></x-note></main>'),
        (1, "a x-note carries the attribute 'data-x', " + NONE_GIVEN)),
    ("a nav link with a target, as committed pages give an a", edit(PAGE, '<a href="/standard/"', '<a target="_self" href="/standard/"'), 0),
    ("the body with bgcolor around a family page heading", edit(GEMINI, "<body>", '<body bgcolor="#f6f4e7">'),
        (1, "a body around the <h1> carries the attribute 'bgcolor', " + GIVEN)),
    ("div.doc with bgcolor around the hero's h1", edit(PAGE, '<div class="doc">', '<div class="doc" bgcolor="#000">'),
        (1, "a div around the hero's h1 carries the attribute 'bgcolor', " + GIVEN)),
    ("the pick label with align", edit(PAGE, PICK, PICK.replace('id="pick"', 'id="pick" align="right"')),
        (1, "the \"pick\" label carries the attribute 'align', " + GIVEN)),
    ("a family link with a title", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace('id="claude"', 'id="claude" title="x"')),
        (1, "a family link carries the attribute 'title', " + GIVEN)),
    ("a family page step list in a table with a width",
        wrap(COPILOT, STEPS, "</ol>", '<table width="1"><tr><td>', "</td></tr></table>"),
        (1, "a table around a step list carries the attribute 'width', " + GIVEN)),
    ("a family page link back with a target", edit(CHATGPT, PROSE_TEST, PROSE_TEST.replace("<a ", '<a target="_x" ')),
        (1, "a link back carries the attribute 'target', " + GIVEN)),
    ("a family page step with a link to the downloads with an id",
        edit(OTHER, '<a href="/instructions/">instructions page', '<a href="/instructions/" id="fresh">instructions page'),
        (1, "an a inside a step carries the attribute 'id', " + GIVEN)),
    # A hidden step, and a dir on a verified line, which a browser can show in another order, each fail as an attribute
    # that the committed pages do not give that element.
    ("a family page with 1 setup step hidden", edit(OTHER, STEPS + "<li>", STEPS + "<li hidden>"),
        (1, "a step carries the attribute 'hidden', " + GIVEN)),
    ("a family page with a dir attribute on its verified line",
        edit(CHATGPT, '<p class="verified">', '<p class="verified" dir="ltr">'),
        (1, "a verified line carries the attribute 'dir', " + GIVEN)),
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
    ("a family page heading whose classes only contain vh", edit(CLAUDE, "<h1>", '<h1 class="vhx pre-vh">'), (1, PINNED)),
    ("a family page heading with the class only-dark", edit(CLAUDE, "<h1>", '<h1 class="only-dark">'), 1),
    ("a family page heading with the class skip", edit(GEMINI, "<h1>", '<h1 class="skip">'), 1),
    ("a family page heading whose classes only contain only-dark or skip", edit(CHATGPT, "<h1>", '<h1 class="only-darker skip-link">'),
        (1, PINNED)),
    ("a family page heading emptied", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>​</h1>"), 1),
    ("a family page heading naming another family", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Gemini</h1>"), 1),
    ("a family page heading naming its family only in a vh span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1>Setup<span class="vh"> ChatGPT</span></h1>'), 1),
    ("the Claude and ChatGPT family pages swapped", swap(CLAUDE, CHATGPT), 1),
    # The committed pages put no element inside a family page's h1 (TAG_PIN), so a span or a br there fails.
    ("a family page heading naming its family in a span", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1><span>ChatGPT</span></h1>"),
        (1, "a span inside the <h1> is a span, " + TAG_GIVEN)),
    # The name is compared without regard to case, with U+0000 and ZERO_WIDTH but U+00A0 deleted, and each run of
    # whitespace, U+00A0 included, and each br that no element hides read as a space.
    ("a family page heading naming its family in another case",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI Systems</h1>"), 0),
    ("a family page heading naming its family with a soft hyphen", edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Chat&shy;GPT</h1>"), 0),
    ("a family page heading naming its family across a br",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI<br>systems</h1>"), (1, "a br inside the <h1> is a br, " + TAG_GIVEN)),
    ("a family page heading naming its family across a no-break space",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI\u00a0systems</h1>"), 0),
    ("a family page heading naming its family with U+034F inside it",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Chat\u034fGPT</h1>"), 1),
    ("a family page heading joining its family's name across a hidden br",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI<br hidden>systems</h1>"), 1),
    # The gate reads </br> as <br>, as a browser may.
    ("a family page heading naming its family across </br>",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI</br>systems</h1>"), (1, "a br inside the <h1> is a br, " + TAG_GIVEN)),
    ("a family page heading joining its family's name across </br> in a hidden span",
        edit(OTHER, "<h1>Other AI systems</h1>", "<h1>Other AI<span hidden></br></span>systems</h1>"), 1),
    # A bidi control can show the name's letters in another order: Chat, U+202E, GPT and U+202C may show "ChatTPG".
    ("a family page heading whose name a right-to-left override reorders",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>Chat&#x202E;GPT&#x202C;</h1>"), (1, "holds a bidi control")),
    *[(f"a family page heading naming its family beside U+{code:04X}",
        edit(CHATGPT, "<h1>ChatGPT</h1>", f"<h1>ChatGPT{chr(code)}</h1>"), (1, "holds a bidi control"))
        for code in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))],
    ("a family page heading naming its family beside a bidi control in a hidden span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1>ChatGPT<span hidden>" + chr(0x202E) + "</span></h1>"),
        (1, "a span inside the <h1> carries the attribute 'hidden', " + GIVEN)),
    # A bdo or a dir attribute can reorder the letters too: <bdo dir="rtl">GPT</bdo> may show "TPG".
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
    ("the button row with data-popover", edit(PAGE, ROW, '<p data-popover><a class="btn inline" id="claude"'),
        (1, "the paragraph of family links carries the attribute 'data-popover', " + GIVEN)),
    # The pin refuses a dialog around the whole row, so the label of 1 link sits in it.
    ("a family link whose label is in an open dialog",
        edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", "><dialog open>Claude</dialog><")),
        (1, "a dialog inside a family link carries the attribute 'open', " + GIVEN)),
    ("a family page heading with popover", edit(CLAUDE, "<h1>", '<h1 popover="manual">'), 1),
    ("a family page heading inside a dialog without open", wrap(CHATGPT, "<h1>", "</h1>", "<dialog>", "</dialog>"), 1),
    ("a family page heading inside a closed details", wrap(GEMINI, "<h1>", "</h1>", "<details>", "</details>"), 1),
    ("a family page heading inside a datalist", wrap(COPILOT, "<h1>", "</h1>", "<datalist>", "</datalist>"), 1),
    ("a family page heading inside a noscript", wrap(OTHER, "<h1>", "</h1>", "<noscript>", "</noscript>"), 1),
    ("a family page heading inside an rp", wrap(CLAUDE, "<h1>", "</h1>", "<rp>", "</rp>"), 1),
    ("a family page heading inside a title", wrap(CHATGPT, "<h1>", "</h1>", "<title>", "</title>"), 1),
    # The committed pages put no details or summary around a family page's h1 (TAG_PIN).
    ("a family page heading in the summary of a closed details",
        wrap(GEMINI, "<h1>", "</h1>", "<details><summary>", "</summary><p>More</p></details>"),
        (1, "a summary around the <h1> is a summary, " + TAG_GIVEN)),
    ("a family page heading after the summary of a closed details",
        wrap(COPILOT, "<h1>", "</h1>", "<details><summary>More</summary>", "</details>"), 1),
    ("a family page heading inside an open dialog", wrap(OTHER, "<h1>", "</h1>", '<dialog open="">', "</dialog>"),
        (1, "a dialog around the <h1> carries the attribute 'open', " + GIVEN)),
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
        wrap(OTHER, STEPS, "</ol>", "<details open><summary>Steps</summary>", "</details>"),
        (1, "a details around a step list carries the attribute 'open', " + GIVEN)),
    ("a family page step list with data-popover", edit(OTHER, STEPS, '<ol class="steps" data-popover="auto">'),
        (1, "a step list carries the attribute 'data-popover', " + GIVEN)),
    # The gate ignores "/>" on an element that is not void, as a browser may, but for an svg and a shape (SVG_SHAPES)
    # directly in an svg, so each of these stays open and hides what follows.
    ("the button row after <div hidden/>", edit(PAGE, ROW, "<div hidden/>" + ROW), 1),
    ('the button row after <div class="vh"/>', edit(PAGE, ROW, '<div class="vh"/>' + ROW), 1),
    ("the button row after <details/>", edit(PAGE, ROW, "<details/>" + ROW), 1),
    # The button row holds only the family links and the whitespace between them, so any other element or text in
    # it fails, a br included; a family page case below keeps a void <img/> from holding what follows, and another
    # refuses a <br/>, a tag that the committed pages do not use (PAGE_TAGS).
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
    ("a family page step list after <br/>", edit(CLAUDE, STEPS, "<br/>" + STEPS), (1, "the page holds a br, " + PAGE_TAG)),
    ('a family page step list after <img alt=""/>', edit(CLAUDE, STEPS, '<img alt=""/>' + STEPS), 0),
    ("a family page heading whose only text is in a hidden span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", "<h1><span hidden>ChatGPT</span></h1>"), 1),
    ("a family page heading whose only text is a structured-data script",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1><script type="application/ld+json">"ChatGPT"</script></h1>'), 1),
    ("a family page heading whose only text is a MathML annotation", edit(CHATGPT, "<h1>ChatGPT</h1>",
        "<h1><math><semantics><mi></mi><annotation>ChatGPT</annotation></semantics></math></h1>"), 1),
    ("a family page heading with visible text and a hidden span",
        edit(CHATGPT, "<h1>ChatGPT</h1>", '<h1>ChatGPT<span class="vh"> setup</span></h1>'), (1, PINNED)),
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
    # The pins hold only the required link back for each target, so a further link to #get in a step passes, held by
    # the step's pins; a page whose only links to #get sit in steps has no link that passes the pins of a link back.
    ("a family page step that links back to #get", STEP_LINK, 0),
    ("a family page whose only link to #get sits in a step", both(
        edit(GEMINI, '<a href="/install/#get">Get Clean Language</a>', "Get Clean Language"),
        edit(GEMINI, GEMINI_STEP, GEMINI_STEP + ', from <a href="/install/#get">Get it</a>')),
        (1, "no link to /install/#get that reads as shown, with visible text, passes the pins of a link back")),
    ("a family page step that links back to #get with a class", edit(GEMINI, GEMINI_STEP,
        GEMINI_STEP + ', from <a class="start" href="/install/#get">Get Clean Language</a>'),
        (1, "an a inside a step carries the class 'start', " + PINNED)),
    ("a family page whose links back to #get are labelled only U+034F", edit(GEMINI,
        '<a href="/install/#get">Get Clean Language</a>', '<a href="/install/#get">' + chr(0x034F) + "</a>", every=True),
        (1, "every link to /install/#get reads as hidden or has no text that reads as visible")),
    # Each family link's visible label is its family's name in the gate's FAMILY_NAMES.
    ("a family link with another family's label", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">ChatGPT<")),
        (1, WRONG_LABEL)),
    ("a family link with its name and another family's", edit(PAGE, CLAUDE_LINK,
        CLAUDE_LINK.replace(">Claude<", ">Claude or ChatGPT<")), (1, WRONG_LABEL)),
    ("a family link labelled in another case, across a no-break space",
        edit(PAGE, OTHER_LINK, OTHER_LINK.replace(">Other AI systems<", ">Other AI\u00a0Systems<")), 0),
    ("a family link labelled only with U+034F", edit(PAGE, CLAUDE_LINK, CLAUDE_LINK.replace(">Claude<", ">" + chr(0x034F) + "<")),
        (1, "the claude family link has no text that reads as visible")),
    *[(f"a family page step of only U+{code:04X}",
        lambda root, code=code: edit(OTHER, steps_of(root, OTHER), STEPS + f"<li>{chr(code)}</li></ol>")(root),
        (1, "a step list has no step (li) with text that reads as visible"))
        for code in (0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x17B4, 0x180B, 0x180E, 0x2061, 0x2064, 0x206A, 0xFE0F,
                     0xE01EF, 0x1BCA0, 0x1D173, 0xE0041, 0x2065, 0xFFF0, 0xE0FFF, 0x2800)],
    ("a family page with an empty verified line", edit(GEMINI, '<p class="verified">', '<p class="verified"></p><p>'),
        (1, "a verified line has no text that reads as visible")),
    ("a family page with a verified line of only U+034F", lambda root: edit(GEMINI, span_of(root, GEMINI, VERIFIED, "</p>"),
        VERIFIED + chr(0x034F) + "</p>")(root), (1, "a verified line has no text that reads as visible")),
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
    # The gate does not count a script inside noscript as a load: a browser with scripting on may read it as text,
    # and one with scripting off runs no script.
    ("copy.js loaded only inside a body noscript",
        both(edit(PAGE, COPY + "\n", ""), edit(PAGE, "<body>\n", "<body>\n<noscript>" + COPY + "</noscript>\n")), 1),
    ("copy.js loaded only inside a noscript on a family page",
        both(edit(OTHER, COPY + "\n", ""), edit(OTHER, "</main>", "</main><noscript>" + COPY + "</noscript>")), 1),
    ("select.js loaded", edit(PAGE, "</head>", f'<script src="/assets/baseline/select.js?v={BASELINE}" defer></script>\n</head>'), 1),
    ("select.js loaded on a family page", edit(CLAUDE, "</head>", f'<script src="/assets/baseline/select.js?v={BASELINE}" defer></script>\n</head>'), 1),
    ("a baseline script without its version token", edit(PAGE, "</head>", '<script src="/assets/baseline/rail.js" defer></script>\n</head>'), 1),
    ("a baseline script without defer", edit(PAGE, "</head>", f'<script src="/assets/baseline/rail.js?v={BASELINE}"></script>\n</head>'), 1),
    ("a script from outside the baseline", edit(PAGE, "</head>", f'<script src="/assets/other.js?v={BASELINE}" defer></script>\n</head>'), 1),
    ("the retired install script", edit(PAGE, "</head>", '<script src="/js/install.js?v=20260101-1" defer></script>\n</head>'), 1),
    ("a baseline script under the old draft path", edit(PAGE, "</head>", f'<script src="/draft/assets/baseline/rail.js?v={BASELINE}" defer></script>\n</head>'), 1),
    ("select.js in an upper-case tag", edit(PAGE, "</head>", f'<SCRIPT SRC="{SELECT}" defer></SCRIPT>\n</head>'), 1),
    ("select.js with a space before the =", edit(PAGE, "</head>", f'<script src ="{SELECT}" defer></script>\n</head>'), 1),
    ("select.js after a > in a quoted value", edit(PAGE, "</head>", f'<script title=">" src="{SELECT}" defer></script>\n</head>'), 1),
    ("rail.js without defer in an upper-case tag", edit(PAGE, "</head>", f'<SCRIPT SRC="/assets/baseline/rail.js?v={BASELINE}"></SCRIPT>\n</head>'), 1),
    ("rail.js with its token and defer", edit(PAGE, "</head>", f'<script src="/assets/baseline/rail.js?v={BASELINE}" defer></script>\n</head>'), 0),
    ("the scheme.js tag missing", edit(PAGE, SCHEME + "\n", ""), 1),
    ("the scheme.js tag with defer", edit(PAGE, SCHEME, SCHEME.replace('"></script>', '" defer></script>')), 1),
    ("the scheme.js tag with async", edit(PAGE, SCHEME, SCHEME.replace('"></script>', '" async></script>')), 1),
    ("the scheme.js tag with src before data-cfasync", edit(PAGE, SCHEME,
        f'<script src="/assets/baseline/scheme.js?v={BASELINE}" data-cfasync="false"></script>'), 1),
    ("the scheme.js tag after the first stylesheet", both(edit(PAGE, SCHEME + "\n", ""),
        edit(PAGE, "</head>", SCHEME + "\n</head>")), 1),
    ("the scheme.js tag twice", edit(PAGE, SCHEME, SCHEME + SCHEME), 1),
    ("a second scheme.js with defer", edit(PAGE, "</head>",
        f'<script src="/assets/baseline/scheme.js?v={BASELINE}" defer></script>\n</head>'), 1),
    ("a second scheme.js in upper case with a character reference", edit(PAGE, "</head>",
        f'<SCRIPT SRC="/assets/baseline/sch&#101;me.js?v={BASELINE}" defer></SCRIPT>\n</head>'), 1),
    ("a second scheme.js with spaces around =", edit(PAGE, "</head>",
        f'<script src = "/assets/baseline/scheme.js?v={BASELINE}" defer></script>\n</head>'), 1),
    ("an upper-case stylesheet before the scheme.js tag", edit(PAGE, SCHEME,
        f'<LINK REL="stylesheet" HREF="/assets/baseline/fonts.css?v={BASELINE}">\n' + SCHEME), 1),
    ("a stylesheet before the scheme.js tag as the first of 2 rel attributes", edit(PAGE, SCHEME,
        f'<LINK REL="stylesheet" REL="icon" HREF="/assets/baseline/fonts.css?v={BASELINE}">\n' + SCHEME), 1),
    ("the scheme.js tag and the stylesheets moved into the body, in order", into_body(SCHEME), 1),
    ("the stylesheets moved into the body, after the scheme.js tag", into_body(FONTS), 1),
    ("the scheme.js tag and the stylesheets in a second head inside the body", into_body(SCHEME, "<head>\n", "</head>\n"), 1),
    ("a later stylesheet moved into the body, after the first", into_body(LATER), 1),
    ("a later stylesheet in upper case at the end of the body", edit(PAGE, "</body>",
        f'<LINK REL="stylesheet" HREF="/assets/baseline/baseline.css?v={BASELINE}">\n</body>'), 1),
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
        f'<script src="/assets/baseline/rail.js?v={BASELINE}" type="module" defer></script>\n</head>'), 1),
    # The load and switch checks hold on the family pages too.
    ("the scheme.js tag missing on a family page", edit(GEMINI, SCHEME + "\n", ""), 1),
    ("the scheme.js tag after the first stylesheet on a family page", both(edit(COPILOT, SCHEME + "\n", ""),
        edit(COPILOT, "</head>", SCHEME + "\n</head>")), 1),
    ("a later stylesheet at the end of the body on a family page", both(edit(OTHER, LATER + "\n", ""),
        edit(OTHER, "</body>", LATER + "\n</body>")), 1),
    ("a second element with data-scheme-toggle on a family page", edit(CHATGPT, "</main>",
        '<p><button class="scheme" type="button" data-scheme-toggle hidden><span class="vh">Dark mode</span></button></p></main>'), 1),
    # The rule pin reads only the 3 baseline stylesheets, so no other loads, site.css with its content token included.
    ("site.css without its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?w=1">\n</head>'), 1),
    ("site.css with its content token", edit(PAGE, "</head>", '<link rel="stylesheet" href="/assets/site.css?v=0123456789ab">\n</head>'),
        (1, OTHER_SHEET)),
    ("another baseline stylesheet on a family page", edit(GEMINI, "</head>",
        f'<link rel="stylesheet" href="/assets/baseline/print.css?v={BASELINE}">\n</head>'), (1, OTHER_SHEET)),
    ("a baseline stylesheet with a media attribute", edit(PAGE, LATER, LATER.replace('">', '" media="all">')),
        (1, OTHER_SHEET)),
    # As for scripts, the text match also finds a tag that the parser reads as a comment or as text.
    ("another stylesheet only inside a comment", edit(PAGE, "</head>",
        '<!--<link rel="stylesheet" href="/assets/site.css?v=0123456789ab">-->\n</head>'), (1, OTHER_SHEET)),
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
    # A Link header can load a stylesheet that the rule pin does not read; the gate reads no value, so it refuses all.
    ("a Link header that loads a stylesheet",
        append(HEADERS, "\n/install/*\n  Link: </assets/site.css>; rel=stylesheet\n"), (1, LINK_SET)),
    ("a lower-case link header that only preloads a stylesheet, on every page",
        edit(HEADERS, SITE_LINE, SITE_LINE + "\n  link: </assets/baseline/fonts.css>; rel=preload; as=style"),
        (1, LINK_SET)),
    # Under a URL pattern that can match an install page, /* included, only the headers and values of INSTALL_HEADERS
    # may appear, and no detach; the gate reads a pattern from its text alone and fails closed (reaches_install).
    ("a Refresh header that sends the reader away from the install pages",
        append(HEADERS, "\n/install/*\n  Refresh: 0; url=/\n"), (1, INSTALL_HEADER)),
    ("a Link header under a family page", append(HEADERS, "\n/install/claude/\n  Link: </>; rel=preload\n"),
        (1, INSTALL_HEADER)),
    ("a Content-Disposition header under /INSTALL/*",
        append(HEADERS, '\n/INSTALL/*\n  Content-Disposition: attachment; filename="install.html"\n'), (1, INSTALL_HEADER)),
    ("a Refresh header on every page", edit(HEADERS, SITE_LINE, SITE_LINE + "\n  Refresh: 0; url=/"), (1, INSTALL_HEADER)),
    ("a Refresh header under a placeholder", append(HEADERS, "\n/:page/*\n  Refresh: 0; url=/\n"), (1, INSTALL_HEADER)),
    ("a Refresh header under /./install/*", append(HEADERS, "\n/./install/*\n  Refresh: 0; url=/\n"),
        (1, INSTALL_HEADER)),
    ("a Refresh header under a full URL", append(HEADERS, "\nhttps://cleanlanguage.ai/install/*\n  Refresh: 0; url=/\n"),
        (1, INSTALL_HEADER)),
    ("X-Frame-Options with another value on every page",
        edit(HEADERS, SITE_LINE, "/*\n  X-Frame-Options: SAMEORIGIN"), (1, INSTALL_HEADER)),
    ("a second /* rule detaching a header", append(HEADERS, "\n/*\n  ! Cross-Origin-Opener-Policy\n"),
        (1, INSTALL_HEADER)),
    ("a Refresh header on the sitemap only", edit(HEADERS, "/sitemap.xml\n", "/sitemap.xml\n  Refresh: 0; url=/\n"), 0),
    ("a Refresh header on a download only, under a full URL",
        append(HEADERS, "\nhttps://cleanlanguage.ai/downloads/cleanlanguage.md\n  Refresh: 0; url=/\n"), 0),
    # No rule of site/_redirects may have a source that can match an install page, read as reaches_install reads a
    # pattern of site/_headers: a redirect sends the reader away, and a rewrite (200) serves other content there.
    ("a redirect from every install page to the home page", append(REDIRECTS, "/install/* / 302\n"),
        (1, "site/_redirects line 11 has the source /install/*, " + REDIRECT)),
    ("a rewrite of a family page to the home page", append(REDIRECTS, "/install/claude/ / 200\n"), (1, REDIRECT)),
    ("a redirect under a placeholder", append(REDIRECTS, "/:page/* / 301\n"), (1, REDIRECT)),
    ("a redirect from /INSTALL to the home page, indented", append(REDIRECTS, "  /INSTALL / 302\n"), (1, REDIRECT)),
    ("a redirect from every page", edit(REDIRECTS, "/claude/download ", "/* / 302\n/claude/download "), (1, REDIRECT)),
    ("a redirect between 2 downloads", append(REDIRECTS, "/downloads/old.md /downloads/cleanlanguage.md 301\n"), 0),
    ("a redirect from the install pages only in a comment", append(REDIRECTS, "# /install/* / 302\n"), 0),
    ("the redirects file missing", remove(REDIRECTS), 3),
    ("the baseline pin missing", remove(".baseline/pin.toml"), (3, PIN_UNREAD)),
    ("the baseline pin malformed", edit(".baseline/pin.toml", 'version = "', 'version = "x'), (3, PIN_UNREAD)),
    # Nor may a source, or a pattern of site/_headers, match a file the install pages load: each sits under a first
    # segment of LOADED_SEGMENTS (assets), in any letter case.
    ("a rewrite of baseline.css to fonts.css",
        append(REDIRECTS, "/assets/baseline/baseline.css /assets/baseline/fonts.css 200\n"),
        (1, "site/_redirects line 11 has the source /assets/baseline/baseline.css, " + REDIRECT)),
    ("a redirect of copy.js to rail.js", append(REDIRECTS, "/assets/baseline/copy.js /assets/baseline/rail.js 302\n"),
        (1, REDIRECT)),
    ("a redirect of every asset, in capitals", append(REDIRECTS, "/ASSETS/* / 302\n"), (1, REDIRECT)),
    ("a redirect of the rail's img under a full URL",
        append(REDIRECTS, "https://cleanlanguage.ai/assets/baseline/logos/cleanlanguage.svg /x.svg 302\n"),
        (1, REDIRECT)),
    ("a redirect of an image the install pages do not load",
        append(REDIRECTS, "/images/old.png /images/cleanlanguage-card.png 301\n"), 0),
    ("a Content-Type header on the stylesheets",
        append(HEADERS, "\n/assets/baseline/*.css\n  Content-Type: text/plain\n"), (1, INSTALL_HEADER)),
    # Every src on the 6 pages is a path under LOADED_SEGMENTS, so check 7 covers what it loads.
    ("the rail's img loaded from another first segment",
        edit(PAGE, 'src="/assets/baseline/logos/cleanlanguage.svg" alt="A document',
             'src="/images/cleanlanguage-card.png" alt="A document'), (1, OUTSIDE_LOADS)),
    ("a family page script loaded by a relative path", edit(CLAUDE, 'src="/assets/baseline/copy.js', 'src="assets/baseline/copy.js'),
        (1, OUTSIDE_LOADS)),
    # No server entry point that Cloudflare Pages runs may exist (SERVER_ENTRIES).
    ("a Pages Function that redirects",
        create("functions/_middleware.js", 'export const onRequest = () => Response.redirect("https://example.com/", 302);\n'),
        (1, "functions " + SERVER_ENTRY)),
    ("a Worker in the output directory", create("site/_worker.js", "export default { fetch: () => new Response('') };\n"),
        (1, "site/_worker.js " + SERVER_ENTRY)),
    ("a Worker directory in the output directory", create("site/_worker.js/index.js", "export default {};\n"),
        (1, "site/_worker.js " + SERVER_ENTRY)),
    ("a Wrangler configuration in TOML", create("wrangler.toml", 'name = "x"\npages_build_output_dir = "./other"\n'),
        (1, "wrangler.toml " + SERVER_ENTRY)),
    ("a Wrangler configuration in JSON", create("wrangler.json", '{"pages_build_output_dir": "./other"}\n'),
        (1, "wrangler.json " + SERVER_ENTRY)),
    ("a Wrangler configuration in JSONC", create("wrangler.jsonc", '// x\n{"pages_build_output_dir": "./other"}\n'),
        (1, "wrangler.jsonc " + SERVER_ENTRY)),
    ("a root package.json with an install script", create("package.json", '{"scripts": {"install": "touch site/x"}}\n'),
        (1, "package.json " + SERVER_ENTRY)),
    ("a root runtime.txt", create("runtime.txt", "python-3.13.3\n"), (1, "runtime.txt " + SERVER_ENTRY)),
    ("a root requirements.txt", create("requirements.txt", "x==1.0\n"), (1, "requirements.txt " + SERVER_ENTRY)),
    ("a root Pipfile", create("Pipfile", '[packages]\nx = "*"\n'), (1, "Pipfile " + SERVER_ENTRY)),
    ("a root Gemfile", create("Gemfile", 'source "https://rubygems.org"\n'), (1, "Gemfile " + SERVER_ENTRY)),
    # No end tag may close an element other than the innermost: a browser may keep the span open after the first, and
    # the div after the second, so each can hide the step list after it.
    ("a family page step list after <span class=\"vh\"><div></span>",
        edit(OTHER, STEPS, '<span class="vh"><div></span>' + STEPS), (1, "</span> closes <span> with <div> " + MISNESTED)),
    ("a family page step list after <p><div class=\"vh\"></p>", edit(OTHER, STEPS, '<p><div class="vh"></p>' + STEPS),
        (1, "</p> closes <p> with <div> " + MISNESTED)),
    # A browser may close <svg/> at once, so the div after it is not in an svg, and keep the span open past </span>.
    ("a family page step list after <span class=\"vh\"><svg/><div/></span>",
        edit(OTHER, STEPS, '<span class="vh"><svg/><div/></span>' + STEPS),
        (1, "</span> closes <span> with <div> " + MISNESTED)),
    # The HTML standard lets a page omit the end tag of a td where no more content follows in its tr, and a browser
    # may close the cell at </tr>, so a valid one-cell table without </td> passes (IMPLIED_ENDS).
    ("a family page with a one-cell table without </td>", edit(CHATGPT, "</main>", "<table><tr><td>Cell</tr></table></main>"),
        0),
    # The same omissions in each table part in its right parent pass (TABLE_PARTS).
    ("a family page with a table of p elements left open in each part", edit(CHATGPT, "</main>",
        "<table><caption><p>x</caption><thead><tr><th><p>y</tr></thead><tbody><tr><td><p>z</tr></tbody></table></main>"), 0),
    # A browser may ignore the start tag of a table part outside a table, so it may open each p in the span and ignore
    # </span> with the p open, and the step list after it can sit in the hiding span (TABLE_PARTS).
    ("a family page step list after <span class=\"vh\"><td><p>x</td></span>",
        edit(OTHER, STEPS, '<span class="vh"><td><p>x</td></span>' + STEPS), (1, "</td> closes <td> with <p> " + MISNESTED)),
    ("a family page step list after <span class=\"vh\"><th><p>x</th></span>",
        edit(OTHER, STEPS, '<span class="vh"><th><p>x</th></span>' + STEPS), (1, "</th> closes <th> with <p> " + MISNESTED)),
    ("a family page step list after <span class=\"vh\"><caption><p>x</caption></span>",
        edit(OTHER, STEPS, '<span class="vh"><caption><p>x</caption></span>' + STEPS),
        (1, "</caption> closes <caption> with <p> " + MISNESTED)),
    ("a family page step list after <span class=\"vh\"><tr><td><p>x</tr></span>",
        edit(OTHER, STEPS, '<span class="vh"><tr><td><p>x</tr></span>' + STEPS), (1, "</tr> closes <tr> with <td> " + MISNESTED)),
    ("a family page step list after <span class=\"vh\"><thead><tr><td><p>x</thead></span>",
        edit(OTHER, STEPS, '<span class="vh"><thead><tr><td><p>x</thead></span>' + STEPS),
        (1, "</thead> closes <thead> with <tr> " + MISNESTED)),
    # A browser may read a table start tag in a table, outside a cell or a caption, as that table's end, so the later
    # cell can be ignored and the p in it can keep the hiding span open past </span>, as above. In a row, the gate
    # refuses that cell only by its rule for a table start tag in a table. The second case puts the cell in a div in
    # the table, after such a start tag: a td whose parent is a div never counts as opened (TABLE_PARTS), so the gate
    # refuses it with or without that start tag.
    ("a family page step list after a table start tag in a table row, in a hiding span",
        edit(OTHER, STEPS, '<span class="vh"><table><tr><table></table><td><p>x</td></tr></table></span>' + STEPS),
        (1, "</td> closes <td> with <p> " + MISNESTED)),
    ("a family page step list after a cell in a div in a table, in a hiding span",
        edit(OTHER, STEPS, '<span class="vh"><table><div><table></table><td><p>x</td></table></span>' + STEPS),
        (1, "</td> closes <td> with <p> " + MISNESTED)),
    # A browser may close the first li at the second's start tag, so a list that omits the first's end tag passes, while
    # around a span it may keep the span open past </span>, and in a step list the tag pin allows no li in a step.
    ("a family page with <ul><li>a<li>b</ul>", edit(CHATGPT, "</main>", "<ul><li>a<li>b</ul></main>"), 0),
    ("a family page step list after <span class=\"vh\"><li>a<li>b</span>",
        edit(OTHER, STEPS, '<span class="vh"><li>a<li>b</span>' + STEPS), (1, "</span> closes <span> with <li> " + MISNESTED)),
    ("a family page step list that omits a step's </li>", edit(OTHER, STEPS, '<ol class="steps"><li>a<li>b</ol>' + STEPS),
        (1, TAG_GIVEN)),
    # A browser may move a div or a p out of an svg and keep it open, though its tag closes itself, so it may keep the
    # span open past </span>. Check 5 refuses that svg too; these show check 8's own refusal.
    ("a family page step list after <span class=\"vh\"><svg><div/></svg></span>",
        edit(OTHER, STEPS, '<span class="vh"><svg><div/></svg></span>' + STEPS), (1, "</svg> closes <svg> with <div> " + MISNESTED)),
    ("a family page step list after <span class=\"vh\"><svg><p/></svg></span>",
        edit(OTHER, STEPS, '<span class="vh"><svg><p/></svg></span>' + STEPS), (1, "</svg> closes <svg> with <p> " + MISNESTED)),
    # Every src, and every href of a link other than the canonical link, on the 6 pages is 1 of the files
    # tools/check-baseline-pin.py pins, read as a path from the site's root with no . or .. segment.
    ("a family page illustration outside the baseline pin", edit(CHATGPT, '<p class="verified">',
        '<img src="/assets/install-illustration.svg" alt=""><p class="verified">'),
        (1, "an img loads '/assets/install-illustration.svg', " + OUTSIDE_PIN)),
    ("the rail's img loaded through a .. segment",
        edit(PAGE, 'src="/assets/baseline/logos/cleanlanguage.svg" alt="A document',
             'src="/assets/../images/cleanlanguage-card.png" alt="A document'), (1, OUTSIDE_PIN)),
    ("the rail's img loaded through a . segment",
        edit(PAGE, 'src="/assets/baseline/logos/cleanlanguage.svg" alt="A document',
             'src="/assets/./baseline/logos/cleanlanguage.svg" alt="A document'), (1, OUTSIDE_PIN)),
    ("the rail's img loaded through an encoded .. segment",
        edit(PAGE, 'src="/assets/baseline/logos/cleanlanguage.svg" alt="A document',
             'src="/assets/%2e%2e/images/cleanlanguage-card.png" alt="A document'), (1, OUTSIDE_PIN)),
    ("a family page script loaded from a file outside the baseline pin",
        edit(CLAUDE, 'src="/assets/baseline/copy.js?v=', 'src="/assets/baseline/copy2.js?v='), (1, OUTSIDE_PIN)),
    ("the rail's img loaded from another pinned file",
        edit(PAGE, 'src="/assets/baseline/logos/cleanlanguage.svg" alt="A document',
             'src="/assets/baseline/logos/cleanlanguage-mono.svg" alt="A document'), 0),
    # Every element on the 6 pages, checked or not, shown or hidden, is of a tag that the committed pages use (the gate's
    # PAGE_TAGS).
    ("a marquee around the label after the button row", wrap(PAGE, SCOPE, SCOPE, "<marquee>", "</marquee>"),
        (1, "the page holds a marquee, " + PAGE_TAG)),
    ("a bdi in the label after the button row", edit(PAGE, SCOPE, SCOPE.replace(">Scope<", "><bdi>Scope</bdi><")),
        (1, "the page holds a bdi, " + PAGE_TAG)),
    ("a bdo without dir in the label after the button row",
        edit(PAGE, SCOPE, SCOPE.replace(">Scope<", "><bdo>Scope</bdo><")), (1, "the page holds a bdo, " + PAGE_TAG)),
    ("a family page with a section below its steps", edit(OTHER, "</main>", "<section></section></main>"),
        (1, "the page holds a section, " + PAGE_TAG)),
    # Check 5 allows only the 2 svg elements of the exact light and dark switch, so a larger width on 1 fails.
    ("the switch's moon svg with a larger width",
        edit(PAGE, '<svg class="moon" viewBox="0 0 24 24" width="24"', '<svg class="moon" viewBox="0 0 24 24" width="3000"'),
        (1, SWITCH)),
    # Every meta, link and base element on the 6 pages, at any depth, shown or hidden, and every such start tag that a
    # text match finds, is 1 that the committed pages carry, with its attributes and values (the gate's HEAD_PIN).
    ("a meta refresh before a family page heading", edit(CHATGPT, "<h1>ChatGPT</h1>", REFRESH + "<h1>ChatGPT</h1>"),
        (1, "site/install/chatgpt/index.html: " + REFRESH + " is not 1 of the meta, link and base elements")),
    ("a meta refresh in the head of the install page", edit(PAGE, "</head>", REFRESH + "\n</head>"), (1, HEAD_PINNED)),
    ("a meta refresh in a noscript", edit(CLAUDE, "</head>", "<noscript>" + REFRESH + "</noscript>\n</head>"),
        (1, HEAD_PINNED)),
    ("a meta refresh only in a comment", edit(COPILOT, "</head>", "<!--" + REFRESH + "-->\n</head>"), (1, HEAD_PINNED)),
    ("a meta refresh in capitals", edit(OTHER, "</head>", '<META HTTP-EQUIV="Refresh" CONTENT="0; URL=/">\n</head>'),
        (1, HEAD_PINNED)),
    ("a meta charset that also carries http-equiv refresh", edit(GEMINI, '<meta charset="utf-8">',
        '<meta charset="utf-8" http-equiv="refresh" content="0; url=/">'), (1, HEAD_PINNED)),
    # The text match stops at the quoted ">", so only the parsed element shows this meta's http-equiv.
    ("a meta refresh behind a quoted greater-than sign", edit(CLAUDE, '<meta charset="utf-8">',
        '<meta charset="utf-8" title=">" http-equiv="refresh" content="0; url=/">'), (1, HEAD_PINNED)),
    ("a meta http-equiv default-style on a family page", edit(GEMINI, "</head>",
        '<meta http-equiv="default-style" content="print">\n</head>'), (1, HEAD_PINNED)),
    ("a meta http-equiv content-security-policy on the install page", edit(PAGE, "</head>",
        '<meta http-equiv="content-security-policy" content="style-src \'none\'">\n</head>'), (1, HEAD_PINNED)),
    ("a base on a family page", edit(CLAUDE, "</head>", '<base href="/">\n</head>'),
        (1, '<base href="/"> is not 1 of the meta, link and base elements')),
    ("a viewport with another value", edit(COPILOT, "width=device-width, initial-scale=1", "width=4000"),
        (1, HEAD_PINNED)),
    ("a meta charset with another value", edit(OTHER, '<meta charset="utf-8">', '<meta charset="windows-1252">'),
        (1, HEAD_PINNED)),
    ("a meta color-scheme on the install page", edit(PAGE, "</head>", '<meta name="color-scheme" content="dark">\n</head>'),
        (1, HEAD_PINNED)),
    ("a link that preloads the home page", edit(CHATGPT, "</head>", '<link rel="prerender" href="/">\n</head>'),
        (1, HEAD_PINNED)),
    ("an icon with a further attribute", edit(PAGE, 'type="image/svg+xml">', 'type="image/svg+xml" sizes="any">'),
        (1, HEAD_PINNED)),
    ("a family page with another description and modified date", both(
        edit(GEMINI, '<meta name="description" content="', '<meta name="description" content="New. '),
        lambda root: edit(GEMINI, span_of(root, GEMINI, MODIFIED, '">'), MODIFIED + '2000-01-01">')(root)), 0),
]
# Faults the gate passes, and the words of the gate's docstring that name each (compared with runs of whitespace
# read as 1 space).
RESIDUALS = [
    ("a family page with 1 setup step dropped",
        edit(OTHER, STEPS + '<li><span>Save the file, or copy everything from the <a href="/instructions/">instructions page</a>.</span></li>', STEPS),
        "not its steps or their wording"),
    # A box that is neither a checked element, an ancestor nor an element it holds can cover or move 1, so the class
    # pin does not reach a class on it.
    ("p.meta with a further class", edit(PAGE, '<p class="meta">', '<p class="meta fresh">'),
        "``.fresh { margin-bottom: 300vh; }`` on ``p.meta``"),
]
# Faults to a copy of STYLESHEETS and PIN_FILE for stylesheet_problems(), the comparison of the committed stylesheets
# with RULE_PIN, and the words that its problems must hold, each in 1 of them; none for none. Each rule is named as
# that comparison names it: a pinned rule by its file name and preludes, a rule the pin does not hold by its text.
# BASELINE_SHEET is the stylesheet that the faults change; BASELINE keeps the version (version_binding_problems()).
BASELINE_SHEET = STYLESHEETS[2]
INLINE_RULE = ".btn.inline { position: static; display: inline-block; text-decoration: none; margin: 0 0.6rem 0.6rem 0; }"
HOVER_RULE = ".btn.inline:hover { color: var(--button-hover-fg); }"
WIDER_RULE = INLINE_RULE.replace("static", "absolute")
WRAP_RULE = ".wrap { margin: 0; padding: 0 var(--pad); }"
# A class name, a ] and a comma in a string count for no selector, and a quote after an even run of backslashes ends
# its string: "\\" is 1 backslash. Each rule can match a pinned element, or sets a custom property a pinned rule uses.
STRING_RULE = 'h1[title="].fresh"] { display: none; }'
QUOTE_RULE = 'h1[title="\\"].fresh"] { display: none; }'
ESCAPE_RULE = '[title="\\\\"] .fresh, h1 { display: none; }'
ESCAPE_PROPERTY_RULE = '.fresh { content: "\\\\"; --text: red; }'
PIN_CASES = (
    ("the committed stylesheets and pin", None, ()),
    ("a pinned rule changed", edit(BASELINE_SHEET, INLINE_RULE, WIDER_RULE),
        (f"{GONE} 'baseline.css: .btn.inline' there", f"the rule '{BASELINE_SHEET}: {WIDER_RULE}', {ADDED}")),
    ("a rule the pin must hold added", append(BASELINE_SHEET, "\n.btn { writing-mode: vertical-rl; }\n"),
        (f"the rule '{BASELINE_SHEET}: .btn {{ writing-mode: vertical-rl; }}', {ADDED}",)),
    ("a pinned rule removed", edit(BASELINE_SHEET, HOVER_RULE + "\n", ""), (f"{GONE} 'baseline.css: .btn.inline:hover' there",)),
    ("a pinned rule moved", edit(BASELINE_SHEET, INLINE_RULE + "\n" + HOVER_RULE, HOVER_RULE + "\n" + INLINE_RULE),
        (f"{GONE} 'baseline.css: .btn.inline:hover' there", f"the rule '{BASELINE_SHEET}: {HOVER_RULE}', {ADDED}")),
    ("a comment between var and its ( in a pinned rule", edit(BASELINE_SHEET, WRAP_RULE, WRAP_RULE.replace("var(", "var/**/(")),
        (f"{GONE} 'baseline.css: .wrap' there", f"the rule '{BASELINE_SHEET}: {WRAP_RULE.replace('var(', 'var/**/(')}', {ADDED}")),
    ("a pin entry with another digest", repin("baseline.css: .btn.inline"),
        (f"{GONE} 'baseline.css: .btn.inline' there", f"the rule '{BASELINE_SHEET}: {INLINE_RULE}', {ADDED}")),
    *[(name, append(BASELINE_SHEET, f"\n{rule}\n"), (f"the rule {f'{BASELINE_SHEET}: {rule}'!r}, {ADDED}",)) for name, rule in (
        ("a pinned name with a class name and a ] in a string", STRING_RULE),
        ("a pinned name with an escaped quote, a ] and a class name in a string", QUOTE_RULE),
        ("a pinned name after a string that ends in an escaped backslash", ESCAPE_RULE),
        ("a used custom property after a string that ends in an escaped backslash", ESCAPE_PROPERTY_RULE))],
)


def unread_at_rule(text: str) -> str:
    """The problem of a prelude or statement that starts an at-rule outside AT_RULES, or ""."""
    rule = re.match(r"\s*@([-\w]*)", text)
    if rule and rule.group(1).lower() not in AT_RULES:
        return f"holds the at-rule @{rule.group(1)}, which it does not read"
    return ""


def css_rules(css: str) -> tuple[list[tuple[str, str, tuple[str, ...]]], str]:
    """The rules of a stylesheet as (prelude, declarations, at-rules) triples, each in the order its block closes, the
    at-rules being the preludes of the at-rules whose blocks hold it, outermost first, and "" or the 1 problem that
    makes it unreadable.

    It normalizes only CSS whitespace and comments. Outside a string, each run of CSS whitespace reads as 1 space,
    and none at either end of a prelude or a block; a comment reads as nothing beside CSS whitespace, at either end of
    a prelude or a declaration, or beside a character of OWN_TOKENS (but a "(" after a NAME_CHAR), and as an empty
    comment, /**/, between any other 2 characters, so that the boundary it keeps between 2 tokens stays
    (var/**/(--pad) does not read as var(--pad), 1 function, and @media/**/screen reads as itself); a string stays as
    written, in its own quotes. So a comment ends at the first "*/" and opens nowhere inside a string, a string ends
    at its next unescaped quote and opens nowhere inside a comment, and no brace, ";" or comment opener in either
    delimits anything. It fails closed on what it does not model: an unclosed comment, a comment between 2 NAME_CHAR
    in a selector, a string that a line break, escaped or not, or its end leaves open, a backslash outside a string,
    "<!--" or "-->", an unquoted url() holding a quote, a "(", a brace, a backslash or a line break, a brace inside
    brackets or
    parentheses, unbalanced braces, brackets or parentheses, a rule inside a rule (CSS nesting), and an at-rule outside
    AT_RULES. The character before a comment is the last one read before it and before the empty comments that
    adjacent comments left, so a run of adjacent comments between 2 NAME_CHAR in a selector fails too."""
    rules: list[tuple[str, str, tuple[str, ...]]] = []
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
            # The character before a comment is read past the empty comments that adjacent comments before it left,
            # so that .a/**//**/b still holds a comment between 2 characters of names.
            kept = len(text)
            while kept and text[kept - 1] == "/**/":
                kept -= 1
            before, after = "".join(text[:kept])[-1:], css[index:index + 1]
            if (before.strip(CSS_SPACE) and after.strip(CSS_SPACE) and before not in OWN_TOKENS
                    and (after not in OWN_TOKENS or (after == "(" and NAME_CHAR.match(before)))):
                # Declarations sit in a style rule's block or an @font-face block; a prelude of a style rule is a
                # selector, and 1 of an at-rule starts with "@".
                values = blocks and (not blocks[-1][0].startswith("@") or re.match("@font-face", blocks[-1][0], re.I))
                if (NAME_CHAR.match(before) and NAME_CHAR.match(after) and not values
                        and not "".join(text).lstrip(" ").startswith("@")):
                    return [], "has a comment between 2 characters of names in a selector, which CSS reads as no space"
                text.append("/**/")
            continue
        if char in CSS_SPACE:
            if not (text and text[-1].endswith(" ")):
                text.append(" ")
            index += 1
            continue
        if char in "\"'":
            end = index + 1
            while end < len(css) and css[end] != char and css[end] not in "\r\n\f":
                if css[end] == "\\" and css[end + 1:end + 2] in ("\r", "\n", "\f"):
                    return [], "has a string that a line break ends"
                end += 2 if css[end] == "\\" else 1
            if end >= len(css):
                return [], "has a string that its end leaves open"
            if css[end] != char:
                return [], "has a string that a line break ends"
            text.append(css[index:end + 1])
            index = end + 1
            continue
        if char == "\\":
            return [], "holds a backslash outside a string"
        if css.startswith(("<!--", "-->"), index):
            return [], "holds <!-- or -->"
        url = URL_START.match(css, index) if char in "uU" else None
        if url and not re.match(r"[\w-]", css[index - 1:index]) and css[url.end():url.end() + 1] not in ("'", '"'):
            end = css.find(")", index)
            if end < 0 or re.search(r"[\"'(\\{}\r\n\f]", css[index + 4:end]):
                return [], "has an unquoted url() holding a quote, a (, a brace, a backslash or a line break"
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
            prelude = "".join(text).strip(" ")
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
            rules.append((block[0], "".join(block[1:] + text).strip(" "), tuple(outer[0] for outer in blocks)))
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


def blank_strings(text: str) -> str:
    """text with each character inside a string (STRING) read as U+0000, so that no bracket, separator or name in a
    string counts, and every character keeps its place."""
    return STRING.sub(lambda match: match.group(0)[0] + "\0" * (len(match.group(0)) - 2) + match.group(0)[-1], text)


def split_outside(text: str, separators: str) -> list[str]:
    """The parts of text between the characters of separators that sit outside every string, bracket and parenthesis."""
    parts, start, depth = [], 0, 0
    for at, char in enumerate(blank_strings(text)):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif depth == 0 and char in separators:
            parts.append(text[start:at])
            start = at + 1
    return parts + [text[start:]]


def can_match(prelude: str, classes: dict[str, set[str]]) -> bool:
    """Whether a selector list can match an element with a name and classes of classes (each tag with the classes it
    may carry; any element may carry none), read by the subject of each selector, its last compound selector, and
    conservatively: what it does not read by names and classes (a combinator and what comes before it, an attribute
    selector, an id, a pseudo-class with or without arguments, :has(), :is() and :not() among them, and a
    pseudo-element) is taken to match, and a namespace makes the selector match. What sits in a string counts for
    nothing (blank_strings)."""
    for selector in split_outside(prelude, ","):
        subject = split_outside(selector.strip(" "), " >+~")[-1]
        depth, kept = 0, []
        for char in blank_strings(subject):
            depth += char in "(["
            kept.append(char if depth == 0 else "")
            depth -= char in ")]"
        compound = "".join(kept)
        if "|" in compound:
            return True
        tag = TYPE_NAME.match(compound)
        names = CLASS_NAME.findall(compound)
        if tag and tag.group(0) != "*":
            allowed = [classes.get(tag.group(0).lower(), set())]
        else:
            allowed = [*classes.values(), set()]
        if any(set(names) <= held for held in allowed):
            return True
    return False


def rule_text(prelude: str, declarations: str, at_rules: tuple[str, ...]) -> str:
    """A rule as the pin holds it: its prelude and its declarations in braces, inside the blocks of its at-rules."""
    text = " ".join(part for part in (prelude, "{", declarations, "}") if part)
    for at_rule in reversed(at_rules):
        text = f"{at_rule} {{ {text} }}"
    return text


def rule_pins(sheets: list[tuple[str, str]], classes: dict[str, set[str]]) -> tuple[list[tuple[str, str]], list[str]]:
    """The rules of sheets, as (path, css) pairs read together, that the pin holds, in order, each as its name (its
    file name, ": " and the preludes before its declarations) and its text ("<path>: <rule>"), and the problems of the
    stylesheets that css_rules() cannot read. It holds every rule that can_match() reads as able
    to match an element of classes, every keyframe among them (from, to or a percentage carries no class), every
    @font-face rule, and every rule that sets a custom property that a rule it holds names in var(), until no more
    is added."""
    problems: list[str] = []
    read: list[tuple[str, tuple[str, str, tuple[str, ...]]]] = []
    for relative, css in sheets:
        rules, problem = css_rules(css)
        if problem or not rules:
            problems.append(f"{relative} {problem or 'holds no rule'}; it cannot be read.")
        read += [(relative, rule) for rule in rules]
    held = {
        at for at, (_, (prelude, declarations, _)) in enumerate(read)
        if (declarations if prelude.startswith("@") else can_match(prelude, classes))
    }
    while True:
        used = {name for at in held for name in VAR_NAME.findall(read[at][1][1])}
        more = {at for at, (_, (_, declarations, _)) in enumerate(read) if at not in held
                and any(part.partition(":")[0].strip(" ") in used for part in split_outside(declarations, ";"))}
        if not more:
            break
        held |= more
    return [(f"{Path(relative).name}: " + " { ".join((*rule[2], rule[0])), f"{relative}: {rule_text(*rule)}")
            for at, (relative, rule) in enumerate(read) if at in held], problems


def pin_lines(held: list[tuple[str, str]]) -> list[str]:
    """Each rule as RULE_PIN holds it: the first 16 hexadecimal digits of the sha256 of its text, as UTF-8, then a space
    and its name. 64 bits tell apart the changes this pin guards against, honest edits; tools/check-baseline-pin.py
    pins each whole stylesheet by its full sha256."""
    return [f"{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]} {name}" for name, text in held]


def sheet_problems(sheets: list[tuple[str, str]], classes: dict[str, set[str]], pin: list[str]) -> list[str]:
    """For the stylesheets sheets, as (path, css) pairs read together: css_rules() can read each, and rule_pins() gives
    exactly the rules of pin, in its order; each rule it gives that pin does not hold there, and each rule of pin it
    does not give there, is a problem."""
    held, problems = rule_pins(sheets, classes)
    return problems or diff_problems(pin, held)


def sheet_case_problems() -> list[str]:
    """sheet_problems(), with CASE_CLASSES and the pin of CASE_RULES, gives each of SHEET_CASES a problem holding its
    words, or none where they are ""."""
    problems: list[str] = []
    for name, css, words in SHEET_CASES:
        found = sheet_problems([("the case", css)], CASE_CLASSES, pin_lines(list(CASE_RULES)))
        if not any(words in problem for problem in found) if words else found:
            problems.append(f"{name}: expected " + (f"a problem with {words!r}" if words else "none") + f", got {found}")
    return problems


def load_gate():
    spec = importlib.util.spec_from_file_location("check_install_page", GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate


def pinned_classes(gate) -> dict[str, set[str]]:
    """Each tag of the gate's CLASS_PIN with every class it may carry in any place there."""
    classes: dict[str, set[str]] = {}
    for maps in gate.CLASS_PIN.values():
        for held in maps:
            for tag, names in held.items():
                classes.setdefault(tag, set()).update(names)
    return classes


def committed_rules(root: Path = REPO_ROOT) -> tuple[list[str], list[str]]:
    """The rules of STYLESHEETS under root that rule_pins() holds for the gate's CLASS_PIN, and the problems of reading
    them."""
    try:
        classes = pinned_classes(load_gate())
    except Exception as error:
        return [], [f"CLASS_PIN could not be read from tools/{GATE.name}: {error!r}"]
    sheets: list[tuple[str, str]] = []
    problems: list[str] = []
    for relative in STYLESHEETS:
        try:
            sheets.append((relative, (root / relative).read_text(encoding="utf-8")))
        except (OSError, UnicodeError) as error:
            problems.append(f"{relative} could not be read: {error}")
    held, unread = rule_pins(sheets, classes)
    return held, problems + unread


def stylesheet_problems(root: Path = REPO_ROOT) -> list[str]:
    """The rules of STYLESHEETS under root that can match an element the gate's CLASS_PIN names are exactly those of
    PIN_FILE under root (RULE_PIN, for the committed tree)."""
    held, problems = committed_rules(root)
    try:
        pin = (root / PIN_FILE).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        return problems + [f"{PIN_FILE} could not be read: {error}"]
    return problems or [f"{problem} Update the pin only as the docstring of tools/{Path(__file__).name} says."
                        for problem in diff_problems(pin, held)]


def pin_case_problems() -> list[str]:
    """stylesheet_problems(), on a copy of STYLESHEETS and PIN_FILE with the fault of each of PIN_CASES, gives problems
    that hold each of its words, or none where it gives none; a fault whose text the copy does not hold is a problem."""
    problems: list[str] = []
    for name, fault, words in PIN_CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            for relative in (*STYLESHEETS, PIN_FILE):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / relative, root / relative)
            # A committed stylesheet that no longer holds the text a fault edits is a problem, not a crash, so the
            # comparison of the committed stylesheets with the pin still runs and names the rule.
            try:
                if fault:
                    fault(root)
            except AssertionError as error:
                problems.append(f"{name}: its fault could not be applied: {error}")
                continue
            found = stylesheet_problems(root)
        if [word for word in words if not any(word in problem for problem in found)] if words else found:
            problems.append(f"{name}: expected " + (f"problems with {words!r}" if words else "none") + f", got {found}")
    return problems


def diff_problems(pin: list[str], held: list[tuple[str, str]]) -> list[str]:
    """Each rule of held that pin does not hold there, by its text, and each rule of pin that held does not give
    there, unchanged, by its name."""
    lines = pin_lines(held)
    problems: list[str] = []
    for kind, first, last, start, end in difflib.SequenceMatcher(a=pin, b=lines, autojunk=False).get_opcodes():
        if kind == "equal":
            continue
        problems += [f"the stylesheets no longer give the pinned rule {line.partition(' ')[2]!r} there, or give it "
                     "changed." for line in pin[first:last]]
        problems += [f"the stylesheets give the rule {text!r}, {ADDED}; it can match an element the gate's "
                     "CLASS_PIN names, or sets a custom property that a pinned rule uses." for _, text in held[start:end]]
    return problems


def paragraph_links(gate, parser) -> list:
    """Each link on a family page that can be its required link back as the committed pages give one, with the kind
    "a link back": a link to /install/#get or /install/#test outside every element of INERT_ELEMENTS, not hidden, with
    visible text and no class, which no li holds (a link in a step cannot pass the pins of a link back, which allow
    no li around it). The required link back is the first of them on each committed page, and a later 1 (in a
    div.callout, say) is the required link back once those before it are gone, so the pins of a link back must hold
    them all."""
    by_order = {element["order"]: element for element in parser.elements}
    links = []
    for anchor in parser.anchors:
        element = by_order[anchor["order"]]
        ancestors = [other["tag"] for position, other in gate.pin_positions(parser, element) if position == 1]
        if (anchor["href"] in ("/install/#get", "/install/#test") and not anchor["inert"] and not anchor["hidden"]
                and anchor["text"] and not anchor["classes"] and "li" not in ancestors):
            links.append(("a link back", element))
    return links


def checked_kinds(gate, relative: str, parser) -> list:
    """The checked elements of a page, each with its kind, as the gate's pins hold them: install_kinds() on the
    install page, and on a family page those of family_checked(), which holds only the required link back to each
    target, with each of paragraph_links(), which the pins of a link back must also hold."""
    if relative == PAGE:
        return gate.install_kinds(parser)
    kinds = gate.family_checked(relative, parser)[0]
    held = {element["order"] for kind, element in kinds if kind == "a link back"}
    return kinds + [link for link in paragraph_links(gate, parser) if link[1]["order"] not in held]


def class_pin_problems(pin: str = "CLASS_PIN", field: str = "classes", root: Path = REPO_ROOT) -> list[str]:
    """The gate's CLASS_PIN (or ATTRIBUTE_PIN, with field "attrs") holds, for each kind, exactly the classes (or the
    attributes) the pages under root give that checked element, each of its ancestors and each element it holds, by
    tag, so that the pin cannot be widened unnoticed."""
    try:
        gate = load_gate()
        found = {kind: ({}, {}, {}) for kind in getattr(gate, pin)}
        for relative in (PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER):
            parser = gate.parse((root / relative).read_text(encoding="utf-8"))
            for kind, element in checked_kinds(gate, relative, parser):
                for position, other in gate.pin_positions(parser, element):
                    if other[field]:
                        found[kind][position].setdefault(other["tag"], set()).update(other[field])
    except Exception as error:
        return [f"{pin} of tools/{GATE.name} could not be checked: {error!r}"]
    problems: list[str] = []
    for kind, maps in getattr(gate, pin).items():
        recorded = tuple({tag: set(names) for tag, names in held.items()} for held in maps)
        if recorded != found[kind]:
            problems.append(f"{pin} of tools/{GATE.name} gives {kind} {recorded}; the committed pages give "
                            f"{found[kind]}.")
    return problems


def inventory_case_problems() -> list[str]:
    """The inventories of the gate's CLASS_PIN, ATTRIBUTE_PIN and TAG_PIN pass on a copy of the pages with STEP_LINK,
    a further link back to #get in a Gemini step, which the gate passes too (CASES): each reads, as the gate does, only
    the required link back to each target."""
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        STEP_LINK(root)
        found = class_pin_problems(root=root) + class_pin_problems("ATTRIBUTE_PIN", "attrs", root) + tag_pin_problems(root)
    return [f"with a further link back to #get in a Gemini step: {problem}" for problem in found]


def head_pin_problems() -> list[str]:
    """The gate's HEAD_PIN holds exactly the meta, link and base elements that the committed pages carry, by the
    gate's head_key(), each with every attribute it carries and that attribute's value, None only where
    FREE_HEAD_VALUES leaves it free, so that the pin cannot be widened unnoticed; the elements of 1 key carry the same
    attributes, with the same values where they are not free."""
    try:
        gate = load_gate()
        found: dict = {}
        problems: list[str] = []
        for relative in (PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER):
            for element in gate.parse((REPO_ROOT / relative).read_text(encoding="utf-8")).elements:
                if element["tag"] not in ("meta", "link", "base"):
                    continue
                key = gate.head_key(element["tag"], element["values"])
                free = FREE_HEAD_VALUES.get(key)
                values = {name: None if name == free else value for name, value in element["values"].items()}
                if found.setdefault(key, values) != values:
                    problems.append(f"{relative} carries {key} as {values}, another page as {found[key]}.")
    except Exception as error:
        return [f"HEAD_PIN of tools/{GATE.name} could not be checked: {error!r}"]
    if gate.HEAD_PIN != found:
        problems.append(f"HEAD_PIN of tools/{GATE.name} holds {gate.HEAD_PIN}; the committed pages carry {found}.")
    return problems + [f"FREE_HEAD_VALUES names {key}, which no committed page carries."
                       for key in FREE_HEAD_VALUES if key not in found]


def rule_attributes(held: list[tuple[str, str]]) -> set[str]:
    """The attributes that the attribute selectors of the rules of held name, read from each rule's name (its file
    name and preludes) with its strings blanked, in lower case."""
    return {name.lower() for rule, _ in held for name in ATTRIBUTE_NAME.findall(blank_strings(rule))}


def attribute_pin_problems() -> list[str]:
    """The gate's RULE_ATTRIBUTES holds exactly the attributes that the attribute selectors of the committed rules the
    rule pin holds name, HIDING_ATTRIBUTE aside, so that the gate cannot drop one unnoticed."""
    held, problems = committed_rules()
    if problems:
        return problems
    try:
        recorded = set(load_gate().RULE_ATTRIBUTES)
    except Exception as error:
        return [f"RULE_ATTRIBUTES could not be read from tools/{GATE.name}: {error!r}"]
    named = rule_attributes(held) - {HIDING_ATTRIBUTE}
    if recorded != named:
        return [f"RULE_ATTRIBUTES of tools/{GATE.name} holds {sorted(recorded)}; the pinned rules name {sorted(named)}."]
    return []


def header_pin_problems() -> list[str]:
    """The gate's INSTALL_HEADERS holds, for each URL pattern of the committed site/_headers that the gate's
    reaches_page() reads as able to match an install page or a file the pages load, exactly the headers and values
    that the file sets there, and no detach, so that the header pin cannot be widened unnoticed."""
    try:
        gate = load_gate()
        entries = gate.load_tool("check-headers.py").parse((REPO_ROOT / HEADERS).read_text(encoding="utf-8"))
        found: dict[str, list[tuple[str, str, str | None]]] = {}
        for _, pattern, kind, name, value in entries:
            if gate.reaches_page(pattern):
                found.setdefault(pattern, []).append((kind, name.lower(), value))
        recorded = {pattern: [("set", name, value) for name, value in held] for pattern, held in gate.INSTALL_HEADERS.items()}
    except (Exception, SystemExit) as error:
        return [f"INSTALL_HEADERS of tools/{GATE.name} could not be checked: {error!r}"]
    if ({pattern: sorted(held, key=repr) for pattern, held in recorded.items()}
            != {pattern: sorted(held, key=repr) for pattern, held in found.items()}):
        return [f"INSTALL_HEADERS of tools/{GATE.name} holds {recorded}; the committed {HEADERS} sets {found} under "
                "the URL patterns that can match an install page or a file the install pages load."]
    return []


def tag_pin_problems(root: Path = REPO_ROOT) -> list[str]:
    """The gate's TAG_PIN holds, for each kind, exactly the tags the pages under root give that checked element, each
    of its ancestors and each element it holds, so that the pin cannot be widened unnoticed."""
    try:
        gate = load_gate()
        found = {kind: (set(), set(), set()) for kind in gate.TAG_PIN}
        for relative in (PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER):
            parser = gate.parse((root / relative).read_text(encoding="utf-8"))
            for kind, element in checked_kinds(gate, relative, parser):
                for position, other in gate.pin_positions(parser, element):
                    found[kind][position].add(other["tag"])
        recorded = {kind: tuple(set(tags) for tags in held) for kind, held in gate.TAG_PIN.items()}
    except Exception as error:
        return [f"TAG_PIN of tools/{GATE.name} could not be checked: {error!r}"]
    return [f"TAG_PIN of tools/{GATE.name} gives {kind} {recorded[kind]}; the committed pages give {found[kind]}."
            for kind in recorded if recorded[kind] != found[kind]]


def page_attribute_pin_problems() -> list[str]:
    """The gate's PAGE_ATTRIBUTES holds, for each tag, exactly the attributes that the committed pages give an element
    of that tag, anywhere on them, and no tag whose elements carry none, so that the pin cannot be widened unnoticed."""
    try:
        gate = load_gate()
        found: dict[str, set[str]] = {}
        for relative in (PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER):
            for element in gate.parse((REPO_ROOT / relative).read_text(encoding="utf-8")).elements:
                if element["attrs"]:
                    found.setdefault(element["tag"], set()).update(element["attrs"])
        recorded = {tag: set(names) for tag, names in gate.PAGE_ATTRIBUTES.items()}
    except Exception as error:
        return [f"PAGE_ATTRIBUTES of tools/{GATE.name} could not be checked: {error!r}"]
    if recorded != found:
        return [f"PAGE_ATTRIBUTES of tools/{GATE.name} holds {recorded}; the committed pages give {found}."]
    return []


def page_tag_pin_problems() -> list[str]:
    """The gate's PAGE_TAGS holds exactly the tags of the elements of the committed pages, anywhere on them, so that
    the pin cannot be widened unnoticed."""
    try:
        gate = load_gate()
        found = {element["tag"] for relative in (PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER)
                 for element in gate.parse((REPO_ROOT / relative).read_text(encoding="utf-8")).elements}
        recorded = set(gate.PAGE_TAGS)
    except Exception as error:
        return [f"PAGE_TAGS of tools/{GATE.name} could not be checked: {error!r}"]
    if recorded != found or len(recorded) != len(gate.PAGE_TAGS):
        return [f"PAGE_TAGS of tools/{GATE.name} holds {sorted(gate.PAGE_TAGS)}; the committed pages give {sorted(found)}."]
    return []


def name_reading_problems() -> list[str]:
    """The gate's parse() and name_text(), run in this process on fragments, apart from the pins, read a family page
    heading as check 4 says: each br that no element hides, </br> included, reads as 1 space, a hidden br as nothing,
    and U+034F is kept, while has_visible_text() reads text of only U+034F or U+0000 as not visible."""
    expected = (
        ("<h1>Other AI<br>systems</h1>", "other ai systems"),
        ("<h1>Other AI</br>systems</h1>", "other ai systems"),
        ("<h1>Other AI<br hidden>systems</h1>", "other aisystems"),
        ("<h1>Other AI<span hidden><br></span>systems</h1>", "other aisystems"),
        ("<h1>Chat&shy;GPT</h1>", "chatgpt"),
        ("<h1>Chat\u034fGPT</h1>", "chat\u034fgpt"),
    )
    try:
        gate = load_gate()
        problems = [f"parse() and name_text() read {markup!r} as {gate.name_text(gate.parse(markup).h1[0]['chars'])!r}, "
                    f"not {name!r}." for markup, name in expected
                    if gate.name_text(gate.parse(markup).h1[0]["chars"]) != name]
        problems += [f"has_visible_text() reads {text!r} as visible." for text in ("\u034f", "\0", "\u200b\u034f")
                     if gate.has_visible_text(text)]
        # load_path() reads a load target as a path from the site's root, refusing a . or .. segment even where the
        # path it names is pinned, so its refusal does not rest on the pin alone.
        paths = ((f"/assets/baseline/copy.js?v={BASELINE}", "assets/baseline/copy.js"), ("/assets/./baseline/copy.js", None),
                 ("/assets/baseline/../baseline/copy.js", None), ("assets/baseline/copy.js", None),
                 ("//host/assets/baseline/copy.js", None), ("/assets/%2e%2e/images/a.png", None))
        problems += [f"load_path() reads {target!r} as {gate.load_path(target)!r}, not {path!r}."
                     for target, path in paths if gate.load_path(target) != path]
    except Exception as error:
        return [f"the name reading of tools/{GATE.name} could not be checked: {error!r}"]
    return problems


def end_tag_problems() -> list[str]:
    """The gate's P_PARENTS, IMPLIED_ENDS, TABLE_PARTS and SVG_SHAPES hold exactly what this states, so widening or
    narrowing any of them fails. Its parse(), run in this process on fragments, reads no misnested end tag (check 8)
    where a page leaves out an end tag that the HTML standard lets it omit where no more content follows in the parent
    element, for each such element and each parent at whose end tag a browser may close it too, inside the table in
    which a table part counts as opened; where a page leaves out an li's end tag before a sibling li; where a table
    start tag sits in a cell or a caption or after a table has ended; and for a self-closing svg, or circle or path
    directly in an svg. It reads 1
    where a browser may keep open an element that the parser closes (a p in a span, a b or an a, and a div around an
    open table cell, whose end tag a browser may ignore), where that parent is a table part outside the parents of
    TABLE_PARTS, which does not count as opened there, where a table start tag ends the table around it, where a
    self-closing tag in an svg is anything else or is not directly in it, and where the parser keeps any other element
    whose end tag a page omits before a sibling open around that sibling, as the gate's docstring states."""
    p_parents = ["address", "article", "aside", "blockquote", "caption", "dd", "details", "dialog", "div", "dt", "fieldset",
                 "figcaption", "figure", "footer", "form", "header", "hgroup", "li", "main", "nav", "section", "td", "th"]
    implied = {"li": ["li", "menu", "ol", "ul"], "dd": ["div", "dl"], "p": p_parents, "rt": ["ruby"], "rp": ["ruby"],
               "optgroup": ["select"], "option": ["datalist", "optgroup", "select"], "tbody": ["table"], "tfoot": ["table"],
               "tr": ["table", "tbody", "tfoot", "thead"], "td": ["tr"], "th": ["tr"]}
    table_parts = {"caption": ["table"], "tbody": ["table"], "tfoot": ["table"], "thead": ["table"],
                   "tr": ["table", "tbody", "tfoot", "thead"], "td": ["tr"], "th": ["tr"]}
    svg_shapes = ["circle", "path"]
    # What the parser must hold, before the part itself, for each table part to count as opened.
    opening = {"caption": "<table>", "tbody": "<table>", "tfoot": "<table>", "thead": "<table>", "tr": "<table>",
               "td": "<table><tr>", "th": "<table><tr>"}
    omitted = [f"{opening.get(parent, '')}<{parent}><{child}>x</{parent}>"
               for child, parents in implied.items() for parent in parents]
    omitted += ["<ul><li>a<li>b</ul>", "<ol><li>a<li>b<li>c</ol>", "<ul><li>a<li><p>b</ul>",
                "<table><tr><td><table></table><p>x</td>", "<table><tr><th><table></table><p>x</th>",
                "<table><caption><table></table><p>x</caption>", "<table></table><table><tr><td><p>x</td>",
                "<svg><path/></svg>", "<svg><circle/><path/></svg>", '<span class="vh"><svg><path/></svg></span>',
                "<span><svg/></span>"]
    misnested = ['<span class="vh"><p>x</span>', "<b><p>x</b>", "<a><p>x</a>", "<div><table><tr><td>x</div>",
                 # A table part with no table around it, and each in a parent that TABLE_PARTS does not name.
                 *[f"<{part}><{child}>x</{part}>" for part in opening for child, parents in implied.items()
                   if part in parents],
                 "<table><td><p>x</td>", "<table><caption><td><p>x</td>", "<table><tr><div><td><p>x</td>",
                 '<span class="vh"><td><p>x</td></span>', '<span class="vh"><caption><p>x</caption></span>',
                 # A table start tag that ends the table around it, in a row: nothing from that table on counts as
                 # opened, so the gate refuses the cell's end tag with the p still open in the first, and the outer
                 # table's end tag with the row still open in the third. The second puts the cell in a div in the
                 # table, after such a start tag; a td whose parent is a div never counts as opened (TABLE_PARTS), so
                 # it reads as misnested with or without that start tag.
                 "<table><tr><table></table><td><p>x</td>", "<table><div><table></table><td><p>x</td>",
                 "<table><tr><table></table></table>",
                 # A self-closing tag in an svg that is not 1 of SVG_SHAPES, or 1 whose parent is not the svg.
                 '<span class="vh"><svg><div/></svg></span>', "<svg><p/></svg>", "<svg><rect/></svg>",
                 "<svg><b><path/></b></svg>", "<div><path/></div>",
                 # An end tag omitted before a sibling, other than an li directly in an li.
                 '<span class="vh"><li>a<li>b</span>', "<ul><li><p>a<li>b</ul>", "<div><p>a<p>b</div>",
                 "<dl><dd>a<dd>b</dl>", "<table><tr><td>a<td>b</table>"]
    try:
        gate = load_gate()
        problems = [f"{name} of tools/{GATE.name} holds {sorted(held)}, not {sorted(stated)}." for name, held, stated in (
            ("P_PARENTS", gate.P_PARENTS, p_parents), ("SVG_SHAPES", gate.SVG_SHAPES, svg_shapes),
            *[(f"IMPLIED_ENDS[{child!r}]", gate.IMPLIED_ENDS.get(child, ()), implied[child]) for child in implied],
            *[(f"TABLE_PARTS[{part!r}]", gate.TABLE_PARTS.get(part, ()), table_parts[part]) for part in table_parts],
            ("IMPLIED_ENDS", gate.IMPLIED_ENDS, implied), ("TABLE_PARTS", gate.TABLE_PARTS, table_parts),
        ) if sorted(held) != sorted(stated)]
        problems += [f"parse() reads {markup!r} as misnested: {gate.parse(markup).misnested}." for markup in omitted
                     if gate.parse(markup).misnested]
        problems += [f"parse() reads {markup!r} with no misnested end tag." for markup in misnested
                     if not gate.parse(markup).misnested]
    except Exception as error:
        return [f"the end tags of tools/{GATE.name} could not be checked: {error!r}"]
    return problems


def loaded_segment_problems() -> list[str]:
    """The gate's LOADED_SEGMENTS holds exactly the first path segments of the files the committed pages load: each
    src, each href of a link other than the canonical link, and each url() of STYLESHEETS, read from the address of
    its stylesheet, so that the redirect and header refusal of check 7 covers every 1 of them."""
    try:
        gate = load_gate()
        loads: set[str] = set()
        for relative in (PAGE, CLAUDE, CHATGPT, GEMINI, COPILOT, OTHER):
            for element in gate.parse((REPO_ROOT / relative).read_text(encoding="utf-8")).elements:
                values = element["values"]
                if "src" in values:
                    loads.add(values["src"])
                if element["tag"] == "link" and values.get("rel") != "canonical":
                    loads.add(values.get("href", ""))
        for relative in STYLESHEETS:
            address = "/" + relative.removeprefix("site/")
            for match in CSS_URL.finditer((REPO_ROOT / relative).read_text(encoding="utf-8")):
                loads.add(urllib.parse.urljoin(address, match.group(1)))
        found = {gate.path_segment(load).lower() for load in loads}
        recorded = set(gate.LOADED_SEGMENTS)
        unpinned = sorted(load for load in loads if gate.load_path(load) not in gate.pinned_files())
    except (Exception, SystemExit) as error:
        return [f"LOADED_SEGMENTS of tools/{GATE.name} could not be checked: {error!r}"]
    if any(not load.startswith("/") for load in loads):
        return [f"the committed pages load {sorted(load for load in loads if not load.startswith('/'))}, which is "
                "not a path from the site's root, so LOADED_SEGMENTS cannot cover it."]
    if unpinned:
        return [f"the committed pages or stylesheets load {unpinned}, which the gate's load_path() does not read as 1 "
                "of the files tools/check-baseline-pin.py pins."]
    if recorded != found:
        return [f"LOADED_SEGMENTS of tools/{GATE.name} holds {sorted(recorded)}; the committed pages load files under "
                f"{sorted(found)}."]
    return []


def glob_pattern(pattern: str) -> re.Pattern:
    """A path filter of a workflow as GitHub reads it, as far as this test needs: ** matches any characters, / among
    them, and * any characters but /."""
    parts = re.split(r"(\*\*|\*)", pattern)
    return re.compile("".join({"**": ".*", "*": "[^/]*"}.get(part, re.escape(part)) for part in parts))


def workflow_path_problems(text: str | None = None) -> list[str]:
    """Each of the 2 path lists of WORKFLOW (pull_request and push) covers every file the gate, this test and the
    workflow read, and every path of the gate's SERVER_ENTRIES, as a file and at any depth under a directory, so that a
    change to any of them runs the workflow, and holds no negative pattern (1 that starts with !). GitHub reads the
    patterns in order, and a negative 1 excludes the paths it matches until a later pattern includes them again; this
    reads each positive pattern as a match on its own, so it fails closed on every negative pattern, wherever it sits
    and whatever it matches. A path list is the lines after a line that is only paths:, up to the first line, blank
    lines and comment lines aside, that is not indented deeper than it. Of those lines, this reads only an item
    written as - "PATTERN" or - 'PATTERN', with no backslash and no quote of that kind in the pattern and nothing after
    its closing quote but spaces and a comment that spaces set off, and refuses every other line, so an item it cannot
    read (unquoted, escaped, or with a doubled single quote), a negative pattern among them, fails instead of going
    unread. It reads no other form of a list: a paths: line with anything else on it (a flow sequence, an anchor, an
    alias or a comment), and items not indented deeper than paths:, hold no list here, so the workflow then has fewer
    than 2 path lists, and that fails."""
    try:
        if text is None:
            text = (REPO_ROOT / WORKFLOW).read_text(encoding="utf-8")
        gate = load_gate()
        entries = [path for name in gate.SERVER_ENTRIES for path in (name, f"{name}/index.js", f"{name}/a/b/index.js")]
    except Exception as error:
        return [f"{WORKFLOW} could not be checked: {error!r}"]
    lists: list[list[str]] = []
    unread: list[str] = []
    indent = None
    for line in text.splitlines():
        depth = len(line) - len(line.lstrip(" "))
        if line.strip() == "paths:":
            lists.append([])
            indent = depth
        elif indent is None or not line.strip() or line.strip().startswith("#"):
            continue
        elif depth > indent:
            item = re.fullmatch(r""" *- (?:"([^"\\]+)"|'([^'\\]+)')(?: +#.*| *)""", line)
            if item:
                lists[-1].append(item.group(1) or item.group(2))
            else:
                unread.append(line.strip())
        else:
            indent = None
    problems = [f"a path list of {WORKFLOW} holds {line!r}, which this test does not read: it reads only an item "
                """written - "PATTERN" or - 'PATTERN', with no backslash or quote of that kind in it and nothing after the """
                "closing quote but spaces and a comment." for line in unread]
    lists = [held for held in lists if held]
    if len(lists) != 2:
        return problems + [f"{WORKFLOW} has {len(lists)} path lists with entries, not 2 (pull_request and push)."]
    read = [f"tools/{GATE.name}", f"tools/{Path(__file__).name}", *FILES, *STYLESHEETS, PIN_FILE, *WORKFLOW_ALSO]
    for number, held in enumerate(lists, 1):
        problems += [f"path list {number} of {WORKFLOW} holds the negative pattern {pattern}; this test does not read "
                     "the order of the patterns, so it refuses every negative 1." for pattern in held if pattern[:1] == "!"]
        patterns = [glob_pattern(pattern) for pattern in held if pattern[:1] != "!"]
        problems += [f"path list {number} of {WORKFLOW} does not cover {path}, which the gate, its test or the "
                     "workflow reads."
                     for path in [*read, *entries] if not any(pattern.fullmatch(path) for pattern in patterns)]
    return problems


def workflow_case_problems() -> list[str]:
    """workflow_path_problems() refuses the committed workflow with site/_redirects removed from 1 path list, or from
    both, with functions/** narrowed to functions/*, which covers no nested path, in 1 path list or in both, and with
    !functions/**, which GitHub reads as excluding what functions/** before it includes, after functions/** in 1 path
    list or in both: double-quoted, single-quoted, written with the escape \\x21 for its !, or quoted either way and
    followed by a comment. It refuses, in the first path list or in both, each other form of an item that it does not
    read: an unquoted item, a comment with no space before it, a doubled single quote and a backslash in single quotes;
    and each form of a list that it does not read: a flow sequence, an anchored list, a comment on the paths: line and
    an indentless sequence, the last in both lists and the others in the first. It finds no problem in the committed
    workflow with a blank line and a comment line after functions/** in both path lists, with a further functions/**
    single-quoted, followed by a comment, or both, or with site/_redirects itself written so in both, which GitHub
    reads as it reads the committed 1; and that last shows that it reads those items, since each list needs them."""
    text = (REPO_ROOT / WORKFLOW).read_text(encoding="utf-8")
    line = '      - "site/_redirects"\n'
    if text.count(line) != 2:
        return [f"{WORKFLOW} lists site/_redirects {text.count(line)} times, not once in each path list."]
    problems: list[str] = []
    for name, edited in (("from the first path list", text.replace(line, "", 1)), ("from both", text.replace(line, ""))):
        if not workflow_path_problems(edited):
            problems.append(f"site/_redirects removed {name}: workflow_path_problems() found no problem.")
    tree = '      - "functions/**"\n'
    if text.count(tree) != 2:
        return problems + [f"{WORKFLOW} lists functions/** {text.count(tree)} times, not once in each path list."]
    narrow = '      - "functions/*"\n'
    for name, edited in (("in the first path list", text.replace(tree, narrow, 1)), ("in both", text.replace(tree, narrow))):
        if not workflow_path_problems(edited):
            problems.append(f"functions/** narrowed to functions/* {name}: workflow_path_problems() found no problem.")
    for item in ('"!functions/**"', "'!functions/**'", '"\\x21functions/**"', '"!functions/**" # excluded',
                 "'!functions/**' # excluded", "functions/**", '"functions/**"#x', "'functions''**'",
                 "'\\x21functions/**'"):
        excluded = tree + f"      - {item}\n"
        for name, edited in (("in the first path list", text.replace(tree, excluded, 1)),
                             ("in both", text.replace(tree, excluded))):
            if not workflow_path_problems(edited):
                problems.append(f"- {item} after functions/** {name}: workflow_path_problems() found no problem.")
    block = re.compile(r'( *)paths:\n(?: +- .*\n)+')
    for name, edited in (("a flow sequence", block.sub(r'\1paths: ["functions/**"]\n', text, count=1)),
                         ("an anchored list", text.replace("paths:\n", "paths: &list\n", 1)),
                         ("a comment on the paths: line", text.replace("paths:\n", "paths: # note\n", 1)),
                         ("an indentless sequence", re.sub(r'\n {6}- ', r'\n    - ', text))):
        if not workflow_path_problems(edited):
            problems.append(f"{name} in a path list: workflow_path_problems() found no problem.")
    spaced = workflow_path_problems(text.replace(tree, tree + "\n      # Pages Functions\n"))
    if spaced:
        problems.append(f"a blank line and a comment line after functions/** in both: workflow_path_problems() found "
                        f"{spaced}, though GitHub reads the lists as committed.")
    for item in ("'functions/**'", '"functions/**" # again', "'functions/**' # again"):
        found = workflow_path_problems(text.replace(tree, tree + f"      - {item}\n"))
        if found:
            problems.append(f"- {item} after functions/** in both: workflow_path_problems() found {found}, though GitHub "
                            "reads it as the same pattern.")
    for item in ("'site/_redirects'", '"site/_redirects" # headers', "'site/_redirects' # headers"):
        found = workflow_path_problems(text.replace(line, f"      - {item}\n"))
        if found:
            problems.append(f"site/_redirects written {item} in both: workflow_path_problems() found {found}, though "
                            "GitHub reads it as the committed item.")
    return problems


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


def version_literal_problems() -> list[str]:
    """Each ?v= token in this file's own source that starts with a digit and that KEPT_TOKENS does not name: a case
    writes the current baseline version as BASELINE, read from the pin."""
    text = Path(__file__).read_text(encoding="utf-8")
    return [f"line {text.count(chr(10), 0, match.start()) + 1} carries {match.group(0)!r}; write BASELINE, or name "
            "the token in KEPT_TOKENS with the reason it is kept"
            for match in VERSION_LITERAL.finditer(text) if match.group(0) not in KEPT_TOKENS]


def version_binding_problems() -> list[str]:
    """Each binding in this file's own source of a name of VERSION_NAMES other than its first, read from the syntax
    tree: an assignment (plain, augmented, annotated, starred or :=), a deletion, a loop, comprehension, with or
    except target, a type alias, an import, a def, a class, an argument, a type parameter, a match capture, or a
    global or nonlocal statement; and each star import, which can bind any name. A local binding counts too, since a
    reader takes that name for the version. The syntax tree does not show a binding made by running code, such as
    one through globals(), exec or setattr on this module, so this check cannot see one."""
    lines: dict[str, list[int]] = {name: [] for name in VERSION_NAMES}
    stars: list[int] = []
    for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names = [node.id]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler,
                               ast.MatchAs, ast.MatchStar, ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)):
            names = [node.name]
        elif isinstance(node, ast.MatchMapping):
            names = [node.rest]
        elif isinstance(node, ast.alias) and node.name == "*":
            # A star import binds the names that the other module exports, which this file's syntax tree does not
            # list, so it may bind a name of VERSION_NAMES.
            stars.append(node.lineno)
            continue
        elif isinstance(node, ast.alias):
            names = [node.asname or node.name.partition(".")[0]]
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names = node.names
        elif isinstance(node, ast.arg):
            names = [node.arg]
        else:
            continue
        for name in names:
            if name in lines:
                lines[name].append(node.lineno)
    problems = [f"{name} is never bound" for name, found in lines.items() if not found]
    problems += [f"line {line} imports *, which can bind {', '.join(VERSION_NAMES)}; import the names it needs"
                 for line in sorted(stars)]
    return problems + [f"line {line} binds {name} again, after line {min(found)}; give that value its own name"
                       for name, found in lines.items() for line in sorted(found)[1:]]


def main() -> int:
    if sys.argv[1:] == [PRINT_PIN]:
        held, problems = committed_rules()
        print("\n".join(problems or pin_lines(held)), file=sys.stderr if problems else sys.stdout)
        return 1 if problems else 0
    failures: list[str] = statement_problems()
    failures += [f"the version literals: {problem}" for problem in version_literal_problems()]
    failures += [f"the version binding: {problem}" for problem in version_binding_problems()]
    failures += [f"the class pin: {problem}" for problem in class_pin_problems()]
    failures += [f"the attribute pin: {problem}" for problem in class_pin_problems("ATTRIBUTE_PIN", "attrs")]
    failures += [f"the head pin: {problem}" for problem in head_pin_problems()]
    failures += [f"the pinned attributes: {problem}" for problem in attribute_pin_problems()]
    failures += [f"the pinned headers: {problem}" for problem in header_pin_problems()]
    failures += [f"the tag pin: {problem}" for problem in tag_pin_problems()]
    failures += [f"the inventories: {problem}" for problem in inventory_case_problems()]
    failures += [f"the page attribute pin: {problem}" for problem in page_attribute_pin_problems()]
    failures += [f"the page tag pin: {problem}" for problem in page_tag_pin_problems()]
    failures += [f"the name reading: {problem}" for problem in name_reading_problems()]
    failures += [f"the end tags: {problem}" for problem in end_tag_problems()]
    failures += [f"the loaded files: {problem}" for problem in loaded_segment_problems()]
    failures += [f"the workflow paths: {problem}" for problem in workflow_path_problems() + workflow_case_problems()]
    failures += [f"the stylesheets: {problem}"
                 for problem in sheet_case_problems() + pin_case_problems() + stylesheet_problems()]
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
          f"ALLOWED_SCRIPTS, the scans of this file for literal versions and for a second binding of BASELINE, "
          f"the checks of CLASS_PIN, ATTRIBUTE_PIN, "
          f"HEAD_PIN, RULE_ATTRIBUTES, INSTALL_HEADERS, TAG_PIN, "
          f"PAGE_ATTRIBUTES, PAGE_TAGS, the inventories with a further link back in a step, the name reading, "
          f"the end tags, LOADED_SEGMENTS and the pinned loads, the workflow's path "
          f"lists, the Python version checks, the "
          f"{len(SHEET_CASES)} cases of the "
          f"stylesheet reader, the {len(PIN_CASES)} cases of the rule pin's comparison and the rule pin of the "
          "stylesheets passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
