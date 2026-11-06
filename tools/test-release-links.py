#!/usr/bin/env python3
"""Tests for check-release-links.py, and for the bare file names set-release-links.py writes.

The gate reads the current version from the first ``Version:`` line of
``cleanlanguage/skills/cleanlanguage/SKILL.md``. These tests pin the gate's failure paths: the version parse (a malformed,
missing, or unreadable SKILL, which fails before the site walk), and the
fail-closed reads of scanned site files, ``site/_redirects``, and the verify
page (which build a small site fixture). They also pin the bare file-name
rule on both sides: the gate fails on a stale version-named file name outside a
URL, and the writer, which regenerates the pages with tools/build-site.py,
writes the new names on the install page as well as the verify page. They pin
the verify page's 2 states (a published checksum, or the zero placeholder with
the not-yet-published note), each held to the download block tools/build-site.py
renders for it (the verify page fixtures carry that block), the refusal of a page
that mixes them, hides or moves the block, and the writer's round trip from the
placeholder to a published checksum. They run
offline with the standard library: the fixtures patch each module's file paths,
and the writer tests run it on a copy of the generator's inputs under $TMPDIR.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
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
INSTALL = '<a href="' + URL + '">cleanlanguage-{v}.zip</a><p class="lbl size">zip, version {v}</p><p>for example <code>cleanlanguage-{v}.zip</code></p>'
ZEROS = "0" * 64


def verify_page(v: str, checksum: str) -> str:
    """A verify page laid out as tools/build-site.py writes it: the download block the generator renders for ``v``
    and ``checksum`` (the gate's download_block), inside the elements build() writes around it (BLOCK_ANCESTORS)."""
    return ('<!doctype html>\n<html lang="en" class="site-cleanlanguage">\n<head><title>Verify</title></head>\n<body>\n'
            '<main id="main-content">\n<div class="wrap"><div class="doc"><h1>Verify your download</h1>\n'
            + gate.download_block(v, checksum) + '<div class="next"></div></div></div>\n</main>\n</body>\n</html>\n')


class Page:
    """A verify page in 1 state, written with format as the fixtures were: VERIFY.format(v=..., sum=...) for a
    published checksum, PENDING.format(v=...) for the zero placeholder."""

    def __init__(self, checksum: str | None = None) -> None:
        self.checksum = checksum

    def format(self, v: str, sum: str | None = None) -> str:
        return verify_page(v, self.checksum or sum)


VERIFY = Page()
PENDING = Page(ZEROS)
# The parts of the published state's download block, each as the generator writes it.
LEAD = '<p>Download the skill. The published checksum is shown under the link.</p>'
SUM_LINK = ('<a href="' + URL + '.sha256" target="_blank" rel="noopener noreferrer">published checksum file'
            '<span class="vh"> (opens in a new tab)</span></a>')
STEP_3 = '<p class="lbl blk">Step 3</p>\n'
REJECT = "If the values still differ after a fresh download, do not install the file and "
CODE = '<code class="sum" id="published-checksum">{sum}</code>'
NOTE = "<p>The checksum for version {v} appears here once that version is published.</p>"


def outside(page: str, extra: str) -> str:
    """``page`` with ``extra`` after the download block, inside main."""
    return page.replace('<div class="next">', extra + '<div class="next">', 1)


class ReleaseSourceTest(unittest.TestCase):
    """Checks 7 and 8: site-src/release.json and the install and verify pages generated from it."""

    NAMES = ("REPO_ROOT", "SITE_ROOT", "SKILL", "REDIRECTS", "INSTALL_PAGE", "VERIFY_PAGE", "RELEASE_JSON")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = {name: getattr(gate, name) for name in self.NAMES}
        root = Path(self._tmp.name)
        site = root / "site"
        gate.REPO_ROOT = root
        gate.SITE_ROOT = site
        gate.SKILL = root / "SKILL.md"
        gate.REDIRECTS = site / "_redirects"
        gate.INSTALL_PAGE = site / "install" / "index.html"
        gate.VERIFY_PAGE = site / "verify" / "index.html"
        gate.RELEASE_JSON = root / "site-src" / "release.json"
        self.write(gate.SKILL, "Version: 1.0.14\n")
        self.write(gate.REDIRECTS, "/download " + URL.format(v="1.0.14") + " 302\n"
                   + "/download/checksum " + URL.format(v="1.0.14") + ".sha256 302\n")
        self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % SUM)
        self.write(gate.INSTALL_PAGE, INSTALL.format(v="1.0.14"))
        self.write(gate.VERIFY_PAGE, VERIFY.format(v="1.0.14", sum=SUM))

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

    def test_release_json_checksum_differs_from_the_verify_page(self):
        self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % ("e" * 64))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("site/verify/index.html shows a checksum other than site-src/release.json", output)

    def test_install_keeps_an_old_filename(self):
        # The known version-text issue: a bare filename left at the old version.
        self.write(gate.INSTALL_PAGE, INSTALL.format(v="1.0.14").replace("<code>cleanlanguage-1.0.14.zip", "<code>cleanlanguage-1.0.13.zip"))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("site/install/index.html names the file cleanlanguage-1.0.13.zip", output)

    def test_version_label_left_behind(self):
        self.write(gate.INSTALL_PAGE, INSTALL.format(v="1.0.14").replace("zip, version 1.0.14", "zip, version 1.0.13"))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("site/install/index.html names version 1.0.13", output)

    def test_install_page_naming_no_release(self):
        self.write(gate.INSTALL_PAGE, "<p>No download here.</p>")
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("site/install/index.html names no release version", output)

    # The reports of the verify page rule (download_block_problems), and the end of each in either state.
    BLOCK = "site/verify/index.html does not carry the download block that tools/build-site.py writes for this state"
    PLACED = "site/verify/index.html does not carry the download block where tools/build-site.py writes it"
    HOLDS = ", but site-src/release.json holds the zero placeholder"
    SHOWS = ", but site-src/release.json holds a published checksum"

    def test_verify_checksum_differs(self):
        self.write(gate.VERIFY_PAGE, VERIFY.format(v="1.0.14", sum="d" * 64))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("checksum other than", output)
        self.assertIn(self.BLOCK, output)

    def test_checksum_element_with_another_attribute_fails(self):
        # The element must be exactly the one the generator writes; no other attribute, such as hidden, passes.
        self.write(gate.VERIFY_PAGE, VERIFY.format(v="1.0.14", sum=SUM).replace(
            'id="published-checksum">', 'id="published-checksum" hidden>'))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn('the verify page has no <code class="sum" id="published-checksum"> block', output)
        self.assertIn(self.BLOCK, output)

    def test_the_old_checksum_element_fails(self):
        # The element of the pages retired at promotion no longer passes.
        self.write(gate.VERIFY_PAGE, VERIFY.format(v="1.0.14", sum=SUM).replace(
            '<code class="sum" id="published-checksum">', '<code id="published-checksum">'))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn(self.BLOCK, output)

    def test_a_second_checksum_element_fails(self):
        self.write(gate.VERIFY_PAGE, outside(VERIFY.format(v="1.0.14", sum=SUM), CODE.format(sum=SUM)))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("site/verify/index.html carries the checksum element's id outside the download block" + self.SHOWS,
                      output)

    def test_verify_without_its_checksum(self):
        self.write(gate.VERIFY_PAGE, VERIFY.format(v="1.0.14", sum=SUM).replace('id="published-checksum"', 'id="sum"'))
        code, output = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn(self.BLOCK, output)

    def pending(self, page: str) -> tuple[int, str]:
        """Run the gate with the zero placeholder in release.json and ``page`` as the verify page."""
        self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % ZEROS)
        self.write(gate.VERIFY_PAGE, page)
        return self.run_gate()

    def test_placeholder_with_the_note_passes(self):
        code, output = self.pending(PENDING.format(v="1.0.14"))
        self.assertEqual(code, 0, output)
        self.assertIn("the verify page says the checksum appears once that version is published", output)

    def test_the_committed_verify_page_carries_its_block_where_the_generator_writes_it(self):
        # The rule holds on the page tools/build-site.py writes, so BLOCK_ANCESTORS is the generator's layout.
        repo = Path(__file__).resolve().parent.parent
        release = json.loads((repo / "site-src/release.json").read_text(encoding="utf-8"))
        page = (repo / "site/verify/index.html").read_text(encoding="utf-8")
        block = gate.download_block(release["version"], release["checksum"])
        redirects = (repo / "site/_redirects").read_text(encoding="utf-8")
        self.assertEqual(gate.download_block_problems(page, block, redirects), [])
        self.assertEqual(gate.PageReader(page).open_at[page.index(block)], gate.BLOCK_ANCESTORS)

    def test_placeholder_shown_as_the_published_checksum_fails(self):
        # The page 35ac33a committed: the zero placeholder under the published wording.
        code, output = self.pending(VERIFY.format(v="1.0.14", sum=SUM).replace(SUM, ZEROS))
        self.assertEqual(code, 1)
        self.assertIn(self.BLOCK + " exactly once, byte for byte (found 0)" + self.HOLDS, output)

    def test_placeholder_note_beside_published_wording_fails(self):
        # 1 case for each part of the published state outside the block; each is reported on its own.
        for label, extra, report in (
            ("the checksum element", '<p>' + CODE.format(sum="1" * 63) + "</p>",
             "carries the checksum element's id outside the download block"),
            ("the published checksum in step 3", "<p>Compare it with the published checksum shown in step 1.</p>",
             'says "published checksum" outside the download block'),
            ("a link to the checksum file", '<a href="' + URL.format(v="1.0.14") + '.sha256">file</a>',
             "links a .sha256 checksum file outside the download block"),
            ("a step that rejects the download", "<p>If the 2 values still differ, do not install the file.</p>",
             "has a step that tells the reader not to install the file outside the download block"),
            ("a second note", NOTE.format(v="1.0.14"), "carries the not-yet-published note outside the download block"),
            ("a second note for another version", NOTE.format(v="1.0.13"),
             "carries the not-yet-published note outside the download block"),
        ):
            with self.subTest(label):
                code, output = self.pending(outside(PENDING.format(v="1.0.14"), extra))
                self.assertEqual(code, 1, output)
                self.assertIn(f"site/verify/index.html {report}{self.HOLDS}", output)

    def test_placeholder_note_beside_equivalent_markup_fails(self):
        # Finding 1 (DISCOVERY round 2), and findings 2 and 5 (VERIFY round 2.1): outside the block, the page
        # is read as parsed markup and as written, comments and hidden elements included, and a link through
        # site/_redirects to the checksum file is a link to that file.
        for label, extra, report in (
            ("the checksum element with its attributes in the other order",
             '<code id="published-checksum" class="sum">' + ZEROS + "</code>",
             "carries the checksum element's id outside the download block"),
            ("the checksum element with another attribute", "<code class='x' hidden id=published&#45;checksum></code>",
             "carries the checksum element's id outside the download block"),
            ("the checksum element in a comment", "<!-- " + CODE.format(sum="1" * 3) + " -->",
             "carries the checksum element's id outside the download block"),
            ("the checksum element's id in a script", '<script>show("published-checksum")</script>',
             "carries the checksum element's id outside the download block"),
            ("a link to the checksum file in a script", '<script>fetch("/v1/x.SHA256")</script>',
             "links a .sha256 checksum file outside the download block"),
            ("64 zeros in an element of the class sum without the id", '<code class="sum">' + ZEROS + "</code>",
             "carries the class sum outside the download block"),
            ("the class sum in a comment", '<!-- <span class="x sum"></span> -->',
             "carries the class sum outside the download block"),
            ("64 zeros as text", "<p>" + ZEROS + "</p>", "carries a 64 digit hexadecimal value outside the download block"),
            ("64 hexadecimal digits split by markup in an attribute and in a comment",
             '<p data-x="' + "A" * 64 + '">' + "f" * 32 + "<b></b>" + "f" * 32 + "</p><!-- " + "e" * 64 + " -->",
             "carries a 64 digit hexadecimal value outside the download block"),
            ("a link through the checksum redirect", '<a href="/download/checksum">file</a>',
             "links a .sha256 checksum file outside the download block"),
            ("a link through the checksum redirect with a doubled slash", '<a href="/download//checksum">file</a>',
             "links a .sha256 checksum file outside the download block"),
            ("a relative link through the checksum redirect", '<a href="../download/Checksum/">file</a>',
             "links a .sha256 checksum file outside the download block"),
            ("an absolute link through the checksum redirect",
             '<a href="https://cleanlanguage.ai/download/checksum?from=verify">file</a>',
             "links a .sha256 checksum file outside the download block"),
            ("a link to the checksum file with an encoded dot", '<a href="' + URL.format(v="1.0.14") + '%2Esha256">file</a>',
             "links a .sha256 checksum file outside the download block"),
            ("published checksum wording split by markup", "<p>The published <b>checksum</b> is below.</p>",
             'says "published checksum" outside the download block'),
            ("a step that rejects the download split by markup", "<p>If they differ, do <em>not</em> install the file.</p>",
             "has a step that tells the reader not to install the file outside the download block"),
            ("a step that rejects the download in a contraction", "<p>If they differ, don&#8217;t install the file.</p>",
             "has a step that tells the reader not to install the file outside the download block"),
            ("the note split by markup", "<p>It appears <b>here</b> once that version is published.</p>",
             "carries the not-yet-published note outside the download block"),
            ("the note in a comment", "<!-- " + NOTE.format(v="1.0.14") + " -->",
             "carries the not-yet-published note outside the download block"),
        ):
            with self.subTest(label):
                code, output = self.pending(outside(PENDING.format(v="1.0.14"), extra))
                self.assertEqual(code, 1, output)
                self.assertIn(f"site/verify/index.html {report}{self.HOLDS}", output)

    def test_placeholder_note_beside_other_links_passes(self):
        # A link to the zip, directly or through its redirect, and a value that is not a URL are not links to
        # the checksum file.
        code, output = self.pending(outside(PENDING.format(v="1.0.14"), '<a href="/download">zip</a><a href="http://[x">x</a>'))
        self.assertEqual(code, 0, output)

    def test_published_checksum_without_the_rest_of_its_state_fails(self):
        # Finding 2 (DISCOVERY round 2) and finding 4 (VERIFY round 2.1): any change to the block, such as a
        # missing step 1 lead, link to the checksum file or step 3, or a step 3 that rejects a matching value,
        # leaves the page without the block the generator writes.
        page = VERIFY.format(v="1.0.14", sum=SUM)
        link = SUM_LINK.format(v="1.0.14")
        for label, changed in (
            ("no step 1 lead", page.replace(LEAD, "<p>Download the skill.</p>")),
            ("the step 1 lead in a comment only", page.replace(LEAD, "<p>Download the skill.<!-- " + LEAD + " --></p>")),
            ("no link to the checksum file", page.replace(link, "published checksum file")),
            ("a link to the checksum file of another version", page.replace(link, link.replace("v1.0.14/", "v1.0.13/"))),
            ("no step 3", page.replace(STEP_3, "")),
            ("no step that rejects the download", page.replace(REJECT, "")),
            ("a step 3 that rejects a matching value", page.replace(REJECT, REJECT.replace("still differ", "match"))),
            ("step 3, the link and the step 1 lead removed",
             page.replace(LEAD, "<p>Download the skill.</p>").replace(link, "published checksum file")
             .replace(page[page.index(STEP_3):page.index('<div class="next">')], "")),
        ):
            with self.subTest(label):
                self.assertNotEqual(changed, page)
                self.write(gate.VERIFY_PAGE, changed)
                code, output = self.run_gate()
                self.assertEqual(code, 1, output)
                self.assertIn(self.BLOCK + " exactly once, byte for byte (found 0)" + self.SHOWS, output)

    def test_the_block_hidden_or_moved_fails(self):
        # Findings 1 and 3 (VERIFY round 2.1): a part of the block hidden or commented out, or a wrong checksum
        # beside it, changes the block; the whole block inside other markup, or a page that copies a hidden
        # attribute onto its body, is not where the generator writes it.
        page = VERIFY.format(v="1.0.14", sum=SUM)
        start, end = page.index('<p class="lbl blk">Step 1</p>'), page.index('<div class="next">')
        step_3 = page[page.index(STEP_3):end]
        code_element = CODE.format(sum=SUM)
        for label, changed, report in (
            ("the step 1 lead hidden", page.replace(LEAD, "<div hidden>" + LEAD + "</div>"), self.BLOCK),
            ("the link to the checksum file hidden",
             page.replace(SUM_LINK.format(v="1.0.14"), "<span hidden>" + SUM_LINK.format(v="1.0.14") + "</span>"),
             self.BLOCK),
            ("step 3 hidden", page.replace(step_3, "<div hidden>" + step_3 + "</div>"), self.BLOCK),
            ("the checksum element in a comment beside a visible one",
             page.replace(code_element, "<!-- " + code_element + ' --><code id="published-checksum" class="sum">'
                          + "f" * 64 + "</code>"), self.BLOCK),
            ("a second, wrong checksum element beside the real one",
             page.replace(code_element, code_element + CODE.format(sum="f" * 64)), self.BLOCK),
            ("the note split by markup beside the checksum",
             page.replace(code_element, code_element + "<p>It appears <b>here</b> once that version is published.</p>"),
             self.BLOCK),
            ("the whole block hidden", page[:start] + "<div hidden>" + page[start:end] + "</div>" + page[end:], self.PLACED),
            ("the whole block in a comment", page[:start] + "<!--" + page[start:end] + "-->" + page[end:], self.PLACED),
            ("the whole block in a template", page[:start] + "<template>" + page[start:end] + "</template>" + page[end:],
             self.PLACED),
            ("the whole block in an element left open", page[:start] + "<details>" + page[start:], self.PLACED),
            ("the whole block in a self-closed div, which a browser leaves open",
             page[:start] + "<div hidden/>" + page[start:], self.PLACED),
            ("the block twice", outside(page, page[start:end]), self.BLOCK + " exactly once, byte for byte (found 2)"),
            ("a stray body start tag with a hidden attribute", outside(page, "<body hidden>"), self.PLACED),
            ("a stray html start tag", outside(page, "<html hidden>"), self.PLACED),
            ("the wrap div with another attribute", page.replace('<div class="wrap">', '<div class="wrap" hidden>'),
             self.PLACED),
        ):
            with self.subTest(label):
                self.assertNotEqual(changed, page)
                self.write(gate.VERIFY_PAGE, changed)
                code, output = self.run_gate()
                self.assertEqual(code, 1, output)
                self.assertIn(report, output)
                self.assertIn(self.SHOWS, output)

    def test_placeholder_note_missing_or_repeated_fails(self):
        for label, page, report in (
            ("no note", PENDING.format(v="1.0.14").replace(NOTE.format(v="1.0.14"), ""), self.BLOCK),
            ("the note in a comment only",
             PENDING.format(v="1.0.14").replace(NOTE.format(v="1.0.14"), "<!-- " + NOTE.format(v="1.0.14") + " -->"),
             self.BLOCK),
            ("2 notes", outside(PENDING.format(v="1.0.14"), NOTE.format(v="1.0.14")),
             "site/verify/index.html carries the not-yet-published note outside the download block"),
        ):
            with self.subTest(label):
                code, output = self.pending(page)
                self.assertEqual(code, 1, output)
                self.assertIn(report + (" exactly once" if report == self.BLOCK else ""), output)

    def test_placeholder_note_for_another_version_fails(self):
        code, output = self.pending(PENDING.format(v="1.0.14").replace(NOTE.format(v="1.0.14"), NOTE.format(v="1.0.13")))
        self.assertEqual(code, 1)
        self.assertIn("the verify page says the checksum for version 1.0.13 appears once that version is published, "
                      "but SKILL.md says 1.0.14", output)
        self.assertIn(self.BLOCK, output)

    def test_published_checksum_with_the_note_fails(self):
        for label, page in (
            ("the note alone", PENDING.format(v="1.0.14")),
            ("the note beside the published checksum", outside(VERIFY.format(v="1.0.14", sum=SUM), NOTE.format(v="1.0.14"))),
        ):
            with self.subTest(label):
                self.write(gate.VERIFY_PAGE, page)
                code, output = self.run_gate()
                self.assertEqual(code, 1, output)
                self.assertIn("site/verify/index.html says the checksum is not yet published, but "
                              "site-src/release.json holds a published checksum", output)

    def test_missing_install_page_fails_closed(self):
        gate.INSTALL_PAGE.unlink()
        code, output = self.run_gate()
        self.assertEqual(code, 3)
        self.assertIn("site/install/index.html does not exist", output)

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
        self._saved_source = (gate.RELEASE_JSON, gate.INSTALL_PAGE)
        root = Path(self._tmp.name)
        # The release source and the install page (checks 7 and 8) sit outside
        # SITE_ROOT and agree with the 1.0.14 site the bare-name tests write, so no
        # test fails on them. The verify page is written by each test.
        gate.RELEASE_JSON = root / "release.json"
        gate.INSTALL_PAGE = root / "install.html"
        gate.RELEASE_JSON.write_text(
            '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % ("a" * 64), encoding="utf-8"
        )
        gate.INSTALL_PAGE.write_text("<p>zip, version 1.0.14</p>", encoding="utf-8")
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
        gate.RELEASE_JSON, gate.INSTALL_PAGE = self._saved_source
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
        gate.VERIFY_PAGE.write_text(VERIFY.format(v="1.0.14", sum="a" * 64), encoding="utf-8")

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


class WriterTest(unittest.TestCase):
    """set-release-links.py regenerates the pages it owns, restamps them and keeps every redirect."""

    REPO = Path(__file__).resolve().parent.parent
    INPUTS = (
        "tools/build-site.py",
        "site-src",
        "cleanlanguage/skills/cleanlanguage/SKILL.md",
        "cleanlanguage/skills/cleanlanguage/references",
        "site",
        ".baseline/pin.toml",
        "tools/sitemap-config.json",
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (writer.REPO_ROOT, writer.SITE)
        root = Path(self._tmp.name)
        for relative in self.INPUTS:
            source, target = self.REPO / relative, root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)
        # The committed site/ is copied whole, so the writer can tell which pages a release changes.
        skill =root / "cleanlanguage/skills/cleanlanguage/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        # The release under test is the next patch version after the copied SKILL.md's, the target
        # tools/release-dry-run.sh chooses, so the test holds at every version, the bump included.
        self.current = gate.SKILL_VERSION.match(gate.VERSION_LINE.search(text).group(0)).group(1)
        major_minor, patch = self.current.rsplit(".", 1)
        self.next = f"{major_minor}.{int(patch) + 1}"
        skill.write_text(re.sub(r"^Version: [0-9.]+", "Version: " + self.next, text, count=1, flags=re.M), encoding="utf-8")
        writer.REPO_ROOT = root
        writer.SITE = root / "site"
        self.root = root

    def tearDown(self):
        writer.REPO_ROOT, writer.SITE = self._saved
        self._tmp.cleanup()

    def plan(self) -> dict:
        planned = writer.rewrite(self.next, "v" + self.next, "a" * 64, "2026-11-04")
        return {path.relative_to(self.root).as_posix(): (text.decode("utf-8") if isinstance(text, bytes) else text)
                for path, text in planned.items()}

    def test_every_page_names_the_new_release_file(self):
        planned = self.plan()
        install, verify = planned["site/install/index.html"], planned["site/verify/index.html"]
        for text in (install, verify):
            self.assertNotIn(f"cleanlanguage-{self.current}.zip", text)
            self.assertNotIn(f"version {self.current}", text)
        self.assertIn(f"<code>cleanlanguage-{self.next}.zip</code>", install)
        self.assertIn(f"sha256sum cleanlanguage-{self.next}.zip", verify)
        self.assertIn('<code class="sum" id="published-checksum">' + "a" * 64 + "</code>", verify)
        self.assertIn(f"published checksum for version {self.next} is", verify)
        self.assertEqual(json.loads(planned["site-src/release.json"]),
                         {"version": self.next, "tag": "v" + self.next, "checksum": "a" * 64})

    def apply(self, checksum: str) -> str:
        """Write what the writer plans for ``checksum`` into the copy, returning the verify page."""
        for path, data in writer.rewrite(self.next, "v" + self.next, checksum, "2026-11-04").items():
            path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return (self.root / "site/verify/index.html").read_text(encoding="utf-8")

    def gate_code(self) -> int:
        """Run check-release-links.py against the copy."""
        saved = {name: getattr(gate, name) for name in ReleaseSourceTest.NAMES}
        gate.REPO_ROOT, gate.SITE_ROOT = self.root, self.root / "site"
        gate.SKILL = self.root / "cleanlanguage/skills/cleanlanguage/SKILL.md"
        gate.REDIRECTS = self.root / "site/_redirects"
        gate.INSTALL_PAGE = self.root / "site/install/index.html"
        gate.VERIFY_PAGE = self.root / "site/verify/index.html"
        gate.RELEASE_JSON = self.root / "site-src/release.json"
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return gate.main()
        finally:
            for name, value in saved.items():
                setattr(gate, name, value)

    def test_the_placeholder_and_the_flip_round_trip(self):
        # A bump writes the zero placeholder and the not-yet-published page; the flip restores the published one.
        note = f"The checksum for version {self.next} appears here once that version is published."
        pending = self.apply(ZEROS)
        self.assertIn(note, pending)
        for gone in ("published checksum", 'id="published-checksum"', ".zip.sha256", "Step 3", "do not install"):
            self.assertNotIn(gone, pending)
        self.assertEqual(self.gate_code(), 0)
        published = self.apply("a" * 64)
        for needed in (f"The published checksum for version {self.next} is:", f"cleanlanguage-{self.next}.zip.sha256",
                       '<code class="sum" id="published-checksum">' + "a" * 64 + "</code>", "Step 3"):
            self.assertIn(needed, published)
        self.assertNotIn(note, published)
        self.assertEqual(self.gate_code(), 0)
        self.assertEqual(self.apply(ZEROS), pending)

    def test_only_the_changed_pages_are_restamped(self):
        planned = self.plan()
        pages = {page["id"]: page for page in json.loads(planned["site-src/site.json"])["pages"]}
        before = {page["id"]: page for page in json.loads((self.root / "site-src/site.json").read_text(encoding="utf-8"))["pages"]}
        for page_id in pages:
            expected = "2026-11-04" if page_id in ("install", "verify") else before[page_id].get("modified")
            self.assertEqual(pages[page_id].get("modified"), expected, page_id)
        for page in ("install", "verify"):
            self.assertIn('<meta property="article:modified_time" content="2026-11-04">', planned[f"site/{page}/index.html"])
            self.assertIn('"dateModified": "2026-11-04"', planned[f"site/{page}/index.html"])
        self.assertNotIn('content="2026-11-04"', planned["site/index.html"])
        # site.json keeps its layout: 1 line per page entry, only the dates changed.
        original = (self.root / "site-src/site.json").read_text(encoding="utf-8")
        self.assertEqual(len(planned["site-src/site.json"].splitlines()), len(original.splitlines()))

    def test_the_redirects_keep_every_fixed_path(self):
        redirects = self.plan()["site/_redirects"]
        for line in ("/privacy https://posluns.ca/privacy/ 301", "/privacy/ https://posluns.ca/privacy/ 301",
                     "/favicon.svg /assets/baseline/logos/cleanlanguage-favicon.svg 301",
                     "/apple-touch-icon.png /assets/baseline/logos/cleanlanguage-touch.png 301",
                     "/downloads/cleanlanguage-short.md /downloads/cleanlanguage-11k.md 301",
                     f"/download https://github.com/jposluns/cleanlanguage/releases/download/v{self.next}/cleanlanguage-{self.next}.zip 302"):
            self.assertIn(line + "\n", redirects)
        self.assertEqual(len(redirects.splitlines()), 10)

    def test_the_committed_redirects_match_the_writer(self):
        # The committed file is exactly what the writer writes for the current release, so a release keeps it.
        release = json.loads((self.REPO / "site-src/release.json").read_text(encoding="utf-8"))
        url = f"https://github.com/jposluns/cleanlanguage/releases/download/{release['tag']}/cleanlanguage-{release['version']}.zip"
        self.assertEqual((self.REPO / "site/_redirects").read_text(encoding="utf-8"), writer.redirects_body(url, url + ".sha256"))

    def test_a_release_that_changes_nothing_restamps_nothing(self):
        (self.root / "cleanlanguage/skills/cleanlanguage/SKILL.md").write_text(
            (self.REPO / "cleanlanguage/skills/cleanlanguage/SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
        release = json.loads((self.REPO / "site-src/release.json").read_text(encoding="utf-8"))
        planned = writer.rewrite(release["version"], release["tag"], release["checksum"], "2026-11-04")
        self.assertNotIn(self.root / "site-src/site.json", planned)


if __name__ == "__main__":
    unittest.main()
