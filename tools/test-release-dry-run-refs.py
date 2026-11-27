#!/usr/bin/env python3
"""Tests the ref comparison of tools/release-dry-run.sh by running the whole script in throwaway
folders.

The dry run proves at exit that it moved no tag, no note and not the HEAD of the worktree that holds
the script, and that no ref that git for-each-ref lists from that worktree contains its own commit.
It snapshots, from the worktree that holds the script (repo_root, which in these cases is the main
worktree of the case's repository), the branch that HEAD names (or that HEAD is detached), the
commit that HEAD resolves to, and every tag and note with its object name, before its run and again
in step 6, and fails when the 2 snapshots differ. Step 6 also fails when a ref that git
for-each-ref lists from repo_root contains the dry run's own commit. A ref that another worktree
writes during the run, as a commit on another branch or a fetch that moves a remote-tracking ref
does, fails the run only when it is a tag or a note, when it is the HEAD of repo_root or the branch
that worktree has checked out, or when it is a ref that git for-each-ref lists from repo_root,
created or moved onto the dry run's commit or a descendant of it; any other such write is outside
the proof. The dry run's commit is the commit that the script's git commit-tree writes and prints,
which the script saves and step 6 reads, never a later HEAD. Every git call of the script after the
before snapshot other than the reads of step 6, the exit cleanup's included, runs with hooks, the
core.fsmonitor program and a pager turned off, and every git process of the dry run with lazy
fetching turned off. Every git process of the dry run that starts after the first 3 git calls that
follow the before snapshot, its tools' included, reads no attribute file other than the
info/attributes file of the repository and, in git archive, the .gitattributes files of the tree it
archives and, in the git check-attr that reads the filter drivers of the dry-run commit, those of
that commit, and runs with every filter driver turned off that the configuration read from the
script's worktree defines or that the info/attributes file names, and, from step 1 on, every one
that an attribute gives a path of the dry-run commit. So no program other than a filter that git
can run from its configuration or from attributes runs during a git call of the script, and no
filter during a git call of the dry run, its tools' included, whatever the configuration that git
reads in any worktree defines, other than a driver that the info/attributes file, or the tree that
git archive archives, comes to name during the run; the run fails unless git refuses a
GIT_ATTR_SOURCE that names no tree with exit 128 and its own message for that refusal, and unless
the HEAD of the throwaway worktree is at that commit once the script has moved it there, and the
move fails unless that HEAD is still at the parent the script read. The leak check reads with
replace refs, the graft file and the shallow file turned off, so no refs/replace/ ref, graft or
shallow boundary can hide a ref that contains the commit. The git commit-tree that makes the
commit runs with commit signing turned off, so the dry run's commit is never signed.

The script's header states the residual of the proof in these words:

Residual: the proof does not catch the deletion of any ref outside tags and notes other than the
branch the script's worktree has checked out, such as another branch, a remote-tracking ref,
refs/stash or a refs/replace/ ref; or a move or creation of such a ref at a commit that does not
contain the dry-run commit, or at an object that peels to no commit, such as a tree or a blob. It
does not see the HEAD or the per-worktree refs of any worktree other than the script's worktree,
the throwaway worktree included, or a ref outside refs/ other than HEAD, such as ORIG_HEAD, of any
worktree, the script's worktree included, so such a ref put on the dry-run commit does not fail it.
It does not see a write to a ref made after the after snapshot, such as a tag that another worktree
makes then, other than a ref that the leak check, which follows that snapshot, finds to contain the
dry-run commit. It does not see anything the exit cleanup does, or a ref moved and then restored
between the 2 snapshots.

Cases 12, 13, 23 and 27 show the first sentence of that residual, and cases 15, 28, 29 and 30 the
second. No case shows the third or the fourth.

This test runs the real script, not an excerpt of it. Each ref case builds a repository in a
temporary folder whose commits hold a copy of tools/release-dry-run.sh, byte for byte, and
stand-ins for the tools it calls, and runs that copy with bash from the main worktree, so bash
itself reads every line of the script, in whatever spelling, and runs every line that the run
reaches, with the stand-ins in place of the tools, the git stand-in below first on PATH and the
fixed environment below, not those of release-dry-run.yml. The stand-ins are 1 small Python
program, written under the name of each Python tool, and a tools/release-package.sh that runs it:
they read and stamp the versions and dates, build a fixed archive, refuse a release date that the
Released line does not name, write the site files that the script's assertions read, and pass every
gate. The repository has branches main, feature and other (other checked out in a second
worktree), a lightweight tag v1.0.0, an annotated tag v0.9.0 and refs/remotes/origin/main.

A ref case's writes are made at 5 points. A git stand-in, first on PATH for the run, runs the real
git for every call and makes the writes of the first 4 points. When the script first asks git to add
a worktree, the stand-in makes the case's first writes, which are all another worktree's, before it
adds the worktree. Once that call has added the worktree, the stand-in records the commit that the
new worktree's HEAD resolves to, makes the case's added writes, which only cases 42 and 44 make, and
records the commit that HEAD then resolves to. When the script runs git commit-tree given the dry
run's message, which it does once it has read the parent of its commit, the stand-in first makes the
case's parent writes, in the dry run's worktree, which only case 43 makes, then runs that call and
records the commit it prints. After the first later git call that leaves the HEAD of the dry run's
worktree at that commit, before that call returns, the stand-in makes the case's second writes, in
the dry run's worktree: these are the dry run's own writes, except in cases 28 and 29, which make
another worktree's writes there because they need the dry run's commit. Once the check of step 5,
the script's last step before step 6, has passed, its stand-in makes the case's late writes, in the
dry run's worktree. So the before snapshot must
precede the dry run's first ref write, the leak check must read the commit that the dry run's git
commit-tree wrote, not the HEAD of its worktree at step 6 (case 39), and the after snapshot and the
leak check must follow step 5; a script in which any of these does not hold fails a ref case. Every
ref case also requires the commit that git commit-tree wrote to be a child of the commit that the
dry run's worktree resolved to once the added writes had run, with the dry run's identity, dates and
message, and with the tree of the commit that worktree was added at, changed only in the version
bump and the Released line. Case 42 moves that worktree to feature first, so a script that reads the
parent in another folder fails it, and a script that writes the tree in another folder, whose index
holds no version bump, fails every ref case. Case 44 attaches that worktree's HEAD to feature first,
so a script whose move of that HEAD follows it to the branch moves feature onto its commit and fails
the case. Case 43 moves that worktree to feature after the script has read the parent, so a script
whose git commit-tree reads HEAD again makes a child of feature and fails the case, and a script
whose move of that HEAD does not require it to be at the parent moves it from feature and passes,
which fails the case. Every ref case other than cases 31 and 43 requires all 5 points to have been
reached and its writes to have succeeded; case 31 requires the first 4, and requires the run to stop
before the fifth, and case 43 requires the first 3, and requires the run to stop before the fourth.
Concurrency is modelled as sequenced writes, which a snapshot comparison cannot tell from a race,
and no real race is run.

A case expected to pass must exit 0 with the script's success message. A ref case expected to fail
must exit 1 without it, print the ref that differs and, when it fails on the snapshot comparison,
print that comparison's sentence, which says that a ref changed during the run, not who changed it,
and the whole before snapshot and the whole after one; when it fails on the leak check, it must
print the leak check's sentence, which says that no ref may contain the dry run's commit, with that
commit, followed by the refs that the case puts on that commit or a descendant of it. The test
reads those snapshots itself, with git, after the case's setup and once the run has ended, in the
format that the failure message prints. Each ref case also checks that its writes took effect: it
compares the whole-repository listing of git
for-each-ref, which the old whole-repository hash compared, taken after the case's setup and again
after the run, and requires exactly the refs that the case names to differ, so the old check failed
exactly the ref cases that name one. Case 20 also requires its new branch to be at a child of the
dry run's commit, case 27 requires its ref to be at a tree, cases 28 and 29 require the other
worktree's ref and HEAD to be at the dry run's commit, case 30 requires ORIG_HEAD of the main
worktree to be at the dry run's commit, case 31 requires the HEAD that its failure names to be at a
child of the dry run's commit, and cases 36, 37 and 38 require their new branch to be at a child of
the dry run's commit that their replace ref, graft or shallow entry shows with no parent.

The ref cases, each with its expected outcome:

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
- 11, the dry run points a remote-tracking ref at its commit: fails, naming its commit and that ref.
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
- 30, the dry run points ORIG_HEAD of the main worktree at its commit: passes, a blind spot before
  and after, since git for-each-ref lists no ref outside refs/.
- 31, once the dry run's worktree is at its commit, a write keeps that commit in a ref and moves the
  HEAD of the dry run's worktree to a child of it: fails closed at the commit, naming that HEAD and
  the dry run's commit.
- 32, the dry run moves an existing tag after its last step: fails, naming the tag.
- 33, the dry run points a ref in a namespace of its own at its commit after its last step: fails,
  naming that ref.
- 34, the dry run adds a note under a notes ref other than refs/notes/commits: fails, naming that
  notes ref.
- 35, the dry run points per-worktree refs of the main worktree at its commit: fails, naming both.
- 36, the dry run points a new branch at a descendant of its commit and hides that commit's parent
  with a replace ref: fails, naming the branch.
- 37, as 36 with a graft in place of the replace ref: fails, naming the branch.
- 38, as 36 with a shallow entry in place of the replace ref: fails, naming the branch.
- 39, the dry run keeps its commit in a ref and moves the HEAD of its worktree to a child of it after
  its last step: fails, naming its commit and that ref.
- 40, the dry run moves an existing notes ref: fails, printing both snapshots.
- 41, the dry run deletes an existing notes ref: fails, printing both snapshots.
- 42, the dry run's worktree is moved to feature after it is added and before the dry run makes its
  commit: passes, and the dry run's commit is a child of feature.
- 43, the dry run's worktree is moved to feature after the dry run reads the parent of its commit:
  fails closed at the move of that HEAD, naming the parent and the dry run's commit, which is a child
  of that parent.
- 44, the dry run's worktree is attached to feature after it is added: passes, the dry run's commit
  is a child of feature, and feature does not move.

The 12 fail-closed cases run the whole script too: in a folder that is not a repository, in a
repository whose HEAD resolves to no commit, with a branch read that exits 2, with a tag and note
listing that git refuses in the before snapshot, with one that git refuses only in step 6, with a
leak check that git refuses, with each git call that makes or reads the dry run's commit or moves
HEAD to it refused in turn, with each git call that lists the filter drivers, finds the
info/attributes file, names the empty tree or reads the filter drivers that the attributes of the
dry run's commit name, git ls-tree and git check-attr, refused in turn, with the git check-attr that
asks git to refuse a GIT_ATTR_SOURCE that names no tree refused with another message than git's
own for that refusal, at exit 128 or at exit 1, or given git's own message at exit 1, or at exit
128 with another line after it or before it, with a blank line after it or before it, without the
newline that ends it, with a NUL byte after it, before it, inside it or before its newline, or with
a carriage return or a space before its newline, with an info/attributes file that cannot be read,
since it is a folder, with a git that ignores GIT_ATTR_SOURCE, and, in the check of
GIT_ATTR_SOURCE, with a mktemp that fails, a temporary file that standard error cannot be written
to, a cmp that cannot compare and an rm that cannot remove, each in turn, each fails with exit 1
and the script's message, never read as an empty listing; in a repository with no tag and no note
it passes. A refused call is made by a git wrapper, first on PATH, that records every call and prints
"wrapper: refused" and the argument it refuses and exits 128, or the status the case names, when it
is given that argument, from the call that the case names on, and otherwise runs git. git's own
message is given by a git wrapper, first on PATH, that writes the standard error that the case
names, byte for byte, from a file, and exits with the status the case names, on each git check-attr
call not given --source, and otherwise runs git. The git that ignores GIT_ATTR_SOURCE is a git
wrapper, first on PATH, that removes it from the environment of every call. A failing mktemp, cmp
or rm is a stand-in of that name, first on PATH: the mktemp stand-in exits 1, or prints the name of
a file in a folder that does not exist, so that the redirection of standard error to it fails; the
cmp stand-in exits 2, as cmp does when it cannot compare; and the rm stand-in exits 1 and removes
nothing. A run that a stand-in fails must record nothing after the check of GIT_ATTR_SOURCE, or,
when that check's git call does not run, after the naming of the empty tree. Each of these
wrappers, and the ones of the case of an info/attributes file that cannot be read and of the case
of those stand-ins, which refuse nothing, also records, in order, every
git call and, through a python3 wrapper first on PATH, every run of python3, which runs every tool
of the script and every Python program of its own. Each failing case requires the script's message
to be the last line of its output, the script's version line to be printed exactly when the
failing call comes after the script's read of the version, and, after the failing call or run,
nothing to be recorded other than the exit cleanup's git worktree remove and, when the failing call
is git ls-tree or git check-attr of the pipeline that reads the filter drivers of the dry-run
commit, the other call of that pipeline, so the run must end at that call. Each run of the case on
the filter settings and of the case of a git that ignores GIT_ATTR_SOURCE, and each run of the case
of the stand-ins other than the one whose rm removes nothing, must also leave in its TMPDIR no entry
that mktemp names, so the script must remove the file in which its check writes standard error on
each of those paths. These 12 cases make no ref
writes and do not use the git stand-in, so they reach none of its points and compare no listing.
The first 2 run the copy of the script in a folder that holds no commit of it, and they require the
wrapper to have recorded only the reads of the before snapshot that precede the failure. They also
turn on git's own trace2 log, which each run of git writes whatever path it is started by, and
require it to record a start of git for exactly those reads. So in a folder that is not a
repository, and in a repository whose HEAD resolves to no commit, the script makes no git call
before those reads, through PATH or by any other path, other than one that turns that log off. No
case shows which git call the script makes first in a repository whose HEAD resolves to a commit.

1 more case, the locale case, runs the dry run with LC_ALL removed from its environment, LANG set
to C.UTF-8 and LANGUAGE to fr, with a git wrapper, first on PATH, that records the LC_ALL of each git
check-attr not given --source, and requires the run to pass and that check to run once, with LC_ALL
set to C, and to leave in its TMPDIR no entry that mktemp names. The wrapper also records the
entries that mktemp names in that TMPDIR when the script reads the version, and the case requires
there to be none, so the script must remove the file of its check before the run goes on. No git
with a translation of its messages is run, so the case shows the locale that the check gives git,
not that git would translate its message without it.

1 more case, the signal case, ends a run with HUP, INT or TERM, each in turn, which a git wrapper,
first on PATH, sends to the process group of the run when the script runs its check of
GIT_ATTR_SOURCE, once it has recorded the entries that mktemp names in the run's TMPDIR. The case
requires that entry list to hold 1 entry, the file in which the check writes standard error, the
run to stop before its read of the version, and the run to leave in its TMPDIR no entry that
mktemp names, so the script must remove that file on an exit that a signal causes.

1 more case, the held-commit case, runs the dry run once, which must pass, and finds the dry-run
commit that the run left in the object store, which is the same object in a second run at the same
HEAD, since its parent, tree, identity, dates and message are. It then points a lightweight tag and
an annotated tag at that commit, a tag at a child of it, and 2 notes refs at that commit and at that
child, and runs the dry run again. Since nothing moves those refs, the 2 snapshots agree; the run
must fail on the leak check alone, with its sentence, which says that no ref may contain the dry
run's commit, not that the run changed a ref, naming exactly those 5 refs, with the
whole-repository listing unchanged. Every ref case that writes a tag or a note fails on the
snapshot comparison, before the leak check, so this case is the one that requires the leak check
to list tags and notes.

1 more case turns commit signing on in the fixture's configuration, with a gpg.program stand-in
that records each call and fails, and first checks, in a repository of its own, that git commit
then tries to sign and fails. The dry run must pass without calling that stand-in. The script
turns signing off for the git commit-tree that makes its commit, but on the git version the cases
ran on git commit-tree does not sign under that setting in any case, so this case does not show
that the script turns it off.

1 more case writes 8 hooks that git runs around a commit, a checkout, an index write or a ref
update, pre-commit, prepare-commit-msg, commit-msg, post-commit, post-checkout,
reference-transaction, post-index-change and pre-auto-gc, to a folder that the fixture's
configuration names as core.hooksPath. Each hook records its name when it runs; the commit-msg
hook also adds a trailer to the message, and the post-commit hook keeps the commit just made in a
ref and moves HEAD to the commit of the same tree and parent with the dry run's message, as a hook
that hides the commit made from the leak check would. The case first checks, in a repository of its
own, that a git commit and a git worktree add then run the first 6 of those hooks. The dry run must
then pass with no hook run and the whole-repository listing unchanged.

7 more cases each configure programs that git runs from its configuration or from attributes, each
of which records its name when it runs, and first check, in a repository of their own, that git
then runs each of them: a core.fsmonitor program, which on its third run in a linked worktree also
moves that worktree's HEAD to a new child of it; clean and smudge commands of a required filter
driver that the main worktree's info/attributes gives every path; the process command of a driver,
not required, that info/attributes gives every path; a pager for each subcommand that the script
runs, with the run's standard output on a pseudo-terminal; textconv and diff command drivers that
info/attributes gives every path, and diff.external; an editor that core.editor names and one that
sequence.editor names; and, in a partial clone made without blobs,
the upload-pack program of its promisor remote. The dry run must pass with none of them run and the
whole-repository listing unchanged, or, in the partial clone, fail closed at its read of the version
with no fetch run.

1 more case, the linked-worktree filter case, configures the clean and smudge commands of 3 filter
drivers only in a file that a conditional include adds to the configuration of a linked worktree,
so the listing of the filter drivers from the main worktree does not see them: info/attributes
gives the first to 1 path, a .gitattributes file committed in the tree that the dry run releases
gives the second to every path under site/, and the file that core.attributesFile names gives the
third to every path under site-src/. The packager's stand-in also runs git archive of HEAD, as
tools/release-package.sh does. The case first checks, in a repository of its own, that a git
worktree add then runs the smudge command of each driver, and that a git archive in that worktree
runs that of the second although GIT_ATTR_SOURCE names the empty tree. The dry run must then pass
with none of them run and the whole-repository listing unchanged. 1 more case gives every path,
through info/attributes, a filter driver named a=b, whose commands either the configuration that
the listing reads or only that of a linked worktree defines, and requires the run to fail with
exit 1 at the script's refusal of that name, before its read of the version, with no command of the
driver run.

1 more case, whose configuration names a hook folder, a core.fsmonitor program, an attributes file
and the commands of 2 filter drivers, reads git's trace2 log of a run and requires every run of git
that the script starts after the before snapshot, other than the reads of step 6, the exit
cleanup's git worktree remove included, to run with core.hooksPath set to the null device and
core.fsmonitor set to false, and each of them other than the first 3, which list the filter
drivers, find the info/attributes file and name the empty tree before the attribute and filter
settings exist, and the check that git refuses a GIT_ATTR_SOURCE that names no tree, which sets
its own, also to run with GIT_ATTR_NOSYSTEM set, GIT_ATTR_SOURCE set to the empty tree,
core.attributesFile set to the null device and the commands of both configured filter drivers
empty; every run of git, the reads of the 2 snapshots and the leak check included, must run with
lazy fetching turned off; the reads must start no program, and the other runs no program other
than git, and no automatic maintenance or fetch, although the case's gc.auto and maintenance.auto
ask for it. The textconv and diff driver case passes against the script before these settings too,
since no git call of the script runs a diff.

1 more case, the text case, compares 4 blocks that are repeated word for word, each run of
whitespace read as 1 space: the residual, the remainder of the filter settings and the remainder of
the tools' git calls, which the comment lines at the top of the script state, and the residual of
the test, which this docstring states. Each block is 1 whole paragraph, the lines from a blank line
or the start of its text to the next blank line or the end of it. Each must be there once, start
with its first words, end with its last words and be the same in the text that states it and in
each text that repeats it, so a word added, removed or changed anywhere in its paragraph, before
its first words or after its last words included, in any of those texts fails the case: the
residual in this docstring, and all 4 in the squash message that .github/squash/290.txt commits
and in the description and the squash message that the export of the branch holds as PR-BODY.md
and SQUASH-MSG at the top of the repository. The script's header, this docstring and the
committed squash message are read in every checkout, CI included. PR-BODY.md and SQUASH-MSG are
not committed, so a checkout of the branch or of main lacks them, and there the case compares
every other text and skips each missing one in a subtest that says so: in CI the header's residual
is compared with this docstring's copy, each of the 4 blocks with the committed squash message, and
no copy in the description. It is the only case that reads the script's text, and it reads only
those comment lines.

Every git and bash process runs with a fixed environment: HOME and TMPDIR in the temporary folder,
the global and system git configuration pointed at the null device, the commit identity and the
hook folder given as GIT_CONFIG_COUNT entries (the environment form of git -c), fixed author and
committer dates, and DRY_DATE fixed; a ref case's run also has REF_CASE_HOOKS, the folder of its
writes. Every git and bash process that the test starts itself is bounded by a timeout, runs in a
session of its own, and is killed with its process group when it ends or times out. A process that
one of those starts, such as a git call of the script or the bash of a case's writes, has no
session or timeout of its own: it runs in that process group, unless it leaves it, and is killed
with it.

Residual of the test: stand-ins replace the packaging, the gates and the site rewrite, which the
next step of release-dry-run.yml runs with the real tools, and the script runs with a git stand-in
first on PATH and an environment that the test fixes, not those of that workflow. A change to the
script is caught only when it changes what a case observes, so a change that acts only outside the
cases, such as one that tests for the stand-ins or for the workflow's environment, or that moves a
ref no case writes or stops step 6 reading one, is not caught. The text case compares only the 4
repeated blocks, each as 1 whole paragraph, so it does not catch a paragraph added next to a block,
a change to any other paragraph, or a change to a text that the checkout lacks, as CI lacks
PR-BODY.md and SQUASH-MSG. The cases run on 1 git version with its default ref backend.

Usage: python3 -I tools/test-release-dry-run-refs.py
Exit status: 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DRY_RUN = REPO_ROOT / "tools" / "release-dry-run.sh"
# The bound in seconds on each git or bash process a case starts.
TIMEOUT = 120
REAP_TIMEOUT = 5
# The sentence with which the snapshot comparison fails, and the one with which the leak check
# fails. Neither says who wrote the ref: another worktree's write fails the comparison too, and a ref
# that held the dry run's commit before the run fails the leak check too.
SNAPSHOT_MESSAGE = "a git ref that the dry run must never move changed during the run"
LEAK_MESSAGE = "no git ref may contain the dry-run commit at the end of the run"
# The text a snapshot mismatch must print: the whole before snapshot, then the whole after one.
BEFORE = "before:\n{before}\nand after:\n{after}\n"
# The date every run stamps, and the success message of a run at the fixture's version.
DRY_DATE = "2026-01-02"
# The identity and the time, in seconds since the epoch, of the commit that every run makes.
DRY_IDENTITY = "release-dry-run <release-dry-run@invalid>"
DRY_EPOCH = int(datetime.datetime.fromisoformat(f"{DRY_DATE}T12:00:00+00:00").timestamp())
SUCCESS = "release-dry-run: every step, gate, and assertion passed for v1.0.1 (nothing was published).\n"
# The name of the empty tree in a repository of SHA-1 object names, as the fixture's are.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# The stand-in for every Python tool the script runs, named by its file name.
STUB = r'''"""A stand-in for a tool of the release path, chosen by its file name, for the ref cases."""
import hashlib
import os
import subprocess
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
    # The late point of a ref case: once the check of step 5, the script's last step before step 6,
    # has passed, make the case's late writes in the dry run's worktree.
    hooks = os.environ.get("REF_CASE_HOOKS")
    if "--check" in found and hooks and not (Path(hooks) / "late.done").exists():
        (Path(hooks) / "late.done").write_bytes(b"")
        if subprocess.run(["bash", "--noprofile", "--norc", "-e", str(Path(hooks) / "late.sh")],
                          stdout=sys.stderr).returncode != 0:
            sys.exit(97)
        (Path(hooks) / "late.ok").write_bytes(b"")
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
# adds a worktree it runs concurrent.sh; once that call has added the worktree, it records the
# commit that the new worktree's HEAD resolves to as checked, runs added.sh with ${wt} naming that
# worktree, and records the commit that HEAD then resolves to as base. On the first git commit-tree
# given the dry run's message, it runs parent.sh with ${wt} naming the folder it runs in, then runs
# that call and records the commit it prints, which is the commit the call wrote, as dry. After the
# first later call that leaves the HEAD of the folder it runs in at that commit, it runs own.sh there.
# A failing write fails the call, so the run cannot pass.
HOOK = """#!/bin/sh
real={real}
hooks={hooks}
point=
previous=
subcommand=
message=
added=
for arg in "$@"; do
  if [ "${{previous}}" = worktree ] && [ "${{arg}}" = add ]; then point=worktree; fi
  if [ "${{previous}}" = --detach ]; then added="${{arg}}"; fi
  if [ "${{arg}}" = commit-tree ]; then subcommand=commit-tree; fi
  case "${{arg}}" in "Dry run: version "*) message=dry ;; esac
  previous="${{arg}}"
done
if [ "${{point}}" = worktree ] && [ ! -e "${{hooks}}/worktree.done" ]; then
  : > "${{hooks}}/worktree.done"
  PATH={path} bash --noprofile --norc -e "${{hooks}}/concurrent.sh" >&2 || exit 97
  : > "${{hooks}}/concurrent.ok"
  "${{real}}" "$@" || exit
  "${{real}}" -C "${{added}}" rev-parse --verify HEAD > "${{hooks}}/checked" || exit
  wt="${{added}}" PATH={path} bash --noprofile --norc -e "${{hooks}}/added.sh" >&2 || exit 97
  "${{real}}" -C "${{added}}" rev-parse --verify HEAD > "${{hooks}}/base" || exit
  : > "${{hooks}}/added.ok"
  exit 0
fi
if [ "${{subcommand}}" = commit-tree ] && [ "${{message}}" = dry ] && [ ! -e "${{hooks}}/commit.done" ]; then
  : > "${{hooks}}/commit.done"
  wt="$(pwd)" PATH={path} bash --noprofile --norc -e "${{hooks}}/parent.sh" >&2 || exit 97
  : > "${{hooks}}/parent.ok"
  "${{real}}" "$@" > "${{hooks}}/dry" || exit
  cat "${{hooks}}/dry"
  exit 0
fi
if [ ! -e "${{hooks}}/commit.done" ] || [ -e "${{hooks}}/own.done" ]; then
  exec "${{real}}" "$@"
fi
"${{real}}" "$@" || exit
if [ "$("${{real}}" rev-parse --verify -q HEAD)" != "$(cat "${{hooks}}/dry")" ]; then
  exit 0
fi
: > "${{hooks}}/own.done"
dry="$(cat "${{hooks}}/dry")" PATH={path} bash --noprofile --norc -e "${{hooks}}/own.sh" >&2 || exit 97
: > "${{hooks}}/own.ok"
"""


def run_bounded(args: list, env: dict, cwd: Path, timeout: float = TIMEOUT):
    """Run args in a new session with standard input from /dev/null and return (exit code, stdout,
    stderr). A run that outlives timeout fails the test. However the wait ends, the process group
    is killed and the process is reaped, so nothing it started keeps running unless it left that
    process group."""
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


def recording_python(folder: Path, env: dict) -> str:
    """Write folder/python3, a wrapper that appends "python3" and the arguments of each run it is
    given, joined by spaces, as a line of folder/events, and runs python3, so that the events log
    records, in order with the git calls that a git wrapper in folder records there, every Python
    tool and every inline Python program that the script runs. Return the shell line with which such
    a git wrapper records a git call there."""
    real = shutil.which("python3", path=env["PATH"])
    if real is None:
        raise AssertionError("no python3 on PATH")
    events = shlex.quote(str(folder / "events"))
    (folder / "python3").write_text(f"#!/bin/sh\nprintf 'python3 %s\\n' \"$*\" >> {events}\nexec {shlex.quote(real)} "
                                    '"$@"\n', encoding="utf-8")
    (folder / "python3").chmod(0o755)
    return f"printf 'git %s\\n' \"$*\" >> {events}\n"


def temporary_files(folder: Path) -> list:
    """The names of the entries of folder, the TMPDIR of a case, that start with tmp., as the names
    that mktemp gives by its default template do, such as the file in which the script's check of
    GIT_ATTR_SOURCE writes standard error and the folder of its throwaway worktree."""
    return sorted(entry.name for entry in folder.iterdir() if entry.name.startswith("tmp."))


def events(folder: Path) -> list:
    """The git calls and python3 runs that the wrappers in folder recorded, in order."""
    return (folder / "events").read_text(encoding="utf-8").splitlines()


def nth_call(word: str, number: int):
    """A predicate, given each recorded event in order, that is true of the number-th git call, counted
    from 1, that is given the argument word, as a refusing wrapper counts them."""
    seen = [0]

    def predicate(event: str) -> bool:
        if event.startswith("git ") and word in event.split()[1:]:
            seen[0] += 1
            return seen[0] == number
        return False
    return predicate


def attribute_source_check(event: str) -> bool:
    """True of the git check-attr not given --source, which asks git to refuse a GIT_ATTR_SOURCE that
    names no tree."""
    words = event.split()
    return words[:1] == ["git"] and "check-attr" in words and "--source" not in words


def refusing_git(folder: Path, env: dict, refused: str | None = None, status: int = 128, after: int = 0) -> Path:
    """A folder holding a git wrapper that appends the arguments of each call it is given, joined by
    spaces, as a line of folder/log, and exits status, without running git, on each call given the
    argument refused after the first after such calls; it runs git for every other call. It also
    records each call in folder/events, with every python3 run, as recording_python does."""
    real = real_git(env)
    folder.mkdir()
    record = recording_python(folder, env)
    refusal = ""
    if refused is not None:
        refusal = (
            "refuse=no\n"
            "for arg in \"$@\"; do\n"
            f"  if [ \"${{arg}}\" = {shlex.quote(refused)} ]; then refuse=yes; fi\n"
            "done\n"
            "if [ \"${refuse}\" = yes ]; then\n"
            f"  printf 'x' >> {shlex.quote(str(folder / 'count'))}\n"
            f"  if [ \"$(wc -c < {shlex.quote(str(folder / 'count'))})\" -gt {after} ]; then\n"
            f"    printf 'wrapper: refused %s\\n' {shlex.quote(refused)} >&2\n"
            f"    exit {status}\n"
            "  fi\n"
            "fi\n")
    (folder / "git").write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(folder / 'log'))}\n"
        + record + refusal +
        f"exec {shlex.quote(real)} \"$@\"\n", encoding="utf-8")
    (folder / "git").chmod(0o755)
    return folder


def mimicking_git(folder: Path, env: dict, status: int, message: bytes) -> Path:
    """A folder holding a git wrapper that, on each git check-attr call not given --source, writes
    message, byte for byte, on standard error and exits status without running git, and runs git for
    every other call. It writes message from the file folder/stderr, since a shell argument cannot
    hold a NUL byte. It records each call in folder/events, with every python3 run, as
    recording_python does."""
    folder.mkdir()
    record = recording_python(folder, env)
    (folder / "stderr").write_bytes(message)
    (folder / "git").write_text(
        "#!/bin/sh\n"
        + record +
        "attr=no\n"
        "source=no\n"
        "for arg in \"$@\"; do\n"
        "  if [ \"${arg}\" = check-attr ]; then attr=yes; fi\n"
        "  if [ \"${arg}\" = --source ]; then source=yes; fi\n"
        "done\n"
        "if [ \"${attr}\" = yes ] && [ \"${source}\" = no ]; then\n"
        f"  cat {shlex.quote(str(folder / 'stderr'))} >&2\n"
        f"  exit {status}\n"
        "fi\n"
        f"exec {shlex.quote(real_git(env))} \"$@\"\n", encoding="utf-8")
    (folder / "git").chmod(0o755)
    return folder


def ignoring_git(folder: Path, env: dict) -> Path:
    """A folder holding a git wrapper that removes GIT_ATTR_SOURCE from the environment of every call,
    as a git that does not read it would ignore it, and runs git. It records each call in
    folder/events, with every python3 run, as recording_python does."""
    folder.mkdir()
    record = recording_python(folder, env)
    (folder / "git").write_text(f"#!/bin/sh\n{record}unset GIT_ATTR_SOURCE\nexec {shlex.quote(real_git(env))} "
                                '"$@"\n', encoding="utf-8")
    (folder / "git").chmod(0o755)
    return folder


def locale_recording_git(folder: Path, env: dict, log: Path, entries: Path) -> Path:
    """A folder holding a git wrapper that, on each git check-attr call not given --source, appends the
    value of LC_ALL in its environment, or "unset", as a line of log, and, on each git show call, the
    word show and then the name of each entry of TMPDIR that starts with tmp., each as a line of
    entries, and runs git for every call."""
    folder.mkdir()
    (folder / "git").write_text(
        "#!/bin/sh\n"
        "attr=no\n"
        "source=no\n"
        "show=no\n"
        "for arg in \"$@\"; do\n"
        "  if [ \"${arg}\" = check-attr ]; then attr=yes; fi\n"
        "  if [ \"${arg}\" = --source ]; then source=yes; fi\n"
        "  if [ \"${arg}\" = show ]; then show=yes; fi\n"
        "done\n"
        "if [ \"${attr}\" = yes ] && [ \"${source}\" = no ]; then\n"
        f"  printf '%s\\n' \"${{LC_ALL-unset}}\" >> {shlex.quote(str(log))}\n"
        "fi\n"
        "if [ \"${show}\" = yes ]; then\n"
        f"  printf 'show\\n' >> {shlex.quote(str(entries))}\n"
        "  for entry in \"${TMPDIR}\"/tmp.*; do\n"
        f"    if [ -e \"${{entry}}\" ]; then printf '%s\\n' \"${{entry##*/}}\" >> {shlex.quote(str(entries))}; fi\n"
        "  done\n"
        "fi\n"
        f"exec {shlex.quote(real_git(env))} \"$@\"\n", encoding="utf-8")
    (folder / "git").chmod(0o755)
    return folder


def signalling_git(folder: Path, env: dict, name: str, entries: Path) -> Path:
    """A folder holding a git wrapper that, on each git check-attr call not given --source, appends the
    name of each entry of TMPDIR that starts with tmp. as a line of entries, then sends the signal name
    to its process group, which is that of the run, and exits 1 if that signal does not end it; it runs
    git for every other call."""
    folder.mkdir()
    (folder / "git").write_text(
        "#!/bin/sh\n"
        "attr=no\n"
        "source=no\n"
        "for arg in \"$@\"; do\n"
        "  if [ \"${arg}\" = check-attr ]; then attr=yes; fi\n"
        "  if [ \"${arg}\" = --source ]; then source=yes; fi\n"
        "done\n"
        "if [ \"${attr}\" = yes ] && [ \"${source}\" = no ]; then\n"
        "  for entry in \"${TMPDIR}\"/tmp.*; do\n"
        f"    if [ -e \"${{entry}}\" ]; then printf '%s\\n' \"${{entry##*/}}\" >> {shlex.quote(str(entries))}; fi\n"
        "  done\n"
        f"  kill -{name} 0\n"
        "  exit 1\n"
        "fi\n"
        f"exec {shlex.quote(real_git(env))} \"$@\"\n", encoding="utf-8")
    (folder / "git").chmod(0o755)
    return folder


def git_log(folder: Path) -> list:
    """The calls that the wrapper in folder recorded, in order."""
    return (folder / "log").read_text(encoding="utf-8").splitlines()


def git_starts(log: Path) -> list:
    """The arguments of each run of git that git's trace2 log at log records, in order, without the
    program name: every run of git writes a start line there, whatever path it is started by."""
    starts = []
    for line in log.read_text(encoding="utf-8").splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4 and fields[2] == "start":
            starts.append(fields[3].split(" ", 1)[1] if " " in fields[3] else "")
    return starts


def last_line(err: str) -> str:
    """The last line of err, the message of the failure that ended the run."""
    lines = err.rstrip("\n").split("\n")
    return lines[-1]


def run_script(script: Path, env: dict, first_on_path: Path | None = None):
    """Run the copy of the script with bash from its repository root, the folder from which the
    workflow runs the script."""
    env = dict(env)
    if first_on_path is not None:
        env["PATH"] = str(first_on_path) + os.pathsep + env["PATH"]
    return run_bounded(["bash", "--noprofile", "--norc", str(script)], env, script.parent.parent)


CONCURRENT_COMMIT = """printf 'other\\n' >> "${other}/file"
git -C "${other}" commit -q -am "Other worktree\""""
FETCHED = """fetched="$(git -C "${other}" commit-tree -p refs/remotes/origin/main -m Fetched 'refs/remotes/origin/main^{tree}')"
git -C "${other}" update-ref refs/remotes/origin/main "${fetched}\""""

# (case, setup before the run, writes another worktree makes before the dry run adds its worktree,
# writes made in the dry run's worktree once its HEAD is at the dry run's commit, before the git call
# that put it there returns, with ${dry} naming that commit (the dry run's own writes, except in
# cases 28 and 29), expected
# outcome, the texts a failure must print, {dry} standing for the dry run's commit, {before} for the
# before snapshot and {after} for the after one, and the refs whose line in the whole-repository
# listing differs between the end of the setup and the end of the run, which the old
# whole-repository hash compared, so the old hash failed the case exactly when that tuple is not
# empty). A case expected to fail must print the sentence of the check it fails, SNAPSHOT_MESSAGE
# when its texts hold BEFORE and LEAK_MESSAGE otherwise; one expected to fail closed must exit 1 with
# its texts and need print neither.
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
     "git update-ref refs/remotes/origin/main HEAD", "fail",
     ("these refs contain its commit {dry}:\nrefs/remotes/origin/main\n",), ("refs/remotes/origin/main",)),
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
    ("30 the dry run points ORIG_HEAD of the main worktree at its commit", "", "",
     'git -C "${repo_root}" update-ref ORIG_HEAD "${dry}"', "pass", (), ()),
    ("31 once the dry run's worktree is at its commit, a write keeps that commit in a ref and moves that "
     "worktree's HEAD to a child of it",
     "", "",
     'git update-ref refs/keep/dry HEAD\nchild="$(git commit-tree -p HEAD -m Moved \'HEAD^{tree}\')"\n'
     'git update-ref --no-deref HEAD "${child}"\nprintf \'%s\\n\' "${child}" > "${REF_CASE_HOOKS}/child"',
     "fail closed",
     ("release-dry-run: the HEAD of the dry run's worktree is at {child}, not at the dry-run commit "
      "{dry}; another process moved that HEAD\n",),
     ("refs/keep/dry",)),
    ("32 the dry run moves an existing tag after its last step", "", "", "", "fail",
     (BEFORE, "{dry} refs/tags/v1.0.0"), ("refs/tags/v1.0.0",)),
    ("33 the dry run points a ref in a namespace of its own at its commit after its last step", "", "", "",
     "fail", ("these refs contain its commit {dry}:\nrefs/keep/late\n",), ("refs/keep/late",)),
    ("34 the dry run adds a note under a notes ref other than refs/notes/commits", "", "",
     "git notes --ref=review add -m dry HEAD", "fail", (BEFORE, "refs/notes/review"), ("refs/notes/review",)),
    ("35 the dry run points per-worktree refs of the main worktree at its commit", "", "",
     'git -C "${repo_root}" update-ref refs/bisect/bad "${dry}"\n'
     'git -C "${repo_root}" update-ref refs/worktree/leak "${dry}"', "fail",
     ("these refs contain its commit {dry}:\nrefs/bisect/bad\nrefs/worktree/leak\n",),
     ("refs/bisect/bad", "refs/worktree/leak")),
    ("36 the dry run hides a new branch at a descendant of its commit with a replace ref", "", "",
     'child="$(git commit-tree -p "${dry}" -m Descendant "${dry}^{tree}")"\ngit update-ref refs/heads/carry "${child}"\n'
     'git replace "${child}" "$(git commit-tree -m Replacement "${dry}^{tree}")"', "fail",
     ("these refs contain its commit {dry}:\nrefs/heads/carry\n",), ("refs/heads/carry", "refs/replace/{carry}")),
    ("37 the dry run hides a new branch at a descendant of its commit with a graft", "", "",
     'child="$(git commit-tree -p "${dry}" -m Descendant "${dry}^{tree}")"\ngit update-ref refs/heads/carry "${child}"\n'
     'printf \'%s\\n\' "${child}" >> "$(git rev-parse --git-path info/grafts)"', "fail",
     ("these refs contain its commit {dry}:\nrefs/heads/carry\n",), ("refs/heads/carry",)),
    ("38 the dry run hides a new branch at a descendant of its commit with a shallow entry", "", "",
     'child="$(git commit-tree -p "${dry}" -m Descendant "${dry}^{tree}")"\ngit update-ref refs/heads/carry "${child}"\n'
     'printf \'%s\\n\' "${child}" >> "$(git rev-parse --git-path shallow)"', "fail",
     ("these refs contain its commit {dry}:\nrefs/heads/carry\n",), ("refs/heads/carry",)),
    ("39 the dry run keeps its commit in a ref and moves its worktree's HEAD to a child of it after its last "
     "step", "", "", "", "fail", ("these refs contain its commit {dry}:\nrefs/keep/held\n",), ("refs/keep/held",)),
    ("40 the dry run moves an existing notes ref", "git notes add -m old HEAD", "", "git notes add -m dry HEAD",
     "fail", (BEFORE, "refs/notes/commits"), ("refs/notes/commits",)),
    ("41 the dry run deletes an existing notes ref", "git notes add -m old HEAD", "",
     "git update-ref -d refs/notes/commits", "fail", (BEFORE, "refs/notes/commits"), ("refs/notes/commits",)),
    ("42 the dry run's worktree is moved to another commit before the dry run makes its commit", "", "", "",
     "pass", (), ()),
    ("43 the dry run's worktree is moved to another commit after the dry run reads the parent of its commit",
     "", "", "", "fail closed",
     ("release-dry-run: could not move the HEAD of the dry run's worktree from {base} to the dry-run commit "
      "{dry}\n",), ()),
    ("44 the dry run's worktree is attached to feature before the dry run makes its commit", "", "", "",
     "pass", (), ()),
)
# The writes made in the dry run's worktree once the dry run has read the parent of its commit, before
# its git commit-tree runs, by case number, with ${wt} naming that worktree. Every other ref case makes
# none.
PARENT = {
    "43": 'git update-ref --no-deref HEAD refs/heads/feature\n'
          'test "$(git rev-parse --verify HEAD)" = "$(git rev-parse --verify refs/heads/feature)"',
}
# The late writes of the cases that make them, by case number: writes the dry run makes in its
# worktree once the check of step 5, its last step before step 6, has passed, with ${dry} naming the
# dry-run commit. Every other ref case makes no late writes.
LATE = {
    "32": "git tag -f v1.0.0 HEAD",
    "33": "git update-ref refs/keep/late HEAD",
    "39": 'git update-ref refs/keep/held "${dry}"\nchild="$(git commit-tree -p "${dry}" -m Later "${dry}^{tree}")"\n'
          'git update-ref --no-deref HEAD "${child}"\ntest "$(git rev-parse --verify HEAD)" = "${child}"',
}
# The writes made once the dry run has added its worktree, before it makes its commit, by case
# number, with ${wt} naming that worktree. Every other ref case makes none.
ADDED = {
    "42": 'git -C "${wt}" update-ref --no-deref HEAD refs/heads/feature',
    "44": 'git -C "${wt}" symbolic-ref HEAD refs/heads/feature',
}
# The ref cases that must stop at the dry-run commit, and so must not reach the late point.
STOP_AT_COMMIT = ("31",)
# The ref cases that must stop at the move of the dry run's worktree to its commit, and so must reach
# neither the point after that move nor the late point.
STOP_AT_MOVE = ("43",)


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

    def hook(self, concurrent: str, own: str, late: str = "", added: str = "", parent: str = "") -> Path:
        """Write the case's writes and the git stand-in, and return the folder that holds it."""
        variables = f"repo_root={shlex.quote(str(self.main))}\nother={shlex.quote(str(self.other))}\n"
        (self.hooks / "concurrent.sh").write_text(variables + concurrent + "\n", encoding="utf-8")
        (self.hooks / "added.sh").write_text(variables + added + "\n", encoding="utf-8")
        (self.hooks / "parent.sh").write_text(variables + parent + "\n", encoding="utf-8")
        (self.hooks / "own.sh").write_text(variables + 'wt="$(pwd)"\n' + own + "\n", encoding="utf-8")
        (self.hooks / "late.sh").write_text(
            variables + f'wt="$(pwd)"\ndry="$(cat {shlex.quote(str(self.hooks / "dry"))})"\n' + late + "\n",
            encoding="utf-8")
        folder = self.tmp / "hook"
        folder.mkdir()
        (folder / "git").write_text(HOOK.format(real=shlex.quote(real_git(self.env)),
                                                hooks=shlex.quote(str(self.hooks)),
                                                path=shlex.quote(self.env["PATH"])), encoding="utf-8")
        (folder / "git").chmod(0o755)
        return folder


class RefComparisonCases(unittest.TestCase):
    def run_case(self, number: str, setup: str, concurrent: str, own: str):
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
        env = dict(fixture.env, REF_CASE_HOOKS=str(fixture.hooks))
        code, out, err = run_script(fixture.script, env,
                                    fixture.hook(concurrent, own, LATE.get(number, ""), ADDED.get(number, ""),
                                                 PARENT.get(number, "")))
        marks = ("concurrent.ok", "added.ok", "parent.ok")
        if number not in STOP_AT_MOVE:
            marks += ("own.ok",)
        if number not in STOP_AT_COMMIT + STOP_AT_MOVE:
            marks += ("late.ok",)
        for mark in marks:
            self.assertTrue((fixture.hooks / mark).exists(),
                            f"the case's writes did not run to the end ({mark} is missing)\n{out}{err}")
        if number in STOP_AT_COMMIT:
            self.assertFalse((fixture.hooks / "late.done").exists(),
                             f"case {number}: the run went on past the dry-run commit\n{out}{err}")
        if number in STOP_AT_MOVE:
            self.assertFalse((fixture.hooks / "own.done").exists() or (fixture.hooks / "late.done").exists(),
                             f"case {number}: the run moved the HEAD of its worktree to the dry-run commit, or "
                             f"went on past that move\n{out}{err}")
        dry = (fixture.hooks / "dry").read_text(encoding="utf-8").strip()
        return fixture, code, out, err, dry, before, fixture.snapshot(), listing_before, fixture.git("for-each-ref")

    def assert_dry_commit(self, name: str, fixture: Fixture, dry: str) -> None:
        """The commit that the dry run's git commit-tree wrote is a child of base, the commit that
        the HEAD of the dry run's worktree resolved to once the case's writes at that point had run,
        with the dry run's identity, dates and message, and its tree is that of checked, the commit
        the worktree was added at, with only the version bump and the Released line changed."""
        checked = (fixture.hooks / "checked").read_text(encoding="utf-8").strip()
        base = (fixture.hooks / "base").read_text(encoding="utf-8").strip()
        tree = fixture.git("rev-parse", "--verify", f"{dry}^{{tree}}").strip()
        stamp = f"{DRY_EPOCH} +0000"
        self.assertEqual(fixture.git("cat-file", "commit", dry),
                         f"tree {tree}\nparent {base}\nauthor {DRY_IDENTITY} {stamp}\n"
                         f"committer {DRY_IDENTITY} {stamp}\n\nDry run: version 1.0.1\n",
                         f"case {name}: the dry run's commit is not the child of {base} it must make")
        self.assertEqual(fixture.git("diff-tree", "-r", "--name-only", checked, dry).split(),
                         ["cleanlanguage/.claude-plugin/plugin.json", "cleanlanguage/skills/cleanlanguage/SKILL.md"],
                         f"case {name}: the dry run's commit changes other files than the version bump")
        self.assertEqual(fixture.git("show", f"{dry}:cleanlanguage/skills/cleanlanguage/SKILL.md"),
                         f"# Skill\n\nVersion: 1.0.1  \nReleased: {DRY_DATE}  \n\nBody.\n",
                         f"case {name}: the dry run's commit does not hold the version bump")
        self.assertEqual(fixture.git("show", f"{dry}:cleanlanguage/.claude-plugin/plugin.json"),
                         '{\n  "version": "1.0.1"\n}\n',
                         f"case {name}: the dry run's commit does not hold the plugin version bump")
        if name.startswith(("42 ", "44 ")):
            feature = fixture.git("rev-parse", "--verify", "refs/heads/feature").strip()
            self.assertEqual((base, checked == base), (feature, False),
                             f"case {name}: the dry run's worktree was not moved from the commit it was added at "
                             "to feature before the dry run made its commit")

    @staticmethod
    def differing(before: str, after: str) -> tuple:
        """The refs whose line in git for-each-ref differs between the 2 listings, sorted."""
        def lines(listing):
            return dict(reversed(line.split("\t", 1)) for line in listing.split("\n") if line)
        old, new = lines(before), lines(after)
        return tuple(sorted(ref for ref in old.keys() | new.keys() if old.get(ref) != new.get(ref)))

    def check(self, name, setup, concurrent, own, outcome, texts, changed):
        number = name.split()[0]
        fixture, code, out, err, dry, snapshot, after_snapshot, before, after = self.run_case(number, setup,
                                                                                              concurrent, own)
        self.assertIsNotNone(snapshot, f"case {name}: the before snapshot could not be read")
        if any("{carry}" in ref for ref in changed):
            carry = fixture.git("rev-parse", "--verify", "refs/heads/carry").strip()
            changed = tuple(ref.format(carry=carry) for ref in changed)
        self.assertEqual(self.differing(before, after), tuple(sorted(changed)),
                         f"case {name}: these refs changed in the whole-repository listing, not {changed!r}, so "
                         "the case's writes are not those it states")
        self.assert_dry_commit(name, fixture, dry)
        if outcome == "pass":
            self.assertEqual((code, SUCCESS in out), (0, True),
                             f"case {name}: expected the dry run to pass, got exit {code}\n{out}{err}")
        else:
            self.assertEqual(code, 1, f"case {name}: expected the dry run to fail with exit 1, got exit {code}\n"
                             f"{out}{err}")
            self.assertNotIn(SUCCESS, out, f"case {name}: the dry run printed its success message")
            if outcome == "fail":
                message = SNAPSHOT_MESSAGE if BEFORE in texts else LEAK_MESSAGE
                self.assertIn(message, err, f"case {name}: the failure does not say {message!r}\n{err}")
            for text in texts:
                if "{after}" in text:
                    self.assertIsNotNone(after_snapshot, f"case {name}: the after snapshot could not be read")
                if "{child}" in text:
                    self.assertTrue((fixture.hooks / "child").exists(), f"case {name}: the case recorded no child")
                    child = (fixture.hooks / "child").read_text(encoding="utf-8").strip()
                    self.assertEqual(fixture.git("rev-parse", "--verify", f"{child}^").strip(), dry,
                                     f"case {name}: the HEAD it moved is not at a child of the dry run's commit")
                    text = text.replace("{child}", child)
                base = (fixture.hooks / "base").read_text(encoding="utf-8").strip()
                wanted = text.format(dry=dry, base=base, before=snapshot, after=after_snapshot)
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
        if name.startswith("30 "):
            self.assertEqual(fixture.git("rev-parse", "--verify", "ORIG_HEAD").strip(), dry,
                             "case 30: ORIG_HEAD of the main worktree is not at the dry run's commit")
        if name.startswith("36 "):
            self.assertEqual(fixture.git("--no-replace-objects", "rev-parse", "--verify", "refs/heads/carry^").strip(),
                             dry, "case 36: refs/heads/carry is not at a child of the dry run's commit")
            self.assertEqual(fixture.git("rev-list", "--count", "refs/heads/carry").strip(), "1",
                             "case 36: the replace ref does not hide the parent of refs/heads/carry")
        if name.startswith(("37 ", "38 ")):
            parents = [line for line in fixture.git("--no-replace-objects", "cat-file", "-p",
                                                    "refs/heads/carry").splitlines() if line.startswith("parent ")]
            self.assertEqual(parents, [f"parent {dry}"],
                             f"case {name}: refs/heads/carry is not at a child of the dry run's commit")
            self.assertEqual(fixture.git("rev-list", "--count", "refs/heads/carry").strip(), "1",
                             f"case {name}: the {'graft' if number == '37' else 'shallow entry'} does not hide "
                             "the parent of refs/heads/carry")


def case_method(case: tuple):
    def test(self):
        self.check(*case)
    test.__doc__ = f"case {case[0]}: expected to {case[4]}"
    return test


for _case in CASES:
    setattr(RefComparisonCases, f"test_case_{_case[0].split()[0]}", case_method(_case))


# The line the script prints once it has read the version at HEAD, after the before snapshot, the
# reads of the filter settings and the check of GIT_ATTR_SOURCE.
VERSION_LINE = "release-dry-run: version 1.0.0 at HEAD"
# The text of the exit cleanup's git worktree remove, the only git call that may follow the call that
# fails a run, other than a call that runs in the same pipeline as it.
CLEANUP = " worktree remove --force "


class FailClosedCases(unittest.TestCase):
    def assert_stops(self, code, out, err, message, reached_version):
        """The run failed with exit 1, its last message starts with message, and it printed the version
        line exactly when reached_version is true."""
        self.assertEqual((code, SUCCESS in out), (1, False), f"exit {code}\n{out}{err}")
        self.assertTrue(last_line(err).startswith(message),
                        f"the run did not end with {message!r}\n{err}")
        self.assertEqual(VERSION_LINE in out, reached_version,
                         f"the run {'did not reach' if reached_version else 'went on to'} the version line\n{out}{err}")

    def assert_ends_at(self, folder: Path, failing, partners: tuple = ()) -> None:
        """The run did no work after the event that failed it, the first event that the wrappers in
        folder recorded for which failing is true: every later event is a git call that holds the text
        of one of partners, the calls that run in the same pipeline as the failing one, or of the exit
        cleanup's git worktree remove, so no later step, no tool and no other python3 run."""
        recorded = events(folder)
        index = next((number for number, event in enumerate(recorded) if failing(event)), None)
        self.assertIsNotNone(index, f"the wrappers recorded no event that fails the run: {recorded}")
        later = [event for event in recorded[index + 1:]
                 if not (event.startswith("git ") and any(text in event for text in (*partners, CLEANUP)))]
        self.assertEqual(later, [], f"the run went on past {recorded[index]!r}")

    def test_a_folder_that_is_not_a_repository_fails(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            env = dict(environment(tmp), GIT_TRACE2=str(tmp / "trace2"))
            wrapper = refusing_git(tmp / "wrapper", env)
            code, out, err = run_script(place_script(tmp / "plain"), env, wrapper)
            self.assert_stops(code, out, err, "release-dry-run: could not read the branch HEAD names", False)
            calls = git_log(wrapper)
            self.assertEqual(len(calls), 1, f"the script made other git calls than the branch read: {calls}")
            self.assertTrue(calls[0].startswith("-C ") and calls[0].endswith(" symbolic-ref -q HEAD"), calls)
            self.assertEqual(git_starts(tmp / "trace2"), calls,
                             "git's trace2 log records other runs of git than the branch read")
            self.assert_ends_at(wrapper, nth_call("symbolic-ref", 1))

    def test_a_head_that_resolves_to_no_commit_fails(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            env = environment(tmp)
            script = place_script(tmp / "unborn")
            self.assertEqual(run_bounded(["git", "init", "-q", "-b", "main"], env, tmp / "unborn")[0], 0)
            env = dict(env, GIT_TRACE2=str(tmp / "trace2"))
            wrapper = refusing_git(tmp / "wrapper", env)
            code, out, err = run_script(script, env, wrapper)
            self.assert_stops(code, out, err, "release-dry-run: could not resolve HEAD to a commit", False)
            calls = git_log(wrapper)
            self.assertEqual(len(calls), 2, f"the script made other git calls than the 2 HEAD reads: {calls}")
            self.assertTrue(calls[0].startswith("-C ") and calls[0].endswith(" symbolic-ref -q HEAD"), calls)
            self.assertTrue(calls[1].startswith("-C ") and calls[1].endswith(" rev-parse --verify -q HEAD"), calls)
            self.assertEqual(git_starts(tmp / "trace2"), calls,
                             "git's trace2 log records other runs of git than the 2 HEAD reads")
            self.assert_ends_at(wrapper, nth_call("rev-parse", 1))

    def test_a_branch_read_with_another_failing_status_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, "symbolic-ref", status=2)
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assert_stops(code, out, err,
                              f"release-dry-run: could not read the branch HEAD names in {fixture.main} "
                              "(git symbolic-ref exit 2)", False)
            self.assert_ends_at(wrapper, nth_call("symbolic-ref", 1))

    def test_a_tag_and_note_listing_that_git_refuses_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, "refs/tags")
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assertIn("wrapper: refused refs/tags", err)
            self.assert_stops(code, out, err, "release-dry-run: could not list the tags and notes", False)
            self.assert_ends_at(wrapper, nth_call("refs/tags", 1))

    def test_a_tag_and_note_listing_that_git_refuses_in_step_6_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, "refs/tags", after=1)
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assertIn("wrapper: refused refs/tags", err)
            self.assert_stops(code, out, err, "release-dry-run: could not list the tags and notes", True)
            self.assertEqual(sum("refs/tags" in call.split() for call in git_log(wrapper)), 2,
                             "the tag and note listing was not read exactly twice")
            self.assert_ends_at(wrapper, nth_call("refs/tags", 2))

    def test_a_leak_check_that_git_refuses_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, "--contains")
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assertIn("wrapper: refused --contains", err)
            self.assert_stops(code, out, err, "release-dry-run: could not list the refs", True)
            self.assert_ends_at(wrapper, nth_call("--contains", 1))

    def test_a_git_call_of_the_dry_run_commit_that_fails_fails(self):
        # (the argument refused, the number of such calls let through first, the message that must end
        # the run): each git call that makes or reads the dry-run commit fails the run with exit 1.
        for refused, after, message in (
                ("-u", 0, "release-dry-run: could not stage the dry-run version bump"),
                ("write-tree", 0, "release-dry-run: could not write the tree of the dry-run commit"),
                ("--verify", 1, "release-dry-run: could not read the HEAD of the dry run's worktree before its commit"),
                ("commit-tree", 0, "release-dry-run: could not make the dry-run commit"),
                ("update-ref", 0, "release-dry-run: could not move the HEAD of the dry run's worktree from "),
                ("--verify", 2, "release-dry-run: could not read the HEAD of the dry run's worktree after its commit"),
        ):
            with self.subTest(refused=refused, after=after), tempfile.TemporaryDirectory() as name:
                fixture = Fixture(Path(name))
                wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, refused, after=after)
                code, out, err = run_script(fixture.script, fixture.env, wrapper)
                self.assertIn(f"wrapper: refused {refused}", err)
                self.assert_stops(code, out, err, message, True)
                self.assert_ends_at(wrapper, nth_call(refused, after + 1))

    def test_no_tag_and_no_note_passes(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            fixture.git("tag", "-d", "v1.0.0", "v0.9.0")
            self.assertEqual(fixture.git("for-each-ref", "refs/tags", "refs/notes"), "")
            code, out, err = run_script(fixture.script, fixture.env)
            self.assertEqual((code, SUCCESS in out), (0, True), err)

    def test_a_git_call_of_the_filter_settings_that_fails_fails(self):
        # (the argument refused, the number of such calls let through first, the exit status of the
        # refusal, the message that must end the run, whether the run reaches the version line): each git
        # call that lists the filter drivers, finds the info/attributes file, names the empty tree or reads
        # the filter drivers that the attributes of the dry-run commit name, git ls-tree and the second git
        # check-attr, fails the run with exit 1. The first git check-attr asks git to refuse a
        # GIT_ATTR_SOURCE that names no tree; a refusal of it with the wrapper's message, at exit 128 or at
        # another exit status, is not git's refusal of such a source, so it fails the run too. The calls of
        # the pipeline that reads the drivers of the dry-run commit, git ls-tree and the second git
        # check-attr, are each the other's partner, which may run on once the other is refused.
        drivers = "release-dry-run: could not read the filter drivers that the attributes of the dry-run commit "
        source = ("release-dry-run: git did not refuse a GIT_ATTR_SOURCE that names no tree as it refuses such "
                  "a source")
        for refused, after, status, message, reached_version, partners in (
                ("--get-regexp", 0, 128, "release-dry-run: could not list the filter drivers of ", False, ()),
                ("--git-path", 0, 128, "release-dry-run: could not find the info/attributes file of ", False, ()),
                ("hash-object", 0, 128, "release-dry-run: could not name the empty tree of ", False, ()),
                ("check-attr", 0, 128, f"{source}, so the dry run cannot show that git reads that variable "
                                       "(git check-attr exit 128)", False, ()),
                ("check-attr", 0, 1, f"{source}, so the dry run cannot show that git reads that variable "
                                     "(git check-attr exit 1)", False, ()),
                ("ls-tree", 0, 128, drivers, True, (" check-attr --source ",)),
                ("check-attr", 1, 128, drivers, True, (" ls-tree -r --name-only ",)),
        ):
            with self.subTest(refused=refused, after=after, status=status), \
                    tempfile.TemporaryDirectory() as name:
                fixture = Fixture(Path(name))
                wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env, refused, status=status, after=after)
                code, out, err = run_script(fixture.script, fixture.env, wrapper)
                self.assertIn(f"wrapper: refused {refused}", err)
                self.assert_stops(code, out, err, message, reached_version)
                self.assert_ends_at(wrapper, nth_call(refused, after + 1), partners)
                self.assertEqual(temporary_files(fixture.tmp), [],
                                 "the run left the file of its check of GIT_ATTR_SOURCE, or its worktree, in TMPDIR")
        # (the exit status, the standard error of the first git check-attr, byte for byte, the text of it
        # that the run must print, as cat -v shows it): git's own message for the refusal of a
        # GIT_ATTR_SOURCE that names no tree, at another exit status than 128, or at 128 with another line
        # after it or before it, with a blank line after it or before it, without the newline that ends
        # it, with a NUL byte after it, before it, inside it or before its newline, or with a carriage
        # return or a space before its newline, is not that refusal either. A command substitution drops
        # every NUL byte, so only a comparison of the bytes themselves fails the 4 NUL outcomes.
        refusal = b"fatal: bad --attr-source or GIT_ATTR_SOURCE"
        shown = refusal.decode("ascii")
        for status, stderr, printed in (
                (1, refusal + b"\n", shown), (128, refusal + b"\nerror: and another reason\n",
                                              f"{shown}\nerror: and another reason"),
                (128, b"error: an earlier reason\n" + refusal + b"\n", f"error: an earlier reason\n{shown}"),
                (128, refusal + b"\n\n", shown), (128, b"\n" + refusal + b"\n", shown), (128, refusal, shown),
                (128, refusal + b"\n\0", f"{shown}\n^@"), (128, b"\0" + refusal + b"\n", f"^@{shown}"),
                (128, b"fatal: bad\0 --attr-source or GIT_ATTR_SOURCE\n",
                 "fatal: bad^@ --attr-source or GIT_ATTR_SOURCE"),
                (128, refusal + b"\0\n", f"{shown}^@"), (128, refusal + b"\r\n", f"{shown}^M"),
                (128, refusal + b" \n", f"{shown} \n")):
            with self.subTest(status=status, stderr=stderr), tempfile.TemporaryDirectory() as name:
                fixture = Fixture(Path(name))
                wrapper = mimicking_git(fixture.tmp / "wrapper", fixture.env, status, stderr)
                code, out, err = run_script(fixture.script, fixture.env, wrapper)
                self.assertIn(printed, err)
                self.assert_stops(code, out, err, f"{source}, so the dry run cannot show that git reads that "
                                  f"variable (git check-attr exit {status})", False)
                self.assert_ends_at(wrapper, attribute_source_check)
                self.assertEqual(temporary_files(fixture.tmp), [],
                                 "the run left the file of its check of GIT_ATTR_SOURCE in TMPDIR")

    def test_the_attribute_source_check_runs_in_the_c_locale(self):
        # The caller's environment names a locale other than C, in which a git with a translation of its
        # messages would translate its refusal; the check must still run with LC_ALL set to C, and the
        # run must pass.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            env = {key: value for key, value in fixture.env.items() if key != "LC_ALL"}
            env.update(LANG="C.UTF-8", LANGUAGE="fr")
            log = fixture.tmp / "locales"
            entries = fixture.tmp / "entries"
            wrapper = locale_recording_git(fixture.tmp / "wrapper", env, log, entries)
            code, out, err = run_script(fixture.script, env, wrapper)
            self.assertEqual((code, SUCCESS in out), (0, True), f"exit {code}\n{out}{err}")
            self.assertEqual(log.read_text(encoding="utf-8").splitlines() if log.exists() else [], ["C"],
                             "the check of GIT_ATTR_SOURCE did not run once with LC_ALL set to C")
            self.assertEqual(entries.read_text(encoding="utf-8").splitlines() if entries.exists() else [], ["show"],
                             "the file of the check of GIT_ATTR_SOURCE was still in TMPDIR when the script read the "
                             "version, or the script did not read it once")
            self.assertEqual(temporary_files(fixture.tmp), [],
                             "the run left the file of its check of GIT_ATTR_SOURCE, or its worktree, in TMPDIR")

    def test_an_info_attributes_file_that_cannot_be_read_fails(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            (fixture.main / ".git" / "info" / "attributes").mkdir()
            wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env)
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assert_stops(code, out, err,
                              "release-dry-run: could not read the filter drivers that .git/info/attributes names",
                              False)
            self.assert_ends_at(wrapper, lambda event: event.startswith("python3 ")
                                and event.endswith(" .git/info/attributes"))

    def test_a_git_that_ignores_the_attribute_source_fails(self):
        # A git wrapper, first on PATH, removes GIT_ATTR_SOURCE from the environment of every call, as a
        # git that does not read it would ignore it.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            wrapper = ignoring_git(fixture.tmp / "ignoring", fixture.env)
            code, out, err = run_script(fixture.script, fixture.env, wrapper)
            self.assert_stops(code, out, err, "release-dry-run: git ignores GIT_ATTR_SOURCE", False)
            self.assert_ends_at(wrapper, attribute_source_check)
            self.assertEqual(temporary_files(fixture.tmp), [],
                             "the run left the file of its check of GIT_ATTR_SOURCE in TMPDIR")

    def test_a_tool_of_the_attribute_source_check_that_fails_fails(self):
        # (the tool that a stand-in, first on PATH, replaces, the stand-in's commands, the message that must
        # end the run, whether the check's git call runs, whether the run must leave no entry that mktemp
        # names in TMPDIR): a mktemp that fails; a mktemp that names a file in a folder that does not
        # exist, so that the redirection of standard error to it fails, git does not run and cmp cannot
        # read the file; a cmp that cannot compare, which exits 2; and an rm that cannot remove the file
        # each fail the run with exit 1 and the script's message, before its read of the version. The rm
        # stand-in removes nothing, so that run leaves the file.
        compare = ("release-dry-run: could not compare the standard error of the check of GIT_ATTR_SOURCE with "
                   "git's message (cmp exit 2)")
        for tool, commands, message, checked, clean in (
                ("mktemp", "exit 1\n", "release-dry-run: could not make a temporary file for the standard error of "
                 "the check of GIT_ATTR_SOURCE", False, True),
                ("mktemp", "printf '%s\\n' \"${TMPDIR}/missing/stderr\"\n", compare, False, True),
                ("cmp", "cat > /dev/null\nexit 2\n", compare, True, True),
                ("rm", "exit 1\n", "release-dry-run: could not remove the temporary file ", True, False)):
            with self.subTest(tool=tool, commands=commands), tempfile.TemporaryDirectory() as name:
                fixture = Fixture(Path(name))
                wrapper = refusing_git(fixture.tmp / "wrapper", fixture.env)
                (wrapper / tool).write_text("#!/bin/sh\n" + commands, encoding="utf-8")
                (wrapper / tool).chmod(0o755)
                code, out, err = run_script(fixture.script, fixture.env, wrapper)
                self.assert_stops(code, out, err, message, False)
                self.assertEqual(any(attribute_source_check(event) for event in events(wrapper)), checked,
                                 f"the check's git call {'did not run' if checked else 'ran'}: {events(wrapper)}")
                self.assert_ends_at(wrapper, attribute_source_check if checked else nth_call("hash-object", 1))
                if clean:
                    self.assertEqual(temporary_files(fixture.tmp), [],
                                     "the run left the file of its check of GIT_ATTR_SOURCE in TMPDIR")


class SignalCases(unittest.TestCase):
    def test_a_signal_during_the_attribute_source_check_leaves_no_file(self):
        # HUP, INT and TERM, each sent to the process group of the run while the check of GIT_ATTR_SOURCE
        # runs, as a hang-up, an interrupt typed at a terminal or a kill of the job sends it, end the run
        # once the file in which the check writes standard error exists. The run must stop before its read
        # of the version and leave no entry that mktemp names in TMPDIR.
        for name_of_signal in ("HUP", "INT", "TERM"):
            with self.subTest(signal=name_of_signal), tempfile.TemporaryDirectory() as name:
                fixture = Fixture(Path(name))
                entries = fixture.tmp / "entries"
                wrapper = signalling_git(fixture.tmp / "wrapper", fixture.env, name_of_signal, entries)
                code, out, err = run_script(fixture.script, fixture.env, wrapper)
                during = entries.read_text(encoding="utf-8").splitlines() if entries.exists() else []
                self.assertEqual(len(during), 1, f"TMPDIR did not hold 1 entry that mktemp names, the file of the "
                                 f"check, while the check ran: {during}")
                self.assertNotEqual(code, 0, f"the run did not end with a failure\n{out}{err}")
                self.assertNotIn(SUCCESS, out)
                self.assertNotIn(VERSION_LINE, out, f"the run went on past the check\n{out}{err}")
                self.assertEqual(temporary_files(fixture.tmp), [],
                                 f"the run left the file of its check of GIT_ATTR_SOURCE in TMPDIR after "
                                 f"{name_of_signal} (exit {code})")


class HeldCommitCases(unittest.TestCase):
    def test_a_tag_or_note_that_already_holds_the_dry_run_commit_fails(self):
        # The dry-run commit is the same object in each run at the same HEAD, since its parent, tree,
        # identity, dates and message are, so a ref can hold it from an earlier run. After a first run,
        # which must pass, a lightweight tag and an annotated tag at that commit, a tag at a child of it,
        # and 2 notes refs, 1 at that commit and 1 at that child, hold it before the second run starts,
        # and nothing moves them. The 2 snapshots then agree, and the second run must fail on the leak
        # check alone, naming exactly those refs, so a leak check that leaves out tags, or notes, fails
        # this case although no ref case reaches the leak check with such a ref.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            code, out, err = run_script(fixture.script, fixture.env)
            self.assertEqual((code, SUCCESS in out), (0, True), f"the first run: exit {code}\n{out}{err}")
            commits = [line.split() for line in fixture.git("cat-file", "--batch-all-objects",
                                                            "--batch-check=%(objecttype) %(objectname)").splitlines()]
            subjects = fixture.git("log", "--no-walk=unsorted", "--format=%H %s",
                                   *[object_name for kind, object_name in commits if kind == "commit"]).splitlines()
            dry = [line.split()[0] for line in subjects if line.split(" ", 1)[1] == "Dry run: version 1.0.1"]
            self.assertEqual(len(dry), 1, f"the first run did not leave exactly 1 dry-run commit: {subjects}")
            dry = dry[0]
            child = fixture.git("commit-tree", "-p", dry, "-m", "Descendant", f"{dry}^{{tree}}").strip()
            fixture.git("tag", "held-light", dry)
            fixture.git("tag", "-a", "-m", "Held", "held-annotated", dry)
            fixture.git("tag", "held-child", child)
            fixture.git("update-ref", "refs/notes/held", dry)
            fixture.git("update-ref", "refs/notes/held-child", child)
            before, listing = fixture.snapshot(), fixture.git("for-each-ref")
            code, out, err = run_script(fixture.script, fixture.env)
            self.assertEqual(fixture.snapshot(), before, "the 2 snapshots differ, so the case does not reach the "
                                                         "leak check with its refs unchanged")
            self.assertEqual(fixture.git("for-each-ref"), listing, "the whole-repository listing changed")
            self.assertEqual((code, SUCCESS in out), (1, False), f"exit {code}\n{out}{err}")
            self.assertNotIn("before:\n", err, "the run failed on the snapshot comparison")
            self.assertNotIn(SNAPSHOT_MESSAGE, err, "the run failed on the snapshot comparison")
            self.assertTrue(err.endswith(f"{LEAK_MESSAGE}; these refs contain its commit {dry}:\nrefs/notes/held\n"
                                         "refs/notes/held-child\nrefs/tags/held-annotated\nrefs/tags/held-child\n"
                                         "refs/tags/held-light\n"),
                            f"the leak check did not name exactly the tags and notes that hold the commit\n{err}")


def signing(env: dict, program: Path) -> dict:
    """env with commit signing turned on and gpg.program set to program, as GIT_CONFIG_COUNT
    entries."""
    env = dict(env)
    count = int(env["GIT_CONFIG_COUNT"])
    keys = [env[f"GIT_CONFIG_KEY_{index}"] for index in range(count)]
    env[f"GIT_CONFIG_VALUE_{keys.index('commit.gpgSign')}"] = "true"
    env[f"GIT_CONFIG_KEY_{count}"] = "gpg.program"
    env[f"GIT_CONFIG_VALUE_{count}"] = str(program)
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    return env


class SigningCases(unittest.TestCase):
    def test_signing_turned_on_in_the_configuration_passes(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            called = fixture.tmp / "signed"
            program = fixture.tmp / "gpg"
            program.write_text(f"#!/bin/sh\n: > {shlex.quote(str(called))}\nexit 1\n", encoding="utf-8")
            program.chmod(0o755)
            env = signing(fixture.env, program)
            (fixture.tmp / "probe").mkdir()
            self.assertEqual(run_bounded(["git", "init", "-q"], env, fixture.tmp / "probe")[0], 0)
            code, _, err = run_bounded(["git", "commit", "-q", "--allow-empty", "-m", "Probe"], env,
                                       fixture.tmp / "probe")
            self.assertTrue(code != 0 and called.exists(),
                            f"the configuration does not make git sign a commit: exit {code}\n{err}")
            called.unlink()
            code, out, err = run_script(fixture.script, env)
            self.assertEqual((code, SUCCESS in out), (0, True), f"exit {code}\n{out}{err}")
            self.assertFalse(called.exists(), "the dry run asked git to sign a commit")


# 8 hooks that git runs around a commit, a checkout, an index write or a ref update, each written to
# the hook folder of the hook case: each records its name in the log of that case. The commit-msg
# hook also adds a trailer to the message, and the post-commit hook keeps the commit just made in
# refs/keep/hooked and moves HEAD to the commit of the same tree and parent with the dry run's
# message, made with git commit-tree, as a hook that hides the commit made from the leak check would.
HOOK_NAMES = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit", "post-checkout",
              "reference-transaction", "post-index-change", "pre-auto-gc")
HOOK_ACTIONS = {
    "commit-msg": "printf '\\nHooked: yes\\n' >> \"$1\"\n",
    "post-commit": ('kept="$(git rev-parse --verify HEAD)"\n'
                    'named="$(git commit-tree -p HEAD^ -m "Dry run: version 1.0.1" "HEAD^{tree}")"\n'
                    'git update-ref refs/keep/hooked "${kept}"\n'
                    'git update-ref --no-deref HEAD "${named}"\n'),
    "reference-transaction": "cat > /dev/null\n",
}
# The hooks that the probe of the hook case must see run: a git commit and a git worktree add run
# these under the case's configuration.
PROBED_HOOKS = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit", "post-checkout",
                "reference-transaction")


class HookCases(unittest.TestCase):
    def test_no_hook_of_the_repository_runs(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            folder = fixture.tmp / "git-hooks"
            folder.mkdir()
            log = fixture.tmp / "hooks-ran"
            for hook in HOOK_NAMES:
                (folder / hook).write_text(f"#!/bin/sh\nprintf '%s\\n' {hook} >> {shlex.quote(str(log))}\n"
                                           + HOOK_ACTIONS.get(hook, ""), encoding="utf-8")
                (folder / hook).chmod(0o755)
            env = dict(fixture.env)
            keys = [env[f"GIT_CONFIG_KEY_{index}"] for index in range(int(env["GIT_CONFIG_COUNT"]))]
            env[f"GIT_CONFIG_VALUE_{keys.index('core.hooksPath')}"] = str(folder)
            probe = fixture.tmp / "probe"
            probe.mkdir()
            for args in (["git", "init", "-q"], ["git", "commit", "-q", "--allow-empty", "-m", "Probe"],
                         ["git", "worktree", "add", "-q", "--detach", str(fixture.tmp / "probe-worktree")]):
                code, _, err = run_bounded(args, env, probe)
                self.assertEqual(code, 0, f"the probe's {' '.join(args)} exited {code}: {err}")
            ran = set(log.read_text(encoding="utf-8").split())
            self.assertEqual(sorted(set(PROBED_HOOKS) - ran), [],
                             "the configuration does not make git run each of these hooks")
            log.unlink()
            listing = fixture.git("for-each-ref")
            code, out, err = run_script(fixture.script, env)
            self.assertEqual((code, SUCCESS in out), (0, True), f"exit {code}\n{out}{err}")
            kept = ""
            if fixture.git("for-each-ref", "refs/keep/hooked"):
                kept = fixture.git("log", "-1", "--format=%H %s%n%b", "refs/keep/hooked")
            self.assertEqual(RefComparisonCases.differing(listing, fixture.git("for-each-ref")), (),
                             f"a hook changed the whole-repository listing while the run passed; refs/keep/hooked "
                             f"holds {kept!r}")
            self.assertFalse(log.exists(), "these hooks ran during the dry run: "
                             + (log.read_text(encoding="utf-8").replace("\n", " ") if log.exists() else ""))


def configured(env: dict, settings: dict) -> dict:
    """env with settings added as GIT_CONFIG_COUNT entries."""
    env = dict(env)
    count = int(env["GIT_CONFIG_COUNT"])
    for key, value in settings.items():
        env[f"GIT_CONFIG_KEY_{count}"] = key
        env[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    env["GIT_CONFIG_COUNT"] = str(count)
    return env


def recorder(path: Path, name: str, log: Path, body: str = "cat\n") -> str:
    """Write a program at path that appends name to log each time it runs, then runs body."""
    path.write_text(f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(log))}\n" + body,
                    encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def worktree_only(fixture: "Fixture", repository: Path, settings: dict) -> None:
    """Give the configuration of repository a conditional include, for every git folder under
    worktrees/, of a new file that holds settings, so git reads them only in a linked worktree of
    repository, and a listing read from its main worktree does not see them."""
    path = repository.parent / f"{repository.name}-worktree-only.config"
    for key, value in settings.items():
        fixture.git("config", "-f", str(path), key, value)
    fixture.git("-C", str(repository), "config", "includeIf.gitdir:**/worktrees/**.path", str(path))


def run_on_terminal(args: list, env: dict, cwd: Path, timeout: float = TIMEOUT):
    """Run args as run_bounded does, but with standard output on a new pseudo-terminal, and return (exit
    code, what it wrote there, stderr)."""
    master, slave = os.openpty()
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=slave, stderr=subprocess.PIPE, env=env, cwd=cwd,
                            start_new_session=True)
    os.close(slave)
    chunks = []

    def drain():
        while True:
            try:
                data = os.read(master, 4096)
            except OSError:
                return
            if not data:
                return
            chunks.append(data)
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        err = proc.communicate(timeout=timeout)[1]
    except subprocess.TimeoutExpired:
        kill_group(proc.pid)
        proc.communicate(timeout=REAP_TIMEOUT)
        raise AssertionError(f"{args[0]} ran longer than {timeout} seconds and was killed")
    finally:
        kill_group(proc.pid)
        try:
            proc.wait(timeout=REAP_TIMEOUT)
        finally:
            reader.join(timeout=REAP_TIMEOUT)
            os.close(master)
            if proc.stderr is not None:
                proc.stderr.close()
    return proc.returncode, b"".join(chunks).decode("utf-8", "replace"), err.decode("utf-8", "replace")


# The git subcommands that the script runs, each of which a pager.<command> setting can name.
SUBCOMMANDS = ("symbolic-ref", "rev-parse", "for-each-ref", "config", "hash-object", "check-attr", "show", "worktree",
               "add", "write-tree", "commit-tree", "update-ref", "ls-tree")


class ConfiguredProgramCases(unittest.TestCase):
    """Each case configures programs that git runs from its configuration or from attributes, each of
    which records its name when it runs, first checks, in a repository of its own, that git then runs
    them, and requires the dry run to run none of them."""

    def ran(self, log: Path) -> str:
        return log.read_text(encoding="utf-8").replace("\n", " ") if log.exists() else ""

    def assert_none_ran(self, fixture: Fixture, env: dict, log: Path, on_terminal: bool = False) -> None:
        listing = fixture.git("for-each-ref")
        if on_terminal:
            code, out, err = run_on_terminal(["bash", "--noprofile", "--norc", str(fixture.script)], env, fixture.main)
        else:
            code, out, err = run_script(fixture.script, env)
        self.assertEqual((code, SUCCESS in out.replace("\r\n", "\n")), (0, True), f"exit {code}\n{out}{err}")
        self.assertEqual(RefComparisonCases.differing(listing, fixture.git("for-each-ref")), (),
                         "the whole-repository listing changed while the run passed")
        self.assertFalse(log.exists(), "these programs ran during the dry run: " + self.ran(log))

    def probe(self, fixture: Fixture, env: dict, log: Path, commands: list, wanted: set, on_terminal: bool = False,
              attributes: str = "") -> None:
        """Run commands in a new repository under env, and require them to run each program in wanted."""
        probe = fixture.tmp / "probe"
        probe.mkdir()
        self.assertEqual(run_bounded(["git", "init", "-q"], env, probe)[0], 0)
        if attributes:
            (probe / ".git" / "info").mkdir(exist_ok=True)
            (probe / ".git" / "info" / "attributes").write_text(attributes, encoding="utf-8")
        (probe / "file").write_text("probe\n", encoding="utf-8")
        for args in commands:
            if on_terminal:
                code, _, err = run_on_terminal(args, env, probe)
            else:
                code, _, err = run_bounded(args, env, probe)
            self.assertEqual(code, 0, f"the probe's {' '.join(args)} exited {code}: {err}")
        ran = set(log.read_text(encoding="utf-8").split()) if log.exists() else set()
        self.assertEqual(sorted(wanted - ran), [], "the configuration does not make git run each of these programs")
        log.unlink()

    def test_no_fsmonitor_program_runs(self):
        # On its third run in a linked worktree, which git add -u starts in the dry run's worktree, the
        # core.fsmonitor program also moves the HEAD of that worktree to a new child of it, once, as a
        # program that changes the parent of the dry-run commit would.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            moved = fixture.tmp / "moved"
            count = shlex.quote(str(fixture.tmp / "count"))
            body = ('case "$(git -c core.fsmonitor=false rev-parse --git-dir)" in\n'
                    '  */worktrees/*)\n'
                    f'    printf x >> {count}\n'
                    f'    if [ ! -e {shlex.quote(str(moved))} ] && [ "$(wc -c < {count})" -ge 3 ]; then\n'
                    '      child="$(git -c core.fsmonitor=false -c core.hooksPath=/dev/null commit-tree -p HEAD '
                    "-m Moved 'HEAD^{tree}')\"\n"
                    '      git -c core.fsmonitor=false -c core.hooksPath=/dev/null update-ref --no-deref HEAD '
                    '"${child}"\n'
                    f'      printf \'%s\\n\' "${{child}}" > {shlex.quote(str(moved))}\n'
                    '    fi ;;\n'
                    'esac\nexit 1\n')
            env = configured(fixture.env, {"core.fsmonitor": recorder(fixture.tmp / "fsmonitor", "fsmonitor", log,
                                                                       body)})
            self.probe(fixture, env, log, [["git", "add", "file"], ["git", "status", "--porcelain"]], {"fsmonitor"})
            self.assert_none_ran(fixture, env, log)
            self.assertFalse(moved.exists(), "the core.fsmonitor program moved the HEAD of the dry run's worktree")

    def test_no_clean_or_smudge_filter_runs(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            attributes = "* filter=probe\n"
            (fixture.main / ".git" / "info" / "attributes").write_text(attributes, encoding="utf-8")
            env = configured(fixture.env, {
                "filter.probe.clean": recorder(fixture.tmp / "clean", "clean", log),
                "filter.probe.smudge": recorder(fixture.tmp / "smudge", "smudge", log),
                "filter.probe.required": "true"})
            self.probe(fixture, env, log, [["git", "add", "file"], ["git", "commit", "-q", "-m", "Probe"],
                                           ["git", "worktree", "add", "-q", "--detach",
                                            str(fixture.tmp / "probe-worktree")]],
                       {"clean", "smudge"}, attributes=attributes)
            self.assert_none_ran(fixture, env, log)

    def test_no_process_filter_runs(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            attributes = "* filter=probe\n"
            (fixture.main / ".git" / "info" / "attributes").write_text(attributes, encoding="utf-8")
            env = configured(fixture.env, {"filter.probe.process": recorder(fixture.tmp / "process", "process", log,
                                                                             "exit 1\n")})
            probe_env = configured(env, {"filter.probe.required": "false"})
            probe = fixture.tmp / "probe"
            probe.mkdir()
            self.assertEqual(run_bounded(["git", "init", "-q"], probe_env, probe)[0], 0)
            (probe / ".git" / "info" / "attributes").write_text(attributes, encoding="utf-8")
            (probe / "file").write_text("probe\n", encoding="utf-8")
            run_bounded(["git", "add", "file"], probe_env, probe)
            self.assertIn("process", self.ran(log), "the configuration does not make git run the process filter")
            log.unlink()
            self.assert_none_ran(fixture, env, log)

    def test_no_pager_runs_on_a_terminal(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            pager = recorder(fixture.tmp / "pager", "pager", log)
            env = configured(fixture.env, {f"pager.{command}": pager for command in SUBCOMMANDS})
            self.probe(fixture, env, log, [["git", "add", "file"]], {"pager"}, on_terminal=True)
            self.assert_none_ran(fixture, env, log, on_terminal=True)

    def test_no_textconv_or_diff_driver_runs(self):
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            (fixture.main / ".git" / "info" / "attributes").write_text("* diff=probe\n", encoding="utf-8")
            env = configured(fixture.env, {
                "diff.probe.textconv": recorder(fixture.tmp / "textconv", "textconv", log, 'cat "$1"\n'),
                "diff.probe.command": recorder(fixture.tmp / "command", "command", log, ":\n"),
                "diff.external": recorder(fixture.tmp / "external", "external", log, ":\n")})
            # In the probe, file has the diff driver and other has none, so other's diff runs diff.external.
            probe = fixture.tmp / "probe"
            probe.mkdir()
            self.assertEqual(run_bounded(["git", "init", "-q"], env, probe)[0], 0)
            (probe / ".git" / "info" / "attributes").write_text("file diff=probe\n", encoding="utf-8")
            for path in ("file", "other"):
                (probe / path).write_text("probe\n", encoding="utf-8")
            for args in (["git", "add", "-A"], ["git", "commit", "-q", "-m", "Probe"],
                         ["git", "show", "--textconv", "HEAD:file"]):
                self.assertEqual(run_bounded(args, env, probe)[0], 0, f"the probe's {' '.join(args)} failed")
            for path in ("file", "other"):
                (probe / path).write_text("changed\n", encoding="utf-8")
            self.assertEqual(run_bounded(["git", "diff", "--ext-diff", "HEAD"], env, probe)[0], 0)
            ran = set(self.ran(log).split())
            self.assertEqual(sorted({"textconv", "command", "external"} - ran), [],
                             "the configuration does not make git run each of these programs")
            log.unlink()
            self.assert_none_ran(fixture, env, log)

    def test_no_editor_runs(self):
        # An editor that core.editor names, which git commit runs for a message it is not given, and one
        # that sequence.editor names, which git rebase -i runs for its list of commits.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            env = configured(fixture.env, {
                "core.editor": recorder(fixture.tmp / "editor", "editor", log, "printf 'Probe\\n' > \"$1\"\n"),
                "sequence.editor": recorder(fixture.tmp / "sequence-editor", "sequence-editor", log, ":\n")})
            self.probe(fixture, env, log, [["git", "commit", "-q", "--allow-empty"],
                                           ["git", "rebase", "-q", "-i", "HEAD"]], {"editor", "sequence-editor"})
            self.assert_none_ran(fixture, env, log)

    def test_no_lazy_fetch_runs(self):
        # A partial clone of the fixture made without blobs: the dry run must fail closed at its first read
        # of a missing blob, without fetching it from the promisor remote, whose upload-pack program records
        # each run.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            fixture.git("config", "uploadpack.allowFilter", "true")
            fixture.git("config", "uploadpack.allowAnySHA1InWant", "true")
            clone = fixture.tmp / "clone"
            code, _, err = run_bounded(["git", "clone", "-q", "--no-checkout", "--filter=blob:none",
                                        "file://" + str(fixture.main), str(clone)], fixture.env, fixture.tmp)
            self.assertEqual(code, 0, f"the partial clone failed: {err}")
            fixture.git("config", "remote.origin.uploadpack",
                        recorder(fixture.tmp / "upload-pack", "upload-pack", log, 'exec git-upload-pack "$@"\n'),
                        cwd=clone)
            self.assertEqual(run_bounded(["git", "cat-file", "-p", "HEAD:file"], fixture.env, clone)[0], 0)
            self.assertIn("upload-pack", self.ran(log), "reading a missing blob does not make git fetch it")
            log.unlink()
            script = place_script(clone)
            code, out, err = run_script(script, fixture.env)
            self.assertEqual((code, SUCCESS in out), (1, False), f"exit {code}\n{out}{err}")
            self.assertTrue(last_line(err).startswith("release-dry-run: could not read a valid bare X.Y.Z Version: "
                                                      "line"), f"the run did not end at its read of the version\n{err}")
            self.assertFalse(log.exists(), "these programs ran during the dry run: " + self.ran(log))

    def test_no_filter_that_only_a_linked_worktree_defines_runs(self):
        # 3 filter drivers that only configuration read in a linked worktree defines, through a
        # conditional include, so the listing of the filter drivers from the script's worktree does not
        # see them. The repository's info/attributes gives the first to file, a .gitattributes file in
        # the tree that the dry run releases gives the second to every path under site/, and the file
        # that core.attributesFile names gives the third to every path under site-src/. The packager's
        # stand-in also runs git archive of HEAD, as tools/release-package.sh does.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            log = fixture.tmp / "programs-ran"
            drivers = ("linked-info", "linked-tree", "linked-global")
            settings = {f"filter.{driver}.{command}": recorder(fixture.tmp / f"{driver}-{command}",
                                                               f"{driver}-{command}", log)
                        for driver in drivers for command in ("clean", "smudge")}
            global_attributes = fixture.tmp / "attributes"
            global_attributes.write_text("site-src/** filter=linked-global\n", encoding="utf-8")
            env = configured(fixture.env, {"core.attributesFile": str(global_attributes)})
            info = "file filter=linked-info\n"
            tree = "site/** filter=linked-tree\n"
            # The probe: in a repository of its own, git worktree add runs the smudge command of each
            # driver, and git archive in that worktree runs that of the second although GIT_ATTR_SOURCE
            # names the empty tree.
            probe = fixture.tmp / "probe"
            probe.mkdir()
            self.assertEqual(run_bounded(["git", "init", "-q"], env, probe)[0], 0)
            for path, text in (("file", "probe\n"), ("site/page", "probe\n"), ("site-src/data", "probe\n"),
                               (".gitattributes", tree)):
                (probe / path).parent.mkdir(parents=True, exist_ok=True)
                (probe / path).write_text(text, encoding="utf-8")
            (probe / ".git" / "info" / "attributes").write_text(info, encoding="utf-8")
            worktree_only(fixture, probe, settings)
            linked = fixture.tmp / "probe-worktree"
            for args in (["git", "add", "-A"], ["git", "commit", "-q", "-m", "Probe"],
                         ["git", "worktree", "add", "-q", "--detach", str(linked)]):
                code, _, err = run_bounded(args, env, probe)
                self.assertEqual(code, 0, f"the probe's {' '.join(args)} exited {code}: {err}")
            ran = set(self.ran(log).split())
            self.assertEqual(sorted({f"{driver}-smudge" for driver in drivers} - ran), [],
                             "git worktree add does not run the smudge command of each of these drivers")
            log.unlink()
            code, _, err = run_bounded(["git", "archive", "--format=tar", "-o", os.devnull, "HEAD"],
                                       dict(env, GIT_ATTR_SOURCE=EMPTY_TREE), linked)
            self.assertEqual(code, 0, f"the probe's git archive exited {code}: {err}")
            self.assertIn("linked-tree-smudge", self.ran(log).split(),
                          "git archive does not read the attributes of the tree it archives")
            log.unlink()
            (fixture.main / ".gitattributes").write_text(tree, encoding="utf-8")
            (fixture.main / "tools" / "release-package.sh").write_text(
                '#!/bin/sh\ngit archive --format=tar HEAD > /dev/null || exit 1\n'
                'exec python3 -I "$(dirname "$0")/release-package.py" "$@"\n', encoding="utf-8")
            fixture.git("add", ".gitattributes", "tools/release-package.sh")
            fixture.git("commit", "-q", "-m", "Attributes")
            (fixture.main / ".git" / "info" / "attributes").write_text(info, encoding="utf-8")
            worktree_only(fixture, fixture.main, settings)
            self.assertEqual(run_bounded(["git", "config", "--name-only", "--get-regexp", "^filter\\."], env,
                                         fixture.main)[0], 1, "the listing from the main worktree sees a driver")
            self.assert_none_ran(fixture, env, log)

    def test_a_filter_driver_whose_name_holds_an_equals_sign_fails(self):
        # A driver named a=b, which info/attributes gives every path: git -c would read the equals sign as
        # the end of the setting's name, so the dry run cannot turn it off and must fail before it runs
        # it, whether the configuration that the listing reads defines it or only that of a linked
        # worktree does.
        for where in ("listed", "linked"):
            with self.subTest(where=where), tempfile.TemporaryDirectory() as name:
                fixture = Fixture(Path(name))
                log = fixture.tmp / "programs-ran"
                settings = {"filter.a=b.clean": recorder(fixture.tmp / "clean", "clean", log),
                            "filter.a=b.smudge": recorder(fixture.tmp / "smudge", "smudge", log)}
                env = configured(fixture.env, settings) if where == "listed" else fixture.env
                probe = fixture.tmp / "probe"
                probe.mkdir()
                self.assertEqual(run_bounded(["git", "init", "-q"], env, probe)[0], 0)
                (probe / ".git" / "info" / "attributes").write_text("* filter=a=b\n", encoding="utf-8")
                (probe / "file").write_text("probe\n", encoding="utf-8")
                if where == "linked":
                    worktree_only(fixture, probe, settings)
                for args in (["git", "add", "file"], ["git", "commit", "-q", "-m", "Probe"],
                             ["git", "worktree", "add", "-q", "--detach", str(fixture.tmp / "probe-worktree")]):
                    code, _, err = run_bounded(args, env, probe)
                    self.assertEqual(code, 0, f"the probe's {' '.join(args)} exited {code}: {err}")
                self.assertIn("smudge", self.ran(log).split(), "git does not run the smudge command of a=b")
                log.unlink()
                (fixture.main / ".git" / "info" / "attributes").write_text("* filter=a=b\n", encoding="utf-8")
                if where == "linked":
                    worktree_only(fixture, fixture.main, settings)
                code, out, err = run_script(fixture.script, env)
                self.assertEqual((code, SUCCESS in out), (1, False), f"exit {code}\n{out}{err}")
                self.assertEqual(last_line(err), "release-dry-run: could not turn off the filter driver a=b, whose "
                                                 "name holds an equals sign", err)
                self.assertNotIn(VERSION_LINE, out)
                self.assertFalse(log.exists(), "these programs ran during the dry run: " + self.ran(log))

    def test_every_git_call_runs_with_the_programs_turned_off(self):
        # git's trace2 log records, for each run of git, the settings it runs with and the programs it
        # starts. Every run of git that the script starts after the before snapshot, other than the reads
        # of step 6, must run with hooks and the core.fsmonitor program turned off and lazy fetching
        # turned off, the exit cleanup's git worktree remove included, and start no program other than
        # git, and no automatic maintenance or fetch; each such run other than the first 3, which list the
        # filter drivers, find the info/attributes file and name the empty tree before the attribute and
        # filter settings exist, and the check that git refuses a GIT_ATTR_SOURCE that names no tree, must
        # also run with GIT_ATTR_NOSYSTEM, GIT_ATTR_SOURCE set to the empty tree, core.attributesFile set
        # to the null device and both configured filter drivers turned off. The reads of the 2 snapshots
        # and the leak check must run with lazy fetching turned off and start no program.
        with tempfile.TemporaryDirectory() as name:
            fixture = Fixture(Path(name))
            trace = fixture.tmp / "trace2"
            # The configuration names a hook folder, a core.fsmonitor program and an attributes file, so a
            # run of git that does not turn them off records their values, not those of the script's
            # settings. It defines 2 filter drivers, so a script that turns off only the first fails.
            env = configured(fixture.env, {"filter.probe.clean": "false", "filter.probe.smudge": "false",
                                           "filter.probe.process": "false", "filter.second.clean": "false",
                                           "filter.second.smudge": "false", "filter.second.process": "false",
                                           "filter.second.required": "true", "gc.auto": "1",
                                           "maintenance.auto": "true",
                                           "core.fsmonitor": str(fixture.tmp / "fsmonitor"),
                                           "core.attributesFile": str(fixture.tmp / "attributes")})
            keys = [env[f"GIT_CONFIG_KEY_{index}"] for index in range(int(env["GIT_CONFIG_COUNT"]))]
            (fixture.tmp / "git-hooks").mkdir()
            env[f"GIT_CONFIG_VALUE_{keys.index('core.hooksPath')}"] = str(fixture.tmp / "git-hooks")
            env.update(GIT_TRACE2_EVENT=str(trace),
                       GIT_TRACE2_CONFIG_PARAMS="core.hooksPath,core.fsmonitor,core.attributesFile,filter.*",
                       GIT_TRACE2_ENV_VARS="GIT_NO_LAZY_FETCH,GIT_ATTR_NOSYSTEM,GIT_ATTR_SOURCE")
            code, out, err = run_script(fixture.script, env)
            self.assertEqual((code, SUCCESS in out), (0, True), f"exit {code}\n{out}{err}")
            runs = {}
            for line in trace.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                run = runs.setdefault(event["sid"], {"argv": None, "params": {}, "children": []})
                if event["event"] == "start":
                    run["argv"] = event["argv"][1:]
                elif event["event"] == "def_param":
                    run["params"][event["param"]] = event["value"]
                elif event["event"] == "child_start":
                    run["children"].append(event.get("argv"))
            off = {"core.hookspath": "/dev/null", "core.fsmonitor": "false", "filter.probe.clean": "",
                   "filter.probe.smudge": "", "filter.probe.process": "", "filter.probe.required": "false",
                   "filter.second.clean": "", "filter.second.smudge": "", "filter.second.process": "",
                   "filter.second.required": "false", "core.attributesfile": "/dev/null",
                   "GIT_ATTR_NOSYSTEM": "1", "GIT_ATTR_SOURCE": EMPTY_TREE, "GIT_NO_LAZY_FETCH": "1"}
            early = ("core.hookspath", "core.fsmonitor", "GIT_NO_LAZY_FETCH")
            reads = {"symbolic-ref", "rev-parse", "for-each-ref"}
            seen = []
            for run in runs.values():
                argv = run["argv"] or []
                if argv[:2] == ["-C", str(fixture.main)] and argv[2] in reads or "--contains" in argv:
                    self.assertEqual((run["params"].get("GIT_NO_LAZY_FETCH"), run["children"]), ("1", []),
                                     f"the read {argv} ran without lazy fetching turned off, or started a program")
                    continue
                seen.append(" ".join(argv))
                # The listing of the filter drivers, the lookup of the info/attributes file and the naming
                # of the empty tree run before the attribute and filter settings exist, and read no index
                # and pass no file content through a filter, although the configuration that they read can
                # include a file that lies in a worktree; the check that git refuses a GIT_ATTR_SOURCE that
                # names no tree sets its own.
                wanted = off
                if ("--get-regexp" in argv or "--git-path" in argv or "hash-object" in argv
                        or "check-attr" in argv and "--source" not in argv):
                    wanted = {key: off[key] for key in early}
                self.assertEqual({key: run["params"].get(key) for key in wanted}, wanted,
                                 f"git {' '.join(argv)} ran without every program turned off")
                # A program that git starts is a run of git itself, which this loop checks in turn, and
                # never automatic maintenance or a fetch, although gc.auto and maintenance.auto ask for it.
                for child in run["children"]:
                    self.assertTrue(child and child[0] == "git" and child[1:2] not in (["gc"], ["maintenance"],
                                                                                    ["fetch"]),
                                    f"git {' '.join(argv)} started {child}")
            for call in ("config --name-only --get-regexp", "rev-parse --git-path info/attributes",
                         "hash-object -t tree --stdin", "check-attr filter --", "show HEAD:", "worktree add --detach",
                         "add -u", "write-tree", "rev-parse --verify HEAD", "commit-tree -p", "update-ref --no-deref",
                         "ls-tree -r --name-only", "check-attr --source", "worktree remove --force"):
                self.assertTrue(any(call in run for run in seen), f"no run of git {call} was recorded: {seen}")


# The texts that state or repeat blocks word for word: the script's header and this test's docstring,
# which every checkout holds; the squash message as .github/squash/290.txt commits it, which every
# checkout of the branch holds; and the description and the squash message as the export of the
# branch holds them at the top of the repository, PR-BODY.md and SQUASH-MSG, which no checkout holds,
# since neither is committed.
HEADER = "the script's header"
DOCSTRING = "the test's docstring"
COMMITTED_SQUASH = REPO_ROOT / ".github" / "squash" / "290.txt"
DESCRIPTION = REPO_ROOT / "PR-BODY.md"
SQUASH_MESSAGE = REPO_ROOT / "SQUASH-MSG"
COMMITTED = ".github/squash/290.txt"
EXPORTED = {"PR-BODY.md": DESCRIPTION, "SQUASH-MSG": SQUASH_MESSAGE}
# (name, the text that states the block, first words, last words, the texts that repeat it) of each
# block that is repeated word for word. Each block is 1 whole paragraph, which starts with its first
# words and ends with its last words, in every text that holds it.
REPEATED = (
    ("the residual", HEADER, "Residual: the proof does not catch", "between the 2 snapshots.",
     (DOCSTRING, COMMITTED, "PR-BODY.md", "SQUASH-MSG")),
    ("the filter remainder", HEADER, "So no filter runs during a git call of the dry run,",
     "comes to name during the run.", (COMMITTED, "PR-BODY.md", "SQUASH-MSG")),
    ("the tools remainder", HEADER, "The git calls of the tools that the script runs", "attribute and filter settings.",
     (COMMITTED, "PR-BODY.md", "SQUASH-MSG")),
    ("the residual of the test", DOCSTRING, "Residual of the test:", "with its default ref backend.",
     (COMMITTED, "PR-BODY.md", "SQUASH-MSG")),
)


def header_text(script: str) -> str:
    """The comment lines at the top of the script, after its first line, without their comment
    marks."""
    lines = []
    for line in script.splitlines()[1:]:
        if not line.startswith("#"):
            break
        lines.append(line[2:] if line.startswith("# ") else line[1:])
    return "\n".join(lines)


def paragraphs(text: str) -> list:
    """The paragraphs of text, each a run of lines that holds no blank line, from a blank line or the
    start of text to a blank line or its end, with each run of whitespace read as 1 space."""
    found, lines = [], []
    for line in text.split("\n") + [""]:
        if line.strip():
            lines.append(line)
        elif lines:
            found.append(" ".join(" ".join(lines).split()))
            lines = []
    return found


def repeated_block(text: str, first: str, last: str):
    """The paragraph of text that holds first, each run of whitespace read as 1 space, or None when
    first occurs in text other than once, or when that paragraph does not start with first or does
    not end with last. So the block is the whole paragraph, and a word added, removed or changed
    anywhere in it, before first or after last included, changes or loses the block."""
    if " ".join(text.split()).count(first) != 1:
        return None
    for paragraph in paragraphs(text):
        if first in paragraph:
            return paragraph if paragraph.startswith(first) and paragraph.endswith(last) else None
    return None


def first_difference(block: str, other: str) -> str:
    """The first word at which 2 blocks differ, with its number, counted from 1."""
    words, others = block.split(), other.split()
    for number, (word, another) in enumerate(zip(words, others), 1):
        if word != another:
            return f"word {number}, {word!r} against {another!r}"
    return f"word {min(len(words), len(others)) + 1}, where the shorter block ends"


class RepeatedTextCases(unittest.TestCase):
    def test_each_repeated_block_is_the_same_in_every_text_that_holds_it(self):
        # Each block of REPEATED, read from the text that states it and from each text that repeats it,
        # must be there once, as 1 whole paragraph that starts with its first words and ends with its
        # last words, and be the same, word for word, in each. The script's header, this test's
        # docstring and the committed squash message are read in every checkout, CI included. The
        # description and the squash message at the top of the repository are read only where they are
        # there; a checkout that lacks either skips that text alone, in a subtest that says so, and
        # still compares every other text.
        texts = {
            HEADER: header_text(DRY_RUN.read_text(encoding="utf-8")),
            DOCSTRING: ast.get_docstring(ast.parse(Path(__file__).read_text(encoding="utf-8")), clean=False) or "",
            COMMITTED: COMMITTED_SQUASH.read_text(encoding="utf-8"),
        }
        for place, path in EXPORTED.items():
            if path.is_file():
                texts[place] = path.read_text(encoding="utf-8")
            else:
                with self.subTest(text=place):
                    self.skipTest(f"{place} is not at the top of the repository, as in a checkout, so its copies "
                                  "of the repeated blocks are not compared; every other text is")
        for name, source, first, last, copies in REPEATED:
            with self.subTest(block=name):
                stated = repeated_block(texts[source], first, last)
                self.assertIsNotNone(stated, f"{name}: {source} holds no paragraph that starts with {first!r} "
                                     f"and ends with {last!r}, or holds its first words other than once")
                for place in copies:
                    if place not in texts:
                        continue
                    block = repeated_block(texts[place], first, last)
                    self.assertIsNotNone(block, f"{name}: {place} holds no paragraph that starts with {first!r} "
                                         f"and ends with {last!r}, or holds its first words other than once")
                    self.assertEqual(block, stated, f"{name}: {place} differs from {source} at "
                                     f"{first_difference(block, stated)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
