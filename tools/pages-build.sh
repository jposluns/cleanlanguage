#!/usr/bin/env bash
#
# The Cloudflare Pages build command for cleanlanguage.ai.
#
# Pages publishes site/ exactly as it is committed; this script changes no file
# under site/. It runs the 5 offline integrity gates that the owner named on
# 2026-11-03, and no others, on the tree Pages checked out. Any gate failure
# fails the build, so a failing commit is never deployed (template
# specification, section 4, step 3). The site's other offline gates, such as
# tools/generate-sitemap.py, run only in GitHub Actions.
#
# Every gate here reads only the checked-out tree: none reaches the network or
# reads git history, so a shallow checkout is enough. The checks that need git
# history (tools/check-page-metadata.py) or the network
# (tools/check-release-checksum-live.py) stay in GitHub Actions only.
#
# A missing gate file fails the build with exit 3, the gates' own code for an
# input that cannot be read; it is never skipped. A failing gate passes its
# exit code through unchanged (1 for a failed check, 3 for an unreadable
# input). tools/test-pages-build.py holds the expected gate list and fails if
# this script stops running a gate, or stops failing when a gate exits 1 or 3.
#
# Usage (the build command in the Cloudflare Pages dashboard):
#   bash tools/pages-build.sh

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

# tools/build-site.py and tools/check-baseline-pin.py import tomllib, which
# needs Python 3.11 or later; refuse an older version here, before any gate,
# so the build log names the problem in one line.
python3 -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' || {
  echo "pages-build: Python 3.11 or later is required (tomllib); found $(python3 --version 2>&1)." >&2
  exit 1
}
echo "pages-build: $(python3 --version 2>&1)"

gate() {
  if [ ! -f "$1" ]; then
    echo "pages-build: gate $1 is missing; failing the build." >&2
    exit 3
  fi
  echo "pages-build: python3 -I $*"
  python3 -I "$@" || {
    status=$?
    echo "pages-build: $1 failed with exit ${status}; failing the build." >&2
    exit "${status}"
  }
}

gate tools/check-baseline-pin.py
gate tools/check-security-txt.py
gate tools/check-headers.py
gate tools/check-inline-code.py
gate tools/build-site.py --check

echo "pages-build: every gate passed; Pages publishes site/ as committed."
