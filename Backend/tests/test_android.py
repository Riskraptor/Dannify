"""The backend inside the Android app: how it is started (shell/android/host.py),
where it finds the programs the app carries, and where it keeps its key.
Run on a computer, with the parts of Android it talks to stood in for."""

from __future__ import annotations

import json
import os
import sys
import types

import pytest

from dannify import jsruntime, keystore, osenv, streaming, vault


def test_the_app_tells_the_backend_where_everything_is(monkeypatch, tmp_path):
    from dannify.shell.android import host

    for name in ('DANNIFY_DATA_DIR', 'DOWNLOAD_DIR', 'DANNIFY_BUNDLE_DIR', 'DANNIFY_NATIVE_DIR', 'TMPDIR', 'TZ', 'LANG'):
        monkeypatch.delenv(name, raising=False)
    config = {
        'data_dir': str(tmp_path / 'data'),
        'music_dir': str(tmp_path / 'Music' / 'Dannify'),
        'bundle_dir': str(tmp_path / 'bundle'),
        'native_dir': str(tmp_path / 'lib'),
        'cache_dir': str(tmp_path / 'cache'),
        'time_zone': 'Africa/Nairobi',
        'locale': 'sw_KE.UTF-8',
    }
    host._environment(config)
    assert os.environ['DANNIFY_DATA_DIR'] == config['data_dir']
    assert os.environ['DOWNLOAD_DIR'] == config['music_dir']
    assert os.environ['DANNIFY_BUNDLE_DIR'] == config['bundle_dir']
    assert os.environ['DANNIFY_NATIVE_DIR'] == config['native_dir']
    assert os.environ['TMPDIR'] == config['cache_dir']
    assert os.environ['TZ'] == 'Africa/Nairobi' and os.environ['LANG'] == 'sw_KE.UTF-8'
    # The folders it writes to are there before anything is imported.
    for key in ('data_dir', 'music_dir', 'cache_dir'):
        assert os.path.isdir(config[key])


def test_starting_twice_answers_with_the_first_start(monkeypatch, tmp_path):
    from dannify.shell import core
    from dannify.shell.android import host

    started = []
    monkeypatch.setattr(host, '_started', {})
    monkeypatch.setattr(core, 'pick_port', lambda: 48123)
    monkeypatch.setattr(core, 'start_server', lambda port, token: started.append((port, token)) or object())
    monkeypatch.setattr(core, 'wait_until_up', lambda port, token, server, timeout: True)
    monkeypatch.setenv('DANNIFY_DATA_DIR', str(tmp_path))
    first = json.loads(host.start(json.dumps({'data_dir': str(tmp_path)})))
    again = json.loads(host.start('{}'))
    assert first == again and len(started) == 1
    assert first['ok'] and first['port'] == 48123
    # The page is told it is in the Android app, and carries its key once.
    assert first['url'] == f"http://127.0.0.1:48123/?shell=android&k={first['token']}"
    assert len(first['token']) >= 40


def test_the_programs_are_found_where_android_installed_them(monkeypatch, tmp_path):
    monkeypatch.setattr(jsruntime, 'IS_ANDROID', True)
    monkeypatch.setenv('DANNIFY_NATIVE_DIR', str(tmp_path))
    assert jsruntime.bundled_qjs() is None and jsruntime.media_tool() is None
    for name in ('libdnfjs.so', 'libdnfmedia.so'):
        (tmp_path / name).write_bytes(b'\x7fELF')
    assert jsruntime.bundled_qjs() == tmp_path / 'libdnfjs.so'
    assert jsruntime.media_tool() == tmp_path / 'libdnfmedia.so'
    # yt-dlp is pointed straight at the phone's media tool.
    opts = jsruntime.apply({})
    assert opts['ffmpeg_location'] == str(tmp_path / 'libdnfmedia.so')


def test_no_transcoded_stream_is_offered_on_a_phone(monkeypatch):
    # Its media tool reads no https, so the desktops' fallback is not tried.
    monkeypatch.setattr(osenv, 'IS_ANDROID', True)
    monkeypatch.setattr(streaming, '_extract_direct', lambda video_id: pytest.fail('nothing is fetched'))
    with pytest.raises(RuntimeError):
        streaming.open_stream('dQw4w9WgXcQ')


class _Vault:
    """The app's KeyVault, as Python sees it through Chaquopy."""

    value = None

    @classmethod
    def get(cls):
        return cls.value

    @classmethod
    def put(cls, value):
        cls.value = value
        return True


def test_the_key_is_kept_in_the_phones_key_vault(monkeypatch):
    monkeypatch.delenv('DANNIFY_KEYSTORE', raising=False)
    monkeypatch.setattr(keystore, 'IS_ANDROID', True)
    monkeypatch.setitem(sys.modules, 'java', types.SimpleNamespace(
        jclass=lambda name: _Vault if name == 'app.dannify.KeyVault' else None))
    _Vault.value = None
    keystore.forget_cache()
    assert keystore.preferred() == 'android'
    key = keystore.wrapping_key('android')
    assert key is not None and len(key) == 32 and _Vault.value
    # The same key the next time the app starts.
    keystore.forget_cache()
    assert keystore.wrapping_key('android') == key
    wrapped = vault._keystore_wrap(b'k' * 32)
    assert vault._unprotect(wrapped) == b'k' * 32


def test_a_vault_that_cannot_keep_it_is_not_trusted(monkeypatch):
    class Broken(_Vault):
        @classmethod
        def put(cls, value):
            return False

    monkeypatch.setitem(sys.modules, 'java', types.SimpleNamespace(jclass=lambda name: Broken))
    Broken.value = None
    keystore.forget_cache()
    assert keystore.wrapping_key('android') is None
