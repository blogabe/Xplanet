"""Finite preview and explicit new-directory save, without desktop operations."""
import asyncio
from .owned_io import OwnedIO,checkpoint as io_checkpoint
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import shutil
import stat
import sys
import re
import tempfile
from .cloud_capture import FrozenCloud, IMAGE_FILE, META_FILE, IMAGE_LIMIT, META_LIMIT, describe_capture
from .astronomy_capture import FrozenAstronomy,FILES as ASTRONOMY_FILES,META_LIMIT as ASTRONOMY_META_LIMIT,LIMIT as ASTRONOMY_LIMIT,ICON_LIMIT as ASTRONOMY_ICON_LIMIT,ICON_NAME as ASTRONOMY_ICON_NAME,payload_names as astronomy_payload_names,describe as describe_astronomy
from .geography import PLACE_FILE, ROUTE_FILE
from .installed_annotations import DATASETS as ANNOTATIONS, LIMIT as ANNOTATION_LIMIT
from .observation_capture import FrozenObservations,PRODUCTS as OBS_PRODUCTS,META_FILE as OBS_META,payload_names,describe as describe_observations,TEXT_LIMIT,ICON_LIMIT
from totalmarker.paths import RootFS
from .cloud_capture import read_stable
from .fileio import new_directory,same_directory

CAPTURE_BUDGET = 128 * 1024 * 1024

from .resources import BoundedLog,capabilities,capability_issues,resource_evidence,identity,binary_signature,verified_identity,renderer_environment
from .model import SAMPLE, View, Issue, parse_saved_view, require_valid, recognized_body, ROOT, SCENE_HEADERS, scene_prefix, ORIGIN_FILE



class _OutputProtocol(asyncio.SubprocessProtocol):
    """Separate leader exit from inherited pipe EOF using public asyncio APIs."""
    def __init__(self,log):self.log=log;self.exited=asyncio.Event();self.closed=asyncio.Event()
    def pipe_data_received(self,fd,data):self.log.feed(data)
    def process_exited(self):self.exited.set()
    def connection_lost(self,exc):self.closed.set()

class _CapturedProcess:
    def __init__(self,transport,protocol):self.transport,self.protocol=transport,protocol
    @property
    def pid(self):return self.transport.get_pid()
    @property
    def returncode(self):return self.transport.get_returncode()
    async def wait(self):
        await self.protocol.exited.wait()
        return self.returncode
    async def close_output(self):
        try:await asyncio.wait_for(self.protocol.closed.wait(),2)
        except asyncio.TimeoutError:
            self.protocol.log.feed(b'\n[... inherited output pipe remained open; bounded capture stopped ...]\n')
        finally:
            self.transport.close()
            # Close owned pipe transports even when a detached descendant keeps
            # its write end. Never signal a different/escaped process group.
            await asyncio.sleep(0)


def renderer_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Choose an absolute path to an installed Xplanet executable.')
    path = path.resolve()
    if any(c in str(path) for c in '\r\n\0'):
        raise ValueError('The renderer path must not contain control characters.')
    return path


def configuration_issues(view, renderer, config_bytes=None, capture=None, observations=None,capability_report=None,astronomy=None):
    """Read-only configuration preflight shared by health, render and save."""
    issues = view.issues()+capability_issues(capability_report,view,renderer)
    problem=view.capture_problem(capture)
    if problem:issues.append(Issue('blocking','capture_id',problem))
    if isinstance(capture,FrozenCloud) and view.uses_capture():
        meta=capture.metadata
        state=capture.freshness()
        issues.append(Issue('warning' if state!='current' else 'info','clouds',
                            f'Frozen TotalMarker input: source freshness {state}. '+describe_capture(meta)))
        if meta['last_outcome']=='failed':
            issues.append(Issue('warning','clouds','Producer reported a failed refresh when captured; verified retained output was used.'))
    problem=view.observation_problem(observations)
    if problem:issues.append(Issue('blocking','observations_id',problem))
    if observations is not None and view.uses_observations():
        issues.append(Issue('info','observations_id','Active frozen layers: '+', '.join(view.uses_observations())+'. '+describe_observations(observations)))
        for product in view.uses_observations():
            facts=observations.metadata['products'].get(product,{})
            if facts and (observations.freshness(product) in ('stale','invalid') or facts['last_outcome']=='failed'):
                issues.append(Issue('warning','observations_id',f'{product}: saved source is stale/invalid or had a failed refresh; verified frozen output is retained.'))
    problem=view.astronomy_problem(astronomy)
    if problem:issues.append(Issue('blocking','astronomy',problem))
    for product,frozen in (astronomy or {}).items():
        if not isinstance(frozen,FrozenAstronomy):continue
        issues.append(Issue('info',product+'_layer',describe_astronomy(frozen)))
        if product in view.uses_astronomy():
            available,reason=frozen.availability(target=view.target,time_mode=view.time_mode,utc=view.utc)
            issues.append(Issue('info' if available else 'blocking',product+'_layer',reason))
            if frozen.metadata['facts']['last_outcome']=='failed':issues.append(Issue('warning',product+'_layer','Saved producer reported failure; validated last-good bytes were captured. No provider request was made.'))
    try:
        renderer_path(renderer)
    except (ValueError, OSError, RuntimeError) as exc:
        issues.append(Issue('blocking', 'renderer', str(exc)))
    try:
        SAMPLE.read_bytes()
        if config_bytes is not None and not recognized_body(config_bytes):
            issues.append(Issue('blocking', 'assets', 'Unsupported body config. Reopen a recognized sample view; arbitrary configs are not rendered.'))
    except OSError:
        issues.append(Issue('blocking', 'assets', 'Cannot read the shipped Earth sample. Restore the complete checkout.'))
    for relative in view.resource_paths():
        path = ROOT / relative
        issues.append(Issue('info', 'assets', f'Requested bundled file: {path}'))
        if not path.is_file() or path.is_symlink():
            issues.append(Issue('blocking', 'assets', f'Missing bundled regular asset: {relative}. Restore the complete checkout.'))
    issues.append(Issue('info', 'assets', f'{view.appearance_summary()}. Bundled resources resolve against the current checkout; stock files use renderer lookup. Image contents and exact lookup remain unverified by file preflight alone; it does not certify compiled support. Explicit diagnostic evidence is reported separately. No provider refresh.'))
    return issues


@dataclass(frozen=True)
class PreviewSnapshot:
    path: Path
    view: View
    renderer: Path
    config_digest: str
    completed_utc: str
    diagnostics: str
    cloud_provenance: bytes | None = None
    observation_provenance: bytes | None = None
    binary_identity: tuple | None = None
    image_identity: tuple | None = None
    astronomy_provenance: tuple = ()

    def matches(self, view, renderer, config_bytes):
        try:
            return (self.view.arguments() == view.arguments() and self.renderer == renderer_path(renderer)
                    and self.binary_identity is not None and identity(self.renderer)==self.binary_identity
                    and recognized_body(config_bytes) and self.config_digest == view.render_digest())
        except (ValueError, OSError, RuntimeError):
            return False


class Workspace:
    def __init__(self):
        self.owned_io=OwnedIO()
        self.temporary = tempfile.TemporaryDirectory(prefix='xplanet-configurator-')
        self.root = Path(self.temporary.name).resolve()
        self.process = None
        self.busy = False
        self.latest = None
        self.previous = None
        self.last_outcome = 'not run'
        self.last_error = None
        self.capabilities=None
        self.last_resources=None
        self.captures = {}
        self.observations = {}
        self.astronomy = {}
        self.operation = None
        self.comparison_workspace=None
        self.comparison_latest=None
        self.comparison_outcome='not run'
        self.comparison_error=None
        self.stopping=None
        self.hard_killed=None

    def capture_bytes(self):
        return sum(len(item.image) for item in self.captures.values())+sum(item.byte_size for item in self.observations.values())+sum(item.byte_size for item in self.astronomy.values())

    def register_capture(self,capture):
        if not isinstance(capture,FrozenCloud):raise ValueError('Invalid frozen capture.')
        if capture.identity not in self.captures and self.capture_bytes()+len(capture.image)>CAPTURE_BUDGET:
            raise ValueError('Capture history reached 128 MiB. Save a new copy and reopen it before capturing again; existing captures are retained.')
        self.captures[capture.identity]=capture
        return capture.identity

    def reset_captures(self,capture=None,observations=None,astronomy=()):
        captures={capture.identity:capture} if capture is not None else {}
        observed={observations.identity:observations} if observations is not None else {}
        sky={item.identity:item for item in astronomy}
        size=sum(len(item.image) for item in captures.values())+sum(item.byte_size for item in observed.values())+sum(item.byte_size for item in sky.values())
        if size>CAPTURE_BUDGET:raise ValueError('Retained captures exceed the session budget.')
        self.captures,self.observations,self.astronomy=captures,observed,sky

    def capture_for(self,view):
        return self.captures.get(view.capture_id)

    def register_observations(self,frozen):
        if not isinstance(frozen,FrozenObservations):raise ValueError('Invalid frozen observations.')
        used=self.capture_bytes()
        if frozen.identity not in self.observations and used+frozen.byte_size>CAPTURE_BUDGET:
            raise ValueError('Capture history reached 128 MiB; save a copy and reopen it before capturing again.')
        self.observations[frozen.identity]=frozen
        return frozen.identity

    def observations_for(self,view):return self.observations.get(view.observations_id)

    def astronomy_for(self,view):
        return {product:self.astronomy[identity] for product in ASTRONOMY_FILES if (identity:=getattr(view,product+'_id')) in self.astronomy}

    def register_astronomy(self,frozen):
        if not isinstance(frozen,FrozenAstronomy):raise ValueError('Invalid frozen astronomy capture.')
        if frozen.identity not in self.astronomy and self.capture_bytes()+frozen.byte_size>CAPTURE_BUDGET:raise ValueError('Capture history reached 128 MiB; save an inactive copy and reopen it before capturing again.')
        self.astronomy[frozen.identity]=frozen
        return frozen.identity

    async def capture_astronomy(self,source_root,config,product,timeout=10):
        if product not in ASTRONOMY_FILES:raise ValueError('Choose NORAD or eclipse capture.')
        return await self._capture(source_root,config,timeout,None,astronomy_product=product)

    async def import_eclipse_file(self,source,claimed_url,timeout=10,*,first_row_date=None):
        try:source=Path(source).expanduser();source.resolve()
        except RuntimeError as exc:raise ValueError('Local eclipse path cannot be resolved safely.') from exc
        return await self._capture(None,None,timeout,None,astronomy_product='eclipse',local_eclipse=(str(source),claimed_url,first_row_date))

    async def capture_cloud(self,source_root,config,timeout=10):
        return await self._capture(source_root,config,timeout,None)

    async def capture_observations(self,source_root,config,products,timeout=10):
        if not products or not set(products)<=set(OBS_PRODUCTS):raise ValueError('Choose supported observations.')
        return await self._capture(source_root,config,timeout,tuple(products))

    async def _capture(self,source_root,config,timeout,products,*,astronomy_product=None,local_eclipse=None):
        if self.busy:raise ValueError('A finite operation is already running.')
        self.busy=True;self.operation='capture';work=None;spawn=None
        try:
            work=Path(tempfile.mkdtemp(prefix='capture-',dir=self.root))
            env={**os.environ,'PYTHONPATH':str(ROOT/'scripts'),'PYTHONDONTWRITEBYTECODE':'1'}
            module='configurator.astronomy_capture' if astronomy_product else 'configurator.observation_capture' if products else 'configurator.cloud_capture'
            extra=['--product',astronomy_product] if astronomy_product else ['--products',','.join(products)] if products else []
            source_args=['--root',source_root,'--config',config]
            if local_eclipse:source_args=['--local-eclipse',local_eclipse[0],'--reference-url',local_eclipse[1]]+(['--first-row-date',local_eclipse[2]] if local_eclipse[2] is not None else []);extra=[]
            with tempfile.TemporaryFile() as log:
                spawn=asyncio.create_task(asyncio.create_subprocess_exec(
                    sys.executable,'-B','-m',module,*source_args,
                    '--output',str(work),*extra,cwd=work,env=env,stdin=asyncio.subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True))
                try:
                    self.process=await asyncio.shield(spawn)
                    code=await asyncio.wait_for(self.process.wait(),timeout)
                    if code:
                        log.seek(0,os.SEEK_END);log.seek(max(0,log.tell()-2048))
                        detail=' '.join(log.read().decode('utf-8',errors='replace').split())
                        raise ValueError(detail or 'Capture failed; previous capture retained.')
                    fs=RootFS(work)
                    if astronomy_product:
                        meta_name=f'frozen-{astronomy_product}.json';raw=read_stable(fs,meta_name,ASTRONOMY_META_LIMIT)
                        contents={meta_name:raw,**{name:read_stable(fs,name,ASTRONOMY_ICON_LIMIT if ASTRONOMY_ICON_NAME.fullmatch(name) else ASTRONOMY_LIMIT) for name in astronomy_payload_names(raw)}}
                        frozen=FrozenAstronomy.from_files(contents,astronomy_product);self.register_astronomy(frozen)
                    elif products:
                        raw=read_stable(fs,OBS_META,16384)
                        contents={OBS_META:raw,**{name:read_stable(fs,name,ICON_LIMIT if name.endswith('.png') else TEXT_LIMIT) for name in payload_names(raw)}}
                        frozen=FrozenObservations.from_files(contents);self.register_observations(frozen)
                    else:
                        frozen=FrozenCloud(read_stable(fs,IMAGE_FILE,IMAGE_LIMIT),read_stable(fs,META_FILE,META_LIMIT));self.register_capture(frozen)
                    return frozen
                except asyncio.TimeoutError as exc:
                    raise ValueError(f'Capture exceeded its {timeout:g}-second wait budget; it was stopped. Previous capture retained.') from exc
                finally:
                    if self.process is None and spawn is not None:
                        try:self.process=await spawn
                        except OSError:pass
                    await self.stop()
        finally:
            self.busy=False;self.operation=None
            if work is not None:shutil.rmtree(work,ignore_errors=True)

    @property
    def image(self):
        return self.latest.path if self.latest else None

    async def _run_child(self,args,work,env,log,timeout):
        async def start():
            protocol=_OutputProtocol(log)
            transport,_=await asyncio.get_running_loop().subprocess_exec(
                lambda:protocol,*args,cwd=work,env=env,stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,start_new_session=True)
            return _CapturedProcess(transport,protocol)
        spawn=asyncio.create_task(start());child=None
        try:
            child=self.process=await asyncio.shield(spawn)
            return await asyncio.wait_for(child.wait(),timeout)
        finally:
            if child is None:
                try:child=self.process=await spawn
                except OSError:pass
            try:await self.stop()
            finally:
                if child is not None:await child.close_output()

    async def exchange_scene(self,mode,source,destination,*,renderer=None,preview=None,timeout=30):
        """Supervise the existing inert CLI; no detached thread can publish later."""
        if self.busy:raise ValueError('Wait for the current operation before exchanging a scene.')
        if mode not in ('export','import'):raise ValueError('Choose scene export or import.')
        try:
            source=Path(source).expanduser();target=Path(destination).expanduser()
            if not source.is_absolute() or not target.is_absolute():raise ValueError('Choose absolute source and destination paths.')
            source.resolve(strict=True)
            # Python 3.13+ no longer reports loops in non-strict resolve. A new
            # destination may lack its leaf, but its parent must already exist.
            try:resolved=target.resolve(strict=True)
            except FileNotFoundError:resolved=target.parent.resolve(strict=True)/target.name
            if preview is not None:preview=Path(preview).expanduser();preview.resolve(strict=True)
            binary=None
            if mode=='import':
                selected=Path(renderer or '').expanduser()
                if not selected.is_absolute():raise ValueError('Choose an absolute path to an installed Xplanet executable.')
                binary=renderer_path(selected.resolve(strict=True))
        except (RuntimeError,OSError) as exc:raise ValueError('Exchange paths cannot be resolved safely; choose real absolute paths without loops or unknown users.') from exc
        if resolved.is_relative_to(self.root):raise ValueError('Choose a destination outside the temporary preview workspace.')
        args=[sys.executable,'-B','-m','configurator.exchange','--'+mode,str(source),'--destination',str(target)]
        if mode=='import':
            if preview is not None:raise ValueError('Import does not accept a preview override.')
            args+=['--renderer',str(binary)]
        elif preview is not None:args+=['--preview',str(preview)]
        self.busy=True;self.operation='exchange';work=None;log=BoundedLog()
        try:
            work=Path(tempfile.mkdtemp(prefix='exchange-',dir=self.root))
            env={**os.environ,'PYTHONPATH':str(ROOT/'scripts'),'PYTHONDONTWRITEBYTECODE':'1','HOME':str(work),'TMPDIR':str(work)}
            code=await self._run_child(args,work,env,log,timeout)
            if code:raise ValueError('Scene exchange did not complete. '+(log.ending() or f'Worker exit {code}.')+' Inspect the destination before retrying; no overwrite or activation occurred.')
            return target
        except asyncio.TimeoutError as exc:
            raise ValueError('Scene exchange exceeded its wait budget and was stopped. Inspect the destination before retrying; a partial or complete new copy may exist.') from exc
        finally:
            self.busy=False;self.operation=None
            if work is not None:shutil.rmtree(work,ignore_errors=True)

    async def preview(self, view, renderer, timeout=30, *, config_bytes=None,diagnostic=False):
        if self.busy:raise ValueError('A preview is already running; cancel it or wait.')
        self.busy=True;self.operation='preview';self.last_outcome='running'
        work=None;obsolete=None;log=BoundedLog();code=None;output=None;binary=None
        if diagnostic:self.last_resources=None
        deadline=asyncio.get_running_loop().time()+timeout
        try:
            require_valid(configuration_issues(view,renderer,config_bytes,self.capture_for(view),self.observations_for(view),None if diagnostic else self.capabilities,astronomy=self.astronomy_for(view)))
            args=view.arguments();binary=renderer_path(renderer);binary_stamp,binary_hash=await self.owned_io.run(binary_signature,binary);body=view.body()
            try:
                work=Path(tempfile.mkdtemp(prefix='preview-',dir=self.root));config=work/'xp.conf';output=work/'earth.png';config.write_bytes(body)
                files=view.auxiliary_files(active_only=True)
                if view.uses_observations():files.update(self.observations_for(view).files(products=view.uses_observations()))
                if view.uses_capture():files[IMAGE_FILE]=self.capture_for(view).image
                for product in view.uses_astronomy():files.update(self.astronomy_for(view)[product].files())
                for name,data in files.items():(work/name).write_bytes(data)
            except OSError as exc:raise ValueError('Cannot prepare preview output. Check temporary-directory permissions and free space: '+str(exc)) from exc
            env=renderer_environment({**os.environ,'HOME':str(work),'TMPDIR':str(work),'XDG_CACHE_HOME':str(work),'PYTHONDONTWRITEBYTECODE':'1'})
            if diagnostic:
                version_log=BoundedLog();stamp,probe_hash=await self.owned_io.run(binary_signature,binary);probe_code=None
                try:
                    probe_code=await self._run_child([str(binary),'-version','-output',str(work/'version-probe.png'),'-num_times','1','-tmpdir',str(work),'-config',str(config),'-searchdir',str(ROOT)],work,env,version_log,min(5,max(.001,deadline-asyncio.get_running_loop().time())))
                except (OSError,asyncio.TimeoutError) as exc:version_log.feed(('\nProbe runtime error: '+(str(exc) or type(exc).__name__)).encode())
                self.capabilities=capabilities(binary,stamp,version_log,probe_code,expected_hash=probe_hash)
                require_valid(capability_issues(self.capabilities,view,renderer))
            remaining=deadline-asyncio.get_running_loop().time()
            if remaining<=0:raise ValueError('Preview process budget expired before rendering; previous preview retained.')
            command=[str(binary),*args,'-searchdir',str(ROOT),'-config',str(config),'-searchdir',str(work),'-output',str(output),'-num_times','1','-tmpdir',str(work)]
            if diagnostic:command+=['-verbosity','3']
            try:code=await self._run_child(command,work,env,log,remaining)
            except asyncio.TimeoutError:raise
            except OSError as exc:raise ValueError('Cannot run the selected Xplanet. Check its executable permissions and binary architecture: '+str(exc)) from exc
            detail=log.ending()
            if code or not output.is_file():raise ValueError(f'Xplanet failed (exit {code}); check the executable, PNG output support and stock texture lookup. {detail or "No image was produced."}')
            with output.open('rb') as image:header=image.read(24)
            if header[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Xplanet did not produce a PNG. Check the selected executable and its PNG build support.')
            if len(header)>=24 and header[12:16]==b'IHDR':
                import struct
                if struct.unpack('>II',header[16:24])!=tuple(map(int,view.geometry.split('x'))):raise ValueError('PNG header dimensions differ from the requested preview geometry; output was not retained.')
            try:binary_stamp=await self.owned_io.run(verified_identity,binary,binary_stamp,binary_hash)
            except ValueError as exc:raise ValueError('Renderer changed during preview; rerun with the current executable. Output was not retained.') from exc
            if diagnostic and self.capabilities.status=='reported' and self.capabilities.binary_identity[:4]==binary_stamp[:4]:
                self.capabilities=replace(self.capabilities,binary_identity=binary_stamp)
            # A valid preflight is not a lease on a time-sensitive capture.
            # Publish only while the completed request is still eligible.
            for product in view.uses_astronomy():
                available,reason=self.astronomy_for(view)[product].availability(target=view.target,time_mode=view.time_mode,utc=view.utc)
                if not available:raise ValueError('Astronomy became unavailable during rendering: '+reason)
            snapshot=PreviewSnapshot(output,view,binary,view.render_digest(),datetime.now(timezone.utc).isoformat(timespec='seconds'),detail,
                                     self.capture_for(view).provenance if view.uses_capture() else None,
                                     self.observations_for(view).provenance if view.uses_observations() else None,binary_identity=binary_stamp,image_identity=identity(output),astronomy_provenance=tuple((product,self.astronomy_for(view)[product].provenance) for product in view.uses_astronomy()))
            obsolete=self.previous.path.parent if self.previous else None
            self.previous,self.latest=self.latest,snapshot;self.last_outcome,self.last_error='succeeded',None
            return output
        except asyncio.CancelledError:
            self.last_outcome,self.last_error='cancelled','Preview cancelled.';raise
        except (ValueError,OSError,asyncio.TimeoutError) as exc:
            note=' Last successful preview retained.' if self.latest else ' No successful preview is available yet.'
            message=f'Preview exceeded {timeout:g} seconds and was stopped. Reduce scene complexity or check the renderer.' if isinstance(exc,asyncio.TimeoutError) else str(exc)
            self.last_outcome,self.last_error='failed',message+note
            raise ValueError(self.last_error) from exc
        finally:
            if diagnostic and binary is not None and output is not None:
                self.last_resources=resource_evidence(binary,view,log,output,self.last_outcome,code)
            self.busy=False;self.operation=None
            kept={record.path.parent for record in (self.latest,self.previous) if record}
            for directory in (work,obsolete):
                if directory is not None and directory not in kept and directory.parent==self.root:shutil.rmtree(directory,ignore_errors=True)

    async def file_operation(self,function,*args,**kwargs):
        if self.busy:raise ValueError('Wait for the current operation or cancel it first.')
        self.busy=True;self.operation='files'
        try:return await self.owned_io.run(function,*args,**kwargs)
        finally:self.busy=False;self.operation=None

    async def stop(self):
        await self.owned_io.stop()
        if self.comparison_workspace is not None:await self.comparison_workspace.stop()
        while self.stopping is not None:
            task=self.stopping
            try:await asyncio.shield(task)
            finally:
                if task.done() and self.stopping is task:self.stopping=None
        process=self.process
        if process is None:return
        task=asyncio.create_task(self._stop_owned(process));self.stopping=task
        try:await asyncio.shield(task)
        finally:
            if task.done() and self.stopping is task:self.stopping=None

    def _kill_process(self,process):
        if self.hard_killed is process:return
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        self.hard_killed=process

    def kill_owned(self):
        if self.comparison_workspace is not None:self.comparison_workspace.kill_owned()
        if self.process is not None:self._kill_process(self.process)

    async def _stop_owned(self,process):
        if self.hard_killed is not process:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:self.hard_killed=process
        try:await asyncio.wait_for(process.wait(),2)
        except asyncio.TimeoutError:pass
        finally:
            self._kill_process(process)
            await process.wait()
            if self.process is process:self.process=None

    async def aclose(self):
        await self.stop()
        self.close()

    def close(self):
        self.owned_io.close()
        if self.comparison_workspace is not None:self.comparison_workspace.close()
        self.kill_owned()
        self.temporary.cleanup()


def save_view(destination, view, renderer, *, config_bytes=None, capture=None, observations=None,astronomy=None):
    """Create a new native config pair, never replace any existing destination."""
    require_valid(configuration_issues(view, renderer, config_bytes, capture,observations,astronomy=astronomy))
    binary = renderer_path(renderer)
    files={**view.auxiliary_files(), **(capture.files() if view.capture_id else {}),**(observations.files() if observations else {})}
    for frozen in (astronomy or {}).values():files.update(frozen.files())
    return new_directory(destination,[('xp.conf',view.body()),('xp.def',view.definition(binary).encode()),*files.items()])


def read_bounded(fd,bound):
    chunks=[];remaining=bound+1
    while remaining:
        io_checkpoint()
        chunk=os.read(fd,min(65536,remaining))
        if not chunk:break
        chunks.append(chunk);remaining-=len(chunk)
    return b''.join(chunks)


def saved_limit(name,prefix):
    short=name[len(prefix):] if prefix and name.startswith(prefix) else name
    if ASTRONOMY_ICON_NAME.fullmatch(short):return ASTRONOMY_ICON_LIMIT
    if short in {row[1] for row in ANNOTATIONS.values()}:return ANNOTATION_LIMIT
    if short==ORIGIN_FILE:return 256
    if short==IMAGE_FILE:return IMAGE_LIMIT
    if short==META_FILE:return META_LIMIT
    if short==OBS_META:return 16384
    for product,names in ASTRONOMY_FILES.items():
        if short==f'frozen-{product}.json':return ASTRONOMY_META_LIMIT
        if short in names:return ASTRONOMY_LIMIT
    for product in OBS_PRODUCTS:
        if short=='observed-'+product+'.png':return ICON_LIMIT
        if short in ('observed-'+product+'.markers','observed-'+product+'.arcs'):return TEXT_LIMIT
    return 16384


def open_view(source):
    """Read a bounded, stable pair of real files without following file links."""
    selected = Path(source).expanduser()
    named=not selected.is_dir() and selected.suffix.lower() in {'.conf','.def'}
    prefix=scene_prefix(selected.stem+'.') if named else ''
    directory=selected.parent if named else selected
    def_name=selected.stem+'.def' if named else 'xp.def'
    conf_name=selected.stem+'.conf' if named else 'xp.conf'
    marker='.saving-'+selected.stem.casefold() if named else None
    try:
        valid = (directory.is_absolute() and bool(directory.name) and directory == directory.resolve() and
                 directory.is_dir() and not any(c in str(directory) for c in '\r\n\0'))
    except (OSError, RuntimeError):
        valid = False
    if not valid:
        raise ValueError('Choose an absolute saved-view directory without symlink components.')
    limit = 16384
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    opened = []
    try:
        contents={}
        if marker is not None:
            try:os.stat(marker,dir_fd=directory_fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise ValueError('This named scene has an unfinished or active save; preserve it and choose another scene.')
        names=[def_name,conf_name]
        for name in names:
            fd=os.open(name,os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,dir_fd=directory_fd)
            before=os.fstat(fd);opened.append((name,fd,before))
            if named and name==selected.stem+selected.suffix.lower():
                chosen=os.stat(selected.name,dir_fd=directory_fd,follow_symlinks=False)
                if (chosen.st_dev,chosen.st_ino)!=(before.st_dev,before.st_ino):raise ValueError('Selected file differs from the canonical saved pair; choose its exact .conf/.def path.')
            bound=saved_limit(name,prefix)
            if not stat.S_ISREG(before.st_mode) or before.st_size>bound:
                raise ValueError(f'Saved-view inputs must be regular files of at most {bound//1024} KiB each.')
            contents[name]=read_bounded(fd,bound)
            if len(contents[name])>bound:raise ValueError('Saved-view input exceeded its size limit.')
            if name==def_name and contents[name].startswith(tuple((header+'\n').encode() for header,version in SCENE_HEADERS.items() if version>=4)):
                lines=contents[name].split(b'\n')
                if contents[name].startswith(tuple((header+'\n').encode() for header,version in SCENE_HEADERS.items() if version>=15)) and f'XPLANET_ORIGIN_FILE={prefix}{ORIGIN_FILE}'.encode() in lines:names.append(prefix+ORIGIN_FILE)
                if contents[name].startswith(tuple((header+'\n').encode() for header,version in SCENE_HEADERS.items() if version>=17)):
                    for key,(_,filename,_,_) in ANNOTATIONS.items():
                        if f'XPLANET_{key.upper()}_FILE={prefix}{filename}'.encode() in lines:names.append(prefix+filename)
                for field,filename in (('XPLANET_PLACES_FILE',PLACE_FILE),('XPLANET_ROUTES_FILE',ROUTE_FILE)):
                    if f'{field}={prefix}{filename}'.encode() in lines:names.append(prefix+filename)
                if contents[name].startswith(tuple((header+'\n').encode() for header,version in SCENE_HEADERS.items() if version>=6)) and any(re.fullmatch(b'XPLANET_CLOUD_CAPTURE=[0-9a-f]{64}',line) for line in lines):
                    names.extend((prefix+IMAGE_FILE,prefix+META_FILE))
                if contents[name].startswith(tuple((header+'\n').encode() for header,version in SCENE_HEADERS.items() if version>=10)) and any(re.fullmatch(b'XPLANET_OBSERVATIONS=[0-9a-f]{64}',line) for line in lines):names.append(prefix+OBS_META)
            if name==def_name and contents[name].startswith(tuple((header+'\n').encode() for header,version in SCENE_HEADERS.items() if version>=16)):
                for product,files in ASTRONOMY_FILES.items():
                    if any(re.fullmatch(('XPLANET_'+product.upper()+'_CAPTURE=[0-9a-f]{64}').encode(),line) for line in contents[name].split(b'\n')):names.append(prefix+f'frozen-{product}.json')
            if name in tuple(prefix+f'frozen-{product}.json' for product in ASTRONOMY_FILES):names.extend(prefix+item for item in astronomy_payload_names(contents[name]))
            if name==prefix+OBS_META:names.extend(prefix+item for item in payload_names(contents[name]))
        for name, fd, before in opened:
            expected = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            for after in (os.fstat(fd), os.stat(name, dir_fd=directory_fd, follow_symlinks=False)):
                actual = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                if actual != expected:
                    raise ValueError('Saved-view files changed while opening. Try again.')
        if marker is not None:
            try:os.stat(marker,dir_fd=directory_fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise ValueError('Named scene changed during a save; retry after it completes.')
        same_directory(directory,directory_fd)
        return replace(parse_saved_view(contents[def_name],contents[conf_name],
                                        places=contents.get(prefix+PLACE_FILE),routes=contents.get(prefix+ROUTE_FILE),
                                        annotations={key:contents[prefix+row[1]] for key,row in ANNOTATIONS.items() if prefix+row[1] in contents},
                                        capture=FrozenCloud(contents[prefix+IMAGE_FILE],contents[prefix+META_FILE]) if prefix+IMAGE_FILE in contents else None,
                                        observations=FrozenObservations.from_files(contents,prefix) if prefix+OBS_META in contents else None,
                                        origin=contents.get(prefix+ORIGIN_FILE),asset_prefix=prefix,astronomy=tuple(FrozenAstronomy.from_files(contents,product,prefix) for product in ASTRONOMY_FILES if prefix+f'frozen-{product}.json' in contents)),source=selected if named else directory,named_source=named,native_files=tuple(contents.items()))
    finally:
        for _, fd, _ in opened:
            os.close(fd)
        os.close(directory_fd)
