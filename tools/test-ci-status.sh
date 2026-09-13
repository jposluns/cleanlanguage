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
run_timed_case "wait stops near the deadline, not a whole interval past it" "$GA_IN_PROGRESS" 4 2 --wait --timeout 2 --interval 5

if [ "$fails" -eq 0 ]; then
  printf 'all ci-status github-actions fail-safe tests pass
'
  exit 0
fi
printf '%s ci-status test(s) failed
' "$fails"
exit 1
