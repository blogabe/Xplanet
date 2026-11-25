"""Plain shared disposable fixtures; no test cases or operational access."""

import tempfile

from pathlib import Path

from configurator.model import View
from configurator.workspace import Workspace

from tests.configurator.support_renderer import write_geometry_png_renderer


class ComparisonFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.binary = self.root / "renderer"
        write_geometry_png_renderer(self.binary)
        self.view = View(projection="space", time_mode="fixed", utc="2026-01-01T12:00:00Z")
