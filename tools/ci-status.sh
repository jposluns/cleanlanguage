#!/usr/bin/env bash
#
# Reports the CI verdict for one commit, and exits non-zero unless every check
# has passed.
#
# The verdict comes from the check-runs API, because that is the only endpoint
# that sees every required check. The Cloudflare Pages build, which CLAUDE.md
# names as this repository's required check, is produced by an external app
# rather than by GitHub Actions, so actions/runs does not report it and a gate
# built on actions/runs alone would pass while the required check was failing.
# The legacy commits/<sha>/status endpoint is not used either: this repository
# publishes no commit statuses, so it answers "pending" forever.
#
# Absence of checks is never success. A commit with no check runs, or a call
# that cannot be read, exits non-zero, so a caller waiting for green never
# mistakes silence for a pass.
#
# Neither is a PARTIAL set of checks. Checks do not all register at once: an
# external app can report before GitHub Actions has created its runs, and a read
# taken in that window sees only the checks that exist and calls them "every
# check". That is a false green, observed reporting exit 0 on a pull request
# whose two Actions gates had not started.
#
# So a pass is never declared on one reading. The script re-reads after one
# interval and passes only when the set of checks and their conclusions are
# identical across two consecutive readings. A check registering late changes the
# set and forces another round. This costs one interval on every green result,
# and applies whether or not --wait was given: one read is not trustworthy
# either way.
#
# Usage:
#   tools/ci-status.sh <sha>                     Report once and exit.
#   tools/ci-status.sh <sha> --wait              Poll until the checks settle.
#   tools/ci-status.sh <sha> --wait --timeout 600 --interval 20
#   tools/ci-status.sh <sha> --repo owner/name   Override the inferred repository.
#
# Exit codes:
#   0  every check passed, confirmed across two consecutive readings
#   1  at least one check failed, was cancelled, or timed out
#   2  checks are still running, or --wait hit its timeout
#   3  the result could not be read, no checks exist, or usage was wrong

set -uo pipefail

sha=""
repo=""
wait_for_settle=0
timeout_seconds=900
interval_seconds=15

die() {
  printf 'ci-status: %s\n' "$1" >&2
  exit 3
}

while [ $# -gt 0 ]; do
  case "$1" in
    --wait) wait_for_settle=1 ;;
    --timeout) shift; timeout_seconds="${1:-}" ;;
    --interval) shift; interval_seconds="${1:-}" ;;
    --repo) shift; repo="${1:-}" ;;
    -*) die "unknown option $1" ;;
    *) [ -n "${sha}" ] && die "more than one commit given"; sha="$1" ;;
  esac
  shift
done

[ -n "${sha}" ] || die "usage: ci-status.sh <sha> [--wait] [--timeout N] [--interval N] [--repo owner/name]"

case "${timeout_seconds}" in *[!0-9]*|'') die "--timeout takes whole seconds" ;; esac
case "${interval_seconds}" in *[!0-9]*|'') die "--interval takes whole seconds" ;; esac
[ "${interval_seconds}" -gt 0 ] || die "--interval must be above zero"

command -v gh >/dev/null 2>&1 || die "the gh CLI is not installed"

if [ -z "${repo}" ]; then
  repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)"
  [ -n "${repo}" ] || die "could not infer the repository; pass --repo owner/name"
fi

# Resolve a short sha or a ref to the full sha the checks are recorded against.
full_sha="$(git rev-parse "${sha}" 2>/dev/null)" || full_sha="${sha}"

# One read. Prints "<status><US><conclusion><US><name>" per check run, or fails
# loudly with the API's own message so a caller never has to guess why. The
# field separator is the unit separator rather than a tab, because bash collapses
# runs of IFS whitespace and a still-running check has an empty conclusion, which
# would otherwise shift its name into the wrong field.
read_checks() {
  local body
  if ! body="$(gh api "repos/${repo}/commits/${full_sha}/check-runs" --paginate 2>&1)"; then
    printf 'ci-status: could not read checks for %s in %s\n' "${full_sha}" "${repo}" >&2
    printf '%s\n' "${body}" >&2
    return 1
  fi
  printf '%s' "${body}" | jq -r '.check_runs[] | "\(.status)\u001f\(.conclusion // "")\u001f\(.name)"'
}

# Sets the verdict from a batch of check lines: pass, fail, pending, or none.
verdict_of() {
  local lines="$1"
  local status conclusion pending=0 failed=0 total=0

  [ -n "${lines}" ] || { printf 'none'; return; }

  while IFS=$'\x1f' read -r status conclusion _; do
    [ -n "${status}" ] || continue
    total=$((total + 1))
    if [ "${status}" != "completed" ]; then
      pending=$((pending + 1))
      continue
    fi
    case "${conclusion}" in
      success|neutral|skipped) ;;
      *) failed=$((failed + 1)) ;;
    esac
  done <<< "${lines}"

  [ "${total}" -gt 0 ] || { printf 'none'; return; }
  [ "${failed}" -gt 0 ] && { printf 'fail'; return; }
  [ "${pending}" -gt 0 ] && { printf 'pending'; return; }
  printf 'pass'
}

report() {
  local lines="$1"
  local status conclusion name
  while IFS=$'\x1f' read -r status conclusion name; do
    [ -n "${status}" ] || continue
    if [ "${status}" = "completed" ]; then
      printf '  %-28s %s\n' "${name}" "${conclusion}"
    else
      printf '  %-28s %s\n' "${name}" "${status}"
    fi
  done <<< "${lines}"
}

confirming=0
confirmed_snapshot=""
confirm_rounds=0

deadline=$(( $(date +%s) + timeout_seconds ))

while true; do
  if ! checks="$(read_checks)"; then
    # A transient read error is not a verdict. In wait mode keep waiting until
    # the deadline rather than aborting (a release step calls this AFTER
    # publishing, so a false abort strands the release); a single-shot report
    # still fails fast.
    if [ "${wait_for_settle}" -eq 1 ]; then
      now="$(date +%s)"
      if [ "${now}" -lt "${deadline}" ]; then
        printf 'ci-status: check read failed; retrying, %s seconds left\n' "$(( deadline - now ))" >&2
        sleep "${interval_seconds}"
        continue
      fi
      printf 'ci-status: check read still failing after %s seconds; giving up\n' "${timeout_seconds}" >&2
    fi
    exit 3
  fi
  verdict="$(verdict_of "${checks}")"

  if [ "${verdict}" != "pass" ]; then
    confirming=0
    confirmed_snapshot=""
  fi

  case "${verdict}" in
    pass)
      # Confirm against a second reading before calling it green, so a check
      # that has not registered yet is not mistaken for one that does not
      # exist. Identical means same names, statuses, and conclusions.
      if [ "${confirming}" -eq 1 ] && [ "${checks}" = "${confirmed_snapshot}" ]; then
        printf 'ci-status: every check passed for %s, confirmed on two readings\n' "${full_sha}"
        report "${checks}"
        exit 0
      fi
      confirm_rounds=$(( confirm_rounds + 1 ))
      if [ "${confirm_rounds}" -gt 5 ]; then
        printf 'ci-status: the set of checks kept changing across %s readings; not calling this green\n' "${confirm_rounds}" >&2
        report "${checks}" >&2
        exit 2
      fi
      confirmed_snapshot="${checks}"
      confirming=1
      printf 'ci-status: all checks pass; re-reading in %ss to confirm none is still registering\n' "${interval_seconds}"
      report "${checks}"
      sleep "${interval_seconds}"
      continue
      ;;
    fail)
      printf 'ci-status: a check did not pass for %s\n' "${full_sha}"
      report "${checks}"
      exit 1
      ;;
    none)
      # Absence is never a pass. In wait mode the checks may simply not have
      # registered yet, so wait until the deadline; a single-shot report treats
      # absence as unreadable and exits now.
      if [ "${wait_for_settle}" -eq 1 ]; then
        now="$(date +%s)"
        if [ "${now}" -lt "${deadline}" ]; then
          printf 'ci-status: no checks recorded yet for %s; waiting, %s seconds left\n' "${full_sha}" "$(( deadline - now ))" >&2
          sleep "${interval_seconds}"
          continue
        fi
        printf 'ci-status: no checks ever registered for %s within %s seconds\n' "${full_sha}" "${timeout_seconds}" >&2
      else
        printf 'ci-status: no checks are recorded for %s in %s\n' "${full_sha}" "${repo}" >&2
        printf 'ci-status: treating absent checks as unreadable, not as a pass\n' >&2
      fi
      exit 3
      ;;
  esac

  # Still running.
  if [ "${wait_for_settle}" -eq 0 ]; then
    printf 'ci-status: checks are still running for %s\n' "${full_sha}"
    report "${checks}"
    exit 2
  fi

  now="$(date +%s)"
  if [ "${now}" -ge "${deadline}" ]; then
    printf 'ci-status: still unsettled after %s seconds; giving up\n' "${timeout_seconds}" >&2
    report "${checks}" >&2
    exit 2
  fi

  printf 'ci-status: waiting, %s seconds left\n' "$(( deadline - now ))"
  report "${checks}"
  sleep "${interval_seconds}"
done
