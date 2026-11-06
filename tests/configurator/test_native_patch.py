"""Copy-on-write native editing preserves opaque configuration and source context."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from configurator.native_patch import NativePatch,Patch
from configurator.fileio import OwnedFiles


class NativePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.source=self.root/'xp.conf'
        self.raw=b'# Keep comments\r\n[default]\r\nshade=30\r\n\r\n[earth]\r\n# native metadata\r\nmap=custom.png\r\nmarker_file=first.markers\r\nmarker_file=second.markers\r\nunknown=\xffopaque\r\n  twilight=6  # blend\r\n# Next body notes\r\n[jupiter]\r\nshade=15\r\n'
        self.source.write_bytes(self.raw);(self.root/'custom.png').write_bytes(b'not opened by editor')
        (self.root/'xp.def').write_text('touch should-not-execute\n')

    def identity(self):
        info=self.source.stat();return self.source.read_bytes(),info.st_mtime_ns,info.st_ctime_ns,info.st_mode

    def test_noop_copy_is_exact_and_does_not_read_scripts_or_assets(self):
        before=self.identity();original=os.open;opened=[]
        def opening(name,*args,**kwargs):opened.append(str(name));return original(name,*args,**kwargs)
        with patch('configurator.native_patch.os.open',side_effect=opening):doc=NativePatch.load(self.source)
        self.assertNotIn('xp.def',opened);self.assertNotIn('custom.png',opened)
        proposal=doc.prepare(doc.initial_values());self.assertFalse(proposal.changes);self.assertEqual(proposal.data,self.raw)
        target=doc.save_copy(self.root/'xp2.conf',proposal)
        self.assertEqual(target.read_bytes(),self.raw);self.assertEqual(before,self.identity())
        self.assertEqual((self.root/'xp.def').read_text(),'touch should-not-execute\n')
        self.assertFalse((self.root/'should-not-execute').exists())

    def test_only_reviewed_numeric_span_changes_with_comments_order_duplicates_and_assets_intact(self):
        doc=NativePatch.load(self.source);proposal=doc.prepare({'earth':{'twilight':'12'}})
        self.assertEqual(proposal.data,self.raw.replace(b'twilight=6',b'twilight=12'))
        target=doc.save_copy(self.root/'xp3.conf',proposal)
        self.assertEqual(target.read_bytes(),proposal.data);self.assertEqual(self.source.read_bytes(),self.raw)
        self.assertEqual(NativePatch.load(target).initial_values()['earth']['twilight'],'12')
        self.assertEqual((self.root/'custom.png').read_bytes(),b'not opened by editor')

    def test_new_overrides_insert_before_trailing_notes_and_preserve_missing_final_newline(self):
        raw=b'[earth]\nmap=earth.jpg\n# trailing note, no newline';self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        proposal=doc.prepare({'earth':{'shade':'20','twilight':'8','bump_scale':'1.5'}})
        self.assertEqual(proposal.data,b'[earth]\nmap=earth.jpg\nshade=20\ntwilight=8\nbump_scale=1.5\n# trailing note, no newline')
        self.assertEqual(doc.prepare({}).data,raw)
        self.source.write_bytes(b'[earth]');doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare({'earth':{'shade':'20'}}).data,b'[earth]\nshade=20\n')

    def test_numeric_equivalence_preserves_original_literal_and_invalid_values_are_not_repaired(self):
        raw=b'[earth]\nshade=+030\nbump_scale=1.000e0\n';self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare({'earth':{'shade':'30','bump_scale':'1'}}).data,raw)
        self.assertEqual(doc.prepare({'earth':{'shade':''}}).data,raw)
        for key,value in (('shade','30.0'),('shade','1e2'),('shade','101'),('twilight','-1'),('bump_scale','nan'),('bump_scale','6'),('bump_scale','x'*1000)):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):doc.prepare({'earth':{key:value}})
        self.source.write_bytes(b'[earth]\nshade=999\ntwilight=1e2\n');doc=NativePatch.load(self.source)
        self.assertTrue(next(s for s in doc.slots if s.key=='shade').reason)
        self.assertEqual(doc.prepare(doc.initial_values()).data,doc.original)

    def test_duplicate_or_mixed_keys_are_opaque_and_cannot_be_edited(self):
        for raw,blocked in ((b'[earth]\nshade=20\nshade=30\ntwilight=6\n',('shade',)),
                            (b'[earth]\ntwilight=6 bump_scale=1\nshade=30\n',('twilight','bump_scale'))):
            self.source.write_bytes(raw);doc=NativePatch.load(self.source)
            for key in blocked:
                slot=next(s for s in doc.slots if s.key==key);self.assertTrue(slot.reason)
                with self.assertRaises(ValueError):doc.prepare({'earth':{key:'1'}})
            self.assertEqual(doc.prepare({}).data,raw)
        self.source.write_bytes(b'[earth]\nshade=20 shade=30 twilight=6 bump_scale=1 grid1=3 grid2=30 cloud_gamma=1 cloud_threshold=90 magnify=1 grid=true map=x night_map=y cloud_map=z\n')
        with self.assertRaises(ValueError):NativePatch.load(self.source)

    def test_ambiguous_structure_controls_and_lines_decline_without_changing_source(self):
        for raw in (b'[earth]\n[Earth]\n',b'[earth] shade=30\n',b'map=earth.jpg\n[earth]\n',b'[earth]\nkey=value\\\n',b'[earth]\nshade=30\rmap=x\n',b'[earth]\nunknown=\x1b[2J\n',b'[earth]\n#'+b'x'*240+b'\n'):
            self.source.write_bytes(raw);before=self.identity()
            with self.subTest(raw=raw),self.assertRaises(ValueError):NativePatch.load(self.source)
            self.assertEqual(before,self.identity())

    def test_only_new_same_directory_files_are_allowed_and_case_aliases_are_not_overwritten(self):
        doc=NativePatch.load(self.source);proposal=doc.prepare({})
        elsewhere=self.root/'elsewhere';elsewhere.mkdir()
        for target in (self.source,self.root/'XP.CONF',self.root/'Xp.conf',elsewhere/'copy.conf',self.root/'bad\x1b.conf'):
            with self.subTest(target=target),self.assertRaises((ValueError,OSError)):doc.save_copy(target,proposal)
        self.assertEqual(self.source.read_bytes(),self.raw);self.assertEqual(list(elsewhere.iterdir()),[])
        (self.root/'paired.def').write_text('keep existing companion')
        with self.assertRaises(ValueError):doc.save_copy(self.root/'paired.conf',proposal)
        self.assertFalse((self.root/'paired.conf').exists())
        with self.assertRaises(ValueError):doc.save_copy(self.root/'forged.conf',Patch(b'unknown replacement'))

    def test_source_change_or_replacement_refuses_stale_edits_and_preserves_new_content(self):
        doc=NativePatch.load(self.source);proposal=doc.prepare({'earth':{'twilight':'12'}})
        self.source.write_bytes(self.raw+b'# external edit\n')
        with self.assertRaisesRegex(ValueError,'Source changed'):doc.save_copy(self.root/'copy.conf',proposal)
        self.assertFalse((self.root/'copy.conf').exists());self.assertTrue(self.source.read_bytes().endswith(b'# external edit\n'))
        self.source.unlink();self.source.symlink_to(self.root/'custom.png')
        with self.assertRaises(OSError):NativePatch.load(self.source)

    def test_source_mutation_during_publish_removes_only_unchanged_owned_copy(self):
        doc=NativePatch.load(self.source);proposal=doc.prepare({});original=OwnedFiles.write;target=self.root/'copy.conf'
        def write(owner,name,data):
            original(owner,name,data);self.source.write_bytes(b'new external source')
        with patch.object(OwnedFiles,'write',autospec=True,side_effect=write),self.assertRaisesRegex(ValueError,'Source changed'):doc.save_copy(target,proposal)
        self.assertFalse(target.exists());self.assertEqual(self.source.read_bytes(),b'new external source')


    def test_directory_replacement_refuses_copy_into_a_different_context(self):
        doc=NativePatch.load(self.source);proposal=doc.prepare({})
        original=self.root;renamed=self.root.with_name(self.root.name+'-moved')
        original.rename(renamed);original.mkdir()
        try:
            with self.assertRaisesRegex(ValueError,'directory changed'):doc.save_copy(original/'copy.conf',proposal)
            self.assertEqual(list(original.iterdir()),[])
        finally:
            original.rmdir();renamed.rename(original)

    def test_insertion_size_growth_is_checked_before_writing(self):
        raw=b'[earth]\n'+b'#\n'*((256*1024-8)//2)
        self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        with self.assertRaisesRegex(ValueError,'bounds'):doc.prepare({'earth':{'shade':'100','twilight':'90','bump_scale':'5'}})
        self.assertEqual(self.source.read_bytes(),raw)


    def test_nonregular_oversized_and_symlink_sources_are_refused(self):
        fifo=self.root/'pipe.conf';os.mkfifo(fifo)
        link=self.root/'link.conf';link.symlink_to(self.source)
        huge=self.root/'huge.conf';huge.write_bytes(b'x'*(256*1024+1))
        for source in (fifo,link,huge):
            with self.subTest(source=source),self.assertRaises((ValueError,OSError)):NativePatch.load(source)

    def test_directory_move_during_publication_cleans_owned_copy(self):
        doc=NativePatch.load(self.source);proposal=doc.prepare({});original=OwnedFiles.write
        moved=self.root.with_name(self.root.name+'-moved')
        def write(owner,name,data):
            original(owner,name,data);self.root.rename(moved);self.root.mkdir()
        try:
            with patch.object(OwnedFiles,'write',autospec=True,side_effect=write),self.assertRaisesRegex(ValueError,'directory moved'):doc.save_copy(self.root/'copy.conf',proposal)
            self.assertFalse((moved/'copy.conf').exists());self.assertEqual((moved/'xp.conf').read_bytes(),self.raw)
        finally:
            self.root.rmdir();moved.rename(self.root)


    def test_grid_edits_patch_only_literals_and_preserve_opaque_native_bytes(self):
        raw=self.raw.replace(b'  twilight=6',b'grid=true\r\ngrid1=+03 # majors\r\ngrid2=030 # dots\r\n  twilight=6')
        self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare({'earth':{'grid1':'3','grid2':'30'}}).data,raw)
        proposal=doc.prepare({'earth':{'grid1':'6','grid2':'15'}})
        target=doc.save_copy(self.root/'grid-copy.conf',proposal)
        self.assertEqual(target.read_bytes(),raw.replace(b'grid1=+03',b'grid1=6').replace(b'grid2=030',b'grid2=15'))
        self.assertEqual(self.source.read_bytes(),raw);self.assertEqual((self.root/'xp.def').read_text(),'touch should-not-execute\n')

    def test_absent_grid_numeric_overrides_do_not_enable_grid_or_repair_other_fields(self):
        raw=b'[earth]\ngrid=false\nmap=custom.png\n';self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        proposal=doc.prepare({'earth':{'grid1':'6','grid2':'15'}})
        self.assertEqual(proposal.data,raw+b'grid1=6\ngrid2=15\n')
        self.assertNotIn(b'grid=true',proposal.data)
        for key,value in (('grid1','0'),('grid2','0'),('grid1','91'),('grid2','91'),('grid1','1.5')):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):doc.prepare({'earth':{key:value}})
        self.assertEqual(self.source.read_bytes(),raw)

    def test_native_zero_grid_values_stay_readonly_and_unchanged(self):
        raw=b'[earth]\ngrid=true\ngrid1=0\ngrid2=0\n';self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare(doc.initial_values()).data,raw)
        for slot in doc.slots:
            if slot.key in ('grid1','grid2'):self.assertTrue(slot.reason)

    def test_mixed_or_duplicate_grid_assignments_are_not_reconstructed(self):
        raw=b'[earth]\ngrid1=3 grid2=30\n';self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        for key in ('grid1','grid2'):
            self.assertTrue(next(slot.reason for slot in doc.slots if slot.key==key))
            with self.assertRaises(ValueError):doc.prepare({'earth':{key:'6'}})
        self.assertEqual(doc.prepare({}).data,raw)

    def test_review_noop_hashes_and_spelling_match_without_source_writes(self):
        import hashlib
        raw=self.raw.replace(b'twilight=6',b'twilight=+006');self.source.write_bytes(raw)
        before=self.identity();doc=NativePatch.load(self.source);proposal=doc.prepare({'earth':{'twilight':'6'}})
        report='\n'.join(doc.review(proposal))
        self.assertEqual(proposal.data,raw);self.assertEqual(proposal.spans,())
        self.assertEqual(report.count(hashlib.sha256(raw).hexdigest()),2)
        self.assertIn('No byte changes',report);self.assertEqual(before,self.identity())

    def test_review_spans_reconstruct_exact_copy_with_crlf_and_multiple_sections(self):
        doc=NativePatch.load(self.source);proposal=doc.prepare({'earth':{'twilight':'12','grid1':'6'},'default':{'shade':'40'}})
        reconstructed=self.raw
        for start,end,value in reversed(proposal.spans):reconstructed=reconstructed[:start]+value+reconstructed[end:]
        self.assertEqual(reconstructed,proposal.data);report='\n'.join(doc.review(proposal))
        self.assertIn('Source line 3',report);self.assertIn("before: b'30'",report);self.assertIn("after:  b'40'",report)
        self.assertIn("before: b''",report);self.assertIn(r'grid1=6\r\n',report)
        self.assertNotIn('\r',report);self.assertEqual(self.source.read_bytes(),self.raw)
        self.assertIn(b'unknown=\xffopaque\r\n',proposal.data)

    def test_review_insertion_at_unterminated_eof_explains_separator_without_rewriting_old_bytes(self):
        raw=b'[earth]\nunknown=keep';self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        proposal=doc.prepare({'earth':{'shade':'20'}});report='\n'.join(doc.review(proposal))
        self.assertEqual(proposal.data,raw+b'\nshade=20\n');self.assertEqual(proposal.spans,((len(raw),len(raw),b'\nshade=20\n'),))
        self.assertIn('Source line 2',report);self.assertIn(r"b'\nshade=20\n'",report)
        self.assertEqual(doc.prepare({}).data,raw);self.assertEqual(self.source.read_bytes(),raw)

    def test_forged_review_spans_changes_or_bytes_are_refused_before_copy(self):
        from dataclasses import replace
        doc=NativePatch.load(self.source);proposal=doc.prepare({'earth':{'twilight':'12'}})
        for forged in (replace(proposal,spans=()),replace(proposal,changes=()),replace(proposal,data=self.raw)):
            with self.subTest(forged=forged),self.assertRaises(ValueError):doc.review(forged)
            with self.assertRaises(ValueError):doc.save_copy(self.root/'never.conf',forged)
        self.assertFalse((self.root/'never.conf').exists());self.assertEqual(self.source.read_bytes(),self.raw)

    def test_review_display_bound_is_explicit_and_full_copy_is_hash_bound(self):
        import hashlib
        from configurator.model import TARGETS
        bodies=list(TARGETS)[:12];raw=b''.join(b'['+body.encode()+b']\n' for body in bodies)
        self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        proposal=doc.prepare({body:{'shade':'20','twilight':'8','grid1':'6'} for body in bodies})
        # Insertions are grouped by section; use literal existing values for >32 spans.
        self.source.write_bytes(proposal.data);doc=NativePatch.load(self.source)
        changed=doc.prepare({body:{'shade':'30','twilight':'9','grid1':'7'} for body in bodies})
        report='\n'.join(doc.review(changed));self.assertIn('32 of 36 byte edits',report)
        self.assertIn(hashlib.sha256(changed.data).hexdigest(),report)
        self.assertEqual(report.count('Source line '),32);self.assertLess(len(report),12000)
        self.assertEqual(self.source.read_bytes(),proposal.data)


    def test_cloud_and_magnification_literals_preserve_noop_spelling_and_other_bytes(self):
        raw=self.raw+b'cloud_gamma=+1.00 # retain\r\ncloud_threshold=090\r\nmagnify=2.0\r\n';self.source.write_bytes(raw)
        doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare({'jupiter':{'cloud_gamma':'1','cloud_threshold':'90','magnify':'2'}}).data,raw)
        change=doc.prepare({'jupiter':{'cloud_gamma':'1.5','cloud_threshold':'120','magnify':'3'}})
        expected=raw.replace(b'cloud_gamma=+1.00',b'cloud_gamma=1.5').replace(b'cloud_threshold=090',b'cloud_threshold=120').replace(b'magnify=2.0',b'magnify=3.0')
        self.assertEqual(change.data,expected);self.assertEqual(self.source.read_bytes(),raw)
        for key,value in (('cloud_gamma','0'),('cloud_gamma','nan'),('cloud_threshold','256'),('cloud_threshold','1.5'),('magnify','0'),('magnify','11')):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):doc.prepare({'jupiter':{key:value}})

    def test_new_fields_refuse_mixed_duplicate_or_unsafe_literals_without_enabling_layers(self):
        raw=b'[earth]\ncloud_gamma=1 cloud_threshold=90\nmagnify=0\n';self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare(doc.initial_values()).data,raw)
        for key in ('cloud_gamma','cloud_threshold','magnify'):
            self.assertTrue(next(slot.reason for slot in doc.slots if slot.key==key))
            with self.assertRaises(ValueError):doc.prepare({'earth':{key:'2'}})
        self.source.write_bytes(b'[earth]\n# leave resources alone\n');doc=NativePatch.load(self.source)
        result=doc.prepare({'earth':{'cloud_gamma':'2','cloud_threshold':'100','magnify':'2'}}).data
        self.assertNotIn(b'cloud_map=',result);self.assertNotIn(b'map=',result)

    def test_literal_grid_and_paths_patch_only_reviewed_bytes_without_opening_assets(self):
        raw=b'# keep\r\n[earth]\r\ngrid=false # off\r\nmap=../maps/day.jpg\r\nnight_map=/maps/night.jpg\r\ncloud_map=clouds.jpg\r\nunknown=opaque\r\n'
        self.source.write_bytes(raw);doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare(doc.initial_values()).data,raw)
        proposal=doc.prepare({'earth':{'grid':'true','map':'../maps/other.jpg','cloud_map':'frozen/clouds.png'}})
        self.assertEqual(proposal.data,raw.replace(b'grid=false',b'grid=true').replace(b'day.jpg',b'other.jpg').replace(b'clouds.jpg',b'frozen/clouds.png'))
        self.assertEqual(doc.save_copy(self.root/'new.conf',proposal).read_bytes(),proposal.data)
        self.assertEqual(self.source.read_bytes(),raw)
        self.assertFalse((self.root/'frozen').exists())

    def test_native_paths_refuse_ambiguous_tokens_and_preserve_opaque_values(self):
        self.source.write_bytes(b'[earth]\nmap="map with spaces.jpg"\nnight_map=$(touch_bad)\ngrid=yes\n')
        doc=NativePatch.load(self.source)
        self.assertEqual(doc.prepare(doc.initial_values()).data,doc.original)
        for key in ('map','night_map','grid'):
            self.assertTrue(next(s.reason for s in doc.slots if s.key==key))
            with self.assertRaises(ValueError):doc.prepare({'earth':{key:'true'}})
        self.source.write_bytes(b'[earth]\n');doc=NativePatch.load(self.source)
        for value in ('~/.map','$HOME/map','file name.jpg','https://example/map','a#comment',r'a\b','a;touch','a*','x\nshade=99','x'*181):
            with self.subTest(value=value),self.assertRaises(ValueError):doc.prepare({'earth':{'map':value}})
        for value in ('TRUE','1','yes'):
            with self.assertRaises(ValueError):doc.prepare({'earth':{'grid':value}})
