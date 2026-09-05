---
corpus-id: secinp
origin: pack
family: security
facet: SECI
slug: input-validation
map-cwe-tight: [CWE-20]
map-cwe-broad: [CWE-74]
map-nist-80053-tight: [SI-10, SI-10(5), SI-10(6)]
map-nist-ssdf-broad: [PW.5.1]
map-atlas-broad: [AML.T0049, AML.T0050]
map-iso-23894-broad: [A.9, A.11]
map-owasp-web-tight: [A05]
map-owasp-cheatsheet-tight: [input-validation]
map-owasp-asvs-tight: [V2]
map-owasp-proactive-tight: [C3]
map-csa-ccm-broad: [AIS-04]
map-csa-aicm-tight: [AIS-09]
map-csa-aicm-broad: [AIS-08]
---

# Validate external input at the boundary

External input is validated for type, range, and format at the point where it enters, preferring an
allow-list over a deny-list. The injection classes, whether SQL, operating-system command, markup, or
template, are prevented by construction rather than filtered after the fact.
