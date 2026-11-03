#!/usr/bin/env python3
"""Tests for check-security-txt.py.

Each test writes a small ``security.txt`` fixture, points the gate at it and
runs ``main()`` at a fixed time. A good fixture passes; each fault fails with
its own message: each decided field missing, duplicated or set to another
value; a field that was not decided; an expired file; a malformed line; and an
unreadable file. The last test runs the gate on the repository's own file. The
tests run offline with the standard library.
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
        gate.SECURITY_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
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

    def test_repository_file_passes(self):
        gate.SECURITY_TXT = self._saved
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main()
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
