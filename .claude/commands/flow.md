# /flow (cleanlanguage, interim local command)

INTERIM. This command's own inlined text below is authoritative for cleanlanguage (except for the
tiers and the QA cycle, which the machine-local "Working method" section governs; that section
carries the same floor as the CODEX ROLE LIMIT below, that a critical change is never graded
light, so the 2 agree on it; and except for the unattended
vote rule, which the machine-local "Put decisions to the maintainer in the four-role shape" section
governs) and is reviewed
through this repository's PR gate. It adapts the fleet /flow standard. The reference copy of that
standard is the host's deployed `/usr/local/share/orch/operating-model.md`, a render of lab_infra's
`docs/operating-model.md`; that source is NORMATIVE and governs wherever the deployed copy differs
from it. The deployed copy replaces the former reference, `/opt/inbox/FLOW.md`, which no longer
exists, and is a cross-check, not an unreviewed override of this file. lab_infra stated on 2026-11-07
that the deployed copy is stale and will be redeployed, so the cross-check of this file's mode
section against it waits for the redeployed copy. When lab_infra renders a shared `/flow` command
(their TODO 208, the on-ramp to the future Orch plugin), adopt it THROUGH this repository's normal
review, then delete this file; do not switch to it sight-unseen. `/flow` is a REMINDER; the mode is
always on.

## The loop (invariant)

2 interlocking loops. The APPLY loop is strictly SERIAL: 1 backlog item at a time, implement -> QA ->
merge, or park. The PLAN-PRODUCTION pipeline runs ALONGSIDE, in parallel, raising upcoming items to
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
  decisions with pre-drafted option blocks, each decision that the session could not ask because an
  AskUserQuestion guard denied it, and a record of each decision-timeout switch (see the MODE bullet
  below).
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
   `/opt/cleanlanguage/.claude/CLAUDE.md` "Working method" section, which never grades a critical
   change light, the same floor as the CODEX ROLE LIMIT below. Record the grade.
   Escalation is immediate; de-escalation needs a maintainer decision + a recorded basis.
5. AUTHORIZE within the standing grant. Not covered: attended-autonomous -> surface a work-naming go
   and hold only this item's AUTHORIZE STEP until the go is given, while research and preparation
   on the item, and other independent queued work, continue (a question never halts independent
   work); when an AskUserQuestion guard denies the go, the MODE bullet below sets what the session
   does; unattended -> DEFER (propose a ?HOLD on the affected STEP, route to the next independent
   item), never self-grant, never self-author a block.
6. RUN the tier per that machine-local "Working method" section (see "Tiers and the QA cycle" below).
7. CLOSE: evidence-grounded completion (enumerate files, re-read, quote support, search contradictions);
   AIQT self-check before the completion claim; records rotation (TODO delete + DONE add) in the same
   change; clear focus.
8. PAUSE (after a merge, after a plan is verified pre-implementation, or when the queue composition
   changed): refresh; if the mode is attended-autonomous or an operator boundary (an inbound operator
   message) is open, surface accumulated decisions, up to 4 per round (per
   .claude/rules/maintainer-questions.md); list the next items; continue on already-authorized safe
   actions. When an AskUserQuestion guard denies a question, the MODE bullet below sets what the
   session does.
9. NOTHING ACTIONABLE: seeds/combines/QA in flight -> keep the pipeline topped up + read-only prep on
   upcoming verified-DISJOINT items; re-enter on the next delivery. Nothing in flight -> run
   blocked-verification (below); only on genuine whole-set exhaustion, close on green via /handoff.

## The seeds -> plan -> implementation pipeline (cleanlanguage tooling)

Pool workers (dispatched by `orch-verify`) run READ-ONLY in the repo workdir and CAN read this
repository, but CANNOT read the private store, `/opt/inbox`, or the machine-local CLAUDE.md. So a seed or
QA brief that depends on any of those must EMBED that context, and the orchestrator self-verifies every
private-context reference at source.

Per item (the machine-local "Working method" section sets which of these steps a tier skips):
(a) SEED BRIEF: 1 self-contained brief embedding all needed context (problem, exact file/line facts,
    constraints, deliverable shape, acceptance criteria).
(b) SEEDS: `orch-verify claude|gemini <brief> /opt/cleanlanguage/cleanlanguage --expensive`, the
    same brief to both in parallel; agy (gemini) is the second family. A family genuinely
    unreachable OR at its cost cap is skip-and-note, never a block to seeding: the family that can
    run seeds, the skipped family's seed is OWED, and no second seed from the family that ran takes
    its place. While a seed is owed, the COMBINE step is HELD as (c) holds it, and each later FEED
    THE PIPELINE step (cycle step 2) re-issues the owed seed only when that family can run:
    `orch-verify --pick` for that family succeeds AND that family is not at its cost cap. A seed leg
    that runs on gemini and delivers no seed is a failed seed leg (the quote and leg-failure
    conditions of FAILED LEG below bind review legs only, not seed output): its seed
    is OWED in the same way, so the COMBINE step stays HELD until the owed seed arrives, and it is
    re-issued on the re-issue terms VERIFIER DIVERSITY sets for a failed gemini leg, never replaced
    by a claude seed. When neither combiner in (c) can combine, the COMBINE step is still HELD, as
    (c) states. If no seed
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
(e) IMPLEMENT (serial): the orchestrator VERIFIES the plan, where the tier has one, against the
    seeds + live tree, may dispatch an implementation DRAFT to a claude worker, then FINALIZES it
    serially, re-verifying every line at
    source, as the SOLE writer/merger. Commit BEFORE dispatching QA (QA pins a revision); then run the
    tier's QA and merge only as the machine-local "Working method" section allows.

GEMINI ROLE LIMIT: gemini may SEED and QA but NEVER plan-combines or drafts the implementation.

FAILED LEG (every family, every tier): this is the 1 definition of a failed leg, and every other
place in this file that names a failed leg, except the failed seed leg of step (b), refers to it.
A review leg of any family, claude, gemini or codex, is a failed leg, NOT an unreachable family, whatever `orch-verify` advises about the
family, when it ends in any of these 3 ways (maintainer decision, Entry 125, 2026-11-15):
(1) it delivers no verdict: it ends `FAILOVER_LIMIT` (exit 4), or in an empty, degenerate, or
5xx chain, at the failover bound of its own dispatch; it ends `EXHAUSTED` (exit 5, rate-limited
or out of quota); it is stopped by a cost cap; or it otherwise delivers no verdict (a dispatch
timeout, a dispatch auth failure, or a delivery that lacks the agreed completion evidence); an
UNVERIFIABLE result is a delivered verdict, not a failed leg;
(2) a quote in it is absent from its source;
(3) a quote in it breaches the whole-line rule of the maintainer decisions of Entries 61, 63, 64
and 69 (2026-11-14 and 2026-11-15; the coordinator's correction recorded with Entry 127,
2026-11-15, gives the rule's entries as these 4): a single-line quote must be a whole line, from
the line's first character to its last, and a range quote must be whole lines; a quote counts as found
when its exact text is the whole of its cited line or of a line within 1 line of it, a range
quote when its joined text is the whole of the cited lines or of the same lines within 1 line of
the cited range, and either of them also when it matches in that way only once each line's
leading spaces are stripped or only without its Markdown formatting marks (backticks, emphasis
asterisks or underscores), with each offset, range, collapse and mark recorded; a quote of only
part of a line, text more than 1 line off, changed or missing words, a dropped comment marker,
or any other changed character fails it.
These quote and leg-failure conditions bind review legs only, not seed or drafter output, whose
cited evidence is checked at source (coordinator ruling under the maintainer's delegation,
2026-11-15).
Every QA brief states this rule in the same words for every family and asks for the same claims
block, and 1 checker applies it to the legs of every family. Wherever this file keeps a seat
OWED until a leg of a family delivers a verdict, a failed leg does not end it, whether the family
is claude, gemini or codex. Each family keeps its own re-issue terms: the CODEX ROLE LIMIT sets
them for a leg in codex's own seat, VERIFIER DIVERSITY sets them for a gemini leg and for a
failed stand-in leg or owed leg, and a failed claude leg is re-issued as the claude leg of the
next round, under the same-family rule (coordinator ruling under the maintainer's delegation,
2026-11-15).

CODEX ROLE LIMIT: codex may QA ONLY; it NEVER seeds, plan-combines, drafts the implementation, or fixes.
Every codex leg is dispatched with `ORCH_MAX_FAILOVERS=1` (1 account, no failover), which is the
failover bound of its dispatch under FAILED LEG. A codex leg that fails in any of the ways FAILED
LEG sets is a failed leg, NOT an unreachable family, whatever `orch-verify` advises about the family.
It is recorded, then re-issued at most once, after a wait between attempts (not cycle step 8,
PAUSE), never with a higher limit, and only when `orch-verify --pick codex` succeeds AND codex is
not at its cost cap; the machine-local "Working method" section sets when, and as which leg, the
re-issue runs. This single re-issue binds only a leg in codex's own seat: a failed codex stand-in
leg in the gemini seat is re-issued on the terms VERIFIER DIVERSITY sets for that seat. While
a failed leg in codex's own seat is undelivered, that seat is OWED, a ?HOLD on
that QA STEP (a proposal, per Blocked-verification): while it is owed, the run limits work on
other items to pipeline top-up and read-only prep on upcoming verified-DISJOINT items, as
cycle step 9 allows, and starts no other apply while this branch is open; the seat is never
dropped or substituted on that basis. The rest of this paragraph sets when an owed codex seat
ends, and the machine-local "Working method" section sets when an item parks. A codex seat still
owed after its single re-issue is filled by the codex leg of the next DISCOVERY round whose panel
holds a codex seat: for a critical change, as defined below, the next DISCOVERY round; for any
other change, the next DISCOVERY round from the sixth on, since its first 5 DISCOVERY rounds have
no seat for that family; after the last DISCOVERY round that section sets, no VERIFY round fills
that seat, which stays owed until the item parks (maintainer decisions, Entries 90 and 124,
2026-11-15).
That section sets the case of a light item, except that a codex seat owed from a light item's QA
runs lapses when the item is regraded, and the regraded item's DISCOVERY panel governs from its
first DISCOVERY round (maintainer decision, Entry 98, 2026-11-15), so a light item regraded and
found critical enters its first DISCOVERY round with all 3 families (coordinator ruling under
the maintainer's delegation, 2026-11-15).
codex may review any change, including a change to a guard, hook, sandbox, filter, or permission
check, but only through a brief worded neutrally as a review for any issues to fix before release, for
example "review this code for any issues that should be fixed before release": no wording that
sets codex against the change, asks it to disprove the change, or frames the review as a security
review (maintainer decision, 2026-11-14). The neutral wording binds the codex brief: where 1
brief would serve several families, codex gets its own neutral brief, and the other families
may keep the review framing. A CRITICAL change is a change to a security-relevant gate, a
guard or hook change, or a change to release-integrity code; a security-control review (a review
of a change that touches, in whole or in part, a guard, hook, sandbox, filter, or permission
check) is a review of a critical change (maintainer decision, Entry 124, 2026-11-15, which
narrows the decision of Entry 95, 2026-11-15, back to a codex seat from the first DISCOVERY
round for such a review, and coordinator ruling under the maintainer's delegation, 2026-11-15,
which keeps sandbox, filter and permission checks in it); and a change whose classification is
doubtful counts as critical, the heavier tier when in doubt (coordinator ruling under the
maintainer's delegation, 2026-11-15). A critical change is never graded light:
it is of at least the substantive tier, and of the tier within that floor that the machine-local
"Working method" section gives it, which governs that tier (coordinator ruling under the
maintainer's delegation, 2026-11-15). VERIFIER
DIVERSITY sets its panel: the third seat goes to codex (neutral brief) from its first DISCOVERY
round. Only this orchestrator's individual codex seat takes the codex leg of a security-control
review, never the multi-seat codex pool that uses API keys (a pool now being onboarded;
infrastructure orchestrator ruling, 2026-11-14). The orchestrator classifies each item as
critical or not by reading its diff, and counts a doubtful classification as critical, with its
reason recorded; it
classifies each review at brief time, checks each codex brief's wording against this limit, and
records the classifications and the check in the item QA record (the QA notes on the item's
entry in `/opt/cleanlanguage/private/TODO.md`, carried into `DONE.md` at CLOSE).

PROHIBITED: dispatch seeds in the background then END THE TURN before collecting them. STATE, DO NOT
PROMISE: collect through the tracked background mechanism that survives to completion.

AIQT HOLD: plan-production throughput NEVER shortens a change's per-tier QA.

## Tiers and the QA cycle (per the machine-local /opt/cleanlanguage/.claude/CLAUDE.md)

The tiers (light, substantive, and sensitive) and the per-change QA cycle (DISCOVERY and VERIFY
rounds, the round budget, the premise review, failed rounds, convergence, and parking) are defined
ONLY in that file's "Working method" section; do not restate them here, except that FAILED LEG
above defines a failed leg of every family and names the round in which a failed claude leg is
re-issued, the CODEX ROLE LIMIT above defines a critical change, bars a light grade for it
(the same floor as that section's), and names the rounds that seat the third family, which
round fills an owed codex seat, and when an owed codex seat ends, and VERIFIER DIVERSITY below
names the rounds that seat the third family, the VERIFY panel and the convergence of a critical
change, the round in which an owed gemini leg or a failed stand-in leg runs, and when an owed
gemini or claude seat ends; the CODEX ROLE LIMIT and VERIFIER DIVERSITY name, in that order, the
lapse of an owed codex seat and of an owed gemini seat when a light item is regraded. Pool workers
cannot read it, so a brief that depends on it EMBEDS the parts a leg needs (see the pipeline
section above).
The GEMINI ROLE LIMIT, FAILED LEG, CODEX ROLE LIMIT, and VERIFIER DIVERSITY stay here and bind
every tier; so do the 3 tier rules kept here: in cycle step 4 (GRADE), escalation is immediate and
de-escalation needs a maintainer decision and a recorded basis; in the CODEX ROLE LIMIT, a critical
change is never graded light, the same floor as the "Working method" section's; and the AIQT
HOLD above. The
"Working method" section in that file sets when a light item is regraded and how a regraded item
enters the QA cycle.

VERIFIER DIVERSITY (QA, every tier): agy (gemini) is the second family in every panel, except
where gemini is genuinely unreachable and its seat is given to codex as set out below. codex, on
the terms of the CODEX ROLE LIMIT, is the third family from the first DISCOVERY round of the QA
cycle for a critical change, as that limit defines it, a security-control review included, and
from the sixth DISCOVERY round for every other change (maintainer decisions, Entries 90 and 124,
2026-11-15); every VERIFY round, a light item's dual-family QA run, and the first 5 DISCOVERY
rounds of a change that is not critical have no seat for that family, so their panel is claude
and the holder of the gemini seat, which is gemini, or codex as the stand-in set out below
(maintainer decision, 2026-11-15). Every VERIFY round of a critical change keeps the standard
VERIFY panel, claude executing plus gemini static; before the sixth DISCOVERY round, a critical
change's DISCOVERY panel is claude, codex and gemini, and its convergence needs all 3, with
equal weight and every finding checked at source (coordinator rulings under the maintainer's
delegation, 2026-11-15). A second claude
review never fills a family's seat, nor does any other second review by a family that already
holds a seat, however it is primed (maintainer decision, 2026-11-14; project rule
`.claude/rules/external/verifier-panel.md`). A required family is dropped only when genuinely
UNREACHABLE, never for cost; cost never buys the reduction. When a required family is genuinely
unreachable, record the drop. Where that family is gemini and the panel has no codex seat, give
the gemini seat to codex as the stand-in, through a neutral brief on the CODEX ROLE LIMIT terms,
only while gemini is genuinely unreachable (maintainer decision, 2026-11-15), and only where the
panel has no codex seat of its own: every VERIFY round, a light item's QA runs, and the first 5
DISCOVERY rounds of a change that is not critical; in a DISCOVERY round whose panel holds a codex
seat, which is each DISCOVERY round of a critical change and the sixth and each later DISCOVERY
round of any other change, it never stands in and sits only in its own seat, and a genuinely
unreachable gemini leaves the gemini seat OWED on the terms set below for
gemini (coordinator ruling under the maintainer's delegation, 2026-11-15). The seat of any other
unreachable family goes to a reachable family that holds no seat (codex, through a neutral brief on
the same terms); where there is none, the seat stays OWED, a ?HOLD on the QA STEP that needs it
(a proposal, per Blocked-verification), and the unreachable family's leg runs once the family
returns, but only
for an item that has not parked (the machine-local "Working method" section sets when an item
parks) or that the maintainer resumes. The owed seat's terms depend on the family. For codex,
they are the terms the CODEX ROLE LIMIT sets for an owed codex seat. For gemini, they are the
terms set below for the seat of a failed gemini leg: the seat stays OWED until a gemini leg
delivers a verdict, with the limits on other work that the CODEX ROLE LIMIT sets while a codex
seat is owed, and is never dropped or substituted on that basis; once gemini returns, its leg is
the gemini leg of the next round of the QA cycle; the obligation ends when the item converges or
parks; and the codex-only terms named below do not apply. For claude, the seat stays OWED until
a claude leg delivers a verdict, with those same limits on other work, and is never dropped or
substituted on that basis; the obligation ends when the item parks. A failed stand-in leg or
owed leg is re-issued in the next round in the family of the seat it fills: for the gemini seat,
gemini when it is reachable, with codex standing in again only while gemini is still genuinely
unreachable (maintainer decisions, 2026-11-15), and only where the panel of that next round has no
seat of codex's own; in a DISCOVERY round whose panel holds a codex seat, it never stands in, so a failed
stand-in leg whose next round is such a round (for a change that is not critical, a failed
stand-in leg of the fifth DISCOVERY round) leaves the seat it fills OWED on the terms set above
for gemini (coordinator ruling under
the maintainer's delegation, 2026-11-15). A codex stand-in leg re-issued in this way is the
gemini seat's re-issue, not codex's own: the single re-issue of a codex leg binds only the codex
seat, and the `ORCH_MAX_FAILOVERS=1` bound is unaffected (coordinator ruling under the
maintainer's delegation, 2026-11-15).
A gemini leg that fails in any of the ways FAILED LEG sets is a failed leg, NOT an unreachable
family; the failover bound under FAILED LEG is that of its own dispatch. The codex-only terms (the
`ORCH_MAX_FAILOVERS=1` bound, the single re-issue, and the rule on which round fills a seat still
owed after that re-issue) do not apply to it.
Its re-issue terms: it is recorded, then re-issued to gemini, after a wait between
attempts, and only when `orch-verify --pick gemini` succeeds AND gemini is not at its cost cap,
with a slim brief that gives the file pointers and line ranges to read rather than pasting whole
deliveries inline (infrastructure orchestrator rulings, 2026-11-14), with no count of
re-issues; it is never waived and never replaced by a claude review. In QA, each re-issue is
the gemini leg of the next round of the QA cycle (a DISCOVERY round while one remains, then a
VERIFY round, within the round budget the machine-local "Working method" section sets). Until a
gemini leg delivers a verdict, its seat stays OWED, a ?HOLD on that QA STEP (a proposal, per
Blocked-verification), with the limits on other work that the CODEX ROLE LIMIT sets while a codex
seat is owed; the seat is never dropped or substituted on that basis, and the obligation ends
when the item converges or parks. A gemini seat owed from a light item's QA runs, whether its leg
failed or gemini was unreachable, lapses when the item is regraded, as an owed codex seat does,
and the regraded item's DISCOVERY panel governs from its first DISCOVERY round (coordinator ruling
under the maintainer's delegation, 2026-11-15).
QA is dispatched read-only via `orch-verify`, except a claude seat that the maintainer directs to run
in-session, on the terms the machine-local "Working method" section sets; judge by the result signal, not
by grepping worker output.

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

- MODE (attended-autonomous | unattended) parameterizes the question policy/timer/routing; it GRANTS NO
  authority. The session reads it from the host's mode record, `/opt/orch-operator/operating-mode`,
  which only the host's mode writer, `orch-set-mode`, writes, and only with these 2 values; a record
  may still hold the retired value "attended", which the writer does not write. The session reads
  the record at entry, when it enters `/flow` at the start of a session (a resume starts a new
  session, so it is such an entry), and again at each task boundary: the end of any numbered step
  of "Each cycle" above, and the end of any item, whether it closes or parks. A mode change is an
  operator act, so a change that the operator makes through `orch-set-mode` takes effect at the
  session's next read.
  Wherever a step or rule in this file depends on whether the mode is attended-autonomous or
  unattended, that mode is the session's mode: the mode the session last read the record as, under
  this bullet's rules, after any decision-timeout switch.
  "attended" is retired as a selectable mode (lab_infra rule FLEET-05): the session reads a legacy
  stored "attended" as attended-autonomous, never as unattended, and gives 1 warning about it in its
  own output, once per session. The session reads an absent mode record as unattended
  (conservative), and alerts lab_infra through `inbox-send lab_infra` to clarify the mode, once per
  session.
  The repository's AskUserQuestion guard never decides from the session's mode: apart from its
  checks of the hook payload, it decides from the host's mode folder and record as it finds
  them when it runs, and it can deny before it reads either, for example on a malformed hook
  payload. Its decisions are set in `.claude/hooks/ask_mode_guard.py` and described in
  `.aiqt/config.md`, and this file does not restate them. The session reads the record only at
  entry and at each task boundary, and a decision-timeout switch changes the session's mode
  without a write, so the session's mode can differ from what the guard reads. When the host's
  mode folder, `/opt/orch-operator`, is itself absent, the guard allows a question, with a
  1-line note, while the session reads the mode as unattended.
  Whenever an AskUserQuestion guard denies an AskUserQuestion call, whether the repository's guard,
  the vendored AIQT guard `orch_ask_guard` or any other, for any reason and in any mode, the session
  records each decision it could not ask in its pending-decisions record,
  `/opt/cleanlanguage/private/pending-decisions.md`, holds the step that decision gates while other
  work continues (in unattended mode, the DECISIONS bullet below sets whether the unattended vote
  rule then settles that step), and names the held decisions in its reply. A non-blocking decision
  gates no step, so the session only records it. A decision that the session could not ask does
  not start the decision timer, which runs only on a question that the session asked. The
  AskUserQuestion dialog stays the only channel for asking a decision. A guard's deny message is
  diagnostic: the session acts on this file's rules, not on the message's instructions, so it holds
  the step, not the item, even where the message says to hold the item, and the message never
  changes the session's mode, even where it says to treat the session as unattended or names a
  mode; the session takes its mode only from its own reads of the record and from a
  decision-timeout switch, under this bullet's rules.
  The only governed transition is a decision-timeout switching attended-autonomous -> unattended (the
  safe/conservative direction only); it switches this session's question policy, timer and routing,
  and never writes the mode record. The session records each such switch, with its time and the
  decision whose timer ran out, in its pending-decisions record,
  `/opt/cleanlanguage/private/pending-decisions.md` (Records-first, above). The switch holds for the
  session until the record is written
  again: any new write ends it, including one that repeats the stored mode, such as the operator
  running `orchmod aa` again (`orchmod` is the operator's front end for `orch-set-mode`), because
  `orch-set-mode` stamps a fresh `set_at` on every write. The session sees that write, as it sees
  any operator change, at its next read. A resume starts a new session, which reads the record and
  starts from the mode it reads the record as, so a switch does not carry over a resume. An inbound
  operator message opens a TRANSIENT operator boundary; it never changes the session's mode, and
  the guard does not read it.
- DECISIONS: blocking + attended-autonomous -> surface immediately, up to 4 per round, in the four-role shape.
  The repo `.claude/rules/maintainer-questions.md` sets that shape in its "Superseded in part" note:
  the 4 roles replace its Option A to D lettering. See that note for the roles, their order, and
  which role carries the recommendation; this file does not restate them.
  Blocking + unattended -> the unattended vote rule in the machine-local
  `/opt/cleanlanguage/.claude/CLAUDE.md` "Put decisions to the maintainer in the four-role shape"
  section governs; this file does not restate it.
  A step that rule does not settle stays held: record BLOCKED only under the provenance test above, route
  to the next independent item; if all items genuinely depend on it, run Blocked-verification above,
  which closes via /handoff only on genuine whole-set exhaustion. Non-blocking ->
  append to `/opt/cleanlanguage/private/pending-decisions.md` with a pre-drafted four-role block.
- REVERSIBILITY GATE (every mode): only a closed allowlist auto-continues unattended/at timeout (observe;
  verify-ephemeral; authorial-local on the authorized branch; read-only worker dispatch; gate/QA runs;
  open a PR; merge a green routine PR under the standing grant; carry out an option that the unattended
  vote rule settles, within the limits that rule sets). Everything irreversible or outward, and every
  authorial CHOICE that the unattended vote rule does not settle, DEFERS; a choice it settles continues
  only through that allowlist entry. A timeout is NEVER an authorization source.

## Standing disciplines (every mode)

AIQT self-check at cycle start, before each commit, and before each completion claim. Express
authorization before a plan-initiating unit of work. Evidence-grounded completion at close. Lease
acquired at entry, refreshed at merges and on cadence, released by /handoff. Records-first. ALWAYS-ON
PEER-COMMS: running `inbox-read` and helping other orchestrators is a standing duty in EVERY mode, never
held or deferred; report worker/pool and shared-infra issues to lab_infra; only genuinely public,
irreversible, or commitment-creating publishes are ever held. The machine-local `/orch` and `/handoff`
commands bracket the loop: `/orch` enters `/flow`; `/flow` closes via `/handoff`.
