"""Version ordering, polite checks against GitHub, and rollback reporting."""

from __future__ import annotations

import email.message
import io
import json
import urllib.error

import pytest

from dannify import api, layout, updates


@pytest.mark.parametrize('newer, older', [
    ('4.7.0', '4.6.2'),
    ('4.7.0', '4.7.0-beta.2'),
    ('4.7.0-beta.10', '4.7.0-beta.2'),
    ('4.7.0-beta.1', '4.7.0-alpha.9'),
    ('4.7.0-beta.2', '4.6.2'),
    ('v4.10.0', '4.9.9'),
    ('4.7.0-rc.1', '4.7.0-beta.3'),
    ('4.7.0.1', '4.7.0'),
])
def test_versions_order_like_semver(newer, older):
    assert updates.is_newer(newer, older)
    assert not updates.is_newer(older, newer)


def test_equal_versions_are_not_newer():
    assert not updates.is_newer('4.7.0', '4.7.0')
    assert not updates.is_newer('4.7', '4.7.0')
    assert not updates.is_newer('4.7.0+build5', '4.7.0')


def test_old_style_and_odd_versions_still_compare():
    assert updates.is_newer('3.19.0', '3.18.1')
    assert not updates.is_newer('', '1.0.0')
    assert updates.is_newer('1.0.0', '')


class _Json:
    def __init__(self, data, etag=None):
        self._body = json.dumps(data).encode('utf-8')
        self.headers = {'ETag': etag} if etag else {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code, headers=None):
    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError('https://api.github.com/x', code, 'x', msg, io.BytesIO(b''))


def test_an_unchanged_release_is_asked_for_with_its_etag(monkeypatch):
    monkeypatch.setattr(updates, '_conditional', {})
    sent = []

    def urlopen(request, timeout=0):
        sent.append(request.get_header('If-none-match'))
        if len(sent) == 1:
            return _Json({'tag_name': 'v9'}, etag='"abc"')
        raise _http_error(304)

    monkeypatch.setattr(updates.urllib.request, 'urlopen', urlopen)
    assert updates._get('https://api.github.com/x') == {'tag_name': 'v9'}
    assert updates._get('https://api.github.com/x') == {'tag_name': 'v9'}
    assert sent == [None, '"abc"']


def test_a_rate_limit_holds_off_the_next_check(monkeypatch):
    calls = []

    def refuse():
        calls.append(1)
        raise updates.RateLimited(1800)

    monkeypatch.setattr(updates, '_fetch_latest', refuse)
    first = updates.check('4.0.0', force=True)
    assert first['error'] == 'rate_limited'
    updates.check('4.0.0')  # not forced: answered from the cache
    assert len(calls) == 1
    # Held for about the 30 minutes asked, not the usual one.
    held_until = updates._cache['at'] + updates.CHECK_TTL
    assert held_until - updates.time.time() > 1700


def test_an_ordinary_failure_is_retried_after_a_minute(monkeypatch):
    def offline():
        raise OSError('no network')

    monkeypatch.setattr(updates, '_fetch_latest', offline)
    updates.check('4.0.0', force=True)
    held_until = updates._cache['at'] + updates.CHECK_TTL
    assert 0 < held_until - updates.time.time() <= 61


def test_rate_limit_headers_are_read():
    assert updates._rate_limit_hold({'X-RateLimit-Remaining': '5'}) is None
    assert updates._rate_limit_hold({'Retry-After': '120'}) == 120.0
    reset = str(int(updates.time.time()) + 900)
    hold = updates._rate_limit_hold({'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': reset})
    assert 850 <= hold <= 900
    assert updates._rate_limit_hold({'X-RateLimit-Remaining': '0'}) == updates.RATE_LIMIT_HOLD


def test_a_403_that_is_a_rate_limit_is_reported_as_one(monkeypatch):
    monkeypatch.setattr(updates, '_conditional', {})
    monkeypatch.setattr(
        updates.urllib.request, 'urlopen',
        lambda request, timeout=0: (_ for _ in ()).throw(_http_error(403, {'X-RateLimit-Remaining': '0'})),
    )
    with pytest.raises(updates.RateLimited):
        updates._get('https://api.github.com/y')


def test_a_plain_403_is_not_mistaken_for_one(monkeypatch):
    monkeypatch.setattr(updates, '_conditional', {})
    monkeypatch.setattr(
        updates.urllib.request, 'urlopen',
        lambda request, timeout=0: (_ for _ in ()).throw(_http_error(403)),
    )
    with pytest.raises(urllib.error.HTTPError):
        updates._get('https://api.github.com/z')


@pytest.mark.parametrize('skipped, running, expected', [
    ('4.7.0', '4.6.2', {'version': '4.7.0', 'running': '4.6.2'}),
    ('4.7.0', '4.7.1', None),  # a later release installed: nothing to say
    ('', '4.6.2', None),
])
def test_status_says_when_an_update_was_rolled_back(monkeypatch, skipped, running, expected):
    monkeypatch.setattr(layout, 'skipped_version', lambda: skipped)
    monkeypatch.setattr(layout, 'pending', lambda: None)
    monkeypatch.setattr(layout, 'just_updated', lambda: None)
    monkeypatch.setattr(api.state, 'version', running)
    assert api.update_status_endpoint()['rolled_back'] == expected
