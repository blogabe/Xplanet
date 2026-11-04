"""Durable copies of owned successful render snapshots; never rerender or Apply."""
import asyncio,hashlib,json,os,stat
from datetime import datetime,timezone
from pathlib import Path
from .fileio import new_directory
from .resources import file_identity

IMAGE_LIMIT=64*1024*1024
META_LIMIT=64*1024
TEMP_NOTE=b'Temporary results: this sheet and images are removed when the editor closes. A later failure/cancellation retains the previous complete set.'
DURABLE_NOTE=b'Durable exported snapshot. These copies remain until you remove them; the studio source images remain temporary.'

def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,indent=2)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

async def read_owned(workspace,path,expected,limit):
    path=Path(path);root=workspace.root
    if not path.is_absolute() or not path.is_relative_to(root) or path!=path.resolve() or expected is None:raise ValueError('Export needs an unchanged owned successful snapshot; render again.')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or file_identity(before)!=expected or before.st_size>limit:raise ValueError('Retained render changed or exceeds its export bound; render again.')
        chunks=[];size=0
        while chunk:=os.read(fd,65536):
            size+=len(chunk)
            if size>limit:raise ValueError('Export source exceeds its bound.')
            chunks.append(chunk);await asyncio.sleep(0)
        if file_identity(os.fstat(fd))!=expected or file_identity(os.stat(path,follow_symlinks=False))!=expected or path!=path.resolve():raise ValueError('Retained render changed during export; nothing was published.')
        return b''.join(chunks)
    finally:os.close(fd)

def image(raw,geometry):
    width,height=map(int,geometry.split('x'))
    if len(raw)<24 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR' or raw[16:24]!=width.to_bytes(4,'big')+height.to_bytes(4,'big'):raise ValueError('Retained PNG header does not match its recorded geometry; render again.')
    # This verifies a container header, not a full image decode or metadata scrub.

async def export_snapshot(workspace,kind,snapshot,destination):
    if workspace.busy:raise ValueError('Wait for the current operation before exporting.')
    try:target=Path(destination).expanduser();resolved=target.resolve()
    except RuntimeError as exc:raise ValueError('Export destination cannot be resolved safely.') from exc
    if any(not c.isprintable() for c in str(target)) or not target.is_absolute():raise ValueError('Choose an absolute export directory without control characters.')
    if resolved.is_relative_to(workspace.root):raise ValueError('Choose a destination outside the temporary preview workspace.')
    workspace.busy=True;workspace.operation='export'
    try:
        files=[];receipt={'schema':1,'kind':kind,'exported_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'snapshot_only':True,'scene_time_is_not_imagery_epoch':True,
            'note':'Image copies, not a portable scene, fresh provider evidence, scientific certification or desktop activation. Embedded image metadata is retained.'}
        if kind=='preview':
            if snapshot is not workspace.latest and snapshot is not workspace.previous:raise ValueError('That preview is no longer retained; choose an available successful image.')
            raw=await read_owned(workspace,snapshot.path,snapshot.image_identity,IMAGE_LIMIT);image(raw,snapshot.view.geometry)
            files=[('preview.png',raw)]
            receipt.update(render_completed_utc=snapshot.completed_utc,scene_summary=snapshot.view.summary(),geometry=snapshot.view.geometry,
                time_mode=snapshot.view.time_mode,fixed_utc=snapshot.view.utc if snapshot.view.time_mode=='fixed' else None,
                images=[{'file':'preview.png','bytes':len(raw),'sha256':sha(raw)}])
        elif kind=='sheet':
            if snapshot is not workspace.comparison_latest:raise ValueError('That framing set is no longer retained; choose the available complete set.')
            identities=dict(snapshot.file_identities);folder=snapshot.index.parent
            page=await read_owned(workspace,snapshot.index,identities.get('index.html'),META_LIMIT)
            metadata=await read_owned(workspace,folder/'comparison.json',identities.get('comparison.json'),META_LIMIT)
            record=json.loads(metadata)
            if not isinstance(record,dict) or record.get('schema')!=1 or record.get('epoch')!=snapshot.plan.epoch or record.get('geometry')!='1920x1080' or not isinstance(record.get('frames'),list) or len(record['frames'])!=3 or len(snapshot.frames)!=3 or len(snapshot.plan.views)!=3:raise ValueError('Framing metadata no longer matches its reviewed set.')
            rows=[]
            for index,(path,row,view) in enumerate(zip(snapshot.frames,record['frames'],snapshot.plan.views),1):
                name=f'frame-{index}.png'
                if not isinstance(row,dict) or path!=folder/name or row.get('file')!=name or row.get('epoch')!=snapshot.plan.epoch or row.get('parameter')!=snapshot.plan.parameter or row.get('value')!=getattr(view,snapshot.plan.parameter):raise ValueError('Framing rows no longer match the reviewed values.')
                raw=await read_owned(workspace,path,identities.get(name),16*1024*1024);image(raw,'1920x1080')
                if sha(raw)!=row.get('sha256'):raise ValueError('Framing image hash changed; render a fresh set.')
                files.append((name,raw));rows.append({'file':name,'bytes':len(raw),'sha256':sha(raw)})
            if page.count(TEMP_NOTE)!=1:raise ValueError('Framing page does not match the supported static export format.')
            files.extend([('index.html',page.replace(TEMP_NOTE,DURABLE_NOTE)),('comparison.json',metadata)])
            receipt.update(epoch=snapshot.plan.epoch,geometry='1920x1080',parameter=snapshot.plan.parameter,images=rows)
        else:raise ValueError('Choose preview or sheet export.')
        # Cancellation is cooperative while preparing bounded bytes. Publication
        # reuses exclusive owned-file creation; no detached thread can write later.
        await asyncio.sleep(0)
        return new_directory(destination,[*files,('export.json',encoded(receipt))])
    except (KeyError,TypeError,UnicodeError,RuntimeError) as exc:raise ValueError('Retained render metadata is invalid; render again.') from exc
    finally:workspace.busy=False;workspace.operation=None
