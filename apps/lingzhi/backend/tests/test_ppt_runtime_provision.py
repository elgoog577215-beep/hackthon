"""Locked packages and their dependencies use the same immutable archive."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ppt_provision', ROOT / 'scripts/provision_ppt_runtime.py')
provisioner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provisioner)


@pytest.mark.parametrize('bad_digest', [False, True])
def test_install_pins_dependencies_and_rejects_tampered_packages(tmp_path, monkeypatch, bad_digest):
    lock = json.loads((ROOT / 'deploy/ppt-runtime/ubuntu-24.04-amd64.json').read_text())
    font = tmp_path / 'frontend/public/presentation-assets/fonts/NotoSansCJKsc-Regular.otf'
    font.parent.mkdir(parents=True)
    font.write_bytes(b'font')
    lock['font_sha256'] = hashlib.sha256(b'font').hexdigest()
    lock['packages'] = {'example': {'Filename': 'pool/example.deb',
        'SHA256': hashlib.sha256(b'correct').hexdigest(), 'Version': '1'}}
    monkeypatch.setattr(provisioner, 'ROOT', tmp_path)
    monkeypatch.setattr(provisioner, 'check_platform', lambda _: None)
    monkeypatch.setattr(provisioner.os, 'geteuid', lambda: 0)
    calls, urls = [], []
    def download(url, **kwargs):
        urls.append(url)
        return io.BytesIO(b'tampered' if bad_digest else b'correct')
    monkeypatch.setattr(provisioner.urllib.request, 'urlopen', download)
    monkeypatch.setattr(provisioner.subprocess, 'run', lambda args, **kw: calls.append(args))
    # Stop after the package installation, before any system font mutation.
    original_mkdir = Path.mkdir
    def mkdir(path, *args, **kwargs):
        if str(path) == '/usr/local/share/fonts/lingzhi':
            raise RuntimeError('font installation boundary')
        return original_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', mkdir)
    with pytest.raises(ValueError if bad_digest else RuntimeError,
                       match='digest_mismatch' if bad_digest else 'font installation boundary'):
        provisioner.provision(lock, install=True)
    assert urls == [lock['source'] + 'pool/example.deb']
    if bad_digest:
        assert not calls
    else:
        assert len(calls) == 2
        assert all(args[args.index('--snapshot') + 1] == lock['snapshot'] for args in calls)


def test_mismatched_snapshot_source_is_rejected_before_install(monkeypatch):
    monkeypatch.setattr(provisioner, 'check_platform', lambda _: pytest.fail('must validate snapshot first'))
    with pytest.raises(ValueError, match='snapshot_mismatch'):
        provisioner.provision({'snapshot': '20260918T000000Z', 'source': 'https://archive.ubuntu.com/ubuntu/'})


@pytest.mark.parametrize('status', [502, 503])
def test_download_recovers_from_temporary_archive_failure(tmp_path, monkeypatch, status):
    calls, sleeps = [], []
    url = 'https://snapshot.ubuntu.com/pinned.deb'
    def download(actual_url, **kwargs):
        calls.append(actual_url)
        if len(calls) == 1:
            raise provisioner.urllib.error.HTTPError(url, status, 'temporary', {}, None)
        return io.BytesIO(b'complete')
    monkeypatch.setattr(provisioner.urllib.request, 'urlopen', download)
    monkeypatch.setattr(provisioner.time, 'sleep', sleeps.append)
    path = tmp_path / 'package.deb'
    provisioner.download_package(url, path)
    assert calls == [url, url]
    assert sleeps == [2]
    assert path.read_bytes() == b'complete'


@pytest.mark.parametrize('status,expected_attempts', [(404, 1), (503, 5)])
def test_download_stops_on_permanent_error_or_retry_limit(tmp_path, monkeypatch, status, expected_attempts):
    calls = []
    def download(url, **kwargs):
        calls.append(url)
        raise provisioner.urllib.error.HTTPError(url, status, 'failed', {}, None)
    monkeypatch.setattr(provisioner.urllib.request, 'urlopen', download)
    monkeypatch.setattr(provisioner.time, 'sleep', lambda _: None)
    with pytest.raises(provisioner.urllib.error.HTTPError):
        provisioner.download_package('https://snapshot.ubuntu.com/pinned.deb', tmp_path / 'package.deb')
    assert len(calls) == expected_attempts
