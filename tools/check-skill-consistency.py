#!/usr/bin/env python3
"""Check the quality checklist's dash line names exactly the skill's dash carve-outs.

``SKILL.md`` makes the dash rule absolute "apart from the carve-outs in
Preserve legitimate language", and that section lists them in one bullet.
``references/qa-checklist.md`` restates the rule in its own dash bullet, which
ends "Keep a dash only in" followed by a list. The checklist once named a
narrower list than the skill (row 98), and nothing caught it. This check makes
that drift fail (row 105).

What it verifies
----------------

It reads only ``cleanlanguage/skills/cleanlanguage/SKILL.md`` and
``cleanlanguage/skills/cleanlanguage/references/qa-checklist.md``, and keeps no
copy of the carve-out list:

1. SKILL.md holds exactly one sentence "the carve-outs in <section>.", and
   exactly one heading "## <section>".
2. That section, which runs to the next heading of level 1 or 2, holds exactly
   one bullet beginning "quoted language". That phrase is the one hand-kept
   anchor: if SKILL.md loses it, this check exits 3 rather than passing.
3. The checklist holds exactly one bullet that mentions a dash, and that
   bullet holds exactly one clause "Keep a dash only in <list>." or "Keep a
   dash only inside <list>.".
4. Both lists are split the same way: at each comma, then at each " or " and
   " and ", with a leading "or" or "and" dropped. An empty item is malformed.
5. The two lists are compared as sets, in both directions. Each SKILL.md item
   the checklist lacks and each checklist item SKILL.md does not name is
   reported.

A bullet runs on over the indented lines that follow it. The generated copies
of the checklist need no check here: tools/build-portable-text.py --check and
tools/build-site.py --check compare them with this source.

What it does not verify
-----------------------

Residuals, named here because the check reads text by fixed rules:

- an item that holds a comma, " or " or " and " splits into several items.
  Both lists split the same way, so the same item in both still matches, but
  the check compares the pieces, not the items: "a and b, c" in one list and
  "a, b and c" in the other pass;
- items are compared as exact text after the split, so a change of letter case
  or of wording is reported as drift, and an item that repeats in one list is
  not;
- a full stop followed by a space or a line end inside an item ends the clause
  early;
- the pointer sentence is found by its words, not by its place in the dash
  rule, and the section's other bullets, including the range separator rule,
  are not compared;
- other restatements of the carve-outs, such as the hand-maintained portable
  renderings and the site's standard and patterns pages, are not read.

Usage: python3 -I tools/check-skill-consistency.py

Exit codes:
  0  the checklist dash line names exactly the skill's carve-outs
  1  the lists differ
  2  the command line was wrong
  3  a file could not be read, or a sentence, heading, bullet or clause above
     is missing, is not unique, or holds an empty item
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
DASH = re.compile(r"\bdash(?:es)?\b", re.IGNORECASE)
KEEP = re.compile(r"\bKeep a dash only in(?:side)? (.+?)\.(?=\s|$)", re.S)
JOINER = re.compile(r"\s+(?:or|and)\s+")
LEADING_JOINER = re.compile(r"^(?:or|and)\s+")


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


def bullets(lines: list[str]) -> list[str]:
    """Each "- " bullet in lines, joined with the indented lines that continue it."""
    found: list[str] = []
    in_bullet = False
    for line in lines:
        if line.startswith("- "):
            found.append(line[2:].strip())
            in_bullet = True
        elif in_bullet and line[:1] in (" ", "\t") and line.strip():
            found[-1] += " " + line.strip()
        else:
            in_bullet = False
    return found


def split(text: str, where: str) -> list[str]:
    """The items of a list such as "a, b, or c", split at commas and at "or" and "and"."""
    items: list[str] = []
    for piece in text.split(","):
        piece = LEADING_JOINER.sub("", " ".join(piece.split()))
        items += [item.strip() for item in JOINER.split(piece)]
    if not all(items):
        raise Unreadable(f"{where} holds an empty item: {text!r}")
    return items


def skill_items(text: str) -> tuple[str, list[str]]:
    """The carve-out section's name and the items of its "quoted language" bullet."""
    pointers = POINTER.findall(text)
    if len(pointers) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one sentence "the carve-outs in <section>.", found {len(pointers)}')
    section = pointers[0].strip()
    lines = text.split("\n")
    starts = [n for n, line in enumerate(lines) if line.rstrip() == f"## {section}"]
    if len(starts) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one heading "## {section}", found {len(starts)}')
    body = []
    for line in lines[starts[0] + 1:]:
        if re.match(r"#{1,2} ", line):
            break
        body.append(line)
    anchored = [bullet for bullet in bullets(body) if bullet.startswith(ANCHOR)]
    if len(anchored) != 1:
        raise Unreadable(f'{SKILL}: expected exactly one bullet beginning "{ANCHOR}" in section "{section}", found {len(anchored)}')
    return section, split(anchored[0].rstrip(" ;."), f'{SKILL}, section "{section}"')


def checklist_items(text: str) -> list[str]:
    """The items of the "Keep a dash only in" clause of the checklist's one dash bullet."""
    dashes = [bullet for bullet in bullets(text.split("\n")) if DASH.search(bullet)]
    if len(dashes) != 1:
        raise Unreadable(f"{CHECKLIST}: expected exactly one bullet that mentions a dash, found {len(dashes)}")
    clauses = KEEP.findall(dashes[0])
    if len(clauses) != 1:
        raise Unreadable(f'{CHECKLIST}: expected exactly one clause "Keep a dash only in <list>." '
                         f"in the dash bullet, found {len(clauses)}")
    return split(clauses[0], f"{CHECKLIST} dash bullet")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the quality checklist's dash line names exactly the skill's dash carve-outs."
    )
    parser.parse_args()

    try:
        section, wanted = skill_items(read_text(SKILL))
        named = checklist_items(read_text(CHECKLIST))
    except Unreadable as error:
        print(f"check-skill-consistency: {error}", file=sys.stderr)
        return 3

    where = f'{SKILL}, section "{section}"'
    missing = [item for item in wanted if item not in named]
    extra = [item for item in named if item not in wanted]
    if missing or extra:
        for item in missing:
            print(f"check-skill-consistency: the checklist dash line lacks {item!r}, a carve-out in {where}.")
        for item in extra:
            print(f"check-skill-consistency: the checklist dash line adds {item!r}, which {where} does not name.")
        return 1
    print(f"check-skill-consistency: the checklist dash line names the {len(set(wanted))} carve-outs in {where}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
