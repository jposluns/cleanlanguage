#!/usr/bin/env python3
"""Behavioural tests for the release-date logic in the release workflow.

Item 26 (G3) puts three pieces of shell into
``.github/workflows/release-skill.yml``: the step that determines the expected
release date, the packaging step that passes it on, and the publication-time
checks in the publish step (the publication-window check immediately before
the create call, and the publication readback on every path that ends a dated
release run green: the first creation, a re-run at the same commit, and a
force upload). These tests EXTRACT each step script from the real workflow
file and run it with bash, the way the runner does, against fake ``gh``,
``git`` and ``date`` commands on PATH and a throwaway working directory holding
the real ``tools/skill-release-date.py``. The fakes record every call in
order, so the tests pin both the verdicts and the ordering: the binding window
check runs after every tag operation and before the create call, the readback
runs after it, and an undated release (``RELEASE_DATED=0``) checks no date at
all. The fake ``date`` refuses any call without ``-u``, so a clock read in
local time goes red.

The environment of each step is built the way the runner builds it, from the
workflow itself: the variables the runner sets, the job ``env:`` keys, the
step ``env:`` keys read from the YAML (their expressions resolved from the
test inputs), and the values earlier steps wrote to ``GITHUB_ENV``. The test
supplies no step variable of its own, and it asserts that every variable a step
script reads is declared by one of those sources, so deleting a declaration
goes red. One chained test runs the determine, package and publish steps in
sequence, carrying ``GITHUB_ENV`` forward.

They run offline: nothing reaches GitHub or any network.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "release-skill.yml"
EXTRACTOR = REPO / "tools" / "skill-release-date.py"
VCS = "git"
COMMIT = "c" * 40
OTHER_COMMIT = "d" * 40
INDENT = " " * 10

# The variables the runner itself sets for every step, which a step may read
# without declaring them.
RUNNER_VARIABLES = ("GITHUB_ENV", "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_EVENT_NAME")

RELEASE_TAG_EXPRESSION = (
    "${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name }}"
)


def workflow_lines() -> list[str]:
    return WORKFLOW.read_text(encoding="utf-8").split("\n")


def step_names() -> list[str]:
    prefix = "      - name: "
    return [line[len(prefix):] for line in workflow_lines() if line.startswith(prefix)]


def has_run_block(name: str) -> bool:
    """True when the step ``name`` runs a script (an action step does not)."""
    lines = workflow_lines()
    for line in lines[lines.index(f"      - name: {name}") + 1:]:
        if line.startswith("      - name:"):
            return False
        if line.startswith("        run: |"):
            return True
    return False


def step_block(name: str) -> list[str]:
    """Return the lines of the workflow step called ``name``, up to its run line."""
    lines = workflow_lines()
    start = lines.index(f"      - name: {name}")
    block = []
    for line in lines[start + 1:]:
        if line.startswith("      - name:"):
            raise AssertionError(f"step {name!r} has no run block")
        block.append(line)
        if line.startswith("        run: |"):
            return block
    raise AssertionError(f"step {name!r} has no run block")


def step_script(name: str) -> str:
    """Return the ``run: |`` script of the workflow step called ``name``."""
    lines = workflow_lines()
    start = lines.index(f"      - name: {name}")
    index = start + 1
    while not lines[index].startswith("        run: |"):
        if lines[index].startswith("      - name:"):
            raise AssertionError(f"step {name!r} has no run block")
        index += 1
    body = []
    for line in lines[index + 1:]:
        if line.strip() and not line.startswith(INDENT):
            break
        body.append(line[len(INDENT):])
    script = "\n".join(body).rstrip() + "\n"
    if "${{" in script:
        raise AssertionError(f"step {name!r} uses an expression the test cannot supply")
    return script


def mapping_after(lines: list[str], header: str, indent: int) -> dict[str, str]:
    """Return the ``KEY: value`` pairs indented ``indent`` spaces under ``header``."""
    if header not in lines:
        return {}
    pairs = {}
    for line in lines[lines.index(header) + 1:]:
        if not line.startswith(" " * indent) or line.startswith(" " * (indent + 1)):
            break
        key, _, value = line.strip().partition(": ")
        pairs[key] = value
    return pairs


def step_env(name: str) -> dict[str, str]:
    """The ``env:`` keys the workflow declares for the step ``name``, raw."""
    return mapping_after(step_block(name), "        env:", 10)


def job_env() -> dict[str, str]:
    """The ``env:`` keys the workflow declares for the release job, raw."""
    lines = workflow_lines()
    job = lines[lines.index("  package-and-release:"):]
    return mapping_after(job[: job.index("    steps:")], "    env:", 6)


def github_env_writes(name: str) -> set[str]:
    """The keys the steps before ``name`` write to ``GITHUB_ENV``."""
    names = step_names()
    written = set()
    for earlier in [n for n in names[: names.index(name)] if has_run_block(n)]:
        written |= set(re.findall(r"echo \"([A-Z_][A-Z0-9_]*)=[^\"]*\" >> \"\$\{GITHUB_ENV\}\"", step_script(earlier)))
    return written


def script_reads(script: str) -> set[str]:
    """The upper-case variables a step script reads and does not set itself."""
    read = set(re.findall(r"\$\{?([A-Z_][A-Z0-9_]*)", script))
    assigned = set(re.findall(r"(?m)^\s*(?:local\s+|export\s+)?([A-Z_][A-Z0-9_]*)=", script))
    return read - assigned


FAKE_COMMON = """
import hashlib, json, os, sys
STATE = os.environ["FAKE_STATE"]
NAME = os.path.basename(sys.argv[0])
ARGS = sys.argv[1:]
with open(os.path.join(STATE, "calls.log"), "a", encoding="utf-8") as log:
    log.write(json.dumps([NAME, ARGS]) + "\\n")
def read(name, default=""):
    path = os.path.join(STATE, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return handle.read()
"""

FAKE_GH = FAKE_COMMON + """
if ARGS[:1] == ["api"] and "--include" in ARGS:
    status = read("status", "404")
    print("HTTP/2.0 " + status + " Fake")
    sys.exit(0 if status == "200" else 1)
if ARGS[:1] == ["api"] and "--jq" in ARGS:
    field = ARGS[ARGS.index("--jq") + 1].lstrip(".")
    value = read(field, "null")
    if value == "FAIL":
        sys.exit(1)
    print(value)
    sys.exit(0)
VERSION = os.environ.get("VERSION", "")
ASSETS = ["cleanlanguage.zip", "cleanlanguage.zip.sha256",
          "cleanlanguage-" + VERSION + ".zip", "cleanlanguage-" + VERSION + ".zip.sha256"]
if ARGS[:2] == ["release", "view"]:
    print("\\n".join(ASSETS))
    sys.exit(0)
if ARGS[:2] == ["release", "download"]:
    target = ARGS[ARGS.index("--dir") + 1]
    data = b"published zip bytes"
    digest = hashlib.sha256(data).hexdigest()
    for asset in ASSETS:
        with open(os.path.join(target, asset), "wb") as handle:
            if asset.endswith(".sha256"):
                handle.write((digest + "  " + asset[: -len(".sha256")] + "\\n").encode("utf-8"))
            else:
                handle.write(data)
    sys.exit(0)
sys.exit(0)
"""

FAKE_VCS = FAKE_COMMON + """
if ARGS[:1] == ["rev-parse"]:
    print(read("commit"))
elif ARGS[:1] == ["ls-remote"]:
    tag = read("remote_tag")
    if tag:
        print(tag + "\\trefs/tags/" + os.environ["RELEASE_TAG"])
sys.exit(0)
"""

FAKE_DATE = FAKE_COMMON + """
if "-u" not in ARGS:
    sys.exit("fake date: called without -u, so it would read local time, not UTC")
clock = read("clock").split()
used = int(read("clock_used", "0"))
now = clock[min(used, len(clock) - 1)]
with open(os.path.join(STATE, "clock_used"), "w", encoding="utf-8") as handle:
    handle.write(str(used + 1))
fmt = [a for a in ARGS if a.startswith("+")][0]
if fmt == "+%F":
    print(now[:10])
elif fmt == "+%Y-%m-%dT%H:%M:%SZ":
    print(now)
else:
    sys.exit("fake date: unsupported format " + fmt)
"""

FAKE_PACKAGER = FAKE_COMMON

# A copy of the real extractor that crashes inside, on reading its input, to
# show an internal error is reported as the extractor failing.
CRASH_HOOK = (
    "import io as _crash_io\n"
    "def _crash(*args, **kwargs):\n"
    "    raise RuntimeError(\"injected internal error\")\n"
    "_crash_io.TextIOWrapper = _crash\n"
)


class WorkflowStepTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.root = root
        self.work = root / "work"
        self.state = root / "state"
        self.bin = root / "bin"
        for path in (self.work / "tools", self.work / "cleanlanguage" / "skills" / "cleanlanguage", self.state, self.bin):
            path.mkdir(parents=True)
        shutil.copy2(EXTRACTOR, self.work / "tools" / "skill-release-date.py")
        for name, body in (("gh", FAKE_GH), (VCS, FAKE_VCS), ("date", FAKE_DATE)):
            self.write_exec(self.bin / name, body)
        self.write_exec(self.work / "tools" / "release-package.sh", FAKE_PACKAGER)
        self.env_file = root / "github-env"
        self.set_state(commit=COMMIT, clock="2026-11-15T12:00:00Z",
                       published_at="2026-11-15T12:00:03Z", immutable="true")
        self.skill("Version: 1.0.15  \nReleased: 2026-11-15  \n")
        # The runner, the dispatch inputs, and the values earlier steps wrote
        # to GITHUB_ENV; no step variable is supplied directly.
        self.runner = {
            "GITHUB_REPOSITORY": "jposluns/cleanlanguage",
            "GITHUB_SHA": COMMIT,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
        }
        self.ref_name = "v1.0.15"
        self.inputs = {"tag": "v1.0.15", "force": "false"}
        self.carried = {"VERSION": "1.0.15", "RELEASE_DATED": "1", "RELEASE_DATE": "2026-11-15"}

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def write_exec(path: Path, body: str):
        path.write_text(f"#!{sys.executable} -I\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def set_state(self, **values):
        for key, value in values.items():
            (self.state / key).write_text(value, encoding="utf-8")

    def skill(self, text: str):
        (self.work / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md").write_text(text, encoding="utf-8")

    def crash_extractor(self):
        target = self.work / "tools" / "skill-release-date.py"
        text = target.read_text(encoding="utf-8")
        anchor = "from pathlib import Path\n"
        self.assertEqual(text.count(anchor), 1)
        target.write_text(text.replace(anchor, anchor + CRASH_HOOK), encoding="utf-8")

    def resolve(self, value: str) -> str:
        """Resolve a declared env value the way the runner would."""
        if "${{" not in value:
            return value
        dispatch = self.runner["GITHUB_EVENT_NAME"] == "workflow_dispatch"
        known = {
            "${{ github.token }}": "fake-token",
            "${{ inputs.force }}": self.inputs.get("force", "") if dispatch else "",
            RELEASE_TAG_EXPRESSION: self.inputs["tag"] if dispatch else self.ref_name,
        }
        if value not in known:
            raise AssertionError(f"the workflow declares an expression the test cannot resolve: {value}")
        return known[value]

    def step_environment(self, name: str) -> dict[str, str]:
        script = step_script(name)
        job, step = job_env(), step_env(name)
        written = github_env_writes(name)
        declared = set(RUNNER_VARIABLES) | set(job) | set(step) | written
        undeclared = script_reads(script) - declared
        self.assertFalse(undeclared, f"step {name!r} reads variables nothing declares: {sorted(undeclared)}")
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.root),
            "TMPDIR": str(self.root),
            "FAKE_STATE": str(self.state),
            "GITHUB_ENV": str(self.env_file),
        }
        env.update(self.runner)
        env.update({key: self.resolve(value) for key, value in job.items()})
        env.update({key: self.resolve(value) for key, value in step.items()})
        env.update({key: value for key, value in self.carried.items() if key in written})
        return env

    def run_step(self, name: str):
        env = self.step_environment(name)
        self.env_file.write_text("", encoding="utf-8")
        script = self.state / "step.sh"
        script.write_text(step_script(name), encoding="utf-8")
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
            cwd=self.work, env=env, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            self.carried.update(self.env_values())
        return proc.returncode, proc.stdout, proc.stderr

    def calls(self):
        path = self.state / "calls.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def reset_calls(self):
        (self.state / "calls.log").unlink(missing_ok=True)
        self.set_state(clock_used="0")

    def index_of(self, calls, predicate, last=False):
        hits = [i for i, call in enumerate(calls) if predicate(call)]
        self.assertTrue(hits, f"no matching call in {calls}")
        return hits[-1] if last else hits[0]

    def env_values(self):
        return dict(line.split("=", 1) for line in self.env_file.read_text(encoding="utf-8").splitlines())


def is_push(call):
    return call[0] == VCS and call[1][:1] == ["push"]


def is_create(call):
    return call[0] == "gh" and call[1][:2] == ["release", "create"]


def is_upload(call):
    return call[0] == "gh" and call[1][:2] == ["release", "upload"]


def is_date(call):
    return call[0] == "date"


def is_field_read(field):
    return lambda call: call[0] == "gh" and call[1][:1] == ["api"] and "--jq" in call[1] and call[1][-1] == "." + field


VALIDATE = "Read and validate the version"
PUBLISH = "Create or update GitHub Release"
DETERMINE = "Determine the expected release date"
PACKAGE = "Validate, package, and verify the skill zip"

# The readback outcomes that must fail a dated run on any path.
BAD_READBACKS = (
    ("immutable false", {"immutable": "false"}, "immutable field reads false"),
    ("immutable null", {"immutable": "null"}, "immutable field reads null"),
    ("wrong day", {"published_at": "2026-11-16T00:00:02Z"}, "IS PUBLISHED on a different UTC day"),
)


class HarnessTest(WorkflowStepTest):
    """R7: the harness itself is as strict as the runner."""

    def test_fake_date_refuses_a_call_without_utc(self):
        proc = subprocess.run([str(self.bin / "date"), "+%F"], env={"FAKE_STATE": str(self.state)},
                              capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("without -u", proc.stderr)

    def test_every_variable_a_step_reads_is_declared(self):
        for name in (VALIDATE, DETERMINE, PACKAGE, PUBLISH):
            with self.subTest(name):
                self.step_environment(name)

    def test_the_declarations_the_steps_rely_on_are_in_the_workflow(self):
        self.assertEqual(set(job_env()), {"RELEASE_TAG"})
        self.assertEqual(set(step_env(DETERMINE)), {"GH_TOKEN"})
        self.assertEqual(set(step_env(PUBLISH)), {"GH_TOKEN", "FORCE"})
        self.assertEqual(github_env_writes(DETERMINE), {"VERSION"})
        self.assertEqual(github_env_writes(PACKAGE), {"VERSION", "RELEASE_DATED", "RELEASE_DATE"})


class PublishStepTest(WorkflowStepTest):
    """F1, F9, F10, F14, R1: the publication-time checks of the publish step."""

    def test_dispatch_checks_the_window_after_the_tag_push_and_reads_back(self):
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        calls = self.calls()
        push = self.index_of(calls, is_push)
        last_date = self.index_of(calls, is_date, last=True)
        create = self.index_of(calls, is_create)
        readback = self.index_of(calls, is_field_read("published_at"))
        immutable = self.index_of(calls, is_field_read("immutable"))
        self.assertLess(push, last_date)
        self.assertLess(last_date, create)
        self.assertLess(create, readback)
        self.assertLess(create, immutable)
        self.assertIn("First-publication readback: release v1.0.15 published_at 2026-11-15T12:00:03Z", out)

    def test_rollover_during_the_tag_push_is_refused_before_create(self):
        self.set_state(clock="2026-11-15T23:45:00Z 2026-11-16T00:00:05Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        calls = self.calls()
        self.assertTrue(any(is_push(c) for c in calls), calls)
        self.assertFalse(any(is_create(c) for c in calls), calls)
        self.assertIn("the UTC day is now 2026-11-16", err)
        self.assertIn("No release was created", err)

    def test_fewer_than_ten_minutes_left_is_refused_before_create(self):
        self.set_state(clock="2026-11-15T23:45:00Z 2026-11-15T23:55:00Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertFalse(any(is_create(c) for c in self.calls()))
        self.assertIn("only 300 seconds remain in the UTC day 2026-11-15", err)

    def test_one_second_left_is_refused_in_the_singular(self):
        self.set_state(clock="2026-11-15T23:59:59Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("only 1 second remains in the UTC day 2026-11-15", err)

    def test_refusal_names_the_recovery_for_both_paths(self):
        self.runner["GITHUB_EVENT_NAME"] = "push"
        self.set_state(remote_tag=COMMIT, clock="2026-11-15T23:55:00Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn(VCS + " push origin --delete refs/tags/v1.0.15", err)
        self.assertIn("pushing v1.0.15 at the new commit", err)
        self.assertIn("dispatching this workflow from main with tag v1.0.15", err)
        self.assertIn("force input; with no published release, force only moves the unpublished tag", err)
        self.assertNotIn("Nothing was tagged", err)

    def test_readback_of_a_different_day_fails_loudly_naming_both_days(self):
        self.runner["GITHUB_EVENT_NAME"] = "push"
        self.set_state(remote_tag=COMMIT, published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertTrue(any(is_create(c) for c in self.calls()))
        self.assertIn("published on 2026-11-16", err)
        self.assertIn("names 2026-11-15", err)
        self.assertIn("IS PUBLISHED on a different UTC day", err)

    def test_readback_mismatch_names_a_corrective_version_and_no_republish(self):
        # R4: an immutable release cannot be republished.
        self.set_state(published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("the remedy is a corrective version", err)
        self.assertNotIn("force", err)
        self.assertNotIn("republish with", err)

    def test_unreadable_readback_fails_loudly(self):
        self.set_state(published_at="FAIL")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("could not be read back", err)

    def test_a_release_that_is_not_immutable_fails(self):
        for value in ("false", "null", ""):
            with self.subTest(value):
                self.reset_calls()
                self.set_state(immutable=value)
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn("immutable field reads", err)

    def test_undated_release_checks_no_date(self):
        self.carried["RELEASE_DATED"] = "0"
        self.carried["RELEASE_DATE"] = ""
        self.set_state(clock="2026-11-15T23:59:59Z", published_at="2026-11-16T00:00:02Z", immutable="false")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        calls = self.calls()
        self.assertTrue(any(is_create(c) for c in calls))
        self.assertFalse(any(is_date(c) for c in calls), calls)
        self.assertFalse(any(is_field_read("published_at")(c) or is_field_read("immutable")(c) for c in calls), calls)

    def test_unavailable_extractor_is_reported_as_unavailable(self):
        (self.work / "tools" / "skill-release-date.py").unlink()
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed (exit 2)", err)
        self.assertFalse(any(is_create(c) for c in self.calls()))


class RerunAndForceTest(WorkflowStepTest):
    """R1: a re-run at the same commit and a force upload end green only on the
    same publication readback as the first creation."""

    def rerun(self):
        self.set_state(status="200", remote_tag=COMMIT)

    def force(self):
        self.inputs["force"] = "true"
        self.set_state(status="200", remote_tag=OTHER_COMMIT)

    def assert_readback_ran(self, calls, after=None):
        immutable = self.index_of(calls, is_field_read("immutable"))
        published_at = self.index_of(calls, is_field_read("published_at"))
        if after is not None:
            self.assertLess(after, immutable)
        self.assertLess(immutable, published_at)

    def test_rerun_at_the_same_commit_runs_the_readback(self):
        self.rerun()
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        calls = self.calls()
        self.assertFalse(any(is_create(c) or is_upload(c) for c in calls), calls)
        self.assert_readback_ran(calls)
        self.assertIn("Re-run readback: release v1.0.15 published_at 2026-11-15T12:00:03Z", out)
        self.assertIn("kept its assets", out)

    def test_rerun_fails_when_the_readback_does_not_hold(self):
        for label, state, message in BAD_READBACKS:
            with self.subTest(label):
                self.reset_calls()
                self.set_state(immutable="true", published_at="2026-11-15T12:00:03Z")
                self.rerun()
                self.set_state(**state)
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn(message, err)
                self.assertNotIn("kept its assets", out)

    def test_force_runs_the_readback_after_the_upload(self):
        self.force()
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        calls = self.calls()
        self.assertFalse(any(is_create(c) for c in calls), calls)
        self.assert_readback_ran(calls, after=self.index_of(calls, is_upload))
        self.assertIn("Force readback: release v1.0.15 published_at 2026-11-15T12:00:03Z", out)

    def test_force_fails_when_the_readback_does_not_hold(self):
        for label, state, message in BAD_READBACKS:
            with self.subTest(label):
                self.reset_calls()
                self.set_state(immutable="true", published_at="2026-11-15T12:00:03Z")
                self.force()
                self.set_state(**state)
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn(message, err)
                self.assertTrue(any(is_upload(c) for c in self.calls()))

    def test_force_needs_the_declared_force_input(self):
        # The FORCE variable reaches the script only through the step env
        # declaration; without the input the forced run is refused.
        self.inputs["force"] = "false"
        self.set_state(status="200", remote_tag=OTHER_COMMIT)
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("Cut a new version", err)
        self.assertFalse(any(is_upload(c) for c in self.calls()))

    def test_undated_rerun_and_force_read_no_record_field(self):
        for label, arrange in (("re-run", self.rerun), ("force", self.force)):
            with self.subTest(label):
                self.reset_calls()
                self.carried["RELEASE_DATED"] = "0"
                self.carried["RELEASE_DATE"] = ""
                self.set_state(immutable="false", published_at="2026-11-16T00:00:02Z")
                arrange()
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 0, err)
                calls = self.calls()
                self.assertFalse(
                    any(is_field_read("published_at")(c) or is_field_read("immutable")(c) for c in calls), calls
                )


class DetermineStepTest(WorkflowStepTest):
    """F5, F9, R6: the step that fixes the expected release date."""

    def test_undated_release_at_the_baseline_checks_no_date(self):
        self.carried["VERSION"] = "1.0.14"
        self.skill("Version: 1.0.14  \nAuthor: x\n")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.env_values(), {"RELEASE_DATED": "0", "RELEASE_DATE": ""})
        self.assertFalse(any(c[0] in ("gh", "date") for c in self.calls()), self.calls())

    def test_new_dated_release_expects_today(self):
        self.set_state(status="404", clock="2026-11-15T10:00:00Z")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.env_values(), {"RELEASE_DATED": "1", "RELEASE_DATE": "2026-11-15"})

    def test_undated_release_above_the_baseline_is_still_dated(self):
        self.skill("Version: 1.0.15  \nAuthor: x\n")
        self.set_state(status="404", clock="2026-11-15T10:00:00Z")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.env_values()["RELEASE_DATED"], "1")

    def test_existing_release_expects_its_publication_day(self):
        self.set_state(status="200", published_at="2026-11-14T08:00:00Z")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.env_values()["RELEASE_DATE"], "2026-11-14")

    def test_unusable_published_at_is_named_as_such(self):
        self.set_state(status="200", published_at="null")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("is not a usable UTC instant", err)

    def test_broken_extractor_is_unavailable_not_malformed(self):
        (self.work / "tools" / "skill-release-date.py").write_text("def broken(:\n", encoding="utf-8")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed", err)
        self.assertNotIn("malformed", err)

    def test_extractor_internal_error_is_a_failure_not_an_unreadable_file(self):
        # R6: an internal error has its own exit (6), never the unreadable 4.
        self.crash_extractor()
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed (exit 6)", err)
        self.assertNotIn("Could not read", err)

    def test_malformed_line_is_named_as_such(self):
        self.skill("Version: 1.0.15  \nReleased: soon\n")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("is malformed", err)


class PackageStepTest(WorkflowStepTest):
    """F8, F9: the packager gets --release-date only for a dated release."""

    def packager_args(self):
        return [c[1] for c in self.calls() if c[0] == "release-package.sh"]

    def test_dated_release_passes_the_date(self):
        code, _out, err = self.run_step(PACKAGE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.packager_args(), [["--tag", "v1.0.15", "--release-date", "2026-11-15"]])

    def test_undated_release_passes_no_date(self):
        self.carried["RELEASE_DATED"] = "0"
        self.carried["RELEASE_DATE"] = ""
        code, _out, err = self.run_step(PACKAGE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.packager_args(), [["--tag", "v1.0.15"]])


class ChainedRunTest(WorkflowStepTest):
    """R7: the determine, package and publish steps in sequence, each reading
    what the earlier ones wrote to GITHUB_ENV, from only the VERSION the
    validate step writes."""

    def setUp(self):
        super().setUp()
        self.carried = {"VERSION": "1.0.15"}

    def chain(self):
        results = []
        for name in (DETERMINE, PACKAGE, PUBLISH):
            code, out, err = self.run_step(name)
            results.append((name, code, out, err))
            if code != 0:
                break
        return results

    def test_first_publication_in_sequence(self):
        self.set_state(status="404", clock="2026-11-15T12:00:00Z")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [0, 0, 0], results)
        self.assertEqual(self.carried, {"VERSION": "1.0.15", "RELEASE_DATED": "1", "RELEASE_DATE": "2026-11-15"})
        calls = self.calls()
        package = self.index_of(calls, lambda c: c[0] == "release-package.sh")
        self.assertEqual(calls[package][1], ["--tag", "v1.0.15", "--release-date", "2026-11-15"])
        self.assertLess(package, self.index_of(calls, is_create))
        self.assertIn("First-publication readback", results[-1][2])

    def test_rerun_in_sequence_takes_the_first_publication_day(self):
        self.skill("Version: 1.0.15  \nReleased: 2026-11-14  \n")
        self.set_state(status="200", remote_tag=COMMIT, published_at="2026-11-14T08:00:00Z")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [0, 0, 0], results)
        self.assertEqual(self.carried["RELEASE_DATE"], "2026-11-14")
        self.assertIn("Re-run readback: release v1.0.15 published_at 2026-11-14T08:00:00Z", results[-1][2])

    def test_rerun_in_sequence_fails_on_a_mutable_release(self):
        self.skill("Version: 1.0.15  \nReleased: 2026-11-14  \n")
        self.set_state(status="200", remote_tag=COMMIT, published_at="2026-11-14T08:00:00Z", immutable="false")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [0, 0, 1], results)
        self.assertIn("immutable field reads false", results[-1][3])


if __name__ == "__main__":
    unittest.main()
