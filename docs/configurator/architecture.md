# Configurator architecture

The studio edits and renders bounded native Xplanet scenes. `xplanet.sh config`
delegates through zsh and `run-configurator` to `scripts/configurator/`. zsh
owns provisioning and desktop lifecycle; the studio owns drafts, previews and
reviewed native files. TotalMarker is a separate standard-library data producer.
The studio reads existing provider output only during explicit capture.

For controls and actions use the [reference](reference.md) and
[user guide](user-guide.md). This page explains ownership, persistence,
validation and the boundaries shared by those workflows.

## Module map

| Boundary | Owners |
| --- | --- |
| Draft model and camera arguments | `model.py`, `geography.py`, `geometry.py` |
| Native scene storage and preview | `workspace.py`, `library.py`, `fileio.py`, `owned_io.py` |
| Textual presentation and history | `app.py`, feature-specific UI modules, `history.py`, `draft_session.py`, `recovery.py` |
| Renderer identity and resource evidence | `renderer_discovery.py`, `resources.py`, `binary_diagnostics.py`, `resource_diagnostics.py`, `display_geometry.py` |
| Read-only captures and installed resources | `cloud_capture.py`, `observation_capture.py`, `astronomy_capture.py`, `installed_annotations.py`, `installed_icons.py` |
| Inspection and literal copies | `native_inspection.py`, `native_patch.py`, `native_edit_ui.py` |
| Export, exchange and selection | `render_export.py`, `exchange.py`, `handoff.py`, `handoff_cli.py`, `selection.py`, `selection_info.py` |

The studio uses interpreter discovery to prepare its own hash-pinned venv.
Runtime readiness is tied to the actual isolated venv: linked runtime
directories are refused, but a normal base-interpreter symlink within the venv
is supported. See [setup and recovery of that environment](user-guide.md#1-open-the-studio).

<a name="flat-named-scene-library"></a>
<a name="consistent-save-preview-and-exit-evidence"></a>
<a name="bundled-map-path-compatibility"></a>

## Scene storage and publication

A native `.def` and its exact matching `.conf` are the scene record. Bounds
and version declarations determine which associated files can be opened; there
is no sidecar settings store. The loader tokenizes literal paths with `shlex`
without expanding or executing them, and recognizes a generated body only
through exact model regeneration. A document keeps the loaded bytes as an
immutable snapshot, not a watcher. Preview and Save validate that snapshot and
generate from the current draft, so editing appearance does not accidentally
copy the previous body. The unmodified sample body is copied verbatim.

Readers hold a directory descriptor, reject symlinks and non-regular files and
verify metadata and identity across reads. Definitions, body configurations and
geographic annotations are bounded to 16 KiB each; lunar camera rows to
256 bytes; cloud JPEG/metadata to 32 MiB/8 KiB; observation marker/arc text and
metadata to 256 KiB/16 KiB; astronomy text and metadata to 256 KiB/8 KiB.
Supported producer icons are bounded to 1 MiB per PNG. A changed or ambiguous
pair fails before replacing the draft. Reopening adopts neither a recorded
renderer nor a recorded asset root.

`library.py` lists candidates and exclusively publishes named copies.
`config/scenes/<name>.conf`, its peer `.def` and optional files use a validated
common prefix; legacy directory saves use their known unprefixed names. Active
render input uses private-workspace names and does not depend on that storage
prefix. The library has a 1,000-entry preflight limit, not an OS quota against
independent concurrent writes. Browsing reads candidate names and the selected
pair, not the entire library's assets. Stock samples use the same loader but
reside outside the user library; they carry illustrative paths rather than
specific installation paths.

A case-folded reservation coordinates writers. Save creates every output
exclusively and publishes the definition last. Readers check the reservation
before and after descriptor-held reads. On failure, cleanup checks ownership,
identity and a stable byte hash before deleting only unchanged output from
that attempt. An edited file or unfinished reservation stays for inspection.
Open and Save recheck moved/replaced directory paths before reporting success.
These rules protect against accidental concurrent changes; they are not a
sandbox against a hostile writer. See the [scene library workflow](reference.md#scene-library-and-reopening).

The bundled maps use top-level `maps/` and padded solar-system folders.
Recognition accepts only known previous bundled-map spellings within an
otherwise exact body and retains the original input bytes. Preview and new
saves use current names; earlier immutable desktop revisions require a new
reviewed copy. This does not migrate or rewrite existing source files or
selections. Relative config resources are not reliably resolved relative to the
config file by Xplanet: preview supplies explicit private and checkout search
roots, independent of the loader's no-symlink rule.

### Native format compatibility

New copies use v17. The loader still reads the original foundation format and
every version in this table. Older scenes keep their version-specific defaults
and byte checks; pre-v14 previews retain 800×600 when reopened and v14 onward
retain their stored frame size. Open never upgrades files in place.

| Format | Native scene extension |
| --- | --- |
| Foundation / v2 | Reviewed sample pair; v2 explicit camera and time assignments |
| v3 | Monthly map choices, night texture, twilight, grid and scene label |
| v4 | Bounded native place and route lists |
| v5 | Bundled Earth relief, specular and cloud layer settings |
| v6 | Frozen cloud image with provenance |
| v7 | Earth composition: solar hour, observer range and rotation |
| v8 | Explicit Earth, Moon and Mars targets; earlier scenes reopen as Earth |
| v9 | Major-planet textures and shadow brightness |
| v10 | Immutable frozen observation choices and associated assets |
| v11 | Bundled companion textures and a shared moon scale |
| v12 | Bounded parent-relative orbital guides |
| v13 | Individual moon-scale overrides |
| v14 | Bounded output frame geometry |
| v15 | Frozen lunar camera row and frame-centre percentages |
| v16 | Independent astronomy capture associations and a provenance-bound eclipse interval |
| v17 | Scene-owned installed sky/planetary annotations, independent choices and derived-file hashes |

<a name="target-aware-planetary-baseline"></a>
<a name="major-planet-maps"></a>
<a name="textured-satellite-expansion"></a>
<a name="earth-composition"></a>

## Camera and time

`View.issues()` supplies severity-tagged findings and `validate()` rejects
blocking ones. `active_fields()` drives UI availability. Every retained
setting is still validated; hidden invalid text is exposed for correction
instead of discarded. `View.arguments()` emits one active strategy: projected
map or non-projected space view, then geographic/body origin and radius/FOV as
appropriate. Same-body origins are blocked. Round-trip numeric formatting keeps
camera precision on save or prefill. Inactive fields are serializable but do
not change the effective renderer arguments or active preview digest.

Now emits no date override. Fixed UTC uses an aware calendar instant and
Xplanet's GMT `YYYYMMDD.HHMMSS` syntax independent of host local time.
The [planetary guide](planetary.md#time-and-ephemerides) owns date and body
limits. The `MOON_PARENTS` table provides family context rather than an orbit
model. Earth-only imagery and data are not reinterpreted as coordinates for
other bodies. A scene's time does not drive a provider, schedule or lifecycle.

<a name="v11-bounded-system-composition"></a>
<a name="v12-bounded-orbital-guides"></a>
<a name="v13-individual-moon-overrides"></a>

### System framing and orbital guides

Exact regeneration recognizes the complete ordered native system body, not
arbitrary companion sections. The target stays at natural scale because
magnifying it can change radius/FOV behavior. Companions use the effective
shared or individual scale. Xplanet's `magnify=0` still plots a point, so
magnification is not a general hide control. Uniform effective scales preserve
the original system-body format; redundant overrides do not invalidate previews.
Mixed scales use bounded per-body assignments rather than one long line.
`moon_scales_ui.py` stages changes until one validated result can enter history.

Orbital guides emit only on active moon sections, using the fixed
`orbit={-0.5,0.5,5}` sampling. Xplanet's arc renderer samples one extra segment
past the stop; validation pads reviewed longest-moon periods out by whole days
before applying date bounds. Invalid footprints fail before renderer launch.
The [systems](systems.md) and [guide](orbits.md) pages explain the controls and
visual limits.

## Fixed lunar orbital camera

The model owns the distinction between body-centre and lunar-orbital cameras.
Only a Moon origin in space mode and fixed UTC activate the latter. Its single
bounded row uses `-dynamic_origin` rather than `-origin_file`, which can
override frame count. Open checks the regular coordinate file through the
stable descriptor path and requires exact regenerated bytes. Preview stages a
private relative copy. Handoff hashes the associated prefixed path into the
immutable revision and recomputes centre offsets from the reviewed dimensions.
The [lunar camera guide](orbital-camera.md) describes the usable viewpoint.

<a name="earth-appearance"></a>
<a name="local-earth-layers"></a>
<a name="geographic-surface-lists"></a>

## Earth appearance and native annotations

Body generation whitelists monthly/night textures and emits only known native
bump, specular and cloud keys. Files are referenced, not copied. The checkout is
passed as a distinct `-searchdir` argument so spaces in its path do not require
unreliable body-file quoting. `XPLANET_ASSET_ROOT` is a saved reference, never a
lookup root adopted on Open. Resource presence checks do not certify image
contents or engine lookup. See the [Earth layer and asset controls](reference.md#local-earth-layers).

`geography.py` accepts bounded place and surface-arc text, not generic marker or
trajectory syntax. Optional names are fixed; disabled nonempty lists are kept
as native files. The loader verifies stable identity under those scene-local
names and exact regeneration verifies style and enabled references. Preview
stages its own copies and fingerprints active lists. See
[places, labels and routes](reference.md#places-labels-and-routes) for syntax and bounds.

<a name="attempt-scoped-diagnostics-and-selection-inspection"></a>

## Diagnostics and preview evidence

`configuration_issues()` adds read-only checks for renderer path and reviewed
body/assets. It is shared by Health, Preview and Save. Preflight runs no renderer
or network probe. An explicit probe can contribute binary-identity-bound
capability and resource evidence; a missing, failed or truncated report
is unknown. Save does not require the current executable to render a valid
native scene intended for a different build. The
[diagnostics guide](diagnostics.md) owns commands, byte limits and interpretation.

`display_geometry.py` asks the system AppKit bridge once per interactive launch,
with a two-second timeout and a 32-display bound. `convertRectToBacking`, not a
guessed Retina multiplier, supplies backing dimensions. Primary means NSScreen
index 0, not the display containing Terminal. Only blank UI drafts use that size;
saved, recovered, stock and handoff geometry remain explicit.

Preview builds one shell-free argv, private work/home/temp directories and
a finite PNG output. Its subprocess has a 30-second wait budget and an owned
process group. Cleanup signals the group even if its leader exited, kills
remaining members and drains output for at most two additional seconds.
Leader exit and output-pipe closure are separate asyncio protocol events.
Detached descendants are not signaled; a pipe they hold open is annotated
and closed locally. This is supervision of a trusted local executable, not a
sandbox for untrusted binaries. Immediate hard bounds on filesystem stalls or
renderer memory are not implied.

Only successful output promotes the latest/previous pair. Snapshots record
completion UTC, settings, selected executable and identity, an active native
input digest and bounded diagnostics. Arguments, generated body and active
associated-file bytes feed the digest. Stable executable bytes are checked
through each attempt. A changed binary marks the prior image stale and a
mid-render substitution prevents promotion. External libraries, kernels and
arbitrary texture collections are not comprehensively fingerprinted. PNG
signature and available header checks are not a full image decoder. Failures
and cancellations preserve successful images; session files are disposable.

<a name="frozen-current-product-clouds"></a>
<a name="observational-snapshot-boundary"></a>

## Frozen data boundary

Capture workers run trusted code from the current checkout in a private owned
process group. Descriptor-stable reads, product hashes, rechecks of config,
published records, dependencies and pending-journal absence prevent adopting a
mixed publication. Cloud capture allows one bounded race retry. These read-only
adapters do not lock, replay journals or write the producer. TotalMarker
`load_bytes`, cloud age and observational freshness helpers are reused without
calling providers. A producer root or credentials are transient inputs, not
scene provenance.

Cloud JPEG/provenance, observational text/icons and astronomy assets are immutable
scene-owned snapshots. Each supported renderer reference is hash-bound; storm
marker/arc output is indivisible. Observational grammar excludes unknown options,
font and arbitrary file references. Scene prefixing rewrites only recognized icon
references, not labels. Exact supported native associations use bounded, no-follow
reads. The workspace shares a 128 MiB capture-data budget across history instead
of evicting objects still referenced by drafts.

The model owns activation. Earth + Now can use captured weather/observations
and NORAD; NORAD epoch is rechecked and active NORAD is refused by both handoff
and selection. Eclipse is Fixed UTC only within the verified metadata interval.
Static eclipse handoff uses the immutable snapshot and `timewarp0`.
Framing comparisons refuse conversions that would change eligibility.
Inactive choices and verified bytes are retained. Installed annotations are a
separate non-provider import with independent sky/body choices. See
[clouds](cloud-capture.md), [observations](observations.md),
[astronomy](astronomy-capture.md) and [installed annotations](installed-annotations.md).

<a name="preservation-aware-inspection-boundary"></a>
<a name="bounded-native-literal-copies"></a>
<a name="native-copy-byte-review"></a>

## Native inspection and literal copying

`native_inspection.py` takes bounded read-only snapshots and displays escaped
reports. It does not infer arbitrary camera settings or follow unknown
resources. Only fully recognized scenes can be copied with all associated files
and exact source bytes, through the same exclusive directory writer used for
legacy saves. Unknown content is not silently omitted.

`native_patch.py` uses exact byte spans, not a general serializer. It supports
bounded literal numeric, grid and bundled-path edits in one unambiguous body
section; ambiguous inputs are refused or read-only. No-op copies preserve
all bytes. Review and Save regenerate and compare all proposed spans and bytes;
the display abbreviates more than 32 spans but publication uses the complete
set. It rechecks source/directory identity and uses same-directory exclusive
publication. These actions do not populate, preview or Apply an arbitrary draft.
See [inspection](import.md) and [literal copies](native-values.md).

<a name="session-continuity-and-management-evidence"></a>
<a name="responsive-local-inspection-and-exit-review"></a>

## Draft history and change review

`DraftHistory` stores raw draft strings independent of validation or Textual.
The baseline compares finite numeric spelling equivalents without losing their
undo history. Widget restoration suppresses change events before recomputing
validation and preview state. Successful Open resets history and establishes a
local renderer baseline. Save & continue reopens the published copy and advances
the baseline without discarding history or captures. If that reopen fails, the
copy remains an explicit successful write and the draft is retained. A successful
Save does not hide uncertain selection evidence at exit. See
[review and undo](reference.md#change-review-and-undo).

Owned filesystem workers handle native inspection/copy, literal writes, library
and recovery listing, and explicit selection verification. Filtering can reuse
a cached listing; Open verifies the selected pair again. Obsolete results are
discarded. Cancellation waits for the owned worker; an OS call must return before
cooperative cancellation completes. Dirty-exit review asks before stopping active
work. Keep editing preserves the work or its completed result; confirmed exit
awaits cleanup before applying the recovery decision. A published copy survives.

## Private recovery and owned shutdown

`draft_session.py` checkpoints memory after a bounded debounce.
`recovery.py` owns versioned private scratch under
`.state/configurator/drafts`; `recovery_ui.py` presents explicit review.
Records store raw fields, the baseline and verified captures without executing
a definition, restoring renderer choice implicitly or replaying producers or
selection. Schema 2 adds bounded astronomy blobs for current and baseline
capture IDs; exact schema 1 inputs normalize to Off in memory without rewriting
the original. Unknown fields or versions are refused.

A session has an OS ownership lock. A nonblocking store lock protects budget
accounting/publication. New owned assets and manifests are verified before
atomic index replacement; readers can inspect two complete revisions.
Descriptor-stable reads, metadata and hashes are checked. Pruning is limited
to verified obsolete outputs of the same session. Unrecognized bytes are
retained; the 256 MiB aggregate budget refuses new checkpoints instead of
evicting other sessions. Recovery is not a renderer-facing configuration store.

`Workspace.stop` coalesces cleanup; emergency KILL is tracked by actual owned
process, not by repeated key events. SIGINT/TERM/HUP and terminal loss use a
no-prompt route, with handlers restored on unmount. The
[recovery guide](recovery.md) owns the user-facing keys and failure semantics.

## Bounded comparison sets

`comparison.py` uses a subordinate owned workspace for reviewed variants.
For framing variants it fixes Now once and refuses active current-derived
inputs rather than reinterpreting them. It promotes the bounded PNGs, JSON
record and local static HTML sheet together, using the same finite render,
identity and cancellation rules as single previews. Failure keeps the previous
set and ordinary preview history. See [comparison modes](comparisons.md).

## Durable image artifacts

`render_export.py` reads only owned retained snapshots, checks file identity,
PNG geometry and comparison data/hash bindings, then exclusively creates a
new destination. Bounded asynchronous reads allow cancellation before final
synchronous publication; no detached write outlives the editor. Receipts omit
local executable/source paths and raw diagnostics, but retained image metadata
can still be private. See the [export guide](export.md).

## Scene exchange boundary

`exchange.py` is a standard-library data path separate from Apply. It normalizes
recognized generated scenes with fixed portable placeholders, hashes bounded
stored-ZIP members and validates a private staging copy before exclusive
publication. Import rebinds the local renderer and asset root, never runs the
archive or selects a scene. Optional PNGs are stripped of ancillary metadata
and bounded as pixel streams. Exchange v1 refuses frozen provider captures.
The UI uses an owned stdlib process; importing a copy and opting to Open it are
separate actions. See [scene exchange](exchange.md) for command and data limits.

<a name="review-only-handoff-export"></a>

## Handoff and selected desktop

`handoff.py` builds an immutable review plan from recognized saved files,
opaque custom-config hashes, an explicit local renderer/geometry and selected
resources. Rechecks reconstruct expected data rather than trusting manifest
arguments or paths. Export writes a new private snapshot, manifest last, with
owned-file cleanup; altered partial output is retained. A plan is not a
filesystem-wide snapshot, authenticated signature or active selector. The
stdlib check mode exits before normal setup and does not invoke an executable.

`selection.py` separately publishes immutable revisions in
`.state/xplanet/scenes` and updates the `config/desktop.scene` reference.
`scene.zsh` verifies hashes and consumes literal argv without Python or sourced
generated definitions. Selected execution uses the revision as cwd and private
desktop scratch, not renderer writes into the immutable directory. Restoring is
guarded and reference-only; ambiguous publication requires inspection. The
management dashboard and explicit selection inspection report the next start,
not the currently running scene. See the [Apply workflow](apply-design.md) and
[management dashboard contract](../architecture.md#management-dashboard-and-terminal-input).

## Engine facts carried into the design

- A projection renders one body and suppresses certain space options, including
  visible Saturn rings. Orthographic is still projected. Space views may show
  incidental bodies.
- TotalMarker produces files; a renderer config must separately refer to them.
  Saved freshness labels do not prove current provider access.
- Multiple native assignments on a line and repeated marker/arc/satellite
  entries are meaningful. `[default]` order changes inheritance. Later scalars
  override earlier ones while file lists append. Generated lines stay short for
  the 256-byte buffer in Xplanet 1.3.1.
- Longitude/local solar hour and origin strategies interact with argument
  order. Non-interpolated origin playback can override `num_times`.
- PNG, image codecs, fonts, SPICE and platform output depend on the binary and
  available resources. A finite render verifies execution, not accuracy.

Sources: [upstream documentation](https://xplanet.sourceforge.net/documentation.php.html),
[manual](https://xplanet.sourceforge.net/README),
[configuration](https://xplanet.sourceforge.net/README.config),
[FAQ](https://xplanet.sourceforge.net/FAQ.php.html) and
[1.3.1 source](https://sourceforge.net/projects/xplanet/files/xplanet/1.3.1/).

## Verification

The [test guide](../../tests/README.md) owns suite commands and coverage. Core
tests use disposable workspaces without Textual; UI interaction tests prepare
their pinned environment separately. Headless interaction and finite-render
checks do not verify actual wallpaper, fresh login or live providers.
