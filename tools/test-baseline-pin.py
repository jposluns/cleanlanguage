#!/usr/bin/env python3
"""Tests for tools/check-baseline-pin.py: each check fails on a deliberate fault.

Each case builds a small pinned tree in a temporary folder (under $TMPDIR),
applies 1 fault, runs the gate on that tree as a separate process and asserts
its exit code. The last case runs the gate on this repository. The first 4
cases run ``tools/copy-baseline.py`` on a small version folder and assert that
the pin header it writes, and the committed one, give each key's base; that it
copies and pins the build tool and counts it among the copied files; and that a
version without the build tool exits 1 before any served file is replaced.
Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-baseline-pin.py"
COPY_TOOL = REPO_ROOT / "tools" / "copy-baseline.py"

FILES = {"baseline.css": b"a { color: red; }\n", "fonts/x.woff2": b"\x00\x01font", "marks/NOTICE.md": b"# marks\n"}
# The rest of the README's runtime and licence set, which the gate requires in the pin.
for _name in ("palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js", "scheme.js", "LICENSE",
              "NOTICE.md"):
    FILES[_name] = f"/* {_name} */\n".encode()
# The pinned build tool, kept at .baseline/check_palette.py and never served.
TOOL = b"# check_palette.py\n"
TOOL_KEY = ".baseline/check_palette.py"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def copied(root: Path) -> Path:
    return root / "site" / "draft" / "assets" / "baseline"


def build(root: Path) -> None:
    for name, data in FILES.items():
        (copied(root) / name).parent.mkdir(parents=True, exist_ok=True)
        (copied(root) / name).write_bytes(data)
    sums = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(FILES.items()))
    sums += f"{digest(b'unpinned')}  reference/landing.html\n"
    sums += f"{digest(TOOL)}  tools/check_palette.py\n"
    (root / ".baseline").mkdir()
    (root / ".baseline" / "SHA256SUMS").write_text(sums, encoding="utf-8")
    (root / TOOL_KEY).write_bytes(TOOL)
    lines = ["# comment", 'version = "1.2.1"', "", "[files]"]
    lines += [f'"assets/baseline/{name}" = "{digest(data)}"' for name, data in sorted(FILES.items())]
    lines += [f'"{TOOL_KEY}" = "{digest(TOOL)}"']
    (root / ".baseline" / "pin.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "site-src").mkdir()
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/draft/"}), encoding="utf-8")


def run(root: Path) -> int:
    return subprocess.run([sys.executable, "-I", str(GATE), str(root)], capture_output=True, text=True).returncode


def edit_pin(root: Path, old: str, new: str) -> None:
    pin = root / ".baseline" / "pin.toml"
    text = pin.read_text(encoding="utf-8")
    assert old in text, old
    pin.write_text(text.replace(old, new, 1), encoding="utf-8")


def fault_flip_byte(root: Path) -> None:
    path = copied(root) / "baseline.css"
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01
    path.write_bytes(bytes(data))


def fault_extra_file(root: Path) -> None:
    (copied(root) / "logos").mkdir()
    (copied(root) / "logos" / "extra.svg").write_bytes(b"<svg/>")


def fault_missing_file(root: Path) -> None:
    (copied(root) / "fonts" / "x.woff2").unlink()


def fault_missing_entry(root: Path) -> None:
    edit_pin(root, f'"assets/baseline/marks/NOTICE.md" = "{digest(FILES["marks/NOTICE.md"])}"\n', "")


def fault_symlink(root: Path) -> None:
    target = copied(root) / "baseline.css"
    real = root / "elsewhere.css"
    real.write_bytes(FILES["baseline.css"])
    target.unlink()
    target.symlink_to(real)


def fault_bad_toml(root: Path) -> None:
    edit_pin(root, "[files]", "[files")


def fault_missing_version(root: Path) -> None:
    edit_pin(root, 'version = "1.2.1"\n', "")


def fault_extra_key(root: Path) -> None:
    edit_pin(root, 'version = "1.2.1"\n', 'version = "1.2.1"\nsource = "x"\n')


def fault_bad_version(root: Path) -> None:
    edit_pin(root, 'version = "1.2.1"', 'version = "1.2"')


def fault_malformed_digest(root: Path) -> None:
    edit_pin(root, digest(FILES["baseline.css"]), "abc")


def fault_path_outside(root: Path) -> None:
    edit_pin(root, '"assets/baseline/baseline.css"', '"assets/../baseline.css"')


def fault_digest_not_published(root: Path) -> None:
    new = b"a { color: blue; }\n"
    (copied(root) / "baseline.css").write_bytes(new)
    edit_pin(root, digest(FILES["baseline.css"]), digest(new))


def fault_rail_js_dropped(root: Path) -> None:
    (copied(root) / "rail.js").unlink()
    edit_pin(root, f'"assets/baseline/rail.js" = "{digest(FILES["rail.js"])}"\n', "")


def fault_scheme_js_dropped(root: Path) -> None:
    (copied(root) / "scheme.js").unlink()
    edit_pin(root, f'"assets/baseline/scheme.js" = "{digest(FILES["scheme.js"])}"\n', "")


def fault_tool_edited(root: Path) -> None:
    (root / TOOL_KEY).write_bytes(TOOL + b"# edited\n")


def fault_tool_deleted(root: Path) -> None:
    (root / TOOL_KEY).unlink()


def fault_tool_unpinned(root: Path) -> None:
    edit_pin(root, f'"{TOOL_KEY}" = "{digest(TOOL)}"\n', "")


def fault_tool_digest_not_published(root: Path) -> None:
    new = TOOL + b"# other\n"
    (root / TOOL_KEY).write_bytes(new)
    edit_pin(root, digest(TOOL), digest(new))


def fault_tool_served(root: Path) -> None:
    (root / "site" / "check_palette.py").write_bytes(TOOL)


def fault_other_baseline_key(root: Path) -> None:
    edit_pin(root, f'"{TOOL_KEY}" = "{digest(TOOL)}"\n',
             f'"{TOOL_KEY}" = "{digest(TOOL)}"\n".baseline/other.py" = "{digest(TOOL)}"\n')


def fault_promoted_base(root: Path) -> None:
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")


def fault_missing_pin(root: Path) -> None:
    (root / ".baseline" / "pin.toml").unlink()


def fault_missing_sums(root: Path) -> None:
    (root / ".baseline" / "SHA256SUMS").unlink()


def fault_unlistable(root: Path) -> None:
    os.chmod(copied(root) / "fonts", 0)


CASES = [
    ("clean tree passes", None, 0),
    ("1 flipped byte", fault_flip_byte, 1),
    ("1 extra file", fault_extra_file, 1),
    ("1 missing file", fault_missing_file, 1),
    ("1 missing pin entry", fault_missing_entry, 1),
    ("a symlink in place of a file", fault_symlink, 1),
    ("a digest the published sums do not list", fault_digest_not_published, 1),
    ("rail.js dropped from the copy and the pin", fault_rail_js_dropped, 1),
    ("scheme.js dropped from the copy and the pin", fault_scheme_js_dropped, 1),
    ("the pinned build tool edited", fault_tool_edited, 1),
    ("the pinned build tool deleted", fault_tool_deleted, 1),
    ("the build tool's pin entry removed", fault_tool_unpinned, 1),
    ("the build tool pinned with a digest the published sums do not list", fault_tool_digest_not_published, 1),
    ("a check_palette.py under the served site/ tree", fault_tool_served, 1),
    ("malformed TOML", fault_bad_toml, 3),
    ("no version", fault_missing_version, 3),
    ("a key outside the README format", fault_extra_key, 3),
    ("a version that is not X.Y.Z", fault_bad_version, 3),
    ("a malformed digest", fault_malformed_digest, 3),
    ("a path outside assets/baseline/", fault_path_outside, 3),
    ("an unknown .baseline/ key", fault_other_baseline_key, 3),
    ("the base path moved to / with the files still under draft/", fault_promoted_base, 3),
    ("the pin is missing", fault_missing_pin, 3),
    ("SHA256SUMS is missing", fault_missing_sums, 3),
]


def run_copy(root: Path, package: dict[str, bytes]) -> subprocess.CompletedProcess:
    """Run tools/copy-baseline.py in root on a version folder 1.2.1 that holds package and its SHA256SUMS."""
    (root / "tools").mkdir()
    shutil.copyfile(COPY_TOOL, root / "tools" / COPY_TOOL.name)
    (root / "site-src").mkdir()
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")
    for name, data in package.items():
        (root / "1.2.1" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "1.2.1" / name).write_bytes(data)
    sums = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(package.items()))
    (root / "1.2.1" / "SHA256SUMS").write_text(sums, encoding="utf-8")
    command = [sys.executable, "-I", str(root / "tools" / COPY_TOOL.name), "--from", str(root / "1.2.1"),
               "--sums-sha256", digest(sums.encode()), "--archive-sha256", "0" * 64]
    return subprocess.run(command, capture_output=True, text=True)


def copy_problems() -> list[str]:
    """copy-baseline pins and copies the build tool, counts it, and checks for it before replacing a file."""
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, {**FILES, "tools/check_palette.py": TOOL})
        pin = (root / ".baseline" / "pin.toml").read_text(encoding="utf-8") if result.returncode == 0 else ""
        if f'"{TOOL_KEY}" = "{digest(TOOL)}"\n' not in pin or (root / TOOL_KEY).read_bytes() != TOOL:
            problems.append(f"copy-baseline: the build tool is not copied to {TOOL_KEY} and pinned "
                            f"(exit {result.returncode})")
        if f"copied {len(FILES) + 1} files " not in result.stdout:
            problems.append(f"copy-baseline: the count of copied files leaves out the build tool: "
                            f"{result.stdout.strip()!r}")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        served = root / "site" / "assets" / "baseline" / "served-before.css"
        served.parent.mkdir(parents=True)
        served.write_bytes(b"a { color: red; }\n")
        result = run_copy(root, dict(FILES))
        if result.returncode != 1 or not served.is_file():
            kept = "keeps" if served.is_file() else "replaces"
            problems.append(f"copy-baseline: a version without the build tool exits {result.returncode} "
                            f"and {kept} the served files; expected 1 and keeps")
    return problems


def pin_header_problems() -> list[str]:
    """The pin's header, as tools/copy-baseline.py writes it and as committed, gives each key's base."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, {**FILES, "tools/check_palette.py": TOOL})
        if result.returncode != 0:
            return [f"the pin header: copy-baseline exit {result.returncode}: {result.stderr.strip()[:200]}"]
        written = (root / ".baseline" / "pin.toml").read_text(encoding="utf-8")
    committed = (REPO_ROOT / ".baseline" / "pin.toml").read_text(encoding="utf-8")

    def header(text: str) -> str:
        lines = text.splitlines()
        return " ".join(lines[:next(i for i, line in enumerate(lines) if line.startswith("# Source:"))])

    problems = []
    if header(written) != header(committed):
        problems.append("the pin header: the committed .baseline/pin.toml header is not copy-baseline's")
    for statement in ("assets/baseline/ are relative to the site's output root",
                      f"{TOOL_KEY} is relative to the repository root"):
        if statement not in header(written).replace("# ", ""):
            problems.append(f"the pin header does not say {statement!r}")
    return problems


def main() -> int:
    failures: list[str] = pin_header_problems() + copy_problems()
    ran = 4
    for name, fault, expected in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            build(root)
            if fault:
                fault(root)
            code = run(root)
            ran += 1
            if code != expected:
                failures.append(f"{name}: exit {code}, expected {expected}")
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            build(root)
            fault_unlistable(root)
            try:
                code = run(root)
            finally:
                os.chmod(copied(root) / "fonts", 0o755)
            ran += 1
            if code != 3:
                failures.append(f"an unlistable folder: exit {code}, expected 3")
    code = run(REPO_ROOT)
    ran += 1
    if code != 0:
        failures.append(f"this repository: exit {code}, expected 0")
    if failures:
        print("test-baseline-pin: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-baseline-pin: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
