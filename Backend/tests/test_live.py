"""Fixes every copy takes without an update (live.py): believed only when the
release key signed them, never rolled back, and applied as they arrive."""

import hashlib
import io
import json

import pytest

from dannify import innertube, live, signing, updates

SECRET = bytes(range(32))  # a key for these tests only
PUBLIC = signing.public_key(SECRET).hex()


def signed(details: dict, kind: str = 'live') -> tuple[bytes, str]:
    raw = json.dumps(details, indent=2).encode('utf-8')
    return raw, signing.sign(SECRET, signing.statement(kind, str(details['version']), hashlib.sha256(raw).hexdigest())).hex()


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(updates, 'PUBLIC_KEY', PUBLIC)
    live._live.clear()
    live._listeners.clear()
    live._dir = None
    kept = dict(innertube._clients), dict(innertube._base_clients)
    yield
    live._live.clear()
    live._listeners.clear()
    innertube._clients, innertube._base_clients = kept
    innertube._live_clients, innertube._live_order = {}, ()


CLIENT = {
    'clientName': 'ANDROID_VR',
    'clientVersion': '1.71.0',
    'clientId': '28',
    'userAgent': 'com.google.android.apps.youtube.vr.oculus/1.71.0 (Linux; U; Android 12L)',
}


def test_signed_is_believed_and_only_its_fields_taken():
    raw, sig = signed({'version': 2, 'clients': {'X': CLIENT}, 'repo': 'someone/else'})
    found = live.accept(raw, sig, PUBLIC)
    assert found == {'version': 2, 'clients': {'X': CLIENT}}


def test_changed_older_or_another_kind_is_not():
    raw, sig = signed({'version': 2, 'notice': {'id': 'a', 'text': 'hi'}})
    assert live.accept(raw.replace(b'hi', b'yo'), sig, PUBLIC) is None
    assert live.accept(raw, sig, PUBLIC, newer_than=3) is None
    raw, support_sig = signed({'version': 2}, kind='support')
    assert live.accept(raw, support_sig, PUBLIC) is None


def test_an_emergency_is_for_the_versions_it_names():
    raw, sig = signed({'version': 4, 'emergency': {'version': '4.15.0.1', 'from': '4.15.0', 'notes': {'en': 'Songs play again'}}})
    live._take(live.accept(raw, sig, PUBLIC))
    assert live.status('4.15.0')['emergency'] == {'version': '4.15.0.1', 'notes': {'en': 'Songs play again'}}
    assert live.status('4.15.0.1')['emergency'] is None, 'already has it'
    assert live.status('4.14.1')['emergency'] is None, 'older than the range'
    assert live.status('4.16.0')['emergency'] is None


def test_a_notice_until_its_time_is_up():
    raw, sig = signed({'version': 5, 'notice': {'id': 'outage', 'text': {'en': 'YouTube is down'}, 'until': 2000}})
    live._take(live.accept(raw, sig, PUBLIC))
    assert live.status('4.15.0', now=1000)['notice'] == {'id': 'outage', 'text': {'en': 'YouTube is down'}}
    assert live.status('4.15.0', now=3000)['notice'] is None


def test_new_identities_reach_youtube_at_once_and_go_when_taken_away():
    live.on_change(lambda found: innertube.use_live(found.get('clients')))
    raw, sig = signed({'version': 6, 'clients': {'ANDROID_VR_1_65_10': CLIENT, 'BAD': {'clientName': 'x'}, '_order': ['ANDROID_VR_1_65_10', 'VISIONOS']}})
    live._take(live.accept(raw, sig, PUBLIC))
    assert innertube._clients['ANDROID_VR_1_65_10']['clientVersion'] == '1.71.0'
    assert 'BAD' not in innertube._clients, 'an identity without its user agent is not taken'
    assert innertube._stream_order() == ('ANDROID_VR_1_65_10', 'VISIONOS')
    raw, sig = signed({'version': 7})
    live._take(live.accept(raw, sig, PUBLIC))
    assert innertube._clients['ANDROID_VR_1_65_10']['clientVersion'] == '1.65.10'
    assert innertube._stream_order() == innertube._STREAM_ORDER


def test_fetched_kept_and_read_back(tmp_path, monkeypatch):
    raw, sig = signed({'version': 3, 'notice': {'id': 'n', 'text': 'hello'}})

    def fake(request, timeout=0):
        return io.BytesIO(sig.encode() if request.full_url.endswith(signing.SIGNATURE_SUFFIX) else raw)

    monkeypatch.setattr(live.urllib.request, 'urlopen', fake)
    live.init(tmp_path)
    assert live.refresh() is True
    assert live.refresh() is False, 'the same again is nothing new'
    assert (tmp_path / live.NAME).read_bytes() == raw
    live._live.clear()
    live.init(tmp_path)
    assert live.status('4.15.0')['notice']['id'] == 'n'
    # Edited on disk: not believed.
    (tmp_path / live.NAME).write_bytes(raw.replace(b'hello', b'howdy'))
    live._live.clear()
    live.init(tmp_path)
    assert live.status('4.15.0')['notice'] is None


def test_nothing_reachable_changes_nothing(tmp_path, monkeypatch):
    def offline(request, timeout=0):
        raise OSError('offline')

    monkeypatch.setattr(live.urllib.request, 'urlopen', offline)
    live.init(tmp_path)
    assert live.refresh() is False
    assert live.status('4.15.0') == {'version': 0, 'emergency': None, 'notice': None}
