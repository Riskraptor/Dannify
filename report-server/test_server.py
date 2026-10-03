"""The report server takes what the app sends, and only the token reads it."""

import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('REPORT_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('REPORT_ADMIN_TOKEN', 'secret-token')
    sys.modules.pop('server', None)
    sys.path.insert(0, str(Path(__file__).parent))
    import server
    return TestClient(server.app)


def _zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('about.txt', 'Dannify 4.6.0')
    return buf.getvalue()


def test_a_report_is_received_kept_and_read_back(client):
    r = client.post('/reports', data={'id': 'AB12CD34', 'version': '4.6.0', 'category': 'lyrics',
                                      'description': 'Lyrics run a second late', 'contact': ''},
                    files={'diagnostics': ('d.zip', _zip(), 'application/zip')})
    assert r.status_code == 201 and r.json()['status'] == 'received'
    # The app retrying the same report does not make a second one.
    again = client.post('/reports', data={'id': 'AB12CD34', 'description': 'Lyrics run a second late'})
    assert again.json()['status'] == 'already received'
    assert client.get('/api/reports').status_code == 401
    listed = client.get('/api/reports', headers={'Authorization': 'Bearer secret-token'}).json()
    assert [x['id'] for x in listed] == ['AB12CD34'] and listed[0]['diagnostics'] is True
    z = client.get('/api/reports/AB12CD34/zip', headers={'Authorization': 'Bearer secret-token'})
    assert z.status_code == 200 and z.content[:2] == b'PK'
    gone = client.delete('/api/reports/AB12CD34', headers={'Authorization': 'Bearer secret-token'})
    assert gone.json() == {'deleted': True}


def test_what_is_not_a_report_is_refused(client):
    assert client.post('/reports', data={'id': 'bad id!', 'description': 'long enough text'}).status_code == 400
    assert client.post('/reports', data={'id': 'AB12CD35', 'description': 'short'}).status_code == 400
    r = client.post('/reports', data={'id': 'AB12CD36', 'description': 'long enough text'},
                    files={'diagnostics': ('d.zip', b'not a zip at all', 'application/zip')})
    assert r.status_code == 400


def test_one_address_cannot_flood_it(client, monkeypatch):
    import server
    monkeypatch.setattr(server, 'PER_HOUR', 3)
    codes = [client.post('/reports', data={'id': f'FLOOD00{i}', 'description': 'long enough text'}).status_code
             for i in range(5)]
    assert codes[:3] == [201, 201, 201] and codes[3:] == [429, 429]
