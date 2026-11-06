# Terminal management

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
(core jobs, with clouds only when enabled). It leaves registered jobs alone.
Only after setup completes does management offer an explicit desktop start.
Cancelling/stopping setup returns directly to the menu. After completed setup
and the optional start offer, new/partial flows acknowledge the summary and exit; existing installations
return to management. macOS may require approval for an installed renderer;
review such prompts yourself.

`config` opens the [scene configurator](configurator/reference.md). It previews temporarily
and saves new native scenes. Explicit reviewed Apply can select an immutable
revision separately from saving and restart; it never changes the running display
or schedules. Completed saves/selections persist when the editor closes. Its
Textual dependencies require explicit isolated preparation. Deliberate configurator
interruptions are reported as interruptions, preserving completed saves/selections;
they are not presented as rollback or command failure. See the [studio exit and
recovery contract](configurator/recovery.md). Missing prerequisites
leave management usable.

Management retains installation, plist generation/registration and lifecycle.
Configurator selection uses the [guarded scene handoff](configurator/apply-design.md);
it is not another installer.

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

The screen separates desktop process/job status, next-start selection and saved data health. It
refreshes status after actions and terminal resizing; there is no polling dashboard.
Navigation repaints only the old and new selected rows. Narrow terminals or missing
cursor capabilities use a full redraw with cached status. Geometry is checked on
the next key after a resize, before repainting; that key is retained across the
full refresh. There is no idle input/status polling. The data-health
area is populated once on standalone interactive entry from saved TotalMarker
state and local output checks. A brief loading message appears first; the menu
worker has a five-second time budget and a bounded disposable capture. Timeout,
missing Python or inspection failure leaves health unknown with a clear retry
hint; it never starts installation, publication recovery or provider access.
Option 7 explicitly repeats the local assessment and shows details. Navigation,
action return and resize use the cached dated snapshot rather than rerunning it.
Current, failed/stale, uncertain and disabled sources retain normal health
semantics. This is saved evidence, never a live access check or refresh.
Direct `health`, `--verbose`, `--json` and explicit `--live` remain unchanged;
`health --dashboard` records are a presentation format, not a diagnostic replacement.
Automatic saved health may start the selected Python; it never executes `xp.def`,
a renderer, provider refresh or lifecycle command. Without a terminal, bare
invocation still prints usage and does not run health. Wide dashboards align
labels and values with horizontal spacing; narrow screens preserve the full text
with compact spacing rather than truncation.
Custom setup status counts files; it does not validate settings. Next-start scene
metadata is hash-checked and labeled separately; assets and the executable are
revalidated only by the start path. Invalid/unavailable selectors are shown as
such, without claiming a custom fallback. **Running scene: not identified** remains
explicit: a registered job or normal Xplanet process cannot establish which scene
is actually displaying. The menu does not execute `xp.def` to guess.
The separate configurator opens chosen samples/saved scenes; opening management
does not automatically discover or import the selected desktop scene.

Desktop facts are read-only: normal `xplanet` process-name detection for the current
user, and registration of `local.xplanet.desktop`. Registration does not establish
that a renderer is running. “Not detected” is neutral, and does not exclude a
custom executable with a different process name; inspection failure says unknown.

Capable terminals keep menus and actions in one alternate screen, using restrained
color and fixed-width ASCII status symbols with text labels. Each action starts
on a clean screen at the top, including its heading, confirmations and output.
Short results and cancellations return automatically. Saved health, completed Python selection, executed updates, errors and completed setup pause for **any key** so details remain readable. Successful new/partial setup acknowledges
its summary before exiting. A persistent last-action result distinguishes
completion, cancellation, unavailable features and errors. Real decisions still
require confirmation; there is no timed pause. The continuation prompt ignores already queued submission newlines; Ctrl-D exits
and Ctrl-C interrupts. No Enter is required. A newly pressed Enter also continues.
Arrow/function-key escape sequences are consumed as one key, with a bounded
50 ms wait per continuation byte; ordinary input never advances on a timer.
Input after the acknowledgement belongs to the next menu choice. Direct/noninteractive
commands never acquire this pause.

Output streams normally without truncation; long operations can scroll within
the interactive screen. Scrollback availability there depends on the terminal.
Use the corresponding named command directly when a complete scrollback transcript
is needed; management does not insert a pager into interactive installer prompts.
Exiting management restores the original terminal screen, rather than adding
action output below previous shell commands.
The menu does not parse provider/installer output or create a new log store.
Completion describes the selected command, not renderer readiness or data health.
Exit, EOF, interruption and fatal errors restore the original screen. The menu makes no persistent terminal-mode changes and does not hide the cursor.
Zsh's single-key read temporarily handles input during key input and
restores the prior terminal modes on exit/interruption. `NO_COLOR` disables
color, including when empty; a missing/dumb terminal or unavailable capabilities
falls back to plain output. No Unicode/emoji support is required.

Guided setup separates prerequisites, missing dependency installation,
configuration/data/schedules, and optional desktop start with headings and spacing.
Its final summary reports whether setup completed and start was skipped, succeeded
or failed. Cancelling or stopping still retains any preparation already completed.
Installer failures keep their output on screen until acknowledged; direct install
and setup retain their documented exit statuses.

## Quick start

1. Install through the [README one-liner](../README.md#install-on-macos), or clone
   into a new directory and run `./scripts/xplanet.sh` for guided management.
2. Follow Guided setup: prepare personal files, choose data sources and review
   the proposed schedules. Keep unconfigured products disabled; cloud access
   needs your source and credentials, and volcano needs an explicit source choice.
3. Accept the optional start offer, or run `./scripts/xplanet.sh start` afterward.
   This asks launchd to run the configured renderer; it does not certify a frame.
4. Expect the desktop image to update asynchronously. If it does not, inspect
   `logs/xplanet-error.log` and Finder automation permission before retrying.
5. Run `./scripts/xplanet.sh health` for saved data status. Only an explicit
   `health --live` checks provider access. Failed refreshes retain older output.
6. To explore scenes independently, run `./scripts/xplanet.sh config --prepare`
   once, then `./scripts/xplanet.sh config`. Saving, selecting and restarting are
   separate actions; the [studio guide](configurator/user-guide.md) explains them.

## Desktop commands

`setup --help` lists setup modes without inspecting configuration or prerequisites.


With no scene selector, `start` uses `XPLANET_GEOMETRY` from `xp.def` when nonempty;
otherwise Xplanet sizes the desktop automatically. A selected revision uses its
reviewed explicit geometry and scene arguments; invalid selection fails clearly.
The `render` command saves a frame at the configured
dimensions, while `preview` uses a fixed 1920×1080 size. Both render the custom
Earth configuration, not a selected studio revision or unsaved draft. Use Preview
in the configurator for a studio scene. `stop` signals
all current-user processes named `xplanet` or by the trusted configured renderer,
including matching finite renders and other checkouts, and succeeds when none is running.
It does not discover arbitrary executable names from historical scenes. It first removes the managed desktop job.
`restart` performs that same broad stop, then starts one display. Custom-configuration `start`
catches up a configured monthly map; selected scenes retain their reviewed map.
Start asks launchd to run one foreground desktop, without
`KeepAlive` or automatic respawn after stop. Python runs TotalMarker and the
isolated configurator; lifecycle remains zsh.

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

## Help and explicit diagnostics in management

**9) Diagnostics** offers confirmation before running the existing selected-renderer
version/support capture. It records private evidence without starting the desktop,
refreshing providers or changing services. A completed but unrecognized/failed probe
reports unknown support; execution/storage problems remain failures. Cancelling the
confirmation runs nothing and returns directly to the menu.

**10) Help** (h shortcut) displays the same intent-grouped usage as `xplanet.sh --help`: scene
exploration, installation/maintenance, desktop control, data refresh, diagnostics,
housekeeping/development, and unavailable commands. Detailed switches and the
studio guide remain in the linked subcommand help. Both long
reports use the existing any-key continuation; Ctrl-D exits and Ctrl-C interrupts
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

**Xplanet build** summarizes the last recorded renderer diagnostic. Diagnostics (9)
shows its reported compile-time features and raw `-version` output; it cannot
recover the original compiler command. Menu entry does not probe the renderer.
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
  macOS Finder automation permission. Acceptance is asynchronous, not proof of a frame.
- Restart reports that `local.xplanet.desktop` was not found: let any in-flight
  lifecycle request finish, then retry `restart` once. Restart uses the stop scope
  above. If it recurs, retain the exact error and desktop log rather than repeatedly
  stopping/starting or assuming the earlier intermittent incident was fixed.
- Source problems: run saved `health` first, then explicitly choose `health --live`
  if provider access should be checked. Retained output is not proof of freshness.

## Disable desktop automation

Run `scripts/xplanet.sh stop` to remove the managed desktop job and stop this
user's normal/configured Xplanet processes as described above. This does not remove login/data-refresh LaunchAgents.
Review their named `local.xplanet.*` files in `~/Library/LaunchAgents` and use
macOS's normal job-management tools if disabling them. Preserve custom settings,
saved scenes and data before removing an installation. There is no automatic
uninstall or permission-reset command.
