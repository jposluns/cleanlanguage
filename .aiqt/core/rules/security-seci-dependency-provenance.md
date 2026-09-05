---
corpus-id: secsup
origin: pack
family: security
facet: SECI
slug: dependency-provenance
map-cwe-tight: [CWE-494, CWE-829]
map-cwe-broad: [CWE-1357]
map-nist-airmf-broad: [GOVERN 6.1, MANAGE 3.1, MAP 4.2]
map-nist-80053-tight: [SR-3, SR-4, SR-11]
map-nist-ssdf-tight: [PW.4.1, PW.4.4]
map-nist-ssdf-broad: [PO.3.2]
map-atlas-tight: [AML.T0010.001, AML.T0010.003, AML.T0010.005, AML.T0011.000, AML.T0011.001, AML.T0011.002, AML.T0104, AML.T0109]
map-atlas-broad: [AML.T0018.002, AML.T0111, AML.T0112.001]
map-iso-42001-broad: [A.4.4, A.10.3]
map-iso-23894-broad: [A.11, B.5]
map-owasp-llm-tight: [LLM04]
map-owasp-asi-tight: [ASI04]
map-owasp-api-broad: [API9]
map-owasp-mcp-tight: [MCP04, MCP09]
map-owasp-web-tight: [A03, A08]
map-owasp-cheatsheet-tight: [software-supply-chain-security]
map-csa-ccm-tight: [STA-01, STA-08, STA-09, STA-10]
map-csa-ccm-broad: [TVM-06, UEM-02]
map-csa-aicm-tight: [MDS-02, MDS-09, STA-01, STA-08, STA-09, STA-10]
map-csa-aicm-broad: [MDS-12, TVM-06, UEM-02]
---

# Trusted, pinned dependency provenance

Dependencies, tools, external servers, and any model or artefact file that executes on load come from trusted
sources with pinned provenance. A file that runs code when loaded is scanned before use, and none is
introduced on the strength of its name or popularity alone. Before relying on a tool, MCP server,
connector, or external server, the active surface is reconciled against the approved pinned inventory; an
unrecognized, shadow, changed, or unpinned entry is treated as unavailable until it is reviewed and
authorized.
