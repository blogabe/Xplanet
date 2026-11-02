# Running TotalMarker independently

TotalMarker runs on Linux with Python 3.11+ and the standard library; no pip
packages are required. Start with a checkout and a personal configuration:

```sh
git clone https://github.com/blogabe/Xplanet.git Xplanet
cd Xplanet
cp config/totalmarker.example.toml config/totalmarker.toml
```

Edit `config/totalmarker.toml` to choose your sources before refreshing them.
The example cloud and volcano CAP URLs use `.invalid` placeholders; configure
a real cloud source and CAP URL, or select `provider = "weekly_html"` for
volcanoes. Quakes use USGS and storms use NHC/JTWC. NORAD and eclipse stay
disabled until deliberately configured.

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
