#!/usr/bin/env python3
"""Behavioural tests for the release-date logic in the release workflow.

Item 26 (G3) puts three pieces of shell into
``.github/workflows/release-skill.yml``: the step that determines the expected
release date, the packaging step that passes it on, and the publication-time
checks in the publish step (the publication-window check immediately before
the create call and the first-publication readback after it). These tests
EXTRACT each step script from the real workflow file and run it with bash,
the way the runner does, against fake ``gh``, ``git`` and ``date`` commands on
PATH and a throwaway working directory holding the real
``tools/skill-release-date.py``. The fakes record every call in order, so the
tests pin both the verdicts and the ordering: the binding window check runs
after every tag operation and before the create call, the readback runs
after it, and an undated release (``RELEASE_DATED=0``) checks no date at all.

They run offline: nothing reaches GitHub or any network.
"""

from __future__ import annotations

import json
import os
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
INDENT = " " * 10


def step_script(name: str) -> str:
    """Return the ``run: |`` script of the workflow step called ``name``."""
    lines = WORKFLOW.read_text(encoding="utf-8").split("\n")
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


FAKE_COMMON = """
import json, os, sys
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


class WorkflowStepTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.work = root / "work"
        self.state = root / "state"
        self.bin = root / "bin"
        for path in (self.work / "tools", self.work / "cleanlanguage" / "skills" / "cleanlanguage", self.state, self.bin):
            path.mkdir(parents=True)
        shutil.copy2(EXTRACTOR, self.work / "tools" / "skill-release-date.py")
        for name, body in (("gh", FAKE_GH), (VCS, FAKE_VCS), ("date", FAKE_DATE)):
            self.write_exec(self.bin / name, body)
        self.write_exec(self.work / "tools" / "release-package.sh", FAKE_PACKAGER)
        self.env_file = root / "env"
        self.env_file.write_text("", encoding="utf-8")
        self.set_state(commit=COMMIT, clock="2026-11-15T12:00:00Z",
                       published_at="2026-11-15T12:00:03Z", immutable="true")
        self.skill("Version: 1.0.15  \nReleased: 2026-11-15  \n")
        self.env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(root),
            "TMPDIR": str(root),
            "FAKE_STATE": str(self.state),
            "GITHUB_ENV": str(self.env_file),
            "GITHUB_REPOSITORY": "jposluns/cleanlanguage",
            "GITHUB_SHA": COMMIT,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GH_TOKEN": "fake",
            "FORCE": "false",
            "RELEASE_TAG": "v1.0.15",
            "VERSION": "1.0.15",
            "RELEASE_DATE": "2026-11-15",
            "RELEASE_DATED": "1",
        }

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

    def run_step(self, name: str):
        script = self.state / "step.sh"
        script.write_text(step_script(name), encoding="utf-8")
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
            cwd=self.work, env=self.env, capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def calls(self):
        path = self.state / "calls.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

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


def is_date(call):
    return call[0] == "date"


def is_field_read(field):
    return lambda call: call[0] == "gh" and call[1][:1] == ["api"] and "--jq" in call[1] and call[1][-1] == "." + field


PUBLISH = "Create or update GitHub Release"
DETERMINE = "Determine the expected release date"
PACKAGE = "Validate, package, and verify the skill zip"


class PublishStepTest(WorkflowStepTest):
    """F1, F9, F10, F14: the publication-time checks of the publish step."""

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

    def test_refusal_names_the_recovery_for_both_paths(self):
        self.env["GITHUB_EVENT_NAME"] = "push"
        self.set_state(remote_tag=COMMIT, clock="2026-11-15T23:55:00Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn(VCS + " push origin --delete refs/tags/v1.0.15", err)
        self.assertIn("pushing v1.0.15 at the new commit", err)
        self.assertIn("dispatching this workflow from main with tag v1.0.15", err)
        self.assertIn("force input; with no published release, force only moves the unpublished tag", err)
        self.assertNotIn("Nothing was tagged", err)

    def test_readback_of_a_different_day_fails_loudly_naming_both_days(self):
        self.env["GITHUB_EVENT_NAME"] = "push"
        self.set_state(remote_tag=COMMIT, published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertTrue(any(is_create(c) for c in self.calls()))
        self.assertIn("published on 2026-11-16", err)
        self.assertIn("names 2026-11-15", err)
        self.assertIn("IS PUBLISHED on a different UTC day", err)

    def test_unreadable_readback_fails_loudly(self):
        self.set_state(published_at="FAIL")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("could not be read back", err)

    def test_a_release_that_is_not_immutable_fails(self):
        for value in ("false", "null", ""):
            with self.subTest(value):
                (self.state / "calls.log").unlink(missing_ok=True)
                self.set_state(immutable=value, clock_used="0")
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn("immutable field reads", err)

    def test_undated_release_checks_no_date(self):
        self.env["RELEASE_DATED"] = "0"
        self.env["RELEASE_DATE"] = ""
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


class DetermineStepTest(WorkflowStepTest):
    """F5, F9: the step that fixes the expected release date."""

    def test_undated_release_at_the_baseline_checks_no_date(self):
        self.env["VERSION"] = "1.0.14"
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
        self.env["RELEASE_DATED"] = "0"
        self.env["RELEASE_DATE"] = ""
        code, _out, err = self.run_step(PACKAGE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.packager_args(), [["--tag", "v1.0.15"]])


if __name__ == "__main__":
    unittest.main()
