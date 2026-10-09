"""One release carries every platform's files. Each copy must find only its
own, and copies already out there (4.7.0 on Windows) must keep finding only
theirs: they pick by name shape, so the other platforms' names are chosen
never to match it. The 4.7.0 updater itself is kept in tests/fixtures and
asked, as it is, what it would take from a release that has everything."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from dannify import layout, osenv, release_assets, signing, updates

BASE = 'https://github.com/DANIELMWENDWA9451/Dannify/releases/download/v4.8.0/'
WINDOWS = ['Dannify-Setup-4.8.0.exe', 'Dannify-Setup-4.8.0.exe.sig',
           'package-4.8.0.json', 'package-4.8.0.json.sig', 'package-4.8.0.zip']
LINUX = ['linux-dannify_4.8.0_amd64.deb', 'linux-dannify_4.8.0_amd64.deb.sig']
MACOS = ['macos-Dannify-4.8.0-arm64.zip', 'macos-Dannify-4.8.0-arm64.zip.sig',
         'macos-Dannify-4.8.0-x64.zip', 'macos-Dannify-4.8.0-x64.zip.sig',
         'macos-Dannify-4.8.0-arm64.dmg', 'macos-Dannify-4.8.0-x64.dmg']


def _release(order):
    # Every order: 4.7.0 takes the first match, so the others' files must not
    # match at all, wherever they sit in the list.
    return {'tag_name': 'v4.8.0', 'body': '', 'assets': [
        {'name': n, 'browser_download_url': BASE + n, 'size': 7} for n in order]}


ORDERS = [LINUX + MACOS + WINDOWS, MACOS + WINDOWS + LINUX, WINDOWS + LINUX + MACOS]


def _updater_470():
    path = Path(__file__).parent / 'fixtures' / 'updates_4_7_0.py'
    spec = importlib.util.spec_from_file_location('dannify._updates_4_7_0', path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = 'dannify'
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('order', ORDERS)
def test_a_4_7_0_windows_copy_takes_only_the_windows_files(monkeypatch, order):
    old = _updater_470()
    monkeypatch.setattr(old, 'PUBLIC_KEY', '')
    monkeypatch.setattr(old, '_fetch_latest', lambda: _release(order))
    monkeypatch.setattr(layout, 'skipped_version', lambda: '')
    got = old.check('4.7.0', force=True)
    assert got['available'] and got['version'] == '4.8.0'
    assert got['download_url'] == BASE + 'Dannify-Setup-4.8.0.exe'
    assert got['installer_signature_url'] == BASE + 'Dannify-Setup-4.8.0.exe.sig'
    assert got['package_manifest_url'] == BASE + 'package-4.8.0.json'
    assert got['package_url'] == BASE + 'package-4.8.0.zip'
    assert got['package_signature_url'] == BASE + 'package-4.8.0.json.sig'


def test_no_other_platform_file_looks_like_a_windows_one():
    for name in LINUX + MACOS:
        assert not name.startswith('package-')
        assert not (name.lower().endswith('.exe') and 'setup' in name.lower())


def _as(monkeypatch, platform, machine):
    monkeypatch.setattr(osenv, 'IS_WINDOWS', platform == 'windows')
    monkeypatch.setattr(osenv, 'IS_MAC', platform == 'macos')
    monkeypatch.setattr(osenv, 'IS_LINUX', platform == 'linux')
    monkeypatch.setattr(osenv, 'PLATFORM', platform)
    monkeypatch.setattr(release_assets, 'IS_WINDOWS', platform == 'windows')
    monkeypatch.setattr(release_assets, 'IS_MAC', platform == 'macos')
    monkeypatch.setattr(release_assets._platform, 'machine', lambda: machine)
    monkeypatch.setattr(updates, 'self_updatable', lambda: True)
    monkeypatch.setattr(layout, 'skipped_version', lambda: '')
    monkeypatch.setattr(layout, 'managed', lambda: False)


@pytest.mark.parametrize('order', ORDERS)
@pytest.mark.parametrize('platform,machine,want,kind', [
    ('linux', 'x86_64', 'linux-dannify_4.8.0_amd64.deb', 'installer-linux-deb-amd64'),
    ('macos', 'arm64', 'macos-Dannify-4.8.0-arm64.zip', 'app-macos-zip-arm64'),
    ('macos', 'x86_64', 'macos-Dannify-4.8.0-x64.zip', 'app-macos-zip-x64'),
    ('windows', 'AMD64', 'Dannify-Setup-4.8.0.exe', 'installer'),
])
def test_each_platform_finds_only_its_own_update(monkeypatch, order, platform, machine, want, kind):
    _as(monkeypatch, platform, machine)
    monkeypatch.setattr(updates, '_fetch_latest', lambda: _release(order))
    got = updates.check('4.7.0', force=True)
    assert got['available'] and got['download_url'] == BASE + want
    assert got['installer_signature_url'] == BASE + want + '.sig'
    assert got['installer_kind'] == kind
    if platform == 'windows':
        assert got['package_url'] == BASE + 'package-4.8.0.zip'
    else:
        assert not got['package_url'] and not got['package_manifest_url']


def test_a_release_without_this_platform_offers_nothing_to_download(monkeypatch):
    _as(monkeypatch, 'linux', 'x86_64')
    monkeypatch.setattr(updates, '_fetch_latest', lambda: _release(WINDOWS + MACOS))
    got = updates.check('4.7.0', force=True)
    assert got['version'] == '4.8.0' and not got['download_url']
    assert not got['installer_signature_url']


def test_every_release_file_is_signed_as_its_own_platform_and_arch():
    kinds = {name: release_assets.describe(name) for name in WINDOWS + LINUX + MACOS
             if not name.endswith('.sig') and not name.endswith('.zip') or name.startswith('macos-')}
    assert kinds['Dannify-Setup-4.8.0.exe'] == ('installer', '4.8.0')
    assert kinds['package-4.8.0.json'] == ('package', '4.8.0')
    assert kinds['linux-dannify_4.8.0_amd64.deb'] == ('installer-linux-deb-amd64', '4.8.0')
    assert kinds['macos-Dannify-4.8.0-arm64.zip'] == ('app-macos-zip-arm64', '4.8.0')
    assert kinds['macos-Dannify-4.8.0-x64.dmg'] == ('installer-macos-dmg-x64', '4.8.0')
    assert release_assets.describe('linux-dannify_4.8.0_amd64.deb.sig') is None


def test_a_signature_never_carries_over_to_another_platform():
    secret = bytes(range(32))
    public = signing.public_key(secret).hex()
    digest = 'ab' * 32
    sig = signing.sign(secret, signing.statement('installer-linux-deb-amd64', '4.8.0', digest)).hex()
    assert signing.verify_release(public, 'installer-linux-deb-amd64', '4.8.0', digest, sig)
    for other in ('installer', 'package', 'app-macos-zip-arm64', 'installer-linux-deb-arm64'):
        assert not signing.verify_release(public, other, '4.8.0', digest, sig)


def test_the_windows_statements_are_unchanged():
    # Byte for byte what 4.7.0 verifies.
    assert signing.statement('installer', '4.8.0', 'AB' * 32) == (
        b'dannify-release-v1\ninstaller\n4.8.0\n' + b'ab' * 32)


def test_old_platform_downloads_are_tidied(tmp_path):
    for name in ('linux-dannify_4.7.0_amd64.deb', 'macos-Dannify-4.7.0-arm64.zip.part',
                 'linux-dannify_4.9.0_amd64.deb', 'Dannify-Setup-4.7.0.exe'):
        (tmp_path / name).write_bytes(b'x')
    gone = updates.prune_downloads(tmp_path, '4.8.0')
    assert sorted(gone) == ['Dannify-Setup-4.7.0.exe', 'linux-dannify_4.7.0_amd64.deb',
                            'macos-Dannify-4.7.0-arm64.zip.part']
