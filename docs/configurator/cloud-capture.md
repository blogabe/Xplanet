# Frozen TotalMarker cloud capture

The configurator can explicitly capture an existing TotalMarker cloud product
for a **Now** scene. It never fetches clouds, refreshes a provider, runs a product
job, takes a write/create lock or replays/removes a journal. This is separate
from the bundled **26 August 2011** static image, which remains available with
its date caveat. Neither is described as an upstream stock cloud map.

## Capture deliberately

1. Choose **Now**, then **Frozen TotalMarker capture — Now only** in Clouds.
2. Enter the existing TotalMarker root and its configuration path (normally
   `config/totalmarker.toml`, relative to that root). These source fields are
   transient, not scene settings. Merely selecting the mode reads no source data.
3. Choose **Capture existing clouds…** and confirm the source. Missing setup,
   invalid outputs or pending publication produce an explanation, never an
   automatic install/refresh/recovery action.
4. Review the captured provenance and health, then Preview or Save a new copy.
   A new capture is explicit; previews and reopening never recapture silently.

The worker reads bounded regular files through TotalMarker’s contained resolver,
including supported internal aliases; outside-root links and nonregular files
are refused. It parses one captured config, requires the image to match saved
state, checks state/config stability and absence of configured pending publications (all share state), and
retries a changing publication at most once. It uses the existing JPEG validator
and requires a 2:1 image up to 8192×4096 and 32 MiB. This is structural validation,
not a complete pixel decoder or independent proof of provider origin.

Capture runs in an owned process group with a 10-second wait budget and
termination cleanup. Cancel capture leaves the editor and previous capture/preview
intact; the usual exit keys stop work and restore the terminal. Local filesystem
stalls or termination cleanup are not promised to obey a hard wall-clock limit.
Original producer files, state, journals, locks and labels are not changed.

## Interpret the metadata

The frozen image is accompanied by a small allowlisted provenance record: image
hash/dimensions, local capture UTC, known image-creation UTC, separate saved
producer check/attempt/success/publication times, recorded outcome and the saved
warning interval. Unknown creation time stays unknown; file modification time
or capture time is never substituted for observation time. Freshness uses
TotalMarker’s existing cloud policy.

A verified last-good image can be captured after a failed refresh or when stale;
those conditions remain explicit warnings. An integrity mismatch, invalid image
or pending publication is blocking. Access is **not checked** by capture. A
local saved hash binds bytes to the saved record; it is not a provider signature.

## Time policy and labels

Changing to **Fixed UTC** omits current-data-derived captured clouds, their gamma/
threshold effects and live product update labels from rendering. The choice and
frozen bytes remain available for undo and a later return to Now. Fixed-time
scenes can retain a not-yet-captured choice without reading a producer root.

The dated 2011 bundled image is a deliberately selected static texture, with its
own warning; it is not current TotalMarker weather. Static place annotations
and the optional renderer UTC **scene-time** label remain separate. The
configurator does not include TotalMarker’s `markers/updatelabel` file at all.

## Save, reopen and portability

New native v6 scenes reference associated `name.cloud-capture.jpg` and
`name.cloud-capture.json` files in a named library, or fixed unprefixed names
in supported legacy directory saves when a capture is retained, alongside xp.def/xp.conf
and any geographic lists. The JSON is provenance, not a parallel settings store.
Both files are preserved even if their current-data layer is inactive; xp.conf
omits that layer for Fixed UTC. Reopening checks bounded regular files, stable
identity, exact metadata, image hashes/dimensions and the scene’s capture identity.
It uses the saved bytes without needing the producer installation. Earlier scene
formats remain readable; saving still creates a new directory and never Apply.

Provenance excludes producer roots/config paths, credentials, URLs, full state/
logs and raw errors. Original JPEG bytes and embedded image metadata are retained
unchanged; this is not an image anonymizer. Existing native executable/asset-root
references remain local references as before, so review those when sharing. Keep
image/provider credits; bundling data does not change its source terms.

Undo/redo tracks capture identity and retains prior immutable captures in the
current draft. Combined cloud, observation and astronomy capture history is bounded to 128 MiB; reaching it refuses
a new capture without evicting undo data. Save/reopen or open another scene to
establish a fresh history. This is a capture-storage budget, not a total renderer
or application memory cap. Existing preview/viewer behavior is unchanged.

Frozen [storm/quake/volcano products](observations.md) and
[NORAD/dated eclipse products](astronomy-capture.md) have separate
validated capture workflows. Persistent live references remain future work. A Now clock still
changes on rerender; frozen input does not freeze scene geometry or certify
pixel-identical results across builds. No UTM validation is claimed here.
