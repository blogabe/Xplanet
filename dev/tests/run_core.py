"""Explicit stdlib test containers; never import optional UI or local scratch."""
from pathlib import Path
from contextlib import contextmanager
import os,tempfile,unittest

TEST_ROOT=Path(__file__).resolve().parent

def module_names():
    names=[]
    for directory in (TEST_ROOT,TEST_ROOT/'configurator'):
        if not directory.is_dir():raise RuntimeError('Missing core test container: '+str(directory))
        for path in sorted(directory.glob('test_*.py')):
            names.append('tests.'+'.'.join(path.relative_to(TEST_ROOT).with_suffix('').parts))
    return names

def suite(*,exclude=()):
    names=module_names();excluded=set(exclude)
    if excluded-set(names):raise ValueError('Unknown test exclusions: '+', '.join(sorted(excluded-set(names))))
    return unittest.TestLoader().loadTestsFromNames([name for name in names if name not in excluded])

@contextmanager
def isolated_environment():
    """Keep identity-sensitive fixtures outside synchronized source checkouts."""
    previous={name:os.environ.get(name) for name in ('TMPDIR','XDG_CACHE_HOME')}
    previous_temp=tempfile.tempdir
    with tempfile.TemporaryDirectory(prefix='xplanet-tests-',dir='/tmp') as directory:
        root=Path(directory).resolve();cache=root/'cache';cache.mkdir()
        try:
            os.environ['TMPDIR']=str(root);os.environ['XDG_CACHE_HOME']=str(cache)
            tempfile.tempdir=str(root)
            yield root
        finally:
            tempfile.tempdir=previous_temp
            for name,value in previous.items():
                if value is None:os.environ.pop(name,None)
                else:os.environ[name]=value

def run(factory):
    with isolated_environment():
        return unittest.TextTestRunner(verbosity=2).run(factory()).wasSuccessful()

if __name__=='__main__':
    raise SystemExit(not run(suite))
