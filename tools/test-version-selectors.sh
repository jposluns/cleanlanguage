#!/usr/bin/env bash
#
# Cross-consumer contract for the shell and CI Version: selectors.
#
# Four selector sites read the skill version. They are now consolidated onto ONE
# shared strict extractor, tools/skill-version.py, which reads the content the way
# the Python release gates do (a universal-newline text read) and applies the
# gates' own VERSION_LINE / SKILL_VERSION regexes: the FIRST ^Version: line is
# authoritative and must be a bare X.Y.Z; a malformed first line is REJECTED,
# never skipped to a later matching one. Because the raw file or blob is handed
# straight to the extractor (a file path, or a pipe that it reads to the end),
# there is no early-quit sed and so no SIGPIPE on a large file, and the shell
# sites no longer strip NUL: they now agree with the Python gates BYTE FOR BYTE,
# including on the two NUL cases the previous shell-only form got wrong.
#
# The four selector sites:
#   1. tools/release-dry-run.sh              (git show HEAD:SKILL.md | skill-version.py)
#   2. .github/workflows/release-skill.yml   (skill-version.py SKILL.md working tree,
#                                             and main via git show FETCH_HEAD | skill-version.py)
#   3. tools/check-portable-text-sync.sh     (version_of helper: skill-version.py "$1")
#
# This test exercises the REAL logic of each site, not a hand-copied stand-in:
#   A. version_of is EXTRACTED from check-portable-text-sync.sh and run.
#   B. The selector block of each other site is EXTRACTED from its real source
#      and run in that site's real producer environment (a throwaway git repo for
#      the git-show reads; a throwaway working tree for the file reads), with the
#      shared extractor copied in so the real relative call resolves.
#   C. Every fixture's expected value is computed by a Python oracle that applies
#      the gates' own universal-newline read and VERSION_LINE / SKILL_VERSION
#      regexes, so the sites are pinned to the gates' rule, not to hardcoded
#      numbers.
#   D. Exit status is captured EXPLICITLY and asserted, so a crash (an injected
#      SIGPIPE 141, say) that leaves empty output can never be mistaken for a
#      legitimate reject: an accept must exit 0, a reject must exit non-zero and
#      NOT 141. Each selector runs on its own line and its status is captured
#      into a variable with NO later command able to overwrite it, so a branch
#      that crashes with 141 is caught, not masked by a trailing print.
#      version_of has its own contract, exit 0 ALWAYS with empty output on
#      failure (callers rely on it under set -e), so it is asserted to exit 0 on
#      every fixture, accept or reject, with the version on accept and empty on
#      reject.
#   E. A structural guard asserts the OLD loose sed selector is gone (fixed-string
#      match, so it genuinely detects the loose selector still on main), the old
#      hand-rolled first-line sed is gone, and each site calls skill-version.py
#      the expected number of times.
#
# Fixtures include a LARGE (>64KB) valid file (each site must return the version
# AND exit 0: the SIGPIPE regression test), CRLF and lone-CR cases, malformed
# first lines (rejected), and the two NUL cases: a NUL before the word on the
# first line (the gate and now the sites select the later clean line), and a NUL
# inside the first version line (rejected by the gate and now by the sites too).
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
# has reverted to a form the extraction below cannot parse (as main has). The
# loose selector body is matched as a FIXED string, so it genuinely detects the
# loose selector present on main.
loose_body='s/^Version:[[:space:]]*\([0-9][0-9.]*\).*/\1/p'
declare -A skillver_count=(
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
  # The old hand-rolled first-line sed selector must be gone; the shared
  # extractor owns the reading now.
  if grep -Fq '{p;q}' "${site}"; then
    fail "structural: hand-rolled first-line sed selector still present in ${site}"
  else
    pass "structural: no hand-rolled first-line sed selector in ${site}"
  fi
  # Each site must call the shared extractor, the expected number of times.
  got="$(grep -Fc 'python3 tools/skill-version.py' "${site}" || true)"
  assert_eq "structural: skill-version.py call count in ${site}" "${skillver_count[$site]}" "${got}"
done

# --- The gates' own rule, as a Python oracle ---------------------------------
# Reads the file with universal newlines (newline=None), exactly as Path.read_text
# does in check-release-links.py / check-release-checksum-live.py, then applies the
# gates' VERSION_LINE and SKILL_VERSION patterns verbatim. Prints the version, or
# empty for a reject. This is what every site (via skill-version.py) must agree with.
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
# A brace counter copes with both the single-line and multi-line function forms,
# so the same test goes red against either the pre-change or the post-change
# source it reads.
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
  'if ! version="$(git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 tools/skill-version.py)"' 'fi')"
WF_LOCAL_BLOCK="$(extract_block .github/workflows/release-skill.yml \
  'if ! version="$(python3 tools/skill-version.py cleanlanguage/skills/cleanlanguage/SKILL.md)"' 'fi')"
WF_MAIN_BLOCK="$(extract_block .github/workflows/release-skill.yml \
  'if ! main_version="$(git show FETCH_HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 tools/skill-version.py)"' 'fi')"
for name in DRY_BLOCK WF_LOCAL_BLOCK WF_MAIN_BLOCK; do
  [ -n "${!name}" ] || { echo "Could not extract ${name} from its source" >&2; exit 1; }
done

git_id=(-c user.email=t@t -c user.name=t -c commit.gpgsign=false)

# --- Runners: each drives one real site against a fixture file ----------------
# Every runner prints the selected version to stdout (empty on reject) and exits
# non-zero on reject, so the caller can assert both value and status. The shared
# extractor is copied into each throwaway tree so the site's real relative call
# (python3 tools/skill-version.py) resolves after the cd.

# Site 3: version_of, reading the fixture file directly.
run_version_of() { version_of "$1"; }

# Site 1: release-dry-run.sh, reading git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md.
run_dry() { # fixture-file
  local repo out rc
  repo="$(mktemp -d)"
  mkdir -p "${repo}/cleanlanguage/skills/cleanlanguage" "${repo}/tools"
  cp "$1" "${repo}/cleanlanguage/skills/cleanlanguage/SKILL.md"
  cp tools/skill-version.py "${repo}/tools/skill-version.py"
  git init -q "${repo}"
  git -C "${repo}" "${git_id[@]}" add cleanlanguage/skills/cleanlanguage/SKILL.md
  git -C "${repo}" "${git_id[@]}" commit -qm fixture >/dev/null
  # Stub fail() to exit, matching release-dry-run.sh's own fail (which exits): a
  # reject aborts the subshell, so a malformed line yields empty and non-zero.
  # The selector runs on its own line and its status is captured into a variable
  # BEFORE the version is printed; the subshell then re-exits with that captured
  # status, so a branch that ends non-zero (an injected 141, say) cannot be
  # masked by the trailing print. errexit is off inside so the capture always
  # runs; pipefail stays on so a real SIGPIPE in the git-show pipe surfaces.
  out="$(
    cd "${repo}" || exit 1
    set -uo pipefail
    exec 2>/dev/null
    fail() { exit 1; }
    eval "${DRY_BLOCK}"
    status=$?
    printf '%s' "${version}"
    exit "${status}"
  )" && rc=0 || rc=$?
  rm -rf "${repo}"
  printf '%s' "${out}"
  return "${rc}"
}

# Site 2a: release-skill.yml working-tree read (skill-version.py SKILL.md).
run_wf_local() { # fixture-file
  local dir out rc
  dir="$(mktemp -d)"
  mkdir -p "${dir}/cleanlanguage/skills/cleanlanguage" "${dir}/tools"
  cp "$1" "${dir}/cleanlanguage/skills/cleanlanguage/SKILL.md"
  cp tools/skill-version.py "${dir}/tools/skill-version.py"
  # Capture the selector's own exit status explicitly, then print the version
  # and re-exit with that status, so no trailing command can overwrite it.
  out="$(
    cd "${dir}" || exit 1
    set -uo pipefail
    exec 2>/dev/null
    eval "${WF_LOCAL_BLOCK}"
    status=$?
    printf '%s' "${version}"
    exit "${status}"
  )" && rc=0 || rc=$?
  rm -rf "${dir}"
  printf '%s' "${out}"
  return "${rc}"
}

# Site 2b: release-skill.yml main read (git show FETCH_HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md).
run_wf_main() { # fixture-file
  local remote local_repo out rc
  remote="$(mktemp -d)"
  mkdir -p "${remote}/cleanlanguage/skills/cleanlanguage"
  cp "$1" "${remote}/cleanlanguage/skills/cleanlanguage/SKILL.md"
  git init -q "${remote}"
  git -C "${remote}" "${git_id[@]}" add cleanlanguage/skills/cleanlanguage/SKILL.md
  git -C "${remote}" "${git_id[@]}" commit -qm fixture >/dev/null
  local_repo="$(mktemp -d)"
  mkdir -p "${local_repo}/tools"
  cp tools/skill-version.py "${local_repo}/tools/skill-version.py"
  git init -q "${local_repo}"
  git -C "${local_repo}" fetch --quiet "${remote}" HEAD
  # Capture the selector's own exit status explicitly, then print the version
  # and re-exit with that status, so no trailing command can overwrite it.
  out="$(
    cd "${local_repo}" || exit 1
    set -uo pipefail
    exec 2>/dev/null
    eval "${WF_MAIN_BLOCK}"
    status=$?
    printf '%s' "${main_version}"
    exit "${status}"
  )" && rc=0 || rc=$?
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

# check_site: run one site on one fixture; assert value AND exit-status class.
#   want: "0" (accept: exit 0), "reject" (non-zero and NOT 141), or "always0"
#         (version_of: exit 0 on every fixture, its exit-0-always contract).
check_site() { # label site fixture expected want
  local label="$1" site="$2" fixture="$3" expected="$4" want="$5" got rc
  got="$("${RUNNERS[$site]}" "${fixture}")" && rc=0 || rc=$?
  assert_eq "${label}: value" "${expected}" "${got}"
  case "${want}" in
    always0) assert_eq "${label}: exit 0 always (version_of contract)" "0" "${rc}" ;;
    0) assert_eq "${label}: exit 0 (no SIGPIPE)" "0" "${rc}" ;;
    reject)
      if [ "${rc}" -ne 0 ] && [ "${rc}" -ne 141 ]; then
        pass "${label}: reject exit non-zero, not SIGPIPE (rc=${rc})"
      else
        fail "${label}: expected non-zero non-SIGPIPE reject exit, got rc=${rc}"
      fi
      ;;
  esac
}

# --- Fixtures (byte-exact, incl NUL and lone CR) -----------------------------
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

mapfile -t fixture_names < <(python3 - "${tmp}" <<'PY'
import os, sys
d = sys.argv[1]
fx = {
    "lf_valid":               b"Version: 1.0.14\nBody line.\n",
    "lf_trailing_spaces":     b"Version: 1.2.3  \n",
    "lf_trailing_tab":        b"Version: 1.2.3\t\n",
    "crlf":                   b"Version: 1.2.3\r\nBody line.\r\n",
    "crlf_trailing_spaces":   b"Version: 1.2.3  \r\n",
    "lone_cr_hidden_valid":   b"foo\rVersion: 1.0.0\nVersion: 2.0.0\n",
    "lone_cr_malformed_first":b"Version: 9.9.9 draft\rVersion: 1.2.3\n",
    "malformed_first_text":   b"Version: 9.9.9 trailing\nVersion: 1.2.3\n",
    "malformed_draft":        b"Version: draft\nVersion: 1.2.3\n",
    "two_part":               b"Version: 1.2\n",
    "four_part":              b"Version: 1.2.3.4\n",
    "double_dot":             b"Version: 1..2\n",
    "no_version_line":        b"This file has no version line.\n",
    "nul_before_word":        b"Ver\x00sion: 9.9.9\nVersion: 1.2.3",
    "nul_in_version_line":    b"Version: 9.9.9\x00\nVersion: 1.2.3",
    "nul_outside":            b"Version: 1.2.3\n<!-- \x00 -->\n",
    # Large valid file well over the ~64KB pipe buffer: the SIGPIPE regression.
    "large_valid":            b"Version: 1.0.14\n" + b"x" * 200000 + b"\n",
}
for name, body in fx.items():
    with open(os.path.join(d, name), "wb") as handle:
        handle.write(body)
    print(name)
PY
)
[ "${#fixture_names[@]}" -gt 0 ] || { echo "no fixtures were written" >&2; exit 1; }

# The large fixture must genuinely exceed the ~64KB pipe buffer, or its no-SIGPIPE
# claim proves nothing.
large_bytes="$(wc -c < "${tmp}/large_valid")"
[ "${large_bytes}" -gt 65536 ] || fail "large fixture is only ${large_bytes} bytes, not over the 64KB pipe buffer"

# --- Drive every site against every fixture ----------------------------------
for name in "${fixture_names[@]}"; do
  f="${tmp}/${name}"
  expected="$(gate_expect "${f}")"
  if [ -n "${expected}" ]; then want="0"; else want="reject"; fi
  check_site "version_of: ${name}"      version_of      "${f}" "${expected}" always0
  check_site "release-dry-run: ${name}" release-dry-run "${f}" "${expected}" "${want}"
  check_site "workflow-local: ${name}"  workflow-local  "${f}" "${expected}" "${want}"
  check_site "workflow-main: ${name}"   workflow-main   "${f}" "${expected}" "${want}"
done

# --- No behaviour change on the real SKILL.md --------------------------------
real_expected="$(gate_expect cleanlanguage/skills/cleanlanguage/SKILL.md)"
[ -n "${real_expected}" ] || fail "the gates' rule read no bare X.Y.Z from the real SKILL.md"
check_site "real SKILL.md: version_of"      version_of      cleanlanguage/skills/cleanlanguage/SKILL.md "${real_expected}" always0
check_site "real SKILL.md: release-dry-run" release-dry-run cleanlanguage/skills/cleanlanguage/SKILL.md "${real_expected}" 0
check_site "real SKILL.md: workflow-local"  workflow-local  cleanlanguage/skills/cleanlanguage/SKILL.md "${real_expected}" 0
check_site "real SKILL.md: workflow-main"   workflow-main   cleanlanguage/skills/cleanlanguage/SKILL.md "${real_expected}" 0

echo
if [ "${fails}" -eq 0 ]; then
  echo "All version-selector checks passed."
  exit 0
fi
echo "${fails} version-selector check(s) failed." >&2
exit 1
