---
corpus-id: seclog
origin: pack
family: security
facet: SECI
secondary: [TRUST]
slug: security-logging
map-cwe-tight: [CWE-778]
map-nist-airmf-broad: [GOVERN 4.3, MAP 4.2]
map-nist-80053-tight: [AU-2, AU-3, AU-12]
map-nist-ssdf-broad: [PW.5.1]
map-iso-42001-tight: [A.6.2.8]
map-iso-23894-broad: [A.2, A.11]
map-owasp-web-tight: [A09]
map-owasp-cheatsheet-tight: [logging]
map-owasp-asvs-tight: [V16]
map-owasp-proactive-tight: [C9]
map-owasp-mcp-tight: [MCP08]
map-csa-ccm-tight: [LOG-07, LOG-09, LOG-12, LOG-13]
map-csa-ccm-broad: [LOG-01]
map-csa-aicm-tight: [LOG-07, LOG-09, LOG-12, LOG-13]
map-csa-aicm-broad: [LOG-01]
---

# Security logging with traceable context

Security-relevant events, including authentication, authorization, and privileged actions, are logged with
enough context to investigate. The human, agent, and tool chain behind an action stays traceable end to end.
