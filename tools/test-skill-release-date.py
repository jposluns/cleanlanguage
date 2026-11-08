#!/usr/bin/env python3
"""Tests for tools/skill-release-date.py, the strict Released-line extractor.

Item 26 adds a ``Released: YYYY-MM-DD`` meta line directly after the
``Version:`` line of the skill and its portable renderings. Every gate reads it
through one extractor, so these tests pin that extractor grammar: the first
line carrying the key is authoritative, the value is a real calendar date, the
line sits directly after the first ``Version:`` line, a duplicate is rejected
(also behind Markdown markers or invisible format characters), absence (exit
3) is distinct from malformed (exit 1), and an internal error of the extractor
has its own exit (6), distinct from an unreadable input (4). They also pin the one
function that interprets a release ``published_at`` value, (T2) that the
portable-text builder carries the line into the generated rendering, and (row
80) the ``--json`` mode the live checksum gate runs as a separate child: its
exact replies, its bad requests (exit 2), its internal error (exit 6), and its
agreement with the functions and the other modes, including (row 89) the ops
parse_date, publish_window and confirm_published and the refused outcome that
the shell callers reach through tools/skill-release-date-client.py.

The tests run offline and touch only throwaway directories.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXTRACTOR = REPO / "tools" / "skill-release-date.py"
SKILL = REPO / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"

spec = importlib.util.spec_from_file_location("skill_release_date", EXTRACTOR)
srd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srd)

HEAD = "# Clean Language\n\n"
VERSION = "Version: 1.0.15  \n"
RELEASED = "Released: 2026-11-15  \n"
TAIL = "Author: Jeff Posluns  \nLicence: CC BY-SA 4.0\n\nBody text.\n"
VALID = HEAD + VERSION + RELEASED + TAIL

# R8: stale copies of the key that the duplicate rule must still see.
DECORATED = (
    ("bold", "**Released:** 2026-11-01"),
    ("bold key", "**Released**: 2026-11-01"),
    ("underscore emphasis", "__Released:__ 2026-11-01"),
    ("dash bullet", "- Released: 2026-11-01"),
    ("star bullet", "* Released: 2026-11-01"),
    ("plus bullet", "+ Released: 2026-11-01"),
    ("ordered list", "1. Released: 2026-11-01"),
    ("ordered list with a parenthesis", "2) Released: 2026-11-01"),
    ("block quote", "> Released: 2026-11-01"),
    ("quoted bold bullet", "> - **Released:** 2026-11-01"),
    ("heading", "## Released: 2026-11-01"),
    ("tab", "\tReleased: 2026-11-01"),
    ("no-break space", "\u00a0Released: 2026-11-01"),
    ("zero-width space", "\u200bReleased: 2026-11-01"),
    ("byte order mark", "\ufeffReleased: 2026-11-01"),
    ("word joiner", "\u2060Released: 2026-11-01"),
    ("bidirectional control", "\u202aReleased: 2026-11-01"),
    ("soft hyphen inside the key", "Rele\u00adased: 2026-11-01"),
    # U4: a table row, a bracket, and the full-width colon.
    ("table row", "| Released: 2026-11-01 |"),
    ("bold table cell", "| **Released:** 2026-11-01 |"),
    ("second table cell", "| | Released: 2026-11-01 |"),
    ("bracket", "[Released: 2026-11-01]"),
    ("full-width colon", "Released\uff1a 2026-11-01"),
    ("table row with a full-width colon", "| Released\uff1a2026-11-01 |"),
    # Fix round 12 (VERIFY round 9.1, finding 1): emphasis markers and
    # blanks after the word, a leading form feed or ideographic space, and a
    # list number of 0.
    ("underscore emphasis after the key", "__Released__: 2026-11-01"),
    ("space before the colon", "Released : 2026-11-01"),
    ("tab before the colon", "Released\t: 2026-11-01"),
    ("form feed", "\x0cReleased: 2026-11-01"),
    ("ideographic space", "\u3000Released: 2026-11-01"),
    ("ordered list from zero", "0. Released: 2026-11-01"),
)

# Fix round 12 (VERIFY round 9.1, finding 1): every character the leading
# \s of the key pattern matches, other than the newline that ends a line.
LEADING_WHITESPACE = (
    "\t", "\x0b", "\x0c", "\r", "\x1c", "\x1d", "\x1e", "\x1f", " ", "\x85", "\xa0", "\u1680",
    "\u2000", "\u2001", "\u2002", "\u2003", "\u2004", "\u2005", "\u2006", "\u2007", "\u2008", "\u2009",
    "\u200a", "\u2028", "\u2029", "\u202f", "\u205f", "\u3000",
)

# Decorations outside the rule, which the docstring states are not detected.
# Fix round 11 (DISCOVERY round 9, finding 1): a list marker with no number,
# a list number of another script's digits, and a no-break space before the
# colon are outside it too, as the key pattern takes only ASCII digits and
# only spaces, tabs and emphasis markers between the word and the colon.
UNDETECTED = (
    ("inline code", "`Released: 2026-11-01`"),
    ("HTML tag", "<b>Released:</b> 2026-11-01"),
    ("a parenthesis with no number", ") Released: 2026-11-01"),
    ("a dot with no number", ". Released: 2026-11-01"),
    ("a list number of non-ASCII digits", "\u0661. Released: 2026-11-01"),
    ("a no-break space before the colon", "Released\u00a0: 2026-11-01"),
    # Fix round 12 (VERIFY round 9.1, class sweep): a colon other than the
    # two the rule names, and an angle bracket before the word.
    ("a small colon", "Released\ufe55 2026-11-01"),
    ("an angle bracket", "<Released: 2026-11-01"),
)

# Runs the real extractor as a script with its input decoding made to crash,
# to observe the exit code of an internal error.
CRASH_RUNNER = (
    "import io, runpy, sys\n"
    "def crash(*args, **kwargs):\n"
    "    raise RuntimeError(\"injected internal error\")\n"
    "io.TextIOWrapper = crash\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name=\"__main__\")\n"
)

# Row 80: runs the real extractor in --json mode with the function named by
# its first argument (a dotted module.attribute) made to raise the built-in
# exception named by its second argument, and the request on stdin, to
# observe the exit code and the empty stdout of an internal error. Arguments
# after the extractor's path replace --json, so a CLI mode can be compared
# with --json. The message names the Python function that made the failing
# call, so a test can tell where the exception rose. _strptime is imported
# before the patch because its import calls time.strftime, so a patched
# time.strftime is reached only where the extractor formats an instant.
JSON_CRASH_RUNNER = (
    "import _strptime, builtins, importlib, runpy, sys\n"
    "kind = getattr(builtins, sys.argv[2])\n"
    "def crash(*args, **kwargs):\n"
    "    raise kind(f\"injected internal error in {sys._getframe(1).f_code.co_name}\")\n"
    "module, name = sys.argv[1].rsplit(\".\", 1)\n"
    "setattr(importlib.import_module(module), name, crash)\n"
    "sys.argv = [sys.argv[3], *(sys.argv[4:] or [\"--json\"])]\n"
    "runpy.run_path(sys.argv[0], run_name=\"__main__\")\n"
)

# Runs the real extractor the way an interpreter without the integer digit
# limit runs it (Python 3.9 before 3.9.14, 3.10 before 3.10.7): int()
# converts a digit run of any length, and sys has neither
# get_int_max_str_digits nor set_int_max_str_digits. Arguments after the
# extractor's path are its own.
NO_LIMIT_RUNNER = (
    "import runpy, sys\n"
    "if hasattr(sys, \"set_int_max_str_digits\"):\n"
    "    sys.set_int_max_str_digits(0)\n"
    "    del sys.get_int_max_str_digits, sys.set_int_max_str_digits\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name=\"__main__\")\n"
)

# Row 80: the exact usage line of the extractor, --json included.
USAGE_LINE = (
    "skill-release-date: usage: skill-release-date [FILE|-] | --baseline | --requires-date VERSION"
    " | --check-date YYYY-MM-DD | --published-day PUBLISHED_AT"
    " | --publish-window YYYY-MM-DD NOW | --confirm-published YYYY-MM-DD PUBLISHED_AT | --json\n"
)


def request(op: str, arg: str | None = None, **fields) -> bytes:
    """Encode a --json request, as the gate does; ``fields`` are the named
    keys of a two-value request."""
    body = {"op": op} if arg is None else {"op": op, "arg": arg}
    body.update(fields)
    return json.dumps(body, ensure_ascii=True).encode("ascii")


def raw_request(op: str, arg: str) -> bytes:
    """Encode a --json request as raw UTF-8 JSON, with no escapes for the
    characters outside ASCII."""
    return json.dumps({"op": op, "arg": arg}, ensure_ascii=False).encode("utf-8")


def parse_error(data: bytes) -> str:
    """The text of the error the standard library raises for a request that
    is not a UTF-8 JSON value."""
    try:
        json.loads(data.decode("utf-8"))
    except ValueError as error:
        return str(error)
    raise AssertionError(f"the request parses: {data[:40]!r}")


def reply_bytes(reply: dict) -> str:
    """The exact stdout of a delivered reply."""
    return json.dumps(reply, ensure_ascii=True, sort_keys=True) + "\n"


def run(data: bytes | None = None, *args: str, stdin: bool = False):
    """Run the extractor CLI. With ``data`` and no ``stdin``, write it to a file
    and pass the path; with ``stdin``, pipe it in. Returns (code, out, err)."""
    cmd = [sys.executable, "-I", str(EXTRACTOR), *args]
    if data is None:
        proc = subprocess.run(cmd, capture_output=True)
    elif stdin:
        proc = subprocess.run(cmd, input=data, capture_output=True)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_bytes(data)
            proc = subprocess.run([*cmd, str(path)], capture_output=True)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


class ExtractorCliTest(unittest.TestCase):
    def assertAccepts(self, text: str | bytes, expected: str = "2026-11-15", stdin: bool = False):
        data = text.encode("utf-8") if isinstance(text, str) else text
        code, out, err = run(data, stdin=stdin)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, expected + "\n")

    def assertRejects(self, text: str | bytes, fragment: str, code_expected: int = 1):
        data = text.encode("utf-8") if isinstance(text, str) else text
        code, out, err = run(data)
        self.assertEqual(code, code_expected, f"out={out!r} err={err!r}")
        self.assertEqual(out, "")
        self.assertIn(fragment, err)

    def test_valid_line_is_read(self):
        self.assertAccepts(VALID)

    def test_valid_line_is_read_from_stdin(self):
        self.assertAccepts(VALID, stdin=True)

    def test_no_trailing_spaces_is_read(self):
        # The hand-maintained renderings carry no Markdown hard break.
        self.assertAccepts(HEAD + "Version: 1.0.15\nReleased: 2026-11-15\n" + TAIL)

    def test_a_dash_reads_stdin(self):
        # Fix round 11 (DISCOVERY round 9, finding 5): "-" names standard
        # input, as the module docstring states, never a usage error.
        self.assertEqual(run(VALID.encode("utf-8"), "-", stdin=True), (0, "2026-11-15\n", ""))
        self.assertEqual(
            run((HEAD + VERSION + TAIL).encode("utf-8"), "-", stdin=True),
            (3, "", "skill-release-date: no Released: line found\n"),
        )

    def test_the_input_is_read_as_given_never_stripped(self):
        # Fix round 12 (VERIFY round 9.1, class sweep): a file and stdin are
        # read whole and decoded as Path.read_text(encoding="utf-8") reads
        # them, never stripped and with no byte order mark removed, so a
        # blank line before the content keeps the line numbers, a form feed
        # at the very end stays in the last line, and a byte order mark
        # before the Version line keeps it from being one.
        last = "Released: 2026-11-15\x0c"
        for label, text, expected in (
            ("a blank first line", "\n" + VALID + "Released: 2026-11-16\n",
             "more than one Released line (lines 5, 10)"),
            ("a form feed at the end", HEAD + VERSION + last,
             f"the first Released line is not a bare YYYY-MM-DD date: {last!r}"),
            ("a byte order mark before the Version line", "\ufeffVersion: 1.0.15\nReleased: 2026-11-15\n",
             "a Released line is present but there is no Version: line"),
        ):
            for stdin in (False, True):
                with self.subTest(label, stdin=stdin):
                    self.assertEqual(
                        run(text.encode("utf-8"), stdin=stdin), (1, "", f"skill-release-date: {expected}\n")
                    )

    def test_an_argument_with_one_leading_dash_is_a_file(self):
        # Fix round 12 (VERIFY round 9.1, mutant X23): only an argument that
        # starts with "--" is an option, so any other argument, one that
        # starts with a single "-" included, names a file.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "-SKILL.md").write_text(VALID, encoding="utf-8")
            proc = subprocess.run([sys.executable, "-I", str(EXTRACTOR), "-SKILL.md"], cwd=tmp, capture_output=True)
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"2026-11-15\n", b""))
            proc = subprocess.run([sys.executable, "-I", str(EXTRACTOR), "-x"], cwd=tmp, capture_output=True)
        self.assertEqual((proc.returncode, proc.stdout), (4, b""), proc.stderr)
        self.assertTrue(proc.stderr.startswith(b"skill-release-date: could not read -x: "), proc.stderr)

    def test_absent_line_exits_3(self):
        self.assertRejects(HEAD + VERSION + TAIL, "no Released: line found", 3)

    def test_real_skill_at_or_below_baseline_reads_absent_or_valid(self):
        # The real SKILL.md is either the undated baseline (exit 3) or a dated
        # later version (exit 0); it is never malformed.
        code, _out, err = run(SKILL.read_bytes())
        self.assertIn(code, (0, 3), err)

    def test_malformed_first_line_is_not_skipped(self):
        text = HEAD + VERSION + "Released: soon\n" + TAIL + "Released: 2026-11-15\n"
        self.assertRejects(text, "first Released line is not a bare YYYY-MM-DD")

    def test_impossible_calendar_date_is_rejected(self):
        self.assertRejects(HEAD + VERSION + "Released: 2026-02-30\n" + TAIL, "not a real calendar date")

    def test_line_not_directly_after_version_is_rejected(self):
        text = HEAD + VERSION + "Author: Jeff Posluns  \n" + RELEASED + "Licence: x\n"
        self.assertRejects(text, "not the line directly after")

    def test_line_before_version_is_rejected(self):
        text = HEAD + RELEASED + VERSION + TAIL
        self.assertRejects(text, "not the line directly after")

    def test_released_without_version_is_rejected(self):
        self.assertRejects(HEAD + RELEASED + TAIL, "there is no Version: line")

    def test_duplicate_line_is_rejected(self):
        self.assertRejects(VALID + "Released: 2026-11-15\n", "more than one Released line")

    def test_decorated_duplicate_lines_are_rejected(self):
        # R8: a stale copy behind Markdown markers or format characters is
        # still a second Released line.
        for label, line in DECORATED:
            with self.subTest(label):
                self.assertRejects(VALID + line + "\n", "more than one Released line")

    def test_decorated_first_line_is_malformed_not_skipped(self):
        for label, line in DECORATED:
            with self.subTest(label):
                self.assertRejects(HEAD + line + "\n" + VERSION + RELEASED + TAIL, "not spelled exactly")

    def test_decorations_outside_the_rule_are_not_detected(self):
        # The residual the module docstring states, pinned so the claim and
        # the behaviour cannot drift apart.
        for label, line in UNDETECTED:
            with self.subTest(label):
                self.assertAccepts(VALID + line + "\n")

    def test_internal_error_exits_6_not_4(self):
        # R6: an internal failure is not an unreadable input.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_text(VALID, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-I", "-c", CRASH_RUNNER, str(EXTRACTOR), str(path)],
                capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 6, proc.stderr)
        self.assertIn("internal error", proc.stderr)
        self.assertIn("injected internal error", proc.stderr)

    def test_misspelt_key_is_malformed_not_absent(self):
        self.assertRejects(HEAD + VERSION + "released: 2026-11-15\n" + TAIL, "not spelled exactly")
        self.assertRejects(HEAD + VERSION + "  Released: 2026-11-15\n" + TAIL, "not spelled exactly")
        self.assertRejects(HEAD + VERSION + "Released : 2026-11-15\n" + TAIL, "not spelled exactly")

    def test_trailing_non_blank_space_is_rejected(self):
        # Fix round 10 (mutation sweep): only spaces and tabs may follow the
        # date; a no-break space or a form feed is trailing text.
        for space in ("\u00a0", "\x0c"):
            with self.subTest(space=space):
                self.assertRejects(HEAD + VERSION + "Released: 2026-11-15" + space + "\n" + TAIL,
                                   "is not a bare YYYY-MM-DD date")

    def test_trailing_text_is_rejected(self):
        self.assertRejects(HEAD + VERSION + "Released: 2026-11-15 (draft)\n" + TAIL, "not a bare YYYY-MM-DD")

    def test_other_date_forms_are_rejected(self):
        for value in ("15 November 2026", "2026-11-5", "2026/11/15", "20261115", "2026-11-15T00:00:00Z"):
            with self.subTest(value):
                self.assertRejects(HEAD + VERSION + f"Released: {value}\n" + TAIL, "not a bare YYYY-MM-DD")

    def test_non_ascii_digits_are_rejected(self):
        self.assertRejects(HEAD + VERSION + "Released: 2026-11-\uff11\uff15\n" + TAIL, "not a bare YYYY-MM-DD")

    def test_crlf_line_endings_are_read(self):
        self.assertAccepts(VALID.replace("\n", "\r\n"))

    def test_lone_cr_line_endings_are_read(self):
        self.assertAccepts(VALID.replace("\n", "\r"))

    def test_nul_in_the_line_is_rejected(self):
        self.assertRejects(HEAD + VERSION + "Released: 2026-11-15\x00\n" + TAIL, "not a bare YYYY-MM-DD")

    def test_invalid_utf8_is_rejected(self):
        self.assertRejects(VALID.encode("utf-8") + b"\xff\n", "not valid UTF-8")

    def test_large_valid_input_on_stdin_reads_whole(self):
        big = VALID + "<!-- " + ("x" * 200000) + " -->\n"
        self.assertAccepts(big, stdin=True)

    def test_usage_errors_exit_2(self):
        code, _out, err = run(None, "a", "b")
        self.assertEqual(code, 2, err)
        code, _out, err = run(None, "--nonsense")
        self.assertEqual(code, 2, err)

    def test_baseline_is_printed(self):
        code, out, err = run(None, "--baseline")
        self.assertEqual((code, out), (0, "1.0.14\n"), err)

    def test_check_date(self):
        self.assertEqual(run(None, "--check-date", "2026-11-15")[:2], (0, "2026-11-15\n"))
        for value in ("2026-02-30", "2026-11-15 ", "2026-1-15", "", "today"):
            with self.subTest(value):
                self.assertEqual(run(None, "--check-date", value)[0], 1)
        # Fix round 10 (mutation sweep): a month or day of one digit fails
        # the date form itself, before any calendar check.
        for value in ("2026-11-5", "2026-1-15"):
            with self.subTest(value):
                self.assertEqual(
                    run(None, "--check-date", value),
                    (1, "", f"skill-release-date: not a bare YYYY-MM-DD date: {value!r}\n"),
                )

    def test_released_beside_a_malformed_version_line_is_rejected(self):
        # F12: the Version line value is validated before the placement rule.
        # Fix round 10 (mutation sweep): a no-break space is not a blank.
        for version in ("Version: draft", "Version: 1.0", "Version: 1.0.15 beta", "Version:\u00a01.0.15"):
            with self.subTest(version):
                self.assertRejects(HEAD + version + "\n" + RELEASED + TAIL, "is not a bare X.Y.Z version")
        self.assertRejects(HEAD + "Version: draft\nAuthor: x\n" + RELEASED, "is not a bare X.Y.Z version")

    def test_unreadable_input_exits_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run(None, tmp)
        self.assertEqual((code, out), (4, ""), err)
        self.assertIn("could not read", err)

    def test_requires_date(self):
        # F7: one numeric baseline rule for every caller.
        for version, answer in (
            ("1.0.9", "optional"), ("1.0.14", "optional"), ("1.00.14", "optional"),
            ("1.0.15", "required"), ("1.0.100", "required"), ("1.1.0", "required"),
        ):
            with self.subTest(version):
                self.assertEqual(run(None, "--requires-date", version)[:2], (0, answer + "\n"))
        for value in ("1.0", "v1.0.15", ""):
            with self.subTest(value):
                self.assertEqual(run(None, "--requires-date", value)[0], 1)
        # Fix round 10 (mutation sweep): an empty part is malformed (exit 1),
        # never an internal error.
        for value in ("1.0.", "1..15", ".0.15"):
            with self.subTest(value):
                self.assertEqual(
                    run(None, "--requires-date", value),
                    (1, "", f"skill-release-date: not a bare X.Y.Z version: {value!r}\n"),
                )

    def test_publish_window(self):
        # F1: same UTC day with at least 10 minutes left passes; anything else
        # is refused with exit 5, and a malformed value is exit 1.
        for now in ("2026-11-15T00:00:00Z", "2026-11-15T12:00:00Z", "2026-11-15T23:50:00Z"):
            with self.subTest(now):
                self.assertEqual(run(None, "--publish-window", "2026-11-15", now)[:2], (0, "2026-11-15\n"))
        for now, fragment in (
            ("2026-11-15T23:50:01Z", "only 599 seconds remain"),
            ("2026-11-15T23:59:59Z", "only 1 second remains in"),
            ("2026-11-15T23:59:58Z", "only 2 seconds remain in"),
            ("2026-11-16T00:00:05Z", "the UTC day is now 2026-11-16"),
            ("2026-11-14T12:00:00Z", "the UTC day is now 2026-11-14"),
        ):
            with self.subTest(now):
                code, out, err = run(None, "--publish-window", "2026-11-15", now)
                self.assertEqual((code, out), (5, ""), err)
                self.assertIn(fragment, err)
                self.assertNotIn(" 1 seconds", err)
        for args in (("2026-11-15", "2026-11-15T12:00:00"), ("2026-02-30", "2026-11-15T12:00:00Z")):
            with self.subTest(args):
                self.assertEqual(run(None, "--publish-window", *args)[0], 1)
        self.assertEqual(run(None, "--publish-window", "2026-11-15")[0], 2)

    def test_publish_window_on_the_last_representable_day(self):
        # Row 99: the margin is counted without building the next date, so
        # 9999-12-31, the last day a date can name, answers like any other
        # day instead of failing as an internal error.
        self.assertEqual(srd.PUBLISH_MARGIN_SECONDS, 600)
        day = "9999-12-31"
        self.assertEqual(run(None, "--publish-window", day, "9999-12-31T12:00:00Z"), (0, day + "\n", ""))
        message = (
            "refusing to start publishing: only 300 seconds remain in the UTC day 9999-12-31 "
            "(9999-12-31T23:55:00Z); publishing is refused within 10 minutes of UTC midnight, "
            "so the release cannot land on a later day than its Released line names"
        )
        self.assertEqual(
            run(None, "--publish-window", day, "9999-12-31T23:55:00Z"), (5, "", f"skill-release-date: {message}\n")
        )
        code, out, err = run(None, "--publish-window", day, "9999-12-31T23:59:59Z")
        self.assertEqual((code, out), (5, ""), err)
        self.assertIn("only 1 second remains in", err)
        for now, outcome in (
            ("9999-12-31T12:00:00Z", {"outcome": "value", "value": day}),
            ("9999-12-31T23:55:00Z", {"outcome": "refused", "message": message}),
        ):
            with self.subTest(json=now):
                self.assertEqual(
                    run(request("publish_window", expected=day, now=now), "--json", stdin=True),
                    (0, reply_bytes({"op": "publish_window", **outcome}), ""),
                )

    def test_a_version_part_past_the_integer_digit_limit_is_malformed(self):
        # Row 101: a part with more digits than int() converts is malformed
        # (exit 1, a malformed reply), never an internal error, and a part at
        # the limit still compares. The child runs under the default limit,
        # 4300 digits.
        over = "9" * 4301
        for label, version in (("major", f"{over}.0.0"), ("minor", f"1.{over}.0"), ("patch", f"1.0.{over}")):
            with self.subTest(label):
                message = f"a part of the version has more than 4300 digits: {version!r}"
                self.assertEqual(run(None, "--requires-date", version), (1, "", f"skill-release-date: {message}\n"))
                self.assertEqual(
                    run(request("requires_release_date", version), "--json", stdin=True),
                    (0, reply_bytes({"op": "requires_release_date", "outcome": "malformed", "message": message}), ""),
                )
        for label, version, answer in (
            ("major, 4300 nines", "9" * 4300 + ".0.0", "required"),
            ("minor, 4300 zeros", "1." + "0" * 4300 + ".14", "optional"),
            ("patch, 4300 nines", "1.0." + "9" * 4300, "required"),
        ):
            with self.subTest(label):
                self.assertEqual(run(None, "--requires-date", version), (0, answer + "\n", ""))
                self.assertEqual(
                    run(request("requires_release_date", version), "--json", stdin=True),
                    (0, reply_bytes({"op": "requires_release_date", "outcome": "value", "value": answer == "required"}), ""),
                )

    def test_a_lowered_integer_digit_limit_is_read_at_run_time(self):
        # Row 101: the limit is read when a version is compared, so a child
        # started with a lower limit (640 is the lowest positive limit Python
        # accepts) reports a longer part as malformed instead of failing.
        def run_lowered(*args: str, data: bytes = b""):
            proc = subprocess.run(
                [sys.executable, "-I", "-X", "int_max_str_digits=640", str(EXTRACTOR), *args],
                input=data, capture_output=True,
            )
            return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")

        version = "1.0." + "9" * 641
        message = f"a part of the version has more than 640 digits: {version!r}"
        self.assertEqual(run_lowered("--requires-date", version), (1, "", f"skill-release-date: {message}\n"))
        self.assertEqual(
            run_lowered("--json", data=request("requires_release_date", version)),
            (0, reply_bytes({"op": "requires_release_date", "outcome": "malformed", "message": message}), ""),
        )
        self.assertEqual(run_lowered("--requires-date", "1.0." + "9" * 640), (0, "required\n", ""))

    def test_an_interpreter_without_the_digit_limit_compares_a_long_part(self):
        # The client supports Python 3.9 and later and runs the extractor with
        # its own interpreter, which may predate the limit and so have no
        # sys.get_int_max_str_digits. There int() converts a part of any
        # length, so a 5000-digit part compares as a value, never exit 6.
        def run_unlimited(*args: str, data: bytes = b""):
            proc = subprocess.run(
                [sys.executable, "-I", "-c", NO_LIMIT_RUNNER, str(EXTRACTOR), *args],
                input=data, capture_output=True,
            )
            return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")

        for label, version, answer in (
            ("major, 5000 nines", "9" * 5000 + ".0.0", "required"),
            ("minor, 5000 zeros", "1." + "0" * 5000 + ".14", "optional"),
            ("patch, 5000 nines", "1.0." + "9" * 5000, "required"),
        ):
            with self.subTest(label):
                self.assertEqual(run_unlimited("--requires-date", version), (0, answer + "\n", ""))
                self.assertEqual(
                    run_unlimited("--json", data=request("requires_release_date", version)),
                    (0, reply_bytes({"op": "requires_release_date", "outcome": "value", "value": answer == "required"}), ""),
                )

    def test_confirm_published(self):
        self.assertEqual(
            run(None, "--confirm-published", "2026-11-15", "2026-11-15T23:59:59Z")[:2], (0, "2026-11-15\n")
        )
        code, out, err = run(None, "--confirm-published", "2026-11-15", "2026-11-16T00:00:02Z")
        self.assertEqual((code, out), (5, ""), err)
        self.assertIn("published on 2026-11-16", err)
        self.assertIn("names 2026-11-15", err)
        for value in ("null", "", "2026-11-15"):
            with self.subTest(value):
                self.assertEqual(run(None, "--confirm-published", "2026-11-15", value)[0], 1)

    def test_published_day(self):
        self.assertEqual(run(None, "--published-day", "2026-11-15T23:59:59Z")[:2], (0, "2026-11-15\n"))
        for value in (
            "null", "", "2026-11-15", "2026-11-15T09:30:00+00:00", "2026-11-15T09:30:00.123Z",
            "2026-02-30T09:30:00Z", "2026-11-15T25:00:00Z", "2026-11-15T09:30:00Z\n",
        ):
            with self.subTest(value):
                self.assertEqual(run(None, "--published-day", value)[0], 1)
        # Fix round 10 (mutation sweep): an instant with no Z fails the
        # instant form itself.
        value = "2026-11-15T09:30:00"
        self.assertEqual(
            run(None, "--published-day", value),
            (1, "", f"skill-release-date: published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}\n"),
        )


class FunctionTest(unittest.TestCase):
    def test_baseline_constant(self):
        self.assertEqual(srd.BASELINE_VERSION, "1.0.14")

    def test_internal_error_exit_constant(self):
        self.assertEqual(srd.INTERNAL_ERROR_EXIT, 6)

    def test_publish_margin_constant(self):
        # Fix round 10 (mutation sweep): every control constant is pinned
        # at its shipped value.
        self.assertEqual(srd.PUBLISH_MARGIN_SECONDS, 600)

    def test_json_ops_constant(self):
        self.assertEqual(
            srd.JSON_OPS,
            ("extract", "requires_release_date", "release_day_from_published_at", "baseline",
             "parse_date", "publish_window", "confirm_published"),
        )
        self.assertEqual(
            srd.JSON_REQUEST_KEYS,
            {
                "extract": ("arg",),
                "requires_release_date": ("arg",),
                "release_day_from_published_at": ("arg",),
                "baseline": (),
                "parse_date": ("arg",),
                "publish_window": ("expected", "now"),
                "confirm_published": ("expected", "published_at"),
            },
        )

    def test_requires_release_date_sorts_numerically(self):
        self.assertFalse(srd.requires_release_date("1.0.14"))
        self.assertFalse(srd.requires_release_date("1.00.14"))
        self.assertFalse(srd.requires_release_date("1.0.9"))
        self.assertFalse(srd.requires_release_date("0.99.99"))
        self.assertTrue(srd.requires_release_date("1.0.15"))
        self.assertTrue(srd.requires_release_date("1.0.100"))
        self.assertTrue(srd.requires_release_date("1.1.0"))
        self.assertTrue(srd.requires_release_date("2.0.0"))

    def test_requires_release_date_rejects_a_malformed_version(self):
        for value in ("1.0", "1.0.15 ", "v1.0.15", ""):
            with self.subTest(value):
                with self.assertRaises(srd.Malformed):
                    srd.requires_release_date(value)

    def test_version_key_reads_the_digit_limit_at_run_time(self):
        # Row 101: the limit in force when a version is compared decides, and
        # 0 means no limit, so a part of any length then compares.
        self.addCleanup(sys.set_int_max_str_digits, sys.get_int_max_str_digits())
        sys.set_int_max_str_digits(640)
        version = "1.0." + "9" * 641
        with self.assertRaises(srd.Malformed) as caught:
            srd.version_key(version)
        self.assertEqual(str(caught.exception), f"a part of the version has more than 640 digits: {version!r}")
        self.assertTrue(srd.requires_release_date("1.0." + "9" * 640))
        sys.set_int_max_str_digits(0)
        self.assertTrue(srd.requires_release_date("1.0." + "9" * 5000))

    def test_the_margin_agrees_with_the_next_midnight_on_ordinary_days(self):
        # Row 99: counting the margin from the time of day gives the verdict
        # and the count that counting to the next UTC midnight gives, on
        # sampled instants of days that have a next day. The seed is fixed,
        # so every run checks the same instants.
        rng = random.Random(99)
        first = datetime.date(1, 1, 1).toordinal()
        last = datetime.date(9999, 12, 30).toordinal()
        days = [datetime.date(1, 1, 1), datetime.date(2024, 2, 29), datetime.date(2026, 11, 15),
                datetime.date(9999, 12, 30)]
        days += [datetime.date.fromordinal(rng.randint(first, last)) for _ in range(200)]
        edges = (0, 1, 85799, 85800, 85801, 86398, 86399)
        checked = 0
        for day in days:
            for second in (*edges, *(rng.randrange(86400) for _ in range(10))):
                now_text = f"{day.isoformat()}T{second // 3600:02d}:{second // 60 % 60:02d}:{second % 60:02d}Z"
                now = srd.parse_instant(now_text, "the current instant")
                midnight = datetime.datetime.combine(
                    day + datetime.timedelta(days=1), datetime.time(0), tzinfo=datetime.timezone.utc
                )
                old = int((midnight - now).total_seconds())
                problem = srd.publish_window_problem(day.isoformat(), now)
                if old >= srd.PUBLISH_MARGIN_SECONDS:
                    self.assertIsNone(problem, now_text)
                else:
                    left = "1 second remains" if old == 1 else f"{old} seconds remain"
                    self.assertIsNotNone(problem, now_text)
                    self.assertTrue(
                        problem.startswith(f"only {left} in the UTC day {day.isoformat()} ({now_text}); "), problem
                    )
                checked += 1
        self.assertEqual(checked, 204 * 17)

    def test_extract_matches_the_cli(self):
        self.assertEqual(srd.extract(VALID), "2026-11-15")
        self.assertIsNone(srd.extract(HEAD + VERSION + TAIL))
        with self.assertRaises(srd.Malformed):
            srd.extract(VALID + "Released: 2026-11-16\n")
        # Row 80: the --json mode agrees with the function and with the other
        # modes, message text included.
        duplicate = VALID + "Released: 2026-11-16\n"
        for label, text, outcome in (
            ("a day", VALID, {"outcome": "value", "value": "2026-11-15"}),
            ("no line", HEAD + VERSION + TAIL, {"outcome": "absent"}),
            ("a duplicate line", duplicate, None),
        ):
            with self.subTest(label):
                code, out, err = run(request("extract", text), "--json", stdin=True)
                self.assertEqual(code, 0, err)
                reply = json.loads(out)
                if outcome is None:
                    with self.assertRaises(srd.Malformed) as caught:
                        srd.extract(text)
                    outcome = {"outcome": "malformed", "message": str(caught.exception)}
                self.assertEqual(reply, {"op": "extract", **outcome})
                cli_code, cli_out, cli_err = run(text.encode("utf-8"))
                if reply["outcome"] == "value":
                    self.assertEqual((cli_code, cli_out), (0, reply["value"] + "\n"), cli_err)
                elif reply["outcome"] == "absent":
                    self.assertEqual(cli_code, 3, cli_err)
                else:
                    self.assertEqual((cli_code, cli_err), (1, f"skill-release-date: {reply['message']}\n"))
        for value in ("2026-11-15T00:00:00Z", "null"):
            with self.subTest(published_at=value):
                code, out, err = run(request("release_day_from_published_at", value), "--json", stdin=True)
                self.assertEqual(code, 0, err)
                reply = json.loads(out)
                cli_code, cli_out, cli_err = run(None, "--published-day", value)
                if reply["outcome"] == "value":
                    self.assertEqual((cli_code, cli_out), (0, reply["value"] + "\n"), cli_err)
                else:
                    self.assertEqual(reply["outcome"], "malformed")
                    self.assertEqual((cli_code, cli_err), (1, f"skill-release-date: {reply['message']}\n"))

    def test_published_day_function(self):
        self.assertEqual(srd.release_day_from_published_at("2026-11-15T00:00:00Z"), "2026-11-15")
        for value in (None, "null", "2026-11-15T00:00:00"):
            with self.subTest(value):
                with self.assertRaises(srd.Malformed):
                    srd.release_day_from_published_at(value)


class JsonModeTest(unittest.TestCase):
    """Row 80: the --json mode, through the real CLI."""

    def malformed_text(self, function, *args):
        with self.assertRaises(srd.Malformed) as caught:
            function(*args)
        return str(caught.exception)

    def test_every_reply_shape_is_exact(self):
        duplicate = VALID + "Released: 2026-11-16\n"
        rows = (
            ("extract a day", "extract", VALID,
             {"op": "extract", "outcome": "value", "value": "2026-11-15"}),
            ("extract with no line", "extract", HEAD + VERSION + TAIL, {"op": "extract", "outcome": "absent"}),
            ("extract a malformed line", "extract", duplicate,
             {"op": "extract", "outcome": "malformed", "message": self.malformed_text(srd.extract, duplicate)}),
            ("requires_release_date above the baseline", "requires_release_date", "1.0.15",
             {"op": "requires_release_date", "outcome": "value", "value": True}),
            ("requires_release_date at the baseline", "requires_release_date", "1.0.14",
             {"op": "requires_release_date", "outcome": "value", "value": False}),
            ("requires_release_date not a bare version", "requires_release_date", "1.0",
             {"op": "requires_release_date", "outcome": "malformed",
              "message": self.malformed_text(srd.requires_release_date, "1.0")}),
            ("release_day_from_published_at a day", "release_day_from_published_at", "2026-11-15T23:59:59Z",
             {"op": "release_day_from_published_at", "outcome": "value", "value": "2026-11-15"}),
            ("release_day_from_published_at unusable", "release_day_from_published_at", "null",
             {"op": "release_day_from_published_at", "outcome": "malformed",
              "message": self.malformed_text(srd.release_day_from_published_at, "null")}),
            ("baseline", "baseline", None, {"op": "baseline", "outcome": "value", "value": "1.0.14"}),
        )
        for label, op, arg, reply in rows:
            with self.subTest(label):
                code, out, err = run(request(op, arg), "--json", stdin=True)
                self.assertEqual(code, 0, err)
                self.assertEqual(out, reply_bytes(reply))
                self.assertEqual(err, "")

    def test_text_crosses_the_request_exactly(self):
        # A NUL, a line separator, a byte order mark, and a character outside
        # the basic plane reach the extractor exactly, so the reply equals the
        # function called directly, message text included.
        for label, text in (
            ("NUL in the line", HEAD + VERSION + "Released: 2026-11-15\x00\n" + TAIL),
            ("line separator in a key-like line", VALID + "\u2028Released: 2026-11-01\n"),
            ("byte order mark in a key-like line", VALID + "\ufeffReleased: 2026-11-01\n"),
            ("text outside the basic plane", VALID + "\U0001f600\n"),
            ("carriage returns left in the text", VALID.replace("\n", "\r\n")),
            # A malformed line that keeps a printable character outside ASCII
            # in its message, so the reply must escape it.
            ("full-width colon in the first key-like line", HEAD + VERSION + "Released\uff1a 2026-11-15\n" + TAIL),
            ("accented letter in the first Released line", HEAD + VERSION + "Released: 2026-11-15 \u00e9\n" + TAIL),
            # A request far larger than one pipe buffer is read whole.
            ("content larger than 64 KiB", VALID + ("x" * 100 + "\n") * 1000 + "Released: 2026-11-01\n"),
        ):
            with self.subTest(label):
                try:
                    value = srd.extract(text)
                except srd.Malformed as error:
                    expected = {"op": "extract", "outcome": "malformed", "message": str(error)}
                else:
                    if value is None:
                        expected = {"op": "extract", "outcome": "absent"}
                    else:
                        expected = {"op": "extract", "outcome": "value", "value": value}
                for encoding, data in (("ASCII", request("extract", text)), ("raw UTF-8", raw_request("extract", text))):
                    with self.subTest(encoding):
                        code, out, err = run(data, "--json", stdin=True)
                        self.assertEqual(code, 0, err)
                        self.assertEqual(out, reply_bytes(expected))
                        self.assertEqual(err, "")

    def test_bad_requests_exit_2_with_nothing_on_stdout(self):
        # Each bad request exits 2 with nothing on stdout and exactly one
        # line on stderr. A request that is not a UTF-8 JSON value names the
        # error the standard library gives for it; every other line is exact.
        prefix = "skill-release-date: --json: "
        not_json = prefix + "the request is not a UTF-8 JSON value: "
        for label, data, expected in (
            ("empty stdin", b"", None),
            ("invalid UTF-8", b"\xff", None),
            ("not JSON", b"not json", None),
            ("invalid UTF-8 inside a JSON string", b'{"op": "extract", "arg": "\xff"}', None),
            ("an encoded surrogate inside a JSON string", b'{"op": "extract", "arg": "\xed\xa0\x80"}', None),
            ("a byte order mark before the request", b"\xef\xbb\xbf" + request("baseline"), None),
            ("a UTF-16 request", '{"op": "baseline"}'.encode("utf-16"), None),
            # Fix round 11 (DISCOVERY round 9, finding 4): the request is
            # parsed as sent, never stripped, so a vertical tab or a form
            # feed, which JSON does not count as whitespace, makes it no JSON
            # value; and an empty object names no op.
            ("a request wrapped in vertical tabs", b"\x0b" + request("baseline") + b"\x0b", None),
            ("a request wrapped in form feeds", b"\x0c" + request("baseline") + b"\x0c", None),
            # Fix round 12 (VERIFY round 9.1, finding 4): one such character
            # on either side alone is enough.
            ("a request followed by a vertical tab", request("baseline") + b"\x0b", None),
            ("a request followed by a form feed", request("baseline") + b"\x0c", None),
            ("a request behind a vertical tab", b"\x0b" + request("baseline"), None),
            ("a request behind a form feed", b"\x0c" + request("baseline"), None),
            ("an empty object", b"{}", "the request names no known op: None"),
            ("a list", b"[]", "the request is not a JSON object"),
            ("a string", b"\"extract\"", "the request is not a JSON object"),
            ("unknown op", request("nope", "x"), "the request names no known op: 'nope'"),
            ("op another function of the module", request("parse_instant", "2026-11-15"),
             "the request names no known op: 'parse_instant'"),
            ("op the main function", request("main", "x"), "the request names no known op: 'main'"),
            ("op in another case", request("Extract", "x"), "the request names no known op: 'Extract'"),
            ("op with a trailing space", request("baseline "), "the request names no known op: 'baseline '"),
            ("op not a string", b'{"op": 5, "arg": "x"}', "the request names no known op: 5"),
            ("op a list", b'{"op": ["extract"], "arg": "x"}', "the request names no known op: ['extract']"),
            ("extra key", b'{"op": "extract", "arg": "x", "extra": 1}',
             "a request for extract has exactly the keys arg, op"),
            ("missing arg", b'{"op": "extract"}', "a request for extract has exactly the keys arg, op"),
            ("missing arg for requires_release_date", b'{"op": "requires_release_date"}',
             "a request for requires_release_date has exactly the keys arg, op"),
            ("extra key for release_day_from_published_at",
             b'{"op": "release_day_from_published_at", "arg": "x", "extra": 1}',
             "a request for release_day_from_published_at has exactly the keys arg, op"),
            ("missing op", b'{"arg": "x"}', "the request names no known op: None"),
            ("arg not a string", b'{"op": "extract", "arg": 5}', "the arg of a request for extract is not a string"),
            ("arg a list", b'{"op": "requires_release_date", "arg": ["1.0.15"]}',
             "the arg of a request for requires_release_date is not a string"),
            ("arg null", b'{"op": "release_day_from_published_at", "arg": null}',
             "the arg of a request for release_day_from_published_at is not a string"),
            ("arg given for baseline", b'{"op": "baseline", "arg": "x"}', "a request for baseline has exactly the keys op"),
            # Row 89: the ops with named keys take exactly those keys, each a
            # string, checked in the order JSON_REQUEST_KEYS names them.
            ("arg given for publish_window", request("publish_window", "x"),
             "a request for publish_window has exactly the keys expected, now, op"),
            ("now missing for publish_window", request("publish_window", expected="2026-11-15"),
             "a request for publish_window has exactly the keys expected, now, op"),
            ("arg beside expected and now", request("publish_window", "x", expected="2026-11-15", now="x"),
             "a request for publish_window has exactly the keys expected, now, op"),
            ("expected not a string", b'{"op": "publish_window", "expected": 5, "now": "x"}',
             "the expected of a request for publish_window is not a string"),
            ("now not a string", b'{"op": "publish_window", "expected": "2026-11-15", "now": null}',
             "the now of a request for publish_window is not a string"),
            ("both not strings, expected named first", b'{"op": "confirm_published", "published_at": 1, "expected": 2}',
             "the expected of a request for confirm_published is not a string"),
            ("published_at not a string", b'{"op": "confirm_published", "expected": "2026-11-15", "published_at": []}',
             "the published_at of a request for confirm_published is not a string"),
            ("now given for confirm_published",
             request("confirm_published", expected="2026-11-15", now="2026-11-15T12:00:00Z"),
             "a request for confirm_published has exactly the keys expected, op, published_at"),
            ("expected given for parse_date", request("parse_date", expected="2026-11-15"),
             "a request for parse_date has exactly the keys arg, op"),
            ("arg not a string for parse_date", b'{"op": "parse_date", "arg": 20261115}',
             "the arg of a request for parse_date is not a string"),
        ):
            with self.subTest(label):
                code, out, err = run(data, "--json", stdin=True)
                self.assertEqual((code, out), (2, ""), err)
                if expected is None:
                    self.assertEqual(err, not_json + parse_error(data) + "\n")
                else:
                    self.assertEqual(err, prefix + expected + "\n")
        with self.subTest("nesting too deep to parse"):
            code, out, err = run(b"[" * 100000, "--json", stdin=True)
            self.assertEqual((code, out), (2, ""), err)
            # The error text depends on the depth of the interpreter stack,
            # so only its presence on the one line is pinned.
            self.assertTrue(err.startswith(not_json), err)
            self.assertTrue(err.endswith("\n"), err)
            self.assertEqual(err.count("\n"), 1, err)
            self.assertGreater(len(err), len(not_json) + 1, err)
        with self.subTest("--json with another argument"):
            code, out, err = run(request("baseline"), "--json", "extra", stdin=True)
            self.assertEqual((code, out, err), (2, "", USAGE_LINE))

    def test_internal_error_exits_6_with_nothing_on_stdout(self):
        # An internal error while the request is parsed, or inside the op
        # itself, is never a reply: exit 6 and an empty stdout. Malformed
        # subclasses ValueError, so a ValueError that is not a Malformed is an
        # internal error too; a Malformed catch that grew to ValueError, or to
        # Exception, would fail here.
        for label, target, kind, data in (
            ("while the request is parsed", "json.loads", "RuntimeError", request("baseline")),
            ("inside extract", "unicodedata.category", "RuntimeError", request("extract", VALID)),
            ("a ValueError inside extract", "unicodedata.category", "ValueError", request("extract", VALID)),
        ):
            with self.subTest(label):
                proc = subprocess.run(
                    [sys.executable, "-I", "-c", JSON_CRASH_RUNNER, target, kind, str(EXTRACTOR)],
                    input=data, capture_output=True,
                )
                self.assertEqual(proc.returncode, 6, proc.stderr)
                self.assertEqual(proc.stdout, b"")
                self.assertIn(f"internal error: {kind}(".encode("ascii"), proc.stderr)
                self.assertIn(b"injected internal error", proc.stderr)

    def test_an_internal_error_in_requires_date_matches_json_mode(self):
        # Row 101: --requires-date catches only Malformed, as the --json op
        # does, so another Exception inside version_key, a ValueError
        # included, exits 6 with the internal-error line and gives the same
        # result as the requires_release_date op. A catch that grew to
        # ValueError would fail the ValueError case.
        version = "1.0.14"
        for kind in ("ValueError", "RuntimeError"):
            with self.subTest(kind):
                results = []
                for args, data in (
                    (("--requires-date", version), b""),
                    (("--json",), request("requires_release_date", version)),
                ):
                    proc = subprocess.run(
                        [sys.executable, "-I", "-c", JSON_CRASH_RUNNER, "sys.get_int_max_str_digits", kind,
                         str(EXTRACTOR), *args],
                        input=data, capture_output=True,
                    )
                    results.append((proc.returncode, proc.stdout, proc.stderr))
                line = f"skill-release-date: internal error: {kind}('injected internal error in version_key')\n"
                self.assertEqual(results[0], (6, b"", line.encode("ascii")))
                self.assertEqual(results[1], results[0])

    def test_an_op_with_no_branch_is_an_internal_error(self):
        # Fix round 10: each op in JSON_OPS is answered by its own branch, so
        # an op added to JSON_OPS without one exits 6 with nothing on stdout,
        # never answered as another op. A copy of the extractor with such an
        # op added to JSON_OPS, just before its __main__ guard, shows it; the
        # argument is one release_day_from_published_at would answer.
        guard = '\nif __name__ == "__main__":\n'
        source = EXTRACTOR.read_text(encoding="utf-8")
        self.assertEqual(source.count(guard), 1)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "skill-release-date.py"
            copy.write_text(
                source.replace(
                    guard,
                    '\nJSON_REQUEST_KEYS["unrouted"] = ("arg",)\nJSON_OPS = JSON_OPS + ("unrouted",)\n' + guard,
                    1,
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, "-I", str(copy), "--json"],
                input=request("unrouted", "2026-11-15T23:59:59Z"), capture_output=True,
            )
        self.assertEqual((proc.returncode, proc.stdout), (6, b""), proc.stderr)
        self.assertEqual(
            proc.stderr,
            b"skill-release-date: internal error: RuntimeError(\"--json: no branch answers the op 'unrouted'\")\n",
        )

    def refusal_text(self, function, *args):
        with self.assertRaises(srd.Refused) as caught:
            function(*args)
        return str(caught.exception)

    def test_the_ops_of_the_shell_callers_reply_exactly_and_agree_with_the_cli(self):
        # Row 89: parse_date, publish_window and confirm_published answer as
        # --check-date, --publish-window and --confirm-published do: a value
        # is what the CLI prints with exit 0, a malformed reply carries the
        # message the CLI prints with exit 1, and a refused reply carries the
        # message the CLI prints with exit 5. The refusal texts are built
        # once, so the two modes cannot drift.
        window = srd.publish_window_verdict
        confirm = srd.confirm_published_verdict
        rows = (
            ("parse_date a day", "parse_date", {"arg": "2026-11-15"},
             ("--check-date", "2026-11-15"), {"outcome": "value", "value": "2026-11-15"}),
            ("parse_date an impossible day", "parse_date", {"arg": "2026-02-30"},
             ("--check-date", "2026-02-30"),
             {"outcome": "malformed", "message": self.malformed_text(srd.parse_date, "2026-02-30")}),
            ("parse_date not a day", "parse_date", {"arg": "15 November 2026"},
             ("--check-date", "15 November 2026"),
             {"outcome": "malformed", "message": self.malformed_text(srd.parse_date, "15 November 2026")}),
            ("publish_window inside the day", "publish_window",
             {"expected": "2026-11-15", "now": "2026-11-15T12:00:00Z"},
             ("--publish-window", "2026-11-15", "2026-11-15T12:00:00Z"),
             {"outcome": "value", "value": "2026-11-15"}),
            ("publish_window a malformed day", "publish_window",
             {"expected": "soon", "now": "2026-11-15T12:00:00Z"},
             ("--publish-window", "soon", "2026-11-15T12:00:00Z"),
             {"outcome": "malformed", "message": self.malformed_text(window, "soon", "2026-11-15T12:00:00Z")}),
            ("publish_window a malformed instant", "publish_window",
             {"expected": "2026-11-15", "now": "2026-11-15 12:00"},
             ("--publish-window", "2026-11-15", "2026-11-15 12:00"),
             {"outcome": "malformed", "message": self.malformed_text(window, "2026-11-15", "2026-11-15 12:00")}),
            ("publish_window too close to midnight", "publish_window",
             {"expected": "2026-11-15", "now": "2026-11-15T23:55:00Z"},
             ("--publish-window", "2026-11-15", "2026-11-15T23:55:00Z"),
             {"outcome": "refused", "message": self.refusal_text(window, "2026-11-15", "2026-11-15T23:55:00Z")}),
            ("publish_window another day", "publish_window",
             {"expected": "2026-11-15", "now": "2026-11-16T00:00:01Z"},
             ("--publish-window", "2026-11-15", "2026-11-16T00:00:01Z"),
             {"outcome": "refused", "message": self.refusal_text(window, "2026-11-15", "2026-11-16T00:00:01Z")}),
            ("confirm_published the same day", "confirm_published",
             {"expected": "2026-11-15", "published_at": "2026-11-15T23:59:59Z"},
             ("--confirm-published", "2026-11-15", "2026-11-15T23:59:59Z"),
             {"outcome": "value", "value": "2026-11-15"}),
            ("confirm_published a null published_at", "confirm_published",
             {"expected": "2026-11-15", "published_at": "null"},
             ("--confirm-published", "2026-11-15", "null"),
             {"outcome": "malformed", "message": self.malformed_text(confirm, "2026-11-15", "null")}),
            ("confirm_published another day", "confirm_published",
             {"expected": "2026-11-15", "published_at": "2026-11-16T00:00:02Z"},
             ("--confirm-published", "2026-11-15", "2026-11-16T00:00:02Z"),
             {"outcome": "refused", "message": self.refusal_text(confirm, "2026-11-15", "2026-11-16T00:00:02Z")}),
        )
        for label, op, fields, cli, outcome in rows:
            with self.subTest(label):
                code, out, err = run(request(op, **fields), "--json", stdin=True)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(out, reply_bytes({"op": op, **outcome}))
                cli_code, cli_out, cli_err = run(None, *cli)
                if outcome["outcome"] == "value":
                    self.assertEqual((cli_code, cli_out, cli_err), (0, outcome["value"] + "\n", ""))
                else:
                    expected_code = 5 if outcome["outcome"] == "refused" else 1
                    self.assertEqual(
                        (cli_code, cli_out, cli_err),
                        (expected_code, "", f"skill-release-date: {outcome['message']}\n"),
                    )
        # The refusal texts, pinned once so a change to either is seen.
        self.assertEqual(
            self.refusal_text(confirm, "2026-11-15", "2026-11-16T00:00:02Z"),
            "the release was published on 2026-11-16 (UTC; published_at 2026-11-16T00:00:02Z), "
            "but its Released line names 2026-11-15",
        )
        self.assertTrue(
            self.refusal_text(window, "2026-11-15", "2026-11-15T23:55:00Z").startswith(
                "refusing to start publishing: only 300 seconds remain in the UTC day 2026-11-15"
            )
        )

    def test_refused_is_a_reply_of_the_two_day_checks_only(self):
        # Row 89: no other op ever replies refused; each, given input it
        # cannot accept, replies malformed.
        for op, arg in (
            ("extract", HEAD + VERSION + "Released: soon\n" + TAIL),
            ("requires_release_date", "1.0"),
            ("release_day_from_published_at", "null"),
            ("parse_date", "2026-13-01"),
        ):
            with self.subTest(op):
                code, out, err = run(request(op, arg), "--json", stdin=True)
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out)["outcome"], "malformed")
        code, out, err = run(request("baseline"), "--json", stdin=True)
        self.assertEqual((code, json.loads(out)["outcome"]), (0, "value"), err)

    def test_an_internal_error_in_an_op_of_the_shell_callers_exits_6(self):
        # Row 89: as for the other ops, an Exception inside parse_date,
        # publish_window or confirm_published is never a reply. The
        # publish_window cases fail time.strftime, which formats the instant
        # in a refusal, so the Exception rises inside publish_window_problem,
        # after parse_instant, which reads a ValueError as a bad instant. The
        # publish_window cases require the runner's message to name
        # publish_window_problem.
        for label, target, kind, data, where in (
            ("parse_date", "datetime.date", "RuntimeError", request("parse_date", "2026-11-15"), None),
            ("publish_window", "time.strftime", "RuntimeError",
             request("publish_window", expected="2026-11-15", now="2026-11-15T23:55:00Z"), "publish_window_problem"),
            ("publish_window, a ValueError", "time.strftime", "ValueError",
             request("publish_window", expected="2026-11-15", now="2026-11-15T23:55:00Z"), "publish_window_problem"),
            ("confirm_published", "datetime.datetime", "RuntimeError",
             request("confirm_published", expected="2026-11-15", published_at="2026-11-15T12:00:00Z"), None),
        ):
            with self.subTest(label):
                proc = subprocess.run(
                    [sys.executable, "-I", "-c", JSON_CRASH_RUNNER, target, kind, str(EXTRACTOR)],
                    input=data, capture_output=True,
                )
                self.assertEqual(proc.returncode, 6, proc.stderr)
                self.assertEqual(proc.stdout, b"")
                self.assertTrue(proc.stderr.startswith(b"skill-release-date: internal error: "), proc.stderr)
                if where is not None:
                    line = f"skill-release-date: internal error: {kind}('injected internal error in {where}')\n"
                    self.assertEqual(proc.stderr, line.encode("ascii"))


class PatternPinTest(unittest.TestCase):
    """Fix round 11 (DISCOVERY round 9, finding 1): every character class,
    width and anchor of every pattern of the extractor is pinned by inputs
    that the shipped pattern and a pattern with that part changed answer
    differently, with the exact message where one is given. The digits of
    every pattern are ASCII digits only, so a digit of another script fails
    the pattern itself; each part has its exact width; and the blanks of
    the Released and Version line patterns are spaces and tabs only, so a
    no-break space, a form feed or a vertical tab is not one."""

    def malformed(self, function, value):
        with self.assertRaises(srd.Malformed) as caught:
            function(value)
        return str(caught.exception)

    def test_a_list_number_of_any_width_marks_a_key_like_line(self):
        # RELEASED_KEY_LIKE: an ordered-list number has one or more digits,
        # so a stale copy behind "10." is still a second Released line.
        for line in ("10. Released: 2025-01-01", "10) Released: 2025-01-01", "123. Released: 2025-01-01"):
            with self.subTest(line):
                text = VALID + line + "\n"
                self.assertEqual(self.malformed(srd.extract, text), "more than one Released line (lines 4, 9)")
                self.assertEqual(
                    run(text.encode("utf-8")), (1, "", "skill-release-date: more than one Released line (lines 4, 9)\n")
                )

    def test_every_unicode_whitespace_may_lead_a_key_like_line(self):
        # Fix round 12 (VERIFY round 9.1, finding 1): the leading blanks of
        # the key pattern are every character \s matches, so a stale copy
        # behind any one of them is still a second Released line, and a first
        # key-like line behind one is malformed. The list is checked against
        # every code point, so it cannot miss one. A file or stdin read ends
        # a line at a carriage return, which reaches extract only through
        # --json, so it is checked through the function alone.
        self.assertEqual(
            LEADING_WHITESPACE,
            tuple(ch for ch in map(chr, range(sys.maxunicode + 1)) if ch != "\n" and re.fullmatch(r"\s", ch)),
        )
        for space in LEADING_WHITESPACE:
            with self.subTest(space=space):
                text = VALID + space + "Released: 2025-01-01\n"
                self.assertEqual(self.malformed(srd.extract, text), "more than one Released line (lines 4, 9)")
                line = space + "Released: 2025-01-01"
                self.assertEqual(
                    self.malformed(srd.extract, HEAD + line + "\n" + VERSION + RELEASED + TAIL),
                    f"the first Released line is not spelled exactly Released: {line!r}",
                )
                if space != "\r":
                    self.assertEqual(
                        run(text.encode("utf-8")),
                        (1, "", "skill-release-date: more than one Released line (lines 4, 9)\n"),
                    )

    def test_each_leading_marker_and_each_mark_before_the_colon_is_key_like(self):
        # Fix round 12 (VERIFY round 9.1, finding 1): each leading Markdown
        # marker, alone and with no blank after it, and each blank and
        # emphasis marker between the word and the colon, alone and in a
        # run, marks a key-like line, in any case and with either colon.
        for line in (
            ">Released: 2025-01-01", "#Released: 2025-01-01", "*Released: 2025-01-01", "_Released: 2025-01-01",
            "+Released: 2025-01-01", "|Released: 2025-01-01", "[Released: 2025-01-01", "-Released: 2025-01-01",
            "0.Released: 2025-01-01", "9)Released: 2025-01-01", "> - 12. [**Released:** 2025-01-01",
            "Released : 2025-01-01", "Released\t: 2025-01-01", "Released*: 2025-01-01", "Released_: 2025-01-01",
            "Released \t*_ : 2025-01-01", "RELEASED: 2025-01-01", "rElEaSeD\uff1a 2025-01-01",
        ):
            with self.subTest(line):
                self.assertEqual(
                    self.malformed(srd.extract, VALID + line + "\n"), "more than one Released line (lines 4, 9)"
                )
        line = "Released\t: 2025-01-01"
        self.assertEqual(
            run((VALID + line + "\n").encode("utf-8")),
            (1, "", "skill-release-date: more than one Released line (lines 4, 9)\n"),
        )

    def test_every_character_that_folds_onto_a_letter_of_the_key_is_key_like(self):
        # Fix round 13 (VERIFY round 9.2, finding 2): the key word matches in
        # any case, and re.IGNORECASE also folds a character outside ASCII
        # onto a letter of it: the long s (U+017F) onto s, the only one, as
        # the list, checked against every code point, states. A stale copy
        # written with it is still a second Released line, and a first
        # key-like line written with it is malformed.
        letters = re.compile("[adelrs]", re.IGNORECASE)
        self.assertEqual(
            tuple(
                ch for ch in map(chr, range(sys.maxunicode + 1)) if ch not in "adelrsADELRS" and letters.fullmatch(ch)
            ),
            ("\u017f",),
        )
        for index, letter in enumerate("Released"):
            if not re.fullmatch(letter, "\u017f", re.IGNORECASE):
                continue
            word = "Released"[:index] + "\u017f" + "Released"[index + 1:]
            line = word + ": 2025-01-01"
            with self.subTest(line):
                self.assertEqual(line, "Relea\u017fed: 2025-01-01")
                text = VALID + line + "\n"
                self.assertEqual(self.malformed(srd.extract, text), "more than one Released line (lines 4, 9)")
                self.assertEqual(
                    run(text.encode("utf-8")), (1, "", "skill-release-date: more than one Released line (lines 4, 9)\n")
                )
                self.assertEqual(
                    self.malformed(srd.extract, HEAD + line + "\n" + VERSION + RELEASED + TAIL),
                    f"the first Released line is not spelled exactly Released: {line!r}",
                )

    def test_the_duplicate_message_names_one_based_line_numbers(self):
        self.assertEqual(
            self.malformed(srd.extract, VALID + "Released: 2026-11-16\n"), "more than one Released line (lines 4, 9)"
        )
        self.assertEqual(
            self.malformed(srd.extract, VALID + "x\nReleased: 2026-11-16\n> Released: 2026-11-17\n"),
            "more than one Released line (lines 4, 10, 11)",
        )

    def test_the_released_line_takes_any_run_of_spaces_and_tabs_only(self):
        # RELEASED_LINE: any run of spaces and tabs, none included, after the
        # colon and after the date.
        for line in (
            "Released:2026-11-15", "Released:\t2026-11-15", "Released:  2026-11-15", "Released: \t 2026-11-15",
            "Released: 2026-11-15\t", "Released: 2026-11-15 \t ",
        ):
            with self.subTest(line):
                self.assertEqual(srd.extract(HEAD + VERSION + line + "\n" + TAIL), "2026-11-15")
        for line in (
            "Released:\u00a02026-11-15", "Released:\x0c2026-11-15", "Released:\x0b2026-11-15",
            "Released: \u00a02026-11-15", "Released: 2026-11-15\x0b",
        ):
            with self.subTest(line):
                self.assertEqual(
                    self.malformed(srd.extract, HEAD + VERSION + line + "\n" + TAIL),
                    f"the first Released line is not a bare YYYY-MM-DD date: {line!r}",
                )
        line = "Released:\u00a02026-11-15"
        self.assertEqual(
            run((HEAD + VERSION + line + "\n" + TAIL).encode("utf-8")),
            (1, "", f"skill-release-date: the first Released line is not a bare YYYY-MM-DD date: {line!r}\n"),
        )

    def test_the_released_date_is_four_two_and_two_ascii_digits(self):
        # RELEASED_LINE: the date has exactly 4, 2 and 2 ASCII digits joined
        # by hyphens, so any other date fails the line pattern itself, with
        # its own message, before the date is checked on its own.
        for value in (
            "02026-11-15", "202-11-15", "2026-011-15", "2026-1-15", "2026-11-015", "2026-11-5",
            "\u0662\u0660\u0662\u0666-11-15", "2026-\u0661\u0661-15", "2026-11-\u0661\u0665",
            "2026/11/15", "2026-11/15", "2026.11.15",
            # Fix round 12 (VERIFY round 9.1, finding 6): no hyphen, or one.
            "20261115", "2026-1115", "202611-15",
        ):
            line = "Released: " + value
            with self.subTest(value):
                self.assertEqual(
                    self.malformed(srd.extract, HEAD + VERSION + line + "\n" + TAIL),
                    f"the first Released line is not a bare YYYY-MM-DD date: {line!r}",
                )

    def test_a_bare_date_is_four_two_and_two_ascii_digits(self):
        # DATE_FORM: the whole value, exactly 4, 2 and 2 ASCII digits joined
        # by hyphens, so any other value fails the form, never the calendar.
        for value in (
            "02026-11-15", "202-11-15", "2026-011-15", "2026-11-015",
            "\u0662\u0660\u0662\u0666-11-15", "2026-\u0661\u0661-15", "2026-11-\u0661\u0665",
            "2026/11/15", "2026-11/15", "2026-11-15 ", " 2026-11-15", "2026-11-15\n",
            "20261115", "2026-1115", "202611-15",
        ):
            with self.subTest(value):
                self.assertEqual(self.malformed(srd.parse_date, value), f"not a bare YYYY-MM-DD date: {value!r}")
        self.assertEqual(
            run(None, "--check-date", "02026-11-15"),
            (1, "", "skill-release-date: not a bare YYYY-MM-DD date: '02026-11-15'\n"),
        )
        # Fix round 12 (VERIFY round 9.1, finding 2): a date with no hyphen
        # or one hyphen fails the form, so date.fromisoformat, which takes
        # the basic form 20261115, never sees it, in every mode that takes a
        # bare date.
        for value in ("20261115", "2026-1115", "202611-15"):
            message = f"skill-release-date: not a bare YYYY-MM-DD date: {value!r}\n"
            for args in (
                ("--check-date", value), ("--confirm-published", value, "2026-11-15T09:30:00Z"),
                ("--publish-window", value, "2026-11-15T09:30:00Z"),
            ):
                with self.subTest(args):
                    self.assertEqual(run(None, *args), (1, "", message))

    def test_a_bare_version_is_three_runs_of_ascii_digits(self):
        # BARE_VERSION: each part one or more ASCII digits, joined by dots.
        for value in (
            "\u0661.0.15", "1.\u0660.15", "1.0.\u0661\u0665", "\uff11.0.15", "1x0x15", "1x0.15", "1.0x15",
            " 1.0.15", "1.0.15\n",
        ):
            with self.subTest(value):
                self.assertEqual(
                    self.malformed(srd.requires_release_date, value), f"not a bare X.Y.Z version: {value!r}"
                )
        self.assertEqual(
            run(request("requires_release_date", "\u0661.0.15"), "--json", stdin=True),
            (0, reply_bytes({"op": "requires_release_date", "outcome": "malformed",
                             "message": "not a bare X.Y.Z version: '\u0661.0.15'"}), ""),
        )

    def test_an_instant_is_two_ascii_digits_per_field_with_t_and_z(self):
        # PUBLISHED_AT_FORM: 4 ASCII digits for the year and exactly 2 for
        # each other field, an upper-case T and Z, hyphens and colons, so
        # any other value fails the form, never the strptime check, which
        # would accept a one-digit field or another script's digits.
        for value in (
            "2026-01-01T1:00:00Z", "2026-1-01T00:00:00Z", "2026-01-1T00:00:00Z", "2026-01-01T00:1:00Z",
            "2026-01-01T00:00:1Z", "202-01-01T00:00:00Z", "02026-01-01T00:00:00Z", "2026-001-01T00:00:00Z",
            "2026-01-001T00:00:00Z", "2026-01-01T000:00:00Z", "2026-01-01T00:000:00Z", "2026-01-01T00:00:000Z",
            "\u0662\u0660\u0662\u0666-01-01T00:00:00Z", "2026-\u0660\u0661-01T00:00:00Z",
            "2026-01-\u0660\u0661T00:00:00Z", "2026-01-01T\u0660\u0661:00:00Z", "2026-01-01T00:\u0660\u0661:00Z",
            "2026-01-01T00:00:\u0660\u0661Z", "2026-01-01 00:00:00Z", "2026-01-01t00:00:00Z",
            "2026-01-01T00:00:00z", "2026/01/01T00:00:00Z", "2026-01-01T00-00-00Z", "2026-01-01T00:00:00Z ",
            # Fix round 12 (VERIFY round 9.1, finding 6): no hyphen or one,
            # no colon or one, fractional seconds, and a leading blank.
            "20260101T00:00:00Z", "2026-0101T00:00:00Z", "202601-01T00:00:00Z", "2026-01-01T000000Z",
            "2026-01-01T0000:00Z", "2026-01-01T00:0000Z", "2026-01-01T00:00:00.123Z", "2026-01-01T00:00:00.5Z",
            " 2026-01-01T00:00:00Z",
        ):
            with self.subTest(value):
                self.assertEqual(
                    self.malformed(srd.release_day_from_published_at, value),
                    f"published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}",
                )
        self.assertEqual(
            run(None, "--published-day", "2026-01-01T1:00:00Z"),
            (1, "", "skill-release-date: published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: '2026-01-01T1:00:00Z'\n"),
        )
        self.assertEqual(
            run(None, "--publish-window", "2026-01-01", "2026-01-01T1:00:00Z"),
            (1, "", "skill-release-date: the current instant is not a YYYY-MM-DDTHH:MM:SSZ instant: "
                    "'2026-01-01T1:00:00Z'\n"),
        )
        for value in ("20260101T00:00:00Z", "2026-01-01T00:00:00.123Z"):
            with self.subTest(value):
                message = f"skill-release-date: published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}\n"
                self.assertEqual(run(None, "--published-day", value), (1, "", message))
                self.assertEqual(run(None, "--confirm-published", "2026-01-01", value), (1, "", message))
        value = "2026-01-01T\u0660\u0661:00:00Z"
        self.assertEqual(
            run(request("release_day_from_published_at", value), "--json", stdin=True),
            (0, reply_bytes({"op": "release_day_from_published_at", "outcome": "malformed",
                             "message": f"published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}"}), ""),
        )

    def test_an_instant_has_exactly_two_digits_of_seconds(self):
        # Fix round 14 (VERIFY round 9.3, finding 1): PUBLISHED_AT_FORM
        # requires the seconds, as exactly 2 ASCII digits, so an instant
        # with no seconds, or with 1 or 3 digits of them, fails the form,
        # never the strptime check, through the function, --published-day
        # and --json alike.
        for value in ("2026-01-01T00:00Z", "2026-01-01T00:00:1Z", "2026-01-01T00:00:000Z"):
            with self.subTest(value):
                message = f"published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}"
                self.assertEqual(self.malformed(srd.release_day_from_published_at, value), message)
                self.assertEqual(
                    run(None, "--published-day", value), (1, "", f"skill-release-date: {message}\n")
                )
                self.assertEqual(
                    run(request("release_day_from_published_at", value), "--json", stdin=True),
                    (0, reply_bytes({"op": "release_day_from_published_at", "outcome": "malformed",
                                     "message": message}), ""),
                )

    def test_an_instant_field_with_its_separator_but_no_digits_fails_the_form(self):
        # Every field of PUBLISHED_AT_FORM requires its digits: a value that
        # keeps every separator but drops only the digits of the seconds,
        # the hour, the minutes, the day, or the month fails the form, never
        # the strptime check, through the function, --published-day and
        # --json alike.
        for value in (
            "2026-01-01T00:00:Z", "2026-01-01T:00:00Z", "2026-01-01T00::00Z", "2026-01-T00:00:00Z",
            "2026--01T00:00:00Z",
        ):
            with self.subTest(value):
                message = f"published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}"
                self.assertEqual(self.malformed(srd.release_day_from_published_at, value), message)
                self.assertEqual(
                    run(None, "--published-day", value), (1, "", f"skill-release-date: {message}\n")
                )
                self.assertEqual(
                    run(request("release_day_from_published_at", value), "--json", stdin=True),
                    (0, reply_bytes({"op": "release_day_from_published_at", "outcome": "malformed",
                                     "message": message}), ""),
                )

    def test_the_version_line_takes_any_run_of_spaces_and_tabs_only(self):
        # VERSION_LINE: any run of spaces and tabs, none included, after the
        # colon and after the version, which is three runs of ASCII digits
        # joined by dots.
        for line in (
            "Version:1.0.15", "Version:\t1.0.15", "Version:  1.0.15", "Version: 1.0.15 ", "Version: 1.0.15\t",
            "Version: 1.0.15 \t ",
            # Fix round 12 (VERIFY round 9.1, finding 5): a part of any
            # width.
            "Version: 1.0.100", "Version: 100.0.15", "Version: 1.100.15", "Version: 1234.5678.9012",
        ):
            with self.subTest(line):
                self.assertEqual(srd.extract(HEAD + line + "\n" + RELEASED + TAIL), "2026-11-15")
        for line in (
            "Version: 1.0.15\u00a0", "Version: 1.0.15\x0c", "Version: 1.0.15\x0b", "Version:\x0c1.0.15",
            "Version:\x0b1.0.15", "Version: \u0661.0.15", "Version: 1.\u0660.15", "Version: 1.0.\u0661\u0665",
            "Version: .0.15", "Version: 1..15", "Version: 1.0.", "Version: 1x0x15", "Version: 1.0x15",
            # Fix round 12 (VERIFY round 9.1, class sweep): each dot alone.
            "Version: 1x0.15",
        ):
            with self.subTest(line):
                self.assertEqual(
                    self.malformed(srd.extract, HEAD + line + "\n" + RELEASED + TAIL),
                    f"the first Version: line (line 3) is not a bare X.Y.Z version: {line!r}",
                )
        line = "Version: 1.0.15\u00a0"
        self.assertEqual(
            run((HEAD + line + "\n" + RELEASED + TAIL).encode("utf-8")),
            (1, "", f"skill-release-date: the first Version: line (line 3) is not a bare X.Y.Z version: {line!r}\n"),
        )

    def test_the_version_line_is_the_first_line_that_starts_with_the_key_and_colon(self):
        # Fix round 13 (VERIFY round 9.2, finding 3): a line that starts with
        # "Version" but not "Version:", one that starts with the key in
        # another case, one that holds the key after other text, and one
        # that holds it after a blank are not the Version line, so the
        # Released line after the real one is accepted.
        for lead in ("Versioning notes", "version: 9.9.9", "See Version: 9.9.9", " Version: 9.9.9"):
            with self.subTest(lead):
                text = HEAD + lead + "\n" + VERSION + RELEASED + TAIL
                self.assertEqual(srd.extract(text), "2026-11-15")
                self.assertEqual(run(text.encode("utf-8")), (0, "2026-11-15\n", ""))

    def test_the_released_line_hangs_from_the_first_version_line_not_a_later_one(self):
        # The Version line is the first line that starts with "Version:", so
        # a later Version line does not move the place the Released line
        # must sit: the Released line directly after the first one is
        # accepted.
        text = "Version: 1.0.15\nReleased: 2026-11-15\nVersion: 1.0.16\n"
        self.assertEqual(srd.extract(text), "2026-11-15")
        self.assertEqual(run(text.encode("utf-8")), (0, "2026-11-15\n", ""))


class BuilderCarriesReleasedTest(unittest.TestCase):
    """T2: the portable-text builder copies the meta block, Released included.

    It builds from a throwaway copy of the skill source with a Released line
    inserted after Version, so a future narrowing of the builder meta-block
    selector that dropped the key goes red here."""

    def test_generated_rendering_carries_the_line_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir()
            shutil.copy2(REPO / "tools" / "build-portable-text.py", root / "tools" / "build-portable-text.py")
            shutil.copytree(REPO / "cleanlanguage" / "skills", root / "cleanlanguage" / "skills")
            (root / "site" / "downloads").mkdir(parents=True)
            skill = root / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            lines = text.split("\n")
            index = next(i for i, line in enumerate(lines) if line.startswith("Version:"))
            if not lines[index + 1].startswith("Released:"):
                lines.insert(index + 1, "Released: 2026-11-15  ")
            else:
                lines[index + 1] = "Released: 2026-11-15  "
            version_line = lines[index]
            skill.write_text("\n".join(lines), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-I", str(root / "tools" / "build-portable-text.py")],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("cleanlanguage.md", "cleanlanguage-29k.md"):
                with self.subTest(name):
                    out = (root / "site" / "downloads" / name).read_text(encoding="utf-8")
                    self.assertEqual(out.count("Released:"), 1)
                    self.assertIn(version_line + "\nReleased: 2026-11-15  \nAuthor:", out)
                    self.assertEqual(srd.extract(out), "2026-11-15")


if __name__ == "__main__":
    unittest.main()
