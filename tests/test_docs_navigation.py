"""The user-facing navigation indexes point to actual checkout files."""
import re,unittest
from pathlib import Path
from urllib.parse import unquote
from .support import PROJECT

class DocsNavigationTests(unittest.TestCase):
    def test_new_indexes_and_edited_guides_have_existing_local_targets(self):
        for name in ('README.md','docs/README.md','docs/management.md','docs/configurator/user-guide.md','examples/README.md'):
            path=PROJECT/name
            with self.subTest(document=name):
                self.assertTrue(path.is_file())
                for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text()):
                    if target.startswith(('http:','https:','mailto:','#')):continue
                    target=unquote(target.split('#')[0])
                    if target:self.assertTrue((path.parent/target).exists(),f'{name}: {target}')
    def test_readme_links_to_docs_and_examples_indexes(self):
        text=(PROJECT/'README.md').read_text()
        self.assertIn('(docs/README.md)',text);self.assertIn('(examples/README.md)',text)
