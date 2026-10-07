"""Only releases signed with Dannify's release key are installed."""

from __future__ import annotations

import hashlib
import json

import pytest

from dannify import layout, signing, updates
from tests.test_updates_inplace import NEW, Release, installed  # noqa: F401  (fixture)

SECRET = bytes.fromhex('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb')
PUBLIC = signing.public_key(SECRET).hex()
OTHER = bytes.fromhex('c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7')
SIG_URL = 'https://github.com/DANIELMWENDWA9451/Dannify/releases/download/v4.1.0/package-4.1.0.json.sig'
SETUP_URL = 'https://github.com/o/r/releases/download/v4.1.0/Dannify-Setup-4.1.0.exe'


def _sig(kind: str, version: str, data: bytes, key: bytes = SECRET) -> str:
    return signing.sign(key, signing.statement(kind, version, hashlib.sha256(data).hexdigest())).hex()


@pytest.fixture
def signed(monkeypatch):
    monkeypatch.setattr(updates, 'PUBLIC_KEY', PUBLIC)
    return PUBLIC


def _serve(monkeypatch, release: Release, signature: str) -> dict:
    info = release.install(monkeypatch)
    text = json.dumps(release.manifest)
    monkeypatch.setattr(updates, '_get_text', lambda url: signature if url.endswith('.sig') else text)
    info['package_signature_url'] = SIG_URL
    return info


def _manifest_bytes(release: Release) -> bytes:
    return json.dumps(release.manifest).encode('utf-8')


def test_a_signed_update_is_staged(installed, monkeypatch, signed):  # noqa: F811
    release = Release(NEW)
    info = _serve(monkeypatch, release, _sig('package', '4.1.0', _manifest_bytes(release)))
    assert updates.stage(info) == installed / 'app-next'
    assert layout.pending()['version'] == '4.1.0'


@pytest.mark.parametrize('how', ['other key', 'other version', 'other kind', 'garbage', 'missing'])
def test_an_unsigned_or_badly_signed_update_is_refused(installed, monkeypatch, signed, how):  # noqa: F811
    release = Release(NEW)
    text = _manifest_bytes(release)
    signature = {
        'other key': _sig('package', '4.1.0', text, OTHER),
        'other version': _sig('package', '4.0.0', text),
        'other kind': _sig('installer', '4.1.0', text),
        'garbage': 'zz',
        'missing': '',
    }[how]
    info = _serve(monkeypatch, release, signature)
    if how == 'missing':
        info['package_signature_url'] = ''
    with pytest.raises(RuntimeError):
        updates.stage(info)
    assert not (installed / 'app-next').exists()
    assert not list(installed.glob('app-next.tmp-*'))


def test_an_old_signed_list_cannot_stand_in_for_a_newer_release(installed, monkeypatch, signed):  # noqa: F811
    release = Release(NEW, '4.0.5')
    info = _serve(monkeypatch, release, _sig('package', '4.0.5', _manifest_bytes(release)))
    info['version'] = '4.1.0'  # what the release says it is
    with pytest.raises(RuntimeError):
        updates.stage(info)
    assert not (installed / 'app-next').exists()


def test_without_a_key_nothing_changes(installed, monkeypatch):  # noqa: F811
    monkeypatch.setattr(updates, 'PUBLIC_KEY', '')
    assert updates.stage(Release(NEW).install(monkeypatch)) == installed / 'app-next'


class _Reply:
    def __init__(self, body: bytes):
        self.headers = {'Content-Length': str(len(body))}
        self.status = 200
        self._left = [body]

    def read(self, n):
        return self._left.pop() if self._left else b''

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_signed_installer_is_handed_over(tmp_path, monkeypatch, signed):
    body = b'MZ' + b'x' * 500
    monkeypatch.setattr(updates.urllib.request, 'urlopen', lambda *a, **k: _Reply(body))
    monkeypatch.setattr(updates, '_get_text', lambda url: _sig('installer', '4.1.0', body))
    got = updates.download(SETUP_URL, tmp_path, None, '4.1.0', SETUP_URL + '.sig')
    assert got.read_bytes() == body


def test_a_tampered_installer_is_deleted_not_kept(tmp_path, monkeypatch, signed):
    body = b'MZ' + b'evil' * 100
    monkeypatch.setattr(updates.urllib.request, 'urlopen', lambda *a, **k: _Reply(body))
    monkeypatch.setattr(updates, '_get_text', lambda url: _sig('installer', '4.1.0', b'MZ genuine'))
    with pytest.raises(RuntimeError):
        updates.download(SETUP_URL, tmp_path, None, '4.1.0', SETUP_URL + '.sig')
    assert list(tmp_path.iterdir()) == []


def test_an_installer_without_a_signature_is_never_fetched(tmp_path, monkeypatch, signed):
    fetched = []
    monkeypatch.setattr(updates.urllib.request, 'urlopen', lambda *a, **k: fetched.append(a))
    with pytest.raises(RuntimeError):
        updates.download(SETUP_URL, tmp_path, None, '4.1.0', '')
    assert fetched == []


def test_the_shipped_key_is_a_real_key():
    # Read from the source: the module's value is switched off for tests.
    import re
    from pathlib import Path

    source = Path(updates.__file__).read_text(encoding='utf-8')
    shipped = re.search(r"^PUBLIC_KEY = '([0-9a-f]*)'$", source, re.M).group(1)
    assert len(bytes.fromhex(shipped)) == 32
    assert signing._decompress(bytes.fromhex(shipped)) is not None


def test_check_finds_the_signatures(monkeypatch):
    base = 'https://github.com/o/r/releases/download/v4.1.0/'
    names = ['Dannify-Setup-4.1.0.exe', 'Dannify-Setup-4.1.0.exe.sig', 'package-4.1.0.json',
             'package-4.1.0.json.sig', 'package-4.1.0.zip']
    assets = [{'name': n, 'browser_download_url': base + n, 'size': 1} for n in names]
    monkeypatch.setattr(updates, '_fetch_latest', lambda: {'tag_name': 'v4.1.0', 'assets': assets})
    monkeypatch.setattr(layout, 'skipped_version', lambda: '')
    got = updates.check('4.0.0', force=True)
    assert got['download_url'] == base + 'Dannify-Setup-4.1.0.exe'
    assert got['installer_signature_url'] == base + 'Dannify-Setup-4.1.0.exe.sig'
    assert got['package_manifest_url'] == base + 'package-4.1.0.json'
    assert got['package_signature_url'] == base + 'package-4.1.0.json.sig'
    assert got['package_url'] == base + 'package-4.1.0.zip'
