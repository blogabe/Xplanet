"""Read-only native review; exact snapshot copies only for recognized scenes."""
from dataclasses import dataclass,field
import hashlib,os,re,stat
from pathlib import Path
from .fileio import fingerprint,new_directory
from .owned_io import checkpoint
from .workspace import open_view,read_bounded

TEXT_LIMIT=256*1024


def display(text):
    """Keep printable text while escaping terminal controls; original bytes stay intact."""
    return ''.join(c if c.isprintable() else ascii(c)[1:-1] for c in text)


@dataclass(frozen=True)
class NativeReview:
    source:Path
    files:tuple=field(repr=False)
    recognized:bool=False
    reason:str='Custom/unsupported native content is read-only; no edit, preview or copy is performed.'

    def sections(self):
        lines=['Read-only snapshot of '+display(str(self.source)),
               'Source files are never executed or rewritten. The current editor draft is unchanged.',self.reason]
        for name,data in self.files:
            lines.append(f'{display(name)}: {len(data)} bytes; SHA-256 {hashlib.sha256(data).hexdigest()}')
            if not name.endswith(('.def','.conf')):continue
            try:text=data.decode('utf-8')
            except UnicodeError:
                lines.append('Non-UTF-8 source: no interpretation or conversion.');continue
            rows=text.splitlines();assignments={}
            for row in rows:
                match=re.match(r'\s*([A-Za-z][A-Za-z0-9_]{0,79})\s*=',row)
                if match:assignments[match[1]]=assignments.get(match[1],0)+1
            duplicates=sorted(key for key,count in assignments.items() if count>1)
            lines.append(f'{len(rows)} lines; {sum(row.lstrip().startswith("#") for row in rows)} comment lines; repeated assignments: '+((', '.join(duplicates[:20])+(' … ['+str(len(duplicates)-20)+' more]' if len(duplicates)>20 else '')) or 'none')+'.')
            lines.append('First 30 lines (terminal controls escaped; bytes retained unchanged):\n'+'\n'.join(display(row[:500])+(' … [display truncated; original bytes retained]' if len(row)>500 else '') for row in rows[:30]))
        if not self.recognized:lines.append('No complete recognized asset association: copying or editing is declined. Unknown content/order/comments/duplicates are not discarded or rewritten.')
        else:lines.append('An unchanged copy preserves every recognized native/associated file byte, original filenames and version. It is a captured snapshot, not a watcher; no activation or settings conversion.')
        return lines


def inspect_native(source):
    selected=Path(source).expanduser()
    if not selected.is_absolute() or any(c in str(selected) for c in '\r\n\0'):raise ValueError('Choose an absolute native .conf/.def path or scene directory.')
    if not selected.exists():raise ValueError('Selected native source does not exist; nothing was read or changed.')
    try:
        doc=open_view(selected)
        directory=selected.parent if doc.named_source else selected
        with os.scandir(directory) as listing:
            actual=set()
            for entry in listing:
                checkpoint()
                actual.add(entry.name)
                if len(actual)>10000:raise ValueError('Source directory is too large for exact filename review.')
        if not {name for name,_ in doc.native_files}<=actual:
            return NativeReview(selected,doc.native_files,False,'Scene syntax is recognized, but exact filename casing/association is ambiguous. Review only; nothing is renamed.')
        return NativeReview(selected,doc.native_files,True,'Recognized complete generated scene; a byte-identical snapshot copy is available. Save-as-new in the editor remains a separate deliberate conversion.')
    except (ValueError,FileNotFoundError):pass
    directory=selected if selected.is_dir() else selected.parent
    if directory!=directory.resolve() or not directory.is_dir():raise ValueError('Native review requires a directory without symlink components.')
    if selected.is_dir():candidates=('xp.def','xp.conf')
    elif selected.suffix in ('.conf','.def'):candidates=(selected.stem+'.def',selected.stem+'.conf')
    else:raise ValueError('Choose a native .conf or .def file, not an arbitrary file type.')
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);opened=[];files=[]
    try:
        for name in candidates:
            checkpoint()
            try:child=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            except FileNotFoundError:continue
            info=os.fstat(child);opened.append((name,child,info))
            if not stat.S_ISREG(info.st_mode) or info.st_size>TEXT_LIMIT:raise ValueError('Custom native review is limited to regular files up to 256 KiB each.')
            raw=read_bounded(child,TEXT_LIMIT)
            if len(raw)>TEXT_LIMIT:raise ValueError('Native file exceeds its review bound.')
            files.append((name,raw))
        if not files:raise ValueError('No matching native files found; nothing was changed.')
        for name,child,before in opened:
            if any(fingerprint(after)!=fingerprint(before) for after in (os.fstat(child),os.stat(name,dir_fd=fd,follow_symlinks=False))):
                raise ValueError('Native files changed during review; retry after the edit completes.')
        return NativeReview(selected,tuple(files))
    finally:
        for _,child,_ in opened:os.close(child)
        os.close(fd)


def copy_unchanged(review,destination):
    if not isinstance(review,NativeReview) or not review.recognized:raise ValueError('Unsupported native content remains read-only; no copy or conversion was made.')
    return new_directory(destination,review.files)
