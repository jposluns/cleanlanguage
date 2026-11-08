#!/usr/bin/env python3
"""Tests the triggers of portable-text-sync.yml and release-dry-run.yml, and the dry run's time limit.

The steps of .github/workflows/portable-text-sync.yml read files across the
repository, and a path list cannot be kept complete against those reads, so
the workflow runs on every pull request and every push to main (row 119).
This test fails if a paths or paths-ignore filter comes back under either
trigger.

That workflow runs this test, and so does workflow-isolation.yml, so a pull
request that adds a filter to that workflow which its own changed files fall
outside still runs it.

The release dry run workflow, .github/workflows/release-dry-run.yml, carries
no paths filter for the same reason: its dry run and gates read files across
the repository, the whole site included, and a path list cannot be kept
complete against those reads (row 127). DryRunTests fails unless the value of
its on: is exactly a bare pull_request trigger, a push trigger on main and a
bare workflow_dispatch, so a paths, paths-ignore, branches, branches-ignore,
tags, tags-ignore or types key under either trigger fails. It also fails
unless that workflow has exactly 1 job, dry-run, whose timeout-minutes is the
integer DRY_RUN_TIMEOUT (row 117), so a removed, changed, quoted or moved
time limit fails, and a change to the limit is made in this test and the
workflow together. It does not check the steps of the dry run. The dry run
does not run this test: workflow-isolation.yml does, with no filter, so a
pull request that adds a filter to the dry run which its own changed files
fall outside still runs it.

The test reads each workflow's bytes and fails unless they decode as UTF-8
and every character is printable ASCII or a line feed, so a tab or a carriage
return (a CRLF line end included) fails. It then parses the text with the
UniqueKeyLoader of tools/test-workflow-launch-isolation.py, a safe PyYAML
loader (that file says what the loader refuses), and fails unless the text
is 1 YAML document that the loader accepts. From the parsed structure, it
fails for portable-text-sync.yml or workflow-isolation.yml unless all 3 of
the following hold, and for release-dry-run.yml unless the first holds:

- its top-level keys are exactly name, on, permissions and jobs, each written
  as a plain key, in that order, so a quoted "on" fails, and so do ON and yes,
  which PyYAML, reading YAML 1.1, loads as the boolean True, as it loads on;
- the value of on: is exactly a bare pull_request trigger and a push trigger
  on main. So a filter in any form fails, and so does any other change to the
  triggers, which is then made in this test and the workflow together;
- exactly 1 step under the steps: of a job with no if: holds, apart from
  its name, exactly shell: bash and a run of the Usage line below. So a
  condition on that step or its job, continue-on-error or any other key on
  that step, and launch lines outside steps: each fail.

The last 2 checks read the structure after PyYAML applies any merge key,
so a merge key is not itself a key they see: they compare a merge by its
effect on the parsed structure, and a merge fails them only if it changes
what they compare. A merge that adds a filter, or an if: to the guard step
or its job, fails them. One that the explicit keys override, such as a
push: that merges branches: [dev] and sets branches: [main], or one that
brings in no key, leaves the parsed structure unchanged, so they do not
fail it. A merge key among the top-level keys fails the first check. How
GitHub Actions handles merge keys is not checked.

The test checks no other key of a job that runs it, such as needs: or
continue-on-error, no condition on any other job or step, and nothing that
GitHub Actions reads differently from PyYAML. A deliberate edit that defeats
this test is caught only by review: a pull request can edit both workflows
and this test, and no check inside them can stop it. Such edits include, for
example, a filter on both workflows that the pull request's own files fall
outside, which starts neither run of this test; a needs: on a job that is
skipped; a step before this one that changes the files this test reads; and
an edit to this test.

Usage:
  python3 -I tools/test-portable-text-sync-workflow.py
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "portable-text-sync.yml"
ISOLATION = REPO_ROOT / ".github" / "workflows" / "workflow-isolation.yml"
DRY_RUN = REPO_ROOT / ".github" / "workflows" / "release-dry-run.yml"

# The loader of the launch isolation scan, loaded by its explicit path; it exits if PyYAML is missing.
ISOLATION_SCAN = REPO_ROOT / "tools" / "test-workflow-launch-isolation.py"
spec = importlib.util.spec_from_file_location("workflow_launch_isolation", ISOLATION_SCAN)
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)
yaml, UniqueKeyLoader = isolation.yaml, isolation.UniqueKeyLoader

TOP_KEYS = ["name", "on", "permissions", "jobs"]
TRIGGERS = {"pull_request": None, "push": {"branches": ["main"]}}
LAUNCH = {"shell": "bash", "run": "python3 -I tools/test-portable-text-sync-workflow.py"}
STEP = "        shell: bash\n        run: python3 -I tools/test-portable-text-sync-workflow.py"
DRY_RUN_TRIGGERS = {"pull_request": None, "push": {"branches": ["main"]}, "workflow_dispatch": None}
# The time limit of the dry-run job in minutes. The comment above timeout-minutes in release-dry-run.yml
# says why the job has a limit and that the value is an estimate.
DRY_RUN_TIMEOUT = 30


def read(path: Path) -> str:
    """The workflow text, decoded from the bytes on disk so that a carriage return is kept.

    A file that cannot be read as UTF-8 raises ValueError.
    """
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise ValueError(f"cannot read {path}: {err}") from err


def parse(text: str) -> dict:
    """The workflow, parsed with UniqueKeyLoader.

    Raises ValueError for a character other than a line feed outside printable
    ASCII, text that is not 1 YAML document or that the loader refuses, or
    top-level keys other than the plain keys name, on, permissions and jobs
    in that order.
    """
    bad = re.search(r"[^\x20-\x7e\n]", text)
    if bad:
        raise ValueError(f"the workflow holds {bad.group()!r}, outside printable ASCII")
    try:
        doc = yaml.load(text, Loader=UniqueKeyLoader)
        node = yaml.compose(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as err:
        raise ValueError(f"the workflow cannot be parsed: {err}") from err
    keys = [(key.value, key.style) for key, _ in node.value] if isinstance(node, yaml.MappingNode) else None
    if keys != [(key, None) for key in TOP_KEYS]:
        raise ValueError(f"the top-level keys are {keys}, not the plain keys {TOP_KEYS}")
    return doc


def triggers(doc: dict):
    """The value of on:, which PyYAML loads as the key True, or None if there is no such key."""
    return doc.get(True)


def launches(doc: dict) -> int:
    """How many steps under the steps: of a job with no if: hold LAUNCH and, apart from a name, nothing else."""
    jobs = doc["jobs"] if isinstance(doc["jobs"], dict) else {}
    count = 0
    for job in jobs.values():
        if isinstance(job, dict) and "if" not in job and isinstance(job.get("steps"), list):
            count += sum(isinstance(step, dict) and {k: v for k, v in step.items() if k != "name"} == LAUNCH
                         for step in job["steps"])
    return count


def timeout_holds(doc: dict) -> bool:
    """Whether the jobs are exactly dry-run and its timeout-minutes is the integer DRY_RUN_TIMEOUT."""
    jobs = doc["jobs"] if isinstance(doc["jobs"], dict) else {}
    job = jobs.get("dry-run")
    limit = job.get("timeout-minutes") if isinstance(job, dict) else None
    return list(jobs) == ["dry-run"] and type(limit) is int and limit == DRY_RUN_TIMEOUT


def edited(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"{old!r} is not in the workflow")
    return text.replace(old, new, 1)


class TriggerTests(unittest.TestCase):
    def test_both_triggers_carry_no_filter(self):
        self.assertEqual(triggers(parse(read(WORKFLOW))), TRIGGERS)

    def test_a_filter_under_either_trigger_fails(self):
        text = read(WORKFLOW)
        for old, new in (("  pull_request:\n", '  pull_request:\n    paths:\n      - "site-src/**"\n'),
                         ("  pull_request:\n", "  pull_request:\n    paths-ignore:\n      - docs/**\n"),
                         ("      - main\n", '      - main\n    paths:\n      - "tools/**"\n'),
                         ("      - main\n", "      - main\n    paths-ignore: [docs/**]\n"),
                         ("      - main\n", '      - main\n    "paths": ["tools/**"]\n'),
                         ("  pull_request:\n", "  pull_request: {paths: [tools/**]}\n")):
            with self.subTest(new):
                self.assertNotEqual(triggers(parse(edited(text, old, new))), TRIGGERS)

    def test_a_commented_filter_is_skipped(self):
        text = edited(read(WORKFLOW), "  pull_request:\n", '  pull_request:\n    # paths:\n#     - "tools/**"\n')
        self.assertEqual(triggers(parse(text)), TRIGGERS)

    def test_an_unexpected_shape_fails(self):
        text = read(WORKFLOW)
        for old, new in (("on:\n", '"on":\n'), ("on:\n", "ON:\n"), ("on:\n", "yes:\n"),
                         ("on:\n", "on: [pull_request, push]\n"),
                         ("permissions:\n", "on:\n  push:\npermissions:\n"),
                         ("permissions:\n", "On:\n  push:\npermissions:\n"), ("      - main\n", "\t- main\n"),
                         ("on:\n", "on:\r\n"), ("jobs:\n", "jobs: [\n"), ("jobs:\n", "---\njobs:\n")):
            with self.subTest(new), self.assertRaises(ValueError):
                parse(edited(text, old, new))

    def test_a_name_that_swallows_the_triggers_fails(self):
        text = edited(read(WORKFLOW), "name: Portable", 'name: "Portable')
        with self.assertRaises(ValueError):
            parse(edited(text, "  contents: read\n", '  contents: read"\n'))

    def test_an_unreadable_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.yml"
            bad.write_bytes(b"on: \xff\n")
            for path in (bad, Path(tmp) / "missing.yml"):
                with self.subTest(path.name), self.assertRaises(ValueError):
                    read(path)

    def test_a_carriage_return_on_disk_fails(self):
        text = read(WORKFLOW)
        with tempfile.TemporaryDirectory() as tmp:
            for name, ending in (("crlf.yml", "\r\n"), ("cr.yml", "\r")):
                path = Path(tmp) / name
                path.write_bytes(text.replace("\n", ending).encode("utf-8"))
                with self.subTest(name), self.assertRaises(ValueError):
                    parse(read(path))


class LaunchTests(unittest.TestCase):
    def test_both_workflows_launch_this_test(self):
        for path in (WORKFLOW, ISOLATION):
            with self.subTest(path.name):
                self.assertEqual(launches(parse(read(path))), 1)

    def test_workflow_isolation_carries_no_filter(self):
        self.assertEqual(triggers(parse(read(ISOLATION))), TRIGGERS)

    def test_a_removed_or_altered_launch_fails(self):
        run = STEP.split("\n")[1]
        for path in (WORKFLOW, ISOLATION):
            text = read(path)
            for old, new in ((run + "\n", ""), (STEP, "#" + STEP), (run, run.replace(" -I", "")),
                             (STEP, "        if: false\n" + STEP),
                             (STEP, STEP + "\n        continue-on-error: true"),
                             ("    runs-on:", "    if: false\n    runs-on:")):
                with self.subTest(path=path.name, new=new):
                    self.assertEqual(launches(parse(edited(text, old, new))), 0)

    def test_launch_lines_outside_the_steps_fail(self):
        name = ("\n      - name: Check the portable text sync, release dry run and this workflow's triggers, "
                "and the dry run time limit\n")
        text = edited(read(ISOLATION), name + STEP + "\n", "")
        text = edited(text, "    steps:\n", "    env:\n      GUARD: |\n" + STEP + "\n    steps:\n")
        self.assertEqual(launches(parse(text)), 0)


class DryRunTests(unittest.TestCase):
    PULL = "  pull_request:\n"
    MAIN = "      - main\n"
    LIMIT = f"    timeout-minutes: {DRY_RUN_TIMEOUT}\n"

    def test_both_triggers_carry_no_filter(self):
        self.assertEqual(triggers(parse(read(DRY_RUN))), DRY_RUN_TRIGGERS)

    def test_a_filter_or_narrowing_under_either_trigger_fails(self):
        text = read(DRY_RUN)
        for old, new in ((self.PULL, self.PULL + '    paths:\n      - "site-src/**"\n'),
                         (self.PULL, self.PULL + "    paths-ignore:\n      - docs/**\n"),
                         (self.PULL, self.PULL + "    branches: [main]\n"),
                         (self.PULL, self.PULL + "    branches-ignore: [dev]\n"),
                         (self.PULL, self.PULL + "    tags: [v*]\n"),
                         (self.PULL, self.PULL + "    types: [opened]\n"),
                         (self.PULL, "  pull_request: {paths: [tools/**]}\n"),
                         (self.MAIN, self.MAIN + '    paths:\n      - "tools/**"\n'),
                         (self.MAIN, self.MAIN + "    paths-ignore: [docs/**]\n"),
                         (self.MAIN, self.MAIN + "    branches-ignore: [dev]\n"),
                         (self.MAIN, self.MAIN + "    tags: [v*]\n"),
                         (self.MAIN, self.MAIN + "    tags-ignore: [v*]\n"),
                         (self.MAIN, self.MAIN + '    "paths": ["tools/**"]\n')):
            with self.subTest(new):
                self.assertNotEqual(triggers(parse(edited(text, old, new))), DRY_RUN_TRIGGERS)

    def test_the_job_carries_its_time_limit(self):
        self.assertTrue(timeout_holds(parse(read(DRY_RUN))))

    def test_a_removed_changed_or_moved_time_limit_fails(self):
        text = read(DRY_RUN)
        for old, new in ((self.LIMIT, ""), (self.LIMIT, "    timeout-minutes: 360\n"),
                         (self.LIMIT, f'    timeout-minutes: "{DRY_RUN_TIMEOUT}"\n'),
                         (self.LIMIT, f"    timeout-minutes: {DRY_RUN_TIMEOUT}.0\n"),
                         (self.LIMIT, "    timeout-minutes: true\n"),
                         (self.LIMIT, f"    # timeout-minutes: {DRY_RUN_TIMEOUT}\n"),
                         (self.LIMIT, "    timeout-minutes: ${{ inputs.limit }}\n"),
                         (self.LIMIT + "    steps:\n", f"    steps:\n      - timeout-minutes: {DRY_RUN_TIMEOUT}\n"
                                                        "        shell: bash\n        run: echo ok\n"),
                         ("jobs:\n", "jobs:\n  other:\n    runs-on: ubuntu-latest\n")):
            with self.subTest(new):
                self.assertFalse(timeout_holds(parse(edited(text, old, new))))


if __name__ == "__main__":
    unittest.main()
