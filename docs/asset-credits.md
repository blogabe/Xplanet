# Asset credits and third-party terms

The [MIT license](../LICENSE) applies to this project's original code and
documentation, including the current Python implementation. It does not relicense
third-party code, imagery, datasets or provider fixtures. Those retain their own
copyrights and applicable terms. Source attribution below is not itself a license
grant, and no single license is asserted for the complete asset collection.

Hari Nair's [Xplanet renderer](https://xplanet.sourceforge.net/) is separately
installed through Homebrew and distributed upstream under GPLv2. Michael Dear
wrote the original Perl TotalMarker that inspired this implementation.
Neither upstream work is relicensed by this project's MIT license.

## Bundled runtime assets

All finished textures remain bundled, including the planetary collection. Source
records from the retired project guide, preserved archive READMEs and the primary
references below provide attribution and terms. The retired guide URLs are recorded
at the end of this page for provenance, not as current instructions.

| Files / family | Source and credit | Terms / mapping limits |
| --- | --- | --- |
| `maps/world/`, `world.topo/`, `world.topo.bathy/` (36 monthly maps) | NASA [Blue Marble: Next Generation](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/), produced by Reto Stöckli, NASA Earth Observatory. Credit: **NASA Earth Observatory**. | NASA explicitly requests this credit for use/republication. Apply its [media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/), including third-party exceptions; this is not MIT imagery. Local files have not been matched byte-for-byte against current upstream downloads. |
| Finished files in `maps/lights/` | The guide identifies NASA's [legacy city lights](https://svs.gsfc.nasa.gov/30003/) and [2012 Earth at Night](https://science.nasa.gov/earth/earth-observatory/night-lights-2012-map-79765/). Underlying DMSP/OLS and VIIRS observations differ by image. | Preserve the source-page credits and NASA conditions. The guide's preferred 1994–95 lights must not be confused with newer alternatives. Exact source/processing mapping for every retained variant remains incomplete. |
| `maps/bump/gebco_08_rev_elev_21600x10800.png`, `maps/bathymetry/gebco_bathy.21601x10801.jpg` | Filenames identify GEBCO-derived elevation/bathymetry; the guide describes the bump layer. | [GEBCO terms](https://www.gebco.net/data-products/gridded-bathymetry/terms-of-use) allow copying/adaptation with acknowledgement and disclaimers. The local images' original conversion/producer and applicable historical attribution still need exact mapping; do not infer rights from the filename alone. |
| `maps/specular/specular.png` | Assembled for the guide from Jestr's Celestia Motherlode tiles using ImageMagick. All 512 renamed source tiles match level 4 of the preserved `JestrEarthSpecular PNG.zip`. Its README identifies NASA landcover inputs and Jestr's manual edits. | Credit **Jestr**, the NASA landcover source, and the guide's assembly. [Motherlode's legal page](https://celestiamotherlode.net/legal.html) retains creator copyrights and describes qualified noncommercial distribution; the README is attribution, not a separate blanket license grant. |
| `maps/clouds/clouds_26Aug2011_*.jpeg` (three static sizes) | The guide distinguishes [NASA Blue Marble static clouds](https://science.nasa.gov/earth/earth-observatory/collections/blue-marble/) from live subscription imagery. | Exact download/producer mapping of these three 2011 JPEGs remains unconfirmed. Do not classify them as MIT or assume that subscription terms apply to them. |
| `maps/solarsystem/` (204 files, including `celestia-textures/`) | Preserved optional planetary texture collection, including a Celestia-named stock-texture subset in `celestia-textures/`, distinct from community Motherlode additions. Its exact source release and per-file terms are not established by the directory name. Xplanet's [map-source directory](https://xplanet.sourceforge.net/maps.php.html) and [Celestia Motherlode](https://celestiamotherlode.net/) are source references, not per-file licenses. | Individual creator/version mapping is incomplete. Filename initials are not sufficient attribution or license evidence; no blanket NASA, GPL or MIT license is asserted for these textures. |
| `maps/xplanet projections.jpg` | Preserved projection reference image. | Original image credit/terms are not yet mapped. |
| `scripts/totalmarker/data/gdacs_volcano_coordinates_20261019.json` | GDACS coordinate-only responses, transformed as documented in the adjacent [data README](../scripts/totalmarker/data/README.md). | Retain [GDACS terms/disclaimer](https://www.gdacs.org/About/termofuse.aspx); public access alone is not an MIT grant. Provider fixtures likewise retain their respective source terms. |

The stock `earth.jpg` / `night.jpg` resolve from the separately installed Xplanet
data directory. `config/earth.example` retains its upstream Getty/TGN source
comments; those data are not relicensed here. Live [Xeric cloud imagery](https://www.xericdesign.com/xplanet.php)
is acquired by each configured subscriber, not bundled from a user's download;
subscription access does not grant this project blanket redistribution rights.

The raw GEBCO JPEG is now at `maps/bathymetry/gebco_bathy.21601x10801.jpg`
(previously `assets/maps/other/gebco_bathy.21601x10801.jpg`). Update any custom
references to the old path explicitly. Setup does not link this JPEG or rewrite
custom links; its separate monthly and bump-map links are unchanged.

## Preserved working sources

Source tiles, the stitching script, a duplicate composite and five source ZIPs
are local development material, outside the current public tree. Their archive
READMEs preserve these additional source details:

- `JestrEarthSpecular PNG.zip`: Jestr; NASA `landcover.E` / `landcover.W` inputs and hand edits.
- `EarthSpec.zip`: JohnVV collection; its README tentatively identifies a 2004 Blue Marble source.
- `earthspec32kVT.zip`: Buzz, July 2004; thanks to Fridger for VT scripts.
- `2k4k8k.EarthNight.zip`: John K. Van Vliet's colour/cleanup work; NOAA NGDC / US Air Force DMSP `F162009.v4b.avg_lights_x_pct` inputs.
- `earth-nightlights-hs.zip`: `2000_human_settlements_version1.tar` input and documented rescaling/colour processing; author not identified in that README.

These are credits/source records, not a common redistribution license. The local
preservation manifest records original paths, hashes and Git modes for restoration.
Removing them from the current tree does not remove old Git history or necessarily
reduce a full clone's size.

## Retired guide references

The original project guide is retired. These source-record URLs are retained as
plain-text provenance references, not current navigation links or license grants:

- Map-source guide: `https://blog.rajab.us/xplanet/maps/`
- Original Perl marker workflow: `https://blog.rajab.us/xplanet/markerfiles/`

Use the current primary-source links and terms above for the bundled assets.

## Solar-system folder names

`maps/solarsystem/` uses `SS-BB-name`: a two-digit system number and a
local body-order number. `00-00-sun` is the Sun; `03-01-moon` belongs to
Earth's system; primary bodies use `00`. Pluto remains system `09` in this
collection; that folder number does not classify it as a planet. `celestia-textures`
and `body-maps.txt` retain their names. These are collection names, not NAIF IDs.

Among the retained moons, the order follows increasing mean orbital distance
within each system, checked against [JPL's satellite mean elements](https://ssd.jpl.nasa.gov/sats/elem/sep.html).
It is not a complete list of satellites, a display order requirement or an
ephemeris. Directory names do not certify image provenance. Empty numbered-folder
placeholders are not packaged. Separately, the retained `celestia-textures/lores/`
and `medres/` collections contain Ariel, Umbriel, Titania, Oberon and Triton maps;
these are not currently offered as configurator targets. Nereid has no tracked
texture. See [resources and prerequisites](resources.md) for the distinction
between an included file and a configured feature. No new imagery or scientific
certification is implied.

## Explicit installed-resource imports

The [satellite icon importer](installed-satellite-icons.md) copies only explicitly
chosen ISS, Hubble and Shuttle PNGs from a physical installed resource directory.
It preserves their original bytes and `images/README`, with SHA-256 source receipts.
That README may identify upstream contributors and license terms; local package
files can differ, so hashes establish consistency rather than upstream authenticity.
The [installed annotation importer](configurator/installed-annotations.md) instead
preserves source hashes and attribution comments alongside canonical bounded text
rows. Neither workflow edits the installed package or vendors its files here.

Imported files keep their upstream/contributor terms. A local import, saved scene
or exported archive is not a new license grant or permission to redistribute them.
Review the retained attribution, comments and applicable terms before sharing.
