---
corpus-id: grdinp
origin: pack
family: aiqt
tier: 10
facet: ACCUR
secondary: [QUALI, INTEG]
slug: guard-input-soundness
map-nist-airmf-tight: [MAP 2.3]
map-nist-airmf-broad: [MEASURE 2.13]
---

# A guard is only as good as its input

A check whose logic is correct is still worthless when its input cannot answer the question asked of it. Ask
of every consequential guard not whether the value is correct but whether the source can, even in principle,
answer what is being asked; when it cannot, change the input rather than harden the check. A value the guard
is handed rather than measures, a caller-supplied count, size, or work-list, or the guard's own denylist,
threshold, or configuration, is itself such an input: validate a passed premise against the real source or
authoritative evidence, and treat a malformed, contradictory, or out-of-range control as a failure rather
than running the guard
mis-sized or disabled. When the source cannot answer, the guard treats that as a distinct cannot-evaluate
case rather than silently collapsing it into either definite verdict; a two-valued predicate cannot carry this third
state, so route a cannot-evaluate to the safe outcome for that guard, a coverage check reporting failure and
a consequential action withholding rather than firing on an unverified basis, never a silent clean pass or a
verdict the guard never reached. Inputs absent from the author's own examples are a particular silent-failure
risk.

A command or control parameter that names the repository, target, or other context an artefact will act
on is itself such an input. A value hardcoded into a reusable command, or carried over from the source the
command was copied or templated from, is not evidence of the target the command now runs against: it is
derived from the authoritative source at the point of use, or validated against it, before the guard
relies on it. A guard whose own logic is correct still answers about the wrong target when the parameter
it was handed cannot answer for the current one, so a parameter that cannot be derived or confirmed is a
cannot-evaluate, not a clean pass.
