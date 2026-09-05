---
corpus-id: secpsn
origin: pack
family: security
facet: SECI
secondary: [ACCUR]
slug: poisoning-resistance
map-cwe-tight: [CWE-345]
map-cwe-broad: [CWE-348]
map-nist-airmf-broad: [MANAGE 3.1, MAP 4.2]
map-nist-80053-tight: [SI-7, SI-10(5)]
map-atlas-tight: [AML.T0018.000, AML.T0020, AML.T0059, AML.T0070, AML.T0071, AML.T0080, AML.T0099]
map-atlas-broad: [AML.T0010.002, AML.T0066]
map-iso-42001-broad: [A.7.3, A.7.4]
map-iso-23894-tight: [A.4]
map-iso-23894-broad: [A.11, B.5]
map-owasp-llm-tight: [LLM05, LLM09]
map-owasp-asi-tight: [ASI06]
map-owasp-mcp-tight: [MCP03]
map-csa-aicm-tight: [DSP-21, DSP-23, MDS-01, MDS-08]
map-csa-aicm-broad: [MDS-06, MDS-07]
---

# Resist data, model, and memory poisoning

Training and fine-tuning data, embeddings, retrieval corpora, and any persisted agent memory are treated as
attack surface. Content that is retrieved or recalled is untrusted and does not silently gain authority over
later decisions. The sources that feed a model or a knowledge base are vetted and their integrity is checked,
so a planted document or a corrupted memory cannot quietly steer behaviour.
