#!/usr/bin/env python3
"""Shared HTML metadata and URL helpers for the site's gates.

Both the page-metadata gate and the sitemap engine read the same kinds of thing
from a page: the attributes of its ``<meta>`` and ``<link>`` elements, and the
mapping from an on-origin URL to a file in the site tree. This module holds that
shared logic so the two gates parse identically and a fix lands once. It names no
site; the caller passes the origin and the site root. It uses only the standard
library.

Three capabilities:

1. A context-aware collector (:func:`collect_document_tags`, :func:`meta_tags`,
   :func:`link_tags`) that reads the attributes of every active ``<meta>`` and
   ``<link>`` element. It parses the markup rather than matching a regex, so it
   does not end a tag on a ``>`` inside a quoted value, accepts single-quoted,
   double-quoted, and unquoted values, lowercases attribute names, treats a void
   ``<meta/>`` as ``<meta>``, never collects a tag written inside an HTML
   comment, and never collects a tag inside an inert container, whose content a
   browser does not treat as active document metadata.

2. URL normalization (:func:`parse_origin`, :func:`same_origin_path`) that
   compares a URL to an origin by normalized scheme, host, and port, strips the
   query and fragment, and rejects a URL too malformed to map to a path.

3. On-disk location (:func:`contained`, :func:`locate_on_disk`) that maps a
   validated on-origin URL path to a file under a root, confined to the root and
   matched against the exact on-disk spelling.
"""

from __future__ import annotations

import html.parser
import os
import re
import urllib.parse
from pathlib import Path

# Elements whose content a browser does not treat as active document metadata: a
# template is an inert fragment, a noscript body is inert while scripting is on,
# and the rest are raw-text elements. A <meta> or <link> inside any of them is
# not live metadata, so the collector ignores it. The raw-text elements (script,
# style, and, by the CDATA extension below, noscript) are handled by html.parser
# itself; the ones listed here are the containers html.parser parses normally, so
# the collector tracks them itself and does not depend on the interpreter version.
INERT_ELEMENTS = frozenset({"template", "title", "textarea"})

_COLLECTED_ELEMENTS = frozenset({"meta", "link"})

# A control character is never a valid URL byte and never a safe filesystem byte.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# A path segment is well formed only when every "%" begins a "%HH" escape.
_PERCENT_ESCAPE = re.compile(r"\A(?:[^%]|%[0-9A-Fa-f]{2})*\Z")


class _DocumentTags(html.parser.HTMLParser):
    """Collect the attributes of every active ``<meta>`` and ``<link>`` element.

    A ``<meta>`` or ``<link>`` inside an inert container is ignored the way a
    browser ignores it. The raw-text containers (``<script>``, ``<style>``, and
    ``<noscript>`` via the CDATA extension below) are handled by html.parser, whose
    tokenizer does not emit their inner tags. The rest are tracked here with a
    stack of open containers; an end tag pops the stack to and including its match,
    which recovers from an unclosed inner container the way HTML's implied end tags
    do, where a plain depth counter would stay stuck and hide the rest of the page.
    """

    # Treat <noscript> as a raw-text element on every interpreter version, so its
    # content is not parsed as active metadata. html.parser only gained a scripting
    # flag for this distinction in 3.14; extending CDATA_CONTENT_ELEMENTS is the
    # portable equivalent and matches what a scripting-enabled browser does.
    CDATA_CONTENT_ELEMENTS = html.parser.HTMLParser.CDATA_CONTENT_ELEMENTS + ("noscript",)

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.metas: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self._inert: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in INERT_ELEMENTS:
            self._inert.append(tag)
            return
        if self._inert or tag not in _COLLECTED_ELEMENTS:
            return
        # HTML tokenization keeps the first of a repeated attribute.
        values: dict[str, str] = {}
        for name, value in attrs:
            values.setdefault(name.lower(), value or "")
        (self.metas if tag == "meta" else self.links).append(values)

    def handle_startendtag(self, tag, attrs):
        # A self-closing slash is ignored on a non-void element, so <template/>
        # opens an inert context that only </template> closes, exactly as a
        # browser and the ld+json collector treat it; a void <meta/> or <link/>
        # is collected the same as its open form. handle_starttag covers all three.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in INERT_ELEMENTS and tag in self._inert:
            while self._inert:
                if self._inert.pop() == tag:
                    break


def collect_document_tags(
    text: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return ``(metas, links)``: the attribute dict of every active ``<meta>``
    and every active ``<link>`` element, each in source order."""
    parser = _DocumentTags()
    parser.feed(text)
    parser.close()
    return parser.metas, parser.links


def meta_tags(text: str) -> list[dict[str, str]]:
    """The attribute dict of every active ``<meta>`` element in ``text``."""
    return collect_document_tags(text)[0]


def link_tags(text: str) -> list[dict[str, str]]:
    """The attribute dict of every active ``<link>`` element in ``text``."""
    return collect_document_tags(text)[1]


class UrlError(ValueError):
    """A URL too malformed to classify or map: a control character, a bad
    percent escape, a malformed port, or a decoded path separator."""


def _normalize_host(host: str) -> str:
    """Lowercase a host and drop a single trailing dot, so a fully qualified name
    like ``example.com.`` compares equal to ``example.com``."""
    host = host.lower()
    if len(host) > 1 and host.endswith("."):
        host = host[:-1]
    return host


def parse_origin(origin: str) -> tuple[str, str, int]:
    """The normalized ``(scheme, host, effective port)`` of an absolute http or
    https URL. The scheme and host are lowercased and a single trailing dot is
    dropped from the host; the port is 80 or 443 when it is omitted. Raises
    :class:`UrlError` when the URL is unparseable, its scheme is not http(s), it
    carries userinfo, its host is missing or malformed, or its port is malformed."""
    try:
        parts = urllib.parse.urlsplit(origin)
    except ValueError as error:
        raise UrlError(f"origin is malformed: {origin!r}") from error
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UrlError(f"origin scheme is not http(s): {origin!r}")
    if parts.username is not None or parts.password is not None:
        raise UrlError(f"origin must not carry userinfo: {origin!r}")
    host = parts.hostname
    if not host or _CONTROL.search(host) or "\\" in host:
        raise UrlError(f"origin has no usable host: {origin!r}")
    try:
        port = parts.port
    except ValueError as error:
        raise UrlError(f"origin has a malformed port: {origin!r}") from error
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, _normalize_host(host), port


def same_origin_path(url: str, origin: str) -> str | None:
    """The decoded, validated URL path when ``url`` is on the same origin as
    ``origin``, with the query and fragment stripped. ``None`` when ``url`` is
    relative, scheme-relative, another scheme, or another origin. Raises
    :class:`UrlError` when ``url`` claims this origin but is malformed."""
    origin_scheme, origin_host, origin_port = parse_origin(origin)
    # A browser normalizes a backslash to a forward slash in an http(s) URL, so a
    # card written with backslashes still resolves against this origin.
    url = url.replace("\\", "/")
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as error:
        raise UrlError(f"image URL is malformed: {url!r}") from error
    scheme = parts.scheme.lower()
    host = parts.hostname
    if not scheme or not host or scheme not in ("http", "https"):
        return None
    if _normalize_host(host) != origin_host:
        return None
    try:
        port = parts.port
    except ValueError as error:
        raise UrlError(f"image URL has a malformed port: {url!r}") from error
    if port is None:
        port = 443 if scheme == "https" else 80
    if (scheme, port) != (origin_scheme, origin_port):
        return None
    # urlsplit strips a tab, carriage return, or line feed from the URL, so the
    # raw control-character check runs on the original string, not the parsed path.
    if _CONTROL.search(url):
        raise UrlError(f"image URL contains a control character: {url!r}")
    path = parts.path
    if " " in path:
        raise UrlError(f"image URL path contains a raw space: {url!r}")
    segments: list[str] = []
    for segment in path.split("/"):
        if not _PERCENT_ESCAPE.fullmatch(segment):
            raise UrlError(f"image URL path has a malformed percent escape: {url!r}")
        try:
            decoded = urllib.parse.unquote(segment, errors="strict")
        except UnicodeDecodeError as error:
            raise UrlError(
                f"image URL path is not valid UTF-8 once decoded: {url!r}"
            ) from error
        if "/" in decoded or "\\" in decoded or _CONTROL.search(decoded):
            raise UrlError(
                f"image URL path decodes to a separator or control byte: {url!r}"
            )
        segments.append(decoded)
    return "/".join(segments)


def contained(path: Path, root: Path) -> bool:
    """True when ``path`` resolves to ``root`` itself or somewhere beneath it.
    Resolving follows symlinks, so a link pointing outside the tree is caught."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def locate_on_disk(url_path: str, root: Path) -> tuple[str, Path]:
    """Map a decoded on-origin URL path to a file under ``root``.

    Returns a ``(status, path)`` pair:

    - ``"outside"``: the candidate resolves outside ``root`` (path: the candidate).
    - ``"missing"``: no entry at that path, the final entry is not a regular file,
      or a component before the last is itself a file (path: the candidate).
    - ``"case"``: the file exists but a path component's spelling differs from the
      request (path: the actual on-disk spelling).
    - ``"ok"``: the file exists at the exact spelling (path: the resolved target).

    A genuine ``OSError`` (a permission or I/O error) from ``scandir`` or
    ``resolve`` propagates: an unreadable tree is the caller's could-not-run case,
    never a verdict. A ``NotADirectoryError`` from walking through a file is a
    content problem and is reported as ``"missing"``.
    """
    candidate = root / url_path.lstrip("/")
    target = candidate.resolve()
    if not contained(target, root):
        return "outside", candidate
    root_resolved = root.resolve()
    current = root_resolved
    spelled_differently = False
    for part in target.relative_to(root_resolved).parts:
        try:
            entries = {entry.name for entry in os.scandir(current)}
        except NotADirectoryError:
            return "missing", candidate
        if part in entries:
            current = current / part
            continue
        folded = {name.casefold(): name for name in entries}
        actual = folded.get(part.casefold())
        if actual is None:
            return "missing", candidate
        current = current / actual
        spelled_differently = True
    if not current.is_file():
        return "missing", candidate
    if spelled_differently:
        return "case", current
    return "ok", current
