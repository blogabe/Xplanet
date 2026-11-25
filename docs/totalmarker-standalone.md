# Running TotalMarker independently

TotalMarker runs on Linux with Python 3.11+ and the standard library; no pip
packages are required. Start with a checkout and a personal configuration:

```sh
git clone https://github.com/blogabe/Xplanet.git Xplanet
cd Xplanet
cp config/totalmarker.example.toml config/totalmarker.toml
```

Review `config/totalmarker.toml` before refreshing your sources. Configure a
real cloud source to replace the example's `.invalid` cloud URL. Volcanoes use
the Smithsonian GVP Weekly Report (HTML) by default in the copied example; to
switch, set `provider = "cap"` in `[volcano]` and use the
[official CAP URL](technical-notes.md#volcano-sources). Quakes use USGS and
storms use NHC/JTWC. NORAD and eclipse stay disabled until deliberately configured.

```sh
./scripts/run-totalmarker --help
./scripts/run-totalmarker quake
./scripts/run-totalmarker health --verbose
```

Use `clouds`, `storm`, or `volcano` in place of `quake` for other products.
`health` reads saved results; `health --live` validates configured sources
without updating normal outputs. An unrun product has unknown health.

The wrapper honors `TOTALMARKER_PYTHON`, then a saved project interpreter choice,
then finds Python 3.11+ on `PATH` and existing Homebrew locations. Set
`TOTALMARKER_PYTHON` to an absolute interpreter path to override discovery.
The [runtime selection details](python-runtime.md) also explain macOS management;
Linux users need neither Homebrew nor uv. It uses the checkout as its root, including
when called from another directory. Keep `scripts/totalmarker/` intact,
including its `data/` directory.

Default outputs are `images/clouds-4096.jpg`, `markers/quake`, `markers/volcano`,
`markers/storm`, `arcs/storm` and `markers/updatelabel`, with persistent state in
`.state/totalmarker/` and events in `logs/totalmarker/events.jsonl`. Paths resolve
against the checkout root. Failed refreshes preserve last-good outputs.

Linux users manage scheduling (for example, cron or systemd timers) and Xplanet
rendering separately. The macOS install, setup, desktop launcher and launchd
plists do not apply to this workflow.

## Offline tests

In a Git checkout, run `PYTHONPATH=scripts:. python3 -B -m tests.run_portable`
for the portable subset. `xplanet.sh test` runs the supported macOS suite and is
not the Linux entry point. Hosted CI currently covers macOS only; Linux standalone
support is distinct from continuous Linux validation.

## Standalone aurora overlay

With `[aurora] enabled = true` in your TOML, run:

```sh
./scripts/run-totalmarker aurora --overlay-only
```

Schedule it independently every five minutes if desired. It writes a transparent
2:1 equirectangular PNG to `.state/totalmarker/aurora/overlay.png` and reports
observation, forecast, and expiry times as Unix timestamps. Consume that PNG
only while fresh; the saved file can remain for diagnostics after expiry.
No Xplanet process, display, cloud feed, or additional Python package is
needed. Optional night-map compositing on Linux needs Pillow available to the
selected interpreter; macOS uses the built-in graphics frameworks via Swift.
See [Aurora](management.md#aurora) for the local night-map handoff and disable
procedure.
