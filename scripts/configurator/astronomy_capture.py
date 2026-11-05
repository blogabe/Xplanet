"""Read-only frozen NORAD/eclipses groundwork; no provider calls or activation.

Kept separate from weather: NORAD is current orbital data, whereas a NASA path
is a dated prediction with a bounded event interval. Scene/UI integration follows.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit,urlunsplit
from totalmarker.features import eclipse as eclipse_product
import re
import time

from totalmarker.config import load_bytes
from totalmarker.diagnostics import observation
from totalmarker.errors import TotalMarkerError
from totalmarker.features.norad import parse_tle
from totalmarker.paths import RootFS
from .cloud_capture import CaptureError, CaptureRace, read_stable, read_state, publication_pending, json_bytes
from .png import normalize_png
from .observation_capture import TOKEN, NUM, stamp

LIMIT = 256 * 1024
META_LIMIT = 8192
ICON_LIMIT = 1024*1024
ICON_NAME = re.compile(r'frozen-norad-([1-9][0-9]{0,4})\.png')
FILES = {'norad': ('frozen-norad.satellites', 'frozen-norad.satellites.tle'),
         'eclipse': ('frozen-eclipse.markers', 'frozen-eclipse.arcs')}
FACTS = {'checked_at', 'attempted_at', 'successful_at', 'published_at', 'last_outcome'}
SHA = re.compile(r'[0-9a-f]{64}')


def normalize_icon(raw):
    try:return normalize_png(raw,byte_limit=ICON_LIMIT,dimension=512,pixels_limit=512*512,decode_limit=3*1024*1024)
    except ValueError as exc:raise CaptureError('NORAD icon must be a valid bounded noninterlaced PNG (1 MiB, 512×512 maximum).') from exc


def payload_names(raw):
    """Only derive a bounded canonical allowlist, never filesystem paths."""
    try:
        if not isinstance(raw,bytes) or len(raw)>META_LIMIT:raise ValueError
        meta=json.loads(raw);product=meta['product'];names=FILES[product]
        icons=meta.get('icons',{})
        if not isinstance(icons,dict) or len(icons)>16 or (icons and (product!='norad' or meta['schema']!=3)):raise ValueError
        if any(not isinstance(key,str) or not isinstance(value,str) or not ICON_NAME.fullmatch(value) or value!=f'frozen-norad-{key}.png' for key,value in icons.items()):raise ValueError
        return (*names,*icons.values())
    except (ValueError,TypeError,KeyError,RecursionError):raise CaptureError('Invalid astronomy payload association.') from None


def rewrite_icons(raw,icons,prefix,*,reverse=False):
    for name in icons.values():
        old,new=(prefix+name,name) if reverse else (name,prefix+name)
        pattern=rb'(?<= image=)'+re.escape(old.encode())+rb'(?= |\n|$)'
        raw,count=re.subn(pattern,new.encode(),raw)
        if count!=1:raise CaptureError('Named NORAD icon references differ from their exact association.')
    return raw


def text_lines(raw):
    if not isinstance(raw, bytes) or len(raw) > LIMIT:
        raise CaptureError('Keep astronomy product files within 256 KiB each.')
    try: text = raw.decode('ascii')
    except UnicodeError: raise CaptureError('Astronomy products must be recognized ASCII output.') from None
    if len(text.splitlines()) > 4096 or any(len(row)>512 for row in text.splitlines()) or any(ord(c) < 32 and c != '\n' or ord(c) == 127 for c in text):
        raise CaptureError('Astronomy product contains unsupported controls or too many rows.')
    return text.splitlines()


def satellite_pair(first, second, metadata):
    ids = metadata['selected_ids']; captured = metadata['captured_at']; max_age = metadata['max_age_seconds']
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 16 or
            any(type(i) is not int or not 1 <= i <= 99999 for i in ids) or len(set(ids)) != len(ids) or
            type(max_age) is not int or not 1 <= max_age <= 2**31):
        raise CaptureError('A nonempty representable NORAD selection and bounded epoch policy are required.')
    rows = text_lines(first); elements = text_lines(second)
    if len(rows) != len(ids) or len(elements) != 3 * len(ids):
        raise CaptureError('NORAD selector/TLE count differs from saved selection.')
    epochs = []
    for index, (catalog_id, row) in enumerate(zip(ids, rows)):
        icon=re.search(r' image=([^ ]+)',row)
        expected=metadata.get('icons',{}).get(str(catalog_id))
        if (icon[1] if icon else None)!=expected:raise CaptureError('NORAD icon association differs from its selected object.')
        if icon:row=row[:icon.start()]+row[icon.end():]
        match = re.fullmatch(r'([0-9]{1,5}) "([A-Za-z0-9 ._()/+ -]{0,64})" color=([^ ]+) trail=\{orbit,(-?[0-9]+),(-?[0-9]+),([0-9]+)\}(?: transparent=\{([0-9]+),([0-9]+),([0-9]+)\})?(?: altcirc=([0-9]+))?(?: align=(right|left|above|below|center))?', row)
        if not match or int(match[1]) != catalog_id or not TOKEN.fullmatch(match[3]):
            raise CaptureError('Unsupported NORAD selector or image dependency; original files were retained.')
        if ',' in match[3] and any(int(value) > 255 for value in match[3].split(',')):
            raise CaptureError('Invalid NORAD selector color.')
        start, end, step = map(int, match.groups()[3:6])
        if not -1440 <= start <= end <= 1440 or not 1 <= step <= 60:
            raise CaptureError('Unsupported NORAD trail bounds.')
        if any(value is not None and int(value) > 255 for value in match.groups()[6:9]):
            raise CaptureError('Invalid NORAD transparency.')
        if match[10] is not None and not 0 <= int(match[10]) <= 90:
            raise CaptureError('Invalid NORAD altitude-circle option.')
        tle = ('\n'.join(elements[index*3:index*3+3])+'\n').encode('ascii')
        try: _, _, _, epoch = parse_tle(tle, catalog_id, captured, max_age)
        except TotalMarkerError as exc: raise CaptureError('NORAD elements fail the existing epoch/orbital validator.') from exc
        epochs.append(epoch)
    if min(epochs) != metadata['oldest_epoch_at']:
        raise CaptureError('Saved NORAD epoch differs from the validated elements.')
    return first, second


def eclipse_pair(first, second, metadata, *, source=False):
    kind, date = metadata['kind'], metadata['event_date']
    if kind not in ('Total', 'Annular', 'Hybrid') or not isinstance(date, str) or not re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', date):
        raise CaptureError('Missing recognized central eclipse event.')
    try: event = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError: raise CaptureError('Invalid eclipse event date.') from None
    start, end = metadata['start_at'], metadata['end_at']
    try: stamp(start,False); stamp(end,False)
    except ValueError as exc: raise CaptureError('Invalid eclipse coverage timestamp.') from exc
    first_day=datetime.fromtimestamp(start,timezone.utc).date();last_day=datetime.fromtimestamp(end,timezone.utc).date()
    local_origin=metadata.get('origin',{})
    explicit=metadata.get('schema')==4 and local_origin.get('kind')=='local-nasa-format'
    if (not start < end or end-start>=86400 or first_day not in (event-timedelta(days=1),event) or
            last_day not in (first_day,first_day+timedelta(days=1)) or not first_day<=event<=last_day):
        raise CaptureError('Eclipse sample coverage is invalid or differs from the event date.')
    if first_day!=last_day and not explicit:
        raise CaptureError('Ambiguous midnight path chronology: import the local table with an explicit first-row UTC date; the event title does not establish it.')
    if explicit and local_origin.get('first_row_utc_date')!=first_day.isoformat():raise CaptureError('First-row UTC date differs from recorded local provenance.')
    header = f"# Eclipse Predictions by Fred Espenak, NASA's GSFC; {kind} {date} UTC"
    local = metadata.get('origin',{}).get('kind')=='local-nasa-format'
    qualified = f"# Unverified local NASA-format central path; {kind} {date} UTC"
    allowed = (header,qualified) if local else (header,)
    output = []; first_header = None
    for arcs, raw in ((False,first),(True,second)):
        lines = text_lines(raw)
        if not lines or lines[0] not in allowed or first_header is not None and lines[0]!=first_header:
            raise CaptureError('Only recognized NASA central-path producer output can be captured.')
        first_header = lines[0]
        kept = [first_header]; count = 0; notices = set(); sections = []; samples = []; rollover=0
        for row in lines[1:]:
            if arcs and row in ('# north path','# south path','# center path'):
                sections.append(row)
                kept.append(row); continue
            if source and not arcs and 'position=pixel' in row:
                # These are wallclock-derived producer notices, never scene labels.
                notice = re.fullmatch(r'-55 1 "'+kind+r' Solar Eclipse central-path (?:samples begin in [0-9]+h [0-9]+m \('+date+r' [0-9]{2}:[0-9]{2} UTC\)|sampling underway \(began '+date+r' [0-9]{2}:[0-9]{2} UTC\)|sampling ended '+datetime.fromtimestamp(end,timezone.utc).strftime('%Y-%m-%d')+r' [0-9]{2}:[0-9]{2} UTC)" color=([^ ]+) image=none position=pixel',row)
                context = re.fullmatch(r'-45 1 "NASA predicted central path and limits shown" color=([^ ]+) image=none position=pixel',row)
                if (not notice and not context) or not TOKEN.fullmatch((notice or context)[1]):
                    raise CaptureError('Unrecognized eclipse pixel notice was not silently removed.')
                label = 'notice' if notice else 'context'
                if label in notices: raise CaptureError('Repeated eclipse notices are unsupported.')
                notices.add(label)
                continue
            if arcs:
                match = re.fullmatch(rf'({NUM}) ({NUM}) ({NUM}) ({NUM}) color=([^ ]+) spacing=0\.2',row)
                coordinate_count=4
            else:
                match = re.fullmatch(rf'({NUM}) ({NUM}) "([0-9]{{2}}:[0-9]{{2}}) UTC" color=([^ ]+) align=above symbolsize=4',row)
                coordinate_count=2
            if not match: raise CaptureError('Unsupported eclipse marker/arc syntax.')
            color = match[5] if arcs else match[4]
            if not TOKEN.fullmatch(color) or ',' in color and any(int(value)>255 for value in color.split(',')):
                raise CaptureError('Invalid eclipse path color.')
            for index in range(coordinate_count):
                number = float(match[index+1]); bound = 90 if index%2==0 else 180
                if not math.isfinite(number) or not -bound <= number <= bound:
                    raise CaptureError('Eclipse path coordinate is out of range.')
            if not arcs:
                try: value=datetime.strptime(first_day.isoformat()+'T'+match[3]+'Z','%Y-%m-%dT%H:%MZ').replace(tzinfo=timezone.utc).timestamp()
                except ValueError: raise CaptureError('Invalid eclipse sample time.') from None
                value+=rollover*86400
                if samples and value<samples[-1]:
                    rollover+=1;value+=86400
                if rollover>1:raise CaptureError('Eclipse labels imply more than one UTC midnight rollover.')
                if not start <= value <= end: raise CaptureError('Eclipse marker lies outside saved event coverage.')
                if samples and value <= samples[-1]: raise CaptureError('Eclipse samples must increase without duplicates.')
                samples.append(value)
            kept.append(row); count += 1
        if (count < (1 if arcs else 2) or
                not arcs and (not samples or samples[0]!=start or samples[-1]!=end) or
                arcs and sections != ['# north path','# south path','# center path'] or
                notices and notices != {'notice','context'}):
            raise CaptureError('Empty, expired or incomplete eclipse output is not an active path.')
        output.append(('\n'.join(kept)+'\n').encode('ascii'))
    return tuple(output)


def reference_url(value):
    """Validate an asserted public event identity; never fetch or authenticate it."""
    try:
        if not isinstance(value,str) or len(value)>2048:raise ValueError
        parsed=urlsplit(value)
        if (parsed.scheme!='https' or parsed.hostname!='eclipse.gsfc.nasa.gov' or
                parsed.port not in (None,443) or parsed.username is not None or parsed.password is not None or
                parsed.query or parsed.fragment or not eclipse_product.URL.fullmatch(parsed.path)):raise ValueError
        return urlunsplit(('https','eclipse.gsfc.nasa.gov',parsed.path,'',''))
    except (ValueError,TypeError):raise CaptureError('Provide a credential-free official NASA central-path event reference URL; it is checked for identity only, never fetched.') from None


def local_eclipse(source,claimed_url,*,first_row_date=None,now=None):
    """Recognize an explicitly supplied bounded file; not proof of NASA authorship."""
    from .exchange import read_file
    try:raw=read_file(source,2*1024*1024)
    except (OSError,ValueError,RuntimeError):raise CaptureError('Choose a stable regular local NASA-format path file up to 2 MiB without symlink components.') from None
    url=reference_url(claimed_url)
    try:path=eclipse_product.parse_path(raw,url)
    except TotalMarkerError as exc:raise CaptureError('Local content is not a complete consistent NASA-format event path: '+str(exc)) from exc
    event=datetime.strptime(path.date,'%Y-%m-%d').date()
    crossing=datetime.fromtimestamp(path.start_at,timezone.utc).date()!=datetime.fromtimestamp(path.end_at,timezone.utc).date()
    explicit=None
    if first_row_date is not None:
        try:
            if not isinstance(first_row_date,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',first_row_date):raise ValueError
            explicit=datetime.strptime(first_row_date,'%Y-%m-%d').date()
        except ValueError:raise CaptureError('Choose a valid first-row UTC date in YYYY-MM-DD form.') from None
        if explicit not in (event-timedelta(days=1),event) or not crossing and explicit!=event:raise CaptureError('First-row date must be the event date or, for a midnight crossing, the preceding UTC date.')
    if crossing and explicit is None:raise CaptureError('Midnight path requires an explicit first-row UTC date from independent evidence; the event title is not enough.')
    if explicit is not None:
        offset=(explicit-event).days*86400
        path=replace(path,start_at=path.start_at+offset,end_at=path.end_at+offset,points=tuple(replace(point,time_at=None if point.time_at is None else point.time_at+offset) for point in path.points))
    style=SimpleNamespace(edge_color='Grey',center_color='Black',notice_enabled=False,notice_color='White')
    payload=eclipse_product.render(path,style,path.start_at,True)
    header=f"# Unverified local NASA-format central path; {path.kind} {path.date} UTC\n".encode('ascii')
    payload=tuple(header+data.split(b'\n',1)[1] for data in payload)
    captured=time.time() if now is None else now
    try:stamp(captured,False)
    except ValueError as exc:raise CaptureError('Invalid local import time.') from exc
    meta={'schema':2,'product':'eclipse','captured_at':captured,
          'facts':{key:None for key in FACTS},'source_hashes':None,
          'origin':{'kind':'local-nasa-format','input_bytes':len(raw),'input_sha256':hashlib.sha256(raw).hexdigest(),'reference_url':url,'authorship_verified':False},
          'kind':path.kind,'event_date':path.date,'start_at':path.start_at,'end_at':path.end_at,'wallclock_notices_removed':True,
          'files':{name:hashlib.sha256(data).hexdigest() for name,data in zip(FILES['eclipse'],payload)}}
    if explicit is not None:meta['schema']=4;meta['origin']['first_row_utc_date']=explicit.isoformat()
    return FrozenAstronomy(json_bytes(meta),tuple(zip(FILES['eclipse'],payload)))


@dataclass(frozen=True)
class FrozenAstronomy:
    provenance: bytes = field(repr=False)
    payload: tuple = field(repr=False)

    def __post_init__(self):
        try:
            if not isinstance(self.provenance,bytes) or len(self.provenance)>META_LIMIT: raise ValueError
            meta=json.loads(self.provenance);product=meta['product']
            common={'schema','product','captured_at','facts','source_hashes','files'}
            extra={'selected_ids','max_age_seconds','oldest_epoch_at'} if product=='norad' else {'kind','event_date','start_at','end_at','wallclock_notices_removed'}
            local=type(meta['schema']) is int and meta['schema'] in (2,4)
            icons=meta['schema']==3
            if icons:
                extra.add('icons')
                if product!='norad' or not isinstance(meta['icons'],dict) or not 1<=len(meta['icons'])<=16:raise ValueError
                if any(key not in list(map(str,meta['selected_ids'])) or value!=f'frozen-norad-{key}.png' for key,value in meta['icons'].items()):raise ValueError
            if local:
                common.add('origin');origin=meta['origin']
                if (product!='eclipse' or not isinstance(origin,dict) or set(origin)!=({'kind','input_bytes','input_sha256','reference_url','authorship_verified'}|({'first_row_utc_date'} if meta['schema']==4 else set())) or
                        origin['kind']!='local-nasa-format' or origin['authorship_verified'] is not False or
                        type(origin['input_bytes']) is not int or not 0<origin['input_bytes']<=2*1024*1024 or
                        not isinstance(origin['input_sha256'],str) or not SHA.fullmatch(origin['input_sha256']) or
                        reference_url(origin['reference_url'])!=origin['reference_url'] or meta['source_hashes'] is not None):raise ValueError
                identity=eclipse_product.URL.fullmatch(urlsplit(origin['reference_url']).path)
                year,month,day,code=identity.groups()
                if datetime(int(year),eclipse_product.MONTHS[month],int(day)).date().isoformat()!=meta['event_date'] or eclipse_product.TYPE_CODE[meta['kind']]!=code:raise ValueError
            if (product not in FILES or set(meta)!=common|extra or type(meta['schema']) is not int or meta['schema'] not in (1,2,3,4) or
                    json_bytes(meta)!=self.provenance or not isinstance(self.payload,tuple) or not 2<=len(self.payload)<=18):raise ValueError
            stamp(meta['captured_at'],False)
            facts=meta['facts']
            if not isinstance(facts,dict) or set(facts)!=FACTS or facts['last_outcome'] not in (None,'installed','updated','unchanged','changed','cached','failed'):raise ValueError
            for key in FACTS-{'last_outcome'}:stamp(facts[key])
            if local and any(value is not None for value in facts.values()):raise ValueError
            if any(not isinstance(row,tuple) or len(row)!=2 or not isinstance(row[0],str) or not isinstance(row[1],bytes) for row in self.payload):raise ValueError
            files=dict(self.payload)
            if tuple(files)!=payload_names(self.provenance) or set(meta['files'])!=set(files) or (not local and set(meta['source_hashes'])!=set(files)):raise ValueError
            for name,data in files.items():
                if not isinstance(data,bytes) or len(data)>(ICON_LIMIT if ICON_NAME.fullmatch(name) else LIMIT) or meta['files'][name]!=hashlib.sha256(data).hexdigest() or (not local and not SHA.fullmatch(meta['source_hashes'][name])):raise ValueError
            first,second=(files[name] for name in FILES[product])
            if product=='norad':
                satellite_pair(first,second,meta)
                for name in meta.get('icons',{}).values():
                    if normalize_icon(files[name])!=files[name]:raise ValueError
            elif meta['wallclock_notices_removed'] is not True or eclipse_pair(first,second,meta)!=(first,second):raise ValueError
        except (ValueError,TypeError,KeyError,RecursionError,OverflowError,TotalMarkerError):
            raise CaptureError('Frozen astronomy data/provenance is invalid or unsupported.') from None

    @property
    def metadata(self):return json.loads(self.provenance)
    @property
    def identity(self):return hashlib.sha256(self.provenance).hexdigest()
    @property
    def product(self):return self.metadata['product']
    @property
    def window_token(self):
        if self.product!='eclipse':return ''
        return '/'.join(datetime.fromtimestamp(self.metadata[key],timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') for key in ('start_at','end_at'))
    @property
    def byte_size(self):return len(self.provenance)+sum(len(data) for _,data in self.payload)

    def files(self, prefix=''):
        if prefix and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}\.',prefix):
            raise CaptureError('Invalid astronomy scene prefix.')
        files={f'frozen-{self.product}.json':self.provenance,**dict(self.payload)}
        if prefix and self.metadata.get('icons'):
            name=FILES['norad'][0];files[name]=rewrite_icons(files[name],self.metadata['icons'],prefix)
        return {prefix+name:data for name,data in files.items()}

    @classmethod
    def from_files(cls, contents, product, prefix=''):
        if product not in FILES:raise CaptureError('Choose a supported astronomy capture.')
        # Validate the prefix before looking up any caller-supplied mapping key.
        if prefix and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}\.',prefix):
            raise CaptureError('Invalid astronomy scene prefix.')
        try:
            raw=contents[prefix+f'frozen-{product}.json'];meta=json.loads(raw)
            files={name:contents[prefix+name] for name in payload_names(raw)}
            if prefix and meta.get('icons'):files[FILES['norad'][0]]=rewrite_icons(files[FILES['norad'][0]],meta['icons'],prefix,reverse=True)
            frozen=cls(raw,tuple(files.items()))
            if frozen.product!=product:raise CaptureError('Astronomy provenance belongs to another product.')
            return frozen
        except (KeyError,ValueError,TypeError,RecursionError) as exc:raise CaptureError('Missing or invalid associated frozen astronomy file.') from exc

    def availability(self, *, target, time_mode, utc=None, now=None):
        """Return an explicit reason; caller must not infer availability from age alone."""
        meta=self.metadata
        if target!='earth':return False,'This frozen astronomy product is Earth-only.'
        moment=time.time() if now is None else now
        try: stamp(moment,False)
        except ValueError: return False,'Current UTC time is unavailable or invalid.'
        if meta['product']=='norad':
            if time_mode!='now':return False,'Current NORAD orbital elements are available only for Now scenes.'
            try: satellite_pair(*(dict(self.payload)[name] for name in FILES['norad']),{**meta,'captured_at':moment})
            except CaptureError:
                return False,'Frozen NORAD elements are outside their saved epoch freshness window.'
            return True,'Frozen TLEs are propagated at Now; no live tracking or provider access is implied.'
        if time_mode=='fixed':
            try:moment=datetime.strptime(utc,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
            except (ValueError,TypeError):return False,'Choose a valid fixed UTC scene time.'
        elif time_mode!='now':return False,'Unknown scene time mode.'
        if not meta['start_at'] <= moment <= meta['end_at']:
            return False,'Scene time is outside the saved central-path sample coverage.'
        return True,('Unverified local NASA-format central path' if meta.get('origin') else 'NASA predicted central path')+' for this event; wallclock countdown/update notices omitted.'


def capture_existing(root, product, config='config/totalmarker.toml', *, now=None):
    if product not in FILES:raise CaptureError('Choose NORAD or eclipse capture.')
    if not Path(root).is_absolute():raise CaptureError('Choose an absolute existing source root.')
    captured=time.time() if now is None else now
    try: stamp(captured,False)
    except ValueError as exc: raise CaptureError('Invalid astronomy capture time.') from exc
    try:
        fs=RootFS(root)
        for attempt in range(2):
            try:
                raw=read_stable(fs,config,1024*1024);settings=load_bytes(fs,raw,config)
                if publication_pending(fs,settings):raise CaptureError('Pending TotalMarker publication; use normal recovery before capture.')
                records=read_state(fs,settings.state)['products'];record=records.get(product,{})
                options=getattr(settings,product)
                paths=(options.satellite,options.satellite+'.tle') if product=='norad' else (options.marker,options.arc)
                keys=('satellite_sha256','tle_sha256') if product=='norad' else ('marker_sha256','arc_sha256')
                originals=tuple(read_stable(fs,path,LIMIT) for path in paths)
                if any(hashlib.sha256(data).hexdigest()!=record.get(key) for data,key in zip(originals,keys)):
                    raise CaptureRace('Astronomy pair differs from saved publication hashes.')
                if hashlib.sha256(originals[0]+b'\0'+originals[1]).hexdigest()!=record.get('body_sha256'):
                    raise CaptureError('Astronomy pair lacks coherent publication metadata.')
                facts=observation(record)
                meta={'schema':1,'product':product,'captured_at':captured,
                      'facts':{key:facts[key] for key in FACTS},
                      'source_hashes':{name:hashlib.sha256(data).hexdigest() for name,data in zip(FILES[product],originals)}}
                if product=='norad':
                    meta.update(selected_ids=record.get('selected_ids'),max_age_seconds=options.max_age,oldest_epoch_at=record.get('oldest_epoch_at'))
                    # Reject malformed/excess selections before any dependency I/O.
                    satellite_pair(re.sub(rb' image=[^ \n]+',b'',originals[0]),originals[1],meta)
                    selector_rows=[];icons={};dependencies={};icon_bytes={}
                    for row in text_lines(originals[0]):
                        match=re.search(r' image=([^ ]+)',row)
                        if not match:selector_rows.append(row);continue
                        catalog_id=row.split(' ',1)[0];source_name=match[1]
                        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\.png',source_name,re.IGNORECASE) or '..' in source_name:raise CaptureError('Only safe bounded PNG NORAD icons are supported.')
                        name=f'frozen-norad-{catalog_id}.png'
                        if not ICON_NAME.fullmatch(name) or catalog_id in icons:raise CaptureError('Ambiguous NORAD icon association.')
                        source_path='images/'+source_name
                        if source_path not in dependencies:dependencies[source_path]=read_stable(fs,source_path,ICON_LIMIT)
                        raw_icon=dependencies[source_path]
                        dependencies[source_path]=raw_icon;icon_bytes[name]=normalize_icon(raw_icon);icons[catalog_id]=name
                        selector_rows.append(row[:match.start(1)]+name+row[match.end(1):])
                        meta['source_hashes'][name]=hashlib.sha256(raw_icon).hexdigest()
                    if icons:meta.update(schema=3,icons=icons)
                    selector=('\n'.join(selector_rows)+'\n').encode('ascii')
                    payload=satellite_pair(selector,originals[1],meta)
                else:
                    meta.update(kind=record.get('kind'),event_date=record.get('event_date'),start_at=record.get('start_at'),end_at=record.get('end_at'),wallclock_notices_removed=True)
                    payload=eclipse_pair(*originals,meta,source=True)
                current=read_state(fs,settings.state)['products']
                if product=='norad' and any(data!=read_stable(fs,path,ICON_LIMIT) for path,data in dependencies.items()):raise CaptureRace('NORAD icon changed during capture.')
                if records.get(product)!=current.get(product) or raw!=read_stable(fs,config,1024*1024) or any(data!=read_stable(fs,path,LIMIT) for path,data in zip(paths,originals)):
                    raise CaptureRace('Astronomy source changed during capture.')
                if publication_pending(fs,settings):raise CaptureError('Publication became pending; capture was not accepted.')
                meta['files']={name:hashlib.sha256(data).hexdigest() for name,data in zip(FILES[product],payload)}
                all_payload=dict(zip(FILES[product],payload))
                if product=='norad':all_payload.update(icon_bytes)
                meta['files']={name:hashlib.sha256(data).hexdigest() for name,data in all_payload.items()}
                return FrozenAstronomy(json_bytes(meta),tuple((name,all_payload[name]) for name in payload_names(json_bytes(meta))))
            except CaptureRace:
                if attempt:raise
    except TotalMarkerError:
        raise CaptureError('Astronomy source could not be validated; nothing was changed.') from None


def describe(frozen):return describe_metadata(frozen.metadata)


def describe_metadata(meta):
    def when(value):return 'unknown' if value is None else datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    facts=meta['facts']
    text=f"Frozen {meta['product']}: captured {when(meta['captured_at'])}; last success {when(facts['successful_at'])}; publication {when(facts['published_at'])}; outcome {facts['last_outcome'] or 'unknown'}. Provider access was not checked."
    if meta['product']=='norad':return text+f"\nSelected NORAD IDs: {', '.join(map(str,meta['selected_ids']))}; captured selection only, not a claim of complete group coverage.\nTLE oldest epoch {when(meta['oldest_epoch_at'])}; saved maximum age {meta['max_age_seconds']} seconds. Now-only preview; desktop handoff unavailable because runtime expiry is not enforced."
    if meta.get('origin',{}).get('kind')=='local-nasa-format':text+='\nImported local NASA-format content; reference/content identity checked, NASA authorship NOT verified. Input SHA-256 '+meta['origin']['input_sha256']+'. No producer fetch/success/publication is claimed.'
    if 'first_row_utc_date' in meta.get('origin',{}):text+='\nUser-supplied first-row UTC date: '+meta['origin']['first_row_utc_date']+'; independently unverified.'
    return text+f"\n{meta['kind']} eclipse {meta['event_date']}; central-path sample coverage {when(meta['start_at'])} to {when(meta['end_at'])}. Fixed UTC only in this editor; wallclock notices omitted."


def main():
    import argparse
    from .fileio import OwnedFiles,same_directory
    parser=argparse.ArgumentParser(description='Internal read-only astronomy capture worker')
    parser.add_argument('--root');parser.add_argument('--config')
    parser.add_argument('--local-eclipse',type=Path);parser.add_argument('--reference-url');parser.add_argument('--first-row-date')
    parser.add_argument('--product',choices=tuple(FILES));parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();fd=None;owned=None
    if args.local_eclipse is not None:
        if not args.reference_url or args.root or args.config or args.product:parser.error('Local import requires --reference-url and excludes producer-root options.')
    elif not args.root or not args.config or not args.product or args.reference_url or args.first_row_date:parser.error('Capture requires --root, --config and --product.')
    try:
        target=args.output
        if not target.is_dir() or target!=target.resolve() or target.stat().st_uid!=os.geteuid() or target.stat().st_mode&0o077 or any(target.iterdir()):raise CaptureError('Capture output must be an empty private workspace.')
        frozen=local_eclipse(args.local_eclipse,args.reference_url,first_row_date=args.first_row_date) if args.local_eclipse is not None else capture_existing(args.root,args.product,args.config)
        fd=os.open(target,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);owned=OwnedFiles(fd)
        same_directory(target,fd)
        for name,data in frozen.files().items():owned.write(name,data)
        os.fsync(fd);same_directory(target,fd)
        return 0
    except CaptureError as exc:
        if owned is not None:owned.cleanup()
        print('Astronomy capture unavailable: '+str(exc))
        return 1
    except (OSError,ValueError):
        if owned is not None:owned.cleanup()
        print('Astronomy capture unavailable: saved pair/metadata, epoch, event coverage or paths are unsupported; source data was not changed.')
        return 1
    finally:
        if fd is not None:os.close(fd)


if __name__=='__main__':raise SystemExit(main())
