# Durable render exports

**Export latest…** copies the retained successful preview; **Export comparison sheet…**
copies the latest complete three-frame set. Neither rerenders. They work with the
recorded snapshot even after the draft changes: read the scene/time shown in the
confirmation rather than assuming the image matches today's editor fields.

Choose an absolute **new directory**, then confirm **Export copy**. The default
suggestion is `output/exports/export-preview-TIMESTAMP` or
`output/exports/export-sheet-TIMESTAMP` under this checkout. Only the default
`output/` and `output/exports/` parents are created automatically, after confirmation
and successful snapshot validation. Other destinations need an existing real parent.
Existing files/directories, linked path components, control characters and
destinations inside the temporary preview workspace are refused. Nothing is
overwritten. Cancelling the destination dialog creates no directories or files.

The originals, undo/baseline, native scenes, selected scene, providers, jobs and
desktop remain unchanged. Native scene saves still use `config/scenes/`. Previous
exports, including copies under `config/`, stay where they are; there is no automatic
migration, deletion or pruning. Shell `preview`/`render` instead use replaceable
`output/preview/` images. All of `output/` is excluded from versioned source and
release privacy checks reject it even if added with force.

A preview export contains `preview.png` and `export.json`. The receipt records
geometry, scene summary, render completion UTC, fixed/current time policy, image
size/hash and export time. A Now preview's completion time is not an exact exposure
or data-collection epoch. A sheet export contains `index.html`, `frame-1.png` through
`frame-3.png`, its `comparison.json` and an export receipt. HTML uses relative image
links, escaped captions and no scripts/external resources. Keep the directory's
files together; open index.html explicitly in a browser if desired.

Image bytes are copied exactly and bind to retained file identity; changed or missing
source images fail safely. Sheet frame hashes and reviewed comparison parameter values must also
match. An ordinary preview is limited to 64 MiB for export; sheet frames remain
16 MiB each. Header geometry is checked, but this is not a complete PNG decoder or
scientific/resource certification. Scene geometry time is not an imagery epoch.
Receipts omit executable/source paths, raw diagnostics and private producer config.
The PNG's own embedded metadata and visible labels are retained; review before
sharing. Exports are image artifacts, **not portable configuration bundles**.

Source reads are bounded and cooperatively cancellable. Publication reuses exclusive
owned-file creation; no detached writer continues after cancellation. A completed
export stays saved when the editor exits or receives an interrupt. Filesystem calls
and final writes can delay input; there is no hard storage-time or power-loss
guarantee. Failure removes only unchanged files demonstrably created by that attempt.
Changed/foreign material may leave a partial destination for inspection; never delete
it blindly or retry with overwrite. Choose a fresh directory after reviewing it.

The studio still cleans its temporary originals on exit. Explicit exported copies
remain outside that cleanup; they are user-owned and never automatically pruned.
Choose a persistent location if they must also survive OS cleanup of temporary folders.
