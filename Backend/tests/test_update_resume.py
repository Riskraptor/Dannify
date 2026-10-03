"""A setup download that was cut off carries on where it stopped, and only
when the file on the server is still the same one."""

from __future__ import annotations

import http.server
import threading

import pytest

from dannify import updates

BODY = bytes(range(256)) * 400  # 100 KiB


class _Server(http.server.BaseHTTPRequestHandler):
    etag = '"v1"'
    seen: list = []

    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):  # noqa: N802
        rng = self.headers.get('Range')
        if_range = self.headers.get('If-Range')
        type(self).seen.append((rng, if_range))
        if rng and (if_range is None or if_range == self.etag):
            start = int(rng.split('=')[1].split('-')[0])
            part = BODY[start:]
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{len(BODY) - 1}/{len(BODY)}')
            self.send_header('Content-Length', str(len(part)))
            self.send_header('ETag', self.etag)
            self.end_headers()
            self.wfile.write(part)
            return
        self.send_response(200)
        self.send_header('Content-Length', str(len(BODY)))
        self.send_header('ETag', self.etag)
        self.end_headers()
        self.wfile.write(BODY)


@pytest.fixture
def server(monkeypatch):
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Server)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    monkeypatch.setenv('DANNIFY_UPDATE_API', base)
    _Server.seen = []
    _Server.etag = '"v1"'
    yield base
    httpd.shutdown()


def test_a_download_cut_off_carries_on_from_where_it_stopped(server, tmp_path):
    part = tmp_path / 'Dannify-Setup-9.9.9.exe.part'
    part.write_bytes(BODY[:30000])
    (tmp_path / 'Dannify-Setup-9.9.9.exe.part.tag').write_text('"v1"', encoding='utf-8')

    got = updates.download(f'{server}/Dannify-Setup-9.9.9.exe', tmp_path)

    assert got.read_bytes() == BODY
    assert _Server.seen[-1] == ('bytes=30000-', '"v1"')
    assert not part.exists() and not (tmp_path / 'Dannify-Setup-9.9.9.exe.part.tag').exists()


def test_a_changed_file_is_fetched_whole_not_spliced(server, tmp_path):
    _Server.etag = '"v2"'
    part = tmp_path / 'Dannify-Setup-9.9.9.exe.part'
    part.write_bytes(b'from the old file' * 100)
    (tmp_path / 'Dannify-Setup-9.9.9.exe.part.tag').write_text('"v1"', encoding='utf-8')

    got = updates.download(f'{server}/Dannify-Setup-9.9.9.exe', tmp_path)

    assert got.read_bytes() == BODY


def test_a_partial_copy_without_its_tag_starts_over(server, tmp_path):
    (tmp_path / 'Dannify-Setup-9.9.9.exe.part').write_bytes(b'junk')

    got = updates.download(f'{server}/Dannify-Setup-9.9.9.exe', tmp_path)

    assert got.read_bytes() == BODY
    assert _Server.seen[-1] == (None, None)


def test_old_partial_downloads_and_their_tags_are_pruned(tmp_path):
    (tmp_path / 'Dannify-Setup-4.0.0.exe.part').write_bytes(b'x')
    (tmp_path / 'Dannify-Setup-4.0.0.exe.part.tag').write_text('"v1"')
    removed = updates.prune_downloads(tmp_path, '4.3.0')
    assert sorted(removed) == ['Dannify-Setup-4.0.0.exe.part', 'Dannify-Setup-4.0.0.exe.part.tag']
