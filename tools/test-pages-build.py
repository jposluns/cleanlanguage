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
which exits 3 on any other version, 3.7 or later. It reads each workflow
under .github/workflows whose name ends in .yml (any other .yml or .yaml file
under .github fails tools/test-workflow-launch-isolation.py instead) with
PyYAML's safe loader, finds every job with a step whose
run text names a tool in GATE_RUNNERS, and fails if there is none, or if such
a job has an if: or continue-on-error, has a run step before its checkout, or
does not run exactly VERSION_RUN, with shell: bash and no key but name, shell
and run, as its first step after checkout. On fixture workflows, it checks
that this passes GATED and fails on each case in WORKFLOW_CASES: a version
step with if:, continue-on-error or another key, a job with if: or
continue-on-error, a missing version step, a new workflow that runs the gate
without it, and no workflow that runs the gate. It runs
tools/check-python-version.py in a temporary tree
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

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "pages-build.sh"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
INLINE_GATE = REPO_ROOT / "tools" / "check-inline-code.py"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
VERSION_TOOL = REPO_ROOT / "tools" / "check-python-version.py"
# The tools that run tools/check-inline-code.py, directly or through a page check. A job that runs one
# runs VERSION_RUN as its first step after checkout, so a runner whose python3 is not the release that
# .python-version names fails there.
GATE_RUNNERS = ("tools/check-inline-code.py", "tools/check-install-page.py", "tools/check-instructions-page.py",
                "tools/pages-build.sh", "tools/release-dry-run.sh")
VERSION_RUN = "python3 -I tools/check-python-version.py"
# Fixture workflows for WORKFLOW_CASES. GATED runs the gate after the version step and passes the check.
JOB = "name: Gate\non:\n  pull_request:\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n"
CHECKOUT = ("      - name: Check out repository\n"
            "        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0\n")
VERSION_STEP = ("      - name: Check that python3 is the release that .python-version names\n"
                "        shell: bash\n"
                f"        run: {VERSION_RUN}\n")
GATE_STEP = ("      - name: Check every HTML page under site/ for inline code\n"
             "        shell: bash\n"
             "        run: python3 -I tools/check-inline-code.py\n")
GATED = JOB + CHECKOUT + VERSION_STEP + GATE_STEP
UNGATED = JOB + CHECKOUT + GATE_STEP
# (case, workflow files and their text, text the refusal must hold): the workflow check must refuse each
WORKFLOW_CASES = [
    ("a version step with if:", {"gate.yml": GATED.replace(VERSION_STEP, VERSION_STEP + "        if: false\n")},
     "/gate.yml "),
    ("a version step with continue-on-error",
     {"gate.yml": GATED.replace(VERSION_STEP, VERSION_STEP + "        continue-on-error: true\n")}, "/gate.yml "),
    ("a version step with another key",
     {"gate.yml": GATED.replace(VERSION_STEP, VERSION_STEP + "        working-directory: site\n")}, "/gate.yml "),
    ("a job with if:", {"gate.yml": GATED.replace("    runs-on:", "    if: false\n    runs-on:")}, "/gate.yml "),
    ("a job with continue-on-error",
     {"gate.yml": GATED.replace("    runs-on:", "    continue-on-error: true\n    runs-on:")}, "/gate.yml "),
    ("no version step", {"gate.yml": UNGATED}, "/gate.yml "),
    ("a new workflow that runs the gate without the version step", {"gate.yml": GATED, "new-gate.yml": UNGATED},
     "/new-gate.yml "),
    ("no workflow that runs the gate", {}, "no workflow "),
]
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


def version_step_problems(workflows: Path) -> tuple[list[str], int]:
    """Each job under workflows that runs a tool in GATE_RUNNERS without the version step, and the
    number of workflows that run one; no such workflow is a problem too."""
    problems = []
    found = 0
    for path in sorted(workflows.glob("*.yml")):
        name = f".github/workflows/{path.name}"
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            problems.append(f"{name} could not be read: {error}")
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        if not isinstance(jobs, dict):
            problems.append(f"{name} has no jobs mapping")
            continue
        runs_gate = False
        for job_id, job in jobs.items():
            steps = job.get("steps") if isinstance(job, dict) else None
            steps = [s if isinstance(s, dict) else {} for s in steps] if isinstance(steps, list) else []
            runs = [s["run"] for s in steps if isinstance(s.get("run"), str)]
            if not any(tool in text for text in runs for tool in GATE_RUNNERS):
                continue
            runs_gate = True
            checkout = next((i for i, s in enumerate(steps)
                             if str(s.get("uses", "")).startswith("actions/checkout@")), None)
            step = steps[checkout + 1] if checkout is not None and checkout + 1 < len(steps) else {}
            if ("if" in job or "continue-on-error" in job or any("run" in s for s in steps[:checkout])
                    or step.get("run") != VERSION_RUN or step.get("shell") != "bash"
                    or not set(step) <= {"name", "shell", "run"}):
                problems.append(f"{name} job {job_id} runs the gate but has an if: or continue-on-error, a run "
                                f"step before checkout, or a first step after checkout other than exactly "
                                f"{VERSION_RUN} with shell: bash and no key but name, shell and run")
        found += runs_gate
    if not found:
        problems.append(f"no workflow under .github/workflows runs a step that names {', '.join(GATE_RUNNERS)}")
    return problems, found


def workflow_case_problems() -> list[str]:
    """GATED if version_step_problems refuses it, and each case in WORKFLOW_CASES that it does not refuse."""
    problems = []
    for case, files, want in [("GATED", {"gate.yml": GATED}, None)] + WORKFLOW_CASES:
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in files.items():
                (Path(tmp) / name).write_text(text, encoding="utf-8")
            refused, gated = version_step_problems(Path(tmp))
            if (refused or gated != 1) if want is None else not any(want in problem for problem in refused):
                problems.append(f"workflow case {case}: {gated} gated workflows, refused with {refused}")
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
    step_problems, gated = version_step_problems(WORKFLOWS)
    failures += step_problems
    failures += workflow_case_problems()
    failures += version_tool_problems()

    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print(
        f"pages-build.sh runs all {len(EXPECTED)} gates in order, fails when one exits 1 or 3, "
        f"and fails with exit 3 when one is missing ({1 + 3 * len(EXPECTED)} cases); "
        ".python-version names a version that tools/check-inline-code.py supports, "
        f"the {gated} workflows that run the gate check it in their first step after checkout, "
        f"the workflow check refuses {len(WORKFLOW_CASES)} cases, and "
        f"tools/check-python-version.py passes {len(VERSION_CASES)} cases."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
