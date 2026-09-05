---
corpus-id: seccry
origin: pack
family: security
facet: SECI
secondary: [SECC]
slug: cryptography
map-cwe-tight: [CWE-295, CWE-327]
map-cwe-broad: [CWE-311]
map-nist-80053-tight: [SC-13]
map-nist-80053-broad: [SC-8, SC-28]
map-nist-ssdf-broad: [PW.5.1]
map-iso-23894-broad: [A.8, A.11]
map-owasp-web-tight: [A04]
map-owasp-asvs-tight: [V11]
map-owasp-asvs-broad: [V12]
map-owasp-proactive-tight: [C2]
map-owasp-cheatsheet-tight: [cryptographic-storage, transport-layer-security]
map-csa-ccm-tight: [CEK-04]
map-csa-ccm-broad: [CEK-03]
map-csa-aicm-tight: [CEK-04]
map-csa-aicm-broad: [CEK-03]
---

# Sound cryptography

Cryptography uses current, approved algorithms and correct parameters, with no weak, deprecated, or
home-grown schemes. Data is protected in transit and at rest to the strength its sensitivity requires.
Protection in transit is never defeated by disabling its verification: certificate and hostname validation
stay on, and code never disables TLS peer verification or accepts a self-signed or mismatched certificate
to work around a connection error.
