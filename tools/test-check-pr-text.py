#!/usr/bin/env python3
"""Tests for tools/check-pr-text.py, the pull request text gate.

Each case runs the gate as a separate process, as CI and a hand run do, with a temporary folder as
its working directory, and checks its exit status and its output. A case that needs a squash
folder copies the gate and the label lint into a temporary tree, since the gate finds both from
its own path. Every review-history label and every dash a case feeds the gate is built when the
case runs, by joining strings or from an escape, so this file carries none of them as text.

The cases fall in 4 groups: a failing case for each mechanical defect class, which includes a code
fence that is never closed, in a description and in a squash message, and a blank text, in each;
the cases at the edges of each exemption and scope limit, which pass honest text inside it and
fail text just outside it, such as the prose after a closed fence, a dash closed up after a URL
or a fence closer the gate does not accept; a case for each kind of unreadable input and for a
usage error, each of which exits 2 with the defect count as its last line; and output prefixes,
runs from other folders, a bound on the time of the inline-code scan, the job's time limit in the
workflow, and honest texts that pass. The class of counts stated with their selection rule has no
case: it stays a judgement for reviewers, because no part of it is mechanical.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "check-pr-text.py"
LINT = HERE / "test-no-qa-labels.py"
WORKFLOW = HERE.parent / ".github" / "workflows" / "pr-text.yml"
PREFIXES = ("description", "squash", "unreadable:", "pr-text:")

EM_DASH = "\u2014"
EN_DASH = "\u2013"
# Review-history labels, joined at run time so that this file holds none as text.
ROUND_LABEL = "fixed in rou" + "nd 7"
FIX_LABEL = "a fix" + " round"
BARE_ID = "R" + "3"
OTHER_BARE_ID = "F" + "1"
ISE_WORD = "standard" + "ise"
# The -ise stems of the gate's denylist, each checked by test_every_ise_stem_fails.
ISE_STEMS = (
    "apolog", "author", "capital", "categor", "central", "character", "critic", "custom",
    "emphas", "final", "formal", "general", "harmon", "initial", "legal", "local", "maxim",
    "memor", "minim", "mobil", "modern", "neutral", "normal", "optim", "organ", "parameter",
    "priorit", "random", "real", "recogn", "sanit", "serial", "special", "stabil",
    "standard", "summar", "synchron", "token", "util", "visual",
)
SHA1 = "e233a7f0c1d2b3a4e5f60718293a4b5c6d7e8f90"
SHA256 = "a1" * 32
CLEAN_SUBJECT = "Add the pull request text gate (#999)"
CLEAN_SQUASH = CLEAN_SUBJECT + "\n\nAdd a gate that checks the texts of a pull request.\n"
UNCLOSED = "the code fence opened on line {} is never closed"
# The inline-code scan must finish this many backticks within this many seconds.
BACKTICK_RUN = 20000
TIME_BOUND = 10


class GateCase(unittest.TestCase):
    """Helpers that write inputs and run the gate."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cwd = self.tmp / "elsewhere"
        self.cwd.mkdir()

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def run_gate(self, *args, gate=GATE, cwd=None, timeout=120):
        """(exit status, output lines) of the gate run with args."""
        done = subprocess.run([sys.executable, "-I", "-B", str(gate), *map(str, args)],
                              cwd=str(cwd or self.cwd), capture_output=True, text=True,
                              encoding="utf-8", timeout=timeout)
        return done.returncode, done.stdout.splitlines()

    def tree(self, squash=None, number=999, lint=True):
        """A copy of the gate in a temporary tree, with the lint and a squash file if given."""
        root = self.tmp / "tree"
        (root / "tools").mkdir(parents=True)
        shutil.copyfile(GATE, root / "tools" / "check-pr-text.py")
        if lint:
            shutil.copyfile(LINT, root / "tools" / "test-no-qa-labels.py")
        if squash is not None:
            (root / ".github" / "squash").mkdir(parents=True)
            (root / ".github" / "squash" / "{}.txt".format(number)).write_text(
                squash, encoding="utf-8")
        return root / "tools" / "check-pr-text.py"

    def event(self, body, number=999, name="event.json"):
        payload = {"action": "opened", "number": number,
                   "pull_request": {"number": number, "body": body}}
        return self.write(name, json.dumps(payload))

    def description(self, text):
        return self.run_gate("--description", self.write("description.md", text))

    def squash(self, text, number=999):
        return self.run_gate("--squash", self.write("squash.txt", text), "--number", number)

    def assertResult(self, result, status, defects):
        code, lines = result
        self.assertEqual(code, status, lines)
        self.assertTrue(lines, "no output")
        self.assertEqual(lines[-1], "pr-text: {} defect(s)".format(defects), lines)

    def assertReports(self, result, fragment):
        self.assertTrue(any(fragment in line for line in result[1]), result[1])


class DefectClasses(GateCase):
    """Each mechanical class fails with a committed case."""

    def test_squash_line_over_72_characters_fails(self):
        result = self.squash(CLEAN_SUBJECT + "\n\n" + "a" * 73 + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:3: 73 characters, over 72")

    def test_squash_line_of_72_characters_passes(self):
        self.assertResult(self.squash(CLEAN_SUBJECT + "\n\n" + "a" * 72 + "\n"), 0, 0)

    def test_label_in_description_fails(self):
        result = self.description("Intro.\n\nThis was " + ROUND_LABEL + ".\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:3: a review round number")

    def test_fix_label_in_description_fails(self):
        self.assertResult(self.description("This came from " + FIX_LABEL + ".\n"), 1, 1)

    def test_label_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\nThis was " + ROUND_LABEL + ".\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: a review round number")

    def test_label_right_after_masked_span_fails(self):
        for text in ("See `x`" + BARE_ID + " for it.\n", 'See "x"' + OTHER_BARE_ID + " here.\n"):
            with self.subTest(text=text):
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: a bare finding id")

    def test_revision_id_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\nBuilt on e233a7f.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: a revision id: e233a7f")

    def test_full_revision_id_in_squash_message_fails(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nBuilt on " + SHA1 + ".\n"), 1, 1)

    def test_revision_id_in_backticks_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\nBuilt on `e233a7f`.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "a revision id: e233a7f")

    def test_em_dash_fails(self):
        result = self.description("The gate " + EM_DASH + " a new check.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_em_dash_in_squash_message_fails(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nA gate " + EM_DASH + " new.\n"), 1, 1)

    def test_en_dash_fails(self):
        result = self.description("The gate " + EN_DASH + " a new check.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an en dash, U+2013")

    def test_en_dash_in_numeric_range_fails(self):
        result = self.description("See pages 12" + EN_DASH + "14.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "an en dash, U+2013")

    def test_dash_after_lone_backtick_and_double_span_fails(self):
        result = self.description("A lone ` backtick, then prose " + EM_DASH
                                  + " shown, then ``code``.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_dash_closed_up_after_url_fails(self):
        result = self.description("See https://example.com" + EM_DASH + "the page.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_ise_spelling_fails(self):
        result = self.description("We " + ISE_WORD + " the texts.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_ise_spelling_in_squash_message_fails(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nWe " + ISE_WORD + " it.\n"), 1, 1)

    def test_ised_word_fails(self):
        result = self.description("We " + ISE_WORD + "d the texts.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "an -ise spelling: " + ISE_WORD + "d")

    def test_every_ise_stem_fails(self):
        words = [stem + "ise" for stem in ISE_STEMS]
        result = self.description("".join("We " + word + " it.\n\n" for word in words))
        self.assertResult(result, 1, len(words))
        for word in words:
            self.assertReports(result, "an -ise spelling: " + word)

    def test_ise_word_right_after_masked_span_fails(self):
        result = self.description("Run `x`organ" + "ise now.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an -ise spelling")

    def test_empty_description_fails(self):
        result = self.description(" \n\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description: the text is empty")

    def test_blank_description_fails(self):
        for text in ("\u200b\n", "\ufeff\n", "<!-- Describe the change here. -->\n",
                     " <!-- a -->\n\u200b<!-- an unclosed comment\n\nwith prose\n"):
            with self.subTest(text=text):
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description: the text is empty")

    def test_empty_squash_file_fails(self):
        for text in ("", "<!-- a comment -->\n\u200b\n"):
            with self.subTest(text=text):
                result = self.squash(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "squash: the text is empty")

    def test_null_body_fails(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        result = self.run_gate("--event", self.event(None), gate=gate)
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description: the text is empty")

    def test_unclosed_fence_in_description_fails(self):
        result = self.description("Intro.\n\n```\nThe gate " + EM_DASH + " a new check.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:3: " + UNCLOSED.format(3))

    def test_unclosed_fence_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\n```\n" + ROUND_LABEL + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: " + UNCLOSED.format(5))

    def test_backtick_in_fence_info_string_is_not_a_fence(self):
        text = "Intro.\n\n``` a`b\nprose " + EM_DASH + " shown\n```\n"
        result = self.description(text)
        self.assertResult(result, 1, 2)
        self.assertReports(result, "description:4: an em dash, U+2014")
        self.assertReports(result, "description:5: " + UNCLOSED.format(5))

    def test_squash_subject_without_its_number_fails(self):
        result = self.squash("Add the pull request text gate\n\nA body.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, 'squash:1: the subject does not end with " (#999)"')

    def test_squash_subject_with_wrong_number_under_number_option_fails(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        result = self.run_gate("--squash", path, "--number", 998)
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#998)"')

    def test_event_squash_subject_with_wrong_number_fails(self):
        gate = self.tree(squash=CLEAN_SQUASH.replace("(#999)", "(#998)"))
        self.assertResult(self.run_gate("--event", self.event("A body."), gate=gate), 1, 1)

    def test_number_option_binding_passes(self):
        result = self.squash(CLEAN_SQUASH)
        self.assertResult(result, 0, 0)
        self.assertNotIn("pr-text: subject binding not checked", result[1])

    def test_number_comes_from_squash_file_name(self):
        folder = self.tmp / "other" / ".github" / "squash"
        folder.mkdir(parents=True)
        (folder / "998.txt").write_text(CLEAN_SQUASH, encoding="utf-8")
        result = self.run_gate("--squash", folder / "998.txt")
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#998)"')

    def test_squash_names_with_a_leading_zero_are_not_bound(self):
        folder = self.tmp / "other" / ".github" / "squash"
        folder.mkdir(parents=True)
        message = "Add a thing (#5)\n\nBody.\n"
        for name in ("0.txt", "007.txt", "7.txt"):
            (folder / name).write_text(message, encoding="utf-8")
        for name in ("0.txt", "007.txt"):
            with self.subTest(name=name):
                result = self.run_gate("--squash", folder / name)
                self.assertResult(result, 0, 0)
                self.assertIn("pr-text: subject binding not checked", result[1])
        result = self.run_gate("--squash", folder / "7.txt")
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#7)"')

    def test_binding_not_checked_line_is_not_a_defect(self):
        result = self.run_gate("--squash", self.write("message.txt", CLEAN_SQUASH))
        self.assertResult(result, 0, 0)
        self.assertIn("pr-text: subject binding not checked", result[1])


class Exemptions(GateCase):
    """Each exemption and scope limit: honest text inside it passes, and text outside it fails."""

    def test_label_and_width_inside_fence_pass(self):
        fence = "```\n" + ROUND_LABEL + "\n" + "b" * 90 + "\n```\n"
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + fence), 0, 0)
        self.assertResult(self.description("Intro.\n\n" + fence), 0, 0)

    def test_closed_fence_then_clean_prose_passes(self):
        fence = "```\n" + ROUND_LABEL + "\n```\n"
        self.assertResult(self.description("Intro.\n\n" + fence + "\nClean prose after it.\n"),
                          0, 0)
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + fence + "\nClean prose after it.\n"),
                          0, 0)

    def test_dash_after_closed_fence_fails(self):
        fence = "```\ncode\n```\n"
        result = self.description("Intro.\n\n" + fence + "\nThe gate " + EM_DASH + " new.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:7: an em dash, U+2014")

    def test_closer_with_trailing_text_leaves_fence_open(self):
        result = self.description("```\ncode\n``` x\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_shorter_closer_leaves_fence_open(self):
        result = self.description("````\ncode\n```\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_other_character_closer_leaves_fence_open(self):
        result = self.description("```\ncode\n~~~\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_closer_with_trailing_whitespace_closes_fence(self):
        result = self.description("```\ncode\n``` \t\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:4: an em dash, U+2014")

    def test_fence_indented_4_spaces_is_not_a_fence(self):
        result = self.description("Intro.\n\n    ```\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:4: an em dash, U+2014")
        result = self.description("```\ncode\n    ```\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_inline_span_at_line_start_is_not_a_fence(self):
        self.assertResult(self.description("```x`y``` is inline code.\n"), 0, 0)

    def test_label_in_backticks_passes(self):
        self.assertResult(self.description("The lint catches `" + ROUND_LABEL + "`.\n"), 0, 0)

    def test_long_url_line_passes(self):
        line = "See https://example.com/" + "c" * 80
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 0, 0)

    def test_long_line_with_url_before_the_excess_fails(self):
        line = "See https://example.com/ and then " + "d " * 30
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 1, 1)

    def test_url_starting_past_72_characters_fails(self):
        line = "a " * 37 + "https://example.com/x"
        result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: 95 characters, over 72")

    def url_line(self, start):
        """A line whose URL starts at character start, counted from 1, and ends the line."""
        line = "a" * (start - 2) + " https://example.com/x"
        self.assertEqual(line.index("https://") + 1, start)
        return line

    def test_url_starting_at_character_72_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + self.url_line(72) + "\n"), 0, 0)

    def test_url_starting_at_character_73_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + self.url_line(73) + "\n"), 0, 0)

    def test_url_starting_at_character_74_fails(self):
        result = self.squash(CLEAN_SQUASH + "\n" + self.url_line(74) + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: 94 characters, over 72")

    def test_prose_glued_to_url_fails(self):
        line = "(see https://example.com/x)," + ",".join(["and", "then", "words"] * 10)
        result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: {} characters, over 72".format(len(line)))

    def test_url_followed_by_punctuation_past_72_characters_fails(self):
        line = "(See https://example.com/" + "c" * 70 + ")."
        result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: {} characters, over 72".format(len(line)))

    def test_ise_word_inside_url_passes(self):
        text = "See https://example.com/organ" + "ise-the-texts for it.\n"
        self.assertResult(self.description(text), 0, 0)

    def test_label_inside_double_quotes_passes(self):
        self.assertResult(self.description('The lint catches "' + ROUND_LABEL + '".\n'), 0, 0)

    def test_dash_inside_curly_quotes_passes(self):
        text = "He said \u201ca " + EM_DASH + " b\u201d.\n"
        self.assertResult(self.description(text), 0, 0)

    def test_sha256_digest_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe digest:\n" + SHA256 + "\n"), 0, 0)

    def test_41_character_hex_run_passes(self):
        run = "a1" * 20 + "b"
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe run " + run + ".\n"), 0, 0)

    def test_word_of_letters_a_to_f_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe effaced and defaced page.\n"), 0, 0)

    def test_run_of_digits_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nDated 20261113, at 1234567.\n"), 0, 0)

    def test_short_hex_word_with_digit_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe cafe1 host.\n"), 0, 0)

    def test_6_character_hex_word_with_digit_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe c0ffee host.\n"), 0, 0)

    def test_long_description_paragraph_passes(self):
        self.assertResult(self.description("word " * 60 + "\n"), 0, 0)

    def test_revision_id_in_description_passes(self):
        self.assertResult(self.description("Built on e233a7f and " + SHA1 + ".\n"), 0, 0)


class UnreadableInputs(GateCase):
    """Each input the gate cannot read exits 2, never 0, with the defect count last."""

    def assertUnreadable(self, result, fragment):
        self.assertResult(result, 2, 0)
        self.assertTrue(any(line.startswith("unreadable: ") and fragment in line
                            for line in result[1]), result[1])

    def assertUsage(self, result, fragment):
        self.assertResult(result, 2, 0)
        self.assertTrue(result[1][0].startswith("pr-text: " + fragment), result[1])

    def test_missing_payload_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        self.assertUnreadable(self.run_gate("--event", self.tmp / "none.json", gate=gate),
                              "event payload")

    def test_unparseable_payload_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        result = self.run_gate("--event", self.write("event.json", "{not json"), gate=gate)
        self.assertUnreadable(result, "not JSON")

    def test_deeply_nested_payload_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        for text in ("[" * 100000, '{"pull_request": ' + "[" * 100000):
            with self.subTest(start=text[:20]):
                result = self.run_gate("--event", self.write("deep.json", text), gate=gate)
                self.assertUnreadable(result, "not JSON")

    def test_other_event_type_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        payload = self.write("push.json", json.dumps({"ref": "refs/heads/main", "commits": []}))
        self.assertUnreadable(self.run_gate("--event", payload, gate=gate),
                              "not a pull request event")

    def test_payload_without_number_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        payload = self.write("event.json", json.dumps({"pull_request": {"body": "A body."}}))
        self.assertUnreadable(self.run_gate("--event", payload, gate=gate), "number")

    def test_body_that_is_a_number_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        payload = self.write("event.json", json.dumps({"pull_request": {"number": 999,
                                                                        "body": 5}}))
        self.assertUnreadable(self.run_gate("--event", payload, gate=gate),
                              "the pull request body is not text")

    def test_undecodable_text_exits_2(self):
        path = self.tmp / "description.md"
        path.write_bytes(b"A body \xff with a bad byte.\n")
        self.assertUnreadable(self.run_gate("--description", path), "not UTF-8")

    def test_undecodable_squash_file_exits_2(self):
        path = self.tmp / "squash.txt"
        path.write_bytes(CLEAN_SQUASH.encode("utf-8") + b"\xfe\n")
        self.assertUnreadable(self.run_gate("--squash", path, "--number", 999), "not UTF-8")

    def test_missing_text_file_exits_2(self):
        self.assertUnreadable(self.run_gate("--description", self.tmp / "none.md"),
                              "description file")

    def test_missing_squash_file_exits_2(self):
        gate = self.tree(squash=None)
        self.assertUnreadable(self.run_gate("--event", self.event("A body."), gate=gate),
                              "squash file")

    def test_missing_squash_file_in_squash_mode_exits_2(self):
        self.assertUnreadable(self.run_gate("--squash", self.tmp / "none.txt", "--number", 999),
                              "squash file")

    def test_squash_name_over_the_digit_bound_exits_2(self):
        path = self.tmp / "other" / ".github" / "squash" / ("9" * 4301 + ".txt")
        self.assertUnreadable(self.run_gate("--squash", path), "squash file")

    def test_removed_working_directory_exits_2(self):
        folder = self.tmp / "removed"
        code = ("import os, runpy, sys; os.mkdir(sys.argv[1]); os.chdir(sys.argv[1]);"
                " os.rmdir(sys.argv[1]); sys.argv = [sys.argv[2], '--squash', 'x.txt'];"
                " runpy.run_path(sys.argv[0], run_name='__main__')")
        done = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(folder), str(GATE)],
                              cwd=str(self.cwd), capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
        self.assertUnreadable((done.returncode, done.stdout.splitlines()),
                              "the working directory cannot be read")

    def test_unloadable_lint_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        self.assertUnreadable(self.run_gate("--event", self.event("A body."), gate=gate),
                              "label lint")

    def test_lint_that_raises_on_load_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text("raise RuntimeError('x')\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "label lint")

    def test_lint_that_exits_on_load_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text("raise SystemExit(0)\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "label lint")

    def test_scan_of_the_wrong_signature_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text("def scan(x):\n    return []\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "unexpected error: TypeError")

    def test_scan_that_raises_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text(
            "def scan(rel, text):\n    raise ValueError('x')\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "unexpected error: ValueError")

    def test_scan_that_exits_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        # The second scan is a generator, so it exits when the gate reads its hits.
        for lint in ("def scan(rel, text):\n    raise SystemExit(0)\n",
                     "def scan(rel, text):\n    raise SystemExit(0)\n    yield rel\n"):
            with self.subTest(lint=lint):
                (gate.parent / "test-no-qa-labels.py").write_text(lint)
                result = self.run_gate("--description", self.write("d.md", "Hi.\n"), gate=gate)
                self.assertUnreadable(result, "unexpected error: SystemExit")

    def test_error_whose_message_exits_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        error = ("class E(Exception):\n    def __str__(self):\n        raise SystemExit(0)\n\n\n")
        # The first lint raises the error from its scan, the second while it loads.
        for lint, fragment in ((error + "def scan(rel, text):\n    raise E()\n",
                                "unexpected error: E (its message cannot be formatted)"),
                               (error + "raise E()\n",
                                "cannot be loaded: E (its message cannot be formatted)")):
            with self.subTest(lint=lint):
                (gate.parent / "test-no-qa-labels.py").write_text(lint)
                result = self.run_gate("--description", self.write("d.md", "Hi.\n"), gate=gate)
                self.assertUnreadable(result, fragment)

    def test_no_arguments_is_a_usage_error(self):
        result = self.run_gate()
        self.assertResult(result, 2, 0)
        self.assertTrue(result[1][0].startswith("pr-text: no mode given; usage: "), result[1])

    def test_bad_arguments_are_usage_errors(self):
        path = self.write("d.md", "Hi.\n")
        for args in (("--description",), ("--bogus", path), ("--description", path, "--number",
                     "5"), ("--squash", path, "--number", "x"), ("--event", path,
                     "--description", path)):
            with self.subTest(args=args):
                self.assertResult(self.run_gate(*args), 2, 0)

    def test_number_option_with_a_leading_zero_is_a_usage_error(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        self.assertUsage(self.run_gate("--squash", path, "--number", "007"),
                         "--number takes a positive integer")

    def test_number_option_over_the_digit_bound_is_a_usage_error(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        self.assertUsage(self.run_gate("--squash", path, "--number", "9" * 5000),
                         "--number takes at most 18 digits")


class OutputAndHonestTexts(GateCase):
    """Output prefixes, runs from other folders, cost bounds, and honest texts that pass."""

    def assertPrefixed(self, lines):
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(line.startswith(PREFIXES), line)
            self.assertTrue(line.isascii(), line)

    def test_defect_lines_start_with_their_prefix(self):
        text = "::error::" + ROUND_LABEL + "\n::warning::x " + EM_DASH + " y\n"
        gate = self.tree(squash="::error::" + EM_DASH + "\n")
        code, lines = self.run_gate("--event", self.event(text), gate=gate)
        self.assertEqual(code, 1, lines)
        self.assertPrefixed(lines)
        self.assertTrue(any(line.startswith("description:1: ") for line in lines), lines)
        self.assertTrue(any(line.startswith("squash:1: ") for line in lines), lines)

    def test_unreadable_lines_start_with_their_prefix(self):
        payload = self.write("::error::x.json", "::error::not json\n")
        gate = self.tree(squash=CLEAN_SQUASH)
        code, lines = self.run_gate("--event", payload, gate=gate)
        self.assertEqual(code, 2, lines)
        self.assertPrefixed(lines)
        self.assertTrue(lines[0].startswith("unreadable: "), lines)

    def test_carriage_return_and_del_are_escaped(self):
        path = self.write("description.md", "a\r::error::b\x7fc " + EM_DASH + " d\n")
        done = subprocess.run([sys.executable, "-I", "-B", str(GATE), "--description",
                               str(path)], cwd=str(self.cwd), capture_output=True, timeout=120)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertNotIn(b"\r", done.stdout)
        self.assertNotIn(b"\x7f", done.stdout)
        self.assertIn(b"a\\x0d::error::b\\x7fc \\u2014 d", done.stdout)

    def test_event_from_another_working_directory(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        result = self.run_gate("--event", self.event("A clean body."), gate=gate, cwd=self.cwd)
        self.assertResult(result, 0, 0)

    def test_hand_run_on_files_outside_the_tree(self):
        outside = self.tmp / "frozen"
        outside.mkdir()
        body = outside / "body.md"
        body.write_text("A frozen description.\n", encoding="utf-8")
        message = outside / "squash.txt"
        message.write_text(CLEAN_SQUASH, encoding="utf-8")
        self.assertResult(self.run_gate("--description", body, cwd=self.cwd), 0, 0)
        self.assertResult(self.run_gate("--squash", message, "--number", 999, cwd=self.cwd), 0, 0)

    def test_long_backtick_run_is_scanned_in_bounded_time(self):
        path = self.write("description.md", "x " + "`" * BACKTICK_RUN + "\n")
        start = time.monotonic()
        try:
            result = self.run_gate("--description", path, timeout=TIME_BOUND)
        except subprocess.TimeoutExpired:
            self.fail("the gate ran over {} s on {} backticks".format(TIME_BOUND, BACKTICK_RUN))
        self.assertLess(time.monotonic() - start, TIME_BOUND)
        self.assertResult(result, 0, 0)

    def test_workflow_job_has_a_time_limit(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        found = re.findall(r"(?m)^    timeout-minutes: ([0-9]+)$", text)
        self.assertEqual(len(found), 1, "the check job needs 1 timeout-minutes line")
        self.assertTrue(1 <= int(found[0]) <= 30, found)

    def test_clean_event_passes(self):
        body = ("## Summary\n\nAdds a gate, in 3 files, with a range of 12-14 and the word"
                " advise.\r\n\r\n- See `tools/check-pr-text.py`.\n")
        gate = self.tree(squash=CLEAN_SQUASH)
        self.assertResult(self.run_gate("--event", self.event(body), gate=gate), 0, 0)

    def test_one_em_dash_in_an_event_is_one_defect(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        body = "A body " + EM_DASH + " with 1 dash.\n"
        self.assertResult(self.run_gate("--event", self.event(body), gate=gate), 1, 1)


if __name__ == "__main__":
    unittest.main()
