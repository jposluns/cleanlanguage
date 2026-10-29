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
(b) SEEDS: `orch-verify claude|gemini <brief> /opt/cleanlanguage/cleanlanguage --expensive`, the
    same brief to both in parallel. A family genuinely unreachable OR at its cost cap is
    skip-and-note (combine at a minimum of 2 by adding an independent, differently-primed second seed,
    given the same facts but a different framing and run in a separate clean context, drawn from the seed
    family that can run; queue a re-combine when the skipped family returns), never a block to seeding;
    when neither combiner in (c) can combine, the COMBINE step is still HELD, as (c) states. If no seed
    family can run (each is unreachable or at its cost cap), the SEED step is HELD in the same way that
    (c) holds the COMBINE step: the item is not execution-ready, the hold is recorded as a ?HOLD on
    this STEP, the run routes to the next independent item, and each later FEED THE PIPELINE step
    (cycle step 2) retries the seeds only when a seed family can run: `orch-verify --pick` for that
    family succeeds AND that family is not at its cost cap.
(c) COMBINE with Fable: `orch-verify claude <combine-brief> ... --super-expensive` (claude-fable-5 at
    high effort). The combiner ADJUDICATES (state settled design; name disagreements + recommend;
    do not average into mush; discard hallucinated claims, verify at source). Fallback when Fable is
    exhausted or unreachable: `orch-verify claude <combine-brief> ... --expensive` (claude-opus-5-5 at
    xhigh effort).
    NEVER codex or gemini as a combiner, of record or otherwise;
    NEVER orchestrator self-synthesis as the combiner.
    The ONLY lawful combiners are Fable and that fallback (NEVER any other claude tier);
    when neither can combine, the COMBINE step is HELD: the item is not execution-ready, the hold is
    recorded as a ?HOLD on this STEP (self-authored, so a proposal and never a grant, per
    Blocked-verification), the run routes to the next independent item, and each later FEED THE
    PIPELINE step (cycle step 2) retries the COMBINE only when a lawful combiner can run:
    `orch-verify --pick claude` succeeds AND claude is not at its cost cap.
(d) PLAN: land it with a numbered step list, a file manifest, an acceptance/verification section, a
    QA-tier declaration, and a rollback note. Execution-ready only when it passes that shape.
(e) IMPLEMENT (serial): the orchestrator VERIFIES the plan against the seeds + live tree, may dispatch an
    implementation DRAFT to a claude worker, then FINALIZES it serially, re-verifying every line at
    source, as the SOLE writer/merger. Commit BEFORE dispatching QA (QA pins a revision); then run the
    tier's QA, fix at the WIDTH OF THE DEFECT CLASS, re-QA on the fixed state, and merge.

GEMINI ROLE LIMIT: gemini may SEED and QA but NEVER plan-combines or drafts the implementation.

CODEX ROLE LIMIT: codex may QA ONLY; it NEVER seeds, plan-combines, drafts the implementation, or fixes.
Every codex leg is dispatched with `ORCH_MAX_FAILOVERS=1` (one account, no failover). A codex leg that
ends at that bound in any form (`orch-verify` `FAILOVER_LIMIT` (exit 4), or an empty, degenerate, or
5xx chain), or that ends `EXHAUSTED` (exit 5, rate-limited or out of quota), or that is stopped by a
cost cap, or that otherwise delivers no verdict (a dispatch timeout, a dispatch auth failure, or a
delivery that lacks the agreed completion evidence; an UNVERIFIABLE result is a delivered verdict, not a
failed leg), is a failed leg, NOT an unreachable family, whatever `orch-verify` advises about the family.
It is recorded, then re-issued at most once, after a wait between attempts
(not cycle step 8, PAUSE), never with a higher limit; the single re-issue happens at the
first later FEED THE PIPELINE step (cycle step 2) at which `orch-verify --pick codex` succeeds
AND codex is not at its cost cap. While undelivered, its seat is OWED, a ?HOLD on
that QA STEP (a proposal, per Blocked-verification): while it is owed, the run limits work on
other items to pipeline top-up and read-only prep on upcoming verified-DISJOINT items, as
cycle step 9 allows, and starts no other apply while this branch is open; the seat is never
dropped or substituted on that basis. A review that hunts for ways past a security
control (a review whose task includes, in whole or in part, finding inputs, commands, or paths that a
guard, hook, sandbox, filter, or permission check fails to block) NEVER goes to codex: run it on
claude + gemini and, where the tier needs a third family, add an independent, differently-primed
claude pass in a separate clean context, recorded as a fleet-rule substitution (a seat change that a
fleet rule, such as this limit, requires). The orchestrator classifies each review at brief time and
records the classification in the item QA record (the QA notes on the item's entry in
`/opt/cleanlanguage/private/TODO.md`, carried into `DONE.md` at CLOSE).

PROHIBITED: dispatch seeds in the background then END THE TURN before collecting them. STATE, DO NOT
PROMISE: collect through the tracked background mechanism that survives to completion.

AIQT HOLD: plan-production throughput NEVER shortens a change's per-tier QA.

## Tiers (per the machine-local /opt/cleanlanguage/.claude/CLAUDE.md)

- LIGHT (quick fix / bookkeeping / version bumps / record edits): implement directly; mechanical gates;
  DUAL-family QA (claude + codex, or claude + gemini where the CODEX ROLE LIMIT bars codex or codex is
  genuinely unreachable; gemini is otherwise excluded on cost, which is allowed only because 2 families
  still meet the verifier-diversity floor).
- SUBSTANTIVE (skill/site-corpus change; new/edited gate/linter/hook/tool; multi-surface; control value /
  citation / normative rule; new feature): the full pipeline; TRI-family adversarial QA weighting codex
  within the CODEX ROLE LIMIT; where that limit bars codex or codex is genuinely unreachable, that
  weighting passes to gemini (or, if gemini is also genuinely unreachable, to the fallback pass for
  the gemini seat under VERIFIER DIVERSITY), and the codex seat is filled as VERIFIER DIVERSITY states;
  validate every finding at source; up to 4 fixing rounds; if it has not converged, trigger a premise
  review (re-derive the problem from fresh observation) and escalate the ITEM with a too-many-rounds
  flag and recommendation, continuing other authorized work. The round limit alone never closes the
  session.
- SENSITIVE (gate-blind correctness AND delicate scale AND high escaped-error cost, all 3): substantive
  plus the high-assurance harness (independent adversarial verifiers, deterministic apply, a persistent
  register). No de-escalation without a maintainer decision.

VERIFIER DIVERSITY (QA, every tier): a required family is dropped only when genuinely UNREACHABLE,
never for cost; cost never buys the reduction. A codex seat barred by the CODEX ROLE LIMIT is filled
by gemini only where gemini does not already hold a seat (a dual-family tier); where it does, the
CODEX ROLE LIMIT claude pass fills it. Either way, the substitute is recorded as a fleet-rule
substitution, not as an unavailability drop. When a required family is genuinely unreachable, record
the drop and give its seat to a reachable, unbarred family that holds no seat (gemini, for codex on a
dual-family tier); only where there is none, run an independent, differently-primed second pass in a
separate clean context as the recorded fallback, and re-run an unreachable family once it returns.
Each lost seat gets its own substitute, so a tri-family tier with codex barred and gemini genuinely
unreachable runs claude plus 2 independent, differently-primed claude passes, each in its own clean
context: the fallback pass for the gemini seat and the fleet-rule substitution pass for the codex seat.
QA is dispatched read-only via `orch-verify`; judge by the result signal, not by grepping worker output.

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
  `.claude/rules/maintainer-questions.md` sets that shape in its "Superseded in part" note: the four
  roles replace its Option A to D lettering. See that note for the roles, their order, their
  definitions, and which role carries the recommendation; this file does not restate them.
  Blocking + unattended -> record BLOCKED only under the provenance test above, route
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
