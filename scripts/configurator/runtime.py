"""Explicit, isolated dependency preparation; no provider/package migration."""
import hashlib
import os
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import subprocess
import sys
import venv


def lock_digest(root):
    return hashlib.sha256((root / 'scripts/configurator/requirements.txt').read_bytes()).hexdigest()


def ready(root):
    try:
        locations=[root/'.state',root/'.state/configurator',root/'.state/configurator/venv']
        if any(path.is_symlink() for path in locations) or not all(path.is_dir() for path in locations):return False
        if Path(sys.prefix).resolve()!=locations[-1].resolve():return False
        if (root / '.state/configurator/lock.sha256').is_symlink():return False
        if (root / '.state/configurator/lock.sha256').read_text().strip() != lock_digest(root):
            return False
        for line in (root / 'scripts/configurator/requirements.txt').read_text().splitlines():
            if line and not line.startswith('#'):
                name, requirement = line.split('==', 1)
                if version(name) != requirement.split()[0]:
                    return False
        return sys.prefix != sys.base_prefix
    except (OSError,ValueError,RuntimeError,PackageNotFoundError):
        return False


def prepare(root):
    state = root / '.state'
    location = state / 'configurator'
    for path in (state, location):
        if path.is_symlink():
            raise ValueError(f'Refusing symlink runtime directory: {path}')
        path.mkdir(mode=0o700, exist_ok=True)
    marker=location/'lock.sha256'
    if marker.is_symlink():raise ValueError('Refusing symlink runtime lock marker.')
    environment = location / 'venv'
    # An existing environment is not silently replaced, repointed or repaired.
    if environment.exists() or environment.is_symlink():
        raise ValueError('Configurator environment already exists. Keep it or move only .state/configurator/venv aside before explicit preparation. Preserve .state/configurator/drafts.')
    print(f'Creating an isolated configurator environment using {sys.executable}.', flush=True)
    print(f'Downloading pinned dependencies from PyPI into {environment}.', flush=True)
    environment.mkdir(mode=0o700)
    venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(environment / 'bin/python'), '-I', '-m', 'pip', 'install',
                    '--isolated', '--disable-pip-version-check', '--no-cache-dir',
                    '--only-binary=:all:', '--require-hashes', '--index-url', 'https://pypi.org/simple',
                    '-r', str(root / 'scripts/configurator/requirements.txt')], check=True)
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:stream.write(lock_digest(root)+'\n')
    print('Configurator runtime ready. Run scripts/xplanet.sh config.')


if __name__ == '__main__':
    try:
        root = Path(sys.argv[2]).resolve()
        if sys.argv[1] == '--check':
            sys.exit(0 if ready(root) else 4)
        if sys.argv[1] != '--prepare':
            raise ValueError('Expected --prepare or --check.')
        prepare(root)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'Configurator runtime: {exc}', file=sys.stderr)
        sys.exit(2)
