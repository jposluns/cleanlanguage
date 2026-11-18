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
placeholder to a published checksum. They also pin that each rule of the
committed ``site/_redirects`` that stays on this site names a file under site/
that is not an HTML file, is not the source of a rule and does not start with a
splat source (a source ending in *) without its *, that each rule to another
origin names a target the writer documents, and that no scanned file names an old
name of a portable instructions file outside the redirect rule that answers for
it. They run
offline with the standard library: the fixtures patch each module's file paths,
and the writer tests run it on a copy of the generator's inputs under $TMPDIR.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import urllib.parse
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
OTHER = "0123456789abcdef" * 4


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
NOTE = ("<p>The checksum for version {v} appears here once that version is published; compare the checksum of your "
        "file with it then.</p>")


def outside(page: str, extra: str) -> str:
    """``page`` with ``extra`` after the download block, inside main."""
    return page.replace('<div class="next">', extra + '<div class="next">', 1)


def fixture_render() -> bytes:
    """The fixtures' stand-in for the whole page tools/build-site.py renders (the gate's rendered_verify_page): the
    fixture verify page for the version and checksum in the fixture's release.json. WholePageTest runs the real
    generator on a copy of its inputs."""
    release = json.loads(gate.RELEASE_JSON.read_text(encoding="utf-8"))
    return verify_page(release["version"], release["checksum"]).encode("utf-8")


class ReleaseSourceTest(unittest.TestCase):
    """Checks 7 and 8: site-src/release.json and the install and verify pages generated from it."""

    NAMES = ("REPO_ROOT", "SITE_ROOT", "SKILL", "REDIRECTS", "INSTALL_PAGE", "VERIFY_PAGE", "RELEASE_JSON")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = {name: getattr(gate, name) for name in (*self.NAMES, "rendered_verify_page")}
        gate.rendered_verify_page = fixture_render
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

    def test_a_checksum_close_to_the_placeholder_fails(self):
        # A checksum other than the zero placeholder with 56 or more of its 64 digits 0, such as a
        # mistyped placeholder, fails check 7, and the page is not rendered (the generator refuses it). A checksum with
        # 55 digits 0, and one that looks real, still pass.
        def refuse() -> bytes:
            raise AssertionError("rendered for a checksum close to the zero placeholder")

        for checksum, expected in (("0" * 63 + "1", 1), ("0" * 56 + "89abcdef", 1), ("0" * 55 + "123456789", 0),
                                   ("1234abcd" * 8, 0)):
            with self.subTest(checksum):
                gate.rendered_verify_page = refuse if expected else fixture_render
                self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % checksum)
                self.write(gate.VERIFY_PAGE, verify_page("1.0.14", checksum))
                code, output = self.run_gate()
                self.assertEqual(code, expected, output)
                report = f"site-src/release.json holds {checksum}, which is not the zero placeholder but has "
                if expected:
                    self.assertIn(report + f"{checksum.count('0')} of its 64 digits 0, such as a mistyped placeholder; "
                                  "until release v1.0.14 is published, run tools/set-release-links.py with the zero "
                                  "placeholder", output)
                    # The closing advice is the placeholder's, as the report says.
                    self.assertIn("site-src/release.json holds a checksum close to the zero placeholder. Until release "
                                  "v1.0.14 is published, run tools/set-release-links.py for version 1.0.14 with the "
                                  "zero placeholder", output)
                    self.assertNotIn("Flip the site with tools/set-release-links.py using the published", output)
                    self.assertNotIn("holds the zero placeholder of a version bump", output)
                else:
                    self.assertNotIn(report, output)

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
    # The report of the gate itself, whole-page equality with the page tools/build-site.py renders.
    EQUAL = "site/verify/index.html is not the page tools/build-site.py renders for it from the committed sources"

    def test_any_other_page_fails_by_whole_page_equality(self):
        # Whatever the rule reads or misses, a page that is not the
        # generator's render fails, each with the same report, in either state.
        for checksum, state in ((SUM, "holds a published checksum"), (ZEROS, "holds the zero placeholder")):
            page = verify_page("1.0.14", checksum)
            for label, changed in (
                ("a contradicting step 3", outside(page, "<p>Correction to step 3: if the two values match, delete "
                                                         "the file.</p>")),
                ("a reworded step 3", outside(page, "<p>Never install the file when the values match.</p>")),
                ("a character added at the end", page + " "),
                ("a carriage return", page.replace("\n", "\r\n", 1)),
                ("the html attributes in another order",
                 page.replace('<html lang="en" class="site-cleanlanguage">', '<html class="site-cleanlanguage" lang="en">')),
            ):
                with self.subTest(f"{label}, {state}"):
                    self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % checksum)
                    gate.VERIFY_PAGE.write_bytes(changed.encode("utf-8"))
                    code, output = self.run_gate()
                    self.assertEqual(code, 1, output)
                    self.assertIn(f"{self.EQUAL}, while site-src/release.json {state} (", output)
                    self.assertIn("; run tools/build-site.py", output)

    def test_the_render_is_read_only_for_a_release_json_that_agrees_with_skill_md(self):
        # The generator refuses such a release.json, so the gate reports it as before and does not render.
        def refuse() -> bytes:
            raise AssertionError("rendered for a release.json that disagrees with SKILL.md")

        gate.rendered_verify_page = refuse
        self.write(gate.RELEASE_JSON, '{"version": "1.0.13", "tag": "v1.0.13", "checksum": "%s"}' % SUM)
        code, output = self.run_gate()
        self.assertEqual(code, 1, output)
        self.assertIn("release.json names version '1.0.13', but SKILL.md says 1.0.14", output)

    def test_a_render_that_fails_stops_the_gate(self):
        def fail() -> bytes:
            raise LookupError("tools/build-site.py could not render the verify page: refused")

        gate.rendered_verify_page = fail
        code, output = self.run_gate()
        self.assertEqual(code, 3)
        self.assertIn("check-release-links: tools/build-site.py could not render the verify page: refused", output)

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

    def test_the_closing_advice_fits_the_state(self):
        # While release.json holds the zero placeholder, there is no published checksum
        # to flip the site to, so the advice is to rerun the writer with the placeholder until the release publishes.
        self.write(gate.INSTALL_PAGE, "<p>No download here.</p>")
        code, output = self.pending(PENDING.format(v="1.0.14"))
        self.assertEqual(code, 1, output)
        self.assertIn("site-src/release.json holds the zero placeholder of a version bump. Until release v1.0.14 is "
                      "published, run tools/set-release-links.py for version 1.0.14 with that placeholder", output)
        self.assertNotIn("Flip the site with tools/set-release-links.py using the published", output)
        self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % SUM)
        self.write(gate.VERIFY_PAGE, VERIFY.format(v="1.0.14", sum=SUM))
        code, output = self.run_gate()
        self.assertEqual(code, 1, output)
        self.assertIn("Flip the site with tools/set-release-links.py using the published", output)
        self.assertNotIn("holds the zero placeholder of a version bump", output)
        # Whole-page equality refuses a page edited by hand, so the advice names only
        # the writer and the generator.
        self.assertIn("then run tools/build-site.py", output)
        self.assertNotIn("by hand", output)

    def test_comments_nested_too_deeply_fail_without_a_traceback(self):
        # 400 nested comment openers before step 1 make PageReader recurse past the
        # interpreter's limit; the rule reports it as 1 problem, in either state, never an uncaught RecursionError.
        deep = "<!--" * 400 + "-->"
        for checksum, page, state in ((SUM, VERIFY.format(v="1.0.14", sum=SUM), self.SHOWS),
                                      (ZEROS, PENDING.format(v="1.0.14"), self.HOLDS)):
            with self.subTest(state):
                self.write(gate.RELEASE_JSON, '{"version": "1.0.14", "tag": "v1.0.14", "checksum": "%s"}' % checksum)
                step = page.index('<p class="lbl blk">Step 1</p>')
                self.write(gate.VERIFY_PAGE, page[:step] + deep + page[step:])
                code, output = self.run_gate()
                self.assertEqual(code, 1, output)
                self.assertIn("site/verify/index.html nests comments too deeply to be read" + state, output)
                self.assertNotIn("Traceback", output)

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
        # Outside the block, the page
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
            # In the text, the value also counts in groups.
            ("64 hexadecimal digits in groups of 8", "<p>" + " ".join(SUM[i:i + 8] for i in range(0, 64, 8)) + "</p>",
             "carries a 64 digit hexadecimal value outside the download block"),
            ("64 hexadecimal digits in groups split by markup, hyphens and colons",
             "<p>" + "<span>-</span>".join(SUM[i:i + 16] for i in range(0, 64, 16)).replace("-", ": ", 1) + "</p>",
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

    def test_placeholder_note_beside_other_links_keeps_the_rule(self):
        # A link to the zip, directly or through its redirect, and a value that is not a URL are not links to
        # the checksum file, so the rule passes; the page is still not the generator's, so the gate refuses it.
        page = outside(PENDING.format(v="1.0.14"), '<a href="/download">zip</a><a href="http://[x">x</a>')
        block = gate.download_block("1.0.14", ZEROS)
        self.assertEqual(gate.download_block_problems(page, block, gate.REDIRECTS.read_text(encoding="utf-8")), [])
        code, output = self.pending(page)
        self.assertEqual(code, 1, output)
        self.assertIn(self.EQUAL + ", while site-src/release.json holds the zero placeholder (first at line ", output)
        self.assertNotIn("outside the download block", output)

    def test_published_checksum_without_the_rest_of_its_state_fails(self):
        # Any change to the block, such as a
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
        # A part of the block hidden or commented out, or a wrong checksum
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
            # An end tag does not close an element across a template or a
            # table, as in a browser.
            ("a template that ends the doc div around the block",
             page[:start] + '<template></div><div class="doc">' + page[start:end] + "</div></template>" + page[end:],
             self.PLACED),
            ("a details element misnested in a table before the block",
             page[:start] + "<details><table></details>" + page[start:], self.PLACED),
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
        self._saved_source = (gate.RELEASE_JSON, gate.INSTALL_PAGE, gate.rendered_verify_page)
        gate.rendered_verify_page = fixture_render
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
        gate.RELEASE_JSON, gate.INSTALL_PAGE, gate.rendered_verify_page = self._saved_source
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


def exclude_draft_home(root: Path) -> None:
    """Exclude the draft's home page from the sitemap under ``root``, as the draft branch does: tools/build-site.py
    refuses to build a staged draft without that exclusion."""
    path = root / "tools/sitemap-config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["exclude"] = [entry for entry in data["exclude"] if entry != "draft/index.html"] + ["draft/index.html"]
    path.write_text(json.dumps(data), encoding="utf-8")


class WriterTest(unittest.TestCase):
    """set-release-links.py regenerates the pages it owns, restamps them and keeps every redirect."""

    REPO = Path(__file__).resolve().parent.parent
    INPUTS = (
        "tools/build-site.py",
        "tools/check-install-page.py",
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

    def test_a_staged_draft_gets_the_redirects_and_no_live_page(self):
        # While a draft is staged, the writer writes what the offline gate's draft advice
        # says: site/_redirects, release.json, the modified dates in site.json and the draft's pages, no live page.
        site_json = self.root / "site-src/site.json"
        text = site_json.read_text(encoding="utf-8")
        self.assertEqual(text.count('"base": "/",'), 1)
        site_json.write_text(text.replace('"base": "/",', '"base": "/draft/",'), encoding="utf-8")
        exclude_draft_home(self.root)
        planned = self.plan()
        for name in ("site/_redirects", "site-src/release.json", "site-src/site.json", "site/draft/verify/index.html"):
            self.assertIn(name, planned)
        self.assertEqual([name for name in planned if name.startswith("site/") and not name.startswith("site/draft/")],
                         ["site/_redirects"])
        self.assertEqual(sorted(name for name in planned if not name.startswith("site/")),
                         ["site-src/release.json", "site-src/site.json"])

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
        note = (f"The checksum for version {self.next} appears here once that version is published; compare the "
                "checksum of your file with it then.")
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

    def write_links(self, checksum: str) -> tuple[int, str]:
        """Run set-release-links.py's main on the copy for ``checksum``, returning its exit code and stderr."""
        argv = ["set-release-links.py", "--version", self.next, "--checksum", checksum, "--date", "2026-11-04"]
        err = io.StringIO()
        with unittest.mock.patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            try:
                code = writer.main()
            except SystemExit as stop:
                code = stop.code
        return code, err.getvalue()

    def test_a_checksum_close_to_the_placeholder_is_refused(self):
        # The writer refuses a checksum other than the zero placeholder with 56 or more of its 64
        # digits 0, such as a mistyped placeholder, before it writes anything, and the gate fails one written by hand
        # (exit 1, not the generator's refusal). The zero placeholder, 55 digits 0 and a real-looking checksum pass.
        release = self.root / "site-src/release.json"
        before = release.read_bytes()
        for checksum in ("0" * 63 + "1", "0" * 56 + "89abcdef"):
            with self.subTest(checksum):
                code, err = self.write_links(checksum)
                self.assertEqual(code, 2, err)
                self.assertIn(f"set-release-links: {checksum} is not the zero placeholder but has "
                              f"{checksum.count('0')} of its 64 digits 0, such as a mistyped placeholder", err)
                self.assertEqual(release.read_bytes(), before)
        for checksum in (ZEROS, "0" * 55 + "123456789", "1234abcd" * 8):
            with self.subTest(checksum):
                self.assertEqual(self.write_links(checksum), (0, ""))
                self.assertEqual(json.loads(release.read_text(encoding="utf-8"))["checksum"], checksum)
                self.assertEqual(self.gate_code(), 0)
        release.write_text(release.read_text(encoding="utf-8").replace("1234abcd" * 8, "0" * 63 + "1"),
                           encoding="utf-8")
        self.assertEqual(self.gate_code(), 1)

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
                     "/downloads/cleanlanguage-short.md /downloads/cleanlanguage-instructions-11k.md 301",
                     "/downloads/cleanlanguage.md /downloads/cleanlanguage-instructions.md 302",
                     "/downloads/cleanlanguage-29k.md /downloads/cleanlanguage-instructions-29k.md 302",
                     "/downloads/cleanlanguage-11k.md /downloads/cleanlanguage-instructions-11k.md 302",
                     "/downloads/cleanlanguage-8k.md /downloads/cleanlanguage-instructions-8k.md 302",
                     f"/download https://github.com/jposluns/cleanlanguage/releases/download/v{self.next}/cleanlanguage-{self.next}.zip 302"):
            self.assertIn(line + "\n", redirects)
        self.assertEqual(len(redirects.splitlines()), 14)

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


class RedirectHopTest(unittest.TestCase):
    """Each rule of the committed site/_redirects that stays on this site names a file under site/ that is not an
    HTML file, is not the source of a rule and does not start with a splat source without its *, and each rule to
    another origin names a target the writer documents.

    The test reads a destination as RFC 3986 parses it, with urllib.parse.urlsplit. A destination is a URL when it
    has a scheme, such as https://cleanlanguage.ai/downloads/file.md, or starts with //, such as
    //cleanlanguage.ai/downloads/file.md, which takes the scheme of the origin it answers on; any other destination
    is a path. A query or fragment is not part of the path, so /downloads/file.md?from=x and /downloads/file.md#top
    name the file /downloads/file.md, and a :// in a query or fragment does not make a path a URL. A URL is on the
    origin that site-src/site.json gives when its scheme and its authority, the text after its // up to the first
    /, ? or #, are the origin's, ignoring letter case. So a URL that adds a port or user details to the origin is
    read as on another origin, and so is //downloads/file.md, whose authority is the host downloads. A destination
    stays on this site when it is a path or a URL on the origin, which the test reads as its path, or as / when its
    path is empty, as in https://cleanlanguage.ai?x=1, and holds to the same checks as a path. A destination that
    urlsplit cannot read, such as http://[x/file.md, fails.
    A destination that holds a control character (U+0000 to U+001F) or a space anywhere, or a backslash, fails
    before the test reads it. The basic URL parser of the WHATWG URL Standard, which browsers follow, removes every
    leading and trailing control character or space and every tab and newline before it reads a URL,
    percent-encodes any other control character, and reads a backslash as / in an https URL. urlsplit strips only
    the leading ones and keeps a backslash, so a destination of U+0001 followed by //example.com/file.md, or
    /\\example.com/file.md, would read here as a path while a browser goes to example.com. The test refuses such a
    destination rather than strip it, since the host that reads site/_redirects need not strip it as a browser does.
    A destination on this site must be a file under site/: the path itself, or its index.html when the path ends
    with a slash. tools/build-site.py writes the generated pages into site/ and the rest of site/ is committed, so the
    committed tree is the tree the site serves. A destination that is the source of a rule, or that starts with a
    splat source (a source ending in *) without its *, would send the reader through a second hop and fails, as
    does a destination with no file. The test reads sources only in those 2 forms: a source with a placeholder
    (:name), or with a * before its end, is not treated, so a destination that only such a source matches passes
    unseen. A destination with an empty or . segment, such as /downloads//file.md, fails, since the file the test
    finds under site/ is not the path as written, and so does one with a .. segment. A destination that names an
    HTML file, such as /install/index.html, fails too: the site serves each page at its folder path, and the host
    may answer a path that names the HTML file with a redirect of its own. A destination on another origin passes
    only when it is 1 of the targets the writer documents: the release zip and its checksum for the version in
    site-src/release.json, and the privacy page. The test does not follow a destination on another origin, so it does
    not count the hops that host takes. A line that is neither blank nor a comment fails unless it holds 3 fields,
    and a file with no rule fails.
    """

    REPO = Path(__file__).resolve().parent.parent

    def off_site_targets(self) -> set[str]:
        release = json.loads((self.REPO / "site-src/release.json").read_text(encoding="utf-8"))
        zip_url = (f"https://github.com/jposluns/cleanlanguage/releases/download/{release['tag']}"
                   f"/cleanlanguage-{release['version']}.zip")
        return {zip_url, zip_url + ".sha256", "https://posluns.ca/privacy/"}

    def origin(self) -> str:
        return json.loads((self.REPO / "site-src/site.json").read_text(encoding="utf-8"))["origin"]

    def failures(self, site: Path) -> list[str]:
        """Each line of site/_redirects under ``site`` that breaks the rule above, with its first reason."""
        found, rules = [], []
        for number, line in enumerate((site / "_redirects").read_text(encoding="utf-8").splitlines(), 1):
            fields = line.split()
            if not fields or fields[0].startswith("#"):
                continue
            if len(fields) != 3:
                found.append(f"site/_redirects line {number} is not 'source destination status'")
                continue
            rules.append((number, fields[0], fields[1]))
        if not rules:
            found.append("site/_redirects holds no rule")
        sources = {source for _, source, _ in rules}
        splats = [source[:-1] for source in sources if source.endswith("*")]
        off_site, origin = self.off_site_targets(), urllib.parse.urlsplit(self.origin())
        for number, source, destination in rules:
            where = f"site/_redirects line {number}: {source} redirects to {destination}"
            # The WHATWG URL Standard's basic URL parser removes leading and trailing control characters (U+0000 to
            # U+001F) and spaces and every tab and newline, and reads \ as / in an https URL; urlsplit strips only the
            # leading ones. Refusing them all makes the text below the text a browser reads.
            if any(character <= " " or character == "\\" for character in destination):
                found.append(f"{where}, which holds a control character, a space or a backslash, so a browser may "
                             "not read it as written")
                continue
            try:
                url = urllib.parse.urlsplit(destination)
            except ValueError:
                found.append(f"{where}, which urllib.parse cannot read as a URL")
                continue
            # urlsplit gives an empty netloc both for no authority and for an empty one, so a destination that
            # starts with // is a URL by its own text; the check above leaves nothing that urlsplit strips before it.
            is_url = bool(url.scheme) or destination.startswith("//")
            on_origin = is_url and ((url.scheme or origin.scheme).lower(), url.netloc.lower()) == (
                origin.scheme.lower(), origin.netloc.lower())
            path = (url.path or "/") if on_origin else url.path
            parts = path.strip("/").split("/")
            splat = next((prefix for prefix in splats if path.startswith(prefix)), None)
            target = site.joinpath(*parts)
            if path.endswith("/"):
                target = target / "index.html"
            if is_url and not on_origin:
                if destination not in off_site:
                    found.append(f"{where}, on an origin other than this site's and not a documented target")
            elif not path.startswith("/"):
                found.append(f"{where}, which is not a path on this site")
            elif path in sources:
                found.append(f"{where}, the source of another rule: 2 hops")
            elif splat is not None:
                found.append(f"{where}, which the splat source {splat}* matches: 2 hops")
            elif "." in path[1:].split("/") or "" in path[1:].split("/")[:-1]:
                found.append(f"{where}, which has an empty or . segment, so it does not name its file as written")
            elif ".." in parts:
                found.append(f"{where}, which leaves site/")
            elif not path.endswith("/") and parts[-1].lower().endswith((".html", ".htm")):
                found.append(f"{where}, which names an HTML file that the host may redirect again: 2 hops")
            elif not target.is_file():
                found.append(f"{where}, which is not a file under site/")
        return found

    def test_every_committed_redirect_keeps_the_rule(self):
        self.assertEqual(self.failures(self.REPO / "site"), [])

    def test_a_destination_that_names_an_html_file_fails(self):
        origin = self.origin()
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "install").mkdir()
            for name in ("install/index.html", "about.html", "About.HTM"):
                (site / name).write_text("<p>page</p>\n", encoding="utf-8")
            (site / "_redirects").write_text("/get /install/index.html 301\n/old-about /about.html 301\n"
                                             "/older-about /About.HTM 301\n/go /install/ 301\n"
                                             f"/origin-about {origin}/about.html 301\n", encoding="utf-8")
            reason = "which names an HTML file that the host may redirect again: 2 hops"
            self.assertEqual(self.failures(site), [
                f"site/_redirects line 1: /get redirects to /install/index.html, {reason}",
                f"site/_redirects line 2: /old-about redirects to /about.html, {reason}",
                f"site/_redirects line 3: /older-about redirects to /About.HTM, {reason}",
                f"site/_redirects line 5: /origin-about redirects to {origin}/about.html, {reason}",
            ])

    def failures_on(self, redirects: str, files: tuple[str, ...]) -> list[str]:
        """failures() on a site under $TMPDIR with ``redirects`` as its _redirects and a file at each of ``files``,
        each a path relative to the site folder, which sits 1 folder below the temporary folder."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        site = Path(tmp.name) / "site"
        site.mkdir()
        for name in files:
            (site / name).parent.mkdir(parents=True, exist_ok=True)
            (site / name).write_text("file\n", encoding="utf-8")
        (site / "_redirects").write_text(redirects, encoding="utf-8")
        return self.failures(site)

    def test_a_line_without_3_fields_fails(self):
        self.assertEqual(self.failures_on("/a /a.md\n/b /b.md 301 extra\n# a comment line\n\n/c /c.md 301\n",
                                          ("a.md", "b.md", "c.md")), [
            "site/_redirects line 1 is not 'source destination status'",
            "site/_redirects line 2 is not 'source destination status'",
        ])

    def test_a_file_with_no_rule_fails(self):
        self.assertEqual(self.failures_on("# a comment line\n\n", ()), ["site/_redirects holds no rule"])

    def test_a_destination_on_another_origin_that_is_not_documented_fails(self):
        zip_url = sorted(url for url in self.off_site_targets() if url.endswith(".zip"))[0]
        origin = self.origin()
        plain = origin.replace("https://", "http://", 1)
        user = origin.replace("://", "://user@", 1)
        rules = (f"/privacy https://posluns.ca/privacy/ 301\n/download {zip_url} 302\n"
                 f"/download/checksum {zip_url}.sha256 302\n/elsewhere https://example.com/privacy/ 301\n"
                 f"/plain {plain}/a.md 301\n/lookalike {origin}.example.com/a.md 301\n/port {origin}:8443/a.md 301\n"
                 f"/user {user}/a.md 301\n/network //downloads/a.md 301\n/other //example.com/a.md 301\n")
        reason = "on an origin other than this site's and not a documented target"
        self.assertEqual(self.failures_on(rules, ("a.md",)), [
            f"site/_redirects line 4: /elsewhere redirects to https://example.com/privacy/, {reason}",
            f"site/_redirects line 5: /plain redirects to {plain}/a.md, {reason}",
            f"site/_redirects line 6: /lookalike redirects to {origin}.example.com/a.md, {reason}",
            f"site/_redirects line 7: /port redirects to {origin}:8443/a.md, {reason}",
            f"site/_redirects line 8: /user redirects to {user}/a.md, {reason}",
            f"site/_redirects line 9: /network redirects to //downloads/a.md, {reason}",
            f"site/_redirects line 10: /other redirects to //example.com/a.md, {reason}",
        ])

    def test_a_destination_on_this_sites_origin_is_read_as_its_path(self):
        # A URL on this site's origin that reaches its file in 1 hop passes, as its path does: with its scheme
        # and host in any letter case, with no path or a query or fragment straight after its host, which the test
        # reads as /, and without a scheme, which it takes from the origin.
        origin = self.origin()
        network = origin.partition(":")[2]
        rules = (f"/a {origin}/downloads/a.md 302\n/b {origin.upper()}/downloads/a.md 302\n"
                 f"/c {origin}/page/ 301\n/d {origin} 301\n/e {origin}?x=1 301\n/f {origin}#top 301\n"
                 f"/g {origin}/downloads/a.md?x=1#top 302\n/h {network}/downloads/a.md 302\n")
        self.assertEqual(self.failures_on(rules, ("downloads/a.md", "page/index.html", "index.html")), [])

    def test_a_query_or_fragment_is_not_part_of_the_path(self):
        # A path with a query or fragment names the file of its path, a :// in either does not make it a URL, and
        # its path is still held to the checks, such as the one for the source of a rule.
        origin = self.origin()
        rules = (f"/a /downloads/a.md?x=1 302\n/b /downloads/a.md#top 302\n/c /downloads/a.md?from={origin} 302\n"
                 f"/d /downloads/a.md#{origin} 302\n/e /?x=1 301\n/f /b.md?x=1 301\n/b.md /downloads/a.md 301\n")
        self.assertEqual(self.failures_on(rules, ("downloads/a.md", "index.html")), [
            "site/_redirects line 6: /f redirects to /b.md?x=1, the source of another rule: 2 hops",
        ])

    def test_a_destination_that_urlsplit_cannot_read_fails(self):
        self.assertEqual(self.failures_on("/a http://[x/a.md 301\n/b /a.md 301\n", ("a.md",)), [
            "site/_redirects line 1: /a redirects to http://[x/a.md, which urllib.parse cannot read as a URL",
        ])

    def test_a_destination_without_a_leading_slash_fails(self):
        self.assertEqual(self.failures_on("/a downloads/a.md 301\n", ("downloads/a.md",)), [
            "site/_redirects line 1: /a redirects to downloads/a.md, which is not a path on this site",
        ])

    def test_a_destination_that_is_the_source_of_a_rule_fails(self):
        origin = self.origin()
        self.assertEqual(self.failures_on(f"/a /b.md 301\n/b.md /c.md 301\n/d {origin}/b.md 301\n",
                                          ("b.md", "c.md")), [
            "site/_redirects line 1: /a redirects to /b.md, the source of another rule: 2 hops",
            f"site/_redirects line 3: /d redirects to {origin}/b.md, the source of another rule: 2 hops",
        ])

    def test_a_destination_that_a_splat_source_matches_fails(self):
        origin = self.origin()
        self.assertEqual(self.failures_on(f"/a /old/file.md 301\n/old/* /new.md 301\n/b /older.md 301\n"
                                          f"/c {origin}/old/file.md 301\n",
                                          ("old/file.md", "new.md", "older.md")), [
            "site/_redirects line 1: /a redirects to /old/file.md, which the splat source /old/* matches: 2 hops",
            f"site/_redirects line 4: /c redirects to {origin}/old/file.md, which the splat source /old/* matches: "
            "2 hops",
        ])

    def test_a_destination_with_an_empty_or_dot_segment_fails(self):
        # A path that starts with // is a URL to another host, so its case is the one for another origin; on the
        # origin, a // after the host is an empty segment.
        origin = self.origin()
        reason = "which has an empty or . segment, so it does not name its file as written"
        self.assertEqual(self.failures_on(f"/a /downloads//a.md 301\n/b /downloads/./a.md 301\n"
                                          f"/c {origin}//downloads/a.md 301\n/d /downloads/a.md 301\n/e / 301\n",
                                          ("downloads/a.md", "index.html")), [
            f"site/_redirects line 1: /a redirects to /downloads//a.md, {reason}",
            f"site/_redirects line 2: /b redirects to /downloads/./a.md, {reason}",
            f"site/_redirects line 3: /c redirects to {origin}//downloads/a.md, {reason}",
        ])

    def test_a_destination_that_leaves_the_site_fails(self):
        origin = self.origin()
        self.assertEqual(self.failures_on(f"/a /../outside.md 301\n/b {origin}/../outside.md 301\n",
                                          ("../outside.md",)), [
            "site/_redirects line 1: /a redirects to /../outside.md, which leaves site/",
            f"site/_redirects line 2: /b redirects to {origin}/../outside.md, which leaves site/",
        ])

    def test_a_destination_with_a_control_character_space_or_backslash_fails(self):
        # Each destination below reaches a file as urlsplit reads it, yet a browser strips a leading or trailing
        # control character, percent-encodes any other, and reads \ as /, so it goes to another host or asks for
        # another path. str.split() ends a field at a space, tab or newline, so those cannot reach the check.
        reason = "which holds a control character, a space or a backslash, so a browser may not read it as written"
        destinations = ("\x01//example.com/a.md", "\x08//example.com/downloads/a.md", "\x00//example.com/a.md",
                        "/a.md\x01", "/downloads/\x1ba.md", "/\\example.com/a.md", "/downloads\\a.md")
        rules = "".join(f"/r{number} {destination} 301\n" for number, destination in enumerate(destinations, 1))
        files = ("a.md", "downloads/a.md", "a.md\x01", "downloads/\x1ba.md", "\\example.com/a.md", "downloads\\a.md")
        self.assertEqual(self.failures_on(rules + "/plain /a.md 301\n", files), [
            f"site/_redirects line {number}: /r{number} redirects to {destination}, {reason}"
            for number, destination in enumerate(destinations, 1)
        ])

    def test_a_destination_with_no_file_fails(self):
        origin = self.origin()
        self.assertEqual(self.failures_on(f"/a /missing.md 301\n/b /folder/ 301\n/c /page/ 301\n"
                                          f"/d {origin}/missing.md 301\n",
                                          ("folder/other.md", "page/index.html")), [
            "site/_redirects line 1: /a redirects to /missing.md, which is not a file under site/",
            "site/_redirects line 2: /b redirects to /folder/, which is not a file under site/",
            f"site/_redirects line 4: /d redirects to {origin}/missing.md, which is not a file under site/",
        ])


class OldNameTest(unittest.TestCase):
    """No scanned file names an old name of a portable instructions file outside the redirect rule that answers
    for it.

    The old names are the sources of the 302 rules in the committed site/_redirects that send a path under
    /downloads/ to a cleanlanguage-instructions file, so this test does not write them out. Each may appear only
    inside the text of its own rule, '<old path> <new path> 302', as site/_redirects, redirects_body() in
    tools/set-release-links.py and test_the_redirects_keep_every_fixed_path write it. A name counts where no letter,
    digit, underscore, dot or hyphen comes directly before it and no letter, digit, underscore or hyphen comes
    directly after it, as in a path, a URL, a link or an attachment filename. The scan reads every file under
    SCANNED outside a __pycache__ folder: the hand-edited files that carry links and references to the instructions
    files (INSTALL.md, .aiqt/gensrc.json, the workflows, site/_headers, site/README.md, the page sources and
    site-src/site.json), the generated pages and the downloads beside them, and the tools. A missing entry of
    SCANNED fails. Residual: a file outside SCANNED, and an old name written in another form, such as
    percent-encoded or in other letter case, pass unseen.
    """

    REPO = Path(__file__).resolve().parent.parent
    SCANNED = ("INSTALL.md", ".aiqt/gensrc.json", ".github/workflows", "site", "site-src", "tools")

    @staticmethod
    def renames(root: Path) -> list[tuple[str, str, str]]:
        """The rule text, old file name and new file name of each 302 rule for a renamed instructions file."""
        found = []
        for line in (root / "site/_redirects").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if (len(fields) == 3 and fields[2] == "302" and fields[0].startswith("/downloads/")
                    and fields[1].startswith("/downloads/cleanlanguage-instructions")):
                found.append((" ".join(fields), fields[0].rsplit("/", 1)[1], fields[1].rsplit("/", 1)[1]))
        return found

    def references(self, root: Path) -> list[str]:
        """Each old name a scanned file under ``root`` holds outside its rule, as 'path:line: name'."""
        renames = self.renames(root)
        if not renames:
            return ["site/_redirects: no 302 rule for a renamed instructions file"]
        names = re.compile(r"(?<![\w.-])(" + "|".join(re.escape(old) for _, old, _ in renames) + r")(?![\w-])")
        found = []
        for entry in self.SCANNED:
            start = root / entry
            if start.is_file():
                paths = [start]
            elif start.is_dir():
                paths = sorted(path for path in start.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
            else:
                found.append(f"{entry}: missing")
                continue
            for path in paths:
                for number, line in enumerate(path.read_bytes().decode("utf-8", "replace").split("\n"), 1):
                    for rule, _, _ in renames:
                        line = line.replace(rule, "")
                    found.extend(f"{path.relative_to(root).as_posix()}:{number}: {match.group(1)}"
                                 for match in names.finditer(line))
        return found

    def fixture(self, files: dict[str, str]) -> Path:
        """A tree under $TMPDIR with every SCANNED entry, the committed site/_redirects and ``files``."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for entry in self.SCANNED:
            if entry.endswith((".md", ".json")):
                (root / entry).parent.mkdir(parents=True, exist_ok=True)
                (root / entry).write_text("\n", encoding="utf-8")
            else:
                (root / entry).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.REPO / "site/_redirects", root / "site/_redirects")
        for relative, text in files.items():
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_text(text, encoding="utf-8")
        return root

    def old(self) -> dict[str, str]:
        return {new: old for _, old, new in self.renames(self.REPO)}

    def test_no_committed_file_names_an_old_name(self):
        self.assertEqual(len(self.renames(self.REPO)), 4)
        self.assertEqual(self.references(self.REPO), [])

    def test_an_old_name_outside_its_rule_fails(self):
        old = self.old()
        whole, n29 = old["cleanlanguage-instructions.md"], old["cleanlanguage-instructions-29k.md"]
        n11, n8 = old["cleanlanguage-instructions-11k.md"], old["cleanlanguage-instructions-8k.md"]
        blob = "https://github.com/jposluns/cleanlanguage/blob/main/site/downloads/"
        raw = "https://raw.githubusercontent.com/jposluns/cleanlanguage/main/site/downloads/"
        root = self.fixture({
            "site/_headers": f"/downloads/{n8}\n  Content-Disposition: attachment; filename=\"{n11}\"\n",
            "INSTALL.md": f"1. Download the [instructions](https://cleanlanguage.ai/downloads/{whole}).\n",
            "site-src/pages/demo.html": f"<p>Read {raw}{n8} first.</p>\n",
            "site-src/pages/install.html": f"<a href=\"{blob}{whole}\">source</a>\n",
            ".aiqt/gensrc.json": f"{{\"target\": \"site/downloads/{n29}\"}}\n",
            ".github/workflows/sync.yml": f"# Keeps {n29} current.\n",
            "tools/writer.py": f"RULE = \"/downloads/{n11} /downloads/cleanlanguage-instructions-11k.md 301\"\n",
        })
        # The rule text in tools/writer.py carries 301, not 302, so it is not the rule that answers for the name.
        self.assertEqual(self.references(root), [
            f"INSTALL.md:1: {whole}",
            f".aiqt/gensrc.json:1: {n29}",
            f".github/workflows/sync.yml:1: {n29}",
            f"site/_headers:1: {n8}",
            f"site/_headers:2: {n11}",
            f"site-src/pages/demo.html:1: {n8}",
            f"site-src/pages/install.html:1: {whole}",
            f"tools/writer.py:1: {n11}",
        ])

    def test_the_rule_text_and_the_new_names_pass(self):
        rules = "".join(f"    f\"{rule}\\n\"\n" for rule, _, _ in self.renames(self.REPO))
        news = "".join(f"/downloads/{new}\n  Content-Disposition: attachment; filename=\"{new}\"\n"
                       for new in self.old())
        root = self.fixture({"tools/writer.py": f"BODY = (\n{rules})\n", "site/_headers": news})
        self.assertEqual(self.references(root), [])

    def test_a_missing_scanned_entry_fails(self):
        root = self.fixture({})
        shutil.rmtree(root / "site-src")
        self.assertEqual(self.references(root), ["site-src: missing"])

    def test_a_name_counts_only_at_a_name_boundary(self):
        whole = self.old()["cleanlanguage-instructions.md"]
        lines = [
            (f"Download {whole}.", True), (f"<a href=\"/downloads/{whole}?v=1\">", True), (whole, True),
            (f"x{whole}", False), (f"1{whole}", False), (f"_{whole}", False), (f".{whole}", False), (f"-{whole}", False),
            (f"{whole}x", False), (f"{whole}1", False), (f"{whole}_", False), (f"{whole}-", False),
        ]
        root = self.fixture({"INSTALL.md": "".join(text + "\n" for text, _ in lines)})
        self.assertEqual(self.references(root),
                         [f"INSTALL.md:{number}: {whole}" for number, (_, counts) in enumerate(lines, 1) if counts])

    def test_a_pycache_folder_is_not_scanned(self):
        n11 = self.old()["cleanlanguage-instructions-11k.md"]
        root = self.fixture({"tools/__pycache__/writer.cpython-312.pyc": f"/downloads/{n11}\n",
                             "tools/writer.py": f"/downloads/{n11}\n"})
        self.assertEqual(self.references(root), [f"tools/writer.py:1: {n11}"])


class WholePageTest(unittest.TestCase):
    """The gate on a copy of the generator's inputs with the real tools/build-site.py: the committed verify page is
    the generator's render, and every page form that test_every_listed_page_form_fails lists, in either state, fails."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        for relative in WriterTest.INPUTS:
            source, target = WriterTest.REPO / relative, root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)
        self.root = root
        self.page = root / "site/verify/index.html"
        generator_spec = importlib.util.spec_from_file_location("build_site_for_whole_page", gate.GENERATOR)
        self.generator = importlib.util.module_from_spec(generator_spec)
        generator_spec.loader.exec_module(self.generator)

    def tearDown(self):
        self._tmp.cleanup()

    def gate_run(self) -> tuple[int, str]:
        saved = {name: getattr(gate, name) for name in ReleaseSourceTest.NAMES}
        gate.REPO_ROOT, gate.SITE_ROOT = self.root, self.root / "site"
        gate.SKILL = self.root / "cleanlanguage/skills/cleanlanguage/SKILL.md"
        gate.REDIRECTS = self.root / "site/_redirects"
        gate.INSTALL_PAGE = self.root / "site/install/index.html"
        gate.VERIFY_PAGE = self.page
        gate.RELEASE_JSON = self.root / "site-src/release.json"
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    code = gate.main()
                except SystemExit as stop:
                    code = stop.code
        finally:
            for name, value in saved.items():
                setattr(gate, name, value)
        return code, out.getvalue()

    def publish(self, checksum: str) -> str:
        """Set ``checksum`` in the copy's release.json and regenerate the copy's site, returning the verify page."""
        release_path = self.root / "site-src/release.json"
        release = json.loads(release_path.read_text(encoding="utf-8"))
        release["checksum"] = checksum
        release_path.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.generator.main(["--root", str(self.root)]), 0)
        return self.page.read_text(encoding="utf-8")

    def test_the_committed_verify_page_is_the_render(self):
        self.assertEqual((WriterTest.REPO / "site/verify/index.html").read_bytes(),
                         self.generator.verify_page(WriterTest.REPO))

    def test_every_listed_page_form_fails(self):
        version = json.loads((self.root / "site-src/release.json").read_text(encoding="utf-8"))["version"]
        note = (f"<p>The checksum for version {version} appears here once that version is published; compare the "
                "checksum of your file with it then.</p>")
        for checksum, state in ((ZEROS, "holds the zero placeholder"), (SUM, "holds a published checksum")):
            page = self.publish(checksum)
            code, output = self.gate_run()
            self.assertEqual(code, 0, output)
            start, end = page.index('<p class="lbl blk">Step 1</p>'), page.index('<div class="next">')
            block = page[start:end]
            forms = [
                ("step 3 wrapped in a hidden div on the page alone", page.replace('<p class="lbl blk">Step 3</p>',
                                                                                  '<div hidden><p class="lbl blk">Step 3</p>', 1)
                 .replace('<div class="next">', '</div><div class="next">', 1)),
                ("a template that ends the doc div around the block",
                 page[:start] + '<template></div><div class="doc">' + block + "</div></template>" + page[end:]),
                ("a contradicting step 3 outside the block",
                 outside(page, "<p>Correction to step 3: if the two values match, delete the file.</p>")),
                ("a reworded step 3 outside the block",
                 outside(page, '<p class="lbl blk">Step 3</p>\n<p>Never install the file when the values match.</p>')),
                ("a second checksum in groups of 8",
                 outside(page, "<p>" + " ".join(OTHER[i:i + 8] for i in range(0, 64, 8)) + "</p>")),
                ("a details element misnested in a table before step 1",
                 page[:start] + "<details><table></details>" + page[start:]),
                ("the html attributes in another order",
                 page.replace('<html lang="en" class="site-cleanlanguage">', '<html class="site-cleanlanguage" lang="en">')),
                ("a double space in step 1", page.replace("<p>Download the skill.", "<p>Download the  skill.", 1)),
                ("the note in a comment", outside(page, "<!-- " + note + " -->")),
                ("zeros in a code.sum", outside(page, '<code class="sum">' + ZEROS + "</code>")),
                ("a step that says to install the file anyway, before the next-page link",
                 outside(page, "<p>If the values differ, install the file anyway.</p>")),
                ("a step 4 after step 3",
                 outside(page, '<p class="lbl blk">Step 4</p>\n<p>Install the file.</p>\n')),
                ("the block inside noscript markup",
                 page[:start] + '<noscript></div><div class="doc">' + block + "</noscript>" + page[end:]),
                ("the block inside select markup",
                 page[:start] + '<select></div><div class="doc">' + block + "</select>" + page[end:]),
                ("a details element misnested in a span before step 1",
                 page[:start] + "<span><details></span>" + page[start:]),
                ("an inline script that removes the block",
                 outside(page, "<script>document.querySelector('.download').remove()</script>")),
                ("a second checksum joined by U+200B",
                 outside(page, "<p>" + "\u200b".join(OTHER[i:i + 8] for i in range(0, 64, 8)) + "</p>")),
                ("a second checksum joined by dots",
                 outside(page, "<p>" + ".".join(OTHER[i:i + 8] for i in range(0, 64, 8)) + "</p>")),
            ]
            if checksum != ZEROS:
                code_element = CODE.format(sum=checksum)
                step_3 = page[page.index('<p class="lbl blk">Step 3</p>'):end]
                forms += [
                    ("a commented canonical element beside a wrong one",
                     page.replace(code_element, "<!-- " + code_element + ' --><code id="published-checksum" class="sum">'
                                  + OTHER + "</code>")),
                    ("a hidden step 3", page.replace(step_3, "<div hidden>" + step_3 + "</div>")),
                    ("a reversed step 3", page.replace("If the values still differ", "If the values match")),
                ]
            for label, changed in forms:
                with self.subTest(f"{label}, {state}"):
                    self.assertNotEqual(changed, page)
                    self.page.write_text(changed, encoding="utf-8")
                    code, output = self.gate_run()
                    self.assertEqual(code, 1, output)
                    self.assertIn("site/verify/index.html is not the page tools/build-site.py renders for it from the "
                                  f"committed sources, while site-src/release.json {state} (first at line ", output)
            self.page.write_text(page, encoding="utf-8")

    def test_a_staged_draft_names_promotion_as_the_remedy(self):
        # With a draft staged under /draft/ and one nav label changed, tools/build-site.py
        # writes only site/draft/, so the correct live page is not the render; the gate says so and names promotion,
        # and still fails a wrong live page. Without a draft, it still says to run tools/build-site.py.
        # The advice says what each tool writes and points to the whole promotion.
        staged = ("site-src/site.json names base /draft/, so a draft is staged: tools/build-site.py writes only the "
                  "draft, and tools/set-release-links.py writes site/_redirects, site-src/release.json, the modified "
                  "dates in site-src/site.json and the draft's pages, so neither writes the live verify page, and this "
                  "gate renders that page at base / from the sources, the draft's changes included.")
        remedy = ("Promotion after the owner approves it is the remedy: the pull request of step 5 under \"Staging at "
                  "/draft/ and promotion\" in .baseline/README.md, of which tools/build-site.py --base / --promote is "
                  "1 step.")
        readme = (WriterTest.REPO / ".baseline/README.md").read_text(encoding="utf-8")
        self.assertIn("### Staging at `/draft/` and promotion\n", readme)
        self.assertIn("\n5. Promotion, after the owner's approval only. In 1 pull request from the `draft` branch to the "
                      "production branch: ", readme)
        for checksum, state in ((ZEROS, "holds the zero placeholder"), (SUM, "holds a published checksum")):
            with self.subTest(state):
                site_json = self.root / "site-src/site.json"
                original = site_json.read_text(encoding="utf-8")
                sitemap_config = self.root / "tools/sitemap-config.json"
                original_sitemap = sitemap_config.read_text(encoding="utf-8")
                page = self.publish(checksum)
                wrong = outside(page, "<p>If the values differ, install the file anyway.</p>")
                self.page.write_text(wrong, encoding="utf-8")
                code, output = self.gate_run()
                self.assertEqual(code, 1, output)
                self.assertIn(f"site-src/release.json {state} (first at line ", output)
                self.assertIn("; run tools/build-site.py\n", output)
                self.assertNotIn("a draft is staged", output)
                self.page.write_text(page, encoding="utf-8")
                config = json.loads(original)
                config["base"] = "/draft/"
                next(entry for entry in config["pages"] if entry["id"] == "install")["nav_label"] = "Install it"
                site_json.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
                exclude_draft_home(self.root)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(self.generator.main(["--root", str(self.root)]), 0)
                self.assertEqual(self.page.read_text(encoding="utf-8"), page)
                self.assertTrue((self.root / "site/draft/verify/index.html").is_file())
                for label, written in (("the correct live page", page), ("a wrong live page", wrong)):
                    self.page.write_text(written, encoding="utf-8")
                    code, output = self.gate_run()
                    self.assertEqual(code, 1, f"{label}: {output}")
                    self.assertIn(f"site-src/release.json {state} (first at line ", output)
                    self.assertIn("); a draft is staged (see below)\n", output)
                    self.assertIn(staged, output)
                    self.assertIn(remedy, output)
                    self.assertNotIn("; run tools/build-site.py", output)
                site_json.write_text(original, encoding="utf-8")
                sitemap_config.write_text(original_sitemap, encoding="utf-8")
                self.page.write_text(page, encoding="utf-8")

    def test_a_staged_draft_gets_no_draft_advice_for_another_failure(self):
        # With a draft staged under /draft/ and the verify page the render, a stale
        # site/_redirects fails with no draft advice: tools/set-release-links.py rewrites it, and the promotion
        # build does not.
        site_json, redirects = self.root / "site-src/site.json", self.root / "site/_redirects"
        version = json.loads((self.root / "site-src/release.json").read_text(encoding="utf-8"))["version"]
        text = site_json.read_text(encoding="utf-8")
        self.assertEqual(text.count('"base": "/",'), 1)
        site_json.write_text(text.replace('"base": "/",', '"base": "/draft/",'), encoding="utf-8")
        exclude_draft_home(self.root)
        code, output = self.gate_run()
        self.assertEqual(code, 0, output)
        written = redirects.read_text(encoding="utf-8")
        self.assertIn(f"/v{version}/", written)
        redirects.write_text(written.replace(f"/v{version}/", "/v0.0.1/", 1), encoding="utf-8")
        code, output = self.gate_run()
        self.assertEqual(code, 1, output)
        self.assertIn(f"site/_redirects uses tag v0.0.1 for version {version}", output)
        self.assertRegex(output, r"[Ff]lip the site with tools/set-release-links\.py")
        self.assertNotIn("a draft is staged", output)
        self.assertNotIn("Promotion", output)


class WorkflowPathsTest(unittest.TestCase):
    """The offline gate holds the verify page to the generator's render, so
    .github/workflows/link-check.yml runs it on a pull request or a push to main that changes the generator or any
    input it reads (WriterTest.INPUTS): each trigger lists a path filter that covers each of them."""

    COVERING = {
        "tools/build-site.py": "tools/build-site.py",
        "tools/check-install-page.py": "tools/check-install-page.py",
        "site-src": "site-src/**",
        "cleanlanguage/skills/cleanlanguage/SKILL.md": "cleanlanguage/**/*.md",
        "cleanlanguage/skills/cleanlanguage/references": "cleanlanguage/**/*.md",
        "site": "site/**",
        ".baseline/pin.toml": ".baseline/pin.toml",
        "tools/sitemap-config.json": "tools/sitemap-config.json",
    }

    def test_each_trigger_covers_every_generator_input(self):
        self.assertEqual(set(self.COVERING), set(WriterTest.INPUTS))
        references = WriterTest.REPO / "cleanlanguage/skills/cleanlanguage/references"
        self.assertEqual([path.name for path in references.rglob("*") if path.suffix != ".md"], [])
        text = (WriterTest.REPO / ".github/workflows/link-check.yml").read_text(encoding="utf-8")
        triggers = text.split("\n  push:\n")
        self.assertEqual(len(triggers), 2)
        for name, part in zip(("pull_request", "push"), triggers):
            for relative, pattern in self.COVERING.items():
                with self.subTest(f"{name}: {relative}"):
                    self.assertIn(f'      - "{pattern}"\n', part)


def load_faults(defined: str, renamed: str) -> list[tuple[str, object, str, type]]:
    """6 faults, each on its own copy of tools/build-site.py and each with the words of the writer's refusal and the
    exception that the gate's LookupError carries as its cause: the file missing, its mode 000, its mode 000 beside a
    valid cached file, a syntax error, the definition that starts with ``defined`` changed to start with ``renamed``,
    and a syntax error beside a cached file of the unbroken source that the normal loader runs without comparing it with
    the source (an unchecked hash-based file). For each fault but the renaming, that cause is the exception the load
    raises; the renamed copy loads, the gate's cause is the AttributeError that the render call raises when it reads the
    missing name, and the writer refuses the copy for that name. Beside a cached file, a tool that always reads the
    source gives that cause or refusal, and one that runs the cached file in its place does not. Root reads a file
    whatever its mode, so under root the 2 mode-000 faults skip their case instead."""
    def missing(path: Path) -> None:
        path.unlink()

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def locked(path: Path) -> None:
        os.chmod(path, 0)

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def cached_locked(path: Path) -> None:
        py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        os.chmod(path, 0)

    def broken(path: Path) -> None:
        path.write_bytes(path.read_bytes() + b"\ndef (\n")

    def rename(path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        if defined not in text:
            raise AssertionError(f"{defined!r} is not in {path.name}")
        path.write_text(text.replace(defined, renamed, 1), encoding="utf-8")

    def stale(path: Path) -> None:
        py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        broken(path)

    name = defined.removeprefix("def ").removesuffix("(")
    return [("missing", missing, "could not be read", FileNotFoundError),
            ("with mode 000", locked, "could not be read", PermissionError),
            ("with mode 000 beside a valid cached file", cached_locked, "could not be read", PermissionError),
            ("with a syntax error", broken, "could not be loaded", SyntaxError),
            (f"with {name} renamed", rename, f"defines no {name}", AttributeError),
            ("with a syntax error beside a stale cached file", stale, "could not be loaded", SyntaxError)]


def exits(code: int | None):
    """A fault that appends raise SystemExit(code), or a bare raise SystemExit when code is None, to
    tools/build-site.py, so that it exits while it loads."""
    def fault(path: Path) -> None:
        statement = "raise SystemExit" if code is None else f"raise SystemExit({code})"
        path.write_bytes(path.read_bytes() + f"\n{statement}\n".encode("ascii"))

    return fault


# Each code that exits() takes, with the exception as the gate's refusal names it.
EXITS = ((0, "SystemExit: 0"), (1, "SystemExit: 1"), (None, "SystemExit"))


class GeneratorLoadTest(unittest.TestCase):
    """A tools/build-site.py with each fault that load_faults() gives is a generator that cannot render, which the gate
    raises as LookupError and main() refuses with exit 3, and the writer refuses with exit 2. Neither runs a cached file
    in place of the source."""

    GENERATOR = Path(__file__).resolve().parent / "build-site.py"

    def faulted(self, root: Path, fault) -> Path:
        path = root / "tools" / "build-site.py"
        path.parent.mkdir()
        shutil.copyfile(self.GENERATOR, path)
        fault(path)
        return path

    def test_the_gate_raises_each_load_failure(self):
        for render, defined in ((lambda: gate.download_block("1.0.0", ZEROS), "def verify_download_block("),
                                (gate.rendered_verify_page, "def verify_page(")):
            for name, fault, _, cause in load_faults(defined, defined.replace("(", "_unused(")):
                with self.subTest(f"{defined}: tools/build-site.py {name}"), tempfile.TemporaryDirectory() as tmp:
                    path = self.faulted(Path(tmp), fault)
                    with unittest.mock.patch.object(gate, "GENERATOR", path), self.assertRaises(LookupError) as raised:
                        render()
                    self.assertTrue(str(raised.exception).startswith("tools/build-site.py could not render"),
                                    raised.exception)
                    self.assertIsInstance(raised.exception.__cause__, cause)
                    # The message ends with the cause's type and text, and for an OSError that text names the
                    # generator's path, so that the refusal says which file could not be read.
                    error = raised.exception.__cause__
                    self.assertTrue(str(raised.exception).endswith(f": {type(error).__name__}: {error}"),
                                    raised.exception)
                    if issubclass(cause, OSError):
                        self.assertIn(f": '{path}'", str(raised.exception))

    def test_the_gate_raises_a_generator_that_exits_while_it_loads(self):
        for site, render in (("download_block", lambda: gate.download_block("1.0.0", ZEROS)),
                             ("rendered_verify_page", gate.rendered_verify_page)):
            for code, shown in EXITS:
                with self.subTest(f"{site}: {shown} at import"), tempfile.TemporaryDirectory() as tmp:
                    path = self.faulted(Path(tmp), exits(code))
                    with unittest.mock.patch.object(gate, "GENERATOR", path), self.assertRaises(LookupError) as raised:
                        render()
                    self.assertTrue(str(raised.exception).startswith("tools/build-site.py could not render"),
                                    raised.exception)
                    # The message names the exception, so that the exit is never shown as a bare code or as nothing.
                    self.assertTrue(str(raised.exception).endswith(f": {shown}"), raised.exception)
                    self.assertIsInstance(raised.exception.__cause__, SystemExit)
                    self.assertEqual(raised.exception.__cause__.code, code)

    def test_the_gate_exits_3_when_the_generator_exits_while_it_loads(self):
        # The gate runs as a process on a copy of the generator's inputs, so that main()'s mapping to exit 3 is
        # observed, not inferred.
        for code, shown in EXITS:
            with self.subTest(f"{shown} at import"), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for relative in WriterTest.INPUTS + ("tools/check-release-links.py",):
                    source, target = WriterTest.REPO / relative, root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if source.is_dir():
                        shutil.copytree(source, target)
                    else:
                        shutil.copyfile(source, target)
                exits(code)(root / "tools/build-site.py")
                result = subprocess.run([sys.executable, "-I", str(root / "tools/check-release-links.py")],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                # main() renders the download block before the whole page, so the block's refusal is the one shown.
                self.assertIn("check-release-links: tools/build-site.py could not render the verify page's download "
                              f"block: {shown}\n", result.stderr)

    def test_the_writer_refuses_each_load_failure(self):
        release = {"version": "1.0.0", "tag": "v1.0.0", "checksum": ZEROS}
        for name, fault, words, _ in load_faults("def build(", "def build_unused("):
            with self.subTest(f"tools/build-site.py {name}"), tempfile.TemporaryDirectory() as tmp:
                self.faulted(Path(tmp), fault)
                stderr = io.StringIO()
                with (unittest.mock.patch.object(writer, "REPO_ROOT", Path(tmp)), contextlib.redirect_stderr(stderr),
                      self.assertRaises(SystemExit) as raised):
                    writer.site_pages(release, "2026-11-04")
                self.assertEqual(raised.exception.code, 2, stderr.getvalue())
                self.assertIn(f"set-release-links: tools/build-site.py {words}", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
