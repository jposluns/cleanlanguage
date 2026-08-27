#!/usr/bin/env bash
#
# Keeps the two portable renderings of the skill in step with the source.
#
# site/downloads/cleanlanguage.md is GENERATED from the skill by
# tools/build-portable-text.py, so this gate regenerates it and the
# /instructions/ embed and fails on any byte drift.
#
# site/downloads/cleanlanguage-short.md is a hand-maintained condensed rendering
# that cannot be compared byte for byte, so this gate records a hash of the skill
# source (SKILL.md and every reference). When the skill changes the hash no
# longer matches and the gate fails until a maintainer reconciles the condensed
# file and re-records with --update. It is a reconciliation gate, not a proof of
# equivalence.
#
# It also checks that both portable files open with the canonical first line and
# that the Version agrees across the skill and both files.
#
# Usage:
#   tools/check-portable-text-sync.sh            Check; exit non-zero on drift.
#   tools/check-portable-text-sync.sh --update   Regenerate, verify, record the hash.

set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

recorded_file="tools/portable-text-skill-source.sha256"
extended="site/downloads/cleanlanguage.md"
short="site/downloads/cleanlanguage-short.md"
opening="This is the Clean Language skill, written out as rules. Apply it to the writing in this conversation unless I tell you not to."

version_of() { sed -n 's/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p' "$1" | head -1; }

check_common() {
  for f in "${extended}" "${short}"; do
    [ -f "${f}" ] || { echo "Missing ${f}." >&2; return 1; }
    if [ "$(head -1 "${f}")" != "${opening}" ]; then
      echo "${f} does not open with the canonical first line." >&2; return 1
    fi
  done
  local sv ev shv
  sv="$(version_of cleanlanguage/SKILL.md)"; ev="$(version_of "${extended}")"; shv="$(version_of "${short}")"
  if [ -z "${sv}" ] || [ "${sv}" != "${ev}" ] || [ "${sv}" != "${shv}" ]; then
    echo "Version disagreement: SKILL.md=${sv} ${extended}=${ev} ${short}=${shv}." >&2; return 1
  fi
}

mapfile -t skill_files < <(printf '%s\n' "cleanlanguage/SKILL.md"; find cleanlanguage/references -type f -name '*.md' | sort)
for f in "${skill_files[@]}"; do [ -f "${f}" ] || { echo "Missing skill file: ${f}" >&2; exit 1; }; done
computed="$(for f in "${skill_files[@]}"; do printf '%s  %s\n' "$(sha256sum "${f}" | cut -d' ' -f1)" "${f}"; done | sha256sum | cut -d' ' -f1)"

if [ "${1:-}" = "--update" ]; then
  # Refuse to bless a stale condensed file: if the source hash changed but
  # cleanlanguage-short.md was not touched, the reconciliation did not happen.
  if [ -f "${recorded_file}" ] && [ "${computed}" != "$(tr -d '"'"'[:space:]'"'"' < "${recorded_file}")" ]; then
    if git -C "${repo_root}" diff --quiet HEAD -- "${short}" 2>/dev/null && [ "${2:-}" != "--force" ]; then
      echo "The skill source changed but ${short} was not modified; reconcile it, or pass --force if no change is needed." >&2
      exit 1
    fi
  fi
  python3 tools/build-portable-text.py --embed >/dev/null
  check_common || { echo "Refusing to record: the portable files failed the opening or version check." >&2; exit 1; }
  python3 tools/build-portable-text.py --check || { echo "Refusing to record: the generated file or embed is out of date." >&2; exit 1; }
  printf '%s\n' "${computed}" > "${recorded_file}"
  echo "Recorded skill-source hash ${computed}. Reconcile ${short} with the skill before committing."
  exit 0
fi

python3 tools/build-portable-text.py --check
check_common

[ -f "${recorded_file}" ] || { echo "Missing ${recorded_file}. Record with --update." >&2; exit 1; }
recorded="$(tr -d '[:space:]' < "${recorded_file}")"
if [ "${computed}" != "${recorded}" ]; then
  cat >&2 <<EOF
The skill source changed but the condensed portable file was not reconciled.
Review ${short}, bring it into line with the skill, then re-record:
  tools/check-portable-text-sync.sh --update
Recorded: ${recorded}
Computed: ${computed}
EOF
  exit 1
fi
echo "Portable files reconciled with the skill source (${computed}); generated file and embed are current."
