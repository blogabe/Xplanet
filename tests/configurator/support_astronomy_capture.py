"""Plain shared disposable fixtures; no test cases or operational access."""

import json

from configurator.astronomy_capture import capture_existing

from totalmarker.features import norad, eclipse
from totalmarker.http import Fetcher, Response
from tests.support import SandboxFixture, ScriptedTransport
from tests.test_norad import SAMPLE, EPOCH
from tests.test_eclipse import TOTAL, TOTAL_URL


class AstronomyCaptureFixture(SandboxFixture):
    def norad(self):
        settings=self.config('NoradEnabled=On\nNoradCatalogIds=25544\n')
        norad.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(Response(200,{},SAMPLE))),now=EPOCH+10)
        return settings

    def eclipse(self, active=True):
        settings=self.config('EclipseEnabled=On\nEclipsePathURL='+TOTAL_URL+'\n')
        path=eclipse.parse_path(TOTAL,TOTAL_URL)
        eclipse.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(Response(200,{},TOTAL))),now=path.start_at-(3600 if active else 10*86400))
        return settings,path

    def capture(self,product,now):return capture_existing(self.root.resolve(),product,'config.ini',now=now)

    def inventory(self):return {str(path.relative_to(self.root)):(path.read_bytes(),path.stat().st_mtime_ns) for path in self.root.rglob('*') if path.is_file()}

    def edit_state(self,settings,edit):
        state=json.loads(self.fs.read(settings.state));edit(state['products']);self.fs.write(settings.state,json.dumps(state).encode())
