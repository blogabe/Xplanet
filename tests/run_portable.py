"""Portable data/publication subset; no macOS or Textual coverage claim."""
from .run_core import suite as core_suite,run

MACOS_MODULES = {
    'tests.configurator.test_handoff_shell',
    'tests.configurator.test_scene_desktop',
    'tests.test_bootstrap',
    'tests.test_build_options',
    'tests.test_health_launcher',
    'tests.test_launchd_examples',
    'tests.test_launchd_setup',
    'tests.test_launcher_install',
    'tests.test_launcher_render',
    'tests.test_launcher_update',
    'tests.test_launcher_wiring',
    'tests.test_lifecycle_race',
    'tests.test_management',
    'tests.test_monthly_map',
    'tests.test_python_provider',
    'tests.test_python_runtime',
    'tests.test_setup',
    'tests.test_shell_boundaries',
    'tests.test_shell_signal_cleanup',
}

def suite():
    return core_suite(exclude=MACOS_MODULES)

if __name__ == '__main__':
    raise SystemExit(not run(suite,portable=True))
