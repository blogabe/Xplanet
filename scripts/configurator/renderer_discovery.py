"""Local renderer discovery; never evaluate definitions or adopt scene metadata."""
import os
from pathlib import Path
import re
import shlex
import shutil
import stat


def executable(value):
    try:
        path = Path(value)
        return path.is_absolute() and not any(c in str(path) for c in '\r\n\0') and path.is_file() and os.access(path, os.X_OK)
    except (OSError, ValueError):
        return False


def discover(root, explicit=None):
    if explicit is not None:
        return explicit, 'Explicit renderer choice; configuration health validates it.'
    definition = Path(root) / 'config/xp.def'
    try:
        if definition.parent.is_symlink() or definition.is_symlink():
            return '', 'Project definitions use a symlink; choose the renderer explicitly. No definitions executed.'
        directory = os.open(definition.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(definition.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
    except FileNotFoundError:
        text = ''
    except OSError:
        return '', 'Cannot read project definitions; choose the renderer explicitly.'
    else:
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 256 * 1024:
                return '', 'Project definitions are not a bounded regular file; choose the renderer explicitly.'
            raw = stream.read(256 * 1024 + 1)
        try:
            if len(raw) > 256 * 1024:raise ValueError
            text = raw.decode('utf-8')
        except (ValueError, UnicodeError):
            return '', 'Project definitions cannot be read safely; choose the renderer explicitly.'
    assignments = re.findall(r'^[ \t]*(?:export[ \t]+)?XPLANET_BIN[ \t]*=(.*)$', text, re.MULTILINE)
    if assignments:
        try:
            if len(assignments) != 1:raise ValueError
            tokens = shlex.split(assignments[0], comments=True)
            if not tokens or tokens == ['']:tokens = []
            if tokens:
                if len(tokens) != 1 or '$' in tokens[0] or '`' in tokens[0]:raise ValueError
                if not executable(tokens[0]):
                    return '', 'The project-selected Xplanet is unavailable; choose a local executable. No fallback was substituted.'
                return tokens[0], 'Renderer from the literal project XPLANET_BIN setting; definitions were not executed.'
        except ValueError:
            return '', 'Project XPLANET_BIN needs shell evaluation or is ambiguous; choose the renderer explicitly. No definitions executed.'
    located = shutil.which('xplanet')
    if located and executable(located):return located, 'Renderer discovered on PATH; stock/saved scene metadata is not adopted.'
    candidates = [Path('/opt/homebrew/bin/xplanet'), Path('/usr/local/bin/xplanet')]
    home = os.environ.get('HOME')
    if home:candidates.append(Path(home) / '.homebrew/bin/xplanet')
    for candidate in candidates:
        if executable(candidate):return str(candidate), 'Renderer discovered at a standard Homebrew path; no package manager was run.'
    return '', 'No local Xplanet found. Use setup/install or choose its executable explicitly.'
