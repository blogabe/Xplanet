"""Plain shared disposable fixtures; no test cases or operational access."""
import sys, tempfile

from pathlib import Path

from configurator.model import View
from configurator.workspace import Workspace


class ComparisonFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.workspace=Workspace();self.addCleanup(self.workspace.close)
        self.binary=self.root/'renderer';self.binary.write_text('#!'+sys.executable+'''\nimport pathlib,sys,struct
p=pathlib.Path(sys.argv[sys.argv.index('-output')+1])
w,h=map(int,sys.argv[sys.argv.index('-geometry')+1].split('x'))
p.write_bytes(b'\\x89PNG\\r\\n\\x1a\\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',w,h)+b'fixture')
''');self.binary.chmod(0o700)
        self.view=View(projection='space',time_mode='fixed',utc='2026-01-01T12:00:00Z')
