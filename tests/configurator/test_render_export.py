"""Durable copies preserve owned snapshots and never overwrite personal files."""
import asyncio,hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from configurator.comparison import plan,render_set
from configurator.model import View,SAMPLE
from configurator.workspace import Workspace
from configurator.render_export import export_snapshot,default_destination
from tests.configurator import support_comparison as fixtures

class RenderExportTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.ComparisonFixture.setUp
    async def preview(self):
        await self.workspace.preview(self.view,str(self.binary));return self.workspace.latest
    async def test_preview_is_byte_identical_private_manifest_and_survives_workspace_close(self):
        snapshot=await self.preview();source=snapshot.path.read_bytes();destination=self.root/'durable preview'
        result=await export_snapshot(self.workspace,'preview',snapshot,destination)
        self.assertEqual(result,destination);self.assertEqual((result/'preview.png').read_bytes(),source)
        record=json.loads((result/'export.json').read_bytes());self.assertEqual(record['images'][0]['sha256'],hashlib.sha256(source).hexdigest())
        self.assertEqual(record['geometry'],snapshot.view.geometry);self.assertEqual(record['fixed_utc'],snapshot.view.utc)
        self.assertNotIn(str(self.binary),(result/'export.json').read_text());self.assertNotIn(str(self.workspace.root),(result/'export.json').read_text())
        self.assertEqual((result/'preview.png').stat().st_mode&0o777,0o600)
        self.workspace.close();self.assertEqual((result/'preview.png').read_bytes(),source)
    async def test_existing_destinations_are_never_changed(self):
        snapshot=await self.preview()
        for folder in (False,True):
            destination=self.root/('file' if not folder else 'folder')
            if folder:destination.mkdir();(destination/'keep').write_bytes(b'keep')
            else:destination.write_bytes(b'keep')
            with self.assertRaises(ValueError):await export_snapshot(self.workspace,'preview',snapshot,destination)
            self.assertEqual((destination/'keep' if folder else destination).read_bytes(),b'keep')
        self.assertTrue(snapshot.path.exists());self.assertFalse(self.workspace.busy)
    async def test_missing_linked_or_temporary_destination_is_refused(self):
        snapshot=await self.preview();link=self.root/'linked';link.symlink_to(self.root,target_is_directory=True)
        for destination in (self.root/'missing/new',link/'new',self.workspace.root/'not-durable',self.root/'bad\x1bname'):
            with self.subTest(destination=destination),self.assertRaises((ValueError,OSError)):
                await export_snapshot(self.workspace,'preview',snapshot,destination)
            self.assertFalse(destination.exists())
    async def test_changed_symlinked_oversize_or_wrong_geometry_source_is_refused(self):
        snapshot=await self.preview();raw=snapshot.path.read_bytes()
        with patch('configurator.render_export.IMAGE_LIMIT',16),self.assertRaises(ValueError):await export_snapshot(self.workspace,'preview',snapshot,self.root/'oversize')
        snapshot.path.write_bytes(raw+b'changed')
        with self.assertRaises(ValueError):await export_snapshot(self.workspace,'preview',snapshot,self.root/'changed')
        snapshot.path.unlink();outside=self.root/'outside';outside.write_bytes(raw);snapshot.path.symlink_to(outside)
        with self.assertRaises(ValueError):await export_snapshot(self.workspace,'preview',snapshot,self.root/'linked-output')
        self.assertEqual(outside.read_bytes(),raw)
    async def test_cancellation_before_publication_keeps_sources_and_no_destination(self):
        snapshot=await self.preview();destination=self.root/'cancelled'
        task=asyncio.create_task(export_snapshot(self.workspace,'preview',snapshot,destination));await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(destination.exists());self.assertTrue(snapshot.path.exists());self.assertFalse(self.workspace.busy)
    async def test_write_failure_cleans_only_owned_files_and_preserves_unrelated_material(self):
        from configurator.fileio import OwnedFiles
        snapshot=await self.preview();original=OwnedFiles.write
        for extra in (False,True):
            destination=self.root/('partial-extra' if extra else 'partial')
            def fail(writer,name,data):
                if name=='export.json':
                    if extra:(destination/'keep').write_bytes(b'unrelated')
                    raise OSError('injected export failure')
                return original(writer,name,data)
            with patch.object(OwnedFiles,'write',fail),self.assertRaises(OSError):await export_snapshot(self.workspace,'preview',snapshot,destination)
            if extra:self.assertEqual(list(destination.iterdir()),[destination/'keep']);self.assertEqual((destination/'keep').read_bytes(),b'unrelated')
            else:self.assertFalse(destination.exists())
            self.assertTrue(snapshot.path.exists())
    async def test_sheet_exports_exact_frames_static_html_and_manifest_then_survives_close(self):
        sheet=await render_set(self.workspace,plan(self.view),str(self.binary),config_bytes=SAMPLE.read_bytes())
        source=[path.read_bytes() for path in sheet.frames];destination=self.root/'durable sheet'
        await export_snapshot(self.workspace,'sheet',sheet,destination)
        self.assertEqual([(destination/f'frame-{i}.png').read_bytes() for i in range(1,4)],source)
        page=(destination/'index.html').read_text();self.assertIn('Durable exported snapshot',page);self.assertNotIn('removed when the editor closes',page)
        self.assertNotIn('<script',page);self.assertNotIn('http:',page);self.assertNotIn('https:',page)
        record=json.loads((destination/'export.json').read_text());self.assertEqual(record['epoch'],sheet.plan.epoch);self.assertEqual(len(record['images']),3)
        self.workspace.close();self.assertTrue((destination/'index.html').is_file());self.assertTrue((destination/'frame-3.png').is_file())
    async def test_changed_sheet_is_refused_and_current_preview_history_is_untouched(self):
        snapshot=await self.preview();sheet=await render_set(self.workspace,plan(self.view),str(self.binary),config_bytes=SAMPLE.read_bytes())
        sheet.frames[0].write_bytes(sheet.frames[0].read_bytes()+b'changed')
        with self.assertRaises(ValueError):await export_snapshot(self.workspace,'sheet',sheet,self.root/'bad-sheet')
        self.assertIs(self.workspace.latest,snapshot);self.assertTrue(snapshot.path.exists());self.assertFalse((self.root/'bad-sheet').exists())
    async def test_simultaneous_export_is_bounded_and_never_overwrites(self):
        snapshot=await self.preview();destination=self.root/'one-copy'
        results=await asyncio.gather(*(export_snapshot(self.workspace,'preview',snapshot,destination) for _ in range(2)),return_exceptions=True)
        self.assertEqual(sum(isinstance(row,Path) for row in results),1);self.assertEqual(sum(isinstance(row,ValueError) for row in results),1)
        self.assertEqual((destination/'preview.png').read_bytes(),snapshot.path.read_bytes())

    async def test_destination_shell_characters_stay_literal_and_link_cycles_fail_cleanly(self):
        snapshot=await self.preview();destination=self.root/'$(touch not-executed); literal copy'
        await export_snapshot(self.workspace,'preview',snapshot,destination)
        self.assertTrue((destination/'preview.png').exists());self.assertFalse((self.root/'not-executed').exists())
        cycle=self.root/'cycle';cycle.symlink_to(cycle)
        with self.assertRaises((ValueError,OSError)):await export_snapshot(self.workspace,'preview',snapshot,cycle/'new')
        self.assertFalse(self.workspace.busy)

    async def test_default_preview_and_sheet_create_only_durable_parents_after_validation(self):
        snapshot=await self.preview();preview=default_destination(self.root,'preview')
        self.assertEqual(preview.parent,self.root/'output/exports');self.assertFalse(preview.parent.exists())
        legacy=self.root/'config/export-preview-old';legacy.mkdir(parents=True);(legacy/'keep').write_bytes(b'old export')
        scene=self.root/'config/scenes/keep.conf';scene.parent.mkdir();scene.write_bytes(b'user scene')
        await export_snapshot(self.workspace,'preview',snapshot,preview,project_root=self.root)
        self.assertEqual((preview/'preview.png').read_bytes(),snapshot.path.read_bytes())
        for directory in (self.root/'output',preview.parent,preview):self.assertEqual(directory.stat().st_mode&0o777,0o700)
        sheet=await render_set(self.workspace,plan(self.view),str(self.binary),config_bytes=SAMPLE.read_bytes())
        destination=default_destination(self.root,'sheet')
        await export_snapshot(self.workspace,'sheet',sheet,destination,project_root=self.root)
        self.assertTrue((destination/'index.html').is_file());self.assertTrue((destination/'frame-3.png').is_file())
        self.workspace.close();self.assertTrue((preview/'preview.png').is_file())
        self.assertEqual((legacy/'keep').read_bytes(),b'old export');self.assertEqual(scene.read_bytes(),b'user scene')
        self.assertFalse((self.root/'output/preview').exists())

    async def test_cancelled_or_invalid_default_export_creates_no_parents(self):
        snapshot=await self.preview();destination=default_destination(self.root,'preview')
        task=asyncio.create_task(export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root))
        await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse((self.root/'output').exists())
        snapshot.path.write_bytes(b'changed')
        with self.assertRaises(ValueError):await export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root)
        self.assertFalse((self.root/'output').exists())

    async def test_default_export_refuses_parent_links_files_existing_copy_and_custom_missing_parent(self):
        snapshot=await self.preview();outside=self.root/'outside';outside.mkdir();(outside/'keep').write_bytes(b'outside')
        for component in ('output','output/exports'):
            target=self.root/component;target.parent.mkdir(exist_ok=True)
            for linked in (True,False):
                with self.subTest(component=component,linked=linked):
                    if linked:target.symlink_to(outside,target_is_directory=True)
                    else:target.write_bytes(b'not a directory')
                    with self.assertRaises((ValueError,OSError)):
                        await export_snapshot(self.workspace,'preview',snapshot,self.root/'output/exports/copy',project_root=self.root)
                    self.assertEqual(list(outside.iterdir()),[outside/'keep']);self.assertEqual((outside/'keep').read_bytes(),b'outside')
                    target.unlink()
        destination=self.root/'output/exports/copy'
        await export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root)
        before={p.name:p.read_bytes() for p in destination.iterdir()}
        with self.assertRaises(ValueError):await export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root)
        self.assertEqual({p.name:p.read_bytes() for p in destination.iterdir()},before)
        custom=self.root/'missing/copy'
        with self.assertRaises(ValueError):await export_snapshot(self.workspace,'preview',snapshot,custom,project_root=self.root)
        self.assertFalse(custom.parent.exists())

    async def test_failed_default_export_cleans_only_new_empty_parents(self):
        from configurator.fileio import OwnedFiles
        snapshot=await self.preview();destination=self.root/'output/exports/copy'
        with patch.object(OwnedFiles,'write',side_effect=OSError('injected failure')),self.assertRaises(OSError):
            await export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root)
        self.assertFalse((self.root/'output').exists())
        destination.parent.mkdir(parents=True);keep=destination.parent/'keep';keep.write_bytes(b'existing export')
        with patch.object(OwnedFiles,'write',side_effect=OSError('injected failure')),self.assertRaises(OSError):
            await export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root)
        self.assertEqual(keep.read_bytes(),b'existing export');self.assertFalse(destination.exists())

    async def test_replaced_default_parent_is_refused_without_following_link(self):
        import configurator.render_export as exports
        snapshot=await self.preview();destination=self.root/'output/exports/copy';outside=self.root/'outside';outside.mkdir()
        original=exports.new_directory
        def moved(target,files,**kwargs):
            destination.parent.rename(self.root/'retained-exports')
            destination.parent.symlink_to(outside,target_is_directory=True)
            return original(target,files,**kwargs)
        with patch.object(exports,'new_directory',moved),self.assertRaises(ValueError):
            await export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root)
        self.assertEqual(list(outside.iterdir()),[]);self.assertEqual(list((self.root/'retained-exports').iterdir()),[])

    async def test_replaced_default_parent_real_directory_is_not_written(self):
        import configurator.render_export as exports
        snapshot=await self.preview();destination=self.root/'output/exports/copy'
        original=exports.new_directory
        def moved(target,files,**kwargs):
            destination.parent.rename(self.root/'retained-exports')
            destination.parent.mkdir();(destination.parent/'foreign').write_bytes(b'new owner')
            return original(target,files,**kwargs)
        with patch.object(exports,'new_directory',moved),self.assertRaises(ValueError):
            await export_snapshot(self.workspace,'preview',snapshot,destination,project_root=self.root)
        self.assertEqual(list(destination.parent.iterdir()),[destination.parent/'foreign'])
        self.assertEqual((destination.parent/'foreign').read_bytes(),b'new owner')
        self.assertEqual(list((self.root/'retained-exports').iterdir()),[])
