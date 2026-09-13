#!/usr/bin/env python3
"""Tests for the shared web-metadata helpers.

These pin the context-aware meta and link collector, the same-origin URL
normalization, and the on-disk location logic that both the page-metadata gate
and the sitemap engine now build on. They run offline with the standard library.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "web_metadata.py"
spec = importlib.util.spec_from_file_location("web_metadata", MODULE_PATH)
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)

ORIGIN = "https://cleanlanguage.ai"


class CollectorTest(unittest.TestCase):
    def metas(self, text):
        return wm.meta_tags(text)

    def test_double_quoted(self):
        self.assertEqual(self.metas('<meta name="author" content="Jeff">'),
                         [{"name": "author", "content": "Jeff"}])

    def test_single_quoted(self):
        self.assertEqual(self.metas("<meta name='author' content='Jeff'>"),
                         [{"name": "author", "content": "Jeff"}])

    def test_unquoted(self):
        self.assertEqual(self.metas("<meta name=author content=Jeff>"),
                         [{"name": "author", "content": "Jeff"}])

    def test_uppercase_names(self):
        self.assertEqual(self.metas('<META NAME="author" CONTENT="Jeff">'),
                         [{"name": "author", "content": "Jeff"}])

    def test_void_self_closing_meta(self):
        self.assertEqual(self.metas('<meta name="author" content="Jeff"/>'),
                         [{"name": "author", "content": "Jeff"}])

    def test_first_duplicate_attribute_wins(self):
        self.assertEqual(self.metas('<meta name="a" name="b" content="x">'),
                         [{"name": "a", "content": "x"}])

    def test_source_order_preserved(self):
        metas = self.metas('<meta name="a" content="1"><meta name="b" content="2">')
        self.assertEqual([m["name"] for m in metas], ["a", "b"])

    def test_both_name_and_property(self):
        self.assertEqual(
            self.metas('<meta name="og:image" property="og:image" content="x">'),
            [{"name": "og:image", "property": "og:image", "content": "x"}])

    def test_quoted_gt_in_attribute(self):
        self.assertEqual(self.metas('<meta name="author" content="a > b">'),
                         [{"name": "author", "content": "a > b"}])

    def test_commented_tag_absent(self):
        self.assertEqual(self.metas('<!-- <meta name="author" content="ghost"> -->'), [])

    def test_link_collected(self):
        links = wm.link_tags('<link rel="canonical" href="https://x/">')
        self.assertEqual(links, [{"rel": "canonical", "href": "https://x/"}])

    def test_meta_inside_template_absent(self):
        self.assertEqual(self.metas('<template><meta name="author" content="x"></template>'), [])

    def test_meta_inside_noscript_absent(self):
        self.assertEqual(self.metas('<noscript><meta name="author" content="x"></noscript>'), [])

    def test_link_inside_template_absent(self):
        self.assertEqual(wm.link_tags('<template><link rel="canonical" href="x"></template>'), [])

    def test_nested_inert_fully_suppressed(self):
        self.assertEqual(
            self.metas('<template><noscript><meta name="a" content="x"></noscript></template>'), [])

    def test_collection_resumes_after_closed_container(self):
        self.assertEqual(
            self.metas('<template><meta name="a" content="x"></template>'
                       '<meta name="b" content="y">'),
            [{"name": "b", "content": "y"}])

    def test_end_tag_over_unclosed_inner_recovers(self):
        # </template> closing over an unclosed <noscript>: a depth counter would
        # stay stuck; the stack pops both and collection resumes.
        self.assertEqual(
            self.metas('<template><noscript></template><meta name="a" content="x">'),
            [{"name": "a", "content": "x"}])

    def test_self_closing_template_opens_suppression(self):
        # A browser ignores the slash on a non-void element, so <template/> opens
        # an inert context that is never closed and the following meta is inert.
        self.assertEqual(self.metas('<template/><meta name="a" content="x">'), [])

    def test_meta_inside_script_absent(self):
        self.assertEqual(self.metas('<script><meta name="a" content="x"></script>'), [])

    def test_meta_inside_style_and_title_absent(self):
        self.assertEqual(self.metas('<style><meta name="a" content="x"></style>'
                                    '<title><meta name="b" content="y"></title>'), [])


class SameOriginPathTest(unittest.TestCase):
    def path(self, url):
        return wm.same_origin_path(url, ORIGIN)

    def test_plain_on_origin(self):
        self.assertEqual(self.path("https://cleanlanguage.ai/card.png"), "/card.png")

    def test_uppercase_scheme_and_host(self):
        self.assertEqual(self.path("HTTPS://CLEANLANGUAGE.AI/card.png"), "/card.png")

    def test_explicit_default_port(self):
        self.assertEqual(self.path("https://cleanlanguage.ai:443/card.png"), "/card.png")

    def test_subdomain_lookalike_is_off_origin(self):
        self.assertIsNone(self.path("https://cleanlanguage.ai.evil/card.png"))

    def test_non_default_port_is_off_origin(self):
        self.assertIsNone(self.path("https://cleanlanguage.ai:8443/card.png"))

    def test_query_and_fragment_stripped(self):
        self.assertEqual(self.path("https://cleanlanguage.ai/card.png?v=1#top"), "/card.png")

    def test_relative_is_none(self):
        self.assertIsNone(self.path("/card.png"))

    def test_scheme_relative_is_none(self):
        self.assertIsNone(self.path("//cleanlanguage.ai/card.png"))

    def test_other_scheme_is_none(self):
        self.assertIsNone(self.path("ftp://cleanlanguage.ai/card.png"))

    def test_other_origin_is_none(self):
        self.assertIsNone(self.path("https://example.com/card.png"))

    def test_raw_nul_raises(self):
        with self.assertRaises(wm.UrlError):
            self.path("https://cleanlanguage.ai/\x00.png")

    def test_encoded_nul_raises(self):
        with self.assertRaises(wm.UrlError):
            self.path("https://cleanlanguage.ai/%00.png")

    def test_malformed_escape_raises(self):
        with self.assertRaises(wm.UrlError):
            self.path("https://cleanlanguage.ai/%zz.png")

    def test_malformed_port_raises(self):
        with self.assertRaises(wm.UrlError):
            self.path("https://cleanlanguage.ai:99999x/card.png")

    def test_raw_space_in_path_raises(self):
        with self.assertRaises(wm.UrlError):
            self.path("https://cleanlanguage.ai/a b.png")

    def test_encoded_separator_raises(self):
        with self.assertRaises(wm.UrlError):
            self.path("https://cleanlanguage.ai/a%2Fb.png")

    def test_encoded_backslash_raises(self):
        with self.assertRaises(wm.UrlError):
            self.path("https://cleanlanguage.ai/a%5Cb.png")

    def test_encoded_space_decodes_and_maps(self):
        self.assertEqual(self.path("https://cleanlanguage.ai/my%20card.png"), "/my card.png")

    def test_parse_origin_rejects_non_https(self):
        with self.assertRaises(wm.UrlError):
            wm.parse_origin("ftp://cleanlanguage.ai")


class LocateOnDiskTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def test_existing_file_ok(self):
        (self.root / "card.png").write_bytes(b"x")
        status, target = wm.locate_on_disk("card.png", self.root)
        self.assertEqual(status, "ok")
        self.assertEqual(target, self.root / "card.png")

    def test_case_mismatch_reports_actual_spelling(self):
        (self.root / "card.png").write_bytes(b"x")
        status, target = wm.locate_on_disk("CARD.PNG", self.root)
        self.assertEqual(status, "case")
        self.assertEqual(target.name, "card.png")

    def test_missing_file(self):
        status, _ = wm.locate_on_disk("nope.png", self.root)
        self.assertEqual(status, "missing")

    def test_traversal_outside(self):
        status, _ = wm.locate_on_disk("../escape.png", self.root)
        self.assertEqual(status, "outside")

    def test_directory_target_is_missing(self):
        (self.root / "sub").mkdir()
        status, _ = wm.locate_on_disk("sub", self.root)
        self.assertEqual(status, "missing")

    def test_symlink_escaping_root_is_outside(self):
        outside = Path(self._tmp.name).parent / ("out-" + self.root.name)
        outside.write_text("x", encoding="utf-8")
        try:
            (self.root / "link.png").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        status, _ = wm.locate_on_disk("link.png", self.root)
        self.assertEqual(status, "outside")
        outside.unlink()


if __name__ == "__main__":
    unittest.main()
