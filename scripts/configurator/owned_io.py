"""One owned filesystem operation; cancellation waits for its writer to finish."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import threading

_cancel = ContextVar('configurator_io_cancel', default=None)

class CancelledIO(asyncio.CancelledError):
    pass

def checkpoint():
    event=_cancel.get()
    if event is not None and event.is_set():raise CancelledIO('Operation cancelled.')

def begin_publication():
    # Finish a committed selector's verification and report its actual outcome.
    checkpoint()
    _cancel.set(None)

@contextmanager
def cleanup_io():
    """Finish verification/removal of owned partial files, never new work."""
    token=_cancel.set(None)
    try:yield
    finally:_cancel.reset(token)

class OwnedIO:
    def __init__(self):
        self.owner=None;self.cancel=None;self.thread=None

    async def run(self,function,*args,**kwargs):
        if self.owner is not None:raise ValueError('Another filesystem operation is still finishing.')
        self.owner=asyncio.current_task();event=self.cancel=threading.Event()
        loop=asyncio.get_running_loop();task=loop.create_future()
        def completed(value,error):
            if not task.done():
                if error is None:task.set_result(value)
                else:task.set_exception(error)
        def invoke():
            token=_cancel.set(event);value=None;error=None
            try:checkpoint();value=function(*args,**kwargs)
            except BaseException as exc:error=exc
            finally:_cancel.reset(token)
            try:loop.call_soon_threadsafe(completed,value,error)
            except RuntimeError:pass  # Fatal loop shutdown; close still joins us.
        self.thread=threading.Thread(target=invoke,name='configurator-files',daemon=False)
        try:self.thread.start()
        except BaseException:
            self.owner=None;self.cancel=None;self.thread=None
            raise
        try:
            while True:
                try:return await asyncio.shield(task)
                except asyncio.CancelledError:
                    event.set()
                    # Never detach the thread, including on repeated interrupts.
                    if task.done():return task.result()
        finally:
            self.thread.join()
            self.owner=None;self.cancel=None;self.thread=None

    def request_cancel(self):
        if self.cancel is not None:self.cancel.set()

    async def stop(self):
        self.request_cancel();owner=self.owner
        if owner is not None and owner is not asyncio.current_task():
            await asyncio.gather(owner,return_exceptions=True)

    def close(self):
        self.request_cancel()
        if self.thread is not None:self.thread.join()
