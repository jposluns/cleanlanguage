#!/usr/bin/env bash
#
# Builds the skill release zip and proves its contents before anything ships.
#
# Everything here reads the git tree at HEAD, never the checkout's filesystem
# metadata. Filesystem permission bits vary by machine (an ACL can add execute
# bits the repository never recorded), so a check that read them would pass on
# one machine and fail on another. The git tree is identical everywhere the
# commit exists, and the archive is stamped from the commit and ordered, so
# the same commit gives the same bytes and the same checksum everywhere.
#
# What it does, in order:
#
#   1. Reads the version from the Version: line in cleanlanguage/SKILL.md at
#      HEAD; with --tag, fails unless the tag is v<version>. Also requires the
#      skill name line and at least one Markdown reference, the two structural
#      checks the previous inline validation enforced.
#   2. Requires every git entry under cleanlanguage/ to carry mode 100644,
#      which rejects executable files (100755), symlinks (120000), and
#      submodules (160000) in one comparison.
#   3. Requires every path to match the package allowlist by shape: SKILL.md,
#      agent configuration in agents/, the CL_icon files in assets/, and
#      Markdown references in references/. This checks path shape and git mode,
#      not file content: a new flat Markdown reference is allowed, while a new
#      directory, a script extension, or a nested path fails.
#   4. Requires every icon the ChatGPT interface configuration references to
#      exist in the package, whether the YAML quotes the path with double
#      quotes, single quotes, or none.
#   5. Stages the package from git archive, adds LICENSE and NOTICE.md into
#      cleanlanguage/, and zips it, so the zip holds exactly what git records
#      plus the two licence files, whatever state the checkout is in.
#   6. Verifies the archive against an expected entry list derived from the
#      same git tree, and verifies every archived file's bytes against its git
#      blob, so a git attribute such as export-subst cannot change the shipped
#      bytes unnoticed.
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

git cat-file -e HEAD:cleanlanguage/SKILL.md 2>/dev/null \
  || fail "cleanlanguage/SKILL.md is missing at HEAD"
skill="$(git show HEAD:cleanlanguage/SKILL.md)"
version="$(printf '%s\n' "${skill}" \
  | sed -n 's/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p' | head -1)"
[ -n "${version}" ] || fail "no Version: line found in cleanlanguage/SKILL.md at HEAD"
if [ -n "${tag}" ] && [ "v${version}" != "${tag}" ]; then
  fail "SKILL.md version (${version}) does not match the tag (${tag})"
fi
printf '%s\n' "${skill}" | grep -Eq '^name:[[:space:]]*cleanlanguage[[:space:]]*$' \
  || fail "cleanlanguage/SKILL.md is missing the 'name: cleanlanguage' line"

bad_modes="$(git ls-tree -r HEAD -- cleanlanguage | awk '$1 != "100644"')"
if [ -n "${bad_modes}" ]; then
  printf 'release-package: every packaged file must be a regular, non-executable file (git mode 100644); found:\n%s\n' "${bad_modes}" >&2
  exit 1
fi

files="$(git ls-tree -r HEAD --name-only -- cleanlanguage)"
[ -n "${files}" ] || fail "git records no files under cleanlanguage/"
printf '%s\n' "${files}" | grep -Eq '^cleanlanguage/references/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.md$' \
  || fail "cleanlanguage/references holds no Markdown reference at HEAD"
unexpected="$(printf '%s\n' "${files}" | grep -Ev \
  '^cleanlanguage/(SKILL\.md|agents/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.yaml|assets/CL_icon\.(png|svg)|references/[a-z0-9]([a-z0-9-]*[a-z0-9])?\.md)$' \
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
  git show HEAD:cleanlanguage/agents/openai.yaml | python3 -c '
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

staging="$(mktemp -d)"
trap 'rm -rf "${staging}"' EXIT
git archive --format=tar HEAD cleanlanguage | tar -xf - -C "${staging}"
git show HEAD:LICENSE > "${staging}/cleanlanguage/LICENSE"
git show HEAD:NOTICE.md > "${staging}/cleanlanguage/NOTICE.md"
chmod 644 "${staging}/cleanlanguage/LICENSE" "${staging}/cleanlanguage/NOTICE.md"

# A byte-reproducible archive: stamp every staged path with the commit's own
# timestamp, order the entries, and read the DOS times in UTC, so the same
# commit always yields the same zip and therefore the same checksum, on any
# machine and at any clock time. Without this the staged licence files would
# carry the build clock, so a later rebuild of the same commit would not match.
commit_epoch="$(git show -s --format=%ct HEAD)"
# Canonical, umask-independent modes for a distributed artefact: the packaged
# files carry only regular content (the mode gate above rejects anything but
# 100644), so normalise every directory to 0755 and every file to 0644. Zip
# records the Unix mode in each entry, so without this an ambient umask would
# change the central-directory bytes and the checksum for the same commit.
find "${staging}" -type d -exec chmod 755 {} +
find "${staging}" -type f -exec chmod 644 {} +
find "${staging}" -exec touch -h -d "@${commit_epoch}" {} +

rm -rf dist
mkdir -p dist
dist_dir="$(pwd)/dist"
# Clear ZIP and ZIPOPT so an ambient option (for example ZIPOPT=-0) cannot
# change the archive bytes; -D omits directory records (whose modes and order
# would otherwise vary); -X drops uid/gid and the extra timestamp fields; the
# sorted list and TZ=UTC fix entry order and the DOS times. Same commit, same
# bytes, on any machine and at any clock time and umask.
(cd "${staging}" && find cleanlanguage -print | LC_ALL=C sort \
  | env -u ZIP -u ZIPOPT TZ=UTC zip -q -X -D -@ "${dist_dir}/cleanlanguage.zip")
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

# Every archived byte must equal its git blob, so a git attribute such as
# export-subst cannot alter the shipped content while leaving the names intact.
while IFS= read -r entry; do
  [ -n "${entry}" ] || continue
  case "${entry}" in
    cleanlanguage/LICENSE) blob="HEAD:LICENSE" ;;
    cleanlanguage/NOTICE.md) blob="HEAD:NOTICE.md" ;;
    *) blob="HEAD:${entry}" ;;
  esac
  if ! cmp -s <(unzip -p dist/cleanlanguage.zip "${entry}") <(git cat-file blob "${blob}"); then
    echo "release-package: archived ${entry} differs from its git blob (${blob})" >&2
    exit 1
  fi
done <<EOF_ENTRIES
${actual}
EOF_ENTRIES

echo "release-package: dist/cleanlanguage-${version}.zip built and verified for version ${version}."
printf '%s\n' "${actual}" | sed 's/^/  /'
