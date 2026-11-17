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
#   5. Lays out the package from git archive in src/ of its work folder,
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
#      and 6 run in 1 work folder that the build makes in dist/ with mktemp
#      (dist/.release-package.XXXXXX, mode 0700), so no unverified output
#      ever sits under an output name in dist/.
#
# It writes dist/cleanlanguage.zip, dist/cleanlanguage-<version>.zip, and a
# .sha256 beside each, only after every check passes.
#
# What it removes. Recursively, it removes only its own work folder, by the
# path that mktemp gave in this run; it never removes recursively a folder
# that it did not make in this run. Non-recursively, it removes each regular
# file in dist/ named cleanlanguage.zip or cleanlanguage-X.Y.Z.zip (X, Y and
# Z each 1 or more ASCII digits) or the .sha256 of either, before every
# check but the refusal of a linked or non-folder dist, and again on a
# failed exit, so that a refused build leaves no zip and no .sha256 that a
# reader could take for its own. It keeps every other entry of dist/,
# among them a folder with a work-folder name (.release-package. and 6
# characters) that an earlier build left: it removes such a folder only
# when this run made it. It makes dist/ before it lays out the package, so a
# build that fails after that point and started with no dist/ leaves an
# empty dist/.
#
# What it refuses, each with exit 1 and a message: a dist that is a
# symbolic link or that exists and is not a folder, before it removes
# anything; a removal at the start that fails; an object other than a
# regular file at 1 of the 4 names it writes, once it knows the version
# and before it makes dist/ or its work folder; and a dist that is a
# symbolic link after it makes dist/. It moves each output from its work
# folder to the folder that holds the work folder, so the outputs land
# beside the folder that this run made; if that folder is no longer at the
# path that mktemp gave, the move fails, and so does the build.
#
# What it does not defend against, by decision: another process of the
# same user that renames or replaces dist/, the work folder or an entry of
# either while the build runs. Such a process can write to dist/ directly,
# and the packager reaches dist/ and its work folder by their paths, which
# such a process can change between 2 uses, so a use can reach another
# folder than the one that a check just before saw. The packager makes no
# claim for that case.
#
# A signal whose default action ends a process ends the build with exit 128
# plus the signal's number, such as 129, 130 or 143 for SIGHUP, SIGINT or
# SIGTERM, once the command in progress has ended, and counts as a failed
# exit, unless the signal was ignored when the build started (as SIGHUP is
# under nohup): bash cannot trap such a signal, so it does not end the
# build. A signal whose name the kill -l of the running shell does not
# know is left out of the traps, rather than ending the build at its
# start (see the traps below). The exit trap ignores the trapped signals
# while it runs, so 1 that arrives then leaves the exit code as it was,
# and its own commands inherit that, so 1 sent to the whole process group
# cannot end them either. A signal that arrives before the exit trap is
# set, when the build has removed and written nothing, leaves dist/ as it
# was. A refused build therefore leaves in dist/ no zip
# and no .sha256, unless a removal itself fails: the build then still
# fails, and an output that it could not remove stays. 3 signals that end
# a process run no trap: SIGKILL, which no process can trap, and signals 32
# and 33, which the C library keeps for its own use, so that a trap that
# bash sets for them does not take effect. Such a signal can leave the work
# folder in dist/ and, during the moves, a zip without its .sha256; the
# next build removes such outputs and keeps the folder.
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
#   128 + n      ended by the signal numbered n, from 129 to 192, such as
#                129, 130 and 143 for SIGHUP, SIGINT and SIGTERM, unless
#                that signal was ignored when the build started
#   other codes  the exit code of a command that failed, such as zip, mv
#                or git, which set -e passes through unchanged and the
#                exit trap keeps; such a command can also give 1 or 1 of
#                the codes from 129 to 192

set -euo pipefail

# Glob and match options can come from the environment (BASHOPTS or
# SHELLOPTS) or from a file that BASH_ENV names: failglob would end the
# removal below at a glob that matches nothing, noglob would hide the
# entries of dist/ from it, and nocasematch would let its name test match
# a name in another letter case. A GLOBIGNORE that the shell assigns drops
# the names it matches from what a glob gives. Bash 5.3.9 does not apply a
# GLOBIGNORE taken from the environment, but it does apply one that a
# BASH_ENV file assigns. So GLOBIGNORE is unset and these options are set
# here: the glob * in dist/ gives the entries of dist/, names that start
# with a dot included, and the name test alone chooses what is removed. With
# no entry in dist/, the glob gives the word * itself, which the name test
# does not match and which is not a file, so the removal
# does nothing, as it would with nullglob. CDPATH is unset as well, so that
# cd enters the folder that its relative name gives here, not 1 that CDPATH
# gives. An option that the running shell does not know cannot be on, so it
# is left alone rather than ending the build under set -e, as a signal name
# that the shell does not know is below; shopt -p prints a line only for an
# option that the shell knows, and each such option is turned off.
unset GLOBIGNORE CDPATH
set +f
for shell_option in extglob failglob globstar nocaseglob nocasematch; do
  if [ -n "$(shopt -p "${shell_option}" 2>/dev/null)" ]; then
    shopt -u "${shell_option}"
  fi
done
shopt -s dotglob

# Without a trap, bash meets a signal whose default action ends a process
# in 1 of 3 ways, none of them a failed exit that the exit trap below can
# rely on: it ends at once and runs no exit trap; it runs the exit trap at
# once, with the status of the last command, which is 0 after a command
# that succeeded, so that the trap reads a good exit, while a command in
# progress, such as a move into dist/, still runs; or, for SIGINT and
# SIGQUIT that arrive while a command runs, it can go on with the build. So
# each such signal that bash can trap exits with 128 plus its number; bash
# runs such a trap once the command in progress has ended. They are the
# signals from 1 to the last real-time signal, except SIGKILL, which no
# process can trap; SIGSTOP, SIGTSTP, SIGTTIN and SIGTTOU, which stop a
# process; SIGCHLD, SIGCONT, SIGURG and SIGWINCH, which do not end one; and
# signals 32 and 33, for which a trap does not take effect. The exit trap
# ignores the signals of signal_numbers while it runs. The numbers come
# from the kill -l of the running shell, and a name that it does not know
# is left out rather than ending the build under set -e: not every
# platform has SIGSTKFLT, SIGPWR or the real-time signals, whose range is
# left out unless the shell knows both SIGRTMIN and SIGRTMAX. POSIX
# requires every shell to know SIGHUP, SIGINT and SIGTERM, so the list is
# never empty.
signal_numbers=()
for signal_name in HUP INT QUIT ILL TRAP ABRT BUS FPE USR1 SEGV USR2 PIPE \
  ALRM TERM STKFLT XCPU XFSZ VTALRM PROF IO PWR SYS; do
  if signal_number="$(kill -l "${signal_name}" 2>/dev/null)"; then
    signal_numbers+=("${signal_number}")
  fi
done
if first_signal="$(kill -l RTMIN 2>/dev/null)" && last_signal="$(kill -l RTMAX 2>/dev/null)"; then
  for ((signal_number = first_signal; signal_number <= last_signal; signal_number++)); do
    signal_numbers+=("${signal_number}")
  done
fi
for signal_number in "${signal_numbers[@]}"; do
  trap "exit $((128 + signal_number))" "${signal_number}"
done

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

# Remove each regular file in dist/ with an output name, and nothing else: no
# folder, no symbolic link and no entry of any other name, so a folder with
# a work-folder name that an earlier build left stays. An output name is
# cleanlanguage.zip, cleanlanguage-X.Y.Z.zip or the .sha256 of either, where
# X, Y and Z are 1 or more ASCII digits. The name test lists each digit, not
# a range such as [0-9]: a range in a bash =~ test follows the locale, and
# under LC_ALL=en_US.UTF-8 it also takes digits outside ASCII, such as an
# Arabic-Indic digit. The removal enters dist/ once, in a subshell, and
# removes each entry by its name there; rm -f removes a symbolic link put at
# that name in between without following it. Each removal is tried, so a
# failed removal does not stop the others; the status is 1 if 1 or more
# failed or cd cannot enter dist/. With no dist/ folder there is nothing to
# remove.
remove_outputs() {
  local output_name='^cleanlanguage(-[0123456789]+\.[0123456789]+\.[0123456789]+)?\.zip(\.sha256)?$'
  { [ -d dist ] && [ ! -L dist ]; } || return 0
  (
    cd -P -- ./dist || exit 1
    rc=0
    for name in *; do
      if [[ "${name}" =~ ${output_name} ]] && [ -f "./${name}" ] && [ ! -L "./${name}" ]; then
        rm -f -- "./${name}" || rc=1
      fi
    done
    exit "${rc}"
  )
}

# The path of the 1 work folder of this run, as mktemp gave it; empty until
# mktemp has made it.
work=""
# On each exit that runs this trap (SIGKILL and signals 32 and 33 do not):
# on a failed exit, which includes an exit through 1 of the signal traps
# above, remove the outputs in dist/ again, so that a failure during the
# first removal below or during the moves leaves none, unless a removal
# fails; then, on any exit, remove the work folder of this run by the path
# that mktemp gave. This rm -rf is the only recursive removal of the
# packager. Each removal runs whatever the one before it returned, since a
# failed command would otherwise end the trap under set -e; what a failed
# removal leaves stays, and the build keeps its exit code, 0 included. The
# trap ignores the signals that the traps above catch while it runs, so 1
# of them cannot cut its removals short: the subshell and the rm of each
# removal inherit an ignored signal, while a handler, even 1 that does
# nothing, would be reset to the default action in them, and a signal
# sent to the whole process group would end them. It ends with the build's
# own exit code. It is set before the first removal, so a signal that ends
# that removal half done still has the rest of the outputs removed.
cleanup() {
  local rc=$?
  trap '' "${signal_numbers[@]}"
  if [ "${rc}" -ne 0 ]; then
    remove_outputs || true
  fi
  if [ -n "${work}" ]; then
    rm -rf -- "${work}" || true
  fi
  exit "${rc}"
}
trap cleanup EXIT

# Remove an earlier build's outputs directly after the refusal of a linked or
# non-folder dist and before every other check, so a build refused at a
# later check does not leave them in dist/ for a reader to take for its
# own. A failed removal ends the build here; the exit trap then tries the
# removal of each output once more, and what neither could remove stays.
remove_outputs \
  || fail "could not remove every earlier output from dist/; any it could not remove is still there"

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
# build makes dist/ or its work folder or writes anything to dist/, and is
# left as it is.
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
# layout step in the work folder below deliberately keeps it out of the
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

# The work folder: 1 folder that this run makes in dist/ with mktemp, mode
# 0700, on the filesystem of dist/, so that each move into dist/ is a
# rename. dist/ is made here, before the layout, and a dist that is a
# symbolic link at this point is refused before mktemp runs. The layout
# goes in src/ of the work folder and the outputs beside src/. The exit
# trap removes the work folder by the path that mktemp gave.
mkdir -p dist
[ ! -L dist ] || fail "dist is a symbolic link; the packager writes only into a real dist/ folder"
work="$(mktemp -d "${PWD}/dist/.release-package.XXXXXX")"
mkdir "${work}/src"
git archive --format=tar HEAD cleanlanguage | tar -xf - -C "${work}/src"
# Keep the downloadable skill zip free of plugin metadata: the Claude
# manifest (.claude-plugin/plugin.json) and the Agent Plugins manifest (the
# root plugin.json) both ship through the marketplace install, never
# through the zip. rmdir, not rm -rf, so an unexpected extra file under
# .claude-plugin/ fails the build loudly instead of being discarded.
rm "${work}/src/cleanlanguage/plugin.json"
rm "${work}/src/cleanlanguage/.claude-plugin/plugin.json"
rmdir "${work}/src/cleanlanguage/.claude-plugin"
# The source keeps SKILL.md and references/ under skills/cleanlanguage/ for
# Agent Plugins discovery; Claude, ChatGPT, and Copilot Studio load the zip
# only with SKILL.md at the archive root, so restore the root layout here.
# rmdir, not rm -rf, so an unexpected extra entry under skills/ fails loudly.
mv "${work}/src/cleanlanguage/skills/cleanlanguage/SKILL.md" "${work}/src/cleanlanguage/SKILL.md"
mv "${work}/src/cleanlanguage/skills/cleanlanguage/references" "${work}/src/cleanlanguage/references"
rmdir "${work}/src/cleanlanguage/skills/cleanlanguage"
rmdir "${work}/src/cleanlanguage/skills"
git show HEAD:LICENSE > "${work}/src/cleanlanguage/LICENSE"
git show HEAD:NOTICE.md > "${work}/src/cleanlanguage/NOTICE.md"

# A byte-reproducible archive: stamp every path in src/ with the
# commit's own timestamp, order the entries, and read the DOS times in UTC,
# so the same commit always yields the same zip and therefore the same
# checksum, on any machine and at any clock time. Without this the licence
# files written to src/ would carry the build clock, so a
# later rebuild of the same commit would not match.
commit_epoch="$(git show -s --format=%ct HEAD)"
# Canonical, umask-independent modes for a distributed artefact: the packaged
# files carry only regular content (the mode gate above rejects anything but
# 100644), so normalize every directory to 0755 and every file to 0644. Zip
# records the Unix mode in each entry, so without this an ambient umask would
# change the central-directory bytes and the checksum for the same commit.
(
  cd -- "${work}/src"
  chmod 644 cleanlanguage/LICENSE cleanlanguage/NOTICE.md
  find . -type d -exec chmod 755 {} +
  find . -type f -exec chmod 644 {} +
  find . -exec touch -h -d "@${commit_epoch}" {} +
)

# Clear ZIP and ZIPOPT so an ambient option (for example ZIPOPT=-0) cannot
# change the archive bytes; -D omits directory records (whose modes and order
# would otherwise vary); -X drops uid/gid and the extra timestamp fields; the
# sorted list and TZ=UTC fix entry order and the DOS times. Same commit, same
# bytes at any clock time and umask, given the same zip binary. zip reads
# the files in src/cleanlanguage/ and writes the archive beside src/ in the
# work folder, where the build also makes the version-named copy and both
# .sha256 files; the checks below read that staged zip.
(
  cd -- "${work}/src/cleanlanguage"
  find . -type f -printf '%P\n' | LC_ALL=C sort \
    | env -u ZIP -u ZIPOPT TZ=UTC zip -q -X -D -@ "${work}/cleanlanguage.zip"
)
(
  cd -- "${work}"
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
actual="$(unzip -Z1 "${work}/cleanlanguage.zip" | grep -v '/$' | LC_ALL=C sort)"
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
# the work folder above re-roots it, so a surviving skills/ entry means
# that re-root was dropped.
if grep -q '^skills/' <<< "${actual}"; then
  echo "release-package: the archive must not carry a skills/ subtree" >&2
  exit 1
fi

# The entry-list check above already excludes the plugin manifest, but a
# coordinated revert of the rm in the work folder and the expected-list
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
  if ! cmp -s <(unzip -p "${work}/cleanlanguage.zip" "${entry}") <(git cat-file blob "${blob}"); then
    echo "release-package: archived ${entry} differs from its git blob (${blob})" >&2
    exit 1
  fi
done <<EOF_ENTRIES
${actual}
EOF_ENTRIES

# Every check passed. Move the 2 zips into dist/, then their .sha256 files, so a
# .sha256 that a build moved into dist/ has its zip beside it, unless a
# removal, at the start of a later build or in an exit trap, removed that
# zip and then failed to remove the .sha256, or a signal that runs no trap
# (SIGKILL, or signal 32 or 33) ended a later build during its first
# removal. Each of the 4 moves is a rename from the work folder to the
# folder that holds it, named as .. of the work folder,
# so the outputs land beside the work folder of this run; if that folder is
# no longer at the path that mktemp gave, the move fails. -T makes mv treat
# the target as a name, never as a folder to move into, so a folder put at
# an output name after the refusal above makes the move fail.
for name in cleanlanguage.zip "cleanlanguage-${version}.zip" \
  cleanlanguage.zip.sha256 "cleanlanguage-${version}.zip.sha256"; do
  mv -fT -- "${work}/${name}" "${work}/../${name}"
done

echo "release-package: dist/cleanlanguage-${version}.zip built and verified for version ${version}."
printf '%s\n' "${actual}" | sed 's/^/  /'
