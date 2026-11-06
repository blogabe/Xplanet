"""Plain shared disposable fixtures; no test cases or operational access."""

from datetime import datetime, timezone

import sys

from configurator.astronomy_capture import capture_existing

from configurator.model import View

from configurator.library import save_named

from configurator.workspace import Workspace

from totalmarker.features import norad

from totalmarker.http import Fetcher, Response

from tests.support import SandboxFixture, ScriptedTransport

from tests.configurator import support_astronomy_capture as capture_fixtures

from tests.test_norad import SAMPLE as TLE

def synthetic_current_tle():
    """Re-epoch the old example ONLY to exercise file plumbing, not real prediction."""
    now=datetime.now(timezone.utc);fraction=int((now.hour*3600+now.minute*60+now.second)/86400*1e8)
    epoch=f'{now:%y}{now.timetuple().tm_yday:03d}.{fraction:08d}'
    lines=TLE.decode().splitlines();lines[0]='SYNTHETIC FILE-PLUMBING FIXTURE'
    body=lines[1][:18]+epoch+lines[1][32:68]
    lines[1]=body+str(sum(int(c) if c.isdigit() else c=='-' for c in body)%10)
    return ('\n'.join(lines)+'\n').encode()


class AstronomySceneFixture(SandboxFixture):
    eclipse=capture_fixtures.AstronomyCaptureFixture.eclipse

    def setUp(self):
        super().setUp();(self.root/'config').mkdir();self.workspace=Workspace();self.addCleanup(self.workspace.close)

    def norad_capture(self):
        settings=self.config('NoradEnabled=On\nNoradCatalogIds=25544\n')
        now=datetime.now(timezone.utc).timestamp()
        norad.run(self.fs,settings,fetcher=Fetcher(ScriptedTransport(Response(200,{},synthetic_current_tle()))),now=now)
        return capture_existing(self.root.resolve(),'norad','config.ini',now=now)

    def eclipse_capture(self):
        _,path=self.eclipse()
        return capture_existing(self.root.resolve(),'eclipse','config.ini',now=path.start_at-1800)

    def scene(self):
        first=self.norad_capture();second=self.eclipse_capture()
        self.workspace.register_astronomy(first);self.workspace.register_astronomy(second)
        view=View(projection='space',norad_layer='captured',norad_id=first.identity,eclipse_layer='captured',eclipse_id=second.identity,eclipse_window=second.window_token,time_mode='fixed',utc=second.window_token.split('/')[0])
        return view,{'norad':first,'eclipse':second}

    def save(self,view,astronomy,name='event.conf'):
        return save_named(self.root/'config/scenes'/name,view,sys.executable,astronomy=astronomy)
