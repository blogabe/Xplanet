"""Deterministic overlap with fake launchctl; never host services or renderer."""
import fcntl,json,os,shlex,subprocess,sys,time
from pathlib import Path
from .support import Sandbox,copy_launcher

class LifecycleRaceTests(Sandbox):
    def setUp(self):
        super().setUp();self.bin=self.base/'bin';self.bin.mkdir();self.runtime=self.base/'runtime';self.runtime.mkdir(mode=0o700)
        self.jobs=self.base/'job.json';self.jobs.write_text('{"root":"seed"}')
        self.marker=self.base/'kickstart-entered';self.trace=self.base/'calls.jsonl'
        self.release=self.base/'release-kickstart'
        self.script(self.bin/'getconf','printf "%s\\n" '+shlex.quote(str(self.runtime))+'\n')
        self.script(self.bin/'pgrep','exit 1\n')
        code='''import json,os,sys,time
from pathlib import Path
args=sys.argv[1:];jobs=Path(os.environ['JOBS']);trace=Path(os.environ['TRACE']);actor=os.environ.get('ACTOR','A')
def log(step):
 with trace.open('a') as out:out.write(json.dumps([actor,args[0],step])+'\\n')
log('begin')
if args[0] in ('list','print'):raise SystemExit(0 if jobs.exists() else 3)
if args[0]=='bootout':
 if not jobs.exists():raise SystemExit(3)
 jobs.unlink()
if args[0]=='bootstrap':
 if jobs.exists():raise SystemExit(5)
 jobs.write_text(json.dumps({'root':actor}))
if args[0]=='kickstart':
 if actor=='A' and os.environ.get('HOLD')=='1':
  Path(os.environ['MARKER']).write_text('entered')
  deadline=time.monotonic()+10
  while not Path(os.environ['RELEASE']).exists():
   if time.monotonic()>deadline:raise SystemExit('test did not release kickstart')
   time.sleep(.005)
 if not jobs.exists():log('missing-job');raise SystemExit(3)
log('end')
'''
        self.script(self.bin/'launchctl',code,python=True)
        self.entry=self.checkout(self.root)
        self.env={**os.environ,'PATH':str(self.bin)+':/usr/bin:/bin','JOBS':str(self.jobs),'TRACE':str(self.trace),'MARKER':str(self.marker),'RELEASE':str(self.release),'PYTHONDONTWRITEBYTECODE':'1'}
    def script(self,path,body,python=False):path.write_text(('#!'+sys.executable if python else '#!/bin/sh')+'\n'+body);path.chmod(0o700)
    def checkout(self,root):
        scripts=root/'scripts';scripts.mkdir(parents=True);entry=scripts/'xplanet.sh';copy_launcher(entry)
        config=root/'config';config.mkdir();(config/'xp.conf').write_text('[earth]\n')
        (config/'xp.def').write_text('XPLANET_BIN=/usr/bin/true\nXPLANET_HOME='+shlex.quote(str(root))+'\nXPLANET_CONFIG='+shlex.quote(str(config))+'\nXPLANET_PROJECTION=rectangular\nXPLANET_LONGITUDE=0\n')
        return entry
    def invoke(self,entry,command,actor):return subprocess.Popen([str(entry),command],env={**self.env,'ACTOR':actor},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def overlap(self,second_entry,second_command='restart'):
        self.env['HOLD']='1'
        first=self.invoke(self.entry,'restart','A');second=None
        try:
            end=time.monotonic()+8
            while not self.marker.exists() and first.poll() is None and time.monotonic()<end:time.sleep(.005)
            self.assertTrue(self.marker.exists(),'first restart never reached isolated kickstart')
            # zsh's native flock uses POSIX record locks, as does lockf.
            # Verify ownership while A is held, independently of B's scheduling.
            with (self.runtime/'local.xplanet.desktop.lock').open('r+') as lock:
                with self.assertRaises(BlockingIOError):
                    fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            second=self.invoke(second_entry,second_command,'B')
            self.release.write_text('continue')
            aout,aerr=first.communicate(timeout=15);bout,berr=second.communicate(timeout=15)
            self.assertEqual(first.returncode,0,(aout,aerr));self.assertEqual(second.returncode,0,(bout,berr))
            rows=[json.loads(line) for line in self.trace.read_text().splitlines()]
            self.assertNotIn(['A','kickstart','missing-job'],rows)
            if second_command=='restart':self.assertEqual(json.loads(self.jobs.read_text())['root'],'B')
            else:self.assertFalse(self.jobs.exists())
            aend=rows.index(['A','kickstart','end']);bremove=rows.index(['B','bootout','begin'])
            self.assertLess(aend,bremove,'restart must finish before another stop removes the job')
        finally:
            for child in (first,second):
                if child is not None and child.poll() is None:child.kill();child.communicate()
    def test_overlapping_restart_is_serialized_in_one_checkout(self):self.overlap(self.entry)
    def test_overlapping_restart_uses_same_user_lock_across_checkouts(self):
        self.overlap(self.checkout(self.base/'second checkout'))
    def test_overlapping_stop_waits_for_start_then_leaves_stopped(self):self.overlap(self.entry,'stop')

    def test_restart_invalid_command_preserves_existing_job_without_service_calls(self):
        definition=self.root/'config/xp.def'
        original_definition=definition.read_text()
        self.assertEqual(original_definition.count('XPLANET_BIN=/usr/bin/true'),1)
        definition.write_text(original_definition.replace('XPLANET_BIN=/usr/bin/true','XPLANET_BIN=/missing/renderer'))
        original=self.jobs.read_bytes()
        child=self.invoke(self.entry,'restart','A');out,err=child.communicate(timeout=10)
        self.assertEqual(child.returncode,2,(out,err))
        self.assertEqual(self.jobs.read_bytes(),original)
        self.assertIn('xp.def XPLANET_BIN must be executable',err)
        self.assertFalse(self.trace.exists(),'invalid preflight must not call launchctl')

    def test_restart_invalid_monthly_map_preserves_job_and_files(self):
        definition=self.root/'config/xp.def'
        with definition.open('a') as stream:stream.write('EARTH_MAP_PRE=world/world\n')
        maps=self.root/'maps/world';maps.mkdir(parents=True)
        images=self.root/'images';images.mkdir()
        before_job=self.jobs.read_bytes()
        for problem in ('missing source','missing images','regular link','external link','locked','valid'):
            with self.subTest(problem=problem):
                for month in range(1,13):
                    image=maps/f'world.2004{month:02d}.3x5400x2700.png'
                    if problem!='missing source':image.write_bytes(b'map')
                if not images.exists():images.mkdir()
                link=images/'earth.png'
                if link.is_symlink() or link.exists():link.unlink()
                lock=self.root/'.state/totalmarker/map.lock.d'
                if lock.exists():lock.rmdir()
                for directory in (lock.parent,lock.parent.parent):
                    if directory.exists():directory.rmdir()
                if problem=='missing images':images.rmdir()
                if problem=='regular link':link.write_bytes(b'user image')
                elif problem=='external link':link.symlink_to('/private/custom-map.png')
                elif problem=='locked':lock.mkdir(parents=True)
                before={str(path.relative_to(self.root)):(('link',str(path.readlink())) if path.is_symlink() else ('file',path.read_bytes()) if path.is_file() else ('directory',path.stat().st_mode)) for path in self.root.rglob('*')}
                if problem=='valid':
                    # Directly exercise the private read-only path: no .state creation.
                    result=subprocess.run(['/bin/zsh','-f','-c','project_root=$1;script_dir="$1/scripts";fail() { print -u2 -r -- "$1";exit 2; };source "$script_dir/lib/xplanet/display.zsh";select_earth_map --check','audit',str(self.root)],env=self.env,capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                else:
                    child=self.invoke(self.entry,'restart','A');out,err=child.communicate(timeout=5)
                    self.assertEqual(child.returncode,2,(out,err))
                    reason={'missing source':'Monthly map is absent or not a regular file',
                            'missing images':'images must be a real directory',
                            'regular link':'images/earth.png is not a symlink',
                            'external link':'images/earth.png is not an internal map link',
                            'locked':'Earth map selection is locked'}[problem]
                    self.assertIn(reason,err)
                    self.assertEqual(self.jobs.read_bytes(),before_job)
                    self.assertFalse(self.trace.exists(),'map preflight must precede any launchctl call')
                after={str(path.relative_to(self.root)):(('link',str(path.readlink())) if path.is_symlink() else ('file',path.read_bytes()) if path.is_file() else ('directory',path.stat().st_mode)) for path in self.root.rglob('*')}
                self.assertEqual(after,before)

    def test_start_does_not_kickstart_a_job_from_another_checkout(self):
        with (self.root/'config/xp.def').open('a') as definition:definition.write('EARTH_MAP_PRE=absent/map\n')
        self.script(self.bin/'launchctl','[ "$1" = print ] && { printf "%s\\n" "program = /bin/zsh" "working directory = /another checkout" "arguments = {" "/bin/zsh" "/another checkout/scripts/lib/xplanet/desktop.zsh" "}"; exit 0; }; printf unexpected > "$TRACE"; exit 9\n')
        child=self.invoke(self.entry,'start','A');out,err=child.communicate(timeout=5)
        self.assertEqual(child.returncode,2,(out,err))
        self.assertIn('another or unverified checkout',err)
        self.assertFalse(self.trace.exists())

    def test_job_identity_parser_accepts_spaces_and_rejects_ambiguous_fields(self):
        spaced=self.base/'checkout with spaces';self.checkout(spaced)
        helper=spaced/'scripts/lib/xplanet/display.zsh'
        root=str(spaced)
        good='program = /bin/zsh\nworking directory = '+root+'\narguments = {\n/bin/zsh\n'+root+'/scripts/lib/xplanet/desktop.zsh\n}\n'
        for text,expected in ((good,0),(good+'working directory = /other\n',1),(good.replace('program = /bin/zsh','program = /bin/sh'),1),(good.replace('arguments = {','arguments = {\nextra'),1)):
            result=subprocess.run(['/bin/zsh','-f','-c','project_root=$1;script_dir="$1/scripts";source "$2";desktop_job_owned "$3"','audit',root,str(helper),text],capture_output=True,text=True)
            self.assertEqual(result.returncode,expected,(text,result.stderr))

    def test_failed_command_releases_lock_and_lock_inode_is_retained(self):
        config=self.root/'config/xp.def';original=config.read_bytes();config.write_text('invalid assignment\n')
        failed=self.invoke(self.entry,'start','A');out,err=failed.communicate(timeout=10)
        self.assertEqual(failed.returncode,2,(out,err));lock=self.runtime/'local.xplanet.desktop.lock'
        self.assertTrue(lock.is_file());inode=lock.stat().st_ino;config.write_bytes(original)
        self.jobs.unlink(missing_ok=True);ok=self.invoke(self.entry,'start','A');out,err=ok.communicate(timeout=10)
        self.assertEqual(ok.returncode,0,(out,err));self.assertEqual(lock.stat().st_ino,inode)
        self.assertEqual(lock.stat().st_mode&0o777,0o600)

    def test_linked_or_nonprivate_lock_is_refused_without_repair_or_service_calls(self):
        lock=self.runtime/'local.xplanet.desktop.lock';target=self.base/'keep';target.write_bytes(b'keep')
        lock.symlink_to(target)
        for linked in (True,False):
            if not linked:lock.unlink();lock.write_bytes(b'keep');lock.chmod(0o644)
            child=self.invoke(self.entry,'stop','A');out,err=child.communicate(timeout=5)
            self.assertEqual(child.returncode,2,(out,err));self.assertIn('private user-owned regular file',err)
            self.assertFalse(self.trace.exists());self.assertEqual(target.read_bytes(),b'keep')
        self.assertEqual(lock.stat().st_mode&0o777,0o644)

    def test_busy_lock_times_out_without_service_calls_and_releases_after_owner_exit(self):
        import fcntl
        lock=self.runtime/'local.xplanet.desktop.lock';lock.touch(mode=0o600)
        # Only shorten the test checkout's wait, not the production default.
        helper=self.root/'scripts/lib/xplanet/lifecycle.zsh';original=helper.read_text()
        self.assertEqual(original.count('flock -t 10'),1)
        helper.write_text(original.replace('flock -t 10','flock -t 0.1'))
        with lock.open('r+') as stream:
            fcntl.lockf(stream,fcntl.LOCK_EX)
            child=self.invoke(self.entry,'stop','A');out,err=child.communicate(timeout=5)
            self.assertEqual(child.returncode,2,(out,err));self.assertIn('busy',err);self.assertFalse(self.trace.exists())
        child=self.invoke(self.entry,'stop','A');out,err=child.communicate(timeout=5)
        self.assertEqual(child.returncode,0,(out,err));self.assertTrue(self.trace.exists());self.assertTrue(lock.exists())

    def removal_fixture(self, *, stuck=False, wrong_domain=False):
        code = r"""import json,os,sys
from pathlib import Path
args=sys.argv[1:]; job=Path(os.environ['JOBS']); trace=Path(os.environ['TRACE'])
with trace.open('a') as out:out.write(json.dumps(args)+'\n')
pending=job.with_suffix('.pending')
if args[0]=='list':raise SystemExit(0 if os.environ.get('WRONG_DOMAIN') or job.exists() else 3)
if args[0]=='print':
 if pending.exists() and not os.environ.get('STUCK_REMOVAL'):
  remaining=int(pending.read_text())
  if remaining:pending.write_text(str(remaining-1))
  else:job.unlink(missing_ok=True);pending.unlink()
 raise SystemExit(0 if job.exists() else 3)
if args[0]=='bootout':pending.write_text('2');raise SystemExit(0)
if args[0]=='bootstrap':
 if job.exists():raise SystemExit(5)
 job.write_text('{}');raise SystemExit(0)
if args[0]=='kickstart':
 if pending.exists():job.unlink(missing_ok=True)
 raise SystemExit(0 if job.exists() else 3)
raise SystemExit(4)
"""
        self.script(self.bin/'launchctl',code,python=True)
        if wrong_domain:self.jobs.unlink()
        self.env.update({'STUCK_REMOVAL':'1' if stuck else '', 'WRONG_DOMAIN':'1' if wrong_domain else ''})

    def test_restart_waits_for_delayed_service_removal_before_registration(self):
        self.removal_fixture()
        child=self.invoke(self.entry,'restart','A');out,err=child.communicate(timeout=10)
        self.assertEqual(child.returncode,0,(out,err))
        calls=[json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertEqual(sum(c[0]=='bootstrap' for c in calls),1)
        self.assertEqual(sum(c[0]=='kickstart' for c in calls),1)
        self.assertTrue(self.jobs.exists())

    def test_start_uses_target_gui_domain_not_contextual_list(self):
        self.removal_fixture(wrong_domain=True)
        child=self.invoke(self.entry,'start','A');out,err=child.communicate(timeout=10)
        self.assertEqual(child.returncode,0,(out,err))
        calls=[json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertFalse(any(c[0]=='list' for c in calls))
        self.assertIn(['print',f'gui/{os.geteuid()}/local.xplanet.desktop'],calls)

    def test_stuck_removal_fails_without_bootstrap_or_kickstart(self):
        self.removal_fixture(stuck=True)
        child=self.invoke(self.entry,'restart','A');out,err=child.communicate(timeout=10)
        self.assertEqual(child.returncode,2,(out,err))
        self.assertIn('desktop job removal',err)
        calls=[json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertFalse(any(c[0] in ('bootstrap','kickstart') for c in calls))

    def test_start_waits_for_registration_visibility_before_kickstart(self):
        self.jobs.unlink()
        code = r"""import os,sys
from pathlib import Path
args=sys.argv[1:]; job=Path(os.environ['JOBS']); pending=job.with_suffix('.pending')
if args[0] in ('list','print'):
 if pending.exists():
  n=int(pending.read_text())
  if n:pending.write_text(str(n-1))
  else:job.write_text('{}');pending.unlink()
 raise SystemExit(0 if job.exists() else 3)
if args[0]=='bootstrap':pending.write_text('2');raise SystemExit(0)
if args[0]=='kickstart':raise SystemExit(0 if job.exists() else 3)
raise SystemExit(4)
"""
        self.script(self.bin/'launchctl',code,python=True)
        child=self.invoke(self.entry,'start','A');out,err=child.communicate(timeout=10)
        self.assertEqual(child.returncode,0,(out,err));self.assertTrue(self.jobs.exists())
