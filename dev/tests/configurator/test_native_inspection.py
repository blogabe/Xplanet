"""Source preservation is an acceptance condition, not a conversion assumption."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from configurator.model import View
from configurator.workspace import save_view,open_view
from configurator.library import save_named
from configurator.native_inspection import inspect_native,copy_unchanged


class NativeInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.source=self.root/'source';self.source.mkdir()

    def inventory(self,root=None):
        return {p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_ctime_ns,p.stat().st_mode) for p in (root or self.source).iterdir() if p.is_file()}

    def custom(self):
        (self.source/'xp.def').write_bytes(b'# custom definitions\r\nXPLANET_BIN=$(touch should-not-exist)\r\nsource private-script\r\n')
        (self.source/'xp.conf').write_bytes(b'# keep comment/order\r\n[earth]\r\nmap=earth.jpg\r\nmap=unknown.jpg\r\nmarker_file=../must-not-read\r\ncustom_unknown=unchanged\r\n')

    def test_unknown_shell_comments_duplicates_and_assets_remain_read_only(self):
        self.custom();before=self.inventory()
        with patch('subprocess.run',side_effect=AssertionError('must not execute source')):review=inspect_native(self.source)
        self.assertFalse(review.recognized);self.assertEqual(dict(review.files),{n:v[0] for n,v in before.items()})
        self.assertIn('map','\n'.join(review.sections()))
        with self.assertRaisesRegex(ValueError,'read-only'):copy_unchanged(review,self.root/'copy')
        self.assertFalse((self.root/'copy').exists());self.assertFalse((self.source/'should-not-exist').exists())
        self.assertEqual(before,self.inventory())

    def test_unpaired_custom_config_is_inspectable_without_camera_inference(self):
        source=self.source/'xp2.conf';raw=b'# unknown single config\n[earth]\nmap=custom.png\n';source.write_bytes(raw)
        review=inspect_native(source);self.assertFalse(review.recognized);self.assertEqual(review.files,(('xp2.conf',raw),))
        self.assertIn('no edit, preview or copy','\n'.join(review.sections()))
        self.assertEqual(source.read_bytes(),raw)

    def test_known_old_format_copy_is_byte_identical_without_version_or_path_upgrade(self):
        view=View(15,20,geometry='800x600');(self.source/'xp.def').write_text(view.definition('/old renderer',version=3,asset_root='/old-assets'))
        (self.source/'xp.conf').write_bytes(view.body());(self.source/'private-note.toml').write_text('unrelated private note')
        before=self.inventory();review=inspect_native(self.source);self.assertTrue(review.recognized)
        target=copy_unchanged(review,self.root/'copy')
        self.assertEqual({p.name:p.read_bytes() for p in target.iterdir()},{name:data for name,data in review.files})
        self.assertEqual((target/'xp.def').read_bytes(),before['xp.def'][0]);self.assertIn(b'scene v3',before['xp.def'][0])
        self.assertFalse((target/'private-note.toml').exists());self.assertEqual(open_view(target).view,view)
        self.assertEqual(before,self.inventory())

    def test_associated_native_assets_preserve_bytes_and_source_changes_are_not_rolled_back(self):
        view=View(places='on',places_text='0 0 "A"',routes='on',routes_text='0 0 10 10')
        named=save_named(self.root/'library'/'old.conf',view,sys.executable)
        review=inspect_native(named);self.assertTrue(review.recognized)
        before={name:data for name,data in review.files};named.write_bytes(b'new external content, preserve it')
        target=copy_unchanged(review,self.root/'copy')
        self.assertEqual({p.name:p.read_bytes() for p in target.iterdir()},before)
        self.assertEqual(open_view(target/'old.conf').view,view)
        self.assertEqual(named.read_bytes(),b'new external content, preserve it')
        with self.assertRaises(ValueError):copy_unchanged(review,target)
        link=self.root/'alias';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):copy_unchanged(review,link/'unsafe')

    def test_links_nonregular_oversize_controls_and_changed_reads_fail_safely(self):
        self.custom();definition=self.source/'xp.def';original=definition.read_bytes();definition.unlink();definition.symlink_to(self.source/'xp.conf')
        with self.assertRaises(OSError):inspect_native(self.source)
        definition.unlink();os.mkfifo(definition)
        with self.assertRaises(ValueError):inspect_native(self.source)
        definition.unlink();definition.write_bytes(original);(self.source/'xp.conf').write_bytes(b'x'*262145)
        with self.assertRaises(ValueError):inspect_native(self.source)
        self.custom()
        from configurator import native_inspection as module
        actual=module.read_bounded
        def changing(fd,bound):
            raw=actual(fd,bound);(self.source/'xp.conf').write_bytes(b'concurrent change');return raw
        with patch.object(module,'read_bounded',side_effect=changing),self.assertRaisesRegex(ValueError,'changed during review'):inspect_native(self.source)
        self.assertEqual((self.source/'xp.conf').read_bytes(),b'concurrent change')

    def test_display_is_bounded_and_controls_are_escaped_without_changing_bytes(self):
        raw=b'# \x1b[2J keep bytes\n'+b'x'*10000+b'\n'+b''.join(f'Key{i}=one\nKey{i}=two\n'.encode() for i in range(500));(self.source/'xp.conf').write_bytes(raw)
        review=inspect_native(self.source);text='\n'.join(review.sections())
        self.assertNotIn('\x1b',text);self.assertIn('\\x1b',text);self.assertIn('display truncated',text)
        self.assertLess(len(text),2000);self.assertEqual(dict(review.files)['xp.conf'],raw)

    def test_partial_copy_cleanup_preserves_concurrently_changed_copy_file(self):
        save_view(self.root/'generated',View(),sys.executable);review=inspect_native(self.root/'generated')
        from configurator.fileio import OwnedFiles
        original=OwnedFiles.write;target=self.root/'copy';first,second=(review.files[0][0],review.files[1][0])
        def write(owner,name,data):
            if name==second:
                (target/first).write_bytes(b'external edit to partial copy')
                raise PermissionError('fixture')
            return original(owner,name,data)
        with patch.object(OwnedFiles,'write',side_effect=write,autospec=True),self.assertRaises(PermissionError):copy_unchanged(review,target)
        self.assertEqual((target/first).read_bytes(),b'external edit to partial copy')


    def test_all_captured_assets_are_byte_identical_in_unchanged_named_copy(self):
        from tests.configurator.test_observation_capture import ObservationCaptureTests, icon, quake_marker
        from tests.configurator.test_configurator import CloudCaptureTests
        fixture=ObservationCaptureTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.config.write_text(fixture.config.read_text().replace('image = ""','image = "images/icon.png"'))
        (fixture.root/'images/icon.png').write_bytes(icon())
        fixture.install('quake',quake_marker(b'0 0 "Event" color=Red image=images/icon.png\n',1700000000));fixture.save_state()
        frozen=fixture.capture()
        cloud_fixture=CloudCaptureTests();cloud_fixture.setUp();self.addCleanup(cloud_fixture.doCleanups);cloud=cloud_fixture.capture()
        view=View(clouds='captured',capture_id=cloud.identity,observations_id=frozen.identity,quake_layer='captured',storm_layer='captured',volcano_layer='captured')
        path=save_named(self.root/'library'/'full.conf',view,sys.executable,capture=cloud,observations=frozen)
        before=self.inventory(path.parent);review=inspect_native(path);self.assertTrue(review.recognized)
        target=copy_unchanged(review,self.root/'full-copy')
        self.assertEqual({p.name:p.read_bytes() for p in target.iterdir()},{name:data[0] for name,data in before.items()})
        self.assertEqual(open_view(target/'full.conf').view,view);self.assertEqual(open_view(target/'full.conf').observations,frozen)
        self.assertEqual(before,self.inventory(path.parent))
        self.assertLess(len(repr(open_view(path))),10000)


    def test_filename_case_aliases_are_declined_instead_of_silently_renamed(self):
        source=save_view(self.root/'case',View(),sys.executable)
        (source/'xp.def').rename(source/'XP.DEF')
        review=inspect_native(source);self.assertFalse(review.recognized)
        with self.assertRaises(ValueError):copy_unchanged(review,self.root/'case-copy')
        self.assertTrue((source/'XP.DEF').is_file());self.assertFalse((self.root/'case-copy').exists())
