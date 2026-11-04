#!/usr/bin/env python3
"""Tests for tools/check-baseline-pin.py: each check fails on a deliberate fault.

Each case builds a small pinned tree in a temporary folder (under $TMPDIR),
with the version's README and specification under ``.baseline/`` and a root
``NOTICE.md``, applies 1 fault, runs the gate on that tree as a separate
process and asserts its exit code, and for some cases a line of its output.
The last case runs the gate on this repository. The first 9 cases run
``tools/copy-baseline.py`` on a small version folder and assert that the pin
header it writes, and the committed one, give each key's base; that it copies
and pins the build tool and counts it among the copied files; that it copies
the README and the specification to ``.baseline/`` without pinning them; and
that a version without the build tool, the README or the specification, or
whose README names another version or lacks its step 7 NOTICE entry, exits 1
before any served file is replaced.
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
# The rest of the files the gate requires in the pin (REQUIRED), from the README's runtime and licence set:
# among them 5 of its 6 scripts (this site leaves out matrix.js, by the owner's decision).
for _name in ("palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js", "scheme.js", "LICENSE",
              "NOTICE.md"):
    FILES[_name] = f"/* {_name} */\n".encode()
# The pinned build tool, kept at .baseline/check_palette.py and never served.
TOOL = b"# check_palette.py\n"
TOOL_KEY = ".baseline/check_palette.py"
# The version's documents, copied to .baseline/ and not pinned: the README's heading names the version, and its
# step 7 prescribes the NOTICE entry; NOTICE_TEXT carries that entry for 1.2.1.
README = (b"# Baseline 1.2.1: x\n\n7. Add this entry to the repository's NOTICE:\n\n"
          b"   > Site template: baseline <version>, with 2 exceptions.\n\n8. Updates.\n")
DOCS = {"README.md": README, "SPECIFICATION.md": b"# specification\n"}
NOTICE_TEXT = ("# Notice\n\n## Site template\n\nSite template: baseline 1.2.1, with 2 exceptions.\n\n"
               "## Other\n\nx\n")


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
    sums += "".join(f"{digest(data)}  {name}\n" for name, data in DOCS.items())
    (root / ".baseline").mkdir()
    (root / ".baseline" / "SHA256SUMS").write_text(sums, encoding="utf-8")
    (root / TOOL_KEY).write_bytes(TOOL)
    for name, data in DOCS.items():
        (root / ".baseline" / name).write_bytes(data)
    (root / "NOTICE.md").write_text(NOTICE_TEXT, encoding="utf-8")
    lines = ["# comment", 'version = "1.2.1"', "", "[files]"]
    lines += [f'"assets/baseline/{name}" = "{digest(data)}"' for name, data in sorted(FILES.items())]
    lines += [f'"{TOOL_KEY}" = "{digest(TOOL)}"']
    (root / ".baseline" / "pin.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "site-src").mkdir()
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/draft/"}), encoding="utf-8")


def run_gate(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(GATE), str(root)], capture_output=True, text=True)


def run(root: Path) -> int:
    return run_gate(root).returncode


def edit_file(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def edit_pin(root: Path, old: str, new: str) -> None:
    edit_file(root / ".baseline" / "pin.toml", old, new)


def edit_readme(root: Path, old: bytes, new: bytes) -> None:
    """Change the copied README and its SHA256SUMS digest together, so only the README's text is at fault."""
    assert old in README, old
    (root / ".baseline" / "README.md").write_bytes(README.replace(old, new, 1))
    edit_file(root / ".baseline" / "SHA256SUMS", digest(README), digest(README.replace(old, new, 1)))


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


def fault_other_version(root: Path) -> None:
    # NOTICE.md moves with the pin, so only the README's heading can tell that SHA256SUMS belongs to 1.2.1.
    edit_pin(root, 'version = "1.2.1"', 'version = "1.2.0"')
    edit_file(root / "NOTICE.md", "baseline 1.2.1", "baseline 1.2.0")


def fault_readme_unlisted(root: Path) -> None:
    edit_file(root / ".baseline" / "SHA256SUMS", f"{digest(README)}  README.md\n", "")


def fault_readme_edited(root: Path) -> None:
    (root / ".baseline" / "README.md").write_bytes(README + b"x\n")


def fault_readme_missing(root: Path) -> None:
    (root / ".baseline" / "README.md").unlink()


def fault_readme_no_heading(root: Path) -> None:
    edit_readme(root, b"# Baseline 1.2.1: x", b"# The template 1.2.1: x")


def fault_readme_no_entry(root: Path) -> None:
    edit_readme(root, b"Add this entry to", b"Add an entry to")


def fault_spec_edited(root: Path) -> None:
    (root / ".baseline" / "SPECIFICATION.md").write_bytes(DOCS["SPECIFICATION.md"] + b"x\n")


def fault_spec_missing(root: Path) -> None:
    (root / ".baseline" / "SPECIFICATION.md").unlink()


def fault_notice_three_exceptions(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions", "with 3 exceptions")


def fault_notice_other_version(root: Path) -> None:
    edit_file(root / "NOTICE.md", "baseline 1.2.1", "baseline 1.2.0")


def fault_notice_no_section(root: Path) -> None:
    edit_file(root / "NOTICE.md", "## Site template\n", "## Template\n")


def fault_notice_second_paragraph(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions.\n", "with 2 exceptions.\n\nAnd more.\n")


def fault_notice_missing(root: Path) -> None:
    (root / "NOTICE.md").unlink()


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
    ("the pin moved to another version, NOTICE.md with it", fault_other_version, 1, "different versions"),
    ("the README not listed in SHA256SUMS", fault_readme_unlisted, 1),
    ("the copied README edited", fault_readme_edited, 1),
    ("the copied specification edited", fault_spec_edited, 1),
    ("a NOTICE entry with 3 exceptions", fault_notice_three_exceptions, 1, "NOTICE.md's '## Site template'"),
    ("a NOTICE entry naming another version", fault_notice_other_version, 1),
    ("no Site template section in NOTICE.md", fault_notice_no_section, 1),
    ("a second paragraph in the Site template section", fault_notice_second_paragraph, 1),
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
    ("the copied README is missing", fault_readme_missing, 3),
    ("a README without its version heading", fault_readme_no_heading, 3),
    ("a README without its step 7 NOTICE entry", fault_readme_no_entry, 3),
    ("the copied specification is missing", fault_spec_missing, 3),
    ("NOTICE.md is missing", fault_notice_missing, 3),
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


PACKAGE = {**FILES, **DOCS, "tools/check_palette.py": TOOL}
# Versions copy-baseline refuses (exit 1) before it replaces a served file: each changes PACKAGE in place.
COPY_REFUSALS = [
    ("a version without the build tool", lambda package: package.pop("tools/check_palette.py")),
    ("a version without README.md", lambda package: package.pop("README.md")),
    ("a version without SPECIFICATION.md", lambda package: package.pop("SPECIFICATION.md")),
    ("a README whose heading names another version",
        lambda package: package.update({"README.md": README.replace(b"Baseline 1.2.1", b"Baseline 1.2.0")})),
    ("a README without its step 7 NOTICE entry",
        lambda package: package.update({"README.md": README.replace(b"   > ", b"")})),
]


def copy_problems() -> list[str]:
    """copy-baseline pins and copies the build tool, counts it, copies the documents unpinned, and checks for each
    and for the README's version and NOTICE entry before replacing a file."""
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, dict(PACKAGE))
        pin = (root / ".baseline" / "pin.toml").read_text(encoding="utf-8") if result.returncode == 0 else ""
        if f'"{TOOL_KEY}" = "{digest(TOOL)}"\n' not in pin or (root / TOOL_KEY).read_bytes() != TOOL:
            problems.append(f"copy-baseline: the build tool is not copied to {TOOL_KEY} and pinned "
                            f"(exit {result.returncode})")
        if f"copied {len(FILES) + 1} files " not in result.stdout:
            problems.append(f"copy-baseline: the count of copied files leaves out the build tool: "
                            f"{result.stdout.strip()!r}")
        documents = root / ".baseline"
        if (not pin or any(not (documents / name).is_file() or (documents / name).read_bytes() != data
                           or name in pin for name, data in DOCS.items())):
            problems.append(f"copy-baseline: the documents are not copied to .baseline/ unpinned "
                            f"(exit {result.returncode})")
    for name, change in COPY_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            package = dict(PACKAGE)
            change(package)
            result = run_copy(root, package)
            if result.returncode != 1 or not served.is_file():
                kept = "keeps" if served.is_file() else "replaces"
                problems.append(f"copy-baseline: {name} exits {result.returncode} "
                                f"and {kept} the served files; expected 1 and keeps")
    return problems


def pin_header_problems() -> list[str]:
    """The pin's header, as tools/copy-baseline.py writes it and as committed, gives each key's base."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, dict(PACKAGE))
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
    ran = 4 + len(COPY_REFUSALS)
    for name, fault, expected, *needles in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            build(root)
            if fault:
                fault(root)
            result = run_gate(root)
            ran += 1
            if result.returncode != expected:
                failures.append(f"{name}: exit {result.returncode}, expected {expected}")
            elif any(needle not in result.stdout for needle in needles):
                failures.append(f"{name}: the output does not say {needles}: {result.stdout.strip()[:200]!r}")
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
