---
corpus-id: secfid
origin: pack
family: security
facet: SECI
slug: federated-identity-flow
map-cwe-tight: [CWE-304, CWE-347]
map-cwe-broad: [CWE-287]
map-owasp-asvs-tight: [V9, V10]
map-owasp-proactive-broad: [C7]
map-owasp-cheatsheet-tight: [json-web-token, oauth2]
map-csa-ccm-broad: [IAM-13, IAM-14, IAM-15]
map-csa-aicm-broad: [IAM-13, IAM-14, IAM-15]
---

# Validate federated identity and token flows

Code the assistant writes that implements OAuth, OIDC, or JWT-based authentication validates the full
protocol flow before granting access: the token issuer, audience, signature, and expiry; the state and
nonce; the redirect binding and PKCE where applicable; and that the granted scopes match what the exact
relying party requested. A token is trusted only after every one of these checks passes.
