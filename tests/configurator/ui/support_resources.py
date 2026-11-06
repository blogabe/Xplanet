"""Plain shared disposable UI fixture helpers; no test cases."""
import sys

from pathlib import Path

from textual.widgets import Static

from tests.configurator.ui import fixtures

from tests.configurator.ui import fixtures
click=fixtures.click


class ResourceUIFixture:
    asyncSetUp=fixtures.setup_editor

    def renderer(self,png=True):
        path=self.root/'fixture renderer'
        features='PNG\\n\\tJPEG' if png else 'JPEG'
        path.write_text('#!'+sys.executable+'\nimport sys,pathlib,struct\na=sys.argv\n'+
            'if "-version" in a:\n'+f' print("Xplanet 1.3.1\\nCompiled with support for:\\n\\t{features}");sys.exit(0)\n'+
            'w,h=map(int,a[a.index("-geometry")+1].split("x"))\n'+
            'pathlib.Path(a[a.index("-output")+1]).write_bytes(b"\\x89PNG\\r\\n\\x1a\\n"+b"\\0\\0\\0\\rIHDR"+struct.pack(">II",w,h))\n'+
            'print("Looking for earth.jpg ... not found\\nLooking for /fixture/earth.jpg ... found")\n')
        path.chmod(0o700);return path

    async def check_readable_evidence(self, size):
        from configurator.app import ReportScreen
        from configurator.resources import Capabilities
        report = Capabilities(Path('/example/xplanet'), (7, 42, 1048576, 1_000_000_001, 2_000_000_002),
                              'reported', ('PNG', 'Mac OS X'), '\tPNG\n\tMac OS X\nunsafe\x1b[31m', 40, 'now')
        async with self.app.run_test(size=size) as pilot:
            self.app.push_screen(ReportScreen('Binary evidence', report.sections()))
            await pilot.pause()
            text = '\n'.join(str(widget.render()) for widget in self.app.screen.query(Static))
            self.assertIn('    Mac OS X', text)
            self.assertNotIn(r'\tMac OS X', text)
            self.assertIn('Size: 1,048,576 bytes', text)
            self.assertIn('Modified: 1970-01-01', text)
            self.assertIn(r'unsafe\x1b[31m', text)
            self.assertNotIn('unsafe\x1b[31m', text)
            await click(pilot, '#close-report')
