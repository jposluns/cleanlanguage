#!/usr/bin/env python3
"""Tests for the page metadata gate's JSON-LD author requirement.

The gate must fail a page whose JSON-LD carries no author object with a
non-empty name, not merely check agreement when a name happens to be present.
These tests pin that requirement, and the preserved disagreement checks, on
fixture pages. They run offline with the standard library: the fixtures patch
the module's git readers, so no history is needed. The CI workflow invokes this
file before the gate itself runs against the real pages.
"""

from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
