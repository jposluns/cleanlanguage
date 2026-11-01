#!/usr/bin/env bash
#
# Thin wrapper: the CI verdict logic lives in ci-status.py, a Python rewrite that
# parses the check-runs JSON structurally and fail-closed. Serializing checks to
# delimited text and parsing them in bash repeatedly let a crafted or malformed
# field forge or hide a check; structured JSON parsing removes that class. This
# wrapper preserves the tools/ci-status.sh interface the orchestrator resume flow
# and the CI workflows depend on. See ci-status.py for the contract and exit codes:
#   0 all checks passed (confirmed twice)  1 a check failed  2 still running / timed out
#   3 unreadable, no checks, or usage error.
# -I isolates the interpreter: PYTHONPATH, the user site directory and the script
# directory cannot shadow a standard-library import used by the gate.
# The wrapper first exits 3 when it runs under a shell other than bash, such as
# sh where /bin/sh is dash. That check is POSIX, so it runs before any bash-only
# syntax, which a non-bash shell would otherwise fail with exit 2, the code the
# contract reserves for checks still running or timed out. The check reads
# BASH_VERSION, so a caller that exports BASH_VERSION into a non-bash shell passes
# it and fails later with exit 2; that falls under the caller-environment residual
# below. The wrapper next refuses with status 3 under a restricted shell, which
# would refuse the redirect and the exec below and exit 1, the code for a failed
# check. Restricted mode is read from $- as well as from the restricted_shell
# option, which is on only when bash starts restricted (bash -r or rbash), so a
# shell restricted later by set -r, for example from BASH_ENV, is refused too.
# Every refusal after the bash check ends the same way: when the wrapper is
# sourced (BASH_SOURCE[0] differs from $0) it returns 3 to the caller, which keeps
# running with status 3, and otherwise it exits 3. Where BASH_SOURCE[0] differs
# from $0 but the wrapper was executed (a bare name found through PATH, or a
# script read from standard input), the return fails and the exit 3 runs. The
# non-bash refusal cannot read BASH_SOURCE, so it always exits 3, which ends a
# caller that sourced the wrapper into a non-bash shell, still with status 3.
# The restricted refusal is printed to standard output: bash 5.3 accepts the
# >&2 duplication there, but the restricted shell is documented to refuse
# output redirection, so this message, and the return that follows it, use none.
# The other refusals run where redirection works, so their return discards the
# error bash prints when the wrapper was executed rather than sourced.
# The wrapper locates itself from BASH_SOURCE[0], never from $0 alone. It exits
# 3, and runs no ci-status.py, when it is sourced rather than executed, when it is
# read from standard input (BASH_SOURCE[0] is empty), when BASH_SOURCE[0] holds no
# "/" (a bare name is a PATH or working-directory lookup), or when $0 differs from
# BASH_SOURCE[0] (as in "bash ci-status.sh" found through PATH, where $0 is the
# bare name even though bash 5.3 sets BASH_SOURCE[0] to the full path). Executed
# through PATH, it receives its full path as both and runs as usual.
# os.path.realpath resolves a symlinked wrapper without depending on GNU readlink.
# The resolved wrapper must be an existing regular file, and the ci-status.py
# beside it must be a regular file that is not a symlink and that the resolver can
# open for reading, or the wrapper exits 3.
# The directory is printed with a trailing slash, so command substitution cannot
# strip a newline from its name.
# Residual: the caller environment, including PATH, BASH_ENV and exported shell
# functions, is outside the trust boundary. PATH chooses the python3 and the gh
# that ci-status.py runs, BASH_ENV runs code before this wrapper, and an exported
# function such as python3 replaces the resolver below; any of them can run a
# planted ci-status.py that exits 0. The wrapper defends only against a planted
# ci-status.py in the working directory and against a symlinked or misplaced gate.
# The checks run before the exec, so a ci-status.py removed or changed between the
# check and the exec is not caught.
# A BASH_VERSION exported into a non-bash shell passes this check (see above).
if [ -z "${BASH_VERSION:-}" ]; then
  printf "ci-status: ci-status.sh must run under bash, not another shell (%s)\n" "$0" >&2
  exit 3
fi
restricted=0
case "$-" in *r*) restricted=1 ;; esac
if shopt -q restricted_shell; then restricted=1; fi
if [ "$restricted" -eq 1 ]; then
  printf "ci-status: ci-status.sh cannot run in a restricted shell (%s)\n" "$0"
  if [ "${BASH_SOURCE[0]:-}" != "$0" ]; then return 3; fi
  exit 3
fi
src="${BASH_SOURCE[0]:-}"
here=""
cause=find
if ! (return 0 2>/dev/null) && [ "$0" = "$src" ]; then
  case "$src" in
    */*)
      here="$(python3 -I -c '
import os, stat, sys
try:
    wrapper = os.path.realpath(sys.argv[1])
    gate = os.path.join(os.path.dirname(wrapper), "ci-status.py")
    ok = stat.S_ISREG(os.stat(wrapper).st_mode) and stat.S_ISREG(os.lstat(gate).st_mode)
except OSError:
    ok = False
if not ok:
    sys.exit(1)
try:
    open(gate, "rb").close()
except OSError:
    sys.exit(4)
print(os.path.join(os.path.dirname(wrapper), ""))
' "$src")"
      rc=$?
      if [ "$rc" -ne 0 ]; then here=""; fi
      if [ "$rc" -eq 4 ]; then cause=read; fi ;;
  esac
fi
if [ "$cause" = read ]; then
  printf "ci-status: cannot read ci-status.py beside the real ci-status.sh (%s)\n" "$src" >&2
  if [ "${BASH_SOURCE[0]:-}" != "$0" ]; then return 3 2>/dev/null; fi
  exit 3
fi
if [ -z "$here" ] || [ ! -f "${here}ci-status.py" ] || [ -L "${here}ci-status.py" ]; then
  printf "ci-status: cannot find ci-status.py beside the real ci-status.sh (%s)\n" "$src" >&2
  if [ "${BASH_SOURCE[0]:-}" != "$0" ]; then return 3 2>/dev/null; fi
  exit 3
fi
exec python3 -I "${here}ci-status.py" "$@"
