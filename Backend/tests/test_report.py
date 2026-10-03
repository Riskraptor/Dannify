"""A problem report: one file with the logs, and nothing in it that signs in."""

from __future__ import annotations

import asyncio
import json
import zipfile

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


def test_the_report_holds_the_logs_the_window_errors_and_the_settings(tmp_path):
    (tmp_path / 'dannify.log').write_text('started\ncookie=SECRET1\nplayed a song\n', encoding='utf-8')
    (tmp_path / 'dannify.2026-10-01.log').write_text('older run\n', encoding='utf-8')
    (tmp_path / 'crash.log').write_text('Fatal Python error: boom\n', encoding='utf-8')
    (tmp_path / 'empty.log').write_text('', encoding='utf-8')
    path = report.build(
        tmp_path,
        '4.3.0',
        settings={'theme': 'dark', 'yt_cookie': 'SECRET2', 'max_parallel_downloads': 3},
        facts={'Playlists': 2},
        window_errors=[{'message': 'TypeError: x is undefined', 'route': '/library'}],
    )
    assert path.parent.name == 'reports' and path.suffix == '.zip'
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        assert {'about.txt', 'logs/dannify.log', 'logs/dannify.2026-10-01.log', 'logs/crash.log', 'window-errors.json'} <= names
        everything = ''.join(z.read(n).decode('utf-8') for n in names)
        about = z.read('about.txt').decode('utf-8')
        errors = json.loads(z.read('window-errors.json'))
    assert 'SECRET1' not in everything and 'SECRET2' not in everything
    assert 'Dannify 4.3.0' in about and 'theme: "dark"' in about and 'Playlists: 2' in about
    assert 'yt_cookie' not in about
    assert errors[0]['route'] == '/library'


def test_only_the_last_few_reports_are_kept(tmp_path):
    (tmp_path / 'dannify.log').write_text('x\n', encoding='utf-8')
    folder = tmp_path / 'reports'
    folder.mkdir()
    for i in range(7):
        (folder / f'Dannify-report-2026010{i}-000000.zip').write_bytes(b'old')
    report.build(tmp_path, '4.3.0')
    assert len(list(folder.glob('Dannify-report-*.zip'))) == report.KEEP_REPORTS


def test_a_huge_log_is_cut_to_its_newest_end(tmp_path):
    log = tmp_path / 'dannify.log'
    log.write_bytes(b'old line\n' * 50 + b'newest line\n')
    cut = report._tail(log, limit=40)
    assert cut.endswith('newest line\n')
    # Whole lines only: the cut lands on the start of one.
    assert all(line in ('old line', 'newest line') for line in cut.splitlines())
    assert len(cut) <= 40


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
