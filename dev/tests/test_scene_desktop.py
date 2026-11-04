"""Native literal scene launch construction only; no host jobs/process control."""
import os,shutil,subprocess,sys,unittest
from tests import test_scene_selection as fixtures
from configurator.model import ROOT
from configurator.selection import REVISIONS,ARGS,SELECTOR,apply_bundle,inspect_selection


class SceneDesktopTests(unittest.TestCase):
    setUp_fixture=fixtures.SceneSelectionTests.setUp_fixture
    plan=fixtures.SceneSelectionTests.plan
    setUp=fixtures.SceneSelectionTests.setUp
    apply=fixtures.SceneSelectionTests.apply
    next_bundle=fixtures.SceneSelectionTests.next_bundle

    def shell(self,code):
        scripts=self.root/'scripts';scripts.mkdir(exist_ok=True)
        if not (scripts/'lib').exists():shutil.copytree(ROOT/'scripts/lib',scripts/'lib')
        command='project_root="$1";script_dir="$project_root/scripts"; fail() { print -u2 -r -- "$1";exit 2; }; source "$script_dir/lib/xplanet/display.zsh"; '+code
        return subprocess.run(['/bin/zsh','-f','-c',command,'scene fixture',str(self.root)],env={'PATH':'/usr/bin:/bin','HOME':str(self.root)},capture_output=True,timeout=20,cwd=self.root)

    def test_selected_arguments_use_frozen_revision_without_python_legacy_source_or_monthly_map(self):
        receipt=self.apply()
        result=self.shell('desktop_command; print -r -N -- "$XPLANET_BIN" "${desktop_args[@]}" "$EARTH_MAP_PRE"')
        self.assertEqual(result.returncode,0,result.stderr)
        args=result.stdout.split(b'\0');self.assertEqual(args[0].decode(),str(__import__('pathlib').Path(sys.executable).resolve()))
        self.assertEqual(args[args.index(b'-body')+1],b'moon');self.assertNotIn(b'-projection',args)
        self.assertEqual(args[args.index(b'-config')+1].decode(),str(self.root/REVISIONS/receipt.after.revision/'lunar.conf'))
        self.assertEqual(args[args.index(b'-geometry')+1],b'1280x720');self.assertEqual(args[args.index(b'-timewarp')+1],b'0')
        self.assertFalse((self.root/'forbidden').exists());self.assertFalse((self.root/'images/earth.png').exists())
        self.assertFalse((self.root/'.state/xplanet/desktop-tmp').exists())
        self.scene.write_bytes(b'later library edit')
        self.assertEqual(self.shell('desktop_command').returncode,0)

    def test_no_selector_retains_legacy_command_construction(self):
        (self.root/'config/xp.def').write_text('XPLANET_BIN=/usr/bin/false\nXPLANET_HOME="$project_root"\nXPLANET_CONFIG="$project_root/config"\nXPLANET_PROJECTION=rectangular\nXPLANET_LONGITUDE=20\nXPLANET_GEOMETRY=1920x1080\n')
        result=self.shell('desktop_command; print -r -N -- "${desktop_args[@]}"')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn(b'-projection=rectangular\0',result.stdout)
        self.assertIn(b'-geometry=1920x1080\0',result.stdout);self.assertFalse((self.root/SELECTOR).exists())

    def test_invalid_or_missing_selected_revision_fails_instead_of_using_legacy(self):
        path=self.root/SELECTOR
        for raw in (b'corrupt\n',b'v1 '+b'a'*64+b'\n'):
            path.write_bytes(raw);result=self.shell('desktop_command')
            self.assertEqual(result.returncode,2);self.assertIn(b'no legacy fallback',result.stderr)
        self.assertFalse((self.root/'forbidden').exists())

    def test_changed_snapshot_arguments_asset_or_manifest_fails_before_execution(self):
        receipt=self.apply();folder=self.root/REVISIONS/receipt.after.revision
        for path in (folder/'lunar.conf',folder/ARGS,folder/'deployment.plist',self.asset):
            raw=path.read_bytes();path.write_bytes(raw+b'altered')
            result=self.shell('desktop_command');self.assertEqual(result.returncode,2,(path,result.stderr))
            self.assertTrue(b'changed' in result.stderr or b'exceeds its bound' in result.stderr,result.stderr);path.write_bytes(raw)
        self.assertFalse((self.root/'forbidden').exists())

    def test_custom_renderer_names_remain_known_for_previous_revisions(self):
        self.apply();apply_bundle(self.root,self.next_bundle(),inspect_selection(self.root))
        result=self.shell('scene_renderer_names')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn(os.path.basename(os.path.realpath(sys.executable)).encode(),result.stdout)

    def test_selector_and_revision_symlinks_are_refused(self):
        receipt=self.apply();path=self.root/SELECTOR;raw=path.read_bytes();path.unlink();path.symlink_to(self.scene)
        self.assertEqual(self.shell('desktop_command').returncode,2)
        path.unlink();path.write_bytes(raw)
        folder=self.root/REVISIONS/receipt.after.revision;moved=folder.with_name('moved');folder.rename(moved);folder.symlink_to(moved,target_is_directory=True)
        self.assertEqual(self.shell('desktop_command').returncode,2)

    def test_foreground_entrypoint_executes_only_selected_fixture_renderer_with_literal_arguments(self):
        from configurator.handoff import create_plan,stage_plan
        binary=self.root/'fixture renderer';binary.write_text('#!/bin/sh\nprintf "%s\\0" "$PWD" "$@"\n');binary.chmod(0o700)
        bundle=self.root/'fixture renderer review';stage_plan(create_plan(self.root,self.scene,binary,'1280x720'),bundle)
        apply_bundle(self.root,bundle,inspect_selection(self.root))
        scripts=self.root/'scripts';scripts.mkdir(exist_ok=True);shutil.copytree(ROOT/'scripts/lib',scripts/'lib')
        result=subprocess.run(['/bin/zsh','-f',str(scripts/'lib/xplanet/desktop.zsh')],cwd=self.root,
                              env={'PATH':'/usr/bin:/bin','HOME':str(self.root)},capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        args=result.stdout.split(b'\0');self.assertEqual(args[args.index(b'-body')+1],b'moon')
        self.assertEqual(args[0].decode(),str(self.root/REVISIONS/inspect_selection(self.root).revision))
        self.assertEqual(args[args.index(b'-tmpdir')+1].decode(),str(self.root/'.state/xplanet/desktop-tmp'))
        self.assertTrue((self.root/'.state/xplanet/desktop-tmp').is_dir())
        from configurator.selection import read_revision
        read_revision(self.root,inspect_selection(self.root).revision)
        self.assertEqual(args[args.index(b'-geometry')+1],b'1280x720');self.assertNotIn(b'-projection',args)
        self.assertFalse((self.root/'forbidden').exists());self.assertFalse((self.root/'images/earth.png').exists())

    def test_stop_discovery_keeps_previous_custom_renderer_names_without_real_process_inspection(self):
        from configurator.handoff import create_plan,stage_plan
        for name in ('old-renderer','new-renderer'):
            binary=self.root/name;binary.write_text('#!/bin/sh\nexit 0\n');binary.chmod(0o700)
            bundle=self.root/(name+' review');stage_plan(create_plan(self.root,self.scene,binary,'1280x720'),bundle)
            apply_bundle(self.root,bundle,inspect_selection(self.root))
        (self.root/'config/xp.def').write_text('XPLANET_BIN=\n')
        tools=self.root/'mock-tools';tools.mkdir();trace=self.root/'pgrep-trace'
        pgrep=tools/'pgrep';pgrep.write_text('#!/bin/sh\nfor argument do last=$argument; done\nprintf "%s\\n" "$last" >> "$TRACE"\n[ "$last" = old-renderer ] || exit 1\nprintf "4242\\n"\n');pgrep.chmod(0o700)
        result=self.shell('PATH="$project_root/mock-tools:/usr/bin:/bin";export PATH;TRACE="$project_root/pgrep-trace";export TRACE;xplanet_pids')
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,b'4242\n')
        names=trace.read_text().splitlines();self.assertIn('xplanet',names);self.assertIn('old-renderer',names);self.assertIn('new-renderer',names)

    def test_selected_scratch_symlink_fails_without_writing_its_target(self):
        self.apply();outside=self.root/'untouched scratch';outside.mkdir()
        scratch=self.root/'.state/xplanet/desktop-tmp';scratch.symlink_to(outside,target_is_directory=True)
        result=self.shell('desktop_command');self.assertEqual(result.returncode,2)
        self.assertIn(b'scratch directory must be real',result.stderr)
        self.assertEqual(list(outside.iterdir()),[]);self.assertTrue(scratch.is_symlink())


    def test_orbital_camera_uses_frozen_coordinate_file_and_resized_frame_without_python(self):
        from tests.test_orbital_camera import orbital
        from configurator.library import save_named
        from configurator.handoff import create_plan,stage_plan
        scene=save_named(self.root/'config/scenes/rise.conf',orbital(),sys.executable)
        bundle=self.root/'orbital review';stage_plan(create_plan(self.root,scene,sys.executable,'3840x2160'),bundle)
        receipt=apply_bundle(self.root,bundle,inspect_selection(self.root))
        result=self.shell('desktop_command; print -r -N -- "${desktop_args[@]}"')
        self.assertEqual(result.returncode,0,result.stderr);args=result.stdout.split(b'\0')
        origin=self.root/REVISIONS/receipt.after.revision/'rise.camera.origin'
        self.assertEqual(args[args.index(b'-dynamic_origin')+1].decode(),str(origin))
        self.assertEqual(args[args.index(b'-center')+1],b'+1920+1800');self.assertNotIn(b'-origin_file',args)
        self.assertFalse((self.root/'forbidden').exists());origin.write_bytes(b'changed coordinates')
        result=self.shell('desktop_command');self.assertNotEqual(result.returncode,0)
        self.assertIn(b'scene file changed',result.stderr)
