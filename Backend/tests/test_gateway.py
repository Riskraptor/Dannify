"""The key at the door, checked against the real app.

Built in a child process with its own data folder: the app reads where its
data lives at import time, and a test must never find the real one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

PROBE = textwrap.dedent('''
    import asyncio, json, sys
    sys.path.insert(0, sys.argv[1])
    import main
    from dannify import api

    app = main.build_app()

    async def call(path, host='127.0.0.1:8765', headers=(), method='GET', query='', scheme='http'):
        scope = {
            'type': 'http', 'http_version': '1.1', 'method': method,
            'scheme': scheme, 'path': path, 'raw_path': path.encode(),
            'query_string': query.encode(), 'root_path': '',
            'headers': [(b'host', host.encode())] + [
                (k.encode(), v.encode()) for k, v in headers
            ],
            'client': ('127.0.0.1', 5000), 'server': ('127.0.0.1', 8765),
        }
        got = {}
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await asyncio.sleep(3600)

        async def send(message):
            if message['type'] == 'http.response.start':
                got['status'] = message['status']
                got['headers'] = {k.decode().lower(): v.decode() for k, v in message['headers']}
        await app(scope, receive, send)
        return got

    async def main_():
        out = {}
        # Development: no key, loopback only.
        api.state.auth_token = ''
        out['dev_loopback'] = (await call('/api/version'))['status']
        out['dev_localhost'] = (await call('/api/version', host='localhost:5173'))['status']
        out['dev_rebound'] = (await call('/api/version', host='evil.example:8765'))['status']
        out['dev_no_host'] = (await call('/api/version', host=''))['status']
        # The window's way: a key.
        api.state.auth_token = 'k' * 43
        out['key_missing'] = (await call('/api/version'))['status']
        out['key_wrong'] = (await call('/api/version', headers=[('x-dannify-key', 'k' * 42 + 'x')]))['status']
        out['key_right'] = (await call('/api/version', headers=[('x-dannify-key', 'k' * 43)]))['status']
        out['cookie_right'] = (await call('/api/version', headers=[('cookie', 'dnf_session=' + 'k' * 43)]))['status']
        out['key_in_api_query'] = (await call('/api/version', query='k=' + 'k' * 43))['status']
        r = await call('/', query='k=' + 'k' * 43, scheme='https')
        out['cookie_attrs'] = r['headers'].get('set-cookie', '')
        r = await call('/api/version', headers=[('x-dannify-key', 'k' * 43), ('origin', 'https://evil.example')])
        out['cors_header'] = r['headers'].get('access-control-allow-origin', '')
        # An API path that matches nothing is a 404, not the interface.
        r = await call('/api/nothing-here', headers=[('x-dannify-key', 'k' * 43)])
        out['unknown_api'] = [r['status'], r['headers'].get('content-type', '')]
        return out

    print(json.dumps(asyncio.run(main_())))
''')


def test_the_gate(tmp_path):
    env = dict(os.environ)
    env['DANNIFY_DATA_DIR'] = str(tmp_path / 'data')
    env['WEB_GUI_LOCATION'] = str(BACKEND.parent / 'frontend')
    env.pop('DOWNLOAD_DIR', None)
    env.pop('HOST', None)
    run = subprocess.run(
        [sys.executable, '-c', PROBE, str(BACKEND)],
        cwd=str(BACKEND), env=env, capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, run.stderr[-3000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])

    assert out['dev_loopback'] == 200
    assert out['dev_localhost'] == 200
    # DNS rebinding: a page on another name that resolves here.
    assert out['dev_rebound'] == 404
    assert out['dev_no_host'] == 404

    assert out['key_missing'] == 404
    assert out['key_wrong'] == 404
    assert out['key_right'] == 200
    assert out['cookie_right'] == 200
    assert out['key_in_api_query'] == 404
    assert 'HttpOnly' in out['cookie_attrs']
    assert 'SameSite=Strict' in out['cookie_attrs']
    assert 'Max-Age=43200' in out['cookie_attrs']
    assert 'Secure' in out['cookie_attrs']
    # No origin is invited to read responses with the user's cookie.
    assert out['cors_header'] == ''
    assert out['unknown_api'][0] == 404
    assert 'html' not in out['unknown_api'][1]


def test_standalone_server_stays_on_this_machine_by_default():
    import ast

    tree = ast.parse((BACKEND / 'main.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, 'id', '') == 'DEFAULT_HOST' for t in node.targets
        ):
            call = node.value
            assert call.args[1].value == '127.0.0.1'
            return
    raise AssertionError('DEFAULT_HOST not found')
