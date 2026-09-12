---
corpus-id: secred
origin: pack
family: security
facet: SECI
secondary: [SECC, SECP]
slug: log-redaction
map-cwe-tight: [CWE-532]
map-cwe-broad: [CWE-200]
map-nist-airmf-broad: [MAP 4.2]
map-nist-80053-tight: [AU-3(3)]
map-nist-ssdf-broad: [PW.5.1]
map-atlas-broad: [AML.T0055, AML.T0063]
map-iso-42001-broad: [A.6.2.8]
map-iso-23894-broad: [A.8, A.11]
map-owasp-asvs-broad: [V16]
map-csa-ccm-tight: [LOG-08, LOG-09]
map-csa-ccm-broad: [DSP-08, DSP-17]
map-csa-aicm-tight: [LOG-08, LOG-09]
map-csa-aicm-broad: [DSP-17]
---

# Redact sensitive content from logs

Logs record events, not the raw sensitive content of prompts, arguments, or results. Secrets and personal
data are redacted before anything is written, never cleaned up after the fact.
