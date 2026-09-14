#!/usr/bin/env python3
"""Extract the strict Clean Language skill version, the one shared way.

This is the single strict extractor for the ``Version:`` line in
``cleanlanguage/SKILL.md``. It reads the content the way the release gates do (a
universal-newline text read, so a ``CRLF`` or a lone ``CR`` line ending agrees,
and a ``NUL`` byte is preserved rather than stripped), takes the FIRST
``Version:`` line, and requires it to be a bare ``X.Y.Z``. A malformed first line
is rejected, never skipped to a later matching one.

The shell and workflow sites that read the version (``tools/release-dry-run.sh``,
``.github/workflows/release-skill.yml``, ``tools/check-portable-text-sync.sh``)
call this tool instead of a hand-rolled ``sed``, so they agree with the gates
byte for byte, including on a ``NUL`` that the old capture-then-``sed`` form
silently stripped. Piping the raw blob straight in
(``git show REF:path | python3 tools/skill-version.py``) reads ALL of stdin, so
the producer completes and can take no ``SIGPIPE``, ending the exit-141
regression a large file used to trigger.

The release gates ``tools/check-release-links.py`` and
``tools/check-release-checksum-live.py`` already carry the equivalent
``VERSION_LINE`` / ``SKILL_VERSION`` regexes. A future consolidation could have
them import this module; that is out of scope here (smallest correct change).

Input modes:
  A positional ``FILE`` path reads that file. ``-`` or no argument reads all of
  stdin.

Output:
  On success, prints only the bare ``X.Y.Z`` version to stdout and exits 0. On a
  missing or malformed first ``Version:`` line, or a read or decode error, prints
  a clear message to stderr and exits non-zero.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

# The gates' own patterns, verbatim (check-release-links.py,
# check-release-checksum-live.py): VERSION_LINE takes the first ``Version:``
# line; SKILL_VERSION validates it as a bare X.Y.Z.
VERSION_LINE = re.compile(r"^Version:[^\n]*", re.M)
SKILL_VERSION = re.compile(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$", re.M)

PROG = "skill-version"


def die(message: str):
    print(f"{PROG}: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_universal(source: str | None) -> str:
    """Read raw bytes from ``source`` (a file path, or stdin for ``-``/None) and
    decode them with universal newlines, byte-identical to the gates'
    ``Path.read_text(encoding="utf-8")``."""
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


def main(argv: list[str]) -> int:
    args = argv[1:]
    if len(args) > 1:
        die(f"usage: {PROG} [FILE|-]  (reads stdin when FILE is omitted or '-')")
    source = args[0] if args else None

    text = read_universal(source)
    line = VERSION_LINE.search(text)
    if line is None:
        die("no 'Version:' line found")
    match = SKILL_VERSION.match(line.group(0))
    if match is None:
        die(f"the first 'Version:' line is not a bare X.Y.Z version: {line.group(0)!r}")
    print(match.group(1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
