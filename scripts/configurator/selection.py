"""Named-scene selection only. No renderer, provider, setup or service execution."""
from .owned_io import begin_publication,cleanup_io
from dataclasses import dataclass,field
from pathlib import Path
import os,plistlib,re,stat,uuid
from .fileio import fingerprint,new_directory
from .handoff import digest,real_path,file_record,check_bundle,command,geometry,LEGACY
from .workspace import open_view,read_bounded,renderer_path

SELECTOR='config/desktop.scene'
REVISIONS='.state/xplanet/scenes'
ARGS='desktop.args'
CHECKS='checks.tsv'
MANIFEST='deployment.plist'


def revision_id(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('Invalid scene revision ID.')
    return value


def read_file(path,limit):
    path=real_path(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('Expected a bounded regular scene file: '+str(path))
        raw=read_bounded(fd,limit)
        if len(raw)>limit or any(fingerprint(value)!=fingerprint(info) for value in (os.fstat(fd),os.stat(path,follow_symlinks=False))):raise ValueError('Scene file changed during reading.')
        return raw,fingerprint(info)
    finally:os.close(fd)


@dataclass(frozen=True)
class Selection:
    data:bytes|None=field(default=None,repr=False)
    identity:tuple|None=None
    @property
    def revision(self):return None if self.data is None else self.data[3:-1].decode('ascii')
    @property
    def label(self):return self.revision or 'legacy'


@dataclass(frozen=True)
class Receipt:
    before:Selection
    after:Selection


class UncertainSelection(RuntimeError):pass


def inspect_selection(root):
    path=real_path(Path(root)/SELECTOR)
    try:raw,identity=read_file(path,68)
    except FileNotFoundError:return Selection()
    if not re.fullmatch(rb'v1 [0-9a-f]{64}\n',raw):raise ValueError('Invalid config/desktop.scene; inspect it. Custom configuration fallback was not selected.')
    return Selection(raw,identity)


def prepare_state(root):
    root=real_path(root)
    if root!=root.resolve() or not root.is_dir():raise ValueError('Project root must be a real directory.')
    if not (root/'config').is_dir() or (root/'config').is_symlink():raise ValueError('A real project config directory is required.')
    for name in ('.state','.state/xplanet',REVISIONS):
        path=real_path(root/name)
        created=False
        try:path.mkdir(mode=0o700);created=True
        except FileExistsError:pass
        if path.is_symlink() or not path.is_dir():raise ValueError('Scene state must use real directories.')
        if created:
            parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(parent)
            finally:os.close(parent)


def runtime_files(record,document):
    binary=record['renderer']['path']
    args=command(document.view,binary,record['root'],'@revision@/'+record['snapshot_config'],'@revision@',record['geometry'])
    if len(args)>64 or any(not value or any(not c.isprintable() for c in value) for value in args):raise ValueError('Scene launch arguments exceed the literal runtime contract.')
    raw=('\n'.join(args)+'\n').encode()
    if len(raw)>16384:raise ValueError('Scene arguments exceed 16 KiB.')
    rows=[]
    for kind,items in (('N',record['native']),('P',record['assets']),('B',{binary:record['renderer']})):
        for name,info in sorted(items.items()):
            if any(not c.isprintable() or c=='\t' for c in name):raise ValueError('Unsafe resource path in scene revision.')
            rows.append(f"{kind}\t{info['sha256']}\t{info['size']}\t{name}\n")
    checks=''.join(rows).encode()
    if len(rows)>128 or len(checks)>32768:raise ValueError('Scene checks exceed the runtime bound.')
    return raw,checks


def same_bytes(path,info,limit):
    actual=file_record(path,limit)
    if (actual['sha256'],actual['size'])!=(info['sha256'],info['size']):raise ValueError('Selected revision resource changed: '+str(path))


def read_revision(root,identity):
    root=real_path(root);folder=real_path(root/REVISIONS/revision_id(identity))
    if folder!=folder.resolve() or not folder.is_dir():raise ValueError('Selected scene revision is absent or linked; no custom configuration fallback.')
    raw,_=read_file(folder/MANIFEST,256*1024)
    if digest(raw)!=identity:raise ValueError('Selected scene manifest hash changed.')
    try:
        value=plistlib.loads(raw)
        if raw!=plistlib.dumps(value,fmt=plistlib.FMT_XML,sort_keys=True) or set(value)!={'schema','review','args_sha256','checks_sha256'} or value['schema']!=1:raise ValueError
        record=value['review']
        if record['root']!=str(root) or record['activation_ready'] is not False:raise ValueError
        if Path(record['scene']).parent!=Path('config/scenes') or Path(record['scene']).name!=record['snapshot_config']:raise ValueError
        if set(record['legacy'])!=set(LEGACY):raise ValueError
        geometry(record['geometry'])
        binary=renderer_path(record['renderer']['path'])
        if str(binary)!=record['renderer']['path']:raise ValueError
        document=open_view(folder/record['snapshot_config'])
        native=dict(document.native_files)
        if not document.named_source or set(native)!=set(record['native']) or len(native)>61:raise ValueError
        if any(type(info['size']) is not int or not 0<=info['size']<=128*1024*1024 for info in record['native'].values()) or sum(info['size'] for info in record['native'].values())>128*1024*1024:raise ValueError
        for name,data in native.items():
            if (digest(data),len(data))!=(record['native'][name]['sha256'],record['native'][name]['size']):raise ValueError
        if set(record['assets'])!={p.as_posix() for p in document.view.resource_paths()}:raise ValueError
        if any(type(info['size']) is not int or not 0<=info['size']<=512*1024*1024 for info in record['assets'].values()) or sum(info['size'] for info in record['assets'].values())>1024*1024*1024:raise ValueError
        for name,info in record['assets'].items():same_bytes(root/name,info,512*1024*1024)
        same_bytes(binary,record['renderer'],512*1024*1024)
        args,checks=runtime_files(record,document)
        if digest(args)!=value['args_sha256'] or digest(checks)!=value['checks_sha256']:raise ValueError
        if read_file(folder/ARGS,16384)[0]!=args or read_file(folder/CHECKS,32768)[0]!=checks:raise ValueError
        names=set()
        with os.scandir(folder) as entries:
            for count,entry in enumerate(entries,1):
                if count>64:raise ValueError
                names.add(entry.name)
        if names!=set(native)|{ARGS,CHECKS,MANIFEST}:raise ValueError
        return record
    except (KeyError,TypeError,ValueError) as exc:raise ValueError('Invalid or altered scene revision; no custom configuration fallback.') from exc


def stage_revision(root,bundle):
    root=real_path(root);bundle=real_path(bundle);record=check_bundle(root,bundle)
    document=open_view(Path(bundle)/record['snapshot_config']);native=document.native_files
    if len(native)>61:raise ValueError('Scene has too many files for an immutable revision.')
    args,checks=runtime_files(record,document)
    manifest=plistlib.dumps({'schema':1,'review':record,'args_sha256':digest(args),'checks_sha256':digest(checks)},fmt=plistlib.FMT_XML,sort_keys=True)
    identity=digest(manifest);prepare_state(root);target=root/REVISIONS/identity
    if not target.exists() and not target.is_symlink():
        try:new_directory(target,(*native,(ARGS,args),(CHECKS,checks),(MANIFEST,manifest)))
        except BaseException as exc:
            if target.exists():exc.add_note('Partial scene revision retained at '+str(target)+'; inspect it, do not force cleanup.')
            raise
    parent=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(parent)
    finally:os.close(parent)
    read_revision(root,identity)
    check_bundle(root,bundle)  # Recheck original review after snapshot publication.
    return identity


def select_revision(root,identity,expected,*,_fault=lambda point:None):
    """Cooperative compare-and-swap. Uncertain publication is never auto-rolled back."""
    if not isinstance(expected,Selection):raise ValueError('Review the current selection first.')
    root=real_path(root)
    if identity is not None:read_revision(root,revision_id(identity))
    prepare_state(root);lock=root/'.state/xplanet/scene-selection.lock.d'
    try:lock.mkdir(mode=0o700)
    except FileExistsError:raise ValueError('Scene selection is locked; inspect an interrupted operation rather than discarding its lock.') from None
    lock_identity=lock.stat();config=None;pending=None;held=None;published=False
    try:
        config=os.open(root/'config',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);directory=os.fstat(config)
        if inspect_selection(root)!=expected:raise ValueError('Scene selection changed since review; no overwrite.')
        data=None if identity is None else ('v1 '+identity+'\n').encode()
        if data==expected.data:return Receipt(expected,expected)
        if data is not None:
            pending='.desktop.scene-'+uuid.uuid4().hex+'.tmp'
            held=os.open(pending,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=config)
            with os.fdopen(os.dup(held),'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        _fault('before-publish')
        if inspect_selection(root)!=expected:raise ValueError('Scene selection changed before publication; no overwrite.')
        current=os.stat(root/'config',follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(directory.st_dev,directory.st_ino):raise ValueError('Config directory changed; no selection update.')
        if pending is not None:
            raw,info=read_file(root/'config'/pending,68)
            if raw!=data or info!=fingerprint(os.fstat(held)):raise ValueError('Pending selector changed; preserve it for inspection.')
        begin_publication()
        if data is None:os.unlink('desktop.scene',dir_fd=config)
        elif expected.data is None:os.link(pending,'desktop.scene',src_dir_fd=config,dst_dir_fd=config,follow_symlinks=False)
        else:os.replace(pending,'desktop.scene',src_dir_fd=config,dst_dir_fd=config);pending=None
        published=True;_fault('after-publish')
        if pending is not None:
            raw,info=read_file(root/'config'/pending,68)
            if raw!=data or info!=fingerprint(os.fstat(held)):raise UncertainSelection('Published selector or pending link changed; inspect before retrying.')
            os.unlink(pending,dir_fd=config);pending=None
        os.fsync(config)
        after=inspect_selection(root)
        if after.data!=data or (held is not None and after.identity!=fingerprint(os.fstat(held))):raise UncertainSelection('Selection changed after publication; inspect before retrying.')
        current=os.stat(root/'config',follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(directory.st_dev,directory.st_ino):raise UncertainSelection('Config directory moved after publication; inspect both locations.')
        return Receipt(expected,after)
    except BaseException as exc:
        if published:raise UncertainSelection('Selection publication occurred; outcome requires inspection. No automatic rollback or retry.') from exc
        raise
    finally:
        if pending is not None and held is not None:
            with cleanup_io():
                try:
                    raw,info=read_file(root/'config'/pending,68)
                    if info==fingerprint(os.fstat(held)) and raw==data:os.unlink(pending,dir_fd=config)
                except (OSError,ValueError):pass  # Changed material is retained.
        if held is not None:os.close(held)
        if config is not None:os.close(config)
        try:
            current=lock.stat()
            if (current.st_dev,current.st_ino)==(lock_identity.st_dev,lock_identity.st_ino):lock.rmdir()
        except OSError:pass


def apply_bundle(root,bundle,expected):
    if inspect_selection(root)!=expected:raise ValueError('Selection changed since review; no Apply.')
    identity=stage_revision(root,bundle)
    try:return select_revision(root,identity,expected)
    except BaseException as exc:
        exc.add_note('Reviewed revision remains at '+str(Path(root)/REVISIONS/identity)+'. No producer or legacy state was rolled back.')
        raise


def restore_selection(root,receipt):
    if not isinstance(receipt,Receipt):raise ValueError('Use the receipt from a completed selection change.')
    return select_revision(root,receipt.before.revision,receipt.after)
