# AIQT Guardrails adoption config

Adopter-owned. The pack updater does not overwrite this file. See `.aiqt/pin.toml`
for provenance and the adopted version.

## Profile

Active condition set: `always`, `tools-retrieval`, `writes-code`, `agent-harness`,
`multi-agent`; `personal-data` off. Equivalent to the Coding profile plus
`agent-harness` and `multi-agent`, since this repository is maintained with Claude
Code and a multi-agent orchestrator (worker dispatch, a concurrency lease, a durable
handoff store, attended and sometimes unattended operation).

## Active rule set

106 of 125 rules auto-load under `.claude/rules/aiqt/` and `.claude/rules/security/`.
The full 125-rule corpus is vendored as reference under `.aiqt/core/rules/`.

Excluded (19):

- Application-security rules with no surface here (no application code): authentication,
  authorization, federated-identity-flow, key-management, least-privilege-retrieval,
  symlink-resolution, ssrf-prevention, session-token-management, file-upload-handling.
- Personal-data rules (no end-user personal data in the maintenance scope):
  data-minimization, data-residency-retention, purpose-limitation, log-redaction,
  synthetic-fixture-data.
- No surface: atomic-claim-from-pool.
- Code-idiom rules, low value for a small content repository: match-surrounding-code,
  test-hermeticity, compatibility-or-migration, minimize-dependencies.

Basis: an expensive codex applicability assessment and a fable value ranking, both
2026-09-05, preserved in the durable store.

## Hooks

The AIQT Guardrails hooks plugin is enabled for dev-time sessions through
`.claude/settings.json` and the local marketplace at `plugin/`. The 13 core hooks are
active. The 9 orchestrator hooks stay inert: they require an orchestration registry
(`.aiqt/orchestration*.json`) this adoption did not add. Arming them is a recorded
follow-up (fable flagged three past incidents they would mechanically prevent).
