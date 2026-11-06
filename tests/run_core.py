"""Explicit stdlib test containers; never import optional UI or local scratch."""
from pathlib import Path
from contextlib import contextmanager
import os,shutil,tempfile,unittest

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

OPTIONAL_EVIDENCE_SKIPS = {
    'tests.test_norad.NoradTests.test_saved_live_group_response_skips_soyuz_without_publishing_empty_pair',
    'tests.test_norad.NoradTests.test_saved_live_group_response_preserves_explicit_iss_with_warning',
}

ZSH_BOUNDARY_SKIPS = {
    'tests.configurator.test_configurator.LauncherTests.test_help_and_noninteractive_config_need_no_dependencies_or_setup': 'absolute',
    'tests.configurator.test_configurator.LauncherTests.test_configurator_helper_propagates_result_without_parsing_output': 'absolute',
    'tests.configurator.test_binary_diagnostics.BinaryDiagnosticTests.test_shell_explicit_renderer_and_missing_configuration_are_isolated': 'path',
    'tests.configurator.test_binary_diagnostics.BinaryDiagnosticTests.test_selected_resolution_is_authoritative_and_invalid_selector_has_no_path_fallback': 'path',
    'tests.configurator.test_binary_diagnostics.BinaryDiagnosticTests.test_shell_help_needs_no_interpreter_config_or_evidence': 'path',
}

def unexpected_skips(result, *, portable=False):
    allowed=set(OPTIONAL_EVIDENCE_SKIPS)
    if portable:
        missing={'absolute':not Path('/bin/zsh').exists(),'path':shutil.which('zsh') is None}
        allowed.update(name for name,kind in ZSH_BOUNDARY_SKIPS.items() if missing[kind])
    return [(test.id(),reason) for test,reason in result.skipped if test.id() not in allowed]

def run(factory, *, portable=False):
    with isolated_environment():
        result=unittest.TextTestRunner(verbosity=2).run(factory())
        unexpected=unexpected_skips(result,portable=portable)
        for name,reason in unexpected:print('Unexpected skipped required check: '+name+' — '+reason,file=__import__('sys').stderr)
        return result.wasSuccessful() and not unexpected

if __name__=='__main__':
    raise SystemExit(not run(suite))
