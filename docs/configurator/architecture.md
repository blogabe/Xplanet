# Configurator architecture

`xplanet.sh config` delegates through a small zsh helper and `run-configurator`
to the independent `scripts/configurator/` module. `model.py` owns the constrained
sample/camera validation, `workspace.py` owns bounded saved-view loading, finite preview and explicit save,
`history.py` owns bounded raw draft snapshots and baseline comparisons, and
`app.py` owns Textual presentation. The optional cloud-capture adapter reuses TotalMarker’s read-only config, image,
state, diagnostic and freshness helpers; it never invokes a provider runner.
It reuses interpreter discovery only to prepare its own pinned isolated venv.
Shell provisioning and desktop lifecycle remain zsh; TotalMarker remains stdlib-only.

The model recognizes a reviewed Earth sample plus constrained appearance, surface annotation
and local-layer settings; no generic INI parser or arbitrary shell importer is used. The default
body is copied verbatim. Other appearance choices regenerate one exact native
body format; comments/order in unrelated or edited configs are not promised to
round-trip because those files are refused rather than normalized.

Saved-view loading reads literal fields then requires exact regeneration of a
versioned xp.def and matching xp.conf. `shlex` tokenizes literal paths without
expansion or execution. V8 adds explicit target; V7 adds composition. V6 adds a bounded frozen cloud asset and provenance; V5 adds whitelisted bundled layer settings; V4 adds bounded native surface
annotation files; V3 adds map family/month, night texture, whole-degree
twilight, grid and label; v2 camera/time and original foundation pairs remain
explicit recognition cases with appearance defaults. V14 stores bounded preview geometry; V15 adds an optional frozen lunar camera row and frame-centre percentages; V16 adds independent astronomy capture associations and a provenance-bound eclipse interval. New copies use v17 with bounded scene-owned installed annotation files, independent sky/body choices and derived-file hashes. Pre-v14 scenes retain 800×600; v14 preserves its stored dimensions. Saved
executables and asset roots are never adopted by the UI. Native files stay the
scene record; there is no sidecar settings store.

The loader opens real files through a directory descriptor, refuses symlinks and
non-regular inputs, and bounds each declared file by its type: definitions/body/
geographic annotations to 16 KiB, lunar camera rows to 256 bytes, cloud JPEG to
32 MiB with 8 KiB metadata, observation marker/arc text to 256 KiB with 16 KiB
metadata, and astronomy text to 256 KiB with 8 KiB metadata. Supported captured
PNG icons are capped at 1 MiB each; accumulated capture history is bounded to
128 MiB. File identity/metadata are checked across each read, including optional
associated files. A changed or ambiguous pair fails without replacing the draft.
The immutable document retains loaded body bytes as a recognized source snapshot,
not a watcher. Preview/save validate that source format, then generate the current
draft’s body; revised appearance never accidentally copies an older source body. Later source edits are preserved, and saving always
creates a new named pair or legacy directory. No sidecar configuration store is introduced.

Preview builds an argv list without a shell, supplies explicit config/search/output
paths, a private working/home/temp directory and one PNG frame. The sample has no
command hooks, trajectories, provider fetches or live product references. A bounded
error tail is displayed; the subprocess gets a 30-second deadline and its own
process group for cancellation. Cleanup signals the group even if its leader has
already exited, then kills any remaining group members before removing attempt
files. Leader exit and output-pipe closure are separate public asyncio protocol
events, including on Python 3.11. Output drains for at most two further seconds;
an inherited pipe held open by an escaped descendant is annotated and closed on
the parent side. Descendants that detach into another session remain outside
process-group control; they are not signaled.
Its temporary files are cleaned on exit. This is
controlled rendering, not a sandbox for untrusted executable binaries or arbitrary
imported recipes. Saving requires confirmation and exclusive creation of a new
native config pair through an opened parent directory; it cannot overwrite an
existing destination. There is no automatic activation.

Setup continues to own preparation, installation and job registration. Explicit
named-scene Apply stages a derived immutable deployment and changes only a
reference; it never invokes setup or lifecycle. The editor still saves native
scene files as its configuration truth, not a parallel service/configuration engine.

## Diagnostics and preview evidence

`View.issues()` is the central severity-tagged rule set; `validate()` rejects its
blocking findings. `active_fields()` drives UI availability. Draft conversion
keeps invalid text for diagnostics, and inactive invalid fields are exposed for
correction. The UI never clears settings when hiding controls. The shared
`configuration_issues()` adds read-only renderer-path and reviewed-body checks for
Health, Preview and Save. Asset/build lookup remains explicitly unverified by
this preflight; no process or network probe runs merely to show health.

Preview state is session-local evidence, separate from the draft and TotalMarker
state. A frozen snapshot records settings, selected renderer, active render-input digest,
completion UTC, path and bounded renderer diagnostics. Successful output alone
advances the latest/previous pair. Failed, timed-out or cancelled attempts retain
both, stop the owned subprocess and clean their private attempt directory. The
third success drops only the oldest disposable snapshot. Closing the editor
cleans the entire workspace; this is not a persistent cache or recovery journal.

Staleness compares active renderer arguments, selected executable path and body
and active annotation-file bytes, plus the recorded executable file identity. Rendering
checks stable executable bytes across each attempt; later metadata changes mark a
retained image stale. External texture collections, linked libraries and kernels
are not comprehensively fingerprinted. A Now image is a captured instant even when settings
match. Before/after inspection uses the two recorded successful scenes and explicit
viewer actions, without auto-compositing, pixel alignment or new image packages.
The output check uses process status, file presence and a PNG signature; it is
not a complete image decoder or a sandbox for an arbitrary renderer binary.

## Camera and time

Targets include Earth, the other major planets, supported moons and system views; see [planetary support](planetary.md). `View.arguments()` emits one coherent active strategy:
projected maps use geographic coordinates and omit space framing; non-projected
space views use geographic coordinates or a body origin, with radius or FOV.
The model retains inactive choices instead of clearing them on mode switches.
A round-trip numeric formatter avoids losing camera precision when saving or
prefilling widgets. Every retained field is validated so a saved scene can reopen.

Now emits no date override. Fixed UTC is parsed as an aware calendar instant and
encoded to the engine's GMT `YYYYMMDD.HHMMSS` syntax without using host-local time.
The studio bounds fixed dates to 1800–2200; Pluto/Charon geometry has a narrower 1800–2099 range. Framing also has documented UI limits;
these are product limits, not universal engine limits or accuracy guarantees.
The default low-precision source (`EphemerisLow.cpp` in Xplanet 1.3.1) discusses
that interval, but this project does not certify astronomical accuracy. No label,
producer, schedule or lifecycle setting follows implicitly from scene time.

V2 uses explicit studio assignments to native xp.def. The custom desktop
path does not interpret these richer assignments. Named-scene Apply produces
literal reviewed deployment arguments for a separate zsh path, leaving legacy
files/default behavior intact. Save remains no-overwrite scene publication;
selection and restart are distinct operations.

## Earth appearance

The model whitelists three 12-month families and one bundled night image.
Native body values use relative `maps/...` names without spaces; preview
passes the current checkout through a separate argv `-searchdir`, so checkout
paths with spaces do not require unsupported quoting in the engine’s body parser.
Saved `XPLANET_ASSET_ROOT` is a quoted reference only: reopening reconstructs
settings without reading from that path, and runtime resolves the current checkout.

Health checks selected bundled files are regular and present, then reports exact
requested paths. It does not decode images, fingerprint external changes, certify
provenance or guarantee which stock file the renderer resolves. All 36 monthly
references have fixtures. No dynamic provider is invoked.

`twilight` is a whole-degree engine range 0–90; night texture selection is separate.
`shade` is intentionally not presented as night-image brightness because it only
applies when the night map cannot be found. Grid presets translate 30/15/10-degree
major spacing and 1-degree dots into positive `grid1`/`grid2` divisors. Optional
`-gmtlabel` follows scene time and renderer font support, not observation freshness.

## Frozen current-product clouds

See the [capture guide](cloud-capture.md) for policy and limits.
The scene records a capture identity, while immutable `FrozenCloud` data binds
allowlisted provenance to its JPEG hash. Native cloud-capture.jpg/json are owned
scene assets, not another provider/configuration store. Source root/config inputs
are transient and never restored from an imported scene.

Capture is explicit and uses this checkout’s trusted worker code in a private
process group, not code from a selected producer root. Read-only descriptor
checks, state hash binding, config/product-state rechecks and journal absence
avoid accepting a mixed publication; one bounded race retry is allowed. No
RootFS.lock, provider call, journal replay or source write occurs. The worker
wait/cancellation lifecycle reaps owned work before attempt cleanup.

TotalMarker exposes `load_bytes` so one stable config snapshot is parsed without
a second read, and `cloud_freshness` shares its existing age policy. Neither
changes producer configuration, network behavior, state schema or CLI contracts.
Normal menu/status display does not read a producer; only confirmed Capture does.

The workspace retains immutable captures by identity under a 128 MiB image-data
budget, preserving undo rather than evicting referenced assets. Successful Open
resets draft history/captures; rendered before/after PNGs and their small provenance
remain session evidence. Preview copies only active captured bytes into its own
work directory. Its digest includes capture identity. Fixed UTC does not use
current-derived capture data or update labels; choices/assets are retained. The
2011 static texture, geographic annotations and UTC scene label are distinct.

V6 loading reads only fixed declared image/provenance names with separate byte
bounds, stable descriptor identity and exact validated metadata/hash binding.
Missing/tampered assets fail without replacing the draft. Old v5/v4/v3/v2 and
foundation scenes retain their defined defaults and do not acquire source reads.
A malformed provenance structure becomes a bounded validation error, not a UI
traceback. JPEG metadata is not stripped and full pixel decoding is not claimed.

## Local Earth layers

The model maps explicit layer choices to fixed bundled filenames for GEBCO relief,
specular reflection and the archived 2011 cloud image. Body generation emits only
known keys: bump_map/scale and optional bump_shade, specular_map, and cloud_map/
gamma/threshold. There is no arbitrary external image-path importer or provider
command. Shared validation bounds numerical inputs (including retained inactive
ones); active_fields drives contextual controls and history preserves all choices.

V5 records switches and retained parameters in native definitions. Exact body
regeneration plus whitelisted resource checks keep Save/Preview/Health consistent.
V4 optional geographic files are still opened safely; old scenes get disabled
layer defaults. Active layer changes affect the render digest, inactive parameter
changes do not. Bundled-layer selection itself adds no image copies, dependencies, producer
state or sidecar settings truth. Explicit frozen capture is described separately.

The cloud image’s archival date is distinct from scene time and source freshness.
A bundled display choice is not a TotalMarker fetch or proof of current access.
High-resolution bump/specular maps may use substantial decoder memory; the
existing finite process deadline/cancellation and prior-output retention remain
in force, without claiming a hard memory cap or automatic image reduction.

## Geographic surface lists

`geography.py` validates two narrow native row grammars: surface lat/lon with a
quoted label, or two surface endpoints for an arc. It bounds rows, bytes, labels
and coordinates, and refuses option tails, control characters, quotes/backslashes
in labels and arbitrary file references. It does not execute or generally import
Xplanet marker/arc syntax. Raw validated text/order is the native data record,
not an additional JSON store or a lossy converted coordinate list.

V4 declares only fixed optional `places.markers` / `routes.arcs` filenames in
xp.def, while native xp.conf references enabled layers. Disabled nonempty lists
are saved for lossless reopening; empty disabled lists need no extra file. The
loader recognizes literal declarations, opens only those fixed scene-relative
regular files with descriptor/no-follow checks, bounds them and checks identity
with the other inputs. Exact regeneration validates switches/styles/references;
older v3/v2/foundation scenes get empty disabled lists. No source-selected path
can redirect annotation loading. Save cleanup covers failures in auxiliary writes.

Preview stages its own native files and fingerprints active annotation data as
well as the body. Hidden inactive changes remain dirty/undoable but do not make
an otherwise matching rendered scene stale. Labels depend on fonts and visibility;
arcs are static great circles, not trajectories, geocoding or eclipse computation.
TotalMarker remains a separate producer; these files never overwrite its outputs.

## Draft history and change review

`DraftHistory` is a small, UI-independent session history. It copies raw string
fields so invalid intermediate edits and inactive settings survive undo/redo,
without asking model validation to accept them. Numeric comparison treats finite
formatting equivalents as unchanged; raw snapshots still preserve the text.
History has at most 100 undo steps, a separate baseline, explicit typing groups
and branch truncation after edits following Undo. It has no disk persistence.

Textual captures edits, breaks typing groups on blur, and restores widgets with
change messages suppressed so undo does not create another edit. Model validation,
availability and preview staleness are then recomputed by the existing paths.
Priority editor bindings own Ctrl-Z/Y; modal review/confirmation screens prevent
draft undo beneath a captured review. Only successful Open resets the baseline
and history; loaded executables remain unadopted and the current local selection
becomes the new executable baseline. Save-as-new/cancel retain their existing
publication boundaries. Destination paths are not scene history.

Change review is a field-level comparison with the session snapshot, including
retained inactive choices and local renderer edits. It is not an arbitrary source
parser, native-file merger, file watcher, recovery journal or Apply plan. Saving
still writes the supported exact native format only; source files stay untouched.

## Engine facts carried into the design

These constraints were checked against Xplanet 1.3.1 documentation and source;
they guide future controls rather than imply that all features are implemented.

- **Scene mode:** an explicit projection renders one body, suppresses FOV/sky
  overlay behavior and Saturn's rings. Non-projected space views can contain
  multiple bodies. Orthographic projection is still projected mode.
- **Producer versus display:** TotalMarker creates files; Xplanet must separately
  reference those files in the appropriate body section. Neither operation
  implies the other, and saved update labels are not proof of current access.
- **Native syntax:** multiple assignments per line and repeated marker/arc/
  satellite entries are meaningful. [default] ordering changes inheritance;
  later scalar settings override earlier ones while file-list entries append.
  The 1.3.1 reader has a 256-byte line buffer; generated lines stay short.
- **Camera/time:** origin-body and geographic controls can select different
  strategies depending on order. Local solar time can override longitude;
  radius and FOV are alternatives. Scene time, label timezone and refresh time
  are distinct. Non-interpolated origin playback can override num_times, so
  arbitrary trajectories are outside the finite-preview contract.
- **Build capabilities:** PNG/image codecs, FreeType/Pango, SPICE and platform
  output support depend on the actual binary. Atmosphere/SPICE/TLE workflows
  need their own resources and date coverage, not merely extra checkboxes.

Primary references: [Xplanet documentation](https://xplanet.sourceforge.net/documentation.php.html),
[manual](https://xplanet.sourceforge.net/README),
[body configuration](https://xplanet.sourceforge.net/README.config),
[FAQ](https://xplanet.sourceforge.net/FAQ.php.html) and the
[1.3.1 source](https://sourceforge.net/projects/xplanet/files/xplanet/1.3.1/).
This project owns a launcher/editor, not the upstream renderer or its numerical
accuracy. Editing and scene selection follow the explicit preservation and Apply contracts
documented below. The studio never executes imported shell definitions.

## Verification

`xplanet.sh test` explicitly loads stdlib modules from `tests/` and
`tests/configurator/`, excluding `ui/` and local scratch directories. The
portable runner shares that module list with explicit macOS exclusions. This
keeps Textual optional. Both runners use private per-run temporary workspaces outside
the checkout so filesystem synchronization cannot alter fixture identities. The stdlib suite covers model, save preservation, subprocess failure,
timeout/cancellation, strict reopening/source preservation and launcher contracts. Headless Textual interactions run
separately with the pinned UI dependencies:

```sh
PYTHONPATH=scripts:. .state/configurator/venv/bin/python -B -m unittest discover -s tests/configurator/ui -v
```

CI prepares a disposable venv rather than installing into the TotalMarker Python.
Native terminal/image output requires disposable macOS guest validation; headless
tests alone do not establish actual wallpaper, login or provider behavior.

## Flat named scene library

`library.py` provides exclusive named saves and bounded candidate listing.
`config/scenes/<name>.conf` pairs with `<name>.def`; native annotation/capture
filenames use the same `<name>.` prefix. The prefix is validated storage
association, not another scene setting. Model serialization accepts that prefix;
rendering uses canonical private-workspace names and preserves the same active
input digest. Exact recognized named body references are normalized only for
preflight, never executed or accepted as arbitrary imports.

A case-folded reservation coordinates writers, including on case-sensitive test
filesystems. Every destination file is created exclusively, definition last;
readers check the reservation before and after descriptor-held stable reads.
Exceptions remove only owned output inodes, never existing scene files. An
unfinished reservation blocks reuse and is preserved on abnormal interruption.
Library size is bounded to 1000 directory entries; a save checks its final pair
and associated-file count before publication so an ordinary save cannot make
the listing exceed that bound. This is a preflight count, not a filesystem quota
against concurrent independent directory additions. Browsing does not read every
image or create directories.
Old directory saves retain the same bounded loader and save-as-new path.


### Earth composition

Geographic views can choose fixed longitude or local solar hour (0 midnight,
12 noon). This selects longitude relative to the Sun, not a civil timezone.
Space views add geographic observer distance measured from the target center in
body radii, body/galactic/orbital north and counterclockwise rotation. Distance
is distinct from radius/FOV image framing, and is inactive for body-origin
observers. Composition was introduced in v7 and remains retained in current native
saves, review and history. Earlier
v2–v6 scenes reopen with composition defaults; v7 composition remains readable. No trajectories or external
ephemerides are imported by these controls.


The scene library does not use symlinks. In isolated tests of the installed
Xplanet 1.3.1 build, a symlinked config was readable, but relative resources were
not resolved relative to either config location automatically. Explicit search
directories (or the matching working directory) were required. A missing texture
could produce a warning and fallback image with exit 0. Preview always supplies
its private workspace and checkout search directories; loader symlink restrictions
are independent safety rules, not a claim that Xplanet cannot read links.


## Target-aware planetary baseline

A target field selects Earth, Moon or a supported major planet. Planetary scenes
reuse the camera/time model and native-file workflow rather than creating another
scene store or renderer. A centralized version table drives both parsing and
associated-file loading, including v6 captures and v7 composition. V8 adds the
explicit target; earlier formats default to Earth.

The model emits only the selected target's known texture/body configuration and
active camera arguments. Earth-specific fields, annotation files and captures
remain serializable but do not affect a planetary render digest. Thus changing an
inactive Earth layer does not falsely mark a Moon preview stale, while changing
target does. Central health rejects same-body origin/target combinations and
validates retained inputs so saved scenes can reopen without losing data.

Only Earth Now scenes can use current-data-derived clouds. Static Earth imagery
and annotations also stay off other bodies; they are not reinterpreted as lunar
or Martian coordinates. Grid/scene labels are common. Body texture presence is
checked, while build-dependent decoding, texture orientation and ephemeris
precision are explicitly not certified. No SPICE/NORAD inputs, giant-planet
systems, ring assets or general multi-body editing are enabled by this baseline.


Stock presets are exact generated native pairs in `samples/scenes`, not user
configuration or another settings store. The same strict loader snapshots them;
stock browsing is distinct from the user library and default Save goes to a new
user-library copy. Preset renderer/asset roots are deliberately illustrative
absolute references, ignored on Open. No personal paths or captured data are
shipped. The normal tracked-source export includes these regular files.


## Major-planet maps

The map allowlist includes Mercury/Venus/Jupiter/Saturn/Uranus/Neptune.
Origins reuse the same explicitly named body set and the existing same-body
conflict rule; no random/system selection or external ephemeris parser is added.
V9 adds one bounded integer `planet_shade` field, retained but inactive on Earth.
Prior formats recognize their original target/origin capabilities; v8 bodies keep
identical default bytes. Native planetary body grammar remains the existing map/
grid/shade grammar, and recognition still requires exact regenerated bytes.

Saturn uses the renderer's internal ring model. No ring image is copied, no
scientific ring/epoch accuracy is claimed, and projected map ring shadows are not
misreported as a visible ring system. Target context distinguishes surface Venus,
static gas-giant textures and body-dependent longitude conventions. Bundled additional moons and Pluto/Charon are supported with conservative
input guards and explicit texture/backend caveats; the studio calendar bound
does not certify backend accuracy or coverage.

Planetary presets use the same source snapshot and save-as-new path as Earth
presets; they carry illustrative executable/root references, not personal paths.
Finite private previews use explicit UI input and shared health. Reviewed selected
scenes also have a literal zsh desktop path, with explicit separate restart. Neither
path executes imported definitions or relaxes arbitrary-import/provider boundaries.


## Observational snapshot boundary

`observation_capture.py` is a narrow adapter for the three known producers, not a
provider/plugin or arbitrary native-import layer. V10 stores layer choices and one
immutable capture identity; the frozen native assets/provenance carry the actual
evidence. Cloud and observation captures share the finite worker/process-group
cleanup and history budget. Preview/save/health use one model activation rule
(Earth + Now), and saved-view loading reads only fixed allowlisted manifest names
with bounds, no-follow descriptors and stable identities.

Capture compares source bytes with saved publication hashes and rechecks config,
records, image dependencies and journal presence without taking a lock or writing
source. Storm marker/arc files are indivisible evidence. Canonical grammar excludes
unknown native options and file/font references; supported producer PNG icons are
renamed and hash-bound. Scene prefixing rewrites image options only, never label
text. Source-dependent paths/errors/credentials never enter provenance. The small
public TotalMarker `observational_freshness` helper reuses existing health policy
without changing producer validation or declaring quake freshness from feed age.

Immutable bundles retain inactive products and history; render input uses only
selected active products. Successful preview snapshots retain their provenance.
Opening/cancelling menus does no implicit capture; actual worker requests remain
explicit user decisions. See [observations guide](observations.md).


## Preservation-aware inspection boundary

`native_inspection.py` offers read-only custom-pair snapshots and bounded escaped
reports. It never evaluates definitions, infers camera values from arbitrary code
or follows unknown resource references. Unsupported input is explicitly ineligible
for conversion/copy; this prevents silently losing unknown associated data. The
existing strict generated-scene loader remains the editable fast path.

`ViewDocument.native_files` retains the exact verified loaded bytes (excluded from
representations), alongside parsed settings. Recognized unchanged copies use those
bytes, not regenerated settings, and include all associated assets with original
names/versions. Both generated legacy saves and verbatim snapshot copies share the
same exclusive-directory writer and conservative owned-file cleanup. No Source
Save, script execution or automatic Apply path was added. The original byte
preservation/no-op tests are acceptance tests for future general import as well.


## Bounded native literal copies

`native_patch.py` uses byte spans for known shading/grid/cloud/magnification numeric assignments and
literal grid switches and map/night/cloud filenames,
not a general configuration serializer. Unknown bytes are opaque; duplicates,
mixed assignments and ambiguous structure are refused or read-only. Missing keys
can become explicit overrides in a unique supported body section. No-op copies
preserve exact bytes and original literal spelling. `native_edit_ui.py` keeps this flow
separate from the scene draft, preview and history. Review/confirmation is bound
to current values and destination. Saves require a new same-directory `.conf`,
recheck source/directory identity and bytes, and use conservative exclusive owned
file cleanup. Definitions and resource paths are never evaluated or followed.
This intentionally limited tool does not satisfy general editable import or Apply.


## Textured satellite expansion

The target/observer allowlists also include 18 additional textured moons/dwarf
bodies already supported by the engine. Existing v10 target/origin fields and exact
body regeneration are reused; no executable import or parallel scene schema is
introduced. Earlier generated scenes still reproduce exactly. `MOON_PARENTS`
provides family context, not a new orbital model. Known longitude conventions
include Miranda/Pluto/Charon. Central health applies the conservative fixed-date
Pluto/Charon policy only to active geometry; UI, preview and Save share it.
Earth and inactive data retention stay unchanged. This adds body relationships,
not a per-body system compositor or accuracy certification. See [planetary limits](planetary.md).


## V11 bounded system composition

Two scalar fields extend the existing model: target/system composition and one
1–10 satellite enlargement factor. Only space views of supported parent targets
activate them; all other modes retain choices without changing effective renderer
inputs. Known companion maps come from the existing asset catalog. Model health,
body generation, preflight, history and strict saved-scene recognition share these
rules. V11 serializes both fields; reopening v2–v10 scenes supplies defaults, and old native pairs
continue to reproduce exactly. System-body recognition regenerates the complete
known ordered config, refusing unknown sections/options or changed scales.

The target stays magnify=1 implicitly. Applying scale to the target could alter
relative radius/FOV semantics, so the one factor is emitted only on companion
sections. There is no visibility abstraction: engine magnify=0 still plots a point.
No orbit model, auto-fit, external kernel or renderer modification is introduced.
See [system composition](systems.md) for user-facing limits.


## V12 bounded orbital guides

Three retained scalar fields add on/off, allowlisted color and integer 1–3 width.
Only active system-space scenes emit guides, only on configured moon sections.
The fixed `orbit={-0.5,0.5,5}` avoids zero segment counts; no arbitrary orbit grammar
or source file is accepted. V12 definitions retain styles; earlier formats use
inactive defaults and reproduce their exact bodies. V11 system bodies remain
unchanged when guides are off. Active guide bodies have an exact v12 header and
are accepted only by complete regeneration of the known layout.

Upstream addArc includes one extra segment past its stop. Model validation uses
reviewed longest-moon periods with outward whole-day padding, including that
sample, before applying existing date policies. It does not implement orbital
mechanics or certify backend coverage. Invalid footprints block before renderer
spawn, retaining the last successful preview. Guides use the engine's parent-held
scene frame; they are not inertial trails. [Guide details](orbits.md).


## V13 individual moon overrides

One bounded scalar table extends the native definition: allowlisted moon names
and finite 1–10 scale literals, with duplicate/unknown/oversized input rejected.
The shared-scale bounds remain the numeric source of truth. There is no new file,
provider, package or execution hook. `moon_scales_ui.py` holds an ephemeral dialog
copy; only an explicitly validated result reaches main history as one edit.
Cancel and unchanged results preserve the original draft/metadata. Other-family
values remain stored and inactive; old scenes default to an empty table.

Body generation depends on effective scales. Uniform effective scales reproduce
the v11/v12 body layout even if produced by overrides; redundant overrides do not
change preview identity. Mixed scales use a short v13 header plus known per-body
magnify lines, not an unbounded comment containing the whole table. This avoids
the renderer's line-buffer limit. Strict recognition reads only the known body
values and regenerates the complete layout. The associated definition preserves
shared defaults and all override intent, including inactive families, and must
reproduce the same effective native body. Date/guide policies stay unchanged.


## Review-only handoff export

`handoff.py` builds an immutable plan from a recognized named scene, opaque custom configuration
hashes, explicit local renderer/geometry and selected bundled resources. Rechecks
rebuild the complete expected record rather than trusting imported manifest paths
or arguments. Export writes a new private snapshot, manifest last, using owned-file
cleanup and source rechecks. Altered partial output is retained. Nothing selects a
scene or invokes an executable. The separate `selection.py` owns explicit
revision/reference publication. `handoff_cli.py` is stdlib-only; the explicit shell
modes bypass the UI dependency check. Setup's check exits before normal setup code.

`handoff_ui.py` presents the same exporter/checker as a separate modal. Review
performs no writes; confirmation rechecks inputs before exclusive publication.
Input changes invalidate the pending review. The dialog never replaces the editor
draft or exports its unsaved fields; application status reports the last result.

This is not a filesystem-wide snapshot, authenticated plan signature or active
selector. Stock/implicit renderer resources remain unbound, and the plan's notes
state geometry/resource limits. There is no whole-state or producer rollback.
Selection uses `config/desktop.scene` and immutable private revisions
in `.state/xplanet/scenes`; `scene.zsh` validates hashes and consumes literal argv
without Python or sourced generated definitions. Selected execution uses the
revision as cwd and separate private desktop scratch, preventing current-directory
resource shadowing and renderer scratch writes into immutable scene snapshots.
Selection rollback is reference-only
and guarded; ambiguous publication requires inspection, not automatic replay.
See [Apply contract and limits](apply-design.md).


## Native copy byte review

Prepared numeric copies retain the complete byte replacement set. Review and save
regenerate the proposal from its literal edits and require exact agreement on
bytes, field-level changes and spans. Review shows bounded escaped spans and
whole-file hashes; it never decodes/re-serializes opaque native content, reads
referenced assets or uses a quadratic generic diff. Byte offsets refer to the
original snapshot. More than 32 spans are explicitly abbreviated in display only;
the complete prepared edit set still determines the copy and its hash. Source
identity checks remain at publication, so review is not a claim of live validity.

## Attempt-scoped diagnostics and selection inspection

`display_geometry.py` reads AppKit NSScreen data through the system JXA bridge
once at interactive CLI launch, with a two-second timeout and a fixed 32-display
report limit. It uses `convertRectToBacking`, not a guessed Retina multiplier;
NSScreen index 0 is the primary menu-bar display. These are backing dimensions,
not a claim about native panel pixels or the display containing Terminal. No
serial numbers/names are collected, settings changed, or renderer invoked.
A valid bounded primary size seeds only a blank UI draft. Saved scenes, recovery,
stock presets, model/CLI defaults and explicit desktop handoff dimensions retain
their own geometry. Missing GUI sessions or excessive sizes visibly fall back to
1920×1080. No live monitoring or automatic resize of an edited draft occurs.

`geometry.py` shares bounded frame validation with deployment review. Geometry
is part of the native scene and active preview identity. `resources.py` keeps
bounded first/last log evidence and executable-identity-bound `-version` support
reports. An explicit diagnostic runs the selected executable in the existing
private finite-render workspace; opening configuration health executes nothing.
Only a complete recognized successful support report establishes an absent
required image format. Unknown/failing/truncated reports remain unknown.

`selection_info.py` verifies the current selector and frozen revision on demand;
its UI reports selected-for-next-start, never actual running state. Opening that
native snapshot creates an editor draft with the current local renderer and
stored preview geometry. Saving remains a new library copy. No service operation
or implicit selection change is part of inspection. See
[diagnostic evidence and limits](diagnostics.md) and
[selected scene ownership](apply-design.md).

## Fixed lunar orbital camera

`View` owns the constrained body-centre/lunar-orbital distinction and native v15
coordinates, frame-centre percentages and exact generated coordinate data.
Only Moon origins in space mode activate the orbital camera, and fixed UTC is
required. Inactive choices remain native/history data. The one bounded row uses
`-dynamic_origin` to avoid `-origin_file` replacing the renderer's frame count.
It is a frozen known snapshot, not arbitrary dynamic input or a trajectory API.
The known Moon body block and bundled map are explicit scene resources.

`open_view` reads the declared regular coordinate file through the existing stable
bounded descriptor path and requires exact model regeneration. Preview uses a
private relative copy; handoff derives the prefixed coordinate path from the
known native scene name and hashes it into the immutable revision. Centre offsets
are recomputed from the reviewed dimensions. Generic zsh literal argv/hash
validation needs no new parser or Python lifecycle dependency. See
[camera limits](orbital-camera.md).

## Consistent save, preview and exit evidence

Exclusive scene writes retain expected bytes as well as file identity. Cleanup
hashes a stable regular file before deleting it; an edit during fsync is not adopted
as disposable owned output. Incomplete or unverifiable failure material can remain
for inspection rather than being deleted. Moved/replaced directory paths are rechecked before
Open/Save success, and cleanup stays confined to unchanged owned files through
held descriptors. These are cooperative accidental-change protections, not a
sandbox against a continuously hostile writer.

Preview snapshots bind the renderer identity as well as active arguments/native
data. Replacing a binary makes an existing image stale; changing it during rendering
refuses promotion and keeps the prior image. Diagnostic reports include preflight
failures even when no binary could be probed. Save and selection outcomes remain
separate at exit, so a later save cannot erase an uncertain selection result.

Runtime readiness is bound to this project's actual isolated venv; linked runtime
directories are refused before the launcher executes their Python. The venv's normal
base-interpreter symlink is still supported. No provider migration or installation
repair is attempted.


## Session continuity and management evidence

Save-and-continue reopens the newly created supported pair, then advances the
history baseline without clearing undo or workspace captures. If reopening fails,
the successful copy is reported separately and the draft remains. Native files are
not autosaved; private draft recovery is described below. Normal exit protects dirty
fields; Ctrl-C cancels work first and emergency exits retain only completed checkpoints. The process result distinguishes an earlier retained save from a save
performed on exit, with selection uncertainty preserved independently.

`library_ui.py` filters bounded library names and validates only the selected pair.
`native_patch.py` still operates on literal byte spans, not arbitrary definitions;
path edits are data-only and never follow resources. Review and exclusive
same-directory publication retain the existing source/owned-cleanup checks.

The zsh management dashboard checks process-name presence and job registration
separately. It verifies only the selector/deployment metadata hash and local root
for the next start, without certifying resources or identifying the running scene.
Normal lifecycle validation remains authoritative. The explicit Saved health action
asks TotalMarker for compact, control-free records derived from its existing health
semantics. Management caches that dated snapshot in memory; entry/navigation never
starts Python, performs a feed request or polls. Unknown evidence stays unknown.


## Private recovery and owned shutdown

`recovery.py` owns only versioned scratch data in `.state/configurator/drafts`.
`draft_session.py` snapshots editor memory on a bounded debounce, while
`recovery_ui.py` provides explicit inspection/recovery/discard. Raw values and
baseline use the model's shared enum rules; invalid input text remains data.
Known frozen object validators govern captures. Recovery never evaluates definitions,
adopts a stored executable without explicit choice, or consumes/replays selection,
producer or service state. It introduces no renderer-facing configuration truth.

Each session holds an OS ownership lock. A nonblocking store lock covers quota
accounting and publication; readers verify canonical metadata, hashes, private
regular files and two complete revisions. Descriptor-relative operations retain
their directory identity. New objects/manifests precede atomic index replacement;
only verified obsolete bytes in that same session are pruned. Unknown/changed
material is retained. The 256 MiB aggregate budget refuses new checkpoints rather
than evicting other unsaved sessions. Filesystem calls remain cooperative/bounded
by data size, not guaranteed hard-latency operations.

Key dispatch schedules cleanup workers rather than blocking the input handler.
`Workspace.stop` coalesces overlapping cleanup and clears completed tasks before a
later child is considered. Emergency KILL is tracked per actual owned Process,
so repeated requests do not signal that already-killed group again. SIGINT/TERM/HUP
and terminal loss use a no-prompt path; signal handlers are restored on unmount.
No shell lifecycle or TotalMarker process ownership is added.

## Bounded comparison sets

`comparison.py` derives three reviewed radius/FOV variants for supported static
body-centre space scenes. Now is fixed once; current observational inputs are
refused rather than reinterpreted. A subordinate owned Workspace uses existing
finite rendering, cancellation and renderer identity checks. Its three bounded
1920×1080 PNGs, JSON record and static local HTML sheet are promoted only together;
ordinary preview history and prior successful sets survive failure. The explicit
viewer route stays external. No queue framework, compositor, animation engine,
provider call or new package dependency is introduced. See the
[comparison limits](comparisons.md) and [recovery contract](recovery.md).

## Durable image artifacts

`render_export.py` reads only owned retained snapshots, binds source file identities,
checks requested PNG header geometry and comparison hashes/values, and uses the
existing exclusive owned-file writer for a new destination directory. It does not
rerender, serialize native settings, run a provider or Apply a scene. Bounded async
reads allow cancellation before publication; final filesystem writes are synchronous
and no detached thread continues after exit. Export receipts omit executable/source
paths and raw private diagnostics; embedded image metadata is intentionally retained.
`export_ui.py` owns explicit destination/confirmation only. Private temporary originals
and user-owned durable copies have separate lifetimes. See [export contracts](export.md).

## Scene exchange boundary

`configurator.exchange` is a stdlib data boundary separate from Apply and rendering.
It normalizes recognized generated scene snapshots with fixed portable renderer/asset
placeholders, hashes bounded stored-ZIP members, and validates a private staging copy
before exclusive publication. Import rebinds only the renderer and asset root to the
recipient. It never evaluates shell definitions, probes the renderer or performs
selection. Optional PNGs lose ancillary metadata and have bounded pixel streams.
Frozen provider captures remain outside exchange v1 rather than being silently omitted.
The small exchange forms collect explicit saved source/destination and optional PNG;
Workspace supervises the same stdlib CLI through its existing owned process/stop path.
No detached thread writes destinations after cancellation. The draft is not an export
source, import never adopts an archived executable, and optional Open uses the existing
fresh dirty-replacement gate. Cancellation truthfully leaves destination inspection to
the user; output inside the temporary workspace is refused. See
[format, workflows and limits](exchange.md).

The [astronomy capture integration](astronomy-capture.md) validates
existing NORAD and dated eclipse products without producer operations. V16 retains
independent product IDs/files, including inactive choices, in named/legacy saves,
preview identity/provenance and byte-preserving native copies. Recovery schema2 adds
bounded astronomy blobs for both current and baseline IDs. Exact old schema1 fields
normalize to Off in memory; unknown fields or versions remain refused without rewriting
original records. Session quotas include all capture kinds.

NORAD activates only on Earth Now, with epoch revalidation for preview/save, and
central handoff command construction refuses active NORAD at both bundle and immutable
revision paths. No runtime-expiry enforcement is implied. Eclipse activates only for
Fixed UTC within its metadata-bound interval; Now omits references deterministically.
Static eclipse handoff uses the existing immutable snapshot and timewarp0. Weather's
Now-only policy stays intact. Framing sheets preserve captures in their owned child
workspace and refuse conversions that would change eligibility. No zsh lifecycle,
provider or deployment service code changes are required.

### Bundled map path compatibility

The bundled collection is top-level `maps/`, with padded solar-system body
folders. Recognition accepts only the known previous map spellings within an
otherwise exact generated body. It retains the input bytes; preview regenerates
from the validated model using current paths. This is not a general path rewrite
or support for arbitrary native imports. Saving a new studio copy emits current
paths. A prior-layout immutable desktop revision requires a new reviewed copy;
no running selection or source file is silently migrated.


## Responsive local inspection and exit review

Native inspection and exact snapshot copying, literal native-file load/save,
scene-library enumeration/inspection, selected-revision verification and recovery
listing use the existing owned filesystem worker. Filtering an already inspected
library entry uses its cached snapshot; Open still revalidates. Results for an
obsolete selection are discarded. Back or Ctrl-C requests cancellation and waits
for that owned reader/writer, rather than detaching it. An individual operating-system
call must return before cooperative cancellation can finish; this is not a claim
that a hung filesystem can be forcibly recovered.

Dirty exit review leaves an active operation running. Keep editing preserves that
operation or its completed result. Confirming exit awaits cleanup before the final
recovery decision. Inspection dialogs cannot appear above a pending exit question,
and a completed save remains an explicit new copy. Native filesystem failures are
translated into actionable missing-file, permission, symlink or destination advice;
source files and refusal rules are unchanged.
