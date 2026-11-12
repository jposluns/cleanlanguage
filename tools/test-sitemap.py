#!/usr/bin/env python3
"""Tests for the sitemap engine.

This is the repository's first test file, a deliberate new idiom justified by
the engine's role as a fleet reference: the generator will be copied to other
sites, so its behaviour is pinned here rather than only checked by eye. Runs
offline with the standard library; the CI workflow invokes it after the verify
gate.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent


def _load_sibling(name: str):
    """Load tools/<name>.py by its explicit path, leaving sys.path unchanged."""
    spec = importlib.util.spec_from_file_location(name, TOOLS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The sibling modules load by explicit path, so sys.path never names the tools
# folder and no file planted there can be imported. web_metadata loads first
# under its own name, because sitemap_engine imports it by that name.
_load_sibling("web_metadata")
engine = _load_sibling("sitemap_engine")

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_GATE = TOOLS_DIR / "check-install-page.py"


# The ast classes of a type parameter, each of which binds its name; a Python older than 3.12 has none of them.
TYPE_PARAMETERS = tuple(getattr(ast, kind) for kind in ("TypeVar", "ParamSpec", "TypeVarTuple") if hasattr(ast, kind))


def bindings_anywhere(tree: ast.Module, name: str) -> tuple[list[ast.AST], list[str]]:
    """The nodes that bind, delete or annotate name anywhere in the source, in any scope, a def, class or lambda body
    included, in the order of the source, and a refusal for each * import, which can bind any name unseen."""
    bindings: list[ast.AST] = []
    refusals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
            bindings.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler,
                               ast.MatchAs, ast.MatchStar, *TYPE_PARAMETERS)) and node.name == name:
            bindings.append(node)
        elif isinstance(node, ast.arg) and node.arg == name:
            bindings.append(node)
        elif isinstance(node, ast.MatchMapping) and node.rest == name:
            bindings.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    refusals.append(f"line {node.lineno} imports *, which can bind {name} unseen")
                elif (alias.asname or alias.name.split(".")[0]) == name:
                    bindings.append(node)
    return sorted(bindings, key=lambda node: (node.lineno, node.col_offset)), refusals


def gate_families(path: Path = INSTALL_GATE) -> list[str]:
    """The families of the install gate's FAMILIES, read from its source by ast, which runs none of it, so this test
    needs no Python version that the gate needs. It does not judge scopes: it walks the whole source, every def, class
    and lambda body included, and counts each binding, deletion or annotation of the name FAMILIES in any scope: a
    plain, annotated or augmented assignment or a bare annotation, a tuple, list or starred target, a for, with or
    comprehension target, :=, a parameter, an import, del, an except name, a match capture, star or rest name, a def,
    class or type parameter name, and a type alias. It returns the families only if there is exactly 1 of them and it is
    a statement of the module of the form FAMILIES = [...] or (...) holding 1 or more strings and nothing else, and only
    if no global or nonlocal statement names FAMILIES, no attribute of FAMILIES is used, no item of FAMILIES is assigned
    or deleted, no attribute access x.FAMILIES is made, on any object x, the module included, and the source has no *
    import. So a FAMILIES local to a def or a lambda, which leaves the module's FAMILIES as it is, is refused too: that
    is the price of a reader that cannot misjudge a scope. Anything else fails with a message naming each refusal, so
    that a list that is computed, or changed in any of those ways, cannot pass unread. It cannot see a change in which
    FAMILIES is neither a target, nor the name before an attribute or item, nor the name of an attribute access.
    Examples are a change made through another name for the same list, such as fam, bound by from __main__ import
    FAMILIES as fam or by the class pattern of case object(FAMILIES=fam); through an expression that holds the list,
    such as (FAMILIES or []).append(...) or [FAMILIES][0] += [...]; through a function the list is passed to, such as
    operator.iadd() or list.append(); and through the name given as a string or keyword, such as the string that
    setattr(), exec() or globals()[...] takes or the keyword that globals().update() takes."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bindings, refusals = bindings_anywhere(tree, "FAMILIES")
    for node in ast.walk(tree):
        if isinstance(node, ast.Global) and "FAMILIES" in node.names:
            refusals.append(f"line {node.lineno} declares FAMILIES global, so the code in that scope can rebind it")
        elif isinstance(node, ast.Nonlocal) and "FAMILIES" in node.names:
            # A nonlocal FAMILIES names the FAMILIES of an enclosing def, never the module's, but this test does not
            # resolve scopes, so it refuses every nonlocal FAMILIES.
            refusals.append(f"line {node.lineno} declares FAMILIES nonlocal, and this test does not resolve which "
                            "scope's FAMILIES that names")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "FAMILIES":
            refusals.append(f"line {node.lineno} uses FAMILIES.{node.attr}, and an attribute of FAMILIES, such as "
                            "append, can change it in place")
        elif (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "FAMILIES"
              and isinstance(node.ctx, (ast.Store, ast.Del))):
            refusals.append(f"line {node.lineno} assigns or deletes an item of FAMILIES")
        elif isinstance(node, ast.Attribute) and node.attr == "FAMILIES":
            # The module's own object, reached through sys.modules[__name__] or an imported __main__, say, can rebind,
            # delete or change FAMILIES through this attribute, and the source cannot show which object is the module.
            refusals.append(f"line {node.lineno} uses an attribute named FAMILIES, which on the module's own object "
                            "can rebind, delete or change it")
    value = None
    if len(bindings) != 1:
        lines = ", ".join(str(node.lineno) for node in bindings)
        refusals.append(f"it is bound, deleted or annotated {len(bindings)} times in the source, in any scope"
                        + (f" (lines {lines})" if bindings else "") + ", not once")
    else:
        plain = [statement for statement in tree.body if isinstance(statement, ast.Assign)
                 and len(statement.targets) == 1 and statement.targets[0] is bindings[0]]
        if plain:
            try:
                value = ast.literal_eval(plain[0].value)
            except (TypeError, ValueError, SyntaxError, MemoryError, RecursionError):
                value = None
        if not (isinstance(value, (list, tuple)) and value and all(isinstance(fam, str) for fam in value)):
            refusals.append(f"its binding at line {bindings[0].lineno} is not a statement of the module of the form "
                            "FAMILIES = [...] or (...) holding 1 or more strings and nothing else")
    if refusals:
        raise AssertionError(f"tools/{path.name} has no single literal assignment FAMILIES = [...] of family names "
                             "that nothing else changes, so the families the sitemap must hold cannot be read: "
                             + "; ".join(refusals))
    return list(value)


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

    def test_committed_config_includes_family_pages(self):
        cfg = engine.load_config(REPO_ROOT / "tools" / "sitemap-config.json")
        urls = {url for url, _ in engine.build_entries(cfg, REPO_ROOT)}
        # The families come from the literal FAMILIES that gate_families() reads in the install gate, so a family added
        # to that literal must be in the sitemap too.
        for fam in gate_families():
            self.assertIn(f"{cfg['base_url']}/install/{fam}/", urls)


# The gate's binding of FAMILIES. Each mutant leaves FAMILIES unbound, binds, deletes or changes it, makes such a change
# possible, or binds or annotates a FAMILIES local to a def, a lambda or the type parameters of a def or class, which
# gate_families() refuses because it does not judge scopes, in a form that it cannot accept as the 1 literal that
# nothing else changes, whether or not that code runs; each pairs with words that the refusal must hold.
GATE_FAMILIES = 'FAMILIES = ["claude", "chatgpt", "gemini", "copilot", "other-ai"]\n'
TWICE = "bound, deleted or annotated 2 times"
ATTRIBUTE = "uses an attribute named FAMILIES"
GLOBAL = "declares FAMILIES global, so the code in that scope can rebind it"
NONLOCAL = "declares FAMILIES nonlocal, and this test does not resolve which scope's FAMILIES that names"
FAMILY_MUTANTS = (
    ("a rebinding in a module-level if", GATE_FAMILIES + 'if True:\n    FAMILIES = FAMILIES + ["sixth"]\n',
     TWICE),
    ("a rebinding in a module-level for", GATE_FAMILIES + 'for _ in range(1):\n    FAMILIES = ["sixth"]\n',
     TWICE),
    ("a rebinding in a module-level try",
     GATE_FAMILIES + 'try:\n    pass\nexcept ValueError:\n    FAMILIES = []\n', TWICE),
    ("a rebinding in a module-level with", GATE_FAMILIES + 'with open(__file__):\n    FAMILIES = ["sixth"]\n',
     TWICE),
    ("a tuple target", GATE_FAMILIES + 'FAMILIES, OTHER = ["sixth"], 1\n', TWICE),
    ("a list target", GATE_FAMILIES + '[FAMILIES] = [["sixth"]]\n', TWICE),
    ("a starred target", GATE_FAMILIES + '*FAMILIES, = ["sixth"]\n', TWICE),
    ("an augmented assignment", GATE_FAMILIES + 'FAMILIES += ["sixth"]\n', TWICE),
    ("an annotated assignment", GATE_FAMILIES + 'FAMILIES: list[str] = ["sixth"]\n', TWICE),
    ("a for target", GATE_FAMILIES + 'for FAMILIES in [["sixth"]]:\n    pass\n', TWICE),
    ("a with target", GATE_FAMILIES + 'with open(__file__) as FAMILIES:\n    pass\n', TWICE),
    ("an assignment expression", GATE_FAMILIES + 'if (FAMILIES := ["sixth"]):\n    pass\n', TWICE),
    ("an assignment expression in a default value",
     GATE_FAMILIES + 'def grow(families=(FAMILIES := ["sixth"])):\n    return families\n', TWICE),
    ("an augmented assignment in a class body", GATE_FAMILIES + 'class Grow:\n    FAMILIES += ["sixth"]\n', TWICE),
    ("a multiplying augmented assignment in a class body", GATE_FAMILIES + "class Grow:\n    FAMILIES *= 2\n",
     TWICE),
    ("an augmented assignment in a class body in a module-level if",
     GATE_FAMILIES + 'if True:\n    class Grow:\n        FAMILIES += ["sixth"]\n', TWICE),
    ("an assignment local to a def", GATE_FAMILIES + 'def grow():\n    FAMILIES = ["sixth"]\n    return FAMILIES\n',
     TWICE),
    ("an assignment expression in a lambda body", GATE_FAMILIES + 'grow = lambda: (FAMILIES := ["sixth"])\n', TWICE),
    # Each := below binds only inside its lambda when the lambda is called, so it leaves the module's FAMILIES as it is,
    # but a reader that does not judge scopes refuses it with every other binding outside the 1 literal.
    ("an assignment expression in the body of a lambda that is a default value",
     GATE_FAMILIES + "def grow(f=lambda: (FAMILIES := 1)):\n    pass\n", TWICE),
    ("an assignment expression in the body of a lambda that is a decorator",
     GATE_FAMILIES + "@(lambda f: (FAMILIES := f))\ndef grow():\n    pass\n", TWICE),
    ("a parameter of the name", GATE_FAMILIES + "def grow(FAMILIES):\n    return FAMILIES\n", TWICE),
    ("a bare annotation in a def", GATE_FAMILIES + "def grow():\n    FAMILIES: list\n", TWICE),
    ("an import as", GATE_FAMILIES + "import json as FAMILIES\n", TWICE),
    ("a from import as", GATE_FAMILIES + "from os import sep as FAMILIES\n", TWICE),
    ("a del", GATE_FAMILIES + "del FAMILIES\n", TWICE),
    ("an except name", GATE_FAMILIES + "try:\n    pass\nexcept ValueError as FAMILIES:\n    pass\n", TWICE),
    ("a match capture", GATE_FAMILIES + "match 1:\n    case FAMILIES:\n        pass\n", TWICE),
    ("a match star", GATE_FAMILIES + "match []:\n    case [*FAMILIES]:\n        pass\n", TWICE),
    ("a match rest", GATE_FAMILIES + "match {}:\n    case {**FAMILIES}:\n        pass\n", TWICE),
    ("a match as", GATE_FAMILIES + "match []:\n    case [] as FAMILIES:\n        pass\n", TWICE),
    ("a def of the name", GATE_FAMILIES + "def FAMILIES():\n    pass\n", TWICE),
    ("an async def of the name", GATE_FAMILIES + "async def FAMILIES():\n    pass\n", TWICE),
    ("a class of the name", GATE_FAMILIES + "class FAMILIES:\n    pass\n", TWICE),
    ("a dotted import of the name", GATE_FAMILIES + "import FAMILIES.path\n", TWICE),
    ("an append", GATE_FAMILIES + 'FAMILIES.append("sixth")\n', "uses FAMILIES.append"),
    ("an extend inside a def", GATE_FAMILIES + 'def grow():\n    FAMILIES.extend(["sixth"])\n',
     "uses FAMILIES.extend"),
    ("an item assignment", GATE_FAMILIES + 'FAMILIES[0] = "sixth"\n', "assigns or deletes an item"),
    ("an item deletion", GATE_FAMILIES + "del FAMILIES[0]\n", "assigns or deletes an item"),
    ("a global rebinding inside a def", GATE_FAMILIES + 'def grow():\n    global FAMILIES\n    FAMILIES = ["sixth"]\n',
     GLOBAL),
    ("a global rebinding in a class body",
     GATE_FAMILIES + 'class Grow:\n    global FAMILIES\n    FAMILIES = ["sixth"]\n', GLOBAL),
    ("a nonlocal in a def nested in a def",
     GATE_FAMILIES + 'def outer():\n    FAMILIES = []\n\n    def grow():\n        nonlocal FAMILIES\n'
     '        FAMILIES = ["sixth"]\n', NONLOCAL),
    ("a * import", GATE_FAMILIES + "from os.path import *\n", "imports *"),
    ("an attribute assignment through sys.modules",
     GATE_FAMILIES + 'import sys\nsys.modules[__name__].FAMILIES = FAMILIES + ["sixth"]\n', ATTRIBUTE),
    ("an attribute assignment through an imported __main__",
     GATE_FAMILIES + 'import __main__ as _m\n_m.FAMILIES = ["sixth"]\n', ATTRIBUTE),
    ("an attribute deletion", GATE_FAMILIES + "import __main__\ndel __main__.FAMILIES\n", ATTRIBUTE),
    ("an append through an attribute", GATE_FAMILIES + 'import __main__\n__main__.FAMILIES.append("sixth")\n',
     ATTRIBUTE),
    ("a chained assignment", 'FAMILIES = OTHER = ["claude"]\n', "is not a statement of the module"),
    ("a computed value", 'FAMILIES = sorted(["claude"])\n', "is not a statement of the module"),
    ("an empty list", "FAMILIES = []\n", "or (...) holding 1 or more strings and nothing else"),
    ("a member that is not a string", 'FAMILIES = ["claude", 1]\n', "is not a statement of the module"),
    ("the only binding inside a module-level if", 'if True:\n    FAMILIES = ["claude"]\n',
     "is not a statement of the module"),
    ("no binding", 'OTHER = ["claude"]\n', "bound, deleted or annotated 0 times"),
)
# These mutants use the type parameters and the type alias of Python 3.12 and later, which an older Python cannot parse,
# so test_each_typing_mutant_fails_closed skips them there.
TYPING_MUTANTS = (
    ("a type parameter of a def", GATE_FAMILIES + "def grow[FAMILIES]():\n    pass\n", TWICE),
    ("a type parameter of a class", GATE_FAMILIES + "class Grow[FAMILIES]:\n    pass\n", TWICE),
    ("a parameter specification of a def", GATE_FAMILIES + "def grow[**FAMILIES]():\n    pass\n", TWICE),
    ("a type variable tuple of a class", GATE_FAMILIES + "class Grow[*FAMILIES]:\n    pass\n", TWICE),
    ("a type alias", GATE_FAMILIES + "type FAMILIES = list[str]\n", TWICE),
)


class GateFamiliesTest(unittest.TestCase):
    def read(self, source: str) -> list[str]:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            gate = Path(d) / "check-install-page.py"
            gate.write_text(source, encoding="utf-8")
            return gate_families(gate)

    def test_committed_gate_gives_its_5_families(self):
        self.assertEqual(gate_families(), ["claude", "chatgpt", "gemini", "copilot", "other-ai"])

    def test_single_literal_list_or_tuple_is_read(self):
        self.assertEqual(self.read(GATE_FAMILIES), ["claude", "chatgpt", "gemini", "copilot", "other-ai"])
        self.assertEqual(self.read('FAMILIES = ("claude", "gemini")\n'), ["claude", "gemini"])

    def assert_each_fails_closed(self, mutants):
        for label, source, words in mutants:
            with self.subTest(label):
                with self.assertRaises(AssertionError) as caught:
                    self.read(source)
                self.assertIn("has no single literal assignment FAMILIES = [...] of family names that nothing else "
                              "changes", str(caught.exception))
                self.assertIn(words, str(caught.exception))

    def test_each_mutant_fails_closed(self):
        self.assert_each_fails_closed(FAMILY_MUTANTS)

    @unittest.skipIf(sys.version_info < (3, 12), "type parameters and type aliases parse only on Python 3.12 or later")
    def test_each_typing_mutant_fails_closed(self):
        self.assert_each_fails_closed(TYPING_MUTANTS)


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


class ConfigOutputAndUrlTest(unittest.TestCase):
    def test_config_bad_bytes_is_run_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.json"
            cfg.write_bytes(b"\xff\xfe{")
            with self.assertRaises(engine.EngineRunError):
                engine.load_config(cfg)

    def test_output_directory_refused(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), {"": {}})
            (root / "adir").mkdir()
            with self.assertRaises(engine.EngineRunError):
                engine.write(config(output="adir"), root)

    def test_url_segments_are_encoded(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            page_dir = root / "site" / "a#b"
            page_dir.mkdir(parents=True)
            url = "https://x.test/a%23b/"
            (page_dir / "index.html").write_text(
                PAGE.format(modified="2026-01-01", canonical=url, robots=""),
                encoding="utf-8",
            )
            entries = engine.build_entries(config(include=["**/index.html"]), root)
            self.assertEqual(entries, [(url, "2026-01-01")])

    def test_base_url_whitespace_rejected(self):
        import json as _json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.json"
            cfg.write_text(_json.dumps(config(base_url="https://x test")), encoding="utf-8")
            with self.assertRaises(engine.EngineRunError):
                engine.load_config(cfg)



class SharedParserTest(unittest.TestCase):
    """The engine now parses meta and link tags through web_metadata, so it reads
    single-quoted, unquoted, and quoted-> attributes, ignores commented tags, and
    ignores metadata inside inert containers."""

    STAMP = "article:modified_time"

    def _repo_with_head(self, tmp: Path, head: str) -> Path:
        site = tmp / "site"
        site.mkdir(parents=True, exist_ok=True)
        (site / "index.html").write_text(
            "<!doctype html><html><head>" + head + "</head><body></body></html>",
            encoding="utf-8",
        )
        return tmp

    def test_robots_noindex_inside_template_is_ignored(self):
        self.assertTrue(engine.is_indexable(
            '<template><meta name="robots" content="noindex"></template>'))

    def test_single_quoted_stamp_is_read(self):
        self.assertEqual(
            engine.read_meta_stamp(
                "<meta property='article:modified_time' content='2026-01-01'>", self.STAMP),
            "2026-01-01")

    def test_multi_token_mixed_case_canonical_is_recognized(self):
        self.assertEqual(
            engine.canonical_href('<link rel="Canonical alternate" href="https://x.test/">'),
            "https://x.test/")

    def test_template_wrapped_duplicate_stamp_is_not_a_duplicate(self):
        self.assertEqual(
            engine.read_meta_stamp(
                '<meta property="article:modified_time" content="2026-01-01">'
                '<template><meta property="article:modified_time" content="2020-01-01"></template>',
                self.STAMP),
            "2026-01-01")

    def test_commented_stamp_is_not_a_duplicate(self):
        self.assertEqual(
            engine.read_meta_stamp(
                '<meta property="article:modified_time" content="2026-01-01">'
                '<!-- <meta property="article:modified_time" content="2020-01-01"> -->',
                self.STAMP),
            "2026-01-01")

    def test_quoted_gt_in_unrelated_attribute_does_not_truncate(self):
        self.assertEqual(
            engine.read_meta_stamp(
                '<meta data-x="a>b" property="article:modified_time" content="2026-01-01">',
                self.STAMP),
            "2026-01-01")

    def test_template_canonical_before_active_builds_cleanly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = self._repo_with_head(
                Path(d),
                '<meta property="article:modified_time" content="2026-01-01">'
                '<template><link rel="canonical" href="https://x.test/wrong/"></template>'
                '<link rel="canonical" href="https://x.test/">')
            entries = engine.build_entries(config(include=["index.html"], exclude=[]), root)
            self.assertEqual([url for url, _ in entries], ["https://x.test/"])

    def test_single_quoted_canonical_mismatch_is_caught(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = self._repo_with_head(
                Path(d),
                '<meta property="article:modified_time" content="2026-01-01">'
                "<link rel='canonical' href='https://x.test/wrong/'>")
            with self.assertRaises(engine.EngineError):
                engine.build_entries(config(include=["index.html"], exclude=[]), root)

    def test_contradicting_canonical_is_caught(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = self._repo_with_head(
                Path(d),
                '<meta property="article:modified_time" content="2026-01-01">'
                '<link rel="canonical alternate" href="https://x.test/">'
                '<link rel="canonical" href="https://x.test/wrong/">')
            with self.assertRaises(engine.EngineError):
                engine.build_entries(config(include=["index.html"], exclude=[]), root)

    def test_nbsp_rel_is_not_a_canonical_token(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # A non-breaking space is not an HTML rel separator, so this is one
            # non-canonical token and must be ignored (no false mismatch).
            root = self._repo_with_head(
                Path(d),
                '<meta property="article:modified_time" content="2026-01-01">'
                '<link rel="canonical\u00a0alternate" href="https://x.test/wrong/">')
            entries = engine.build_entries(config(include=["index.html"], exclude=[]), root)
            self.assertEqual([u for u, _ in entries], ["https://x.test/"])

    def test_malformed_port_base_url_is_run_error(self):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            cfgfile = Path(d) / "c.json"
            cfgfile.write_text(_json.dumps(config(base_url="https://x.test:99999x")),
                               encoding="utf-8")
            with self.assertRaises(engine.EngineRunError):
                engine.load_config(cfgfile)


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
    """tools/generate-sitemap.py, run with tools/sitemap_engine.py failing to
    load in each way load_faults() gives, exits 3 with its own refusal naming
    that file, and never runs a cached file in its place."""

    def test_each_load_failure_is_refused(self):
        for name, fault, words in load_faults("def verify(", "def verify_unused(", "verify"):
            with self.subTest(name), tempfile.TemporaryDirectory() as scratch:
                tools = Path(scratch) / "tools"
                tools.mkdir()
                for file in ("generate-sitemap.py", "web_metadata.py", "sitemap_engine.py"):
                    shutil.copyfile(Path(__file__).resolve().parent / file, tools / file)
                fault(tools / "sitemap_engine.py")
                result = subprocess.run([sys.executable, "-I", str(tools / "generate-sitemap.py")],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 3, result.stderr[-300:])
                self.assertIn(f"generate-sitemap: tools/sitemap_engine.py {words}", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
