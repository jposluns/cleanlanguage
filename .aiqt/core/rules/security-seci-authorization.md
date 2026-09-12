---
corpus-id: secazn
origin: pack
family: security
facet: SECI
secondary: [SECC]
slug: authorization
map-cwe-tight: [CWE-862, CWE-863, CWE-915]
map-cwe-broad: [CWE-284]
map-nist-80053-tight: [AC-3, AC-6]
map-nist-ssdf-broad: [PW.5.1]
map-atlas-broad: [AML.T0053, AML.T0082, AML.T0085]
map-iso-23894-broad: [A.11]
map-owasp-asvs-tight: [V8]
map-owasp-web-tight: [A01]
map-owasp-api-tight: [API1, API3, API5]
map-owasp-proactive-tight: [C1]
map-owasp-cheatsheet-tight: [authorization]
map-owasp-cheatsheet-broad: [mass-assignment]
map-csa-ccm-tight: [IAM-05, IAM-15]
map-csa-aicm-tight: [IAM-05, IAM-15]
map-csa-aicm-broad: [IAM-16, IAM-17, IAM-18]
---

# Least-privilege authorization

Code the assistant writes and operations it performs enforce least-privilege authorization, checked at every
access rather than inferred from an earlier step. Verification happens at the object, function, and property
level on each request: a write binds only to an explicit allow-list of fields, so a caller can never reach
data or actions, nor set a protected field through mass assignment, beyond what its own rights permit.
