# Technical notes

## Labels and timestamps

TotalMarker shares `markers/updatelabel` across products. A product run re-ages configured rows, including when it retains existing output; `./scripts/xplanet.sh label` does this without fetching. A matching row keeps its position, order, and other options while its text and color change. Unrelated rows are retained. Older product labels spelling “Infomation” are corrected in place on refresh.

The cloud label uses the JPEG's embedded EarthDesk creation time, displayed in local time. Download time, local file modification time, and HTTP `Last-Modified` do not establish when the image was created. Missing, conflicting, or future-dated creation metadata displays `UNKNOWN` in red. Quake, storm, and volcano labels use the last confirmed successful refresh time. A valid check with unchanged output can advance that time; `installed_at` changes only when output bytes are published, while `checked_at` records a local check, including one that skips HTTP. Provider source times, such as a quake feed's generation time or a storm advisory's issue time, are separate from the label time.

A label is green through its configured warning interval, yellow through twice that interval, and red afterward. Missing or future-dated times are red. The label can age while its marker or image stays in place.

## Fetches and provider limits

The configured check interval can skip a network request when matching, valid local output was fetched recently. For clouds, `Cached image retained` means no HTTP request occurred; `Server reported no change` means HTTP 304. An identical HTTP 200 also leaves the installed image unchanged. A newer server modification time can still accompany an older embedded cloud creation time. Storm caching is additionally bounded by advisory validity. The shipped cloud, quake
and volcano example intervals leave a small margin below their launchd periods so
minor start-time jitter does not skip a whole cycle. Existing personal intervals
are preserved; strict interval comparisons are unchanged.

Storm data combines NHC Atlantic/East/Central Pacific coverage with JTWC Northwest Pacific, North Indian, and Southern Hemisphere coverage. JTWC significant-weather advisories also supply invest positions; an invest without an issued forecast gets no invented forecast arc. Missing, stale, or unrecognized required coverage fails the complete snapshot instead of publishing an apparently empty world map. `markers/storm` and `arcs/storm` are published as a pair.

NORAD and eclipse are disabled by default. NORAD supports at most 16 selected one-to-five-digit IDs for Xplanet's TLE format. Unsupported six-digit group matches are skipped with a warning when supported selections remain; an all-unsupported selection fails. Display requires a separate Xplanet `satellite_file` setting. Eclipse handles NASA central total, annular, and hybrid paths, not partial-only events; its marker and arc settings must also be enabled in Xplanet. The volcano weekly-HTML option uses a static coordinate catalogue only to locate volcanoes named in the weekly report; that catalogue does not determine activity. CAP and weekly HTML must identify one seven-day reporting period. Coverage ends at midnight UTC after its final day; reports more than 14 days past that cutoff, or more than one hour in the future, retain the last good markers without advancing the successful-refresh time. CAP uses headline coverage dates, not the alert sent time. Missing, malformed or conflicting CAP periods fail the refresh. This also applies to cached output and HTTP 304 responses.

Each normal refresh creates one fetch client. Its total network budget starts with
the first request: four times the configured socket timeout, with a 60-second
minimum and 300-second maximum (120 seconds for the usual 30-second timeout).
All requests and redirects in that refresh share the same monotonic deadline;
intermediate parsing consumes that remaining time too. Network-only workers bound
DNS, certificate setup, connect, headers, body reads and IPC. On timeout or
interruption they are killed/reaped before the product lock is released; a worker
also watches its deadline and parent identity. Credentials are sent through a
private pipe, not command arguments. A deadline failure follows normal last-good
and error-recording rules; it adds no retries or provider-access workaround.
This budget does not bound lock waiting, final parsing/publication or extraordinary
OS process failures. Injected offline transports are synchronous; a fetch client
reused by a custom caller retains its original deadline rather than resetting it.

## Failure and recovery

A provider download or validation failure reports `failed` and retains prior published output and its last successful label time. Labels continue aging; a fresh install without prior valid output has no affected layer until a successful refresh. Product commands return nonzero on failure. Offline label aging does not clear a
saved provider failure. A later validated cloud response, not an attempted request,
advances its fetch time; failed checks are retried rather than treated as cached success.

TotalMarker writes only to approved runtime areas inside its project root: `images/`, `markers/`, `arcs/`, `satellites/`, `logs/totalmarker/`, and `.state/totalmarker/`. An internal output symlink is allowed only when its destination remains in an approved area; outside-root and protected source/configuration paths are rejected. A shared local lock serializes jobs in one installation. Product journals can replay an interrupted output/state/label publication on the next run using the same configuration. The files are not one atomic filesystem transaction, so a viewer can briefly see a partial update before recovery. This lock does not coordinate separate computers syncing the same folder.
Storage/configuration errors can prevent label aging. In particular, an incompatible
or ambiguous pending journal blocks all normal mutations: it contains shared state
and labels, so bypassing it could roll back another product on later replay. Preserve
the journal and restore its original configuration before retrying; do not delete it
to suppress an error. Saved health reports pending recovery without replaying it.

A failed storm refresh keeps the latest rejection evidence in
`.state/totalmarker/storm-rejected.json`. It records already-received fixed public
source responses, never request headers, credentials or arbitrary URLs. Bodies are
base64 with hashes, original sizes and explicit truncation: at most 64 KiB per body,
256 KiB total bodies, 32 responses and 384 KiB JSON. Capacity is reserved for the
JTWC ABPW/ABIO advisories. Only the latest failed snapshot is retained; successful
and cached checks leave it intact. Configured-path collisions or unsafe aliases
suppress capture; capture failure does not replace the primary source failure.
Live health captures, if any, remain inside its disposable probe root. This evidence
may be incomplete and does not establish provider conventions by itself.

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
not perform a live first install. A tag checkout is intentionally detached and cannot
use branch fast-forward update; select a branch for installations that use `update`.

`install` installs Xplanet and offers an interactive Python choice (Homebrew is
recommended; uv is an alternative). Noninteractive install retains Homebrew
provisioning. It offers a one-frame Xplanet launch for macOS security approval,
then continues into interactive setup. See [Python runtime](python-runtime.md). Setup creates
missing personal files from examples and preserves existing files. The example
cloud URL ends in `.invalid` and must be replaced before enabling cloud refreshes.
Setup offers product refreshes and launchd automation separately. A failed first
provider fetch does not veto scheduled retries when the operator enables that
source. Re-running setup validates on-disk personal plists with plutil and leaves
already registered labels unchanged. Loaded settings are explicitly unverified;
label presence does not prove configuration equality. Setup does not replace
personal schedules.

To rerun setup, use `./scripts/xplanet.sh setup`. With an existing `config/xp.def`,
`XPLANET_BIN` must point to the installed Xplanet executable. Set
`TOTALMARKER_PYTHON` to an absolute Python 3.11+ executable only to override the
launcher's interpreter selection. No global `PATH` change is required.

For renderer build/support troubleshooting, run `./scripts/xplanet.sh diagnostics`
explicitly, or choose an absolute `--renderer` before setup. This records bounded
self-reported capabilities, not original compiler flags; setup/start do not probe
automatically. See [support evidence and limits](configurator/diagnostics.md#renderer-support-outside-the-studio).

## Setup checks and testing

`./scripts/xplanet.sh setup --dry-run` lists safe preparation without writing. `setup --check` returns 0 when directory, link, and personal-file preparation is ready; 1 when safe preparation remains; and 2 for invalid or unsafe input. It does not test live providers or prove launchd jobs will run. Setup verifies existing personal launchd plists and preserves them rather than replacing them; it renders only missing ones. A provider refresh that returns a valid failed TotalMarker result is reported as an optional warning; malformed results, configuration errors, and preparation or automation failures remain setup failures.

`./scripts/xplanet.sh test` runs offline tests with mocked HTTP, saved fixtures, and stubbed system commands. Passing tests do not establish future provider availability, a Homebrew build, or desktop and scheduled-job behavior on another Mac.
The CI workflow runs the full suite on macOS with Python 3.11 and 3.13, plus the
isolated configurator interactions on macOS Python 3.11. Ubuntu jobs are currently
disabled. Historical Linux checks and the available
`PYTHONPATH=scripts:dev python -m tests.run_portable` data/publication subset are
portability evidence, not current continuous Linux CI or macOS workflow coverage.
Standalone TotalMarker usage and the portable runner remain available.

`earth` uses a directory lock to serialize monthly map selection. Normal signals
clean it up; a crash or SIGKILL can leave it behind. If the command reports an
existing lock, first ensure no map selection is running, then inspect/remove only
the reported lock directory before retrying. No automatic lock stealing occurs.
Desktop lifecycle uses zsh and macOS launchd; it does not require Python.
Start selects the current monthly map and runs one managed foreground renderer,
without automatic respawn after stop. An existing unmanaged renderer prompts for
restart rather than being adopted. Stop stops all current-user Xplanet processes;
restart performs that same stop before starting a display. Legacy manual-map
configs without `EARTH_MAP_PRE` stay manual.
To disable future scheduled runs, unload the relevant personal LaunchAgent with
`launchctl unload "$HOME/Library/LaunchAgents/<job>.plist"`; stopping Xplanet alone
does not disable its scheduled jobs. Preserve the personal plist for re-enabling.

## Source health

Human terminal summaries color source names: green for current data, yellow for
stale or unverified output, red for a recorded refresh/access/inspection failure,
and dim for disabled sources. Freshness not assessed remains neutral. Text labels
remain authoritative; redirected output, JSON and `NO_COLOR` contain no colors.
A saved check performs no network request. Exit 1 means the assessment completed
with source/data issues; exit 2 means a local inspection/configuration/storage
error. Management distinguishes those outcomes in its result footer.

`./scripts/xplanet.sh health` reads saved state without fetching or writing.
The default is one line per enabled product with saved status and last success.
`--verbose` adds source URLs, check/attempt/success/publication times, coverage
and dated errors. Disabled products share one summary line.
Errors recorded before the last success are omitted from the default summary.
A check time can include an offline cache check; an unknown attempt time is not
inferred from it. Cloud
success falls back to its last confirmed publication when no successful-refresh
time was saved. Missing state or unsupported freshness remains unknown.

`health --live` runs the normal product validators in disposable output roots.
Normal markers, labels, state, caches and timestamps remain unchanged. It reports
access separately from content and freshness; valid content alone is not proof
of current coverage. Disabled optional products are skipped; Santa has no live
provider. NORAD respects the saved provider cooldown, but probes do not persist
a new cooldown: avoid repeated live requests. No provider restriction is bypassed.

Use `--json` for structured results. Exit status is 1 for an access failure,
invalid content, stale data or an enabled product's saved failed refresh
(`refresh_failed`), 2 for configuration/storage/recovery/probe errors, and 0 otherwise.
A local output error, even for a disabled product, is reported per product while the
remaining report continues. JSON adds `output.error` or `recovery_error` when relevant.
A successful isolated probe reports its own result without clearing the saved failure.
0 can include unknown health and is not an all-sources-current guarantee. This makes
saved failed refreshes nonzero; monitoring callers should handle exit 1 explicitly.
New checks persist bounded historical last-error facts alongside the product
result, even without logging. Older records fall back to the event log, which
may be unavailable or exceed the bounded diagnostic read. Health also exposes
last publication separately from last successful refresh. Saved results can predate config changes;
use `--live` to check the current configuration.

## Logs

The example launchd jobs send normal command output, including TotalMarker's JSON result, to `logs/xplanet.log`. Their stderr goes to separate files such as `logs/xplanet-clouds.log` or `logs/xplanet-storm.log`; an empty stderr file does not mean the refresh succeeded. TotalMarker also appends product outcome events to `logs/totalmarker/events.jsonl` when logging is configured. The supplied examples use `__XPLANET_ROOT__` path placeholders. Setup renders absolute working, launcher and log paths for the actual checkout, without adding a Python environment override. Existing personal plist customization is preserved.

Logs grow without automatic rotation. To inspect an optional manual trim:

```sh
./scripts/xplanet.sh log-trim --dry-run
./scripts/xplanet.sh log-trim --days 30
```

Only the configured `logs/totalmarker/*.jsonl` event log is eligible. The default
keeps 30 days, using each recognized event's `time`, not source or publication
dates. Exactly-at-cutoff, future, undated, incomplete and unknown records remain.
Malformed/multiline/duplicate-key or oversized records preserve the entire file;
files over 512 MiB are skipped. JSON reports scanned, removed, retained,
`would_remove` and per-path reasons. Dry-run writes nothing and returns estimates.

Rewriting shares the normal event writers' project lock and verifies file and
parent-directory identity before atomic replacement. Symlink/hardlink aliases,
configured state/output/journal collisions and source-evidence captures are
excluded. Writers outside this protocol cannot be coordinated by a stat check;
launchd stdout/stderr `.log` files are therefore reported as skipped and preserved.
No trim has run merely because this command is installed.
