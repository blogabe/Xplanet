# Scene studio user guide

The configurator lets you explore Earth, planets and supported moons, preview a
scene, and save a new native Xplanet configuration. It is an editor, not an installer
or a desktop supervisor. **Save**, **select for next start**, and **restart** are
separate operations. Bare `xplanet.sh` opens management; choose Configurator to
enter this editor. The keys below describe the scene studio, not management.

Read this guide inside the studio with **Help / F1**, or print it without starting
Python, installing packages or opening the editor:

```sh
./scripts/xplanet.sh config --help
./scripts/xplanet.sh config --guide
# Optional: page through it yourself
./scripts/xplanet.sh config --guide | less
```

## 1. Open the studio

From a complete checkout, you need Python 3.11+, an installed Xplanet with PNG
support, and the shipped assets. Permanent desktop setup, personal xp.def/xp.conf,
TotalMarker configuration and registered jobs are not required for exploration.

```sh
# One-time, explicit preparation of the isolated Textual environment:
./scripts/xplanet.sh config --prepare
./scripts/xplanet.sh config
# For a renderer outside PATH:
./scripts/xplanet.sh config --renderer /absolute/path/to/xplanet
```

Preparation downloads pinned dependencies into the project's private UI venv.
It does not install packages globally or change Homebrew/uv selection. If the
runtime needs rebuilding, preserve `.state/configurator/drafts`; move only the
old `venv` aside before explicit preparation. See [Python/runtime details](reference.md#prerequisites).

## 2. Start from a scene

For a first experiment, choose **Stock scenes…**, filter a name such as
`moon-from-earth` or `saturn-rings`, inspect its summary and **Open selected**.
Stock files are starting points; your changes save under a new user-scene name.
**Scene library…** browses your own matching `.conf`/`.def` pairs in `config/scenes`.

You can also open a shipped scene directly:

```sh
./scripts/xplanet.sh config --view "$PWD/scripts/configurator/samples/scenes/moon-from-earth.conf"
```

Only generated, recognized scenes can be opened as studio drafts. Arbitrary
`xp2.conf`/`xp3.conf` files may instead need **Inspect native files…** or the
bounded **Edit native values…** tool. A valid working configuration can be
unsupported by the editor. It is not executed, repaired or silently converted.
Opening a valid scene replaces the current draft and resets undo; sources stay
unchanged. Save or explicitly keep a recovery draft first if necessary.

## 3. Move around and change settings

A blank scene starts at the primary macOS display's current backing-pixel size.
The geometry control shows both backing pixels and logical points (which differ
on Retina/scaled displays), plus other displays. This is a read-only snapshot at
launch; reopening the studio checks again. Saved and stock scenes keep their own
dimensions, and editing the geometry stays explicit. If detection is unavailable
or the primary size exceeds preview limits, the field uses 1920×1080 and explains
why. This does not change macOS display settings or the installation's legacy
geometry. Desktop geometry is still reviewed separately in Handoff review.

Use the mouse, **Tab / Shift-Tab** to move focus, and **Enter** to activate buttons.
For a focused selector, Enter/Space/Up/Down opens its choices; arrows and Enter
choose an item. Scroll with the mouse wheel/scrollbar or Page Up/Down in the scroll
area. There is no required wizard order: revisit sections freely.

Choose the **target**, then the view/camera. **Space** is the non-projected view;
rectangular and orthographic are map projections. Space offers observer origins,
radius or field of view. A body-origin viewpoint is from that body's centre,
not its surface. The separate lunar orbital camera has explicit limitations.

Irrelevant controls hide while retaining their choices. Invalid retained values
are exposed for correction. **Configuration health** explains blocking conflicts,
warnings and information; it does not refresh a provider or certify astronomy.
**Review changes** compares against the loaded/last saved baseline.
**Undo / Redo** (Ctrl-Z / Ctrl-Y) handles session edits, including invalid text.

For a first planetary experiment, open `saturn-rings`, change framing or observer
latitude, then preview. For Earth, try `earth-september` and change the map family,
month, night texture or grid. See the [settings reference](reference.md) and
[stock scene catalogue](stock-scenes.md).

## 4. Preview and compare

**Preview** renders one temporary PNG; **Open latest** explicitly opens it in the
external image viewer. The studio does not display a continuously updated image
inline. **Export latest…** makes an explicit durable copy in a new chosen directory,
with an image hash and receipt; it does not rerender or overwrite anything.
A later failure/cancellation keeps the previous successful image, labeled
when it no longer matches the draft. **Compare…** describes the last two successes.

**Diagnose resources** performs an explicit finite renderer diagnostic and capability
probe. Outside the editor, use `xplanet.sh diagnostics` explicitly; see the
[diagnostic guide](diagnostics.md#renderer-support-outside-the-studio). Read its evidence rather than assuming a missing map and a missing compiled
feature are the same problem. A reported unknown is not proof of unsupported code.

**Framing sheet…** separately reviews three radius/FOV variants at one epoch,
then renders three 1920×1080 images. **Open framing sheet** opens their temporary
local HTML grid explicitly. Framing comparisons use static body-centre space views;
it refuses active current-data captures and lunar orbital cameras. It is not
animation or an image-difference tool. **Imagery month sheet…** instead compares
three explicit months from the selected bundled Earth map family, holding camera
and scene time constant. Stock maps have no monthly variants; current observational
layers are refused rather than re-dated. See [comparison limits](comparisons.md).

All preview/contact-sheet files are temporary and disappear on editor exit.
An external viewer may retain already loaded pixels. Nothing replaces wallpaper,
starts desktop jobs or runs providers.

**Export comparison sheet…** keeps the complete set as PNGs plus static local HTML.
Source previews are temporary; exported copies survive editor cleanup. Exported
images are snapshots, not portable scene files or new observations. See
[durable exports and limits](export.md).

For eclipse paths, **Import local NASA-format path…** reads an explicit local table
and a claimed official event reference without fetching it. Format, hash and event
consistency are evidence about supplied content, not proof of NASA authorship.
Review coverage, then choose matching Fixed UTC, including a midnight
rollover only with an explicit independently supplied first-row UTC date; Now retains but omits the prediction. Frozen NORAD can retain bounded PNG
icons for Now previews, while active NORAD desktop handoff remains unavailable.
See [astronomy capture policy](astronomy-capture.md).

## 5. Save a new scene and continue later

Choose a new destination such as `config/scenes/my-moon.conf`, then review and
confirm **Save & continue…** or **Save & close…**. Names use 1–48 ASCII letters,
digits, underscores or hyphens. Existing names and case aliases are refused.

Saving creates a matching `.conf`/`.def` pair and any scene-prefixed associated
files. Keep them together; do not rename only half a pair. A destination without
`.conf` uses the supported legacy new-directory format. Save-as-new never
replaces your original configuration.

Save & continue keeps undo/captures and establishes the saved copy as the clean
baseline. Later Undo does not delete a saved copy. Reopen through Scene library
or `--view` to resume; cross-session undo history is not restored. For example:

```sh
./scripts/xplanet.sh config --view "$PWD/config/scenes/my-moon.conf"
```

## 6. Leave, interrupt or recover

| Key/action | Result |
| --- | --- |
| F1 / Help | Read this guide; F1 or Escape returns to the previous screen. |
| Ctrl-C during work | Cancel owned preview/capture/set/export preparation and stay in the editor. |
| Another Ctrl-C during cancellation, or Ctrl-C while idle | Emergency exit using only completed recovery checkpoints. Recent edits may be absent. |
| Ctrl-D / Ctrl-Q / main Escape / Cancel | Request exit; dirty drafts offer Continue editing, Keep recovery draft and exit, or Discard. |
| Escape in a dialog | Normally returns from that dialog. |

Private draft recovery is debounced under `.state/configurator/drafts`. It retains
raw invalid inputs, inactive choices, baseline and frozen captures with a bounded
budget and separate concurrent sessions. Native files are never autosaved.

Choose **Recovery drafts…**, **Inspect checkpoint**, then explicitly recover or
discard. An older fallback checkpoint is clearly identified. The local executable
stays selected unless you opt in to restoring recorded text; recovery never runs it.
Undo stacks, previews and transient dialog forms are not recovered. Open editable
forms therefore require explicit discard/continue when leaving. Source files,
provider state, selected scene and jobs are never replayed. See [recovery, keys and
failure limits](recovery.md).

## 7. Use a scene as the desktop—only when you choose

Saving alone changes no desktop selection. **Handoff review…** uses an already
saved named scene: review its local renderer, geometry and resources; export and
check the review bundle; then explicitly review and confirm selection. Unsaved
editor changes are not part of that saved-scene review.

**Apply selects an immutable revision for the next start. It does not restart.**
Inspect it with **Selected scene…** or:

```sh
./scripts/xplanet.sh config --show-selection
```

Restart through management/the lifecycle CLI only when ready; it stops all your
Xplanet processes before starting the selected desktop. A running display does not
silently adopt library edits. No selector preserves legacy behavior; an invalid
selector fails clearly rather than falling back. For exact export/selection/restore
commands, see [Apply and guarded recovery](apply-design.md).

## Limits and where to look next

- Fixed scene time changes geometry, not imagery dates. Bundled maps/clouds are
  static imagery; current-derived clouds, storms, quakes and volcanoes are Now-only.
  Frozen captures use existing verified output without refreshing it.
- Body shapes, textures and backend approximations are not scientific/event
  certification. There is no general Hide control or arbitrary trajectory editor.
- Recovery/preview bounds are not hard guarantees against filesystem stalls,
  SIGKILL or power loss. Live desktop, fresh-login and UTM validation remain separate
  from automated, real-terminal and finite-render evidence.

| Need | Reference |
| --- | --- |
| Detailed controls, saved formats and resources | [Configurator reference](reference.md) |
| Missing feature, binary or map | [Diagnostics](diagnostics.md) |
| Planet/moon coverage and dates | [Planetary limits](planetary.md) |
| Existing clouds/events and freshness | [Frozen clouds](cloud-capture.md), [observations](observations.md) |
| Preserve a custom configuration | [Native inspection](import.md), [literal copies](native-values.md) |
| Installation, scheduling and desktop commands | [Management](../management.md) |

## Share a generated scene

**Export saved scene…** and **Import scene archive…** use the
[scene exchange workflow](exchange.md) for saved settings and recognized
local annotations with hashes. Export excludes unsaved draft changes; import creates
a new copy, then offers an explicit Open with dirty-draft protection. The CLI also
remains available. Bundled
maps stay references; frozen provider captures are excluded from exchange v1.
It does not execute imported files or select a desktop scene.

## Frozen astronomy layers

Earth scenes can explicitly capture existing TotalMarker NORAD selectors/TLEs and
dated eclipse paths. NORAD is Now-only for editor preview; eclipse display requires
matching Fixed UTC. Inactive captures remain saved, but active NORAD desktop handoff
is refused because runtime expiry is not enforced. No producer refresh or automatic
activation occurs. See [capture steps, time policy and limits](astronomy-capture.md).
