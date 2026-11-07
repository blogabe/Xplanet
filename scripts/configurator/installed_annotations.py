"""Explicit bounded local annotation imports; no provider, package or source writes."""
import hashlib
import math
from pathlib import Path
import re
from .cloud_capture import read_stable
from .owned_io import checkpoint
from totalmarker.paths import RootFS
from totalmarker.errors import TotalMarkerError

# Separate coordinate domains and destinations. No arbitrary filenames/options.
DATASETS = {
    'sky_labels': ('markers/brightStars', 'sky-labels.markers', 128, 'Sky bright-star labels'),
    'sky_constellations': ('arcs/constellations', 'sky-constellations.arcs', 1024, 'Sky constellation lines'),
    'moon_sites': ('markers/moon', 'moon-sites.markers', 32, 'Moon Apollo landing sites'),
    'mars_names': ('markers/mars', 'mars-names.markers', 128, 'Mars historical surface labels'),
}
FIELDS = frozenset(DATASETS) | {key+'_text' for key in DATASETS}
LIMIT = 96 * 1024
HEADER = '# Xplanet configurator installed annotation v1\n'
NUMBER = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
MARKER = re.compile(rf'({NUMBER}),?\s+({NUMBER})\s+"([^"\\]*)"(?:\s+(image=none|color=[A-Za-z][A-Za-z0-9]{{0,39}}))?')
ARC = re.compile(rf'({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})')


def selected(view):
    return tuple(key for key in DATASETS if getattr(view,key)=='on' and
                 (view.projection=='space' if key.startswith('sky_') else view.target==('moon' if key=='moon_sites' else 'mars')))


def resource_requests(view):
    return tuple((DATASETS[key][3], DATASETS[key][1]) for key in selected(view))


def _rows(text,key):
    if not isinstance(text,str) or len(text.encode('utf-8'))>LIMIT:
        raise ValueError('Annotation input exceeds 96 KiB.')
    if any(not c.isprintable() and c not in '\n\r\t' for c in text):raise ValueError('Annotation input contains control characters.')
    lines=text.splitlines()
    if len(lines)>2048:raise ValueError('Annotation input exceeds 2048 lines.')
    rows=[];comments=[]
    for line in lines:
        checkpoint()
        if len(line.encode('utf-8'))>220 or any(not c.isprintable() and c!='\t' for c in line):
            raise ValueError('Annotation rows must be printable and at most 220 UTF-8 bytes.')
        row,separator,comment=line.partition('#')
        if separator and comment.strip():comments.append('# '+comment.strip())
        row=row.strip()
        if not row:continue
        match=(ARC if key=='sky_constellations' else MARKER).fullmatch(row)
        if not match:raise ValueError('Unsupported '+DATASETS[key][3]+' row; no arbitrary native options are imported.')
        count=4 if key=='sky_constellations' else 2
        coords=match.groups()[:count]
        for index,token in enumerate(coords):
            value=float(token)
            low,high=(-90,90) if index%2==0 else ((0,24) if key.startswith('sky_') else (-180,180) if key=='moon_sites' else (0,360))
            if not math.isfinite(value) or not low<=value<=high:
                raise ValueError('Annotation coordinates are outside the supported body/sky units.')
        if count==2:
            label,option=match.groups()[2:]
            if not label or len(label.encode('utf-8'))>100:raise ValueError('Annotation labels need 1–100 UTF-8 bytes.')
            if key=='sky_labels' and option!='image=none':raise ValueError('Bright-star labels require image=none; image dependencies are not imported.')
            if key=='moon_sites' and option:raise ValueError('Apollo rows do not accept extra native options.')
            if key=='mars_names' and option and not option.startswith('color='):raise ValueError('Mars rows accept only a named color.')
            rows.append(' '.join(coords)+f' "{label}"'+(' '+option if option else ''))
        else:rows.append(' '.join(coords))
        if len(rows)>DATASETS[key][2]:raise ValueError('Annotation row count exceeds the supported preset bound.')
    if not rows:raise ValueError('Annotation dataset has no supported rows.')
    return rows,comments


def validate_text(text,key):
    """Recognize our inert snapshot and strict native subset, without file I/O."""
    if key not in DATASETS:raise ValueError('Unknown installed annotation dataset.')
    if text=='':return 0
    if not isinstance(text,str) or len(text.encode('utf-8'))>LIMIT or not text.startswith(HEADER):raise ValueError('Unsupported annotation snapshot header.')
    source,filename,maximum,label=DATASETS[key]
    lines=text.splitlines()
    if len(lines)<4 or not re.fullmatch(r'# Source: '+re.escape(source)+r'; SHA256: [0-9a-f]{64}',lines[1]):
        raise ValueError('Annotation source receipt is missing or differs from its dataset.')
    if lines[2]!='# Local installed data; source identity and coordinates are not independently verified.':
        raise ValueError('Unsupported annotation provenance.')
    rows,comments=_rows('\n'.join(lines[3:]),key)
    # Snapshot rows precede retained attribution comments, making representation exact.
    expected='\n'.join([*lines[:3],*rows,*comments])+'\n'
    if text!=expected:raise ValueError('Annotation snapshot is not canonical; re-import its local source explicitly.')
    return len(rows)


def import_datasets(root,keys):
    """Snapshot only selected allowlisted files, including their attribution comments."""
    keys=tuple(keys)
    if not keys or len(set(keys))!=len(keys) or any(key not in DATASETS for key in keys):
        raise ValueError('Select one or more supported annotation layers before importing.')
    source=Path(root).expanduser()
    if not source.is_absolute() or any(not c.isprintable() for c in str(source)):
        raise ValueError('Choose an explicit absolute installed xplanet data directory.')
    try:
        # Package-manager root symlinks are allowed; their descendants are not.
        resolved=source.resolve(strict=True)
        class NoLinks:
            def __init__(self):self.fs=RootFS(resolved)
            def parent(self,path):return self.fs.parent(path,follow_symlinks=False)
        fs=NoLinks()
        originals={key:read_stable(fs,DATASETS[key][0],LIMIT) for key in keys}
        result={}
        for key,raw in originals.items():
            try:rows,comments=_rows(raw.decode('utf-8'),key)
            except UnicodeError as exc:raise ValueError('Annotation source must be UTF-8 text.') from exc
            result[key]=(HEADER+f'# Source: {DATASETS[key][0]}; SHA256: {hashlib.sha256(raw).hexdigest()}\n'
                         '# Local installed data; source identity and coordinates are not independently verified.\n'
                         +'\n'.join([*rows,*comments])+'\n')
            validate_text(result[key],key)
        if source.resolve(strict=True)!=resolved or any(read_stable(fs,DATASETS[key][0],LIMIT)!=raw for key,raw in originals.items()):
            raise ValueError('Annotation source changed during import; previous choices retained.')
        checkpoint()
        return result
    except (OSError,RuntimeError,TotalMarkerError) as exc:
        raise ValueError('Cannot read the selected installed annotation data safely; choose its real installed resource directory.') from exc
