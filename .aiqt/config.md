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

107 of 126 rules auto-load under `.claude/rules/aiqt/` and `.claude/rules/security/`.
The full 126-rule corpus is vendored as reference under `.aiqt/core/rules/`.

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
`.claude/settings.json` and the local marketplace at `plugin/`. All 14 core hooks can
fire: `gensrc_guard` was armed by authoring `.aiqt/gensrc.json` (PR #156), which lists
this repository's generated artefacts (the sitemap and the portable text).
`write_scope_guard` remains partly armed: without its per-slice `write-scope.json`
declaration, and with no committed `.aiqt/frozen.json` floor, its slice confinement and
frozen-floor denial are un-armed, but its structural cross-repository and nested-repository
write denial stays active. That denial now exempts one declared companion store: the
orchestration registry below names `/opt/cleanlanguage/private`, the durable record store,
so a guarded-tool write into that store is permitted and audited rather than denied, while a
guarded-tool write to any other outside repository is still denied.

A minimal orchestration registry (`.aiqt/orchestration.json`, version 1) now exists. It
declares only `companion_stores`, so of the 10 orchestrator hooks it arms just the two that
gate on the registry's mere presence: `orch_truncation_guard` and `orch_untracked_wait_loop`.
These deny an untracked background detach (a bare `&`), a truncated background capture (a
background dispatch piped into `head` or `tail`), and a backgrounded poll loop. They carry
one disclosed residual that touches a common idiom: the detach scan does not model
here-document bodies, so a foreground Bash heredoc whose body contains a literal `&` or an
odd number of apostrophes is denied as though it were a detach. Write multi-line content
through the Write or Edit tool (which these Bash guards never see) or through `printf` rather
than a Bash heredoc when the body carries such characters.

The other eight orchestrator hooks do not fire under this registry, but for different
reasons, so they are not uniformly scope-gated. Five are scope-gated and stay inert because
the registry declares no `lease` and no `mode`, so `scope_live` is false: `orch_yield_tool`,
`orch_dispatch_ledger`, `orch_prompt_stamp`, `orch_stop_guard`, and `orch_teammate_idle`.
`orch_ask_guard` fires only in `unattended` mode, which is not declared, and otherwise only
logs a fail-open audit event. `orch_resume_barrier` is not scope-gated at all: it fires only
once `orch_resume_audit` has armed a `resume-barrier.json`, which has not happened, and
`orch_resume_audit` itself reads the registry at SessionStart and is warn-only.

One caution for the deferred arming: a malformed registry is fail-safe for the write path
(`companion_stores` empties, so cross-repository writes deny), but the scope-gated stop,
yield, and dispatch guards fail OPEN, with a warning, on a `bad` registry. That bites only
once a `lease` or `mode` arms them, so `tools/check-orchestration-registry.py` (run by the
Orchestration registry workflow) rejects a structurally invalid `.aiqt/orchestration.json`
before it lands, and the follow-up that arms the full suite (a `lease`, a `mode`, and an AEI
enumerator so the stop and yield guards can judge the backlog, the deferred 28.2 work) relies
on that gate. A value review flagged three past incidents that `orch_dispatch_ledger`,
`orch_truncation_guard`, and `orch_resume_audit` would mechanically prevent.
