# Bundled planetary system composition

Choose a supported parent target in **space mode**, then select **System textures**:

| Parent | Configured bundled companions |
| --- | --- |
| Mars | Phobos, Deimos |
| Jupiter | Io, Europa, Ganymede, Callisto |
| Saturn | Mimas, Enceladus, Tethys, Dione, Rhea, Titan, Hyperion, Iapetus, Phoebe |
| Uranus | Miranda only; other Uranian moons lack bundled maps |
| Pluto | Charon |

The existing camera, origin, date, range, framing and rotation are unchanged.
There is no auto-fit. Lower target-radius framing can reveal more of a system,
but distant moons may still be outside the image or behind the observer. Bodies
unconfigured by this mode remain eligible for the renderer's normal space view;
this is a known-texture composition, not an isolated visibility layer.

## Scale and visibility are different

**Moon visual enlargement** accepts 1–10×. The default 1 preserves the renderer's natural body sizes.
One shared factor applies to the configured moons, never the parent target.
Larger factors change rendered disks, not orbital positions. Overlaps, apparent
contacts and shadows in enlarged images are not reliable physical events. Health,
scene summaries and saved native files identify the factor. Small moons may still
be rendered as points; enlarging a subpixel moon does not always change an image.

There is deliberately no Hide checkbox. In reviewed Xplanet 1.3.1
`drawMultipleBodies.cpp`, a disk radius at or below one pixel is still plotted as
a pixel. `magnify=0` therefore does not hide a body; using it would promise the
wrong behavior. Negative magnification is reset by the engine. General per-body
visibility and custom ring editing remain
unimplemented. No upstream renderer modification is made here.

System mode and its scale remain stored but inactive in projected maps, Earth
views or unsupported targets. Default target mode reproduces the existing body
configuration. Grid and the existing shadow-brightness control apply to the target only;
companions retain the normal shade fallback. Body-name labels remain suppressed
as in the existing planetary workflow. The independent UTC scene label is unchanged.
No Earth clouds, markers or observational products are placed on these systems.

## Save, preview and limits

V11 generated definitions explicitly store `XPLANET_COMPOSITION` and
`XPLANET_SATELLITE_SCALE`; native `.conf` files contain the known ordered body
sections and `magnify` settings. Strict reopen refuses edited/unknown fields.
V2–V10 and foundation scenes still reopen with target mode and scale 1. Saving a
new copy never rewrites its source. Inspection's original-byte copy remains distinct
from generated Save. No arbitrary native import or Apply is introduced.

The existing [planetary date and asset limits](configurator-planetary.md) apply,
including the conservative fixed-time Pluto/Charon guard. No new ephemerides,
provider refresh, package installation or network access is used. Textures and
simplified geometry are not scientifically certified. Retained previews preserve
their own scale; failed or cancelled attempts do not erase prior success.

Stock scenes use fixed 2000-01-01 12:00 UTC. `jupiter-inner-enlarged` and
`saturn-inner-enlarged` use 10× moons to make nearby companions visible;
`pluto-charon-system` uses physical sizes. Open, revise, preview and save a new
named copy. Enlarged presets are illustrative, not event reconstructions.


A bounded [orbital-guide layer](configurator-orbits.md) is now available for
configured moons, with explicit sampling and shared style. It does not change
camera framing, orbital positions or the visibility limitation described above.


## Individual moon scales

**Individual moon scales…** opens a draft-only dialog for the current family.
Choose a moon and enter 1–10×, or leave it blank to inherit the shared scale.
Overrides **replace**, rather than multiply, the shared value. An explicit 1× can
keep one moon at the engine's natural size while others inherit enlargement.
Zero is invalid and does not provide hiding.

Invalid intermediate text survives selecting another moon in the dialog. **Use
overrides in draft** validates the entire table and creates one undoable main-draft
edit; it does not preview, save or Apply. **Cancel edits** or Escape leaves the
draft unchanged. Other-family values remain stored when switching targets. Returning
to their system restores them. No-op dialog results preserve the original metadata.

Health lists effective enlarged bodies rather than assuming every moon uses the
shared factor. Redundant overrides and unused shared defaults do not falsely mark
a preview stale. Effective disk scales remain independent of orbital guide centers,
positions and existing date policies. No physical-event fidelity is claimed.

V13 definitions retain the bounded `XPLANET_MOON_SCALES` scalar table; the native
body writes each effective `magnify` value. Earlier scenes reopen with no overrides.
Mixed-scale bodies use an exact known v13 layout; uniformly scaled bodies retain
the earlier body layout. There is no new configuration file or parallel store.
Source files are never edited in place. `jupiter-europa-enlarged` and
`saturn-titan-enlarged` illustrate one moon at 10× while others remain at 1×.


A wider Uranus view can expose unconfigured moons such as Ariel. The renderer may
report a missing texture and still produce an image with fallback appearance.
Health explicitly warns about this coverage gap. No map is fabricated and the
warning is retained in render diagnostics. Titan's known PNG profile warning can
also appear when its map is actually decoded; the asset is not silently altered.
