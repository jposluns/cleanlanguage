---
corpus-id: rerunf
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [QUALI]
slug: rerun-pass-is-still-failure
map-nist-80053-broad: [SI-2]
map-iso-42001-broad: [A.6.2.4]
---

# A rerun pass does not erase an earlier failure

A check that fails and then passes on rerun with no deliberate intervening change is treated as an
unresolved intermittent result: the earlier failure is recorded and investigated, and the later pass
is not presented as conclusive verification. A rerun does not by itself explain or resolve the earlier
failure, so both results remain part of the gate evidence.
