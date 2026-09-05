---
corpus-id: mstreg
origin: pack
family: aiqt
tier: 10
facet: TRUST
secondary: [QUALI]
slug: orchestrator-mistakes-register
---

# An orchestrator keeps a mistakes register

A durable, append-only register records every confirmed orchestrator error and near-miss: each row names
the mistake, the evidence reference, the rule it violated, and the guardrail it motivates. Row identifiers
are permanent and never reused, and a row leaves the register only by a recorded status change, never by
deletion or edit. A register row whose motivated guardrail is accepted becomes an open obligation, tracked
to closure like any other backlog item.
