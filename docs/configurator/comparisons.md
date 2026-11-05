# Comparison sheets

**Framing sheet…** renders three finite snapshots with 75%, 100% and 125% of the
current radius or field of view. It is separate from **Compare…**, which compares
the two ordinary successful previews. The draft and ordinary preview history
remain unchanged.

Framing comparison supports **space views with body-centre cameras and static layers**.
All three values must fit the existing model bounds; values are not silently
clamped. The interface explains unavailable cases. Map projections, lunar orbital
cameras and active current-data captures are deliberately unsupported here.
Fixed-UTC scenes can retain inactive current-data choices, which remain omitted.
The dated 2011 cloud texture is an ordinary static layer.

Review the exact values, epoch and budget before selecting **Render set**. A Now
draft is frozen once at review time so lighting/geometry do not drift among frames;
a fixed UTC draft keeps its chosen epoch. This does not authorize historical or
future scenes to display current observational data. Current captures are refused
rather than silently removed or relabeled to produce a comparison.

Every frame is 1920×1080 (16:9), independent of the draft's saved geometry and
texture-map aspect. Three frames contain about 6.2 million output pixels. A larger
radius may crop a body; a larger FOV normally shows more sky. Framing values remain
explicit rather than implying three scientifically equivalent viewpoints.

The set has a 60-second total render-process wait budget, at most 30 seconds per
frame, and a retained PNG limit of 16 MiB per image. Cleanup, filesystem work and
texture decoding overhead are not hard wall-clock/RAM/disk guarantees. The chosen
executable is byte-checked for stability across the set. Actual resolved resources,
imagery epochs and scientific precision are not certified by a successful render.

**Open framing sheet** explicitly opens a static local HTML grid in the platform's
associated application. No viewer opens automatically. It uses relative PNGs,
escaped captions, no JavaScript or external resources and no new image-processing
dependency. It is an HTML contact sheet, not a stitched PNG, an animation, a desktop
background or an image-difference calculation. Each PNG and a small JSON record
retain framing values, epoch and image hashes.

The previous complete set survives a later failure or cancellation. An incomplete
new set is not promoted as success. Changing the draft/executable relabels the
button **Open prior framing sheet**; retained results are snapshots. Ctrl-C or
Cancel framing set stops owned work; the exit/recovery keys follow the
[draft recovery contract](recovery.md).

Only one completed sheet is retained, separately from the two ordinary previews.
The studio originals are temporary and disappear when the editor closes; a viewer
may retain already loaded pixels. **Export comparison sheet…** explicitly preserves
a complete set in a new user-chosen directory: see [durable export](export.md).
Arbitrary batch axes, live-data comparisons, contact-sheet rasterization, trajectories
and video assembly remain future choices.

## Bundled imagery months

**Imagery month sheet…** offers three distinct months from the draft's already
selected bundled Earth monthly-map family. Stock imagery has no month axis. Review
the three months and fixed epoch, then render. Camera, framing, lighting time and
all other scene choices stay constant; only the bundled imagery-month selection
changes. These are 2004 imagery-month alternatives, not three simulated seasons,
contemporary observations or certified historical imagery.

Unlike framing sheets, this axis also supports Earth map projections and orbital
cameras. It retains the same three-frame geometry, budgets, cancellation, prior
success and explicit open/export protections above. Current observational captures
and active NORAD are refused rather than re-dated. A validated Fixed-UTC eclipse
prediction can accompany all three images unchanged. The ordinary draft, preview
history and native scenes are unchanged.
