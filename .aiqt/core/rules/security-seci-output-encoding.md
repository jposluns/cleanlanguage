---
corpus-id: secenc
origin: pack
family: security
facet: SECI
slug: output-encoding
map-cwe-tight: [CWE-838]
map-cwe-broad: [CWE-116]
map-nist-80053-tight: [SI-10(6)]
map-nist-ssdf-broad: [PW.5.1]
map-atlas-tight: [AML.T0077]
map-atlas-broad: [AML.T0050, AML.T0113]
map-iso-23894-broad: [A.11]
map-owasp-asvs-tight: [V1]
map-owasp-web-broad: [A05]
map-owasp-cheatsheet-tight: [cross-site-scripting-prevention]
map-csa-ccm-broad: [AIS-04]
map-csa-aicm-broad: [AIS-10]
---

# Encode output for its sink

Output is encoded for the specific sink that will consume it, such as HTML, SQL, a shell, or a template
engine. Encoding is chosen by destination rather than applied generically, since encoding for the wrong sink
still leaves the actual sink exploitable.
