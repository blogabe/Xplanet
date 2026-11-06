"""Headless interaction tests run in the separately prepared Textual environment."""
import asyncio
import os
import pty
import select
import subprocess
import termios
import time
from pathlib import Path
import sys
import tempfile
import unittest

from textual.widgets import Input, Select, Static, TextArea
from configurator.app import ConfiguratorApp
from configurator.model import View
from configurator.workspace import Workspace, save_view, open_view
from tests.configurator.ui.fixtures import setup_editor,prepare_editor,click,enter_native




class AppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_open_cancel_has_no_project_writes(self):
        async with self.app.run_test(size=(100, 45)) as pilot:
            await pilot.press('escape')
        self.assertEqual(self.app.return_value, ('cancelled', None))
        self.assertEqual(list((self.root / 'dev').iterdir()), [])

    async def test_save_back_and_existing_destination_are_safe(self):
        async with self.app.run_test(size=(100, 45)) as pilot:
            await click(pilot, '#save')
            await click(pilot, '#back')
            self.assertFalse((self.root / 'dev/earth-view').exists())
            (self.root / 'dev/earth-view').mkdir()
            await click(pilot, '#save')
            await click(pilot, '#confirm-save')
            await pilot.pause()
            self.assertIsNone(self.app.saved)
            self.assertIn('already exists', str(self.app.query_one('#status', Static).render()))
            await pilot.press('escape')

    async def test_explicit_save_keeps_camera_and_exits_without_apply(self):
        async with self.app.run_test(size=(100, 45)) as pilot:
            self.app.query_one('#latitude', Input).value = '25'
            await click(pilot, '#save')
            await click(pilot, '#confirm-save')
        destination = self.root / 'dev/earth-view'
        self.assertEqual(self.app.return_value, ('saved', str(destination)))
        self.assertIn('XPLANET_LATITUDE=25', (destination / 'xp.def').read_text())
        self.assertEqual(sorted(x.name for x in destination.iterdir()), ['xp.conf', 'xp.def'])

    async def test_invalid_camera_stays_in_editor(self):
        async with self.app.run_test(size=(100, 45)) as pilot:
            self.app.query_one('#longitude', Input).value = 'nan'
            await click(pilot, '#preview')
            self.assertIsNone(self.workspace.process)
            self.assertIsNone(self.app.saved)
            await pilot.press('escape')

    async def test_preview_failure_is_visible_and_cancel_stops_worker(self):
        binary = self.root / 'renderer'
        binary.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(30)\n')
        binary.chmod(0o700)
        self.app.renderer = str(binary)
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.query_one('#preview').scroll_visible(animate=False)
            await pilot.pause()
            await click(pilot, '#preview')
            async def started():
                while self.workspace.process is None:
                    await asyncio.sleep(.001)
            await asyncio.wait_for(started(), 2)
            await pilot.press('ctrl+c');await pilot.pause()
            self.assertFalse(self.app.leaving);self.assertIsNone(self.workspace.process)
            await pilot.press('ctrl+c')
        self.assertEqual(self.app.return_value, ('cancelled', None))
        self.assertIsNone(self.workspace.process)
        self.assertFalse((self.root / 'dev/earth-view').exists())


    async def test_control_cancel_keys_work_in_focused_input(self):
        for key in ('ctrl+c', 'ctrl+d', 'ctrl+q'):
            app = ConfiguratorApp(self.root, str(Path(sys.executable).resolve()), self.workspace)
            async with app.run_test(size=(80, 24)) as pilot:
                app.query_one('#renderer', Input).focus()
                await pilot.pause()  # Let focus scrolling settle before exiting the pilot.
                await pilot.press(key)
            self.assertEqual(app.return_value, ('cancelled', None), key)


    async def test_successful_preview_then_explicit_save(self):
        binary = self.root / 'renderer'
        binary.write_text('#!' + sys.executable + '\nimport pathlib,sys\na=sys.argv\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n')
        binary.chmod(0o700)
        self.app.renderer = str(binary)
        async with self.app.run_test(size=(100, 45)) as pilot:
            await click(pilot, '#preview')
            async def finished():
                while self.workspace.image is None:
                    await asyncio.sleep(.001)
            await asyncio.wait_for(finished(), 2)
            await pilot.pause()
            self.assertIn('Preview ready', str(self.app.query_one('#status', Static).render()))
            await click(pilot, '#save')
            await click(pilot, '#confirm-save')
        self.assertEqual(self.app.return_value[0], 'saved')



    async def test_reopen_revise_preview_and_save_copy_never_runs_saved_renderer(self):
        evil = self.root / 'untrusted renderer'
        marker = self.root / 'must-not-run'
        evil.write_text('#!/bin/sh\ntouch ' + str(marker) + '\n');evil.chmod(0o700)
        source = self.root / 'original'
        save_view(source, View(25, -80, 'orthographic'), evil)
        before = {p.name:p.read_bytes() for p in source.iterdir()}
        local = self.root / 'local renderer'
        local.write_text('#!' + sys.executable + '\nimport pathlib,sys\na=sys.argv\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n');local.chmod(0o700)
        self.app.renderer = str(local)
        async with self.app.run_test(size=(80, 30)) as pilot:
            await click(pilot, '#load')
            self.app.screen.query_one('#source-directory', Input).value = str(source)
            await click(pilot, '#confirm-open')
            self.assertEqual(self.app.query_one('#latitude', Input).value, '25')
            self.assertEqual(self.app.query_one('#renderer', Input).value, str(local))
            self.app.query_one('#latitude', Input).value = '10'
            await click(pilot, '#preview')
            async def finished():
                while self.workspace.image is None:
                    await asyncio.sleep(.001)
            await asyncio.wait_for(finished(), 2)
            await pilot.pause()
            await click(pilot, '#save')
            await click(pilot, '#confirm-save')
        self.assertEqual(open_view(self.root / 'original-copy').view.latitude, 10)
        self.assertEqual({p.name:p.read_bytes() for p in source.iterdir()}, before)
        self.assertFalse(marker.exists())

    async def test_open_cancel_and_invalid_input_preserve_draft(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.query_one('#latitude', Input).value = '30'
            await click(pilot, '#load')
            await click(pilot, '#back-open')
            self.assertEqual(self.app.query_one('#latitude', Input).value, '30')
            await click(pilot, '#load')
            self.app.screen.query_one('#source-directory', Input).value = str(self.root / 'missing')
            await click(pilot, '#confirm-open')
            self.assertEqual(self.app.query_one('#latitude', Input).value, '30')
            self.assertIsNone(self.app.document.source)
            self.assertIn('Cannot open view', str(self.app.query_one('#status', Static).render()))
            await pilot.press('escape')

    async def test_cli_loaded_document_prefills_fields_and_keeps_local_renderer(self):
        from configurator.model import View
        source = self.root / 'source';save_view(source, View(-10, 120), sys.executable)
        app = ConfiguratorApp(self.root, '/local/trusted/xplanet', self.workspace, document=open_view(source))
        async with app.run_test(size=(80, 24)) as pilot:
            self.assertEqual(app.query_one('#longitude', Input).value, '120')
            self.assertEqual(app.query_one('#renderer', Input).value, '/local/trusted/xplanet')
            self.assertEqual(app.query_one('#destination', Input).value, str(self.root / 'config/scenes/source-copy.conf'))
            await pilot.press('ctrl+d')
        self.assertEqual(app.return_value, ('cancelled', None))
        self.assertFalse((self.root / 'source-copy').exists())




    async def test_camera_mode_switch_retains_inactive_preferences_and_time(self):
        async with self.app.run_test(size=(80, 30)) as pilot:
            self.app.query_one('#projection', Select).value = 'space'
            self.app.query_one('#observer', Select).value = 'moon'
            self.app.query_one('#framing', Select).value = 'fov'
            self.app.query_one('#fov', Input).value = '4.123456789'
            self.app.query_one('#latitude', Input).value = '23.123456789'
            self.app.query_one('#time-mode', Select).value = 'fixed'
            self.app.query_one('#utc', Input).value = '2024-02-29T23:59:59Z'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#latitude', Input).disabled)
            self.assertFalse(self.app.query_one('#fov', Input).disabled)
            self.app.query_one('#projection', Select).value = 'orthographic'
            self.app.query_one('#time-mode', Select).value = 'now'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#observer', Select).disabled)
            self.assertTrue(self.app.query_one('#framing', Select).disabled)
            self.assertTrue(self.app.query_one('#utc', Input).disabled)
            self.assertFalse(self.app.query_one('#latitude', Input).disabled)
            args = self.app.view().arguments()
            self.assertNotIn('-origin', args);self.assertNotIn('-fov', args);self.assertNotIn('-date', args)
            self.assertEqual(self.app.view().observer, 'moon')
            self.assertEqual(self.app.view().fov, 4.123456789)
            self.assertEqual(self.app.view().utc, '2024-02-29T23:59:59Z')
            await click(pilot, '#save');await click(pilot, '#confirm-save')
        reopened = open_view(self.root / 'dev/earth-view')
        self.assertEqual(reopened.view.latitude, 23.123456789)
        self.assertEqual(reopened.view.observer, 'moon')
        self.assertEqual(reopened.view.fov, 4.123456789)
        self.assertEqual(reopened.view.utc, '2024-02-29T23:59:59Z')

    async def test_fixed_time_error_prevents_preview_and_save(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.query_one('#time-mode', Select).value = 'fixed'
            self.app.query_one('#utc', Input).value = '2023-02-29T12:00:00Z'
            await click(pilot, '#preview')
            self.assertIsNone(self.workspace.process)
            self.assertIn('valid calendar', str(self.app.query_one('#status', Static).render()))
            await click(pilot, '#save')
            self.assertIsNone(self.app.saved)
            self.assertIs(self.app.screen, self.app.screen_stack[0])
            self.assertFalse((self.root / 'dev/earth-view').exists())
            await pilot.press('escape')

    async def test_reopened_space_scene_prefills_all_controls_without_reset(self):
        view = View(12.123456789, -80, 'space', 'opposite_sun', 'fov', 40, 5.123456789,
                    'fixed', '2000-01-01T12:00:00Z')
        source = self.root / 'space';save_view(source, view, sys.executable)
        app = ConfiguratorApp(self.root, str(Path(sys.executable).resolve()), self.workspace, document=open_view(source))
        async with app.run_test(size=(80, 24)) as pilot:
            self.assertEqual(app.view(), view)
            self.assertTrue(app.query_one('#latitude', Input).disabled)
            self.assertFalse(app.query_one('#fov', Input).disabled)
            self.assertFalse(app.query_one('#utc', Input).disabled)
            self.assertIn('Space:', str(app.query_one('#camera-context', Static).render()))
            await pilot.press('ctrl+d')


    async def test_hidden_invalid_value_is_exposed_and_health_uses_same_rules(self):
        async with self.app.run_test(size=(80,30)) as pilot:
            self.assertFalse(self.app.query_one('#control-observer').display)
            self.assertFalse(self.app.query_one('#control-radius').display)
            self.app.query_one('#radius',Input).value = 'not numeric'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#control-radius').display)
            self.assertFalse(self.app.query_one('#radius',Input).disabled)
            await click(pilot,'#health')
            text = '\n'.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn('BLOCKING',text);self.assertIn('radius',text);self.assertIn('unverified',text)
            await pilot.press('escape');await pilot.pause()
            self.assertTrue(self.app.is_running)
            self.app.query_one('#radius',Input).value = '45';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-radius').display)
            await pilot.press('escape')

    async def test_failure_and_cancel_keep_preview_and_comparison_is_deliberate(self):
        binary=self.root/'renderer'
        good='#!'+sys.executable+'\nimport pathlib,sys\na=sys.argv\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n'
        binary.write_text(good);binary.chmod(0o700);self.app.renderer=str(binary)
        async with self.app.run_test(size=(100,40)) as pilot:
            async def rendered(old=None):
                while self.workspace.latest is old or self.workspace.busy:await asyncio.sleep(.001)
                await pilot.pause()
            await click(pilot,'#preview');await asyncio.wait_for(rendered(),2)
            first=self.workspace.latest
            self.app.query_one('#latitude',Input).value='20';await pilot.pause()
            self.assertIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            binary.write_text('#!'+sys.executable+'\nimport sys\nsys.exit(7)\n')
            await click(pilot,'#preview')
            async def outcome(value):
                while self.workspace.last_outcome!=value or self.workspace.busy:await asyncio.sleep(.001)
                await pilot.pause()
            await asyncio.wait_for(outcome('failed'),2)
            self.assertIs(self.workspace.latest,first)
            self.assertIn('retained',str(self.app.query_one('#status',Static).render()))
            binary.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(30)\n')
            await click(pilot,'#preview')
            async def running():
                while self.workspace.process is None:await asyncio.sleep(.001)
            await asyncio.wait_for(running(),2)
            await click(pilot,'#cancel-preview');await asyncio.wait_for(outcome('cancelled'),2)
            self.assertIs(self.workspace.latest,first)
            binary.write_text(good)
            await click(pilot,'#preview');await asyncio.wait_for(rendered(first),2)
            self.assertFalse(self.app.query_one('#compare').disabled)
            await click(pilot,'#compare')
            text='\n'.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn('before:',text);self.assertIn('after:',text);self.assertIn('not an aligned',text)
            await click(pilot,'#close-report')
            retained=self.workspace.latest
            source=self.root/'different-scene';save_view(source,View(40),sys.executable)
            await click(pilot,'#load')
            self.app.screen.query_one('#source-directory',Input).value=str(source)
            await click(pilot,'#confirm-open');await pilot.pause()
            self.assertIs(self.workspace.latest,retained)
            self.assertIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            await pilot.press('escape')

    async def test_health_warnings_do_not_block_save_after_reopen(self):
        source=self.root/'source';save_view(source,View(time_mode='fixed'),sys.executable)
        async with self.app.run_test(size=(80,30)) as pilot:
            await click(pilot,'#load');self.app.screen.query_one('#source-directory',Input).value=str(source)
            await click(pilot,'#confirm-open');await click(pilot,'#health')
            text='\n'.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn('WARNING',text);self.assertNotIn('BLOCKING',text)
            await click(pilot,'#close-report');await click(pilot,'#save');await click(pilot,'#confirm-save')
        self.assertTrue((self.root/'source-copy/xp.def').exists())


class AppearanceAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = setup_editor
    async def test_seasonal_controls_preserve_month_and_save_reopen_appearance(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.assertFalse(self.app.query_one('#control-month').display)
            self.app.query_one('#map-family',Select).value='world.topo'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#control-month').display)
            self.app.query_one('#month',Select).value='11'
            self.app.query_one('#night',Select).value='lights2002'
            self.app.query_one('#grid',Select).value='30'
            self.app.query_one('#label',Select).value='utc'
            self.app.query_one('#twilight',Input).value='12'
            self.app.query_one('#map-family',Select).value='stock'
            await pilot.pause()
            self.assertFalse(self.app.query_one('#control-month').display)
            self.app.query_one('#map-family',Select).value='world.topo'
            await pilot.pause()
            self.assertEqual(self.app.query_one('#month',Select).value,'11')
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        doc=open_view(self.root/'dev/earth-view')
        self.assertEqual((doc.view.map_family,doc.view.month,doc.view.night,doc.view.grid,doc.view.label,doc.view.twilight),
                         ('world.topo','11','lights2002','30','utc',12))
        app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),document=doc)
        try:
            async with app.run_test(size=(100,45)) as pilot:
                self.assertEqual(app.query_one('#month',Select).value,'11')
                self.assertEqual(app.draft(),doc.view)
                await pilot.press('escape')
        finally:
            app.workspace.close()

    async def test_invalid_twilight_blocks_and_health_explains_appearance(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#twilight',Input).value='1.5'
            await click(pilot,'#save')
            self.assertIsNone(self.app.saved)
            self.assertIn('whole number',str(self.app.query_one('#status',Static).render()))
            self.app.query_one('#night',Select).value='lights2002'
            await click(pilot,'#health')
            text=' '.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn('2002',text);self.assertIn('blocking'.upper(),text)
            await pilot.press('escape');await pilot.press('escape')


class HistoryAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = setup_editor

    async def test_invalid_input_undo_redo_and_branching_through_focused_keys(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            field=self.app.query_one('#latitude',Input);field.scroll_visible(animate=False);field.focus()
            await pilot.pause();await pilot.press('ctrl+shift+a','-','x')
            self.assertEqual(field.value,'-x');self.assertTrue(self.app.history.dirty)
            await pilot.press('ctrl+z');self.assertEqual(field.value,'0')
            self.assertFalse(self.app.history.dirty)
            await pilot.press('ctrl+y');self.assertEqual(field.value,'-x')
            await pilot.press('ctrl+z');await pilot.press('ctrl+shift+a','2','5')
            self.assertEqual(field.value,'25');self.assertFalse(self.app.history.can_redo)
            await pilot.press('escape');await pilot.pause()
            self.assertFalse(self.app.leaving)
            await click(pilot,'#discard-draft')
        self.assertEqual(self.app.return_value,('cancelled',None))
        self.assertFalse((self.root/'dev/earth-view').exists())

    async def test_mode_switch_undo_retains_inactive_choices(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#map-family',Select).value='world';await pilot.pause()
            self.app.query_one('#month',Select).value='08';await pilot.pause()
            self.app.query_one('#map-family',Select).value='stock';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-month').display)
            await click(pilot,'#undo')
            self.assertEqual(self.app.query_one('#map-family',Select).value,'world')
            self.assertEqual(self.app.query_one('#month',Select).value,'08')
            await click(pilot,'#redo');self.assertFalse(self.app.query_one('#control-month').display)
            self.assertEqual(self.app.draft().month,'08')
            self.assertIn('retained / currently inactive', '\n'.join(self.app.change_review()))
            await pilot.press('escape')

    async def test_review_tracks_semantic_scene_edits_not_destination_and_blocks_hidden_undo(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#destination',Input).value=str(self.root/'different-copy')
            self.app.query_one('#latitude',Input).value='0.000';await pilot.pause()
            self.assertFalse(self.app.history.dirty)
            self.app.query_one('#latitude',Input).value='bad';await pilot.pause()
            await click(pilot,'#review')
            text='\n'.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn("'0' → 'bad'",text);self.assertIn('not Apply',text)
            await pilot.press('ctrl+z');self.assertEqual(self.app.raw_fields()['latitude'],'bad')
            await pilot.press('escape');await click(pilot,'#undo')
            self.assertFalse(self.app.history.dirty)
            await pilot.press('escape')

    async def test_failed_cancelled_and_successful_open_have_explicit_history_boundaries(self):
        source=self.root/'source';save_view(source,View(40,month='12'),sys.executable)
        before={p.name:p.read_bytes() for p in source.iterdir()}
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause()
            prior=self.app.history.current
            await click(pilot,'#load')
            self.assertIn('replace draft',str(self.app.screen.query_one('#confirm-open').label))
            await click(pilot,'#back-open');self.assertEqual(self.app.history.current,prior)
            await click(pilot,'#load');self.app.screen.query_one('#source-directory',Input).value=str(self.root/'missing')
            await click(pilot,'#confirm-open');self.assertEqual(self.app.history.current,prior)
            self.assertTrue(self.app.history.can_undo)
            await click(pilot,'#load');self.app.screen.query_one('#source-directory',Input).value=str(source)
            await click(pilot,'#confirm-open');await pilot.pause()
            self.assertFalse(self.app.history.dirty or self.app.history.can_undo or self.app.history.can_redo)
            self.assertEqual(self.app.draft().latitude,40)
            self.assertEqual(self.app.history.baseline['renderer'],str(Path(sys.executable).resolve()))
            await pilot.press('ctrl+z');self.assertEqual(self.app.draft().latitude,40)
            await pilot.press('escape')
        self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})

    async def test_save_review_cancel_failure_and_reopen_clean_baseline(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause()
            await click(pilot,'#save')
            text='\n'.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn("'0' → '25'",text)
            await click(pilot,'#back');self.assertTrue(self.app.history.dirty)
            (self.root/'dev/earth-view').mkdir()
            await click(pilot,'#save');await click(pilot,'#confirm-save')
            self.assertTrue(self.app.history.dirty);self.assertTrue(self.app.history.can_undo)
            self.app.query_one('#destination',Input).value=str(self.root/'new-copy')
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        doc=open_view(self.root/'new-copy');self.assertEqual(doc.view.latitude,25)
        app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),document=doc)
        try:
            async with app.run_test(size=(100,45)) as pilot:
                self.assertFalse(app.history.dirty or app.history.can_undo)
                await pilot.press('escape')
        finally:app.workspace.close()


    async def test_undo_redo_recomputes_preview_staleness_without_rendering(self):
        binary=self.root/'finite-renderer';counter=self.root/'calls'
        binary.write_text('#!'+sys.executable+'\nimport pathlib,sys\na=sys.argv\np=pathlib.Path('+repr(str(counter))+')\np.write_text("called")\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n')
        binary.chmod(0o700);self.app.renderer=str(binary)
        async with self.app.run_test(size=(100,45)) as pilot:
            await click(pilot,'#preview')
            async def finished():
                while self.workspace.latest is None or self.workspace.busy:await asyncio.sleep(.001)
                await pilot.pause()
            await asyncio.wait_for(finished(),2)
            snapshot=self.workspace.latest;metadata=counter.stat().st_mtime_ns
            self.app.query_one('#latitude',Input).value='25';await pilot.pause()
            self.assertIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            await click(pilot,'#undo')
            self.assertNotIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            await click(pilot,'#redo')
            self.assertIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            self.assertIs(self.workspace.latest,snapshot);self.assertEqual(counter.stat().st_mtime_ns,metadata)
            await pilot.press('escape')


class GeographyAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_geographic_editor_history_disable_and_native_reopen(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.assertFalse(self.app.query_one('#control-places-text').display)
            self.app.query_one('#places',Select).value='on';await pilot.pause()
            text=self.app.query_one('#places-text',TextArea);text.load_text('51.5 -0.1 "London"');await pilot.pause()
            self.assertEqual(self.app.draft().places_text,'51.5 -0.1 "London"')
            await click(pilot,'#undo');self.assertEqual(text.text,'')
            await click(pilot,'#redo');self.assertIn('London',text.text)
            self.app.query_one('#places',Select).value='off';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-places-text').display)
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        doc=open_view(self.root/'dev/earth-view');self.assertIn('London',doc.view.places_text)
        self.assertEqual(doc.view.places,'off');self.assertNotIn(b'marker_file=',doc.config)
        app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),document=doc)
        try:
            async with app.run_test(size=(100,45)) as pilot:
                self.assertFalse(app.history.dirty)
                app.query_one('#places',Select).value='on';await pilot.pause()
                self.assertIn('London',app.query_one('#places-text',TextArea).text)
                await pilot.press('escape')
        finally:app.workspace.close()

    async def test_inactive_bad_rows_are_exposed_and_health_blocks_save(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#routes',Select).value='on';await pilot.pause()
            self.app.query_one('#routes-text',TextArea).load_text('0 0 91 0');await pilot.pause()
            self.app.query_one('#routes',Select).value='off';await pilot.pause()
            self.assertTrue(self.app.query_one('#control-routes-text').display)
            await click(pilot,'#save');self.assertIsNone(self.app.saved)
            await click(pilot,'#health')
            text='\n'.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn('BLOCKING',text);self.assertIn('Row 1',text)
            await pilot.press('escape');await pilot.press('escape')
        self.assertFalse((self.root/'dev/earth-view').exists())

    async def test_preview_stages_only_generated_surface_files(self):
        binary=self.root/'renderer';binary.write_text('#!'+sys.executable+'\nimport pathlib,sys\na=sys.argv\nbody=pathlib.Path(a[a.index("-config")+1]).read_text()\nassert "marker_file=places.markers" in body and "arc_file=routes.arcs" in body\nassert "London" in pathlib.Path("places.markers").read_text()\nassert "51.5" in pathlib.Path("routes.arcs").read_text()\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n');binary.chmod(0o700)
        self.app.renderer=str(binary)
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#places',Select).value='on'
            self.app.query_one('#routes',Select).value='on'
            self.app.query_one('#places-text',TextArea).load_text('51.5 -0.1 "London"')
            self.app.query_one('#routes-text',TextArea).load_text('51.5 -0.1 40.7 -74')
            await pilot.pause();await click(pilot,'#preview')
            async def done():
                while self.workspace.latest is None or self.workspace.busy:await asyncio.sleep(.001)
                await pilot.pause()
            await asyncio.wait_for(done(),2)
            self.assertEqual(self.workspace.last_outcome,'succeeded')
            self.app.query_one('#places-text',TextArea).load_text('0 0 "Elsewhere"');await pilot.pause()
            self.assertIn('STALE',str(self.app.query_one('#preview-state',Static).render()))
            await pilot.press('escape')


class EarthLayerAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_cloud_controls_hide_preserve_save_and_reopen(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.assertFalse(self.app.query_one('#control-cloud-gamma').display)
            self.app.query_one('#clouds',Select).value='snapshot2011';await pilot.pause()
            self.assertTrue(self.app.query_one('#control-cloud-gamma').display)
            self.app.query_one('#cloud-gamma',Input).value='1.7'
            self.app.query_one('#cloud-threshold',Input).value='120';await pilot.pause()
            await click(pilot,'#health')
            report='\n'.join(str(w.render()) for w in self.app.screen.query(Static))
            self.assertIn('26 August 2011',report);self.assertIn('No provider refresh',report)
            await pilot.press('escape')
            self.app.query_one('#clouds',Select).value='off';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-cloud-gamma').display)
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        doc=open_view(self.root/'dev/earth-view')
        self.assertEqual((doc.view.clouds,doc.view.cloud_gamma,doc.view.cloud_threshold),('off',1.7,120))
        self.assertNotIn(b'cloud_map=',doc.config)
        app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),document=doc)
        try:
            async with app.run_test(size=(100,45)) as pilot:
                app.query_one('#clouds',Select).value='snapshot2011';await pilot.pause()
                self.assertEqual(app.query_one('#cloud-gamma',Input).value,'1.7')
                await pilot.press('escape')
        finally:app.workspace.close()

    async def test_relief_shadow_context_invalid_retained_values_and_undo(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.assertFalse(self.app.query_one('#control-relief-scale').display)
            self.app.query_one('#relief',Select).value='gebco';await pilot.pause()
            self.assertTrue(self.app.query_one('#control-relief-scale').display)
            self.assertFalse(self.app.query_one('#control-relief-shade').display)
            self.app.query_one('#relief-shadow',Select).value='shade';await pilot.pause()
            self.app.query_one('#relief-shade',Input).value='80';await pilot.pause()
            self.app.query_one('#relief-shadow',Select).value='night';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-relief-shade').display)
            await click(pilot,'#undo')
            self.assertEqual(self.app.query_one('#relief-shadow',Select).value,'shade')
            self.assertEqual(self.app.query_one('#relief-shade',Input).value,'80')
            self.app.query_one('#relief-shade',Input).value='1.5';await pilot.pause()
            self.app.query_one('#relief-shadow',Select).value='night';await pilot.pause()
            self.assertTrue(self.app.query_one('#control-relief-shade').display)
            await click(pilot,'#save');self.assertIsNone(self.app.saved)
            await pilot.press('escape')

    async def test_finite_preview_contains_local_layers_and_annotations_without_provider_work(self):
        binary=self.root/'renderer';binary.write_text('#!'+sys.executable+'\nimport pathlib,sys\na=sys.argv\nbody=pathlib.Path(a[a.index("-config")+1]).read_text()\nassert all(k in body for k in ("bump_map=maps/","specular_map=maps/","cloud_map=maps/","marker_file=places.markers"))\nassert "cloud_gamma=1.2" in body\nassert "Center" in pathlib.Path("places.markers").read_text()\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n');binary.chmod(0o700)
        self.app.renderer=str(binary)
        async with self.app.run_test(size=(100,45)) as pilot:
            for field,value in (('relief','gebco'),('specular','bundled'),('clouds','snapshot2011'),('places','on')):
                self.app.query_one('#'+field,Select).value=value
            self.app.query_one('#cloud-gamma',Input).value='1.2'
            self.app.query_one('#places-text',TextArea).load_text('0 0 "Center"')
            await pilot.pause();await click(pilot,'#preview')
            async def done():
                while self.workspace.latest is None or self.workspace.busy:await asyncio.sleep(.001)
                await pilot.pause()
            await asyncio.wait_for(done(),2)
            self.assertEqual(self.workspace.last_outcome,'succeeded')
            await pilot.press('escape')


def capture_fixture(root):
    import hashlib,json
    from configurator.model import ROOT
    source=root/'producer';source.mkdir()
    for name in ('config','images','.state/totalmarker'):(source/name).mkdir(parents=True)
    (source/'config/totalmarker.toml').write_text((ROOT/'config/totalmarker.example.toml').read_text().replace('resolution = 4096','resolution = 2048'))
    image=(ROOT/'maps/clouds/clouds_26Aug2011_2048.jpeg').read_bytes()
    (source/'images/clouds-2048.jpg').write_bytes(image)
    (source/'.state/totalmarker/state.json').write_text(json.dumps({'schema':1,'products':{'clouds':{'image_sha256':hashlib.sha256(image).hexdigest(),'source_image_sha256':hashlib.sha256(image).hexdigest(),'installed_at':1700000000,'successful_at':1700000000,'last_outcome':'unchanged'}}}))
    return source


class FrozenCloudAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_selecting_and_cancelling_capture_does_not_read_source(self):
        from unittest.mock import AsyncMock,patch
        async with self.app.run_test(size=(100,45)) as pilot:
            with patch.object(self.workspace,'capture_cloud',new_callable=AsyncMock) as capture:
                self.app.query_one('#clouds',Select).value='captured';await pilot.pause()
                await click(pilot,'#capture-cloud');await click(pilot,'#back-capture')
                capture.assert_not_called();self.assertEqual(self.app.capture_id,'')
                self.app.query_one('#time-mode',Select).value='fixed';await pilot.pause()
                self.assertFalse(self.app.query_one('#capture-source').display)
                self.app.start_capture(True,'/must-not-read','config/totalmarker.toml')
                capture.assert_not_called()
            await pilot.press('escape')

    async def test_real_worker_capture_undo_fixed_preview_and_portable_save(self):
        source=capture_fixture(self.root)
        binary=self.root/'renderer';binary.write_text('#!'+sys.executable+'\nimport pathlib,sys\na=sys.argv\nbody=pathlib.Path(a[a.index("-config")+1]).read_text()\nif "-date" in a:\n assert "cloud_map=" not in body and not pathlib.Path("cloud-capture.jpg").exists()\nelse:\n assert "cloud_map=cloud-capture.jpg" in body and pathlib.Path("cloud-capture.jpg").is_file()\npathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n');binary.chmod(0o700)
        self.app.renderer=str(binary)
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#clouds',Select).value='captured'
            self.app.query_one('#capture-root',Input).value=str(source)
            await pilot.pause();await click(pilot,'#capture-cloud');await click(pilot,'#confirm-capture')
            async def captured():
                while not self.app.capture_id or self.workspace.busy:await asyncio.sleep(.005)
                await pilot.pause()
            await asyncio.wait_for(captured(),12)
            identity=self.app.capture_id;frozen=self.workspace.capture_for(self.app.draft())
            self.assertIsNotNone(frozen);self.assertNotIn(str(source).encode(),frozen.provenance)
            await click(pilot,'#undo');self.assertEqual(self.app.capture_id,'')
            await click(pilot,'#redo');self.assertEqual(self.app.capture_id,identity)
            source.rename(self.root/'producer-offline')
            await click(pilot,'#preview')
            async def rendered(prior=None):
                while self.workspace.latest is prior or self.workspace.busy:await asyncio.sleep(.005)
                await pilot.pause()
            await asyncio.wait_for(rendered(),3)
            self.assertIsNotNone(self.workspace.latest.cloud_provenance)
            prior=self.workspace.latest
            self.app.query_one('#time-mode',Select).value='fixed';await pilot.pause()
            self.assertFalse(self.app.query_one('#capture-source').display)
            self.assertNotIn('cloud_map=',self.app.draft().body().decode())
            await click(pilot,'#preview');await asyncio.wait_for(rendered(prior),3)
            self.assertIsNone(self.workspace.latest.cloud_provenance)
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        target=self.root/'dev/earth-view';doc=open_view(target)
        self.assertEqual(doc.capture,frozen);self.assertEqual(doc.view.time_mode,'fixed')
        app=ConfiguratorApp(self.root,str(Path(sys.executable).resolve()),document=doc)
        try:
            async with app.run_test(size=(100,45)) as pilot:
                self.assertFalse(app.history.dirty)
                app.query_one('#time-mode',Select).value='now';await pilot.pause()
                self.assertEqual(app.workspace.capture_for(app.draft()),frozen)
                await pilot.press('escape')
        finally:app.workspace.close()

    async def test_failed_recapture_preserves_existing_input_and_draft(self):
        from configurator.cloud_capture import capture_existing
        source=capture_fixture(self.root);frozen=capture_existing(source)
        async with self.app.run_test(size=(100,45)) as pilot:
            self.workspace.register_capture(frozen);self.app.capture_id=frozen.identity
            self.app.query_one('#clouds',Select).value='captured';await pilot.pause()
            self.app.query_one('#capture-root',Input).value=str(self.root/'missing')
            await click(pilot,'#capture-cloud');await click(pilot,'#confirm-capture')
            async def failed():
                while 'Capture unavailable' not in str(self.app.query_one('#status',Static).render()) or self.workspace.busy:await asyncio.sleep(.005)
                await pilot.pause()
            await asyncio.wait_for(failed(),5)
            self.assertEqual(self.app.capture_id,frozen.identity)
            self.assertEqual(self.workspace.capture_for(self.app.draft()),frozen)
            await pilot.press('escape')



class NamedLibraryAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await AppTests.asyncSetUp(self)
        self.app.copy_destination=ConfiguratorApp.copy_destination.__get__(self.app,ConfiguratorApp)

    async def test_browsing_empty_library_is_read_only_and_default_save_is_named(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.assertEqual(self.app.query_one('#destination',Input).value,str(self.root/'config/scenes/earth-view.conf'))
            await click(pilot,'#library');self.assertFalse((self.root/'config/scenes').exists())
            await click(pilot,'#library-back');await click(pilot,'#save');await click(pilot,'#confirm-save')
        target=self.root/'config/scenes/earth-view.conf'
        self.assertTrue(target.is_file());self.assertTrue(target.with_suffix('.def').is_file())
        self.assertTrue(open_view(target).named_source)

    async def test_library_opens_named_pair_then_duplicate_preserves_original(self):
        from configurator.library import save_named
        source=save_named(self.root/'config/scenes/first.conf',View(25,places='on',places_text='0 0 "Center"'),sys.executable)
        before={p.name:p.read_bytes() for p in source.parent.iterdir()}
        async with self.app.run_test(size=(100,45)) as pilot:
            await click(pilot,'#library');await click(pilot,'#library-open')
            self.assertEqual(self.app.draft().latitude,25)
            self.assertFalse(self.app.history.dirty)
            self.assertEqual(self.app.query_one('#destination',Input).value,str(source.parent/'first-copy.conf'))
            self.app.query_one('#latitude',Input).value='30'
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        self.assertEqual(open_view(source.parent/'first-copy.conf').view.latitude,30)
        for name,data in before.items():self.assertEqual((source.parent/name).read_bytes(),data)

    async def test_explicit_legacy_destination_still_works(self):
        async with self.app.run_test(size=(100,45)) as pilot:
            self.app.query_one('#destination',Input).value=str(self.root/'dev/old-style')
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        self.assertFalse(open_view(self.root/'dev/old-style').named_source)


class CompositionAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor
    async def test_solar_and_distance_visibility_history_and_mode_retention(self):
        async with self.app.run_test(size=(110,45)) as pilot:
            self.app.query_one('#longitude-mode',Select).value='solar'
            self.app.query_one('#solar-hour',Input).value='18'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#control-solar-hour').display)
            self.assertFalse(self.app.query_one('#control-longitude').display)
            self.app.query_one('#projection',Select).value='space'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#control-distance').display)
            self.app.query_one('#distance',Input).value='4'
            self.app.query_one('#north',Select).value='orbit'
            self.app.query_one('#rotation',Input).value='25'
            await pilot.pause()
            self.app.query_one('#observer',Select).value='moon'
            await pilot.pause()
            self.assertFalse(self.app.query_one('#control-solar-hour').display)
            self.assertFalse(self.app.query_one('#control-distance').display)
            self.assertEqual(self.app.draft().distance,4)
            self.assertEqual(self.app.draft().solar_hour,18)
            self.app.query_one('#observer',Select).value='geographic'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#control-distance').display)
            self.assertEqual(self.app.draft().north,'orbit')


class PlanetaryAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_target_switch_retains_earth_draft_and_rejects_same_origin(self):
        async with self.app.run_test(size=(110,45)) as pilot:
            self.app.query_one('#places',Select).value='on'
            self.app.query_one('#places-text',TextArea).load_text('0 0 "Home"')
            self.app.query_one('#clouds',Select).value='snapshot2011'
            await pilot.pause()
            self.app.query_one('#target',Select).value='moon'
            await pilot.pause()
            self.assertFalse(self.app.query_one('#control-places').display)
            self.assertFalse(self.app.query_one('#control-clouds').display)
            self.assertTrue(self.app.query_one('#control-grid').display)
            self.assertEqual(self.app.draft().places_text,'0 0 "Home"')
            self.assertIn('inactive',self.app.draft().summary())
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#observer',Select).value='moon'
            await pilot.pause()
            self.assertTrue(any(i.severity=='blocking' and i.field=='observer' for i in self.app.current_issues()))
            self.app.query_one('#observer',Select).value='earth'
            await pilot.pause()
            self.assertFalse(any(i.severity=='blocking' for i in self.app.current_issues()))
            self.app.query_one('#target',Select).value='earth'
            self.app.query_one('#observer',Select).value='geographic'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#control-places').display)
            self.assertEqual(self.app.draft().clouds,'snapshot2011')
            self.assertEqual(self.app.draft().places_text,'0 0 "Home"')

    async def test_planetary_save_and_reopen_keep_target_and_local_renderer(self):
        async with self.app.run_test(size=(110,45)) as pilot:
            self.app.query_one('#target',Select).value='mars'
            await pilot.pause();await click(pilot,'#save');await click(pilot,'#confirm-save')
        doc=open_view(self.root/'dev/earth-view')
        self.assertEqual(doc.view.target,'mars');self.assertEqual(doc.saved_renderer,str(Path(sys.executable).resolve()))


class StockSceneAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_stock_picker_opens_snapshot_and_saves_user_copy(self):
        from configurator.app import STOCK_LIBRARY
        before={p.name:p.read_bytes() for p in STOCK_LIBRARY.iterdir()}
        self.app.copy_destination=ConfiguratorApp.copy_destination.__get__(self.app)
        async with self.app.run_test(size=(110,45)) as pilot:
            await click(pilot,'#stock');await pilot.pause()
            self.app.screen.query_one('#library-selection',Select).value=str(STOCK_LIBRARY/'earth-from-moon.conf')
            await click(pilot,'#library-open');await pilot.pause()
            self.assertEqual(self.app.draft().observer,'moon');self.assertEqual(self.app.draft().projection,'space')
            self.assertEqual(self.app.query_one('#renderer',Input).value,str(Path(sys.executable).resolve()))
            self.assertEqual(self.app.query_one('#destination',Input).value,str(self.root/'config/scenes/earth-from-moon-copy.conf'))
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        self.assertTrue((self.root/'config/scenes/earth-from-moon-copy.conf').is_file())
        self.assertEqual(before,{p.name:p.read_bytes() for p in STOCK_LIBRARY.iterdir()})


class MajorPlanetAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_planetary_shadow_context_history_and_save(self):
        async with self.app.run_test(size=(110,45)) as pilot:
            self.app.query_one('#target',Select).value='saturn'
            self.app.query_one('#projection',Select).value='space'
            await pilot.pause()
            self.assertTrue(self.app.query_one('#control-planet-shade').display)
            self.app.query_one('#planet-shade',Input).value='10.5';await pilot.pause()
            self.assertTrue(any(i.field=='planet_shade' and i.severity=='blocking' for i in self.app.current_issues()))
            self.app.query_one('#planet-shade',Input).value='15'
            self.app.query_one('#observer',Select).value='jupiter'
            await pilot.pause()
            self.assertEqual(self.app.draft().observer,'jupiter')
            self.app.query_one('#target',Select).value='earth';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-planet-shade').display)
            self.assertEqual(self.app.draft().planet_shade,15)
            self.app.action_undo();await pilot.pause()
            self.assertEqual(self.app.draft().target,'saturn')
            self.assertTrue(self.app.query_one('#control-planet-shade').display)
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        doc=open_view(self.root/'dev/earth-view')
        self.assertEqual(doc.view.target,'saturn');self.assertEqual(doc.view.planet_shade,15)
        self.assertEqual(doc.view.observer,'jupiter')


def observation_fixture(root):
    import hashlib,json
    from totalmarker.quake_geojson import render_marker
    source=capture_fixture(root);(source/'markers').mkdir()
    data=render_marker(b'0 0 "M6 fixture" color=Red symbolsize=15\n',1700000000)
    (source/'markers/quake').write_bytes(data)
    state=json.loads((source/'.state/totalmarker/state.json').read_bytes())
    state['products']['quake']={'marker_sha256':hashlib.sha256(data).hexdigest(),'installed_at':1700000000,'successful_at':1700000000,'last_outcome':'changed','feed_generated_at':1700000000}
    (source/'.state/totalmarker/state.json').write_text(json.dumps(state))
    return source


class ObservationAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_open_selection_and_capture_cancel_do_not_inspect_source(self):
        from unittest.mock import AsyncMock,patch
        async with self.app.run_test(size=(110,45)) as pilot:
            with patch.object(self.workspace,'capture_observations',new_callable=AsyncMock) as capture:
                self.app.query_one('#quake-layer',Select).value='captured';await pilot.pause()
                await click(pilot,'#capture-observations');await click(pilot,'#back-capture')
                capture.assert_not_called();self.assertEqual(self.app.observations_id,'')
                self.app.query_one('#time-mode',Select).value='fixed';await pilot.pause()
                self.assertFalse(self.app.query_one('#capture-source').display)
                self.app.start_observations(True,'/must-not-read','config/totalmarker.toml',('quake',))
                capture.assert_not_called()
            await pilot.press('escape')

    async def test_worker_capture_history_inactivity_and_native_copy(self):
        source=observation_fixture(self.root)
        async with self.app.run_test(size=(110,45)) as pilot:
            self.app.query_one('#quake-layer',Select).value='captured'
            self.app.query_one('#capture-root',Input).value=str(source);await pilot.pause()
            await click(pilot,'#capture-observations');await click(pilot,'#confirm-capture');await self.app.workers.wait_for_complete();await pilot.pause()
            frozen=self.workspace.observations_for(self.app.draft());self.assertIsNotNone(frozen)
            identity=self.app.observations_id;self.assertNotIn(str(source).encode(),frozen.provenance)
            self.app.action_undo();await pilot.pause();self.assertEqual(self.app.observations_id,'')
            self.app.action_redo();await pilot.pause();self.assertEqual(self.app.observations_id,identity)
            self.app.query_one('#time-mode',Select).value='fixed';await pilot.pause()
            self.assertNotIn(b'observed-',self.app.draft().body())
            self.app.query_one('#target',Select).value='mars';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-quake-layer').display)
            self.assertEqual(self.app.observations_id,identity)
            source.rename(self.root/'source-offline')
            await click(pilot,'#save');await click(pilot,'#confirm-save')
        doc=open_view(self.root/'dev/earth-view')
        self.assertEqual(doc.observations,frozen);self.assertEqual(doc.view.quake_layer,'captured')
        self.assertEqual(doc.view.target,'mars');self.assertNotIn(b'observed-',doc.config)


class NativeInspectionAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_custom_inspection_back_is_read_only_and_preserves_dirty_draft(self):
        source=self.root/'custom';source.mkdir();raw=b'# Keep exactly\r\n[earth]\r\nmap=earth.jpg\r\nmap=unknown.jpg\r\nunknown=preserve\r\n'
        (source/'xp.conf').write_bytes(raw)
        async with self.app.run_test(size=(110,45)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();before=self.app.history.current
            await click(pilot,'#inspect-native');self.app.screen.query_one('#source-directory',Input).value=str(source)
            await click(pilot,'#confirm-open');await pilot.pause()
            self.assertFalse(self.app.screen.review.recognized)
            self.assertEqual(len(self.app.screen.query('#native-copy')),0)
            await click(pilot,'#native-back');await pilot.pause()
            self.assertEqual(self.app.history.current,before);self.assertTrue(self.app.history.dirty)
            self.assertEqual(self.app.draft().latitude,25)
        self.assertEqual((source/'xp.conf').read_bytes(),raw);self.assertEqual(list(source.iterdir()),[source/'xp.conf'])

    async def test_exact_copy_uses_snapshot_bytes_and_does_not_replace_editor(self):
        source=save_view(self.root/'original',View(10),sys.executable)
        before={p.name:p.read_bytes() for p in source.iterdir()}
        async with self.app.run_test(size=(110,45)) as pilot:
            await click(pilot,'#inspect-native');self.app.screen.query_one('#source-directory',Input).value=str(source)
            await click(pilot,'#confirm-open');await pilot.pause();self.assertTrue(self.app.screen.review.recognized)
            self.app.screen.query_one('#native-destination',Input).value=str(self.root/'original-copy')
            await click(pilot,'#native-copy');await pilot.pause()
            self.assertEqual(self.app.draft().latitude,0);self.assertFalse(self.app.history.dirty)
            self.assertIn('Original snapshot bytes copied',str(self.app.query_one('#status',Static).render()))
        self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'original-copy').iterdir()})


class NativeValueAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    def source(self):
        path=self.root/'native.conf';path.write_bytes(b'# preserve\r\n[earth]\r\nmap=custom.png\r\nmarker_file=one\r\nmarker_file=two\r\n  twilight=6 # comment\r\n[jupiter]\r\nshade=20\r\n')
        (self.root/'native.def').write_text('touch must-not-run\n');return path

    enter=enter_native

    async def test_unchanged_confirmed_copy_preserves_source_bytes_and_main_draft(self):
        source=self.source();before=source.read_bytes()
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#latitude',Input).value='25';await pilot.pause();draft=self.app.history.current
            await self.enter(pilot,source)
            self.assertFalse(self.app.screen.query_one('#native-patch-confirm').display)
            await click(pilot,'#native-patch-review-button');await pilot.pause()
            review=str(self.app.screen.query_one('#native-patch-review',Static).render())
            self.assertIn('No value changes',review);self.assertIn('No byte changes',review)
            import hashlib
            self.assertEqual(review.count(hashlib.sha256(before).hexdigest()),2)
            await click(pilot,'#native-patch-confirm');await pilot.pause()
            self.assertEqual(self.app.history.current,draft);self.assertTrue(self.app.history.dirty)
        self.assertEqual(source.read_bytes(),before);self.assertEqual((self.root/'native-edited.conf').read_bytes(),before)
        self.assertEqual((self.root/'native.def').read_text(),'touch must-not-run\n')
        self.assertFalse((self.root/'must-not-run').exists())

    async def test_invalid_values_survive_section_switch_and_review_is_invalidated(self):
        source=self.source();before=source.read_bytes()
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot,source)
            self.app.screen.query_one('#native-value-twilight',Input).value='invalid';await pilot.pause()
            self.app.screen.query_one('#native-section',Select).value='jupiter';await pilot.pause()
            self.app.screen.query_one('#native-section',Select).value='earth';await pilot.pause()
            self.assertEqual(self.app.screen.query_one('#native-value-twilight',Input).value,'invalid')
            await click(pilot,'#native-patch-review-button');await pilot.pause()
            self.assertFalse(self.app.screen.query_one('#native-patch-confirm').display)
            self.assertIn('twilight',str(self.app.screen.query_one('#native-patch-status',Static).render()))
            self.app.screen.query_one('#native-value-twilight',Input).value='12';await pilot.pause()
            await click(pilot,'#native-patch-review-button');await pilot.pause();self.assertTrue(self.app.screen.query_one('#native-patch-confirm').display)
            self.app.screen.query_one('#native-patch-destination',Input).value=str(self.root/'another.conf');await pilot.pause()
            self.assertFalse(self.app.screen.query_one('#native-patch-confirm').display)
            await click(pilot,'#native-patch-cancel');await pilot.pause()
        self.assertEqual(source.read_bytes(),before);self.assertFalse((self.root/'another.conf').exists())

    async def test_changed_copy_edits_only_numeric_value_and_stale_source_is_refused(self):
        source=self.source();before=source.read_bytes()
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot,source)
            self.app.screen.query_one('#native-value-twilight',Input).value='12';await pilot.pause()
            await click(pilot,'#native-patch-review-button');await pilot.pause()
            review=str(self.app.screen.query_one('#native-patch-review',Static).render())
            self.assertIn("before: b'6'",review);self.assertIn("after:  b'12'",review)
            self.assertIn('Source line 6',review);self.assertIn('source identity is rechecked at save',review)
            source.write_bytes(before+b'# external change\r\n')
            await click(pilot,'#native-patch-confirm');await pilot.pause()
            self.assertIn('Source changed',str(self.app.screen.query_one('#native-patch-status',Static).render()))
            self.assertFalse((self.root/'native-edited.conf').exists())
            await click(pilot,'#native-patch-cancel');await pilot.pause()
            await self.enter(pilot,source)
            self.app.screen.query_one('#native-value-twilight',Input).value='12';await pilot.pause()
            await click(pilot,'#native-patch-review-button');await click(pilot,'#native-patch-confirm');await pilot.pause()
        self.assertEqual(source.read_bytes(),before+b'# external change\r\n')
        self.assertEqual((self.root/'native-edited.conf').read_bytes(),source.read_bytes().replace(b'twilight=6',b'twilight=12'))


    async def test_escape_closes_native_modal_without_exiting_editor(self):
        source=self.source();before=source.read_bytes()
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot,source)
            await pilot.press('escape');await pilot.pause()
            self.assertEqual(type(self.app.screen).__name__,'Screen')
            self.assertFalse(self.app.leaving)
        self.assertEqual(source.read_bytes(),before)


class MoonAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_moon_selection_context_and_retained_earth_settings(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#month',Select).value='09'
            self.app.query_one('#target',Select).value='europa'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#observer',Select).value='jupiter';await pilot.pause()
            self.assertIn('Moon of Jupiter',str(self.app.query_one('#target-context',Static).render()))
            self.assertFalse(self.app.query_one('#control-map-family').display)
            self.assertEqual(self.app.draft().month,'09')
            self.app.query_one('#target',Select).value='earth';await pilot.pause()
            self.assertTrue(self.app.query_one('#control-map-family').display)
            self.assertEqual(self.app.draft().month,'09')

    async def test_pluto_date_conflict_is_visible_and_can_be_revised(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#target',Select).value='charon'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#observer',Select).value='pluto'
            self.app.query_one('#time-mode',Select).value='fixed'
            self.app.query_one('#utc',Input).value='2100-01-01T00:00:00Z';await pilot.pause()
            self.assertTrue(any(i.severity=='blocking' and 'before 2100' in i.message for i in self.app.current_issues()))
            self.app.query_one('#utc',Input).value='2099-12-31T23:59:59Z';await pilot.pause()
            self.assertFalse(any(i.severity=='blocking' and i.field=='utc' for i in self.app.current_issues()))

    async def test_new_stock_relationship_opens_and_saves_as_copy(self):
        from configurator.app import STOCK_LIBRARY
        source=STOCK_LIBRARY/'europa-from-jupiter.conf';before=source.read_bytes()
        self.app.copy_destination=ConfiguratorApp.copy_destination.__get__(self.app)
        async with self.app.run_test(size=(110,50)) as pilot:
            await click(pilot,'#stock')
            self.app.screen.query_one('#library-selection',Select).value=str(source)
            await click(pilot,'#library-open');await pilot.pause()
            self.assertEqual((self.app.draft().target,self.app.draft().observer),('europa','jupiter'))
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        self.assertEqual(source.read_bytes(),before)
        doc=open_view(self.root/'config/scenes/europa-from-jupiter-copy.conf')
        self.assertEqual((doc.view.target,doc.view.observer),('europa','jupiter'))


class SystemAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_system_controls_keep_inactive_choices_and_existing_camera(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#target',Select).value='jupiter'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#radius',Input).value='2'
            self.app.query_one('#composition',Select).value='system'
            self.app.query_one('#satellite-scale',Input).value='3';await pilot.pause()
            self.assertTrue(self.app.query_one('#control-satellite-scale').display)
            self.assertEqual(self.app.draft().radius,2)
            self.assertIn('io, europa',str(self.app.query_one('#system-context',Static).render()))
            self.app.query_one('#projection',Select).value='orthographic';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-composition').display)
            self.assertFalse(self.app.query_one('#control-satellite-scale').display)
            self.assertEqual(self.app.draft().satellite_scale,3)
            self.app.query_one('#projection',Select).value='space';await pilot.pause()
            self.assertTrue(self.app.draft().uses_system())
            self.app.query_one('#target',Select).value='earth';await pilot.pause()
            self.assertFalse(self.app.draft().uses_system());self.assertEqual(self.app.draft().composition,'system')

    async def test_invalid_scale_remains_editable_and_does_not_crash_health_or_history(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#target',Select).value='jupiter'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#composition',Select).value='system';await pilot.pause()
            self.app.query_one('#satellite-scale',Input).value='bad';await pilot.pause()
            self.assertTrue(any(i.field=='satellite_scale' and i.severity=='blocking' for i in self.app.current_issues()))
            self.assertEqual(self.app.raw_fields()['satellite_scale'],'bad')
            await pilot.press('ctrl+z');await pilot.pause()
            self.assertEqual(self.app.draft().satellite_scale,1)
            await pilot.press('ctrl+y');await pilot.pause()
            self.assertEqual(self.app.raw_fields()['satellite_scale'],'bad')
            self.app.query_one('#satellite-scale',Input).value='2.5';await pilot.pause()
            self.assertFalse(any(i.field=='satellite_scale' and i.severity=='blocking' for i in self.app.current_issues()))

    async def test_system_save_reopen_preserves_scale_and_draft_fields(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#target',Select).value='saturn'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#composition',Select).value='system'
            self.app.query_one('#satellite-scale',Input).value='3';await pilot.pause()
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        doc=open_view(self.root/'dev/earth-view')
        self.assertEqual((doc.view.composition,doc.view.satellite_scale),('system',3))
        self.assertTrue(doc.view.uses_system());self.assertIn(b'magnify=3',doc.config)


class OrbitAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def test_orbit_context_modes_and_invalid_intermediate_width(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#target',Select).value='jupiter'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#composition',Select).value='system'
            self.app.query_one('#orbit-paths',Select).value='on'
            self.app.query_one('#orbit-color',Select).value='yellow';await pilot.pause()
            self.assertTrue(self.app.query_one('#control-orbit-width').display)
            self.assertIn('Not spacecraft',str(self.app.query_one('#orbit-context',Static).render()))
            self.app.query_one('#orbit-width',Input).value='bad';await pilot.pause()
            self.assertTrue(any(i.field=='orbit_width' and i.severity=='blocking' for i in self.app.current_issues()))
            await pilot.press('ctrl+z');await pilot.pause();self.assertEqual(self.app.draft().orbit_width,1)
            self.app.query_one('#projection',Select).value='orthographic';await pilot.pause()
            self.assertFalse(self.app.query_one('#control-orbit-width').display)
            self.assertEqual(self.app.draft().orbit_color,'yellow');self.assertEqual(self.app.draft().orbit_paths,'on')

    async def test_orbit_sample_coverage_conflict_can_be_resolved_without_changing_date(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#target',Select).value='saturn'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#composition',Select).value='system'
            self.app.query_one('#time-mode',Select).value='fixed'
            self.app.query_one('#utc',Input).value='1800-01-01T00:00:00Z'
            self.app.query_one('#orbit-paths',Select).value='on';await pilot.pause()
            self.assertTrue(any(i.field=='utc' and 'Orbital path samples' in i.message for i in self.app.current_issues()))
            self.app.query_one('#orbit-paths',Select).value='off';await pilot.pause()
            self.assertEqual(self.app.draft().utc,'1800-01-01T00:00:00Z')
            self.assertFalse(any(i.field=='utc' and i.severity=='blocking' for i in self.app.current_issues()))

    async def test_orbit_save_reopens_with_style_and_preserves_source_workflow(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.query_one('#target',Select).value='jupiter'
            self.app.query_one('#projection',Select).value='space'
            self.app.query_one('#composition',Select).value='system'
            self.app.query_one('#orbit-paths',Select).value='on'
            self.app.query_one('#orbit-color',Select).value='green'
            self.app.query_one('#orbit-width',Input).value='2';await pilot.pause()
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        doc=open_view(self.root/'dev/earth-view')
        self.assertEqual((doc.view.orbit_paths,doc.view.orbit_color,doc.view.orbit_width),('on','green',2))
        self.assertTrue(doc.view.uses_orbits());self.assertIn(b'orbit_color=green\narc_thickness=2\n',doc.config)


class MoonOverrideAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor

    async def prepare(self,pilot):
        self.app.query_one('#target',Select).value='jupiter'
        self.app.query_one('#projection',Select).value='space'
        self.app.query_one('#composition',Select).value='system'
        self.app.query_one('#satellite-scale',Input).value='3';await pilot.pause()

    async def test_invalid_intermediate_values_switch_moons_and_commit_as_one_undoable_edit(self):
        from configurator.model import parse_moon_scales
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.prepare(pilot);self.app.moon_scales='titan=2';self.app.capture_edit()
            await click(pilot,'#moon-scales')
            self.app.screen.query_one('#moon-override-value',Input).value='bad';await pilot.pause()
            self.app.screen.query_one('#scale-moon',Select).value='europa';await pilot.pause()
            await click(pilot,'#moon-override-use');await pilot.pause()
            self.assertIn('literal moon scale',str(self.app.screen.query_one('#moon-override-error',Static).render()))
            self.app.screen.query_one('#scale-moon',Select).value='io';await pilot.pause()
            self.assertEqual(self.app.screen.query_one('#moon-override-value',Input).value,'bad')
            self.app.screen.query_one('#moon-override-value',Input).value='1';await pilot.pause()
            await click(pilot,'#moon-override-use');await pilot.pause()
            self.assertEqual(parse_moon_scales(self.app.moon_scales),{'io':1,'titan':2})
            await pilot.press('ctrl+z');await pilot.pause();self.assertEqual(self.app.moon_scales,'titan=2')
            await pilot.press('ctrl+y');await pilot.pause();self.assertEqual(parse_moon_scales(self.app.moon_scales),{'io':1,'titan':2})

    async def test_cancel_escape_and_unchanged_use_leave_history_and_raw_metadata_intact(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.prepare(pilot);self.app.moon_scales='titan=+02';self.app.capture_edit();before=self.app.history.current
            await click(pilot,'#moon-scales');self.app.screen.query_one('#moon-override-value',Input).value='10';await pilot.pause()
            await pilot.press('escape');await pilot.pause();self.assertFalse(self.app.leaving);self.assertEqual(self.app.history.current,before)
            await click(pilot,'#moon-scales');await click(pilot,'#moon-override-use');await pilot.pause()
            self.assertEqual(self.app.moon_scales,'titan=+02');self.assertEqual(self.app.history.current,before)
            self.assertEqual(list((self.root/'config').iterdir()),[])

    async def test_blank_removes_override_and_shared_invalid_value_does_not_open_dialog(self):
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.prepare(pilot);self.app.moon_scales='io=10,titan=2';self.app.capture_edit()
            await click(pilot,'#moon-scales');self.app.screen.query_one('#moon-override-value',Input).value='';await pilot.pause()
            await click(pilot,'#moon-override-use');await pilot.pause();self.assertEqual(self.app.moon_scales,'titan=2')
            self.assertEqual(self.app.draft().system_scales()['io'],3)
            self.app.query_one('#satellite-scale',Input).value='bad';await pilot.pause()
            await click(pilot,'#moon-scales');await pilot.pause()
            self.assertIn('Cannot edit moon overrides',str(self.app.query_one('#status',Static).render()))
            self.assertEqual(type(self.app.screen).__name__,'Screen')

    async def test_loaded_scene_override_state_restores_and_saves_as_new(self):
        from configurator.library import save_named
        view=View(target='jupiter',projection='space',composition='system',satellite_scale=3,moon_scales='europa=10,io=1,titan=2')
        source=save_named(self.root/'config/scenes/source.conf',view,sys.executable);before=source.read_bytes()
        self.app.copy_destination=ConfiguratorApp.copy_destination.__get__(self.app)
        async with self.app.run_test(size=(110,50)) as pilot:
            self.app.load(str(source));await pilot.pause();self.assertEqual(self.app.moon_scales,view.moon_scales);self.assertFalse(self.app.history.dirty)
            await click(pilot,'#moon-scales');self.assertEqual(self.app.screen.query_one('#moon-override-value',Input).value,'1')
            await click(pilot,'#moon-override-cancel');await pilot.pause()
            await click(pilot,'#save');await click(pilot,'#confirm-save');await pilot.pause()
        self.assertEqual(open_view(self.root/'config/scenes/source-copy.conf').view,view)
        self.assertEqual(source.read_bytes(),before)



class NativeGridAppTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup_editor
    source=NativeValueAppTests.source
    enter=NativeValueAppTests.enter

    async def test_grid_controls_review_and_copy_without_enabling_or_rewriting_source(self):
        source=self.source();raw=source.read_bytes().replace(b'[jupiter]',b'grid=true\r\ngrid1=3\r\ngrid2=30\r\n[jupiter]');source.write_bytes(raw)
        async with self.app.run_test(size=(110,50)) as pilot:
            await self.enter(pilot,source)
            self.app.screen.query_one('#native-value-grid1',Input).value='6'
            self.app.screen.query_one('#native-value-grid2',Input).value='15';await pilot.pause()
            await click(pilot,'#native-patch-review-button');await pilot.pause()
            self.assertIn('grid1',str(self.app.screen.query_one('#native-patch-review',Static).render()))
            await click(pilot,'#native-patch-confirm');await pilot.pause()
        self.assertEqual(source.read_bytes(),raw)
        self.assertEqual((self.root/'native-edited.conf').read_bytes(),raw.replace(b'grid1=3',b'grid1=6').replace(b'grid2=30',b'grid2=15'))


class TerminalTests(unittest.TestCase):
    setUp=prepare_editor

    def test_real_terminal_reopened_cancel_restores_screen_and_tty(self):
        from configurator import __file__ as module_file
        source = self.root / 'pty-saved'
        save_view(source, View(20, -45), sys.executable)
        original = {p.name:p.read_bytes() for p in source.iterdir()}
        for key in (b'\x1b', b'\x03', b'\x04'):
            master, slave = pty.openpty()
            before = termios.tcgetattr(slave)
            env = {**os.environ, 'TERM': 'xterm-256color',
                   'PYTHONPATH': str(Path(module_file).parent.parent),
                   'PYTHONDONTWRITEBYTECODE': '1'}
            process = subprocess.Popen([sys.executable, '-B', '-m', 'configurator',
                                        '--root', str(self.root), '--view', str(source)], stdin=slave,
                                       stdout=slave, stderr=slave, env=env)
            output = b''
            try:
                deadline = time.monotonic() + 8
                while b'No unsaved scene changes.' not in output and time.monotonic() < deadline:
                    if select.select([master], [], [], .2)[0]:
                        output += os.read(master, 65536)
                self.assertIn(b'No unsaved scene changes.', output)
                self.assertIn(b'Opened snapshot', output)
                os.write(master, key)
                while process.poll() is None and time.monotonic() < deadline:
                    if select.select([master], [], [], .2)[0]:
                        output += os.read(master, 65536)
                self.assertEqual(process.wait(timeout=2),130 if key==b'\x03' else 3,output[-500:])
                while select.select([master], [], [], 0)[0]:
                    output += os.read(master, 65536)
                self.assertIn(b'\x1b[?1049h', output)
                self.assertIn(b'\x1b[?1049l', output)
                self.assertEqual(termios.tcgetattr(slave), before)
                self.assertEqual({p.name:p.read_bytes() for p in source.iterdir()}, original)
            finally:
                if process.poll() is None:
                    process.kill();process.wait()
                os.close(master);os.close(slave)

    def test_real_terminal_rejects_unsupported_source_before_ui(self):
        from configurator import __file__ as module_file
        source = self.root / 'unsupported';source.mkdir()
        marker = self.root / 'must-not-execute'
        (source / 'xp.def').write_text('touch ' + str(marker) + '\n')
        (source / 'xp.conf').write_text('[earth]\n')
        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        env = {**os.environ, 'TERM':'xterm-256color',
               'PYTHONPATH':str(Path(module_file).parent.parent), 'PYTHONDONTWRITEBYTECODE':'1'}
        try:
            done = subprocess.run([sys.executable, '-B', '-m', 'configurator', '--view', str(source)],
                                  stdin=slave, stdout=slave, stderr=slave, env=env, timeout=5)
            output = b''
            while select.select([master], [], [], 0)[0]:
                output += os.read(master, 65536)
            self.assertEqual(done.returncode, 2)
            self.assertIn(b'Cannot open view:', output)
            self.assertNotIn(b'\x1b[?1049h', output)
            self.assertEqual(termios.tcgetattr(slave), before)
            self.assertFalse(marker.exists())
        finally:
            os.close(master);os.close(slave)

    def test_real_terminal_history_keys_restore_tty_on_cancel(self):
        from configurator import __file__ as module_file
        probe=self.root/'history-probe.py'
        probe.write_text("""from pathlib import Path
import sys
from textual.widgets import Input
from configurator.app import ConfiguratorApp
root=Path(sys.argv[1])
class Probe(ConfiguratorApp):
 def on_mount(self):
  self.call_after_refresh(self.seed)
 def seed(self):
  self.query_one('#latitude',Input).value='25'
  self.query_one('#latitude',Input).focus()
  self.capture_edit('latitude')
  (root/'ready').write_text('ready')
 def action_undo(self):
  super().action_undo()
  assert self.raw_fields()['latitude']=='0' and not self.history.dirty
  (root/'undone').write_text('ok')
 def action_redo(self):
  super().action_redo()
  assert self.raw_fields()['latitude']=='25' and self.history.dirty
  (root/'redone').write_text('ok')
app=Probe(root,sys.executable)
try: result=app.run()
finally: app.workspace.close()
raise SystemExit(3 if result==('cancelled',None) else 1)
""")
        master,slave=pty.openpty();before=termios.tcgetattr(slave)
        env={**os.environ,'TERM':'xterm-256color','PYTHONPATH':str(Path(module_file).parent.parent),'PYTHONDONTWRITEBYTECODE':'1'}
        process=subprocess.Popen([sys.executable,'-B',str(probe),str(self.root)],stdin=slave,stdout=slave,stderr=slave,env=env)
        output=b''
        def wait_for(marker):
            nonlocal output
            deadline=time.monotonic()+8
            while not marker.exists() and time.monotonic()<deadline:
                if select.select([master],[],[],.05)[0]:output+=os.read(master,65536)
            self.assertTrue(marker.exists(),output[-1000:])
        try:
            wait_for(self.root/'ready');os.write(master,b'\x1a')
            wait_for(self.root/'undone');os.write(master,b'\x19')
            wait_for(self.root/'redone');os.write(master,b'\x03')
            deadline=time.monotonic()+8
            while process.poll() is None and time.monotonic()<deadline:
                if select.select([master],[],[],.05)[0]:output+=os.read(master,65536)
            self.assertEqual(process.wait(timeout=2),3,output[-1000:])
            while select.select([master],[],[],0)[0]:output+=os.read(master,65536)
            self.assertIn(b'\x1b[?1049h',output);self.assertIn(b'\x1b[?1049l',output)
            self.assertEqual(termios.tcgetattr(slave),before)
            self.assertFalse((self.root/'dev/earth-view').exists())
        finally:
            if process.poll() is None:process.kill();process.wait()
            os.close(master);os.close(slave)

    def test_real_terminal_reopens_snapshot_without_producer_and_restores_tty(self):
        from configurator.cloud_capture import capture_existing
        from configurator import __file__ as module_file
        source=capture_fixture(self.root);frozen=capture_existing(source)
        saved=save_view(self.root/'captured-scene',View(clouds='captured',capture_id=frozen.identity),sys.executable,capture=frozen)
        source.rename(self.root/'producer-offline')
        original={p.name:p.read_bytes() for p in saved.iterdir()}
        master,slave=pty.openpty();before=termios.tcgetattr(slave)
        env={**os.environ,'TERM':'xterm-256color','PYTHONPATH':str(Path(module_file).parent.parent),'PYTHONDONTWRITEBYTECODE':'1'}
        process=subprocess.Popen([sys.executable,'-B','-m','configurator','--root',str(self.root),'--view',str(saved)],stdin=slave,stdout=slave,stderr=slave,env=env)
        output=b''
        try:
            deadline=time.monotonic()+10
            while b'No unsaved scene changes.' not in output and time.monotonic()<deadline:
                if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
            self.assertIn(b'No unsaved scene changes.',output)
            os.write(master,b'\x03')
            while process.poll() is None and time.monotonic()<deadline:
                if select.select([master],[],[],.1)[0]:output+=os.read(master,65536)
            self.assertEqual(process.wait(timeout=2),130,output[-1000:])
            while select.select([master],[],[],0)[0]:output+=os.read(master,65536)
            self.assertIn(b'\x1b[?1049l',output);self.assertEqual(termios.tcgetattr(slave),before)
            self.assertEqual(original,{p.name:p.read_bytes() for p in saved.iterdir()})
        finally:
            if process.poll() is None:process.kill();process.wait()
            os.close(master);os.close(slave)
