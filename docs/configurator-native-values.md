# Native literal copies

**Edit native values…** is a separate, bounded copy-on-write tool for an existing
`.conf`. It does not convert arbitrary configurations into studio scenes.
Opening, reviewing or cancelling never changes the source or the editor draft.
Definitions, scripts and referenced resources are neither opened nor executed.

Choose an absolute regular `.conf` without symlink components. In a unique literal
`[default]` or supported body section, the tool can change standalone `shade`
(0–100 integer), `twilight` (0–90 integer), `bump_scale` (0.1–5), and
`grid1`/`grid2` (1–90 integers in this tool), `cloud_gamma` (0.1–5),
`cloud_threshold` (0–255 integer), and `magnify` (1–10). Shadow shade
is not night-map brightness; bump scale needs an existing bump map to have an effect.
For an active grid, `grid1` is the number of major divisions per 90° and `grid2`
is the number of subdivisions per major interval. The editor does not enable a
grid implicitly, infer inherited state or validate a whole arbitrary configuration. An explicit
`grid=true` or `grid=false` edit is now supported. Native
zero/out-of-tool-range values remain read-only and are preserved, not repaired.

Cloud gamma/threshold do not enable a cloud map or establish whether one exists.
Magnification is illustrative enlargement, not a physical-size/visibility control;
zero is not Hide and stays read-only. Repeated/mixed/nonliteral assignments remain
opaque. Literal `map`, `night_map` and `cloud_map` filenames can also be patched.
These accept one simple POSIX filename/path up to 180 characters using ASCII
letters, digits, dot, underscore, hyphen and slash only, with no spaces,
quotes, expansion, escapes, URLs or shell syntax. Relative paths (including parent
components) stay literal in the same directory; absolute paths are not made portable.
No referenced file is opened, copied, downloaded or certified. Unsupported current
path/switch syntax remains read-only. Color and arbitrary resource-list editing
are not offered.

An absent value is not an inferred effective value: entering one adds an explicit
override. Blank leaves the original unchanged; this tool does not delete settings.

Select a section, edit values, review the changes and confirm a **new `.conf` in
the same directory**. No companion `.def` is created. Existing destinations,
case aliases and a matching destination `.def` are refused. The original `.conf`,
companion definitions and assets remain untouched. Numerically equivalent changes
retain the original spelling; a no-op copy is byte-identical. Other bytes, including
unknown settings, comments, ordering, repeated resource entries and line endings,
are retained rather than reconstructed.

The review includes source-snapshot and proposed-copy byte counts/SHA-256 hashes,
plus escaped before/after byte spans with source line numbers and zero-based
`[start:end)` offsets. Newline bytes are shown literally; an empty before span
means insertion. A no-op explicitly reports byte identity. The span display is
limited to 32 edits with an explicit omission count; the hash always covers the
entire proposed copy. This is snapshot evidence, not a generic text diff or a
claim that the on-disk source has not changed. Save still rechecks that source.

The copy still needs the original assets, working directory, search paths and
launch arguments. It is not a portable bundle. This flow provides no arbitrary
preview, script execution, setup or Apply. Selecting the copy for actual use is a
separate operation; do not assume an existing definition automatically selects it.
Use the normal scene workflow for configurator-produced scenes.

Ambiguous sections, duplicate/mixed/nonliteral assignments and unsupported
syntax are refused or made read-only. Files are bounded to 256 KiB, lines to 240
bytes. Source identity and bytes are rechecked at save; external changes require
reopening. Failures clean only unchanged files owned by that save attempt.
These checks protect against accidental changes, not a hostile process able to
continually rewrite the same directory. General preservation-aware import remains
future work; see [native inspection](configurator-import.md).
