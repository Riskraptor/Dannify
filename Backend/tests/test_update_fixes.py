"""Old downloads, streams that get cut off, and the taskbar buttons.

Each of these was seen on the user's machine: old update downloads left in
the data folder, a stream that ended short of what it promised the player,
and taskbar buttons that never appeared because a class was defined twice.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from dannify import streaming, updates

BACKEND = Path(__file__).resolve().parents[1]


def _load_from_desktop(*names: str) -> dict:
    """Pull top-level definitions out of desktop.py without importing it
    (importing it starts setting up the desktop shell)."""

    source = (BACKEND / 'desktop.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    wanted = [
        node for node in tree.body
        if (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names)
        or (isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in names for t in node.targets
        ))
    ]
    namespace: dict = {'time': time, 'Path': Path}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), 'desktop.py', 'exec'), namespace)
    return namespace


# ---------------------------------------------------------------------------
# Old update downloads
# ---------------------------------------------------------------------------
def test_old_downloads_go_and_a_waiting_update_stays(tmp_path):
    folder = tmp_path / 'updates'
    (folder / 'delta-3.17.0' / 'runtime').mkdir(parents=True)
    (folder / 'delta-3.17.0' / 'Dannify.exe').write_bytes(b'x')
    (folder / 'Dannify-Setup-3.17.0.exe').write_bytes(b'x')
    (folder / 'Dannify-Setup-3.18.0.exe.part').write_bytes(b'x')
    (folder / 'delta-3.18.1').mkdir()
    (folder / 'delta-3.19.0').mkdir()  # newer: waiting to be applied
    (folder / 'Dannify-Setup-3.19.0.exe').write_bytes(b'x')
    (folder / 'notes.txt').write_text('not ours')

    removed = updates.prune_downloads(folder, '3.18.1')

    assert sorted(removed) == [
        'Dannify-Setup-3.17.0.exe', 'Dannify-Setup-3.18.0.exe.part', 'delta-3.17.0', 'delta-3.18.1',
    ]
    assert sorted(p.name for p in folder.iterdir()) == [
        'Dannify-Setup-3.19.0.exe', 'delta-3.19.0', 'notes.txt',
    ]


def test_pruning_copes_with_nothing_there(tmp_path):
    assert updates.prune_downloads(tmp_path / 'missing', '3.18.1') == []


def test_pruning_keeps_everything_when_the_running_version_is_unknown(tmp_path):
    (tmp_path / 'Dannify-Setup-3.17.0.exe').write_bytes(b'x')
    assert updates.prune_downloads(tmp_path, '') == []
    assert (tmp_path / 'Dannify-Setup-3.17.0.exe').exists()


# ---------------------------------------------------------------------------
# A stream the CDN cuts off part way
# ---------------------------------------------------------------------------
AUDIO = bytes(range(256)) * 400  # 102400 bytes


class FakeResponse:
    def __init__(self, start, end, total, cut_after=None, status=206):
        self.status_code = status
        self.start, self.end, self.cut_after = start, end, cut_after
        self.headers = {'Content-Range': f'bytes {start}-{end}/{total}', 'Content-Length': str(end - start + 1)}
        if status == 200:
            self.headers = {'Content-Length': str(total)}
        self.closed = False

    def iter_content(self, size):
        body = AUDIO[self.start:self.end + 1]
        sent = 0
        for at in range(0, len(body), 4096):
            if self.cut_after is not None and sent >= self.cut_after:
                raise ConnectionResetError('the CDN let go')
            chunk = body[at:at + 4096]
            sent += len(chunk)
            yield chunk

    def close(self):
        self.closed = True


@pytest.fixture
def cdn(monkeypatch):
    asked = []
    plan = {'cuts': [], 'status': 206}

    def get_range(url, range_header, timeout=12.0, **_):
        first, _, last = range_header[len('bytes='):].partition('-')
        asked.append(range_header)
        cut = plan['cuts'].pop(0) if plan['cuts'] else None
        return FakeResponse(int(first), int(last), len(AUDIO), cut_after=cut, status=plan['status'])

    monkeypatch.setattr(streaming, '_http_get_range', get_range)
    return asked, plan


def test_a_cut_stream_is_picked_up_where_it_stopped(cdn):
    asked, plan = cdn
    plan['cuts'] = [20000]  # the second connection is cut too
    first = FakeResponse(0, len(AUDIO) - 1, len(AUDIO), cut_after=30000)
    got = b''.join(streaming._relay('vid', first, 'https://cdn/x'))
    assert got == AUDIO
    # Each connection hands over whole 4096 byte chunks before it drops, so
    # the first got 8 of them to the player and the second 5 more.
    assert asked == [f'bytes=32768-{len(AUDIO) - 1}', f'bytes={32768 + 20480}-{len(AUDIO) - 1}']


def test_a_seek_range_is_resumed_within_its_own_span(cdn):
    asked, plan = cdn
    first = FakeResponse(50000, 80000, len(AUDIO), cut_after=8000)
    got = b''.join(streaming._relay('vid', first, 'https://cdn/x'))
    assert got == AUDIO[50000:80001]
    assert asked == [f'bytes={50000 + 8192}-80000']


def test_it_gives_up_after_a_few_tries(cdn):
    asked, plan = cdn
    plan['cuts'] = [0, 0, 0, 0, 0]
    first = FakeResponse(0, len(AUDIO) - 1, len(AUDIO), cut_after=4096)
    got = b''.join(streaming._relay('vid', first, 'https://cdn/x'))
    assert len(asked) == streaming.RESUMES
    assert AUDIO.startswith(got) and len(got) < len(AUDIO)


def test_a_cdn_that_will_not_resume_ends_the_stream(cdn):
    asked, plan = cdn
    plan['status'] = 200  # answered with the whole file instead of the part
    first = FakeResponse(0, len(AUDIO) - 1, len(AUDIO), cut_after=10000)
    got = b''.join(streaming._relay('vid', first, 'https://cdn/x'))
    assert len(asked) == 1 and len(got) < len(AUDIO)


def test_a_whole_stream_is_passed_through_untouched(cdn):
    asked, _ = cdn
    first = FakeResponse(0, len(AUDIO) - 1, len(AUDIO), status=200)
    assert b''.join(streaming._relay('vid', first, 'https://cdn/x')) == AUDIO
    assert asked == []


def test_the_relay_always_gives_its_slot_back(cdn):
    before = streaming._PROXY_SEMA._value
    first = FakeResponse(0, len(AUDIO) - 1, len(AUDIO), cut_after=4096)
    gen = streaming._relay('vid', first, 'https://cdn/x')
    next(gen)
    gen.close()  # the listener seeked away
    assert streaming._PROXY_SEMA._value == before
    assert first.closed


# ---------------------------------------------------------------------------
# A name defined twice in one module replaces the first without a word
# ---------------------------------------------------------------------------
def test_no_module_defines_the_same_name_twice():
    found = {}
    for path in [BACKEND / 'main.py', BACKEND / 'desktop.py', *sorted((BACKEND / 'dannify').glob('*.py'))]:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        names = [
            n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            found[path.name] = twice
    assert found == {}


@pytest.mark.skipif(not hasattr(__import__('ctypes'), 'WinDLL'), reason='Windows only')
def test_the_taskbar_guid_parses_the_taskbar_interface():
    import ctypes

    tree = ast.parse((BACKEND / 'desktop.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_GUID')
    ns = {'ctypes': ctypes, 'ole32': ctypes.WinDLL('ole32')}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'desktop.py', 'exec'), ns)

    iid = ns['_GUID'].parse('{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}')  # ITaskbarList3
    assert (iid.Data1, iid.Data2, iid.Data3) == (0xEA1AFB91, 0x9E28, 0x4B86)
    assert bytes(iid.Data4) == bytes.fromhex('90E99E9F8A5EEFAF')


# ---------------------------------------------------------------------------
# Where an update may come from
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('url, ok', [
    ('https://github.com/o/r/releases/download/v1/Dannify-Setup-1.exe', True),
    ('https://objects.githubusercontent.com/github-production-release-asset/x', True),
    ('https://release-assets.githubusercontent.com/github-production-release-asset/x', True),
    ('http://github.com/o/r/releases/download/v1/Dannify-Setup-1.exe', False),
    ('https://evil.example/Dannify-Setup.exe', False),
    ('https://github.com.evil.example/x.exe', False),
    ('file:///C:/Windows/System32/calc.exe', False),
    ('https://github.com/o/r/releases/download/v1/..' + chr(92) + 'x.exe', False),
    ('', False),
])
def test_only_release_hosts_are_trusted(url, ok, monkeypatch):
    monkeypatch.delenv('DANNIFY_UPDATE_API', raising=False)
    assert updates.trusted_asset(url) is ok


def test_the_loopback_test_server_is_trusted_only_when_set(monkeypatch):
    monkeypatch.setenv('DANNIFY_UPDATE_API', 'http://127.0.0.1:5123')
    assert updates.trusted_asset('http://127.0.0.1:5123/dl/package-9.json')
    assert not updates.trusted_asset('http://127.0.0.1:9999/dl/package-9.json')
    monkeypatch.delenv('DANNIFY_UPDATE_API')
    assert not updates.trusted_asset('http://127.0.0.1:5123/dl/package-9.json')


def test_an_untrusted_installer_is_never_fetched(tmp_path, monkeypatch):
    monkeypatch.delenv('DANNIFY_UPDATE_API', raising=False)
    fetched = []
    monkeypatch.setattr(updates.urllib.request, 'urlopen', lambda *a, **k: fetched.append(a))
    with pytest.raises(RuntimeError):
        updates.download('https://evil.example/Dannify-Setup.exe', tmp_path)
    assert fetched == []
    assert list(tmp_path.iterdir()) == []


def test_the_installer_name_cannot_leave_its_folder(tmp_path, monkeypatch):
    class Reply:
        headers = {'Content-Length': '3'}

        def __init__(self):
            self.left = [b'MZ!']

        def read(self, n):
            return self.left.pop() if self.left else b''

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(updates.urllib.request, 'urlopen', lambda *a, **k: Reply())
    dest = tmp_path / 'updates'
    got = updates.download(
        'https://github.com/o/r/releases/download/v1/%2E%2E%5C%2E%2E%5Cevil.exe', dest,
    )
    assert got.parent == dest
    assert got.name == 'evil.exe'
    got = updates.download('https://github.com/o/r/releases/download/v1/notes.txt', dest)
    assert got.parent == dest and got.name == 'Dannify-Setup.exe'
