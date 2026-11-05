"""Review-only deployment bundles. No selection, renderer execution or service API."""
from dataclasses import dataclass,field
from pathlib import Path
import hashlib,json,os,re,stat
from .fileio import OwnedFiles,fingerprint
from .workspace import open_view,renderer_path,read_bounded
from .geometry import geometry

MANIFEST='handoff.json'
LEGACY=('config/xp.def','config/xp.conf')
FILE_LIMIT=512*1024*1024
TOTAL_LIMIT=1024*1024*1024
NATIVE_LIMIT=128*1024*1024


def canonical(value):return json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True).encode()+b'\n'
def digest(data):return hashlib.sha256(data).hexdigest()


def real_path(path):
    value=Path(path).expanduser()
    if not value.is_absolute() or any(not c.isprintable() for c in str(value)) or value.parent!=value.parent.resolve():raise ValueError('Use an absolute path without controls or symlink ancestors.')
    return value


def file_record(path,limit=FILE_LIMIT,*,missing=False):
    path=real_path(path)
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except FileNotFoundError:
        if missing:return {'present':False}
        raise
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>limit:raise ValueError('Handoff inputs must be bounded regular files: '+str(path))
        sha=hashlib.sha256();count=0
        while chunk:=os.read(fd,65536):
            count+=len(chunk)
            if count>limit:raise ValueError('Handoff input grew beyond its bound.')
            sha.update(chunk)
        if any(fingerprint(info)!=fingerprint(before) for info in (os.fstat(fd),os.stat(path,follow_symlinks=False))):raise ValueError('Handoff input changed while hashing; review again.')
        return {'present':True,'sha256':sha.hexdigest(),'size':count,'fingerprint':list(fingerprint(before))}
    finally:os.close(fd)


def command(view,binary,root,config,search,dimensions):
    if 'norad' in view.uses_astronomy():raise ValueError('NORAD desktop handoff is unavailable: runtime epoch expiry is not enforced. Turn the NORAD layer Off to retain its capture without displaying it.')
    prefix=Path(config).stem+'.'
    args=view.arguments(asset_prefix=prefix,geometry_override=dimensions)
    if '-dynamic_origin' in args:
        index=args.index('-dynamic_origin')+1;args[index]=str(Path(config).parent/args[index])
    if args[-2:]!=['-geometry',dimensions]:raise ValueError('Preview argument contract changed; handoff must be reviewed.')
    args=[str(binary),*args[:-2],'-searchdir',str(root),'-searchdir',str(search),'-config',str(config),'-geometry',geometry(dimensions)]
    if view.time_mode=='fixed':args+=['-timewarp','0']
    return args


@dataclass(frozen=True)
class HandoffPlan:
    record:bytes=field(repr=False)
    native:tuple=field(repr=False)
    @property
    def metadata(self):return json.loads(self.record)


def create_plan(root,scene,binary,dimensions,*,_verify=True):
    root=real_path(root)
    if root!=root.resolve() or not root.is_dir():raise ValueError('Project root must be a real directory.')
    source=real_path(scene)
    try:relative=source.relative_to(root/'config/scenes')
    except ValueError:raise ValueError('Save a named scene inside this project config/scenes first.') from None
    if len(relative.parts)!=1 or relative.suffix!='.conf':raise ValueError('Choose a flat named .conf scene.')
    doc=open_view(source)
    if not doc.named_source or not doc.native_files:raise ValueError('A complete recognized named scene is required.')
    geometry(dimensions);binary=renderer_path(binary)
    native=dict(doc.native_files)
    if MANIFEST in native or len(native)>63 or sum(map(len,native.values()))>NATIVE_LIMIT:raise ValueError('Scene exceeds the handoff snapshot bound.')
    native_records={}
    for name,data in native.items():
        info=file_record(source.parent/name,NATIVE_LIMIT)
        if info['sha256']!=digest(data):raise ValueError('Scene changed after opening; reopen before review.')
        native_records[name]=info
    assets={relative.as_posix():file_record(root/relative) for relative in doc.view.resource_paths()}
    if sum(row['size'] for row in assets.values())>TOTAL_LIMIT:raise ValueError('Selected asset set exceeds 1 GiB; do not export a partial plan.')
    unbound=sorted(set(re.findall(rb'^(?:map|night_map)=([^/\r\n]+)$',doc.config,re.M)))
    data={'schema':1,'purpose':'review-only named-scene handoff','activation_ready':False,
          'root':str(root),'scene':'config/scenes/'+source.name,'snapshot_config':source.name,
          'geometry':dimensions,'preview_geometry':doc.view.geometry,'renderer':{'path':str(binary),**file_record(binary)},
          'native':native_records,'assets':assets,'legacy':{name:file_record(root/name,1024*1024,missing=True) for name in LEGACY},
          'unbound_stock_lookups':[name.decode('ascii') for name in unbound],
          'proposed_argv':command(doc.view,binary,root,'@bundle@/'+source.name,'@bundle@',dimensions),
          'notes':['This review artifact alone does not select a scene or invoke services.',
                   'Legacy definitions are hashed, never executed or included as content.',
                   'Native/captured scene files are frozen; bundled assets remain hash-bound references, not copied.',
                   'Stock lookups, incidental-body textures, fonts and compiled renderer resources are not fully bound.',
                   'Executable and file structure checks do not certify rendering or desktop capability.',
                   f'Review desktop framing at the requested geometry; saved preview geometry {doc.view.geometry} alone is not equivalent.',
                   'Now advances geometry while observations remain frozen; fixed UTC explicitly uses timewarp 0.',
                   'Producer/map jobs and the broad Stop/restart contract remain unchanged.']}
    data['id']=digest(canonical(data))
    plan=HandoffPlan(canonical(data),tuple(native.items()))
    if _verify:recheck(plan)
    return plan


def recheck(plan):
    try:
        data=plan.metadata
        fresh=create_plan(data['root'],Path(data['root'])/data['scene'],data['renderer']['path'],data['geometry'],_verify=False)
        if fresh.record!=plan.record or dict(fresh.native)!=dict(plan.native):raise ValueError('Input identity or bytes changed.')
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('Scene, asset, renderer or legacy baseline changed, or the plan was altered; export a fresh review.') from exc


def stage_plan(plan,destination):
    """Publish a new private review bundle; roll back only unchanged owned output."""
    recheck(plan);data=plan.metadata;target=real_path(destination)
    if not target.parent.is_dir():raise ValueError('Choose a new directory in an existing parent.')
    parent=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);fd=None;owned=None;identity=None
    try:
        os.mkdir(target.name,0o700,dir_fd=parent)
        info=os.stat(target.name,dir_fd=parent,follow_symlinks=False);identity=(info.st_dev,info.st_ino)
        fd=os.open(target.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);owned=OwnedFiles(fd)
        for name,raw in plan.native:owned.write(name,raw)
        doc=open_view(target/data['snapshot_config'])
        argv=command(doc.view,data['renderer']['path'],data['root'],target/data['snapshot_config'],target,data['geometry'])
        recheck(plan)
        manifest={'schema':1,'plan':data,'compiled_argv':argv}
        owned.write(MANIFEST,canonical(manifest))
        recheck(plan)
        actual=os.stat(target.name,dir_fd=parent,follow_symlinks=False);parent_info=os.fstat(parent);parent_path=os.stat(target.parent,follow_symlinks=False)
        if (actual.st_dev,actual.st_ino)!=identity or (parent_info.st_dev,parent_info.st_ino)!=(parent_path.st_dev,parent_path.st_ino):raise ValueError('Handoff destination moved during export.')
        os.fsync(fd);os.fsync(parent)
        return target
    except BaseException as exc:
        retained=owned.cleanup() if owned is not None else []
        if identity and not retained:
            try:
                current=os.stat(target.name,dir_fd=parent,follow_symlinks=False)
                if (current.st_dev,current.st_ino)==identity:os.rmdir(target.name,dir_fd=parent)
            except OSError:pass  # Concurrent/new material remains for review; never force removal.
        if identity:
            try:
                os.stat(target.name,dir_fd=parent,follow_symlinks=False)
                exc.add_note('Partial review output remains at '+str(target)+'; inspect it rather than forcing cleanup.')
            except FileNotFoundError:pass
            except OSError:exc.add_note('Could not verify cleanup at '+str(target)+'; inspect the destination before retrying.')
        raise
    finally:
        if fd is not None:os.close(fd)
        os.close(parent)


def check_bundle(root,destination):
    """Read and revalidate an exported plan; never execute its argv or definitions."""
    target=real_path(destination)
    if target!=target.resolve() or not target.is_dir():raise ValueError('Review bundle must be a real directory.')
    fd=os.open(target/MANIFEST,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>256*1024:raise ValueError('Handoff manifest is not a bounded regular file.')
        raw=read_bounded(fd,256*1024)
        if any(fingerprint(info)!=fingerprint(before) for info in (os.fstat(fd),os.stat(target/MANIFEST,follow_symlinks=False))):raise ValueError('Handoff manifest changed during reading.')
    finally:os.close(fd)
    try:
        manifest=json.loads(raw)
        if raw!=canonical(manifest) or set(manifest)!={'schema','plan','compiled_argv'} or manifest['schema']!=1:raise ValueError
        record=manifest['plan'];identity=record['id'];unsigned={k:v for k,v in record.items() if k!='id'}
        if identity!=digest(canonical(unsigned)) or record['root']!=str(real_path(root)):raise ValueError
        rebuilt=create_plan(root,Path(root)/record['scene'],record['renderer']['path'],record['geometry'])
        if rebuilt.metadata!=record:raise ValueError
        names=set()
        with os.scandir(target) as entries:
            for count,entry in enumerate(entries,1):
                if count>64:raise ValueError('Unexpected files in review bundle.')
                names.add(entry.name)
        if names!=set(record['native'])|{MANIFEST}:raise ValueError
        doc=open_view(target/record['snapshot_config'])
        if dict(doc.native_files)!=dict(rebuilt.native):raise ValueError
        expected=command(doc.view,record['renderer']['path'],root,target/record['snapshot_config'],target,record['geometry'])
        if manifest['compiled_argv']!=expected:raise ValueError
        return record
    except (KeyError,TypeError,ValueError) as exc:raise ValueError('Stale, altered or unsupported review bundle; export a fresh plan. No activation occurred.') from exc
