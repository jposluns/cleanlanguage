#!/usr/bin/env python3
"""Check that every `uses` in the workflows is pinned to a full commit.

Threat model: honest drift. A `uses` that names a tag or a branch runs
whatever that name points at when the job starts, so a moved tag changes what
the workflow runs without any change in this repository. The gate guards
against an honest author who writes such a reference by mistake; deliberate
evasion is a named residual.

The rule: each .github/workflows/*.yml file is loaded with UniqueKeyLoader,
taken from tools/test-workflow-launch-isolation.py by its explicit path, and
every value of a mapping key `uses`, at any depth, so a step `uses`, a job
`uses` and one that an alias or a merge key brings in, must be text of the
form `owner/repo[/path]@<sha>`, where `<sha>` is exactly 40 lower-case hex
digits. The owner starts with a letter or digit and holds only letters, digits
and hyphens; the repo and each path part hold only letters, digits, `_`, `.`
and `-` and are not `.` or `..`. Anything else is a finding: a tag or a
branch, a short, long or upper-case hex ref, a local `./` or `../` path, any
`docker://` value, an expression such as `${{ matrix.action }}`, and a `uses`
that is not text. A workflow that cannot be read as UTF-8, one whose loading
raises any exception, such as a duplicate key, and a recursive node are
findings, and an empty .github/workflows/*.yml listing is a failure.
tools/test-workflow-launch-isolation.py separately refuses local actions and
local reusable workflows, and any .yml or .yaml file under .github outside
.github/workflows/*.yml, such as an action.yml.

Residuals:

- deliberate evasion of any kind, including an edit to this gate;
- files outside .github/workflows/*.yml, which the launch scan refuses;
- a 40-hex commit that is the commit of a tag, or a commit in a fork, is
  accepted; the gate does not check that the commit exists or which repository
  holds it;
- GitHub Actions' own YAML reading is not checked, so a key that GitHub
  Actions reads as `uses` but PyYAML builds as other text passes;
- what a pinned action does, including the actions and images it fetches in
  turn.

Usage: python3 -I tools/test-action-pins.py
Exit status: 0 when every check passes, 1 on any finding or failure.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
SCAN = Path(__file__).resolve().parent / "test-workflow-launch-isolation.py"

SEGMENT = r"(?!\.\.?(?:/|@))[A-Za-z0-9_.-]+"
PIN = re.compile(rf"[A-Za-z0-9][A-Za-z0-9-]*/{SEGMENT}(?:/{SEGMENT})*@[0-9a-f]{{40}}")


def load_scan():
    """Load the launch scan by its explicit path, leaving the search path unchanged."""
    spec = importlib.util.spec_from_file_location("workflow_launch_isolation", SCAN)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SCAN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_uses(value) -> str | None:
    """Describe why one `uses` value is refused, or return None."""
    if not isinstance(value, str):
        return f"{value!r} is not text"
    if not PIN.fullmatch(value):
        return f"{value!r} is not owner/repo[/path]@<40 lower-case hex>"
    return None


def walk(node, where: str, found: list[str], checked: list[str], seen: tuple = ()) -> None:
    """Check every `uses` key in node, at any depth; record each in checked."""
    if isinstance(node, (dict, list)):
        if any(node is item for item in seen):
            found.append(f"{where}: a recursive node")
            return
        seen = seen + (node,)
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses":
                checked.append(where)
                reason = check_uses(value)
                if reason:
                    found.append(f"{where}.uses: {reason}")
            walk(value, f"{where}.{key}", found, checked, seen)
    elif isinstance(node, list):
        for n, item in enumerate(node):
            walk(item, f"{where}[{n}]", found, checked, seen)


def check_text(text: str, label: str, loader) -> tuple[list[str], int]:
    """Return the findings for one workflow's text, and its number of uses."""
    try:
        doc = yaml.load(text, Loader=loader)
    except Exception as exc:
        first = f"{type(exc).__name__}: {exc}".splitlines()[0]
        return [f"{label}: cannot be parsed as YAML ({first})"], 0
    found: list[str] = []
    checked: list[str] = []
    walk(doc, "", found, checked)
    return [f"{label}: {reason.lstrip('.')}" for reason in found], len(checked)


def scan_tree(root: Path, loader) -> tuple[list[str], int]:
    """Check every root/.github/workflows/*.yml; return (findings, number of uses)."""
    files = sorted((root / ".github" / "workflows").glob("*.yml"))
    if not files:
        return [f"no workflow found in {root / '.github' / 'workflows'}"], 0
    findings: list[str] = []
    count = 0
    for path in files:
        label = str(path.relative_to(root))
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{label}: cannot be read as UTF-8 ({exc})")
            continue
        found, uses = check_text(text, label, loader)
        findings += found
        count += uses
    return findings, count


# ---------------------------------------------------------------- self-tests

SHA = "11d5960a326750d5838078e36cf38b85af677262"


def step(uses: str) -> str:
    return f"jobs:\n  a:\n    steps:\n      - uses: {uses}\n"


# Workflow text that must be refused (True) or must pass (False).
CASES = [
    (step("actions/checkout@v4"), True),
    (step("actions/checkout@main"), True),
    (step("docker://alpine"), True),
    (step("docker://alpine@sha256:" + "0" * 64), True),
    (step(f"docker://alpine@{SHA}"), True),
    (step("actions/checkout@" + SHA[:39]), True),
    (step("actions/checkout@" + SHA + "0"), True),
    (step("actions/checkout@" + SHA.upper()), True),
    (step("./local"), True),
    (step(f"./local@{SHA}"), True),
    (step(f"../x/y@{SHA}"), True),
    (step(f"owner/../w.yml@{SHA}"), True),
    (step(f"owner/repo/./w.yml@{SHA}"), True),
    (step(f"actions@{SHA}"), True),
    (step(f"-owner/repo@{SHA}"), True),
    (step(f"'actions/checkout@{SHA} '"), True),
    (step(f'"actions/checkout@{SHA}\\n"'), True),
    (step("'${{ matrix.action }}'"), True),
    (step("5"), True),
    (step("[a]"), True),
    (step("~"), True),
    ("jobs:\n  a:\n    uses: owner/repo/.github/workflows/w.yml@v1\n", True),
    ("jobs:\n  a:\n    uses: ./.github/workflows/w.yml\n", True),
    ("jobs:\n  a:\n    strategy:\n      matrix:\n        include:\n          - uses: actions/checkout@v4\n", True),
    ("jobs:\n  a:\n    env: {V: &u actions/checkout@v4}\n    steps:\n      - uses: *u\n", True),
    ("x: &s {name: n}\njobs:\n  a:\n    steps:\n      - <<: [*s, {uses: actions/checkout@v4}]\n", True),
    ("jobs:\n  a:\n    steps: &x\n      - *x\n", True),
    (f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA}\n        uses: actions/checkout@{SHA}\n", True),
    (step(f"actions/checkout@{SHA}"), False),
    (step(f"actions/checkout@{SHA} # v4.4.0"), False),
    (f"jobs:\n  a:\n    uses: owner/repo/.github/workflows/w.yml@{SHA}\n", False),
    (f"jobs:\n  a:\n    uses: octo-org/.github/.github/workflows/w.yml@{SHA}\n", False),
    (f"jobs:\n  a:\n    steps:\n      - uses: owner/repo.js/sub_dir/x-y@{SHA}\n", False),
    ("jobs:\n  a:\n    steps:\n      - run: echo uses actions/checkout@v4\n", False),
]


def self_test(loader) -> list[str]:
    errors: list[str] = []
    for text, refused in CASES:
        found, _ = check_text(text, "case.yml", loader)
        if bool(found) != refused:
            errors.append(f"self-test: {text!r} gave {found or 'no finding'}, expected {'a finding' if refused else 'none'}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        findings, _ = scan_tree(root, loader)
        if not any("no workflow found" in f for f in findings):
            errors.append("self-test: an empty .github/workflows/*.yml listing gave no failure")
        (workflows / "ok.yml").write_text(step(f"actions/checkout@{SHA}"), encoding="utf-8")
        findings, count = scan_tree(root, loader)
        if findings or count != 1:
            errors.append(f"self-test: a clean tree gave {findings}, {count} uses")
        (workflows / "bad.yml").write_bytes(b"jobs: {a: {steps: [{uses: '\xff'}]}}\n")
        findings, _ = scan_tree(root, loader)
        if not any(".github/workflows/bad.yml: cannot be read" in f for f in findings):
            errors.append("self-test: a workflow that is not UTF-8 gave no finding")
    return errors


def main() -> int:
    try:
        loader = load_scan().UniqueKeyLoader
    except Exception as exc:
        print(f"FAIL: cannot load UniqueKeyLoader from {SCAN} ({type(exc).__name__}: {exc})")
        return 1
    errors = self_test(loader)
    if errors:
        for error in errors:
            print(error)
        print(f"FAIL: {len(errors)} self-test failure(s)")
        return 1
    findings, count = scan_tree(REPO, loader)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s)")
        return 1
    print(f"OK: {count} uses values in .github/workflows/*.yml, every uses pinned to owner/repo[/path]@<40 lower-case hex>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
