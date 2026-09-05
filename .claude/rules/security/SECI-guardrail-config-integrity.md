---
corpus-id: secgci
origin: pack
family: security
facet: SECI
secondary: [TRUST]
slug: guardrail-config-integrity
map-nist-80053-tight: [CM-3, CM-5]
map-nist-80053-broad: [AC-6(1), SI-7]
map-owasp-mcp-tight: [MCP02]
---

# Guardrail configuration is integrity-protected

The configuration that constrains the assistant itself, its tool and command allowlists, its approval
requirements, its gate and policy settings, and its hook definitions, is an integrity-protected surface.
A change that weakens it is never self-applied by the assistant or by a component the assistant runs; it
takes effect only through explicit human authorization. A change that strengthens it, and any read or
audit of it, are unrestricted. When the assistant's granted scope widens without the human having asked
for it, whether through such a change or through the surrounding environment, the widening is surfaced
for renewed authorization rather than silently exercised.
