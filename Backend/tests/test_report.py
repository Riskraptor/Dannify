"""Problem reports: sent from inside the app, nothing in them that signs in,
and kept to send later when they cannot go now."""

from __future__ import annotations

import asyncio
import email
import email.policy
import http.server
import io
import json
import sys
import threading
import zipfile

import pytest

from dannify import api, report


def test_secrets_are_blanked_wherever_they_turn_up():
    text = '\n'.join([
        'cookie: SAPISID=abc123; HSID=zzz',
        'headers {"Authorization": "SAPISIDHASH 123_deadbeef"}',
        'token=eyJhbGciOiJIUzI1NiJ9.e30.x refresh_token: "r-123"',
        'Bearer abcdefghijklmnop',
        'password = hunter2',
        'downloaded Bien - Inauma.dnf in 2.1 s',
    ])
    out = report.scrub(text)
    for secret in ('abc123', 'SAPISIDHASH', 'eyJhbGci', 'r-123', 'abcdefghijklmnop', 'hunter2'):
        assert secret not in out, secret
    assert 'downloaded Bien - Inauma.dnf in 2.1 s' in out


def _unzip(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n).decode('utf-8') for n in z.namelist()}


def test_the_diagnostics_hold_logs_window_errors_and_settings_and_no_secrets(tmp_path):
    (tmp_path / 'dannify.log').write_text('started\ncookie=SECRET1\nplayed a song\n', encoding='utf-8')
    (tmp_path / 'dannify.2026-10-01.log').write_text('older run\n', encoding='utf-8')
    (tmp_path / 'crash.log').write_text('Fatal Python error: boom\n', encoding='utf-8')
    (tmp_path / 'empty.log').write_text('', encoding='utf-8')
    files = _unzip(report.pack(
        tmp_path, '4.5.0',
        settings={'theme': 'dark', 'yt_cookie': 'SECRET2', 'max_parallel_downloads': 3},
        facts={'Playlists': 2},
        window_errors=[{'message': 'TypeError: x is undefined', 'route': '/library'}],
    ))
    assert {'about.txt', 'logs/dannify.log', 'logs/dannify.2026-10-01.log', 'logs/crash.log',
            'window-errors.json'} <= set(files)
    everything = ''.join(files.values())
    assert 'SECRET1' not in everything and 'SECRET2' not in everything
    assert 'Dannify 4.5.0' in files['about.txt'] and 'Playlists: 2' in files['about.txt']
    assert 'yt_cookie' not in files['about.txt']
    assert json.loads(files['window-errors.json'])[0]['route'] == '/library'


def test_the_diagnostics_stay_small_dropping_the_oldest_logs_first(tmp_path):
    import os
    import random

    noise = random.Random(1)
    for i, name in enumerate(('dannify.old.log', 'dannify.log')):
        p = tmp_path / name
        p.write_text(''.join(noise.choice('abcdef0123456789') for _ in range(300_000)), encoding='utf-8')
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
    files = _unzip(report.pack(tmp_path, '4.5.0', limit=250_000))
    assert 'logs/dannify.log' in files and 'logs/dannify.old.log' not in files


def test_what_the_person_typed_is_checked():
    assert report.clean_fields('The song stops after a minute', 'PLAYBACK', '') == {
        'description': 'The song stops after a minute', 'category': 'playback', 'contact': ''}
    assert report.clean_fields('Something odd happens here', 'nonsense', 'me@example.com')['category'] == 'other'
    with pytest.raises(ValueError):
        report.clean_fields('short', 'other', '')
    with pytest.raises(ValueError):
        report.clean_fields('A long enough description', 'other', 'not an email')


# ---------------------------------------------------------------------------
# Sending, against a stand-in for the report server
# ---------------------------------------------------------------------------


class _Receiver(http.server.BaseHTTPRequestHandler):
    got: list = []
    status = 200

    def log_message(self, *args):
        pass

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers['Content-Length']))
        head = f'Content-Type: {self.headers["Content-Type"]}\r\n\r\n'.encode()
        message = email.message_from_bytes(head + body, policy=email.policy.default)
        parts = {}
        for part in message.iter_parts():
            name = part.get_param('name', header='content-disposition')
            parts[name] = part.get_payload(decode=True)
        type(self).got.append(parts)
        self.send_response(type(self).status)
        self.send_header('Content-Length', '0')
        self.end_headers()


@pytest.fixture
def receiver(monkeypatch):
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Receiver)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _Receiver.got = []
    _Receiver.status = 200
    url = f'http://127.0.0.1:{httpd.server_address[1]}/reports'
    monkeypatch.setenv('DANNIFY_REPORT_URL', url)
    yield url
    httpd.shutdown()


def _a_report(diag=b'PK-zip-bytes'):
    return {'id': report.new_id(), 'version': '4.5.0', 'category': 'playback',
            'description': 'It stops after a minute', 'contact': '', 'diagnostics': diag}


def test_a_report_arrives_with_its_fields_and_diagnostics(receiver, tmp_path):
    r = _a_report()
    assert report.send(tmp_path, r) == 'sent'
    got = _Receiver.got[-1]
    assert got['id'].decode() == r['id'] and got['category'] == b'playback'
    assert got['description'].decode() == 'It stops after a minute'
    assert got['diagnostics'] == b'PK-zip-bytes'
    assert report.pending(tmp_path) == 0


def test_one_that_cannot_go_waits_and_goes_later(receiver, tmp_path):
    _Receiver.status = 503
    r = _a_report()
    assert report.send(tmp_path, r) == 'queued'
    assert report.pending(tmp_path) == 1
    assert report.flush(tmp_path) == (0, 1)  # still down
    _Receiver.status = 200
    assert report.flush(tmp_path) == (1, 0)
    assert _Receiver.got[-1]['id'].decode() == r['id']
    assert _Receiver.got[-1]['diagnostics'] == b'PK-zip-bytes'


def test_only_a_few_wait(receiver, tmp_path):
    _Receiver.status = 500
    for _ in range(report.OUTBOX_KEEP + 3):
        report.send(tmp_path, _a_report(diag=None))
    assert report.pending(tmp_path) == report.OUTBOX_KEEP


def test_closed_until_there_is_a_server(monkeypatch, tmp_path):
    monkeypatch.delenv('DANNIFY_REPORT_URL', raising=False)
    monkeypatch.setattr(report, 'REPORT_ENDPOINT', '')
    assert not report.enabled()
    with pytest.raises(report.NotOpen):
        report.send(tmp_path, _a_report())


def test_a_shipped_copy_sends_nowhere_but_its_own_server_or_this_machine(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(report, 'REPORT_ENDPOINT', '')
    monkeypatch.setenv('DANNIFY_REPORT_URL', 'https://somewhere-else.example/collect')
    assert report.endpoint() == ''
    monkeypatch.setenv('DANNIFY_REPORT_URL', 'http://127.0.0.1:5999/r')
    assert report.endpoint() == 'http://127.0.0.1:5999/r'


def test_the_files_earlier_versions_saved_are_tidied_away(tmp_path):
    folder = tmp_path / 'reports'
    folder.mkdir()
    (folder / 'Dannify-report-20261003-042256.zip').write_bytes(b'x')
    (folder / 'Dannify-report-20261003-042300.zip.part').write_bytes(b'x')
    (folder / 'outbox').mkdir()
    assert report.tidy_old_exports(tmp_path) == 2
    assert (folder / 'outbox').is_dir()


def test_the_api_sends_and_says_how(receiver, tmp_path, monkeypatch):
    (tmp_path / 'dannify.log').write_text('a line\n', encoding='utf-8')
    monkeypatch.setattr(api.state, 'data_dir', tmp_path)
    status = asyncio.run(api.support_report_status_endpoint())
    assert status['enabled'] is True and status['pending'] == 0
    out = asyncio.run(api.support_report_send_endpoint({
        'description': 'Lyrics are out of time on every song',
        'category': 'lyrics', 'contact': '', 'include_diagnostics': True,
    }))
    assert out['status'] == 'sent' and len(out['id']) == 8
    files = _unzip(_Receiver.got[-1]['diagnostics'])
    assert 'about.txt' in files and 'logs/dannify.log' in files


def test_window_errors_are_logged_once_and_not_without_limit():
    api._window_errors.clear()
    api._window_error_times.clear()

    def send(message):
        return asyncio.run(api.client_error_endpoint({'message': message, 'route': '/x'}))

    assert send('boom')['logged'] is True
    # The same again straight away: counted on the first, not logged again.
    assert send('boom')['logged'] is False
    assert api._window_errors[-1]['times'] == 2
    logged = [send(f'error {i}')['logged'] for i in range(40)]
    assert logged.count(True) == api.WINDOW_ERRORS_PER_MINUTE - 1
    api._window_errors.clear()
    api._window_error_times.clear()
