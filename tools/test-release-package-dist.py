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
builds, 1 in each of cases 3, 17 and 18, through the GIT_CONFIG_COUNT,
GIT_CONFIG_KEY_0 and GIT_CONFIG_VALUE_0 variables of each such build's
environment, never by a git config command. Each build runs with TMPDIR set
to a folder of the temporary folder, and without the BASHOPTS, SHELLOPTS,
GLOBIGNORE, BASH_ENV and CDPATH of the test's own environment; the cases of
inherited shell options set 1 of the first 4, case 26 sets BASHOPTS, and
case 23 sets CDPATH. Each stand-in command but kill, shopt and trap is a
short sh script that the test writes into its temporary folder and puts
first on the PATH of 1 build. The script gives each path that it uses as 1
shell word, quoted by shlex.quote, and the test writes it in the encoding
of the file system, so that a path with an apostrophe, white space or a
character outside ASCII reaches it unchanged. The stand-ins kill, shopt and
trap of cases 24 and 26 are bash functions that the environment of 1 build
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
test waits for its stand-in. Every build runs in a session of its own. Once
the bash of a build that the test signals has ended, the test ends with
SIGKILL any process of that session that still runs, so that none changes
dist/ while the test reads it; and when any build outlasts BUILD_TIMEOUT,
the test ends every process of its session with SIGKILL and reaps its bash
before it reports the timeout, so that none changes dist/ during a later
case. The signal of the exit trap cases of case 14 goes
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
of REFERENCE_COMMIT, which gives the reference digest. The cases, all in
that clone:

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
16. The packager's code, with its comment lines and the Python programs
    that it passes to python3 -c set aside, and with each line that ends
    in a backslash joined to the next with nothing between them, as bash
    joins them, holds exactly 1 rm with a recursive option,
    `rm -rf -- "${work}" || true`, no rmdir in a for, while or until loop,
    no rmdir with its parents option, no find -delete, and the line that
    sets work from mktemp -d with a template in dist/. The scan decodes
    each $'...' string as bash does, reads each $"..." as "...", reads each
    ${...} as its parameter, its operator and its word, expands each brace
    list or sequence in a word, such as -{r,f} or {a..c}, sets aside the
    quotes and backslashes of each line, and starts a new command at each
    (, ), backquote, {, }, ;, & and |, so it reads the commands of a
    subshell, a command substitution, backquotes or a group too, in the
    word of a ${...} as well. A word names rm or rmdir whatever folder
    path, quotes or backslash it carries (/usr/bin/rm, \\rm, 'rm'),
    wherever it stands in its command, such as after `command` or find
    -exec, and each option word up to the end of that command counts,
    before or after an operand; an option is recursive when it is a group
    of short options that holds r or R, or --recursive or an abbreviation
    of it from --r on. When it counts loops, it sets aside each quoted
    string that holds no command substitution. The scan reads quotes by
    their characters, not as bash pairs them, and makes no expansion that
    depends on the run, so it does not see a removal whose command name or
    option comes from a variable, eval of a variable, an alias, a function,
    pathname expansion or another program, such as a Python program, nor a
    loop whose words sit in a quoted string with no command substitution or
    a line that it takes for part of a Python program; and it counts a
    removal that a quoted message only names.
17. A stand-in rm, found through the PATH, records each call and a
    stand-in mktemp the work folder: a good build, a build refused by the
    blob check under core.autocrlf=true, and a build whose stand-in mv
    refuses each move of a .sha256 file each call rm with a recursive
    option exactly once, with the path that mktemp gave as its only
    operand; a build refused by --bogus calls it never. A call of rm by
    its folder path does not reach the stand-in; case 16 refuses 1 with a
    recursive option.
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
    whose name it knows. With the 4 together, a build that receives SIGSYS
    while a stand-in mv holds the move of the .sha256 files exits 159 and
    leaves no zip and no .sha256 in dist/.
25. The scan of case 16 finds 1 more removal of its kind in the packager's
    text with each line of SECOND_REMOVALS added at its end than without:
    a recursive rm, an rmdir with its parents option, a find -delete or an
    rmdir in a loop, in each form that case 16 names.
26. For each glob or match option of SHELL_OPTIONS_OFF, which the packager
    turns off, with a stand-in shopt that records each call and fails as
    bash does for an option that it does not know at each call that names
    that option, with the other 4 turned on through BASHOPTS, and with the
    stand-in trap of case 24, which also records the shell options that
    BASHOPTS lists at each call, a good build exits 0, writes the 4 outputs
    and keeps the planted paths; the build asked the stand-in shopt about
    that option; and at each trap that it set, its shell options held
    dotglob and none of the 5, so an option that the shell does not know
    neither ends the build nor leaves another option turned on.

Each case starts with no dist/ in the clone.

REFERENCE_COMMIT names the commit of the last packager that wrote dist/
before its checks, and the reference comparison in case 1 holds only while
the packager gives the same bytes as that commit's packager. An intended
change to the packager's output therefore makes case 1 fail by design.
REFERENCE_COMMIT then moves to the commit that makes the change, in the
same pull request.

Usage:
  python3 -I tools/test-release-package-dist.py

Needs git, bash, zip, unzip, sha256sum and GNU coreutils, and the full
history of the checkout, since it reads tools/release-package.sh at
REFERENCE_COMMIT.
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
# Words that end a shell command on a line of the packager.
COMMAND_ENDS = {"||", "&&", "|", ";", ";;", "&", ")", "}", "then", "do", "done", "else", "fi", "esac"}
# A ${...} expansion with no brace inside, which the removal scan reads as
# its parameter, its operator and its word, so that a command substitution
# or an option in its word is read too; the parts of its text; and the
# characters at which the scan starts a new command: a subshell or command
# substitution, a backquote, a group, a list or a pipe.
PARAMETER = re.compile(r"\$\{([^{}]*)\}")
PARAMETER_PARTS = re.compile(r"([#!]?(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[-*@#?$!])(?:\[[^]]*\])?)"
                             r"(:?[-+=?]|##?|%%?|/[/#%]?|\^\^?|,,?|:|@)?(.*)", re.S)
COMMAND_STARTS = re.compile(r"[()`{};&|]")
# An ANSI-C quoted string, $'...', the escapes in it that bash decodes, and
# the 1-letter ones among them.
ANSI_C = re.compile(r"\$'((?:\\.|[^'\\])*)'", re.S)
ANSI_C_ESCAPE = re.compile(r"\\(?:([abeEfnrtv\\'\"?])|([0-7]{1,3})|x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})"
                           r"|U([0-9A-Fa-f]{1,8})|c(.))", re.S)
ANSI_C_LETTERS = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r",
                  "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
# A pair of braces with no white space and no brace in it, which bash
# expands as a brace expansion when it holds a list, such as {r,f}, or a
# sequence, such as {a..c} or {1..9..2}.
BRACES = re.compile(r"\{([^\s{}]*)\}")
BRACE_SEQUENCE = re.compile(r"(-?[0-9]+|[A-Za-z])\.\.(-?[0-9]+|[A-Za-z])(?:\.\.(-?[0-9]+))?")
# A quoted string of a shell line that holds no command substitution, which
# the scan sets aside when it counts loops.
QUOTED = re.compile(r"'[^']*'|\"(?:\\.|\$(?!\()|[^\"\\$`])*\"")
# A second removal in each form that the scan of the structural case must
# see, as lines added at the end of the packager's text, with the list of
# removal_scan that it adds to: recursive rm, looped rmdir or other.
SECOND_REMOVALS = (
    ("recursive", 'rm -rf -- "${work}/src"'),
    ("recursive", '/usr/bin/rm -rf -- "${work}/src"'),
    ("recursive", '\\rm -r -- "${work}/src"'),
    ("recursive", "'rm' -R -- \"${work}/src\""),
    ("recursive", 'r"m" --recursive -- "${work}/src"'),
    ("recursive", 'rm --rec -- "${work}/src"'),
    ("recursive", 'rm "${work}/src" -r'),
    ("recursive", '/bin/rm "-rf" -- "${work}/src"'),
    ("recursive", "rm '-r' -- \"${work}/src\""),
    ("recursive", '(rm -rf -- "${work}/src")'),
    ("recursive", 'gone="$(\\rm -r -- "${work}/src")"'),
    ("recursive", 'gone=`rm -r -- "${work}/src"`'),
    ("recursive", '/usr/bin/rm -f \\\n  -r -- "${work}/src"'),
    ("recursive", '/bin/rm \\\n  -rf -- "${work}/src"'),
    ("recursive", 'rm -f "${work}/a" \\\n  "${work}/src" -r'),
    ("recursive", 'true; rm -r -- "${work}/src"'),
    ("recursive", 'true && rm -r -- "${work}/src"'),
    ("recursive", 'true || rm -r -- "${work}/src"'),
    ("recursive", 'true | rm -r -- "${work}/src"'),
    ("recursive", '{ rm -r -- "${work}/src"; }'),
    ("recursive", 'if true; then rm -r -- "${work}/src"; fi'),
    ("recursive", 'command rm -r -- "${work}/src"'),
    ("recursive", 'find "${work}/src" -exec rm -r {} +'),
    ("recursive", "rm $'-r' -- \"${work}/src\""),
    ("recursive", "/usr/bin/rm $'\\x2drf' -- \"${work}/src\""),
    ("recursive", 'rm $"-r" -- "${work}/src"'),
    ("recursive", '/usr/bin/r\\\nm -rf -- "${work}/src"'),
    ("recursive", 'rm -\\\nrf -- "${work}/src"'),
    ("recursive", ': "${unset_name:-$(/usr/bin/rm -rf -- "$work/src")}"'),
    ("recursive", ': "${unset_name:-`rm -r -- "$work/src"`}"'),
    ("recursive", 'rm ${unset_name:--r} -- "${work}/src"'),
    ("recursive", 'rm -f{,r} -- "${work}/src"'),
    ("other", 'rmdir -p "${work}/src/a"'),
    ("other", 'rmdir "-p" "${work}/src/a"'),
    ("other", '(rmdir --parents "${work}/src/a")'),
    ("other", '/usr/bin/rmdir \\\n  -p "${work}/src/a"'),
    ("other", 'find "${work}" -delete'),
    ("other", 'find "${work}" "-delete"'),
    ("other", "rmdir $'-p' \"${work}/src/a\""),
    ("other", 'rmdir -{p..p} "${work}/src/a"'),
    ("other", "find \"${work}\" $'-delete'"),
    ("other", 'find "${work}" -del\\\nete'),
    ("looped", 'for d in a b; do rmdir "${work}/$d"; done'),
    ("looped", '(for d in a b; do rmdir "${work}/$d"; done)'),
    ("looped", 'while false; do\n  rmdir "${work}/src"\ndone'),
    ("looped", 'gone="$(for d in a b; do rmdir "${work}/$d"; done)"'),
)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=BUILD_TIMEOUT).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def end_session(proc: subprocess.Popen):
    """End with SIGKILL every process of the session that proc leads that
    still runs, and reap proc."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def sh_word(value) -> str:
    """value, a path or a string, as 1 sh word that sh reads back unchanged."""
    return shlex.quote(str(value))


def command_name(word: str) -> str:
    """The name of the command that a word of a shell line gives, with its
    quotes, backslashes and folder path set aside: rm for rm, \\rm, 'rm',
    "rm" or /usr/bin/rm."""
    return word.replace("\\", "").replace("'", "").replace('"', "").rsplit("/", 1)[-1]


def command_options(words: list) -> list:
    """The option words among words, the arguments of a command on a line,
    up to the word that ends the command or --; an option may stand before
    or after an operand, as GNU rm and rmdir take it."""
    options = []
    for word in words:
        last = word.endswith(";")
        word = word.rstrip(";")
        if word in COMMAND_ENDS or word == "--":
            break
        if word.startswith("-") and word != "-":
            options.append(word)
        if last:
            break
    return options


def long_option(word: str, name: str) -> bool:
    """Whether word is the long option name or an abbreviation of it, from
    its first letter on, as GNU rm and rmdir take it."""
    return word.startswith("--") and len(word) > 2 and name.startswith(word)


def recursive_option(word: str) -> bool:
    """Whether an rm option word asks for a recursive removal: a group of
    short options that holds r or R, or --recursive or an abbreviation of it."""
    if word.startswith("--"):
        return long_option(word, "--recursive")
    return word.startswith("-") and ("r" in word or "R" in word)


def parents_option(word: str) -> bool:
    """Whether an rmdir option word asks for its parents option: a group of
    short options that holds p, or --parents or an abbreviation of it."""
    if word.startswith("--"):
        return long_option(word, "--parents")
    return word.startswith("-") and "p" in word


def code_lines(text: str) -> list:
    """(number, line) for each line of a shell script that is not blank, not
    a comment line, and not inside a Python program that the script passes
    to python3 -c in single quotes over several lines."""
    found, in_python = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if in_python:
            in_python = not line.startswith("'")
            continue
        if "python3 -I -c '" in line and line.count("'") % 2 == 1:
            in_python = True
        if line.strip() and not line.lstrip().startswith("#"):
            found.append((n, line))
    return found


def logical_lines(text: str) -> list:
    """(number, line) for each line of code_lines(text), with each line that
    ends in a backslash joined to the next with nothing between them, as
    bash removes a backslash and the newline after it, so that a word split
    there, such as r and m, is read as 1 word; each is numbered by its first
    line."""
    found, pending = [], None
    for n, line in code_lines(text):
        if pending is not None:
            n, line = pending[0], pending[1] + line
        if line.endswith("\\"):
            pending = (n, line[:-1])
        else:
            pending = None
            found.append((n, line))
    if pending is not None:
        found.append(pending)
    return found


def ansi_c(text: str) -> str:
    """The text of a $'...' string, without its quotes, as bash decodes
    its escapes."""
    def escape(match) -> str:
        letter, octal, hexadecimal, short, long, control = match.groups()
        if letter:
            return ANSI_C_LETTERS[letter]
        if control:
            return chr(ord(control) & 0x1F)
        value = int(octal, 8) if octal else int(hexadecimal or short or long, 16)
        return chr(min(value, 0x10FFFF))
    return ANSI_C_ESCAPE.sub(escape, text)


def parameter_words(match) -> str:
    """The text of 1 ${...} with no brace inside, read as its parameter, its
    operator and its word, separated by spaces, with the first / of the
    word of a pattern substitution read as a space as well, so that each of
    them is read as a word."""
    parts = PARAMETER_PARTS.fullmatch(match.group(1))
    if parts is None:
        return "$" + match.group(1)
    name, operator, word = parts.groups()
    if operator and operator.startswith("/"):
        word = word.replace("/", " ", 1)
    return " ".join(part for part in ("$" + name, operator, word) if part)


def brace_items(text: str):
    """The items that bash gives for the text between a pair of braces: the
    parts of a list split at each comma, or each item of a sequence; None
    when the text is neither."""
    sequence = BRACE_SEQUENCE.fullmatch(text)
    if sequence:
        first, last, step = sequence.groups()
        step = abs(int(step or 1)) or 1
        if first.isalpha() != last.isalpha():
            return None
        start, end = (ord(first), ord(last)) if first.isalpha() else (int(first), int(last))
        numbers = range(start, end + 1, step) if start <= end else range(start, end - 1, -step)
        return [chr(n) for n in numbers] if first.isalpha() else [str(n) for n in numbers]
    return text.split(",") if "," in text else None


def brace_expand(line: str) -> str:
    """line with each brace expansion in a word replaced by the words that
    bash gives for it; braces that hold neither a list nor a sequence stay."""
    start = 0
    while True:
        match = BRACES.search(line, start)
        if match is None:
            return line
        items = brace_items(match.group(1))
        if items is None:
            start = match.end()
            continue
        before = re.search(r"\S*\Z", line[:match.start()]).start()
        after = match.end() + re.match(r"\S*", line[match.end():]).end()
        prefix, suffix = line[before:match.start()], line[match.end():after]
        line = line[:before] + " ".join(prefix + item + suffix for item in items) + line[after:]
        start = before


def commands(line: str) -> list:
    """The words of each command of a logical line, read as bash reads them
    in these respects: each $'...' string decoded, each $"..." read as
    "...", each ${...} read as its parameter, its operator and its word,
    each brace expansion expanded, and the quotes and backslashes of the
    line set aside. A command starts at each character of COMMAND_STARTS,
    so the commands of a subshell, a command substitution, backquotes or a
    group are read as well, in the word of a ${...} too."""
    line = ANSI_C.sub(lambda match: ansi_c(match.group(1)), line)
    line = line.replace('$"', '"')
    while PARAMETER.search(line):
        line = PARAMETER.sub(parameter_words, line)
    line = brace_expand(line)
    line = line.replace("\\", "").replace("'", "").replace('"', "")
    return [part.split() for part in COMMAND_STARTS.split(line) if part.split()]


def loop_counts(line: str) -> tuple:
    """The number of for, while and until loops that a logical line opens
    and the number of done words that close 1, read from its commands with
    its quoted strings set aside, so that a word of a message is not
    taken for either."""
    words = [w[0] for w in commands(QUOTED.sub("''", line))]
    return sum(w in ("for", "while", "until") for w in words), words.count("done")


def removal_scan(text: str) -> dict:
    """The removals of a shell script that the structural case refuses, each
    as (number, line): "recursive", each rm with a recursive option;
    "looped", each rmdir on a line that is in a for, while or until loop or
    opens 1; and "other", each rmdir with its parents option and each find
    -delete."""
    found = {"recursive": [], "looped": [], "other": []}
    depth = 0
    for number, line in logical_lines(text):
        opens, closes = loop_counts(line)
        for words in commands(line):
            for index, word in enumerate(words):
                name = command_name(word)
                if name == "rm" and any(recursive_option(o) for o in command_options(words[index + 1:])):
                    found["recursive"].append((number, line.strip()))
                if name == "rmdir":
                    if depth + opens:
                        found["looped"].append((number, line.strip()))
                    if any(parents_option(o) for o in command_options(words[index + 1:])):
                        found["other"].append((number, line.strip()))
                if word == "-delete":
                    found["other"].append((number, line.strip()))
        depth = max(depth + opens - closes, 0)
    return found


class DistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix=TEMP_PREFIX)
        if os.pathsep in cls.tmp.name:
            cls.tmp.cleanup()
            raise AssertionError("the temporary folder %r holds %r, which no entry of PATH can hold; "
                                 "set TMPDIR to a folder whose path holds none" % (cls.tmp.name, os.pathsep))
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
        reference.write_bytes(git("-C", str(REPO), "show", REFERENCE_COMMIT + ":tools/release-package.sh"))
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
                     extra: dict = None):
        """Run script with bash in the clone and return its exit code and
        error output. The build runs in a session of its own, so that a
        build that outlasts BUILD_TIMEOUT has every process of that session
        ended with SIGKILL, and its bash reaped, before the timeout is
        raised, and none of them can change dist/ during a later case."""
        with subprocess.Popen(["bash", str(script), *args], cwd=str(cls.clone),
                              env=cls.packager_env(autocrlf, path_prefix, extra),
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, start_new_session=True) as proc:
            try:
                _, stderr = proc.communicate(timeout=BUILD_TIMEOUT)
            except subprocess.TimeoutExpired:
                end_session(proc)
                proc.communicate()
                raise
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
        process of its session that still runs, such as a stand-in that a
        build ended at once left behind, reap the bash and close its error
        output, so that none changes dist/ after this returns or raises;
        raise the timeout if there was one, and return the build's stderr
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
                end_session(proc)
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
        of its own, whose processes held_signal can signal and end together."""
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

    def test_only_recursive_removal_is_work_folder(self):
        """The packager's code, comment lines set aside and continued lines
        joined, holds exactly 1 rm with a recursive option, the removal of
        the work folder by the path that mktemp gave; no rmdir in a for or
        while loop, no rmdir with its parents option, and no find -delete.
        Each command of a line counts, in a subshell, a command substitution
        or a group too; a word names rm or rmdir whatever folder path,
        quotes or backslash it carries, and each option word up to the end
        of its command counts, read as case 16 of the module's docstring
        says."""
        text = (self.clone / "tools" / "release-package.sh").read_text(encoding="utf-8")
        found = removal_scan(text)
        self.assertEqual([line for _, line in found["recursive"]], ['rm -rf -- "${work}" || true'],
                         "the recursive removals are %r" % found["recursive"])
        self.assertEqual(found["looped"], [], "rmdir runs in a loop at %r" % found["looped"])
        self.assertEqual(found["other"], [], "other recursive or repeated removals: %r" % found["other"])
        self.assertIn('work="$(mktemp -d "${PWD}/dist/.release-package.XXXXXX")"',
                      [line.strip() for _, line in code_lines(text)])

    def test_structural_scan_sees_second_removal(self):
        """The scan of the structural case finds 1 more removal of its kind
        in the packager's text with each line of SECOND_REMOVALS added at
        its end than in the text alone."""
        text = (self.clone / "tools" / "release-package.sh").read_text(encoding="utf-8")
        before = removal_scan(text)
        for kind, added in SECOND_REMOVALS:
            with self.subTest(added):
                after = removal_scan(text.rstrip("\n") + "\n" + added + "\n")
                self.assertEqual(len(after[kind]), len(before[kind]) + 1,
                                 "the scan did not see %r: %r" % (added, after[kind]))

    def recording_rm(self, bin_dir: Path) -> Path:
        """Write into bin_dir a stand-in rm that writes each call's arguments
        as 1 record of its log, then runs the real rm. Return the log."""
        log = bin_dir / "rm-calls.log"
        self.write_script(bin_dir / "rm", self.recorder(log) +
                          "record \"$@\"\n"
                          "exec %s \"$@\"\n" % sh_word(self.real("rm")))
        return log

    def recursive_removals(self, log: Path) -> list:
        """The operands of each recorded rm call with a recursive option. An
        option word may stand before or after an operand, as GNU rm takes
        it, and each word after -- is an operand."""
        found = []
        for args in self.records(log):
            options, operands, ended = [], [], False
            for arg in args:
                if not ended and arg == "--":
                    ended = True
                elif not ended and arg.startswith("-") and arg != "-":
                    options.append(arg)
                else:
                    operands.append(arg)
            if any(recursive_option(o) for o in options):
                found.append(operands)
        return found

    def test_recursive_removal_only_of_work_folder(self):
        """A stand-in rm records each call and a stand-in mktemp the work
        folder: a good build, a build refused by the blob check, and a build
        whose move of the .sha256 files fails each call rm with a recursive
        option exactly once, with the path that mktemp gave as its only
        operand; a build refused by --bogus calls it never."""
        for label, args, autocrlf, move_exit in (("good", (), False, 0), ("blob", (), True, 0),
                                                  ("move", (), False, MOVE_EXIT), ("bogus", ("--bogus",), False, 0)):
            with self.subTest(label):
                self.setUp()
                bin_dir, work_log = self.trap_stand_ins(move_exit)
                rm_log = self.recording_rm(Path(bin_dir))
                self.plant()
                code, stderr = self.build(*args, autocrlf=autocrlf, path_prefix=bin_dir)
                self.assertEqual(code, {"good": 0, "blob": 1, "move": MOVE_EXIT, "bogus": 1}[label], stderr)
                removals = self.recursive_removals(rm_log)
                if label == "bogus":
                    self.assertFalse(work_log.exists(), "the build refused by --bogus made a work folder")
                    self.assertEqual(removals, [], "the build refused by --bogus removed %r" % removals)
                else:
                    self.assertEqual(removals, [[str(self.work_folder(work_log))]],
                                     "the recursive removals were %r" % removals)
                self.assert_plants_kept()

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
        signal. With NON_LINUX_NAMES unknown, SIGSYS, which comes after
        STKFLT in the packager's list, still ends a build with 159 while a
        stand-in mv holds the move of the .sha256 files, and the build leaves
        no output."""
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
            self.assert_signal_ends_build(signal.SIGSYS, 128 + signal.SIGSYS, extra=extra)
            self.assertTrue(self.records(log), "the build never asked the stand-in kill for an unknown name")

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


if __name__ == "__main__":
    unittest.main()
