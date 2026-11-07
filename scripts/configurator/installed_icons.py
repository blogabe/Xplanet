"""Explicit, offline, new-file-only copies from a selected Xplanet installation.

No discovery, producer configuration, scene activation or renderer invocation.
PNG bytes and the installed images/README are preserved, not relicensed.
"""
import argparse
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from .astronomy_capture import ICON_LIMIT, normalize_icon
from .fileio import fingerprint, native_error

ICONS = ('iss', 'hubble', 'shuttle')
README_LIMIT = 64 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


class IconImportError(ValueError):
    pass


class Directory:
    """Pin every directory component; relative operations never follow links."""
    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.chain = []

    def __enter__(self):
        if (not self.path.is_absolute() or '..' in self.path.parts or
                any(not c.isprintable() for c in str(self.path))):
            raise IconImportError('Choose absolute physical directories without parent traversal or controls.')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            self.chain.append(('/', os.open('/', flags)))
            for part in self.path.parts[1:]:
                self.chain.append((part, os.open(part, flags, dir_fd=self.fd)))
            self.verify()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    @property
    def fd(self):
        return self.chain[-1][1]

    def verify(self):
        for (_, parent), (name, child) in zip(self.chain, self.chain[1:]):
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if identity(current) != identity(os.fstat(child)) or not stat.S_ISDIR(current.st_mode):
                raise IconImportError('A selected directory changed or moved; inspect the paths before retrying.')

    def __exit__(self, *unused):
        for _, fd in reversed(self.chain):
            os.close(fd)
        self.chain.clear()

    def read(self, name, limit):
        self.verify()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
                raise IconImportError('An installed input is not a nonempty bounded regular file: ' + name)
            chunks = []; count = 0
            while chunk := os.read(fd, min(65536, limit + 1 - count)):
                chunks.append(chunk); count += len(chunk)
                if count > limit:
                    raise IconImportError('Installed input grew beyond its bound: ' + name)
            self.verify()
            if (fingerprint(before) != fingerprint(os.fstat(fd)) or
                    fingerprint(before) != fingerprint(os.stat(name, dir_fd=self.fd, follow_symlinks=False))):
                raise IconImportError('Installed input changed while reading: ' + name)
            return b''.join(chunks), fingerprint(before)
        finally:
            os.close(fd)


def selected_icons(values):
    values = tuple(values)
    if (not values or len(values) > len(ICONS) or
            any(value not in ICONS for value in values) or len(set(values)) != len(values)):
        raise IconImportError('Select each of iss, hubble or shuttle at most once; select at least one.')
    return tuple(name for name in ICONS if name in values)


def output_names(icon):
    return icon + '.png', icon + '.png.source-readme.txt', icon + '.png.import.json'


@dataclass(frozen=True)
class PreparedIcon:
    name: str
    raw: bytes
    readme: bytes
    receipt: bytes

    def files(self):
        png, readme, receipt = output_names(self.name)
        # Publish attribution/receipt before the image, even on an interrupted run.
        return ((readme, self.readme), (receipt, self.receipt), (png, self.raw))


def prepare(source, names):
    readme, readme_stamp = source.read('README', README_LIMIT)
    try:
        text = readme.decode('utf-8')
    except UnicodeError:
        raise IconImportError('Installed images/README must be UTF-8 attribution text.') from None
    if any(not c.isprintable() and c not in '\r\n\t' for c in text):
        raise IconImportError('Installed images/README contains unsupported controls.')
    result = []; stamps = {'README': readme_stamp}
    for name in names:
        filename = name + '.png'
        if filename not in text:
            raise IconImportError('Installed images/README does not identify ' + filename + '; attribution is required.')
        raw, stamps[filename] = source.read(filename, ICON_LIMIT)
        normalized = normalize_icon(raw)  # Validate bounded pixels without rewriting original metadata.
        receipt = {'schema': 1, 'kind': 'installed-xplanet-satellite-icon',
                   'source': 'images/' + filename, 'bytes': len(raw), 'sha256': digest(raw),
                   'normalized_sha256': digest(normalized), 'copied_bytes_unchanged': True,
                   'attribution': {'source': 'images/README', 'file': output_names(name)[1],
                                   'bytes': len(readme), 'sha256': digest(readme)},
                   'authorship_verified': False,
                   'terms': 'Original upstream terms apply; this copy does not relicense the image.'}
        encoded = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode('ascii')
        result.append(PreparedIcon(name, raw, readme, encoded))
    return tuple(result), stamps


def verify_sources(source, stamps):
    source.verify()
    for name, expected in stamps.items():
        if fingerprint(os.stat(name, dir_fd=source.fd, follow_symlinks=False)) != expected:
            raise IconImportError('Installed input changed; preview again before importing: ' + name)


def require_absent(destination, files):
    destination.verify()
    for name, _ in files:
        try:
            os.stat(name, dir_fd=destination.fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        raise IconImportError('Destination already exists: images/' + name + '. Nothing was overwritten.')


def verify_copy(destination, name, fd, raw):
    """Check the pinned new file and its name, never following a replacement."""
    destination.verify()
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size != len(raw):
        raise IconImportError('New destination has unexpected size or type: images/' + name)
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []; count = 0
    while chunk := os.read(fd, min(65536, len(raw) + 1 - count)):
        chunks.append(chunk); count += len(chunk)
        if count > len(raw):
            break
    if (b''.join(chunks) != raw or fingerprint(before) != fingerprint(os.fstat(fd)) or
            fingerprint(before) != fingerprint(os.stat(name, dir_fd=destination.fd, follow_symlinks=False))):
        raise IconImportError('New destination changed during import: images/' + name)
    destination.verify()


def publish(destination, files, verify):
    """Create only absent names and write validated memory via held descriptors.

    There is no staging pathname to substitute. This is not a crash-atomic file
    or batch transaction: any newly created, possibly incomplete files remain
    on interruption and are reported. Existing destination names are never
    opened for writing, replaced or removed, even during error handling.
    """
    require_absent(destination, files)
    verify()
    created = []
    try:
        for name, raw in files:
            destination.verify(); verify()
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=destination.fd)
            created.append((name, fd, raw))
            # Refuse a moved directory before writing into its pinned descriptor.
            destination.verify()
            remaining = memoryview(raw)
            while remaining:
                count = os.write(fd, remaining)
                if not count:
                    raise OSError('Incomplete icon write.')
                remaining = remaining[count:]
            os.fsync(fd)
            verify_copy(destination, name, fd, raw)
        os.fsync(destination.fd)
        destination.verify(); verify()
        for name, fd, raw in created:
            verify_copy(destination, name, fd, raw)
        return ['images/' + name for name, _, _ in created]
    except BaseException as exc:
        if created:
            names = ', '.join('images/' + name for name, _, _ in created)
            raise IconImportError('Import interrupted. New files already created and retained (possibly incomplete or changed): ' +
                                  names + '. Inspect them before retrying. Cause: ' + native_error(exc)) from exc
        raise
    finally:
        for _, fd, _ in created:
            os.close(fd)


def import_icons(resource_root, project_root, icons, *, apply=False):
    """Default is a read-only preview. Both roots and their images dirs must exist."""
    names = selected_icons(icons)
    with ExitStack() as stack:
        source = stack.enter_context(Directory(Path(resource_root).expanduser() / 'images'))
        destination = stack.enter_context(Directory(Path(project_root).expanduser() / 'images'))
        if identity(os.fstat(source.fd)) == identity(os.fstat(destination.fd)):
            raise IconImportError('Source and destination images directories must differ.')
        prepared, stamps = prepare(source, names)
        files = tuple(file for icon in prepared for file in icon.files())
        require_absent(destination, files)
        verify_sources(source, stamps)
        created = publish(destination, files, lambda: verify_sources(source, stamps)) if apply else []
        return {'mode': 'imported' if apply else 'preview',
                'icons': [{'name': icon.name, 'bytes': len(icon.raw), 'sha256': digest(icon.raw),
                           'files': ['images/' + name for name, _ in icon.files()]} for icon in prepared],
                'created': created}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Preview or explicitly import installed ISS/Hubble/Shuttle icons, offline and new-file-only.')
    parser.add_argument('--resource-root', required=True, type=Path, help='Explicit physical installed Xplanet data directory (contains images/)')
    parser.add_argument('--project-root', required=True, type=Path, help='Explicit physical destination project directory (existing images/)')
    parser.add_argument('--icon', action='append', choices=ICONS, required=True, help='Select one icon; repeat for multiple icons')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Read-only preview (the default)')
    mode.add_argument('--import', dest='apply', action='store_true', help='Explicitly create new images and attribution receipts')
    parser.add_argument('--json', action='store_true', help='Print the result as JSON')
    args = parser.parse_args(argv)
    try:
        result = import_icons(args.resource_root, args.project_root, args.icon, apply=args.apply)
    except (OSError, ValueError, RuntimeError) as exc:
        print('Satellite icon import refused: ' + native_error(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print('Imported new files.' if args.apply else 'Read-only preview; no files created. Repeat with --import to create them.')
        for icon in result['icons']:
            print(icon['name'] + ': ' + str(icon['bytes']) + ' bytes; SHA-256 ' + icon['sha256'])
            for name in icon['files']:
                print('  ' + name)
        print('Producer settings, scenes, jobs and desktop are unchanged. Original upstream terms apply.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
