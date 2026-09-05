---
corpus-id: rtsafe
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [TRUST]
slug: safe-retries
---

# Make retries safe to repeat

Before a state-changing operation is retried after a timeout, interruption, or unknown outcome,
authoritative state is reconciled or a stable idempotency mechanism is used, so the side effect cannot be
applied twice. A lost response is never taken as proof the operation did not happen.
