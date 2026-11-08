#!/usr/bin/env python3
"""Tests for tools/check-flow-mode.py: its verdict on the flow.md texts it must pass or fail.

Each case runs the check as a separate process, isolated (-I), and asserts its exit status, 0 for
a pass and 1 for a failure, and for a failure the report line that names the reason. Most cases
give the check the text on standard input.

The verdict cases are these. The committed .claude/commands/flow.md passes on standard input, as
a path argument and as the default path. The mode text of main's flow.md at ee6be48 fails with 9
findings; the case copies the lines of that flow.md that the check reports, so it needs no git
history and runs in a shallow checkout. The committed flow.md with 1 change each fails when its
MODE line names a third value, repeats a value, names a value with capital letters, drops either
value, uses a comma as the separator or puts its values inside double quotes, when the MODE line
is renamed so that none is left, when a second MODE line is added, closed or with no closing
parenthesis, when the MODE line loses its closing parenthesis, when a line holds an unquoted bare
"attended" in lower case, with a capital letter or inside typographic quotes, when such a line
comes after line 250, when a line holds a longer word that starts with "attended-autonomous",
such as "attended-autonomously", and when the absent-record sentence is removed. It passes with
the MODE values in the other order, with a quoted "attended", with a longer word that holds
"attended", with "Attended-Autonomous" in capital letters outside the MODE line, and with the
absent-record sentence in its second wording, in capital letters, or wrapped across a line
break. A path that does not exist, text
that is not UTF-8 and 2 arguments each give exit status 1.

The residual cases hold the limits that the check's docstring states: a third mode value, other
than the writer's 2 and the retired "attended", named outside the MODE line passes, an indented
line that starts "- MODE (" after its indent is not counted and passes, a retired default inside
straight double quotes passes, a sentence that contradicts the
absent rule passes, the matched absent-rule sentence negated passes, the absent-rule sentence
inside a quotation that rejects it passes, the absent rule in other words fails, an ordinary
English use of "attended" fails, a quoted "attended" whose quotes wrap across a line break
fails, and a bare "attended" passes on a line that closes a quotation wrapped from the line above
when it stands between that closing quote and the next opening quote.

Usage: python3 -I tools/test-check-flow-mode.py
Exit 0 when every case passes; 1 otherwise.
"""
import subprocess
import sys
import tempfile
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
UNCLOSED = "the MODE line has no closing parenthesis"
NO_ABSENT = "no statement that an absent mode record is read as unattended"


def run_check(args, data=b""):
    """The exit status of the check run with args and data on standard input, and its output."""
    run = subprocess.run([sys.executable, "-I", str(CHECK)] + args, input=data,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, check=False)
    return run.returncode, run.stdout.decode("utf-8", "replace")


def verdict(text):
    """The exit status of the check run on text, and its output."""
    return run_check(["-"], text.encode("utf-8"))


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

    def assert_status_one(self, status, output, reason):
        self.assertEqual(status, 1, output)
        self.assertIn(reason, output)

    def test_the_committed_flow_passes(self):
        self.assert_passes(committed())

    def test_the_committed_flow_passes_by_path_and_by_default(self):
        for args in ([str(FLOW)], []):
            with self.subTest(args=args):
                status, output = run_check(args)
                self.assertEqual(status, 0, output)
                self.assertTrue(output.startswith("OK: "), output)

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

    def test_a_repeated_value_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous | unattended | unattended)"),
                          WRONG_MODES)

    def test_a_capitalized_value_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (Attended-Autonomous | unattended)"), WRONG_MODES)

    def test_a_dropped_value_on_the_mode_line_fails(self):
        for line in ("- MODE (unattended)", "- MODE (attended-autonomous)"):
            with self.subTest(line=line):
                self.assert_fails(changed(MODE_LINE, line), WRONG_MODES)

    def test_another_separator_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous, unattended)"),
                          WRONG_MODES)

    def test_the_mode_values_in_the_other_order_pass(self):
        self.assert_passes(changed(MODE_LINE, "- MODE (unattended | attended-autonomous)"))

    def test_no_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- Mode (attended-autonomous | unattended)"),
                          "expected 1 MODE line starting \"- MODE (\", found 0")

    def test_a_second_mode_line_fails(self):
        self.assert_fails(added(MODE_LINE + " is repeated."),
                          "expected 1 MODE line starting \"- MODE (\", found 2")

    def test_a_second_unclosed_mode_line_fails(self):
        status, output = verdict(added("- MODE (supervised is a third mode."))
        self.assertEqual(status, 1, output)
        self.assertIn("expected 1 MODE line starting \"- MODE (\", found 2", output)
        self.assertIn(UNCLOSED, output)

    def test_an_unclosed_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous | unattended"), UNCLOSED)

    def test_quoted_values_on_the_mode_line_fail(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (\"attended-autonomous\" | \"unattended\")"),
                          WRONG_MODES)

    def test_an_unquoted_bare_attended_fails(self):
        self.assert_fails(added("- Absent = attended (conservative)."), BARE)

    def test_a_capitalized_bare_attended_fails(self):
        self.assert_fails(added("- Attended is the default."), BARE)

    def test_attended_in_typographic_quotes_fails(self):
        quoted = chr(0x201C) + "attended" + chr(0x201D)
        self.assert_fails(added("- A record that holds " + quoted + " is a legacy record."), BARE)

    def test_a_bare_attended_after_line_250_fails(self):
        # The other bare-word cases add their line just before the DECISIONS bullet, so whether a
        # check that read only the start of the file reaches that line depends on where the bullet
        # is. This case adds its line at the end, after blank lines that place it after line 300
        # whatever line the bullet is on, beyond any likely read limit of such a check.
        text = committed()
        self.assertTrue(text.endswith("\n"))
        count = text.count("\n")
        padding = "\n" * max(0, 300 - count)
        number = count + len(padding) + 1
        status, output = verdict(text + padding + "- Absent = attended (conservative).\n")
        self.assertEqual(status, 1, output)
        self.assertIn("-:{}: {}".format(number, BARE), output)

    def test_the_absent_record_sentence_removed_fails(self):
        self.assert_fails(changed(ABSENT_WORDS, "reads the mode record"), NO_ABSENT)

    def test_a_quoted_attended_passes(self):
        self.assert_passes(added("- A record that holds \"attended\" is a legacy record."))

    def test_a_longer_word_that_holds_attended_passes(self):
        self.assert_passes(added("- The record has no attendedness field."))

    def test_a_word_that_extends_attended_autonomous_fails(self):
        # Only the whole word "attended-autonomous" is exempt, so a longer word that starts with it
        # still holds a bare "attended".
        self.assert_fails(added("- The session runs attended-autonomously."), BARE)

    def test_attended_autonomous_in_capital_letters_passes(self):
        self.assert_passes(added("- Attended-Autonomous is one of the writer's 2 values."))

    def test_the_absent_rule_in_its_second_wording_passes(self):
        self.assert_passes(changed("The session " + ABSENT_WORDS,
                                   "An absent mode record is read as unattended"))

    def test_the_absent_rule_in_capital_letters_passes(self):
        self.assert_passes(changed(ABSENT_WORDS, ABSENT_WORDS.upper()))

    def test_the_absent_rule_wrapped_across_a_line_break_passes(self):
        self.assert_passes(changed(ABSENT_WORDS, "reads an absent mode\n  record as unattended"))

    def test_a_path_that_does_not_exist_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            status, output = run_check([str(Path(folder) / "missing.md")])
        self.assert_status_one(status, output, "cannot be read")

    def test_text_that_is_not_utf8_fails(self):
        status, output = run_check(["-"], committed().encode("utf-8") + b"\xff\n")
        self.assert_status_one(status, output, "cannot be read")

    def test_two_arguments_fail(self):
        status, output = run_check([str(FLOW), str(FLOW)])
        self.assert_status_one(status, output, "usage:")


class Residual(unittest.TestCase):
    def test_a_third_value_outside_the_mode_line_passes(self):
        status, output = verdict(added("- A third mode, supervised, is also read."))
        self.assertEqual(status, 0, output)

    def test_a_quoted_retired_default_passes(self):
        status, output = verdict(added("- Absent = \"attended\" (conservative)."))
        self.assertEqual(status, 0, output)

    def test_an_indented_mode_line_is_not_counted(self):
        status, output = verdict(added("  - MODE (supervised) is a nested bullet."))
        self.assertEqual(status, 0, output)

    def test_the_absent_rule_inside_a_rejecting_quotation_passes(self):
        status, output = verdict(changed(
            "The session " + ABSENT_WORDS,
            "It is false that \"the session " + ABSENT_WORDS + "\"; it reads it as"
            " attended-autonomous"))
        self.assertEqual(status, 0, output)

    def test_a_sentence_that_contradicts_the_absent_rule_passes(self):
        status, output = verdict(added("- A session reads a missing record as attended-autonomous."))
        self.assertEqual(status, 0, output)

    def test_the_matched_absent_sentence_negated_passes(self):
        status, output = verdict(changed(
            "The session " + ABSENT_WORDS,
            "The session never " + ABSENT_WORDS + "; it reads it as attended-autonomous"))
        self.assertEqual(status, 0, output)

    def test_a_quoted_attended_wrapped_across_a_line_break_fails(self):
        status, output = verdict(added("- A record that holds \"the retired\n  attended\" value."))
        self.assertEqual(status, 1, output)
        self.assertIn(BARE, output)

    def test_a_bare_attended_after_a_wrapped_closing_quote_passes(self):
        # The check pairs straight quotes left to right on each line, so the closing quote of the
        # quotation opened on the line above pairs with the opening quote of "for now", and the
        # bare "attended" between them is skipped.
        status, output = verdict(added("- A legacy record is read \"as attended-autonomous, never as\n"
                                       "  unattended\" though Absent = attended \"for now\"."))
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
