#!/usr/bin/env bash
#
# Offline tests for the github-actions fail-safe in ci-status (TODO 19). The
# verdict logic lives in tools/ci-status.py (a Python rewrite that parses the
# check-runs JSON structurally and fail-closed); tools/ci-status.sh is a thin
# wrapper that execs it, so these tests drive the wrapper exactly as callers do.
#
# The gate reports a pass only after two identical readings. This repository runs
# an Actions workflow on every PR and every push to main (plugin-validate,
# sitemap), so a passing commit with no github-actions check means Actions produced
# nothing (a malformed-branch false green) and is downgraded to pending, never a
# red. Presence is read from the same reading as the verdict (the app slug), and
# the reading is FAIL-CLOSED: a malformed page (non-object, or check_runs that is
# not a list), a check that is not an object, or any field of the wrong type (a
# status that is not a non-empty string, a conclusion/name/slug that is neither a
# string nor null) makes the whole reading unreadable rather than dropping or
# forging a check. Control characters in a name are inert string data, so they
# cannot fabricate presence; only the slug decides it. A failed read breaks a
# confirmation in progress but the same green set reappearing re-arms without
# consuming the changing-set budget. Waits are deadline-capped; numeric arguments
# are base-10 and range-checked.
#
# Each case puts a fake gh on PATH serving check-runs from a per-call "plan"
# (tokens g/a/f: default payload, alternate payload, or a failed call). ci-status
# runs and its exit code (and, for two cases, elapsed time or --paginate handling)
# is asserted.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ci="${here}/ci-status.sh"
fails=0
skips=0  # a skipped case is reported on a skip line and never counted as ok

GA_PRESENT='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}
]}'
GA_REVERSED='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}},
  {"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}}
]}'
CLOUDFLARE_ONLY='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}
]}'
GA_IN_PROGRESS='{"check_runs":[
  {"status":"in_progress","conclusion":null,"name":"check","app":{"slug":"github-actions"}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}
]}'
EMPTY_CONCLUSION='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}},
  {"status":"completed","conclusion":null,"name":"success","app":{"slug":"external-app"}}
]}'
INJECT_US='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"x\u001fgithub-actions","app":{"slug":null}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}
]}'
INJECT_NL_US='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"benign\ncompleted\u001fsuccess\u001fforged\u001fgithub-actions","app":{"slug":null}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}
]}'
MULTIPAGE_GA_P2='{"check_runs":[{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}]}
{"check_runs":[{"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}}]}'
# A page whose check_runs is null (malformed) followed by a green page: the whole
# reading must be rejected, not confirmed from the good page alone.
MALFORMED_PAGE='{"check_runs":null}
{"check_runs":[{"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}}]}'
# A green github-actions check beside a completed check whose status is null
# (malformed). The malformed record must not be silently dropped.
NULL_STATUS='{"check_runs":[{"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}},{"status":null,"conclusion":"failure","name":"malformed","app":{"slug":"external"}}]}'
# A check whose name is a JSON number, not a string (hostile/malformed).
NONSTRING_NAME='{"check_runs":[{"status":"completed","conclusion":"failure","name":7,"app":{"slug":"hostile"}}]}
{"check_runs":[{"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}}]}'
# A completed check with an EMPTY-STRING status beside a green github-actions
# check: a required field that is present but empty is malformed -> fail-closed.
EMPTY_STATUS='{"check_runs":[{"status":"completed","conclusion":"success","name":"good","app":{"slug":"github-actions"}},{"status":"","conclusion":"failure","name":"bad","app":{"slug":"external"}}]}'
# A check field that is a JSON boolean (false) beside a green github-actions check:
# a bool is not a string, so the reading is rejected (a naive x-or-empty would hide it).
FALSE_FIELD='{"check_runs":[{"status":"completed","conclusion":"success","name":"good","app":{"slug":"github-actions"}},{"status":"completed","conclusion":"success","name":false,"app":{"slug":"external"}}]}'
# check_runs is a JSON OBJECT, not an array (malformed container).
NONARRAY='{"check_runs":{"only":{"status":"completed","conclusion":"success","name":"good","app":{"slug":"github-actions"}}}}'

# run_case NAME DEFAULT ALT PLAN WANT [EXTRA ci-status ARGS...]
run_case() {
  local name="$1" def="$2" alt="$3" plan="$4" want="$5"; shift 5
  local tmp; tmp="$(mktemp -d)"
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf '%s' "$def" > "$tmp/def.json"
  printf '%s' "$alt" > "$tmp/alt.json"
  printf '%s' "$plan" > "$tmp/plan"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*)
    n_file="$tmp/n"
    n=\$(( \$(cat "\$n_file" 2>/dev/null || echo 0) + 1 ))
    printf '%s' "\$n" > "\$n_file"
    read -r -a toks < "$tmp/plan"
    tok="g"
    if [ "\${#toks[@]}" -gt 0 ]; then
      idx=\$(( n - 1 ))
      [ "\$idx" -ge "\${#toks[@]}" ] && idx=\$(( \${#toks[@]} - 1 ))
      tok="\${toks[\$idx]}"
    fi
    case "\$tok" in
      f) printf 'simulated check-runs read failure\n' >&2; exit 1 ;;
      a) cat "$tmp/alt.json" ;;
      *) cat "$tmp/def.json" ;;
    esac
    ;;
  *"repo view"*) printf 'owner/name' ;;
  *) printf '' ;;
esac
GH
  chmod +x "$bin/gh"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 \
    --repo owner/name --interval 1 "$@" >/dev/null 2>&1
  local got=$?
  if [ "$got" -eq "$want" ]; then
    printf 'ok   %s (exit %s)\n' "$name" "$got"
  else
    printf 'FAIL %s (got %s, want %s)\n' "$name" "$got" "$want"; fails=$((fails + 1))
  fi
  rm -rf "$tmp"
}

# run_timed_case NAME PAYLOAD MAX_SECONDS WANT EXTRA...
run_timed_case() {
  local name="$1" payload="$2" maxs="$3" want="$4"; shift 4
  local tmp; tmp="$(mktemp -d)"
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf '%s' "$payload" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*) cat "$tmp/def.json" ;;
  *"repo view"*) printf 'owner/name' ;;
  *) printf '' ;;
esac
GH
  chmod +x "$bin/gh"
  local start end elapsed got
  start="$(date +%s)"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 --repo owner/name "$@" >/dev/null 2>&1
  got=$?; end="$(date +%s)"; elapsed=$(( end - start ))
  if [ "$got" -eq "$want" ] && [ "$elapsed" -le "$maxs" ]; then
    printf 'ok   %s (exit %s, %ss <= %ss)\n' "$name" "$got" "$elapsed" "$maxs"
  else
    printf 'FAIL %s (got exit %s in %ss; want exit %s within %ss)\n' "$name" "$got" "$elapsed" "$want" "$maxs"; fails=$((fails + 1))
  fi
  rm -rf "$tmp"
}

# run_paginate_case NAME PAGE1 PAGE2 WANT
# The fake emits PAGE1 always, and PAGE2 ONLY when --paginate is passed. So a tool
# that drops --paginate sees only PAGE1. Used to pin that read_checks paginates.
run_paginate_case() {
  local name="$1" p1="$2" p2="$3" want="$4"
  local tmp; tmp="$(mktemp -d)"
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf '%s' "$p1" > "$tmp/p1.json"
  printf '%s' "$p2" > "$tmp/p2.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
args="\$*"
case "\$args" in
  *check-runs*)
    cat "$tmp/p1.json"
    case "\$args" in *--paginate*) printf '\n'; cat "$tmp/p2.json" ;; esac
    ;;
  *"repo view"*) printf 'owner/name' ;;
  *) printf '' ;;
esac
GH
  chmod +x "$bin/gh"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 --repo owner/name --interval 1 >/dev/null 2>&1
  local got=$?
  if [ "$got" -eq "$want" ]; then
    printf 'ok   %s (exit %s)\n' "$name" "$got"
  else
    printf 'FAIL %s (got %s, want %s)\n' "$name" "$got" "$want"; fails=$((fails + 1))
  fi
  rm -rf "$tmp"
}

# run_deep_case NAME WANT: a deeply nested JSON payload makes the parser recurse;
# the RecursionError must be caught and fail closed, not escape as a crash.
run_deep_case() {
  local name="$1" want="$2"
  local tmp; tmp="$(mktemp -d)"; local bin="$tmp/bin"; mkdir -p "$bin"
  python3 -c "open('$tmp/cr.json','w').write('['*100000 + ']'*100000)"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in *check-runs*) cat "$tmp/cr.json";; *"repo view"*) printf 'owner/name';; *) printf '';; esac
GH
  chmod +x "$bin/gh"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 --repo owner/name >/dev/null 2>&1
  local got=$?
  if [ "$got" -eq "$want" ]; then printf 'ok   %s (exit %s)\n' "$name" "$got";
  else printf 'FAIL %s (got %s, want %s)\n' "$name" "$got" "$want"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

# run_bytes_case NAME WANT: fake gh emits a non-UTF-8 byte; must fail closed.
run_bytes_case() {
  local name="$1" want="$2"
  local tmp; tmp="$(mktemp -d)"; local bin="$tmp/bin"; mkdir -p "$bin"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in *check-runs*) printf '\377garbage';; *"repo view"*) printf 'owner/name';; *) printf '';; esac
GH
  chmod +x "$bin/gh"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 --repo owner/name >/dev/null 2>&1
  local got=$?
  if [ "$got" -eq "$want" ]; then printf 'ok   %s (exit %s)\n' "$name" "$got";
  else printf 'FAIL %s (got %s, want %s)\n' "$name" "$got" "$want"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

# run_slow_case NAME WANT: fake gh sleeps past the wait deadline; the read must be
# bounded so it does not overshoot -> fail closed within the window.
run_slow_case() {
  local name="$1" want="$2"
  local tmp; tmp="$(mktemp -d)"; local bin="$tmp/bin"; mkdir -p "$bin"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*) sleep 5; printf '{"total_count":1,"check_runs":[{"status":"in_progress","conclusion":null,"name":"c","app":{"slug":"github-actions"}}]}';;
  *"repo view"*) printf 'owner/name';; *) printf '';;
esac
GH
  chmod +x "$bin/gh"
  local start end elapsed; start="$(date +%s)"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 --repo owner/name --wait --timeout 2 --interval 1 >/dev/null 2>&1
  local got=$?; end="$(date +%s)"; elapsed=$(( end - start ))
  if [ "$got" -eq "$want" ] && [ "$elapsed" -le 4 ]; then printf 'ok   %s (exit %s, %ss)\n' "$name" "$got" "$elapsed";
  else printf 'FAIL %s (got exit %s in %ss, want %s within 4s)\n' "$name" "$got" "$elapsed" "$want"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

# run_rc_case NAME WANT: fake gh emits a GREEN body but exits nonzero; the
# returncode guard must reject it (exit 3), not parse the body as green.
run_rc_case() {
  local name="$1" want="$2"
  local tmp; tmp="$(mktemp -d)"; local bin="$tmp/bin"; mkdir -p "$bin"
  printf '%s' "$GA_PRESENT" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in *check-runs*) cat "$tmp/def.json"; exit 1;; *"repo view"*) printf 'owner/name';; *) printf '';; esac
GH
  chmod +x "$bin/gh"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 --repo owner/name >/dev/null 2>&1
  local got=$?
  if [ "$got" -eq "$want" ]; then printf 'ok   %s (exit %s)\n' "$name" "$got";
  else printf 'FAIL %s (got %s, want %s)\n' "$name" "$got" "$want"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}


run_case "github-actions check present -> green" "$GA_PRESENT" "" "" 0
run_case "only external check, no github-actions -> not green" "$CLOUDFLARE_ONLY" "" "" 2
run_case "unfinished github-actions check -> not green" "$GA_IN_PROGRESS" "" "" 2
run_case "unreadable check-runs read -> not green" "$GA_PRESENT" "" "f" 3
run_case "failed read between green reads does not confirm" "$GA_PRESENT" "" "g f g f" 3 --wait --timeout 8
run_case "transient read failures on a stable set still confirm green" "$GA_PRESENT" "" "g f g f g f g f g f g g" 0 --wait --timeout 30
run_case "reordered identical check set still confirms green" "$GA_PRESENT" "$GA_REVERSED" "g a g a g a" 0
# A completed check with no conclusion must stay non-green; the unit separator
# preserves the empty conclusion field rather than collapsing it into the name.
run_case "completed check with null conclusion is not green" "$EMPTY_CONCLUSION" "" "" 1
# Control characters in a name are stripped before serialization, so US bytes in a
# name cannot forge a github-actions slug: not green.
run_case "text in a name cannot fabricate github-actions presence" "$INJECT_US" "" "" 2
# A newline plus separators in a name cannot forge a github-actions record on a new
# line: control characters are stripped, so it stays one field: not green.
run_case "newline and text in a name cannot fabricate presence" "$INJECT_NL_US" "" "" 2
# The sole github-actions check is on page 2 of a paginated payload; read_checks
# parses every page of the concatenated stream, so it is seen: green.
run_case "github-actions only on page 2 of a paginated payload -> green" "$MULTIPAGE_GA_P2" "" "" 0
# read_checks must request --paginate: the fake emits page 2 (the sole
# github-actions check) only when --paginate is passed, so a tool that drops it
# would miss it and not be green.
run_paginate_case "read_checks paginates to see a page-2 github-actions check -> green" "$CLOUDFLARE_ONLY" '{"check_runs":[{"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}}]}' 0
# Duplicate check_runs members: JSON keeps the last, so a naive parser would hide
# the failing run. Must be rejected as ambiguous.
DUP_KEY='{"check_runs":[{"status":"completed","conclusion":"failure","name":"required","app":{"slug":"external"}}],"check_runs":[{"status":"completed","conclusion":"success","name":"ga","app":{"slug":"github-actions"}}]}'
# A page declaring total_count 2 but delivering one run (truncation): the missing
# run could be failing, so the reading must be rejected.
TRUNCATED='{"total_count":2,"check_runs":[{"status":"completed","conclusion":"success","name":"ga","app":{"slug":"github-actions"}}]}'
# github-actions present but the required Cloudflare Pages check ABSENT: not green
# until the required check registers.
MISSING_CLOUDFLARE='{"total_count":1,"check_runs":[{"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}}]}'
# A duplicate check-run id pads the list to match total_count while hiding a run.
DUP_ID='{"total_count":3,"check_runs":[{"id":1,"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}},{"id":2,"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}},{"id":2,"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}]}'
# total_count present as an explicit null is malformed.
TOTAL_NULL='{"total_count":null,"check_runs":[{"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}},{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}]}'
# total_count present on one page but not the other is inconsistent.
INCONSISTENT_TOTAL='{"check_runs":[{"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}}]}
{"total_count":2,"check_runs":[{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}}]}'
# A check whose app field is not an object ([]) must not coerce to a null slug.
NONOBJ_APP='{"total_count":2,"check_runs":[{"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}},{"status":"completed","conclusion":"success","name":"cf","app":[]}]}'
# A lone surrogate in a name is unencodable and must fail closed, not crash report.
SURROGATE='{"total_count":1,"check_runs":[{"status":"completed","conclusion":"success","name":"\ud800","app":{"slug":"github-actions"}}]}'
# A green reading with an EXTRA passing check: a different set than GA_PRESENT
# (both carry the required checks), used to exercise a changing-but-green set.
GA_PLUS_EXTRA='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages"}},
  {"status":"completed","conclusion":"success","name":"extra","app":{"slug":"github-actions"}}
]}'
# The REAL Cloudflare app slug on this repository is cloudflare-workers-and-pages,
# not cloudflare-pages; the required-check match is by the "cloudflare" prefix.
REAL_CLOUDFLARE='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages"}}
]}'
# A digit-only timeout with a leading zero (08) is base-10, not octal: it does not
# error, and a green commit still confirms green.
run_case "leading-zero timeout is base 10, not octal -> green" "$GA_PRESENT" "" "" 0 --wait --timeout 08

# A malformed page (null check_runs) cannot be masked by a later good page: the
# slurped read fails closed -> not green (exit 3).
run_case "malformed page is not masked by a later good page" "$MALFORMED_PAGE" "" "" 3
# A check with a null status is not silently dropped: the reading fails closed.
run_case "null-status malformed check is not dropped" "$NULL_STATUS" "" "" 3
# A non-string (numeric) check name is rejected fail-closed, not coerced.
run_case "non-string check name is rejected fail-closed" "$NONSTRING_NAME" "" "" 3
# An out-of-range (overflow) timeout is rejected as a usage error, never wrapped
# into unrelated timeout semantics.
run_case "overflow timeout is rejected as usage error" "$GA_PRESENT" "" "" 3 --wait --timeout 9223372036854775808
# An empty-string status is a malformed required field -> fail-closed (exit 3),
# never silently dropped.
run_case "empty-string status is rejected fail-closed" "$EMPTY_STATUS" "" "" 3
# A boolean check field is not a string -> fail-closed, not coerced to empty.
run_case "boolean check field is rejected fail-closed" "$FALSE_FIELD" "" "" 3
# A non-array check_runs container is malformed -> fail-closed.
run_case "non-array check_runs is rejected fail-closed" "$NONARRAY" "" "" 3
# A deeply nested payload triggers a parser RecursionError; it must be caught and
# reported as unreadable (exit 3), never escape as a crash/exit 1.
run_deep_case "deeply nested payload is rejected fail-closed" 3
# Duplicate JSON members must not hide a check -> fail-closed.
run_case "duplicate JSON keys are rejected fail-closed" "$DUP_KEY" "" "" 3
# A declared total_count that exceeds the runs received is a truncated reading.
run_case "declared total_count truncation is rejected fail-closed" "$TRUNCATED" "" "" 3
# A non-ASCII digit passes str.isdigit() but int() would raise: reject as usage.
run_case "non-ASCII digit timeout is rejected as usage" "$GA_PRESENT" "" "" 3 --timeout ²
# Non-UTF-8 transport output is unreadable, not a failed check.
run_bytes_case "non-UTF-8 output is rejected fail-closed" 3
# A gh read that would exceed the wait deadline is bounded and fails closed.
run_slow_case "gh read exceeding the wait deadline is not green" 3
# The required Cloudflare Pages check absent -> not green even with a green
# github-actions check (a partial reading is not confirmed).
run_case "required Cloudflare check absent -> not green" "$MISSING_CLOUDFLARE" "" "" 2
# A duplicate check-run id must not pad the count to hide a run.
run_case "duplicate check-run id is rejected fail-closed" "$DUP_ID" "" "" 3
# total_count as an explicit null is malformed.
run_case "null total_count is rejected fail-closed" "$TOTAL_NULL" "" "" 3
# total_count present on only one page is inconsistent.
run_case "inconsistent total_count presence is rejected fail-closed" "$INCONSISTENT_TOTAL" "" "" 3
# A non-object app must not coerce to a null slug.
run_case "non-object app is rejected fail-closed" "$NONOBJ_APP" "" "" 3
# A lone surrogate in a name fails closed, it does not crash the report.
run_case "unencodable name is rejected fail-closed" "$SURROGATE" "" "" 3
# A nonzero gh exit with a green body on stdout is rejected by the returncode guard.
run_rc_case "green body with nonzero gh exit is rejected fail-closed" 3
# In --wait mode a changing-but-green set must NOT give up at the changing-set cap
# while time remains; it keeps going and confirms once the set settles.
run_case "wait does not give up early on a changing green set" "$GA_PRESENT" "$GA_PLUS_EXTRA" "g a g a g a g g" 0 --wait --timeout 30
# A zero-length wait window fails closed rather than overrunning the deadline.
run_case "zero-timeout wait window fails closed" "$GA_IN_PROGRESS" "" "" 3 --wait --timeout 0
# The real Cloudflare app slug (cloudflare-workers-and-pages) satisfies the required
# Cloudflare check via the prefix match -> green (regression: an exact cloudflare-pages
# match would false-red every real commit).
run_case "real cloudflare-workers-and-pages slug satisfies the required check" "$REAL_CLOUDFLARE" "" "" 0
run_timed_case "wait stops near the deadline, not a whole interval past it" "$GA_IN_PROGRESS" 4 2 --wait --timeout 2 --interval 5

# Commit sha and repository contract (backlog row 86). The tool accepts only a
# full 40-character hexadecimal sha and makes no local git call, so no case needs
# a git repository. Each case copies ci-status.sh and ci-status.py into a
# throwaway tools directory, runs the copy from /, and serves a green reading
# from a fake gh that logs the arguments, environment and working directory of
# every call, and snapshots the tool output at its first call. The fake gh repo
# view answers with GH_REPO when that variable reaches it, else with the VIEW
# value (FAIL makes it exit 1), so a leaked GH_REPO changes the path read.
C1=0c83f120fcc4630694465bcf89f7415a21d54dba
C1_UPPER=0C83F120FCC4630694465BCF89F7415A21D54DBA
C2=1111111111111111111111111111111111111111
NL="$(printf "\n.")"; NL="${NL%.}"

# run_contract_case NAME WANT EXPECT REPO VIEW ENVSPEC CHECKS [ci-status ARGS...]
# EXPECT is the full sha every check-runs call must use, "noapi" when no
# check-runs call may be made, or "nogh" when no gh call at all may be made.
# REPO is the owner/name the check-runs path must name. VIEW is what the fake gh
# repo view prints. ENVSPEC is "-" or space-separated NAME=VALUE assignments; the
# token SHADOW stands for a PYTHONPATH entry whose json.py exits 7. CHECKS is "-"
# or space-separated words: env (no gh call saw GH_REPO, GH_HOST or a GIT_
# variable), pwd (every gh call ran in the real tools directory), first (the sha
# line was already printed at the first gh call), hint (stderr tells the caller
# to pass the full 40-character sha), link (run ci-status.py through a symlink
# in another directory instead of through ci-status.sh), wraplink (run
# ci-status.sh through a symlink named ci-status.sh in another directory that
# holds no ci-status.py, so only a wrapper that resolves the link finds the gate),
# dup (stderr refuses a repeated --repo, --timeout or --interval).
run_contract_case() {
  local name="$1" want="$2" expect="$3" repo_want="$4" view="$5" envspec="$6" checks="$7"; shift 7
  local tmp; tmp="$(mktemp -d)"
  local tools="$tmp/repo/tools" bin="$tmp/bin"; mkdir -p "$tools" "$bin" "$tmp/shadow"
  cp "${here}/ci-status.sh" "${here}/ci-status.py" "$tools/"
  printf "raise SystemExit(7)\n" > "$tmp/shadow/json.py"
  printf "%s" "$GA_PRESENT" > "$tmp/def.json"
  printf "%s" "$view" > "$tmp/view"
  : > "$tmp/calls"; : > "$tmp/envlog"; : > "$tmp/pwds"; : > "$tmp/out"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
[ -e "$tmp/seen" ] || cp "$tmp/out" "$tmp/seen"
printf "%s\n" "\$*" >> "$tmp/calls"
env >> "$tmp/envlog"
pwd -P >> "$tmp/pwds"
case "\$*" in
  *check-runs*) cat "$tmp/def.json" ;;
  *"repo view"*)
    if [ -n "\${GH_REPO:-}" ]; then printf "%s" "\$GH_REPO"; exit 0; fi
    if [ "\$(cat "$tmp/view")" = FAIL ]; then exit 1; fi
    cat "$tmp/view" ;;
  *) printf "" ;;
esac
GH
  chmod +x "$bin/gh"
  local envset=() word
  if [ "$envspec" != "-" ]; then
    for word in $envspec; do
      if [ "$word" = SHADOW ]; then word="PYTHONPATH=$tmp/shadow"; fi
      envset+=("$word")
    done
  fi
  local entry=(bash "$tools/ci-status.sh")
  case " $checks " in
    *" link "*)
      mkdir -p "$tmp/elsewhere"
      ln -s "$tools/ci-status.py" "$tmp/elsewhere/ci-status.py"
      entry=(python3 -I "$tmp/elsewhere/ci-status.py") ;;
    *" wraplink "*)
      mkdir -p "$tmp/elsewhere"
      ln -s "$tools/ci-status.sh" "$tmp/elsewhere/ci-status.sh"
      entry=(bash "$tmp/elsewhere/ci-status.sh") ;;
  esac
  (cd / || exit 99; env "${envset[@]}" PATH="$bin:$PATH" "${entry[@]}" \
    --interval 1 "$@" > "$tmp/out" 2> "$tmp/err")
  local got=$? ok=1 why=""
  if [ "$got" -ne "$want" ]; then ok=0; why="$why exit"; fi
  local runs; runs="$(grep -c check-runs "$tmp/calls")"
  case "$expect" in
    nogh) if [ -s "$tmp/calls" ]; then ok=0; why="$why gh-called"; fi ;;
    noapi) if [ "$runs" -ne 0 ]; then ok=0; why="$why api-called"; fi ;;
    *)
      local good; good="$(grep -c -F "repos/${repo_want}/commits/${expect}/check-runs" "$tmp/calls")"
      if [ "$good" -lt 1 ] || [ "$good" -ne "$runs" ]; then ok=0; why="$why path"; fi
      if ! grep -q -F "reading checks for commit ${expect}" "$tmp/out"; then ok=0; why="$why sha-line"; fi
      ;;
  esac
  local tooldir; tooldir="$(cd "$tools" || exit 99; pwd -P)"
  for word in $checks; do
    case "$word" in
      env)
        if [ ! -s "$tmp/envlog" ] || grep -q -E "^(GH_REPO|GH_HOST|GIT_[A-Za-z0-9_]*)=" "$tmp/envlog"; then
          ok=0; why="$why env"
        fi ;;
      pwd)
        if [ ! -s "$tmp/pwds" ] || grep -q -v -x -F "$tooldir" "$tmp/pwds"; then ok=0; why="$why pwd"; fi ;;
      first)
        if [ ! -e "$tmp/seen" ] || ! grep -q -E "reading checks for commit [0-9a-f]{40}" "$tmp/seen"; then
          ok=0; why="$why not-first"
        fi ;;
      hint)
        if ! grep -q -F "pass the full 40-character sha" "$tmp/err"; then ok=0; why="$why hint"; fi ;;
      dup)
        if ! grep -q -E "more than one --(repo|timeout|interval) given" "$tmp/err"; then
          ok=0; why="$why dup"
        fi ;;
      *) ;;
    esac
  done
  if [ "$ok" -eq 1 ]; then
    printf "ok   %s (exit %s)\n" "$name" "$got"
  else
    printf "FAIL %s (got exit %s, want %s;%s)\n" "$name" "$got" "$want" "$why"
    fails=$((fails + 1))
  fi
  rm -rf "$tmp"
}

# A full sha is accepted as given; upper case is folded to lower case.
run_contract_case "full sha is used as given" 0 "$C1" owner/name owner/name - "env pwd first" "$C1"
run_contract_case "full sha unknown locally is used as given" 0 "$C2" owner/name owner/name - - "$C2"
run_contract_case "upper-case full sha is folded to lower case" 0 "$C1" owner/name owner/name - - "$C1_UPPER"
# Every abbreviation is refused before any gh call, whatever its length.
run_contract_case "4-character abbreviation is refused" 3 nogh owner/name owner/name - hint "${C1:0:4}"
run_contract_case "7-character abbreviation is refused" 3 nogh owner/name owner/name - hint "${C1:0:7}"
run_contract_case "39-character abbreviation is refused" 3 nogh owner/name owner/name - hint "${C1:0:39}"
run_contract_case "abbreviation with --repo is refused" 3 nogh owner/name owner/name - hint --repo owner/name "${C1:0:7}"
# Ref names, revision expressions, path-like, non-hex, empty and over-long values.
run_contract_case "ref name HEAD is refused" 3 nogh owner/name owner/name - hint HEAD
run_contract_case "branch name main is refused" 3 nogh owner/name owner/name - hint main
run_contract_case "revision expression is refused" 3 nogh owner/name owner/name - hint "${C1:0:7}~1"
run_contract_case "peel expression on a full sha is refused" 3 nogh owner/name owner/name - hint "${C1}^{commit}"
run_contract_case "path-like value is refused" 3 nogh owner/name owner/name - hint "${C1:0:7}/../x"
run_contract_case "40-character non-hex value is refused" 3 nogh owner/name owner/name - hint "${C1:0:39}g"
run_contract_case "empty value is refused" 3 nogh owner/name owner/name - hint ""
run_contract_case "41-character value is refused" 3 nogh owner/name owner/name - hint "${C1}0"
run_contract_case "full sha with a trailing newline is refused" 3 nogh owner/name owner/name - hint "${C1}${NL}"
# --repo is accepted only as owner/name with GitHub-safe characters.
run_contract_case "--repo with an injected path is refused" 3 nogh owner/name owner/name - - --repo "owner/name/commits/${C2}/check-runs?x=" "$C1"
run_contract_case "--repo with a query is refused" 3 nogh owner/name owner/name - - --repo "owner/name?x=1" "$C1"
run_contract_case "--repo with a fragment is refused" 3 nogh owner/name owner/name - - --repo "owner/name#x" "$C1"
run_contract_case "--repo with a dot-leading name is refused" 3 nogh owner/name owner/name - - --repo "owner/.." "$C1"
run_contract_case "--repo with a dot owner is refused" 3 nogh owner/name owner/name - - --repo "../name" "$C1"
run_contract_case "--repo without a slash is refused" 3 nogh owner/name owner/name - - --repo owner "$C1"
run_contract_case "--repo with a trailing slash is refused" 3 nogh owner/name owner/name - - --repo "owner/name/" "$C1"
run_contract_case "--repo with a space is refused" 3 nogh owner/name owner/name - - --repo "own er/name" "$C1"
run_contract_case "--repo with an encoded slash is refused" 3 nogh owner/name owner/name - - --repo "owner/na%2Fme" "$C1"
run_contract_case "--repo with a trailing newline is refused" 3 nogh owner/name owner/name - - --repo "owner/name${NL}" "$C1"
run_contract_case "empty --repo is refused" 3 nogh owner/name owner/name - - --repo "" "$C1"
run_contract_case "--repo with no value is refused" 3 nogh owner/name owner/name - - "$C1" --repo
run_contract_case "--repo with hyphens, underscores and dots is used" 0 "$C1" my-org/my_repo.js owner/name - - --repo my-org/my_repo.js "$C1"
# The inferred repository is validated the same way, and the sha is printed first.
run_contract_case "inferred repository with an injected path is refused" 3 noapi owner/name "owner/name/commits/${C2}/check-runs?x=" - - "$C1"
run_contract_case "sha line is printed before a failing repository lookup" 3 noapi owner/name FAIL - first "$C1"
# GH_REPO, GH_HOST and GIT_ variables never reach gh, so they cannot redirect it.
run_contract_case "ambient GH_REPO does not change the repository" 0 "$C1" owner/name owner/name "GH_REPO=evil/repo" "env pwd" "$C1"
run_contract_case "ambient GH_REPO does not reach gh with --repo" 0 "$C1" owner/name owner/name "GH_REPO=evil/repo" env --repo owner/name "$C1"
run_contract_case "ambient GH_HOST does not reach gh" 0 "$C1" owner/name owner/name "GH_HOST=evil.example.invalid" env "$C1"
run_contract_case "ambient GIT_DIR does not reach gh" 0 "$C1" owner/name owner/name "GIT_DIR=/nonexistent GIT_WORK_TREE=/nonexistent" env "$C1"
# A single -- ends option parsing.
run_contract_case "-- ends option parsing with --repo" 0 "$C1" owner/name owner/name - - --repo owner/name -- "$C1"
run_contract_case "-- ends option parsing with an inferred repository" 0 "$C1" owner/name owner/name - first -- "$C1"
run_contract_case "trailing -- is accepted" 0 "$C1" owner/name owner/name - - "$C1" --
run_contract_case "option-like value after -- is refused as a sha" 3 nogh owner/name owner/name - hint -- --wait
run_contract_case "second -- is an operand, not an option" 3 nogh owner/name owner/name - - -- -- "$C1"
# The interpreter is isolated, and a symlinked copy binds to the real file.
run_contract_case "PYTHONPATH shadowing does not change the result" 0 "$C1" owner/name owner/name SHADOW - "$C1"
run_contract_case "symlinked copy binds to the clone that holds the real file" 0 "$C1" owner/name owner/name - "link pwd" "$C1"
run_contract_case "symlinked wrapper in another directory runs the real ci-status.py" 0 "$C1" owner/name owner/name - "wraplink pwd first" "$C1"
# A repeated --repo, --timeout or --interval is refused, never silently replaced.
# run_contract_case already passes --interval 1, so one more --interval repeats it.
run_contract_case "second --repo is refused" 3 nogh owner/name owner/name - dup --repo owner/name --repo other/name "$C1"
run_contract_case "second --timeout is refused" 3 nogh owner/name owner/name - dup --wait --timeout 5 --timeout 6 "$C1"
run_contract_case "second --interval is refused" 3 nogh owner/name owner/name - dup --interval 2 "$C1"

# Wrapper path resolution fails closed (VERIFY 1.1 finding 1). Each case runs
# ci-status.sh from a working directory that holds a planted ci-status.py, which
# records that it ran. The planted file must never run. RESOLVE is a space-separated
# list: noreadlink (a readlink first on PATH that exits 1), nopyresolve (a python3
# first on PATH that exits 1 for python3 -I -c and runs the real python3 otherwise),
# nopy (the tools directory holds ci-status.sh only). One more token may name how
# the wrapper is invoked: sourced (bash -c sources it, so $0 is bash, then prints
# after=<status>; the caller must keep running and see status 3), stdin (bash
# -s reads it from a pipe), barename (bash ci-status.sh, found through PATH),
# pylink (a copied wrapper beside a ci-status.py that is a symlink to the planted
# file), pathexec (ci-status.sh executed through PATH), posixsh (the wrapper run
# by the first of dash, sh, ksh, mksh or posh that a probe confirms is not bash;
# skipped when there is none), restricted (bash -r), setr (bash run with a
# BASH_ENV file that runs set -r), setrsourced (bash -c runs set -r, then sources
# ci-status.sh found through PATH, then prints after=<status>; the caller must
# keep running and see status 3), or noread (the ci-status.py
# beside the wrapper has mode 000; skipped as root, where mode 000 is readable).
# Without one, the wrapper runs as bash with its absolute path. Each refusal has
# its own message, which the case checks.
# non_bash_shell prints the path of a shell whose BASH_VERSION is unset, or fails.
non_bash_shell() {
  local cand found
  for cand in dash sh ksh mksh posh; do
    found="$(command -v "$cand")" || continue
    if [ "$("$found" -c 'echo "${BASH_VERSION:-unset}"' 2>/dev/null)" = unset ]; then
      printf "%s" "$found"; return 0
    fi
  done
  return 1
}
# run_wrapper_case NAME WANT RESOLVE
run_wrapper_case() {
  local name="$1" want="$2" resolve="$3" posix_sh=""
  case " $resolve " in
    *" posixsh "*)
      if ! posix_sh="$(non_bash_shell)"; then
        printf "skip %s (no shell other than bash found)\n" "$name"; skips=$((skips + 1)); return
      fi ;;
    *" noread "*)
      if [ "$(id -u)" -eq 0 ]; then
        printf "skip %s (running as root, where mode 000 is readable)\n" "$name"; skips=$((skips + 1)); return
      fi ;;
  esac
  local tmp; tmp="$(mktemp -d)"
  local tools="$tmp/repo/tools" bin="$tmp/bin" cwd="$tmp/cwd"; mkdir -p "$tools" "$bin" "$cwd"
  cp "${here}/ci-status.sh" "$tools/"
  case " $resolve " in *" nopy "*) ;; *) cp "${here}/ci-status.py" "$tools/" ;; esac
  printf "import pathlib\npathlib.Path(\"%s\").touch()\n" "$tmp/planted-ran" > "$cwd/ci-status.py"
  printf "%s" "$GA_PRESENT" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*) cat "$tmp/def.json" ;;
  *) printf "" ;;
esac
GH
  chmod +x "$bin/gh"
  case " $resolve " in
    *" noreadlink "*)
      printf "#!/usr/bin/env bash\nexit 1\n" > "$bin/readlink"; chmod +x "$bin/readlink" ;;
  esac
  case " $resolve " in
    *" nopyresolve "*)
      local real_py; real_py="$(command -v python3)"
      cat > "$bin/python3" <<PY
#!/usr/bin/env bash
if [ "\${1:-}" = "-I" ] && [ "\${2:-}" = "-c" ]; then exit 1; fi
exec "$real_py" "\$@"
PY
      chmod +x "$bin/python3" ;;
  esac
  local entry=(bash "$tools/ci-status.sh") feed="" path="$bin:$PATH"
  case " $resolve " in
    *" sourced "*)
      entry=(bash -c '. "$1" "${@:2}"; s=$?; printf "after=%s\n" "$s"; exit "$s"' bash "$tools/ci-status.sh") ;;
    *" stdin "*) feed="$tools/ci-status.sh"; entry=(bash -s --) ;;
    *" barename "*) path="$bin:$tools:$PATH"; entry=(bash ci-status.sh) ;;
    *" pylink "*)
      tools="$tmp/copy"; mkdir -p "$tools"
      cp "${here}/ci-status.sh" "$tools/"
      ln -s "$cwd/ci-status.py" "$tools/ci-status.py"
      entry=(bash "$tools/ci-status.sh") ;;
    *" posixsh "*) entry=("$posix_sh" "$tools/ci-status.sh") ;;
    *" restricted "*) entry=(bash -r "$tools/ci-status.sh") ;;
    *" setr "*)
      printf "set -r\n" > "$tmp/setr.sh"
      entry=(env BASH_ENV="$tmp/setr.sh" bash "$tools/ci-status.sh") ;;
    *" setrsourced "*)
      path="$bin:$tools:$PATH"
      entry=(bash -c 'set -r; . ci-status.sh "$@"; s=$?; printf "after=%s\n" "$s"; exit "$s"' bash) ;;
    *" noread "*) chmod 000 "$tools/ci-status.py" ;;
    *" pathexec "*)
      chmod +x "$tools/ci-status.sh"; path="$bin:$tools:$PATH"; entry=(ci-status.sh) ;;
  esac
  (cd "$cwd" || exit 99
    if [ -n "$feed" ]; then
      cat "$feed" | PATH="$path" "${entry[@]}" --repo owner/name --interval 1 "$C1"
    else
      PATH="$path" "${entry[@]}" --repo owner/name --interval 1 "$C1"
    fi > "$tmp/out" 2> "$tmp/err")
  local got=$? ok=1 why=""
  if [ "$got" -ne "$want" ]; then ok=0; why="$why exit"; fi
  if [ -e "$tmp/planted-ran" ]; then ok=0; why="$why planted-ran"; fi
  local msg="ci-status: cannot find ci-status.py beside the real ci-status.sh" msgfile="$tmp/err"
  case " $resolve " in
    *" posixsh "*) msg="ci-status: ci-status.sh must run under bash, not another shell" ;;
    *" restricted "*|*" setr "*|*" setrsourced "*)
      msg="ci-status: ci-status.sh cannot run in a restricted shell"; msgfile="$tmp/out" ;;
    *" noread "*) msg="ci-status: cannot read ci-status.py beside the real ci-status.sh" ;;
  esac
  if [ "$want" -eq 3 ] && ! grep -q -F "$msg" "$msgfile"; then
    ok=0; why="$why message"
  fi
  if [ "$want" -eq 0 ] && ! grep -q -F "reading checks for commit ${C1}" "$tmp/out"; then
    ok=0; why="$why sha-line"
  fi
  case " $resolve " in
    *" sourced "*|*" setrsourced "*)
      if ! grep -q -x -F "after=3" "$tmp/out"; then ok=0; why="$why caller-status"; fi ;;
  esac
  if [ "$ok" -eq 1 ]; then
    printf "ok   %s (exit %s)\n" "$name" "$got"
  else
    printf "FAIL %s (got exit %s, want %s;%s)\n" "$name" "$got" "$want" "$why"
    fails=$((fails + 1))
  fi
  rm -rf "$tmp"
}

run_wrapper_case "normal path runs the real gate, not a planted ./ci-status.py" 0 -
run_wrapper_case "failing readlink does not run a planted ./ci-status.py" 0 noreadlink
run_wrapper_case "failed path resolution fails closed with exit 3" 3 nopyresolve
run_wrapper_case "failed resolution with failing readlink fails closed with exit 3" 3 "noreadlink nopyresolve"
run_wrapper_case "wrapper with no ci-status.py beside it fails closed with exit 3" 3 nopy
run_wrapper_case "sourced wrapper returns status 3 to the caller" 3 sourced
run_wrapper_case "wrapper read from standard input fails closed with exit 3" 3 stdin
run_wrapper_case "bare wrapper name found through PATH fails closed with exit 3" 3 barename
run_wrapper_case "symlinked ci-status.py beside a copied wrapper fails closed with exit 3" 3 pylink
run_wrapper_case "wrapper executed through PATH runs the real gate" 0 pathexec
run_wrapper_case "wrapper run by a non-bash shell fails closed with exit 3" 3 posixsh
run_wrapper_case "wrapper run by a restricted shell fails closed with exit 3" 3 restricted
run_wrapper_case "unreadable ci-status.py fails closed with exit 3" 3 noread
run_wrapper_case "wrapper executed in a shell restricted by set -r fails closed with exit 3" 3 setr
run_wrapper_case "wrapper sourced after set -r returns status 3 to the caller" 3 setrsourced

# A skipped case is not verified, so any skip makes the suite incomplete and
# nonzero; the final line then names the count.
if [ "$skips" -gt 0 ]; then
  if [ "$fails" -gt 0 ]; then
    printf "%s ci-status test(s) failed\n" "$fails"
  fi
  printf "ci-status suite incomplete: %s test(s) skipped\n" "$skips"
  exit 1
fi
if [ "$fails" -eq 0 ]; then
  printf 'all ci-status github-actions fail-safe tests pass
'
  exit 0
fi
printf '%s ci-status test(s) failed
' "$fails"
exit 1
