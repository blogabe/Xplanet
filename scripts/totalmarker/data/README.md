# Static volcano positions

`gdacs_volcano_coordinates_20261019.json` is a coordinate-only cache made on
2026-10-19 from the public GDACS Volcano `getvolcanoesinfoinperiod` responses
with `fromDate=2026-10-08` and both `active=true` and `active=false`.
The two disjoint responses contained 26 and 1,414 features. `properties.oid`
is the join key; `geometry.coordinates` was converted from `[longitude,
latitude]` to `[latitude, longitude]`. All 1,440 IDs were unique and their
coordinates finite and in range. This cache does not select weekly activity,
serve as a report history, or establish a GVP publication time.

GVP display names always come from its weekly report, not this cache. GVP
`Aira` (ID 282080) joins the GDACS location labelled `Sakurajima`,
31.5772° N, 130.6589° E. Matching IDs do not establish that this is GVP's
preferred current reference point. A missing future ID must fail the whole
weekly update until the catalogue is reviewed and refreshed.
