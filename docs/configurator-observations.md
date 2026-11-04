# Frozen Earth observations

The configurator can explicitly capture **existing** TotalMarker earthquake and
volcano markers, and a coherent storm marker/arc pair. This does not run a producer,
contact a provider, lock or recover TotalMarker state, or change source files.
Cloud capture remains a separate operation; see [frozen clouds](configurator-cloud-capture.md).

Choose **Use frozen capture** for the desired products, keep target **Earth** and
time **Now**, review the existing source root/config, then choose **Capture selected
observations…** and confirm. Merely opening the editor, choosing a layer or cancelling
the confirmation reads no source product. A failed/cancelled capture retains prior
captures and successful previews. Source fields are transient and not saved.

## What is captured

Capture requires the saved marker SHA-256 to match the actual bytes. Storms require
both marker and arc hashes from the same stable saved record. Configuration, records,
referenced icons and pending-journal presence are rechecked; changing publication is
retried at most once. Any pending product journal causes refusal, not automatic replay
or deletion. Legacy/unverified output without matching saved hashes is refused.

Only the known TotalMarker Python marker/arc syntax is accepted. Coordinates,
quoted labels, colors, alignments, bounded symbols and explicit image dependencies
are validated; unknown options, repeated options or arbitrary file/font references
are rejected. Labels and supported styles are preserved in canonical native rows;
no arbitrary native text is passed through. Global fonts/defaults come from the
scene and renderer; the producer working `xp.conf`/`xp.def` is not imported. This
is not general configuration import.

Referenced producer icons must match its configured image dependency and be regular
contained files. This slice supports PNG containers up to 1 MiB and 512×512 only;
other formats are refused rather than silently omitted. Container/chunk/dimension
checks are not a full decoder certification. PNG embedded metadata is unchanged;
review captured imagery and labels before sharing a saved scene.

Limits: 256 KiB and 4096 rows per marker/arc file; printable rows up to 240 bytes
before scene-name prefixing; labels up to 160 UTF-8 bytes; symbols up to 512 pixels.
Scene-name prefixing is checked against the same saved-file bounds before writing;
a large icon-marker file may require a shorter scene name or legacy directory save.
Supported values outside these studio bounds are refused without modifying source.
All cloud/observation capture history shares a 128 MiB session budget. At the limit,
save a new scene and reopen it rather than silently evicting Undo data. Capture has
an isolated finite worker/wait budget and cleanup, not a guaranteed hard filesystem
latency bound. No extra provider or imaging dependency is installed.

## Time, freshness and provenance

Current-data-derived observations are active only for **Earth + Now**. Fixed UTC,
planetary targets or Off retain choices and captured bytes but omit marker/arc files
from rendering. The live update label is never copied. Storm forecast arcs remain
part of the captured producer product; they do not enable future-scene observations.
The explicitly dated bundled 2011 cloud image is a separate static imagery choice.

Provenance records capture time, original publication hashes, source/report and
check/attempt/success/publication timestamps when available, reporting period and
source validity/coverage boundaries, plus the recorded producer outcome. It includes
neither source paths/configuration/credentials nor URLs/error text. Missing facts
remain unknown. Successful source access is not claimed. Quake freshness remains
unassessed; storm validity and volcano weekly coverage reuse TotalMarker health
policy and can become stale as time passes. A verified retained product can be
captured after a failed producer refresh; the failure remains visible as a warning.

Preview comparison retains the exact provenance of each successful rendered scene.
A frozen image is not a live display, and a fresh local capture time does not make
its source observations current.

## Save and reopen

V10 saves include the native marker/arc files, referenced PNG icons and bounded
`observations.json` provenance. Named scenes prefix all associated files and icon
references (for example `earth.observed-quake.markers`); metadata uses canonical
scene-independent names/hashes. Reopening verifies associations and hashes, never
reads the original producer, and does not adopt imported executable/asset roots.
Inactive captured data remains portable with the scene. Old configurator formats
still reopen; new observational choices cannot be written into an older format.

Original configurations, producer files, desktop settings and schedules are untouched.
Saving is still a new-copy operation, not Apply. See [configurator](configurator.md).
