"""Plain shared disposable fixtures; no test cases or operational access."""
import tempfile
from pathlib import Path

from configurator.recovery import RecoveryStore, raw_fields, pack
from configurator.workspace import Workspace
from configurator.model import SAMPLE


class RecoveryFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.store=RecoveryStore(self.root);self.w=Workspace();self.addCleanup(self.w.close)
        self.baseline=raw_fields(renderer='/local/renderer');self.current={**self.baseline,'latitude':'-x','places_text':'invalid geographic text'}
        self.sessions=[]
        self.addCleanup(lambda:[session.close() for session in self.sessions])

    def session(self):
        session=self.store.new_session();self.sessions.append(session);return session

    def proposal(self,**changes):return pack({**self.current,**changes},self.baseline,SAMPLE.read_bytes(),self.w,'source hint only.conf')
