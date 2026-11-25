"""Plain shared disposable UI fixture helpers; no test cases."""

from tests.configurator.support_renderer import write_geometry_png_renderer

from tests.configurator.ui import fixtures

click = fixtures.click


class ComparisonUIFixture:
    asyncSetUp = fixtures.setup_editor

    def binary(self):
        path = self.root / "renderer"
        write_geometry_png_renderer(path)
        return str(path)
