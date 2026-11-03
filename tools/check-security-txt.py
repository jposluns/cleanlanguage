#!/usr/bin/env python3
"""Check that site/.well-known/security.txt carries every decided field and value.

The site serves ``/.well-known/security.txt`` (RFC 9116) so that a security
researcher can find where to report a vulnerability. The owner decided its
fields and values; this gate holds the file to that decision.

What it verifies
----------------

1. The file reads as UTF-8 with no byte order mark, and its lines break only
   at a line feed; one carriage return before a line feed is ignored, and a
   carriage return at the end of the file, with no line feed after it, counts
   as a lone carriage return. A line that holds any other control character (a
   tab or a lone carriage return included), a Unicode line or paragraph
   separator, a byte order mark, or any whitespace other than the ASCII space
   (U+0020) fails closed (exit 3), naming the line. Every line is empty, a
   ``#`` comment, or a ``Field: value`` line with at most one space after the
   colon, as RFC 9116 shows it. A line that starts or ends with a space, a
   line with more than one space after the colon, and any other line fail
   closed (exit 3).
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
is everything after the colon and its optional single space, and compares
exactly; no character is removed from it.

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
import unicodedata
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

FIELD_LINE = re.compile(r"^([A-Za-z0-9-]+): ?(.*)$")


def die(message: str) -> None:
    print(f"check-security-txt: {message}", file=sys.stderr)
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
                die(f"site/.well-known/security.txt line {number}: holds the control character "
                    f"{code}; a line may end only in a line feed, with at most one carriage "
                    "return before it")
            if char in ("\u2028", "\u2029"):
                die(f"site/.well-known/security.txt line {number}: holds the Unicode line or "
                    f"paragraph separator {code}; lines break only at a line feed")
            if char == "\ufeff":
                die(f"site/.well-known/security.txt line {number}: holds a byte order mark "
                    f"({code}); save the file as UTF-8 without one")
            if char.isspace() and char != " ":
                die(f"site/.well-known/security.txt line {number}: holds the whitespace "
                    f"character {code}; only the ASCII space (U+0020) may appear")
        lines.append((number, raw))
    return lines


def parse(text: str) -> list[tuple[int, str, str]]:
    fields: list[tuple[int, str, str]] = []
    for number, line in split_lines(text):
        if not line:
            continue
        if line.startswith(" "):
            die(f"site/.well-known/security.txt line {number}: starts with a space; a field "
                "or comment starts in the first column")
        if line.endswith(" "):
            die(f"site/.well-known/security.txt line {number}: ends in a space; nothing may "
                "follow the value but the line end")
        if line.startswith("#"):
            continue
        match = FIELD_LINE.match(line)
        if not match:
            die(f"site/.well-known/security.txt line {number}: not a 'Field: value' line: {line!r}")
        if match.group(2).startswith(" "):
            die(f"site/.well-known/security.txt line {number}: more than one space after the "
                "colon; RFC 9116 shows at most one")
        fields.append((number, match.group(1), match.group(2)))
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
        text = SECURITY_TXT.read_bytes().decode("utf-8", errors="strict")
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
