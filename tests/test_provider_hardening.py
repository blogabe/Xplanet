"""Untrusted provider and storage inputs fail before publication."""
import unittest
from totalmarker.xmlsafe import parse
from totalmarker.errors import FeedError, StorageError
from totalmarker.state import publication_bytes
from totalmarker.paths import RootFS
from .support import Sandbox

class ProviderInputTests(unittest.TestCase):
    def test_xml_declarations_rejected_even_with_non_ascii_encoding(self):
        text='<!DOCTYPE rss [<!ENTITY x "expanded">]><rss>&x;</rss>'
        for encoding in ('utf-8','utf-16','utf-16-be'):
            with self.subTest(encoding=encoding),self.assertRaisesRegex(FeedError,'unsupported XML declarations'):
                parse(text.encode(encoding))
        self.assertEqual(parse(b'<rss/>').tag,'rss')

    def test_missing_journal_label_is_storage_error(self):
        with self.assertRaisesRegex(StorageError,'required state or label'):
            publication_bytes({'state':{'schema':1,'products':{}}},1024)

class OutputPathTests(Sandbox):
    def test_control_paths_rejected_before_any_filesystem_operation(self):
        for suffix in ('\x00hidden','\nline','\x1bcontrol','\x7f'):
            with self.subTest(suffix=suffix),self.assertRaisesRegex(StorageError,'control characters'):
                self.fs.resolve('markers/quake'+suffix,write=True)

    def test_configuration_rejects_control_output_before_runtime_operations(self):
        from totalmarker.errors import ConfigError
        with self.assertRaisesRegex(ConfigError,'output paths.*control'):
            self.config('CloudOutput=images/bad\x00name.jpg\n')

    def test_defaults_have_jitter_margin_without_rewriting_explicit_intervals(self):
        settings=self.config()
        self.assertEqual((settings.interval,settings.quake.interval,settings.volcano.interval),(3300,1100,82800))
        settings=self.config('CloudCheckIntervalSeconds=3600\nQuakeCheckIntervalSeconds=1200\nVolcanoCheckIntervalSeconds=86400\n')
        self.assertEqual((settings.interval,settings.quake.interval,settings.volcano.interval),(3600,1200,86400))
