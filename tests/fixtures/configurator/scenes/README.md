# Frozen native scene contracts

Each pair was produced by the historical serializer at the recorded commit that
introduced its version, independently of the current serializer. The renderer and
asset-root arguments use public placeholders; no personal configuration or maps
are included. v2's body is its historical shipped sample. The manifest pins the
bytes and the expected model fields, including later defaults.

Do not regenerate existing versions to accommodate current code. A deliberate
new format adds a new golden while retaining every supported historical pair.
These fixtures test native compatibility, not renderer or asset certification.
