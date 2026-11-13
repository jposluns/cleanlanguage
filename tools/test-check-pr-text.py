#!/usr/bin/env python3
"""Tests for tools/check-pr-text.py, the pull request text gate.

Each case runs the gate as a separate process, as CI and a hand run do, with a temporary folder as
its working directory, and checks its exit status and its output. A case that needs a squash
folder copies the gate and the label lint into a temporary tree, since the gate finds both from
its own path. Every review-history label and every dash a case feeds the gate is built when the
case runs, by joining strings or from an escape, so this file carries none of them as text.

The cases fall in 4 groups: a failing case for each mechanical defect class, which includes a code
fence that is never closed, in a description and in a squash message; a passing case for each
exemption, which includes a closed fence that masks its lines and leaves the prose after it
checked; a case for each kind of unreadable input and for a usage error; and honest texts that
pass. The class of counts stated with their selection rule has no case: it stays a judgement for
reviewers, because no part of it is mechanical.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "check-pr-text.py"
LINT = HERE / "test-no-qa-labels.py"
PREFIXES = ("description", "squash", "unreadable:", "pr-text:")

EM_DASH = "\u2014"
EN_DASH = "\u2013"
# Review-history labels, joined at run time so that this file holds none as text.
ROUND_LABEL = "fixed in rou" + "nd 7"
FIX_LABEL = "a fix" + " round"
ISE_WORD = "standard" + "ise"
SHA1 = "e233a7f0c1d2b3a4e5f60718293a4b5c6d7e8f90"
SHA256 = "a1" * 32
CLEAN_SUBJECT = "Add the pull request text gate (#999)"
CLEAN_SQUASH = CLEAN_SUBJECT + "\n\nAdd a gate that checks the texts of a pull request.\n"
UNCLOSED = "the code fence opened on line {} is never closed"


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

    def run_gate(self, *args, gate=GATE, cwd=None):
        """(exit status, output lines) of the gate run with args."""
        done = subprocess.run([sys.executable, "-I", "-B", str(gate), *map(str, args)],
                              cwd=str(cwd or self.cwd), capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
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

    def test_ise_spelling_fails(self):
        result = self.description("We " + ISE_WORD + " the texts.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_ise_spelling_in_squash_message_fails(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nWe " + ISE_WORD + " it.\n"), 1, 1)

    def test_empty_description_fails(self):
        result = self.description(" \n\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description: the text is empty")

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

    def test_binding_not_checked_line_is_not_a_defect(self):
        result = self.run_gate("--squash", self.write("message.txt", CLEAN_SQUASH))
        self.assertResult(result, 0, 0)
        self.assertIn("pr-text: subject binding not checked", result[1])


class Exemptions(GateCase):
    """Each exemption and scope limit passes honest text."""

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

    def test_label_in_backticks_passes(self):
        self.assertResult(self.description("The lint catches `" + ROUND_LABEL + "`.\n"), 0, 0)

    def test_long_url_line_passes(self):
        line = "See https://example.com/" + "c" * 80
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 0, 0)

    def test_long_line_with_url_before_the_excess_fails(self):
        line = "See https://example.com/ and then " + "d " * 30
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 1, 1)

    def test_label_inside_double_quotes_passes(self):
        self.assertResult(self.description('The lint catches "' + ROUND_LABEL + '".\n'), 0, 0)

    def test_sha256_digest_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe digest:\n" + SHA256 + "\n"), 0, 0)

    def test_word_of_letters_a_to_f_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe effaced and defaced page.\n"), 0, 0)

    def test_run_of_digits_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nDated 20261113, at 1234567.\n"), 0, 0)

    def test_short_hex_word_with_digit_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe cafe1 host.\n"), 0, 0)

    def test_long_description_paragraph_passes(self):
        self.assertResult(self.description("word " * 60 + "\n"), 0, 0)

    def test_revision_id_in_description_passes(self):
        self.assertResult(self.description("Built on e233a7f and " + SHA1 + ".\n"), 0, 0)


class UnreadableInputs(GateCase):
    """Each input the gate cannot read exits 2, never 0."""

    def assertUnreadable(self, result, fragment):
        self.assertResult(result, 2, 0)
        self.assertTrue(any(line.startswith("unreadable: ") and fragment in line
                            for line in result[1]), result[1])

    def test_missing_payload_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        self.assertUnreadable(self.run_gate("--event", self.tmp / "none.json", gate=gate),
                              "event payload")

    def test_unparseable_payload_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        result = self.run_gate("--event", self.write("event.json", "{not json"), gate=gate)
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

    def test_unloadable_lint_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        self.assertUnreadable(self.run_gate("--event", self.event("A body."), gate=gate),
                              "label lint")

    def test_lint_that_raises_on_load_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text("raise RuntimeError('x')\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "label lint")

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


class OutputAndHonestTexts(GateCase):
    """Output prefixes, runs from other folders, and honest texts that pass."""

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
