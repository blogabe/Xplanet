# Architecture

`scripts/xplanet.sh` is the stable macOS command interface. It handles standalone
bootstrap before checkout discovery and loads private shell helpers only for the
requested workflow:

- `xp-bootstrap.sh`: acquire a new checkout and invoke install.
- `lib/xplanet/install.zsh`: Homebrew installation and setup handoff.
- `lib/xplanet/update.zsh`: Git fast-forward and formula comparison/rebuild.
- `lib/xplanet/display.zsh`: render, process lifecycle and monthly map selection.
- `lib/xplanet/display_process.py`: private macOS executable/argv/birth identity.
- `lib/xplanet/launchd_registration.py`: bounded literal registration verification.
- `xp-setup.sh`: preserve/prepare personal configuration and launchd jobs.
- `run-totalmarker`: select compatible Python and invoke the data CLI.

Bootstrap and setup remain separately executable alongside `xplanet.sh`. A
complete checkout supplies the private helper files; a downloaded bootstrap entry
does not depend on them. Help, product refreshes and health load no macOS helpers.
The separate Homebrew tap builds upstream Xplanet; this project does not own the
renderer or consolidate its formula patches.

## Data and diagnostics

Python TotalMarker owns provider retrieval, parsing, freshness and output
publication. `features/` orchestrates products; parsers/models validate provider
meaning. `paths.py` constrains I/O to the installation root. `state.py` supplies
shared locking and recoverable publication, including paired marker/arc outputs.
Existing last-good output survives download or validation failure.

`diagnostics.py` projects a common view from existing schema-1 product records:
check, actual client attempt, successful check, publication, source date, coverage
and historical error. New checks persist bounded errors even without event logs.
Labels and health share success-time interpretation; cloud labels still display
embedded image creation time. No configuration migration or duplicate timestamp
snapshot is introduced. Old unknown facts remain unknown.

Health distinguishes a successful unchanged check from new output bytes through
`last_publication_at`. Concise summaries omit historical errors predating success;
`--verbose` includes dated details and publication time. `--json` retains every
field even with `--verbose`. Saved inspection is read-only; live checks reuse
normal validators in disposable roots and preserve normal output/state/timestamps.
NORAD retains its provider cooldown rules; a live probe does not persist a new
cooldown. A process interruption before result-journal publication can lose an
attempt/error fact, except NORAD's existing pre-request cooldown record. The run's
sampled clock identifies an attempt; it is not a per-request network audit trail.

## File ownership

| Area | Owner and lifecycle |
| --- | --- |
| Code, docs, tests, `config/*.example`, launchd examples | Shipped versioned inputs |
| Personal config and `.plist` files | User-owned, preserved by setup, excluded from source |
| `assets/` | Committed static imagery; optional map selection, shipped with the checkout |
| `images/`, `markers/`, `arcs/`, `satellites/` | Generated display inputs; preserve last-good output on failure |
| `.state/totalmarker/state.json` and pending journals | Persistent provenance/recovery, not disposable cache |
| `.state/totalmarker/job.lock` | Installation-local coordination; not a cross-machine sync lock |
| `.state/xplanet/display.json` and `display.lock` | Desktop process identity and crash-releasing lifecycle lock; separate from product journals |
| `.state/totalmarker/storm-rejected.json` | Bounded latest rejected public-source evidence; preserve for diagnosis |
| `logs/` | Diagnostic history; not required for new saved product error facts |
| Preview, test temporary directories, release staging | Disposable development output |

The existing self-contained installation paths remain. Stock maps come from the
installed renderer; seasonal maps use the checkout's committed assets. Packages
must supply the documented map months. The optional local release builder exports
committed source and regular committed assets, excludes local-only files, and
verifies a fresh one-commit candidate before publishing its local manifest. Unknown
local asset files stay ignored; adding a shipped asset requires deliberate `git add -f`
and provenance review. The builder verifies committed asset bytes and modes, not only
working-tree cleanliness.

## Verification boundaries

Offline tests use saved/synthetic HTTP fixtures, temporary roots and stub system
commands. Calendar fixtures use fixed dates and cover all twelve months plus the
same instant in UTC and a non-UTC timezone, preserving host-local month selection.
The normal suite runs in UTC. These tests verify contracts, publication recovery,
source/packaged file boundaries and live-probe isolation; live installation,
Homebrew builds, native process inspection, launchd execution and rendered output
require guest validation. The audit guest exercised native identity/start/restart
and explicit launchd load/rerun on macOS27; this is not a fresh Homebrew build or
login/reboot test. Desktop identity uses macOS executable/argv/start facts; offline
fixtures inject the process API and do not inspect or signal host processes.
Identity is rechecked before SIGTERM; signaling is still PID-based, not an atomic
kernel identity-conditional operation.

The smaller dispatcher improves workflow ownership rather than reducing total
code volume. Native process identity and legacy launchd verification use small
private Python helpers alongside the shell workflows; data policy stays in
TotalMarker. This avoids ambiguous process-string matching and evaluation of
human-readable launchd output. Product-specific validation and setup remain explicit; no provider plugin
framework, configuration migration, GUI or Python-management change is added.
