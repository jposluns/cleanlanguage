#!/usr/bin/env python3
"""Run the baseline's palette contrast gate on this site, after checking its pin.

Baseline 1.6.0 ships a contrast gate, ``tools/check_palette.py``, and makes it
mandatory: a site copies it to ``.baseline/check_palette.py``, pins it in
``.baseline/pin.toml`` and runs it from the build (baseline README, "Adoption
in a repository", steps 2 and 3). It is never served. This wrapper is the one
launch form for it here, ``python3 -I tools/check-palette.py``, from any
working folder, and it runs exactly:

    python3 -I .baseline/check_palette.py --site cleanlanguage --palettes <output root>/assets/baseline/palettes.css

from the repository root, where the output root follows the base path in
``site-src/site.json`` (``site/`` at base ``/``). The explicit ``--palettes``
matters: without it the tool reads a path relative to its own folder, which
does not resolve from ``.baseline/``.

What it verifies
----------------

1. ``.baseline/pin.toml`` parses as TOML and pins ``.baseline/check_palette.py``
   with a lower-case SHA-256, and that file is a regular file that hashes to
   it, so a tampered copy never runs. ``tools/check-baseline-pin.py`` checks
   the same digest against the version's ``SHA256SUMS``.
2. No file named ``site-palette.css`` exists under the output root. This site
   sets no palette colours of its own, the maintainer's default (template
   specification, "Site-owned palette colours"), so such a file is drift, and
   the command above runs without ``--site-palette``.
3. The pinned gate passes, read from its own exit status: 0 when every
   contrast check passes, 1 on any failure or on input it cannot read, and 2
   on a usage error. The wrapper exits with that status. From baseline 1.9.1
   the gate also reads the ``baseline.css`` beside ``palettes.css``, where the
   family and component tokens are declared.

What it does not verify
-----------------------

It checks the pinned file's digest and then runs that file, so a write to it
between the 2 steps is not caught; the repository's checkout is the trust
boundary. It judges the palette only, not the rendered pages.

Exit codes:
  0  the pin holds and every contrast check passes
  1  the pinned gate's digest differs, a site-palette.css exists, or a contrast check fails
  2  the pinned gate reports a usage error
  3  the pin, the pinned gate, site-src/site.json or the output root could not be read
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python older than 3.11
    print("check-palette: Python 3.11 or later is required (tomllib)", file=sys.stderr)
    raise SystemExit(3)

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN = Path(".baseline/pin.toml")
TOOL = ".baseline/check_palette.py"
SITE_JSON = Path("site-src/site.json")
SITE = "cleanlanguage"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Unreadable(Exception):
    """An input the wrapper must read could not be read, or is malformed."""


def read_bytes(path: Path) -> bytes:
    try:
        info = os.lstat(path)
    except OSError as error:
        raise Unreadable(f"{path} could not be read: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise Unreadable(f"{path} is not a regular file")
    try:
        return path.read_bytes()
    except OSError as error:
        raise Unreadable(f"{path} could not be read: {error}") from error


def pinned_digest(root: Path) -> str:
    try:
        pin = tomllib.loads(read_bytes(root / PIN).decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise Unreadable(f"{PIN} is not valid TOML: {error}") from error
    files = pin.get("files")
    digest = files.get(TOOL) if isinstance(files, dict) else None
    if not isinstance(digest, str) or not HEX64.match(digest):
        raise Unreadable(f"{PIN} does not pin {TOOL} with a lower-case sha256")
    return digest


def output_root(root: Path) -> Path:
    try:
        base = json.loads(read_bytes(root / SITE_JSON).decode("utf-8")).get("base")
    except (UnicodeError, ValueError, AttributeError) as error:
        raise Unreadable(f"{SITE_JSON} is not a JSON object with a base: {error}") from error
    if base == "/":
        return Path("site")
    if not isinstance(base, str) or not re.match(r"^/[a-z0-9-]+/$", base):
        raise Unreadable(f"{SITE_JSON} base {base!r} must be / or a single folder such as /draft/")
    return Path("site") / base.strip("/")


def site_palettes(directory: Path) -> list[Path]:
    found: list[Path] = []
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            raise Unreadable(f"{current} could not be listed: {error}") from error
        for entry in entries:
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as error:
                raise Unreadable(f"{entry.path} could not be read: {error}") from error
            if stat.S_ISDIR(mode):
                stack.append(Path(entry.path))
            elif entry.name == "site-palette.css":
                found.append(Path(entry.path))
    return sorted(found)


def main() -> int:
    root = REPO_ROOT
    try:
        digest = pinned_digest(root)
        if hashlib.sha256(read_bytes(root / TOOL)).hexdigest() != digest:
            print(f"check-palette: {TOOL} differs from its pinned digest; never edit a copied file.")
            return 1
        out = output_root(root)
        strays = site_palettes(root / out)
    except Unreadable as error:
        print(f"check-palette: {error}", file=sys.stderr)
        return 3
    if strays:
        for path in strays:
            print(f"check-palette: {path.relative_to(root)} exists, but this site sets no palette colours of its own.")
        return 1
    command = [sys.executable, "-I", TOOL, "--site", SITE, "--palettes", (out / "assets/baseline/palettes.css").as_posix()]
    code = subprocess.run(command, cwd=root).returncode
    print(f"check-palette: the pinned palette gate exited {code}.")
    return code


if __name__ == "__main__":
    sys.exit(main())
