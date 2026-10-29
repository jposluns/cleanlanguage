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

`commit_identity` (cmtidn) denies a git command whose tokens attribute a commit to a
recognized AI identity, Claude, Anthropic, OpenAI, Codex, Copilot, or Gemini among them, as
author, committer, or co-author, whether in a `Co-Authored-By` trailer, an `--author` value, a
`GIT_AUTHOR` or `GIT_COMMITTER` assignment, or a `user.name` or `user.email` config set. A
detected identity is denied absolutely, with no escape hatch. Detection scans the command
itself: it ignores an AI product name in an ordinary commit message, and it does not inspect an
identity already inherited from existing git config, so a session configures a human commit
identity rather than relying on the scan alone. This repository requires the same for Claude in
its [root `CLAUDE.md`](../CLAUDE.md): the maintainer is the sole author, with no Claude
co-author or session trailer.

A minimal orchestration registry (`.aiqt/orchestration.json`, version 1) arms part of the
orchestrator suite. It declares `companion_stores`, `record`, `lease`, `state_dir`, and an
empty `dispatch_tools`. Two of the 10 orchestrator hooks gate on the presence of the registry
alone: `orch_truncation_guard` and `orch_untracked_wait_loop`.
These deny an untracked background detach (a bare `&`), a truncated background capture (a
background dispatch piped into `head` or `tail`), and a backgrounded poll loop. They carry
one disclosed residual that touches a common idiom: the detach scan does not model
here-document bodies, so a foreground Bash heredoc whose body contains a literal `&` or an
odd number of apostrophes is denied as though it were a detach. Write multi-line content
through the Write or Edit tool (which these Bash guards never see) or through `printf` rather
than a Bash heredoc when the body carries such characters.

The declared `lease` makes scope live: while the lease file is present and fresh, every
session whose working directory resolves to this checkout and which can reach the lease file
is in scope, so the scope-gated hooks fire. `orch_dispatch_ledger` records each background
launch in `dispatch-ledger.jsonl`, and `orch_prompt_stamp` stamps each human prompt in
`turn-state.json`, both under `state_dir`. `orch_stop_guard` and `orch_teammate_idle` share
one decision core. With no AEI enumerator declared, a turn-end Stop in scope is denied on
`NO_ENUMERATOR` unless the operator escape sentinel `ESCAPE-ALLOW-YIELD` in `state_dir`
releases it; on the maintainer host that sentinel is a root-owned file (observed 2026-10-29),
and each release is logged as an operator escape event. `orch_yield_tool` is in scope but
finds no `yield_tools` roster, so it allows every scheduling call as out of roster.
`orch_ask_guard` denies only in `unattended` mode; no `mode` record is declared, so it allows
and logs a fail-open audit event. `orch_resume_audit` reads the registry at every
SessionStart and writes `resume-barrier.json` under `state_dir`, arming the barrier only when
it finds divergence; while a barrier is armed, `orch_resume_barrier` surfaces a one-time
warning on a mutation outside the record surfaces and blocks nothing.

One caution: a malformed (`bad`) registry is fail-safe for the write path (`companion_stores`
empties, so cross-repository writes deny), but the scope-gated guards do not react to it
uniformly. `orch_stop_guard` fails open with a warning; `orch_dispatch_ledger` silently allows
without recording; and `orch_yield_tool` fails closed, denying a scheduling call, so a
malformed registry blocks scheduling immediately, even with no `lease` or `mode`. To keep a
corrupt registry from reaching a session, `tools/check-orchestration-registry.py` (run by the
Orchestration registry workflow) rejects a structurally invalid `.aiqt/orchestration.json`
before it lands. Stage 2 of item 28.2, which arms the rest of the suite, is deferred and
relies on that gate. It is planned as two pull requests. The first extends the gate to
validate the stage-2 keys (`enumerator`, `yield_tools`, `mode`, `staleness`, `escape`,
`attestations`, and `mistakes_register`) and adds the AEI backlog enumerator and its tests,
with no registry change. The second declares those keys, `attestations` and
`mistakes_register` only if the maintainer adopts them, while the escape sentinel stays in
place, so the enumerator first runs in shadow; the sentinel is removed only after that shadow
period and an acknowledged notice to lab_infra. `truth` has no reader in the vendored hook and
stays rejected. A value review flagged three past incidents that `orch_dispatch_ledger`,
`orch_truncation_guard`, and `orch_resume_audit` would mechanically prevent.
