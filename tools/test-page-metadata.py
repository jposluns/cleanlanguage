#!/usr/bin/env python3
"""Tests for the page metadata gate's JSON-LD author requirement.

The gate must fail a page whose JSON-LD carries no author object with a
non-empty name, not merely check agreement when a name happens to be present.
These tests pin that requirement, and the check that the meta and JSON-LD
authors agree, on fixture pages. They run offline with the standard library.
Most fixtures patch the module's git readers, so no history is needed;
ProtectedLineHistoryTest builds its history with git in a temporary
repository, so git must be on PATH. The CI workflow invokes this file before
the gate runs against the real pages.

They also pin the gate's meta-tag parsing, its handling of an unreadable
(non-UTF-8) page, and its containment of image references to the site
directory.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import itertools
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parent / "check-page-metadata.py"
spec = importlib.util.spec_from_file_location("check_page_metadata", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

TODAY = "2026-01-03"

PAGE = """<!doctype html>
<html><head>
<meta name="author" content="Jeff Posluns">
<meta property="article:published_time" content="2026-01-01">
<meta property="article:modified_time" content="2026-01-02">
<meta property="article:author" content="https://posluns.ca">
{json_ld}
</head><body></body></html>
"""

FAQ_BLOCK = (
    '<script type="application/ld+json">'
    '{"@context": "https://schema.org", "@type": "FAQPage"}'
    "</script>"
)

NO_AUTHOR_MESSAGE = (
    "no JSON-LD primary content entity names an author matching the meta "
    "author; add a Person author whose name matches the meta author"
)
# The message when a primary content entity (Article, CreativeWork, ...) does
# not carry an accepted author matching the meta author.
WRONG_PRIMARY_AUTHOR = (
    "a primary JSON-LD content entity does not carry an author that is a "
    "Person object whose name matches the meta author"
)


def article(author_json: str) -> str:
    """An Article JSON-LD block whose author is the given JSON value."""
    return (
        '<script type="application/ld+json">'
        '{"@context": "https://schema.org", "@type": "Article",'
        ' "datePublished": "2026-01-01", "dateModified": "2026-01-02",'
        ' "author": ' + author_json + "}"
        "</script>"
    )


class AuthorRequirementTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (gate.REPO_ROOT, gate.added_date, gate.last_change_date)
        gate.REPO_ROOT = Path(self._tmp.name)
        gate.added_date = lambda relative: "2026-01-01"
        gate.last_change_date = lambda relative: "2026-01-02"

    def tearDown(self):
        gate.REPO_ROOT, gate.added_date, gate.last_change_date = self._saved
        self._tmp.cleanup()

    def check(self, json_ld: str) -> list[str]:
        page = Path(self._tmp.name) / "index.html"
        page.write_text(PAGE.format(json_ld=json_ld), encoding="utf-8")
        problems, _author = gate.check_page(page, TODAY)
        return problems

    def test_compliant_page_passes(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        self.assertEqual(self.check(article(author)), [])

    def test_extra_block_without_author_is_allowed(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        self.assertEqual(self.check(article(author) + FAQ_BLOCK), [])

    def test_page_without_json_ld_fails(self):
        self.assertEqual(self.check(""), [NO_AUTHOR_MESSAGE])

    def test_page_whose_blocks_carry_no_author_fails(self):
        self.assertEqual(self.check(FAQ_BLOCK), [NO_AUTHOR_MESSAGE])

    def test_author_without_name_fails(self):
        author = '{"@type": "Person"}'
        self.assertEqual(self.check(article(author)), [WRONG_PRIMARY_AUTHOR])

    def test_author_with_empty_name_fails(self):
        author = '{"@type": "Person", "name": ""}'
        self.assertEqual(self.check(article(author)), [WRONG_PRIMARY_AUTHOR])

    def test_author_that_is_not_an_object_fails(self):
        self.assertEqual(self.check(article('"Jeff Posluns"')), [WRONG_PRIMARY_AUTHOR])

    def test_primary_with_wrong_author_fails(self):
        # A primary entity whose author is not the meta author fails; it is not
        # excused as a secondary entity.
        author = '{"@type": "Person", "name": "Someone Else"}'
        self.assertEqual(self.check(article(author)), [WRONG_PRIMARY_AUTHOR])

    def test_commented_out_author_block_fails(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        self.assertEqual(self.check("<!-- " + article(author) + " -->"), [NO_AUTHOR_MESSAGE])

    def test_attribute_variation_block_is_recognized(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = article(author).replace(
            '<script type="application/ld+json">',
            "<script id='page-schema' type='application/ld+json'>",
        )
        self.assertEqual(self.check(block), [])

    def test_top_level_array_is_recognized(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = (
            '<script type="application/ld+json">'
            '[{"@context": "https://schema.org", "@type": "Article",'
            ' "datePublished": "2026-01-01", "dateModified": "2026-01-02",'
            ' "author": ' + author + "}]"
            "</script>"
        )
        self.assertEqual(self.check(block), [])

    def test_member_that_is_not_an_object_is_skipped(self):
        # A top-level array member that is a number or a string is not an
        # entity, so it is skipped beside the Article that names the author.
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = article(author).replace('<script type="application/ld+json">',
                                        '<script type="application/ld+json">[1, "x", ')
        block = block.replace("</script>", "]</script>")
        self.assertEqual(self.check(block), [])

    def test_unparseable_block_reports_one_message(self):
        malformed = '<script type="application/ld+json">{"@type": "Article" "author": {}}</script>'
        problems = self.check(malformed)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not parse", problems[0])

    def test_data_type_attribute_is_not_the_type(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = article(author).replace(
            '<script type="application/ld+json">',
            '<script type="text/plain" data-type="application/ld+json">',
        )
        self.assertEqual(self.check(block), [NO_AUTHOR_MESSAGE])

    def test_comment_delimiters_inside_json_are_preserved(self):
        author = (
            '{"@type": "Person", "name": "Jeff Posluns",'
            ' "description": "a <!-- b --> c"}'
        )
        self.assertEqual(self.check(article(author)), [])

    def test_quoted_angle_bracket_in_attribute_is_handled(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = article(author).replace(
            '<script type="application/ld+json">',
            '<script data-note="a > b" type="application/ld+json">',
        )
        self.assertEqual(self.check(block), [])

    def test_duplicate_type_first_ld_json_wins(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = article(author).replace(
            '<script type="application/ld+json">',
            '<script type="application/ld+json" type="text/javascript">',
        )
        self.assertEqual(self.check(block), [])

    def test_duplicate_type_first_non_ld_json_wins(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = article(author).replace(
            '<script type="application/ld+json">',
            '<script type="text/plain" type="application/ld+json">',
        )
        self.assertEqual(self.check(block), [NO_AUTHOR_MESSAGE])

    def test_nan_constant_is_reported_not_accepted(self):
        block = (
            '<script type="application/ld+json">'
            '{"@type": "Article", "author": {"name": "Jeff Posluns"},'
            ' "value": NaN}'
            "</script>"
        )
        problems = self.check(block)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not parse", problems[0])

    def test_oversized_int_is_reported_not_crashed(self):
        block = (
            '<script type="application/ld+json">'
            '{"@type": "Article", "author": {"name": "Jeff Posluns"},'
            ' "n": ' + ("1" * 5000) + "}"
            "</script>"
        )
        problems = self.check(block)
        self.assertEqual(len(problems), 1)
        self.assertIn("does not parse", problems[0])

    def test_author_as_array_is_accepted(self):
        author = '[{"@type": "Person", "name": "Jeff Posluns"}]'
        self.assertEqual(self.check(article(author)), [])

    def test_value_object_name_is_accepted(self):
        author = '{"@type": "Person", "name": {"@value": "Jeff Posluns"}}'
        self.assertEqual(self.check(article(author)), [])

    def test_secondary_entity_does_not_false_fail(self):
        block = (
            '<script type="application/ld+json">'
            '[{"@type": "Article", "datePublished": "2026-01-01",'
            ' "dateModified": "2026-01-02",'
            ' "author": {"@type": "Person", "name": "Jeff Posluns"}},'
            ' {"@type": "Comment", "datePublished": "2026-01-09",'
            ' "author": {"@type": "Person", "name": "Alice"}}]'
            "</script>"
        )
        self.assertEqual(self.check(block), [])

    def test_nbsp_wrapped_type_is_not_collected(self):
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        block = article(author).replace(
            '<script type="application/ld+json">',
            '<script type="\u00a0application/ld+json\u00a0">',
        )
        self.assertEqual(self.check(block), [NO_AUTHOR_MESSAGE])

    def test_self_closing_script_content_is_checked(self):
        # HTML does not honour self-closing on <script>; the following block is
        # its content and must be collected and checked, not silently dropped.
        author = '{"@type": "Person", "name": "Mallory"}'
        block = article(author).replace(
            '<script type="application/ld+json">',
            '<script type="application/ld+json"/>',
        )
        self.assertEqual(self.check(block), [WRONG_PRIMARY_AUTHOR])

    def test_wrong_primary_author_not_saved_by_secondary(self):
        # The primary Article has the wrong author; a secondary Comment that
        # names the meta author must not rescue it, which would be a false green.
        block = (
            '<script type="application/ld+json">'
            '[{"@type": "Article",'
            ' "author": {"@type": "Person", "name": "Mallory"}},'
            ' {"@type": "Comment",'
            ' "author": {"@type": "Person", "name": "Jeff Posluns"}}]'
            "</script>"
        )
        self.assertEqual(self.check(block), [WRONG_PRIMARY_AUTHOR])

    def test_non_person_author_type_fails(self):
        author = '{"@type": "PostalAddress", "name": "Jeff Posluns"}'
        self.assertEqual(self.check(article(author)), [WRONG_PRIMARY_AUTHOR])

    def test_creativework_primary_is_recognized(self):
        block = (
            '<script type="application/ld+json">'
            '{"@type": "CreativeWork",'
            ' "author": {"@type": "Person", "name": "Jeff Posluns"}}'
            "</script>"
        )
        self.assertEqual(self.check(block), [])

    def test_stray_coauthor_fails(self):
        # Single-author site: a stray or stale co-author on the primary entity
        # must fail, not be masked by the matching author.
        author = ('[{"@type": "Person", "name": "Jeff Posluns"},'
                  ' {"@type": "Person", "name": "Mallory"}]')
        self.assertEqual(self.check(article(author)), [WRONG_PRIMARY_AUTHOR])

    def test_unclosed_script_at_eof_is_checked(self):
        # A missing </script> at end of input must not drop (and thus hide) the
        # block; it is flushed, parsed, and checked.
        page = Path(self._tmp.name) / "index.html"
        page.write_text(
            "<!doctype html><html><head>"
            '<meta name="author" content="Jeff Posluns">'
            '<meta property="article:published_time" content="2026-01-01">'
            '<meta property="article:modified_time" content="2026-01-02">'
            '<meta property="article:author" content="https://posluns.ca">'
            '<script type="application/ld+json">'
            '{"@type": "Article", "author": {"@type": "Person", "name": "Mallory"}}',
            encoding="utf-8",
        )
        problems, _ = gate.check_page(page, TODAY)
        self.assertEqual(problems, [WRONG_PRIMARY_AUTHOR])


class ModifiedStampToleranceTest(unittest.TestCase):
    """The modified-stamp check tolerates a bounded window between the stamp and
    the file's last commit date, so a normal cross-day squash merge does not red
    the gate, while a stamp well beyond that window still flags a forgotten bump,
    and a future stamp is still rejected regardless."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (gate.REPO_ROOT, gate.added_date, gate.last_change_date)
        gate.REPO_ROOT = Path(self._tmp.name)

    def tearDown(self):
        gate.REPO_ROOT, gate.added_date, gate.last_change_date = self._saved
        self._tmp.cleanup()

    def check(self, *, published: str, modified: str, changed: str, today: str) -> list[str]:
        # A fully author-compliant page whose only varying inputs are the date
        # stamps, so each problem that can surface concerns its dates or its
        # history, such as the modified-stamp tolerance or a future stamp.
        # published_time equals the mocked added_date and the JSON-LD
        # dateModified equals the meta article:modified_time.
        gate.added_date = lambda relative: published
        gate.last_change_date = lambda relative: changed
        author = '{"@type": "Person", "name": "Jeff Posluns"}'
        json_ld = (
            '<script type="application/ld+json">'
            '{"@context": "https://schema.org", "@type": "Article",'
            f' "datePublished": "{published}", "dateModified": "{modified}",'
            ' "author": ' + author + "}"
            "</script>"
        )
        page_html = (
            "<!doctype html>\n<html><head>\n"
            '<meta name="author" content="Jeff Posluns">\n'
            f'<meta property="article:published_time" content="{published}">\n'
            f'<meta property="article:modified_time" content="{modified}">\n'
            '<meta property="article:author" content="https://posluns.ca">\n'
            + json_ld
            + "\n</head><body></body></html>\n"
        )
        page = Path(self._tmp.name) / "index.html"
        page.write_text(page_html, encoding="utf-8")
        problems, _author = gate.check_page(page, today)
        return problems

    def test_stamp_within_tolerance_passes(self):
        # modified = D (2026-01-10); the file last changed D + 4 days, within the
        # 7-day tolerance; today is well after both. A gate that flagged any
        # changed > modified would fail this page; the tolerance must pass it.
        problems = self.check(
            published="2026-01-01", modified="2026-01-10",
            changed="2026-01-14", today="2026-02-01")
        self.assertEqual(problems, [], problems)

    def test_stamp_beyond_tolerance_fails(self):
        # modified = D (2026-01-10); the file last changed D + 20 days, beyond the
        # 7-day tolerance; today is after both.
        problems = self.check(
            published="2026-01-01", modified="2026-01-10",
            changed="2026-01-30", today="2026-02-01")
        self.assertTrue(
            any("the file last changed" in p and "tolerance" in p for p in problems),
            problems)
        self.assertTrue(
            any("beyond the 7-day tolerance" in p for p in problems), problems)

    def test_stamp_exactly_at_tolerance_passes(self):
        # modified = D (2026-01-10); the file last changed exactly D + 7 days, the
        # last day within the 7-day tolerance. The check is `> tolerance`, so
        # exactly 7 passes; a `>=` check would fail this test.
        problems = self.check(
            published="2026-01-01", modified="2026-01-10",
            changed="2026-01-17", today="2026-02-01")
        self.assertEqual(problems, [], problems)

    def test_stamp_one_day_past_tolerance_fails(self):
        # modified = D (2026-01-10); the file last changed D + 8 days, 1 day past
        # the 7-day tolerance.
        problems = self.check(
            published="2026-01-01", modified="2026-01-10",
            changed="2026-01-18", today="2026-02-01")
        self.assertTrue(
            any("beyond the 7-day tolerance" in p for p in problems), problems)

    def test_modified_in_future_still_rejected(self):
        # modified is after today and equals changed, a 0-day gap within the 7-day
        # tolerance; the test needs a problem stating that the stamp is in the future.
        problems = self.check(
            published="2026-01-01", modified="2026-02-15",
            changed="2026-02-15", today="2026-02-01")
        self.assertTrue(
            any("is in the future" in p for p in problems), problems)

    def test_missing_or_malformed_stamp_reports_only_that_problem(self):
        # A page with no published or no modified stamp, or with one that is
        # not YYYY-MM-DD, such as one with a digit too few or too many in a
        # part, a letter in a part, or a line feed and more after the date,
        # reports that problem alone: the date checks skip a stamp that is
        # absent or malformed.
        gate.added_date = lambda relative: "2026-01-01"
        gate.last_change_date = lambda relative: "2026-01-02"
        page = Path(self._tmp.name) / "index.html"
        stamps = {"article:published_time": "2026-01-01", "article:modified_time": "2026-01-02"}
        malformed = (None, "Jan 2", "026-01-02", "02026-01-02", "2026-1-02", "2026-001-02", "2026-01-2",
                     "2026-01-002", "202A-01-02", "2026-0A-02", "2026-01-0A", "2026-01-02x", "2026-01-02\nx")
        for label, value in itertools.product(stamps, malformed):
            with self.subTest(label=label, value=value):
                meta = f'<meta property="{label}" content="{stamps[label]}">\n'
                new = "" if value is None else meta.replace(stamps[label], value)
                html = PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}'))
                page.write_text(html.replace(meta, new), encoding="utf-8")
                expected = f"missing {label}" if value is None else f"{label} is {value!r}, expected YYYY-MM-DD"
                self.assertEqual(gate.check_page(page, TODAY)[0], [expected])

    def test_page_with_no_history_reports_only_that(self):
        # A page for which git records no commit, so that no added date and
        # no last change date are read, reports that problem alone.
        gate.added_date = lambda relative: None
        gate.last_change_date = lambda relative: None
        page = Path(self._tmp.name) / "index.html"
        page.write_text(PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}')),
                        encoding="utf-8")
        self.assertEqual(gate.check_page(page, TODAY)[0],
                         ["git records no commit for this file, so its dates cannot be checked"])

    def test_published_override_excuses_the_published_stamp(self):
        # A page listed in PUBLISHED_OVERRIDES is not asked to match the date
        # that git shows it was added.
        gate.added_date = lambda relative: "2025-12-01"
        gate.last_change_date = lambda relative: "2026-01-02"
        page = Path(self._tmp.name) / "index.html"
        page.write_text(PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}')),
                        encoding="utf-8")
        self.assertTrue([p for p in gate.check_page(page, TODAY)[0] if p.startswith("article:published_time")])
        with mock.patch.dict(gate.PUBLISHED_OVERRIDES, {"index.html": "moved in"}):
            self.assertEqual(gate.check_page(page, TODAY)[0], [])

    def test_stamp_equal_to_today_passes(self):
        # A modified stamp of today is not in the future.
        problems = self.check(
            published="2026-01-01", modified="2026-02-01",
            changed="2026-02-01", today="2026-02-01")
        self.assertEqual(problems, [], problems)

    def test_invalid_calendar_date_is_reported_not_crashed(self):
        # An ISO-shaped but invalid date (fromisoformat rejects it) must produce
        # a clean problem, not a traceback: tolerance math that parsed the date
        # unguarded would raise ValueError here.
        problems = self.check(
            published="2026-01-01", modified="2026-13-40",
            changed="2026-01-14", today="2026-02-01")
        self.assertTrue(any("not a real calendar date" in p for p in problems), problems)

    def test_stamp_in_other_decimal_digits_has_the_form(self):
        # ISO_DATE reads \d as any decimal digit, so a modified stamp written
        # in Arabic-Indic digits has the form YYYY-MM-DD, and it is reported
        # as not a real calendar date, since dt.date.fromisoformat() does not
        # read those digits.
        stamp = "\u0662\u0660\u0662\u0666-\u0660\u0661-\u0661\u0660"
        problems = self.check(
            published="2026-01-01", modified=stamp,
            changed="2026-01-14", today="2026-02-01")
        self.assertEqual(problems, [f"article:modified_time {stamp} is not a real calendar date"])


GATE_PAGE = """<!doctype html>
<html><head>
{extra_meta}
<meta property="article:published_time" content="2026-01-01">
<meta property="article:modified_time" content="2026-01-02">
<meta property="article:author" content="https://posluns.ca">
{json_ld}
</head><body></body></html>
"""


class _PatchedGateTest(unittest.TestCase):
    """A temporary repository root with a site/ directory and stubbed git readers."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (gate.REPO_ROOT, gate.SITE_ROOT,
                       gate.added_date, gate.last_change_date)
        root = Path(self._tmp.name).resolve()
        gate.REPO_ROOT = root
        gate.SITE_ROOT = root / "site"
        gate.SITE_ROOT.mkdir()
        gate.added_date = lambda relative: "2026-01-01"
        gate.last_change_date = lambda relative: "2026-01-02"

    def tearDown(self):
        (gate.REPO_ROOT, gate.SITE_ROOT,
         gate.added_date, gate.last_change_date) = self._saved
        self._tmp.cleanup()


class UnreadablePageTest(_PatchedGateTest):
    def test_non_utf8_page_is_reported_unreadable_exit_3(self):
        page = gate.SITE_ROOT / "index.html"
        page.write_bytes(b"<html>\xff\xfe not utf-8</html>")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.check_page(page, TODAY)
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("could not read", stderr.getvalue())


class PageListTest(_PatchedGateTest):
    def test_refused_sitemap_configuration_exits_3(self):
        # A sitemap configuration that the shared engine refuses stops the
        # check with exit 3 and the engine's message.
        def refuse(path):
            raise gate.engine.EngineError("synthetic refusal")

        stderr = io.StringIO()
        with mock.patch.object(gate.engine, "load_config", refuse), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.content_pages()
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("check-page-metadata: synthetic refusal", stderr.getvalue())

    def test_no_content_pages_exits_3(self):
        # main() with full history and no content page stops with exit 3.
        stderr = io.StringIO()
        with mock.patch.object(gate, "require_full_history", lambda: None), \
                mock.patch.object(gate, "content_pages", lambda: []), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.main()
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("no content pages found", stderr.getvalue())


class MetaParsingTest(_PatchedGateTest):
    def check(self, author_meta: str, ld_author: str):
        page = gate.SITE_ROOT / "index.html"
        block = article('{"@type": "Person", "name": "' + ld_author + '"}')
        page.write_text(GATE_PAGE.format(extra_meta=author_meta, json_ld=block),
                        encoding="utf-8")
        return gate.check_page(page, TODAY)

    def test_quoted_gt_in_content_is_parsed(self):
        problems, author = self.check('<meta name="author" content="a > b">', "a > b")
        self.assertEqual(author, "a > b")
        self.assertEqual(problems, [])

    def test_single_quoted_meta_is_parsed(self):
        problems, author = self.check(
            "<meta name='author' content='Jeff Posluns'>", "Jeff Posluns")
        self.assertEqual(author, "Jeff Posluns")
        self.assertEqual(problems, [])

    def test_uppercase_self_closing_meta_is_parsed(self):
        problems, author = self.check(
            '<meta NAME="author" CONTENT="Jeff Posluns"/>', "Jeff Posluns")
        self.assertEqual(author, "Jeff Posluns")
        self.assertEqual(problems, [])

    def test_commented_meta_does_not_satisfy(self):
        problems, author = self.check(
            '<!-- <meta name="author" content="Jeff Posluns"> -->', "Jeff Posluns")
        self.assertIsNone(author)
        self.assertIn('missing <meta name="author">', problems)

    def test_commented_meta_does_not_override(self):
        problems, author = self.check(
            '<meta name="author" content="Jeff Posluns">\n'
            '<!-- <meta name="author" content="Mallory"> -->', "Jeff Posluns")
        self.assertEqual(author, "Jeff Posluns")
        self.assertEqual(problems, [])


class ImageReferenceTest(_PatchedGateTest):
    def _check(self, image_url: str) -> list[str]:
        page = gate.SITE_ROOT / "index.html"
        block = article('{"@type": "Person", "name": "Jeff Posluns"}')
        extra = ('<meta name="author" content="Jeff Posluns">\n'
                 f'<meta property="og:image" content="{image_url}">')
        page.write_text(GATE_PAGE.format(extra_meta=extra, json_ld=block),
                        encoding="utf-8")
        return gate.check_page(page, TODAY)[0]

    def test_out_of_tree_traversal_is_reported_not_passed(self):
        (gate.REPO_ROOT / "secret.txt").write_text("x", encoding="utf-8")
        problems = self._check("https://cleanlanguage.ai/../secret.txt")
        self.assertTrue(any("outside the site directory" in p for p in problems))

    def test_traversal_to_missing_target_is_reported_outside(self):
        # A traversal to a missing out-of-tree target must be reported as a
        # containment violation, not as a plain "does not exist": the test needs
        # exactly 1 problem, whose text holds "outside the site directory", and
        # fails a gate that reports this missing target only as "does not exist".
        problems = self._check("https://cleanlanguage.ai/../no-such-file.png")
        self.assertEqual(len(problems), 1)
        self.assertIn("outside the site directory", problems[0])

    def test_in_tree_image_passes(self):
        (gate.SITE_ROOT / "card.png").write_bytes(b"x")
        self.assertEqual(self._check("https://cleanlanguage.ai/card.png"), [])

    def test_missing_in_tree_image_is_reported(self):
        problems = self._check("https://cleanlanguage.ai/missing.png")
        self.assertTrue(any("does not exist" in p for p in problems))


def _img_meta(url):
    return f'<meta property="og:image" content="{url}">'


class OriginMatchTest(_PatchedGateTest):
    def _problems(self, extra, files=()):
        for rel in files:
            (gate.SITE_ROOT / rel).write_bytes(b"x")
        page = gate.SITE_ROOT / "index.html"
        block = article('{"@type": "Person", "name": "Jeff Posluns"}')
        extra = '<meta name="author" content="Jeff Posluns">\n' + extra
        page.write_text(GATE_PAGE.format(extra_meta=extra, json_ld=block), encoding="utf-8")
        return gate.check_page(page, TODAY)[0]

    def test_uppercase_origin_missing_is_reported(self):
        problems = self._problems(_img_meta("HTTPS://CLEANLANGUAGE.AI/missing.png"))
        self.assertTrue(any("does not exist" in p for p in problems))

    def test_explicit_default_port_maps_to_the_file(self):
        # :443 is the default https port, so this is on-origin and maps to
        # card.png. A gate that looked up site/:443/card.png would fail the page.
        problems = self._problems(_img_meta("https://cleanlanguage.ai:443/card.png"),
                                  files=["card.png"])
        self.assertEqual(problems, [])
        # The same port on a missing file must be reported as missing, so a gate
        # that reads :443 as off-origin and skips the URL fails this test.
        problems = self._problems(_img_meta("https://cleanlanguage.ai:443/missing.png"))
        self.assertTrue(any("does not exist" in p for p in problems))

    def test_subdomain_lookalike_is_ignored(self):
        problems = self._problems(_img_meta("https://cleanlanguage.ai.evil/card.png"))
        self.assertEqual(problems, [])

    def test_query_and_fragment_are_stripped(self):
        problems = self._problems(_img_meta("https://cleanlanguage.ai/card.png?v=1#top"),
                                  files=["card.png"])
        self.assertEqual(problems, [])

    def test_backslash_url_missing_is_reported(self):
        # A browser normalizes the backslash to a slash, so this is on-origin and
        # points at a missing file. A parser that kept the backslash in the host
        # would treat the URL as off-origin and silently pass it.
        problems = self._problems(_img_meta("https://cleanlanguage.ai\\missing.png"))
        self.assertTrue(any("does not exist" in p for p in problems))


class MultiImageTest(_PatchedGateTest):
    def _problems(self, extra, files=()):
        for rel in files:
            (gate.SITE_ROOT / rel).write_bytes(b"x")
        page = gate.SITE_ROOT / "index.html"
        block = article('{"@type": "Person", "name": "Jeff Posluns"}')
        extra = '<meta name="author" content="Jeff Posluns">\n' + extra
        page.write_text(GATE_PAGE.format(extra_meta=extra, json_ld=block), encoding="utf-8")
        return gate.check_page(page, TODAY)[0]

    def test_first_of_two_og_images_is_checked(self):
        extra = (_img_meta("https://cleanlanguage.ai/missing.png") + "\n"
                 + _img_meta("https://cleanlanguage.ai/card.png"))
        problems = self._problems(extra, files=["card.png"])
        self.assertTrue(any("missing.png" in p and "does not exist" in p for p in problems))

    def test_name_form_not_hidden_by_property_form(self):
        extra = (_img_meta("https://cleanlanguage.ai/card.png") + "\n"
                 + '<meta name="og:image" content="https://cleanlanguage.ai/missing.png">')
        problems = self._problems(extra, files=["card.png"])
        self.assertTrue(any("missing.png" in p for p in problems))

    def test_twitter_image_reference_is_checked(self):
        # og:image names an existing file and twitter:image a missing one, so a
        # gate that checks only the first image reference fails this test.
        extra = (_img_meta("https://cleanlanguage.ai/card.png") + "\n"
                 + '<meta name="twitter:image" content="https://cleanlanguage.ai/missing.png">')
        problems = self._problems(extra, files=["card.png"])
        self.assertTrue(any("twitter:image" in p for p in problems))


class MetaContextTest(_PatchedGateTest):
    def _check(self, extra_meta):
        page = gate.SITE_ROOT / "index.html"
        block = article('{"@type": "Person", "name": "Jeff Posluns"}')
        page.write_text(GATE_PAGE.format(extra_meta=extra_meta, json_ld=block), encoding="utf-8")
        return gate.check_page(page, TODAY)

    def test_author_only_in_template_is_missing(self):
        problems, author = self._check(
            '<template><meta name="author" content="Jeff Posluns"></template>')
        self.assertIsNone(author)
        self.assertIn('missing <meta name="author">', problems)

    def test_author_only_in_noscript_is_missing(self):
        problems, author = self._check(
            '<noscript><meta name="author" content="Jeff Posluns"></noscript>')
        self.assertIsNone(author)
        self.assertIn('missing <meta name="author">', problems)

    def test_broken_image_in_template_is_ignored(self):
        problems, _ = self._check(
            '<meta name="author" content="Jeff Posluns">\n'
            '<template>' + _img_meta("https://cleanlanguage.ai/missing.png") + '</template>')
        self.assertEqual(problems, [])

    def test_meta_after_closed_template_still_counts(self):
        # The author after a closed template is active and satisfies the
        # requirement: a gate that ignores meta past </template> fails this test.
        problems, author = self._check(
            '<template><meta name="robots" content="noindex"></template>\n'
            '<meta name="author" content="Jeff Posluns">')
        self.assertEqual(author, "Jeff Posluns")
        self.assertEqual(problems, [])


class MalformedImageUrlTest(_PatchedGateTest):
    def _problems(self, url):
        page = gate.SITE_ROOT / "index.html"
        block = article('{"@type": "Person", "name": "Jeff Posluns"}')
        extra = '<meta name="author" content="Jeff Posluns">\n' + _img_meta(url)
        page.write_text(GATE_PAGE.format(extra_meta=extra, json_ld=block), encoding="utf-8")
        return gate.check_page(page, TODAY)[0]

    def test_literal_nul_is_a_content_problem(self):
        problems = self._problems("https://cleanlanguage.ai/\x00.png")
        self.assertTrue(any("not a valid image URL" in p for p in problems))

    def test_encoded_nul_is_a_content_problem(self):
        problems = self._problems("https://cleanlanguage.ai/%00.png")
        self.assertTrue(any("not a valid image URL" in p for p in problems))

    def test_url_through_a_file_is_a_content_problem_not_exit_3(self):
        # og:image traverses through an existing file. The test needs a problem
        # holding "does not exist" and errors if check_page() raises instead.
        (gate.SITE_ROOT / "card.png").write_bytes(b"x")
        problems = self._problems("https://cleanlanguage.ai/card.png/child.png")
        self.assertTrue(any("does not exist" in p for p in problems))

    def test_value_error_in_check_page_exits_3(self):
        page = gate.SITE_ROOT / "index.html"
        page.write_text("<html></html>", encoding="utf-8")
        saved = (gate.require_full_history, gate.content_pages, gate.check_page)
        gate.require_full_history = lambda: None
        gate.content_pages = lambda: [page]

        def boom(*args, **kwargs):
            raise ValueError("synthetic")

        gate.check_page = boom
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    gate.main()
        finally:
            (gate.require_full_history, gate.content_pages, gate.check_page) = saved
        self.assertEqual(caught.exception.code, 3)


class CaseSpellingTest(_PatchedGateTest):
    def test_wrong_case_image_reports_spelling(self):
        (gate.SITE_ROOT / "card.png").write_bytes(b"x")
        page = gate.SITE_ROOT / "index.html"
        block = article('{"@type": "Person", "name": "Jeff Posluns"}')
        extra = ('<meta name="author" content="Jeff Posluns">\n'
                 + _img_meta("https://cleanlanguage.ai/CARD.PNG"))
        page.write_text(GATE_PAGE.format(extra_meta=extra, json_ld=block), encoding="utf-8")
        problems = gate.check_page(page, TODAY)[0]
        self.assertTrue(any("spelled" in p and "404" in p for p in problems))


def load_faults(defined: str, renamed: str, attribute: str) -> list[tuple[str, object, str]]:
    """7 of the ways a sibling tool can fail to load, each a fault on 1 file
    with the words of the refusal it gives: the file missing, its mode 000, its
    mode 000 beside a valid cached file, a syntax error, the definition of
    attribute renamed, a syntax error beside a cached file of the unbroken
    source that the normal loader runs without comparing it with the source (an
    unchecked hash-based file), and the file a symbolic link to the unbroken
    source. The tool must always read the source, so that no cached file stands
    in for it. Root reads a file whatever its mode, so under root the 2
    mode-000 faults skip their case instead."""
    def missing(path: Path) -> None:
        path.unlink()

    def linked(path: Path) -> None:
        target = path.with_name(path.name + ".target")
        path.rename(target)
        path.symlink_to(target.name)

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def locked(path: Path) -> None:
        os.chmod(path, 0)

    def cache(path: Path, mode: py_compile.PycInvalidationMode) -> None:
        py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)),
                           doraise=True, invalidation_mode=mode)

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def cached_locked(path: Path) -> None:
        cache(path, py_compile.PycInvalidationMode.TIMESTAMP)
        os.chmod(path, 0)

    def broken(path: Path) -> None:
        path.write_bytes(path.read_bytes() + b"\ndef (\n")

    def rename(path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        if defined not in text:
            raise AssertionError(f"{defined!r} is not in {path.name}")
        path.write_text(text.replace(defined, renamed, 1), encoding="utf-8")

    def stale(path: Path) -> None:
        cache(path, py_compile.PycInvalidationMode.UNCHECKED_HASH)
        broken(path)

    return [("missing", missing, "could not be read"),
            ("with mode 000", locked, "could not be read"),
            ("with mode 000 beside a valid cached file", cached_locked, "could not be read"),
            ("with a syntax error", broken, "could not be loaded"),
            (f"with {attribute} renamed", rename, f"defines no {attribute}"),
            ("with a syntax error beside a stale cached file", stale, "could not be loaded"),
            ("as a symbolic link", linked, "is not a regular file")]


class SiblingLoadTest(unittest.TestCase):
    """tools/check-page-metadata.py, run with tools/sitemap_engine.py failing to
    load in each way load_faults() gives, exits 3 with its own refusal naming
    that file, and never runs a cached file in its place."""

    def test_each_load_failure_is_refused(self):
        faults = load_faults("def enumerate_pages(", "def enumerate_pages_unused(", "enumerate_pages")
        for name, fault, words in faults:
            with self.subTest(name), tempfile.TemporaryDirectory() as scratch:
                tools = Path(scratch) / "tools"
                tools.mkdir()
                for file in ("check-page-metadata.py", "web_metadata.py", "sitemap_engine.py"):
                    shutil.copyfile(Path(__file__).resolve().parent / file, tools / file)
                fault(tools / "sitemap_engine.py")
                gate = str(tools / "check-page-metadata.py")
                result = subprocess.run([sys.executable, "-I", gate], capture_output=True, text=True)
                self.assertEqual(result.returncode, 3, result.stderr[-300:])
                refusal = f"check-page-metadata: tools/sitemap_engine.py {words}"
                self.assertIn(refusal, result.stderr)


def history_page(modified: str, body: str = "First body.", published: str = "2026-01-01") -> str:
    """An author-compliant page whose only varying inputs are its stamps and
    body, so each problem that the gate can find on it concerns its dates or
    its history, such as the modified-stamp one or the published-date one."""
    json_ld = (
        '<script type="application/ld+json">'
        '{"@context": "https://schema.org", "@type": "Article",'
        f' "datePublished": "{published}", "dateModified": "{modified}",'
        ' "author": {"@type": "Person", "name": "Jeff Posluns"}}'
        "</script>"
    )
    return (
        "<!doctype html>\n<html><head>\n"
        '<meta name="author" content="Jeff Posluns">\n'
        f'<meta property="article:published_time" content="{published}">\n'
        f'<meta property="article:modified_time" content="{modified}">\n'
        '<meta property="article:author" content="https://posluns.ca">\n'
        + json_ld
        + f"\n</head><body><p>{body}</p></body></html>\n"
    )


def gate_git_text(*args: str) -> str:
    """The gate's git() output for args, decoded as strict UTF-8."""
    return gate.git(*args).decode("utf-8")


# A git for PATH that runs the real git with its arguments and keeps its
# stderr and exit code, and prints the given output in place of its stdout
# when the arguments after -C and the folder start with the given prefix.
FAKE_GIT = """\
import os
import subprocess
import sys

args = sys.argv[1:]
result = subprocess.run([os.environ["PAGE_METADATA_REAL_GIT"], *args], capture_output=True)
prefix = os.environ["PAGE_METADATA_FAKE_ARGS"].split("\\n")
sys.stderr.buffer.write(result.stderr)
if args[2:2 + len(prefix)] == prefix:
    sys.stdout.buffer.write(bytes.fromhex(os.environ["PAGE_METADATA_FAKE_OUTPUT"]))
else:
    sys.stdout.buffer.write(result.stdout)
sys.exit(result.returncode)
"""


class ProtectedLineHistoryTest(unittest.TestCase):
    """last_change_date() dates a page at the merge base of HEAD and
    refs/remotes/origin/main only when that base is the only one, the page's
    mode and blob at HEAD equal its mode and blob there, and git hash-object of
    the working-tree page gives its blob at HEAD; otherwise it reads at HEAD,
    and a failed git call exits 3. Each test runs in a temporary repository
    made by start_repository() with git init --template=, each commit is made
    through the class's git() with a fixture identity and a fixed date, and
    each call of check_page() passes the fixed TODAY, since run_main() makes it
    the date that main() reads. isolate_git() keeps the suite's and the gate's
    git calls from reading the system and global configuration, configuration
    from GIT_ variables, the user's attributes and ignore files, and the
    system's attributes file. Cases plant configuration through
    GIT_CONFIG_COUNT before isolate_git() runs, a ~/.gitconfig in a HOME set
    before it runs, a GIT_CONFIG_SYSTEM file after it runs, and a user
    attributes file and a user ignore file at both default paths, and
    test_repository_has_no_template_files checks for template files.
    GIT_CONFIG_GLOBAL and HOME are overlapping layers: git reads ~/.gitconfig
    only when both are dropped, so no case checks dropping either alone, and
    test_global_configuration_in_home_is_not_read fails when both are. No case
    plants a system attributes file, since git has no variable that moves it,
    and test_isolated_git_names_no_system_attributes_file fails when
    GIT_ATTR_NOSYSTEM is not set. The class still takes inputs from the
    machine, such as the git binary found on PATH, with its version and
    built-in defaults, the locale, and the folder that tempfile picks."""

    TODAY = "2026-03-01"
    MAIN_DATE = "2026-01-01"

    def setUp(self):
        environ = mock.patch.dict(os.environ)
        environ.start()
        self.addCleanup(environ.stop)
        # Each folder that the test makes, such as its repositories, its HOME
        # and its planted files, sits in this 1 folder, which is removed when
        # the test ends.
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        self.isolate_git()
        saved = (gate.REPO_ROOT, gate.SITE_ROOT)
        self.addCleanup(self._restore_roots, saved)
        self.start_repository()

    def isolate_git(self) -> None:
        # Remove every GIT_ variable, so no configuration comes from the
        # environment, such as GIT_CONFIG_COUNT; read /dev/null as the global
        # configuration and no system configuration or system attributes file;
        # and point HOME and XDG_CONFIG_HOME at a fresh empty folder, so git
        # finds no user attributes or ignore file at their default paths. The
        # loop, GIT_CONFIG_NOSYSTEM and XDG_CONFIG_HOME each have a case that
        # plants their input and fails without them. GIT_CONFIG_GLOBAL and HOME
        # overlap: git reads ~/.gitconfig only when both are dropped, so no
        # case checks dropping either alone, and
        # test_global_configuration_in_home_is_not_read, which plants a
        # ~/.gitconfig, fails when both are. No case plants a system attributes
        # file, since git has no variable that moves it, and
        # test_isolated_git_names_no_system_attributes_file fails without
        # GIT_ATTR_NOSYSTEM. os.environ is restored when the test ends.
        for key in [key for key in os.environ if key.startswith("GIT_")]:
            del os.environ[key]
        os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        os.environ["GIT_ATTR_NOSYSTEM"] = "1"
        home = tempfile.mkdtemp(dir=self.scratch)
        os.environ["HOME"] = home
        os.environ["XDG_CONFIG_HOME"] = home

    def start_repository(self, *options: str) -> None:
        root = Path(tempfile.mkdtemp(dir=self.scratch)).resolve()
        gate.REPO_ROOT = root
        gate.SITE_ROOT = root / "site"
        gate.SITE_ROOT.mkdir()
        self.page = gate.SITE_ROOT / "index.html"
        self.git("init", "-q", "--template=", "-b", "main", *options)

    @staticmethod
    def _restore_roots(saved):
        gate.REPO_ROOT, gate.SITE_ROOT = saved

    def git(self, *args: str, date: str = MAIN_DATE) -> str:
        stamp = f"{date} 12:00:00 +0000"
        env = dict(os.environ,
                   GIT_AUTHOR_NAME="Fixture Author", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                   GIT_COMMITTER_NAME="Fixture Author", GIT_COMMITTER_EMAIL="fixture@example.invalid",
                   GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        result = subprocess.run(["git", "-C", str(gate.REPO_ROOT), *args],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def commit_page(self, date: str, modified: str, body: str = "First body.",
                    published: str = MAIN_DATE) -> None:
        self.page.write_text(history_page(modified, body, published), encoding="utf-8")
        self.git("add", "site/index.html")
        self.git("commit", "-q", "-m", f"Page on {date}", date=date)

    def commit_other_file(self, date: str) -> None:
        (gate.REPO_ROOT / "README").write_text("fixture\n", encoding="utf-8")
        self.git("add", "README")
        self.git("commit", "-q", "-m", f"Other file on {date}", date=date)

    def protect_main(self) -> None:
        self.git("update-ref", "refs/remotes/origin/main", "main")

    def change_and_restore_on_branch(self, protect: bool = True) -> None:
        # main dates the page 2026-01-01 with a matching stamp; the branch
        # changes its body on 2026-02-01 and restores it exactly on 2026-02-02.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        if protect:
            self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        self.commit_page("2026-02-01", self.MAIN_DATE, body="Changed body.")
        self.commit_page("2026-02-02", self.MAIN_DATE)

    def problems(self) -> list[str]:
        problems, _author = gate.check_page(self.page, self.TODAY)
        return problems

    def assert_stamp_problem(self, problems: list[str], changed: str) -> None:
        self.assertTrue(
            any(f"the file last changed {changed}" in p and "tolerance" in p for p in problems),
            problems)

    def record_gate_git(self) -> list[tuple[str, ...]]:
        # Each git call the gate makes from here to the end of the test is
        # recorded as its argument tuple.
        calls: list[tuple[str, ...]] = []
        real_git = gate.git

        def recording_git(*args: str) -> str:
            calls.append(args)
            return real_git(*args)

        patcher = mock.patch.object(gate, "git", recording_git)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def run_main(self, stdout) -> int:
        # main() runs on self.page alone with stdout as given, and reads the
        # class's TODAY as today's date through a date class whose today()
        # gives it. The case fails when main() raises.
        today = dt.date.fromisoformat(self.TODAY)

        class FixedDate(dt.date):
            @classmethod
            def today(cls):
                return cls(today.year, today.month, today.day)

        stderr = io.StringIO()
        with mock.patch.object(gate, "content_pages", lambda: [self.page]), \
                mock.patch.object(gate.dt, "date", FixedDate), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                return gate.main()
            except (Exception, SystemExit) as error:
                self.fail(f"main() raised {error!r}: {stderr.getvalue()}")

    def make_folder(self, folder: Path) -> None:
        # A folder that cannot be made fails the case rather than skipping it.
        try:
            folder.mkdir()
        except OSError as error:
            self.fail(f"the folder {ascii(folder.name)} could not be made: {error!r}")

    def commit_page_at(self, page: Path, date: str, modified: str, published: str = MAIN_DATE,
                       body: str = "First body.") -> None:
        # The page at the path given is written and committed with every
        # other change in the working tree.
        page.write_text(history_page(modified, body, published), encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"Page on {date}", date=date)

    def test_user_attributes_and_ignore_files_are_not_read(self):
        # A user attributes file that re-encodes HTML and a user ignore file
        # that lists README and the site folder are planted at both default
        # paths. Through the suite's git and the gate's git(), the page has
        # no working-tree-encoding attribute, no file is ignored, and git
        # add of the page and README succeeds, so the case fails when git
        # reads either planted file.
        hostile = self.scratch / "hostile"
        for config in (hostile / ".config" / "git", hostile / "xdg" / "git"):
            config.mkdir(parents=True)
            (config / "attributes").write_text("*.html working-tree-encoding=UTF-16\n", encoding="utf-8")
            (config / "ignore").write_text("README\nsite/\n", encoding="utf-8")
        os.environ["HOME"] = str(hostile)
        os.environ["XDG_CONFIG_HOME"] = str(hostile / "xdg")
        self.isolate_git()
        self.page.write_text(history_page(self.MAIN_DATE), encoding="utf-8")
        (gate.REPO_ROOT / "README").write_text("fixture\n", encoding="utf-8")
        gits = (("suite", self.git), ("gate", gate_git_text))
        for label, git in gits:
            with self.subTest(git=label):
                self.assertEqual(git("check-attr", "working-tree-encoding", "--", "site/index.html"),
                                 "site/index.html: working-tree-encoding: unspecified\n")
                self.assertEqual(git("ls-files", "--others", "--ignored", "--exclude-standard"), "")
        for label, git in gits:
            with self.subTest(git=label):
                git("add", "--", "site/index.html", "README")
                git("rm", "-q", "--cached", "--", "site/index.html", "README")

    def assert_no_signing_configuration(self) -> None:
        for label, git in (("suite", self.git), ("gate", gate_git_text)):
            with self.subTest(git=label):
                keys = {line.partition("=")[0] for line in git("config", "--list").splitlines()}
                self.assertFalse(keys & {"commit.gpgsign", "gpg.program"}, keys)

    def test_configuration_from_git_variables_is_not_read(self):
        # Configuration through GIT_CONFIG_COUNT, set before isolate_git()
        # runs, signs each commit with a program that fails, so git commit
        # fails when git reads it.
        os.environ.update(GIT_CONFIG_COUNT="2",
                          GIT_CONFIG_KEY_0="commit.gpgsign", GIT_CONFIG_VALUE_0="true",
                          GIT_CONFIG_KEY_1="gpg.program", GIT_CONFIG_VALUE_1="false")
        self.isolate_git()
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.assert_no_signing_configuration()

    def test_global_configuration_in_home_is_not_read(self):
        # A ~/.gitconfig in a HOME set before isolate_git() runs signs each
        # commit with a program that fails, so git commit fails when git
        # reads it, which git does only when isolate_git() replaces neither
        # GIT_CONFIG_GLOBAL nor HOME.
        hostile = self.scratch / "hostile"
        hostile.mkdir()
        (hostile / ".gitconfig").write_text(
            "[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n", encoding="utf-8")
        os.environ["HOME"] = str(hostile)
        self.isolate_git()
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.assert_no_signing_configuration()

    def test_isolated_git_names_no_system_attributes_file(self):
        # git var GIT_ATTR_SYSTEM names the system attributes file that git
        # reads, and fails when git reads none, so the case fails when
        # isolate_git() does not set GIT_ATTR_NOSYSTEM.
        result = subprocess.run(["git", "-C", str(gate.REPO_ROOT), "var", "GIT_ATTR_SYSTEM"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")

    def test_git_that_cannot_be_run_exits_3(self):
        # PATH names only an empty folder, so the gate's git() cannot run
        # git, which must stop the check rather than read as a problem.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        empty = self.scratch / "empty"
        empty.mkdir()
        os.environ["PATH"] = str(empty)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.require_full_history()
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("git could not be run", stderr.getvalue())

    def test_system_configuration_is_not_read(self):
        # A system configuration file, named by GIT_CONFIG_SYSTEM after
        # isolate_git() runs, signs each commit with a program that fails,
        # so git commit fails when git reads it.
        system = self.scratch / "gitconfig"
        system.write_text("[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = false\n", encoding="utf-8")
        os.environ["GIT_CONFIG_SYSTEM"] = str(system)
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.assert_no_signing_configuration()

    def test_repository_has_no_template_files(self):
        # git init --template= copies nothing from git's template directory,
        # such as its sample hooks and its info/exclude file.
        git_dir = gate.REPO_ROOT / ".git"
        self.assertFalse((git_dir / "hooks").exists())
        self.assertFalse((git_dir / "info").exists())

    def test_restored_page_with_main_stamp_passes(self):
        self.change_and_restore_on_branch()
        self.assertEqual(self.problems(), [])

    def test_content_change_without_restamp_fails(self):
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        self.commit_page("2026-02-01", self.MAIN_DATE, body="Changed body.")
        self.assert_stamp_problem(self.problems(), "2026-02-01")

    def test_date_only_restamp_to_branch_date_passes(self):
        self.change_and_restore_on_branch()
        self.commit_page("2026-02-03", "2026-02-03")
        self.assertEqual(self.problems(), [])

    def test_date_only_stale_restamp_fails(self):
        # The stamp alone moves to 2026-01-12, 21 days before the branch's last
        # commit, so the page differs from main and is read at HEAD.
        self.change_and_restore_on_branch()
        self.commit_page("2026-02-02", "2026-01-12")
        self.assert_stamp_problem(self.problems(), "2026-02-02")

    def test_missing_protected_ref_reads_at_head(self):
        # A local main exists, but only refs/remotes/origin/main is read.
        self.change_and_restore_on_branch(protect=False)
        self.assert_stamp_problem(self.problems(), "2026-02-02")

    def test_protected_ref_without_shared_history_exits_3(self):
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.git("switch", "-q", "--orphan", "unrelated")
        self.commit_other_file(self.MAIN_DATE)
        self.git("update-ref", "refs/remotes/origin/main", "unrelated")
        self.git("switch", "-q", "main")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.check_page(self.page, self.TODAY)
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("merge-base", stderr.getvalue())

    def test_working_tree_hash_failure_exits_3(self):
        # A required clean filter that fails makes git hash-object fail for the
        # page, which must stop the check rather than read as a mismatch.
        self.change_and_restore_on_branch()
        self.git("config", "filter.broken.clean", "false")
        self.git("config", "filter.broken.required", "true")
        info = gate.REPO_ROOT / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_text("site/index.html filter=broken\n", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.check_page(self.page, self.TODAY)
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("hash-object", stderr.getvalue())

    def test_page_added_on_branch_is_dated_at_head(self):
        self.commit_other_file(self.MAIN_DATE)
        self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        self.commit_page("2026-02-01", "2026-02-01", published="2026-02-01")
        self.assertEqual(self.problems(), [])

    def test_push_to_main_without_restamp_fails(self):
        # The page changes on main 40 days after its stamp, and the protected
        # ref is HEAD itself, so the newest commit of the page is read there.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.commit_page("2026-02-10", self.MAIN_DATE, body="Changed body.")
        self.protect_main()
        self.assert_stamp_problem(self.problems(), "2026-02-10")

    def test_main_merged_into_restoring_branch_passes(self):
        # The branch takes main's newer commit by a merge whose first parent is
        # the branch, as updating a pull request branch from main does. git log
        # at HEAD follows the first parent that has the page as the merge has
        # it, which is the branch's restore of 2026-02-02, so the page passes
        # only when it is dated at the merge base, main's tip.
        self.change_and_restore_on_branch()
        self.git("switch", "-q", "main")
        self.commit_other_file("2026-02-03")
        self.protect_main()
        self.git("switch", "-q", "topic")
        self.git("merge", "-q", "--no-ff", "-m", "Merge main", "main", date="2026-02-04")
        self.assertEqual(self.problems(), [])

    def test_restoring_branch_merged_into_main_passes(self):
        # main merges the restoring branch with no fast-forward, so main's
        # tip is the first parent and the branch head the second, as a pull
        # request's merge checkout has it, and the page passes there. With
        # the protected ref at main's tip before the merge, the page is read
        # at that merge base; without the ref, it is read at HEAD, where git
        # log follows the first parent whose page matches the merge's, which
        # is main.
        for protect in (True, False):
            with self.subTest(protect=protect):
                self.start_repository()
                self.change_and_restore_on_branch(protect=False)
                self.git("switch", "-q", "main")
                self.commit_other_file("2026-02-03")
                if protect:
                    self.protect_main()
                self.git("merge", "-q", "--no-ff", "-m", "Merge topic", "topic", date="2026-02-04")
                self.assertEqual(self.problems(), [])

    def test_branch_restamp_merged_into_main_is_dated_at_branch_commit(self):
        # main merges, with no fast-forward, a branch that changed the page
        # and restamped it to 2026-02-01. git log at the merge follows the
        # parent whose page matches the merge's, which is the branch, so the
        # page is dated 2026-02-01, not 2026-02-20, the date of the merge.
        # With no ref, and with the ref at main's tip before the merge, the
        # page is read at HEAD, the latter once the blob comparison fails;
        # with the ref at the tip after the merge, the merge base is the
        # merge itself and the page is read there.
        for protect in ("none", "before merge", "after merge"):
            with self.subTest(protect=protect):
                self.start_repository()
                self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
                self.git("switch", "-q", "-c", "topic")
                self.commit_page("2026-02-01", "2026-02-01", body="Changed body.")
                self.git("switch", "-q", "main")
                self.commit_other_file("2026-02-10")
                if protect == "before merge":
                    self.protect_main()
                self.git("merge", "-q", "--no-ff", "-m", "Merge topic", "topic", date="2026-02-20")
                if protect == "after merge":
                    self.protect_main()
                self.assertEqual(gate.last_change_date("site/index.html"), "2026-02-01")
                self.assertEqual(self.problems(), [])

    def test_page_added_on_branch_merged_into_main_keeps_its_added_date(self):
        # main merges, with no fast-forward, a branch that added the page on
        # 2026-02-01, so the merge's diff against main's tip adds the page
        # too. git log at HEAD finds the branch's commit as the one that
        # added it, so the published stamp of 2026-02-01 matches. The case
        # asserts only on the added date and the published stamp, so the
        # last-change reading does not decide it.
        self.commit_other_file(self.MAIN_DATE)
        self.git("switch", "-q", "-c", "topic")
        self.commit_page("2026-02-01", "2026-02-01", published="2026-02-01")
        self.git("switch", "-q", "main")
        self.git("merge", "-q", "--no-ff", "-m", "Merge topic", "topic", date="2026-02-20")
        self.assertEqual(gate.added_date("site/index.html"), "2026-02-01")
        self.assertFalse([p for p in self.problems() if "article:published_time" in p])

    def test_page_added_on_both_sides_of_a_merge_keeps_first_parent_added_date(self):
        # Branch y adds the page on 2026-02-01 and main adds the identical page
        # on 2026-02-05, and then main merges y with no fast-forward. git log
        # at HEAD follows main, the first parent whose page matches the
        # merge's, so the page was added 2026-02-05; with --full-history it
        # also lists y's commit, and the oldest date, 2026-02-01, is read. The
        # stamp of 2026-02-05 is within 7 days of each commit that has the
        # page, so the last-change reading does not decide the case.
        self.commit_other_file(self.MAIN_DATE)
        self.git("switch", "-q", "-c", "y")
        self.commit_page("2026-02-01", "2026-02-05", published="2026-02-05")
        self.git("switch", "-q", "main")
        # git switch removes the site folder, which main does not track yet.
        gate.SITE_ROOT.mkdir()
        self.commit_page("2026-02-05", "2026-02-05", published="2026-02-05")
        self.git("merge", "-q", "--no-ff", "-m", "Merge y", "y", date="2026-02-06")
        self.assertEqual(gate.added_date("site/index.html"), "2026-02-05")
        problems = self.problems()
        self.assertFalse([p for p in problems if "article:published_time" in p])
        self.assertEqual(problems, [])

    def test_criss_cross_reads_at_head_whichever_base_git_picks(self):
        # Branch a changes another file and branch b changes the page body.
        # main merges a and then b, and topic merges b and then a and restores
        # the page with main's first stamp, so HEAD and the protected ref have
        # 2 merge bases, a and b, and the page at HEAD differs from main's tip.
        # The 2 builds swap the commit dates of a and b so that git picks each
        # base once, and the page is read at HEAD in both.
        for picked, a_date, b_date in (("a", "2026-02-03", "2026-02-02"),
                                        ("b", "2026-02-02", "2026-02-03")):
            with self.subTest(picked=picked):
                self.start_repository()
                self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
                root = self.git("rev-parse", "HEAD").strip()
                self.git("switch", "-q", "-c", "a")
                self.commit_other_file(a_date)
                self.git("switch", "-q", "-c", "b", root)
                self.commit_page(b_date, self.MAIN_DATE, body="Changed body.")
                self.git("switch", "-q", "main")
                self.git("merge", "-q", "--no-ff", "-m", "Merge a", "a", date="2026-02-05")
                self.git("merge", "-q", "--no-ff", "-m", "Merge b", "b", date="2026-02-06")
                self.protect_main()
                self.git("switch", "-q", "-c", "topic", root)
                self.git("merge", "-q", "--no-ff", "-m", "Merge b", "b", date="2026-02-07")
                self.git("merge", "-q", "--no-ff", "-m", "Merge a", "a", date="2026-02-08")
                self.commit_page("2026-02-12", self.MAIN_DATE)
                names = {self.git("rev-parse", name).strip(): name for name in ("a", "b")}
                bases = self.git("merge-base", "--all", "HEAD", "refs/remotes/origin/main").split()
                self.assertEqual(sorted(names.get(base) for base in bases), ["a", "b"])
                pick = self.git("merge-base", "HEAD", "refs/remotes/origin/main").strip()
                self.assertEqual(names.get(pick), picked)
                self.assert_stamp_problem(self.problems(), "2026-02-12")

    def test_ref_below_protected_refname_reads_at_head(self):
        # git for-each-ref lists refs/remotes/origin/main/x for the protected
        # refname, but only a ref of exactly that name is read.
        self.change_and_restore_on_branch(protect=False)
        self.git("update-ref", "refs/remotes/origin/main/x", "main")
        listed = self.git("for-each-ref", "--format=%(refname)", "refs/remotes/origin/main")
        self.assertEqual(listed.split(), ["refs/remotes/origin/main/x"])
        self.assert_stamp_problem(self.problems(), "2026-02-02")

    def test_ref_named_across_a_unicode_line_separator_reads_at_head(self):
        # With no protected ref, a ref at main is named
        # refs/remotes/origin/main/x, then U+0085, U+2028 or U+2029, then the
        # protected refname, which git for-each-ref lists on 1 line. The gate
        # splits its listing only at a line feed, so it finds no ref of
        # exactly the protected refname and dates the page at HEAD. The case
        # reads no ref listing through the suite's git(), which reads it
        # without error, since a caller's str.split() splits such a name in 2.
        for separator in ("\u0085", "\u2028", "\u2029"):
            with self.subTest(separator=ascii(separator)):
                self.start_repository()
                self.change_and_restore_on_branch(protect=False)
                self.git("update-ref", f"refs/remotes/origin/main/x{separator}refs/remotes/origin/main",
                         "main")
                self.assert_stamp_problem(self.problems(), "2026-02-02")

    def test_ref_named_across_a_line_separator_at_unrelated_commit_reads_at_head(self):
        # With no protected ref, the ref named across U+2028 points at a
        # commit that shares no history with HEAD. The gate reads no merge
        # base for it, so it dates the page at HEAD and does not stop.
        self.change_and_restore_on_branch(protect=False)
        self.git("switch", "-q", "--orphan", "unrelated")
        self.commit_other_file(self.MAIN_DATE)
        self.git("update-ref", "refs/remotes/origin/main/x\u2028refs/remotes/origin/main", "unrelated")
        self.git("switch", "-q", "topic")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            try:
                problems = self.problems()
            except SystemExit as error:
                self.fail(f"exit {error.code}: {stderr.getvalue()}")
        self.assert_stamp_problem(problems, "2026-02-02")

    def test_ref_below_protected_refname_with_non_utf8_name_reads_at_head(self):
        # git for-each-ref lists a ref below the protected refname whose last
        # name byte is 0xff, which is not UTF-8. The gate reads its name and
        # dates the page at HEAD, as with no protected ref. The suite reads no
        # git output that holds that byte, since its git() decodes strictly.
        self.change_and_restore_on_branch(protect=False)
        self.git("update-ref", "refs/remotes/origin/main/" + os.fsdecode(b"\xff"), "main")
        self.assert_stamp_problem(self.problems(), "2026-02-02")

    def test_restored_page_in_non_utf8_folder_passes(self):
        # A page in a folder named by the byte 0xff, which is not UTF-8, by
        # a, CR and b, by a, CR, LF and b, by a, by ab, by a, LF and b, or by
        # a, TAB and b is changed and restored exactly on a branch, with the
        # protected ref at main. The name that git ls-tree prints for each
        # equals the page's path in bytes, so each is dated at the merge base
        # and passes, and none stops the check. The TAB folder fails when
        # blob_at() partitions an entry at its last tab rather than its
        # first. A folder that cannot be made fails the case.
        for folder in (os.fsdecode(b"\xff"), "a\rb", "a\r\nb", "a", "ab", "a\nb", "a\tb"):
            with self.subTest(folder=ascii(folder)):
                self.start_repository()
                self.page = gate.SITE_ROOT / folder / "index.html"
                self.make_folder(self.page.parent)
                for date, body in ((self.MAIN_DATE, "First body."), ("2026-02-01", "Changed body."),
                                   ("2026-02-02", "First body.")):
                    self.commit_page_at(self.page, date, self.MAIN_DATE, body=body)
                    if date == self.MAIN_DATE:
                        self.protect_main()
                        self.git("switch", "-q", "-c", "topic")
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    try:
                        problems = self.problems()
                    except SystemExit as error:
                        self.fail(f"exit {error.code}: {stderr.getvalue()}")
                self.assertEqual(problems, [])

    def test_page_in_glob_named_folder_is_dated_by_its_own_commit(self):
        # site/[ab]/index.html is committed on 2026-01-01 with that stamp,
        # and site/a/index.html, which the glob [ab] matches, on 2026-02-20.
        # The page is dated by its own commit, so it has no problem.
        self.page = gate.SITE_ROOT / "[ab]" / "index.html"
        self.make_folder(self.page.parent)
        self.commit_page_at(self.page, self.MAIN_DATE, self.MAIN_DATE)
        other = gate.SITE_ROOT / "a" / "index.html"
        self.make_folder(other.parent)
        self.commit_page_at(other, "2026-02-20", "2026-02-20", published="2026-02-20")
        self.assertEqual(self.problems(), [])

    def test_page_in_glob_named_folder_keeps_its_own_added_date(self):
        # site/a/index.html is added on 2026-01-01, and site/[ab]/index.html
        # on 2026-02-01 with a published stamp of 2026-01-01. The page's
        # added date is that of its own commit, so the stamp is a problem.
        other = gate.SITE_ROOT / "a" / "index.html"
        self.make_folder(other.parent)
        self.commit_page_at(other, self.MAIN_DATE, self.MAIN_DATE)
        self.page = gate.SITE_ROOT / "[ab]" / "index.html"
        self.make_folder(self.page.parent)
        self.commit_page_at(self.page, "2026-02-01", "2026-02-01")
        self.assertEqual(gate.added_date("site/[ab]/index.html"), "2026-02-01")
        self.assertTrue([p for p in self.problems() if p.startswith("article:published_time is 2026-01-01")])

    def test_pathspec_variables_do_not_change_restored_page_result(self):
        # Each of the 4 variables through which git reads a pathspec as a
        # glob, a literal path or with no regard to case is set to 1, and to
        # bogus, a value that git refuses as not boolean, before the gate
        # runs on a page restored exactly with the protected ref. The page
        # passes and the check does not stop.
        for variable, value in itertools.product(
                ("GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS",
                 "GIT_LITERAL_PATHSPECS"), ("1", "bogus")):
            with self.subTest(variable=variable, value=value):
                self.start_repository()
                self.change_and_restore_on_branch()
                stderr = io.StringIO()
                with mock.patch.dict(os.environ, {variable: value}), contextlib.redirect_stderr(stderr):
                    try:
                        problems = self.problems()
                    except SystemExit as error:
                        self.fail(f"exit {error.code}: {stderr.getvalue()}")
                self.assertEqual(problems, [])

    def test_failed_ls_tree_exits_3(self):
        # The merge base's root tree object is removed, so git ls-tree fails
        # there. The other file makes HEAD's tree differ from it, and the
        # restore is HEAD itself, so git ls-tree and git log at HEAD still
        # succeed. check_page() reads the added date first, which needs the
        # same tree, so the case calls last_change_date() directly.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        self.commit_page("2026-02-01", self.MAIN_DATE, body="Changed body.")
        self.commit_other_file("2026-02-01")
        self.commit_page("2026-02-02", self.MAIN_DATE)
        tree = self.git("rev-parse", "refs/remotes/origin/main^{tree}").strip()
        self.assertNotEqual(self.git("rev-parse", "HEAD^{tree}").strip(), tree)
        (gate.REPO_ROOT / ".git" / "objects" / tree[:2] / tree[2:]).unlink()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.last_change_date("site/index.html")
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("ls-tree", stderr.getvalue())

    def test_mode_only_change_reads_at_head(self):
        # The branch only sets the executable bit on the page, so its blob at
        # HEAD equals main's but its mode does not.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        self.git("update-index", "--chmod=+x", "site/index.html")
        self.git("commit", "-q", "-m", "Mode on 2026-02-01", date="2026-02-01")
        self.assert_stamp_problem(self.problems(), "2026-02-01")

    def test_uncommitted_edit_after_restore_reads_at_head(self):
        self.change_and_restore_on_branch()
        self.page.write_text(history_page(self.MAIN_DATE, body="Uncommitted body."), encoding="utf-8")
        self.assert_stamp_problem(self.problems(), "2026-02-02")

    def test_untracked_page_is_dated_at_head_without_hashing(self):
        # A page with no blob at HEAD is dated at HEAD, where git records no
        # commit for it, and git hash-object never runs for it.
        self.commit_other_file(self.MAIN_DATE)
        self.protect_main()
        self.page.write_text(history_page(self.MAIN_DATE), encoding="utf-8")
        calls = self.record_gate_git()
        problems = self.problems()
        self.assertIn("git records no commit for this file, so its dates cannot be checked", problems)
        self.assertFalse([call for call in calls if call[0] == "hash-object"], calls)

    def test_blob_differing_from_base_reads_at_head_without_hashing(self):
        # The branch changes the page body, so its blob at HEAD differs from
        # the base's, and the page is read at HEAD without git hash-object.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        self.commit_page("2026-02-01", self.MAIN_DATE, body="Changed body.")
        calls = self.record_gate_git()
        self.assertEqual(gate.last_change_date("site/index.html"), "2026-02-01")
        self.assertFalse([call for call in calls if call[0] == "hash-object"], calls)

    def test_mode_differing_from_base_reads_at_head_without_hashing(self):
        # The branch only sets the executable bit on the page, so its blob at
        # HEAD equals the base's but its mode does not, and the page is read at
        # HEAD without git hash-object.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        self.git("update-index", "--chmod=+x", "site/index.html")
        self.git("commit", "-q", "-m", "Mode on 2026-02-01", date="2026-02-01")
        calls = self.record_gate_git()
        self.assertEqual(gate.last_change_date("site/index.html"), "2026-02-01")
        self.assertFalse([call for call in calls if call[0] == "hash-object"], calls)

    def test_gitlink_at_page_path_reads_at_head_without_hashing(self):
        # HEAD and the base have a gitlink, mode 160000, at the page path,
        # and the working tree has a page there. blob_at() reads only a blob
        # entry, so the page has no blob at HEAD, and git hash-object never
        # runs for it.
        self.commit_other_file(self.MAIN_DATE)
        commit = self.git("rev-parse", "HEAD").strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{commit},site/index.html")
        self.git("commit", "-q", "-m", "Gitlink on 2026-01-05", date="2026-01-05")
        self.protect_main()
        self.git("switch", "-q", "-c", "topic")
        (gate.REPO_ROOT / "README").write_text("other\n", encoding="utf-8")
        self.git("add", "README")
        self.git("commit", "-q", "-m", "Other file on 2026-02-01", date="2026-02-01")
        self.page.write_text(history_page("2026-01-05"), encoding="utf-8")
        calls = self.record_gate_git()
        self.assertIsNone(gate.blob_at("HEAD", "site/index.html"))
        self.problems()
        self.assertFalse([call for call in calls if call[0] == "hash-object"], calls)

    def commit_non_utf8_page(self) -> str:
        # A page in a folder named by the byte 0xff, which is not UTF-8, is
        # stamped 40 days before its only commit. The return value is the
        # report line that names it, with the byte shown as decoding it
        # with the file system encoding and a backslash escape shows it.
        self.page = gate.SITE_ROOT / os.fsdecode(b"\xff") / "index.html"
        self.make_folder(self.page.parent)
        self.commit_page_at(self.page, "2026-02-10", self.MAIN_DATE, published="2026-02-10")
        return "  site/" + b"\xff".decode(sys.getfilesystemencoding(), "backslashreplace") + "/index.html"

    def test_report_names_non_utf8_page_on_strict_stdout(self):
        # main() runs on the page of commit_non_utf8_page() with a stdout
        # whose error handler is strict, returns 1 and reports the page,
        # named with the backslash escape, and its stamp problem.
        named = self.commit_non_utf8_page()
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8", errors="strict", newline="\n")
        code = self.run_main(stdout)
        stdout.flush()
        lines = output.getvalue().split(b"\n")
        self.assertEqual(code, 1)
        self.assertIn(named.encode("utf-8"), lines)
        self.assertTrue(any(b"the file last changed 2026-02-10" in line and b"tolerance" in line
                            for line in lines), lines)

    def test_report_to_stdout_without_buffer_names_non_utf8_page(self):
        # main() runs on the page of commit_non_utf8_page() with an
        # io.StringIO as stdout, which has no buffer attribute, returns 1
        # and reports the page, named with the backslash escape, its stamp
        # problem and no lone surrogate.
        named = self.commit_non_utf8_page()
        stdout = io.StringIO()
        code = self.run_main(stdout)
        text = stdout.getvalue()
        lines = text.split("\n")
        self.assertEqual(code, 1)
        self.assertIn(named, lines)
        self.assertTrue(any("the file last changed 2026-02-10" in line and "tolerance" in line
                            for line in lines), lines)
        self.assertFalse([char for char in text if "\udc80" <= char <= "\udcff"], ascii(text))

    def test_report_to_no_stdout_returns_exit_code(self):
        # main() runs on the page of commit_non_utf8_page() with sys.stdout
        # None, the state Python gives when file descriptor 1 is closed,
        # and returns 1 without raising.
        self.commit_non_utf8_page()
        self.assertEqual(self.run_main(None), 1)

    def test_report_under_ascii_file_system_encoding_prints_author(self):
        # sys.getfilesystemencoding() is patched to give ascii, the encoding
        # that Python uses under LC_ALL=C with UTF-8 mode off, since the suite
        # cannot change the file system encoding of its own process. main()
        # runs on a passing page whose author holds U+00E9, with io.StringIO
        # and with a strict UTF-8 stdout, and returns 0 with the author line
        # printed unchanged.
        author = "Jos\u00e9 Posluns"
        self.page.write_text(history_page(self.MAIN_DATE).replace("Jeff Posluns", author),
                             encoding="utf-8")
        self.git("add", "site/index.html")
        self.git("commit", "-q", "-m", "Page on 2026-01-01")
        expected = f"Author: {author}."
        with mock.patch.object(sys, "getfilesystemencoding", lambda: "ascii"):
            text = io.StringIO()
            self.assertEqual(self.run_main(text), 0)
            self.assertIn(expected, text.getvalue())
            output = io.BytesIO()
            stdout = io.TextIOWrapper(output, encoding="utf-8", errors="strict", newline="\n")
            self.assertEqual(self.run_main(stdout), 0)
            stdout.flush()
            self.assertIn(expected.encode("utf-8"), output.getvalue())

    def test_report_under_ascii_file_system_encoding_escapes_utf8_folder(self):
        # With sys.getfilesystemencoding() patched to give ascii, as in the
        # case above, report() prints a line that holds the lone surrogates
        # which os.fsdecode() gives under that encoding for a folder named by
        # the UTF-8 bytes 0xc3 0xa9, and shows them as the escapes \xc3\xa9.
        # The suite's own os.fsdecode() decodes those bytes as UTF-8, so the
        # line is built with the surrogates rather than from a folder.
        line = io.StringIO()
        with mock.patch.object(sys, "getfilesystemencoding", lambda: "ascii"), \
                contextlib.redirect_stdout(line):
            gate.report("  site/\udcc3\udca9/index.html")
        self.assertEqual(line.getvalue(), "  site/\\xc3\\xa9/index.html\n")

    def test_report_escapes_only_surrogates_from_udc80_to_udcff(self):
        # report() shows each lone surrogate from \udc80 to \udcff as the
        # escape of its byte, from \x80 to \xff, and prints \udc7f and
        # \udd00, on each side of that range, unchanged.
        expected = {code: f"\\x{code - 0xdc00:02x}" for code in range(0xdc80, 0xdd00)}
        expected.update({0xdc7f: "\udc7f", 0xdd00: "\udd00"})
        for code, shown in expected.items():
            with self.subTest(code=hex(code)):
                line = io.StringIO()
                with contextlib.redirect_stdout(line):
                    gate.report(chr(code))
                self.assertEqual(line.getvalue(), shown + "\n")

    def test_main_reads_the_class_today(self):
        # main() runs on a page stamped 2026-01-01 with TODAY set to
        # 2000-01-01 and then to 2000-01-02, and reports the stamp as in the
        # future with each of those dates as today, so the case fails when
        # main() reads the wall clock, whatever its date.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        for today in ("2000-01-01", "2000-01-02"):
            with self.subTest(today=today):
                self.TODAY = today
                stdout = io.StringIO()
                self.assertEqual(self.run_main(stdout), 1)
                self.assertIn(f"article:modified_time 2026-01-01 is in the future (today is {today})",
                              stdout.getvalue())

    def test_git_calls_per_page(self):
        # check_page() makes 3 git calls for a page with no protected ref,
        # and 7 for a page restored exactly with it, 1 of them git
        # hash-object: 1 for the added date and from 2 to 6 for the last
        # change. main() makes 1 more, for the shallow status.
        self.change_and_restore_on_branch(protect=False)
        calls = self.record_gate_git()
        self.assert_stamp_problem(self.problems(), "2026-02-02")
        self.assertEqual(len(calls), 3, calls)
        self.protect_main()
        calls.clear()
        self.assertEqual(self.problems(), [])
        self.assertEqual(len(calls), 7, calls)
        self.assertEqual([call[0] for call in calls].count("hash-object"), 1, calls)
        calls.clear()
        self.assertEqual(self.run_main(io.StringIO()), 0)
        self.assertEqual(len(calls), 8, calls)
        self.assertEqual(calls[0], ("rev-parse", "--is-shallow-repository"), calls)

    def fake_git(self, prefix: tuple[str, ...], output: bytes) -> None:
        # From here until os.environ is restored, each git call whose
        # arguments after -C and the folder start with prefix prints output
        # in place of git's stdout, through a git on PATH that runs the real
        # git and keeps its stderr and exit code. In prefix and output,
        # {main} stands for main's tip, and in output {blob} stands for the
        # page's blob at HEAD.
        real = shutil.which("git")
        self.assertIsNotNone(real)
        main = self.git("rev-parse", "main").strip()
        prefix = tuple(arg.replace("{main}", main) for arg in prefix)
        output = output.replace(b"{main}", main.encode("ascii"))
        output = output.replace(b"{blob}", self.git("rev-parse", "HEAD:site/index.html").strip().encode("ascii"))
        folder = Path(tempfile.mkdtemp(dir=self.scratch))
        (folder / "git").write_text(f"#!{sys.executable} -I\n" + FAKE_GIT, encoding="utf-8")
        (folder / "git").chmod(0o755)
        os.environ.update(PAGE_METADATA_REAL_GIT=real, PAGE_METADATA_FAKE_ARGS="\n".join(prefix),
                          PAGE_METADATA_FAKE_OUTPUT=output.hex())
        os.environ["PATH"] = str(folder) + os.pathsep + os.environ["PATH"]

    def check_with_fake_git(self, prefix: tuple[str, ...], output: bytes,
                            *options: str) -> tuple[list[str] | None, str]:
        # A new repository, made with git init and options, holds a page
        # restored exactly with the protected ref. With fake_git() set for
        # prefix and output, the gate checks its history and the page. The
        # return value is the page's problems, or None when the check stops
        # with exit 3, and the gate's stderr.
        self.start_repository(*options)
        self.change_and_restore_on_branch()
        stderr = io.StringIO()
        with mock.patch.dict(os.environ), contextlib.redirect_stderr(stderr):
            self.fake_git(prefix, output)
            try:
                gate.require_full_history()
                return self.problems(), stderr.getvalue()
            except SystemExit as error:
                self.assertEqual(error.code, 3, stderr.getvalue())
                return None, stderr.getvalue()

    def test_unusable_git_output_exits_3(self):
        # Each git reading of the gate is given output that git does not
        # print there, and the check stops with exit 3 and names it as
        # output that the gate cannot use.
        entry = b"100644 blob {blob}\tsite/index.html\0"
        cases = [(("rev-parse",), b"yes\n"),
                 (("for-each-ref",), b"refs/remotes/origin/main HEAD\n"),
                 (("for-each-ref",), b" {main}\n"),
                 (("for-each-ref",), b"refs/remotes/origin/main/x zz\nrefs/remotes/origin/main {main}\n"),
                 (("for-each-ref",), b"refs/remotes/origin/main {main}"),
                 (("for-each-ref",), b"refs/remotes/origin/main {main}\n" * 2),
                 *[(("for-each-ref",), b"refs/remotes/origin/main/x " + name + b"\n")
                   for name in (b"0" * 39, b"0" * 41, b"0" * 63, b"0" * 65)],
                 (("merge-base",), b"HEAD\n"),
                 (("merge-base",), b"{main}\nHEAD\n"),
                 (("ls-tree",), entry.replace(b" blob ", b" blub ")),
                 (("ls-tree",), entry.replace(b"100644", b"100648")),
                 (("ls-tree",), entry.replace(b"100644", b"10064")),
                 (("ls-tree",), entry.replace(b"{blob}", b"{blob}0")),
                 (("ls-tree",), entry.replace(b"index", b"other")),
                 (("ls-tree",), entry.replace(b"\t", b" x\t")),
                 (("ls-tree",), entry * 2),
                 (("ls-tree",), entry[:-1]),
                 (("ls-tree",), entry.replace(b"100644", b"10064/")),
                 (("ls-tree",), entry.replace(b"100644", b"1006440")),
                 (("hash-object",), b"zz\n"),
                 *[(("hash-object",), name + b"\n")
                   for name in (b"0" * 39, b"0" * 41, b"0" * 63, b"0" * 65, b"/" * 40, b":" * 40, b"`" * 40,
                                b"g" * 40, b"0" * 40 + b"/" * 24, b"0" * 40 + b":" * 24,
                                b"0" * 40 + b"`" * 24, b"0" * 40 + b"g" * 24)],
                 (("log", "--diff-filter=A"), b"yesterday\n"),
                 (("log", "--diff-filter=A"), b"2026-02-30\n"),
                 (("log", "-1"), b"yesterday\n"),
                 (("log", "-1"), b"20260202\n"),
                 (("log", "-1"), b"2026-02-02\n2026-02-02\n")]
        # Output that is not of the form that git prints there: a ref
        # listing line whose refname is neither the protected refname nor
        # below it, or whose refname and object name are joined by a
        # character other than a space; a merge base line that is not 1
        # object name, the same object name on 2 merge base lines, next to
        # each other or not, the first or the last of them, a merge base
        # line whose object name differs in length from main's tip, first,
        # in the middle or last, or merge base output that does not end
        # with a line feed; an object name of 64 digits beside main's tip
        # of 40 in the tree entry at HEAD or at the merge base, or from git
        # hash-object; a tree entry whose mode and type are not a pair that
        # git prints, whose fields are joined by other than 1 space, or
        # which has no object name; a line that git prints with leading or
        # trailing whitespace, with a CR or with a blank line, or with no
        # line feed at its end; an object name in upper case or of 88 or
        # 104 digits; and shallow status or git hash-object output with no
        # line.
        cases += [(("for-each-ref",), b"refs/remotes/origin/mainx {main}\nrefs/remotes/origin/main {main}\n"),
                  (("for-each-ref",), b"refs/heads/main {main}\n"),
                  (("for-each-ref",), b"refs/remotes/origin/main\x0b{main}\n"),
                  (("for-each-ref",), b"refs/remotes/origin/main\t{main}\n"),
                  (("merge-base",), b"{main} {main}\n"),
                  (("merge-base",), b"{main}\t{main}\n"),
                  (("merge-base",), b"{main}"),
                  (("merge-base",), b"{main}\r\n"),
                  (("merge-base",), b"\n{main}\n"),
                  (("merge-base",), b"{main}\n{main}\n"),
                  (("merge-base",), b"{main}\n" + b"1" * 40 + b"\n{main}\n"),
                  (("merge-base",), b"{main}\n" + b"1" * 40 + b"\n" + b"2" * 40 + b"\n" + b"1" * 40 + b"\n"),
                  (("merge-base",), b"{main}\n" + b"1" * 64 + b"\n"),
                  (("merge-base",), b"{main}\n{main}" + b"0" * 24 + b"\n"),
                  (("merge-base",), b"{main}\n" + b"1" * 64 + b"\n" + b"2" * 40 + b"\n"),
                  (("merge-base",), b"{main}\n" + b"1" * 40 + b"\n" + b"2" * 64 + b"\n"),
                  (("merge-base",), b"{main}\n" + b"1" * 64 + b"\n" + b"2" * 64 + b"\n"),
                  (("merge-base",), b"1" * 64 + b"\n{main}\n" + b"2" * 40 + b"\n"),
                  (("merge-base",), b"{main}\n{main}\n" + b"1" * 40 + b"\n"),
                  (("merge-base",), b"1" * 64 + b"\n"),
                  (("merge-base",), b"1" * 64 + b"\n" + b"2" * 64 + b"\n"),
                  (("ls-tree", "-z", "HEAD"), entry.replace(b"{blob}", b"0123456789abcdef" * 4)),
                  (("ls-tree", "-z", "{main}"), entry.replace(b"{blob}", b"0123456789abcdef" * 4)),
                  (("hash-object",), b"0123456789abcdef" * 4 + b"\n"),
                  *[(("ls-tree",), entry.replace(b"100644 blob", pair))
                    for pair in (b"100644 tree", b"100644 commit", b"100755 tree", b"120000 commit",
                                 b"040000 blob", b"040000 commit", b"160000 blob", b"160000 tree",
                                 b"100664 blob", b"000000 blob", b"100644  blob", b"100644\x0bblob",
                                 b"100644\x0cblob")],
                  (("ls-tree",), entry.replace(b" {blob}", b"")),
                  (("rev-parse",), b"false"), (("rev-parse",), b""),
                  (("rev-parse",), b" false\n"),
                  (("rev-parse",), b"false\n\n"),
                  (("rev-parse",), b"false\r\n"),
                  (("rev-parse",), b"true"),
                  (("hash-object",), b"{blob}"),
                  (("hash-object",), b" {blob}\n"),
                  (("hash-object",), b"{blob}\n\n"),
                  (("hash-object",), b"{blob}\r\n"),
                  (("hash-object",), b""),
                  *[(("hash-object",), name + b"\n")
                    for name in (b"A" * 40, b"0" * 40 + b"A" * 24, b"0" * 88, b"0" * 104)],
                  (("log", "--diff-filter=A"), b"2026-01-01"),
                  (("log", "--diff-filter=A"), b"2026-01-01 \n"),
                  (("log", "--diff-filter=A"), b"\n2026-01-01\n"),
                  (("log", "--diff-filter=A"), b"2026-01-01\r\n"),
                  (("log", "--diff-filter=A"), b"2026-01-01\nyesterday\n"),
                  (("log", "-1"), b"2026-02-02"),
                  (("log", "-1"), b"\n")]
        for prefix, output in cases:
            with self.subTest(prefix=prefix, output=output):
                problems, stderr = self.check_with_fake_git(prefix, output)
                self.assertIsNone(problems, stderr)
                self.assertIn("printed output that the gate cannot use", stderr)

    def test_git_output_exit_3_messages(self):
        # A shallow clone, a merge base list with no line and a byte that is
        # not ASCII in a date each stop the check with exit 3 and their own
        # message.
        cases = [(("rev-parse",), b"true\n", "the repository is a shallow clone"),
                 (("merge-base",), b"", "printed no merge base"),
                 (("log", "--diff-filter=A"), b"\xff2026-01-01\n", "printed a byte that is not ASCII")]
        for prefix, output, words in cases:
            with self.subTest(prefix=prefix, output=output):
                problems, stderr = self.check_with_fake_git(prefix, output)
                self.assertIsNone(problems, stderr)
                self.assertIn(words, stderr)

    def test_byte_that_is_not_ascii_in_an_object_name_exits_3(self):
        # The byte 0xff before an object name stops the check with exit 3
        # and the message that names a byte that is not ASCII, not the
        # message for output that the gate cannot use, in each reading of
        # an object name: the protected refname's line of the ref listing,
        # a line below it listed first, the merge base, the blob entry at
        # HEAD, the blob entry at the merge base, a tree and a gitlink
        # entry at HEAD, and the git hash-object result. Each subtest fails
        # when its reading alone decodes the object name with a replacing
        # decode, which keeps exit 3 but gives the other message.
        entry = b"100644 blob {blob}\tsite/index.html\0"
        for prefix, output in ((("for-each-ref",), b"refs/remotes/origin/main \xff{main}\n"),
                               (("for-each-ref",),
                                b"refs/remotes/origin/main/x \xff{main}\nrefs/remotes/origin/main {main}\n"),
                               (("merge-base",), b"\xff{main}\n"),
                               (("ls-tree", "-z", "HEAD"), entry.replace(b"{blob}", b"\xff{blob}")),
                               (("ls-tree", "-z", "{main}"), entry.replace(b"{blob}", b"\xff{blob}")),
                               (("ls-tree", "-z", "HEAD"), b"040000 tree \xff{blob}\tsite/index.html\0"),
                               (("ls-tree", "-z", "HEAD"), b"160000 commit \xff{blob}\tsite/index.html\0"),
                               (("hash-object",), b"\xff{blob}\n")):
            with self.subTest(prefix=prefix, output=output):
                problems, stderr = self.check_with_fake_git(prefix, output)
                self.assertIsNone(problems, stderr)
                self.assertIn("printed a byte that is not ASCII", stderr)
                self.assertNotIn("printed output that the gate cannot use", stderr)

    def test_usable_git_output_is_read(self):
        # Output of the form that git prints is read: a tree or a gitlink
        # entry at the page's path is no blob, so the page is read at HEAD;
        # an added date of 1999-09-29 is compared with the published stamp;
        # and an object name of 40 digits from git hash-object, the length
        # of the blob's, is compared with the blob and differs.
        for output in (b"040000 tree {blob}\tsite/index.html\0", b"160000 commit {blob}\tsite/index.html\0"):
            with self.subTest(output=output):
                problems, stderr = self.check_with_fake_git(("ls-tree",), output)
                self.assertIsNotNone(problems, stderr)
                self.assert_stamp_problem(problems, "2026-02-02")
        with self.subTest(output="added 1999-09-29"):
            problems, stderr = self.check_with_fake_git(("log", "--diff-filter=A"), b"1999-09-29\n")
            self.assertIsNotNone(problems, stderr)
            self.assertIn("article:published_time is 2026-01-01 but git shows the file was added 1999-09-29; "
                          "correct the stamp, or record the exception in PUBLISHED_OVERRIDES", problems)
        with self.subTest(output="40 digits"):
            problems, stderr = self.check_with_fake_git(("hash-object",), b"0123456789abcdef" * 2 + b"01234567\n")
            self.assertIsNotNone(problems, stderr)
            self.assert_stamp_problem(problems, "2026-02-02")

    def test_shorter_object_name_in_sha256_repository_exits_3(self):
        # In a repository whose object names have 64 digits, an object name
        # of 40 digits as the merge base, in the tree entry at HEAD or at
        # the merge base, or from git hash-object stops the check with exit
        # 3, as a longer one does beside a tip of 40 digits.
        name = b"0123456789abcdef" * 2 + b"01234567"
        entry = b"100644 blob {blob}\tsite/index.html\0"
        for prefix, output in ((("merge-base",), name + b"\n"),
                               (("ls-tree", "-z", "HEAD"), entry.replace(b"{blob}", name)),
                               (("ls-tree", "-z", "{main}"), entry.replace(b"{blob}", name)),
                               (("hash-object",), name + b"\n")):
            with self.subTest(prefix=prefix, output=output):
                problems, stderr = self.check_with_fake_git(prefix, output, "--object-format=sha256")
                self.assertIsNone(problems, stderr)
                self.assertIn("printed output that the gate cannot use", stderr)

    def test_restored_page_in_sha256_repository_passes(self):
        # In a repository whose object names have 64 digits, as under
        # SHA-256, the tip, the merge base, the blobs and the git
        # hash-object result each have 64, so a page restored exactly with
        # the protected ref passes.
        self.start_repository("--object-format=sha256")
        self.change_and_restore_on_branch()
        self.assertEqual(len(self.git("rev-parse", "main").strip()), 64)
        self.assertEqual(self.problems(), [])

    def test_real_git_output_is_read(self):
        # Real git prints, through the gate's git(), a tree entry of mode
        # 100644, 100755 or 120000 with the type blob, 040000 with tree and
        # 160000 with commit, 1 line for the shallow status, the git
        # hash-object result, each date and the merge base, and a ref
        # listing of the protected refname alone, which leaves out
        # refs/remotes/origin/mainx and refs/remotes/origin/main-y. The
        # gate reads each: blob_at() gives the mode and blob of each blob
        # entry and None for the others, and protected_base() gives main's
        # tip.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        site = gate.SITE_ROOT
        (site / "run.sh").write_text("fixture\n", encoding="utf-8")
        (site / "run.sh").chmod(0o755)
        os.symlink("index.html", site / "link.html")
        (site / "folder").mkdir()
        (site / "folder" / "inner.html").write_text("fixture\n", encoding="utf-8")
        self.git("add", "-A")
        commit = self.git("rev-parse", "HEAD").strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{commit},site/gitlink")
        self.git("commit", "-q", "-m", "Entries on 2026-01-01")
        main = self.git("rev-parse", "HEAD").strip()
        for ref in ("refs/remotes/origin/main", "refs/remotes/origin/mainx", "refs/remotes/origin/main-y"):
            self.git("update-ref", ref, main)
        for path, mode, kind in (("site/index.html", "100644", "blob"), ("site/run.sh", "100755", "blob"),
                                 ("site/link.html", "120000", "blob"), ("site/folder", "040000", "tree"),
                                 ("site/gitlink", "160000", "commit")):
            with self.subTest(path=path):
                name = self.git("rev-parse", f"HEAD:{path}").strip()
                self.assertEqual(gate.git("ls-tree", "-z", "HEAD", "--", path),
                                 f"{mode} {kind} {name}\t{path}\0".encode("ascii"))
                self.assertEqual(gate.blob_at("HEAD", path), (mode, name) if kind == "blob" else None)
        self.assertEqual(gate.git("rev-parse", "--is-shallow-repository"), b"false\n")
        blob = self.git("rev-parse", "HEAD:site/index.html").strip()
        self.assertEqual(gate.git("hash-object", "--", "site/index.html"), blob.encode("ascii") + b"\n")
        self.assertEqual(gate.git("log", "--format=%cs", "HEAD", "--", "site"), b"2026-01-01\n" * 2)
        listing = f"refs/remotes/origin/main {main}\n".encode("ascii")
        self.assertEqual(gate.git("for-each-ref", "--format=%(refname) %(objectname)", "refs/remotes/origin/main"),
                         listing)
        self.assertEqual(gate.git("merge-base", "--all", "HEAD", main), main.encode("ascii") + b"\n")
        self.assertEqual(gate.protected_base(), main)
        gate.require_full_history()

    def test_git_that_cannot_be_executed_exits_3(self):
        # PATH names only a folder whose file named git has no execute
        # permission, so the gate's git() cannot run it for a reason other
        # than a missing file, which must stop the check rather than raise.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        folder = self.scratch / "locked"
        folder.mkdir()
        (folder / "git").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (folder / "git").chmod(0o644)
        os.environ["PATH"] = str(folder)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.require_full_history()
        self.assertEqual(caught.exception.code, 3)
        self.assertIn("git could not be run", stderr.getvalue())

    def test_page_added_twice_keeps_its_first_added_date(self):
        # The page is added on 2026-01-01, removed on 2026-01-10 and added
        # again on 2026-01-20 with its first published stamp. git log lists
        # both additions, newest first, and the oldest is the added date, so
        # the published stamp of 2026-01-01 matches.
        self.commit_page(self.MAIN_DATE, self.MAIN_DATE)
        self.git("rm", "-q", "--", "site/index.html")
        self.git("commit", "-q", "-m", "Page removed on 2026-01-10", date="2026-01-10")
        gate.SITE_ROOT.mkdir(exist_ok=True)
        self.commit_page("2026-01-20", "2026-01-20")
        self.assertEqual(gate.git("log", "--diff-filter=A", "--format=%cs", "--", "site/index.html"),
                         b"2026-01-20\n2026-01-01\n")
        self.assertEqual(gate.added_date("site/index.html"), "2026-01-01")
        self.assertEqual(self.problems(), [])

    def test_listing_line_below_protected_refname_is_not_checked_as_a_refname(self):
        # A ref listing line below the protected refname is read as a ref
        # other than the protected one whether or not its name follows the
        # refname rules of git, such as a name with a .. component or a NUL
        # byte, which git does not print. Beside the protected refname, the
        # page restored exactly is dated at the merge base and passes.
        for name in (b"refs/remotes/origin/main/a..b", b"refs/remotes/origin/main/a\0b"):
            with self.subTest(name=name):
                listing = name + b" {main}\nrefs/remotes/origin/main {main}\n"
                problems, stderr = self.check_with_fake_git(("for-each-ref",), listing)
                self.assertEqual(problems, [], stderr)

    def test_listing_line_of_other_length_exits_3(self):
        # A ref listing line whose object name differs in length from that
        # of the listing's first line stops the check with exit 3: the
        # protected refname's line, with main's tip of 40 digits, after a
        # line below it of 64; a line below the protected refname of 64
        # digits after the protected refname's line of 40, or after another
        # line below it of 40 with no protected refname listed; and a line
        # below it of 40 digits after a tip of 64 in a SHA-256 repository.
        other = b"0123456789abcdef" * 4
        protected = b"refs/remotes/origin/main {main}\n"
        below = b"refs/remotes/origin/main/x "
        for listing, options in ((below + other + b"\n" + protected, ()),
                                 (protected + below + other + b"\n", ()),
                                 (below + b"{main}\nrefs/remotes/origin/main/y " + other + b"\n", ()),
                                 (protected + below + other[:40] + b"\n", ("--object-format=sha256",))):
            with self.subTest(listing=listing, options=options):
                problems, stderr = self.check_with_fake_git(("for-each-ref",), listing, *options)
                self.assertIsNone(problems, stderr)
                self.assertIn("printed output that the gate cannot use", stderr)

    def test_tree_entry_of_other_length_exits_3(self):
        # A tree entry, which is no blob, at the page's path at HEAD whose
        # object name differs in length from the merge base's stops the
        # check with exit 3 rather than reading the page at HEAD: 64 digits
        # beside a merge base of 40, and 40 beside one of 64.
        for name, options in ((b"0123456789abcdef" * 4, ()),
                              (b"0123456789abcdef" * 2 + b"01234567", ("--object-format=sha256",))):
            with self.subTest(name=name, options=options):
                entry = b"040000 tree " + name + b"\tsite/index.html\0"
                problems, stderr = self.check_with_fake_git(("ls-tree", "-z", "HEAD"), entry, *options)
                self.assertIsNone(problems, stderr)
                self.assertIn("printed output that the gate cannot use", stderr)

    def test_gitlink_entry_of_other_length_exits_3(self):
        # A gitlink entry, which is no blob, at the page's path at HEAD
        # whose object name differs in length from the merge base's stops
        # the check with exit 3 rather than reading the page at HEAD: 64
        # digits beside a merge base of 40, and 40 beside one of 64.
        for name, options in ((b"0123456789abcdef" * 4, ()),
                              (b"0123456789abcdef" * 2 + b"01234567", ("--object-format=sha256",))):
            with self.subTest(name=name, options=options):
                entry = b"160000 commit " + name + b"\tsite/index.html\0"
                problems, stderr = self.check_with_fake_git(("ls-tree", "-z", "HEAD"), entry, *options)
                self.assertIsNone(problems, stderr)
                self.assertIn("printed output that the gate cannot use", stderr)

    def test_tree_entry_with_empty_name_exits_3(self):
        # A tree entry whose name after the tab is empty is not the page's
        # path, so the check stops with exit 3 rather than reading its blob.
        entry = b"100644 blob {blob}\t\0"
        problems, stderr = self.check_with_fake_git(("ls-tree",), entry)
        self.assertIsNone(problems, stderr)
        self.assertIn("printed output that the gate cannot use", stderr)


class EmptyValueTest(_PatchedGateTest):
    """Empty values on a page are read as values, not as absent ones."""

    def problems(self, html: str) -> list[str]:
        page = gate.SITE_ROOT / "index.html"
        page.write_text(html, encoding="utf-8")
        return gate.check_page(page, TODAY)[0]

    def test_empty_meta_author_matching_empty_json_ld_name_reports_only_that(self):
        # An empty meta author is reported as missing, and a JSON-LD Person
        # whose name is empty matches it, so no JSON-LD problem is added.
        html = PAGE.format(json_ld=article('{"@type": "Person", "name": ""}'))
        html = html.replace('content="Jeff Posluns"', 'content=""')
        self.assertEqual(self.problems(html), ['missing <meta name="author">'])

    def test_property_without_content_is_missing(self):
        # A required meta property with no content attribute is reported as
        # missing, as when its tag is absent.
        for prop, value in (("article:published_time", "2026-01-01"), ("article:modified_time", "2026-01-02"),
                            ("article:author", "https://posluns.ca")):
            with self.subTest(prop=prop):
                html = PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}'))
                html = html.replace(f'property="{prop}" content="{value}"', f'property="{prop}"')
                self.assertEqual(self.problems(html), [f"missing {prop}"])

    def test_empty_stamp_is_malformed(self):
        for label, stamp in (("article:published_time", "2026-01-01"), ("article:modified_time", "2026-01-02")):
            with self.subTest(label=label):
                html = PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}'))
                html = html.replace(f'property="{label}" content="{stamp}"', f'property="{label}" content=""')
                self.assertEqual(self.problems(html), [f"{label} is '', expected YYYY-MM-DD"])

    def test_falsy_co_author_entry_fails(self):
        # An author list that holds the meta author and an entry that is
        # empty or false but not null fails, as any other stray entry does.
        for entry in ("{}", '""', "0", "false", "[]"):
            with self.subTest(entry=entry):
                author = '[{"@type": "Person", "name": "Jeff Posluns"}, ' + entry + "]"
                self.assertEqual(self.problems(PAGE.format(json_ld=article(author))), [WRONG_PRIMARY_AUTHOR])


class ErrorKindTest(_PatchedGateTest):
    """Each failure that the gate catches stops the check with exit 3, or is
    reported as a problem, for each kind of error that can raise it."""

    def stop(self, call) -> str:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                call()
        self.assertEqual(caught.exception.code, 3, stderr.getvalue())
        return stderr.getvalue()

    def load(self, folder: Path) -> None:
        self.addCleanup(sys.modules.pop, "page_metadata_fixture", None)
        with mock.patch.object(gate, "TOOLS_DIR", folder):
            gate._load_sibling("page_metadata_fixture", ())

    def test_sibling_under_a_file_is_refused(self):
        # A tools folder that is a file makes os.lstat() fail with an error
        # other than a missing file.
        folder = gate.REPO_ROOT / "file"
        folder.write_text("fixture\n", encoding="utf-8")
        self.assertIn("could not be read", self.stop(lambda: self.load(folder)))

    def test_sibling_read_failure_is_refused(self):
        # A sibling whose read fails with an input and output error, which
        # is neither a missing file nor a refused permission.
        (gate.REPO_ROOT / "page_metadata_fixture.py").write_text("X = 1\n", encoding="utf-8")
        failure = OSError(5, "Input/output error")
        with mock.patch.object(gate.Path, "read_bytes", side_effect=failure):
            self.assertIn("could not be read", self.stop(lambda: self.load(gate.REPO_ROOT)))

    def test_sibling_that_exits_is_refused(self):
        (gate.REPO_ROOT / "page_metadata_fixture.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        self.assertIn("could not be loaded", self.stop(lambda: self.load(gate.REPO_ROOT)))

    def test_deeply_nested_json_ld_is_a_problem(self):
        page = gate.SITE_ROOT / "index.html"
        block = '<script type="application/ld+json">' + "[" * 200000 + "</script>"
        page.write_text(PAGE.format(json_ld=block), encoding="utf-8")
        problems = gate.check_page(page, TODAY)[0]
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith("JSON-LD does not parse"), problems)

    def test_page_that_is_a_folder_exits_3(self):
        # main() stops with exit 3 when reading a page fails with an error
        # other than a missing file or a refused permission.
        page = gate.SITE_ROOT / "index.html"
        page.mkdir()
        with mock.patch.object(gate, "require_full_history", lambda: None), \
                mock.patch.object(gate, "content_pages", lambda: [page]):
            self.assertIn("could not read site/index.html", self.stop(gate.main))


class PrimaryTypeTest(_PatchedGateTest):
    """Each primary JSON-LD type carries the page's author on its own."""

    def test_each_primary_type_satisfies_the_author_requirement(self):
        page = gate.SITE_ROOT / "index.html"
        for kind in ("Article", "NewsArticle", "TechArticle", "BlogPosting", "ScholarlyArticle", "Report",
                     "CreativeWork", "WebPage"):
            with self.subTest(kind=kind):
                block = ('<script type="application/ld+json">{"@context": "https://schema.org", "@type": "'
                         + kind + '", "author": {"@type": "Person", "name": "Jeff Posluns"}}</script>')
                page.write_text(PAGE.format(json_ld=block), encoding="utf-8")
                self.assertEqual(gate.check_page(page, TODAY)[0], [])


class SiblingNeedsTest(unittest.TestCase):
    """tools/check-page-metadata.py exits 3 and names the missing name when a
    sibling tool does not define a name that the gate needs from it."""

    def test_each_needed_name_is_required(self):
        needs = {"web_metadata.py": ("UrlError", "parse_origin", "meta_tags", "link_tags", "contained",
                                     "same_origin_path", "locate_on_disk"),
                 "sitemap_engine.py": ("EngineError", "load_config", "enumerate_pages")}
        for sibling, names in needs.items():
            for name in names:
                with self.subTest(sibling=sibling, name=name), tempfile.TemporaryDirectory() as scratch:
                    tools = Path(scratch) / "tools"
                    tools.mkdir()
                    for file in ("check-page-metadata.py", "web_metadata.py", "sitemap_engine.py"):
                        shutil.copyfile(Path(__file__).resolve().parent / file, tools / file)
                    with (tools / sibling).open("a", encoding="utf-8") as handle:
                        handle.write(f"\ndel {name}\n")
                    result = subprocess.run([sys.executable, "-I", str(tools / "check-page-metadata.py")],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 3, result.stderr[-300:])
                    self.assertIn(f"check-page-metadata: tools/{sibling} defines no {name}", result.stderr)


class RequiredPropertyTest(_PatchedGateTest):
    """A page without 1 of the required meta properties reports that
    property as missing, and no other problem."""

    def test_each_missing_required_property_is_reported(self):
        page = gate.SITE_ROOT / "index.html"
        html = PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}'))
        for prop in ("article:published_time", "article:modified_time", "article:author"):
            with self.subTest(prop=prop):
                lines = [line for line in html.splitlines(keepends=True) if f'property="{prop}"' not in line]
                self.assertEqual(len(lines), len(html.splitlines()) - 1)
                page.write_text("".join(lines), encoding="utf-8")
                self.assertEqual(gate.check_page(page, TODAY)[0], [f"missing {prop}"])


class AuthorEntryTest(_PatchedGateTest):
    """A primary entity whose author holds no entry fails, and an author
    name matches the meta author with each character at its ends for
    which str.isspace() is true removed, and no other."""

    def problems(self, author_member: str) -> list[str]:
        page = gate.SITE_ROOT / "index.html"
        block = ('<script type="application/ld+json">{"@context": "https://schema.org",'
                 ' "@type": "Article"' + author_member + "}</script>")
        page.write_text(PAGE.format(json_ld=block), encoding="utf-8")
        return gate.check_page(page, TODAY)[0]

    def test_primary_entity_with_no_author_entry_fails(self):
        # An author that is an empty array, null or an array that holds only
        # null, or no author property, names no author, so the primary
        # entity fails.
        for member in (', "author": []', ', "author": null', ', "author": [null]', ""):
            with self.subTest(member=member):
                self.assertEqual(self.problems(member), [WRONG_PRIMARY_AUTHOR])

    def test_padded_author_name_matches(self):
        # A name that holds the meta author between white space, as a
        # string or as a value object, matches it.
        for name in ('" Jeff Posluns\\t"', '{"@value": "\\nJeff Posluns "}'):
            with self.subTest(name=name):
                member = ', "author": {"@type": "Person", "name": ' + name + "}"
                self.assertEqual(self.problems(member), [])

    def test_name_is_trimmed_of_each_isspace_character_and_no_other(self):
        # Each character for which str.isspace() is true, such as U+0085,
        # U+00A0, U+3000 and U+001C to U+001F, is removed from the ends of
        # a name, as a string or as a value object; each other character,
        # such as U+200B, U+2060 or U+FEFF, is kept, so the name with it
        # at its ends does not match. Every code point is checked.
        spaces = [chr(code) for code in range(sys.maxunicode + 1) if chr(code).isspace()]
        for char in ("\x85", "\xa0", chr(0x3000), "\x1c", "\x1d", "\x1e", "\x1f"):
            self.assertIn(char, spaces)
        for char in (chr(0x200B), chr(0x2060), chr(0xFEFF), chr(0x180E), "x"):
            self.assertNotIn(char, spaces)
        wrong = []
        for code in range(sys.maxunicode + 1):
            char = chr(code)
            for name in (char + "Jeff Posluns" + char, {"@value": char + "Jeff Posluns" + char}):
                if gate._author_ok({"@type": "Person", "name": name}, "Jeff Posluns") != char.isspace():
                    wrong.append((f"U+{code:04X}", name))
        self.assertEqual(wrong, [])
        member = ', "author": {"@type": "Person", "name": "\\u3000Jeff Posluns\\u00a0"}'
        self.assertEqual(self.problems(member), [])

    def test_null_entry_beside_meta_author_is_skipped(self):
        # A null entry in an author list is no author, so the meta author
        # beside it passes on its own.
        self.assertEqual(self.problems(', "author": [{"@type": "Person", "name": "Jeff Posluns"}, null]'), [])


class GateGuardTest(_PatchedGateTest):
    """The gate reads each block, type and page that its guards admit, and
    its entry point runs main()."""

    def check(self, html: str) -> list[str]:
        page = gate.SITE_ROOT / "index.html"
        page.write_text(html, encoding="utf-8")
        return gate.check_page(page, TODAY)[0]

    def test_type_with_ascii_white_space_or_capitals_is_collected(self):
        # The type attribute is read with ASCII white space removed from its
        # ends and in lower case, so such a block is collected and checked.
        for kind in (" \t\napplication/ld+json\r\f", "APPLICATION/LD+JSON"):
            with self.subTest(kind=kind):
                block = article('{"@type": "Person", "name": "Mallory"}').replace(
                    '<script type="application/ld+json">', f'<script type="{kind}">')
                self.assertEqual(self.check(PAGE.format(json_ld=block)), [WRONG_PRIMARY_AUTHOR])

    def test_type_with_other_white_space_is_not_collected(self):
        # Only ASCII white space, space, TAB, LF, FF and CR, is removed from
        # the ends of the type attribute, so a type with another character
        # at its ends, such as VT, U+00A0 or U+2060, is no ld+json type and
        # the block is not collected.
        others = [chr(code) for code in range(sys.maxunicode + 1)
                  if chr(code).isspace() and chr(code) not in " \t\n\f\r"]
        for char in [*others, chr(0x200B), chr(0x2060)]:
            with self.subTest(char=f"U+{ord(char):04X}"):
                block = article('{"@type": "Person", "name": "Mallory"}').replace(
                    '<script type="application/ld+json">', f'<script type="{char}application/ld+json{char}">')
                self.assertEqual(self.check(PAGE.format(json_ld=block)), [NO_AUTHOR_MESSAGE])

    def test_unclosed_empty_block_at_end_is_no_block(self):
        # An ld+json script that is opened at the end of the page and holds
        # nothing gives no block, so no parse problem is reported for it.
        html = PAGE.format(json_ld="").replace("</head><body></body></html>\n", "")
        self.assertEqual(self.check(html + '<script type="application/ld+json">'), [NO_AUTHOR_MESSAGE])

    def test_end_tag_in_self_closed_block_does_not_end_it(self):
        # The content of a self-closed ld+json script runs to </script>, so
        # the end tag of another element in it does not end the block, and
        # the content after that tag is still read.
        block = ('<script type="application/ld+json"/>'
                 '{"@type": "Article", "author": {"@type": "Person", "name": "Jeff Posluns"}}</p>'
                 '{"@type": "Article", "author": {"@type": "Person", "name": "Mallory"}}</script>')
        problems = self.check(PAGE.format(json_ld=block))
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith("JSON-LD does not parse"), problems)

    def test_type_list_is_read_and_its_other_members_are_skipped(self):
        # An @type that is a list is read as its strings, and a member that
        # is not a string is skipped.
        block = ('<script type="application/ld+json">{"@type": ["Article", {"x": 1}],'
                 ' "author": {"@type": ["Person", ["y"]], "name": "Jeff Posluns"}}</script>')
        self.assertEqual(self.check(PAGE.format(json_ld=block)), [])

    def test_failed_git_message_is_stripped(self):
        # The exit-3 message of a failed git call shows git's stderr with
        # the white space at its ends removed, so it ends with 1 line feed.
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                gate.git("--no-such-option")
        self.assertEqual(caught.exception.code, 3)
        message = stderr.getvalue()
        self.assertTrue(message.startswith("check-page-metadata: git --no-such-option failed: "), message)
        self.assertFalse(message.endswith("\n\n"), message)
        self.assertEqual(message, message.strip() + "\n")

    def test_failed_git_message_trims_each_isspace_character_and_no_other(self):
        # git's stderr is trimmed as str.strip() trims it: each character
        # at its ends for which str.isspace() is true, such as U+3000,
        # U+001C and U+0085, is removed at the start and at the end, and
        # each other character, such as U+200B, is kept. Every code point
        # other than a surrogate, which UTF-8 does not encode, is checked.
        spaces = [chr(code) for code in range(sys.maxunicode + 1) if chr(code).isspace()]
        for char in ("\x85", chr(0x3000), "\x1c", "\n"):
            self.assertIn(char, spaces)
        self.assertNotIn(chr(0x200B), spaces)
        printed = [b""]
        stderr = io.StringIO()
        wrong = []
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(gate.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
                    ["git"], 1, stdout=b"", stderr=printed[0])), \
                contextlib.redirect_stderr(stderr):
            for code in itertools.chain(range(0xD800), range(0xE000, sys.maxunicode + 1)):
                char = chr(code)
                printed[0] = (char + "fatal: bad" + char).encode("utf-8")
                stderr.seek(0)
                stderr.truncate()
                try:
                    gate.git("status")
                except SystemExit as error:
                    exit_code = error.code
                else:
                    exit_code = None
                kept = "" if char in spaces else char
                if (exit_code != 3 or stderr.getvalue()
                        != f"check-page-metadata: git status failed: {kept}fatal: bad{kept}\n"):
                    wrong.append(f"U+{code:04X}")
        self.assertEqual(wrong, [])

    def test_element_other_than_script_with_ld_json_type_is_not_collected(self):
        # Only a script element is collected: another element with the
        # ld+json type, here in the body after the page's own block, is not
        # read as JSON-LD.
        div = ('<div type="application/ld+json">{"@type": "Article", '
               '"author": {"@type": "Person", "name": "Mallory"}}</div>')
        html = PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}'))
        self.assertIn("<body></body>", html)
        self.assertEqual(self.check(html.replace("<body></body>", "<body>" + div + "</body>")), [])

    def test_pages_that_disagree_on_the_author_fail(self):
        # 2 pages that each name their own author consistently fail together.
        pages = []
        for name, author in (("a.html", "Jeff Posluns"), ("b.html", "Someone Else")):
            page = gate.SITE_ROOT / name
            html = PAGE.format(json_ld=article('{"@type": "Person", "name": "' + author + '"}'))
            page.write_text(html.replace('content="Jeff Posluns"', f'content="{author}"'), encoding="utf-8")
            pages.append(page)
        stdout = io.StringIO()
        with mock.patch.object(gate, "require_full_history", lambda: None), \
                mock.patch.object(gate, "content_pages", lambda: pages), contextlib.redirect_stdout(stdout):
            self.assertEqual(gate.main(), 1)
        self.assertIn("pages disagree on the author: 'Jeff Posluns' on 1 page(s); 'Someone Else' on 1 page(s)",
                      stdout.getvalue())

    def test_page_with_no_meta_author_beside_agreeing_pages_names_no_author(self):
        # A page whose meta author is absent or empty names no author, so
        # beside 2 pages that agree it gives its own problems and no
        # disagreement across pages.
        for meta in ("", '<meta name="author" content="">'):
            with self.subTest(meta=meta):
                pages = []
                for name in ("a.html", "b.html", "c.html"):
                    page = gate.SITE_ROOT / name
                    html = PAGE.format(json_ld=article('{"@type": "Person", "name": "Jeff Posluns"}'))
                    if name == "c.html":
                        html = html.replace('<meta name="author" content="Jeff Posluns">', meta)
                        self.assertNotIn('content="Jeff Posluns"', html)
                    page.write_text(html, encoding="utf-8")
                    pages.append(page)
                stdout = io.StringIO()
                with mock.patch.object(gate, "require_full_history", lambda: None), \
                        mock.patch.object(gate, "content_pages", lambda: pages), contextlib.redirect_stdout(stdout):
                    self.assertEqual(gate.main(), 1)
                report = stdout.getvalue()
                self.assertIn('missing <meta name="author">', report)
                self.assertNotIn("pages disagree on the author", report)
                self.assertIn("2 problem(s) across 1 page(s).", report)

    def test_script_entry_point_runs_main(self):
        # Run as a script with no git on PATH, the gate runs main() and
        # stops with exit 3.
        with tempfile.TemporaryDirectory() as empty:
            result = subprocess.run([sys.executable, "-I", str(MODULE_PATH)], capture_output=True, text=True,
                                    env={"PATH": empty})
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("git could not be run", result.stderr)


if __name__ == "__main__":
    unittest.main()
