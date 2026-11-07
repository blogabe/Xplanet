"""Installed annotation data is explicit, bounded, frozen and native-scope aware."""
import asyncio
from dataclasses import replace
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from configurator.installed_annotations import DATASETS,FIELDS,LIMIT,import_datasets,validate_text
from configurator.model import View,SAMPLE,parse_saved_view,recognized_body,PLANET_MAPS
from configurator.workspace import Workspace,open_view,save_view
from configurator.library import save_named
from configurator.recovery import raw_fields,validate_fields,V16_FIELDS,LEGACY_FIELDS,pack,RecoveryStore
from configurator.handoff import create_plan,stage_plan,command
from configurator.selection import stage_revision,read_revision
from configurator.exchange import export_scene,import_scene
from configurator.native_inspection import inspect_native,copy_unchanged

from tests.configurator.support_installed_annotations import SOURCES

class Fixture:
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.source=self.root/'source';self.source.mkdir()
  for key,text in SOURCES.items():
   path=self.source/DATASETS[key][0];path.parent.mkdir(exist_ok=True);path.write_text(text)
  self.data=import_datasets(self.source,DATASETS)
 def scene(self,**kwargs):
  fields={field:value for key,text in self.data.items() for field,value in ((key,'on'),(key+'_text',text))}
  return View(**{**fields,**kwargs})

class AnnotationTests(Fixture,unittest.TestCase):
 def test_import_is_explicit_stable_and_preserves_attribution_without_source_path(self):
  before={p.relative_to(self.source):p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
  with patch('subprocess.run',side_effect=AssertionError('no process')):result=import_datasets(self.source,DATASETS)
  for key,text in result.items():
   self.assertEqual(validate_text(text,key),1);self.assertIn(hashlib.sha256(SOURCES[key].encode()).hexdigest(),text);self.assertNotIn(str(self.source),text)
  self.assertIn('# Test line attribution',result['sky_constellations']);self.assertIn('-16.2 21.3',result['mars_names'])
  self.assertEqual(before,{p.relative_to(self.source):p.read_bytes() for p in self.source.rglob('*') if p.is_file()})
  alias=self.root/'installed';alias.symlink_to(self.source,target_is_directory=True);self.assertEqual(import_datasets(alias,DATASETS),result)
 def test_unsafe_rows_formats_coordinates_size_and_paths_are_refused(self):
  path=self.source/'markers/brightStars'
  for text in ('91 1 "Bad" image=none\n','0 25 "Bad" image=none\n','0 1 "Bad" image=/secret\n','0 1 "Bad" font=/secret\n','0 1 "Bad" image=none\x1b\n','x'*(LIMIT+1),'0 1 "Bad" image=none\n'*129):
   path.write_text(text)
   with self.assertRaises(ValueError):import_datasets(self.source,['sky_labels'])
  path.unlink();path.symlink_to(self.source/'markers/moon')
  with self.assertRaises(ValueError):import_datasets(self.source,['sky_labels'])
  path.unlink();os.mkfifo(path)
  with self.assertRaises(ValueError):import_datasets(self.source,['sky_labels'])
  with self.assertRaises(ValueError):import_datasets('relative',['sky_labels'])
  with self.assertRaises(ValueError):import_datasets(self.source,['unknown'])
  with self.assertRaises(ValueError):import_datasets(self.source,[])
 def test_source_child_directory_symlink_and_changed_bytes_are_refused(self):
  (self.source/'markers').rename(self.source/'other');(self.source/'markers').symlink_to(self.source/'other',target_is_directory=True)
  with self.assertRaises(ValueError):import_datasets(self.source,['moon_sites'])
  (self.source/'markers').unlink();(self.source/'other').rename(self.source/'markers')
  from configurator import installed_annotations as module
  original=module.read_stable;calls=0
  def changing(*args):
   nonlocal calls
   calls+=1;raw=original(*args);return raw if calls==1 else raw+b'# changed\n'
  with patch.object(module,'read_stable',side_effect=changing),self.assertRaisesRegex(ValueError,'changed'):import_datasets(self.source,['moon_sites'])
 def test_cancellation_during_final_reread_refuses_import(self):
  import threading
  from configurator import installed_annotations as module,owned_io
  original=module.read_stable;event=threading.Event();calls=0
  def cancelling(*args):
   nonlocal calls
   raw=original(*args);calls+=1
   if calls==2:event.set()
   return raw
  token=owned_io._cancel.set(event)
  try:
   with patch.object(module,'read_stable',side_effect=cancelling),self.assertRaises(asyncio.CancelledError):import_datasets(self.source,['moon_sites'])
  finally:owned_io._cancel.reset(token)
 def test_coordinate_domains_mode_retention_and_native_scope(self):
  v=self.scene(target='moon',projection='space');v.validate()
  self.assertEqual(v.uses_annotations(),('sky_labels','sky_constellations','moon_sites'))
  self.assertIn('-marker_file',v.arguments());self.assertIn('-arc_file',v.arguments());self.assertIn(b'[moon]\nmarker_file=moon-sites.markers',v.body());self.assertNotIn(b'mars-names',v.body());self.assertTrue(recognized_body(v.body()))
  projected=replace(v,projection='rectangular');self.assertNotIn('-marker_file',projected.arguments());self.assertEqual(projected.uses_annotations(),('moon_sites',))
  mars=replace(v,target='mars',composition='system');self.assertIn(b'[mars]\nmarker_file=mars-names.markers',mars.body());self.assertTrue(recognized_body(mars.body()))
  for candidate in (v,projected,mars,replace(v,target='earth')):
   files=candidate.auxiliary_files();annotations={key:files[row[1]] for key,row in DATASETS.items()}
   reopened=parse_saved_view(candidate.definition(sys.executable).encode(),candidate.body(),annotations=annotations)
   self.assertEqual(reopened.view,candidate);self.assertEqual(len(files),4)
  missing=replace(v,sky_labels_text='')
  with self.assertRaisesRegex(ValueError,'Import'):missing.validate()
  with self.assertRaises(ValueError):v.definition(sys.executable,version=16)
 def test_save_reopen_new_copy_digest_and_tamper_are_bound(self):
  v=self.scene(target='moon',projection='space');source=save_named(self.root/'scenes/annotated.conf',v,sys.executable)
  self.assertEqual(open_view(source).view,v);self.assertIn(b'marker_file=annotated.moon-sites.markers',source.read_bytes())
  review=inspect_native(source);self.assertTrue(review.recognized);copy_unchanged(review,self.root/'copy');self.assertEqual(open_view(self.root/'copy/annotated.conf').view,v)
  self.assertNotEqual(v.render_digest(),replace(v,sky_labels_text=v.sky_labels_text.replace('Test Star','Other Star')).render_digest())
  self.assertEqual(v.render_digest(),replace(v,mars_names_text=v.mars_names_text.replace('Test Terra','Other Terra')).render_digest())
  file=source.parent/'annotated.sky-labels.markers';file.write_text(file.read_text().replace('Test Star','Altered Star'))
  with self.assertRaises(ValueError):open_view(source)
 def test_native_handoff_selection_and_exchange_preserve_owned_snapshots(self):
  # Project asset requirement is independent from imported annotation copies.
  (self.root/'config').mkdir();asset=self.root/PLANET_MAPS['moon'];asset.parent.mkdir(parents=True);asset.write_bytes(b'synthetic texture')
  v=self.scene(target='moon',projection='space',observer='earth',time_mode='fixed');source=save_named(self.root/'config/scenes/annotated.conf',v,sys.executable)
  plan=create_plan(self.root,source,sys.executable,'800x600');bundle=stage_plan(plan,self.root/'review');revision=stage_revision(self.root,bundle);record=read_revision(self.root,revision)
  self.assertTrue(all('annotated.'+row[1] in record['native'] for row in DATASETS.values()))
  args=command(v,sys.executable,self.root,source,source.parent,'800x600');self.assertEqual(args[args.index('-marker_file')+1],str(source.parent/'annotated.sky-labels.markers'))
  archive=export_scene(source,self.root/'export');imported=import_scene(archive/'scene.xplanet.zip',self.root/'imported',renderer=sys.executable,asset_root=self.root)
  self.assertEqual(open_view(imported).view,v)
  # Installed sources may disappear; saved/reviewed snapshots remain self-contained.
  for p in self.source.rglob('*'):
   if p.is_file():p.unlink()
  self.assertEqual(open_view(source).view,v);self.assertEqual(read_revision(self.root,revision),record)
 def test_recovery_prior_formats_and_invalid_raw_choices(self):
  fields=raw_fields(self.scene(),sys.executable)
  for names in (V16_FIELDS,LEGACY_FIELDS):
   old={key:value for key,value in fields.items() if key in names};upgraded=validate_fields(old)
   self.assertTrue(all(upgraded[key]==getattr(View(),key) for key in FIELDS))
  workspace=Workspace();self.addCleanup(workspace.close);record,blobs=pack(fields,raw_fields(renderer=sys.executable),SAMPLE.read_bytes(),workspace)
  store=RecoveryStore(self.root);session=store.new_session();asyncio.run(session.checkpoint(record,blobs));session.close()
  self.assertEqual(store.load(session.identity).record['current'],fields)
  # Exact v16 schema-2 checkpoint also upgrades in memory.
  record['current']={key:value for key,value in record['current'].items() if key in V16_FIELDS};record['baseline']={key:value for key,value in record['baseline'].items() if key in V16_FIELDS}
  session=store.new_session();asyncio.run(session.checkpoint(record,blobs));session.close();restored=store.load(session.identity)
  self.assertEqual(restored.record['current']['sky_labels'],'off')
