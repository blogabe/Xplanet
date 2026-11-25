# Terminal management

Use this guide for macOS setup, desktop control and troubleshooting. For Linux or
data-only use, see [standalone TotalMarker](totalmarker-standalone.md).

## TotalMarker timing units

In `config/totalmarker.toml`, use whole units as named in each key:

- **Check intervals:** minutes for clouds, earthquakes and storms; hours for
  volcanoes (`check_interval_hours = 23`), NORAD (`check_interval_hours = 2`)
  and eclipses (`check_interval_hours = 24`).
- **Label warnings:** hours for clouds, earthquakes and storms; days for
  volcanoes and NORAD.
- **Other settings:** seconds for network timeouts, days for NORAD's
  `max_age_days` and hours for eclipse `notify_hours`.

The scheduler (launchd plist, cron, or systemd timer) decides when
TotalMarker runs. The TOML `check_interval_*` is the minimum time between
fetches when saved data can still be reused. A manual run can also reuse
recent data. Lowering the TOML value does not make the scheduler run more
often; raising it above the scheduled interval can make a run skip a fetch.
For example, the quake plist runs every 20 minutes, but TotalMarker can
reuse valid saved quake data fetched less than 18 minutes ago.

Prior TOML spellings (including eclipse `check_interval_days`) and INI
settings remain supported without rounding. Use only one spelling for a setting.
Response byte limits still apply by default; existing override keys
remain supported for deployments such as unusually large cloud maps.

## Quick start

1. Install through the [README one-liner](../README.md#install-on-macos), or clone
   into a new directory and run `./scripts/xplanet.sh` for guided management.
2. Follow Guided setup: prepare personal files, choose data sources and review
   the proposed schedules. Keep unconfigured products disabled; cloud access
   needs your source and credentials. For volcanoes, keep the Weekly Report
   default, select CAP, or skip.
3. Accept the optional start offer, or run `./scripts/xplanet.sh start` afterward.
   This asks launchd to run the configured renderer; it does not certify a frame.
4. Expect the desktop image to update asynchronously. If it does not, inspect
   `logs/xplanet-error.log` and [Finder Automation permission](#finder-automation-permission) before retrying.
5. Run `./scripts/xplanet.sh health` for saved data status. Only an explicit
   `health --live` checks provider access. Failed refreshes retain older output.
6. To explore scenes independently, run `./scripts/xplanet.sh config --prepare`
   once, then `./scripts/xplanet.sh config`. Saving, selecting and restarting are
   separate actions; the [studio guide](configurator/user-guide.md) explains them.

## Choose a cloud provider

Setup copies the [complete TotalMarker template](../config/totalmarker.example.toml)
only when personal `config/totalmarker.toml` is missing. Edit that personal file,
not the shipped template; do not replace an existing configuration with a recipe.

- **Custom:** keep `provider = "custom"` in `[cloud]` and replace the `.invalid`
  `url_template` in `[cloud.custom]` with your permitted HTTPS source. Leave
  credentials empty for `auth_mode = "none"`; use supported authentication only
  when your source requires it.
- **Xeric:** set `provider = "xeric"` in `[cloud]`. The fixed HTTPS URL and Basic
  authentication settings already exist in `[cloud.xeric]`; supply your subscription
  credentials there or name the environment variables holding them. Never commit
  personal credentials. LaunchAgents do not inherit your interactive shell environment.

Set `[cloud].resolution` once; the URL and output filename templates follow it.
Configure the source before enabling refreshes. Keep existing paths, labels and
other products unchanged unless you deliberately want to change them.

## Choose a volcano source

When setup creates your first `config/totalmarker.toml`, it defaults to the
Smithsonian GVP **Weekly Report (HTML)**. In an interactive terminal, press Enter
to keep it, or choose **Official CAP feed** or **Skip volcanoes for now**.
Without an interactive terminal, the fresh template uses the Weekly Report.
Choosing a source does not contact it; setup asks separately before a live
refresh and before installing automation.

If you skip, future setup runs do not offer a volcano refresh or register a new
volcano job, and direct refresh and live health do not contact a placeholder.
Existing personal settings and registered jobs are not migrated or removed.
To enable volcanoes later, edit your personal `[volcano]` settings: choose
`weekly_html` and clear the unused URL, or use `cap` with an explicit
[CAP URL](technical-notes.md#volcano-sources). Run setup again. An eligible
source can be scheduled with the automation bundle even if you decline the
immediate refresh; eligibility is not proof of access.

## Optional ISS and solar-eclipse overlays

These Earth overlays are off by default. Guided setup does not enable, refresh or
schedule them; start, restart and update do not fetch them. Edit your existing
personal `config/totalmarker.toml` and `config/xp.conf`, not the
[shipped template](../config/totalmarker.example.toml). Change the keys in their
existing TOML sections instead of adding a second section. The refresh commands
write data; the native Earth configuration tells Xplanet what to draw.

### Show the ISS

In `[norad]`, set `enabled = true` and keep `catalog_ids = "25544"` for the
International Space Station. The shipped ISS profile supplies the caption and
style; an [imported icon](installed-satellite-icons.md) is optional. Run from
your checkout:

```sh
./scripts/xplanet.sh norad
```

With the default output path, a successful refresh produces
`satellites/totalmarker` and its matching `satellites/totalmarker.tle`.
Add the following line under the existing `[earth]` section in your personal
`config/xp.conf`:

```ini
satellite_file=totalmarker
```

Keep the two files together and use current elements; the installed sample TLE
is historical. Xplanet estimates position from the elements, not from live
telemetry. Refresh explicitly and check `./scripts/xplanet.sh health --verbose`
before interpreting the overlay. A failed refresh can leave older files in
place; the running custom desktop does not enforce TotalMarker’s TLE expiry.

### Show a central solar-eclipse path

In `[eclipse]`, set `enabled = true`. Leave `path_url = ""` to discover a
current or upcoming central event, or set it to a NASA GSFC central-path table,
such as the [February 6, 2027 annular solar eclipse](https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2027Feb06Apath.html).
Total, annular and hybrid paths are supported; partial-only events are not.
Run:

```sh
./scripts/xplanet.sh eclipse
```

With the default output paths, add the following under the existing `[earth]`
section of `config/xp.conf`:

```ini
marker_file=eclipse arc_file=eclipse
```

These references draw `markers/eclipse` and `arcs/eclipse`. The producer writes
header-only files outside its display window, from the first timed path sample
minus `notify_hours` (48 hours by default) through one hour after the last timed
sample. A successful refresh of a distant event can therefore leave nothing to
draw. The overlay shows a published prediction, not a rendering of the eclipse
itself. Neither native overlay requires SPICE or an external ephemeris.

After editing the native configuration, try `./scripts/xplanet.sh preview` to
render a separate custom Earth frame before restarting the desktop. Visibility
also depends on framing, scene time and whether the object or path is in view.

### Optional launchd examples

After a manual refresh works, you can choose to schedule either producer using
the [NORAD LaunchAgent example](../scripts/launchd/local.xplanet.norad.plist.example)
or the [eclipse LaunchAgent example](../scripts/launchd/local.xplanet.eclipse.plist.example).
Guided setup does not install or register these templates. They are independent:
you do not need to enable both. They refresh the overlay files; they do not start,
stop, or restart Xplanet or edit your display settings.

- **NORAD** runs at :40 every three hours (00:40, 03:40, …, 21:40).
- **Eclipse** runs at 06:15 and 18:15.

Times are local to the Mac. These are opportunities to run the commands, not
guaranteed provider requests. TotalMarker applies its own cache and freshness
rules (default check intervals: two hours for NORAD and 24 hours for eclipse).
Eclipse can reevaluate when the display window changes; a successful run may
still draw nothing outside that window.

Make a separate personal copy without the `.example` suffix. In a plist editor,
replace `__XPLANET_ROOT__` in the working directory, launcher argument, and both
log paths with the absolute checkout path. The checkout's `logs/` directory must
exist. Keep the launcher path and its command as separate arguments; do not use
`~` or shell variables in paths. Review the copy with
`/usr/bin/plutil -lint -- /absolute/path/to/your.plist` before deliberately
installing it as a per-user LaunchAgent. Do not overwrite an existing agent.
Check `logs/xplanet.log` and the product's own error log if a scheduled run fails.

### Explore separately in the scene studio

The [astronomy capture guide](configurator/astronomy-capture.md) covers explicit
copies of existing validated output. Capture does not fetch or schedule data.
Frozen ISS is Earth/Now preview-only; it cannot be selected for the desktop while
active. To explore the 2027 eclipse before the producer’s display window, use
[local NASA-format path import](configurator/astronomy-capture.md#offline-local-nasa-format-path-import)
with the [saved February 6 NASA table](../tests/fixtures/nasa/2027-02-06-annular.html)
and its event URL above. Leave the optional first-row date blank for this
same-day table. Choose **Fixed UTC** `2027-02-06T16:00:00Z`, within the
14:08–17:52 UTC samples. This preview does not need a producer refresh and does
not change the desktop.

For a planet rather than an Earth overlay, open **Stock scenes…** and try
`mars-from-phobos`. The [stock scene catalogue](configurator/stock-scenes.md)
and [planetary limits](configurator/planetary.md) explain the bundled examples,
viewpoints and date bounds. These are finite views, not precision ephemerides.

## Using management

Run `scripts/xplanet.sh` without arguments in a terminal to open management.
Opening management assesses saved health once when configured; it does not refresh providers or change configuration. Leaving or cancelling makes no operational changes. `q` or EOF exits;
Ctrl-C interrupts. In capable terminals, Up/Down moves the highlight, digits 1–9 or h
highlight an option (h selects 10, Help), and Enter activates it; q exits immediately. Limited terminals
use numbered line input. Windows smaller than 100 columns × 34 rows also use
numbered input and normal scrollback so full status remains available instead
of scrolling off the alternate screen. Enlarging then reopening restores arrows. With redirected input or output, no arguments prints usage instead. `--help` and named commands retain their direct behavior.

After a manual clone into a new directory, bare `xplanet.sh` is the interactive
front door. Direct `install` provisions Xplanet/Python and continues to setup;
`setup` prepares configuration/data/schedules using existing prerequisites.
Neither means overwriting or cloning over an existing checkout.

Guided install/setup checks prerequisites only when selected. It proposes missing
Homebrew installations before asking for approval; Homebrew itself must already
be installed. Compatible Python 3.11+ interpreters and `TOTALMARKER_PYTHON` remain
supported. [Advanced Python](python-runtime.md) offers an explicit later change between Homebrew
(recommended) and uv-managed Python, with explicit provisioning and save confirmation.
Existing scheduled interpreter overrides are preserved; see that page before switching.

Configuration-file presence distinguishes new, partial and existing installations;
this is not a readiness or health check. Shell-style executable definitions are
left for setup to validate rather than evaluated while opening management.
Existing configurations are not automatically reinstalled. Setup retains its
confirmations for preparation, live refresh and the selected automation bundle
(login, monthly map, quake and storm; volcano only with a configured source and
clouds only when selected). It leaves registered jobs alone.
Only after setup completes does management offer an explicit desktop start.
Cancelling/stopping setup returns directly to the menu. After completed setup
and the optional start offer, new/partial flows acknowledge the summary and exit; existing installations
return to management. macOS may require approval for an installed renderer;
review such prompts yourself.

`config` opens the separate [scene studio](configurator/user-guide.md). Prepare
its isolated dependencies explicitly; missing prerequisites leave management usable.
Saving, [selecting for next start](configurator/apply-design.md) and restarting are
separate actions. Closing or interrupting the editor does not roll back completed
saves/selections; see [exit and recovery](configurator/recovery.md). Management
retains installation, schedules and desktop lifecycle.

Setup's apply-mode exit status is explicit: **0 completed**, **3 cancelled or
stopped**, **1 failed core steps**, **2 invalid setup or ended input**. Exit 3 is
an intentional change from the previous cancellation status of 0, including
when setup is reached through install/bootstrap. Early cancellation prepares
nothing; stopping after configuration review retains preparation already done.
`setup --check` still uses 1 for preparation needed and 0 for ready;
`setup --dry-run` uses 0 for a successful inspection.

When `config/totalmarker.toml` is absent, saved health shows a setup hint without
starting Python or creating configuration. Update explains when
this checkout lacks a remote-tracking upstream before asking for confirmation.
The direct update command retains all of its validation and race checks.
Health exit 1 means the assessment completed and found source issues; management
shows an Issues result. Execution/configuration failures remain errors. Terminal
source names use green for current, yellow for stale/uncertain, red for recorded
failure, neutral for unassessed freshness with valid output, and dim for disabled.
Text labels remain authoritative; JSON and nonterminal output have no colors.

Management delegates start, stop, restart, update and saved health to the existing
commands. It confirms lifecycle/update actions; stop removes the managed desktop
job and stops this user's normal/configured renderer processes, including finite
renders, and restart performs that same stop first.
The foreground launchd renderer has no automatic respawn after intentional stop.

The screen separates desktop process/job status, next-start selection and saved
data health. Opening management assesses saved health once, locally, with a
five-second budget. This may start the selected Python, but never executes
`xp.def`, a renderer, provider refresh or lifecycle command. Missing configuration
shows a setup hint; timeout or inspection failure leaves health unknown.
Choose **Saved health (7)** to retry or inspect details. Navigation and resizing
reuse the dated snapshot; this is not a live access check or polling dashboard.

Setup status indicates file presence, not validated settings. Next-start selection
is separate from the running display: **Running scene: not identified** means the
menu cannot establish which scene is displaying. Start revalidates selected assets
and the executable; invalid selection is not silently replaced with a custom scene.
Opening management does not import the selected scene into the configurator.
See [dashboard implementation](architecture.md#management-dashboard-and-terminal-input)
for the inspection, caching and input contracts.

Desktop facts are read-only: normal `xplanet` process-name detection for the current
user, and registration of `local.xplanet.desktop`. Registration does not establish
that a renderer is running. “Not detected” is neutral, and does not exclude a
custom executable with a different process name; inspection failure says unknown.

Capable terminals keep menus and actions in one alternate screen. Short results
and cancellations return automatically; saved health, completed Python selection,
executed updates, errors and completed setup pause for **any key**. Ctrl-D exits
and Ctrl-C interrupts. There is no timed pause; real decisions still require
confirmation. Direct/noninteractive commands never acquire this pause.

Long output can scroll within the interactive screen, depending on the terminal.
For a complete scrollback transcript, run the corresponding named command directly.
Exiting management restores the original screen and terminal modes. `NO_COLOR`
disables color; limited terminals use plain output. Completion describes the
selected command, not renderer readiness or data health.

Guided setup separates prerequisites, missing dependency installation,
configuration/data/schedules, and optional desktop start with headings and spacing.
Its final summary reports whether setup completed and start was skipped, succeeded
or failed. Cancelling or stopping still retains any preparation already completed.
Installer failures keep their output on screen until acknowledged; direct install
and setup retain their documented exit statuses.

## Desktop commands

Shell `preview` and `render` write replaceable images and renderer scratch beneath
`output/preview/`. Configurator image and comparison-sheet exports instead default
to new named directories under `output/exports/`; those copies are durable and never
automatically pruned. The editor's working previews remain temporary. Existing
exports, including older copies under `config/`, are left in place; native scene
saves still belong to `config/scenes/`. No migration or cleanup is performed.

`setup --help` lists setup modes without inspecting configuration or prerequisites.


With no scene selector, `start` uses `XPLANET_GEOMETRY` from `xp.def` when nonempty;
otherwise Xplanet sizes the desktop automatically. A selected revision uses its
reviewed explicit geometry and scene arguments; invalid selection fails clearly.
The `render` command saves a frame at the configured
dimensions, while `preview` uses a fixed 1920×1080 size. Both render the custom
Earth configuration, not a selected studio revision or unsaved draft. Both use
the checkout as the renderer working directory, matching the custom desktop job;
a same-named resource in the caller directory cannot replace the checkout’s map
or overlay. Use Preview in the configurator for a studio scene. `stop` signals
all current-user processes named `xplanet` or by the trusted configured renderer,
including matching finite renders and other checkouts, and succeeds when none is running.
It does not discover arbitrary executable names from historical scenes. It first removes the managed desktop job.
`restart` performs that same broad stop, then starts one display. Custom-configuration `start`
catches up a configured monthly map; selected scenes retain their reviewed map.
Start asks launchd to run one foreground desktop, without
`RunAtLoad`, `KeepAlive` or automatic respawn after stop. It registers the regular
`~/Library/LaunchAgents/local.xplanet.desktop.plist` file if needed, then explicitly
kickstarts it. No logout or login is required. Repeated start leaves the running
renderer in place; stop unloads it and a later start registers it again. Python runs TotalMarker and the
isolated configurator; lifecycle remains zsh.

An existing desktop registration loaded from `.state/xplanet/desktop.plist`
requires explicit `restart` to migrate to the standard LaunchAgents pathname.
Plain `start` leaves it running and reports that instruction. Restart validates
configuration and destination before stopping; a foreign, linked or edited
same-name plist or unverified loaded job is refused rather than overwritten.
The previous `.state` plist is retained unchanged. Existing file/directory
permissions are preserved, not repaired.

On the first start after upgrading from the old `-fork` launcher, an existing
unmanaged Xplanet process produces a request to use `restart`; setup never kills
it automatically. The existing login trigger stays compatible and can start the
display on a later login. Stopping a display does not disable login automation.
Start reports launchd's acceptance, not proof that the renderer produced an image;
renderer errors go to `logs/xplanet-error.log`. Normal and configured executable
names (including a resolved symlink target) are included in broad stop. Desktop
launch resolves executable symlinks. Unmanaged renderers with names outside this
set are not automatically discovered. Keep the normal `xplanet` executable name
for manual launches; historical scene metadata does not add names to Stop's scope.

## Renderer troubleshooting

For suspected build/support problems, use `scripts/xplanet.sh diagnostics` explicitly;
`diagnostics --show` reads the last evidence without running Xplanet. Before setup,
`diagnostics --renderer /absolute/path/to/xplanet` inspects a deliberate local choice.
See [renderer support evidence and limits](configurator/diagnostics.md#renderer-support-outside-the-studio).
Management's binary line is historical evidence, not a current/running build check.
Setup and normal start do not automatically run this diagnostic. Saved TotalMarker
health describes data sources, not compiled renderer capabilities.

## Help and troubleshooting in management

**9) Troubleshooting...** opens a small submenu. Opening it or highlighting an
option does not read a log, resolve a renderer or run a probe.

- **View renderer log** runs the existing read-only `log-view` command against
  `logs/xplanet-error.log`. Repeated exact resize notices are counted, not removed
  from the original log. An absent log gets a clear message without creating it.
- **View saved renderer support** runs `diagnostics --show`, resolving the current
  choice and reading existing evidence without executing Xplanet. Missing, stale
  or unknown evidence remains distinct from inspection failure.
- **Check renderer support now** asks for confirmation before running `diagnostics`.
  It records private evidence without starting the desktop, refreshing providers
  or changing services. An inconclusive probe reports unknown support, not missing
  features. Cancelling the confirmation returns immediately to the submenu.
- **Back to management** returns to the main screen; `b` is a shortcut. `q` exits
  management from either screen.

All completed reports, including the filtered renderer log, warnings, errors and
missing-log messages, stay visible until **Press any key to continue** is acknowledged.
Only then is the submenu redrawn. Already queued submission newlines do not dismiss
reports. Ctrl-D exits; Ctrl-C interrupts with terminal restoration. There is no
pause added to direct CLI commands. The submenu uses arrow/highlight-and-Enter
navigation in capable terminals and numbered line input in compact/plain terminals.
Scene-specific resource diagnosis remains **Diagnose resources** in Configurator;
renderer support alone does not establish that a scene's files are available.

**10) Help** (h shortcut) displays the same intent-grouped usage as `xplanet.sh --help`: scene
exploration, installation/maintenance, desktop control, data refresh, diagnostics,
housekeeping/development, and unavailable commands. Detailed switches and the
studio guide remain in the linked subcommand help. Help also
uses the existing any-key continuation; Ctrl-D exits and Ctrl-C interrupts
with terminal restoration. Arrows reach both entries; 1–9 and h highlight (h selects Help), Enter
activates. q remains the immediate exit shortcut. Limited terminals accept a numbered
line (10 for Help), or h followed by Enter. Merely opening/highlighting entries performs no probe.

## Concurrent desktop commands

Start, Stop and Restart serialize through a native zsh advisory file lock in the
current user's macOS local runtime directory. The lock is shared across checkouts;
Restart holds it across both broad Stop and Start, so another cooperating command
cannot remove the job between registration and kickstart. Lock acquisition waits
up to ten seconds, then reports busy without changing the job. The kernel releases
the lock when its owning shell exits; the private empty lock file stays in place.
Do not remove held lock files. No PID database, stale-lock deletion, new daemon,
Python lifecycle dependency or automatic renderer respawn is introduced.

This coordinates this version's commands, not arbitrary manual launchctl commands
or older scripts. Concurrent requests execute serially rather than guaranteeing
wall-clock invocation order. A later explicit Start can follow Stop. The original missing-job incident was subsequently reported working, but its
cause was not reproduced. This overlap correction does not prove that incident
resolved; recurring failures still need their exact log and job state.

**Xplanet build** summarizes the last recorded renderer diagnostic. Troubleshooting (9)
can show saved support or capture reported compile-time features and raw `-version`
output; it cannot recover the original compiler command. Menu entry does not probe the renderer.
**Custom setup** only counts `xp.def`, `xp.conf`, `earth` and `totalmarker.toml`;
“existing” means all four are present, not validated. “Configurator: option 2” points
to the editor menu entry, not a scene count. The custom configuration is the default
next-start choice when `config/desktop.scene` is absent.

Restart checks registration in the same GUI domain used for start and stop.
After job removal it waits up to five seconds for that service to disappear;
a removal timeout stops the restart rather than starting against a retiring job.
This is a condition-based wait, not a fixed startup delay.

## Map layout upgrades

After updating a checkout, inspect `scripts/xplanet.sh setup --dry-run`, then
run `scripts/xplanet.sh setup` to review the link relocation. Git pull and the
update command do not run setup automatically.

Bundled maps now live in top-level `maps/`. Solar-system folders use
`SS-BB-name`, for example `03-01-moon` and `06-09-phoebe`. Setup's dry run lists recognized
old `images` links that it can relocate. It changes them only after preparation
is confirmed, preserving their selected month. The normal monthly-map command
can also replace its own exact old seasonal link with the current month in
`maps/`; it refuses unknown old custom targets. Custom regular files and custom
links are never silently replaced. An unsupported old custom link may need a
manual path edit; setup refuses it before preparing files.

Older studio scenes can reopen and preview without rewriting their source.
Save a new copy to emit current `maps/` references, then review/select that copy.
An already selected immutable revision using `assets/maps/` must be reviewed
again from the new copy before starting; no selector or old revision is silently
rewritten. Custom native configs with direct old paths need deliberate edits.

## Saved-health freshness

Health keeps provider access, successful refresh, output integrity and source age
separate. No network request is made by saved health.

- Clouds use source-image creation time and the cloud warning policy.
- Earthquakes use [USGS feed generation time](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php), not the newest event or last fetch.
  The application tolerance is `max(2 × configured refresh interval, 5 minutes)`,
  with at most 60 seconds of future clock skew. This is an application policy,
  not a USGS guarantee. Missing/invalid generation stays unassessed; stale empty
  feeds remain stale. Saved output must match the current quake settings.
- Storms use the saved bulletin-validity endpoint; volcanoes use weekly coverage.
- NORAD reuses the normal cached-TLE checksum, ID and epoch validator with the
  configured maximum age, verified outputs, source settings and icon checks.
  Missing or inconclusive evidence stays unassessed; expired epochs are stale.
- Eclipse predictions show event phase (upcoming, active, ended or unknown) and
  whether the producer's overlay is enabled or hidden. Their age is not treated
  as generic observational freshness, and this does not verify desktop display.
- Disabled sources remain disabled; Santa has no supported live provider.

A recorded refresh failure remains a failure even while retained source data is
recent. Cached success timestamps alone do not prove recent provider access.
Frozen quake captures remain unassessed because their manifest does not retain
the producer's refresh-interval policy; their source generation time is still shown.

## Restart preflight and renderer updates

Restart validates the next command and any immutable selected-scene resources
before stopping the display, including custom monthly-map directories, source and
link prerequisites without changing them, then checks again at start. A new
filesystem change after preflight can still cause start to fail. Invalid selections fail
without falling back to custom settings. If a formula update changes the bound
renderer bytes or path, reopen the saved scene with the updated local renderer,
export/review a fresh handoff and explicitly select it before retrying. Existing
running processes are not stopped merely because that preflight fails; future
starts still require a valid reviewed revision.

Start verifies that an already registered desktop job belongs to this checkout
before requesting it. A different or unreadable job identity requires an explicit
restart/review. Stop removes the managed job, including its selected renderer,
and finds normal current-user Xplanet processes plus explicitly configured names
from the trusted personal `xp.def`. Historical scene argument files never grant
permission to signal unrelated process names. An unmanaged renderer with another
arbitrary executable name needs explicit identification rather than automatic
historical-name discovery.

The optional installation approval frame renders once **to the desktop
background** and may request Finder automation permission. Declining it leaves
that approval for later. Installation requires Homebrew's `trust` subcommand;
if unavailable, update Homebrew through its normal supported procedure rather
than bypassing trust. No particular historical Homebrew version is inferred.

## Checkout size

The bundled map tree is approximately 610 MiB. The reviewed full checkout was
about 1.3 GB on disk including Git objects, with about 0.7 GB of packed history;
these are size observations, not fixed download promises. Network transfer varies
with compression/history, and the private UI runtime, caches and saved scenes add
space. Allow several gigabytes for working headroom. A manual `git clone --depth 1`
reduces downloaded history while retaining the complete current map tree and a
normal remote upstream. Bootstrap keeps its existing clone behavior. Shallow
history is less useful for development and historical comparisons.

## Troubleshooting

- Configurator unavailable: run `scripts/xplanet.sh config --prepare` explicitly
  to prepare its pinned private dependencies; updates never install them silently.
- Missing or changed selected revision: inspect Selected scene / handoff, reopen
  the saved scene and explicitly review/select it again. There is no silent fallback.
- Accepted start without visible wallpaper: inspect `logs/xplanet-error.log` and
  [Finder Automation permission](#finder-automation-permission). Acceptance is
  asynchronous, not proof of a frame.
- Restart reports that `local.xplanet.desktop` was not found: let any in-flight
  lifecycle request finish, then retry `restart` once. Restart uses the stop scope
  above. If it recurs, retain the exact error and desktop log rather than repeatedly
  stopping/starting or assuming the earlier intermittent incident was fixed.
- Source problems: run saved `health` first, then explicitly choose `health --live`
  if provider access should be checked. Retained output is not proof of freshness.

### Finder Automation permission

Xplanet uses Finder to update the desktop. If macOS asks to allow that control,
choose **Allow** for desktop updates. If already authorized, no action is needed.
A `macOS error -1743` warning in `logs/xplanet-error.log` means the Apple event
was not permitted; a rendered image alone does not prove a desktop update.

First open **System Settings > Privacy & Security > Automation** and enable
**Finder** for the sender associated with your Xplanet run. Restart through your
usual launcher and verify an actual desktop update. Terminal-launched and
launchd runs may require separate approvals; check each launch method you use.

If the switch remains stuck, even after reboot, resetting Automation decisions
can allow a fresh approval. **Last resort only:** the following resets the
current user’s Apple Events permissions for **all apps**, not just Xplanet.
Both allows and denials are cleared; other apps and unattended workflows may
need reauthorization before they work again. Pause affected automation first.
Run this yourself in the affected user’s Terminal, **without sudo**, only if you
accept that impact:

```sh
/usr/bin/tccutil reset AppleEvents
```

This does not grant access automatically and is not a guaranteed fix. Restart
Xplanet through its intended launcher in the logged-in desktop session, approve
the expected Finder request, and verify the desktop updates. Review other apps’
permission prompts before resuming their workflows. Do not automate this reset
or substitute the broader `tccutil reset All` command. If denial persists, retain
the exact error, macOS version and launch method rather than repeating resets.

An optional `tccutil` bundle ID identifies the **sending app**, not Finder; do
not guess one for a standalone binary or use `com.apple.finder` to target its
callers. See [Apple’s Automation settings guide](https://support.apple.com/guide/mac-help/mchl07817563/mac)
and `man tccutil` for the settings and reset scope.

## Disable desktop automation

Run `scripts/xplanet.sh stop` to remove the managed desktop job and stop this
user's normal/configured Xplanet processes as described above. This does not remove login/data-refresh LaunchAgents.
Review their named `local.xplanet.*` files in `~/Library/LaunchAgents` and use
macOS's normal job-management tools if disabling them. Preserve custom settings,
saved scenes and data before removing an installation. There is no automatic
uninstall or permission-reset command.


## Xplanet build choices

Before a fresh build, install shows the available features using the same shell
menu style as management. Defaults come from the tap: JPEG, PNG, GIF and TIFF
are enabled; CSPICE, Pango and PNM are optional. PNG remains checked because
macOS wallpaper handoff requires it. FreeType and required build tools are included. This is independent of TotalMarker and the configurator.
Use Up/Down to move, Space to toggle, and Enter on **Continue with these choices**.
On compact terminals, type a feature number to toggle it or press Enter to
continue. **Details** shows the corresponding Homebrew flags. Cancel, Ctrl-C and
Ctrl-D stop before building; prior tap or repository updates may already remain.
The feature choices live in the installed Homebrew receipt, not another project
configuration file.

For unattended installation, choose defaults explicitly:

```sh
./scripts/xplanet.sh install --defaults
```

Or supply exact options from `brew options blogabe/xplanet/xplanet`, for example:

```sh
./scripts/xplanet.sh install --with-cspice --without-giflib
```

These are choices for that invocation, not public defaults. Bootstrap accepts
the same install options and forwards them to the cloned checkout. Noninteractive
install without an explicit choice stops before building. Subsequent setup retains
its own confirmations; these switches do not authorize all setup actions.


During `update`, the installed Homebrew receipt supplies the current choices.
When a changed formula needs a rebuild, the interactive review summarizes them
and offers Continue or Cancel. An unchanged formula needs no confirmation. Explicit
saved options are preserved; features left at defaults follow the current formula. It does
not offer switches that Homebrew would silently retain against the user's choice.
The receipt is checked again after rebuilding, including the old JPEG option
alias and the older all-optional-features shorthand. The formula is only rebuilt
when its recipe changes; unchanged recipes do not restart the display.

Noninteractive `update`, or `update --keep-options`, keeps installed choices.
Changing an existing feature profile remains a direct Homebrew operation; this
workflow does not edit receipts or uninstall a working renderer. Missing receipts,
unknown flags or a renderer from another tap require manual review rather than
silently substituting default features. `setup` can continue to use an existing
renderer without migrating its installation. Binary feature reports are useful
for inspection but do not establish Homebrew provenance or original build flags.

## Aurora

Aurora is a new Xplanet layer, separate from the Perl TotalMarker migration.
It uses NOAA SWPC's [OVATION forecast](https://www.spaceweather.gov/products/aurora-30-minute-forecast)
to draw a subtle green glow with no markers. It is model output, not a local
visibility forecast.

New guided setups enable it when the bundled night map is available and you
choose to register automation. Setup initializes a fallback link offline; the
first scheduled run attempts the forecast. Existing `xp.conf` and TotalMarker
settings are never migrated automatically. To enable it manually, add this to
`config/totalmarker.toml`:

```toml
[aurora]
enabled = true
base_night_map = "maps/lights/earth_lights_4800.tiff"
```

The base can instead be your existing link, for example `images/lights.tiff`.
That link and its original map stay under your control. Keep these paths
inside this checkout. Then:

1. Run `./scripts/xplanet.sh aurora --prepare` to create the fallback link
   without fetching, or `./scripts/xplanet.sh aurora` to try the forecast now.
2. Set `night_map=.state/totalmarker/aurora/night-current` in the Earth section
   of `config/xp.conf`. Restart the existing service once if it is running.
3. Rerun guided setup to install automation, or use the
   [aurora plist example](../scripts/launchd/local.xplanet.aurora.plist.example).
   It checks every five minutes; cloud scheduling and maps are unaffected.

The job validates the complete forecast, produces the overlay and builds
a separate composite from the original base (never from a prior composite).
It switches the renderer's link atomically. Xplanet opens the stable link
on redraw, with its usual day/night fade. The job checks for changes to your
base link before it reuses a composite. If the forecast expires, the next
job invocation selects the original map even if NOAA is unavailable. If the
job is stopped entirely, it cannot clear the last composite automatically.

When desktop update labels are enabled, the Aurora row appears below Clouds.
It shows the saved forecast's expiry: green while current (even if it predicts
no glow), yellow when expired and red when no valid forecast is saved. Aurora
has no separate warning timer. `--overlay-only` does not touch desktop labels.

To turn it off, set `enabled = false` in `[aurora]` and run
`./scripts/xplanet.sh aurora --prepare` to restore the original map without
fetching or restarting. A still-registered job does no network work when
disabled. To stop the scheduled wake-ups too, unload the aurora LaunchAgent
after restoring the original map. Check the shared TotalMarker event log
for `aurora` refresh results and forecast timestamps.
