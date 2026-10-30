---
corpus-id: rvwpin
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [TRUST]
slug: review-in-flight-pins-its-artefact
---

# A review in flight pins its artefact

Once a review, verification, or adversarial check has been dispatched against a named artefact or
revision, that artefact is not modified until the review returns or is abandoned. A reviewer's findings
are meaningful only against the state it observed: a target that moves under it invalidates its line
references, forces it to re-derive the ground truth mid-review, and makes its report impossible to
reconcile against other reviewers of the same nominal revision. The target this holds stable is the
mutable one the review named, a working tree, the tip of a branch, or a file under examination, which is
distinct from committing an artefact to an immutable object identity before the review reads it and from
the inertness of the reviewer's own output. Where a change genuinely cannot wait, it is made on a
separate revision and the in-flight review is left undisturbed, to be re-dispatched against the new
state once that change has settled.
