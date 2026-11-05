"""One bundled manual shared by CLI and UI; no Textual/runtime preparation."""
import os,stat
from pathlib import Path

GUIDE=Path(__file__).resolve().parents[2]/'docs/configurator/user-guide.md'
LIMIT=128*1024

def read_guide():
    try:parent=GUIDE.parent.resolve()
    except (OSError,RuntimeError) as exc:raise ValueError('Guide directory is unavailable; restore the complete checkout.') from exc
    if GUIDE.parent!=parent:raise ValueError('Guide directory is linked; restore the complete checkout.')
    fd=os.open(GUIDE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size>LIMIT:raise ValueError('Guide is not a bounded regular file; restore the complete checkout.')
        raw=stream.read(LIMIT+1)
        after=os.fstat(stream.fileno())
        if len(raw)>LIMIT or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Guide changed during reading; retry.')
    return raw.decode('utf-8')
