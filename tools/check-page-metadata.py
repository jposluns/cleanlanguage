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
6. Where a page carries JSON-LD, its ``datePublished``, ``dateModified``, and
   author name agree with the meta tags, so a page cannot contradict itself.
7. Every page names the same author, so one page cannot drift from the rest.

What it does not verify
-----------------------

It proves the dates are internally consistent and consistent with git history.
It does not prove any particular crawler reads or displays them. It says nothing
about whether the prose on a page is current, only about when the file changed.

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
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = REPO_ROOT / "site"

# Pages that must carry the metadata. 404.html is deliberately absent.
EXCLUDED = {"404.html"}

# Pages whose publish date cannot come from git history, with the reason. A page
# that was deleted and re-added, or moved in from elsewhere, belongs here rather
# than being handled by weakening the check.
PUBLISHED_OVERRIDES: dict[str, str] = {}

META_NAME = re.compile(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"\s*/?>')
META_PROPERTY = re.compile(r'<meta\s+property="([^"]+)"\s+content="([^"]*)"\s*/?>')
JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_PROPERTIES = ("article:published_time", "article:modified_time", "article:author")


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
    pages = []
    index = SITE_ROOT / "index.html"
    if index.is_file():
        pages.append(index)
    pages.extend(sorted(SITE_ROOT.glob("*/index.html")))
    return [p for p in pages if p.name not in EXCLUDED]


def check_page(path: Path, today: str) -> tuple[list[str], str | None]:
    """Return the problems found on one page, and the author it names."""
    relative = path.relative_to(REPO_ROOT).as_posix()
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")

    names = dict(META_NAME.findall(text))
    properties = dict(META_PROPERTY.findall(text))

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

    for match in JSON_LD.finditer(text):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as error:
            problems.append(f"JSON-LD does not parse: {error}")
            continue
        if not isinstance(data, dict):
            continue
        ld_published, ld_modified = data.get("datePublished"), data.get("dateModified")
        if ld_published and published and ld_published != published:
            problems.append(
                f"JSON-LD datePublished {ld_published} disagrees with "
                f"article:published_time {published}"
            )
        if ld_modified and modified and ld_modified != modified:
            problems.append(
                f"JSON-LD dateModified {ld_modified} disagrees with "
                f"article:modified_time {modified}"
            )
        ld_author = data.get("author")
        if isinstance(ld_author, dict):
            ld_name = ld_author.get("name")
            if ld_name and author and ld_name != author:
                problems.append(
                    f"JSON-LD author {ld_name!r} disagrees with meta author {author!r}"
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
