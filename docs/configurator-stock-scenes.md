# Stock scenes

Open **Stock scenes…** in the [studio](configurator.md), then preview and save a
new named copy. The 24 native pairs under `scripts/configurator/samples/scenes`
are read-only starting points, separate from `config/scenes`. Opening never
adopts their illustrative executable or asset-root paths. The local renderer and
checkout supply previews; no provider refresh or desktop operation occurs.

All start at **1920×1080**, with other bounded dimensions available. Fixed-time
examples use 2000-01-01 12:00 UTC, except the orbital Earthrise scene at
2000-01-18 12:00 UTC; Now scenes sample each preview's renderer clock.
Maps are bundled/installed imagery, not historical photographs at that instant.

| Group | Scenes | Purpose |
| --- | --- | --- |
| Lunar orbital limb | `earthrise-lunar-orbit` | Fixed lunar orbital camera with a small crescent Earth and Sun; no surface/event claim. |
| Earth | `earth-solar-dawn`, `earth-september`, `earth-from-moon` | Solar-hour framing, dated seasonal imagery, body-origin view. |
| Single bodies | `moon-from-earth`, `jupiter-cloudtops`, `saturn-rings` | Phase, cloud texture, inclined ring framing. |
| Mars from moons | `mars-from-phobos`, `mars-from-deimos` | Same 80° FOV to compare near/far apparent size. |
| Jupiter from moons | `jupiter-from-io`, `jupiter-from-europa` | Same 45° FOV; no moon surface or terrain. |
| Saturn from moons | `saturn-from-titan`, `saturn-from-iapetus` | 25° and 12° FOV artistic framing; compare ring orientation. No Titan atmosphere simulation. |
| Other relationships | `europa-from-jupiter`, `uranus-from-miranda`, `pluto-from-charon` | Reverse relationship, Uranian viewpoint, close binary. |
| Enlarged systems | `jupiter-inner-enlarged`, `saturn-inner-enlarged`, `pluto-charon-system` | Explicit illustrative shared scale. |
| Selective enlargement | `jupiter-europa-enlarged`, `saturn-titan-enlarged` | One moon enlarged; others inherit the stated scale. |
| Orbit guides | `jupiter-orbit-guides`, `saturn-orbit-guides`, `pluto-charon-guides` | Sampled parent-relative guides, not spacecraft tracks or predicted events. |

## Interpretation and limits

Ordinary body-origin cameras use the origin body's **centre**. `earth-from-moon`
retains that behavior. The separate [lunar orbital camera](configurator-orbital-camera.md)
now supports `earthrise-lunar-orbit`: an offset spherical lunar observer, static
Moon texture, small crescent Earth and Sun. It was verified in a finite 1920×1080
render. It is not a Moon-surface, terrain or Apollo reconstruction.

FOV/radius and body magnification are framing controls, not a certified optical
camera or astronomical measurement. Incidental bodies may appear; the engine
has no general per-body Hide feature. Dates remain subject to the studio's
conservative backend policy, including active Pluto/Charon before 2100.

The previous 23 stock scenes were finite-rendered at 1920×1080 with the
available Xplanet 1.3.1 build; this is not certification of every scene, build,
texture orientation or future date. Uranus's acknowledged texture gap remains.
Use [configuration health and resource diagnostics](configurator-diagnostics.md)
to distinguish missing resources, explicit build limitations and unknowns.
