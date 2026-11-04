# Terminal management groundwork

Run `scripts/xplanet.sh` without arguments in a terminal to open management.
Opening, leaving or cancelling the menu changes nothing. `q` or EOF exits;
Ctrl-C interrupts. In capable terminals, Up/Down moves the highlight, digits 1–9 or h
highlight an option, and Enter activates it; q exits immediately. Limited terminals
use numbered line input. With redirected input or output, no arguments prints usage instead. `--help` and named commands retain their direct behavior.

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

`config` opens the [scene configurator](configurator.md). It previews temporarily
and saves new native scenes. Explicit reviewed Apply can select an immutable
revision separately from saving and restart; it never changes the running display
or schedules. Completed saves/selections persist when the editor closes. Its
Textual dependencies require explicit isolated preparation. Deliberate configurator
interruptions are reported as interruptions, preserving completed saves/selections;
they are not presented as rollback or command failure. See the [studio exit and
recovery contract](configurator-recovery.md). Missing prerequisites
leave management usable.

Management retains installation, plist generation/registration and lifecycle.
Configurator selection uses the [guarded scene handoff](configurator-apply-design.md);
it is not another installer.

Setup's apply-mode exit status is explicit: **0 completed**, **3 cancelled or
stopped**, **1 failed core steps**, **2 invalid setup or ended input**. Exit 3 is
an intentional change from the previous cancellation status of 0, including
when setup is reached through install/bootstrap. Early cancellation prepares
nothing; stopping after configuration review retains preparation already done.
`setup --check` still uses 1 for preparation needed and 0 for ready;
`setup --dry-run` uses 0 for a successful inspection.

Saved health gives a setup hint when `config/totalmarker.toml` is absent; it does
not create configuration or invoke health automatically. Update explains when
this checkout lacks a remote-tracking upstream before asking for confirmation.
The direct update command retains all of its validation and race checks.
Health exit 1 means the assessment completed and found source issues; management
shows an Issues result. Execution/configuration failures remain errors. Terminal
source names use green for current, yellow for stale/uncertain, red for recorded
failure, neutral for unassessed freshness with valid output, and dim for disabled.
Text labels remain authoritative; JSON and nonterminal output have no colors.

Management delegates start, stop, restart, update and saved health to the existing
commands. It confirms lifecycle/update actions; stop still stops **all** the
current user's Xplanet processes, and restart performs that same stop first.
The foreground launchd renderer has no automatic respawn after intentional stop.

The screen separates desktop process/job status, next-start selection and saved data health. It
refreshes status after actions and terminal resizing; there is no polling dashboard.
Navigation repaints only the old and new selected rows. Narrow terminals or missing
cursor capabilities use a full redraw with cached status. Geometry is checked on
the next key after a resize, before repainting; that key is retained across the
full refresh. There is no idle input/status polling. The data-health
area starts **not checked in this session**. Option 7 explicitly inspects saved
TotalMarker state and caches a dated per-product snapshot in memory. It shows
current, failed/stale, uncertain and disabled sources using the same semantics as
normal health. This is saved evidence, never a live access check or automatic
refresh; select 7 again to refresh. Inspection failure clears the cached snapshot.
Ordinary `health`, `--verbose`, `--json` and explicit `--live` remain available as
direct commands; the compact `health --dashboard` records are a presentation format,
not a replacement for detailed diagnostics.
Opening management never starts Python, fetches feeds or executes configuration.
Legacy setup status counts files; it does not validate settings. Next-start scene
metadata is hash-checked and labeled separately; assets and the executable are
revalidated only by the start path. Invalid/unavailable selectors are shown as
such, without claiming a legacy fallback. **Running scene: not identified** remains
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

## Desktop commands

With no scene selector, `start` uses `XPLANET_GEOMETRY` from `xp.def` when nonempty;
otherwise Xplanet sizes the desktop automatically. A selected revision uses its
reviewed explicit geometry and scene arguments; invalid selection fails clearly.
The legacy `render` command saves a frame at the configured
dimensions, while `preview` uses a fixed 1920×1080 size. `stop` signals
ALL of this user's Xplanet processes, including finite renders and other checkouts,
and succeeds when none is running. It first removes the managed desktop job.
`restart` performs that same broad stop, then starts one display. Legacy `start`
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
launch resolves executable symlinks. macOS name lookup cannot reliably discover
unmanaged, physically renamed binaries with names longer than 19 characters; use
the normal Xplanet binary name for those older manual launches.

## Renderer troubleshooting

For suspected build/support problems, use `scripts/xplanet.sh diagnostics` explicitly;
`diagnostics --show` reads the last evidence without running Xplanet. Before setup,
`diagnostics --renderer /absolute/path/to/xplanet` inspects a deliberate local choice.
See [renderer support evidence and limits](configurator-diagnostics.md#renderer-support-outside-the-studio).
Management's binary line is historical evidence, not a current/running build check.
Setup and normal start do not automatically run this diagnostic. Saved TotalMarker
health describes data sources, not compiled renderer capabilities.

## Help and explicit diagnostics in management

**9) Diagnostics** offers confirmation before running the existing selected-renderer
version/support capture. It records private evidence without starting the desktop,
refreshing providers or changing services. A completed but unrecognized/failed probe
reports unknown support; execution/storage problems remain failures. Cancelling the
confirmation runs nothing and returns directly to the menu.

**h) Help** displays the existing top-level command help and points to
`diagnostics --help`, `config --help` and `config --guide` for details. Both long
reports use the existing any-key continuation; Ctrl-D exits and Ctrl-C interrupts
with terminal restoration. Arrows reach both entries; 1–9 and h highlight, Enter
activates. q remains the immediate exit shortcut. Limited terminals accept a numbered
line or h followed by Enter. Merely opening/highlighting entries performs no probe.

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
wall-clock invocation order. A later explicit Start can follow Stop. The separate
original missing-job incident is not proven resolved by this overlap correction.
