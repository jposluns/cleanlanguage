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
copy of the carve-out list. It reads each file as blocks (headings, bullets
and paragraphs) with HTML comments and the lines inside fenced code blocks
left out, so a sentence, heading or bullet that exists only inside them is
missing:

1. SKILL.md holds exactly one sentence "the carve-outs in <section>.", and
   exactly one heading "## <section>".
2. That section, which runs to the next heading of level 1 or 2, holds exactly
   one bullet that lists "quoted language" as one of its items, in any place.
   That phrase is a hand-kept anchor: if SKILL.md loses it, this check exits 3
   rather than passing. Items are found by splitting at each comma, then at
   each " or " and " and ", with a leading "or" or "and" dropped. An empty
   item in that bullet is malformed.
3. The checklist holds exactly one block that mentions a dash, that block is a
   bullet, and no HTML comment or fenced code block in the checklist mentions
   a dash.
4. That whole bullet, with every line and sub-bullet that continues it, reads
   exactly OPENING, then " Keep a dash only in ", then the SKILL.md bullet as
   SKILL.md writes it, without its closing ";" or ".", then ".". A line break
   or a run of spaces counts as 1 space. Any other wording, order or sentence
   in the bullet is drift; the check then prints the bullet it expected and
   the one it found, and, when the found bullet holds exactly one clause "Keep
   a dash only in <list>." or "Keep a dash only inside <list>.", each SKILL.md
   item that clause lacks and each item it adds.

A bullet starts with "-", "*" or "+" at the start of a line. It runs on over
each later line that is indented, across blank lines too, and over each
unindented line until a blank line or a line that starts another block (a
heading, a "-", "*", "+" or "1." list marker, a quotation, a rule or a fence).
The generated copies of the checklist need no check here:
tools/build-portable-text.py --check and tools/build-site.py --check compare
them with this source.

What it does not verify
-----------------------

Residuals, named here because the check reads text by fixed rules:

- only the one SKILL.md bullet is compared: a carve-out SKILL.md states in
  another bullet, another section, another sentence or an HTML comment is not
  read, and the section's other bullets, including the range separator rule,
  are not compared;
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
  bullet is read as part of it, and an HTML comment opener written inside
  inline code is read as a comment. A fence keeps its opening line, so a
  fenced block inside the dash bullet still fails the comparison;
- the items an exit 1 report names come from the split above, so an item that
  holds a comma, " or " or " and " is named in pieces; the comparison itself
  is of the whole bullet;
- the pointer sentence is found by its words, not by its place in the dash
  rule;
- other restatements of the carve-outs, such as the hand-maintained portable
  renderings and the site's standard and patterns pages, are not read.

Usage: python3 -I tools/check-skill-consistency.py

Exit codes:
  0  the checklist dash bullet matches the bullet built from the SKILL.md one
  1  the checklist dash bullet differs from it
  2  the command line was wrong
  3  a file could not be read, a sentence, heading, bullet or block above is
     missing or not unique, a comment or fenced code block in the checklist
     mentions a dash, or the SKILL.md bullet holds an empty item
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
FENCE = re.compile(r"[ \t]*(`{3,}|~{3,})")
HEADING = re.compile(r"#{1,6}(?:[ \t]|$)")
BULLET = re.compile(r"[-*+](?:[ \t]+|$)")
RULE = re.compile(r"(?:[-*_][ \t]*){3,}$")
BLOCK = re.compile(r"#{1,6}(?:[ \t]|$)|[-*+][ \t]|1[.)][ \t]|>|`{3}|~{3}|(?:[-*_][ \t]*){3,}$")


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


def visible(text: str) -> list[str]:
    """The lines of text with HTML comments and the lines inside fenced code blocks blanked.

    A fence keeps its opening line, so a fence inside a bullet still changes that bullet's text.
    """
    lines: list[str] = []
    fence = ""
    in_comment = False
    for line in text.split("\n"):
        if fence:
            if line.strip().startswith(fence) and not line.strip().strip(fence[0]):
                fence = ""
            lines.append("")
            continue
        opened = None if in_comment else FENCE.match(line)
        if opened:
            fence = opened.group(1)
            lines.append(line)
            continue
        kept = ""
        while line:
            if in_comment:
                end = line.find("-->")
                if end < 0:
                    break
                line, in_comment = line[end + 3:], False
            else:
                start = line.find("<!--")
                if start < 0:
                    kept += line
                    break
                kept, line, in_comment = kept + line[:start], line[start + 4:], True
        lines.append(kept)
    return lines


def blocks(text: str) -> list[tuple[str, str]]:
    """Each heading, bullet and paragraph of the visible text, as (kind, text) with spaces collapsed.

    A bullet's text holds every line that continues it and drops its marker.
    """
    found: list[list[str]] = []
    open_kind = ""
    after_blank = False
    for line in visible(text):
        if not line.strip():
            after_blank = True
            continue
        indented = line[:1] in (" ", "\t")
        if open_kind and (indented and (open_kind == "bullet" or not after_blank)
                          or not after_blank and not BLOCK.match(line)):
            found[-1][1] += " " + line
        elif HEADING.match(line):
            found.append(["heading", line])
            open_kind = ""
        elif BULLET.match(line) and not RULE.match(line):
            found.append(["bullet", BULLET.sub("", line, count=1)])
            open_kind = "bullet"
        else:
            found.append(["text", line])
            open_kind = "text"
        after_blank = False
    return [(kind, " ".join(words.split())) for kind, words in found]


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
    starts = [n for n, (kind, words) in enumerate(found) if kind == "heading" and words == f"## {section}"]
    if len(starts) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one heading "## {section}", found {len(starts)}')
    body = []
    for kind, words in found[starts[0] + 1:]:
        if kind == "heading" and re.match(r"#{1,2}(?: |$)", words):
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
    hidden = len(DASH.findall(text)) - sum(len(DASH.findall(words)) for kind, words in dashes)
    if len(dashes) != 1 or dashes[0][0] != "bullet" or hidden:
        kinds = ", ".join(kind for kind, words in dashes) or "none"
        raise Unreadable(f"{CHECKLIST}: expected exactly one block that mentions a dash, a bullet, and no mention "
                         f"in a comment or fenced code; found {len(dashes)} ({kinds}) and {hidden} hidden")
    return dashes[0][1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that the quality checklist's dash bullet matches the skill's carve-out bullet."
    )
    parser.parse_args()

    try:
        section, listing = carve_out_list(read_text(SKILL))
        found = dash_bullet(read_text(CHECKLIST))
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
