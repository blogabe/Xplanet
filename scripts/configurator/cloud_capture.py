"""Explicit read-only cloud capture. No provider calls, locks or journal replay."""
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
from datetime import datetime, timezone

from totalmarker.config import load_bytes
from totalmarker.diagnostics import observation
from totalmarker.errors import TotalMarkerError
from totalmarker.health import cloud_freshness
from totalmarker.image import validate_jpeg, cloud_creation_time
from totalmarker.paths import RootFS
from totalmarker.state import STATE_LIMIT, validate_state

IMAGE_FILE = 'cloud-capture.jpg'
META_FILE = 'cloud-capture.json'
IMAGE_LIMIT = 32 * 1024 * 1024
META_LIMIT = 8192
OUTCOMES = (None, 'installed', 'updated', 'unchanged', 'cached', 'failed')
STAMPS = ('captured_at', 'source_created_at', 'last_check_at', 'last_attempt_at',
          'last_success_at', 'last_publication_at')
KEYS = {'schema','product','image_sha256','width','height','source_time_origin',
        'warning_seconds','last_outcome',*STAMPS}


class CaptureError(ValueError):
    pass


class CaptureRace(CaptureError):
    pass


def json_bytes(value):
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


@dataclass(frozen=True)
class FrozenCloud:
    image: bytes = field(repr=False)
    provenance: bytes = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.image,bytes) or len(self.image)>IMAGE_LIMIT:
            raise CaptureError('Captured cloud image exceeds 32 MiB.')
        if not isinstance(self.provenance,bytes) or len(self.provenance)>META_LIMIT:
            raise CaptureError('Invalid cloud provenance size.')
        try:
            meta=json.loads(self.provenance)
            if not isinstance(meta,dict) or set(meta)!=KEYS or type(meta['schema']) is not int or meta['schema']!=1 or meta['product']!='clouds':
                raise ValueError
            if self.provenance!=json_bytes(meta):raise ValueError
            for key in STAMPS:
                value=meta[key]
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=32503680000):raise ValueError
            if meta['captured_at'] is None:raise ValueError
            if type(meta['warning_seconds']) is not int or not 0<=meta['warning_seconds']<=2**31:raise ValueError
            if meta['last_outcome'] not in OUTCOMES:raise ValueError
            if type(meta['width']) is not int or type(meta['height']) is not int or not 0<meta['width']<=8192 or meta['width']!=2*meta['height']:raise ValueError
            info=validate_jpeg(self.image,meta['width'])
            if info.height!=meta['height'] or hashlib.sha256(self.image).hexdigest()!=meta['image_sha256']:raise ValueError
            created=meta['source_created_at']
            if meta['source_time_origin']!=('unavailable' if created is None else 'jpeg-earthdesk-comment'):raise ValueError
            if created is not None and cloud_creation_time(self.image)!=created:raise ValueError
        except (ValueError,TypeError,KeyError,RecursionError,TotalMarkerError):
            raise CaptureError('Captured image/provenance is invalid or inconsistent; use a supported 2:1 JPEG up to 8192×4096.') from None

    @property
    def metadata(self):
        return json.loads(self.provenance)

    @property
    def identity(self):
        return hashlib.sha256(self.provenance).hexdigest()

    def files(self):
        return {IMAGE_FILE:self.image,META_FILE:self.provenance}

    def freshness(self,now=None):
        meta=self.metadata
        return cloud_freshness(meta['source_created_at'],meta['warning_seconds'],time.time() if now is None else now)


def describe_capture(meta):
    def stamp(value):
        return 'unknown' if value is None else datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    return (f'Frozen cloud JPEG {meta["width"]}×{meta["height"]}; captured {stamp(meta["captured_at"])}; '
            f'image created {stamp(meta["source_created_at"])}.\n'
            f'Producer last success {stamp(meta["last_success_at"])}; publication {stamp(meta["last_publication_at"])}; '
            f'recorded outcome {meta["last_outcome"] or "unknown"}. Provider access was not checked.\n'
            f'Image SHA-256: {meta["image_sha256"]}')


def read_stable(fs,path,limit):
    """Descriptor-held bounded regular read; no create, lock or recovery paths."""
    try:
        with fs.parent(path) as (parent,name):
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            with os.fdopen(fd,'rb') as source:
                before=os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size>limit:
                    raise CaptureError('A required saved product input is not a bounded regular file.')
                raw=source.read(limit+1)
                after=os.fstat(source.fileno())
                named=os.stat(name,dir_fd=parent,follow_symlinks=False)
                key=lambda item:(item.st_dev,item.st_ino,item.st_size,item.st_mtime_ns,item.st_ctime_ns)
                if key(before)!=key(after) or key(before)!=key(named):
                    raise CaptureRace('Saved product inputs changed during capture; retry when publication finishes.')
                if len(raw)>limit:raise CaptureError('A required saved product input exceeds its size limit.')
                return raw
    except (FileNotFoundError,TotalMarkerError,OSError):
        raise CaptureError('A required saved product input is missing, unreadable or outside the selected root.') from None


def read_state(fs,path):
    try:return validate_state(json.loads(read_stable(fs,path,STATE_LIMIT)))
    except (TotalMarkerError,ValueError,UnicodeError,RecursionError) as exc:
        if isinstance(exc,CaptureError):raise
        raise CaptureError('Saved TotalMarker state cannot be validated; preserve it for normal recovery.') from None


def publication_pending(fs,settings):
    # All product journals carry shared state; inspect presence, never contents.
    journals=[settings.journal]+[getattr(settings,name).journal for name in ('quake','storm','volcano','norad','eclipse','santa')]
    return any(fs.file_stat(path) is not None for path in dict.fromkeys(journals))


def capture_existing(root,config='config/totalmarker.toml',*,now=None):
    """Optimistic coherent capture, retrying a changing publication at most once."""
    if not Path(root).is_absolute():raise CaptureError('Choose an absolute existing TotalMarker root.')
    try:fs=RootFS(root)
    except TotalMarkerError:raise CaptureError('Choose an existing TotalMarker root without symlink ancestors.') from None
    for attempt in range(2):
        try:
            raw_config=read_stable(fs,config,1024*1024)
            try:settings=load_bytes(fs,raw_config,config)
            except (TotalMarkerError,ValueError):raise CaptureError('Cannot validate the selected TotalMarker configuration; no refresh was attempted.') from None
            if publication_pending(fs,settings):
                raise CaptureError('Pending TotalMarker publication: preserve its journal and recover through normal TotalMarker operation, not the configurator.')
            record=read_state(fs,settings.state)['products'].get('clouds',{})
            image=read_stable(fs,settings.image,min(settings.max_bytes,IMAGE_LIMIT))
            digest=hashlib.sha256(image).hexdigest()
            if digest!=record.get('image_sha256'):
                raise CaptureRace('Cloud bytes do not match a saved publication; no verifiable capture is available.')
            try:info=validate_jpeg(image,settings.resolution)
            except TotalMarkerError:raise CaptureError('The saved cloud product is not a supported JPEG matching its configured width.') from None
            if (record!=read_state(fs,settings.state)['products'].get('clouds',{}) or
                    raw_config!=read_stable(fs,config,1024*1024)):
                raise CaptureRace('Saved cloud metadata changed during capture; retry after publication.')
            if publication_pending(fs,settings):
                raise CaptureError('TotalMarker publication is pending; capture was not accepted.')
            facts=observation(record)
            created=record.get('source_created_at')
            if created is not None and (record.get('source_image_sha256')!=digest or cloud_creation_time(image)!=created):
                raise CaptureError('Saved cloud creation metadata does not match the image; no capture was accepted.')
            meta={'schema':1,'product':'clouds','image_sha256':digest,'width':info.width,'height':info.height,
                  'captured_at':time.time() if now is None else now,'source_created_at':created,
                  'source_time_origin':'unavailable' if created is None else 'jpeg-earthdesk-comment',
                  'warning_seconds':settings.warning,'last_check_at':facts['checked_at'],
                  'last_attempt_at':facts['attempted_at'],'last_success_at':facts['successful_at'],
                  'last_publication_at':facts['published_at'],
                  'last_outcome':facts['last_outcome'] if facts['last_outcome'] in OUTCOMES else None}
            return FrozenCloud(image,json_bytes(meta))
        except CaptureRace:
            if attempt:raise
        except TotalMarkerError:
            raise CaptureError('Saved cloud metadata or paths cannot be inspected safely; no source files were changed.') from None


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Internal read-only cloud capture worker')
    parser.add_argument('--root',required=True);parser.add_argument('--config',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        target=args.output
        if not target.is_dir() or target!=target.resolve() or any(target.iterdir()):
            raise CaptureError('Capture workspace must be a new empty private directory.')
        frozen=capture_existing(args.root,args.config)
        for name,data in frozen.files().items():
            fd=os.open(target/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(data)
        return 0
    except CaptureError as exc:
        print(str(exc));return 1
    except Exception:
        print('Cloud capture failed; original data was not changed.');return 1


if __name__=='__main__':
    raise SystemExit(main())
