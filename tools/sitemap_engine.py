"""A portable, deterministic sitemap engine.

This module builds and verifies a `sitemap.xml` as a pure function of a site's
page tree and a small per-project configuration. It carries no knowledge of any
one site: every project-specific fact (the origin, the site root, which files
are pages) arrives through a config object, so the same engine renders an
identical style for every site that adopts it.

A sitemap entry is two derivable facts, a location and a last-modified date, so
the file can be generated and then verified byte for byte. The generator writes
it; a gate re-derives it and fails when the committed bytes differ. Nothing in
the file is hand-tuned, so nothing rots.

What belongs here, and what does not
------------------------------------

The engine owns the shared primitives: config loading and validation, page
enumeration, meta-tag parsing, the indexability filter, the last-modified
resolvers, URL derivation, sorting, the canonical serializer, byte comparison,
and the atomic write. The style constants live here too, so every adopting site
renders identically. The engine names no site: it holds no origin, no site
directory, and no per-page policy.

What a fleet consumer must not assume
-------------------------------------

* Pages are `index.html` files addressed as directory-style pretty URLs
  (`site/guide/index.html` becomes `<base>/guide/`). A flat-file layout
  (`about.html` served at `/about.html`) needs a deliberate engine extension,
  not a config change; two root-level non-index files would both derive `<base>/`
  and fail as duplicates. The `include` globs may nest to any depth, and the URL
  keeps the full path (`site/a/b/index.html` becomes `<base>/a/b/`).
* Indexability is read from an HTML `<meta name="robots">` tag. A page hidden by
  a transport header (an `X-Robots-Tag`) is invisible here and must be named in
  `exclude`.
* HTML uses double-quoted attributes, matching this repository's pages and
  `tools/check-page-metadata.py`. A single-quoted `rel="canonical"` or `robots`
  tag is not recognized.
* The `lastmod` stamp is the authority. The `git_last_change` resolver fails
  closed on a page with no committed history rather than inventing a date.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

# The style, fixed for every adopting site so the fleet renders identically.
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
URLSET_OPEN = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
URLSET_CLOSE = "</urlset>"
INDENT = "  "

# Meta tags are parsed attribute by attribute, matching tools/check-page-metadata.py,
# because a tag may carry both name and property on one element and a fixed-order
# pattern would stop seeing it if the attributes were reordered.
META_TAG = re.compile(r"<meta\s+([^>]*?)/?>", re.I)
META_ATTR = re.compile(r'([A-Za-z][\w:.-]*)\s*=\s*"([^"]*)"')
CANONICAL = re.compile(r'<link\s+[^>]*rel="canonical"[^>]*>', re.I)
HREF_ATTR = re.compile(r'href="([^"]*)"', re.I)
ROBOTS_NOINDEX = re.compile(r"\b(noindex|none)\b", re.I)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ALLOWED_CONFIG_KEYS = {
    "schema",
    "base_url",
    "site_root",
    "output",
    "include",
    "exclude",
    "lastmod",
}
ALLOWED_LASTMOD_SOURCES = {"html_meta_property", "git_last_change"}


class EngineError(Exception):
    """A failure of the tree: drift, or a page that is not in a valid state.
    The caller maps this to a gate failure (exit 1)."""


class EngineRunError(EngineError):
    """The check could not run: a bad or unreadable config, a missing or
    escaping site root, or an unreadable page. The caller maps this to exit 3,
    on the principle that an unanswerable check is never a pass."""


def _contained(path: Path, root: Path) -> bool:
    """True when path resolves to root itself or somewhere beneath it. Resolving
    follows symlinks, so a link pointing outside the tree is caught."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# --- Configuration -------------------------------------------------------


def load_config(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EngineRunError(f"cannot read config {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise EngineRunError(f"config {path} does not parse: {error}") from error
    if not isinstance(raw, dict):
        raise EngineRunError(f"config {path} is not a JSON object")

    unknown = set(raw) - ALLOWED_CONFIG_KEYS
    if unknown:
        raise EngineRunError(f"config has unknown keys: {', '.join(sorted(unknown))}")
    if raw.get("schema") != 1:
        raise EngineRunError('config must set "schema": 1')

    base_url = raw.get("base_url", "")
    if not isinstance(base_url, str) or not re.match(r"^https://[^/?#]+$", base_url):
        raise EngineRunError(
            'config "base_url" must be an https:// origin with no path, query, '
            "fragment, or trailing slash"
        )

    for key in ("site_root", "output"):
        value = raw.get(key)
        if not isinstance(value, str) or not value:
            raise EngineRunError(f'config "{key}" must be a non-empty path')
        if Path(value).is_absolute() or ".." in Path(value).parts:
            raise EngineRunError(f'config "{key}" must be a relative path inside the repository')

    for key in ("include", "exclude"):
        value = raw.get(key, [])
        if not isinstance(value, list) or not all(isinstance(g, str) for g in value):
            raise EngineRunError(f'config "{key}" must be a list of glob strings')

    lastmod = raw.get("lastmod", {})
    if not isinstance(lastmod, dict) or lastmod.get("source") not in ALLOWED_LASTMOD_SOURCES:
        raise EngineRunError(
            f'config "lastmod.source" must be one of {sorted(ALLOWED_LASTMOD_SOURCES)}'
        )
    if lastmod["source"] == "html_meta_property" and not lastmod.get("key"):
        raise EngineRunError('config "lastmod.key" is required for source html_meta_property')

    raw.setdefault("include", [])
    raw.setdefault("exclude", [])
    return raw


# --- Parsing helpers -----------------------------------------------------


def parse_meta(html: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Return (names, property_pairs). Properties are a list so a duplicate
    stamp can be detected rather than silently collapsed."""
    names: dict[str, str] = {}
    properties: list[tuple[str, str]] = []
    for tag in META_TAG.finditer(html):
        attributes = dict(META_ATTR.findall(tag.group(1)))
        content = attributes.get("content")
        if content is None:
            continue
        if "name" in attributes:
            names[attributes["name"]] = content
        if "property" in attributes:
            properties.append((attributes["property"], content))
    return names, properties


def is_indexable(html: str) -> bool:
    """False when any robots meta tag carries noindex or none. Every tag is
    checked, so a later index token cannot mask an earlier noindex."""
    for tag in META_TAG.finditer(html):
        attributes = dict(META_ATTR.findall(tag.group(1)))
        if attributes.get("name", "").lower() == "robots" and ROBOTS_NOINDEX.search(
            attributes.get("content", "")
        ):
            return False
    return True


def canonical_href(html: str) -> str | None:
    match = CANONICAL.search(html)
    if not match:
        return None
    href = HREF_ATTR.search(match.group(0))
    return href.group(1) if href else None


# --- Enumeration and URL derivation -------------------------------------


def enumerate_pages(site_root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    if not _contained(site_root, site_root.parent):
        pass  # site_root is always contained in its own parent; kept for symmetry
    seen: dict[Path, None] = {}
    for pattern in include:
        for path in site_root.glob(pattern):
            if path.is_file():
                if not _contained(path, site_root):
                    raise EngineRunError(
                        f"include pattern {pattern!r} matched {path}, which escapes "
                        f"the site root {site_root}"
                    )
                seen[path] = None
    excluded: set[Path] = set()
    for pattern in exclude:
        excluded.update(p for p in site_root.glob(pattern) if p.is_file())
    return sorted(p for p in seen if p not in excluded)


def derive_url(base_url: str, site_root: Path, page: Path) -> str:
    relative = page.parent.resolve().relative_to(site_root.resolve())
    if relative == Path("."):
        return base_url + "/"
    return f"{base_url}/{relative.as_posix()}/"


# --- Last-modified resolvers --------------------------------------------


def read_meta_stamp(html: str, key: str) -> str:
    _, properties = parse_meta(html)
    stamps = [value for prop, value in properties if prop == key]
    if len(stamps) != 1:
        raise EngineError(f"expected exactly one {key} meta tag, found {len(stamps)}")
    value = stamps[0]
    if not ISO_DATE.match(value):
        raise EngineError(f"{key} is {value!r}, expected YYYY-MM-DD")
    try:
        _dt.date.fromisoformat(value)
    except ValueError as error:
        raise EngineError(f"{key} {value!r} is not a real calendar date: {error}") from error
    return value


def git_last_change(repo_root: Path, relative: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "-1", "--format=%cs", "--", relative],
        capture_output=True,
        text=True,
    )
    date = result.stdout.strip()
    if result.returncode != 0 or not ISO_DATE.match(date):
        raise EngineError(
            f"git records no committed date for {relative}; a page with no history "
            f"cannot supply a lastmod through the git_last_change resolver"
        )
    return date


def resolve_lastmod(config: dict, repo_root: Path, page: Path, html: str) -> str:
    source = config["lastmod"]["source"]
    if source == "html_meta_property":
        return read_meta_stamp(html, config["lastmod"]["key"])
    return git_last_change(repo_root, page.relative_to(repo_root).as_posix())


# --- Build, render, verify, write ---------------------------------------


def _site_root(config: dict, repo_root: Path) -> Path:
    site_root = repo_root / config["site_root"]
    if not site_root.is_dir():
        raise EngineRunError(f"site root {site_root} does not exist")
    if not _contained(site_root, repo_root):
        raise EngineRunError(f"site root {site_root} resolves outside the repository")
    return site_root


def build_entries(config: dict, repo_root: Path) -> list[tuple[str, str]]:
    site_root = _site_root(config, repo_root)
    pages = enumerate_pages(site_root, config["include"], config["exclude"])

    entries: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for page in pages:
        try:
            html = page.read_text(encoding="utf-8")
        except OSError as error:
            raise EngineRunError(f"cannot read {page}: {error}") from error
        if not is_indexable(html):
            continue
        url = derive_url(config["base_url"], site_root, page)
        canonical = canonical_href(html)
        if canonical is not None and canonical != url:
            raise EngineError(
                f"{page.relative_to(repo_root).as_posix()} derives URL {url} but its "
                f"canonical link is {canonical}; they must agree"
            )
        if url in seen_urls:
            raise EngineError(f"two pages derive the same URL {url}")
        seen_urls.add(url)
        entries.append((url, resolve_lastmod(config, repo_root, page, html)))

    if not entries:
        raise EngineError("no indexable pages found; refusing to write an empty sitemap")
    entries.sort(key=lambda entry: entry[0])
    return entries


def render(entries: list[tuple[str, str]]) -> bytes:
    lines = [XML_DECLARATION, URLSET_OPEN]
    for url, lastmod in entries:
        loc = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{INDENT}<url>")
        lines.append(f"{INDENT * 2}<loc>{loc}</loc>")
        lines.append(f"{INDENT * 2}<lastmod>{lastmod}</lastmod>")
        lines.append(f"{INDENT}</url>")
    lines.append(URLSET_CLOSE)
    return ("\n".join(lines) + "\n").encode("utf-8")


def generate_bytes(config: dict, repo_root: Path) -> bytes:
    return render(build_entries(config, repo_root))


def output_path(config: dict, repo_root: Path) -> Path:
    target = repo_root / config["output"]
    if not _contained(target.parent, repo_root):
        raise EngineRunError(f"output {target} resolves outside the repository")
    return target


def verify(config: dict, repo_root: Path) -> tuple[bool, str]:
    expected = generate_bytes(config, repo_root)
    target = output_path(config, repo_root)
    if not target.is_file():
        return False, f"{config['output']} does not exist; run --write to create it"
    try:
        actual = target.read_bytes()
    except OSError as error:
        raise EngineRunError(f"cannot read {config['output']}: {error}") from error
    if actual == expected:
        count = expected.count(b"<url>")
        return True, f"{config['output']} matches the {count} pages; no drift"
    expected_lines = expected.decode("utf-8").splitlines()
    actual_lines = actual.decode("utf-8", "replace").splitlines()
    for number, (want, got) in enumerate(zip(expected_lines, actual_lines), start=1):
        if want != got:
            return False, (
                f"{config['output']} differs at line {number}: expected {want!r}, "
                f"found {got!r}. Run: python3 tools/generate-sitemap.py --write"
            )
    return False, (
        f"{config['output']} differs in length (expected {len(expected_lines)} lines, "
        f"found {len(actual_lines)}). Run: python3 tools/generate-sitemap.py --write"
    )


def _target_mode(target: Path) -> int:
    """The mode to give the written file: the existing file's mode if it exists,
    otherwise a world-readable default narrowed by the process umask, so a
    generated sitemap is readable by the web server and never left at the
    private 0600 a temporary file is created with."""
    if target.is_file():
        return stat.S_IMODE(target.stat().st_mode)
    current = os.umask(0)
    os.umask(current)
    return 0o666 & ~current


def write(config: dict, repo_root: Path) -> int:
    data = generate_bytes(config, repo_root)
    target = output_path(config, repo_root)
    if target.is_file() and target.read_bytes() == data:
        return data.count(b"<url>")
    mode = _target_mode(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "wb", dir=str(target.parent), prefix=".sitemap-", suffix=".tmp", delete=False
    )
    try:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.chmod(handle.name, mode)
        os.replace(handle.name, target)
    except BaseException:
        handle.close()
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    return data.count(b"<url>")
