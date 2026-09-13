#!/usr/bin/env python3
"""Check that every content page carries accurate author and date metadata.

The site declares an author and two dates per page, so a crawler and a reader
can both see who wrote a page and when it last changed. Hand-maintained dates
rot silently: a page gets edited, the stamped date stays where it was, and the
page then asserts something false. This gate makes that rot fail loudly.

What it verifies, per page
--------------------------

1. The required tags are present: ``author``, ``article:published_time``,
   ``article:modified_time``, and ``article:author``.
2. Both dates are ``YYYY-MM-DD``.
3. ``article:modified_time`` is not older than the file's last commit date.
   This is the rot check: if a page changed after the date it claims, the claim
   is false. The comparison is one-sided on purpose, so a stamp made in a
   working tree before the commit lands does not fail spuriously.
4. ``article:published_time`` matches the date the file was added to the
   repository, so a publish date cannot be invented. ``PUBLISHED_OVERRIDES``
   records the deliberate exceptions, of which there are currently none.
5. ``article:modified_time`` is not in the future.
6. Every page's primary content entity (an Article and its siblings, a
   CreativeWork, or a WebPage) carries an ``author`` in which every author is a
   Person object whose name is the meta author, so a stray co-author fails. A
   secondary entity (a Comment, a Review, an FAQPage, or a typeless object) is
   exempt. The gate reads top-level JSON-LD objects and the members of a
   top-level array, skipping HTML comments; it does not descend into an
   ``@graph`` container, so a page whose only author sits inside an ``@graph``
   fails loudly rather than passing. An author name may be a string or a value
   object (``@value``); JSON-LD dates are not cross-checked here, since the
   meta-versus-git checks above already guard date rot.
7. Every page names the same author, so one page cannot drift from the rest.
8. Each ``og:image`` and ``twitter:image`` URL on the site's own origin resolves
   to a file that exists. These URLs are absolute, because a crawler needs them
   to be, which puts them outside the relative-link scope of check-links.py, so
   a card pointing at a missing file would otherwise ship unnoticed.
The sitemap is no longer checked here. ``tools/generate-sitemap.py`` regenerates
``site/sitemap.xml`` from these same pages, driven by the same
``tools/sitemap-config.json``, and verifies it byte for byte, which subsumes and
strengthens the per-page listing and ``lastmod`` comparison this gate used to make.

What it does not verify
-----------------------

It proves the dates are internally consistent and consistent with git history,
and that the referenced card files exist. It does not prove any particular
crawler reads or displays any of it. It says nothing about whether the prose on
a page is current, only about when the file changed, and nothing about whether an
image's contents are correct, only that the file is there.

``site/404.html`` is out of scope: it is ``noindex`` and carries no social or
authorship metadata by design.

Git history is required. A shallow clone cannot answer when a file was added, so
this exits 3 rather than passing, on the principle that an unanswerable check is
never a pass. In CI that means ``actions/checkout`` needs ``fetch-depth: 0``.

Exit codes:
  0  every page passed
  1  at least one page has a problem
  3  the check could not run: no git history, or a page could not be read
"""

from __future__ import annotations

import datetime as dt
import html.parser
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = REPO_ROOT / "site"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sitemap_engine as engine  # noqa: E402

SITEMAP_CONFIG = REPO_ROOT / "tools" / "sitemap-config.json"

# Pages whose publish date cannot come from git history, with the reason. A page
# that was deleted and re-added, or moved in from elsewhere, belongs here rather
# than being handled by weakening the check.
PUBLISHED_OVERRIDES: dict[str, str] = {}

# Match the ld+json script tag tolerant of attribute order and quote style, and
# strip HTML comments before scanning so a commented-out block cannot satisfy
# the author requirement.
class _LDJSONScripts(html.parser.HTMLParser):
    """Collect the text of ``<script type="application/ld+json">`` elements.

    Parsing the markup, rather than matching a regex over raw HTML, matches the
    ``type`` attribute exactly (never a ``data-type`` suffix), handles attribute
    order and quoting, does not end a tag on a quoted ``>``, and never collects a
    commented-out block, all without altering the JSON text (a global comment
    strip would corrupt a JSON string that contains the comment delimiters).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._collecting = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            # HTML tokenization keeps the first of a repeated attribute, so a
            # later duplicate never changes the effective type.
            values: dict[str, str] = {}
            for name, value in attrs:
                values.setdefault(name.lower(), value or "")
            self._collecting = (
                values.get("type", "").strip(" \t\n\f\r").lower() == "application/ld+json"
            )
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._collecting:
            self.blocks.append("".join(self._buf))
            self._collecting = False
            self._buf = []

    def handle_startendtag(self, tag, attrs):
        # HTML does not honour a self-closing flag on the non-void <script>
        # element: a browser's parser treats <script .../> as an opening tag
        # whose content follows. Mirror that so a mis-serialized block is
        # collected and checked, not silently dropped.
        if tag == "script":
            self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self._collecting:
            self._buf.append(data)

    def close(self) -> None:
        # An unclosed <script> at end of input still holds buffered content; flush
        # it so a missing </script> cannot drop (and thus hide) a block.
        super().close()
        if self._collecting and self._buf:
            self.blocks.append("".join(self._buf))
            self._collecting = False
            self._buf = []


def ld_json_blocks(text: str) -> list[str]:
    """The text content of every ld+json script block in ``text``."""
    parser = _LDJSONScripts()
    parser.feed(text)
    parser.close()
    return parser.blocks


class _MetaTags(html.parser.HTMLParser):
    """Collect the attributes of every ``<meta>`` element.

    Parsing the markup, rather than matching a regex over raw HTML, does not
    end a tag on a ``>`` inside a quoted value, accepts single-quoted,
    double-quoted, and unquoted attribute values, lowercases attribute names,
    treats a self-closing ``<meta/>`` as the void element a browser sees, and
    never collects a ``<meta>`` written inside an HTML comment. Attributes
    are kept tag by tag, because a tag may set both name and property on one
    element (LinkedIn's documented form) and must appear under both.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.tags: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        # HTML tokenization keeps the first of a repeated attribute,
        # matching _LDJSONScripts above.
        values: dict[str, str] = {}
        for name, value in attrs:
            values.setdefault(name.lower(), value or "")
        self.tags.append(values)

    def handle_startendtag(self, tag, attrs):
        # <meta> is a void element: a browser treats <meta .../> exactly as
        # <meta ...>, so collect it the same way.
        self.handle_starttag(tag, attrs)


def meta_tags(text: str) -> list[dict[str, str]]:
    """The attribute dict of every ``<meta>`` element in ``text``."""
    parser = _MetaTags()
    parser.feed(text)
    parser.close()
    return parser.tags


def _reject_json_constant(token: str) -> None:
    """Reject the constants ``json.loads`` accepts but strict JSON forbids.

    NaN and Infinity parse by default, so a block that carries them would read
    as well formed here yet be rejected by a strict consumer. Treat them as a
    parse failure, like any other malformed block.
    """
    raise ValueError(f"non-standard JSON constant {token}")


# The JSON-LD @type values that mark a page's primary content entity, whose
# author must name the meta author. Secondary entities (a Comment, a Review, an
# FAQPage, or a typeless object) are exempt. CreativeWork covers the landing
# page; Article and its siblings cover the rest.
PRIMARY_TYPES = frozenset({
    "Article", "NewsArticle", "TechArticle", "BlogPosting", "ScholarlyArticle",
    "Report", "CreativeWork", "WebPage",
})
# The schema.org author @type the gate accepts. A matching name carried on any
# other type (for example PostalAddress) does not satisfy the requirement.
AUTHOR_TYPES = frozenset({"Person"})


def _ld_types(obj: dict) -> set:
    """The set of @type values on ``obj`` (a string, or a list of strings)."""
    value = obj.get("@type")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {t for t in value if isinstance(t, str)}
    return set()


def _author_ok(author: object, meta_author: str) -> bool:
    """True when there is at least one author entry and EVERY entry is an
    accepted author-type object whose ``name`` is ``meta_author``. A stray or
    stale co-author, a non-Person author, or a bare-string author fails; a name
    may be a string or a value object ``{"@value": "..."}``. This enforces the
    site's single-author convention."""
    items = [item for item in (author if isinstance(author, list) else [author])
             if item is not None]
    if not items:
        return False
    for item in items:
        if not isinstance(item, dict) or not (_ld_types(item) & AUTHOR_TYPES):
            return False
        name = item.get("name")
        if isinstance(name, dict):
            name = name.get("@value")
        if not (isinstance(name, str) and name.strip() == meta_author):
            return False
    return True
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_PROPERTIES = ("article:published_time", "article:modified_time", "article:author")

# The site's own origin. Image URLs are written absolute, because a crawler needs
# an absolute URL, which puts them outside check-links.py's relative-link scope.
# A card URL pointing at a file that does not exist would otherwise ship
# unnoticed, so the image references are resolved back to files here.
SITE_ORIGIN = "https://cleanlanguage.ai"
IMAGE_REFERENCES = ("og:image", "twitter:image")



def die(message: str) -> None:
    print(f"check-page-metadata: {message}", file=sys.stderr)
    raise SystemExit(3)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        die(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def require_full_history() -> None:
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        die(
            "the repository is a shallow clone, so file history cannot be read. "
            "Unshallow it, or set fetch-depth: 0 on actions/checkout."
        )


def added_date(relative: str) -> str | None:
    """The date the path was added, or None if history does not record it."""
    lines = git("log", "--diff-filter=A", "--format=%cs", "--", relative).split()
    return lines[-1] if lines else None


def last_change_date(relative: str) -> str | None:
    lines = git("log", "-1", "--format=%cs", "--", relative).split()
    return lines[0] if lines else None


def content_pages() -> list[Path]:
    """The content pages, enumerated by the shared engine so this gate and the
    sitemap generator start from the same set. A bad shared config makes this
    gate exit 3, matching its own could-not-run contract, rather than crashing."""
    try:
        config = engine.load_config(SITEMAP_CONFIG)
        return engine.enumerate_pages(SITE_ROOT, config["include"], config["exclude"])
    except engine.EngineError as error:
        die(str(error))


def check_page(path: Path, today: str) -> tuple[list[str], str | None]:
    """Return the problems found on one page, and the author it names."""
    relative = path.relative_to(REPO_ROOT).as_posix()
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        die(f"could not read {relative}: {error}")

    names: dict[str, str] = {}
    properties: dict[str, str] = {}
    for attributes in meta_tags(text):
        content = attributes.get("content")
        if content is None:
            continue
        if "name" in attributes:
            names[attributes["name"]] = content
        if "property" in attributes:
            properties[attributes["property"]] = content

    author = names.get("author")
    if not author:
        problems.append('missing <meta name="author">')

    for prop in REQUIRED_PROPERTIES:
        if prop not in properties:
            problems.append(f"missing {prop}")

    published = properties.get("article:published_time")
    modified = properties.get("article:modified_time")

    for label, value in (("article:published_time", published), ("article:modified_time", modified)):
        if value is not None and not ISO_DATE.match(value):
            problems.append(f"{label} is {value!r}, expected YYYY-MM-DD")

    added = added_date(relative)
    changed = last_change_date(relative)
    if changed is None:
        problems.append("git records no commit for this file, so its dates cannot be checked")

    if modified and ISO_DATE.match(modified):
        if changed and changed > modified:
            problems.append(
                f"article:modified_time is {modified} but the file last changed {changed}; "
                f"update the stamp to {changed} or later"
            )
        if modified > today:
            problems.append(f"article:modified_time {modified} is in the future (today is {today})")

    if published and ISO_DATE.match(published):
        override = PUBLISHED_OVERRIDES.get(relative)
        if override is None and added and published != added:
            problems.append(
                f"article:published_time is {published} but git shows the file was added "
                f"{added}; correct the stamp, or record the exception in PUBLISHED_OVERRIDES"
            )

    site_root = SITE_ROOT.resolve()
    for reference in IMAGE_REFERENCES:
        url = properties.get(reference) or names.get(reference)
        if url and url.startswith(SITE_ORIGIN):
            target = (SITE_ROOT / url[len(SITE_ORIGIN) :].lstrip("/")).resolve()
            if not target.is_relative_to(site_root):
                problems.append(
                    f"{reference} points at {url}, which resolves outside "
                    f"the site directory"
                )
            elif not target.is_file():
                problems.append(
                    f"{reference} points at {url}, but "
                    f"{target.relative_to(REPO_ROOT)} does not exist"
                )

    ld_author_ok = False
    ld_author_problem = False
    for raw in ld_json_blocks(text):
        try:
            parsed = json.loads(raw, parse_constant=_reject_json_constant)
        except (ValueError, RecursionError) as error:
            problems.append(f"JSON-LD does not parse: {error}")
            ld_author_problem = True
            continue
        for data in (parsed if isinstance(parsed, list) else [parsed]):
            if not isinstance(data, dict) or not (_ld_types(data) & PRIMARY_TYPES):
                # Only a primary content entity (Article, CreativeWork, ...) must
                # carry the author. A secondary entity (Comment, Review, FAQPage,
                # or a typeless object) is exempt, so a multi-entity page is
                # neither false-failed nor able to satisfy the requirement from a
                # secondary object. Date agreement is left to the meta-vs-git
                # checks above.
                continue
            if author is not None and _author_ok(data.get("author"), author):
                ld_author_ok = True
            else:
                problems.append(
                    "a primary JSON-LD content entity does not carry an author "
                    "that is a Person object whose name matches the meta author"
                )
                ld_author_problem = True

    if not ld_author_ok and not ld_author_problem:
        problems.append(
            "no JSON-LD primary content entity names an author matching the meta "
            "author; add a Person author whose name matches the meta author"
        )

    return problems, author


def main() -> int:
    require_full_history()
    pages = content_pages()
    if not pages:
        die(f"no content pages found under {SITE_ROOT}")

    today = dt.date.today().isoformat()
    findings: dict[str, list[str]] = {}
    authors: dict[str, list[str]] = {}

    for path in pages:
        relative = path.relative_to(REPO_ROOT).as_posix()
        try:
            problems, author = check_page(path, today)
        except OSError as error:
            die(f"could not read {relative}: {error}")
        if problems:
            findings[relative] = problems
        if author:
            authors.setdefault(author, []).append(relative)

    if len(authors) > 1:
        listed = "; ".join(f"{name!r} on {len(files)} page(s)" for name, files in authors.items())
        findings.setdefault("(across pages)", []).append(
            f"pages disagree on the author: {listed}"
        )

    if findings:
        print("Page metadata problems found:")
        for relative, problems in findings.items():
            print(f"  {relative}")
            for problem in problems:
                print(f"    - {problem}")
        total = sum(len(v) for v in findings.values())
        print(f"\n{total} problem(s) across {len(findings)} page(s).")
        return 1

    author = next(iter(authors), "(none)")
    print(
        f"All {len(pages)} content pages carry author and date metadata "
        f"consistent with git history. Author: {author}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
