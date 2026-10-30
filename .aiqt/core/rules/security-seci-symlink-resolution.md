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

When such code classifies a control or state path, a lock, marker, journal, or state directory, to
decide what to do, the classification is a no-follow inspection bound to a trusted directory
descriptor, never a re-resolved string-path existence or type check that follows links. The result
is three-way: genuine absence, which may legitimately mean nothing to do; presence with exactly the
expected type, confirmed on the opened object rather than on the name; and everything else, a
regular file where a directory was expected, a symbolic link, a dangling link, any other wrong-type
entry, a malformed name, or an entry the code cannot evaluate, which is refused as an error and
never collapsed into absence or treated as clean. Enumeration and use after classification stay
bound to the same descriptor rather than re-resolving the string path, so a substitution of the
name cannot redirect those operations to a different object.
