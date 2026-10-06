"""Updates that are built beside the running copy and swapped in at start.

A fake release is made from real files: a package list and a zip, served
through the same range-request code the app uses, with every request
counted. The installed copy is a folder shaped like the real thing:

    root/Dannify.exe      (the launcher)
    root/app/...          (the running version)
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import zipfile

import pytest

from dannify import delta, layout, updates


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _blob(seed: int, size: int) -> bytes:
    # Random, so it does not compress away and the byte counts mean something.
    return random.Random(seed).randbytes(size)


# The unchanged files are big, as in the real app (Python, the media
# encoder): bigger than the gap two wanted files are joined across, so they
# split the download into separate requests instead of riding along.
OLD = {
    'Dannify.exe': _blob(1, 40_000),
    'runtime/python314.dll': _blob(2, 700_000),
    'runtime/dannify.res': _blob(3, 20_000),
    'runtime/media/dnfmedia.exe': _blob(4, 1_200_000),
    'config/updates.json': b'{"repo": "x/y"}',
    'runtime/gone.pyd': b'removed in the new version',
}
NEW = {
    'Dannify.exe': _blob(11, 41_000),
    'runtime/python314.dll': OLD['runtime/python314.dll'],
    'runtime/dannify.res': _blob(13, 21_000),
    'runtime/media/dnfmedia.exe': OLD['runtime/media/dnfmedia.exe'],
    'config/updates.json': OLD['config/updates.json'],
    'runtime/new-module.pyd': _blob(15, 9_000),
}


class Release:
    """A package list and zip, served by range, with every request counted."""

    def __init__(self, files: dict[str, bytes], version: str = '4.1.0') -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rel, data in files.items():
                zf.writestr(rel, data)
        self.zip = buf.getvalue()
        self.manifest = {
            'version': version,
            'files': {rel: {'size': len(d), 'sha256': _sha(d)} for rel, d in files.items()},
        }
        self.requests: list[tuple[int, int]] = []

    @property
    def data_requests(self) -> list[tuple[int, int]]:
        # The first two requests read the zip's own directory (its tail, then
        # the directory itself); the rest fetch the files.
        return self.requests[2:]

    def get(self, url, start=None, end=None, on_bytes=None):
        if start is None:
            data = self.zip
        else:
            last = len(self.zip) - 1 if end is None else min(end, len(self.zip) - 1)
            data = self.zip[start:last + 1]
            self.requests.append((start, last))
        if on_bytes:
            on_bytes(len(data))
        return data

    def install(self, monkeypatch) -> dict:
        monkeypatch.setattr(delta, '_get', self.get)
        monkeypatch.setattr(delta, '_content_length', lambda url: len(self.zip))
        monkeypatch.setattr(updates, '_get_text', lambda url: json.dumps(self.manifest))
        return {
            'version': self.manifest['version'],
            'notes': 'Faster starts.\nA new look.',
            'package_manifest_url': 'https://github.com/DANIELMWENDWA9451/Dannify/releases/download/v4.1.0/package-4.1.0.json',
            'package_url': 'https://github.com/DANIELMWENDWA9451/Dannify/releases/download/v4.1.0/package-4.1.0.zip',
        }


@pytest.fixture
def installed(tmp_path, monkeypatch):
    root = tmp_path / 'Dannify'
    app = root / 'app'
    for rel, data in OLD.items():
        path = app / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / 'Dannify.exe').write_bytes(b'launcher')
    monkeypatch.setattr(layout, 'app_dir', lambda: app)
    monkeypatch.setattr(layout, 'root', lambda: root)
    return root


def test_only_the_changed_files_are_downloaded_and_the_rest_are_shared(installed, monkeypatch):
    release = Release(NEW)
    info = release.install(monkeypatch)

    staged = updates.stage(info)

    assert staged == installed / 'app-next'
    got = {p.relative_to(staged).as_posix(): p.read_bytes() for p in staged.rglob('*') if p.is_file()}
    marker = json.loads(got.pop(layout.READY))
    assert got == NEW
    assert marker['version'] == '4.1.0' and 'Faster starts.' in marker['notes']
    # Unchanged files are the same file under a second name, not copies.
    for rel in ('runtime/python314.dll', 'runtime/media/dnfmedia.exe', 'config/updates.json'):
        assert os.path.samefile(staged / rel, installed / 'app' / rel)
    # Only the changed files came down: about 71 KB of a 2 MB archive.
    fetched = sum(end - start + 1 for start, end in release.data_requests)
    changed = sum(len(NEW[rel]) for rel in ('Dannify.exe', 'runtime/dannify.res', 'runtime/new-module.pyd'))
    assert changed <= fetched < changed + 60_000
    assert len(release.data_requests) <= 3
    # The running copy was not touched.
    assert {p.relative_to(installed / 'app').as_posix(): p.read_bytes()
            for p in (installed / 'app').rglob('*') if p.is_file()} == OLD
    assert not list(installed.glob('app-next.tmp-*'))


def test_the_launcher_sees_it_as_ready(installed, monkeypatch):
    updates.stage(Release(NEW).install(monkeypatch))
    waiting = layout.pending()
    assert waiting and waiting['version'] == '4.1.0'


def test_a_damaged_download_leaves_nothing_behind(installed, monkeypatch):
    release = Release(NEW)
    info = release.install(monkeypatch)
    # The list promises one thing, the archive holds another.
    release.manifest['files']['Dannify.exe']['sha256'] = '0' * 64

    with pytest.raises(RuntimeError):
        updates.stage(info)
    assert not (installed / 'app-next').exists()
    assert not list(installed.glob('app-next.tmp-*'))


def test_a_list_that_points_outside_the_app_is_refused(installed, monkeypatch):
    release = Release(NEW)
    info = release.install(monkeypatch)
    release.manifest['files']['../evil.dll'] = {'size': 1, 'sha256': '0' * 64}

    with pytest.raises(ValueError):
        updates.stage(info)
    assert not (installed.parent / 'evil.dll').exists()
    assert not (installed / 'app-next').exists()


def test_a_newer_update_replaces_one_already_waiting(installed, monkeypatch):
    updates.stage(Release(NEW, '4.1.0').install(monkeypatch))
    newer = dict(NEW)
    newer['Dannify.exe'] = _blob(21, 42_000)
    updates.stage(Release(newer, '4.2.0').install(monkeypatch))
    assert layout.pending()['version'] == '4.2.0'
    assert (installed / 'app-next' / 'Dannify.exe').read_bytes() == newer['Dannify.exe']


def test_an_unmanaged_copy_does_not_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(layout, 'root', lambda: None)
    with pytest.raises(RuntimeError):
        updates.stage({'package_url': 'x', 'package_manifest_url': 'y'})


def test_nearby_entries_are_fetched_in_one_request(tmp_path, monkeypatch):
    release = Release({f'runtime/m{i}.pyd': _blob(100 + i, 3000) for i in range(40)})
    release.install(monkeypatch)
    names = [f'runtime/m{i}.pyd' for i in (3, 4, 5, 20, 21, 39)]

    delta.fetch('https://example.invalid/p.zip', names, tmp_path / 'out')

    assert len(release.data_requests) == 1  # all within the join gap of each other
    for name in names:
        assert (tmp_path / 'out' / name).is_file()


def test_the_installer_download_refuses_a_short_file(tmp_path, monkeypatch):
    class Short:
        headers = {'Content-Length': '1000'}

        def __init__(self):
            self.sent = False

        def read(self, n):
            if self.sent:
                return b''
            self.sent = True
            return b'x' * 400

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updates.urllib.request, 'urlopen', lambda *a, **k: Short())
    with pytest.raises(RuntimeError):
        updates.download('https://example.invalid/Dannify-Setup-4.1.0.exe', tmp_path)
    assert not (tmp_path / 'Dannify-Setup-4.1.0.exe').exists()
    assert not (tmp_path / 'Dannify-Setup-4.1.0.exe.part').exists()


def test_a_version_rolled_back_here_is_not_offered_again(tmp_path, monkeypatch):
    monkeypatch.setattr(layout, 'skipped_version', lambda: '4.1.0')
    monkeypatch.setattr(updates, '_fetch_latest', lambda: {'tag_name': 'v4.1.0', 'assets': []})
    assert updates.check('4.0.0', force=True)['available'] is False
    monkeypatch.setattr(updates, '_fetch_latest', lambda: {'tag_name': 'v4.2.0', 'assets': []})
    assert updates.check('4.0.0', force=True)['available'] is True


def test_tidy_keeps_one_version_to_go_back_to(installed):
    import time

    for n in range(3):
        old = installed / f'app-old-{n}'
        old.mkdir()
        (old / 'Dannify.exe').write_bytes(b'x')
        stamp = time.time() - 100 + n * 10
        os.utime(old, (stamp, stamp))
    (installed / 'app-broken-1').mkdir()
    (installed / 'app-next.tmp-abc').mkdir()
    (installed / 'runtime').mkdir()  # left by Dannify 3.x
    (installed / 'unins000.exe').write_bytes(b'x')

    layout.tidy()

    assert sorted(p.name for p in installed.iterdir()) == ['Dannify.exe', 'app', 'app-old-2']
