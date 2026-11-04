"""Three finite framing renders and a static local HTML contact sheet.

No image-processing dependency, animation engine, provider or desktop operation.
The studio draft and ordinary two-preview history are left intact.
"""
from dataclasses import dataclass,replace
from datetime import datetime,timezone
import asyncio,hashlib,html,json,os,shutil,stat,tempfile
from pathlib import Path
from .model import NUMERIC_FIELDS,View
from .fileio import fingerprint
from .resources import binary_signature,verified_identity,identity
from .workspace import Workspace,renderer_path,read_bounded

GEOMETRY='1920x1080'
IMAGE_LIMIT=16*1024*1024
WAIT_BUDGET=60

@dataclass(frozen=True)
class ComparisonPlan:
    source:View
    views:tuple[View,...]
    parameter:str
    epoch:str

@dataclass(frozen=True)
class ComparisonSet:
    index:Path
    frames:tuple[Path,...]
    plan:ComparisonPlan
    renderer:Path
    binary_identity:tuple
    file_identities:tuple=()
    def matches(self,view,renderer):
        try:return self.plan.source.render_digest()==view.render_digest() and renderer_path(renderer)==self.renderer and identity(self.renderer)==self.binary_identity
        except (OSError,ValueError,RuntimeError):return False


def reason(view):
    if view.projection!='space':return 'Framing sheets need a space view; map projections do not use these framing controls.'
    if view.camera_mode!='centre':return 'This first framing sheet supports body-centre cameras; lunar orbital camera comparisons are not implemented.'
    if view.uses_capture() or view.uses_observations():return 'Framing sheets currently require static imagery/layers. Current-data captures are not relabeled as fixed-time observations.'
    parameter=view.framing;value=getattr(view,parameter,None)
    if parameter not in ('radius','fov') or type(value) not in (int,float):return 'Enter valid radius or field-of-view framing first.'
    _,low,high=NUMERIC_FIELDS[parameter]
    if not low<=value*.75<=high or not low<=value*1.25<=high:return 'All three framing values (75%, 100%, 125%) must stay inside the existing framing bounds; choose a less extreme base value.'
    return ''


def plan(view,*,now=None):
    view.validate();problem=reason(view)
    if problem:raise ValueError(problem)
    epoch=(now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if view.time_mode=='now' else view.utc
    frozen=replace(view,time_mode='fixed',utc=epoch,geometry=GEOMETRY)
    views=tuple(replace(frozen,**{view.framing:getattr(view,view.framing)*factor}) for factor in (.75,1,1.25))
    for candidate in views:candidate.validate()
    return ComparisonPlan(view,views,view.framing,epoch)


def png_bytes(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 24<=before.st_size<=IMAGE_LIMIT:raise ValueError('Comparison PNG exceeds its 16 MiB per-frame bound or is not regular.')
        raw=read_bounded(fd,IMAGE_LIMIT)
        if fingerprint(os.fstat(fd))!=fingerprint(before) or fingerprint(os.stat(path,follow_symlinks=False))!=fingerprint(before):raise ValueError('Comparison image changed during copying.')
        if len(raw)>IMAGE_LIMIT or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR' or raw[16:24]!=(1920).to_bytes(4,'big')+(1080).to_bytes(4,'big'):raise ValueError('Comparison needs a PNG header with the requested 1920×1080 dimensions.')
        return raw
    finally:os.close(fd)


def write(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(data)


async def render_set(workspace,review,renderer,*,config_bytes=None,progress=None):
    if workspace.busy:raise ValueError('Another finite operation is running.')
    # A caller cannot smuggle a historical live-data scene through a forged plan.
    expected=plan(review.source,now=datetime.strptime(review.epoch,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc))
    if review!=expected:raise ValueError('Comparison plan changed; review again.')
    child=Workspace();directory=None;published=False
    workspace.busy=True;workspace.operation='comparison';workspace.comparison_workspace=child
    workspace.comparison_outcome='running';workspace.comparison_error=None
    deadline=asyncio.get_running_loop().time()+WAIT_BUDGET
    try:
        child.reset_captures(workspace.capture_for(review.source),workspace.observations_for(review.source))
        binary=renderer_path(renderer);stamp,binary_hash=binary_signature(binary)
        directory=Path(tempfile.mkdtemp(prefix='comparison-',dir=workspace.root));frames=[];rows=[]
        for index,view in enumerate(review.views,1):
            if progress:progress(index,len(review.views))
            remaining=deadline-asyncio.get_running_loop().time()
            if remaining<=0:raise ValueError('Comparison render-process budget expired; prior sheet retained.')
            image=await child.preview(view,str(binary),min(30,remaining),config_bytes=config_bytes)
            stamp=verified_identity(binary,stamp,binary_hash)
            raw=png_bytes(image);name=f'frame-{index}.png';write(directory/name,raw);frames.append(directory/name)
            rows.append({'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'parameter':review.parameter,'value':getattr(view,review.parameter),'epoch':review.epoch})
        caption=f'{review.source.target.title()} framing · {review.epoch} · {GEOMETRY}'
        figures=''.join('<figure><img src="'+row['file']+'" alt="'+html.escape(row['parameter']+' '+str(row['value']),quote=True)+'"><figcaption>'+html.escape(row['parameter']+' = '+str(row['value']))+'</figcaption></figure>' for row in rows)
        page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; base-uri 'none'; object-src 'none'"><title>Framing comparison</title><style>body{background:#17171c;color:#eee;font:16px system-ui;margin:2rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}figure{margin:0}img{width:100%;height:auto}figcaption{padding:.5rem}p{max-width:90ch}</style><h1>'''+html.escape(caption)+'''</h1><p>Three finite snapshots, not live output. Scene time is held fixed; a Now draft is frozen once for this reviewed set. Only framing changes; original draft, native files and desktop stay unchanged. These 16:9 images do not certify another display geometry, texture epoch or scientific accuracy. Actual resource resolution is not certified. No external resources or scripts.</p><main>'''+figures+'''</main><p>Temporary results: this sheet and images are removed when the editor closes. A later failure/cancellation retains the previous complete set.</p></html>'''
        write(directory/'index.html',page.encode())
        write(directory/'comparison.json',(json.dumps({'schema':1,'epoch':review.epoch,'geometry':GEOMETRY,'renderer_sha256':binary_hash.hex(),'frames':rows},indent=2)+'\n').encode())
        stamp=verified_identity(binary,stamp,binary_hash)
        previous=workspace.comparison_latest
        result=ComparisonSet(directory/'index.html',tuple(frames),review,binary,stamp,tuple((name,identity(directory/name)) for name in ('index.html','comparison.json',*(path.name for path in frames))))
        workspace.comparison_latest=result;workspace.comparison_outcome='succeeded';published=True
        if previous and previous.index.parent.parent==workspace.root:shutil.rmtree(previous.index.parent,ignore_errors=True)
        return result
    except asyncio.CancelledError:
        workspace.comparison_outcome='cancelled';workspace.comparison_error='Comparison cancelled; prior complete sheet retained.';raise
    except (ValueError,OSError) as exc:
        workspace.comparison_outcome='failed';workspace.comparison_error=str(exc)+' Prior complete sheet retained.';raise ValueError(workspace.comparison_error) from exc
    finally:
        await child.stop();child.close();workspace.comparison_workspace=None;workspace.busy=False;workspace.operation=None
        if directory is not None and not published:shutil.rmtree(directory,ignore_errors=True)
