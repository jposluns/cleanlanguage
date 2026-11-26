#!/usr/bin/env python3
"""Tests the ref comparison of tools/release-dry-run.sh by running the whole script in throwaway
repositories.

The dry run proves at exit that it moved no tag, no note and not the HEAD of the worktree that holds
the script, and that no ref that git for-each-ref lists from that worktree contains its own commit;
it does not prove that it moved no other ref (cases 12, 13, 23 and 27), and it does not see the HEAD
or the per-worktree refs of any other worktree (cases 15, 28 and 29). It snapshots, from the
worktree that holds the script (repo_root, which in these cases is the main worktree of the case's
repository), the branch that HEAD names (or that HEAD is detached), the commit that HEAD resolves
to, and every tag and note with its object name, before its run and again in step 6, and fails when
the 2 snapshots differ. Step 6 also fails when a ref that git for-each-ref lists from repo_root
contains the dry run's own commit. A ref other than a tag, a note, that worktree's HEAD or the
branch it has checked out that another worktree moves during the run, as a commit on another
branch or a fetch that moves a remote-tracking ref does, is outside that comparison, so it no
longer fails the run unless it then contains the dry run's commit.

This test runs the real script, not an excerpt of it. Each case builds a repository in a temporary
folder whose commits hold a copy of tools/release-dry-run.sh, byte for byte, and stand-ins for the
tools it calls, and runs that copy with bash from the main worktree, so bash itself reads every line
of the script, in whatever spelling, and every line runs as it would in release-dry-run.yml. The
stand-ins are 1 small Python program, written under the name of each Python tool, and a
tools/release-package.sh that runs it: they read and stamp the versions and dates, build a fixed
archive, refuse a release date that the Released line does not name, write the site files that the
script's assertions read, and pass every gate. The repository has branches main, feature and
other (other checked out in a second worktree), a lightweight tag v1.0.0, an annotated tag v0.9.0
and refs/remotes/origin/main.

A case's writes are made by a git stand-in, first on PATH for the run, that runs the real git for
every call. When the script first asks git to add a worktree, the stand-in makes the case's writes
that it attributes to another worktree, before it adds the worktree. When the script's own commit
of the dry run has been made, the stand-in records that commit and makes the case's writes that the
dry run makes, in the dry run's worktree. So the before snapshot must precede the dry run's first
ref write, and the leak check must read the commit that the dry run made in its own worktree; a
script in which either does not hold fails a case. Every case requires both points to have been
reached and its writes to have succeeded. Concurrency is modelled as sequenced writes, which a
snapshot comparison cannot tell from a race, and no real race is run.

A case expected to pass must exit 0 with the script's success message. A case expected to fail must
exit 1 without it, print the ref that differs and, when it fails on the snapshot comparison, print
the whole before snapshot and the whole after one. The test reads those snapshots itself, with git,
after the case's setup and once the run has ended, in the format that the failure message prints.
Each case also checks that its writes took effect: it compares the whole-repository listing of git
for-each-ref, which the old whole-repository hash compared, taken after the case's setup and again
after the run, and requires exactly the refs that the case names to differ, so the old check failed
exactly the cases that name one. Case 20 also requires its new branch to be at a child of the dry
run's commit, case 27 requires its ref to be at a tree, and cases 28 and 29 require the other
worktree's ref and HEAD to be at the dry run's commit.

The cases, each with its expected outcome:

- 01, the dry run alone: passes.
- 02, a concurrent commit on a branch in another worktree: passes.
- 03, a concurrent update of refs/remotes/origin/main, as a fetch does: passes.
- 04, a concurrent new branch from another worktree: passes.
- 16, as 02 with the main worktree detached: passes.
- 05, the dry run moves an existing tag: fails, naming the tag.
- 06, the dry run creates the dry tag at its commit: fails, naming the tag.
- 07, the dry run checks out a new branch at its commit in its worktree: fails, naming the branch.
- 08, the dry run puts its commit on the branch the main worktree has checked out: fails, naming
  HEAD's commit.
- 09, the dry run puts its commit on the detached HEAD of the main worktree: fails, naming HEAD's
  commit (the old whole-repository hash passed it, since git for-each-ref lists no HEAD).
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
- 20, the dry run makes a child commit of its commit and points a new branch at that descendant:
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
- 26, another worktree detaches the main worktree's HEAD at the same commit: fails, naming HEAD as
  detached (the old whole-repository hash passed it).
- 27, the dry run points a ref in a namespace of its own at its commit's tree: passes, an accepted
  residual, since a ref that peels to no commit contains no commit.
- 28, another worktree points a per-worktree ref of its own at the dry run's commit: passes, an
  accepted residual, since git for-each-ref lists no other worktree's per-worktree refs.
- 29, another worktree checks out the dry run's commit on a detached HEAD: passes, an accepted
  residual, since git for-each-ref lists no HEAD.

The fail-closed cases run the whole script too: in a folder that is not a repository, in a
repository whose HEAD resolves to no commit, with a tag and note listing that git refuses after
both HEAD reads succeed, and with a leak check that git refuses, each fails with the script's
message, never read as an empty listing; in a repository with no tag and no note it passes. A
refused call is made by a git wrapper, first on PATH, that exits 128 when it is given the argument
it refuses and otherwise runs git.

Every git and bash process runs with a fixed environment: HOME and TMPDIR in the temporary folder,
the global and system git configuration pointed at the null device, the commit identity and the
hook folder given as GIT_CONFIG_COUNT entries (the environment form of git -c), fixed author and
committer dates, and DRY_DATE fixed. Every process is bounded by a timeout, runs in a session of its
own, and is killed with its process group when it ends or times out; nothing is left running in the
background.

Residual: the stand-ins replace the packaging, the gates and the site rewrite, which
tools/release-dry-run.sh runs with the real tools in the next step of release-dry-run.yml. The
cases catch a change to the script only when it changes what a case observes, so a change that acts
only outside these cases, such as one that tests for the stand-ins or for the workflow's
environment, or that moves a ref no case writes, is not caught. The cases run on the git of this
machine with its default ref backend.

Usage: python3 -I tools/test-release-dry-run-refs.py
Exit status: 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import os
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
TIMEOUT = 120
REAP_TIMEOUT = 5
MESSAGE = "the dry run changed a git ref, which it must never do"
# The text a snapshot mismatch must print: the whole before snapshot, then the whole after one.
BEFORE = "before:\n{before}\nand after:\n{after}\n"
# The date every run stamps, and the success message of a run at the fixture's version.
DRY_DATE = "2026-01-02"
SUCCESS = "release-dry-run: every step, gate, and assertion passed for v1.0.1 (nothing was published).\n"

# The stand-in for every Python tool the script runs, named by its file name.
STUB = r'''"""A stand-in for a tool of the release path, chosen by its file name, for the ref cases."""
import hashlib
import sys
from pathlib import Path

NAME = Path(sys.argv[0]).stem
SKILL = Path("cleanlanguage/skills/cleanlanguage/SKILL.md")


def field(text, key):
    for line in text.split("\n"):
        if line.startswith(key):
            return line[len(key):].strip()
    return None


def options(args):
    found, index = {}, 0
    while index < len(args):
        if args[index] in ("--check", "--write"):
            found[args[index]] = True
            index += 1
        else:
            found[args[index]] = args[index + 1]
            index += 2
    return found


def pages(found):
    version, tag, checksum, date = found["--version"], found["--tag"], found["--checksum"], found["--date"]
    stamps = f'<meta property="article:modified_time" content="{date}">\n"dateModified": "{date}"\n'
    url = f"https://example.invalid/releases/download/{tag}/cleanlanguage-{version}.zip"
    return {
        "site/_redirects": f"/download {url} 302\n/privacy https://posluns.ca/privacy/ 301\n"
                           "/privacy/ https://posluns.ca/privacy/ 301\n"
                           "/favicon.svg /assets/baseline/logos/cleanlanguage-favicon.svg 301\n"
                           "/apple-touch-icon.png /assets/baseline/logos/cleanlanguage-touch.png 301\n",
        "site/install/index.html": stamps + f'<a href="{url}">zip, version {version}</a>\n'
                                   f"for example <code>cleanlanguage-{version}.zip</code>\n",
        "site/verify/index.html": stamps + f"cleanlanguage-{version}.zip.sha256\n"
                                  f"published checksum for version {version} is "
                                  f'<code class="sum" id="published-checksum">{checksum}</code>\n'
                                  f"sha256sum cleanlanguage-{version}.zip\n",
        "site-src/release.json": f'{{"version": "{version}", "checksum": "{checksum}"}}\n',
        "site-src/site.json": f'{{"id": "install", "modified": "{date}"}}\n'
                              f'{{"id": "verify", "modified": "{date}"}}\n',
        "site/sitemap.xml": "".join(f"<loc>https://cleanlanguage.ai/{page}/</loc>\n<lastmod>{date}</lastmod>\n"
                                    for page in ("install", "verify")),
    }


if NAME == "skill-version":
    print(field(sys.stdin.read(), "Version:"))
elif NAME == "skill-release-date-client":
    if sys.argv[1] == "baseline":
        print("1.0.0")
    else:
        print(field(Path(sys.argv[2]).read_text(encoding="utf-8"), "Released:"))
elif NAME == "release-package":
    found = options(sys.argv[1:])
    text = SKILL.read_text(encoding="utf-8")
    version, released = field(text, "Version:"), field(text, "Released:")
    dist = Path("dist")
    names = (f"cleanlanguage-{version}.zip", "cleanlanguage.zip")
    if released != found["--release-date"]:
        for name in names:
            for path in (dist / name, dist / (name + ".sha256")):
                path.unlink(missing_ok=True)
        sys.exit(f"release-package: the Released line ({released}) does not match the release date "
                 f"({found['--release-date']})")
    dist.mkdir(exist_ok=True)
    data = f"archive of {version}\n".encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    for name in names:
        (dist / name).write_bytes(data)
        (dist / (name + ".sha256")).write_text(f"{digest}  {name}\n", encoding="utf-8")
elif NAME == "set-release-links":
    found = options(sys.argv[1:])
    for path, text in pages(found).items():
        if "--check" in found:
            if Path(path).read_text(encoding="utf-8") != text:
                sys.exit(f"set-release-links: {path} is out of date")
        else:
            Path(path).write_text(text, encoding="utf-8")
'''
STUB_TOOLS = ("skill-version", "skill-release-date-client", "release-package", "set-release-links",
              "generate-sitemap", "check-release-links", "check-page-metadata", "check-links",
              "check-install-page", "build-site", "check-baseline-pin", "check-instructions-page")
STAMPS = '<meta property="article:modified_time" content="2026-01-01">\n"dateModified": "2026-01-01"\n'
# The files of the fixture's first commit, other than the script and the stand-ins.
FILES = {
    "file": "base\n",
    "cleanlanguage/skills/cleanlanguage/SKILL.md": "# Skill\n\nVersion: 1.0.0  \n\nBody.\n",
    "cleanlanguage/.claude-plugin/plugin.json": '{\n  "version": "1.0.0"\n}\n',
    "site-src/site.json": '{"id": "install", "modified": "2026-01-01"}\n{"id": "verify", "modified": "2026-01-01"}\n',
    "site-src/release.json": '{"version": "1.0.0"}\n',
    "site/install/index.html": STAMPS,
    "site/verify/index.html": STAMPS,
    "site/sitemap.xml": "".join(f"<loc>https://cleanlanguage.ai/{page}/</loc>\n<lastmod>2026-01-01</lastmod>\n"
                                for page in ("install", "verify")),
    "site/_redirects": "/privacy https://posluns.ca/privacy/ 301\n",
}
# The git stand-in of the ref cases. It runs the real git for every call. Before the first call that
# adds a worktree it runs concurrent.sh; after the dry run's commit it records that commit and runs
# own.sh in the dry run's worktree. A failing write fails the call, so the run cannot pass.
HOOK = """#!/bin/sh
real={real}
hooks={hooks}
point=
previous=
for arg in "$@"; do
  if [ "${{previous}}" = worktree ] && [ "${{arg}}" = add ]; then point=worktree; fi
  case "${{arg}}" in "Dry run: version "*) point=commit ;; esac
  previous="${{arg}}"
done
if [ "${{point}}" = worktree ] && [ ! -e "${{hooks}}/worktree.done" ]; then
  : > "${{hooks}}/worktree.done"
  PATH={path} bash --noprofile --norc -e "${{hooks}}/concurrent.sh" >&2 || exit 97
  : > "${{hooks}}/concurrent.ok"
fi
if [ "${{point}}" != commit ] || [ -e "${{hooks}}/commit.done" ]; then
  exec "${{real}}" "$@"
fi
: > "${{hooks}}/commit.done"
"${{real}}" "$@" || exit
"${{real}}" rev-parse --verify HEAD > "${{hooks}}/dry" || exit
dry="$(cat "${{hooks}}/dry")" PATH={path} bash --noprofile --norc -e "${{hooks}}/own.sh" >&2 || exit 97
: > "${{hooks}}/own.ok"
"""


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
    env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home), "TMPDIR": str(home), "LC_ALL": "C",
           "TZ": "UTC", "DRY_DATE": DRY_DATE, "GIT_CEILING_DIRECTORIES": str(home),
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_DATE": "2026-01-01T12:00:00 +0000", "GIT_COMMITTER_DATE": "2026-01-01T12:00:00 +0000",
           "GIT_CONFIG_COUNT": str(len(config))}
    for index, (key, value) in enumerate(config):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def real_git(env: dict) -> str:
    found = shutil.which("git", path=env["PATH"])
    if found is None:
        raise AssertionError("no git on PATH")
    return found


def place_script(folder: Path) -> Path:
    """Copy the real script, byte for byte, to folder/tools/release-dry-run.sh."""
    target = folder / "tools" / "release-dry-run.sh"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(DRY_RUN.read_bytes())
    target.chmod(0o755)
    return target


def refusing_git(folder: Path, env: dict, refused: str) -> Path:
    """A folder holding a git wrapper that exits 128 when it is given the argument refused."""
    real = real_git(env)
    folder.mkdir()
    (folder / "git").write_text(
        "#!/bin/sh\n"
        "for arg in \"$@\"; do\n"
        f"  if [ \"${{arg}}\" = {shlex.quote(refused)} ]; then\n"
        f"    printf 'wrapper: refused %s\\n' {shlex.quote(refused)} >&2\n"
        "    exit 128\n"
        "  fi\n"
        "done\n"
        f"exec {shlex.quote(real)} \"$@\"\n", encoding="utf-8")
    (folder / "git").chmod(0o755)
    return folder


def run_script(script: Path, env: dict, first_on_path: Path | None = None):
    """Run the copy of the script with bash from its repository root, as the workflow runs it."""
    env = dict(env)
    if first_on_path is not None:
        env["PATH"] = str(first_on_path) + os.pathsep + env["PATH"]
    return run_bounded(["bash", "--noprofile", "--norc", str(script)], env, script.parent.parent)


CONCURRENT_COMMIT = """printf 'other\\n' >> "${other}/file"
git -C "${other}" commit -q -am "Other worktree\""""
FETCHED = """fetched="$(git -C "${other}" commit-tree -p refs/remotes/origin/main -m Fetched 'refs/remotes/origin/main^{tree}')"
git -C "${other}" update-ref refs/remotes/origin/main "${fetched}\""""

# (case, setup before the run, writes another worktree makes before the dry run adds its worktree,
# writes the dry run makes in its worktree after its commit, with ${dry} naming that commit, expected
# outcome, the texts a failure must print, {dry} standing for the dry run's commit, {before} for the
# before snapshot and {after} for the after one, and the refs whose line in the whole-repository
# listing differs between the end of the setup and the end of the run, which the old
# whole-repository hash compared, so the old hash failed the case exactly when that tuple is not
# empty). A case expected to fail must print MESSAGE; one expected to fail closed must exit 1 with
# its texts and need not print MESSAGE.
CASES = (
    ("01 the dry run alone", "", "", "", "pass", (), ()),
    ("02 a concurrent commit on a branch in another worktree", "", CONCURRENT_COMMIT, "", "pass", (),
     ("refs/heads/other",)),
    ("03 a concurrent update of refs/remotes/origin/main, as a fetch does", "", FETCHED, "", "pass", (),
     ("refs/remotes/origin/main",)),
    ("04 a concurrent new branch from another worktree", "", 'git -C "${other}" branch topic', "", "pass",
     (), ("refs/heads/topic",)),
    ("16 a concurrent commit in another worktree with the main worktree detached", "git checkout -q --detach",
     CONCURRENT_COMMIT, "", "pass", (), ("refs/heads/other",)),
    ("05 the dry run moves an existing tag", "", "", "git tag -f v1.0.0 HEAD", "fail",
     (BEFORE, "{dry} refs/tags/v1.0.0"), ("refs/tags/v1.0.0",)),
    ("06 the dry run creates the dry tag at its commit", "", "", "git tag v1.0.1 HEAD", "fail",
     (BEFORE, "{dry} refs/tags/v1.0.1"), ("refs/tags/v1.0.1",)),
    ("07 the dry run checks out a new branch at its commit in its worktree", "", "", "git checkout -q -b dry-run",
     "fail", ("these refs contain its commit {dry}:\nrefs/heads/dry-run\n",), ("refs/heads/dry-run",)),
    ("08 the dry run puts its commit on the branch the main worktree has checked out", "", "",
     'git -C "${repo_root}" update-ref HEAD "${dry}"', "fail", (BEFORE, "HEAD commit: {dry}"),
     ("refs/heads/main",)),
    ("09 the dry run puts its commit on the detached HEAD of the main worktree", "git checkout -q --detach", "",
     'git -C "${repo_root}" update-ref --no-deref HEAD "${dry}"', "fail", (BEFORE, "HEAD commit: {dry}"), ()),
    ("10 the dry run adds a note", "", "", "git notes add -m dry HEAD", "fail",
     (BEFORE, "refs/notes/commits"), ("refs/notes/commits",)),
    ("11 the dry run points a remote-tracking ref at its commit", "", "",
     "git update-ref refs/remotes/origin/main HEAD", "fail", ("refs/remotes/origin/main",),
     ("refs/remotes/origin/main",)),
    ("12 the dry run deletes a branch other than the checked-out one", "", "",
     'git -C "${repo_root}" branch -q -D feature', "pass", (), ("refs/heads/feature",)),
    ("13 the dry run moves a remote-tracking ref to a commit that already existed", "", "",
     "git update-ref refs/remotes/origin/main feature", "pass", (), ("refs/remotes/origin/main",)),
    ("14 a concurrent tag from another worktree", "", 'git -C "${other}" tag v2.0.0', "", "fail",
     (BEFORE, "refs/tags/v2.0.0"), ("refs/tags/v2.0.0",)),
    ("15 a per-worktree ref inside the dry run's own worktree", "", "",
     "git update-ref refs/bisect/bad HEAD\ngit rev-parse --verify -q refs/bisect/bad >/dev/null", "pass", (), ()),
    ("17 the dry run switches the main worktree to a new branch at the same commit", "", "",
     'git -C "${repo_root}" checkout -q -b twin', "fail", (BEFORE, "HEAD ref: refs/heads/twin"),
     ("refs/heads/twin",)),
    ("18 the dry run detaches the main worktree at the same commit", "", "",
     'git -C "${repo_root}" checkout -q --detach', "fail", (BEFORE, "HEAD ref: detached"), ()),
    ("19 the dry run attaches a detached main worktree to main at the same commit", "git checkout -q --detach", "",
     'git -C "${repo_root}" checkout -q main', "fail", (BEFORE, "HEAD ref: refs/heads/main"), ()),
    ("20 the dry run points a new branch at a descendant of its commit", "", "",
     'child="$(git commit-tree -p "${dry}" -m Descendant "${dry}^{tree}")"\ngit update-ref refs/heads/carry "${child}"',
     "fail",
     ("these refs contain its commit {dry}:\nrefs/heads/carry\n",), ("refs/heads/carry",)),
    ("21 the dry run points refs/stash and a ref in a namespace of its own at its commit", "", "",
     "git update-ref refs/stash HEAD\ngit update-ref refs/keep/dry HEAD", "fail",
     ("these refs contain its commit {dry}:\nrefs/keep/dry\nrefs/stash\n",), ("refs/keep/dry", "refs/stash")),
    ("22 the dry run deletes an existing tag", "", "", "git tag -d v0.9.0 >/dev/null", "fail", (BEFORE,),
     ("refs/tags/v0.9.0",)),
    ("23 the dry run deletes a remote-tracking ref and a ref in a namespace of its own",
     "git update-ref refs/keep/old HEAD", "",
     "git update-ref -d refs/remotes/origin/main\ngit update-ref -d refs/keep/old", "pass", (),
     ("refs/keep/old", "refs/remotes/origin/main")),
    ("24 another worktree moves the branch the main worktree has checked out", "",
     'git -C "${other}" update-ref refs/heads/main refs/heads/feature', "", "fail", (BEFORE,), ("refs/heads/main",)),
    ("25 the dry run deletes the branch the main worktree has checked out", "", "",
     'git -C "${repo_root}" update-ref -d refs/heads/main', "fail closed",
     ("release-dry-run: could not resolve HEAD to a commit",), ("refs/heads/main",)),
    ("26 another worktree detaches the main worktree's HEAD at the same commit", "",
     'git -C "${other}" update-ref --no-deref main-worktree/HEAD HEAD', "", "fail", (BEFORE, "HEAD ref: detached"),
     ()),
    ("27 the dry run points a ref in a namespace of its own at its commit's tree", "", "",
     "git update-ref refs/keep/tree 'HEAD^{tree}'", "pass", (), ("refs/keep/tree",)),
    ("28 another worktree points a per-worktree ref of its own at the dry run's commit", "", "",
     'git -C "${other}" update-ref refs/worktree/leak "${dry}"', "pass", (), ()),
    ("29 another worktree checks out the dry run's commit on a detached HEAD", "", "",
     'git -C "${other}" checkout -q --detach "${dry}"', "pass", (), ()),
)


class Fixture:
    """A throwaway repository whose commits hold a copy of the script and the stand-ins: main
    checked out in the main worktree, feature 1 commit past the base, other checked out in a second
    worktree, v1.0.0 lightweight at main, v0.9.0 annotated at the base, and refs/remotes/origin/main
    at main."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.env = environment(tmp)
        self.main = tmp / "main"
        self.other = tmp / "other"
        self.hooks = tmp / "hooks"
        self.main.mkdir()
        self.hooks.mkdir()
        self.script = place_script(self.main)
        for name in STUB_TOOLS:
            (self.main / "tools" / f"{name}.py").write_text(STUB, encoding="utf-8")
        package = self.main / "tools" / "release-package.sh"
        package.write_text('#!/bin/sh\nexec python3 -I "$(dirname "$0")/release-package.py" "$@"\n',
                           encoding="utf-8")
        package.chmod(0o755)
        for name, text in FILES.items():
            (self.main / name).parent.mkdir(parents=True, exist_ok=True)
            (self.main / name).write_text(text, encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
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

    def git(self, *args: str, cwd: Path | None = None) -> str:
        code, out, err = run_bounded(["git", *args], self.env, cwd or self.main)
        if code != 0:
            raise AssertionError(f"the fixture's git {' '.join(args)} exited {code}: {err.strip()}")
        return out

    def snapshot(self) -> str | None:
        """The refs that step 6 compares, read from the main worktree in the format its failure
        message prints, or None when HEAD resolves to no commit."""
        code, ref, _ = run_bounded(["git", "symbolic-ref", "-q", "HEAD"], self.env, self.main)
        if code not in (0, 1):
            return None
        code, commit, _ = run_bounded(["git", "rev-parse", "--verify", "-q", "HEAD"], self.env, self.main)
        if code != 0:
            return None
        listing = self.git("for-each-ref", "--format=%(objectname) %(refname)", "refs/tags", "refs/notes")
        head = ref.strip() if ref.strip() else "detached"
        return f"HEAD ref: {head}\nHEAD commit: {commit.strip()}\n{listing}".rstrip("\n")

    def hook(self, concurrent: str, own: str) -> Path:
        """Write the case's writes and the git stand-in, and return the folder that holds it."""
        variables = f"repo_root={shlex.quote(str(self.main))}\nother={shlex.quote(str(self.other))}\n"
        (self.hooks / "concurrent.sh").write_text(variables + concurrent + "\n", encoding="utf-8")
        (self.hooks / "own.sh").write_text(variables + 'wt="$(pwd)"\n' + own + "\n", encoding="utf-8")
        folder = self.tmp / "hook"
        folder.mkdir()
        (folder / "git").write_text(HOOK.format(real=shlex.quote(real_git(self.env)),
                                                hooks=shlex.quote(str(self.hooks)),
                                                path=shlex.quote(self.env["PATH"])), encoding="utf-8")
        (folder / "git").chmod(0o755)
        return folder


class RefComparisonCases(unittest.TestCase):
    def run_case(self, setup: str, concurrent: str, own: str):
        """(fixture, exit code, stdout, stderr, dry commit, before snapshot, after snapshot, listing
        before, listing after). The listing is git for-each-ref of the whole repository, taken by
        the test after the case's setup and once the run has ended, and so are the snapshots."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fixture = Fixture(Path(tmp.name))
        if setup:
            code, _, err = run_bounded(["bash", "--noprofile", "--norc", "-e", "-c", setup], fixture.env, fixture.main)
            self.assertEqual(code, 0, f"the case's setup exited {code}: {err}")
        listing_before = fixture.git("for-each-ref")
        before = fixture.snapshot()
        code, out, err = run_script(fixture.script, fixture.env, fixture.hook(concurrent, own))
        for mark in ("concurrent.ok", "own.ok"):
            self.assertTrue((fixture.hooks / mark).exists(),
                            f"the case's writes did not run to the end ({mark} is missing)\n{out}{err}")
        dry = (fixture.hooks / "dry").read_text(encoding="utf-8").strip()
        return fixture, code, out, err, dry, before, fixture.snapshot(), listing_before, fixture.git("for-each-ref")

    @staticmethod
    def differing(before: str, after: str) -> tuple:
        """The refs whose line in git for-each-ref differs between the 2 listings, sorted."""
        def lines(listing):
            return dict(reversed(line.split("\t", 1)) for line in listing.split("\n") if line)
        old, new = lines(before), lines(after)
        return tuple(sorted(ref for ref in old.keys() | new.keys() if old.get(ref) != new.get(ref)))

    def check(self, name, setup, concurrent, own, outcome, texts, changed):
        fixture, code, out, err, dry, snapshot, after_snapshot, before, after = self.run_case(setup, concurrent, own)
        self.assertIsNotNone(snapshot, f"case {name}: the before snapshot could not be read")
        self.assertEqual(self.differing(before, after), tuple(sorted(changed)),
                         f"case {name}: these refs changed in the whole-repository listing, not {changed!r}, so "
                         "the case's writes are not those it states")
        if outcome == "pass":
            self.assertEqual((code, SUCCESS in out), (0, True),
                             f"case {name}: expected the dry run to pass, got exit {code}\n{out}{err}")
        else:
            self.assertEqual(code, 1, f"case {name}: expected the dry run to fail with exit 1, got exit {code}\n"
                             f"{out}{err}")
            self.assertNotIn(SUCCESS, out, f"case {name}: the dry run printed its success message")
            if outcome == "fail":
                self.assertIn(MESSAGE, err, f"case {name}: the failure does not say {MESSAGE!r}\n{err}")
            for text in texts:
                if "{after}" in text:
                    self.assertIsNotNone(after_snapshot, f"case {name}: the after snapshot could not be read")
                wanted = text.format(dry=dry, before=snapshot, after=after_snapshot)
                self.assertIn(wanted, err, f"case {name}: the failure does not name {wanted!r}\n{err}")
        if name.startswith("20 "):
            self.assertEqual(fixture.git("rev-parse", "--verify", "refs/heads/carry^").strip(), dry,
                             "case 20: refs/heads/carry is not at a child of the dry run's commit")
        if name.startswith("27 "):
            self.assertEqual(fixture.git("cat-file", "-t", "refs/keep/tree").strip(), "tree",
                             "case 27: refs/keep/tree is not at a tree")
        if name.startswith("28 "):
            self.assertEqual(fixture.git("rev-parse", "--verify", "refs/worktree/leak", cwd=fixture.other).strip(),
                             dry, "case 28: the other worktree's refs/worktree/leak is not at the dry run's commit")
        if name.startswith("29 "):
            self.assertEqual(fixture.git("rev-parse", "--verify", "HEAD", cwd=fixture.other).strip(), dry,
                             "case 29: the other worktree's HEAD is not at the dry run's commit")
            code, _, _ = run_bounded(["git", "symbolic-ref", "-q", "HEAD"], fixture.env, fixture.other)
            self.assertEqual(code, 1, "case 29: the other worktree's HEAD is not detached")


def case_method(case: tuple):
    def test(self):
        self.check(*case)
    test.__doc__ = f"case {case[0]}: expected to {case[4]}"
    return test


for _case in CASES:
    setattr(RefComparisonCases, f"test_case_{_case[0].split()[0]}", case_method(_case))


class FailClosedCases(unittest.TestCase):
    def test_a_folder_that_is_not_a_repository_fails(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            code, out, err = run_script(place_script(tmp / "plain"), environment(tmp))
            self.assertEqual((code, SUCCESS in out), (1, False), err)
            self.assertIn("release-dry-run: could not read the branch HEAD names", err)

    def test_a_head_that_resolves_to_no_commit_fails(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            env = environment(tmp)
            script = place_script(tmp / "unborn")
            self.assertEqual(run_bounded(["git", "init", "-q", "-b", "main"], env, tmp / "unborn")[0], 0)
            code, out, err = run_script(script, env)
            self.assertEqual((code, SUCCESS in out), (1, False), err)
            self.assertIn("release-dry-run: could not resolve HEAD to a commit", err)

    def test_a_tag_and_note_listing_that_git_refuses_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, "refs/tags")
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assertEqual((code, SUCCESS in out), (1, False), err)
            self.assertIn("wrapper: refused refs/tags", err)
            self.assertIn("release-dry-run: could not list the tags and notes", err)

    def test_a_leak_check_that_git_refuses_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, "--contains")
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assertEqual((code, SUCCESS in out), (1, False), err)
            self.assertIn("wrapper: refused --contains", err)
            self.assertIn("release-dry-run: could not list the refs", err)

    def test_no_tag_and_no_note_passes(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            fixture.git("tag", "-d", "v1.0.0", "v0.9.0")
            self.assertEqual(fixture.git("for-each-ref", "refs/tags", "refs/notes"), "")
            code, out, err = run_script(fixture.script, fixture.env)
            self.assertEqual((code, SUCCESS in out), (0, True), err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
