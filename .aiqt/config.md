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

Excluded (19), grouped by exclusion reason (not by the rules' AIQT facet; for example
log-redaction is a SECI rule listed here for its personal-data subject). Full per-rule
reasoning is in the codex applicability assessment in the durable store.

- No application-code surface (9): authentication, authorization, federated-identity-flow,
  key-management, least-privilege-retrieval, symlink-resolution, ssrf-prevention,
  session-token-management, file-upload-handling.
- No end-user personal data in scope (5): data-minimization, data-residency-retention,
  purpose-limitation, log-redaction, synthetic-fixture-data.
- No shared-claim-pool surface (1): atomic-claim-from-pool. Judgement call: this repository
  dispatches workers concurrently, which is arguably a shared pool, but the orchestrator holds
  a single session lease and does not implement atomic pool claiming in its own code. Re-include
  if it gains a shared claim pool.
- Low value for a small content repository (4): match-surrounding-code, test-hermeticity,
  compatibility-or-migration, minimize-dependencies.

Basis: an expensive codex applicability assessment and a fable value ranking, both
2026-09-05, preserved in the durable store.

## Hooks

The AIQT Guardrails hooks plugin is enabled for dev-time sessions through
`.claude/settings.json` and the local marketplace at `plugin/`. Of the 14 core hooks, 13
can fire out of the box. Only `gensrc_guard` is wholly inert here: it needs
`.aiqt/gensrc.json`, which was not authored, so it never fires. `write_scope_guard`
is partly armed: without its per-slice `write-scope.json` declaration, and with no
committed `.aiqt/frozen.json` floor, its slice confinement and frozen-floor denial are
un-armed, but its structural cross-repository and nested-repository write denial stays
active in both regimes, so it still fires (a guarded-tool write landing outside this
repository is denied). Authoring a `gensrc.json` for this repository's generated artefacts
(the sitemap and the portable text) is a recorded follow-up. The 10 orchestrator hooks stay
inert: they require an orchestration registry (`.aiqt/orchestration*.json`) this adoption
did not add. Arming them is a recorded follow-up (a value review flagged 3 past incidents
they would mechanically prevent).
