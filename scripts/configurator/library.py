"""Flat named scene pairs with exclusive publication and no overwrite."""
import os
from pathlib import Path
import stat

from .fileio import OwnedFiles,same_directory
from .owned_io import checkpoint
from .model import scene_prefix
from .workspace import configuration_issues,renderer_path,require_valid

MAX_ENTRIES=1000


def entries(fd):
    with os.scandir(fd) as listing:
        rows=[]
        for row in listing:
            checkpoint()
            rows.append(row.name)
            if len(rows)>MAX_ENTRIES:raise ValueError(f'Scene library exceeds {MAX_ENTRIES} entries; choose a smaller library.')
        return rows


def save_named(destination,view,renderer,*,config_bytes=None,capture=None,observations=None,astronomy=None):
    require_valid(configuration_issues(view,renderer,config_bytes,capture,observations,astronomy=astronomy))
    binary=renderer_path(renderer);target=Path(destination).expanduser()
    if not target.is_absolute() or target.suffix!='.conf' or any(c in str(target) for c in '\r\n\0'):
        raise ValueError('Choose an absolute new scene-name.conf path.')
    prefix=scene_prefix(target.stem+'.');parent=target.parent
    if parent!=parent.resolve():raise ValueError('Scene library must have no symlink components.')
    if not parent.exists():
        if not parent.parent.is_dir() or parent.parent!=parent.parent.resolve():raise ValueError('The library needs an existing parent without symlinks.')
        ancestor=os.open(parent.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            try:os.mkdir(parent.name,mode=0o700,dir_fd=ancestor)
            except FileExistsError:pass
        finally:os.close(ancestor)
    fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    reservation='.saving-'+target.stem.casefold();owned=OwnedFiles(fd);reserved=False;retained=[]
    try:
        same_directory(parent,fd)
        try:os.mkdir(reservation,mode=0o700,dir_fd=fd);reserved=os.stat(reservation,dir_fd=fd,follow_symlinks=False)
        except FileExistsError:raise ValueError('Scene is being saved or has an unfinished save; choose a new name.') from None
        existing=entries(fd)
        if any(name.casefold().startswith(prefix.casefold()) for name in existing):
            raise ValueError('Scene name or associated files already exist; choose a new name. Nothing was overwritten.')
        auxiliary={**view.auxiliary_files(),**(capture.files() if view.capture_id else {})}
        files=[(prefix+name,data) for name,data in auxiliary.items()]
        if observations is not None:files.extend(observations.files(prefix).items())
        for frozen in (astronomy or {}).values():files.extend(frozen.files(prefix).items())
        files += [(target.name,view.body(prefix)),(target.stem+'.def',view.definition(binary,asset_prefix=prefix).encode())]
        # Exclude our temporary reservation from the final entry count. Refuse
        # publication before writing files that would make browsing fail.
        if len(existing)-1+len(files)>MAX_ENTRIES:
            raise ValueError('Scene library has no room for this scene and its associated files; choose another library.')
        for name,data in files:owned.write(name,data)
        os.fsync(fd)
        same_directory(parent,fd)
        return target
    except BaseException:
        retained=owned.cleanup()
        raise
    finally:
        if reserved and not retained:
            try:
                current=os.stat(reservation,dir_fd=fd,follow_symlinks=False)
                if (current.st_dev,current.st_ino)==(reserved.st_dev,reserved.st_ino):
                    os.rmdir(reservation,dir_fd=fd);os.fsync(fd)
            except OSError:pass  # Leave an unexpected nonempty reservation for review.
        os.close(fd)


def list_scenes(library):
    directory=Path(library).expanduser()
    if directory!=directory.resolve() or not directory.is_absolute():raise ValueError('Choose a scene library without symlink components.')
    if not directory.exists():return []
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        names=set(entries(fd));result=[]
        for name in sorted(names,key=str.casefold):
            checkpoint()
            if not name.endswith('.conf'):continue
            try:scene_prefix(Path(name).stem+'.')
            except ValueError:continue
            stem=Path(name).stem
            if stem+'.def' not in names or '.saving-'+stem.casefold() in names:continue
            try:
                info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                peer=os.stat(stem+'.def',dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:continue  # A concurrently removed candidate is not a broken library.
            if stat.S_ISREG(info.st_mode) and stat.S_ISREG(peer.st_mode):result.append(directory/name)
        return result
    finally:os.close(fd)
