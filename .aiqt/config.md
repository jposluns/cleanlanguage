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

113 of 132 rules auto-load under `.claude/rules/aiqt/` and `.claude/rules/security/`.
The full 132-rule corpus is vendored as reference under `.aiqt/core/rules/`.

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

## Vendor integrity

`tools/check-aiqt-vendor.py` checks that the vendored files agree with the vendored manifest
and that the manifest agrees with `.aiqt/pin.toml`. Every tracked file under the pin's vendored
paths must match its manifest entry; the rule corpus and the hooks plugin must be present
whole; the active rule trees must match their rendered entries and hold exactly
`[active-rules] active` rules, with exactly the listed exclusions absent; and the manifest
digest and `.aiqt/release/root.txt` must match the pin. The pack `LICENSE` and `NOTICE` are
vendored byte for byte as `.aiqt/LICENSE` and `.aiqt/NOTICE` (the vendored licence decision); the pin maps each
to its path at the pack root, and the gate verifies them like any other vendored file. It
fails closed: an input it cannot read or parse is a failure that names the path. With
`--upstream DIR` it also re-derives every vendored file from the pack checkout at the pinned
commit and compares it byte for byte.
Its disclosed residual: without `--upstream` it proves internal consistency only, so an actor
who rewrites a file, its manifest entry, and the pin together passes. CI cannot reach the
pack checkout, so the upstream check is a QA-worker and pre-merge step until CI egress to the
pack repository is granted. The gate also does not re-derive applicability from
`applies.toml` and the profile: the exclusion list is adopter-declared, and a wrong exclusion
is a review finding, not a gate finding.

## Hooks

The AIQT Guardrails hooks plugin is enabled for dev-time sessions through
`.claude/settings.json` and the local marketplace at `plugin/`. The plugin registers 18
core hooks, and 16 of them can fire. The 14 earlier ones can: `gensrc_guard` was armed by
authoring `.aiqt/gensrc.json` (PR #156), which lists this repository's generated artefacts
(the sitemap and the portable text). The two new hooks that fire are described below.
`write_scope_guard` remains partly armed: without its per-slice `write-scope.json`
declaration, and with no committed `.aiqt/frozen.json` floor, its slice confinement and
frozen-floor denial are un-armed, but its structural cross-repository and nested-repository
write denial stays active. That denial now exempts one declared companion store: the
orchestration registry below names `/opt/cleanlanguage/private`, the durable record store,
so a guarded-tool write into that store is permitted and audited rather than denied, while a
guarded-tool write to any other outside repository is still denied.

Four core hooks are new in this re-vendor. `pgrep_self_match` denies a process check that can
match the shell running it: `pgrep`, `pkill`, or `pidwait` with `-f`, or `ps` piped into a
program given a pattern, unless the pattern is written as the bracket idiom (`[j]ob7`).
`git_stash_ref` allows a bare `git stash pop` or `git stash apply` with a note that it acts on
the top of the stash stack, and allows a named stash silently. `review_dispatch_pin` is inert
without a `review_dispatch` binding in a well-formed registry, and `review_workdir_hold` is
inert while no review-hold marker directory exists. The registry gate rejects a
`review_dispatch` key, so neither review hook arms in this repository.

The hook script requires Python 3.14 or later. Under an older `python3`, the eight hooks on
events that must not block (`diff_wall_stop`, `orch_dispatch_ledger`, the two lease heartbeat
hooks, `orch_prompt_stamp`, `orch_resume_audit`, `orch_stop_guard`, and `orch_teammate_idle`)
warn and allow, and every other hook exits 2, which denies every tool call that a PreToolUse
matcher of the plugin selects, Bash and the file tools included. The interpreter on the
maintainer host is Python 3.14.4 (observed 2026-10-30).

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

The upstream guard reads a command of at most 128 KiB (131,072 characters) in full. A longer
command is judged by a conservative fallback: it is denied when an AI name appears anywhere
in it together with a word that can record an identity, allowed at once when it names no AI,
and otherwise judged by raw-string identity contexts with no length bound. On the upstream
measuring host a command of about 40 to 48 MiB or longer can outlast the 10-second hook
timeout, and the platform contract does not say that a timed-out hook refuses the call, so
such a command may run with no deny. This is the upstream behaviour, and the maintainer
accepted it as a disclosed reduction, the commit identity read limit reduction, with a
regression test:
`tools/test-cmtidn-large-message.py` drives the vendored hook with a commit command of about
200 KiB whose message carries an AI co-author trailer, once at its start and once past the
128 KiB mark, and expects a deny each time. It does not test a command of tens of MiB.

A minimal orchestration registry (`.aiqt/orchestration.json`, version 1) arms part of the
orchestrator suite. It declares `companion_stores`, `record`, `lease`, `state_dir`, and an
empty `dispatch_tools`. Two of the 12 orchestrator hooks deny on the presence of the registry
alone: `orch_truncation_guard` and `orch_untracked_wait_loop`.
These deny an untracked background detach (a bare `&`), a truncated background capture (a
background dispatch piped into `head` or `tail`), and a backgrounded poll loop. The detach
scan reads a here-document body as data only when the whole command is nothing but plain
`cat` writes, each with one output redirect to a plain file and a quoted delimiter (`<<'EOF'`
or `<<"EOF"`), separated only by newlines. Every other body is read as code. A body `&`
under a quoted delimiter is still lifted, but a body with an odd number of apostrophes that
the scan reads at the outer quoting level, and a body `&` under an unquoted delimiter, are
denied although nothing detaches. Write such content with `cat > file` under a quoted
delimiter in a call of its own, or through the Write or Edit tool, which these Bash guards
never see.

That lifting carries one disclosed reduction, the heredoc lifting reduction: it applies even
when the body is fed to a
shell, so `bash <<'EOF'` with `sleep 30 &` in its body detaches a child with no deny from
the vendored guard. The maintainer accepted the heredoc lifting reduction with a compensating
control (the heredoc compensating hook decision):
the adopter-owned PreToolUse Bash hook `.claude/hooks/shell_heredoc_detach_guard.py`, outside
every vendored path and registered in `.claude/settings.json`, denies a quoted-delimiter
here-document fed to `sh`, `bash`, `dash`, `zsh`, or `ksh` whose body holds a backgrounding
`&`. Its disclosed residual is listed in full in the hook docstring. It includes a shell
reached through a variable, an alias, or a wrapper such as `sudo` or `nohup`, and a detacher
that carries no single `&` (`setsid`, `disown`, a nested `bash -c` string), which are not
seen, and an unreadable hook payload, which the hook allows with a note while the vendored
guard denies it.

The two new orchestrator hooks, `orch_lease_heartbeat_post` and `orch_lease_heartbeat_stop`,
never block and stay silent while the `lease` declares no `heartbeat` block, which the
registry gate rejects.

The declared `lease` makes scope live: while the lease file is present, non-empty, and
fresh, every session whose working directory resolves to this checkout and which can
reach the lease file
is in scope, so the scope-gated hooks fire. `orch_dispatch_ledger` records each background
launch in `dispatch-ledger.jsonl`, and `orch_prompt_stamp` stamps each human prompt in
`turn-state.json`, both under `state_dir`. `orch_stop_guard` and `orch_teammate_idle` share
one decision core. With no AEI enumerator declared, a turn-end Stop in scope is denied on
`NO_ENUMERATOR` unless the operator escape sentinel `ESCAPE-ALLOW-YIELD` in `state_dir`
releases it; on the maintainer host that sentinel is a root-owned file (observed 2026-10-29),
and each release is logged as an operator escape event. The denial has two further exits.
It is bounded: after two denials since the last human prompt (the loop bound), or when the
Stop event reports that a stop hook is already active, the Stop is allowed with the
unresolved items reported as findings, and the forced exit is recorded for the next resume
audit while open work remains or the backlog is not enumerable. An unreadable denial counter
counts as the bound reached. If the denial counter cannot be saved to `turn-state.json`, the
guard fails open instead: it allows the Stop with a warning, since an unsaved counter could
never reach the bound. `orch_yield_tool` is in scope but
finds no `yield_tools` roster, so it allows every scheduling call as out of roster.
`orch_ask_guard` denies a blocking question in `unattended` mode. In an attended-family mode,
where the registry also declares an enumerator, it judges the question against a fresh
backlog enumeration and denies it while granted open items are actionable. No `mode` record
and no enumerator are declared, so it allows and logs a fail-open audit event. Its mode
reader fails closed: a declared mode file that is present but cannot be opened or read, is
not a regular file (a FIFO, a device, or a socket), is larger than 1 MiB, or is not valid
UTF-8 reads as `unattended`, so the deny arms rather than disarms. `orch_resume_audit` reads
the registry at every SessionStart and writes `resume-barrier.json` under `state_dir`, arming
the barrier only when it finds divergence; while a barrier is armed, `orch_resume_barrier`
surfaces a one-time warning on a mutation outside the record surfaces and blocks nothing.

One caution: a malformed (`bad`) registry is fail-safe for the write path (`companion_stores`
empties, so cross-repository writes deny), but the scope-gated guards do not react to it
uniformly. `orch_stop_guard` fails open with a warning and records no guard event;
`orch_dispatch_ledger` silently allows without recording; `orch_ask_guard` allows; and
`orch_yield_tool` fails closed, denying a scheduling call, so a malformed registry blocks
scheduling immediately, even with no `lease` or `mode`. `review_dispatch_pin` reacts most
strongly: it withholds every Bash call as UNVERIFIABLE until an operator repairs the registry,
so a malformed registry blocks all Bash use at once. To keep a
corrupt registry from reaching a session, `tools/check-orchestration-registry.py` (run by the
Orchestration registry workflow) rejects a structurally invalid `.aiqt/orchestration.json`
before it lands. Stage 2 of item 28.2, which arms the rest of the suite, is deferred and
relies on that gate. It is planned as two pull requests. The first extends the gate to
validate the stage-2 keys (`enumerator`, `yield_tools`, `mode`, `staleness`, `escape`,
`attestations`, and `mistakes_register`) and adds the AEI backlog enumerator, the backlog
migration tool, the orchestration doctor, and their tests, with no registry change. The second
declares those keys, `attestations` and
`mistakes_register` only if the maintainer adopts them, while the escape sentinel stays in
place, so the enumerator first runs in shadow; the sentinel is removed only after that shadow
period and an acknowledged notice to lab_infra. `truth` has no reader in the vendored hook and
stays rejected. A value review flagged three past incidents that `orch_dispatch_ledger`,
`orch_truncation_guard`, and `orch_resume_audit` would mechanically prevent.
