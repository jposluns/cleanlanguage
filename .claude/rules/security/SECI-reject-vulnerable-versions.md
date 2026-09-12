---
corpus-id: secvln
origin: pack
family: security
facet: SECI
slug: reject-vulnerable-versions
map-cwe-tight: [CWE-1395]
map-nist-airmf-broad: [MANAGE 3.1]
map-nist-80053-broad: [RA-5]
map-nist-ssdf-tight: [PW.4.4]
map-owasp-llm-broad: [LLM04]
map-owasp-asi-broad: [ASI04]
map-owasp-mcp-broad: [MCP04]
map-owasp-web-tight: [A03]
map-owasp-proactive-tight: [C6]
map-owasp-cheatsheet-tight: [vulnerable-dependency-management]
map-csa-ccm-tight: [TVM-06]
map-csa-ccm-broad: [TVM-03]
map-csa-aicm-tight: [TVM-06]
map-csa-aicm-broad: [TVM-03]
---

# Reject known-vulnerable dependency versions

Before a dependency is added or upgraded, the exact resolved version is checked against current
authoritative vulnerability advisories, and a version with a known exploitable vulnerability is rejected.
Authentic provenance does not make a version safe; a legitimate, correctly named package can still resolve
to an artefact that is unsafe to ship.
