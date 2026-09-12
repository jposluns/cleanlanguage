---
corpus-id: secau1
origin: pack
family: security
facet: SECI
secondary: [SECC]
slug: authentication
map-cwe-tight: [CWE-287]
map-cwe-broad: [CWE-306, CWE-798]
map-nist-80053-tight: [IA-2]
map-nist-80053-broad: [IA-5(5), IA-5(7)]
map-nist-ssdf-broad: [PW.1.3, PW.5.1]
map-atlas-broad: [AML.T0012, AML.T0055]
map-iso-23894-broad: [A.11]
map-owasp-asvs-tight: [V6]
map-owasp-web-tight: [A07]
map-owasp-cheatsheet-tight: [authentication, multifactor-authentication]
map-owasp-api-tight: [API2]
map-csa-ccm-tight: [IAM-13, IAM-14]
map-csa-aicm-tight: [IAM-13, IAM-14]
---

# Strong authentication

Code the assistant writes and operations it performs enforce strong authentication before granting access to
a protected resource or action. Credentials are never hardcoded, defaulted, or bypassable, and authentication
uses vetted, current mechanisms rather than a scheme invented ad hoc.
