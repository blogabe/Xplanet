"""Private macOS desktop lifecycle; exact argv, executable and birth identity.

Native API access is lazy. Unit tests supply a process API and never inspect or
signal host processes. The persistent flock releases on crashes; ownership is
revalidated before signaling. There is no force-kill or name-only fallback.
"""
import ctypes
from contextlib import contextmanager
import errno
import fcntl
import json
import os
from pathlib import Path
import signal
import secrets
import stat
import struct
import subprocess
import sys
import time


class IdentityError(RuntimeError):
    pass


def parse_procargs(data):
    if len(data) < 5:
        raise IdentityError("truncated process arguments")
    argc = struct.unpack_from('=i', data)[0]
    if not 1 <= argc <= 4096:
        raise IdentityError("invalid process argument count")
    end = data.find(b'\0', 4)
    if end < 0:
        raise IdentityError("missing executable argument separator")
    start = end + 1
    while start < len(data) and data[start] == 0:
        start += 1
    parts = data[start:].split(b'\0')
    if len(parts) <= argc:
        raise IdentityError("incomplete process arguments")
    return [os.fsdecode(part) for part in parts[:argc]]


class BSDInfo(ctypes.Structure):
    # sys/proc_info.h: struct proc_bsdinfo / PROC_PIDTBSDINFO (flavor 3).
    _fields_ = ([(name, ctypes.c_uint32) for name in
                 ('flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid',
                  'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
                + [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
                + [(name, ctypes.c_uint32) for name in
                   ('nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')]
                + [('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64),
                   ('start_usec', ctypes.c_uint64)])


def command_names(executables):
    # pbi_comm is a 16-byte C field. It is only an inspection prefilter;
    # executable path, argv and birth identity still establish ownership.
    names = set()
    for executable in executables:
        if executable:
            for path in (Path(executable), Path(executable).resolve()):
                name = os.fsencode(path.name)
                names.update((name[:15], name[:16]))
    return names


class MacProcesses:
    def __init__(self, executables):
        if sys.platform != 'darwin':
            raise IdentityError("desktop process identity requires macOS")
        self.commands = command_names(executables)
        self.lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                         ctypes.c_void_p, ctypes.c_int]
        self.lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.lib.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
                                    ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                    ctypes.c_void_p, ctypes.c_size_t]

    def pids(self):
        # sys/proc_info.h: PROC_UID_ONLY=4. Do not inspect protected processes
        # owned by other users merely to find this installation's display.
        size = self.lib.proc_listpids(4, os.geteuid(), None, 0)
        if size <= 0:
            raise IdentityError("could not enumerate desktop processes")
        values = (ctypes.c_int * (size // ctypes.sizeof(ctypes.c_int) + 64))()
        size = self.lib.proc_listpids(4, os.geteuid(), values, ctypes.sizeof(values))
        if size <= 0 or size >= ctypes.sizeof(values) or size % ctypes.sizeof(ctypes.c_int):
            raise IdentityError("process enumeration changed; retry")
        return [pid for pid in values[:size // ctypes.sizeof(ctypes.c_int)] if pid > 0]

    def info(self, pid):
        info = BSDInfo()
        count = self.lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        if count != ctypes.sizeof(info):
            if ctypes.get_errno() in (errno.ESRCH, errno.ENOENT):
                return None
            raise IdentityError(f"could not inspect process {pid}")
        return info

    def snapshot(self, pid):
        before = self.info(pid)
        if before is None or before.uid != os.geteuid() or before.comm not in self.commands:
            return None
        path = ctypes.create_string_buffer(4096)
        if self.lib.proc_pidpath(pid, path, len(path)) <= 0:
            raise IdentityError(f"could not identify executable for process {pid}")
        # sys/sysctl.h: CTL_KERN=1, KERN_PROCARGS2=49. Bounded kernel argv buffer.
        mib = (ctypes.c_int * 3)(1, 49, pid)
        data = ctypes.create_string_buffer(1024 * 1024)
        size = ctypes.c_size_t(len(data))
        if self.libc.sysctl(mib, 3, data, ctypes.byref(size), None, 0) != 0:
            raise IdentityError(f"could not identify arguments for process {pid}")
        after = self.info(pid)
        if after is None:
            return None
        identity = (before.pid, before.uid, before.start_sec, before.start_usec)
        if identity != (after.pid, after.uid, after.start_sec, after.start_usec):
            raise IdentityError(f"process {pid} changed during inspection; retry")
        return {'pid': pid, 'uid': before.uid,
                'start': [before.start_sec, before.start_usec],
                'executable': os.fsdecode(path.value),
                'argv': parse_procargs(data.raw[:size.value])}

    def terminate(self, pid):
        os.kill(pid, signal.SIGTERM)

    def spawn(self, argv):
        return subprocess.run(argv, check=False).returncode

    def pause(self):
        time.sleep(0.1)


def safe_open(path, flags, directory):
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        os.close(fd)
        raise IdentityError(f"unsafe desktop state file: {path}")
    return fd


def desktop_for_root(snapshot, root):
    args = snapshot.get('argv', [])
    return (snapshot.get('uid') == os.geteuid() and '-fork' in args
            and f'-searchdir={root}' in args and f'-config={root}/config/xp.conf' in args
            and not any(arg in ('-output', '-num_times') or
                        arg.startswith(('-output=', '-num_times=')) for arg in args))


@contextmanager
def state_directory(root):
    # Anchor every state operation at real directory descriptors. Checking paths
    # and opening them later would permit an ancestor symlink swap.
    descriptors = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for name in ('.state', 'xplanet'):
            try:
                os.mkdir(name, mode=0o700, dir_fd=directory)
            except FileExistsError:
                pass
            directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
            descriptors.append(directory)
            if os.fstat(directory).st_uid != os.geteuid():
                raise IdentityError("desktop state directory has another owner")
        yield directory
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def save_record(directory, snapshot):
    temporary = '.display-' + secrets.token_hex(8)
    fd = safe_open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(snapshot, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        try:
            existing = os.stat('display.json', dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.geteuid():
                raise IdentityError("desktop identity record became unsafe")
        except FileNotFoundError:
            pass
        os.replace(temporary, 'display.json', src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def operate(root, argv, restart=False, api=None, status_only=False):
    root = Path(root).resolve()
    with state_directory(root) as directory, os.fdopen(
            safe_open('display.lock', os.O_CREAT | os.O_RDWR, directory), 'r+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise IdentityError("another desktop start/restart is running; retry") from exc
        owned = None
        saved = None
        try:
            record_fd = safe_open('display.json', os.O_RDONLY, directory)
        except FileNotFoundError:
            record_fd = None
        if record_fd is not None:
            with os.fdopen(record_fd) as stream:
                if os.fstat(stream.fileno()).st_size > 65536:
                    raise IdentityError("desktop identity record is too large")
                saved = json.load(stream)
            if not isinstance(saved, dict) or not desktop_for_root(saved, root):
                raise IdentityError("invalid desktop identity record; review it before retrying")
        if api is None:
            executables = [argv[0]]
            if saved:
                executables.extend((saved.get('executable'), saved['argv'][0]))
            api = MacProcesses(executables)
        if saved:
            current = api.snapshot(saved['pid'])
            if current == saved:
                owned = saved
        # Exact argv/executable matching can adopt an existing display after an
        # upgrade, but never a preview, another checkout, or a mere name match.
        matches = []
        expected = [str(Path(argv[0]).resolve()), *argv[1:]]
        for pid in api.pids():
            current = api.snapshot(pid)
            if current and desktop_for_root(current, root):
                actual = [str(Path(current['argv'][0]).resolve()), *current['argv'][1:]]
                if actual == expected and current['executable'] == expected[0]:
                    matches.append(current)
                elif current != owned:
                    raise IdentityError("an unrecorded desktop for this checkout has different arguments or executable; inspect it before retrying")
        if owned and owned not in matches:
            matches.append(owned)
        if len(matches) > 1:
            raise IdentityError("multiple matching desktop displays; review before retrying")
        owned = matches[0] if matches else None
        if owned:
            save_record(directory, owned)
        if status_only:
            return 0, str(owned['pid']) if owned else ''
        if owned and not restart:
            return 0, 'Xplanet display already running; use restart to replace it.'
        if owned:
            if api.snapshot(owned['pid']) != owned:
                raise IdentityError("desktop process changed before stop; retry")
            try:
                api.terminate(owned['pid'])
            except ProcessLookupError:
                pass
            for _ in range(50):
                if api.snapshot(owned['pid']) != owned:
                    break
                api.pause()
            else:
                raise IdentityError("Xplanet desktop is still running after stop")
        result = api.spawn(argv)
        if result:
            return result, ''
        for _ in range(50):
            matches = []
            for pid in api.pids():
                current = api.snapshot(pid)
                if current and desktop_for_root(current, root):
                    actual = [str(Path(current['argv'][0]).resolve()), *current['argv'][1:]]
                    if actual == expected and current['executable'] == expected[0]:
                        matches.append(current)
            if len(matches) == 1:
                save_record(directory, matches[0])
                return 0, 'Xplanet display running.' if restart else 'Xplanet display started.'
            if len(matches) > 1:
                raise IdentityError("multiple desktop displays appeared; review before retrying")
            api.pause()
        raise IdentityError("Xplanet returned success but its desktop process could not be verified")


def main():
    if len(sys.argv) < 5 or sys.argv[2] not in ('start', 'restart', 'status'):
        raise IdentityError("expected ROOT start|restart|status EXECUTABLE ARGS...")
    result, message = operate(sys.argv[1], sys.argv[3:], sys.argv[2] == 'restart', status_only=sys.argv[2] == 'status')
    if message and (sys.argv[2] == 'status' or sys.stdout.isatty()):
        print(message)
    return result


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (IdentityError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'xplanet.sh: {exc}', file=sys.stderr)
        raise SystemExit(2)
