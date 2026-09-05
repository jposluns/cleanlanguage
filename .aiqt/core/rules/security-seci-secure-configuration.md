---
corpus-id: seccfg
origin: pack
family: security
facet: SECI
secondary: [SECC]
slug: secure-configuration
map-cwe-tight: [CWE-1188, CWE-1269]
map-nist-80053-tight: [CM-6, CM-7, SI-11]
map-nist-ssdf-tight: [PW.9.1, PW.9.2]
map-atlas-broad: [AML.T0049, AML.T0063]
map-iso-23894-broad: [A.11]
map-owasp-web-tight: [A02]
map-owasp-api-tight: [API8]
map-owasp-asvs-tight: [V13]
map-owasp-proactive-tight: [C5]
map-csa-ccm-tight: [AIS-02, I&S-04]
map-csa-ccm-broad: [CCC-06, CCC-07]
map-csa-aicm-tight: [AIS-02, I&S-04]
map-csa-aicm-broad: [CCC-06, CCC-07]
---

# Secure by default configuration

Configuration is secure by default: unnecessary features, ports, and accounts are not enabled, verbose
errors and debug settings do not reach production, and defaults are hardened rather than permissive. What
the assistant generates for infrastructure, services, and applications follows the same secure baseline.
