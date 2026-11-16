#!/usr/bin/env bash
#
# Builds the skill release zip and proves its contents before anything ships.
#
# Everything here reads the git tree at HEAD, never the checkout's filesystem
# metadata. Filesystem permission bits vary by machine (an ACL can add execute
# bits the repository never recorded), so a check that read them would pass on
# one machine and fail on another. The git tree is identical everywhere the
# commit exists, and the archive is stamped from the commit and ordered, so
# the same commit rebuilt with the same zip binary gives the same
# bytes and checksum; different zip builds can differ, so a digest is
# comparable only between builds made with the same zip binary.
#
# What it does, in order:
#
#   1. Reads the version from the first Version: line in cleanlanguage/skills/cleanlanguage/SKILL.md
#      at HEAD and requires a bare X.Y.Z, the same rule the release gates apply;
#      with --tag, fails unless the tag is v<version>. Also requires the
#      skill name line and at least one Markdown reference, the two structural
#      checks the previous inline validation enforced. Reads the Released line
#      (item 26) through tools/skill-release-date.py, run in its --json mode by
#      tools/skill-release-date-client.py, and fails on a malformed
#      one, and on a missing one when the version sorts above the undated
#      baseline, whether or not --release-date is given; --release-date adds
#      the check that the line is present, at any version, and names that date.
#   2. Requires every git entry under cleanlanguage/ to carry mode 100644,
#      which rejects executable files (100755), symlinks (120000), and
#      submodules (160000) in one comparison.
#   3. Requires every path to match the package allowlist by shape:
#      skills/cleanlanguage/SKILL.md, the Claude manifest at
#      .claude-plugin/plugin.json, the Agent Plugins manifest at plugin.json,
#      agent configuration in agents/, the CL_icon files in assets/, and
#      Markdown references in skills/cleanlanguage/references/. This checks path
#      shape and git mode, not file content: a new flat Markdown reference under
#      skills/cleanlanguage/references/ is allowed, while a new directory, a
#      script extension, or any other nested path fails.
#   4. Requires every icon the ChatGPT interface configuration references to
#      exist in the package, whether the YAML quotes the path with double
#      quotes, single quotes, or none.
#   5. Lays out the package from git archive in a source folder under TMPDIR,
#      removes both plugin manifests, which ship through the marketplace
#      rather than the zip, adds LICENSE and
#      NOTICE.md, restores SKILL.md and references/ from skills/cleanlanguage/
#      to the archive root, and zips the files at the archive ROOT (SKILL.md,
#      agents/, assets/, references/, LICENSE, NOTICE.md), with no cleanlanguage/
#      prefix, so the zip holds exactly what git records, minus both manifests
#      and the skills/cleanlanguage/ nesting, plus the two licence files,
#      whatever state the checkout is in.
#   6. Verifies the archive against an expected entry list derived from the
#      same git tree, excluding the plugin manifest, and verifies every
#      archived file's bytes against its git blob, so a git attribute such as
#      export-subst cannot change the shipped bytes unnoticed.
#   7. Moves the 2 verified zips into dist/, then their .sha256 files. Steps 5
#      and 6 build and verify the outputs in a staging folder inside dist/
#      (dist/.release-package.XXXXXX), so no unverified output ever sits
#      under an output name in dist/.
#
# It writes dist/cleanlanguage.zip, dist/cleanlanguage-<version>.zip, and a
# .sha256 beside each, only after every check passes. Its first check
# refuses a dist that is a symbolic link, or that exists and is not a
# folder, before it removes or writes anything; it records the device and
# inode of that folder, or of the one it makes later, and ends with exit 1
# and a message, having removed nothing, if it cannot read them or reads
# an answer that is not 2 numbers. It refuses with exit 1 if dist is no
# longer that folder after it makes dist/, after it makes its staging
# folder there, or just before the moves, and with exit 1 and a message of
# its own if it cannot enter dist/ before its exit trap runs; in the exit
# trap, a dist that it cannot enter leaves the exit code as it was. It
# reaches dist/, its staging folder
# and its source folder only by entering each folder and checking the
# device and inode of the folder it entered (see enter_dist), and then
# works by names relative to that folder. Its exit trap removes the
# staging folder and the source folder each by its name in the folder that
# holds it, and only after a check that the name still holds the folder
# that the build recorded; if the build ended after it made a work folder
# and before it recorded that folder's device and inode, the trap removes
# that name only while it holds an empty folder (rmdir). A failed read of
# the device and inode of a work folder ends the build with the exit code
# of stat, and the build records nothing from it. So a folder
# replaced after its check does not receive the removals, writes or moves
# of the build, apart from the windows that the comment on enter_dist
# lists. A staging or source folder that is not the folder it recorded
# when the build next enters it ends the build with exit 1; 1 replaced
# after the build's last entry into it leaves the exit code as it was, 0
# for a good build, and the exit trap keeps it.
# Directly after that first check it sets its exit trap, and then, before
# the argument and git tree checks, it removes the outputs that an earlier
# build left, chosen by name and type, not by who wrote them: each regular
# file named
# cleanlanguage.zip, cleanlanguage-X.Y.Z.zip, or the .sha256 of either,
# where X, Y and Z are ASCII digits, and each folder named
# .release-package. followed by 6 ASCII letters or digits, together with
# everything that folder holds. The name tests list each of these
# characters, so the locale does not change what they match. It keeps
# every other entry of dist/: a file or folder of any other name, a symbolic
# link or file that carries a staging name, and a symbolic link, folder,
# FIFO or other special file that carries an output name. The move into
# dist/ is a rename, which would replace an object of the last kind, so
# once the version is known the build refuses with exit 1 if 1 of the 4
# names it writes is held by anything other than a regular file.
# That refusal comes after the removal of the earlier outputs, so it leaves
# no stale output, and before the build writes anything to dist/, so the
# object stays as it was. From just before the first removal, the exit
# trap removes the outputs again on a failed exit, so a build ended during
# that removal does not leave the rest of an earlier build's outputs; of
# the folders with a staging name, the trap removes only the 1 that the
# build made. A
# SIGHUP, SIGINT or SIGTERM ends the build with exit 129, 130 or 143, once
# the command in progress has ended, and counts as a failed exit, unless
# the signal was ignored when the build started (as SIGHUP is under
# nohup): bash cannot trap such a signal, so it does not end the build.
# The exit trap ignores the 3 signals while it runs, so 1 that arrives
# then leaves the exit code as it was. A
# signal that arrives before the exit trap is set, when the build has
# removed and written nothing, leaves dist/ as it was. So a
# refused build leaves in dist/ no zip and no .sha256 that a build wrote,
# unless a removal itself fails, the first read of the identity of dist
# fails, the build cannot enter dist/, or dist was replaced while it ran:
# the build then still fails, an output that it could not remove stays,
# and through a dist that it cannot enter or that was replaced it removes
# nothing. A SIGKILL runs no trap, so it can leave
# a zip without its .sha256, a .sha256 without its zip, or a staging
# folder, which the next build removes.
# It never tags, pushes, or talks to the network.
#
# Usage:
#   tools/release-package.sh                 Build and verify at HEAD.
#   tools/release-package.sh --tag v1.0.12   Also require the tag to match.
#   tools/release-package.sh --release-date 2026-11-15
#                                            Also require the Released line
#                                            to be present and to name that
#                                            UTC day.
#
# Exit codes:
#   0  built and verified
#   1  a validation or layout check failed
#   129, 130, 143  ended by SIGHUP, SIGINT or SIGTERM, unless that signal
#                was ignored when the build started
#   other codes  the exit code of a command that failed, such as zip, mv
#                or git, which set -e passes through unchanged and the
#                exit trap keeps; such a command can also give 1, 129,
#                130 or 143

set -euo pipefail

# Glob and match options can come from the environment (BASHOPTS or
# SHELLOPTS) or from a file that BASH_ENV names: failglob would end the
# removal below at a glob that matches nothing, noglob would hide the
# entries of dist/ from it, and nocasematch would let its name tests match
# a name in another letter case. A GLOBIGNORE that the shell assigns drops
# the names it matches from what a glob gives. Bash 5.3.9 does not apply a
# GLOBIGNORE taken from the environment, but it does apply one that a
# BASH_ENV file assigns. So GLOBIGNORE is unset and these options are set
# here: the glob * in dist/ gives the entries of dist/, names that start
# with a dot included, and the name tests alone choose what is removed. With
# no entry in dist/, the glob gives the word * itself, which matches
# neither name test and is neither a file nor a folder, so the removal
# does nothing, as it would with nullglob. CDPATH is unset as well, so that
# cd enters the folder that its relative name gives here, not 1 that CDPATH
# gives.
unset GLOBIGNORE CDPATH
set +f
shopt -u extglob failglob globstar nocaseglob nocasematch
shopt -s dotglob

# A signal would otherwise end bash with the status of the last command,
# which the exit trap below would read as a good exit, so each of these
# exits with 128 plus the signal's number. Bash runs such a trap once the
# command in progress has ended.
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$(dirname "${BASH_SOURCE[0]}")/.."

fail() {
  printf 'release-package: %s\n' "$1" >&2
  exit 1
}

# A dist that is a symbolic link would send every removal and every output to
# wherever it points, which may lie outside this checkout, and a dist that is
# a file cannot hold the outputs, so both are refused before anything is
# removed.
if [ -L dist ]; then
  fail "dist is a symbolic link; the packager writes only into a real dist/ folder"
elif [ -e dist ] && [ ! -d dist ]; then
  fail "dist exists and is not a folder"
fi
# The device and inode of the dist/ folder that passed the refusal above, or
# of the one the build makes. A dist renamed, or replaced by a symbolic link,
# while the build runs would send the outputs and the removals elsewhere, so
# the build checks dist by name with same_dist after it makes dist/ and
# just before the moves, and reaches the folder itself only through
# enter_dist below. If this first read fails, or gives an answer that is
# not 2 numbers separated by a colon, the build ends here with exit
# 1, before it sets its exit trap: it has removed nothing, so any output of
# an earlier build is still in dist/. The read after the build makes dist/
# is checked in the same way.
DIST_ID_FAILED="could not read the device and inode of dist; the build has removed nothing from dist/, and any earlier output is still there"
dist_id=""
if [ -d dist ]; then
  dist_id="$(stat -c '%d:%i' -- dist)" || fail "${DIST_ID_FAILED}"
  [[ "${dist_id}" =~ ^[0123456789]+:[0123456789]+$ ]] || fail "${DIST_ID_FAILED}"
fi
same_dist() {
  [ -n "${dist_id}" ] && [ ! -L dist ] && [ -d dist ] \
    && [ "$(stat -c '%d:%i' -- dist 2>/dev/null)" = "${dist_id}" ]
}
DIST_REPLACED="dist was replaced while the build ran; the packager writes only into the dist/ folder it checked at the start"
DIST_UNREACHABLE="could not enter dist/; the packager writes only into the dist/ folder it checked at the start"
WORK_REPLACED="a work folder was replaced while the build ran; the packager writes only into the folders it made"

# A check of a folder by its name and a use of that name later can reach 2
# different folders, since a process of the same user can rename or replace
# the folder between them. So the build reaches each of its 3 folders by
# entering it once, with cd -P, and checking the device and inode of . (the
# folder it entered) against those it recorded; after that, the names it
# uses are relative to that folder, which a rename of the folder or a
# replacement of its name does not change. Each of these functions changes
# the working directory, so the build calls each only in a subshell, which
# leaves the working directory of the build at the root of the checkout.
# enter_dist enters the dist/ folder that the build recorded; enter_staging,
# called in that folder, enters the staging folder that the build made
# there (the folder whose name is in out); enter_source enters the source
# folder under TMPDIR (the folder whose name is in source_dir). Each
# returns 1, and enters nothing that it could not check, if the name is a
# symbolic link or the folder it reaches is not the recorded one;
# enter_dist returns 3 instead if cd cannot enter dist, so that the build
# does not report a dist that it could not enter as replaced.
# These windows remain, since each command involved takes a name and bash
# cannot give it the object that was checked: the time between mkdir or
# mktemp making a folder, or the refusal of a linked dist, and the read of
# that folder's device and inode; the time between a test of an entry of
# an entered folder and the rm, write or mv of that entry by its name; the
# time between the check that .. of the staging folder is the recorded
# dist/ folder and the moves to ..; and the time between the check, in
# the exit trap, that the name of a work folder still holds the recorded
# folder, or with no identity recorded that it is not a symbolic link,
# and the rm -rf or rmdir of that name. The exit trap enters the folder that
# holds the source folder (TMPDIR) by its path, which it has not recorded;
# if that path then reaches another folder, the check of the source
# folder's identity fails and the source folder stays. The subfolders that
# tar makes in the source folder, such as cleanlanguage/, are reached by
# relative names and are not recorded; the source folder is made by mktemp
# with mode 0700, so only the same user, or root, can replace them. The
# checks of dist by name (the refusal of a linked or non-folder dist,
# same_dist and the refusal of an object at an output name) only decide
# whether to refuse, and a dist replaced after 1 of them is refused at the
# next entry into dist/, before anything is written there. rm removes a
# symbolic link put at a name without following it.
enter_dist() {
  { [ -n "${dist_id}" ] && [ ! -L dist ]; } || return 1
  cd -P -- ./dist 2>/dev/null || return 3
  [ "$(stat -c '%d:%i' -- . 2>/dev/null)" = "${dist_id}" ]
}
enter_staging() {
  [ -n "${out_id}" ] && [ ! -L "./${out}" ] && cd -P -- "./${out}" 2>/dev/null \
    && [ "$(stat -c '%d:%i' -- . 2>/dev/null)" = "${out_id}" ]
}
enter_source() {
  [ -n "${source_id}" ] && [ ! -L "${source_dir}" ] && cd -P -- "${source_dir}" 2>/dev/null \
    && [ "$(stat -c '%d:%i' -- . 2>/dev/null)" = "${source_id}" ]
}
# Enter dist/, or the staging folder through dist/, or end the subshell
# with exit 1 and the message that names the folder that failed its check,
# or that says that dist/ could not be entered.
to_dist() {
  local rc=0
  enter_dist || rc=$?
  case "${rc}" in
    0) ;;
    3) fail "${DIST_UNREACHABLE}" ;;
    *) fail "${DIST_REPLACED}" ;;
  esac
}
to_staging() {
  to_dist
  enter_staging || fail "${WORK_REPLACED}"
}
to_source() {
  enter_source || fail "${WORK_REPLACED}"
}

# The packager's outputs in dist/ and its staging folders there, matched by
# exact name and type, not by who wrote them: a regular file named
# cleanlanguage.zip, cleanlanguage-X.Y.Z.zip or the .sha256 of either, where
# X, Y and Z are 1 or more ASCII digits, and a folder named .release-package.
# followed by 6 ASCII letters or digits, the characters that mktemp gives,
# which is removed with everything it holds. The name tests list each of
# these characters, not a range such as [0-9] or [A-Z]: a range in a bash
# =~ test follows the locale, and under LC_ALL=en_US.UTF-8 it also takes
# letters and digits outside ASCII, such as an accented capital letter or an
# Arabic-Indic digit. A symbolic link is neither, so it is kept, as is an
# entry of any other name or type. The removal runs in a subshell that has
# entered the recorded dist/ folder (enter_dist) and removes each entry by
# its name in that folder, so a dist renamed or replaced during the removal
# does not change the folder that it removes from. It removes the folders
# with a staging name only when its first argument is with-staging, as at
# the start of the build; the exit trap calls it without, so that on a
# failed exit it removes no staging folder but the 1 that the build made,
# which the trap removes through remove_staging. Each
# removal is tried, so a failed removal does not stop the others; the
# return status is 1 if 1 or more failed, 2 if dist is not the folder
# recorded above, and 3 if cd cannot enter dist; with 2 or 3 it removes
# nothing. With no dist recorded,
# the build has written nothing to dist/, so there is nothing to remove.
remove_outputs() {
  local output_name='^cleanlanguage(-[0123456789]+\.[0123456789]+\.[0123456789]+)?\.zip(\.sha256)?$'
  local staging_name='^\.release-package\.[ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789]{6}$'
  local with_staging="${1:-}"
  [ -n "${dist_id}" ] || return 0
  (
    enter_rc=0
    enter_dist || enter_rc=$?
    case "${enter_rc}" in
      0) ;;
      3) exit 3 ;;
      *) exit 2 ;;
    esac
    rc=0
    for name in *; do
      if [[ "${name}" =~ ${output_name} ]]; then
        if [ -f "./${name}" ] && [ ! -L "./${name}" ]; then
          rm -f -- "./${name}" || rc=1
        fi
      elif [ "${with_staging}" = with-staging ] && [[ "${name}" =~ ${staging_name} ]]; then
        if [ -d "./${name}" ] && [ ! -L "./${name}" ]; then
          rm -rf -- "./${name}" || rc=1
        fi
      fi
    done
    exit "${rc}"
  )
}

# The 2 work folders: source_dir holds the path of the source folder under
# TMPDIR, in which the build lays out the files to zip, and out holds the
# name, in dist/, of the staging folder, in which it builds and verifies
# the outputs; source_id and out_id hold the device and inode of each, and
# source_parent and source_name hold the path of the folder that holds the
# source folder and the name of the source folder in it. Each
# is empty until the build makes its folder.
source_dir=""
source_id=""
source_parent=""
source_name=""
out=""
out_id=""
# Remove the source folder by its name in the folder that holds it, and
# only while that name is not a symbolic link and holds the folder whose
# device and inode the build recorded; otherwise remove nothing. If mktemp
# made the folder but the build recorded no identity for it (a failed
# read, a name that was a symbolic link at the check after mktemp, or a
# signal in between), it removes that name with rmdir, after the same
# check that it is not a symbolic link; rmdir removes only an empty
# folder, so it removes no file that anyone wrote.
remove_source() {
  [ -n "${source_name}" ] || return 0
  (
    cd -P -- "${source_parent}" 2>/dev/null && [ ! -L "./${source_name}" ] || exit 1
    if [ -n "${source_id}" ]; then
      [ "$(stat -c '%d:%i' -- "./${source_name}" 2>/dev/null)" = "${source_id}" ] \
        && rm -rf -- "./${source_name}"
    else
      rmdir -- "./${source_name}" 2>/dev/null
    fi
  )
}
# Remove the staging folder in the same way, by its name in the recorded
# dist/ folder (enter_dist), so through a dist that is no longer that
# folder it removes nothing.
remove_staging() {
  [ -n "${out}" ] || return 0
  (
    enter_dist && [ ! -L "./${out}" ] || exit 1
    if [ -n "${out_id}" ]; then
      [ "$(stat -c '%d:%i' -- "./${out}" 2>/dev/null)" = "${out_id}" ] \
        && rm -rf -- "./${out}"
    else
      rmdir -- "./${out}" 2>/dev/null
    fi
  )
}
# On each exit that runs this trap, which a SIGKILL does not, try to
# remove each work folder that the build made (remove_source and
# remove_staging): each only while its name still holds the folder that
# the build recorded, or, with no identity recorded, only while that name
# holds an empty folder; so a folder put in place of a work folder after
# the build recorded its identity stays.
# On a failed exit, which includes an exit through 1 of the
# signal traps above, also remove any output in dist/, so a failure during
# the first removal below, or during or after the move, leaves no zip and
# no .sha256 there, unless a removal fails or dist is no longer the folder
# recorded above. On a failed exit it removes no folder with a staging
# name but the staging folder of this build. Through a dist that is no
# longer that folder it removes nothing in dist/, not even the staging
# folder. Each
# removal runs whatever an earlier one returned, since a failed command
# would otherwise end the trap under set -e; an output or work folder that
# a failed removal leaves stays, and the build keeps its exit code, 0
# included. The trap ignores SIGHUP, SIGINT and
# SIGTERM while it runs, so 1 of them cannot cut its removals short, and it
# ends with the build's own exit code. It is set before the first removal,
# so a signal that ends that removal half done still has the rest of the
# outputs removed.
cleanup() {
  local rc=$?
  trap '' HUP INT TERM
  if [ "${rc}" -ne 0 ]; then
    remove_outputs || true
  fi
  remove_source || true
  remove_staging || true
  exit "${rc}"
}
trap cleanup EXIT

# Remove an earlier build's outputs directly after the refusal of a linked or
# non-folder dist and before every other check, so a build refused at a
# later check does not leave them in dist/ for a reader to take for its
# own. A failed removal ends the build here; the exit trap then tries the
# removal of each output once more, and what neither could remove stays. A
# dist that is not the recorded folder ends the build with the message for
# a replaced dist, and a dist that cd cannot enter with the message for
# that; then nothing has been removed.
removal_rc=0
remove_outputs with-staging || removal_rc=$?
case "${removal_rc}" in
  0) ;;
  2) fail "${DIST_REPLACED}" ;;
  3) fail "${DIST_UNREACHABLE}" ;;
  *) fail "could not remove every earlier output from dist/; any it could not remove is still there" ;;
esac

tag=""
release_date=""
release_date_given=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tag)
      [ $# -ge 2 ] || fail "--tag needs a value, for example --tag v1.0.12"
      shift; tag="$1" ;;
    --release-date)
      [ $# -ge 2 ] || fail "--release-date needs a YYYY-MM-DD value"
      shift; release_date="$1"; release_date_given=1 ;;
    *) fail "unknown argument $1" ;;
  esac
  shift
done

git cat-file -e HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md 2>/dev/null \
  || fail "cleanlanguage/skills/cleanlanguage/SKILL.md is missing at HEAD"
# The skill lives only under skills/cleanlanguage/ for Agent Plugins discovery;
# a stray copy at the legacy root would silently regress the layout, so fail on it.
if git cat-file -e HEAD:cleanlanguage/SKILL.md 2>/dev/null; then
  fail "cleanlanguage/SKILL.md must live only at cleanlanguage/skills/cleanlanguage/SKILL.md; a copy exists at the legacy root"
fi
skill="$(git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md)" \
  || fail "could not read cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"
# Read the version exactly as the two release gates do, so all three consumers
# agree on every input by construction instead of re-implementing the gates'
# parse in shell (three QA rounds found byte-level divergences that a shell
# re-implementation cannot fully reconcile: NUL location, invalid UTF-8, and CR
# line endings). This decodes the blob as UTF-8 with universal newlines, exactly
# as Path.read_text does, and applies the gates' own VERSION_LINE and
# SKILL_VERSION patterns verbatim (check-release-links.py and
# check-release-checksum-live.py), so the verdict and the extracted value are
# identical here and there.
if version="$(git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 -I -c '
import io
import re
import sys

try:
    text = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", newline=None).read()
except UnicodeDecodeError:
    sys.exit(4)
line = re.search(r"^Version:[^\n]*", text, re.M)
if line is None:
    sys.exit(2)
match = re.match(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$", line.group(0))
if match is None:
    sys.exit(3)
sys.stdout.write(match.group(1))
')"; then
  :
else
  case "$?" in
    2) fail "no Version: line found in cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD" ;;
    3) fail "the first Version: line in cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD is not a bare X.Y.Z version" ;;
    4) fail "cleanlanguage/skills/cleanlanguage/SKILL.md is not valid UTF-8 at HEAD" ;;
    *) fail "could not read the version from cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD" ;;
  esac
fi
if [ -n "${tag}" ] && [ "v${version}" != "${tag}" ]; then
  fail "SKILL.md version (${version}) does not match the tag (${tag})"
fi
# The outputs reach dist/ by a rename, which replaces whatever holds the
# name, and the exit trap then removes what it moved there. The removal above
# has removed every regular file at an output name, or the build has exited,
# so an object still at an output name is one that the packager does not
# write: a symbolic link (followed or not), folder, FIFO or other special
# file at 1 of the 4 names this build writes is refused here, before the
# build makes its first work folder or writes anything to dist/, and is left
# as it is.
for path in dist/cleanlanguage.zip "dist/cleanlanguage-${version}.zip" \
  dist/cleanlanguage.zip.sha256 "dist/cleanlanguage-${version}.zip.sha256"; do
  if [ -L "${path}" ] || { [ -e "${path}" ] && [ ! -f "${path}" ]; }; then
    fail "${path} exists and is not a regular file that the packager wrote; move it out of dist/ and build again"
  fi
done
# The Released line (item 26), read from HEAD through the one shared strict
# extractor, tools/skill-release-date.py, run in its --json mode by
# tools/skill-release-date-client.py (row 89). The client gives a content
# verdict only from a reply that meets the contract: exit 0 prints the date,
# 13 means no line, 11 is a malformed line, 14 means the client could not read
# its input (reported as unreadable input), and any other exit (16 when the
# client found the extractor unavailable, 1 or 2 from a broken or missing
# client, 127, an interpreter failure) means the tool is unavailable or
# crashed, which is reported as that, never as malformed content. The client
# is probed first (baseline), so a missing or broken tool fails here, before
# any content is judged. A malformed line fails whether or not --release-date
# is given. Both pipeline statuses are printed on a last line of their own and
# read explicitly, so a failed blob read never surfaces as the client exit 13
# (absent) that pipefail would otherwise report. A non-zero blob status is
# reported as a failed blob read, with one exception: a blob status of 141
# (git show ended by SIGPIPE) beside a client exit that is not a content
# verdict (0, 11 or 13) means the client ended before it read the whole blob,
# so the client's own exit and reason are reported instead. A content verdict
# is never taken beside a non-zero blob status, since it may rest on part of
# the blob.
# The client writes to one stream only: on exit 0 the value on stdout, and on
# any other exit its message on stderr with nothing on stdout. The probe, the
# check-date call, the first Released read and the requires-date call below
# capture both streams, so 5 branches relay the line in which the client
# names its reason (relay_client) before their own message: a failed probe, a
# check-date exit other than 0 or 11, a Released read exit of 14 (unreadable
# input) or of any exit other than 0, 11, 13 or 14, and a requires-date exit
# other than 0 or 11. The second Released read, for a malformed line (exit
# 11), captures stderr only, where the client writes its reason, and
# discards stdout. A value is checked for its form before it is used.
relay_client() {
  [ -z "$1" ] || printf '%s\n' "$1" >&2
}
probe_rc=0
baseline="$(python3 -I tools/skill-release-date-client.py baseline 2>&1)" || probe_rc=$?
if [ "${probe_rc}" -ne 0 ] || ! [[ "${baseline}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  relay_client "${baseline}"
  fail "tools/skill-release-date.py is unavailable or broken (probe exit ${probe_rc}), so the Released line could not be checked"
fi
if [ -n "${release_date_given}" ]; then
  check_rc=0
  checked="$(python3 -I tools/skill-release-date-client.py check-date "${release_date}" 2>&1)" || check_rc=$?
  case "${check_rc}" in
    0)
      # The client prints the day it was given; anything else is refused.
      [[ "${checked}" == "${release_date}" ]] \
        || fail "tools/skill-release-date.py gave an unexpected answer (${checked:-nothing}) checking --release-date ${release_date}"
      ;;
    11) fail "--release-date must be a real YYYY-MM-DD date, got ${release_date:-nothing}" ;;
    *)
      relay_client "${checked}"
      fail "tools/skill-release-date.py is unavailable or crashed (exit ${check_rc}) checking --release-date ${release_date:-nothing}"
      ;;
  esac
fi
# The substitution turns errexit off for itself, so its statuses are printed
# even when errexit is inherited (shopt -s inherit_errexit, or POSIX mode),
# where a failing client would otherwise end it, and set -e the packager,
# before any status was read.
read_out="$(
  set +e
  git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 -I tools/skill-release-date-client.py extract-stdin 2>&1
  statuses=("${PIPESTATUS[@]}")
  printf '\n%s %s' "${statuses[0]}" "${statuses[1]}"
)"
read_statuses="${read_out##*$'\n'}"
released="${read_out%$'\n'*}"
released="${released%$'\n'}"
blob_rc="${read_statuses% *}"
released_rc="${read_statuses#* }"
case "${blob_rc}:${released_rc}" in
  0:*) ;;
  141:0 | 141:11 | 141:13) fail "could not read cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD for its Released line" ;;
  141:*) ;;
  *) fail "could not read cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD for its Released line" ;;
esac
case "${released_rc}" in
  0)
    [[ "${released}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
      || fail "tools/skill-release-date.py gave an unexpected answer (${released:-nothing}) for the Released line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"
    ;;
  13) released="" ;;
  14)
    relay_client "${released}"
    fail "could not read cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD for its Released line: the client could not read its input (exit 14)"
    ;;
  11)
    fail "the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD is malformed: $(git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 -I tools/skill-release-date-client.py extract-stdin 2>&1 >/dev/null || true)"
    ;;
  *)
    relay_client "${released}"
    fail "tools/skill-release-date.py is unavailable or crashed (exit ${released_rc}) reading the Released line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"
    ;;
esac
if [ -z "${released}" ]; then
  # Without --release-date, absence is legitimate only at or below the
  # undated baseline (the release of an undated version, for example a re-run
  # of it); the extractor decides the comparison. A given --release-date has
  # no line to check, so its absence fails here at any version.
  req_rc=0
  requirement="$(python3 -I tools/skill-release-date-client.py requires-date "${version}" 2>&1)" || req_rc=$?
  case "${req_rc}" in
    0) ;;
    11) fail "tools/skill-release-date.py rejected the version ${version} as malformed: ${requirement}" ;;
    *)
      relay_client "${requirement}"
      fail "tools/skill-release-date.py is unavailable or crashed (exit ${req_rc}) deciding whether ${version} needs a Released line"
      ;;
  esac
  case "${requirement}" in
    optional)
      if [ -n "${release_date_given}" ]; then
        fail "--release-date ${release_date} was given, but SKILL.md at HEAD has no Released: line to check it against; add Released: ${release_date} directly after the Version line, or omit --release-date for an undated release at or below the undated baseline ${baseline}"
      fi
      ;;
    required)
      fail "SKILL.md at HEAD has no Released: line, but version ${version} sorts above the undated baseline ${baseline}; add Released: YYYY-MM-DD (the UTC release day) directly after the Version line"
      ;;
    *) fail "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for whether ${version} needs a Released line" ;;
  esac
elif [ -n "${release_date_given}" ] && [ "${released}" != "${release_date}" ]; then
  fail "SKILL.md Released date (${released}) at HEAD does not match the release date (${release_date}); re-stamp the Released line for the UTC day the release is published"
fi
# grep -Eq exits on the first match, so a here-string (not a printf pipe) avoids
# a SIGPIPE that set -o pipefail would turn into a spurious failure on a large
# SKILL.md.
grep -Eq '^name:[[:space:]]*cleanlanguage[[:space:]]*$' <<< "${skill}" \
  || fail "cleanlanguage/skills/cleanlanguage/SKILL.md is missing the 'name: cleanlanguage' line"

# The plugin manifests live in two places: marketplace.json at the repository
# root, which is what makes this repository a marketplace, and plugin.json
# inside cleanlanguage/.claude-plugin/, which makes cleanlanguage/ the plugin
# root so a marketplace install copies only the skill tree. The plugin
# manifest therefore sits inside the tree this script archives, and the
# layout step in the source folder below deliberately keeps it out of the
# zip: the zip is the skill artefact, and the plugin ships through the
# marketplace. The version, name, and source checks run here because this
# is the script that runs at release time. A version that disagrees with SKILL.md is exactly what would
# ship a plugin pinned to the wrong release, and a source that regresses to
# "./" is exactly what would ship the whole repository. Read from the git
# tree at HEAD, like everything else above, so a dirty working tree cannot
# pass a check the release would fail.
git cat-file -e HEAD:cleanlanguage/.claude-plugin/plugin.json 2>/dev/null \
  || fail "cleanlanguage/.claude-plugin/plugin.json is missing at HEAD"
git cat-file -e HEAD:.claude-plugin/marketplace.json 2>/dev/null \
  || fail ".claude-plugin/marketplace.json is missing at HEAD"

plugin_version="$(git show HEAD:cleanlanguage/.claude-plugin/plugin.json \
  | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("version",""))')"
[ "${plugin_version}" = "${version}" ] \
  || fail "plugin.json version (${plugin_version}) does not match SKILL.md (${version})"

plugin_name="$(git show HEAD:cleanlanguage/.claude-plugin/plugin.json \
  | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("name",""))')"
marketplace_name="$(git show HEAD:.claude-plugin/marketplace.json \
  | python3 -I -c 'import json,sys; d=json.load(sys.stdin); p=d.get("plugins") or [{}]; print(p[0].get("name",""))')"
[ -n "${plugin_name}" ] || fail "plugin.json has no name at HEAD"
[ "${marketplace_name}" = "${plugin_name}" ] \
  || fail "marketplace.json plugins[0].name (${marketplace_name}) does not match plugin.json name (${plugin_name})"

marketplace_source="$(git show HEAD:.claude-plugin/marketplace.json \
  | python3 -I -c 'import json,sys; d=json.load(sys.stdin); p=d.get("plugins") or [{}]; print(p[0].get("source",""))')"
[ "${marketplace_source}" = "./cleanlanguage" ] \
  || fail "marketplace.json plugins[0].source (${marketplace_source}) must be ./cleanlanguage so an install ships only the skill tree"

bad_modes="$(git ls-tree -r HEAD -- cleanlanguage | awk '$1 != "100644"')"
if [ -n "${bad_modes}" ]; then
  printf 'release-package: every packaged file must be a regular, non-executable file (git mode 100644); found:\n%s\n' "${bad_modes}" >&2
  exit 1
fi

files="$(git ls-tree -r HEAD --name-only -- cleanlanguage)"
[ -n "${files}" ] || fail "git records no files under cleanlanguage/"
grep -Eq '^cleanlanguage/skills/cleanlanguage/references/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.md$' <<< "${files}" \
  || fail "cleanlanguage/skills/cleanlanguage/references holds no Markdown reference at HEAD"
unexpected="$(printf '%s\n' "${files}" | grep -Ev \
  '^cleanlanguage/(plugin\.json|skills/cleanlanguage/SKILL\.md|\.claude-plugin/plugin\.json|agents/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.yaml|assets/CL_icon\.(png|svg)|skills/cleanlanguage/references/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.md)$' \
  || true)"
if [ -n "${unexpected}" ]; then
  printf 'release-package: paths outside the package allowlist:\n%s\n' "${unexpected}" >&2
  exit 1
fi

# Any icon the ChatGPT interface config references must exist in the package,
# so a shipped skill never points at a missing asset. The path may be quoted
# with double quotes, single quotes, or left bare.
if git cat-file -e HEAD:cleanlanguage/agents/openai.yaml 2>/dev/null; then
  # Validate the ChatGPT icon references entirely in Python, so nothing is
  # serialized through newline-delimited shell: parse the YAML, walk it at any
  # depth, reject a value that is missing, empty, or carries a control
  # character, resolve an optional ./, confirm the git blob exists at HEAD, and
  # require at least one icon_ key so the check can never become vacuous.
  git show HEAD:cleanlanguage/agents/openai.yaml | python3 -I -c '
import sys, subprocess
try:
    import yaml
except ImportError:
    sys.stderr.write("release-package: PyYAML is required to validate agents/openai.yaml icons.\n")
    sys.exit(1)
data = yaml.safe_load(sys.stdin)
bad = False
found = 0
def check(key, value):
    global bad
    if not isinstance(value, str) or not value.strip():
        sys.stderr.write("release-package: icon key %s has no usable path.\n" % key); bad = True; return
    p = value.strip()
    if any(ord(c) < 32 for c in p):
        sys.stderr.write("release-package: icon key %s has a control character.\n" % key); bad = True; return
    rel = p[2:] if p.startswith("./") else p
    if not rel:
        sys.stderr.write("release-package: icon key %s resolves to an empty path.\n" % key); bad = True; return
    if subprocess.call(["git", "cat-file", "-e", "HEAD:cleanlanguage/" + rel],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        sys.stderr.write("release-package: icon referenced in agents/openai.yaml is missing: %s\n" % rel); bad = True
def walk(node):
    global found
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and k.startswith("icon_"):
                found += 1; check(k, v)
            else:
                walk(v)
    elif isinstance(node, list):
        for item in node:
            walk(item)
walk(data)
if found == 0:
    sys.stderr.write("release-package: no icon_ keys found in agents/openai.yaml; the icon check would be vacuous.\n")
    sys.exit(1)
sys.exit(1 if bad else 0)
' || exit 1
fi

# The source folder under TMPDIR. mktemp gives its name, not a handle on it,
# so the build reads its device and inode by that name directly after
# mktemp makes it, and from then on reaches it only through enter_source
# (to_source), with git writing to a pipe that a subshell in that folder
# reads. The exit trap removes it by its name in the folder that holds it
# (remove_source).
source_dir="$(mktemp -d)"
case "${source_dir}" in
  */*)
    source_parent="${source_dir%/*}"
    source_parent="${source_parent:-/}"
    ;;
  *) source_parent=. ;;
esac
source_name="${source_dir##*/}"
[ ! -L "${source_dir}" ] || fail "${WORK_REPLACED}"
# A failed read ends the build here under set -e, with the exit code of
# stat, before source_id is assigned, so no output of a failed stat is
# recorded as the identity.
source_read="$(stat -c '%d:%i' -- "${source_dir}")"
source_id="${source_read}"
git archive --format=tar HEAD cleanlanguage | (
  to_source
  tar -xf -
  # Keep the downloadable skill zip free of plugin metadata: the Claude
  # manifest (.claude-plugin/plugin.json) and the Agent Plugins manifest (the
  # root plugin.json) both ship through the marketplace install, never
  # through the zip. rmdir, not rm -rf, so an unexpected extra file under
  # .claude-plugin/ fails the build loudly instead of being discarded.
  rm cleanlanguage/plugin.json
  rm cleanlanguage/.claude-plugin/plugin.json
  rmdir cleanlanguage/.claude-plugin
  # The source keeps SKILL.md and references/ under skills/cleanlanguage/ for
  # Agent Plugins discovery; Claude, ChatGPT, and Copilot Studio load the zip
  # only with SKILL.md at the archive root, so restore the root layout here.
  # rmdir, not rm -rf, so an unexpected extra entry under skills/ fails loudly.
  mv cleanlanguage/skills/cleanlanguage/SKILL.md cleanlanguage/SKILL.md
  mv cleanlanguage/skills/cleanlanguage/references cleanlanguage/references
  rmdir cleanlanguage/skills/cleanlanguage
  rmdir cleanlanguage/skills
)
git show HEAD:LICENSE | (to_source; cat > cleanlanguage/LICENSE)
git show HEAD:NOTICE.md | (to_source; cat > cleanlanguage/NOTICE.md)

# A byte-reproducible archive: stamp every path in the source folder with the
# commit's own timestamp, order the entries, and read the DOS times in UTC,
# so the same commit always yields the same zip and therefore the same
# checksum, on any machine and at any clock time. Without this the licence
# files written to the source folder would carry the build clock, so a
# later rebuild of the same commit would not match.
commit_epoch="$(git show -s --format=%ct HEAD)"
# Canonical, umask-independent modes for a distributed artefact: the packaged
# files carry only regular content (the mode gate above rejects anything but
# 100644), so normalize every directory to 0755 and every file to 0644. Zip
# records the Unix mode in each entry, so without this an ambient umask would
# change the central-directory bytes and the checksum for the same commit.
(
  to_source
  chmod 644 cleanlanguage/LICENSE cleanlanguage/NOTICE.md
  find . -type d -exec chmod 755 {} +
  find . -type f -exec chmod 644 {} +
  find . -exec touch -h -d "@${commit_epoch}" {} +
)

mkdir -p dist
if [ -z "${dist_id}" ] && [ ! -L dist ]; then
  dist_id="$(stat -c '%d:%i' -- dist)" || fail "${DIST_ID_FAILED}"
  [[ "${dist_id}" =~ ^[0123456789]+:[0123456789]+$ ]] || fail "${DIST_ID_FAILED}"
fi
# Checked after the build makes dist/, so that a dist replaced before then
# ends the build with this message.
same_dist || fail "${DIST_REPLACED}"
# Build and verify in a staging folder inside dist/, on the same filesystem,
# so the move after the checks is a rename and no unverified output ever sits
# under an output name in dist/. mktemp runs in the recorded dist/ folder,
# with a template relative to it, and gives the name of the folder that it
# made there; the build reads the device and inode of that name in the same
# folder directly after, and refuses a name that is then a symbolic link.
# As for the source folder, a failed read ends the build before out_id is
# assigned.
out="$(to_dist; mktemp -d .release-package.XXXXXX)"
out_read="$(
  to_dist
  { [ -d "./${out}" ] && [ ! -L "./${out}" ]; } || fail "${WORK_REPLACED}"
  stat -c '%d:%i' -- "./${out}"
)"
out_id="${out_read}"
# Clear ZIP and ZIPOPT so an ambient option (for example ZIPOPT=-0) cannot
# change the archive bytes; -D omits directory records (whose modes and order
# would otherwise vary); -X drops uid/gid and the extra timestamp fields; the
# sorted list and TZ=UTC fix entry order and the DOS times. Same commit, same
# bytes at any clock time and umask, given the same zip binary. zip writes
# the archive in the source folder, beside the files it zips, since it
# cannot both read names relative to 1 folder and write into another that
# the build has entered; a subshell in the source folder then gives its
# bytes through a pipe to a subshell in the staging folder, which writes
# them there. The checks below read only that staged copy.
(
  to_source
  cd ./cleanlanguage
  find . -type f -printf '%P\n' | LC_ALL=C sort \
    | env -u ZIP -u ZIPOPT TZ=UTC zip -q -X -D -@ ../cleanlanguage.zip
)
(to_source; cat cleanlanguage.zip) | (to_staging; cat > cleanlanguage.zip)
(
  to_staging
  cp cleanlanguage.zip "cleanlanguage-${version}.zip"
  sha256sum cleanlanguage.zip > cleanlanguage.zip.sha256
  sha256sum "cleanlanguage-${version}.zip" > "cleanlanguage-${version}.zip.sha256"
)

expected="$(
  {
    printf '%s\n' "${files}" \
      | grep -Fvx 'cleanlanguage/.claude-plugin/plugin.json' \
      | grep -Fvx 'cleanlanguage/plugin.json' \
      | sed 's#^cleanlanguage/skills/cleanlanguage/#cleanlanguage/#' \
      | sed 's#^cleanlanguage/##'
    printf 'LICENSE\nNOTICE.md\n'
  } | LC_ALL=C sort
)"
actual="$( (to_staging; unzip -Z1 cleanlanguage.zip) | grep -v '/$' | LC_ALL=C sort)"
if [ "${expected}" != "${actual}" ]; then
  echo "release-package: the archive entry list does not match the git tree:" >&2
  diff <(printf '%s\n' "${expected}") <(printf '%s\n' "${actual}") >&2 || true
  exit 1
fi

# Lock in the root-level layout. Claude, ChatGPT, and Copilot Studio all load
# the skill only when SKILL.md sits at the archive root, so fail if the build
# ever regresses to a wrapping cleanlanguage/ directory. The entry-list check
# above proves the zip matches its own expected list; this proves that list is
# rooted, which a coordinated revert of the zip and expected-list lines would
# otherwise slip past.
if grep -q '^cleanlanguage/' <<< "${actual}"; then
  echo "release-package: the archive must place files at the root, but found cleanlanguage/-prefixed entries" >&2
  exit 1
fi
grep -qx 'SKILL.md' <<< "${actual}" \
  || fail "SKILL.md is not at the archive root"

# The source nests the skill under skills/cleanlanguage/; the layout step in
# the source folder above re-roots it, so a surviving skills/ entry means
# that re-root was dropped.
if grep -q '^skills/' <<< "${actual}"; then
  echo "release-package: the archive must not carry a skills/ subtree" >&2
  exit 1
fi

# The entry-list check above already excludes the plugin manifest, but a
# coordinated revert of the rm in the source folder and the expected-list
# filter would put the manifest in both lists and slip past it, the same
# shape the root-layout check above guards for its own pair of lines. This
# proves the shipped zip itself carries no plugin metadata.
if grep -q '^\.claude-plugin/' <<< "${actual}"; then
  echo "release-package: the plugin manifest must not ship in the skill zip" >&2
  exit 1
fi

if grep -qx 'plugin.json' <<< "${actual}"; then
  echo "release-package: the Agent Plugins manifest (plugin.json) must not ship in the skill zip" >&2
  exit 1
fi

# Every archived byte must equal its git blob, so a git attribute such as
# export-subst cannot alter the shipped content while leaving the names intact.
while IFS= read -r entry; do
  [ -n "${entry}" ] || continue
  case "${entry}" in
    LICENSE) blob="HEAD:LICENSE" ;;
    NOTICE.md) blob="HEAD:NOTICE.md" ;;
    SKILL.md) blob="HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md" ;;
    references/*) blob="HEAD:cleanlanguage/skills/cleanlanguage/${entry}" ;;
    *) blob="HEAD:cleanlanguage/${entry}" ;;
  esac
  if ! cmp -s <(to_staging; unzip -p cleanlanguage.zip "${entry}") <(git cat-file blob "${blob}"); then
    echo "release-package: archived ${entry} differs from its git blob (${blob})" >&2
    exit 1
  fi
done <<EOF_ENTRIES
${actual}
EOF_ENTRIES

# Every check passed. Move the 2 zips into dist/, then their .sha256 files, so a
# .sha256 that a build moved into dist/ has its zip beside it, unless a
# removal, at the start of a later build or in an exit trap, removed that
# zip and then failed to remove the .sha256, or a SIGKILL ended a later
# build during its first removal. The moves run in the staging folder,
# entered through the recorded dist/ folder, and name their target as ..,
# the folder that holds the staging folder, after a check that .. is the
# recorded dist/ folder; so a dist renamed or replaced after these checks
# does not change where the outputs go.
same_dist || fail "${DIST_REPLACED}"
(
  to_staging
  [ "$(stat -c '%d:%i' -- ..)" = "${dist_id}" ] || fail "${WORK_REPLACED}"
  mv -f cleanlanguage.zip "cleanlanguage-${version}.zip" ..
  mv -f cleanlanguage.zip.sha256 "cleanlanguage-${version}.zip.sha256" ..
)

echo "release-package: dist/cleanlanguage-${version}.zip built and verified for version ${version}."
printf '%s\n' "${actual}" | sed 's/^/  /'
