# Frozen NORAD and eclipse layers

The Earth editor can explicitly capture **existing TotalMarker output** for two
separate layers. Neither capture contacts a provider, invokes producer refresh,
performs recovery or changes the original files.

1. Choose Earth and set the desired layer to **Use frozen capture**.
2. For NORAD, choose **Now**. An eclipse may be captured while **Now** remains
   selected: its path stays inactive until you choose a covered Fixed UTC.
3. Review the capture source root and configuration filename, then choose
   **Capture existing NORAD…** or **Capture existing eclipse…** and confirm.
4. Read configuration health and the capture summary: selected NORAD IDs/epochs
   or the eclipse kind/date/coverage, last success/publication and any saved failure.
   Then choose **Fixed UTC** inside the displayed eclipse coverage if using that layer.
5. Preview, save a new scene or cancel. No desktop selection or restart follows a
   capture or save. Original data is never rewritten.

TotalMarker's optional producers must already have generated complete supported
files in the explicitly selected source root. This UI does not enable producers,
download an old event or find historical TLEs. Source input paths are not saved
in the scene. The stdlib `configurator.astronomy_capture` API validates immutable
snapshots; Textual only presents the explicit workflow.

## Evidence and refusal

Both product files must match saved publication hashes **and** the saved paired-body
hash. Configuration, state and both source files are checked again before accepting
the capture. Any pending product journal fails closed; bounded retries handle changed
snapshots without attempting recovery. Inputs use existing no-symlink, regular-file,
size-bounded readers. Each product file is limited to 256 KiB/4096 printable ASCII rows;
metadata is limited to 8 KiB. Frozen payload names and hashes are allowlisted and
revalidated when constructing a snapshot. These hashes establish consistency, not
authenticity or scientific certification.

Common facts distinguish check, request attempt, last success and publication.
A recorded failure may coexist with validated last-good bytes; it is retained as a
failure fact rather than relabeled as fresh provider access. Reading a frozen capture
performs no network access.

## NORAD policy

- Require a nonempty, coherent selection of 1–16 representable one-to-five-digit
  catalog IDs and matching selector/TLE rows.
- Reuse TotalMarker's actual TLE checksum, orbital-field and epoch validator;
  require the saved oldest epoch to match the parsed elements. The saved configured
  maximum age is preserved. Future-epoch tolerance remains the producer's 24 hours.
- Availability is Earth/Now-only. A current TLE is not an historical/future orbital
  archive. A frozen TLE also becomes stale; propagation is not live tracking or a
  guarantee of positional accuracy.
- Supported native captions, colors, bounded trails, transparency, altitude circles
  and alignment are preserved. Optional PNG icons are frozen from existing source
  images only: at most one per selected object, 1 MiB and 512×512 per icon, bounded
  noninterlaced pixel decoding. Unsupported formats or missing/unsafe dependencies
  refuse capture rather than silently removing icons. Ancillary metadata is stripped;
  raw source hashes remain distinct from normalized frozen-image hashes.
- Named scenes prefix and verify icon references with their associated files;
  reopening restores the same canonical capture identity. Recovery preserves all
  baseline/current references within its existing aggregate object/byte quotas;
  quota refusal retains the previous complete checkpoint. No provider is refreshed.
  Active NORAD desktop handoff remains refused, and archive sharing v1 continues
  refusing any retained provider capture, including inactive icon-bearing NORAD.

## Eclipse policy

Eclipse paths are **dated predictions**, not current weather. The paired marker/arc
files must describe one recognized Total/Annular/Hybrid central event, with bounded
coordinates and increasing timed samples whose endpoints agree with saved coverage.
Only the producer's known wallclock countdown/context pixel notices are removed;
unknown notices are refused. Native timed geographic labels and path attribution
remain. General scene date/time labels are unrelated and are not removed.

Editor availability requires Earth and **Fixed UTC** inside the saved central-path
sample interval, inclusively. Now keeps the choice and captured bytes but omits
the eclipse path and explains how to choose the event time. A fixed UTC inside that interval is legitimate even when the
scene date is historical/future relative to the editor's wallclock. This does not
relax the Now-only rule for storms, volcanoes, earthquakes, live-derived clouds or
current TLEs. Sample coverage is not a claim to cover every eclipse contact.

The producer intentionally writes header-only files outside its display window.
Saved state retains dates but not all original coordinates, so this API **refuses
header-only or incomplete path output** rather than reconstructing an event. A complete
preserved prediction may still be reused for its matching event time after that event
has passed in wallclock time. For an already saved NASA-format path table, use the explicit local import below;
no acquisition is performed. Local import can cover one UTC midnight only with an
explicit **first timed row UTC date**, supplied from independent evidence. The event
title alone does not establish whether rows start on the event day or preceding day.
Only those two dates are accepted, and the resulting monotonic interval must be
shorter than 24 hours and include the header event date. Multiple rollovers,
duplicate/backward labels and inconsistent coverage are refused. The first-row date
is recorded as user-supplied and unverified, not NASA-certified chronology.

Producer output and older unpublished local midnight captures lack this independent
day association and are refused with local-import guidance. Ordinary prior same-day
captures remain readable unchanged. Fixed-UTC availability includes both explicitly
dated covered days and their exact endpoints.

## Offline local NASA-format path import

With the Earth eclipse layer selected, **Import local NASA-format path…** accepts
an explicit regular local file (up to 2 MiB), an official event reference URL and,
for a midnight crossing, the first timed row UTC date. Leave the date blank for an
ordinary same-day table.
The URL is never fetched. No source file, producer state or provider configuration
is written. A matching format/header/URL and content hash establish internal event
consistency, **not NASA authorship, authenticity, a live download or scientific
certification**. The current parser requires complete central-path limits and
consecutive 120-second timed rows; other cadences/unsupported content fail safely.

Provenance records the input bytes/hash, normalized public event reference and
explicit unverified local origin. Your pathname and raw HTML are not saved. Producer
check, request-attempt, success and publication facts remain unknown rather than
being manufactured from import time. Only bounded derived native paths are retained,
using fixed neutral styles and no wallclock countdown/update labels. Review the shown
coverage, then choose a covered Fixed UTC. Now remains inactive; importing does not
silently change scene time. Normal save/reopen, recovery and reviewed static handoff
preserve this provenance. Existing ordinary same-day producer captures remain readable unchanged.

## Save, recovery, comparisons and desktop handoff

New generated copies use scene format v16. Older recognized scenes still open
without changing their source bytes and default these layers Off. Named pairs
retain product-scoped metadata and payloads, for example:

```text
event.def  event.conf
event.frozen-norad.json
event.frozen-norad.satellites  event.frozen-norad.satellites.tle
event.frozen-eclipse.json
event.frozen-eclipse.markers  event.frozen-eclipse.arcs
```

Both captures can coexist. Save/reopen, unchanged native copy, undo/redo and
private recovery preserve inactive bytes and choices. The eclipse interval in the
definition must exactly match validated capture provenance; it is not a second
editable prediction. Active capture hashes contribute to preview identity and
retained preview provenance. A later failed/cancelled operation retains earlier
successful captures and previews. The shared 128 MiB session capture quota includes
astronomy history; existing data is not silently evicted. Older exact recovery
records gain Off defaults in memory; original checkpoints are not rewritten.

Stale active NORAD blocks Preview and native Save with an explicit health problem.
Preview rechecks eligibility immediately before publishing a completed image; expiry
or an invalid clock during rendering fails without replacing the prior successful preview.
Recovery still checkpoints invalid raw drafts. To save an inactive native copy,
turn the NORAD layer Off: the captured bytes remain associated. Framing sheets
refuse active NORAD and any Now-to-fixed conversion that would change astronomy
eligibility. Fixed eclipse framing sheets retain the same validated prediction
and exact event time in all three frames; inactive planetary choices remain inactive.

**Active NORAD desktop handoff is deliberately unavailable**, even when its TLEs
are fresh. Editor checks do not enforce epoch expiry in a long-running desktop.
Turn its layer Off to retain the capture in an otherwise allowed scene; no automatic
renderer stopping or Python lifecycle helper is introduced.

A matching **Fixed UTC eclipse** can use the existing reviewed handoff and immutable
scene-selection flow, with all native/captured files hash-bound and `timewarp 0`.
Complete predictions remain usable at their matching event time after the real-world
event has passed. A Now scene omits eclipse references even if its wallclock happens
to fall inside the event; this policy avoids changing native
file bytes just because time passed. Selection and restart stay separate explicit
actions, and this feature has not been validated on a live desktop or in UTM.

Scene exchange v1 explicitly refuses scenes retaining either astronomy capture,
including disabled ones. It never silently drops captures or redistributes provider
data. See [scene exchange](configurator-exchange.md),
[reviewed handoff](configurator-apply-design.md) and
[weather observations](configurator-observations.md).

New local-derived marker/arc headers explicitly say **unverified local NASA-format**.
Earlier local captures with the producer-style credit header remain readable byte
for byte; their provenance still does not establish authorship or producer success.
