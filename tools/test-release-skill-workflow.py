#!/usr/bin/env python3
"""Behavioural tests for the release-date logic in the release workflow.

Item 26 (G3) puts three pieces of shell into
``.github/workflows/release-skill.yml``: the step that determines the expected
release date, the packaging step that passes it on, and the publication-time
checks in the publish step (the publication-window check immediately before
the create call, and the publication readback on every path that ends a
release run green: the first creation and a re-run at the same commit). These
tests EXTRACT each step script from the real workflow file and run it with
bash, the way the runner does, against fake ``gh``,
``git`` and ``date`` commands on PATH and a throwaway working directory holding
the real ``tools/skill-release-date.py``. The fakes record every call in
order, so the tests pin both the verdicts and the ordering: the binding window
check runs after every tag operation and before the create call, the readback
runs after it, and an undated release (``RELEASE_DATED=0``) checks no date at
all, though its readback still requires the release to be immutable (item
57). The fake ``date`` refuses any call without ``-u``, so a clock read in
local time goes red.

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
immutability check. Mutation tests apply the round 4 reproductions (a blank
line before an ``env:`` override, and an unmodelled step writing
``RELEASE_DATED=0``) and other forms of the same defects, and require the
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

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "release-skill.yml"
EXTRACTOR = REPO / "tools" / "skill-release-date.py"
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
JOB_ENV_KEYS = {"RELEASE_TAG", "OLDER_TAG_ADVICE", "TAG_GONE_ADVICE"}
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
    # U1: GitHub documents the immutable-releases setting endpoint as needing
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


STRUCTURAL_CHECKS = (
    problems_layout, problems_step_list, problems_step_keys, problems_env,
    problems_runner_files, problems_setting_endpoint, problems_duplicate_keys,
    problems_republish,
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
if ARGS[:1] == ["api"]:
    # Row 59: every API path is answered from one shared state, so the exact
    # path each call names is logged for ApiPathTest to pin.
    paths = [arg for index, arg in enumerate(ARGS[1:]) if not arg.startswith("-") and ARGS[index] != "--jq"]
    kind = ARGS[ARGS.index("--jq") + 1] if "--jq" in ARGS else "status"
    with open(os.path.join(STATE, "api.log"), "a", encoding="utf-8") as log:
        log.write(json.dumps([kind, paths]) + "\\n")
if ARGS[:1] == ["release"]:
    # Every release subcommand is logged with all its arguments, so the tag
    # each release read and the create call name is pinned by ApiPathTest.
    with open(os.path.join(STATE, "release.log"), "a", encoding="utf-8") as log:
        log.write(json.dumps([ARGS[1] if len(ARGS) > 1 else "", ARGS[2:]]) + "\\n")
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
# The state file "missing" names assets the published release lacks,
# "corrupt" names zips whose published bytes no longer match their manifest,
# and "differ" names zips published with other bytes and a manifest that
# matches them, so the two zips differ while each manifest stays valid.
MISSING = read("missing").split()
# Fix round 4 (F3): "extra" is a count of further assets listed after the
# required ones. Each name is about 200 bytes, so 1000 of them overflow a
# 64 KiB pipe buffer many times over and a reader that exits on its first
# match always leaves its writer with bytes still to write.
EXTRA = ["extra-asset-%04d-" % index + "x" * 180 + ".txt" for index in range(int(read("extra", "0")))]
CORRUPT = read("corrupt").split()
DIFFER = read("differ").split()
if ARGS[:2] == ["release", "view"]:
    print("\\n".join([asset for asset in ASSETS if asset not in MISSING] + EXTRA))
    sys.exit(0)
if ARGS[:2] == ["release", "download"]:
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
sys.exit(0)
"""

FAKE_VCS = FAKE_COMMON + """
if ARGS[:1] == ["rev-parse"]:
    print(read("commit"))
elif ARGS[:1] == ["ls-remote"]:
    # The state file "ls_remote" set to FAIL makes the lookup itself fail.
    if read("ls_remote") == "FAIL":
        sys.exit(128)
    tag = read("remote_tag")
    if tag:
        print(tag + "\\trefs/tags/" + os.environ["RELEASE_TAG"])
elif ARGS[:1] == ["tag"]:
    # The local tag points at the commit named last.
    with open(os.path.join(STATE, "local_tag"), "w", encoding="utf-8") as handle:
        handle.write(ARGS[-1])
elif ARGS[:1] == ["push"] and ARGS[-1] == "refs/tags/" + os.environ["RELEASE_TAG"]:
    # A tag push moves the remote tag to the local one, so a later run reads
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

    def run_step(self, name: str, script_text: str | None = None):
        env = self.step_environment(name)
        self.env_file.write_text("", encoding="utf-8")
        script = self.state / "step.sh"
        script.write_text(step_script(name) if script_text is None else script_text, encoding="utf-8")
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


# Fix round 11: an unconditional claim that a release or its assets are
# immutable, or that nothing (or no workflow) can republish one. Fix round 12:
# up to three words (an adverb such as always, permanently or forever) may
# stand between the verb and the adjective, the verb may be stay or remain,
# never mutable or not mutable counts as immutable, no one and nobody count as
# nothing, and can not and can't count as cannot. Row 87: a pair of commas may
# set off an aside of up to three words right after the verb (a single comma
# elsewhere ends the claim, so "is published, but its immutable field" is not
# one), and up to three words may follow the aside, no-one counts as no one, and
# could not, will not, won't and can, could or will never count as cannot.
IMMUTABILITY_CLAIM = re.compile(
    r"\b(releases?|assets?)\b[^.;:]*\b(is|are|stays?|remains?)"
    r"(\s+(\w+\s+){0,3}?|\s*,\s*(\w+\s+){0,2}\w+\s*,\s*(\w+\s+){0,3}?)"
    r"(immutable|never\s+mutable|not\s+mutable)\b"
    r"|\b(nothing|no[\s-]+one|nobody|no\s+(other\s+)?workflow|no\s+run)\b[^.;]*\brepublish"
    r"|\b(can(\s*not|\Wt)|could(\s*not|n\Wt)|will\s+not|won\Wt|(can|could|will)\s+never)"
    r"\s+be\s+republished\b",
    re.IGNORECASE)
# The printed lines whose truth the workflow establishes first, by their exact
# text: the readback line printed after the immutable check, the day-mismatch
# line printed only after it, and the conditional re-stamping line.
IMMUTABILITY_CLAIM_ALLOWED = (
    "echo \"$1: release ${RELEASE_TAG} is immutable; it carries no Released line, so no publication day is checked.\"",
    "echo \"The published zip carries Released: ${RELEASE_DATE}, and an immutable release cannot be republished,"
    " so the remedy is a corrective new version whose Released line names its own publication day;"
    " tools/check-release-checksum-live.py reports the same disagreement until then.\" >" + chr(38) + "2",
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


def is_push(call):
    return call[0] == VCS and call[1][:1] == ["push"]


def is_create(call):
    return call[0] == "gh" and call[1][:2] == ["release", "create"]


def is_upload(call):
    return call[0] == "gh" and call[1][:2] == ["release", "upload"]


def is_tag(call):
    return call[0] == VCS and call[1][:1] == ["tag"]


def is_mutation(call):
    return is_push(call) or is_tag(call) or is_create(call) or is_upload(call)


def is_date(call):
    return call[0] == "date"


def is_field_read(field):
    return lambda call: call[0] == "gh" and call[1][:1] == ["api"] and "--jq" in call[1] and call[1][-1] == "." + field


def is_tag_operation(call):
    return call[0] == VCS and call[1][:1] in (["tag"], ["push"])


# Extractors that cannot run at all: the interpreter fails before main, on a
# SyntaxError or on an import that raises ModuleNotFoundError.
BROKEN_EXTRACTORS = (
    ("syntax-broken", "def broken(:\n"),
    ("import-broken", EXTRACTOR.read_text(encoding="utf-8").replace(
        "from pathlib import Path\n", "from pathlib import Path\nimport cleanlanguage_no_such_module\n", 1)),
)

# Row 72: the remedy the not-immutable readback refusal names.
REMEDY_NOT_IMMUTABLE = "Turn on immutable releases for the repository, then cut a corrective new version."

# Fix round 1: the next step the unreadable readback refusals name (row 78
# adds the determine-step refusal), and the verification path the force
# refusal names. Fix round 2: the force and moved-tag refusals name that
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

# Fix round 3: a dispatch at the tag runs the workflow stored at the tag, and a
# workflow without the publish step name above (older than item 57) can
# republish. So the refusals of a run that is not at the tag name the
# verifying dispatch only for a tag carrying that step, and for any other tag
# forbid a dispatch at it and name a read-only check. The readback refusals
# (REMEDY_UNREADABLE) run at the tag commit, which carries this workflow.
# Fix round 7: the one advice for such a tag, declared once in the job env,
# printed by both sites and repeated in the description. It names the
# authority, the release step of the workflow at that tag, and no procedure:
# no command, file or path.
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
# Fix round 8: each condition the advice states, pinned by its words; the
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
# Fix round 7: the tag-gone text, declared once in the job env and printed by
# both steps with <tag> replaced.
TAG_GONE_ADVICE = ("The tag <tag> is no longer on origin, so no dispatch can select it as the run ref to"
                   " verify the published release; cut a corrective new version.")
TAG_GONE_ECHO = "echo \"${TAG_GONE_ADVICE//<tag>/${RELEASE_TAG}}\" >" + chr(38) + "2"
# A command name, or a file name, path or archive the advice must not carry.
ADVICE_NAMES_A_PROCEDURE = re.compile(
    r"\b(gh|git|sha256sum|cmp|unzip|zip|curl)\b|\.(zip|sha256|md|ya?ml)\b|/|--")
DETERMINE_UNREADABLE = ("Once the release record is readable, check that .github/workflows/release-skill.yml"
                        " at the tag v1.0.15 has the step " + PUBLISH + ". If it does, dispatch this"
                        " workflow again with the force input unchecked and the tag v1.0.15 itself selected"
                        " as the run ref, not main, to verify the published release; cut a corrective"
                        " new version only if that verification fails.")

# Fix round 3: a published release whose publication day is not its Released
# day is refused in the determine step, naming the remedy, not the packager
# re-stamp advice, which leads back to the same verifying dispatch.
PUBLISHED_ON_ANOTHER_DAY = ("Re-stamping the Released line cannot fix this: the published zip carries the"
                            " Released line of the commit it was built from, and an immutable release"
                            " cannot be republished. If the line at this commit was edited after the"
                            " release, restore the value the published zip carries; otherwise the remedy"
                            " is a corrective new version whose Released line names its own publication"
                            " day.")

# Fix round 2: the remedy both refusals name when the tag of a published
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
        self.assertEqual(set(job_env()), {"RELEASE_TAG", "OLDER_TAG_ADVICE", "TAG_GONE_ADVICE"})
        self.assertEqual(set(step_env(VALIDATE)), set())
        self.assertEqual(set(step_env(DETERMINE)), {"GH_TOKEN"})
        self.assertEqual(set(step_env(PACKAGE)), set())
        self.assertEqual(set(step_env(PUBLISH)), {"GH_TOKEN", "FORCE"})
        self.assertEqual(github_env_writes(DETERMINE), {"VERSION"})
        self.assertEqual(github_env_writes(PACKAGE), {"VERSION", "RELEASE_DATED", "RELEASE_DATE"})

    def test_no_env_key_overlaps_an_earlier_github_env_write(self):
        # T2: the result must not depend on runner precedence between a step
        # or job env: key and GITHUB_ENV, which these tests do not model.
        for name in MODELLED:
            with self.subTest(name):
                written = github_env_writes(name)
                self.assertEqual(set(job_env()).union(step_env(name)).intersection(written), set())

    def test_modelled_steps_carry_only_modelled_keys(self):
        # T2: a step-level if or continue-on-error is not modelled, so it fails.
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

    def test_readback_mismatch_names_a_corrective_new_version_and_no_republish(self):
        # R4: an immutable release cannot be republished.
        self.set_state(published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("the remedy is a corrective new version", err)
        self.assertNotIn("force", err)
        self.assertNotIn("republish with", err)

    def test_unreadable_readback_fails_loudly(self):
        self.set_state(published_at="FAIL")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("could not be read back", err)
        self.assertIn(REMEDY_UNREADABLE, err)

    def test_a_release_that_is_not_immutable_fails(self):
        # U1: with no pre-check, the first-publication readback is the only
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
                    else:
                        self.assertIn("immutable field reads ", err)
                        self.assertIn(REMEDY_NOT_IMMUTABLE, err)
                        self.assertNotIn(REMEDY_UNREADABLE, err)
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
                    else:
                        self.assertIn("immutable field reads ", err)
                        self.assertIn(REMEDY_NOT_IMMUTABLE, err)
                        self.assertNotIn(REMEDY_UNREADABLE, err)
                    self.assertNotIn("is immutable", out)
                    calls = self.calls()
                    self.assertLess(self.index_of(calls, is_create), self.index_of(calls, is_field_read("immutable")))
                    self.assertFalse(any(is_field_read("published_at")(c) for c in calls), calls)

    def test_unavailable_extractor_is_reported_as_unavailable(self):
        (self.work / "tools" / "skill-release-date.py").unlink()
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed (exit 2)", err)
        self.assertFalse(any(is_create(c) for c in self.calls()))

    def test_broken_extractor_is_reported_by_the_probe_on_first_publication(self):
        # T3: the probe at the start of the step reports a crashed extractor
        # as that, never as a malformed clock reading.
        for label, body in BROKEN_EXTRACTORS:
            with self.subTest(label):
                self.reset_calls()
                (self.work / "tools" / "skill-release-date.py").write_text(body, encoding="utf-8")
                code, _out, err = self.run_step(PUBLISH)
                self.assertEqual(code, 1, err)
                self.assertIn("unavailable or crashed (exit 1) while probing it", err)
                self.assertIn("ModuleNotFoundError" if label == "import-broken" else "SyntaxError", err)
                self.assertNotIn("malformed", err)
                calls = self.calls()
                self.assertFalse(any(is_tag_operation(c) or is_create(c) for c in calls), calls)


class NoSettingPreCheckTest(WorkflowStepTest):
    """U1: the workflow never reads the repository immutable-releases setting,
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
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
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
    """R1: a re-run at the same commit ends green only on the same publication
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
                self.assertFalse(any(is_create(c) or is_upload(c) for c in calls), calls)
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
                    self.assertNotIn("kept its assets", out)

    def test_broken_extractor_is_reported_by_the_probe_on_a_rerun(self):
        # T3: a re-run reports a crashed extractor as that, never as an
        # unusable published_at.
        for event in RERUN_EVENTS:
            for label, body in BROKEN_EXTRACTORS:
                with self.subTest(event=event, extractor=label):
                    self.reset_calls()
                    self.rerun(event)
                    (self.work / "tools" / "skill-release-date.py").write_text(body, encoding="utf-8")
                    code, out, err = self.run_step(PUBLISH)
                    self.assertEqual(code, 1, err)
                    self.assertIn("unavailable or crashed (exit 1) while probing it", err)
                    self.assertIn("ModuleNotFoundError" if label == "import-broken" else "SyntaxError", err)
                    self.assertNotIn("not a usable UTC instant", err)
                    self.assertNotIn("kept its assets", out)
                    calls = self.calls()
                    self.assertFalse(any(is_create(c) or is_upload(c) for c in calls), calls)
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
                    calls = self.calls()
                    self.assertTrue(any(is_field_read("immutable")(c) for c in calls), calls)
                    self.assertFalse(any(is_field_read("published_at")(c) for c in calls), calls)
                    if expected == 0:
                        self.assertIn("Re-run readback: release v1.0.15 is immutable", out)
                        self.assertIn("kept its assets", out)
                    else:
                        self.assertNotIn("kept its assets", out)


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
        self.assertFalse([c for c in calls if is_mutation(c)], calls)

    def test_force_against_a_published_release_is_refused(self):
        # T1: the same commit, force set.
        self.published(force="true")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("this workflow never republishes a published release", err)
        # Fix round 2: no unconditional corrective-version remedy ahead of the
        # verifying dispatch.
        self.assertNotIn("The remedy for a published release is a corrective new version", err)
        self.assertIn("only moves the tag of a release that is not yet published", err)
        # Fix round 1: the refusal names the fresh dispatch that verifies the
        # published release.
        self.assertIn(VERIFY_BY_DISPATCH, err)
        # Fix round 3: only at a tag carrying this workflow.
        self.assertIn(NEVER_AT_OLDER_TAG, err)
        # Row 71: a re-run keeps the force input, so no re-run is advised.
        self.assertNotIn("re-run", err.lower())
        self.assertNotIn("to verify this one", err)
        self.assertNotIn("overwriting", out + err)
        self.assertNotIn("kept its assets", out)
        self.assert_no_mutation(self.calls())

    def test_the_named_dispatch_verifies_a_release_published_under_force(self):
        # Fix round 1: a force run publishes, then its readback fails for a
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
        self.reset_calls()
        self.set_state(immutable="true", status="200")
        self.inputs["force"] = "true"
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn(VERIFY_BY_DISPATCH, err)
        self.reset_calls()
        self.inputs["force"] = "false"
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        self.assertIn("kept its assets", out)
        calls = self.calls()
        self.assert_no_mutation(calls)
        assert_readback_ran(self, calls, out)

    def test_force_against_a_published_release_never_moves_its_tag(self):
        # T2: the damaging case, a tag at another commit and force set.
        self.published(remote_tag=OTHER_COMMIT, force="true")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("this workflow never republishes a published release", err)
        self.assert_no_mutation(self.calls())

    def test_force_is_refused_for_an_undated_published_release_too(self):
        self.carried["RELEASE_DATED"] = "0"
        self.carried["RELEASE_DATE"] = ""
        self.published(remote_tag=OTHER_COMMIT, force="true")
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("this workflow never republishes a published release", err)
        self.assert_no_mutation(self.calls())

    def test_rerun_without_force_verifies_and_keeps_the_assets(self):
        # T3: regression guard for the verification branch, on both events,
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
                calls = self.calls()
                self.assert_no_mutation(calls)
                assert_readback_ran(self, calls, out)

    def test_missing_asset_names_a_corrective_new_version_not_the_force_input(self):
        # T4
        self.published()
        self.set_state(missing="cleanlanguage.zip.sha256")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("is missing the asset cleanlanguage.zip.sha256", err)
        self.assertIn("cannot be completed in place; cut a corrective new version", err)
        self.assertNotIn("force", err)
        self.assertNotIn("kept its assets", out)
        self.assert_no_mutation(self.calls())

    def test_a_long_asset_list_never_reads_a_present_asset_as_missing(self):
        # Fix round 4 (F3): grep -q exits on its first match, so a printf
        # pipe into it took SIGPIPE (141) on a long asset list, and pipefail
        # then reported a present asset as missing. Here the four required
        # assets come first and 1000 long names follow them.
        self.published()
        self.set_state(extra="1000")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        self.assertNotIn("is missing the asset", err)
        self.assertIn("kept its assets", out)
        calls = self.calls()
        self.assert_no_mutation(calls)
        assert_readback_ran(self, calls, out)

    def test_a_long_asset_list_still_names_a_missing_asset(self):
        # Fix round 4 (F3): the membership check still refuses an absent
        # asset when the list is long.
        self.published()
        self.set_state(extra="1000", missing="cleanlanguage-1.0.15.zip.sha256")
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("is missing the asset cleanlanguage-1.0.15.zip.sha256", err)
        self.assertNotIn("kept its assets", out)
        self.assert_no_mutation(self.calls())

    def test_checksum_mismatch_names_a_corrective_new_version_not_the_force_input(self):
        # T5, for each of the two zips, each checked by its own line.
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
                self.assertNotIn("force", err)
                self.assertNotIn("kept its assets", out)
                self.assert_no_mutation(self.calls())

    def test_moved_tag_of_a_published_release_offers_no_force_remedy(self):
        # T6, which also keeps the former check that FORCE reaches the script
        # only through the declared input: without it the run is refused.
        self.published(remote_tag=OTHER_COMMIT)
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("This workflow never republishes a published release, with or without the force input.", err)
        # Fix round 2: a release whose create call failed after GitHub published
        # it is probably correct, so the refusal names the verifying dispatch
        # first, and a corrective new version only if that verification fails.
        self.assertIn(VERIFY_BY_DISPATCH, err)
        self.assertIn(NEVER_AT_OLDER_TAG, err)
        self.assertNotIn("with or without the force input; cut a corrective new version", err)
        self.assertNotIn("to overwrite", err)
        self.assertNotIn("Refusing the force input", err)
        self.assert_no_mutation(self.calls())

    def test_a_published_release_whose_tag_is_gone_names_a_corrective_new_version(self):
        # Fix round 2: with the tag gone from origin, no dispatch can select
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
                self.assertNotIn("kept its assets", out)
                self.assert_no_mutation(self.calls())

    def test_every_remedy_names_a_corrective_new_version(self):
        # Row 73: the remedy lines, found by their wording (an echo line that
        # carries corrective or new version), all read corrective new version,
        # and no echo line carries a retired wording. The count is reconciled
        # against the workflow, so the probe cannot pass empty. Residual: a
        # remedy phrased without either word is neither counted nor checked.
        echoes = [line for line in WORKFLOW_TEXT.splitlines() if "echo " in line]
        remedies = [line for line in echoes if "corrective" in line or "new version" in line]
        # Fix round 7: the two tag-gone lines now print TAG_GONE_ADVICE from
        # the job env, so they leave this count; the job env values are
        # pinned by test_the_older_tag_advice_and_the_tag_gone_text_each_have_one_source.
        self.assertEqual(len(remedies), 9, remedies)
        for value in (job_env()["OLDER_TAG_ADVICE"], job_env()["TAG_GONE_ADVICE"]):
            self.assertIn("corrective new version", value)
            self.assertNotRegex(value, r"(?<!corrective )new version")
        for line in echoes:
            with self.subTest(line.strip()):
                self.assertNotRegex(line, r"(?<!corrective )new version")
                self.assertNotIn("corrective version", line)
                self.assertNotIn("re-run without", line)

    def test_no_test_name_carries_the_retired_wording(self):
        # Fix round 1: a search for the retired wording finds no test name.
        names = [name for value in list(globals().values())
                 if isinstance(value, type) and issubclass(value, unittest.TestCase)
                 for name in vars(value) if name.startswith("test_")]
        self.assertGreater(len(names), 50, names)
        self.assertEqual([name for name in names if "corrective_version" in name], [])

    def test_force_still_moves_the_tag_of_an_unpublished_release(self):
        # T7: the useful path survives, and its run reads back.
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
        self.assertFalse(any(is_upload(c) for c in calls), calls)
        self.assertIn("First-publication readback", out)

    def test_moved_tag_of_an_unpublished_release_needs_the_force_input(self):
        # T8
        self.set_state(status="404", remote_tag=OTHER_COMMIT)
        code, _out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 1, err)
        self.assertIn("refusing to move it without the force input", err)
        self.assert_no_mutation(self.calls())

    def test_tag_push_of_a_new_release_creates_it(self):
        # T9
        self.runner["GITHUB_EVENT_NAME"] = "push"
        self.set_state(status="404", remote_tag=COMMIT)
        code, out, err = self.run_step(PUBLISH)
        self.assertEqual(code, 0, err)
        calls = self.calls()
        self.assertTrue(any(is_create(c) for c in calls), calls)
        self.assertFalse(any(is_upload(c) or is_push(c) for c in calls), calls)
        self.assertIn("First-publication readback", out)

    def test_unknown_release_status_fails_closed_before_any_mutation(self):
        # T10
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
                self.assert_no_mutation(self.calls())

    def test_no_text_or_path_offers_a_republish(self):
        """T11, structural: problems_republish holds on the real workflow, the
        force input describes only a tag move, and the extractor docstring no
        longer describes a re-upload. Residual: the wording checks are a list
        of known strings; the behavioural cases above are the guard that does
        not depend on wording."""
        self.assertEqual(problems_republish(WF), [])
        description = WF.data.get("on", WF.data.get(True))["workflow_dispatch"]["inputs"]["force"]["description"]
        self.assertTrue(description.startswith("Move the tag of a release that is not yet published"), description)
        # Fix round 10: a statement about this workflow, not a claim that
        # every published release is immutable, which an older workflow can
        # make false.
        self.assertIn("This workflow never republishes a published release, so this input never overwrites"
                      " one.", description)
        self.assertNotIn("A published release is immutable", description)
        self.assertNotIn("byte for byte", description)
        # Fix round 2: for a published release the description names the
        # verifying dispatch first, and a corrective new version only if that
        # verification fails or the tag is gone.
        self.assertNotIn("the remedy for a published release is a corrective new version", description)
        # Fix round 5b: the description ends with the shared advice and then
        # one sentence naming the two remaining cases, so no condition is
        # stated twice.
        # Fix round 6: the advice now names two remedies, so the closing
        # sentence names its remedy rather than pointing back at one.
        last = ("A corrective new version is also the remedy if the dispatch at the tag fails its"
                " verification, or if the tag is no longer on origin.")
        self.assertTrue(description.endswith(OLDER_TAG_ADVICE + " " + last), description)
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
        # Fix round 9: a re-run executes the workflow at the run commit, so
        # the re-run advice is limited to a commit carrying the publish step,
        # consistent with the ban on repeating the runs of an older tag.
        self.assertIn("To finish a run that failed before it published, re-run it only if its commit carries"
                      " the step " + PUBLISH + ", and otherwise dispatch this workflow again from main with the"
                      " same tag.", description)
        self.assertNotIn("re-run it or dispatch", description)
        self.assertIn("or repeat any of its runs", description)
        # Fix round 9: the subject of the remedy is the release, not a command.
        self.assertNotIn("If it fails", description)
        self.assertIn("If that tag is already on origin at another commit, for example because the failed"
                      " run pushed it and main has moved since, check this input on that dispatch from"
                      " main.", description)
        # Fix round 3: the verifying dispatch is named only for a tag whose
        # workflow has the publish step, and a dispatch at any other tag is
        # forbidden, since an older workflow can republish.
        self.assertIn("To verify a release that is already published, first check that"
                      " .github/workflows/release-skill.yml at the tag has the step " + PUBLISH + "; if it"
                      " does, dispatch this workflow again with this input unchecked and the tag itself"
                      " selected as the run ref, not main", description)
        # Fix round 5: the description carries the shared advice verbatim.
        self.assertIn(OLDER_TAG_ADVICE, description)
        # Fix round 4: the description covers every era of tag, so it names
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
        # Fix round 3: every echo line naming a dispatch at the tag as the run
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
        # Fix round 7: the job env declares each text once and each step
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
        # Fix round 8: each stated condition, in the one source and in the
        # verbatim repeat; the two steps print the one source (above).
        description = WF.data.get("on", WF.data.get(True))["workflow_dispatch"]["inputs"]["force"]["description"]
        for condition in ADVICE_CONDITIONS:
            with self.subTest(condition=condition):
                self.assertIn(condition, OLDER_TAG_ADVICE)
                self.assertIn(condition, job_env()["OLDER_TAG_ADVICE"])
                self.assertIn(condition, description)
        sentences = [s for s in re.split(r"(?<=[.;])\s+", OLDER_TAG_ADVICE) if s]
        self.assertEqual(len(sentences), len(set(sentences)), sentences)

    def test_a_failed_tag_lookup_stops_the_publish_step_with_no_tag_gone_advice(self):
        # Fix round 5: a failed lookup is not a tag gone from origin. The
        # mutant that ignores the failure (|| true) reads it as gone, so this
        # test distinguishes the two.
        self.published()
        self.set_state(ls_remote="FAIL")
        code, _out, err = self.run_step(PUBLISH)
        self.assertNotEqual(code, 0, err)
        self.assertNotIn(TAG_GONE, err)
        self.assertNotIn("dispatch this workflow", err)
        self.assert_no_mutation(self.calls())
        self.reset_calls()
        code, _out, err = self.run_step(PUBLISH, ignore_lookup_failure(step_script(PUBLISH)))
        self.assertEqual(code, 1, err)
        self.assertIn(TAG_GONE, err)

    def test_no_printed_text_claims_every_published_release_is_immutable(self):
        # Fix round 11: an older workflow can republish, so no printed line,
        # job env value or input description states, unconditionally, that a
        # release or its assets are immutable, or that nothing (or no
        # workflow) can republish one. The allowed lines are the ones whose
        # truth the workflow establishes first (the readback lines after the
        # immutable check) and the conditional re-stamping line. Residual:
        # this is a pattern over known phrasings, widened in round 12 and in
        # row 87 to the close variants above, and a claim whose subject is "it", a claim
        # split across sentences, or another wording can still slip past it.
        self.assertEqual(immutability_claims(WORKFLOW_TEXT), [])
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
                      # Fix round 12: the close variants VERIFY 9.2 found.
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
                      "Published assets are not mutable."):
            with self.subTest(probe=probe):
                self.assertNotEqual(immutability_claims(probe), [])

    def test_every_success_path_reads_back(self):
        # One readback per remaining success path, dated or not.
        self.assertEqual(READBACK_CALL.findall(step_script(PUBLISH)), READBACK_LABELS)


class ValidateStepTest(WorkflowStepTest):
    """Fix round 8: the version mismatch refusal cannot tell whether the
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
        self.assertFalse(any(c[0] == "gh" for c in self.calls()), self.calls())


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

    def test_unreadable_published_at_names_the_verifying_dispatch(self):
        # Row 78: like the publish-step readback refusals, the refusal names
        # the next step.
        self.set_state(status="200", published_at="FAIL", remote_tag=COMMIT)
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("Could not read published_at for the existing release v1.0.15.", err)
        self.assertNotIn(TAG_GONE, err)
        # Fix round 3: this step may run away from the tag, so the dispatch
        # at the tag is named only for a tag carrying this workflow.
        self.assertIn(DETERMINE_UNREADABLE, err)
        self.assertIn(NEVER_AT_OLDER_TAG, err)
        self.assertNotIn(REMEDY_UNREADABLE, err)

    def test_unreadable_published_at_with_the_tag_gone_names_a_corrective_new_version(self):
        # Fix round 4: as in the publish step, a tag gone from origin cannot
        # be selected as the run ref, so no dispatch is named.
        self.set_state(status="200", published_at="FAIL", remote_tag="")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("Could not read published_at for the existing release v1.0.15.", err)
        self.assertIn(TAG_GONE, err)
        self.assertNotIn("dispatch this workflow", err)
        self.assertTrue(any(c[0] == VCS and c[1][:1] == ["ls-remote"] for c in self.calls()), self.calls())

    def test_a_failed_tag_lookup_stops_the_determine_step_with_no_tag_gone_advice(self):
        # Fix round 5: as in the publish step, and the || true mutant is killed.
        self.set_state(status="200", published_at="FAIL", ls_remote="FAIL")
        code, _out, err = self.run_step(DETERMINE)
        self.assertNotEqual(code, 0, err)
        self.assertIn("Could not read published_at for the existing release v1.0.15.", err)
        self.assertNotIn(TAG_GONE, err)
        self.assertNotIn("dispatch this workflow", err)
        self.assertEqual(self.env_values(), {})
        code, _out, err = self.run_step(DETERMINE, ignore_lookup_failure(step_script(DETERMINE)))
        self.assertEqual(code, 1, err)
        self.assertIn(TAG_GONE, err)

    def test_a_dated_release_with_no_released_line_reaches_the_packager(self):
        # Fix round 8: a version above the undated baseline with no Released
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
        # Fix round 3: the UTC day rolled over between the window check and
        # publication, so published_at names the next day. The verifying run
        # must name the remedy, not the packager re-stamp advice, which would
        # lead back to this same run.
        self.set_state(status="200", published_at="2026-11-16T00:00:02Z")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 1, err)
        self.assertIn("Release v1.0.15 IS PUBLISHED on 2026-11-16 (UTC, published_at 2026-11-16T00:00:02Z),"
                      " but the Released line at this commit names 2026-11-15.", err)
        self.assertIn(PUBLISHED_ON_ANOTHER_DAY, err)
        self.assertNotIn("dispatch this workflow", err)
        self.assertEqual(self.env_values(), {})

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

    def test_rerun_in_sequence_stops_before_the_packager_on_another_day(self):
        # Fix round 3: the determine step refuses, so the packager re-stamp
        # advice is never reached.
        self.set_state(status="200", remote_tag=COMMIT, published_at="2026-11-16T00:00:02Z")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [1], results)
        self.assertIn(PUBLISHED_ON_ANOTHER_DAY, results[0][3])
        self.assertFalse(any(c[0] == "release-package.sh" for c in self.calls()), self.calls())

    def test_rerun_in_sequence_fails_on_a_mutable_release(self):
        self.skill("Version: 1.0.15  \nReleased: 2026-11-14  \n")
        self.set_state(status="200", remote_tag=COMMIT, published_at="2026-11-14T08:00:00Z", immutable="false")
        results = self.chain()
        self.assertEqual([r[1] for r in results], [0, 0, 1], results)
        self.assertIn("immutable field reads false", results[-1][3])


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


class MutationTest(unittest.TestCase):
    """U2: each reproduced defect, and other forms of it, applied to the real
    workflow text, must be named by the structural checks."""

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
        # Round 4 reproduction: valid YAML that the line reader stopped at.
        wf = self.mutated(FORCE_LINE, FORCE_LINE + "\n          RELEASE_DATED: \"0\"\n")
        self.assertEqual(wf.step_env(PUBLISH)["RELEASE_DATED"], "0")
        self.assertNamed(
            wf,
            "step " + repr(PUBLISH) + " declares env keys an earlier step writes to GITHUB_ENV: " + repr(["RELEASE_DATED"]),
            f"step {PUBLISH!r} declares env keys",
        )

    def test_unmodelled_step_writing_release_dated_is_caught(self):
        # Round 4 reproduction: an extra step overriding RELEASE_DATED.
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
        # Item 57 (D4): the step no longer promises an update.
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
                self.assertEqual([arg for arg in rest if arg == "-R" or arg.startswith("--repo")], [], calls)

    def test_determine_probe_and_published_at_read_name_the_release_tag(self):
        self.set_state(status="200")
        code, _out, err = self.run_step(DETERMINE)
        self.assertEqual(code, 0, err)
        self.assert_exact_paths(["status", ".published_at"])
        self.assert_release_tag([])

    def test_determine_probe_of_an_unpublished_release_names_the_release_tag(self):
        # Gemini (F3): the probe is pinned on the 404 path too, the first
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
                # Claude and gemini (F2): the asset list and the verification
                # download read the release of RELEASE_TAG.
                self.assert_release_tag(["view", "download"])


if __name__ == "__main__":
    unittest.main()
