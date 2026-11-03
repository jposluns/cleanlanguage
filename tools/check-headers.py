#!/usr/bin/env python3
"""Check that site/_headers sets the decided security headers exactly once.

Cloudflare Pages reads ``site/_headers`` as a list of rules. A line that starts
in the first column is a URL pattern; each indented line under it is either a
header, ``Name: value``, or a detach, ``! Name``, which removes a header that an
earlier rule set. Pages applies every rule whose pattern matches a request, and
when 2 matching rules set the same header it joins their values with a comma.
So a header set in the ``/*`` rule and again in any other rule reaches the
responses that both rules match twice over, as a single joined value.

What it verifies
----------------

1. The file reads as UTF-8 with no byte order mark, and its lines break only
   at a line feed; one carriage return before a line feed is ignored, and a
   carriage return at the end of the file, with no line feed after it, counts
   as a lone carriage return. A line that holds any other control character (a
   tab or a lone carriage return included), a Unicode line or paragraph
   separator, a byte order mark, or any whitespace other than the ASCII space
   (U+0020) fails closed (exit 3), naming the line. A line that starts in the
   first column is a ``#`` comment or a URL pattern, and a URL pattern is a
   path that starts with ``/`` or an absolute URL that starts with
   ``https://``, with no space in it. A header line is indented by one or more
   ASCII spaces, sits under a URL pattern and has the form ``Name: value`` or
   ``! Name``, where the name is an HTTP token (RFC 9110 ``tchar`` characters
   only) and only ASCII spaces may follow the colon. A header name never starts
   with ``!``, which marks a detach (``!X-Name: value`` fails closed). An indented line that
   looks like a URL or a path, a first-column line that is neither a comment
   nor a URL pattern (a header written without its indent, for example), a
   line that ends in a space, a line that holds only spaces, and any other
   line fail closed (exit 3).
2. The ``/*`` rule sets each of these headers exactly once, with exactly this
   value:

   - ``X-Frame-Options: DENY``
   - ``Permissions-Policy: accelerometer=(), autoplay=(), bluetooth=(),
     browsing-topics=(), camera=(), display-capture=(), fullscreen=(),
     geolocation=(), gyroscope=(), hid=(), magnetometer=(), microphone=(),
     midi=(), payment=(), serial=(), usb=()``
   - ``Cross-Origin-Opener-Policy: same-origin``

   - ``Content-Security-Policy:`` the shared policy of the template
     specification (baseline 1.5.0, section 9), ``DRAFT_CSP`` below, the same
     value a ``/draft/*`` rule sets while a draft is staged.
3. No other rule sets or detaches any of those 4 headers, so each appears once
   on every response class: pages, files and the 404 response. The 1 exception
   is the staged draft's rule (check 5): its own detach and policy replace the
   site-wide policy on ``/draft/*`` responses, so those still carry it once.
5. A ``/draft/*`` rule, while the site is staged there, is exactly these 3
   lines in this order, and nothing else: ``! Content-Security-Policy``,
   ``Content-Security-Policy: `` followed by ``DRAFT_CSP`` below, and
   ``X-Robots-Tag: noindex``. The detach comes first, so Pages removes the
   site-wide policy before it adds the draft's, and the browser never enforces
   both. Any other line in that rule, another value, another order, or the same
   lines under another pattern fails. The owner decided this policy for /draft/
   on 2026-11-03; at promotion the rule is removed and the site-wide rule
   carries the policy. A file with no ``/draft/*`` rule passes check 5.
6. No rule detaches ``X-Robots-Tag``, and no rule other than ``/draft/*`` sets it
   where its pattern can match a path under ``/draft/``: a pattern whose path
   is ``/`` or starts with ``/draft``, or whose first path segment holds a ``*`` or a ``:``
   anywhere (``/*``, ``/:name``, ``/d:x/*``), or a full URL whose path does
   either. So no later rule
   can remove or dilute the draft's ``X-Robots-Tag: noindex``. Rules for other
   paths, such as the download files' ``noindex``, are unaffected. The pattern
   comparison ignores case (``/Draft/*`` counts as reaching the draft), because
   whether Cloudflare Pages matches ``_headers`` patterns case-sensitively is
   not established, so the check fails closed.
4. No rule sets or detaches ``X-Content-Type-Options``, ``Referrer-Policy`` or
   ``Strict-Transport-Security``. Cloudflare sends the first 2 by default and the
   zone sends HSTS, so a line here would duplicate or remove them.

Header names compare without regard to case, as HTTP defines them. A value
compares exactly, after the ASCII spaces between the colon and the value are
removed; no other character is removed.

What it does not verify
-----------------------

It reads the file only. It does not observe the headers that Cloudflare actually
sends: zone settings, Transform Rules and the Pages defaults sit between this
file and the response. The live check of each response class stays a separate,
manual acceptance step after deploy. Checks 1 to 5 do not evaluate URL pattern
matching, so a second rule whose pattern happens to be equivalent to ``/*`` (for
example ``https://:host/*``) counts as another rule, where it fails check 3 if it
sets a decided header. Check 6 uses a conservative prefix heuristic,
``reaches_draft``, not Pages' matcher: a pattern reaches the draft when its path
(after any ``https://host``) starts with ``/draft`` in any case, is ``/``, or has
a ``*`` or a ``:`` anywhere in its first segment. Its residual: it reads pattern
text only, so it misses a rule that reaches ``/draft/`` through a redirect or a
rewrite elsewhere, or through any matching behaviour of Pages beyond those
cases; and it flags some patterns Pages would not match to the draft, which can
only fail closed.

Exit codes:
  0  every check passes
  1  one or more checks fail; each problem is listed
  3  site/_headers could not be read or holds a malformed line
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEADERS = REPO_ROOT / "site" / "_headers"

ALL_PATHS = "/*"

DECIDED = {
    "X-Frame-Options": "DENY",
    "Permissions-Policy": (
        "accelerometer=(), autoplay=(), bluetooth=(), browsing-topics=(), camera=(), "
        "display-capture=(), fullscreen=(), geolocation=(), gyroscope=(), hid=(), "
        "magnetometer=(), microphone=(), midi=(), payment=(), serial=(), usb=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
}
ONCE_ANY_VALUE: tuple[str, ...] = ()
FORBIDDEN = ("X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security")

DRAFT_PATTERN = "/draft/*"
DRAFT_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://ajax.cloudflare.com "
    "https://static.cloudflareinsights.com; connect-src 'self' https://cloudflareinsights.com; "
    "style-src 'self'; font-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
# The site-wide policy is the same shared policy (owner's decision: the live pages adopted it after
# https://posluns.ca/privacy/ was published), pinned exactly like the other decided headers.
DECIDED["Content-Security-Policy"] = DRAFT_CSP
# (kind, header name in lower case, value) of each line of the /draft/* rule, in order.
DRAFT_RULE = [
    ("detach", "content-security-policy", None),
    ("set", "content-security-policy", DRAFT_CSP),
    ("set", "x-robots-tag", "noindex"),
]

TOKEN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
HEADER_LINE = re.compile(rf"^({TOKEN}): *(.*)$")
DETACH_LINE = re.compile(rf"^! *({TOKEN})$")
URL_OR_PATH = re.compile(r"^(?:/|[A-Za-z][A-Za-z0-9+.-]*://)")
URL_PATTERN = re.compile(r"^(?:/[^ ]*|https://[^ ]+)$")


def die(message: str) -> None:
    print(f"check-headers: {message}", file=sys.stderr)
    raise SystemExit(3)


def split_lines(text: str) -> list[tuple[int, str]]:
    """Split at line feeds only and return (line number, line) pairs.

    One carriage return before a line feed is removed. A carriage return at the
    end of the text, with no line feed after it, stays and fails closed. Any
    other control character, a Unicode line or paragraph separator, a byte order
    mark, or any whitespace other than the ASCII space fails closed, naming the
    line.
    """
    lines: list[tuple[int, str]] = []
    pieces = text.split("\n")
    for number, raw in enumerate(pieces, start=1):
        if number < len(pieces) and raw.endswith("\r"):
            raw = raw[:-1]
        for char in raw:
            code = f"U+{ord(char):04X}"
            if unicodedata.category(char) == "Cc":
                die(f"site/_headers line {number}: holds the control character {code}; "
                    "a line may end only in a line feed, with at most one carriage return before it")
            if char in ("\u2028", "\u2029"):
                die(f"site/_headers line {number}: holds the Unicode line or paragraph separator "
                    f"{code}; lines break only at a line feed")
            if char == "\ufeff":
                die(f"site/_headers line {number}: holds a byte order mark ({code}); "
                    "save the file as UTF-8 without one")
            if char.isspace() and char != " ":
                die(f"site/_headers line {number}: holds the whitespace character {code}; "
                    "only the ASCII space (U+0020) may appear")
        lines.append((number, raw))
    return lines


def parse(text: str) -> list[tuple[int, str, str, str, str | None]]:
    """Return (line number, pattern, kind, name, value) for each header line.

    kind is "set" or "detach"; value is None for a detach.
    """
    entries: list[tuple[int, str, str, str, str | None]] = []
    pattern: str | None = None
    for number, raw in split_lines(text):
        if not raw:
            continue
        if raw.endswith(" "):
            die(f"site/_headers line {number}: ends in a space; no line may carry trailing "
                "whitespace or hold only spaces")
        content = raw.lstrip(" ")
        if content.startswith("#"):
            continue
        if raw[0] != " ":
            if not URL_PATTERN.match(raw):
                die(f"site/_headers line {number}: a first-column line is not a URL pattern: "
                    f"{raw!r}; a URL pattern is a path that starts with '/' or a URL that "
                    "starts with 'https://', with no space, and a header line is indented")
            pattern = raw
            continue
        line = content
        if pattern is None:
            die(f"site/_headers line {number}: a header line comes before any URL pattern")
        if URL_OR_PATH.match(line):
            die(f"site/_headers line {number}: an indented line looks like a URL or a path: "
                f"{line!r}; a URL pattern starts in the first column")
        detach = DETACH_LINE.match(line)
        if detach:
            if detach.group(1).startswith("!"):
                die(f"site/_headers line {number}: a detached header name starts with '!': "
                    f"{line!r}; write a detach as '! Name'")
            entries.append((number, pattern, "detach", detach.group(1), None))
            continue
        if line.startswith("!") and HEADER_LINE.match(line):
            die(f"site/_headers line {number}: a line that starts with '!' must be a detach, "
                f"'! Name' alone, not a header to set: {line!r}")
        header = HEADER_LINE.match(line)
        if header:
            entries.append((number, pattern, "set", header.group(1), header.group(2)))
            continue
        die(f"site/_headers line {number}: not a 'Name: value' or '! Name' line: {line!r}")
    return entries


def draft_rule(entries: list[tuple[int, str, str, str, str | None]]) -> tuple[set[int], list[str]]:
    """Check 5: the line numbers of an exact /draft/* rule, which check 3 then allows, or a problem."""
    mine = [entry for entry in entries if entry[1] == DRAFT_PATTERN]
    if not mine:
        return set(), []
    shape = [(kind, name.lower(), value) for _, _, kind, name, value in mine]
    if shape != DRAFT_RULE:
        return set(), [
            f"the {DRAFT_PATTERN} rule (lines {', '.join(str(entry[0]) for entry in mine)}) must be exactly "
            f"'! Content-Security-Policy', 'Content-Security-Policy: {DRAFT_CSP}' and "
            "'X-Robots-Tag: noindex', in that order, and nothing else."
        ]
    return {entry[0] for entry in mine}, []


def reaches_draft(pattern: str) -> bool:
    """Whether a URL pattern can match a path under /draft/ (check 6)."""
    path = (re.sub(r"^https://[^/]*", "", pattern) or "/").lower()
    if path.startswith("/draft"):
        return True
    first = path.split("/")[1] if path.count("/") >= 1 else ""
    return path == "/" or "*" in first or ":" in first


def robots_rule(entries: list[tuple[int, str, str, str, str | None]]) -> list[str]:
    """Check 6: the draft's X-Robots-Tag is set only by /draft/* and detached nowhere."""
    problems = []
    for number, pattern, kind, name, _ in entries:
        if name.lower() != "x-robots-tag":
            continue
        if kind == "detach":
            problems.append(f"line {number}: {pattern} detaches X-Robots-Tag; no rule may remove the draft's noindex.")
        elif pattern != DRAFT_PATTERN and reaches_draft(pattern):
            problems.append(
                f"line {number}: {pattern} sets X-Robots-Tag where the draft is served; only {DRAFT_PATTERN} may set it there."
            )
    return problems


def check(entries: list[tuple[int, str, str, str, str | None]]) -> list[str]:
    allowed, problems = draft_rule(entries)
    problems += robots_rule(entries)
    for name in FORBIDDEN:
        for number, pattern, kind, found, _ in entries:
            if found.lower() == name.lower():
                problems.append(
                    f"line {number}: {pattern} {'sets' if kind == 'set' else 'detaches'} "
                    f"{found}, which must not appear in site/_headers."
                )
    for name in list(DECIDED) + list(ONCE_ANY_VALUE):
        matching = [e for e in entries if e[3].lower() == name.lower()]
        in_all = [e for e in matching if e[1] == ALL_PATHS and e[2] == "set"]
        if len(in_all) != 1:
            problems.append(
                f"the {ALL_PATHS} rule sets {name} {len(in_all)} times; it must set it exactly once."
            )
        elif name in DECIDED and in_all[0][4] != DECIDED[name]:
            problems.append(
                f"line {in_all[0][0]}: {name} is {in_all[0][4]!r}; the decided value is "
                f"{DECIDED[name]!r}."
            )
        for number, pattern, kind, found, _ in matching:
            if pattern == ALL_PATHS and kind == "set":
                continue
            if number in allowed:
                continue  # the exact /draft/* rule of check 5
            problems.append(
                f"line {number}: {pattern} {'sets' if kind == 'set' else 'detaches'} {found}; "
                f"only one set line in the {ALL_PATHS} rule may name it."
            )
    return problems


def main() -> int:
    try:
        text = HEADERS.read_bytes().decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        die(f"site/_headers could not be read: {error}")
    problems = check(parse(text))
    if problems:
        print("site/_headers problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        "site/_headers sets X-Frame-Options, Permissions-Policy, Cross-Origin-Opener-Policy "
        "and Content-Security-Policy exactly once, in the /* rule, with the decided values, "
        "and carries no X-Content-Type-Options, Referrer-Policy or Strict-Transport-Security line."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
