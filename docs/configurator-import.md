# Native file inspection and preservation

**Inspect native files…** is a read-only review flow, separate from **Open saved
view…**. It never sources `xp.def`, launches a renderer, replaces the editor draft,
or changes the original configuration. A valid working Xplanet configuration can
be unsupported by this editor; that does not mean it needs repair.

Choose an absolute `.conf`/`.def` file or a scene directory. For custom sources,
inspection reads only the selected matching native pair (or existing member),
without following referenced scripts, images, fonts, includes or other assets.
Files must be regular, bounded and reached without symlink components. Unknown
content, comments, ordering, repeated assignments and original newline bytes stay
in the immutable snapshot. The report shows hashes and a bounded textual preview;
terminal controls are escaped and display truncation never alters stored bytes.
Custom source files are limited to 256 KiB each. No camera settings are inferred
from arbitrary code or incomplete native content.

## Unchanged means unchanged

Loading and closing inspection performs no source writes. In this inspection flow, custom
content stays read-only: there is no Edit, Render or Copy operation that might
silently omit unknown settings or associated assets. The current editor draft and
its unsaved history remain unchanged. General preservation-aware editing/import
is not implemented by this review slice.

For a **complete recognized configurator-generated scene**, **Copy original bytes**
can create an explicitly chosen new directory. It preserves every loaded native
file, its original filename/version and all recognized associated asset/provenance
bytes. It neither regenerates a definition with the current renderer/root nor
upgrades an old scene version. Unrelated files in the source directory are never
read or copied. The new files are private regular data files, not executable scripts;
source file permissions are untouched. No overwrite or in-place Save is offered.

This is a captured snapshot, not a watcher. Later external source edits remain
untouched; a copied snapshot contains the bytes originally reviewed. If a source
changes during the read it is rejected. Copy failures remove only unchanged files
owned by that attempt; externally changed partial output is retained for review.
Existing destinations and symlinked destinations are refused. Exact filename
casing must be unambiguous; an alias is not silently renamed during copying.

Open the copied `.conf` file to edit the recognized scene afterward. The normal
editor **Save** deliberately creates a new generated scene from its current draft;
it is separate from the inspection flow's verbatim copy. Neither action applies
anything to desktop settings or schedules. See [configurator](configurator.md).

General custom editing must satisfy the same acceptance condition: an unchanged
save preserves source bytes, unknown content/order/comments/repeated entries and
associated assets, or safely declines. It must not execute definitions merely to
learn settings. That broader parser/editor remains future work. A separate [native literal-copy
tool](configurator-native-values.md) can patch bounded numeric values, literal grid switches and image paths without
reconstructing the rest of a custom file; it is not general editable import.
