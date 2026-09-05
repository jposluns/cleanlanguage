---
corpus-id: secaud
origin: pack
family: security
facet: SECI
slug: protect-audit-records
map-cwe-tight: [CWE-471]
map-cwe-broad: [CWE-732]
map-nist-80053-tight: [AU-9]
map-owasp-web-broad: [A09]
map-owasp-asvs-broad: [V16]
map-owasp-mcp-broad: [MCP08]
map-owasp-cheatsheet-broad: [logging]
map-csa-ccm-tight: [LOG-02, LOG-10]
map-csa-ccm-broad: [LOG-04]
map-csa-aicm-tight: [LOG-02, LOG-10]
map-csa-aicm-broad: [LOG-04]
---

# Protect audit records from the actors they record

Security and change audit records are append-only or integrity-protected and held under authority separate
from the actor or agent whose actions they record. This prevents or makes detectable attempts by the recorded actor to rewrite or erase its own trail.
