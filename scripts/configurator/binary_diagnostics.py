"""Explicit renderer support evidence; no Textual, providers or service operations."""
import argparse,asyncio,json,os,stat,sys,tempfile
from dataclasses import asdict
from pathlib import Path
from .resources import Capabilities,BoundedLog,binary_signature,capabilities,safe

CACHE=Path('.state/configurator/binary-evidence.json')
LIMIT=256*1024

def location(root,create=False):
    root=Path(root).resolve()
    for part in (root/'.state',root/'.state/configurator'):
        if create:
            try:part.mkdir(mode=0o700)
            except FileExistsError:pass
        if part.is_symlink() or not part.is_dir() or part.resolve()!=part:raise ValueError('Diagnostic state directory is absent or linked.')
    return root/CACHE

def store(root,report):
    path=location(root,True)
    if path.is_symlink() or path.exists() and not path.is_file():raise ValueError('Diagnostic evidence destination is not a regular file.')
    data=asdict(report);data['renderer']=str(report.renderer)
    data={'schema':1,'report':data}
    raw=json.dumps(data,ensure_ascii=True).encode()
    if len(raw)>LIMIT:raise ValueError('Diagnostic evidence exceeds its bound.')
    fd,name=tempfile.mkstemp(prefix='.binary-evidence-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        try:os.unlink(name)
        except FileNotFoundError:pass

def load(root):
    path=location(root)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>LIMIT:raise ValueError('Diagnostic evidence is not a bounded regular file.')
        raw=stream.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError('Diagnostic evidence exceeds its bound.')
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get('schema')!=1:raise ValueError('Unknown diagnostic evidence format.')
    row=data['report']
    if not isinstance(row,dict) or set(row)!={'renderer','binary_identity','status','features','raw','log_bytes','completed_utc','exit_code','truncated'}:raise ValueError('Invalid diagnostic evidence fields.')
    if not isinstance(row['renderer'],str) or not Path(row['renderer']).is_absolute():raise ValueError('Invalid diagnostic executable.')
    if not isinstance(row['binary_identity'],list) or len(row['binary_identity'])!=5 or any(type(v) is not int for v in row['binary_identity']):raise ValueError('Invalid diagnostic identity.')
    for key in ('status','raw','completed_utc'):
        if not isinstance(row[key],str):raise ValueError('Invalid diagnostic text.')
    if not isinstance(row['features'],list) or any(not isinstance(v,str) or len(v)>200 or any(not c.isprintable() for c in v) for v in row['features']):raise ValueError('Invalid diagnostic support list.')
    if type(row['log_bytes']) is not int or row['log_bytes']<0 or type(row['truncated']) is not bool or row['exit_code'] is not None and type(row['exit_code']) is not int:raise ValueError('Invalid diagnostic result.')
    row['renderer']=Path(row['renderer']);row['binary_identity']=tuple(row['binary_identity']);row['features']=tuple(row['features'])
    return Capabilities(**row)

def cached(root):
    try:return load(root)
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,RecursionError):return None

async def probe(renderer,timeout=5):
    # Reuse the configurator's owned-process cleanup and strict support parser.
    from .workspace import Workspace
    binary=Path(renderer).expanduser().resolve(strict=True)
    if not binary.is_file() or not os.access(binary,os.X_OK):raise ValueError('Renderer must be an executable regular file.')
    stamp,digest=binary_signature(binary);log=BoundedLog();code=None
    workspace=Workspace()
    try:
        with tempfile.TemporaryDirectory(prefix='xplanet-version-') as folder:
            work=Path(folder);config=work/'empty.conf';config.write_text('[default]\n')
            env={**os.environ,'HOME':folder,'TMPDIR':folder,'XDG_CACHE_HOME':folder,'PYTHONDONTWRITEBYTECODE':'1'}
            try:
                code=await workspace._run_child([str(binary),'-version','-output',str(work/'probe.png'),'-num_times','1','-tmpdir',folder,'-config',str(config)],work,env,log,timeout)
            except (OSError,asyncio.TimeoutError) as exc:log.feed(('\nProbe runtime error: '+(str(exc) or type(exc).__name__)).encode())
    finally:workspace.close()
    return capabilities(binary,stamp,log,code,expected_hash=digest)

def main():
    parser=argparse.ArgumentParser(description='On-demand renderer support evidence; never starts the desktop.')
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--renderer',required=True)
    parser.add_argument('--show',action='store_true',help='Read previous evidence without executing the renderer')
    args=parser.parse_args()
    try:
        if args.show:
            report=load(args.root)
            match=report.matches(args.renderer)
            print('Cached evidence: '+('metadata matches this selected executable; not a fresh probe.' if match else 'STALE or different from the selected executable; support for this choice remains unknown.'))
        else:
            report=asyncio.run(probe(args.renderer))
            store(args.root,report)
        print('Diagnostic choice only; not necessarily the next-start choice. This does not identify a running process.')
        print('\n\n'.join(report.sections()))
        print('Evidence contains local paths; review before sharing. No original compiler flags are reconstructed.')
        return 0 if report.status=='reported' and (not args.show or match) else 1
    except KeyboardInterrupt:
        print('Renderer diagnostic interrupted; capabilities unknown. No new evidence saved.',file=sys.stderr);return 130
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,RecursionError) as exc:
        print('Renderer capabilities unknown: '+safe(exc),file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
