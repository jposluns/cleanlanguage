---
corpus-id: datbnd
origin: pack
family: security
facet: SECC
secondary: [SECP]
slug: data-boundary
map-cwe-broad: [CWE-200]
map-nist-80053-tight: [MP-3]
map-owasp-asvs-broad: [V14]
map-owasp-llm-broad: [LLM02]
map-csa-ccm-tight: [DSP-04]
map-csa-ccm-broad: [DSP-10, DSP-17]
map-csa-aicm-tight: [DSP-04]
map-csa-aicm-broad: [DSP-10, DSP-17, DSP-24, IAM-16]
---

# Classify content by sensitivity tier

Every artefact and piece of content is classified PUBLIC, INTERNAL, or RESTRICTED at the point it is
produced, and is stored, shared, or disclosed only through a channel that tier permits. Content that
incorporates material from more than one tier is classified at the most restrictive tier of anything it
contains.
