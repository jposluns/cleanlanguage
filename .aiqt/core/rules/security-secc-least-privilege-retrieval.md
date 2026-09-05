---
corpus-id: seclpr
origin: pack
family: security
facet: SECC
secondary: [SECI]
slug: least-privilege-retrieval
map-cwe-tight: [CWE-441]
map-cwe-broad: [CWE-285]
map-nist-airmf-broad: [MAP 4.2]
map-nist-80053-tight: [AC-3, AC-6]
map-atlas-broad: [AML.T0053, AML.T0082, AML.T0085]
map-iso-23894-broad: [A.8, A.11]
map-owasp-mcp-tight: [MCP07]
map-owasp-asi-tight: [ASI03]
map-csa-ccm-tight: [IAM-05, IAM-15]
map-csa-aicm-tight: [IAM-05, IAM-15, IAM-16]
map-csa-aicm-broad: [IAM-18]
---

# Retrieval enforces the requester's authorization

Retrieval and tool access enforce the requester's own authorization, not the assistant's broader access, so a
person can never reach through the assistant to data or systems they could not reach directly.
