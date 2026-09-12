---
corpus-id: secout
origin: pack
family: security
facet: SECI
secondary: [QUALI]
slug: output-handling
map-cwe-tight: [CWE-1426]
map-cwe-broad: [CWE-20]
map-nist-airmf-broad: [GOVERN 4.1, MAP 4.2, MEASURE 2.9]
map-nist-80053-tight: [SI-10(6), SI-15]
map-nist-80053-broad: [SA-11]
map-nist-ssdf-broad: [PW.5.1, PW.7.1, PW.8.1]
map-atlas-tight: [AML.T0077, AML.T0102]
map-atlas-broad: [AML.T0050]
map-iso-23894-broad: [A.9, A.11]
map-owasp-llm-tight: [LLM10]
map-owasp-asvs-tight: [V1, V2]
map-owasp-web-broad: [A05]
map-owasp-proactive-tight: [C3]
map-owasp-cheatsheet-tight: [cross-site-scripting-prevention, injection-prevention]
map-csa-ccm-broad: [AIS-04, AIS-05]
map-csa-aicm-tight: [AIS-10]
map-csa-aicm-broad: [AIS-05, AIS-09, AIS-13, TVM-13]
---

# Generated output is untrusted input

Everything the assistant produces, whether code, configuration, commands, queries, or markup, is untrusted
input to whatever will consume it. It is validated, encoded for its destination, and never executed or
trusted merely because the assistant produced it. The project's review, testing, and static-analysis gates
apply to generated artefacts exactly as they apply to human-written ones; no check is waived on the grounds
that the output came from a model.
