"""Suggestions for the search box: tidied, never what was typed, and not
asked for twice."""

from __future__ import annotations

import asyncio

from dannify import explorer
from dannify.routes import explore as explore_routes


class _Fake:
    calls = 0

    def get_search_suggestions(self, query):
        type(self).calls += 1
        return [
            'sauti sol',
            'Sauti  Sol   suzanna',
            'sauti sol',  # twice
            'SAUTI SOL SUZANNA',  # and once more, shouting
            {'not': 'text'},
            '',
            'sauti sol melanin',
        ]


def test_suggestions_are_tidied_and_cached(monkeypatch):
    _Fake.calls = 0
    fake = _Fake()
    monkeypatch.setattr(explorer, '_ytm', lambda: fake)
    explorer.clear_cache()
    assert explorer.suggest('sauti') == ['sauti sol', 'Sauti Sol suzanna', 'sauti sol melanin']
    # What was typed is not offered back, however it was spaced or cased.
    assert explorer.suggest('  Sauti   SOL ') == ['Sauti Sol suzanna', 'sauti sol melanin']
    assert explorer.suggest('sauti', limit=1) == ['sauti sol']
    assert _Fake.calls == 2  # the third came from the cache
    assert explorer.suggest('   ') == [] and _Fake.calls == 2
    explorer.clear_cache()
    explorer.suggest('sauti')
    assert _Fake.calls == 3
    explorer.clear_cache()


def test_no_connection_is_no_suggestions_not_an_error(monkeypatch):
    def offline():
        raise ConnectionError('no route to host')

    monkeypatch.setattr(explorer, '_ytm', offline)
    explorer.clear_cache()
    got = asyncio.run(explore_routes.explore_suggest_endpoint(q='sauti', limit=8))
    assert got == {'suggestions': []}
    assert asyncio.run(explore_routes.explore_suggest_endpoint(q='  ', limit=8)) == {'suggestions': []}
