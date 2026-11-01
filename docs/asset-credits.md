# Asset credits and third-party terms

The [MIT license](../LICENSE) applies to this project's original code and
documentation, including the current Python implementation. It does not relicense
third-party code, imagery, datasets or provider fixtures. Those retain their own
copyrights and applicable terms. Source attribution below is not itself a license
grant, and no single license is asserted for the complete asset collection.

Hari Nair's [Xplanet renderer](https://xplanet.sourceforge.net/) is separately
installed through Homebrew and distributed upstream under GPLv2. Michael Dear
wrote the original Perl TotalMarker that inspired this implementation; see the
[original marker-file guide](https://blog.rajab.us/xplanet/markerfiles/).
Neither upstream work is relicensed by this project's MIT license.

## Bundled runtime assets

All finished textures remain bundled, including the planetary collection. The
[original map guide](https://blog.rajab.us/xplanet/maps/) is the starting source
record; its references and preserved archive READMEs support the entries below.
Historical links are retained as provenance even when a site is unavailable.

| Files / family | Source and credit | Terms / mapping limits |
| --- | --- | --- |
| `assets/maps/world/`, `world.topo/`, `world.topo.bathy/` (36 monthly maps) | NASA [Blue Marble: Next Generation](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/), produced by Reto Stöckli, NASA Earth Observatory. Credit: **NASA Earth Observatory**. | NASA explicitly requests this credit for use/republication. Apply its [media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/), including third-party exceptions; this is not MIT imagery. Local files have not been matched byte-for-byte against current upstream downloads. |
| Finished files in `assets/maps/lights/` | The guide identifies NASA's [legacy city lights](https://svs.gsfc.nasa.gov/30003/) and [2012 Earth at Night](https://science.nasa.gov/earth/earth-observatory/night-lights-2012-map-79765/). Underlying DMSP/OLS and VIIRS observations differ by image. | Preserve the source-page credits and NASA conditions. The guide's preferred 1994–95 lights must not be confused with newer alternatives. Exact source/processing mapping for every retained variant remains incomplete. |
| `assets/maps/bump/gebco_08_rev_elev_21600x10800.png`, `assets/maps/other/gebco_bathy.21601x10801.jpg` | Filenames identify GEBCO-derived elevation/bathymetry; the guide describes the bump layer. | [GEBCO terms](https://www.gebco.net/data-products/gridded-bathymetry/terms-of-use) allow copying/adaptation with acknowledgement and disclaimers. The local images' original conversion/producer and applicable historical attribution still need exact mapping; do not infer rights from the filename alone. |
| `assets/maps/specular/specular.png` | Assembled for the guide from Jestr's Celestia Motherlode tiles using ImageMagick. All 512 renamed source tiles match level 4 of the preserved `JestrEarthSpecular PNG.zip`. Its README identifies NASA landcover inputs and Jestr's manual edits. | Credit **Jestr**, the NASA landcover source, and the guide's assembly. [Motherlode's legal page](https://celestiamotherlode.net/legal.html) retains creator copyrights and describes qualified noncommercial distribution; the README is attribution, not a separate blanket license grant. |
| `assets/maps/clouds/clouds_26Aug2011_*.jpeg` (three static sizes) | The guide distinguishes [NASA Blue Marble static clouds](https://science.nasa.gov/earth/earth-observatory/collections/blue-marble/) from live subscription imagery. | Exact download/producer mapping of these three 2011 JPEGs remains unconfirmed. Do not classify them as MIT or assume that subscription terms apply to them. |
| `assets/maps/solarsystem/` (204 files, including `celestia-textures/`) | Preserved optional planetary texture collection. Xplanet's [map-source directory](https://xplanet.sourceforge.net/maps.php.html) and [Celestia Motherlode](https://celestiamotherlode.net/) are source references, not per-file licenses. | Individual creator/version mapping is incomplete. Filename initials are not sufficient attribution or license evidence; no blanket NASA, GPL or MIT license is asserted for these textures. |
| `assets/maps/xplanet projections.jpg` | Preserved projection reference image. | Original image credit/terms are not yet mapped. |
| `scripts/totalmarker/data/gdacs_volcano_coordinates_20261019.json` | GDACS coordinate-only responses, transformed as documented in the adjacent [data README](../scripts/totalmarker/data/README.md). | Retain [GDACS terms/disclaimer](https://www.gdacs.org/About/termofuse.aspx); public access alone is not an MIT grant. Provider fixtures likewise retain their respective source terms. |

The stock `earth.jpg` / `night.jpg` resolve from the separately installed Xplanet
data directory. `config/earth.example` retains its upstream Getty/TGN source
comments; those data are not relicensed here. Live [Xeric cloud imagery](https://www.xericdesign.com/xplanet.php)
is acquired by each configured subscriber, not bundled from a user's download;
subscription access does not grant this project blanket redistribution rights.

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
