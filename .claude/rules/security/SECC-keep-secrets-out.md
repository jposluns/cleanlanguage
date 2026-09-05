---
corpus-id: secsec
origin: pack
family: security
facet: SECC
secondary: [SECI]
slug: keep-secrets-out
map-cwe-tight: [CWE-532, CWE-540]
map-cwe-broad: [CWE-798]
map-nist-airmf-broad: [MAP 4.2]
map-nist-80053-tight: [IA-5(7)]
map-nist-ssdf-broad: [PW.5.1]
map-atlas-tight: [AML.T0055, AML.T0095.000]
map-atlas-broad: [AML.T0082, AML.T0083, AML.T0098]
map-iso-23894-broad: [A.11]
map-owasp-llm-broad: [LLM02]
map-owasp-mcp-tight: [MCP01]
map-owasp-asvs-broad: [V14]
map-owasp-cheatsheet-tight: [secrets-management]
map-csa-ccm-tight: [IAM-14]
map-csa-ccm-broad: [DSP-17, LOG-08]
map-csa-aicm-tight: [AIS-12, IAM-14]
map-csa-aicm-broad: [DSP-17, LOG-08]
---

# Keep secrets out

No credential, token, key, or other secret is committed to a repository or written to any shared or persisted
location, including prompts, logs, transcripts, tool output, and generated files. Pattern scanning and a leak
gate are compensating controls, never a substitute for keeping secrets out in the first place. The assistant
never asks a human to paste a password, key, token, or other raw secret into the conversation or any surface
it reads; a credential a task needs is supplied through the platform's secret store, environment, or
authentication flow instead.
