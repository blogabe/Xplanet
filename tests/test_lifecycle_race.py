"""Deterministic overlap with fake launchctl; never host services or renderer."""
import json,os,shlex,subprocess,sys,time
from pathlib import Path
from .support import Sandbox,copy_launcher

class LifecycleRaceTests(Sandbox):
    def setUp(self):
        super().setUp();self.bin=self.base/'bin';self.bin.mkdir();self.runtime=self.base/'runtime';self.runtime.mkdir(mode=0o700)
        self.jobs=self.base/'job.json';self.jobs.write_text('{"root":"seed"}')
        self.marker=self.base/'kickstart-entered';self.trace=self.base/'calls.jsonl'
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
 if actor=='B':time.sleep(.4)
if args[0]=='bootstrap':
 if jobs.exists():raise SystemExit(5)
 jobs.write_text(json.dumps({'root':actor}))
if args[0]=='kickstart':
 if actor=='A':Path(os.environ['MARKER']).write_text('entered');time.sleep(.2)
 if not jobs.exists():log('missing-job');raise SystemExit(3)
log('end')
'''
        self.script(self.bin/'launchctl',code,python=True)
        self.entry=self.checkout(self.root)
        self.env={**os.environ,'PATH':str(self.bin)+':/usr/bin:/bin','JOBS':str(self.jobs),'TRACE':str(self.trace),'MARKER':str(self.marker),'PYTHONDONTWRITEBYTECODE':'1'}
    def script(self,path,body,python=False):path.write_text(('#!'+sys.executable if python else '#!/bin/sh')+'\n'+body);path.chmod(0o700)
    def checkout(self,root):
        scripts=root/'scripts';scripts.mkdir(parents=True);entry=scripts/'xplanet.sh';copy_launcher(entry)
        config=root/'config';config.mkdir();(config/'xp.conf').write_text('[earth]\n')
        (config/'xp.def').write_text('XPLANET_BIN=/usr/bin/true\nXPLANET_HOME='+shlex.quote(str(root))+'\nXPLANET_CONFIG='+shlex.quote(str(config))+'\nXPLANET_PROJECTION=rectangular\nXPLANET_LONGITUDE=0\n')
        return entry
    def invoke(self,entry,command,actor):return subprocess.Popen([str(entry),command],env={**self.env,'ACTOR':actor},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def overlap(self,second_entry,second_command='restart'):
        first=self.invoke(self.entry,'restart','A');second=None
        try:
            end=time.monotonic()+8
            while not self.marker.exists() and first.poll() is None and time.monotonic()<end:time.sleep(.005)
            self.assertTrue(self.marker.exists(),'first restart never reached isolated kickstart')
            second=self.invoke(second_entry,second_command,'B')
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
        helper=self.root/'scripts/lib/xplanet/lifecycle.zsh';helper.write_text(helper.read_text().replace('flock -t 10','flock -t 0.1'))
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
