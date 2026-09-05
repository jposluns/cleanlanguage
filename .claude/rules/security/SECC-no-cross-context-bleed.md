---
corpus-id: secncb
origin: pack
family: security
facet: SECC
secondary: [SECP]
slug: no-cross-context-bleed
map-cwe-tight: [CWE-488]
map-cwe-broad: [CWE-200, CWE-653]
map-nist-airmf-broad: [MAP 4.2]
map-nist-80053-tight: [AC-4, SC-4]
map-atlas-broad: [AML.T0057, AML.T0080]
map-iso-23894-broad: [A.8, A.11]
map-owasp-mcp-tight: [MCP10]
map-csa-ccm-tight: [I&S-06]
map-csa-aicm-tight: [AIS-11, I&S-06]
map-csa-aicm-broad: [AIS-14, IAM-16]
---

# No cross-context bleed

Context assembled for one task, user, tenant, or trust boundary is not carried into another. Each new task or
session starts from a clean boundary, so information gathered under one authorization never surfaces in a
response served under a different one.
