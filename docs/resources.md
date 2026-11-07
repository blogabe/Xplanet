# Resources and prerequisites

An Xplanet feature needs three separate things: a renderer that supports it,
usable data and a scene that selects that data. An installed folder, a successful
`-version` report or a completed render alone does not establish all three.

## Where resources belong

| Resource source | Examples | Ownership and use |
| --- | --- | --- |
| Installed Xplanet package | Stock `images/earth.jpg` and `night.jpg`, font, star catalogue, marker/arc data and example configurations | Package-managed data, normally below its `share/xplanet` directory. Inspect it, but put custom changes in your own configuration/resources rather than editing the package. Reinstallation can replace package files. |
| Tracked project assets | Seasonal Earth maps, night/bump/specular textures, planetary and Celestia textures under `maps/` | Shipped with this checkout. Inclusion does not imply a studio control, scientific validation or common redistribution license. |
| Generated project inputs | Cloud images in `images/`, marker files in `markers/`, storm tracks in `arcs/`, NORAD files in `satellites/` | Produced only by configured, successful refreshes. A failed refresh can leave older last-good data. See [freshness and provenance](technical-notes.md). |
| Personal scene/configuration inputs | Ignored `config/xp.conf`, `config/xp.def`, `config/scenes/`, local resources and explicit frozen captures | User-owned. Setup preserves existing personal files. A saved capture is a snapshot, not a live provider connection. |

The renderer executable is separate from all these data files. This repository's
scripts manage scenes and data; the [Homebrew tap](https://github.com/blogabe/homebrew-xplanet)
builds Xplanet. Updating this checkout does not turn a missing external kernel or
font into an installed resource. Do not copy the package's whole data tree into
the project just to satisfy one missing file.

### What the installed package actually contains

The Xplanet 1.3.1 package inspected for this guide includes these resource families:

| Directory | Included example/data | Important limit |
| --- | --- | --- |
| `images/` | Stock Earth day/night maps, Sun image and several spacecraft/marker icons | Not a full planetary texture collection. Decoding needs the relevant image-format support. |
| `fonts/` | `FreeMonoBold.ttf` and its README | A font file does not establish FreeType/Pango support or coverage for every glyph. |
| `stars/` | `BSC` star catalogue | The native `-starmap` option selects a catalogue. Star catalogues are not geographic marker files. |
| `markers/`, `arcs/`, `config/` | Earth/Moon/Mars and bright-star markers, constellation arcs, native examples | Match the resource to its coordinate system and use. Sky overlays and per-body geographic overlays are different roles. These are not current TotalMarker products. |
| `satellites/` | `iss` display specification and historical `iss.tle` sample | Example TLEs are not current orbital data. A display file also needs its associated TLE file and matching catalogue IDs. |
| `origin/` | Galileo and Cassini observer-path examples | Dated examples, not current spacecraft locations or complete SPICE kernels. |
| `spice/` | Object lists, `.krn` kernel-name lists and README | The reviewed package has example lists, not the referenced mission kernels. A `.krn` list alone cannot supply an ephemeris. |
| `ephemeris/` | README for external JPL files | No JPL binary ephemeris is included in the reviewed package. |
| `scattering/` | `earthRayleigh` recipe and README | The recipe is not a generated lookup-table set. Tables must exist for a scene using them. |

This is an inventory of the reviewed package, not a promise about every Xplanet
build or package revision. With a Homebrew installation, inspect that package's
current data without changing it:

```sh
package_root="$(brew --prefix xplanet)"
find "$package_root/share/xplanet" -type f -print
```

This locates the Homebrew package, not necessarily the executable selected for a
scene. Do not infer the selected binary's compiled data directory from its filename,
parent directory or a symlink. Inspect its own manual and explicit lookup evidence.
Installed resource READMEs describe formats; old sample URLs and dates are not
assurances that a provider is available or the example remains current.

### Project maps and the studio's supported subset

The numbered folders and `celestia-textures` collection under `maps/solarsystem/`
are both tracked assets. `body-maps.txt` indexes the retained files; it is not a
list of studio targets or a configuration to run unchanged. Triton, Ariel, Umbriel,
Titania and Oberon have JPEG maps in both the `lores/` and `medres/` Celestia folders.
They are not currently connected to the studio's body choices or system composition.
Nereid has no tracked texture. See [current targets](configurator/planetary.md) and
[system composition](configurator/systems.md).

A similarly named map is not automatically chosen for an incidental body. For
example, the renderer can report a missing `ariel.jpg` in a Uranus view even though
`maps/solarsystem/celestia-textures/medres/ariel.jpg` exists: that nested texture
was never selected for Ariel. A fallback-colored body or a successful output file
does not prove that every visible body used a texture.

The dated 2011 cloud samples under `maps/clouds/` are static illustrations, not
fresh weather. The project keeps optional textures even when no stock scene uses
them. Review [asset credits and third-party terms](asset-credits.md) before copying
or redistributing any of them; the project's MIT license does not relicense maps
or installed upstream resources.

## How native file lookup works

The reviewed Xplanet 1.3.1 manual describes this search order for relative resources:

1. The current working directory.
2. The directory passed with `-searchdir`, then its resource-type subdirectory.
3. The resource-type subdirectory of `./xplanet`, if present.
4. The per-user resource directory: `~/.xplanet` on X11 or
   `~/Library/Xplanet` on native Mac OS X, with the appropriate type subdirectory.
5. The resource-type subdirectory of the compiled `DATADIR/xplanet` location.

The relevant subdirectory depends on the request, such as `images`, `fonts`,
`markers`, `arcs`, `stars`, `origin`, `satellites` or `ephemeris`; SPICE and
scattering have their own resource directories. This is not a recursive scan of
every map folder. The build's platform support and compiled data location matter.
Repeated search directories and unusual builds should be checked from actual
lookup evidence rather than guessed from this overview.

The project's native launcher explicitly supplies its project root as a search
directory and its `config/xp.conf` as the configuration. Thus `map=earth.jpg` can
fall through to the installed stock image, while a selected monthly map uses
`images/earth.png`, linked to a tracked `maps/` file. A local file of the same name
can take precedence over package data. Setup also prepares `images/solarsystem`
for existing native image references. Finite launcher preview/render commands use the selected checkout as their working
directory, so the caller's directory cannot shadow its resources. The studio names its selected
project maps explicitly and renders in a private workspace/HOME with its own
configuration and frozen inputs. A successful interactive command from another
working directory is not proof of the studio's or desktop's lookup context.

Use **Diagnose resources** in the studio for a finite verbose render of the
chosen scene. It reports recognized found paths and unsuccessful search attempts.
A miss followed by a later found path is ordinary search behavior. Finding a file
is not proof that it decoded correctly or covered the requested date. The report
is bounded and attempt-specific, not a recursive inventory or live asset watcher.
See [diagnostic evidence and limits](configurator/diagnostics.md).

## Optional-feature prerequisites

| Feature | Required data/configuration beyond a capable renderer | Current project boundary |
| --- | --- | --- |
| Texture maps and output images | Readable selected maps, matching image codecs, suitable layer dimensions and valid native paths | Stock and selected bundled maps are supported. PNG output support is needed for studio previews; other formats depend on selected textures. |
| Text labels and fonts | A usable font file, or a resolvable family when using Pango, with the required glyphs | Existing labels use renderer font behavior. Package font presence is not a font-picker or glyph-validation feature. |
| Star maps and sky overlays | Star catalogue with declination/right-ascension/magnitude rows, or native sky marker/arc data selected by the relevant options | Normal stars retain the renderer's catalogue behavior. The studio supports explicit frozen imports of [bright-star labels and constellation lines](configurator/installed-annotations.md), plus body-specific Moon/Mars annotations. No general resource picker is provided; sky coordinates are not Earth latitude/longitude markers. |
| NORAD satellites/icons | Configured display file plus matching, sufficiently current TLE data; any referenced icon must also resolve | [Explicit icon import](installed-satellite-icons.md) copies selected installed PNGs with source receipts; it does not configure NORAD. [Existing NORAD capture](configurator/astronomy-capture.md) is Earth/Now preview-only. Installing a sample icon or TLE does not enable provider refreshes or desktop handoff. |
| JPL planetary ephemerides | A compatible binary ephemeris with coverage for the bodies and times requested | The 1.3.1 manual documents DE200/DE405/DE406 via `-ephemeris_file`; do not assume every newer DE file works. The studio does not select external JPL files. |
| SPICE objects/ephemerides | Compiled SPICE support, object list, associated `.krn` list, actual compatible kernels and sufficient object/time coverage | Example lists are not kernels. Kernel order and reference bodies matter; the studio does not manage or certify external kernels. |
| Rayleigh scattering | Appropriate scattering configuration and generated lookup tables, selected by native configuration | Installed `earthRayleigh` is a table-generation input. This guide neither generates tables nor enables a studio scattering control. |
| Observer trajectories | A valid native origin file with correct reference body, units and time behavior | The studio's bounded [orbital camera](configurator/orbital-camera.md) is separate from arbitrary trajectory import. Historical mission examples are not current tracking. |

External JPL and SPICE data are optional for ordinary scenes: Xplanet has built-in
position calculations. Neither those built-in calculations nor a high-resolution
texture certify scientific accuracy. See [planetary time and ephemeris limits](configurator/planetary.md#time-and-ephemerides).

## Diagnose in the right order

1. Confirm which executable and which scene are being inspected. Saved evidence
   for another binary or a prior render can be stale.
2. Check compiled support explicitly with `./scripts/xplanet.sh diagnostics`, or
   with **Diagnose resources** in the studio. The terminal command probes support,
   not scene-resource availability. `diagnostics --show` only reads saved evidence.
3. Confirm the selected files exist in the relevant lookup context. Use the scene's
   verbose diagnostic to see what was found; keep configuration/path errors
   separate from missing compiled support.
4. Check format, image decoding, font/glyph availability, data freshness and body/date
   coverage as applicable. Exit zero alone is not proof of these properties.
5. Preview the intended scene. Saving it, selecting it for next start and restarting
   remain separate actions. Do not change installed files or personal configuration
   as a side effect of inspection.

A failed or unfamiliar support probe means **unknown**, not unsupported. A missing
file does not mean the renderer lacks that feature. An available file does not mean
the studio supports editing that feature, and an installed example does not mean a
live source is configured. Optional-feature development must establish these pieces
explicitly rather than treating all of them as one availability flag.
