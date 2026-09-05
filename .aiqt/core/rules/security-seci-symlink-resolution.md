---
corpus-id: secspr
origin: pack
family: security
facet: SECI
slug: symlink-resolution
map-cwe-tight: [CWE-59, CWE-363]
map-cwe-broad: [CWE-367]
map-owasp-asvs-broad: [V5]
---

# Resolve privileged filesystem paths against symlink races

Code the assistant writes that opens, reads, or writes a filesystem path with elevated privilege resolves
that path safely against a symbolic-link race rather than trusting the name it was given. It resolves each
path component beneath a pre-opened directory handle, using the platform's containment primitive where one
exists, refusing to follow a symbolic link or to escape above the anchoring directory, so an attacker who
swaps a component for a link between the check and the use cannot redirect the operation onto a target
outside the intended tree. After the object is opened it confirms the opened object's type and identity,
because a name-based check performed before the open describes a path that may no longer point where it did.
Where the platform offers no race-free containment primitive, the operation fails closed rather than
falling back to an unguarded name-based resolution.
