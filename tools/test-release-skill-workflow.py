#!/usr/bin/env python3
"""Behavioural tests for the release-date logic in the release workflow.

Item 26 puts 3 pieces of shell into
``.github/workflows/release-skill.yml``: the step that determines the expected
release date, the packaging step that passes it on, and the publication-time
checks in the publish step (the publication-window check immediately before
the create call, and the publication readback on every path that ends a
release run green: the first creation and a re-run at the same commit). These
tests EXTRACT each step script from the real workflow file and run it with
bash, the way the runner does, against fake ``gh``,
``git`` and ``date`` commands on PATH and a throwaway working directory holding
the real ``tools/skill-release-date.py`` and the real
``tools/skill-release-date-client.py``, through which every step reads it
(row 89). The fakes record every call in
order, so the tests pin both the verdicts and the ordering: the binding window
check runs after every tag operation and before the create call, the readback
runs after it, and an undated release (``RELEASE_DATED=0``) checks no date at
all, though its readback still requires the release to be immutable (item
57). The fake ``date`` refuses any call without ``-u``, so a clock read in
local time goes red.

The fakes of ``git`` and ``gh`` answer only the calls listed in
``CALL_FORMS``, a table of the exact call shapes the workflow makes, each
with its kind (a read, or the change it makes). The fakes and the call
predicates find the row of a call through the same function, ``row_of``.
A call that matches no row is recorded by the fake that refused it, and the
run that made it fails unless the case opts out and gives its reason, so an
unknown call is never counted as harmless.
The table lists call shapes; it does not model how ``git`` or ``gh`` read
their options.

The workflow is parsed with ``yaml.safe_load`` (PyYAML, the same dependency
the release packager already relies on in the same CI job), so the step names,
the keys of each step and every ``env:`` mapping are read as the runner reads
them, not by line patterns that a blank line or a reordered key could defeat.
The environment of each step is built the way the runner builds it, from the
workflow itself: the variables the runner sets, the job ``env:`` keys, the
step ``env:`` keys (their expressions resolved from the test inputs), and the
values earlier steps wrote to ``GITHUB_ENV``. The test supplies no step
variable of its own, and it asserts that every variable a step script reads is
declared by one of those sources, so deleting a declaration goes red. One
chained test runs the determine, package and publish steps in sequence,
carrying ``GITHUB_ENV`` forward.

The structure the harness models is pinned on the parsed data: the exact list
of steps; the key set of every step; ``shell: bash`` on every modelled step;
the ``env:`` key set of the job and of every modelled step; no step or job
``env:`` key overlapping a key an earlier step writes to ``GITHUB_ENV`` (so no
result depends on the precedence the runner gives the two, which these tests
do not model); no step other than the validate and determine steps naming
``GITHUB_ENV`` in any form, and every mention in those two being a write in
the one form the harness reads; no step naming ``GITHUB_PATH``; no duplicate
mapping key anywhere in the file (``safe_load`` would otherwise keep the last
silently); and no read of the repository immutable-releases setting, which the
workflow token cannot read, so the publication readback is the only
immutability check. Mutation tests apply defects to the real workflow text,
among them a blank line before an ``env:`` override, an unmodelled step
writing ``RELEASE_DATED=0``, and other forms of those defects, and require the
structural checks to name each one. Residual: a write to the runner command
files that never names ``GITHUB_ENV`` (for example a path built from pieces,
or a write from inside an action) is not detected; the pinned step list and
key sets are what keep such a step out.

Item 57 removes the path that re-uploaded the assets of a published release.
This workflow never republishes a published release, so the force input is
refused against one and only moves the tag of a release that is not yet
published. The
ImmutableReleaseTest cases pin that behaviour and the wording of every
published-release refusal, and a structural check names any return of an
asset upload, of a clobbering call other than the verification download, of
the old step name or the old republish wording, and any change to the one
readback per success path. Residual: the wording check is a list of known
strings, so a new wording that offers a republish in other words is not
caught; the behavioural cases are the guard that does not depend on wording.

They run offline: nothing reaches GitHub or any network.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "release-skill.yml"
EXTRACTOR = REPO / "tools" / "skill-release-date.py"
CLIENT = REPO / "tools" / "skill-release-date-client.py"

# Row 89: the extractor file name. Each caller reaches the extractor only
# through tools/skill-release-date-client.py, whose name does not contain
# it, so in a caller the lines that name it are only the messages and
# comments listed with the caller (none, in the release workflow, since
# row 95 left no line there naming a .py file outside a launch); any other
# line that names it, a launch in any form among them (any interpreter,
# quoted or not, any options, a continuation line, or the script run by
# its shebang), fails the launch test. Residual: a launch that builds the
# name from parts or reads it from a variable is not seen.
EXTRACTOR_NAME = 'skill-release-date.py'


def extractor_mentions(text: str) -> list:
    """Each line of ``text`` that names the extractor, once per mention."""
    return [line for line in text.split("\n") for _ in range(line.count(EXTRACTOR_NAME))]


# The forms a direct launch could take; each must fail the launch test.
LAUNCH_PROBES = (
    'python3 -X utf8 tools/skill-release-date.py --baseline',
    'python3 -I \\\n  tools/skill-release-date.py --baseline',
    'tools/skill-release-date.py --baseline',
    '"${PYTHON:-python3}" tools/skill-release-date.py --baseline',
    '"python3" tools/skill-release-date.py --baseline',
)

# Row 89: the client file name, checked the same way. In a caller, the
# lines that name it are only the comments and the launches listed with
# the caller (only launches, in the release workflow), each launch
# exactly "python3 -I tools/skill-release-date-client.py" and its
# arguments, so any other line that names it fails:
# a launch without -I, with another interpreter word, quoted or from a
# variable, over a continuation line, by its shebang, or one more launch in
# the listed form. Residual: a launch that builds the name from parts or
# reads it from a variable is not seen.
CLIENT_NAME = 'skill-release-date-client.py'


def client_mentions(text: str) -> list:
    """Each line of ``text`` that names the client, once per mention."""
    return [line for line in text.split("\n") for _ in range(line.count(CLIENT_NAME))]


# The forms another client launch could take; each must fail the check.
CLIENT_LAUNCH_PROBES = (
    'python3 tools/skill-release-date-client.py baseline',
    '"python3" -I tools/skill-release-date-client.py baseline',
    'python3 -X utf8 tools/skill-release-date-client.py baseline',
    'python3 -I \\\n  tools/skill-release-date-client.py baseline',
    'tools/skill-release-date-client.py baseline',
    '"${PYTHON:-python3}" -I tools/skill-release-date-client.py baseline',
    'python3 -I tools/skill-release-date-client.py baseline',
)

# The lines of the release workflow that name the client: its launches
# only, since row 95 reworded every comment that named it.
WORKFLOW_CLIENT_MENTIONS = (
    '          baseline="$(python3 -I tools/skill-release-date-client.py baseline)" || prc=$?',
    '          released="$(python3 -I tools/skill-release-date-client.py extract-file cleanlanguage/skills/cleanlanguage/SKILL.md)" || rc=$?',
    '              requirement="$(python3 -I tools/skill-release-date-client.py requires-date "${VERSION}")" || rc=$?',
    '              release_date="$(python3 -I tools/skill-release-date-client.py published-day "${published_at}")" || rc=$?',
    '            python3 -I tools/skill-release-date-client.py publish-window "${RELEASE_DATE}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >/dev/null || rc=$?',
    '            python3 -I tools/skill-release-date-client.py confirm-published "${RELEASE_DATE}" "${published_at}" >/dev/null || rc=$?',
    '            baseline="$(python3 -I tools/skill-release-date-client.py baseline)" || prc=$?',
)

# The lines of the release workflow that name the extractor: none. Row 95
# reworded its failure messages and comments to name "the release-date
# extractor", so any line that names the file is a new mention.
WORKFLOW_MENTIONS = ()
VCS = "git"
COMMIT = "c" * 40
OTHER_COMMIT = "d" * 40

# The variables the runner itself sets for every step, which a step may read
# without declaring them.
RUNNER_VARIABLES = ("GITHUB_ENV", "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_EVENT_NAME")

RELEASE_TAG_EXPRESSION = (
    "${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name }}"
)


VALIDATE = "Read and validate the version"
PUBLISH = "Create or verify GitHub Release"
DETERMINE = "Determine the expected release date"
PACKAGE = "Validate, package, and verify the skill zip"
CHECKOUT = "Check out repository"
MODELLED = (VALIDATE, DETERMINE, PACKAGE, PUBLISH)
JOB = "package-and-release"

# The exact steps of the release job, in order.
EXPECTED_STEPS = [CHECKOUT, VALIDATE, DETERMINE, PACKAGE, PUBLISH]

# The keys of the release job, and of each of its steps. The step keys the
# harness models are name, env, shell and run; any other key on a modelled
# step, for example a step-level if or continue-on-error, changes what the
# runner does without the harness seeing it, so it fails the suite until the
# harness models it.
JOB_KEYS = {"runs-on", "env", "steps"}
MODELLED_STEP_KEYS = {"name", "env", "shell", "run"}
STEP_KEYS = {
    CHECKOUT: {"name", "uses", "with"},
    VALIDATE: {"name", "shell", "run"},
    DETERMINE: {"name", "env", "shell", "run"},
    PACKAGE: {"name", "shell", "run"},
    PUBLISH: {"name", "env", "shell", "run"},
}

# The env: keys the job and each modelled step declare, and the keys the
# steps before each named step write to GITHUB_ENV.
JOB_ENV_KEYS = {"RELEASE_TAG", "OLDER_TAG_ADVICE", "TAG_GONE_ADVICE", "SUPERSEDED_RELEASE_ADVICE"}
STEP_ENV_KEYS = {VALIDATE: set(), DETERMINE: {"GH_TOKEN"}, PACKAGE: set(), PUBLISH: {"GH_TOKEN", "FORCE"}}
GITHUB_ENV_WRITES = {
    VALIDATE: set(),
    DETERMINE: {"VERSION"},
    PACKAGE: {"VERSION", "RELEASE_DATED", "RELEASE_DATE"},
    PUBLISH: {"VERSION", "RELEASE_DATED", "RELEASE_DATE"},
}

# The only steps that may write GITHUB_ENV, and the one form of write the
# harness reads. Every mention of GITHUB_ENV in those steps must be such a
# write; any mention in any other step fails, whatever its form.
GITHUB_ENV_WRITERS = (VALIDATE, DETERMINE)
CANONICAL_WRITE = re.compile(r"echo \"([A-Z_][A-Z0-9_]*)=[^\"]*\" >> \"\$\{GITHUB_ENV\}\"")


def env_mapping(value, where: str) -> dict[str, str]:
    """An env: mapping as parsed, checked to hold only string keys and values,
    the only form the harness models."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AssertionError(f"the env: of {where} is not a mapping: {value!r}")
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise AssertionError(f"the env: of {where} has a non-string entry {key!r}: {item!r}")
    return dict(value)


def dumped(value) -> str:
    return json.dumps(value, default=str)


class Workflow:
    """The release workflow, parsed with yaml.safe_load."""

    def __init__(self, text: str):
        self.text = text
        self.data = yaml.safe_load(text)
        self.job = self.data["jobs"][JOB]
        self.steps = self.job["steps"]

    def step_names(self) -> list:
        return [step.get("name") for step in self.steps]

    def step(self, name: str) -> dict:
        matches = [step for step in self.steps if step.get("name") == name]
        if len(matches) != 1:
            raise AssertionError(f"the workflow has {len(matches)} steps named {name!r}")
        return matches[0]

    def step_script(self, name: str) -> str:
        """The run: script of the step ``name``."""
        run = self.step(name).get("run")
        if not isinstance(run, str):
            raise AssertionError(f"step {name!r} has no run block")
        script = run.rstrip() + "\n"
        if "${{" in script:
            raise AssertionError(f"step {name!r} uses an expression the test cannot supply")
        return script

    def step_env(self, name: str) -> dict[str, str]:
        """The env: keys the workflow declares for the step ``name``, raw."""
        return env_mapping(self.step(name).get("env"), f"step {name!r}")

    def step_keys(self, name: str) -> set[str]:
        return set(self.step(name))

    def job_env(self) -> dict[str, str]:
        """The env: keys the workflow declares for the release job, raw."""
        return env_mapping(self.job.get("env"), f"job {JOB!r}")

    def github_env_writes(self, name: str) -> set[str]:
        """The keys the steps before ``name`` write to GITHUB_ENV."""
        written = set()
        for earlier in self.steps[: self.step_names().index(name)]:
            run = earlier.get("run")
            if isinstance(run, str):
                written |= set(CANONICAL_WRITE.findall(run))
        return written


def problems_layout(wf: Workflow) -> list[str]:
    problems = []
    jobs = sorted(wf.data["jobs"])
    if jobs != [JOB]:
        problems.append(f"the workflow jobs are {jobs}, not [{JOB!r}]")
    for key in ("env", "defaults"):
        if key in wf.data:
            problems.append(f"the workflow carries a top-level {key}: key the harness does not model")
    if set(wf.job) != JOB_KEYS:
        problems.append(f"job {JOB!r} carries the keys {sorted(wf.job)}, not {sorted(JOB_KEYS)}")
    return problems


def problems_step_list(wf: Workflow) -> list[str]:
    names = wf.step_names()
    if names != EXPECTED_STEPS:
        return [f"the workflow steps are {names}, not the pinned list {EXPECTED_STEPS}"]
    return []


def problems_step_keys(wf: Workflow) -> list[str]:
    problems = []
    for step in wf.steps:
        name = step.get("name")
        keys = set(step)
        if name in STEP_KEYS and keys != STEP_KEYS[name]:
            problems.append(f"step {name!r} carries the keys {sorted(keys)}, not {sorted(STEP_KEYS[name])}")
        if name in MODELLED:
            if not keys <= MODELLED_STEP_KEYS:
                problems.append(f"step {name!r} carries keys the harness does not model: {sorted(keys - MODELLED_STEP_KEYS)}")
            shell = step.get("shell")
            if shell != "bash":
                problems.append(f"step {name!r} runs under shell {shell!r}, not bash")
    return problems


def problems_env(wf: Workflow) -> list[str]:
    problems = []
    job = wf.job_env()
    if set(job) != JOB_ENV_KEYS:
        problems.append(f"job {JOB!r} declares env keys {sorted(job)}, not {sorted(JOB_ENV_KEYS)}")
    for name in MODELLED:
        declared = wf.step_env(name)
        if set(declared) != STEP_ENV_KEYS[name]:
            problems.append(f"step {name!r} declares env keys {sorted(declared)}, not {sorted(STEP_ENV_KEYS[name])}")
        written = wf.github_env_writes(name)
        if written != GITHUB_ENV_WRITES[name]:
            problems.append(f"the steps before {name!r} write {sorted(written)} to GITHUB_ENV, not {sorted(GITHUB_ENV_WRITES[name])}")
        overlap = set(job).union(declared).intersection(written)
        if overlap:
            problems.append(f"step {name!r} declares env keys an earlier step writes to GITHUB_ENV: {sorted(overlap)}")
    return problems


def problems_runner_files(wf: Workflow) -> list[str]:
    problems = []
    outside = dumped({key: value for key, value in wf.job.items() if key != "steps"})
    for token in ("GITHUB_ENV", "GITHUB_PATH"):
        if token in outside:
            problems.append(f"job {JOB!r} names {token} outside its steps")
    for step in wf.steps:
        name = step.get("name")
        if "GITHUB_PATH" in dumped(step):
            problems.append(f"step {name!r} names GITHUB_PATH, which no step may write")
        if name not in GITHUB_ENV_WRITERS:
            if "GITHUB_ENV" in dumped(step):
                problems.append(f"step {name!r} names GITHUB_ENV, which only {list(GITHUB_ENV_WRITERS)} may write")
            continue
        run = step.get("run") if isinstance(step.get("run"), str) else ""
        if "GITHUB_ENV" in dumped({key: value for key, value in step.items() if key != "run"}):
            problems.append(f"step {name!r} names GITHUB_ENV outside its run: script")
        mentions, writes = run.count("GITHUB_ENV"), len(CANONICAL_WRITE.findall(run))
        if mentions != writes:
            problems.append(f"step {name!r} names GITHUB_ENV {mentions} times but makes {writes} writes in the modelled form")
    return problems


def problems_setting_endpoint(wf: Workflow) -> list[str]:
    # GitHub documents the immutable-releases setting endpoint as needing
    # administration read access, which the workflow token cannot be granted.
    if "immutable-releases" in wf.text:
        return ["the workflow names the immutable-releases setting endpoint, which the workflow token cannot read"]
    return []


def problems_duplicate_keys(wf: Workflow) -> list[str]:
    """Every mapping key repeated within one mapping, from the composed node
    tree (no object is constructed), since safe_load keeps the last silently."""
    problems = []
    pending = [yaml.compose(wf.text, Loader=yaml.SafeLoader)]
    while pending:
        node = pending.pop()
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for key, value in node.value:
                label = key.value if isinstance(key, yaml.ScalarNode) else None
                if label in seen:
                    problems.append(f"line {key.start_mark.line + 1} repeats the key {label!r}")
                seen.add(label)
                pending.extend((key, value))
        elif isinstance(node, yaml.SequenceNode):
            pending.extend(node.value)
    return problems


# Item 57: text the workflow carried while it offered a force republish of a
# published release or re-uploaded its assets, and the old step name; none of
# it may return.
STALE_REPUBLISH_TEXT = (
    "Overwrite an already published release",
    "force is enabled; overwriting",
    "Republish deliberately with a manual dispatch",
    "republish deliberately with a manual dispatch",
    "force input to overwrite",
    "deliberate force republish",
    "except by a deliberate manual dispatch",
    "force dispatch",
    "after a force",
    "Force readback",
    "Create or update GitHub Release",
)

# The publication readback labels of the publish step, in order: one for each
# path that ends a run green, dated or not (a re-run at the same commit, and
# the first creation).
READBACK_LABELS = ["Re-run readback", "First-publication readback"]
READBACK_CALL = re.compile(r"confirm_published_release \"([^\"]+)\"")


def problems_republish(wf: Workflow) -> list[str]:
    """Item 57: no asset upload, no clobbering call but the verification
    download, none of the old republish wording, and exactly one readback per
    success path of the publish step."""
    problems = []
    for number, line in enumerate(wf.text.split("\n"), 1):
        if "release upload" in line:
            problems.append(f"line {number} uploads release assets, which a published release cannot take")
        if "--clobber" in line and "release download" not in line:
            problems.append(f"line {number} clobbers outside the verification download")
    for stale in STALE_REPUBLISH_TEXT:
        if stale in wf.text:
            problems.append(f"the workflow carries the stale republish text {stale!r}")
    if PUBLISH in wf.step_names():
        labels = READBACK_CALL.findall(wf.step_script(PUBLISH))
        if labels != READBACK_LABELS:
            problems.append(f"the publish step reads back under the labels {labels}, not {READBACK_LABELS}")
    return problems


def problems_superseded_advice(wf: Workflow) -> list[str]:
    """Row 88: the superseded-release note has one source, the job env value
    SUPERSEDED_RELEASE_ADVICE, and the force input description repeats it
    once, verbatim. In the determine and publish steps every remedy line (an
    echo line naming a corrective new version, or the OLDER_TAG_ECHO or
    TAG_GONE_ECHO line) is followed, before its block ends at exit 1, else,
    fi or }, by exactly one SUPERSEDED_ECHO, the note prints nowhere else,
    and no script carries the note's words inline. The remedy and print
    counts are pinned, so the probe cannot pass empty. Residual: a remedy
    phrased without the word corrective is not found, the same residual as
    test_every_remedy_names_a_corrective_new_version; the behavioural tests
    are the guard that does not depend on wording. The constants it reads
    are declared with the other advice constants below; every call runs
    after import."""
    problems = []
    key = "SUPERSEDED_RELEASE_ADVICE"
    value = wf.job_env().get(key)
    if value != SUPERSEDED_RELEASE_ADVICE:
        problems.append(f"job {JOB!r} declares {key} as {value!r}, not the pinned note")
    copies = wf.text.count(SUPERSEDED_RELEASE_ADVICE)
    if copies != 2:
        problems.append(f"the note {key} appears {copies} times in the workflow, not 2 (the job env and the force input description)")
    description = wf.data.get("on", wf.data.get(True))["workflow_dispatch"]["inputs"]["force"]["description"]
    in_description = description.count(SUPERSEDED_RELEASE_ADVICE)
    if in_description != 1:
        problems.append(f"the force input description carries the note {key} {in_description} times, not once")
    close = "\" >" + chr(38) + "2"
    for name, (expected_remedies, expected_prints) in SUPERSEDED_SITES.items():
        script = wf.step_script(name)
        for phrase in SUPERSEDED_PHRASES:
            if phrase in script:
                problems.append(f"step {name!r} carries the note's words {phrase!r} inline; it prints {key} only through {SUPERSEDED_ECHO!r}")
        lines = script.splitlines()
        remedies = [i for i, line in enumerate(lines)
                    if ("echo " in line and "corrective" in line) or line.strip() in (OLDER_TAG_ECHO, TAG_GONE_ECHO)]
        if len(remedies) != expected_remedies:
            problems.append(f"step {name!r} names {len(remedies)} remedy lines, not the pinned {expected_remedies}")
        covered = set()
        for i in remedies:
            # The rest of the remedy line after its own echo, then each line
            # to the end of its block (that line included).
            tail = lines[i].split(close, 1)
            pieces = [tail[1] if len(tail) == 2 else ""]
            j = i
            while "exit 1" not in pieces[-1] and pieces[-1].strip() not in ("else", "fi", "}"):
                j += 1
                if j >= len(lines):
                    break
                pieces.append(lines[j])
            prints = "\n".join(pieces).count(SUPERSEDED_ECHO)
            if prints != 1:
                problems.append(f"step {name!r} line {i + 1} names a remedy that is followed by {prints} prints of {key}, not 1")
            covered.update(range(i, j + 1))
        total = script.count(SUPERSEDED_ECHO)
        inside = sum(lines[i].count(SUPERSEDED_ECHO) for i in covered)
        if total != inside:
            problems.append(f"step {name!r} prints {key} {total - inside} times outside a remedy block")
        if total != expected_prints:
            problems.append(f"step {name!r} prints {key} {total} times, not the pinned {expected_prints}")
    return problems


STRUCTURAL_CHECKS = (
    problems_layout, problems_step_list, problems_step_keys, problems_env,
    problems_runner_files, problems_setting_endpoint, problems_duplicate_keys,
    problems_republish, problems_superseded_advice,
)


def structural_problems(wf: Workflow) -> list[str]:
    return [problem for check in STRUCTURAL_CHECKS for problem in check(wf)]


WORKFLOW_TEXT = WORKFLOW.read_text(encoding="utf-8")
WF = Workflow(WORKFLOW_TEXT)
step_names = WF.step_names
step_script = WF.step_script
step_env = WF.step_env
step_keys = WF.step_keys
job_env = WF.job_env
github_env_writes = WF.github_env_writes


def script_reads(script: str) -> set[str]:
    """The upper-case variables a step script reads and does not set itself."""
    read = set(re.findall(r"\$\{?([A-Z_][A-Z0-9_]*)", script))
    assigned = set(re.findall(r"(?m)^\s*(?:local\s+|export\s+)?([A-Z_][A-Z0-9_]*)=", script))
    return read - assigned


# CALL_FORMS: every git and gh call the release workflow makes, by its
# exact shape, as 1 row each: the row name, the program, the arguments after
# the program, and the kind of the call. The kind is "read" for a call that
# changes neither a tag nor a release, and otherwise names the change: "tag"
# for a local tag, "push" for a push of the tag to origin, "create" for a
# release creation. Each argument is a template: its text matches only
# itself, and each slot of SLOTS in it matches the slot's pattern. A call
# matches a row only when it names the row's program and has exactly as many
# arguments as the row, each matching its template in full, so a call that
# adds an argument to a row, drops one or joins 2 does not match that row.
# The fakes of git and gh answer a call by the row it matches, and the call
# predicates below read a recorded call by the same row, so the routing is
# written once, here. A call that matches no row is off the table: the fake
# records it in the state file "unmodelled", gives no answer and exits 97,
# and run_step fails the run that made it unless the case opts out. The
# table states the call shapes of the workflow only; it does not model how
# git or gh read their options.
CALL_FORMS = (
    ("fetch", "git", ("fetch", "--quiet", "origin", "main"), "read"),
    ("show", "git", ("show", "FETCH_HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md"), "read"),
    ("status", "gh", ("api", "--include", "--silent", "repos/<REPO>/releases/tags/<TAG>"), "read"),
    ("published_at", "gh", ("api", "repos/<REPO>/releases/tags/<TAG>", "--jq", ".published_at"), "read"),
    ("lookup", "git", ("ls-remote", "origin", "refs/tags/<TAG>^{}", "refs/tags/<TAG>"), "read"),
    ("immutable", "gh", ("api", "repos/<REPO>/releases/tags/<TAG>", "--jq", ".immutable"), "read"),
    ("rev-parse", "git", ("rev-parse", "<COMMIT>^{commit}"), "read"),
    ("view", "gh", ("release", "view", "<TAG>", "--json", "assets", "--jq", ".assets[].name"), "read"),
    ("download", "gh", ("release", "download", "<TAG>", "--dir", "<DIR>", "--clobber",
                        "--pattern", "cleanlanguage.zip", "--pattern", "cleanlanguage.zip.sha256",
                        "--pattern", "cleanlanguage-<VERSION>.zip", "--pattern", "cleanlanguage-<VERSION>.zip.sha256"),
     "read"),
    ("tag", "git", ("tag", "<TAG>", "<COMMIT>"), "tag"),
    ("push", "git", ("push", "origin", "refs/tags/<TAG>"), "push"),
    ("tag-force", "git", ("tag", "-f", "<TAG>", "<COMMIT>"), "tag"),
    ("push-force", "git", ("push", "--force", "origin", "refs/tags/<TAG>"), "push"),
    ("create", "gh", ("release", "create", "<TAG>", "--verify-tag", "dist/cleanlanguage.zip",
                      "dist/cleanlanguage.zip.sha256", "dist/cleanlanguage-<VERSION>.zip",
                      "dist/cleanlanguage-<VERSION>.zip.sha256", "--title", "Clean Language <TAG>",
                      "--generate-notes"), "create"),
)
# The slots of the templates. No slot pattern matches a text that starts
# with -, so no slot takes an option.
SLOTS = {
    "<TAG>": r"v[0-9]+\.[0-9]+\.[0-9]+",
    "<VERSION>": r"[0-9]+\.[0-9]+\.[0-9]+",
    "<COMMIT>": r"[0-9a-f]{40}",
    "<REPO>": r"[A-Za-z0-9_.]+/[A-Za-z0-9_.]+",
    "<DIR>": r"/[^\n]*",
}
# The kind of each row, and the programs whose calls the table covers.
ROW_KINDS = {name: kind for name, _program, _template, kind in CALL_FORMS}
TABLE_PROGRAMS = ("git", "gh")


def token_matches(template, arg):
    """Whether arg matches the argument template in full: each slot by its
    pattern in SLOTS, and every other character as itself."""
    pattern = "".join(SLOTS.get(piece, re.escape(piece)) for piece in re.split(r"(<[A-Z]+>)", template))
    return re.fullmatch(pattern, arg) is not None


def row_of(program, args):
    """The name of the row of CALL_FORMS that the call of program with args
    matches, or None when it matches no row."""
    for name, row_program, template, _kind in CALL_FORMS:
        if row_program != program:
            continue
        if len(template) != len(args):
            continue
        if all(token_matches(piece, arg) for piece, arg in zip(template, args)):
            return name
    return None


# Every fake records its call in calls.log and reads its state files.
FAKE_COMMON = """
import hashlib, json, os, re, sys
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

# The fakes of git and gh then find the row of their call with the same
# CALL_FORMS, SLOTS and functions the predicates use. Each fake matches by
# the program it stands for, not by its file name, so a copy of the fake gh
# under another name answers as gh. A call that matches no row is recorded in
# "unmodelled" and refused with exit 97, with no answer and no other change.
FAKE_TABLE = """
CALL_FORMS = """ + repr(CALL_FORMS) + """
SLOTS = """ + repr(SLOTS) + "\n" + "".join(inspect.getsource(function) for function in (token_matches, row_of)) + """
ROW = row_of(PROGRAM, ARGS)
if ROW is None:
    with open(os.path.join(STATE, "unmodelled"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps([NAME, ARGS]) + "\\n")
    print("fake " + PROGRAM + ": call off the table CALL_FORMS: " + json.dumps(ARGS), file=sys.stderr)
    sys.exit(97)
"""

# The state files through which the fakes model a change: the local tag, the
# tag on origin, every release creation, which the fake gh appends to
# gh_writes, and every call off CALL_FORMS, which the fakes of git and gh
# append to unmodelled. A step that changed nothing and made no call off the
# table leaves all 4 as they were.
FAKE_WRITE_STATE = ("local_tag", "remote_tag", "gh_writes", "unmodelled")
# The seconds a step run allows the step, and every process that still holds
# the output of the step, to exit before the run fails its test, so a step
# that hangs, or that leaves a process holding its output, cannot hang the
# suite (see run_step). A case may lower it through step_run_limit.
STEP_RUN_LIMIT = 60
# The seconds a step run then waits in all, after the step exits, for the
# processes that still hold the pipe the step inherited to exit before the
# run fails its test. Bytes written to the pipe do not end the wait; only
# its end of file does. A process that closes the descriptors it inherited
# no longer holds the pipe, so it is not waited for, and a change it makes
# after the step exits is missed (see run_step). A case may lower it through
# step_process_wait.
STEP_PROCESS_WAIT = 60

FAKE_GH = FAKE_COMMON + "PROGRAM = \"gh\"\n" + FAKE_TABLE + """
# Each API row is answered from the same state, so the exact path each call
# names is logged for ApiPathTest to pin: the status probe prints its status
# line, and a field read prints the value of its field.
if ROW == "status":
    with open(os.path.join(STATE, "api.log"), "a", encoding="utf-8") as log:
        log.write(json.dumps(["status", [ARGS[-1]]]) + "\\n")
    status = read("status", "404")
    print("HTTP/2.0 " + status + " Fake")
    sys.exit(0 if status == "200" else 1)
if ROW in ("published_at", "immutable"):
    with open(os.path.join(STATE, "api.log"), "a", encoding="utf-8") as log:
        log.write(json.dumps(["." + ROW, [ARGS[1]]]) + "\\n")
    value = read(ROW, "null")
    if value == "FAIL":
        sys.exit(1)
    print(value)
    sys.exit(0)
# Every release row is logged with its arguments after the subcommand, so the
# tag each release read and the create call name is pinned by ApiPathTest.
with open(os.path.join(STATE, "release.log"), "a", encoding="utf-8") as log:
    log.write(json.dumps([ARGS[1], ARGS[2:]]) + "\\n")
VERSION = os.environ.get("VERSION", "")
ASSETS = ["cleanlanguage.zip", "cleanlanguage.zip.sha256",
          "cleanlanguage-" + VERSION + ".zip", "cleanlanguage-" + VERSION + ".zip.sha256"]
# The state file "missing" names assets the published release lacks,
# "corrupt" names zips whose published bytes no longer match their manifest,
# and "differ" names zips published with other bytes and a manifest that
# matches them, so the two zips differ while each manifest stays valid.
MISSING = read("missing").split()
# "extra" is a count of further assets listed after the
# required ones. Each name is about 200 bytes, so 1000 of them overflow a
# 64 KiB pipe buffer many times over and a reader that exits on its first
# match always leaves its writer with bytes still to write.
EXTRA = ["extra-asset-%04d-" % index + "x" * 180 + ".txt" for index in range(int(read("extra", "0")))]
CORRUPT = read("corrupt").split()
DIFFER = read("differ").split()
if ROW == "view":
    print("\\n".join([asset for asset in ASSETS if asset not in MISSING] + EXTRA))
    sys.exit(0)
if ROW == "download":
    target = ARGS[ARGS.index("--dir") + 1]
    for asset in ASSETS:
        zip_name = asset[: -len(".sha256")] if asset.endswith(".sha256") else asset
        data = b"published zip bytes" + (b" differ" if zip_name in DIFFER else b"")
        with open(os.path.join(target, asset), "wb") as handle:
            if asset.endswith(".sha256"):
                handle.write((hashlib.sha256(data).hexdigest() + "  " + zip_name + "\\n").encode("utf-8"))
            else:
                handle.write(data + (b" altered" if asset in CORRUPT else b""))
    sys.exit(0)
if ROW == "create":
    # The release creation is appended to gh_writes, whatever the call log
    # holds, so a no-change assertion can read the fake's own state.
    with open(os.path.join(STATE, "gh_writes"), "a", encoding="utf-8") as writes:
        writes.write(json.dumps(ARGS) + "\\n")
sys.exit(0)
"""

FAKE_VCS = FAKE_COMMON + "PROGRAM = \"git\"\n" + FAKE_TABLE + """
# The fetch row has no answer and no effect.
if ROW == "show":
    # The state file "main_skill" is the SKILL.md of main.
    print(read("main_skill"), end="")
elif ROW == "lookup":
    # The state file "ls_remote" set to FAIL makes the lookup itself fail.
    if read("ls_remote") == "FAIL":
        sys.exit(128)
    tag = read("remote_tag")
    if tag:
        print(tag + "\\t" + ARGS[-1])
elif ROW == "rev-parse":
    print(read("commit"))
elif ROW in ("tag", "tag-force"):
    # The local tag points at the commit named last.
    with open(os.path.join(STATE, "local_tag"), "w", encoding="utf-8") as handle:
        handle.write(ARGS[-1])
elif ROW in ("push", "push-force"):
    # The push moves the tag on origin to the local tag, so a later run reads
    # the tag where an earlier run left it.
    with open(os.path.join(STATE, "remote_tag"), "w", encoding="utf-8") as handle:
        handle.write(read("local_tag"))
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

# A copy of the real extractor that crashes inside extract, after the probe
# has passed, to show an internal error is reported as the extractor failing.
CRASH_HOOK = (
    "import unicodedata as _crash_mod\n"
    "def _crash(*args, **kwargs):\n"
    "    raise RuntimeError(\"injected internal error\")\n"
    "_crash_mod.category = _crash\n"
)

# Row 89: a copy of the real extractor whose --json mode breaks for one op
# only, in the way the mode names, while every other op still answers, and
# whose CLI content modes exit 1, so the probe passes and a step that still
# read the CLI would take the content as malformed.
BROKEN_HOOK = """
_real_json_main = json_main
def json_main():
    data = sys.stdin.buffer.read()
    request = json.loads(data.decode("utf-8"))
    if request["op"] != {op!r}:
        sys.stdin = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        return _real_json_main()
{body}
_real_main = main
def main(argv):
    if argv[1:] in (["--baseline"], ["--json"]):
        return _real_main(argv)
    return 1
"""
BROKEN_MODES = {
    "exit1": "    raise SystemExit(1)",
    "notjson": "    print(\"not json\")\n    return 0",
    "otherop": "    print(json.dumps({\"op\": \"baseline\", \"outcome\": \"value\", \"value\": \"1.0.14\"}))\n    return 0",
    "badvalue": "    print(json.dumps({\"op\": request[\"op\"], \"outcome\": \"value\", \"value\": \"2026-11-15 \"}))\n    return 0",
    "refused": "    print(json.dumps({\"op\": request[\"op\"], \"outcome\": \"refused\", \"message\": \"x\"}))\n    return 0",
}

# What a step that still read the CLI would print for the broken copy.
VERDICT_TEXTS = ("is malformed", "Could not read", "rejected the version", "unexpected answer",
                 "not a usable UTC instant", "Refusing to publish", "IS PUBLISHED on a different UTC day")


class WorkflowStepTest(unittest.TestCase):
    step_run_limit = STEP_RUN_LIMIT
    step_process_wait = STEP_PROCESS_WAIT

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
        shutil.copy2(CLIENT, self.work / "tools" / "skill-release-date-client.py")
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
            if value is None:
                (self.state / key).unlink(missing_ok=True)
            else:
                (self.state / key).write_text(value, encoding="utf-8")

    def skill(self, text: str):
        (self.work / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md").write_text(text, encoding="utf-8")

    def crash_extractor(self):
        target = self.work / "tools" / "skill-release-date.py"
        text = target.read_text(encoding="utf-8")
        anchor = "from pathlib import Path\n"
        self.assertEqual(text.count(anchor), 1)
        target.write_text(text.replace(anchor, anchor + CRASH_HOOK), encoding="utf-8")

    def break_extractor(self, op: str, mode: str):
        target = self.work / "tools" / "skill-release-date.py"
        text = EXTRACTOR.read_text(encoding="utf-8")
        guard = "\nif __name__ == \"__main__\":\n"
        self.assertEqual(text.count(guard), 1)
        target.write_text(text.replace(guard, BROKEN_HOOK.format(op=op, body=BROKEN_MODES[mode]) + guard),
                          encoding="utf-8")

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
        # The runner precedence between a step or job env: key and a value an
        # earlier step wrote to GITHUB_ENV is not modelled here, so no such
        # overlap is allowed: the order of the updates below cannot matter.
        overlap = set(job).union(step).intersection(written)
        self.assertFalse(overlap, f"step {name!r} declares env keys an earlier step writes to GITHUB_ENV: {sorted(overlap)}")
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

    def fake_write_state(self):
        """The fakes' tag, write and off-table state (FAKE_WRITE_STATE), each
        file's text or None."""
        return {name: (self.state / name).read_text(encoding="utf-8") if (self.state / name).exists() else None
                for name in FAKE_WRITE_STATE}

    def run_step(self, name: str, script_text: str | None = None, bash_options: tuple = (),
                 off_table: str | None = None):
        """Run the step name, or script_text in its place, and return its exit
        code, output and error output. A run in which the fake git or gh
        records a call off CALL_FORMS fails its test, whatever the step's exit
        code, unless the case opts out by giving off_table, the reason it
        makes such a call on purpose."""
        env = self.step_environment(name)
        self.env_file.write_text("", encoding="utf-8")
        # The fake state as the run found it, for a later no-change assertion.
        self.state_before_run = self.fake_write_state()
        script = self.state / "step.sh"
        script.write_text(step_script(name) if script_text is None else script_text, encoding="utf-8")
        # The step and the processes it starts inherit the write end of this
        # pipe, so its read end reaches end of file only when every process
        # holding that end has exited: a change that such a process, left
        # running in the background, makes after the step exits is in the
        # state a later assertion reads. Such a process may also write to
        # the pipe, so the wait reads the pipe until its end of file: a byte
        # that makes it readable does not end the wait. A process that
        # closes the descriptors it inherited no longer holds the pipe, so
        # this wait does not cover it, and a change it makes after the step
        # exits is missed. The run itself ends at step_run_limit: a step that
        # is still running then, or that has left a process still holding
        # its output, fails the test rather than hanging the suite or passing
        # once that process exits.
        done_read, done_write = os.pipe()
        try:
            try:
                proc = subprocess.run(
                    ["bash", "--noprofile", "--norc", *bash_options, "-eo", "pipefail", str(script)],
                    cwd=self.work, env=env, capture_output=True, text=True, pass_fds=(done_write,),
                    timeout=self.step_run_limit,
                )
            except subprocess.TimeoutExpired:
                raise self.failureException(
                    f"step {name!r}, or a process it left holding its output, was still running"
                    f" {self.step_run_limit} s after the step started") from None
            os.close(done_write)
            done_write = None
            deadline = time.monotonic() + self.step_process_wait
            while True:
                left = deadline - time.monotonic()
                ready = select.select([done_read], [], [], left)[0] if left > 0 else []
                self.assertTrue(ready, f"step {name!r} left a process running {self.step_process_wait} s after it exited")
                if not os.read(done_read, 4096):
                    break
        finally:
            os.close(done_read)
            if done_write is not None:
                os.close(done_write)
        # An unknown call is never harmless: a call off the table, recorded by
        # the fake that refused it, fails the run unless the case opted out.
        unmodelled = self.fake_write_state()["unmodelled"]
        if unmodelled != self.state_before_run["unmodelled"] and off_table is None:
            raise self.failureException(f"step {name!r} made a call off the table CALL_FORMS: {unmodelled}")
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

    def assert_superseded_advice(self, text: str, times: int = 1):
        """Row 88: the note follows a corrective-version remedy exactly once,
        and never prints on a path that names no such remedy (times=0)."""
        self.assertEqual(text.count(SUPERSEDED_RELEASE_ADVICE), times, text)


# An unconditional claim that a release or its assets are immutable, or that
# nothing (or no workflow) can republish one. Its close variants count too:
# up to three words (an adverb such as always, permanently or forever) may
# stand between the verb and the adjective, the verb may be stay or remain,
# never mutable or not mutable counts as immutable, no one and nobody count as
# nothing, and can not and can't count as cannot. Row 87: a pair of commas may
# set off an aside of up to three words right after the verb (a single comma
# elsewhere ends the claim, so "is published, but its immutable field" is not
# one), and up to three words may follow the aside, no-one counts as no one, and
# could not, couldn't, will not, won't and can, could or will never count as
# cannot, and one word (such as ever or again) may stand before be republished.
IMMUTABILITY_CLAIM = re.compile(
    r"\b(releases?|assets?)\b[^.;:]*\b(is|are|stays?|remains?)"
    r"(\s+(\w+\s+){0,3}?|\s*,\s*(\w+\s+){0,2}\w+\s*,\s*(\w+\s+){0,3}?)"
    r"(immutable|never\s+mutable|not\s+mutable)\b"
    r"|\b(nothing|no[\s-]+one|nobody|no\s+(other\s+)?workflow|no\s+run)\b[^.;]*\brepublish"
    r"|\b(can(\s*not|\Wt)|could(\s*not|n\Wt)|will\s+not|won\Wt|(can|could|will)\s+never)"
    r"\s+(\w+\s+)?be\s+republished\b",
    re.IGNORECASE)
# The printed lines whose truth the workflow establishes first, by their exact
# text: the readback line printed after the immutable check, the day-mismatch
# line printed only after it, and the conditional re-stamping line.
IMMUTABILITY_CLAIM_ALLOWED = (
    "echo \"$1: release ${RELEASE_TAG} is immutable; it carries no Released line, so no publication day is checked.\"",
    "echo \"The published zip carries Released: ${RELEASE_DATE}, and an immutable release cannot be republished,"
    " so the remedy is a corrective new version whose Released line names its own publication day."
    " The live release checksum check compares a Released date with a publication day only for the"
    " version that cleanlanguage/skills/cleanlanguage/SKILL.md names in the checkout the check runs from,"
    " so it checks the date of ${RELEASE_TAG} only while that file names that version, and it reports a"
    " mismatch whenever it compares the 2 days and finds them different (see the exit codes listed in the"
    " module docstring of that check for its other outcomes).\" >" + chr(38) + "2",
    "echo \"Re-stamping the Released line cannot fix this: the published zip carries the Released line of the"
    " commit it was built from, and an immutable release cannot be republished. If the line at this commit"
    " was edited after the release, restore the value the published zip carries; otherwise the remedy is a"
    " corrective new version whose Released line names its own publication day.\" >" + chr(38) + "2",
)
CLAIM_MUTANT = "echo \"Every published release is immutable, so no workflow can republish it.\" >" + chr(38) + "2"


def immutability_claims(text: str) -> list[str]:
    """The lines of text, comments excluded, that make an immutability claim
    and are not allowed by their exact text."""
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped in IMMUTABILITY_CLAIM_ALLOWED:
            continue
        if IMMUTABILITY_CLAIM.search(stripped):
            found.append(stripped)
    return found


def ignore_lookup_failure(script: str) -> str:
    """The mutant that appends || true to the one tag lookup in a step."""
    lookup = [l for l in script.splitlines() if l.strip().startswith("remote_tag_sha=\"$(" + VCS + " ls-remote ")]
    assert len(lookup) == 1, lookup
    return script.replace(lookup[0], lookup[0] + " || true", 1)


# Each predicate of a git or gh call reads a recorded call by the row of
# CALL_FORMS it matches, through row_of, the function the fakes use, so a
# call off the table is no tag, push, create, lookup or field read. is_date
# reads only the command name, since the table does not cover date.
def row_of_call(call):
    return row_of(call[0], call[1])


def kind_of(call):
    """The kind of the row of a recorded call, or None for a call off the table."""
    return ROW_KINDS.get(row_of_call(call))


def is_push(call):
    return kind_of(call) == "push"


def is_create(call):
    return kind_of(call) == "create"


def is_tag(call):
    return kind_of(call) == "tag"


def is_lookup(call):
    return row_of_call(call) == "lookup"


def is_mutation(call):
    """A git or gh call that is not a read of the table: a change, or a call
    off the table, which is never counted as harmless."""
    return call[0] in TABLE_PROGRAMS and kind_of(call) != "read"


def is_date(call):
    return call[0] == "date"


def is_field_read(field):
    """A gh api call of the row that reads field (published_at or immutable)."""
    def reads(call):
        return row_of_call(call) == field
    return reads


def is_tag_operation(call):
    return is_tag(call) or is_push(call)


# Extractors that cannot run at all: the interpreter fails before main, on a
# SyntaxError or on an import that raises ModuleNotFoundError.
BROKEN_EXTRACTORS = (
    ("syntax-broken", "def broken(:\n"),
    ("import-broken", EXTRACTOR.read_text(encoding="utf-8").replace(
        "from pathlib import Path\n", "from pathlib import Path\nimport cleanlanguage_no_such_module\n", 1)),
)

# Row 72: the remedy the not-immutable readback refusal names.
REMEDY_NOT_IMMUTABLE = "Turn on immutable releases for the repository, then cut a corrective new version."

# The next step the unreadable readback refusals name (row 78
# adds the determine-step refusal), and the verification path the force
# refusal names. The force and moved-tag refusals name that
# verifying dispatch first, and a corrective new version only if the
# verification fails. Repeating a run keeps its
# force input and run ref, so each names a fresh dispatch without force at
# the tag itself.
REMEDY_UNREADABLE = ("Once the release record is readable, dispatch this workflow again with the force input"
                     " unchecked and the tag v1.0.15 itself selected as the run ref, not main, to verify the"
                     " published release.")
VERIFY_BY_DISPATCH = ("To verify the published release, first check that .github/workflows/release-skill.yml"
                      " at the tag v1.0.15 has the step " + PUBLISH + ". If it does, dispatch this"
                      " workflow again with the force input unchecked and the tag v1.0.15 itself selected as"
                      " the run ref, not main; cut a corrective new version only if that verification fails.")

# A dispatch at the tag runs the workflow stored at the tag, and a
# workflow without the publish step name above (older than item 57) can
# republish. So the refusals of a run that is not at the tag name the
# verifying dispatch only for a tag carrying that step, and for any other tag
# forbid a dispatch at it and name a read-only check. The readback refusals
# (REMEDY_UNREADABLE) run at the tag commit, which carries this workflow.
# OLDER_TAG_ADVICE is the single advice text for such a tag, declared once
# in the job env, printed by both sites and repeated in the description. It
# names the authority, the release step of the workflow at that tag, and no
# procedure: no command, file or path.
OLDER_TAG_ADVICE = ("A tag without the step " + PUBLISH + " carries an older workflow that can"
                    " republish a published release, so never dispatch this workflow at such a tag, or repeat"
                    " any of its runs, with or without the force input; its step texts that advise a republish"
                    " do not apply. Check such a release by hand, read-only: it passes only if it is immutable,"
                    " it has every asset the workflow at that tag publishes, each published checksum matches its"
                    " asset, and each asset passes the checks that workflow made on it, in its packaging steps as"
                    " well as its release step. The check is against what that workflow verified when it"
                    " published, never against a fresh rebuild: a rebuild with another toolchain can differ, so"
                    " a mismatch proves nothing. A command that fails to run is run again and says"
                    " nothing about the release. If the release fails that check, turn on immutable releases if"
                    " they are off, then cut a corrective new version.")
# Each condition the advice states, pinned by its words; the
# advice reaches all 3 sites from one source, so each is pinned at each.
ADVICE_CONDITIONS = (
    "never dispatch this workflow at such a tag, or repeat any of its runs, with or without the force input",
    "its step texts that advise a republish do not apply",
    "Check such a release by hand, read-only",
    "it passes only if it is immutable",
    "it has every asset the workflow at that tag publishes",
    "each published checksum matches its asset",
    "each asset passes the checks that workflow made on it",
    "in its packaging steps as well as its release step",
    "The check is against what that workflow verified when it published, never against a fresh rebuild:"
    " a rebuild with another toolchain can differ, so a mismatch proves nothing.",
    "A command that fails to run is run again and says nothing about the release.",
    "If the release fails that check, turn on immutable releases if they are off, then cut a corrective new"
    " version.",
)
NEVER_AT_OLDER_TAG = OLDER_TAG_ADVICE
OLDER_TAG_ECHO = "echo \"${OLDER_TAG_ADVICE}\" >" + chr(38) + "2"
# The tag-gone text, declared once in the job env and printed by
# both steps with <tag> replaced.
TAG_GONE_ADVICE = ("The tag <tag> is no longer on origin, so no dispatch can select it as the run ref to"
                   " verify the published release; cut a corrective new version.")
TAG_GONE_ECHO = "echo \"${TAG_GONE_ADVICE//<tag>/${RELEASE_TAG}}\" >" + chr(38) + "2"
# Row 88: the one note every corrective-version remedy a run can reach for
# an older release prints after it. Declared once in the job env, printed by
# both steps only through SUPERSEDED_ECHO, and repeated verbatim at the end
# of the force input description, as OLDER_TAG_ADVICE is. It is conditional
# in its own words, so the first-publication readback prints it too.
SUPERSEDED_RELEASE_ADVICE = ("A corrective new version repairs only the latest release. If a later version"
                             " supersedes the release that failed, report the failure of that older release"
                             " to the maintainer.")
SUPERSEDED_ECHO = "echo \"${SUPERSEDED_RELEASE_ADVICE}\" >" + chr(38) + "2"
# Words of the note that no step script may carry inline, so a reworded copy
# is caught as well as a verbatim one. None appears in either script today.
SUPERSEDED_PHRASES = ("latest release", "older release", "to the maintainer")
# Per step: the remedy lines the note follows (an echo line that names a
# corrective new version, or the OLDER_TAG_ECHO or TAG_GONE_ECHO line) and
# the prints of the note. Pinned so the probe cannot pass empty.
SUPERSEDED_SITES = {DETERMINE: (4, 3), PUBLISH: (9, 8)}
# A command name, or a file name, path or archive the advice must not carry.
ADVICE_NAMES_A_PROCEDURE = re.compile(
    r"\b(gh|git|sha256sum|cmp|unzip|zip|curl)\b|\.(zip|sha256|md|ya?ml)\b|/|--")
DETERMINE_UNREADABLE = ("Once the release record is readable, check that .github/workflows/release-skill.yml"
                        " at the tag v1.0.15 has the step " + PUBLISH + ". If it does, dispatch this"
                        " workflow again with the force input unchecked and the tag v1.0.15 itself selected"
                        " as the run ref, not main, to verify the published release; cut a corrective"
                        " new version only if that verification fails.")

# A published release whose publication day is not its Released
# day is refused in the determine step, naming the remedy, not the packager
# re-stamp advice, which leads back to the same verifying dispatch.
PUBLISHED_ON_ANOTHER_DAY = ("Re-stamping the Released line cannot fix this: the published zip carries the"
                            " Released line of the commit it was built from, and an immutable release"
                            " cannot be republished. If the line at this commit was edited after the"
                            " release, restore the value the published zip carries; otherwise the remedy"
                            " is a corrective new version whose Released line names its own publication"
                            " day.")

# The remedy both refusals name when the tag of a published
# release is no longer on origin, so no dispatch can select it.
TAG_GONE = ("The tag v1.0.15 is no longer on origin, so no dispatch can select it as the run ref to"
            " verify the published release; cut a corrective new version.")

# The readback outcomes that must fail a dated run on any path.
BAD_READBACKS = (
    ("immutable false", {"immutable": "false"}, "immutable field reads false"),
    ("immutable null", {"immutable": "null"}, "immutable field reads null"),
    ("immutable missing", {"immutable": None}, "immutable field reads null"),
    ("immutable empty", {"immutable": ""}, "immutable field reads empty"),
    ("immutable unreadable", {"immutable": "FAIL"}, "immutable field could not be read back"),
    ("wrong day", {"published_at": "2026-11-16T00:00:02Z"}, "IS PUBLISHED on a different UTC day"),
)


class HarnessTest(WorkflowStepTest):
    """The harness itself is as strict as the runner."""

    def test_every_extractor_launch_goes_through_the_client(self):
        # Row 89: no step runs the extractor CLI; each of the 7 calls runs
        # the client, isolated.
        self.assertNotIn(EXTRACTOR_NAME, "tools/skill-release-date-client.py")
        self.assertEqual(extractor_mentions(WORKFLOW_TEXT), list(WORKFLOW_MENTIONS))
        self.assertEqual(WORKFLOW_TEXT.count("python3 -I tools/skill-release-date-client.py"), 7)
        for probe in LAUNCH_PROBES:
            with self.subTest(probe=probe):
                injected = WORKFLOW_TEXT + "".join("          " + line + "\n" for line in probe.split("\n"))
                self.assertNotEqual(extractor_mentions(injected), list(WORKFLOW_MENTIONS))

    def test_every_other_client_launch_fails_the_check(self):
        self.assertEqual(client_mentions(WORKFLOW_TEXT), list(WORKFLOW_CLIENT_MENTIONS))
        for probe in CLIENT_LAUNCH_PROBES:
            with self.subTest(probe=probe):
                injected = WORKFLOW_TEXT + "".join("          " + line + "\n" for line in probe.split("\n"))
                self.assertNotEqual(client_mentions(injected), list(WORKFLOW_CLIENT_MENTIONS))

    def test_fake_date_refuses_a_call_without_utc(self):
        proc = subprocess.run([str(self.bin / "date"), "+%F"], env={"FAKE_STATE": str(self.state)},
                              capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("without -u", proc.stderr)

    def test_each_row_changes_the_fake_state_exactly_when_its_kind_is_a_change(self):
        # The fakes answer a call by its row, and the predicates count it by
        # the kind of that row. For each row, a call built from its template
        # matches that row, and the fake changes the tag or write state for
        # it exactly when the kind of the row is not read, as is_mutation
        # counts it, so a change labelled as a read, or a read labelled as a
        # change, fails here. No call of this case is off the table.
        target = self.root / "download"
        target.mkdir()
        sample = {"<TAG>": "v1.0.15", "<VERSION>": "1.0.15", "<COMMIT>": COMMIT,
                  "<REPO>": "jposluns/cleanlanguage", "<DIR>": str(target)}
        self.assertEqual(set(sample), set(SLOTS))
        for name, program, template, kind in CALL_FORMS:
            with self.subTest(row=name):
                args = [re.sub(r"<[A-Z]+>", lambda slot: sample[slot.group(0)], piece) for piece in template]
                self.assertEqual(row_of(program, args), name)
                self.set_state(local_tag=None, remote_tag=OTHER_COMMIT, gh_writes=None, unmodelled=None,
                               status="200")
                before = self.fake_write_state()
                subprocess.run([str(self.bin / program), *args],
                               env={"FAKE_STATE": str(self.state), "VERSION": "1.0.15"},
                               capture_output=True, text=True)
                after = self.fake_write_state()
                self.assertIsNone(after["unmodelled"], after)
                self.assertEqual(after != before, kind != "read", (before, after))
                self.assertEqual(is_mutation([program, args]), kind != "read")

    def test_every_row_of_the_table_is_a_call_the_workflow_makes(self):
        # The runs below take the paths on which the workflow makes its git
        # and gh calls: the validate step, the determine step on a published
        # release, and the publish step on a first publication by dispatch,
        # on a forced move of the tag of an unpublished release and on a
        # re-run. Each run fails if a call it makes is off the table, and the
        # rows its calls match, together, are exactly the rows of CALL_FORMS,
        # so a row that no run reaches fails here.
        shutil.copy2(REPO / "tools" / "skill-version.py", self.work / "tools" / "skill-version.py")
        self.set_state(main_skill="Version: 1.0.15  \n")
        runs = (
            (VALIDATE, {}, "false"),
            (DETERMINE, {"status": "200"}, "false"),
            (PUBLISH, {"status": "404", "remote_tag": None}, "false"),
            (PUBLISH, {"status": "404", "remote_tag": OTHER_COMMIT}, "true"),
            (PUBLISH, {"status": "200", "remote_tag": COMMIT}, "false"),
        )
        rows = set()
        for name, state, force in runs:
            self.reset_calls()
            self.set_state(**state)
            self.inputs["force"] = force
            code, _out, err = self.run_step(name)
            self.assertEqual(code, 0, err)
            rows |= {row_of_call(call) for call in self.calls() if call[0] in TABLE_PROGRAMS}
        self.assertEqual(rows, set(ROW_KINDS))

    def test_a_step_still_running_at_the_limit_fails_its_test(self):
        # With the limit lowered to 1 s, a step that runs for 5 s fails its
        # test at the limit with a message naming the step. The step is the
        # sleep itself, through exec, so the run stops it and leaves no
        # process behind.
        self.step_run_limit = 1
        start = time.monotonic()
        with self.assertRaises(self.failureException) as raised:
            self.run_step(PUBLISH, "exec sleep 5\n")
        self.assertLess(time.monotonic() - start, 4)
        self.assertEqual(str(raised.exception),
                         f"step {PUBLISH!r}, or a process it left holding its output, was still running"
                         " 1 s after the step started")

    def test_a_process_still_holding_the_pipe_after_the_wait_fails_its_test(self):
        # With the wait lowered to 1 s, a step that exits at once but leaves
        # a background process holding the pipe for about 3 s fails its test
        # once that 1 s has passed in all, with a message naming the step.
        # The process is a Python child that writes 1 byte to each descriptor
        # from 3 to 254 that it can write, every 0.3 s, so the pipe becomes
        # readable many times during the wait: a wait that restarts its limit
        # on each read, or that has no limit, would pass once the process
        # exits. Its output goes to /dev/null, so it does not hold the output
        # of the step, and the step limit does not apply.
        self.step_process_wait = 1
        writer = ("import os, time\n"
                  "for _ in range(10):\n"
                  "    for fd in range(3, 255):\n"
                  "        try:\n"
                  "            os.write(fd, b\"x\")\n"
                  "        except OSError:\n"
                  "            pass\n"
                  "    time.sleep(0.3)\n")
        script = "\"" + sys.executable + "\" -I -c '" + writer + "' >/dev/null 2>&1 &\nexit 0\n"
        start = time.monotonic()
        with self.assertRaises(self.failureException) as raised:
            self.run_step(PUBLISH, script)
        self.assertLess(time.monotonic() - start, 2.5)
        self.assertIn(f"step {PUBLISH!r} left a process running 1 s after it exited", str(raised.exception))

    def test_every_variable_a_step_reads_is_declared(self):
        for name in (VALIDATE, DETERMINE, PACKAGE, PUBLISH):
            with self.subTest(name):
                self.step_environment(name)

    def test_the_declarations_the_steps_rely_on_are_in_the_workflow(self):
        self.assertEqual(set(job_env()), {"RELEASE_TAG", "OLDER_TAG_ADVICE", "TAG_GONE_ADVICE", "SUPERSEDED_RELEASE_ADVICE"})
        self.assertEqual(set(step_env(VALIDATE)), set())
        self.assertEqual(set(step_env(DETERMINE)), {"GH_TOKEN"})
        self.assertEqual(set(step_env(PACKAGE)), set())
        self.assertEqual(set(step_env(PUBLISH)), {"GH_TOKEN", "FORCE"})
        self.assertEqual(github_env_writes(DETERMINE), {"VERSION"})
        self.assertEqual(github_env_writes(PACKAGE), {"VERSION", "RELEASE_DATED", "RELEASE_DATE"})

    def test_no_env_key_overlaps_an_earlier_github_env_write(self):
        # The result must not depend on runner precedence between a step
        # or job env: key and GITHUB_ENV, which these tests do not model.
        for name in MODELLED:
            with self.subTest(name):
                written = github_env_writes(name)
                self.assertEqual(set(job_env()).union(step_env(name)).intersection(written), set())

    def test_modelled_steps_carry_only_modelled_keys(self):
        # A step-level if or continue-on-error is not modelled, so it fails.
        self.assertEqual(step_keys(VALIDATE), {"name", "shell", "run"})
        self.assertEqual(step_keys(DETERMINE), {"name", "env", "shell", "run"})
        self.assertEqual(step_keys(PACKAGE), {"name", "shell", "run"})
        self.assertEqual(step_keys(PUBLISH), {"name", "env", "shell", "run"})
        for name in MODELLED:
            with self.subTest(name):
                keys = step_keys(name)
                self.assertFalse(keys.intersection({"if", "continue-on-error"}), f"step {name!r} carries {sorted(keys)}")
                self.assertLessEqual(keys, MODELLED_STEP_KEYS)

    def test_the_workflow_has_exactly_the_pinned_steps(self):
        self.assertEqual(step_names(), EXPECTED_STEPS)
        self.assertEqual(problems_step_list(WF), [])

    def test_every_step_carries_its_pinned_keys(self):
        self.assertEqual(problems_step_keys(WF), [])
        self.assertEqual(problems_layout(WF), [])

    def test_modelled_steps_run_under_bash(self):
        for name in MODELLED:
            with self.subTest(name):
                self.assertEqual(WF.step(name)["shell"], "bash")

    def test_env_declarations_and_writes_hold_on_the_parsed_data(self):
        self.assertEqual(problems_env(WF), [])

    def test_only_the_writer_steps_name_github_env(self):
        self.assertEqual(problems_runner_files(WF), [])
        self.assertEqual(len(CANONICAL_WRITE.findall(step_script(VALIDATE))), 1)
        self.assertEqual(len(CANONICAL_WRITE.findall(step_script(DETERMINE))), 4)

    def test_the_workflow_has_no_duplicate_key(self):
        self.assertEqual(problems_duplicate_keys(WF), [])

    def test_every_structural_check_passes(self):
        self.assertEqual(structural_problems(WF), [])


class PublishStepTest(WorkflowStepTest):
    """The publication-time checks of the publish step."""

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
        self.assertIn("skill-release-date: refusing to start publishing: only 300 seconds remain", err)

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
        self.assert_superseded_advice(err, 0)

    def test_readback_of_a_different_day_fails_loudly_naming_both_days(self):
        self.runner["GITHUB_EVENT_NAME"] = "push"
        self.set_state(remote_tag=COMMIT, published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertTrue(any(is_create(c) for c in self.calls()))
        self.assertIn("published on 2026-11-16", err)
        self.assertIn("names 2026-11-15", err)
        self.assertIn("IS PUBLISHED on a different UTC day", err)
        self.assertIn("skill-release-date: the release was published on 2026-11-16 (UTC; published_at "
                      "2026-11-16T00:00:02Z), but its Released line names 2026-11-15", err)
        self.assertIn("The live release checksum check compares a Released date with a publication day only for "
                      "the version that cleanlanguage/skills/cleanlanguage/SKILL.md names in the checkout the check "
                      "runs from, so it checks the date of v1.0.15 only while that file names that version, and it "
                      "reports a mismatch whenever it compares the 2 days and finds them different (see the exit "
                      "codes listed in the module docstring of that check for its other outcomes).",
                      err)

    def test_readback_mismatch_names_a_corrective_new_version_and_no_republish(self):
        # An immutable release cannot be republished.
        self.set_state(published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("the remedy is a corrective new version", err)
        self.assert_superseded_advice(err)
        self.assertNotIn("force", err)
        self.assertNotIn("republish with", err)

    def test_unreadable_readback_fails_loudly(self):
        self.set_state(published_at="FAIL")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("could not be read back", err)
        self.assertIn(REMEDY_UNREADABLE, err)
        self.assert_superseded_advice(err, 0)

    def test_a_release_that_is_not_immutable_fails(self):
        # With no pre-check, the first-publication readback is the only
        # immutability check, and every value but exactly true refuses.
        for event, remote_tag in (("workflow_dispatch", ""), ("push", COMMIT)):
            for value in ("false", "null", None, "", "True", "TRUE", "1", " true", "true false", "FAIL"):
                with self.subTest(event=event, value=value):
                    self.reset_calls()
                    self.runner["GITHUB_EVENT_NAME"] = event
                    self.set_state(immutable=value, remote_tag=remote_tag)
                    code, out, err = self.run_step(PUBLISH)
                    self.assertEqual(code, 1, err)
                    if value == "FAIL":
                        self.assertIn("immutable field could not be read back", err)
                        self.assertIn(REMEDY_UNREADABLE, err)
                        self.assert_superseded_advice(err, 0)
                    else:
                        self.assertIn("immutable field reads ", err)
                        self.assertIn(REMEDY_NOT_IMMUTABLE, err)
                        self.assertNotIn(REMEDY_UNREADABLE, err)
                        self.assert_superseded_advice(err)
                    self.assertNotIn("the day its Released line names", out)
                    calls = self.calls()
                    self.assertLess(self.index_of(calls, is_create), self.index_of(calls, is_field_read("immutable")))
                    self.assertFalse(any(is_field_read("published_at")(c) for c in calls), calls)

    def undated(self):
        self.carried["RELEASE_DATED"] = "0"
        self.carried["RELEASE_DATE"] = ""
        self.set_state(clock="2026-11-15T23:59:59Z", published_at="2026-11-16T00:00:02Z")

    def test_undated_release_checks_no_date_but_reads_back_immutability(self):
        # Item 57: an undated release checks no date, but its first
        # publication still ends green only on an immutable record.
        for event, remote_tag in (("workflow_dispatch", ""), ("push", COMMIT)):
            with self.subTest(event):
                self.reset_calls()
                self.runner["GITHUB_EVENT_NAME"] = event
                self.undated()
                self.set_state(remote_tag=remote_tag)
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 0, err)
                calls = self.calls()
                self.assertLess(self.index_of(calls, is_create), self.index_of(calls, is_field_read("immutable")))
                self.assertFalse(any(is_date(c) for c in calls), calls)
                self.assertFalse(any(is_field_read("published_at")(c) for c in calls), calls)
                self.assertIn("First-publication readback: release v1.0.15 is immutable", out)

    def test_undated_release_that_is_not_immutable_fails(self):
        # Item 57: the immutable readback fails closed on an undated release
        # exactly as on a dated one.
        for event, remote_tag in (("workflow_dispatch", ""), ("push", COMMIT)):
            for value in ("false", "null", None, "", "True", "1", "FAIL"):
                with self.subTest(event=event, value=value):
                    self.reset_calls()
                    self.runner["GITHUB_EVENT_NAME"] = event
                    self.undated()
                    self.set_state(immutable=value, remote_tag=remote_tag)
                    code, out, err = self.run_step(PUBLISH)
                    self.assertEqual(code, 1, err)
                    if value == "FAIL":
                        self.assertIn("immutable field could not be read back", err)
                        self.assertIn(REMEDY_UNREADABLE, err)
                        self.assert_superseded_advice(err, 0)
                    else:
                        self.assertIn("immutable field reads ", err)
                        self.assertIn(REMEDY_NOT_IMMUTABLE, err)
                        self.assertNotIn(REMEDY_UNREADABLE, err)
                        self.assert_superseded_advice(err)
                    self.assertNotIn("is immutable", out)
                    calls = self.calls()
                    self.assertLess(self.index_of(calls, is_create), self.index_of(calls, is_field_read("immutable")))
                    self.assertFalse(any(is_field_read("published_at")(c) for c in calls), calls)

    def test_unavailable_extractor_is_reported_as_unavailable(self):
        (self.work / "tools" / "skill-release-date.py").unlink()
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed (exit 16) while probing it", err)
        self.assertIn("exited 2 in baseline", err)
        self.assertFalse(any(is_create(c) for c in self.calls()))

    def test_a_missing_or_broken_client_is_reported_by_the_probe(self):
        # Row 89: a client that is missing (exit 2) or does not compile
        # (exit 1) fails the probe, before any tag operation.
        for label, code_expected in (("missing", 2), ("broken", 1)):
            with self.subTest(label):
                self.reset_calls()
                client = self.work / "tools" / "skill-release-date-client.py"
                if label == "missing":
                    client.unlink(missing_ok=True)
                else:
                    client.write_text("def broken(:\n", encoding="utf-8")
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn(f"unavailable or crashed (exit {code_expected}) while probing it", err)
                calls = self.calls()
                self.assertFalse(any(is_tag_operation(c) or is_create(c) for c in calls), calls)

    def test_a_broken_extractor_reply_is_unavailable_at_each_publish_check(self):
        # Row 89: an extractor that passes the probe but breaks the contract
        # for the window check or the readback is the tool failing, never a
        # refusal, a malformed clock reading or another publication day.
        for op, what, created in (
            ("publish_window", "while checking the publication window", False),
            ("confirm_published", "while confirming the publication day of v1.0.15", True),
        ):
            for mode in ("exit1", "notjson", "otherop", "badvalue"):
                with self.subTest(op=op, mode=mode):
                    self.reset_calls()
                    self.break_extractor(op, mode)
                    code, out, err = self.run_step(PUBLISH)
                    self.assertEqual(code, 1, err)
                    self.assertIn(f"The release-date extractor is unavailable or crashed (exit 16) {what}.", err)
                    self.assertIn("so the extractor is unavailable", err)
                    for text in VERDICT_TEXTS:
                        self.assertNotIn(text, err)
                    self.assertNotIn("was published on", out)
                    self.assertEqual(any(is_create(c) for c in self.calls()), created, self.calls())

    def test_broken_extractor_is_reported_by_the_probe_on_first_publication(self):
        # The probe at the start of the step reports a crashed extractor
        # as that, never as a malformed clock reading.
        for label, body in BROKEN_EXTRACTORS:
            with self.subTest(label):
                self.reset_calls()
                (self.work / "tools" / "skill-release-date.py").write_text(body, encoding="utf-8")
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn("unavailable or crashed (exit 16) while probing it", err)
                self.assertIn("exited 1 in baseline", err)
                self.assertIn("ModuleNotFoundError" if label == "import-broken" else "SyntaxError", err)
                self.assertNotIn("malformed", err)
                calls = self.calls()
                self.assertFalse(any(is_tag_operation(c) or is_create(c) for c in calls), calls)


class NoSettingPreCheckTest(WorkflowStepTest):
    """The workflow never reads the repository immutable-releases setting,
    whose endpoint the workflow token cannot read; a dated first publication
    relies on the readback alone."""

    def test_workflow_never_calls_the_immutable_releases_endpoint(self):
        self.assertNotIn("immutable-releases", WORKFLOW_TEXT)
        for step in WF.steps:
            with self.subTest(step.get("name")):
                self.assertNotIn("immutable-releases", dumped(step))

    def test_no_run_calls_the_immutable_releases_endpoint(self):
        for event, remote_tag, status in (
            ("workflow_dispatch", "", "404"), ("push", COMMIT, "404"), ("workflow_dispatch", COMMIT, "200"),
        ):
            with self.subTest(event=event, status=status):
                self.reset_calls()
                self.runner["GITHUB_EVENT_NAME"] = event
                self.set_state(remote_tag=remote_tag, status=status)
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 0, err)
                calls = self.calls()
                self.assertTrue(calls)
                self.assertFalse(
                    any(c[0] == "gh" and any("immutable-releases" in a for a in c[1]) for c in calls), calls
                )

    def test_first_publication_proceeds_to_the_readback(self):
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        self.assert_superseded_advice(out + err, 0)
        calls = self.calls()
        self.assertLess(self.index_of(calls, is_tag_operation), self.index_of(calls, is_create))
        self.assertLess(self.index_of(calls, is_create), self.index_of(calls, is_field_read("immutable")))


# The events that can start a re-run at the same commit: a dispatch, and a
# re-run of a tag-push run, which keeps the push event.
RERUN_EVENTS = ("workflow_dispatch", "push")


def assert_readback_ran(test, calls, out):
    """The dated publication readback ran on a re-run: its label, and the
    immutable read before the published_at read."""
    immutable = test.index_of(calls, is_field_read("immutable"))
    published_at = test.index_of(calls, is_field_read("published_at"))
    test.assertLess(immutable, published_at)
    test.assertIn("Re-run readback: release v1.0.15 published_at 2026-11-15T12:00:03Z", out)


class RerunTest(WorkflowStepTest):
    """A re-run at the same commit ends green only on the same publication
    readback as the first creation, on each event that can start one. Item 57:
    there is no force upload path."""

    def rerun(self, event="workflow_dispatch"):
        self.runner["GITHUB_EVENT_NAME"] = event
        self.set_state(status="200", remote_tag=COMMIT)

    def test_rerun_at_the_same_commit_runs_the_readback(self):
        for event in RERUN_EVENTS:
            with self.subTest(event):
                self.reset_calls()
                self.rerun(event)
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 0, err)
                calls = self.calls()
                self.assertFalse(any(is_mutation(c) for c in calls), calls)
                assert_readback_ran(self, calls, out)
                self.assertIn("kept its assets", out)

    def test_rerun_fails_when_the_readback_does_not_hold(self):
        for event in RERUN_EVENTS:
            for label, state, message in BAD_READBACKS:
                with self.subTest(event=event, readback=label):
                    self.reset_calls()
                    self.set_state(immutable="true", published_at="2026-11-15T12:00:03Z")
                    self.rerun(event)
                    self.set_state(**state)
                    code, out, err = self.run_step(PUBLISH)
                    self.assertEqual(code, 1, err)
                    self.assertIn(message, err)
                    self.assert_superseded_advice(err, 0 if label == "immutable unreadable" else 1)
                    self.assertNotIn("kept its assets", out)

    def test_broken_extractor_is_reported_by_the_probe_on_a_rerun(self):
        # A re-run reports a crashed extractor as that, never as an
        # unusable published_at.
        for event in RERUN_EVENTS:
            for label, body in BROKEN_EXTRACTORS:
                with self.subTest(event=event, extractor=label):
                    self.reset_calls()
                    self.rerun(event)
                    (self.work / "tools" / "skill-release-date.py").write_text(body, encoding="utf-8")
                    code, out, err = self.run_step(PUBLISH)
                    self.assertEqual(code, 1, err)
                    self.assertIn("unavailable or crashed (exit 16) while probing it", err)
                    self.assertIn("exited 1 in baseline", err)
                    self.assertIn("ModuleNotFoundError" if label == "import-broken" else "SyntaxError", err)
                    self.assertNotIn("not a usable UTC instant", err)
                    self.assertNotIn("kept its assets", out)
                    calls = self.calls()
                    self.assertFalse(any(is_mutation(c) for c in calls), calls)
                    self.assertFalse(any(is_field_read("published_at")(c) for c in calls), calls)

    def test_undated_rerun_reads_back_immutability_only(self):
        # Item 57: an undated re-run reads back no publication day, but ends
        # green only on an immutable record, on each event.
        for event in RERUN_EVENTS:
            for value, expected in (("true", 0), ("false", 1), ("FAIL", 1)):
                with self.subTest(event=event, immutable=value):
                    self.reset_calls()
                    self.carried["RELEASE_DATED"] = "0"
                    self.carried["RELEASE_DATE"] = ""
                    self.set_state(immutable=value, published_at="2026-11-16T00:00:02Z")
                    self.rerun(event)
                    code, out, err = self.run_step(PUBLISH)
                    self.assertEqual(code, expected, err)
                    self.assert_superseded_advice(err, 1 if value == "false" else 0)
                    calls = self.calls()
                    self.assertTrue(any(is_field_read("immutable")(c) for c in calls), calls)
                    self.assertFalse(any(is_field_read("published_at")(c) for c in calls), calls)
                    if expected == 0:
                        self.assertIn("Re-run readback: release v1.0.15 is immutable", out)
                        self.assertIn("kept its assets", out)
                    else:
                        self.assertNotIn("kept its assets", out)


# The tag check of the push branch of the publish step, each line stripped of
# its indentation, as the witness that replaces it requires it to read.
TAG_PUSH_CHECK = (
    "if [ \"${remote_tag_sha}\" != \"${built_commit}\" ]; then",
    "echo \"Tag ${RELEASE_TAG} resolves to ${remote_tag_sha:-nothing} on origin, not the built commit"
    " ${built_commit}; refusing to publish mismatched bytes.\" >" + chr(38) + "2",
    "exit 1",
    "fi",
)

# Calls that match no row of CALL_FORMS, each as a label, its program and its
# arguments: an option before the subcommand, a method or body option that
# the table does not hold, a release deletion or upload, a ref update, a row
# with 1 argument more or fewer, a push with an option after the ref or of
# the bare tag, the arguments of a git row given to gh, an option in each
# slot, and a slot with text after its pattern.
RELEASES_PATH = "repos/jposluns/cleanlanguage/releases"
DOWNLOAD_PATTERNS = ["--pattern", "cleanlanguage.zip", "--pattern", "cleanlanguage.zip.sha256",
                     "--pattern", "cleanlanguage-1.0.15.zip", "--pattern", "cleanlanguage-1.0.15.zip.sha256"]
OFF_TABLE_CALLS = (
    ("a git option before tag", VCS, ["-c", "user.name=x", "tag", "v1.0.15", COMMIT]),
    ("git --attr-source before tag", VCS, ["--attr-source", "HEAD", "tag", "v1.0.15", COMMIT]),
    ("gh -R before release create", "gh", ["-R", "jposluns/cleanlanguage", "release", "create", "v1.0.15"]),
    ("a method before api", "gh", ["-X", "POST", "api", RELEASES_PATH]),
    ("a joined method", "gh", ["api", "-XPOST", RELEASES_PATH]),
    ("a method after =", "gh", ["api", "--method=POST", RELEASES_PATH]),
    ("a long body option", "gh", ["api", "--field", "tag_name=v1.0.15", RELEASES_PATH]),
    ("an include with nothing after =", "gh",
     ["api", "--include=", "--silent", RELEASES_PATH + "/tags/v1.0.15"]),
    ("a release deletion", "gh", ["release", "delete", "v1.0.15", "--yes"]),
    ("a release upload", "gh", ["release", "upload", "v1.0.15", "dist/cleanlanguage.zip", "--clobber"]),
    ("a ref update", VCS, ["update-ref", "refs/tags/v1.0.15", COMMIT]),
    ("a row with 1 more argument", VCS, ["tag", "v1.0.15", COMMIT, "HEAD"]),
    ("a row with 1 argument fewer", VCS, ["tag", "v1.0.15"]),
    ("a push with an option after the ref", VCS, ["push", "origin", "refs/tags/v1.0.15", "--force"]),
    ("a push of the bare tag", VCS, ["push", "origin", "v1.0.15"]),
    ("a git row given to gh", "gh", ["tag", "v1.0.15", COMMIT]),
    ("an option in the tag slot", VCS, ["tag", "-x", COMMIT]),
    ("an option in the commit slot", VCS, ["tag", "v1.0.15", "-x"]),
    ("an option in the repository slot", "gh", ["api", "repos/-x/y/releases/tags/v1.0.15", "--jq", ".immutable"]),
    ("an option in the directory slot", "gh",
     ["release", "download", "v1.0.15", "--dir", "-x", "--clobber", *DOWNLOAD_PATTERNS]),
    ("an option in the version slot", "gh",
     ["release", "download", "v1.0.15", "--dir", "/d", "--clobber", *DOWNLOAD_PATTERNS[:5],
      "cleanlanguage--x.zip", *DOWNLOAD_PATTERNS[6:]]),
    ("text after the tag slot", VCS, ["tag", "v1.0.15-x", COMMIT]),
)


class ImmutableReleaseTest(WorkflowStepTest):
    """Item 57: this workflow never republishes a published release. The force
    input is refused against a published release and only moves the tag of a release that is not
    yet published; there is no path that re-uploads published assets, and every
    published-release refusal names a corrective new version, never the force
    input as a remedy. The fake gh proves the shell logic only, never what
    GitHub itself enforces."""

    def published(self, remote_tag=COMMIT, force="false"):
        self.inputs["force"] = force
        self.set_state(status="200", remote_tag=remote_tag)

    def assert_no_mutation(self, calls):
        # No git or gh call in the log is a change or off the table.
        self.assertFalse([c for c in calls if is_mutation(c)], calls)
        # The fakes' own state as well as the call log, so a change or an
        # off-table call that the log does not show still fails this
        # assertion.
        self.assertEqual(self.fake_write_state(), self.state_before_run, calls)

    def test_force_against_a_published_release_is_refused(self):
        # The same commit, force set.
        self.published(force="true")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("this workflow never republishes a published release", err)
        # No unconditional corrective-version remedy ahead of the
        # verifying dispatch.
        self.assertNotIn("The remedy for a published release is a corrective new version", err)
        self.assertIn("only moves the tag of a release that is not yet published", err)
        # The refusal names the fresh dispatch that verifies the
        # published release.
        self.assertIn(VERIFY_BY_DISPATCH, err)
        # It names that dispatch only for a tag carrying this workflow.
        self.assertIn(NEVER_AT_OLDER_TAG, err)
        self.assert_superseded_advice(err)
        # Row 71: a re-run keeps the force input, so no re-run is advised.
        self.assertNotIn("re-run", err.lower())
        self.assertNotIn("to verify this one", err)
        self.assertNotIn("overwriting", out + err)
        self.assertNotIn("kept its assets", out)
        self.assert_no_mutation(self.calls())

    def test_the_named_dispatch_verifies_a_release_published_under_force(self):
        # A force run publishes, then its readback fails for a
        # transient reason. Repeating that run keeps force and is refused; the
        # fresh dispatch both refusals name (force unchecked, the tag as the run
        # ref, so the built commit is the tag commit) ends green on the readback.
        self.inputs["force"] = "true"
        self.set_state(status="404", remote_tag=OTHER_COMMIT, immutable="FAIL")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        calls = self.calls()
        # Row 78: the forced run moved the tag to the commit it built and
        # pushed it before the create call, so the later runs read the tag
        # where this run left it, not where the test put it.
        move = self.index_of(calls, lambda c: c == [VCS, ["tag", "-f", "v1.0.15", COMMIT]])
        push = self.index_of(calls, lambda c: is_push(c) and "--force" in c[1] and c[1][-1] == "refs/tags/v1.0.15")
        self.assertLess(move, push)
        self.assertLess(push, self.index_of(calls, is_create))
        self.assertEqual((self.state / "remote_tag").read_text(encoding="utf-8"), COMMIT)
        self.assertIn(REMEDY_UNREADABLE, err)
        self.assert_superseded_advice(err, 0)
        self.reset_calls()
        self.set_state(immutable="true", status="200")
        self.inputs["force"] = "true"
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn(VERIFY_BY_DISPATCH, err)
        self.assert_superseded_advice(err)
        self.reset_calls()
        self.inputs["force"] = "false"
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        self.assertIn("kept its assets", out)
        self.assert_superseded_advice(out + err, 0)
        calls = self.calls()
        self.assert_no_mutation(calls)
        assert_readback_ran(self, calls, out)

    def test_force_against_a_published_release_never_moves_its_tag(self):
        # The damaging case, a tag at another commit and force set.
        self.published(remote_tag=OTHER_COMMIT, force="true")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("this workflow never republishes a published release", err)
        self.assert_superseded_advice(err)
        self.assert_no_mutation(self.calls())

    def test_force_is_refused_for_an_undated_published_release_too(self):
        self.carried["RELEASE_DATED"] = "0"
        self.carried["RELEASE_DATE"] = ""
        self.published(remote_tag=OTHER_COMMIT, force="true")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("this workflow never republishes a published release", err)
        self.assert_superseded_advice(err)
        self.assert_no_mutation(self.calls())

    def test_rerun_without_force_verifies_and_keeps_the_assets(self):
        # Regression guard for the verification branch, on both events,
        # each of which must also run the readback.
        for event in RERUN_EVENTS:
            with self.subTest(event):
                self.reset_calls()
                self.runner["GITHUB_EVENT_NAME"] = event
                self.published()
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 0, err)
                self.assertIn("kept its assets", out)
                self.assertNotIn("Refusing the force input", err)
                self.assert_superseded_advice(out + err, 0)
                calls = self.calls()
                self.assert_no_mutation(calls)
                assert_readback_ran(self, calls, out)

    def test_missing_asset_names_a_corrective_new_version_not_the_force_input(self):
        self.published()
        self.set_state(missing="cleanlanguage.zip.sha256")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("is missing the asset cleanlanguage.zip.sha256", err)
        self.assertIn("cannot be completed in place; cut a corrective new version", err)
        self.assert_superseded_advice(err)
        self.assertNotIn("force", err)
        self.assertNotIn("kept its assets", out)
        self.assert_no_mutation(self.calls())

    def test_a_long_asset_list_never_reads_a_present_asset_as_missing(self):
        # grep -q exits on its first match, so a printf
        # pipe into it took SIGPIPE (141) on a long asset list, and pipefail
        # then reported a present asset as missing. Here the four required
        # assets come first and 1000 long names follow them.
        self.published()
        self.set_state(extra="1000")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        self.assertNotIn("is missing the asset", err)
        self.assertIn("kept its assets", out)
        self.assert_superseded_advice(out + err, 0)
        calls = self.calls()
        self.assert_no_mutation(calls)
        assert_readback_ran(self, calls, out)

    def test_a_long_asset_list_still_names_a_missing_asset(self):
        # The membership check still refuses an absent
        # asset when the list is long.
        self.published()
        self.set_state(extra="1000", missing="cleanlanguage-1.0.15.zip.sha256")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("is missing the asset cleanlanguage-1.0.15.zip.sha256", err)
        self.assert_superseded_advice(err)
        self.assertNotIn("kept its assets", out)
        self.assert_no_mutation(self.calls())

    def test_checksum_mismatch_names_a_corrective_new_version_not_the_force_input(self):
        # For each of the 2 zips, each checked by its own line.
        for zip_name in ("cleanlanguage.zip", "cleanlanguage-1.0.15.zip"):
            with self.subTest(zip_name):
                self.reset_calls()
                self.published()
                self.set_state(corrupt=zip_name)
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn("Published " + zip_name + " (", err)
                self.assertIn("does not match its published checksum", err)
                self.assertIn("fails verification against its own published checksums", err)
                self.assertIn("cut a corrective new version", err)
                self.assert_superseded_advice(err)
                self.assertNotIn("force", err)
                self.assertNotIn("kept its assets", out)
                self.assert_no_mutation(self.calls())

    def test_differing_zips_name_a_corrective_new_version_not_the_force_input(self):
        # Each zip matches its own published manifest, but the two differ.
        for zip_name in ("cleanlanguage.zip", "cleanlanguage-1.0.15.zip"):
            with self.subTest(zip_name):
                self.reset_calls()
                self.published()
                self.set_state(differ=zip_name)
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertNotIn("does not match its published checksum", err)
                self.assertIn("The published stable and version-named zips of v1.0.15 differ.", err)
                self.assertIn("This workflow never republishes a published release; cut a corrective new version", err)
                self.assert_superseded_advice(err)
                self.assertNotIn("force", err)
                self.assertNotIn("kept its assets", out)
                self.assert_no_mutation(self.calls())

    def test_moved_tag_of_a_published_release_offers_no_force_remedy(self):
        # The test also keeps the former check that FORCE reaches the script
        # only through the declared input: without it the run is refused.
        self.published(remote_tag=OTHER_COMMIT)
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("This workflow never republishes a published release, with or without the force input.", err)
        # A release whose create call failed after GitHub published
        # it is probably correct, so the refusal names the verifying dispatch
        # first, and a corrective new version only if that verification fails.
        self.assertIn(VERIFY_BY_DISPATCH, err)
        self.assertIn(NEVER_AT_OLDER_TAG, err)
        self.assert_superseded_advice(err)
        self.assertNotIn("with or without the force input; cut a corrective new version", err)
        self.assertNotIn("to overwrite", err)
        self.assertNotIn("Refusing the force input", err)
        self.assert_no_mutation(self.calls())

    def test_a_published_release_whose_tag_is_gone_names_a_corrective_new_version(self):
        # With the tag gone from origin, no dispatch can select
        # it as the run ref, so neither refusal names the verifying dispatch;
        # each names a corrective new version and changes nothing.
        for force in ("false", "true"):
            with self.subTest(force=force):
                self.reset_calls()
                self.published(remote_tag="", force=force)
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn(TAG_GONE, err)
                self.assertNotIn("dispatch this workflow again", err)
                self.assert_superseded_advice(err)
                self.assertNotIn("kept its assets", out)
                self.assert_no_mutation(self.calls())

    def test_a_dropped_note_leaves_the_refusal_without_it(self):
        # Row 88: a deliberate flip. With one print of the note replaced by
        # the no-op :, the refusal it followed no longer carries the note, so
        # the behavioural pins above fail without the change. The publish
        # step prints the note after, in order from 0: the not-immutable
        # remedy, the day-mismatch remedy, the tag-gone remedy, the older-tag
        # advice, the missing-asset remedy, the two checksum remedies and the
        # differing-zips remedy; site 2 and site 5 are dropped here.
        script = step_script(PUBLISH)
        self.assertEqual(script.count(SUPERSEDED_ECHO), 8)
        self.published(remote_tag="")
        code, _out, err = self.run_step(PUBLISH, replace_nth(script, SUPERSEDED_ECHO, 2, ":"))
        self.assertEqual(code, 1, err)
        self.assertIn(TAG_GONE, err)
        self.assert_superseded_advice(err, 0)
        self.reset_calls()
        self.published()
        self.set_state(corrupt="cleanlanguage.zip")
        code, _out, err = self.run_step(PUBLISH, replace_nth(script, SUPERSEDED_ECHO, 5, ":"))
        self.assertEqual(code, 1, err)
        self.assertIn("fails verification against its own published checksums", err)
        self.assert_superseded_advice(err, 0)

    def test_every_remedy_names_a_corrective_new_version(self):
        # Row 73: the remedy lines, found by their wording (an echo line that
        # carries corrective or new version), all read corrective new version,
        # and no echo line carries a retired wording. The count is reconciled
        # against the workflow, so the probe cannot pass empty. Residual: a
        # remedy phrased without either word is neither counted nor checked.
        echoes = [line for line in WORKFLOW_TEXT.splitlines() if "echo " in line]
        remedies = [line for line in echoes if "corrective" in line or "new version" in line]
        # The 2 tag-gone lines print TAG_GONE_ADVICE from
        # the job env, so this count excludes them; the job env values are
        # pinned by test_the_older_tag_advice_and_the_tag_gone_text_each_have_one_source.
        self.assertEqual(len(remedies), 9, remedies)
        for value in (job_env()["OLDER_TAG_ADVICE"], job_env()["TAG_GONE_ADVICE"],
                      job_env()["SUPERSEDED_RELEASE_ADVICE"]):
            self.assertIn("corrective new version", value)
            self.assertNotRegex(value, r"(?<!corrective )new version")
        for line in echoes:
            with self.subTest(line.strip()):
                self.assertNotRegex(line, r"(?<!corrective )new version")
                self.assertNotIn("corrective version", line)
                self.assertNotIn("re-run without", line)

    def test_no_test_name_carries_the_retired_wording(self):
        # A search for the retired wording finds no test name.
        names = [name for value in list(globals().values())
                 if isinstance(value, type) and issubclass(value, unittest.TestCase)
                 for name in vars(value) if name.startswith("test_")]
        self.assertGreater(len(names), 50, names)
        self.assertEqual([name for name in names if "corrective_version" in name], [])

    def test_force_still_moves_the_tag_of_an_unpublished_release(self):
        # The useful path survives, and its run reads back.
        self.inputs["force"] = "true"
        self.set_state(status="404", remote_tag=OTHER_COMMIT)
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        calls = self.calls()
        move = self.index_of(calls, lambda c: is_tag(c) and c[1][:2] == ["tag", "-f"])
        push = self.index_of(calls, lambda c: is_push(c) and "--force" in c[1])
        create = self.index_of(calls, is_create)
        self.assertLess(move, push)
        self.assertLess(push, create)
        self.assertLess(create, self.index_of(calls, is_field_read("immutable")))
        self.assertEqual([row_of_call(c) for c in calls if is_mutation(c)], ["tag-force", "push-force", "create"], calls)
        self.assertIn("First-publication readback", out)

    def test_moved_tag_of_an_unpublished_release_needs_the_force_input(self):
        self.set_state(status="404", remote_tag=OTHER_COMMIT)
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("refusing to move it without the force input", err)
        self.assert_superseded_advice(err, 0)
        self.assert_no_mutation(self.calls())

    def test_tag_push_of_a_new_release_creates_it(self):
        self.runner["GITHUB_EVENT_NAME"] = "push"
        self.set_state(status="404", remote_tag=COMMIT)
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        calls = self.calls()
        self.assertTrue(any(is_create(c) for c in calls), calls)
        self.assertEqual([row_of_call(c) for c in calls if is_mutation(c)], ["create"], calls)
        self.assertIn("First-publication readback", out)

    # The tag-push runs of an unpublished release whose tag on origin is not
    # the built commit: dated and undated, with the tag at another commit and
    # with no tag, each with the value the refusal names for that tag.
    TAG_PUSH_MISMATCHES = tuple((dated, remote_tag, shown) for dated in (True, False)
                                for remote_tag, shown in ((OTHER_COMMIT, OTHER_COMMIT), ("", "nothing")))

    def tag_push_mismatch(self, dated, remote_tag):
        self.reset_calls()
        self.runner["GITHUB_EVENT_NAME"] = "push"
        self.carried["RELEASE_DATED"] = "1" if dated else "0"
        self.carried["RELEASE_DATE"] = "2026-11-15" if dated else ""
        self.set_state(status="404", remote_tag=remote_tag, local_tag=None, gh_writes=None, unmodelled=None)

    def test_tag_push_of_an_unpublished_release_refuses_mismatched_bytes(self):
        # A tag-triggered run publishes only the commit that its tag names on
        # origin. With the tag at another commit or gone when the step reads
        # it, the run refuses before any tag operation or create call, on a
        # dated release (past the early window check) and an undated one.
        for dated, remote_tag, shown in self.TAG_PUSH_MISMATCHES:
            with self.subTest(dated=dated, remote_tag=shown):
                self.tag_push_mismatch(dated, remote_tag)
                code, out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn("Tag v1.0.15 resolves to " + shown + " on origin, not the built commit "
                              + COMMIT, err)
                self.assertIn("refusing to publish mismatched bytes", err)
                self.assertNotIn("Refusing to publish v1.0.15", err)
                # No release is published, so no text names a corrective
                # version: neither the superseded-release advice nor any line
                # holding the word corrective or the words new version.
                self.assert_superseded_advice(out + err, 0)
                for marker in ("corrective", "new version"):
                    self.assertNotIn(marker, (out + err).lower())
                calls = self.calls()
                # The fakes' tag and write state is the state this case set,
                # whatever the call log shows. It is compared with that state
                # as written here, before assert_no_mutation compares it with
                # the copy run_step took, so a hidden change fails here naming
                # the expected state, and so does a reading of the state that
                # drops 1 of its files, which the comparison of 2 readings by
                # the same function cannot see.
                self.assertEqual(self.fake_write_state(),
                                 {"local_tag": None, "remote_tag": remote_tag, "gh_writes": None, "unmodelled": None},
                                 calls)
                self.assert_no_mutation(calls)
                self.assertEqual(len([c for c in calls if is_lookup(c)]), 1, calls)
                # Only the early window check reads the clock; the binding
                # check before the create call is never reached.
                self.assertEqual(len([c for c in calls if is_date(c)]), 1 if dated else 0, calls)
                self.assertFalse(any(is_field_read("immutable")(c) for c in calls), calls)

    def test_without_its_tag_check_a_tag_push_publishes_mismatched_bytes(self):
        # The witness for the case above: with the tag check of the push
        # branch replaced by the no-op :, each of the 4 runs of that case
        # exits 0 and creates the release, which shows that the case above
        # fails whenever the check is dropped. The check is found by its
        # refusal line, which must occur on exactly 1 line, and each of its
        # 4 lines, stripped of indentation, must equal TAG_PUSH_CHECK, so a
        # changed check fails this test rather than letting it pass on a
        # script it no longer changes.
        lines = step_script(PUBLISH).splitlines(keepends=True)
        hits = [i for i, line in enumerate(lines) if "refusing to publish mismatched bytes" in line]
        self.assertEqual(len(hits), 1, hits)
        start = hits[0] - 1
        block = [line.strip() for line in lines[start:start + 4]]
        self.assertEqual(block, list(TAG_PUSH_CHECK), block)
        mutant = "".join(lines[:start]) + ":\n" + "".join(lines[start + 4:])
        for dated, remote_tag, shown in self.TAG_PUSH_MISMATCHES:
            with self.subTest(dated=dated, remote_tag=shown):
                self.tag_push_mismatch(dated, remote_tag)
                code, _out, err = self.run_step(PUBLISH, mutant)
                self.assertEqual(code, 0, err)
                self.assertNotIn("mismatched bytes", err)
                calls = self.calls()
                self.assertEqual(len([c for c in calls if is_create(c)]), 1, calls)
                writes = [json.loads(line)[:3] for line in (self.fake_write_state()["gh_writes"] or "").splitlines()]
                self.assertEqual(writes, [["release", "create", "v1.0.15"]], calls)

    def test_a_tag_written_in_the_background_after_the_step_exits_is_seen(self):
        # A step run waits for every process that still holds the pipe it
        # inherited from the step, so a tag that such a background process
        # writes after the step has exited is in the call log and the state
        # that assert_no_mutation reads. A process that closes the
        # descriptors it inherited is not waited for (see run_step).
        self.tag_push_mismatch(True, OTHER_COMMIT)
        script = "( sleep 1; " + VCS + " tag v1.0.15 " + COMMIT + " ) >/dev/null 2>&1 &\nexit 1\n"
        code, _out, err = self.run_step(PUBLISH, script)
        self.assertEqual(code, 1, err)
        self.assertEqual(self.fake_write_state()["local_tag"], COMMIT)
        self.assertEqual(len([c for c in self.calls() if is_tag(c)]), 1, self.calls())
        with self.assertRaises(AssertionError):
            self.assert_no_mutation(self.calls())

    def test_a_byte_written_to_the_pipe_does_not_end_the_wait(self):
        # A background process that writes to the pipe it inherited makes
        # the pipe readable while it still holds it. The step run reads the
        # pipe until its end of file, so a tag that such a process writes
        # 1 s later is still in the call log and the state that
        # assert_no_mutation reads. The bytes are written by a Python child
        # of that process, which inherits no descriptor that bash keeps for
        # itself, so the pipe is the only one from 3 up that it can write;
        # it counts the descriptors it wrote to, and exactly 1 shows that
        # the byte reached the pipe.
        self.tag_push_mismatch(True, OTHER_COMMIT)
        writer = ("import os\n"
                  "count = 0\n"
                  "for fd in range(3, 255):\n"
                  "    try:\n"
                  "        os.write(fd, b\"x\")\n"
                  "        count += 1\n"
                  "    except OSError:\n"
                  "        pass\n"
                  "with open(os.path.join(os.environ[\"FAKE_STATE\"], \"pipe_writes\"), \"w\") as handle:\n"
                  "    handle.write(str(count))\n")
        script = ("( \"" + sys.executable + "\" -I -c '" + writer + "'; sleep 1; "
                  + VCS + " tag v1.0.15 " + COMMIT + " ) >/dev/null 2>&1 &\nexit 1\n")
        code, _out, err = self.run_step(PUBLISH, script)
        self.assertEqual(code, 1, err)
        self.assertEqual(self.fake_write_state()["local_tag"], COMMIT)
        self.assertEqual(len([c for c in self.calls() if is_tag(c)]), 1, self.calls())
        with self.assertRaises(AssertionError):
            self.assert_no_mutation(self.calls())
        self.assertEqual((self.state / "pipe_writes").read_text(encoding="utf-8"), "1")

    def test_a_call_off_the_table_fails_the_run(self):
        # Each call of OFF_TABLE_CALLS matches no row of CALL_FORMS. A step
        # that makes it, and goes on to exit 0, fails its run. Run again with
        # the opt-out, the step exits 0, and the fake has refused the call
        # (exit 97, with its message), recorded it in unmodelled and changed
        # nothing else; the predicates read it as no row and as a change, and
        # assert_no_mutation fails on the state of the fakes alone, given an
        # empty call log.
        for label, program, args in OFF_TABLE_CALLS:
            with self.subTest(label):
                self.tag_push_mismatch(True, OTHER_COMMIT)
                self.set_state(local_tag=COMMIT)
                script = shlex.join([program, *args]) + " || true\nexit 0\n"
                with self.assertRaises(self.failureException) as raised:
                    self.run_step(PUBLISH, script)
                self.assertIn("made a call off the table CALL_FORMS", str(raised.exception))
                self.set_state(unmodelled=None)
                code, _out, err = self.run_step(
                    PUBLISH, script,
                    off_table="the case makes this call on purpose, to show that the fake refuses and records it")
                self.assertEqual(code, 0, err)
                self.assertIn("fake " + program + ": call off the table CALL_FORMS", err)
                self.assertEqual(self.fake_write_state(),
                                 {"local_tag": COMMIT, "remote_tag": OTHER_COMMIT, "gh_writes": None,
                                  "unmodelled": json.dumps([program, args]) + "\n"})
                self.assertEqual((row_of_call([program, args]), is_mutation([program, args])), (None, True))
                with self.assertRaises(AssertionError):
                    self.assert_no_mutation([])

    def test_every_gh_call_of_the_publish_step_reaches_the_fake_gh(self):
        # The pin counts the text gh api, the text gh release and the word gh
        # in the publish step, so a gh call added in those forms fails it. A
        # call that bash runs as gh but that is written otherwise, such as g\h
        # or "g"h, escapes the pin; the runs below catch it on the paths they
        # take. Each renames every gh word of the step gh-text, a copy of the
        # fake gh, which matches its calls as gh, so each call written as the
        # word gh reaches the fake by that name, and a call that bash still
        # runs as gh reaches it as gh and fails here. This holds on the 3
        # paths these runs take (a re-run, a first publication, and the
        # refusal of a tag push at another commit), not on a path none of
        # them reaches.
        script = step_script(PUBLISH)
        self.assertEqual((script.count("gh api "), script.count("gh release "), len(re.findall(r"\bgh\b", script))),
                         (3, 3, 6))
        self.write_exec(self.bin / "gh-text", FAKE_GH)
        renamed = re.sub(r"\bgh\b", "gh-text", script)
        for path in ("200", "404", "push"):
            with self.subTest(renamed=path):
                if path == "push":
                    self.tag_push_mismatch(True, OTHER_COMMIT)
                else:
                    self.reset_calls()
                    self.set_state(status=path, remote_tag=COMMIT, local_tag=None, gh_writes=None)
                code, _out, err = self.run_step(PUBLISH, renamed)
                self.assertEqual(code, 1 if path == "push" else 0, err)
                if path == "push":
                    self.assertIn("refusing to publish mismatched bytes", err)
                names = [call[0] for call in self.calls()]
                self.assertIn("gh-text", names, self.calls())
                self.assertNotIn("gh", names, self.calls())

    def test_unknown_release_status_fails_closed_before_any_mutation(self):
        for force in ("false", "true"):
            with self.subTest(force=force):
                self.reset_calls()
                self.inputs["force"] = force
                self.set_state(status="500", remote_tag=OTHER_COMMIT)
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn("Could not determine whether v1.0.15 is already published (HTTP 500)", err)
                self.assertIn("Refusing to proceed rather than act on a release whose state is unknown.", err)
                self.assertNotIn("overwriting", err)
                self.assert_superseded_advice(err, 0)
                self.assert_no_mutation(self.calls())

    def test_no_text_or_path_offers_a_republish(self):
        """Structural: problems_republish holds on the real workflow, the
        force input describes only a tag move, and the extractor docstring no
        longer describes a re-upload. Residual: the wording checks are a list
        of known strings; the behavioural cases above are the guard that does
        not depend on wording."""
        self.assertEqual(problems_republish(WF), [])
        description = WF.data.get("on", WF.data.get(True))["workflow_dispatch"]["inputs"]["force"]["description"]
        self.assertTrue(description.startswith("Move the tag of a release that is not yet published"), description)
        # A statement about this workflow, not a claim that
        # every published release is immutable, which an older workflow can
        # make false.
        self.assertIn("This workflow never republishes a published release, so this input never overwrites"
                      " one.", description)
        self.assertNotIn("A published release is immutable", description)
        self.assertNotIn("byte for byte", description)
        # For a published release the description names the
        # verifying dispatch first, and a corrective new version only if that
        # verification fails or the tag is gone.
        self.assertNotIn("the remedy for a published release is a corrective new version", description)
        # The description ends with the shared advice, then 1 sentence
        # naming the 2 remaining cases (so no condition is stated twice),
        # then the superseded-release advice; the endswith assertion below
        # checks all 3, in that order.
        # The sentence after the advice (last): the advice names 2
        # remedies, so this sentence names its own remedy rather than
        # pointing back at one.
        last = ("A corrective new version is also the remedy if the dispatch at the tag fails its"
                " verification, or if the tag is no longer on origin.")
        # Row 88: the shared superseded-release note closes the description.
        self.assertTrue(description.endswith(OLDER_TAG_ADVICE + " " + last + " " + SUPERSEDED_RELEASE_ADVICE), description)
        self.assertEqual(description.count(SUPERSEDED_RELEASE_ADVICE), 1, description)
        self.assertNotIn("The same remedy", description)
        sentences = [s for s in re.split(r"(?<=[.;])\s+", description) if s]
        self.assertEqual(len(sentences), len(set(sentences)), sentences)
        self.assertNotIn("only if that verification fails", description)
        self.assertLess(description.index("To verify a release that is already published"),
                        description.index("corrective new version"))
        # Row 78: a run that failed before it published is finished by a
        # re-run or a fresh dispatch from main, and the tag as the run ref is
        # named only to verify a release that is already published. A run
        # can fail after its tag push (the binding window check, or the
        # create call), so the tag may already be on origin; once main has
        # moved, an unforced dispatch from main refuses to move it, and the
        # description names this input for that case. The behavioural
        # pair is test_force_still_moves_the_tag_of_an_unpublished_release
        # and test_moved_tag_of_an_unpublished_release_needs_the_force_input.
        # Re-run advice: a re-run executes the workflow at the run commit,
        # so the advice is limited to a commit carrying the publish step,
        # consistent with the ban on repeating the runs of an older tag.
        self.assertIn("To finish a run that failed before it published, re-run it only if its commit carries"
                      " the step " + PUBLISH + ", and otherwise dispatch this workflow again from main with the"
                      " same tag.", description)
        self.assertNotIn("re-run it or dispatch", description)
        self.assertIn("or repeat any of its runs", description)
        # The subject of the remedy is the release, not a command.
        self.assertNotIn("If it fails", description)
        self.assertIn("If that tag is already on origin at another commit, for example because the failed"
                      " run pushed it and main has moved since, check this input on that dispatch from"
                      " main.", description)
        # The verifying dispatch is named only for a tag whose
        # workflow has the publish step, and a dispatch at any other tag is
        # forbidden, since an older workflow can republish.
        self.assertIn("To verify a release that is already published, first check that"
                      " .github/workflows/release-skill.yml at the tag has the step " + PUBLISH + "; if it"
                      " does, dispatch this workflow again with this input unchecked and the tag itself"
                      " selected as the run ref, not main", description)
        # The description carries the shared advice verbatim.
        self.assertIn(OLDER_TAG_ADVICE, description)
        # The description covers every era of tag, so it names
        # no asset file and no fixed path inside the zip.
        self.assertNotIn("cleanlanguage.zip", description)
        self.assertNotIn("clean-language", description)
        self.assertNotIn("unzip -p cleanlanguage.zip SKILL.md", description)
        # gh release view names the field isImmutable; immutable is the REST field.
        self.assertNotIn("--json immutable", WORKFLOW_TEXT)
        self.assertNotIn("failed before it published, dispatch this workflow again with the tag", description)
        extractor = EXTRACTOR.read_text(encoding="utf-8")
        for stale in ("release upload", "force dispatch", "--clobber"):
            with self.subTest(stale):
                self.assertNotIn(stale, extractor)

    def test_every_dispatch_at_the_tag_is_conditional_outside_the_readback(self):
        # Every echo line naming a dispatch at the tag as the run
        # ref either sits in confirm_published_release, which runs only at the
        # tag commit and so under this workflow, or names the publish step the
        # tag must carry and is followed by the line forbidding a dispatch at an
        # older tag. The count is reconciled, so the probe cannot pass empty.
        lines = WORKFLOW_TEXT.splitlines()
        start = lines.index("          confirm_published_release() { # label")
        end = lines.index("          }", start)
        at_tag = [i for i, line in enumerate(lines)
                  if "echo " in line and "selected as the run ref, not main" in line]
        self.assertEqual(len(at_tag), 4, at_tag)
        inside = [i for i in at_tag if start < i < end]
        self.assertEqual(len(inside), 2, inside)
        for i in at_tag:
            if i in inside:
                continue
            with self.subTest(line=i + 1):
                self.assertIn("has the step " + PUBLISH + ". If it does, dispatch", lines[i])
                self.assertEqual(lines[i + 1].strip(), OLDER_TAG_ECHO)

    def test_the_older_tag_advice_and_the_tag_gone_text_each_have_one_source(self):
        # The job env declares each text once and each step
        # prints it through one line; the description repeats the advice
        # verbatim. The advice names no command, file or path, and no
        # sentence repeats.
        self.assertEqual(job_env()["OLDER_TAG_ADVICE"], OLDER_TAG_ADVICE)
        self.assertEqual(job_env()["TAG_GONE_ADVICE"], TAG_GONE_ADVICE)
        self.assertEqual(TAG_GONE, TAG_GONE_ADVICE.replace("<tag>", "v1.0.15"))
        for name in (DETERMINE, PUBLISH):
            with self.subTest(name):
                stripped = [l.strip() for l in step_script(name).splitlines()]
                self.assertEqual(stripped.count(OLDER_TAG_ECHO), 1)
                self.assertEqual(stripped.count(TAG_GONE_ECHO), 1)
                self.assertNotIn("older workflow", step_script(name))
                self.assertNotIn("is no longer on origin", step_script(name))
        self.assertIsNone(ADVICE_NAMES_A_PROCEDURE.search(OLDER_TAG_ADVICE), OLDER_TAG_ADVICE)
        for bad in ("gh release view", "sha256sum -c", "cmp a b", "unzip -p", "x.zip", "y.sha256",
                    "SKILL.md", "release-skill.yml", "a/b", "--json"):
            with self.subTest(probe=bad):
                self.assertIsNotNone(ADVICE_NAMES_A_PROCEDURE.search(bad))
        # Each stated condition, in the one source and in the
        # verbatim repeat; the two steps print the one source (above).
        description = WF.data.get("on", WF.data.get(True))["workflow_dispatch"]["inputs"]["force"]["description"]
        for condition in ADVICE_CONDITIONS:
            with self.subTest(condition=condition):
                self.assertIn(condition, OLDER_TAG_ADVICE)
                self.assertIn(condition, job_env()["OLDER_TAG_ADVICE"])
                self.assertIn(condition, description)
        sentences = [s for s in re.split(r"(?<=[.;])\s+", OLDER_TAG_ADVICE) if s]
        self.assertEqual(len(sentences), len(set(sentences)), sentences)

    def test_the_superseded_release_advice_has_one_source_and_follows_every_remedy(self):
        # Row 88: the job env declares the note once; each step prints it
        # only through SUPERSEDED_ECHO, after every remedy line and nowhere
        # else; the description ends with it verbatim; it names no command,
        # file or path, makes no immutability claim, carries none of the
        # words the refusal tests forbid, and is two sentences.
        self.assertEqual(problems_superseded_advice(WF), [])
        self.assertEqual(job_env()["SUPERSEDED_RELEASE_ADVICE"], SUPERSEDED_RELEASE_ADVICE)
        self.assertEqual(WORKFLOW_TEXT.count(SUPERSEDED_RELEASE_ADVICE), 2)
        self.assertEqual(WORKFLOW_TEXT.count(SUPERSEDED_ECHO), 11)
        for name, (_remedies, prints) in SUPERSEDED_SITES.items():
            with self.subTest(name):
                script = step_script(name)
                self.assertEqual(script.count(SUPERSEDED_ECHO), prints)
                self.assertNotIn(SUPERSEDED_RELEASE_ADVICE, script)
                for phrase in SUPERSEDED_PHRASES:
                    self.assertNotIn(phrase, script)
        self.assertIsNone(ADVICE_NAMES_A_PROCEDURE.search(SUPERSEDED_RELEASE_ADVICE), SUPERSEDED_RELEASE_ADVICE)
        self.assertEqual(immutability_claims(SUPERSEDED_RELEASE_ADVICE), [])
        self.assertIn("corrective new version", SUPERSEDED_RELEASE_ADVICE)
        self.assertNotRegex(SUPERSEDED_RELEASE_ADVICE, r"(?<!corrective )new version")
        for word in ("force", "re-run", "dispatch this workflow", "immutable", "republish", "overwriting"):
            self.assertNotIn(word, SUPERSEDED_RELEASE_ADVICE.lower())
        for dash in (chr(8212), chr(8211)):
            self.assertNotIn(dash, SUPERSEDED_RELEASE_ADVICE)
        description = WF.data.get("on", WF.data.get(True))["workflow_dispatch"]["inputs"]["force"]["description"]
        self.assertTrue(description.endswith(" " + SUPERSEDED_RELEASE_ADVICE), description)
        self.assertEqual(description.count(SUPERSEDED_RELEASE_ADVICE), 1)
        sentences = [s for s in re.split(r"(?<=[.;])\s+", SUPERSEDED_RELEASE_ADVICE) if s]
        self.assertEqual(len(sentences), 2, sentences)

    def test_a_failed_tag_lookup_stops_the_publish_step_with_no_tag_gone_advice(self):
        # A failed lookup is not a tag gone from origin. The
        # mutant that ignores the failure (|| true) reads it as gone, so this
        # test distinguishes the two.
        self.published()
        self.set_state(ls_remote="FAIL")
        code, _out, err = self.run_step(PUBLISH)
        self.assertNotEqual(code, 0, err)
        self.assertNotIn(TAG_GONE, err)
        self.assertNotIn("dispatch this workflow", err)
        self.assert_superseded_advice(err, 0)
        self.assert_no_mutation(self.calls())
        self.reset_calls()
        code, _out, err = self.run_step(PUBLISH, ignore_lookup_failure(step_script(PUBLISH)))
        self.assertEqual(code, 1, err)
        self.assertIn(TAG_GONE, err)
        self.assert_superseded_advice(err)

    def test_no_printed_text_claims_every_published_release_is_immutable(self):
        # An older workflow can republish, so no printed line,
        # job env value or input description states, unconditionally, that a
        # release or its assets are immutable, or that nothing (or no
        # workflow) can republish one. The allowed lines are the ones whose
        # truth the workflow establishes first (the readback lines after the
        # immutable check) and the conditional re-stamping line. Residual:
        # this is a pattern over known phrasings, including the close
        # variants above (row 87 added some of them), and a claim whose
        # subject is "it", a claim split across sentences, or another
        # wording can still slip past it.
        self.assertEqual(immutability_claims(WORKFLOW_TEXT), [])
        # Each allowed line occurs exactly once in the workflow text. A pin
        # left behind after its line changes fails the assertion above if
        # immutability_claims() reports the new line, and fails here if it
        # does not, as when the new line has its own pin or words a claim in
        # a way the guard misses. This counts lines of the text, not prints:
        # a function that runs more than once prints its line more than
        # once, and a second copy of an allowed line, even an honest one,
        # fails here. The subtest names each entry by its index in the
        # allowed tuple.
        stripped = [line.strip() for line in WORKFLOW_TEXT.splitlines()]
        for index, allowed in enumerate(IMMUTABILITY_CLAIM_ALLOWED):
            with self.subTest(entry=index, allowed=allowed[:60]):
                self.assertEqual(stripped.count(allowed), 1)
        description = WF.data.get("on", WF.data.get(True))["workflow_dispatch"]["inputs"]["force"]["description"]
        for value in list(job_env().values()) + [description]:
            with self.subTest(value=value[:60]):
                self.assertEqual(immutability_claims(value), [])
        anchor = "              published_release_remedy\n"
        mutant = WORKFLOW_TEXT.replace(anchor, anchor + "              " + CLAIM_MUTANT + "\n", 1)
        self.assertNotEqual(mutant, WORKFLOW_TEXT)
        self.assertEqual(len(immutability_claims(mutant)), 1)
        for probe in ("Every published release is immutable.", "The published assets are immutable.",
                      "Nothing can republish it.", "No workflow republishes a release.",
                      "A release cannot be republished.",
                      # Close variants of the claims above.
                      "Every published release is always immutable.",
                      "Releases stay immutable once published.",
                      "No one can republish a published release.",
                      "A published release can" + chr(39) + "t be republished.",
                      "Published releases are permanently immutable.",
                      "A release can not be republished.",
                      "Published assets are never mutable.",
                      "Nobody can republish it.",
                      "A release remains immutable forever.",
                      # Row 87: one probe per alternative the guard lacked or
                      # left unprobed, each caught by that alternative alone.
                      "Releases are, once published, immutable.",
                      "Releases are, once published, always immutable.",
                      "No-one can republish a published release.",
                      "A release can never be republished.",
                      "A release could never be republished.",
                      "A release will never be republished.",
                      "A release will not be republished.",
                      "A release won" + chr(39) + "t be republished.",
                      "A release could not be republished.",
                      "A release couldn" + chr(39) + "t be republished.",
                      "Published assets are not mutable.",
                      "A release cannot ever be republished.",
                      "A release will never again be republished."):
            with self.subTest(probe=probe):
                self.assertNotEqual(immutability_claims(probe), [])

    def test_every_success_path_reads_back(self):
        # One readback per remaining success path, dated or not.
        self.assertEqual(READBACK_CALL.findall(step_script(PUBLISH)), READBACK_LABELS)


class ValidateStepTest(WorkflowStepTest):
    """The version mismatch refusal cannot tell whether the
    tag is already published, so its advice holds in both cases."""

    def test_mismatch_advice_holds_whether_or_not_the_tag_is_published(self):
        shutil.copy2(REPO / "tools" / "skill-version.py", self.work / "tools" / "skill-version.py")
        self.skill("Version: 1.0.15  \nReleased: 2026-11-15  \n")
        self.inputs["tag"] = "v1.0.14"
        code, _out, err = self.run_step(VALIDATE)
        self.assertEqual(code, 1, err)
        self.assertIn("SKILL.md version (1.0.15) does not match the release tag (v1.0.14).", err)
        self.assertIn("This step does not check whether v1.0.14 is already published. If it is not, set the"
                      " Version line in cleanlanguage/skills/cleanlanguage/SKILL.md to match the tag, or cut"
                      " the matching tag.", err)
        self.assertIn("If it is, do not change the Version line: this workflow never republishes a published release."
                      " See the description of the force input of this workflow.", err)
        self.assert_superseded_advice(err, 0)
        self.assertFalse(any(c[0] == "gh" for c in self.calls()), self.calls())

    def test_a_release_ahead_of_main_is_refused(self):
        # The step reads the version on main through the fetch and show rows
        # of CALL_FORMS, and refuses a release whose version main lacks.
        shutil.copy2(REPO / "tools" / "skill-version.py", self.work / "tools" / "skill-version.py")
        self.set_state(main_skill="Version: 1.0.14  \n")
        code, _out, err = self.run_step(VALIDATE)
        self.assertEqual(code, 1, err)
        self.assertIn("main names version 1.0.14, older than the release 1.0.15.", err)
        self.assertEqual([row_of_call(c) for c in self.calls() if c[0] == VCS], ["fetch", "show"], self.calls())


class DetermineStepTest(WorkflowStepTest):
    """The step that fixes the expected release date."""

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
        self.skill("Version: 1.0.15  \nReleased: 2026-11-14  \n")
        self.set_state(status="200", published_at="2026-11-14T08:00:00Z")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.env_values()["RELEASE_DATE"], "2026-11-14")

    def test_unusable_published_at_is_named_as_such(self):
        self.set_state(status="200", published_at="null")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("is not a usable UTC instant", err)
        self.assertIn("skill-release-date: published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: " + repr("null"), err)
        self.assert_superseded_advice(err, 0)

    def test_unreadable_published_at_names_the_verifying_dispatch(self):
        # Row 78: like the publish-step readback refusals, the refusal names
        # the next step.
        self.set_state(status="200", published_at="FAIL", remote_tag=COMMIT)
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("Could not read published_at for the existing release v1.0.15.", err)
        self.assertNotIn(TAG_GONE, err)
        # This step may run away from the tag, so the dispatch
        # at the tag is named only for a tag carrying this workflow.
        self.assertIn(DETERMINE_UNREADABLE, err)
        self.assertIn(NEVER_AT_OLDER_TAG, err)
        self.assert_superseded_advice(err)
        self.assertNotIn(REMEDY_UNREADABLE, err)

    def test_unreadable_published_at_with_the_tag_gone_names_a_corrective_new_version(self):
        # As in the publish step, a tag gone from origin cannot
        # be selected as the run ref, so no dispatch is named.
        self.set_state(status="200", published_at="FAIL", remote_tag="")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("Could not read published_at for the existing release v1.0.15.", err)
        self.assertIn(TAG_GONE, err)
        self.assert_superseded_advice(err)
        self.assertNotIn("dispatch this workflow", err)
        self.assertTrue(any(c[0] == VCS and c[1][:1] == ["ls-remote"] for c in self.calls()), self.calls())

    def test_a_failed_tag_lookup_stops_the_determine_step_with_no_tag_gone_advice(self):
        # As in the publish step, and the || true mutant is killed.
        self.set_state(status="200", published_at="FAIL", ls_remote="FAIL")
        code, _out, err = self.run_step(DETERMINE)
        self.assertNotEqual(code, 0, err)
        self.assertIn("Could not read published_at for the existing release v1.0.15.", err)
        self.assertNotIn(TAG_GONE, err)
        self.assertNotIn("dispatch this workflow", err)
        self.assert_superseded_advice(err, 0)
        self.assertEqual(self.env_values(), {})
        code, _out, err = self.run_step(DETERMINE, ignore_lookup_failure(step_script(DETERMINE)))
        self.assertEqual(code, 1, err)
        self.assertIn(TAG_GONE, err)
        self.assert_superseded_advice(err)

    def test_a_dated_release_with_no_released_line_reaches_the_packager(self):
        # A version above the undated baseline with no Released
        # line, and a published release. The determine step must not refuse
        # it with the day mismatch (the line is absent, not wrong); the
        # packager refuses the absent line. The mutant that drops the
        # non-empty guard reads the absent line as a wrong day.
        self.skill("Version: 1.0.15  \nAuthor: x\n")
        self.set_state(status="200", published_at="2026-11-14T08:00:00Z")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.env_values(), {"RELEASE_DATED": "1", "RELEASE_DATE": "2026-11-14"})
        self.assertNotIn("IS PUBLISHED on", err)
        code, _out, err = self.run_step(PACKAGE)
        self.assertEqual(code, 0, err)
        self.assertIn(["--tag", "v1.0.15", "--release-date", "2026-11-14"],
                      [c[1] for c in self.calls() if c[0] == "release-package.sh"])
        guard = "[ -n \"${released}\" ] " + chr(38) + chr(38) + " "
        script = step_script(DETERMINE)
        self.assertEqual(script.count(guard), 1)
        code, _out, err = self.run_step(DETERMINE, script.replace(guard, ""))
        self.assertEqual(code, 1, err)
        self.assertIn("IS PUBLISHED on 2026-11-14", err)

    def test_published_release_on_another_day_names_a_corrective_new_version(self):
        # The UTC day rolled over between the window check and
        # publication, so published_at names the next day. The verifying run
        # must name the remedy, not the packager re-stamp advice, which would
        # lead back to this same run.
        self.set_state(status="200", published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("Release v1.0.15 IS PUBLISHED on 2026-11-16 (UTC, published_at 2026-11-16T00:00:02Z),"
                      " but the Released line at this commit names 2026-11-15.", err)
        self.assertIn(PUBLISHED_ON_ANOTHER_DAY, err)
        self.assert_superseded_advice(err)
        self.assertNotIn("dispatch this workflow", err)
        self.assertEqual(self.env_values(), {})

    def test_broken_extractor_is_unavailable_not_malformed(self):
        (self.work / "tools" / "skill-release-date.py").write_text("def broken(:\n", encoding="utf-8")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed", err)
        self.assertNotIn("malformed", err)

    def test_extractor_internal_error_is_a_failure_not_an_unreadable_file(self):
        # An internal error has its own exit (6), never the unreadable 4.
        self.crash_extractor()
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed (exit 16)", err)
        self.assertIn("failed unexpectedly (internal error) in extract", err)
        self.assertNotIn("Could not read", err)

    def test_malformed_line_is_named_as_such(self):
        self.skill("Version: 1.0.15  \nReleased: soon\n")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("is malformed", err)
        self.assertIn("skill-release-date: the first Released line is not a bare YYYY-MM-DD date: "
                      + repr("Released: soon"), err)

    def test_a_broken_extractor_reply_is_unavailable_at_each_determine_call(self):
        # Row 89: an extractor that passes the probe but breaks the contract
        # for one call is the tool failing at that call, never a verdict on
        # the content, the version or published_at.
        sites = (
            ("extract", "reading the Released line of cleanlanguage/skills/cleanlanguage/SKILL.md",
             "Version: 1.0.15  \nReleased: 2026-11-15  \n", "1.0.15", {"status": "404"}),
            ("requires_release_date", "deciding whether 1.0.14 needs a Released line",
             "Version: 1.0.14  \nAuthor: x\n", "1.0.14", {"status": "404"}),
            ("release_day_from_published_at", "reading the published_at of v1.0.15",
             "Version: 1.0.15  \nReleased: 2026-11-15  \n", "1.0.15", {"status": "200"}),
        )
        for op, what, skill, version, state in sites:
            for mode in BROKEN_MODES:
                with self.subTest(op=op, mode=mode):
                    self.reset_calls()
                    self.skill(skill)
                    self.carried["VERSION"] = version
                    self.set_state(**state)
                    self.break_extractor(op, mode)
                    code, _out, err = self.run_step(DETERMINE)
                    self.assertEqual(code, 1, err)
                    self.assertIn(f"The release-date extractor is unavailable or crashed (exit 16) while {what}, "
                                  "so the release date cannot be checked.", err)
                    self.assertIn("so the extractor is unavailable", err)
                    for text in VERDICT_TEXTS:
                        self.assertNotIn(text, err)
                    self.assertEqual(self.env_values(), {})


class PackageStepTest(WorkflowStepTest):
    """The packager gets --release-date only for a dated release."""

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


# Row 89: the two ways errexit can be inherited by a command substitution.
INHERITED_ERREXIT = (("inherit_errexit", ("-O", "inherit_errexit")), ("posix", ("-o", "posix")))

# Row 89: a stand-in client whose baseline is a version followed by another
# line, and which runs the real client for every other word.
TWO_LINE_BASELINE_CLIENT = (
    "import os, sys\n"
    "if sys.argv[1:] == [\"baseline\"]:\n"
    "    print(\"1.0.14\")\n"
    "    print(\"noise\")\n"
    "    raise SystemExit(0)\n"
    "real = os.path.join(os.path.dirname(os.path.abspath(__file__)), \"real-client.py\")\n"
    "os.execv(sys.executable, [sys.executable, \"-I\", real, *sys.argv[1:]])\n"
)


class InheritedErrexitStepTest(WorkflowStepTest):
    """Row 89: the Determine and Publish steps keep every result of the
    client when errexit is inherited by command substitutions, by shopt -s
    inherit_errexit or in POSIX mode."""

    def test_the_steps_give_the_same_verdicts(self):
        for label, options in INHERITED_ERREXIT:
            with self.subTest(label, case="a new dated release expects today"):
                self.reset_calls()
                self.set_state(status="404", clock="2026-11-15T10:00:00Z")
                code, _out, err = self.run_step(DETERMINE, bash_options=options)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.env_values(), {"RELEASE_DATED": "1", "RELEASE_DATE": "2026-11-15"})
            with self.subTest(label, case="a broken extractor is unavailable"):
                self.reset_calls()
                self.break_extractor("extract", "exit1")
                code, _out, err = self.run_step(DETERMINE, bash_options=options)
                shutil.copy2(EXTRACTOR, self.work / "tools" / "skill-release-date.py")
                self.assertEqual(code, 1, err)
                self.assertIn("unavailable or crashed (exit 16) while reading the Released line", err)
                self.assertIn("exited 1 in extract, so the extractor is unavailable", err)
            with self.subTest(label, case="a first publication ends green"):
                self.reset_calls()
                self.set_state(status="404", clock="2026-11-15T12:00:00Z")
                code, _out, err = self.run_step(PUBLISH, bash_options=options)
                self.assertEqual(code, 0, err)
            with self.subTest(label, case="the window refusal is named"):
                self.reset_calls()
                self.set_state(clock="2026-11-15T23:55:00Z")
                code, _out, err = self.run_step(PUBLISH, bash_options=options)
                self.assertEqual(code, 1, err)
                self.assertIn("Refusing to publish v1.0.15", err)
                self.set_state(clock="2026-11-15T12:00:00Z")


# Row 89: a stand-in client that, for one word, prints a valid value and then
# a second line at exit 0, and runs the real client for every other word.
VALUE_AND_A_LINE_CLIENT = (
    "import os, sys\n"
    "if sys.argv[1:2] == [{word!r}]:\n"
    "    print({value!r})\n"
    "    print(\"X=1\")\n"
    "    raise SystemExit(0)\n"
    "real = os.path.join(os.path.dirname(os.path.abspath(__file__)), \"real-client.py\")\n"
    "os.execv(sys.executable, [sys.executable, \"-I\", real, *sys.argv[1:]])\n"
)


class WholeValueTest(WorkflowStepTest):
    """Row 89: at each capture of a client value in the Determine step, a
    valid value followed by a second line at exit 0 is refused before
    GITHUB_ENV is written, so no extra line can reach it."""

    def stand_in(self, word: str, value: str):
        tools = self.work / "tools"
        shutil.move(str(tools / "skill-release-date-client.py"), str(tools / "real-client.py"))
        (tools / "skill-release-date-client.py").write_text(
            VALUE_AND_A_LINE_CLIENT.format(word=word, value=value), encoding="utf-8")

    def assert_refused(self, message: str):
        code, out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn(message, err)
        self.assertEqual(self.env_values(), {})
        self.assertNotIn("Expected release date", out)

    def test_extract_file_value_with_a_second_line(self):
        self.set_state(status="404")
        self.stand_in("extract-file", "2026-11-15")
        self.assert_refused("The release-date extractor gave an unexpected answer (2026-11-15\nX=1) for the Released "
                            "line of cleanlanguage/skills/cleanlanguage/SKILL.md.")

    def test_requires_date_value_with_a_second_line(self):
        self.carried["VERSION"] = "1.0.14"
        self.skill("Version: 1.0.14  \nAuthor: x\n")
        self.stand_in("requires-date", "optional")
        self.assert_refused("The release-date extractor gave an unexpected answer (optional\nX=1) for 1.0.14.")

    def test_published_day_value_with_a_second_line(self):
        # A version above the baseline with no Released line, and a published
        # release: released is empty, so only the check of release_date stands
        # between the value and GITHUB_ENV.
        self.skill("Version: 1.0.15  \nAuthor: x\n")
        self.set_state(status="200", published_at="2026-11-15T12:00:03Z")
        self.stand_in("published-day", "2026-11-15")
        self.assert_refused("The release-date extractor gave an unexpected answer (2026-11-15\nX=1) for the "
                            "published_at of v1.0.15.")


class WholeBaselineTest(WorkflowStepTest):
    """Row 89: each baseline probe of the workflow checks the value as a
    whole string, so a version followed by another line is refused."""

    def test_a_baseline_with_another_line_is_refused_by_each_probe(self):
        tools = self.work / "tools"
        shutil.move(str(tools / "skill-release-date-client.py"), str(tools / "real-client.py"))
        (tools / "skill-release-date-client.py").write_text(TWO_LINE_BASELINE_CLIENT, encoding="utf-8")
        for step in (DETERMINE, PUBLISH):
            with self.subTest(step):
                self.reset_calls()
                self.set_state(status="404")
                code, _out, err = self.run_step(step)
                self.assertEqual(code, 1, err)
                self.assertIn("The release-date extractor is unavailable or crashed (exit 0) while probing it", err)
                self.assertFalse(any(is_tag_operation(c) or is_create(c) for c in self.calls()), self.calls())


class ChainedRunTest(WorkflowStepTest):
    """The determine, package and publish steps in sequence, each reading
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
        self.assertNotIn(SUPERSEDED_RELEASE_ADVICE, results[-1][2] + results[-1][3])

    def test_rerun_in_sequence_takes_the_first_publication_day(self):
        self.skill("Version: 1.0.15  \nReleased: 2026-11-14  \n")
        self.set_state(status="200", remote_tag=COMMIT, published_at="2026-11-14T08:00:00Z")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [0, 0, 0], results)
        self.assertEqual(self.carried["RELEASE_DATE"], "2026-11-14")
        self.assertIn("Re-run readback: release v1.0.15 published_at 2026-11-14T08:00:00Z", results[-1][2])

    def test_rerun_in_sequence_stops_before_the_packager_on_another_day(self):
        # The determine step refuses, so the packager re-stamp
        # advice is never reached.
        self.set_state(status="200", remote_tag=COMMIT, published_at="2026-11-16T00:00:02Z")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [1], results)
        self.assertIn(PUBLISHED_ON_ANOTHER_DAY, results[0][3])
        self.assertEqual(results[0][3].count(SUPERSEDED_RELEASE_ADVICE), 1, results)
        self.assertFalse(any(c[0] == "release-package.sh" for c in self.calls()), self.calls())

    def test_rerun_in_sequence_fails_on_a_mutable_release(self):
        self.skill("Version: 1.0.15  \nReleased: 2026-11-14  \n")
        self.set_state(status="200", remote_tag=COMMIT, published_at="2026-11-14T08:00:00Z", immutable="false")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [0, 0, 1], results)
        self.assertIn("immutable field reads false", results[-1][3])
        self.assertEqual(results[-1][3].count(SUPERSEDED_RELEASE_ADVICE), 1, results)


FORCE_LINE = "          FORCE: ${{ inputs.force }}\n"
PACKAGE_LINE = "      - name: Validate, package, and verify the skill zip\n"
PACKAGE_BODY = "          # The packager always refuses a malformed Released line, and a\n"
PUBLISH_SHELL = "          FORCE: ${{ inputs.force }}\n        shell: bash\n"


def unmodelled_step(line: str) -> str:
    return (
        "      - name: Unmodelled step\n"
        "        shell: bash\n"
        "        run: |\n"
        "          " + line + "\n"
        "\n"
    )


def replace_nth(text: str, old: str, k: int, new: str) -> str:
    """text with its k-th occurrence (from 0) of old replaced by new; raises
    ValueError when there are fewer than k + 1 occurrences, so a loop over
    sites cannot pass empty."""
    start = -1
    for _ in range(k + 1):
        start = text.index(old, start + 1)
    return text[:start] + new + text[start + len(old):]


class MutationTest(unittest.TestCase):
    """Each defect, and other forms of it, applied to the real workflow
    text, must be named by the structural checks."""

    @staticmethod
    def mutated(old: str, new: str) -> Workflow:
        if WORKFLOW_TEXT.count(old) != 1:
            raise AssertionError(f"mutation anchor not unique: {old!r}")
        return Workflow(WORKFLOW_TEXT.replace(old, new))

    def assertNamed(self, wf: Workflow, *fragments: str):
        problems = structural_problems(wf)
        for fragment in fragments:
            self.assertTrue(any(fragment in problem for problem in problems), (fragment, problems))

    def test_blank_line_before_an_env_override_is_caught(self):
        # Valid YAML with a blank line before an env override. A reader
        # matching line patterns could end the env: block at the blank line
        # and miss the override; this test pins that the override is read
        # and that the structural checks name it.
        wf = self.mutated(FORCE_LINE, FORCE_LINE + "\n          RELEASE_DATED: \"0\"\n")
        self.assertEqual(wf.step_env(PUBLISH)["RELEASE_DATED"], "0")
        self.assertNamed(
            wf,
            "step " + repr(PUBLISH) + " declares env keys an earlier step writes to GITHUB_ENV: " + repr(["RELEASE_DATED"]),
            f"step {PUBLISH!r} declares env keys",
        )

    def test_unmodelled_step_writing_release_dated_is_caught(self):
        # An extra step overriding RELEASE_DATED.
        wf = self.mutated(PACKAGE_LINE, unmodelled_step("echo \"RELEASE_DATED=0\" >> \"${GITHUB_ENV}\"") + PACKAGE_LINE)
        self.assertNamed(wf, "the workflow steps are", "step " + repr("Unmodelled step") + " names GITHUB_ENV")

    def test_every_form_of_a_github_env_reference_is_caught(self):
        forms = (
            ("braced", "echo \"RELEASE_DATED=0\" >> \"${GITHUB_ENV}\""),
            ("unbraced", "echo RELEASE_DATED=0 >> \"$GITHUB_ENV\""),
            ("via a variable", "target=\"$GITHUB_ENV\"; echo RELEASE_DATED=0 >> \"$target\""),
        )
        for label, line in forms:
            with self.subTest(label, place="modelled step"):
                wf = self.mutated(PACKAGE_BODY, "          " + line + "\n" + PACKAGE_BODY)
                self.assertNamed(wf, "step " + repr(PACKAGE) + " names GITHUB_ENV")
            with self.subTest(label, place="unmodelled step"):
                wf = self.mutated(PACKAGE_LINE, unmodelled_step(line) + PACKAGE_LINE)
                self.assertNamed(wf, "step " + repr("Unmodelled step") + " names GITHUB_ENV")

    def test_a_writer_step_writing_in_another_form_is_caught(self):
        anchor = "          echo \"Releasing version ${version} as ${RELEASE_TAG}.\"\n"
        wf = self.mutated(anchor, anchor + "          echo RELEASE_DATED=0 >> \"$GITHUB_ENV\"\n")
        self.assertNamed(wf, "step " + repr(VALIDATE) + " names GITHUB_ENV 2 times but makes 1 writes")

    def test_a_shell_other_than_bash_is_caught(self):
        wf = self.mutated(PUBLISH_SHELL, PUBLISH_SHELL.replace("shell: bash", "shell: sh"))
        self.assertNamed(wf, "step " + repr(PUBLISH) + " runs under shell " + repr("sh") + ", not bash")

    def test_a_duplicate_env_key_is_caught(self):
        wf = self.mutated(PUBLISH_SHELL, PUBLISH_SHELL + "        env:\n          RELEASE_DATED: \"0\"\n")
        self.assertNamed(wf, "repeats the key " + repr("env"))

    def test_a_step_level_condition_is_caught(self):
        wf = self.mutated(PUBLISH_SHELL, PUBLISH_SHELL + "        if: false\n")
        self.assertNamed(wf, "carries keys the harness does not model: [" + repr("if") + "]")

    def test_the_old_step_name_is_caught(self):
        # Item 57: the step no longer promises an update.
        # The other structural checks look the publish step up by its name
        # and raise when it is missing, so the two that name this defect are
        # called directly.
        wf = self.mutated("      - name: " + PUBLISH + "\n", "      - name: Create or update GitHub Release\n")
        problems = problems_step_list(wf) + problems_republish(wf)
        for fragment in ("the workflow steps are", "stale republish text " + repr("Create or update GitHub Release")):
            self.assertTrue(any(fragment in problem for problem in problems), (fragment, problems))
        with self.assertRaisesRegex(AssertionError, "0 steps named " + repr(PUBLISH)):
            structural_problems(wf)

    def test_a_restored_asset_upload_is_caught(self):
        anchor = "          gh release create \"${RELEASE_TAG}\" --verify-tag \\\n"
        upload = "          gh release upload \"${RELEASE_TAG}\" dist/cleanlanguage.zip --clobber\n"
        wf = self.mutated(anchor, upload + anchor)
        self.assertNamed(wf, "uploads release assets", "clobbers outside the verification download")

    def test_a_restored_force_bypass_is_caught(self):
        anchor = "              echo \"Refusing the force input: release ${RELEASE_TAG} is already published"
        bypass = "              echo \"force is enabled; overwriting the published release ${RELEASE_TAG}.\"\n"
        wf = self.mutated(anchor, bypass + anchor)
        self.assertNamed(wf, "stale republish text " + repr("force is enabled; overwriting"))

    def test_a_restored_force_readback_is_caught(self):
        anchor = "          confirm_published_release \"First-publication readback\"\n"
        wf = self.mutated(anchor, anchor + "          confirm_published_release \"Force readback\"\n")
        self.assertNamed(wf, "stale republish text " + repr("Force readback"), "reads back under the labels")

    def test_a_dropped_rerun_readback_is_caught(self):
        anchor = "              confirm_published_release \"Re-run readback\"\n"
        wf = self.mutated(anchor, "              :\n")
        self.assertNamed(wf, "reads back under the labels " + repr(["First-publication readback"]))

    def test_a_setting_read_is_caught(self):
        anchor = "          confirm_published_release() { # label\n"
        wf = self.mutated(anchor, "          gh api \"repos/${GITHUB_REPOSITORY}/immutable-releases\" --jq .enabled\n" + anchor)
        self.assertNamed(wf, "immutable-releases setting endpoint")

    def test_a_note_dropped_from_one_remedy_is_caught(self):
        # Row 88: each print of the note replaced in turn by the no-op :,
        # whole-line sites and inline sites alike.
        self.assertEqual(WORKFLOW_TEXT.count(SUPERSEDED_ECHO), 11)
        for k in range(11):
            with self.subTest(site=k):
                wf = Workflow(replace_nth(WORKFLOW_TEXT, SUPERSEDED_ECHO, k, ":"))
                self.assertNamed(wf, "followed by 0 prints of SUPERSEDED_RELEASE_ADVICE", "not the pinned")

    def test_an_inline_copy_of_the_note_is_caught(self):
        # Row 88: the note's text written where the echo of the env value
        # belongs, verbatim at each site and reworded at one.
        inline = "echo \"" + SUPERSEDED_RELEASE_ADVICE + "\" >" + chr(38) + "2"
        for k in range(11):
            with self.subTest(site=k):
                wf = Workflow(replace_nth(WORKFLOW_TEXT, SUPERSEDED_ECHO, k, inline))
                self.assertNamed(wf, "appears 3 times in the workflow", "carries the note's words",
                                 "followed by 0 prints")
        reworded = "echo \"Report the failure of that older release to the maintainer.\" >" + chr(38) + "2"
        wf = Workflow(replace_nth(WORKFLOW_TEXT, SUPERSEDED_ECHO, 0, reworded))
        self.assertNamed(wf, "carries the note's words " + repr("older release"), "followed by 0 prints")

    def test_a_description_without_or_twice_the_note_is_caught(self):
        tail = " " + SUPERSEDED_RELEASE_ADVICE + "\""
        wf = self.mutated(tail, "\"")
        self.assertNamed(wf, "appears 1 times in the workflow",
                         "force input description carries the note SUPERSEDED_RELEASE_ADVICE 0 times")
        wf = self.mutated(tail, tail[:-1] + tail)
        self.assertNamed(wf, "appears 3 times in the workflow", "2 times, not once")

    def test_a_stray_print_of_the_note_is_caught(self):
        # Row 88: a print after the unreadable-immutable refusal, which names
        # no corrective new version.
        anchor = ("              echo \"::error::Release ${RELEASE_TAG} is published, but its immutable field"
                  " could not be read back.\" >" + chr(38) + "2\n")
        wf = self.mutated(anchor, anchor + "              " + SUPERSEDED_ECHO + "\n")
        self.assertNamed(wf, "1 times outside a remedy block", "9 times, not the pinned 8")

    def test_a_changed_or_dropped_note_declaration_is_caught(self):
        env_line = "      SUPERSEDED_RELEASE_ADVICE: \"" + SUPERSEDED_RELEASE_ADVICE + "\"\n"
        wf = self.mutated(env_line, env_line.replace("latest", "newest", 1))
        self.assertNamed(wf, "not the pinned note", "appears 1 times in the workflow")
        wf = self.mutated(env_line, "")
        self.assertNamed(wf, "declares env keys", "not the pinned note")


# Row 59: the one API path every probe and readback names.
RELEASE_PATH = "repos/jposluns/cleanlanguage/releases/tags/v1.0.15"
# The one tag every gh release subcommand names, and the shape of any tag.
PINNED_TAG = "v1.0.15"
TAG_LIKE = re.compile(r"v[0-9]+[.][0-9]+[.][0-9]+")


class ApiPathTest(WorkflowStepTest):
    """Row 59: the fake gh answers every API path from one shared state, so
    the exact path of each status probe and of both readback fields is pinned
    here: the release of RELEASE_TAG, never another release or endpoint.
    The tag of every gh release subcommand (view, download and create) is
    pinned the same way: its first argument is RELEASE_TAG, it names no other
    tag, and it names no other repository."""

    def api_calls(self):
        path = self.state / "api.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def assert_exact_paths(self, kinds):
        calls = self.api_calls()
        self.assertEqual(sorted({kind for kind, _paths in calls}), sorted(kinds), calls)
        for kind, paths in calls:
            with self.subTest(kind=kind):
                self.assertEqual(paths, [RELEASE_PATH], calls)

    def release_calls(self):
        path = self.state / "release.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def assert_release_tag(self, subcommands):
        calls = self.release_calls()
        self.assertEqual(sorted({sub for sub, _rest in calls}), sorted(subcommands), calls)
        for sub, rest in calls:
            with self.subTest(subcommand=sub):
                self.assertEqual(rest[:1], [PINNED_TAG], calls)
                self.assertEqual([arg for arg in rest if TAG_LIKE.fullmatch(arg)], [PINNED_TAG], calls)
                self.assertEqual([arg for arg in rest if arg.startswith(("-R", "--repo"))], [], calls)

    def test_determine_probe_and_published_at_read_name_the_release_tag(self):
        self.set_state(status="200")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assert_exact_paths(["status", ".published_at"])
        self.assert_release_tag([])

    def test_determine_probe_of_an_unpublished_release_names_the_release_tag(self):
        # The probe is pinned on the 404 path too, the first
        # release of a version, where it is the only API call.
        self.set_state(status="404")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assert_exact_paths(["status"])
        self.assert_release_tag([])

    def test_first_publication_probe_and_both_readbacks_name_the_release_tag(self):
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        self.assert_exact_paths(["status", ".immutable", ".published_at"])
        self.assert_release_tag(["create"])

    def test_rerun_probe_and_both_readbacks_name_the_release_tag(self):
        for event in RERUN_EVENTS:
            with self.subTest(event):
                (self.state / "api.log").unlink(missing_ok=True)
                (self.state / "release.log").unlink(missing_ok=True)
                self.reset_calls()
                self.runner["GITHUB_EVENT_NAME"] = event
                self.set_state(status="200", remote_tag=COMMIT)
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 0, err)
                self.assert_exact_paths(["status", ".immutable", ".published_at"])
                # The asset list and the verification
                # download read the release of RELEASE_TAG.
                self.assert_release_tag(["view", "download"])


if __name__ == "__main__":
    unittest.main()
