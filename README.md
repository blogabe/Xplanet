# Xplanet for macOS

[Xplanet](https://xplanet.sourceforge.net/) renders Earth, other planets and moons.
This project brings its maps, scene configuration, current-data overlays and
macOS desktop automation together. Xplanet is required for previews and the desktop.

The [configurator](docs/configurator/user-guide.md) lets you explore and preview
scenes, save native configurations and explicitly select a scene for the next
start/restart. See the [stock scenes](docs/configurator/stock-scenes.md).

TotalMarker downloads cloud imagery and generates earthquake, volcano and storm
markers, storm tracks and update labels. Optional NORAD satellite and central
eclipse products are disabled by default; Santa remains a disabled stub.

`xplanet.sh` manages installation, setup, updates and desktop control; optional
launchd jobs start the display and schedule refreshes. Both the configurator and
TotalMarker require Python 3.11+. The configurator's UI dependencies are isolated;
TotalMarker uses only the Python standard library.

[Xplanet](https://xplanet.sourceforge.net/) is by Hari Nair. Michael Dear wrote
and maintained the original Perl TotalMarker, which inspired this Python version;
see [credits and third-party terms](docs/asset-credits.md).

See the [documentation index](docs/README.md) and [configuration examples](examples/README.md).

## Install on macOS

Requires [Homebrew](https://brew.sh/) with `trust` support, Git, curl and zsh.
The bundled maps are large; allow several gigabytes for the checkout, history and
private runtimes. A shallow manual clone is available; see [installation details](docs/management.md#checkout-size).

```sh
/bin/zsh -c 's=$(curl -fsSL https://raw.githubusercontent.com/blogabe/Xplanet/main/scripts/xplanet.sh) && eval "$s"' -- bootstrap
```

The one-liner executes the current GitHub `main` scripts; review them before
running if you need to verify that version. Follow the setup prompts. Set your cloud URL in
`~/.xplanet/config/totalmarker.toml` before enabling cloud refreshes.

Or clone into a new directory and open guided management:

```sh
git clone https://github.com/blogabe/Xplanet.git ~/.xplanet
cd ~/.xplanet
./scripts/xplanet.sh
```

Use a destination that does not already exist; open an existing checkout in place.
Direct `install` provisions dependencies and continues into setup; `setup` reuses
installed prerequisites. After setup, run `./scripts/xplanet.sh start` if you skipped
its start offer, then `./scripts/xplanet.sh health` to inspect saved source status.
Start acceptance is asynchronous; see the [first-run sequence](docs/management.md#quick-start)
for what to expect and how to diagnose missing wallpaper.

For TotalMarker-only use, including Linux, see
[Running TotalMarker independently](docs/totalmarker-standalone.md).

## Maps and configuration

The stock configuration uses `earth.jpg` and `night.jpg` from the installed
[Xplanet data directory](https://xplanet.sourceforge.net/README). It includes
Earth, quake, volcano and storm marker entries; generated files appear after
successful refreshes. To display clouds with the stock maps, select 2048-pixel
clouds in `config/totalmarker.toml` and enable `cloud_map=clouds-2048.jpg` in
`config/xp.conf` after downloading a cloud image.

The included `maps/` directory has monthly Earth maps and optional lights,
bump and specular textures. For example, select the included `world.topo` set with
`EARTH_MAP_PRE=world.topo/world.topo` in `config/xp.def` and `map=earth.png` in
`config/xp.conf`. The `earth` command points `images/earth.png` to the current
month's map. When enabled, the `earth-map` launchd job runs that selection on the
first day of each month.

See [asset credits and source records](docs/asset-credits.md) for map provenance
and third-party terms.

TotalMarker settings live in `config/totalmarker.toml`. `[cloud]` selects a Xeric
or custom HTTPS image source and its credentials; `[quake]` selects a USGS feed
and magnitude threshold; `[storm]` uses NHC and JTWC; `[volcano]` supports CAP or
Smithsonian GVP weekly data. See `config/totalmarker.example.toml` for styles,
intervals and output settings. If a launchd job needs a credential from the
environment, configure it for that job; launchd does not inherit your interactive
shell environment.

## Commands

Run `./scripts/xplanet.sh --help` for the current command list. Commands work from
any directory. Bare `./scripts/xplanet.sh` opens [terminal management](docs/management.md);
`config` opens the separate scene studio: reopen a saved view, preview,
save a new copy or cancel; explicitly select a reviewed scene separately from restart. See [Configurator](docs/configurator/README.md)
for its explicit isolated-runtime preparation and current limits. Management also offers
[TotalMarker interpreter selection](docs/python-runtime.md): Homebrew is recommended,
with uv-managed Python available as an explicit choice.

| Command | Action |
| --- | --- |
| `bootstrap` | Clone into a new `~/.xplanet`, then run install (Homebrew required) |
| `install` | Install Xplanet and Python, then run setup |
| `setup [--dry-run\|--check]` | Prepare or inspect this installation |
| `config [--prepare]` | Open the scene studio; explicitly prepare its isolated UI if needed |
| `update` | Fast-forward Git, then reinstall Xplanet if the tap formula changed |
| `start` / `stop` / `restart` | Start, stop, or restart the desktop display |
| `preview` / `render` | Render the custom Earth configuration under `output/preview/` |
| `earth` | Select the current seasonal Earth map |
| `clouds`, `quake`, `storm`, `volcano` | Refresh that product and its labels |
| `label` | Refresh update labels without fetching a product |
| `log-view [--file PATH]` | Read stderr with counts for repeated resize notices; raw logs stay unchanged |
| `log-trim [--dry-run] [--days N]` | Trim recognized event logs older than 30 days by default |
| `health [--live] [--json] [--verbose]` | Read saved health, or validate sources without updating outputs |
| `norad`, `eclipse` | Run an explicitly configured optional product |
| `diagnostics [--show]` | Explicitly probe renderer support, or show saved evidence |
| `test` | Run the supported macOS offline test suite |

`start` catches up the monthly map on the custom configuration path and runs one
launchd-owned foreground desktop, without automatic respawn after stop. A selected
studio scene keeps its reviewed map/time choices. `stop` removes the managed job
and stops current-user processes named `xplanet` or by the trusted configured
renderer, including finite renders; it does not discover arbitrary historical
renderer names. `restart` performs that stop before starting a display.
See [desktop behavior and upgrade details](docs/management.md#desktop-commands)
for geometry, previews, process names and the old-launcher transition.

To update your checkout:

```sh
./scripts/xplanet.sh update
```

`update` needs a configured upstream and fast-forwards only when local changes
allow it. It then updates Homebrew tap metadata and rebuilds the tap's Xplanet
formula from source only when its recipe differs from the installed build,
keeping the installed build options. If this user's Xplanet processes were running
before a successful reinstall, `update` requests a validated restart; otherwise it stays stopped. A changed renderer binding requires a fresh reviewed scene selection; failed preflight preserves the running display. If the
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
For internal boundaries and file ownership, see [Architecture](docs/architecture.md).

Optional NORAD and eclipse products require deliberate configuration and
corresponding Xplanet display settings. Santa has no live provider or production
tracking.

## Limitations and troubleshooting

Provider access and source coverage are separate; green labels alone do not prove
current access. Known limits include:

- Volcano reports through 2026-11-04 included rejected stale CAP coverage and HTTP
  403 from weekly HTML. A fresh install has no volcano markers until retrieval
  succeeds. Choose a source explicitly; see [volcano sources](docs/technical-notes.md#volcano-sources).
- Storm refreshes fail closed on incomplete coverage or unsupported provider-format
  changes, retaining the last-good marker/track pair.
- NORAD currently accepts one-to-five-digit catalogue IDs; six-digit IDs are unsupported.
- An intermittent missing-desktop-job restart was reported; later restarts were
  reported working, without a reproduced cause. See [troubleshooting](docs/management.md#troubleshooting).

Scene previews and reviewed selection do not verify desktop permissions or every
renderer build/asset. See [configuration health](docs/configurator/diagnostics.md),
[desktop troubleshooting](docs/management.md#troubleshooting), and the
[validation boundaries](docs/architecture.md#verification-boundaries).

## Sources

Data sources include
[USGS](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php),
[NOAA/NHC](https://www.nhc.noaa.gov/),
[JTWC](https://www.metoc.navy.mil/jtwc/jtwc.html),
[Smithsonian GVP](https://volcano.si.edu/), [CelesTrak](https://celestrak.org/)
and [NASA GSFC eclipses](https://eclipse.gsfc.nasa.gov/). The Xplanet build is
provided through the [Homebrew tap](https://github.com/blogabe/homebrew-xplanet).

## License and credits

Original project code and documentation are [MIT licensed](LICENSE). Bundled
textures, third-party data and upstream software retain their own terms; see
[asset credits and third-party terms](docs/asset-credits.md). Finished runtime
textures remain included; source tiles/archives are local development material.
