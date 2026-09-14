#!/usr/bin/env bash
#
# Cross-consumer contract for the shell and CI Version: selectors.
#
# Four loose selectors used to read the skill version with
#   sed -n 's/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p' ... | head -1
# which matches loosely and, via head -1 after a per-line match, silently SKIPS
# a malformed first Version: line to a later matching one. They are now
# consolidated onto the strict, first-line-authoritative rule the Python release
# gates apply (check-release-links.py, check-release-checksum-live.py): the FIRST
# ^Version: line is authoritative and must be a bare X.Y.Z; a malformed first
# line is REJECTED, never skipped.
#
# The four selectors:
#   1. tools/release-dry-run.sh              (git show HEAD:SKILL.md)
#   2. .github/workflows/release-skill.yml   (SKILL.md, x2: local and main)
#   3. tools/check-portable-text-sync.sh     (version_of helper)
#
# This test pins the strict rule three ways:
#   A. The real version_of helper is extracted from check-portable-text-sync.sh
#      and exercised against fixtures: a malformed first line must yield empty.
#   B. The stream form (used by the git show / file selectors) is exercised
#      against the same fixtures.
#   C. A structural guard asserts the loose pattern is gone from all four sites
#      and the strict marker is present.
#
# It runs offline and reads only fixtures and the repo's own files.
#
# Usage:
#   tools/test-version-selectors.sh          Run; exit non-zero on any failure.

set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

fails=0
pass() { printf 'ok   - %s\n' "$1"; }
fail() { printf 'FAIL - %s\n' "$1" >&2; fails=$((fails + 1)); }

assert_eq() { # label expected actual
  if [ "$2" = "$3" ]; then pass "$1"; else
    fail "$1 (expected [$2], got [$3])"
  fi
}

# --- Extract the real version_of from check-portable-text-sync.sh -------------
# A brace counter copes with both the single-line (loose) and multi-line (strict)
# function forms, so the same test goes red against either the pre-change or the
# post-change source it reads.
extract_version_of() {
  awk '
    !started && /^version_of\(\)/ { started=1; depth=0 }
    started {
      tmp=$0; o=gsub(/\{/,"",tmp)
      tmp=$0; c=gsub(/\}/,"",tmp)
      print
      depth += o - c
      if (depth==0) exit
    }
  ' "$1"
}

version_of_src="$(extract_version_of tools/check-portable-text-sync.sh)"
[ -n "${version_of_src}" ] || { echo "Could not extract version_of from check-portable-text-sync.sh" >&2; exit 1; }
eval "${version_of_src}"

# --- The stream form (git show / file selectors) as one function -------------
# Identical strict logic to tools/release-dry-run.sh and release-skill.yml:
# take the first ^Version: line, require a bare X.Y.Z, extract it, else empty.
stream_version() {
  local line
  line="$(sed -n '/^Version:/{p;q}')"
  printf '%s' "${line}" | grep -Eq $'^Version:[ \t]*[0-9]+\\.[0-9]+\\.[0-9]+[ \t]*$' || return 0
  printf '%s' "${line}" | sed -E $'s/^Version:[ \t]*([0-9]+\\.[0-9]+\\.[0-9]+)[ \t]*$/\\1/'
}

# --- Fixtures ----------------------------------------------------------------
# label|expected|body   (body \n rendered by printf %b)
fixtures=(
  "valid|1.0.14|Version: 1.0.14\nBody line.\n"
  "valid_trailing_spaces|1.2.3|Version: 1.2.3  \n"
  "valid_trailing_tab|1.2.3|Version: 1.2.3\t\n"
  "malformed_first_trailing_text||Version: 9.9.9 trailing\nVersion: 1.2.3\n"
  "malformed_first_draft||Version: draft\nVersion: 1.2.3\n"
  "two_part||Version: 1.2\n"
  "four_part||Version: 1.2.3.4\n"
  "double_dot||Version: 1..2\n"
  "no_version_line||This file has no version line.\n"
)

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

for entry in "${fixtures[@]}"; do
  label="${entry%%|*}"; rest="${entry#*|}"
  expected="${rest%%|*}"; body="${rest#*|}"
  f="${tmp}/${label}.md"
  printf '%b' "${body}" > "${f}"
  assert_eq "version_of: ${label}" "${expected}" "$(version_of "${f}")"
  assert_eq "stream:     ${label}" "${expected}" "$(stream_version < "${f}")"
done

# --- No behaviour change on the real SKILL.md --------------------------------
# The version both selectors read from the real skill must equal the version the
# gates' own rule reads, and must be a bare X.Y.Z. Computed here by the gates'
# identical regex, so the check is not pinned to a hardcoded number.
expected_real="$(python3 - <<'PY'
import re, pathlib
text = pathlib.Path("cleanlanguage/SKILL.md").read_text(encoding="utf-8")
line = re.search(r"^Version:[^\n]*", text, re.M)
m = re.match(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$", line.group(0)) if line else None
print(m.group(1) if m else "")
PY
)"
[ -n "${expected_real}" ] || fail "the gates' rule read no bare X.Y.Z from the real SKILL.md"
assert_eq "version_of: real SKILL.md matches the gate rule" "${expected_real}" "$(version_of cleanlanguage/SKILL.md)"
assert_eq "stream:     real SKILL.md matches the gate rule" "${expected_real}" "$(stream_version < cleanlanguage/SKILL.md)"

# --- Structural guard: the loose pattern is gone; the strict marker is present -
loose='s/^Version:\[\[:space:\]\]'
declare -A strict_count=(
  ["tools/release-dry-run.sh"]=1
  ["tools/check-portable-text-sync.sh"]=1
  [".github/workflows/release-skill.yml"]=2
)
for site in tools/release-dry-run.sh tools/check-portable-text-sync.sh .github/workflows/release-skill.yml; do
  if grep -Eq "${loose}" "${site}"; then
    fail "structural: loose Version selector still present in ${site}"
  else
    pass "structural: no loose Version selector in ${site}"
  fi
  got="$(grep -Fc "sed -n '/^Version:/{p;q}'" "${site}" || true)"
  assert_eq "structural: strict marker count in ${site}" "${strict_count[$site]}" "${got}"
done

echo
if [ "${fails}" -eq 0 ]; then
  echo "All version-selector checks passed."
  exit 0
fi
echo "${fails} version-selector check(s) failed." >&2
exit 1
