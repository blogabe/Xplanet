# Potential configurator roadmap: an Xplanet scene studio

A living set of possibilities, updated as we learn. The vision is a scene studio:
explore a viewpoint, understand its ingredients, compare alternatives, and keep
native, reusable scenes. The same editor can help someone find a first desktop
view or build a much richer planetary experiment.

This is a direction for discussion, not a fixed sequence, release schedule or
promise to implement every idea. Active work and decisions belong in the local
configurator open-items tracker. Current behavior is documented in the
[user guide](user-guide.md) and [module architecture](architecture.md).

## What exists, and what the evidence means

The configurator has an isolated Python/Textual module; a shipped Earth
sample; projected and space camera modes; geographic/body-origin observers;
exclusive space framing; current/fixed UTC time; temporary finite PNG previews;
explicit native-file saves; and strict reopen/revise/save-copy with retained
inactive choices, without executing shell definitions or changing the original. Configuration health, dynamic controls
and two-success preview retention/comparison support that workflow. Exact
resource inspection and image compositing remain future possibilities. Bundled
seasonal day maps, stock/bundled night imagery, twilight blending, grid presets
and UTC scene labels round-trip through versioned native formats. It has
explicit immutable named-scene selection, but no general importer. A flat named scene library under config/scenes provides matching .def/.conf
pairs and scene-prefixed assets, while retaining legacy directory compatibility.
Session change review, dirty status and bounded
undo/redo support revision, including invalid and inactive draft values.
Bounded static place labels and surface route arcs save/reopen as native
optional files; broad layer import and advanced marker options remain future work.
Bundled relief/specular shading and the explicitly archived 2011 cloud display
are available as Earth appearance settings, with contextual parameter controls.
TotalMarker live references and provider controls are not implied. Explicit frozen
cloud capture for Now scenes is implemented separately, with provenance and
source-independent save/reopen; quake/volcano markers and paired storm marker/arcs
have bounded frozen capture with dependency validation as well; fixed UTC excludes current-derived data.

Earth composition includes local solar hour, geographic observer range and
space north/rotation with inactive retention and v7 scene compatibility.

Planetary selection covers Moon and all eight major planets with bundled
textures, explicit body-origin viewpoints, shadow brightness, target/origin health
and inactive Earth setting preservation. Saturn space-mode rings and three
planetary presets are verified narrowly. The additional bundled moons, Pluto/Charon
and four relationship presets are supported with explicit geometry caveats.
Bounded system-texture composition and explicit shared moon enlargement are
implemented. Bounded parent-relative orbital guides and shared path styling are
implemented as well. Individual moon-scale overrides are supported with explicit inheritance.
Per-body visibility, ring editing and external
ephemeris-driven work remain future.

Three shipped Earth starting scenes demonstrate solar-hour framing, seasonal
imagery and Earth-from-Moon geometry, with read-only originals and safe copies.

Future ideas below use these evidence labels:

- **Engine:** documented Xplanet 1.3.1 behavior. The corresponding editor controls
  still need implementation and tests; documentation is not a rendered proof.
- **Conditional:** an engine feature needs particular build support, files,
  provider access, date coverage or other resources. A feature name alone does
  not establish that those prerequisites exist on a user's machine.
- **Exploratory:** a proposed editor experience or supporting tool. It may need
  extra software, engineering or research beyond Xplanet. No dependency choice
  is implied by an idea appearing here.

Evidence can overlap: a flight sequence may combine an Engine camera option,
Conditional ephemeris data and an Exploratory timeline editor.

## The tick-tock rhythm

Alternate useful workflow improvements with visible new capabilities. A workflow
slice makes experimentation safer or easier; a capability slice gives someone
something new to see. Each should end in a small working loop: open, change,
preview, keep a copy or cancel. Revisit the next pair after learning from use.

| Possible workflow tick | Possible capability tock |
| --- | --- |
| Reopen, revise and preserve a source view — implemented narrowly | Earth camera/time and explicit space-view mode — implemented |
| Change review / undo — implemented; bounded private draft recovery — implemented; general unknown-content editing — future | Earth appearance and bundled-map exploration — implemented narrowly |
| Inspect resource resolution and compare previews | Static places/routes plus grids and labels — implemented narrowly |
| Explain build/data prerequisites before enabling controls | Planets, moons, orbital scenes and eclipses |
| Review a bounded Apply plan and recover known config changes | Deliberately connect existing live-data layers |
| Reproducible finite batches and explicit automation | Timelines, flybys and visual stories |

These pairings are not mandatory phases or a fixed schedule. Choose further
workflow improvements and capabilities based on real use and the remaining
limitations documented below.

## Workflow possibilities

### Safe revision and import — Exploratory

A potential starting path asks for Earth or a planetary scene, then exposes the
relevant controls and prerequisites. Make this a guided start with revisitable
sections, not a rigid wizard. Retain inapplicable choices where their meaning is
well-defined, and explain incompatible settings rather than silently discarding
them. Earth/Moon/major-planet target selection is implemented narrowly; additional
textured moons and Pluto/Charon are included; bounded system composition configures supported companions. General
individual scale editing is also implemented; general per-body visibility remains
unavailable in this renderer.

Grow from exact recognition of our own saved pairs toward a preservation-aware
reader: show understood settings, inherited values and opaque content separately.
Preserve comments, ordering, repeated file entries and valid multiple assignments.
Bounded numeric-copy review shows exact byte edits and snapshot/copy hashes.
General preservation-aware native-file diffs remain future work. Concurrent-source
checks, snapshots and explicit new-copy saves already protect the bounded workflows.

Session undo/redo and private recoverable raw drafts are implemented. Broader named
project organization remains a possibility for more comfortable experimentation. Import should explain exactly
what can be edited and what stays untouched. Inspecting `xp.def` must remain data
inspection; supporting a wider subset is not permission to execute arbitrary shell.

### Preview and diagnostics — Engine + Conditional + Exploratory

Make the preview explain the scene: chosen target/mode, camera, scene time,
resolved resources, actual renderer build and warnings. Add deliberate A/B,
before/after and contact-sheet comparisons. Offer quick low-resolution drafts
and an explicit full-quality finite render with progress, cancellation and budgets.

Resource inspection could identify missing/shadowed maps, dimensions, texture
roles, font availability and data coverage. A useful failure should point to the
setting or prerequisite that needs attention. Image comparisons, pixel inspection
and richer in-terminal imagery may require additional image/viewer support;
Textual alone does not turn Xplanet into an interactive graphics engine.

### Safe Apply and recovery — Implemented narrowly / Exploratory depth

Saving, selection and restart remain separate. Current Apply reviews a known
named scene, stages an immutable revision and changes only a guarded reference;
legacy files and schedules stay intact. Broader setup/application workflows remain
future work, not permission to replace arbitrary custom content.

Recovery should stay bounded: draft undo and configuration recovery do not mean
rolling back TotalMarker's entire state or discarding pending publication intent.
An ambiguous interruption should stop with useful diagnostics. The configurator
should not become a second installer, lifecycle supervisor or transaction engine.

## Capability possibilities

| Area | Potential user experience | Evidence and conditions |
| --- | --- | --- |
| Camera and time | Pick a target, geographic observer or body-origin viewpoint; compare daylight/night-side views; choose orientation, framing and a fixed UTC scene time. | **Engine.** Model camera strategies explicitly. Longitude/local solar time and radius/FOV interact; argument order can change meaning. Label timezone is separate from scene time. |
| Earth appearance and assets | Browse bundled seasonal maps; compare stock and textured Earth; tune night lighting, relief, specular reflection, cloud gamma/threshold, labels and grids. | **Engine + Conditional.** Show texture roles and resolved files. Cloud display needs an actual cloud product. Scattering needs prepared tables, not just a specification file. Keep bundled runtime assets available. |
| Geographic markers and arcs | Build place/event annotations, routes, eclipse-path overlays, grid presets and styled layers; inspect labels at different scales. | **Engine + Conditional.** Body and sky coordinates differ; marker units/visibility rules matter. Friendly editors and picking locations from a preview are **Exploratory**. |
| Planets and moons | Explore the Moon, Saturn's rings, Jupiter's system, Earth from the Moon and selected satellite relationships; compare honest fallback colors with supplied textures. | **Engine + Conditional.** Multi-body views need non-projected mode and suitable framing. Textures and optional ephemerides are separate resources; visual magnification must be identified. |
| Eclipses | Revisit an illustrative event from multiple viewpoints; compare a geographic path overlay with the engine's physical shadow scene. | **Engine + Conditional.** These are different workflows. Event time, geometry, resource coverage and ephemeris accuracy need validation before any scientific-accuracy claim. |
| Dynamic data | Deliberately connect clouds, earthquakes, storms, volcanoes, NORAD satellites and existing eclipse products to a scene. Show provenance, last-good data, stale state and unavailable layers. | **Conditional.** Reuse TotalMarker's supported producers and validation. Producing a file and displaying it are separate choices. Current weather/live-derived layers, their update labels and current TLEs are Now-only; fixed-time scenes retain those choices without displaying them. Dated eclipse predictions can display at matching Fixed UTC within proven sample coverage, without wallclock countdown/update labels. Explicitly dated static textures are separate. |
| Automation and portability | Render selected views or finite batches reproducibly; review schedules; export native scenes that can be understood independently of the UI. | **Engine + Exploratory.** Management owns macOS jobs. Portable model/render work can be evaluated separately from zsh/launchd; this is not a commitment to a Linux desktop installer or service port. |
| Timeline and storytelling | Mark scene moments, compare event stages, generate frame sequences and assemble a narrated visual story or flyby. | **Engine + Conditional + Exploratory.** Xplanet supplies finite rendering, simulated time and trajectory inputs; timeline editing and video assembly are additional work. Encoders, transitions and audio may require extra software. |

For advanced trajectories, a `num_times` flag alone does not guarantee a bounded
preview: non-interpolated origin playback can replace its frame count. Reviewed
inputs, row/frame limits, resource/date checks and cancellation must precede a
trajectory editor. SPICE/NORAD paths also need actual kernels/TLEs and coverage.

## Further-out scene-studio ideas

These deliberately stretch the vision. They are **Exploratory**, not implied
features of the current renderer or commitments to a framework.

- **Mission control:** a coherent view of the active desktop scene, renderer,
  saved data health and scene library, with a clear route into editing. Management
  retains lifecycle and activation; the configurator owns proposed settings.
  A dashboard could distinguish wall clock, simulation time and observation age.
- **Interactive exploration:** keyboard camera nudges, viewpoint bookmarks,
  coordinated map/globe comparisons and a progressively refined preview while
  moving through a scene. Test achievable latency before promising real-time
  navigation; a separate viewer or rendering strategy may be needed.
- **Layer laboratory:** compare day/night, relief, clouds, markers and tracks in
  isolation; inspect why a layer is absent; compare projection and scale choices.
  A swipe comparator, pixel-to-source inspector or compositor would be additional
  tooling, with its own coordinate/imagery validation.
- **Richer scene sharing:** [exchange v1](exchange.md) already supports reviewed
  native-scene copies, resource references, optional previews and hashes. Future
  sharing could add self-contained resources and captures only with explicit
  privacy, provenance and redistribution checks. Missing dependencies must stay
  visible; importing must not silently install or activate them.
- **A visual observing journal:** save rendered moments and notes alongside the
  exact scene/resource choices; revisit a sequence as the sky or data changes.
  Distinguish reproducible frozen inputs from an intentional live scene.
- **Scenario notebooks and guided tours:** assemble comparisons such as an
  approaching storm, a lunar eclipse or a spacecraft encounter. An annotated
  storyboard could explain the camera, exaggeration and data limitations rather
  than present an unexplained attractive image.

## Lessons from existing projects

- The original Java configurator's [mode-switch warning](https://xplanetconfig.sourceforge.net/docu_faq.html)
  reinforces cloning presets and preserving advanced content across simplified
  views, rather than silently regenerating only understood settings.
- [planet-slideshow](https://sourceforge.net/projects/planetslideshow/) and its
  [wiki](https://sourceforge.net/p/planetslideshow/wiki/Home/) illustrate separate
  rendering, optional compositing, caching and desktop consumption. Extra styling
  software would be a deliberate dependency choice, not an engine assumption.
- The [Live World Map wrapper](https://github.com/blairw/liveworldmap/blob/master/cronjob.sh)
  removes old JPGs before rendering. Our design should retain known-good output
  until a new image is verified, with its publication/freshness status visible.
- [Sailfish xplanet-background](https://openrepos.net/content/eatdirt/xplanet-background)
  documents output-directory setup failures and an optional cloudless fallback:
  preflight paths, explain missing layers and make fallback behavior explicit.
- The [upstream project list](https://xplanet.sourceforge.net/links.php) credits
  Living Earth HD with cloud maps, while attributing both renderer and cloud maps
  to WorldView. Track renderer, data and presentation provenance separately.

These are lessons from project descriptions/source, including historical tools;
none establishes present-day compatibility or selects software for this project.
Source/report time, successful checks and actual publication should remain distinct
from the scene's simulation clock and the age of an image still being displayed.

## Boundaries that should survive expansion

Native Xplanet configuration remains transparent. The configurator model/UI is
separate from TotalMarker's providers and zsh installation/lifecycle. Dependency
preparation stays explicit and isolated; opening a menu does not fetch data or
install packages. Scenes refer to resources rather than creating a drifting second
copy of active configuration. Existing finished assets and credits remain intact.

A map projection is not a multi-body space view; orthographic is still projected.
Some controls become irrelevant when the mode changes. Body/default ordering,
repeated entries, camera precedence and the engine's line-length constraints
shape any preservation-aware editor. Prefer one coherent intent over exposing
incompatible flags with no explanation.

Build probes and rendered fixtures should determine available controls. Optional
codecs, FreeType/Pango, SPICE, fonts, textures, scattering tables and ephemeris
coverage are prerequisites, not universal promises. A screenshot is evidence of
an output, not of scientific precision or current provider access.

## How this roadmap evolves

When choosing a slice, record its user benefit, evidence category, prerequisites,
smallest useful loop and how success will be checked. Move approved actions into
open items; keep unchosen ideas here. Update the implemented baseline as work
lands, revise assumptions when source/build or rendering evidence changes, and
retire ideas that do not earn their complexity. Attach provenance to new research
and compare what it actually demonstrates before turning it into a commitment.

The engine baseline comes from the existing Xplanet 1.3.1 research and
[module architecture](architecture.md), including source-backed
corrections to older documentation. Primary references:
[Xplanet documentation](https://xplanet.sourceforge.net/documentation.php.html),
[manual](https://xplanet.sourceforge.net/README),
[body configuration](https://xplanet.sourceforge.net/README.config),
[FAQ](https://xplanet.sourceforge.net/FAQ.php.html) and
[1.3.1 source](https://sourceforge.net/projects/xplanet/files/xplanet/1.3.1/).


A bounded native numeric-copy tool patches shade/twilight/bump scale without
reserializing unknown content. It preserves no-op bytes, requires a new same-directory
file and refuses ambiguity. General editable import, resource relocation and
general activation of arbitrary native copies remain separate future work; see [the limits](native-values.md).


Review-only named-scene handoff export/check is implemented. It freezes known
native/captured bytes, binds baselines and compiles explicit display arguments;
it does not activate a selection or change jobs. Explicit immutable named-scene
selection and guarded restoration are
implemented; restart remains separate and visible UTM validation is deferred. Bounded native numeric copying also covers grid subdivisions, without
enabling grids or reconstructing arbitrary definitions.

### Preview and stock scenes

The studio stores bounded preview dimensions (1920×1080 for new and stock
scenes), explicitly diagnoses the selected binary and renderer lookup evidence,
and inspects the immutable scene selected for the next start. The stock set has
24 scenes, with paired moon-to-planet viewpoints. A fixed lunar orbital camera demonstrates a limb, crescent Earth and Sun
in a separately labeled Earthrise-style stock scene; body-centre Earth-from-Moon
remains distinct. This is not a surface/event reconstruction or arbitrary trajectory
import. Centre offsets and a generated frozen coordinate row round-trip safely. See the [stock scene guide](stock-scenes.md).

The bounded native numeric-copy tool includes cloud gamma/threshold and
illustrative magnification. It preserves no-op bytes and opaque content; broad
path/resource/definition editing remains outside its contract.


Implemented workflow increment: save-and-continue with retained undo/captures and
dirty-exit protection; filtered scene-library browsing with selected-pair context;
bounded native literal grid/image-path copies; management next-start metadata and
explicit, dated saved-health snapshots. Private draft recovery is implemented below;
native files are never autosaved. General script import, companion-aware file
deletion/rename, running-scene verification and background polling remain optional
future scope, not release requirements.


Implemented foundation: [private recovery](recovery.md), protected exit,
responsive cancellation/escalation and concurrent-session checkpoints; plus a first
[three-frame contact sheet](comparisons.md). This does not implement
whole undo-history recovery, arbitrary batch/timeline axes, current-data comparison,
self-contained asset/capture bundles or broader native shell import. The next useful capability can
build on finite sets without treating successful images as event-accuracy evidence.


Implemented artifact workflow: retained previews and complete framing sheets can
be exported explicitly to a new no-overwrite directory with image hashes and minimal
receipts. Temporary originals remain separate. [Scene exchange v1](exchange.md) separately exports/imports recognized native scenes
as new copies with resource references, optional PNGs and hashes. It excludes
frozen captures and does not bundle third-party maps. Self-contained asset/capture
bundles, rasterized sheets, general batch axes and timeline/video systems remain
future work.
