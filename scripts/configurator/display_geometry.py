"""Read-only macOS frame hint for new UI drafts; never a runtime setting."""
from dataclasses import dataclass
import json
import subprocess
import sys

from .geometry import DEFAULT_GEOMETRY, geometry

# NSScreen[0] is the menu-bar display, not the active application's screen.
# Convert coordinates through AppKit instead of assuming a Retina scale factor.
SCRIPT = """ObjC.import('AppKit');
$.NSApplication.sharedApplication;
var screens = $.NSScreen.screens;
var rows = [];
if (screens.count > 32) throw Error('Too many displays');
for (var i = 0; i < screens.count; i++) {
    var screen = screens.objectAtIndex(i);
    var frame = screen.frame;
    var backing = screen.convertRectToBacking(frame);
    rows.push({points:[frame.size.width,frame.size.height],
               pixels:[backing.size.width,backing.size.height]});
}
JSON.stringify(rows);"""


@dataclass(frozen=True)
class DisplayGeometry:
    default: str
    description: str


def fallback(reason):
    return DisplayGeometry(DEFAULT_GEOMETRY,
        f'macOS display size unavailable ({reason}); new-scene fallback {DEFAULT_GEOMETRY}.')


def dimensions(value):
    if not isinstance(value,list) or len(value)!=2 or any(
            type(v) not in (int,float) or not 1<=v<=131072 or int(v)!=v for v in value):
        raise ValueError('Invalid display dimensions')
    return 'x'.join(str(int(v)) for v in value)


def parse(raw):
    if len(raw)>16384:raise ValueError('Oversized display report')
    rows=json.loads(raw)
    if not isinstance(rows,list) or not 1<=len(rows)<=32:raise ValueError('No bounded display list')
    frames=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'points','pixels'}:raise ValueError('Invalid display report')
        frames.append((dimensions(row['pixels']),dimensions(row['points'])))
    current=frames[0][0]
    try:chosen=geometry(current)
    except ValueError:chosen=DEFAULT_GEOMETRY
    details='; '.join(f'{"primary" if i==0 else "display "+str(i+1)} {pixels} backing pixels ({points} points)'
                     for i,(pixels,points) in enumerate(frames))
    policy=f'New-scene default {chosen}.' if chosen==current else f'Primary size exceeds preview limits; new-scene fallback {chosen}.'
    return DisplayGeometry(chosen,f'macOS displays at launch: {details}. {policy}')


def detect():
    if sys.platform!='darwin':return fallback('not macOS')
    try:
        result=subprocess.run(['/usr/bin/osascript','-l','JavaScript','-e',SCRIPT],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            timeout=2,check=True)
        return parse(result.stdout)
    except (OSError,subprocess.SubprocessError,ValueError,TypeError,RecursionError):
        return fallback('no usable display report within 2 seconds')
