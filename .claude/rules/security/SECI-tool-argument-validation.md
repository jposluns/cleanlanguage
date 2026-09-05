---
corpus-id: sectvl
origin: pack
family: security
facet: SECI
slug: tool-argument-validation
map-cwe-tight: [CWE-20, CWE-88]
map-cwe-broad: [CWE-22, CWE-77]
map-nist-80053-tight: [SI-10, SI-10(6)]
map-atlas-broad: [AML.T0050, AML.T0102]
map-iso-23894-broad: [A.11]
map-owasp-asi-broad: [ASI05]
map-owasp-mcp-broad: [MCP05]
map-owasp-web-broad: [A05]
map-owasp-asvs-tight: [V2]
map-csa-ccm-broad: [AIS-04]
map-csa-aicm-tight: [AIS-09, AIS-11, AIS-13, IAM-18]
---

# Validate tool arguments before use

Every argument the assistant passes to a tool, shell, database, or file operation is validated against an
expected schema before use. A command, query, path, or request is never assembled directly from unvalidated
model output or untrusted content, which is how command, query, and path-traversal injection occur.
