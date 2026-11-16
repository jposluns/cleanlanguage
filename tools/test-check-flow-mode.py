#!/usr/bin/env python3
"""Tests for tools/check-flow-mode.py: its verdict on the flow.md texts it must pass or fail.

Each case runs the check as a separate process, isolated (-I), and asserts its exit status, 0 for
a pass and 1 for a failure, and for a failure the report line that names the reason. Most cases
give the check the text on standard input.

The check pins the 7 paragraphs of .claude/commands/flow.md that NAMED below lists, by name and
opening text; every edit of those 7 paragraphs fails the check until the paragraph's sha256 in
the check's PARAGRAPHS is updated. The test holds its own list, so a check whose table drops,
adds or moves a paragraph fails, and it reads the paragraph texts only from flow.md.

The verdict cases are these. The committed flow.md passes on standard input, as a path argument
and as the default path, and its pass gives the count of pinned paragraphs. The check's table
names the 7 paragraphs of NAMED, in that order and with the same opening texts; each of its
sha256 values is the one this test computes from flow.md, and each stands alone on 1 line of the
check in the form that the report gives. The entry list of the whole-line rule, Entries 61, 63,
64 and 69, lies inside the pinned FAILED LEG paragraph. The mode text of main's flow.md at ee6be48
fails with 16 findings, 9 from the mode tests and 1 for each pinned paragraph, which the copied
lines do not hold; the case copies the lines of that flow.md that the mode tests report, so it
needs no git history and runs in a shallow checkout. For each of the 7 pinned paragraphs, the
committed flow.md with 1 change each fails with the report that the paragraph has changed when a
word is appended to it, its last character is removed, a character is joined just after its
opening text, a letter changes case, a comma becomes a semicolon, 2 words are joined, a blank
line or a line of white space is put inside it, a line is added just after it, or the blank line
after it is removed so that it joins the next paragraph; it fails with the paragraph found 0
times when its opening text changes, when an indent is put before its opening text, or when the
blank line before it is removed so that it joins the paragraph before it, and found 2 times when
it is repeated; and it passes when the white space between 2 of its words is replaced by a line
break and an indent, a carriage return and a line break, a tab, a no-break space, an em space, an
ideographic space, a unit separator (U+001F), a line separator (U+2028) or a doubled space, and
when white space is put after its last word. For each pinned paragraph, the report of a change
names the paragraph and its line range, gives its new sha256 and gives the 1-line update to
PARAGRAPHS, and a copy of the check with that 1 line updated passes the changed text. Each
pinned paragraph passes at the start of the file and at the end of the file with no final line
break, where its last character removed fails. A mention of an opening text inside another
paragraph passes. The committed flow.md fails with each of these rule changes: Entry 62 put back
in the entry list of the whole-line rule, before, inside or after it, or between it and the
attribution to Entry 125, and the list's count made 5; the attribution to Entry 125 removed; the
whole-line test replaced; the found clause reverted to "on its cited line"; the range of a range
quote widened to 2 lines; the allowances made alternatives only; a quote of part of a line
allowed; the quote conditions bound to every leg; a checker for each family; a clause negated;
the tier floor replaced and in other words; the header naming 3 tier rules; the statement of the
tier rules kept here cut; and the floor removed from the header, from cycle step 4 and from the
tiers paragraph. The committed flow.md with 1 change each fails when its
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
when it stands between that closing quote and the next opening quote. Text outside the 7 pinned
paragraphs is not pinned: an edit of the keep-ahead buffer paragraph passes, and so does a
paragraph elsewhere that adds Entry 62 to the entries of the whole-line rule.

Usage: python3 -I tools/test-check-flow-mode.py
Exit 0 when every case passes; 1 otherwise.
"""
import hashlib
import importlib.util
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
# mode tests report here what they report on the whole file; the copied lines hold none of the 7
# pinned paragraphs, so the check also reports each of those.
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
CHANGED = "{}, a pinned paragraph, has changed: its sha256 is now "
NOT_ONCE = "expected 1 pinned paragraph, {}, starting {!r}, found {}"
PINS_PRESENT = "the 7 pinned paragraphs are unchanged"
# The report line for a changed paragraph, written out here so that a check whose report drops
# any part of it, or whose 1-line update does not match its table, fails.
REPORT = ("FAIL: -:{}-{}: {}, a pinned paragraph, has changed: its sha256 is now {}; to accept the"
          " change, replace the line '     \"{}\"),' of PARAGRAPHS in tools/check-flow-mode.py"
          " with '     \"{}\"),'")
DIGEST_LINE = "     \"{}\"),"
ENTRIES = "Entries 61, 63, 64 and 69"

# The 7 pinned paragraphs, by the name the check's report gives each and the text it starts with.
NAMED = [
    ("the header", "INTERIM. This command's own inlined text"),
    ("the cycle steps", "1. REFRESH: "),
    ("the seeding paragraph", "Per item (the machine-local"),
    ("FAILED LEG", "FAILED LEG (every family, every tier):"),
    ("the CODEX ROLE LIMIT", "CODEX ROLE LIMIT: "),
    ("the tiers paragraph", "The tiers (light, substantive, and sensitive)"),
    ("VERIFIER DIVERSITY", "VERIFIER DIVERSITY (QA, every tier):"),
]
BLANK_LINE = re.compile(r"\n[^\S\n]*\n")

# Kinds of white space that may stand between 2 words of a pinned paragraph, each by name.
SPACES = [
    ("a line break and an indent", "\n   "),
    ("a carriage return and a line break", "\r\n"),
    ("a tab", "\t"),
    ("a no-break space", chr(0x00A0)),
    ("an em space", chr(0x2003)),
    ("an ideographic space", chr(0x3000)),
    ("a unit separator", chr(0x001F)),
    ("a line separator", chr(0x2028)),
    ("a doubled space", "  "),
]

# Rule changes in the pinned paragraphs, each as the paragraph it is in, a text that flow.md
# holds once, and its replacement.
RULE_CHANGES = [
    ("FAILED LEG", ENTRIES, "Entries 61, 62, 63, 64 and 69"),
    ("FAILED LEG", ENTRIES, "Entries 62, 61, 63, 64 and 69"),
    ("FAILED LEG", ENTRIES, "Entries 61, 63, 64 and 69 and of Entry 62"),
    ("FAILED LEG", ENTRIES, "Entries 61, 63, 64, 69 and 62"),
    ("FAILED LEG", ENTRIES, "Entries 61, 63, 64 and 69, 62"),
    ("FAILED LEG", "as these 4):", "as these 4) and Entry 62:"),
    ("FAILED LEG", "as these 4):", "as these 5):"),
    ("FAILED LEG", "Entry 125 states, the rule", "Entry 125 states, the rule of Entry 62 and the rule"),
    ("FAILED LEG", "the whole-line rule that Entry 125 states,", "the whole-line rule,"),
    ("FAILED LEG", "must be a whole line, from the line's first character to its last",
     "must be found within 1 line"),
    ("FAILED LEG", "is the whole of its cited line", "is on its cited line"),
    ("FAILED LEG", "within 1 line of the cited range", "within 2 lines of the cited range"),
    ("FAILED LEG", "only once either or both of 2 allowances apply",
     "only once each of 2 allowances applies alone"),
    ("FAILED LEG", "a quote of only part of a line, text", "text"),
    ("FAILED LEG", "conditions bind review legs only", "conditions bind every leg"),
    ("FAILED LEG", "and 1 checker applies it", "and a checker for each family applies it"),
    ("FAILED LEG", "(2) a quote in it is absent", "(2) it is false that a quote in it is absent"),
    ("the CODEX ROLE LIMIT", "A critical change is never graded light:",
     "A critical change may be graded light:"),
    ("the CODEX ROLE LIMIT", "A critical change is never graded light:",
     "A critical change is never given the light tier:"),
    ("the header", "governs, apart from the 2", "governs, apart from the 3"),
    ("the header", "HOLD; that section and the CODEX ROLE LIMIT below both state",
     "HOLD; the CODEX ROLE LIMIT below states"),
    ("the cycle steps", "which never grades a critical", "which may grade a critical"),
    ("the tiers paragraph",
     "escalation is immediate and de-escalation needs a maintainer decision and a",
     "escalation is immediate and de-escalation needs a"),
    ("the tiers paragraph", "The CODEX ROLE LIMIT and that section both state the",
     "The CODEX ROLE LIMIT states the"),
]


def run_check(args, data=b"", check=CHECK):
    """The exit status of the check run with args and data on standard input, and its output."""
    run = subprocess.run([sys.executable, "-I", str(check)] + args, input=data,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, check=False)
    return run.returncode, run.stdout.decode("utf-8", "replace")


def verdict(text, check=CHECK):
    """The exit status of the check run on text, and its output."""
    return run_check(["-"], text.encode("utf-8"), check)


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


def span(text, opening):
    """The start and end offsets in text of the 1 paragraph that starts a line with opening and
    ends before the next blank line or at the end of text."""
    if text.count("\n" + opening) != 1:
        raise AssertionError("expected 1 line starting {!r} in {}".format(opening, FLOW))
    start = text.index("\n" + opening) + 1
    blank = BLANK_LINE.search(text, start)
    return start, blank.start() if blank else len(text)


def line_range(text, opening):
    """The first and last line numbers in text of the paragraph that starts with opening."""
    start, end = span(text, opening)
    return text.count("\n", 0, start) + 1, text.count("\n", 0, end) + 1


def with_paragraph(opening, change):
    """The committed flow.md with the paragraph that starts with opening replaced by change of
    it."""
    text = committed()
    start, end = span(text, opening)
    return text[:start] + change(text[start:end]) + text[end:]


def own_digest(paragraph):
    """The sha256 of paragraph with each run of white space collapsed to 1 space, as this test
    computes it."""
    return hashlib.sha256(" ".join(paragraph.split()).encode("utf-8")).hexdigest()


def check_module():
    """tools/check-flow-mode.py loaded as a module, without running its main."""
    spec = importlib.util.spec_from_file_location("check_flow_mode", str(CHECK))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def after(paragraph, opening, pattern):
    """The offset of the first match of pattern in paragraph after its opening text."""
    return re.compile(pattern).search(paragraph, len(opening)).start()


def space_at(paragraph, opening):
    """The offset of the first space between 2 words of paragraph after its opening text."""
    return after(paragraph, opening, r"\w \w") + 1


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

    def test_the_committed_flow_passes_with_the_7_paragraphs(self):
        self.assert_passes_with_pins(committed())

    def test_the_check_pins_the_7_paragraphs(self):
        table = check_module().PARAGRAPHS
        self.assertEqual([(name, opening) for name, opening, _ in table], NAMED)
        text = committed()
        source = CHECK.read_text(encoding="utf-8").split("\n")
        for name, opening, pinned in table:
            with self.subTest(paragraph=name):
                start, end = span(text, opening)
                self.assertEqual(pinned, own_digest(text[start:end]))
                self.assertEqual(source.count(DIGEST_LINE.format(pinned)), 1)

    def test_the_entry_list_is_inside_the_pinned_failed_leg_paragraph(self):
        # The opening comes from the check's own table, so the list is pinned only when the check
        # pins the paragraph that holds it.
        openings = {name: opening for name, opening, _ in check_module().PARAGRAPHS}
        text = committed()
        start, end = span(text, openings["FAILED LEG"])
        self.assertEqual(" ".join(text[start:end].split()).count(ENTRIES), 1)
        self.assertEqual(" ".join(text.split()).count(ENTRIES), 1)
        self.assert_passes_with_pins(text)

    def test_each_pinned_paragraph_changed_fails(self):
        # Each change leaves the paragraph's opening text in place, so the paragraph is found and
        # its sha256 differs; a check that ignored any of these changes would pass that copy.
        changes = [
            ("a word appended", lambda p, o: p + " x"),
            ("its last character removed", lambda p, o: p[:-1]),
            ("a character joined after its opening", lambda p, o: p[:len(o)] + "x" + p[len(o):]),
            ("a letter in another case", lambda p, o: (
                lambda i: p[:i] + p[i].upper() + p[i + 1:])(after(p, o, r"[a-z]"))),
            ("a comma made a semicolon", lambda p, o: (
                lambda i: p[:i] + ";" + p[i + 1:])(after(p, o, r","))),
            ("2 words joined", lambda p, o: (
                lambda i: p[:i] + p[i + 1:])(space_at(p, o))),
            ("a blank line put inside", lambda p, o: (
                lambda i: p[:i] + "\n\n" + p[i + 1:])(space_at(p, o))),
            ("a line of white space put inside", lambda p, o: (
                lambda i: p[:i] + "\n \t" + chr(0x00A0) + "\n" + p[i + 1:])(space_at(p, o))),
            ("a line added after it", lambda p, o: p + "\nx"),
        ]
        for name, opening in NAMED:
            for what, change in changes:
                with self.subTest(paragraph=name, change=what):
                    self.assert_fails(with_paragraph(opening, lambda p: change(p, opening)),
                                      CHANGED.format(name))
            with self.subTest(paragraph=name, change="joined to the next paragraph"):
                text = committed()
                _, end = span(text, opening)
                blank = BLANK_LINE.match(text, end)
                self.assert_fails(text[:end] + "\n" + text[blank.end():], CHANGED.format(name))

    def test_each_pinned_paragraph_not_found_once_fails(self):
        for name, opening in NAMED:
            with self.subTest(paragraph=name, change="opening changed"):
                self.assert_fails(with_paragraph(opening, lambda p: "x" + p[1:]),
                                  NOT_ONCE.format(name, opening, 0))
            with self.subTest(paragraph=name, change="indent before its opening"):
                self.assert_fails(with_paragraph(opening, lambda p: " " + p),
                                  NOT_ONCE.format(name, opening, 0))
            with self.subTest(paragraph=name, change="joined to the paragraph before it"):
                text = committed()
                start, _ = span(text, opening)
                self.assert_fails(text[:start].rstrip() + "\n" + text[start:],
                                  NOT_ONCE.format(name, opening, 0))
            with self.subTest(paragraph=name, change="repeated"):
                self.assert_fails(with_paragraph(opening, lambda p: p + "\n\n" + p),
                                  NOT_ONCE.format(name, opening, 2))

    def test_each_pinned_paragraph_rewrapped_passes(self):
        # Only the amount and kind of white space between words, or after the last word, changes.
        for name, opening in NAMED:
            for what, space in SPACES:
                with self.subTest(paragraph=name, space=what):
                    self.assert_passes_with_pins(with_paragraph(
                        opening, lambda p, s=space, o=opening: (
                            lambda i: p[:i] + s + p[i + 1:])(space_at(p, o))))
            with self.subTest(paragraph=name, space="after its last word"):
                self.assert_passes_with_pins(with_paragraph(opening, lambda p: p + " \t"))

    def test_each_report_of_a_change_gives_the_1_line_update(self):
        table = {name: pinned for name, _, pinned in check_module().PARAGRAPHS}
        source = CHECK.read_text(encoding="utf-8")
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                text = with_paragraph(opening, lambda p: p + " x")
                first, last = line_range(text, opening)
                start, end = span(text, opening)
                now = own_digest(text[start:end])
                status, output = verdict(text)
                self.assertEqual(status, 1, output)
                self.assertIn(REPORT.format(first, last, name, now, table[name], now),
                              output.splitlines())
                old_line = DIGEST_LINE.format(table[name])
                self.assertEqual(source.count(old_line), 1)
                with tempfile.TemporaryDirectory() as folder:
                    updated = Path(folder) / "check-flow-mode.py"
                    updated.write_text(source.replace(old_line, DIGEST_LINE.format(now)),
                                       encoding="utf-8")
                    status, output = verdict(text, updated)
                self.assertEqual(status, 0, output)
                self.assertIn(PINS_PRESENT, output)

    def test_an_opening_text_inside_another_paragraph_passes(self):
        # Only a paragraph that starts with the opening text counts, so a mention of it inside
        # another paragraph is not a second paragraph of that name.
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                self.assert_passes_with_pins(added("- See " + opening + " above."))

    def test_each_pinned_paragraph_at_the_start_of_the_file_passes(self):
        text = committed()
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                start, end = span(text, opening)
                self.assert_passes_with_pins(text[start:end] + "\n\n" + text[:start] + text[end:])

    def test_each_pinned_paragraph_at_the_end_of_the_file_passes(self):
        # The text ends with the pinned paragraph and no line break, so the paragraph's verdict
        # depends on the check reading a paragraph that the end of the text closes.
        text = committed()
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                start, end = span(text, opening)
                rest = text[:start] + text[end:]
                self.assertTrue(rest.endswith("\n"))
                self.assert_passes_with_pins(rest + "\n" + text[start:end])
                self.assert_fails(rest + "\n" + text[start:end - 1], CHANGED.format(name))

    def test_each_rule_change_in_a_pinned_paragraph_fails(self):
        for name, old, new in RULE_CHANGES:
            with self.subTest(paragraph=name, old=old, new=new):
                self.assert_fails(changed(old, new), CHANGED.format(name))

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
        self.assertEqual(lines[-1], "FAIL: 16 finding(s)", output)
        self.assertEqual(sum(WRONG_MODES in line for line in lines), 1, output)
        self.assertEqual(sum(BARE in line for line in lines), 7, output)
        self.assertEqual(sum(NO_ABSENT in line for line in lines), 1, output)
        for name, opening in NAMED:
            self.assertEqual(sum(NOT_ONCE.format(name, opening, 0) in line for line in lines), 1,
                             output)

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

    def test_an_edit_outside_the_pinned_paragraphs_passes(self):
        status, output = verdict(changed("Keep-ahead buffer: at every invocation",
                                         "Keep-ahead buffer: at each invocation"))
        self.assertEqual(status, 0, output)
        self.assertIn(PINS_PRESENT, output)

    def test_entry_62_added_to_the_rule_in_another_paragraph_passes(self):
        status, output = verdict(added("- The whole-line rule also rests on Entry 62."))
        self.assertEqual(status, 0, output)
        self.assertIn(PINS_PRESENT, output)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
