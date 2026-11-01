#!/usr/bin/env bash
#
# Guarantees. Property A: no ci-status.py other than the real one beside the real
# wrapper ever runs through this wrapper. Property B: the wrapper exits 0 only when
# that gate ran and every check passed. Under supported invocations (executed as
# tools/ci-status.sh, run as bash tools/ci-status.sh, by absolute path or through
# PATH, from an ordinary shell with ordinary process state) the exit status
# follows the 0 to 3 contract below exactly. Under any other caller state the
# status may be any nonzero code. The exceptions, all disclosed below, are: the
# whole caller environment, every environment variable, including PATH,
# BASH_ENV, SHELLOPTS (noexec or onecmd there makes bash run nothing and exit 0),
# BASHOPTS and exported functions, which can defeat both properties; bash -n,
# bash -t and the startup files that bash runs first, which can exit 0 without
# running the wrapper code as written; and caller control of the process view, a
# tracer (ptrace) or seccomp filter that can alter any system call result, or a
# bind mount or other mount-namespace control that can present the real wrapper
# beside a planted gate, so both properties assume no such control. A copy of
# the wrapper runs the ci-status.py beside that copy by design: it is the real
# wrapper of its own directory.
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
# below. The non-bash refusal cannot tell whether it was sourced, so it always
# exits 3, which ends a caller that sourced the wrapper into a non-bash shell,
# still with status 3.
# Every refusal message is printed from a subshell that ignores SIGPIPE, and any
# write failure is ignored, so a closed or broken output cannot end the wrapper
# (or a caller that sourced it) before it returns or exits 3.
# The wrapper then decides once whether it is sourced: return succeeds in a
# subshell only when the wrapper is sourced. That test closes standard error with
# 2>&- rather than redirecting it to a file, and bash 5.3 accepts that in a
# restricted shell, so the one test serves every case. When sourced, the wrapper
# assigns no variable and changes no shell state of the caller: it prints its
# refusal (the restricted refusal in a restricted shell, otherwise the cannot-find
# refusal) and returns 3, so the caller keeps running with status 3; if return
# fails, because the test misread an executed wrapper as sourced (a tracer can
# make that happen), the block exits 3 rather than fall through to the gate. A
# readonly or otherwise unassignable caller variable cannot change its path.
# When executed, the wrapper next resets the inherited shell state that could
# change its exit status or skip its checks: errexit, nounset, pipefail,
# errtrace, functrace, noglob, noclobber, keyword, allexport, verbose, xtrace and
# posix are turned off, extdebug and expand_aliases are unset, aliases are
# removed, and the EXIT, ERR, DEBUG and RETURN traps are cleared. Its own
# variables carry the __ci_status_ prefix, and an assignment that fails ends in
# the cannot-find refusal, never in the exec.
# The wrapper next refuses with status 3 under a restricted shell, which would
# refuse the redirect and the exec below and exit 1, the code for a failed check.
# Restricted mode is read from $- as well as from the restricted_shell option,
# which is on only when bash starts restricted (bash -r or rbash), so a shell
# restricted later by set -r, for example from BASH_ENV, is refused too. The
# restricted refusal is printed to standard output: bash 5.3 accepts the >&2
# duplication there, but the restricted shell is documented to refuse output
# redirection, so this message uses none.
# The wrapper locates itself from BASH_SOURCE[0], never from $0 alone. It exits
# 3, and runs no ci-status.py, when it is read from standard input (BASH_SOURCE[0]
# is empty), when BASH_SOURCE[0] holds no "/" (a bare name is a PATH or
# working-directory lookup), or when $0 differs from BASH_SOURCE[0] (as in "bash
# ci-status.sh" found through PATH, where $0 is the bare name even though bash
# 5.3 sets BASH_SOURCE[0] to the full path). Executed through PATH, it receives
# its full path as both and runs as usual.
# A source path under /dev/fd/ or /proc/ is refused at once: it names an open
# descriptor, whose resolved name a caller can imitate with a decoy file.
# os.path.realpath resolves a symlinked wrapper without depending on GNU readlink.
# The resolved wrapper must be an existing regular file and the same file (device
# and inode) as the ci-status.sh in its directory, which must have exactly 1
# link; the ci-status.py beside it must be a regular file that is not a symlink
# and that the resolver can open for reading; otherwise the wrapper exits 3. A
# hard link to the real wrapper placed beside a planted ci-status.py is refused
# with the cannot-find refusal. Any nonzero resolver status is a refusal, and an
# empty resolver answer is one too, so a lost status cannot reach the exec. The
# directory is printed with a trailing slash, so command substitution cannot
# strip a newline from its name. Last, the ci-status.sh in the resolved directory
# must be the same file (test -ef) as /dev/fd/255, where bash 5.3 keeps the
# script it opened, whether it was run as bash FILE, as bash /dev/fd/N or
# executed directly. So the gate is bound to the file bash is running, not to a
# path string: a directory symlink swapped after bash opened the wrapper, or a
# decoy named like a deleted file, resolves to a directory whose ci-status.sh is
# a different file, and the wrapper refuses. If fd 255 is not the script, for
# example because the caller holds fd 255 open, the test fails and the wrapper
# refuses.
# Residual: the whole caller environment, every environment variable, including
# PATH, BASH_ENV, SHELLOPTS, BASHOPTS and exported shell functions, is outside the
# trust boundary. PATH chooses the python3 and the gh
# that ci-status.py runs, BASH_ENV runs code before this wrapper, and an exported
# function such as python3 replaces the resolver below; any of them can run a
# planted ci-status.py that exits 0. The wrapper defends only against a planted
# ci-status.py in the working directory and against a symlinked or misplaced gate.
# The checks run before the exec, so a ci-status.py removed or changed between the
# check and the exec is not caught.
# Shell invocation options that act before the wrapper code runs are outside what
# it can check: bash -n reads the wrapper, runs nothing and exits 0, and bash -t
# runs only its first command, the bash check, and exits 0. The startup files that
# bash reads before the wrapper, a file named by --rcfile or --init-file with -i,
# and the interactive or login startup files (such as ~/.bashrc, ~/.bash_profile
# and /etc/profile) run first and can exit 0 before the wrapper runs. A
# restricted caller that names the wrapper by path is refused by bash, with
# status 1, before the wrapper runs. When the wrapper is sourced, the options and traps of the caller,
# such as a DEBUG trap under extdebug, stay in force and are outside its reset.
# Resource exhaustion (a failed fork, for which bash exits 254) and a signal that
# ends the process are outside the exact-code contract; both give a nonzero
# status, so property B holds.
# A BASH_VERSION exported into a non-bash shell passes this check (see above).
if [ -z "${BASH_VERSION:-}" ]; then
  (trap "" PIPE; printf "ci-status: ci-status.sh must run under bash, not another shell (%s)\n" "$0" >&2) || :
  exit 3
fi
if (return 0 2>&-); then
  if shopt -q restricted_shell || [[ "$-" == *r* ]]; then
    (trap "" PIPE; printf "ci-status: ci-status.sh cannot run in a restricted shell (%s)\n" "$0") || :
  else
    (trap "" PIPE; printf "ci-status: cannot find ci-status.py beside the real ci-status.sh (%s)\n" "${BASH_SOURCE[0]:-}" >&2) || :
  fi
  return 3
  exit 3  # never fall through to the gate if return fails
fi
set +e +u +E +T +f +C +k +a +v +x +o pipefail +o posix
shopt -u extdebug expand_aliases
unalias -a
trap - EXIT ERR DEBUG RETURN
__ci_status_refuse() {
  # $1 is the stream (out or err), $2 the message; prints it and exits 3.
  if [ "$1" = out ]; then
    (trap "" PIPE; printf "%s\n" "$2") || :
  else
    (trap "" PIPE; printf "%s\n" "$2" >&2) || :
  fi
  exit 3
}
if shopt -q restricted_shell || [[ "$-" == *r* ]]; then
  __ci_status_refuse out "ci-status: ci-status.sh cannot run in a restricted shell ($0)"
fi
__ci_status_src="${BASH_SOURCE[0]:-}" || __ci_status_refuse err "ci-status: cannot find ci-status.py beside the real ci-status.sh ()"
__ci_status_find="ci-status: cannot find ci-status.py beside the real ci-status.sh ($__ci_status_src)" ||
  __ci_status_refuse err "ci-status: cannot find ci-status.py beside the real ci-status.sh ($__ci_status_src)"
if [ "$0" != "$__ci_status_src" ]; then __ci_status_refuse err "$__ci_status_find"; fi
case "$__ci_status_src" in
  /dev/fd/* | /proc/*) __ci_status_refuse err "$__ci_status_find" ;;
  */*) ;;
  *) __ci_status_refuse err "$__ci_status_find" ;;
esac
__ci_status_rc=0 || __ci_status_refuse err "$__ci_status_find"
__ci_status_here="$(python3 -I -c '
import os, stat, sys
try:
    wrapper = os.path.realpath(sys.argv[1])
    named = os.path.join(os.path.dirname(wrapper), "ci-status.sh")
    gate = os.path.join(os.path.dirname(wrapper), "ci-status.py")
    st = os.stat(wrapper)
    sn = os.lstat(named)
    ok = (stat.S_ISREG(st.st_mode) and stat.S_ISREG(sn.st_mode) and sn.st_nlink == 1
          and (st.st_dev, st.st_ino) == (sn.st_dev, sn.st_ino)
          and stat.S_ISREG(os.lstat(gate).st_mode))
except OSError:
    ok = False
if not ok:
    sys.exit(1)
try:
    open(gate, "rb").close()
except OSError:
    sys.exit(4)
print(os.path.join(os.path.dirname(wrapper), ""))
' "$__ci_status_src")" || __ci_status_rc=$?
if [ "$__ci_status_rc" = 4 ]; then
  __ci_status_refuse err "ci-status: cannot read ci-status.py beside the real ci-status.sh ($__ci_status_src)"
fi
if [ "$__ci_status_rc" != 0 ] || [ -z "$__ci_status_here" ] ||
  [ ! -f "${__ci_status_here}ci-status.py" ] || [ -L "${__ci_status_here}ci-status.py" ] ||
  ! [ "${__ci_status_here}ci-status.sh" -ef /dev/fd/255 ]; then
  __ci_status_refuse err "$__ci_status_find"
fi
exec python3 -I "${__ci_status_here}ci-status.py" "$@"
