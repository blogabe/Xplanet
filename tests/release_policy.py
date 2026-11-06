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
                (name.startswith(("maps/", "assets/")) and
                 (not metadata.startswith(("100644 ", "100755 ")) or
                  any(excluded_name(part) for part in PurePosixPath(name).parts[1:]))) or
                (name.startswith("examples/") and name != "examples/README.md" and not name.endswith(".example.toml")) or
                (name.startswith("config/") and name not in allowed_config) or
                name.startswith("dev/") or
                (name.startswith("scripts/launchd/") and
                 not name.endswith(".plist.example"))):
            raise RuntimeError(f"unsafe source entry: {name}")


TEXT_SUFFIXES={'.py','.zsh','.sh','.md','.txt','.toml','.xml','.conf','.def','.example','.json','.yml','.yaml','.tsv','.html','.origin','.dat','.geojson'}
TEXT_LIMIT=5*1024*1024
TEXT_TOTAL_LIMIT=64*1024*1024
BINARY_LIMIT=5*1024*1024
BINARY_TOTAL_LIMIT=64*1024*1024

def index_text(root):
    """Read bounded text blobs by immutable index identities, with no filters."""
    import subprocess
    raw=subprocess.check_output(['git','ls-files','--stage','-z'],cwd=root)
    rows={};text=[];binary=[]
    for row in raw.split(b'\0'):
        if not row:continue
        metadata,name=row.split(b'\t',1);name=name.decode();mode,identity,stage=metadata.decode().split()
        if stage!='0':raise RuntimeError('Unmerged index entry: '+name)
        rows[name]=metadata.decode()
        path=PurePosixPath(name)
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {'LICENSE','.gitignore','.gitattributes','run-totalmarker','run-configurator'}:text.append((name,identity))
        elif not name.startswith(('maps/','assets/')):binary.append((name,identity))
    check_source_paths(rows)
    # Binary fixtures are not decoded by the identifier scan. Bound their indexed
    # sizes separately; shipped imagery has its own regular-file/asset checks.
    if binary:
        request=''.join(identity+'\n' for _,identity in binary).encode()
        checked=subprocess.check_output(['git','cat-file','--batch-check'],cwd=root,input=request).splitlines()
        sizes=[int(line.split()[2]) for line in checked]
        if any(size>BINARY_LIMIT for size in sizes) or sum(sizes)>BINARY_TOTAL_LIMIT:
            raise RuntimeError('Indexed binary source/fixtures exceed the reviewed size budget')
    if not text:return []
    request=''.join(identity+'\n' for _,identity in text).encode()
    checked=subprocess.check_output(['git','cat-file','--batch-check'],cwd=root,input=request).splitlines()
    sizes=[int(line.split()[2]) for line in checked]
    if any(size>TEXT_LIMIT for size in sizes) or sum(sizes)>TEXT_TOTAL_LIMIT:raise RuntimeError('Indexed text exceeds the reviewed privacy-scan budget')
    raw=subprocess.check_output(['git','cat-file','--batch'],cwd=root,input=request)
    import io
    stream=io.BytesIO(raw);result=[]
    for (name,identity),size in zip(text,sizes):
        header=stream.readline().decode().strip().split()
        if header!=[identity,'blob',str(size)]:raise RuntimeError('Unexpected indexed text object')
        data=stream.read(size)
        if len(data)!=size or stream.read(1)!=b'\n':raise RuntimeError('Incomplete indexed text object')
        result.append((name,data))
    return result
