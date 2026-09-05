---
corpus-id: cnclse
origin: pack
family: aiqt
tier: 10
facet: TRUST
secondary: [INTEG]
slug: concurrency-lease
---

# Hold a concurrency lease to prevent double runs

A concurrency lease prevents two runs from acting on the same session at once. It is reconciled against the
recorded state on resume or close, and never seized from a run that currently holds it.
