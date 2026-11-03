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

1. Every header line sits under a URL pattern and has the form ``Name: value``
   or ``! Name``. Anything else is a malformed line and fails closed (exit 3).
2. The ``/*`` rule sets each of these headers exactly once, with exactly this
   value:

   - ``X-Frame-Options: DENY``
   - ``Permissions-Policy: accelerometer=(), autoplay=(), camera=(),
     display-capture=(), fullscreen=(), geolocation=(), gyroscope=(),
     magnetometer=(), microphone=(), payment=(), usb=()``
   - ``Cross-Origin-Opener-Policy: same-origin``

   It also sets ``Content-Security-Policy`` exactly once. This gate does not pin
   the policy's value: ``tools/check-install-page.py`` checks its sources.
3. No other rule sets or detaches any of those 4 headers, so each appears once
   on every response class: pages, files and the 404 response.
4. No rule sets or detaches ``X-Content-Type-Options``, ``Referrer-Policy`` or
   ``Strict-Transport-Security``. Cloudflare sends the first 2 by default and the
   zone sends HSTS, so a line here would duplicate or remove them.

Header names compare without regard to case, as HTTP defines them. A value
compares exactly, after the surrounding spaces are removed.

What it does not verify
-----------------------

It reads the file only. It does not observe the headers that Cloudflare actually
sends: zone settings, Transform Rules and the Pages defaults sit between this
file and the response. The live check of each response class stays a separate,
manual acceptance step after deploy. It does not evaluate URL pattern matching,
so a second rule whose pattern happens to be equivalent to ``/*`` (for example
``https://:host/*``) counts as another rule, where it fails check 3 if it sets a
decided header.

Exit codes:
  0  every check passes
  1  one or more checks fail; each problem is listed
  3  site/_headers could not be read or holds a malformed line
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEADERS = REPO_ROOT / "site" / "_headers"

ALL_PATHS = "/*"

DECIDED = {
    "X-Frame-Options": "DENY",
    "Permissions-Policy": (
        "accelerometer=(), autoplay=(), camera=(), display-capture=(), fullscreen=(), "
        "geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
}
ONCE_ANY_VALUE = ("Content-Security-Policy",)
FORBIDDEN = ("X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security")

HEADER_LINE = re.compile(r"^([!-9;-~]+):(.*)$")
DETACH_LINE = re.compile(r"^!\s*([!-9;-~]+)\s*$")


def die(message: str) -> None:
    print(f"check-headers: {message}", file=sys.stderr)
    raise SystemExit(3)


def parse(text: str) -> list[tuple[int, str, str, str, str | None]]:
    """Return (line number, pattern, kind, name, value) for each header line.

    kind is "set" or "detach"; value is None for a detach.
    """
    entries: list[tuple[int, str, str, str, str | None]] = []
    pattern: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            pattern = raw.strip()
            continue
        line = raw.strip()
        if pattern is None:
            die(f"site/_headers line {number}: a header line comes before any URL pattern")
        detach = DETACH_LINE.match(line)
        if detach:
            entries.append((number, pattern, "detach", detach.group(1), None))
            continue
        header = HEADER_LINE.match(line)
        if header:
            entries.append((number, pattern, "set", header.group(1), header.group(2).strip()))
            continue
        die(f"site/_headers line {number}: not a 'Name: value' or '! Name' line: {line!r}")
    return entries


def check(entries: list[tuple[int, str, str, str, str | None]]) -> list[str]:
    problems: list[str] = []
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
            problems.append(
                f"line {number}: {pattern} {'sets' if kind == 'set' else 'detaches'} {found}; "
                f"only one set line in the {ALL_PATHS} rule may name it."
            )
    return problems


def main() -> int:
    try:
        text = HEADERS.read_text(encoding="utf-8", errors="strict")
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
