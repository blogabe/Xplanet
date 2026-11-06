"""Private recovery data, never native configuration or an activation journal.

One namespace per editing session; two hash-bound complete revisions. A short
nonblocking store lock serializes publication/quota accounting, not UI editing.
Only explicit discard or replacing this session's older checkpoints removes data.
"""
import asyncio
from .owned_io import checkpoint as io_checkpoint
from contextlib import contextmanager
from dataclasses import dataclass,field
import fcntl,hashlib,json,math,os,re,stat,time,uuid
from pathlib import Path
from .cloud_capture import FrozenCloud,IMAGE_FILE,META_FILE
from .observation_capture import FrozenObservations,META_FILE as OBS_META
from .astronomy_capture import FrozenAstronomy,FILES as ASTRONOMY_FILES,payload_names as astronomy_payload_names
from .fileio import OwnedFiles,fingerprint,same_directory
from .model import View,NUMERIC_FIELDS,choice_rules,recognized_body

META_LIMIT=2*1024*1024
BLOB_LIMIT=32*1024*1024
BUDGET=256*1024*1024
ENTRY_LIMIT=4096
SESSION=re.compile('[0-9a-f]{32}')
SHA=re.compile('[0-9a-f]{64}')
ASTRONOMY_FIELDS={'norad_layer','norad_id','eclipse_layer','eclipse_id','eclipse_window'}
LEGACY_FIELDS=(set(vars(View()))-ASTRONOMY_FIELDS)|{'renderer'}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':'))+'\n').encode()

def raw_fields(view=None,renderer=''):
    from .model import number
    values={key:number(value) if key in NUMERIC_FIELDS else value for key,value in vars(view or View()).items()}
    return {**values,'renderer':renderer}

def validate_fields(values):
    if isinstance(values,dict) and set(values)==LEGACY_FIELDS:
        values={**{key:getattr(View(),key) for key in ASTRONOMY_FIELDS},**values}
    if not isinstance(values,dict) or set(values)!=set(vars(View()))|{'renderer'}:raise ValueError('Unsupported recovery fields/version; originals retained.')
    for key,value in values.items():
        if not isinstance(value,str) or len(value.encode('utf-8'))>256*1024 or any(not c.isprintable() and not (key in ('places_text','routes_text') and c in '\n\t') for c in value):raise ValueError('Unsafe or oversized recovery field: '+key)
    for key,allowed,_ in choice_rules():
        if values[key] not in allowed:raise ValueError('Unsupported recovery choice: '+key)
    for key in ('capture_id','observations_id','norad_id','eclipse_id'):
        if values[key] and not SHA.fullmatch(values[key]):raise ValueError('Invalid frozen capture reference.')
    return values

@dataclass(frozen=True)
class Recovered:
    session:str
    revision:str
    record:dict=field(repr=False)
    config:bytes=field(repr=False)
    clouds:tuple=field(default=(),repr=False)
    observations:tuple=field(default=(),repr=False)
    fallback:bool=False
    astronomy:tuple=field(default=(),repr=False)


def pack(current,baseline,config,workspace,source=''):
    io_checkpoint()
    """Snapshot memory only; raw invalid inputs need not make a valid scene."""
    current=dict(validate_fields(current));baseline=dict(validate_fields(baseline))
    if not isinstance(config,bytes) or len(config)>256*1024 or not recognized_body(config):raise ValueError('Recovery requires a recognized studio body snapshot.')
    blobs={digest(config):config};clouds={};observations={};astronomy={}
    def refs(files):
        result={}
        for name,raw in files.items():blobs[digest(raw)]=raw;result[name]=digest(raw)
        return result
    for identity in {v['capture_id'] for v in (current,baseline)}-{''}:
        item=workspace.captures.get(identity)
        if item is None:raise ValueError('Referenced frozen cloud is unavailable; previous checkpoint retained.')
        clouds[identity]=refs(item.files())
    for identity in {v['observations_id'] for v in (current,baseline)}-{''}:
        item=workspace.observations.get(identity)
        if item is None:raise ValueError('Referenced frozen observations are unavailable; previous checkpoint retained.')
        observations[identity]=refs(item.files())
    for identity in {v[field] for v in (current,baseline) for field in ('norad_id','eclipse_id')}-{''}:
        item=workspace.astronomy.get(identity)
        if item is None:raise ValueError('Referenced astronomy capture is unavailable; previous checkpoint retained.')
        astronomy[identity]=refs(item.files())
    record={'schema':2,'at':time.time(),'current':current,'baseline':baseline,'source':''.join(c if c.isprintable() else ' ' for c in str(source or ''))[:4096],'config':digest(config),'clouds':clouds,'observations':observations,'astronomy':astronomy,'objects':{sha:len(raw) for sha,raw in blobs.items()}}
    raw=encoded(record)
    if len(raw)>META_LIMIT or len(blobs)>64 or any(len(raw)>BLOB_LIMIT for raw in blobs.values()) or sum(map(len,blobs.values()))>128*1024*1024+256*1024:raise ValueError('Recovery snapshot exceeds its metadata/capture bounds.')
    io_checkpoint()
    return record,blobs


def private(info,directory=False):
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) or info.st_uid!=os.geteuid() or info.st_mode&0o077:raise ValueError('Recovery files/directories must be private, regular and owned by this user; permissions were not changed.')


def read(fd,name,limit):
    child=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:
        before=os.fstat(child);private(before)
        if before.st_size>limit:raise ValueError('Recovery file exceeds its bound.')
        chunks=[];size=0
        while True:
            io_checkpoint()
            chunk=os.read(child,65536)
            if not chunk:break
            size+=len(chunk)
            if size>limit:raise ValueError('Recovery file grew beyond its bound.')
            chunks.append(chunk)
        if any(fingerprint(info)!=fingerprint(before) for info in (os.fstat(child),os.stat(name,dir_fd=fd,follow_symlinks=False))):raise ValueError('Recovery file changed during reading.')
        return b''.join(chunks),fingerprint(before)
    finally:os.close(child)


def json_read(fd,name,limit):
    raw,stamp=read(fd,name,limit)
    try:
        value=json.loads(raw)
        if encoded(value)!=raw:raise ValueError
    except (ValueError,TypeError,RecursionError):raise ValueError('Recovery metadata is invalid; originals retained.') from None
    return value,raw,stamp


def head(fd):
    try:value,_,_=json_read(fd,'head.json',1024)
    except FileNotFoundError:return []
    if not isinstance(value,dict) or set(value)!={'schema','revisions'} or type(value['schema']) is not int or value['schema']!=1 or not isinstance(value['revisions'],list) or not 1<=len(value['revisions'])<=2 or len(set(value['revisions']))!=len(value['revisions']) or any(not isinstance(v,str) or not SHA.fullmatch(v) for v in value['revisions']):raise ValueError('Invalid recovery checkpoint index; originals retained.')
    return value['revisions']


def metadata(fd,sha):
    value,raw,_=json_read(fd,sha+'.json',META_LIMIT)
    legacy_keys={'schema','at','current','baseline','source','config','clouds','observations','objects'}
    if digest(raw)!=sha or not isinstance(value,dict) or type(value.get('schema')) is not int:raise ValueError('Recovery checkpoint hash/schema mismatch.')
    if value['schema']==1 and set(value)==legacy_keys:
        if any(not isinstance(value[key],dict) or set(value[key])!=LEGACY_FIELDS for key in ('current','baseline')):raise ValueError('Unsupported legacy recovery fields; originals retained.')
        value={**value,'astronomy':{}}
    elif value['schema']!=2 or set(value)!=legacy_keys|{'astronomy'}:raise ValueError('Recovery checkpoint hash/schema mismatch.')
    elif any(not isinstance(value[key],dict) or set(value[key])!=set(vars(View()))|{'renderer'} for key in ('current','baseline')):raise ValueError('Unsupported recovery fields/version; originals retained.')
    value={**value,'current':dict(validate_fields(value['current'])),'baseline':dict(validate_fields(value['baseline']))}
    if type(value['at']) not in (int,float) or not math.isfinite(value['at']) or not 0<=value['at']<=32503680000:raise ValueError('Invalid recovery time.')
    if not isinstance(value['source'],str) or len(value['source'])>4096 or any(not c.isprintable() for c in value['source']):raise ValueError('Invalid source hint.')
    objects=value['objects']
    if not isinstance(objects,dict) or not 1<=len(objects)<=64 or any(not SHA.fullmatch(key) or type(size) is not int or not 0<=size<=BLOB_LIMIT for key,size in objects.items()) or sum(objects.values())>128*1024*1024+256*1024:raise ValueError('Invalid recovery object bounds.')
    referenced={value['config']}
    for kind,fields in (('clouds',('capture_id',)),('observations',('observations_id',)),('astronomy',('norad_id','eclipse_id'))):
        captures=value[kind];expected={v[field_name] for v in (value['current'],value['baseline']) for field_name in fields}-{''}
        if not isinstance(captures,dict) or set(captures)!=expected:raise ValueError('Recovery captures do not match draft references.')
        for files in captures.values():
            if not isinstance(files,dict) or not 1<=len(files)<=(19 if kind=='astronomy' else 10) or any(not isinstance(name,str) or len(name)>80 or not isinstance(sha,str) or not SHA.fullmatch(sha) for name,sha in files.items()):raise ValueError('Invalid frozen file reference.')
            referenced.update(files.values())
    if referenced!=set(objects):raise ValueError('Recovery object association mismatch.')
    return value


def recover(fd,session,sha,fallback=False):
    value=metadata(fd,sha);objects={}
    for identity,size in value['objects'].items():
        raw,_=read(fd,identity,size)
        if len(raw)!=size or digest(raw)!=identity:raise ValueError('Recovery object changed or is corrupt.')
        objects[identity]=raw
    config=objects[value['config']]
    if len(config)>256*1024 or not recognized_body(config):raise ValueError('Unsupported recovery body snapshot.')
    clouds=[];observations=[];astronomy=[]
    for identity,files in value['clouds'].items():
        if set(files)!={IMAGE_FILE,META_FILE}:raise ValueError('Unsupported cloud file association.')
        item=FrozenCloud(objects[files[IMAGE_FILE]],objects[files[META_FILE]])
        if item.identity!=identity:raise ValueError('Frozen cloud identity mismatch.')
        clouds.append(item)
    for identity,files in value['observations'].items():
        item=FrozenObservations.from_files({name:objects[sha] for name,sha in files.items()})
        if item.identity!=identity:raise ValueError('Frozen observation identity mismatch.')
        observations.append(item)
    for identity,files in value['astronomy'].items():
        products=[product for product in ASTRONOMY_FILES if f'frozen-{product}.json' in files]
        if len(products)!=1 or set(files)!={f'frozen-{products[0]}.json',*astronomy_payload_names(objects[files[f'frozen-{products[0]}.json']])}:raise ValueError('Unsupported astronomy file association.')
        item=FrozenAstronomy.from_files({name:objects[sha] for name,sha in files.items()},products[0])
        if item.identity!=identity:raise ValueError('Frozen astronomy identity mismatch.')
        astronomy.append(item)
    return Recovered(session,sha,value,config,tuple(clouds),tuple(observations),fallback,tuple(astronomy))


class RecoveryStore:
    def __init__(self,root,*,budget=BUDGET):
        self.root=Path(root);self.path=self.root/'.state/configurator/drafts';self.budget=budget

    @contextmanager
    def directory(self,create=False):
        if not self.root.is_absolute() or self.root!=self.root.resolve():raise ValueError('Recovery needs a real absolute checkout root.')
        for path in (self.root/'.state',self.root/'.state/configurator',self.path):
            if create:path.mkdir(mode=0o700,exist_ok=True)
            if path.is_symlink() or not path.is_dir() or path!=path.resolve():raise ValueError('Recovery directory is absent, linked or replaced.')
        fd=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:private(os.fstat(fd),True);same_directory(self.path,fd);yield fd;same_directory(self.path,fd)
        finally:os.close(fd)

    @contextmanager
    def lock(self,fd):
        lock=os.open('store.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=fd)
        try:
            private(os.fstat(lock))
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Another recovery writer is busy; last complete checkpoint retained.') from None
            yield
        finally:os.close(lock)

    def usage(self,fd):
        count=0;total=0
        for item in os.scandir(fd):
            count+=1
            if count>ENTRY_LIMIT:raise ValueError('Recovery directory entry limit reached.')
            info=item.stat(follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                if item.name != '.DS_Store':private(info)
                elif info.st_uid != os.geteuid():raise ValueError('Foreign Finder metadata retained; inspect recovery storage.')
                total+=info.st_size
            elif stat.S_ISDIR(info.st_mode) and SESSION.fullmatch(item.name):
                child=os.open(item.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                try:
                    private(os.fstat(child),True)
                    for entry in os.scandir(child):
                        count+=1
                        if count>ENTRY_LIMIT:raise ValueError('Recovery directory entry limit reached.')
                        info=entry.stat(follow_symlinks=False);private(info);total+=info.st_size
                finally:os.close(child)
            else:raise ValueError('Unknown or linked recovery material retained; inspect it before writing.')
        return total

    def new_session(self):return RecoverySession(self,uuid.uuid4().hex)

    @contextmanager
    def session(self,identity,directory=None):
        if not isinstance(identity,str) or not SESSION.fullmatch(identity):raise ValueError('Invalid recovery session identifier.')
        if directory is None:
            with self.directory() as parent:
                with self.session(identity,parent) as fd:yield fd
            return
        same_directory(self.path,directory)
        fd=os.open(identity,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
        try:
            private(os.fstat(fd),True);same_directory(self.path/identity,fd);yield fd
            same_directory(self.path,directory);same_directory(self.path/identity,fd)
        finally:os.close(fd)

    def entries(self):
        if not self.path.exists() and not self.path.is_symlink():return []
        rows=[]
        with self.directory() as directory:
            with os.scandir(directory) as listing:
                names=[]
                for count,item in enumerate(listing,1):
                    io_checkpoint()
                    if count>ENTRY_LIMIT:raise ValueError('Recovery directory exceeds its entry bound; inspect retained material before retrying.')
                    names.append(item.name)
            for name in names:
                io_checkpoint()
                if not SESSION.fullmatch(name):continue
                if len(rows)>=64:raise ValueError('More than 64 recovery sessions; inspect existing drafts before continuing.')
                row={'id':name,'at':None,'active':False,'error':'','fallback':False}
                try:
                    with self.session(name,directory) as fd:
                        active=os.open('active.lock',os.O_RDWR|os.O_NOFOLLOW,dir_fd=fd)
                        try:
                            private(os.fstat(active))
                            try:fcntl.flock(active,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            except BlockingIOError:row['active']=True
                        finally:os.close(active)
                        revisions=head(fd)
                        for index,sha in enumerate(revisions):
                            try:value=metadata(fd,sha)
                            except (ValueError,OSError,TypeError,KeyError):continue
                            row.update(at=value['at'],fallback=index>0,source=value['source']);break
                        else:row['error']='No complete readable checkpoint; material retained.'
                except (ValueError,OSError,TypeError,KeyError) as exc:row['error']=str(exc)
                rows.append(row)
        return sorted(rows,key=lambda row:row['at'] or 0,reverse=True)

    def load(self,identity):
        with self.session(identity) as fd:
            active=os.open('active.lock',os.O_RDWR|os.O_NOFOLLOW,dir_fd=fd)
            try:
                private(os.fstat(active))
                try:fcntl.flock(active,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise ValueError('This draft is active in another editor; it was not loaded.') from None
                for index,sha in enumerate(head(fd)):
                    try:return recover(fd,identity,sha,index>0)
                    except (ValueError,OSError,TypeError,KeyError):continue
                raise ValueError('Neither retained checkpoint is complete; files were not repaired or removed.')
            finally:os.close(active)

    def discard(self,identity,*,owner=None):
        with self.directory() as directory,self.lock(directory):
            with self.session(identity,directory) as fd:
                active=None
                try:
                    if owner is None:
                        active=os.open('active.lock',os.O_RDWR|os.O_NOFOLLOW,dir_fd=fd);private(os.fstat(active))
                        try:fcntl.flock(active,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        except BlockingIOError:raise ValueError('Active drafts cannot be discarded by another editor.') from None
                    elif owner.identity!=identity or owner.active is None:raise ValueError('Recovery ownership is no longer held.')
                    known={'active.lock','head.json'};records=head(fd)
                    for sha in records:
                        item=recover(fd,identity,sha);known.add(sha+'.json');known.update(item.record['objects'])
                    files={entry.name for entry in os.scandir(fd)}
                    for name in files-known:
                        if not SHA.fullmatch(name):raise ValueError('Unrecognized recovery material retained; discard was refused: '+name)
                        raw,_=read(fd,name,BLOB_LIMIT)
                        if digest(raw)!=name:raise ValueError('Changed orphan recovery object retained; discard was refused.')
                    if not known<=files:raise ValueError('Incomplete recovery material retained; discard was refused.')
                    owned=OwnedFiles(fd)
                    for name in files:
                        raw,stamp=read(fd,name,BLOB_LIMIT if SHA.fullmatch(name) else META_LIMIT);owned.created[name]=stamp;owned.expected[name]=(len(raw),hashlib.sha256(raw).digest())
                    same_directory(self.path/identity,fd)
                    if owned.cleanup():raise ValueError('Changed recovery material retained; discard was incomplete.')
                finally:
                    if active is not None:os.close(active)
            os.rmdir(identity,dir_fd=directory);os.fsync(directory)

class RecoverySession:
    def __init__(self,store,identity):self.store,self.identity=store,identity;self.active=None;self.verified={}
    def close(self):
        if self.active is not None:
            try:
                with self.store.directory() as directory,self.store.lock(directory):
                    empty=False
                    with self.store.session(self.identity,directory) as fd:
                        if {entry.name for entry in os.scandir(fd)}=={'active.lock'} and fingerprint(os.stat('active.lock',dir_fd=fd,follow_symlinks=False))==fingerprint(os.fstat(self.active)):
                            os.unlink('active.lock',dir_fd=fd);empty=True
                    if empty:os.rmdir(self.identity,dir_fd=directory)
            except (OSError,ValueError):pass
            finally:os.close(self.active);self.active=None

    async def checkpoint(self,record,blobs):
        raw=encoded(record);sha=digest(raw)
        if len(raw)>META_LIMIT or set(blobs)!=set(record['objects']) or any((key not in self.verified and digest(data)!=key) or len(data)!=record['objects'][key] for key,data in blobs.items()):raise ValueError('Invalid recovery checkpoint proposal.')
        with self.store.directory(True) as directory,self.store.lock(directory):
            if self.active is None:
                if len([entry for entry in os.scandir(directory) if SESSION.fullmatch(entry.name)])>=64:raise ValueError('Recovery session limit reached; existing drafts retained.')
                os.mkdir(self.identity,mode=0o700,dir_fd=directory)
                with self.store.session(self.identity,directory) as fd:
                    self.active=os.open('active.lock',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd);fcntl.flock(self.active,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.store.session(self.identity,directory) as fd:
                previous=head(fd);owned=OwnedFiles(fd);published=False;new_objects=False;pending='.pending-'+uuid.uuid4().hex
                needed=len(raw)+1024
                for key,data in blobs.items():
                    try:
                        info=os.stat(key,dir_fd=fd,follow_symlinks=False)
                        if self.verified.get(key)==fingerprint(info):continue
                        old,stamp=read(fd,key,BLOB_LIMIT)
                    except FileNotFoundError:needed+=len(data);new_objects=True;continue
                    if old!=data:raise ValueError('Existing recovery object changed; last complete checkpoint retained.')
                    self.verified[key]=stamp
                if self.store.usage(directory)+needed>self.store.budget:raise ValueError('Recovery budget is full; older unsaved drafts were not evicted. Discard an unwanted draft explicitly.')
                try:
                    for key,data in blobs.items():
                        try:os.stat(key,dir_fd=fd,follow_symlinks=False);continue
                        except FileNotFoundError:pass
                        child=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                        created=None
                        try:
                            # Record expected full bytes first; partial writes are
                            # cleaned only while still exactly our owned bytes.
                            created=os.fstat(child);written=0;written_hash=hashlib.sha256()
                            for offset in range(0,len(data),65536):
                                chunk=data[offset:offset+65536];view=memoryview(chunk)
                                while view:
                                    count=os.write(child,view)
                                    if count<=0:raise OSError('Recovery write made no progress.')
                                    written+=count;written_hash.update(view[:count]);view=view[count:]
                                await asyncio.sleep(0)
                            os.fsync(child)
                        finally:
                            try:
                                final=os.fstat(child)
                                if created is not None and (final.st_dev,final.st_ino,final.st_mode,final.st_uid,final.st_gid)==(created.st_dev,created.st_ino,created.st_mode,created.st_uid,created.st_gid):
                                    owned.created[key]=fingerprint(final);owned.expected[key]=(written,written_hash.digest())
                            finally:os.close(child)
                    if sha not in previous:owned.write(sha+'.json',raw)
                    elif read(fd,sha+'.json',META_LIMIT)[0]!=raw:raise ValueError('Existing checkpoint changed.')
                    # Validate before the only commit point. No selection/state
                    # protocol is invoked; head refers exclusively to draft data.
                    if new_objects:recover(fd,self.identity,sha)
                    else:metadata(fd,sha)
                    for key in blobs:self.verified[key]=fingerprint(os.stat(key,dir_fd=fd,follow_symlinks=False))
                    revisions=[sha,*[old for old in previous if old!=sha]][:2]
                    owned.write(pending,encoded({'schema':1,'revisions':revisions}));os.fsync(fd)
                    same_directory(self.store.path,directory);same_directory(self.store.path/self.identity,fd)
                    if head(fd)!=previous:raise ValueError('Recovery index changed; checkpoint was not selected.')
                    os.replace(pending,'head.json',src_dir_fd=fd,dst_dir_fd=fd);published=True;os.fsync(fd)
                    self._prune(fd,revisions,previous)
                    same_directory(self.store.path/self.identity,fd)
                    return sha
                finally:
                    if not published:owned.cleanup()

    def _prune(self,fd,revisions,previous):
        keep={'active.lock','head.json'}
        for sha in revisions:
            value=metadata(fd,sha);keep.add(sha+'.json');keep.update(value['objects'])
        # Ownership comes from the prior committed index, never merely from a
        # hash-shaped filename. Unindexed crash/user material stays untouched.
        candidates=set()
        for sha in set(previous)-set(revisions):
            value=metadata(fd,sha);candidates.add(sha+'.json');candidates.update(value['objects'])
        owned=OwnedFiles(fd)
        for name in candidates-keep:
            raw,stamp=read(fd,name,BLOB_LIMIT if SHA.fullmatch(name) else META_LIMIT)
            if digest(raw)!=(name if SHA.fullmatch(name) else name[:-5]):continue
            owned.created[name]=stamp;owned.expected[name]=(len(raw),hashlib.sha256(raw).digest())
        owned.cleanup()  # Changed or unknown bytes remain; quota still counts them.
