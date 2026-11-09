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
# that the generated files are current (regenerated) and the Version agrees
# everywhere, so a failing case can fail only on the Released check it targets;
# each failure is also pinned by its message. The passing cases record the
# source hash with --update --force inside the copy, which also regenerates the
# site pages with tools/build-site.py, so the copy carries the generator's
# inputs and a site-src/release.json that names the fixture's version. Every
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
  mkdir -p "${work}/tools" "${work}/cleanlanguage/skills" "${work}/site/downloads" "${work}/.baseline"
  local t
  for t in check-portable-text-sync.sh build-portable-text.py skill-version.py skill-release-date.py skill-release-date-client.py \
      portable-text-skill-source.sha256 build-site.py check-install-page.py sitemap-config.json; do
    cp -p "${repo_root}/tools/${t}" "${work}/tools/${t}"
  done
  cp -R "${repo_root}/cleanlanguage/skills/cleanlanguage" "${work}/cleanlanguage/skills/cleanlanguage"
  cp -p "${repo_root}"/site/downloads/*.md "${work}/site/downloads/"
  cp -R "${repo_root}/site-src" "${work}/site-src"
  cp -p "${repo_root}/.baseline/pin.toml" "${work}/.baseline/pin.toml"
}

# release_matches_skill: set site-src/release.json to the fixture skill's version,
# so tools/build-site.py, which --update runs, accepts the copy.
release_matches_skill() {
  python3 -I - "${work}" <<'PYREL'
import json, subprocess, sys
work = sys.argv[1]
version = subprocess.run([sys.executable, "-I", work + "/tools/skill-version.py", work + "/cleanlanguage/skills/cleanlanguage/SKILL.md"],
                         capture_output=True, text=True, check=True).stdout.strip()
path = work + "/site-src/release.json"
release = json.load(open(path, encoding="utf-8"))
release.update(version=version, tag="v" + version)
open(path, "w", encoding="utf-8").write(json.dumps(release, indent=2) + "\n")
PYREL
}

# set_meta FILE KEY VALUE SUFFIX: set the Version number, or insert or replace
# the Released line directly after Version, keeping each line ending.
# KEY "Version" replaces the number; KEY "Released" sets the line after
# Version; KEY "Released-after-Author" places it after the Author line instead;
# KEY "Released-drop" removes it; KEY "GitHub-drop" removes the GitHub line.
set_meta() {
  python3 -I - "${work}/$1" "$2" "$3" "$4" <<'PYSET'
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
  (cd "${work}" && python3 -I tools/build-portable-text.py >/dev/null)
}

record() {
  release_matches_skill
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
# The options passed to the bash that runs the gate (none by default).
gate_bash=()
run_gate() {
  local code=0
  (cd "${work}" && bash "${gate_bash[@]}" tools/check-portable-text-sync.sh) >"${gate_out}" 2>&1 || code=$?
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

expect_fail_line() { # label line: the gate fails and prints line as a whole line
  local code=0
  run_gate || code=$?
  if [ "${code}" -eq 0 ]; then
    fail "$1 (expected a failure, the gate passed)"
  elif ! grep -Fxq -- "$2" "${gate_out}"; then
    fail "$1 (failed, but no line is exactly [$2]: $(cat "${gate_out}"))"
  else
    pass "$1"
  fi
}

# break_extractor OP MODE: make the copy of the extractor answer the --json op
# OP in the way MODE names, while every other op still answers and the probe
# passes, and make its CLI content modes exit 1 (row 89).
break_extractor() {
  python3 -I - "${work}/tools/skill-release-date.py" "$1" "$2" <<"PYBREAK"
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

# 2a2. G1: client exit 11 at requires-date can rest on any reason the
#      extractor gives, so the gate names the version as malformed and relays
#      the reason the client printed. A part 1 digit longer than the default
#      integer-string limit of 4300 digits is bare X.Y.Z, so only the relayed
#      reason says why it was rejected.
long_version="1.0.$(python3 -I -c 'print("1" * 4301)')"
undated_fixture "${long_version}"
expect_fail_line "an undated version with a 4301-digit part relays the extractor reason" \
  "tools/skill-release-date.py rejected the version ${long_version} as malformed: skill-release-date: a part of the version has more than 4300 digits: '${long_version}'"

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
python3 -I - "${work}/tools/skill-release-date.py" <<"PYCRASH"
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

# 2d2. Row 89: at each call of the gate, the line in which the client names
#      its reason is relayed before the message of the gate.
for op in baseline extract requires_release_date; do
  undated_fixture 1.0.14
  break_extractor "${op}" exit1
  expect_fail "the client reason is relayed at the ${op} call" \
    "skill-release-date-client: skill-release-date.py exited 1 in ${op}, so the extractor is unavailable"
done

# 2d3. Row 89: an exit 0 whose output is not a bare day (which the client
#      never gives) fails as an unexpected answer, never as a Released date.
undated_fixture 1.0.14
mv "${work}/tools/skill-release-date-client.py" "${work}/tools/real-client.py"
cat > "${work}/tools/skill-release-date-client.py" <<'PYCLIENT'
import os, sys
if sys.argv[1:2] == ["extract-file"]:
    print("2026-11-15")
    print("noise")
    raise SystemExit(0)
real = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real-client.py")
os.execv(sys.executable, [sys.executable, "-I", real, *sys.argv[1:]])
PYCLIENT
expect_fail "a value that is not a bare day is not used" \
  "tools/skill-release-date.py gave an unexpected answer (2026-11-15"

# 2g. Row 89: with errexit inherited by command substitutions (shopt -s
#     inherit_errexit, or POSIX mode), the gate gives the same verdicts.
for mode in "-O inherit_errexit" "-o posix"; do
  read -r -a gate_bash <<< "${mode}"
  undated_fixture 1.0.14
  if record; then pass "undated 1.0.14 fixture records (${mode})"; else fail "undated 1.0.14 fixture records (${mode})"; fi
  expect_pass "baseline 1.0.14 without a Released line passes (${mode})"
  undated_fixture 1.0.15
  expect_fail "1.0.15 without a Released line fails (${mode})" "above the undated baseline 1.0.14"
  undated_fixture 1.0.14
  break_extractor extract exit1
  expect_fail_without "a broken extract reply is reported as unavailable (${mode})" \
    "tools/skill-release-date.py is unavailable or crashed (exit 16) reading ${skill}, so its Released line could not be checked." \
    "Malformed Released"
  undated_fixture 1.0.15
  set_meta "${skill}" Released 2026-02-30 "  "
  regen
  expect_fail "an impossible date fails (${mode})" "Malformed Released: line in ${skill}: skill-release-date: not a real calendar date"
done
gate_bash=()

# 2e. Row 89: a missing client fails the probe.
undated_fixture 1.0.14
rm -f "${work}/tools/skill-release-date-client.py"
expect_fail "a missing client is reported as unavailable" "tools/skill-release-date.py is unavailable or broken (probe exit 2)"

# 2f. Row 89: every launch in the gate goes through the client, whose name
#     does not contain the extractor file name. The lines of the gate that
#     name skill-release-date.py are only the messages and the comment listed
#     here, so any other line that names it, a launch in any form among them
#     (any interpreter, quoted or not, any options, a continuation line, or
#     the script run by its shebang), fails. Residual: a launch that builds
#     the name from parts or reads it from a variable is not seen.
allowed_mentions="${scratch}/allowed-mentions.txt"
cat > "${allowed_mentions}" <<'ALLOWED'
# return 1. The one shared strict extractor, tools/skill-release-date.py, does
        echo "tools/skill-release-date.py gave an unexpected answer (${out:-nothing}) for the Released line of $1." >&2
      echo "tools/skill-release-date.py is unavailable or crashed (exit ${rc}) reading $1, so its Released line could not be checked." >&2
    echo "tools/skill-release-date.py is unavailable or broken (probe exit ${prc}), so the Released lines could not be checked." >&2
      11) echo "tools/skill-release-date.py rejected the version ${sv} as malformed: ${requirement}" >&2; return 1 ;;
        echo "tools/skill-release-date.py is unavailable or crashed (exit ${prc}) deciding whether ${sv} needs a Released line." >&2
      echo "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for whether ${sv} needs a Released line." >&2
ALLOWED
mentions_match() { # file: its lines that name the extractor are exactly the allowed ones
  grep -F -- "skill-release-date.py" "$1" | cmp -s - "${allowed_mentions}"
}
# The forms a direct launch could take, each ended by a PROBE-END line; each
# appended to a copy of the gate must fail the check.
launch_probes="${scratch}/launch-probes.txt"
cat > "${launch_probes}" <<'PROBES'
python3 -X utf8 tools/skill-release-date.py --baseline
PROBE-END
python3 -I \
  tools/skill-release-date.py --baseline
PROBE-END
tools/skill-release-date.py --baseline
PROBE-END
"${PYTHON:-python3}" tools/skill-release-date.py --baseline
PROBE-END
"python3" tools/skill-release-date.py --baseline
PROBE-END
PROBES
probe_copy="${scratch}/sync-probe.sh"
probes_seen=0
probes_caught=0
probe_text=""
while IFS= read -r probe_line; do
  if [ "${probe_line}" = "PROBE-END" ]; then
    probes_seen=$((probes_seen + 1))
    { cat "${repo_root}/tools/check-portable-text-sync.sh"; printf '%s' "${probe_text}"; } > "${probe_copy}"
    if ! mentions_match "${probe_copy}"; then probes_caught=$((probes_caught + 1)); fi
    probe_text=""
  else
    probe_text="${probe_text}${probe_line}
"
  fi
done < "${launch_probes}"
if [ "${probes_seen}" -eq 5 ] && [ "${probes_caught}" -eq 5 ]; then
  pass "each direct launch form fails the launch check (${probes_caught} of ${probes_seen})"
else
  fail "each direct launch form fails the launch check (${probes_caught} of ${probes_seen} caught, 5 expected)"
fi
# The client file name, checked the same way: the lines of the gate that
# name skill-release-date-client.py are only the comment and the launches
# listed here, each exactly "python3 -I tools/skill-release-date-client.py"
# and its arguments, so any other line that names it fails, one more launch
# in the listed form among them.
allowed_client="${scratch}/allowed-client.txt"
cat > "${allowed_client}" <<'ALLOWEDCLIENT'
# the reading, run in its --json mode by tools/skill-release-date-client.py
  out="$(python3 -I tools/skill-release-date-client.py extract-file "$1" 2>&1)" || rc=$?
      echo "Malformed Released: line in $1: $(python3 -I tools/skill-release-date-client.py extract-file "$1" 2>&1 >/dev/null || true)" >&2
      echo "Could not read $1 for its Released line: $(python3 -I tools/skill-release-date-client.py extract-file "$1" 2>&1 >/dev/null || true)" >&2
  baseline="$(python3 -I tools/skill-release-date-client.py baseline 2>&1)" || prc=$?
    requirement="$(python3 -I tools/skill-release-date-client.py requires-date "${sv}" 2>&1)" || prc=$?
ALLOWEDCLIENT
client_mentions_match() { # file: its lines that name the client are exactly the allowed ones
  grep -F -- "skill-release-date-client.py" "$1" | cmp -s - "${allowed_client}"
}
client_probes="${scratch}/client-probes.txt"
cat > "${client_probes}" <<'CLIENTPROBES'
python3 tools/skill-release-date-client.py baseline
PROBE-END
"python3" -I tools/skill-release-date-client.py baseline
PROBE-END
python3 -X utf8 tools/skill-release-date-client.py baseline
PROBE-END
python3 -I \
  tools/skill-release-date-client.py baseline
PROBE-END
tools/skill-release-date-client.py baseline
PROBE-END
"${PYTHON:-python3}" -I tools/skill-release-date-client.py baseline
PROBE-END
python3 -I tools/skill-release-date-client.py baseline
PROBE-END
CLIENTPROBES
probes_seen=0
probes_caught=0
probe_text=""
while IFS= read -r probe_line; do
  if [ "${probe_line}" = "PROBE-END" ]; then
    probes_seen=$((probes_seen + 1))
    { cat "${repo_root}/tools/check-portable-text-sync.sh"; printf '%s' "${probe_text}"; } > "${probe_copy}"
    if ! client_mentions_match "${probe_copy}"; then probes_caught=$((probes_caught + 1)); fi
    probe_text=""
  else
    probe_text="${probe_text}${probe_line}
"
  fi
done < "${client_probes}"
if [ "${probes_seen}" -eq 7 ] && [ "${probes_caught}" -eq 7 ]; then
  pass "each other client launch form fails the client check (${probes_caught} of ${probes_seen})"
else
  fail "each other client launch form fails the client check (${probes_caught} of ${probes_seen} caught, 7 expected)"
fi
if mentions_match "${repo_root}/tools/check-portable-text-sync.sh" \
    && client_mentions_match "${repo_root}/tools/check-portable-text-sync.sh" \
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
