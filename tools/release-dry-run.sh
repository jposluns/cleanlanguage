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
# and no git push, proving at exit that no repository ref moved.
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

cd "$(dirname "${BASH_SOURCE[0]}")/.."
repo_root="$(pwd)"

fail() {
  printf 'release-dry-run: %s\n' "$1" >&2
  exit 1
}

dry_date="${DRY_DATE:-$(date -u +%F)}"
case "${dry_date}" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
  *) fail "DRY_DATE must be YYYY-MM-DD, got ${dry_date}" ;;
esac
# A date that predates the current page stamps, so a broken stamping step
# cannot pass by leaving the existing dates in place.
seed_date="2020-01-01"

refs_before="$(git for-each-ref | sha256sum)"

version="$(git show HEAD:cleanlanguage/SKILL.md \
  | sed -n 's/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p' | head -1)"
[ -n "${version}" ] || fail "no Version: line found in cleanlanguage/SKILL.md at HEAD"
printf '%s' "${version}" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' \
  || fail "expected a three-part version like 1.0.11, got ${version}"
patch="${version##*.}"
dry_version="${version%.*}.$(( 10#${patch} + 1 ))"
dry_tag="v${dry_version}"
echo "release-dry-run: version ${version} at HEAD; dry-run version ${dry_version}; date ${dry_date}."

worktree="$(mktemp -d)"
cleanup() {
  cd "${repo_root}"
  git worktree remove --force "${worktree}" >/dev/null 2>&1 || true
  rm -rf "${worktree}"
}
trap cleanup EXIT
git worktree add --detach "${worktree}" HEAD >/dev/null
cd "${worktree}"

# Stand in for the human version-bump commit that precedes a real release.
# The commit lives on the worktree's detached HEAD and is discarded with it.
# The Version: line can carry trailing whitespace (a Markdown hard break),
# so replace the number in place and keep the rest of the line intact.
sed -i -E "s/^(Version:[[:space:]]*)[0-9][0-9.]*/\1${dry_version}/" cleanlanguage/SKILL.md
grep -qE "^Version:[[:space:]]*${dry_version}([[:space:]]|\$)" cleanlanguage/SKILL.md \
  || fail "could not set the dry-run version in SKILL.md"
GIT_AUTHOR_DATE="${dry_date}T12:00:00 +0000" GIT_COMMITTER_DATE="${dry_date}T12:00:00 +0000" \
  git -c user.name="release-dry-run" -c user.email="release-dry-run@invalid" \
  commit -q -am "Dry run: version ${dry_version}"

# Seed the modified-date fields with an old sentinel so the writer must restamp
# them for the gates and assertions to pass. Publish dates are left untouched.
python3 - "${seed_date}" <<'PYSEED'
import sys, re, pathlib
d = sys.argv[1]
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

# 1. Validate, package, and verify the zip, exactly as the release does.
tools/release-package.sh --tag "${dry_tag}"

# 1a. Prove the build is REPRODUCIBLE: a second build under a different umask
#     and a hostile ZIPOPT must yield the identical archive and checksum, so a
#     third party who rebuilds the commit to verify the release gets our bytes.
first_sum="$(cut -d' ' -f1 < dist/cleanlanguage.zip.sha256)"
( umask 077; ZIPOPT="-0" ZIP="-1" tools/release-package.sh --tag "${dry_tag}" >/dev/null )
second_sum="$(cut -d' ' -f1 < dist/cleanlanguage.zip.sha256)"
[ "${first_sum}" = "${second_sum}" ] \
  || fail "the build is not reproducible: ${first_sum} vs ${second_sum} under a different umask/ZIPOPT"

# 2. Point the site at the dry-run release, exactly as the orchestrator's
#    post-release flip does,
#    including the real checksum of the zip just built.
checksum="$(cut -d' ' -f1 < "dist/cleanlanguage-${dry_version}.zip.sha256")"
tools/set-release-links.py --version "${dry_version}" --tag "${dry_tag}" \
  --checksum "${checksum}" --date "${dry_date}"

# 3. The writer's own gate, then every gate the site pull request
#    triggers (link check, page metadata, and the install page; the portable
#    text gate does not run on a site-only pull request, and the synthetic
#    version bump above stands in for a human commit that gate already
#    covers in real pull requests). check-page-metadata can only pass if the
#    writer restamped the sentinel dates seeded above.
tools/check-release-links.py
python3 tools/check-page-metadata.py
python3 tools/check-links.py
python3 tools/check-install-page.py

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
for page in site/install/index.html site/verify/index.html; do
  assert_contains "${page}" "article:modified_time\" content=\"${dry_date}\""
  assert_contains "${page}" "\"dateModified\": \"${dry_date}\""
  grep -q "${seed_date}" "${page}" && fail "the sentinel date survived in ${page}; stamping did not run"
done
for name in install verify; do
  grep -A1 "<loc>https://cleanlanguage.ai/${name}/</loc>" site/sitemap.xml \
    | grep -q "<lastmod>${dry_date}</lastmod>" \
    || fail "the sitemap lastmod for /${name}/ was not stamped to ${dry_date}"
done

# 5. A second run must find nothing left to change.
tools/set-release-links.py --version "${dry_version}" --tag "${dry_tag}" \
  --checksum "${checksum}" --date "${dry_date}" --check

# 6. Prove nothing here moved a repository ref.
refs_after="$(git -C "${repo_root}" for-each-ref | sha256sum)"
[ "${refs_before}" = "${refs_after}" ] \
  || fail "the dry run changed a git ref, which it must never do"

echo "release-dry-run: every step, gate, and assertion passed for ${dry_tag} (nothing was published)."
