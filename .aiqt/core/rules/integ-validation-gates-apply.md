---
corpus-id: valgat
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [QUALI]
slug: validation-gates-apply
map-nist-airmf-broad: [MAP 4.2]
map-nist-80053-tight: [CM-3(2)]
map-nist-80053-broad: [SA-11]
map-nist-ssdf-broad: [PW.7.1, PW.8.1]
map-iso-42001-broad: [A.6.2.4]
---

# Validation is a gate on apply

There is no trusted-worker fast path: every candidate change is validated before it lands, no matter its
source. Trust is never a substitute for the gate.
