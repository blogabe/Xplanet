"""An escaped stdout holder must not hold the parent waiter or pipe open."""
import asyncio,os,signal,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from configurator.workspace import Workspace
from configurator.resources import BoundedLog

async def heartbeat_after_progress(path, size, timeout=1):
    """Observe continued output separately from the product cleanup deadline."""
    loop=asyncio.get_running_loop();deadline=loop.time()+timeout
    current=path.stat().st_size
    while current<=size:
        remaining=deadline-loop.time()
        if remaining<=0:break
        await asyncio.sleep(min(.01,remaining))
        current=path.stat().st_size
    return current


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
                size=heartbeat.stat().st_size
                self.assertGreater(await heartbeat_after_progress(heartbeat,size),size,'the escaped child must remain outside product cleanup signals')
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


class HeartbeatObservationTests(unittest.IsolatedAsyncioTestCase):
    async def observe(self, growth_at, timeout):
        clock=[0.0];size=[1];waits=[]
        loop=SimpleNamespace(time=lambda:clock[0])
        path=SimpleNamespace(stat=lambda:SimpleNamespace(st_size=size[0]))
        async def advance(delay):
            waits.append(delay);clock[0]+=delay
            if growth_at is not None and clock[0]>=growth_at:size[0]=2
        with patch.object(asyncio,'get_running_loop',return_value=loop),patch.object(asyncio,'sleep',new=advance):
            result=await heartbeat_after_progress(path,1,timeout)
        return result,clock[0],waits

    async def test_delayed_progress_is_observed_within_budget(self):
        size,elapsed,waits=await self.observe(.15,1)
        self.assertEqual(size,2);self.assertGreaterEqual(elapsed,.15)
        self.assertLess(elapsed,.17);self.assertGreater(len(waits),1)

    async def test_absent_progress_is_not_reported_as_success_after_the_deadline(self):
        size,elapsed,waits=await self.observe(None,.2)
        self.assertEqual(size,1);self.assertAlmostEqual(elapsed,.2)
        self.assertTrue(waits);self.assertTrue(all(0<delay<=.01 for delay in waits))
