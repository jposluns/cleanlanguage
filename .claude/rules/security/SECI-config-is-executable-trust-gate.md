---
corpus-id: seccet
origin: pack
family: security
facet: SECI
slug: config-is-executable-trust-gate
map-cwe-tight: [CWE-829]
map-nist-80053-broad: [SI-7]
map-owasp-asi-tight: [ASI05]
---

# Configuration that executes on load is treated as code

Agent, editor, workspace, and repository configuration and hook definitions that can trigger execution
when they are loaded, opened, or applied are executable code, not inert settings, and pass the same
review and trust gate as code before they are trusted or run. Whether a file has that property is decided
by what it can do on load, not by its name or format, so genuinely inert configuration, values a tool
only reads, is never swept in. An executable configuration is reviewed for what it will run, from
whatever source it arrived, exactly as hand-written or generated code is, and until it passes that gate
it remains untrusted.

A Python-launched hook or gate places its own script directory first on the interpreter's module path, so
a file written beside the script can shadow a standard-library import and silently disable the control. A
direct Python launcher for such a configuration therefore runs isolated: `-I`, or the complete `-P -E -s`
equivalent, placed before the executed script.
