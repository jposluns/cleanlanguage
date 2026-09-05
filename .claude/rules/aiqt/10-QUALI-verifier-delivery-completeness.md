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

A verifier's output counts as a verdict only when the verifier actually delivered one. Completeness is
judged by a single criterion: the delivery carries the positive evidence of a finished verdict that the
verification agreed on in advance, whether that agreed evidence is a completion marker the verifier emits,
the explicit verdict the verification asked for, or both. A delivery that lacks that agreed evidence, or
that is truncated, empty, or errored, is treated as no verdict, never as a pass, a vote, or a finding-free
result.
A capture piped through a truncating sink is a degraded delivery, not a verdict, even when its retained
prefix appears complete.
Completeness is never inferred from the length or volume of the output or from the mere absence of
a reported problem, because a run cut off before it reached its verdict is indistinguishable from a clean
one when judged by silence or size. A delivery that fails this test is re-dispatched and contributes
nothing; it does not by itself justify reducing the verifier panel, since one failed delivery is not
evidence that a verifier family is unavailable. A required family is dropped from the panel only when it
is genuinely unreachable, on the terms the verifier-diversity rule sets, and that reduction is recorded
and re-run when the family returns.
The same fail-closed posture applies when the verifier itself cannot read or access a required input it was
meant to cover: it does not emit a permissive verdict over the gap. It emits UNVERIFIABLE, the
cannot-evaluate outcome guard-input-soundness names, identifying the input it could not read; this is a
terminal fail-closed result, not the transient degraded delivery above that a re-dispatch can cure, so it
is treated as not-passed and resolved by fixing the input, never a clean, passing, or finding-free verdict.
A clean verdict asserted over an input the verifier never actually read is the same false-clean this rule
already guards against, applied to the unreadable-required-input case, meeting the fail-closed posture
check-fails-closed-on-unreadable requires of a gate that cannot read its own input.
