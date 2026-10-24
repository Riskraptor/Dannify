"""YouTube Music's charts and new releases, where the listener is: shaped for
the window, cached, and the world's charts for a country it has none for."""

from __future__ import annotations

from dannify import explorer


class _Fake:
    asked: list = []

    def get_charts(self, country):
        type(self).asked.append(country)
        return {
            'countries': {'selected': {'text': 'Kenya' if country == 'KE' else 'Global'}, 'options': ['KE', 'NG', 'ZZ']},
            'videos': [
                {'title': 'Trending 20 Kenya', 'playlistId': 'OLAK5uy_trend', 'thumbnails': [{'url': 'https://i/t'}]},
                {'title': '', 'playlistId': 'nameless'},
            ],
            'artists': [
                {'title': 'Bien', 'browseId': 'UCbien', 'rank': '1', 'trend': 'up', 'subscribers': '771K',
                 'thumbnails': [{'url': 'https://i/b'}]},
                {'title': 'Diamond Platnumz', 'browseId': 'UCdiamond', 'rank': '2', 'trend': 'sideways'},
                {'title': 'No id'},
            ],
        }

    def get_explore(self):
        type(self).asked.append('explore')
        return {'new_releases': [
            {'title': 'Shing (feat. Toxic Lyrikali)', 'artists': [{'name': 'Kapitani'}], 'browseId': 'MPREb_shing',
             'type': 'Single', 'isExplicit': True, 'thumbnails': [{'url': 'https://i/s'}]},
            {'title': 'No id'},
        ]}


def _fake(monkeypatch):
    _Fake.asked = []
    monkeypatch.setattr(explorer, '_ytm', lambda: _Fake())
    explorer.clear_cache()


def test_the_charts_of_a_country(monkeypatch):
    _fake(monkeypatch)
    got = explorer.charts('ke')
    assert (got['country'], got['code']) == ('Kenya', 'KE')
    assert [p['name'] for p in got['playlists']] == ['Trending 20 Kenya']
    assert got['playlists'][0]['browse_id'] == 'OLAK5uy_trend'
    assert [(a['rank'], a['name'], a['trend']) for a in got['artists']] == [
        (1, 'Bien', 'up'), (2, 'Diamond Platnumz', 'neutral'),
    ]
    assert got['artists'][0]['subscribers'] == '771K'
    explorer.charts('KE')
    assert _Fake.asked == ['KE'], 'from the cache the second time'
    explorer.clear_cache()


def test_a_country_without_charts_gets_the_worlds(monkeypatch):
    _fake(monkeypatch)
    assert explorer.charts('US')['code'] == 'ZZ'
    assert explorer.charts('')['code'] == 'ZZ'
    assert explorer.charts('K3')['code'] == 'ZZ'
    explorer.clear_cache()


def test_new_releases(monkeypatch):
    _fake(monkeypatch)
    got = explorer.new_releases()
    assert got == [{
        'type': 'album', 'browse_id': 'MPREb_shing', 'name': 'Shing (feat. Toxic Lyrikali)', 'artist': 'Kapitani',
        'kind': 'Single', 'cover_url': got[0]['cover_url'], 'explicit': True,
    }]
    explorer.clear_cache()
