---
corpus-id: secres
origin: pack
family: security
facet: SECA
secondary: [COST]
slug: resource-bounds
map-cwe-tight: [CWE-400, CWE-770]
map-cwe-broad: [CWE-674, CWE-834]
map-nist-airmf-broad: [MAP 4.2]
map-nist-80053-tight: [SC-5, SC-6]
map-atlas-tight: [AML.T0029, AML.T0034.000, AML.T0034.001, AML.T0034.002]
map-atlas-broad: [AML.T0046]
map-iso-42001-broad: [A.6.2.6]
map-iso-23894-broad: [A.9, A.11, B.4]
map-owasp-llm-tight: [LLM06]
map-owasp-asi-tight: [ASI08]
map-owasp-api-tight: [API4]
map-owasp-cheatsheet-broad: [denial-of-service]
map-csa-ccm-broad: [I&S-02]
map-csa-aicm-broad: [AIS-13, MDS-11]
---

# Bounded consumption and safe failure

Tool-call depth and recursion, token and cost budgets, and request rate are bounded, and the assistant
fails safe when a bound is reached rather than continuing unchecked. Loops that call tools or spawn work
carry a limit and a timeout, so a manipulated or runaway agent cannot exhaust resources, run up cost, or
cascade a failure across a system. Repeated failure of a downstream dependency suppresses further calls
to it, a circuit breaker or an equivalent backoff that stops while failure persists and probes before
full traffic resumes, so a degraded component is relieved rather than amplified into a wider outage.
