# Preview geometry and resource diagnostics

Blank UI drafts use the primary macOS display's backing-pixel size when it fits
the preview bounds. Detection failure or an oversized primary display falls back
to **1920×1080** with an explanation. Saved/stock scenes retain their own dimensions;
stock scenes and comparison sheets use 1920×1080. Enter another canonical `WIDTHxHEIGHT` in the
preview size field: for example 2160×1080 (2:1), 3840×2160, or a square frame.
Texture-map aspect ratio does not dictate output aspect ratio. Framing, projection
and image dimensions are separate choices.

Each edge must be 200–16384 pixels and the total at most 16,777,216 pixels. This
bounds requested image size, not every aspect of renderer memory use. The existing
finite process budget/cancellation remains; large textures or complex scenes may
still exceed it. Change review/undo, preview identity and new saves retain geometry.
Changing dimensions marks a prior successful image stale. If a PNG IHDR is
available and reports a different size, that output is refused and the last
successful preview remains.

V14 native definitions store the chosen geometry. Earlier recognized versions
retain their original 800×600 value when reopened; opening never rewrites them.
Choose a new size and save a new copy to upgrade deliberately. Apply still reviews
an explicit local desktop geometry; saved preview dimensions do not silently change
the desktop or certify another aspect ratio.

## Diagnose resources

**Diagnose resources** explicitly runs the currently selected executable's version
probe and one finite verbose preview. It uses a private workspace and HOME, with
no provider requests, installers, desktop changes or service calls. Ordinary health
inspection does not execute the binary. Normal Preview does not implicitly add a
version probe. Missing prerequisites leave existing source files unchanged.

The probe has up to five seconds, inside the preview's overall process-wait budget
(default thirty seconds). Owned process-group cleanup also runs on failure, timeout
and cancellation. Diagnostics do not discard a prior successful image; successful
diagnostic images join the same two-preview comparison history. Cancellation keeps
the editor open; its evidence remains available through Configuration health.

Child output is drained into a bounded 32 KiB head/tail buffer, rather than an
unlimited log file. Reports explicitly flag omitted output and interpret at most
128 recognized lookup rows from the retained excerpt. Unknown formats remain raw
evidence. Terminal controls are escaped; paths may still be private. Review a
report before sharing it. Raw lookup reports are session evidence, not written into saved scenes. Explicit
binary probes also save a private shared support cache (below).

## Binary support versus configuration problems

Upstream Xplanet's `-version` prints its version and compile-time support list.
The diagnostic preserves that raw report and binds it to the chosen binary's
identity. It does not depend on an installation method, package receipt or retained
build log. Changed executables invalidate old evidence. Preview binds a stable readable
regular executable (up to 512 MiB). A metadata-only change during a version probe or rendering is
accepted only after verifying identical bytes; real byte changes are refused.
Later identity changes still mark retained previews stale, without deleting them.

A complete recognized successful report distinguishes listed support from a
required feature not listed. Configuration health gives actionable guidance when
PNG output or a selected texture format is explicitly unsupported: changing scene
settings cannot enable a missing compiled feature. A failed, truncated, unfamiliar
or stale probe means **unknown**, not “feature missing.” Select a compatible build
or consult its build instructions; the configurator does not recompile it.

These are not the original `configure` arguments, compiler options or optimisation
flags. Linked-library tools can corroborate some dependencies, but static libraries
may be absent from their listings. Compiled SPICE support does not establish kernel
availability/date coverage; FreeType support does not establish that a font exists.
Version strings may describe runtime library versions as well as compiled features.

## Lookup and render evidence

For the recognized verbosity format, reports show paths the renderer reported
finding and not-found search attempts. A miss followed by a later successful path
is normal search behavior, not a failed data source. A reported found path is not
independent proof that the image decoded correctly. Unsupported log formats or
missing rows leave resource resolution unknown.

The report separately records the process outcome, PNG signature and available
IHDR dimensions. Those do not certify the complete PNG, every renderer feature,
all incidental-body textures or astronomical accuracy. Raw warnings remain visible;
there is no heuristic “all green” classification based on exit zero alone.

Evidence belongs to that scene/time/geometry and executable attempt. It is not a
live watcher of assets or an assertion about the currently running desktop.
See [the configurator guide](reference.md) and [Apply boundaries](apply-design.md).

## Renderer support outside the studio

From the checkout, explicitly capture the renderer selected for the next desktop
start (immutable scene selection wins, otherwise the trusted legacy xp.def):

```sh
./scripts/xplanet.sh diagnostics
./scripts/xplanet.sh diagnostics --show
# Before setup, or to inspect another local executable deliberately:
./scripts/xplanet.sh diagnostics --renderer /absolute/path/to/xplanet
```

Without desktop configuration, the default command identifies its PATH choice
explicitly. An invalid selector/configuration does not silently fall back. An
explicit `--renderer` inspects that choice, not necessarily the desktop choice.
Custom configuration resolution uses the same trusted shell definitions as start; this is not an
arbitrary-config import tool. This diagnostic needs the existing compatible Python
selection, but does not need Textual or its prepared environment. It installs nothing.

The version child receives only finite-output arguments and a private temporary
HOME/configuration/workspace. Its wait budget is five seconds; owned process cleanup
and bounded output draining can add time. A pipe still held by a detached child
is annotated and closed on the parent side after two seconds of draining; the
escaped child is not signaled and such an incomplete version report stays unknown. Binary identity reads (up to 512 MiB) and
filesystem operations are not hard wall-clock guarantees. A selected executable is
trusted local code: this is not a sandbox for untrusted programs. No provider fetch,
service operation or desktop activation is requested.

The bounded combined stdout/stderr excerpt, UTC, resolved path, identity, exit and
recognized support list are atomically saved in the private owner-only file
`.state/configurator/binary-evidence.json`. It holds one last completed probe, even
when that probe failed; it is not a success log. Controls are escaped on display;
non-UTF-8 bytes are represented with replacement characters. Truncation is explicit.
Review local paths before sharing. Concurrent completed probes replace the cache
atomically; they cannot leave a partially written report.

`--show` reads the cache without executing Xplanet and compares its recorded file
metadata against the currently resolved choice. A different/replaced executable
makes this evidence stale; metadata equality is not a fresh byte audit or proof of
running-process identity. Full explicit probes verify stable executable bytes across
the attempt. Exit 0 means recognized support (and matching metadata for `--show`),
1 means inconclusive/stale support, and 2 means resolution, storage or inspection
failure. A missing cache is unknown. No failure is interpreted as unsupported.

The studio reads this cache without probing; its normal identity checks mark old
or different binary evidence stale. Explicit **Diagnose resources** refreshes the
same binary cache while retaining its separate scene-specific lookup/render report.
Management displays only the last recorded outcome/time, explicitly unverified for
next start/running; it does not source xp.def, hash executables or invoke Python to
populate that line. Use the explicit diagnostic to revalidate. Normal startup and
source health remain independent of this probe.
