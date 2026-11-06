"""Plain shared disposable UI fixture helpers; no test cases."""

from tests.configurator.ui.fixtures import setup_editor, enter_native

from tests.configurator.ui import fixtures
click=fixtures.click


class NativeValueUIFixture:
    asyncSetUp=setup_editor

    def source(self):
        path=self.root/'native.conf';path.write_bytes(b'# preserve\r\n[earth]\r\nmap=custom.png\r\nmarker_file=one\r\nmarker_file=two\r\n  twilight=6 # comment\r\n[jupiter]\r\nshade=20\r\n')
        (self.root/'native.def').write_text('touch must-not-run\n');return path

    enter=enter_native
