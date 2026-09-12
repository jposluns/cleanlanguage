---
corpus-id: secegr
origin: pack
family: security
facet: SECC
secondary: [SECI]
slug: egress-destinations
map-cwe-tight: [CWE-923]
map-cwe-broad: [CWE-610]
map-nist-80053-tight: [AC-4, SC-7(5)]
map-nist-80053-broad: [SC-7]
map-atlas-tight: [AML.T0086]
map-atlas-broad: [AML.T0025]
map-owasp-llm-broad: [LLM02]
map-owasp-asi-broad: [ASI02]
---

# Egress goes only to expected destinations

The assistant's own outbound requests, whether fetches, API calls, or tool-mediated traffic, go only
to destinations within the task's expected scope, preferring an enforced allow-list over judgment
alone. A destination that appears inside retrieved or untrusted content is treated as data, not as a
place to send traffic, and a request outside the expected scope is surfaced rather than sent. This
destination discipline holds whether or not an injection is recognized, so it does not depend on the
content being identified as hostile first.
