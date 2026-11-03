#!/usr/bin/env python3
"""Tests for tools/pages-build.sh: it runs every listed gate and fails when one fails.

Each case copies the build script into a temporary tree whose tools/ folder
holds a stub in place of each gate. A stub records its name and arguments and
exits with the code the case sets. The script runs as a separate process with
bash, the command the Cloudflare Pages dashboard runs, but against the stubs.

EXPECTED is the gate list the owner decided for the Pages build command, kept
here apart from the script, so a gate dropped from the script, a changed
argument (build-site.py without --check), a reordered list, or a skipped
missing gate fails a case. A failing gate stub exits 1 or 3 only, so a case
fails if the script masks either code, but a failure the script masks only
for another exit code passes every case. The cases do not test the script's
Python version check. Adding a gate to the script means adding it here too,
which a reviewer sees.

Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "pages-build.sh"

EXPECTED = [
    ["tools/check-baseline-pin.py"],
    ["tools/check-security-txt.py"],
    ["tools/check-headers.py"],
    ["tools/check-inline-code.py"],
    ["tools/build-site.py", "--check"],
]

STUB = """import sys
from pathlib import Path
here = Path(__file__).resolve()
with open(here.parent / "calls.log", "a", encoding="utf-8") as log:
    log.write(" ".join(["tools/" + here.name] + sys.argv[1:]) + "\\n")
code = here.with_suffix(".exit")
sys.exit(int(code.read_text()) if code.exists() else 0)
"""


def build(root: Path) -> None:
    (root / "tools").mkdir()
    shutil.copy2(SCRIPT, root / "tools" / "pages-build.sh")
    for gate in EXPECTED:
        (root / gate[0]).write_text(STUB, encoding="utf-8")


def run(root: Path) -> tuple[int, list[str], str]:
    result = subprocess.run(
        ["bash", str(root / "tools" / "pages-build.sh")], capture_output=True, text=True
    )
    log = root / "tools" / "calls.log"
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result.returncode, calls, result.stdout + result.stderr


def main() -> int:
    failures: list[str] = []
    expected_calls = [" ".join(gate) for gate in EXPECTED]

    def case(name: str, fault, want_code: int, want_calls: list[str]) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root)
            fault(root)
            code, calls, output = run(root)
            if code != want_code or calls != want_calls:
                failures.append(
                    f"{name}: exit {code}, calls {calls}, wanted exit {want_code}, "
                    f"calls {want_calls}\n{output}"
                )

    case("every gate passes", lambda root: None, 0, expected_calls)
    for index, gate in enumerate(EXPECTED):
        for code in (1, 3):
            case(
                f"{gate[0]} exits {code}",
                lambda root, gate=gate, code=code: (root / gate[0]).with_suffix(".exit").write_text(str(code)),
                code,
                expected_calls[: index + 1],
            )
        case(
            f"{gate[0]} is missing",
            lambda root, gate=gate: os.remove(root / gate[0]),
            3,
            expected_calls[:index],
        )

    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print(
        f"pages-build.sh runs all {len(EXPECTED)} gates in order and fails on each "
        f"gate's failure or absence ({1 + 3 * len(EXPECTED)} cases)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
