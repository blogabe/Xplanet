# Lunar orbital camera and frame centre

The [studio](reference.md) can place a fixed-time observer above the Moon,
looking at another target. Choose **Space**, **Moon** as observer, **Lunar orbital
camera**, and **Fixed UTC**. Other origins retain their body-centre behavior.
Map mode or another origin retains the lunar choices without using them.

- Lunar latitude: −90° to 90°; longitude: east-positive, −180° to 180°.
- Range: 1.1–100 lunar radii **from the centre**, not altitude above the surface.
- Frame centre X/Y: 0–100% from left/top, available in space mode. The default
  50/50 retains the engine default centre; explicit offsets are rounded to pixels
  using the requested output dimensions. Changing preview size or reviewed desktop
  geometry recomputes those pixels from the saved percentages.
- FOV/radius remains independent framing. A large nearby Moon can clip/occlude
  the target; there is no automatic horizon fit or terrain collision detection.

These are spherical orbital views using this build's geometry and static bundled
Moon map, not surface panoramas, DEMs, spacecraft ephemerides or reconstructed
Apollo photographs. Close-range distortion and the engine's projection/body
approximations are not scientifically certified. Lunar limb appearance depends
on the camera and scene epoch. A near-Sun Earth is crescent/dark; a bright full
Earth beside the Sun would need explicitly artistic changes.

## Earthrise-style starting point

**Stock scenes… → earthrise-lunar-orbit** uses fixed 2000-01-18 12:00 UTC,
latitude 0°, longitude 145°, range 2 lunar radii, FOV 120°, rotation −90°, frame
centre 50% / 83⅓%, and 1920×1080. The finite tested composition includes a lunar
limb below, a small crescent Earth above it and the Sun higher in the frame.
Incidental bodies/labels may appear. It is an **orbital Earthrise-style** scene,
not a Moon-surface view or a certified historical event. Keep the separate
`earth-from-moon` preset for the body-centre view.

Open, revise, preview, save a new copy or cancel normally. The original stock
files stay unchanged. Changing camera/time/centre makes prior previews stale;
invalid intermediate edits remain undoable. Now is deliberately blocked for an
active lunar orbital camera rather than silently freezing a supposedly live clock.

## Native data and deployment

V15 native pairs retain camera mode, lunar coordinates/range and centre percentages.
Older recognized versions keep body-centre/default-centre behavior. They cannot
silently discard new camera settings on an older-format save. A generated named
scene also has `scene-name.camera.origin`: one bounded coordinate row whose exact
bytes are validated against its definition. No imported origin file, script,
trajectory or arbitrary dynamic camera is accepted. The Moon texture is an
explicit checked scene asset, not an incidental unbound lookup.

The renderer reads this **frozen** row using its documented `-dynamic_origin`
input; its name does not mean the studio fetches or animates coordinates. Fixed
UTC is passed separately. This avoids `-origin_file`, which replaces the requested
frame count with its row count. Previews still request one frame. Reviewed desktop
handoff uses the immutable coordinate snapshot and `-timewarp 0` without forcing
the persistent renderer to exit after one frame. No desktop or launchd operation
is part of Preview or Save.

Named save/reopen, review-only export, immutable selection and zsh literal runtime
validation include the camera file's hash. Missing, linked, edited, multi-row or
mismatched inputs are refused. Frame centre is calculated for the explicit reviewed
desktop dimensions, not copied as stale preview pixels. Apply/restart retain their
[existing separate contracts](apply-design.md); no user installation
was activated while developing this feature.
