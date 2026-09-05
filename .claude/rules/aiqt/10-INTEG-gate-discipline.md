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

A gate verdict is trusted only when it is read from the gate's own unmasked termination status, or from
a structured terminal result bound to the exact revision under gate; a downstream pipeline's status, a
truncated delivery, a textual success token, or a result for a different revision is not that verdict. A
pending, missing, ambiguous, malformed, unknown, or unreadable result is unverified, never a pass, and the
gated action stays a separate step, withheld until terminal success is observed, so a check folded into the
same unverified apply or merge does not establish the checkpoint.
