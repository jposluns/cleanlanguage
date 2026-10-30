---
corpus-id: vrfdlv
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [ACCUR, INTEG]
slug: verifier-delivery-completeness
---

# A degraded verifier delivery is not a verdict

A verifier's output counts as a verdict only if the verifier delivered one. Completeness has one test:
the delivery carries the positive evidence, agreed in advance by the verification, of a finished
verdict, whether a completion marker the verifier emits, the explicit verdict the verification asked
for, or both. A delivery lacking that agreed evidence, or truncated, empty, or errored, counts as no
verdict, never a pass, a vote, or a finding-free result.
A capture piped through a truncating sink is a degraded delivery, not a verdict, even if its retained
prefix looks complete.
Completeness is never inferred from output length, volume, or a reported problem's absence: a run cut
off before its verdict is indistinguishable from a clean one judged by silence or size. A delivery
failing this test is re-dispatched and contributes nothing; it alone does not justify reducing the
panel, since one failed delivery is not evidence that a verifier family is unavailable. A required
family leaves the panel only if genuinely unreachable, on the verifier-diversity rule's terms, and that
reduction is recorded and re-run when the family returns.
The same fail-closed posture holds when the verifier cannot read or access a required input it should
cover: it emits no permissive verdict over the gap but UNVERIFIABLE, the cannot-evaluate outcome
guard-input-soundness names, identifying the unread input. Terminal and fail-closed, not a transient
degraded delivery a re-dispatch can cure, it counts as not-passed, resolved by fixing the input, never a
clean, passing, or finding-free verdict. A clean verdict over a required input the verifier never read
is the false-clean this rule guards against, meeting the posture check-fails-closed-on-unreadable
requires of a gate unable to read its input.
A worker run ending in a safety refusal or provider content stop, known by the provider's stop or result
signal, not by matching output text, counts as a refusal, not a delivery, whatever its status line: the
step needing it is held and the refusal reported to the maintainer, never routed around by rewording,
narrowing, splitting or reframing.
