#!/usr/bin/env bash
#
# Flags when the packaged skill changes without the portable instructions file
# being reconciled.
#
# The portable text at site/downloads/cleanlanguage-instructions.txt is a
# hand-maintained flat rendering of the skill, so this check cannot compare the
# two byte for byte. Instead it records a hash of the skill source (SKILL.md and
# every reference file). When the skill changes, the recorded hash no longer
# matches, and this check fails until a maintainer reviews the portable text,
# brings it back into line with the skill, and records the new hash with
# --update.
#
# This is a reconciliation gate, not a proof of semantic equivalence. It forces
# a deliberate review of the portable text whenever the skill source changes; it
# does not verify that the review made the two say the same thing.
#
# Usage:
#   tools/check-portable-text-sync.sh            Check and exit non-zero on drift.
#   tools/check-portable-text-sync.sh --update   Record the current skill hash.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

recorded_file="tools/portable-text-skill-source.sha256"

# Hash SKILL.md followed by every reference file, in a stable sorted order, so
# the result depends only on content and not on filesystem ordering.
mapfile -t skill_files < <(
  printf '%s\n' "cleanlanguage/SKILL.md"
  find cleanlanguage/references -type f -name '*.md' | sort
)

for f in "${skill_files[@]}"; do
  if [ ! -f "${f}" ]; then
    echo "Expected skill file is missing: ${f}" >&2
    exit 1
  fi
done

computed="$(cat "${skill_files[@]}" | sha256sum | cut -d' ' -f1)"

if [ "${1:-}" = "--update" ]; then
  printf '%s\n' "${computed}" > "${recorded_file}"
  echo "Recorded skill-source hash ${computed} in ${recorded_file}."
  echo "Confirm site/downloads/cleanlanguage-instructions.txt matches the skill before committing."
  exit 0
fi

if [ ! -f "${recorded_file}" ]; then
  echo "Missing ${recorded_file}. Record it with: tools/check-portable-text-sync.sh --update" >&2
  exit 1
fi

recorded="$(tr -d '[:space:]' < "${recorded_file}")"

if [ "${computed}" != "${recorded}" ]; then
  cat >&2 <<EOF
The skill source changed but the portable instructions file was not reconciled.

The packaged skill (cleanlanguage/SKILL.md and cleanlanguage/references/*.md)
no longer matches the hash recorded in ${recorded_file}.

Review the portable rendering at
site/downloads/cleanlanguage-instructions.txt, bring it back into line with the
skill, then record the new hash:

  tools/check-portable-text-sync.sh --update

Recorded: ${recorded}
Computed: ${computed}
EOF
  exit 1
fi

echo "Portable instructions are reconciled with the skill source (${computed})."
