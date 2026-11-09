#!/usr/bin/env python3
"""Check that the quality checklist's dash bullet matches the skill's carve-out bullet.

``SKILL.md`` makes the dash rule absolute "apart from the carve-outs in
Preserve legitimate language", and that section lists them in one bullet.
``references/qa-checklist.md`` restates the rule in its own dash bullet. The
checklist once named a narrower list than the skill (row 98), and nothing
caught it. This check makes that drift fail (row 105).

The check runs no Markdown renderer. Where this docstring says what a
renderer might make of a line, it gives the reason for a refusal, not a
behaviour the check or its tests confirm.

What it verifies
----------------

It reads only ``cleanlanguage/skills/cleanlanguage/SKILL.md`` and
``cleanlanguage/skills/cleanlanguage/references/qa-checklist.md``, and keeps no
copy of the carve-out list. It reads each file as raw text, with no region of
either file left out, split into blocks (headings, bullets and paragraphs):

1. Neither file holds any of the following, which this check does not model.
   The check exits 3 at a line that holds one and names its file and line
   number; only LF ends a line. For the entries before the last, it exits at
   the first line that holds any of them, reading SKILL.md and then the
   checklist; the last entry says when its refusal runs.
   - a carriage return (U+000D), so a CRLF line ending is refused;
   - any other character for which Python's str.isspace() is true, apart from
     the space (U+0020) and LF (U+000A), such as a tab (U+0009) or U+00A0;
   - "<!--" anywhere, or three backticks or three tildes in a row anywhere,
     so neither file holds an HTML comment or a fenced code block;
   - a thematic break: a line of 3 or more of one mark, "-", "*" or "_", with
     any number of spaces before, between and after them, such as "---" or
     "* * *". The marks must be identical, so this check reads a line that
     mixes them, such as "_*_", as text;
   - a setext heading underline: a line that holds one run of "=" or one run
     of "-", with any number of spaces before and after it, under a line
     that is not blank;
   - a heading or block quote marker indented by 1 or more spaces: 1 or more
     spaces, then "#" to "######" followed by a space or the end of the
     line, or ">". The reason for the refusal: a renderer might read such a
     line as a heading or block quote at an indent that depends on how
     deeply the open list items are nested, which this check does not track,
     and any fixed window of indents leaves a deeper nesting open, so the
     check refuses the line at any indent rather than read it as text or as
     part of an open bullet;
   - a list marker indented by 1 to 3 spaces: 1 to 3 spaces, then "-", "*"
     or "+", or 1 to 9 digits with "." or ")", each followed by a space or
     the end of the line. The reason for the refusal: a renderer might read
     such a line as a list item, and this check reads a marker only at the
     start of the line, so it refuses the line rather than read it as text
     or as part of an open bullet. This
     also refuses a sub-bullet indented by 2 or 3 spaces, and a wrapped line
     that starts with a number and a full stop, such as "  404. as its
     status;";
   - an empty list item line: "-", "*" or "+", or 1 to 9 digits with "." or
     ")", at the start of the line, followed by nothing or only spaces. The
     check would read it as an empty bullet or as text. The reason for the
     refusal: what a renderer might make of it depends on what comes before,
     so the file must hold none.
     A lone "-" under a line that is not blank is refused as a setext
     underline first;
   - a bullet marker followed by 2 or more spaces: "-", "*" or "+" at the start
     of the line, then 2 or more spaces. After a blank line, this check reads
     each line that is not blank and is indented by 2 spaces or more as part of
     the open bullet. The reason for the refusal: a renderer might read such a
     line as part of the bullet only when the line is indented at least as far
     as the bullet's text, which a second, third or fourth space after the
     marker moves further in, so the file must hold none. A line that holds
     only the marker and spaces is refused first, as an empty list item or, for
     a "-" under a line that is not blank, as a setext underline;
   - a line that starts with "<" after 0 to 3 spaces. The reason for the
     refusal: a renderer might open an HTML block at such a line, and might run
     some kinds, such as one opened by "<script>" or "<pre>", on past blank
     lines and headings until a closing tag, so a block opened above a span
     could hold the span. A "<" later in a line is refused only in the two
     spans item 5 covers, and there on every line but the SKILL.md section's
     own heading line, unless it starts "<!--", which is refused anywhere. Item
     5 accepts that heading line without reading its characters, because its
     text is the section name item 2 matches, not part of the compared bullet;
   - a line that is not blank and starts with exactly 1 space, after a blank
     line under a bullet. The reason for the refusal: a renderer might start a
     new paragraph at such a line, because it is indented less than the
     bullet's text, which starts after the marker and 1 space, while this check
     would read the line as part of the bullet. After a blank line under a
     heading or a paragraph, this check reads such a line as the start of a new
     paragraph, and item 5 refuses it in its two spans. This refusal runs after
     the others in this list have run over both files, so a line they refuse
     keeps its message. It runs over each file before any later item reads that
     file, and exits at the first such line in it.
   The one exception is the front matter at the top of SKILL.md: when line 1
   and a later line are exactly "---", line 1 and the first such later line
   are not refused as a thematic break or an underline. Every other refusal
   applies to the lines between them too, so an indented YAML list item there,
   such as "  - Read" under a key, makes the check exit 3. So a space and LF
   are the only whitespace either file holds, and the only separators the
   check reads.
2. SKILL.md holds exactly one sentence "the carve-outs in <section>.", and
   exactly one heading "## <section>". The heading may end with a closing
   run of "#" after a space, followed by nothing but spaces, which the check
   does not read as part of its text, so "## <section> ##" is the same heading;
   "### <section>" is not, and neither is "## <section>##".
3. That section, which runs from its heading up to the next heading of level
   1 or 2, or to the end of the file where there is none, holds only the
   lines item 5 accepts, and exactly one bullet that lists "quoted
   language" as one of its items, in any place. That phrase is a hand-kept
   anchor: if SKILL.md loses it, this check exits 3 rather than passing. Items
   are found by splitting at each comma, then at each " or " and " and ", with
   a leading "or" or "and" dropped. An empty item in that bullet is malformed.
4. The checklist holds exactly one block that mentions a dash, and that block
   is a bullet. The lines after the heading line above that block, or from
   line 1 where there is none, up to the next heading line, or to the end of
   the file where there is none, hold only the lines item 5 accepts. A
   refusal there names the 2 edges, each a heading line or an end of the file.
5. In the two spans items 3 and 4 name, the check accepts only these lines:
   - a blank line, empty or holding only spaces;
   - in SKILL.md, the section's own heading line, as item 2 finds it;
   - plain text: a line that starts with neither a space nor a list marker
     ("-", or 1 to 9 digits with "." or ")", each followed by a space or the
     end of the line), and that holds only ASCII letters, digits, spaces and
     the characters ' ( ) , - . : ; and the backtick;
   - a bullet: "- " at the start of the line, followed by plain text.
   The characters are the ones the committed spans use. It exits 3 at the first
   other line in a span and names its file and line number, and, for a
   character outside that list, the character. Item 1 runs over each whole file
   before item 5 reads that file, so a line it refuses keeps its message, and
   item 4 checks the kind of the dash block before it reads the checklist span.
   Every line the check compares lies in these spans.
6. That whole bullet, with every line that continues it, reads exactly
   OPENING, then " Keep a dash only in ", then the SKILL.md bullet as
   SKILL.md writes it, without its closing ";" or ".", then ".". Any run of
   spaces and line breaks counts as 1 space. Any other wording, order or
   sentence in the bullet is drift; the check then prints the bullet it
   expected and the one it found, and, when the found bullet holds exactly one
   clause "Keep a dash only in <list>." or "Keep a dash only inside <list>.",
   each SKILL.md item that clause lacks and each item it adds.

A bullet starts with "-", "*" or "+" at the start of a line, followed by a
space or the end of the line. It runs on over each later line that starts with
a space, across blank lines too (after a blank line, item 1 refuses a line that
is not blank and starts with exactly 1 space), and over each other line until a
blank line or a line that starts with one of: "#" to "######" followed by a
space or the end of the line; "-", "*" or "+" followed by a space; "1." or "1)"
followed by a space; or ">". So a line such as "2. text" continues the bullet
when no blank line comes before it; item 5 refuses such a line in the two spans
it covers, because a renderer might read it as the start of an ordered list. A
line that holds only a list marker, such as "2.", "*" or "+", is refused as an
empty list item when the marker is at the start of the line, as an indented
list marker after 1 to 3 spaces, and, after 4 or more spaces, only in the two
spans item 5 covers; a lone "-" under a line that is not blank is refused as a
setext underline after any number of spaces, in the spans or outside them. The
generated copies of the checklist need no check here:
tools/build-portable-text.py --check and tools/build-site.py --check compare
them with this source.

What it does not verify
-----------------------

Residuals, named here because the check reads text by fixed rules:

- only the one SKILL.md bullet is compared: a carve-out SKILL.md states in
  another bullet, another section or another sentence is not read, and the
  section's other bullets, including the range separator rule, are not
  compared;
- the check does not read HTML comments, fenced code blocks, thematic breaks,
  setext headings, carriage returns or whitespace other than a space and LF;
  it refuses them. A future edit that adds one to either file, such as a
  comment, a fence, a "---" rule between sections, a CRLF line ending or a
  tab, makes the check exit 3 until the check is extended. Some refusals
  match a form wherever it occurs, not only where it opens the construct the
  refusal is for: a run of three backticks or three tildes anywhere, such as
  in inline code; a refused whitespace character anywhere, such as U+00A0
  inside a line of text; a run of "=" or "-" under any line that is not
  blank; a heading or block quote marker indented by 1 or more spaces at any
  indent, including where the line starts 4 or more columns past the start
  of the text of the innermost list item that holds it, or is indented by 4
  or more spaces with no list item holding it; a list marker indented by 1
  to 3 spaces, including a sub-bullet indented by 2 or 3 spaces and a
  wrapped line "  404. as its status;"; an empty list item line, even after
  a blank line, and even directly under a line of a paragraph outside any
  list; a bullet marker followed by 2 or more spaces, even when no later
  line is indented less than the bullet's text; and a line that starts with
  "<" after 0 to 3 spaces, including inline HTML or an autolink at the start
  of a line, also make it exit 3;
- item 5 is wider still: in its two spans it refuses every line it does not
  list, such as a line indented by 1 or more spaces that continues a bullet
  or paragraph, a bullet marked
  "*" or "+", a heading of level 3 to 6 in the carve-out section, a bullet
  whose text starts with a list marker, such as "- - x", and, on every line
  but the SKILL.md section's own heading line, any character outside its
  list, such as a non-ASCII letter, "*" for emphasis, "&" or "/". A future
  edit that adds such a line there makes the check exit 3 until the edit is
  rewritten or the check is extended;
- outside the two spans item 5 covers, a link title, the title of a link
  reference definition and the markup of raw HTML later in a line, other
  than a comment, are read as text like the rest of the file, so a pointer
  sentence there is found whether or not a rendering shows it. In the spans,
  apart from the SKILL.md section's own heading line, each of them needs a
  character item 5 refuses: "[" for a link title or the title of a link
  reference definition, and "<" for raw HTML. That heading line can hold a
  link title or raw HTML, because item 5 accepts it without reading its
  characters: its text is the section name item 2 matches, not part of the
  compared bullet;
- OPENING, the first sentence of the expected bullet, is a second hand-kept
  copy: rewording that sentence in the checklist fails until OPENING follows
  it;
- the checklist must mention a dash in one block only, so a second block that
  mentions a dash exits 3 even when it adds no carve-out. Finding the dash
  bullet by its opening instead would let a second bullet add a carve-out
  unseen, so the check stays fail-closed;
- a checklist block that grants a carve-out without the word "dash" or
  "dashes" is not read;
- the reader handles a small part of Markdown: a heading or block quote marker
  indented by 1 or more spaces, a list marker indented by 1 to 3 spaces, an
  empty list item line, a bullet marker followed by 2 or more spaces, a line
  that starts with "<" after 0 to 3 spaces, and a line that is not blank and
  starts with exactly 1 space after a blank line under a bullet are refused
  rather than read, and "<!--" written inside inline code is refused like a
  comment. Outside the two spans that item 5 covers, the reader reads a list
  item indented by 4 or more spaces under an open bullet, and a line such as
  "2. text" directly under a bullet line as part of that bullet, whatever a
  renderer makes of them. No compared text comes from those lines, but the
  pointer sentence and the checklist's mentions of a dash are found there;
- the items an exit 1 report names come only from the one Keep clause, so a
  carve-out the bullet adds anywhere else, such as in another sentence, is
  named by no item line, and with no Keep clause or more than
  one no item is named; the check still exits 1 and prints both bullets. The
  items come from the split above, so an item that holds a comma, " or " or
  " and " is named in pieces; the comparison itself is of the whole bullet;
- the pointer sentence is found by its words, not by its place in the dash
  rule;
- other restatements of the carve-outs, such as the hand-maintained portable
  renderings and the site's standard and patterns pages, are not read.

Usage: python3 -I tools/check-skill-consistency.py

Exit codes:
  0  the checklist dash bullet matches the bullet built from the SKILL.md one
  1  the checklist dash bullet differs from it
  2  the command line was wrong
  3  a file could not be read, a file holds a line item 1 or item 5 refuses, a
     sentence, heading, bullet or block above is missing or not unique, or the
     SKILL.md bullet holds an empty item
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = Path("cleanlanguage/skills/cleanlanguage/SKILL.md")
CHECKLIST = Path("cleanlanguage/skills/cleanlanguage/references/qa-checklist.md")

POINTER = re.compile(r"\bthe carve-outs in ([^.\n]+)\.")
ANCHOR = "quoted language"
OPENING = ("Remove every em and en dash, converting each to the punctuation the sentence needs; "
           "write numeric and date ranges with a hyphen or `to`.")
DASH = re.compile(r"\bdash(?:es)?\b", re.IGNORECASE)
KEEP = re.compile(r"\bKeep a dash only in(?:side)? (.+?)\.(?=\s|$)")
JOINER = re.compile(r"\s+(?:or|and)\s+")
LEADING_JOINER = re.compile(r"^(?:or|and)\s+")
CR = "\r"
COMMENT = "<!--"
FENCE = re.compile(r"`{3}|~{3}")
BREAK = re.compile(r" *([-*_])(?: *\1){2,} *$")
UNDERLINE = re.compile(r" *(?:=+|-+) *$")
INDENTED_HEADING = re.compile(r" +(?:#{1,6}(?: |$)|>)")
INDENTED_ITEM = re.compile(r" {1,3}(?:[-*+](?: |$)|[0-9]{1,9}[.)](?: |$))")
EMPTY_ITEM = re.compile(r"(?:[-*+]|[0-9]{1,9}[.)]) *$")
SPACED = re.compile(r"[-*+] {2}")
FRONT_MATTER = "---"
HEADING = re.compile(r"#{1,6}(?: |$)")
CLOSING = re.compile(r" #+ *$")
BULLET = re.compile(r"[-*+](?: +|$)")
BLOCK = re.compile(r"#{1,6}(?: |$)|[-*+] |1[.)] |>")
# The reason for the refusal: a renderer might open an HTML block at a line that starts with "<" after 0 to 3
# spaces, and might run some kinds on past blank lines and headings, so such a line outside the spans could hide them.
HTML = re.compile(r" {0,3}<")
# The characters a line of plain text may hold, apart from ASCII letters, digits and spaces: the ones the
# committed spans use. Every other character, such as "*", "_", "#", ">", "<", "[" or "&", is refused on every
# line of the spans but the SKILL.md section's own heading line, so emphasis, a thematic break of "*" or "_", a
# heading, a block quote, HTML, a link written with "[" or "<" and an entity are refused on those lines. A bare
# address such as www.example.com holds only accepted characters, so it is read as text there, whatever a renderer
# makes of it. Item 5 of the module docstring accepts that heading line without reading its characters, because its
# text is the section name, not part of the compared bullet.
OTHER = "'(),-.:;`"
NOT_ALLOWED = re.compile(r"[^A-Za-z0-9 '(),\-.:;`]")
# What a line of plain text may not start with, among the characters above: a space, or a list marker.
NOT_PLAIN = re.compile(r" |-(?: |$)|[0-9]{1,9}[.)](?: |$)")


class Unreadable(Exception):
    """A file could not be read, or a structure the check needs is missing or not unique."""


def read_text(path: Path) -> str:
    try:
        info = os.lstat(REPO_ROOT / path)
    except OSError as error:
        raise Unreadable(f"{path} could not be read: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise Unreadable(f"{path} is not a regular file")
    try:
        return (REPO_ROOT / path).read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise Unreadable(f"{path} could not be read: {error}") from error


def front_matter(path: Path, lines: list[str]) -> set[int]:
    """The line numbers of SKILL.md's front matter delimiters: line 1 and the first later line, when both are "---"."""
    if path == SKILL and lines[0] == FRONT_MATTER and FRONT_MATTER in lines[1:]:
        return {1, lines.index(FRONT_MATTER, 1) + 1}
    return set()


def plain_text(path: Path) -> str:
    """The text of path, which must hold none of the lines item 1 of the module docstring refuses."""
    text = read_text(path)
    lines = text.split("\n")
    delimiters = front_matter(path, lines)
    for number, line in enumerate(lines, start=1):
        if CR in line:
            raise Unreadable(f"{path}, line {number}: holds a carriage return (U+000D); this check reads only LF "
                             "as a line ending, so the file must hold none")
        other = [char for char in line if char.isspace() and char != " "]
        if other:
            raise Unreadable(f"{path}, line {number}: holds U+{ord(other[0]):04X}, whitespace other than a space; "
                             "this check reads no such whitespace, so the file must hold none")
        ruled = BREAK.match(line) or UNDERLINE.match(line) and number > 1 and lines[number - 2].strip()
        if ruled and number not in delimiters:
            raise Unreadable(f"{path}, line {number}: is a thematic break or a setext heading underline; this check "
                             "reads neither, so the file must hold none apart from the front matter delimiters at "
                             "the top of SKILL.md")
        if COMMENT in line:
            raise Unreadable(f'{path}, line {number}: holds "{COMMENT}"; this check reads no HTML comments, '
                             "so the file must hold none")
        if FENCE.search(line):
            raise Unreadable(f"{path}, line {number}: holds 3 backticks or 3 tildes in a row; this check reads "
                             "no fenced code blocks, so the file must hold none")
        if INDENTED_HEADING.match(line):
            raise Unreadable(f"{path}, line {number}: is a heading or block quote marker indented by 1 or more "
                             "spaces; this check reads a marker only at the start of the line, so the file must "
                             "hold none")
        if INDENTED_ITEM.match(line):
            raise Unreadable(f"{path}, line {number}: is a list marker indented by 1 to 3 spaces; this check reads "
                             "a marker only at the start of the line, so the file must hold none")
        if EMPTY_ITEM.match(line):
            raise Unreadable(f"{path}, line {number}: is a list marker with nothing after it, an empty list item; "
                             "this check reads no empty list items, so the file must hold none")
        if SPACED.match(line):
            raise Unreadable(f"{path}, line {number}: is a bullet marker followed by 2 or more spaces; this check "
                             "reads a bullet only with 1 space between its marker and its text, so the file must "
                             "hold none")
        if HTML.match(line):
            raise Unreadable(f'{path}, line {number}: starts with "<" after 0 to 3 spaces, where an HTML block can '
                             "open; this check reads no HTML blocks, so the file must hold none")
    return text


def blocks(path: Path, text: str) -> list[tuple[str, str, int]]:
    """Each heading, bullet and paragraph of the text, as (kind, text, first line number) with spaces collapsed.

    A bullet's text holds every line that continues it and drops its marker. A
    heading's text drops any closing run of "#", found on the line as written,
    before spaces are collapsed, so only a space separates it. plain_text() has
    refused every thematic break the text could hold, apart from the front
    matter delimiters, which are read as text. A line that is not blank and
    starts with exactly 1 space, after a blank line under a bullet, is refused,
    as item 1 of the module docstring says.
    """
    found: list[list] = []
    open_kind = ""
    after_blank = False
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            after_blank = True
            continue
        indented = line[:1] == " "
        if open_kind == "bullet" and after_blank and indented and line[1:2] != " ":
            raise Unreadable(f"{path}, line {number}: is indented by 1 space after a blank line under a bullet; a "
                             "renderer might start a new paragraph there, while this check would read the line as "
                             "part of the bullet, so the file must hold none")
        if open_kind and (indented and (open_kind == "bullet" or not after_blank)
                          or not after_blank and not BLOCK.match(line)):
            found[-1][1] += " " + line
        elif HEADING.match(line):
            found.append(["heading", CLOSING.sub("", line), number])
            open_kind = ""
        elif BULLET.match(line):
            found.append(["bullet", BULLET.sub("", line, count=1), number])
            open_kind = "bullet"
        else:
            found.append(["text", line, number])
            open_kind = "text"
        after_blank = False
    return [(kind, " ".join(words.split()), number) for kind, words, number in found]


def plain(line: str) -> bool:
    """Whether line starts as plain text: with a character other than a space, and with no marker NOT_PLAIN names."""
    return bool(line) and not NOT_PLAIN.match(line)


def read_lines(path: Path, text: str, first: int, last: int, span: str, own_heading: bool) -> None:
    """Refuse each line from first up to but not including last that item 5 of the module docstring does not accept.

    The lines are numbered from 1. When own_heading is true, line first is the
    span's own heading and is accepted.
    """
    lines = text.split("\n")
    for number in range(first, last):
        line = lines[number - 1]
        if not line.strip() or own_heading and number == first:
            continue
        words = line[2:] if line[:2] == "- " else line
        if not plain(words):
            accepted = "blank lines, the section heading, " if own_heading else "blank lines, "
            raise Unreadable(f"{path}, line {number}: is not a line this check reads in {span}, which must hold only "
                             f'{accepted}plain text and "- " bullets of plain text, each at the start of the line')
        other = NOT_ALLOWED.search(words)
        if other:
            raise Unreadable(f'{path}, line {number}: holds U+{ord(other[0]):04X} ("{other[0]}"), a character this '
                             f"check does not read in {span}; its text may hold only ASCII letters, digits, spaces "
                             f"and {' '.join(OTHER)}")


def heading(words: str) -> tuple[int, str]:
    """A heading block's level and its text, without its marker; blocks() has dropped any closing run of "#"."""
    level = len(words) - len(words.lstrip("#"))
    return level, words[level:].strip()


def items(text: str) -> list[str]:
    """The items of a list such as "a, b, or c", split at commas and at "or" and "and"."""
    found: list[str] = []
    for piece in text.split(","):
        piece = LEADING_JOINER.sub("", " ".join(piece.split()))
        found += [item.strip() for item in JOINER.split(piece)]
    return found


def carve_out_list(text: str) -> tuple[str, str]:
    """The carve-out section's name and its bullet that lists "quoted language", as SKILL.md writes it."""
    found = blocks(SKILL, text)
    pointers = POINTER.findall("\n".join(words for kind, words, number in found))
    if len(pointers) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one sentence "the carve-outs in <section>.", found {len(pointers)}')
    section = pointers[0].strip()
    starts = [n for n, (kind, words, number) in enumerate(found)
              if kind == "heading" and heading(words) == (2, section)]
    if len(starts) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one heading "## {section}", found {len(starts)}')
    body = []
    last = len(text.split("\n")) + 1
    for kind, words, number in found[starts[0] + 1:]:
        if kind == "heading" and heading(words)[0] <= 2:
            last = number
            break
        body.append((kind, words))
    read_lines(SKILL, text, found[starts[0]][2], last, f'section "{section}"', own_heading=True)
    anchored = [words.rstrip(" ;.") for kind, words in body
                if kind == "bullet" and ANCHOR in items(words.rstrip(" ;."))]
    if len(anchored) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one bullet in section "{section}" that lists "{ANCHOR}", '
                         f"found {len(anchored)}")
    if not all(items(anchored[0])):
        raise Unreadable(f'{SKILL}, section "{section}" holds an empty item: {anchored[0]!r}')
    return section, anchored[0]


def dash_bullet(text: str) -> str:
    """The text of the checklist's one block that mentions a dash, which must be a bullet."""
    found = blocks(CHECKLIST, text)
    dashes = [(kind, words, number) for kind, words, number in found if DASH.search(words)]
    # The kind runs first, so a heading or paragraph that mentions a dash is reported as such, not as a line of
    # the span around it.
    if len(dashes) != 1 or dashes[0][0] != "bullet":
        kinds = ", ".join(kind for kind, words, number in dashes) or "none"
        raise Unreadable(f"{CHECKLIST}: expected exactly one block that mentions a dash, a bullet; "
                         f"found {len(dashes)} ({kinds})")
    start = dashes[0][2]
    headings = [number for kind, words, number in found if kind == "heading"]
    above = [number for number in headings if number < start]
    below = [number for number in headings if number > start]
    first = max(above, default=0) + 1
    last = min(below, default=len(text.split("\n")) + 1)
    # Either edge can be a heading line or an end of the file, so the message names the 2 edges it read between.
    span = (f"the lines between {'the heading above the dash bullet' if above else 'the start of the file'} "
            f"and {'the next heading' if below else 'the end of the file'}")
    read_lines(CHECKLIST, text, first, last, span, own_heading=False)
    return dashes[0][1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that the quality checklist's dash bullet matches the skill's carve-out bullet."
    )
    parser.parse_args()

    try:
        skill, checklist = plain_text(SKILL), plain_text(CHECKLIST)
        section, listing = carve_out_list(skill)
        found = dash_bullet(checklist)
    except Unreadable as error:
        print(f"check-skill-consistency: {error}", file=sys.stderr)
        return 3

    where = f'{SKILL}, section "{section}"'
    wanted = items(listing)
    expected = f"{OPENING} Keep a dash only in {listing}."
    if found == expected:
        print(f"check-skill-consistency: the checklist dash bullet matches the carve-out bullet in {where}, "
              f"naming its {len(set(wanted))} carve-outs.")
        return 0
    print(f"check-skill-consistency: the checklist dash bullet does not match the carve-out bullet in {where}.")
    print(f"check-skill-consistency: expected: {expected}")
    print(f"check-skill-consistency: found: {found}")
    clauses = KEEP.findall(found)
    if len(clauses) == 1:
        named = items(clauses[0])
        for item in wanted:
            if item not in named:
                print(f"check-skill-consistency: the checklist dash bullet lacks {item!r}, a carve-out in {where}.")
        for item in named:
            if item not in wanted:
                print(f"check-skill-consistency: the checklist dash bullet adds {item!r}, which {where} does not name.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
