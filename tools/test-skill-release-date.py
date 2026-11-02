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
agreement with the functions and the other modes.

The tests run offline and touch only throwaway directories.
"""

from __future__ import annotations

import importlib.util
import json
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
)

# Decorations outside the rule, which the docstring states are not detected.
UNDETECTED = (
    ("inline code", "`Released: 2026-11-01`"),
    ("HTML tag", "<b>Released:</b> 2026-11-01"),
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
# observe the exit code and the empty stdout of an internal error.
JSON_CRASH_RUNNER = (
    "import builtins, importlib, runpy, sys\n"
    "kind = getattr(builtins, sys.argv[2])\n"
    "def crash(*args, **kwargs):\n"
    "    raise kind(\"injected internal error\")\n"
    "module, name = sys.argv[1].rsplit(\".\", 1)\n"
    "setattr(importlib.import_module(module), name, crash)\n"
    "sys.argv = [sys.argv[3], \"--json\"]\n"
    "runpy.run_path(sys.argv[0], run_name=\"__main__\")\n"
)

# Row 80: the exact usage line of the extractor, --json included.
USAGE_LINE = (
    "skill-release-date: usage: skill-release-date [FILE|-] | --baseline | --requires-date VERSION"
    " | --check-date YYYY-MM-DD | --published-day PUBLISHED_AT"
    " | --publish-window YYYY-MM-DD NOW | --confirm-published YYYY-MM-DD PUBLISHED_AT | --json\n"
)


def request(op: str, arg: str | None = None) -> bytes:
    """Encode a --json request, as the gate does."""
    body = {"op": op} if arg is None else {"op": op, "arg": arg}
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

    def test_released_beside_a_malformed_version_line_is_rejected(self):
        # F12: the Version line value is validated before the placement rule.
        for version in ("Version: draft", "Version: 1.0", "Version: 1.0.15 beta"):
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


class FunctionTest(unittest.TestCase):
    def test_baseline_constant(self):
        self.assertEqual(srd.BASELINE_VERSION, "1.0.14")

    def test_internal_error_exit_constant(self):
        self.assertEqual(srd.INTERNAL_ERROR_EXIT, 6)

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
            ("a list", b"[]", "the request is not a JSON object"),
            ("a string", b"\"extract\"", "the request is not a JSON object"),
            ("unknown op", request("nope", "x"), "the request names no known op: 'nope'"),
            ("op another function of the module", request("parse_date", "2026-11-15"),
             "the request names no known op: 'parse_date'"),
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
        # A version whose last part has more digits than int() converts
        # raises a ValueError that is not a Malformed: exit 6 and an empty
        # stdout, as --requires-date gives for the same version.
        version = "1.0." + "9" * 5000
        with self.subTest("a version past the integer digit limit"):
            code, out, err = run(request("requires_release_date", version), "--json", stdin=True)
            self.assertEqual((code, out), (6, ""), err)
            self.assertTrue(err.startswith("skill-release-date: internal error: ValueError("), err)
            cli_code, cli_out, cli_err = run(None, "--requires-date", version)
            self.assertEqual((cli_code, cli_out, cli_err), (code, out, err))


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
