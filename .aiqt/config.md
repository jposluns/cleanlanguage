# AIQT Guardrails adoption config

Adopter-owned. The pack updater does not overwrite this file. See `.aiqt/pin.toml`
for provenance and the adopted version.

## Profile

Active condition set: `always`, `tools-retrieval`, `writes-code`, `agent-harness`,
`multi-agent`; `personal-data` off. Equivalent to the Coding profile plus
`agent-harness` and `multi-agent`, since this repository is maintained with Claude
Code and a multi-agent orchestrator (worker dispatch, a concurrency lease, a durable
handoff store, attended-autonomous and sometimes unattended operation).

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
`.claude/settings.json` and the local marketplace at `plugin/`. The plugin registers 33
hooks: 12 orchestrator hooks and 21 others. The refresh to pack commit 9d249b47 added 9 of
them: 2 orchestrator hooks (`orch_lease_heartbeat_post` and `orch_lease_heartbeat_stop`) and
7 others (`clock_inject_failure`, `clock_inject_post`, `git_stash_ref`, `inline_errexit`,
`pgrep_self_match`, `review_dispatch_pin` and `review_workdir_hold`). The 2 clock hooks refuse
nothing: by the hook source, `clock_inject_post` (PostToolUse) and `clock_inject_failure`
(PostToolUseFailure) each add 1 context line holding the host clock read at that hook event,
after a tool call that ran; a call refused before it runs gets no reading, and the reading goes
stale as time passes. `gensrc_guard` was armed by authoring `.aiqt/gensrc.json` (PR #156),
which lists this repository's generated artefacts (the sitemap and the portable text), and
since that refresh it also watches Bash commands as well as Write and Edit calls.
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
empty `dispatch_tools`. 2 of the 12 orchestrator hooks deny on the presence of the registry
alone: `orch_truncation_guard` and `orch_untracked_wait_loop`.
These deny an untracked background detach (a bare `&`), a truncated background capture (a
background dispatch piped into `head` or `tail`), and a backgrounded poll loop.
`orch_truncation_guard` also denies, in every session, a Bash call whose payload it cannot
read or whose working directory it cannot walk. How the detach scan reads here-document
bodies and quotes comes from a recorded decision-table run for pull request 275, which passed
256 named forms, in 314 rows of a form and a working directory (a branch, and for each git form
a detached HEAD as well), to every Bash handler of the hook before the refresh and of the
refreshed hook; forms not named here were not tried. Through `orch_truncation_guard` the
refreshed hook denies:

- a here-document body that a shell runs and that holds a bare `&`: `bash`, `sh`, `bash -s` or
  `sh -s`, directly or piped from `cat`, under a quoted, partly quoted, backslashed or `<<-`
  delimiter, such as `bash <<'EOF'` with `sleep 100 &` in its body, the same through
  `cat <<'EOF' | bash`, and `sh <<'EOF'` with `sleep 100 &` and `wait`;
- a file written by `cat` from a quoted-delimiter body holding `sleep 100 &` and then run with
  `bash` or `source`;
- a bare `&` in a quoted-delimiter body that `tee`, `python3 -I -`, `ruby`, `wc -c`,
  `sed -n 1p` or a bare `> file` redirect reads, and a quoted-delimiter `cat > file` write of
  such a body followed by `ls 2>&1`;
- a bare `&` outside quotes in a body under an unquoted delimiter (`<<EOF`), whatever command
  reads it (the run tried `cat > file`, `python3 -I -` and `bash`);
- an apostrophe that leaves a quote open in a command that also holds an `&` (a bare `&`, a
  `2>&1` or an `&&`), unless the whole command is a plain `cat > file` or `cat >> file` write
  under `<<'EOF'` or `<<"EOF"`: the run denied such a write under `<<EOF` or `<<\EOF`,
  `cat <<'EOF' | tee file` and `tee file <<"EOF"` with `it's a & b` in the body, a
  quoted-delimiter write of `it's` followed by `ls 2>&1`, and `echo it's # a & b`;
- an apostrophe in a command that also holds, outside the here-document body, a word that can
  start a background job without an `&`: a quoted-delimiter write of `it's` followed by
  `setsid true`, or by `.` running the written file.

The refreshed hook does not deny the following forms, which the hook before the refresh denied
through `orch_truncation_guard` (65 rows, 43 distinct commands; the pull request 275
description lists every form id by class):

- a here-document of data written by `cat` (to a file, appended or to standard output), by
  `tee` or by a bare `> file` redirect, whose body holds an apostrophe (for a `cat` write, also
  an unterminated double quote), including an apostrophe beside a word that can start a
  background job (`coproc`, `disown`, `eval`, `setsid`, `source`, `.`, `<<<` or `<(`), and
  such a `cat` write followed by `echo done`;
- a `cat` write or a `cat` to standard output whose body, under `<<'EOF'` or `<<"EOF"`, holds an
  ampersand in data (`a & b`), with or without an apostrophe, including 2 such writes in 1
  command;
- `python3 -I -` with `print('it\'s')` in a quoted-delimiter body;
- `bash <<'EOF'` with `echo "unfinished` in its body, which leaves a double quote open and holds
  no `&`;
- a command with an open quote and no here-document: `echo it's`, `echo "unfinished`,
  `echo 'unfinished` and `echo "it`.

None of these 65 rows starts a command in the background. Neither hook denies these forms of
the run, each of which starts a background job: `bash -c "$(cat <<'EOF' ... EOF)"` and
`out="$(bash <<'EOF' ... EOF)"` with `sleep 100 &` in the body, `bash <<< 'sleep 100 &'`, a
script written by `printf 'sleep 100 &\n'` and then run with `bash`, and a body run by `bash`
that holds `coproc true` and no `&`. Neither denies a body run by `sh` that holds
`setsid true`, a `python3 -I -` here-document with an `&` or an apostrophe inside a
double-quoted Python string, under either delimiter, with or without a `2>&1` on its line or
after it, or a `perl` body with an `&` inside a Perl string.

Maintainer decision Entry 99 accepted the pack's decisions verbatim and named the list, by
class, of every form of this run that the refreshed hook no longer denies, in the pull request
275 description, as the recorded authorization for those forms; maintainer decisions Entry 59
and Entry 62 had already authorized 4 of them, all `cat > file` writes. Any form the maintainer
later objects to goes to guardrails as a seed. Against the earlier pin of this change,
730c039b, the same run moved 13 rows from deny to no decision, all data here-documents written
by `cat` whose body holds an apostrophe beside a word that can start a background job, and 40
rows from no decision to deny: the bodies that a shell runs, the write-then-run detach forms,
and the `tee`, `python3 -I -`, other-reader and `cat` write with `ls 2>&1` forms with a bare
`&` in a quoted-delimiter body. No form that starts a command in the background moved from
deny to no decision. Write multi-line content through the Write or Edit tool (which these Bash
guards never see) or through `printf` when the body carries such characters.

`gate_weakening` (gatdis) denies the 5 write-then-run commit probes that
`tools/test-gate-weakening-probes.py` holds: a script written by a here-document or by
`printf` that runs `git commit --no-verify` or `git commit -n`, then run with bash, sh or
python3. Other handlers deny some of them as well. In a recorded run of the probes whose hook
process could read every path that they name, the refreshed hook denied probe 1 through
`gate_weakening` and `git_discard`, probes 2, 3 and 5 through `gate_weakening` alone, and
probe 4 through `gate_weakening` and `protected_line`; probes 4 and 5 ran on a branch only.
`review_workdir_hold` also denies a probe when the hook cannot read a path that the probe
names (below). In the decision-table run, `gate_weakening` also denied 4 further
write-then-run commit forms that the hook before the refresh did not decide: a script written
by `tee` from a here-document and
run with bash, a script written by `echo` and run with bash, a here-document script run with
`source`, and a here-document script made executable with `chmod +x` and run by its path. It
does not deny every write-then-run commit that skips hooks. In hook runs, a
written script that runs `git -c core.hooksPath=/dev/null commit` (or `/var/empty`), and a
script decoded from base64 and then run with bash, got no decision from any of the 19 Bash
handlers. The direct `git -c core.hooksPath=/dev/null commit` and
`echo --no-verify | xargs git commit` forms get no decision from `gate_weakening`, as before
the refresh; in runs on a branch and on a detached HEAD, `protected_line` (artbr1) denied
both as a segment outside its commit grammar, which the hook before the refresh did not.

Since the refresh, `protected_line` (artbr1) denies a Bash `git commit` on a detached HEAD,
with the reason "Git or filesystem probe did not succeed cleanly", where the hook before the
refresh gave no decision: its probe of the branch that HEAD names fails when HEAD names none.

The decision-table run found 39 distinct forms that the hook before the refresh did not decide
and the refreshed hook denies. 4 are the detached-HEAD commits above (`git commit -m`,
`git commit --allow-empty` and `git commit -F` with 2 paths); the other 35:

- `protected_line` (artbr1), on a branch and on a detached HEAD, denies 14 commit forms: the
  2 direct core.hooksPath forms and the xargs form above, `command git commit`,
  `env git commit`, `git -c commit.gpgsign=false commit`, `git --literal-pathspecs commit`,
  `git -C . commit`, `git status && git commit`, `echo ready && git commit`,
  `git commit -m probe && echo done` and a commit with its output redirected to a file, as a
  segment outside its commit grammar; `git commit -m probe; true`, as not an uninterrupted
  `&&` chain; and `git commit -m $'probe'`, for its ANSI-C quoting. `gate_weakening` also
  denies the redirected and the `$'probe'` forms. On a detached HEAD only, it also denies
  `git commit --amend --no-edit`, `git commit -am probe` and `true && git commit -m probe`;
- `protected_line` denies ANSI-C or locale quoting in a command with no git word:
  `printf '%s\n' $'hello'`, `printf $'a\nb'`, `echo $'hello'` and `echo $"hello"`;
- `branch_root`, `gate_weakening`, `git_discard` and `protected_line` each deny a git alias
  defined on the command line (`git -c alias.c='commit --no-verify' c` and
  `git -c alias.s=status s`) and `git -C $D log`; `gate_weakening` denies `git -C "$D" log`;
- `gate_weakening` denies the 5 probes and the 4 further write-then-run forms above;
  `git_discard` also denies probe 1, and `protected_line` also denies probe 4 (probes 4 and
  5 ran on a branch only);
  `review_workdir_hold` also denies a probe when the hook cannot read a path that the
  probe names, as when the hook runs as another user, since it fails closed when it cannot
  probe the git identity of a directory that an absolute path in the command names, so
  whether it is among the handlers that deny a probe depends on who runs the hook;
- `orch_truncation_guard` denies a Bash call whose working directory does not exist.

In 10 further forms both hooks deny and the denying handlers differ, most often because
`protected_line` joins them.

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
`orch_ask_guard` denies only in `unattended` mode; no `mode` record is declared, so it allows
every question and, when it can resolve the repository and read a usable registry, tries to
append a fail-open audit event, an append that is best effort; otherwise it returns without
logging. `orch_resume_audit` reads the registry at every
SessionStart and writes `resume-barrier.json` under `state_dir`, arming the barrier only when
it finds divergence; while a barrier is armed, `orch_resume_barrier` surfaces a one-time
warning on a mutation outside the record surfaces and blocks nothing.

The host's operating-mode file is JSON, which `orch_ask_guard` cannot read, so this repository
adds its own guard for AskUserQuestion. `.claude/hooks/ask_mode_guard.py`, registered in
`.claude/settings.json`, reads `/opt/orch-operator/operating-mode`, a JSON object whose `"mode"`
member holds 1 mode for the whole host. The guard takes 2 values from the file's only writer,
the host's `orch-set-mode`, which the operator runs through `orchmod` and which accepts exactly
`"attended-autonomous"` (`orchmod aa`) and `"unattended"` (`orchmod ua`); a change to that list is
a change to this guard. It allows a question when `"mode"` is exactly `"attended-autonomous"`,
and in 1 other case: when `"mode"` is exactly `"attended"`, a legacy value that the writer does
not write, it reads the record as `"attended-autonomous"`, never as `"unattended"`, under the
maintainer's decision of 2026-11-07 adopting lab_infra's rule FLEET-05, and allows the question
with 1 warning that names the file and `"attended-autonomous"`. It denies,
naming the cause, when the hook payload has no string `tool_name`; when `/opt/orch-operator`
itself is absent, since the host then declares no operating-mode and removing that root-owned
directory must not disarm the guard, and that deny names the operator's remedy, which is to create
the directory, owned by root, writable by neither its group nor others, and searchable by the
session's user, for example with mode 0755, to run `orchmod aa`, and to let the session's user
read the mode file in it;
when `lstat` on `/opt/orch-operator`, which does not follow a symlink there, fails for any other
reason, such as a path component that is a regular file; when `/opt/orch-operator` itself is a
symlink, is not a directory, is not owned by uid 0, or is writable by its group or by others; when
the file is missing while `/opt/orch-operator` exists, unreadable, a symlink, on a path that holds
a symlink loop or too many symlinks, not a regular file, not owned by uid 0, writable by its group
or by others, over 4096 bytes, not strict UTF-8, not 1 JSON object, or holding a duplicate key;
when `"mode"` is absent, not a string, `"unattended"`, or any other value, including a case or
spacing variant of `"attended-autonomous"`, `"attended"`, or `"unattended"`; and when
the guard raises an exception before it prints its verdict. The `"unattended"` deny names the
remedy: the operator runs `orchmod aa`, since the file is root-owned and `orch-set-mode` writes it.
Every deny reason carries the record-and-continue instruction that `orch_ask_guard` gives, but
the guard writes no `pending-asks.jsonl` row. `tools/test-ask-mode-guard.py`, run by the
Orchestration registry workflow, tests it against files and directories that it creates under a
temporary directory, with 2 exceptions: the device case puts the mode file below `/dev/null`,
and the 2 owner rename cases have the guard open a readable file that another uid owns, the first
suitable one among `/etc/passwd`, `/etc/group`, `/etc/hosts` and the Python interpreter, or, run
as root, a file that they create and give to uid 65534. The guard stays as a second layer after
an upstream fix lets a re-vendored `orch_ask_guard` read the JSON file, under the adopted
defence-in-depth default. Residual: the guard covers only AskUserQuestion calls in sessions
that load this checkout's `.claude/settings.json`; it does not cover other checkouts,
other repositories, or non-Claude worker families; a session that can edit the guard or
`.claude/settings.json` can disarm it, and the edit shows in review only once it is committed; a
settings file that the repository does not track, such as `.claude/settings.local.json`, which
`.gitignore` ignores, or a user settings file outside the checkout, never shows in review, and
nothing in this repository shows or tests whether such a file can disable or override this hook;
on a host where `/opt/orch-operator` is absent, every AskUserQuestion call is denied with the
record-and-continue instruction; the guard trusts root, and it does not check `/opt` or any
directory above `/opt/orch-operator`: it checks `/opt/orch-operator` by path before it opens the
file, so whoever can write `/opt` can replace `/opt/orch-operator`, including between that check
and the open, and root controls the decision only while only root can write those directories;
the file holds 1 mode for the
whole host, so a session with the operator present is blocked while the host says unattended; the
4096-byte bound limits size, not time: the `lstat` of `/opt/orch-operator`, the open of whatever is
at the file's path, including a device node, which the guard opens before it checks for a regular
file, and the read of a regular file can each block, and each is bounded only by the hook's
10-second timeout, and the tests do not show what Claude Code does with the call when that timeout
expires; the guard's fail-closed handler covers only its argument parse, payload read and decision,
so before that handler runs the outcome depends on how the hook process ends: when `python3 -I`
cannot open the script, for example because the file is missing, it exits 2, which Claude Code's
hook contract treats as blocking for PreToolUse, so every AskUserQuestion call would be blocked, in
any mode, without the record-and-continue instruction, and if the hook process cannot start, such
as when `python3` is not on the hook shell's `PATH` (exit 127), is killed by a signal, or fails
while it writes its verdict, it ends without a complete verdict and with a status other than 0 or
2, which the contract treats as a non-blocking error, so the question would go through; both
outcomes are what the contract says, not something the tests observe; the legacy warning repeats
on every question while a usable record holds `"attended"`, since the guard keeps no state and
writes no file, and a session without root cannot rewrite the root-owned record; the operator runs
`orchmod aa` to rewrite it as `"attended-autonomous"`; the tests check only the warning the guard
prints, not whether Claude Code shows it to the user or to the model; and until the upstream fix
is re-vendored, `orch_ask_guard` allows every question and, when it can resolve the repository
and read a usable registry, tries to append a fail-open audit event, an append that is best effort.

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
`attestations`, and `mistakes_register`) and adds the AEI backlog enumerator, the backlog
migration tool, the orchestration doctor, and their tests, with no registry change. The second
declares those keys, `attestations` and
`mistakes_register` only if the maintainer adopts them, while the escape sentinel stays in
place, so the enumerator first runs in shadow; the sentinel is removed only after that shadow
period and an acknowledged notice to lab_infra. `truth` has no reader in the vendored hook and
stays rejected. A value review flagged three past incidents that `orch_dispatch_ledger`,
`orch_truncation_guard`, and `orch_resume_audit` would mechanically prevent.
