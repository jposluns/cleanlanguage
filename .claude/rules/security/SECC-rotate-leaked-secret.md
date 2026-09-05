---
corpus-id: secrot
origin: pack
family: security
facet: SECC
secondary: [SECI]
slug: rotate-leaked-secret
map-nist-airmf-broad: [MANAGE 2.3, MANAGE 4.3]
map-nist-80053-tight: [IA-5]
map-nist-80053-broad: [IR-4]
map-atlas-broad: [AML.T0012, AML.T0091.000, AML.T0091.001]
map-iso-23894-broad: [A.11]
map-owasp-mcp-tight: [MCP01]
map-owasp-cheatsheet-tight: [secrets-management]
map-csa-ccm-tight: [CEK-12, CEK-19, IAM-14]
map-csa-ccm-broad: [SEF-07]
map-csa-aicm-tight: [CEK-12, CEK-19, IAM-14]
map-csa-aicm-broad: [SEF-07]
---

# Rotate a leaked secret

A secret that reaches a remote or an external service is treated as compromised and rotated, whatever any
scanner said. Rotation happens regardless of whether the exposure was intentional, brief, or already deleted
from the destination.
