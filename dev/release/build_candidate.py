#!/usr/bin/env python3
"""Build an unpublished, fresh-history local candidate with checkout assets.

Only committed source and regular files under assets/ are exported. This does
not modify the source index, live configuration, services, or map choices.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "dev/release-staging"
OUTPUT = STAGING / "candidate-next"
CLUTTER = {".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX",
           ".git", ".state", "__pycache__"}
PRIVATE_SUFFIXES = {".ini", ".toml", ".plist", ".log", ".key", ".pem"}


def git(*args, cwd=None, **kwargs):
    return subprocess.run(("git", *args), cwd=ROOT if cwd is None else cwd,
                          check=True, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def excluded_name(name):
    return (name in CLUTTER or name.startswith("._") or
            name.startswith(".env") or Path(name).suffix.lower() in PRIVATE_SUFFIXES)


def asset_inventory(directory):
    """Yield regular asset paths and excluded paths, never following symlinks."""
    included, excluded = [], []
    for base, dirs, files in os.walk(directory, topdown=True, followlinks=False):
        for name in sorted(tuple(dirs)):
            path = Path(base) / name
            if excluded_name(name) or path.is_symlink():
                dirs.remove(name)
                excluded.append(path.relative_to(ROOT).as_posix())
        for name in sorted(files):
            path = Path(base) / name
            mode = path.lstat().st_mode
            relative = path.relative_to(ROOT).as_posix()
            if excluded_name(name) or stat.S_ISLNK(mode):
                excluded.append(relative)
            elif stat.S_ISREG(mode):
                included.append(path)
            else:
                excluded.append(relative)
    return sorted(included), sorted(excluded)


def export_committed_source(destination):
    process = subprocess.Popen(("git", "archive", "--format=tar", "HEAD"),
                               cwd=ROOT, stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if (name.is_absolute() or not name.parts or
                        any(part in {"..", ".git"} for part in name.parts)):
                    raise ValueError(f"unsafe source archive path: {member.name}")
                target = destination.joinpath(*name.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, open(target, "wb") as sink:
                        shutil.copyfileobj(source, sink)
                    target.chmod(member.mode & 0o777)
                else:
                    raise ValueError(f"nonregular source archive member: {member.name}")
    finally:
        process.stdout.close()
        if process.wait() != 0:
            raise RuntimeError("git archive failed")


def copy_asset(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(os.open(source, flags), "rb") as stream, open(destination, "xb") as sink:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError(f"asset changed type: {source}")
        while block := stream.read(1024 * 1024):
            sink.write(block)
            digest.update(block)
            size += len(block)
    if (sha256(source) != digest.hexdigest() or
            sha256(destination) != digest.hexdigest()):
        raise ValueError(f"asset changed during export: {source}")
    return {"path": source.relative_to(ROOT).as_posix(),
            "bytes": size, "sha256": digest.hexdigest()}


def tree_entries(cwd, revision):
    raw = git("ls-tree", "-r", "-z", revision, cwd=cwd,
              stdout=subprocess.PIPE).stdout
    entries = {}
    for row in raw.split(b"\0"):
        if row:
            metadata, name = row.split(b"\t", 1)
            entries[name.decode()] = metadata.decode()
    return entries


def check_source_paths(entries):
    """Keep personal config, development history and runtime outputs out."""
    allowed_config = {"config/earth.example", "config/xp.conf.example",
                      "config/xp.def.example", "config/totalmarker.example.toml"}
    runtime = ("images/", "markers/", "arcs/", "satellites/", "logs/", ".state/")
    allowed_dev = ("dev/tests/", "dev/examples/", "dev/release/")
    for name, metadata in entries.items():
        if (metadata.startswith("120000 ") or name.startswith(runtime) or
                name.startswith("assets/") or
                (name.startswith("config/") and name not in allowed_config) or
                (name.startswith("dev/") and not name.startswith(allowed_dev)) or
                (name.startswith("scripts/launchd/") and
                 not name.endswith(".plist.example"))):
            raise RuntimeError(f"unsafe source entry: {name}")


def check_candidate(source_entries, asset_records):
    """Verify the fresh checkout before publishing its local manifest."""
    entries = tree_entries(OUTPUT, "HEAD")
    if {name: entry for name, entry in entries.items()
        if not name.startswith("assets/")} != source_entries:
        raise RuntimeError("candidate committed source differs from source HEAD")
    if set(entries) - set(source_entries) != {r["path"] for r in asset_records}:
        raise RuntimeError("candidate asset index differs from copied assets")
    if git("rev-list", "--count", "HEAD", cwd=OUTPUT,
           stdout=subprocess.PIPE).stdout.strip() != b"1":
        raise RuntimeError("candidate does not have fresh one-commit history")
    if git("remote", cwd=OUTPUT, stdout=subprocess.PIPE).stdout.strip() or \
            (OUTPUT / ".git/objects/info/alternates").exists():
        raise RuntimeError("candidate has a remote or alternate object store")
    if git("status", "--porcelain", "--untracked-files=normal", cwd=OUTPUT,
           stdout=subprocess.PIPE).stdout.strip():
        raise RuntimeError("candidate checkout is not clean")
    records = []
    for name in sorted(entries):
        path = OUTPUT / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"candidate has nonregular entry: {name}")
        records.append({"path": name, "bytes": path.stat().st_size,
                        "sha256": sha256(path)})
    actual = {path.relative_to(OUTPUT).as_posix()
              for path in OUTPUT.rglob("*")
              if (path.is_file() or path.is_symlink())
              and path.relative_to(OUTPUT).parts[0] != ".git"}
    if actual != set(entries):
        raise RuntimeError("candidate checkout has unexpected files")
    by_name = {record["path"]: record for record in records}
    for record in asset_records:
        if by_name.get(record["path"]) != record or \
                sha256(ROOT / record["path"]) != record["sha256"]:
            raise RuntimeError(f"candidate asset verification failed: {record['path']}")
    return records


def test_candidate():
    """Run the exported package's offline suite with no personal Python site."""
    environment = {**os.environ, "TOTALMARKER_PYTHON": sys.executable,
                   "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run((str(OUTPUT / "scripts/xplanet.sh"), "test"),
                            cwd=OUTPUT, env=environment, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            check=False)
    log = STAGING / "candidate-next-test.log"
    log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"exported package tests failed ({result.returncode}); see {log}")
    print(f"exported package tests passed; log={log}")


def build():
    if git("status", "--porcelain", "--untracked-files=normal",
           stdout=subprocess.PIPE).stdout.strip():
        raise RuntimeError("commit or remove source changes before export")
    source_commit = git("rev-parse", "HEAD", stdout=subprocess.PIPE).stdout.decode().strip()
    source_tree = git("rev-parse", "HEAD^{tree}",
                      stdout=subprocess.PIPE).stdout.decode().strip()
    source_entries = tree_entries(ROOT, source_commit)
    check_source_paths(source_entries)
    manifest_path = STAGING / f"candidate-manifest-{source_commit[:7]}.json"
    if OUTPUT.exists() or OUTPUT.is_symlink() or manifest_path.exists():
        raise FileExistsError(f"release staging already exists: {OUTPUT} or {manifest_path}")
    if not (ROOT / "assets").is_dir() or (ROOT / "assets").is_symlink():
        raise RuntimeError("assets must be a real directory")
    included, excluded = asset_inventory(ROOT / "assets")
    if not included:
        raise RuntimeError("assets has no regular files to include")
    STAGING.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir()
    export_committed_source(OUTPUT)
    asset_records = [copy_asset(path, OUTPUT / path.relative_to(ROOT))
                     for path in included]
    git("init", "-q", "-b", "main", cwd=OUTPUT)
    git("add", "-A", cwd=OUTPUT)
    git("add", "-f", "--", "assets", cwd=OUTPUT)
    git("-c", "user.name=Local Release Candidate",
        "-c", "user.email=release-candidate@localhost",
        "-c", "core.hooksPath=/dev/null",
        "commit", "-q", "-m", "Local unpublished candidate", cwd=OUTPUT)
    records = check_candidate(source_entries, asset_records)
    test_candidate()
    # A test must not leave even Git-ignored files inside the exported package.
    if check_candidate(source_entries, asset_records) != records:
        raise RuntimeError("candidate files changed during offline tests")
    if git("rev-parse", "HEAD", stdout=subprocess.PIPE).stdout.decode().strip() != source_commit or \
            git("status", "--porcelain", "--untracked-files=normal",
                stdout=subprocess.PIPE).stdout.strip():
        raise RuntimeError("source changed during export")
    manifest = {
        "source_commit": source_commit,
        "source_tree": source_tree,
        "candidate_commit": git("rev-parse", "HEAD", cwd=OUTPUT,
                                stdout=subprocess.PIPE).stdout.decode().strip(),
        "candidate_tree": git("rev-parse", "HEAD^{tree}", cwd=OUTPUT,
                              stdout=subprocess.PIPE).stdout.decode().strip(),
        "fresh_history_commits": 1,
        "remote_count": 0,
        "files_count": len(records),
        "total_bytes": sum(r["bytes"] for r in records),
        "asset_files_count": len(asset_records),
        "asset_bytes": sum(r["bytes"] for r in asset_records),
        "asset_exclusions": excluded,
        "files": records,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"candidate={OUTPUT}\nmanifest={manifest_path}\n"
          f"assets={len(asset_records)} bytes={manifest['asset_bytes']} "
          f"excluded={excluded}")


if __name__ == "__main__":
    build()
