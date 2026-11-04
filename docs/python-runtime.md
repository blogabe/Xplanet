# TotalMarker Python runtime

TotalMarker needs Python 3.11+ and only the standard library. Python is used for
TotalMarker data work, never desktop lifecycle or management orchestration.
The separate [configurator](configurator.md) explicitly prepares its own isolated
Textual environment; it does not add dependencies to TotalMarker or this interpreter.

Initial interactive installation/setup offers a Python choice. Later, management's
**Advanced Python** action offers an explicit change when needed:

- **Homebrew (recommended):** use an existing compatible Homebrew Python, or
  explicitly approve `brew install python`.
- **uv-managed Python:** find an existing compatible managed interpreter offline,
  or explicitly approve `uv --no-config python install --no-bin '>=3.11'`.
  If uv itself is missing, the proposed commands include `brew install uv`.
  You can also install uv separately and make it available on PATH.

The screen shows proposed commands before running them and the resolved absolute
interpreter before saving. Initial setup can also keep a compatible existing
interpreter. Advanced Python first asks whether you want to change providers;
this is an occasional maintenance action, not a routine toggle. Selecting an
existing interpreter does not reinstall or uninstall anything. A failed install
or validation keeps the previous selection. Noninteractive `install` retains its
Homebrew provisioning behavior. Normal updates preserve the saved choice.

Homebrew and uv own installation and upgrades. This project does not manage pip,
packages, virtual environments, uv projects or lockfiles; migrate dependencies;
repair providers; relink Python; or edit shell/global PATH settings. The uv command
avoids executable links in its bin directory. Provider download/cache and Python
installation directories are still managed by uv itself.

## Selection and scheduled jobs

`run-totalmarker` selects in this order:

1. Explicit `TOTALMARKER_PYTHON` absolute executable path.
2. This checkout's ignored `config/totalmarker.python`, containing one literal
   absolute path saved by management/install.
3. Compatible Python discovery on PATH and existing Homebrew locations.

An explicit environment or saved choice that fails validation is an error, not a
reason to silently switch providers. An environment override must be unset before
management can change the saved choice. `--python-path` reports the effective
interpreter without downloading or installing anything. Ordinary data commands
execute the saved interpreter directly; uv is not required on their PATH.

Setup records the compatible interpreter during confirmed preparation if no
selection exists; it validates and preserves an existing choice. New scheduled
jobs invoke the same shared launcher and contain **no automatically added Python
environment override**. A later provider change updates only the selection file;
no renderer restart or job reload is required.

An explicit `TOTALMARKER_PYTHON` remains authoritative for the invocation that
receives it. It is not copied into new plists. If setup has no saved choice, it
records its validated interpreter as the shared default; if a choice exists,
setup preserves it and explains any difference from its environment override.

Existing personal plists and registrations remain unchanged. If an actual job
contains `EnvironmentVariables.TOTALMARKER_PYTHON`, management warns that it still
overrides the shared selection. Review that explicit setting separately; this
feature does not rewrite or reload existing jobs or provide a migration workflow.

For independent use without the macOS management/install flow, see
[standalone TotalMarker](totalmarker-standalone.md).
