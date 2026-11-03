#!/usr/bin/env python3
"""Tests for check-headers.py.

Each test writes a small ``_headers`` fixture, points the gate at it and runs
``main()``. A good fixture passes; each fault fails with its own message: a
decided header missing, duplicated, set to another value, or set or detached by
another rule; the Content-Security-Policy missing or duplicated; a forbidden
header set or detached anywhere; a malformed line; and an unreadable file. The
last test runs the gate on the repository's own ``site/_headers``. The tests run
offline with the standard library.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-headers.py"
spec = importlib.util.spec_from_file_location("check_headers", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

PERMISSIONS = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), fullscreen=(), "
    "geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
)
DECIDED = {
    "X-Frame-Options": "DENY",
    "Permissions-Policy": PERMISSIONS,
    "Cross-Origin-Opener-Policy": "same-origin",
}
ONCE = list(DECIDED) + ["Content-Security-Policy"]
FORBIDDEN = ["X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security"]
GOOD_LINES = [
    "/*",
    "  X-Frame-Options: DENY",
    f"  Permissions-Policy: {PERMISSIONS}",
    "  Cross-Origin-Opener-Policy: same-origin",
    "  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'",
    "",
    "/downloads/cleanlanguage.md",
    '  Content-Disposition: attachment; filename="cleanlanguage.md"',
    "  X-Robots-Tag: noindex",
    "",
    "/sitemap.xml",
    "  Cache-Control: public, max-age=3600",
]


class HeadersGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = gate.HEADERS
        gate.HEADERS = Path(self._tmp.name) / "_headers"

    def tearDown(self):
        gate.HEADERS = self._saved
        self._tmp.cleanup()

    def run_gate(self, lines):
        gate.HEADERS.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = gate.main()
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue() + err.getvalue()

    def expect_fail(self, lines, needle, code=1):
        got, text = self.run_gate(lines)
        self.assertEqual(got, code, text)
        self.assertIn(needle, text)

    def replace(self, old, new):
        lines = list(GOOD_LINES)
        lines[lines.index(old)] = new
        return lines

    def without(self, old):
        lines = list(GOOD_LINES)
        lines.remove(old)
        return lines

    def test_good_fixture_passes(self):
        code, text = self.run_gate(GOOD_LINES)
        self.assertEqual(code, 0, text)

    def test_names_compare_without_case(self):
        lines = self.replace("  X-Frame-Options: DENY", "  x-frame-options: DENY")
        code, text = self.run_gate(lines)
        self.assertEqual(code, 0, text)

    def test_each_decided_header_missing_fails(self):
        for name, value in DECIDED.items():
            with self.subTest(name=name):
                self.expect_fail(self.without(f"  {name}: {value}"),
                                 f"the /* rule sets {name} 0 times")

    def test_each_decided_header_duplicated_fails(self):
        for name, value in DECIDED.items():
            with self.subTest(name=name):
                lines = list(GOOD_LINES)
                lines.insert(1, f"  {name}: {value}")
                self.expect_fail(lines, f"the /* rule sets {name} 2 times")

    def test_each_decided_header_with_another_value_fails(self):
        for name, value in DECIDED.items():
            with self.subTest(name=name):
                lines = self.replace(f"  {name}: {value}", f"  {name}: {value}x")
                self.expect_fail(lines, f"the decided value is {value!r}")

    def test_permissions_policy_missing_one_feature_fails(self):
        lines = self.replace(f"  Permissions-Policy: {PERMISSIONS}",
                             "  Permissions-Policy: " + PERMISSIONS.replace(", usb=()", ""))
        self.expect_fail(lines, "Permissions-Policy is")

    def test_each_once_header_set_in_another_rule_fails(self):
        for name in ONCE:
            with self.subTest(name=name):
                lines = GOOD_LINES + [f"  {name}: SAMEORIGIN"]
                self.expect_fail(lines, f"/sitemap.xml sets {name}; only one set line")

    def test_each_once_header_detached_in_another_rule_fails(self):
        for name in ONCE:
            with self.subTest(name=name):
                lines = GOOD_LINES + [f"  ! {name}"]
                self.expect_fail(lines, f"/sitemap.xml detaches {name}; only one set line")

    def test_csp_missing_fails(self):
        csp = next(line for line in GOOD_LINES if "Content-Security-Policy" in line)
        self.expect_fail(self.without(csp), "the /* rule sets Content-Security-Policy 0 times")

    def test_csp_duplicated_fails(self):
        lines = list(GOOD_LINES)
        lines.insert(1, "  Content-Security-Policy: default-src 'none'")
        self.expect_fail(lines, "the /* rule sets Content-Security-Policy 2 times")

    def test_each_forbidden_header_set_fails(self):
        for name in FORBIDDEN:
            for where in (1, len(GOOD_LINES)):
                with self.subTest(name=name, line=where):
                    lines = list(GOOD_LINES)
                    lines.insert(where, f"  {name.lower()}: x")
                    self.expect_fail(lines, f"sets {name.lower()}, which must not appear")

    def test_each_forbidden_header_detached_fails(self):
        for name in FORBIDDEN:
            with self.subTest(name=name):
                lines = list(GOOD_LINES)
                lines.insert(1, f"  ! {name}")
                self.expect_fail(lines, f"detaches {name}, which must not appear")

    def test_malformed_line_fails_closed(self):
        lines = list(GOOD_LINES)
        lines.insert(1, "  X-Frame-Options DENY")
        self.expect_fail(lines, "not a 'Name: value' or '! Name' line", code=3)

    def test_header_before_pattern_fails_closed(self):
        self.expect_fail(["  X-Frame-Options: DENY"] + GOOD_LINES,
                         "comes before any URL pattern", code=3)

    def test_unreadable_file_fails_closed(self):
        gate.HEADERS.mkdir()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as stop:
                gate.main()
        self.assertEqual(stop.exception.code, 3)
        self.assertIn("could not be read", err.getvalue())

    def test_repository_headers_pass(self):
        gate.HEADERS = self._saved
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main()
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
