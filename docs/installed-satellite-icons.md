# Import installed satellite icons

This optional offline tool copies explicitly selected `iss.png`, `hubble.png` or
`shuttle.png` from an existing Xplanet installation into an explicit project's
`images/` directory. Nothing is imported automatically, and no package files are
modified. It does not fetch orbital data, change TotalMarker settings, select a
scene, schedule a job, or start/restart the desktop.

The Python 3.11+ interpreter is selected through the existing
[TotalMarker runtime selection](python-runtime.md). No Textual setup is needed.
The wrapper works from any current directory and ignores an inherited
`PYTHONPATH` for module lookup.

## Preview, then import

Choose the installed resource directory that contains `images/README` and the
icons. Choose the destination project separately; its `images/` directory must
already exist. Both paths must be absolute physical paths with no symlink
components. Homebrew's `share/xplanet` is often a symlink: resolve your chosen
installation with `cd` and `pwd -P`, then inspect the resulting versioned path.
The tool never searches Homebrew, a home directory, PATH, or the network for
images and never falls back to another root.

For example, replace both placeholder paths before running:

```sh
installed_root=$(CDPATH= cd -- /chosen/installed/share/xplanet && pwd -P)
project_root=$(CDPATH= cd -- /chosen/project && pwd -P)

/path/to/checkout/scripts/import-satellite-icons \
  --resource-root "$installed_root" --project-root "$project_root" \
  --icon iss --icon hubble --dry-run
```

Preview is the default, even without `--dry-run`. It reads and validates the
selected files, reports their hashes and proposed destinations, and writes
nothing. Add `--json` for structured output. To create the reviewed copies,
repeat the same selections with `--import` instead of `--dry-run`:

```sh
/path/to/checkout/scripts/import-satellite-icons \
  --resource-root "$installed_root" --project-root "$project_root" \
  --icon iss --icon hubble --import
```

Import validates the current source again; a previous preview is not a lock on
its bytes. Each requested icon creates exactly three new files:

- `images/iss.png`: the original PNG bytes, unchanged.
- `images/iss.png.source-readme.txt`: the installed `images/README`, verbatim.
- `images/iss.png.import.json`: original and normalized PNG hashes, attribution
  hash, logical source name and the original-terms notice. It omits local paths.

The same naming applies to Hubble and Shuttle. Retain the sidecars with the image.
The receipt records a local copy, not proof of upstream authorship or a license
grant. No installed imagery is added to the public repository by this workflow.
See [asset credits and third-party terms](asset-credits.md).

## Deliberate use after import

TotalMarker already requires a configured satellite icon to be a safe basename
inside the project's `images/` directory. An imported `iss.png` can therefore be
referenced as `icon = "iss.png"` in an explicitly configured NORAD profile. This
tool does not add or edit that profile, enable NORAD, associate a spacecraft with
a catalog ID, or copy the installed historical sample TLE. See
[the optional product settings](../config/totalmarker.example.toml) and
[NORAD capture policy](configurator/astronomy-capture.md#norad-policy).

The configurator's existing NORAD capture validates and freezes the referenced
project PNG, strips ancillary PNG metadata, and records raw/normalized hashes.
That separate capture does not embed the import attribution sidecars; retain them
with your project and preserve source credits when redistributing imagery.
Importing an icon alone does not make a scene's orbital elements current.

## Bounds and failure behavior

- The initial allowlist is ISS, Hubble and Shuttle only. Specify each at most
  once. Other installed icons, arbitrary paths, directories and archives are not
  accepted.
- Each icon must be a noninterlaced PNG of at most 1 MiB and 512 × 512 pixels,
  passing the same bounded container/pixel-stream checks as frozen NORAD icons.
  This is not a render test or a certification of image content.
- Installed `images/README` is required, must identify each selected basename,
  and must be nonempty UTF-8 text of at most 64 KiB. It is preserved exactly;
  historical links and upstream statements are not rewritten as modern terms.
- Source and destination paths are pinned and checked for replacement. Symlink
  components, symlink files, special files, missing roots and changed inputs are
  refused. Only explicitly selected source files and their README are read.
- An existing destination image **or sidecar**, including a dangling symlink,
  refuses the whole batch before any copying. There is no overwrite option.
  Existing custom images and other project files remain untouched.
- Files are created exclusively, then written from validated in-memory bytes
  through held file descriptors. Their content and path identity are checked
  before success. Attribution and receipt precede each PNG. This is not a
  crash-atomic file or batch transaction: a late race, disk error or interrupt
  can leave new, possibly incomplete files. The error lists created files;
  inspect them before retrying. A hard process termination may prevent that
  report, so also inspect the requested destinations. Error handling never
  overwrites or removes an existing destination.

Normal success exits `0`; validation or filesystem refusal exits `2`. No provider,
renderer, shell configuration, desktop or launchd operation is run by the import.
