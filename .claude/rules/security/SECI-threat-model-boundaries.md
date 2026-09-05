---
corpus-id: secthm
origin: pack
family: security
facet: SECI
slug: threat-model-boundaries
map-nist-80053-tight: [SA-11(2)]
map-nist-80053-broad: [SA-8]
map-nist-ssdf-tight: [PW.1.1]
map-iso-23894-broad: [6.4.2]
map-owasp-web-broad: [A06]
map-owasp-proactive-tight: [C4]
map-owasp-cheatsheet-tight: [threat-modeling]
map-csa-ccm-tight: [TVM-04]
map-csa-aicm-tight: [TVM-04]
---

# Threat-model new trust boundaries before implementation

Before a new external interface, privileged operation, untrusted data flow, or trust boundary is
implemented, its credible abuse paths are identified and their mitigations carried into the change's
acceptance criteria. This makes identified gaps reviewable before implementation rather than waiting for production evidence.
