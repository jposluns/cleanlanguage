---
corpus-id: gatdis
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [QUALI]
slug: gate-discipline
map-nist-airmf-broad: [GOVERN 4.1]
map-nist-80053-broad: [CM-3(2), SA-11]
map-nist-ssdf-tight: [PW.8.2]
map-nist-ssdf-broad: [PO.4.1]
map-iso-42001-broad: [A.6.2.4]
---

# Gate discipline

Never weaken a gate to obtain a pass; fix the artefact instead. No bypass flags, no piping a check to a
truncating sink, no `|| true`, no deleted tests, no lowered thresholds. A failing gate is signal;
understand why it failed before considering any override. A security floor, a deny list, a permission
floor, or a required-check set, never shrinks silently: any reduction, whatever motivated it, lands only
through the maintainer's explicit, recorded authorization.

Replacing or removing a control, a gate, a check, a hook, a validator, or another guard, is a set operation,
so a replacement is treated as a reduction until its coverage is shown. Before such a change is dispatched
for review or integrated, the threats or cases the outgoing control covered are enumerated from its own
code, its tests, its specification, and its disclosed residual, never from a recollection of its purpose.
Each enumerated case is then accounted for in one of three states: covered, shown by a reference to the
replacement code that handles it and a case exercised against the replacement and observed to be caught;
unreachable, shown by the change that removes the capability the case depends on and an observed attempt
confirming the path is unavailable; or disclosed as no longer covered. A case disclosed as no longer covered
is a reduction, and it lands only through the maintainer's explicit, recorded authorization. A case left in
none of the three states is a silent reduction, and the change is not dispatched while one remains. The
enumeration and its accounting are recorded with the change, so a verifier reproduces them rather than
re-deriving the covered set. Where a case is covered by a surviving sibling control rather than by the
replacement, that coverage is cited on the same evidence, and the lost overlap is weighed under the
defence-in-depth-default rule rather than assumed free.

A gate verdict is trusted only when it is read from the gate's own unmasked termination status, or from
a structured terminal result bound to the exact revision under gate; a downstream pipeline's status, a
truncated delivery, a textual success token, or a result for a different revision is not that verdict. A
pending, missing, ambiguous, malformed, unknown, or unreadable result is unverified, never a pass, and the
gated action stays a separate step, withheld until terminal success is observed, so a check folded into the
same unverified apply or merge does not establish the checkpoint.

When a command's own termination status is the evidence a verdict rests on, that status is taken only from a
construct that faithfully propagates the gating command's own exit, never from one that can report success
while the gate failed; sequencing that preserves the gate's failure, such as a short-circuit that runs the
next command only on the gate's success or an explicit re-raise of the gate's saved exit, is not this
hazard, so the test is whether the construct's terminal status still reflects the gate's, not merely whether
another command follows it. An always-succeeding trailer appended after the gate, a `true`, a `:`, a
status-printing echo of the prior exit, or any other no-op whose own success overwrites the gate's exit,
makes the compound report the trailer's status, not the gate's, so a failing gate reads as a pass; a printed
copy of the exit is output, not the verdict, and such a status-masking trailer is never appended to a
command whose exit is relied on. The exit of a launcher, dispatcher, wrapper, or detached background task
carries the gate's verdict only where it demonstrably propagates the gate's own exit; a carrier that reports
its own success regardless of what the gate returned yields the vehicle's status, not the verdict, which is
then read from the gate's own result instead.

An event-triggered gate is relied on only after its trigger's preconditions are confirmed against
authoritative state: a pipeline triggered by a change request needs an open change request for the exact
revision and intended base before any run can exist, so where the precondition is unmet the absence of a
reported failure is a missing result, never a pass. A pushed revision, an acknowledged dispatch, or an
elapsed wait is not evidence the trigger fired; a run is confirmed to exist for the revision under gate
before anything is read from its outcome.
