---
corpus-id: secupl
origin: pack
family: security
facet: SECI
slug: file-upload-handling
map-cwe-tight: [CWE-434, CWE-646]
map-owasp-asvs-tight: [V5]
map-owasp-cheatsheet-tight: [file-upload]
---

# Validate and contain uploaded files

An uploaded file is accepted only when its extension is on an allow-list and its actual content is
validated to match that expected type; the client-supplied filename and declared content type are not
trusted on their own. Its size and any archive expansion are bounded before processing. It is stored
under an application-generated name outside the web root and any executable or directly served path, and
is never executed or included as code. It is served back only with a safe, explicit content type and a
content-disposition that forces download rather than inline rendering, so an accepted upload is not
turned into executable or active content on the system that received it.
