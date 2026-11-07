# Maps and textures

These Earth and planetary images are third-party assets. The project's MIT
license does **not** relicense them. Source records, known terms and unresolved
per-file provenance are documented in [asset credits](../docs/asset-credits.md).
Attribution alone does not grant redistribution rights; review those records
before copying or sharing imagery. Scene exchange references bundled maps and
does not silently include them.

The numbered solar-system directories group a planetary system and its bodies.
`solarsystem/body-maps.txt` indexes the retained map collection. Its historical
`map=/solarsystem/...` notation is an inventory, not a portable absolute filename
or a complete scene configuration. From a project search root, use the actual
`maps/solarsystem/...` path; setup also prepares `images/solarsystem` as a link
for native configurations using that image lookup route.

Optional textures may be used by personal native configurations; lack of a
stock-scene reference does not make an asset disposable. In particular, Triton,
Ariel, Umbriel, Titania and Oberon images exist in the Celestia collection even
though the studio does not offer those bodies. See
[resources and prerequisites](../docs/resources.md) for installed-package data,
project assets and the difference between file presence and scene support.

## Renaming a tracked map family

New map paths remain ignored to prevent accidental publication of personal images.
Use `git mv maps/old-family maps/new-family` for tracked maps, then review
`git diff --cached --stat`. A filesystem rename followed only by `git add -A`
stages removal of the old paths but leaves the new paths ignored. If the files
were already renamed that way, explicitly review and stage only that known family
with `git add -f -- maps/new-family`; verify the indexed filenames and unchanged
image bytes before committing. Do not force-add the entire maps directory.
