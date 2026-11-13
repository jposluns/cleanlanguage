#!/usr/bin/env python3
"""Tests for the page metadata gate's JSON-LD author requirement.

The gate must fail a page whose JSON-LD carries no author object with a
non-empty name, not merely check agreement when a name happens to be present.
These tests pin that requirement, and the preserved disagreement checks, on
fixture pages. They run offline with the standard library. Most fixtures patch
the module's git readers, so no history is needed; ProtectedLineHistoryTest
builds its history with git in a temporary repository, so git must be on PATH.
The CI workflow invokes this file before the gate runs against the real pages.

They also pin the gate's meta-tag parsing, its handling of an unreadable
(non-UTF-8) page, and its containment of image references to the site
directory.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
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
        # names the meta author must NOT rescue it, which would be a false green.
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
        # stamps, so the sole problem that can surface is the modified-stamp one.
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
        # 7-day tolerance; today is well after both. The OLD gate flagged any
        # changed > modified; the NEW gate tolerates the short window.
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
        # The file last changed exactly D + 7 days, the tolerance boundary. The
        # check is `> tolerance`, so exactly 7 passes; a `>=` mutation would fail
        # this.
        problems = self.check(
            published="2026-01-01", modified="2026-01-10",
            changed="2026-01-17", today="2026-02-01")
        self.assertEqual(problems, [], problems)

    def test_stamp_one_day_past_tolerance_fails(self):
        # The file last changed D + 8 days, one day past the boundary.
        problems = self.check(
            published="2026-01-01", modified="2026-01-10",
            changed="2026-01-18", today="2026-02-01")
        self.assertTrue(
            any("beyond the 7-day tolerance" in p for p in problems), problems)

    def test_modified_in_future_still_rejected(self):
        # modified is after today; the tolerance branch stays silent (changed
        # equals modified) so only the future check fires.
        problems = self.check(
            published="2026-01-01", modified="2026-02-15",
            changed="2026-02-15", today="2026-02-01")
        self.assertTrue(
            any("is in the future" in p for p in problems), problems)

    def test_invalid_calendar_date_is_reported_not_crashed(self):
        # An ISO-shaped but invalid date (fromisoformat rejects it) must produce
        # a clean problem, not a traceback. Before the guard, the tolerance math
        # raised ValueError here.
        problems = self.check(
            published="2026-01-01", modified="2026-13-40",
            changed="2026-01-14", today="2026-02-01")
        self.assertTrue(any("not a real calendar date" in p for p in problems), problems)


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
        # A traversal to a MISSING out-of-tree target must be reported as a
        # containment violation, not as a plain "does not exist": the old
        # unresolved code emitted "does not exist", so asserting the
        # "outside" message makes this a real change-detector for fix (c).
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
        # card.png. The old gate looked for site/:443/card.png and false-failed.
        problems = self._problems(_img_meta("https://cleanlanguage.ai:443/card.png"),
                                  files=["card.png"])
        self.assertEqual(problems, [])

    def test_subdomain_lookalike_is_ignored(self):
        problems = self._problems(_img_meta("https://cleanlanguage.ai.evil/card.png"))
        self.assertEqual(problems, [])

    def test_query_and_fragment_are_stripped(self):
        problems = self._problems(_img_meta("https://cleanlanguage.ai/card.png?v=1#top"),
                                  files=["card.png"])
        self.assertEqual(problems, [])

    def test_backslash_url_missing_is_reported(self):
        # A browser normalizes the backslash to a slash, so this is on-origin and
        # points at a missing file. The old textual check also caught it; the new
        # parser must not silently pass it.
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
        # Parity: og:image present, twitter:image missing -> the twitter reference
        # is reported (passes before and after; guards the reference loop).
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
        # Parity guard against over-suppression: the author after a closed
        # template is active and satisfies the requirement.
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
        # og:image traverses THROUGH an existing file: a content problem (exit 1),
        # never a whole-gate exit-3 traceback.
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
    """6 of the ways a sibling tool can fail to load, each a fault on 1 file
    with the words of the refusal it gives: the file missing, its mode 000, its
    mode 000 beside a valid cached file, a syntax error, the definition of
    attribute renamed, and a syntax error beside a cached file of the unbroken
    source that the normal loader runs without comparing it with the source (an
    unchecked hash-based file). The tool must always read the source, so that no
    cached file stands in for it. Root reads a file whatever its mode, so under
    root the 2 mode-000 faults skip their case instead."""
    def missing(path: Path) -> None:
        path.unlink()

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
            ("with a syntax error beside a stale cached file", stale, "could not be loaded")]


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
    body, so the sole problem that can surface is the modified-stamp one."""
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


class ProtectedLineHistoryTest(unittest.TestCase):
    """last_change_date() dates a page at the merge base of HEAD and
    refs/remotes/origin/main only when that base is the only one, the page's
    mode and blob at HEAD equal its mode and blob there, and git hash-object of
    the working-tree page gives its blob at HEAD; otherwise it reads at HEAD,
    and a failed git call exits 3. Each test runs in a temporary repository
    made by start_repository() with git init --template=, each commit is made
    through the class's git() with a fixture identity and a fixed date, and
    each call of check_page() passes the fixed TODAY. isolate_git() keeps the
    suite's and the gate's git calls from reading the system and global
    configuration, configuration from GIT_ variables, the user's attributes and
    ignore files, and the system's attributes file. Cases plant configuration
    through GIT_CONFIG_COUNT before isolate_git() runs, a GIT_CONFIG_SYSTEM
    file after it runs, and a user attributes file and a user ignore file at
    both default paths, and test_repository_has_no_template_files checks for
    template files. GIT_CONFIG_GLOBAL and HOME are overlapping layers: git
    reads ~/.gitconfig only when both are dropped, so no case fails when only 1
    of them is. No case plants a system attributes file, since git has no
    variable that moves it. The class still takes inputs from the machine, such
    as the git binary found on PATH, with its version and built-in defaults,
    the locale, and the folder that tempfile picks."""

    TODAY = "2026-03-01"
    MAIN_DATE = "2026-01-01"

    def setUp(self):
        environ = mock.patch.dict(os.environ)
        environ.start()
        self.addCleanup(environ.stop)
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
        # case fails when only 1 of them is. No case plants a system attributes
        # file, since git has no variable that moves it. os.environ is restored
        # when the test ends.
        for key in [key for key in os.environ if key.startswith("GIT_")]:
            del os.environ[key]
        os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        os.environ["GIT_ATTR_NOSYSTEM"] = "1"
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        os.environ["HOME"] = home.name
        os.environ["XDG_CONFIG_HOME"] = home.name

    def start_repository(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        gate.REPO_ROOT = root
        gate.SITE_ROOT = root / "site"
        gate.SITE_ROOT.mkdir()
        self.page = gate.SITE_ROOT / "index.html"
        self.git("init", "-q", "--template=", "-b", "main")

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

    def test_user_attributes_and_ignore_files_are_not_read(self):
        # A user attributes file that re-encodes HTML and a user ignore file
        # that lists README and the site folder are planted at both default
        # paths. Through the suite's git and the gate's git(), the page has
        # no working-tree-encoding attribute, no file is ignored, and git
        # add of the page and README succeeds, so the case fails when git
        # reads either planted file.
        hostile = tempfile.TemporaryDirectory()
        self.addCleanup(hostile.cleanup)
        for config in (Path(hostile.name, ".config", "git"), Path(hostile.name, "xdg", "git")):
            config.mkdir(parents=True)
            (config / "attributes").write_text("*.html working-tree-encoding=UTF-16\n", encoding="utf-8")
            (config / "ignore").write_text("README\nsite/\n", encoding="utf-8")
        os.environ["HOME"] = hostile.name
        os.environ["XDG_CONFIG_HOME"] = str(Path(hostile.name, "xdg"))
        self.isolate_git()
        self.page.write_text(history_page(self.MAIN_DATE), encoding="utf-8")
        (gate.REPO_ROOT / "README").write_text("fixture\n", encoding="utf-8")
        gits = (("suite", self.git), ("gate", gate.git))
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
        for label, git in (("suite", self.git), ("gate", gate.git)):
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

    def test_system_configuration_is_not_read(self):
        # A system configuration file, named by GIT_CONFIG_SYSTEM after
        # isolate_git() runs, signs each commit with a program that fails,
        # so git commit fails when git reads it.
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        system = Path(scratch.name, "gitconfig")
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
        # added it, so the published stamp of 2026-02-01 matches.
        self.commit_other_file(self.MAIN_DATE)
        self.git("switch", "-q", "-c", "topic")
        self.commit_page("2026-02-01", "2026-02-01", published="2026-02-01")
        self.git("switch", "-q", "main")
        self.git("merge", "-q", "--no-ff", "-m", "Merge topic", "topic", date="2026-02-20")
        self.assertEqual(gate.added_date("site/index.html"), "2026-02-01")
        self.assertEqual(self.problems(), [])

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


if __name__ == "__main__":
    unittest.main()
