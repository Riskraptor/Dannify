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


def test_only_a_few_wait(receiver, tmp_path, monkeypatch):
    monkeypatch.setattr(report, 'DAILY_LIMIT', 100)
    _Receiver.status = 500
    for _ in range(report.OUTBOX_KEEP + 3):
        report.send(tmp_path, _a_report(diag=None))
    assert report.pending(tmp_path) == report.OUTBOX_KEEP


def test_closed_until_there_is_a_server(monkeypatch, tmp_path):
    monkeypatch.delenv('DANNIFY_REPORT_URL', raising=False)
    monkeypatch.delenv('DANNIFY_WEB3FORMS_KEY', raising=False)
    monkeypatch.setattr(report, 'REPORT_ENDPOINT', '')
    monkeypatch.setattr(report, 'WEB3FORMS_KEY', '')
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


def test_two_logs_with_one_name_are_both_kept(tmp_path):
    import io
    import zipfile

    from dannify import report

    (tmp_path / 'data').mkdir()
    (tmp_path / 'elsewhere').mkdir()
    (tmp_path / 'data' / 'dannify.log').write_text('from the data folder', encoding='utf-8')
    other = tmp_path / 'elsewhere' / 'dannify.log'
    other.write_text('from somewhere else', encoding='utf-8')
    data = report.pack(tmp_path / 'data', '4.12.0', log_file=other)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    logs = sorted(n for n in names if n.startswith('logs/'))
    assert logs == ['logs/dannify-2.log', 'logs/dannify.log']


# --- By email, through Web3Forms --------------------------------------------------


class _Answer:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {'success': True}

    def json(self):
        return self._body


@pytest.fixture
def emailed(monkeypatch):
    """Web3Forms stood in for: what it was sent, and what it answers."""

    import requests

    sent = []
    answer = {'value': _Answer()}

    def fake_post(url, json=None, **kw):
        sent.append({'url': url, 'json': json, **kw})
        return answer['value']

    monkeypatch.delenv('DANNIFY_REPORT_URL', raising=False)
    monkeypatch.setattr(report, 'REPORT_ENDPOINT', '')
    monkeypatch.setenv('DANNIFY_WEB3FORMS_KEY', 'test-access-key')
    monkeypatch.setattr(requests, 'post', fake_post)
    return sent, answer


def test_a_report_is_emailed_with_its_diagnostics_written_in(emailed, tmp_path):
    sent, _ = emailed
    (tmp_path / 'dannify.log').write_text('started\ncookie=SECRET123 here\nthe last line\n', encoding='utf-8')
    zipped = report.pack(tmp_path, '4.14.0', settings={'theme': 'dark', 'yt_cookie': 'x'})
    r = {**_a_report(diag=zipped), 'contact': 'listener@example.com'}
    assert report.send(tmp_path, r) == 'sent'
    body = sent[-1]['json']
    assert sent[-1]['url'] == report.WEB3FORMS_URL
    assert body['access_key'] == 'test-access-key' and body['botcheck'] is False
    assert body['email'] == 'listener@example.com'
    assert r['id'] in body['subject'] and 'playback' in body['subject']
    text = body['message']
    assert text.startswith('It stops after a minute')
    assert 'Dannify 4.14.0' in text and 'theme' in text and 'the last line' in text
    assert 'SECRET123' not in text and 'yt_cookie' not in text


def test_an_email_that_did_not_go_waits(emailed, tmp_path):
    sent, answer = emailed
    answer['value'] = _Answer(200, {'success': False, 'message': 'Invalid access key'})
    assert report.send(tmp_path, _a_report(diag=None)) == 'queued'
    answer['value'] = _Answer()
    assert report.flush(tmp_path) == (1, 0)


def test_a_long_log_keeps_its_newest_end(tmp_path):
    lines = ''.join(f'line {i}\n' for i in range(20000))
    (tmp_path / 'dannify.log').write_text(lines, encoding='utf-8')
    text = report._diagnostics_text(report.pack(tmp_path, '4.14.0'), 5000)
    assert len(text) <= 5000 and 'line 19999' in text and 'line 0\n' not in text


def test_five_a_day_and_no_more(emailed, tmp_path):
    for _ in range(report.DAILY_LIMIT):
        report.send(tmp_path, _a_report(diag=None))
    with pytest.raises(report.TooMany):
        report.send(tmp_path, _a_report(diag=None))


def test_what_fills_the_hidden_field_is_thanked_and_sends_nothing(emailed, tmp_path, monkeypatch):
    sent, _ = emailed
    monkeypatch.setattr(api.state, 'data_dir', tmp_path)
    out = asyncio.run(api.support_report_send_endpoint({
        'description': 'Buy cheap things at my shop now', 'category': 'other', 'website': 'http://spam.example',
    }))
    assert out['status'] == 'sent' and sent == []


def test_an_idea_is_a_kind_of_its_own():
    assert report.clean_fields('Could it have a sleep timer?', 'idea', '')['category'] == 'idea'


# --- Sent by the window (a free form takes browser submissions only) ---------------


def test_by_email_the_app_prepares_and_the_window_sends(emailed, tmp_path, monkeypatch):
    sent, _ = emailed
    monkeypatch.setattr(api.state, 'data_dir', tmp_path)
    assert asyncio.run(api.support_report_status_endpoint())['mode'] == 'email'
    out = asyncio.run(api.support_report_send_endpoint({
        'description': 'The lyrics panel stays empty on every song', 'category': 'lyrics',
        'contact': 'me@example.com', 'include_diagnostics': False,
    }))
    assert out['status'] == 'prepared' and sent == []  # nothing left the app
    email = out['email']
    assert email['access_key'] == 'test-access-key' and email['email'] == 'me@example.com'
    assert email['report_id'] == out['id'] and out['url'] == report.WEB3FORMS_URL
    assert email['message'].startswith('The lyrics panel stays empty')


def test_an_email_the_window_could_not_send_waits_for_it(emailed, tmp_path, monkeypatch):
    monkeypatch.setattr(api.state, 'data_dir', tmp_path)
    email = report.email_body({**_a_report(diag=None), 'id': 'AB12CD34'}, 'old-key')
    asyncio.run(api.support_report_hold_endpoint({'email': email}))
    assert report.pending(tmp_path) == 1
    held = asyncio.run(api.support_report_held_endpoint())['emails']
    assert [e['report_id'] for e in held] == ['AB12CD34']
    assert held[0]['access_key'] == 'test-access-key'  # the key the app has now
    asyncio.run(api.support_report_done_endpoint({'id': 'AB12CD34'}))
    assert report.pending(tmp_path) == 0
