#!/usr/bin/env python3
"""Tests for tools/pages-build.sh: it runs every listed gate and fails when one exits 1 or 3.

Each case copies the build script into a temporary tree whose tools/ folder
holds a stub in place of each gate. A stub records its name and arguments and
exits with the code the case sets. The script runs as a separate process with
bash, as the build command in site/README.md runs it, but against the stubs.

EXPECTED is the gate list the owner decided for the Pages build command, kept
here apart from the script, so a gate dropped from the script, a changed
argument (build-site.py without --check), a reordered list, or a skipped
missing gate fails a case. A failing gate stub exits 1 or 3 only, so a case
fails if the script masks either code, but a failure the script masks only
for another exit code passes every case. The cases do not test the script's
Python version check. Adding a gate to the script means adding it here too,
which a reviewer sees.

It also reads .python-version at the repository root, which names the Python
release for the Pages build (site/README.md), and fails if the file is missing
or names a version outside SUPPORTED_PYTHONS in tools/check-inline-code.py,
which exits 3 on any other version. It fails too if a workflow in
VERSION_CHECK_WORKFLOWS does not run tools/check-python-version.py, with shell:
bash, before its first other run step. It runs that tool in a temporary tree
against each .python-version in VERSION_CASES: one that names this interpreter,
one that names another release, a missing file and two malformed files.

Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "pages-build.sh"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
INLINE_GATE = REPO_ROOT / "tools" / "check-inline-code.py"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
VERSION_TOOL = REPO_ROOT / "tools" / "check-python-version.py"
# The workflows that run tools/check-inline-code.py, directly or through a page check. Each runs
# tools/check-python-version.py before its first other run step, so a runner whose python3 is not
# the release that .python-version names fails there.
VERSION_CHECK_WORKFLOWS = ("site-hardening.yml", "install-page.yml", "portable-text-sync.yml", "pages-build.yml",
                           "release-dry-run.yml")
VERSION_STEP = re.compile(
    r"\n      - name: [^\n]+\n        shell: bash\n        run: python3 -I tools/check-python-version\.py\n"
)
FIRST_RUN = re.compile(r"\n      (?:- |  )run: ")
RUNNING = platform.python_version()
OTHER = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2] + 1}"
# (case, .python-version text or None for no file, wanted exit, text the one output line must hold)
VERSION_CASES = [
    ("a .python-version that names this interpreter", f"{RUNNING}\n", 0, [RUNNING]),
    ("a .python-version that names another release", f"{OTHER}\n", 3, [RUNNING, OTHER]),
    ("no .python-version", None, 3, [".python-version"]),
    ("a .python-version that names no patch release", f"{sys.version_info[0]}.{sys.version_info[1]}\n", 3,
     [".python-version"]),
    ("a .python-version of two lines", f"{RUNNING}\n{RUNNING}\n", 3, [".python-version"]),
]

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


def python_version_problem() -> str | None:
    """The problem with .python-version, or None when it names a version check-inline-code.py supports."""
    spec = importlib.util.spec_from_file_location("check_inline_code", INLINE_GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    try:
        text = PYTHON_VERSION_FILE.read_text(encoding="utf-8")
    except OSError as error:
        return f".python-version could not be read: {error}"
    match = re.fullmatch(r"(\d+)\.(\d+)(\.\d+)?\n?", text)
    if not match:
        return f".python-version holds {text!r}, not one Python version such as 3.14.4"
    if (int(match[1]), int(match[2])) not in gate.SUPPORTED_PYTHONS:
        return f".python-version names {text.strip()}, outside SUPPORTED_PYTHONS {gate.SUPPORTED_PYTHONS}"
    return None


def version_step_problems() -> list[str]:
    """Each workflow in VERSION_CHECK_WORKFLOWS whose first run step is not the version check."""
    problems = []
    for name in VERSION_CHECK_WORKFLOWS:
        try:
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
        except OSError as error:
            problems.append(f".github/workflows/{name} could not be read: {error}")
            continue
        step = VERSION_STEP.search(text)
        run = FIRST_RUN.search(text)
        if step is None or run is None or not step.start() < run.start() < step.end():
            problems.append(f".github/workflows/{name} does not run python3 -I tools/check-python-version.py, "
                            "with shell: bash, before its first other run step")
    return problems


def version_tool_problems() -> list[str]:
    """Each case in VERSION_CASES where tools/check-python-version.py does not exit as wanted with one line."""
    problems = []
    for name, text, want, needles in VERSION_CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir()
            try:
                shutil.copy2(VERSION_TOOL, root / "tools" / VERSION_TOOL.name)
            except OSError as error:
                problems.append(f"check-python-version.py with {name}: the tool could not be copied: {error}")
                continue
            if text is not None:
                (root / ".python-version").write_text(text, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-I", str(root / "tools" / VERSION_TOOL.name)], capture_output=True, text=True
            )
            output = result.stdout + result.stderr
            if result.returncode != want or output.count("\n") != 1 or not all(n in output for n in needles):
                problems.append(f"check-python-version.py with {name}: exit {result.returncode}, wanted exit "
                                f"{want} and one line naming {', '.join(needles)}: {output.strip()[:300]}")
    return problems


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
    problem = python_version_problem()
    if problem:
        failures.append(problem)
    failures += version_step_problems()
    failures += version_tool_problems()

    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print(
        f"pages-build.sh runs all {len(EXPECTED)} gates in order, fails when one exits 1 or 3, "
        f"and fails with exit 3 when one is missing ({1 + 3 * len(EXPECTED)} cases); "
        ".python-version names a version that tools/check-inline-code.py supports, "
        f"{len(VERSION_CHECK_WORKFLOWS)} workflows check it before their first other run step, and "
        f"tools/check-python-version.py passes {len(VERSION_CASES)} cases."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
