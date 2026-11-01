"""Manual trimming of configured event JSONL; never rotate launchd text logs.

Project event writers append while holding settings.lock. Replacement shares that
lock and checks the opened file and its pathname before publishing. External
writers that ignore this lock cannot be made safe by a last-moment stat check;
stdout/stderr logs therefore remain untouched. Dry runs read a bounded snapshot
without creating a lock or temporary file and provide estimates only.
"""
from contextlib import nullcontext
import json
import math
import os
import stat
import time
import uuid

from .errors import ConfigError, StorageError

MAX_LINE = 64 * 1024
MAX_FILE = 512 * 1024 * 1024
FEATURES = {"clouds", "quake", "storm", "volcano", "norad", "eclipse"}
OUTCOMES = {"changed", "unchanged", "failed"}


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_nlink, info.st_uid, info.st_gid)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Non-finite JSON constant")


def _old_event(line, cutoff):
    value = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(value, dict):
        return False
    stamp = value.get("time")
    feature, outcome = value.get("feature"), value.get("outcome")
    return (isinstance(feature, str) and feature in FEATURES
            and isinstance(outcome, str) and outcome in OUTCOMES
            and isinstance(value.get("message"), str)
            and type(stamp) in (int, float) and math.isfinite(stamp)
            and 0 <= stamp < cutoff)


def _scan(file, size, cutoff, output=None):
    """Keep memory bounded; ambiguous JSON preserves the entire file."""
    scanned = removed = consumed = 0
    while consumed < size:
        line = file.readline(min(MAX_LINE + 1, size - consumed))
        if not line:
            raise ValueError("Log changed during inspection")
        consumed += len(line)
        scanned += 1
        if len(line) > MAX_LINE:
            raise ValueError("Oversized record; entire log preserved")
        # An incomplete final line may belong to an interrupted append. Preserve
        # it, including its exact bytes, rather than treating it as an event.
        old = _old_event(line, cutoff) if line.endswith(b"\n") else False
        if old:
            removed += 1
        elif output is not None:
            output.write(line)
    return scanned, removed


def _protected_paths(settings):
    for key in ("image", "labels", "state", "journal", "lock"):
        yield getattr(settings, key)
    for options in (settings.quake, settings.storm, settings.volcano,
                    settings.norad, settings.eclipse, settings.santa):
        for key in ("marker", "arc", "satellite", "journal"):
            if hasattr(options, key):
                yield getattr(options, key)
    yield settings.norad.satellite + ".tle"


def _candidate(fs, settings):
    path = fs.resolve(settings.log, write=True, follow_symlinks=False)
    parts = path.relative_to(fs.root).parts
    if parts[:2] != ("logs", "totalmarker") or path.suffix != ".jsonl":
        raise StorageError("Only configured logs/totalmarker/*.jsonl event logs are eligible")
    target = tuple(part.casefold() for part in path.parts)
    for protected in _protected_paths(settings):
        other = tuple(part.casefold() for part in fs.resolve(protected, write=True).parts)
        length = min(len(target), len(other))
        if target[:length] == other[:length]:
            raise StorageError("Configured event log aliases a protected runtime path")
    return path


def _row(path, status, *, scanned=0, removed=0, would_remove=0, reason=""):
    return {"path": path, "status": status, "scanned": scanned,
            "removed": removed, "would_remove": would_remove,
            "retained": scanned - removed - would_remove, "reason": reason}


def _trim_file(fs, path, cutoff, dry_run):
    relative = str(path.relative_to(fs.root))
    replaced = False
    try:
        with fs.parent(path, write=True, follow_symlinks=False) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as source:
                initial = os.fstat(source.fileno())
                if (not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1
                        or initial.st_uid != os.geteuid()):
                    return _row(relative, "skipped", reason="Log must be a non-aliased regular file owned by this user; preserved")
                if initial.st_size > MAX_FILE:
                    return _row(relative, "skipped", reason="Log exceeds the 512 MiB scan limit; preserved")
                try:
                    scanned, old = _scan(source, initial.st_size, cutoff)
                except (ValueError, UnicodeError, RecursionError, OverflowError):
                    return _row(relative, "skipped", reason="Malformed, multiline or oversized record; entire log preserved")
                if _signature(os.fstat(source.fileno())) != _signature(initial):
                    return _row(relative, "skipped", reason="Log changed during inspection; preserved")
                if dry_run or not old:
                    return _row(relative, "would_trim" if old else "unchanged",
                                scanned=scanned, would_remove=old)
                temporary = ".totalmarker-trim-" + uuid.uuid4().hex + ".tmp"
                try:
                    out_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                     | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                    with os.fdopen(out_fd, "wb") as output:
                        source.seek(0)
                        try:
                            _scan(source, initial.st_size, cutoff, output)
                        except (ValueError, UnicodeError, RecursionError, OverflowError):
                            return _row(relative, "skipped", reason="Log changed during rewrite; preserved")
                        output.flush()
                        os.fchmod(output.fileno(), stat.S_IMODE(initial.st_mode))
                        os.fsync(output.fileno())
                    # A pinned directory alone could become detached from its
                    # configured pathname. Re-open it and check that identity too.
                    with fs.parent(path, write=True, follow_symlinks=False) as (current_parent, current_name):
                        same_parent = ((os.fstat(parent).st_dev, os.fstat(parent).st_ino)
                                       == (os.fstat(current_parent).st_dev, os.fstat(current_parent).st_ino))
                        current = os.stat(current_name, dir_fd=current_parent, follow_symlinks=False)
                        if (not same_parent or _signature(current) != _signature(initial)
                                or _signature(os.fstat(source.fileno())) != _signature(initial)):
                            return _row(relative, "skipped", reason="Log identity or contents changed; preserved")
                        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                        replaced = True
                        os.fsync(parent)
                    return _row(relative, "trimmed", scanned=scanned, removed=old)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass
    except FileNotFoundError:
        return _row(relative, "missing", reason="Event log is absent")
    except StorageError:
        return _row(relative, "skipped", reason="Log path changed or became unsafe; preserved")
    except OSError:
        if replaced:
            raise StorageError("Event log replaced but directory sync failed") from None
        return _row(relative, "skipped", reason="Event log could not be safely inspected or rewritten; preserved")


def _unmanaged_logs(fs):
    try:
        with fs.parent("logs/.event-log-inventory", follow_symlinks=False) as (parent, _):
            with os.scandir(parent) as entries:
                names = sorted(entry.name for entry in entries if entry.name.endswith(".log"))
    except (FileNotFoundError, OSError, StorageError):
        return []
    return [_row("logs/" + name, "skipped",
                 reason="Text log has no trusted event timestamps or shared writer lock; preserved")
            for name in names]


def trim(fs, settings, days=30, dry_run=False, now=None):
    """Remove dated events older than days; retain unknown records conservatively."""
    if type(days) is not int or days <= 0:
        raise ConfigError("Log retention days must be a positive integer")
    now = time.time() if now is None else now
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise ConfigError("Log trim time is invalid")
    cutoff = max(0, now - days * 86400) if days <= now / 86400 else 0
    rows = []
    if settings.log:
        try:
            path = _candidate(fs, settings)
        except (OSError, StorageError):
            rows.append(_row("configured event log", "skipped",
                             reason="Configured log or protected runtime paths are unsafe; preserved"))
        else:
            # Missing logs need no lock creation, including on an unused root.
            try:
                info = fs.file_stat(path)
            except StorageError:
                rows.append(_row(str(path.relative_to(fs.root)), "skipped",
                                 reason="Event log cannot be safely inspected; preserved"))
            else:
                if info is None:
                    rows.append(_row(str(path.relative_to(fs.root)), "missing", reason="Event log is absent"))
                else:
                    with nullcontext() if dry_run else fs.lock(settings.lock):
                        rows.append(_trim_file(fs, path, cutoff, dry_run))
    rows.extend(_unmanaged_logs(fs))
    removed = sum(row["removed"] for row in rows)
    return {"outcome": "changed" if removed else "unchanged", "dry_run": dry_run,
            "days": days, "cutoff": cutoff, "scanned": sum(row["scanned"] for row in rows),
            "removed": removed, "would_remove": sum(row["would_remove"] for row in rows),
            "retained": sum(row["retained"] for row in rows), "files": rows,
            "message": "Event log trim preview; no files written" if dry_run else "Event log trim complete"}
