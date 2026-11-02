# Terminal management groundwork

Run `scripts/xplanet.sh` without arguments in a terminal to open management.
Opening, leaving or cancelling the menu changes nothing. `q` or EOF exits;
Ctrl-C interrupts. In capable terminals, Up/Down moves the highlight, digits 1–8
highlight an option, and Enter activates it; q exits immediately. Limited terminals
use numbered line input. With redirected input or output, no arguments prints usage instead. `--help` and named commands retain their direct behavior.

Guided install/setup checks prerequisites only when selected. It proposes missing
Homebrew installations before asking for approval; Homebrew itself must already
be installed. Compatible Python 3.11+ interpreters and `TOTALMARKER_PYTHON` remain
supported. Python runtime information explains the recommended Homebrew default;
uv remains deferred, with no selectable implementation.

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

`config` is deliberately a placeholder. Setup also shows this handoff before
manual configuration review. It saves and applies nothing and reports
`configuration_result=deferred` to its caller. Setup preparation can still finish;
that does not mean the future configurator has completed. Continue using the
existing configuration files and setup prompts.

The future configurator can navigate settings nonlinearly, validate/preview and
save or cancel proposed settings. Management will own applying settings, generating
and registering plists, and lifecycle. There is no additional configuration store,
provider framework or dashboard in this groundwork.

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

Management delegates start, stop, restart, update and saved health to the existing
commands. It confirms lifecycle/update actions; stop still stops **all** the
current user's Xplanet processes, and restart performs that same stop first.
The foreground launchd renderer has no automatic respawn after intentional stop.

The screen separates desktop status, data health and active configuration. It
refreshes status after actions and terminal resizing; there is no polling dashboard.
Navigation repaints only the old and new selected rows. Narrow terminals or missing
cursor capabilities use a full redraw with cached status. Geometry is checked on
the next key after a resize, before repainting; that key is retained across the
full refresh. There is no idle input/status polling. The data-health
area is explicitly a placeholder, with saved health available through option 7.
Opening management never starts Python, fetches feeds or executes configuration.
Configuration status counts files; it does not validate or display active settings.
The configurator remains a separate, unimplemented editing flow.

Desktop facts are read-only: normal `xplanet` process-name detection for the current
user, and registration of `local.xplanet.desktop`. Registration does not establish
that a renderer is running. “Not detected” is neutral, and does not exclude a
custom executable with a different process name; inspection failure says unknown.

Capable terminals keep menus and actions in one alternate screen, using restrained
color and fixed-width ASCII status symbols with text labels. Each action starts
on a clean screen at the top, including its heading, confirmations and output.
Short results and cancellations return automatically. Saved health, Python runtime
information, executed updates, errors and completed setup pause for **any key** so details remain readable. Successful new/partial setup acknowledges
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
