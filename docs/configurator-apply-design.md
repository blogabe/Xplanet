# Named-scene Apply and recovery

Save, selection and restart are separate actions. **Apply selects a reviewed,
immutable named-scene revision for the next desktop start/restart.** It never
starts/stops a renderer, registers jobs, refreshes providers or replaces personal
`xp.def`/`xp.conf`. An already running display remains unchanged. `start` stays
idempotent; explicitly restart when ready to replace a running display.

## Review, export and select

In **Handoff review…**, choose a saved named scene from this checkout's
`config/scenes`, an explicit local renderer, intended `WIDTHxHEIGHT`, and a new
export directory in an existing parent. **Review export** only reads/hashes;
**Confirm new export** creates a private review bundle. The dialog uses saved
files on disk, not unsaved editor changes. Save those as a new scene first if
needed. Opening/reviewing/closing preserves the draft and source files.

**Check existing bundle** verifies the directory field using its recorded choices,
not the other fields. **Review Apply** shows the verified bundle and current
selection; **Confirm selection** explicitly publishes/selects its immutable
revision. Changed inputs or selection require review again. No operation in this
dialog restarts the desktop. Closing after a confirmed selection retains it;
closing or cancelling is not an implicit undo.

The same operations work without Textual/TTY through the selected Python 3.11+:

```sh
./scripts/xplanet.sh config --export-handoff /absolute/new-review-directory \
  --view /absolute/checkout/config/scenes/lunar.conf \
  --renderer /absolute/path/to/xplanet --geometry 1920x1080
./scripts/xplanet.sh setup --check-handoff /absolute/new-review-directory
./scripts/xplanet.sh config --show-selection
./scripts/xplanet.sh config --apply-handoff /absolute/new-review-directory \
  --expect-selected legacy
```

For an existing selection, use the exact current revision ID instead of `legacy`.
A wrong/missing expectation refuses the change. These commands install nothing;
`setup --check-handoff` returns before normal setup or legacy execution. Restart is
an independent management/CLI action, with its existing broad Stop contract.

## Ownership and defaults

`config/desktop.scene` is a small literal versioned revision reference.
`.state/xplanet/scenes/<revision-id>/` contains private native/captured files,
a native XML `deployment.plist`, literal `desktop.args` and `checks.tsv`.
The revision ID hashes the manifest, which binds arguments and resource checks.
Tool-managed revisions are never edited or overwritten; old revisions are retained.
They remain ordinary user-owned files, not filesystem-enforced immutable objects.
No automatic retention cleanup, symlink selection or shell evaluation is used.

No selector means the existing legacy desktop path, including monthly-map
catch-up. An invalid selector or damaged selected revision fails clearly; it never
silently falls back. The scene-aware desktop path remains zsh-only, using native
`plutil`, `stat` and `shasum`. It passes literal argv and does not source generated
studio definitions. Lifecycle never needs the configurator's Python environment.
Selected rendering uses the revision as its working directory so checkout files
cannot shadow frozen relative resources. The launcher adds a fixed private
`-tmpdir` at `.state/xplanet/desktop-tmp`, outside the revision; linked scratch
directories are refused. Operational temporary output is not scene configuration.
Existing personal legacy definitions retain their intentional shell semantics,
including existing Stop/process-name discovery; Apply itself never executes them.

The reviewed local executable and explicit geometry belong to this deployment;
saved foreign executable choices are not adopted. Moving the checkout or changing
the renderer/resources requires fresh review. No automatic monitor detection or
reinterpretation of a scene's camera occurs. A preview at any dimensions does not
certify another aspect ratio. `preview`/`render` legacy CLI commands remain separate
from the studio/selected desktop workflow.

Library edits do not change a selected revision. Captured observations remain
frozen; Now advances geometry, not the captured data. Fixed UTC uses `-timewarp 0`.
Monthly jobs keep their existing legacy purpose and do not rotate a selected
seasonal map. Producer schedules/state are not changed or rolled back.

## Integrity and resource limits

Export/check binds source identities, selected asset hashes, local renderer and
opaque legacy baseline hashes, including absence. Definitions are known literal
data, never sourced by review. Changed source identity, even metadata-only changes,
invalidates an unapplied review. Setup-created baselines require re-export afterward.

Apply rechecks the review, freezes native/captured bytes and changes only the
selector. Subsequent validation uses the frozen revision, not editable library
sources or legacy baseline hashes. Selected bundled assets remain hash-bound
references, avoiding another large copy. Startup verifies manifest/argument/native/
asset/renderer bytes with bounded reads before constructing the command.

Stock texture lookups are disclosed as unresolved; incidental-body textures, fonts
and compiled resources are not comprehensively bound. Hashes do not certify image
decoding, executable identity as Xplanet, desktop capability or astronomical
accuracy. This is local path-bound integrity, not authenticated scene sharing or
protection against a hostile same-user process continuously rewriting files.
Hashing bounded large assets can take time. Bundles/revisions can contain local
paths and frozen observation metadata; review before sharing. Nothing is uploaded.

## Restore and failures

Within the dialog, **Review previous selection** then **Confirm previous selection**
restores only the preceding reference, and only if the current selector still
matches the completed change. It does not restore assets, legacy files, schedules
or producer state. A prior revision must still validate. This single undo receipt
lasts for the dialog session; there is no automatic crash-replay journal.

Outside that session, explicitly select a retained revision or return to legacy:

```sh
./scripts/xplanet.sh config --select-revision PREVIOUS_ID --expect-selected CURRENT_ID
./scripts/xplanet.sh config --use-legacy --expect-selected CURRENT_ID
```

Selection changes use a cooperative lock and identity checks. Existing locks are
not discarded. A failed pre-publication change preserves the previous selector;
changed temporary material is retained. Revisions staged before a later failure
remain unselected for inspection, never force-deleted. An uncertain publication
returns a distinct error (CLI exit 5): inspect the selector before retrying. No
automatic rollback can overwrite a newer choice. Invalid selector repair requires
manual inspection; no force/bypass option is provided.

A failed later start/restart does not undo a selection automatically. Restore a
known reference deliberately after diagnosis. Legacy files and last-good producer
outputs are never part of this recovery operation.

## Validation scope

Fixture tests cover immutable snapshots, no-op/repeated selection, old/new revision
restoration, concurrent edits, symlinks, corrupted files, pending material, locks,
write/interrupt boundaries and uncertain outcomes. Native zsh tests construct args
without Python or live services; finite isolated renders exercise those arguments.
UI/PTY tests cover confirmation/cancellation and terminal restoration. These are
not host deployment, visible UTM, actual launchd activation, login/reboot or a fresh
installation test of this new selected-scene path.

## Inspect the next selected scene

**Selected scene…** in the studio explicitly verifies the selector, immutable
native snapshot and known resource hashes. It distinguishes reviewed desktop
geometry from stored preview geometry and shows frozen input provenance. Refresh
is manual. Invalid selection is an error, never an assumed legacy fallback.
**Open native scene as draft** replaces the editor only when requested, retains
the local renderer and saves future changes as a new library copy. It does not
modify the revision or selector. With no selector, the inspector reports the
legacy default without reading or executing personal definitions.

The CLI equivalent is `xplanet.sh config --show-selection`. Both describe the
next explicit start/restart; neither inspects the running desktop.
