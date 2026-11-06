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

Fixtures are offline/synthetic or attributed public captures. Preserve raw fixture
bytes and `.gitattributes`. Optional private NORAD captures remain under ignored
`dev/validation`; missing optional evidence is reported as a skip, not invented.
Tests use disposable roots and stub operations; do not point them at a working
installation. See [architecture](../docs/architecture.md#verification-boundaries).

The core runners allow only the two named optional private NORAD evidence skips;
zero skips is valid when that evidence is available. Any other skipped required
check, including Git-index privacy checks, makes the supported run fail. Use a
complete Git checkout for release verification. Running selected tests directly
in a source-only copy is useful development evidence, not a verified release.
UI fixtures are plain helpers; blocking PTY tests use synchronous runners with
explicit geometry. File-identity tests use local `/tmp` storage with nanosecond
ctime/mtime evidence; a filesystem without that evidence is outside those fixtures
(the production safety checks are not weakened to make the tests pass).
Hosted CI covers macOS Python 3.11/3.13 and the isolated Textual suite. Linux
runtime support is unchanged; Ubuntu CI remains deliberately disabled.
