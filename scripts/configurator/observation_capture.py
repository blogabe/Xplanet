"""Frozen, validated existing TotalMarker observations; no producer or source writes."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
import hashlib,json,math,os,re,shlex,struct,time,zlib
from pathlib import Path

from totalmarker.config import load_bytes
from totalmarker.diagnostics import observation
from totalmarker.errors import TotalMarkerError
from totalmarker.paths import RootFS
from totalmarker.health import observational_freshness
from .cloud_capture import CaptureError,CaptureRace,read_stable,read_state,publication_pending,json_bytes,OUTCOMES

PRODUCTS=('quake','volcano','storm')
OBS_OUTCOMES=(*OUTCOMES,'changed')
META_FILE='observations.json'
TEXT_LIMIT=256*1024
ICON_LIMIT=1024*1024
META_LIMIT=16384
FACT_KEYS={'checked_at','attempted_at','successful_at','published_at','source_at','source_valid_until_at','coverage_end_at','feed_generated_at','latest_origin_at','latest_revision_at','source_report_at','last_outcome','source_marker_sha256','source_arc_sha256','report_period_start','report_period_end'}
SHA=re.compile(r'[0-9a-f]{64}')
NUM=r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
MARKER=re.compile(rf'\s*({NUM})\s+({NUM})\s+("(?:[^"\\]|\\["\\])*")(.*)')
TOKEN=re.compile(r'[A-Za-z][A-Za-z0-9]{0,39}|#[0-9a-fA-F]{6}|[0-9]{1,3},[0-9]{1,3},[0-9]{1,3}')


def names(product):
    if product not in PRODUCTS:raise CaptureError('Unsupported observational product.')
    return f'observed-{product}.markers',f'observed-{product}.arcs',f'observed-{product}.png'


def payload_names(raw):
    """Validate the bounded manifest before opening only fixed allowlisted names."""
    try:
        if len(raw)>META_LIMIT:raise ValueError
        meta=json.loads(raw)
        if not isinstance(meta,dict) or set(meta)!={'schema','captured_at','products','files'} or type(meta['schema']) is not int or meta['schema']!=1 or json_bytes(meta)!=raw:raise ValueError
        stamp(meta['captured_at'],nullable=False)
        if not isinstance(meta['products'],dict) or not meta['products'] or not set(meta['products'])<=set(PRODUCTS):raise ValueError
        allowed=set()
        for product,facts in meta['products'].items():
            if not isinstance(facts,dict) or set(facts)!=FACT_KEYS:raise ValueError
            for key in FACT_KEYS-{'last_outcome','source_marker_sha256','source_arc_sha256','report_period_start','report_period_end'}:stamp(facts[key])
            if facts['last_outcome'] not in OBS_OUTCOMES:raise ValueError
            for key in ('source_marker_sha256','source_arc_sha256'):
                if facts[key] is not None and (not isinstance(facts[key],str) or not SHA.fullmatch(facts[key])):raise ValueError
            if facts['source_marker_sha256'] is None or (product=='storm')!=(facts['source_arc_sha256'] is not None):raise ValueError
            for key in ('report_period_start','report_period_end'):
                value=facts[key]
                if value is not None:
                    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):raise ValueError
                    datetime.strptime(value,'%Y-%m-%d')
            marker,arc,icon=names(product);allowed|={marker,icon}
            if product=='storm':allowed.add(arc)
        files=meta['files']
        if not isinstance(files,dict) or not set(files)<=allowed:raise ValueError
        for product in meta['products']:
            marker,arc,_=names(product)
            if marker not in files or (product=='storm' and arc not in files):raise ValueError
        if any(not isinstance(v,str) or not SHA.fullmatch(v) for v in files.values()):raise ValueError
        return tuple(sorted(files))
    except (ValueError,TypeError,KeyError,RecursionError,OverflowError):
        raise CaptureError('Invalid frozen observation manifest.') from None


def stamp(value,nullable=True):
    if value is None and nullable:return
    if type(value) not in (float,int) or not math.isfinite(value) or not 0<=value<=32503680000:raise ValueError('Invalid observation timestamp.')


def png(data):
    """Bounded PNG container/dimensions, not full decoder certification."""
    if not isinstance(data,bytes) or not 33<=len(data)<=ICON_LIMIT or data[:8]!=b'\x89PNG\r\n\x1a\n':raise CaptureError('Observation icons must be bounded PNG files (up to 1 MiB, 512×512).')
    pos=8;seen=[]
    while pos<len(data):
        if pos+12>len(data):raise CaptureError('Truncated observation PNG.')
        length=struct.unpack('>I',data[pos:pos+4])[0];kind=data[pos+4:pos+8];end=pos+12+length
        if end>len(data) or zlib.crc32(data[pos+4:end-4])&0xffffffff!=struct.unpack('>I',data[end-4:end])[0]:raise CaptureError('Invalid observation PNG chunks.')
        if not seen:
            if kind!=b'IHDR' or length!=13:raise CaptureError('Missing observation PNG dimensions.')
            width,height=struct.unpack('>II',data[pos+8:pos+16])
            if not 0<width<=512 or not 0<height<=512:raise CaptureError('Observation icon exceeds 512×512.')
        seen.append(kind);pos=end
        if len(seen)>4096:raise CaptureError('Observation PNG has too many chunks.')
        if kind==b'IEND':
            if length or pos!=len(data) or b'IDAT' not in seen:raise CaptureError('Invalid observation PNG ending.')
            return
    raise CaptureError('Incomplete observation PNG.')


def native(data,product,arcs=False,*,source=False,icon=None):
    names(product)
    if not isinstance(data,bytes) or len(data)>TEXT_LIMIT:raise CaptureError('Keep each captured marker/arc file within 256 KiB.')
    try:text=data.decode('utf-8')
    except UnicodeError:raise CaptureError('Observation text is not UTF-8.') from None
    header=f'# Frozen TotalMarker {product} '+('arcs' if arcs else 'markers')+' v1\n'
    if source:
        kind={'quake':'Earthquake','volcano':'Volcano','storm':'Storm'}[product]
        expected=f'# This {kind} '+('great-arc' if arcs else 'marker')+' file created by TotalMarker Python\n'
        lines=text.splitlines()
        if len(lines)<3 or lines[0]+'\n'!=expected or not lines[1].startswith('# Last Updated: ') or lines[2]!='#':raise CaptureError('Only recognized TotalMarker Python output can be captured.')
        lines=lines[3:]
    else:
        if not text.startswith(header):raise CaptureError('Invalid frozen observation header.')
        lines=text[len(header):].splitlines()
    if len(lines)>4096:raise CaptureError('Keep each observation layer within 4096 native rows.')
    output=[];used=set()
    for line in lines:
        if not line.strip():continue
        if len(line.encode())>240 or any(ord(c)<32 and c!='\t' or ord(c)==127 for c in line):raise CaptureError('Observation rows must be printable and at most 240 bytes.')
        if arcs:
            tokens=line.split();coordinates=tokens[:4];tail=tokens[4:];label=None
            if len(coordinates)!=4:raise CaptureError('Invalid observed arc coordinates.')
        else:
            match=MARKER.fullmatch(line)
            if not match:raise CaptureError('Unsupported observation marker syntax.')
            coordinates=list(match.groups()[:2]);label=shlex.split(match.group(3))[0];tail=match.group(4).split()
            if len(label.encode())>160 or not label.isprintable() and label:raise CaptureError('Observation label exceeds its supported printable bound.')
        values=[]
        for index,value in enumerate(coordinates):
            if not re.fullmatch(NUM,value):raise CaptureError('Invalid observation coordinate.')
            number=float(value);bound=90 if index%2==0 else 180
            if not math.isfinite(number) or not -bound<=number<=bound:raise CaptureError('Observation coordinates are outside surface-degree bounds.')
            values.append(format(number,'.12g'))
        options={}
        for token in tail:
            if token.count('=')!=1:raise CaptureError('Unsupported observation option.')
            key,value=token.split('=',1)
            if key in options or key not in ({'color'} if arcs else {'color','symbolsize','align','image','transparent'}):raise CaptureError('Unsupported or repeated observation option.')
            if key=='image':
                if value!='none':
                    if source:
                        if icon is None or value!=icon:raise CaptureError('Observation image does not match its declared producer dependency.')
                    elif value!=names(product)[2]:raise CaptureError('Invalid frozen observation icon reference.')
                    used.add(value);value=names(product)[2]
            elif key=='symbolsize':
                try:number=float(value)
                except ValueError:raise CaptureError('Invalid observation symbol size.') from None
                if not math.isfinite(number) or not 0<=number<=512:raise CaptureError('Observation symbol size exceeds 512 pixels.')
                value=format(number,'.12g')
            elif key=='align':
                if not re.fullmatch(r'[A-Za-z]{1,20}',value) or value[0].lower() not in 'rlabc':raise CaptureError('Invalid observation alignment.')
                value={'r':'Right','l':'Left','a':'Above','b':'Below','c':'Center'}[value[0].lower()]
            elif not TOKEN.fullmatch(value) or (',' in value and any(int(part)>255 for part in value.split(','))):raise CaptureError('Invalid observation color/transparency.')
            options[key]=value
        if 'color' not in options:raise CaptureError('Observation row lacks its producer color.')
        row=' '.join(values)
        if label is not None:row+=' "'+label.replace('\\','\\\\').replace('"','\\"')+'"'
        row+=''.join(' '+key+'='+value for key,value in sorted(options.items()))
        output.append(row)
    result=(header+'\n'.join(output)+ ('\n' if output else '')).encode()
    if len(result)>TEXT_LIMIT:raise CaptureError('Normalized observations exceed their text bound.')
    return result,bool(used)


def image_prefix(data,product,prefix,inverse=False):
    if prefix and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}\.',prefix):raise CaptureError('Invalid observation scene prefix.')
    alias=names(product)[2];old,new=(prefix+alias,alias) if inverse else (alias,prefix+alias)
    lines=data.decode('utf-8').splitlines(keepends=True);result=[]
    for line in lines:
        match=MARKER.fullmatch(line.rstrip('\n'))
        if match:
            start=match.start(4)
            tail=re.sub(r'(?<!\S)image='+re.escape(old)+r'(?=\s|$)',lambda _: 'image='+new,line[start:])
            line=line[:start]+tail
        result.append(line)
    return ''.join(result).encode()


@dataclass(frozen=True)
class FrozenObservations:
    provenance:bytes=field(repr=False)
    payload:tuple=field(repr=False)

    def __post_init__(self):
        expected=payload_names(self.provenance)
        if not isinstance(self.payload,tuple):raise CaptureError('Observation payload must be an immutable tuple.')
        files=dict(self.payload)
        if len(files)!=len(self.payload) or tuple(sorted(files))!=expected:raise CaptureError('Observation assets do not match the manifest.')
        meta=self.metadata
        for name,data in files.items():
            if not isinstance(data,bytes) or hashlib.sha256(data).hexdigest()!=meta['files'][name]:raise CaptureError('Frozen observation hash mismatch.')
        for product in meta['products']:
            marker,arc,icon=names(product)
            normalized,used=native(files[marker],product)
            if normalized!=files[marker] or used!=(icon in files):raise CaptureError('Frozen marker/icon association is invalid.')
            if icon in files:png(files[icon])
            if product=='storm' and native(files[arc],product,True)[0]!=files[arc]:raise CaptureError('Invalid frozen storm arcs.')

    @property
    def metadata(self):return json.loads(self.provenance)
    @property
    def identity(self):return hashlib.sha256(self.provenance).hexdigest()
    @property
    def byte_size(self):return len(self.provenance)+sum(len(data) for _,data in self.payload)

    def files(self,prefix='',products=None):
        files={}
        selected=set(self.metadata['products']) if products is None else set(products)
        for name,data in self.payload:
            product=next(p for p in PRODUCTS if name.startswith('observed-'+p+'.'))
            if product not in selected:continue
            if name.endswith('.markers') and prefix:data=image_prefix(data,product,prefix)
            if name.endswith('.markers') and len(data)>TEXT_LIMIT:
                raise CaptureError('Observation marker exceeds 256 KiB with this scene prefix; choose a shorter name or a legacy directory save.')
            files[prefix+name]=data
        if products is None:files[prefix+META_FILE]=self.provenance
        return files

    @classmethod
    def from_files(cls,contents,prefix=''):
        raw=contents[prefix+META_FILE];files=[]
        for name in payload_names(raw):
            data=contents[prefix+name]
            if prefix and name.endswith('.markers'):
                product=next(p for p in PRODUCTS if name==names(p)[0])
                data=image_prefix(data,product,prefix,inverse=True)
            files.append((name,data))
        return cls(raw,tuple(files))

    def freshness(self,product,now=None):
        return observational_freshness(product,self.metadata['products'][product],time.time() if now is None else now)


def describe(frozen):return describe_metadata(frozen.metadata)


def describe_metadata(meta):
    def when(value):return 'unknown' if value is None else datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    lines=['Frozen observations captured '+when(meta['captured_at'])+'. Provider access was not checked.']
    for product,facts in meta['products'].items():
        lines.append(f'{product}: freshness {observational_freshness(product,facts,time.time())}; source {when(facts["source_at"])}; success {when(facts["successful_at"])}; publication {when(facts["published_at"])}; outcome {facts["last_outcome"] or "unknown"}.')
        if product=='volcano':lines.append('Reporting period '+str(facts['report_period_start'] or 'unknown')+' to '+str(facts['report_period_end'] or 'unknown')+'; coverage ends '+when(facts['coverage_end_at'])+'.')
        if product=='storm':lines.append('Source validity ends '+when(facts['source_valid_until_at'])+'; forecast arcs are captured producer output, not observations at a selected historical/future time.')
    return '\n'.join(lines)


def capture_existing(root,products,config='config/totalmarker.toml',*,now=None):
    products=tuple(products)
    if not products or len(set(products))!=len(products) or not set(products)<=set(PRODUCTS):raise CaptureError('Choose quake, volcano and/or storm capture.')
    if not Path(root).is_absolute():raise CaptureError('Choose an absolute existing TotalMarker root.')
    try:fs=RootFS(root)
    except TotalMarkerError:raise CaptureError('Choose an existing source root without symlink ancestors.') from None
    for attempt in range(2):
        try:
            raw=read_stable(fs,config,1024*1024);settings=load_bytes(fs,raw,config)
            if publication_pending(fs,settings):raise CaptureError('Pending TotalMarker publication; preserve its journal and recover through normal operation.')
            records=read_state(fs,settings.state)['products'];facts={};files={};dependencies=[]
            for product in products:
                options=getattr(settings,product);record=records.get(product,{})
                marker,arc,icon=names(product);source=read_stable(fs,options.marker,TEXT_LIMIT)
                source_hash=hashlib.sha256(source).hexdigest()
                if source_hash!=record.get('marker_sha256'):raise CaptureRace('Observation marker does not match saved publication metadata.')
                files[marker],used=native(source,product,source=True,icon=options.image or None)
                arc_hash=None
                if product=='storm':
                    data=read_stable(fs,options.arc,TEXT_LIMIT);arc_hash=hashlib.sha256(data).hexdigest()
                    if arc_hash!=record.get('arc_sha256'):raise CaptureRace('Storm marker/arc pair does not match one saved publication.')
                    files[arc]=native(data,product,True,source=True)[0]
                if used:
                    data=read_stable(fs,options.image,ICON_LIMIT);png(data);files[icon]=data;dependencies.append((options.image,data))
                common=observation(record)
                row={key:record.get(key) for key in FACT_KEYS}
                row.update({key:common[key] for key in ('checked_at','attempted_at','successful_at','published_at','source_at','last_outcome')})
                row.update(source_marker_sha256=source_hash,source_arc_sha256=arc_hash)
                facts[product]=row
            current=read_state(fs,settings.state)['products']
            if any(records.get(p)!=current.get(p) for p in products) or raw!=read_stable(fs,config,1024*1024):raise CaptureRace('Saved observation metadata changed during capture.')
            if any(data!=read_stable(fs,path,ICON_LIMIT) for path,data in dependencies):raise CaptureRace('Observation image dependency changed during capture.')
            if publication_pending(fs,settings):raise CaptureError('Publication became pending; observation capture was not accepted.')
            meta={'schema':1,'captured_at':time.time() if now is None else now,'products':facts,'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
            return FrozenObservations(json_bytes(meta),tuple(sorted(files.items())))
        except CaptureRace:
            if attempt:raise
        except TotalMarkerError:raise CaptureError('Saved observation paths/configuration/state cannot be inspected safely; nothing was changed.') from None


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Internal read-only observation capture worker')
    parser.add_argument('--root',required=True);parser.add_argument('--config',required=True)
    parser.add_argument('--products',required=True);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        target=args.output
        if not target.is_dir() or target!=target.resolve() or any(target.iterdir()):raise CaptureError('Capture output must be an empty private workspace.')
        frozen=capture_existing(args.root,args.products.split(','),args.config)
        for name,data in frozen.files().items():
            fd=os.open(target/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(data)
        return 0
    except CaptureError as exc:print(str(exc));return 1
    except Exception:print('Observation capture failed; source data was not changed.');return 1


if __name__=='__main__':raise SystemExit(main())
