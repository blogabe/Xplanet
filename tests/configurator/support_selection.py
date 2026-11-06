"""Plain shared disposable fixtures; no test cases or operational access."""
import sys
from tests.configurator import support_handoff as fixtures
from configurator.handoff import stage_plan, create_plan
from configurator.library import save_named
from configurator.model import View
from configurator.selection import inspect_selection, apply_bundle


class SceneSelectionFixture:
    setUp_fixture=fixtures.HandoffFixture.setUp

    plan=fixtures.HandoffFixture.plan

    def setUp(self):
        self.setUp_fixture();stage_plan(self.plan(),self.target)
        self.baseline={p:p.read_bytes() for p in (self.scene,self.scene.with_suffix('.def'),self.asset,self.root/'config/xp.def',self.root/'config/xp.conf')}
        self.guard=self.root/'producer-state';self.guard.write_bytes(b'pending producer intent; do not rewind')

    def preserved(self):
        for path,raw in self.baseline.items():self.assertEqual(path.read_bytes(),raw)
        self.assertEqual(self.guard.read_bytes(),b'pending producer intent; do not rewind')
        self.assertFalse((self.root/'forbidden').exists())

    def apply(self):return apply_bundle(self.root,self.target,inspect_selection(self.root))

    def next_bundle(self):
        source=save_named(self.root/'config/scenes/second.conf',View(),sys.executable)
        bundle=self.root/'second review';stage_plan(create_plan(self.root,source,sys.executable,'1920x1080'),bundle)
        return bundle
