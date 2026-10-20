# Xplanet and TotalMarker

This project renders an Xplanet Earth desktop and generates its cloud image,
earthquake, volcano and tropical-cyclone markers, storm arcs, and update
labels. TotalMarker is Python 3.11+; `scripts/xplanet.sh` and
`scripts/xp-setup.sh` handle Xplanet, maps and macOS setup in shell. Optional
NORAD satellite files and NASA central eclipse paths are available but disabled
by default. Santa is a disabled stub.

## Quick start (macOS)

Install [Homebrew](https://brew.sh/) first, then clone and run the installer:

```sh
git clone https://github.com/blogabe/Xplanet.git ~/.xplanet
cd ~/.xplanet
./scripts/xplanet.sh install
```

`install` installs Xplanet and a compatible Python, then continues directly to
interactive setup. You do not need a separate setup command after it. For an
existing installation, `./scripts/xplanet.sh setup` runs setup alone; use
`./scripts/xplanet.sh setup --dry-run` to inspect its preparation steps.

To update a checkout with a configured Git upstream, run:

```sh
./scripts/xplanet.sh update
```

`update` fetches the current branch's configured upstream and fast-forwards
only when local files are safe. It does not discard edits or assume a branch
named `master`, and it does not run install or setup.

## Setup and configuration

The checkout includes safe Xplanet configuration examples. Review your feed
settings before accepting live refresh prompts. The TotalMarker launcher
checks each `python3` on `PATH`, then Homebrew's reported prefix and standard
Apple Silicon, Intel, and per-user Homebrew locations. A set
`TOTALMARKER_PYTHON` must be an absolute compatible executable and is never
silently replaced. Setup uses the selected absolute path in new launchd jobs;
no global `PATH` change is required.

After its preparation prompt, setup copies any missing personal `xp.conf`,
`xp.def`, TotalMarker TOML and Earth marker config from the shipped examples.
Standalone setup leaves existing personal files untouched. After `install`,
setup changes an existing `xp.def` only if you explicitly approve its
`XPLANET_BIN` update. You may instead put reviewed custom files in `config/`
before setup. Inspection modes do not write files.

The templates use `earth.jpg` and `night.jpg` from the installed Xplanet data
directory; [Xplanet documents its installed-data search path](https://xplanet.sourceforge.net/README).
They are referenced, not copied into this repository. `EARTH_MAP_PRE=stock`
makes `earth` a safe no-op because no monthly map link is needed. The stock
configuration retains the Earth, quake, volcano, storm marker/arc and update
label entries; generated files appear after their successful product runs.
The cloud layer is commented until a cloud image is configured and downloaded.
With these stock maps, set the personal TotalMarker cloud resolution to 2048
and then enable `cloud_map=clouds-2048.jpg` in `xp.conf`.
Confirm the package assets and rendering on a clean VM before relying on them.

For a seasonal high-resolution layout, set `EARTH_MAP_PRE=folder/stem`,
change `map=earth.png` in `xp.conf`, and supply the matching twelve files
`assets/maps/folder/stem.2004MM.3x5400x2700.png`. The legacy setup path also
expects `assets/maps/lights/earth_lights_4800.tiff`,
`assets/maps/bump/gebco_08_rev_elev_21600x10800.png`, and
`assets/maps/specular/specular.png` for its optional texture links. Select
those `xp.conf` layers only after supplying the files. Git ignores local
assets. Supply the seasonal files in your own checkout; the stock map path
works without them.

`xp.def` sets `XPLANET_HOME` and `XPLANET_CONFIG` from the checkout at runtime.
For a newly created copy, setup fills `XPLANET_BIN` with the binary found on
`PATH`; `install` passes the binary it just built. An existing personal
`xp.def` is preserved by standalone setup, so set its `XPLANET_BIN` to an
absolute executable path yourself. After `install`, setup asks explicitly
before changing an existing value.
Review personal settings before accepting live refresh prompts.

```sh
./scripts/xplanet.sh --help
./scripts/xplanet.sh setup --dry-run
./scripts/xplanet.sh setup --check
```

`setup --dry-run` lists missing directories, personal examples and safe map
links without writing. `setup --check` exits 0 when ready, 1 when safe
preparation remains, and 2 for unsafe paths. The interactive `setup` command
checks the configured Xplanet executable and Python, asks before preparing
files, then separately offers marker refreshes, a cloud download and launchd
activation. A live refresh uses the configured provider. The tracked
`config/totalmarker.example.toml` contains an intentionally unfetchable
`.invalid` cloud URL: review the personal copy before accepting that prompt.
Setup installs no packages or virtual environment.

`install` is a separate, deliberate Homebrew operation. It runs `brew tap
blogabe/xplanet`, `brew trust blogabe/xplanet`, source-builds
`blogabe/xplanet/xplanet` with `--without-giflib --with-cspice`, and runs
unversioned `brew install python`. It locates the installed Xplanet binary
and offers exactly one finite Xplanet launch for macOS security approval.
During the subsequent setup, it asks before changing `XPLANET_BIN` in an
existing `xp.def`. Declining the optional launch does not fail installation.
A missing `xp.def` is copied from the example only after setup confirmation.
A failed install stops before setup; an unresolved existing `xp.def` stops
setup before personal files are prepared.
Homebrew formula compatibility and macOS approval still need VM verification.

The working data directories are `images/`, `markers/`, `arcs/`, `satellites/`,
`logs/totalmarker/` and `.state/totalmarker/`. `scripts/launchd/` holds six
tracked `.plist.example` templates and ignored personal `.plist` files.
Setup preserves existing personal plists and checks registration after each
optional `launchctl load -w` request. Preflight accepts existing launcher and
log paths that resolve inside this project from the job's `WorkingDirectory`.
An absent `TOTALMARKER_PYTHON`
uses the launcher's interpreter selection; a present override must be an
executable Python 3.11+ path, though it need not match the interactive choice.
These checks do not prove launchd execution on a clean VM. The start job has
`RunAtLoad`, so accepting automation may start Xplanet. An interrupted setup
may leave new directories or loaded jobs; inspect the result before rerunning.

## Commands

Run `scripts/xplanet.sh --help` for the current command list. Commands work
from any directory because the launcher resolves its project root.

| Command | Effect |
| --- | --- |
| `install` | Homebrew install, optional one-frame approval launch, then interactive setup |
| `setup [--dry-run\|--check]` | Inspect or interactively prepare this working root |
| `update` | Fetch the current Git branch's configured upstream and fast-forward only |
| `start` / `stop` | Fork the configured Xplanet display / run `killall xplanet` |
| `preview` / `render` | One local Xplanet frame, under `dev/preview/`, without starting the desktop |
| `earth` | Select the current local calendar month's configured Earth map link |
| `clouds` | Download/validate the selected cloud image and refresh labels |
| `quake` / `volcano` | Fetch and render the selected earthquake / weekly volcano feed |
| `storm` | Fetch worldwide tropical-cyclone positions and tracks |
| `label` (`labels`) | Refresh the shared update label offline |
| `norad` / `eclipse` | Explicit optional satellite / central-eclipse products |
| `santa` | Disabled foundation stub, not live tracking |
| `test` | Run the offline regression suite |

`start` retains the Xplanet search directory, config, projection, longitude,
label position, date format, color and `-fork` display options. `stop` is
system-wide for Xplanet processes the caller may signal; it is not scoped to
this checkout. `preview` writes one 1920×1080 frame to
`dev/preview/earth-manual.png`; `render` uses `XPLANET_GEOMETRY` and writes
`dev/preview/earth-render.png`. Both require the configured projection and
longitude. `earth` is a no-op with stock maps; the seasonal mode requires a
matching monthly map in `assets/maps/` and refuses to replace an unrelated
regular file or unsafe link.

`update` requires a configured remote/upstream for the checked-out branch.
It refuses tracked local edits and untracked or ignored files that would be
overwritten. It checks the branch, commit and upstream again after fetch, and
only then attempts a fast-forward. That check and the Git operation are
separate, so do not run concurrent Git commands. It runs no install, setup,
feed, service or push.

## TotalMarker configuration

Setup copies `config/totalmarker.example.toml` to ignored
`config/totalmarker.toml` when it is missing; edit that personal copy before
live refresh. The example is safe to parse, not a live-ready credential file.
Native TOML and flat INI are both supported; the launcher
uses the personal TOML by default. Relative paths resolve against the project
root, never the caller's directory or the configuration file's directory.
Configuration is not rewritten by normal product commands. Cloud-only safe
TOML examples also live under `dev/examples/`.

`[cloud].provider` selects `xeric` or `custom`. Only the selected provider's
URL and authentication are used. Xeric accepts its fixed HTTPS origin and
2048/4096/8192-pixel widths; custom HTTPS URLs can use independent widths
and credentials. URL and filename templates may contain `{resolution}`;
URL/image outputs may also use `{local_image_name}`. Unsupported placeholders,
wrong TOML types and output paths outside approved runtime areas fail
validation. Set credentials in the ignored personal file or use environment
references; launchd jobs do not automatically inherit an interactive shell's
environment. Custom mode never borrows Xeric credentials. No plaintext secret
is intentionally written to persistent state or diagnostic logs.

`[quake]` selects USGS Day/Week/Month and
All/1.0/2.5/4.5/Significant summary GeoJSON with an inclusive minimum
magnitude. `[volcano]` defaults to GVP weekly CAP; `provider = "weekly_html"`
selects the official weekly page and joins its report IDs to a static
coordinate-only catalogue. That catalogue does not determine volcanic
activity; see `scripts/totalmarker/data/README.md` for provenance.
`[storm]` uses official NHC and JTWC current-storm, warning, track and
significant-weather sources. Unsupported or incomplete coverage fails closed
and preserves the last good marker/arc pair. All product style, interval and
output settings are shown in the example TOML.

## Output and freshness rules

Cloud images are accepted as bounded, structurally valid JPEGs; the validator
is not a full pixel decoder. A cloud label's displayed time comes from the
image's `EarthDesk Cloud Image Created ... UTC ...` comment, formatted in
local time. Missing, conflicting or future creation metadata displays
`UNKNOWN` in Red. Download time, HTTP Last-Modified and local file mtime do
not substitute for image creation. Identical bytes, HTTP 304, cache hits and
failed fetches retain the saved image's creation time.

Quake, volcano and storm labels use the latest successful execution time.
A valid unchanged response or cache hit can refresh that time; a failure
retains the previous successful time and last-good output. Source-report,
event-origin, fetch and file-installation times remain separate diagnostic
facts. Cloud and marker warning intervals are configured independently;
Green lasts through the warning limit, Yellow through twice it, then Red.

The shared `markers/updatelabel` file preserves existing rows, their order,
coordinates and options, plus unknown rows verbatim. A new update row uses
first coordinate `-(53 + 15 × existing row count)`. Cloud rows deliberately
use second coordinate `-12`; quake, volcano and storm rows use `-13`. The
one-pixel difference right-aligns the visible label stack and must not be
normalized. The visible volcano label retains `Volcano Infomation` spelling.
Any product refresh also re-ages other known rows from saved times.

Storm output comprises `markers/storm` and `arcs/storm`. NHC supplies
Atlantic/East/Central Pacific current storms, best tracks and forecasts;
JTWC supplies Northwest Pacific, North Indian and Southern Hemisphere
warnings/tracks, with ABPW/ABIO invest positions. Invest summaries add no
unsupported arcs. An explicit same-area invest-to-warning reference lets the
numbered warning replace the invest without reusing its previous coordinate.
Source categories must be complete and fresh; unrecognized
empty wording, stale observations and malformed forecasts fail without
publishing a false empty result. The conservative NHC 24-hour forecast rule
and naturally empty JTWC wording still need live-case validation.

JTWC RSS can link a tropical cyclone formation alert with a `web.txt` filename
and KMZ even though it has no numbered warning. TotalMarker validates that
alert's invest code, dated current position and agreement with the linked
significant advisory; the invest uses the advisory position and gains no
invented forecast arc. A newer advisory may supersede the alert's position;
same-time positions must agree, and an older advisory is rejected. A captured
2026-10-20 advisory also places its issue interval on the `SUBJ` line, which
is checked against its dated header.

Volcano CAP and weekly HTML are offline-tested but unattended retrieval is
paused. Local programmatic access to GVP returned HTTP 403; no equivalent
global weekly replacement has been verified. This may change, so a saved report
fixture proves parsing, not future access. A direct `volcano` refresh still
reports failure and retains the last good marker and stale status. During
interactive setup, an exit 1 with a valid failed TotalMarker result for a
selected quake, storm, volcano or cloud refresh becomes an optional warning
with its reason and an absolute retry command. It does not make otherwise
successful setup fail. Missing or malformed results, configuration, storage
and internal errors (exit 2), unexpected launcher failures, and preparation
or automation errors remain setup failures. If no earlier output exists,
the affected layer is unavailable until a successful refresh; any retained
older output may be stale. GVP HTTP 403 remains a known provider-access example, not evidence
of current volcano data.

Writes stay inside the explicit project root, in approved runtime areas.
Internal output symlinks may be retained; outside-root paths, protected source
folders and unsafe case aliases are rejected. A shared local lock and
product-specific intent journals recover interrupted output/state/label
publication on the next run. These files are not one atomic filesystem
transaction: a viewer can briefly observe a partial update before recovery.
The lock does not coordinate separate computers syncing the same folder.

## Optional products

NORAD is disabled by default. A deliberate `[norad].catalog_ids` selection
fetches one-to-five-digit TLE catalog IDs; optional `[[norad.groups]]` can
select CelesTrak `stations`, `science` or `visual` matches, with profile style
overrides. No more than 16 representable objects are published. Six-digit
matches are reported but cannot fit Xplanet's five-digit TLE format. On a
source failure the last verified selector/TLE pair remains. Requests respect
CelesTrak's two-hour provider interval. Displaying the files requires a
separate operator change to Xplanet's `satellite_file` setting.

Eclipse is also disabled by default. It discovers upcoming/current NASA GSFC
central total, annular or hybrid paths, or accepts an explicit path URL. It
publishes `markers/eclipse` and `arcs/eclipse` together; a lower-left notice
can be enabled independently. Source failure preserves verified geometry;
saved event times can hide an expired path. Partial-only eclipses have no
central path in this product. Display requires separate Xplanet marker/arc
settings.

`santa` has no verified live coordinate provider and no production tracking.
Its TOML placeholder remains entirely commented. The intended future choice
is on/off when Xplanet starts, not a separate scheduled refresh.

## Verification, attribution and release limits

Run `./scripts/xplanet.sh test` for the offline suite. It uses mocked HTTP,
saved fixtures and stubbed system commands; it does not verify live providers,
a Homebrew build or desktop behavior.

Data and software sources include the original TotalMarker Perl scripts,
[Xplanet](https://xplanet.sourceforge.net/), the
[Homebrew Xplanet tap](https://github.com/blogabe/homebrew-xplanet),
[USGS earthquake feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php),
[NOAA/NHC](https://www.nhc.noaa.gov/), [JTWC](https://www.metoc.navy.mil/jtwc/jtwc.html),
[Smithsonian GVP](https://volcano.si.edu/), [CelesTrak](https://celestrak.org/),
[NASA GSFC eclipses](https://eclipse.gsfc.nasa.gov/) and
[GDACS volcano coordinates](https://www.gdacs.org/).
Review software licensing and imagery redistribution rights before publishing
a release.
