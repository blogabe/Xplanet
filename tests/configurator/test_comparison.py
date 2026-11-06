"""Bounded framing sets preserve ordinary previews and never activate anything."""
import asyncio,os,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from configurator.comparison import plan,reason,render_set,GEOMETRY
from configurator.model import View,SAMPLE
from configurator.workspace import Workspace

class ComparisonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.workspace=Workspace();self.addCleanup(self.workspace.close)
        self.binary=self.root/'renderer';self.binary.write_text('#!'+sys.executable+'''\nimport pathlib,sys,struct
p=pathlib.Path(sys.argv[sys.argv.index('-output')+1])
w,h=map(int,sys.argv[sys.argv.index('-geometry')+1].split('x'))
p.write_bytes(b'\\x89PNG\\r\\n\\x1a\\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',w,h)+b'fixture')
''');self.binary.chmod(0o700)
        self.view=View(projection='space',time_mode='fixed',utc='2026-01-01T12:00:00Z')

    async def test_plan_freezes_now_once_and_changes_only_framing_and_comparison_geometry(self):
        original=View(projection='space',geometry='1000x1000');review=plan(original,now=datetime(2026,1,1,12,tzinfo=timezone.utc))
        self.assertEqual(review.epoch,'2026-01-01T12:00:00Z');self.assertEqual([v.radius for v in review.views],[33.75,45,56.25])
        self.assertTrue(all(v.time_mode=='fixed' and v.utc==review.epoch and v.geometry==GEOMETRY for v in review.views))
        self.assertEqual(original.geometry,'1000x1000');self.assertEqual(original.time_mode,'now')
        fov=plan(View(projection='space',framing='fov',fov=10,time_mode='fixed'))
        self.assertEqual([v.fov for v in fov.views],[7.5,10,12.5])

    async def test_unsupported_modes_current_observations_and_extremes_refuse_without_render(self):
        for view in (View(),View(projection='space',radius=100),View(projection='space',clouds='captured'),View(projection='space',storm_layer='captured'),View(projection='space',camera_mode='lunar_orbit',time_mode='fixed')):
            with self.subTest(view=view),self.assertRaises(ValueError):plan(view)
        self.assertIsNone(self.workspace.process);self.assertEqual(list(self.workspace.root.iterdir()),[])

    async def test_completed_set_preserves_preview_history_and_static_html_is_local_only(self):
        await self.workspace.preview(self.view,str(self.binary));previous=self.workspace.latest
        result=await render_set(self.workspace,plan(self.view),str(self.binary),config_bytes=SAMPLE.read_bytes())
        self.assertIs(self.workspace.latest,previous);self.assertTrue(previous.path.exists());self.assertEqual(len(result.frames),3)
        self.assertTrue(result.matches(self.view,str(self.binary)))
        page=result.index.read_text();self.assertEqual(page.count('<figure>'),3);self.assertNotIn('<script',page);self.assertNotIn('https:',page)
        self.assertIn("default-src 'none'",page);self.assertTrue(all(p.exists() for p in result.frames));self.assertFalse(self.workspace.busy)
        self.assertFalse((self.root/'config').exists())

    async def test_later_failure_keeps_complete_sheet_and_ordinary_preview(self):
        result=await render_set(self.workspace,plan(self.view),str(self.binary));old=result.index.read_bytes()
        with patch('configurator.comparison.png_bytes',side_effect=ValueError('bad PNG')),self.assertRaisesRegex(ValueError,'bad PNG'):
            await render_set(self.workspace,plan(self.view),str(self.binary))
        self.assertIs(self.workspace.comparison_latest,result);self.assertEqual(result.index.read_bytes(),old)
        self.assertEqual(self.workspace.comparison_outcome,'failed');self.assertEqual(len(list(self.workspace.root.glob('comparison-*'))),1)

    async def test_cancel_set_reaps_child_and_retains_prior_complete_sheet(self):
        result=await render_set(self.workspace,plan(self.view),str(self.binary))
        slow=self.root/'slow';slow.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(30)\n');slow.chmod(0o700)
        task=asyncio.create_task(render_set(self.workspace,plan(self.view),str(slow)))
        async def started():
            while self.workspace.comparison_workspace is None or self.workspace.comparison_workspace.process is None:await asyncio.sleep(.001)
        await asyncio.wait_for(started(),3);process=self.workspace.comparison_workspace.process
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNotNone(process.returncode);self.assertFalse(self.workspace.busy);self.assertIsNone(self.workspace.comparison_workspace)
        self.assertIs(self.workspace.comparison_latest,result);self.assertTrue(result.index.exists())

    async def test_changed_binary_and_forged_review_do_not_publish_new_sheet(self):
        from dataclasses import replace
        review=plan(self.view)
        with self.assertRaises(ValueError):await render_set(self.workspace,replace(review,parameter='other'),str(self.binary))
        self.assertIsNone(self.workspace.comparison_latest)
        original=self.workspace.latest
        with patch('configurator.comparison.verified_identity',side_effect=ValueError('binary changed')),self.assertRaisesRegex(ValueError,'binary changed'):
            await render_set(self.workspace,review,str(self.binary))
        self.assertIs(self.workspace.latest,original);self.assertIsNone(self.workspace.comparison_latest)

    async def test_output_bound_and_global_wait_budget_fail_closed(self):
        with patch('configurator.comparison.IMAGE_LIMIT',1),self.assertRaisesRegex(ValueError,'16 MiB'):await render_set(self.workspace,plan(self.view),str(self.binary))
        with patch('configurator.comparison.WAIT_BUDGET',0),self.assertRaisesRegex(ValueError,'budget'):await render_set(self.workspace,plan(self.view),str(self.binary))
        self.assertIsNone(self.workspace.comparison_latest);self.assertEqual(list(self.workspace.root.glob('comparison-*')),[])

    async def test_completed_stop_task_never_hides_a_later_owned_child(self):
        # A cancelled waiter can leave a completed shared cleanup task behind.
        # The next render must still reap its own distinct process group.
        self.workspace.stopping=asyncio.create_task(asyncio.sleep(0));await self.workspace.stopping
        slow=self.root/'next-renderer';slow.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(30)\n');slow.chmod(0o700)
        task=asyncio.create_task(self.workspace.preview(self.view,str(slow)))
        async def started():
            while self.workspace.process is None:await asyncio.sleep(.001)
        await asyncio.wait_for(started(),3);process=self.workspace.process;task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNotNone(process.returncode);self.assertIsNone(self.workspace.process)

    async def test_emergency_and_normal_cleanup_signal_the_same_owned_group_only_once(self):
        class Finished:
            pid=12345
            async def wait(self):return 0
        process=Finished();self.workspace.process=process
        with patch('configurator.workspace.os.killpg') as signal_group:
            self.workspace.kill_owned();self.workspace.kill_owned();await self.workspace.stop()
            self.assertEqual(signal_group.call_count,1)
        self.assertIsNone(self.workspace.process)
