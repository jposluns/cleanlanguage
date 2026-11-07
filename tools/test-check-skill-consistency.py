#!/usr/bin/env python3
"""Tests for tools/check-skill-consistency.py: the checklist dash bullet against the skill's carve-outs.

The first case runs the gate on this repository and changes nothing. Each case
in CASES copies the gate and the 2 files it reads into a temporary repository
(under $TMPDIR), applies the case's change, runs the gate there as a separate
process and asserts its exit code and the fragments the case lists. The case
named "the committed tree" changes nothing, and the 2 cases named "the skill
list sorted, and the checklist with it" and "both bullets with 3 spaces after
the marker, each continued after a blank line by a line indented by 2 spaces"
each make 2 edits, one in each file; each other case makes 1 change, which
edits, rewrites or removes a file. The cases that expect exit 0,
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
INDENTED = "is a heading, list or block quote marker indented by 1 to 3 spaces"
NESTED = "is a heading or block quote marker indented by 4 or 5 spaces"
EMPTY_ITEM = "is a list marker with nothing after it, an empty list item"
SPACED = "is a bullet marker followed by 2 or more spaces"


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


def lacks(item: str) -> str:
    return f"lacks {item!r}"


def adds(item: str) -> str:
    return f"adds {item!r}"


SKILL_LINE = "- " + listed(ITEMS) + ";"

CASES = [
    ("the committed tree", None, 0, []),
    ("the clause continued on an indented line", checklist_lists(ITEMS, "Keep a dash only in\n  "), 0, []),
    ("the clause continued on an unindented line", checklist_lists(ITEMS, "Keep a dash only in\n"), 0, []),
    ("the skill bullet continued on an indented line", edit(SKILL, "text, or ", "text,\n  or "), 0, []),
    ("the skill bullet continued on an unindented line", edit(SKILL, "text, or ", "text,\nor "), 0, []),
    ("the skill list sorted, and the checklist with it",
        together(skill_lists(sorted(ITEMS)), checklist_lists(sorted(ITEMS))), 0, []),
    ("the carve-out heading with closing hashes and trailing spaces",
        edit(SKILL, HEADING, HEADING.rstrip("\n") + " ##  \n"), 0, []),
    ("a mixed-mark line in the checklist", prepend(CHECKLIST, "_*_\n\n"), 0, []),
    ("a mixed-mark line in SKILL.md", edit(SKILL, HEADING, HEADING + "\n- * _\n"), 0, []),
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
        [at(CHECKLIST, KEEP, 1) + INDENTED]),
    ("a sub-bullet indented by 4 spaces under the dash bullet",
        change_dash_line(lambda line: line + "    - " + EXTRA + "\n"), 1, []),
    ("the carve-out heading indented by 1 space", edit(SKILL, HEADING, " " + HEADING), 3,
        [at(SKILL, HEADING) + INDENTED]),
    ("the skill bullet indented by 3 spaces", edit(SKILL, SKILL_LINE, "   " + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE) + INDENTED]),
    ("an indented heading above the skill bullet", edit(SKILL, SKILL_LINE, " ## Moved\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE) + INDENTED]),
    ("the dash bullet indented by 1 space", change_dash_line(lambda line: " " + line), 3,
        [at(CHECKLIST, KEEP) + INDENTED]),
    ("a block quote marker indented by 2 spaces under the dash bullet",
        change_dash_line(lambda line: line + "  > " + EXTRA + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED]),
    ("an indented * sub-bullet under the dash bullet", change_dash_line(lambda line: line + "  * " + EXTRA + "\n"), 3,
        [at(CHECKLIST, KEEP, 1) + INDENTED]),
    ("an indented + sub-bullet under the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n + or code samples;"),
        3, [at(SKILL, SKILL_LINE, 1) + INDENTED]),
    ("an indented * at the end of a line under the dash bullet",
        change_dash_line(lambda line: line + "  *\n" + SPLIT + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED]),
    ("an indented # at the end of a line above the skill bullet", edit(SKILL, SKILL_LINE, " #\n" + SKILL_LINE), 3,
        [at(SKILL, SKILL_LINE) + INDENTED]),
    ("an indented level 6 heading above the skill bullet", edit(SKILL, SKILL_LINE, "   ###### Moved\n" + SKILL_LINE),
        3, [at(SKILL, SKILL_LINE) + INDENTED]),
    ("an indented 1. item under the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n  1. or code samples;"), 3,
        [at(SKILL, SKILL_LINE, 1) + INDENTED]),
    ("a wrapped line starting 404. under the dash bullet",
        change_dash_line(lambda line: line + "  404. " + SPLIT + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED]),
    ("an indented 123456789) at the end of a line under the dash bullet",
        change_dash_line(lambda line: line + "  123456789)\n" + SPLIT + "\n"), 3, [at(CHECKLIST, KEEP, 1) + INDENTED]),
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
        3, [at(SKILL, SKILL_LINE) + NESTED]),
    ("a level 6 heading indented by 4 spaces above the skill bullet",
        edit(SKILL, SKILL_LINE, "    ###### Moved\n" + SKILL_LINE), 3, [at(SKILL, SKILL_LINE) + NESTED]),
    ("a block quote marker indented by 5 spaces above the skill bullet",
        edit(SKILL, SKILL_LINE, "     > Moved\n" + SKILL_LINE), 3, [at(SKILL, SKILL_LINE) + NESTED]),
    ("a heading indented by 5 spaces under the dash bullet", change_dash_line(lambda line: line + "     ## Moved\n"), 3,
        [at(CHECKLIST, KEEP, 1) + NESTED]),
    ("a # at the end of a line indented by 5 spaces under the dash bullet",
        change_dash_line(lambda line: line + "     #\n" + SPLIT + "\n"), 3, [at(CHECKLIST, KEEP, 1) + NESTED]),
    ("a block quote marker indented by 4 spaces under the dash bullet",
        change_dash_line(lambda line: line + "    > " + EXTRA + "\n"), 3, [at(CHECKLIST, KEEP, 1) + NESTED]),
    ("a heading and a block quote marker indented by 6 spaces, continuing the bullet above the skill bullet",
        edit(SKILL, SKILL_LINE, "      ## Moved\n      > Moved\n" + SKILL_LINE), 0, []),
    ("text that is not a marker, indented by 1 to 5 spaces, continuing the bullet above the skill bullet",
        edit(SKILL, SKILL_LINE, " #x\n  ####### x\n  -x\n  1.x\n  1234567890. x\n  . x\n    #x\n     ####### x\n"
             + SKILL_LINE), 0, []),
    ("text that is not a list marker, at the start of a line continuing the bullet above the skill bullet",
        edit(SKILL, SKILL_LINE, ")\n1234567890.\n" + SKILL_LINE), 0, []),
    ("an empty * item indented by 4 spaces under the dash bullet", change_dash_line(lambda line: line + "    *\n"), 1,
        []),
    ("a sub-bullet indented by 4 spaces with 2 spaces after its marker, under the dash bullet",
        change_dash_line(lambda line: line + "    -  " + EXTRA + "\n"), 1, []),
    ("an empty 2. item followed by 2 spaces after the skill bullet",
        edit(SKILL, SKILL_LINE, SKILL_LINE + "\n2.  \nor code samples;"), 3, [at(SKILL, SKILL_LINE, 1) + EMPTY_ITEM]),
    ("a lone 10) after the skill bullet", edit(SKILL, SKILL_LINE, SKILL_LINE + "\n10)\nor code samples;"), 3,
        [at(SKILL, SKILL_LINE, 1) + EMPTY_ITEM]),
    ("an indented YAML list item in the SKILL.md front matter",
        edit(SKILL, "meaning.\n---\n", "meaning.\nallowed-tools:\n  - Read\n---\n"), 3,
        [at(SKILL, "meaning.\n---\n", 2) + INDENTED]),
    ("both bullets with 3 spaces after the marker, each continued after a blank line by a line indented by 2 spaces",
        together(edit(SKILL, SKILL_LINE, "-   " + SKILL_LINE[2:] + "\n\n  or code samples;"),
                 change_dash_line(lambda line: "-   " + line[2:].rstrip("\n.") + ";\n\n  or code samples.\n")),
        3, [at(SKILL, SKILL_LINE) + SPACED]),
    ("the dash bullet with 2 spaces after a * marker", change_dash_line(lambda line: "*  " + line[2:]), 3,
        [at(CHECKLIST, KEEP) + SPACED]),
    ("the skill bullet with 2 spaces after a + marker", edit(SKILL, SKILL_LINE, "+  " + SKILL_LINE[2:]), 3,
        [at(SKILL, SKILL_LINE) + SPACED]),
    ("an indented paragraph in the dash bullet", change_dash_line(lambda line: line + "\n  " + EXTRA + "\n"), 1, []),
    ("an unindented line continuing the dash bullet", change_dash_line(lambda line: line + EXTRA + "\n"), 1, []),
    ("a carve-out after a mixed-mark line in the dash bullet",
        change_dash_line(lambda line: line + "_*_\n" + SPLIT + "\n"), 1, []),
    ("a carve-out after a mixed-mark line in the skill bullet",
        edit(SKILL, SKILL_LINE, SKILL_LINE + "\n_*_\nor code samples;"), 1,
        [lacks(ITEMS[-1] + "; _*_"), lacks("code samples"), adds(ITEMS[-1])]),
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
        + "\n  or code samples;"), 1, [lacks("code samples")]),
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
