"""Bounded, attempt-specific binary and renderer lookup evidence, never guesses."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
import hashlib,os,re,stat,sys
from .model import Issue

LOG_LIMIT=32768


def file_identity(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def identity(path):return file_identity(Path(path).stat())


def binary_signature(path):
    """Bounded stable bytes; distinguish metadata-only changes from a new build."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);limit=512*1024*1024
        if not stat.S_ISREG(before.st_mode) or before.st_size>limit:raise ValueError('Choose a readable regular renderer of at most 512 MiB.')
        sha=hashlib.sha256();count=0
        while chunk:=os.read(fd,65536):
            count+=len(chunk)
            if count>limit:raise ValueError('Renderer exceeds the 512 MiB identity bound.')
            sha.update(chunk)
        after=os.fstat(fd)
        if count!=before.st_size or file_identity(before)!=file_identity(after) or identity(path)!=file_identity(after):raise ValueError('Renderer changed while checking its bytes; retry with a stable executable.')
        return file_identity(after),sha.digest()
    finally:os.close(fd)


def verified_identity(path,before,digest):
    after=identity(path)
    if after==before:return after
    if after[:4]==before[:4]:
        checked,current=binary_signature(path)
        if checked[:4]==before[:4] and current==digest:return checked
    raise ValueError('Renderer identity or executable bytes changed.')


class BoundedLog:
    """Drain child output without an unbounded memory buffer or log file."""
    def __init__(self):self.head=bytearray();self.tail=bytearray();self.size=0
    def feed(self,chunk):
        self.size+=len(chunk)
        room=LOG_LIMIT//2-len(self.head)
        if room>0:self.head.extend(chunk[:room])
        self.tail.extend(chunk)
        if len(self.tail)>LOG_LIMIT//2:del self.tail[:-LOG_LIMIT//2]
    def ending(self,limit=8192):return bytes(self.tail[-limit:]).decode('utf-8','replace').strip()
    def excerpt(self):
        if self.size<=LOG_LIMIT//2:raw=bytes(self.head)
        elif self.size<=LOG_LIMIT:raw=bytes(self.head)+bytes(self.tail[-(self.size-LOG_LIMIT//2):])
        else:raw=bytes(self.head).rsplit(b'\n',1)[0]+b'\n[... diagnostic log middle omitted ...]\n'+bytes(self.tail).partition(b'\n')[2]
        return raw.decode('utf-8','replace'),self.size,self.size>LOG_LIMIT


def excerpt(stream):
    if isinstance(stream,BoundedLog):return stream.excerpt()
    stream.seek(0,os.SEEK_END);size=stream.tell();stream.seek(0)
    if size<=LOG_LIMIT:return stream.read().decode('utf-8','replace'),size,False
    head=stream.read(LOG_LIMIT//2);stream.seek(-LOG_LIMIT//2,os.SEEK_END);tail=stream.read()
    # Do not interpret partial boundary lines as complete lookup evidence.
    head=head.rsplit(b'\n',1)[0];tail=tail.partition(b'\n')[2]
    return head.decode('utf-8','replace')+'\n[... diagnostic log middle omitted ...]\n'+tail.decode('utf-8','replace'),size,True


def safe(text):return '\n'.join(''.join(c if c.isprintable() else ascii(c)[1:-1] for c in line) for line in str(text).split('\n'))


@dataclass(frozen=True)
class Capabilities:
    renderer:Path
    binary_identity:tuple
    status:str
    features:tuple
    raw:str
    log_bytes:int
    completed_utc:str
    exit_code:int|None=None
    truncated:bool=False

    def matches(self,renderer):
        try:return Path(renderer).expanduser().resolve()==self.renderer and identity(self.renderer)==self.binary_identity
        except (OSError,ValueError,RuntimeError):return False

    def sections(self):
        return [safe('Binary capability probe: '+self.status+'\nExecutable: '+str(self.renderer)+'\nUTC: '+self.completed_utc+'\nRecorded file identity (device, inode, bytes, mtime_ns, ctime_ns): '+str(self.binary_identity)),
                'Self-reported compiled support: '+(safe(', '.join(self.features)) if self.status=='reported' else 'unknown; an inconclusive/failed probe does not establish missing support.'),
                'This does not recover the original configure/compiler flags, package receipt, kernel coverage or runtime resource availability. Static libraries may not appear in a linked-library listing.',
                f'Probe exit: {self.exit_code}; bytes: {self.log_bytes}; truncated: {self.truncated}.\nRaw version evidence (bounded):\n'+safe(self.raw)]


def capabilities(binary,stamp,stream,code,*,expected_hash=None):
    raw,size,truncated=excerpt(stream);features=();status='unknown'
    lines=raw.splitlines()
    if code==0 and not truncated and lines and re.fullmatch(r'Xplanet [0-9]+(?:\.[0-9]+)+(?:[^\r\n]*)',lines[0]):
        try:index=lines.index('Compiled with support for:')
        except ValueError:pass
        else:
            rows=lines[index+1:]
            if all(not row or row.startswith('\t') and len(row)<=200 and all(c.isprintable() for c in row[1:]) for row in rows):
                features=tuple(row.strip() for row in rows if row.strip());status='reported'
    if code!=0:status='runtime/probe failure (support unknown)'
    if truncated:status='truncated report (support unknown)'
    try:
        if expected_hash is not None:stamp=verified_identity(binary,stamp,expected_hash)
        elif identity(binary)!=stamp:status='binary changed during probe (support unknown)'
    except ValueError:status='binary changed during probe (support unknown)'
    except OSError:status='binary unavailable after probe (support unknown)'
    return Capabilities(Path(binary),stamp,status,features,raw,size,datetime.now(timezone.utc).isoformat(timespec='seconds'),code,truncated)


def capability_issues(report,view,renderer):
    if report is None:return [Issue('info','renderer','Compiled capabilities have not been checked. Diagnose resources explicitly probes this executable; opening health does not execute it.')]
    if not report.matches(renderer):return [Issue('info','renderer','Previous binary evidence is stale or belongs to another executable. Run Diagnose resources for the current choice.')]
    if report.status!='reported':return [Issue('warning','renderer','Binary capabilities remain unknown: '+report.status+'. Inspect the raw probe evidence; do not assume a configuration error or missing build feature.')]
    required={'PNG'}
    paths=[str(path).lower() for path in view.resource_paths()]
    if view.target=='earth' and (view.map_family=='stock' or view.night=='stock'):required.add('JPEG')
    if any(path.endswith(('.jpg','.jpeg')) for path in paths) or view.uses_capture():required.add('JPEG')
    if any(path.endswith(('.tif','.tiff')) for path in paths):required.add('TIFF')
    result=[Issue('info','renderer','Binary reports compiled support: '+(', '.join(report.features) or 'no listed optional features')+'. Compiled support does not certify every runtime feature or data file.')]
    if sys.platform=='darwin' and 'Mac OS X' not in report.features:
        result.append(Issue('warning','renderer','Native Mac OS X display support is not reported. Finite PNG previews may work, but native desktop display may require a compatible build; no desktop probe was performed.'))
    for feature in sorted(required-set(report.features)):
        result.append(Issue('blocking','renderer',f'This Xplanet binary reports no {feature} support; this scene/output requires it. Select a compatible build or consult its build instructions. Scene settings cannot enable a missing compiled feature.'))
    return result


@dataclass(frozen=True)
class ResourceEvidence:
    renderer:Path
    view_digest:str
    summary:str
    outcome:str
    exit_code:int|None
    raw:str
    log_bytes:int
    truncated:bool
    lookups:tuple
    png_signature:bool
    dimensions:tuple|None

    def sections(self):
        found=tuple(dict.fromkeys(path for path,success in self.lookups if success))
        misses=sum(not success for _,success in self.lookups)
        return [safe('Diagnostic attempt: '+self.outcome+'; renderer exit '+str(self.exit_code)+'\n'+self.summary+'\nExecutable: '+str(self.renderer)),
                'PNG signature observed: '+str(self.png_signature)+'; IHDR dimensions: '+(str(self.dimensions) if self.dimensions else 'unavailable')+'. This is not a full image-decoding or build certification.',
                'Renderer-reported found paths (not independent proof of decoding):\n'+('\n'.join(safe(path) for path in found) if found else 'No recognized successful lookup rows; resolution remains unknown.'),
                f'Recognized not-found search attempts in the retained excerpt: {misses}. A search miss before a later successful lookup is normal, not a source failure.',
                f'Lookup rows are limited to 128; this is not a complete resource inventory. Log bytes: {self.log_bytes}; excerpt truncated: {self.truncated}. Evidence is from this attempt, not a live watcher or a guarantee about another scene/binary.',
                'Raw renderer evidence (bounded, controls escaped):\n'+safe(self.raw)]


def resource_evidence(binary,view,stream,output,outcome,code):
    raw,size,truncated=excerpt(stream);rows=[]
    for line in raw.splitlines():
        match=re.fullmatch(r'Looking for (.{1,4096}) \.\.\. (found|not found)',line)
        if match and len(rows)<128:rows.append((match[1],match[2]=='found'))
    signature=False;dimensions=None
    try:
        with Path(output).open('rb') as image:header=image.read(24)
        signature=header[:8]==b'\x89PNG\r\n\x1a\n'
        if signature and len(header)>=24 and header[12:16]==b'IHDR':
            import struct
            dimensions=struct.unpack('>II',header[16:24])
    except OSError:pass
    return ResourceEvidence(Path(binary),view.render_digest(),view.summary(),outcome,code,raw,size,truncated,tuple(rows),signature,dimensions)
