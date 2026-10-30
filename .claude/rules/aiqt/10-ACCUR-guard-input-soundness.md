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

A document's own wording is itself such an input when a check verifies a fact by matching it. The wording
establishes only that the text is present, never that what it asserts is true, so a suite of such presence or
wording checks passing is not evidence the document is correct. Where a document asserts a fact about the
system it governs, an owning account, a path, a schedule, or an interface, that fact is verified against an
authority the document's author does not control, the live system or a second in-tree artefact whose purpose
is to state that same fact, rather than against the document's own words. A membership question over a range
or interval is likewise answered by a membership test, whether a value falls within the interval, not by
matching the literal endpoint tokens: a range expressed by its endpoints is not the set of its members, so a
literal-token scan is a proxy that structurally cannot see a member the range includes only implicitly, one
lying between its endpoints and written nowhere as a literal token.

A negative check that asserts a string is absent is only as sound as its input in the same way: run against
a whole artefact it cannot tell an operative occurrence from the same string quoted in a correction that
warns against it, or recorded as what a value used to be, so it fires on the correction and trains its
author to weaken the check or delete the explanation. It is therefore scoped to the narrowest locus where
the string's presence would be a defect; a whole-artefact scope is right only where every occurrence is a
defect, such as a leaked secret, an invalid byte, or a forbidden character with no legitimate quotation.
Where the string legitimately appears elsewhere, the invariant is asserted against the parsed or semantic
state, or the negative predicate is scoped to the defect locus, rather than run as a naive whole-artefact
string scan.

A list kept by hand that selects what a generated view contains is itself such an input. Comparing the view
with a fresh run of its generator shows that it is current, never that it is complete, since both read the
list and an item the list omits is missing from each. A view that claims to cover a set checks, as it is
generated, that each item of the authoritative set appears in it or is named in a recorded exclusion, and
fails on an item in neither; a view that declares itself a curated selection makes no such claim.

A check run ahead of an expensive apply step to report whether it will succeed is such a guard too and
evaluates every condition the apply enforces, the expected state after the change as well as the state
before it. An expensive apply and a check of whether it will succeed decide from one shared predicate, or,
where the apply's predicate is out of reach, a test holds the check to failing on every input the apply
rejects. A check of whether an expensive apply will succeed refuses an input the apply would refuse, such
as a version or sequence number no greater than the last one consumed, before any long work begins.
