---
corpus-id: secfcl
origin: pack
family: security
facet: SECI
slug: fail-closed
map-cwe-tight: [CWE-636]
map-owasp-web-tight: [A10]
map-owasp-cheatsheet-broad: [error-handling]
---

# Fail closed in security-relevant paths

An exception or error in an authentication, authorization, validation, or cryptographic check leaves the
system in the deny or otherwise safe state. A failed, unavailable, or unreadable check is treated as not
passed, never as a default-allow.
