"""Public-tree privacy policy used only by offline repository tests."""
from pathlib import PurePosixPath

CLUTTER = {".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX",
           ".git", ".state", "__pycache__"}
PRIVATE_SUFFIXES = {".ini", ".toml", ".plist", ".log", ".key", ".pem"}
SOURCE_PRIVATE_SUFFIXES = {".ini", ".log", ".key", ".pem", ".pyc", ".pyo", ".pyd"}
SOURCE_PRIVATE_COMPONENTS = {name.casefold() for name in CLUTTER} | {".tmp", ".cache"}


def private_source_path(name):
    """Reject known private/runtime names, not arbitrary fixture contents."""
    parts = PurePosixPath(name).parts
    return (any(part.casefold() in SOURCE_PRIVATE_COMPONENTS or
                part.casefold().startswith(".env") or part.startswith("._")
                for part in parts) or
            PurePosixPath(name).suffix.lower() in SOURCE_PRIVATE_SUFFIXES)

def excluded_name(name):
    return (name in CLUTTER or name.startswith("._") or
            name.startswith(".env") or PurePosixPath(name).suffix.lower() in PRIVATE_SUFFIXES)

def check_source_paths(entries):
    """Keep personal config, development history and runtime outputs out."""
    allowed_config = {"config/earth.example", "config/xp.conf.example",
                      "config/xp.def.example", "config/totalmarker.example.toml"}
    runtime = ("images/", "markers/", "arcs/", "satellites/", "logs/", ".state/")
    for name, metadata in entries.items():
        if (private_source_path(name) or metadata.startswith("120000 ") or
                name.startswith(runtime) or
                (name.startswith("assets/") and
                 (not metadata.startswith(("100644 ", "100755 ")) or
                  any(excluded_name(part) for part in PurePosixPath(name).parts[1:]))) or
                (name.startswith("examples/") and name != "examples/README.md" and not name.endswith(".example.toml")) or
                (name.startswith("config/") and name not in allowed_config) or
                name.startswith("dev/") or
                (name.startswith("scripts/launchd/") and
                 not name.endswith(".plist.example"))):
            raise RuntimeError(f"unsafe source entry: {name}")
