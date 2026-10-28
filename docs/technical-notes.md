# Technical notes

## Labels and timestamps

TotalMarker shares `markers/updatelabel` across products. A product run re-ages configured rows, including when it retains existing output; `./scripts/xplanet.sh label` does this without fetching. A matching row keeps its position, order, and other options while its text and color change. Unrelated rows are retained. Older product labels spelling “Infomation” are corrected in place on refresh.

The cloud label uses the JPEG's embedded EarthDesk creation time, displayed in local time. Download time, local file modification time, and HTTP `Last-Modified` do not establish when the image was created. Missing, conflicting, or future-dated creation metadata displays `UNKNOWN` in red. Quake, storm, and volcano labels use the last confirmed successful refresh time. A valid check with unchanged output can advance that time; `installed_at` changes only when output bytes are published, while `checked_at` records a local check, including one that skips HTTP. Provider source times, such as a quake feed's generation time or a storm advisory's issue time, are separate from the label time.

A label is green through its configured warning interval, yellow through twice that interval, and red afterward. Missing or future-dated times are red. The label can age while its marker or image stays in place.

## Fetches and provider limits

The configured check interval can skip a network request when matching, valid local output was fetched recently. For clouds, `Cached image retained` means no HTTP request occurred; `Server reported no change` means HTTP 304. An identical HTTP 200 also leaves the installed image unchanged. A newer server modification time can still accompany an older embedded cloud creation time. Storm caching is additionally bounded by advisory validity.

Storm data combines NHC Atlantic/East/Central Pacific coverage with JTWC Northwest Pacific, North Indian, and Southern Hemisphere coverage. JTWC significant-weather advisories also supply invest positions; an invest without an issued forecast gets no invented forecast arc. Missing, stale, or unrecognized required coverage fails the complete snapshot instead of publishing an apparently empty world map. `markers/storm` and `arcs/storm` are published as a pair.

NORAD and eclipse are disabled by default. NORAD supports at most 16 selected one-to-five-digit IDs for Xplanet's TLE format. Unsupported six-digit group matches are skipped with a warning when supported selections remain; an all-unsupported selection fails. Display requires a separate Xplanet `satellite_file` setting. Eclipse handles NASA central total, annular, and hybrid paths, not partial-only events; its marker and arc settings must also be enabled in Xplanet. The volcano weekly-HTML option uses a static coordinate catalogue only to locate volcanoes named in the weekly report; that catalogue does not determine activity.

## Failure and recovery

A provider download or validation failure reports `failed` and retains prior published output and its last successful label time. Labels continue aging; a fresh install without prior valid output has no affected layer until a successful refresh. Product commands return nonzero on failure.

TotalMarker writes only to approved runtime areas inside its project root: `images/`, `markers/`, `arcs/`, `satellites/`, `logs/totalmarker/`, and `.state/totalmarker/`. An internal output symlink is allowed only when its destination remains in an approved area; outside-root and protected source/configuration paths are rejected. A shared local lock serializes jobs in one installation. Product journals can replay an interrupted output/state/label publication on the next run using the same configuration. The files are not one atomic filesystem transaction, so a viewer can briefly see a partial update before recovery. This lock does not coordinate separate computers syncing the same folder.

## First-install bootstrap

`xplanet.sh bootstrap` downloads `xp-bootstrap.sh`, which requires Homebrew and
Git, reserves `~/.xplanet`, clones the repository, and invokes the checkout's
`xplanet.sh install`. Existing destinations, including empty directories and
symlinks, are refused. A failed clone leaves its destination for inspection.
Both downloads finish successfully before execution; installer stdin is retained.
The entry point defaults to `main`; developers can select a branch or tag with
`XPLANET_BOOTSTRAP_REF`. For example, from a feature checkout whose branch is
available on GitHub:

```sh
XPLANET_BOOTSTRAP_REF=feature/bootstrap-install ./scripts/xplanet.sh bootstrap
```

The local entry point, downloaded helper and clone must use the same ref. Offline
tests exercise the README one-liner, failed downloads, destination protection,
stdin, exit status, and real Git clone mechanics with a local repository. They do
not perform a live first install.

`install` installs Xplanet and Homebrew Python, offers a one-frame Xplanet launch
for macOS security approval, and continues into interactive setup. Setup creates
missing personal files from examples and preserves existing files. The example
cloud URL ends in `.invalid` and must be replaced before enabling cloud refreshes.
Setup offers product refreshes and launchd automation separately.

To rerun setup, use `./scripts/xplanet.sh setup`. With an existing `config/xp.def`,
`XPLANET_BIN` must point to the installed Xplanet executable. Set
`TOTALMARKER_PYTHON` to an absolute Python 3.11+ executable only to override the
launcher's interpreter selection. No global `PATH` change is required.

## Setup checks and testing

`./scripts/xplanet.sh setup --dry-run` lists safe preparation without writing. `setup --check` returns 0 when directory, link, and personal-file preparation is ready; 1 when safe preparation remains; and 2 for invalid or unsafe input. It does not test live providers or prove launchd jobs will run. Setup verifies existing personal launchd plists and preserves them rather than replacing them; it renders only missing ones. A provider refresh that returns a valid failed TotalMarker result is reported as an optional warning; malformed results, configuration errors, and preparation or automation failures remain setup failures.

`./scripts/xplanet.sh test` runs offline tests with mocked HTTP, saved fixtures, and stubbed system commands. Passing tests do not establish future provider availability, a Homebrew build, or desktop and scheduled-job behavior on another Mac.

## Logs

The example launchd jobs send normal command output, including TotalMarker's JSON result, to `logs/xplanet.log`. Their stderr goes to separate files such as `logs/xplanet-clouds.log` or `logs/xplanet-storm.log`; an empty stderr file does not mean the refresh succeeded. TotalMarker also appends product outcome events to `logs/totalmarker/events.jsonl` when logging is configured. These paths are relative to the installation root in the supplied examples and can be changed by configuration or plist customization.
