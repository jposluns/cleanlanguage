#!/usr/bin/env python3
"""Check that site/.well-known/security.txt carries every decided field and value.

The site serves ``/.well-known/security.txt`` (RFC 9116) so that a security
researcher can find where to report a vulnerability. The owner decided its
fields and values; this gate holds the file to that decision.

What it verifies
----------------

1. The file reads as UTF-8, and every line is blank, a ``#`` comment, or a
   ``Field: value`` line. Anything else fails closed (exit 3).
2. Each of these fields appears exactly once, with exactly this value:

   - ``Contact: mailto:jeff@posluns.ca``
   - ``Expires: 2030-10-31T00:00:00Z``
   - ``Encryption: https://posluns.ca/security/pgp-key.txt``
   - ``Policy: https://posluns.ca/security/``
   - ``Preferred-Languages: en, fr``
   - ``Canonical: https://cleanlanguage.ai/.well-known/security.txt``

3. No other field appears.
4. The ``Expires`` date is later than the time the gate runs, read from the
   clock, so the gate fails once the file has expired and must be renewed.

Field names compare without regard to case, as RFC 9116 defines them. A value
compares exactly, after the surrounding spaces are removed.

What it does not verify
-----------------------

It reads the file only. It does not observe what the live domain serves at
``/.well-known/security.txt`` or with which Content-Type, and it does not fetch
the Encryption or Policy URLs. Those stay a manual check after deploy.

Exit codes:
  0  every check passes
  1  one or more checks fail; each problem is listed
  3  the file could not be read or holds a malformed line
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SECURITY_TXT = REPO_ROOT / "site" / ".well-known" / "security.txt"

DECIDED = {
    "Contact": "mailto:jeff@posluns.ca",
    "Expires": "2030-10-31T00:00:00Z",
    "Encryption": "https://posluns.ca/security/pgp-key.txt",
    "Policy": "https://posluns.ca/security/",
    "Preferred-Languages": "en, fr",
    "Canonical": "https://cleanlanguage.ai/.well-known/security.txt",
}

FIELD_LINE = re.compile(r"^([A-Za-z0-9-]+):(.*)$")


def die(message: str) -> None:
    print(f"check-security-txt: {message}", file=sys.stderr)
    raise SystemExit(3)


def parse(text: str) -> list[tuple[int, str, str]]:
    fields: list[tuple[int, str, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = FIELD_LINE.match(line)
        if not match:
            die(f"site/.well-known/security.txt line {number}: not a 'Field: value' line: {line!r}")
        fields.append((number, match.group(1), match.group(2).strip()))
    return fields


def check(fields: list[tuple[int, str, str]], now: datetime) -> list[str]:
    problems: list[str] = []
    known = {name.lower() for name in DECIDED}
    for number, name, _ in fields:
        if name.lower() not in known:
            problems.append(f"line {number}: {name} is not a decided field.")
    for name, value in DECIDED.items():
        found = [f for f in fields if f[1].lower() == name.lower()]
        if len(found) != 1:
            problems.append(f"{name} appears {len(found)} times; it must appear exactly once.")
            continue
        number, _, got = found[0]
        if got != value:
            problems.append(f"line {number}: {name} is {got!r}; the decided value is {value!r}.")
        elif name == "Expires":
            expires = datetime.strptime(got, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if expires <= now:
                problems.append(
                    f"line {number}: Expires {got} is not later than now "
                    f"({now.strftime('%Y-%m-%dT%H:%M:%SZ')}); renew the file."
                )
    return problems


def main(now: datetime | None = None) -> int:
    try:
        text = SECURITY_TXT.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        die(f"site/.well-known/security.txt could not be read: {error}")
    if now is None:
        now = datetime.now(timezone.utc)
    problems = check(parse(text), now)
    if problems:
        print("site/.well-known/security.txt problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        "site/.well-known/security.txt carries each of its 6 decided fields exactly once with "
        "the decided value, no other field, and an Expires date later than now."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
