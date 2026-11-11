#!/usr/bin/env bash
#
# Offline tests for the required-check fail-safe in ci-status. The verdict logic
# lives in tools/ci-status.py (a Python rewrite that parses the check-runs JSON
# structurally and fail-closed); tools/ci-status.sh is a thin wrapper that execs
# it, so these tests drive the wrapper exactly as callers do.
#
# The gate reports a pass only after two identical readings. It insists on 5
# checks: the GitHub Actions jobs Plugin manifests, Skill discovery, Agent
# Plugins manifest and CI status tests, each matched by its exact display name
# together with the github-actions app slug and read as a failure on any
# conclusion other than success, and the external Cloudflare Pages build,
# matched by the exact app slug cloudflare-workers-and-pages and app id 85455 of
# the Cloudflare app, whatever its name. A passing reading missing any of them
# is downgraded to pending, never a red; an unnamed or differently named
# github-actions run, or a required name posted by another app, does not count.
# Presence is read from the same reading as the verdict, and the reading is
# FAIL-CLOSED: a malformed page (non-object, or check_runs that is not a list),
# a check that is not an object, any field of the wrong type (a status that is
# not a non-empty string, a conclusion/name/slug that is neither a string nor
# null, or an app id that is neither an integer nor null), or a head_sha that is
# present and does not name the requested commit makes the whole reading
# unreadable rather than dropping or forging a check. A name and the
# github-actions slug are each compared as the whole string, control characters
# included, with no trimming, case folding or partial match, and a present
# head_sha as the whole commit sha in either letter case. The slug is taken only
# from the app object, so a required name followed by separators and a slug,
# under a null app, does not count. A failed read breaks a confirmation in
# progress but the same green set reappearing re-arms without consuming the
# changing-set budget. Waits are deadline-capped; numeric arguments are base-10
# and range-checked.
#
# Each case of run_case, run_err_case and run_log_case puts a fake gh on PATH
# serving check-runs from a per-call "plan" (tokens g/a/t/f/s: default payload,
# alternate payload, third payload, a failed call, or a call that hangs until
# ci-status ends it at the wait deadline), runs ci-status and asserts its exit
# code. Many cases also assert a fixed string on standard error (CASE_NEEDLE
# and run_err_case), such as the required check named as missing, the malformed
# field, or a line of the report; some assert a fixed string on standard output
# (CASE_OUT); some assert that a fixed string is absent from standard error
# (CASE_ABSENT); some assert how many check-runs calls the fake gh served
# (CASE_READS); and some assert that the only gh call made is the paginated
# check-runs read of the commit (CASE_ONLY_CALLS and run_log_case). The timed
# case also bounds the elapsed time; the cut-off, deadline-stop and plan-clock
# cases (run_cut_off_case, run_deadline_stop_case and run_clock_case) serve
# check-runs from a fake gh in process on 1 fake clock, and their gh on PATH
# only refuses; and the paginate case serves page 2 only to a --paginate call.
# The later sections, the workflow shape check, the commit sha and repository
# contract, the wrapper path resolution, and the output, signal, pipe, import,
# lost-status, final-reap, closed-window and late-pass cases, each say what
# they assert.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ci="${here}/ci-status.sh"
fails=0
skips=0  # a skipped case is reported on a skip line and never counted as ok
# setup_failed NAME: a case that cannot create its scratch directory fails visibly
# and runs nothing.
setup_failed() {
  printf "FAIL %s (could not create a scratch directory)\n" "$1"; fails=$((fails + 1))
}

C1=0c83f120fcc4630694465bcf89f7415a21d54dba
C1_UPPER=0C83F120FCC4630694465BCF89F7415A21D54DBA
C2=1111111111111111111111111111111111111111

# The 5 required checks, each green, as JSON fragments; every green fixture is
# built from them.
PM_OK='{"status":"completed","conclusion":"success","name":"Plugin manifests","app":{"slug":"github-actions"}}'
SD_OK='{"status":"completed","conclusion":"success","name":"Skill discovery","app":{"slug":"github-actions"}}'
APM_OK='{"status":"completed","conclusion":"success","name":"Agent Plugins manifest","app":{"slug":"github-actions"}}'
CST_OK='{"status":"completed","conclusion":"success","name":"CI status tests","app":{"slug":"github-actions"}}'
CF='{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}'
REQ_GA="${PM_OK},${SD_OK},${APM_OK},${CST_OK}"
# runs FRAGMENT...: one check-runs page holding the fragments in order.
runs() { local IFS=,; printf '{"check_runs":[%s]}' "$*"; }
# head_runs HEAD: the 5 required checks, each carrying "head_sha":HEAD, where
# HEAD is raw JSON.
head_runs() {
  local f out=()
  for f in "$PM_OK" "$SD_OK" "$APM_OK" "$CST_OK" "$CF"; do out+=("{\"head_sha\":${1},${f#\{}"); done
  runs "${out[@]}"
}

GA_PRESENT="$(runs "$REQ_GA" "$CF")"
GA_REVERSED="$(runs "$CF" "$CST_OK" "$APM_OK" "$SD_OK" "$PM_OK")"
# The reading every github-actions run satisfied before row 66: one unnamed
# github-actions job (display name check, as the sitemap job has) beside the
# Cloudflare build. None of the 4 required Actions checks is in it.
GENERIC_GA='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}
]}'
CLOUDFLARE_ONLY='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}
]}'
GA_IN_PROGRESS="$(runs '{"status":"in_progress","conclusion":null,"name":"Plugin manifests","app":{"slug":"github-actions"}}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")"
# A red reading: Plugin manifests failed, beside the other 4 required checks
# green. A wait that reaches it ends at once (exit 1), whatever time is left.
GA_RED="$(runs '{"status":"completed","conclusion":"failure","name":"Plugin manifests","app":{"slug":"github-actions"}}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")"
EMPTY_CONCLUSION='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}},
  {"status":"completed","conclusion":null,"name":"success","app":{"slug":"external-app"}}
]}'
INJECT_US='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"x\u001fgithub-actions","app":{"slug":null}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}
]}'
INJECT_NL_US='{"check_runs":[
  {"status":"completed","conclusion":"success","name":"benign\ncompleted\u001fsuccess\u001fforged\u001fgithub-actions","app":{"slug":null}},
  {"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}
]}'
# A required name followed by a unit separator and the github-actions slug,
# under a null app, beside the other 4 required checks green. A reader that took
# the name and slug from the name text (as the earlier shell reader, which split
# delimited records, could be made to) would see all 5 and call the reading
# green; the tool takes the slug only from the app object, so Plugin manifests
# stays missing.
FORGE_US="$(runs '{"status":"completed","conclusion":"success","name":"Plugin manifests\u001fgithub-actions","app":null}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")"
# The same with a newline and a whole forged record (status, conclusion, name,
# slug) after it, under an app whose slug is null.
FORGE_NL_US="$(runs '{"status":"completed","conclusion":"success","name":"benign\ncompleted\u001fsuccess\u001fPlugin manifests\u001fgithub-actions","app":{"slug":null}}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")"
MULTIPAGE_GA_P2="$(runs "$CF")
$(runs "$REQ_GA")"
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
# The commit read is CASE_SHA when it is set, else the zero sha. When CASE_NEEDLE
# is set, standard error must contain each of its lines as a fixed string. When
# CASE_READS is set, the fake gh must have served exactly that many check-runs
# calls. When CASE_ONLY_CALLS
# is set, every gh call must be exactly the paginated check-runs read of that
# commit. The fake gh logs every call and answers a commit-status route with a
# green body, so a tool that consulted commit statuses would see a pass there.
# When CASE_ABSENT is set, standard error must not contain it as a fixed
# string, and an error file that grep cannot search fails the case. When
# CASE_THIRD is set, the plan token t serves it as the payload. When CASE_OUT is
# set, standard output must contain it as a fixed string.
run_case() {
  local name="$1" def="$2" alt="$3" plan="$4" want="$5"; shift 5
  local sha="${CASE_SHA:-0000000000000000000000000000000000000000}"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf '%s' "$def" > "$tmp/def.json"
  printf '%s' "$alt" > "$tmp/alt.json"
  printf '%s' "${CASE_THIRD:-}" > "$tmp/third.json"
  printf '%s' "$plan" > "$tmp/plan"
  : > "$tmp/calls"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$tmp/calls"
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
      s) exec sleep 60 ;;
      a) cat "$tmp/alt.json" ;;
      t) cat "$tmp/third.json" ;;
      *) cat "$tmp/def.json" ;;
    esac
    ;;
  */status*) printf '{"state":"success","statuses":[{"state":"success","context":"Plugin manifests"}]}' ;;
  *"repo view"*) printf 'owner/name' ;;
  *) printf '' ;;
esac
GH
  chmod +x "$bin/gh"
  PATH="$bin:$PATH" bash "$ci" "$sha" \
    --repo owner/name --interval 1 "$@" >"$tmp/out" 2>"$tmp/err"
  local got=$? why=""
  if [ "$got" -ne "$want" ]; then why="$why exit"; fi
  if [ -n "${CASE_NEEDLE:-}" ]; then
    local needle
    while IFS= read -r needle; do
      if ! grep -q -F -- "$needle" "$tmp/err"; then why="$why message"; break; fi
    done <<< "$CASE_NEEDLE"
  fi
  if [ -n "${CASE_READS:-}" ] && [ "$(cat "$tmp/n" 2>/dev/null || echo 0)" != "$CASE_READS" ]; then
    why="$why reads"
  fi
  if [ -n "${CASE_OUT:-}" ] && ! grep -q -F -- "$CASE_OUT" "$tmp/out"; then
    why="$why output"
  fi
  if [ -n "${CASE_ABSENT:-}" ]; then
    grep -q -F -- "$CASE_ABSENT" "$tmp/err"
    case $? in 1) ;; *) why="$why absent" ;; esac
  fi
  if [ -n "${CASE_ONLY_CALLS:-}" ]; then
    local only="api repos/owner/name/commits/${sha}/check-runs --paginate"
    if [ ! -s "$tmp/calls" ] || grep -q -v -x -F -- "$only" "$tmp/calls"; then why="$why calls"; fi
  fi
  if [ -z "$why" ]; then
    printf 'ok   %s (exit %s)\n' "$name" "$got"
  else
    printf 'FAIL %s (got %s, want %s;%s)\n' "$name" "$got" "$want" "$why"; fails=$((fails + 1))
  fi
  rm -rf "$tmp"
}

# run_err_case NAME PAYLOAD WANT NEEDLE: one reading of PAYLOAD must exit WANT
# with NEEDLE on standard error.
run_err_case() { local CASE_NEEDLE="$4"; run_case "$1" "$2" "" "" "$3"; }
# run_log_case NAME PAYLOAD WANT: one reading of PAYLOAD must exit WANT, and the
# only gh call made must be the paginated check-runs read of the commit, so
# neither a commit-status read nor a check-runs filter can stand in for a
# required check.
run_log_case() { local CASE_ONLY_CALLS=1; run_case "$1" "$2" "" "" "$3"; }

# run_timed_case NAME PAYLOAD MAX_SECONDS WANT EXTRA...
run_timed_case() {
  local name="$1" payload="$2" maxs="$3" want="$4"; shift 4
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
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
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
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
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }; local bin="$tmp/bin"; mkdir -p "$bin"
  python3 -I -c "open('$tmp/cr.json','w').write('['*100000 + ']'*100000)"
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
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }; local bin="$tmp/bin"; mkdir -p "$bin"
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

# FAKE_CLOCK_GATE is the start of the Python program that run_cut_off_case,
# run_deadline_stop_case and run_clock_case run. It loads tools/ci-status.py in
# process and gives it 1 fake clock, a count of whole nanoseconds that starts
# at 1000.0 seconds. time.time reads it, time.sleep moves it by the time asked
# for without waiting, and time.monotonic reads it 500 seconds lower. While
# wall is set, time.time reads that fixed value and time.monotonic moves on, as
# when the wall clock stands still or steps; kills, returns and the exit are
# recorded on the moving clock (now). Counting whole nanoseconds makes every
# sum of sleeps exact. gh is a fake child on the same clock, reached through
# Popen, os.waitpid and os.kill, not a real process (its pid is above any pid
# the kernel assigns). Starting it moves the clock by GH_STARTS seconds, as
# starting a real gh takes time. It records its call in TMP/reads, writes
# GH_OUTPUT, and ends with the wait status GH_STATUS (0, an exit 0, unless a
# case sets it) once the clock reaches GH_ENDS seconds after it has started,
# unless a SIGKILL ends it first; a blocking wait moves the clock to that end.
# A gate that polls it 100000 times without an end is stopped with an error, so
# a gate that polls without sleeping cannot hang the suite. The program records
# each deadline read_checks is given, each deadline _gh is given, the clock at
# each kill and at each return of _gh, and calls before_read as each read
# starts. Every clock read and sleep the gate makes through its time name is
# fake, so the speed of the host cannot change any time these cases read. A
# wait the gate makes outside that name, such as __import__("time").sleep or a
# sleep in another module, does not move the fake clock, so no case here
# asserts it. finish writes what the case observed to TMP/facts and the names
# of the failed expectations to TMP/why, and exits with the code of the gate.
FAKE_CLOCK_GATE='import importlib.util, os, signal, subprocess, sys, types
path, sha, tmp = sys.argv[1:4]
NS = 10 ** 9
TOL = 1e-6  # 1 microsecond: far above float rounding here, far below a poll of 0.02 seconds
PID = 2 ** 31 - 1  # above any pid the kernel assigns, so no real process can be reached
spec = importlib.util.spec_from_file_location("ci_status_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ticks = [1000 * NS]
wall = [None]  # while set, time.time reads this value and time.monotonic moves on
def now():
    return ticks[0] / NS
def clock():
    return now() if wall[0] is None else wall[0]
def sleep(seconds):
    if seconds < 0:
        raise ValueError("sleep length must be non-negative")
    ticks[0] += round(seconds * NS)  # the time asked for, without waiting
def monotonic():
    return now() - 500  # a fixed offset, so the 2 clocks never agree
mod.time = types.SimpleNamespace(time=clock, monotonic=monotonic, sleep=sleep)
GH_STARTS, GH_ENDS, GH_OUTPUT, GH_STATUS = 0.0, 60.0, b"", 0
deadlines, gh_deadlines, kills, returns, procs, polls = [], [], [], [], {}, [0]
class Gh:
    def __init__(self, args, stdout):
        ticks[0] += round(GH_STARTS * NS)  # the time starting gh takes
        self.args, self.pid, self.returncode = args, PID - len(procs), None
        self.ends, self.status, self.reaped = ticks[0] + round(GH_ENDS * NS), None, False
        self.code = GH_STATUS  # the wait status gh ends with on its own
        with open(tmp + "/reads", "a") as f:
            f.write("read\n")
        stdout.write(GH_OUTPUT)
        procs[self.pid] = self
class Subprocess:
    def __getattr__(self, name):
        return getattr(subprocess, name)
    def Popen(self, args, stdout=None, **kwargs):
        return Gh(args, stdout)
mod.subprocess = Subprocess()
def child(pid, error):
    if pid not in procs or procs[pid].reaped:
        raise error(pid)
    return procs[pid]
class Os:
    def __getattr__(self, name):
        return getattr(os, name)
    def waitpid(self, pid, options):
        p = child(pid, ChildProcessError)
        if p.status is None and ticks[0] >= p.ends:
            p.status = p.code
        if p.status is None:
            if options & os.WNOHANG:
                polls[0] += 1
                if polls[0] > 100000:
                    raise RuntimeError("gh polled 100000 times without an end")
                return 0, 0
            ticks[0], p.status = p.ends, p.code  # a blocking wait lasts until gh ends
        p.reaped = True
        return p.pid, p.status
    def kill(self, pid, sig):
        p = child(pid, ProcessLookupError)
        kills.append(now())
        if p.status is None and sig == signal.SIGKILL:
            p.status = signal.SIGKILL  # the wait status of an end by SIGKILL
mod.os = Os()
def before_read():
    pass
real_read_checks = mod.read_checks
def read_checks(repo, full_sha, deadline):
    deadlines.append(deadline)
    before_read()
    return real_read_checks(repo, full_sha, deadline)
mod.read_checks = read_checks
real_gh = mod._gh
def gh(args, deadline):
    gh_deadlines.append(deadline)
    try:
        return real_gh(args, deadline)
    finally:
        wall[0] = None  # the wall clock catches up once _gh has returned
        returns.append(now())
mod._gh = gh
def run_gate(*flags):
    sys.argv = [path, "--repo", "owner/name", *flags, sha]
    return mod.run()
def near(values, wants):
    return len(values) == len(wants) and all(abs(v - w) <= TOL for v, w in zip(values, wants))
def show(values):
    return " ".join("%.6f" % v for v in values) or "none"
def finish(code, why, facts):
    with open(tmp + "/facts", "w") as f:
        f.write(facts)
    with open(tmp + "/why", "w") as f:
        f.write("".join(" " + w for w in why))
    sys.exit(code)
'

# run_cut_off_case NAME LEFT BOUND [STARTS [KILLED [FROZEN]]]: the gate runs in
# process on the fake clock of FAKE_CLOCK_GATE, in wait mode with --timeout 2
# and --interval 1, so the deadline is 1002.0. When the read starts, with the
# clock still at 1000.0, the case moves the clock to 1002.0 minus LEFT, so LEFT
# seconds are left; starting the fake gh then takes STARTS seconds (0 when not
# given), and gh would end only 60 seconds after it has started, so only the
# wait deadline can end the read. KILLED is 1002.0 when not given. With FROZEN
# 1, time.time stands still from the start of the read until _gh returns. Every
# expectation is a constant of this setup, compared as a number to within 1
# microsecond: read_checks must be called once, at 1000.0, with the deadline
# 1002.0; _gh must be given the deadline 1002.0; gh must be killed exactly
# once, at KILLED; _gh must return at KILLED; the gate must exit with the clock
# at KILLED; standard error must hold the read-failure line saying that gh api
# did not return within BOUND; and the fake gh must serve exactly 1 check-runs
# call. A delay of more than 1 microsecond that moves the start of the read,
# the kill, the return of _gh or the exit off its constant fails the case; so
# do any other deadline given to read_checks or _gh, a bound whose clock starts
# only after gh has started (with STARTS 1 and LEFT 2 it kills at 1003.0), a
# last poll that sleeps a whole 0.02 seconds with less left (with 0.03 seconds
# left it kills at 1002.01), a gate that compares one clock with a deadline set
# on the other, a gate that kills on time.time (with FROZEN 1), and a gate that
# never kills gh. No expectation asserts a delay that comes after _gh has read
# both clocks and before a clock read of the poll loop, ending no later than
# 1002.0; the time STARTS charges to the start of gh, when it ends before
# 1002.0, is such a delay. With the wall clock moving and gh started before
# 1002.0, the kill, return and exit times do not assert a delay in read_checks
# or _gh before _gh reads started. Such a delay leaves gh a bound below LEFT,
# which changes the tenths the message names in the case with LEFT 0.5 and in
# the 2 cases with LEFT 2, STARTS 0 or 1 and FROZEN 0, so the message check
# catches it in those 3 cases.
run_cut_off_case() {
  local name="$1" left="$2" want_bound="$3" starts="${4:-0}" killed="${5:-1002.0}" frozen="${6:-0}"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }; local bin="$tmp/bin"; mkdir -p "$bin"
  # The fake gh is in process; a gh on PATH is reached only if the gate
  # bypasses it.
  printf '#!/usr/bin/env bash\necho "unexpected gh call" >&2; exit 1\n' > "$bin/gh"
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c "$FAKE_CLOCK_GATE"'
left, GH_STARTS, KILLED = float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
FROZEN = sys.argv[7] == "1"
START, DEADLINE = 1000.0, 1002.0  # the start, the start plus --timeout 2
starts = []
def before_read():
    starts.append(clock())
    ticks[0] = 1002 * NS - round(left * NS)  # LEFT seconds are left when the read starts
    if FROZEN:
        wall[0] = now()  # time.time stands still until _gh returns
code = run_gate("--wait", "--timeout", "2", "--interval", "1")
why = [w for w, ok in (
    ("start", near(starts, [START])),
    ("deadline", near(deadlines, [DEADLINE])),
    ("gh-deadline", near(gh_deadlines, [DEADLINE])),
    ("kill", near(kills, [KILLED])),
    ("returned", near(returns, [KILLED])),
    ("end", near([now()], [KILLED])),
) if not ok]
finish(code, why, "read at %s, deadline %s, gh deadline %s, killed at %s, returned at %s, exit at %.6f"
       % (show(starts), show(deadlines), show(gh_deadlines), show(kills), show(returns), now()))' \
    "${here}/ci-status.py" "$C1" "$tmp" "$left" "$starts" "$killed" "$frozen" > "$tmp/out" 2> "$tmp/err" || got=$?
  local why="" facts
  facts="$(cat "$tmp/facts" 2>/dev/null)"
  if [ -f "$tmp/why" ]; then why="$(cat "$tmp/why")"; else why=" clocks"; fi
  [ "$got" -eq 3 ] || why="$why exit"
  grep -q -x -F -- "ci-status: check read failed for ${C1}: gh api did not return within ${want_bound}" \
    "$tmp/err" || why="$why message"
  [ "$(grep -c "" "$tmp/reads" 2>/dev/null)" = 1 ] || why="$why reads"
  if [ -z "$why" ]; then printf "ok   %s (exit %s, %s)\n" "$name" "$got" "$facts";
  else printf "FAIL %s (got exit %s, %s; want exit 3, read at 1000.000000, deadline and gh deadline 1002.000000, kill, return and exit at %s;%s)\n" "$name" "$got" "${facts:-?}" "$killed" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

# run_deadline_stop_case NAME: the gate runs in process on the fake clock of
# FAKE_CLOCK_GATE, in wait mode with --timeout 10 and --interval 30, so the
# deadline is 1010.0, and the fake gh serves a pending reading and ends 3
# seconds after it has started. Every expectation is a constant of this setup,
# compared as a number to within 1 microsecond: read_checks must be called
# once, with the deadline 1010.0; _gh must be given the deadline 1010.0; gh
# must not be killed; _gh must return at 1003.0; the gate must exit with the
# clock at 1010.0; standard output must hold the line "ci-status: waiting, 7
# seconds left"; standard error must hold the still-unsettled line but no
# read-failure line; and the fake gh must serve exactly 1 check-runs call. A
# delay of more than 1 microsecond that moves the return of _gh or the exit off
# its constant fails the case: a sleep before _gh returns moves the return past
# 1003.0, and a sleep between readings longer than the time left moves the exit
# past 1010.0 (one capped by the whole timeout ends at 1013.0, a whole interval
# at 1033.0). No expectation asserts a delay after the waiting line and before
# nap reads the clock, ending no later than 1010.0.
run_deadline_stop_case() {
  local name="$1"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf "%s" "$GA_IN_PROGRESS" > "$tmp/def.json"
  # The fake gh is in process; a gh on PATH is reached only if the gate
  # bypasses it.
  printf '#!/usr/bin/env bash\necho "unexpected gh call" >&2; exit 1\n' > "$bin/gh"
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c "$FAKE_CLOCK_GATE"'
START, DEADLINE, READ = 1000.0, 1010.0, 3.0  # the start, the start plus --timeout 10, the read time
with open(tmp + "/def.json", "rb") as f:
    GH_OUTPUT = f.read()
GH_ENDS = READ
code = run_gate("--wait", "--timeout", "10", "--interval", "30")
why = [w for w, ok in (
    ("deadline", near(deadlines, [DEADLINE])),
    ("gh-deadline", near(gh_deadlines, [DEADLINE])),
    ("kill", not kills),
    ("returned", near(returns, [START + READ])),
    ("end", near([clock()], [DEADLINE])),
) if not ok]
finish(code, why, "deadline %s, gh deadline %s, killed at %s, returned at %s, exit at %.6f"
       % (show(deadlines), show(gh_deadlines), show(kills), show(returns), clock()))' \
    "${here}/ci-status.py" "$C1" "$tmp" > "$tmp/out" 2> "$tmp/err" || got=$?
  local why="" facts
  facts="$(cat "$tmp/facts" 2>/dev/null)"
  if [ -f "$tmp/why" ]; then why="$(cat "$tmp/why")"; else why=" clocks"; fi
  [ "$got" -eq 2 ] || why="$why exit"
  grep -q -x -F -- "ci-status: waiting, 7 seconds left" "$tmp/out" || why="$why pending"
  grep -q -x -F -- "ci-status: still unsettled after 10 seconds; giving up" "$tmp/err" || why="$why timeout"
  grep -q -F -- "check read failed" "$tmp/err"
  case $? in 1) ;; *) why="$why absent" ;; esac
  [ "$(grep -c "" "$tmp/reads" 2>/dev/null)" = 1 ] || why="$why reads"
  if [ -z "$why" ]; then printf "ok   %s (exit %s, %s)\n" "$name" "$got" "$facts";
  else printf "FAIL %s (got exit %s, %s; want exit 2, deadline and gh deadline 1010.000000, return at 1003.000000, exit at 1010.000000;%s)\n" "$name" "$got" "${facts:-?}" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

# run_clock_case NAME DEFAULT ALT PLAN WANT [EXTRA ci-status ARGS...]: run_case
# for a plan that ends in a read the deadline cuts off, on the fake clock of
# FAKE_CLOCK_GATE with --interval 1, so a slow host cannot close the window
# before that read starts. Each read other than s takes 0.5 seconds on that
# clock: g serves DEFAULT, a serves ALT, f ends with exit 1, and s would end
# only 60 seconds after it has started; the last token repeats once the plan
# runs out. Exit, CASE_NEEDLE, CASE_ABSENT and CASE_READS are checked as
# run_case checks them, and gh must be killed exactly once, at the deadline of
# the --timeout given. When CASE_NO_KILL is set, the plan is one the deadline
# never cuts off, and gh must never be killed instead.
run_clock_case() {
  local name="$1" def="$2" alt="$3" plan="$4" want="$5"; shift 5
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf '%s' "$def" > "$tmp/def.json"
  printf '%s' "$alt" > "$tmp/alt.json"
  # The fake gh is in process; a gh on PATH is reached only if the gate
  # bypasses it.
  printf '#!/usr/bin/env bash\necho "unexpected gh call" >&2; exit 1\n' > "$bin/gh"
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c "$FAKE_CLOCK_GATE"'
plan, flags = sys.argv[4].split(), sys.argv[5:]
no_kill = bool(os.environ.get("CASE_NO_KILL"))  # set on the case, so the shell exports it
DEADLINE = 1000.0 + float(flags[flags.index("--timeout") + 1])
payloads = {}
for tok, file in (("g", "/def.json"), ("a", "/alt.json")):
    with open(tmp + file, "rb") as f:
        payloads[tok] = f.read()
starts = []
def before_read():
    global GH_OUTPUT, GH_ENDS, GH_STATUS
    starts.append(clock())
    tok = plan[min(len(starts), len(plan)) - 1]
    GH_OUTPUT = payloads.get(tok, b"")
    GH_ENDS = 60.0 if tok == "s" else 0.5
    GH_STATUS = 256 if tok == "f" else 0  # 256 is the wait status of exit 1
code = run_gate("--interval", "1", *flags)
why = [w for w, ok in (("kill", not kills if no_kill else near(kills, [DEADLINE])),) if not ok]
finish(code, why, "reads at %s, killed at %s, exit at %.6f" % (show(starts), show(kills), now()))' \
    "${here}/ci-status.py" 0000000000000000000000000000000000000000 "$tmp" "$plan" "$@" > "$tmp/out" 2> "$tmp/err" || got=$?
  local why="" facts
  facts="$(cat "$tmp/facts" 2>/dev/null)"
  if [ -f "$tmp/why" ]; then why="$(cat "$tmp/why")"; else why=" clocks"; fi
  [ "$got" -eq "$want" ] || why="$why exit"
  if [ -n "${CASE_NEEDLE:-}" ]; then
    local needle
    while IFS= read -r needle; do
      if ! grep -q -F -- "$needle" "$tmp/err"; then why="$why message"; break; fi
    done <<< "$CASE_NEEDLE"
  fi
  if [ -n "${CASE_READS:-}" ] && [ "$(grep -c "" "$tmp/reads" 2>/dev/null)" != "$CASE_READS" ]; then
    why="$why reads"
  fi
  if [ -n "${CASE_ABSENT:-}" ]; then
    grep -q -F -- "$CASE_ABSENT" "$tmp/err"
    case $? in 1) ;; *) why="$why absent" ;; esac
  fi
  if [ -z "$why" ]; then printf 'ok   %s (exit %s, %s)\n' "$name" "$got" "$facts";
  else printf 'FAIL %s (got %s, want %s, %s;%s)\n' "$name" "$got" "$want" "${facts:-?}" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

# run_rc_case NAME WANT [END]: fake gh emits a GREEN body, then runs END (exit 1
# when END is not given); the returncode guard must reject it (exit 3), not
# parse the body as green.
run_rc_case() {
  local name="$1" want="$2" end="${3:-exit 1}"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }; local bin="$tmp/bin"; mkdir -p "$bin"
  printf '%s' "$GA_PRESENT" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in *check-runs*) cat "$tmp/def.json"; ${end};; *"repo view"*) printf 'owner/name';; *) printf '';; esac
GH
  chmod +x "$bin/gh"
  PATH="$bin:$PATH" bash "$ci" 0000000000000000000000000000000000000000 --repo owner/name >/dev/null 2>&1
  local got=$?
  if [ "$got" -eq "$want" ]; then printf 'ok   %s (exit %s)\n' "$name" "$got";
  else printf 'FAIL %s (got %s, want %s)\n' "$name" "$got" "$want"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}


run_case "all 5 required checks present -> green" "$GA_PRESENT" "" "" 0
run_case "only external check, no github-actions -> not green" "$CLOUDFLARE_ONLY" "" "" 2
run_case "unfinished required check -> not green" "$GA_IN_PROGRESS" "" "" 2
run_case "unreadable check-runs read -> not green" "$GA_PRESENT" "" "f" 3
# A failed gh call is reported with the commit and repository read, the standard
# error of gh passed on, and gh api failed as the reason.
CASE_NEEDLE="could not read checks for 0000000000000000000000000000000000000000 in owner/name" \
  run_case "a failed read names the commit and repository" "$GA_PRESENT" "" "f" 3
CASE_NEEDLE="simulated check-runs read failure" \
  run_case "a failed read passes on the standard error of gh" "$GA_PRESENT" "" "f" 3
CASE_NEEDLE="check read failed for 0000000000000000000000000000000000000000: gh api failed" \
  run_case "a failed read gives gh api failed as the reason" "$GA_PRESENT" "" "f" 3
# A failed read, or a pending reading, between 2 green readings restarts the
# confirmation: the green reading after it is a first reading again, not the
# second of a pair, so the tool reads once more. That reading is red, so the
# tool exits 1 at once; a reader that kept the earlier green reading would
# confirm on the third reading (exit 0). The red reading, not the window, ends
# each case, so its result does not depend on how long the reads take.
CASE_THIRD="$GA_RED" run_case "failed read between green reads does not confirm" \
  "$GA_PRESENT" "" "g f g t" 1 --wait --timeout 30
CASE_THIRD="$GA_RED" run_case "pending reading between green readings restarts the confirmation" \
  "$GA_PRESENT" "$GA_IN_PROGRESS" "g a g t" 1 --wait --timeout 30
run_case "transient read failures on a stable set still confirm green" "$GA_PRESENT" "" "g f g f g f g f g f g g" 0 --wait --timeout 30
run_case "reordered identical check set still confirms green" "$GA_PRESENT" "$GA_REVERSED" "g a g a g a" 0
# A completed check with no conclusion must stay non-green: a null conclusion
# reads as empty, which is not a passing conclusion, so the reading is red.
run_case "completed check with null conclusion is not green" "$EMPTY_CONCLUSION" "" "" 1
# The tool strips nothing from a name: it compares the whole string, control
# characters included, and takes the slug only from the app object. These 2
# readings carry none of the 4 required Actions names, so they stay pending
# whatever a reader does with control characters; they pin only that such text
# does not turn a reading red or unreadable.
run_case "text in a name cannot fabricate github-actions presence" "$INJECT_US" "" "" 2
run_case "newline and text in a name cannot fabricate presence" "$INJECT_NL_US" "" "" 2
# These 2 carry a required name with separators and a slug appended, under a
# null app or a null slug, beside the other 4 required checks green, so a reader
# that took the name or slug from the name text would read green (exit 0); the
# tool reads Plugin manifests as missing and names it.
run_err_case "required name with a separator and slug under a null app does not count" \
  "$FORGE_US" 2 "required check(s) Plugin manifests not registered"
run_err_case "required name in a forged record after a newline does not count" \
  "$FORGE_NL_US" 2 "required check(s) Plugin manifests not registered"
# The 4 required github-actions checks are on page 2 of a paginated payload;
# read_checks parses every page of the concatenated stream, so they are seen: green.
run_case "required github-actions checks only on page 2 of a paginated payload -> green" "$MULTIPAGE_GA_P2" "" "" 0
# read_checks must request --paginate: the fake emits page 2 (the 4 required
# github-actions checks) only when --paginate is passed, so a tool that drops it
# would miss them and not be green.
run_paginate_case "read_checks paginates to see page-2 required checks -> green" "$CLOUDFLARE_ONLY" "$(runs "$REQ_GA")" 0
# Duplicate check_runs members: JSON keeps the last, so a naive parser would hide
# the failing run. Must be rejected as ambiguous.
DUP_KEY='{"check_runs":[{"status":"completed","conclusion":"failure","name":"required","app":{"slug":"external"}}],"check_runs":[{"status":"completed","conclusion":"success","name":"ga","app":{"slug":"github-actions"}}]}'
# A page declaring total_count 2 but delivering one run (truncation): the missing
# run could be failing, so the reading must be rejected.
TRUNCATED='{"total_count":2,"check_runs":[{"status":"completed","conclusion":"success","name":"ga","app":{"slug":"github-actions"}}]}'
# The 4 required github-actions checks present but the required Cloudflare Pages
# check ABSENT: not green until the required check registers.
MISSING_CLOUDFLARE="{\"total_count\":4,\"check_runs\":[${REQ_GA}]}"
# A duplicate check-run id pads the list to match total_count while hiding a run.
DUP_ID='{"total_count":3,"check_runs":[{"id":1,"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}},{"id":2,"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}},{"id":2,"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}]}'
# total_count present as an explicit null is malformed.
TOTAL_NULL='{"total_count":null,"check_runs":[{"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}},{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}]}'
# total_count present on one page but not the other is inconsistent.
INCONSISTENT_TOTAL='{"check_runs":[{"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}}]}
{"total_count":2,"check_runs":[{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}]}'
# A check whose app field is not an object ([]) must not coerce to a null slug.
NONOBJ_APP='{"total_count":2,"check_runs":[{"status":"completed","conclusion":"success","name":"pm","app":{"slug":"github-actions"}},{"status":"completed","conclusion":"success","name":"cf","app":[]}]}'
# A lone surrogate in a name is unencodable and must fail closed, not crash report.
SURROGATE='{"total_count":1,"check_runs":[{"status":"completed","conclusion":"success","name":"\ud800","app":{"slug":"github-actions"}}]}'
# A green reading with an EXTRA passing check: a different set than GA_PRESENT
# (both carry the required checks), used to exercise a changing-but-green set.
GA_PLUS_EXTRA="$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":"extra","app":{"slug":"github-actions"}}')"
# The real Cloudflare app on this repository, as its live check-runs show: slug
# cloudflare-workers-and-pages and app id 85455. The required-check match is exact.
REAL_CLOUDFLARE="$(runs "$REQ_GA" '{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85455}}')"
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
# Each malformed container is named for what it is, so none reaches a later step
# that would fail with another message.
run_err_case "a check-runs page that is not an object is named" '[{"check_runs":[]}]' 3 \
  "check read failed for 0000000000000000000000000000000000000000: check-runs page is not an object"
run_err_case "a check_runs object is named as not an array" "$NONARRAY" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check_runs is not an array"
run_err_case "a null check_runs is named as not an array" '{"check_runs":null}' 3 \
  "check read failed for 0000000000000000000000000000000000000000: check_runs is not an array"
run_err_case "a check run that is not an object is named" '{"check_runs":["completed"]}' 3 \
  "check read failed for 0000000000000000000000000000000000000000: a check run is not an object"
# A deeply nested payload triggers a parser RecursionError; it must be caught and
# reported as unreadable (exit 3), never escape as a crash/exit 1.
run_deep_case "deeply nested payload is rejected fail-closed" 3
# Duplicate JSON members must not hide a check -> fail-closed.
run_case "duplicate JSON keys are rejected fail-closed" "$DUP_KEY" "" "" 3
# The same holds inside the app object: a second id or slug would otherwise
# replace the first and could make a run of another app read as the pinned one.
run_err_case "duplicate id inside app is rejected fail-closed" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85456,"id":85455}}')" 3 \
  "duplicate JSON key 'id'"
run_err_case "duplicate slug inside app is rejected fail-closed" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages","slug":"cloudflare-workers-and-pages","id":85455}}')" 3 \
  "duplicate JSON key 'slug'"
# A declared total_count that exceeds the runs received is a truncated reading.
run_case "declared total_count truncation is rejected fail-closed" "$TRUNCATED" "" "" 3
# A non-ASCII digit passes str.isdigit() but int() would raise: reject as usage.
run_case "non-ASCII digit timeout is rejected as usage" "$GA_PRESENT" "" "" 3 --timeout ²
# Non-UTF-8 transport output is unreadable, not a failed check.
run_bytes_case "non-UTF-8 output is rejected fail-closed" 3
# With 2 seconds left and a gh that would end 60 seconds after it starts, this
# case asserts the kill at the deadline, 1002.0, and exit 3.
run_cut_off_case "gh read exceeding the wait deadline is not green" 2.000 "2.0 seconds"
# The required Cloudflare Pages check absent -> not green even with the 4 required
# github-actions checks green (a partial reading is not confirmed).
run_case "required Cloudflare check absent -> not green" "$MISSING_CLOUDFLARE" "" "" 2
# A duplicate check-run id must not pad the count to hide a run.
run_case "duplicate check-run id is rejected fail-closed" "$DUP_ID" "" "" 3
# total_count as an explicit null is malformed.
run_case "null total_count is rejected fail-closed" "$TOTAL_NULL" "" "" 3
# total_count present on only one page is inconsistent.
run_case "inconsistent total_count presence is rejected fail-closed" "$INCONSISTENT_TOTAL" "" "" 3
# A total_count of true is not a whole number, though Python treats a bool as
# the integer 1: read as 1, it would match the 1 run received.
run_err_case "boolean total_count is rejected fail-closed" \
  "{\"total_count\":true,\"check_runs\":[${PM_OK}]}" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check-runs total_count is not a whole number"
# Pages that declare different totals cannot both be right. The first page's
# total matches the 5 runs received, so a reader that kept only the first total
# would confirm this reading green.
run_err_case "pages declaring different total_count values are rejected fail-closed" \
  "{\"total_count\":5,\"check_runs\":[${PM_OK},${SD_OK}]}"$'\n'"{\"total_count\":6,\"check_runs\":[${APM_OK},${CST_OK},${CF}]}" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check-runs pages disagree on total_count"
# A declared total below the runs received means that the payload holds a run
# the API did not count, so it is as inconsistent as a truncated one. A reader
# that checked only for truncation would confirm this reading green.
run_err_case "declared total_count below the runs received is rejected fail-closed" \
  "{\"total_count\":4,\"check_runs\":[${REQ_GA},${CF}]}" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check-runs declared 4 runs but the reading received 5"
# A non-object app must not coerce to a null slug.
run_case "non-object app is rejected fail-closed" "$NONOBJ_APP" "" "" 3
# A lone surrogate in a name fails closed, it does not crash the report.
run_case "unencodable name is rejected fail-closed" "$SURROGATE" "" "" 3
run_err_case "an unencodable name is named on standard error" "$SURROGATE" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check field name is not encodable text"
# A nonzero gh exit with a green body on stdout is rejected by the returncode guard.
run_rc_case "green body with nonzero gh exit is rejected fail-closed" 3
# A gh that writes a green body and is then ended by a signal has no exit
# status; the tool reads that as returncode -1, which is never success.
run_rc_case "green body from a gh ended by a signal is rejected fail-closed" 3 'kill -KILL $$'
# In --wait mode a changing-but-green set must NOT give up at the changing-set cap
# while time remains; it keeps going and confirms once the set settles.
run_case "wait does not give up early on a changing green set" "$GA_PRESENT" "$GA_PLUS_EXTRA" "g a g a g a g g" 0 --wait --timeout 30
# A pass is confirmed only by a second reading identical in the conclusion, name
# and app slug of every run. Each pair below differs only in one of those
# fields of an extra run, and both readings are green; read in turn without
# --wait, they never confirm, and after 6 changing readings the tool gives up
# (exit 2). A reader that confirmed on any second green reading, or left a
# field out of the comparison, would read green (exit 0).
# extra_run CONCLUSION NAME SLUG: one completed run with those fields.
extra_run() {
  printf '{"status":"completed","conclusion":"%s","name":"%s","app":{"slug":"%s"}}' "$1" "$2" "$3"
}
changing="the set of checks kept changing across 6 readings; not calling this green"
CASE_NEEDLE="$changing" run_case "readings differing only in a conclusion do not confirm" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra github-actions)")" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run neutral extra github-actions)")" "g a g a g a" 2
CASE_NEEDLE="$changing" run_case "readings differing only in a name do not confirm" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra github-actions)")" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra2 github-actions)")" "g a g a g a" 2
CASE_NEEDLE="$changing" run_case "readings differing only in an app slug do not confirm" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra github-actions)")" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra other-app)")" "g a g a g a" 2
# A run that appears twice is in the set twice: a reading with a run duplicated
# and one with that run once are different sets, so they never confirm. A
# reader that compared the sets without duplicates would read green (exit 0).
CASE_NEEDLE="$changing" run_case "readings differing only in a duplicated run do not confirm" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra github-actions)" "$(extra_run success extra github-actions)")" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra github-actions)")" "g a g a g a" 2
# A nullable field that is null or absent reads as the empty string, so a
# reading that carries it and one that carries the empty string instead are the
# same set and confirm green (exit 0). A reader that read null as any other text
# would see the set change on every reading and give up (exit 2).
null_forms=(
  'a null name|"name":null,"app":{"slug":"github-actions"}|"name":"","app":{"slug":"github-actions"}'
  'no name|"app":{"slug":"github-actions"}|"name":"","app":{"slug":"github-actions"}'
  'a null app slug|"name":"x","app":{"slug":null}|"name":"x","app":{"slug":""}'
  'no app slug|"name":"x","app":{}|"name":"x","app":{"slug":""}'
  'a null app|"name":"x","app":null|"name":"x","app":{"slug":""}'
  'no app|"name":"x"|"name":"x","app":{"slug":""}'
)
for form in "${null_forms[@]}"; do
  IFS='|' read -r what as_null as_empty <<<"$form"
  run_case "an extra run with $what confirms against the empty value -> green" \
    "$(runs "$REQ_GA" "$CF" "{\"status\":\"completed\",\"conclusion\":\"success\",$as_null}")" \
    "$(runs "$REQ_GA" "$CF" "{\"status\":\"completed\",\"conclusion\":\"success\",$as_empty}")" "g a g a g a" 0
done
# The report on standard error gives a completed run its conclusion and an
# unfinished run its status.
CASE_NEEDLE="$(printf '  %-28s %s' extra neutral)" \
  run_case "the report gives a completed run its conclusion" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run success extra github-actions)")" \
  "$(runs "$REQ_GA" "$CF" "$(extra_run neutral extra github-actions)")" "g a g a g a" 2
# A wait that never settles ends at the deadline with the wait timing out (exit
# 2) only after a reading has succeeded, so in real time a first read that a
# loaded host keeps past the window exits 3 instead. The 2 cases below therefore
# run on the fake clock of run_clock_case, where each read takes 0.5 seconds:
# with --timeout 4 the 3 reads end at 1000.5, 1002.0 and 1003.5, none of them on
# the deadline 1004.0, the top-of-loop guard ends the wait, and gh is never
# killed.
WAIT_TIMED_OUT="still unsettled after 4 seconds; giving up"
CASE_NEEDLE="$(printf '  %-28s %s' "Plugin manifests" in_progress)"$'\n'"${WAIT_TIMED_OUT}" CASE_NO_KILL=1 \
  run_clock_case "the report gives an unfinished run its status" "$GA_IN_PROGRESS" "" "g" 2 --wait --timeout 4
# A zero-length wait window fails closed rather than overrunning the deadline.
run_case "zero-timeout wait window fails closed" "$GA_IN_PROGRESS" "" "" 3 --wait --timeout 0
CASE_NEEDLE="check read failed for 0000000000000000000000000000000000000000: the wait window closed before the read" \
  run_case "zero-timeout wait window says it closed before the read" "$GA_IN_PROGRESS" "" "" 3 --wait --timeout 0
# The real Cloudflare app (slug cloudflare-workers-and-pages, app id 85455)
# satisfies the required Cloudflare check -> green (regression: a pin on a slug or
# id that the live check-runs do not show would false-red every real commit).
run_case "real cloudflare-workers-and-pages slug satisfies the required check" "$REAL_CLOUDFLARE" "" "" 0
# With --timeout 10 and --interval 30, this case asserts that a pending wait
# exits at 1010.0, not a whole interval past it. The fake clock of
# run_deadline_stop_case, not the elapsed time, says when it stopped, and no
# step of that case waits in real time.
run_deadline_stop_case "wait stops near the deadline, not a whole interval past it"

# The required set is the 4 named GitHub Actions jobs and the Cloudflare
# build. An Actions job counts only when a run carries its exact display name and
# the github-actions app slug; every run, duplicates included, still feeds the
# verdict.
run_case "unnamed github-actions run is not a required check -> not green" "$GENERIC_GA" "" "" 2
run_case "Plugin manifests missing -> not green" "$(runs "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 2
run_case "Skill discovery missing -> not green" "$(runs "$PM_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 2
run_case "Agent Plugins manifest missing -> not green" "$(runs "$PM_OK" "$SD_OK" "$CST_OK" "$CF")" "" "" 2
run_case "CI status tests missing -> not green" "$(runs "$PM_OK" "$SD_OK" "$APM_OK" "$CF")" "" "" 2
run_err_case "a missing required check is named on standard error" "$(runs "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" 2 \
  "required check(s) Plugin manifests not registered"
run_case "required name from another app does not count -> not green" \
  "$(runs '{"status":"completed","conclusion":"success","name":"Plugin manifests","app":{"slug":"evil-app"}}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF" \
  '{"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}}')" "" "" 2
run_case "required name with a null app does not count -> not green" \
  "$(runs '{"status":"completed","conclusion":"success","name":"Plugin manifests","app":null}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 2
run_case "required name in another letter case does not count -> not green" \
  "$(runs '{"status":"completed","conclusion":"success","name":"plugin manifests","app":{"slug":"github-actions"}}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 2
run_case "required name with a trailing space does not count -> not green" \
  "$(runs "$PM_OK" '{"status":"completed","conclusion":"success","name":"Skill discovery ","app":{"slug":"github-actions"}}' "$APM_OK" "$CST_OK" "$CF")" "" "" 2
CASE_NEEDLE="$(printf '  %-28s %s' "Plugin manifests" in_progress)"$'\n'"${WAIT_TIMED_OUT}" CASE_NO_KILL=1 \
  run_clock_case "unfinished required check with --wait stays not green at the deadline" \
  "$GA_IN_PROGRESS" "" "g" 2 --wait --timeout 4
# A read that the deadline cuts off after a reading that succeeded and was still
# unsettled is the wait timing out (exit 2), not an unreadable result (exit 3): a
# loaded host can start a read with little of the window left. The plan token s
# is a gh call that hangs until the tool ends it at the deadline.
# These cases run on the fake clock of run_clock_case, because in real time the
# earlier reads and the 1-second sleeps between them must all fit inside the
# 5-second window, which a heavily loaded host can exceed before the hanging
# call starts. Each case requires the line naming the cut-off of that hanging
# call, and requires the fake gh to have served it (CASE_READS), so a gate
# whose window runs out before that call starts fails rather than passing
# through the top-of-loop guard or the closed-window check before the read.
# After a failed read, a read cut off at the deadline still reports the read
# failure (exit 3), and so does one after a good reading and then a failed
# read.
CUT_OFF="ci-status: the wait window cut off the last read (gh api did not return within"
HUNG_READ_FAILED="check read failed for 0000000000000000000000000000000000000000: gh api did not return within"
CASE_NEEDLE="${CUT_OFF}"$'\n'"still unsettled after 5 seconds; giving up" \
  CASE_ABSENT="check read failed" CASE_READS=2 \
  run_clock_case "pending reading then a read cut off at the deadline -> not green, timed out" \
  "$GA_IN_PROGRESS" "" "g s" 2 --wait --timeout 5
CASE_NEEDLE="${CUT_OFF}"$'\n'"still unsettled after 5 seconds; giving up" \
  CASE_ABSENT="check read failed" CASE_READS=2 \
  run_clock_case "green reading then a confirmation read cut off at the deadline -> not green, timed out" \
  "$GA_PRESENT" "" "g s" 2 --wait --timeout 5
CASE_NEEDLE="$HUNG_READ_FAILED" CASE_ABSENT="still unsettled" CASE_READS=2 \
  run_clock_case "failed read then a read cut off at the deadline -> unreadable" \
  "$GA_PRESENT" "" "f s" 3 --wait --timeout 5
CASE_NEEDLE="$HUNG_READ_FAILED" CASE_ABSENT="still unsettled" CASE_READS=3 \
  run_clock_case "pending reading, a failed read, then a read cut off at the deadline -> unreadable" \
  "$GA_IN_PROGRESS" "" "g f s" 3 --wait --timeout 5
# An empty reading (no checks) is a successful reading too, so a read cut off at
# the deadline after it is the wait timing out (exit 2), as the top-of-loop guard
# gives for the same reading.
CASE_NEEDLE="${CUT_OFF}"$'\n'"still unsettled after 5 seconds; giving up" \
  CASE_ABSENT="check read failed" CASE_READS=2 \
  run_clock_case "empty reading then a read cut off at the deadline -> not green, timed out" \
  '{"total_count":0,"check_runs":[]}' "" "g s" 2 --wait --timeout 5
# Without --wait, the confirmation read after a green reading is the only second
# read, and it is bounded by the same deadline. A cut-off there keeps its old
# result, the read failure (exit 3), not a timed-out wait.
CASE_NEEDLE="$HUNG_READ_FAILED" CASE_ABSENT="still unsettled" CASE_READS=2 \
  run_clock_case "green reading then a confirmation read cut off without --wait -> unreadable" \
  "$GA_PRESENT" "" "g s" 3 --timeout 5
# The fake clock above starts and kills no real process, so this case runs a
# real hung gh that is killed and reaped. Its first read hangs, so the tool
# must start that 1 gh call inside the 5-second window, and the fake gh must
# start and record its read (CASE_READS) before the tool kills it at the
# deadline.
CASE_NEEDLE="$HUNG_READ_FAILED" CASE_ABSENT="still unsettled" CASE_READS=1 \
  run_case "a real gh that hangs from the first read is killed and reaped -> unreadable" \
  "$GA_PRESENT" "" "s" 3 --wait --timeout 5
run_cut_off_case "a read cut off with under a second left names its real bound" 0.500 "0.5 seconds"
run_cut_off_case "a read cut off with 1.96 seconds left names 1.9 seconds, not a longer bound" \
  1.960 "1.9 seconds"
run_cut_off_case "a read cut off with under 0.1 seconds left is not named as 0 seconds" \
  0.040 "the time left (under 0.1 seconds)"
# With 0.03 seconds left, this case asserts the kill at 1002.0; a last poll
# that sleeps a whole 0.02 seconds kills at 1002.01.
run_cut_off_case "a read cut off with 0.03 seconds left is killed at the deadline, not a poll after it" \
  0.030 "the time left (under 0.1 seconds)"
# With a 1-second start, this case asserts the kill at 1002.0; a bound whose
# clock starts after Popen kills at 1003.0 here.
run_cut_off_case "a read whose gh takes 1 second to start is still killed at the deadline" \
  2.000 "2.0 seconds" 1.000
# With a 3-second start and 2 seconds left, gh is still running when Popen
# returns at 1003.0; this case asserts that gh is killed then and that the
# message names 2.0 seconds.
run_cut_off_case "a read whose gh start outlasts the time left is killed once Popen returns, after the deadline" \
  2.000 "2.0 seconds" 3.000 1003.0
# With time.time standing still from the start of the read until _gh returns,
# this case asserts the kill at 1002.0.
run_cut_off_case "a read is killed at its deadline while the wall clock stands still" \
  2.000 "2.0 seconds" 0 1002.0 1
run_case "failed required check -> red" \
  "$(runs '{"status":"completed","conclusion":"failure","name":"Plugin manifests","app":{"slug":"github-actions"}}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 1
run_case "failing impostor of a required name beside the full set -> red" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"failure","name":"Skill discovery","app":{"slug":"evil-app"}}')" "" "" 1
run_case "failing other run while a required check is missing -> red" \
  "$(runs "$PM_OK" "$SD_OK" "$CST_OK" "$CF" '{"status":"completed","conclusion":"failure","name":"check","app":{"slug":"github-actions"}}')" "" "" 1
# The failing run has the lower id and comes first, so collapsing duplicates to
# the latest or highest-id run would hide it; every run must still count.
run_case "duplicate required run with an earlier one failing -> red" \
  "$(runs "$PM_OK" '{"id":1,"status":"completed","conclusion":"failure","name":"Skill discovery","app":{"slug":"github-actions"}}' \
  "{\"id\":2,${SD_OK#\{}" "$APM_OK" "$CST_OK" "$CF")" "" "" 1
run_case "duplicate required run with both passing -> green" "$(runs "$PM_OK" "$SD_OK" "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 0
# The first reading lacks Agent Plugins manifest and must be reported as that
# required check not registered, not taken as the first of 2 green readings.
CASE_NEEDLE="required check(s) Agent Plugins manifest not registered" \
  run_case "required check that registers late is waited for -> green" \
  "$GA_PRESENT" "$(runs "$PM_OK" "$SD_OK" "$CST_OK" "$CF")" "a g g" 0 --wait --timeout 30
# The downgrade holds on every reading, not only until the first green one: a
# reading that lacks a required check after a green reading, whether it is the
# confirmation reading or a later reading of a wait, is not green, and the check
# is named. A reader that downgraded only before the first green reading would
# confirm the 2 later readings green (exit 0). The 2 cases of a wait read a red
# reading after the 2 that lack the check, so they end at once (exit 1) rather
# than when the window closes, and their result does not depend on how long the
# reads take.
CASE_NEEDLE="required check(s) Plugin manifests not registered" \
  run_case "required check missing from the confirmation reading -> not green" \
  "$GA_PRESENT" "$(runs "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "g a a" 2
CASE_NEEDLE="required check(s) Plugin manifests not registered" CASE_THIRD="$GA_RED" \
  run_case "required check missing from later readings of a wait -> not green" \
  "$GA_PRESENT" "$(runs "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "g a a t" 1 --wait --timeout 30
CASE_NEEDLE="required check(s) Cloudflare Pages not registered" CASE_THIRD="$GA_RED" \
  run_case "Cloudflare build missing from later readings of a wait -> not green" \
  "$GA_PRESENT" "$(runs "$REQ_GA")" "g a a t" 1 --wait --timeout 30
# The missing-check message belongs to a passing reading alone: a pending or red
# reading that also lacks a required check is reported as pending or red, and
# the message is not written.
CASE_ABSENT="not registered" run_case "pending reading lacking a required check does not name it" \
  "$(runs '{"status":"in_progress","conclusion":null,"name":"Plugin manifests","app":{"slug":"github-actions"}}' "$SD_OK" "$APM_OK" "$CST_OK")" "" "" 2
CASE_ABSENT="not registered" run_case "red reading lacking a required check does not name it" \
  "$(runs '{"status":"completed","conclusion":"failure","name":"Plugin manifests","app":{"slug":"github-actions"}}' "$SD_OK" "$APM_OK" "$CST_OK")" "" "" 1
# The downgrade holds at every reading size: a reading of 6, 12, 100 or 300
# runs, the extra runs all green, still lacks Plugin manifests and is not green.
# many_runs N: Skill discovery, Agent Plugins manifest, CI status tests and the
# Cloudflare build, green, then N - 4 green extra runs named extra 5 to extra N.
many_runs() {
  local i out=("$SD_OK" "$APM_OK" "$CST_OK" "$CF")
  for ((i = 5; i <= $1; i++)); do
    out+=("{\"status\":\"completed\",\"conclusion\":\"success\",\"name\":\"extra $i\",\"app\":{\"slug\":\"github-actions\"}}")
  done
  runs "${out[@]}"
}
for size in 6 12 100 300; do
  CASE_NEEDLE="required check(s) Plugin manifests not registered" \
    run_case "reading of $size runs missing a required check -> not green" "$(many_runs "$size")" "" "" 2
done
run_case "Cloudflare build under another name is matched by its app slug and app id -> green" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"success","name":"Pages build","app":{"slug":"cloudflare-workers-and-pages","id":85455}}')" "" "" 0
# A green commit status is never read: the only gh call is the check-runs read.
run_log_case "a green commit status never stands in for a missing required check" "$(runs "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" 2
run_log_case "a green reading makes only the paginated check-runs call" "$GA_PRESENT" 0
# A present head_sha must name the commit read; absence is tolerated.
run_case "head_sha of another commit on one run -> unreadable" \
  "$(runs "{\"head_sha\":\"$C2\",${PM_OK#\{}" "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 3
run_case "head_sha equal to the commit read -> green" "$(head_runs '"0000000000000000000000000000000000000000"')" "" "" 0
CASE_SHA="$C1_UPPER" run_case "head_sha matches an upper-case sha argument -> green" "$(head_runs "\"$C1\"")" "" "" 0
CASE_SHA="$C1" run_case "upper-case head_sha matches the commit read -> green" "$(head_runs "\"$C1_UPPER\"")" "" "" 0
run_case "numeric head_sha -> unreadable" "$(head_runs 7)" "" "" 3
run_case "null head_sha -> unreadable" "$(head_runs null)" "" "" 3
# head_sha is not a required field (its absence is tolerated), so a present null
# or empty head_sha is reported as null or empty, never as a missing required field.
run_err_case "a null head_sha is named on standard error" "$(head_runs null)" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check field head_sha is null"
run_case "empty head_sha -> unreadable" "$(head_runs '""')" "" "" 3
run_err_case "an empty head_sha is named on standard error" "$(head_runs '""')" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check field head_sha is empty"
run_err_case "a numeric head_sha is named on standard error" "$(head_runs 7)" 3 \
  "check read failed for 0000000000000000000000000000000000000000: non-string check field head_sha"
run_err_case "a head_sha of another commit is named on standard error" \
  "$(runs "{\"head_sha\":\"$C2\",${PM_OK#\{}" "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check run head_sha '$C2' is not the requested commit 0000000000000000000000000000000000000000"
# head_sha is checked after the id and the app object of its run and before its
# status, conclusion, name and app slug, so a run whose status is null or absent
# is reported by its head_sha.
for st in null absent; do
  st_field=""
  if [ "$st" = null ]; then st_field='"status":null,'; fi
  run_err_case "head_sha of another commit on a run whose status is $st is named" \
    "{\"check_runs\":[{\"head_sha\":\"$C2\",${st_field}\"conclusion\":\"success\",\"name\":\"x\",\"app\":{\"slug\":\"github-actions\"}}]}" 3 \
    "check read failed for 0000000000000000000000000000000000000000: check run head_sha '$C2' is not the requested commit"
done
# head_sha is compared as the whole 40-character sha, folded to lower case and
# nothing else: an abbreviation, a trailing or middle slice, a value padded on
# both sides or on one, a value that has the commit as a prefix or a suffix, the
# sha with a separator inserted, before it or after it, or with 0x before it, and
# the zero sha on a read of another commit each name another value, so the
# reading is unreadable.
CASE_SHA="$C1" run_case "head_sha abbreviated to 7 characters -> unreadable" "$(head_runs "\"${C1:0:7}\"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha abbreviated to 39 characters -> unreadable" "$(head_runs "\"${C1:0:39}\"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha padded with spaces -> unreadable" "$(head_runs "\" $C1 \"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha with a trailing newline -> unreadable" "$(head_runs "\"$C1\\n\"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha with the commit as a prefix -> unreadable" "$(head_runs "\"${C1}0\"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha with the commit as a suffix -> unreadable" "$(head_runs "\"0${C1}\"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha with a leading space only -> unreadable" "$(head_runs "\" $C1\"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha holding the last 7 characters -> unreadable" "$(head_runs "\"${C1:33}\"")" "" "" 3
CASE_SHA="$C1" run_case "head_sha holding a middle slice -> unreadable" "$(head_runs "\"${C1:10:20}\"")" "" "" 3
for sep in - " " _ : .; do
  CASE_SHA="$C1" run_case "head_sha with [$sep] inserted -> unreadable" "$(head_runs "\"${C1:0:20}${sep}${C1:20}\"")" "" "" 3
  CASE_SHA="$C1" run_case "head_sha with [$sep] before it -> unreadable" "$(head_runs "\"${sep}${C1}\"")" "" "" 3
  CASE_SHA="$C1" run_case "head_sha with [$sep] after it -> unreadable" "$(head_runs "\"${C1}${sep}\"")" "" "" 3
done
CASE_SHA="$C1" run_case "head_sha with 0x before it -> unreadable" "$(head_runs "\"0x$C1\"")" "" "" 3
CASE_SHA="$C1" run_case "zero head_sha on a read of another commit -> unreadable" \
  "$(head_runs '"0000000000000000000000000000000000000000"')" "" "" 3
# U+FB00, the ff ligature, is the one character whose upper case (FF) or case fold
# (ff) is hexadecimal while its lower case is not, so a head_sha that spells ff
# with it names another value only when head_sha is folded to lower case.
CASE_SHA="ff${C1:2}" run_case "head_sha spelling ff with the U+FB00 ligature -> unreadable" \
  "$(head_runs "\"\\ufb00${C1:2}\"")" "" "" 3
# The status field is required: an absent status and a present null status are
# each named for what they are, as are an empty status and a non-string
# conclusion or app slug.
run_err_case "an absent status is named as a missing required field" \
  '{"check_runs":[{"conclusion":"success","name":"x","app":{"slug":"github-actions"}}]}' 3 \
  "check read failed for 0000000000000000000000000000000000000000: missing required field status"
run_err_case "a null status is named as null" "$NULL_STATUS" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check field status is null"
run_err_case "an empty status is named as empty" "$EMPTY_STATUS" 3 \
  "check read failed for 0000000000000000000000000000000000000000: check field status is empty"
run_err_case "a non-string conclusion is named on standard error" \
  '{"check_runs":[{"status":"completed","conclusion":1,"name":"x","app":{"slug":"github-actions"}}]}' 3 \
  "check read failed for 0000000000000000000000000000000000000000: non-string check field conclusion"
run_err_case "a non-string name is named on standard error" \
  '{"check_runs":[{"status":"completed","conclusion":"success","name":7,"app":{"slug":"github-actions"}}]}' 3 \
  "check read failed for 0000000000000000000000000000000000000000: non-string check field name"
run_err_case "a non-string app slug is named on standard error" \
  '{"check_runs":[{"status":"completed","conclusion":"success","name":"x","app":{"slug":7}}]}' 3 \
  "check read failed for 0000000000000000000000000000000000000000: non-string check field app.slug"
# conclusion, name, app.slug and the app object are nullable: each, null or absent
# on an extra run beside the 5 green required checks, reads as an empty value,
# never as a malformed reading. A completed run with no conclusion is a failure,
# so the conclusion cases use an unfinished run, which reads pending (exit 2).
run_case "extra run with a null name -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":null,"app":{"slug":"github-actions"}}')" "" "" 0
run_case "extra run with no name -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","app":{"slug":"github-actions"}}')" "" "" 0
run_case "extra run with a null app slug -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":"x","app":{"slug":null}}')" "" "" 0
run_case "extra run with no app slug -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":"x","app":{}}')" "" "" 0
run_case "extra run with a null app -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":"x","app":null}')" "" "" 0
run_case "extra run with no app -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":"x"}')" "" "" 0
run_case "unfinished extra run with a null conclusion -> not green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"in_progress","conclusion":null,"name":"x","app":{"slug":"github-actions"}}')" "" "" 2
run_case "unfinished extra run with no conclusion -> not green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"queued","name":"x","app":{"slug":"github-actions"}}')" "" "" 2
# An empty name, conclusion or app slug is accepted on these nullable fields: an
# extra run that carries one reads it as that empty value, never as a malformed
# reading. A completed run with an empty conclusion is a failure.
run_case "extra run with an empty name -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":"","app":{"slug":"github-actions"}}')" "" "" 0
run_case "extra run with an empty app slug -> green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"success","name":"x","app":{"slug":""}}')" "" "" 0
run_case "unfinished extra run with an empty conclusion -> not green" \
  "$(runs "$REQ_GA" "$CF" '{"status":"in_progress","conclusion":"","name":"x","app":{"slug":"github-actions"}}')" "" "" 2
run_case "completed extra run with an empty conclusion -> red" \
  "$(runs "$REQ_GA" "$CF" '{"status":"completed","conclusion":"","name":"x","app":{"slug":"github-actions"}}')" "" "" 1
# Only an empty status is malformed: a status of whitespace alone is a status
# other than completed, so its run is unfinished and the reading pending.
run_case "extra run with a whitespace-only status -> not green" \
  "$(runs "$REQ_GA" "$CF" '{"status":" ","conclusion":"success","name":"x","app":{"slug":"github-actions"}}')" "" "" 2
# A Plugin manifests run whose name is null reads as an unnamed run, so the
# required check is missing rather than the reading malformed.
CASE_NEEDLE="required check(s) Plugin manifests not registered" \
  run_case "Plugin manifests run with a null name does not count -> not green" \
  "$(runs '{"status":"completed","conclusion":"success","name":null,"app":{"slug":"github-actions"}}' "$SD_OK" "$APM_OK" "$CST_OK" "$CF")" "" "" 2

# Every per-run check applies to every run, not only to the first or the last.
# For a head_sha of another commit and for each malformed field, bad_at puts the
# bad value on one run alone, at each index of a 6-run reading in turn, so a
# reader that checked only some runs would read it as green, pending or red, or
# fail with another message; the whole reading must be unreadable, and the
# message names what is wrong.
# bad_at FIELD VALUE INDEX: the 5 green required checks and a green extra run, in
# that order, with FIELD of the run at INDEX (0 to 5) set to the raw JSON VALUE.
# FIELD is status, conclusion, name, app.slug, app.id, app (the whole app object)
# or head_sha, which is added to that run alone. Any other INDEX changes no run. Each
# run is NAME|SLUG|ID; the Cloudflare run carries the app id 85455, the others none.
bad_at() {
  local i=0 spec st cn nm app hs slug id out=()
  for spec in "Plugin manifests|github-actions|" "Skill discovery|github-actions|" \
    "Agent Plugins manifest|github-actions|" "CI status tests|github-actions|" \
    "Cloudflare Pages|cloudflare-workers-and-pages|85455" "extra|github-actions|"; do
    slug="${spec#*|}" id="${spec##*|}"
    slug="${slug%|*}"
    st='"completed"' cn='"success"' nm="\"${spec%%|*}\"" app="{\"slug\":\"${slug}\"${id:+,\"id\":$id}}" hs=""
    if [ "$i" -eq "$3" ]; then
      case "$1" in
        status) st="$2" ;;
        conclusion) cn="$2" ;;
        name) nm="$2" ;;
        app.slug) app="{\"slug\":$2${id:+,\"id\":$id}}" ;;
        app.id) app="{\"slug\":\"${slug}\",\"id\":$2}" ;;
        app) app="$2" ;;
        head_sha) hs="\"head_sha\":$2," ;;
      esac
    fi
    out+=("{${hs}\"status\":${st},\"conclusion\":${cn},\"name\":${nm},\"app\":${app}}")
    i=$((i + 1))
  done
  runs "${out[@]}"
}
run_case "the bad_at reading with no run changed -> green" "$(bad_at status null 6)" "" "" 0
read_failed="check read failed for 0000000000000000000000000000000000000000"
for idx in 0 1 2 3 4 5; do
  run_err_case "head_sha of another commit on run $idx alone -> unreadable" "$(bad_at head_sha "\"$C2\"" "$idx")" 3 \
    "$read_failed: check run head_sha '$C2' is not the requested commit 0000000000000000000000000000000000000000"
  run_err_case "null status on run $idx alone -> unreadable" "$(bad_at status null "$idx")" 3 \
    "$read_failed: check field status is null"
  run_err_case "non-string conclusion on run $idx alone -> unreadable" "$(bad_at conclusion 1 "$idx")" 3 \
    "$read_failed: non-string check field conclusion"
  run_err_case "non-string name on run $idx alone -> unreadable" "$(bad_at name 7 "$idx")" 3 \
    "$read_failed: non-string check field name"
  run_err_case "non-string app slug on run $idx alone -> unreadable" "$(bad_at app.slug 7 "$idx")" 3 \
    "$read_failed: non-string check field app.slug"
  run_err_case "non-object app on run $idx alone -> unreadable" "$(bad_at app '[]' "$idx")" 3 \
    "$read_failed: check run app is not an object"
  run_err_case "non-integer app id on run $idx alone -> unreadable" "$(bad_at app.id '"9"' "$idx")" 3 \
    "$read_failed: check run app.id is not an integer"
  run_err_case "boolean false app id on run $idx alone -> unreadable" "$(bad_at app.id false "$idx")" 3 \
    "$read_failed: check run app.id is not an integer"
done
# A status that is a JSON array or object is not a string, whatever it holds.
for bad in '[]' '{}' '["completed"]'; do
  run_err_case "status $bad on an extra run -> unreadable" "$(bad_at status "$bad" 5)" 3 \
    "$read_failed: non-string check field status"
done
# Only success, neutral and skipped can pass: a required check that concludes
# cancelled, stale, action_required, timed_out or startup_failure is red, never
# green.
for concl in cancelled stale action_required timed_out startup_failure; do
  run_case "required check concluding $concl -> red" "$(bad_at conclusion "\"$concl\"" 0)" "" "" 1
done
# A required GitHub Actions job passes only on success: each of the 4, runs 0 to
# 3 of bad_at, in turn concluding skipped or neutral, beside the other 4
# required checks green, reads red, because such a job may not have run its
# steps. The Cloudflare build, run 4, keeps the reading GitHub gives a required
# check: concluding skipped or neutral, it passes (the residual the ci-status.py
# docstring discloses).
for concl in skipped neutral; do
  for idx in 0 1 2 3; do
    run_case "required Actions job $idx concluding $concl beside the other 4 green -> red" \
      "$(bad_at conclusion "\"$concl\"" "$idx")" "" "" 1
  done
  run_case "Cloudflare build concluding $concl beside the other 4 green -> green" \
    "$(bad_at conclusion "\"$concl\"" 4)" "" "" 0
done
# A run counts as finished only when its status is completed: a queued or
# in-progress required run that already carries the conclusion success is still
# running, so the reading is pending, not green.
for st in queued in_progress; do
  run_case "$st required check carrying the conclusion success -> not green" \
    "$(bad_at status "\"$st\"" 0)" "" "" 2
done
# The status and the conclusion are compared in their exact letter case: a
# required run whose status is COMPLETED or Completed has not finished, so the
# reading is pending, and one that concludes Success or SUCCESS has not passed,
# so the reading is red. A reader that folded either to lower case would read
# green (exit 0).
for st in COMPLETED Completed; do
  run_case "required check with the status $st and the conclusion success -> not green" \
    "$(bad_at status "\"$st\"" 0)" "" "" 2
done
for concl in Success SUCCESS; do
  run_case "completed required check concluding $concl -> red" "$(bad_at conclusion "\"$concl\"" 0)" "" "" 1
done
# A failed run outranks an unfinished one, so a reading that holds both is red,
# not pending.
run_case "failed run beside an unfinished run -> red" \
  "$(runs '{"status":"completed","conclusion":"failure","name":"Plugin manifests","app":{"slug":"github-actions"}}' \
  '{"status":"in_progress","conclusion":null,"name":"Skill discovery","app":{"slug":"github-actions"}}' "$APM_OK" "$CST_OK" "$CF")" "" "" 1
# A reading with no check runs is unreadable, never a pass or pending, and both
# lines of the report say so.
run_err_case "empty check_runs is unreadable and says no checks are recorded" '{"total_count":0,"check_runs":[]}' 3 \
  "ci-status: no checks are recorded for 0000000000000000000000000000000000000000 in owner/name"
run_err_case "empty check_runs is not treated as a pass" '{"total_count":0,"check_runs":[]}' 3 \
  "ci-status: treating absent checks as unreadable, not as a pass"

# Every per-run check applies whatever the other fields of its run hold. A real
# check run always carries a large integer id and the head_sha of its commit, so
# the decisive run below carries the id 31234567890, and it follows the 5 green
# required checks, the first of them with the id 31234567880. Each check is made
# on that run with one other field of it changed in turn: the id left out,
# head_sha naming the commit read, each status, each conclusion, each form of the
# app and its slug, and each form of the name, except the field the check reads.
# Each check is also made with the field combinations a real run carries: an
# in-progress or queued run with a null conclusion, with and without head_sha
# naming the commit read, and a completed run with head_sha naming the commit
# read and each conclusion. A context that sets the field the check reads is used
# without that field. A reader that made a check only when other fields of the
# same run held some values, or were present or absent, would read such a
# reading green, pending or red, or fail with another message; the whole reading
# must be unreadable, and the message names what is wrong. A null or absent
# status is itself unreadable, so those 2 forms are used only for the checks made
# before the status is read: the id, the app object and head_sha.
# gated_run FIELD=RAW...: a completed, successful github-actions run named extra
# with the id 31234567890 and no head_sha, with each FIELD set to the raw JSON
# RAW, or left out when RAW is absent; a later FIELD=RAW replaces an earlier one.
# FIELD is id, head_sha, status, conclusion, name or app (the whole app object);
# an empty argument changes nothing, and any other FIELD prints nothing and
# fails.
gate_id=31234567890
gate_pm_id=31234567880
gated_run() {
  local id="$gate_id" hs=absent st='"completed"' cn='"success"' nm='"extra"' app='{"slug":"github-actions"}'
  local spec k v out=()
  for spec in "$@"; do
    [ -n "$spec" ] || continue
    k="${spec%%=*}" v="${spec#*=}"
    [ "$k" != "$spec" ] || return 1
    case "$k" in
      id) id="$v" ;;
      head_sha) hs="$v" ;;
      status) st="$v" ;;
      conclusion) cn="$v" ;;
      name) nm="$v" ;;
      app) app="$v" ;;
      *) return 1 ;;
    esac
  done
  for spec in "id|$id" "head_sha|$hs" "status|$st" "conclusion|$cn" "name|$nm" "app|$app"; do
    [ "${spec#*|}" = absent ] || out+=("\"${spec%%|*}\":${spec#*|}")
  done
  local IFS=,
  printf '{%s}' "${out[*]}"
}
# Each context is a list of FIELD=RAW changes separated by semicolons.
gate_head='head_sha="0000000000000000000000000000000000000000"'
gate_ctx=("" id=absent "$gate_head"
  'status="in_progress"' 'status="queued"' status=null status=absent
  'conclusion="failure"' 'conclusion="neutral"' 'conclusion="skipped"' 'conclusion="cancelled"'
  conclusion=null conclusion=absent
  'app={"slug":"cloudflare-workers-and-pages","id":85455}' 'app={"slug":"other-app"}' 'app={"slug":null}' 'app={}' app=null app=absent
  'name="Plugin manifests"' 'name=""' name=null name=absent
  'status="in_progress";conclusion=null' 'status="queued";conclusion=null'
  "$gate_head;status=\"in_progress\";conclusion=null" "$gate_head;status=\"queued\";conclusion=null"
  "$gate_head;conclusion=\"failure\"" "$gate_head;conclusion=\"neutral\"" "$gate_head;conclusion=\"skipped\""
  "$gate_head;conclusion=\"cancelled\"" "$gate_head;conclusion=null")
# The realistic contexts: a run as the API returns it, finished or not.
gate_real=("" "$gate_head" "$gate_head;status=\"in_progress\";conclusion=null"
  "$gate_head;status=\"queued\";conclusion=null" "$gate_head;conclusion=\"failure\"")
# FIELD|WHAT|BAD|MESSAGE|WHEN: the check of FIELD, the bad value BAD given to
# gated_run, the message it gives, and whether it is made before the status is
# read (early) or after (late). gate_checks holds one bad value per check, made
# in every context; gate_bad holds every other bad value of each check, made in
# the realistic contexts.
gate_checks=(
  "head_sha|head_sha of another commit|head_sha=\"$C2\"|check run head_sha '$C2' is not the requested commit 0000000000000000000000000000000000000000|early"
  "id|a non-integer id|id=\"31234567890\"|check run id is not an integer|early"
  "id|the id of run 1 repeated|id=$gate_pm_id|duplicate check run id|early"
  "app|a non-object app|app=[]|check run app is not an object|early"
  "app|a non-integer app id|app={\"slug\":\"github-actions\",\"id\":\"9\"}|check run app.id is not an integer|early"
  "status|a null status|status=null|check field status is null|late"
  "conclusion|a non-string conclusion|conclusion=1|non-string check field conclusion|late"
  "name|a non-string name|name=7|non-string check field name|late"
  "app|a non-string app slug|app={\"slug\":7}|non-string check field app.slug|late"
)
gate_bad=(
  "head_sha|a numeric head_sha|head_sha=7|non-string check field head_sha|early"
  "head_sha|a null head_sha|head_sha=null|check field head_sha is null|early"
  "head_sha|an empty head_sha|head_sha=\"\"|check field head_sha is empty|early"
  "head_sha|a boolean head_sha|head_sha=true|non-string check field head_sha|early"
  "head_sha|an array head_sha|head_sha=[]|non-string check field head_sha|early"
  "head_sha|an object head_sha|head_sha={}|non-string check field head_sha|early"
  "head_sha|an unencodable head_sha|head_sha=\"\\ud800\"|check field head_sha is not encodable text|early"
  "head_sha|head_sha with a hyphen before it|head_sha=\"-0000000000000000000000000000000000000000\"|check run head_sha '-0000000000000000000000000000000000000000' is not the requested commit|early"
  "head_sha|head_sha with a hyphen after it|head_sha=\"0000000000000000000000000000000000000000-\"|check run head_sha '0000000000000000000000000000000000000000-' is not the requested commit|early"
  "id|the id 9.0|id=9.0|check run id is not an integer|early"
  "id|the id 31234567890.0|id=31234567890.0|check run id is not an integer|early"
  "id|the id 9e0|id=9e0|check run id is not an integer|early"
  "id|the id 9.5|id=9.5|check run id is not an integer|early"
  "id|the id -9.0|id=-9.0|check run id is not an integer|early"
  "id|the id 1E400|id=1E400|check run id is not an integer|early"
  "id|a true id|id=true|check run id is not an integer|early"
  "id|a false id|id=false|check run id is not an integer|early"
  "id|an empty string id|id=\"\"|check run id is not an integer|early"
  "id|an array id|id=[]|check run id is not an integer|early"
  "id|an object id|id={}|check run id is not an integer|early"
  "app|a string app|app=\"github-actions\"|check run app is not an object|early"
  "app|an empty string app|app=\"\"|check run app is not an object|early"
  "app|a numeric app|app=1|check run app is not an object|early"
  "app|a zero app|app=0|check run app is not an object|early"
  "app|a true app|app=true|check run app is not an object|early"
  "app|a false app|app=false|check run app is not an object|early"
  "status|an absent status|status=absent|missing required field status|late"
  "status|an empty status|status=\"\"|check field status is empty|late"
  "status|a numeric status|status=1|non-string check field status|late"
  "status|a boolean status|status=true|non-string check field status|late"
  "status|an array status|status=[]|non-string check field status|late"
  "status|an object status|status={}|non-string check field status|late"
  "status|an unencodable status|status=\"\\ud800\"|check field status is not encodable text|late"
  "conclusion|a boolean conclusion|conclusion=true|non-string check field conclusion|late"
  "conclusion|a false conclusion|conclusion=false|non-string check field conclusion|late"
  "conclusion|an array conclusion|conclusion=[]|non-string check field conclusion|late"
  "conclusion|an object conclusion|conclusion={}|non-string check field conclusion|late"
  "conclusion|an unencodable conclusion|conclusion=\"\\ud800\"|check field conclusion is not encodable text|late"
  "name|a boolean name|name=true|non-string check field name|late"
  "name|a false name|name=false|non-string check field name|late"
  "name|an array name|name=[]|non-string check field name|late"
  "name|an object name|name={}|non-string check field name|late"
  "name|an unencodable name|name=\"\\ud800\"|check field name is not encodable text|late"
  "app|a boolean app slug|app={\"slug\":true}|non-string check field app.slug|late"
  "app|a false app slug|app={\"slug\":false}|non-string check field app.slug|late"
  "app|an array app slug|app={\"slug\":[]}|non-string check field app.slug|late"
  "app|an object app slug|app={\"slug\":{}}|non-string check field app.slug|late"
  "app|an unencodable app slug|app={\"slug\":\"\\ud800\"}|check field app.slug is not encodable text|late"
  "app|a true app id|app={\"slug\":\"github-actions\",\"id\":true}|check run app.id is not an integer|early"
  "app|a false app id|app={\"slug\":\"github-actions\",\"id\":false}|check run app.id is not an integer|early"
  "app|the app id 9.0|app={\"slug\":\"github-actions\",\"id\":9.0}|check run app.id is not an integer|early"
  "app|the app id 9e0|app={\"slug\":\"github-actions\",\"id\":9e0}|check run app.id is not an integer|early"
  "app|an array app id|app={\"slug\":\"github-actions\",\"id\":[]}|check run app.id is not an integer|early"
  "app|an object app id|app={\"slug\":\"github-actions\",\"id\":{}}|check run app.id is not an integer|early"
  "app|the app id [9]|app={\"slug\":\"github-actions\",\"id\":[9]}|check run app.id is not an integer|early"
)
gate_pm="{\"id\":${gate_pm_id},${PM_OK#\{}"
run_case "the gated reading with no field changed -> green" \
  "$(runs "$gate_pm" "$SD_OK" "$APM_OK" "$CST_OK" "$CF" "$(gated_run)")" "" "" 0
run_case "the gated reading with head_sha naming the commit read -> green" \
  "$(runs "$gate_pm" "$SD_OK" "$APM_OK" "$CST_OK" "$CF" "$(gated_run "$gate_head")")" "" "" 0
run_case "the gated reading with the decisive run in progress -> not green" \
  "$(runs "$gate_pm" "$SD_OK" "$APM_OK" "$CST_OK" "$CF" "$(gated_run "$gate_head" 'status="in_progress"' conclusion=null)")" "" "" 2
run_case "the gated reading with the decisive run failed -> red" \
  "$(runs "$gate_pm" "$SD_OK" "$APM_OK" "$CST_OK" "$CF" "$(gated_run "$gate_head" 'conclusion="failure"')")" "" "" 1
# gate_cases CHECKS CONTEXTS: each check of the array named CHECKS, made in each
# context of the array named CONTEXTS less the changes to the field the check
# reads; a context left empty by that, or repeating one already made for the
# check, is skipped, as are a null or absent status for a late check.
gate_cases() {
  local -n gc_checks="$1" gc_ctxs="$2"
  local chk field what bad needle when ctx spec key late_bad
  local -a specs kept
  local -A made
  for chk in "${gc_checks[@]}"; do
    IFS='|' read -r field what bad needle when <<<"$chk"
    made=()
    for ctx in "${gc_ctxs[@]}"; do
      specs=() kept=() late_bad=""
      IFS=';' read -r -a specs <<<"$ctx"
      for spec in "${specs[@]}"; do
        if [ "${spec%%=*}" != "$field" ]; then kept+=("$spec"); fi
        case "$spec" in status=null | status=absent) late_bad=1 ;; esac
      done
      if [ -n "$ctx" ] && [ "${#kept[@]}" -eq 0 ]; then continue; fi
      if [ -n "$late_bad" ] && [ "$when" != early ] && [ "$field" != status ]; then continue; fi
      key="$(IFS=';'; printf '%s' "${kept[*]}")"
      if [ -n "${made["k$key"]+x}" ]; then continue; fi
      made["k$key"]=1
      run_err_case "$what on a run with the id $gate_id and [${key:-no other change}] -> unreadable" \
        "$(runs "$gate_pm" "$SD_OK" "$APM_OK" "$CST_OK" "$CF" "$(gated_run "${kept[@]}" "$bad")")" 3 "$read_failed: $needle"
    done
  done
}
gate_cases gate_checks gate_ctx
gate_cases gate_bad gate_real
# Each check is also made once with small ids, after a first run with the id 7,
# so a reader that made a check only on a run whose id is above some size is
# caught as well as one that made it only below. The decisive run carries the id
# 9; for the id checks it carries the small string id "9" (not an integer) or
# the id 7 of the first run (repeated). Each case names the id its decisive run
# carries.
for chk in "${gate_checks[@]}"; do
  IFS='|' read -r field what bad needle when <<<"$chk"
  small_id=9
  case "$bad" in
    "id=$gate_pm_id") small_id=7 bad="" ;;
    id=*) small_id='"9"' bad="" ;;
  esac
  run_err_case "$what on a run with the id $small_id -> unreadable" \
    "$(runs "{\"id\":7,${PM_OK#\{}" "$SD_OK" "$APM_OK" "$CST_OK" "$CF" "$(gated_run "id=$small_id" "$bad")")" 3 "$read_failed: $needle"
done
# The repeated-id check applies whatever the first run carrying the id holds: the
# first run below carries the id 31234567890 and each context above in turn (a
# null or absent status is itself unreadable, and a context changing the id is
# not this case, so those are left out), and a later run, with head_sha naming
# the commit read, carries the same id. A reader that recorded an id only for a
# run with some field value, or with head_sha present or absent, would read the
# reading green, pending or red.
for ctx in "${gate_ctx[@]}"; do
  specs=() skip=""
  IFS=';' read -r -a specs <<<"$ctx"
  for spec in "${specs[@]}"; do
    case "$spec" in id=* | status=null | status=absent) skip=1 ;; esac
  done
  if [ -n "$skip" ]; then continue; fi
  run_err_case "the id of an earlier run with [${ctx:-no other change}] repeated -> unreadable" \
    "$(runs "$PM_OK" "$SD_OK" "$APM_OK" "$CST_OK" "$CF" "$(gated_run "${specs[@]}")" "$(gated_run "$gate_head")")" 3 \
    "$read_failed: duplicate check run id"
done

# Every computation over the runs of a reading covers every run, wherever it
# sits: not only the first runs, the last runs, or the first page. The 6-run
# bad_at fixture above covers each index of a small reading; the cases below put
# one decisive run at late positions of a 300-run reading served as 1 page and
# as 3 pages of 100: runs 0, 6, 49, 50, 99, 100, 101 and 299 of the 1-page
# reading, and runs 100 and 199 (the first and last of page 2) and 200 and 299
# (the first and last of page 3) of the 3-page reading. The 5 green required
# checks are runs 1 to 5. At each position the decisive run is, in turn, a
# head_sha of another commit, each malformed field, a check run that is not an
# object, an id that is not an integer, a repeat of the id of run 1 (at every
# position but run 0), a failed run (red), an unfinished run (pending, and no
# required check is named as missing), and one of the 5 required checks moved
# there from its own run (green); 2 readings that differ only in the conclusion
# of that run do not confirm (the second differs from the first, so the tool
# reads again, and that third read fails: exit 3, where a reader that compared
# only some runs would confirm on the second reading, exit 0); and an
# unfinished run there is named in the report that a single reading without
# --wait writes on standard output, so no wait window can close first. A
# page 2 or 3 that is malformed makes the whole reading unreadable. A reader that checked only some runs or pages would read
# such a reading green or pending, or fail with another message. Residual: the
# positions are a sample, so a reader that skipped one other run of a large
# reading is not caught.
# big_reading SIZE PAGES [WHERE=RAW]...: SIZE green github-actions runs named
# extra 0 to extra SIZE - 1, split in order into PAGES pages of equal size, with
# the run at index WHERE replaced by the raw JSON RAW, or, for WHERE pN, page N
# (counted from 1) replaced whole by RAW. A WHERE out of range or given twice,
# or a SIZE that PAGES does not divide, prints nothing and fails, so the case
# built on it fails.
big_reading() {
  python3 -I - "$@" <<'PY'
import sys

size, pages = int(sys.argv[1]), int(sys.argv[2])
if pages < 1 or size % pages:
    sys.exit(f"big_reading: {pages} pages do not divide {size} runs")
runs = ['{"status":"completed","conclusion":"success","name":"extra %d","app":{"slug":"github-actions"}}' % i
        for i in range(size)]
whole, seen = {}, set()
for spec in sys.argv[3:]:
    where, sep, raw = spec.partition("=")
    if not sep or where in seen:
        sys.exit(f"big_reading: bad or repeated placement {where!r}")
    seen.add(where)
    if where[:1] == "p" and where[1:].isdigit() and 1 <= int(where[1:]) <= pages:
        whole[int(where[1:])] = raw
    elif where.isdigit() and int(where) < size:
        runs[int(where)] = raw
    else:
        sys.exit(f"big_reading: placement {where!r} is out of range")
per = size // pages
sys.stdout.write("\n".join(
    whole.get(p + 1, '{"check_runs":[%s]}' % ",".join(runs[p * per:(p + 1) * per]))
    for p in range(pages)
))
PY
}
# big_bad FIELD VALUE INDEX: the green extra run of index INDEX with FIELD set to
# the raw JSON VALUE. FIELD is status, conclusion, name, app.slug, app.id, app (the
# whole app object), or head_sha or id, which is added to that run alone; any other
# FIELD prints nothing and fails.
big_bad() {
  local st='"completed"' cn='"success"' nm="\"extra $3\"" app='{"slug":"github-actions"}' pre=""
  case "$1" in
    status) st="$2" ;;
    conclusion) cn="$2" ;;
    name) nm="$2" ;;
    app.slug) app="{\"slug\":$2}" ;;
    app.id) app="{\"slug\":\"github-actions\",\"id\":$2}" ;;
    app) app="$2" ;;
    head_sha | id) pre="\"$1\":$2," ;;
    *) return 1 ;;
  esac
  printf '{%s"status":%s,"conclusion":%s,"name":%s,"app":%s}' "$pre" "$st" "$cn" "$nm" "$app"
}
big_req=("1=$PM_OK" "2=$SD_OK" "3=$APM_OK" "4=$CST_OK" "5=$CF")
req_json=("$PM_OK" "$SD_OK" "$APM_OK" "$CST_OK" "$CF")
req_names=("Plugin manifests" "Skill discovery" "Agent Plugins manifest" "CI status tests" "Cloudflare Pages")
# big_one PAGES INDEX RAW: the 300-run reading in PAGES pages, with the 5 green
# required checks at runs 1 to 5 and the run at INDEX replaced by RAW.
big_one() { big_reading 300 "$1" "${big_req[@]}" "$2=$3"; }
# big_where PAGES INDEX: that position in words.
big_where() { printf 'run %s of 300 on page %s of %s' "$2" "$(( $2 / (300 / $1) + 1 ))" "$1"; }
for pages in 1 3; do
  run_case "a reading of 300 runs on $pages page(s) with no run changed -> green" \
    "$(big_reading 300 "$pages" "${big_req[@]}")" "" "" 0
done
moved_n=0
for at in 1:0 1:6 1:49 1:50 1:99 1:100 1:101 1:299 3:100 3:199 3:200 3:299; do
  pages="${at%%:*}" idx="${at#*:}"
  where="$(big_where "$pages" "$idx")"
  run_err_case "head_sha of another commit on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad head_sha "\"$C2\"" "$idx")")" 3 \
    "$read_failed: check run head_sha '$C2' is not the requested commit 0000000000000000000000000000000000000000"
  run_err_case "null status on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad status null "$idx")")" 3 "$read_failed: check field status is null"
  run_err_case "non-string conclusion on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad conclusion 1 "$idx")")" 3 "$read_failed: non-string check field conclusion"
  run_err_case "non-string name on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad name 7 "$idx")")" 3 "$read_failed: non-string check field name"
  run_err_case "non-string app slug on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad app.slug 7 "$idx")")" 3 "$read_failed: non-string check field app.slug"
  run_err_case "non-object app on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad app '[]' "$idx")")" 3 "$read_failed: check run app is not an object"
  run_err_case "non-integer app id on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad app.id '"9"' "$idx")")" 3 "$read_failed: check run app.id is not an integer"
  run_err_case "check run that is not an object as $where -> unreadable" \
    "$(big_one "$pages" "$idx" '"completed"')" 3 "$read_failed: a check run is not an object"
  run_err_case "non-integer id on $where alone -> unreadable" \
    "$(big_one "$pages" "$idx" "$(big_bad id '"7"' "$idx")")" 3 "$read_failed: check run id is not an integer"
  if [ "$idx" -ne 0 ]; then
    run_err_case "id of run 1 repeated on $where -> unreadable" \
      "$(big_reading 300 "$pages" "1={\"id\":7,${PM_OK#\{}" "2=$SD_OK" "3=$APM_OK" "4=$CST_OK" "5=$CF" "$idx=$(big_bad id 7 "$idx")")" 3 \
      "$read_failed: duplicate check run id"
  fi
  run_case "failed run on $where alone -> red" \
    "$(big_one "$pages" "$idx" "$(big_bad conclusion '"failure"' "$idx")")" "" "" 1
  CASE_ABSENT="not registered" run_case "unfinished run on $where alone -> not green" \
    "$(big_one "$pages" "$idx" "$(big_bad status '"in_progress"' "$idx")")" "" "" 2
  # One of the 5 required checks, in turn, moved here from its own run, which is
  # left a green extra run.
  k=$(( moved_n % 5 )); moved_n=$(( moved_n + 1 ))
  moved=()
  for j in 0 1 2 3 4; do
    if [ "$j" -eq "$k" ]; then moved+=("$idx=${req_json[j]}"); else moved+=("$(( j + 1 ))=${req_json[j]}"); fi
  done
  run_case "required check ${req_names[k]} as $where is seen -> green" \
    "$(big_reading 300 "$pages" "${moved[@]}")" "" "" 0
  CASE_NEEDLE="$read_failed: gh api failed" run_case "readings differing only on $where do not confirm" \
    "$(big_reading 300 "$pages" "${big_req[@]}")" \
    "$(big_one "$pages" "$idx" "$(big_bad conclusion '"neutral"' "$idx")")" "g a f" 3
  CASE_OUT="$(printf '  %-28s %s' "extra $idx" in_progress)" \
    run_case "the report names the unfinished $where" \
    "$(big_one "$pages" "$idx" "$(big_bad status '"in_progress"' "$idx")")" "" "" 2
done
for p in 2 3; do
  run_err_case "page $p of 3 that is not an object -> unreadable" \
    "$(big_reading 300 3 "${big_req[@]}" "p$p=[]")" 3 "$read_failed: check-runs page is not an object"
  run_err_case "page $p of 3 whose check_runs is null -> unreadable" \
    "$(big_reading 300 3 "${big_req[@]}" "p$p={\"check_runs\":null}")" 3 "$read_failed: check_runs is not an array"
done

# Exact matching of each required Actions job: a run counts only when its name is
# the whole display name and its app slug is the whole github-actions slug. Each
# near miss below replaces Plugin manifests beside the other 4 required checks
# green, so a relaxed comparison (prefix, suffix, substring, trimmed or folded)
# would read green (exit 0); the exact comparison reads it missing (exit 2).
# near_pm NAME SLUG: that reading, with the Plugin manifests run named NAME under
# app slug SLUG.
near_pm() {
  runs "{\"status\":\"completed\",\"conclusion\":\"success\",\"name\":\"$1\",\"app\":{\"slug\":\"$2\"}}" "$SD_OK" "$APM_OK" "$CST_OK" "$CF"
}
for near in "Plugin manifest" "Plugin" "Plugin manifests (pull_request)" "Plugin manifestsx" \
  "xPlugin manifests" "lugin manifests" "Validate Plugin manifests" " Plugin manifests" \
  "Plugin manifests\\t" "\\tPlugin manifests" "\\uff30lugin manifests" "The Plugin manifests job" \
  "PLUGIN MANIFESTS" "Plugin  manifests"; do
  CASE_NEEDLE="required check(s) Plugin manifests not registered" \
    run_case "near name [$near] does not count -> not green" "$(near_pm "$near" github-actions)" "" "" 2
done
for near in "github-actions-x" "xgithub-actions" "github-action" "ithub-actions" "x-github-actions-x" \
  " github-actions" "\\tgithub-actions" "github-actions " "\\uff47ithub-actions" "GitHub-Actions" \
  "GITHUB-ACTIONS"; do
  CASE_NEEDLE="required check(s) Plugin manifests not registered" \
    run_case "near slug [$near] does not count -> not green" "$(near_pm "Plugin manifests" "$near")" "" "" 2
done
# The Cloudflare build is matched by the exact app slug and app id of the
# Cloudflare app, so a run carrying the real app id under any other slug, whether
# it shares a prefix, has text or whitespace before or after the real slug, uses a
# compatibility form of a letter, or is in another letter case, does not count.
for near in "xcloudflare-pages" " cloudflare-pages" "Cloudflare-pages" "pages-cloudflare" "cloudflar" \
  "cloudflare-evil" "cloudflare" "cloudflare-pages" "cloudflare-workers-and-pages-x" \
  "CLOUDFLARE-WORKERS-AND-PAGES" "cloudflare-workers-and-pages " "x-cloudflare-workers-and-pages" \
  " cloudflare-workers-and-pages" "\\tcloudflare-workers-and-pages" "\\uff43loudflare-workers-and-pages"; do
  CASE_NEEDLE="required check(s) Cloudflare Pages not registered" \
    run_case "near Cloudflare slug [$near] with the app id 85455 does not count -> not green" \
    "$(runs "$REQ_GA" "{\"status\":\"completed\",\"conclusion\":\"success\",\"name\":\"Cloudflare Pages\",\"app\":{\"slug\":\"$near\",\"id\":85455}}")" "" "" 2
done
# The name is not consulted: a run of the real app with an empty name counts.
run_case "Cloudflare build with an empty name is matched by its app slug and app id -> green" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"success","name":"","app":{"slug":"cloudflare-workers-and-pages","id":85455}}')" "" "" 0
# An integer app id on a github-actions run is valid: the 4 required Actions jobs
# carrying the github-actions app id 15368 still count.
run_case "github-actions runs carrying the app id 15368 still count -> green" \
  "$(runs '{"status":"completed","conclusion":"success","name":"Plugin manifests","app":{"slug":"github-actions","id":15368}}' \
    '{"status":"completed","conclusion":"success","name":"Skill discovery","app":{"slug":"github-actions","id":15368}}' \
    '{"status":"completed","conclusion":"success","name":"Agent Plugins manifest","app":{"slug":"github-actions","id":15368}}' \
    '{"status":"completed","conclusion":"success","name":"CI status tests","app":{"slug":"github-actions","id":15368}}' \
    "$CF")" "" "" 0
# The slug cloudflare alone, with the real app id, does not count.
CASE_NEEDLE="required check(s) Cloudflare Pages not registered" \
  run_case "Cloudflare app slug of exactly cloudflare does not count -> not green" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare","id":85455}}')" "" "" 2
# The real slug with another app id (including the negated one, and the ids that
# equal it modulo 2**32 and 2**64), with no app id, or with a null app id is not the
# Cloudflare app, so the reading stays pending.
for spec in '85456|,"id":85456' '-85455|,"id":-85455' '4295052751|,"id":4295052751' \
  '18446744073709637071|,"id":18446744073709637071' 'absent|' 'null|,"id":null'; do
  CASE_NEEDLE="required check(s) Cloudflare Pages not registered" \
    run_case "real Cloudflare slug with app id [${spec%%|*}] does not count -> not green" \
    "$(runs "$REQ_GA" "{\"status\":\"completed\",\"conclusion\":\"success\",\"name\":\"Cloudflare Pages\",\"app\":{\"slug\":\"cloudflare-workers-and-pages\"${spec#*|}}}")" "" "" 2
done
# The real slug and the real app id on 2 different runs are not the Cloudflare
# app: each run must carry both.
CASE_NEEDLE="required check(s) Cloudflare Pages not registered" \
  run_case "real Cloudflare slug and real app id on different runs do not count -> not green" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85456}}' \
    '{"status":"completed","conclusion":"success","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages","id":85455}}')" "" "" 2
# A run that is not the pinned app is still read for its verdict: if Cloudflare
# renames the app (another slug) or re-registers it (another app id), a failed
# build of it reads red, never pending.
run_case "failed run of a renamed Cloudflare app (slug cloudflare-pages) -> red" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"failure","name":"Cloudflare Pages","app":{"slug":"cloudflare-pages","id":85455}}')" "" "" 1
run_case "failed run of a re-registered Cloudflare app (app id 85456) -> red" \
  "$(runs "$REQ_GA" '{"status":"completed","conclusion":"failure","name":"Cloudflare Pages","app":{"slug":"cloudflare-workers-and-pages","id":85456}}')" "" "" 1
# The app id is checked whatever the slug: a non-integer app id under an app with
# no slug, or with a null slug, makes the whole reading unreadable.
for app in '{"id":"9"}' '{"slug":null,"id":"9"}'; do
  run_err_case "non-integer app id in the app $app -> unreadable" \
    "$(runs "$REQ_GA" "$CF" "{\"status\":\"completed\",\"conclusion\":\"success\",\"name\":\"extra\",\"app\":$app}")" 3 \
    "check read failed for 0000000000000000000000000000000000000000: check run app.id is not an integer"
done
# An app id that is present and is neither an integer nor null (a string, either
# boolean, a number with a fraction part or an exponent, an array or an object)
# makes the whole reading unreadable.
for app_id in '"85455"' true false 85455.0 85455e0 '[]' '{}' '[85455]'; do
  run_err_case "Cloudflare app id [$app_id] is not an integer -> unreadable" \
    "$(runs "$REQ_GA" "{\"status\":\"completed\",\"conclusion\":\"success\",\"name\":\"Cloudflare Pages\",\"app\":{\"slug\":\"cloudflare-workers-and-pages\",\"id\":${app_id}}}")" 3 \
    "check read failed for 0000000000000000000000000000000000000000: check run app.id is not an integer"
done
# Every required check missing: the message names all 5, in their declared order,
# and the commit read.
run_err_case "every missing required check is named, in order" \
  '{"check_runs":[{"status":"completed","conclusion":"success","name":"check","app":{"slug":"github-actions"}}]}' 2 \
  "required check(s) Plugin manifests, Skill discovery, Agent Plugins manifest, CI status tests, Cloudflare Pages not registered for 0000000000000000000000000000000000000000 though they run on every PR and push here; not green"

# The declared required names follow the workflows, and each workflow runs its
# job on every pull request and every push to main. wf_shape reads each of the 4
# workflows with an allow-list that fails closed, in Python with the standard
# library only, because no YAML parser is guaranteed on the CI image. It accepts
# only the YAML subset these files use: block mappings and block sequences whose
# keys are plain unquoted words; scalar values that are plain, or quoted on one
# line without escapes; a one-line flow list of such scalars; block scalars (| or
# >, with an optional chomping indicator), whose content is every following line
# indented more than the column of the key that opened the block, so for
# "- run: |" the column of run, not of the dash; and comments. Any other line,
# such as a quoted, anchored, aliased, tagged, explicit or merge key, a flow
# mapping, a duplicate key, a tab or a non-ASCII character, fails the check and
# is named by its line number. A failure of the checker itself, a workflow that
# is missing or cannot be read as UTF-8 text, or a workflow with no line other
# than blank lines and comments, also fails the check, and is named
# shape-check-error, unreadable-workflow or empty-workflow, not by a line number,
# so no report names a line past the end of the file. Within that subset the
# top level holds only name, on, permissions, env and jobs. The on: block holds
# only a pull_request trigger with nothing under it and a push
# trigger filtered to main alone. The permissions block is exactly contents:
# read. A top-level env, if present, holds only CLAUDE_CODE_VERSION, set to a
# dotted version number such as 2.1.310, which cannot change whether or how a
# step runs, so the check admits no BASH_ENV, ENV, SHELLOPTS or BASHOPTS that
# could turn every step into a no-op. The job with the declared display name
# holds only name, runs-on set to ubuntu-latest, and steps, so no env:, if:,
# needs:, defaults: or container: key. Each step holds an optional name and
# either uses: naming an owner/repo action pinned to a full 40-character commit
# sha, never a local ./ action or a docker:// image, or run: with shell: bash,
# never another shell or a custom shell command, and nothing else, so no env:,
# if: or continue-on-error: key. So the check refuses anything set in the
# workflow that could skip the job or its steps, or pass over a failed step. A
# job skipped by an if:, or by a failed job it needs, concludes skipped, which
# ci-status.py reads as a failure for a required Actions job, but a step skipped
# by an if: or allowed to fail leaves the job successful, so such a job would
# read green without running its checks. The job display name is also the
# only 4-space-indented name: line, and it equals the name that ci-status.py
# declares. A renamed job, a filter that leaves a commit without the check, or
# any key or line outside that shape fails here, instead of turning every read
# into a forever-pending one or a false green. In CI this check runs in the CI
# status tests job (.github/workflows/ci-status-test.yml) on every pull request
# and every push to main, and ci-status.py insists on that job, so a commit on
# which it has not run, or has not passed, does not read green. Residual: what
# the commands the steps run and the pinned actions do, including anything they
# write for later steps, such as a BASH_ENV line in the GITHUB_ENV file, and
# what the other jobs of the workflow run, are not checked, so a step changed
# to do nothing still reads green.
# wf_shape FILE JOB: print a word for each shape problem found, nothing if none.
# A line outside the subset, a file that cannot be read as UTF-8, or a file with
# no line other than blank lines and comments, ends the check with that one word;
# a failure of the checker itself exits non-zero with nothing on standard output.
wf_shape() {
  python3 -I - "$1" "$2" <<'PY'
import re
import sys

path, job = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
except (OSError, UnicodeDecodeError):
    print("unreadable-workflow")
    sys.exit(0)

KEY = r"[A-Za-z_][A-Za-z0-9_-]*"
COMMENT = r"(?:\s+#.*)?"
QUOTED = r"""(?:"[^"\\]*"|'[^']*')"""
# The only forms accepted for the CLAUDE_CODE_VERSION value and for a uses:
# value, matching what the 4 workflows use today.
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
PINNED_ACTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*@[0-9a-f]{40}")
PLAIN = r"[A-Za-z0-9_$./][^#]*?"
WORD = r"""(?:[A-Za-z0-9_./-]+|"[^"\\,\[\]{}]*"|'[^',\[\]{}]*')"""
ENTRY = re.compile("(" + KEY + "):(?: (.*))?")
BLOCK = re.compile(r"[|>][+-]?" + COMMENT)
FLOW = re.compile(r"\[\s*(" + WORD + r"(?:\s*,\s*" + WORD + r")*)\s*\]" + COMMENT)
VALUE = re.compile("(" + QUOTED + "|" + PLAIN + ")" + COMMENT)


class Refused(Exception):
    pass


def indent(line):
    return len(line) - len(line.lstrip(" "))


class Reader:
    """A reader for the YAML subset above; anything outside it raises Refused."""

    def __init__(self, lines):
        self.lines, self.i = lines, 0

    def fail(self, word="unrecognized-line"):
        raise Refused(f"{word}-{self.i + 1}")

    def peek(self):
        # The indent of the next line that is neither blank nor a comment.
        while self.i < len(self.lines):
            s = self.lines[self.i].strip()
            if s and not s.startswith("#"):
                return indent(self.lines[self.i])
            self.i += 1
        return None

    def scalar(self, value):
        m = VALUE.fullmatch(value)
        if not m:
            self.fail()
        s = m.group(1).rstrip()
        if s[0] in "\"'":
            return s[1:-1]
        if ": " in s or s.endswith(":"):
            self.fail()
        return s

    def node(self):
        col = self.peek()
        rest = self.lines[self.i][col:]
        if rest == "-" or rest.startswith("- "):
            return self.sequence(col)
        return self.mapping(col, {})

    def sequence(self, col):
        items = []
        while self.peek() == col:
            line = self.lines[self.i]
            if not line[col:].startswith("- "):
                self.fail()
            rest = line[col + 2:]
            if re.match(KEY + ":(?: |$)", rest):
                item = {}
                self.entry(col + 2, rest, item)
                items.append(self.mapping(col + 2, item))
            else:
                items.append(self.scalar(rest))
                self.i += 1
        if (self.peek() or 0) > col:
            self.fail()
        return items

    def mapping(self, col, found):
        while self.peek() == col:
            self.entry(col, self.lines[self.i][col:], found)
        if (self.peek() or 0) > col:
            self.fail()
        return found

    def entry(self, col, rest, found):
        # col is the column of the key, also for the first key of "- key: ...".
        m = ENTRY.fullmatch(rest)
        if not m:
            self.fail()
        key, value = m.group(1), (m.group(2) or "").strip()
        if key in found:
            self.fail("duplicate-key")
        if not value or value.startswith("#"):
            self.i += 1
            found[key] = self.node() if (self.peek() or 0) > col else None
        elif BLOCK.fullmatch(value):
            self.i += 1
            self.block(col)
            found[key] = "block scalar"
        elif value.startswith("["):
            f = FLOW.fullmatch(value)
            if not f:
                self.fail()
            found[key] = [self.scalar(w) for w in re.split(r"\s*,\s*", f.group(1))]
            self.i += 1
        else:
            found[key] = self.scalar(value)
            self.i += 1

    def block(self, col):
        # Block scalar content: every following line that is blank or indented
        # more than the key column; a later line less indented than the first
        # content line, but still past the key column, is refused.
        first = None
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip():
                if indent(line) <= col:
                    return
                if first is None:
                    first = indent(line)
                elif indent(line) < first:
                    self.fail()
            self.i += 1


reader = Reader(lines)
try:
    for n, line in enumerate(lines):
        if re.search(r"[^\x20-\x7e]", line):
            reader.i = n
            reader.fail("character-line")
    # peek() runs off the end of a file holding only blank lines and comments,
    # so name that case rather than cite a line past the end of the file.
    first = reader.peek()
    if first is None:
        raise Refused("empty-workflow")
    if first != 0:
        reader.fail()
    tree = reader.mapping(0, {})
    if reader.peek() is not None:
        reader.fail()
except Refused as err:
    print(err)
    sys.exit(0)


found = []
for key in tree:
    if key not in ("name", "on", "permissions", "env", "jobs"):
        found.append("top-key-" + key)
if not isinstance(tree.get("name"), str):
    found.append("top-shape-name")
if tree.get("permissions") != {"contents": "read"}:
    found.append("top-shape-permissions")
if "env" in tree:
    env = tree["env"]
    if not isinstance(env, dict) or not env:
        found.append("top-shape-env")
    else:
        for key, value in env.items():
            if key != "CLAUDE_CODE_VERSION":
                found.append("env-key-" + key)
            elif not isinstance(value, str) or not VERSION.fullmatch(value):
                found.append("env-value-" + key)
on = tree.get("on")
if not isinstance(on, dict) or set(on) != {"pull_request", "push"}:
    found.append("on-block")
else:
    if on["pull_request"] is not None:
        found.append("pull-request-filter")
    if on["push"] != {"branches": ["main"]}:
        found.append("push-filter")
jobs = tree.get("jobs")
named = [v for v in jobs.values() if isinstance(v, dict) and v.get("name") == job] if isinstance(jobs, dict) else []
if len(named) != 1:
    found.append("job-block")
else:
    body = named[0]
    for key in body:
        if key not in ("name", "runs-on", "steps"):
            found.append("job-key-" + key)
    if body.get("runs-on") != "ubuntu-latest":
        found.append("job-shape-runs-on")
    steps = body.get("steps")
    if not isinstance(steps, list) or not steps or not all(isinstance(s, dict) for s in steps):
        found.append("job-shape-steps")
    else:
        for step in steps:
            for key, value in step.items():
                if key not in ("name", "uses", "shell", "run"):
                    found.append("step-key-" + key)
                elif not isinstance(value, str):
                    found.append("step-shape-" + key)
            # Either a pinned remote action alone, or a run: under exactly bash.
            if "uses" in step:
                if "run" in step or "shell" in step:
                    found.append("step-shape-uses-with-run")
                if not isinstance(step["uses"], str) or not PINNED_ACTION.fullmatch(step["uses"]):
                    found.append("step-value-uses")
            elif "run" in step:
                if step.get("shell") != "bash":
                    found.append("step-value-shell")
            else:
                found.append("step-shape-empty")
print(" ".join(dict.fromkeys(found)))
PY
}
wf_dir="${here}/../.github/workflows"
for pair in "plugin-validate.yml:Plugin manifests" "skill-discovery.yml:Skill discovery" \
  "agent-plugin-manifest.yml:Agent Plugins manifest" "ci-status-test.yml:CI status tests"; do
  wf="${pair%%:*}" job="${pair#*:}" why=""
  if [ ! -f "$wf_dir/$wf" ] || [ ! -r "$wf_dir/$wf" ]; then
    why=" unreadable-workflow"
  else
    if [ "$(grep -E '^    name: ' "$wf_dir/$wf")" != "    name: $job" ]; then why="$why job-name"; fi
    if grep -q -E '^[[:space:]]*(paths|paths-ignore|branches-ignore):' "$wf_dir/$wf"; then why="$why trigger-filter"; fi
    shape="$(wf_shape "$wf_dir/$wf" "$job")" || why="$why shape-check-error"
    if [ -n "$shape" ]; then why="$why $shape"; fi
  fi
  if [ "$(grep -c -F "_actions_job(\"$job\")" "${here}/ci-status.py")" != 1 ]; then why="$why declared"; fi
  if [ -z "$why" ]; then
    printf 'ok   required check %s follows %s\n' "$job" "$wf"
  else
    printf 'FAIL required check %s follows %s (%s)\n' "$job" "$wf" "${why# }"; fails=$((fails + 1))
  fi
done

# A workflow with no line other than blank lines and comments is named
# empty-workflow, never by a line number past the end of the file.
# run_empty_shape_case NAME CONTENT: wf_shape on a file holding exactly CONTENT
# (printf format) must print empty-workflow and nothing else.
run_empty_shape_case() {
  local name="$1" tmp got
  tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  printf "$2" > "$tmp/wf.yml"
  if got="$(wf_shape "$tmp/wf.yml" "Skill discovery")" && [ "$got" = "empty-workflow" ]; then
    printf 'ok   %s\n' "$name"
  else
    printf 'FAIL %s (got %s)\n' "$name" "$got"; fails=$((fails + 1))
  fi
  rm -rf "$tmp"
}
run_empty_shape_case "an empty workflow file is named empty-workflow" ""
run_empty_shape_case "a workflow of one blank line is named empty-workflow" "\n"
run_empty_shape_case "a workflow of blank lines and comments is named empty-workflow" "\n# a comment\n  \n"

# Commit sha and repository contract (backlog row 86). The tool accepts only a
# full 40-character hexadecimal sha and makes no local git call, so no case needs
# a git repository. Each case copies ci-status.sh and ci-status.py into a
# throwaway tools directory, runs the copy from /, and serves a green reading
# from a fake gh that logs the arguments, environment and working directory of
# every call, and snapshots the tool output at its first call. The fake gh repo
# view answers with GH_REPO when that variable reaches it, else with the VIEW
# value (FAIL makes it exit 1), so a leaked GH_REPO changes the path read.
# C1, C1_UPPER and C2 are set at the top of this file.
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
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
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
# --timeout and --interval are bounded at 86400 seconds. run_contract_case
# passes --interval 1, so the interval bound is checked through run_timed_case
# below, inside a 2-second wait window so a tool that accepts the value ends
# within 5 seconds instead of sleeping for a day.
run_contract_case "--timeout at the 86400-second bound is used" 0 "$C1" owner/name owner/name - - --wait --timeout 86400 "$C1"
run_contract_case "--timeout above the 86400-second bound is refused" 3 nogh owner/name owner/name - - --timeout 86401 "$C1"
run_contract_case "--timeout far above the 86400-second bound is refused" 3 nogh owner/name owner/name - - --timeout 2147484 "$C1"
run_timed_case "--interval above the 86400-second bound is refused" "$GA_PRESENT" 5 3 --wait --timeout 2 --interval 86401

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
# sourcedself (bash -c sources it with $0 set to the wrapper path, then prints
# after=<status>; the caller must keep running and see status 3). Without one,
# the wrapper runs as bash with its absolute path. A shell option token, errexit
# (bash -e), nounset (bash -u) or pipefail (bash -o pipefail), runs that bash
# with the option set. sourcedvars sources it from a caller that holds here, src,
# cause, sourced and restricted, which must be left unchanged; sourcedro does the
# same with those names (and rc) readonly, which must not turn the sourced path
# into the executed one. hardlink runs a hard link to the copied wrapper placed
# in the working directory, beside the planted ci-status.py, which must be
# refused because the wrapper then has 2 links. fddecoy opens a hard link to the
# copied wrapper (in the working directory) as fd 9, removes the link, creates a
# regular decoy file named as /proc/self/fd/9 then reads (".../h.sh (deleted)"),
# and runs bash /dev/fd/9. dirswap runs the wrapper through a directory symlink
# that a python3 first on PATH retargets, just before the resolver runs, to a
# directory holding a copy of the wrapper and the planted ci-status.py.
# fdslashes, fdlink, fdslasheshold and fdlinkhold build the descriptor decoy of
# the round 8 seat driver: a hard link to the copied wrapper opened as fd 9 and
# removed, a symlink named ".../h.sh (deleted)" to a decoy copy of the wrapper
# beside the planted ci-status.py, and bash run on /dev//fd/9 (slashes) or on a
# symlink to /dev/fd/9 (link); the hold forms also pass fd 255 open on the decoy.
# roflags and rotext run bash with a BASH_ENV file that marks the wrapper
# variable __ci_status_flags (with a close-on-exec value) or __ci_status_text
# (with a passing path) readonly, so the assignment fails: the wrapper must give
# the cannot-find refusal, never run the gate on the value the caller set.
# rorefuse runs a hard link to the copied wrapper, placed beside the planted
# ci-status.py, with a BASH_ENV file that defines __ci_status_refuse as a no-op
# and marks it readonly (readonly -f), so the wrapper cannot redefine it: the
# wrapper must still give the cannot-find refusal, never run the planted file.
# hold255self passes fd 255 open on the real copied wrapper and runs it normally,
# so only the close-on-exec check can refuse it. dotdotproc and dotdotdevfd
# open the real copied wrapper as fd 9 and run bash on cwd/L/../fd/9, with L a
# symlink to /proc/self/fd or to /dev/fd: every other layer would let that real
# wrapper run, so only the descriptor-path test on the resolved source can
# refuse it. dirfd opens the copied tools directory as fd 9 and runs bash on
# /dev//fd/9/ci-status.sh; WANT A asserts property A only: the planted
# ci-status.py must not run, and the wrapper must either run the real gate
# (exit 0 with the sha line) or refuse (exit 3 with the message). Each refusal
# has its own message, which the case checks.
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
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
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
  local bflags=()
  case " $resolve " in
    *" errexit "*) bflags=(-e) ;;
    *" nounset "*) bflags=(-u) ;;
    *" pipefail "*) bflags=(-o pipefail) ;;
  esac
  local entry=(bash "${bflags[@]}" "$tools/ci-status.sh") feed="" path="$bin:$PATH"
  case " $resolve " in
    *" sourced "*)
      entry=(bash -c '. "$1" "${@:2}"; s=$?; printf "after=%s\n" "$s"; exit "$s"' bash "$tools/ci-status.sh") ;;
    *" stdin "*) feed="$tools/ci-status.sh"; entry=(bash -s --) ;;
    *" barename "*) path="$bin:$tools:$PATH"; entry=(bash ci-status.sh) ;;
    *" pylink "*)
      tools="$tmp/copy"; mkdir -p "$tools"
      cp "${here}/ci-status.sh" "$tools/"
      ln -s "$cwd/ci-status.py" "$tools/ci-status.py"
      entry=(bash "${bflags[@]}" "$tools/ci-status.sh") ;;
    *" sourcedself "*)
      entry=(bash -c '. "$0" "$@"; s=$?; printf "after=%s\n" "$s"; exit "$s"' "$tools/ci-status.sh") ;;
    *" sourcedvars "*)
      entry=(bash -c 'here=keep src=keep cause=keep sourced=keep restricted=keep; . "$1" "${@:2}"; s=$?; printf "after=%s\n" "$s"; printf "vars=%s,%s,%s,%s,%s\n" "$here" "$src" "$cause" "$sourced" "$restricted"; exit "$s"' bash "$tools/ci-status.sh") ;;
    *" fddecoy "*)
      ln "$tools/ci-status.sh" "$cwd/h.sh"
      entry=(bash -c 'exec 9<"$1" || exit 98; rm -f "$1"; printf "" > "$1 (deleted)"; shift; exec bash /dev/fd/9 "$@"' _ "$cwd/h.sh") ;;
    *" dirswap "*)
      local swap_py; swap_py="$(command -v python3)"
      mkdir -p "$tmp/other" "$tmp/swapbin"
      cp "${here}/ci-status.sh" "$tmp/other/"
      cp "$cwd/ci-status.py" "$tmp/other/ci-status.py"
      ln -s "$tools" "$tmp/link"
      cat > "$tmp/swapbin/python3" <<PY
#!/usr/bin/env bash
if [ ! -e "$tmp/swapped" ]; then : > "$tmp/swapped"; ln -sfn "$tmp/other" "$tmp/link"; fi
exec "$swap_py" "\$@"
PY
      chmod +x "$tmp/swapbin/python3"
      path="$tmp/swapbin:$bin:$PATH"
      entry=(bash "$tmp/link/ci-status.sh") ;;
    *" fdslashes "*|*" fdlink "*|*" fdslasheshold "*|*" fdlinkhold "*)
      cp "${here}/ci-status.sh" "$cwd/ci-status.sh"
      ln "$tools/ci-status.sh" "$cwd/h.sh"
      local fd_hold=nohold fd_target="/dev//fd/9"
      case " $resolve " in *" fdslasheshold "*|*" fdlinkhold "*) fd_hold=hold ;; esac
      case " $resolve " in
        *" fdlink "*|*" fdlinkhold "*) ln -s /dev/fd/9 "$cwd/l.sh"; fd_target="$cwd/l.sh" ;;
      esac
      entry=(bash -c 'exec 9<"$1" || exit 98; rm -f "$1"; ln -s ci-status.sh "$1 (deleted)"; if [ "$2" = hold ]; then exec 255<"$3" || exit 98; fi; t="$4"; shift 4; exec bash "$t" "$@"' _ "$cwd/h.sh" "$fd_hold" "$cwd/ci-status.sh" "$fd_target") ;;
    *" dotdotproc "*|*" dotdotdevfd "*)
      local dd_link=/proc/self/fd
      case " $resolve " in *" dotdotdevfd "*) dd_link=/dev/fd ;; esac
      ln -s "$dd_link" "$cwd/L"
      entry=(bash -c 'exec 9<"$1" || exit 98; shift; exec bash "$@"' _ "$tools/ci-status.sh" "$cwd/L/../fd/9") ;;
    *" dirfd "*)
      entry=(bash -c 'exec 9<"$1" || exit 98; shift; exec bash "$@"' _ "$tools" "/dev//fd/9/ci-status.sh") ;;
    *" hold255self "*)
      entry=(bash -c 'exec 255<"$1" || exit 98; exec bash "$@"' _ "$tools/ci-status.sh") ;;
    *" hardlink "*)
      ln "$tools/ci-status.sh" "$cwd/ci-status.sh"
      entry=(bash "$cwd/ci-status.sh") ;;
    *" sourcedro "*)
      entry=(bash -c 'readonly here=keep src=keep cause=keep sourced=0 restricted=0 rc=0; . "$1" "${@:2}"; s=$?; printf "after=%s\n" "$s"; exit "$s"' bash "$tools/ci-status.sh") ;;
    *" posixsh "*) entry=("$posix_sh" "$tools/ci-status.sh") ;;
    *" restricted "*) entry=(bash -r "$tools/ci-status.sh") ;;
    *" setr "*)
      printf "set -r\n" > "$tmp/setr.sh"
      entry=(env BASH_ENV="$tmp/setr.sh" bash "$tools/ci-status.sh") ;;
    *" roflags "*)
      printf "readonly __ci_status_flags=2000000\n" > "$tmp/ro.sh"
      entry=(env BASH_ENV="$tmp/ro.sh" bash "$tools/ci-status.sh") ;;
    *" rotext "*)
      printf "readonly __ci_status_text=/ok/ci-status.sh\n" > "$tmp/ro.sh"
      entry=(env BASH_ENV="$tmp/ro.sh" bash "$tools/ci-status.sh") ;;
    *" rorefuse "*)
      ln "$tools/ci-status.sh" "$cwd/ci-status.sh"
      printf "__ci_status_refuse() { :; }\nreadonly -f __ci_status_refuse\n" > "$tmp/ro.sh"
      entry=(env BASH_ENV="$tmp/ro.sh" bash "$cwd/ci-status.sh") ;;
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
  if [ "$want" = A ]; then
    # Property A only: exit 0 (the real gate ran) or 3 (refused), never a planted run.
    case "$got" in 0 | 3) want="$got" ;; *) want=3 ;; esac
  fi
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
    *" sourced "*|*" setrsourced "*|*" sourcedself "*|*" sourcedvars "*|*" sourcedro "*)
      if ! grep -q -x -F "after=3" "$tmp/out"; then ok=0; why="$why caller-status"; fi ;;
  esac
  case " $resolve " in
    *" sourcedvars "*)
      if ! grep -q -x -F "vars=keep,keep,keep,keep,keep" "$tmp/out"; then ok=0; why="$why caller-vars"; fi ;;
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
run_wrapper_case "wrapper sourced with \$0 set to its own path returns status 3 to the caller" 3 sourcedself
run_wrapper_case "sourced wrapper leaves the variables of the caller unchanged" 3 sourcedvars
run_wrapper_case "sourced wrapper with readonly caller variables still refuses as sourced" 3 sourcedro
run_wrapper_case "hard link to the wrapper beside a planted ci-status.py fails closed with exit 3" 3 hardlink
run_wrapper_case "wrapper run as /dev/fd/N with a deleted-file decoy fails closed with exit 3" 3 fddecoy
run_wrapper_case "directory symlink swapped before the resolver runs fails closed with exit 3" 3 dirswap
run_wrapper_case "descriptor decoy run as /dev//fd/9 fails closed with exit 3" 3 fdslashes
run_wrapper_case "descriptor decoy run through a symlink to /dev/fd/9 fails closed with exit 3" 3 fdlink
run_wrapper_case "descriptor decoy as /dev//fd/9 with fd 255 held on the decoy fails closed with exit 3" 3 fdslasheshold
run_wrapper_case "descriptor decoy through a symlink with fd 255 held on the decoy fails closed with exit 3" 3 fdlinkhold
run_wrapper_case "fd 255 inherited from the caller fails closed with exit 3" 3 hold255self
run_wrapper_case "readonly __ci_status_flags from BASH_ENV fails closed with exit 3" 3 roflags
run_wrapper_case "readonly __ci_status_text from BASH_ENV fails closed with exit 3" 3 rotext
run_wrapper_case "readonly __ci_status_refuse from BASH_ENV with a hard-linked wrapper fails closed with exit 3" 3 rorefuse
run_wrapper_case "real wrapper as L/../fd/9 with L to /proc/self/fd fails closed with exit 3" 3 dotdotproc
run_wrapper_case "real wrapper as L/../fd/9 with L to /dev/fd fails closed with exit 3" 3 dotdotdevfd
run_wrapper_case "directory descriptor /dev//fd/9/ci-status.sh never runs a planted gate" A dirfd
# Inherited shell options never change a refusal: each runs with no gate, a
# symlinked gate and an unreadable gate, and must refuse with status 3.
for opt in errexit nounset pipefail; do
  run_wrapper_case "$opt: wrapper with no ci-status.py beside it fails closed with exit 3" 3 "$opt nopy"
  run_wrapper_case "$opt: symlinked ci-status.py beside a copied wrapper fails closed with exit 3" 3 "$opt pylink"
  run_wrapper_case "$opt: unreadable ci-status.py fails closed with exit 3" 3 "$opt noread"
done

# run_output_case NAME WANT STREAM KIND: run ci-status.sh with standard output
# closed (out), standard error closed (err) or standard output on /dev/full
# (full), for a green reading (green) or a usage error (usage, an abbreviated
# sha). A failed or impossible write must end the tool with exit 3, never with a
# verdict or a crash status.
run_output_case() {
  local name="$1" want="$2" stream="$3" kind="$4"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }; local bin="$tmp/bin"; mkdir -p "$bin"
  printf "%s" "$GA_PRESENT" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in *check-runs*) cat "$tmp/def.json";; *"repo view"*) printf "owner/name";; *) printf "";; esac
GH
  chmod +x "$bin/gh"
  local sha="$C1"
  if [ "$kind" = usage ]; then sha="${C1:0:7}"; fi
  case "$stream" in
    out) PATH="$bin:$PATH" bash "$ci" --repo owner/name --interval 1 "$sha" >&- 2> "$tmp/err" ;;
    err) PATH="$bin:$PATH" bash "$ci" --repo owner/name --interval 1 "$sha" > "$tmp/out" 2>&- ;;
    full) PATH="$bin:$PATH" bash "$ci" --repo owner/name --interval 1 "$sha" > /dev/full 2> "$tmp/err" ;;
  esac
  local got=$?
  if [ "$got" -eq "$want" ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got %s, want %s)\n" "$name" "$got" "$want"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_output_case "green reading with standard output closed exits 3" 3 out green
run_output_case "green reading with standard error closed exits 3" 3 err green
run_output_case "usage error with standard output closed exits 3" 3 out usage
run_output_case "usage error with standard error closed exits 3" 3 err usage
run_output_case "green reading with standard output on a full device exits 3" 3 full green

# run_signal_case NAME WANT MODE: a fake gh prints a green body and exits 1. MODE
# sigchld runs ci-status.sh with SIGCHLD ignored, which, unless the gate restores
# the default, lets the kernel reap gh so its status reads as 0 (a false green).
run_signal_case() {
  local name="$1" want="$2" mode="$3"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf "%s" "$GA_PRESENT" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in *check-runs*) cat "$tmp/def.json"; exit 1;; *"repo view"*) printf "owner/name";; *) printf "";; esac
GH
  chmod +x "$bin/gh"
  local launch='import os, signal, sys
signal.signal(signal.SIGCHLD, signal.SIG_IGN)
os.execvp(sys.argv[1], sys.argv[1:])'
  case "$mode" in
    sigchld) PATH="$bin:$PATH" python3 -I -c "$launch" bash "$ci" --repo owner/name --interval 1 "$C1" > /dev/null 2>&1 ;;
  esac
  local got=$?
  if [ "$got" -eq "$want" ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got %s, want %s)\n" "$name" "$got" "$want"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_signal_case "green body from a failing gh with SIGCHLD ignored exits 3, not 0" 3 sigchld

# run_pipe_case NAME MODE: the refusal for a wrapper with no ci-status.py beside
# it is written to a standard error whose pipe has no reader, with SIGPIPE at its
# default. MODE exec runs the wrapper; MODE sourced sources it and the caller must
# keep running and see status 3. SIGPIPE must not end either.
run_pipe_case() {
  local name="$1" mode="$2"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local tools="$tmp/repo/tools"; mkdir -p "$tools"
  cp "${here}/ci-status.sh" "$tools/"
  local launch='import os, signal, sys
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
r, w = os.pipe()
os.close(r)
os.dup2(w, 2)
os.close(w)
os.execvp(sys.argv[1], sys.argv[1:])'
  case "$mode" in
    exec) python3 -I -c "$launch" bash "$tools/ci-status.sh" "$C1" > "$tmp/out" ;;
    sourced)
      python3 -I -c "$launch" bash -c '. "$1" "${@:2}"; s=$?; printf "after=%s\n" "$s"; exit "$s"' \
        bash "$tools/ci-status.sh" "$C1" > "$tmp/out" ;;
  esac
  local got=$? ok=1 why=""
  if [ "$got" -ne 3 ]; then ok=0; why="$why exit"; fi
  if [ "$mode" = sourced ] && ! grep -q -x -F "after=3" "$tmp/out"; then ok=0; why="$why caller-status"; fi
  if [ "$ok" -eq 1 ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got exit %s, want 3;%s)\n" "$name" "$got" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_pipe_case "refusal to a broken pipe still exits 3" exec
run_pipe_case "sourced refusal to a broken pipe still returns 3 to the caller" sourced

# An exception while importing the standard library exits 3, never 1: the gate is
# run with json made unimportable.
import_got=0
python3 -I -c 'import sys
sys.modules["json"] = None
path = sys.argv[1]
sys.argv = [path, "0c83f120fcc4630694465bcf89f7415a21d54dba"]
exec(compile(open(path).read(), path, "exec"), {"__name__": "__main__", "__file__": path})' \
  "${here}/ci-status.py" > /dev/null 2>&1 || import_got=$?
if [ "$import_got" -eq 3 ]; then printf "ok   import failure exits 3 (exit %s)\n" "$import_got";
else printf "FAIL import failure exits 3 (got %s, want 3)\n" "$import_got"; fails=$((fails + 1)); fi

# run_lost_status_case NAME: a fake gh prints a green body and exits 1, and the
# gate runs in process with os.waitpid replaced by one that raises
# ChildProcessError, as a lost exit status (ECHILD) does. The real gh-running
# code path must read that as unreadable (exit 3), never as exit 0, whatever
# CPython subprocess does with ECHILD. The gate is imported under -B, so the
# run writes no __pycache__ beside the tools under test.
run_lost_status_case() {
  local name="$1"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf "%s" "$GA_PRESENT" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in *check-runs*) cat "$tmp/def.json"; exit 1;; *"repo view"*) printf "owner/name";; *) printf "";; esac
GH
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c 'import importlib.util, os, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("ci_status_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
def lost(*args, **kwargs):
    raise ChildProcessError(10, "No child processes")
os.waitpid = lost
sys.argv = [path, "--repo", "owner/name", "--interval", "1", sys.argv[2]]
sys.exit(mod.run())' "${here}/ci-status.py" "$C1" > /dev/null 2>&1 || got=$?
  if [ "$got" -eq 3 ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got %s, want 3)\n" "$name" "$got"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_lost_status_case "lost gh exit status (ECHILD from the wait) exits 3, not 0"

# run_final_reap_case NAME MODE WANT NEEDLE: the gate runs in process in wait
# mode after a pending reading, with os.waitpid replaced so the second
# check-runs call looks unfinished to every poll and its status is first seen
# at the reap after the kill at the deadline. That gh ends on its own: MODE
# exit has it exit 1, MODE signal has it end itself with SIGTERM, MODE lost has
# it exit 1 and makes the reap after the kill raise ChildProcessError, and MODE
# red has it print a red reading and exit 0. At the first poll of that gh, the
# replaced os.waitpid waits with os.waitid and WNOWAIT until gh has ended,
# without reaping it, and then reports it unfinished as at every other poll. So
# gh has ended on its own before the kill. The gate runs with --timeout 30. Its
# time name is replaced by one whose time() and monotonic() return 2 fixed
# bases, the real clocks read once before the gate starts, plus a shift, and
# whose other attributes, sleep included, are the real ones. No host clock
# reading reaches the gate, so only the shift moves its clock: however long the
# first read, served by a fake gh script run as its own process, and the sleep
# after it take on a loaded host, the window stays open for the second read.
# Once that wait has seen gh end, the replaced os.waitpid sets the shift to the
# whole 30-second window, so the gate, at its next clock read (the one after
# that poll), finds the deadline passed and kills and reaps gh at once through
# its own code, and the case does not wait out the window. No sleep of the gate
# is skipped. None of the ends of the second gh is
# a read the deadline cut off, so each case must exit WANT, never 2 as a
# timed-out wait: 3 with NEEDLE on standard error, or for MODE red the red
# verdict, 1 with NEEDLE on standard output. The replaced os.waitpid also
# requires the status it reaps after the kill to be that end of gh, not the
# kill, so no case passes without reaching it. Because gh has always ended
# before the kill, these cases do not cover a gh still running when it is
# killed (the hung-gh cases of plan token s cover that) or a gate that reads a
# kill as gh's own end. The gate's clock stands apart from the host's, so they
# assert no time.
run_final_reap_case() {
  local name="$1" mode="$2" want="$3" needle="$4"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf "%s" "$GA_IN_PROGRESS" > "$tmp/def.json"
  printf "%s" "$GA_RED" > "$tmp/red.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*)
    if [ -e "$tmp/read" ]; then
      case "$mode" in
        signal) kill -TERM \$\$; sleep 60 ;;
        red) cat "$tmp/red.json"; exit 0 ;;
        *) exit 1 ;;
      esac
    fi
    : > "$tmp/read"; cat "$tmp/def.json" ;;
  *"repo view"*) printf "owner/name";; *) printf "";;
esac
GH
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c 'import importlib.util, os, signal, sys, time
path, mode, own = sys.argv[1], sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("ci_status_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
shift = [0]
WALL, MONO = time.time(), time.monotonic()  # read once, before the gate starts
class Clock:
    def __getattr__(self, name):
        return getattr(time, name)
    def time(self):
        return WALL + shift[0]
    def monotonic(self):
        return MONO + shift[0]
mod.time = Clock()
real_waitpid = os.waitpid
seen, waited = [], []
def waitpid(pid, options):
    if pid not in seen:
        seen.append(pid)
    if seen.index(pid) != 1:
        return real_waitpid(pid, options)
    if options & os.WNOHANG:
        if not waited:
            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)  # gh has ended, still unreaped
            waited.append(pid)
            shift[0] = 30  # the whole window: the gate next reads its deadline as passed
        return 0, 0
    result = real_waitpid(pid, options)
    status = result[1]
    if mode == "signal":
        ended = os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGTERM
    else:
        code = 0 if mode == "red" else 1
        ended = os.WIFEXITED(status) and os.WEXITSTATUS(status) == code
    if ended:
        open(own, "w").close()  # gh ended on its own, as MODE intends
    if mode == "lost":
        raise ChildProcessError(10, "No child processes")
    return result
os.waitpid = waitpid
sys.argv = [path, "--repo", "owner/name", "--wait", "--timeout", "30", "--interval", "1", sys.argv[2]]
sys.exit(mod.run())' "${here}/ci-status.py" "$C1" "$mode" "$tmp/own" > "$tmp/out" 2> "$tmp/err" || got=$?
  local stream="$tmp/err" why=""
  [ "$mode" = red ] && stream="$tmp/out"
  [ "$got" -eq "$want" ] || why="$why exit"
  grep -q -F -- "$needle" "$stream" || why="$why message"
  [ -e "$tmp/own" ] || why="$why reap"
  if [ -z "$why" ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got %s, want %s;%s)\n" "$name" "$got" "$want" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_final_reap_case "gh exiting 1 just before the kill at the deadline exits 3, not 2" exit 3 \
  "check read failed for ${C1}: gh api failed"
run_final_reap_case "gh ending itself by a signal just before the kill at the deadline exits 3, not 2" signal 3 \
  "check read failed for ${C1}: gh api failed"
run_final_reap_case "gh exit status lost at the reap after the kill at the deadline exits 3, not 2" lost 3 \
  "check read failed for ${C1}: could not run gh: the exit status of gh was lost"
run_final_reap_case "gh exiting 0 with a red reading just before the kill at the deadline exits 1, not 2" red 1 \
  "ci-status: a check did not pass for ${C1}"

# run_final_reap_view_case NAME FLAG: the gate runs in process with no --repo,
# with FLAG --wait, or - for none, and with os.waitpid replaced so gh repo
# view, the first gh call, looks unfinished to every poll and its status is
# first seen at the reap after the kill at the deadline. That gh prints
# owner/name and exits 0 on its own. At its first poll, the replaced os.waitpid
# waits with os.waitid and WNOWAIT until it has ended, without reaping it, and
# then reports it unfinished as at every other poll, so it has ended before the
# kill. The gate runs with --timeout 30, so the steps of the gate before gh
# repo view starts, including the clock read in infer_repo, have 30 seconds
# before the deadline. The gate's time name is replaced by one whose time() and
# monotonic() are the real clocks plus a shift: once that wait has seen gh repo
# view end, time.time and time.monotonic read 30 seconds ahead, so the gate, at
# its next clock read, finds the deadline passed and kills and reaps gh at once
# through its own code, and the case does not wait out the window. Because gh
# repo view has ended on its own before the kill, it is not a call the deadline
# cut off: the repository is inferred and printed on standard output, and the
# read after it, finding the window closed, exits 3 with that on standard error,
# never the line saying the repository could not be inferred, and never makes a
# check-runs call. The replaced os.waitpid also requires the status it reaps
# after the kill to be that exit 0, not the kill, so the case does not pass
# without reaching it. Because gh repo view has always ended before the kill,
# the case does not cover one still running when it is killed or a gate that
# reads a kill as gh's own end. The shift moves the gate's clock away from the
# host's, so it asserts no time.
run_final_reap_view_case() {
  local name="$1" flag="$2"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*) : > "$tmp/read"; exit 1 ;;
  *"repo view"*) printf "owner/name";; *) printf "";;
esac
GH
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c 'import importlib.util, os, sys, time
path, flag, own = sys.argv[1], sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("ci_status_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
shift = [0]
class Clock:
    def __getattr__(self, name):
        return getattr(time, name)
    def time(self):
        return time.time() + shift[0]
    def monotonic(self):
        return time.monotonic() + shift[0]
mod.time = Clock()
real_waitpid = os.waitpid
seen, waited = [], []
def waitpid(pid, options):
    if pid not in seen:
        seen.append(pid)
    if seen.index(pid) != 0:
        return real_waitpid(pid, options)
    if options & os.WNOHANG:
        if not waited:
            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)  # gh has ended, still unreaped
            waited.append(pid)
            shift[0] = 30  # the whole window: the gate next reads its deadline as passed
        return 0, 0
    result = real_waitpid(pid, options)
    status = result[1]
    if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0:
        open(own, "w").close()  # gh repo view ended on its own with exit 0
    return result
os.waitpid = waitpid
flags = [] if flag == "-" else [flag]
sys.argv = [path, *flags, "--timeout", "30", "--interval", "1", sys.argv[2]]
sys.exit(mod.run())' "${here}/ci-status.py" "$C1" "$flag" "$tmp/own" > "$tmp/out" 2> "$tmp/err" || got=$?
  local why=""
  [ "$got" -eq 3 ] || why="$why exit"
  grep -q -x -F -- "ci-status: repository owner/name" "$tmp/out" || why="$why repository"
  grep -q -F -- "check read failed for ${C1}: the wait window closed before the read" "$tmp/err" \
    || why="$why message"
  grep -q -F -- "could not infer the repository" "$tmp/err"
  case $? in 1) ;; *) why="$why absent" ;; esac
  [ -e "$tmp/own" ] || why="$why reap"
  [ ! -e "$tmp/read" ] || why="$why reads"
  if [ -z "$why" ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got %s, want 3;%s)\n" "$name" "$got" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_final_reap_view_case "gh repo view exiting 0 just before the kill at the deadline is accepted, then exits 3" \
  --wait
run_final_reap_view_case "gh repo view exiting 0 just before the kill without --wait is accepted, then exits 3" -

# run_closed_window_case NAME: the gate runs in process in wait mode with the
# wall clock it reads (time.time) replaced by a fixed one, and time.monotonic
# by the same fixed value 500 seconds lower. Its sleeps stay real, so the case,
# not the host's speed, fixes when the window closes. time.monotonic does not
# move while gh runs, so _gh never kills gh in this case and the first gh call
# has no bound; that call ends only when the fake gh returns on its own, which
# it does at once. The first check-runs call serves a pending reading, a
# successful unsettled one. When main calls read_checks again, after the
# top-of-loop guard has found time left, the fixed clock is moved to the
# deadline, so read_checks finds the window closed before the read and raises
# WindowClosed without running gh. After that reading this is the wait timing
# out: the case must exit 2; standard output must hold the pending reading's
# line "ci-status: waiting, 10 seconds left"; standard error must hold the
# cut-off line, here giving the reason that the window closed before the read,
# and the still-unsettled line, but no read-failure line; and the fake gh must
# serve exactly 1 check-runs call. Each expected line is matched whole by its
# own grep, so the order of the 2 standard-error lines is not checked. The
# zero-timeout cases and the run_final_reap_view_case cases reach the same
# raise with no successful reading before it, so they exit 3.
run_closed_window_case() {
  local name="$1"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf "%s" "$GA_IN_PROGRESS" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*) echo read >> "$tmp/reads"; cat "$tmp/def.json" ;;
  *"repo view"*) printf "owner/name";; *) printf "";;
esac
GH
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c 'import importlib.util, sys, time, types
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("ci_status_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
now = [1000.0]
mod.time = types.SimpleNamespace(time=lambda: now[0], sleep=time.sleep, monotonic=lambda: now[0] - 500)
real_read_checks = mod.read_checks
calls = []
def read_checks(repo, full_sha, deadline):
    calls.append(deadline)
    if len(calls) == 2:
        now[0] = deadline  # after the top-of-loop guard, before the read
    return real_read_checks(repo, full_sha, deadline)
mod.read_checks = read_checks
sys.argv = [path, "--repo", "owner/name", "--wait", "--timeout", "10", "--interval", "1", sys.argv[2]]
sys.exit(mod.run())' "${here}/ci-status.py" "$C1" > "$tmp/out" 2> "$tmp/err" || got=$?
  local why=""
  [ "$got" -eq 2 ] || why="$why exit"
  grep -q -x -F -- "ci-status: waiting, 10 seconds left" "$tmp/out" || why="$why pending"
  grep -q -x -F -- "ci-status: the wait window cut off the last read (the wait window closed before the read)" \
    "$tmp/err" || why="$why message"
  grep -q -x -F -- "ci-status: still unsettled after 10 seconds; giving up" "$tmp/err" || why="$why timeout"
  grep -q -F -- "check read failed" "$tmp/err"
  case $? in 1) ;; *) why="$why absent" ;; esac
  [ "$(grep -c "" "$tmp/reads" 2>/dev/null)" = 1 ] || why="$why reads"
  if [ -z "$why" ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got %s, want 2;%s)\n" "$name" "$got" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_closed_window_case "pending reading then the window closing before the next read -> not green, timed out"

# run_late_pass_case NAME: the gate runs in process in wait mode with time.time
# and time.monotonic fixed as in run_closed_window_case, so _gh never kills gh
# in this case, and both check-runs calls serve the same green reading. When
# the second read has returned, before main checks the deadline, the fixed
# clock is moved to the deadline, so the pass is confirmed only after the
# window closed. The case must exit 2; standard error must hold the line saying
# that the checks passed only after the window closed; standard output must
# hold the first reading's line asking for a confirmation reading but no
# confirmed-pass line; and the fake gh must serve exactly 2 check-runs calls.
run_late_pass_case() {
  local name="$1"
  local tmp; tmp="$(mktemp -d)" && [ -d "$tmp" ] || { setup_failed "$name"; return; }
  local bin="$tmp/bin"; mkdir -p "$bin"
  printf "%s" "$GA_PRESENT" > "$tmp/def.json"
  cat > "$bin/gh" <<GH
#!/usr/bin/env bash
case "\$*" in
  *check-runs*) echo read >> "$tmp/reads"; cat "$tmp/def.json" ;;
  *"repo view"*) printf "owner/name";; *) printf "";;
esac
GH
  chmod +x "$bin/gh"
  local got=0
  PATH="$bin:$PATH" python3 -I -B -c 'import importlib.util, sys, time, types
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("ci_status_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
now = [1000.0]
mod.time = types.SimpleNamespace(time=lambda: now[0], sleep=time.sleep, monotonic=lambda: now[0] - 500)
real_read_checks = mod.read_checks
calls = []
def read_checks(repo, full_sha, deadline):
    calls.append(deadline)
    checks = real_read_checks(repo, full_sha, deadline)
    if len(calls) == 2:
        now[0] = deadline  # after the confirmation read, before main checks the deadline
    return checks
mod.read_checks = read_checks
sys.argv = [path, "--repo", "owner/name", "--wait", "--timeout", "10", "--interval", "1", sys.argv[2]]
sys.exit(mod.run())' "${here}/ci-status.py" "$C1" > "$tmp/out" 2> "$tmp/err" || got=$?
  local why=""
  [ "$got" -eq 2 ] || why="$why exit"
  grep -q -x -F -- "ci-status: checks passed but only after the 10 second wait window closed" \
    "$tmp/err" || why="$why message"
  grep -q -x -F -- "ci-status: all checks pass; re-reading to confirm none is still registering" \
    "$tmp/out" || why="$why first"
  grep -q -F -- "every check passed" "$tmp/out"
  case $? in 1) ;; *) why="$why absent" ;; esac
  [ "$(grep -c "" "$tmp/reads" 2>/dev/null)" = 2 ] || why="$why reads"
  if [ -z "$why" ]; then printf "ok   %s (exit %s)\n" "$name" "$got";
  else printf "FAIL %s (got %s, want 2;%s)\n" "$name" "$got" "$why"; fails=$((fails + 1)); fi
  rm -rf "$tmp"
}

run_late_pass_case "green readings confirmed only after the window closed -> not green, timed out"

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
