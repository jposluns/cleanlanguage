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
# skill and all files, that the skill carries a well-formed Released line when
# its version sorts above the undated baseline and that every file carries the
# same Released value as the skill (or none when the skill has none), that
# cleanlanguage.md and cleanlanguage-29k.md are byte-equal, and that the
# condensed files are within their size labels.
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

# The first Version: line is authoritative and must be a bare X.Y.Z, the same
# strict rule the release gates apply. A malformed first line is rejected (empty
# output), never skipped to a later matching line; callers treat empty as an
# error.
#
# One shared strict extractor, tools/skill-version.py, does the reading and
# validation, so this helper agrees with the workflow, the dry run, and the
# Python gates byte for byte (including on CRLF, a lone CR, and a NUL). It reads
# the file directly, so there is no early-quit pipe and no SIGPIPE on a large
# file. The contract callers rely on under set -e is unchanged: exit 0 always,
# printing the version on success and nothing on any failure (2>/dev/null || true
# absorbs the extractor's error message and non-zero exit).
version_of() {
  python3 tools/skill-version.py "$1" 2>/dev/null || true
}

# released_of FILE: print the Released date of FILE, or nothing when it has no
# line, and return 0; otherwise report why the line cannot be accepted and
# return 1. The one shared strict extractor, tools/skill-release-date.py, does
# the reading: exit 0 prints the date, 3 means no line, 1 is malformed content,
# 4 is an unreadable file, and anything else (2, 127, an interpreter failure)
# means the extractor itself is unavailable or crashed, which is reported as
# that, never as malformed content. Every exit but 0 and 3 fails closed.
released_of() {
  local out rc=0
  out="$(python3 tools/skill-release-date.py "$1" 2>/dev/null)" || rc=$?
  case "${rc}" in
    0) printf '%s\n' "${out}" ;;
    3) ;;
    1)
      echo "Malformed Released: line in $1: $(python3 tools/skill-release-date.py "$1" 2>&1 >/dev/null || true)" >&2
      return 1
      ;;
    4)
      echo "Could not read $1 for its Released line: $(python3 tools/skill-release-date.py "$1" 2>&1 >/dev/null || true)" >&2
      return 1
      ;;
    *)
      echo "tools/skill-release-date.py is unavailable or crashed (exit ${rc}) reading $1, so its Released line could not be checked." >&2
      return 1
      ;;
  esac
}

check_common() {
  local f
  for f in "${all_files[@]}"; do
    [ -f "${f}" ] || { echo "Missing ${f}." >&2; return 1; }
    if [ "$(head -1 "${f}")" != "${opening}" ]; then
      echo "${f} does not open with the canonical first line." >&2; return 1
    fi
  done
  local sv
  sv="$(version_of cleanlanguage/skills/cleanlanguage/SKILL.md)"
  [ -n "${sv}" ] || { echo "No valid bare X.Y.Z Version: line in cleanlanguage/skills/cleanlanguage/SKILL.md." >&2; return 1; }
  for f in "${all_files[@]}"; do
    if [ "$(version_of "${f}")" != "${sv}" ]; then
      echo "Version disagreement: SKILL.md=${sv}, ${f}=$(version_of "${f}")." >&2; return 1
    fi
  done
  # The Released line (item 26), read everywhere through released_of. G1: the
  # skill must carry the line when its version sorts above the baseline the
  # extractor declares (the last undated release), and may omit it at or below
  # that baseline; the extractor decides that comparison (--requires-date), so
  # no copy of the rule lives here. G2: every rendering carries the same parsed
  # value as the skill, or none when the skill has none; parsed values are
  # compared because the hand-maintained files carry no trailing hard-break
  # spaces. The extractor is probed first (--baseline), so a missing or broken
  # extractor is reported as unavailable before any content is judged.
  local sr baseline requirement fr prc=0
  baseline="$(python3 tools/skill-release-date.py --baseline 2>/dev/null)" || prc=$?
  if [ "${prc}" -ne 0 ] || ! printf '%s' "${baseline}" | grep -Eqx '[0-9]+\.[0-9]+\.[0-9]+'; then
    echo "tools/skill-release-date.py is unavailable or broken (probe exit ${prc}), so the Released lines could not be checked." >&2
    return 1
  fi
  sr="$(released_of cleanlanguage/skills/cleanlanguage/SKILL.md)" || return 1
  if [ -z "${sr}" ]; then
    prc=0
    requirement="$(python3 tools/skill-release-date.py --requires-date "${sv}" 2>/dev/null)" || prc=$?
    case "${prc}" in
      0) ;;
      1) echo "tools/skill-release-date.py rejected the version ${sv} as not a bare X.Y.Z." >&2; return 1 ;;
      *) echo "tools/skill-release-date.py is unavailable or crashed (exit ${prc}) deciding whether ${sv} needs a Released line." >&2; return 1 ;;
    esac
    if [ "${requirement}" = "required" ]; then
      echo "cleanlanguage/skills/cleanlanguage/SKILL.md is version ${sv}, above the undated baseline ${baseline}, but has no Released: YYYY-MM-DD line directly after its Version line." >&2
      return 1
    elif [ "${requirement}" != "optional" ]; then
      echo "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for whether ${sv} needs a Released line." >&2
      return 1
    fi
  fi
  for f in "${all_files[@]}"; do
    fr="$(released_of "${f}")" || return 1
    if [ "${fr}" != "${sr}" ]; then
      echo "Released disagreement: SKILL.md=${sr:-absent}, ${f}=${fr:-absent}." >&2; return 1
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

mapfile -t skill_files < <(printf '%s\n' "cleanlanguage/skills/cleanlanguage/SKILL.md"; find cleanlanguage/skills/cleanlanguage/references -type f -name '*.md' | sort)
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
