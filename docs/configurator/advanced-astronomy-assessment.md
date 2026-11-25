# Advanced astronomy limits

<a name="advanced-astronomy-workflow-assessment"></a>

Upstream recipes for atmosphere, flybys and external ephemerides describe
separate workflows, not scene-studio controls. Build support, resources,
date coverage and reliable finite rendering must each be established.

<a name="atmosphere-prepare-before-exposing-a-switch"></a>

## Atmosphere

An installed `scattering/earthRayleigh` specification is not a complete set
of disk/limb intensity tables. Table generation and the selected binary need
their own verification before an atmosphere recipe is usable.

<a name="historical-flybys-freeze-individual-frames-first"></a>

## Historical flybys

The distributed Galileo (December 7–8, 1995) and Cassini (June 30–July 1,
2004) origin files are illustrative historical inputs sampled every two
minutes, not current mission positions. Non-interpolated `-origin_file`
playback replaces the requested frame count with the input row count, so
`-num_times 1` by itself does not bound it. The studio's
[one-row lunar camera](orbital-camera.md) uses a different strategy.

<a name="external-ephemerides-and-spice-data-coverage-is-the-gating-dependency"></a>
<a name="recommended-implementation-sequence"></a>

## External ephemerides and SPICE

The installed `.krn` lists do not supply the kernels they name. The
`ephemeris/README` is not a JPL ephemeris. A binary reporting CSPICE support
does not establish availability or date coverage; the documented external JPL
formats are DE200/405/406. Coordinate centres, body/spacecraft coverage and
units also matter. SPICE trails use days; NORAD trails use minutes. A valid
native render shows that an input ran, not that its geometry is accurate.

See [planetary date limits](planetary.md#time-and-ephemerides),
[resource diagnostics](diagnostics.md) and the
[upstream manual](https://xplanet.sourceforge.net/README).
