#!/usr/bin/env python3
"""Tests for check-headers.py.

Each test writes a small ``_headers`` fixture, points the gate at it and runs
``main()``. A good fixture passes; each fault fails with its own message: a
decided header missing, duplicated, set to another value, or set or detached by
another rule, the ``/*`` rule included; the Content-Security-Policy missing or
duplicated; a forbidden header set or detached anywhere; a malformed line; a
line broken by any character but a line feed; a control character, a byte order
mark or whitespace other than the ASCII space; a carriage return at the end of
the file with no line feed after it; a trailing space; an indented URL or path;
a first-column line that is not a URL pattern, such as a header written without
its indent; a header name that is not an HTTP token; invalid UTF-8; and an
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
    "accelerometer=(), autoplay=(), bluetooth=(), browsing-topics=(), camera=(), "
    "display-capture=(), fullscreen=(), geolocation=(), gyroscope=(), hid=(), "
    "magnetometer=(), microphone=(), midi=(), payment=(), serial=(), usb=()"
)
SHARED_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://ajax.cloudflare.com https://static"
    ".cloudflareinsights.com; connect-src 'self' https://cloudflareinsights.com; style-src 'self'; fo"
    "nt-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
DECIDED = {
    "X-Frame-Options": "DENY",
    "Permissions-Policy": PERMISSIONS,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": SHARED_CSP,
}
ONCE = list(DECIDED)
FORBIDDEN = ["X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security"]
GOOD_LINES = [
    "/*",
    "  X-Frame-Options: DENY",
    f"  Permissions-Policy: {PERMISSIONS}",
    "  Cross-Origin-Opener-Policy: same-origin",
    f"  Content-Security-Policy: {SHARED_CSP}",
    "",
    "/downloads/cleanlanguage.md",
    '  Content-Disposition: attachment; filename="cleanlanguage.md"',
    "  X-Robots-Tag: noindex",
    "",
    "/sitemap.xml",
    "  Cache-Control: public, max-age=3600",
]


DRAFT_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://ajax.cloudflare.com "
    "https://static.cloudflareinsights.com; connect-src 'self' https://cloudflareinsights.com; "
    "style-src 'self'; font-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
DRAFT_LINES = [
    "",
    "/draft/*",
    "  ! Content-Security-Policy",
    f"  Content-Security-Policy: {DRAFT_CSP}",
    "  X-Robots-Tag: noindex",
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

    def test_site_wide_policy_wider_than_the_shared_policy_fails(self):
        for value in (SHARED_CSP + "; worker-src *", SHARED_CSP.replace("default-src 'none'", "default-src 'self'"),
                      SHARED_CSP.replace("img-src 'self'", "img-src 'self' data:"),
                      "default-src 'self'; style-src 'self'; script-src 'self'"):
            with self.subTest(value=value):
                lines = self.replace(f"  Content-Security-Policy: {SHARED_CSP}", f"  Content-Security-Policy: {value}")
                self.expect_fail(lines, "the decided value is")

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
        for line in ("  https://cleanlanguage.ai/nothing", "  /nothing", "  http://:host/*",
                     "  ftp://cleanlanguage.ai/", "  git+ssh://host/x", "  a.b-c://host/x",
                     "  Z9://host/x"):
            with self.subTest(line=line):
                lines = list(GOOD_LINES)
                lines.insert(3, line)
                self.expect_fail(lines, "line 4: an indented line looks like a URL or a path",
                                 code=3)

    def test_a_set_line_that_starts_with_a_bang_fails_closed(self):
        for line in ("  !X-Frame-Options: SAMEORIGIN", "  !!X-Frame-Options: DENY"):
            with self.subTest(line=line):
                lines = list(GOOD_LINES)
                lines.insert(3, line)
                self.expect_fail(lines, "line 4: a line that starts with '!' must be a detach",
                                 code=3)
        lines = list(GOOD_LINES)
        lines.insert(3, "  ! X-Frame-Options: DENY")
        self.expect_fail(lines, "line 4: not a 'Name: value' or '! Name' line", code=3)

    def test_a_detach_of_a_name_that_starts_with_a_bang_fails_closed(self):
        for line in ("  !!X-Frame-Options", "  ! !Strict-Transport-Security",
                     "  !!Cross-Origin-Opener-Policy"):
            with self.subTest(line=line):
                lines = list(GOOD_LINES)
                lines.insert(3, line)
                self.expect_fail(lines, "line 4: a detached header name starts with '!'",
                                 code=3)

    def test_header_in_first_column_fails_closed(self):
        cases = (
            (5, "Strict-Transport-Security: max-age=0", 6),
            (9, "X-Frame-Options: SAMEORIGIN", 10),
            (5, "! X-Frame-Options", 6),
            (12, "X-Content-Type-Options: nosniff", 13),
        )
        for where, line, number in cases:
            with self.subTest(line=line):
                fixture = list(GOOD_LINES)
                fixture.insert(where, line)
                code, text = self.run_gate(fixture)
                self.assertEqual(code, 3, text)
                self.assertEqual(
                    text,
                    f"check-headers: site/_headers line {number}: a first-column line is not a URL "
                    f"pattern: {line!r}; a URL pattern is a path that starts with '/' or a URL "
                    "that starts with 'https://', with no space, and a header line is indented\n")

    def test_first_column_line_outside_the_pattern_forms_fails_closed(self):
        for line in ("http://cleanlanguage.ai/*", "https://", "cleanlanguage.ai/*",
                     "/downloads/* X-Frame-Options: DENY", "https://:host/ *", "*"):
            with self.subTest(line=line):
                lines = GOOD_LINES + [line, "  Cache-Control: no-store"]
                self.expect_fail(lines, f"line 13: a first-column line is not a URL pattern: "
                                        f"{line!r}", code=3)

    def test_url_patterns_pass(self):
        for line in ("/", "/downloads/*", "/:splat", "https://:project.pages.dev/*",
                     "https://cleanlanguage.ai/sitemap.xml"):
            with self.subTest(line=line):
                code, text = self.run_gate(GOOD_LINES + [line, "  Cache-Control: no-store"])
                self.assertEqual(code, 0, text)
                self.assertEqual(text, (
                    "site/_headers sets X-Frame-Options, Permissions-Policy, "
                    "Cross-Origin-Opener-Policy and Content-Security-Policy exactly once, in "
                    "the /* rule, with the decided values, and carries no "
                    "X-Content-Type-Options, Referrer-Policy or Strict-Transport-Security "
                    "line.\n"))

    def test_first_column_comment_is_skipped(self):
        lines = list(GOOD_LINES)
        lines.insert(0, "# Strict-Transport-Security: max-age=0")
        code, text = self.run_gate(lines)
        self.assertEqual(code, 0, text)

    def test_carriage_return_at_end_without_line_feed_fails_closed(self):
        for data, number in ((("\n".join(GOOD_LINES) + "\r"), 12),
                             (("\r\n".join(GOOD_LINES) + "\r\n\r"), 13)):
            with self.subTest(data=data[-6:]):
                code, text = self.run_bytes(data.encode("utf-8"))
                self.assertEqual(code, 3, text)
                self.assertEqual(
                    text,
                    f"check-headers: site/_headers line {number}: holds the control character "
                    "U+000D; a line may end only in a line feed, with at most one carriage "
                    "return before it\n")

    def test_no_final_line_feed_passes(self):
        code, text = self.run_bytes("\n".join(GOOD_LINES).encode("utf-8"))
        self.assertEqual(code, 0, text)

    def test_every_tchar_in_a_header_name_passes(self):
        name = "A!#$%&'*+.^_`|~09az-Z"
        for line in (f"  {name}: x", f"  ! {name}"):
            with self.subTest(line=line):
                code, text = self.run_gate(GOOD_LINES + [line])
                self.assertEqual(code, 0, text)

    def test_header_name_must_be_token(self):
        for line in ("  X-Frame(Options): DENY", "  X-Frame/Options: DENY",
                     "  X-Frame-Opt\u200bions: DENY", "  X-Frame-Options : DENY",
                     "  X-Fr\u00e9me-Options: DENY"):
            with self.subTest(line=line):
                lines = self.replace("  X-Frame-Options: DENY", line)
                self.expect_fail(lines, "line 2: not a 'Name: value' or '! Name' line", code=3)

    def test_each_delimiter_in_a_header_name_fails_closed(self):
        for char in '"(),/;<=>?@[\\]{} ':
            with self.subTest(char=char):
                lines = GOOD_LINES + [f"  X-Robots{char}Tag: noindex"]
                self.expect_fail(lines, "line 13: not a 'Name: value' or '! Name' line", code=3)
        for char in '"(),/:;<=>?@[\\]{}':
            with self.subTest(char=char, detach=True):
                lines = GOOD_LINES + [f"  ! X-Robots{char}Tag"]
                self.expect_fail(lines, "line 13: not a 'Name: value' or '! Name' line", code=3)

    def test_repository_headers_pass(self):
        gate.HEADERS = self._saved
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main()
        self.assertEqual(code, 0, out.getvalue())

    # Boundaries of the first-column and bang rules: the https:// scheme is
    # matched in lower case only, and the bang rule tests the whole line, so a
    # lone '!' as the name is still a set line that starts with '!'.

    def test_first_column_url_with_an_upper_case_scheme_fails_closed(self):
        for line in ("HTTPS://cleanlanguage.ai/*", "Https://cleanlanguage.ai/*"):
            with self.subTest(line=line):
                code, text = self.run_gate(GOOD_LINES + [line, "  Cache-Control: no-store"])
                self.assertEqual(code, 3, text)
                self.assertEqual(
                    text,
                    f"check-headers: site/_headers line 13: a first-column line is not a URL "
                    f"pattern: {line!r}; a URL pattern is a path that starts with '/' or a URL "
                    "that starts with 'https://', with no space, and a header line is indented\n")

    def test_a_set_line_whose_name_is_a_lone_bang_fails_closed(self):
        code, text = self.run_gate(GOOD_LINES + ["  !: x"])
        self.assertEqual(code, 3, text)
        self.assertEqual(
            text,
            "check-headers: site/_headers line 13: a line that starts with '!' must be a detach, "
            "'! Name' alone, not a header to set: '!: x'\n")


class DraftRuleTest(unittest.TestCase):
    """Check 5: exactly the staged draft's /draft/* rule is accepted, and nothing wider."""

    # The fixture helpers of HeadersGateTest, borrowed without inheriting its tests.
    setUp = HeadersGateTest.setUp
    tearDown = HeadersGateTest.tearDown
    run_gate = HeadersGateTest.run_gate
    run_bytes = HeadersGateTest.run_bytes
    expect_fail = HeadersGateTest.expect_fail

    def with_draft(self, draft):
        return GOOD_LINES + draft

    def test_exact_draft_rule_passes(self):
        code, text = self.run_gate(self.with_draft(DRAFT_LINES))
        self.assertEqual(code, 0, text)

    def test_draft_rule_header_names_compare_without_case(self):
        lines = [line.replace("Content-Security-Policy", "content-security-policy") for line in DRAFT_LINES]
        code, text = self.run_gate(self.with_draft(lines))
        self.assertEqual(code, 0, text)

    def test_draft_policy_with_another_value_fails(self):
        for value in (DRAFT_CSP + "; worker-src *", DRAFT_CSP.replace("'unsafe-inline' ", "'unsafe-inline' 'unsafe-eval' "),
                      DRAFT_CSP.replace("default-src 'none'", "default-src *")):
            with self.subTest(value=value):
                lines = list(DRAFT_LINES)
                lines[3] = f"  Content-Security-Policy: {value}"
                self.expect_fail(self.with_draft(lines), "the /draft/* rule")

    def test_draft_policy_without_detach_fails(self):
        lines = [line for line in DRAFT_LINES if "!" not in line]
        self.expect_fail(self.with_draft(lines), "the /draft/* rule")

    def test_detach_after_draft_policy_fails(self):
        lines = list(DRAFT_LINES)
        lines[2], lines[3] = lines[3], lines[2]
        self.expect_fail(self.with_draft(lines), "the /draft/* rule")

    def test_draft_rule_without_noindex_fails(self):
        self.expect_fail(self.with_draft(DRAFT_LINES[:-1]), "the /draft/* rule")

    def test_draft_rule_with_another_header_fails(self):
        for extra in ("  Cache-Control: no-store", "  X-Frame-Options: DENY", "  ! X-Frame-Options", "  Referrer-Policy: no-referrer"):
            with self.subTest(extra=extra):
                self.expect_fail(self.with_draft(DRAFT_LINES + [extra]), "the /draft/* rule")

    def test_draft_rule_repeated_fails(self):
        self.expect_fail(self.with_draft(DRAFT_LINES + DRAFT_LINES), "the /draft/* rule")

    def test_detach_alone_fails(self):
        self.expect_fail(self.with_draft(DRAFT_LINES[:3]), "the /draft/* rule")

    def test_same_lines_under_another_pattern_fail(self):
        for pattern in ("/draft/", "/draft/assets/*", "/preview/*"):
            with self.subTest(pattern=pattern):
                lines = list(DRAFT_LINES)
                lines[1] = pattern
                self.expect_fail(self.with_draft(lines), f"{pattern} detaches Content-Security-Policy; only one set line")

    def test_noindex_detached_under_draft_fails(self):
        # The review's mutant M9.
        self.expect_fail(self.with_draft(DRAFT_LINES + ["", "/draft/install/*", "  ! X-Robots-Tag"]),
                         "/draft/install/* detaches X-Robots-Tag")

    def test_noindex_detached_anywhere_fails(self):
        for pattern in ("/*", "/sitemap.xml", "https://cleanlanguage.ai/*"):
            with self.subTest(pattern=pattern):
                self.expect_fail(self.with_draft(DRAFT_LINES + ["", pattern, "  ! X-Robots-Tag"]), "detaches X-Robots-Tag")

    def test_noindex_changed_where_the_draft_is_served_fails(self):
        # "/" and a path-less full URL pin the root case of reaches_draft (path == "/").
        for pattern in ("/draft/install/*", "/draft/", "/*", "/:page/*", "https://cleanlanguage.ai/draft/*",
                        "/", "https://cleanlanguage.ai"):
            with self.subTest(pattern=pattern):
                self.expect_fail(self.with_draft(DRAFT_LINES + ["", pattern, "  X-Robots-Tag: all"]),
                                 "sets X-Robots-Tag where the draft is served")

    def test_noindex_changed_under_a_draft_pattern_in_another_case_fails(self):
        # Whether Pages matches patterns case-sensitively is not established, so /Draft/ counts as the draft.
        for pattern in ("/Draft/*", "/DRAFT/install/*", "https://cleanlanguage.ai/Draft/*"):
            with self.subTest(pattern=pattern):
                self.expect_fail(self.with_draft(DRAFT_LINES + ["", pattern, "  X-Robots-Tag: all"]),
                                 "sets X-Robots-Tag where the draft is served")

    def test_noindex_changed_under_a_mid_segment_splat_or_placeholder_fails(self):
        # A * or : anywhere in the first segment counts as reaching the draft (fail closed).
        for pattern in ("/d:x/*", "/dr*", "/x*y/install/*"):
            with self.subTest(pattern=pattern):
                self.expect_fail(self.with_draft(DRAFT_LINES + ["", pattern, "  X-Robots-Tag: all"]),
                                 "sets X-Robots-Tag where the draft is served")

    def test_noindex_on_other_paths_passes(self):
        # The download files' own noindex (GOOD_LINES) and another live path stay allowed.
        code, text = self.run_gate(self.with_draft(DRAFT_LINES + ["", "/sitemap-old.xml", "  X-Robots-Tag: noindex"]))
        self.assertEqual(code, 0, text)

    def test_draft_rule_does_not_relax_the_site_wide_rule(self):
        csp = next(line for line in GOOD_LINES if "Content-Security-Policy" in line)
        lines = [line for line in GOOD_LINES if line != csp] + DRAFT_LINES
        self.expect_fail(lines, "the /* rule sets Content-Security-Policy 0 times")


if __name__ == "__main__":
    unittest.main()
