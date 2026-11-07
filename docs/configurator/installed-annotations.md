# Installed sky and planetary annotations

The studio can explicitly import four small datasets from a locally installed
Xplanet resource directory. This reads existing files, never downloads data,
changes the package, rewrites a working configuration or selects/restarts a desktop.
Normal star rendering and the renderer's existing BSC catalogue remain unchanged.

## Use a layer

1. Choose **Space** for bright-star labels or constellation lines, **Moon** for
   Apollo sites, or **Mars** for historical surface labels.
2. Turn the desired annotation layer On. Enter the installed `share/xplanet`
   directory in **Installed xplanet data directory**. Use the actual local path;
   Homebrew's prefix differs between machines. A package-root symlink is allowed,
   but linked descendant files/directories are refused.
3. Choose **Import selected annotations…**. This imports every selected On layer,
   including choices retained while another target/projection is active. Import
   replaces only those datasets in the draft. Review the row counts, then Preview.
   For sky overlays, try FOV framing at 90°; a narrow radius-derived view may
   contain no bright-star labels or constellation segments.
4. Save a new scene. The normal reviewed selection workflow can use that scene;
   saving, selection and restarting remain separate actions.

An active layer without imported data blocks Preview and Save. Off layers retain
imported bytes; switching targets or to a projected map retains choices without
rendering incompatible overlays. Undo/redo and private draft recovery preserve
these choices. Failed/cancelled imports leave previous data intact. A saved scene
continues working if its original package is upgraded or removed, provided the
renderer and the scene's other map/font dependencies remain available.

## Coordinate and evidence limits

- Bright-star labels use `markers/brightStars`; constellation segments use
  `arcs/constellations`. These are **sky** overlays, with declination in degrees
  and right ascension in hours. They become CLI `-marker_file`/`-arc_file` options
  only in space mode. They do not turn a map projection into a sky view.
- Apollo labels use `markers/moon`, with Moon east-positive longitude. They are
  attached only to the Moon target's body section.
- Mars labels use `markers/mars`, with west-positive longitude and its historical
  named-color styles. The source includes old mission sites and is not a current
  gazetteer. No coordinates, map registration or scientific accuracy are certified.
- Visibility still depends on camera, illumination, field of view, font support,
  overlap and the renderer's marker-size thresholds. Import success alone does
  not establish that every label will be visible.

Only these datasets and their bounded native grammar are supported. The importer
refuses custom image/font dependencies, pixel positions, timezones and other native
options. It validates finite coordinates, row/line/byte limits and UTF-8 text. Each
source is limited to 96 KiB/2048 physical lines; selected records are limited to
128 bright labels, 1024 constellation segments, 32 Apollo sites and 128 Mars labels.
The source root and inputs are rechecked before accepting the complete import.

## Native files, provenance and sharing

New saves use scene format v17. Existing v2–v16 scenes remain readable without
rewriting their source and start with these layers Off. The generated scene owns
up to four associated files, prefixed by its name:

- `scene.sky-labels.markers`
- `scene.sky-constellations.arcs`
- `scene.moon-sites.markers`
- `scene.mars-names.markers`

Each contains the source-relative dataset name, SHA-256 of the original input,
retained attribution comments and canonical validated rows. Comments are moved after
records and the legacy Mars comma delimiter is normalized. The definition binds
these derived bytes separately with their own hashes. The importer does not add the chosen local pathname; source comments are retained
and may contain other personal or contributor information. This establishes internal consistency, **not** upstream authenticity
or verification of the coordinates. Files supplied under these names may be local
modifications; the receipt explicitly says their identity is unverified.

Save/reopen, unchanged native copy, comparison previews, reviewed immutable selection
and local scene archive export/import retain all imported files, including inactive
ones. Selection freezes the data instead of referring to the mutable installed
package. Sky CLI references are compiled to the frozen revision's absolute paths;
body annotations retain scene-owned relative references. No source sharing happens
merely by saving or exporting an archive locally.

Imported datasets retain their own upstream/contributor terms. They do not acquire
the project's MIT license. Export includes their data and attribution; review those
terms and the visible labels before sending an archive to someone else. Dataset
comments can contain contributor names or addresses. The project does not vendor
these installed datasets or download a replacement automatically.
