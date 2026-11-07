# Planetary bodies and limits

The same scene workflow supports all eight major planets (including Earth),
the Moon and these additional bundled targets/viewpoints:

| Family | Additional targets and origins |
| --- | --- |
| Mars | Phobos, Deimos |
| Jupiter | Io, Europa, Ganymede, Callisto |
| Saturn | Mimas, Enceladus, Tethys, Dione, Rhea, Titan, Hyperion, Iapetus, Phoebe |
| Uranus | Miranda |
| Pluto | Pluto and Charon |

Each has an existing texture under `maps/solarsystem`; no files are fetched.
This is the studio's supported body list, not a complete inventory of the bundled
collection. Triton, Ariel, Umbriel, Titania and Oberon textures are already present
under `maps/solarsystem/celestia-textures/lores/` and `medres/`, but are not wired
into the studio's target, origin or system choices. Nereid has no tracked texture.
See [resource ownership and availability](../resources.md). Resource presence is
checked for the selected maps; this does not certify orientation, coverage, epoch
or scientific accuracy. Pluto/Charon maps and geometry
are legacy material, not a reconstruction of New Horizons observations. Satellite
shapes and orbits are simplified; small irregular moons are not shape-model views.

Choose a projected map or a space view. In space, choose a distinct body as origin,
or geographic coordinates/range. Projected maps ignore retained body origins.
Miranda, Pluto and Charon use east-positive longitude like Uranus, Earth and the
Moon; other added moons follow the renderer's west-positive convention. The
camera context explains the convention. Inactive Earth layers remain saved,
without placing Earth clouds or observational markers onto another body.

## Time and ephemerides

Fixed UTC input normally spans 1800–2200. For an active Pluto/Charon target or
space origin the studio uses **1800–2099**. This conservative UI policy stays
inside the normalized interval used by the bundled Pluto-series implementation;
it is not a certified validity interval or an engine hard limit. Earth retains its
existing date rule. An inactive origin or inactive fixed time is not discarded.

The reviewed upstream Xplanet 1.3.1 source uses `libephemeris/EphemerisLow.cpp`
when no JPL file is specified, satellite theories in `libephemeris/libmoons`, and
`libephemeris/pluto.cpp` for Pluto. The latter normalizes against JD 2341972.5
plus 146120 days (roughly 1700–2100). Major-planet precision comments cannot be
extended to every satellite or body orientation. Charon uses an older orbital
approximation. This editor does not load external JPL files or SPICE kernels,
probe their coverage, certify eclipses, or assert that all renderer builds behave
identically. Successful finite renders establish execution, not astronomical truth.

## Stock relationship views

`europa-from-jupiter`, `mars-from-phobos`, `saturn-from-titan` and
`pluto-from-charon` use the shared stock-scene picker and save as new user scenes.
They use fixed 2000-01-01 12:00 UTC. Europa-from-Jupiter retains radius framing;
Mars-from-Phobos uses FOV 80°, Saturn-from-Titan 25° and Pluto-from-Charon 20°.
These relationship scenes do not magnify moons or promise another visible body.
See the [current stock collection](stock-scenes.md) for the additional
paired viewpoints and separately labeled orbital Earthrise scene.
Unconfigured bodies may enter a space view according to renderer geometry. [Bundled system composition](systems.md) configures supported
companions with optional explicit enlargement. General per-body visibility, arbitrary
trajectory editing, custom rings and event presets remain
separate work. No install, desktop, provider or Apply action occurs here.


[Illustrative orbital guides](orbits.md) provide a bounded local
path layer; their sampled time footprint has stricter date-edge checks.
