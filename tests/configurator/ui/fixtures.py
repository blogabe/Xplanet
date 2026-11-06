"""Plain disposable editor fixtures; no tests are imported or instantiated."""
from pathlib import Path
import sys,tempfile
from textual.widgets import Input
from configurator.app import ConfiguratorApp
from configurator.workspace import Workspace

async def click(pilot, selector):
    await pilot.pause()
    pilot.app.screen.query_one(selector).scroll_visible(animate=False)
    await pilot.pause()
    await pilot.click(selector)


def prepare_editor(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name).resolve()
    (self.root / 'dev').mkdir()
    (self.root / 'config').mkdir()
    self.workspace = Workspace()
    self.addCleanup(self.workspace.close)
    self.app = ConfiguratorApp(self.root, str(Path(sys.executable).resolve()), self.workspace,recovery=False)
    # Existing interaction regressions deliberately retain the supported legacy destination flow.
    self.app.copy_destination=lambda:str(self.app.document.source.with_name(self.app.document.source.name+'-copy') if self.app.document.source else self.root/'dev/earth-view')

async def enter_native(self,pilot,path):
    await click(pilot,'#edit-native')
    self.app.screen.query_one('#native-patch-source',Input).value=str(path)
    await click(pilot,'#native-patch-open');await pilot.pause()


async def setup_editor(self):
    prepare_editor(self)


async def wait_event(event,timeout=3):
    """Bounded wait for a thread/async barrier without blocking the UI loop."""
    import asyncio
    async def wait():
        while not event.is_set():await asyncio.sleep(.005)
    await asyncio.wait_for(wait(),timeout)
