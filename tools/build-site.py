#!/usr/bin/env python3
"""Generate the cleanlanguage.ai site on the shared template (baseline), with a base path.

The site is generated from ``site-src/`` into the folder its base path names:
``/`` writes ``site/`` (the published site, the current setting in
``site-src/site.json`` since promotion), and ``/draft/`` writes ``site/draft/``
(staging a new version for review). Cloudflare Pages publishes ``site/`` as
committed, so the output is committed and this tool's ``--check`` mode proves
that the committed output is exactly what the sources produce.

Sources
-------

- ``site-src/site.json``: base path, site class, navigation, page list (each
  page with its ``modified`` date, the ``article:modified_time`` of the ``/``
  build, and its ``published`` date), the fixed root paths a draft page may
  link to (``root_allowlist``), the files committed by hand beside the
  generated ones at ``site/`` (``static_files``), the family footer order, and
  the pages allowed to link the Disclosure and Licence pages.
- ``.baseline/pin.toml``: the baseline version (for the ``?v=`` asset tokens)
  and the pinned file list, the one source of both (``tools/copy-baseline.py``
  writes it, ``tools/check-baseline-pin.py`` checks the copied files). Only the
  keys under ``assets/baseline/`` are served; the pinned build tool
  ``.baseline/check_palette.py`` is not, so no link may resolve to it.
- ``site-src/release.json``: the release version, tag and checksum, written by
  ``tools/set-release-links.py``. Every version string the pages show comes
  from here, and the build refuses to run if it disagrees with the ``Version:``
  line of ``cleanlanguage/skills/cleanlanguage/SKILL.md``.
- ``site-src/pages/<page>.html``: the hand-written content of each page, with
  ``{{token}}`` placeholders.
- ``site-src/assets/site.css``, optional: only the measured per-site constants
  ``--sw`` and ``--logo-inset`` (baseline README, "Per-site constants"),
  loaded after ``baseline.css``, when the statement or the logo changes. This
  site uses the values shipped in ``baseline.css``, so there is no such file.
- Generated from the skill's own files: the Examples pairs
  (``references/examples.md``), the By channel lists
  (``references/context-modes.md``), the checklist (``references/qa-checklist.md``)
  and the Instructions block (``site/downloads/cleanlanguage.md``, exactly).

Every page loads ``scheme.js`` in ``<head>`` before the stylesheets, with
``data-cfasync="false"`` and no ``defer``, and ends ``header.mast`` with the
light and dark switch (``SCHEME_SWITCH``), as template specification 7.33
(baseline 1.6.0) requires.

The baseline files under ``<out>/assets/baseline/`` are copied and pinned by
``tools/copy-baseline.py`` and ``tools/check-baseline-pin.py``; this tool reads
them but never writes them.

Refusals (any one stops the build, exit 1)
-----------------------------------------

An unbalanced element (a closing tag with no open element, or an element left
open), content after the document grid ``.doc`` closes inside ``main``, or
tag text such as ``<code>`` shown inside a ``pre`` block (each a defect found
in the 1.2.1 reference demo page);
an en or em dash, as written or as a character reference; an inline
``style`` attribute or ``<style>`` element; an
inline executable ``<script>`` (a ``application/ld+json`` data block is
allowed, and emitted only at base ``/``); an ``on*`` attribute; an attribute
repeated on 1 tag, which a browser reads by its first value; "what this is"
framing in the text the parser reads; not exactly 1 ``h1``; a missing skip
link, ``main#main-content``,
family footer or ``#copy-status``; a duplicate ``id``; an unreplaced token; an
in-page fragment with no target; a root-relative link or asset outside the base
path that is not in ``root_allowlist``; a relative link; an external link
without ``target="_blank" rel="noopener noreferrer"`` and the "(opens in a new
tab)" text; a draft page, or a ``noindex`` page at base ``/``, without
exactly 1 ``noindex, nofollow`` robots meta, and an indexable page at base
``/`` with one; a JSON-LD block on a draft page or a ``noindex`` page; a page
of the ``/`` build with no ``modified`` date (and no ``--date``), or a date
that is not ``YYYY-MM-DD``; a page without exactly 1 light and dark switch
(``SCHEME_SWITCH``, exactly, as the last child of ``header.mast``, after
``nav.nav``, and the only element with a ``data-scheme-toggle`` attribute,
each of which ``scheme.js`` wires and shows), without exactly 1 ``scheme.js``
script tag before the first stylesheet, it and every stylesheet inside
``<head>``, or with any other ``<svg``; a page source, the landing page's
included, outside the page source grammar or tree rules below; a source with an
``html``, ``head``, ``body`` or ``frameset`` start tag (in any letter case or
self-closing), since the generator writes the page's html, head and body:
HTML5 copies a stray html or body start tag's attributes onto the page's own,
a stray head is refused because the generator writes the head, and
``tools/check-install-page.py`` reads a frameset start tag as hiding the whole
page; a page source with a ``math`` start tag, and a page with one as the
parser reads it, since inside ``<math>``, as inside ``<svg>`` (refused above),
a browser can read a ``title``, ``textarea``, ``script`` or ``style``
element's content as markup (``tools/check-inline-code.py`` refuses any
``math`` element too); a page source, the landing page's included, with
an element whose class names include ``about``, since the generator writes
the About block of template specification 7.24 (baseline 1.7.0) itself; a
landing page source without exactly 1 ``p.value``, or with that ``p.value``
inside an element of ``INERT_TAGS`` (which holds every element of
``tools/check-install-page.py``'s ``HIDING_ELEMENTS``), or hidden by itself or
by an ancestor as that gate's ``is_hiding_element()`` reads an element (a
``hidden``, ``inert`` or ``popover`` attribute in any value,
``aria-hidden="true"`` in any letter case, a class in its ``HIDING_CLASSES``,
an element of its ``HIDING_ELEMENTS``, or a ``dialog`` without ``open``), or
inside a ``details`` without ``open`` other than in its first ``summary``
child, as that gate's ``PageParser`` reads it, or with no ``div.region``
among its ancestors, or whose ``p.value`` holds anything outside its pin: an
element other than an ``a`` with no attribute but ``href`` or an ``em`` with
no attribute, a character of its text after NFC other than those of
``VALUE_SPACES`` (the ordinary space, U+0009, U+000A and U+000D, which a
browser collapses to a space, and U+00A0), ``VALUE_SIGNS`` (the visible
signs U+00A9, U+00AE, U+2122, U+2120 and U+00B0, the superscript digits, and
every vulgar fraction, each by name) and ``VALUE_CATEGORIES`` (letters
Lu, Ll and Lt, decimal digits, punctuation, and currency and math symbols), or
no letter (the pin leaves no element in the paragraph that could hide its
text, so no visible-text model applies there; it refuses Lo, which holds the
Hangul fillers, So and No outside ``VALUE_SIGNS`` (So holds U+2800), and
every other category, so the paragraph cannot be written in an uncased script such as
CJK, Arabic, Hebrew or Thai; NFC composes ``e`` and U+0301 into U+00E9, and
leaves a combining mark with no precomposed form, such as U+0301 after ``q``,
and an invisible one, such as U+034F or a variation selector, refused),
or whose value region (that ``div.region``) or an element inside it carries a
class name outside ``VALUE_REGION_CLASSES`` (``region``, ``lbl`` and
``value``, those the committed landing page uses there) or 1 of them away
from its place (in the landing page source, ``region`` only on the region,
``lbl`` only on its label and ``value`` only on the ``p.value``, since
``.region`` lays out an element as a grid), or whose value
region holds other than ``VALUE_REGION_CHILDREN``, in the landing page source
and, in ``validate()``, on the built landing page: exactly a ``p.lbl`` whose
text that shows (its text, not an ``img``'s alt text, which a browser shows
only when the image does not load, nor the folded content of a ``details``
without ``open``, which shows only once a reader opens it) holds a letter or a
digit, then the ``div`` that holds the
``p.value``, and no text other than whitespace directly (above 1000 px
``.region`` shows its first child in its label column, so a missing, moved,
repeated or hidden label, or a ``div`` closed before the ``p.value``, puts
the paragraph there; read from the stylesheet, not checked in a browser); a
page source with a
class name outside ``SOURCE_CLASSES`` (below); a page source with a
``hidden`` attribute whose value holds ``until-found`` in any letter case
(``UNTIL_FOUND``), since a browser shows such an element's content when
find-in-page matches text in it, where every rule here reads it as hidden (no
committed source uses it; ``validate()`` does not refuse it on a built page,
where only page sources and the generator's own markup, which carries none,
can put it); a page source with a bidi
formatting character (``BIDI_CONTROLS``: U+061C, U+200E, U+200F, U+202A to
U+202E and U+2066 to U+2069), as written or as a character reference, and a
page with one, since a browser reorders the text it shows around one, where
the label rule reads text in its stored order; a landing page whose output
lacks exactly 1 such ``p.value`` and, once and byte for byte, the whole About
block (``about_block()``: ``ABOUT_BLOCK``, the ``div.region`` with its label
and its ``div`` around the row ``about_line()`` gives, 1 ordinary space after
each dot span and none before it) directly after the end tag of that
paragraph's region, the ``div.region`` nearest it among its ancestors, with
no byte between the end of that end tag as the parser reads it (``</div>``,
its name in any ASCII letter case, then ASCII whitespace if any, before its
``>``, as the grammar's ``END_TAG`` admits) and the block, as the generator
writes them,
or whose region or About block has other ancestors, as the parser reads the
page, than exactly ``ABOUT_ANCESTORS`` (``html``, ``body``, ``main`` and
``div.wrap``), or that carries any other element whose class names include
``about``; any
other page with one; a page source whose text carries the About block's
label (``ABOUT_LABELS``: ``About this project`` or ``ABOUT THIS PROJECT``,
case-sensitive, in the text the parser reads, which it reads in upper case,
as a browser shows it, where the stylesheets show text so: in an element that
a selector of ``UPPERCASE_SELECTORS`` matches (the rules that set
``text-transform: uppercase`` in the stylesheets the pages load, such as
``.lbl`` and ``th``) unless one of ``RESET_SELECTORS`` (the rules that set it
back to ``none``, such as ``.lbl.file``) of higher specificity does, and in
the elements inside it that neither matches; there the label counts in any
letter case. The text is joined across elements, with
character references decoded and each ``img``'s ``alt`` text read as text in
its place (a browser shows it there when the image does not load) and also
left out (as when the image loads), and the folded content of each
``details`` without ``open`` (all but its first ``summary`` child) read both
shown (opened) and left out (closed), each image and details apart from the
others, the label counting in any such choice (``label_count()`` counts the
labels of 1 choice together and takes the most that any choice gives), each
character of general category Cf (format characters, such as the zero-width
and soft hyphen characters), each Default_Ignorable_Code_Point
(``DEFAULT_IGNORABLE``, such as U+034F, the variation selectors and the
Hangul fillers), each character of ``tools/check-install-page.py``'s
``ZERO_WIDTH`` other than U+00A0, and U+0000 deleted, then decomposed by NFKD
(a fullwidth or other compatibility letter reads as its Latin letter, an
accented letter as its letter and a mark), with each Latin small capital (a
character named ``LATIN LETTER SMALL CAPITAL`` and 1 letter, such as U+1D00)
read as that capital letter, and then every character other than a letter
or a digit, such as whitespace, punctuation, a mark or U+2800, deleted from
it and from the label, other attribute values and comments apart. It is read
3 times: whole, and twice with the
text of every element hidden as the value paragraph rule reads hiding
deleted, other than the folded content of a ``details`` without ``open``,
which each choice reads closed or opened, so a hidden element inside the label
does not split it and a details hides the label in neither state, first with
an element that only ``aria-hidden="true"`` hides kept, since that attribute
hides an element from assistive technology alone and a browser shows it,
then with it deleted too, as before; those 2 are each read again as a
browser with scripting off shows the page (``scripting_off()``), with the
content of each ``noscript`` kept, its hiding rules applying, since a
``noscript`` paragraph holding ``About``, a hidden span, then ``this
project`` built with exit 0 at 77823df; the label counts in any reading), a
landing page whose text carries it other than once, from inside the About
block, in each reading, and any other page whose text carries it; and a
release version that disagrees with SKILL.md. The page source grammar leaves
no element whose content the parser reads as text in a source, so on a page
only the generator's own elements in the head are read that way: the
``title``, the JSON-LD ``script``, and the empty ``script`` elements that
load ``scheme.js`` and the page's other scripts by ``src``. The About rules
read hiding from the
markup alone, as ``tools/check-install-page.py`` does: no stylesheet rule
other than a bare single class its ``HIDING_CLASSES`` lists (that gate's
tests fail when a stylesheet the pages load hides another bare single class).
Rather than model the others, the class pins hold the classes a source may
use: in the value region, ``VALUE_REGION_CLASSES``, and no rule of
``baseline.css`` 1.7.0 whose class parts are those, ``wrap`` and the site
class hides an element or positions one absolutely, other than those that
need the ``hidden`` attribute or one that ``SOURCE_ATTRIBUTES`` leaves out
(read from the stylesheet, not checked in a browser); elsewhere,
``SOURCE_CLASSES``, which
leaves out a class of each rule that sets ``display: none`` or clips an
element (such as ``.scheme .sun``, ``.figure .stack`` and ``.figure .wide``),
other than the rules that the hiding reader reads (``[hidden]`` and ``.vh``)
or that need an attribute ``SOURCE_ATTRIBUTES`` leaves out (such as
``[data-preset]``). Where ``SOURCE_CLASSES`` admits a class that a rule of
``baseline.css`` 1.7.0 uses to place an element out of its source order
(``copy``, ``btn``, ``entries``, ``t``, ``n``, ``d``, the hero's classes and
``start``), the placement pins (below) hold it to where the committed
sources use it, and ``rail_pin()`` keeps ``rail`` and ``rail-logo`` to the
rail the generator writes. The About block is pinned byte
for byte, so its classes are pinned too. The label rule joins text in source
order, and a page source holds at most 1 hero (``placement_pin()``), whose
text it also reads in its narrow-width order (at 600 px and below the hero
image sits in the kicker's row, before the statement), with the image's alt
text, ``site.json``'s ``logo_alt``, moved to the end of the kicker when the
first child of the ``div.hero-text`` is the kicker (a ``p.lbl``), and
otherwise to where the ``div.hero-text`` starts, so a label split between
``logo_alt`` and the kicker or the statement counts, with a kicker or without
one. Accepted residual of the threat model (editing mistakes, not deliberate
tricks), not modelled: a label formed through layout the generator does not
model. Its known members: text that a browser shows beside other text in
another grid column (the rail beside the text column above 1000 px, a label
column beside its content) counts only in source order, the hero's
narrow-width order apart; no rule reads a ``transform`` or a negative margin
that moves an element without reordering it (``.start:hover .arrow``,
``.code-note``, ``.verified``); and no rule reads a hiding selector with a
sibling combinator or of an element name alone (the label rule reads ``th``,
an element name alone, only as a selector that sets upper case), and none of
either kind sets ``display: none`` in ``baseline.css`` 1.7.0. The label
rule reads a tie
in specificity between an uppercase and a reset selector as upper case, and
an uppercase rule inside ``@media`` or ``@supports`` as always applying, so
it counts the label in any letter case in some text that a browser can show
as written, never the reverse. It compares code points after NFKD and the
small-capital reading, so a letter that looks like a Latin one but is
neither, such as a Cyrillic or Greek letter or U+0131 (a dotless i), keeps
the label from counting (a residual, not modelled).
The switch, its place and the
head are read as parsed elements: each element with ``data-scheme-toggle`` (an
attribute name in any letter case), the switch's parent, the element before it
and the end of its parent, and ``html > head``, the first head or body the page
opens. As in a browser, a self-closing tag leaves an element that is neither
void nor in ``<svg>`` open, class names split on ASCII whitespace only
(``class="mast&nbsp;x"`` is not ``mast``), and the head ends at the first text
other than whitespace, start tag other than those HTML5 allows in a head
(``HEAD_TAGS``), or ``</body>``, ``</html>`` or ``</br>``; a script or
stylesheet after that point is outside it. No element with
``data-scheme-toggle`` may sit inside an element whose content a browser with
scripting on, the only case in which ``scheme.js`` runs, does not render as
page elements (``INERT_TAGS``: ``noscript``, ``template``, ``plaintext``, the
raw-text and RCDATA elements, and the elements ``tools/check-install-page.py``
hides for that reason, ``audio``, ``canvas``, ``datalist``, ``meter``,
``object``, ``progress``, ``rp``, ``select`` and ``video``, whose content a
browser renders only as fallback, only in its control or not at all, so for
an element that a browser also places inside one, this refuses at least what
a browser hides); a script or stylesheet inside one is not in
``html > head``, and an ``h1``, a robots meta, the skip link,
``main#main-content``, the family footer, ``#copy-status`` or the landing
page's value paragraph inside one fails, as does a fragment whose only target
is inside one. The reading fails closed where it does not model HTML5: such a
start tag inside a ``<template>`` or ``<noscript>`` in the head ends the head,
and a self-closing tag in ``<math>`` leaves its element open. It is not a full
HTML5 tree builder, so each page must also carry, once and byte for byte, the
markup from the body start tag to the end of ``header.mast`` as the generator
writes it: ``<body>``, the skip link and the header block ``MAST_BLOCK`` pins
with the values from ``site-src/site.json``, each on its own line. That
``<body>`` must be the page's first body, parsed as a child of ``html`` right
after its only head closes (whitespace and comments apart), before the head
ends. As far as the parsed reading models HTML5, no element can then wrap the
header, nor precede it in the body other than the skip link, and a change to
``mast()`` or to the lines around it that alters that markup fails. That pin
covers neither the head nor anything after ``header.mast``, which only the
parsed reading checks (and, on the landing page, the About block pin), and it
is only as right as ``MAST_BLOCK``, ``SKIP_LINK`` and ``SCHEME_SWITCH``: a
change to one of them made together with the same change to the generator
passes. The About block pin is only as right as ``ABOUT_BLOCK`` and
``about_line()``, from which the generator both writes and checks the block,
so a change to either alone passes it; ``tools/test-build-site.py`` reads the
block apart from them, from section 7.24 of the pinned template's
``SPECIFICATION.md`` (``.baseline/SPECIFICATION.md``, checked against
``.baseline/SHA256SUMS``). What guarantees the committed
pages is ``--check``, a deploy gate, which compares them byte for byte with a
fresh build that passed these refusals.

Page source grammar
-------------------

The rules above read a page as Python's parser reads it, and that parser and a
browser tokenize some markup differently (comment openers such as ``<!-->``, a
CDATA section, a noscript element's text with scripting on, a script's escape
states). So each page source, as ``with_about()`` reads it with its tokens and
rail written in, is held to a small grammar on which the two agree
(``SOURCE_TOKEN``), and anything outside it is refused, wherever it sits:

- text holds no ``<`` (it writes ``&lt;``), so a ``<`` begins only a start
  tag, an end tag or a comment;
- a comment's text holds no ``<``, no ``>`` and no ``--``, so ``<!-->``,
  ``<!--->`` and ``--!>`` cannot occur;
- a start tag holds only attributes separated by ASCII whitespace, with ASCII
  whitespace allowed around an attribute's ``=``, and no attribute value holds
  ``<`` or ``>`` (an unquoted one holds only ASCII letters, digits and
  ``_.:-``); an end tag holds only its name, then ASCII whitespace if any;
- a start tag names an element of ``SOURCE_ELEMENTS`` (in any letter case),
  the elements the committed sources use as ``with_about()`` reads them, and
  no ``noscript`` starts inside a ``noscript``;
- each attribute name is one of ``SOURCE_ATTRIBUTES`` (in any letter case),
  the names the committed sources use as ``with_about()`` reads them;
- an end tag names an element of ``SOURCE_ELEMENTS`` (in any letter case), so
  no source carries ``</br>``;
- no element of ``RAW_TEXT_TAGS``, whose content a browser reads as raw or
  escapable raw text (script, style, textarea, title, xmp, iframe, noembed,
  noframes, plaintext) or does not render (template), no ``math``, no CDATA
  section, no processing instruction and no DOCTYPE (each of these elements is
  also outside ``SOURCE_ELEMENTS``, and is refused with its own message).

Why the two then agree: outside raw text, foreign content and the constructs
refused above, a browser's tokenizer stays in its data state, where it ends
text only at ``<``, reads ``<`` and a letter as a tag, ``</`` and a letter as
an end tag and ``<!--`` as a comment; a tag then ends at the first ``>``
outside a quoted value, and a comment whose text holds no ``--`` or ``>`` at
the first ``-->``. With no ``<`` in text, no ``<`` or ``>`` in a value or a
comment and no raw-text element, there is no other place a token can end or
begin, so the parser, which splits markup at the same characters, reads the
same tokens. ASCII whitespace around an attribute's ``=`` or before an end
tag's ``>`` begins or ends no token: a browser's tokenizer skips it in its
after attribute name, before attribute value and before attribute name
states, and Python 3.14.4's parser skips it there too (``class = "value"``
reads as ``class="value"``, ``</p >`` as ``</p>``). There is 1 deliberate
exception: the content of a noscript element,
which a browser with scripting on reads as text up to the first
``</noscript``, and the parser reads as elements. The rules stay safe for it.
They read everything inside a noscript as not rendered, so nothing there can
meet a rule that needs a rendered element, apart from the label rule's
readings with scripting off, in which a browser reads that content as
elements, as the parser does (``scripting_off()``); and under these rules
the first ``</noscript`` after a noscript start tag is that element's own
end tag, the one the parser reads as closing it on a page ``validate()``
accepts, since no ``<`` sits in text, a comment or an attribute value and no
noscript starts inside another. A noscript inside a noscript was allowed
before: with scripting on, a browser ended the outer one at the inner one's
end tag, so a later ``</summary>`` closed a summary the parser read as still
open, and the value paragraph and the About block after it became hidden
children of a closed details while every rule passed.

The generator's own readers then read what the parser reads. Every rule that
reads elements, attributes or text of a page source reads them from 1 parser
class, ``PageScan``, with its self-closing and end-tag handling: the rules of
``with_about()``, the class and placement pins, ``rail_pin()``, and
``rail()``, whose entries are the ``h2`` elements with an ``id`` as
``PageScan`` reads them, their text without that of a ``span.num`` (a regex
over the markup before DISCOVERY round 7, which dropped ``<h2 id = "try">``
and ran an ``</h2 >`` heading's entry into the prose). ``validate()`` reads a
page with ``PageScan`` too, and reads "what this is" in its text; it finds the
end of the value region's end tag where the parser read that tag
(``end_tag_end()``), as ``with_about()`` does. The other reads of markup are
not parses, and each reads at least what the parser reads or only markup the
generator writes: ``source_problem()`` is the grammar; ``bidi_control()`` and
the dash refusal read every character, with character references decoded by
``html.unescape()``; the count and replacement of ``<!--rail-->``, a comment
token wherever the grammar admits the string; ``validate()``'s byte pins (the
header block, the switch, the required blocks, the ``scheme.js`` tag and the
About block), each also held to where the parser reads that element start;
its counts of ``<svg`` and ``scheme.js``; and its search for
``aria-current="true"``, an attribute no page source may carry.

``SOURCE_ELEMENTS`` admits only the elements the committed sources use, which
keeps out ``select`` and ``input``: under legacy select parsing, a browser
ends an open ``select`` at a nested ``select`` or an ``input`` and places what
follows outside it, where the parser reads it as still inside, which moved
the value paragraph out of the summary of a closed details. The list settles
which elements a source may carry; the tree rules below settle where. An
element is added only after a review of its parsing rules and of those rules.

``SOURCE_ATTRIBUTES`` admits only the attribute names the committed sources
use (``alt``, ``aria-hidden``, ``aria-label``, ``class``, ``data-copy``,
``hidden``, ``href``, ``id``, ``rel``, ``src``, ``tabindex``, ``target`` and
``type``; no ``details`` carries any). What a browser does with an attribute
is open-ended: in a ``details`` name group it closes all but 1 open member,
so a value paragraph inside a later open member was hidden while every rule
passed. The rules model ``hidden``, ``aria-hidden`` and ``class`` (as
``tools/check-install-page.py`` reads hiding, stylesheet rules apart, as
above); by the HTML Standard's rules, the others admitted neither hide nor
move an element; only ``data-copy`` makes a loaded script show an element:
``copy.js`` shows every ``button`` with ``data-copy`` whose value names an
element and, on a copy, replaces its content with plain text, so
``placement_pin()`` holds it to the committed copy button (below). An
attribute is added only after a review of what it makes a browser do.
``open`` stays out (accepted residual, refused, not modelled): the rules read
a details with ``open`` as opened only, where a reader can close it, so once
``open`` was admitted, a label that shows only on closing and a value
paragraph in its folded content each built with exit 0 (a probe on 77823df),
and an ordinary ``<details open>`` is refused.

``SOURCE_CLASSES`` admits only the class names the committed sources use, as
``with_about()`` reads them, and in the landing page's value region only
``VALUE_REGION_CLASSES`` (``region``, ``lbl`` and ``value``). A stylesheet
rule can hide or move an element by a class it names, which the rules do not
read apart from the hiding reader's bare single classes: a ``div.figure`` and
a ``div.stack`` around the value paragraph (the descendant selector
``.figure .stack`` sets ``display: none``), or ``copy`` on it (the
single-class selector ``.copy`` sets ``position: absolute``), built with exit
0, and so did a ``span.sun`` that hid a character splitting the label in a
``p.lbl.scheme`` (the descendant selector ``.scheme .sun``). Both pins are
checked after the other source rules, and name where the start tag starts. A
class name is added only after a review of what each stylesheet rule that
names it does. In the value region each of the 3 also has 1 place, after
the region's children rule: ``region`` only on the region, ``lbl`` only on
its label and ``value`` only on the ``p.value``. ``.region`` lays out an
element as a grid of a label column and a content column, so
``class="value region"`` on the value paragraph, alone or with its content
in an ``em``, built with exit 0 at 9134d0b (the grid read from the
stylesheet, not checked in a browser).

Page source placement
---------------------

Some admitted classes are safe only where the committed sources use them: a
rule of ``baseline.css`` 1.7.0 places an element that carries one out of its
source order, so a browser can show text that the label rule reads apart as
joined. ``.copy`` and ``.btn`` set ``position: absolute`` (``.btn.inline``
sets it back to ``static``); ``.hero``, ``.hero-text``, ``.hero-art``,
``.statement``, ``.hero .intro``, ``.hero .lbl`` and ``.start`` place the
hero's parts by grid area (at 600 px and below ``.hero-text`` sets
``display: contents``, so its children are placed by area); and at 1000 px
and below ``.entries a`` places its ``.t``, ``.n`` and ``.d`` children by
grid area. Built with exit 0 at c22c9dd: the label split by a ``span.btn``
in a ``p.lbl`` on the landing page, or by a ``span.copy`` on the demo page,
and an ``ol.entries`` link whose ``span.d`` came before its ``span.t``. After
the class pins, ``placement_pin()`` refuses, naming where the start tag
starts:

- a class of ``PLACED_CLASSES`` on another element, without its companion
  classes or attributes, under another parent, or (``copy``) after text or
  an element in its parent: ``copy`` only on a ``button`` with ``hidden``
  first in a ``pre.hascopy``, which the hiding reader reads as hidden, so the
  label rule joins the text around it; ``btn`` only on an ``a`` that also
  carries ``inline``; ``entries`` only on an ``ol``; ``t`` and ``d`` only on
  a ``span`` in an ``a``, and ``n`` in an ``a`` or an ``li``; ``hero`` only
  on a ``section`` at the top of the source, ``hero-text`` and ``hero-art``
  only on a ``div`` in it; ``statement``, ``intro`` and ``start`` only on an
  ``h1``, a ``p`` and an ``a`` in the ``div.hero-text`` (``start`` also in a
  ``div.next``, which is not a grid);
- a ``section.hero``, ``div.hero-text`` or ``div.hero-art``, or an ``a``
  inside an ``ol.entries``, with text other than whitespace directly in it,
  or with children outside their committed order (``PLACED_CHILDREN``: the
  text, then the art; the kicker, statement, intro and start link; the
  image; the ``span.t``, ``span.n`` and ``span.d``), each at most once, so a
  browser shows them in source order;
- a second ``section.hero``: the label rule reads the narrow-width order of
  1 hero, the first;
- a ``data-copy`` attribute other than on a ``button.copy`` (so with
  ``hidden``, first in a ``pre.hascopy``) whose value is that pre's ``id``
  and whose content is only the text ``Copy``, as the committed sources
  write it (``COPY_BUTTON_PIN``): ``copy.js`` selects every
  ``button[data-copy]``, shows it and, on a copy, replaces its content with
  plain text, whatever its classes, so at 77823df a hidden, unclassed button
  with ``data-copy`` holding ``About``, a hidden span, then ``this project``
  (a second label once the script runs), and the value paragraph wrapped in
  such a button (its markup lost on a copy), built with exit 0;
- an image in the ``div.hero-art`` whose alt text is not ``site.json``'s
  ``logo_alt``, which ``build()`` passes to ``with_about()`` (without it, any
  such image is refused): at 600 px and below a browser shows the image in
  the kicker's row, beside the kicker if the hero has one, before the
  statement.

``build()`` also refuses, through ``rail_pin()``, a page source that carries
``rail`` or ``rail-logo`` itself, or more than 1 ``<!--rail-->``: above
1000 px ``.doc > .rail`` shows the rail at the top of the third column,
wherever it sits in the source, and the rail ``rail()`` writes starts with
the logo, whose alt text is ``logo_alt``.

Page source tree
----------------

The parser reads tags as they nest, and a browser's tree builder (the HTML
Standard's tree-construction rules) closes or moves some of the admitted
elements where they are written. So, as the parser reads the open elements
(``misnested()``), a page source opens a ``summary`` only as the first element
child of a ``details``, with no element before it there, so the parser and a
browser agree on which summary a details without open shows; and refuses,
with a message naming where it starts:

- a start tag of ``P_CLOSERS`` (``details``, ``div``, ``h1``, ``h2``, ``h3``,
  ``li``, ``nav``, ``ol``, ``p``, ``pre``, ``section``, ``summary``,
  ``table``, ``ul``) inside an open ``p`` with no ``button``, ``caption``,
  ``table``, ``td`` or ``th`` between them, where a browser ends the ``p``;
- a heading start tag directly inside an open heading, which a browser ends;
- an ``li`` start tag inside an open ``li`` with only ``LI_THROUGH``
  elements between them, where a browser ends the open ``li`` and what it
  holds;
- an ``a`` inside an open ``a``, or a ``button`` inside an open ``button``,
  where a browser ends the open one;
- in a ``table`` any child other than ``caption``, ``thead`` and ``tbody``,
  in a ``thead`` or ``tbody`` any child other than ``tr``, in a ``tr`` any
  child other than ``td`` and ``th`` (``TABLE_CHILDREN``), and text other
  than whitespace directly in any of them, which a browser moves to before
  the table (foster parenting), or inserts a ``tbody`` around; and a table
  part (``TABLE_PARTS``) anywhere else, whose start tag a browser ignores;
- a child of a ``table`` after a later one in ``TABLE_ORDER`` (``caption``,
  then ``thead``, then ``tbody``), or a second ``caption`` or ``thead``: a
  browser shows a table's captions first and its first ``thead`` before its
  ``tbody`` elements, whatever their order in the source (no stylesheet the
  pages load sets ``caption-side``), so the label rule reads a table's text
  in the order it shows;
- a ``summary`` start tag after text other than ASCII whitespace directly in
  its ``details``: a browser shows a details' first summary before the rest
  of its content, opened or closed, so the label rule reads a details' text
  in the order it shows, its folded content as 1 run after the summary.

Why that suffices (an argument from the standard's rules, not checked in a
browser): with these refused, the parser's open elements and a browser's are
the same at every token of a balanced source, for the admitted elements. A
start tag of ``P_CLOSERS`` finds no ``p`` to end, a heading or an ``li`` none
to end, an ``a`` or a ``button`` no open one, and a table part's child is one
the browser keeps where written; so each start tag inserts its element as a
child of the same current element, and each end tag, which the parser
requires to close its current element, closes the same one in a browser. No
element is then closed early, so no formatting element is left to be
reopened with its attributes elsewhere. The two read the same tree, and so
the same ancestors, hiding attributes and first summary for every element.
The tree rules read the source alone, which the generator writes inside
``main`` and a ``div`` with no ``p``, ``li``, heading, ``a``, ``button`` or
table part open around it, on a page with a DOCTYPE, so no quirks-mode rule
applies. ``noscript`` is the exception the grammar names: a browser with
scripting on reads its content as text, which the rules read as not
rendered (with scripting off, a browser reads it as elements, as the parser
does, and the label rule reads it so too). One difference remains that
places no element elsewhere: a browser drops a line feed that is the next
token after a ``pre`` start tag. The placement pins read it as a browser
does (``PageScan`` leaves it out of what they read, so a ``button.copy``
after it still comes first in its ``pre``); the other rules read it as text,
which the label rule deletes as whitespace. The
grammar refuses ``</br>``, which a browser reads as a ``br`` start tag (and,
directly inside a ``table``, ``thead``, ``tbody`` or ``tr``, moves to before
the table), where the parser ignores it.

The source is checked before the generator writes the About block in, so
the built landing page is not inferred from these rules alone: ``validate()``
requires its value region and the About block to have exactly the ancestors
``ABOUT_ANCESTORS`` (``html``, ``body``, ``main`` and ``div.wrap``), as the
parser reads the built page. Why a browser then places both there too (an
argument, not checked in a browser): the generator writes ``main`` and
``div.wrap`` around the source, after the pinned body start and header
block; inside them, the open elements are the same in both at every token of
the source, as above, so at the region's start tag and at the block's, a
browser's open elements are the parser's 4, and it inserts each as a child of
``div.wrap``. No ``a`` or other formatting element is open there, and each
closed one was closed by its own end tag, so none is reopened around the
block's links; the block itself is balanced and obeys the tree rules.

Decoding is left to the parser. Python 3.14.4, which ``.python-version``
pins, leaves a legacy named character reference without ``;`` undecoded in
an attribute value before ``=`` or an ASCII letter or digit (``&notx`` stays
as written) and decodes it in text (``&notx`` reads as U+00AC and ``x``), as
the HTML Standard's named character reference state does; a parser that
decodes otherwise can read a class name or the About label that a browser
does not.

Threat model: these rules catch editing mistakes in the repository's own
sources. A source written to exploit a parser difference outside this grammar
is refused by the grammar, not modelled, and ``tools/check-inline-code.py``
remains the deploy gate for scripts and math on the built pages.

Modes
-----

    python3 -I tools/build-site.py            write the configured base path's output
    python3 -I tools/build-site.py --check    regenerate in memory and compare byte for byte
    python3 -I tools/build-site.py --out DIR [--base B] [--date YYYY-MM-DD]
                                             render into DIR instead (tests); --date
                                             replaces every page's modified date

``--check`` fails on any missing, extra or different file under the output
folder outside ``assets/baseline/``, on any file there that is neither
generated nor listed in ``static_files`` (at ``site/`` only), on a listed static
file that is missing, and on any internal link that does not resolve to a
generated page, a generated anchor, a pinned baseline file or an allowlisted
root file. Writing a ``--base /`` override into ``site/`` while
``site-src/site.json`` names another base needs ``--promote``, so a promotion
cannot happen by accident before the owner approves; once the configured base
is ``/``, a plain run writes ``site/``. The build never deletes a stale file at
``site/``; remove an old page with ``git rm``.

Exit codes:
  0  written, or the check passed
  1  a refusal, a drift or an unresolved link
  3  an input could not be read or is malformed
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import tomllib
import html
import json
import os
import re
import stat
import sys
import types
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = Path("site-src")
SKILL = Path("cleanlanguage/skills/cleanlanguage/SKILL.md")
REFS = Path("cleanlanguage/skills/cleanlanguage/references")
DOWNLOADS = Path("site/downloads")
REPO_SLUG = "jposluns/cleanlanguage"

SKILL_VERSION = re.compile(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$")
TOKEN = re.compile(r"\{\{([a-z0-9_.:-]+)\}\}")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
# 1 end tag as the page source grammar admits it (SOURCE_TOKEN): its name, then ASCII whitespace if any.
END_TAG = re.compile(r"</[a-zA-Z][a-zA-Z0-9]*[ \t\n\f\r]*>")
NEW_TAB = "<span class=\"vh\"> (opens in a new tab)</span>"
EXECUTABLE_TYPES = {"", "module", "text/javascript", "application/javascript", "text/ecmascript"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# The start tags HTML5 allows in a head; any other start tag ends it, as text other than whitespace does.
HEAD_TAGS = {"base", "basefont", "bgsound", "link", "meta", "noframes", "noscript", "script", "style", "template", "title"}
# The elements whose content a browser with scripting on (the only case in which scheme.js runs) does not render
# as page elements (noscript, template, plaintext, the raw-text and RCDATA elements) or renders only as fallback,
# only in its control or not at all (the other elements of tools/check-install-page.py's HIDING_ELEMENTS: audio,
# canvas, datalist, meter, object, progress, rp, select and video). No switch counts as placed inside one.
INERT_TAGS = {"noscript", "template", "script", "style", "title", "textarea", "xmp", "iframe", "noembed", "noframes", "plaintext",
              "audio", "canvas", "datalist", "meter", "object", "progress", "rp", "select", "video"}
# HTML separates class names by ASCII whitespace only; str.split() also splits on U+00A0 and other spaces.
ASCII_WHITESPACE = re.compile(r"[ \t\n\f\r]+")
# The page source grammar (module docstring): 1 token of a page source, on which Python's parser and a browser read
# the same markup. Text holds no <; a comment's text holds no <, > or --; an end tag holds only its name, then ASCII
# whitespace if any; a start tag holds attributes separated by ASCII whitespace, with ASCII whitespace allowed around
# an attribute's =, each value quoted with no < or > in it, or unquoted of ASCII letters, digits and _.:- only.
SOURCE_TOKEN = re.compile(
    r"(?P<text>[^<]+)|<!--(?:[^<>-]|-(?!-))*-->|</(?P<end>[a-zA-Z][a-zA-Z0-9]*)[ \t\n\f\r]*>"
    r"|<(?P<start>[a-zA-Z][a-zA-Z0-9]*)(?:[ \t\n\f\r]+[a-zA-Z][a-zA-Z0-9_.:-]*(?:[ \t\n\f\r]*=[ \t\n\f\r]*"
    r"""(?:"[^"<>]*"|'[^'<>]*'|[a-zA-Z0-9_.:-]+(?=[ \t\n\f\r>])))?)*[ \t\n\f\r]*/?>"""
)
# The elements no page source may carry because a browser reads their content as raw or escapable raw text, which the
# parser need not read alike, or (template) does not render it; and the start tags the generator writes for each page.
RAW_TEXT_TAGS = {"script", "style", "template", "textarea", "title", "xmp", "iframe", "noembed", "noframes", "plaintext"}
DOCUMENT_TAGS = ("html", "head", "body", "frameset")
# The only elements a page source may carry (module docstring, "Page source grammar"): those the committed sources
# use, as with_about() reads them (rail() writes nav). Adding an element is a deliberate change: review first how a
# browser's tree builder places it and what follows it (as at select and input, which end an open select), against
# the rules that read the parsed page.
SOURCE_ELEMENTS = {"a", "button", "caption", "code", "details", "div", "em", "h1", "h2", "h3", "img", "li", "nav",
                   "noscript", "ol", "p", "pre", "section", "small", "span", "strong", "summary", "table", "tbody", "td",
                   "th", "thead", "tr", "ul"}
# The only attribute names a page source may carry, in any letter case (module docstring, "Page source grammar"): those
# the committed sources use, as with_about() reads them; no details carries any. Adding one is a deliberate change:
# review first what it makes a browser do (as at a details name group, where a browser closes all but 1 open member),
# against the rules that read the parsed page.
SOURCE_ATTRIBUTES = {"alt", "aria-hidden", "aria-label", "class", "data-copy", "hidden", "href", "id", "rel", "src",
                     "tabindex", "target", "type"}
# The only class names a page source may carry (module docstring, "Page source grammar"): those the committed sources
# use, as with_about() reads them. A stylesheet rule can hide or move an element by a class it names, in a descendant
# selector (.scheme .sun and .figure .stack set display: none) or alone (.copy sets position: absolute; PLACED_CLASSES
# pins it), which the rules do not read apart from the hiding reader's bare single classes. Adding one
# is a deliberate change: review first what each stylesheet rule that names it does, against the rules that read the
# parsed page.
SOURCE_CLASSES = {"accent", "after", "arrow", "before", "blk", "btn", "callout", "clause", "clauses", "code-note",
                  "copy", "d", "described", "doc", "download", "entries", "file", "first", "gold", "hascopy", "hero",
                  "hero-art", "hero-text", "inline", "intro", "lbl", "lead", "meta", "n", "next", "num", "pair", "plan",
                  "prompt-flow", "rail", "rail-logo", "region", "sec", "size", "start", "statement", "steps", "sum",
                  "t", "tablewrap", "value", "verified", "vh", "wide"}
# The only class names that the landing page source's value region (the div.region nearest its p.value) and the
# elements inside it may carry: those the committed landing page uses there. No rule of baseline.css 1.7.0 whose class
# parts are these, wrap and site.json's site_class hides an element or positions one absolutely, other than those that
# need the hidden attribute, which the hiding reader reads, or an attribute that SOURCE_ATTRIBUTES leaves out; .copy,
# which SOURCE_CLASSES admits, sets position: absolute. Each has 1 place there (PageScan.region_class_problem()):
# region only on the region, lbl only on its label and value only on the p.value, since .region sets display: grid.
VALUE_REGION_CLASSES = {"region", "lbl", "value"}
# The children of the landing page's value region, as the committed landing page orders them, in PLACED_CHILDREN's
# form: above 1000 px .region places its first child in its label column (--label-col, 9rem) and its second in its
# content column, so a value paragraph that came first would sit in the label column. Each slot
# is filled exactly once, the p.lbl's text that shows holds a letter or a digit, the div holds the p.value, and the
# region holds no text other than whitespace directly (PageScan.region_problem()).
VALUE_REGION_CHILDREN = (("p.lbl",), ("div",))
# The refusal of a value region outside VALUE_REGION_CHILDREN (PageScan.region_problem() names what it holds).
VALUE_REGION_PIN = ("the grid of .region shows its first child in the label column, so it holds only a p.lbl with "
                    "text that shows, then the div that holds the p.value, and no text (VALUE_REGION_CHILDREN)")
# The page source placement pins (module docstring, "Page source placement"): each class name of SOURCE_CLASSES that a
# rule of baseline.css 1.7.0 uses to place an element out of its source order (.copy and .btn set position: absolute;
# the grid areas of .hero, .hero-text, .hero-art, .statement, .hero .intro, .start and, at 1000 px and below,
# .entries .t, .n and .d), pinned to where the committed sources use it, as (element, companion classes it needs,
# parents, attributes it needs, whether it comes first in its parent). A parent is "*" for any, "" for none (the top
# level of the source), or an element name with at most 1 class name it carries. .btn.inline sets position: static.
PLACED_CLASSES = {
    "copy": ("button", (), ("pre.hascopy",), ("hidden",), True),
    "btn": ("a", ("inline",), ("*",), (), False),
    "entries": ("ol", (), ("*",), (), False),
    "t": ("span", (), ("a",), (), False),
    "n": ("span", (), ("a", "li"), (), False),
    "d": ("span", (), ("a",), (), False),
    "hero": ("section", (), ("",), (), False),
    "hero-text": ("div", (), ("section.hero",), (), False),
    "hero-art": ("div", (), ("section.hero",), (), False),
    "statement": ("h1", (), ("div.hero-text",), (), False),
    "intro": ("p", (), ("div.hero-text",), (), False),
    "start": ("a", (), ("div.hero-text", "div.next"), (), False),
}
# The refusal of a data-copy attribute outside the copy button as the committed sources write it (placement_pin()):
# copy.js shows every button with data-copy whose value names an element, which the rules read as hidden, and on a
# copy replaces its content with plain text, so the attribute sits only on a button.copy (PLACED_CLASSES: with hidden,
# first in a pre.hascopy) whose value is that pre's id and whose content is only the text Copy.
COPY_BUTTON_PIN = ("copy.js shows every button with data-copy and replaces its content on a copy, so a page source "
                   "carries it only on a button.copy with hidden, first in a pre.hascopy whose id is its value, "
                   "holding only the text Copy (COPY_BUTTON_PIN)")
# The children of the elements whose grid template places them by area, as the committed sources order them: for the
# element with each class name (for entries, each a inside it), the slots in order, each the element and class names
# (sorted) that may fill it. Each slot is filled at most once, and the element holds no text other than whitespace,
# which a browser would place as an anonymous grid item after the named areas.
PLACED_CHILDREN = {
    "hero": (("div.hero-text",), ("div.hero-art",)),
    "hero-text": (("p.gold.lbl", "p.lbl"), ("h1.statement",), ("p.intro",), ("a.start",)),
    "hero-art": (("img",),),
    "entries": (("span.t",), ("span.n",), ("span.d",)),
}
# The class names only rail() writes, at the page source's <!--rail-->: .doc > .rail sets grid-row: 1 / span 200 in
# the third column, above 1000 px, which shows the rail at the top whatever its place in the source.
RAIL_CLASSES = {"rail", "rail-logo"}
# The bidi formatting characters, which reorder the text a browser shows around them (U+202E shows the text after it
# reversed): U+061C, U+200E, U+200F, U+202A to U+202E and U+2066 to U+2069. No page source or page may carry one,
# as written or as a character reference, since the label rule reads text in its stored order.
BIDI_CONTROLS = "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
# 1 attribute of a start tag that SOURCE_TOKEN matched, with the whitespace before it and around its =; group 1 is its
# name.
SOURCE_ATTRIBUTE = re.compile(r"""[ \t\n\f\r]+([a-zA-Z][a-zA-Z0-9_.:-]*)"""
                              r"""(?:[ \t\n\f\r]*=[ \t\n\f\r]*(?:"[^"]*"|'[^']*'|[a-zA-Z0-9_.:-]+))?""")
# The page source tree rules (module docstring, "Page source tree"): the source elements whose start tag ends an open p
# in button scope in a browser, the elements that end that scope, the elements an li start tag looks through for an
# open li, the headings, and the children a browser keeps where they are written in each table part.
P_CLOSERS = {"details", "div", "h1", "h2", "h3", "li", "nav", "ol", "p", "pre", "section", "summary", "table", "ul"}
BUTTON_SCOPE = {"button", "caption", "table", "td", "th"}
LI_THROUGH = {"a", "code", "div", "em", "p", "small", "span", "strong"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
TABLE_CHILDREN = {"table": {"caption", "thead", "tbody"}, "thead": {"tr"}, "tbody": {"tr"}, "tr": {"td", "th"}}
TABLE_PARTS = {"caption", "thead", "tbody", "tr", "td", "th"}
# The order in which a browser shows a table's children, whatever their order in the source: its caption first, then
# its first thead, then its tbody elements (no stylesheet the pages load sets caption-side). A table holds them in that
# order, at most 1 caption and 1 thead (PageScan.table_ranks), so the label rule reads them in the order they show.
TABLE_ORDER = ("caption", "thead", "tbody")
# The refusal of a summary after text in its details: a browser shows a details' first summary before the rest of its
# content, so the label rule, which reads text in source order, reads a details' folded content as 1 run after it.
SUMMARY_ORDER_PIN = ("a browser shows a details' summary before the rest of its content, so a page source writes no "
                     "text other than ASCII whitespace in a details before its summary")
# The refusal of hidden="until-found": a browser shows such an element's content when find-in-page matches text in it,
# where the rules read it as hidden (tools/check-install-page.py's is_hiding_element() reads hidden in any value).
UNTIL_FOUND = ("a browser shows the content of an element with hidden=until-found when find-in-page matches text in "
               "it, where the rules read it as hidden, so a page source carries no hidden attribute with that value")
TABLE_ORDER_PIN = ("a browser shows a table's caption first and its thead before its tbody, whatever their order in "
                   "the source, so a table holds at most 1 caption, then at most 1 thead, then its tbody elements "
                   "(TABLE_ORDER)")
SKIP_LINK = '<a class="skip" href="#main-content">Skip to content</a>'
COPY_STATUS = '<p class="vh" id="copy-status" role="status" aria-live="polite"></p>'
# The light and dark switch of template specification 7.33 (baseline 1.6.0), byte for byte as in the
# reference pages (reference/install.html line 18): the last child of header.mast on every page. Its 2
# glyphs are the only inline <svg> elements a page may carry; tools/check-inline-code.py admits exactly
# this string, once.
SCHEME_SWITCH = (
    '<button class="scheme" type="button" data-scheme-toggle aria-pressed="false" hidden>'
    '<svg class="moon" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7z"/></svg>'
    '<svg class="sun" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="4.2"/>'
    '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/>'
    '</svg><span class="vh">Dark mode</span></button>'
)
# The header block as mast() is meant to write it, held apart from mast() so that validate() refuses a change to
# either that the parsed reading misses: the markup is pinned here, and only the values come from site.json (the
# base path, name, tld, GitHub URL and nav pages, with aria-current on the page's own entry).
MAST_BLOCK = (
    '<header class="mast"><a class="brand" href="{base}"><span class="name">{name}<span class="tld">{tld}</span></span>'
    '<span class="rule" aria-hidden="true"></span></a><nav class="nav" aria-label="Site">{items}'
    '<a href="{github}" target="_blank" rel="noopener noreferrer">GitHub<span class="vh"> (opens in a new tab)</span></a>'
    "</nav>{switch}</header>"
)
MAST_ITEM = '<a href="{href}"{current}>{label}</a>'
# The dot between 2 links of the About row of template specification 7.24 (baseline 1.7.0); about_line() gives the row.
ABOUT_DOT = '<span class="dot" aria-hidden="true">&middot;</span>'
# The whole About block of specification 7.24 (baseline 1.7.0), byte for byte as SPECIFICATION.md section 7.24 gives
# it: the region, its label and the div around the About row, which about_line() gives. The generator writes it on the
# landing page only, directly after the end tag of the value paragraph's region, and validate() requires it there once.
ABOUT_BLOCK = '<div class="region"><p class="lbl">About this project</p><div>{row}</div></div>'
# The ancestors, outermost first, of the landing page's value region and of the About block, as (name, classes), as
# the parser reads the committed page: html (with site.json's site_class), body, main#main-content and div.wrap, which
# the generator writes. validate() requires exactly these for both, so no element can wrap either.
ABOUT_ANCESTORS = (("html", "{site_class}"), ("body", ""), ("main", ""), ("div", "wrap"))
# The About block's label, as written and in upper case: the text of a page source carries neither, and the text of
# the landing page carries 1, inside the block (PageScan.labels() counts them).
ABOUT_LABELS = ("About this project", "ABOUT THIS PROJECT")
# Each selector of a rule that sets text-transform: uppercase in the stylesheets every page loads (baseline 1.7.0's
# fonts.css, palettes.css and baseline.css, and site-src/assets/site.css when it exists), as written there, and each
# selector of a rule outside any at-rule that sets it to none (RESET_SELECTORS): a browser shows the text of an
# element in upper case when an uppercase selector matches it and no reset selector of higher specificity does, or,
# when neither matches it, when its parent's text shows so (uppercase_here()). PageScan reads that text in upper case,
# and the label rule counts the label there in any letter case. A tie in specificity reads as upper case, which
# counts at least what a browser shows. Each selector is compound selectors, each a name or *, then .class parts, or
# .class parts alone, joined by descendant or child (>) combinators (selector_matches() reads no other syntax).
# tools/test-build-site.py fails when the stylesheets' uppercase or reset rules name a selector these lack, when these
# name one that no such rule names, or when a stylesheet sets text-transform in a way it does not read: to a value
# other than uppercase or none, in a rule nested in a style rule, in an at-rule other than @media and @supports, or to
# none inside an at-rule; when a style rule holds a property name with a backslash (an escape, which can spell
# text-transform); and when any rule or at-rule sets small capitals, which show the label in capital letters and which
# the label rule does not read, or a value it cannot read, by font-variant, font-variant-caps, font-feature-settings or
# the font shorthand (its CAPS_PROPERTIES and CAPS_VALUE).
UPPERCASE_SELECTORS = (
    ".skip", ".lbl", ".label", ".nav", ".start", ".copy", ".btn", "th", ".tag", "table.matrix th .grp", "dl.record dt",
    ".picker a", ".chips a", ".chips button", ".figure svg .t", ".srcview .view h4", ".region .about", ".control dt",
    ".note > .label", ".reg-cap", ".fig .cap",
)
RESET_SELECTORS = (".lbl.file", "table.matrix tbody th", "table.matrix th .org", ".reg-cap .count")
# The general categories of the characters, besides VALUE_SPACES and VALUE_SIGNS, that the text of the landing page's
# value paragraph may hold, read after NFC: letters (Lu, Ll and Lt), decimal digits (Nd), punctuation (P), and
# currency and math symbols (Sc and Sm). Its text uses Lu, Ll, Nd, Pd and Po today. No Default_Ignorable_Code_Point
# falls in them. Lo, which holds the Hangul fillers, and So, which holds U+2800 (a Braille pattern blank), are left
# out, as is every other category, Mn among them: NFC composes a letter and a combining mark that has a precomposed
# form (e plus U+0301 reads as U+00E9), and leaves any other mark, such as U+034F, a variation selector or U+0301 after
# q, refused.
VALUE_CATEGORIES = {"Lu", "Ll", "Lt", "Nd", "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po", "Sc", "Sm"}
# The visible signs outside VALUE_CATEGORIES that the value paragraph's text may also hold, each by name: the
# copyright, registered, trade mark and service mark signs (U+00A9, U+00AE, U+2122 and U+2120, So), the degree sign
# (U+00B0, So), the superscript digits (U+2070, U+00B9, U+00B2, U+00B3 and U+2074 to U+2079, No) and every character
# named VULGAR FRACTION (U+00BC to U+00BE, U+2150 to U+215E and U+2189, No). Each shows a glyph; none is blank,
# whitespace or a Default_Ignorable_Code_Point, and NFC leaves each as it is. Every other character of So and No,
# such as U+2800, U+215F (fraction numerator one) or a subscript digit, stays refused.
VALUE_SIGNS = ("\u00a9\u00ae\u2122\u2120\u00b0\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
               "\u00bc\u00bd\u00be\u2150\u2151\u2152\u2153\u2154\u2155\u2156\u2157\u2158\u2159\u215a\u215b\u215c"
               "\u215d\u215e\u2189")
# The whitespace the value paragraph's text may hold: the ordinary space and U+0009, U+000A and U+000D, which a
# browser collapses with it, and U+00A0 (&nbsp;), which it shows as a space.
VALUE_SPACES = " \t\n\r\u00a0"
# The refusal of a value paragraph outside its pin (PageScan.value_problem() names what it holds).
VALUE_PIN = ("the value paragraph holds markup or text outside its pin (only a elements with no attribute but href, "
             "em elements with no attribute, and text of letters, digits, punctuation, currency and math symbols, "
             "the signs of VALUE_SIGNS and whitespace, with at least 1 letter)")
# Every Default_Ignorable_Code_Point, as (first, last) ranges, from DerivedCoreProperties.txt of the Unicode Character
# Database, version 16.0.0 (unicodedata.unidata_version on Python 3.14): 4174 code points that Unicode says to render
# invisibly where they are not supported. Python's unicodedata does not expose this property; the label rule deletes
# them, with every character of general category Cf, which unicodedata does expose.
DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)
SLICE_COUNT = 6


class BuildError(Exception):
    """A refusal or a drift: exit 1."""


class Unreadable(Exception):
    """An input could not be read or is malformed: exit 3."""


# Reading inputs -------------------------------------------------------------

def read_text(root: Path, relative: Path | str) -> str:
    path = root / relative
    try:
        info = os.lstat(path)
    except OSError as error:
        raise Unreadable(f"{relative} could not be read: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise Unreadable(f"{relative} is not a regular file")
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        raise Unreadable(f"{relative} could not be read: {error}") from error


def read_json(root: Path, relative: Path) -> dict:
    try:
        value = json.loads(read_text(root, relative))
    except ValueError as error:
        raise Unreadable(f"{relative} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise Unreadable(f"{relative} is not a JSON object")
    return value


def skill_version(root: Path) -> str:
    for line in read_text(root, SKILL).splitlines():
        if line.startswith("Version:"):
            match = SKILL_VERSION.match(line)
            if match is None:
                raise Unreadable("the first Version: line of SKILL.md is not a bare X.Y.Z version")
            return match.group(1)
    raise Unreadable("SKILL.md has no Version: line")


def load_release(root: Path, override: dict | None = None) -> dict:
    """Release values from site-src/release.json, or from ``override`` (the release writer's new values)."""
    release = override if override is not None else read_json(root, SRC / "release.json")
    version, tag, checksum = release.get("version"), release.get("tag"), release.get("checksum")
    if not isinstance(version, str) or not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", version):
        raise Unreadable(f"site-src/release.json version {version!r} is not X.Y.Z")
    if tag != f"v{version}":
        raise BuildError(f"site-src/release.json tag {tag!r} is not v{version}")
    if not isinstance(checksum, str) or not HEX64.match(checksum):
        raise BuildError("site-src/release.json checksum is not a 64 character lower-case SHA-256")
    expected = skill_version(root)
    if version != expected:
        raise BuildError(
            f"site-src/release.json names version {version}, but SKILL.md says {expected}; "
            "run tools/set-release-links.py for the release, never edit one without the other"
        )
    zip_name = f"cleanlanguage-{version}.zip"
    zip_url = f"https://github.com/{REPO_SLUG}/releases/download/{tag}/{zip_name}"
    return {
        "release.version": version,
        "release.tag": tag,
        "release.checksum": checksum,
        "release.zip_name": zip_name,
        "release.zip_url": zip_url,
        "release.sum_url": f"{zip_url}.sha256",
    }


# Markdown subset for the skill's reference files ------------------------------

UNSUPPORTED_MARKDOWN = re.compile(r"\*\*|__|\]\(|^\s*[>|]|^\s*```|<", re.M)


def inline(text: str, where: str) -> str:
    """Escape a line of reference Markdown and turn `code` spans into <code>."""
    if UNSUPPORTED_MARKDOWN.search(text) or text.count("`") % 2:
        raise BuildError(f"{where}: unsupported Markdown in {text!r}; extend the generator before using it")
    parts = text.split("`")
    out = []
    for index, part in enumerate(parts):
        escaped = html.escape(part, quote=False)
        out.append(f"<code>{escaped}</code>" if index % 2 else escaped)
    return "".join(out)


def parse_sections(markdown: str, where: str) -> tuple[list[str], list[dict]]:
    """Split a reference file into its intro paragraphs and its ## sections.

    Each section holds an ordered list of blocks: ("p", text), ("ul", [items]),
    ("ol", [items]) or ("h3", heading).
    """
    intro: list[str] = []
    sections: list[dict] = []
    current: list | None = None
    lines = markdown.splitlines()
    index = 0
    seen_title = False
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("# "):
            if seen_title:
                raise BuildError(f"{where}: more than 1 title line")
            seen_title = True
            index += 1
            continue
        if line.startswith("## "):
            sections.append({"title": line[3:].strip(), "blocks": []})
            current = sections[-1]["blocks"]
            index += 1
            continue
        if line.startswith("### "):
            if current is None:
                raise BuildError(f"{where}: a ### heading before any ## section")
            current.append(("h3", line[4:].strip()))
            index += 1
            continue
        if line.startswith("- ") or re.match(r"^[0-9]+\. ", line):
            kind = "ul" if line.startswith("- ") else "ol"
            items = []
            while index < len(lines) and lines[index].strip():
                item = lines[index]
                if kind == "ul" and item.startswith("- "):
                    items.append(item[2:].strip())
                elif kind == "ol" and re.match(r"^[0-9]+\. ", item):
                    items.append(item.split(" ", 1)[1].strip())
                else:
                    raise BuildError(f"{where}: list continued by {item!r}")
                index += 1
            target = current if current is not None else None
            if target is None:
                raise BuildError(f"{where}: a list before any ## section")
            target.append((kind, items))
            continue
        if line.startswith("#"):
            raise BuildError(f"{where}: unsupported heading {line!r}")
        paragraph = []
        while index < len(lines) and lines[index].strip() and not lines[index].startswith(("#", "- ")):
            paragraph.append(lines[index].strip())
            index += 1
        text = " ".join(paragraph)
        if current is None:
            intro.append(text)
        else:
            current.append(("p", text))
    return intro, sections


def slug(prefix: str, title: str) -> str:
    return prefix + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def render_list(kind: str, items: list[str], where: str) -> str:
    return f"<{kind}>" + "".join(f"<li>{inline(item, where)}</li>" for item in items) + f"</{kind}>"


def render_clauses(sections: list[dict], where: str) -> str:
    """Render ## sections of bullet questions as numbered clauses (specification 7.22, the checklist page)."""
    out = []
    for number, section in enumerate(sections, start=1):
        anchor = slug("", section["title"])
        out.append(f'<p class="lbl sec">Section {number}</p>')
        out.append(f'<h2 class="clause" id="{anchor}"><span class="num">{number}</span><span>{inline(section["title"], where)}</span></h2>')
        if [kind for kind, _ in section["blocks"]] != ["ul"]:
            raise BuildError(f"{where}: section {section['title']!r} must be exactly 1 bullet list to render as clauses")
        items = section["blocks"][0][1]
        out.append(
            '<ol class="clauses">'
            + "".join(f'<li><span class="n">{number}.{index}</span><div><p>{inline(item, where)}</p></div></li>' for index, item in enumerate(items, start=1))
            + "</ol>"
        )
    return "\n".join(out)


def render_reference_sections(sections: list[dict], prefix: str, label: str, where: str) -> str:
    """Render ## sections of a reference file as labelled document sections."""
    out = []
    for number, section in enumerate(sections, start=1):
        anchor = slug(prefix, section["title"])
        out.append(f'<p class="lbl sec">{html.escape(label, quote=False)} {number}</p>')
        out.append(f'<h2 id="{anchor}">{inline(section["title"], where)}</h2>')
        for kind, value in section["blocks"]:
            if kind == "p":
                out.append(f"<p>{inline(value, where)}</p>")
            elif kind in ("ul", "ol"):
                out.append(render_list(kind, value, where))
            else:
                raise BuildError(f"{where}: unexpected ### heading {value!r} in {section['title']!r}")
    return "\n".join(out)


LABELS = {"Weak": "Before", "Source": "Source", "Preferred": "After"}


def render_examples(root: Path, commentary: dict) -> tuple[str, int]:
    where = str(REFS / "examples.md")
    _, sections = parse_sections(read_text(root, REFS / "examples.md"), where)
    unknown = set(commentary) - {s["title"] for s in sections}
    if unknown:
        raise BuildError(f"site-src/examples-commentary.json names sections examples.md does not have: {sorted(unknown)}")
    out = []
    for number, section in enumerate(sections, start=1):
        anchor = slug("ex-", section["title"])
        out.append(f'<p class="lbl sec">Example {number}</p>')
        out.append(f'<h2 id="{anchor}">{inline(section["title"], where)}</h2>')
        blocks: list[dict] = []
        pending_paragraphs: list[str] = []
        for kind, value in section["blocks"]:
            if kind == "h3":
                blocks.append({"heading": value, "paras": []})
            elif kind == "p":
                if blocks:
                    blocks[-1]["paras"].append(value)
                else:
                    pending_paragraphs.append(value)
            else:
                raise BuildError(f"{where}: a list inside example {section['title']!r}")
        for paragraph in pending_paragraphs:
            out.append(f"<p>{inline(paragraph, where)}</p>")
        extra = commentary.get(section["title"])
        if extra is not None and (not isinstance(extra, str) or "<" in extra or "{{" in extra):
            raise BuildError(f"site-src/examples-commentary.json: {section['title']!r} must be plain text")
        index = 0
        while index < len(blocks):
            block = blocks[index]
            if not block["paras"]:
                raise BuildError(f"{where}: ### {block['heading']} in {section['title']!r} has no text")
            if block["heading"].startswith("Preferred"):
                raise BuildError(f"{where}: ### {block['heading']} in {section['title']!r} has no example before it")
            afters = []
            index += 1
            while index < len(blocks) and blocks[index]["heading"].startswith("Preferred"):
                if not blocks[index]["paras"]:
                    raise BuildError(f"{where}: ### {blocks[index]['heading']} has no text")
                afters.append(blocks[index])
                index += 1
            before_label = html.escape(LABELS.get(block["heading"], block["heading"]), quote=False)
            if not afters:
                out.append(
                    f'<div class="wide"><div class="callout"><p class="lbl">{before_label}</p>'
                    f"<p>{inline(block['paras'][0], where)}</p></div></div>"
                )
                notes = block["paras"][1:]
            else:
                if len(block["paras"]) != 1:
                    raise BuildError(f"{where}: ### {block['heading']} has notes before its preferred version")
                after_html = "".join(
                    f'<p class="lbl">{html.escape(LABELS.get(a["heading"], a["heading"]), quote=False)}</p>'
                    f"<p>{inline(a['paras'][0], where)}</p>"
                    for a in afters
                )
                out.append(
                    f'<div class="wide"><div class="pair"><div class="before"><p class="lbl">{before_label}</p>'
                    f"<p>{inline(block['paras'][0], where)}</p></div>"
                    f'<div class="after">{after_html}</div></div></div>'
                )
                notes = [p for a in afters for p in a["paras"][1:]]
            if extra:
                # The site's own commentary follows the section's first pair, before the source's notes.
                out.append(f"<p>{html.escape(extra, quote=False)}</p>")
                extra = None
            for note in notes:
                out.append(f"<p>{inline(note, where)}</p>")
    return "\n".join(out), len(sections)


def load_pin(root: Path) -> tuple[str, set[str]]:
    """The baseline version and the pinned paths from .baseline/pin.toml, the one source of both."""
    try:
        pin = tomllib.loads(read_text(root, Path(".baseline/pin.toml")))
    except tomllib.TOMLDecodeError as error:
        raise Unreadable(f".baseline/pin.toml is not valid TOML: {error}") from error
    version, files = pin.get("version"), pin.get("files")
    if not isinstance(version, str) or not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", version):
        raise Unreadable(".baseline/pin.toml version is not X.Y.Z")
    if not isinstance(files, dict) or not files:
        raise Unreadable(".baseline/pin.toml pins no files")
    # Only the copied files under assets/baseline/ are served; the pinned build tool is not.
    return version, {path for path in files if path.startswith("assets/baseline/")}


def operating_mode_count(root: Path) -> int:
    text = read_text(root, SKILL)
    match = re.search(r"^## Select the operating mode\n(.*?)(?=^## )", text, re.S | re.M)
    if match is None:
        raise Unreadable("SKILL.md has no 'Select the operating mode' section")
    count = len(re.findall(r"^- \*\*[A-Z][a-z]+:\*\*", match.group(1), re.M))
    if count == 0:
        raise Unreadable("SKILL.md lists no operating modes")
    return count


# Page assembly ----------------------------------------------------------------

def page_date(page: dict, override: str | None) -> str | None:
    """The page's modified date: ``--date`` when given, else its ``modified`` entry in site.json."""
    return override if override is not None else page.get("modified")


def head(config: dict, page: dict, base: str, asset_tokens: dict, date: str | None) -> str:
    title = f"{page['title']} | {config['name']}{config['tld']}"
    lines = [
        "<!doctype html>",
        f'<html lang="en" class="{config["site_class"]}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
    ]
    draft = base != "/"
    if draft or page.get("noindex"):
        lines.append('<meta name="robots" content="noindex, nofollow">')
    lines.append(f"<title>{html.escape(title, quote=False)}</title>")
    if not draft and not page.get("noindex"):
        lines += promotion_metadata(config, page, page_date(page, date))
    key = config["site_key"]
    lines.append(f'<link rel="icon" href="{base}assets/baseline/logos/{key}-favicon.svg" type="image/svg+xml">')
    lines.append(f'<link rel="apple-touch-icon" href="{base}assets/baseline/logos/{key}-touch.png">')
    lines.append(f'<script data-cfasync="false" src="{base}assets/baseline/scheme.js?v={asset_tokens["baseline"]}"></script>')
    for sheet in ("fonts.css", "palettes.css", "baseline.css"):
        lines.append(f'<link rel="stylesheet" href="{base}assets/baseline/{sheet}?v={asset_tokens["baseline"]}">')
    if "site.css" in asset_tokens:
        lines.append(f'<link rel="stylesheet" href="{base}assets/site.css?v={asset_tokens["site.css"]}">')
    names = list(page["scripts"]) + (["rail.js"] if page.get("rail") == "list" else [])
    scripts = "".join(
        f'<script src="{base}assets/baseline/{name}?v={asset_tokens["baseline"]}" defer></script>'
        for name in names
    )
    if scripts:
        lines.append(scripts)
    lines.append("</head>")
    return "\n".join(lines)


def promotion_metadata(config: dict, page: dict, date: str | None) -> list[str]:
    """The metadata the page-metadata gate requires, emitted only at base /."""
    if not isinstance(date, str) or not DATE.match(date):
        raise BuildError(
            f"{page['source']}: the / build needs a modified date YYYY-MM-DD for article:modified_time; "
            f"set \"modified\" for page {page['id']!r} in site-src/site.json (found {date!r})"
        )
    published = page.get("published") or date
    if not DATE.match(published):
        raise BuildError(f"{page['source']}: published date {published!r} is not YYYY-MM-DD")
    url = f"{config['origin']}/{page['path']}"
    full_title = f"{page['title']} | {config['name']}{config['tld']}"
    description = page.get("description", "")
    person = {
        "@type": "Person",
        "@id": f"{config['origin']}/#jeffposluns",
        "name": config["author"],
        "url": config["author_url"],
        "sameAs": config["author_same_as"],
    }
    entity = {
        "@context": "https://schema.org",
        "@type": "CreativeWork" if page["id"] == "home" else "WebPage",
        "name": full_title,
        "url": url,
        "description": description,
        "license": "https://creativecommons.org/licenses/by-sa/4.0/",
        "datePublished": published,
        "dateModified": date,
        "author": person,
        "publisher": person,
    }
    esc = lambda value: html.escape(value, quote=True)  # noqa: E731
    return [
        f'<meta name="description" content="{esc(description)}">',
        f'<meta name="author" content="{esc(config["author"])}">',
        f'<link rel="canonical" href="{esc(url)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{esc(full_title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<meta property="og:site_name" content="{esc(config["name"] + config["tld"])}">',
        f'<meta property="og:image" content="{esc(config["card_image"])}">',
        f'<meta property="og:image:alt" content="{esc(config["card_image_alt"])}">',
        f'<meta property="article:published_time" content="{published}">',
        f'<meta property="article:modified_time" content="{date}">',
        f'<meta property="article:author" content="{esc(config["article_author"])}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(full_title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
        f'<meta name="twitter:image" content="{esc(config["card_image"])}">',
        f'<meta name="twitter:image:alt" content="{esc(config["card_image_alt"])}">',
        '<script type="application/ld+json">',
        json.dumps(entity, indent=2, ensure_ascii=False).replace("</", "<\\/"),
        "</script>",
    ]


def external(href: str, text: str) -> str:
    return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{text}{NEW_TAB}</a>'


def mast(config: dict, page: dict, base: str, pages_by_id: dict) -> str:
    items = []
    for page_id in config["nav"]:
        target = pages_by_id[page_id]
        current = ' aria-current="page"' if target["id"] == page["id"] else ""
        items.append(f'<a href="{base}{target["path"]}"{current}>{html.escape(target["nav_label"], quote=False)}</a>')
    items.append(external(config["github"], "GitHub"))
    return (
        f'<header class="mast"><a class="brand" href="{base}"><span class="name">{config["name"]}'
        f'<span class="tld">{config["tld"]}</span></span><span class="rule" aria-hidden="true"></span></a>'
        f'<nav class="nav" aria-label="Site">{"".join(items)}</nav>{SCHEME_SWITCH}</header>'
    )


def footer(config: dict, base: str) -> str:
    family = config["family"]
    keys = [site["key"] for site in family]
    if len(family) != SLICE_COUNT or config["site_key"] not in keys:
        raise Unreadable("site-src/site.json family must list the 6 sites, this one included")
    start = keys.index(config["site_key"])
    logos = f"{base}assets/baseline/logos"
    marks = f"{base}assets/baseline/marks"
    cards = []
    for offset in range(SLICE_COUNT):
        index = (start + offset) % SLICE_COUNT
        site = family[index]
        name = f'<span class="cname">{site["name"]}<span class="tld">.ai</span></span>'
        image = f'<img src="{logos}/{site["key"]}.svg" alt="">'
        if offset == 0:
            link = f'<a class="card" href="{base}" aria-current="page">{image}{name}<span class="vh"> (this site)</span></a>'
        else:
            link = (
                f'<a class="card" href="{site["url"]}" target="_blank" rel="noopener noreferrer">'
                f"{image}{name}{NEW_TAB}</a>"
            )
        cards.append(f'<li class="slice slice-{index + 1}">{link}</li>')
    tail = (
        '<ul class="tail" aria-label="Jeff Posluns elsewhere">'
        '<li class="tile tile-1"><a class="card" href="https://github.com/jposluns" target="_blank" rel="noopener noreferrer">'
        f'<img class="only-light" src="{marks}/github-invertocat-black.svg" alt="">'
        f'<img class="only-dark" src="{marks}/github-invertocat-white.svg" alt="">'
        f'<span class="cname vh">GitHub</span>{NEW_TAB}</a></li>'
        '<li class="tile tile-2"><a class="card" href="https://www.linkedin.com/in/jposluns/" target="_blank" rel="noopener noreferrer">'
        f'<img src="{marks}/linkedin-in-bug.png" alt=""><span class="cname vh">LinkedIn</span>{NEW_TAB}</a></li>'
        '<li class="tile tile-3"><a class="card" href="https://orcid.org/0009-0000-7775-2233" target="_blank" rel="noopener noreferrer">'
        f'<img src="{marks}/orcid-id.svg" alt=""><span class="cname vh">ORCID</span>{NEW_TAB}</a></li></ul>'
    )
    signature = (
        '<div class="tile sigtile"><a class="sig" href="https://posluns.ca/" target="_blank" rel="noopener noreferrer" '
        'aria-label="A Jeff at Posluns dot ca project: posluns.ca (opens in a new tab)"><span class="pre">A </span>'
        'Jeff<span class="gold">@</span>Posluns<span class="gold">.ca</span><span class="post"> Project</span></a></div>'
    )
    return (
        '<footer class="family wrap"><div class="bar"><ul class="cards rainbow" aria-label="The 6 project sites">'
        + "".join(cards)
        + "</ul>"
        + tail
        + signature
        + "</div></footer>"
    )


def rail(config: dict, page: dict, base: str, content: str) -> str:
    """The rail rail_pin() leaves room for at <!--rail-->: on a page with a list rail, 1 entry for each h2 with an id,
    as PageScan reads the source (PageScan.headings), so the rail reads the tags, attributes and end tags that the
    other rules read."""
    image = f'<img class="rail-logo" src="{base}assets/baseline/logos/{config["site_key"]}.svg" alt="{html.escape(config["logo_alt"])}">'
    if page.get("rail") != "list":
        return f'<div class="rail">{image}</div>'
    entries = source_shape(content).headings
    # A source outside the grammar, which the parser need not read as a browser does (after a plaintext start tag it
    # reads the rest as text), is left to with_about(), which refuses it with its own message after the rail is in.
    if len(entries) < 2 and source_problem(content) is None:
        raise BuildError(f"{page['source']}: a list rail needs at least 2 h2 sections with ids")
    items = []
    for anchor, label in entries:
        # A numbered clause heading carries its number in a span.num, which PageScan leaves out; the rail lists the
        # title only, its ASCII whitespace collapsed, as a browser shows it.
        text = " ".join(part for part in ASCII_WHITESPACE.split("".join(label)) if part)
        # No link is marked in the markup; rail.js marks the reader's section with aria-current="location".
        items.append(f'<li><a href="#{html.escape(anchor)}">{html.escape(text, quote=False)}</a></li>')
    return f'<nav class="rail" aria-label="On this page">{image}<p class="lbl">On this page</p><ol>{"".join(items)}</ol></nav>'


def substitute(text: str, values: dict, where: str) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            raise BuildError(f"{where}: unknown token {{{{{name}}}}}")
        return values[name]

    result = TOKEN.sub(replace, text)
    if "{{" in result or "}}" in result:
        raise BuildError(f"{where}: an unreplaced or malformed token remains")
    return result


# Validation -------------------------------------------------------------------

@functools.cache
def install_gate():
    """tools/check-install-page.py, beside this tool, read, compiled and run as a fresh module, so that the value
    paragraph rule reads an element as hidden by that gate's is_hiding_element(), given the first of each repeated
    attribute as that gate's PageParser gives it, the label rule reads the text that shows by it, and deletes its
    ZERO_WIDTH. The
    source is always read, so no cached bytecode stands in for it; a source that is not a regular file, as
    read_text() requires, or that cannot be read, compiled or run, or that defines no is_hiding_element() or no
    ZERO_WIDTH string, is an input that cannot be read or is malformed (exit 3)."""
    path = Path(__file__).resolve().parent / "check-install-page.py"
    where = f"tools/{path.name}, whose hiding reader the value paragraph rule applies,"
    try:
        info = os.lstat(path)
    except OSError as error:
        raise Unreadable(f"{where} could not be read: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise Unreadable(f"{where} is not a regular file")
    try:
        source = path.read_bytes()
    except OSError as error:
        raise Unreadable(f"{where} could not be read: {error}") from error
    module = types.ModuleType("check_install_page")
    module.__file__ = str(path)
    try:
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    except (Exception, SystemExit) as error:
        raise Unreadable(f"{where} could not be loaded: {error!r}") from error
    if not callable(getattr(module, "is_hiding_element", None)):
        raise Unreadable(f"{where} defines no is_hiding_element()")
    if not isinstance(getattr(module, "ZERO_WIDTH", None), str):
        raise Unreadable(f"{where} defines no ZERO_WIDTH string")
    return module


def is_hiding(tag: str, attrs: dict[str, str]) -> bool:
    """Whether tools/check-install-page.py's is_hiding_element(), as install_gate() loads it, reads an element as hiding
    itself and its content. A call into it that fails, as when its signature has changed, or that returns anything
    but a bool, is an input that cannot be read or is malformed (exit 3), as the gate's loading is."""
    gate = install_gate()
    try:
        hides = gate.is_hiding_element(tag, attrs)
    except (Exception, SystemExit) as error:
        raise Unreadable(f"tools/check-install-page.py, whose hiding reader the value paragraph rule applies, failed "
                         f"when called on a <{tag}> start tag: {error!r}") from error
    if not isinstance(hides, bool):
        raise Unreadable(f"tools/check-install-page.py, whose hiding reader the value paragraph rule applies, returned "
                         f"{hides!r} for a <{tag}> start tag, not True or False")
    return hides


def source_problem(content: str) -> str | None:
    """The first markup in a page source outside the page source grammar (SOURCE_TOKEN), or the first html, head,
    body, frameset or math start tag, start tag of an element of RAW_TEXT_TAGS or outside SOURCE_ELEMENTS, noscript
    start tag inside a noscript, start tag with an attribute outside SOURCE_ATTRIBUTES, or end tag of an element
    outside SOURCE_ELEMENTS in it, as a refusal naming where it starts (source_at()); None if there is none."""
    at, noscript = 0, False
    while at < len(content):
        token = SOURCE_TOKEN.match(content, at)
        name = (token.group("start") or "").lower() if token else ""
        end = (token.group("end") or "").lower() if token else ""
        # The attribute names outside SOURCE_ATTRIBUTES, as written, of a start tag that the grammar admits.
        stray = [found.group(1) for found in SOURCE_ATTRIBUTE.finditer(token.group(0), 1 + len(name))
                 if found.group(1).lower() not in SOURCE_ATTRIBUTES] if name else []
        # What is refused, and why; the place goes between them.
        refusal = None
        if token is None:
            rest = content[at:at + len("<![cdata[")].lower()
            what = ("a CDATA section" if rest.startswith("<![cdata[") else "a DOCTYPE" if rest.startswith("<!doctype")
                    else "a processing instruction" if rest.startswith("<?")
                    else "a comment whose text holds <, > or --, or that does not end" if rest.startswith("<!--")
                    else "a < that begins no start tag, end tag or comment of the grammar")
            refusal = (what, "a page source holds only markup on which Python's parser and a browser read the same "
                       "tokens: text with no <, start and end tags whose attribute values hold no < or >, and comments "
                       "whose text holds no <, > or --")
        elif name in DOCUMENT_TAGS:
            refusal = (f"a stray <{name}> start tag", "the generator writes the page's html, head and body, so a page "
                       "source may carry none of them, nor a frameset")
        elif name == "math":
            refusal = ("a <math> start tag", "inside math, a browser can read a title, textarea, script or style "
                       "element's content as markup, which the parser reads as text")
        elif name in RAW_TEXT_TAGS:
            refusal = (f"a <{name}> start tag", "a page source holds only markup on which Python's parser and a browser "
                       "read the same tokens, so no element whose content a browser reads as raw or escapable raw "
                       "text, nor template")
        elif name and name not in SOURCE_ELEMENTS:
            refusal = (f"a <{name}> start tag", "a page source carries only the elements of SOURCE_ELEMENTS; adding "
                       "one needs a review of how a browser's tree builder places it and what follows it")
        elif name == "noscript" and noscript:
            refusal = ("a <noscript> start tag inside a noscript", "with scripting on, a browser ends the outer "
                       "noscript at the inner one's end tag, where the parser reads the outer one as still open")
        elif stray:
            refusal = (f"a {stray[0]} attribute on a <{name}> start tag", "a page source carries only the attributes "
                       "of SOURCE_ATTRIBUTES; adding one needs a review of what it makes a browser do, such as close "
                       "all but 1 open details of a name group")
        elif end and end not in SOURCE_ELEMENTS:
            refusal = (f"a </{end}> end tag", "an end tag in a page source names an element of SOURCE_ELEMENTS; a "
                       "browser reads </br> as a br start tag, which it moves to before the table directly inside a "
                       "table, thead, tbody or tr, where the parser ignores it")
        if refusal is not None:
            return f"{refusal[0]} {source_at(line_column(content, at))}; {refusal[1]}"
        if name == "noscript" or end == "noscript":
            noscript = bool(name)
        at = token.end()
    return None


def source_at(position: tuple[int, int]) -> str:
    """Where a refused tag or markup starts in a page source, as a refusal names it: position is (line, column) as
    getpos() and line_column() give it, the line counted from 1 and the column from 0, in the source as with_about()
    reads it, with its {{tokens}} and rail written in. A token that writes in several lines (such as {{instructions}})
    puts what follows it on a later line than in the committed file."""
    line, column = position
    return f"at line {line}, column {column} of the source with its tokens and rail written in"


def misnested(tag: str, open_names: list[str], first_child: bool) -> tuple[str, str] | None:
    """Why a browser's tree builder would not place a start tag of tag where the parser does, as the next child of the
    last of open_names (the parser's open elements; first_child: no element has started in that one yet), as (what,
    why) for a refusal (module docstring, "Page source tree"); None if a browser places it there too."""
    parent = open_names[-1] if open_names else ""
    if tag == "summary" and not (parent == "details" and first_child):
        return ("a <summary> start tag", "a summary is allowed only as the first element child of a details, so the "
                "parser and a browser agree on which summary a details without open shows")
    if tag in P_CLOSERS:
        for name in reversed(open_names):
            if name == "p":
                return (f"a <{tag}> start tag inside an open p", "a browser ends the p there, where the parser "
                        "reads it as still open")
            if name in BUTTON_SCOPE:
                break
    if tag in HEADINGS and parent in HEADINGS:
        return (f"a <{tag}> start tag directly inside an open {parent}", "a browser ends the heading there, where "
                "the parser reads it as still open")
    if tag == "li":
        for name in reversed(open_names):
            if name == "li":
                return ("a <li> start tag inside an open li", "with only a, code, div, em, p, small, span or "
                        "strong between them, a browser ends the open li and what it holds there, where the parser "
                        "reads them as still open")
            if name not in LI_THROUGH:
                break
    if tag in ("a", "button") and tag in open_names:
        return (f"a <{tag}> start tag inside an open {tag}", f"a browser ends the open {tag} there, where the "
                "parser reads it as still open")
    if (parent in TABLE_CHILDREN or tag in TABLE_PARTS) and tag not in TABLE_CHILDREN.get(parent, ()):
        return (f"a <{tag}> start tag as a child of {f'a {parent}' if parent else 'no element'}", "a table holds "
                "only caption, thead and tbody, a thead or tbody only tr, and a tr only td and th; a browser moves "
                "anything else out of a table part to before the table, and ignores a table part's start tag "
                "anywhere else, where the parser reads it as written")
    return None


class PageScan(HTMLParser):
    """The parsed reading validate() checks, which build() also reads on each page source. Not a full HTML5 tree
    builder: it models the open elements as tags nest, void elements, the slash only in <svg>, the head's end, class
    names split on ASCII whitespace, and the INERT_TAGS ancestors of each element with data-scheme-toggle, h1, robots
    meta and id, and of each element start validate() requires, the element starts hidden by themselves or by an
    ancestor as tools/check-install-page.py reads hiding (its is_hiding_element(), and a details without open, which
    shows only its first summary child), where each value paragraph starts and where the region of the first one
    ends, that region's ancestors and those of the element at about_at, where each element whose classes include
    about starts, where each html, head, body, frameset and math start tag is, each start tag or text a browser's
    tree builder would place elsewhere (misnested(), a table child out of TABLE_ORDER, and a summary after text in its
    details), each start tag with hidden=until-found, its text, all of it and that which shows (with an element that
    only aria-hidden="true" hides read as shown, and then as hidden), each piece with the optional groups it is in
    (chains: the folded content of a details without open, an img's alt text), in upper
    case where the stylesheets show it so (labels(), uppercase_here()), the first p.value's text and the first start
    tag in it outside its pin (value_problem()), the children of its region and the text that shows in each
    (region_problem()) and where each of its class names sits (region_class_problem()), each start tag's class names
    with where it and its open elements start (stray_class()), where the page's body starts, each element with its
    parent and what came before it there, for the placement pins and rail_pin(), each h2 with an id and its text,
    for rail(), and the hero's narrow-width order, for labels(). It is not the only read of a page source: some rules
    read the source text itself, such as the grammar (source_problem()) and bidi_control(), and the module docstring
    describes reads of that kind. An element's
    attributes are the first of each repeated name, as a browser and tools/check-install-page.py's PageParser
    read them. validate() also pins the markup from <body> to the end of header.mast, and the landing
    page's About block; --check compares the committed pages with a build that passed it. With scripting False
    (scripting_off()), the text that shows is read as a browser with scripting off shows it: the content of each
    noscript as rendered, its hiding rules all applying, and that of every other element of INERT_TAGS as not."""

    def __init__(self, switch_at: tuple[int, int] | None = None, about_at: tuple[int, int] | None = None,
                 scripting: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        # The elements whose content the text that shows leaves out: INERT_TAGS, or, with scripting off, all but
        # noscript, whose content a browser then renders as page elements, as the parser reads it.
        self.unrendered = INERT_TAGS if scripting else INERT_TAGS - {"noscript"}
        self.ids: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.h1 = 0
        self.problems: list[str] = []
        self.anchor: dict | None = None
        self.scripts: list[dict] = []
        # Where each script with a src, each stylesheet, and each element with data-scheme-toggle (the elements
        # scheme.js wires and shows) start: (line, column), as getpos() reports.
        self.loads: list[tuple[tuple[int, int], str]] = []
        self.sheets: list[tuple[int, int]] = []
        self.toggles: list[tuple[int, int]] = []
        # Whether an element with data-scheme-toggle, an h1 or a robots meta starts inside an element of INERT_TAGS;
        # the ids outside them, which a fragment may target; and where each element outside them starts.
        self.inert_toggle = False
        self.inert_h1 = False
        self.inert_robots = False
        self.live_ids: set[str] = set()
        self.live_starts: set[tuple[int, int]] = set()
        # Where each script and link starts outside the page's head: html > head, the first head or body opened,
        # until the head ends where HTML5 ends it.
        self.outside_head: set[tuple[int, int]] = set()
        self.heads = 0
        self.head_ended = False
        # Where the page's body starts: a body start tag in html right after the page's only head closes, with no
        # element or text between them, before the head ends.
        self.body_at: tuple[int, int] | None = None
        self.robots: list[str] = []
        # Where each element whose classes include about starts, inside an element of INERT_TAGS or not: on the
        # landing page, the row of the About block the generator writes; anywhere else, About markup.
        self.about_classes: list[tuple[int, int]] = []
        # Each html, head, body and frameset start tag and where it starts: in a page source, which the generator
        # wraps in its own html, head and body, a stray one.
        self.document_tags: list[tuple[str, tuple[int, int]]] = []
        # Where each math start tag starts; the text the parser reads (attribute values and comments apart), in upper
        # case where the stylesheets show it so (uppercase_here()), as a browser shows it; that text outside every
        # element of unrendered and every element hidden as tools/check-install-page.py reads hiding, folded content
        # kept, first with an element that only aria-hidden="true"
        # hides read as shown, since it hides an element from assistive technology alone (shown), then with it read
        # as hidden (unhidden); for each piece of each of the 3, the keys of the optional groups it is in, outermost
        # first (chains, label_count()): where each details without open starts whose folded content holds it
        # (fold_keys()), then, for an img's alt text, where the img starts; and, for each open element, whether its text
        # shows in upper case.
        self.maths: list[tuple[int, int]] = []
        self.text: list[str] = []
        self.shown: list[str] = []
        self.unhidden: list[str] = []
        self.chains: tuple[list[tuple], list[tuple], list[tuple]] = ([], [], [])
        self.uppercase: list[bool] = []
        # Each start tag or text that a browser's tree builder would place elsewhere (misnested()), as (what, where it
        # starts, why): in a page source, a refusal.
        self.misnested: list[tuple[str, tuple[int, int], str]] = []
        # Where each element hidden by itself or by an open ancestor starts, as tools/check-install-page.py reads
        # hiding; the depth in open of each such ancestor, and of each that hides other than by aria-hidden="true"
        # alone; and, for each open details without open, by its depth, whether its first summary child has started.
        self.hidden_starts: set[tuple[int, int]] = set()
        self.hiding: list[int] = []
        self.covering: list[int] = []
        self.closed: dict[int, bool] = {}
        # The depth in open of each element folded in a details without open (a child other than its first summary),
        # which the value paragraph rule reads as hidden and the label rule both as hidden and as shown; for each open
        # table by its depth, the place in TABLE_ORDER of its last child; the depth of each open details that holds
        # text other than ASCII whitespace directly; and where each start tag with hidden=until-found starts.
        self.folding: list[int] = []
        self.table_ranks: dict[int, int] = {}
        self.details_text: set[int] = set()
        self.until_found: list[tuple[int, int]] = []
        # For each div.region, by where it starts: its children (name, classes and where each starts) and whether it
        # holds text other than whitespace directly; and, for each child of a div.region, the text in it that shows.
        self.region_children: dict[tuple[int, int], list[tuple[str, list[str], tuple[int, int]]]] = {}
        self.region_texts: set[tuple[int, int]] = set()
        self.child_shown: dict[tuple[int, int], list[str]] = {}
        # Where each p.value starts; the depth in open of the first one's region, the div.region nearest it among its
        # open elements, while that region is open; and where the end tag of that region starts.
        self.values: list[tuple[int, int]] = []
        self.value_region: int | None = None
        self.value_region_end: tuple[int, int] | None = None
        # The depth in open of the first p.value while it is open, its text, the first start tag in it other than an a
        # with no attribute but href or an em with no attribute (value_problem()), and where its open elements start.
        self.value_depth: int | None = None
        self.value_text: list[str] = []
        self.value_stray: str | None = None
        self.value_lineage: tuple[tuple[int, int], ...] = ()
        # The open elements (name, classes) where that region starts, its ancestors; and those where the element
        # that starts at about_at (on the landing page, the About block) starts.
        self.value_region_ancestors: list[tuple[str, list[str]]] | None = None
        self.about_at = about_at
        self.about_ancestors: list[tuple[str, list[str]]] | None = None
        # Each open element's name and classes, and the element that ended last (or a void one) since the last
        # start tag: the previous sibling of the next element.
        self.open: list[tuple[str, list[str]]] = []
        self.previous: tuple[str, list[str]] | None = None
        # Where each open element starts, as open holds them; where the first p.value's region starts; and, for each
        # start tag with a class name, where it starts, where its open elements start and its class names.
        self.open_at: list[tuple[int, int]] = []
        self.value_region_at: tuple[int, int] | None = None
        self.class_starts: list[tuple[tuple[int, int], tuple[tuple[int, int], ...], list[str]]] = []
        # The switch, the button that starts at switch_at: its parent, its previous sibling, its depth, and where
        # the end tag of its parent starts.
        self.switch_at = switch_at
        self.switch_parent: tuple[str, list[str]] | None = None
        self.switch_previous: tuple[str, list[str]] | None = None
        self.switch_depth = 0
        self.switch_parent_end: tuple[int, int] | None = None
        self.doc_closed = False
        self.in_main = False
        self.in_pre = 0
        # The elements as the placement pins and rail_pin() read them: for each start tag, its name, class names,
        # attributes, where it starts, the index of its parent (None at the top level) and whether text or an element
        # came before it there; the index of each open element, as open holds them; the indexes of the elements (None
        # for the top level) that hold any text, and of those that hold text other than ASCII whitespace, directly;
        # and whether the last token was a pre start tag, after which a browser drops a line feed (written or as a
        # character reference) that is the next token, so an element after it in the pre still comes first there.
        self.elements: list[tuple[str, list[str], dict, tuple[int, int], int | None, bool]] = []
        self.open_index: list[int] = []
        self.filled: set[int | None] = set()
        self.texts: set[int | None] = set()
        # The text directly in each element, by its index (None for the top level), for the data-copy pin.
        self.own_texts: dict[int | None, list[str]] = {}
        self.after_pre = False
        # Each h2 with an id, as (id, its text but that of a span.num inside it), for rail(); and the depth in open
        # of the h2 whose text is being read.
        self.headings: list[tuple[str, list[str]]] = []
        self.heading_depth: int | None = None
        # The hero's narrow-width order (at 600 px and below, the hero image sits in the kicker's row, before the
        # statement): the length of text, shown and unhidden where the first child of the first div.hero-text in a
        # section.hero ends when that child is the kicker (a p.lbl), and otherwise where that div.hero-text starts
        # (hero_start); and the index in each of the alt text of the first img in a div.hero-art in a section.hero
        # (None in a reading that leaves it out).
        self.hero_start: tuple[int, int, int] | None = None
        self.kicker_end: tuple[int, int, int] | None = None
        self.hero_alt: tuple[int | None, int | None, int | None] | None = None

    def handle_starttag(self, tag: str, attrs_list) -> None:
        # A browser reads the first of 2 attributes with the same name, as tools/check-install-page.py does.
        attrs: dict[str, str] = {}
        for k, v in attrs_list:
            attrs.setdefault(k.lower(), v or "")
        if len(attrs) != len(attrs_list):
            self.problems.append(f"<{tag}> carries an attribute twice")
        classes = [name for name in ASCII_WHITESPACE.split(attrs.get("class", "")) if name]
        if classes:
            self.class_starts.append((self.getpos(), tuple(self.open_at), classes))
        if "about" in classes:
            self.about_classes.append(self.getpos())
        if tag in ("html", "head", "body", "frameset"):
            self.document_tags.append((tag, self.getpos()))
        if tag == "math":
            self.maths.append(self.getpos())
        # The first element child of the current element: no element has ended in it, nor a void one started, since
        # the last start tag, which (no end tag having closed it) is the current element's.
        misplaced = misnested(tag, [name for name, _ in self.open], self.previous is None)
        if misplaced is not None:
            self.misnested.append((misplaced[0], self.getpos(), misplaced[1]))
        if self.open and self.open[-1][0] == "table" and tag in TABLE_ORDER:
            # A table's children in TABLE_ORDER, each slot but the last at most once, as a browser shows them.
            rank, last = TABLE_ORDER.index(tag), self.table_ranks.get(len(self.open) - 1)
            if last is not None and (rank < last or rank == last < len(TABLE_ORDER) - 1):
                self.misnested.append((f"a <{tag}> start tag after a {TABLE_ORDER[last]} in a table", self.getpos(),
                                       TABLE_ORDER_PIN))
            self.table_ranks[len(self.open) - 1] = max(rank, last or 0)
        if tag == "summary" and len(self.open) - 1 in self.details_text:
            self.misnested.append(("a <summary> start tag after text in its details", self.getpos(), SUMMARY_ORDER_PIN))
        if "until-found" in attrs.get("hidden", "").lower():
            self.until_found.append(self.getpos())
        if (tag == "body" and [name for name, _ in self.open] == ["html"] and self.heads == 1 and not self.head_ended
                and self.previous is not None and self.previous[0] == "head"):
            self.body_at = self.getpos()
        if tag in ("head", "body"):
            self.heads += 1
        if tag not in HEAD_TAGS and tag not in ("html", "head"):
            self.head_ended = True
        if tag in ("script", "link") and ([name for name, _ in self.open] != ["html", "head"] or self.heads != 1
                                          or self.head_ended):
            self.outside_head.add(self.getpos())
        inert = any(name in INERT_TAGS for name, _ in self.open)
        if not inert:
            self.live_starts.add(self.getpos())
        # Whether the element hides itself and its content: by tools/check-install-page.py's is_hiding_element(), whose
        # HIDING_ELEMENTS holds noscript; with scripting off, a browser renders a noscript, which then hides only by
        # its attributes, read as on a span.
        shape = "span" if tag == "noscript" and "noscript" not in self.unrendered else tag
        hides = is_hiding(shape, attrs)
        # Whether it hides other than by aria-hidden="true" alone, which hides an element from assistive technology
        # only: a browser shows it, so the text that shows (shown) keeps its text.
        covers = hides and ("aria-hidden" not in attrs or is_hiding(
            shape, {name: value for name, value in attrs.items() if name != "aria-hidden"}))
        # Whether it is folded: as that gate's PageParser reads it, a child of a details without open other than its
        # first summary. The value paragraph rule and the value region's label read it as hidden; the label rule
        # reads it both as hidden and as a reader who opens the details sees it (fold_keys(), label_count()), so a label
        # counts in either state (folding apart, its hiding rules all apply).
        folds = False
        if len(self.open) - 1 in self.closed:
            if tag == "summary" and not self.closed[len(self.open) - 1]:
                self.closed[len(self.open) - 1] = True
            else:
                folds = True
        if self.hiding or self.folding or hides or folds:
            self.hidden_starts.add(self.getpos())
        if self.open and self.open[-1][0] == "div" and "region" in self.open[-1][1]:
            self.region_children.setdefault(self.open_at[-1], []).append((tag, classes, self.getpos()))
        if self.value_depth is not None and self.value_stray is None and (
                tag not in ("a", "em") or set(attrs) - ({"href"} if tag == "a" else set())):
            self.value_stray = f"a <{tag}> start tag" + (f" with {', '.join(sorted(attrs))}" if attrs else "")
        if tag == "p" and "value" in classes:
            self.values.append(self.getpos())
            regions = [depth for depth, (name, names) in enumerate(self.open) if name == "div" and "region" in names]
            if len(self.values) == 1 and regions:
                self.value_region = regions[-1]
                self.value_region_ancestors = self.open[:regions[-1]]
                self.value_region_at = self.open_at[regions[-1]]
            if len(self.values) == 1:
                self.value_depth = len(self.open)
                self.value_lineage = tuple(self.open_at)
        if self.getpos() == self.about_at:
            self.about_ancestors = list(self.open)
        if "data-scheme-toggle" in attrs:
            self.toggles.append(self.getpos())
            self.inert_toggle = self.inert_toggle or inert
        if tag == "button" and self.getpos() == self.switch_at:
            self.switch_parent = self.open[-1] if self.open else None
            self.switch_previous = self.previous
            self.switch_depth = len(self.open)
        if tag == "img" and attrs.get("alt"):
            # A browser shows an img's alt text in its place when the image does not load, and none when it loads, in
            # upper case where the stylesheets show its text so, so the label rule reads it as text there that it may
            # also leave out (an optional group of its own, keyed by where the img starts, inside those of fold_keys()).
            # It is no text of a region's child (show()), so the value region's label holds text, not an image alone.
            upper = uppercase_here([*self.open, (tag, classes)])
            alt = attrs["alt"].upper() if (bool(self.uppercase and self.uppercase[-1]) if upper is None
                                           else upper) else attrs["alt"]
            chain = (*self.fold_keys(), self.getpos())
            self.text.append(alt)
            self.chains[0].append(chain)
            shown = unhidden = None
            unrendered = any(name in self.unrendered for name, _ in self.open)
            if not (self.covering or covers or unrendered):
                self.show(alt, chain)
                shown = len(self.shown) - 1
            if not (self.hiding or hides or unrendered):
                self.unhidden.append(alt)
                self.chains[2].append(chain)
                unhidden = len(self.unhidden) - 1
            if (self.hero_alt is None and len(self.open) >= 2 and self.open[-1][0] == "div"
                    and "hero-art" in self.open[-1][1] and self.open[-2][0] == "section" and "hero" in self.open[-2][1]):
                self.hero_alt = (len(self.text) - 1, shown, unhidden)
        if tag == "h2" and attrs.get("id") and self.heading_depth is None:
            self.headings.append((attrs["id"], []))
            self.heading_depth = len(self.open)
        if (self.kicker_end is None and tag == "div" and "hero-text" in classes and self.open
                and self.open[-1][0] == "section" and "hero" in self.open[-1][1]):
            self.hero_start = (len(self.text), len(self.shown), len(self.unhidden))
        parent = self.open_index[-1] if self.open_index else None
        self.elements.append((tag, classes, attrs, self.getpos(), parent, parent in self.filled))
        self.filled.add(parent)
        self.after_pre = tag == "pre"
        self.previous = (tag, classes) if tag in VOID_TAGS else None
        if tag not in VOID_TAGS:
            self.open.append((tag, classes))
            self.open_at.append(self.getpos())
            self.open_index.append(len(self.elements) - 1)
            if hides:
                self.hiding.append(len(self.open) - 1)
            if covers:
                self.covering.append(len(self.open) - 1)
            if folds:
                self.folding.append(len(self.open) - 1)
            upper = uppercase_here(self.open)
            self.uppercase.append(bool(self.uppercase and self.uppercase[-1]) if upper is None else upper)
            if tag == "details" and "open" not in attrs:
                self.closed[len(self.open) - 1] = False
        if self.doc_closed and self.in_main:
            self.problems.append(f"<{tag}> follows the end of .doc inside main; .doc closes early")
        if tag == "main":
            self.in_main = True
        if tag == "pre":
            self.in_pre += 1
        for name in attrs:
            if name.startswith("on"):
                self.problems.append(f"an {name} attribute on <{tag}>")
            if name == "style":
                self.problems.append(f"an inline style attribute on <{tag}>")
        if tag == "style":
            self.problems.append("a <style> element")
        if "id" in attrs:
            self.ids.append(attrs["id"])
            if not inert:
                self.live_ids.add(attrs["id"])
        if tag == "h1":
            self.h1 += 1
            self.inert_h1 = self.inert_h1 or inert
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots.append(attrs.get("content", ""))
            self.inert_robots = self.inert_robots or inert
        if tag == "script":
            self.scripts.append(attrs)
            if "src" in attrs:
                self.loads.append((self.getpos(), attrs["src"]))
        if tag == "link" and "stylesheet" in attrs.get("rel", "").lower().split():
            self.sheets.append(self.getpos())
        canonical = tag == "link" and attrs.get("rel") == "canonical"
        for name in ("href", "src"):
            if name in attrs and not canonical:
                self.links.append((tag, attrs[name]))
        if tag == "a" and attrs.get("href", "").startswith(("http://", "https://")):
            self.anchor = {"href": attrs["href"], "attrs": attrs, "text": ""}

    def handle_startendtag(self, tag, attrs):
        # A browser honours the slash only in <svg> (foreign content); any other element that is not void stays open.
        foreign = tag == "svg" or any(name == "svg" for name, _ in self.open)
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and foreign:
            self.handle_endtag(tag)

    def handle_comment(self, data: str) -> None:
        self.after_pre = False

    def handle_data(self, data: str) -> None:
        shaped = data[1:] if self.after_pre and data.startswith("\n") else data
        self.after_pre = False
        self.own_texts.setdefault(self.open_index[-1] if self.open_index else None, []).append(data)
        if shaped:
            self.filled.add(self.open_index[-1] if self.open_index else None)
            if shaped.strip(" \t\n\f\r"):
                self.texts.add(self.open_index[-1] if self.open_index else None)
        if self.heading_depth is not None and not any(name == "span" and "num" in names
                                                      for name, names in self.open[self.heading_depth:]):
            self.headings[-1][1].append(data)
        self.text.append(data.upper() if self.uppercase and self.uppercase[-1] else data)
        # Text directly inside a details without open, or inside a child other than its first summary, shows once a
        # reader opens it and not while it is closed, so the readings of the text that shows keep it in the optional
        # groups of fold_keys(), which the label rule reads both left out and shown.
        chain = self.fold_keys()
        self.chains[0].append(chain)
        if not any(name in self.unrendered for name, _ in self.open):
            if not self.covering:
                self.show(self.text[-1], chain)
            if not self.hiding:
                self.unhidden.append(self.text[-1])
                self.chains[2].append(chain)
        if self.open and self.open[-1][0] == "details" and data.strip(" \t\n\f\r"):
            self.details_text.add(len(self.open) - 1)
        if self.open and self.open[-1][0] == "div" and "region" in self.open[-1][1] and data.strip(" \t\n\f\r"):
            self.region_texts.add(self.open_at[-1])
        if self.value_depth is not None:
            self.value_text.append(data)
        if self.open and self.open[-1][0] in TABLE_CHILDREN and data.strip(" \t\n\f\r"):
            # A browser moves such text out of the table part to before the table (foster parenting).
            self.misnested.append((f"text other than whitespace directly inside a {self.open[-1][0]}", self.getpos(),
                                   "a browser moves it out to before the table, where the parser reads it as written"))
        if data.strip(" \t\n\f\r") and [name for name, _ in self.open] in ([], ["html"], ["html", "head"]):
            # Text other than whitespace in or before the head ends it (HTML5).
            self.head_ended = True
        if self.anchor is not None:
            self.anchor["text"] += data
        if self.in_pre and re.search(r"</?[a-z][a-z0-9]*[\s>]", data):
            self.problems.append("tag text such as <code> shown inside a <pre> block")

    def handle_endtag(self, tag: str) -> None:
        self.after_pre = False
        if tag in ("body", "html", "br"):
            # HTML5 ends the head at each of these end tags (</br> reads as <br>).
            self.head_ended = True
        if tag in VOID_TAGS:
            return
        if not self.open or self.open[-1][0] != tag:
            self.problems.append(f"</{tag}> does not close the open element {self.open[-1][0] if self.open else 'none'}")
        else:
            self.previous = self.open.pop()
            self.open_at.pop()
            self.open_index.pop()
            if len(self.open) == self.heading_depth:
                self.heading_depth = None
            if (self.kicker_end is None and len(self.open) >= 2 and self.open[-1][0] == "div"
                    and "hero-text" in self.open[-1][1] and self.open[-2][0] == "section" and "hero" in self.open[-2][1]):
                kicker = self.previous[0] == "p" and "lbl" in self.previous[1]
                self.kicker_end = (len(self.text), len(self.shown), len(self.unhidden)) if kicker else self.hero_start
            if tag == "div" and "doc" in self.previous[1]:
                self.doc_closed = True
            if len(self.open) == self.value_region:
                self.value_region, self.value_region_end = None, self.getpos()
            if len(self.open) == self.value_depth:
                self.value_depth = None
            while self.hiding and self.hiding[-1] >= len(self.open):
                self.hiding.pop()
            while self.covering and self.covering[-1] >= len(self.open):
                self.covering.pop()
            while self.folding and self.folding[-1] >= len(self.open):
                self.folding.pop()
            self.uppercase.pop()
            self.closed.pop(len(self.open), None)
            self.table_ranks.pop(len(self.open), None)
            self.details_text.discard(len(self.open))
            if self.switch_parent is not None and self.switch_parent_end is None and len(self.open) < self.switch_depth:
                self.switch_parent_end = self.getpos()
        if tag == "main":
            self.in_main = False
        if tag == "pre":
            self.in_pre -= 1
        if tag == "a" and self.anchor is not None:
            attrs = self.anchor["attrs"]
            label = self.anchor["text"] + attrs.get("aria-label", "")
            if attrs.get("target") != "_blank" or attrs.get("rel") != "noopener noreferrer" or "(opens in a new tab)" not in label:
                self.problems.append(f"the external link {self.anchor['href']} lacks target, rel or the new-tab text")
            self.anchor = None

    def show(self, text: str, chain: tuple) -> None:
        """Add text to the text that shows (shown), with the keys of the optional groups it is in (chain), and, inside
        a child of a div.region and in no such group, to that child's: an img's alt text, or text that only a reader
        who opens a details sees, is no text that shows of the value region's label."""
        self.shown.append(text)
        self.chains[1].append(chain)
        depth = next((depth for depth in range(len(self.open) - 1, -1, -1)
                      if self.open[depth][0] == "div" and "region" in self.open[depth][1]), None)
        if depth is not None and depth + 1 < len(self.open) and not chain:
            self.child_shown.setdefault(self.open_at[depth + 1], []).append(text)

    def fold_keys(self) -> tuple[tuple[int, int], ...]:
        """Where each open details without open starts, outermost first, whose folded content holds the next text or
        void element: it is directly inside that details, or inside a child of it other than its first summary."""
        return tuple(self.open_at[depth] for depth in sorted(self.closed)
                     if depth == len(self.open) - 1 or depth + 1 in self.folding)

    def labels(self) -> tuple[int, int, int]:
        """How many times the text the parser reads (each img's alt text in its place, other attribute values and
        comments apart, character references decoded), joined across elements, carries the About block's label
        (ABOUT_LABELS, case-sensitive), read by
        label_count(): in all of it, and twice in the text that shows, with the text of every element of INERT_TAGS
        and every element hidden as tools/check-install-page.py reads hiding deleted, so a hidden element inside the
        label does not split it: first with an element that only aria-hidden="true" hides kept, since a browser
        shows it, then with it deleted too. Text that the stylesheets show in upper case (uppercase_here()) is read
        in upper case, so there the label counts in any letter case. The folded content of each details without
        open is read both left out and shown, as a reader sees the details closed and opened, and each img's alt
        text both left out and kept, as a browser shows it when the image loads and when it does not, each details
        and img apart from the others (chains), and the reading counts the most that any 1 such choice gives
        (label_count()). Each reading is also read in the hero's narrow-width
        order, with the hero image's alt text moved to the end of the kicker, or to the start of the hero's text when
        its first child is not a p.lbl (kicker_end, hero_alt), and counts the more of its 2 orders. With scripting
        off (scripting_off()), the text that shows keeps the content of each noscript, its hiding rules applying."""
        counts = []
        for which, text in enumerate((self.text, self.shown, self.unhidden)):
            orders = [list(range(len(text)))]
            kicker, alt = (self.kicker_end or (None,) * 3)[which], (self.hero_alt or (None,) * 3)[which]
            if kicker is not None and alt is not None and kicker <= alt:
                orders.append([*range(kicker), alt, *range(kicker, alt), *range(alt + 1, len(text))])
            counts.append(max(label_count([text[index] for index in order],
                                          [self.chains[which][index] for index in order]) for order in orders))
        return tuple(counts)

    def region_problem(self) -> str | None:
        """What the first p.value's region (the div.region nearest it) holds outside VALUE_REGION_CHILDREN: text other
        than whitespace directly in it, children other than its slots, each filled once and in order, a p.lbl whose
        text that shows (its text, no img's alt text and no folded content of a details without open, as it shows with
        every details closed; aria-hidden="true" alone hiding nothing) holds no letter or digit as label_text() reads
        it, or the p.value outside its div; None if it holds none of these, or if the p.value has no region."""
        if self.value_region_at is None:
            return None
        if self.value_region_at in self.region_texts:
            return "text other than whitespace directly in it"
        children = self.region_children.get(self.value_region_at, [])
        names = [shape_name(tag, classes) for tag, classes, _ in children]
        if len(names) != len(VALUE_REGION_CHILDREN) or any(name not in slot
                                                           for name, slot in zip(names, VALUE_REGION_CHILDREN)):
            return f"the children {', '.join(names) or 'none'}"
        if not label_text("".join(self.child_shown.get(children[0][2], []))):
            return "a p.lbl with no letter or digit in its text that shows"
        if children[1][2] not in self.value_lineage:
            return "the p.value outside its div"
        return None

    def region_class_problem(self) -> tuple[str, tuple[int, int]] | None:
        """The first class name of VALUE_REGION_CLASSES that the first p.value's region or an element inside it carries
        away from its place, with where its start tag starts: region only on that region, lbl only on its first child
        (its label) and value only on that p.value; None if there is none, or if the p.value has no region."""
        if self.value_region_at is None:
            return None
        children = self.region_children.get(self.value_region_at, [])
        places = {"region": self.value_region_at, "lbl": children[0][2] if children else None,
                  "value": self.values[0] if self.values else None}
        for at, lineage, classes in self.class_starts:
            if at == self.value_region_at or self.value_region_at in lineage:
                for name in classes:
                    if name in places and at != places[name]:
                        return name, at
        return None

    def stray_class(self, allowed: set[str],
                    within: tuple[int, int] | None = None) -> tuple[str, tuple[int, int]] | None:
        """The first class name outside allowed, with where its start tag starts, of the page's elements or, given
        within, of the element that starts there and the elements inside it; None if there is none."""
        for at, lineage, classes in self.class_starts:
            if within is None or at == within or within in lineage:
                for name in classes:
                    if name not in allowed:
                        return name, at
        return None

    def value_problem(self) -> str | None:
        """What the first p.value holds outside its pin, which leaves no visible-text model to apply there: a start
        tag other than an a with no attribute but href or an em with no attribute, a character of its text after NFC
        other than those of VALUE_SPACES, VALUE_SIGNS and VALUE_CATEGORIES (named with its code point and category),
        or, when it holds neither, no letter (Lu, Ll or Lt); None if it holds none of these."""
        if self.value_stray is not None:
            return self.value_stray
        text = unicodedata.normalize("NFC", "".join(self.value_text))
        stray = next((character for character in text if character not in VALUE_SPACES + VALUE_SIGNS
                      and unicodedata.category(character) not in VALUE_CATEGORIES), None)
        if stray is not None:
            return f"U+{ord(stray):04X} (category {unicodedata.category(stray)})"
        if not any(unicodedata.category(character) in ("Lu", "Ll", "Lt") for character in text):
            return "no letter"
        return None


def uppercase_here(open_elements: list[tuple[str, list[str]]]) -> bool | None:
    """Whether the stylesheets show the text of the last of open_elements, (name, classes) outermost first, in upper
    case (True) or as written (False), by the selector of UPPERCASE_SELECTORS or RESET_SELECTORS of highest
    specificity that matches it, an uppercase one on a tie; None when none matches it, so it shows its parent's."""
    upper, reset = ([specificity(selector) for selector in selectors if selector_matches(selector, open_elements)]
                    for selectors in (UPPERCASE_SELECTORS, RESET_SELECTORS))
    if reset and (not upper or max(reset) > max(upper)):
        return False
    return True if upper else None


def specificity(selector: str) -> tuple[int, int]:
    """The specificity of selector, which selector_matches() reads, as (.class parts, names other than *)."""
    parts = selector.replace(">", " ").split()
    return (sum(part.count(".") for part in parts),
            sum(1 for part in parts if part.split(".")[0] not in ("", "*")))


def selector_matches(selector: str, open_elements: list[tuple[str, list[str]]]) -> bool:
    """Whether selector (compound selectors, each a name or *, then .class parts, or .class parts alone, joined by
    descendant or child (>) combinators) matches the last of open_elements, (name, classes) outermost first, given
    the others as its ancestors."""
    parts = selector.replace(">", " > ").split()

    def compound(part: str, element: tuple[str, list[str]]) -> bool:
        name, *classes = part.split(".")
        return name in ("", "*", element[0]) and all(class_name in element[1] for class_name in classes)

    def match(index: int, depth: int) -> bool:
        if not compound(parts[index], open_elements[depth]):
            return False
        if index == 0:
            return True
        if parts[index - 1] == ">":
            return depth > 0 and match(index - 2, depth - 1)
        return any(match(index - 1, ancestor) for ancestor in range(depth - 1, -1, -1))

    return bool(open_elements) and match(len(parts) - 1, len(open_elements) - 1)


def label_text(text: str) -> str:
    """text as the label rule reads it: each character that label_ignored() names deleted; then decomposed by NFKD,
    which reads a fullwidth or other compatibility letter as its Latin letter (U+FF41 as a) and an accented letter as
    its letter and a mark; each Latin small capital (a character named LATIN LETTER SMALL CAPITAL and 1 letter, such
    as U+1D00) read as that capital letter; and then each character other than a letter or a digit (general category
    L or N), such as whitespace, punctuation, a symbol such as U+2800 or a mark, deleted, so no character between the
    label's words keeps it from counting."""
    return label_texts([text])[0]


def label_texts(texts: list[str]) -> list[str]:
    """Each of texts as label_text() reads it, with label_ignored() asked once for each character. NFKD reorders
    only combining marks, which the reading deletes, so the reading of joined texts is the join of their readings."""
    ignored = {ord(character): None for character in set("".join(texts)) if label_ignored(character)}
    texts = [unicodedata.normalize("NFKD", text.translate(ignored)) for text in texts]
    read = {}
    for character in set("".join(texts)):
        name = unicodedata.name(character, "")
        if name.startswith("LATIN LETTER SMALL CAPITAL ") and len(name) == len("LATIN LETTER SMALL CAPITAL X"):
            read[ord(character)] = name[-1]
        elif unicodedata.category(character)[0] not in "LN":
            read[ord(character)] = None
    return [text.translate(read) for text in texts]


def label_count(parts: list[str], chains: list[tuple]) -> int:
    """How many times the text that parts join to carries the About block's label (ABOUT_LABELS, case-sensitive),
    both read by label_text(), at most over every choice of showing or leaving out each optional group: chains gives,
    for each part, the keys of the groups it is in, outermost first (the folded content of a details without open,
    which a reader sees only once the details is opened, and an img's alt text, which a browser shows only when the
    image does not load), and a group inside another shows only when that one does. The labels of 1 choice are
    counted together, so the count is the most that any 1 choice gives. Each group is read as the run of parts that
    carry its key (the page source tree rules keep a details' folded content to 1 run), and the labels are followed
    through the text from each tuple of their proper prefixes that the text read so far can end in (label_states())."""
    read = label_texts(list(parts) + list(ABOUT_LABELS))
    labels = tuple(read[len(parts):])
    # The parts as a tree: each group a list of the parts and groups it holds, in order, in the list around it.
    tree: list = []
    stack: list[tuple[tuple, list]] = [((), tree)]
    for text, chain in zip(read, chains):
        while chain[:len(stack[-1][0])] != stack[-1][0]:
            stack.pop()
        for depth in range(len(stack[-1][0]), len(chain)):
            stack[-1][1].append([])
            stack.append((chain[:depth + 1], stack[-1][1][-1]))
        stack[-1][1].append(text)
    return max(label_states(tree, {("",) * len(labels): 0}, labels).values())


def label_states(items: list, best: dict[tuple[str, ...], int], labels: tuple[str, ...]) -> dict[tuple[str, ...], int]:
    """best after the text that items (label_count()'s tree) hold: best maps each tuple of the labels' proper
    prefixes, 1 for each label, that the text read so far ends in to the most labels found in a choice that ends so.
    A group is read both left out and shown, and each tuple keeps the more labels of the 2."""
    for item in items:
        if isinstance(item, list):
            closed, opened = best, label_states(item, best, labels)
            best = {state: max(closed.get(state, -1), opened.get(state, -1)) for state in {**closed, **opened}}
            continue
        after: dict[tuple[str, ...], int] = {}
        for state, count in best.items():
            ends = []
            for prefix, label in zip(state, labels):
                joined = prefix + item
                found = joined.count(label)
                count += found
                tail = joined[joined.rfind(label) + len(label):] if found else joined
                ends.append(next(tail[len(tail) - size:] for size in range(min(len(label) - 1, len(tail)), -1, -1)
                                 if label.startswith(tail[len(tail) - size:])))
            after[tuple(ends)] = max(after.get(tuple(ends), 0), count)
        best = after
    return best


def label_ignored(character: str) -> bool:
    """Whether the label rule deletes character: a character of general category Cf (format), a
    Default_Ignorable_Code_Point (DEFAULT_IGNORABLE), a character of tools/check-install-page.py's ZERO_WIDTH other
    than U+00A0, or U+0000 (which a browser ignores in body text)."""
    code = ord(character)
    return (unicodedata.category(character) == "Cf" or any(first <= code <= last for first, last in DEFAULT_IGNORABLE)
            or character in install_gate().ZERO_WIDTH.replace("\u00a0", "") + "\0")


def line_column(text: str, index: int) -> tuple[int, int]:
    """The (line, column) of index in text, as HTMLParser.getpos() reports where a tag starts."""
    return text.count("\n", 0, index) + 1, index - text.rfind("\n", 0, index) - 1


def pinned_mast(config: dict, page: dict, base: str) -> str:
    """The header block MAST_BLOCK pins for 1 page, with the values site.json gives."""
    pages_by_id = {entry["id"]: entry for entry in config["pages"]}
    items = "".join(
        MAST_ITEM.format(href=base + pages_by_id[page_id]["path"], current=' aria-current="page"' if page_id == page["id"]
                         else "", label=html.escape(pages_by_id[page_id]["nav_label"], quote=False))
        for page_id in config["nav"]
    )
    return MAST_BLOCK.format(base=base, name=config["name"], tld=config["tld"], items=items, github=config["github"],
                             switch=SCHEME_SWITCH)


def about_line(base: str) -> str:
    """The landing page's About row at base, as specification 7.24 (baseline 1.7.0) gives it: 1 ordinary space
    after each dot span and none before it, so a line breaks only after a dot."""
    links = (f'<a href="{base}disclosure/">Disclosure</a>', f'<a href="{base}license/">Licence</a>',
             f'<a href="https://posluns.ca/privacy/" target="_blank" rel="noopener noreferrer">Privacy{NEW_TAB}</a>',
             f'<a href="https://posluns.ca/security/" target="_blank" rel="noopener noreferrer">Security{NEW_TAB}</a>')
    return '<p class="about">' + (ABOUT_DOT + " ").join(links) + "</p>"


def about_block(base: str) -> str:
    """The landing page's whole About block at base: ABOUT_BLOCK around about_line(), as specification 7.24 gives it."""
    return ABOUT_BLOCK.format(row=about_line(base))


def with_about(content: str, page: dict, base: str, logo_alt: str | None = None) -> str:
    """A page's content with, on the landing page only, the About block of specification 7.24 written in directly
    after the end tag of the value paragraph's region. It refuses, first, a source outside the page source grammar
    (source_problem(): tokens the parser and a browser read alike, elements of SOURCE_ELEMENTS only, no noscript
    inside a noscript, attributes of SOURCE_ATTRIBUTES only) or with an html, head, body or frameset start
    tag (the generator writes the page's html, head and body: HTML5 copies a stray html or body start tag's attributes
    onto the page's own, a stray head is refused because the generator writes the head, and
    tools/check-install-page.py reads a frameset start tag as hiding the whole page) or a math start tag (inside math,
    a browser can read a title, textarea, script or style element's content as markup, which the parser reads as text;
    validate() refuses svg, the other such element), each also as the parser reads it; then a start tag with a hidden
    attribute whose value holds until-found in any letter case (UNTIL_FOUND); then a start tag or text that a
    browser's tree builder would place elsewhere, a table child out of TABLE_ORDER, or a summary after text in its
    details (misnested(), PageScan.table_ranks and PageScan.details_text, the page source tree rules), and, right after
    source_problem(), a source with a bidi formatting character (bidi_control()); then a source with an
    element whose classes include about, a source whose text carries the About block's label (PageScan.labels(), with
    scripting on and off: scripting_off()), and a
    landing page source without exactly 1 p.value, with that p.value inside an element of INERT_TAGS, hidden by
    itself or by an ancestor as tools/check-install-page.py reads hiding, holding markup or text outside its pin
    (PageScan.value_problem()), or with no div.region among its ancestors, or with a class name outside
    VALUE_REGION_CLASSES in that region, or with that region holding other than VALUE_REGION_CHILDREN
    (PageScan.region_problem()), or with 1 of those class names away from its place there
    (PageScan.region_class_problem()); and last, any source with a class name outside SOURCE_CLASSES (class_pin()),
    then any source with a class of PLACED_CLASSES outside its pinned place, a second section.hero, an element of
    PLACED_CHILDREN with text or children outside their pinned order, a data-copy attribute outside the committed copy
    button (COPY_BUTTON_PIN), or a hero image whose alt text is not logo_alt, site.json's, which
    build() passes; without it, any hero image is refused (placement_pin()). The rules here that read a parse share 1
    PageScan of the source, and the label rule reads a second, with scripting off (scripting_off()). Other reads are
    of the source text itself, such as the grammar's, bidi_control()'s (every character, with its character
    references decoded) and end_tag_end()'s, which finds where the parser read the region's end tag end; the About
    block goes there."""
    where = page["source"]
    problem = source_problem(content)
    if problem is not None:
        raise BuildError(f"{where}: {problem}")
    bidi = bidi_control(content)
    if bidi is not None:
        raise BuildError(f"{where}: the page source holds {bidi}")
    scan = PageScan()
    scan.feed(content)
    scan.close()
    if scan.document_tags:
        tag, at = scan.document_tags[0]
        raise BuildError(f"{where}: a stray <{tag}> start tag {source_at(at)}; the generator writes the page's html, "
                         "head and body, so a page source may carry none of them, nor a frameset")
    if scan.maths:
        raise BuildError(f"{where}: a <math> start tag {source_at(scan.maths[0])}; inside math, a browser can read a "
                         "title, textarea, script or style element's content as markup, which the parser reads as text")
    if scan.until_found:
        raise BuildError(f"{where}: a hidden attribute with until-found {source_at(scan.until_found[0])}; "
                         f"{UNTIL_FOUND}")
    if scan.misnested:
        what, at, why = scan.misnested[0]
        raise BuildError(f"{where}: {what} {source_at(at)}; {why}")
    if scan.about_classes:
        raise BuildError(f"{where}: an element whose classes include about; the generator writes the About block of "
                         "specification 7.24 itself, on the landing page only")
    if any(scan.labels()) or any(scripting_off(content).labels()):
        raise BuildError(f"{where}: the About block's label in the page source's text; the generator writes it, in "
                         "the About block of specification 7.24, on the landing page only")
    if page["path"] != "":
        class_pin(scan, where)
        placement_pin(scan, where, logo_alt)
        return content
    if len(scan.values) != 1 or scan.values[0] not in scan.live_starts or scan.values[0] in scan.hidden_starts:
        raise BuildError(f"{where}: the landing page source must carry exactly 1 p.value, outside every element of "
                         "INERT_TAGS and not hidden by itself or by an ancestor as tools/check-install-page.py reads "
                         "hiding; the About block goes after its region")
    if scan.value_problem() is not None:
        raise BuildError(f"{where}: {VALUE_PIN} ({scan.value_problem()})")
    if scan.value_region_end is None:
        raise BuildError(f"{where}: the value paragraph has no enclosing div.region, after which the About block goes")
    stray = scan.stray_class(VALUE_REGION_CLASSES, scan.value_region_at)
    if stray is not None:
        raise BuildError(f"{where}: a class name {stray[0]!r} {source_at(stray[1])}, in the value paragraph's region; "
                         "there a page source carries only the class names of VALUE_REGION_CLASSES (region, lbl and "
                         "value), since a stylesheet rule can hide or move an element by a class, such as .copy or "
                         ".figure .stack")
    if scan.region_problem() is not None:
        raise BuildError(f"{where}: the value paragraph's region {source_at(scan.value_region_at)} holds "
                         f"{scan.region_problem()}; {VALUE_REGION_PIN}")
    stray = scan.region_class_problem()
    if stray is not None:
        raise BuildError(f"{where}: the class name {stray[0]!r} {source_at(stray[1])} is away from its place in the "
                         "value paragraph's region; there region sits only on the region, lbl only on its label and "
                         "value only on the value paragraph, since .region lays out an element as a grid of a label "
                         "column and a content column (VALUE_REGION_CLASSES)")
    class_pin(scan, where)
    placement_pin(scan, where, logo_alt)
    # The index just after the region's end tag, as the parser read it: under the grammar (END_TAG), </div> with its
    # name in any ASCII letter case, then ASCII whitespace if any, before its >.
    at = end_tag_end(content, scan.value_region_end)
    if at is None:
        raise BuildError(f"{where}: the value paragraph's region has no end tag that the grammar admits")
    return content[:at] + about_block(base) + content[at:]


def end_tag_end(text: str, position: tuple[int, int]) -> int | None:
    """The index in text just after the end tag that starts at position, (line, column) as getpos() and line_column()
    give it, written as the page source grammar admits one (END_TAG: its name, then ASCII whitespace if any); None
    if no such end tag starts there."""
    line, column = position
    # The lines before it, each with its "\n", then the column.
    found = END_TAG.match(text, sum(len(part) + 1 for part in text.split("\n")[:line - 1]) + column)
    return found.end() if found is not None else None


def class_pin(scan: PageScan, where: str) -> None:
    """Refuse a page source, as scan reads it, with a class name outside SOURCE_CLASSES, naming where it starts."""
    stray = scan.stray_class(SOURCE_CLASSES)
    if stray is not None:
        raise BuildError(f"{where}: a class name {stray[0]!r} {source_at(stray[1])}; a page source carries only the "
                         "class names of SOURCE_CLASSES; adding one needs a review of the stylesheet rules that name "
                         "it, such as .scheme .sun, which hides an element")


def scripting_off(text: str) -> PageScan:
    """text read by PageScan as a browser with scripting off shows it, for labels(): the text that shows keeps the
    content of each noscript, which such a browser renders as page elements, as the parser reads it, with the hiding
    of each element in it and around it applying (the noscript itself hides only by its attributes, read as on a
    span); every other element of INERT_TAGS is still read as not rendered."""
    scan = PageScan(scripting=False)
    scan.feed(text)
    scan.close()
    return scan


def source_shape(content: str) -> PageScan:
    """content read by PageScan, for rail_pin() and rail(), which read a page source before with_about() does: the
    same tokens, self-closing tags and end tags as every other rule reads."""
    shape = PageScan()
    shape.feed(content)
    shape.close()
    return shape


def shape_name(tag: str, classes: list[str]) -> str:
    """An element as PLACED_CHILDREN names it: its name, then each of its class names, sorted, after a dot."""
    return tag + "".join(f".{name}" for name in sorted(set(classes)))


def placement_pin(shape: PageScan, where: str, logo_alt: str | None) -> None:
    """Refuse a page source, as shape (with_about()'s PageScan) reads it, with a class name of PLACED_CLASSES on an
    element other than its pinned element, without its companion classes or attributes, under another parent, or
    (for copy) after text or an element in its parent; with a second section.hero, since the label rule reads the
    narrow-width order of 1 hero; with an element of PLACED_CHILDREN (for entries, an a inside
    it) that holds text other than whitespace directly, or children outside its slots, in their order, each filled
    at most once; with a data-copy attribute other than on a button.copy whose value is its parent's id and whose
    content is only the text Copy (COPY_BUTTON_PIN); or with an img in a div.hero-art whose alt text is not logo_alt.
    Each refusal names where the start tag starts."""
    for index, (tag, classes, attrs, at, parent, after) in enumerate(shape.elements):
        above = shape.elements[parent] if parent is not None else None
        for name in classes:
            if name not in PLACED_CLASSES:
                continue
            element, companions, parents, needs, first = PLACED_CLASSES[name]
            fits = any(wanted == "*" or (above is None if wanted == "" else above is not None and (
                above[0] == wanted.split(".")[0] and all(part in above[1] for part in wanted.split(".")[1:])))
                for wanted in parents)
            if (tag != element or not set(companions) <= set(classes) or not fits
                    or any(need not in attrs for need in needs) or (first and after)):
                place = shape_name(element, [name, *companions]) + "".join(f" with {need}" for need in needs)
                inside = " or ".join("any element" if wanted == "*" else "no element" if wanted == "" else wanted
                                     for wanted in parents)
                raise BuildError(f"{where}: the class name {name!r} {source_at(at)} is outside its pinned place; a "
                                 "stylesheet rule places an element with it out of its source order, so a page source "
                                 f"carries it only on {place}, {'first ' if first else ''}inside {inside} "
                                 "(PLACED_CLASSES)")
        if "data-copy" in attrs and (tag != "button" or "copy" not in classes or above is None
                                     or attrs["data-copy"] != above[2].get("id")
                                     or any(child[4] == index for child in shape.elements)
                                     or "".join(shape.own_texts.get(index, [])) != "Copy"):
            raise BuildError(f"{where}: a data-copy attribute {source_at(at)} outside the copy button's pinned form; "
                             f"{COPY_BUTTON_PIN}")
    heroes = [at for _, classes, _, at, _, _ in shape.elements if "hero" in classes]
    if len(heroes) > 1:
        raise BuildError(f"{where}: a second section.hero {source_at(heroes[1])}; a page source carries at most 1 "
                         "hero, the one whose narrow-width order the label rule reads")
    for index, (tag, classes, attrs, at, parent, after) in enumerate(shape.elements):
        lineage, up = [], parent
        while up is not None:
            lineage.append(shape.elements[up])
            up = shape.elements[up][4]
        key = next((name for name in classes if name in PLACED_CHILDREN and name != "entries"), None)
        if key is None and tag == "a" and any("entries" in ancestor[1] for ancestor in lineage):
            key = "entries"
        if key is None:
            continue
        slots, slot = PLACED_CHILDREN[key], 0
        children = [child for child in shape.elements if child[4] == index]
        for child in children:
            while slot < len(slots) and shape_name(child[0], child[1]) not in slots[slot]:
                slot += 1
            slot += 1
        if index in shape.texts or slot > len(slots):
            order = ", ".join(" or ".join(names) for names in slots)
            raise BuildError(f"{where}: the {shape_name(tag, classes)} {source_at(at)} holds text or children outside "
                             "its pinned order; a stylesheet places its children by grid area, so it holds only "
                             f"{order}, each at most once and in that order, and no text (PLACED_CHILDREN)")
        if key == "hero-art" and any(child[2].get("alt") != logo_alt for child in children):
            raise BuildError(f"{where}: the img in the div.hero-art {source_at(at)} has an alt text other than "
                             "site.json's logo_alt; at 600 px and below a browser shows it in the kicker's row, before "
                             "the statement")


def rail_pin(content: str, where: str) -> None:
    """Refuse a page source, with its tokens written in and before rail() writes the rail at <!--rail-->, that carries
    a class name of RAIL_CLASSES or more than 1 <!--rail-->, naming where the start tag starts in that source (the
    rail, written in on the same line, would move a later column only)."""
    if content.count("<!--rail-->") > 1:
        raise BuildError(f"{where}: more than 1 <!--rail-->; the generator writes 1 rail there")
    for _, classes, _, (line, column), _, _ in source_shape(content).elements:
        for name in classes:
            if name in RAIL_CLASSES:
                raise BuildError(f"{where}: the class name {name!r} at line {line}, column {column} of the source with "
                                 "its tokens written in, which only the rail the generator writes at <!--rail--> "
                                 "carries; above 1000 px .doc > .rail shows it at the top of the third column, "
                                 "whatever its place in the source")


def bidi_control(text: str) -> str | None:
    """The first character of BIDI_CONTROLS in text, as written or as a character reference that html.unescape()
    decodes, named with its code point, as a refusal; None if there is none."""
    found = next((character for character in html.unescape(text) if character in BIDI_CONTROLS), None)
    if found is None:
        return None
    return (f"a bidi formatting character, U+{ord(found):04X}, which reorders the text a browser shows and which the "
            "label rule reads in its stored order")


def validate(page_html: str, page: dict, config: dict, base: str) -> PageScan:
    where = page["source"]
    problems = []
    bidi = bidi_control(page_html)
    if bidi is not None:
        problems.append(f"the page holds {bidi}")
    if 'aria-current="true"' in page_html:
        problems.append('a static aria-current="true"; the rail is marked by rail.js')
    # As written or as a character reference that html.unescape() decodes (&mdash; among them), anywhere in the page.
    if any(dash in html.unescape(page_html) for dash in ("\u2013", "\u2014")):
        problems.append("an en or em dash")
    switch = page_html.find(SCHEME_SWITCH)
    about = page_html.find(about_block(base)) if page["path"] == "" else -1
    scan = PageScan(line_column(page_html, switch) if switch != -1 else None,
                    line_column(page_html, about) if about != -1 else None)
    scan.feed(page_html)
    scan.close()
    # In the text the parser reads (character references decoded, each img's alt text among it), with a space where a
    # tag or comment parts it.
    if re.search(r"what this is", " ".join(scan.text), re.I):
        problems.append('"what this is" framing')
    # Each required block starts as a parsed element outside every element of INERT_TAGS.
    for required in (SKIP_LINK, '<main id="main-content">', '<footer class="family wrap">', COPY_STATUS):
        if page_html.count(required) != 1 or line_column(page_html, page_html.find(required)) not in scan.live_starts:
            problems.append(f"{required!r} must appear exactly once, outside every element of INERT_TAGS")
    # The switch is the only parsed element with data-scheme-toggle; the element it sits in and the one before it;
    # the end tag of its parent starts where it ends.
    parent, previous = scan.switch_parent or ("", []), scan.switch_previous or ("", [])
    if (page_html.count(SCHEME_SWITCH) != 1 or scan.toggles != [line_column(page_html, switch)] or scan.inert_toggle
            or parent[0] != "header" or "mast" not in parent[1]
            or previous[0] != "nav" or "nav" not in previous[1]
            or scan.switch_parent_end != line_column(page_html, switch + len(SCHEME_SWITCH))):
        problems.append("the light and dark switch must appear exactly once, as the last child of header.mast, after nav.nav, "
                        "outside every element of INERT_TAGS, and no other element may carry data-scheme-toggle")
    # The page's body opens with the skip link and the header block, each on its own line as the generator writes
    # them, so no element wraps header.mast and only the skip link precedes it in the body.
    block = pinned_mast(config, page, base)
    top = "<body>\n" + SKIP_LINK + "\n" + block
    if (page_html.count(block) != 1 or page_html.count(top) != 1
            or line_column(page_html, page_html.find(top)) != scan.body_at):
        problems.append("the header block is not, once and byte for byte, the header.mast markup MAST_BLOCK pins, "
                        "after the skip link at the start of the page's body")
    if re.search(r"<svg", page_html.replace(SCHEME_SWITCH, "", 1), re.I):
        problems.append("an inline <svg> other than the light and dark switch")
    # with_about() refuses a source outside the page source grammar, such as one that ends inside a tag or a comment,
    # and any math start tag in one; the page is read again for a math start tag only, as the parser reads it.
    if scan.maths:
        problems.append("a <math> start tag in the page, which no page source may carry")
    scheme_tags = {line_column(page_html, match.start()) for match in re.finditer(
        r'<script data-cfasync="false" src="' + re.escape(base)
        + r'assets/baseline/scheme\.js\?v=[0-9]+\.[0-9]+\.[0-9]+"></script>', page_html)}
    # Each script element that loads scheme.js, read with character references decoded and names in lower
    # case, so another spelling of a second load counts; PageScan refuses a tag that carries an attribute
    # twice, and resolve_links refuses a root-relative src that names no generated, pinned or allowlisted
    # path, such as a percent-encoded one.
    scheme_loads = [at for at, src in scan.loads
                    if src.split("#", 1)[0].split("?", 1)[0] == base + "assets/baseline/scheme.js"]
    if len(scheme_loads) != 1 or scheme_loads[0] not in scheme_tags or page_html.count("scheme.js") != 1:
        problems.append("scheme.js must load exactly once, with data-cfasync=\"false\" and no defer")
    elif not scan.sheets or scan.sheets[0] < scheme_loads[0]:
        problems.append("scheme.js must load before the first stylesheet")
    elif scheme_loads[0] in scan.outside_head or any(at in scan.outside_head for at in scan.sheets):
        problems.append("scheme.js and every stylesheet must load inside <head>")
    problems += scan.problems
    if scan.open:
        problems.append(f"elements left open: {[tag for tag, _ in scan.open]}")
    if scan.h1 != 1 or scan.inert_h1:
        problems.append(f"{scan.h1} h1 elements; exactly 1 is required, outside every element of INERT_TAGS")
    duplicates = sorted({i for i in scan.ids if scan.ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate ids {duplicates}")
    for attrs in scan.scripts:
        kind = attrs.get("type", "").strip().lower()
        if "src" not in attrs and kind in EXECUTABLE_TYPES:
            problems.append("an inline executable <script>")
        if kind == "application/ld+json" and base != "/":
            problems.append("a JSON-LD block on a draft page")
        elif kind == "application/ld+json" and page.get("noindex"):
            problems.append("a JSON-LD block on a noindex page")
    if base != "/" and scan.robots != ["noindex, nofollow"]:
        problems.append("a draft page must carry exactly 1 robots meta, noindex, nofollow")
    elif base == "/" and page.get("noindex") and scan.robots != ["noindex, nofollow"]:
        problems.append("a noindex page must carry exactly 1 robots meta, noindex, nofollow")
    elif base == "/" and not page.get("noindex") and scan.robots:
        problems.append("an indexable page carries a robots meta")
    if scan.inert_robots:
        problems.append("a robots meta inside an element of INERT_TAGS")
    allow = set(config["root_allowlist"])
    if page["id"] not in config["about_linkers"]:
        for tag, value in scan.links:
            if tag == "a" and any(value.split("#", 1)[0] == base + config_path for config_path in config["about_paths"]):
                problems.append(f"{value} links a page only the landing page links (specification 7.24)")
    # On the landing page, exactly 1 p.value starts as a parsed element outside every element of INERT_TAGS, as the
    # required blocks do, is not hidden by itself or by an ancestor as tools/check-install-page.py reads hiding, and
    # holds nothing outside its pin (PageScan.value_problem()); its region holds exactly VALUE_REGION_CHILDREN
    # (PageScan.region_problem()); the whole About block, once and byte for byte, starts where the end tag of its
    # region ends; and the region and
    # the block each have exactly the ancestors ABOUT_ANCESTORS as the parser reads the page, so no element wraps
    # either. The block's ancestors are then the region's, the value paragraph's outermost 4: none is an element of
    # INERT_TAGS, and none hides the block, since none hides the value paragraph. The block holds no element of
    # INERT_TAGS, and the only elements in it that hide are its dot spans (aria-hidden="true") and the two notices
    # NEW_TAB writes in its row (span.vh, "(opens in a new tab)"). The block's row is then the only parsed element
    # whose classes include about. On any other page, no such element appears, inside an element of INERT_TAGS or
    # not. The page's text, and its text that shows in both readings (PageScan.labels()), with scripting on and off
    # (scripting_off()), each carry the block's label once on the landing page, inside the block (with the block's
    # label taken out, they carry none), and nowhere else, in any letter case where the stylesheets show text in upper
    # case (uppercase_here()).
    if page["path"] == "":
        block, value = about_block(base), scan.values[0] if len(scan.values) == 1 else None
        at = page_html.find(block)
        ancestors = [(name, [part for part in ASCII_WHITESPACE.split(classes.format(site_class=config["site_class"]))
                             if part]) for name, classes in ABOUT_ANCESTORS]
        if (value is None or value not in scan.live_starts or value in scan.hidden_starts
                or page_html.count(block) != 1 or scan.value_region_end is None
                or end_tag_end(page_html, scan.value_region_end) != at
                or scan.value_region_ancestors != ancestors or scan.about_ancestors != ancestors
                or len(scan.about_classes) != 1):
            problems.append("the About block must appear exactly once, byte for byte as specification 7.24 gives it "
                            "(ABOUT_BLOCK), directly after the end tag of the region of the only p.value, which "
                            "starts outside every element of INERT_TAGS and is not hidden by itself or by an ancestor "
                            "as tools/check-install-page.py reads hiding, the region and the block each with exactly "
                            "the ancestors ABOUT_ANCESTORS (html, body, main and div.wrap), and no other About markup "
                            "may appear")
        if value is not None and scan.value_problem() is not None:
            problems.append(f"{VALUE_PIN} ({scan.value_problem()})")
        if scan.region_problem() is not None:
            problems.append(f"the value paragraph's region holds {scan.region_problem()}; {VALUE_REGION_PIN}")
        unlabelled_html = page_html.replace(block, block.replace(f">{ABOUT_LABELS[0]}<", "><", 1), 1)
        unlabelled = PageScan()
        unlabelled.feed(unlabelled_html)
        unlabelled.close()
        if (scan.labels() != (1, 1, 1) or any(unlabelled.labels()) or scripting_off(page_html).labels() != (1, 1, 1)
                or any(scripting_off(unlabelled_html).labels())):
            problems.append("the About block's label must appear in the page's text exactly once, inside the About "
                            "block (specification 7.24)")
    else:
        if scan.about_classes:
            problems.append("About markup (an element whose classes include about), which only the landing page's "
                            "About block carries (specification 7.24)")
        if any(scan.labels()) or any(scripting_off(page_html).labels()):
            problems.append("the About block's label in the page's text, which only the landing page's About block "
                            "carries (specification 7.24)")
    for tag, value in scan.links:
        if value.startswith(("https://", "http://")):
            if tag != "a":
                problems.append(f"<{tag}> loads an external resource {value}")
            continue
        if value.startswith("#"):
            if value[1:] not in scan.live_ids:
                problems.append(f"the in-page link {value} has no target outside every element of INERT_TAGS")
            continue
        if value.startswith("/"):
            path = value.split("#", 1)[0].split("?", 1)[0]
            if path in allow and tag == "a":
                continue
            if not value.startswith(base):
                problems.append(f"{value} is outside the base path {base}")
            continue
        problems.append(f"{value!r} is neither a base-path link nor an external link")
    if problems:
        raise BuildError(f"{where}: " + "; ".join(problems))
    return scan


# Build ------------------------------------------------------------------------

def out_dir_for(base: str) -> Path:
    if base == "/":
        return Path("site")
    if not re.match(r"^/[a-z0-9-]+/$", base):
        raise Unreadable(f"base {base!r} must be / or a single folder such as /draft/")
    return Path("site") / base.strip("/")


def check_sitemap_exclusion(root: Path, base: str, pages: list) -> None:
    """The page-metadata and sitemap gates read */index.html, so each noindex page there must be excluded.

    While a draft is staged, tools/sitemap-config.json must exclude the draft's home page
    (recorded exclusion E1). At base /, it must exclude exactly the noindex pages whose output
    is a */index.html (the /draft/ holding page), so every indexable page is checked and no
    noindex page is.
    """
    config = read_json(root, Path("tools/sitemap-config.json"))
    exclude = config.get("exclude")
    if not isinstance(exclude, list):
        raise Unreadable("tools/sitemap-config.json has no exclude list")
    stray = [entry for entry in exclude if isinstance(entry, str) and entry.endswith("/index.html") and entry != "404.html"]
    if base == "/":
        wanted = sorted(
            page["path"] + "index.html"
            for page in pages
            if page.get("noindex") and page["path"].endswith("/") and page["path"].count("/") == 1
        )
    else:
        wanted = [base.strip("/") + "/index.html"]
    if sorted(stray) != wanted:
        raise BuildError(
            f"tools/sitemap-config.json excludes {sorted(stray)}, but base {base} needs exactly {wanted}; "
            "a noindex page that the gates would read as */index.html is excluded, and no other page is"
        )


def static_files(config: dict) -> list[str]:
    """The files committed by hand beside the generated ones at site/ (site.json static_files)."""
    listed = config.get("static_files", [])
    if not isinstance(listed, list) or not all(isinstance(name, str) and name for name in listed):
        raise Unreadable("site-src/site.json static_files must be a list of file paths")
    if len(set(listed)) != len(listed):
        raise Unreadable("site-src/site.json static_files lists a file twice")
    for name in listed:
        parts = name.split("/")
        if name.startswith("/") or "" in parts or "." in parts or ".." in parts or name.startswith("assets/baseline/"):
            raise Unreadable(f"site-src/site.json static_files entry {name!r} is not a plain path under site/")
    return listed


def file_kb(root: Path, name: str) -> str:
    path = root / DOWNLOADS / name
    try:
        size = os.stat(path).st_size
    except OSError as error:
        raise Unreadable(f"{DOWNLOADS / name} could not be read: {error}") from error
    return f"{round(size / 1000)} KB"


def build(
    root: Path,
    base: str | None = None,
    date: str | None = None,
    release: dict | None = None,
    config: dict | None = None,
) -> tuple[Path, dict[str, bytes], dict]:
    """Render every output file in memory.

    ``release`` replaces site-src/release.json and ``config`` replaces site-src/site.json when
    given (the release writer's new values, before it writes them).
    """
    if config is None:
        config = read_json(root, SRC / "site.json")
    elif not isinstance(config, dict):
        raise Unreadable("the site.json override is not a JSON object")
    base = base or config.get("base")
    if not isinstance(base, str):
        raise Unreadable("site-src/site.json has no base")
    out = out_dir_for(base)
    pages = config.get("pages")
    if not isinstance(pages, list) or not pages:
        raise Unreadable("site-src/site.json lists no pages")
    for page in pages:
        modified = page.get("modified")
        if modified is not None and (not isinstance(modified, str) or not DATE.match(modified)):
            raise Unreadable(f"site-src/site.json page {page.get('id')!r} modified {modified!r} is not YYYY-MM-DD")
    if date is not None and not DATE.match(date):
        raise BuildError(f"--date {date!r} is not YYYY-MM-DD")
    check_sitemap_exclusion(root, base, pages)
    statics = static_files(config) if out == Path("site") else []
    release = load_release(root, release)
    baseline_version, pinned = load_pin(root)
    config["pinned"] = pinned
    asset_tokens = {"baseline": baseline_version}
    outputs: dict[str, bytes] = {}
    if (root / SRC / "assets" / "site.css").exists():
        site_css = read_text(root, SRC / "assets" / "site.css")
        asset_tokens["site.css"] = hashlib.sha256(site_css.encode("utf-8")).hexdigest()[:12]
        outputs["assets/site.css"] = site_css.encode("utf-8")
    commentary = read_json(root, SRC / "examples-commentary.json")
    examples_html, example_count = render_examples(root, commentary)
    _, channel_sections = parse_sections(read_text(root, REFS / "context-modes.md"), str(REFS / "context-modes.md"))
    _, checklist_sections = parse_sections(read_text(root, REFS / "qa-checklist.md"), str(REFS / "qa-checklist.md"))
    instructions = read_text(root, DOWNLOADS / "cleanlanguage.md").rstrip("\n")
    # Each AI family has its own setup page under install/; the home page counts them.
    families = sum(1 for page in pages if str(page.get("path", "")).startswith("install/") and page.get("path") != "install/")
    if families == 0:
        raise BuildError("site-src/site.json lists no family install pages under install/; the home page would read 0 assistants")
    values = {
        "base": base,
        **release,
        "size.full": file_kb(root, "cleanlanguage.md"),
        "chars.full": str(len(instructions)),
        "count.examples": str(example_count),
        "count.channels": str(len(channel_sections)),
        "count.modes": str(operating_mode_count(root)),
        "count.families": str(families),
        "examples": examples_html,
        "channels": render_reference_sections(channel_sections, "", "Channel", str(REFS / "context-modes.md")),
        "checklist": render_clauses(checklist_sections, str(REFS / "qa-checklist.md")),
        "instructions": html.escape(instructions, quote=False),
    }
    pages_by_id = {page["id"]: page for page in pages}
    for page_id in config.get("nav", []):
        if page_id not in pages_by_id:
            raise Unreadable(f"site-src/site.json nav names unknown page {page_id!r}")
    scans: dict[str, PageScan] = {}
    the_footer = footer(config, base)
    for page in pages:
        fragment = read_text(root, SRC / "pages" / page["source"])
        content = substitute(fragment, values, page["source"])
        rail_pin(content, page["source"])
        content = content.replace("<!--rail-->", rail(config, page, base, content))
        content = with_about(content, page, base, config.get("logo_alt"))
        document = "\n".join(
            [
                head(config, page, base, asset_tokens, date),
                "<body>",
                SKIP_LINK,
                mast(config, page, base, pages_by_id),
                '<main id="main-content">',
                f'<div class="wrap">{content.strip()}</div>',
                "</main>",
                the_footer,
                COPY_STATUS,
                "</body>",
                "</html>",
                "",
            ]
        )
        scans[page["path"]] = validate(document, page, config, base)
        name = page["path"] + "index.html" if not page["path"].endswith(".html") else page["path"]
        outputs[name] = document.encode("utf-8")
    clashes = sorted(set(statics) & set(outputs))
    if clashes:
        raise BuildError(f"site-src/site.json static_files names generated files {clashes}")
    config["static_files_in_out"] = statics
    resolve_links(root, out, base, config, outputs, scans)
    return out, outputs, config


def resolve_links(root: Path, out: Path, base: str, config: dict, outputs: dict, scans: dict) -> None:
    """Every internal link resolves to a generated page and anchor, a pinned baseline file or an allowlisted root file."""
    ids_by_file = {}
    for path, scan in scans.items():
        name = path + "index.html" if not path.endswith(".html") else path
        ids_by_file[name] = scan.live_ids
    problems = []
    for path, scan in scans.items():
        for tag, value in scan.links:
            if not value.startswith("/"):
                continue
            target, _, fragment = value.partition("#")
            target = target.split("?", 1)[0]
            if target in config["root_allowlist"]:
                if not (root / "site" / target.lstrip("/")).is_file():
                    problems.append(f"{path or 'index'}: allowlisted root file {target} does not exist")
                continue
            relative = target[len(base):]
            name = relative + "index.html" if relative == "" or relative.endswith("/") else relative
            if name in outputs:
                if fragment and fragment not in ids_by_file.get(name, set()):
                    problems.append(f"{path or 'index'}: {value} names an anchor the target page lacks")
                continue
            if name in config["pinned"]:
                continue  # a pinned baseline file; tools/check-baseline-pin.py checks it on disk
            problems.append(f"{path or 'index'}: {value} does not resolve inside {base}")
    if problems:
        raise BuildError("; ".join(problems))


def existing_files(directory: Path) -> list[str]:
    found = []
    if not directory.exists():
        return found
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            raise Unreadable(f"{current} could not be listed: {error}") from error
        for entry in entries:
            relative = Path(entry.path).relative_to(directory).as_posix()
            if relative == "assets/baseline":
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            else:
                found.append(relative)
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the site on the shared template.")
    parser.add_argument("--check", action="store_true", help="compare the committed output with a fresh build")
    parser.add_argument("--base", help="override the base path (/ renders the promotion build)")
    parser.add_argument("--out", help="write into this folder instead (with --base, for tests)")
    parser.add_argument("--date", help="replace every page's modified date in the / build, YYYY-MM-DD")
    parser.add_argument("--promote", action="store_true", help="allow a --base / build to write into site/ while site.json names another base")
    parser.add_argument("--root", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else REPO_ROOT
    try:
        out, outputs, config = build(root, args.base, args.date)
        target = Path(args.out) if args.out else root / out
        if args.check:
            if args.out or args.base:
                raise BuildError("--check compares the configured base path's committed output only")
            present = existing_files(target)
            statics = config["static_files_in_out"]
            problems = [f"{out / name} is listed in static_files but missing" for name in statics if name not in present]
            for name in sorted(set(present) | set(outputs)):
                if name in statics:
                    continue
                if name not in outputs:
                    problems.append(f"{out / name} is not generated or listed in static_files; remove it or add it to the sources")
                elif name not in present:
                    problems.append(f"{out / name} is missing; run tools/build-site.py")
                elif (target / name).read_bytes() != outputs[name]:
                    problems.append(f"{out / name} differs from a fresh build; run tools/build-site.py")
            if problems:
                print("Generated site problems found:")
                for problem in problems:
                    print(f"  - {problem}")
                return 1
            print(
                f"The committed {out}/ matches a fresh build ({len(outputs)} files, beside {len(statics)} listed static files) "
                f"and every internal link resolves inside {config['base']}."
            )
            return 0
        if out == Path("site") and not args.out and config.get("base") != "/" and not args.promote:
            raise BuildError(
                f"refusing to write the / build into site/ while site-src/site.json names base {config.get('base')!r}, without --promote"
            )
        for name, data in outputs.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        removed = [name for name in existing_files(target) if name not in outputs] if not args.out and out != Path("site") else []
        for name in removed:
            (target / name).unlink()
        print(f"wrote {len(outputs)} files to {target}" + (f" and removed {len(removed)} stale files" if removed else ""))
        return 0
    except BuildError as error:
        print(f"build-site: {error}", file=sys.stderr)
        return 1
    except Unreadable as error:
        print(f"build-site: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
