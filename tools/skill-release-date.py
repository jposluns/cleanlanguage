#!/usr/bin/env python3
"""Extract the strict Clean Language skill release date, the one shared way.

This is the single strict extractor for the ``Released:`` line in
``cleanlanguage/skills/cleanlanguage/SKILL.md`` and in the four portable
renderings under ``site/downloads/``. It is the sibling of
``tools/skill-version.py`` and reads the content the same way: a
universal-newline text read, so a ``CRLF`` or a lone ``CR`` line ending agrees,
and a ``NUL`` byte is preserved (and so rejected) rather than stripped.

The field (item 26) is one meta line, directly after the ``Version:`` line:

    Released: YYYY-MM-DD

meaning the UTC calendar day on which the matching GitHub Release was first
published. The rules, all enforced here so every caller agrees:

  - The first line that looks like a ``Released:`` key is authoritative. It must
    be spelled exactly ``Released:`` and match
    ``Released:[ \\t]*YYYY-MM-DD[ \\t]*``; a malformed first line is rejected,
    never skipped to a later well-formed one.
  - The value must be a real calendar date (``datetime.date.fromisoformat``).
  - The line must be the line immediately after the first ``Version:`` line.
  - A second ``Released:`` line anywhere is rejected, so a stale copy cannot
    survive beside a fresh one.
  - Absent (no line looks like a ``Released:`` key) is a distinct outcome from
    malformed, because absence is legitimate at or below the baseline version.

The baseline is declared once, here: ``1.0.14`` is the last release that carries
no date. Callers require the line when the skill version sorts above it and
accept it absent at or below it.

Input modes:
  ``FILE`` reads that file; ``-`` or no argument reads all of stdin (so a
  producer piped in completes and can take no ``SIGPIPE``).
  ``--baseline`` prints the baseline version.
  ``--check-date VALUE`` validates a bare ``YYYY-MM-DD`` calendar date and
  prints it.
  ``--published-day VALUE`` prints the UTC day of a release ``published_at``
  value; see ``release_day_from_published_at`` for the assumption it carries.

Exit codes:
  0  success; the date (or the baseline) is printed to stdout
  1  malformed line or value, or the input could not be read or decoded
  2  usage error
  3  absent: no ``Released:`` line
"""

from __future__ import annotations

import datetime
import io
import re
import sys
from pathlib import Path

PROG = "skill-release-date"

# Item 26: 1.0.14 is the last undated release. The Released line is required
# when the skill version sorts above this and accepted absent at or below it.
BASELINE_VERSION = "1.0.14"

# Any line that looks like the key, whatever its case or leading blanks. The
# first such line is the authoritative one; if it is not spelled exactly
# "Released:" it is malformed, never read as absent.
RELEASED_KEY_LIKE = re.compile(r"[ \t]*released[ \t]*:", re.IGNORECASE)
RELEASED_LINE = re.compile(r"Released:[ \t]*([0-9]{4}-[0-9]{2}-[0-9]{2})[ \t]*")
DATE_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
BARE_VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")
PUBLISHED_AT_FORM = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


class Malformed(ValueError):
    """A Released line or value that breaks the strict grammar."""


def parse_date(value: str) -> str:
    """Return ``value`` if it is a bare ``YYYY-MM-DD`` real calendar date."""
    if not isinstance(value, str) or DATE_FORM.fullmatch(value) is None:
        raise Malformed(f"not a bare YYYY-MM-DD date: {value!r}")
    try:
        datetime.date.fromisoformat(value)
    except ValueError as error:
        raise Malformed(f"not a real calendar date: {value!r} ({error})") from None
    return value


def extract(text: str) -> str | None:
    """Return the Released date in ``text``, or None when no line carries the key.

    ``text`` is already decoded with universal newlines. Raises ``Malformed``
    on any breach of the grammar in the module docstring.
    """
    lines = text.split("\n")
    keyed = [i for i, line in enumerate(lines) if RELEASED_KEY_LIKE.match(line)]
    if not keyed:
        return None
    first = keyed[0]
    line = lines[first]
    if not line.startswith("Released:"):
        raise Malformed(f"the first Released line is not spelled exactly Released: {line!r}")
    match = RELEASED_LINE.fullmatch(line)
    if match is None:
        raise Malformed(f"the first Released line is not a bare YYYY-MM-DD date: {line!r}")
    value = parse_date(match.group(1))
    if len(keyed) > 1:
        numbers = ", ".join(str(i + 1) for i in keyed)
        raise Malformed(f"more than one Released line (lines {numbers})")
    version_index = next((i for i, l in enumerate(lines) if l.startswith("Version:")), None)
    if version_index is None:
        raise Malformed("a Released line is present but there is no Version: line")
    if first != version_index + 1:
        raise Malformed(
            f"the Released line (line {first + 1}) is not the line directly after "
            f"the first Version: line (line {version_index + 1})"
        )
    return value


def version_key(version: str) -> tuple[int, int, int]:
    match = BARE_VERSION.fullmatch(version)
    if match is None:
        raise Malformed(f"not a bare X.Y.Z version: {version!r}")
    return tuple(int(part) for part in match.groups())


def requires_release_date(version: str) -> bool:
    """True when ``version`` sorts above the baseline, so the line is required."""
    return version_key(version) > version_key(BASELINE_VERSION)


def release_day_from_published_at(value: str) -> str:
    """Return the UTC calendar day (``YYYY-MM-DD``) of a release ``published_at``.

    UNVERIFIED ASSUMPTION (item 26). This function is the one place the release
    tooling relies on the meaning of the GitHub REST API ``published_at`` field of
    a release record. It assumes that the field:

      - is the UTC instant at which the release was FIRST published, in the
        form ``YYYY-MM-DDTHH:MM:SSZ``;
      - is not changed by a later asset re-upload (``gh release upload
        --clobber``), so a re-run or a force dispatch still reports the
        original publication instant;
      - is null for a draft (``gh api --jq .published_at`` then prints
        ``null``, which is rejected here, failing closed).

    That assumption has not been corroborated against the API documentation or
    a probe of a live release record. Both the release-time check (G3, in
    ``.github/workflows/release-skill.yml``) and the post-release comparison
    (G4, in ``tools/check-release-checksum-live.py``) reach ``published_at`` only
    through this function, so if the assumption is refuted the fix is here and
    in the field each caller reads, nowhere else.

    Raises ``Malformed`` for any value not in exactly that form, including a
    null, an offset other than ``Z``, fractional seconds, or an impossible date
    or time.
    """
    if not isinstance(value, str):
        raise Malformed(f"published_at is not a string: {value!r}")
    match = PUBLISHED_AT_FORM.fullmatch(value)
    if match is None:
        raise Malformed(f"published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}")
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise Malformed(f"published_at is not a real instant: {value!r} ({error})") from None
    return match.group(1)


def die(message: str, code: int = 1):
    print(f"{PROG}: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_universal(source: str | None) -> str:
    """Read ``source`` (a path, or stdin for ``-``/None) with universal newlines,
    byte-identical to ``Path.read_text(encoding="utf-8")``."""
    where = "standard input" if source in (None, "-") else source
    try:
        if source in (None, "-"):
            data = sys.stdin.buffer.read()
        else:
            data = Path(source).read_bytes()
    except OSError as error:
        die(f"could not read {where}: {error}")
    try:
        return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None).read()
    except UnicodeDecodeError as error:
        die(f"{where} is not valid UTF-8: {error}")


USAGE = (
    f"usage: {PROG} [FILE|-] | --baseline | --check-date YYYY-MM-DD"
    f" | --published-day PUBLISHED_AT"
)


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args == ["--baseline"]:
        print(BASELINE_VERSION)
        return 0
    if len(args) == 2 and args[0] in ("--check-date", "--published-day"):
        try:
            if args[0] == "--check-date":
                value = parse_date(args[1])
            else:
                value = release_day_from_published_at(args[1])
        except Malformed as error:
            die(str(error))
        print(value)
        return 0
    if len(args) > 1 or (args and args[0].startswith("--")):
        die(USAGE, 2)
    source = args[0] if args else None
    text = read_universal(source)
    try:
        value = extract(text)
    except Malformed as error:
        die(str(error))
    if value is None:
        die("no Released: line found", 3)
    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
