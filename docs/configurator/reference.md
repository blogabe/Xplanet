# Configurator reference

New to the studio? Start with the [user guide](user-guide.md), use
**Help / F1** in the editor, or print it with `scripts/xplanet.sh config --guide`.

Open the scene studio (Earth is the initial target) with `scripts/xplanet.sh config`, or reopen
a configurator-produced view to revise it and save a new copy. This is a
separate editing flow within the repository, also available from management.
It can run before permanent desktop setup; it does not require personal xp.def,
xp.conf, TotalMarker configuration or registered jobs.

## Prerequisites

Use a complete checkout, Python 3.11+ and an installed Xplanet build with PNG
output and its stock Earth/night textures. Homebrew remains the recommended
renderer installation; see the [installation overview](../../README.md#install-on-macos).
There is no live provider request or implicit prerequisite installation.

Prepare the UI explicitly once:

```sh
./scripts/xplanet.sh config --prepare
./scripts/xplanet.sh config
# If Xplanet is not on PATH:
./scripts/xplanet.sh config --renderer /absolute/path/to/xplanet
```

`--prepare` creates `.state/configurator/venv` using the compatible interpreter
selected through the existing [Python selection](../python-runtime.md). It downloads
an exact, hash-checked Textual dependency set from PyPI **only into that venv**.
Both Homebrew and uv-managed Python can create it; uv is not required. No global
pip, package migration, provider removal or PATH changes occur. TotalMarker
remains standard-library-only. Merely opening management installs nothing.

The UI environment keeps its original interpreter when the TotalMarker selection
changes. If its base Python disappears or the dependency lock changes, explicitly
move only `.state/configurator/venv` aside and run `config --prepare` again;
preserve private recovery data in `.state/configurator/drafts`. Preparation
refuses to replace an existing environment. A failed preparation may leave that
incomplete directory for inspection. Normal updates do not install UI dependencies.

## Explore, preview, save or cancel

Blank UI drafts start at the primary macOS display's bounded backing-pixel size,
with an explained 1920×1080 fallback. Saved/stock scenes keep their dimensions.
Previews use stock or selected bundled textures and explicitly frozen layers;
there are no live overlay references. Fields remain freely editable; this is not a serial installation wizard.

For a fixed observer above the Moon and percentage frame-centre controls, see
[Lunar orbital camera](orbital-camera.md).

See [geometry and resource diagnostics](diagnostics.md) for frame limits,
explicit binary-capability checks and qualified resource evidence. An input map’s
2:1 texture layout does not require a 2:1 output frame. Pre-v14 saved scenes retain
their original 800×600 dimensions; v14 scenes retain their stored dimensions.

| Control | Meaning |
| --- | --- |
| Preview geometry | Blank UI drafts use the primary macOS display's backing-pixel size, within the 16,777,216-pixel bound; unavailable/out-of-bound detection visibly falls back to 1920×1080. Logical points and additional display sizes are shown separately. Saved/stock scenes retain their dimensions; manual changes remain authoritative. No display settings or lifecycle defaults change. |
| Rectangular / orthographic map | A projected target view using latitude/longitude. Orthographic is still projected mode. |
| Space (no projection) | A non-projected target view, with geographic or body-origin camera choices. |
| Geographic observer | Latitude/longitude above the target; studio bounds are ±90° latitude and ±180° longitude. |
| Earth / Moon / Sun / opposite Sun | Space-view observer at a different body or opposite solar direction. Sun/opposite-Sun are day-side/night-side constructions, not a local civil-time setting. An origin matching the target is blocked. |
| Radius / field of view | Space framing alternatives: target radius as % of image height, or angular FOV. The studio permits radius 0.1–100% and FOV 0.1–179°. Only one is sent to the renderer. |
| Day map / month | Stock renderer Earth, or one of three bundled 2004 monthly families: Earth, topography, topography/bathymetry. Month is independent of scene time; changing time does not silently change imagery. |
| Night texture / twilight | Stock night map or bundled Earthlights 2002; twilight sets the day/night blend width in whole degrees, 0–90. It is not a night-map brightness control. |
| Relief / shadows | Bundled GEBCO height-map shading; exaggeration 0.1–5 is a studio range. Shadows can use night imagery or the day map shaded by a whole 0–100%. This changes shading, not camera altitude. |
| Specular | Optional bundled ocean reflectance mask; actual reflection depends on illumination/view geometry. |
| Clouds / gamma / threshold | Optional **26 August 2011 snapshot**, or an explicit **frozen TotalMarker capture for Now only**. Gamma 0.1–5 changes brightness; whole threshold 0–255 hides dimmer pixels. |
| Grid | Off or 30°, 15°, 10° major spacing, with 1° dots; presets derive the engine grid divisors. |
| Label | Off or the renderer’s UTC scene-information label; rendering requires suitable font/build support. This is scene time, not provider freshness. |
| Now / fixed UTC | Renderer clock for each preview, or a strict `YYYY-MM-DDTHH:MM:SSZ` calendar instant. Fixed dates are limited to 1800–2200, except Pluto/Charon geometry uses 1800–2099. No astronomical-accuracy certification is implied. |

Irrelevant controls are hidden with contextual explanations; their values stay
in the draft and in saved scenes. A retained invalid value is exposed and enabled
for correction, even when it is not part of the active scene. Returning to a
mode restores its choices. Retained values must also remain valid so reopening
is lossless. Map mode never emits a retained space origin, radius or FOV.

Fixed UTC controls scene lighting/geometry. It does not change label timezone,
provider timestamps, data freshness or the age of stock textures, and performs no
data refresh. Stock city lights are not a historical reconstruction. Opposite-Sun
previews can include the Sun/glare behind Earth and a bright background. The retained
initial fixed value is `2000-01-01T12:00:00Z`; Now remains the default.

**Preview** renders one PNG in a temporary workspace, with a 30-second render
wait budget and termination cleanup. It never changes wallpaper or starts desktop
jobs. **Cancel preview** stops that attempt and keeps the editor open; Escape or
the main Cancel action requests a protected exit. Ctrl-C first cancels active work; an idle or repeated Ctrl-C exits using the last complete recovery checkpoint. Invalid settings, launch/output errors, timeouts and
cancelled attempts preserve the last successful image and comparison history.

**Open latest** explicitly opens the retained result in the macOS image viewer.
The preview status identifies when active settings or the executable identity have changed since that image;
matching settings do not make a Now image live or establish imagery freshness.
After two successes, **Compare…** describes the before/after camera, time,
renderer and completion timestamps, with separate deliberate image-open actions.
This is two-snapshot viewing, not an aligned pixel-difference or compositor tool.
Only the two latest successes are retained; failed attempt directories and older
snapshots are discarded. All preview files disappear when the editor exits; an
image already loaded by the viewer may remain visible there.

**Save & close…** or **Save & continue…** reviews changes and a new named destination, defaulting to
`config/scenes/earth-view.conf`. It creates matching `.conf` / `.def` files and
scene-prefixed optional assets in that same library. Existing names, case aliases
and associated-file collisions are refused. The library folder is created only
when a confirmed Save needs it; its parent must already exist without symlinks.
A destination without `.conf` retains the supported legacy new-directory save.

The default body config remains byte-for-byte the shipped sample. Appearance
changes generate a constrained native body config; supported camera/time and
appearance settings, including inactive preferences, are recorded in xp.def.
Save & close exits; Save & continue keeps the editor open, advances the clean
baseline to the new copy, and retains undo/redo, frozen captures and previews.
It proposes another new filename for the next copy. Undo can therefore return to
an earlier draft and mark it unsaved; it never deletes a saved file.

Ctrl-D/Ctrl-Q, main Escape and Cancel request exit. A dirty studio draft offers
**Keep editing**, **Keep recovery draft and exit**, or **Discard draft and exit**.
Ctrl-C cancels active work first; idle/repeated Ctrl-C exits without a new native
save. Private recovery checkpoints preserve raw/invalid studio inputs and frozen
captures, with no selection/provider replay. See [recovery and keys](recovery.md)
for concurrent sessions, bounds, signals and emergency-exit limitations.
Previously saved copies and explicit scene selections remain.

Saving is not Apply: it creates a new library copy and does not change selection,
legacy config, schedules or the running desktop. The implemented
[reviewed Apply workflow](apply-design.md) can separately select an
immutable revision for the next explicit start/restart. Selected desktop execution
consumes the studio camera/time/appearance arguments through the zsh scene path;
no selector keeps the custom configuration path. Do not copy studio definitions over active
custom configuration expecting that path to interpret every studio field.

A session may select a scene and then save another draft. The completion message
reports both outcomes; uncertainty about selection still exits with status 5 and
requires inspection, even if the new draft was saved successfully.

## Local Earth layers

The bundled choices below display existing files; they do not fetch observations,
run TotalMarker or alter a schedule. Each switch preserves hidden parameters
for undo, review and save/reopen. Invalid inactive parameters still need correction.

- **Relief:** `maps/bump/gebco_08_rev_elev_21600x10800.png`. The engine
  derives shading from this height map. Relief exaggeration has a studio range
  of 0.1–5; it is not certified terrain geometry or an observer-height control.
  By default shadows use night imagery. Choosing shaded-day shadows exposes
  `bump_shade` (0–100 whole percent), independent of the true night texture.
- **Specular:** `maps/specular/specular.png`, the bundled ocean-reflection
  mask. Reflected sunlight may be subtle or absent for the chosen geometry.
- **Clouds:** `maps/clouds/clouds_26Aug2011_2048.jpeg`. This is an archived
  2011 snapshot, deliberately labelled as such even with Now selected. Gamma
  changes its brightness and threshold hides dimmer pixels; a high threshold
  can hide nearly all clouds. Changing scene UTC does not retrieve weather for
  that time. This is separate from TotalMarker’s generated cloud product.

Relief/specular assets are high resolution and can require substantial decoding
memory/time. A preview has the existing finite wait budget and cancellation,
with prior successful output retained after failure. The editor does not silently
replace these assets with reduced copies or install image-processing software.
Xplanet may resize maps to match the day texture and report that diagnostic.

Health checks presence of the selected whitelisted regular files and reports
requested paths and caveats. It does not certify image contents, engine codecs
or scientific accuracy. New native saves retain all layer settings but reference
the checkout’s bundled files rather than embedding images. V4 and earlier scenes
reopen with these layers off. Explicit existing-cloud capture is described in the [frozen capture guide](cloud-capture.md).
Other live TotalMarker output references, product refresh controls and provider
configuration remain separate work.

## Places, labels and routes

Enable **Places and labels** or **Static great-circle route arcs** to expose
the relevant editor/style controls. Each is a small native surface-coordinate
list, with at most 32 rows, 8 KiB total and 200 UTF-8 bytes per line.

Places use `latitude longitude "Label"`, for example:

```text
51.5 -0.1 "London"
40.7 -74 "New York"
```

Labels are printable text of at most 80 UTF-8 bytes, without quotes/backslashes.
Color and whole-pixel font size (10–24) apply to the list. The renderer chooses
label placement; overlap, back-side visibility and font/glyph support still matter.
No geocoding, icons, pixel/sky coordinates or arbitrary per-marker options are
accepted. These labels are separate from the optional UTC scene-information label.

Routes use `latitude1 longitude1 latitude2 longitude2`, one arc per row:

```text
51.5 -0.1 40.7 -74
```

Use additional rows with shared endpoints for a segmented route. Colors and
whole-pixel thickness (1–5) apply to the list. These are static great-circle
surface arcs, not travel planning, trajectories or calculated eclipse paths.
Identical endpoints have no visible length; antipodal endpoints do not define a
unique path. Longitudes are east-positive within ±180°, latitudes within ±90°.
No native options, comments, file references or command hooks are accepted in
these editors; blank lines and entered numeric precision/order are preserved.

Off hides the related controls and omits the layer from rendering, but preserves
its text/styles for undo, review and save/reopen. Invalid retained text is exposed
for correction and blocks Save/Preview, consistently with other inactive values.
Native `places.markers` and `routes.arcs` files are written only when their list
is enabled or contains retained text; xp.def declares fixed relative names.
The loader accepts only those names, real bounded files and recognized headers,
and checks their stable identity alongside xp.def/xp.conf. Missing/tampered lists
fail safely. Preview writes its own copies; original files are not modified.

These files are independent static annotations. They neither read nor alter
TotalMarker’s generated products, providers or schedules.

## Change review and undo

The editor shows whether the current draft has **unsaved scene changes** against
the snapshot opened in this session, or the shipped sample when starting fresh.
**Review changes** lists before/after values and identifies active versus retained,
currently inactive settings. The same review appears in the Save confirmation.
It describes proposed settings, not a live diff against files that may have
changed elsewhere; source files are never reread or overwritten by review.

The local executable selection is tracked from the point this scene was opened,
not compared with the untrusted executable recorded in an imported file. The
save destination is not a scene setting or part of undo. Equivalent numeric
formatting, such as `0` and `0.000`, does not mark the scene dirty, although its
raw text can still be undone. Invalid text does count as a change and remains
available for diagnosis or undo.

Use **Undo / Redo**, **Ctrl-Z / Ctrl-Y** in the editor. Typing in one field is
grouped until focus leaves it; selection changes are individual edits. History
includes camera, time, appearance, retained inactive values and the local
executable field. It retains up to 100 undo steps in memory; older undo states
may be evicted, while change review keeps the original baseline. A new edit
after Undo discards the redo branch. Review/confirmation dialogs do not allow
these shortcuts to change the draft underneath them.

A successful Open explicitly replaces scene settings, preserves the selected
renderer, establishes a new baseline and clears undo/redo; the Open dialog warns
when replacing unsaved settings. Failed or cancelled Open leaves the draft,
baseline and history intact. Back from Save or a failed save also retains them.
Save & close exits; Save & continue establishes a new clean baseline without
clearing undo. Both create new copies, never overwrite an existing scene.
Protected exit and emergency interruption follow the [recovery contract](recovery.md).
Neither rolls back prior saves or selection. Recovery retains raw fields and a baseline,
not the session undo stack; native files are never autosaved.

Undo changes draft settings only: it does not undo a renderer process, an image
viewer, a saved file or a desktop action. Retained preview staleness is recomputed
against the restored draft; a matching Now image is still only a snapshot.

## Bundled assets and native references

The day-map selector covers the 36 finished monthly PNGs in
`maps/world`, `world.topo` and `world.topo.bathy`. These are 2004 composites,
not a historical reconstruction of a chosen scene date. The optional bundled
night map is `maps/lights/Earthlights_2002.png`. Assets and credits remain
in place; no copies, downloads or live cloud layers are added by selecting them.

Generated xp.conf uses explicit relative asset names such as
`map=maps/world/world.200401.3x5400x2700.png`. The preview passes the current
checkout as one `-searchdir` argument, including when its path contains spaces.
The native xp.def records `XPLANET_ASSET_ROOT` as a reference to that checkout;
it is metadata, not a new engine option or an automatic desktop setting. If
rendering a saved pair independently, supply the checkout as Xplanet’s
`-searchdir` and translate the desired native definition settings to arguments.

Reopening recognizes those references but does not adopt a saved asset root or
executable. Preview uses the current checkout’s whitelisted bundled files, and a
new save records the current root. A scene moved to another checkout therefore
requires its bundled assets there; saved pairs do not embed images.

The engine can resize a night map to match the day map; that diagnostic is not
a failed render. Stock imagery still depends on renderer lookup. `shade=30` is
kept as the engine’s missing-night-map fallback, not exposed as a misleading
brightness slider: a found night texture is not modified by that setting.

## Configuration health and preflight

The scene summary shows the active observer/framing/time and the requested
textures. Selected bundled paths are shown and missing regular assets block
preview/save; image contents and exact renderer lookup are not certified. **Configuration health** separates **blocking** invalid settings/path
conflicts, **warnings** such as historical geometry with undated stock imagery,
and **information** about retained settings, Now snapshots and resource limits.
Warnings and information do not prevent Save or Preview. Blocking fields are
shown for correction. The same model and file preflight govern health, Preview and Save; the view is
not a second validator. Session-cached explicit binary support also informs health
and can block Preview for a known missing codec. Save deliberately does not enforce
that probe cache: a valid native draft can be saved for another build. Saving or
exporting alone does not certify that the reviewed binary can render it.

These are read-only configuration and executable-path checks. They do not launch
the selected binary or fetch data. Explicit cached diagnostics can report supported
codecs, qualified resource evidence and binary identity; preflight alone does not
certify output, exact asset resolution or imagery dates. A finite render and inspection provide additional
evidence. Renderer diagnostics are shown as a bounded, unclassified tail; a
warning-looking line is not automatically treated as a fatal error. Health also
shows the last render outcome separately from the last successful snapshot.

Output preparation and render errors explain the next useful check: temporary
permissions/free space, selected executable/architecture, PNG build support or
stock texture lookup. The retained image is labelled as prior successful output,
not the result of a failed attempt. No provider/data health or installed desktop
state is changed by these checks.

## Scene library and reopening

New scenes use a flat library under `config/scenes`, for example:

```text
summer.def                winter.def
summer.conf               winter.conf
summer.places.markers     winter.routes.arcs
summer.cloud-capture.jpg  summer.cloud-capture.json
```

Scene names use 1–48 ASCII letters/digits/underscores/hyphens. Optional assets
are prefixed with the exact scene name; they are not shared mutable files across
scenes. Keep associated files together. Renaming only the pair or copying a body
from another scene can break association and is refused, rather than importing
the wrong data. Use Save under a new name to duplicate a supported scene safely.

Choose **Scene library…** to browse candidate pairs in `config/scenes`, or use
**Open saved view…** / the command line for a specific file or legacy directory:

```sh
./scripts/xplanet.sh config --view /absolute/library/summer.conf
./scripts/xplanet.sh config --view /absolute/library/summer.def
./scripts/xplanet.sh config --view /absolute/legacy-scene-directory
```

Browsing reads a directory listing bounded to 1000 total entries and creates
nothing. Before publishing, Save checks room for the pair and all its associated
files; if they would exceed that limit, choose another library. Opening performs
full format/data validation; an arbitrary hand-edited `xp2.conf`/`xp3.conf` is not
accepted merely because a peer `.def` exists. Existing configurator directory
saves containing `xp.def`/`xp.conf` remain supported, including their optional
unprefixed assets. Opening establishes a new snapshot/baseline and resets history
only on success; sources and the local renderer selection are preserved.

Save defaults to a new `<source-name>-copy.conf` in the current library. You can
choose another new name or a legacy directory destination. Named publication
reserves a case-folded name, creates all files exclusively and publishes the
definition last; readers refuse an active/unfinished save marker. Failure removes
only unchanged files owned by that attempt; concurrently edited files and an
incomplete-save guard are retained for review. A crash marker is preserved for review; use
a different name rather than automatically discarding incomplete files.

The current reader recognizes explicit v17 through v2 and foundation scene
formats. Each must match its exact native layout and associated data; unsupported
edits, duplicates, unknown fields, file links and ambiguous/missing inputs fail
without replacing the draft. Loading never executes xp.def or adopts its saved
executable/asset root. Current checkout resources and locally chosen renderer
are used for subsequent previews. Saving is still not Apply and changes no jobs
or active desktop configuration.

## Current limits

There is no arbitrary config import/round-trip editing, in-place overwrite,
general per-body scene editor, provider configuration, persistent live references,
dashboard or automatic Apply. Explicit frozen capture supports existing clouds and observational marker/arc products
in Earth Now scenes; fixed UTC and other targets exclude that current-data-derived layer.
Non-Earth targets use selected bundled textures, including the supported moons and Pluto/Charon. External ephemerides,
configurable timewarp, trajectories and animation are unsupported. Scene time is not evidence of scientific precision. Existing custom
xp.def is never executed to populate the editor. See [module architecture](architecture.md)
for preservation rules and the engine relationships informing future work.


### Earth composition

Geographic views can choose fixed longitude or local solar hour (0 midnight,
12 noon). This selects longitude relative to the Sun, not a civil timezone.
Space views add geographic observer distance measured from the target center in
body radii, body/galactic/orbital north and counterclockwise rotation. Distance
is distinct from radius/FOV image framing, and is inactive for body-origin
observers. Composition was introduced in v7 and remains retained in current native
saves, review and history. Earlier
v2–v6 scenes reopen with composition defaults; v7 composition scenes still reopen. No trajectories or external
ephemerides are imported by these controls.


## Planetary targets

Choose the target first, then revisit any camera/time or appearance section.
Earth, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus and Neptune support
the existing projected maps and non-projected space views. Moon uses `maps/solarsystem/03-01-moon/moon-4k.png`; Mars uses
`maps/solarsystem/04-00-mars/Mars_2k-050104.png`. These are existing bundled
textures, not observations at the chosen scene time. No Mars cloud layer is
implied by another asset being present in the repository.

Space views can use geographic coordinates, any supported target as a body
origin, the Sun or the opposite-Sun construction. Health blocks an origin equal to the target; choose another origin or
geographic coordinates. Radius/FOV and orientation retain their existing roles.
Longitude follows Xplanet's convention: east-positive on Earth, Moon, Venus and Uranus;
west-positive on Mercury, Mars, Jupiter, Saturn and Neptune. Local solar hour avoids a fixed longitude convention.
The preview uses the installed renderer's internal geometry. No external kernel,
trajectory or scientific accuracy guarantee is added; resource presence does not
certify texture epoch, map orientation or ephemeris precision.

Earth maps, night lighting, relief/specular/cloud layers and geographic annotations
are hidden and inactive on other targets. Their values and any associated files remain
in the saved scene, Undo and change review. Returning to Earth restores them.
The grid and scene-time label remain available. Captured observational clouds are
active only for **Earth + Now**; fixed UTC or another target omits them, regardless
of the retained cloud choice. The generic UTC scene label is not a data-update label.

New v17 named or legacy-directory saves retain the target, planetary shadow
brightness and inactive Earth choices; v8 Moon/Mars scenes retain their defaults. Foundation/v2–v7 formats reopen as Earth; v8 retains its Moon/Mars targets. Arbitrary `xp2.conf` or
`xp3.conf` files still require a recognized matching generated definition and
associated files. No desktop Apply or lifecycle change is performed.


## Shipped stock scenes

The [stock scene guide](stock-scenes.md) lists the current 24 starting
points, including Mars, Jupiter, Saturn and Uranus viewed from their moons.
Shipped scenes start at 1920×1080. Ordinary body-origin cameras remain body-centre viewpoints. The separate
[orbital Earthrise-style camera](orbital-camera.md) adds a lunar limb,
crescent Earth and Sun; it is not a surface/terrain or historical reconstruction.

**Stock scenes…** opens read-only starting points shipped under
`scripts/configurator/samples/scenes`, separate from your `config/scenes` library:

- `earth-solar-dawn`: an orthographic Earth centered on local solar hour 6,
  with a geographic grid. Now samples the renderer clock at each preview.
- `earth-september`: the bundled September 2004 composite and 2002 night lights,
  showing how imagery choices are independent of scene time.
- `earth-from-moon`: Earth viewed from the Moon at 2000-01-01 12:00 UTC, with
  FOV framing. This is illustrative geometry, not a certified ephemeris product.

Open, revise, preview and save a named copy; the originals remain unchanged.
Saved executable/asset-root values are illustrative references, never
adopted or executed by Open. Your chosen installed renderer and current checkout
resolve previews. These presets need no TotalMarker configuration or capture.
Their native pairs are bundled with source exports; textures remain in the
existing asset collection. Planetary starting-point examples include: `moon-from-earth` illustrates lunar
phase, `jupiter-cloudtops` uses a solar-noon viewpoint and `saturn-rings` uses a
25-degree viewpoint to expose the rings. All use fixed 2000-01-01 12:00 UTC and
shadow brightness 15%; they are illustrative, not certified observations.


### Planetary imagery, shadows and time limits

The additional bundled day maps are Mercury's `01-00-mercury/mercury.jpg`, Venus's
`02-00-venus/venussurface__praesepe.jpg`, Jupiter's `05-00-jupiter/Jupiter.png`, Saturn's
`06-00-saturn/th_saturn.png`, Uranus's `07-00-uranus/UranusJVV.png` and Neptune's
`08-00-neptune/neptune2k.jpg`, all under `maps/solarsystem`. Asset presence is
checked; orientation, epoch and scientific precision are not certified. Venus
shows a surface texture, not the optically visible cloud deck. Giant-planet
atmospheric features are static texture details, not historical reconstructions.

Planetary **shadow brightness** uses native `shade`: 0–100 whole percent for the
unlit map, without introducing a planetary night texture. It is hidden on Earth,
whose existing night-map workflow remains separate; the retained value survives
switching targets. Newly supported major targets suppress incidental body-name
labels. The optional UTC scene label is independent of those labels.

Saturn's visible rings are built into Xplanet's non-projected space renderer,
not loaded from our ring image files. Radius framing includes the outer rings;
a nonzero observer latitude helps expose them. Projected Saturn omits the visible
ring system but can retain ring shadows on the map. No rings for other planets
or ring-texture editor is enabled. Other bodies/shadows may enter space views.
This target-selection mode does not configure individual companion bodies; see
[system composition](systems.md) for those controls.

The **1800–2200 studio input rule** remains for Earth and most targets.
Active Pluto/Charon target or space-origin geometry instead requires fixed UTC
in **1800–2099**; inactive origins and inactive fixed times are retained.
It is not a promise that every engine body, origin, satellite calculation or build
has equal accuracy throughout that interval. Xplanet 1.3.1's `EphemerisLow.cpp`
discusses its major-planet approximations over that interval; actual previews use
the selected renderer's backend. The studio does not select external ephemeris
files or certify event geometry. Satellite approximations and the Pluto input
guard are explained in [planetary bodies and limits](planetary.md).
Eclipse/event presets and kernel-dependent scenes need separate coverage validation. The stock scenes
and recorded real-render checks exercise a representative instant, not every date.


## Existing Earth observational products

Earthquake/volcano markers and paired storm markers/arcs can be explicitly frozen
from existing verified TotalMarker output, with supported styles, referenced PNG
icons and minimal provenance. They are Earth Now-only; no provider refresh or source
write occurs. See [frozen Earth observations](observations.md) for the
workflow, bounds, freshness semantics and safe save/reopen behavior.


## Inspect a custom native configuration

**Inspect native files…** reviews custom files without executing them, replacing
the draft or changing source. Unsupported content remains read-only; complete
recognized scenes can be copied byte-for-byte with their associated assets. See
[native inspection and preservation](import.md). This does not claim
general editable import or arbitrary config round-trip support.


Explicit named-scene selection is separate from saving and restart. See
[Apply and recovery](apply-design.md); custom configuration files stay intact.


## Make a bounded native literal copy

**Edit native values…** can review and patch literal shade, twilight, bump scale and bounded grid subdivisions
in a unique body section, preserving all other bytes. It saves only a new `.conf`
beside its source; it never executes definitions or previews unknown content.
See [native literal copies](native-values.md) for limits and context.


### Additional moons and relationship presets

The target/viewpoint selectors include the bundled Mars, Galilean and Saturnian
moons, Miranda, Pluto and Charon. Relationship stock scenes include Europa from
Jupiter, Mars from Phobos, Saturn from Titan and Pluto from Charon. These are
finite views, without magnification tricks or guaranteed simultaneous visibility
of the system. See [planetary bodies and limits](planetary.md).


## Compose a bundled planetary system

In **space mode**, Mars, Jupiter, Saturn, Uranus and Pluto offer **System textures**.
This configures the parent and its bundled moons while keeping your camera unchanged.
**Moon visual enlargement** is 1–10×: 1 keeps physical sizes; larger values enlarge
moon disks without moving their centers. It does not magnify the target planet.
Health and scene summaries identify enlargement; do not use enlarged overlaps as
eclipse predictions. Switch to a map or another target and the choices remain
stored but inactive. See [system composition](systems.md).

System stock scenes include `jupiter-inner-enlarged` and `saturn-inner-enlarged` (10× moons),
and `pluto-charon-system` (physical sizes). These are manually framed examples,
not a promise that every moon is visible. None changes desktop configuration.


### Illustrative orbital guides

System space views can draw bounded moon orbital guides with a shared color and
1–3 px width. V12 saves preserve these choices; fixed-time validation includes the
whole sampled interval. These are parent-relative illustrations, not inertial
trails or event predictions. See [orbital guides](orbits.md) for
sampling, date limits and three stock examples.


### Individual moon enlargement

In a system-space draft, **Individual moon scales…** can replace the shared scale
for selected moons. Blank inherits; 1× restores natural size. Use the result in
the draft as one undoable edit, or cancel without changing it. V13 saves retain
other-family overrides as inactive choices. See [individual moon scales](systems.md#individual-moon-scales).


### Review a setup handoff

**Handoff review…** reviews a saved named scene, explicit local renderer and
desktop geometry, then requires confirmation to export a new private bundle.
It checks saved files, not unsaved editor changes; the draft stays intact.
**Review Apply** and **Confirm selection** separately select an immutable revision
for the next explicit start/restart. Reviewed restoration changes only the
reference. Export/check/selection are also available from the CLI. `setup --check-handoff` verifies the
bundle without sourcing custom definitions or changing jobs. This is review and
staging only until explicit selection; no operation here starts/restarts the desktop.
See [Apply, recovery and limits](apply-design.md).


## Browse stock and saved scenes

**Stock scenes…** and **Scene library…** share a name filter, visible pair count
and a summary of the selected scene, its preview dimensions and native-file count.
Only the selected pair is inspected; browsing does not read every captured image
in a library. Opening revalidates that pair and keeps the local renderer choice.
An unsupported or incomplete pair stays unavailable with a reason; use the
separate native inspection tool rather than treating it as a generated scene.
The filter changes no files, and this browser does not rename, delete or activate
scenes. Opening a valid pair still replaces the current draft as explicitly warned.


## Framing sets and private drafts

[Framing comparison sheets](comparisons.md) provide three reviewed
1920×1080 static space-view variants at a single epoch, without changing the draft
or ordinary previews. The explicitly opened contact sheet is local HTML, not an
inline image renderer or an animation. Current-data captures remain outside this
framing comparison mode.

[Private draft recovery](recovery.md) adds debounced, bounded checkpoints
and explicit inspection/recovery, with separate namespaces for concurrent editors.
It is editing continuity, not another runtime configuration or Apply mechanism.

## Frozen astronomy

[Existing NORAD and eclipse captures](astronomy-capture.md) are separate
from weather observations. NORAD is Earth/Now preview-only; eclipse display uses
Fixed UTC within validated event sample coverage. Captures, choices and provenance
survive save/reopen and recovery, including when inactive. No source refresh occurs.
Active NORAD cannot be handed off to the desktop; static eclipse handoff remains
reviewed and explicit.

Installed sky/planetary annotation imports have a separate bounded workflow.
See [installed annotations](installed-annotations.md) for coordinate domains,
source receipts, owned files, and selection/exchange behavior.
