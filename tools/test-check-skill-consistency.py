#!/usr/bin/env python3
"""Tests for tools/check-skill-consistency.py: the checklist dash line against the skill's carve-outs.

The first case runs the gate on this repository and applies no change. Each
other case copies the gate and the 2 files it reads into a temporary
repository (under $TMPDIR), applies 1 fault, runs the gate there as a separate
process and asserts its exit code and, where the case lists them, the items its
output names. The case named "main's checklist line" restores the exact line
the checklist carried before row 98 and expects the gate to name the 5 items
it lacks and the 2 it adds. One further case passes the gate an argument and
asserts exit 2.

ITEMS is the carve-out list as SKILL.md states it today, in its order. The
faults that rewrite a list check that ITEMS is still there first, so a change
to that list fails this test until ITEMS follows it.
Exit 0 when every case passes; 1 otherwise, naming each failing case.
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
# The checklist's dash line on main before row 98.
OLD_LINE = ("- Remove every em and en dash, converting each to the punctuation the sentence needs; write numeric "
            "and date ranges with a hyphen or `to`. Keep a dash only inside quoted or verbatim material.\n")


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


def checklist_lists(items: list[str], keep: str = KEEP):
    return edit(CHECKLIST, KEEP + listed(ITEMS) + ".", keep + listed(items) + ".")


def skill_lists(items: list[str]):
    return edit(SKILL, "- " + listed(ITEMS) + ";", "- " + listed(items) + ";")


def replace_dash_line(new: str):
    return lambda root: edit(CHECKLIST, dash_line(root), new)(root)


def lacks(item: str) -> str:
    return f"lacks {item!r}"


def adds(item: str) -> str:
    return f"adds {item!r}"


CASES = [
    ("the committed tree", None, 0, []),
    ("the checklist list reordered", checklist_lists(list(reversed(ITEMS))), 0, []),
    ("the skill list reordered after its first item", skill_lists(ITEMS[:1] + list(reversed(ITEMS[1:]))), 0, []),
    ('the "only inside" form', checklist_lists(ITEMS, "Keep a dash only inside "), 0, []),
    ("the clause continued on an indented line", checklist_lists(ITEMS, "Keep a dash only in\n  "), 0, []),
    ("main's checklist line", replace_dash_line(OLD_LINE), 1,
        [lacks(item) for item in ITEMS] + [adds("quoted"), adds("verbatim material")]),
    *[(f"the checklist without {item!r}", checklist_lists([i for i in ITEMS if i != item]), 1, [lacks(item)])
      for item in ITEMS],
    ("the checklist with an item the skill lacks", checklist_lists(ITEMS + ["code samples"]), 1, [adds("code samples")]),
    ("the skill with a new item", skill_lists(ITEMS + ["legal citations"]), 1, [lacks("legal citations")]),
    ("SKILL.md missing", lambda root: (root / SKILL).unlink(), 3, []),
    ("the checklist missing", lambda root: (root / CHECKLIST).unlink(), 3, []),
    ("the checklist not UTF-8", lambda root: (root / CHECKLIST).write_bytes(b"- dash \xff\n"), 3, []),
    ("no pointer sentence", edit(SKILL, POINTER, "the exceptions below."), 3, []),
    ("2 pointer sentences", edit(SKILL, POINTER, POINTER + " See " + POINTER), 3, []),
    ("the carve-out section renamed", edit(SKILL, HEADING, "## Keep legitimate language\n"), 3, []),
    ("the carve-out section repeated", edit(SKILL, HEADING, HEADING + "\n" + HEADING), 3, []),
    ("no quoted language bullet", edit(SKILL, "- " + ITEMS[0] + ",", "- quoted text,"), 3, []),
    ("quoted language moved off the start of its bullet", skill_lists(ITEMS[1:] + ITEMS[:1]), 3, []),
    ("the quoted language bullet outside the section",
        edit(SKILL, HEADING, HEADING + "\n## Moved\n"), 3, []),
    ("2 quoted language bullets", edit(SKILL, HEADING + "\n", HEADING + "\n- quoted language only;\n"), 3, []),
    ("no dash bullet", replace_dash_line(""), 3, []),
    ("2 dash bullets", lambda root: edit(CHECKLIST, dash_line(root), dash_line(root) + "- Count every dash.\n")(root),
        3, []),
    ("no Keep clause", checklist_lists(ITEMS, "Keep a dash where it is "), 3, []),
    ("2 Keep clauses", lambda root: edit(CHECKLIST, dash_line(root),
        dash_line(root).rstrip("\n") + " " + KEEP + listed(ITEMS) + ".\n")(root), 3, []),
    ("an empty item", checklist_lists(ITEMS[:1] + [""] + ITEMS[1:]), 3, []),
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
                fault(root)
            result = run(root)
            ran += 1
            output = (result.stdout + result.stderr).strip()
            if result.returncode != expected:
                failures.append(f"{name}: exit {result.returncode}, expected {expected}: {output[:300]}")
            for fragment in named:
                if fragment not in result.stdout:
                    failures.append(f"{name}: the output does not name {fragment}: {output[:300]}")
            if expected == 1 and len(result.stdout.strip().splitlines()) != len(named):
                failures.append(f"{name}: the output names other items than {named}: {output[:300]}")
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
