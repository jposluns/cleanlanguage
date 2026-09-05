---
corpus-id: atmclm
origin: pack
family: aiqt
tier: 10
facet: TRUST
secondary: [INTEG]
slug: atomic-claim-from-pool
---

# Claim a pooled item atomically

Selecting an item from a shared pool and recording the claim on it are one atomic operation spanning both
the selection and the reservation, so no gap between choosing and reserving lets two actors take the same
item. The mechanism can be a transaction, a conditional write, a compare-and-set, or a lock; the
atomicity is what matters, not the primitive. A claim already held by another live actor is not
overridden: the operation aborts rather than proceeds or merely warns. This extends the concurrency-lease
discipline from a single session's lease to selection from a shared pool.
