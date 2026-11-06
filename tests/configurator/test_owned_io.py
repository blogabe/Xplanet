"""Cancellation owns the filesystem worker through completion, including commit."""
import asyncio
import threading
import unittest
from configurator.owned_io import OwnedIO, CancelledIO, checkpoint, begin_publication

class OwnedIOTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_waits_for_worker_and_never_detaches_late_write(self):
        io=OwnedIO();entered=threading.Event();release=threading.Event();writes=[]
        def operation():
            entered.set()
            if not release.wait(3):raise AssertionError('test barrier expired')
            checkpoint();writes.append('must not write')
        task=asyncio.create_task(io.run(operation))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,3))
            task.cancel()
            async def cancellation_seen():
                while not io.cancel.is_set():await asyncio.sleep(0)
            await asyncio.wait_for(cancellation_seen(),3)
            self.assertFalse(task.done())
            task.cancel();release.set()
            with self.assertRaises(CancelledIO):await task
            self.assertEqual(writes,[])
            self.assertIsNone(io.owner)
            self.assertEqual(await io.run(lambda:'next operation'),'next operation')
        finally:
            release.set();await asyncio.gather(task,return_exceptions=True);io.close()

    async def test_cancellation_after_commit_reports_completed_receipt(self):
        io=OwnedIO();committed=threading.Event();release=threading.Event()
        def operation():
            begin_publication();committed.set()
            if not release.wait(3):raise AssertionError('test barrier expired')
            checkpoint();return 'verified committed receipt'
        task=asyncio.create_task(io.run(operation))
        try:
            self.assertTrue(await asyncio.to_thread(committed.wait,3))
            task.cancel();release.set()
            self.assertEqual(await task,'verified committed receipt')
            self.assertIsNone(io.owner)
        finally:release.set();await asyncio.gather(task,return_exceptions=True);io.close()

    async def test_stop_waits_for_callers_outcome_and_refuses_concurrent_work(self):
        io=OwnedIO();entered=threading.Event();release=threading.Event();outcomes=[]
        def operation():
            entered.set()
            if not release.wait(3):raise AssertionError('test barrier expired')
            checkpoint()
        async def caller():
            try:await io.run(operation)
            except CancelledIO:outcomes.append('cancelled')
        task=asyncio.create_task(caller())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,3))
            with self.assertRaisesRegex(ValueError,'still finishing'):await io.run(lambda:None)
            io.request_cancel();release.set();await io.stop()
            self.assertEqual(outcomes,['cancelled']);self.assertTrue(task.done())
        finally:release.set();await asyncio.gather(task,return_exceptions=True);io.close()

class WorkspaceCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_close_reaps_renderer_before_removing_temporary_workspace(self):
        import os,sys,tempfile
        from pathlib import Path
        from configurator.workspace import Workspace
        from configurator.model import View
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'renderer'
            binary.write_text('#!'+sys.executable+'\nimport pathlib,signal,sys,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\npathlib.Path(sys.argv[sys.argv.index("-output")+1]).with_name("ready").write_text("ready")\ntime.sleep(30)\n');binary.chmod(0o700)
            workspace=Workspace();root=workspace.root
            task=asyncio.create_task(workspace.preview(View(),str(binary),timeout=20))
            try:
                async def ready():
                    while not list(root.glob('preview-*/ready')):await asyncio.sleep(.005)
                await asyncio.wait_for(ready(),5);process=workspace.process
                self.assertIsNotNone(process)
                await workspace.aclose()
                self.assertIsNotNone(process.returncode)
                self.assertFalse(root.exists())
                with self.assertRaises(ProcessLookupError):os.kill(process.pid,0)
            finally:
                await workspace.stop();await asyncio.gather(task,return_exceptions=True);workspace.close()
