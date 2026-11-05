# Scene exchange

Scene exchange is an explicit, stdlib-only command for sharing **recognized
configurator-produced scenes** as data. It does not run imported definitions,
render images, contact providers, install dependencies, select a desktop scene or
restart anything. The editor exposes **Export saved scene…** and **Import scene
archive…**; the same stdlib CLI remains available. Ordinary Open still opens native
scene pairs, not ZIP archives.

## In the editor

**Export saved scene…** asks for a saved named .conf/.def pair or legacy scene
directory and a new destination directory. The source is read again when confirmed.
The unsaved draft is never silently saved or exported, even when the current saved
scene is prefilled. Save a new scene first if you want to share draft changes.
An optional manually chosen PNG is an illustration; the editor does not attach its
latest preview automatically or assert that it matches the chosen saved scene.

**Import scene archive…** asks for the archive and a new destination directory. It
uses the current local renderer reference, never an executable path supplied by an
archive, and does not run the renderer. The new copy contains xp.conf/xp.def, associated
recognized files and a receipt. After success, the normal **Open view** dialog is
offered: Back keeps the current draft; Open explicitly replaces it, with an additional
warning/confirmation label when it is dirty. Opening revalidates the copy and keeps
the editor's current local renderer. To put an imported scene in the flat named
library, optionally open it then use the ordinary Save workflow with a new
config/scenes/scene-name.conf destination.

Opening or cancelling an exchange form writes nothing. Confirmed operations run in
an owned, bounded subprocess using the existing API; cancellation/exit reaps it rather
than leaving a background writer. A cancellation, timeout or interrupted publication
may leave a partial **or complete** new destination: inspect it before retrying. No
rollback or destination deletion is promised. The last exchange outcome or inspection
warning is printed after the editor restores the terminal, including emergency exit;
it does not change draft/selection exit codes. Prior drafts, source files, previews and
successful copies remain. Destinations inside the editor's temporary preview workspace
are refused so editor cleanup cannot remove an exchanged copy.

## Command line

From the repository root, using your selected compatible Python 3.11 or newer:

```sh
PYTHONPATH=scripts python3 -m configurator.exchange --export /absolute/config/scenes/europa.conf --destination /absolute/new-package
```

The destination must be a **new directory** in an existing real parent. The result
is `new-package/scene.xplanet.zip`. Export also accepts a legacy generated scene
directory containing `xp.def` and `xp.conf`. It reads only the loader's recognized
native pair and associated places/routes/orbital-camera data, not neighboring
files. Unsupported or hand-edited definitions are refused. Originals stay unchanged.

An optional `--preview /absolute/preview.png` includes an illustrative PNG. It is
not proof that the image matches the exported scene: render it deliberately and
review it before sharing. Ancillary metadata is removed; pixel data remains visible
and may itself contain personal labels. Supported PNGs are noninterlaced, at most
4096 pixels per side and 8,388,608 pixels total, with bounded decompression.
Metadata removal can alter color interpretation. This is not image certification.

To import into a separate new directory:

```sh
PYTHONPATH=scripts python3 -m configurator.exchange --import /absolute/scene.xplanet.zip --destination /absolute/new-scene --renderer /absolute/path/to/xplanet
```

The renderer path is validated as an existing executable but **never executed**.
The imported `xp.def` uses that local renderer and this checkout's asset root.
Open `/absolute/new-scene` or its `xp.conf` with the configurator afterward. The
usual explicit scene review/selection and separate restart remain separate. Existing
files and directories are never overwritten. An `exchange-receipt.json` records
the archive hash and original member hashes, without sender paths.

## Scope and privacy

- Version 1 exchanges scene settings and supported user-authored places/routes and
  camera data. It normalizes generated native files to the current recognized format;
  it is **not a byte-preserving native-file backup** or arbitrary-config importer.
- Bundled maps, imagery, fonts and renderer binaries are **references only**, not
  redistributed. The recipient needs the corresponding compatible project assets
  and renderer resources. Stock renderer lookups and build capabilities remain local
  requirements, not archive guarantees. Third-party terms remain unchanged.
- Frozen provider captures are refused, including retained inactive captures. They
  are not silently stripped. Sharing those images/observations needs a separate
  provenance, embedded-metadata and redistribution policy.
- Renderer and checkout paths, unrelated files, environment variables, provider
  credentials and source filenames are not copied. User-authored names, route text
  and rendered pixels are intentional content: inspect them before sharing. The tool
  cannot infer whether a label contains personal information or a secret.
- Hashes establish internal consistency, **not authenticity or trust**. No signature,
  scientific accuracy claim, provider freshness claim or activation is implied.

## Untrusted archive boundary

The format is a stored (uncompressed) ZIP with a canonical JSON manifest, SHA-256
hashes and sizes. It is limited to 20 MiB and ten members; recognized native inputs
have their existing smaller limits. Deflated or encrypted archives, duplicates,
subdirectories, links, special files, control-character names and unsupported native
content are refused. Image decoding is bounded. Import never calls `extractall` and
validates a private staging copy before creating the user-chosen destination.
Unexpected source changes and linked paths fail safely. Publication uses the existing
exclusive private-file writer; a failure cleans only unchanged files owned by that
attempt and preserves externally changed partial output for review.

Use `python3 -m configurator.exchange --help` with `PYTHONPATH=scripts` for the
complete command syntax. See [native preservation](import.md),
[durable image exports](export.md) and the [user guide](user-guide.md).
