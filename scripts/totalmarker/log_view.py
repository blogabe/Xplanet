"""Read a finite text-log snapshot; collapse only complete known resize notices."""
import codecs
import os
import stat

from .errors import StorageError


ADVICE = b"For better performance, all image maps should be the same size as the day map\n"
NOTICES = {b"Warning: Resizing " + kind + b" map\n": kind.decode("ascii")
           for kind in (b"night", b"bump", b"specular", b"cloud")}
CHUNK = 64 * 1024


def _display(data, output, decoder=None, *, final=False):
    # Invalid bytes and terminal controls must not hide another diagnostic.
    text = (decoder.decode(data, final=final) if decoder is not None
            else data.decode("utf-8", errors="backslashreplace"))
    output.write("".join(char if char.isprintable() or char in "\n\t"
                         else f"\\x{ord(char):02x}" for char in text))


def _scan(source, size, output):
    decoder = codecs.getincrementaldecoder("utf-8")(errors="backslashreplace")
    remaining = size
    pending = None
    line_start = True
    counts = {}
    last = b""
    while remaining:
        line = source.readline(min(remaining, CHUNK))
        if not line:
            break
        remaining -= len(line)
        last = line
        if pending is not None:
            if line == ADVICE:
                counts[pending] = counts.get(pending, 0) + 1
                if counts[pending] == 1:
                    _display(pending + line, output, decoder)
                pending = None
                line_start = True
                continue
            _display(pending, output, decoder)
            pending = None
        if line_start and line in NOTICES:
            pending = line
        else:
            _display(line, output, decoder)
        line_start = line.endswith(b"\n")
    if pending is not None:
        _display(pending, output, decoder)
    _display(b"", output, decoder, final=True)
    if counts:
        if last and not last.endswith(b"\n"):
            output.write("\n")
        output.write("\nResize notices (exact two-line matches; first shown above):\n")
        for notice, count in counts.items():
            output.write(f"  {NOTICES[notice]}: {count} occurrence(s), {count - 1} repeat(s) hidden\n")
    return remaining


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def view(fs, path, output, errors):
    """Return 1 if the snapshot changed while read, otherwise 0; never lock/write."""
    try:
        with fs.parent(path, follow_symlinks=False) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                os.close(fd)
                raise StorageError("Log view requires a regular file")
            with os.fdopen(fd, "rb") as source:
                short = _scan(source, before.st_size, output)
                after = os.fstat(source.fileno())
                try:
                    current = fs.file_stat(path)
                except (OSError, StorageError):
                    current = None
                changed = (short or _identity(before) != _identity(after)
                           or current is None or _identity(before) != _identity(current))
    except BrokenPipeError:
        # The CLI handles a reader closing stdout; it is not a file-read failure.
        raise
    except FileNotFoundError:
        raise StorageError("Log file not found; log view creates nothing") from None
    except OSError:
        raise StorageError("Could not read log file") from None
    if changed:
        errors.write("Log changed while being read; this view may be incomplete. Run log-view again.\n")
        return 1
    return 0
