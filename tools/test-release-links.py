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
placeholder to a published checksum. They also pin that every rule of the
committed ``site/_redirects`` keeps the closed form that the docstring of
RedirectHopTest states, and that no scanned file names an old name of a portable
instructions file outside the redirect rule that answers for it. They run
offline with the standard library: the fixtures patch each module's file paths,
and the writer tests run it on a copy of the generator's inputs under $TMPDIR.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
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

    def write_links(self, checksum: str, version: str | None = None, date: str = "2026-11-04") -> tuple[int, str]:
        """Run set-release-links.py's main on the copy for ``checksum``, ``version`` (the next release when it is None;
        any other value, the empty string included, is passed as given) and ``date``, returning its exit code and
        stderr."""
        version = self.next if version is None else version
        argv = ["set-release-links.py", "--version", version, "--checksum", checksum, "--date", date]
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

    def test_a_version_or_date_with_a_final_newline_is_refused(self):
        # --version and --date are checked with a full match, so a value with a final LF is refused (exit 2) with
        # the reason of its form, before anything is written. A $ anchor would admit that LF past the form check, so
        # the value would be refused later, if at all, and with another reason.
        release = self.root / "site-src/release.json"
        before = release.read_bytes()
        with_lf = self.next + "\n"
        for version, date, reason in ((with_lf, "2026-11-04", f"{with_lf!r} is not a version number"),
                                      (None, "2026-11-04\n", "'2026-11-04\\n' is not a YYYY-MM-DD date")):
            with self.subTest(version=version, date=date):
                code, err = self.write_links(ZEROS, version, date)
                self.assertEqual(code, 2, err)
                self.assertIn(f"set-release-links: {reason}", err)
                self.assertEqual(release.read_bytes(), before)
        self.assertEqual(self.write_links(ZEROS), (0, ""))

    def test_an_empty_version_is_passed_to_the_writer_and_refused(self):
        # write_links passes an empty version to the writer as given, not as the next release, so the writer refuses
        # it (exit 2) with the reason of its form before anything is written. An omitted version is the next release.
        release = self.root / "site-src/release.json"
        before = release.read_bytes()
        code, err = self.write_links(ZEROS, "")
        self.assertEqual(code, 2, err)
        self.assertIn("set-release-links: '' is not a version number", err)
        self.assertEqual(release.read_bytes(), before)
        self.assertEqual(self.write_links(ZEROS), (0, ""))
        self.assertEqual(json.loads(release.read_text(encoding="utf-8"))["version"], self.next)

    def test_a_date_in_digits_outside_ascii_is_refused_for_its_form(self):
        # The --date form takes only the ASCII digits 0-9, so a date written wholly or partly in other Unicode digits
        # (Arabic-Indic, fullwidth or Devanagari here) is refused (exit 2) as not a YYYY-MM-DD date before anything is
        # written. Without re.ASCII, \d admits those digits, and the date is refused later with another reason.
        release = self.root / "site-src/release.json"
        before = release.read_bytes()
        # 2026-11-04 in each of those digits, and with only its last digit Arabic-Indic.
        dates = ["".join(chr(zero + int(c)) if c.isdigit() else c for c in "2026-11-04")
                 for zero in (0x660, 0xFF10, 0x966)]
        for date in dates + ["2026-11-0" + chr(0x664)]:
            with self.subTest(date=date):
                code, err = self.write_links(ZEROS, None, date)
                self.assertEqual(code, 2, err)
                self.assertIn(f"set-release-links: {date!r} is not a YYYY-MM-DD date", err)
                self.assertEqual(release.read_bytes(), before)
        self.assertEqual(self.write_links(ZEROS), (0, ""))

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


# The closed form of a source, and of a destination on this site: 1 or more segments, each a / then a lower-case
# ASCII letter or digit and then any of those, a dot, an underscore or a hyphen, with an optional final /.
REDIRECT_PATH = re.compile(r"(?:/[a-z0-9][a-z0-9._-]*)+/?", re.ASCII)
# The closed form of a documented target on another origin.
REDIRECT_TARGET = re.compile(r"https://[a-z0-9.-]+(?:/[A-Za-z0-9._-]+)+/?", re.ASCII)
# The closed form of a line of site/_redirects: bytes 0x20 to 0x7E only.
REDIRECT_LINE = re.compile(rb"[\x20-\x7e]*")
# Each reason RedirectHopTest gives, by key. Its class docstring lists every reason with the case that covers it, and
# test_the_docstring_lists_every_reason fails when the 2 lists differ or when a named case does not use its key.
REDIRECT_REASONS = {
    "alphabet": "holds a byte outside 0x20 to 0x7E, the space and printable ASCII",
    "fields": "is not 'source destination status'",
    "status": "has a status other than 301 or 302",
    "source": "has a source that is not a path in the closed form",
    "empty": "holds no rule",
    "target": "is not an https URL in the closed form, so no rule may name it",
    "form": "which is neither a documented target nor a path in the closed form",
    "hop": "which is a source, with or without a final /: 2 hops",
    "html": "which names an HTML file that the host may redirect: 2 hops",
    "file": "which is not a file under site/",
    "outside": "whose file resolves outside site/",
}


class RedirectHopTest(unittest.TestCase):
    """Every rule of the committed site/_redirects is in a closed form that every reader of it reads alike, and each
    rule that stays on this site reaches a file under site/ in 1 hop (Entry 133).

    The test refuses every line, rule and documented target outside this form:

    1. Every line, blank lines and comments included, holds only bytes 0x20 to 0x7E (the space and printable ASCII),
       and a line ends only at LF (REDIRECT_LINE). So no tab, CR, other control character, non-ASCII character or
       byte order mark can occur, and every reader ends lines and fields at the same places.
    2. A line that is neither blank nor a comment (a line whose first field starts with #) holds 3 fields split at
       runs of U+0020: source, destination and status. The status is 301 or 302.
    3. The source is a path in the closed form (REDIRECT_PATH): 1 or more segments, each a / then a lower-case ASCII
       letter or digit and then any of those, a dot, an underscore or a hyphen, with an optional final /. So no
       splat (*) or placeholder (:name) source can occur.
    4. The destination is byte-equal to a documented target, or is a path in the closed form. The documented targets
       are the release zip and its checksum for the version in site-src/release.json, and the privacy page. Each
       must itself be an https URL in the closed form of REDIRECT_TARGET, so a malformed release.json cannot widen
       the set. Every pattern is checked with re.fullmatch, since a $ anchor admits a final LF.
    5. A destination path is not a source, both read without a final /, since that takes a second hop. It does not
       end in .html or .htm, since the site serves each page at its folder path and the host may answer a path that
       names the HTML file with a redirect of its own. It names a file under site/, not a folder, the path itself or
       its index.html when the path ends with /, and that file resolves inside site/, so a symbolic link cannot point
       elsewhere.
       tools/build-site.py writes the generated pages into site/ and the rest of site/ is committed, so the
       committed tree is the tree the site serves.
    6. The file holds at least 1 rule.

    Why a path in the closed form is read alike: it starts with / and a letter or digit, so a browser resolving it
    on a page of this site keeps this site's host. It holds no character that a browser percent-encodes or reads as
    /, and no segment that a browser reads as a dot segment, so the browser asks for the path as written.
    Percent-decoding, Unicode normalization, lower-casing and trimming of white space each leave it unchanged, so a
    host that applies any of them reaches the same file. Neither path form admits an upper-case letter, so a host
    that folds letter case cannot make a destination equal a source.

    The test refuses what rules 1 to 6 do not admit, and nothing else; no line of the committed file, the output of
    redirects_body() in tools/set-release-links.py, is refused. A rule they do not admit, such as one with a URL that
    is not a documented target, a query, a splat source or another status, can be admitted later by widening a rule
    on purpose, with its own argument.

    The argument holds for a host whose reading of site/_redirects and of a request path leaves such lines, and paths
    in the alphabet a-z, 0-9, a dot, an underscore, a hyphen and /, as written. Its residual, stated plainly, lists
    what the test does not check. What the form refuses is the complement of the admitted form and is not part of
    the residual.

    - The host is not observed. A host that changes a string in that alphabet, for example by serving `/a` for
      `/a.html` (the HTML check covers this), by redirecting `/x/` to `/x`, or by treating a `.` in a path specially,
      is outside the argument. Unknown: Cloudflare Pages behaviour, which cannot be observed offline.
    - The 5 off-site rules are checked only as exact strings. The test does not follow them, so their hops at GitHub
      and posluns.ca stay unchecked.
    - The test reads the committed file. Whether the deployed file equals it is outside this test.
    - The closed form narrows the contract on purpose. An earlier version of this test read each destination as a
      browser would, and accepted URLs on this site's origin written in full and paths with a query or fragment.
      The inputs of the cases that pinned that wider reading were kept, and the cases of this class now expect each
      of them to be refused.

    Each reason the test gives, with the case that covers it (REDIRECT_REASONS holds the same reasons):

    - test_a_line_outside_printable_ascii_fails: holds a byte outside 0x20 to 0x7E, the space and printable ASCII
    - test_a_line_without_3_fields_fails: is not 'source destination status'
    - test_a_status_other_than_301_or_302_fails: has a status other than 301 or 302
    - test_a_source_outside_the_form_fails: has a source that is not a path in the closed form
    - test_a_file_with_no_rule_fails: holds no rule
    - test_a_documented_target_outside_its_form_fails: is not an https URL in the closed form, so no rule may name it
    - test_a_destination_outside_the_form_fails: which is neither a documented target nor a path in the closed form
    - test_a_destination_that_is_the_source_of_a_rule_fails: which is a source, with or without a final /: 2 hops
    - test_a_destination_that_names_an_html_file_fails: which names an HTML file that the host may redirect: 2 hops
    - test_a_destination_with_no_file_fails: which is not a file under site/
    - test_a_destination_that_resolves_outside_the_site_fails: whose file resolves outside site/
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
        """Each documented target outside its form, then each line of site/_redirects under ``site`` outside the form
        above, with its first reason (REDIRECT_REASONS)."""
        found, rules, targets = [], [], set()
        for target in sorted(self.off_site_targets()):
            if REDIRECT_TARGET.fullmatch(target):
                targets.add(target)
            else:
                found.append(f"the documented target {target!r} {REDIRECT_REASONS['target']}")
        # The alphabet is checked on the bytes, before any decoding, and a line ends only at LF.
        for number, line in enumerate((site / "_redirects").read_bytes().split(b"\n"), 1):
            if not REDIRECT_LINE.fullmatch(line):
                found.append(f"site/_redirects line {number} {REDIRECT_REASONS['alphabet']}")
                continue
            fields = [field for field in line.decode("ascii").split(" ") if field]
            if not fields or fields[0].startswith("#"):
                continue
            if len(fields) != 3:
                found.append(f"site/_redirects line {number} {REDIRECT_REASONS['fields']}")
            elif fields[2] not in ("301", "302"):
                found.append(f"site/_redirects line {number} {REDIRECT_REASONS['status']}")
            elif not REDIRECT_PATH.fullmatch(fields[0]):
                found.append(f"site/_redirects line {number} {REDIRECT_REASONS['source']}")
            else:
                rules.append((number, fields[0], fields[1]))
        if not rules:
            found.append(f"site/_redirects {REDIRECT_REASONS['empty']}")
        sources = {source.removesuffix("/") for _, source, _ in rules}
        root = site.resolve()
        for number, source, destination in rules:
            if destination in targets:
                continue
            if not REDIRECT_PATH.fullmatch(destination):
                reason = "form"
            elif destination.removesuffix("/") in sources:
                reason = "hop"
            elif destination.endswith((".html", ".htm")):
                reason = "html"
            else:
                target = site.joinpath(*destination.strip("/").split("/"))
                if destination.endswith("/"):
                    target = target / "index.html"
                if not target.is_file():
                    reason = "file"
                elif not target.resolve().is_relative_to(root):
                    reason = "outside"
                else:
                    continue
            found.append(f"site/_redirects line {number}: {source} redirects to {destination}, "
                         f"{REDIRECT_REASONS[reason]}")
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
                                             f"/origin-about {origin}/about.html 301\n/oldest /about.htm 301\n",
                                             encoding="utf-8")
            (site / "about.htm").write_text("<p>page</p>\n", encoding="utf-8")
            # /About.HTM and the URL on the origin are outside the closed form, so they fail on the form first.
            html, form = REDIRECT_REASONS["html"], REDIRECT_REASONS["form"]
            self.assertEqual(self.failures(site), [
                f"site/_redirects line 1: /get redirects to /install/index.html, {html}",
                f"site/_redirects line 2: /old-about redirects to /about.html, {html}",
                f"site/_redirects line 3: /older-about redirects to /About.HTM, {form}",
                f"site/_redirects line 5: /origin-about redirects to {origin}/about.html, {form}",
                f"site/_redirects line 6: /oldest redirects to /about.htm, {html}",
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
        # A field ends only at a space, and a run of spaces is 1 split. Fields split by tabs or by U+00A0 fail on the
        # line's alphabet before they are counted.
        fields, alphabet = REDIRECT_REASONS["fields"], REDIRECT_REASONS["alphabet"]
        self.assertEqual(self.failures_on("/a /a.md\n/b /b.md 301 extra\n# a comment line\n\n/c /c.md 301\n"
                                          "/d\t/d.md\t301\n/e\xa0/e.md\xa0301\n/f   /f.md  301  \n",
                                          ("a.md", "b.md", "c.md", "d.md", "e.md", "f.md")), [
            f"site/_redirects line 1 {fields}",
            f"site/_redirects line 2 {fields}",
            f"site/_redirects line 6 {alphabet}",
            f"site/_redirects line 7 {alphabet}",
        ])

    def test_a_field_ends_only_at_a_space(self):
        # Every byte that a line may hold, other than the space, belongs to a field, so a line whose 3 parts are
        # joined by any of them is 1 field and fails. A rule whose fields are split at a space passes.
        joiners = [chr(code) for code in range(0x21, 0x7F)]
        lines = [f"/a{joiner}/a.md{joiner}301" for joiner in joiners] + ["/b /b.md 301"]
        fields = REDIRECT_REASONS["fields"]
        self.assertEqual(self.failures_on("\n".join(lines) + "\n", ("a.md", "b.md")), [
            f"site/_redirects line {number} {fields}" for number in range(1, len(joiners) + 1)
        ])

    def test_a_line_whose_first_field_starts_with_a_hash_is_a_comment(self):
        # A line is a comment when its first field starts with #: the # alone or joined to text, with or without
        # spaces before it. A # in a later field does not make a line a comment, so that line fails.
        lines = ["# a comment line", "#a comment", "#", "##", "   # after spaces", " #after a space",
                 "#/c /a.md 301 extra", "/a /a.md 301", "/b /a.md 301 #not a comment"]
        self.assertEqual(self.failures_on("\n".join(lines) + "\n", ("a.md",)), [
            f"site/_redirects line {len(lines)} {REDIRECT_REASONS['fields']}",
        ])

    def test_a_file_with_no_rule_fails(self):
        self.assertEqual(self.failures_on("# a comment line\n\n", ()), [f"site/_redirects {REDIRECT_REASONS['empty']}"])

    def test_a_line_outside_printable_ascii_fails(self):
        # Every byte outside 0x20 to 0x7E fails its line, wherever it stands: in a destination (controls, a tab, CR
        # before LF, U+0085, U+00A0, U+2028, U+2029, U+3000 and a non-ASCII letter), between fields, in a comment, and
        # as a byte order mark or a byte that is not UTF-8. A blank line and a printable rule pass.
        destinations = ("\x01//example.com/a.md", "\x08//example.com/downloads/a.md", "\x00//example.com/a.md",
                        "/a.md\x01", "/downloads/\x1ba.md", "/a.md\t", "/downloads/\ra.md", "/a.md\x0b", "/a.md\x1f",
                        "/a.md\x7f", "/a.md\x85", "/a.md\x9f", "/a.md\xa0", "/a.md\u2028", "/a.md\u2029",
                        "/a.md\u3000", "/\xe9.md")
        lines = [f"/r{number} {destination} 301" for number, destination in enumerate(destinations, 1)]
        lines += ["/s\t/a.md\t301", "/t /a.md\x1f301", "# a comment with \xe9", "", "/plain /a.md 301",
                  "/u /a.md 301\r"]
        files = ("a.md", "downloads/a.md", "a.md\x01", "downloads/\x1ba.md", "a.md\x0b", "a.md\x1f", "a.md\x7f",
                 "a.md\x85", "a.md\x9f", "a.md\xa0", "a.md\u2028", "a.md\u2029", "a.md\u3000", "\xe9.md")
        alphabet = REDIRECT_REASONS["alphabet"]
        self.assertEqual(self.failures_on("\n".join(lines) + "\n", files), [
            f"site/_redirects line {number} {alphabet}" for number, line in enumerate(lines, 1)
            if line not in ("", "/plain /a.md 301")
        ])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        site = Path(tmp.name)
        (site / "a.md").write_text("file\n", encoding="utf-8")
        for body in (b"\xef\xbb\xbf/a /a.md 301\n", b"/a /a.md\xff 301\n"):
            (site / "_redirects").write_bytes(body)
            self.assertEqual(self.failures(site), [f"site/_redirects line 1 {alphabet}",
                                                   f"site/_redirects {REDIRECT_REASONS['empty']}"])

    def test_a_status_other_than_301_or_302_fails(self):
        status = REDIRECT_REASONS["status"]
        self.assertEqual(self.failures_on("/a /a.md 200\n/b /a.md 301\n/c /a.md 302\n/d /a.md 308\n/e /a.md 301!\n"
                                          "/f /a.md 404\n", ("a.md",)), [
            f"site/_redirects line 1 {status}",
            f"site/_redirects line 4 {status}",
            f"site/_redirects line 5 {status}",
            f"site/_redirects line 6 {status}",
        ])

    def test_a_source_outside_the_form_fails(self):
        # These are examples: a splat or placeholder source, a source in upper case, with a dot segment, a query, or as
        # a URL, and the root / each fail, and the rules they would have made are not read. A source with a final /
        # passes. test_the_path_rule_is_read_as_the_docstring_states checks rules 1 to 3, as a source, on each value
        # that its comment lists.
        origin, source = self.origin(), REDIRECT_REASONS["source"]
        rules = (f"/old/* /new.md 301\n/old/:name /new.md 301\n/Old /new.md 301\n/./old /new.md 301\n"
                 f"/old?x=1 /new.md 301\n{origin}/old /new.md 301\n/ /new.md 301\n/older/ /new.md 301\n"
                 f"/a /old/file.md 301\n")
        self.assertEqual(self.failures_on(rules, ("old/file.md", "new.md")), [
            f"site/_redirects line {number} {source}" for number in range(1, 8)
        ])

    def test_a_documented_target_outside_its_form_fails(self):
        # A documented target that is not an https URL in the closed form fails, so a malformed release.json cannot
        # widen the set, and a rule that names it fails on the form; one with a final LF fails, since the check is a
        # full match. The privacy page passes, and only byte-equal to the target, not in other letter case.
        targets = {"https://posluns.ca/privacy/", "https://github.com/a/b/v1.0.15/c.zip\n", "http://github.com/a/c.zip",
                   "https://github.com/a/b/v1.0.15/c.zip?x=1", "https://GitHub.com/a/c.zip"}
        rules = ("/privacy https://posluns.ca/privacy/ 301\n/a https://github.com/a/b/v1.0.15/c.zip 302\n"
                 "/b http://github.com/a/c.zip 302\n/c https://POSLUNS.ca/privacy/ 301\n")
        with unittest.mock.patch.object(self, "off_site_targets", return_value=targets):
            found = self.failures_on(rules, ())
        target, form = REDIRECT_REASONS["target"], REDIRECT_REASONS["form"]
        self.assertEqual(found, [
            f"the documented target {name!r} {target}" for name in sorted(targets - {"https://posluns.ca/privacy/"})
        ] + [
            f"site/_redirects line 2: /a redirects to https://github.com/a/b/v1.0.15/c.zip, {form}",
            f"site/_redirects line 3: /b redirects to http://github.com/a/c.zip, {form}",
            f"site/_redirects line 4: /c redirects to https://POSLUNS.ca/privacy/, {form}",
        ])

    def test_a_destination_outside_the_form_fails(self):
        # Each destination below is neither a documented target nor a path in the closed form, so it fails, though a
        # file exists under its literal name where 1 can. These are examples: URLs on another origin or on this site's
        # origin, a query or fragment, a destination that starts with // or does not start with /, an empty, ., .. or
        # percent-encoded segment, a backslash, an upper-case letter, a character outside a-z, 0-9, ., _, - and /, a
        # segment that starts with a dot, an underscore or a hyphen, and the root /. The documented targets and 2 paths
        # in the form pass. test_the_path_rule_is_read_as_the_docstring_states checks rules 1 and 2 and the path form of
        # rule 4, as a destination, on each value that its comment lists.
        origin = self.origin()
        zip_url = sorted(url for url in self.off_site_targets() if url.endswith(".zip"))[0]
        plain, user = origin.replace("https://", "http://", 1), origin.replace("://", "://user@", 1)
        refused = ("https://example.com/privacy/", f"{plain}/a.md", f"{origin}.example.com/a.md", f"{origin}:8443/a.md",
                   f"{user}/a.md", "//downloads/a.md", "//example.com/a.md", f"{origin}/downloads/a.md",
                   f"{origin.upper()}/downloads/a.md", f"{origin}/page/", origin, f"{origin}?x=1", f"{origin}#top",
                   f"{origin}/downloads/a.md?x=1#top", f"{origin.partition(':')[2]}/downloads/a.md",
                   "/downloads/a.md?x=1", "/downloads/a.md#top", f"/downloads/a.md?from={origin}",
                   f"/downloads/a.md#{origin}", "/?x=1", "/b.md?x=1", "http://[x/a.md", "downloads/a.md",
                   "/downloads//a.md", "/downloads/./a.md", f"{origin}//downloads/a.md", "/", "/../outside.md",
                   f"{origin}/../outside.md", "/downloads/%2e/a.md", "/downloads/%2E/a.md", "/%2e%2e/outside.md",
                   "/downloads/.%2E/a.md", "/downloads/%2e./a.md", f"{origin}/%2E%2e/outside.md", "/\\example.com/a.md",
                   "/downloads\\a.md", "/Downloads/a.md", "/a~b.md", "/a+b.md", "/.well-known/x.txt", "/a%2emd",
                   "/downloads%2fa.md", "/downloads/_a.md", "/downloads/-a.md")
        passed = (zip_url, f"{zip_url}.sha256", "https://posluns.ca/privacy/", "/downloads/a.md", "/page/")
        destinations = refused + passed
        rules = "".join(f"/r{number} {destination} 302\n" for number, destination in enumerate(destinations, 1))
        files = ("a.md", "downloads/a.md", "page/index.html", "index.html", "../outside.md", "downloads/%2e/a.md",
                 "downloads/%2E/a.md", "%2e%2e/outside.md", "downloads/.%2E/a.md", "downloads/%2e./a.md",
                 "%2E%2e/outside.md", "\\example.com/a.md", "downloads\\a.md", "Downloads/a.md", "a~b.md", "a+b.md",
                 ".well-known/x.txt", "a%2emd", "downloads%2fa.md", "downloads/_a.md", "downloads/-a.md")
        form = REDIRECT_REASONS["form"]
        self.assertEqual(self.failures_on(rules, files), [
            f"site/_redirects line {number}: /r{number} redirects to {destination}, {form}"
            for number, destination in enumerate(refused, 1)
        ])

    def test_the_path_rule_is_read_as_the_docstring_states(self):
        # The oracle reads rules 1 and 2 of the class docstring without a regular expression, and the closed path form,
        # which rule 3 applies to a source and rule 4 to a destination, segment by segment. The values are each value
        # of length 1 to 4 over the 11 characters /a0._-A%*:?; each value of length 1 or 2 over the 98 characters of
        # wide, 0x20 to 0x7E (the space and printable ASCII) and U+00E9, U+0430 and U+FF0F; and, for x of a or 0 and
        # each character w of wide, /xw, /xwx and /x/w, so that each of the 98 is run first in a segment, last after
        # its first character, between 2 others, and first in a second segment: 26196 values. failures() gives the
        # line of each value, as a source and as a destination, a reason of rule 1, of rule 2 or of the path form
        # exactly when the oracle does, and the same one. Residual: a value longer than 4 characters, a value of length
        # 3 or 4 that holds a character outside the 11 and is not 1 of those 3 forms, and a value that holds a
        # character outside 0x20 to 0x7E other than those 3 are not run; a destination in the path form is read on by
        # the rest of rules 4 and 5, which this case does not check; and the oracle binds this reading of rules 1 to 4,
        # not every word of the docstring.
        narrow, first = "/a0._-A%*:?", "abcdefghijklmnopqrstuvwxyz0123456789"
        wide = "".join(chr(code) for code in (*range(0x20, 0x7F), 0xE9, 0x430, 0xFF0F))

        def in_form(value: str) -> bool:
            # 1 or more segments, each a / then a letter or digit and then any of those, a dot, an underscore or a
            # hyphen, with an optional final /.
            segments = value.removesuffix("/").split("/")
            return len(segments) > 1 and segments[0] == "" and all(
                segment and segment[0] in first and set(segment) <= set(first + "._-") for segment in segments[1:])

        def strings(alphabet: str, longest: int) -> list[str]:
            # Each value of length 1 to longest over alphabet, shortest first.
            found, layer = [], [""]
            for _ in range(longest):
                layer = [value + char for value in layer for char in alphabet]
                found += layer
            return found

        placed = [value for x in "a0" for w in wide for value in (f"/{x}{w}", f"/{x}{w}{x}", f"/{x}/{w}")]
        values = list(dict.fromkeys(strings(narrow, 4) + strings(wide, 2) + placed))
        self.assertEqual(len(values), 26196)

        def reason(line: str, index: int, key: str) -> str | None:
            # Rule 1: only the space and printable ASCII. Rule 2: a comment, or 3 fields split at runs of spaces; each
            # line here ends with a status of 301 or 302. Rules 3 and 4: field ``index`` is a path in the closed form.
            if not all(" " <= char <= "~" for char in line):
                return "alphabet"
            fields = [field for field in line.split(" ") if field]
            if fields[0].startswith("#"):
                return None
            if len(fields) != 3:
                return "fields"
            return None if in_form(fields[index]) else key

        def given(rules: list[str], files: tuple[str, ...], key: str) -> set[tuple[str, str]]:
            # 1 rule per value, so the line number that a failure names gives its value back.
            names = ("alphabet", "fields", key)
            return {(values[int(line.split()[2].rstrip(":")) - 1], name)
                    for line in self.failures_on("".join(f"{rule}\n" for rule in rules), files)
                    for name in names if line.endswith(REDIRECT_REASONS[name])}

        sources = [f"{value} /a.md 301" for value in values]
        destinations = [f"/r{number} {value} 302" for number, value in enumerate(values, 1)]
        for rules, files, index, key in ((sources, ("a.md",), 0, "source"), (destinations, (), 1, "form")):
            with self.subTest(key=key):
                oracle = {(value, reason(rule, index, key)) for value, rule in zip(values, rules)}
                self.assertEqual(given(rules, files, key), {pair for pair in oracle if pair[1]})

    def test_a_destination_that_is_the_source_of_a_rule_fails(self):
        # A destination and a source are compared without a final /, so /f/ and /f, or /h and /h/, are 1 path, and a
        # rule to its own source fails as well. The URL on the origin fails on the form first.
        origin, hop = self.origin(), REDIRECT_REASONS["hop"]
        rules = ("/a /b.md 301\n/b.md /c.md 301\n/e /f/ 301\n/f /c.md 301\n/g /h 301\n/h/ /c.md 301\n/i /i 301\n"
                 f"/d {origin}/b.md 301\n")
        self.assertEqual(self.failures_on(rules, ("b.md", "c.md", "f/index.html", "h", "i")), [
            f"site/_redirects line 1: /a redirects to /b.md, {hop}",
            f"site/_redirects line 3: /e redirects to /f/, {hop}",
            f"site/_redirects line 5: /g redirects to /h, {hop}",
            f"site/_redirects line 7: /i redirects to /i, {hop}",
            f"site/_redirects line 8: /d redirects to {origin}/b.md, {REDIRECT_REASONS['form']}",
        ])

    def test_a_destination_that_resolves_outside_the_site_fails(self):
        # A symbolic link under site/ to a file, or to a folder, outside site/ fails; one to a file inside passes.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        site = Path(tmp.name) / "site"
        site.mkdir()
        (site.parent / "elsewhere").mkdir()
        for path in (site.parent / "outside.md", site.parent / "elsewhere" / "a.md", site / "real.md"):
            path.write_text("file\n", encoding="utf-8")
        (site / "link.md").symlink_to(site.parent / "outside.md")
        (site / "folder").symlink_to(site.parent / "elsewhere", target_is_directory=True)
        (site / "alias.md").symlink_to(site / "real.md")
        (site / "_redirects").write_text("/a /link.md 301\n/b /folder/a.md 301\n/c /alias.md 301\n/d /real.md 301\n",
                                         encoding="utf-8")
        outside = REDIRECT_REASONS["outside"]
        self.assertEqual(self.failures(site), [
            f"site/_redirects line 1: /a redirects to /link.md, {outside}",
            f"site/_redirects line 2: /b redirects to /folder/a.md, {outside}",
        ])

    # Rule lines on which a browser, urllib.parse and a host have been seen or shown to read a destination or the
    # fields differently, each with the key of the reason it fails with: URLs on this site's origin, with a query,
    # a fragment, user details, an empty, dot or percent-encoded dot segment, or under a splat source; destinations
    # that start with //; a percent-encoded slash or dot in a name; a segment that starts with a dot; and controls,
    # separators, invisible characters and letters outside ASCII, in a destination or between fields.
    DISAGREEMENTS = (
        ("/r https://cleanlanguage.ai/downloads/cleanlanguage-instructions-8k.md 302", "form"),
        ("/r https://cleanlanguage.ai?x=1 301", "form"),
        ("/r https://cleanlanguage.ai#top 301", "form"),
        ("/r https://cleanlanguage.ai/downloads/a.md?x=1 301", "form"),
        ("/r /downloads/a.md?x=1 301", "form"),
        ("/r /downloads/a.md#top 301", "form"),
        ("/r /downloads/a.md?from=https://cleanlanguage.ai 301", "form"),
        ("/r /downloads/a.md#https://x 301", "form"),
        ("/r //cleanlanguage.ai/downloads/a.md 301", "form"),
        ("/r //example.com/downloads/a.md 301", "form"),
        ("/r //downloads/a.md 301", "form"),
        ("/r https://user@cleanlanguage.ai/downloads/a.md 301", "form"),
        ("/r https://cleanlanguage.ai//downloads/a.md 301", "form"),
        ("/r https://cleanlanguage.ai/old/file.md 301", "form"),
        ("/r \x01//example.com/a.md 301", "alphabet"),
        ("/r \x08//example.com/downloads/a.md 302", "alphabet"),
        ("/r https://cleanlanguage.ai/about.html 301", "form"),
        ("/r https://cleanlanguage.ai/../outside.md 301", "form"),
        ("/a /a.md\x1f301", "alphabet"),
        ("/a /a.md\x1f 301", "alphabet"),
        ("/a /a.md\xa0301", "alphabet"),
        ("/a /a.md\N{IDEOGRAPHIC SPACE}301", "alphabet"),
        ("/a /a.md\N{EM SPACE}301", "alphabet"),
        ("/a /a.md\N{NARROW NO-BREAK SPACE}301", "alphabet"),
        ("/a /a.md\N{PARAGRAPH SEPARATOR}301", "alphabet"),
        ("/a /a.md\N{OGHAM SPACE MARK}301", "alphabet"),
        ("/a /a.md\x0b301", "alphabet"),
        ("/a /a.md\x0c301", "alphabet"),
        ("/a /a.md\r301", "alphabet"),
        ("/a /a.md\x1c301", "alphabet"),
        ("/a /a.md\x1d301", "alphabet"),
        ("/a /a.md\x1e301", "alphabet"),
        ("/r\t/a.md\t301", "alphabet"),
        ("/r /%2e%2e/outside.md 301", "form"),
        ("/r /downloads/%2E/a.md 301", "form"),
        ("/r https://cleanlanguage.ai/.%2e/outside.md 301", "form"),
        ("/r /downloads/%2e%2e 301", "form"),
        ("/r /a.md\x7f 301", "alphabet"),
        ("/r /a.md\N{ZERO WIDTH NO-BREAK SPACE} 301", "alphabet"),
        ("/r /\xe9.md 301", "alphabet"),
        ("/r //\N{FULLWIDTH LATIN SMALL LETTER C}leanlanguage.ai 301", "alphabet"),
        ("/r \x7f//example.com/a.md 301", "alphabet"),
        ("/r \N{ZERO WIDTH NO-BREAK SPACE}//example.com/a.md 301", "alphabet"),
        ("/r //ex\xe4mple.com 301", "alphabet"),
        ("/r https://cleanlanguag\xe9.ai 301", "alphabet"),
        ("/r //example.com\N{FULLWIDTH SOLIDUS}a.md 301", "alphabet"),
        ("/r /a.md\xad 301", "alphabet"),
        ("/r /a.md\N{ZERO WIDTH SPACE} 301", "alphabet"),
        ("/r /downloads%2fa.md 301", "form"),
        ("/r /a%2emd 301", "form"),
        ("/r /.well-known/x.txt 301", "form"),
    )

    def test_every_known_disagreement_is_refused(self):
        # Each line is refused on its own, with a file under its literal name where 1 can exist, so no other rule and
        # no missing file can be what refuses it.
        files = ("a.md", "downloads/a.md", "old/file.md", "about.html", "%2e%2e/outside.md", "downloads/%2E/a.md",
                 "downloads/%2e%2e", "a.md\x7f", "a.md\N{ZERO WIDTH NO-BREAK SPACE}", "\xe9.md", "a.md\xad",
                 "a.md\N{ZERO WIDTH SPACE}", "downloads%2fa.md", "a%2emd", ".well-known/x.txt",
                 "downloads/cleanlanguage-instructions-8k.md")
        for line, key in self.DISAGREEMENTS:
            with self.subTest(line=line):
                if key == "alphabet":
                    expected = [f"site/_redirects line 1 {REDIRECT_REASONS['alphabet']}",
                                f"site/_redirects {REDIRECT_REASONS['empty']}"]
                else:
                    source, destination, _ = line.split(" ")
                    expected = [f"site/_redirects line 1: {source} redirects to {destination}, "
                                f"{REDIRECT_REASONS['form']}"]
                self.assertEqual(self.failures_on(line + "\n", files), expected)

    def test_the_docstring_lists_every_reason(self):
        # The class docstring lists each reason of REDIRECT_REASONS once, with a case that exists and whose source
        # names the key of that reason. Residual: this binds the reason strings and the case names, not the meaning of
        # the prose around them.
        rows = re.findall(r"^- (test_\w+): (.+)$", inspect.cleandoc(type(self).__doc__), re.MULTILINE)
        self.assertEqual(sorted(reason for _, reason in rows), sorted(REDIRECT_REASONS.values()))
        keys = {reason: key for key, reason in REDIRECT_REASONS.items()}
        for name, reason in rows:
            case = getattr(type(self), name, None)
            self.assertTrue(callable(case), name)
            source = inspect.getsource(case)
            self.assertTrue(f'REDIRECT_REASONS["{keys[reason]}"]' in source
                            or f"REDIRECT_REASONS['{keys[reason]}']" in source, name)

    def test_a_destination_with_no_file_fails(self):
        # A destination names a file, so a missing file fails, and so does a folder: /folder/ with no index.html,
        # /folder itself, which exists without a final /, and /nested/, whose index.html is a folder. /page/ passes.
        origin = self.origin()
        self.assertEqual(self.failures_on(f"/a /missing.md 301\n/b /folder/ 301\n/c /page/ 301\n"
                                          f"/d {origin}/missing.md 301\n/e /folder 301\n/f /nested/ 301\n",
                                          ("folder/other.md", "page/index.html", "nested/index.html/other.md")), [
            f"site/_redirects line 1: /a redirects to /missing.md, {REDIRECT_REASONS['file']}",
            f"site/_redirects line 2: /b redirects to /folder/, {REDIRECT_REASONS['file']}",
            f"site/_redirects line 4: /d redirects to {origin}/missing.md, {REDIRECT_REASONS['form']}",
            f"site/_redirects line 5: /e redirects to /folder, {REDIRECT_REASONS['file']}",
            f"site/_redirects line 6: /f redirects to /nested/, {REDIRECT_REASONS['file']}",
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
