---
corpus-id: lvw001
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [ACCUR, SECI]
slug: lightweight-verifier-workers
map-nist-airmf-broad: [MEASURE 1.3, MEASURE 2.13]
map-nist-80053-broad: [SA-11(3)]
map-iso-42001-broad: [A.6.2.4]
---

# Isolate verifiers and judge by their result signal

Run each verifier in its own isolated, read-only context. Judge its outcome by an authoritative result
signal, not by grepping its output: a verifier legitimately echoes the very rule text under review, so
text-matching its output produces false positives.
