---
corpus-id: secdsz
origin: pack
family: security
facet: SECI
slug: safe-deserialization
map-cwe-tight: [CWE-502]
map-cwe-broad: [CWE-20]
map-owasp-web-broad: [A08]
map-owasp-asi-broad: [ASI05]
map-owasp-cheatsheet-tight: [deserialization]
map-csa-ccm-broad: [AIS-04]
map-csa-aicm-broad: [AIS-09, MDS-02, MDS-13]
---

# Deserialize untrusted data only as data

Data from an untrusted source is never passed to a deserializer that can instantiate arbitrary types or
run code during parsing, such as pickle, Java native serialization, PHP unserialize, or unsafe YAML. A
data-only format or a schema-bound parser is used instead, so parsing cannot become execution.
