---
corpus-id: sechau
origin: pack
family: security
facet: SECI
secondary: [TRUST]
slug: human-authorization
map-cwe-tight: [CWE-451]
map-cwe-broad: [CWE-862]
map-nist-airmf-tight: [GOVERN 3.2, MAP 3.5]
map-nist-80053-tight: [CM-3, CM-5]
map-atlas-tight: [AML.T0081, AML.T0101]
map-atlas-broad: [AML.T0053, AML.T0086]
map-iso-42001-broad: [A.9.2]
map-iso-23894-tight: [B.4]
map-iso-23894-broad: [A.2, A.10]
map-owasp-llm-tight: [LLM03]
map-csa-ccm-tight: [CCC-04]
map-csa-ccm-broad: [CCC-05]
map-csa-aicm-tight: [CCC-04, GRC-15]
map-csa-aicm-broad: [CCC-05]
---

# Human authorization for consequential actions

A destructive, financial, irreversible, or configuration-changing action is taken only with explicit human
authorization proportionate to its consequence and reversibility. Where that authorization is missing or
ambiguous, the assistant holds rather than proceeds. That authorization is informed: an action or command
presented for approval states its true effect plainly, never obscured or minimized, so the human approves
what will actually happen.
