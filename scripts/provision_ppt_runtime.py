#!/usr/bin/env python3
"""Install/check the explicitly locked Ubuntu PPT tools; never starts a service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def check_platform(lock):
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    arch = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    if (release.get('ID', '').strip('"'), release.get('VERSION_ID', '').strip('"'), arch) != (lock['os_id'], lock['os_version'], lock['architecture']):
        raise ValueError('ppt_runtime_platform_mismatch')


def check_packages(lock):
    for package, record in lock['packages'].items():
        installed = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', package], text=True).strip()
        if installed != record['Version']:
            raise ValueError(f'ppt_runtime_package_mismatch:{package}')
    font = Path('/usr/local/share/fonts/lingzhi/NotoSansCJKsc-Regular.otf')
    if not font.is_file() or hashlib.sha256(font.read_bytes()).hexdigest() != lock['font_sha256']:
        raise ValueError('ppt_runtime_system_font_mismatch')


def provision(lock, *, install=False):
    check_platform(lock)
    source_font = ROOT / 'frontend/public/presentation-assets/fonts/NotoSansCJKsc-Regular.otf'
    if hashlib.sha256(source_font.read_bytes()).hexdigest() != lock['font_sha256']:
        raise ValueError('ppt_runtime_bundled_font_mismatch')
    if install:
        if os.geteuid() != 0:
            raise ValueError('ppt_runtime_install_requires_root')
        with tempfile.TemporaryDirectory(prefix='lingzhi-ppt-packages-') as directory:
            packages = []
            for package, record in lock['packages'].items():
                path = Path(directory) / f'{package}.deb'
                with urllib.request.urlopen(lock['source'] + record['Filename'], timeout=120) as source, path.open('wb') as target:
                    shutil.copyfileobj(source, target)
                if hashlib.sha256(path.read_bytes()).hexdigest() != record['SHA256']:
                    raise ValueError(f'ppt_runtime_package_digest_mismatch:{package}')
                packages.append(str(path))
            subprocess.run(['apt-get', 'update', '-qq'], check=True)
            subprocess.run(['apt-get', 'install', '-y', '--no-install-recommends', *packages], check=True)
        target = Path('/usr/local/share/fonts/lingzhi')
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_font, target / source_font.name)
        subprocess.run(['fc-cache', '-f', str(target)], check=True)
    check_packages(lock)
    print('PPT runtime package versions, package digests on install, and system font verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT / 'deploy/ppt-runtime/ubuntu-24.04-amd64.json')
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    provision(json.loads(args.lock.read_text()), install=args.install)
