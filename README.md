# Xplanet and TotalMarker

Xplanet renders the Earth desktop. Python 3.11+ runs TotalMarker, which downloads
cloud imagery and generates earthquake, volcano and storm markers, storm arcs, and
update labels for Xplanet. Optional launchd jobs start the display and schedule
refreshes. NORAD satellites and central eclipse paths are available but disabled
by default; Santa is a disabled stub.

[Xplanet](https://xplanet.sourceforge.net/) is by Hari Nair. Michael Dear wrote
and maintained the original Perl TotalMarker, which inspired this Python version;
see the [original marker-file notes](https://blog.rajab.us/xplanet/markerfiles/).

## Install on macOS

Requires [Homebrew](https://brew.sh/), Git, curl and zsh.

```sh
/bin/zsh -c 's=$(curl -fsSL https://raw.githubusercontent.com/blogabe/Xplanet/main/scripts/xplanet.sh) && eval "$s"' -- bootstrap
```

Follow the setup prompts. Set your cloud URL in
`~/.xplanet/config/totalmarker.toml` before enabling cloud refreshes.

Or clone and install manually:

```sh
git clone https://github.com/blogabe/Xplanet.git ~/.xplanet
cd ~/.xplanet
./scripts/xplanet.sh install
```

## Maps and configuration

The stock configuration uses `earth.jpg` and `night.jpg` from the installed
[Xplanet data directory](https://xplanet.sourceforge.net/README). It includes
Earth, quake, volcano and storm marker entries; generated files appear after
successful refreshes. To display clouds with the stock maps, select 2048-pixel
clouds in `config/totalmarker.toml` and enable `cloud_map=clouds-2048.jpg` in
`config/xp.conf` after downloading a cloud image.

The included `assets/maps/` directory has monthly Earth maps and optional lights,
bump and specular textures. For example, select the included `world.topo` set with
`EARTH_MAP_PRE=world.topo/world.topo` in `config/xp.def` and `map=earth.png` in
`config/xp.conf`. The `earth` command points `images/earth.png` to the current
month's map. When enabled, the `earth-map` launchd job runs that selection on the
first day of each month.

The [original map notes](https://blog.rajab.us/xplanet/maps/) describe NASA
imagery, a preference for 1994–95 night lights because the Nile and Trans-Siberian
corridor showed more clearly, and a specular map assembled from Celestia
Motherlode tiles.

TotalMarker settings live in `config/totalmarker.toml`. `[cloud]` selects a Xeric
or custom HTTPS image source and its credentials; `[quake]` selects a USGS feed
and magnitude threshold; `[storm]` uses NHC and JTWC; `[volcano]` uses Smithsonian
GVP weekly data. See `config/totalmarker.example.toml` for available styles,
intervals and output settings. If a launchd job needs a credential from the
environment, configure it for that job; launchd does not inherit your interactive
shell environment.

## Commands

Run `./scripts/xplanet.sh --help` for the current command list. Commands work from
any directory.

| Command | Action |
| --- | --- |
| `bootstrap` | Clone into a new `~/.xplanet`, then run install (Homebrew required) |
| `install` | Install Xplanet and Python, then run setup |
| `setup [--dry-run\|--check]` | Prepare or inspect this installation |
| `update` | Fast-forward Git, then reinstall Xplanet if the tap formula changed |
| `start` / `stop` / `restart` | Start, stop, or restart the desktop display |
| `preview` / `render` | Save one frame under `dev/preview/` |
| `earth` | Select the current seasonal Earth map |
| `clouds`, `quake`, `storm`, `volcano` | Refresh that product and its labels |
| `label` | Refresh update labels without fetching a product |
| `norad`, `eclipse` | Run an explicitly configured optional product |
| `test` | Run the offline test suite |

`start` uses `XPLANET_GEOMETRY` from `xp.def` when nonempty; otherwise Xplanet
sizes the desktop automatically. `render` saves a frame at the configured
dimensions, while `preview` uses a fixed 1920×1080 size. `stop` signals
this user's Xplanet processes and succeeds when none is running. `restart`
waits for them to stop, then starts one display.

To update your checkout:

```sh
./scripts/xplanet.sh update
```

`update` needs a configured upstream and fast-forwards only when local changes
allow it. It then updates Homebrew tap metadata and rebuilds the tap's Xplanet
formula from source only when its recipe differs from the installed build,
keeping the installed build options. If Xplanet was running before a successful
reinstall, `update` restarts the display; otherwise it stays stopped. If the
Homebrew check fails, the Git checkout may already be updated; rerun `update`
after resolving the reported issue.
It does not run setup.

## Output and freshness

Cloud labels show the image's embedded creation time, not the download time.
Missing or future creation metadata displays `UNKNOWN` in red. Quake, storm and
volcano labels show the latest successful refresh time; a failed refresh retains
the last good output and its earlier time. Label colors age from green through
yellow to red using the configured warning intervals.

Storm updates publish `markers/storm` and `arcs/storm` together. Incomplete or
stale source coverage does not replace the last good pair. See the command result
before treating any layer as current.

For timestamp, cache, and log details, see [Technical notes](docs/technical-notes.md).

Optional NORAD and eclipse products require deliberate configuration and
corresponding Xplanet display settings. Santa has no live provider or production
tracking.

## Known limitation

Automated requests to the Smithsonian GVP weekly volcano source are returning
HTTP 403. Setup treats a failed volcano refresh as a warning and continues,
leaving any existing volcano markers in place; they may be stale. A fresh install
has no volcano markers until retrieval succeeds or a marker file is supplied
manually.

## Sources

Data sources include
[USGS](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php),
[NOAA/NHC](https://www.nhc.noaa.gov/),
[JTWC](https://www.metoc.navy.mil/jtwc/jtwc.html),
[Smithsonian GVP](https://volcano.si.edu/), [CelesTrak](https://celestrak.org/)
and [NASA GSFC eclipses](https://eclipse.gsfc.nasa.gov/). The Xplanet build is
provided through the [Homebrew tap](https://github.com/blogabe/homebrew-xplanet).
