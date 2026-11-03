#!/usr/bin/env python3
"""Tests for check-headers.py.

Each test writes a small ``_headers`` fixture, points the gate at it and runs
``main()``. A good fixture passes; each fault fails with its own message: a
decided header missing, duplicated, set to another value, or set or detached by
another rule, the ``/*`` rule included; the Content-Security-Policy missing or
duplicated; a forbidden header set or detached anywhere; a malformed line; a
line broken by any character but a line feed; a control character, a byte order
mark or whitespace other than the ASCII space; a trailing space; an indented URL
or path; a header name that is not an HTTP token; invalid UTF-8; and an
unreadable file. The last test runs the gate on the repository's own
``site/_headers``. The tests run offline with the standard library.
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
        return self.run_bytes(("\n".join(lines) + "\n").encode("utf-8"))

    def run_bytes(self, data):
        gate.HEADERS.write_bytes(data)
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

    def test_each_once_header_detached_in_all_paths_rule_fails(self):
        for name in ONCE:
            with self.subTest(name=name):
                lines = list(GOOD_LINES)
                lines.insert(5, f"  ! {name}")
                self.expect_fail(lines, f"line 6: /* detaches {name}; only one set line")
                _, text = self.run_gate(lines)
                self.assertNotIn(f"sets {name} 2 times", text)

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

    def test_line_breaks_only_at_line_feed(self):
        for sep in ("\f", "\v", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
            with self.subTest(sep=f"U+{ord(sep):04X}"):
                lines = self.without("  X-Frame-Options: DENY")
                where = lines.index("  Cross-Origin-Opener-Policy: same-origin")
                lines[where] += sep + "  X-Frame-Options: DENY"
                self.expect_fail(lines, "site/_headers line 3: holds the", code=3)
                self.expect_fail(lines, f"U+{ord(sep):04X}", code=3)
                if sep in ("\u2028", "\u2029"):
                    self.expect_fail(lines, "line or paragraph separator", code=3)

    def test_other_control_characters_fail_closed(self):
        cases = {
            "\tX-Frame-Options: DENY": "U+0009",
            "  X-Frame-Options:\tDENY": "U+0009",
            "  X-Frame-Options: DENY\x00": "U+0000",
            "  X-Frame-Options: DE\rNY": "U+000D",
            "  X-Frame-Options: DENY\x7f": "U+007F",
        }
        for line, code in cases.items():
            with self.subTest(code=code, line=line):
                lines = self.replace("  X-Frame-Options: DENY", line)
                self.expect_fail(lines, f"line 2: holds the control character {code}", code=3)

    def test_crlf_line_ends_pass(self):
        code, text = self.run_bytes(("\r\n".join(GOOD_LINES) + "\r\n").encode("utf-8"))
        self.assertEqual(code, 0, text)

    def test_carriage_return_other_than_one_before_line_feed_fails_closed(self):
        for line in ("  X-Frame-Options: DE\rNY", "  X-Frame-Options: DENY\r"):
            with self.subTest(line=line):
                lines = self.replace("  X-Frame-Options: DENY", line)
                data = ("\r\n".join(lines) + "\r\n").encode("utf-8")
                code, text = self.run_bytes(data)
                self.assertEqual(code, 3, text)
                self.assertIn("line 2: holds the control character U+000D", text)

    def test_indented_comment_is_skipped(self):
        lines = list(GOOD_LINES)
        lines.insert(2, "  # X-Content-Type-Options: nosniff")
        code, text = self.run_gate(lines)
        self.assertEqual(code, 0, text)

    def test_byte_order_mark_fails_closed(self):
        data = ("\ufeff" + "\n".join(GOOD_LINES) + "\n").encode("utf-8")
        code, text = self.run_bytes(data)
        self.assertEqual(code, 3, text)
        self.assertIn("site/_headers line 1: holds a byte order mark (U+FEFF)", text)

    def test_invalid_utf8_fails_closed(self):
        data = b"# \xff\n" + ("\n".join(GOOD_LINES) + "\n").encode("utf-8")
        code, text = self.run_bytes(data)
        self.assertEqual(code, 3, text)
        self.assertIn("site/_headers could not be read", text)

    def test_whitespace_other_than_ascii_space_fails_closed(self):
        for char in ("\u00a0", "\u2003", "\u3000"):
            with self.subTest(char=f"U+{ord(char):04X}"):
                lines = self.replace("  X-Frame-Options: DENY", "  X-Frame-Options: DENY" + char)
                self.expect_fail(
                    lines, f"line 2: holds the whitespace character U+{ord(char):04X}", code=3)

    def test_trailing_space_fails_closed(self):
        for old, new, number in (("/*", "/* ", 1),
                                 ("  X-Frame-Options: DENY", "  X-Frame-Options: DENY ", 2),
                                 ("", "  ", 6)):
            with self.subTest(line=new):
                self.expect_fail(self.replace(old, new), f"line {number}: ends in a space", code=3)

    def test_spaces_after_colon_pass(self):
        for line in ("  X-Frame-Options:DENY", "  X-Frame-Options:   DENY", "    X-Frame-Options: DENY"):
            with self.subTest(line=line):
                code, text = self.run_gate(self.replace("  X-Frame-Options: DENY", line))
                self.assertEqual(code, 0, text)

    def test_url_or_path_under_rule_fails_closed(self):
        for line in ("  https://cleanlanguage.ai/nothing", "  /nothing", "  http://:host/*"):
            with self.subTest(line=line):
                lines = list(GOOD_LINES)
                lines.insert(3, line)
                self.expect_fail(lines, "line 4: an indented line looks like a URL or a path",
                                 code=3)

    def test_header_name_must_be_token(self):
        for line in ("  X-Frame(Options): DENY", "  X-Frame/Options: DENY",
                     "  X-Frame-Opt\u200bions: DENY", "  X-Frame-Options : DENY"):
            with self.subTest(line=line):
                lines = self.replace("  X-Frame-Options: DENY", line)
                self.expect_fail(lines, "line 2: not a 'Name: value' or '! Name' line", code=3)

    def test_repository_headers_pass(self):
        gate.HEADERS = self._saved
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main()
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
