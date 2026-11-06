# Frozen native scene contracts

Each pair freezes output from the historical serializer for its recorded version,
independently of the current serializer. `source_commit` identifies the recorded
private development revision; do not rely on it resolving in published history.
The checked-in bytes, expected fields and manifest hashes are the public test
contract, not a claim that this repository can reconstruct the original history.
The renderer and asset-root arguments use public placeholders; no personal configuration or maps
are included. v2's body is its historical shipped sample. The manifest pins the
bytes and the expected model fields, including later defaults.

Do not regenerate existing versions to accommodate current code. A deliberate
new format adds a new golden while retaining every supported historical pair.
These fixtures test native compatibility, not renderer or asset certification.
