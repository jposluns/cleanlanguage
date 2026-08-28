#!/usr/bin/env python3
"""Tests for the sitemap engine.

This is the repository's first test file, a deliberate new idiom justified by
the engine's role as a fleet reference: the generator will be copied to other
sites, so its behaviour is pinned here rather than only checked by eye. Runs
offline with the standard library; the CI workflow invokes it after the verify
gate.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sitemap_engine as engine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

PAGE = """<!doctype html>
<html><head>
<meta property="article:modified_time" content="{modified}">
<link rel="canonical" href="{canonical}">
{robots}
</head><body></body></html>
"""


def make_repo(tmp: Path, pages: dict[str, dict]) -> Path:
    """pages maps a URL path like '' or 'guide' to its fields; writes an index
    per entry and returns a config dict-ready repo root."""
    site = tmp / "site"
    site.mkdir(parents=True, exist_ok=True)
    for where, fields in pages.items():
        directory = site if where == "" else site / where
        directory.mkdir(parents=True, exist_ok=True)
        url = "https://x.test/" if where == "" else f"https://x.test/{where}/"
        robots = (
            f'<meta name="robots" content="{fields["robots"]}">'
            if fields.get("robots")
            else ""
        )
        (directory / "index.html").write_text(
            PAGE.format(
                modified=fields.get("modified", "2026-01-01"),
                canonical=fields.get("canonical", url),
                robots=robots,
            ),
            encoding="utf-8",
        )
    return tmp


def config(**overrides) -> dict:
    base = {
        "schema": 1,
        "base_url": "https://x.test",
        "site_root": "site",
        "output": "site/sitemap.xml",
        "include": ["index.html", "*/index.html"],
        "exclude": ["404.html"],
        "lastmod": {"source": "html_meta_property", "key": "article:modified_time"},
    }
    base.update(overrides)
    return base


class StyleTest(unittest.TestCase):
    def test_exact_bytes(self):
        out = engine.render([("https://x.test/", "2026-01-01")])
        self.assertEqual(
            out,
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            b"  <url>\n"
            b"    <loc>https://x.test/</loc>\n"
            b"    <lastmod>2026-01-01</lastmod>\n"
            b"  </url>\n"
            b"</urlset>\n",
        )

    def test_escapes_ampersand(self):
        out = engine.render([("https://x.test/?a&b", "2026-01-01")]).decode()
        self.assertIn("<loc>https://x.test/?a&amp;b</loc>", out)


class BuildTest(unittest.TestCase):
    def build(self, tmp, pages, **cfg):
        make_repo(tmp, pages)
        return engine.build_entries(config(**cfg), tmp)

    def test_sorted_and_root_first(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            entries = self.build(Path(d), {"": {}, "zebra": {}, "alpha": {}})
            self.assertEqual(
                [u for u, _ in entries],
                ["https://x.test/", "https://x.test/alpha/", "https://x.test/zebra/"],
            )

    def test_noindex_excluded(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            entries = self.build(Path(d), {"": {}, "hidden": {"robots": "noindex"}})
            self.assertEqual([u for u, _ in entries], ["https://x.test/"])

    def test_canonical_mismatch_fails(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(engine.EngineError):
                self.build(Path(d), {"": {"canonical": "https://x.test/wrong/"}})

    def test_missing_stamp_fails(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<link rel="canonical" href="https://x.test/">', encoding="utf-8"
            )
            with self.assertRaises(engine.EngineError):
                engine.build_entries(config(), Path(d))

    def test_empty_set_fails(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "site").mkdir()
            with self.assertRaises(engine.EngineError):
                engine.build_entries(config(), Path(d))


class WriteVerifyTest(unittest.TestCase):
    def test_write_then_verify_and_determinism(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), {"": {}, "guide": {}})
            engine.write(config(), root)
            ok, _ = engine.verify(config(), root)
            self.assertTrue(ok)
            first = engine.generate_bytes(config(), root)
            second = engine.generate_bytes(config(), root)
            self.assertEqual(first, second)

    def test_add_page_then_stale_then_repair(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), {"": {}})
            engine.write(config(), root)
            make_repo(root, {"new": {}})  # add a page, sitemap now stale
            ok, message = engine.verify(config(), root)
            self.assertFalse(ok)
            self.assertIn("--write", message)
            engine.write(config(), root)
            ok, _ = engine.verify(config(), root)
            self.assertTrue(ok)

    def test_hand_edit_caught(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), {"": {}, "guide": {}})
            engine.write(config(), root)
            target = root / "site" / "sitemap.xml"
            target.write_bytes(target.read_bytes().replace(b"2026-01-01", b"2019-09-09"))
            ok, message = engine.verify(config(), root)
            self.assertFalse(ok)
            self.assertIn("differs", message)


class LiveTreeTest(unittest.TestCase):
    def test_committed_sitemap_matches(self):
        cfg = engine.load_config(REPO_ROOT / "tools" / "sitemap-config.json")
        ok, message = engine.verify(cfg, REPO_ROOT)
        self.assertTrue(ok, message)


class FixesTest(unittest.TestCase):
    def test_nested_url_keeps_full_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            site = root / "site" / "docs" / "start"
            site.mkdir(parents=True)
            url = "https://x.test/docs/start/"
            (site / "index.html").write_text(
                PAGE.format(modified="2026-01-01", canonical=url, robots=""),
                encoding="utf-8",
            )
            entries = engine.build_entries(config(include=["**/index.html"]), root)
            self.assertEqual(entries, [(url, "2026-01-01")])

    def test_include_escape_fails_closed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), {"": {}})
            (root / "evil.html").write_text("outside", encoding="utf-8")
            with self.assertRaises(engine.EngineRunError):
                engine.build_entries(config(include=["index.html", "../evil.html"]), root)

    def test_impossible_date_rejected(self):
        with self.assertRaises(engine.EngineError):
            engine.read_meta_stamp(
                '<meta property="article:modified_time" content="2026-02-31">',
                "article:modified_time",
            )

    def test_noindex_cannot_be_masked(self):
        html = (
            '<meta name="robots" content="noindex">'
            '<meta name="robots" content="index">'
        )
        self.assertFalse(engine.is_indexable(html))

    def test_write_mode_respects_umask_not_0600(self):
        import os
        import stat as _stat
        import tempfile

        old = os.umask(0o022)
        try:
            with tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d), {"": {}})
                engine.write(config(), root)
                mode = _stat.S_IMODE((root / "site" / "sitemap.xml").stat().st_mode)
                self.assertEqual(mode, 0o644)
        finally:
            os.umask(old)

    def test_uppercase_robots_noindex(self):
        self.assertFalse(engine.is_indexable('<META NAME="ROBOTS" CONTENT="NOINDEX">'))

    def test_symlink_output_refused(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), {"": {}})
            outside = root / "outside.xml"
            outside.write_text("x", encoding="utf-8")
            target = root / "site" / "sitemap.xml"
            os.symlink(outside, target)
            with self.assertRaises(engine.EngineRunError):
                engine.write(config(), root)

    def test_malformed_config_is_run_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            for bad in (
                {"include": [""]},
                {"include": ["/etc/passwd"]},
                {"lastmod": {"source": "html_meta_property", "key": 7}},
            ):
                cfgfile = Path(d) / "c.json"
                import json as _json

                cfgfile.write_text(_json.dumps(config(**bad)), encoding="utf-8")
                with self.assertRaises(engine.EngineRunError):
                    engine.load_config(cfgfile)

    def test_undecodable_page_is_run_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), {"": {}})
            (root / "site" / "bad").mkdir()
            (root / "site" / "bad" / "index.html").write_bytes(b"\xff\xfe not utf8")
            with self.assertRaises(engine.EngineRunError):
                engine.build_entries(config(), root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
