#!/usr/bin/env python3
"""Tests for tools/check-skill-consistency.py: the checklist dash bullet against the skill's carve-outs.

The first case runs the gate on this repository and changes nothing. Each case
in CASES copies the gate and the 2 files it reads into a temporary repository
(under $TMPDIR), applies the case's change, runs the gate there as a separate
process and asserts its exit code and the fragments the case lists. The case
named "the committed tree" changes nothing, and the 2 cases named "the skill
list sorted, and the checklist with it" and "both bullets with 3 spaces after
the marker, each continued after a blank line by a line indented by 2 spaces",
the 4 cases whose names start "an ordered item", the 3 cases whose names
start "the skill bullet under", and the case named "a link title in the skill
bullet, with the same link in the dash bullet", each make 2 edits, one in
each file; the case whose name starts "the skill bullet last in its section"
makes 3, 2 in SKILL.md and 1 in the checklist; each other case makes 1
change, which edits, rewrites or removes a file. The cases that expect exit 0,
apart from the committed tree, make edits that keep the 2 files consistent;
the cases that expect exit 1 or 3 apply a fault. An exit 1 case also asserts
that the output says the bullet differs and names no item
beyond the case's list; an exit 3 case lists the structure the message must
name, or, for a line the gate refuses, the file and the line, counted in the
file as the case edits it, that the message must name. The case named
"main's checklist line" restores the exact line the checklist carried before
row 98 and expects the gate to name the 5 items it lacks and the 2 it adds.
One further case passes the gate an argument and asserts exit 2.

ITEMS is the carve-out list as SKILL.md states it today, in its order. The
edits that rewrite a list check that ITEMS is still there first, so a change
to that list fails this test until ITEMS follows it.
Exit 0 when every case passes; 1 otherwise, naming each failing case,
including a case whose change cannot find the text it edits.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-skill-consistency.py"
SKILL = "cleanlanguage/skills/cleanlanguage/SKILL.md"
CHECKLIST = "cleanlanguage/skills/cleanlanguage/references/qa-checklist.md"
FILES = [SKILL, CHECKLIST]
ITEMS = ["quoted language", "official titles", "product names", "standards text", "contractual wording"]
POINTER = "the carve-outs in Preserve legitimate language."
HEADING = "## Preserve legitimate language\n"
KEEP = "Keep a dash only in "
EXTRA = "Code samples may also keep a dash."
# The checklist's dash line on main before row 98.
OLD_LINE = ("- Remove every em and en dash, converting each to the punctuation the sentence needs; write numeric "
            "and date ranges with a hyphen or `to`. Keep a dash only inside quoted or verbatim material.\n")
# What the gate says when the bullet differs, and how each item line it then prints begins.
DIFFERS = "the checklist dash bullet does not match"
ITEM_LINES = ("check-skill-consistency: the checklist dash bullet lacks ",
              "check-skill-consistency: the checklist dash bullet adds ")
# The structure each exit 3 message names.
UNREAD = "could not be read"
NO_POINTER = 'sentence "the carve-outs in <section>."'
NO_HEADING = 'heading "' + HEADING.strip() + '"'
NO_ANCHOR = 'bullet in section "Preserve legitimate language" that lists "quoted language"'
NO_DASH = "one block that mentions a dash"
EMPTY = "holds an empty item"
COMMENT = 'holds "<!--"'
FENCED = "holds 3 backticks or 3 tildes in a row"
CR = "holds a carriage return"
TAB = "holds U+0009, whitespace other than a space"
NBSP = "holds U+00A0, whitespace other than a space"
RULED = "is a thematic break or a setext heading underline"
SPLIT = "Code samples may keep one too."
INDENTED_HEADING = "is a heading or block quote marker indented by 1 or more spaces"
INDENTED_ITEM = "is a list marker indented by 1 to 3 spaces"
EMPTY_ITEM = "is a list marker with nothing after it, an empty list item"
SPACED = "is a bullet marker followed by 2 or more spaces"
UNREAD_LINE = "is not a line this check reads in "
HTML = 'starts with "<" after 0 to 3 spaces'
LEAD_IN = "Do not mechanically delete:\n"
OTHER_BULLET = "- throat-clearing before the substantive point;\n"
CHECKLIST_HEADING = "## Mechanics\n"
# The heading after the carve-out section, which ends the section.
NEXT_HEADING = "## Match the context\n"
# A line that only item 5 refuses, for its "&", so it pins where each span starts and ends: refused on the first
# and last line of a span, and read as text just outside it.
EDGE = "x & y\n"
# How the gate names the checklist span, by the 2 edges it read between.
CHECKLIST_SPAN = "the lines between the heading above the dash bullet and "
# Lines the gate reads as plain text or as a bullet of plain text in the carve-out section; lines it refuses there
# by how they start; and lines it refuses there by a character, with the first such character.
PLAIN_LINES = ["-x", "1.x", "1234567890. x", ".x", "- -x", "AZ az 09", "x (y): 'z'; `w`, v."]
UNREAD_LINES = ["- - x", "- -", "- 2.", "- 123456789) x"]
CHARACTER_LINES = [("* x", "*"), ("+ x", "+"), ("### Note", "#"), ("###### x", "#"), ("> x", ">"), ("- #", "#"),
                   ("- > x", ">"), ("- <b>x</b>", "<"), ("#x", "#"), ("#######", "#"), ("+x", "+"), ("*x", "*"),
                   ("x <b>y</b>", "<"), ("- #x", "#"), ("x [y]", "["), ("x & y", "&"), ("x/y", "/"),
                   ("x \N{LATIN SMALL LETTER E WITH ACUTE}", "\N{LATIN SMALL LETTER E WITH ACUTE}"),
                   ("x\N{ZERO WIDTH SPACE}y", "\N{ZERO WIDTH SPACE}")]


def listed(items: list[str]) -> str:
    """Items written as SKILL.md writes them: "a", "a or b", or "a, b, or c"."""
    if len(items) < 3:
        return " or ".join(items)
    return ", ".join(items[:-1]) + ", or " + items[-1]


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(GATE, root / "tools" / GATE.name)
    for relative in FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name), *args],
                          capture_output=True, text=True)


def edit(relative: str, old: str, new: str):
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(f"{old!r} is not in {relative}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return apply


def dash_line(root: Path) -> str:
    """The checklist's one line that holds the Keep clause."""
    lines = [line for line in (root / CHECKLIST).read_text(encoding="utf-8").splitlines(keepends=True)
             if KEEP in line]
    if len(lines) != 1:
        raise AssertionError(f"{CHECKLIST} holds {len(lines)} lines with {KEEP!r}, not 1")
    return lines[0]


def prepend(relative: str, new: str):
    def apply(root: Path) -> None:
        path = root / relative
        path.write_text(new + path.read_text(encoding="utf-8"), encoding="utf-8")
    return apply


def append(relative: str, new: str):
    def apply(root: Path) -> None:
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + new, encoding="utf-8")
    return apply


def cut(relative: str, old: str, new: str):
    """Replace old, and everything after it in the file, with new."""
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(f"{old!r} is not in {relative}")
        path.write_text(text[:text.find(old)] + new, encoding="utf-8")
    return apply


def past_end(relative: str) -> str:
    """The gate's "<file>, line <n>: " for the first line after the committed file's last line, which ends in LF."""
    number = (REPO_ROOT / relative).read_text(encoding="utf-8").count("\n") + 1
    return f"{relative}, line {number}: "


def at(relative: str, old: str, below: int = 0) -> str:
    """The gate's "<file>, line <n>: " for the line below lines after the one where old starts in the committed file."""
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    number = text[:text.find(old)].count("\n") + 1 + below if old in text else "?"
    return f"{relative}, line {number}: "


def checklist_lists(items: list[str], keep: str = KEEP):
    return edit(CHECKLIST, KEEP + listed(ITEMS) + ".", keep + listed(items) + ".")


def skill_lists(items: list[str]):
    return edit(SKILL, "- " + listed(ITEMS) + ";", "- " + listed(items) + ";")


def replace_dash_line(new: str):
    return lambda root: edit(CHECKLIST, dash_line(root), new)(root)


def change_dash_line(change):
    """Replace the dash line with change(line), for faults that keep the line and add text around it."""
    return lambda root: edit(CHECKLIST, dash_line(root), change(dash_line(root)))(root)


def together(*faults):
    def apply(root: Path) -> None:
        for fault in faults:
            fault(root)
    return apply


def character(char: str) -> str:
    """How the gate names a character it does not read in a span."""
    return f'holds U+{ord(char):04X} ("{char}"), a character this check does not read in '


def lacks(item: str) -> str:
    return f"lacks {item!r}"


def adds(item: str) -> str:
    return f"adds {item!r}"


SKILL_LINE = "- " + listed(ITEMS) + ";"

CASES = [
    ("the committed tree", None, 0, []),
    ("the clause continued on an indented line", checklist_lists(ITEMS, "Keep a dash only in\n  "), 3,
        [at(CHECKLIST, KEEP, 1) + UNREAD_LINE]),
    ("the clause continued on an unindented line", checklist_lists(ITEMS, "Keep a dash only in\n"), 0, []),
    ("the skill bullet continued on an indented line", edit(SKILL, "text, or ", "text,\n  or "), 3,
        [at(SKILL, SKILL_LINE, 1) + UNREAD_LINE]),
    ("the skill bullet continued on an unindented line", edit(SKILL, "text, or ", "text,\nor "), 0, []),
    ("the skill list sorted, and the checklist with it",
        together(skill_lists(sorted(ITEMS)), checklist_lists(sorted(ITEMS))), 0, []),
    ("the carve-out heading with closing hashes and trailing spaces",
        edit(SKILL, HEADING, HEADING.rstrip("\n") + " ##  \n"), 0, []),
    ("a mixed-mark line in the checklist", prepend(CHECKLIST, "_*_\n\n"), 0, []),
    ("a mixed-mark line in SKILL.md, above the carve-out section", edit(SKILL, HEADING, "- * _\n\n" + HEADING), 0, []),
    ("plain text and bullets of plain text in the carve-out section",
        edit(SKILL, LEAD_IN, LEAD_IN + "\n".join(PLAIN_LINES) + "\n   \n"), 0, []),
    *[(f"the line {line!r} under the carve-out heading", edit(SKILL, HEADING, HEADING + line + "\n"), 3,
       [at(SKILL, HEADING, 1) + UNREAD_LINE]) for line in UNREAD_LINES],
    *[(f"the line {line!r} under the carve-out heading, refused for {char!r}",
       edit(SKILL, HEADING, HEADING + line + "\n"), 3, [at(SKILL, HEADING, 1) + character(char)])
      for line, char in CHARACTER_LINES],
    ("the line '<b>x</b>' under the carve-out heading", edit(SKILL, HEADING, HEADING + "<b>x</b>\n"), 3,
        [at(SKILL, HEADING, 1) + HTML]),
    ("a character outside the list in the dash bullet",
        change_dash_line(lambda line: line.replace("Keep a dash", "Keep a *dash*", 1)), 3,
        [at(CHECKLIST, KEEP) + character("*")]),
    ("a character outside the list in a checklist line under the heading",
        edit(CHECKLIST, CHECKLIST_HEADING, CHECKLIST_HEADING + "\nSee [the rules].\n"), 3,
        [at(CHECKLIST, CHECKLIST_HEADING, 2) + character("[")]),
    # The span edges. The case "the line 'x & y' under the carve-out heading, refused for '&'" puts the line on the
    # first line of the carve-out section after its heading.
    ("x & y directly above the carve-out heading", edit(SKILL, HEADING, EDGE + HEADING), 0, []),
    ("x & y on the last line of the carve-out section", edit(SKILL, NEXT_HEADING, EDGE + NEXT_HEADING), 3,
        [at(SKILL, NEXT_HEADING) + character("&")]),
    ("x & y directly under the heading after the carve-out section", edit(SKILL, NEXT_HEADING, NEXT_HEADING + EDGE),
        0, []),
    # A level 1 heading ends the section as a level 2 heading does, so these 2 cases pin that edge apart from the
    # level 2 heading after it.
    ("x & y directly above a level 1 heading added after the carve-out section",
        edit(SKILL, NEXT_HEADING, EDGE + "# More\n" + NEXT_HEADING), 3, [at(SKILL, NEXT_HEADING) + character("&")]),
    ("x & y directly under a level 1 heading added after the carve-out section",
        edit(SKILL, NEXT_HEADING, "# More\n" + EDGE + NEXT_HEADING), 0, []),
    # With the carve-out section last in SKILL.md, the section ends at the end of the file, and no line lies past
    # it: the section with no refused line pins a check that reads past the end, and x & y on its last line, with
    # and without a final LF, pins a check that stops short of it.
    ("the carve-out section last in SKILL.md", cut(SKILL, "\n" + NEXT_HEADING, ""), 0, []),
    ("x & y as the last line of SKILL.md, with the carve-out section last", cut(SKILL, NEXT_HEADING, EDGE), 3,
        [at(SKILL, NEXT_HEADING) + character("&")]),
    ("x & y as the last line of SKILL.md, with the carve-out section last and no LF after it",
        cut(SKILL, NEXT_HEADING, EDGE.rstrip("\n")), 3, [at(SKILL, NEXT_HEADING) + character("&")]),
    # The bullet moves from its place to just above the next heading, with the "2." line under it, so the "2." line
    # takes the number the next heading has in the committed file.
    ("the skill bullet last in its section, 2. or code samples; under it, the same words in the dash bullet",
        together(edit(SKILL, SKILL_LINE + "\n", ""),
                 edit(SKILL, "\n" + NEXT_HEADING, "\n" + SKILL_LINE + "\n2. or code samples;\n" + NEXT_HEADING),
                 change_dash_line(lambda line: line.rstrip("\n.") + "; 2. or code samples.\n")),
        3, [at(SKILL, NEXT_HEADING) + UNREAD_LINE]),
    ("x & y directly under the checklist heading above the dash bullet",
        edit(CHECKLIST, CHECKLIST_HEADING, CHECKLIST_HEADING + EDGE), 3,
        [at(CHECKLIST, CHECKLIST_HEADING, 1) + character("&") + CHECKLIST_SPAN + "the end of the file;"]),
    ("x & y directly above the checklist heading above the dash bullet",
        edit(CHECKLIST, CHECKLIST_HEADING, EDGE + CHECKLIST_HEADING), 0, []),
    # A heading of any level above the dash bullet starts the checklist span, so these 4 cases pin that edge at
    # levels 1 and 3, apart from the level 2 heading in the 2 cases above them.
    ("x & y directly under a level 1 checklist heading above the dash bullet",
        edit(CHECKLIST, CHECKLIST_HEADING, CHECKLIST_HEADING[1:] + EDGE), 3,
        [at(CHECKLIST, CHECKLIST_HEADING, 1) + character("&") + CHECKLIST_SPAN + "the end of the file;"]),
    ("x & y directly above a level 1 checklist heading above the dash bullet",
        edit(CHECKLIST, CHECKLIST_HEADING, EDGE + CHECKLIST_HEADING[1:]), 0, []),
    ("x & y directly under a level 3 checklist heading above the dash bullet",
        edit(CHECKLIST, CHECKLIST_HEADING, "#" + CHECKLIST_HEADING + EDGE), 3,
        [at(CHECKLIST, CHECKLIST_HEADING, 1) + character("&") + CHECKLIST_SPAN + "the end of the file;"]),
    ("x & y directly above a level 3 checklist heading above the dash bullet",
        edit(CHECKLIST, CHECKLIST_HEADING, EDGE + "#" + CHECKLIST_HEADING), 0, []),
    ("x & y as the last line of the checklist", append(CHECKLIST, EDGE), 3,
        [past_end(CHECKLIST) + character("&") + CHECKLIST_SPAN + "the end of the file;"]),
    ("x & y as the last line of the checklist, with no LF after it", append(CHECKLIST, EDGE.rstrip("\n")), 3,
        [past_end(CHECKLIST) + character("&") + CHECKLIST_SPAN + "the end of the file;"]),
    ("x & y directly above a heading added after the dash bullet", append(CHECKLIST, EDGE + "## More\n"), 3,
        [past_end(CHECKLIST) + character("&") + CHECKLIST_SPAN + "the next heading;"]),
    ("x & y directly under a heading added after the dash bullet", append(CHECKLIST, "## More\n" + EDGE), 0, []),
    # A heading of any level ends the checklist span, so these 4 cases pin that edge at levels 3 and 1, apart from
    # the level 2 heading in the 2 cases above them.
    ("x & y directly above a level 3 heading added after the dash bullet", append(CHECKLIST, EDGE + "### More\n"), 3,
        [past_end(CHECKLIST) + character("&") + CHECKLIST_SPAN + "the next heading;"]),
    ("x & y directly under a level 3 heading added after the dash bullet", append(CHECKLIST, "### More\n" + EDGE), 0,
        []),
    ("x & y directly above a level 1 heading added after the dash bullet", append(CHECKLIST, EDGE + "# More\n"), 3,
        [past_end(CHECKLIST) + character("&") + CHECKLIST_SPAN + "the next heading;"]),
    ("x & y directly under a level 1 heading added after the dash bullet", append(CHECKLIST, "# More\n" + EDGE), 0,
        []),
    ("x & y on line 1 of a checklist with no heading above the dash bullet",
        lambda root: (root / CHECKLIST).write_text(EDGE + "\n" + dash_line(root), encoding="utf-8"), 3,
        [f"{CHECKLIST}, line 1: " + character("&")
         + "the lines between the start of the file and the end of the file;"]),
    # No line lies before line 1, and a check that starts at line 0 reads the last line first, by Python's negative
    # indexing, so this case puts the line last, where such a check names line 0.
    ("x & y as the last line, with no LF after it, of a checklist with no heading above the dash bullet",
        lambda root: (root / CHECKLIST).write_text(dash_line(root) + "\n" + EDGE.rstrip("\n"), encoding="utf-8"), 3,
        [f"{CHECKLIST}, line 3: " + character("&")
         + "the lines between the start of the file and the end of the file;"]),
    *[(f"the skill bullet under {marks!r}, with the same words in the dash bullet",
       together(edit(SKILL, SKILL_LINE, marks + "\ncode samples, " + SKILL_LINE[2:]),
                checklist_lists(ITEMS, KEEP + marks[2:] + " code samples, ")),
       3, [at(SKILL, SKILL_LINE) + character(marks[2])]) for marks in ("- ***", "- ___", "- _ _ _")],
    ("a link title in the skill bullet, with the same link in the dash bullet",
        together(edit(SKILL, SKILL_LINE, SKILL_LINE[:-1] + ' [w](/x "or code samples");'),
                 checklist_lists(ITEMS[:-1] + [ITEMS[-1] + ' [w](/x "or code samples")'])),
        3, [at(SKILL, SKILL_LINE) + character("[")]),
    ("<script> above the carve-out heading", edit(SKILL, HEADING, "<script>\n" + HEADING), 3,
        [at(SKILL, HEADING) + HTML]),
    ("<pre> above the checklist heading over the dash bullet",
        edit(CHECKLIST, CHECKLIST_HEADING, "<pre>\n" + CHECKLIST_HEADING), 3,
        [at(CHECKLIST, CHECKLIST_HEADING) + HTML]),
    ("<style> after 3 spaces in the checklist", prepend(CHECKLIST, "   <style>\n\n"), 3,
        [f"{CHECKLIST}, line 1: " + HTML]),
    ("< later in a line, and < after 4 spaces, continuing a bullet above the carve-out section",
        edit(SKILL, OTHER_BULLET, OTHER_BULLET + "before <b>the</b> point;\n    <pre>\n"), 0, []),
    ("a heading as the checklist's one block that mentions a dash", replace_dash_line("## Keep a dash\n"), 3,
        [f"{NO_DASH}, a bullet; found 1 (heading)"]),
    ("a * bullet above the dash bullet", change_dash_line(lambda line: "* Count words.\n" + line), 3,
        [at(CHECKLIST, KEEP) + character("*")]),
    ("an ordered item 2. under the skill bullet, with the same words on the dash bullet line",
        together(edit(SKILL, SKILL_LINE, SKILL_LINE + "\n2. or code samples;"),
                 change_dash_line(lambda line: line.rstrip("\n.") + "; 2. or code samples.\n")),
        3, [at(SKILL, SKILL_LINE, 1) + UNREAD_LINE]),
    ("an ordered item 2. under the dash bullet, with the same words on the skill bullet line",
        together(edit(SKILL, SKILL_LINE, SKILL_LINE + " 2. or code samples;"),
                 change_dash_line(lambda line: line.rstrip("\n.") + ";\n2. or code samples.\n")),
        3, [at(CHECKLIST, KEEP, 1) + UNREAD_LINE]),
    ("an ordered item 10) under the skill bullet, with the same words on the dash bullet line",
        together(edit(SKILL, SKILL_LINE, SKILL_LINE + "\n10) or code samples;"),
                 change_dash_line(lambda line: line.rstrip("\n.") + "; 10) or code samples.\n")),
        3, [at(SKILL, SKILL_LINE, 1) + UNREAD_LINE]),
    ("an ordered item 10) under the dash bullet, with the same words on the skill bullet line",
        together(edit(SKILL, SKILL_LINE, SKILL_LINE + " 10) or code samples;"),
                 change_dash_line(lambda line: line.rstrip("\n.") + ";\n10) or code samples.\n")),
        3, [at(CHECKLIST, KEEP, 1) + UNREAD_LINE]),
    ("the checklist list reordered", checklist_lists(list(reversed(ITEMS))), 1, []),
    ("the skill list reordered after its first item", skill_lists(ITEMS[:1] + list(reversed(ITEMS[1:]))), 1, []),
    ("the skill list with quoted language last", skill_lists(ITEMS[1:] + ITEMS[:1]), 1, []),
    ('the "only inside" form', checklist_lists(ITEMS, "Keep a dash only inside "), 1, []),
    ("main's checklist line", replace_dash_line(OLD_LINE), 1,
        [lacks(item) for item in ITEMS] + [adds("quoted"), adds("verbatim material")]),
    *[(f"the checklist without {item!r}", checklist_lists([i for i in ITEMS if i != item]), 1, [lacks(item)])
      for item in ITEMS],
    ("the checklist with an item the skill lacks", checklist_lists(ITEMS + ["code samples"]), 1, [adds("code samples")]),
    ("the skill with a new item", skill_lists(ITEMS + ["legal citations"]), 1, [lacks("legal citations")]),
    ("a sentence after the Keep clause", change_dash_line(lambda line: line.rstrip("\n") + " " + EXTRA + "\n"), 1, []),
    ("an indented sub-bullet under the dash bullet", change_dash_line(lambda line: line + "  - " + EXTRA + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + INDENTED_ITEM]),
    ("a sub-bullet indented by 4 spaces under the dash bullet",
        change_dash_line(lambda line: line + "    - " + EXTRA + "\n"), 3, [at(CHECKLIST, KEEP, 1) + UNREAD_LINE]),
    ("the carve-out heading indented by 1 space", edit(SKILL, HEADING, " " + HEADING), 3,
        [at(SKILL, HEADING) + INDENTED_HEADING]),
    ("the skill bullet indented by 3 spaces", edit(SKILL, SKILL_LINE, "   " + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE) + INDENTED_ITEM]),
    ("an indented heading above the skill bullet", edit(SKILL, SKILL_LINE, " ## Moved\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("the dash bullet indented by 1 space", change_dash_line(lambda line: " " + line), 3,
        [at(CHECKLIST, KEEP) + INDENTED_ITEM]),
    ("a block quote marker indented by 2 spaces under the dash bullet",
        change_dash_line(lambda line: line + "  > " + EXTRA + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED_HEADING]),
    ("an indented * sub-bullet under the dash bullet", change_dash_line(lambda line: line + "  * " + EXTRA + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + INDENTED_ITEM]),
    ("an indented + sub-bullet under the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n + or code samples;"),
        3, [at(SKILL, SKILL_LINE, 1) + INDENTED_ITEM]),
    ("an indented * at the end of a line under the dash bullet",
        change_dash_line(lambda line: line + "  *\n" + SPLIT + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED_ITEM]),
    ("an indented # at the end of a line above the skill bullet", edit(SKILL, SKILL_LINE, " #\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("an indented level 6 heading above the skill bullet", edit(SKILL, SKILL_LINE, "   ###### Moved\n" + SKILL_LINE),
        3, [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("an indented 1. item under the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n  1. or code samples;"), 3,
        [at(SKILL, SKILL_LINE, 1) + INDENTED_ITEM]),
    ("a wrapped line starting 404. under the dash bullet",
        change_dash_line(lambda line: line + "  404. " + SPLIT + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED_ITEM]),
    ("an indented 123456789) at the end of a line under the dash bullet",
        change_dash_line(lambda line: line + "  123456789)\n" + SPLIT + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + INDENTED_ITEM]),
    ("an empty * item after the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n* \nor code samples;"), 3,
        [at(SKILL, SKILL_LINE, 1) + EMPTY_ITEM]),
    ("the skill bullet text under an empty + item, after a line continuing the bullet above",
        edit(SKILL, SKILL_LINE, "Also:\n+ \n" + SKILL_LINE[2:]), 3, [at(SKILL, SKILL_LINE, 1) + EMPTY_ITEM]),
    ("an empty - item after a blank line under the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n\n- "), 3,
        [at(SKILL, SKILL_LINE, 2) + EMPTY_ITEM]),
    ("an empty 1. item after the dash bullet", change_dash_line(lambda line: line + "1. \n" + SPLIT + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + EMPTY_ITEM]),
    ("a lone * after the dash bullet", change_dash_line(lambda line: line + "*\n" + SPLIT + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + EMPTY_ITEM]),
    ("a lone 2. after the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n2.\nor code samples;"), 3,
        [at(SKILL, SKILL_LINE, 1) + EMPTY_ITEM]),
    ("a lone 123456789) after the dash bullet", change_dash_line(lambda line: line + "123456789)\n" + SPLIT + "\n"),
        3, [at(CHECKLIST, KEEP, 1) + EMPTY_ITEM]),
    ("a heading indented by 4 spaces above the skill bullet", edit(SKILL, SKILL_LINE, "    ## Moved\n" + SKILL_LINE),
        3, [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("a level 6 heading indented by 4 spaces above the skill bullet",
        edit(SKILL, SKILL_LINE, "    ###### Moved\n" + SKILL_LINE), 3, [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("a block quote marker indented by 5 spaces above the skill bullet",
        edit(SKILL, SKILL_LINE, "     > Moved\n" + SKILL_LINE), 3, [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("a heading indented by 5 spaces under the dash bullet", change_dash_line(lambda line: line + "     ## Moved\n"), 3,
        [at(CHECKLIST, KEEP, 1) + INDENTED_HEADING]),
    ("a # at the end of a line indented by 5 spaces under the dash bullet",
        change_dash_line(lambda line: line + "     #\n" + SPLIT + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + INDENTED_HEADING]),
    ("a block quote marker indented by 4 spaces under the dash bullet",
        change_dash_line(lambda line: line + "    > " + EXTRA + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED_HEADING]),
    ("a heading indented by 6 spaces under the bullet above the skill bullet",
        edit(SKILL, SKILL_LINE, "      ## Moved\n" + SKILL_LINE), 3, [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("a block quote marker indented by 6 spaces under the bullet above the skill bullet",
        edit(SKILL, SKILL_LINE, "      > Moved\n" + SKILL_LINE), 3, [at(SKILL, SKILL_LINE) + INDENTED_HEADING]),
    ("a heading indented by 6 spaces under a sub-bullet indented by 4 spaces above the skill bullet",
        edit(SKILL, SKILL_LINE, "    - Also:\n      ## Moved\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE, 1) + INDENTED_HEADING]),
    ("a block quote marker indented by 6 spaces under a sub-bullet indented by 4 spaces above the skill bullet",
        edit(SKILL, SKILL_LINE, "    - Also:\n      > Moved\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE, 1) + INDENTED_HEADING]),
    ("a heading indented by 10 spaces under a sub-bullet indented by 8 spaces above the skill bullet",
        edit(SKILL, SKILL_LINE, "    - Also:\n        - More:\n          ## Moved\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE, 2) + INDENTED_HEADING]),
    ("a heading indented by 6 spaces under an ordered item above the skill bullet",
        edit(SKILL, SKILL_LINE, "1. Also:\n      ## Moved\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE, 1) + INDENTED_HEADING]),
    ("a heading indented by 16 spaces directly under the carve-out heading, with no list open",
        edit(SKILL, HEADING, HEADING + "                ## Moved\n"), 3, [at(SKILL, HEADING, 1) + INDENTED_HEADING]),
    ("text that is not a marker, indented by 1 to 5 spaces, continuing a bullet above the carve-out section",
        edit(SKILL, OTHER_BULLET, OTHER_BULLET + " #x\n  ####### x\n  -x\n  1.x\n  1234567890. x\n  . x\n    #x\n"
             "     ####### x\n"), 0, []),
    ("text that is not a list marker, at the start of a line continuing the bullet above the skill bullet",
        edit(SKILL, SKILL_LINE, ")\n1234567890.\n" + SKILL_LINE), 0, []),
    ("an empty * item indented by 4 spaces under the dash bullet", change_dash_line(lambda line: line + "    *\n"), 3,
        [at(CHECKLIST, KEEP, 1) + UNREAD_LINE]),
    ("a sub-bullet indented by 4 spaces with 2 spaces after its marker, under the dash bullet",
        change_dash_line(lambda line: line + "    -  " + EXTRA + "\n"), 3, [at(CHECKLIST, KEEP, 1) + UNREAD_LINE]),
    ("an empty 2. item followed by 2 spaces after the skill bullet",
        edit(SKILL, SKILL_LINE, SKILL_LINE + "\n2.  \nor code samples;"), 3, [at(SKILL, SKILL_LINE, 1) + EMPTY_ITEM]),
    ("a lone 10) after the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n10)\nor code samples;"), 3,
        [at(SKILL, SKILL_LINE, 1) + EMPTY_ITEM]),
    ("an indented YAML list item in the SKILL.md front matter",
        edit(SKILL, "meaning.\n---\n", "meaning.\nallowed-tools:\n  - Read\n---\n"), 3,
        [at(SKILL, "meaning.\n---\n", 2) + INDENTED_ITEM]),
    ("both bullets with 3 spaces after the marker, each continued after a blank line by a line indented by 2 spaces",
        together(edit(SKILL, SKILL_LINE, "-   " + SKILL_LINE[2:] + "\n\n  or code samples;"),
                 change_dash_line(lambda line: "-   " + line[2:].rstrip("\n.") + ";\n\n  or code samples.\n")),
        3, [at(SKILL, SKILL_LINE) + SPACED]),
    ("the dash bullet with 2 spaces after a * marker", change_dash_line(lambda line: "*  " + line[2:]), 3,
        [at(CHECKLIST, KEEP) + SPACED]),
    ("the skill bullet with 2 spaces after a + marker", edit(SKILL, SKILL_LINE, "+  " + SKILL_LINE[2:]), 3,
        [at(SKILL, SKILL_LINE) + SPACED]),
    ("an indented paragraph in the dash bullet", change_dash_line(lambda line: line + "\n  " + EXTRA + "\n"), 3,
        [at(CHECKLIST, KEEP, 2) + UNREAD_LINE]),
    ("an unindented line continuing the dash bullet", change_dash_line(lambda line: line + EXTRA + "\n"), 1, []),
    ("a carve-out after a mixed-mark line in the dash bullet",
        change_dash_line(lambda line: line + "_*_\n" + SPLIT + "\n"), 3, [at(CHECKLIST, KEEP, 1) + character("_")]),
    ("a carve-out after a mixed-mark line in the skill bullet",
        edit(SKILL, SKILL_LINE, SKILL_LINE + "\n_*_\nor code samples;"), 3,
        [at(SKILL, SKILL_LINE, 1) + character("_")]),
    ("a fenced block in the dash bullet", change_dash_line(lambda line: line + "  ```\n  code samples\n  ```\n"), 3,
        [at(CHECKLIST, KEEP, 1) + FENCED]),
    ("a comment appended to the dash bullet",
        change_dash_line(lambda line: line.rstrip("\n") + " <!-- " + SPLIT + " -->\n"), 3,
        [at(CHECKLIST, KEEP) + COMMENT]),
    ("a comment on an indented line in the dash bullet",
        change_dash_line(lambda line: line + "  <!-- " + SPLIT + " -->\n"), 3, [at(CHECKLIST, KEEP, 1) + COMMENT]),
    ("a comment inside a dash word, with a comment appended",
        change_dash_line(lambda line: line.replace("en dash", "en da<!-- -->sh", 1).rstrip("\n")
                         + " <!-- Code samples may keep a dash. -->\n"), 3, [at(CHECKLIST, KEEP) + COMMENT]),
    ("a skill item on an unindented line", edit(SKILL, SKILL_LINE, SKILL_LINE.replace(", or", ",").rstrip(";")
        + "\nor code samples;"), 1, [lacks("code samples")]),
    ("a skill item on an indented line", edit(SKILL, SKILL_LINE, SKILL_LINE.replace(", or", ",").rstrip(";")
        + "\n  or code samples;"), 3, [at(SKILL, SKILL_LINE, 1) + UNREAD_LINE]),
    ("no Keep clause", checklist_lists(ITEMS, "Keep a dash where it is "), 1, []),
    ("2 Keep clauses", change_dash_line(lambda line: line.rstrip("\n") + " " + KEEP + listed(ITEMS) + ".\n"), 1, []),
    ("an empty item in the checklist", checklist_lists(ITEMS[:1] + [""] + ITEMS[1:]), 1, [adds("")]),
    ("SKILL.md missing", lambda root: (root / SKILL).unlink(), 3, [UNREAD]),
    ("the checklist missing", lambda root: (root / CHECKLIST).unlink(), 3, [UNREAD]),
    ("the checklist not UTF-8", lambda root: (root / CHECKLIST).write_bytes(b"- dash \xff\n"), 3, [UNREAD]),
    ("no pointer sentence", edit(SKILL, POINTER, "the exceptions below."), 3, [NO_POINTER]),
    ("2 pointer sentences", edit(SKILL, POINTER, POINTER + " See " + POINTER), 3, [NO_POINTER]),
    ("the pointer sentence only in a comment", edit(SKILL, POINTER, "the exceptions below. <!-- " + POINTER + " -->"),
        3, [at(SKILL, POINTER) + COMMENT]),
    ("the pointer sentence only on a fence opening line",
        edit(SKILL, POINTER, "the exceptions below.\n\n``` " + POINTER + "\n```"), 3, [at(SKILL, POINTER, 2) + FENCED]),
    ("the pointer sentence only in a comment on a fence opening line",
        edit(SKILL, POINTER, "the exceptions below.\n\n``` <!-- " + POINTER + " -->\n```"), 3,
        [at(SKILL, POINTER, 2) + COMMENT]),
    ("a comment in SKILL.md", edit(SKILL, HEADING, HEADING + "<!-- note -->\n"), 3, [at(SKILL, HEADING, 1) + COMMENT]),
    ("a fence at the start of SKILL.md", prepend(SKILL, "```\ncode\n```\n\n"), 3, [f"{SKILL}, line 1: " + FENCED]),
    ("an indented fence in SKILL.md", edit(SKILL, HEADING, HEADING + "\n   ~~~\n   code\n   ~~~\n"), 3,
        [at(SKILL, HEADING, 2) + FENCED]),
    ("a fence opened by a bullet in SKILL.md",
        edit(SKILL, SKILL_LINE, SKILL_LINE + "\n- ```text\n  code samples;\n  ```"), 3, [at(SKILL, SKILL_LINE, 1) + FENCED]),
    ("a comment at the start of the checklist", prepend(CHECKLIST, "<!-- note -->\n"), 3,
        [f"{CHECKLIST}, line 1: " + COMMENT]),
    ("a fence at the start of the checklist", prepend(CHECKLIST, "~~~\ncode\n~~~\n\n"), 3,
        [f"{CHECKLIST}, line 1: " + FENCED]),
    ("3 backticks in inline code in the checklist", prepend(CHECKLIST, "Write ```` ``` ```` to open a fence.\n\n"),
        3, [f"{CHECKLIST}, line 1: " + FENCED]),
    ("the carve-out section renamed", edit(SKILL, HEADING, "## Keep legitimate language\n"), 3, [NO_HEADING]),
    ("the carve-out section repeated", edit(SKILL, HEADING, HEADING + "\n" + HEADING), 3, [NO_HEADING]),
    ("the carve-out heading at level 3", edit(SKILL, HEADING, "#" + HEADING), 3, [NO_HEADING]),
    ("the carve-out heading at level 3 with closing hashes", edit(SKILL, HEADING, "#" + HEADING.rstrip("\n") + " ###\n"),
        3, [NO_HEADING]),
    ("the carve-out heading with hashes and no space before them",
        edit(SKILL, HEADING, HEADING.rstrip("\n") + "##\n"), 3, [NO_HEADING]),
    ("the carve-out heading with closing hashes between tabs",
        edit(SKILL, HEADING, HEADING.rstrip("\n") + "\t##\t\n"), 3, [at(SKILL, HEADING) + TAB]),
    ("the carve-out heading with U+00A0 before closing hashes",
        edit(SKILL, HEADING, HEADING.rstrip("\n") + "\u00a0##\n"), 3, [at(SKILL, HEADING) + NBSP]),
    ("the carve-out heading with U+00A0 after closing hashes",
        edit(SKILL, HEADING, HEADING.rstrip("\n") + " ##\u00a0\n"), 3, [at(SKILL, HEADING) + NBSP]),
    ("the carve-out heading with closing hashes and a CRLF ending",
        edit(SKILL, HEADING, HEADING.rstrip("\n") + " ##\r\n"), 3, [at(SKILL, HEADING) + CR]),
    ("the checklist with CRLF line endings", lambda root: (root / CHECKLIST).write_bytes(
        (root / CHECKLIST).read_bytes().replace(b"\n", b"\r\n")), 3, [f"{CHECKLIST}, line 1: " + CR]),
    ("a tab and U+00A0 in the dash bullet", checklist_lists(ITEMS, "Keep\ta dash only\u00a0in "), 3,
        [at(CHECKLIST, KEEP) + TAB]),
    ("U+00A0 in the dash bullet", checklist_lists(ITEMS, "Keep a dash only\u00a0in "), 3, [at(CHECKLIST, KEEP) + NBSP]),
    ("U+2028 in the skill bullet", edit(SKILL, "text, or ", "text,\u2028or "), 3,
        [at(SKILL, SKILL_LINE) + "holds U+2028"]),
    ("a thematic break after the dash bullet", change_dash_line(lambda line: line + "***\n" + SPLIT + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + RULED]),
    ("a spaced thematic break in SKILL.md", edit(SKILL, HEADING, HEADING + "\n _ _ _ \n"), 3,
        [at(SKILL, HEADING, 2) + RULED]),
    ("a thematic break under a blank line in SKILL.md", edit(SKILL, HEADING, HEADING + "\n---\n"), 3,
        [at(SKILL, HEADING, 2) + RULED]),
    ("a setext heading of = in the carve-out section", edit(SKILL, HEADING, HEADING + "\nMoved\n==\n"), 3,
        [at(SKILL, HEADING, 3) + RULED]),
    ("a lone - under the dash bullet", change_dash_line(lambda line: line + "-\n"), 3,
        [at(CHECKLIST, KEEP, 1) + RULED]),
    ("a setext heading of - in the checklist", prepend(CHECKLIST, "Notes\n --\n\n"), 3,
        [f"{CHECKLIST}, line 2: " + RULED]),
    ("front matter in the checklist", prepend(CHECKLIST, "---\ntitle: checklist\n---\n\n"), 3,
        [f"{CHECKLIST}, line 1: " + RULED]),
    ("the SKILL.md front matter after a blank line", prepend(SKILL, "\n"), 3, [f"{SKILL}, line 2: " + RULED]),
    ("the SKILL.md front matter not closed", edit(SKILL, "meaning.\n---\n", "meaning.\n"), 3,
        [f"{SKILL}, line 1: " + RULED]),
    ("the carve-out heading only in fenced code", edit(SKILL, HEADING, "```\n" + HEADING + "```\n"), 3,
        [at(SKILL, HEADING) + FENCED]),
    ("no quoted language bullet", edit(SKILL, "- " + ITEMS[0] + ",", "- quoted text,"), 3, [NO_ANCHOR]),
    ("the quoted language bullet outside the section",
        edit(SKILL, HEADING, HEADING + "\n## Moved\n"), 3, [NO_ANCHOR]),
    ("2 quoted language bullets", edit(SKILL, HEADING + "\n", HEADING + "\n- quoted language or code samples;\n\n"),
        3, [NO_ANCHOR]),
    ("the quoted language bullet only in a comment", edit(SKILL, SKILL_LINE, "<!--\n" + SKILL_LINE + "\n-->"),
        3, [at(SKILL, SKILL_LINE) + COMMENT]),
    ("the quoted language bullet only in fenced code", edit(SKILL, SKILL_LINE, "~~~\n" + SKILL_LINE + "\n~~~"),
        3, [at(SKILL, SKILL_LINE) + FENCED]),
    ("an empty item in the skill list", skill_lists(ITEMS[:1] + [""] + ITEMS[1:]), 3, [EMPTY]),
    ("no dash bullet", replace_dash_line(""), 3, [NO_DASH]),
    ("2 dash bullets", change_dash_line(lambda line: line + "- Count every dash.\n"), 3, [NO_DASH]),
    ("a paragraph that mentions a dash", change_dash_line(lambda line: line + "\n" + EXTRA + "\n"), 3, [NO_DASH]),
    ("the dash bullet only in a comment", change_dash_line(lambda line: "<!--\n" + line + "-->\n"), 3,
        [at(CHECKLIST, KEEP) + COMMENT]),
    ("the dash bullet only in fenced code", change_dash_line(lambda line: "```\n" + line + "```\n"), 3,
        [at(CHECKLIST, KEEP) + FENCED]),
    ("a comment that mentions a dash", change_dash_line(lambda line: line + "<!-- - Keep a dash in code. -->\n"),
        3, [at(CHECKLIST, KEEP, 1) + COMMENT]),
    ("fenced code that mentions a dash", change_dash_line(lambda line: line + "\n```\n- " + EXTRA + "\n```\n"),
        3, [at(CHECKLIST, KEEP, 2) + FENCED]),
]


def main() -> int:
    failures: list[str] = []
    ran = 0
    result = run(REPO_ROOT)
    ran += 1
    if result.returncode != 0:
        failures.append(f"this repository: exit {result.returncode}, expected 0: {(result.stdout + result.stderr).strip()[:300]}")
    for name, fault, expected, named in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if fault:
                try:
                    fault(root)
                except (AssertionError, OSError) as error:
                    failures.append(f"{name}: the fault could not be applied: {error}")
                    continue
            result = run(root)
            ran += 1
            output = (result.stdout + result.stderr).strip()
            if result.returncode != expected:
                failures.append(f"{name}: exit {result.returncode}, expected {expected}: {output[:300]}")
            for fragment in named:
                if fragment not in output:
                    failures.append(f"{name}: the output does not name {fragment}: {output[:300]}")
            if expected == 1:
                if DIFFERS not in result.stdout:
                    failures.append(f"{name}: the output does not say the bullet differs: {output[:300]}")
                itemized = [line for line in result.stdout.splitlines() if line.startswith(ITEM_LINES)]
                if len(itemized) != len(named):
                    failures.append(f"{name}: the output names other items than {named}: {itemized}")
    with tempfile.TemporaryDirectory() as scratch:
        result = run(make_root(Path(scratch)), "--write")
        ran += 1
        if result.returncode != 2:
            failures.append(f"an argument: exit {result.returncode}, expected 2")
    if failures:
        print("test-check-skill-consistency: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-check-skill-consistency: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
