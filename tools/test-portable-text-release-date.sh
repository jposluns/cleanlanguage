#!/usr/bin/env bash
#
# Tests the Released-line checks (item 26, G1 and G2) in
# tools/check-portable-text-sync.sh.
#
# G1: the skill must carry a well-formed "Released: YYYY-MM-DD" line directly
# after its Version line when its version sorts above the undated baseline
# (tools/skill-release-date.py --baseline), and may omit it at or below it.
# G2: every portable rendering carries the same Released value as the skill, or
# none when the skill has none. Row 89: the gate reads the extractor only
# through tools/skill-release-date-client.py, so an extractor that passes the
# probe but breaks its --json contract is reported as unavailable, never as a
# malformed line or a rejected version.
#
# Each case runs the CHECKOUT copy of the gate in a throwaway copy of the files
# it reads, so nothing in the repository is changed. Every fixture is built so
# that the generated files and the embed are current (regenerated) and the
# Version agrees everywhere, so a failing case can fail only on the Released
# check it targets; each failure is also pinned by its message. The passing
# cases record the source hash with --update --force inside the copy. Every
# fixture sets its own Version and Released lines explicitly (an undated
# fixture strips them), so the suite gives the same verdicts on an undated
# checkout and on a dated one.
#
# It runs offline.
#
# Usage:
#   tools/test-portable-text-release-date.sh   Run; exit non-zero on any failure.

set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fails=0
pass() { printf 'ok   - %s\n' "$1"; }
fail() { printf 'FAIL - %s\n' "$1" >&2; fails=$((fails + 1)); }

scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT
work="${scratch}/work"
skill="cleanlanguage/skills/cleanlanguage/SKILL.md"
eleven="site/downloads/cleanlanguage-11k.md"
eight="site/downloads/cleanlanguage-8k.md"

fresh() {
  rm -rf "${work}"
  mkdir -p "${work}/tools" "${work}/cleanlanguage/skills" "${work}/site/downloads" "${work}/site/instructions"
  local t
  for t in check-portable-text-sync.sh build-portable-text.py skill-version.py skill-release-date.py skill-release-date-client.py portable-text-skill-source.sha256; do
    cp -p "${repo_root}/tools/${t}" "${work}/tools/${t}"
  done
  cp -R "${repo_root}/cleanlanguage/skills/cleanlanguage" "${work}/cleanlanguage/skills/cleanlanguage"
  cp -p "${repo_root}"/site/downloads/*.md "${work}/site/downloads/"
  cp -p "${repo_root}/site/instructions/index.html" "${work}/site/instructions/index.html"
}

# set_meta FILE KEY VALUE SUFFIX: set the Version number, or insert or replace
# the Released line directly after Version, keeping each line ending.
# KEY "Version" replaces the number; KEY "Released" sets the line after
# Version; KEY "Released-after-Author" places it after the Author line instead;
# KEY "Released-drop" removes it; KEY "GitHub-drop" removes the GitHub line.
set_meta() {
  python3 - "${work}/$1" "$2" "$3" "$4" <<'PYSET'
import re, sys
path, key, value, suffix = sys.argv[1:5]
lines = open(path, encoding="utf-8", newline="").read().split("\n")
vi = next(i for i, l in enumerate(lines) if l.startswith("Version:"))
if key == "Version":
    lines[vi] = re.sub(r"^(Version:[ \t]*)[0-9.]+", lambda m: m.group(1) + value, lines[vi])
elif key == "Released":
    if lines[vi + 1].startswith("Released:"):
        lines[vi + 1] = "Released: " + value + suffix
    else:
        lines.insert(vi + 1, "Released: " + value + suffix)
elif key == "Released-after-Author":
    ai = next(i for i, l in enumerate(lines) if l.startswith("Author:"))
    lines.insert(ai + 1, "Released: " + value + suffix)
elif key == "Released-drop":
    lines = [l for l in lines if not l.startswith("Released:")]
elif key == "GitHub-drop":
    lines = [l for l in lines if not l.startswith("GitHub:")]
else:
    sys.exit("set_meta: unknown key " + key)
open(path, "w", encoding="utf-8", newline="").write("\n".join(lines))
PYSET
}

drop_released_everywhere() {
  set_meta "${skill}" Released-drop "" ""
  set_meta "${eleven}" Released-drop "" ""
  set_meta "${eight}" Released-drop "" ""
}

set_version_everywhere() {
  set_meta "${skill}" Version "$1" ""
  set_meta "${eleven}" Version "$1" ""
  set_meta "${eight}" Version "$1" ""
}

regen() {
  (cd "${work}" && python3 tools/build-portable-text.py --embed >/dev/null)
}

record() {
  (cd "${work}" && tools/check-portable-text-sync.sh --update --force >/dev/null 2>&1)
}

# An undated fixture at version $1: every Released line is stripped, whatever
# the checkout carries, and the generated files are regenerated.
undated_fixture() {
  fresh
  drop_released_everywhere
  set_version_everywhere "$1"
  regen
}

# A dated 1.0.15 fixture in which every file agrees. The 11k file drops its
# GitHub line (the condensed-budget choice for the bump), so it stays within
# its 11000-character label with the new line.
dated_fixture() {
  fresh
  set_version_everywhere 1.0.15
  set_meta "${skill}" Released 2026-11-15 "  "
  regen
  set_meta "${eleven}" GitHub-drop "" ""
  set_meta "${eleven}" Released 2026-11-15 ""
  set_meta "${eight}" Released 2026-11-15 ""
}

gate_out="${scratch}/gate.out"
run_gate() {
  local code=0
  (cd "${work}" && tools/check-portable-text-sync.sh) >"${gate_out}" 2>&1 || code=$?
  return "${code}"
}

expect_pass() { # label
  local code=0
  run_gate || code=$?
  if [ "${code}" -eq 0 ]; then pass "$1"; else
    fail "$1 (expected exit 0, got ${code}: $(cat "${gate_out}"))"
  fi
}

expect_fail() { # label fragment
  local code=0
  run_gate || code=$?
  if [ "${code}" -eq 0 ]; then
    fail "$1 (expected a failure, the gate passed)"
  elif ! grep -Fq -- "$2" "${gate_out}"; then
    fail "$1 (failed, but not with [$2]: $(cat "${gate_out}"))"
  else
    pass "$1"
  fi
}

expect_fail_without() { # label fragment absent-fragment
  local code=0
  run_gate || code=$?
  if [ "${code}" -eq 0 ]; then
    fail "$1 (expected a failure, the gate passed)"
  elif ! grep -Fq -- "$2" "${gate_out}"; then
    fail "$1 (failed, but not with [$2]: $(cat "${gate_out}"))"
  elif grep -Fq -- "$3" "${gate_out}"; then
    fail "$1 (failed, but also with [$3]: $(cat "${gate_out}"))"
  else
    pass "$1"
  fi
}

# break_extractor OP MODE: make the copy of the extractor answer the --json op
# OP in the way MODE names, while every other op still answers and the probe
# passes, and make its CLI content modes exit 1 (row 89).
break_extractor() {
  python3 - "${work}/tools/skill-release-date.py" "$1" "$2" <<"PYBREAK"
import sys
path, op, mode = sys.argv[1:4]
bodies = {
    "exit1": "    raise SystemExit(1)",
    "notjson": "    print(\"not json\")\n    return 0",
    "otherop": "    print(json.dumps({\"op\": \"baseline\", \"outcome\": \"value\", \"value\": \"1.0.14\"}))\n    return 0",
    "badvalue": "    print(json.dumps({\"op\": request[\"op\"], \"outcome\": \"value\", \"value\": \"2026-11-15 \"}))\n    return 0",
    "refused": "    print(json.dumps({\"op\": request[\"op\"], \"outcome\": \"refused\", \"message\": \"x\"}))\n    return 0",
}
hook = (
    "\n_real_json_main = json_main\n"
    "def json_main():\n"
    "    data = sys.stdin.buffer.read()\n"
    "    request = json.loads(data.decode(\"utf-8\"))\n"
    "    if request[\"op\"] != " + repr(op) + ":\n"
    "        sys.stdin = io.TextIOWrapper(io.BytesIO(data), encoding=\"utf-8\")\n"
    "        return _real_json_main()\n"
    + bodies[mode] + "\n"
    "_real_main = main\n"
    "def main(argv):\n"
    "    if argv[1:] in ([\"--baseline\"], [\"--json\"]):\n"
    "        return _real_main(argv)\n"
    "    return 1\n"
)
text = open(path, encoding="utf-8").read()
guard = "\nif __name__ == \"__main__\":\n"
if text.count(guard) != 1:
    sys.exit("main guard not unique in " + path)
open(path, "w", encoding="utf-8").write(text.replace(guard, hook + guard))
PYBREAK
}

# 1. The undated baseline passes.
undated_fixture 1.0.14
if record; then pass "undated 1.0.14 fixture records"; else fail "undated 1.0.14 fixture records"; fi
expect_pass "baseline 1.0.14 without a Released line passes"

# 2. G1: above the baseline, the line is required.
undated_fixture 1.0.15
expect_fail "1.0.15 without a Released line fails" "above the undated baseline 1.0.14"

# 2a. G1 compares versions numerically, by the extractor rule: at or below
#     the baseline an undated skill passes, above it it fails.
for v in 1.0.9 1.00.14; do
  undated_fixture "${v}"
  if record; then pass "undated ${v} fixture records"; else fail "undated ${v} fixture records"; fi
  expect_pass "undated ${v} (not above the baseline) passes"
done
for v in 1.0.100 1.1.0; do
  undated_fixture "${v}"
  expect_fail "undated ${v} (above the baseline) fails" "is version ${v}, above the undated baseline 1.0.14"
done

# 2b. A missing or broken extractor is reported as unavailable, never as a
#     malformed line.
undated_fixture 1.0.14
rm -f "${work}/tools/skill-release-date.py"
expect_fail "a missing extractor is reported as unavailable" "tools/skill-release-date.py is unavailable or broken"
undated_fixture 1.0.14
printf 'def broken(:\n' > "${work}/tools/skill-release-date.py"
expect_fail "a broken extractor is reported as unavailable" "tools/skill-release-date.py is unavailable or broken"

# 2c. An internal error of the extractor (its exit 6, the client exit 16) is
#     reported as the extractor crashing, never as an unreadable file or a
#     malformed line. The copy is made to crash inside extract, after the
#     probe has passed.
undated_fixture 1.0.14
python3 - "${work}/tools/skill-release-date.py" <<"PYCRASH"
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
anchor = "from pathlib import Path\n"
if text.count(anchor) != 1:
    sys.exit("crash anchor not unique in " + path)
hook = "import unicodedata as _crash_mod\ndef _crash(*args, **kwargs):\n    raise RuntimeError(\"injected internal error\")\n_crash_mod.category = _crash\n"
open(path, "w", encoding="utf-8").write(text.replace(anchor, anchor + hook))
PYCRASH
expect_fail "an extractor internal error is reported as a crash" "tools/skill-release-date.py is unavailable or crashed (exit 16)"

# 2d. Row 89: an extractor that passes the probe but breaks its --json
#     contract for one op is reported as unavailable at that call, never as a
#     malformed line or a rejected version.
for mode in exit1 notjson otherop badvalue refused; do
  undated_fixture 1.0.14
  break_extractor extract "${mode}"
  expect_fail_without "a broken extract reply (${mode}) is reported as unavailable" \
    "tools/skill-release-date.py is unavailable or crashed (exit 16) reading ${skill}, so its Released line could not be checked." \
    "Malformed Released"
  undated_fixture 1.0.14
  break_extractor requires_release_date "${mode}"
  expect_fail_without "a broken requires_release_date reply (${mode}) is reported as unavailable" \
    "tools/skill-release-date.py is unavailable or crashed (exit 16) deciding whether 1.0.14 needs a Released line." \
    "rejected the version"
done

# 2e. Row 89: a missing client fails the probe.
undated_fixture 1.0.14
rm -f "${work}/tools/skill-release-date-client.py"
expect_fail "a missing client is reported as unavailable" "tools/skill-release-date.py is unavailable or broken (probe exit 2)"

# 2f. Row 89: every launch in the gate goes through the client. A direct
#     launch of the extractor in any python form (python, python3 or a
#     versioned or pathed interpreter, any options, any path, quoted or not)
#     is counted; the client does not match.
direct_launch='python[0-9.]*([[:space:]]+-[^[:space:]]+)*[[:space:]]+["'"'"']?([^[:space:]]*/)?skill-release-date[.]py([^[:alnum:]_.-]|$)'
direct_launches() { grep -Ec -- "${direct_launch}" "$1"; }
probe="${scratch}/launch-probe.sh"
printf '%s\n' 'python3 -I tools/skill-release-date.py --baseline' 'x="$(python3 tools/skill-release-date.py "$1")"' \
  '/usr/bin/python3.12 -I -B "./tools/skill-release-date.py"' 'python3 -I tools/skill-release-date-client.py baseline' > "${probe}"
if [ "$(direct_launches "${probe}")" = "3" ]; then
  pass "the launch pattern finds each python form and not the client"
else
  fail "the launch pattern finds each python form and not the client"
fi
if [ "$(direct_launches "${repo_root}/tools/check-portable-text-sync.sh")" = "0" ] \
    && [ "$(grep -Fo "python3 -I tools/skill-release-date-client.py" "${repo_root}/tools/check-portable-text-sync.sh" | wc -l)" -eq 5 ]; then
  pass "every extractor launch in the gate goes through the client"
else
  fail "every extractor launch in the gate goes through the client"
fi

# 3. A consistent dated release above the baseline passes.
dated_fixture
if record; then pass "dated 1.0.15 fixture records"; else fail "dated 1.0.15 fixture records"; fi
expect_pass "1.0.15 with the same Released line everywhere passes"

# 4. G2: a rendering with a different date fails.
dated_fixture
set_meta "${eight}" Released 2026-11-16 ""
expect_fail "a rendering with a different date fails" "Released disagreement: SKILL.md=2026-11-15, ${eight}=2026-11-16"

# 5. G2: a rendering missing the date fails.
dated_fixture
set_meta "${eleven}" Released-drop "" ""
expect_fail "a rendering missing the date fails" "Released disagreement: SKILL.md=2026-11-15, ${eleven}=absent"

# 6. G1: an impossible date in the skill fails, whatever the renderings say.
undated_fixture 1.0.15
set_meta "${skill}" Released 2026-02-30 "  "
regen
expect_fail "an impossible date fails" "Malformed Released: line in ${skill}: skill-release-date: not a real calendar date"

# 7. G1: the date on the wrong line fails.
undated_fixture 1.0.15
set_meta "${skill}" Released-after-Author 2026-11-15 "  "
regen
expect_fail "the date on the wrong line fails" "is not the line directly after"

# 8. G2: a malformed line in a rendering fails.
dated_fixture
set_meta "${eleven}" Released soon ""
expect_fail "a malformed rendering line fails" "Malformed Released: line in ${eleven}: skill-release-date: the first Released line is not a bare YYYY-MM-DD date"

# 9. G2 at the baseline: a rendering dated while the skill is not fails.
undated_fixture 1.0.14
set_meta "${eight}" Released 2026-11-15 ""
expect_fail "a dated rendering beside an undated skill fails" "Released disagreement: SKILL.md=absent, ${eight}=2026-11-15"

if [ "${fails}" -ne 0 ]; then
  printf '%d failure(s).\n' "${fails}" >&2
  exit 1
fi
echo "All Released-line sync gate cases passed."
