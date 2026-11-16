---
name: verifier-panel
description: Adopter-owned practice for this project's verifier panel, narrower than the fallback the vendored verifier-diversity rule allows, and meeting that rule's third-family clause for a critical change.
---

# Verifier panel

Adopter-owned, under the reserved `.claude/rules/external/` namespace. The vendored rule
`.claude/rules/aiqt/10-QUALI-verifier-diversity.md` stays unedited. That rule allows, and does
not require, a fallback to an extra pass by a family already on the panel where no further model
family is available; this project never uses that fallback (maintainer decision, 2026-11-14).
This rule meets that rule's clause "A critical change adds a third family": a critical change
has its third family from its first DISCOVERY round (maintainer decision, Entry 124,
2026-11-15). A critical change is a change to a security-relevant gate, a guard or hook change,
or a change to release-integrity code; a security-control review (sandbox, filter and permission
checks included) is a review of a critical change, and a doubtful classification counts as
critical, the heavier tier when in doubt (coordinator rulings under the maintainer's delegation,
2026-11-15); the vendored rule does not define the word. The clause
binds only a critical change, so nothing in this rule departs from it: a change that is not
critical has its third family from its sixth DISCOVERY round (maintainer decision, Entry 90,
2026-11-15), which the clause does not require at all. The orchestrator classifies each item as
critical or not by reading its diff, and counts a doubtful classification as critical, with its
reason recorded.

- The panel's families are claude, agy (gemini) as the second family in every panel except
  where gemini is genuinely unreachable and its seat goes to codex as set out below, and codex
  as the third family from the first DISCOVERY round of the QA cycle for a critical change, a
  security-control review included, and from the sixth DISCOVERY round for every other change.
  Every VERIFY round, a light item's dual-family QA run, and the first 5 DISCOVERY rounds of a
  change that is not critical have no seat for that family, so their panel is claude and the
  holder of the gemini seat, which is gemini, or codex as the stand-in set out below
  (maintainer decisions, 2026-11-15). Every VERIFY round of a critical change keeps the
  standard VERIFY panel, claude executing plus gemini static; before the sixth DISCOVERY round,
  a critical change's DISCOVERY panel is claude, codex and gemini, and its convergence needs
  all 3, with equal weight and every finding checked at source (coordinator rulings under the
  maintainer's delegation, 2026-11-15).
- A second claude review never fills a family's seat, nor does any other second review by a
  family that already holds a seat, however it is primed.
- codex reviews only through a brief worded neutrally as a review for any issues to fix before
  release: no wording that sets it against the change, asks it to disprove the change, or frames
  the review as a security review. Where 1 brief would serve several families, codex gets its own
  neutral brief, and the other families may keep the review framing.
- A failed leg, of any family, is a leg that FAILED LEG in `.claude/commands/flow.md` defines as
  failed; that definition is the same for every family (maintainer decision, Entry 125,
  2026-11-15), and each family keeps its own re-issue terms, as set out below and in flow.md.
  Its quote and leg-failure conditions bind review legs only, not seed or drafter output, whose
  cited evidence is checked at source, and a failed claude leg is re-issued as the claude leg
  of the next round, under the same-family rule (coordinator rulings under the maintainer's
  delegation, 2026-11-15).
- When a family is genuinely unreachable, the reduction is recorded. Where that family is gemini
  and the panel has no codex seat, codex takes the gemini seat as the stand-in, through its own
  neutral brief, only while gemini is genuinely unreachable and only where the panel has no codex
  seat of its own: every VERIFY round, a light item's QA runs, and the first 5 DISCOVERY rounds
  of a change that is not critical; in a DISCOVERY round whose panel holds a codex seat, it never
  stands in and sits only in its own seat, and a genuinely unreachable gemini leaves the gemini
  seat owed on the terms below for the seat of a failed gemini leg. The seat of any other
  unreachable family goes to a reachable family that holds no seat (codex, through its own
  neutral brief); where there is none, the seat stays owed, and the step that needs it holds,
  until a leg of that family delivers a verdict, a failed leg not counting, or the item parks. A
  codex or gemini seat owed from a light item's QA runs lapses when the item is regraded, and the
  regraded item's DISCOVERY panel governs from its first DISCOVERY round, so a light item
  regraded and found critical enters its first DISCOVERY round with all 3 families (coordinator
  ruling under the maintainer's delegation, 2026-11-15). A failed stand-in leg or
  owed leg is re-issued in the next round in the family of the seat it fills: for the gemini
  seat, gemini when it is reachable, with codex standing in again only while gemini is still
  genuinely unreachable and only where the panel of that next round has no seat of codex's own;
  in a DISCOVERY round whose panel holds a codex seat, it never stands in, so a failed stand-in
  leg whose next round is such a round (for a change that is not critical, a failed stand-in leg
  of the fifth DISCOVERY round) leaves the seat it fills owed on the terms below for the seat of
  a failed gemini leg. A codex stand-in leg
  re-issued in this way is the gemini seat's re-issue, not codex's own: the single re-issue of a
  codex leg binds only the codex seat, and the `ORCH_MAX_FAILOVERS=1` bound is unaffected.
- A failed gemini leg is re-issued to gemini with a slim brief that gives the file pointers and
  line ranges to read, with no count of re-issues; it is never waived and never replaced by a
  claude review. Its seat stays owed until a gemini leg delivers a verdict, a failed leg not
  counting, and the obligation ends when the item converges or parks.

`.claude/commands/flow.md` (FAILED LEG, the CODEX ROLE LIMIT and VERIFIER DIVERSITY) sets how
this applies in the `/flow` loop, including where the codex leg of a security-control review is
dispatched.
