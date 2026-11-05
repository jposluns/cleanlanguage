#!/usr/bin/env python3
"""Check that the quality checklist's dash bullet matches the skill's carve-out bullet.

``SKILL.md`` makes the dash rule absolute "apart from the carve-outs in
Preserve legitimate language", and that section lists them in one bullet.
``references/qa-checklist.md`` restates the rule in its own dash bullet. The
checklist once named a narrower list than the skill (row 98), and nothing
caught it. This check makes that drift fail (row 105).

What it verifies
----------------

It reads only ``cleanlanguage/skills/cleanlanguage/SKILL.md`` and
``cleanlanguage/skills/cleanlanguage/references/qa-checklist.md``, and keeps no
copy of the carve-out list. It reads each file as raw text, with no region of
either file left out, split into blocks (headings, bullets and paragraphs):

1. Neither file holds any of the following, which this check does not model.
   The check exits 3 at the first line that holds one and names its file and
   line number; only LF ends a line.
   - a carriage return (U+000D), so a CRLF line ending is refused;
   - any other character for which Python's str.isspace() is true, apart from
     the space (U+0020) and LF (U+000A), such as a tab (U+0009) or U+00A0;
   - "<!--" anywhere, or three backticks or three tildes in a row anywhere,
     so neither file holds an HTML comment or a fenced code block;
   - a thematic break: a line of 3 or more of one mark, "-", "*" or "_", with
     any number of spaces before, between and after them, such as "---" or
     "* * *". The marks must be identical, as in CommonMark, so a line that
     mixes them, such as "_*_", is ordinary text;
   - a setext heading underline: a line that holds one run of "=" or one run
     of "-", with any number of spaces before and after it, under a line
     that is not blank.
   The one exception is the front matter at the top of SKILL.md: when line 1
   and a later line are exactly "---", line 1 and the first such later line
   are not refused as a thematic break or an underline. So a space and LF are
   the only whitespace either file holds, and the only separators the check
   reads.
2. SKILL.md holds exactly one sentence "the carve-outs in <section>.", and
   exactly one heading "## <section>". As in Markdown, the heading may end
   with a closing run of "#" after a space, followed by nothing but spaces,
   which is not part of its text, so "## <section> ##" is the same heading;
   "### <section>" is not, and neither is "## <section>##".
3. That section, which runs to the next heading of level 1 or 2, holds exactly
   one bullet that lists "quoted language" as one of its items, in any place.
   That phrase is a hand-kept anchor: if SKILL.md loses it, this check exits 3
   rather than passing. Items are found by splitting at each comma, then at
   each " or " and " and ", with a leading "or" or "and" dropped. An empty
   item in that bullet is malformed.
4. The checklist holds exactly one block that mentions a dash, and that block
   is a bullet.
5. That whole bullet, with every line and sub-bullet that continues it, reads
   exactly OPENING, then " Keep a dash only in ", then the SKILL.md bullet as
   SKILL.md writes it, without its closing ";" or ".", then ".". Any run of
   spaces and line breaks counts as 1 space. Any other wording, order or
   sentence in the bullet is drift; the check then prints the bullet it
   expected and the one it found, and, when the found bullet holds exactly one
   clause "Keep a dash only in <list>." or "Keep a dash only inside <list>.",
   each SKILL.md item that clause lacks and each item it adds.

A bullet starts with "-", "*" or "+" at the start of a line, followed by a
space or the end of the line. It runs on over each later line that starts with
a space, across blank lines too, and over each other line until a blank line
or a line that starts with one of: "#" to "######" followed by a space or the
end of the line; "-", "*" or "+" followed by a space; "1." or "1)" followed by
a space; or ">". So a line that is a lone "*" or "+", or that starts "2.",
continues the bullet when no blank line comes before it; a lone "-" there is
refused as a setext underline. The generated copies of the checklist need no
check here:
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
  tab, makes the check exit 3 until the check is extended. Some refusals are
  wider than the Markdown they stand for: a run of three backticks or three
  tildes anywhere, such as in inline code; a refused whitespace character
  anywhere, such as a U+00A0 that Markdown shows as text; and a run of "=" or
  "-" under any line that is not blank, whether or not Markdown reads it as
  an underline, also make it exit 3;
- other Markdown that a rendered page does not show, such as the title of a
  link reference definition or raw HTML other than a comment, is read as text
  like the rest of the file, so a pointer sentence there is found although a
  reader of the page does not see it;
- OPENING, the first sentence of the expected bullet, is a second hand-kept
  copy: rewording that sentence in the checklist fails until OPENING follows
  it;
- the checklist must mention a dash in one block only, so a second block that
  mentions a dash exits 3 even when it adds no carve-out. Finding the dash
  bullet by its opening instead would let a second bullet add a carve-out
  unseen, so the check stays fail-closed;
- a checklist block that grants a carve-out without the word "dash" or
  "dashes" is not read;
- the reader handles a small part of Markdown: a heading or list marker
  indented by 1 to 3 spaces is read as text, a list item nested under a
  bullet is read as part of it, and "<!--" written inside inline code is
  refused like a comment;
- the items an exit 1 report names come only from the one Keep clause, so a
  carve-out the bullet adds anywhere else, such as in another sentence or a
  sub-bullet, is named by no item line, and with no Keep clause or more than
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
  3  a file could not be read, a file holds a line item 1 refuses, a sentence,
     heading, bullet or block above is missing or not unique, or the SKILL.md
     bullet holds an empty item
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
FRONT_MATTER = "---"
HEADING = re.compile(r"#{1,6}(?: |$)")
CLOSING = re.compile(r" #+ *$")
BULLET = re.compile(r"[-*+](?: +|$)")
BLOCK = re.compile(r"#{1,6}(?: |$)|[-*+] |1[.)] |>")


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
    return text


def blocks(text: str) -> list[tuple[str, str]]:
    """Each heading, bullet and paragraph of the text, as (kind, text) with spaces collapsed.

    A bullet's text holds every line that continues it and drops its marker. A
    heading's text drops any closing run of "#", found on the line as written,
    before spaces are collapsed, so only a space separates it. plain_text() has
    refused every thematic break the text could hold, apart from the front
    matter delimiters, which are read as text.
    """
    found: list[list[str]] = []
    open_kind = ""
    after_blank = False
    for line in text.split("\n"):
        if not line.strip():
            after_blank = True
            continue
        indented = line[:1] == " "
        if open_kind and (indented and (open_kind == "bullet" or not after_blank)
                          or not after_blank and not BLOCK.match(line)):
            found[-1][1] += " " + line
        elif HEADING.match(line):
            found.append(["heading", CLOSING.sub("", line)])
            open_kind = ""
        elif BULLET.match(line):
            found.append(["bullet", BULLET.sub("", line, count=1)])
            open_kind = "bullet"
        else:
            found.append(["text", line])
            open_kind = "text"
        after_blank = False
    return [(kind, " ".join(words.split())) for kind, words in found]


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
    found = blocks(text)
    pointers = POINTER.findall("\n".join(words for kind, words in found))
    if len(pointers) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one sentence "the carve-outs in <section>.", found {len(pointers)}')
    section = pointers[0].strip()
    starts = [n for n, (kind, words) in enumerate(found) if kind == "heading" and heading(words) == (2, section)]
    if len(starts) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one heading "## {section}", found {len(starts)}')
    body = []
    for kind, words in found[starts[0] + 1:]:
        if kind == "heading" and heading(words)[0] <= 2:
            break
        body.append((kind, words))
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
    dashes = [(kind, words) for kind, words in blocks(text) if DASH.search(words)]
    if len(dashes) != 1 or dashes[0][0] != "bullet":
        kinds = ", ".join(kind for kind, words in dashes) or "none"
        raise Unreadable(f"{CHECKLIST}: expected exactly one block that mentions a dash, a bullet; "
                         f"found {len(dashes)} ({kinds})")
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
