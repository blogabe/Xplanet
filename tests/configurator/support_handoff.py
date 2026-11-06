"""Plain shared disposable fixtures; no test cases or operational access."""
from pathlib import Path
import sys, tempfile

from configurator.model import View, PLANET_MAPS
from configurator.library import save_named
from configurator.handoff import create_plan


class HandoffFixture:
    def setUp(self):
        # Identity-sensitive fixtures stay outside sync-managed suite TMPDIR.
        # Metadata-only changes are deliberately rejected in the regression below.
        self.temp=tempfile.TemporaryDirectory(prefix="xp handoff '$() ",dir="/tmp");self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'config').mkdir()
        self.legacy={'config/xp.def':b'XPLANET_BIN=$(touch forbidden)\nsource do-not-execute\n','config/xp.conf':b'[earth]\n# preserve\nunknown=first\nunknown=again\n'}
        for name,data in self.legacy.items():(self.root/name).write_bytes(data)
        self.asset=self.root/PLANET_MAPS['moon'];self.asset.parent.mkdir(parents=True);self.asset.write_bytes(b'Known fixture bytes; image decoding is NOT certified')
        self.scene=save_named(self.root/'config/scenes/lunar.conf',View(target='moon',projection='space',observer='earth',time_mode='fixed'),sys.executable)
        self.target=self.root/'new review bundle'

    def plan(self):return create_plan(self.root,self.scene,sys.executable,'1280x720')
