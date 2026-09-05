---
corpus-id: secsyn
origin: pack
family: security
facet: SECP
secondary: [SECC]
slug: synthetic-fixture-data
map-cwe-broad: [CWE-359, CWE-531]
map-nist-80053-tight: [SA-3(2), SA-15(9)]
map-owasp-llm-broad: [LLM02]
map-owasp-asvs-broad: [V14]
map-csa-ccm-tight: [DSP-15]
map-csa-aicm-tight: [DSP-15]
---

# Fixtures and examples use synthetic data

Test fixtures, seed data, examples, and documentation use purpose-built synthetic data or anonymization
validated against the applicable re-identification risk, never real personal data or production records
copied over for convenience. Version control can retain removed content in history, so later cleanup is not
the primary safeguard.
