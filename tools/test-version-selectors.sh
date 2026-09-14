#!/usr/bin/env bash
#
# Cross-consumer contract for the shell and CI Version: selectors.
#
# Four shell selectors read the skill version. They are now consolidated onto the
# strict, first-line-authoritative rule the Python release gates apply
# (check-release-links.py, check-release-checksum-live.py, release-package.sh):
# the FIRST ^Version: line is authoritative and must be a bare X.Y.Z; a malformed
# first line is REJECTED, never skipped to a later matching one. Each selector
# also captures the whole file into a variable FIRST and then extracts from that
# variable, so an early-quitting sed never sends SIGPIPE to a live producer (a
# valid but large SKILL.md over the ~64KB pipe buffer used to abort with exit 141
# under set -o pipefail), and it normalizes CR to LF before extracting, matching
# the gates' Python universal-newline read (Path.read_text) so a CRLF or lone-CR
# line agrees.
#
# The four selector sites:
#   1. tools/release-dry-run.sh              (git show HEAD:SKILL.md)
#   2. .github/workflows/release-skill.yml   (SKILL.md working tree, and main via
#                                             git show FETCH_HEAD:SKILL.md)
#   3. tools/check-portable-text-sync.sh     (version_of helper, cat "$1")
#
# This test exercises the REAL logic of each site, not a hand-copied stand-in:
#   A. version_of is EXTRACTED from check-portable-text-sync.sh and run.
#   B. The selector block of each other site is EXTRACTED from its real source
#      and run in that site's real producer environment (a throwaway git repo for
#      the git-show reads; a throwaway working tree for the file reads).
#   C. Every fixture's expected value is computed by a Python oracle that applies
#      the gates' own universal-newline read and VERSION_LINE / SKILL_VERSION
#      regexes, so the shell selectors are pinned to the gates' rule rather than
#      to hardcoded numbers.
#   D. A structural guard asserts the loose pattern is gone (fixed-string match,
#      so it genuinely detects the loose selector on main), no live producer is
#      piped into the early-quit sed (the SIGPIPE regression), CR normalization is
#      present, and the strict marker is present, at every site.
#
# Fixtures include a LARGE (>64KB) valid file (each site must still return the
# version and exit 0: the SIGPIPE regression test), a CRLF file (must return the
# version), and a lone-CR case (the hidden first Version line is selected, and a
# lone-CR malformed first line is rejected).
#
# One documented residual: bash command substitution strips NUL bytes, so a NUL
# inside the version line, which the Python gates reject, is not caught by these
# shell selectors. The Python release gate (release-package.sh) is authoritative
# for that byte-exact case, and tools/test-skill-version-consumers.py pins it. No
# NUL fixture is asserted here for that reason.
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

# --- Structural guard --------------------------------------------------------
# Runs first, before any extraction, so it registers findings even when a site
# has reverted to a form the extraction below cannot parse. The loose selector
# body is matched as a FIXED string: the previous guard used an ERE with an
# unescaped mid-pattern '^', which is only an anchor at position 0 and so never
# matched, falsely reporting "no loose selector" even on main where the loose
# selector is present. A fixed-string match genuinely detects it.
loose_body='s/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p'
# The strict marker is the first-^Version-line select ('{p;q}'). Its early-quit
# 'q' is SIGPIPE-safe only off a captured variable, so we also assert it is never
# fed by a live producer ('| sed' on the same line as '{p;q}').
declare -A selector_count=(
  ["tools/release-dry-run.sh"]=1
  ["tools/check-portable-text-sync.sh"]=1
  [".github/workflows/release-skill.yml"]=2
)
for site in tools/release-dry-run.sh tools/check-portable-text-sync.sh .github/workflows/release-skill.yml; do
  if grep -Fq "${loose_body}" "${site}"; then
    fail "structural: loose Version selector still present in ${site}"
  else
    pass "structural: no loose Version selector in ${site}"
  fi
  if grep -F '{p;q}' "${site}" | grep -Fq '| sed'; then
    fail "structural: a live producer is piped into the early-quit sed in ${site} (SIGPIPE risk)"
  else
    pass "structural: no live producer piped into the early-quit sed in ${site}"
  fi
  if grep -Eq "//\\\$.\\\\r" "${site}"; then
    pass "structural: CR-to-LF normalization present in ${site}"
  else
    fail "structural: CR-to-LF normalization missing in ${site}"
  fi
  if grep -Fq '^Version:[ \t]*[0-9]+' "${site}"; then
    pass "structural: strict bare-X.Y.Z marker present in ${site}"
  else
    fail "structural: strict bare-X.Y.Z marker missing in ${site}"
  fi
  # Count the here-string selectors ('sed ... {p;q}' <<<"${...}") by their
  # here-string operator, so a prose mention of {p;q} in a comment is not counted.
  got="$(grep -Fc '<<<"${' "${site}" || true)"
  assert_eq "structural: strict selector count in ${site}" "${selector_count[$site]}" "${got}"
done

# --- The gates' own rule, as a Python oracle ---------------------------------
# Reads the file with universal newlines (newline=None), exactly as Path.read_text
# does in check-release-links.py / check-release-checksum-live.py, then applies the
# gates' VERSION_LINE and SKILL_VERSION patterns verbatim. Prints the version, or
# empty for a reject. This is what every shell selector must agree with.
gate_expect() { # file
  python3 - "$1" <<'PY'
import io, re, sys
data = open(sys.argv[1], "rb").read()
try:
    text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None).read()
except UnicodeDecodeError:
    print("")
    sys.exit(0)
line = re.search(r"^Version:[^\n]*", text, re.M)
if line is None:
    print("")
    sys.exit(0)
m = re.match(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$", line.group(0))
print(m.group(1) if m else "")
PY
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

# --- Extract the selector block of each other site from its real source -------
# Prints the lines from the first line containing START through the first later
# line containing END (both fixed substrings), so the code under test is the real
# site's own, never a copy that could drift from it.
extract_block() { # file start end
  awk -v s="$2" -v e="$3" '
    index($0,s){on=1}
    on{print}
    on && index($0,e){exit}
  ' "$1"
}

DRY_BLOCK="$(extract_block tools/release-dry-run.sh \
  'skill_content="$(git show HEAD:cleanlanguage/SKILL.md)"' 'version="$(')"
WF_LOCAL_BLOCK="$(extract_block .github/workflows/release-skill.yml \
  'skill_content="$(cat cleanlanguage/SKILL.md)"' 'version="$(')"
WF_MAIN_BLOCK="$(extract_block .github/workflows/release-skill.yml \
  'main_skill_content="$(git show FETCH_HEAD:cleanlanguage/SKILL.md)"' 'main_version="$(')"
for name in DRY_BLOCK WF_LOCAL_BLOCK WF_MAIN_BLOCK; do
  [ -n "${!name}" ] || { echo "Could not extract ${name} from its source" >&2; exit 1; }
done

git_id=(-c user.email=t@t -c user.name=t -c commit.gpgsign=false)

# --- Runners: each drives one real site against a fixture file ----------------
# Every runner prints the selected version to stdout (empty on reject) and exits
# non-zero on reject, so a single output comparison covers accept and reject.

# Site 3: version_of, reading the fixture file directly (cat "$1").
run_version_of() { version_of "$1"; }

# Site 1: release-dry-run.sh, reading git show HEAD:cleanlanguage/SKILL.md.
run_dry() { # fixture-file
  local repo out rc
  repo="$(mktemp -d)"
  mkdir -p "${repo}/cleanlanguage"
  cp "$1" "${repo}/cleanlanguage/SKILL.md"
  git init -q "${repo}"
  git -C "${repo}" "${git_id[@]}" add cleanlanguage/SKILL.md
  git -C "${repo}" "${git_id[@]}" commit -qm fixture >/dev/null
  # Stub fail() to exit, matching release-dry-run.sh's own fail (which exits): a
  # reject then aborts the subshell, so a malformed line yields empty and non-zero.
  out="$(cd "${repo}"; set -euo pipefail; fail() { exit 1; }; eval "${DRY_BLOCK}"; printf '%s' "${version}")" && rc=0 || rc=$?
  rm -rf "${repo}"
  printf '%s' "${out}"
  return "${rc}"
}

# Site 2a: release-skill.yml working-tree read (cat cleanlanguage/SKILL.md).
run_wf_local() { # fixture-file
  local dir out rc
  dir="$(mktemp -d)"
  mkdir -p "${dir}/cleanlanguage"
  cp "$1" "${dir}/cleanlanguage/SKILL.md"
  out="$(cd "${dir}"; set -euo pipefail; eval "${WF_LOCAL_BLOCK}"; printf '%s' "${version}")" && rc=0 || rc=$?
  rm -rf "${dir}"
  printf '%s' "${out}"
  return "${rc}"
}

# Site 2b: release-skill.yml main read (git show FETCH_HEAD:cleanlanguage/SKILL.md).
run_wf_main() { # fixture-file
  local remote local_repo out rc
  remote="$(mktemp -d)"
  mkdir -p "${remote}/cleanlanguage"
  cp "$1" "${remote}/cleanlanguage/SKILL.md"
  git init -q "${remote}"
  git -C "${remote}" "${git_id[@]}" add cleanlanguage/SKILL.md
  git -C "${remote}" "${git_id[@]}" commit -qm fixture >/dev/null
  local_repo="$(mktemp -d)"
  git init -q "${local_repo}"
  git -C "${local_repo}" fetch --quiet "${remote}" HEAD
  out="$(cd "${local_repo}"; set -euo pipefail; eval "${WF_MAIN_BLOCK}"; printf '%s' "${main_version}")" && rc=0 || rc=$?
  rm -rf "${remote}" "${local_repo}"
  printf '%s' "${out}"
  return "${rc}"
}

declare -A RUNNERS=(
  [version_of]=run_version_of
  [release-dry-run]=run_dry
  [workflow-local]=run_wf_local
  [workflow-main]=run_wf_main
)

# --- Fixtures ----------------------------------------------------------------
# label|body   (body is rendered by printf %b, so \n \r \t are honoured). The
# expected value is computed by the gate oracle, never hardcoded.
fixtures=(
  "valid|Version: 1.0.14\nBody line.\n"
  "valid_trailing_spaces|Version: 1.2.3  \n"
  "valid_trailing_tab|Version: 1.2.3\t\n"
  "malformed_first_trailing_text|Version: 9.9.9 trailing\nVersion: 1.2.3\n"
  "malformed_first_draft|Version: draft\nVersion: 1.2.3\n"
  "two_part|Version: 1.2\n"
  "four_part|Version: 1.2.3.4\n"
  "double_dot|Version: 1..2\n"
  "no_version_line|This file has no version line.\n"
  "crlf|Version: 1.2.3\r\nBody line.\r\n"
  "crlf_trailing_spaces|Version: 1.2.3  \r\n"
  "lone_cr_hidden_valid|foo\rVersion: 1.0.0\nVersion: 2.0.0\n"
  "lone_cr_malformed_first|Version: 9.9.9 draft\rVersion: 1.2.3\n"
)

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

for entry in "${fixtures[@]}"; do
  label="${entry%%|*}"; body="${entry#*|}"
  f="${tmp}/${label}.md"
  printf '%b' "${body}" > "${f}"
  expected="$(gate_expect "${f}")"
  for site in version_of release-dry-run workflow-local workflow-main; do
    got="$("${RUNNERS[$site]}" "${f}")" || true
    assert_eq "${site}: ${label}" "${expected}" "${got}"
  done
done

# --- Large valid file: the SIGPIPE regression test ---------------------------
# A valid SKILL.md well over the ~64KB pipe buffer. Each site must still return
# the version AND exit 0. Before the fix, the git-show sites piped a live producer
# into an early-quitting sed, which aborted with exit 141 under set -o pipefail.
large="${tmp}/large_valid.md"
{ printf 'Version: 1.0.14\n'; head -c 200000 /dev/zero | tr '\0' 'x'; printf '\n'; } > "${large}"
large_bytes="$(wc -c < "${large}")"
[ "${large_bytes}" -gt 65536 ] || fail "large fixture is only ${large_bytes} bytes, not over the 64KB pipe buffer"
large_expected="$(gate_expect "${large}")"
for site in version_of release-dry-run workflow-local workflow-main; do
  got="$("${RUNNERS[$site]}" "${large}")"; rc=$?
  assert_eq "large-valid version: ${site}" "${large_expected}" "${got}"
  assert_eq "large-valid exit 0 (no SIGPIPE): ${site}" "0" "${rc}"
done

# --- No behaviour change on the real SKILL.md --------------------------------
# Every site must read the real skill's version the way the gates' rule does.
real_expected="$(gate_expect cleanlanguage/SKILL.md)"
[ -n "${real_expected}" ] || fail "the gates' rule read no bare X.Y.Z from the real SKILL.md"
for site in version_of release-dry-run workflow-local workflow-main; do
  got="$("${RUNNERS[$site]}" cleanlanguage/SKILL.md)" || true
  assert_eq "real SKILL.md: ${site}" "${real_expected}" "${got}"
done

echo
if [ "${fails}" -eq 0 ]; then
  echo "All version-selector checks passed."
  exit 0
fi
echo "${fails} version-selector check(s) failed." >&2
exit 1
