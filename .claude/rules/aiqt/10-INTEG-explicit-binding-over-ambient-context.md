---
corpus-id: expbnd
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [ACCUR, QUALI]
slug: explicit-binding-over-ambient-context
---

# Bind to the explicit target, not the ambient context

An action that has an authoritative, explicit way to name what it acts on, its identity, its target,
or its scope, binds to that explicit name rather than inheriting the binding from ambient context
that can silently point elsewhere. Ambient context is inherited mutable state not named at the point
of use: the current working directory, the current tree or index state, the process environment, the
wall clock, and the order in which results arrive or complete. Where an explicit binding is available
and unused, the action is bound to it; where only an ambient binding exists, the execution target is
confirmed by observation before the action runs, per the confirm-execution-target discipline.

This manifests in three recurring forms. An asynchronous result is correlated to the dispatch that
produced it only through the authoritative identifier that dispatch returns, a handle, a path, or an
id, never by wall-clock proximity or arrival order, because two dispatches can complete out of order
or at the same instant and ambient timing cannot tell them apart; a result with no identifier is
surfaced as unbound, never assigned to the nearest or most recent dispatch. A command with side
effects prefers to name its target on the command that performs the mutation, a repository or
working tree bound by an on-command flag rather than left to the current working directory. Where
the same command also shifts that target, a directory change chained ahead of the mutation or a
wrapper that redirects the tool, the ambient binding is no longer the target named at the point of
use, so the explicit on-command binding is required there because the mutation would otherwise read
its target from wherever the shell landed. A bare mutation left in the session's working directory,
with no such shift confusing its target, is not thereby a violation: its ambient target is confirmed
by observation under confirm-execution-target rather than forced to carry that flag. A destructive
or broad operation takes its scope from the specific thing under change, an enumerated set of paths,
rather than from ambient whole-tree state; a breadth selector that stages, commits, or discards
whatever the tree currently holds can sweep in unrelated work, and where committed state is needed
for a fixture or test, an isolated checkout provides it rather than reshaping the shared working
tree in place.

The preference is to remove the ambient dependency, not merely to check it: an explicit binding
removes that ambient dependency, whereas a confirmed ambient binding is correct only until the
surrounding state next shifts. This is the prefer-removing-a-path preference applied to how an
action names its referent, and it sits beside confirm-execution-target, which governs the residual
case where only an ambient binding exists, and absolute-paths, its file-path instance. An explicit
binding is still not proof of intent: a named target can be the wrong target, and confirming it is
confirm-execution-target's obligation. When an ambient binding would discard uncommitted work or
absorb unrelated changes into a change set, preserve-uncommitted-work and separate-task-changes
govern that loss; this rule governs the prior choice of what the action was bound to.
