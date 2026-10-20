"""Contained filesystem operations; preserve internal symlink destinations."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import time
import uuid

from .errors import StorageError

# A contained path is not necessarily a TotalMarker output. Compare folded
# components so case aliases on case-insensitive filesystems cannot reach
# input/configuration trees. Both the configured alias and any symlink target
# must resolve into one of these runtime areas.
OUTPUT_PREFIXES = (("images",), ("markers",), ("arcs",), ("satellites",),
                   ("logs", "totalmarker"), (".state", "totalmarker"))


class RootFS:
    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        if not self.root.is_dir() or self.root.resolve() != self.root:
            raise StorageError("Root must be an existing directory without symlink ancestors")

    def resolve(self, path, *, write=False):
        path = Path(path)
        if ".." in path.parts:
            raise StorageError("Parent traversal is not allowed")
        candidate = path if path.is_absolute() else self.root / path
        candidate = Path(os.path.normpath(candidate))
        for _ in range(41):
            if not candidate.is_relative_to(self.root) or candidate == self.root:
                raise StorageError("Path escapes the project root")
            parts = candidate.relative_to(self.root).parts
            if write:
                folded = tuple(part.casefold() for part in parts)
                if not any(len(folded) > len(prefix) and
                           folded[:len(prefix)] == prefix
                           for prefix in OUTPUT_PREFIXES):
                    raise StorageError("Output is outside TotalMarker runtime areas")
            current = self.root
            restarted = False
            for index, part in enumerate(parts):
                current = current / part
                try:
                    mode = current.lstat().st_mode
                except FileNotFoundError:
                    break
                if stat.S_ISLNK(mode):
                    target = Path(os.readlink(current))
                    target = target if target.is_absolute() else current.parent / target
                    target = Path(os.path.normpath(target))
                    # Reject before accessing any component of an outside target.
                    if not target.is_relative_to(self.root):
                        raise StorageError("Symlink target escapes the project root")
                    candidate = target.joinpath(*parts[index + 1:])
                    restarted = True
                    break
            if not restarted:
                return candidate
        raise StorageError("Symlink loop or excessive indirection")

    @contextmanager
    def parent(self, path, *, create=False, write=False):
        path = self.resolve(path, write=write)
        parts = path.relative_to(self.root).parts
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=fd)
                os.close(fd)
                fd = next_fd
            yield fd, parts[-1]
        finally:
            os.close(fd)

    def read(self, path, limit=34 * 1024 * 1024):
        try:
            with self.parent(path) as (parent, name):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                with os.fdopen(fd, "rb") as file:
                    if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                        raise StorageError("Expected a regular file")
                    data = file.read(limit + 1)
                    if len(data) > limit:
                        raise StorageError("File exceeds the configured size limit")
                    return data
        except FileNotFoundError:
            return None
        except OSError:
            raise StorageError("Contained file read failed") from None

    def file_stat(self, path):
        try:
            with self.parent(path) as (parent, name):
                result = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISREG(result.st_mode):
                    raise StorageError("Expected a regular file")
                return result
        except FileNotFoundError:
            return None
        except OSError:
            raise StorageError("Contained file metadata read failed") from None

    def write(self, path, data, *, mtime=None):
        temporary = ".totalmarker-" + uuid.uuid4().hex + ".tmp"
        try:
            with self.parent(path, create=True, write=True) as (parent, name):
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW, 0o600, dir_fd=parent)
                try:
                    with os.fdopen(fd, "wb") as file:
                        file.write(data)
                        file.flush()
                        os.fsync(file.fileno())
                    if mtime is not None:
                        os.utime(temporary, (mtime, mtime), dir_fd=parent)
                    try:
                        if stat.S_ISLNK(os.stat(name, dir_fd=parent,
                                               follow_symlinks=False).st_mode):
                            raise StorageError("Destination changed into a symlink")
                    except FileNotFoundError:
                        pass
                    os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                    os.fsync(parent)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass
        except OSError:
            raise StorageError("Contained atomic publication failed") from None

    def unlink(self, path):
        try:
            with self.parent(path, write=True) as (parent, name):
                os.unlink(name, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            pass
        except OSError:
            raise StorageError("Contained file removal failed") from None

    def append(self, path, data):
        try:
            with self.parent(path, create=True, write=True) as (parent, name):
                fd = os.open(name, os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                             os.O_NOFOLLOW, 0o600, dir_fd=parent)
                with os.fdopen(fd, "ab") as file:
                    file.write(data)
                    file.flush()
        except OSError:
            raise StorageError("Contained log write failed") from None

    @contextmanager
    def lock(self, path, timeout=60):
        try:
            with self.parent(path, create=True, write=True) as (parent, name):
                # Some file-provider filesystems briefly report ENOENT while a
                # competing creator has already made the lock directory entry.
                # Prefer opening the stable inode; exclusive creation arbitrates
                # startup, with a bounded retry for visibility races.
                for attempt in range(25):
                    try:
                        fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW, dir_fd=parent)
                        break
                    except FileNotFoundError:
                        try:
                            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL |
                                         os.O_NOFOLLOW, 0o600, dir_fd=parent)
                            break
                        except (FileExistsError, FileNotFoundError):
                            time.sleep(0.02)
                else:
                    raise StorageError("Contained lock did not become available")
        except OSError:
            raise StorageError("Cannot open contained lock") from None
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise StorageError("Another TotalMarker job holds the lock")
                    time.sleep(0.02)
            yield
        finally:
            os.close(fd)
