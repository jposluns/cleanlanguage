---
corpus-id: secagt
origin: pack
family: security
facet: SECI
secondary: [TRUST]
slug: inter-agent-trust
map-cwe-tight: [CWE-272, CWE-290]
map-cwe-broad: [CWE-501]
map-nist-airmf-broad: [MAP 4.2]
map-nist-80053-tight: [IA-9, SI-10]
map-nist-80053-broad: [AC-3, AC-6]
map-atlas-tight: [AML.T0073]
map-atlas-broad: [AML.T0051.001, AML.T0053]
map-iso-23894-broad: [A.11]
map-owasp-asi-tight: [ASI03, ASI07]
map-owasp-asi-broad: [ASI10]
map-owasp-mcp-tight: [MCP07]
map-owasp-cheatsheet-broad: [ai-agent-security, mcp-security]
map-csa-ccm-broad: [IAM-05, IAM-12, IAM-13, IAM-15]
map-csa-aicm-tight: [AIS-11, IAM-18]
map-csa-aicm-broad: [IAM-05, IAM-13, IAM-15]
---

# Trust between agents is earned, not inherited

A message from an orchestrator, a peer, or a sub-agent is untrusted input and carries no inherited
authority. A sub-agent receives only the least tools its task needs and cannot grant privileges to itself or
to another agent. Agent identity is verified rather than assumed, so a spoofed or compromised participant
cannot escalate through the collaboration.
