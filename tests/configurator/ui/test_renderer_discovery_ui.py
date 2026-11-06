"""Initial local renderer notes and stock loading never adopt scene executables."""
import unittest
from textual.widgets import Input,Static
from configurator.app import STOCK_LIBRARY
from configurator.renderer_discovery import discover
from tests.configurator.ui import fixtures
from tests.configurator.ui import test_resources_ui as resources

class RendererDiscoveryUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor
    renderer=resources.ResourceUITests.renderer
    async def test_project_renderer_note_and_stock_open_retain_local_choice(self):
        import shlex
        binary=self.renderer()
        (self.root/'config/xp.def').write_text('XPLANET_BIN='+shlex.quote(str(binary))+'\n')
        selected,note=discover(self.root)
        self.app.renderer=selected;self.app.renderer_note=note
        async with self.app.run_test(size=(100,40)) as pilot:
            self.assertEqual(self.app.query_one('#renderer',Input).value,str(binary))
            self.assertIn('literal project',str(self.app.query_one('#renderer-discovery',Static).render()))
            self.app.load(STOCK_LIBRARY/'earth-september.conf');await pilot.pause()
            self.assertEqual(self.app.query_one('#renderer',Input).value,str(binary))
            self.assertIsNone(self.workspace.process)
