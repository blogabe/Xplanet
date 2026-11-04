"""Bounded output dimensions; texture-map aspect does not constrain the frame."""
import re
DEFAULT_GEOMETRY='1920x1080'
LEGACY_GEOMETRY='800x600'
MAX_PIXELS=16_777_216


def geometry(value):
    if not isinstance(value,str) or len(value)>32:raise ValueError('Use explicit WIDTHxHEIGHT.')
    match=re.fullmatch(r'([0-9]+)x([0-9]+)',value)
    if not match:raise ValueError('Use explicit WIDTHxHEIGHT without offsets.')
    width,height=map(int,match.groups())
    if not all(200<=v<=16384 for v in (width,height)) or width*height>MAX_PIXELS:
        raise ValueError('WIDTHxHEIGHT must be 200–16384 per edge and at most 16,777,216 pixels.')
    if value!=f'{width}x{height}':raise ValueError('Use canonical WIDTHxHEIGHT without leading zeros.')
    return value
