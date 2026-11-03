#!/usr/bin/env python3
"""Tests for tools/copy-baseline.py: it copies exactly the runtime set and refuses a bad folder.

Each case builds a small repository and an unpacked version folder in a
temporary folder (under $TMPDIR), places a copy of the tool (and of
``tools/check-baseline-pin.py``) in that repository, runs the tool as a
separate process and asserts its exit code. The version folder lists, beside
the runtime and licence set, a ``reference/`` page, a ``tools/`` script and a
document, which the tool must not copy.

The clean case also asserts that the copied files are exactly the runtime and
licence set, ``matrix.js`` (from 1.5.0) and ``rail.js`` among them, each byte
for byte; that the pin names each copied file and no other; that
``.baseline/SHA256SUMS`` is the version's own; and that
``tools/check-baseline-pin.py`` passes on the result. Exit 0 when every case
passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "tools" / "copy-baseline.py"
GATE = REPO_ROOT / "tools" / "check-baseline-pin.py"
VERSION = "9.8.7"
ARCHIVE_SHA256 = "0" * 64

# The runtime and licence set the tool copies into assets/baseline/.
RUNTIME = {
    "baseline.css": b"a { color: red; }\n",
    "palettes.css": b"/* palettes */\n",
    "fonts.css": b"/* fonts */\n",
    "copy.js": b"/* copy */\n",
    "select.js": b"/* select */\n",
    "search.js": b"/* search */\n",
    "rail.js": b"/* rail */\n",
    "matrix.js": b"/* matrix */\n",
    "LICENSE": b"CC0\n",
    "NOTICE.md": b"# notice\n",
    "fonts/x.woff2": b"\x00\x01font",
    "fonts/OFL.txt": b"OFL\n",
    "logos/logo.svg": b"<svg/>\n",
    "marks/NOTICE.md": b"# marks\n",
    "marks/mark.svg": b"<svg/>\n",
}
# Files the version lists that the tool must never copy.
NOT_COPIED = {
    "README.md": b"# readme\n",
    "SPECIFICATION.md": b"# specification\n",
    "gen_palettes.py": b"# generator\n",
    "contrast-report.txt": b"report\n",
    "reference/landing.html": b"<!doctype html>\n",
    "tools/check.py": b"# tool\n",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(scratch: Path) -> tuple[Path, Path]:
    """A repository with the tool, and a verified version folder; returns (repo, folder)."""
    repo = scratch / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copyfile(TOOL, repo / "tools" / "copy-baseline.py")
    shutil.copyfile(GATE, repo / "tools" / "check-baseline-pin.py")
    (repo / "site-src").mkdir()
    (repo / "site-src" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")
    folder = scratch / "unpacked" / VERSION
    for name, data in {**RUNTIME, **NOT_COPIED}.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    sums = "".join(f"{digest(data)}  {name}\n" for name, data in sorted({**RUNTIME, **NOT_COPIED}.items()))
    (folder / "SHA256SUMS").write_text(sums, encoding="utf-8")
    return repo, folder


def run(repo: Path, folder: Path, sums_sha256: str | None = None) -> int:
    if sums_sha256 is None:
        sums_sha256 = digest((folder / "SHA256SUMS").read_bytes())
    command = [sys.executable, "-I", str(repo / "tools" / "copy-baseline.py"), "--from", str(folder),
               "--sums-sha256", sums_sha256, "--archive-sha256", ARCHIVE_SHA256]
    return subprocess.run(command, capture_output=True, text=True).returncode


def copied_files(repo: Path) -> dict[str, bytes]:
    root = repo / "site" / "assets" / "baseline"
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def check_clean(repo: Path, folder: Path) -> list[str]:
    problems: list[str] = []
    code = run(repo, folder)
    if code != 0:
        return [f"exit {code}, expected 0"]
    found = copied_files(repo)
    if sorted(found) != sorted(RUNTIME):
        missing = sorted(set(RUNTIME) - set(found))
        extra = sorted(set(found) - set(RUNTIME))
        problems.append(f"copied set differs: missing {missing}, extra {extra}")
    for name, data in RUNTIME.items():
        if name in found and found[name] != data:
            problems.append(f"{name} was not copied byte for byte")
    pin = (repo / ".baseline" / "pin.toml").read_text(encoding="utf-8")
    pinned = sorted(line.split('"')[1] for line in pin.splitlines() if line.startswith('"assets/baseline/'))
    if pinned != sorted(f"assets/baseline/{name}" for name in RUNTIME):
        problems.append(f"the pin names {pinned}, not exactly the copied set")
    for name, data in RUNTIME.items():
        if f'"assets/baseline/{name}" = "{digest(data)}"' not in pin:
            problems.append(f"the pin has no line for {name} with its digest")
    if f'version = "{VERSION}"' not in pin:
        problems.append("the pin does not name the version")
    if (repo / ".baseline" / "SHA256SUMS").read_bytes() != (folder / "SHA256SUMS").read_bytes():
        problems.append(".baseline/SHA256SUMS is not the version's own")
    gate = subprocess.run([sys.executable, "-I", str(repo / "tools" / "check-baseline-pin.py"), str(repo)],
                          capture_output=True, text=True).returncode
    if gate != 0:
        problems.append(f"check-baseline-pin.py exits {gate} on the result, expected 0")
    return problems


def fault_wrong_sums_digest(repo: Path, folder: Path) -> int:
    return run(repo, folder, sums_sha256="f" * 64)


def fault_not_a_version(repo: Path, folder: Path) -> int:
    renamed = folder.with_name("baseline-" + VERSION)
    folder.rename(renamed)
    return run(repo, renamed)


def fault_unlisted_file(repo: Path, folder: Path) -> int:
    (folder / "extra.js").write_bytes(b"/* extra */\n")
    return run(repo, folder)


def fault_missing_file(repo: Path, folder: Path) -> int:
    (folder / "matrix.js").unlink()
    return run(repo, folder)


def fault_changed_file(repo: Path, folder: Path) -> int:
    (folder / "matrix.js").write_bytes(b"/* changed */\n")
    return run(repo, folder)


CASES = [
    ("SHA256SUMS does not hash to the given digest", fault_wrong_sums_digest, 1),
    ("the folder name is not a version number", fault_not_a_version, 1),
    ("a file the folder holds that SHA256SUMS does not list", fault_unlisted_file, 1),
    ("a file SHA256SUMS lists that the folder lacks", fault_missing_file, 1),
    ("a file that differs from its SHA256SUMS digest", fault_changed_file, 1),
]


def main() -> int:
    failures: list[str] = []
    ran = 0
    with tempfile.TemporaryDirectory() as scratch:
        repo, folder = build(Path(scratch))
        ran += 1
        failures += [f"clean version folder: {problem}" for problem in check_clean(repo, folder)]
    for name, fault, expected in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            repo, folder = build(Path(scratch))
            code = fault(repo, folder)
            ran += 1
            if code != expected:
                failures.append(f"{name}: exit {code}, expected {expected}")
            elif (repo / ".baseline").exists() or (repo / "site").exists():
                failures.append(f"{name}: the tool wrote a copy or a pin before refusing")
    if failures:
        print("test-copy-baseline: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-copy-baseline: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
