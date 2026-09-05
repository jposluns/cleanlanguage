---
corpus-id: abspth
origin: pack
family: aiqt
tier: 10
facet: QUALI
slug: absolute-paths
---

# Use absolute paths, not relative

A file path the assistant passes to a tool call, command, or file reference is absolute, not relative to
an assumed working directory, because that directory can silently differ between tool calls, subprocesses,
and sessions and send the action at the wrong target. A relative path is used only when the tool or format
in use requires a path relative to a named fixed root, and that root is identified where the path appears.
