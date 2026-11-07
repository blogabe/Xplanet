# Advanced astronomy workflow assessment

These are separate conditional workflows, not settings that can be enabled from
an example filename. The installed Xplanet 1.3.1 resource library supplies useful
recipes, but build support, data readiness, date coverage and visual correctness
must be checked independently. No downloads, generation, playback or activation
are performed by this assessment.

## Atmosphere: prepare before exposing a switch

`scattering/earthRayleigh` is a specification, not generated disk/limb lookup
intensity tables. The first useful implementation slice is an explicit preparation
command operating in a new private directory: validate the bounded specification,
show intended outputs/storage, generate under a supervised process budget, inspect
completeness, then offer finite A/B previews. Record spec hash, renderer identity,
generation parameters and all output hashes. Never generate in the installed
package or mutate source textures. Failed/cancelled attempts keep the prior complete
cache. A scene may reference only a complete reviewed set; table presence is not
atmospheric accuracy certification. Generation cost and table compatibility still
need controlled native measurements before selecting default budgets.

## Historical flybys: freeze individual frames first

The distributed Galileo and Cassini origin files are historical data, not current
mission positions. The inspected example periods are December 7–8, 1995 (Galileo)
and June 30–July 1, 2004 (Cassini), sampled at two-minute intervals. Treat these as
illustrations until their provenance and coordinate conventions are verified.

Xplanet's non-interpolated `-origin_file` playback replaces the requested frame
count with its input row count. **`-num_times 1` alone does not bound it.** The
existing one-row lunar `-dynamic_origin` camera is a different, deliberately fixed
workflow. Do not combine these strategies or import the entire example into an
ordinary preview.

The smallest safe extension is explicit date selection from a bounded validated
trajectory, extracting one reviewed row into a private scene-owned origin snapshot.
The observer body/radius units, UTC, longitude/localtime choice and camera strategy
must be explicit. Follow with a separate finite batch controller: approved frame
indices, independent per-frame process/time budgets, aggregate pixel/storage/frame
limits, cancellation and verified output manifests. Render individual rows rather
than trusting native playback's frame cap. A video encoder is a later, optional
dependency, not implied by finite image support. Longitude wrapping, midnight
localtime behavior and out-of-coverage interpolation need source-backed tests.

## External ephemerides and SPICE: data coverage is the gating dependency

The installed example `.krn` lists refer to kernels but do not contain them.
Likewise, `ephemeris/README` is not a JPL ephemeris. CSPICE in `-version` establishes
compiled support only. The documented external JPL formats are DE200/405/406;
newer DE formats must not be advertised without actual compatibility tests.

A useful first slice is a read-only manifest inspector: explicit local kernel/DE
files, bounded paths, file hashes, required companions and independently obtained
coverage. Missing or unknown coverage stays Unknown. It must distinguish planet
centres from system barycentres and ensure spacecraft and parent-body ephemerides
are consistent. SPICE trails use days; NORAD trails use minutes. Old sample URLs
and kernel comments are not proof of availability or actual interval coverage.

A later import/preview workflow requires a chosen mission/body/date, lawful data
source, complete kernel set and a reliable coverage-inspection mechanism. No new
scientific library or kernel download is selected by this assessment. Without
those inputs, exposing `naif<ID>` or `spice_ephemeris` would be a misleading feature.
A validated native render demonstrates execution; precision claims require separate
reference comparisons and stated tolerances.

## Recommended implementation sequence

1. Explicit read-only inventory and prerequisite report, already independent of
   binary support and finite diagnostic evidence.
2. One-row historical trajectory snapshot with strict date/body semantics and
   fixture-backed native render comparison.
3. Measured scattering preparation experiment in disposable storage, then a
   complete cache/scene ownership design.
4. Explicit local ephemeris manifest/coverage inspection, followed by one chosen
   spacecraft scene only once its data set is complete.
5. Finite batch/image sequence export and optional encoding after per-frame
   semantics, cancellation and publication are proven.

No user decision is needed to document or test these boundaries. A specific mission,
time range, external dataset source or optional dependency becomes a decision only
when implementing the corresponding data-acquisition/coverage workflow.

References: [Xplanet manual](https://xplanet.sourceforge.net/README),
[body configuration](https://xplanet.sourceforge.net/README.config),
[Xplanet 1.3.1 source](https://sourceforge.net/projects/xplanet/files/xplanet/1.3.1/),
and the installed `origin`, `spice`, `ephemeris` and `scattering` READMEs.
