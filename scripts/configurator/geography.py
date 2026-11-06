"""Bounded surface-coordinate lists, not a general native annotation importer."""
import math
import re

COLORS = ('white', 'yellow', 'cyan', 'red', 'green')
PLACE_FILE = 'places.markers'
ROUTE_FILE = 'routes.arcs'
HEADERS = {PLACE_FILE:b'# Xplanet configurator surface places v1\n',
           ROUTE_FILE:b'# Xplanet configurator surface routes v1\n'}
NUMBER = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
PLACE = re.compile(rf'[ \t]*({NUMBER})[ \t]+({NUMBER})[ \t]+"([^"\\]*)"[ \t]*')
ROUTE = re.compile(rf'[ \t]*({NUMBER})[ \t]+({NUMBER})[ \t]+({NUMBER})[ \t]+({NUMBER})[ \t]*')


def validate_rows(text, places):
    if not isinstance(text,str) or len(text.encode('utf-8'))>8192:
        raise ValueError('Keep each geographic list within 8 KiB.')
    if len(text.split('\n'))>33:
        raise ValueError('Use at most 32 geographic rows (plus an optional trailing newline).')
    count=0
    for index,line in enumerate(text.split('\n'),1):
        if any(ord(c)<32 and c!='\t' for c in line) or len(line.encode('utf-8'))>200:
            raise ValueError(f'Row {index}: use a printable line of at most 200 UTF-8 bytes.')
        if not line.strip():continue
        match=(PLACE if places else ROUTE).fullmatch(line)
        if not match:
            syntax='latitude longitude "label"' if places else 'latitude1 longitude1 latitude2 longitude2'
            raise ValueError(f'Row {index}: use {syntax}; no extra native options or comments.')
        coordinates=match.groups()[:2 if places else 4]
        for offset,token in enumerate(coordinates):
            value=float(token);bound=90 if offset%2==0 else 180
            if not math.isfinite(value) or not -bound<=value<=bound:
                raise ValueError(f'Row {index}: latitude must be within ±90 and longitude within ±180 degrees.')
        if places:
            label=match.group(3)
            if not label or not label.isprintable() or len(label.encode('utf-8'))>80:
                raise ValueError(f'Row {index}: use a nonempty printable label of at most 80 UTF-8 bytes.')
        count+=1
    if count>32:raise ValueError('Use at most 32 geographic rows.')
    return count


def read_rows(data, name):
    if data is None:return ''
    if not data.startswith(HEADERS[name]):raise ValueError('Unrecognized geographic file header.')
    text=data[len(HEADERS[name]):].decode('utf-8')
    validate_rows(text,name==PLACE_FILE)
    return text
