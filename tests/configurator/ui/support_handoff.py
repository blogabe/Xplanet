"""Plain shared disposable UI fixture helpers; no test cases."""

from pathlib import Path

import sys, tempfile

from textual.widgets import Input, Static

from configurator.app import ConfiguratorApp

from configurator.library import save_named

from configurator.model import View

from configurator.workspace import Workspace

from tests.configurator.ui.fixtures import click

from tests.configurator.ui import fixtures
click=fixtures.click

def prepare_handoff(self):
    self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
    self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
    self.legacy=self.root/'config/xp.def';self.legacy.write_bytes(b'$(touch never-execute)\n# opaque\n')
    self.scene=save_named(self.root/'config/scenes/earth.conf',View(),sys.executable)
    self.source={p:p.read_bytes() for p in (self.legacy,self.scene,self.scene.with_suffix('.def'))}
    self.target=self.root/'config/review'
    self.workspace=Workspace();self.addCleanup(self.workspace.close)
    # Isolate handoff publication; recovery has its own explicit integration suite.
    self.app=ConfiguratorApp(self.root,sys.executable,self.workspace,recovery=False)


class HandoffUIFixture:
    async def asyncSetUp(self):
        prepare_handoff(self)

    async def enter(self,pilot):
        await click(pilot,'#handoff')
        self.app.screen.query_one('#handoff-source',Input).value=str(self.scene)
        self.app.screen.query_one('#handoff-geometry',Input).value='1280x720'
        self.app.screen.query_one('#handoff-destination',Input).value=str(self.target)
        await pilot.pause()

    def unchanged(self):
        for path,raw in self.source.items():self.assertEqual(path.read_bytes(),raw)
        self.assertFalse((self.root/'never-execute').exists());self.assertFalse((self.root/'.state').exists())

    def status(self):return str(self.app.screen.query_one('#handoff-status',Static).render())

    async def export_and_review_apply(self,pilot):
        await self.enter(pilot);await click(pilot,'#handoff-review-button');await click(pilot,'#handoff-confirm')
        await click(pilot,'#handoff-apply-review');await pilot.pause()
