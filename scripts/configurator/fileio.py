"""Exclusive scene writes and conservative cleanup of unchanged owned files."""
import hashlib,os,stat
from .owned_io import checkpoint


def fingerprint(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def same_directory(path,fd):
    """Refuse a moved/replaced destination without following a replacement link."""
    from pathlib import Path
    path=Path(path)
    try:
        held=os.fstat(fd);current=os.stat(path,follow_symlinks=False)
        valid=(path==path.resolve() and stat.S_ISDIR(current.st_mode) and
               (held.st_dev,held.st_ino)==(current.st_dev,current.st_ino))
    except (OSError,RuntimeError):valid=False
    if not valid:raise ValueError('Scene directory changed or moved; reopen before retrying.')


class OwnedFiles:
    def __init__(self,directory_fd):
        self.directory_fd=directory_fd
        self.created={}
        self.expected={}

    def write(self,name,data):
        expected=(len(data),hashlib.sha256(data).digest())
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.directory_fd)
        with os.fdopen(fd,'wb',buffering=0) as stream:
            self.created[name]=fingerprint(os.fstat(fd))
            self.expected[name]=expected
            try:
                written=0;sha=hashlib.sha256()
                for offset in range(0,len(data),65536):
                    checkpoint()
                    chunk=data[offset:offset+65536]
                    remaining=memoryview(chunk)
                    while remaining:
                        checkpoint();count=stream.write(remaining)
                        if not count:raise OSError('Scene write made incomplete progress.')
                        written+=count;sha.update(remaining[:count]);remaining=remaining[count:]
                stream.flush();os.fsync(stream.fileno())
            finally:
                self.created[name]=fingerprint(os.fstat(stream.fileno()))
                self.expected[name]=(written,sha.digest())

    def cleanup(self):
        retained=[]
        for name,expected in reversed(list(self.created.items())):
            try:
                if name not in self.expected:
                    retained.append(name);continue
                actual=os.stat(name,dir_fd=self.directory_fd,follow_symlinks=False)
                if fingerprint(actual)!=expected:
                    retained.append(name)
                else:
                    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.directory_fd)
                    try:
                        before=os.fstat(fd);size,digest=self.expected[name];sha=hashlib.sha256();count=0
                        if fingerprint(before)!=expected or not stat.S_ISREG(before.st_mode) or before.st_size!=size:
                            retained.append(name);continue
                        while chunk:=os.read(fd,65536):
                            count+=len(chunk)
                            if count>size:break
                            sha.update(chunk)
                        if (count!=size or sha.digest()!=digest or fingerprint(os.fstat(fd))!=expected or
                                fingerprint(os.stat(name,dir_fd=self.directory_fd,follow_symlinks=False))!=expected):
                            retained.append(name);continue
                        os.unlink(name,dir_fd=self.directory_fd)
                    finally:os.close(fd)
            except FileNotFoundError:pass
            except OSError:retained.append(name)
        return retained


def new_directory(destination,files):
    """Exclusive private data snapshot; no overwrite or execution."""
    from pathlib import Path
    target=Path(destination).expanduser();files=tuple(files)
    if not target.is_absolute() or target.name in ('','.','..'):
        raise ValueError('Choose an absolute path to a new directory in an existing parent.')
    if any(c in str(target) for c in '\r\n\0'):raise ValueError('The destination must not contain control characters.')
    parent=target.parent
    if parent!=parent.resolve() or not parent.is_dir():raise ValueError('The parent must be an existing directory without symlink components.')
    if not files or len(files)>64 or len({name for name,_ in files})!=len(files):raise ValueError('Invalid native snapshot file set.')
    if any(Path(name).name!=name or name in ('','.','..') or not isinstance(data,bytes) for name,data in files):raise ValueError('Native snapshot names must be contained files.')
    parent_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);directory_fd=None;owned=None
    try:
        same_directory(parent,parent_fd)
        try:os.mkdir(target.name,mode=0o700,dir_fd=parent_fd)
        except FileExistsError:raise ValueError('Destination already exists; choose a new directory. Nothing was overwritten.') from None
        directory_fd=os.open(target.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent_fd);owned=OwnedFiles(directory_fd)
        for name,data in files:owned.write(name,data)
        os.fsync(directory_fd)
        same_directory(parent,parent_fd);same_directory(target,directory_fd)
        return target
    except BaseException:
        if directory_fd is not None:
            if owned is not None:owned.cleanup()
            try:
                current=os.stat(target.name,dir_fd=parent_fd,follow_symlinks=False);held=os.fstat(directory_fd)
                if (current.st_dev,current.st_ino)==(held.st_dev,held.st_ino):os.rmdir(target.name,dir_fd=parent_fd)
            except OSError:pass
        raise
    finally:
        if directory_fd is not None:os.close(directory_fd)
        os.close(parent_fd)
