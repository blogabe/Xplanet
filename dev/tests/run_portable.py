"""Run data/publication tests without claiming macOS workflow coverage.

The normal xplanet.sh test command remains the full supported macOS suite.
This explicit boundary is for hosts without zsh, launchd, plutil or Homebrew.
"""
from pathlib import Path
import unittest

MACOS_MODULES = {
    'test_management', 'test_bootstrap', 'test_health_launcher', 'test_launchd_examples',
    'test_launchd_setup', 'test_launcher_install', 'test_launcher_render',
    'test_launcher_update', 'test_launcher_wiring', 'test_monthly_map',
    'test_python_runtime', 'test_setup', 'test_shell_boundaries',
}


def suite():
    loader = unittest.TestLoader()
    names = [path.stem for path in sorted(Path(__file__).parent.glob('test_*.py'))
             if path.stem not in MACOS_MODULES]
    return loader.loadTestsFromNames(['tests.' + name for name in names])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(suite())
    raise SystemExit(not result.wasSuccessful())
