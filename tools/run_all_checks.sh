#!/usr/bin/env bash
#
# Runs on this machine the run text of the workflow steps that
# tools/test-run-all-checks.py reads, the steps of the 17 workflows under
# .github/workflows that a pull_request or a push to main triggers, in the order
# of their files and of their steps, a command that an earlier workflow already
# runs being run once. Each distinct run text of those steps has a run line of
# its own, apart from the 5 run texts of the Plugin manifests job, for which the
# 1 run line plugin_manifests stands in (see below). plugin-drift.yml (a
# schedule and a manual dispatch) and release-skill.yml (a tag push and a manual
# dispatch) are not triggered by a pull request or a push to main, so neither is
# mirrored. Each command runs unpiped, from the repository root, and its exit
# status is recorded; a failure does not stop the run, and the script ends by
# naming the commands that failed and exiting 1, or exits 0 when all of them
# passed. It unsets CDPATH before its cd, so that cd does not resolve its
# relative folder through CDPATH and the commands it runs do not inherit it.
#
# The Plugin manifests job installs the Claude Code CLI at the version that
# plugin-validate.yml pins in CLAUDE_CODE_VERSION. This script installs nothing:
# plugin_manifests reads that pin, fails when claude is missing or when claude
# --version reports another version, and otherwise runs the 3 validations of
# that job, the staged skills directory included.
#
# tools/test-run-all-checks.py fails when a run text that it reads is neither a
# command line here nor one of its listed exceptions, when a command line here
# is not such a run text, or when the sha256 of this script is not the one it
# records, so a change here records the new digest there.
#
# Residual: the script runs all of its commands whatever a change touches, and
# it needs what CI provides, including the pinned CLI, PyYAML, the full git
# history, and network access with gh signed in for the live release checksum
# check, whose step in CI takes GH_TOKEN from the workflow. Each run text runs
# with bash in this machine's environment, so what a workflow sets around a step
# through a key that tools/test-run-all-checks.py does not read is not
# reproduced; that test's docstring says which keys it reads. Some commands
# write temporary files or temporary git worktrees, as in CI.
set -uo pipefail

unset CDPATH
cd "$(dirname "$0")/.." || exit 1

failed=()

# run COMMAND...: print the command, run it unpiped, and record a nonzero exit.
run() {
  printf '==> %s\n' "$*"
  "$@"
  local status=$?
  if [ "$status" -ne 0 ]; then
    printf '==> exit %s: %s\n' "$status" "$*"
    failed+=("$* (exit $status)")
  fi
}

# plugin_manifests: the Plugin manifests job of plugin-validate.yml, on the
# pinned CLI, which this script never installs.
plugin_manifests() {
  local pin version staged status=0
  pin="$(sed -n 's/^  CLAUDE_CODE_VERSION: "\([0-9][0-9.]*\)"$/\1/p' .github/workflows/plugin-validate.yml)"
  if [ -z "$pin" ]; then
    echo "run_all_checks: plugin-validate.yml pins no CLAUDE_CODE_VERSION" >&2
    return 1
  fi
  if ! command -v claude >/dev/null 2>&1; then
    echo "run_all_checks: claude is not installed; install @anthropic-ai/claude-code@${pin}" >&2
    return 1
  fi
  version="$(claude --version)" || return 1
  case "$version" in
    "$pin" | "$pin "*) ;;
    *)
      echo "run_all_checks: claude --version reports ${version:-nothing}, not the pinned ${pin}" >&2
      return 1
      ;;
  esac
  claude plugin validate . --strict || status=1
  claude plugin validate ./cleanlanguage --strict || status=1
  staged="$(mktemp -d)" || return 1
  mkdir -p "${staged}/skills" || status=1
  cp -r cleanlanguage/skills/cleanlanguage "${staged}/skills/cleanlanguage" || status=1
  claude plugin validate "${staged}/skills" --strict || status=1
  rm -rf "$staged"
  return "$status"
}

# agent-plugin-manifest.yml
run python3 -I tools/test-agent-plugin-manifest.py
run python3 -I tools/check-agent-plugin-manifest.py
# ci-status-test.yml
run bash tools/test-ci-status.sh
# install-page.yml
run python3 -I tools/check-python-version.py
run python3 -I tools/test-install-page.py
run python3 -I tools/check-install-page.py
# link-check.yml
run python3 -I tools/check-links.py
run python3 -I tools/test-release-links.py
run python3 -I tools/check-release-links.py
# manifest-icon.yml
run python3 -I tools/test-manifest-icon.py
run python3 -I tools/check-manifest-icon.py
# orchestration-registry.yml
run python3 -I tools/check-orchestration-registry.py
run python3 -I tools/test-orchestration-registry.py
run python3 -I tools/test-no-qa-labels.py
run python3 -I tools/test-orch-stage1-hooks.py
run python3 -I tools/test-orch-enumerate-backlog.py
run python3 -I tools/test-orch-migrate-todo.py
run python3 -I tools/test-orch-stage2-hooks.py
run python3 -I tools/test-ask-mode-guard.py
run python3 -I tools/check-flow-mode.py
run python3 -I tools/test-check-flow-mode.py
run python3 -I tools/check-orchestration-registry.py .aiqt/orchestration.json
# page-metadata.yml
run python3 -I tools/test-web-metadata.py
run python3 -I tools/test-page-metadata.py
run python3 -I tools/check-page-metadata.py
# pages-build.yml, after tools/check-python-version.py above
run python3 -I tools/test-pages-build.py
run bash tools/pages-build.sh
# plugin-validate.yml
run plugin_manifests
# portable-text-sync.yml, after tools/check-python-version.py above
run python3 -I tools/test-portable-text-sync-workflow.py
run python3 -I tools/test-skill-release-date.py
run python3 -I tools/test-skill-release-date-client.py
run bash tools/test-portable-text-release-date.sh
run tools/check-portable-text-sync.sh
run python3 -I tools/test-check-skill-consistency.py
run python3 -I tools/check-skill-consistency.py
run python3 -I tools/test-instructions-page.py
run python3 -I tools/check-instructions-page.py
# release-checksum-live.yml
run python3 -I tools/test-release-checksum-live.py
run python3 -I tools/check-release-checksum-live.py
# release-dry-run.yml, after the 3 of its steps above
run python3 -I tools/test-skill-version-consumers.py
run python3 -I tools/test-release-skill-workflow.py
run bash tools/test-version-selectors.sh
run tools/release-dry-run.sh
# site-draft.yml
run python3 -I tools/test-baseline-pin.py
run python3 -I tools/check-baseline-pin.py
run python3 -I tools/test-build-site.py
run python3 -I tools/build-site.py --check
run python3 -I tools/test-check-palette.py
run python3 -I tools/check-palette.py
# site-hardening.yml, after tools/check-python-version.py above
run python3 -I tools/test-headers.py
run python3 -I tools/check-headers.py
run python3 -I tools/test-security-txt.py
run python3 -I tools/check-security-txt.py
run python3 -I tools/test-inline-code.py
run python3 -I tools/check-inline-code.py
# sitemap.yml, after tools/test-web-metadata.py above
run python3 -I tools/generate-sitemap.py
run python3 -I tools/test-sitemap.py
# skill-discovery.yml
run python3 -I tools/test-skill-discovery.py
run python3 -I tools/check-skill-discovery.py
# workflow-isolation.yml, after tools/test-portable-text-sync-workflow.py above
run python3 -I tools/test-workflow-launch-isolation.py
run python3 -I tools/test-shell-launch-isolation.py
run python3 -I tools/test-tools-sys-path.py
run python3 -I tools/test-action-pins.py
run python3 -I tools/test-run-all-checks.py

if [ "${#failed[@]}" -gt 0 ]; then
  printf '==> %s of the commands failed:\n' "${#failed[@]}"
  printf '  %s\n' "${failed[@]}"
  exit 1
fi
printf '==> every command passed\n'
exit 0
