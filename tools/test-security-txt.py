#!/usr/bin/env python3
"""Tests for check-security-txt.py.

Each test writes a small ``security.txt`` fixture, points the gate at it and
runs ``main()`` at a fixed time. A good fixture passes; each fault fails with
its own message: each decided field missing, duplicated or set to another
value; a field that was not decided; an expired file, against a fixed time and
against the clock; a malformed line; a line broken by any character but a line
feed; a control character, a byte order mark or whitespace other than the ASCII
space; a leading or trailing space or a second space after the colon; invalid
UTF-8; and an unreadable file. The last test runs the gate on the repository's
own file. The tests run offline with the standard library.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-security-txt.py"
spec = importlib.util.spec_from_file_location("check_security_txt", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

DECIDED = {
    "Contact": "mailto:jeff@posluns.ca",
    "Expires": "2030-10-31T00:00:00Z",
    "Encryption": "https://posluns.ca/security/pgp-key.txt",
    "Policy": "https://posluns.ca/security/",
    "Preferred-Languages": "en, fr",
    "Canonical": "https://cleanlanguage.ai/.well-known/security.txt",
}
GOOD_LINES = [
    "# Security contact for cleanlanguage.ai",
    "Contact: mailto:jeff@posluns.ca",
    "Expires: 2030-10-31T00:00:00Z",
    "Encryption: https://posluns.ca/security/pgp-key.txt",
    "Policy: https://posluns.ca/security/",
    "Preferred-Languages: en, fr",
    "Canonical: https://cleanlanguage.ai/.well-known/security.txt",
]
BEFORE = datetime(2026, 11, 3, tzinfo=timezone.utc)
AT_EXPIRY = datetime(2030, 10, 31, tzinfo=timezone.utc)


class SecurityTxtGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = gate.SECURITY_TXT
        gate.SECURITY_TXT = Path(self._tmp.name) / "security.txt"

    def tearDown(self):
        gate.SECURITY_TXT = self._saved
        self._tmp.cleanup()

    def run_gate(self, lines, now=BEFORE):
        return self.run_bytes(("\n".join(lines) + "\n").encode("utf-8"), now)

    def run_bytes(self, data, now=BEFORE):
        gate.SECURITY_TXT.write_bytes(data)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = gate.main(now)
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue() + err.getvalue()

    def expect_fail(self, lines, needle, code=1, now=BEFORE):
        got, text = self.run_gate(lines, now)
        self.assertEqual(got, code, text)
        self.assertIn(needle, text)

    def test_good_fixture_passes(self):
        code, text = self.run_gate(GOOD_LINES)
        self.assertEqual(code, 0, text)

    def test_names_compare_without_case(self):
        lines = [line.replace("Contact:", "contact:") for line in GOOD_LINES]
        code, text = self.run_gate(lines)
        self.assertEqual(code, 0, text)

    def test_each_field_missing_fails(self):
        for name, value in DECIDED.items():
            with self.subTest(name=name):
                lines = [line for line in GOOD_LINES if line != f"{name}: {value}"]
                self.expect_fail(lines, f"{name} appears 0 times")

    def test_each_field_duplicated_fails(self):
        for name, value in DECIDED.items():
            with self.subTest(name=name):
                self.expect_fail(GOOD_LINES + [f"{name}: {value}"], f"{name} appears 2 times")

    def test_each_field_with_another_value_fails(self):
        for name, value in DECIDED.items():
            with self.subTest(name=name):
                lines = [line if line != f"{name}: {value}" else f"{name}: {value}x"
                         for line in GOOD_LINES]
                self.expect_fail(lines, f"the decided value is {value!r}")

    def test_field_not_decided_fails(self):
        self.expect_fail(GOOD_LINES + ["Hiring: https://example.com/"],
                         "Hiring is not a decided field")

    def test_expired_file_fails(self):
        self.expect_fail(GOOD_LINES, "is not later than now", now=AT_EXPIRY)

    def test_default_clock_is_read(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2030, 10, 31, 0, 0, 1, tzinfo=timezone.utc)

        saved = gate.datetime
        gate.datetime = Clock
        try:
            self.expect_fail(GOOD_LINES, "is not later than now (2030-10-31T00:00:01Z)", now=None)
        finally:
            gate.datetime = saved

    def test_past_expiry_fails_against_the_real_clock(self):
        saved = dict(gate.DECIDED)
        gate.DECIDED["Expires"] = "2001-01-01T00:00:00Z"
        try:
            lines = [line if not line.startswith("Expires:") else "Expires: 2001-01-01T00:00:00Z"
                     for line in GOOD_LINES]
            self.expect_fail(lines, "Expires 2001-01-01T00:00:00Z is not later than now", now=None)
        finally:
            gate.DECIDED.clear()
            gate.DECIDED.update(saved)

    def test_malformed_line_fails_closed(self):
        self.expect_fail(GOOD_LINES + ["Contact mailto:jeff@posluns.ca"],
                         "not a 'Field: value' line", code=3)

    def test_unreadable_file_fails_closed(self):
        gate.SECURITY_TXT.mkdir()
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as stop:
                gate.main(BEFORE)
        self.assertEqual(stop.exception.code, 3)
        self.assertIn("could not be read", err.getvalue())

    def test_line_breaks_only_at_line_feed(self):
        for sep in ("\f", "\v", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
            with self.subTest(sep=f"U+{ord(sep):04X}"):
                lines = [line for line in GOOD_LINES if not line.startswith("Preferred-Languages:")]
                where = lines.index("Policy: https://posluns.ca/security/")
                lines[where] += sep + "Preferred-Languages: en, fr"
                self.expect_fail(lines, "security.txt line 5: holds the", code=3)
                self.expect_fail(lines, f"U+{ord(sep):04X}", code=3)
                if sep in ("\u2028", "\u2029"):
                    self.expect_fail(lines, "line or paragraph separator", code=3)

    def test_other_control_characters_fail_closed(self):
        cases = {
            "Contact:\tmailto:jeff@posluns.ca": "U+0009",
            "Contact: mailto:jeff@posluns.ca\x00": "U+0000",
            "Contact: mailto:jeff@\rposluns.ca": "U+000D",
            "Contact: mailto:jeff@posluns.ca\x7f": "U+007F",
        }
        for line, code in cases.items():
            with self.subTest(code=code, line=line):
                lines = [line if old.startswith("Contact:") else old for old in GOOD_LINES]
                self.expect_fail(lines, f"line 2: holds the control character {code}", code=3)

    def test_crlf_line_ends_pass(self):
        code, text = self.run_bytes(("\r\n".join(GOOD_LINES) + "\r\n").encode("utf-8"))
        self.assertEqual(code, 0, text)

    def test_carriage_return_other_than_one_before_line_feed_fails_closed(self):
        for line in ("Contact: mailto:jeff@\rposluns.ca", "Contact: mailto:jeff@posluns.ca\r"):
            with self.subTest(line=line):
                lines = [line if old.startswith("Contact:") else old for old in GOOD_LINES]
                data = ("\r\n".join(lines) + "\r\n").encode("utf-8")
                code, text = self.run_bytes(data)
                self.assertEqual(code, 3, text)
                self.assertIn("line 2: holds the control character U+000D", text)

    def test_no_final_line_feed_passes(self):
        code, text = self.run_bytes("\n".join(GOOD_LINES).encode("utf-8"))
        self.assertEqual(code, 0, text)

    def test_byte_order_mark_fails_closed(self):
        data = ("\ufeff" + "\n".join(GOOD_LINES) + "\n").encode("utf-8")
        code, text = self.run_bytes(data)
        self.assertEqual(code, 3, text)
        self.assertIn("security.txt line 1: holds a byte order mark (U+FEFF)", text)

    def test_invalid_utf8_fails_closed(self):
        data = b"# \xff\n" + ("\n".join(GOOD_LINES) + "\n").encode("utf-8")
        code, text = self.run_bytes(data)
        self.assertEqual(code, 3, text)
        self.assertIn("security.txt could not be read", text)

    def test_whitespace_other_than_ascii_space_fails_closed(self):
        for char in ("\u00a0", "\u2003", "\u3000"):
            with self.subTest(char=f"U+{ord(char):04X}"):
                lines = [line + char if line.startswith("Preferred-Languages:") else line
                         for line in GOOD_LINES]
                self.expect_fail(
                    lines, f"line 6: holds the whitespace character U+{ord(char):04X}", code=3)

    def test_spacing_outside_the_rfc_form_fails_closed(self):
        cases = (
            ("   Contact: mailto:jeff@posluns.ca", "line 2: starts with a space"),
            (" # comment", "line 2: starts with a space"),
            ("Contact: mailto:jeff@posluns.ca ", "line 2: ends in a space"),
            ("Contact:  mailto:jeff@posluns.ca", "line 2: more than one space after the colon"),
        )
        for line, needle in cases:
            with self.subTest(line=line):
                lines = [line if old.startswith("Contact:") else old for old in GOOD_LINES]
                self.expect_fail(lines, needle, code=3)

    def test_no_space_after_colon_passes(self):
        lines = [line.replace(": ", ":", 1) if not line.startswith("#") else line
                 for line in GOOD_LINES]
        code, text = self.run_gate(lines)
        self.assertEqual(code, 0, text)

    def test_repository_file_passes(self):
        gate.SECURITY_TXT = self._saved
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main()
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
