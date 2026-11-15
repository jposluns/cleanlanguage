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
  where gemini is genuinely unreachable and its seat goes to another family as set out below,
  and codex as the third family where a tier needs one.
- A second claude review never fills a family's seat, nor does any other second review by a
  family that already holds a seat, however it is primed.
- codex reviews only through a brief worded neutrally as a review for any issues to fix before
  release: no wording that sets it against the change, asks it to disprove the change, or frames
  the review as a security review. Where 1 brief would serve several families, codex gets its own
  neutral brief, and the other families may keep the review framing.
- When a family is genuinely unreachable, the reduction is recorded and the family's seat goes to a
  reachable family that holds no seat; where there is none, the seat stays owed and the step
  that needs it holds until the family returns or the item parks.
- A failed gemini leg is re-issued to gemini with a slim brief that gives the file pointers and
  line ranges to read, with no count of re-issues; it is never waived and never replaced by a
  claude review. Its seat stays owed until a gemini leg delivers a verdict, and the obligation
  ends when the item converges or parks.

`.claude/commands/flow.md` (the CODEX ROLE LIMIT and VERIFIER DIVERSITY) sets how this applies
in the `/flow` loop, including where each codex review is dispatched.
