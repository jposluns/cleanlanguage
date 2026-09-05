---
corpus-id: trkasy
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [QUALI]
slug: track-launched-work
map-nist-airmf-broad: [MANAGE 4.3]
map-iso-42001-broad: [A.6.2.6]
map-iso-23894-broad: [6.7]
---

# A launched task stays observable

A unit of work whose result or completion the caller depends on is launched so its outcome stays observable,
never discarded at the moment it starts. A task started and abandoned, a background process whose completion
is neither collected nor monitored, an asynchronous result neither awaited nor otherwise observed, or a queued
job whose outcome no one reads, hides any failure it carries and leaves a later claim that it finished
ungrounded. Such work is launched through a mechanism that tracks it to completion and surfaces both its
result and its failures; a launch that drops the completion signal is not a safe way to start work the caller
relies on. Where neither its result nor its completion is genuinely needed, running the task without tracking
it is a deliberate, recorded choice, not the default.

A tracked deliverable whose output is captured only through a truncating filter is not observable
completion: the completion signal must carry the full result, never a truncated view of it.

Shell syntax that detaches a child from an otherwise foreground call launches asynchronous work no less
than an explicit background dispatch does: the foreground call returns while the detached child runs on,
so its result and its failure are lost unless they are collected. Such work is launched through a tracked
background mechanism that keeps its completion observable; where its result and completion are genuinely
not needed, detaching it is a deliberate, recorded choice, not a reflex.
