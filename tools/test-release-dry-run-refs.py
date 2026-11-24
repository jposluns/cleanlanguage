#!/usr/bin/env python3
"""Tests the ref comparison of tools/release-dry-run.sh in throwaway repositories.

The dry run proves at exit that it moved none of the refs it could itself move. It snapshots, from
the main worktree, the branch that HEAD names (or that HEAD is detached), the commit that HEAD
resolves to, and every tag and note with its object name, before its run and again in step 6, and
fails when the 2 snapshots differ. Step 6 also fails when any ref of any namespace contains the
dry run's own commit. A ref other than a tag, a note or the branch the main worktree has checked
out that another worktree moves during the run, as a commit on another branch or a fetch that moves
a remote-tracking ref does, is outside that comparison, so it no longer fails the run unless it then
contains the dry run's commit.

This test runs the script's own text. It extracts from tools/release-dry-run.sh every shell
function defined before the line that starts with refs_before= (fail and the 2 ref functions), that
line, the line that starts with dry_commit=, and step 6, from its line starting "# 6. " up to the
final success message. Each of those anchors, and each function, must occur exactly once; a missing
or repeated anchor fails every case, naming it, and nothing is read as an empty block. The
extraction cases remove and repeat each anchor and each function in a copy of the script's text
and require the extraction to fail, naming it. Each case builds a repository in a temporary folder
with branches main, feature and other (other checked out in a second worktree), a lightweight tag
v1.0.0, an annotated tag v0.9.0 and refs/remotes/origin/main. It then runs, with bash, the
extracted functions, the before snapshot, the dry run's worktree and commit (or the defect the case
models), the dry_commit line, the case's ref writes, and step 6, and checks the exit status. A
failing case must also print the ref that differs, and a case that fails on the snapshot
comparison must print the whole before snapshot as well as the after one. A write that the case
attributes to another worktree is made from the second worktree after the before snapshot and
before step 6: concurrency is modelled as sequenced writes, which a snapshot comparison cannot tell
from a race, and no real race is run.

Each case also checks that its writes took effect: it compares the whole-repository listing of git
for-each-ref before and after the run, which the old whole-repository hash compared, and requires
it to change exactly when the case says that the old check failed.

The cases, each with its expected outcome:

- 01, the dry run alone: passes.
- 02, a concurrent commit on a branch in another worktree: passes.
- 03, a concurrent update of refs/remotes/origin/main, as a fetch does: passes.
- 04, a concurrent new branch from another worktree: passes.
- 16, as 02 with the main worktree detached: passes.
- 05, the dry run moves an existing tag: fails, naming the tag.
- 06, the dry run creates the dry tag at its commit: fails, naming the tag.
- 07, the dry run makes its worktree with -b and commits: fails, naming the branch.
- 08, the dry run commits in the main worktree on a branch: fails, naming HEAD's commit.
- 09, the dry run commits in a detached main worktree: fails, naming HEAD's commit (the old
  whole-repository hash passed it, since git for-each-ref lists no HEAD).
- 10, the dry run adds a note: fails, naming the notes ref.
- 11, the dry run points a remote-tracking ref at its commit: fails, naming that ref.
- 12, the dry run deletes a branch other than the checked-out one: passes, an accepted residual.
- 13, the dry run moves a remote-tracking ref to a commit that already existed: passes, an accepted
  residual.
- 14, a concurrent tag from another worktree: fails, naming the tag, an accepted false failure,
  since tags are release artefacts.
- 15, a per-worktree ref inside the dry run's own worktree: passes, a blind spot before and after.
- 17, the dry run switches the main worktree to a new branch at the same commit: fails, naming the
  branch HEAD names.
- 18, the dry run detaches the main worktree at the same commit: fails, naming HEAD as detached
  (the old whole-repository hash passed it).
- 19, the dry run attaches a detached main worktree to main at the same commit: fails, naming the
  branch HEAD names (the old whole-repository hash passed it).
- 20, the dry run commits again on top of its commit and points a new branch at that descendant:
  fails, naming the branch.
- 21, the dry run points refs/stash and a ref in a namespace of its own at its commit: fails,
  naming both.
- 22, the dry run deletes an existing tag: fails, printing the before snapshot that names it.
- 23, the dry run deletes a remote-tracking ref and a ref in a namespace of its own: passes, an
  accepted residual.
- 24, another worktree moves the branch the main worktree has checked out: fails, printing both
  snapshots.
- 25, the dry run deletes the branch the main worktree has checked out: fails closed, since HEAD
  then resolves to no commit.

The fail-closed cases run the 2 ref functions directly: a folder that is not a repository, a
repository whose HEAD resolves to no commit, a tag and note listing that git refuses after both
HEAD reads succeed, and a leak check given an object name that does not exist each fail with the
script's message, never read as an empty listing; a repository with no tag and no note gives a
snapshot. The refused listing is made by a git wrapper, first on PATH, that exits 128 when it is
asked to list refs/tags and otherwise runs git. A structural case requires that the dry_commit line
follows the dry run's commit and that step 6 holds the after snapshot and the leak check on that
commit as lines of their own, not as comments.

Every git and bash process runs with a fixed environment: HOME in the temporary folder, the global
and system git configuration pointed at the null device, the commit identity and the hook folder
given as GIT_CONFIG_COUNT entries (the environment form of git -c), and fixed author and committer
dates. Every process is bounded by a timeout, runs in a session of its own, and is killed with its
process group when it ends or times out; nothing is left running in the background.

Residual: the cases run the extracted functions and step 6, not the whole script, so the packaging,
the gates and the site rewrite between the 2 snapshots are not run here; tools/release-dry-run.sh
itself runs them in the next step of release-dry-run.yml. The cases run on the git of this machine
with its default ref backend.

Usage: python3 -I tools/test-release-dry-run-refs.py
Exit status: 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DRY_RUN = REPO_ROOT / "tools" / "release-dry-run.sh"
# The bound in seconds on each git or bash process a case starts.
TIMEOUT = 60
REAP_TIMEOUT = 5
FUNCTION = re.compile(r"([a-z_]+)\(\) \{")
# The functions the cases run, each of which the script must define exactly once before refs_before=.
FUNCTIONS = ("fail", "ref_snapshot", "ref_leak_check")
# The line anchors, each of which must start exactly 1 line of the script.
ANCHORS = ("refs_before=", "# 6. ", 'echo "release-dry-run: every step, gate, and assertion passed',
           '  commit -q -am "Dry run: version ', "dry_commit=")
MESSAGE = "the dry run changed a git ref, which it must never do"
# The text a snapshot mismatch must print: the whole before snapshot, then the after one.
BEFORE = "before:\n{before}\nand after:\n"


def run_bounded(args: list, env: dict, cwd: Path, timeout: float = TIMEOUT):
    """Run args in a new session with standard input from /dev/null and return (exit code, stdout,
    stderr). A run that outlives timeout fails the test. However the wait ends, the process group
    is killed and the process is reaped, so nothing it started keeps running."""
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env, cwd=cwd, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(proc.pid)
        proc.communicate(timeout=REAP_TIMEOUT)
        raise AssertionError(f"{args[0]} ran longer than {timeout} seconds and was killed")
    finally:
        kill_group(proc.pid)
        try:
            proc.wait(timeout=REAP_TIMEOUT)
        finally:
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
    return proc.returncode, stdout, stderr


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def environment(home: Path) -> dict:
    """The fixed environment of every process a case starts."""
    config = (("user.name", "release-dry-run test"), ("user.email", "release-dry-run-test@invalid"),
              ("commit.gpgSign", "false"), ("tag.gpgSign", "false"), ("core.hooksPath", os.devnull))
    env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home), "LC_ALL": "C", "TZ": "UTC",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_DATE": "2026-01-01T12:00:00 +0000", "GIT_COMMITTER_DATE": "2026-01-01T12:00:00 +0000",
           "GIT_CONFIG_COUNT": str(len(config))}
    for index, (key, value) in enumerate(config):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def extract(text: str) -> dict:
    """The parts of the script that the cases run, found by content anchors. Raises ValueError,
    naming the anchor, when one is missing or repeated."""
    lines = text.split("\n")

    def only(prefix: str, required: bool = True):
        found = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        if len(found) > 1 or (required and not found):
            raise ValueError(f"tools/release-dry-run.sh holds {len(found)} lines starting with {prefix!r}, not 1")
        return found[0] if found else None

    before = only("refs_before=")
    functions, names, index = [], [], 0
    while index < before:
        match = FUNCTION.fullmatch(lines[index])
        if match:
            end = index + 1
            while end < before and lines[end] != "}":
                end += 1
            if end >= before:
                raise ValueError(f"the function {match.group(1)} of tools/release-dry-run.sh has no closing line")
            functions.append("\n".join(lines[index:end + 1]))
            names.append(match.group(1))
            index = end
        index += 1
    for name in sorted(set(names) | set(FUNCTIONS)):
        if names.count(name) != 1:
            raise ValueError(f"tools/release-dry-run.sh defines the function {name!r} {names.count(name)} times "
                             "before its refs_before= line, not 1")
    step6 = only("# 6. ")
    done = only('echo "release-dry-run: every step, gate, and assertion passed')
    if not before < step6 < done:
        raise ValueError("tools/release-dry-run.sh does not hold refs_before=, step 6 and its success message "
                         "in that order")
    commit = only('  commit -q -am "Dry run: version ')
    dry = only("dry_commit=")
    return {"functions": "\n".join(functions), "names": names, "before": lines[before],
            "dry_commit": lines[dry], "dry_index": dry, "commit_index": commit,
            "step6_index": step6, "step6": "\n".join(lines[step6:done]).rstrip("\n")}


try:
    PARTS = extract(DRY_RUN.read_bytes().decode("utf-8"))
    EXTRACT_ERROR = None
except (OSError, UnicodeDecodeError, ValueError) as error:  # fail closed: every case fails, naming it
    PARTS, EXTRACT_ERROR = None, f"{type(error).__name__}: {error}"

# The dry run as the script makes it: a detached worktree from HEAD and a commit inside it.
DRY_BODY = """git worktree add -q --detach "${wt}" HEAD
cd "${wt}"
printf 'dry\\n' >> file
git commit -q -am "Dry run\""""
# The defect of a lost cd: the commit lands in the main worktree.
MAIN_BODY = """git worktree add -q --detach "${wt}" HEAD
printf 'dry\\n' >> file
git commit -q -am "Dry run\""""
CONCURRENT_COMMIT = """printf 'other\\n' >> "${other}/file"
git -C "${other}" commit -q -am "Other worktree\""""
FETCHED = """fetched="$(git -C "${other}" commit-tree -p refs/remotes/origin/main -m Fetched 'refs/remotes/origin/main^{tree}')"
git -C "${other}" update-ref refs/remotes/origin/main "${fetched}\""""

# (case, setup before the before snapshot, the dry run's body, writes before step 6, expected outcome,
# the texts a failure must print, {dry} standing for the dry run's commit and {before} for the before
# snapshot, and whether the whole-repository listing changes, which is when the old whole-repository
# hash failed the case). A case expected to fail must print MESSAGE; one expected to fail closed
# must exit 1 with its texts and need not print MESSAGE.
CASES = (
    ("01 the dry run alone", "", DRY_BODY, "", "pass", (), False),
    ("02 a concurrent commit on a branch in another worktree", "", DRY_BODY, CONCURRENT_COMMIT, "pass", (), True),
    ("03 a concurrent update of refs/remotes/origin/main, as a fetch does", "", DRY_BODY, FETCHED, "pass", (),
     True),
    ("04 a concurrent new branch from another worktree", "", DRY_BODY, 'git -C "${other}" branch topic', "pass",
     (), True),
    ("16 a concurrent commit in another worktree with the main worktree detached", "git checkout -q --detach",
     DRY_BODY, CONCURRENT_COMMIT, "pass", (), True),
    ("05 the dry run moves an existing tag", "", DRY_BODY, "git tag -f v1.0.0 HEAD", "fail",
     (BEFORE, "{dry} refs/tags/v1.0.0"), True),
    ("06 the dry run creates the dry tag at its commit", "", DRY_BODY, "git tag v1.0.1 HEAD", "fail",
     (BEFORE, "{dry} refs/tags/v1.0.1"), True),
    ("07 the dry run makes its worktree with -b and commits", "",
     DRY_BODY.replace("--detach", "-b dry-run"), "", "fail", ("refs/heads/dry-run",), True),
    ("08 the dry run commits in the main worktree on a branch", "", MAIN_BODY, "", "fail",
     (BEFORE, "HEAD commit: {dry}"), True),
    ("09 the dry run commits in a detached main worktree", "git checkout -q --detach", MAIN_BODY, "", "fail",
     (BEFORE, "HEAD commit: {dry}"), False),
    ("10 the dry run adds a note", "", DRY_BODY, "git notes add -m dry HEAD", "fail",
     (BEFORE, "refs/notes/commits"), True),
    ("11 the dry run points a remote-tracking ref at its commit", "", DRY_BODY,
     "git update-ref refs/remotes/origin/main HEAD", "fail", ("refs/remotes/origin/main",), True),
    ("12 the dry run deletes a branch other than the checked-out one", "", DRY_BODY,
     'git -C "${repo_root}" branch -q -D feature', "pass", (), True),
    ("13 the dry run moves a remote-tracking ref to a commit that already existed", "", DRY_BODY,
     "git update-ref refs/remotes/origin/main feature", "pass", (), True),
    ("14 a concurrent tag from another worktree", "", DRY_BODY, 'git -C "${other}" tag v2.0.0', "fail",
     (BEFORE, "refs/tags/v2.0.0"), True),
    ("15 a per-worktree ref inside the dry run's own worktree", "", DRY_BODY,
     "git update-ref refs/bisect/bad HEAD", "pass", (), False),
    ("17 the dry run switches the main worktree to a new branch at the same commit", "", DRY_BODY,
     'git -C "${repo_root}" checkout -q -b twin', "fail", (BEFORE, "HEAD ref: refs/heads/twin"), True),
    ("18 the dry run detaches the main worktree at the same commit", "", DRY_BODY,
     'git -C "${repo_root}" checkout -q --detach', "fail", (BEFORE, "HEAD ref: detached"), False),
    ("19 the dry run attaches a detached main worktree to main at the same commit", "git checkout -q --detach",
     DRY_BODY, 'git -C "${repo_root}" checkout -q main', "fail", (BEFORE, "HEAD ref: refs/heads/main"), False),
    ("20 the dry run points a new branch at a descendant of its commit", "", DRY_BODY,
     'git commit -q --allow-empty -m Descendant\ngit update-ref refs/heads/carry HEAD', "fail",
     ("these refs contain its commit {dry}:\nrefs/heads/carry\n",), True),
    ("21 the dry run points refs/stash and a ref in a namespace of its own at its commit", "", DRY_BODY,
     "git update-ref refs/stash HEAD\ngit update-ref refs/keep/dry HEAD", "fail",
     ("these refs contain its commit {dry}:\nrefs/keep/dry\nrefs/stash\n",), True),
    ("22 the dry run deletes an existing tag", "", DRY_BODY, "git tag -d v0.9.0 >/dev/null", "fail", (BEFORE,),
     True),
    ("23 the dry run deletes a remote-tracking ref and a ref in a namespace of its own",
     "git update-ref refs/keep/old HEAD", DRY_BODY,
     "git update-ref -d refs/remotes/origin/main\ngit update-ref -d refs/keep/old", "pass", (), True),
    ("24 another worktree moves the branch the main worktree has checked out", "", DRY_BODY,
     'git -C "${other}" update-ref refs/heads/main refs/heads/feature', "fail", (BEFORE,), True),
    ("25 the dry run deletes the branch the main worktree has checked out", "", DRY_BODY,
     'git -C "${repo_root}" update-ref -d refs/heads/main', "fail closed",
     ("release-dry-run: could not resolve HEAD to a commit",), True),
)


class Fixture:
    """A throwaway repository: main checked out in the main worktree, feature 1 commit past the
    base, other checked out in a second worktree, v1.0.0 lightweight at main, v0.9.0 annotated at
    the base, and refs/remotes/origin/main at main."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.env = environment(tmp)
        self.main = tmp / "main"
        self.other = tmp / "other"
        self.wt = tmp / "dry-run"
        self.main.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.main / "file").write_text("base\n", encoding="utf-8")
        self.git("add", "file")
        self.git("commit", "-q", "-m", "Base")
        self.git("tag", "-a", "-m", "v0.9.0", "v0.9.0")
        self.git("checkout", "-q", "-b", "feature")
        (self.main / "file").write_text("base\nfeature\n", encoding="utf-8")
        self.git("commit", "-q", "-am", "Feature")
        self.git("checkout", "-q", "main")
        (self.main / "file").write_text("base\nmain\n", encoding="utf-8")
        self.git("commit", "-q", "-am", "Main")
        self.git("tag", "v1.0.0")
        self.git("update-ref", "refs/remotes/origin/main", "main")
        self.git("worktree", "add", "-q", "-b", "other", str(self.other), "main")

    def git(self, *args: str) -> str:
        code, out, err = run_bounded(["git", *args], self.env, self.main)
        if code != 0:
            raise AssertionError(f"the fixture's git {' '.join(args)} exited {code}: {err.strip()}")
        return out

    def bash(self, script: str, cwd: Path | None = None):
        return run_bounded(["bash", "--noprofile", "--norc", "-c", script], self.env, cwd or self.main)

    def variables(self) -> str:
        return "".join(f"{name}={shlex.quote(str(path))}\n"
                       for name, path in (("repo_root", self.main), ("wt", self.wt), ("other", self.other)))


def parts(case: unittest.TestCase) -> dict:
    """The extracted parts, or a failure of case that names why they could not be extracted."""
    if EXTRACT_ERROR is not None:
        case.fail(f"cannot extract the code under test: {EXTRACT_ERROR}")
    return PARTS


class RefComparisonCases(unittest.TestCase):
    def run_case(self, setup: str, body: str, writes: str):
        """(fixture, exit code, stdout, stderr, dry commit, before snapshot, listing before, listing
        after). The listing is git for-each-ref of the whole repository, taken by the test outside
        the run."""
        code_parts = parts(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fixture = Fixture(Path(tmp.name))
        script = "\n".join((
            "set -euo pipefail",
            fixture.variables(),
            code_parts["functions"],
            'cd "${repo_root}"',
            setup,
            code_parts["before"],
            "printf 'before snapshot\\n%s\\nend of before snapshot\\n' \"${refs_before}\"",
            body,
            code_parts["dry_commit"],
            "printf 'dry commit %s\\n' \"$(git rev-parse --verify HEAD)\"",
            writes,
            code_parts["step6"],
            "printf 'step 6 passed\\n'",
            "",
        ))
        listing_before = fixture.git("for-each-ref")
        code, out, err = fixture.bash(script)
        listing_after = fixture.git("for-each-ref")
        dry = re.search(r"^dry commit ([0-9a-f]{40,64})$", out, re.M)
        snapshot = re.search(r"^before snapshot\n(.*?)\nend of before snapshot$", out, re.M | re.S)
        return (fixture, code, out, err, dry.group(1) if dry else None, snapshot.group(1) if snapshot else None,
                listing_before, listing_after)

    def check(self, name, setup, body, writes, outcome, texts, changed):
        fixture, code, out, err, dry, snapshot, before, after = self.run_case(setup, body, writes)
        self.assertIsNotNone(dry, f"case {name}: the dry run made no commit\n{out}{err}")
        self.assertIsNotNone(snapshot, f"case {name}: the before snapshot was not printed\n{out}{err}")
        self.assertEqual(before != after, changed,
                         f"case {name}: the whole-repository listing {'did not change' if changed else 'changed'}, "
                         "so the case's writes are not those it states")
        if outcome == "pass":
            self.assertEqual((code, "step 6 passed" in out), (0, True),
                             f"case {name}: expected step 6 to pass, got exit {code}\n{err}")
        else:
            self.assertEqual(code, 1, f"case {name}: expected step 6 to fail with exit 1, got exit {code}\n{out}{err}")
            self.assertNotIn("step 6 passed", out, f"case {name}: step 6 passed")
            if outcome == "fail":
                self.assertIn(MESSAGE, err, f"case {name}: the failure does not say {MESSAGE!r}\n{err}")
            for text in texts:
                wanted = text.format(dry=dry, before=snapshot)
                self.assertIn(wanted, err, f"case {name}: the failure does not name {wanted!r}\n{err}")
        if name.startswith("15 "):
            code, _, _ = run_bounded(["git", "rev-parse", "--verify", "-q", "refs/bisect/bad"], fixture.env, fixture.wt)
            self.assertEqual(code, 0, "case 15: the per-worktree ref was not written")


def case_method(case: tuple):
    def test(self):
        self.check(*case)
    test.__doc__ = f"case {case[0]}: expected to {case[4]}"
    return test


for _case in CASES:
    setattr(RefComparisonCases, f"test_case_{_case[0].split()[0]}", case_method(_case))


class FailClosedCases(unittest.TestCase):
    def run_functions(self, tmp: Path, repo_root: Path, call: str, first_on_path: Path | None = None):
        script = "\n".join(("set -euo pipefail", f"repo_root={shlex.quote(str(repo_root))}", parts(self)["functions"],
                            call, "printf 'reached\\n'", ""))
        env = environment(tmp)
        if first_on_path is not None:
            env["PATH"] = str(first_on_path) + os.pathsep + env["PATH"]
        return run_bounded(["bash", "--noprofile", "--norc", "-c", script], env, tmp)

    def test_a_folder_that_is_not_a_repository_fails(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            (tmp / "plain").mkdir()
            code, out, err = self.run_functions(tmp, tmp / "plain", 'snapshot="$(ref_snapshot)"')
            self.assertEqual((code, "reached" in out), (1, False), err)
            self.assertIn("release-dry-run: could not read the branch HEAD names", err)

    def test_a_head_that_resolves_to_no_commit_fails(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            fixture_env = environment(tmp)
            (tmp / "unborn").mkdir()
            run_bounded(["git", "init", "-q", "-b", "main"], fixture_env, tmp / "unborn")
            code, out, err = self.run_functions(tmp, tmp / "unborn", 'snapshot="$(ref_snapshot)"')
            self.assertEqual((code, "reached" in out), (1, False), err)
            self.assertIn("release-dry-run: could not resolve HEAD", err)

    def test_a_tag_and_note_listing_that_git_refuses_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            real = shutil.which("git", path=fixture.env["PATH"])
            self.assertIsNotNone(real, "no git on PATH")
            wrapper = fixture.tmp / "wrapper"
            wrapper.mkdir()
            (wrapper / "git").write_text(
                "#!/bin/sh\n"
                "for arg in \"$@\"; do\n"
                "  if [ \"${arg}\" = refs/tags ]; then\n"
                "    printf 'wrapper: refused to list refs/tags\\n' >&2\n"
                "    exit 128\n"
                "  fi\n"
                "done\n"
                f"exec {shlex.quote(real)} \"$@\"\n", encoding="utf-8")
            (wrapper / "git").chmod(0o755)
            code, out, err = self.run_functions(fixture.tmp, fixture.main, 'snapshot="$(ref_snapshot)"', wrapper)
            self.assertEqual((code, "reached" in out), (1, False), err)
            self.assertIn("wrapper: refused to list refs/tags", err)
            self.assertIn("release-dry-run: could not list the tags and notes", err)

    def test_a_leak_check_that_git_refuses_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            code, out, err = self.run_functions(fixture.tmp, fixture.main, "ref_leak_check " + "0" * 40)
            self.assertEqual((code, "reached" in out), (1, False), err)
            self.assertIn("release-dry-run: could not list the refs", err)

    def test_no_tag_and_no_note_is_a_snapshot(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            env = environment(tmp)
            (tmp / "bare").mkdir()
            for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "Only"]):
                self.assertEqual(run_bounded(["git", *args], env, tmp / "bare")[0], 0)
            code, out, err = self.run_functions(tmp, tmp / "bare", 'ref_snapshot')
            self.assertEqual((code, "reached" in out), (0, True), err)
            self.assertIn("HEAD ref: refs/heads/main", out)


class StructureCases(unittest.TestCase):
    def test_the_leak_check_reads_the_dry_runs_own_commit(self):
        found = parts(self)
        self.assertEqual(found["before"], 'refs_before="$(ref_snapshot)"')
        self.assertEqual(found["dry_commit"], 'dry_commit="$(git rev-parse --verify HEAD)"')
        self.assertTrue(found["commit_index"] < found["dry_index"] < found["step6_index"],
                        "the dry_commit line does not follow the dry run's commit and precede step 6")
        step6 = found["step6"].split("\n")
        for line in ('refs_after="$(ref_snapshot)"', 'ref_leak_check "${dry_commit}"'):
            self.assertEqual(step6.count(line), 1, f"step 6 does not hold the line {line!r} exactly once")


class ExtractionCases(unittest.TestCase):
    """A missing or repeated anchor or function makes the extraction fail, naming it."""

    def extraction_error(self, lines: list) -> str:
        with self.assertRaises(ValueError) as caught:
            extract("\n".join(lines))
        return str(caught.exception)

    def test_a_missing_or_repeated_line_anchor_is_named(self):
        parts(self)
        lines = DRY_RUN.read_bytes().decode("utf-8").split("\n")
        for anchor in ANCHORS:
            found = [i for i, line in enumerate(lines) if line.startswith(anchor)]
            self.assertEqual(len(found), 1, f"the script holds {len(found)} lines starting with {anchor!r}")
            at = found[0]
            for form, changed in (("missing", lines[:at] + lines[at + 1:]), ("repeated", lines[:at + 1] + lines[at:])):
                with self.subTest(anchor=anchor, form=form):
                    self.assertIn(repr(anchor), self.extraction_error(changed))

    def test_a_missing_or_repeated_function_is_named(self):
        parts(self)
        lines = DRY_RUN.read_bytes().decode("utf-8").split("\n")
        for name in FUNCTIONS:
            start = lines.index(f"{name}() {{")
            end = lines.index("}", start)
            for form, changed in (("missing", lines[:start] + lines[end + 1:]),
                                  ("repeated", lines[:end + 1] + lines[start:end + 1] + lines[end + 1:])):
                with self.subTest(function=name, form=form):
                    self.assertIn(f"function {name!r}", self.extraction_error(changed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
