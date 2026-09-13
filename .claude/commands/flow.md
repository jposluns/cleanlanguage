# /flow (cleanlanguage, interim local command)

INTERIM. This command's own inlined text below is authoritative for cleanlanguage and is reviewed
through this repository's PR gate. It adapts the fleet /flow standard, whose co-owned reference copy is
`/opt/inbox/FLOW.md` (reconciled with lab_infra's `docs/operating-model.md`, the NORMATIVE source that governs where the two differ); that reference is a
cross-check, not an unreviewed override of this file. When lab_infra renders a shared `/flow` command
(their TODO 208, the on-ramp to the future Orch plugin), adopt it THROUGH this repository's normal
review, then delete this file; do not switch to it sight-unseen. `/flow` is a REMINDER; the mode is
always on.

## The loop (invariant)

2 interlocking loops. The APPLY loop is strictly SERIAL: 1 backlog item at a time, implement -> QA ->
merge. The PLAN-PRODUCTION pipeline runs ALONGSIDE, in parallel, raising upcoming items to
execution-ready. CARDINAL RULE: parallelism lives ONLY in research (seeds, plan-combines, QA reads);
APPLIES ARE NEVER PARALLEL (1 branch, 1 plan, 1 writer at a time).

Keep-ahead buffer: at every invocation, merge, and resume, keep at least 3 upcoming items pre-worked to
execution-ready; where possible pick one that can be worked CONCURRENTLY while another item's QA is
pending, so the loop never idles on QA. The buffer check is a NUDGE, never a stop.

## The durable store (cleanlanguage state)

All backlog and session state lives in the machine-local durable store at `/opt/cleanlanguage/private/`
(orchestrators-group-readable; pool workers CANNOT read it, see below):
- `TODO.md`: the backlog, whose ORDER is the selection order. `DONE.md`: the closed-work ledger.
- `open-findings.md`: findings (a non-terminal row blocks new work). `pending-decisions.md`: open
  decisions with pre-drafted option blocks.
- `session-handoff.md`: the resume handoff. `session-state.md`: the concurrency LEASE
  (Active-session / Status / Last-heartbeat-UTC), acquired at entry, refreshed at merges and on cadence,
  released by /handoff.
Records-first: a decision not written here did not happen. Store git-commits may be externally blocked
(TODO 32); when so, records land on disk and the blocker is tracked, never skipped. Existing-file store
writes go through an in-session subagent, so the writes stay off the console, and are verified against
only the affected file(s).

## Each cycle

1. REFRESH: read the board from `/opt/cleanlanguage/private/TODO.md` (order = selection) and check `/opt/cleanlanguage/private/open-findings.md` (a non-terminal row blocks new work). If a gate is
   red with a confirmed defect, finish the unit in hand then FIX the source first (anything-wrong-first).
2. FEED THE PIPELINE: top the buffer up to at least 3 execution-ready; dispatch seed/combine fan-out
   non-blocking; move on.
3. SELECT the top actionable item.
4. GRADE the tier (light | substantive | sensitive), per the machine-local
   `/opt/cleanlanguage/.claude/CLAUDE.md` "Working method" section; in doubt, heavier. Record it.
   Escalation is immediate; de-escalation needs a maintainer decision + a recorded basis.
5. AUTHORIZE within the standing grant. Not covered: attended -> surface a work-naming go, hold THIS
   item, and continue other independent queued work (a question never halts independent work);
   unattended -> DEFER (propose a ?HOLD on the affected STEP, route to the next independent item), never
   self-grant, never self-author a block.
6. RUN the tier (below).
7. CLOSE: evidence-grounded completion (enumerate files, re-read, quote support, search contradictions);
   AIQT self-check before the completion claim; records rotation (TODO delete + DONE add) in the same
   change; clear focus.
8. PAUSE (after a merge, after a plan is verified pre-implementation, or when the queue composition
   changed): refresh; if an attended boundary is open, surface accumulated decisions ONE AT A
   TIME (per .claude/rules/maintainer-questions.md); list the next items; continue on already-authorized
   safe actions.
9. NOTHING ACTIONABLE: seeds/combines/QA in flight -> keep the pipeline topped up + read-only prep on
   upcoming verified-DISJOINT items; re-enter on the next delivery. Nothing in flight -> run
   blocked-verification (below); only on genuine whole-set exhaustion, close on green via /handoff.

## The seeds -> plan -> implementation pipeline (cleanlanguage tooling)

Pool workers (dispatched by `orch-verify`) run READ-ONLY in the repo workdir and CAN read this
repository, but CANNOT read the private store, `/opt/inbox`, or the machine-local CLAUDE.md. So a seed or
QA brief that depends on any of those must EMBED that context, and the orchestrator self-verifies every
private-context reference at source.

Per item:
(a) SEED BRIEF: 1 self-contained brief embedding all needed context (problem, exact file/line facts,
    constraints, deliverable shape, acceptance criteria).
(b) SEEDS: `orch-verify claude|codex|gemini <brief> /opt/cleanlanguage/cleanlanguage --expensive`, the
    same brief to all 3 in parallel. A family genuinely unreachable OR at its cost cap is
    skip-and-note (combine at a minimum of 2, queue a re-combine when it returns), never a block.
(c) COMBINE with Fable: `orch-verify claude <combine-brief> ... --expensive` (the --expensive claude tier
    is claude-fable-5). The combiner ADJUDICATES (state settled design; name disagreements + recommend;
    do not average into mush; discard hallucinated claims, verify at source). Fallback when Fable is
    exhausted: `orch-verify codex <combine-brief> ... --model gpt-5.6-sol --effort xhigh` (an explicit
    override; note --expensive codex is gpt-6-astra, not this). NEVER gemini as combiner of record;
    NEVER orchestrator self-synthesis as the combiner.
(d) PLAN: land it with a numbered step list, a file manifest, an acceptance/verification section, a
    QA-tier declaration, and a rollback note. Execution-ready only when it passes that shape.
(e) IMPLEMENT (serial): the orchestrator VERIFIES the plan against the seeds + live tree, may dispatch an
    implementation DRAFT to a worker, then FINALIZES it serially, re-verifying every line at source, as
    the SOLE writer/merger. Commit BEFORE dispatching QA (QA pins a revision); then run the tier's QA, fix at the WIDTH OF THE DEFECT CLASS, re-QA on the fixed state, and merge.

GEMINI ROLE LIMIT: gemini may SEED and QA but NEVER plan-combines or drafts the implementation.

PROHIBITED: dispatch seeds in the background then END THE TURN before collecting them. STATE, DO NOT
PROMISE: collect through the tracked background mechanism that survives to completion.

AIQT HOLD: plan-production throughput NEVER shortens a change's per-tier QA.

## Tiers (per the machine-local /opt/cleanlanguage/.claude/CLAUDE.md)

- LIGHT (quick fix / bookkeeping / version bumps / record edits): implement directly; mechanical gates;
  DUAL-family QA (claude + codex; gemini excluded on cost, which is allowed only because 2 families still
  meet the verifier-diversity floor).
- SUBSTANTIVE (skill/site-corpus change; new/edited gate/linter/hook/tool; multi-surface; control value /
  citation / normative rule; new feature): the full pipeline; TRI-family adversarial QA weighting codex;
  validate every finding at source; up to 4 fixing rounds; if it has not converged, trigger a premise review (re-derive the problem from fresh observation) and escalate the ITEM with a too-many-rounds flag and recommendation, continuing other authorized work. The round limit alone never closes the session.
- SENSITIVE (gate-blind correctness AND delicate scale AND high escaped-error cost, all 3): substantive
  plus the high-assurance harness (independent adversarial verifiers, deterministic apply, a persistent
  register). No de-escalation without a maintainer decision.

VERIFIER DIVERSITY (QA, every tier): a required family is dropped only when genuinely UNREACHABLE, never
for cost; cost never buys the reduction. When a required family is genuinely unreachable, run an independent, differently-primed second pass in a separate clean context as the recorded fallback, and re-run the dropped family once it returns. QA is dispatched read-only via `orch-verify`; judge by the
result signal, not by grepping worker output.

## Gates and merge (cleanlanguage)

Merge only via a PR merged on GREEN required checks, read through `tools/ci-status.sh <sha>` (it reads the
check-runs API; the `actions/runs` and `commits/<sha>/status` endpoints are blind to the required
Cloudflare Pages check, so never rely on them), AND only when no unresolved review thread requests changes. Never a
bypass flag. Generated artefacts (sitemap, portable text) are regenerated, never hand-edited. Commit
identity is the maintainer's, with no AI author/co-author/session trailer.

## Blocked-verification (before any "blocked"/"nothing to do")

Enumerate the backlog from `/opt/cleanlanguage/private/TODO.md` and, per remaining item, show the
observed, terminal blocker from a closed set (maintainer-decision-unreachable,
irreversible-needs-confirmation, failing-check, source-unavailable, maintainer-directed-hold). A blocker
counts only when it is EXTERNALLY GRANTED, proven by provenance: recorded in an artefact the maintainer
controls and the assistant cannot write; a self-authored "blocked"/"hold" is a proposal, not a grant, and
gates only the affected STEP, never the item or the session. A pending wait, in-flight QA, partial
evidence, or absent authorization is NEVER blocked; all fail toward WORK. Only on genuine whole-set
exhaustion (each item shown terminally blocked) close on green via /handoff, never a bare mid-turn stop.

## Mode, decisions, reversibility

- MODE (attended | unattended) parameterizes the question policy/timer/routing; it GRANTS NO authority.
  Absent = attended (conservative). The ONE governed transition is a decision-timeout switching
  attended -> unattended (the safe/conservative direction only). An inbound operator message is a
  TRANSIENT attended boundary and does NOT silently flip the mode.
- DECISIONS: blocking + attended -> surface immediately, ONE AT A TIME, in the four-role shape. The repo
  `.claude/rules/maintainer-questions.md` sets the base shape (Option A recommended, B and C viable, D
  free-form); the machine-local/home four-role layer refines A into "predicted" (the choice drawn from
  the maintainer-decisions record) plus "best on the merits", then "maximal", then "free-form"; use
  that layered shape. Blocking + unattended -> record BLOCKED only under the provenance test above, route
  to the next independent item; if all items genuinely depend on it, close via /handoff. Non-blocking ->
  append to `/opt/cleanlanguage/private/pending-decisions.md` with a pre-drafted four-role block.
- REVERSIBILITY GATE (every mode): only a closed allowlist auto-continues unattended/at timeout (observe;
  verify-ephemeral; authorial-local on the authorized branch; read-only worker dispatch; gate/QA runs;
  open a PR; merge a green routine PR under the standing grant). Everything irreversible or outward, and
  every authorial CHOICE, DEFERS. A timeout is NEVER an authorization source.

## Standing disciplines (every mode)

AIQT self-check at cycle start, before each commit, and before each completion claim. Express
authorization before a plan-initiating unit of work. Evidence-grounded completion at close. Lease
acquired at entry, refreshed at merges and on cadence, released by /handoff. Records-first. ALWAYS-ON
PEER-COMMS: running `inbox-read` and helping other orchestrators is a standing duty in EVERY mode, never
held or deferred; report worker/pool and shared-infra issues to lab_infra; only genuinely public,
irreversible, or commitment-creating publishes are ever held. The machine-local `/orch` and `/handoff`
commands bracket the loop: `/orch` enters `/flow`; `/flow` closes via `/handoff`.
