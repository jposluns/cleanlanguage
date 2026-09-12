---
corpus-id: vrfdiv
origin: pack
family: aiqt
tier: 10
facet: QUALI
slug: verifier-diversity
map-nist-airmf-broad: [MEASURE 1.3, MEASURE 2.1]
map-nist-80053-broad: [SA-11(3)]
map-nist-ssdf-broad: [PW.7.1]
map-iso-42001-broad: [A.6.2.4]
---

# Verifier diversity

Diversify the verification so it surfaces different failure classes: run it across two model families, and
a second family from any vendor counts. Only where no second model family is available may this fall back to
two independent, differently-primed passes in separate clean contexts, which is the accepted fallback and
not the equal of two families; record the reduction and run the two-family pass once a second family
becomes available. A critical change adds a third family; only where no third family is available
may a further independent, differently-primed pass take its place, recorded and re-run once a third family
becomes available. Unavailable means unreachable, not merely unbudgeted: cost never buys the reduction.
