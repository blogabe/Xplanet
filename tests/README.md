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
