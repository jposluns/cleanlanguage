#!/usr/bin/env bash
#
# Proves the local, side-effect-free part of the release path without publishing.
#
# The release path does four things a test can prove without touching GitHub:
# validate and package the skill, rewrite the site at the new release, stamp the
# modified dates that rewrite implies, and satisfy the gates the site pull
# request must pass. This script runs all four against a throwaway git worktree,
# at a synthetic next version, and asserts the results. The side-effecting steps
# are deliberately absent here: the tag push and gh release stay in the workflow,
# the site checksum flip and its pull request are performed by the orchestrator
# out of band after the release publishes, and this script contains no gh call
# and no git push. At exit it proves, reading the worktree that holds this
# script (repo_root, called the script's worktree below, which is the main
# worktree when the script is run from there, as release-dry-run.yml runs
# it), that it moved no tag, no note, and not the HEAD of the script's
# worktree (the branch HEAD names and the commit HEAD resolves to), and that
# no ref that git for-each-ref lists from the script's worktree contains the
# dry-run commit, read with replace refs, the graft file and the shallow file
# turned off. A ref that another worktree writes during the run fails the
# proof only when it is a tag or a note, when it is the HEAD of the script's
# worktree or the branch that worktree has checked out, or when it is such a
# listed ref created or moved onto the dry-run commit or a descendant of it;
# any other such write is outside the proof. The dry-run commit is the commit
# that git commit-tree writes and prints, which the script saves and step 6
# reads, never a later HEAD. Every git call of the script after the before
# snapshot other than the reads of step 6, the exit cleanup's git worktree
# remove included, runs with hooks, the core.fsmonitor program and a pager
# turned off, whatever the configuration asks, and every git process of the
# dry run runs with lazy fetching from a promisor remote turned off. Every git
# process of the dry run that starts after the first 3 git calls that follow
# the before snapshot, its tools' included, reads no attribute file other
# than the info/attributes file of the repository and, in git archive, the
# .gitattributes files of the tree it archives, and runs with the clean,
# smudge and process commands turned off of every filter driver that the
# configuration read from the script's worktree defines or that the
# info/attributes file names, and, from the dry-run commit on, of every one
# that an attribute gives a path of that commit; those 3 calls list the filter
# drivers, find the info/attributes file and name the empty tree, and read no
# index and no file of a worktree. So no filter runs during a git call of the
# dry run, whatever the configuration that git reads in any worktree defines,
# other than a driver that the info/attributes file, or the tree that git
# archive archives, comes to name during the run. The run fails unless git
# refuses a GIT_ATTR_SOURCE that names no tree. No git call of the script asks
# for a textconv or diff driver, a signature, an editor or automatic
# maintenance, and the reads of the 2 snapshots and the leak check read no
# index and no file content and write to no terminal. So no other program that
# git can run from its configuration or from attributes runs during a git call
# of the script, and the run fails unless the HEAD of the throwaway worktree
# is at the dry-run commit once the script has moved it there. The git calls
# of the tools that the script runs are covered only by the lazy-fetch,
# attribute and filter settings.
#
# Residual: the proof does not catch the deletion of any ref outside tags and
# notes other than the branch the script's worktree has checked out, such as
# another branch, a remote-tracking ref, refs/stash or a refs/replace/ ref; or
# a move or creation of such a ref at a commit that does not contain the
# dry-run commit, or at an object that peels to no commit, such as a tree or a
# blob. It does not see the HEAD or the per-worktree refs of any
# worktree other than the script's worktree, the throwaway worktree included,
# or a ref outside refs/ other than HEAD, such as ORIG_HEAD, of any worktree,
# the script's worktree included, so such a ref put on the dry-run commit does
# not fail it. It does not see anything the exit cleanup does, or a ref moved
# and then restored between the 2 snapshots.
#
# To keep the date-stamp proof honest, the worktree's modified-date fields are
# first seeded with an old sentinel, so the gates and the assertions can only
# pass if the writer actually restamps them. Without the seed the proof would
# be vacuous on any day the pages were last stamped that same day.
#
# The dry run proves HEAD, never the working tree: commit first, then run it.
#
# Usage:
#   tools/release-dry-run.sh
#
# DRY_DATE overrides the stamped date (YYYY-MM-DD). It defaults to today in
# UTC, the date a real release run would stamp. The clock is read once, here,
# and injected everywhere a date is needed, so every assertion compares
# against the same value.
#
# Exit codes:
#   0  every step, gate, and assertion passed
#   1  something failed

set -euo pipefail

# Read every date in UTC, exactly as the release runner does, so a dry run
# west of UTC in the evening does not stamp tomorrow's local date and fail its
# own metadata gate.
export TZ=UTC
# A missing object fails a git call of the dry run, its tools' included,
# instead of fetching it from a promisor remote with the programs that a fetch
# starts.
export GIT_NO_LAZY_FETCH=1

cd "$(dirname "${BASH_SOURCE[0]}")/.."
repo_root="$(pwd)"

fail() {
  printf 'release-dry-run: %s\n' "$1" >&2
  exit 1
}

# ref_snapshot: print, reading the script's worktree at repo_root, the refs
# that step 6 compares: the branch HEAD names, or "detached"; the commit HEAD
# resolves to; and every tag and note with its object name. An empty tag and
# note listing is legitimate. Any git error fails the run, so an error is never
# read as an empty listing.
ref_snapshot() {
  local head_ref head_rc=0 head_commit listing
  head_ref="$(git -C "${repo_root}" symbolic-ref -q HEAD)" || head_rc=$?
  case "${head_rc}" in
    0) ;;
    1) head_ref="detached" ;;
    *) fail "could not read the branch HEAD names in ${repo_root} (git symbolic-ref exit ${head_rc})" ;;
  esac
  head_commit="$(git -C "${repo_root}" rev-parse --verify -q HEAD)" \
    || fail "could not resolve HEAD to a commit in ${repo_root}"
  listing="$(git -C "${repo_root}" for-each-ref --format='%(objectname) %(refname)' refs/tags refs/notes)" \
    || fail "could not list the tags and notes of ${repo_root}"
  printf 'HEAD ref: %s\nHEAD commit: %s\n%s\n' "${head_ref}" "${head_commit}" "${listing}"
}

# ref_leak_check COMMIT: fail unless no ref that git for-each-ref lists from
# repo_root contains COMMIT, the dry-run commit, so a branch, tag, note,
# remote-tracking ref or other such ref created or moved onto it, or onto a
# descendant of it, fails the run. The HEAD and the per-worktree refs of any
# other worktree, and a ref outside refs/ other than HEAD, such as ORIG_HEAD,
# of any worktree, are not listed, so they are not checked. The listing reads
# every commit's parents as its object records them: replace refs are turned
# off, and the graft file and the shallow file are each set to an empty path,
# which git reads as no file, so no refs/replace/ ref, graft or shallow
# boundary can give a descendant of COMMIT other parents and hide a ref that
# contains it. A failing git call fails the run and is never read as an empty
# listing.
ref_leak_check() {
  local holders
  holders="$(GIT_GRAFT_FILE='' git -C "${repo_root}" --no-replace-objects --shallow-file '' \
    for-each-ref --contains "$1" --format='%(refname)')" \
    || fail "could not list the refs of ${repo_root} that contain the dry-run commit $1"
  [ -z "${holders}" ] \
    || fail "the dry run changed a git ref, which it must never do; these refs contain its commit $1:
${holders}"
}

dry_date="${DRY_DATE:-$(date -u +%F)}"
case "${dry_date}" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
  *) fail "DRY_DATE must be YYYY-MM-DD, got ${dry_date}" ;;
esac
# A date that predates the current page stamps, so a broken stamping step
# cannot pass by leaving the existing dates in place.
seed_date="2020-01-01"

refs_before="$(ref_snapshot)"

# git_off holds the options that turn off, for 1 git call, the hooks, the
# core.fsmonitor program and the pager that git can otherwise run from its
# configuration during the git calls of this script, whatever the
# configuration asks, and every later git call of the script, the exit
# cleanup's included, other than the reads of step 6, runs with them:
# --no-pager, so no pager that pager.<command> or core.pager names runs when
# the call writes to a terminal; core.hooksPath set to the null device, which
# holds no hook, so no hook of the repository runs, such as post-checkout here;
# and core.fsmonitor set to false, so no core.fsmonitor program runs, which git
# otherwise starts on reading the index.
git_off=(--no-pager -c core.hooksPath=/dev/null -c core.fsmonitor=false)

# export_settings SETTING...: append each SETTING, a name, an equals sign and a
# value, to GIT_CONFIG_PARAMETERS, quoted as git quotes it there. git -c passes
# its settings to the git processes it starts in that variable, and git reads
# them after every other configuration, so every later git process of the dry
# run, its tools' included, runs with each SETTING, whatever any other
# configuration asks.
export_settings() {
  local setting quoted
  for setting in "$@"; do
    quoted="${setting//\'/\'\\\'\'}"
    quoted="'${quoted//!/\'\\!\'}'"
    GIT_CONFIG_PARAMETERS="${GIT_CONFIG_PARAMETERS:+${GIT_CONFIG_PARAMETERS} }${quoted}"
  done
  export GIT_CONFIG_PARAMETERS
}

# turn_off_filters NAMES: for each filter driver in NAMES, each name ended by a
# newline, export its clean, smudge and process commands set to empty, which git
# reads as no command, and its required flag set to false, so that driver runs
# on checking out, staging, hashing or archiving no file. A name that holds an
# equals sign fails the run, since git would read that sign as the end of the
# setting's name and leave the driver on.
turn_off_filters() {
  local name
  local -a settings=()
  while IFS= read -r name; do
    case "${name}" in
      *=*) fail "could not turn off the filter driver ${name}, whose name holds an equals sign" ;;
    esac
    settings+=("filter.${name}.clean=" "filter.${name}.smudge=" "filter.${name}.process="
      "filter.${name}.required=false")
  done < <(printf '%s' "$1")
  [ "${#settings[@]}" -eq 0 ] || export_settings "${settings[@]}"
}

# A filter runs only on a path that an attribute gives a filter driver. So the
# dry run keeps every attribute file other than the info/attributes file out
# of reach of its git processes, and turns off every filter driver that the
# info/attributes file names and every one that the configuration read from
# repo_root defines, which git config lists; then no filter applies, whatever
# the configuration that git reads in any worktree defines. The first 3 git
# calls below run before these settings exist, and read no index and no file
# of a worktree. A git error in any of them, or an error in reading the
# info/attributes file, fails the run.
filter_rc=0
filter_keys="$(git "${git_off[@]}" config --name-only --get-regexp '^filter\.')" || filter_rc=$?
case "${filter_rc}" in
  0|1) ;;
  *) fail "could not list the filter drivers of ${repo_root} (git config exit ${filter_rc})" ;;
esac
filter_drivers=""
while IFS= read -r filter_key; do
  case "${filter_key}" in
    filter.*.*) filter_driver="${filter_key#filter.}"; filter_driver="${filter_driver%.*}" ;;
    *) continue ;;
  esac
  filter_drivers+="${filter_driver}"$'\n'
done <<< "${filter_keys}"
# The info/attributes file of the repository, which every worktree of it
# reads, is the attribute file that the settings below leave in reach. Every
# word of it that starts with filter= names a driver, the rest of the word, up
# to a space, a tab, a carriage return, a newline or a NUL byte, at which git
# ends a word; a word in a comment, or the pattern of a line, is read as one
# too, which turns off at most a driver that no attribute names. A missing
# file names none, as git reads it.
attributes_file="$(git "${git_off[@]}" rev-parse --git-path info/attributes)" \
  || fail "could not find the info/attributes file of ${repo_root}"
attributes_drivers="$(python3 -I - "${attributes_file}" <<'PYATTR'
import sys
try:
    with open(sys.argv[1], "rb") as attributes:
        data = attributes.read()
except (FileNotFoundError, NotADirectoryError):
    data = b""
names = set()
for blank in (b"\0", b"\t", b"\r", b"\n"):
    data = data.replace(blank, b" ")
for word in data.split(b" "):
    if word.startswith(b"filter="):
        names.add(word[len(b"filter="):])
sys.stdout.buffer.write(b"".join(name + b"\n" for name in sorted(names)) + b".")
PYATTR
)" || fail "could not read the filter drivers that ${attributes_file} names"
attributes_drivers="${attributes_drivers%.}"
empty_tree="$(git "${git_off[@]}" hash-object -t tree --stdin < /dev/null)" \
  || fail "could not name the empty tree of ${repo_root}"
# Every later git process of the dry run, its tools' included, reads no
# system attribute file (GIT_ATTR_NOSYSTEM), no attribute file that
# core.attributesFile or its default names (core.attributesFile set to the
# null device), and the .gitattributes files of the empty tree, which holds
# none, in place of those of its worktree, index or HEAD (GIT_ATTR_SOURCE), so
# only the info/attributes file stays in reach, and, in git archive, the
# .gitattributes files of the tree it archives, which git archive reads
# whatever GIT_ATTR_SOURCE names; step 1 runs git archive only after the
# drivers that those name are turned off below.
export GIT_ATTR_NOSYSTEM=1 GIT_ATTR_SOURCE="${empty_tree}"
export_settings core.attributesFile=/dev/null
turn_off_filters "${filter_drivers}${attributes_drivers}"
# A git that ignores GIT_ATTR_SOURCE would read the attribute files of the
# throwaway worktree, so the run fails unless git refuses a GIT_ATTR_SOURCE
# that names no tree.
if GIT_ATTR_SOURCE=.. git "${git_off[@]}" check-attr filter -- tools/release-dry-run.sh >/dev/null 2>&1; then
  fail "git ignores GIT_ATTR_SOURCE, so the dry run cannot keep the attribute files of its worktree out of reach"
fi

# The first Version: line is authoritative and must be a bare X.Y.Z, the same
# strict rule the release gates apply; a malformed first line is rejected here,
# never skipped to a later matching line. One shared strict extractor,
# tools/skill-version.py, does the reading and validation for every site, so the
# shell, the workflow, and the Python gates agree byte for byte (including on a
# NUL, which the old capture-then-sed form silently stripped). The raw blob is
# piped straight in: skill-version.py reads ALL of stdin, so git show completes
# and can take no SIGPIPE, and the ~64KB-pipe exit-141 regression cannot recur.
if ! version="$(git "${git_off[@]}" show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 -I tools/skill-version.py)"; then
  fail "could not read a valid bare X.Y.Z Version: line from cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"
fi
patch="${version##*.}"
dry_version="${version%.*}.$(( 10#${patch} + 1 ))"
dry_tag="v${dry_version}"
echo "release-dry-run: version ${version} at HEAD; dry-run version ${dry_version}; date ${dry_date}."

worktree="$(mktemp -d)"
cleanup() {
  cd "${repo_root}"
  git "${git_off[@]}" worktree remove --force "${worktree}" >/dev/null 2>&1 || true
  rm -rf "${worktree}"
}
trap cleanup EXIT
# Like every later git call of the script, git worktree add runs with git_off
# and the attribute and filter settings exported above, so no hook,
# core.fsmonitor program, pager or filter runs inside it.
git "${git_off[@]}" worktree add --detach "${worktree}" HEAD >/dev/null
cd "${worktree}"

# Stand in for the human version-bump commit that precedes a real release.
# The commit lives on the worktree's detached HEAD and is discarded with it.
# The Version: line can carry trailing whitespace (a Markdown hard break),
# so replace the number in place and keep the rest of the line intact.
sed -i -E "s/^(Version:[[:space:]]*)[0-9][0-9.]*/\1${dry_version}/" cleanlanguage/skills/cleanlanguage/SKILL.md
grep -qE "^Version:[[:space:]]*${dry_version}([[:space:]]|\$)" cleanlanguage/skills/cleanlanguage/SKILL.md \
  || fail "could not set the dry-run version in SKILL.md"
# A real bump above the undated baseline also stamps the Released line (item 26)
# with the UTC day of the release, so stamp the dry-run date directly after the
# Version line: insert the line when HEAD carries none (the undated baseline)
# and replace its value otherwise, keeping the two-space hard break. The
# shared extractor then confirms the stamped value.
python3 -I - "${dry_date}" <<'PYDATE'
import sys
from pathlib import Path
d = sys.argv[1]
p = Path("cleanlanguage/skills/cleanlanguage/SKILL.md")
lines = p.read_bytes().decode("utf-8").split("\n")
vi = next(i for i, l in enumerate(lines) if l.startswith("Version:"))
if vi + 1 < len(lines) and lines[vi + 1].startswith("Released:"):
    lines[vi + 1] = "Released: " + d + "  "
else:
    lines.insert(vi + 1, "Released: " + d + "  ")
p.write_bytes("\n".join(lines).encode("utf-8"))
PYDATE
# The client, tools/skill-release-date-client.py, runs the extractor in its
# --json mode and is probed first, so a missing or broken tool is reported as
# that. Then exit 11 or 13 means the stamp did not produce a well-formed line,
# exit 14 means the stamped file could not be read, and any other exit means
# the tool is unavailable or crashed, reported as that. The probe captures
# both streams of the client (which writes the value on stdout on exit 0,
# and only its message on stderr otherwise), so its reason is relayed.
probe_rc=0
probe="$(python3 -I tools/skill-release-date-client.py baseline 2>&1)" || probe_rc=$?
case "${probe_rc}" in
  0) [[ "${probe}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "tools/skill-release-date.py is unavailable or broken (probe exit 0)" ;;
  *)
    [ -z "${probe}" ] || printf '%s\n' "${probe}" >&2
    fail "tools/skill-release-date.py is unavailable or broken (probe exit ${probe_rc})"
    ;;
esac
stamped_rc=0
stamped="$(python3 -I tools/skill-release-date-client.py extract-file cleanlanguage/skills/cleanlanguage/SKILL.md)" || stamped_rc=$?
case "${stamped_rc}" in
  0) ;;
  11|13) fail "could not set the dry-run Released date in SKILL.md (client exit ${stamped_rc})" ;;
  14) fail "could not read the stamped cleanlanguage/skills/cleanlanguage/SKILL.md for its Released line (client exit 14)" ;;
  *) fail "tools/skill-release-date.py is unavailable or crashed (exit ${stamped_rc}) reading the stamped SKILL.md" ;;
esac
[ "${stamped}" = "${dry_date}" ] \
  || fail "could not set the dry-run Released date in SKILL.md (read ${stamped}, wanted ${dry_date})"

# The plugin manifest carries the same version, and release-package.sh asserts the
# two agree. A real release bumps both together, so the dry run must too, or it
# would fail on a mismatch it created itself.
python3 -I - "${dry_version}" <<'PYVER'
import json, pathlib, sys
v = sys.argv[1]
p = pathlib.Path("cleanlanguage/.claude-plugin/plugin.json")
d = json.loads(p.read_text(encoding="utf-8"))
d["version"] = v
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
PYVER
python3 -I -c 'import json,sys; v=json.load(open("cleanlanguage/.claude-plugin/plugin.json"))["version"]; sys.exit(0 if v==sys.argv[1] else 1)' "${dry_version}" \
  || fail "could not set the dry-run version in cleanlanguage/.claude-plugin/plugin.json"
# The dry-run commit, for the leak check of step 6. The script makes it with
# git commit-tree, from the staged tree, on the commit the HEAD of this
# worktree resolves to, with the dry run's identity, dates and message. git
# commit-tree prints the name of the commit it writes, so the saved name is the
# commit the dry run made, and the leak check reads it, never a later HEAD. git
# update-ref then moves the HEAD of this worktree from the parent to that
# commit, and fails if that HEAD is no longer at the parent.
# Every git call here runs with git_off and the attribute and filter settings,
# as git worktree add does above, so no hook, core.fsmonitor program, pager or
# filter can change the commit, keep another or move that HEAD inside them;
# the run then fails unless that HEAD is at the dry-run commit, so the steps
# below read that commit. Its object is in the store the worktree shares with
# repo_root, so repo_root resolves it. git commit-tree runs with commit signing
# turned off, whatever the configuration asks, so the dry-run commit is never
# signed. Every git call here fails the run with exit 1 on an error.
dry_message="Dry run: version ${dry_version}"
git "${git_off[@]}" add -u || fail "could not stage the dry-run version bump"
dry_tree="$(git "${git_off[@]}" write-tree)" || fail "could not write the tree of the dry-run commit"
dry_parent="$(git "${git_off[@]}" rev-parse --verify HEAD)" \
  || fail "could not read the HEAD of the dry run's worktree before its commit"
dry_commit="$(GIT_AUTHOR_DATE="${dry_date}T12:00:00 +0000" GIT_COMMITTER_DATE="${dry_date}T12:00:00 +0000" \
  git "${git_off[@]}" -c user.name="release-dry-run" -c user.email="release-dry-run@invalid" \
  -c commit.gpgSign=false commit-tree -p "${dry_parent}" -m "${dry_message}" "${dry_tree}")" \
  || fail "could not make the dry-run commit"
git "${git_off[@]}" update-ref --no-deref -m "${dry_message}" HEAD "${dry_commit}" "${dry_parent}" \
  || fail "could not move the HEAD of the dry run's worktree from ${dry_parent} to the dry-run commit ${dry_commit}"
dry_head="$(git "${git_off[@]}" rev-parse --verify HEAD)" \
  || fail "could not read the HEAD of the dry run's worktree after its commit"
[ "${dry_head}" = "${dry_commit}" ] \
  || fail "the HEAD of the dry run's worktree is at ${dry_head}, not at the dry-run commit ${dry_commit}; another process moved that HEAD"
# git archive, which the packager of step 1 runs on HEAD, reads the
# .gitattributes files of the tree it archives whatever GIT_ATTR_SOURCE
# names, so every filter driver that an attribute gives a path of the dry-run
# commit, read as git archive reads them, is turned off too. git check-attr
# prints set, unset or unspecified both for an attribute that names no driver
# and for a driver of that name, so a driver of each of those names is turned
# off too. A git error here fails the run.
tree_drivers="$(git "${git_off[@]}" ls-tree -r --name-only "${dry_commit}" \
  | git "${git_off[@]}" check-attr --source "${dry_commit}" --stdin filter \
  | sed 's/.*: //' | LC_ALL=C sort -u && printf '.')" \
  || fail "could not read the filter drivers that the attributes of the dry-run commit ${dry_commit} name"
turn_off_filters "${tree_drivers%.}"

# Seed the modified-date fields with an old sentinel so the writer must restamp
# them for the gates and assertions to pass: the modified dates of the install
# and verify pages in site-src/site.json, which the generator stamps into the
# pages, and the same stamps in the committed pages and the sitemap. Publish
# dates are left untouched.
python3 -I - "${seed_date}" <<'PYSEED'
import sys, re, pathlib
d = sys.argv[1]
sj = pathlib.Path("site-src/site.json"); t = sj.read_text(encoding="utf-8")
for page_id in ("install", "verify"):
    t, n = re.subn(r'(\{"id": "' + page_id + r'", [^\n]*?"modified": ")\d{4}-\d{2}-\d{2}(")', rf'\g<1>{d}\g<2>', t, count=1)
    if n != 1:
        sys.exit(f"seed: expected one modified date for {page_id} in site-src/site.json, got {n}")
sj.write_text(t, encoding="utf-8")
for f in ("site/install/index.html", "site/verify/index.html"):
    p = pathlib.Path(f); t = p.read_text(encoding="utf-8")
    t, a = re.subn(r'(<meta property="article:modified_time" content=")\d{4}-\d{2}-\d{2}(")', rf'\g<1>{d}\g<2>', t, count=1)
    t, b = re.subn(r'("dateModified":\s*")\d{4}-\d{2}-\d{2}(")', rf'\g<1>{d}\g<2>', t, count=1)
    if a != 1 or b != 1:
        sys.exit(f"seed: expected one modified stamp and one dateModified in {f}, got {a} and {b}")
    p.write_text(t, encoding="utf-8")
sm = pathlib.Path("site/sitemap.xml"); t = sm.read_text(encoding="utf-8")
for slug in ("install", "verify"):
    t, n = re.subn(r'(<loc>https://cleanlanguage\.ai/' + slug + r'/</loc>\s*<lastmod>)\d{4}-\d{2}-\d{2}(</lastmod>)', rf'\g<1>{d}\g<2>', t, count=1)
    if n != 1:
        sys.exit(f"seed: expected one sitemap lastmod for /{slug}/, got {n}")
sm.write_text(t, encoding="utf-8")
PYSEED
grep -q "article:modified_time\" content=\"${seed_date}\"" site/install/index.html \
  || fail "the sentinel seed did not take on the install page"
grep -q "\"id\": \"install\", .*\"modified\": \"${seed_date}\"" site-src/site.json \
  || fail "the sentinel seed did not take in site-src/site.json"

# 1. Validate, package, and verify the zip, exactly as the release does,
#    including the release-date check the workflow runs with the UTC day.
tools/release-package.sh --tag "${dry_tag}" --release-date "${dry_date}"

# 1a. Prove the build is REPRODUCIBLE: a second build under a different umask
#     and a hostile ZIPOPT must yield the identical archive and checksum, so a
#     third party who rebuilds the commit to verify the release gets our bytes.
first_sum="$(cut -d' ' -f1 < dist/cleanlanguage.zip.sha256)"
( umask 077; ZIPOPT="-0" ZIP="-1" tools/release-package.sh --tag "${dry_tag}" --release-date "${dry_date}" >/dev/null )
second_sum="$(cut -d' ' -f1 < dist/cleanlanguage.zip.sha256)"
[ "${first_sum}" = "${second_sum}" ] \
  || fail "the build is not reproducible: ${first_sum} vs ${second_sum} under a different umask/ZIPOPT"
# The real checksum of the zip just built, for step 2. It is read here because
# the refused build in 1b removes the packager's outputs from dist/.
checksum="$(cut -d' ' -f1 < "dist/cleanlanguage-${dry_version}.zip.sha256")"

# 1b. Prove the release-date check is live: the same commit, asked to release
#     on the sentinel day its Released line does not name, must be refused for
#     exactly that reason, before anything is built, and must leave no zip and
#     no .sha256 in dist/.
if date_err="$(tools/release-package.sh --tag "${dry_tag}" --release-date "${seed_date}" 2>&1 >/dev/null)"; then
  fail "the packager accepted a release date (${seed_date}) that the Released line does not name"
fi
case "${date_err}" in
  *"does not match the release date (${seed_date})"*) ;;
  *) fail "the packager refused the sentinel release date for another reason: ${date_err}" ;;
esac
for output in cleanlanguage.zip cleanlanguage.zip.sha256 \
  "cleanlanguage-${dry_version}.zip" "cleanlanguage-${dry_version}.zip.sha256"; do
  [ ! -e "dist/${output}" ] \
    || fail "the refused build left dist/${output} in place"
done

# 2. Point the site at the dry-run release, exactly as the orchestrator's
#    post-release flip does,
#    including the real checksum of the zip built in step 1, read after 1a.
python3 -I tools/set-release-links.py --version "${dry_version}" --tag "${dry_tag}" \
  --checksum "${checksum}" --date "${dry_date}"

# The sitemap is regenerated from the restamped pages, repairing the sentinel
# dates seeded above. set-release-links no longer edits the sitemap; the
# generator owns it.
python3 -I tools/generate-sitemap.py --write

# 3. The writer's own gate, then these gates that the site pull request
#    also triggers: link check, page metadata, the sitemap, and the install
#    page. The portable text gate runs on every pull request, the site pull
#    request included (row 119), but it is not run here: the synthetic
#    version bump above changes the skill without the portable renderings
#    that gate compares, and stands in for a human commit that gate already
#    covers in real pull requests; the Released date agreement across the
#    renderings is likewise proved by that gate on the real bump pull
#    request. Of that workflow's steps, only the instructions page gate runs
#    below. check-page-metadata can only pass if the writer restamped the
#    sentinel dates seeded above.
python3 -I tools/check-release-links.py
python3 -I tools/check-page-metadata.py
python3 -I tools/generate-sitemap.py
python3 -I tools/check-links.py
python3 -I tools/check-install-page.py
# The pages under site/ are generated from site-src/release.json and site-src/site.json,
# which the writer above rewrote and then regenerated from; the generator's check mode
# proves the output now matches a fresh build, and the pin is untouched.
python3 -I tools/build-site.py --check
python3 -I tools/check-baseline-pin.py
python3 -I tools/check-instructions-page.py

# 4. Assertions on the rewritten site. Because the dates were seeded old, a
#    passing stamp assertion here proves the writer changed them.
assert_contains() {
  grep -q "$2" "$1" || fail "expected $1 to contain: $2"
}
assert_contains site/_redirects "releases/download/${dry_tag}/cleanlanguage-${dry_version}.zip"
assert_contains site/install/index.html "cleanlanguage-${dry_version}.zip"
assert_contains site/verify/index.html "cleanlanguage-${dry_version}.zip.sha256"
assert_contains site/verify/index.html "${checksum}"
assert_contains site/verify/index.html "published checksum for version ${dry_version} is"
# No page may still name the release it replaced, in a URL or written out bare
# (the install page's example download name, the verify page's hash commands).
for page in site/install/index.html site/verify/index.html; do
  if grep -qF "cleanlanguage-${version}.zip" "${page}"; then
    fail "${page} still names cleanlanguage-${version}.zip after the rewrite"
  fi
done
# The generated pages name the new version everywhere: the download block, the
# version labels, the checksum, the hash commands, and the install page's example
# filename (the version text the old writer left behind), and no old version.
assert_contains site-src/release.json "\"version\": \"${dry_version}\""
assert_contains site-src/release.json "\"checksum\": \"${checksum}\""
assert_contains site/install/index.html "releases/download/${dry_tag}/cleanlanguage-${dry_version}.zip"
assert_contains site/install/index.html "zip, version ${dry_version}"
assert_contains site/install/index.html "for example <code>cleanlanguage-${dry_version}.zip</code>"
assert_contains site/verify/index.html "<code class=\"sum\" id=\"published-checksum\">${checksum}</code>"
assert_contains site/verify/index.html "sha256sum cleanlanguage-${dry_version}.zip"
for page in site/install/index.html site/verify/index.html; do
  grep -q "version ${version}\b" "${page}" \
    && fail "${page} still names version ${version} after the flip"
done
for page in site/install/index.html site/verify/index.html; do
  assert_contains "${page}" "article:modified_time\" content=\"${dry_date}\""
  assert_contains "${page}" "\"dateModified\": \"${dry_date}\""
  grep -q "${seed_date}" "${page}" && fail "the sentinel date survived in ${page}; stamping did not run"
done
for name in install verify; do
  assert_contains site-src/site.json "\"id\": \"${name}\", .*\"modified\": \"${dry_date}\""
done
grep -q "${seed_date}" site-src/site.json && fail "the sentinel date survived in site-src/site.json; stamping did not run"
# The writer rewrites site/_redirects whole, so the fixed redirects kept since
# promotion must survive the flip.
assert_contains site/_redirects "^/privacy https://posluns.ca/privacy/ 301$"
assert_contains site/_redirects "^/privacy/ https://posluns.ca/privacy/ 301$"
assert_contains site/_redirects "^/favicon.svg /assets/baseline/logos/cleanlanguage-favicon.svg 301$"
assert_contains site/_redirects "^/apple-touch-icon.png /assets/baseline/logos/cleanlanguage-touch.png 301$"
# grep -q exits on its first match, so the entry is captured first and read
# from a here-string: a pipe into it would rest on the writer making a single
# write, and any later write would take a SIGPIPE that pipefail reports.
for name in install verify; do
  entry="$(grep -A1 "<loc>https://cleanlanguage.ai/${name}/</loc>" site/sitemap.xml)" \
    && grep -q "<lastmod>${dry_date}</lastmod>" <<< "${entry}" \
    || fail "the sitemap lastmod for /${name}/ was not stamped to ${dry_date}"
done

# 5. A second run must find nothing left to change.
python3 -I tools/set-release-links.py --version "${dry_version}" --tag "${dry_tag}" \
  --checksum "${checksum}" --date "${dry_date}" --check

# 6. Prove that the dry run moved no tag, no note and not the HEAD of the
#    script's worktree, and that no ref that git for-each-ref lists from it
#    contains the dry-run commit. A write that the header's residual names
#    does not fail it, whoever makes it; the header states the proof and that
#    residual in full.
refs_after="$(ref_snapshot)"
[ "${refs_before}" = "${refs_after}" ] \
  || fail "the dry run changed a git ref, which it must never do; the HEAD of ${repo_root}, and every tag and note, before:
${refs_before}
and after:
${refs_after}"
ref_leak_check "${dry_commit}"

echo "release-dry-run: every step, gate, and assertion passed for ${dry_tag} (nothing was published)."
