"""Bounded literal value edits; all other native bytes remain opaque and intact."""
from dataclasses import dataclass,field
from pathlib import Path
import hashlib,math,os,re,stat
from .model import NUMERIC_FIELDS,TARGETS
from .fileio import fingerprint,OwnedFiles
from .owned_io import checkpoint
from .workspace import read_bounded

LIMIT=256*1024
LINE_LIMIT=240
FIELDS={
 'grid':('boolean',False,'Literal true/false grid switch; inherited settings are not inferred.'),
 'map':('path',False,'Literal day-map filename; asset existence and search paths are not checked.'),
 'night_map':('path',False,'Literal night-map filename; no asset is opened or certified.'),
 'cloud_map':('path',False,'Literal cloud-map filename; no download or freshness claim.'),
 'shade':('planet_shade',True,'Shadow fallback without night imagery; not night-map brightness.'),
 'twilight':('twilight',True,'Whole-degree day/night blending width.'),
 'bump_scale':('relief_scale',False,'Shading exaggeration; has no effect without an existing bump map.'),
 'grid1':((1,90),True,'Major divisions per 90° (spacing = 90/grid1); only when a grid is active.'),
 'grid2':((1,90),True,'Subdivisions per major interval; only when a grid is active. Inherited values are not inferred.'),
 'cloud_gamma':('cloud_gamma',False,'Cloud brightness gamma; no cloud map is enabled or inferred.'),
 'cloud_threshold':('cloud_threshold',True,'Hide cloud pixels below this 0–255 threshold; requires an existing cloud map.'),
 'magnify':('satellite_scale',False,'Illustrative visual enlargement 1–10; does not hide a body or certify physical scale.'),
}
HEADER=re.compile(rb'[ \t]*\[([A-Za-z0-9_.-]{1,64})\][ \t]*(?:#.*)?')
NUMBER=rb'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'


def parse_value(key,text):
    model,integer,_=FIELDS[key]
    if model=='boolean':
        if text not in ('true','false'):raise ValueError('Use the literal true or false.')
        return text
    if model=='path':
        if len(text)>180 or not re.fullmatch(r'(?:/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',text) or text in ('.','..'):
            raise ValueError('Use a simple literal filename/path (up to 180 characters; ASCII letters, digits, dot, underscore, hyphen and slash only).')
        return text
    if len(text)>64:raise ValueError('Numeric literal exceeds 64 characters.')
    raw=text.encode('ascii')
    if not re.fullmatch(rb'[+-]?[0-9]+' if integer else NUMBER,raw):raise ValueError(key+': use a literal '+('whole number.' if integer else 'number.'))
    value=float(text);low,high=model if isinstance(model,tuple) else NUMERIC_FIELDS[model][1:]
    if not math.isfinite(value) or not low<=value<=high:raise ValueError(f'{key}: supported range is {low:g}–{high:g}.')
    return int(value) if integer else value


@dataclass(frozen=True)
class Slot:
    section:str
    key:str
    literal:str=''
    start:int|None=None
    end:int|None=None
    reason:str=''


@dataclass(frozen=True)
class Patch:
    data:bytes=field(repr=False)
    changes:tuple=()
    edits:tuple=field(default=(),repr=False)
    spans:tuple=field(default=(),repr=False)


@dataclass(frozen=True)
class NativePatch:
    source:Path
    original:bytes=field(repr=False)
    source_identity:tuple=field(repr=False)
    directory_identity:tuple=field(repr=False)
    slots:tuple=()
    insertions:tuple=()

    @classmethod
    def load(cls,source):
        path=Path(source).expanduser()
        if not path.is_absolute() or path.suffix!='.conf' or any(not c.isprintable() for c in str(path)):raise ValueError('Choose an absolute native .conf file.')
        parent=path.parent
        if parent!=parent.resolve() or not parent.is_dir():raise ValueError('Native values require a source directory without symlink components.')
        directory=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);child=None
        try:
            child=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory);before=os.fstat(child)
            if not stat.S_ISREG(before.st_mode) or before.st_size>LIMIT:raise ValueError('Native value editing requires a regular file up to 256 KiB.')
            raw=read_bounded(child,LIMIT)
            if len(raw)>LIMIT:raise ValueError('Native file exceeds 256 KiB.')
            if any(fingerprint(item)!=fingerprint(before) for item in (os.fstat(child),os.stat(path.name,dir_fd=directory,follow_symlinks=False))):raise ValueError('Source changed during reading; reopen it.')
            slots,insertions=parse(raw)
            info=os.fstat(directory)
            return cls(path,raw,fingerprint(before),(info.st_dev,info.st_ino),slots,insertions)
        finally:
            if child is not None:os.close(child)
            os.close(directory)

    @property
    def sections(self):return tuple(dict.fromkeys(slot.section for slot in self.slots))

    def initial_values(self):return {section:{slot.key:slot.literal for slot in self.slots if slot.section==section} for section in self.sections}

    def prepare(self,edits):
        if not isinstance(edits,dict) or not set(edits)<=set(self.sections):raise ValueError('Unknown native section.')
        replacements=[];inserted={};changes=[]
        for section,values in edits.items():
            if not isinstance(values,dict) or not set(values)<=set(FIELDS):raise ValueError('Unknown native field.')
            for key,text in values.items():
                slot=next(s for s in self.slots if s.section==section and s.key==key)
                if not isinstance(text,str):raise ValueError('Native fields must be text.')
                if not text:continue  # Blank means leave original; deletion is not offered.
                if slot.reason:
                    if text!=slot.literal:raise ValueError(f'{section}/{key}: {slot.reason}')
                    continue
                try:value=parse_value(key,text)
                except (UnicodeError,ValueError,OverflowError) as exc:raise ValueError(f'{section}/{key}: {exc}') from None
                if slot.literal and value==parse_value(key,slot.literal):continue  # Preserve no-op spelling too.
                token=(value if isinstance(value,str) else str(value) if isinstance(value,int) else repr(value)).encode()
                if slot.start is not None:replacements.append((slot.start,slot.end,token))
                else:inserted.setdefault(section,[]).append(key.encode()+b'='+token)
                changes.append(f'[{section}] {key}: {slot.literal or "not explicitly set (inherited value unknown)"} → {token.decode()}')
        positions={name:(offset,newline) for name,offset,newline in self.insertions}
        for section,lines in inserted.items():
            offset,newline=positions[section];separator=b'' if offset==0 or self.original[offset-1:offset]==b'\n' else newline
            replacements.append((offset,offset,separator+newline.join(lines)+newline))
        raw=self.original
        for start,end,value in sorted(replacements,reverse=True):raw=raw[:start]+value+raw[end:]
        if len(raw)>LIMIT or any(len(line.rstrip(b'\r\n'))>LINE_LIMIT for line in raw.splitlines(keepends=True)):raise ValueError('Edited copy exceeds the safe native file/line bounds.')
        return Patch(raw,tuple(changes),tuple((section,tuple(values.items())) for section,values in edits.items()),tuple(sorted(replacements)))

    def verify_proposal(self,proposal):
        if not isinstance(proposal,Patch):raise ValueError('Review a prepared native copy first.')
        verified=self.prepare({section:dict(values) for section,values in proposal.edits})
        if verified!=proposal:raise ValueError('Copy proposal does not match the reviewed source edits.')
        return verified

    def review(self,proposal):
        """Bounded byte-edit evidence from the snapshot, not a generic text diff."""
        proposal=self.verify_proposal(proposal)
        lines=[f'Source snapshot: {len(self.original)} bytes; SHA-256 {hashlib.sha256(self.original).hexdigest()}',
               f'Proposed copy: {len(proposal.data)} bytes; SHA-256 {hashlib.sha256(proposal.data).hexdigest()}']
        if not proposal.spans:
            lines.append('No byte changes: exact original spelling, comments and line endings retained.')
            return tuple(lines)
        lines.append('Byte edits below use zero-based [start:end) source offsets and one-based source lines. Escaped bytes show line endings literally; an empty before span means insertion.')
        for start,end,replacement in proposal.spans[:32]:
            line=self.original.count(b'\n',0,start)+1
            lines.extend((f'Source line {line}, bytes [{start}:{end}):',
                          '  before: '+repr(self.original[start:end]),'  after:  '+repr(replacement)))
        if len(proposal.spans)>32:lines.append(f'Display limited to 32 of {len(proposal.spans)} byte edits; the copy hash covers the entire proposed file. No edits are omitted from the copy.')
        lines.append('All source ranges outside the complete prepared edit set remain byte-for-byte unchanged. These hashes describe snapshots, not an asset/dependency certification; source identity is rechecked at save.')
        return tuple(lines)

    def save_copy(self,destination,proposal):
        self.verify_proposal(proposal)
        target=Path(destination).expanduser()
        if not target.is_absolute() or target.suffix!='.conf' or target.parent!=self.source.parent or any(not c.isprintable() for c in str(target)):raise ValueError('Choose a NEW .conf in the same source directory; assets are not moved.')
        if self.source.parent!=self.source.parent.resolve():raise ValueError('Source directory now has symlink components; reopen it.')
        directory=os.open(self.source.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);child=None;owned=OwnedFiles(directory)
        try:
            info=os.fstat(directory)
            if (info.st_dev,info.st_ino)!=self.directory_identity:raise ValueError('Source directory changed; reopen the source.')
            child=os.open(self.source.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
            self._check_source(directory,child)
            if read_bounded(child,LIMIT)!=self.original:raise ValueError('Source bytes changed; reopen before editing.')
            with os.scandir(directory) as listing:
                for count,entry in enumerate(listing,1):
                    checkpoint()
                    if count>10000:raise ValueError('Source directory exceeds the review bound.')
                    if entry.name.casefold() in (target.name.casefold(),target.with_suffix('.def').name.casefold()):raise ValueError('Destination or matching definition already exists (including case aliases); choose another stem.')
            # Compare path identity too: do not publish into a substituted directory.
            current=os.stat(self.source.parent,follow_symlinks=False)
            if (current.st_dev,current.st_ino)!=self.directory_identity:raise ValueError('Source directory moved; reopen it.')
            owned.write(target.name,proposal.data)
            self._check_source(directory,child)
            current=os.stat(self.source.parent,follow_symlinks=False)
            if (current.st_dev,current.st_ino)!=self.directory_identity:raise ValueError('Source directory moved during saving; reopen it.')
            os.fsync(directory)
            return target
        except BaseException:
            owned.cleanup();raise
        finally:
            if child is not None:os.close(child)
            os.close(directory)

    def _check_source(self,directory,child):
        if any(fingerprint(item)!=self.source_identity for item in (os.fstat(child),os.stat(self.source.name,dir_fd=directory,follow_symlinks=False))):raise ValueError('Source changed since opening; reopen it. Nothing was overwritten.')


def parse(raw):
    if any(byte<32 and byte not in (9,10,13) or byte==127 for byte in raw) or b'\r' in raw.replace(b'\r\n',b''):raise ValueError('Control characters or bare CR make native scope ambiguous; inspect read-only instead.')
    offset=0;sections=[];current=None
    for line in raw.splitlines(keepends=True):
        content=line.rstrip(b'\r\n')
        if len(content)>LINE_LIMIT:raise ValueError('A native line exceeds 240 bytes; inspect read-only instead.')
        if content.rstrip().endswith(b'\\'):raise ValueError('Line continuation/escape scope is unsupported; inspect read-only instead.')
        stripped=content.lstrip(b' \t')
        if stripped and not stripped.startswith(b'#'):
            match=HEADER.fullmatch(content)
            if match:
                current={'name':match[1].decode(),'start':offset,'insert':offset+len(line),'newline':b'\r\n' if line.endswith(b'\r\n') else b'\n','rows':[]}
                sections.append(current)
            else:
                if b'[' in content or b']' in content:raise ValueError('Inline or unclear section boundaries are unsupported; inspect read-only instead.')
                if current is None:raise ValueError('Native settings before a literal body section are ambiguous.')
                current['rows'].append((offset,content));current['insert']=offset+len(line)
        offset+=len(line)
    counts={}
    for section in sections:counts[section['name'].casefold()]=counts.get(section['name'].casefold(),0)+1
    if any(count>1 and name in (*TARGETS,'default') for name,count in counts.items()):raise ValueError('Repeated body sections are ambiguous; inspect read-only instead.')
    slots=[];insertions=[]
    for section in sections:
        name=section['name']
        if name not in (*TARGETS,'default') or counts[name.casefold()]!=1:continue
        available=[]
        for key,(kind,integer,_) in FIELDS.items():
            occurrences=[(start,content) for start,content in section['rows'] for _ in re.finditer(rb'(?i)(?<![A-Za-z0-9_])'+key.encode()+rb'[ \t]*=',content)]
            literal='';begin=end=None;reason=''
            if not occurrences:pass
            elif len(occurrences)!=1:reason='Repeated or ambiguous assignments are preserved, not edited.'
            else:
                start,content=occurrences[0]
                token=rb'(?:true|false)' if kind=='boolean' else rb'[^ \t#]+' if kind=='path' else rb'[+-]?[0-9]+' if integer else NUMBER
                match=re.fullmatch(rb'([ \t]*'+key.encode()+rb'=)('+token+rb')([ \t]*(?:#.*)?)',content)
                if match:
                    begin=start+match.start(2);end=start+match.end(2)
                    try:
                        literal=match[2].decode('ascii');parse_value(key,literal)
                    except (ValueError,OverflowError,UnicodeError):reason='Existing literal is outside this tool\'s literal syntax or bounds.'
                else:reason='Mixed, spaced, non-literal or unsupported assignment syntax is preserved.'
            available.append(Slot(name,key,literal,begin,end,reason))
        if any(not slot.reason for slot in available):slots.extend(available);insertions.append((name,section['insert'],section['newline']))
    if not slots:raise ValueError('No unique supported literal body section is available; inspect read-only instead.')
    return tuple(slots),tuple(insertions)
