#!/usr/bin/env python3
"""Tests for tools/check-flow-mode.py: its verdict on the flow.md texts it must pass or fail.

Each case runs the check as a separate process, isolated (-I), with the text on standard input,
and asserts its exit status, 0 for a pass and 1 for a failure, and the report line that names the
reason. The cases are the committed .claude/commands/flow.md, which passes; the mode text of
main's flow.md at ee6be48, which fails; and the committed flow.md with 1 change each: a third
value on the MODE line, an unquoted bare "attended" and the absent-record sentence removed, which
fail, and a quoted "attended", which passes. The main case copies the lines of that flow.md that
the check reports, so it needs no git history and runs in a shallow checkout.

The residual cases pin the limits that the check's docstring states, so a change to what the
check reads fails here until that docstring and these cases change with it: a third value named
outside the MODE line passes, a retired default inside double quotes passes, a sentence that
contradicts the absent rule passes, the absent rule in other words fails, and an ordinary English
use of "attended" fails.

Usage: python3 -I tools/test-check-flow-mode.py
Exit 0 when every case passes; 1 otherwise.
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "tools" / "check-flow-mode.py"
FLOW = ROOT / ".claude" / "commands" / "flow.md"

MODE_LINE = "- MODE (attended-autonomous | unattended)"
ABSENT_WORDS = "reads an absent mode record as unattended"
# A new bullet goes before this one, so it lands in the mode section and away from the MODE line.
DECISIONS = "- DECISIONS: "

# The lines of .claude/commands/flow.md at main ee6be48 that the check reports, copied with the
# lines that open their items: cycle step 5, the first 2 lines of cycle step 8, the MODE bullet and
# the first line of the DECISIONS bullet. That file has no absent-record sentence either, so the
# check reports here what it reports on the whole file.
MAIN_MODE_TEXT = """\
5. AUTHORIZE within the standing grant. Not covered: attended -> surface a work-naming go, hold THIS
   item, and continue other independent queued work (a question never halts independent work);
   unattended -> DEFER (propose a ?HOLD on the affected STEP, route to the next independent item), never
   self-grant, never self-author a block.
8. PAUSE (after a merge, after a plan is verified pre-implementation, or when the queue composition
   changed): refresh; if an attended boundary is open, surface accumulated decisions, up to 4
- MODE (attended | unattended) parameterizes the question policy/timer/routing; it GRANTS NO authority.
  Absent = attended (conservative). The ONE governed transition is a decision-timeout switching
  attended -> unattended (the safe/conservative direction only). An inbound operator message is a
  TRANSIENT attended boundary and does NOT silently flip the mode.
- DECISIONS: blocking + attended -> surface immediately, up to 4 per round, in the four-role shape.
"""

WRONG_MODES = "the MODE line names"
BARE = "unquoted bare \"attended\""
NO_ABSENT = "no statement that an absent mode record is read as unattended"


def verdict(text):
    """The exit status of the check run on text, and its output."""
    run = subprocess.run([sys.executable, "-I", str(CHECK), "-"], input=text.encode("utf-8"),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, check=False)
    return run.returncode, run.stdout.decode("utf-8", "replace")


def committed():
    """The committed flow.md."""
    return FLOW.read_text(encoding="utf-8")


def changed(old, new):
    """The committed flow.md with its one occurrence of old replaced by new."""
    text = committed()
    if text.count(old) != 1:
        raise AssertionError("expected 1 {!r} in {}, found {}".format(old, FLOW, text.count(old)))
    return text.replace(old, new)


def added(line):
    """The committed flow.md with line added as a bullet just before the DECISIONS bullet."""
    return changed(DECISIONS, line + "\n" + DECISIONS)


class Verdicts(unittest.TestCase):
    def assert_passes(self, text):
        status, output = verdict(text)
        self.assertEqual(status, 0, output)
        self.assertTrue(output.startswith("OK: "), output)

    def assert_fails(self, text, reason):
        status, output = verdict(text)
        self.assertEqual(status, 1, output)
        self.assertIn(reason, output)

    def test_the_committed_flow_passes(self):
        self.assert_passes(committed())

    def test_the_mode_text_of_main_fails(self):
        status, output = verdict(MAIN_MODE_TEXT)
        self.assertEqual(status, 1, output)
        lines = output.splitlines()
        self.assertEqual(lines[-1], "FAIL: 9 finding(s)", output)
        self.assertEqual(sum(WRONG_MODES in line for line in lines), 1, output)
        self.assertEqual(sum(BARE in line for line in lines), 7, output)
        self.assertEqual(sum(NO_ABSENT in line for line in lines), 1, output)

    def test_a_third_value_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous | unattended | supervised)"),
                          WRONG_MODES)

    def test_an_unquoted_bare_attended_fails(self):
        self.assert_fails(added("- Absent = attended (conservative)."), BARE)

    def test_the_absent_record_sentence_removed_fails(self):
        self.assert_fails(changed(ABSENT_WORDS, "reads the mode record"), NO_ABSENT)

    def test_a_quoted_attended_passes(self):
        self.assert_passes(added("- A record that holds \"attended\" is a legacy record."))


class Residual(unittest.TestCase):
    def test_a_third_value_outside_the_mode_line_passes(self):
        status, output = verdict(added("- A third mode, supervised, is also read."))
        self.assertEqual(status, 0, output)

    def test_a_quoted_retired_default_passes(self):
        status, output = verdict(added("- Absent = \"attended\" (conservative)."))
        self.assertEqual(status, 0, output)

    def test_a_sentence_that_contradicts_the_absent_rule_passes(self):
        status, output = verdict(added("- A session reads a missing record as attended-autonomous."))
        self.assertEqual(status, 0, output)

    def test_the_absent_rule_in_other_words_fails(self):
        status, output = verdict(changed(ABSENT_WORDS, "treats a missing mode record as unattended"))
        self.assertEqual(status, 1, output)
        self.assertIn(NO_ABSENT, output)

    def test_an_ordinary_english_attended_fails(self):
        status, output = verdict(added("- The operator attended the planning call."))
        self.assertEqual(status, 1, output)
        self.assertIn(BARE, output)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
