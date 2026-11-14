#!/usr/bin/env python3
"""Tests for tools/check-pr-text.py, the pull request text gate.

Each case runs the gate as a separate process, as CI and a hand run do, with a temporary folder as
its working directory, and checks its exit status and its output. A case that needs a squash
folder copies the gate and the label lint into a temporary tree, since the gate finds both from
its own path. Every review-history label and every dash a case feeds the gate is built when the
case runs, by joining strings or from an escape, so this file carries none of them as text.

The cases fall in 5 groups: a failing case for each mechanical defect class, which includes a code
fence that is never closed, in a description and in a squash message, and a blank text, in each;
cases at the edges of the exemptions and scope limits, which pass honest text inside an edge and
fail text just outside it, such as the prose after a closed fence, a dash closed up after a URL,
each character that ends a URL, a fence closer the gate does not accept and the digit bound of a
squash file name; a case for each kind of unreadable input, an interrupt raised by the lint among
them, and for a usage error, each of which exits 2 with the defect count as its last line, where
the deeply nested payload runs the gate under a soft stack limit of 1 MiB that the case sets, or
the hard limit when that is lower, so the JSON reader overflows its stack on any runner; output
prefixes and escapes, runs from other folders, a bound on the time of the inline-code scan, the
job's time limit in the workflow, and honest texts that pass; and the mutant sweep, MutantSweep,
the record that each guard it lists has a case that fails without it. Its docstring names the
substitutions it leaves out as equivalent, each with its reason: the line feed removed from either
class of the quote mask, the isinstance test of the payload and the len(parts) guard of the file
name binding. The class of counts stated with their selection rule has no case: it stays a
judgement for reviewers, because no part of it is mechanical.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "check-pr-text.py"
SUITE = HERE / "test-check-pr-text.py"
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
# Each character that ends a URL: whitespace, angle brackets, quote marks, a backtick, a
# parenthesis outside a pair, U+2013, U+2014 and the curly quote marks.
URL_STOPPERS = (" ", "\t", "<", ">", '"', "'", "`", "(", ")", EN_DASH, EM_DASH,
                "\u201c", "\u201d", "\u2018", "\u2019")
ISE_ENDINGS = ("e", "es", "ed", "ing", "er", "ers", "able", "ation", "ations")
# The inline-code scan must finish this many backticks within this many seconds.
BACKTICK_RUN = 20000
TIME_BOUND = 10
# The deep-nesting case runs the gate with this many levels under a soft stack limit of
# DEEP_STACK bytes, or the hard limit when that is lower, so the JSON reader overflows its
# stack, and so reaches the RecursionError branch, whatever stack limit the runner has.
DEEP_LEVELS = 100000
DEEP_STACK = 1024 * 1024
# A child that sets the soft stack limit given as its first argument, never above the hard
# limit, then replaces itself with the gate run with the rest of its arguments.
STACK_LAUNCH = ("import os, resource, sys\n"
                "soft = int(sys.argv[1])\n"
                "hard = resource.getrlimit(resource.RLIMIT_STACK)[1]\n"
                "if hard != resource.RLIM_INFINITY:\n"
                "    soft = min(soft, hard)\n"
                "resource.setrlimit(resource.RLIMIT_STACK, (soft, hard))\n"
                "os.execv(sys.executable, [sys.executable, '-I', '-B', *sys.argv[2:]])\n")


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

    def test_each_ise_ending_fails(self):
        for ending in ISE_ENDINGS:
            word = "organ" + "is" + ending
            with self.subTest(word=word):
                result = self.description("We see " + word + " here.\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: an -ise spelling: " + word)

    def test_ise_spelling_with_a_capital_fails(self):
        word = "Organ" + "ise"
        result = self.description(word + " the texts.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "an -ise spelling: " + word)

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

    def test_number_name_outside_a_squash_folder_is_not_bound(self):
        result = self.run_gate("--squash", self.write("998.txt", CLEAN_SQUASH))
        self.assertResult(result, 0, 0)
        self.assertIn("pr-text: subject binding not checked", result[1])

    def squash_name(self, digits):
        """A real squash file named by digits in a squash folder, whose subject ends (#5)."""
        folder = self.tmp / "other" / ".github" / "squash"
        folder.mkdir(parents=True)
        path = folder / (digits + ".txt")
        path.write_text("Add a thing (#5)\n\nBody.\n", encoding="utf-8")
        return path

    def test_squash_name_of_18_digits_binds_the_subject(self):
        result = self.run_gate("--squash", self.squash_name("9" * 18))
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#' + "9" * 18 + ')"')

    def test_squash_name_of_19_digits_is_not_bound(self):
        result = self.run_gate("--squash", self.squash_name("9" * 19))
        self.assertResult(result, 0, 0)
        self.assertIn("pr-text: subject binding not checked", result[1])

    def test_payload_number_1_is_read(self):
        gate = self.tree(squash="Add a thing (#1)\n\nBody.\n", number=1)
        self.assertResult(self.run_gate("--event", self.event("A body.", number=1), gate=gate),
                          0, 0)


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

    def test_closer_followed_by_a_tab_or_a_space_closes_fence(self):
        for tail in ("\t", " "):
            with self.subTest(tail=tail):
                result = self.description("```\ncode\n```" + tail + "\nprose " + EM_DASH + "\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:4: an em dash, U+2014")

    def test_closer_followed_by_other_whitespace_leaves_fence_open(self):
        for char in ("\x0c", "\x0b", "\x1c", "\xa0", "\x85"):
            with self.subTest(char=hex(ord(char))):
                result = self.description("Intro.\n\n```\ncode\n```" + char + "\n\nAfter.\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:3: " + UNCLOSED.format(3))

    def test_fence_indented_4_spaces_is_not_a_fence(self):
        result = self.description("Intro.\n\n    ```\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:4: an em dash, U+2014")
        result = self.description("```\ncode\n    ```\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_fence_indented_1_to_3_spaces_masks_its_lines(self):
        for indent in (" ", "  ", "   "):
            with self.subTest(indent=len(indent)):
                text = "Intro.\n\n" + indent + "```\nprose " + EM_DASH + "\n" + indent + "```\n"
                self.assertResult(self.description(text), 0, 0)

    def test_run_of_2_backticks_or_tildes_is_not_a_fence(self):
        for run in ("``", "~~"):
            with self.subTest(run=run):
                result = self.description("Intro.\n\n" + run + " a\nprose " + EM_DASH + "\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:4: an em dash, U+2014")

    def test_tilde_fence_masks_its_lines(self):
        fence = "~~~\n" + ROUND_LABEL + "\n" + "b" * 90 + "\n~~~\n"
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + fence), 0, 0)
        self.assertResult(self.description("Intro.\n\n" + fence), 0, 0)

    def test_span_scan_resumes_after_its_closer(self):
        result = self.description("`a``b` " + EM_DASH + " c``\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_span_closes_on_the_nearest_run_of_its_length(self):
        result = self.description("Use `a` here " + EM_DASH + " and `b` there.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

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

    def test_url_ending_in_each_trailing_mark_past_72_characters_fails(self):
        for mark in ".,;:!?":
            with self.subTest(mark=mark):
                line = "See https://example.com/" + "c" * 70 + mark
                result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "squash:5: 95 characters, over 72")

    def test_long_url_with_a_parenthesis_pair_passes(self):
        line = "See https://en.wikipedia.org/wiki/" + "C" * 50 + "_(bar)"
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 0, 0)

    def test_each_url_stopper_ends_the_url(self):
        for stop in URL_STOPPERS:
            with self.subTest(stop=hex(ord(stop))):
                result = self.description("See https://e.com/a" + stop + ISE_WORD + " it.\n")
                self.assertResult(result, 1, 2 if stop in (EN_DASH, EM_DASH) else 1)
                self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_each_url_stopper_ends_a_parenthesis_pair(self):
        for stop in URL_STOPPERS:
            with self.subTest(stop=hex(ord(stop))):
                text = "See https://e.com/(a" + stop + "b)" + ISE_WORD + " it.\n"
                result = self.description(text)
                self.assertResult(result, 1, 2 if stop in (EN_DASH, EM_DASH) else 1)
                self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_dash_after_curly_quoted_url_fails(self):
        text = "He said \u201csee https://x.org/a\u201d " + EM_DASH + " and \u201cb\u201d.\n"
        result = self.description(text)
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_curly_quoted_url_ending_a_long_squash_line_fails(self):
        line = "See \u201chttps://example.org/" + "a" * 70 + "\u201d"
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

    def test_text_between_2_quoted_pairs_is_checked(self):
        for opener, closer in (('"', '"'), ("\u201c", "\u201d")):
            with self.subTest(opener=hex(ord(opener))):
                text = ("He said " + opener + "a" + closer + " " + EM_DASH + " and " + opener
                        + "b" + closer + ".\n")
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: an em dash, U+2014")

    def test_mixed_or_reversed_quote_pair_is_not_masked(self):
        for opener, closer in (("\u201d", "\u201d"), ('"', "\u201d"), ("\u201c", '"')):
            with self.subTest(opener=hex(ord(opener)), closer=hex(ord(closer))):
                text = "He said " + opener + "a " + EM_DASH + " b" + closer + ".\n"
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: an em dash, U+2014")

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
    """Each input the gate cannot read exits 2, never 0, with the defect count last.

    The deeply nested payload runs the gate under a soft stack limit of DEEP_STACK, 1 MiB, or
    the hard limit when that is lower, set in a child that then replaces itself with the gate,
    so the JSON reader overflows its stack and the gate reports it through its RecursionError
    branch whatever stack limit the runner has. With a larger stack the reader can read the
    whole payload and raise a ValueError instead, or parse a balanced one with no error.
    """

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
        # The gate runs under a stack limit this case sets, so the payload overflows on every
        # runner; the message shows that the RecursionError branch, not the ValueError
        # branch, reported it.
        gate = self.tree(squash=CLEAN_SQUASH)
        for text in ("[" * DEEP_LEVELS, '{"pull_request": ' + "[" * DEEP_LEVELS):
            with self.subTest(start=text[:20]):
                path = self.write("deep.json", text)
                done = subprocess.run([sys.executable, "-I", "-B", "-c", STACK_LAUNCH,
                                       str(DEEP_STACK), str(gate), "--event", str(path)],
                                      cwd=str(self.cwd), capture_output=True, text=True,
                                      encoding="utf-8", timeout=120)
                result = done.returncode, done.stdout.splitlines()
                self.assertUnreadable(result, "not JSON")
                self.assertRegex(result[1][0], r"^unreadable: .*: not JSON: "
                                 r"(?i:stack overflow|maximum recursion depth)")

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

    def test_squash_name_too_long_to_open_exits_2(self):
        path = self.tmp / "other" / ".github" / "squash" / ("9" * 4301 + ".txt")
        self.assertUnreadable(self.run_gate("--squash", path), "squash file")

    def test_folder_given_as_text_file_exits_2(self):
        self.assertUnreadable(self.run_gate("--description", self.cwd), "description file")

    def test_unreadable_line_names_its_input(self):
        result = self.run_gate("--description", self.tmp / "none.md")
        self.assertResult(result, 2, 0)
        self.assertTrue(result[1][0].startswith("unreadable: description file "), result[1])

    def test_payload_number_below_1_exits_2(self):
        gate = self.tree(squash="Add a thing (#0)\n\nBody.\n", number=0)
        self.assertUnreadable(self.run_gate("--event", self.event("A body.", number=0), gate=gate),
                              "no positive integer pull request number")

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

    def run_lint(self, lint):
        """The result of the gate on a clean description, with lint as the label lint."""
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text(lint)
        return self.run_gate("--description", self.write("d.md", "Hi.\n"), gate=gate)

    def test_lint_interrupted_while_it_loads_exits_2(self):
        self.assertUnreadable(self.run_lint("raise KeyboardInterrupt\n"),
                              "cannot be loaded: KeyboardInterrupt")

    def test_scan_interrupted_exits_2(self):
        self.assertUnreadable(self.run_lint("def scan(rel, text):\n    raise KeyboardInterrupt\n"),
                              "unexpected error: KeyboardInterrupt")

    def test_error_whose_message_raises_an_interrupt_exits_2(self):
        lint = ("class E(Exception):\n    def __str__(self):\n"
                "        raise KeyboardInterrupt\n\n\ndef scan(rel, text):\n    raise E()\n")
        self.assertUnreadable(self.run_lint(lint),
                              "unexpected error: E (its message cannot be formatted)")

    def test_error_whose_type_name_cannot_be_formatted_exits_2(self):
        lint = ("class S(str):\n    def __str__(self):\n        raise SystemExit(0)\n\n\n"
                "class E(Exception):\n    pass\n\n\nE.__name__ = S('E')\n\n\n"
                "def scan(rel, text):\n    raise E('x')\n")
        self.assertUnreadable(self.run_lint(lint), "unexpected error: an exception: x")

    def test_type_name_of_a_str_subclass_is_described_as_text(self):
        # The name formats as itself, a str subclass whose concatenation exits.
        lint = ("class N(str):\n    def __str__(self):\n        return self\n\n"
                "    def __add__(self, other):\n        raise SystemExit(0)\n\n\n"
                "class E(Exception):\n    pass\n\n\nE.__name__ = N('E')\n\n\n"
                "def scan(rel, text):\n    raise E('x')\n")
        self.assertUnreadable(self.run_lint(lint), "unexpected error: E: x")

    def test_message_of_a_str_subclass_is_described_as_text(self):
        # The message formats as a str subclass whose concatenation from the left exits.
        lint = ("class S(str):\n    def __radd__(self, other):\n        raise SystemExit(0)\n\n\n"
                "class E(Exception):\n    def __str__(self):\n        return S('x')\n\n\n"
                "def scan(rel, text):\n    raise E()\n")
        self.assertUnreadable(self.run_lint(lint), "unexpected error: E: x")

    def test_no_arguments_is_a_usage_error(self):
        result = self.run_gate()
        self.assertResult(result, 2, 0)
        self.assertTrue(result[1][0].startswith("pr-text: no mode given; usage: "), result[1])

    def test_bad_arguments_are_usage_errors(self):
        path = self.write("d.md", "Hi.\n")
        for args, fragment in ((("--description",), "--description needs 1 value"),
                               (("--bogus", path), "unknown argument --bogus"),
                               (("--description", path, "--number", "5"),
                                "--number applies to --squash only"),
                               (("--squash", path, "--number", "x"),
                                "--number takes a positive integer"),
                               (("--event", path, "--description", path), "give exactly 1 of"),
                               (("--number", "5"), "give exactly 1 of")):
            with self.subTest(args=args):
                self.assertUsage(self.run_gate(*args), fragment)

    def test_flag_given_twice_is_a_usage_error(self):
        path = self.write("d.md", "Hi.\n")
        self.assertUsage(self.run_gate("--description", path, "--description", path),
                         "--description needs 1 value and is given once")

    def test_number_option_with_a_leading_zero_is_a_usage_error(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        self.assertUsage(self.run_gate("--squash", path, "--number", "007"),
                         "--number takes a positive integer")

    def test_number_option_over_the_digit_bound_is_a_usage_error(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        self.assertUsage(self.run_gate("--squash", path, "--number", "9" * 5000),
                         "--number takes at most 18 digits")

    def test_number_option_of_18_digits_binds_and_19_is_a_usage_error(self):
        path = self.write("squash.txt", "Add a thing (#" + "9" * 18 + ")\n\nBody.\n")
        self.assertResult(self.run_gate("--squash", path, "--number", "9" * 18), 0, 0)
        self.assertUsage(self.run_gate("--squash", path, "--number", "9" * 19),
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

    def test_reported_line_escapes_each_range_edge(self):
        text = "a " + EM_DASH + " \x1f ~\x7f\xff\u0100\uffff\U00010000 b\n"
        result = self.description(text)
        self.assertResult(result, 1, 1)
        self.assertIn("description:1: an em dash, U+2014: a \\u2014 \\x1f ~\\x7f\\xff\\u0100"
                      "\\uffff\\U00010000 b", result[1])

    def test_squash_file_with_crlf_line_endings_passes(self):
        path = self.tmp / "squash.txt"
        text = CLEAN_SQUASH + "\n```\ncode\n```\n"
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        self.assertResult(self.run_gate("--squash", path, "--number", 999), 0, 0)

    def test_event_body_with_crlf_line_endings_passes(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        body = "Intro.\r\n\r\n```\r\ncode\r\n```\r\n\r\nAfter.\r\n"
        self.assertResult(self.run_gate("--event", self.event(body), gate=gate), 0, 0)

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


D = "DefectClasses."
E = "Exemptions."
U = "UnreadableInputs."
O = "OutputAndHonestTexts."
NL = "\n"
# The 2 character classes of the URL pattern share this text; the second follows "|\(".
URL_CLASS = r"""\s<>\"'`()\u2013\u2014\u201c\u201d\u2018\u2019"""
URL_MEMBERS = (
    ("whitespace", r"\s"), ("the opening angle bracket", "<"),
    ("the closing angle bracket", ">"), ("the straight double quote mark", r"\""),
    ("the straight single quote mark", "'"), ("the backtick", "`"),
    ("the opening parenthesis", "("), ("the closing parenthesis", ")"),
    ("U+2013", r"\u2013"), ("U+2014", r"\u2014"), ("U+201C", r"\u201c"),
    ("U+201D", r"\u201d"), ("U+2018", r"\u2018"), ("U+2019", r"\u2019"),
)
TRAILING_MARKS = (("full stop", "."), ("comma", ","), ("semicolon", ";"), ("colon", ":"),
                  ("exclamation mark", "!"), ("question mark", "?"))
MARKS = "".join(mark for _, mark in TRAILING_MARKS)
LOOKBEHIND = "(?<![" + MARKS + "])"


def row(words, old, new, ids, count=1, target="gate"):
    """1 row of the sweep: (words, target file, old text, new text, count, case ids)."""
    return (words, target, old, new, count, tuple(ids))


SWEEP_ROWS = (
    # The fence pattern: the indent bound, each alternative and the run lengths.
    row("the fence indent bound dropped", "^ {0,3}(", "^(",
        [E + "test_fence_indented_1_to_3_spaces_masks_its_lines"]),
    row("the fence indent bound narrowed to 2 spaces", "^ {0,3}(", "^ {0,2}(",
        [E + "test_fence_indented_1_to_3_spaces_masks_its_lines"]),
    row("the fence indent bound widened to 4 spaces", "^ {0,3}(", "^ {0,4}(",
        [E + "test_fence_indented_4_spaces_is_not_a_fence"]),
    row("the fence indent bound widened to any number of spaces", "^ {0,3}(", "^ *(",
        [E + "test_fence_indented_4_spaces_is_not_a_fence"]),
    row("a backtick fence opened by 2 backticks", "(`{3,}(?=", "(`{2,}(?=",
        [E + "test_run_of_2_backticks_or_tildes_is_not_a_fence"]),
    row("a backtick fence opened only by 4 backticks", "(`{3,}(?=", "(`{4,}(?=",
        [D + "test_unclosed_fence_in_description_fails"]),
    row("a tilde fence opened by 2 tildes", "|~{3,})", "|~{2,})",
        [E + "test_run_of_2_backticks_or_tildes_is_not_a_fence"]),
    row("the tilde alternative of the fence pattern removed", "|~{3,})", ")",
        [E + "test_tilde_fence_masks_its_lines"]),
    row("the backtick alternative of the fence pattern removed", "(`{3,}(?=[^`]*$)|~{3,})",
        "(~{3,})", [E + "test_label_and_width_inside_fence_pass"]),
    row("the lookahead dropped from the backtick fence opener", "(?=[^`]*$)", "",
        [D + "test_backtick_in_fence_info_string_is_not_a_fence"]),
    # The fence closer.
    row("a closer of the other character accepted", "match.group(1)[0] == opener[0]", "True",
        [E + "test_other_character_closer_leaves_fence_open"]),
    row("a shorter closer accepted", "len(match.group(1)) >= len(opener)", "True",
        [E + "test_shorter_closer_leaves_fence_open"]),
    row("a closer of the same length refused", ">= len(opener)", "> len(opener)",
        [E + "test_closed_fence_then_clean_prose_passes"]),
    row("the closer strip widened back to any whitespace", '.strip(" \\t")', ".strip()",
        [E + "test_closer_followed_by_other_whitespace_leaves_fence_open"]),
    row("the closer strip narrowed to spaces", '.strip(" \\t")', '.strip(" ")',
        [E + "test_closer_followed_by_a_tab_or_a_space_closes_fence"]),
    row("the closer strip narrowed to tabs", '.strip(" \\t")', '.strip("\\t")',
        [E + "test_closer_followed_by_a_tab_or_a_space_closes_fence"]),
    row("a closer with trailing text accepted", NL + '                and not line[match.end():]'
        '.strip(" \\t")):', "):", [E + "test_closer_with_trailing_text_leaves_fence_open"]),
    row("the fenced lines dropped from the fenced set", "return inside, (start if",
        "return set(), (start if", [E + "test_label_and_width_inside_fence_pass"]),
    row("the unclosed-fence report made never to apply", "if unclosed is not None:",
        "if False:", [D + "test_unclosed_fence_in_description_fails"]),
    # The inline code spans.
    row("a span that closes on the farthest run of the same length", "later[width] = index",
        "later.setdefault(width, index)",
        [E + "test_span_closes_on_the_nearest_run_of_its_length"]),
    row("the step of the inline-span scan changed", "index = closer[index] + 1", "index += 1",
        [E + "test_span_scan_resumes_after_its_closer"]),
    row("no closer found for any backtick run", "closer[index] = later.get(width)",
        "closer[index] = None", [E + "test_label_in_backticks_passes"]),
    row("the inline-code mask skipped", "line = masked(line, code_spans(line))",
        "line = masked(line, [])", [E + "test_label_in_backticks_passes"]),
    # The URL pattern: the curly marks, the parenthesis pair and the trailing marks.
    row("the curly quote marks removed from both classes of the URL pattern",
        r"\u2014\u201c\u201d\u2018\u2019]", r"\u2014]",
        [E + "test_dash_after_curly_quoted_url_fails",
         E + "test_curly_quoted_url_ending_a_long_squash_line_fails"], count=2),
    row("the parenthesis-pair branch of the URL pattern disabled", "|\\([^", "|(?!)\\([^",
        [E + "test_long_url_with_a_parenthesis_pair_passes"]),
    row("the trailing-mark lookbehind of the URL pattern dropped", 'r"' + LOOKBEHIND + '")',
        'r"")', [E + "test_url_ending_in_each_trailing_mark_past_72_characters_fails"]),
    # The masks.
    row("the mask written with an underscore", 'MASK_CHAR = " "', 'MASK_CHAR = "_"',
        [D + "test_label_right_after_masked_span_fails"]),
    row("the URL mask removed", "MASKS = (URL, QUOTED)", "MASKS = (QUOTED,)",
        [E + "test_ise_word_inside_url_passes"]),
    row("the quote mask removed", "MASKS = (URL, QUOTED)", "MASKS = (URL,)",
        [E + "test_label_inside_double_quotes_passes"]),
    row("the straight-quote alternative of the quote mask removed", r'\"[^\"\n]*\"|', "",
        [E + "test_label_inside_double_quotes_passes"]),
    row("the curly-quote alternative of the quote mask removed", r"|\u201c[^\u201d\n]*\u201d",
        "", [E + "test_dash_inside_curly_quotes_passes"]),
    row("the straight double quote mark removed from its quote-mask class", r'[^\"\n]',
        r"[^\n]", [E + "test_text_between_2_quoted_pairs_is_checked"]),
    row("U+201D removed from its quote-mask class", r"[^\u201d\n]", r"[^\n]",
        [E + "test_text_between_2_quoted_pairs_is_checked"]),
    # The blank test.
    row("the unclosed comment no longer runs to the end", r"(?:-->|\Z)", "-->",
        [D + "test_blank_description_fails"]),
    row("a comment no longer spans lines", '", re.S)', '")',
        [D + "test_blank_description_fails"]),
    row("whitespace removed from the invisible characters", r"[\s\u200b\ufeff]",
        r"[\u200b\ufeff]", [D + "test_empty_description_fails"]),
    row("U+200B removed from the invisible characters", r"[\s\u200b\ufeff]", r"[\s\ufeff]",
        [D + "test_blank_description_fails"]),
    row("U+FEFF removed from the invisible characters", r"[\s\u200b\ufeff]", r"[\s\u200b]",
        [D + "test_blank_description_fails"]),
    row("the blank test reduced to whitespace only",
        'return not INVISIBLE.sub("", COMMENT.sub("", text))', "return not text.strip()",
        [D + "test_blank_description_fails"]),
    row("the empty-text check made never to apply",
        "if blank(text):" + NL + "        report.defect(prefix",
        "if False:" + NL + "        report.defect(prefix", [D + "test_empty_description_fails"]),
    row("the squash check made to go on after a blank text",
        "if blank(text):" + NL + "        return", "if False:" + NL + "        return",
        [D + "test_empty_squash_file_fails"]),
    # The -ise pattern: its flag and each ending; the stems follow the table.
    row("the -ise pattern made case-sensitive", 'r"(?i)\\b(?:"', 'r"\\b(?:"',
        [D + "test_ise_spelling_with_a_capital_fails"]),
    # The label, dash, width and revision checks.
    row("the label scan replaced by an empty list of hits", 'hits = scan(rel, "\\n".join(prose))',
        "hits = []", [D + "test_label_in_description_fails"]),
    row("the em dash removed from the dash check", '("an em dash, U+2014", "\\u2014"),', "",
        [D + "test_em_dash_fails"]),
    row("the en dash removed from the dash check", '("an en dash, U+2013", "\\u2013"),', "",
        [D + "test_en_dash_fails"]),
    row("the width limit raised by 1", "WIDTH = 72", "WIDTH = 73",
        [D + "test_squash_line_over_72_characters_fails"]),
    row("the width limit lowered by 1", "WIDTH = 72", "WIDTH = 71",
        [D + "test_squash_line_of_72_characters_passes"]),
    row("a line of exactly the width limit failed", "if len(line) > WIDTH and not exempt:",
        "if len(line) >= WIDTH and not exempt:", [D + "test_squash_line_of_72_characters_passes"]),
    row("the width check applied to the description", "width_applies = squash",
        "width_applies = True", [E + "test_long_description_paragraph_passes"]),
    row("the revision check applied to the description", "revision_applies = squash",
        "revision_applies = True", [E + "test_revision_id_in_description_passes"]),
    row("the URL-excess width exemption removed",
        "exempt = number - 1 in fence or excess_is_url(line)", "exempt = number - 1 in fence",
        [E + "test_long_url_line_passes"]),
    row("the fenced-code width exemption removed",
        "exempt = number - 1 in fence or excess_is_url(line)", "exempt = excess_is_url(line)",
        [E + "test_label_and_width_inside_fence_pass"]),
    row("the URL start bound moved by 1", "match.start() <= WIDTH", "match.start() < WIDTH",
        [E + "test_url_starting_at_character_73_passes"]),
    row("the URL start bound dropped", "match.start() <= WIDTH and ", "",
        [E + "test_url_starting_past_72_characters_fails"]),
    row("the URL end test made strict", "match.end() >= len(line)", "match.end() > len(line)",
        [E + "test_long_url_line_passes"]),
    row("the URL end test dropped", "match.end() >= len(line)", "True",
        [E + "test_long_line_with_url_before_the_excess_fails"]),
    row("the fenced lines given to the prose checks", '"" if index in fence else mask(line)',
        "mask(line)", [E + "test_label_and_width_inside_fence_pass"]),
    row("the revision check run on the masked lines", "for number, raw in enumerate(lines, 1):",
        "for number, raw in enumerate(prose, 1):",
        [D + "test_revision_id_in_backticks_in_squash_message_fails"]),
    row("the revision upper bound widened to 41", "{7,40}", "{7,41}",
        [E + "test_41_character_hex_run_passes"]),
    row("the revision lower bound lowered to 6", "{7,40}", "{6,40}",
        [E + "test_6_character_hex_word_with_digit_passes"]),
    row("the revision lower bound raised to 8", "{7,40}", "{8,40}",
        [D + "test_revision_id_in_squash_message_fails"]),
    row("the digit lookahead dropped from the revision pattern", "(?=[0-9a-f]*[0-9])", "",
        [E + "test_word_of_letters_a_to_f_passes"]),
    row("the letter lookahead dropped from the revision pattern", "(?=[0-9a-f]*[a-f])", "",
        [E + "test_run_of_digits_passes"]),
    row("the revision pattern made to match nothing", 'REVISION = re.compile(r"\\b',
        'REVISION = re.compile(r"(?!)\\b', [D + "test_revision_id_in_squash_message_fails"]),
    # The subject binding and the digit bound.
    row("the subject suffix check made never to apply", "if not subject.endswith(suffix):",
        "if False:", [D + "test_squash_subject_without_its_number_fails"]),
    row("the binding note skipped when no number is known",
        "if number is None:" + NL + "        report.note",
        "if False:" + NL + "        report.note",
        [D + "test_binding_not_checked_line_is_not_a_defect"]),
    row("the digit bound off by 1 upwards", "if len(digits) > MAX_DIGITS:",
        "if len(digits) > MAX_DIGITS + 1:", [D + "test_squash_name_of_19_digits_is_not_bound",
                                            U + "test_number_option_of_18_digits_binds_and_19_"
                                            "is_a_usage_error"]),
    row("the digit bound off by 1 downwards", "if len(digits) > MAX_DIGITS:",
        "if len(digits) >= MAX_DIGITS:", [D + "test_squash_name_of_18_digits_binds_the_subject"]),
    row("the digit bound made never to apply", "if len(digits) > MAX_DIGITS:", "if False:",
        [U + "test_number_option_over_the_digit_bound_is_a_usage_error",
         U + "test_squash_name_too_long_to_open_exits_2"]),
    row("the digit bound raised to 19", "MAX_DIGITS = 18", "MAX_DIGITS = 19",
        [D + "test_squash_name_of_19_digits_is_not_bound"]),
    row("the digit bound raised to 100", "MAX_DIGITS = 18", "MAX_DIGITS = 100",
        [D + "test_squash_name_of_19_digits_is_not_bound"]),
    row("the digit bound lowered to 17", "MAX_DIGITS = 18", "MAX_DIGITS = 17",
        [D + "test_squash_name_of_18_digits_binds_the_subject"]),
    row("the squash folder test dropped from the file name binding",
        'parts[-3:-1] == (".github", "squash") and ', "",
        [D + "test_number_name_outside_a_squash_folder_is_not_bound"]),
    row("the squash name pattern made to allow a leading zero", r'r"[1-9][0-9]*\.txt"',
        r'r"[0-9]+\.txt"', [D + "test_squash_names_with_a_leading_zero_are_not_bound"]),
    row("the number option ignored in favour of the file name",
        "number = given_number if given_number is not None else number_from_name(path)",
        "number = number_from_name(path)", [D + "test_number_option_binding_passes"]),
    # The readers and the payload.
    row("the CRLF replace in the text reader dropped", 'return text.replace("\\r\\n", "\\n")',
        "return text", [O + "test_squash_file_with_crlf_line_endings_passes"]),
    row("the CRLF replace in the payload reader dropped",
        'return number, body.replace("\\r\\n", "\\n")', "return number, body",
        [O + "test_event_body_with_crlf_line_endings_passes"]),
    row("UTF-8 decoded with replacement", '"utf-8", "strict"', '"utf-8", "replace"',
        [U + "test_undecodable_text_exits_2"]),
    row("the decode handler narrowed to an exception that never occurs",
        "except UnicodeDecodeError as error:", "except ImportError as error:",
        [U + "test_undecodable_text_exits_2"]),
    row("the file read handler narrowed to a missing file",
        "    except OSError as error:" + NL + '        raise Unreadable("{} {}: {}"',
        "    except FileNotFoundError as error:" + NL + '        raise Unreadable("{} {}: {}"',
        [U + "test_folder_given_as_text_file_exits_2"]),
    row("a missing file read as empty",
        'raise Unreadable("{} {}: {}".format(what, path, error.strerror or error)) from error',
        'return ""', [U + "test_missing_squash_file_exits_2"]),
    row("ValueError dropped from the JSON catch", "except (ValueError, RecursionError) as error:",
        "except (RecursionError,) as error:", [U + "test_unparseable_payload_exits_2"]),
    row("RecursionError dropped from the JSON catch",
        "except (ValueError, RecursionError) as error:", "except (ValueError,) as error:",
        [U + "test_deeply_nested_payload_exits_2"]),
    row("a payload with no pull request read as the pull request itself",
        'pull = event.get("pull_request") if', "pull = event if",
        [U + "test_other_event_type_exits_2"]),
    row("the pull request test made never to apply", "if not isinstance(pull, dict):",
        "if False:", [U + "test_other_event_type_exits_2"]),
    row("the integer type test of the number dropped", "type(number) is not int or ", "",
        [U + "test_payload_without_number_exits_2"]),
    row("the number bound lowered so a payload number of 0 passes", "number < 1", "number < 0",
        [U + "test_payload_number_below_1_exits_2"]),
    row("the number bound raised so a payload number of 1 fails", "number < 1", "number <= 1",
        [D + "test_payload_number_1_is_read"]),
    row("a null body no longer read as empty", "if body is None:", "if False:",
        [D + "test_null_body_fails"]),
    row("the body-not-text check made never to apply", "if not isinstance(body, str):",
        "if False:", [U + "test_body_that_is_a_number_exits_2"]),
    row("the handler for an unreadable working directory narrowed to one that never occurs",
        "    except OSError as error:" + NL + '        raise Unreadable("squash file {}: the',
        "    except ZeroDivisionError as error:" + NL
        + '        raise Unreadable("squash file {}: the',
        [U + "test_removed_working_directory_exits_2"]),
    # The lint and the error descriptions.
    row("the lint found from the working directory",
        'LINT = ROOT / "tools" / "test-no-qa-labels.py"',
        'LINT = Path("tools") / "test-no-qa-labels.py"',
        [O + "test_event_from_another_working_directory"]),
    row("the squash folder taken from the working directory",
        'SQUASH_DIR = ROOT / ".github" / "squash"', 'SQUASH_DIR = Path(".github") / "squash"',
        [O + "test_event_from_another_working_directory"]),
    row("Exception caught, not BaseException, when the lint loads",
        "    except BaseException as error:" + NL + "        raise Unreadable(LINT_FAILURE",
        "    except Exception as error:" + NL + "        raise Unreadable(LINT_FAILURE",
        [U + "test_lint_that_exits_on_load_exits_2"]),
    row("an unloadable lint read as a scan with no hits",
        "raise Unreadable(LINT_FAILURE.format(LINT, describe(error))) from error",
        "return lambda rel, text: []", [U + "test_unloadable_lint_exits_2"]),
    row("the message of an error raised while the lint loads formatted directly",
        "LINT_FAILURE.format(LINT, describe(error))", "LINT_FAILURE.format(LINT, error)",
        [U + "test_error_whose_message_exits_exits_2"]),
    row("str.__str__ dropped where the type name is described",
        "name = str.__str__(str(type(error).__name__))", "name = str(type(error).__name__)",
        [U + "test_type_name_of_a_str_subclass_is_described_as_text"]),
    row("str.__str__ dropped where an error is described", "text = str.__str__(str(error))",
        "text = str(error)", [U + "test_message_of_a_str_subclass_is_described_as_text"]),
    row("the handler that names an error type narrowed to Exception",
        "    except BaseException:" + NL + "        name = ",
        "    except Exception:" + NL + "        name = ",
        [U + "test_error_whose_type_name_cannot_be_formatted_exits_2"]),
    row("the handler that formats a message narrowed to Exception",
        "    except BaseException:" + NL + "        return name",
        "    except Exception:" + NL + "        return name",
        [U + "test_error_whose_message_exits_exits_2"]),
    row("a KeyboardInterrupt re-raise restored where a message is formatted",
        "text = str.__str__(str(error))" + NL + "    except BaseException:",
        "text = str.__str__(str(error))" + NL + "    except KeyboardInterrupt:" + NL
        + "        raise" + NL + "    except BaseException:",
        [U + "test_error_whose_message_raises_an_interrupt_exits_2"]),
    row("a KeyboardInterrupt re-raise restored where the lint loads",
        "scan = module.scan" + NL + "    except BaseException",
        "scan = module.scan" + NL + "    except KeyboardInterrupt:" + NL + "        raise" + NL
        + "    except BaseException", [U + "test_lint_interrupted_while_it_loads_exits_2"]),
    row("a KeyboardInterrupt re-raise restored in main()",
        "status = EXIT_UNREADABLE" + NL + "    except BaseException",
        "status = EXIT_UNREADABLE" + NL + "    except KeyboardInterrupt:" + NL + "        raise"
        + NL + "    except BaseException", [U + "test_scan_interrupted_exits_2"]),
    row("Exception caught, not BaseException, in main()",
        "    except BaseException as error:" + NL + "        # A scan",
        "    except Exception as error:" + NL + "        # A scan",
        [U + "test_scan_that_exits_exits_2"]),
    row("the catch-all handler of main() narrowed to one that never occurs",
        "    except BaseException as error:" + NL + "        # A scan",
        "    except ZeroDivisionError as error:" + NL + "        # A scan",
        [U + "test_scan_that_raises_exits_2"]),
    row("the message of an error caught in main() formatted directly",
        "describe(error)))" + NL + "        status", "error))" + NL + "        status",
        [U + "test_error_whose_message_exits_exits_2"]),
    # The arguments and the exits.
    row("the no-argument guard of parse() dropped", "if not argv:", "if False:",
        [U + "test_no_arguments_is_a_usage_error"]),
    row("the unknown-argument guard of parse() dropped",
        'if flag not in ("--event", "--description", "--squash", "--number"):', "if False:",
        [U + "test_bad_arguments_are_usage_errors"]),
    row("the duplicate-flag test dropped", "if flag in options or not rest:", "if not rest:",
        [U + "test_flag_given_twice_is_a_usage_error"]),
    row("the missing-value test dropped", "if flag in options or not rest:",
        "if flag in options:", [U + "test_bad_arguments_are_usage_errors"]),
    row("the mode count test made to allow no mode", "if len(modes) != 1:",
        "if len(modes) > 1:", [U + "test_bad_arguments_are_usage_errors"]),
    row("the mode count test made to allow 2 modes", "if len(modes) != 1:",
        "if len(modes) < 1:", [U + "test_bad_arguments_are_usage_errors"]),
    row("the number option allowed with every mode", 'if modes[0] != "--squash":', "if False:",
        [U + "test_bad_arguments_are_usage_errors"]),
    row("the number option made to allow a leading zero", 'r"[1-9][0-9]*", options',
        'r"[0-9]+", options', [U + "test_number_option_with_a_leading_zero_is_a_usage_error"]),
    row("the number option bound made never to apply",
        "if number is None:" + NL + "            raise Usage",
        "if False:" + NL + "            raise Usage",
        [U + "test_number_option_over_the_digit_bound_is_a_usage_error"]),
    row("the usage handler of main() narrowed to one that never occurs",
        "except Usage as error:", "except ZeroDivisionError as error:",
        [U + "test_no_arguments_is_a_usage_error"]),
    row("the unreadable handler of main() narrowed to one that never occurs",
        "except Unreadable as error:", "except ZeroDivisionError as error:",
        [U + "test_unreadable_line_names_its_input"]),
    row("unreadable input given exit 0", "EXIT_UNREADABLE = 2", "EXIT_UNREADABLE = 0",
        [U + "test_missing_payload_exits_2"]),
    row("a usage error given exit 0", "EXIT_USAGE = 2", "EXIT_USAGE = 0",
        [U + "test_no_arguments_is_a_usage_error"]),
    row("a defect given exit 0", "status = EXIT_DEFECT if report.count else 0", "status = 0",
        [D + "test_em_dash_fails"]),
    row("the count line dropped",
        '    report.note("pr-text:", " {} defect(s)".format(report.count))' + NL, "",
        [D + "test_em_dash_fails"]),
    # The output.
    row("report lines printed without their prefix", "print(prefix + ascii_text(detail))",
        "print(ascii_text(detail))", [O + "test_defect_lines_start_with_their_prefix"]),
    row("report lines printed without escapes", "print(prefix + ascii_text(detail))",
        "print(prefix + detail)", [O + "test_carriage_return_and_del_are_escaped"]),
    row("the space escaped", "if 0x20 <= code < 0x7f:", "if 0x20 < code < 0x7f:",
        [O + "test_reported_line_escapes_each_range_edge"]),
    row("the tilde escaped", "if 0x20 <= code < 0x7f:", "if 0x20 <= code < 0x7e:",
        [O + "test_reported_line_escapes_each_range_edge"]),
    row("DEL printed raw", "if 0x20 <= code < 0x7f:", "if 0x20 <= code <= 0x7f:",
        [O + "test_carriage_return_and_del_are_escaped"]),
    row("U+0100 written as a 2-digit escape", "elif code < 0x100:", "elif code <= 0x100:",
        [O + "test_reported_line_escapes_each_range_edge"]),
    row("U+00FF written as a 4-digit escape", "elif code < 0x100:", "elif code < 0xff:",
        [O + "test_reported_line_escapes_each_range_edge"]),
    row("U+10000 written as a 4-digit escape", "elif code < 0x10000:", "elif code <= 0x10000:",
        [O + "test_reported_line_escapes_each_range_edge"]),
    row("U+FFFF written as an 8-digit escape", "elif code < 0x10000:", "elif code < 0xffff:",
        [O + "test_reported_line_escapes_each_range_edge"]),
    # The workflow.
    row("the job's time limit removed from the workflow", "    timeout-minutes: 10" + NL, "",
        [O + "test_workflow_job_has_a_time_limit"], target="workflow"),
) + tuple(
    row("{} removed from the first class of the URL pattern".format(name),
        "(?:[^" + URL_CLASS + "]", "(?:[^" + URL_CLASS.replace(member, "", 1) + "]",
        [E + "test_each_url_stopper_ends_the_url"])
    for name, member in URL_MEMBERS
) + tuple(
    row("{} removed from the parenthesis-pair class of the URL pattern".format(name),
        "|\\([^" + URL_CLASS + "]", "|\\([^" + URL_CLASS.replace(member, "", 1) + "]",
        [E + "test_each_url_stopper_ends_a_parenthesis_pair"])
    for name, member in URL_MEMBERS
) + tuple(
    row("the {} removed from the trailing-mark lookbehind".format(name), LOOKBEHIND,
        "(?<![" + MARKS.replace(mark, "") + "])",
        [E + "test_url_ending_in_each_trailing_mark_past_72_characters_fails"])
    for name, mark in TRAILING_MARKS
) + tuple(
    row("the ending -{} removed from the -ise pattern".format(ending), "|".join(ISE_ENDINGS),
        "|".join(other for other in ISE_ENDINGS if other != ending),
        [D + "test_each_ise_ending_fails"])
    for ending in ISE_ENDINGS
) + tuple(
    row("the stem {} removed from the -ise denylist".format(stem), '"{}",'.format(stem), "",
        [D + "test_every_ise_stem_fails"])
    for stem in ISE_STEMS
)
SWEEP_TARGETS = {"gate": Path("tools") / "check-pr-text.py",
                 "workflow": Path(".github") / "workflows" / "pr-text.yml"}
SWEEP_WORKERS = 4
SWEEP_TIMEOUT = 300


class MutantSweep(unittest.TestCase):
    """The recorded mutant sweep: each guard it lists has a case that fails without it.

    Each row of SWEEP_ROWS names a guard of the gate, or of the workflow, in words, with the
    exact text to replace, its replacement, the number of times the text must occur and the
    cases that must fail once it is replaced. For each row the sweep copies the gate, this
    suite, the label lint and the workflow into a fresh temporary tree, checks that the text
    occurs exactly that many times, so that a row that no longer applies fails, applies the
    replacement and runs the named cases there in a separate process; the row passes only when
    that run exits 1 with FAILED. The named cases also run, and pass, on an unmutated copy. No
    row names a case of this class, so the sweep cannot run itself.

    These substitutions are left out of the table as equivalent, each with its reason:
    - the line feed removed from either class of the quote mask: the mask reads 1 line, which
      holds no line feed, so the class never meets one;
    - the isinstance test of the payload dropped: a payload that is JSON but not an object
      then raises AttributeError, which the catch-all handler reports with exit 2, an
      unreadable line and the count line, so only the reason in that line differs;
    - the len(parts) guard of the file name binding dropped: a path of fewer than 3 parts
      cannot have .github and squash as the 2 parts before its last, so the test after the
      guard gives the same answer.
    """

    def copy_tree(self, root):
        """Copy the gate, this suite, the lint and the workflow into root."""
        for source, target in ((GATE, SWEEP_TARGETS["gate"]), (SUITE, Path("tools") / SUITE.name),
                               (LINT, Path("tools") / LINT.name),
                               (WORKFLOW, SWEEP_TARGETS["workflow"])):
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, root / target)

    def run_cases(self, root, ids):
        """(exit status, last line of the report) of the named cases run in root."""
        try:
            done = subprocess.run([sys.executable, "-I", "-B",
                                   str(root / "tools" / SUITE.name), *ids],
                                  cwd=str(root), capture_output=True, text=True,
                                  encoding="utf-8", timeout=SWEEP_TIMEOUT)
        except subprocess.TimeoutExpired:
            return None, "timed out after {} s".format(SWEEP_TIMEOUT)
        lines = done.stderr.strip().splitlines()
        return done.returncode, lines[-1] if lines else ""

    def mutate(self, sweep_row):
        """None when the row is killed, or the reason it is not."""
        words, target, old, new, count, ids = sweep_row
        missing = [case for case in ids
                   if not hasattr(globals().get(case.partition(".")[0]), case.partition(".")[2])]
        if missing:
            return "names a case that does not exist: " + ", ".join(missing)
        root = Path(tempfile.mkdtemp())
        try:
            self.copy_tree(root)
            path = root / SWEEP_TARGETS[target]
            text = path.read_text(encoding="utf-8")
            found = text.count(old)
            if found != count:
                return "the text occurs {} times, not {}".format(found, count)
            path.write_text(text.replace(old, new), encoding="utf-8")
            code, last = self.run_cases(root, ids)
            if code == 1 and last.startswith("FAILED"):
                return None
            return "survived: exit {}, {}".format(code, last)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rows_are_well_formed(self):
        names = [sweep_row[0] for sweep_row in SWEEP_ROWS]
        self.assertEqual(len(names), len(set(names)), "each row needs its own name")
        for words, target, old, new, count, ids in SWEEP_ROWS:
            with self.subTest(row=words):
                self.assertIn(target, SWEEP_TARGETS)
                self.assertNotEqual(old, new)
                self.assertGreaterEqual(count, 1)
                self.assertTrue(ids)
                for case in ids:
                    class_name, _, method = case.partition(".")
                    self.assertNotEqual(class_name, type(self).__name__, "the sweep would recurse")
                    self.assertTrue(hasattr(globals().get(class_name), method), case)

    def test_named_cases_pass_unmutated(self):
        ids = sorted({case for sweep_row in SWEEP_ROWS for case in sweep_row[5]})
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        self.copy_tree(root)
        code, last = self.run_cases(root, ids)
        self.assertEqual((code, last), (0, "OK"))

    def test_each_row_is_killed(self):
        with ThreadPoolExecutor(max_workers=SWEEP_WORKERS) as pool:
            results = list(pool.map(self.mutate, SWEEP_ROWS))
        for sweep_row, reason in zip(SWEEP_ROWS, results):
            with self.subTest(row=sweep_row[0]):
                self.assertIsNone(reason, sweep_row[0])


if __name__ == "__main__":
    unittest.main()
