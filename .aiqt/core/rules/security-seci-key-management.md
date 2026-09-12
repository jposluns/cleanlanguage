---
corpus-id: seckey
origin: pack
family: security
facet: SECI
secondary: [SECC]
slug: key-management
map-cwe-tight: [CWE-321, CWE-324]
map-cwe-broad: [CWE-323]
map-nist-80053-tight: [IA-5(7), SC-12]
map-nist-ssdf-broad: [PW.5.1]
map-atlas-tight: [AML.T0055]
map-atlas-broad: [AML.T0012]
map-iso-23894-broad: [A.11]
map-owasp-asvs-broad: [V11]
map-owasp-cheatsheet-tight: [key-management]
map-csa-ccm-tight: [CEK-10, CEK-11, CEK-12, CEK-13, CEK-14, CEK-21]
map-csa-ccm-broad: [CEK-01]
map-csa-aicm-tight: [CEK-10, CEK-11, CEK-12, CEK-13, CEK-14, CEK-21]
map-csa-aicm-broad: [CEK-01]
---

# Key management

Keys and other secret material are generated, stored, rotated, and retired properly, and are never hardcoded.
A key is never reused across contexts that are meant to stay isolated from one another.
