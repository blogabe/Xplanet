"""Display hints seed only blank scenes; loaded scenes and explicit edits win."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from textual.widgets import Input,Static
from configurator.app import ConfiguratorApp
from configurator.display_geometry import parse
from configurator.model import View,ViewDocument
from configurator.workspace import Workspace


class DisplayGeometryUITests(unittest.IsolatedAsyncioTestCase):
    async def test_default_hint_and_explicit_edit_survive_ui_changes(self):
        hint=parse(json.dumps([{'pixels':[3840,2160],'points':[1920,1080]}]))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);workspace=Workspace()
            try:
                app=ConfiguratorApp(root,sys.executable,workspace,recovery=False,display=hint)
                with patch('configurator.display_geometry.subprocess.run',side_effect=AssertionError('no repeated probing')):
                    async with app.run_test(size=(110,50)) as pilot:
                        self.assertEqual(app.query_one('#geometry',Input).value,'3840x2160')
                        self.assertIn('1920x1080 points',str(app.query_one('#display-geometry',Static).render()))
                        app.query_one('#geometry',Input).value='1280x720';await pilot.pause()
                        self.assertEqual(app.query_one('#geometry',Input).value,'1280x720')
                self.assertEqual(list(root.iterdir()),[])
            finally:workspace.close()

    async def test_loaded_scene_dimensions_are_not_replaced_by_current_display(self):
        hint=parse(json.dumps([{'pixels':[3840,2160],'points':[1920,1080]}]))
        view=View(geometry='2160x1080');document=ViewDocument(view,sys.executable,view.body())
        with tempfile.TemporaryDirectory() as temp:
            workspace=Workspace()
            try:
                app=ConfiguratorApp(Path(temp),sys.executable,workspace,document=document,recovery=False,display=hint)
                async with app.run_test(size=(110,50)):
                    self.assertEqual(app.query_one('#geometry',Input).value,'2160x1080')
                    self.assertIs(app.document,document)
            finally:workspace.close()
