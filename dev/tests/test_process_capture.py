"""An escaped stdout holder must not hold the parent waiter or pipe open."""
import asyncio,os,signal,sys,tempfile,time,unittest
from pathlib import Path
from configurator.workspace import Workspace
from configurator.resources import BoundedLog

class CapturedProcessTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self,finish):
        with tempfile.TemporaryDirectory(prefix='xp-detached-pipe-') as folder:
            root=Path(folder).resolve();pidfile=root/'detached.pid';heartbeat=root/'heartbeat';script=root/'renderer.py'
            script.write_text('import os,signal,time,pathlib\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nif os.fork()==0:\n os.setsid();pathlib.Path('+repr(str(pidfile))+').write_text(str(os.getpid()))\n while True:\n  with pathlib.Path('+repr(str(heartbeat))+').open("ab") as stream:stream.write(b"x")\n  time.sleep(.01)\n'+('print("finite leader completed",flush=True)\n' if finish else 'time.sleep(30)\n'))
            workspace=Workspace();log=BoundedLog();task=asyncio.create_task(workspace._run_child([sys.executable,str(script)],root,dict(os.environ),log,1));child=None;pipe_fd=None
            started=time.monotonic()
            try:
                while workspace.process is None and not task.done():await asyncio.sleep(.001)
                if workspace.process is not None:
                    pipe_fd=workspace.process.transport.get_pipe_transport(1).get_extra_info('pipe').fileno()
                if finish:self.assertEqual(await asyncio.wait_for(task,9),0)
                else:
                    with self.assertRaises(asyncio.TimeoutError):await asyncio.wait_for(task,9)
                self.assertLess(time.monotonic()-started,7.5,'cleanup waited for escaped stdout EOF')
                self.assertIsNone(workspace.process);self.assertTrue(pidfile.exists())
                child=int(pidfile.read_text());os.kill(child,0) # outside the owned group; do not signal it in product code
                size=heartbeat.stat().st_size;await asyncio.sleep(.05)
                self.assertGreater(heartbeat.stat().st_size,size,'the escaped child must remain outside product cleanup signals')
                self.assertIn('inherited output pipe remained open',log.excerpt()[0])
                await asyncio.sleep(0)
                if pipe_fd is not None:
                    with self.assertRaises(OSError):os.fstat(pipe_fd)
            finally:
                if child is None and pidfile.exists():child=int(pidfile.read_text())
                if child is not None:
                    try:os.kill(child,signal.SIGKILL)
                    except ProcessLookupError:pass
                if not task.done():task.cancel()
                await asyncio.gather(task,return_exceptions=True);await workspace.stop();workspace.close()
    async def test_timeout_kills_term_ignoring_leader_but_does_not_wait_for_detached_stdout(self):await self.run_fixture(False)
    async def test_successful_leader_closes_parent_pipe_after_bounded_drain_without_killing_detached_child(self):await self.run_fixture(True)
