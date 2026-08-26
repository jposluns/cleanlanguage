#!/usr/bin/env bash
#
# Builds the skill release zip and proves its contents before anything ships.
#
# Everything here reads the git tree at HEAD, never the checkout's filesystem
# metadata. Filesystem permission bits vary by machine (an ACL can add execute
# bits the repository never recorded), so a check that read them would pass on
# one machine and fail on another. The git tree is identical everywhere the
# commit exists, so this script gives one answer everywhere.
#
# What it does, in order:
#
#   1. Reads the version from the Version: line in cleanlanguage/SKILL.md at
#      HEAD; with --tag, fails unless the tag is v<version>.
#   2. Requires every git entry under cleanlanguage/ to carry mode 100644,
#      which rejects executable files (100755), symlinks (120000), and
#      submodules (160000) in one comparison.
#   3. Requires every path to match the package allowlist: SKILL.md, agent
#      configuration in agents/, the CL_icon files in assets/, and Markdown
#      references in references/. A new reference document is allowed; a new
#      directory, script, or binary fails.
#   4. Requires every icon the ChatGPT interface configuration references to
#      exist in the package.
#   5. Stages the package from git archive, adds LICENSE and NOTICE.md into
#      cleanlanguage/, and zips it, so the zip holds exactly what git records
#      plus the two licence files, whatever state the checkout is in.
#   6. Verifies the archive against an expected entry list derived from the
#      same git tree. The comparison is equality: a missing entry and an
#      extra entry both fail.
#
# It writes dist/cleanlanguage.zip, dist/cleanlanguage-<version>.zip, and a
# .sha256 beside each. It never tags, pushes, or talks to the network.
#
# Usage:
#   tools/release-package.sh                 Build and verify at HEAD.
#   tools/release-package.sh --tag v1.0.12   Also require the tag to match.
#
# Exit codes:
#   0  built and verified
#   1  a validation or layout check failed

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

fail() {
  printf 'release-package: %s\n' "$1" >&2
  exit 1
}

tag=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) shift; tag="${1:-}" ;;
    *) fail "unknown argument $1" ;;
  esac
  shift
done

version="$(git show HEAD:cleanlanguage/SKILL.md \
  | sed -n 's/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p' | head -1)"
[ -n "${version}" ] || fail "no Version: line found in cleanlanguage/SKILL.md at HEAD"
if [ -n "${tag}" ] && [ "v${version}" != "${tag}" ]; then
  fail "SKILL.md version (${version}) does not match the tag (${tag})"
fi

bad_modes="$(git ls-tree -r HEAD -- cleanlanguage | awk '$1 != "100644"')"
if [ -n "${bad_modes}" ]; then
  printf 'release-package: every packaged file must be a regular, non-executable file (git mode 100644); found:\n%s\n' "${bad_modes}" >&2
  exit 1
fi

files="$(git ls-tree -r HEAD --name-only -- cleanlanguage)"
[ -n "${files}" ] || fail "git records no files under cleanlanguage/"
unexpected="$(printf '%s\n' "${files}" | grep -Ev \
  '^cleanlanguage/(SKILL\.md|agents/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.yaml|assets/CL_icon\.(png|svg)|references/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.md)$' \
  || true)"
if [ -n "${unexpected}" ]; then
  printf 'release-package: paths outside the package allowlist:\n%s\n' "${unexpected}" >&2
  exit 1
fi

# Any icon the ChatGPT interface config references must exist in the package,
# so a shipped skill never points at a missing asset.
if git cat-file -e HEAD:cleanlanguage/agents/openai.yaml 2>/dev/null; then
  missing_icon=0
  while IFS= read -r icon; do
    [ -n "${icon}" ] || continue
    if ! git cat-file -e "HEAD:cleanlanguage/${icon#./}" 2>/dev/null; then
      echo "release-package: icon referenced in agents/openai.yaml is missing: ${icon}" >&2
      missing_icon=1
    fi
  done < <(git show HEAD:cleanlanguage/agents/openai.yaml \
    | sed -n 's/.*icon_[a-z]*:[[:space:]]*"\(\.\/[^"]*\)".*/\1/p')
  [ "${missing_icon}" -eq 0 ] || exit 1
fi

staging="$(mktemp -d)"
trap 'rm -rf "${staging}"' EXIT
git archive --format=tar HEAD cleanlanguage | tar -xf - -C "${staging}"
git show HEAD:LICENSE > "${staging}/cleanlanguage/LICENSE"
git show HEAD:NOTICE.md > "${staging}/cleanlanguage/NOTICE.md"
chmod 644 "${staging}/cleanlanguage/LICENSE" "${staging}/cleanlanguage/NOTICE.md"

rm -rf dist
mkdir -p dist
dist_dir="$(pwd)/dist"
(cd "${staging}" && zip -q -r -X "${dist_dir}/cleanlanguage.zip" cleanlanguage)
cp dist/cleanlanguage.zip "dist/cleanlanguage-${version}.zip"
(cd dist && sha256sum cleanlanguage.zip > cleanlanguage.zip.sha256)
(cd dist && sha256sum "cleanlanguage-${version}.zip" > "cleanlanguage-${version}.zip.sha256")

expected="$(
  {
    printf '%s\n' "${files}"
    printf 'cleanlanguage/LICENSE\ncleanlanguage/NOTICE.md\n'
  } | LC_ALL=C sort
)"
actual="$(unzip -Z1 dist/cleanlanguage.zip | grep -v '/$' | LC_ALL=C sort)"
if [ "${expected}" != "${actual}" ]; then
  echo "release-package: the archive entry list does not match the git tree:" >&2
  diff <(printf '%s\n' "${expected}") <(printf '%s\n' "${actual}") >&2 || true
  exit 1
fi

echo "release-package: dist/cleanlanguage-${version}.zip built and verified for version ${version}."
printf '%s\n' "${actual}" | sed 's/^/  /'
