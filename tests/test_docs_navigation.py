"""The user-facing navigation indexes point to actual checkout files."""
import re,unittest
from pathlib import Path
from urllib.parse import unquote
from .support import PROJECT

class DocsNavigationTests(unittest.TestCase):
    @staticmethod
    def anchors(path):
        text=re.sub(r'^```.*?^```[^\n]*','',path.read_text(),flags=re.M|re.S);anchors=set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)',text));counts={}
        for line in text.splitlines():
            match=re.match(r'^#{1,6}\s+(.+?)\s*#*$',line)
            if not match:continue
            label=re.sub(r'\[([^]]+)\]\([^)]+\)',r'\1',match[1])
            label=re.sub(r'<[^>]+>','',label).replace('`','').lower()
            slug=re.sub(r'[^\w -]','',label).replace(' ','-')
            count=counts.get(slug,0);counts[slug]=count+1
            anchors.add(slug+('-'+str(count) if count else ''))
        return anchors

    def test_all_public_markdown_local_links_and_anchors_resolve(self):
        paths=[PROJECT/'README.md',*sorted((PROJECT/'docs').rglob('*.md')),PROJECT/'examples/README.md',PROJECT/'maps/README.md']
        for path in paths:
            text=re.sub(r'^```.*?^```[^\n]*','',path.read_text(),flags=re.M|re.S)
            for target in re.findall(r'!?\[[^\]]+\]\(([^)]+)\)',text):
                if target.startswith(('http:','https:','mailto:')):continue
                target=unquote(target.strip('<>'));name,_,anchor=target.partition('#')
                destination=path.parent/name if name else path
                with self.subTest(document=str(path.relative_to(PROJECT)),target=target):
                    self.assertTrue(destination.exists(),target)
                    if anchor and destination.suffix=='.md':self.assertIn(anchor,self.anchors(destination))
    def test_readme_links_to_docs_and_examples_indexes(self):
        text=(PROJECT/'README.md').read_text()
        self.assertIn('(docs/README.md)',text);self.assertIn('(examples/README.md)',text)
