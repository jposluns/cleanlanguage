#!/usr/bin/env python3
"""Tests for tools/skill-release-date.py, the strict Released-line extractor.

Item 26 adds a ``Released: YYYY-MM-DD`` meta line directly after the
``Version:`` line of the skill and its portable renderings. Every gate reads it
through one extractor, so these tests pin that extractor grammar: the first
line carrying the key is authoritative, the value is a real calendar date, the
line sits directly after the first ``Version:`` line, a duplicate is rejected,
and absence (exit 3) is distinct from malformed (exit 1). They also pin the one
function that interprets a release ``published_at`` value, and (T2) that the
portable-text builder carries the line into the generated rendering.

The tests run offline and touch only throwaway directories.
"""

from __future__ import annotations

import importlib.util
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
            ("2026-11-15T23:59:59Z", "only 1 seconds remain"),
            ("2026-11-16T00:00:05Z", "the UTC day is now 2026-11-16"),
            ("2026-11-14T12:00:00Z", "the UTC day is now 2026-11-14"),
        ):
            with self.subTest(now):
                code, out, err = run(None, "--publish-window", "2026-11-15", now)
                self.assertEqual((code, out), (5, ""), err)
                self.assertIn(fragment, err)
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

    def test_published_day_function(self):
        self.assertEqual(srd.release_day_from_published_at("2026-11-15T00:00:00Z"), "2026-11-15")
        for value in (None, "null", "2026-11-15T00:00:00"):
            with self.subTest(value):
                with self.assertRaises(srd.Malformed):
                    srd.release_day_from_published_at(value)


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
