#!/usr/bin/env python3
"""Check that python3 is the Python release that .python-version names.

The root ``.python-version`` names the Python release for the site's gates:
Cloudflare's build image page says that the Pages build reads it
(site/README.md), and every workflow that runs ``tools/check-inline-code.py``,
directly or through a page check, runs this check first, as
``python3 -I tools/check-python-version.py``. A runner image that moves to
another release then fails here, naming both versions, until
``.python-version`` is updated in a pull request. On Python 3.6 and older it
fails with exit 1 and names no version: this file imports ``annotations``
from ``__future__``, which those versions cannot compile.

What it verifies
----------------

The file reads as UTF-8 and holds exactly one line, one ``X.Y.Z`` version with
ASCII digits and an optional line feed after it, and that version equals
``platform.python_version()`` of the interpreter running this check.

What it does not verify
-----------------------

It confirms only that the interpreter running it matches the pin. It says
nothing about the Pages build image: only the Pages build log, and the exit 3
of ``tools/check-inline-code.py`` on another version, show the version a Pages
build ran.

Exit codes, on Python 3.7 or later:
  0  the interpreter is the release that .python-version names
  3  .python-version is missing, unreadable or malformed, or names another release
"""

from __future__ import annotations

import platform
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
VERSION_LINE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\n?")


def die(message: str) -> None:
    print(f"check-python-version: {message}", file=sys.stderr)
    raise SystemExit(3)


def main() -> int:
    try:
        text = PYTHON_VERSION_FILE.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        die(f".python-version could not be read: {error}")
    if not VERSION_LINE.fullmatch(text):
        die(f".python-version holds {text!r}, not one X.Y.Z line such as 3.14.4")
    pinned = text.strip()
    running = platform.python_version()
    if running != pinned:
        die(f"python3 is Python {running}, but .python-version names {pinned}; "
            "update .python-version in a pull request")
    print(f"check-python-version: python3 is Python {running}, the release that .python-version names.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
