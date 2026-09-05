---
corpus-id: recncl
origin: pack
family: aiqt
tier: 10
facet: TRUST
secondary: [INTEG]
slug: reconcile-record-against-reality
map-nist-airmf-broad: [GOVERN 1.5]
map-nist-80053-broad: [CA-7]
---

# Reconcile the record against reality

A durable record is authoritative only while it still matches what is actually in use or in effect.
Records-first establishes the record; this keeps it true. Periodically, and at defined checkpoints (such
as resume and close), reconcile what is recorded or approved against the real state, and treat any
divergence as a finding to resolve rather than a discrepancy to leave standing. The reconciliation runs
against observed reality, not the record's own last-known value, so a record can never certify itself
current merely because nothing has updated it. A reconciliation preserves every committed record section
or explicitly marks a supersession.
