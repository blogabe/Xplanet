"""Plain shared disposable UI fixture helpers; no test cases."""
import sys

from tests.configurator.ui import fixtures

from tests.configurator.ui import fixtures
click=fixtures.click


class ComparisonUIFixture:
    asyncSetUp=fixtures.setup_editor

    def binary(self):
        path=self.root/'renderer';path.write_text('#!'+sys.executable+'''\nimport pathlib,sys,struct
p=pathlib.Path(sys.argv[sys.argv.index('-output')+1])
w,h=map(int,sys.argv[sys.argv.index('-geometry')+1].split('x'))
p.write_bytes(b'\\x89PNG\\r\\n\\x1a\\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',w,h)+b'fixture')
''');path.chmod(0o700);return str(path)
