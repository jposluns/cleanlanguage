#!/usr/bin/env python3
"""Check internal links for breakage, without touching the network.

Two passes, both deterministic and offline:

1. Site HTML: every root-relative or document-relative href/src in
   ``site/**/*.html`` must resolve to a file that exists under ``site/`` (or to
   a redirect source declared in ``site/_redirects``). Query strings and
   fragments are ignored; a directory URL resolves to its ``index.html``.

2. Repository Markdown: every relative link target in the tracked Markdown docs
   must resolve to a file that exists, relative to the linking document.

External links (http, https, mailto, tel), pure anchors, and data URIs are out
of scope: this gate proves internal references resolve, not that remote URLs are
live. It exits non-zero and lists every broken link when it finds one.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = REPO_ROOT / "site"

# href="..." or src="..."
ATTR_LINK = re.compile(r'(?:href|src)\s*=\s*"([^"]*)"')
# Markdown inline link: ](target)
MD_LINK = re.compile(r'\]\(([^)]+)\)')

SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:", "#", "//")

MARKDOWN_DOCS = [
    "README.md",
    "INSTALL.md",
    "NOTICE.md",
    "CLAUDE.md",
    "site/README.md",
    ".claude/CLAUDE.md",
    "cleanlanguage/SKILL.md",
]


def redirect_sources() -> set[str]:
    """Source paths declared in site/_redirects are valid internal targets."""
    sources: set[str] = set()
    redirects = SITE_ROOT / "_redirects"
    if not redirects.is_file():
        return sources
    for line in redirects.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sources.add(line.split()[0])
    return sources


def clean_target(raw: str) -> str:
    """Strip fragment and query from a link target."""
    return raw.split("#", 1)[0].split("?", 1)[0].strip()


def resolve_site(value: str, html_file: Path, redirects: set[str]) -> Path | None:
    """Resolve a site link to a file path, or None if it is a valid redirect."""
    target = clean_target(value)
    if not target:
        return None  # pure fragment or empty; nothing to resolve
    # A path that matches a redirect source is served by Cloudflare, not a file.
    if target.rstrip("/") in {s.rstrip("/") for s in redirects}:
        return None
    if target.startswith("/"):
        base = SITE_ROOT / target.lstrip("/")
    else:
        base = html_file.parent / target
    base = Path(os.path.normpath(base))
    if base.is_dir() or target.endswith("/") or base == SITE_ROOT:
        base = base / "index.html"
    return base


def check_site(redirects: set[str]) -> list[str]:
    errors: list[str] = []
    for html_file in sorted(SITE_ROOT.rglob("*.html")):
        text = html_file.read_text()
        for value in ATTR_LINK.findall(text):
            if value.startswith(SKIP_PREFIXES):
                continue
            target = clean_target(value)
            if not target:
                continue
            resolved = resolve_site(value, html_file, redirects)
            if resolved is None:
                continue  # redirect source or pure fragment
            if not resolved.exists():
                rel = html_file.relative_to(REPO_ROOT)
                errors.append(f"{rel}: '{value}' -> missing {resolved.relative_to(REPO_ROOT)}")
    return errors


def check_markdown() -> list[str]:
    errors: list[str] = []
    for doc in MARKDOWN_DOCS:
        md_file = REPO_ROOT / doc
        if not md_file.is_file():
            continue
        text = md_file.read_text()
        for value in MD_LINK.findall(text):
            value = value.strip()
            if value.startswith(SKIP_PREFIXES):
                continue
            target = clean_target(value)
            if not target:
                continue
            resolved = Path(os.path.normpath(md_file.parent / target))
            if not resolved.exists():
                errors.append(f"{doc}: '{value}' -> missing {resolved.relative_to(REPO_ROOT)}")
    return errors


def main() -> int:
    redirects = redirect_sources()
    errors = check_site(redirects) + check_markdown()
    if errors:
        print("Broken internal links found:")
        for error in errors:
            print(f"  {error}")
        print(f"\n{len(errors)} broken link(s).")
        return 1
    print("All internal links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
