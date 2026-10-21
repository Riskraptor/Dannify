"""Payment details changed between releases: believed only when signed with
the release key, and never rolled back to an older file (support.accept_live)."""

import hashlib
import io
import json

import pytest

from dannify import signing, support, updates

SECRET = bytes(range(32))  # a key for these tests only
PUBLIC = signing.public_key(SECRET).hex()


def signed(details: dict) -> tuple[bytes, str]:
    raw = json.dumps(details, indent=2).encode('utf-8')
    statement = signing.statement('support', str(details['version']), hashlib.sha256(raw).hexdigest())
    return raw, signing.sign(SECRET, statement).hex()


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    kept = dict(support._config)
    monkeypatch.setattr(updates, 'PUBLIC_KEY', PUBLIC)
    yield
    support._config.clear()
    support._config.update(kept)
    support._live.clear()
    support._live_dir = None


NEW = {'version': 3, 'paypal': 'https://www.paypal.com/ncp/payment/PLB-NEWLINK123', 'mpesa': {'kind': 'till', 'number': '1234567'}}


def test_signed_details_are_believed():
    raw, sig = signed(NEW)
    found = support.accept_live(raw, sig, PUBLIC)
    assert found == {'paypal': NEW['paypal'], 'mpesa': NEW['mpesa'], 'version': 3}


def test_a_changed_file_is_not():
    raw, sig = signed(NEW)
    forged = raw.replace(b'PLB-NEWLINK123', b'PLB-SOMEONEELS')
    assert support.accept_live(forged, sig, PUBLIC) is None


def test_another_key_is_not():
    raw, _ = signed(NEW)
    other = signing.sign(bytes(range(1, 33)), signing.statement('support', '3', hashlib.sha256(raw).hexdigest())).hex()
    assert support.accept_live(raw, other, PUBLIC) is None


def test_an_older_file_put_back_is_not():
    raw, sig = signed({**NEW, 'version': 2})
    assert support.accept_live(raw, sig, PUBLIC, newer_than=3) is None
    assert support.accept_live(raw, sig, PUBLIC, newer_than=2) is not None


def test_a_release_signature_is_not_a_support_one():
    raw, _ = signed(NEW)
    release = signing.sign(SECRET, signing.statement('package', '3', hashlib.sha256(raw).hexdigest())).hex()
    assert support.accept_live(raw, release, PUBLIC) is None


def test_only_payment_fields_are_taken():
    raw, sig = signed({**NEW, 'enabled': False, 'repo': 'someone/else', 'link': 'https://ko-fi.com/x'})
    found = support.accept_live(raw, sig, PUBLIC)
    assert 'enabled' not in found and 'repo' not in found
    assert found['link'] == 'https://ko-fi.com/x'


def test_kept_details_are_used_and_still_checked(tmp_path):
    raw, sig = signed(NEW)
    (tmp_path / support.LIVE_NAME).write_bytes(raw)
    (tmp_path / (support.LIVE_NAME + signing.SIGNATURE_SUFFIX)).write_text(sig)
    support.init(tmp_path)
    out = support.config()
    assert out['paypal_link'] == NEW['paypal']
    assert out['mpesa']['number'] == '1234567'
    # Edited on disk: not believed, the built-in details again.
    (tmp_path / support.LIVE_NAME).write_bytes(raw.replace(b'1234567', b'7654321'))
    support.init(tmp_path)
    assert support.config()['mpesa']['number'] == '8496746'


def test_signed_details_are_still_checked_like_any(tmp_path):
    raw, sig = signed({'version': 4, 'paypal': 'https://evil.example/pay'})
    (tmp_path / support.LIVE_NAME).write_bytes(raw)
    (tmp_path / (support.LIVE_NAME + signing.SIGNATURE_SUFFIX)).write_text(sig)
    support.init(tmp_path)
    assert support.config()['paypal_link'] == ''


def test_fetched_from_the_repository_and_kept(tmp_path, monkeypatch):
    raw, sig = signed(NEW)
    asked = []

    def fake(request, timeout=0):
        asked.append(request.full_url)
        body = sig.encode() if request.full_url.endswith(signing.SIGNATURE_SUFFIX) else raw
        return io.BytesIO(body)

    monkeypatch.setattr(support.urllib.request, 'urlopen', fake)
    support.init(tmp_path)
    assert support.refresh_live() is True
    assert asked[0] == f'https://raw.githubusercontent.com/{updates.repo()}/main/config/support-live.json'
    assert (tmp_path / support.LIVE_NAME).read_bytes() == raw
    assert support.config()['paypal_link'] == NEW['paypal']
    # The same again: nothing new.
    assert support.refresh_live() is False


def test_nothing_reachable_changes_nothing(tmp_path, monkeypatch):
    def offline(request, timeout=0):
        raise OSError('offline')

    monkeypatch.setattr(support.urllib.request, 'urlopen', offline)
    support.init(tmp_path)
    assert support.refresh_live() is False
    assert support.config()['mpesa']['number'] == '8496746'


def test_the_ko_fi_page_can_change_too_but_only_to_an_https_page(tmp_path):
    raw, sig = signed({'version': 5, 'link': 'https://ko-fi.com/dannifyapp'})
    (tmp_path / support.LIVE_NAME).write_bytes(raw)
    (tmp_path / (support.LIVE_NAME + signing.SIGNATURE_SUFFIX)).write_text(sig)
    support.init(tmp_path)
    assert support.config()['link'] == 'https://ko-fi.com/dannifyapp'
    raw, sig = signed({'version': 6, 'link': 'javascript:alert(1)'})
    (tmp_path / support.LIVE_NAME).write_bytes(raw)
    (tmp_path / (support.LIVE_NAME + signing.SIGNATURE_SUFFIX)).write_text(sig)
    support.init(tmp_path)
    assert support.config()['link'] == ''


def test_a_way_to_give_can_be_taken_away(tmp_path):
    raw, sig = signed({'version': 7, 'mpesa': {}, 'paypal': ''})
    (tmp_path / support.LIVE_NAME).write_bytes(raw)
    (tmp_path / (support.LIVE_NAME + signing.SIGNATURE_SUFFIX)).write_text(sig)
    support.init(tmp_path)
    out = support.config()
    assert out['mpesa'] == {} and out['paypal_link'] == ''
    assert out['sponsors_link'] == 'https://github.com/sponsors/Riskraptor'


def test_sponsors_can_be_named_and_taken_away(tmp_path):
    raw, sig = signed({'version': 8, 'github': 'another-dev'})
    (tmp_path / support.LIVE_NAME).write_bytes(raw)
    (tmp_path / (support.LIVE_NAME + signing.SIGNATURE_SUFFIX)).write_text(sig)
    support.init(tmp_path)
    assert support.config()['sponsors_link'] == 'https://github.com/sponsors/another-dev'
    raw, sig = signed({'version': 9, 'github': ''})
    (tmp_path / support.LIVE_NAME).write_bytes(raw)
    (tmp_path / (support.LIVE_NAME + signing.SIGNATURE_SUFFIX)).write_text(sig)
    support.init(tmp_path)
    assert support.config()['sponsors_link'] == ''
