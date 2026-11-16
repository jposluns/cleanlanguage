#!/usr/bin/env python3
"""Tests for tools/check-flow-mode.py: its verdict on the flow.md texts it must pass or fail.

Each case runs the check as a separate process, isolated (-I), and asserts its exit status, 0 for
a pass and 1 for a failure, and for a failure the report line that names the reason. Most cases
give the check the text on standard input.

The verdict cases are these. The committed .claude/commands/flow.md passes on standard input, as
a path argument and as the default path, and its pass names the 8 pinned texts. The mode text of
main's flow.md at ee6be48 fails with 17 findings, 9 from the mode tests and 1 for each pinned
text, which the copied lines do not hold; the case copies the lines of that flow.md that the mode
tests report, so it needs no git history and runs in a shallow checkout. The committed flow.md
with 1 change each fails when any 1 of the 8 pinned texts is replaced: the header's statement of
the 2 tier rules that /flow keeps, the attribution of the whole-line rule to Entry 125, its entry
list (Entries 61, 63, 64 and 69), its whole-line test, its allowances, which may apply alone or
together, its failures, among them a quote of only part of a line, the tier floor that a
critical change is never graded light, and the tiers section's statement of the 2 tier rules
that /flow keeps; when the entry list puts Entry 62 back, inside the list or after it; and, for
each pinned text, when it is in another letter case, when its first word or its last word is
cut, and when another character is joined to its first or its last character. The committed
flow.md with 1 change each fails when its
MODE line names a third value, repeats a value, names a value with capital letters, drops either
value, uses a comma as the separator or puts its values inside double quotes, when the MODE line
is renamed so that none is left, when a second MODE line is added, closed or with no closing
parenthesis, when the MODE line loses its closing parenthesis, when a line holds an unquoted bare
"attended" in lower case, with a capital letter or inside typographic quotes, when such a line
comes after line 250, when a line holds a longer word that starts with "attended-autonomous",
such as "attended-autonomously", when a bare "attended" follows a closing quote at once, as in
'un"stored"attended', since the check reads a quotation as a space and so does not join the text
on its 2 sides, and when the absent-record sentence is removed. It passes with the MODE values in
the other order, with a quoted "attended", with a quotation just after "attended-autonomous", as
in 'attended-autonomous"x"ly', with a longer word that holds "attended", with
"Attended-Autonomous" in capital letters outside the MODE line, and with the absent-record
sentence in its second wording, in capital letters, or wrapped across a line break. A path that
does not exist, text that is not UTF-8 and 2 arguments each give exit status 1.

The residual cases hold the limits that the check's docstring states: outside the MODE line only
the bare "attended" test can fail a line, so a third mode value named there, such as "supervised",
passes, and one that holds a bare "attended", such as "attended-only", fails; an indented line
that starts "- MODE (" after its indent is not counted and passes, a retired default inside
straight double quotes passes, a sentence that contradicts the
absent rule passes, the matched absent-rule sentence negated passes, the absent-rule sentence
inside a quotation that rejects it passes, the absent rule in other words fails, an ordinary
English use of "attended" fails, a quoted "attended" whose quotes wrap across a line break
fails, and a bare "attended" passes on a line that closes a quotation wrapped from the line above
when it stands between that closing quote and the next opening quote. For the pinned texts, a
pinned text rewrapped across other line breaks passes, a pinned text kept inside a sentence that
negates it passes, a sentence elsewhere that adds Entry 62 to the entries of the whole-line rule
passes, and the tier floor in other words fails.

Usage: python3 -I tools/test-check-flow-mode.py
Exit 0 when every case passes; 1 otherwise.
"""
import re
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
# mode tests report here what they report on the whole file; the copied lines hold none of the 8
# pinned texts, so the check also reports each of those.
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
PIN_MISSING = "the pinned text of {} is missing"
PINS_PRESENT = "the 8 pinned texts are present"

# The 8 pinned texts, as tools/check-flow-mode.py names them in its reports.
HEADER_RULES = ("the header's statement of which tier rules /flow keeps",
                "apart from the 2 tier rules that it names as kept here, the escalation rule of"
                " cycle step 4 (GRADE) and the AIQT HOLD;")
ENTRY_125 = ("the attribution of the whole-line rule to Entry 125",
             "(3) a quote in it breaches the whole-line rule that Entry 125 states,")
ENTRY_LIST = ("the entry list of the whole-line rule",
              "the rule of the maintainer decisions of Entries 61, 63, 64 and 69 (2026-11-14 and"
              " 2026-11-15; the coordinator's correction recorded with Entry 127, 2026-11-15,"
              " gives the rule's entries as these 4):")
WHOLE_LINE = ("the whole-line test of the FAILED LEG rule",
              "a single-line quote must be a whole line, from the line's first character to its"
              " last, and a range quote must be whole lines;")
ALLOWANCES = ("the allowances of the whole-line rule",
              "either of them also when it matches in that way only once either or both of 2"
              " allowances apply, each line's leading spaces stripped or its Markdown formatting"
              " marks (backticks, emphasis asterisks or underscores) missing, with each offset,"
              " range, collapse and mark recorded;")
FAILURES = ("the failures of the whole-line rule",
            "a quote of only part of a line, text more than 1 line off, changed or missing words,"
            " a dropped comment marker, or any other changed character fails it.")
TIER_FLOOR = ("the tier floor of the CODEX ROLE LIMIT",
              "A critical change is never graded light: it is of at least the substantive tier,")
TIER_RULES = ("the statement of which tier rules /flow keeps",
              "so do the 2 tier rules kept here, which the \"Working method\" section names: in"
              " cycle step 4 (GRADE), escalation is immediate and de-escalation needs a"
              " maintainer decision and a recorded basis; and the AIQT HOLD above.")
PINS = (HEADER_RULES, ENTRY_125, ENTRY_LIST, WHOLE_LINE, ALLOWANCES, FAILURES, TIER_FLOOR,
        TIER_RULES)
ENTRIES = "Entries 61, 63, 64 and 69"


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


def replaced(pin, new):
    """The committed flow.md with its one occurrence of the text pin, however its words wrap,
    replaced by new."""
    text = committed()
    words = re.compile(r"\s+".join(re.escape(word) for word in pin.split()))
    found = words.findall(text)
    if len(found) != 1:
        raise AssertionError("expected 1 {!r} in {}, found {}".format(pin, FLOW, len(found)))
    return words.sub(lambda match: new, text)


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

    def assert_passes_with_pins(self, text):
        status, output = verdict(text)
        self.assertEqual(status, 0, output)
        self.assertTrue(output.startswith("OK: "), output)
        self.assertIn(PINS_PRESENT, output)

    def test_the_committed_flow_passes(self):
        self.assert_passes(committed())

    def test_the_committed_flow_passes_with_the_8_pins(self):
        self.assert_passes_with_pins(committed())

    def test_the_header_tier_rule_statement_replaced_fails(self):
        self.assert_fails(replaced(HEADER_RULES[1],
                                   "apart from the 3 tier rules kept here, the floor among them;"),
                          PIN_MISSING.format(HEADER_RULES[0]))

    def test_the_entry_125_attribution_removed_fails(self):
        self.assert_fails(replaced(ENTRY_125[1],
                                   ENTRY_125[1].replace(" that Entry 125 states", "")),
                          PIN_MISSING.format(ENTRY_125[0]))

    def test_the_whole_line_test_replaced_fails(self):
        self.assert_fails(replaced(WHOLE_LINE[1], "a quote must be found within 1 line;"),
                          PIN_MISSING.format(WHOLE_LINE[0]))

    def test_the_allowances_as_alternatives_only_fail(self):
        self.assert_fails(replaced(ALLOWANCES[1], ALLOWANCES[1].replace(
            "only once either or both of 2 allowances apply, each line's leading spaces"
            " stripped or", "only once each line's leading spaces are stripped or only without")),
                          PIN_MISSING.format(ALLOWANCES[0]))

    def test_a_quote_of_part_of_a_line_allowed_fails(self):
        self.assert_fails(replaced(FAILURES[1], "a quote of part of a line counts."),
                          PIN_MISSING.format(FAILURES[0]))

    def test_the_entry_list_replaced_fails(self):
        self.assert_fails(replaced(ENTRY_LIST[1],
                                   ENTRY_LIST[1].replace(ENTRIES, "Entries 61 to 64 and 69")),
                          PIN_MISSING.format(ENTRY_LIST[0]))

    def test_the_entry_list_with_entry_62_put_back_fails(self):
        for entries in ("Entries 61, 62, 63, 64 and 69", "Entries 62, 61, 63, 64 and 69",
                        "Entries 61, 63, 64 and 69 and of Entry 62",
                        "Entries 61, 63, 64, 69 and 62", "Entries 61, 63, 64 and 69, 62"):
            with self.subTest(entries=entries):
                self.assert_fails(replaced(ENTRY_LIST[1], ENTRY_LIST[1].replace(ENTRIES, entries)),
                                  PIN_MISSING.format(ENTRY_LIST[0]))
        self.assert_fails(replaced(ENTRY_LIST[1], ENTRY_LIST[1].replace("these 4", "these 5")),
                          PIN_MISSING.format(ENTRY_LIST[0]))

    def test_the_tier_floor_replaced_fails(self):
        self.assert_fails(replaced(TIER_FLOOR[1], "A critical change may be graded light"),
                          PIN_MISSING.format(TIER_FLOOR[0]))

    def test_the_tier_rule_statement_replaced_fails(self):
        self.assert_fails(replaced(TIER_RULES[1],
                                   "the 3 tier rules kept here: in cycle step 4 (GRADE), escalation"
                                   " is immediate; and the AIQT HOLD above"),
                          PIN_MISSING.format(TIER_RULES[0]))

    def test_a_pinned_text_in_another_letter_case_fails(self):
        self.assert_fails(replaced(TIER_FLOOR[1], TIER_FLOOR[1].lower()),
                          PIN_MISSING.format(TIER_FLOOR[0]))

    def test_each_pinned_text_in_another_letter_case_fails(self):
        # A check that compared any 1 pin without regard to letter case would pass the upper-case
        # copy of that pin.
        for label, pin in PINS:
            with self.subTest(pin=label):
                self.assertNotEqual(pin, pin.upper())
                self.assert_fails(replaced(pin, pin.upper()), PIN_MISSING.format(label))

    def test_each_pinned_text_with_its_last_word_cut_fails(self):
        # A check whose pin held only a prefix of the pinned text would pass this copy.
        for label, pin in PINS:
            with self.subTest(pin=label):
                self.assert_fails(replaced(pin, pin.rsplit(" ", 1)[0]), PIN_MISSING.format(label))

    def test_each_pinned_text_with_its_first_word_cut_fails(self):
        # A check whose pin held only a suffix of the pinned text would pass this copy.
        for label, pin in PINS:
            with self.subTest(pin=label):
                self.assert_fails(replaced(pin, pin.split(" ", 1)[1]), PIN_MISSING.format(label))

    def test_each_pinned_text_joined_to_another_character_fails(self):
        # A check that looked for a pin as a bare substring would pass these copies, since each
        # still holds the pinned text, joined to 1 more character on 1 side.
        for label, pin in PINS:
            for joined in ("x" + pin, pin + "x"):
                with self.subTest(pin=label, joined=joined[:1] + "..." + joined[-1:]):
                    self.assert_fails(replaced(pin, joined), PIN_MISSING.format(label))

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
        self.assertEqual(lines[-1], "FAIL: 17 finding(s)", output)
        self.assertEqual(sum(WRONG_MODES in line for line in lines), 1, output)
        self.assertEqual(sum(BARE in line for line in lines), 7, output)
        self.assertEqual(sum(NO_ABSENT in line for line in lines), 1, output)
        for label, _ in PINS:
            self.assertEqual(sum(PIN_MISSING.format(label) in line for line in lines), 1, output)

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

    def test_a_bare_attended_just_after_a_closing_quote_fails(self):
        # The quotation reads as a space, so the "un" before it does not join the "attended" after
        # it, and the line holds a bare "attended" outside the quotes.
        self.assert_fails(added("- A legacy un\"stored\"attended record."), BARE)

    def test_a_quotation_just_after_attended_autonomous_passes(self):
        # The quotation reads as a space, so the "ly" after it does not extend
        # "attended-autonomous" into a longer word, and the line holds no bare "attended".
        self.assert_passes(added("- The session runs attended-autonomous\"x\"ly."))

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

    def test_a_third_value_with_a_bare_attended_outside_the_mode_line_fails(self):
        # Outside the MODE line only the bare-word test can fail a line, so a third value named
        # there fails exactly when it holds a bare "attended", whatever value it is.
        status, output = verdict(added("- A third mode, attended-only, is also read."))
        self.assertEqual(status, 1, output)
        self.assertIn(BARE, output)

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

    def test_a_pinned_text_rewrapped_passes(self):
        status, output = verdict(replaced(ENTRY_LIST[1], ENTRY_LIST[1].replace(
            ENTRIES, "Entries 61,\n63, 64\n  and 69")))
        self.assertEqual(status, 0, output)
        self.assertIn(PINS_PRESENT, output)

    def test_a_pinned_text_inside_a_negating_sentence_passes(self):
        status, output = verdict(replaced(WHOLE_LINE[1], "it is false that " + WHOLE_LINE[1]))
        self.assertEqual(status, 0, output)
        self.assertIn(PINS_PRESENT, output)

    def test_entry_62_added_to_the_rule_in_another_sentence_passes(self):
        status, output = verdict(added("- The whole-line rule also rests on Entry 62."))
        self.assertEqual(status, 0, output)
        self.assertIn(PINS_PRESENT, output)

    def test_the_tier_floor_in_other_words_fails(self):
        status, output = verdict(replaced(
            TIER_FLOOR[1], "A critical change is never given the light tier: it is of at least the"
            " substantive tier,"))
        self.assertEqual(status, 1, output)
        self.assertIn(PIN_MISSING.format(TIER_FLOOR[0]), output)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
