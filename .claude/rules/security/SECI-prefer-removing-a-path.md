---
corpus-id: rmvpth
origin: pack
family: security
facet: SECI
secondary: [SECC]
slug: prefer-removing-a-path
map-nist-80053-tight: [CM-7]
map-nist-80053-broad: [AC-6, SC-7]
---

# Prefer removing a path over constraining or monitoring it

When a tool, connector, data path, or execution path is hardened, a capability the task does not need is
removed so that it is unavailable, rather than retained for policy or monitoring to police; a path the task
does need is constrained to the least capability, access, destinations, and data it requires. Removal is
preferred to constraint and constraint to monitoring, because a capability that is absent cannot be misused
while one that is merely watched can. Monitoring a capability that could be removed, or constraining one the
task does not need at all, leaves standing an attack surface that subtraction would have eliminated.

What survives subtraction is needed, so it is then hardened: constrained, monitored, and given overlapping
controls where they are cheap. This orders the hardening; it does not argue against layered defence of what
is kept. It is a design-time preference over how a path is hardened, distinct from minimizing dependencies,
which governs what is brought in, and from least-privilege tool scope, which governs the runtime access a
retained capability is granted. Using a retained, constrained path is not itself a violation.
