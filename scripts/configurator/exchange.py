"""Portable generated-scene data, never an installer or arbitrary archive extractor."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import zipfile

from .png import normalize_png
from .fileio import new_directory, fingerprint
from .model import ROOT
from .workspace import open_view, renderer_path

LIMIT = 20 * 1024 * 1024
PREVIEW_LIMIT = 16 * 1024 * 1024
MAX_FILES = 14
PORTABLE_ROOT = '/xplanet-exchange/assets'
PORTABLE_RENDERER = '/xplanet-exchange/renderer'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()


def read_file(source, limit):
    path = Path(source).expanduser()
    if not path.is_absolute() or path != path.resolve() or any(not c.isprintable() for c in str(path)):
        raise ValueError('Choose an absolute regular file without symlink components.')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('Exchange input is not a bounded regular file.')
        chunks = []; count = 0
        while chunk := os.read(fd, min(65536, limit + 1 - count)):
            count += len(chunk)
            if count > limit:
                raise ValueError('Exchange input exceeds its size bound.')
            chunks.append(chunk)
        if (fingerprint(before) != fingerprint(os.fstat(fd)) or
                fingerprint(before) != fingerprint(os.stat(path, follow_symlinks=False)) or path != path.resolve()):
            raise ValueError('Exchange input changed while reading.')
        return b''.join(chunks)
    finally:
        os.close(fd)


def preview_bytes(raw):
    return normalize_png(raw,byte_limit=PREVIEW_LIMIT,dimension=4096,pixels_limit=8_388_608,decode_limit=40*1024*1024)


def scene_files(view, renderer=PORTABLE_RENDERER, asset_root=PORTABLE_ROOT):
    if any(getattr(view,field,'') for field in ('capture_id','observations_id','norad_id','eclipse_id')):
        raise ValueError('Version 1 exchange excludes frozen provider captures. Save an explicitly separate scene without them; nothing was discarded.')
    # Rebuild only recognized output: no original renderer/root paths, unrelated
    # files or imported executable syntax can enter the exchange.
    return {'xp.def': view.definition(renderer, asset_root=asset_root).encode(),
            'xp.conf': view.body(), **view.auxiliary_files()}


def publish(destination, files):
    target = Path(destination).expanduser()
    if any(not c.isprintable() for c in str(target)):
        raise ValueError('Exchange destination must not contain control characters.')
    return new_directory(target, files)


def export_scene(source, destination, *, preview=None):
    document = open_view(source)
    files = scene_files(document.view)
    if preview is not None:
        files['preview.png'] = preview_bytes(read_file(preview, PREVIEW_LIMIT))
    manifest = {'schema': 1, 'kind': 'xplanet-generated-scene',
                'origin': 'recognized-configurator-scene',
                'bundled_assets': 'references-only; recipient needs compatible Xplanet for macOS assets',
                'preview': 'illustration; scene match and rendering not verified' if preview is not None else None,
                'files': {name: {'bytes': len(raw), 'sha256': digest(raw)} for name, raw in files.items()}}
    files['exchange.json'] = encode(manifest)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name); info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, raw)
    raw = stream.getvalue()
    if len(raw) > LIMIT: raise ValueError('Exchange exceeds 20 MiB.')
    return publish(destination, [('scene.xplanet.zip', raw)])


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate exchange metadata key.')
        result[key] = value
    return result


def import_scene(source, destination, *, renderer, asset_root=ROOT):
    raw = read_file(source, LIMIT)
    try:
        # Bound central-directory allocation before ZipFile builds its index.
        # Our format uses no ZIP64, multi-disk records, prefix or ZIP comments.
        if len(raw) < 22 or raw[:4] != b'PK\x03\x04':
            raise ValueError('Not a supported scene archive.')
        signature, disk, directory_disk, local_count, count, size, offset, comment = struct.unpack('<4s4H2IH', raw[-22:])
        if (signature != b'PK\x05\x06' or disk or directory_disk or comment or
                local_count != count or not 3 <= count <= MAX_FILES or size > count * 110 or
                offset + size != len(raw) - 22):
            raise ValueError('Unsupported or oversized archive directory.')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if not 3 <= len(infos) <= MAX_FILES or len({row.filename for row in infos}) != len(infos):
                raise ValueError('Invalid exchange member count or duplicate names.')
            files = {}; total = 0
            for row in infos:
                name = row.filename; mode = row.external_attr >> 16
                if (Path(name).name != name or name in ('', '.', '..') or '\\' in name or
                        any(not c.isprintable() for c in name) or row.is_dir() or
                        stat.S_IFMT(mode) not in (0, stat.S_IFREG) or row.flag_bits & 1 or
                        row.compress_type != zipfile.ZIP_STORED or row.file_size > PREVIEW_LIMIT):
                    raise ValueError('Unsupported exchange member, path, type or compression.')
                total += row.file_size
                if total > LIMIT: raise ValueError('Exchange expands beyond 20 MiB.')
                files[name] = archive.read(row)
        manifest_raw = files.pop('exchange.json')
        if len(manifest_raw) > 16384: raise ValueError('Exchange metadata too large.')
        manifest = json.loads(manifest_raw, object_pairs_hook=unique_object)
        if (set(manifest) != {'schema', 'kind', 'origin', 'bundled_assets', 'preview', 'files'} or
                type(manifest['schema']) is not int or manifest['schema'] != 1 or
                manifest['kind'] != 'xplanet-generated-scene' or
                manifest['origin'] != 'recognized-configurator-scene' or
                manifest['bundled_assets'] != 'references-only; recipient needs compatible Xplanet for macOS assets' or
                manifest['preview'] != ('illustration; scene match and rendering not verified' if 'preview.png' in files else None) or
                manifest_raw != encode(manifest) or not isinstance(manifest['files'], dict) or
                set(manifest['files']) != set(files)):
            raise ValueError('Unsupported exchange manifest.')
        for name, payload in files.items():
            record = manifest['files'][name]
            if record != {'bytes': len(payload), 'sha256': digest(payload)} or type(record['bytes']) is not int:
                raise ValueError('Exchange integrity check failed.')
        preview = files.pop('preview.png', None)
        if preview is not None and preview_bytes(preview) != preview:
            raise ValueError('Exchange preview contains unsupported metadata.')
        # Validate privately before touching the chosen destination. Never use
        # extractall, execute definitions or follow archive-controlled paths.
        with tempfile.TemporaryDirectory(prefix='xplanet-exchange-') as temp:
            staging = new_directory(Path(temp).resolve() / 'scene', files.items())
            document = open_view(staging)
            if scene_files(document.view) != files:
                raise ValueError('Exchange is not canonical recognized scene data.')
            binary = renderer_path(renderer)
            root = Path(asset_root).expanduser()
            if (not root.is_absolute() or root != root.resolve() or not root.is_dir() or
                    any(not c.isprintable() for c in str(root)) or any(not c.isprintable() for c in str(binary))):
                raise ValueError('Choose an existing real checkout asset root.')
            imported = scene_files(document.view, binary, root)
        receipt = {'schema': 1, 'archive_sha256': digest(raw), 'activated': False,
                   'source_files': manifest['files'], 'preview': manifest['preview']}
        if preview is not None: imported['preview.png'] = preview
        imported['exchange-receipt.json'] = encode(receipt)
        return publish(destination, imported.items())
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError, RecursionError, OverflowError, NotImplementedError) as exc:
        raise ValueError('Invalid or unsupported scene exchange.') from exc


def main():
    parser = argparse.ArgumentParser(description='Exchange generated scenes as data; never execute, select or activate them.')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--export', type=Path, metavar='SAVED_SCENE')
    modes.add_argument('--import', type=Path, dest='archive', metavar='ARCHIVE')
    parser.add_argument('--destination', required=True, type=Path, help='New directory in an existing real parent')
    parser.add_argument('--preview', type=Path, help='Optional illustrative PNG for export; metadata stripped')
    parser.add_argument('--renderer', help='Existing absolute local renderer, required for import; never executed')
    args = parser.parse_args()
    if args.export and args.renderer: parser.error('--renderer is only for import')
    if args.archive and (not args.renderer or args.preview): parser.error('Import requires --renderer and does not accept --preview')
    try:
        path = export_scene(args.export, args.destination, preview=args.preview) if args.export else import_scene(args.archive, args.destination, renderer=args.renderer)
        print('Scene copy created at ' + str(path) + '. Nothing selected, executed or activated.')
        return 0
    except (OSError, ValueError) as exc:
        print('Scene exchange refused: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
