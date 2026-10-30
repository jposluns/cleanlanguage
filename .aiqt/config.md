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
without a `review_dispatch` binding in a well-formed registry, and the registry gate rejects a
`review_dispatch` key, so it cannot arm in this repository. `review_workdir_hold` needs no
binding and no registry key: it reads the review-hold marker files a dispatcher writes under the
common git directory (`aiqt/review-holds/` there), and it is inert only while no such marker
directory exists. No tool in this repository writes one, so it stays inert here until a
dispatcher writes a marker, and then it holds the marked worktree.

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
every vendored path and registered in `.claude/settings.json`, reads the command as text,
without parsing the shell, and denies it when three text tests all hold: a here-document
operator with a quote or a backslash after it on its physical line, an ampersand character
anywhere in the text (operators included), and a shell name anywhere in the text. A deny,
and an internal error, exit with status 2. The cost is over-refusal: a command chained with
`&&`, or carrying an ampersand redirection, that also holds a quoted here-document and a
shell name is denied although nothing detaches. The remedy is to split the command, so that
the here-document and the ampersand sit in separate calls, or to avoid the here-document. The
rule, its cost and its what-still-passes list, quoted from the hook docstring:

```text
The rule. This hook does not parse bash. It reads the command as text and denies it when all three of
these tests hold:
  1. a here-document operator, two less-than signs that no third less-than sign adjoins (so a
     here-string is not one), stands on a physical line that holds a quote (an apostrophe or a double
     quote) or a backslash anywhere after that operator;
  2. an ampersand character stands anywhere in the text, operators included: a double ampersand, an
     ampersand redirection and the stderr pipe all count;
  3. a shell name stands anywhere in the text: bash, dash, zsh or ksh as a substring of any word
     (case-sensitive, so ksh93 and mksh count), or sh as a word bounded on each side by a character
     that is not a letter or a digit, or by the edge of the text, with an optional digit suffix (sh5),
     or the variable SHELL or BASH expanded.
Each test reads the command both as written and with every backslash-newline pair removed, as bash
removes a line continuation, and test 3 also reads it with every quote and backslash removed, so a name
split by quotes or by a backslash still counts. The three need not be related: the operator, the
ampersand and the shell name may sit anywhere in the command.

RESIDUAL (disclosed; a coarse best-effort rule, not complete coverage):
  Cost, over-refusal. A command that holds the three is denied even when nothing detaches. This covers
  every command chained with a double ampersand, or carrying an ampersand redirection (such as 2>&1,
  &> or >&2) or the stderr pipe, that also holds a quoted here-document and a shell name; an
  ampersand that is only data, quoted, escaped, in a comment, in a case fall-through terminator or in an
  input duplication; a quote or a backslash after the operator that is not part of the delimiter, and two
  less-than signs that are no here-document operator at all (a left shift); and a shell name inside a
  longer word (dashboard, .bashrc, a file name ending in .sh), as an argument, in a shebang line or in
  prose. The remedy is to split the command, so that the here-document and the ampersand sit in separate
  calls, or to avoid the here-document (write the body to a file first, or pass it some other way); a
  job meant to run in the background goes through the tracked background dispatch (run_in_background).
  What still passes:
  1. A shell reached without its name in the text: through a variable other than SHELL or BASH, an
     alias or a function, a name built by an expansion or by ANSI-C quoting, sh glued to a letter or a
     digit before it (env -Ssh) or to a letter after it (shx), a name written in another case, another
     interpreter (ash, yash, posh, a renamed shell binary), a script file run directly, or eval, source
     or the dot command reading the body.
  2. A detacher with no ampersand character in the text: setsid, nohup, disown, coproc, at, a terminal
     multiplexer, or an ampersand built by an expansion (such as printf with an octal escape) and then
     run through eval or a nested shell.
  3. A command with no here-document operator followed on its line by a quote or a backslash: an
     unquoted delimiter, a here-string, a pipe from echo or printf, or a script file. This hook does not
     judge them; they are left to the vendored trkasy guard, and this hook does not establish which of
     them that guard catches.
  4. An unreadable hook payload (not JSON, or no command string) is allowed with a note; the vendored
     trkasy guard denies such a payload.
```

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
