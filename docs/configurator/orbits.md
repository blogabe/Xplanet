# Illustrative moon orbital guides

In a supported **System textures** space view, enable **One nominal orbit**.
Each configured moon receives a guide centered on the scene time, with a shared
color and a whole 1–3 px line width. The target planet's solar orbit is not drawn.
Sampling is fixed at 5°; arbitrary duration, step sizes and trajectory files are
not accepted. This bounds work and avoids the engine's zero-segment division case.

These are local illustrative guides. Reviewed Xplanet 1.3.1 `addOrbits.cpp`
computes moon positions relative to their parent and holds that parent's position
at the scene epoch. The lines are not an inertial historical trail, a spacecraft
trajectory or an eclipse prediction. Enlarging moon disks does not move guide
centers. Guides may clip or be hidden by bodies; visibility and complete framing
are not guaranteed.

## Time coverage

Native `orbit={-0.5,0.5,5}` spans approximately one nominal orbital period centered
on the scene. The engine draws an extra segment after its nominal stop. Validation
includes that extension, conservatively rounded out to whole days using the
longest configured moon period in each family:

| Family | Padding before / after scene time |
| --- | --- |
| Mars | 1 / 1 days |
| Jupiter | 9 / 9 days |
| Saturn | 276 / 283 days, including Phoebe |
| Uranus / Miranda | 1 / 1 days |
| Pluto / Charon | 4 / 4 days |

For fixed UTC, this padded interval must remain within the studio's existing
1800–2200 policy, or 1800–2099 for active Pluto/Charon geometry. Health gives the
permitted date range. Turning guides off restores the ordinary single-epoch rule;
it never changes your date automatically. Inactive choices remain stored without
imposing this extra footprint. Now uses the renderer clock; this policy is not a
runtime probe or scientific certification of every build's ephemerides.

Periods and sampling behavior were checked against upstream 1.3.1 `Planet.cpp`
and `libmultiple/addOrbits.cpp`. Other renderer versions/backends may differ.
No kernels, provider requests or downloads are involved.

## Preserve and experiment

Color, width and the on/off choice were introduced in v12 and remain in v13 scenes. Earlier scene
versions remain readable with guides off. Switching away from system space mode
retains choices without emitting paths or changing effective preview identity.
Invalid widths or date footprints block preview/save; a failed attempt retains
prior successful output. Source scenes stay untouched by Save-as-new.

Stock examples `jupiter-orbit-guides`, `saturn-orbit-guides` and
`pluto-charon-guides` use fixed 2000-01-01 12:00 UTC and physical moon sizes.
Open them, revise the camera or style, preview and save a new copy. They are
illustrations, not observations. No desktop Apply or lifecycle action is performed.
