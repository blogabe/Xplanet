# Configurator reference

The [user guide](user-guide.md) explains how to open, edit, preview and save a
scene. Use **Help / F1** in the editor or run
`./scripts/xplanet.sh config --guide` to read it without opening the studio.
This reference covers the controls and the named-scene library.

## Prerequisites

See [open the studio](user-guide.md#1-open-the-studio) for the complete checkout,
renderer, Python and isolated UI runtime requirements.

## Explore, preview, save or cancel

See the [preview](user-guide.md#4-preview-and-compare),
[save](user-guide.md#5-save-a-new-scene-and-continue-later) and
[exit](recovery.md#keys-and-exit-choices) workflows for actions and shortcuts.
These are scene controls, not installation or desktop controls.

| Control | Meaning |
| --- | --- |
| Preview geometry | Choose a bounded output frame. Blank drafts use the primary display when available; [diagnostics](diagnostics.md) covers limits and fallback. |
| Rectangular / orthographic map | Project a single target from geographic coordinates. Orthographic is still a projection. |
| Space (no projection) | Use geographic coordinates or a body origin. The observer cannot be the target body. |
| Geographic observer | Latitude ±90° and longitude ±180° above the target. |
| Body / Sun / opposite Sun | View from another supported body's centre, or from a solar direction. Sun/opposite Sun are day-side/night-side constructions, not civil-time settings. |
| Radius / field of view | Frame by target radius (0.1–100% of image height) or angular field of view (0.1–179°). The renderer receives only one. |
| Day map / month | Choose stock Earth or a bundled 2004 Earth, topography or topography/bathymetry composite. Map month is independent of scene time. |
| Night texture / twilight | Choose stock night imagery or bundled Earthlights 2002. Twilight is the day/night blend width, 0–90 whole degrees, not night brightness. |
| Relief / shadows | Use bundled GEBCO relief, with exaggeration 0.1–5. Shadows use night imagery by default; shaded-day shadows use an independent 0–100 whole percent. |
| Specular | Use the bundled ocean-reflection mask. Visible reflection depends on illumination and viewing geometry. |
| Clouds / gamma / threshold | Choose the archived 26 August 2011 texture or [explicitly capture an existing TotalMarker image](cloud-capture.md) for Earth + Now. Gamma 0.1–5 changes brightness; whole threshold 0–255 hides dimmer pixels. |
| Grid | Off, or 30°, 15° or 10° major spacing with 1° dots. |
| Label | Off, or the renderer's UTC scene-information label, which requires suitable font/build support. It does not show provider freshness. |
| Now / fixed UTC | Use the renderer clock for each preview, or enter a strict `YYYY-MM-DDTHH:MM:SSZ` instant. See [date limits and ephemerides](planetary.md#time-and-ephemerides). |

Controls that do not apply to the current mode keep their values in drafts and
saved scenes. An invalid retained value is exposed for correction. A fixed UTC
date changes lighting and geometry; it does not refresh data, change label
timezone or make stock imagery historical. The initial retained fixed value is
`2000-01-01T12:00:00Z`; Now is the default. An opposite-Sun preview can include
the Sun or glare behind Earth.

### Earth composition

Geographic views can choose fixed longitude or local solar hour (0 is midnight,
12 is noon). Solar hour sets longitude relative to the Sun, not a civil timezone.
In space, a geographic observer can set distance in body radii from the target's
centre. This distance is separate from radius or FOV image framing and is inactive
for body origins. Space views also offer body, galactic or orbital north and
counterclockwise rotation. For an offset Moon observer and percentage
frame-centre controls, see the [lunar orbital camera](orbital-camera.md).

## Local Earth layers

The relief, specular and archived cloud choices read only bundled files:

| Layer | File |
| --- | --- |
| Relief | `maps/bump/gebco_08_rev_elev_21600x10800.png` |
| Specular | `maps/specular/specular.png` |
| Archived clouds | `maps/clouds/clouds_26Aug2011_2048.jpeg` |

Large relief and specular textures can increase decoding time and memory.
Xplanet can resize textures to match the day map. The studio does not reduce
the images or install image-processing software. These selections do not run
TotalMarker or alter a schedule. See the
[cloud capture guide](cloud-capture.md) for the separate frozen-provider workflow.

## Places, labels and routes

Enable **Places and labels** or **Static great-circle route arcs** to expose
the related editor and style fields. Each native list allows up to 32 rows,
8 KiB total and 200 UTF-8 bytes per line. Coordinates use east-positive
longitude (±180°) and latitude within ±90°.

Places use `latitude longitude "Label"`:

```text
51.5 -0.1 "London"
40.7 -74 "New York"
```

Labels are printable text up to 80 UTF-8 bytes, without quotes or backslashes.
Color and whole-pixel font size (10–24) apply to the list. The renderer chooses
label placement; overlap, visibility and font support still matter. The editor
does not geocode or accept icons, pixel/sky coordinates or per-marker options.

Routes use `latitude1 longitude1 latitude2 longitude2`:

```text
51.5 -0.1 40.7 -74
```

Use further rows with shared endpoints for a segmented route. Color and whole-pixel
thickness (1–5) apply to the list. Identical endpoints have no visible length;
antipodal endpoints do not define a unique path. These are surface arcs, not
travel routes, trajectories or calculated eclipse paths.

Neither editor accepts comments, native options, file references or command hooks.
Blank lines, entered numeric precision and row order are retained. Off hides the
controls and omits the layer from rendering without losing its settings. Invalid
retained text must be corrected before Save or Preview. New scenes keep a native
list when it is enabled or contains retained text. Missing or altered associated
files can prevent reopening; save or copy the complete scene. These files do not
change any TotalMarker output.

## Change review and undo

**Review changes** compares active and retained settings with the scene opened
in this session (or the starting sample). The Save confirmation uses that same
comparison. Review does not reread the source files. Equivalent finite numeric
spellings, such as `0` and `0.000`, do not mark the scene dirty, but can be undone;
invalid text counts as an edit. The renderer is compared against the local
choice when the scene was opened, not against an executable recorded in the
imported data. The save destination is not part of scene history.

**Undo / Redo** (Ctrl-Z / Ctrl-Y) keeps up to 100 undo steps in memory. Typing
groups until focus leaves the field, selection changes count individually, and
a new edit after Undo discards Redo. Review and confirmation dialogs block undo
beneath the dialog. Only successful Open replaces the baseline and clears the
history; Save & continue advances the baseline but retains undo. Undo restores
draft values and recomputes preview staleness; it does not remove saved files or
undo a renderer or desktop action. [Recovery](recovery.md) keeps the draft and
baseline, not the undo stack.

## Bundled assets and native references

The selector covers 36 monthly PNGs in `maps/world`, `maps/world.topo` and
`maps/world.topo.bathy`; the bundled night map is `maps/lights/Earthlights_2002.png`.
Generated body settings use relative paths such as
`map=maps/world/world.200401.3x5400x2700.png`. Preview supplies the checkout as
one `-searchdir` argument. The saved `XPLANET_ASSET_ROOT` records a reference,
not an engine setting. If rendering a saved pair independently, supply the
checkout as Xplanet's search directory and translate the desired native
definition settings to arguments.

Opening a scene does not adopt its recorded executable or asset root. It uses
the current checkout and the local renderer. Saved scenes reference the bundled
maps rather than embedding them; a moved scene needs those assets in the new
checkout. The engine can resize a night map to match the day map. Native
`shade=30` is the fallback for a missing night map, not a brightness slider
for a found night texture.

## Configuration health and preflight

See [resource diagnostics](diagnostics.md) for the interpretation of missing
resources, known build limitations, unknowns and renderer evidence. Preflight
does not fetch data or launch the renderer. Blocking fields prevent Preview and
Save; warnings and information do not. A known missing codec can block Preview
on that binary without blocking a valid native Save for another build.

## Scene library and reopening

New scenes use the flat `config/scenes` library:

```text
summer.def                winter.def
summer.conf               winter.conf
summer.places.markers     winter.routes.arcs
summer.cloud-capture.jpg  summer.cloud-capture.json
```

Scene names accept 1–48 ASCII letters, digits, underscores or hyphens. Keep the
pair and its scene-prefixed associated files together. To copy a scene, use
Save under a new name rather than renaming files independently.

**Scene library…** browses the library, or you can open a specific generated
pair or supported legacy directory:

```sh
./scripts/xplanet.sh config --view /absolute/library/summer.conf
./scripts/xplanet.sh config --view /absolute/library/summer.def
./scripts/xplanet.sh config --view /absolute/legacy-scene-directory
```

Browsing creates nothing, checks at most 1,000 directory entries and inspects
only the selected pair. Save can require another library if the new files would
exceed that bound. Open validates the exact generated format and never executes
a definition. The reader supports v17 through v2 and the original foundation
format, including legacy directory saves with unprefixed associated files.
A hand-edited pair may be ineligible; use [native inspection](import.md) to
examine it without replacing the draft.

The default Save destination is another new copy, such as
`<source-name>-copy.conf`. The editor won't overwrite files or publish to a
case alias. If an earlier save left an incomplete marker, use a new name and
inspect the guarded files rather than automatically deleting them. The
[architecture](architecture.md#scene-storage-and-publication) explains the
publication and recovery checks. Saving does not change the desktop selection.

<a name="current-limits"></a>
<a name="planetary-targets"></a>
<a name="planetary-imagery-shadows-and-time-limits"></a>
<a name="additional-moons-and-relationship-presets"></a>
<a name="shipped-stock-scenes"></a>
<a name="browse-stock-and-saved-scenes"></a>
<a name="existing-earth-observational-products"></a>
<a name="inspect-a-custom-native-configuration"></a>
<a name="make-a-bounded-native-literal-copy"></a>
<a name="compose-a-bundled-planetary-system"></a>
<a name="illustrative-orbital-guides"></a>
<a name="individual-moon-enlargement"></a>
<a name="review-a-setup-handoff"></a>
<a name="framing-sets-and-private-drafts"></a>
<a name="frozen-astronomy"></a>

## Topic guides

| For | Read |
| --- | --- |
| Supported bodies, date limits and textures | [Planetary bodies and limits](planetary.md) |
| Shipped starting points and filters | [Stock scenes](stock-scenes.md) |
| Companion textures, shared and individual moon scales | [System composition](systems.md) |
| Parent-relative moon paths | [Orbital guides](orbits.md) |
| Earth cloud and weather snapshots | [Frozen clouds](cloud-capture.md), [observations](observations.md) |
| Satellite, eclipse and installed sky/body layers | [Frozen astronomy](astronomy-capture.md), [installed annotations](installed-annotations.md) |
| Examine or preserve native files | [Native inspection](import.md), [literal copies](native-values.md) |
| Select a reviewed scene for the next start | [Apply and guarded recovery](apply-design.md) |
| Before/after or three-variant framing | [Comparison sets](comparisons.md), [user guide](user-guide.md#4-preview-and-compare) |
| Recover an editing session | [Draft recovery](recovery.md) |
| Keep an image or share a saved scene | [Image export](export.md), [scene exchange](exchange.md) |
