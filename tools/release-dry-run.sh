#!/usr/bin/env bash
#
# Proves the release path end to end without publishing anything.
#
# The release workflow does four things a test can prove without touching
# GitHub: validate and package the skill, rewrite the site at the new release,
# stamp the modified dates that rewrite implies, and satisfy the gates the
# auto-opened site pull request must pass. This script runs all four against a
# throwaway git worktree, at a synthetic next version, and asserts the results.
# The side-effecting steps (tag push, gh release, opening and merging the pull
# request) stay in the workflow and are deliberately absent here: this script
# contains no gh call and no git push, and it proves at exit that no
# repository ref moved.
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

refs_before="$(git for-each-ref | sha256sum)"

version="$(git show HEAD:cleanlanguage/SKILL.md \
  | sed -n 's/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p' | head -1)"
[ -n "${version}" ] || fail "no Version: line found in cleanlanguage/SKILL.md at HEAD"
dry_version="${version%.*}.$(( ${version##*.} + 1 ))"
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

# 1. Validate, package, and verify the zip, exactly as the release does.
tools/release-package.sh --tag "${dry_tag}"

# 2. Point the site at the dry-run release, exactly as the release does,
#    including the real checksum of the zip just built.
checksum="$(cut -d' ' -f1 < "dist/cleanlanguage-${dry_version}.zip.sha256")"
tools/set-release-links.py --version "${dry_version}" --tag "${dry_tag}" \
  --checksum "${checksum}" --date "${dry_date}"

# 3. The writer's own gate, then every gate the auto-opened site pull request
#    triggers (link check, page metadata, and the install page; the portable
#    text gate does not run on a site-only pull request, and the synthetic
#    version bump above stands in for a human commit that gate already
#    covers in real pull requests).
tools/check-release-links.py
python3 tools/check-page-metadata.py
python3 tools/check-links.py
python3 tools/check-install-page.py

# 4. Assertions on the rewritten site.
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
