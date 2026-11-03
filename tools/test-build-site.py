#!/usr/bin/env python3
"""Tests for tools/build-site.py: each refusal fires on a deliberate fault.

Every case copies the generator's inputs into a temporary folder (under
$TMPDIR), applies 1 fault, runs the generator there as a separate process and
asserts its exit code, and for the passing cases, what the output contains.
The first case runs ``--check`` on this repository. Exit 0 when every case
passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "tools" / "build-site.py"
INPUTS = [
    "site-src",
    "cleanlanguage/skills/cleanlanguage/SKILL.md",
    "cleanlanguage/skills/cleanlanguage/references",
    "site/downloads",
    "site/draft/assets/baseline",
    ".baseline/pin.toml",
    "tools/sitemap-config.json",
]


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    for relative in INPUTS:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)
    return root


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(GENERATOR), "--root", str(root), *args],
        capture_output=True,
        text=True,
    )


def edit(root: Path, relative: str, old: str, new: str, count: int = 1) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if text.count(old) < 1:
        raise AssertionError(f"{old!r} not in {relative}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")


PAGE = "site-src/pages/demo.html"
ANCHOR = "<p>This pair preserves every fact; only the style changes.</p>"


def inject(snippet: str):
    return lambda root: edit(root, PAGE, ANCHOR, ANCHOR + snippet)


def set_release(root: Path, **changes: str) -> None:
    path = root / "site-src" / "release.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


REFUSALS = [
    ("an en dash", inject("<p>pages 1\u20132</p>")),
    ("an em dash", inject("<p>a pause\u2014here</p>")),
    ("an inline style attribute", inject('<p style="color: red">x</p>')),
    ("a style element", inject("<style>p { color: red; }</style>")),
    ("an inline script", inject("<script>alert(1)</script>")),
    ("a module script", inject('<script type="module">alert(1)</script>')),
    ("an on* handler", inject('<p onclick="x()">x</p>')),
    ("what this is framing", inject("<p>What this is not: a filter.</p>")),
    ("a second h1", inject("<h1>Another</h1>")),
    ("a duplicate id", inject('<p id="watch">again</p>')),
    ("an unknown token", inject("<p>{{nonsense}}</p>")),
    ("a malformed token", inject("<p>{{ base }}</p>")),
    ("a root link outside the base", inject('<p><a href="/install/">live page</a></p>')),
    ("a root asset outside the base", inject('<img src="/favicon.svg" alt="">')),
    ("a relative link", inject('<p><a href="install/">relative</a></p>')),
    ("an external link without target", inject('<p><a href="https://example.org/">x<span class="vh"> (opens in a new tab)</span></a></p>')),
    ("an external link without the new-tab text", inject('<p><a href="https://example.org/" target="_blank" rel="noopener noreferrer">x</a></p>')),
    ("an external image", inject('<img src="https://example.org/x.png" alt="">')),
    ("a JSON-LD block on a draft page", inject('<script type="application/ld+json">{}</script>')),
    ("an in-page link with no target", inject('<p><a href="#nowhere">x</a></p>')),
    ("a link to a page that is not generated", inject('<p><a href="{{base}}nope/">x</a></p>')),
    ("a link to an anchor the target lacks", inject('<p><a href="{{base}}install/#nowhere">x</a></p>')),
    ("an allowlisted root link to a missing file", lambda root: (
        edit(root, "site-src/site.json", '"/downloads/cleanlanguage-8k.md"', '"/downloads/cleanlanguage-8k.md", "/downloads/gone.md"'),
        inject('<p><a href="/downloads/gone.md">x</a></p>')(root),
    )),
    ("release.json disagrees with SKILL.md", lambda root: set_release(root, version="1.0.99", tag="v1.0.99")),
    ("release.json tag is not v<version>", lambda root: set_release(root, tag="1.0.14")),
    ("release.json checksum is malformed", lambda root: set_release(root, checksum="abc")),
    ("unsupported Markdown in examples.md", lambda root: edit(
        root, "cleanlanguage/skills/cleanlanguage/references/examples.md",
        "The vendor contract expires on 31 March.", "The **vendor** contract expires on 31 March.")),
    ("commentary for a section examples.md lacks", lambda root: edit(
        root, "site-src/examples-commentary.json", '"Incident status":', '"Incident report":')),
    ("a Preferred block with no example before it", lambda root: edit(
        root, "cleanlanguage/skills/cleanlanguage/references/examples.md", "### Weak\n\nThe team has been", "### Preferred\n\nThe team has been")),
    ("the sitemap config no longer excludes the draft home page", lambda root: edit(
        root, "tools/sitemap-config.json", ', "draft/index.html"', "")),
    ("an extra closing div (the reference demo's defect)", lambda root: edit(
        root, PAGE, "untested recovery path.</p></div></div>", "untested recovery path.</p></div></div></div>")),
    ("an unclosed div", inject('<div class="callout"><p>x</p>')),
    ("content after .doc closes", lambda root: edit(
        root, PAGE, "</a></div></div>\n", "</a></div></div>\n<p>after the document</p>\n")),
    ("code-tag text inside the prompt (the reference demo's defect)", lambda root: edit(
        root, PAGE, "hidden>Copy</button>First, read", "hidden>Copy</button>&lt;code id=&quot;demo-prompt&quot;&gt;First, read")),
    ("a static aria-current=true mark", inject('<p><a href="#watch" aria-current="true">x</a></p>')),
    ("an inner page linking the Licence page", inject('<p><a href="{{base}}license/">x</a></p>')),
    ("an inner page linking the Disclosure page", inject('<p><a href="{{base}}disclosure/#d-1">x</a></p>')),
    ("a baseline asset the pin does not list", inject('<img src="{{base}}assets/baseline/logos/missing.svg" alt="">')),
    ("a checklist group that is not 1 bullet list", lambda root: edit(
        root, "cleanlanguage/skills/cleanlanguage/references/qa-checklist.md", "## Tone\n\n", "## Tone\n\nA paragraph.\n\n")),
    ("a list rail with fewer than 2 sections", lambda root: edit(
        root, "site-src/site.json", '"source": "404.html", ', '"source": "404.html", "rail": "list", ')),
]


def check_refusals(failures: list[str]) -> int:
    ran = 0
    for name, fault in REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            fault(root)
            result = run(root, "--out", str(Path(scratch) / "out"))
            ran += 1
            if result.returncode != 1:
                failures.append(f"refusal '{name}': exit {result.returncode}, expected 1 ({result.stderr.strip()[:200]})")
    return ran


def check_clean_build(failures: list[str]) -> int:
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"clean build: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        pages = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html"))
        if len(pages) != 13:
            failures.append(f"clean build: {len(pages)} pages, expected 13: {pages}")
        for page in pages:
            text = (out / page).read_text(encoding="utf-8")
            if '<link rel="apple-touch-icon" href="/draft/assets/baseline/logos/cleanlanguage-touch.png">' not in text:
                failures.append(f"clean build: {page} lacks the touch icon")
            list_rail = '<nav class="rail" aria-label="On this page">' in text
            if list_rail != ('assets/baseline/rail.js?v=' in text):
                failures.append(f"clean build: {page} loads rail.js {'without' if not list_rail else 'not on'} a list rail")
            if "aria-current=" in text.split('<nav class="rail"', 1)[-1].split("</nav>", 1)[0] and list_rail:
                failures.append(f"clean build: {page} marks a rail link in the markup")
            if text.count('<meta name="robots" content="noindex, nofollow">') != 1:
                failures.append(f"clean build: {page} lacks the noindex meta")
            if "application/ld+json" in text or 'rel="canonical"' in text:
                failures.append(f"clean build: {page} carries publish metadata in the draft")
            for value in re.findall(r'(?:href|src)="(/[^"]*)"', text):
                if not value.startswith("/draft/") and not value.startswith("/downloads/"):
                    failures.append(f"clean build: {page} links {value} outside /draft/")
        examples_md = (root / "cleanlanguage/skills/cleanlanguage/references/examples.md").read_text(encoding="utf-8")
        examples = (out / "examples/index.html").read_text(encoding="utf-8")
        sections = re.findall(r"^## (.+)$", examples_md, re.M)
        if examples.count('<p class="lbl sec">Example ') != len(sections):
            failures.append("clean build: the examples page does not show every section of examples.md")
        for paragraph in re.findall(r"^### .+\n\n(.+)$", examples_md, re.M):
            rendered = html.escape(paragraph, quote=False)
            rendered = re.sub(r"`([^`]*)`", r"<code>\1</code>", rendered)
            if rendered not in examples:
                failures.append(f"clean build: example text missing: {paragraph[:60]!r}")
        instructions = (out / "instructions/index.html").read_text(encoding="utf-8")
        source = (root / "site/downloads/cleanlanguage.md").read_text(encoding="utf-8").rstrip("\n")
        match = re.search(r'<pre id="instructions-text" class="hascopy prompt-flow"><button class="copy" type="button" data-copy="instructions-text" hidden>Copy</button>(.*?)</pre>', instructions, re.S)
        if match is None or html.unescape(match.group(1)) != source:
            failures.append("clean build: the instructions page does not embed cleanlanguage.md exactly")
    return 1


def check_release_flip(failures: list[str]) -> int:
    """Every version string on the install and verify pages follows release.json (the known version-text issue)."""
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        skill = root / "cleanlanguage/skills/cleanlanguage/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(re.sub(r"^Version: [0-9.]+", "Version: 9.8.7", text, count=1, flags=re.M), encoding="utf-8")
        set_release(root, version="9.8.7", tag="v9.8.7", checksum="a" * 64)
        out = Path(scratch) / "out"
        result = run(root, "--out", str(out))
        if result.returncode != 0:
            failures.append(f"release flip: exit {result.returncode}: {result.stderr.strip()}")
            return 1
        for page in ("install/index.html", "verify/index.html"):
            body = (out / page).read_text(encoding="utf-8")
            stale = sorted(set(re.findall(r"cleanlanguage-([0-9][0-9.]*[0-9])\.zip|version ([0-9]+\.[0-9]+\.[0-9]+)", body)))
            names = {v for pair in stale for v in pair if v}
            if names != {"9.8.7"}:
                failures.append(f"release flip: {page} names versions {sorted(names)}, expected only 9.8.7")
        verify = (out / "verify/index.html").read_text(encoding="utf-8")
        for needed in ("published checksum for version 9.8.7 is", 'id="published-checksum">' + "a" * 64, "releases/download/v9.8.7/cleanlanguage-9.8.7.zip.sha256",
                       "Get-FileHash cleanlanguage-9.8.7.zip", "shasum -a 256 cleanlanguage-9.8.7.zip", "sha256sum cleanlanguage-9.8.7.zip"):
            if needed not in verify:
                failures.append(f"release flip: verify page lacks {needed!r}")
        install = (out / "install/index.html").read_text(encoding="utf-8")
        for needed in ("zip, version 9.8.7", "for example <code>cleanlanguage-9.8.7.zip</code>"):
            if needed not in install:
                failures.append(f"release flip: install page lacks {needed!r}")
    return 1


def check_check_mode(failures: list[str]) -> int:
    ran = 0
    for name, fault in (
        ("a changed output byte", lambda d: (d / "verify/index.html").write_text((d / "verify/index.html").read_text(encoding="utf-8") + " ", encoding="utf-8")),
        ("an extra output file", lambda d: (d / "stale.html").write_text("x", encoding="utf-8")),
        ("a missing output file", lambda d: (d / "demo/index.html").unlink()),
    ):
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if run(root).returncode != 0 or run(root, "--check").returncode != 0:
                failures.append(f"check mode '{name}': the clean tree did not build and check")
                continue
            fault(root / "site" / "draft")
            code = run(root, "--check").returncode
            ran += 1
            if code != 1:
                failures.append(f"check mode '{name}': exit {code}, expected 1")
    return ran


def check_promotion_build(failures: list[str]) -> int:
    with tempfile.TemporaryDirectory() as scratch:
        root = make_root(Path(scratch))
        edit(root, "tools/sitemap-config.json", ', "draft/index.html"', "")
        result = run(root, "--base", "/", "--out", str(Path(scratch) / "x"))
        if result.returncode != 1 or "--date" not in result.stderr:
            failures.append("promotion build: ran without --date")
        result = run(root, "--base", "/", "--date", "2026-11-03")
        if result.returncode != 1 or "--promote" not in result.stderr:
            failures.append("promotion build: wrote into site/ without --promote")
        out = Path(scratch) / "root"
        result = run(root, "--base", "/", "--out", str(out), "--date", "2026-11-03")
        if result.returncode != 0:
            failures.append(f"promotion build: exit {result.returncode}: {result.stderr.strip()}")
            return 3
        home = (out / "index.html").read_text(encoding="utf-8")
        for needed in ('<link rel="canonical" href="https://cleanlanguage.ai/">', '<link rel="apple-touch-icon" href="/assets/baseline/logos/cleanlanguage-touch.png">', '<meta name="author" content="Jeff Posluns">',
                       '<meta property="article:modified_time" content="2026-11-03">', '"@type": "Person"', 'href="/install/"'):
            if needed not in home:
                failures.append(f"promotion build: the home page lacks {needed!r}")
        if "noindex" in home or "/draft/" in home:
            failures.append("promotion build: the home page still carries draft paths or noindex")
        missing = (out / "404.html").read_text(encoding="utf-8")
        if '<meta name="robots" content="noindex, nofollow">' not in missing or "application/ld+json" in missing:
            failures.append("promotion build: the 404 page must stay noindex without publish metadata")
    return 3


def main() -> int:
    failures: list[str] = []
    ran = 0
    code = subprocess.run([sys.executable, "-I", str(GENERATOR), "--check"], capture_output=True, text=True).returncode
    ran += 1
    if code != 0:
        failures.append(f"this repository: --check exit {code}, expected 0")
    ran += check_refusals(failures)
    ran += check_clean_build(failures)
    ran += check_release_flip(failures)
    ran += check_check_mode(failures)
    ran += check_promotion_build(failures)
    if failures:
        print("test-build-site: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-build-site: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
