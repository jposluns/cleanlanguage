#!/usr/bin/env python3
"""Check what tools/release-package.sh leaves in dist/ after each build.

The packager is meant to work as follows, and the cases below check it at
the builds and on the planted paths that they name. A build that passes
every check writes dist/cleanlanguage.zip, dist/cleanlanguage-<version>.zip
and a .sha256 beside each. A build that is refused at a check, or ended at
any point from its first removal on by a signal of TRAPPED_SIGNALS, each
signal whose default action ends a process and that bash can trap, must
leave no zip and no .sha256 in dist/, neither a new one nor one that an
earlier build wrote, so that a reader cannot take a stale or unverified zip
for the refused build; a removal that fails is the exception, and then the
build fails and the output it could not remove stays. Apart from its own
work folder, the packager removes an entry of dist/ only when it is a
regular file with an output name. Its only recursive removal is that of its
work folder, which it makes in dist/ with mktemp, by the path that mktemp
gave; a folder with a work-folder name that an earlier build left stays. A
build refuses with exit 1 a dist that is a symbolic link or that exists and
is not a folder at the start, a dist that is a symbolic link after it makes
dist/, and a symbolic link, folder, FIFO or other object that is not a
regular file at 1 of the 4 names it writes, since its rename into dist/
would replace that object. It moves each output from its work folder to the
folder that holds it, so a work folder moved away before the moves makes
the build fail, and a folder put at an output name after the refusal makes
the move fail. The name test takes only ASCII digits, whatever the locale.
The packager makes no claim for another process of the same user that
renames or replaces dist/ or the work folder while a build runs; cases 19
to 21 make such a change only to pin the refusal or failure that the
packager states for it.

Every build here runs in a clone that the test makes in a temporary folder
with `git clone --no-local`, never in the checkout it runs from, so a dist/
folder in the checkout is never touched. The clone carries the checkout's
HEAD; the checkout's tools/release-package.sh, tools/skill-release-date.py
and tools/skill-release-date-client.py are copied into it, so the code under
test is the checkout's, uncommitted changes included. The test runs
read-only git commands and git clone only; it sets core.autocrlf for 3
builds, 1 in each of cases 3, 16 and 18, through the GIT_CONFIG_COUNT,
GIT_CONFIG_KEY_0 and GIT_CONFIG_VALUE_0 variables of each such build's
environment, never by a git config command. Each build runs with TMPDIR set
to a folder of the temporary folder, and without the BASHOPTS, SHELLOPTS,
GLOBIGNORE, BASH_ENV and CDPATH of the test's own environment; the cases of
inherited shell options set 1 of the first 4, case 25 sets BASHOPTS, and
case 23 sets CDPATH. Each stand-in command but kill, shopt and trap is a
short sh script that the test writes into its temporary folder and puts
first on the PATH of 1 build. The script gives each path that it uses as 1
shell word, quoted by shlex.quote, and the test writes it in the encoding
of the file system, so that a path with an apostrophe, white space or a
character outside ASCII reaches it unchanged. The stand-ins kill, shopt and
trap of cases 24 and 25 are bash functions that the environment of 1 build
exports as BASH_FUNC_<name>%%, since each is a builtin of bash, which no
entry of PATH replaces; each gives the path of its log as 1 shell word,
quoted by shlex.quote. Some stand-ins record their calls in a log. The
others write no log; some of them write a file that the test or the
stand-in itself reads, such as the running count of calls of the stand-in
cmp of cases 20 and 21, a file that tells the test that a stand-in holds a
call, or the file that the stand-in mkdir of case 19 writes when it links
dist. A stand-in that records its calls writes to its log, for each call,
the number of its fields and then each field, each ended by a NUL byte, so
that a field may hold a tab or a newline. The name of the temporary folder
starts with TEMP_PREFIX, which holds a space, an apostrophe and a letter
outside ASCII, so that every case runs with such a path; a temporary folder
whose path holds a colon, which no entry of PATH can hold, ends the set-up
with an error. A build that the test starts and then signals writes its
error output to a file of the temporary folder, not to a pipe, and its
standard output is discarded, so it cannot block on a full pipe while the
test waits for its stand-in. Every build runs in a session and a process
group of its own. Once the bash of a build that the test signals has ended,
the test ends with SIGKILL any process of that process group that still
runs, so that none changes dist/ while the test reads it; and when any build
outlasts its time limit, BUILD_TIMEOUT unless case 26 gives a shorter one,
the test ends every process of that group with SIGKILL, waits at most
REAP_TIMEOUT seconds for its bash to end and at most REAP_TIMEOUT more for
its output to close, and then reports the timeout, so that none of them
changes dist/ during a later case and no wait of the case is unbounded. A
process that has left the build's process group, such as 1 that the build
starts under job control (set -m) or with setsid, is not ended; the
packager does neither. The signal of the exit trap cases of case 14 goes
to every process of the build's process group; the other signal cases
send theirs to its bash only. In such a build each signal of
TRAPPED_SIGNALS has its default action and is not blocked, since bash
cannot trap a signal that was ignored when it started, and the limit on
the size of a core file is 1 byte, so that a build that a signal ends,
when the packager does not trap it, dumps no core.

The near-miss plants are generated, not picked by hand (near_misses): from
each of the 4 output names of the version at HEAD and from the 2 output
names of SAMPLE_VERSION (1.0.0), whose version parts have 1 digit each,
every name made by deleting 1 character, inserting 1 character of ALPHABET
(a letter, a digit, a dot, a hyphen, an underscore) at any position,
replacing 1 character by 1 of ALPHABET, or changing the letter case of 1
letter, and the name in capital letters; and the 4 names that repeat an
optional group of an output name (a second version part, a second
.sha256). A name that is itself an output name is left out. Each is planted
as a regular file. So a loosening of the name test of the removal that
admits a name of this set removes a plant, and a case fails; a loosening
that admits only names outside the set, such as a name 2 edits away, is not
caught by it. Besides these, the test plants a plain file, a folder of
scripts, a folder at the output name of another version, a regular file
with a work-folder name (OTHER_PLANTS), a symbolic link with a work-folder
name to a folder outside dist/ (WORK_LINK), and 2 leftover work folders
(LEFTOVER_WORK), each holding a file at an output name. After each build
that follows a planting, each planted path must be there with its bytes
unchanged, the link must still point at the same unchanged folder, and each
leftover work folder must still hold its file. Before the refused build of
case 2 and of case 3, before the build of case 4 and of case 10 that
follows a good build, before the build of case 9 that follows a good build,
and before each build of case 11 that receives a signal during its first
removal, the test also plants the 2 outputs of an earlier build for each
version of STALE_VERSIONS: 10.20.30, a version each of whose parts holds
the 10 digits in turn, and a version each of whose parts has 20 digits, so
that a narrowing of the output test that drops a digit at any part, or
takes fewer than 20 digits in a part, keeps a stale output, and a case
fails.

In its set-up, before any case, the test builds the clone with the packager
of REFERENCE_COMMIT, adapted by REFERENCE_EDITS to the licence copies
cleanlanguage/LICENSE and cleanlanguage/NOTICE.md, which gives the
reference digest. The cases, all in that clone:

1. A good build with the checkout's packager exits 0, writes the 4 outputs,
   and gives the reference digest for both zips with matching .sha256 files;
   it keeps the planted paths. A good build with no dist/ exits 0 and writes
   the 4 outputs.
2. After a good build, a build refused before the archive is made
   (--tag v0.0.0, --release-date 2020-01-01, and the unknown argument
   --bogus) leaves no zip and no .sha256 in dist/.
3. After a good build, a build with core.autocrlf=true, refused by the check
   that compares each archived file with its git blob, leaves no zip and no
   .sha256 in dist/.
4. After a good build, a build whose move of the .sha256 files into dist/
   fails, through a stand-in mv that refuses each move of a .sha256 file,
   leaves no zip and no .sha256 in dist/, including the 2 zips it had
   already moved.
5. In a good build, a stand-in mv records each of the 4 moves into dist/:
   each is `mv -fT -- <work>/<name> <work>/../<name>`, where <work> is a
   folder of dist/ with a work-folder name, and both zips are in dist/
   before either .sha256 is moved there.
6. In a good build, a stand-in unzip records that no output name is present
   in dist/ at any of its calls, so no output reaches dist/ before the checks
   that read the staged zip.
7. A dist that is a symbolic link to a folder, a dangling symbolic link, a
   plain file or a FIFO is refused with exit 1 and the packager's message,
   and the folder it points at, the missing target, the file or the FIFO
   is unchanged.
8. A folder named dist/cleanlanguage.zip/ is refused with exit 1 and the
   packager's message, is kept with its contents, and dist/ holds no zip
   and no .sha256; a stand-in mktemp that records its calls was never
   called.
9. A symbolic link to a file outside dist/ at dist/cleanlanguage.zip and at
   dist/cleanlanguage.zip.sha256, a dangling symbolic link at the
   version-named .sha256, and a FIFO at the version-named zip are each
   refused with exit 1 and the packager's message in a build with no
   arguments. The link at dist/cleanlanguage.zip, the dangling link and
   the FIFO are also each refused after a good build, in a build whose
   stand-in mv runs each move and then fails for a .sha256 file. The
   refusal comes before any move, so these builds never call that mv; a
   build without the refusal would reach the moves, replace the object,
   and fail at the first move of a .sha256 file, so the exit trap would
   remove what replaced the object and the case would fail. In each build
   the object, and the file or missing path that a link points at, is
   unchanged, dist/ holds no zip and no .sha256, and a stand-in mktemp that
   records its calls was never called.
10. After a good build, a build whose stand-in rm fails at the
    version-named zip exits 1 with the packager's message for a failed
    removal; that zip is still there, and each other earlier output is
    gone. The removal runs in dist/ and gives rm each name as ./<name>,
    which is the argument at which the stand-in fails.
11. A build that receives SIGTERM, SIGHUP or SIGINT while a stand-in mv
    holds the move of the .sha256 files exits 143, 129 or 130, and leaves
    no zip and no .sha256 in dist/; a build that receives there any other
    signal of TRAPPED_SIGNALS exits with 128 plus the signal's number and
    leaves none either. After a good build, a build refused by --bogus
    that receives 1 of these signals while a stand-in rm holds the first
    removal in dist/ exits with 128 plus the signal's number before the
    argument check, and leaves no zip and no .sha256 in dist/, neither the
    good build's nor a stale one. That stand-in, once the test has sent
    the signal, ends the removal half done: it kills, with SIGKILL, the
    subshell in which the removal runs, and removes nothing, so only the
    exit trap, set before the first removal, can remove the rest.
12. With BASHOPTS=dotglob, BASHOPTS=nocasematch, SHELLOPTS=noglob,
    GLOBIGNORE=dist/*:*, or BASH_ENV naming a file that assigns
    GLOBIGNORE=dist/*:*, in its environment, a good build keeps the planted
    paths, and a build refused by --bogus after it, with nothing planted
    again, leaves no zip and no .sha256 in dist/. With BASHOPTS=failglob, a
    good build that starts with an empty dist/, where nothing is planted,
    writes the 4 outputs, and a build refused by --bogus after it leaves no
    zip and no .sha256 in dist/.
13. Under the first locale of WIDE_LOCALES in which a bash [0-9] takes an
    Arabic-Indic digit, a good build keeps the planted paths and 2 files
    whose names are an output name with digits outside ASCII. The case is
    skipped, with that reason, when no such locale is installed.
14. A stand-in mktemp records the work folder of a build. After a good
    build, and after a build whose stand-in mv refuses each move of a
    .sha256 file with exit 7, it is gone; the failed build exits 7 and
    leaves no zip and no .sha256 in dist/. In a build with that mv, a
    stand-in rm that fails at ./cleanlanguage.zip, in dist/, leaves that
    zip in place, and the build still exits 7 and removes its work folder;
    a stand-in rm that fails at the work folder leaves it in place, and the
    build still exits 7 with no output in dist/. In a good build, a
    stand-in rm that fails at the work folder leaves it in place, and the
    build still exits 0 with its 4 outputs. A build with that mv whose
    process group receives any signal of TRAPPED_SIGNALS while a stand-in
    rm holds the first removal of its exit trap still exits 7, leaves no
    zip and no .sha256 in dist/, and leaves no work folder. The signal
    reaches the subshell of that removal and the stand-in rm as well, so
    an exit trap that caught the signal with a handler, which those
    processes do not inherit, instead of ignoring it would let the signal
    end that removal, and the case would fail.
15. After a good build, a build refused by --bogus keeps the planted
    paths, among them the near miss Cleanlanguage.zip, and removes the
    outputs of version 11111111111.0.0.
16. A good build, a build refused by the blob check under
    core.autocrlf=true, a build whose stand-in mv refuses each move of a
    .sha256 file, and a build refused by --bogus each run under strace
    -f, which records the unlink, unlinkat, rmdir, rename, renameat and
    renameat2 calls of every process of the build, whatever program makes
    them and however it names the path, and the chdir, fchdir, clone,
    clone3, fork and vfork calls by which the test follows the current
    folder of each process; -xx gives each string in hex escapes and -y
    the path of each descriptor, so the test reads no shell text. Each
    path that a call removes or replaces, the path of an unlink, unlinkat
    or rmdir and both paths of a rename, is made absolute against the
    folder of its descriptor or the current folder of its process; a call
    that failed removes nothing, and 1 that strace shows with no result or
    with the result ?, since strace detached from its process or that
    process ended during it, counts as a removal; a chdir or fchdir of that
    kind leaves the current folder not known, so a later relative path in
    it ends the case, and a process that a clone, clone3, fork or vfork of
    that kind made starts in a folder not known; a call that strace could
    not read at the entry where its process ended removes nothing (case
    27). Just before each build
    the test records every path under the temporary folder with lstat,
    which follows no link. Each such path must lie in the temporary
    folder, below no symbolic link that was there before the build, and
    either not have existed before the build or be a regular file
    directly in dist/ with an output name; the case names any other path
    with its call and process id, and strace leads the session and
    process group of each build. A stand-in mktemp records the work
    folder: the trace of each build but the last shows the removal of the
    folder at the path that mktemp gave, and the last makes none. The case
    fails, and is never skipped, when strace is not on the PATH, writes to
    the build's error output, or records no chdir of the build into the
    clone. The test makes a path absolute by its text, so a removal
    through a symbolic link that the build itself made is read at the
    link's path. A removal on a code path that none of these 4 builds
    runs, such as 1 behind a condition that they never meet, is not
    observed, and wider build coverage, not parsing, is the remedy for it.
17. The trace of case 16 is checked against itself. A good build of a copy
    of the packager runs under that trace and must give no path that case
    16 refuses; then, for each form of ORACLE_FORMS, a good build of a copy
    with that form added at its end, unguarded, must give as refused
    exactly the paths that the form removes or replaces and no other: a
    folder planted outside the clone before the build and the file in it,
    or the planted dist/keep.txt. So the case fails when strace cannot
    trace, when the test decodes a path wrongly (each planted path holds
    the space, apostrophe and letter outside ASCII of TEMP_PREFIX), when
    it makes a relative path absolute against the wrong folder (the forms
    on dist/keep.txt, 1 of which removes it in a child that a subshell in
    dist/ forks), when the rule of case 16 lets a form pass, and when
    it refuses a path of the unchanged packager.
18. A folder with a work-folder name that holds a file, as a SIGKILL could
    leave, is kept unchanged by a good build, by a build refused by
    --bogus, by a build refused by the blob check, and by a build whose
    move of the .sha256 files fails.
19. A stand-in mkdir that, at the build's `mkdir -p dist`, first puts at
    dist a symbolic link to a folder outside the clone that holds a file
    named cleanlanguage.zip makes the build exit 1 with the message for a
    linked dist; the outside folder is unchanged, and the stand-in mktemp
    was never called.
20. A stand-in cmp that, after its last call, makes a folder holding a
    file at dist/cleanlanguage.zip makes the build fail rather than move
    the zip into that folder; the folder is unchanged, and dist/ holds no
    zip and no .sha256.
21. A stand-in cmp that, after its last call, moves the work folder out of
    dist/ makes the build fail; the moved folder still holds src/ and the
    4 staged files, so no move took place, and dist/ holds no output and
    no work folder.
22. In a good build with nothing planted, a stand-in zip records 1 call,
    which writes cleanlanguage.zip in a folder of dist/ with a work-folder
    name and runs in src/cleanlanguage/ of that folder; the build exits 0
    and writes the 4 outputs.
23. A good build started as `bash tools/release-package.sh` in the root of
    the clone, with CDPATH naming a folder outside the clone that holds
    tools/ and dist/cleanlanguage.zip, exits 0 and writes the 4 outputs in
    the dist/ of the clone; the outside folder is unchanged.
24. With a stand-in trap that records each call and passes it to the
    builtin, a good build traps each signal of TRAPPED_SIGNALS once, with
    the action exit 128 plus its number, and no other, and its exit trap
    ignores the same signals. With a stand-in kill as well that records
    each call and, at `kill -l NAME`, fails as bash does for a name that it
    does not know, for 1 of the 24 names of SIGNAL_NAMES, which the
    packager asks its shell for, at a time, and then for STKFLT, PWR, RTMIN
    and RTMAX together, a good build exits 0, writes the 4 outputs and
    keeps the planted paths; each call of the stand-in kill was
    `kill -l NAME` for a NAME of SIGNAL_NAMES, and 1 or more of them for a
    name that it does not know; and the build traps, and its exit trap
    ignores, each signal of TRAPPED_SIGNALS but that of a name that the
    stand-in does not know and, when RTMIN or RTMAX is among those names,
    the real-time range, so an unknown name makes the build drop no signal
    whose name it knows. With the 4 together and the stand-in trap, a
    build that receives SIGSYS while a stand-in mv holds the move of the
    .sha256 files exits 159 and leaves no zip and no .sha256 in dist/; each
    call of the stand-in kill was `kill -l NAME` for a NAME of
    SIGNAL_NAMES, the build asked it for SYS after 1 or more of the 4, and
    the build trapped, and its exit trap ignored, each signal of
    TRAPPED_SIGNALS but SIGSTKFLT, SIGPWR and the real-time range, SIGSYS
    among them.
25. For each glob or match option of SHELL_OPTIONS_OFF, which the packager
    turns off, with a stand-in shopt that records each call and fails as
    bash does for an option that it does not know at each call that names
    that option, with the other 4 turned on through BASHOPTS, and with the
    stand-in trap of case 24, which also records the shell options that
    BASHOPTS lists at each call, a good build exits 0, writes the 4 outputs
    and keeps the planted paths; the build asked the stand-in shopt about
    that option; and at each trap that it set, its shell options held
    dotglob and none of the 5, so an option that the shell does not know
    neither ends the build nor leaves another option turned on.
26. A build by a stand-in script, with a time limit of 1 second, that
    starts in its own process group a child that writes a file after 3
    seconds, starts under job control a process that leaves that group and
    keeps the build's output open, and then sleeps, makes the test raise
    the timeout within the limit plus twice REAP_TIMEOUT and 5 seconds,
    long before that process ends; the child never writes its file.
27. The reader of the trace of cases 16 and 17 is checked on traces that
    the test writes in the form of strace -f -qq -xx -y, with no build and
    no strace. strace writes TRACE_UNREAD, ???( with no name and no
    argument, or the name of a call and ( with no argument, whatever the
    name, for a call whose number or arguments it could not read at the
    entry where its process ended, and cuts such a call, or any other,
    short in each form of CUT_SHORT: closed by <detached ...>, or by
    <unfinished ...> with or without a later resumption with the result ?,
    or ended with the result ?, before or after the end of its process
    (+++). In each form such an unread call removes nothing, fork and vfork
    with no argument are read as the call, a removal before it or next to
    it is still reported, and a removal cut short counts, as does 1 that
    ends with the result ? and the note <unavailable>, in its line or in
    its resumption, a form that strace is not shown here to write for a
    call whose arguments it read; and renameat2 removes or replaces both
    of its paths. A relative path is read against the folder of its
    process, which a child made without CLONE_FS takes from its maker
    when it is made and 1 made with CLONE_FS shares, or against the
    folder that its descriptor names, but against the folder of its
    process for AT_FDCWD. The reader is written to end the case rather
    than guess. Its refusals are the raise statements of
    trace_string, trace_folder, trace_call, trace_records, traced_path
    and traced_removals; that code, not this docstring, is the full
    list, and a trace that fits none of the forms these functions take
    can also end the case with another error, such as an IndexError.
    For example, it ends the case when the trace holds no call, when a
    process shows a call after the call at which strace detached from
    it, when a process resumes a call that it did not start, when a
    process that the trace shows with no maker, other than its first
    process, gives a relative path, with no descriptor or with
    AT_FDCWD, in a removal whose result is 0 or ? or not given, or in a
    chdir whose result is 0, before a chdir or fchdir whose result is 0
    gives it a folder, and when any process gives a relative path, in
    such a removal, against a descriptor whose path strace -y does not
    give, gives as relative or gives as that of a removed folder. Each
    call of clone, clone3, fork or vfork whose result is ? or not given
    lets 1 later process that no call made start, in a folder that is
    not known, and a further such process ends the case; the docstring
    of test_trace_admits_1_process_with_no_maker_for_each_call_cut_short
    states which traces check this. Some refusals share the text of
    their error, so that the error alone does not show which of them
    ended the case: a resumption with no call open and 1 under another
    name; a call cut short and 1 that strace detached from while
    another call of its process is open; 3 refusals in trace_call of a
    call that the test cannot read; a line of a process after a call
    that strace detached from, 1 after an unread call left unfinished
    and 1 after an unread call that ended with the result ?; a
    relative path in a process with no maker and 1 in a folder that a
    chdir or fchdir that strace cut short left not known; and a
    process that no traced call made when no call cut short came
    before it and 1 when each such call has let 1 start. The subtests
    of test_trace_refuses_what_it_cannot_read name further examples in
    their labels.

Each case starts with no dist/ in the clone.

REFERENCE_COMMIT names the commit of the last packager that wrote dist/
before its checks, and the reference comparison in case 1 holds only while
the packager gives the same bytes as that commit's packager. An intended
change to the packager's output therefore makes case 1 fail by design.
REFERENCE_COMMIT then moves to the commit that makes the change, in the
same pull request.

The packager of REFERENCE_COMMIT predates the licence copies
cleanlanguage/LICENSE and cleanlanguage/NOTICE.md, which pull request #279
adds to the git tree. Its allowlist
refuses the 2 paths, and its expected entry list adds LICENSE and NOTICE.md
by name to the entries of the git tree, so with the copies in the tree it
would list each twice. REFERENCE_EDITS makes 2 edits to its text, each of
which must match exactly once, or the set-up ends with an error: the
allowlist admits the 2 paths, and the expected entry list drops them from
the entries of the git tree. The reference still writes the root LICENSE
and NOTICE.md into its layout, over the copies that git archive laid out
there, and the packager under test refuses a copy whose git blob differs
from its root file's. Case 1 checks that both builds zip the same bytes
for 1 tree only: the set-up builds the clone's HEAD with the adapted
reference packager, and case 1 builds it with the packager under test.
No case builds another tree with both packagers.

Usage:
  python3 -I tools/test-release-package-dist.py

Needs git, bash, zip, unzip, sha256sum and GNU coreutils, strace that may
trace the processes that it starts, without which cases 16 and 17 fail,
and the full history of the checkout, since it reads
tools/release-package.sh at REFERENCE_COMMIT.
"""

import hashlib
import os
import re
import resource
import shlex
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = ("release-package.sh", "skill-release-date.py", "skill-release-date-client.py")
REFERENCE_COMMIT = "8d6de113182691d313c7cb6bdfb01df7423d280c"
# The 2 edits that adapt the packager of REFERENCE_COMMIT to the licence
# copies, each as (text, replacement); each text must occur exactly once in
# that packager. The first admits cleanlanguage/LICENSE and
# cleanlanguage/NOTICE.md to its allowlist; the second drops them from the
# entries of the git tree in its expected entry list, to which it adds
# LICENSE and NOTICE.md by name.
REFERENCE_EDITS = (
    (b"'^cleanlanguage/(plugin\\.json|", b"'^cleanlanguage/(LICENSE|NOTICE\\.md|plugin\\.json|"),
    (b"      | grep -Fvx 'cleanlanguage/plugin.json' \\\n",
     b"      | grep -Fvx 'cleanlanguage/plugin.json' \\\n"
     b"      | grep -Fvx 'cleanlanguage/LICENSE' \\\n"
     b"      | grep -Fvx 'cleanlanguage/NOTICE.md' \\\n"),
)
KEEP = "keep.txt"
KEEP_TEXT = b"a file the packager does not write\n"
# The characters that the near misses insert or put in place of another: a
# letter, a digit, a dot, a hyphen and an underscore.
ALPHABET = "a0.-_"
# A second version for the near misses, whose parts have 1 digit each, so
# that deleting 1 character can leave a version part empty whatever the
# version at HEAD is.
SAMPLE_VERSION = "1.0.0"
# Entries of dist/ that the packager did not write and that are not near
# misses, each of which a build must keep byte for byte: a plain file, a
# folder of scripts, a folder at the output name of another version, and a
# regular file with a work-folder name.
OTHER_PLANTS = {
    KEEP: KEEP_TEXT,
    "edit-scripts/keep.py": b"print('kept')\n",
    "cleanlanguage-1.0.0.zip/keep.txt": b"a folder with an output name\n",
    ".release-package.FiLe12": b"a file with a work-folder name\n",
}
# Earlier builds' outputs for other versions, planted by plant_stale before
# the refused or later build of the cases that call it. Each version part of
# the first has 2 digits, so that a version test that takes only 1 digit in
# a part keeps them; each part of the second holds each of the 10 digits, so
# that a version test that drops a digit from a part, or takes fewer than
# 10 digits in a part, keeps them; each part of the third has 20 digits,
# so that a version test that takes fewer than 20 digits in a part keeps
# them.
STALE_VERSIONS = ("10.20.30", "0123456789.0123456789.0123456789",
                  "01234567890123456789.01234567890123456789.01234567890123456789")
# A symbolic link with a work-folder name, to a folder outside dist/ that
# holds WORK_LINK_FILE; the build must keep the link and leave the folder as
# it is.
WORK_LINK = ".release-package.LnK456"
WORK_LINK_FILE = "keep.txt"
# Leftover work folders, as a build ended by SIGKILL could leave, each
# holding a file at an output name; a build must keep each unchanged.
LEFTOVER_WORK = (".release-package.AbC123", ".release-package.zZ9999")
LEFTOVER_FILE = "cleanlanguage.zip"
LEFTOVER_TEXT = b"left by a killed build\n"
# Locales in which a bash range may take characters outside ASCII; the
# locale case uses the first of them in which [0-9] takes an Arabic-Indic
# digit, and is skipped, with that reason, when none does.
WIDE_LOCALES = ("en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8")
# Names outside ASCII that a range test of the removal takes under such a
# locale and that the packager never gives, each planted as a regular file:
# a version in Arabic-Indic digits, and a version with 1 Arabic-Indic digit.
NON_ASCII_FILES = ("cleanlanguage-%s.%s.%s.zip" % (chr(0x661), chr(0x660), chr(0x660)),
                   "cleanlanguage-1.0.%s.zip.sha256" % chr(0x663))
REFUSED_NAME = "exists and is not a regular file that the packager wrote"
REMOVAL_FAILED = ("release-package: could not remove every earlier output from dist/; "
                  "any it could not remove is still there")
LINKED_DIST = "release-package: dist is a symbolic link; the packager writes only into a real dist/ folder"
OUTPUT_NAME = re.compile(r"cleanlanguage(-[0-9]+\.[0-9]+\.[0-9]+)?\.zip(\.sha256)?")
WORK_NAME = re.compile(r"\.release-package\.[A-Za-z0-9]{6}")
# The GLOBIGNORE of the 2 cases that set it: a colon-separated list of dist/*,
# which hides every entry from a glob dist/*, and *, which hides every
# entry from the glob * that the removal, run in dist/, uses.
GLOBIGNORE_VALUE = "dist/*:*"
# Variables of the test's own environment that would change how bash globs
# and matches, which folder cd enters, or run code before the packager; no
# build inherits them.
SHELL_VARIABLES = ("BASHOPTS", "SHELLOPTS", "GLOBIGNORE", "BASH_ENV", "CDPATH")
BUILD_TIMEOUT = 300
# The longest that the test waits, once it has ended the process group of a
# build with SIGKILL, for the build's bash to end, and then for its output
# to close.
REAP_TIMEOUT = 5
# The exit code of the stand-in mv that refuses a move with a code other than 1.
MOVE_EXIT = 7
# The start of the name of the test's temporary folder. It starts with
# ASCII letters and holds a space, an apostrophe and a letter outside
# ASCII, so that every stand-in, log and build runs with such a path.
TEMP_PREFIX = "release-package-dist it's %s " % chr(0xE9)
# The signals whose default action ends a process and that bash can trap,
# from 1 to SIGRTMAX: all but SIGKILL, which no process can trap; SIGSTOP,
# SIGTSTP, SIGTTIN and SIGTTOU, which stop a process; SIGCHLD, SIGCONT,
# SIGURG and SIGWINCH, which do not end one; and the signals between SIGSYS
# and SIGRTMIN (32 and 33 with the GNU C library), for which a trap that
# bash sets does not take effect.
NOT_TRAPPED = {signal.SIGKILL, signal.SIGSTOP, signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU,
               signal.SIGCHLD, signal.SIGCONT, signal.SIGURG, signal.SIGWINCH}
TRAPPED_SIGNALS = tuple(n for n in range(1, signal.SIGRTMAX + 1)
                        if n not in NOT_TRAPPED and not signal.SIGSYS < n < signal.SIGRTMIN)
# The signals of TRAPPED_SIGNALS that cases of their own name, and the others.
NAMED_SIGNALS = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
OTHER_SIGNALS = tuple(n for n in TRAPPED_SIGNALS if n not in NAMED_SIGNALS)
# The signal names that the packager asks the kill -l of its shell for: the
# 22 names that it traps by name, then the 2 bounds of the real-time range.
SIGNAL_NAMES = ("HUP", "INT", "QUIT", "ILL", "TRAP", "ABRT", "BUS", "FPE", "USR1", "SEGV", "USR2", "PIPE",
                "ALRM", "TERM", "STKFLT", "XCPU", "XFSZ", "VTALRM", "PROF", "IO", "PWR", "SYS",
                "RTMIN", "RTMAX")
# Names that a platform other than Linux may lack together.
NON_LINUX_NAMES = ("STKFLT", "PWR", "RTMIN", "RTMAX")
# The glob and match options that the packager turns off when its shell
# knows them.
SHELL_OPTIONS_OFF = ("extglob", "failglob", "globstar", "nocaseglob", "nocasematch")
# The system calls that the trace of a build records: each that removes or
# replaces a path, each that changes the current folder of a process, and
# each that makes a process or a thread, which starts in the current folder
# of the process that made it, or shares it.
TRACED_CALLS = ("unlink", "unlinkat", "rmdir", "rename", "renameat", "renameat2",
                "chdir", "fchdir", "clone", "clone3", "fork", "vfork")
# For each traced call that removes or replaces a path, the arguments that
# give each such path, as (descriptor, path) positions; a call with no
# descriptor works from the current folder of its process.
REMOVING_CALLS = {"unlink": ((None, 0),), "rmdir": ((None, 0),), "unlinkat": ((0, 1),),
                  "rename": ((None, 0), (None, 1)), "renameat": ((0, 1), (2, 3)),
                  "renameat2": ((0, 1), (2, 3))}
FORKING_CALLS = ("clone", "clone3", "fork", "vfork")
# The traced calls that take no argument, so that strace writes their name
# and ( with no argument even when it read them.
NO_ARGUMENT_CALLS = ("fork", "vfork")
CLONE_FS = re.compile(r"\bCLONE_FS\b")
# A line of the trace that strace -f -o writes: a process id, then a call
# with its arguments and its result, a signal (---) or the end of the
# process (+++). A call that another process interrupts is split into a
# line that ends in TRACE_UNFINISHED and a later 1 that starts with
# <... name resumed>. strace cuts a call short in these forms, by its
# source (strace.c printleader, droptcb and print_event_exit; syscall.c
# syscall_entering_decode):
#   name(args <unfinished ...>     another line came first; the call may
#                                  be resumed later, or never
#   name(args <detached ...>       strace dropped the ended process with
#                                  the line still open; no later line
#   name(args) = ?                 the process ended during the call
#   name(args <unfinished ...>) = ?
#                                  the same, when the decoder of the call
#                                  had more to write at its exit
#   <... name resumed>) = ?        the same, after another line, and
#   <... name resumed> <unfinished ...>) = ?
# Each of these may be followed by the end of its process (+++), which a
# signal that ended it writes even under -qq. A call with no result or
# with the result ? may have taken effect. strace writes the name of a call
# and ( with no argument, or TRACE_UNREAD, ??? with no name, when it could
# not read the arguments or the number of the call at the entry stop of
# its process, since that process had already ended there, before the call
# ran; and it writes that text before it applies the calls that the test
# asked for, so the name may be any. Such a call ends in any form above
# with no result or with the result ? alone, and its process shows no
# later line but that result and the end of the process. fork and vfork
# take no argument, so their name and ( alone are read as the call. The
# reader also reads name(args) = ? <unavailable>, a call with its arguments,
# the result ? and that note, as a call cut short with the result ?, and so
# its resumed spelling, <... name resumed>) = ? <unavailable>. That strace
# writes this form for a call whose arguments it read is not verified here;
# the reader takes it so that such a removal, if strace writes one, counts
# (case 27).
TRACE_LINE = re.compile(r"([0-9]+) +(.*)", re.S)
TRACE_UNFINISHED = " <unfinished ...>"
TRACE_DETACHED = " <detached ...>"
TRACE_UNREAD = "???("
TRACE_NAME = re.compile(r"[a-z0-9_]+|\?\?\?")
TRACE_RESUMED = re.compile(r"<\.\.\. ([a-z0-9_]+|\?\?\?) resumed>(.*)", re.S)
TRACE_CALL = re.compile(r"([a-z0-9_]+|\?\?\?)\((.*)\) += (-?[0-9]+|\?)( .*)?", re.S)
# A string argument as strace -xx gives it, each byte as a hex escape; a
# string that strace cut short has ... after its closing quote and does not
# match. A descriptor argument as strace -y gives it: AT_FDCWD or a number,
# with the path of the descriptor in <...>; and the escapes in that path.
TRACE_STRING = re.compile(r'"((?:\\x[0-9A-Fa-f]{2})*)"')
TRACE_DESCRIPTOR = re.compile(r"(AT_FDCWD|-?[0-9]+)(?:<(.*)>)?", re.S)
TRACE_ESCAPE = re.compile(r"\\(?:x([0-9A-Fa-f]{2})|([0-7]{1,3})|(.))", re.S)
TRACE_ESCAPES = {"a": b"\a", "b": b"\b", "f": b"\f", "n": b"\n", "r": b"\r", "t": b"\t", "v": b"\v"}
# The removals that the self-check of the trace (case 17) adds, 1 at a
# time and unguarded, at the end of a copy of the packager, each with the
# paths that it removes or replaces and that the trace must report: @PLANT
# stands for a folder outside the clone, planted before the build, that
# holds the file KEEP, and dist/keep.txt is a planted file. The forms give
# rm an option in a $'...' string; split /usr/bin/rm over a continued line
# after a here-document whose body line continues onto its delimiter line;
# run rm in a command substitution in the word of a ${...}; follow an
# escaped backslash with rm on the next line; build the command name in a
# variable; remove with a Python program, with find -delete, with rm of a
# relative path in a subshell that entered dist/, once as its last command,
# which bash runs in that subshell, and once before another command, which
# bash runs in a child that it forks there, and with mv of a new file onto
# dist/keep.txt, both paths relative; split /usr/bin/rm over a
# continued line after a here-document on a line that ends inside a
# single-quoted string, after a here-document whose quoted delimiter holds
# a backslash, and after an apostrophe in backquotes, with set +e first, so
# that the error in those backquotes cannot end the build; and follow a
# here-document whose quoted delimiter holds a backslash with rm.
PLANT_PATHS = ("@PLANT", "@PLANT/" + KEEP)
KEPT_PATHS = ("dist/" + KEEP,)
ORACLE_FORMS = (
    ("/usr/bin/rm $'-r' -- @PLANT", PLANT_PATHS),
    ("cat <<E >/dev/null\nx\\\nE\nit's\nE\n/usr/bin/r\\\nm -rf -- @PLANT", PLANT_PATHS),
    (': "${unset_name:-$(/usr/bin/rm -rf -- @PLANT)}"', PLANT_PATHS),
    (": clean\\\\\nrm -rf -- @PLANT", PLANT_PATHS),
    ('cmd=r; cmd+=m; "$cmd" -rf -- @PLANT', PLANT_PATHS),
    ("python3 -I -c 'import shutil,sys; shutil.rmtree(sys.argv[1])' @PLANT", PLANT_PATHS),
    ("find @PLANT -delete", PLANT_PATHS),
    ("( cd -P -- dist && rm -f -- ./keep.txt )", KEPT_PATHS),
    ("( cd -P -- dist && rm -f -- ./keep.txt; true )", KEPT_PATHS),
    (": > dist/new.txt\nmv -f -- dist/new.txt dist/keep.txt", KEPT_PATHS),
    ("cat <<E >/dev/null; : 'a\nb'\nit\nE\n/usr/bin/r\\\nm -rf -- @PLANT", PLANT_PATHS),
    ("cat <<'E\\' >/dev/null\nx\nE\\\n/usr/bin/r\\\nm -rf -- @PLANT", PLANT_PATHS),
    ("set +e\n: `: it's`\n/usr/bin/r\\\nm -rf -- @PLANT", PLANT_PATHS),
    ("cat <<'E\\' >/dev/null\nx\nE\\\nrm -rf -- @PLANT", PLANT_PATHS),
)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=BUILD_TIMEOUT).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_packager(text: bytes) -> bytes:
    """text, the packager of REFERENCE_COMMIT, with each edit of
    REFERENCE_EDITS made; a text of an edit that does not occur exactly once
    ends the set-up with an error."""
    for old, new in REFERENCE_EDITS:
        count = text.count(old)
        if count != 1:
            raise AssertionError("the packager of REFERENCE_COMMIT holds %r %d times, not once" % (old, count))
        text = text.replace(old, new)
    return text


def edits(name: str) -> set:
    """Every name made from name by deleting 1 character, inserting 1
    character of ALPHABET at any position, replacing 1 character by 1 of
    ALPHABET, or changing the letter case of 1 letter, and name in capital
    letters."""
    made = {name.upper()}
    for i in range(len(name) + 1):
        for c in ALPHABET:
            made.add(name[:i] + c + name[i:])
    for i in range(len(name)):
        made.add(name[:i] + name[i + 1:])
        for c in ALPHABET:
            made.add(name[:i] + c + name[i + 1:])
        if name[i].isalpha():
            made.add(name[:i] + name[i].swapcase() + name[i + 1:])
    return made


def near_misses(version: str) -> list:
    """The near misses of the output names of version and of
    SAMPLE_VERSION, sorted, including the 4 names that repeat an optional
    group. No name is an output name."""
    outputs = ["cleanlanguage.zip"] + ["cleanlanguage-%s.zip" % v for v in (version, SAMPLE_VERSION)]
    outputs += [n + ".sha256" for n in outputs]
    made = set().union(*(edits(n) for n in outputs))
    made |= {"cleanlanguage-%s-%s.zip" % (version, version),
             "cleanlanguage-%s-%s.zip.sha256" % (version, version),
             "cleanlanguage.zip.sha256.sha256",
             "cleanlanguage-%s.zip.sha256.sha256" % version}

    def usable(name: str) -> bool:
        return (name not in ("", ".", "..") and "/" not in name
                and not OUTPUT_NAME.fullmatch(name)
                and name.split("/")[0] not in {p.split("/")[0] for p in OTHER_PLANTS})

    return sorted(filter(usable, made))


def outputs(dist: Path) -> list:
    """Every regular file in dist/ with an output name, and every folder
    with a work-folder name other than LEFTOVER_WORK, which is a work folder
    that a build left; a symbolic link is neither."""
    if not dist.is_dir() or dist.is_symlink():
        return []
    return sorted(p.name for p in dist.iterdir()
                  if not p.is_symlink()
                  and ((OUTPUT_NAME.fullmatch(p.name) and p.is_file())
                       or (WORK_NAME.fullmatch(p.name) and p.is_dir() and p.name not in LEFTOVER_WORK)))


def snapshot(root: Path) -> dict:
    """Every path under root, with the bytes of each file and None for each folder."""
    return {str(p.relative_to(root)): (None if p.is_dir() else p.read_bytes())
            for p in sorted(root.rglob("*"))}


def default_signals():
    """In the build's process, give each signal of TRAPPED_SIGNALS its
    default action and unblock it, so that its bash can trap them even when
    the test was started with 1 of them ignored or blocked, and set the
    limit on the size of a core file to 1 byte, so that a build that such a
    signal ends, when the packager does not trap it, dumps no core."""
    for sig in TRAPPED_SIGNALS:
        signal.signal(sig, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, TRAPPED_SIGNALS)
    _, hard = resource.getrlimit(resource.RLIMIT_CORE)
    if hard == resource.RLIM_INFINITY or hard >= 1:
        resource.setrlimit(resource.RLIMIT_CORE, (1, hard))


def signal_label(number: int) -> str:
    """The name of a signal, such as SIGTERM or SIGRTMIN+3."""
    try:
        return signal.Signals(number).name
    except ValueError:
        return "SIGRTMIN+%d" % (number - signal.SIGRTMIN)


def trapped_without(names: tuple) -> list:
    """The numbers of TRAPPED_SIGNALS, sorted, that the packager traps when
    the kill -l of its shell does not know the names of SIGNAL_NAMES in
    names: each but that of a name in names, and none of the real-time
    range when RTMIN or RTMAX is in names."""
    left = set(TRAPPED_SIGNALS)
    for name in names:
        if name in ("RTMIN", "RTMAX"):
            left -= set(range(signal.SIGRTMIN, signal.SIGRTMAX + 1))
        else:
            left.discard(getattr(signal, "SIG" + name))
    return sorted(left)


def end_group(proc: subprocess.Popen):
    """End with SIGKILL every process of the process group that proc leads
    that still runs, and wait at most REAP_TIMEOUT seconds for proc to end
    and be reaped, so that this never blocks for longer. A process that has
    left that group, such as 1 that proc starts under job control (set -m)
    or with setsid, is not ended."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=REAP_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass


def sh_word(value) -> str:
    """value, a path or a string, as 1 sh word that sh reads back unchanged."""
    return shlex.quote(str(value))


def lstat_tree(root: str) -> dict:
    """The lstat mode of root and of every path under it, by its path; lstat
    follows no symbolic link, and neither does the walk."""
    found = {root: os.lstat(root).st_mode}
    for folder, folders, files in os.walk(root):
        for name in folders + files:
            path = os.path.join(folder, name)
            found[path] = os.lstat(path).st_mode
    return found


def trace_bytes(text: str) -> bytes:
    """The bytes that text, a string or a path of a trace read as Latin-1,
    gives once its escapes are decoded."""
    found, start = bytearray(), 0
    for match in TRACE_ESCAPE.finditer(text):
        found += text[start:match.start()].encode("latin-1")
        hexadecimal, octal, letter = match.groups()
        if hexadecimal:
            found.append(int(hexadecimal, 16))
        elif octal:
            found.append(int(octal, 8) & 0xFF)
        else:
            found += TRACE_ESCAPES.get(letter, letter.encode("latin-1"))
        start = match.end()
    return bytes(found + text[start:].encode("latin-1"))


def trace_string(token: str) -> str:
    """The path that a string argument of the trace gives; a string that is
    not whole or not in hex escapes ends the case."""
    match = TRACE_STRING.fullmatch(token)
    if match is None:
        raise AssertionError("the trace gives the path %r, which is not 1 whole string in hex escapes" % token)
    return os.fsdecode(trace_bytes(match.group(1)))


def trace_folder(token: str, current: str) -> str:
    """The folder that a descriptor argument of the trace names: current for
    AT_FDCWD, and otherwise the path that strace -y gives for the
    descriptor; a descriptor with no such path, or with that of a removed
    folder, ends the case."""
    match = TRACE_DESCRIPTOR.fullmatch(token)
    if match is None:
        raise AssertionError("the trace gives the descriptor %r, which the test cannot read" % token)
    if match.group(1) == "AT_FDCWD":
        return current
    path = None if match.group(2) is None else os.fsdecode(trace_bytes(match.group(2)))
    if path is None or not os.path.isabs(path) or path.endswith(" (deleted)"):
        raise AssertionError("the trace gives the descriptor %r, with no path that the test can use" % token)
    return path


def trace_arguments(text: str) -> list:
    """The arguments of a call of the trace, split at each comma that stands
    outside a string, a path in <...>, braces and brackets."""
    found, start, depth, closing, index = [], 0, 0, "", 0
    while index < len(text):
        char = text[index]
        if closing:
            if char == "\\":
                index += 1
            elif char == closing:
                closing = ""
        elif char in "\"<":
            closing = '"' if char == '"' else ">"
        elif char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
        elif char == "," and depth == 0:
            found.append(text[start:index].strip())
            start = index + 1
        index += 1
    found.append(text[start:].strip())
    return found


def trace_unread(text: str) -> bool:
    """Whether text, the start of a call of the trace, is a call that strace
    could not read at the entry where its process ended: a name of
    TRACE_NAME and ( with no argument, ??? among them, but fork or vfork."""
    name, opening, arguments = text.partition("(")
    return bool(opening) and arguments == "" and name not in NO_ARGUMENT_CALLS


def trace_call(pid: int, text: str, result_given: bool = True) -> tuple:
    """(process id, name, arguments, result) for the text of 1 call of the
    trace; result is None for a call whose text has no result, since the
    trace never resumed it or strace detached from its process during it.
    TRACE_UNFINISHED before the ) of the result ? alone, which strace
    writes when the decoder of a call that it cut short had more to write,
    is dropped. For a call that trace_unread finds, name is None, with no
    argument, when its text has no result or the result ? alone; any other
    result ends the case, since that call then ran with arguments that the
    trace does not give. A text that fits no call ends the case."""
    if result_given:
        match = TRACE_CALL.fullmatch(text)
        if match is None:
            raise AssertionError("the trace holds a call that the test cannot read: %r" % text)
        name, arguments, result, note = match.groups()
        if arguments.endswith(TRACE_UNFINISHED):
            if result != "?" or note is not None:
                raise AssertionError("the trace gives a result for a call that it cut short: %r" % text)
            arguments = arguments[:-len(TRACE_UNFINISHED)]
    else:
        name, opening, arguments = text.partition("(")
        result, note = None, None
        if not opening or not TRACE_NAME.fullmatch(name):
            raise AssertionError("the trace holds a call that the test cannot read: %r" % text)
    if trace_unread(name + "(" + arguments):
        if result is not None and (result != "?" or note is not None):
            raise AssertionError("the trace gives a result for a call whose arguments strace could not read: %r"
                                 % text)
        return pid, None, [], None
    if name == "???":
        raise AssertionError("the trace holds a call that the test cannot read: %r" % text)
    return pid, name, trace_arguments(arguments), result


def trace_records(log: Path) -> list:
    """Each call of the trace at log as trace_call gives it, in the order in
    which the calls started; a call that another process interrupted is
    joined again. A line that fits no form of the trace ends the case, and
    so does any line of a process after a call that ends in TRACE_DETACHED
    or that trace_unread finds, since that process had ended, but the end
    of the process (+++) and, for such a call that TRACE_UNFINISHED left
    open, its resumption."""
    records, open_calls, ended = [], {}, set()
    for line in log.read_bytes().decode("latin-1").splitlines():
        match = TRACE_LINE.fullmatch(line)
        if match is None:
            raise AssertionError("the trace holds a line that the test cannot read: %r" % line)
        pid, text = int(match.group(1)), match.group(2)
        if text.startswith("+++"):
            continue
        resumed = TRACE_RESUMED.fullmatch(text)
        if pid in ended and not (resumed and pid in open_calls):
            raise AssertionError("the trace shows process %d after the call at which it ended: %r" % (pid, line))
        if text.startswith("---"):
            continue
        if resumed:
            index, start = open_calls.pop(pid, (None, ""))
            if index is None or not start.startswith(resumed.group(1) + "("):
                raise AssertionError("the trace resumes a call that it did not start: %r" % line)
            records[index] = trace_call(pid, start + resumed.group(2))
        elif text.endswith(TRACE_UNFINISHED):
            if pid in open_calls:
                raise AssertionError("the trace starts a call of process %d before it resumes the last" % pid)
            open_calls[pid] = (len(records), text[:-len(TRACE_UNFINISHED)])
            records.append(None)
            if trace_unread(open_calls[pid][1]):
                ended.add(pid)
        elif text.endswith(TRACE_DETACHED):
            if pid in open_calls:
                raise AssertionError("the trace starts a call of process %d before it resumes the last" % pid)
            records.append(trace_call(pid, text[:-len(TRACE_DETACHED)], result_given=False))
            ended.add(pid)
        else:
            records.append(trace_call(pid, text))
            if records[-1][1] is None:
                ended.add(pid)
    for pid, (index, start) in open_calls.items():
        records[index] = trace_call(pid, start, result_given=False)
    return records


def traced_path(arguments: list, current: str, descriptor, position: int) -> str:
    """The absolute path that the argument at position of a traced call
    gives, made absolute against the folder of the argument at descriptor,
    or against current when descriptor is None, by its text alone; a
    relative path against a current folder that is None, not known, ends
    the case."""
    path = trace_string(arguments[position])
    if not os.path.isabs(path):
        base = current if descriptor is None else trace_folder(arguments[descriptor], current)
        if base is None:
            raise AssertionError("the trace gives the relative path %r in a current folder that it does not "
                                 "show, after a change of folder or a making of a process that strace cut short"
                                 % path)
        path = os.path.join(base, path)
    return os.path.normpath(path)


def traced_removals(log: Path, start: str) -> tuple:
    """The paths that the processes of the trace at log removed or replaced,
    each as (process id, call, path), and the folders that they entered. A
    path is that given to unlink, unlinkat or rmdir, or either path of a
    rename, renameat or renameat2, of a call that returned 0 or whose result
    the trace does not give. The first process of the trace starts in start;
    each process or thread that a traced call makes starts in the current
    folder of its maker, and shares it when made with CLONE_FS; chdir and
    fchdir change it, and 1 of them whose result is ? or not given leaves
    it not known. A call that trace_unread finds never ran and changes
    nothing, whatever its name. A call that makes a process and whose
    result is ? or not given names no process, so for each such call 1
    process that the trace shows later with no maker starts in a folder
    that is not known. Any other process that no traced call made ends the
    case, as does a call that the test did not ask strace for."""
    records = trace_records(log)
    if not records:
        raise AssertionError("the trace records no call")
    folders, removed, entered, unnamed = {records[0][0]: [start]}, [], [], 0
    for pid, name, arguments, result in records:
        if pid not in folders:
            if not unnamed:
                raise AssertionError("the trace shows process %d, which no traced call made" % pid)
            unnamed -= 1
            folders[pid] = [None]
        folder = folders[pid]
        if name is None:
            continue
        if name in FORKING_CALLS:
            if result is not None and result.isdigit() and int(result) > 0:
                folders[int(result)] = folder if CLONE_FS.search(", ".join(arguments)) else [folder[0]]
            elif result in (None, "?"):
                unnamed += 1
        elif name in ("chdir", "fchdir"):
            if result == "0":
                folder[0] = (traced_path(arguments, folder[0], None, 0) if name == "chdir"
                             else os.path.normpath(trace_folder(arguments[0], folder[0])))
                entered.append(folder[0])
            elif result in (None, "?"):
                folder[0] = None
        elif name in REMOVING_CALLS:
            if result in (None, "?", "0"):
                for descriptor, position in REMOVING_CALLS[name]:
                    removed.append((pid, name, traced_path(arguments, folder[0], descriptor, position)))
        else:
            raise AssertionError("the trace holds the call %s, which the test did not ask strace for" % name)
    return removed, entered


class DistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix=TEMP_PREFIX)
        if os.pathsep in cls.tmp.name:
            cls.tmp.cleanup()
            raise AssertionError("the temporary folder %r holds %r, which no entry of PATH can hold; "
                                 "set TMPDIR to a folder whose path holds none" % (cls.tmp.name, os.pathsep))
        cls.root = os.path.realpath(cls.tmp.name)
        cls.clone = Path(cls.tmp.name) / "clone"
        cls.work = Path(cls.tmp.name) / "work"
        cls.work.mkdir()
        git("clone", "-q", "--no-local", "--no-hardlinks", str(REPO), str(cls.clone))
        for name in TOOLS:
            shutil.copyfile(REPO / "tools" / name, cls.clone / "tools" / name)
        os.chmod(cls.clone / "tools" / "release-package.sh", 0o755)
        cls.dist = cls.clone / "dist"
        skill = git("-C", str(cls.clone), "show", "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md")
        cls.version = next(line.split(":", 1)[1].strip() for line in skill.decode("utf-8").splitlines()
                           if line.startswith("Version:"))
        cls.names = ["cleanlanguage-%s.zip" % cls.version, "cleanlanguage-%s.zip.sha256" % cls.version,
                     "cleanlanguage.zip", "cleanlanguage.zip.sha256"]
        cls.output_misses = near_misses(cls.version)
        reference = cls.clone / "tools" / "release-package-reference.sh"
        reference.write_bytes(reference_packager(
            git("-C", str(REPO), "show", REFERENCE_COMMIT + ":tools/release-package.sh")))
        code, stderr = cls.run_packager(reference)
        if code != 0:
            raise AssertionError(f"the reference packager failed with exit {code}: {stderr}")
        cls.reference_digest = sha256(cls.dist / "cleanlanguage.zip")
        with zipfile.ZipFile(cls.dist / "cleanlanguage.zip") as archive:
            cls.entry_count = len([n for n in archive.namelist() if not n.endswith("/")])
        reference.unlink()
        shutil.rmtree(cls.dist)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        if self.dist.is_dir() and not self.dist.is_symlink():
            shutil.rmtree(self.dist)
        elif os.path.lexists(self.dist):
            self.dist.unlink()

    def plants(self) -> dict:
        """The planted files: OTHER_PLANTS, each near miss as a regular file,
        and the file in each leftover work folder."""
        planted = dict(OTHER_PLANTS)
        for name in self.output_misses:
            planted[name] = name.encode("ascii") + b"\n"
        for name in LEFTOVER_WORK:
            planted[name + "/" + LEFTOVER_FILE] = LEFTOVER_TEXT
        return planted

    @classmethod
    def packager_env(cls, autocrlf: bool = False, path_prefix: str = "", extra: dict = None) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GIT_CONFIG") and k not in SHELL_VARIABLES}
        env["TMPDIR"] = str(cls.work)
        if autocrlf:
            env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.autocrlf", GIT_CONFIG_VALUE_0="true")
        if path_prefix:
            env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
        env.update(extra or {})
        return env

    @classmethod
    def run_packager(cls, script: Path, *args: str, autocrlf: bool = False, path_prefix: str = "",
                     extra: dict = None, timeout: float = BUILD_TIMEOUT, trace: Path = None):
        """Run script with bash in the clone and return its exit code and
        error output. The build runs in a session and a process group of its
        own. When it outlasts timeout, every process of that group is ended
        with SIGKILL, the test waits at most REAP_TIMEOUT seconds for its
        bash to end and at most REAP_TIMEOUT more for its output to close,
        closes that output, and raises the timeout; so no process of the
        group can change dist/ during a later case, and the wait is bounded
        even when a process that has left the group keeps the output open.
        With trace, bash runs under strace, which leads that session and
        group and writes to trace each call of TRACED_CALLS by every
        process of the build."""
        command = ["bash", str(script), *args]
        if trace is not None:
            command = [shutil.which("strace") or "strace", "-f", "-qq", "-xx", "-y", "-o", str(trace),
                       "-e", "trace=" + ",".join(TRACED_CALLS)] + command
        proc = subprocess.Popen(command, cwd=str(cls.clone),
                                env=cls.packager_env(autocrlf, path_prefix, extra),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        try:
            _, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as expired:
            end_group(proc)
            try:
                proc.communicate(timeout=REAP_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass
            finally:
                proc.stdout.close()
                proc.stderr.close()
            raise expired
        return proc.returncode, stderr

    def build(self, *args: str, autocrlf: bool = False, path_prefix: str = "", extra: dict = None):
        return self.run_packager(self.clone / "tools" / "release-package.sh", *args, autocrlf=autocrlf,
                                 path_prefix=path_prefix, extra=extra)

    def outside(self, name: str) -> Path:
        """A new, empty folder of the temporary folder, outside the clone."""
        folder = Path(self.tmp.name) / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir()
        return folder

    def bin_dir(self, name: str) -> Path:
        """A new, empty folder of the temporary folder for stand-ins."""
        return self.outside(name)

    @staticmethod
    def write_script(path: Path, text: str):
        """Write a sh script in the encoding of the file system, so that each
        path that it names is written as the bytes of that path."""
        path.write_bytes(os.fsencode("#!/bin/sh\n" + text))
        os.chmod(path, 0o755)

    @staticmethod
    def recorder(log: Path) -> str:
        """sh lines that define record, which writes 1 record of its
        arguments to log: their number and then each of them, each ended by
        a NUL byte."""
        return "record() {\n  printf '%%s\\000' \"$#\" \"$@\" >> %s\n}\n" % sh_word(log)

    @staticmethod
    def records(log: Path) -> list:
        """The records of a log that record wrote, each as the list of its
        fields."""
        if not log.exists():
            return []
        fields = log.read_bytes().split(b"\0")
        found, index = [], 0
        while index < len(fields) - 1:
            count = int(fields[index])
            found.append([os.fsdecode(f) for f in fields[index + 1:index + 1 + count]])
            index += 1 + count
        return found

    def real(self, name: str) -> str:
        found = shutil.which(name)
        self.assertIsNotNone(found, "%s is not on the PATH" % name)
        return found

    def plant(self):
        """Plant the files of plants() and WORK_LINK."""
        self.dist.mkdir(exist_ok=True)
        for rel, data in self.plants().items():
            path = self.dist / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        link = self.dist / WORK_LINK
        if not link.is_symlink():
            target = self.outside("work-link-target")
            (target / WORK_LINK_FILE).write_bytes(KEEP_TEXT)
            link.symlink_to(target, target_is_directory=True)

    def assert_plants_kept(self):
        """Assert that every plant is unchanged, among them the file in each
        leftover work folder, and that the link and the folder it points at
        are unchanged."""
        for rel, data in self.plants().items():
            path = self.dist / rel
            self.assertTrue(path.is_file() and not path.is_symlink(),
                            "the build removed %s, which it did not write" % path)
            self.assertEqual(path.read_bytes(), data, "the build changed %s, which it did not write" % path)
        for name in LEFTOVER_WORK:
            self.assertEqual(snapshot(self.dist / name), {LEFTOVER_FILE: LEFTOVER_TEXT},
                             "the build changed the leftover work folder %s" % name)
        link = self.dist / WORK_LINK
        target = Path(self.tmp.name) / "work-link-target"
        self.assertTrue(link.is_symlink(), "the build removed the link %s, which it did not write" % link)
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(snapshot(target), {WORK_LINK_FILE: KEEP_TEXT},
                         "the build changed the folder that %s points at" % WORK_LINK)

    def good_build(self, path_prefix: str = "", extra: dict = None):
        self.plant()
        code, stderr = self.build(path_prefix=path_prefix, extra=extra)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)
        self.assert_plants_kept()

    def plant_stale(self):
        """Plant the outputs of an earlier build for each of STALE_VERSIONS."""
        for version in STALE_VERSIONS:
            (self.dist / ("cleanlanguage-%s.zip" % version)).write_bytes(b"stale")
            (self.dist / ("cleanlanguage-%s.zip.sha256" % version)).write_bytes(b"stale\n")

    def assert_refused_leaves_nothing(self, *args: str, autocrlf: bool = False, path_prefix: str = "",
                                      reason: str):
        self.good_build()
        self.plant()
        self.plant_stale()
        code, stderr = self.build(*args, autocrlf=autocrlf, path_prefix=path_prefix)
        self.assertEqual(code, 1, stderr)
        self.assertIn(reason, stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()

    def stand_in(self, name: str) -> tuple:
        """Write a stand-in for name into its own folder of the temporary
        folder. At each call it writes 1 record to its log: the output names
        present in the dist/ of the clone, separated by commas, then its
        working directory and each argument. It then runs the real
        command."""
        real = self.real(name)
        bin_dir = Path(self.tmp.name) / ("record-" + name)
        bin_dir.mkdir(exist_ok=True)
        log = bin_dir / "calls.log"
        if log.exists():
            log.unlink()
        self.write_script(bin_dir / name, self.recorder(log) +
                          "line=\n"
                          "for n in %s; do\n"
                          "  if [ -e %s/\"$n\" ]; then line=\"$line$n,\"; fi\n"
                          "done\n"
                          "record \"$line\" \"$(pwd -P)\" \"$@\"\n"
                          "exec %s \"$@\"\n" % (" ".join(self.names), sh_word(self.dist), sh_word(real)))
        return str(bin_dir), log

    def calls(self, log: Path) -> list:
        """Each recorded call as (the output names present, the working
        directory, the arguments)."""
        return [([n for n in present.split(",") if n], cwd, args)
                for present, cwd, *args in self.records(log)]

    def test_good_build_keeps_other_files(self):
        self.good_build()

    def test_good_build_without_dist(self):
        code, stderr = self.build()
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)

    def test_good_build_matches_reference(self):
        self.good_build()
        for name in ("cleanlanguage.zip", "cleanlanguage-%s.zip" % self.version):
            with self.subTest(name):
                self.assertEqual(sha256(self.dist / name), self.reference_digest)
                self.assertEqual((self.dist / (name + ".sha256")).read_text(encoding="ascii"),
                                 "%s  %s\n" % (self.reference_digest, name))

    def test_refused_tag_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--tag", "v0.0.0", reason="does not match the tag (v0.0.0)")

    def test_refused_release_date_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--release-date", "2020-01-01",
                                           reason="does not match the release date (2020-01-01)")

    def test_refused_unknown_argument_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--bogus", reason="unknown argument --bogus")

    def test_autocrlf_build_leaves_nothing(self):
        self.assert_refused_leaves_nothing(autocrlf=True, reason="differs from its git blob")

    def refusing_mv(self, folder: str, code: int) -> str:
        """Write a stand-in mv that refuses any move of a .sha256 file with
        exit code, and runs the real mv for every other, so the build fails
        after it has moved the 2 zips into dist/. Return its folder."""
        bin_dir = self.bin_dir(folder)
        self.write_script(bin_dir / "mv",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in *.sha256) echo 'mv: refused by the test' >&2; exit %d ;; esac\n"
                          "done\n"
                          "exec %s \"$@\"\n" % (code, sh_word(self.real("mv"))))
        return str(bin_dir)

    def test_failed_move_leaves_nothing(self):
        self.assert_refused_leaves_nothing(path_prefix=self.refusing_mv("bin", 1),
                                           reason="mv: refused by the test")

    def refusing_rm(self, refused: str) -> str:
        """Write a stand-in rm, first on the PATH, that fails, without removing
        anything, at any call with the argument ./<refused>, the name by which
        the removal, run in dist/, removes it, and runs the real rm for every
        other call. It records nothing. Return its folder."""
        bin_dir = self.bin_dir("refusing-rm")
        self.write_script(bin_dir / "rm",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in %s) echo 'rm: refused by the test' >&2; exit 1 ;; esac\n"
                          "done\n"
                          "exec %s \"$@\"\n" % (sh_word("./" + refused), sh_word(self.real("rm"))))
        return str(bin_dir)

    def test_failed_removal_of_output_refused(self):
        """After a good build, a build whose removal of the version-named zip
        fails exits 1 with the packager's removal message; that zip is still
        there, and every other earlier output is gone."""
        refused = "cleanlanguage-%s.zip" % self.version
        self.good_build()
        self.plant()
        self.plant_stale()
        code, stderr = self.build(path_prefix=self.refusing_rm(refused))
        self.assertEqual(code, 1, stderr)
        self.assertIn("rm: refused by the test", stderr)
        self.assertIn(REMOVAL_FAILED, stderr)
        self.assertEqual(outputs(self.dist), [refused], "the build removed the wrong set of earlier outputs")
        self.assert_plants_kept()

    def test_moves_staged_zips_before_checksums(self):
        """A stand-in mv records each move into dist/: each of the 4 is
        `mv -fT -- <work>/<name> <work>/../<name>`, where <work> is a folder
        of dist/ with a work-folder name, and both zips are in dist/ before
        either .sha256 is moved there."""
        bin_dir, log = self.stand_in("mv")
        self.good_build(path_prefix=bin_dir)
        dist = os.path.realpath(self.dist)
        moves = [(present, args) for present, _, args in self.calls(log)
                 if args and OUTPUT_NAME.fullmatch(os.path.basename(args[-1]))]
        self.assertEqual(len(moves), 4, "the moves into dist/ were %r" % moves)
        for present, args in moves:
            self.assertEqual(len(args), 4, "a move into dist/ was %r" % args)
            options, end, source, target = args
            self.assertEqual((options, end), ("-fT", "--"), "a move into dist/ was %r" % args)
            folder, name = os.path.split(source)
            self.assertTrue(WORK_NAME.fullmatch(os.path.basename(folder)),
                            "a move into dist/ took a source outside a work folder: %r" % args)
            self.assertEqual(os.path.realpath(os.path.dirname(folder)), dist,
                             "the work folder of a move is not in dist/: %r" % args)
            self.assertEqual(target, folder + "/../" + name, "a move into dist/ was %r" % args)
            if name.endswith(".sha256"):
                self.assertTrue(all(z in present for z in self.names if z.endswith(".zip")),
                                "a .sha256 was moved into dist/ before both zips were there: %r" % moves)
        self.assertEqual(sorted(os.path.basename(args[-1]) for _, args in moves), self.names)

    def test_no_output_in_dist_during_checks(self):
        bin_dir, log = self.stand_in("unzip")
        self.good_build(path_prefix=bin_dir)
        calls = self.calls(log)
        self.assertTrue(calls, "the build never called unzip")
        for present, _, args in calls:
            self.assertEqual(present, [], "unzip %r ran with %r already in dist/" % (args, present))

    def test_zip_runs_in_layout_folder(self):
        """In a good build with nothing planted, a stand-in zip records 1
        call, which writes cleanlanguage.zip in a folder of dist/ with a
        work-folder name and runs in src/cleanlanguage/ of that folder. A
        build that runs zip in another folder fails this case after 1
        build."""
        bin_dir, log = self.stand_in("zip")
        code, stderr = self.build(path_prefix=bin_dir)
        calls = self.calls(log)
        self.assertEqual(len(calls), 1, "the build called zip %d times: %r" % (len(calls), calls))
        _, cwd, args = calls[0]
        folder, name = os.path.split(args[-1])
        self.assertEqual(name, "cleanlanguage.zip", "zip wrote %r" % args[-1])
        self.assertTrue(WORK_NAME.fullmatch(os.path.basename(folder)), "zip wrote %r outside a work folder" % args[-1])
        self.assertEqual(os.path.realpath(os.path.dirname(folder)), os.path.realpath(self.dist),
                         "the work folder of zip is not in dist/: %r" % args[-1])
        self.assertEqual(cwd, os.path.realpath(os.path.join(folder, "src", "cleanlanguage")),
                         "zip ran in %s, not in src/cleanlanguage/ of its work folder" % cwd)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)

    def test_symlinked_dist_refused(self):
        target = self.outside("linked-dist")
        for name in ("cleanlanguage.zip", "cleanlanguage-other.zip", "unrelated.txt"):
            (target / name).write_bytes(b"planted in the link target\n")
        before = snapshot(target)
        self.dist.symlink_to(target, target_is_directory=True)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn(LINKED_DIST, stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(snapshot(target), before, "the build changed the folder that dist points at")

    def test_dangling_symlinked_dist_refused(self):
        target = Path(self.tmp.name) / "absent-dist"
        if target.exists():
            shutil.rmtree(target)
        self.dist.symlink_to(target, target_is_directory=True)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn(LINKED_DIST, stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(os.readlink(self.dist), str(target))
        self.assertFalse(os.path.lexists(target), "the build created the missing folder that dist points at")

    def test_file_dist_refused(self):
        self.dist.write_bytes(KEEP_TEXT)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist exists and is not a folder", stderr)
        self.assertTrue(self.dist.is_file() and not self.dist.is_symlink())
        self.assertEqual(self.dist.read_bytes(), KEEP_TEXT)

    def test_fifo_dist_refused(self):
        os.mkfifo(self.dist)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist exists and is not a folder", stderr)
        self.assertTrue(stat.S_ISFIFO(self.dist.lstat().st_mode), "the build replaced the FIFO dist")

    def assert_no_work_folder(self, log: Path):
        """Assert that the stand-in mktemp whose log is given was never called,
        so the build was refused before it made its work folder, which it
        makes before it writes to dist/."""
        self.assertEqual(self.calls(log), [], "the build made a work folder before it was refused")

    def test_output_name_folder_kept(self):
        self.plant()
        folder = self.dist / "cleanlanguage.zip"
        folder.mkdir()
        (folder / KEEP).write_bytes(KEEP_TEXT)
        bin_dir, log = self.stand_in("mktemp")
        code, stderr = self.build(path_prefix=bin_dir)
        self.assertEqual(snapshot(folder), {KEEP: KEEP_TEXT}, "the build changed the folder %s" % folder)
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist/cleanlanguage.zip " + REFUSED_NAME, stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()
        self.assert_no_work_folder(log)

    def plant_object(self, kind: str, name: str) -> tuple:
        """Plant at dist/<name> an object of the given kind that the packager
        did not write: "link" (to a file outside dist/), "dangling link" or
        "fifo". Return the object's path and, for a link, its target."""
        path = self.dist / name
        target = None
        if kind == "link":
            target = self.outside("object-target") / "target.txt"
            target.write_bytes(KEEP_TEXT)
            path.symlink_to(target)
        elif kind == "dangling link":
            target = self.outside("object-target") / "absent"
            path.symlink_to(target)
        else:
            os.mkfifo(path)
        return path, target

    def assert_object_unchanged(self, kind: str, path: Path, target):
        self.assertTrue(os.path.lexists(path), "the build removed %s, which it did not write" % path)
        if kind == "fifo":
            self.assertTrue(stat.S_ISFIFO(path.lstat().st_mode), "the build replaced the FIFO %s" % path)
            return
        self.assertTrue(path.is_symlink(), "the build replaced the link %s" % path)
        self.assertEqual(os.readlink(path), str(target))
        if kind == "link":
            self.assertEqual(snapshot(target.parent), {target.name: KEEP_TEXT},
                             "the build changed the file that %s points at" % path)
        else:
            self.assertEqual(snapshot(target.parent), {}, "the build created what %s points at" % path)

    def move_then_fail(self) -> str:
        """Write a stand-in mv, first on the PATH, that runs the real mv and,
        for a move of a .sha256 file, then fails. It records nothing. Return
        its folder. The packager refuses an object at an output name before
        any move, so a build that passes the object cases never calls it; a
        build that reached the moves would fail at the first move of a .sha256
        file, after the rename had replaced the object and before the exit
        trap removed what replaced it, so the case fails without the refusal."""
        bin_dir = self.bin_dir("move-then-fail")
        self.write_script(bin_dir / "mv",
                          "%s \"$@\" || exit\n"
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in *.sha256) echo 'mv: failed after the move, by the test' >&2; exit 1 ;; esac\n"
                          "done\n" % sh_word(self.real("mv")))
        return str(bin_dir)

    def assert_object_refused(self, kind: str, name: str, failed_move: bool):
        path_prefix = ""
        if failed_move:
            path_prefix = self.move_then_fail()
            self.good_build()
        self.plant()
        if failed_move:
            self.plant_stale()
            # The object takes the place of the good build's output of that name.
            (self.dist / name).unlink()
        path, target = self.plant_object(kind, name)
        bin_dir, log = self.stand_in("mktemp")
        code, stderr = self.build(path_prefix=os.pathsep.join(p for p in (path_prefix, bin_dir) if p))
        self.assert_object_unchanged(kind, path, target)
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist/%s %s" % (name, REFUSED_NAME), stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()
        self.assert_no_work_folder(log)

    def test_link_at_zip_name_refused(self):
        self.assert_object_refused("link", "cleanlanguage.zip", failed_move=False)

    def test_link_at_zip_name_refused_with_failed_move(self):
        self.assert_object_refused("link", "cleanlanguage.zip", failed_move=True)

    def test_link_at_zip_checksum_name_refused(self):
        self.assert_object_refused("link", "cleanlanguage.zip.sha256", failed_move=False)

    def test_link_at_checksum_name_refused(self):
        self.assert_object_refused("dangling link", "cleanlanguage-%s.zip.sha256" % self.version,
                                   failed_move=False)

    def test_link_at_checksum_name_refused_with_failed_move(self):
        self.assert_object_refused("dangling link", "cleanlanguage-%s.zip.sha256" % self.version,
                                   failed_move=True)

    def test_fifo_at_output_name_refused(self):
        self.assert_object_refused("fifo", "cleanlanguage-%s.zip" % self.version, failed_move=False)

    def test_fifo_at_output_name_refused_with_failed_move(self):
        self.assert_object_refused("fifo", "cleanlanguage-%s.zip" % self.version, failed_move=True)

    def held_signal(self, proc: subprocess.Popen, held: Path, go: Path, sig: int, what: str,
                    group: bool = False) -> str:
        """Wait until the stand-in of proc has written held, send sig to the
        build's bash, or with group to every process of its process group,
        as a terminal or a CI runner does, then write go so that the
        stand-in goes on; once the build's bash has ended, or once
        BUILD_TIMEOUT has passed without its end, end with SIGKILL every
        process of its process group that still runs, such as a stand-in
        that a build ended at once left behind, wait at most REAP_TIMEOUT
        seconds for the bash to be reaped and close its error output, so
        that none of them changes dist/ after this returns or raises; raise
        the timeout if there was one, and return the build's stderr
        otherwise."""
        try:
            deadline = time.monotonic() + BUILD_TIMEOUT
            while not held.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(held.exists(), what)
            if group:
                os.killpg(proc.pid, sig)
            else:
                proc.send_signal(sig)
            time.sleep(0.2)
        finally:
            go.write_bytes(b"")
            try:
                proc.wait(timeout=BUILD_TIMEOUT)
            finally:
                end_group(proc)
                proc.output.seek(0)
                stderr = proc.output.read().decode("utf-8", "replace")
                proc.output.close()
        return stderr

    def popen_build(self, *args: str, path_prefix: str, extra: dict = None) -> subprocess.Popen:
        """Start a build that the test signals. Its error output goes to a
        file of the temporary folder, never to a pipe that the test does not
        read while it waits, and its standard output is discarded, so a
        build that writes more than a pipe holds does not block until the
        wait ends; held_signal reads the file. The build runs in a session
        and a process group of its own, whose processes held_signal can
        signal and end together."""
        output = tempfile.TemporaryFile(dir=self.tmp.name)
        proc = subprocess.Popen(["bash", str(self.clone / "tools" / "release-package.sh"), *args],
                                cwd=str(self.clone), env=self.packager_env(path_prefix=path_prefix, extra=extra),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=output,
                                preexec_fn=default_signals, start_new_session=True)
        proc.output = output
        return proc

    def holding_rm(self, bin_dir: Path, end_removal: bool = False):
        """Write into bin_dir a stand-in rm that, at its first call with an
        argument that starts with ./ (a removal in dist/), writes held and
        waits for go, then runs the real rm. With end_removal, it instead
        kills, with SIGKILL, the subshell that called it, in which that
        removal runs, and exits 1 without removing anything, so that the
        removal ends half done. Return held and go."""
        held, go = bin_dir / "held", bin_dir / "go"
        self.write_script(bin_dir / "rm",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in ./*)\n"
                          "    if [ ! -e %s ]; then\n"
                          "      : > %s\n"
                          "      n=0\n"
                          "      while [ ! -e %s ] && [ \"$n\" -lt 1200 ]; do sleep 0.1; n=$((n + 1)); done\n"
                          "%s"
                          "    fi\n"
                          "    break ;;\n"
                          "  esac\n"
                          "done\n"
                          "exec %s \"$@\"\n"
                          % (sh_word(held), sh_word(held), sh_word(go),
                             "      kill -9 \"$PPID\"\n      exit 1\n" if end_removal else "",
                             sh_word(self.real("rm"))))
        return held, go

    def assert_signal_ends_build(self, sig: int, code: int, extra: dict = None):
        """A stand-in mv holds each move of a .sha256 file until the test
        has sent sig to the build, with extra in its environment, then runs
        the real mv; the build must exit with code and leave no zip and no
        .sha256 in dist/."""
        bin_dir = self.bin_dir("holding-mv")
        held, go = bin_dir / "held", bin_dir / "go"
        self.write_script(bin_dir / "mv",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in *.sha256)\n"
                          "    : > %s\n"
                          "    n=0\n"
                          "    while [ ! -e %s ] && [ \"$n\" -lt 1200 ]; do sleep 0.1; n=$((n + 1)); done\n"
                          "    break ;;\n"
                          "  esac\n"
                          "done\n"
                          "exec %s \"$@\"\n" % (sh_word(held), sh_word(go), sh_word(self.real("mv"))))
        self.plant()
        proc = self.popen_build(path_prefix=str(bin_dir), extra=extra)
        stderr = self.held_signal(proc, held, go, sig, "the build never moved a .sha256 file")
        self.assertEqual(proc.returncode, code, stderr)
        self.assertEqual(outputs(self.dist), [], "a build ended by a signal left output in dist/")
        self.assert_plants_kept()

    def test_other_signals_during_move_leave_nothing(self):
        """Each signal of OTHER_SIGNALS, sent while a stand-in mv holds the
        move of the .sha256 files, ends the build with 128 plus its number,
        and the build leaves no zip and no .sha256 in dist/."""
        for sig in OTHER_SIGNALS:
            with self.subTest(signal=signal_label(sig)):
                self.setUp()
                self.assert_signal_ends_build(sig, 128 + sig)

    def test_sigterm_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGTERM, 143)

    def test_sighup_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGHUP, 129)

    def test_sigint_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGINT, 130)

    def assert_signal_during_first_removal(self, sig: int, code: int):
        """After a good build, with the plants and the stale outputs planted
        again, a build refused by --bogus whose stand-in rm holds the first
        removal in dist/ until the test has sent sig to the build, and then
        ends that removal half done by killing the subshell in which it
        runs, must exit with code and leave no zip and no .sha256 in dist/,
        neither the good build's nor a stale one: only its exit trap can
        remove the rest of them."""
        self.good_build()
        self.plant()
        self.plant_stale()
        bin_dir = self.bin_dir("holding-rm")
        held, go = self.holding_rm(bin_dir, end_removal=True)
        proc = self.popen_build("--bogus", path_prefix=str(bin_dir))
        stderr = self.held_signal(proc, held, go, sig, "the first removal never removed an entry of dist/")
        self.assertEqual(proc.returncode, code, stderr)
        self.assertNotIn("unknown argument --bogus", stderr)
        self.assertEqual(outputs(self.dist), [], "a build ended during its first removal left output in dist/")
        self.assert_plants_kept()

    def test_sigterm_during_first_removal_leaves_nothing(self):
        self.assert_signal_during_first_removal(signal.SIGTERM, 143)

    def test_sighup_during_first_removal_leaves_nothing(self):
        self.assert_signal_during_first_removal(signal.SIGHUP, 129)

    def test_sigint_during_first_removal_leaves_nothing(self):
        self.assert_signal_during_first_removal(signal.SIGINT, 130)

    def test_other_signals_during_first_removal_leave_nothing(self):
        """As the 3 cases above, for each signal of OTHER_SIGNALS, with 128
        plus its number as the exit code."""
        for sig in OTHER_SIGNALS:
            with self.subTest(signal=signal_label(sig)):
                self.setUp()
                self.assert_signal_during_first_removal(sig, 128 + sig)

    def wide_locale(self) -> str:
        """The first of WIDE_LOCALES in which a bash [0-9] takes an
        Arabic-Indic digit, or an empty string."""
        for locale in WIDE_LOCALES:
            proc = subprocess.run(["bash", "-c", "[[ $1 =~ ^[0-9]$ ]]", "probe", chr(0x663)],
                                  env=self.packager_env(extra={"LC_ALL": locale}),
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=BUILD_TIMEOUT)
            if proc.returncode == 0:
                return locale
        return ""

    def test_name_tests_ignore_locale(self):
        """Under a locale in which a bash range takes a digit outside ASCII,
        a good build, with the plants and NON_ASCII_FILES planted, keeps each
        of the latter unchanged and keeps the planted paths."""
        locale = self.wide_locale()
        if not locale:
            self.skipTest("no locale of %s in which a bash range takes a digit outside ASCII is installed"
                          % ", ".join(WIDE_LOCALES))
        self.plant()
        for name in NON_ASCII_FILES:
            with open(os.path.join(os.fsencode(self.dist), name.encode("utf-8")), "wb") as handle:
                handle.write(KEEP_TEXT)
        code, stderr = self.build(extra={"LC_ALL": locale})
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)
        self.assert_plants_kept()
        for name in NON_ASCII_FILES:
            path = os.path.join(os.fsencode(self.dist), name.encode("utf-8"))
            self.assertTrue(os.path.isfile(path), "the build under %s removed %r" % (locale, name))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), KEEP_TEXT)

    def assert_inherited_option(self, plant: bool = True, **extra: str):
        """A good build and then a build refused by --bogus, with nothing
        planted again, each with extra in its environment. Without plant,
        the good build starts with an empty dist/, so that no glob of the
        removal matches an entry there."""
        if plant:
            self.good_build(extra=extra)
        else:
            self.dist.mkdir()
            code, stderr = self.build(extra=extra)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(outputs(self.dist), self.names)
        code, stderr = self.build("--bogus", extra=extra)
        self.assertEqual(code, 1, stderr)
        self.assertIn("unknown argument --bogus", stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        if plant:
            self.assert_plants_kept()

    def test_inherited_failglob(self):
        # Nothing is planted: any planted name would give the glob * of the
        # removal a match.
        self.assert_inherited_option(plant=False, BASHOPTS="failglob")

    def test_inherited_dotglob(self):
        self.assert_inherited_option(BASHOPTS="dotglob")

    def test_inherited_nocasematch(self):
        self.assert_inherited_option(BASHOPTS="nocasematch")

    def test_inherited_noglob(self):
        self.assert_inherited_option(SHELLOPTS="noglob")

    def test_inherited_globignore(self):
        self.assert_inherited_option(GLOBIGNORE=GLOBIGNORE_VALUE)

    def test_globignore_from_bash_env(self):
        # Bash 5.3.9 applies a GLOBIGNORE that a BASH_ENV file assigns, but
        # not one that it takes from its environment.
        # Bash expands the value of BASH_ENV before it reads that file, so
        # the case gives its path relative to the root of the clone, where
        # each build starts, which holds no character of the temporary path.
        bash_env = self.outside("bash-env") / "globignore.sh"
        bash_env.write_text("GLOBIGNORE='%s'\n" % GLOBIGNORE_VALUE, encoding="ascii")
        self.assert_inherited_option(BASH_ENV=os.path.relpath(bash_env, self.clone))

    def trap_stand_ins(self, move_exit: int = 0, refused: str = "") -> tuple:
        """Write a stand-in mktemp that writes the full path of each work
        folder it makes to its log, and the first of them, as it is, to the
        file first-work-folder of its folder; with move_exit, a stand-in mv
        that refuses each move of a .sha256 file with that exit code; and
        with refused, a stand-in rm that fails, without removing anything,
        at the argument refused, where @1 names the path of the first work
        folder, the operand by which the exit trap removes it. Return the
        folder and the log."""
        bin_dir = self.bin_dir("trap-stand-ins")
        log = bin_dir / "work-folders.log"
        first = bin_dir / "first-work-folder"
        self.write_script(bin_dir / "mktemp", self.recorder(log) +
                          "p=$(%s \"$@\") || exit\n"
                          "case \"$p\" in /*) full=$p ;; *) full=\"$(pwd -P)/$p\" ;; esac\n"
                          "record \"$full\"\n"
                          "[ -e %s ] || printf '%%s' \"$full\" > %s\n"
                          "printf '%%s\\n' \"$p\"\n" % (sh_word(self.real("mktemp")), sh_word(first), sh_word(first)))
        if move_exit:
            self.write_script(bin_dir / "mv",
                              "for a in \"$@\"; do\n"
                              "  case \"$a\" in *.sha256) echo 'mv: refused by the test' >&2; exit %d ;; esac\n"
                              "done\n"
                              "exec %s \"$@\"\n" % (move_exit, sh_word(self.real("mv"))))
        if refused:
            self.write_script(bin_dir / "rm",
                              "target=%s\n"
                              "case \"$target\" in\n"
                              "  @1) target=$(cat %s) ;;\n"
                              "esac\n"
                              "for a in \"$@\"; do\n"
                              "  if [ \"$a\" = \"$target\" ]; then echo 'rm: refused by the test' >&2; exit 1; fi\n"
                              "done\n"
                              "exec %s \"$@\"\n" % (sh_word(refused), sh_word(first), sh_word(self.real("rm"))))
        return str(bin_dir), log

    def work_folder(self, log: Path) -> Path:
        folders = [fields[0] for fields in self.records(log)]
        self.assertEqual(len(folders), 1, "the build made the work folders %r" % folders)
        return Path(folders[0])

    def test_good_build_removes_work_folder(self):
        bin_dir, log = self.trap_stand_ins()
        self.good_build(path_prefix=bin_dir)
        folder = self.work_folder(log)
        self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)

    def assert_trap(self, move_exit: int, refused: str):
        """A build whose stand-in mv, with move_exit, refuses each move of a
        .sha256 file with that exit code, and whose stand-in rm fails at
        refused, exits with move_exit, or 0 without it; the path that
        refused names is still there, the work folder is gone unless rm
        failed at it, and so is every other output of a failed build."""
        bin_dir, log = self.trap_stand_ins(move_exit, refused)
        self.plant()
        code, stderr = self.build(path_prefix=bin_dir)
        self.assertEqual(code, move_exit, stderr)
        if move_exit:
            self.assertIn("mv: refused by the test", stderr)
        folder = self.work_folder(log)
        if refused == "@1":
            self.assertTrue(folder.is_dir(), "the stand-in rm did not keep %s" % folder)
        else:
            self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)
        expected = [] if move_exit else list(self.names)
        if refused.startswith("./"):
            expected.append(refused[len("./"):])
        if refused == "@1":
            expected.append(folder.name)
        self.assertEqual(outputs(self.dist), sorted(expected), "the exit trap removed the wrong set of outputs")
        self.assert_plants_kept()
        if refused == "@1":
            shutil.rmtree(folder)

    def test_failed_build_keeps_exit_code_and_removes_work_folder(self):
        self.assert_trap(MOVE_EXIT, "")

    def test_trap_continues_after_failed_output_removal(self):
        self.assert_trap(MOVE_EXIT, "./cleanlanguage.zip")

    def test_failed_build_keeps_exit_code_after_failed_work_folder_removal(self):
        self.assert_trap(MOVE_EXIT, "@1")

    def test_good_build_exits_0_after_failed_work_folder_removal(self):
        self.assert_trap(0, "@1")

    def assert_signal_during_trap(self, sig: int):
        """A build whose stand-in mv refuses each move of a .sha256 file with
        MOVE_EXIT, and whose stand-in rm holds the first removal of the exit
        trap until the test has sent sig to every process of the build's
        process group, must still complete the removals of the trap and exit
        with MOVE_EXIT. Nothing is planted, so the trap makes the first
        removal in dist/ of the build. The subshell of that removal and the
        stand-in rm receive sig too: they keep a signal that the trap
        ignores ignored, but take the default action for 1 that it catches
        with a handler, so such a trap lets sig end the removal."""
        bin_dir, log = self.trap_stand_ins(MOVE_EXIT)
        held, go = self.holding_rm(Path(bin_dir))
        proc = self.popen_build(path_prefix=bin_dir)
        stderr = self.held_signal(proc, held, go, sig, "the exit trap never removed an output from dist/",
                                  group=True)
        self.assertEqual(proc.returncode, MOVE_EXIT, stderr)
        self.assertIn("mv: refused by the test", stderr)
        self.assertEqual(outputs(self.dist), [], "a signal cut the removals of the exit trap short")
        folder = self.work_folder(log)
        self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)

    def test_sigterm_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGTERM)

    def test_sighup_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGHUP)

    def test_sigint_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGINT)

    def test_other_signals_during_exit_trap_ignored(self):
        """As the 3 cases above, for each signal of OTHER_SIGNALS."""
        for sig in OTHER_SIGNALS:
            with self.subTest(signal=signal_label(sig)):
                self.setUp()
                self.assert_signal_during_trap(sig)

    def test_name_test_edges(self):
        """After a good build, a build refused by --bogus keeps the planted
        paths, among them the regular file Cleanlanguage.zip (an output name
        with a capital initial, which the near misses hold), and removes the
        2 outputs of version 11111111111.0.0, whose first part has 11
        digits."""
        self.assertIn("Cleanlanguage.zip", self.output_misses)
        self.good_build()
        kept_file = self.dist / "Cleanlanguage.zip"
        for name in ("cleanlanguage-11111111111.0.0.zip", "cleanlanguage-11111111111.0.0.zip.sha256"):
            (self.dist / name).write_bytes(b"stale\n")
        code, stderr = self.build("--bogus")
        self.assertEqual(code, 1, stderr)
        self.assertIn("unknown argument --bogus", stderr)
        self.assertTrue(kept_file.is_file(), "the build removed %s" % kept_file)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()

    @classmethod
    def real_path(cls, path: str) -> str:
        """path with the path of the temporary folder, as the test gave it,
        replaced by the real path of that folder, root."""
        given = os.path.abspath(cls.tmp.name)
        if path == given or path.startswith(given + os.sep):
            return cls.root + path[len(given):]
        return path

    def stated_removal(self, path: str, before: dict) -> bool:
        """Whether the packager states that a build may remove or replace
        path, a real path: a path of the temporary folder below no symbolic
        link of before that did not exist before the build, or a regular
        file directly in dist/ with an output name. before is lstat_tree of
        the temporary folder just before the build."""
        if not path.startswith(self.root + os.sep):
            return False
        folder = os.path.dirname(path)
        while folder != self.root:
            if stat.S_ISLNK(before.get(folder, 0)):
                return False
            folder = os.path.dirname(folder)
        if path not in before:
            return True
        return (os.path.dirname(path) == self.real_path(str(self.dist))
                and OUTPUT_NAME.fullmatch(os.path.basename(path)) is not None and stat.S_ISREG(before[path]))

    def traced_build(self, script: Path, *args: str, autocrlf: bool = False, path_prefix: str = "") -> tuple:
        """Run script as run_packager does, under strace, and return its exit
        code, its error output, each path that the build removed or
        replaced, as (process id, call, real path), and those of them that
        stated_removal refuses. The case fails, rather than passing without
        a trace, when strace is not on the PATH, writes to the build's error
        output, or records no chdir of the build into the clone."""
        self.assertIsNotNone(shutil.which("strace"),
                             "strace is not on the PATH; this case needs it to see what a build removes")
        trace = self.outside("trace") / "calls.trace"
        before = lstat_tree(self.root)
        code, stderr = self.run_packager(script, *args, autocrlf=autocrlf, path_prefix=path_prefix, trace=trace)
        self.assertNotIn("strace: ", stderr, "strace could not trace the build")
        self.assertTrue(trace.is_file(), "strace wrote no trace of the build: %s" % stderr)
        removed, entered = traced_removals(trace, str(self.clone))
        self.assertIn(self.real_path(str(self.clone)), [self.real_path(p) for p in entered],
                      "the trace records no chdir of the build into the clone, so strace did not trace it")
        removed = [(pid, call, self.real_path(path)) for pid, call, path in removed]
        return code, stderr, removed, [r for r in removed if not self.stated_removal(r[2], before)]

    def test_removals_only_as_stated(self):
        """Under strace, a good build, a build refused by the blob check, a
        build whose move of the .sha256 files fails, and a build refused by
        --bogus each remove or replace only what stated_removal allows; each
        but the last removes the work folder at the path that the stand-in
        mktemp recorded, and the last makes none."""
        for label, args, autocrlf, move_exit in (("good", (), False, 0), ("blob", (), True, 0),
                                                  ("move", (), False, MOVE_EXIT), ("bogus", ("--bogus",), False, 0)):
            with self.subTest(label):
                self.setUp()
                bin_dir, work_log = self.trap_stand_ins(move_exit)
                self.plant()
                code, stderr, removed, refused = self.traced_build(
                    self.clone / "tools" / "release-package.sh", *args, autocrlf=autocrlf, path_prefix=bin_dir)
                self.assertEqual(code, {"good": 0, "blob": 1, "move": MOVE_EXIT, "bogus": 1}[label], stderr)
                self.assertEqual(refused, [], "the build removed or replaced paths that it does not state")
                if label == "bogus":
                    self.assertFalse(work_log.exists(), "the build refused by --bogus made a work folder")
                else:
                    folder = self.real_path(str(self.work_folder(work_log)))
                    self.assertIn(folder, [path for _, _, path in removed],
                                  "the trace shows no removal of the work folder %s" % folder)
                self.assert_plants_kept()

    def test_trace_reports_each_form(self):
        """A good build with no added form, and with each form of
        ORACLE_FORMS added at the end of a copy of the packager, runs under
        the trace of traced_build: the control gives no refused path, and
        each form gives exactly the paths that it names, real, and no other."""
        packager = (self.clone / "tools" / "release-package.sh").read_text(encoding="utf-8")
        script = self.clone / "tools" / "release-package-oracle.sh"
        clone = self.real_path(str(self.clone))
        try:
            for form, paths in (("", ()),) + ORACLE_FORMS:
                with self.subTest(form or "control"):
                    self.setUp()
                    self.plant()
                    plant = self.outside("oracle-plant")
                    (plant / KEEP).write_bytes(KEEP_TEXT)
                    added = form.replace("@PLANT", sh_word(plant))
                    script.write_bytes(os.fsencode(packager.rstrip("\n") + "\n" + added + "\n"))
                    _, stderr, _, refused = self.traced_build(script)
                    expected = sorted(p.replace("@PLANT", self.real_path(str(plant))) if p.startswith("@PLANT")
                                      else os.path.join(clone, p) for p in paths)
                    self.assertEqual(sorted({path for _, _, path in refused}), expected,
                                     "the trace refused %r: %s" % (refused, stderr))
        finally:
            if script.exists():
                script.unlink()

    def test_leftover_work_folders_kept(self):
        """A folder with a work-folder name that holds a file, as a SIGKILL
        could leave, is kept unchanged by a good build, by a build refused
        by --bogus, by a build refused by the blob check, and by a build
        whose move of the .sha256 files fails."""
        self.good_build()
        for label, args, autocrlf, prefix in (("bogus", ("--bogus",), False, ""), ("blob", (), True, ""),
                                              ("move", (), False, self.refusing_mv("leftover-mv", 1))):
            with self.subTest(label):
                code, stderr = self.build(*args, autocrlf=autocrlf, path_prefix=prefix)
                self.assertEqual(code, 1, stderr)
                self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
                self.assert_plants_kept()

    def test_dist_link_after_mkdir_refused(self):
        """A stand-in mkdir, at the build's `mkdir -p dist`, first puts at
        dist a symbolic link to a folder outside the clone that holds a file
        named cleanlanguage.zip, then runs the real mkdir. The build exits 1
        with the message for a linked dist before it makes its work folder;
        the outside folder is unchanged."""
        target = self.outside("late-linked-dist")
        (target / "cleanlanguage.zip").write_bytes(b"a reader's file\n")
        before = snapshot(target)
        bin_dir, log = self.stand_in("mktemp")
        mkdir_dir = self.bin_dir("linking-mkdir")
        made = mkdir_dir / "linked"
        self.write_script(mkdir_dir / "mkdir",
                          "if [ \"$1\" = -p ] && [ \"$2\" = dist ] && [ ! -e %s ]; then\n"
                          "  : > %s\n"
                          "  %s -s %s dist || exit 1\n"
                          "fi\n"
                          "exec %s \"$@\"\n" % (sh_word(made), sh_word(made), sh_word(self.real("ln")),
                                                sh_word(target), sh_word(self.real("mkdir"))))
        code, stderr = self.build(path_prefix=os.pathsep.join((str(mkdir_dir), bin_dir)))
        self.assertTrue(made.exists(), "the stand-in mkdir never linked dist")
        self.assertEqual(code, 1, stderr)
        self.assertIn(LINKED_DIST, stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(snapshot(target), before, "the build changed the folder that dist points at")
        self.assert_no_work_folder(log)

    def last_cmp(self, bin_dir: Path, action: str):
        """Write into bin_dir a stand-in cmp that runs the real cmp and, after
        its call number entry_count, the last check before the moves, runs
        the sh lines of action."""
        count = bin_dir / "cmp-count"
        self.write_script(bin_dir / "cmp",
                          "%s \"$@\"\n"
                          "rc=$?\n"
                          "n=$(($(cat %s 2>/dev/null || echo 0) + 1))\n"
                          "echo \"$n\" > %s\n"
                          "if [ \"$n\" -eq %d ]; then\n"
                          "%s"
                          "fi\n"
                          "exit \"$rc\"\n" % (sh_word(self.real("cmp")), sh_word(count), sh_word(count),
                                              self.entry_count, action))

    def test_folder_at_output_name_after_refusal_fails_move(self):
        """A stand-in cmp, after its last call, makes a folder holding KEEP
        at dist/cleanlanguage.zip. The first move, `mv -fT`, fails rather
        than move the zip into that folder; the folder is unchanged, and
        dist/ holds no zip and no .sha256."""
        bin_dir = self.bin_dir("folder-cmp")
        folder = self.dist / "cleanlanguage.zip"
        self.last_cmp(bin_dir, "%s %s || exit 1\n"
                               "printf 'a file the packager does not write\\n' > %s || exit 1\n"
                      % (sh_word(self.real("mkdir")), sh_word(folder), sh_word(folder / KEEP)))
        code, stderr = self.build(path_prefix=str(bin_dir))
        self.assertTrue(folder.is_dir(), "the stand-in cmp never made the folder")
        self.assertNotEqual(code, 0, stderr)
        self.assertEqual(snapshot(folder), {KEEP: KEEP_TEXT}, "the build moved into, or changed, %s" % folder)
        self.assertEqual(outputs(self.dist), [], "dist/ holds %r" % outputs(self.dist))

    def test_work_folder_moved_before_moves_fails(self):
        """A stand-in cmp, after its last call, moves the work folder into a
        folder outside the clone. The first move fails, since its source is
        no longer at the path that mktemp gave; the moved folder holds src/
        and the 4 staged files, and dist/ holds no output and no work
        folder."""
        bin_dir, log = self.trap_stand_ins()
        outside = self.outside("moved-work-parent")
        self.last_cmp(Path(bin_dir), "%s \"$(cat %s)\" %s || exit 1\n"
                      % (sh_word(self.real("mv")), sh_word(Path(bin_dir) / "first-work-folder"),
                         sh_word(str(outside) + "/")))
        code, stderr = self.build(path_prefix=bin_dir)
        self.assertNotEqual(code, 0, stderr)
        entries = sorted(outside.iterdir())
        self.assertEqual(len(entries), 1, "the outside folder holds %r" % entries)
        self.assertEqual(entries[0].name, self.work_folder(log).name)
        self.assertEqual(sorted(p.name for p in entries[0].iterdir()), sorted(self.names + ["src"]))
        self.assertEqual(outputs(self.dist), [], "dist/ holds %r" % outputs(self.dist))

    def test_relative_invocation_ignores_cdpath(self):
        """A good build started as `bash tools/release-package.sh` in the
        root of the clone, with CDPATH naming a folder outside the clone
        that holds tools/ and dist/cleanlanguage.zip, exits 0 and writes the
        4 outputs in the dist/ of the clone; the outside folder is
        unchanged. A cd to tools/.. that followed CDPATH would enter the
        outside folder, and the first removal would remove its zip."""
        decoy = self.outside("cdpath-decoy")
        (decoy / "tools").mkdir()
        (decoy / "dist").mkdir()
        (decoy / "dist" / "cleanlanguage.zip").write_bytes(b"a reader's file\n")
        before = snapshot(decoy)
        code, stderr = self.run_packager(Path("tools") / "release-package.sh", extra={"CDPATH": str(decoy)})
        self.assertEqual(snapshot(decoy), before, "the build changed the folder that CDPATH names")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)

    def builtin_stand_in(self, name: str, body: str) -> tuple:
        """A stand-in for the bash builtin name, as an environment entry that
        exports to the build's bash a function of that name, which bash runs
        in place of its builtin; body is the text of the function, in which
        %(log)s gives the path of its log as 1 shell word. Return the entry
        and the log, which does not exist yet."""
        log = Path(self.tmp.name) / ("%s-calls.log" % name)
        if log.exists():
            log.unlink()
        return {"BASH_FUNC_%s%%%%" % name: body % {"log": sh_word(log)}}, log

    def kill_not_knowing(self, names: tuple) -> tuple:
        """A stand-in kill that writes 1 record of the arguments of each call
        to its log; at `kill -l NAME` for a NAME of names it then fails with
        a message, as bash does for a name that it does not know, and it
        passes every other call to the builtin. Return the entry and the
        log."""
        return self.builtin_stand_in("kill", (
            "() { printf '%%s\\000' \"$#\" \"$@\" >> %(log)s; "
            "if [ \"$1\" = -l ]; then case \"$2\" in " + "|".join(names) + ") "
            "printf 'kill: %%s: invalid signal specification\\n' \"$2\" >&2; return 1 ;; esac; fi; "
            "builtin kill \"$@\"; }"))

    def recording_trap(self) -> tuple:
        """A stand-in trap that writes 1 record of each call to its log, the
        shell options that BASHOPTS lists at that call and then each
        argument, and passes the call to the builtin. Return the entry and
        the log."""
        return self.builtin_stand_in("trap", (
            "() { printf '%%s\\000' \"$(($# + 1))\" \"$BASHOPTS\" \"$@\" >> %(log)s; "
            "builtin trap \"$@\"; }"))

    def shopt_not_knowing(self, name: str) -> tuple:
        """A stand-in shopt that writes 1 record of the arguments of each call
        to its log; at a call that names the option name it then fails with
        a message, as bash does for an option that it does not know, once it
        has passed the call without that name to the builtin when the call
        names another option, and it passes every other call to the builtin.
        Return the entry and the log."""
        return self.builtin_stand_in("shopt", (
            "() { printf '%%s\\000' \"$#\" \"$@\" >> %(log)s; "
            "local a named= rest=(); "
            "for a in \"$@\"; do case \"$a\" in " + name + ") ;; -*) rest+=(\"$a\") ;; "
            "*) rest+=(\"$a\"); named=1 ;; esac; done; "
            "if [ \"${#rest[@]}\" -lt \"$#\" ]; then "
            "printf 'shopt: %%s: invalid shell option name\\n' " + name + " >&2; "
            "if [ -n \"$named\" ]; then builtin shopt \"${rest[@]}\"; fi; return 1; fi; "
            "builtin shopt \"$@\"; }"))

    def assert_traps(self, log: Path, expected: list):
        """Assert that the build, through the stand-in trap whose log is
        given, trapped each signal number of expected, and no other, once
        with the action exit 128 plus that number, and that its exit trap
        then ignored exactly those numbers."""
        calls = [fields[1:] for fields in self.records(log)]
        exits = [args for args in calls if args and args[0].startswith("exit ")]
        for args in exits:
            self.assertEqual(len(args), 2, "the build set the trap %r" % args)
            self.assertEqual(args[0], "exit %d" % (128 + int(args[1])), "the build set the trap %r" % args)
        self.assertEqual(sorted(int(args[1]) for args in exits), expected,
                         "the build trapped %r" % [args[1] for args in exits])
        ignored = [sorted(int(n) for n in args[1:]) for args in calls if args and args[0] == ""]
        self.assertEqual(ignored, [expected], "the exit trap ignored %r" % ignored)

    def test_unknown_signal_names_skipped(self):
        """With a stand-in trap that records each call, a good build traps
        each signal of TRAPPED_SIGNALS with exit 128 plus its number, and its
        exit trap ignores the same signals. With a stand-in kill as well that
        records each call and does not know 1 name of SIGNAL_NAMES at a time,
        and then the names of NON_LINUX_NAMES together, a good build exits 0,
        writes the 4 outputs and keeps the plants; each call of the stand-in
        kill was `kill -l NAME` for a NAME of SIGNAL_NAMES, and 1 or more of
        them for a name that it does not know; and the build traps, and its
        exit trap ignores, each signal of TRAPPED_SIGNALS but that of a name
        that it does not know and, when RTMIN or RTMAX is among those names,
        the real-time range, so an unknown name makes the build drop no other
        signal. With NON_LINUX_NAMES unknown and the stand-in trap, SIGSYS,
        which comes after STKFLT and PWR in the packager's list, still ends
        a build with 159 while a stand-in mv holds the move of the .sha256
        files, and the build leaves no output; each call of the stand-in
        kill was `kill -l NAME` for a NAME of SIGNAL_NAMES, the build asked
        it for SYS after 1 or more names that it does not know, and the
        build trapped, and its exit trap ignored, each signal of
        TRAPPED_SIGNALS but SIGSTKFLT, SIGPWR and the real-time range, so a
        packager that drops SIGSYS, or asks for no unknown name before SYS,
        fails this subtest."""
        with self.subTest(unknown="none"):
            self.setUp()
            extra, trap_log = self.recording_trap()
            self.good_build(extra=extra)
            self.assert_traps(trap_log, sorted(TRAPPED_SIGNALS))
        for names in [(name,) for name in SIGNAL_NAMES] + [NON_LINUX_NAMES]:
            with self.subTest(unknown=" ".join(names)):
                self.setUp()
                extra, log = self.kill_not_knowing(names)
                trap_entry, trap_log = self.recording_trap()
                extra.update(trap_entry)
                self.good_build(extra=extra)
                asked = self.records(log)
                self.assertTrue(all(len(a) == 2 and a[0] == "-l" and a[1] in SIGNAL_NAMES for a in asked),
                                "the stand-in kill recorded %r" % asked)
                self.assertTrue(any(a[1] in names for a in asked),
                                "the build never asked the stand-in kill for %s: %r" % (", ".join(names), asked))
                self.assert_traps(trap_log, trapped_without(names))
        with self.subTest(unknown=" ".join(NON_LINUX_NAMES), signal="SIGSYS"):
            self.setUp()
            extra, log = self.kill_not_knowing(NON_LINUX_NAMES)
            trap_entry, trap_log = self.recording_trap()
            extra.update(trap_entry)
            self.assert_signal_ends_build(signal.SIGSYS, 128 + signal.SIGSYS, extra=extra)
            asked = self.records(log)
            self.assertTrue(all(len(a) == 2 and a[0] == "-l" and a[1] in SIGNAL_NAMES for a in asked),
                            "the stand-in kill recorded %r" % asked)
            names = [a[1] for a in asked]
            self.assertIn("SYS", names, "the build never asked the stand-in kill for SYS: %r" % names)
            self.assertTrue(set(names[:names.index("SYS")]) & set(NON_LINUX_NAMES),
                            "the build asked the stand-in kill for no unknown name before SYS: %r" % names)
            self.assert_traps(trap_log, trapped_without(NON_LINUX_NAMES))

    def test_unknown_shell_options_skipped(self):
        """For each option of SHELL_OPTIONS_OFF, with a stand-in shopt that
        records each call and does not know that option, with the other 4
        turned on through BASHOPTS, and with a stand-in trap that records the
        shell options at each call, a good build exits 0, writes the 4
        outputs and keeps the plants; the build asked the stand-in shopt
        about that option; and at each trap that it set, its shell options
        held dotglob and none of SHELL_OPTIONS_OFF, so an option that the
        shell does not know leaves no other turned on."""
        for name in SHELL_OPTIONS_OFF:
            with self.subTest(unknown=name):
                self.setUp()
                extra, log = self.shopt_not_knowing(name)
                trap_entry, trap_log = self.recording_trap()
                extra.update(trap_entry)
                extra["BASHOPTS"] = ":".join(o for o in SHELL_OPTIONS_OFF if o != name)
                self.good_build(extra=extra)
                asked = self.records(log)
                self.assertTrue(any(name in args for args in asked),
                                "the build never asked the stand-in shopt about %s: %r" % (name, asked))
                options = [fields[0] for fields in self.records(trap_log)]
                self.assertTrue(options, "the build set no trap")
                for held in options:
                    self.assertIn("dotglob", held.split(":"), "a trap was set with the options %s" % held)
                    self.assertEqual(set(held.split(":")) & set(SHELL_OPTIONS_OFF), set(),
                                     "a trap was set with the options %s" % held)

    @staticmethod
    def end_left_group(pid_file: Path):
        """End with SIGKILL the process group whose number pid_file holds,
        that of a process that left the process group of a build, if it
        still runs."""
        try:
            os.killpg(int(pid_file.read_text().strip()), signal.SIGKILL)
        except (OSError, ValueError):
            pass

    def test_build_past_its_limit_ends_within_bound(self):
        """A build by a stand-in script, with a time limit of 1 second, that
        starts in its own process group a child that writes a file after 3
        seconds, starts under job control (set -m) a process that leaves
        that group and keeps the build's output open, and then sleeps,
        makes run_packager raise the timeout within the limit plus twice
        REAP_TIMEOUT and 5 seconds, long before that process ends; the
        child never writes its file, since the test ended the build's
        process group with SIGKILL. A wait for the output with no bound
        would last until that process ends, and this case would fail."""
        folder = self.outside("timeout-build")
        late, pid_file, script = folder / "late", folder / "left-group", folder / "build.sh"
        limit = 1
        bound = limit + 2 * REAP_TIMEOUT + 5
        script.write_bytes(os.fsencode("(sleep 3; : > %s) &\n"
                                       "set -m\n"
                                       "sleep %d &\n"
                                       "printf '%%s\\n' \"$!\" > %s\n"
                                       "set +m\n"
                                       "sleep %d\n" % (sh_word(late), bound + 30, sh_word(pid_file), bound + 30)))
        self.addCleanup(self.end_left_group, pid_file)
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_packager(script, timeout=limit)
        elapsed = time.monotonic() - start
        self.assertTrue(pid_file.exists(), "the build never started the process that leaves its group")
        self.assertLess(elapsed, bound, "the timeout was raised after %.1f seconds" % elapsed)
        time.sleep(max(0.0, 4 - elapsed))
        self.assertFalse(late.exists(), "a child in the build's process group outlived the timeout")


class TraceReaderTests(unittest.TestCase):
    """Case 27: the reader of the trace of cases 16 and 17, on traces that
    the test writes in the form of strace -f -qq -xx -y; no build runs, and
    strace is not needed."""

    CLONE = "100   clone(child_stack=NULL, flags=CLONE_CHILD_CLEARTID|CLONE_CHILD_SETTID|SIGCHLD"
    FORK = CLONE + ", child_tidptr=0x7f0a) = 101"
    SHARED = ("100   clone(child_stack=0x7f0b, flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD"
              "|CLONE_SYSVSEM, parent_tid=[101], tls=0x7f0c, child_tidptr=0x7f0d) = 101")
    # The start of a call by process 100 of each name of FORKING_CALLS, to
    # which a trace adds the end of the call.
    MAKERS = {"clone": CLONE,
              "clone3": "100   clone3({flags=CLONE_VM|CLONE_VFORK, exit_signal=SIGCHLD, stack=0x7f0e,"
                        " stack_size=0x9000}, 88",
              "fork": "100   fork(", "vfork": "100   vfork("}

    def made(self, form: str, name: str, *children: str, pid: int = 100) -> list:
        """The lines of the call of MAKERS with the name name, made by
        process pid, in the form form of MADE: the lines of that form of
        CUT_SHORT, or for "ended as unavailable" the call with
        ) = ? <unavailable>, with children, the lines of other processes,
        in place of OTHER, or last where the form does not place it."""
        return self.written(form, name, self.MAKERS[name][len("100   "):], *children, pid=pid)

    def written(self, form: str, name: str, call: str, *children: str, pid: int) -> list:
        """The lines of call, the start of a call with the name name, made
        by process pid, in the form form of MADE, as made writes them."""
        lines = (["{call}) = ? <unavailable>"] if form == "ended as unavailable"
                 else list(self.CUT_SHORT[form]))
        if self.OTHER not in lines:
            lines.append(self.OTHER)
        found = []
        for line in lines:
            found += children if line is self.OTHER else ["%d   %s" % (pid, line.format(call=call, name=name))]
        return found

    def chained(self, form: str, name: str, count: int, *children: str) -> list:
        """The lines of count calls of MAKERS with the name name, in the
        form form of MADE, by processes 100 to 99 plus count, after lines
        in which process 100 makes each of the others by clone; each call
        is written as made writes it, with the lines of the call of the
        next process in place of children, and the last with children."""
        lines = list(children)
        for pid in range(99 + count, 99, -1):
            lines = self.made(form, name, *lines, pid=pid)
        return ["%s, child_tidptr=0x7f0a) = %d" % (self.CLONE, pid) for pid in range(101, 100 + count)] + lines

    # The start of a call that makes a process, by any process, for each
    # name of MAKERS, and for clone and clone3 also with CLONE_FS.
    CUTTERS = {**{name: start[len("100   "):] for name, start in MAKERS.items()},
               "clone with CLONE_FS": ("clone(child_stack=0x7f0b, flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND"
                                       "|CLONE_THREAD|CLONE_SYSVSEM, parent_tid=[0], tls=0x7f0c, child_tidptr=0x7f0d"),
               "clone3 with CLONE_FS": ("clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD"
                                        "|CLONE_SYSVSEM, exit_signal=0, stack=0x7f0e, stack_size=0x9000}, 88")}
    # The processes that make a call of CUTTERS that strace cut short in a
    # trace of allowance_trace.
    OWNERS = ("a process whose folder is known", "a process whose folder is not known", "a process with no maker")
    # The kinds of the first call of a process with no maker in a trace of
    # allowance_trace: an unread call, and each name of TRACED_CALLS, with
    # clone and clone3 also with CLONE_FS.
    FIRST_KINDS = ("an unread call", *(name for name in TRACED_CALLS if name not in FORKING_CALLS), *CUTTERS)

    @staticmethod
    def orders(calls: int, processes: int) -> list:
        """Every order, as a string of C for a call that strace cut short
        and N for a process with no maker, with at most calls C, at most
        processes N and at least 1 N, in which each N but the last finds a
        C before it that no earlier N used."""
        found = []
        for length in range(1, calls + processes + 1):
            for bits in range(2 ** length):
                order = "".join("CN"[bits >> index & 1] for index in range(length))
                if order.count("C") > calls or not 0 < order.count("N") <= processes:
                    continue
                left = 0
                for index, step in enumerate(order):
                    left += 1 if step == "C" else -1
                    if left < 0 and index < length - 1:
                        break
                else:
                    found.append(order)
        return found

    def first_call(self, kind: str, pid: int) -> tuple:
        """(start, name, paths) for the first call of the kind kind of
        FIRST_KINDS by process pid: the start of the call, to which a trace
        adds its end, its name, and the absolute paths that it removes or
        replaces when it is not refused."""
        path, other = "/clone/%d" % pid, "/clone/%d.new" % pid
        if kind in self.CUTTERS:
            return self.CUTTERS[kind], kind.split()[0], []
        starts = {"an unread call": (TRACE_UNREAD, []),
                  "unlink": ("unlink(%s" % self.hexed(path), [path]),
                  "unlinkat": ("unlinkat(AT_FDCWD</clone>, %s, 0" % self.hexed(path), [path]),
                  "rmdir": ("rmdir(%s" % self.hexed(path), [path]),
                  "rename": ("rename(%s, %s" % (self.hexed(other), self.hexed(path)), [other, path]),
                  "renameat": ("renameat(AT_FDCWD</clone>, %s, AT_FDCWD</clone>, %s"
                               % (self.hexed(other), self.hexed(path)), [other, path]),
                  "renameat2": ("renameat2(AT_FDCWD</clone>, %s, AT_FDCWD</clone>, %s, RENAME_NOREPLACE"
                                % (self.hexed(other), self.hexed(path)), [other, path]),
                  "chdir": ("chdir(%s" % self.hexed("/clone/sub"), []),
                  "fchdir": ("fchdir(3</clone/sub>", [])}
        start, paths = starts[kind]
        return start, "???" if kind == "an unread call" else kind, paths

    def allowance_trace(self, order: str, cut: tuple, first: tuple) -> tuple:
        """(lines, error, paths) for order, a string of orders: the lines
        of a trace, and what the rule of 1 process with no maker for each
        call of a maker that strace cut short gives for it: the error that
        names the first process that the rule refuses, or None and the
        absolute paths that the trace removes or replaces, in order.
        Process 100 enters /clone by chdir and then makes by clone each
        process that makes a C or the clone before it, and the thread
        below. Each C is a call of the name of CUTTERS that cut, (name,
        form, owner), gives, in the form form of MADE, by a process of the
        kind owner of OWNERS: 1 that process 100 made; 1 that process 100
        made with CLONE_FS, after which a thread that it made with
        CLONE_FS starts a chdir that strace detached from, so that their
        shared folder is not known; or 1 with no maker, after a clone by a
        process that process 100 made that strace detached from, whose
        first call removes an absolute path.
        Each N is a process with no maker whose first call is of the kind
        of FIRST_KINDS that first, (kind, result), gives, with the result
        result: done, failed, or a form of MADE. Each call is written with
        the lines that follow it in place of OTHER."""
        name, form, owner = cut
        kind, result = first
        lines, steps, pid = ["100   chdir(%s) = 0" % self.hexed("/clone")], [], 101
        for step in order:
            if step == "N":
                steps.append((step, pid, None))
                pid += 1
            elif owner == self.OWNERS[2]:
                lines.append("100   %s) = %d" % (self.CUTTERS["clone"], pid))
                steps.append((step, pid + 1, pid))
                pid += 2
            else:
                lines.append("100   %s) = %d" % (self.CUTTERS["clone" if owner == self.OWNERS[0]
                                                                else "clone with CLONE_FS"], pid))
                steps.append((step, pid, None))
                pid += 1
        if owner == self.OWNERS[1] and "C" in order:
            lines += ["100   %s) = %d" % (self.CUTTERS["clone with CLONE_FS"], pid),
                      "%d   chdir(%s <detached ...>" % (pid, self.hexed("sub"))]
        left, error, paths = 0, None, []
        for step, pid, before in steps:
            left += before is not None
            if (step == "N" or before is not None) and not left:
                error = "the trace shows process %d, which no traced call made" % pid
                break
            left -= step == "N" or before is not None
            if step == "C":
                left += 1
                paths += [] if before is None else ["/clone/%d" % pid]
            else:
                paths += [] if result == "failed" else self.first_call(kind, pid)[2]
                left += kind in self.CUTTERS and result in self.MADE
        ends = {"done": ") = 0", "failed": ") = -1 ENOENT (No such file or directory)"}
        if kind in self.CUTTERS:
            ends = {"done": ") = %d", "failed": ") = -1 EAGAIN (Resource temporarily unavailable)"}
        elif kind == "fchdir":
            ends["failed"] = ") = -1 EBADF (Bad file descriptor)"
        rest = []
        for step, pid, before in reversed(steps):
            if step == "C":
                rest = self.written(form, name.split()[0], self.CUTTERS[name], *rest, pid=pid)
                if before is not None:
                    rest = self.written("detached", "clone", self.CUTTERS["clone"],
                                        "%d   unlink(%s) = 0" % (pid, self.hexed("/clone/%d" % pid)), *rest, pid=before)
            else:
                start, call, _ = self.first_call(kind, pid)
                if result in ends:
                    rest = ["%d   %s%s" % (pid, start, ends[result].replace("%d", str(900 + pid)))] + rest
                else:
                    rest = self.written(result, call, start, *rest, pid=pid)
        return lines + rest, error, paths

    @staticmethod
    def hexed(path: str) -> str:
        """path as strace -xx gives a string: each byte as a hex escape."""
        return '"%s"' % "".join("\\x%02x" % b for b in os.fsencode(path))

    # The arguments of a call of each name of REMOVING_CALLS, by their names
    # in the manual pages of the calls, and the value that the test gives
    # each argument that is neither a path nor a descriptor. The test
    # derives from these, and not from REMOVING_CALLS, which a mutant of the
    # reader may change, each path of each call and the descriptor that it
    # is read against, by the descriptor rule: a path is an argument whose
    # name holds "path", and it is read against the argument just before
    # it when that argument's name ends in "dirfd", and otherwise against
    # the folder of its process.
    SIGNATURES = {"unlink": ("pathname",), "rmdir": ("pathname",), "unlinkat": ("dirfd", "pathname", "flags"),
                  "rename": ("oldpath", "newpath"), "renameat": ("olddirfd", "oldpath", "newdirfd", "newpath"),
                  "renameat2": ("olddirfd", "oldpath", "newdirfd", "newpath", "flags")}
    FLAGS = {"unlinkat": "0", "renameat2": "RENAME_NOREPLACE"}
    # The ordinal of each path of a call, by its place among the paths.
    PATH_ORDINALS = ("first", "second")
    # The kinds of process, and the descriptors with no path that the test
    # can use, at which the coverage subtests of the folder test and the
    # refusal test want a trace for each path of each name of
    # REMOVING_CALLS. They are given here, apart from the tables that write
    # the traces, so that a kind or a descriptor dropped from such a table
    # is still wanted.
    PROCESS_KINDS = ("the first process", "a process that a call made", "a process with no maker")
    UNUSABLE_DESCRIPTORS = ("no path", "a relative path", "the path of a removed folder")

    @classmethod
    def removing_paths(cls, name: str) -> list:
        """(descriptor, position) for each path of a call of name, in
        order, as SIGNATURES and the descriptor rule give them; descriptor
        is None for a path that is read against the folder of its
        process."""
        arguments = cls.SIGNATURES[name]
        return [(index - 1 if index and arguments[index - 1].endswith("dirfd") else None, index)
                for index, argument in enumerate(arguments) if "path" in argument]

    def removing_call(self, name: str, given: list) -> str:
        """The start of a call of name, to which a trace adds its end, in
        which the paths of removing_paths take, in order, the (token, path)
        pairs of given: token is the text of the descriptor argument, or
        None for a path with no descriptor, and path is the path, which the
        call gives in hex escapes. Each other argument takes its value in
        FLAGS."""
        arguments = {}
        for (descriptor, position), (token, path) in zip(self.removing_paths(name), given, strict=True):
            arguments[position] = self.hexed(path)
            if descriptor is not None:
                arguments[descriptor] = token
        return "%s(%s" % (name, ", ".join(arguments.get(index, self.FLAGS.get(name))
                                           for index in range(len(self.SIGNATURES[name]))))

    @staticmethod
    def removal_coordinates(forms) -> set:
        """Each (name, index, key) for the path at index of each name of
        REMOVING_CALLS and each key that forms, given whether
        REMOVING_CALLS reads that path against a descriptor, gives for it.
        The coverage subtests compare these with the coordinates of the
        traces that they hold, so that a name, path or descriptor form of
        REMOVING_CALLS with no trace fails them."""
        return {(name, index, key) for name, paths in REMOVING_CALLS.items()
                for index, (descriptor, _) in enumerate(paths) for key in forms(descriptor is not None)}

    def removals(self, *lines: str) -> tuple:
        """traced_removals of a trace that holds lines, whose first process
        starts in /clone."""
        folder = tempfile.TemporaryDirectory(prefix=TEMP_PREFIX)
        self.addCleanup(folder.cleanup)
        log = Path(folder.name) / "calls.trace"
        log.write_bytes("".join(line + "\n" for line in lines).encode("latin-1"))
        return traced_removals(log, "/clone")

    # The forms in which strace cuts a call short, as the lines of the
    # process of the call after the start of the call, given as {call},
    # which the test puts in place of the call's name and arguments;
    # cut_short writes them as lines of process 101, and made as lines of
    # process pid. OTHER stands for a line of another process, which comes
    # last where a form does not place it.
    OTHER = None
    CUT_SHORT = {
        "detached": ("{call} <detached ...>",),
        "unfinished, never resumed": ("{call} <unfinished ...>", OTHER),
        "unfinished, then killed": ("{call} <unfinished ...>", "+++ killed by SIGKILL +++", OTHER),
        "unfinished, killed after another line": ("{call} <unfinished ...>", OTHER, "+++ killed by SIGKILL +++"),
        "unfinished, exited after another line": ("{call} <unfinished ...>", OTHER, "+++ exited with 0 +++"),
        "resumed with ?": ("{call} <unfinished ...>", OTHER, "<... {name} resumed>) = ?",
                           "+++ killed by SIGKILL +++"),
        "resumed with ? after <unfinished ...>": ("{call} <unfinished ...>", OTHER,
                                                  "<... {name} resumed> <unfinished ...>) = ?"),
        "ended with ?": ("{call}) = ?", "+++ killed by SIGKILL +++"),
        "ended unfinished with ?": ("{call} <unfinished ...>) = ?",),
    }
    # The forms in which made writes a call of MAKERS: each form of
    # CUT_SHORT, and "ended as unavailable", the form ") = ? <unavailable>",
    # which the reader reads as a call cut short with the result ?.
    MADE = (*CUT_SHORT, "ended as unavailable")

    def cut_short(self, form: str, name: str, call: str) -> list:
        """The lines of process 101 for the form of CUT_SHORT, with OTHER as
        a removal by process 100 of /clone/dist/old.zip."""
        other = "100   unlinkat(AT_FDCWD</clone>, %s, 0) = 0" % self.hexed("dist/old.zip")
        lines = list(self.CUT_SHORT[form])
        if self.OTHER not in lines:
            lines.append(self.OTHER)
        return [other if line is self.OTHER else "101   " + line.format(call=call, name=name) for line in lines]

    def test_trace_reads_calls_cut_short_by_an_ended_process(self):
        """In each form of CUT_SHORT, a call that strace could not read at
        the entry where its process ended, TRACE_UNREAD or a name with (
        and no argument, whatever the name, removes nothing, and the
        removals before it in its process and next to it in another are
        still reported; fork and vfork with no argument are read as the
        call; and a removal that strace cut short counts, as does 1 read
        with its arguments that ends with the result ? and the note
        <unavailable>, in its line or in its resumption."""
        before = (101, "rmdir", "/clone/work")
        other = (100, "unlinkat", "/clone/dist/old.zip")
        calls = [(call[:-1], call, [before, other])
                 for call in (TRACE_UNREAD, "unlinkat(", "chdir(", "getpid(", "fork(", "vfork(")]
        calls.append(("unlink", "unlink(" + self.hexed("y"), [before, (101, "unlink", "/clone/y"), other]))
        for name, call, expected in calls:
            for form in self.CUT_SHORT:
                with self.subTest(call=call, form=form):
                    removed, _ = self.removals(self.FORK, "101   rmdir(%s) = 0" % self.hexed("work"),
                                               *self.cut_short(form, name, call))
                    self.assertEqual(removed, expected)
        with self.subTest("cut short"):
            removed, _ = self.removals(
                self.FORK,
                "101   unlinkat(AT_FDCWD</clone>, %s, AT_REMOVEDIR%s" % (self.hexed("a"), TRACE_DETACHED),
                "100   rename(%s, %s) = ?" % (self.hexed("b"), self.hexed("/c")))
            self.assertEqual(removed, [(101, "unlinkat", "/clone/a"), (100, "rename", "/clone/b"),
                                       (100, "rename", "/c")])
        with self.subTest("ended with ? and <unavailable>"):
            removed, _ = self.removals(self.FORK, "101   unlink(%s) = ? <unavailable>" % self.hexed("y"))
            self.assertEqual(removed, [(101, "unlink", "/clone/y")])
        with self.subTest("resumed with ? and <unavailable>"):
            removed, _ = self.removals(self.FORK, "101   unlink(%s <unfinished ...>" % self.hexed("y"),
                                       "100   rmdir(%s) = 0" % self.hexed("z"),
                                       "101   <... unlink resumed>) = ? <unavailable>")
            self.assertEqual(removed, [(101, "unlink", "/clone/y"), (100, "rmdir", "/clone/z")])

    def test_trace_reads_both_paths_of_renameat2(self):
        """renameat2 removes or replaces both of its paths, each read
        against the folder that its own descriptor names."""
        removed, _ = self.removals("100   renameat2(4</clone/source>, %s, 3</clone/dist>, %s, RENAME_NOREPLACE) = 0"
                                   % (self.hexed("a"), self.hexed("b")))
        self.assertEqual(removed, [(100, "renameat2", "/clone/source/a"), (100, "renameat2", "/clone/dist/b")])

    def test_trace_follows_the_folder_of_each_process(self):
        """A relative path is read against the folder of its process: a
        child that clone, fork or vfork makes without CLONE_FS starts in
        the current folder of its maker and does not follow a later change
        of it, and a thread made with CLONE_FS shares it; a descriptor
        other than AT_FDCWD gives the folder that strace -y names for it,
        and fchdir enters that folder; a chdir that strace could not read
        at entry changes no folder; an absolute path after a chdir that
        ends with the result ? and the note <unavailable> in a shared
        folder is read; a process that a clone, clone3, fork or vfork made
        is read by its absolute paths when strace cut that call short in
        any form of CUT_SHORT, or ended it with the result ? and the note
        <unavailable>, so that the call does not name the process; and so
        is 1 such process for each of 2, 3 or 4 such calls of the same
        name in the same form, and for each of a fork and a vfork that
        ended with the result ?. A fork or vfork that a line of its child
        interrupted and that is resumed with the id of that child is read
        as the call, so its maker goes on, and the child reads a relative
        path, before the resumption and after a chdir of its maker,
        against the folder that its maker had at the call. A process with
        no maker reads a relative path after it enters a folder by a chdir
        or fchdir whose result is 0, and against a descriptor, other than
        AT_FDCWD, whose path strace -y gives as absolute and not as that
        of a removed folder. At each path of a call of each name of
        REMOVING_CALLS, a relative path is read against the folder that
        its own descriptor names, against the folder of its process for
        AT_FDCWD, and against that folder where the path takes no
        descriptor, while each other path of the call is read by the same
        rule, in the first process after a chdir and in a process that it
        then made, and, against its own descriptor, in a process with no
        maker. The test derives each path, and the descriptor that it is
        read against, from SIGNATURES by the descriptor rule, not from
        REMOVING_CALLS, and a subtest fails if a name, a path or a
        descriptor form that REMOVING_CALLS gives has no such trace, in a
        kind of process above; it takes the descriptor forms and the kinds
        of process that it wants from a list of its own, not from the
        tables that write the traces."""
        unlink = "%d   unlink(" + self.hexed("x") + ") = 0"
        chdir = "100   chdir(%s) = 0" % self.hexed("sub")
        traces = {
            "a child made after a chdir of its maker": ((chdir, self.FORK, unlink % 101), "/clone/sub/x"),
            "a child made before a chdir of its maker": ((self.FORK, chdir, unlink % 101), "/clone/x"),
            "a thread that shares the folder of its maker": ((self.SHARED, chdir, unlink % 101), "/clone/sub/x"),
            "a child of vfork, shown before vfork returns":
                ((chdir, "100   vfork( <unfinished ...>", unlink % 101, "100   <... vfork resumed>) = 101"),
                 "/clone/sub/x"),
            "a descriptor": (("100   unlinkat(3</clone/sub>, %s, 0) = 0" % self.hexed("x"),), "/clone/sub/x"),
            "an fchdir": (("100   fchdir(3</clone/sub>) = 0", unlink % 100), "/clone/sub/x"),
            "a chdir that strace could not read, in a shared folder":
                ((self.SHARED, "101   chdir( <detached ...>", unlink % 100), "/clone/x"),
            "an absolute path in a child of a clone resumed with ? after its last argument":
                ((self.CLONE + " <unfinished ...>", "101   unlink(%s) = 0" % self.hexed("/clone/y"),
                  "100   <... clone resumed>, child_tidptr=0x7f0a) = ?"), "/clone/y"),
            "a child of fork, which takes no argument": ((chdir, "100   fork() = 101", unlink % 101), "/clone/sub/x"),
            "a child of fork made before a chdir of its maker": (("100   fork() = 101", chdir, unlink % 101), "/clone/x"),
            "a child of vfork made before a chdir of its maker":
                (("100   vfork() = 101", chdir, unlink % 101), "/clone/x"),
            "an absolute path after a chdir ended as unavailable in a shared folder":
                ((self.SHARED, "101   chdir(%s) = ? <unavailable>" % self.hexed("sub"),
                  "100   unlink(%s) = 0" % self.hexed("/clone/y")), "/clone/y"),
            "a relative path in a process with no maker after it enters a folder by chdir":
                (("100   fork() = ?", "101   chdir(%s) = 0" % self.hexed("/clone/sub"), unlink % 101), "/clone/sub/x"),
            "a relative path in a process with no maker after it enters a folder by fchdir":
                (("100   fork() = ?", "101   fchdir(3</clone/sub>) = 0", unlink % 101), "/clone/sub/x"),
            "a relative path against a descriptor in a process with no maker":
                (("100   fork() = ?", "101   unlinkat(3</clone/sub>, %s, 0) = 0" % self.hexed("x")), "/clone/sub/x"),
        }
        for name in self.MAKERS:
            for form in self.MADE:
                traces["an absolute path in a child of a %s in the form %s" % (name, form)] = (
                    self.made(form, name, "101   unlink(%s) = 0" % self.hexed("/clone/y")), "/clone/y")
        for label, (lines, path) in traces.items():
            with self.subTest(label):
                removed, _ = self.removals(*lines)
                self.assertEqual([removal[2] for removal in removed], [path])
        # A fork and a vfork that a line of their child interrupts, so that
        # the trace records that line between the start of the call and its
        # resumption with the id of the child; the child's relative paths,
        # before the resumption and after a chdir of its maker, are both
        # read against the folder that its maker had at the call.
        for name in ("fork", "vfork"):
            with self.subTest("a child of %s that a line of the child interrupted, resumed with 101, made before a "
                              "chdir of its maker" % name):
                removed, _ = self.removals("100   %s( <unfinished ...>" % name,
                                           "101   unlink(%s) = 0" % self.hexed("before"),
                                           "100   <... %s resumed>) = 101" % name, chdir, unlink % 101)
                self.assertEqual(removed, [(101, "unlink", "/clone/before"), (101, "unlink", "/clone/x")])
        for name in self.MAKERS:
            for form in self.MADE:
                with self.subTest("an absolute path in each child of 2 calls of %s in the form %s" % (name, form)):
                    removed, _ = self.removals(self.FORK, *self.made(form, name, *self.made(
                        form, name, "102   unlink(%s) = 0" % self.hexed("/clone/y"),
                        "103   unlink(%s) = 0" % self.hexed("/clone/z"), pid=101)))
                    self.assertEqual([removal[2] for removal in removed], ["/clone/y", "/clone/z"])
                for count in (3, 4):
                    paths = ["/clone/%d" % number for number in range(count)]
                    with self.subTest("an absolute path in each child of %d calls of %s in the form %s"
                                      % (count, name, form)):
                        removed, _ = self.removals(*self.chained(form, name, count, *(
                            "%d   unlink(%s) = 0" % (100 + count + number, self.hexed(path))
                            for number, path in enumerate(paths))))
                        self.assertEqual([removal[2] for removal in removed], paths)
        with self.subTest("an absolute path in each child of a fork and a vfork that ended with ?"):
            removed, _ = self.removals(self.FORK, "100   fork() = ?", "101   vfork() = ?",
                                       "102   unlink(%s) = 0" % self.hexed("/clone/y"),
                                       "103   unlink(%s) = 0" % self.hexed("/clone/z"))
            self.assertEqual([removal[2] for removal in removed], ["/clone/y", "/clone/z"])
        # At each path of a call of each name of REMOVING_CALLS, as
        # removing_paths gives it, a relative path against its own
        # descriptor, against AT_FDCWD or, where the path takes no
        # descriptor, with none, while each other path of the call is a
        # relative path against its own descriptor, or with none where it
        # takes none; in process 100 after it enters /clone/sub by chdir and
        # in a child that it then makes, and, against its own descriptor, in
        # a process with no maker, where no other path of the call needs the
        # folder of its process. Each descriptor names a folder of its own,
        # and AT_FDCWD is given as AT_FDCWD</clone>, not the folder of its
        # process, so that a path read against any folder but the one that
        # the rule gives gives another result.
        processes = {"the first process": ([chdir], 100), "a process that a call made": ([chdir, self.FORK], 101),
                     "a process with no maker": (["100   fork() = ?"], 101)}
        held = set()
        for name in self.SIGNATURES:
            paths = self.removing_paths(name)
            for index, (descriptor, _) in enumerate(paths):
                for form in (("against its own descriptor", "against AT_FDCWD") if descriptor is not None
                             else ("with no descriptor",)):
                    for process, (before, pid) in processes.items():
                        given, expected = [], []
                        for other, (other_descriptor, position) in enumerate(paths):
                            path = "p%d" % position
                            if other_descriptor is not None and (other != index
                                                                 or form == "against its own descriptor"):
                                folder = "/clone/fd%d" % (3 + other_descriptor)
                                given.append(("%d<%s>" % (3 + other_descriptor, folder), path))
                            else:
                                folder = None if process == "a process with no maker" else "/clone/sub"
                                given.append((None if other_descriptor is None else "AT_FDCWD</clone>", path))
                            expected.append(None if folder is None else (pid, name, folder + "/" + path))
                        if None in expected:
                            continue
                        held.add((name, index, (form, process)))
                        with self.subTest("a relative path %s as the %s path of %s, in %s"
                                          % (form, self.PATH_ORDINALS[index], name, process)):
                            removed, _ = self.removals(*before, "%d   %s) = 0" % (pid, self.removing_call(name, given)))
                            self.assertEqual(removed, expected)
        # wanted takes its forms and kinds of process from lists of its own,
        # not from processes or the forms of the loop above, so that a form
        # or a kind dropped from those is still wanted.
        wanted = self.removal_coordinates(lambda has_descriptor: [
            (form, process)
            for form in (("against its own descriptor", "against AT_FDCWD") if has_descriptor
                         else ("with no descriptor",))
            for process in self.PROCESS_KINDS
            if process != "a process with no maker" or form == "against its own descriptor"])
        # wanted - held is empty when held has a trace for each coordinate
        # of REMOVING_CALLS; held may hold more.
        with self.subTest("a trace for each name of REMOVING_CALLS, each of its paths and each form of its descriptor"):
            self.assertEqual(sorted(wanted - held), [])

    def test_trace_refuses_what_it_cannot_read(self):
        """Each trace below ends the case. The labels name the condition of
        each; the reader functions are the full list of refusals. Each
        trace of pinned ends it with the error, whole, that pinned gives
        for it, and each check below that names an error checks it whole,
        so that no error with another text passes it; pinned holds the
        error of each raise statement of the reader functions. Where
        refusals share the text of their error, as the module docstring
        names, such a check does not show which of them ended the case. A
        call by process 100 after a call that strace detached from ends
        the case, for an unread call, a removal, a chdir, an fchdir and
        each name of MAKERS, and so does a resumption of a call of each of
        these under another name, a shorter 1 among them. A line of
        process 101 after a call that strace detached from, read or
        unread, after an unread call left unfinished, resumed with ? among
        them, and after an unread call that ended with the result ?, a
        signal and a second resumption among them, ends the case with the
        error that names that line, so that each way in which the reader
        finds that a process ended is checked with its error whole. After
        a chdir that ends with the result ? and the note <unavailable> in
        a shared folder, the case ends at the relative path that follows
        it, with the error that names that path.
        For a call of each name of MAKERS in each form of MADE, the case
        ends at a relative path of the process that the call made; at a
        second process after 1 such call whose process first enters a
        folder by chdir or fchdir, makes an unread call, makes a process
        by clone, clone3, fork or vfork, or makes an unlink, a chdir or a
        fork that fails; and at a third, fourth or fifth process after 2,
        3 or 4 such calls; each with the error that names that path or
        process. The docstring of
        test_trace_admits_1_process_with_no_maker_for_each_call_cut_short
        states the further traces that check that rule. A relative path
        against AT_FDCWD in a process with no maker ends the case, with
        the error that names that path, and 1 against a descriptor with
        no path, with a relative path or with that of a removed folder
        ends it, with the error that names that descriptor. So does such
        a path at each path of a call of each name of REMOVING_CALLS, with
        the result 0 or in each form of MADE, each other path of the call
        absolute: with no descriptor or against AT_FDCWD in a process with
        no maker, and, where the path takes a descriptor, against each
        such descriptor in the first process, in a process that a call
        made and in a process with no maker. The test derives each path,
        and the descriptor that it is read against, from SIGNATURES by the
        descriptor rule, not from REMOVING_CALLS, and a subtest fails if a
        name, a path or a descriptor form that REMOVING_CALLS gives has no
        such pin, in a kind of process and with a result above; it takes
        the descriptors, the kinds of process and the results that it
        wants from lists of its own, not from the tables that write the
        pins. A relative chdir whose result is 0 in a
        process with no maker ends the case with the error that names
        that path. A process with no maker ends the case, with the error
        that names it, after a call of each name of CUTTERS whose result
        is 0, and after an unread call of each name of TRACED_CALLS but
        fork and vfork, and of ???, in each form of CUT_SHORT. A rename
        with 1 argument, which fits no form that the reader takes, ends
        the case with an IndexError."""
        unlink = "100   unlink(%s) = 0" % self.hexed("x")
        later = "101   rmdir(%s) = 0" % self.hexed("z")
        cut = "101   unlink(%s <unfinished ...>) = " % self.hexed("y")
        opened = "101   unlink(%s <unfinished ...>" % self.hexed("y")
        traces = {
            "an unread call resumed":
                (self.FORK, "101   ???( <unfinished ...>", "101   <... ??? resumed>) = 0"),
            "an unread call with 2 spaces": (self.FORK, "101   ???(  <detached ...>"),
            "an unread call with 4 question marks": (self.FORK, "101   ????( <detached ...>"),
            "a chdir detached in a shared folder":
                (self.SHARED, "101   chdir(%s <detached ...>" % self.hexed("sub"), unlink),
            "a chdir ended in a shared folder": (self.SHARED, "101   chdir(%s) = ?" % self.hexed("sub"), unlink),
            "an fchdir detached in a shared folder":
                (self.SHARED, "101   fchdir(3</clone/sub> <detached ...>", unlink),
            "an fchdir ended in a shared folder": (self.SHARED, "101   fchdir(3</clone/sub>) = ?", unlink),
            "an unread call resumed with ? and <unavailable>":
                (self.FORK, "101   ???( <unfinished ...>", unlink, "101   <... ??? resumed>) = ? <unavailable>"),
            "a named unread call resumed":
                (self.FORK, "101   unlinkat( <unfinished ...>", unlink, "101   <... unlinkat resumed>) = 0"),
            "a named unread call ended as unavailable": (self.FORK, "101   unlinkat() = ? <unavailable>"),
            "a call cut short with a note": (self.FORK, cut + "? <unavailable>"),
            "a call resumed after <unfinished ...> with a result":
                (self.FORK, opened, unlink, "101   <... unlink resumed> <unfinished ...>) = 0"),
            "a call resumed with ? and a note after <unfinished ...>":
                (self.FORK, opened, unlink, "101   <... unlink resumed> <unfinished ...>) = ? <unavailable>"),
            "an unread call with an argument and a result": (self.FORK, "101   ???(0) = ?"),
            "a descriptor of a removed folder":
                ("100   unlinkat(3</clone/gone (deleted)>, %s, 0) = 0" % self.hexed("x"),),
            "an fchdir into a removed folder": ("100   fchdir(3</clone/gone (deleted)>) = 0",),
            "a descriptor with no path": ("100   unlinkat(3, %s, 0) = 0" % self.hexed("x"),),
            "a descriptor with a relative path": ("100   unlinkat(3<gone>, %s, 0) = 0" % self.hexed("x"),),
            "a process that no call made": (unlink, "101   unlink(%s) = 0" % self.hexed("/clone/y")),
            "a relative path in a child of a clone resumed with ? after its last argument":
                (self.CLONE + " <unfinished ...>", "101   unlink(%s) = 0" % self.hexed("x"),
                 "100   <... clone resumed>, child_tidptr=0x7f0a) = ?"),
            "2 processes after 1 clone that strace cut short":
                (self.CLONE + ", child_tidptr=0x7f0a) = ?", "101   unlink(%s) = 0" % self.hexed("/clone/y"),
                 "102   unlink(%s) = 0" % self.hexed("/clone/z")),
            "3 processes after a fork and a vfork that ended with ?":
                (self.FORK, "100   fork() = ?", "101   vfork() = ?", "102   unlink(%s) = 0" % self.hexed("/clone/y"),
                 "103   unlink(%s) = 0" % self.hexed("/clone/z"), "104   unlink(%s) = 0" % self.hexed("/clone/w")),
        }
        for name in self.MAKERS:
            for form in self.MADE:
                traces["2 processes after 1 %s in the form %s" % (name, form)] = self.made(
                    form, name, "101   unlink(%s) = 0" % self.hexed("/clone/y"),
                    "102   unlink(%s) = 0" % self.hexed("/clone/z"))
        for label, lines in traces.items():
            with self.subTest(label):
                with self.assertRaises(AssertionError):
                    self.removals(*lines)
        resumed = "101   <... unlink resumed>, 0) = 0"
        pinned = {
            "a path not in hex escapes":
                (('100   unlink("x") = 0',),
                 "the trace gives the path '\"x\"', which is not 1 whole string in hex escapes"),
            "a descriptor that the test cannot read":
                (("100   unlinkat(foo, %s, 0) = 0" % self.hexed("x"),),
                 "the trace gives the descriptor 'foo', which the test cannot read"),
            "a line with no process id":
                ((unlink, "unlink(%s) = 0" % self.hexed("y")),
                 "the trace holds a line that the test cannot read: %r" % ("unlink(%s) = 0" % self.hexed("y"))),
            "a call resumed under a shorter name":
                ((self.FORK, "101   unlinkat(AT_FDCWD</clone>, %s <unfinished ...>" % self.hexed("y"), unlink, resumed),
                 "the trace resumes a call that it did not start: %r" % resumed),
            "a call resumed under another name":
                ((self.FORK, opened, unlink, "101   <... rmdir resumed>) = 0"),
                 "the trace resumes a call that it did not start: %r" % "101   <... rmdir resumed>) = 0"),
            "an unread call resumed with ? under a name":
                ((self.FORK, "101   ???( <unfinished ...>", unlink, "101   <... unlink resumed>) = ?"),
                 "the trace resumes a call that it did not start: %r" % "101   <... unlink resumed>) = ?"),
            "a resumption with no call open":
                ((self.FORK, resumed), "the trace resumes a call that it did not start: %r" % resumed),
            "an unread call cut short while a call is open":
                ((self.FORK, opened, "101   ???( <unfinished ...>"),
                 "the trace starts a call of process 101 before it resumes the last"),
            "a call cut short while a call is open":
                ((self.FORK, opened, "101   rmdir(%s <unfinished ...>" % self.hexed("z")),
                 "the trace starts a call of process 101 before it resumes the last"),
            "an unread call while a call is open":
                ((self.FORK, opened, "101   ???( <detached ...>"),
                 "the trace starts a call of process 101 before it resumes the last"),
            "a call detached while a call is open":
                ((self.FORK, opened, "101   rmdir(%s <detached ...>" % self.hexed("z")),
                 "the trace starts a call of process 101 before it resumes the last"),
            "a trace with no call": (("100   +++ exited with 0 +++",), "the trace records no call"),
            "a call that the test did not ask strace for":
                (("100   openat(AT_FDCWD</clone>, %s, O_RDONLY) = 3" % self.hexed("x"),),
                 "the trace holds the call openat, which the test did not ask strace for"),
            "an unread call with a space after it":
                ((self.FORK, "101   ???( <detached ...> "),
                 "the trace holds a call that the test cannot read: %r" % "???( <detached ...> "),
            "an unread call with no parenthesis":
                ((self.FORK, "101   ??? <detached ...>"), "the trace holds a call that the test cannot read: '???'"),
            "an unread call with an argument":
                ((self.FORK, "101   ???(0 <detached ...>"), "the trace holds a call that the test cannot read: '???(0'"),
            "a call cut short with a result":
                ((self.FORK, cut + "0"),
                 "the trace gives a result for a call that it cut short: %r" % (cut[len("101   "):] + "0")),
            "a named unread call with a result":
                ((self.FORK, "101   unlinkat() = 0"),
                 "the trace gives a result for a call whose arguments strace could not read: 'unlinkat() = 0'"),
            "an fchdir into a descriptor with no path":
                (("100   fchdir(3) = 0",), "the trace gives the descriptor '3', with no path that the test can use"),
            "an fchdir into a descriptor with a relative path":
                (("100   fchdir(3<gone>) = 0",),
                 "the trace gives the descriptor '3<gone>', with no path that the test can use"),
        }
        # The lines of process 101, after the fork that makes it, that end
        # with a line after the call at which it ended: a call that strace
        # detached from, read or unread, an unread call left unfinished,
        # resumed with ? among them, and an unread call that ended with the
        # result ?. Each ends the case with the error that names its last
        # line.
        signal_line = "101   --- SIGCHLD {si_signo=SIGCHLD} ---"
        ended = {
            "a call after a detached unread call":
                ("101   ???( <detached ...>", "101   unlink(%s) = 0" % self.hexed("x")),
            "a call after an unfinished unread call":
                ("101   ???( <unfinished ...>", "101   unlink(%s) = 0" % self.hexed("x")),
            "a signal after a detached unread call": ("101   ???( <detached ...>", signal_line),
            "a call after a detached call": ("101   unlink(%s <detached ...>" % self.hexed("y"), later),
            "an unread call resumed with ? 2 times":
                ("101   ???( <unfinished ...>", unlink, "101   <... ??? resumed>) = ?", "101   <... ??? resumed>) = ?"),
            "a call after an unread call resumed with ?":
                ("101   ???( <unfinished ...>", unlink, "101   <... ??? resumed>) = ?", later),
            "a call after an unread call that ended": ("101   ???() = ?", later),
            "a signal after an unfinished unread call": ("101   ???( <unfinished ...>", signal_line),
            "a call after a named unread call": ("101   unlinkat( <unfinished ...>", later),
            "a call after a named unread call that ended": ("101   getpid() = ?", later),
        }
        for label, lines in ended.items():
            pinned[label] = ((self.FORK, *lines),
                             "the trace shows process 101 after the call at which it ended: %r" % lines[-1])
        # The start of a call by process 100 of an unread call, a removal, a
        # chdir, an fchdir and each name of MAKERS, each with another name
        # under which a resumption of it ends the case.
        calls = {"an unread call": ("???(", "unlink"), "a named unread call": ("unlinkat(", "unlink"),
                 "a renameat2": ("renameat2(4</clone/source>, %s, 3</clone/dist>, %s, RENAME_NOREPLACE"
                                 % (self.hexed("a"), self.hexed("b")), "renameat"),
                 "a chdir": ("chdir(%s" % self.hexed("sub"), "fchdir"), "an fchdir": ("fchdir(3</clone/sub>", "chdir")}
        others = {"clone": "clone3", "clone3": "clone", "fork": "vfork", "vfork": "fork"}
        for name, start in self.MAKERS.items():
            calls["a " + name] = (start[len("100   "):], others[name])
        after = "100   rmdir(%s) = 0" % self.hexed("z")
        for label, (start, other) in calls.items():
            pinned["a call after %s that strace detached from" % label] = (
                ("100   %s <detached ...>" % start, after),
                "the trace shows process 100 after the call at which it ended: %r" % after)
            pinned["%s resumed under the name %s" % (label, other)] = (
                ("100   %s <unfinished ...>" % start, "100   <... %s resumed>) = 0" % other),
                "the trace resumes a call that it did not start: %r" % ("100   <... %s resumed>) = 0" % other))
        relative = ("the trace gives the relative path 'x' in a current folder that it does not show, after a change "
                    "of folder or a making of a process that strace cut short")
        pinned["a chdir ended as unavailable in a shared folder"] = (
            (self.SHARED, "101   chdir(%s) = ? <unavailable>" % self.hexed("sub"), unlink), relative)
        pinned["a relative path against AT_FDCWD in a process with no maker"] = (
            ("100   fork() = ?", "101   unlinkat(AT_FDCWD</clone/sub>, %s, 0) = 0" % self.hexed("x")), relative)
        for label, token in (("no path", "3"), ("a relative path", "3<gone>"),
                             ("the path of a removed folder", "3</clone/gone (deleted)>")):
            pinned["a relative path against a descriptor with %s in a process with no maker" % label] = (
                ("100   fork() = ?", "101   unlinkat(%s, %s, 0) = 0" % (token, self.hexed("x"))),
                "the trace gives the descriptor %r, with no path that the test can use" % token)
        # For each path of a call of each name of REMOVING_CALLS, as
        # removing_paths gives it, the relative path x at that path, with no
        # descriptor or against AT_FDCWD in a process with no maker, and,
        # where the path takes a descriptor, against each descriptor whose
        # path strace -y does not give, gives as relative or gives as that
        # of a removed folder, in each kind of process; each other path of
        # the call is the absolute path /clone/y, against AT_FDCWD</clone>
        # where it takes a descriptor. The label of a pin at the first path
        # names no path. held records the coordinates of the pins, which a
        # subtest below compares with those of REMOVING_CALLS.
        y = self.hexed("/clone/y")
        processes = {"the first process": ([], 100), "a process that a call made": ([self.FORK], 101),
                     "a process with no maker": (["100   fork() = ?"], 101)}
        descriptors = {"no path": "3", "a relative path": "3<gone>",
                       "the path of a removed folder": "3</clone/gone (deleted)>"}
        results = ("the result 0", *self.MADE)
        held = set()
        for name in self.SIGNATURES:
            paths = self.removing_paths(name)
            for index, (descriptor, _) in enumerate(paths):
                cases = [("with no descriptor" if descriptor is None else "against AT_FDCWD", "AT_FDCWD</clone/sub>",
                          "a process with no maker", relative)]
                if descriptor is not None:
                    cases += [("against a descriptor with %s" % label, token, process,
                               "the trace gives the descriptor %r, with no path that the test can use" % token)
                              for label, token in descriptors.items() for process in processes]
                for where, token, process, error in cases:
                    before, pid = processes[process]
                    call = self.removing_call(name, [
                        (token if descriptor is not None else None, "x") if other == index
                        else (None if other_descriptor is None else "AT_FDCWD</clone>", "/clone/y")
                        for other, (other_descriptor, _) in enumerate(paths)])
                    place = "in %s" % name if index == 0 else "as the %s path of %s" % (self.PATH_ORDINALS[index], name)
                    for result in results:
                        lines = (["%d   %s) = 0" % (pid, call)] if result == "the result 0"
                                 else self.written(result, name, call, pid=pid))
                        pinned["a relative path %s %s %s, in %s" % (
                            where, place, "with the result 0" if result == "the result 0" else "in the form " + result,
                            process)] = ([*before, *lines], error)
                        held.add((name, index, (where, process, result)))
        # wanted takes its descriptors, kinds of process and results from
        # lists of its own, not from descriptors, processes or results, so
        # that an entry dropped from those is still wanted.
        wanted = self.removal_coordinates(lambda has_descriptor: [
            (where, process, result)
            for where, process in [("against AT_FDCWD" if has_descriptor else "with no descriptor",
                                    "a process with no maker"),
                                   *(("against a descriptor with %s" % label, process)
                                     for label in (self.UNUSABLE_DESCRIPTORS if has_descriptor else ())
                                     for process in self.PROCESS_KINDS)]
            for result in ("the result 0", *self.MADE)])
        pinned["a relative chdir with the result 0 in a process with no maker"] = (
            ("100   fork() = ?", "101   chdir(%s) = 0" % self.hexed("sub")), relative.replace("'x'", "'sub'"))
        for name, start in self.CUTTERS.items():
            pinned["a process with no maker after a %s whose result is 0" % name] = (
                ("100   %s) = 0" % start, "101   unlink(%s) = 0" % y),
                "the trace shows process 101, which no traced call made")
        for name in ("???", *(name for name in TRACED_CALLS if name not in ("fork", "vfork"))):
            for form in self.CUT_SHORT:
                pinned["a process with no maker after an unread call %s( in the form %s" % (name, form)] = (
                    self.written(form, name, name + "(", "101   unlink(%s) = 0" % y, pid=100),
                    "the trace shows process 101, which no traced call made")
        # The first call of the process that a call of MAKERS cut short
        # leaves with no maker, each with the label that names it.
        firsts = [("a chdir", "chdir(%s) = 0" % self.hexed("/clone/a")), ("an fchdir", "fchdir(3</clone/sub>) = 0"),
                  ("an unread call", "???() = ?")]
        for name, start in self.MAKERS.items():
            firsts.append(("a %s that made a process" % name, start[len("100   "):] + (
                ", child_tidptr=0x7f0a) = 103" if name == "clone" else ") = 103")))
        failed = " = -1 ENOENT (No such file or directory)"
        firsts += [("an unlink that failed", "unlink(%s)%s" % (self.hexed("/clone/a"), failed)),
                   ("a chdir that failed", "chdir(%s)%s" % (self.hexed("/clone/a"), failed)),
                   ("a fork that failed", "fork() = -1 EAGAIN (Resource temporarily unavailable)")]
        for name in self.MAKERS:
            for form in self.MADE:
                pinned["a relative path in a child of a %s in the form %s" % (name, form)] = (
                    self.made(form, name, "101   unlink(%s) = 0" % self.hexed("x")), relative)
                pinned["3 processes after 2 calls of %s in the form %s" % (name, form)] = (
                    [self.FORK, *self.made(form, name, *self.made(
                        form, name, "102   unlink(%s) = 0" % self.hexed("/clone/y"),
                        "103   unlink(%s) = 0" % self.hexed("/clone/z"),
                        "104   unlink(%s) = 0" % self.hexed("/clone/w"), pid=101))],
                    "the trace shows process 104, which no traced call made")
                for count in (3, 4):
                    pinned["%d processes after %d calls of %s in the form %s" % (count + 1, count, name, form)] = (
                        self.chained(form, name, count, *("%d   unlink(%s) = 0" % (pid, self.hexed("/clone/%d" % pid))
                                                          for pid in range(100 + count, 101 + 2 * count))),
                        "the trace shows process %d, which no traced call made" % (100 + 2 * count))
                for first, call in firsts:
                    pinned["2 processes after 1 %s in the form %s, the first with %s" % (name, form, first)] = (
                        self.made(form, name, "101   " + call, "102   unlink(%s) = 0" % self.hexed("/clone/z")),
                        "the trace shows process 102, which no traced call made")
        for label, (lines, error) in pinned.items():
            with self.subTest(label):
                with self.assertRaisesRegex(AssertionError, r"\A%s\Z" % re.escape(error)):
                    self.removals(*lines)
        with self.subTest("a rename with 1 argument, which fits no form that the reader takes"):
            with self.assertRaises(IndexError):
                self.removals("100   rename(%s) = 0" % self.hexed("x"))
        with self.subTest("a pin for each name of REMOVING_CALLS, each of its paths and each form of its descriptor"):
            self.assertEqual(sorted(wanted - held), [])

    def test_trace_admits_1_process_with_no_maker_for_each_call_cut_short(self):
        """Each call of clone, clone3, fork or vfork whose result is ? or
        not given lets 1 later process that no call made start, and a
        further such process ends the case with the error that names it;
        this is checked on the traces of allowance_trace. orders(4, 5)
        gives the 82 orders of at most 4 such calls, C, and 1 to 5 such
        processes, N, in which only the last N may find no C before it
        that an earlier N did not use. A call attribute is a name of
        CUTTERS, a form of MADE and an owner of OWNERS, 180 in all; a first
        call is a kind of FIRST_KINDS with the result done, failed or a
        form of MADE, or for an unread call a form of CUT_SHORT, 177 in
        all. All the C of a trace take 1 call attribute, and all its N
        take 1 first call. The traces are every order with each call
        attribute and the first call unlink done; every order with each
        first call and the call attribute clone detached by a process
        whose folder is known; and the order CNN with each call attribute
        and each first call. Each trace is checked for its error, whole,
        or, where the rule admits each process, for the absolute paths
        that it removes or replaces, in order. An order holds at most 4 C
        and 5 N, but a trace also holds such calls and processes that are
        not C or N: before each C by a process with no maker, a process
        that process 100 made makes a clone that strace detached from,
        and the process with no maker that this clone lets start removes
        an absolute path by unlink and then makes the C; and each N whose
        first call is a call of CUTTERS in a form of MADE is itself such a
        call. So a trace holds up to 9 such calls and up to 9 such
        processes, but on none of these traces does the rule leave more
        than 4 such calls untaken at the same time, and in none does a
        process make a call after its own call cut short. A reader that
        breaks the rule only in a trace that none of these products gives
        passes this test, such as 1 that breaks it only while more than 4
        such calls are untaken, or only for a call after a call cut short
        of the same process. That such a process starts in a folder that
        is not known is checked not here but, for the calls of MAKERS by
        process 100, by the relative paths of
        test_trace_refuses_what_it_cannot_read."""
        cuts = [(name, form, owner) for name in self.CUTTERS for form in self.MADE for owner in self.OWNERS]
        firsts = [(kind, result) for kind in self.FIRST_KINDS
                  for result in (self.CUT_SHORT if kind == "an unread call" else ("done", "failed", *self.MADE))]
        orders = self.orders(4, 5)
        self.assertEqual((len(orders), len(cuts), len(firsts)), (82, 180, 177))
        groups = {}
        for cut in cuts:
            groups["each order, each call %s in the form %s by %s, each first call unlink done" % cut] = [
                (order, cut, ("unlink", "done")) for order in orders]
        for first in firsts:
            groups["each order, each call clone detached by %s, each first call %s %s" % (self.OWNERS[0], *first)] = [
                (order, ("clone", "detached", self.OWNERS[0]), first) for order in orders]
        for cut in cuts:
            groups["the order CNN, the call %s in the form %s by %s, each first call, those resumed with ? among them"
                   % cut] = [
                ("CNN", cut, first) for first in firsts]
        folder = tempfile.TemporaryDirectory(prefix=TEMP_PREFIX)
        self.addCleanup(folder.cleanup)
        log = Path(folder.name) / "calls.trace"
        for label, traces in groups.items():
            with self.subTest(label):
                wrong = []
                for order, cut, first in traces:
                    lines, error, paths = self.allowance_trace(order, cut, first)
                    log.write_bytes("".join(line + "\n" for line in lines).encode("latin-1"))
                    try:
                        found = [removal[2] for removal in traced_removals(log, "/clone")[0]]
                    except Exception as caught:
                        found = "%s: %s" % (type(caught).__name__, caught)
                    expected = paths if error is None else "AssertionError: " + error
                    if found != expected:
                        wrong.append((order, first, expected, found))
                if wrong:
                    self.fail("%d of %d traces give another result, first %r" % (len(wrong), len(traces), wrong[0]))


if __name__ == "__main__":
    unittest.main()
