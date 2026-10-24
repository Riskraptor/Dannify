"""Where an update check learns of the latest release: the release's own
description first (a plain download), then GitHub's API (60 an hour per
address), then the release page, so a network that has used up the API's
allowance still hears of updates."""

from __future__ import annotations

import json
import urllib.error

import pytest

from dannify import updates

RELEASE = {
    'tag_name': 'v9.0.0',
    'body': 'notes',
    'assets': [
        {'name': 'Dannify-Setup-9.0.0.exe', 'size': 10,
         'browser_download_url': 'https://github.com/Riskraptor/Dannify/releases/download/v9.0.0/Dannify-Setup-9.0.0.exe'},
        {'name': 'package-9.0.0.json', 'size': 5,
         'browser_download_url': 'https://github.com/Riskraptor/Dannify/releases/download/v9.0.0/package-9.0.0.json'},
    ],
}


@pytest.fixture(autouse=True)
def stable(monkeypatch):
    monkeypatch.setitem(updates._settings, 'channel', 'stable')
    monkeypatch.delenv('DANNIFY_UPDATE_API', raising=False)


def _not_found(url):
    raise urllib.error.HTTPError(url, 404, 'Not Found', None, None)


def test_the_description_is_read_first_and_the_api_left_alone(monkeypatch):
    asked = []
    monkeypatch.setattr(updates, '_get_text', lambda url: asked.append(url) or json.dumps(RELEASE))
    monkeypatch.setattr(updates, '_get', lambda url: pytest.fail('the API was asked'))
    assert updates._fetch_latest()['tag_name'] == 'v9.0.0'
    assert asked == ['https://github.com/Riskraptor/Dannify/releases/latest/download/latest.json']


def test_a_release_without_a_description_is_read_from_the_api(monkeypatch):
    monkeypatch.setattr(updates, '_get_text', _not_found)
    monkeypatch.setattr(updates, '_get', lambda url: RELEASE)
    assert updates._fetch_latest() is RELEASE


def test_a_refused_api_falls_back_to_the_release_page(monkeypatch):
    monkeypatch.setattr(updates, '_from_description', lambda: _not_found('latest.json'))

    def refused():
        raise updates.RateLimited(1800)

    monkeypatch.setattr(updates, '_from_api', refused)

    class Landed:
        def __init__(self, request, timeout=0):
            assert request.get_method() == 'HEAD'

        def geturl(self):
            return 'https://github.com/Riskraptor/Dannify/releases/tag/v9.0.0'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    page = ''.join(
        f'<a href="/Riskraptor/Dannify/releases/download/v9.0.0/{n}" rel="nofollow">'
        for n in ('Dannify-Setup-9.0.0.exe', 'Dannify-Setup-9.0.0.exe.dsig', 'package-9.0.0.json', 'package-9.0.0.json')
    )
    monkeypatch.setattr(updates.urllib.request, 'urlopen', Landed)
    monkeypatch.setattr(updates, '_get_text', lambda url: page)
    found = updates._fetch_latest()
    assert found['tag_name'] == 'v9.0.0'
    assert [a['name'] for a in found['assets']] == [
        'Dannify-Setup-9.0.0.exe', 'Dannify-Setup-9.0.0.exe.dsig', 'package-9.0.0.json'
    ]
    assert found['assets'][0]['browser_download_url'] == (
        'https://github.com/Riskraptor/Dannify/releases/download/v9.0.0/Dannify-Setup-9.0.0.exe'
    )


def test_refused_everywhere_is_still_said_to_be_a_refusal(monkeypatch):
    def refused():
        raise updates.RateLimited(900)

    for name in ('_from_description', '_from_api', '_from_page'):
        monkeypatch.setattr(updates, name, refused)
    with pytest.raises(updates.RateLimited):
        updates._fetch_latest()


def test_a_description_that_is_not_a_release_is_not_believed(monkeypatch):
    monkeypatch.setattr(updates, '_get_text', lambda url: json.dumps({'tag_name': 'v9'}))
    with pytest.raises(ValueError):
        updates._from_description()


def test_check_now_pressed_again_and_again_asks_once(monkeypatch):
    monkeypatch.setattr(updates, 'FORCE_GAP', 20)
    monkeypatch.setattr(updates, '_cache', {'at': 0.0, 'result': None, 'tried': 0.0})
    asked = []
    monkeypatch.setattr(updates, '_fetch_latest', lambda: asked.append(1) or RELEASE)
    for _ in range(5):
        assert updates.check('8.0.0', force=True)['version'] == '9.0.0'
    assert len(asked) == 1
