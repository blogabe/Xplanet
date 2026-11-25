# Tests

The public tests live here; `dev/` is ignored local evidence and working material.
Run the supported macOS stdlib suite with:

```sh
./scripts/xplanet.sh test
```

The data/configurator-model portable subset can run separately; it does not claim
macOS or Textual coverage:

```sh
PYTHONPATH=scripts:. TZ=Pacific/Auckland python3 -B -m tests.run_portable
```

Textual interactions are deliberately separate from stdlib discovery. After
explicitly preparing the isolated configurator runtime, run:

```sh
PYTHONPATH=scripts:. .state/configurator/venv/bin/python -B -m unittest discover -s tests/configurator/ui -v
```

GitHub runs the same UI suite in two parallel shards. Modules stay together
and new modules go in shard 2 unless assigned to shard 1 for balance. The
`configurator` check requires both shards to succeed. To reproduce one locally:

```sh
PYTHONPATH=scripts:. TZ=UTC .state/configurator/venv/bin/python -B -m tests.run_configurator_ui --shard 1
```

Fixtures are offline/synthetic or attributed public captures. Preserve raw fixture
bytes and `.gitattributes`.
Tests use disposable roots and stub operations; do not point them at a working
installation. See [architecture](../docs/architecture.md#verification-boundaries).

The supported macOS runner requires zero skips. The portable
runner permits five explicitly named zsh shell-boundary cases to
skip only when their required `/bin/zsh` or PATH executable is unavailable. It
does not exempt arbitrary skips by reason text. Other required checks, including
Git-index privacy, must still run; this is a capability boundary, not evidence
that the portable suite has run on every Linux host. Use a complete Git
checkout for release verification. Running selected tests directly
in a source-only copy is useful development evidence, not a verified release.
UI fixtures are plain helpers; blocking PTY tests use synchronous runners with
explicit geometry. File-identity tests use local `/tmp` storage with nanosecond
ctime/mtime evidence; a filesystem without that evidence is outside those fixtures
(the production safety checks are not weakened to make the tests pass).
Hosted CI runs the core and isolated Textual suites on macOS. The Ubuntu job
reports the combined Textual results; it does not run Linux runtime tests.

## Indexed privacy and fixture receipts

Release checks apply one shared path policy to every index entry and scan known
private identifiers in indexed text, including `.dat` and `.geojson` provider
fixtures. Working-tree replacements cannot substitute for indexed bytes. Text
and non-map binary source/fixtures each have 5 MiB per-file / 64 MiB aggregate
review budgets. Binary payloads are not decoded for arbitrary secret detection;
large shipped maps use the separate asset byte/mode checks. This is not a general
secret or license scanner.

[Selected fixture receipts](fixtures/provenance.json) pin current bytes and state
where original retrieval metadata is unknown. The historical scene
[goldens](fixtures/configurator/scenes/README.md) retain their hashes and versions.
Do not regenerate fixture bytes to accommodate current parsers.

## Explicit native resource lookup check

With an already installed Xplanet binary supporting PNG, verify finite shell
preview/render lookup against colliding maps:

```sh
PYTHONPATH=scripts:. python3 -B -m tests.native_renderer_cwd /absolute/path/to/xplanet
```

This uses disposable configurations, images and a temporary HOME under `/tmp`.
It neither starts/stops the desktop nor reads or edits a working installation.
The offline suite remains independent of a native renderer.

## Explicit native overlay check

With an installed Xplanet binary supporting PNG, verify finite renders of the
ISS and a central solar-eclipse path:

```sh
PYTHONPATH=scripts:. python3 -B -m tests.native_renderer_overlays /absolute/path/to/xplanet
```

The check uses a historical public ISS TLE at its recorded epoch and a captured
NASA annular-eclipse table. It compares overlay-on/off pixels and checks a path
sample against its expected map position. Each frame has a 30-second timeout.
The files and temporary HOME are isolated under `/tmp`, with no provider
requests, wallpaper changes, launchd operations or extra dependencies. This is
finite renderer evidence, not a live feed, orbital-accuracy or desktop handoff
test. The offline suite remains renderer-independent.
