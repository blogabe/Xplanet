"""Orbital editing retains inactive choices and never applies a scene."""
import unittest
from textual.widgets import Button,Input,Select,Static
from configurator.model import ROOT
from configurator.workspace import open_view
from tests.configurator.ui import fixtures
from tests.configurator.ui import test_resources_ui as resource_fixtures
click=fixtures.click

class OrbitalUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor
    renderer=resource_fixtures.ResourceUITests.renderer

    async def test_stock_camera_conflicts_mode_retention_undo_and_safe_save_reopen(self):
        source=ROOT/'scripts/configurator/samples/scenes/earthrise-lunar-orbit.conf'
        original={p.name:p.read_bytes() for p in source.parent.glob('earthrise-lunar-orbit.*')}
        target=self.root/'config/scenes/revised.conf'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.load(str(source));await pilot.pause();view=self.app.draft()
            self.assertTrue(view.uses_lunar_camera());self.assertEqual(view.orbit_range,2)
            self.assertTrue(self.app.query_one('#control-orbit-range').display)
            self.app.query_one('#time-mode',Select).value='now';await pilot.pause()
            self.assertTrue(any(i.severity=='blocking' and i.field=='time_mode' for i in self.app.current_issues()))
            await click(pilot,'#preview');self.assertIsNone(self.workspace.process)
            self.app.query_one('#time-mode',Select).value='fixed';self.app.query_one('#orbit-range',Input).value='3';await pilot.pause()
            self.app.query_one('#projection',Select).value='orthographic';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-orbit-range').display)
            self.assertEqual(self.app.draft().orbit_range,3)
            self.app.query_one('#projection',Select).value='space';await pilot.pause()
            self.assertEqual(self.app.query_one('#orbit-range',Input).value,'3')
            self.app.query_one('#orbit-range',Input).value='bad';await pilot.pause()
            self.assertTrue(any(i.field=='orbit_range' and i.severity=='blocking' for i in self.app.current_issues()))
            await pilot.press('ctrl+z');await pilot.pause();self.assertEqual(self.app.draft().orbit_range,3)
            self.app.query_one('#destination',Input).value=str(target);await click(pilot,'#save');await click(pilot,'#confirm-save')
        self.assertEqual(open_view(target).view.orbit_range,3)
        self.assertTrue((target.parent/'revised.camera.origin').is_file())
        self.assertEqual(original,{p.name:p.read_bytes() for p in source.parent.glob('earthrise-lunar-orbit.*')})
        self.assertFalse((self.root/'config/desktop.scene').exists())

    async def test_orbital_preview_staleness_and_failed_edit_keep_last_image(self):
        source=ROOT/'scripts/configurator/samples/scenes/earthrise-lunar-orbit.conf'
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.load(str(source));self.app.query_one('#renderer',Input).value=str(self.renderer());await pilot.pause()
            await click(pilot,'#preview');await self.app.workers.wait_for_complete();await pilot.pause()
            old=self.workspace.image;self.assertIsNotNone(old)
            self.app.query_one('#orbit-longitude',Input).value='140';await pilot.pause()
            self.assertIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            self.app.query_one('#frame-y',Input).value='101';await pilot.pause()
            await click(pilot,'#preview');self.assertEqual(self.workspace.image,old);self.assertIsNone(self.workspace.process)
            await pilot.press('escape');await pilot.pause()
            await click(pilot,'#discard-draft')
        self.assertTrue(self.app.leaving)

class ExpandedNativeUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.setup_editor
    enter=fixtures.enter_native

    async def test_cloud_and_scale_copy_needs_review_and_preserves_source_and_draft(self):
        source=self.root/'native.conf';raw=b'# preserve\r\n[earth]\r\ncloud_gamma=1.0 # note\r\ncloud_threshold=090\r\nmagnify=1\r\nunknown=opaque\r\n';source.write_bytes(raw)
        async with self.app.run_test(size=(110,50)) as pilot:
            initial=self.app.history.current;await self.enter(pilot,source)
            # Exercise edit/review events, independently of Button's click-animation debounce.
            self.app.screen.query_one('#native-patch-review-button',Button).active_effect_duration=0
            self.app.screen.query_one('#native-value-magnify',Input).value='0';await click(pilot,'#native-patch-review-button');await pilot.pause()
            self.assertFalse(self.app.screen.query_one('#native-patch-confirm').display)
            self.assertIn('magnify',str(self.app.screen.query_one('#native-patch-status',Static).render()))
            self.app.screen.query_one('#native-value-magnify',Input).value='2'
            self.app.screen.query_one('#native-value-cloud_gamma',Input).value='1.5'
            self.app.screen.query_one('#native-value-cloud_threshold',Input).value='120';await click(pilot,'#native-patch-review-button');await pilot.pause()
            self.assertTrue(self.app.screen.query_one('#native-patch-confirm').display,str(self.app.screen.query_one('#native-patch-status',Static).render()))
            await click(pilot,'#native-patch-confirm');await pilot.pause();self.assertEqual(self.app.history.current,initial)
        self.assertEqual(source.read_bytes(),raw)
        copy=(self.root/'native-edited.conf').read_bytes()
        self.assertEqual(copy,raw.replace(b'cloud_gamma=1.0',b'cloud_gamma=1.5').replace(b'cloud_threshold=090',b'cloud_threshold=120').replace(b'magnify=1',b'magnify=2.0'))
        self.assertNotIn(b'cloud_map=',copy)
