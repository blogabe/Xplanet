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

The one-liner executes the current GitHub `main` scripts; review them before
running if you need to verify that version. Follow the setup prompts. Set your cloud URL in
`~/.xplanet/config/totalmarker.toml` before enabling cloud refreshes.

Or clone and install manually:

```sh
git clone https://github.com/blogabe/Xplanet.git ~/.xplanet
cd ~/.xplanet
./scripts/xplanet.sh install
```

For TotalMarker-only use, including Linux, see
[Running TotalMarker independently](docs/totalmarker-standalone.md).

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
and magnitude threshold; `[storm]` uses NHC and JTWC; `[volcano]` supports CAP or
Smithsonian GVP weekly data. See `config/totalmarker.example.toml` for styles,
intervals and output settings. If a launchd job needs a credential from the
environment, configure it for that job; launchd does not inherit your interactive
shell environment.

## Commands

Run `./scripts/xplanet.sh --help` for the current command list. Commands work from
any directory. Bare `./scripts/xplanet.sh` opens [terminal management](docs/management.md);
`config` is a placeholder that changes no settings.

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
| `log-trim [--dry-run] [--days N]` | Trim recognized event logs older than 30 days by default |
| `health [--live] [--json] [--verbose]` | Read saved health, or validate sources without updating outputs |
| `norad`, `eclipse` | Run an explicitly configured optional product |
| `test` | Run the offline test suite |

`start` uses `XPLANET_GEOMETRY` from `xp.def` when nonempty; otherwise Xplanet
sizes the desktop automatically. `render` saves a frame at the configured
dimensions, while `preview` uses a fixed 1920×1080 size. `stop` signals
ALL of this user's Xplanet processes, including finite renders and other checkouts,
and succeeds when none is running. It first removes the managed desktop job.
`restart` performs that same broad stop, then starts one display. `start` catches up
a configured monthly map and asks launchd to run one foreground desktop, without
`KeepAlive` or automatic respawn after stop. Python is used only for TotalMarker.

On the first start after upgrading from the old `-fork` launcher, an existing
unmanaged Xplanet process produces a request to use `restart`; setup never kills
it automatically. The existing login trigger stays compatible and can start the
display on a later login. Stopping a display does not disable login automation.
Start reports launchd's acceptance, not proof that the renderer produced an image;
renderer errors go to `logs/xplanet-error.log`. Normal and configured executable
names (including a resolved symlink target) are included in broad stop. Desktop
launch resolves executable symlinks. macOS name lookup cannot reliably discover
unmanaged, physically renamed binaries with names longer than 19 characters; use
the normal Xplanet binary name for those older manual launches.

To update your checkout:

```sh
./scripts/xplanet.sh update
```

`update` needs a configured upstream and fast-forwards only when local changes
allow it. It then updates Homebrew tap metadata and rebuilds the tap's Xplanet
formula from source only when its recipe differs from the installed build,
keeping the installed build options. If this user's Xplanet processes were running
before a successful reinstall, `update` performs the same broad restart; otherwise it stays stopped. If the
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

## Known limitation

Set a CAP URL or choose `provider = "weekly_html"` in `[volcano]` before
refreshing; the shipped CAP URL is a placeholder.

Automated CAP access resumed in late October 2026 after HTTP 403 failures.
Reliability is still being observed; successful access does not prove the report
is current. Setup warns if a volcano refresh fails and preserves existing
markers, which may be stale. A fresh install has no volcano markers until
retrieval succeeds or a marker file is supplied manually.

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
