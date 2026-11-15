---
name: verifier-panel
description: Adopter-owned practice for this project's verifier panel, narrower than the fallback the vendored verifier-diversity rule allows.
---

# Verifier panel

Adopter-owned, under the reserved `.claude/rules/external/` namespace. This rule narrows, and
does not override, the vendored rule `.claude/rules/aiqt/10-QUALI-verifier-diversity.md`, which
stays unedited. That rule allows, and does not require, a fallback to an extra pass by a family
already on the panel where no further model family is available; this project never uses that
fallback (maintainer decision, 2026-11-14).

- The panel's families are claude, agy (gemini) as the second family in every panel except
  where gemini is genuinely unreachable and its seat goes to codex as set out below, and codex
  as the third family from the sixth DISCOVERY round of the QA cycle, a security-control review
  included. The first 5 DISCOVERY rounds, every VERIFY round, and a light item's dual-family QA
  run have no seat for that family, so their panel is claude and the holder of the gemini seat,
  which is gemini, or codex as the stand-in set out below
  (maintainer decision, 2026-11-15).
- A second claude review never fills a family's seat, nor does any other second review by a
  family that already holds a seat, however it is primed.
- codex reviews only through a brief worded neutrally as a review for any issues to fix before
  release: no wording that sets it against the change, asks it to disprove the change, or frames
  the review as a security review. Where 1 brief would serve several families, codex gets its own
  neutral brief, and the other families may keep the review framing.
- When a family is genuinely unreachable, the reduction is recorded. Where that family is gemini
  and the panel has no codex seat, codex takes the gemini seat as the stand-in, through its own
  neutral brief, only while gemini is genuinely unreachable and only where the panel has no codex
  seat of its own: the first 5 DISCOVERY rounds, every VERIFY round, and a light item's QA runs;
  from the sixth DISCOVERY round on, it never stands in and sits only in its own seat, and a
  genuinely unreachable gemini leaves the gemini seat owed. The seat of any other unreachable
  family goes to a reachable family that holds no seat (codex, through its own neutral brief);
  where there is none, the seat stays owed and the step that needs it holds until the family
  returns or the item parks. A codex or gemini seat owed from a light item's QA runs lapses when
  the item is regraded, and the regraded item's DISCOVERY panel governs from its first DISCOVERY
  round. A failed stand-in leg or owed leg is re-issued in the next round in
  the family of the seat it fills: for the gemini seat, gemini when it is reachable, with codex
  standing in again only while gemini is still genuinely unreachable and only where the panel of
  that next round has no seat of codex's own; from the sixth DISCOVERY round on, it never stands
  in, and a failed stand-in leg of the fifth DISCOVERY round leaves the seat it fills owed while
  gemini is unreachable. A codex stand-in leg
  re-issued in this way is the gemini seat's re-issue, not codex's own: the single re-issue of a
  codex leg binds only the codex seat, and the `ORCH_MAX_FAILOVERS=1` bound is unaffected.
- A failed gemini leg is re-issued to gemini with a slim brief that gives the file pointers and
  line ranges to read, with no count of re-issues; it is never waived and never replaced by a
  claude review. Its seat stays owed until a gemini leg delivers a verdict, and the obligation
  ends when the item converges or parks.

`.claude/commands/flow.md` (the CODEX ROLE LIMIT and VERIFIER DIVERSITY) sets how this applies
in the `/flow` loop, including where each codex review is dispatched.
