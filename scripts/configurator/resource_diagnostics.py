"""Bounded scene-specific file evidence, not a renderer search-path emulator.

Only generated scene requests and two known local roots are inspected. Installed
DATADIR is never inferred; log paths are reported, not opened. Metadata checks do
not decode assets and never turn a truncated/unfamiliar log into missing support.
"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import re
import stat

MAX_REQUESTS = 32
MAX_NAME = 512
REPORT_LIMIT = 16384
CONFIG_LIMIT = 65536
_TYPES = {'map': 'images', 'night_map': 'images', 'bump_map': 'images',
          'specular_map': 'images', 'cloud_map': 'images', 'marker_file': 'markers',
          'arc_file': 'arcs', 'satellite_file': 'satellites'}
_ARGUMENTS = {'-marker_file': ('sky markers', 'markers'),
              '-arc_file': ('sky arcs', 'arcs'), '-starmap': ('star catalogue', 'stars'),
              '-origin_file': ('observer path', 'origin'),
              '-dynamic_origin': ('observer path', 'origin')}


@dataclass(frozen=True)
class Request:
    role: str
    name: str
    directory: str
    source: str  # project, scene, or lookup


def _name(value):
    if (not isinstance(value, str) or not value or len(value) > MAX_NAME or
            any(not c.isprintable() or c.isspace() for c in value)):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and '..' not in path.parts and str(path) == value


def requests(view):
    """Read the generated native layout, not arbitrary imported native text."""
    body = view.body()
    if len(body) > CONFIG_LIMIT:
        raise ValueError('Generated configuration exceeds the diagnostic request bound.')
    project = {path.as_posix() for path in view.resource_paths()}
    auxiliary = set(view.auxiliary_files(active_only=True))
    result = []
    section = 'default'
    for line in body.decode('utf-8').splitlines():
        match = re.fullmatch(r'\[([a-z]+)\]', line)
        if match:
            section = match[1]
            continue
        key, separator, name = line.partition('=')
        if not separator or key not in _TYPES or not _name(name):
            continue
        source = ('project' if name in project else 'lookup' if name in ('earth.jpg', 'night.jpg')
                  else 'scene' if name in auxiliary or key in ('cloud_map', 'marker_file', 'arc_file', 'satellite_file')
                  else 'lookup')
        result.append(Request(section + ' ' + key, name, _TYPES[key], source))
    arguments = view.arguments()
    for index, argument in enumerate(arguments[:-1]):
        if argument not in _ARGUMENTS:
            continue
        name = arguments[index + 1]
        if _name(name):
            role, directory = _ARGUMENTS[argument]
            result.append(Request(role, name, directory, 'scene' if name in auxiliary else 'lookup'))
    # Resource roles remain separate even when filenames coincide.
    return tuple(dict.fromkeys(result))[:MAX_REQUESTS], len(result) > MAX_REQUESTS


def _metadata(root, relative):
    """Check file kind without opening file bytes or following child symlinks."""
    descriptors = []
    try:
        # The caller supplies a known project/work root; resolve that root once.
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            info = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                return 'symlink (not followed)'
            if not stat.S_ISDIR(info.st_mode):
                return 'not a directory'
            descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            descriptors.append(descriptor)
        info = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode):
            return 'symlink (not followed)'
        return 'regular file present' if stat.S_ISREG(info.st_mode) else 'not a regular file'
    except FileNotFoundError:
        return 'missing'
    except OSError:
        return 'unavailable (metadata could not be checked)'
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _absolute(path, work):
    # Lexical normalization only: never stat or resolve a renderer-supplied path.
    value = Path(path)
    return Path(os.path.abspath(value if value.is_absolute() else work / value))


def describe(view, rows, work, project, *, incomplete=False):
    """Return read-only, attempt-specific evidence for active generated requests."""
    try:
        selected, limited = requests(view)
        work, project = Path(work).resolve(), Path(project).resolve()
    except (OSError, RuntimeError, ValueError, TypeError, UnicodeError) as exc:
        return 'Relevant scene resources: unknown; request inspection failed (' + type(exc).__name__ + ').'
    lines = ['Relevant scene resources (metadata and filename-matched lookup evidence):',
             'Only known project/preview roots are checked. Installed DATADIR, fonts and incidental-body defaults are not inventoried.',
             'File presence is not readability/decoding, freshness, compiled support or scientific coverage. Log paths are not opened.']
    cache = {}
    for request in selected:
        name = request.name
        roots = (('preview', work), ('project', project))
        candidates = []
        for label, root in roots:
            for relative in dict.fromkeys((name, request.directory + '/' + name)):
                key = (root, relative)
                if key not in cache:
                    cache[key] = _metadata(root, relative)
                candidates.append((label, root / relative, cache[key]))
        expected = (project if request.source == 'project' else work) / name if request.source != 'lookup' else None
        expected_state = next((state for _, path, state in candidates if path == expected), None)
        matched = [(path, found) for path, found in rows
                   if path == name or path.endswith('/' + name)]
        found = tuple(dict.fromkeys(_absolute(path, work) for path, success in matched if success))
        misses = sum(not success for _, success in matched)
        lines.append('\n' + request.role + ': ' + name)
        if expected is not None:
            lines.append('  Expected ' + request.source + ' input: ' + str(expected) + ' [' + str(expected_state) + '].')
        else:
            lines.append('  Renderer lookup input; installed location is unknown until reported by this attempt.')
        if found:
            lines.append('  Reported found (filename match, not decoding): ' + '; '.join(map(str, found)))
            if expected is not None and any(path != expected for path in found):
                lines.append('  Possible shadowing/path mismatch: a reported path differs from the expected input. Verify the raw lookup context; matching names alone do not prove a role match.')
        else:
            lines.append('  No successful matching lookup retained; renderer resolution remains unknown.')
        if misses:
            lines.append('  Retained matching search misses: ' + str(misses) + ('; a later found path is normal.' if found else '; not proof that every search location failed.'))
        for label, path, state in candidates:
            if path == expected or state == 'missing':
                continue
            lines.append('  Other known ' + label + ' candidate: ' + str(path) + ' [' + state + '].')
            if state == 'regular file present' and found and path not in found:
                lines.append('    Potentially shadowed/not selected; candidate precedence is not independently verified.')
    if not selected:
        lines.append('No supported explicit file requests were identified; this is not evidence that the scene needs no resources.')
    if limited:
        lines.append('Request list limited to ' + str(MAX_REQUESTS) + ' entries; remaining resources are unknown.')
    if incomplete:
        lines.append('Lookup evidence is incomplete/truncated; omitted searches cannot establish absence or precedence.')
    lines.append('These metadata facts were sampled after this attempt. They do not bind resource bytes during rendering or monitor later file changes.')
    text = '\n'.join(lines)
    if len(text) > REPORT_LIMIT:
        text = text[:REPORT_LIMIT].rsplit('\n', 1)[0] + '\n[... relevant resource report omitted after 16384 characters ...]'
    return text
