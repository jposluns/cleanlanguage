#!/usr/bin/env python3
"""Tests for the page metadata gate's JSON-LD author requirement.

The gate must fail a page whose JSON-LD carries no author object with a
non-empty name, not merely check agreement when a name happens to be present.
These tests pin that requirement, and the preserved disagreement checks, on
fixture pages. They run offline with the standard library: the fixtures patch
the module's git readers, so no history is needed. The CI workflow invokes this
file before the gate itself runs against the real pages.

They also pin the gate's meta-tag parsing, its handling of an unreadable
(non-UTF-8) page, and its containment of image references to the site
directory.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

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
        # names the meta author must NOT rescue it (the round-4 false-green).
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
        self.assertFalse(
            any("but the file last changed" in p for p in problems), problems)

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

    def test_modified_in_future_still_rejected(self):
        # modified is after today; the tolerance branch stays silent (changed
        # equals modified) so only the future check fires.
        problems = self.check(
            published="2026-01-01", modified="2026-02-15",
            changed="2026-02-15", today="2026-02-01")
        self.assertTrue(
            any("is in the future" in p for p in problems), problems)


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


if __name__ == "__main__":
    unittest.main()
