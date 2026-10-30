---
corpus-id: gensrc
origin: pack
family: aiqt
tier: 10
facet: INTEG
slug: generated-artefact-source-only
---

# A generated artefact is changed only through its source

A derived or generated artefact is never hand-edited; it changes only by changing its source and
regenerating. Source and derivative land in the same change, so the two cannot drift apart.
Deriving an artefact leaves its source originals byte-for-byte unchanged and writes separate outputs;
in-place derivation uses copies in an area excluding the originals and refuses any path or alias
writing outside it or back to an original.
