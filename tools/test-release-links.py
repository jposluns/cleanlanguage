#!/usr/bin/env python3
"""Tests for check-release-links.py, and for the bare file names set-release-links.py writes.

The gate reads the current version from the first ``Version:`` line of
``cleanlanguage/skills/cleanlanguage/SKILL.md``. These tests pin the gate's failure paths: the version parse (a malformed,
missing, or unreadable SKILL, which fails before the site walk), and the
fail-closed reads of scanned site files, ``site/_redirects``, and the verify
page (which build a small site fixture). They also pin the bare file-name
rule on both sides: the gate fails on a stale version-named file name outside a
URL, and the writer rewrites such names on the install page as well as the
verify page. They run offline with the standard library: the fixtures patch
each module's file paths.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-release-links.py"
spec = importlib.util.spec_from_file_location("check_release_links", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

WRITER_PATH = Path(__file__).resolve().parent / "set-release-links.py"
writer_spec = importlib.util.spec_from_file_location("set_release_links", WRITER_PATH)
writer = importlib.util.module_from_spec(writer_spec)
writer_spec.loader.exec_module(writer)


SUM = "2b57d83fcbe567d5d617a8d2416770e5a832002aa5f01e196ef6d1bcd12f1336"
URL = "https://github.com/jposluns/cleanlanguage/releases/download/v{v}/cleanlanguage-{v}.zip"
LIVE_VERIFY = (
    '<a href="' + URL + '">x</a><p>The published checksum for version {v} is:</p>'
    '<pre><code id="published-checksum">{sum}</code></pre>'
)
DRAFT_INSTALL = '<a href="' + URL + '">cleanlanguage-{v}.zip</a><p class="lbl size">zip, version {v}</p><p>for example <code>cleanlanguage-{v}.zip</code></p>'
DRAFT_VERIFY = (
    '<a href="' + URL + '">cleanlanguage-{v}.zip</a><p class="lbl size">zip, version {v}, SHA-256</p>'
    '<p>The published checksum for version {v} is:</p><code class="sum" id="published-checksum">{sum}</code>'
    '<pre>sha256sum cleanlanguage-{v}.zip</pre>'
)


class DraftReleaseTest(unittest.TestCase):
    """Checks 6 and 7: site-src/release.json and the template pages under site/draft/."""

    NAMES = ("REPO_ROOT", "SITE_ROOT", "SKILL", "REDIRECTS", "VERIFY_PAGE", "RELEASE_JSON", "DRAFT_PAGES", "DRAFT_VERIFY")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = {name: getattr(gate, name) for name in self.NAMES}
        root = Path(self._tmp.name)
        site = root / "site"
        gate.REPO_ROOT = root
        gate.SITE_ROOT = site
        gate.SKILL = root / "SKILL.md"
        gate.REDIRECTS = site / "_redirects"
        gate.VERIFY_PAGE = site / "verify" / "index.html"
        gate.RELEASE_JSON = root / "site-src" / "release.json"
        gate.DRAFT_PAGES = [site / "draft" / "install" / "index.html", site / "draft" / "verify" / "index.html"]
        gate.DRAFT_VERIFY = gate.DRAFT_PAGES[1]
        self.write(gate.SKILL, "Version: 1.0.14\n")
        self.write(gate.REDIRECTS, "/download " + URL.format(v="1.0.14") + " 302\n")
        self.write(gate.VERIFY_PAGE, LIVE_VERIFY.format(v="1.0.14", sum=SUM))
        self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % SUM)
        self.write(gate.DRAFT_PAGES[0], DRAFT_INSTALL.format(v="1.0.14"))
        self.write(gate.DRAFT_VERIFY, DRAFT_VERIFY.format(v="1.0.14", sum=SUM))

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(gate, name, value)
        self._tmp.cleanup()

    @staticmethod
    def write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_gate(self) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = gate.main()
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue() + err.getvalue()

    def test_consistent_fixture_passes(self):
        code, output = self.run_gate()
        self.assertEqual(code, 0, output)

    def test_release_json_names_another_version(self):
        self.write(gate.RELEASE_JSON, '{"version": "1.0.13", "tag": "v1.0.13", "checksum": "%s"}' % SUM)
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("release.json names version", output)

    def test_release_json_checksum_differs_from_live_page(self):
        self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % ("e" * 64))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("different checksums", output)

    def test_draft_install_keeps_an_old_filename(self):
        # The known version-text issue: a bare filename left at the old version.
        self.write(gate.DRAFT_PAGES[0], DRAFT_INSTALL.format(v="1.0.14").replace("<code>cleanlanguage-1.0.14.zip", "<code>cleanlanguage-1.0.13.zip"))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("site/draft/install/index.html names the file cleanlanguage-1.0.13.zip", output)

    def test_draft_version_label_left_behind(self):
        self.write(gate.DRAFT_PAGES[0], DRAFT_INSTALL.format(v="1.0.14").replace("zip, version 1.0.14", "zip, version 1.0.13"))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("names version 1.0.13", output)

    def test_draft_verify_checksum_differs(self):
        self.write(gate.DRAFT_VERIFY, DRAFT_VERIFY.format(v="1.0.14", sum="d" * 64))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("checksum other than", output)

    def test_draft_verify_without_its_checksum(self):
        self.write(gate.DRAFT_VERIFY, DRAFT_VERIFY.format(v="1.0.14", sum=SUM).replace('id="published-checksum"', 'id="sum"'))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("exactly 1", output)

    def test_missing_release_json_fails_closed(self):
        gate.RELEASE_JSON.unlink()
        code, _ = self.run_gate()
        self.assertEqual(code, 3)

    def test_malformed_release_json_fails_closed(self):
        self.write(gate.RELEASE_JSON, "{not json")
        code, _ = self.run_gate()
        self.assertEqual(code, 3)


class VersionParseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (
            gate.REPO_ROOT, gate.SITE_ROOT, gate.SKILL,
            gate.REDIRECTS, gate.VERIFY_PAGE,
        )
        self._saved_draft = (gate.RELEASE_JSON, gate.DRAFT_PAGES, gate.DRAFT_VERIFY)
        root = Path(self._tmp.name)
        # The draft inputs (checks 7 and 8) sit outside SITE_ROOT and agree with
        # the 1.0.14 site the bare-name tests write, so no test fails on them.
        gate.RELEASE_JSON = root / "release.json"
        gate.DRAFT_PAGES = [root / "draft-install.html", root / "draft-verify.html"]
        gate.DRAFT_VERIFY = gate.DRAFT_PAGES[1]
        gate.RELEASE_JSON.write_text(
            '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % ("a" * 64), encoding="utf-8"
        )
        gate.DRAFT_PAGES[0].write_text("<p>zip, version 1.0.14</p>", encoding="utf-8")
        gate.DRAFT_VERIFY.write_text(
            "<p>The published checksum for version 1.0.14 is:</p>"
            '<code class="sum" id="published-checksum">' + "a" * 64 + "</code>",
            encoding="utf-8",
        )
        gate.REPO_ROOT = root
        gate.SITE_ROOT = root / "site"
        gate.SKILL = root / "SKILL.md"
        gate.REDIRECTS = root / "_redirects"
        gate.VERIFY_PAGE = root / "verify.html"
        # REDIRECTS and VERIFY_PAGE must exist so main() reaches the version
        # parse; each test writes SKILL.md itself. SITE_ROOT is left absent, so a
        # test that parses a valid version would find no links and pass, while
        # these tests all fail at the parse before the site walk.
        gate.REDIRECTS.write_text("", encoding="utf-8")
        gate.VERIFY_PAGE.write_text("", encoding="utf-8")

    def tearDown(self):
        (gate.REPO_ROOT, gate.SITE_ROOT, gate.SKILL, gate.REDIRECTS,
         gate.VERIFY_PAGE) = self._saved
        gate.RELEASE_JSON, gate.DRAFT_PAGES, gate.DRAFT_VERIFY = self._saved_draft
        self._tmp.cleanup()

    def _expect_die(self, needle: str):
        # Assert both exit 3 AND the version-parse-specific message, so a test
        # cannot pass on an unrelated later exit-3 path (for example the empty
        # SITE_ROOT reporting no release URLs).
        err = io.StringIO()
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
            gate.main()
        self.assertEqual(caught.exception.code, 3)
        self.assertIn(needle, err.getvalue())

    def test_malformed_first_version_line_is_rejected(self):
        # The first Version line is authoritative; a malformed first line must
        # fail rather than fall through to a later valid one.
        gate.SKILL.write_text(
            "Version: 9.9.9 trailing\nVersion: 1.2.3\n", encoding="utf-8"
        )
        self._expect_die("not a bare X.Y.Z version")

    def test_dotted_version_is_rejected(self):
        gate.SKILL.write_text("Version: 1.0.\n", encoding="utf-8")
        self._expect_die("not a bare X.Y.Z version")

    def test_missing_version_line_is_rejected(self):
        gate.SKILL.write_text("name: cleanlanguage\n", encoding="utf-8")
        self._expect_die("no 'Version:' line found")

    def test_non_utf8_skill_is_rejected(self):
        gate.SKILL.write_bytes(b"Version: 1.0.14\xff\n")
        self._expect_die("could not be read")

    def _valid_url(self, version):
        return (
            "https://github.com/jposluns/cleanlanguage/releases/download/"
            f"v{version}/cleanlanguage-{version}.zip"
        )

    def test_unreadable_site_file_fails_closed(self):
        # A scanned site file that is not valid UTF-8 must fail closed and name
        # the file, not be silently skipped -- a skipped file could carry a
        # stale release link that then ships unnoticed.
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        gate.SITE_ROOT.mkdir(parents=True, exist_ok=True)
        (gate.SITE_ROOT / "page.html").write_bytes(b"<a>\xff</a>\n")
        self._expect_die("site/page.html could not be read")

    def test_unreadable_redirects_fails_closed(self):
        # A present-but-unreadable _redirects must exit 3 naming the file, not
        # raise an uncaught traceback (which mislabels it as exit 1).
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        gate.SITE_ROOT.mkdir(parents=True, exist_ok=True)
        (gate.SITE_ROOT / "index.html").write_text(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n', encoding="utf-8"
        )
        gate.REDIRECTS.write_bytes(b"\xff\n")
        self._expect_die("site/_redirects could not be read")

    def test_unreadable_verify_page_fails_closed(self):
        # A present-but-unreadable verify page must exit 3 naming the file, not
        # raise an uncaught traceback.
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        gate.SITE_ROOT.mkdir(parents=True, exist_ok=True)
        (gate.SITE_ROOT / "index.html").write_text(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n', encoding="utf-8"
        )
        gate.REDIRECTS.write_text(self._valid_url("1.0.14") + "\n", encoding="utf-8")
        gate.VERIFY_PAGE.write_bytes(b"\xff\n")
        self._expect_die("site/verify/index.html could not be read")

    def test_present_but_unreadable_skill_reports_could_not_be_read(self):
        # The existence pre-check must distinguish a missing file from one that
        # exists but cannot be stat'd (an unreadable parent, say): the latter
        # reports "could not be read", not the misleading "does not exist". It
        # still fails closed either way; only the message differs.
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        real_stat = Path.stat

        def fake_stat(self, *args, **kwargs):
            if self == gate.SKILL:
                raise PermissionError(13, "Permission denied")
            return real_stat(self, *args, **kwargs)

        with unittest.mock.patch.object(Path, "stat", fake_stat):
            self._expect_die("SKILL.md could not be read: [Errno 13]")

    def test_present_but_non_regular_skill_is_rejected(self):
        # A required path that exists but is not a regular file must fail closed
        # at the pre-check with "is not a regular file". A directory is used
        # rather than a fifo so that if the S_ISREG guard ever regressed, the
        # downstream read fails fast (IsADirectoryError) and this test fails
        # cleanly, instead of blocking forever on a writer-less fifo. The guard
        # rejects fifos and sockets by the same S_ISREG check.
        gate.SKILL.mkdir()
        try:
            self._expect_die("SKILL.md is not a regular file")
        finally:
            gate.SKILL.rmdir()

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "chmod is not restrictive when running as root",
    )
    def test_unreadable_site_directory_fails_closed(self):
        # os.walk/rglob silently drop files under a directory they cannot list;
        # the gate must fail closed on such a directory, not skip it (a stale
        # link inside it would otherwise ship undetected).
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        gate.SITE_ROOT.mkdir(parents=True, exist_ok=True)
        (gate.SITE_ROOT / "index.html").write_text(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n', encoding="utf-8"
        )
        secret = gate.SITE_ROOT / "archive"
        secret.mkdir()
        (secret / "old.html").write_text("stale", encoding="utf-8")
        os.chmod(secret, 0o000)
        try:
            self._expect_die("site/archive could not be read")
        finally:
            os.chmod(secret, 0o755)

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        "chmod is not restrictive when running as root",
    )
    def test_unreadable_file_in_unreadable_directory_fails_closed(self):
        # A directory readable for names but not traversable (mode 0o400) lets
        # os.walk list a file inside it, but stat and read of that file are
        # denied. is_file() would swallow the error and skip the file; the gate
        # must fail closed instead of dropping a possibly-stale page.
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        gate.SITE_ROOT.mkdir(parents=True, exist_ok=True)
        (gate.SITE_ROOT / "index.html").write_text(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n', encoding="utf-8"
        )
        locked = gate.SITE_ROOT / "archive"
        locked.mkdir()
        (locked / "old.html").write_text("stale", encoding="utf-8")
        os.chmod(locked, 0o400)
        try:
            self._expect_die("site/archive/old.html could not be read")
        finally:
            os.chmod(locked, 0o755)

    def test_directory_classification_error_fails_closed(self):
        # os.walk treats an entry whose is_dir() raises an OSError as a
        # non-directory and never descends it, silently dropping the subtree.
        # The scandir walk must fail closed on such a classification error.
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        gate.SITE_ROOT.mkdir(parents=True, exist_ok=True)
        (gate.SITE_ROOT / "index.html").write_text(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n', encoding="utf-8"
        )
        (gate.SITE_ROOT / "install").mkdir()
        (gate.SITE_ROOT / "install" / "page.html").write_text("stale", encoding="utf-8")
        real_scandir = os.scandir

        def raising_scandir(target):
            for entry in real_scandir(target):
                if entry.name == "install":
                    proxy = unittest.mock.Mock(wraps=entry)
                    proxy.name = entry.name
                    proxy.path = entry.path
                    proxy.is_dir.side_effect = OSError(5, "injected classification error")
                    yield proxy
                else:
                    yield entry

        with unittest.mock.patch("os.scandir", raising_scandir):
            self._expect_die("site/install could not be read")

    def _write_consistent_site(self, page_text):
        # A site that passes every other rule, so a test fails only on the
        # page text it supplies.
        gate.SKILL.write_text("Version: 1.0.14\n", encoding="utf-8")
        gate.SITE_ROOT.mkdir(parents=True, exist_ok=True)
        (gate.SITE_ROOT / "install.html").write_text(page_text, encoding="utf-8")
        gate.REDIRECTS.write_text(self._valid_url("1.0.14") + "\n", encoding="utf-8")
        gate.VERIFY_PAGE.write_text(
            '<p>The published checksum for version 1.0.14 is:</p>\n'
            '<code id="published-checksum">' + "a" * 64 + "</code>\n",
            encoding="utf-8",
        )

    def _run_gate(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gate.main()
        return code, out.getvalue()

    def test_stale_bare_file_name_fails(self):
        # A version-named file name written out bare, outside any URL, must
        # name the current version. This is the install page's example
        # download name, which once kept the old version after a release.
        self._write_consistent_site(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n'
            "<p>for example <code>cleanlanguage-1.0.13.zip</code></p>\n"
        )
        code, out = self._run_gate()
        self.assertEqual(code, 1)
        self.assertIn(
            "site/install.html names the file cleanlanguage-1.0.13.zip, "
            "but SKILL.md says 1.0.14",
            out,
        )

    def test_current_bare_file_name_passes(self):
        self._write_consistent_site(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n'
            "<p>for example <code>cleanlanguage-1.0.14.zip</code></p>\n"
        )
        code, out = self._run_gate()
        self.assertEqual(code, 0, out)

    def test_stale_url_is_not_also_reported_as_a_bare_name(self):
        # A stale URL is reported once, as a link, not again as a file name.
        self._write_consistent_site(
            f'<a href="{self._valid_url("1.0.14")}">dl</a>\n'
            f'<a href="{self._valid_url("1.0.13")}">old</a>\n'
        )
        code, out = self._run_gate()
        self.assertEqual(code, 1)
        self.assertIn("site/install.html links at version 1.0.13", out)
        self.assertNotIn("names the file", out)


class WriterBareFileNameTest(unittest.TestCase):
    """set-release-links.py rewrites bare file names on both pages it owns."""

    OLD_URL = (
        "https://github.com/jposluns/cleanlanguage/releases/download/"
        "v1.0.14/cleanlanguage-1.0.14.zip"
    )
    STAMPS = (
        '<meta property="article:modified_time" content="2020-01-01">\n'
        '<script type="application/ld+json">{"dateModified": "2020-01-01"}</script>\n'
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (writer.REPO_ROOT, writer.SITE)
        # The temporary repository has no generator; these tests are about the live
        # pages, so the draft regeneration is replaced by a stub that plans nothing.
        self._saved_draft_pages = writer.draft_pages
        writer.draft_pages = lambda release: {}
        root = Path(self._tmp.name)
        writer.REPO_ROOT = root
        writer.SITE = root / "site"
        (writer.SITE / "install").mkdir(parents=True)
        (writer.SITE / "verify").mkdir(parents=True)
        (writer.SITE / "install" / "index.html").write_text(
            self.STAMPS
            + f'<a href="{self.OLD_URL}">dl</a>\n'
            + "<p>for example <code>cleanlanguage-1.0.14.zip</code></p>\n",
            encoding="utf-8",
        )
        (writer.SITE / "verify" / "index.html").write_text(
            self.STAMPS
            + f'<a href="{self.OLD_URL}">dl</a>\n'
            + "<p>The published checksum for version 1.0.14 is:</p>\n"
            + '<code id="published-checksum">' + "b" * 64 + "</code>\n"
            + "<pre><code>sha256sum cleanlanguage-1.0.14.zip</code></pre>\n",
            encoding="utf-8",
        )

    def tearDown(self):
        writer.REPO_ROOT, writer.SITE = self._saved
        writer.draft_pages = self._saved_draft_pages
        self._tmp.cleanup()

    def test_every_page_names_the_new_release_file(self):
        planned = writer.rewrite("1.0.15", "v1.0.15", "a" * 64, "2026-11-03")
        install = planned[writer.SITE / "install" / "index.html"]
        verify = planned[writer.SITE / "verify" / "index.html"]
        for text in (install, verify):
            self.assertNotIn("cleanlanguage-1.0.14.zip", text)
        self.assertIn("<code>cleanlanguage-1.0.15.zip</code>", install)
        self.assertIn("sha256sum cleanlanguage-1.0.15.zip", verify)


if __name__ == "__main__":
    unittest.main()
