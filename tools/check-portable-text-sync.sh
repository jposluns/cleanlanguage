#!/usr/bin/env bash
#
# Keeps the portable renderings of the skill in step with the source and within
# their size labels.
#
# The size-labelled family in site/downloads/:
#   cleanlanguage.md      the canonical file; always byte-equal to the largest
#                         size-labelled rendering (29k for now).
#   cleanlanguage-29k.md  the largest rendering; GENERATED from the skill by
#                         tools/build-portable-text.py, byte-equal to cleanlanguage.md.
#   cleanlanguage-11k.md  a hand-maintained condensed rendering (<= 11000 chars).
#   cleanlanguage-8k.md   a hand-maintained further-condensed rendering (<= 8000
#                         chars) for assistants that cap instruction length.
#
# The generated files are checked byte-for-byte by build-portable-text.py --check.
# The hand-maintained files cannot be compared byte for byte, so this gate records
# a hash of the skill source (SKILL.md and every reference); when the skill changes
# the hash no longer matches and the gate fails until a maintainer reconciles both
# hand-maintained files and re-records with --update. It also checks that every
# file opens with the canonical first line, that the Version agrees across the
# skill and all files, that cleanlanguage.md and cleanlanguage-29k.md are byte-
# equal, and that the condensed files are within their size labels.
#
# Usage:
#   tools/check-portable-text-sync.sh            Check; exit non-zero on drift.
#   tools/check-portable-text-sync.sh --update   Regenerate, verify, record the hash.

set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

recorded_file="tools/portable-text-skill-source.sha256"
canonical="site/downloads/cleanlanguage.md"
twin29="site/downloads/cleanlanguage-29k.md"
eleven="site/downloads/cleanlanguage-11k.md"
eight="site/downloads/cleanlanguage-8k.md"
hand_maintained=("${eleven}" "${eight}")
all_files=("${canonical}" "${twin29}" "${eleven}" "${eight}")
opening="This is the Clean Language skill, written out as rules. Apply it to the writing in this conversation unless I tell you not to."

version_of() { sed -n 's/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p' "$1" | head -1; }

check_common() {
  local f
  for f in "${all_files[@]}"; do
    [ -f "${f}" ] || { echo "Missing ${f}." >&2; return 1; }
    if [ "$(head -1 "${f}")" != "${opening}" ]; then
      echo "${f} does not open with the canonical first line." >&2; return 1
    fi
  done
  local sv
  sv="$(version_of cleanlanguage/SKILL.md)"
  [ -n "${sv}" ] || { echo "No Version in cleanlanguage/SKILL.md." >&2; return 1; }
  for f in "${all_files[@]}"; do
    if [ "$(version_of "${f}")" != "${sv}" ]; then
      echo "Version disagreement: SKILL.md=${sv}, ${f}=$(version_of "${f}")." >&2; return 1
    fi
  done
  # The canonical file mirrors the largest rendering byte-for-byte.
  if ! cmp -s "${canonical}" "${twin29}"; then
    echo "${canonical} is not byte-equal to ${twin29}." >&2; return 1
  fi
  # The condensed files must stay within their size labels.
  local n
  n="$(wc -m < "${eight}")"
  [ "${n}" -le 8000 ] || { echo "${eight} is ${n} chars, over its 8000 label." >&2; return 1; }
  n="$(wc -m < "${eleven}")"
  [ "${n}" -le 11000 ] || { echo "${eleven} is ${n} chars, over its 11000 label." >&2; return 1; }
}

mapfile -t skill_files < <(printf '%s\n' "cleanlanguage/SKILL.md"; find cleanlanguage/references -type f -name '*.md' | sort)
for f in "${skill_files[@]}"; do [ -f "${f}" ] || { echo "Missing skill file: ${f}" >&2; exit 1; }; done
computed="$(for f in "${skill_files[@]}"; do printf '%s  %s\n' "$(sha256sum "${f}" | cut -d' ' -f1)" "${f}"; done | sha256sum | cut -d' ' -f1)"

if [ "${1:-}" = "--update" ]; then
  # Refuse to bless stale condensed files: if the source hash changed but a
  # hand-maintained rendering was not touched, the reconciliation did not happen.
  if [ -f "${recorded_file}" ] && [ "${computed}" != "$(tr -d '[:space:]' < "${recorded_file}")" ]; then
    for f in "${hand_maintained[@]}"; do
      if git -C "${repo_root}" diff --quiet HEAD -- "${f}" 2>/dev/null && [ "${2:-}" != "--force" ]; then
        echo "The skill source changed but ${f} was not modified; reconcile it, or pass --force if no change is needed." >&2
        exit 1
      fi
    done
  fi
  python3 tools/build-portable-text.py --embed >/dev/null
  check_common || { echo "Refusing to record: the portable files failed a common check." >&2; exit 1; }
  python3 tools/build-portable-text.py --check || { echo "Refusing to record: a generated file or the embed is out of date." >&2; exit 1; }
  printf '%s\n' "${computed}" > "${recorded_file}"
  echo "Recorded skill-source hash ${computed}. Reconcile the condensed files with the skill before committing."
  exit 0
fi

python3 tools/build-portable-text.py --check
check_common

[ -f "${recorded_file}" ] || { echo "Missing ${recorded_file}. Record with --update." >&2; exit 1; }
recorded="$(tr -d '[:space:]' < "${recorded_file}")"
if [ "${computed}" != "${recorded}" ]; then
  cat >&2 <<EOF
The skill source changed but the condensed portable files were not reconciled.
Review ${eleven} and ${eight}, bring them into line with the skill, then re-record:
  tools/check-portable-text-sync.sh --update
Recorded: ${recorded}
Computed: ${computed}
EOF
  exit 1
fi
echo "Portable files reconciled with the skill source (${computed}); generated files and embed are current."
