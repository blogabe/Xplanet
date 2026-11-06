"""Debounced recovery scheduling, contained in the configurator event loop."""
import asyncio
from .owned_io import OwnedIO
from .recovery import RecoveryStore,pack,digest,encoded

class DraftSession:
    def __init__(self,root,snapshot,notify):
        self.packing=OwnedIO()
        self.store=RecoveryStore(root);self.snapshot=snapshot;self.notify=notify
        self.session=None;self.sessions=[];self.timer=None;self.task=None
        self.first_pending=None;self.signature=None;self.last_complete=None;self.closing=False

    def changed(self):
        if self.closing:return
        loop=asyncio.get_running_loop()
        if self.first_pending is None:self.first_pending=loop.time()
        if self.timer:self.timer.cancel()
        self.timer=loop.call_later(max(0,min(1,5-(loop.time()-self.first_pending))),self.start)

    def start(self):
        self.timer=None
        if self.closing:return
        if self.task and not self.task.done():
            self.timer=asyncio.get_running_loop().call_later(.2,self.start);return
        self.task=asyncio.create_task(self.write())

    async def write(self):
        self.first_pending=None
        session=None
        try:
            values=self.snapshot()
            if values is None:return True
            current,baseline,config,workspace,source=values
            record,blobs=await self.packing.run(pack,current,baseline,config,workspace,source)
            signature=digest(encoded({key:value for key,value in record.items() if key!='at'}))
            if signature==self.signature:return True
            if self.session is None:
                self.session=self.store.new_session();self.sessions.append(self.session)
            session=self.session
            revision=await session.checkpoint(record,blobs)
            if self.session is session:self.signature=signature;self.last_complete=(session.identity,revision,record['at'])
            self.notify('Last complete recovery checkpoint recorded. Native files and selection unchanged.')
            return True
        except (OSError,ValueError,TypeError,KeyError) as exc:
            self.notify('Recovery unavailable: '+str(exc)+' Earlier complete checkpoints remain; save a native copy if needed.')
            return False
        finally:
            if session is not None and self.session is not session:session.close()

    async def flush(self):
        if self.timer:self.timer.cancel();self.timer=None
        if self.task and not self.task.done():await self.task
        return await self.write()

    async def cancel_writer(self):
        if self.timer:self.timer.cancel();self.timer=None
        if self.task and not self.task.done():
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)

    async def discard_current(self):
        await self.cancel_writer()
        if self.session is not None:
            session=self.session
            try:
                if self.last_complete and self.last_complete[0]==session.identity:self.store.discard(session.identity,owner=session)
            except (OSError,ValueError) as exc:self.notify('Saved/discarded draft, but recovery material was retained: '+str(exc))
            session.close();self.session=None
        self.signature=None;self.last_complete=None

    def boundary(self):
        # Opening another document retains earlier complete draft checkpoints.
        # A writer already holding a snapshot may finish in its own namespace.
        if self.timer:self.timer.cancel();self.timer=None
        if self.session is not None and (self.task is None or self.task.done()):self.session.close()
        self.session=None;self.signature=None;self.last_complete=None;self.first_pending=None

    async def stop(self):
        self.closing=True
        await self.cancel_writer()

    def close(self):
        self.packing.close()
        self.closing=True
        if self.timer:self.timer.cancel()
        for session in self.sessions:session.close()
