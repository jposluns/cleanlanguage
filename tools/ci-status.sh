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
# os.path.realpath resolves a symlinked wrapper without depending on GNU readlink, so
# the real ci-status.py beside the real file runs. The directory is printed with a
# trailing slash, so command substitution cannot strip a newline from its name. If
# the resolution fails, or the resolved directory holds no regular ci-status.py, the
# wrapper exits 3 rather than run a ci-status.py from the caller working directory.
here="$(python3 -I -c "import os, sys; print(os.path.join(os.path.dirname(os.path.realpath(sys.argv[1])), \"\"))" "$0")" || here=""
if [ -z "$here" ] || [ ! -f "${here}ci-status.py" ]; then
  printf "ci-status: cannot find ci-status.py beside the real ci-status.sh (%s)\n" "$0" >&2
  exit 3
fi
exec python3 -I "${here}ci-status.py" "$@"
