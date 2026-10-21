"""Which lyrics belong to a song: the ranking of the catalogue's uploads, and
what each version says about itself. Nothing here reaches the network."""

from dannify import lyrics


def _row(title='Girl Next Door', artist='Sauti Sol', duration=193, synced=None, album='Afrikan Sauce'):
    if synced is None:
        synced = '\n'.join(f'[00:{10 + i * 5:02d}.00] line {i}' for i in range(20))
    return {
        'trackName': title,
        'artistName': artist,
        'albumName': album,
        'duration': duration,
        'syncedLyrics': synced,
        'plainLyrics': 'line',
    }


def _score(row, title='Girl Next Door (feat. Tiwa Savage)', duration=193, album='Afrikan Sauce'):
    return lyrics._score_row(row, title, 'Sauti Sol', duration, album)


def test_who_a_song_features_does_not_make_it_another_song():
    plain_title = _score(_row())
    assert plain_title < 1, plain_title


def test_another_artist_or_title_is_never_taken():
    assert _score(_row(artist='Someone Else')) == float('inf')
    assert _score(_row(title='Melanin')) == float('inf')


def test_a_remix_or_sped_up_upload_loses_to_the_song_itself():
    assert _score(_row()) < _score(_row(title='Girl Next Door (Remix)'))
    assert _score(_row()) < _score(_row(title='Girl Next Door (Sped Up)'))
    # And for a remix, the remix's words are the ones wanted.
    remix = 'Girl Next Door (Remix)'
    assert _score(_row(title=remix), title=remix) < _score(_row(), title=remix)


def test_words_that_go_on_after_the_song_has_ended_are_another_cut():
    long_timing = '\n'.join(f'[0{i // 6}:{(i * 10) % 60:02d}.00] line {i}' for i in range(30))
    assert _score(_row()) < _score(_row(synced=long_timing))


def test_closer_length_wins_and_another_cut_loses_more():
    assert _score(_row(duration=194)) < _score(_row(duration=199))
    assert _score(_row(duration=199)) + 15 < _score(_row(duration=215))


def test_word_by_word_timing_and_the_same_album_are_preferred():
    words = '\n'.join(f'[00:{10 + i * 5:02d}.00] <00:{10 + i * 5:02d}.00> line {i}' for i in range(20))
    assert _score(_row(synced=words)) < _score(_row())
    assert _score(_row()) < _score(_row(album='Live at the Stadium'))


def test_untimed_lyrics_come_last():
    assert _score(_row(duration=230)) < _score(_row(synced=''))


def test_each_version_says_what_it_is(monkeypatch):
    words = '\n'.join(f'[00:{10 + i * 5:02d}.00] <00:{10 + i * 5:02d}.00> line {i}' for i in range(12))
    rows = [_row(duration=201), _row(synced=words, duration=193)]
    monkeypatch.setattr(lyrics, '_gather_candidates', lambda title, artist: rows)
    song = {'name': 'Girl Next Door', 'artists': ['Sauti Sol'], 'duration': 193, 'album_name': 'Afrikan Sauce'}
    versions = lyrics.fetch_all_versions(song)
    assert [v.about for v in versions] == [
        {'words': True, 'lines': 12, 'length': 193, 'diff': 0},
        {'words': False, 'lines': 20, 'length': 201, 'diff': 8},
    ]


def test_titles_lose_their_asides_only():
    assert lyrics._base_title('Yesterday - Remastered 2009') == 'Yesterday'
    assert lyrics._base_title('Hello ft. Someone') == 'Hello'
    assert lyrics._base_title('Essence (Live)') == 'Essence (Live)'


def test_two_lengths_of_one_song_keep_their_own_lyrics(monkeypatch):
    found = []

    def lookup(song, providers):
        found.append(song['duration'])
        return lyrics.Lyrics(synced=f"[00:01.00] cut of {song['duration']}")

    monkeypatch.setattr(lyrics, '_fetch_uncached', lookup)
    monkeypatch.setattr(lyrics, '_persist_cache', lambda: None)
    lyrics.clear_cache()
    a = {'name': 'Calm Down', 'artists': ['Rema'], 'duration': 220}
    b = {'name': 'Calm Down', 'artists': ['Rema'], 'duration': 239}
    assert 'cut of 220' in lyrics.fetch(a, ['lrclib']).synced
    assert 'cut of 239' in lyrics.fetch(b, ['lrclib']).synced
    assert 'cut of 220' in lyrics.fetch(a, ['lrclib']).synced
    assert found == [220, 239]


def test_what_was_kept_before_lengths_counted_is_still_used(monkeypatch):
    monkeypatch.setattr(lyrics, '_fetch_uncached', lambda song, providers: None)
    monkeypatch.setattr(lyrics, '_persist_cache', lambda: None)
    lyrics.clear_cache()
    kept = lyrics.Lyrics(synced='[00:01.00] kept')
    lyrics._lyrics_cache['rema|calm down'] = kept
    assert lyrics.fetch({'name': 'Calm Down', 'artists': ['Rema'], 'duration': 220}, ['lrclib']) is kept


def test_clearing_a_song_clears_every_length_of_it(monkeypatch):
    monkeypatch.setattr(lyrics, '_persist_cache', lambda: None)
    lyrics.clear_cache()
    for key in ('rema|calm down', 'rema|calm down|220', 'rema|calm down|239', 'rema|calm down remix|200'):
        lyrics._lyrics_cache[key] = None
    lyrics.clear_cache({'name': 'Calm Down', 'artists': ['Rema']})
    assert list(lyrics._lyrics_cache) == ['rema|calm down remix|200']


# --- Versions of a saved song -------------------------------------------------

import asyncio  # noqa: E402

from dannify.routes import lyrics as lyrics_routes  # noqa: E402

V1 = '[00:01.00] one\n[00:02.00] two'
V2 = '[00:01.50] one\n[00:02.50] two'


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _saved_song(monkeypatch, tmp_path, kept_text='', chosen=0, versions=(V1, V2)):
    song_file = tmp_path / 'Rema - Calm Down.dnf'
    song_file.write_bytes(b'x')
    monkeypatch.setattr(lyrics_routes, '_library_file', lambda f: song_file if f else None)
    # Thin tags, as a download can leave them: no artist.
    monkeypatch.setattr(lyrics_routes.library_mod, '_read_tags', lambda p: {'title': 'Calm Down', 'duration': 239})
    monkeypatch.setattr(lyrics, '_versions_of', lambda song: [lyrics.Lyrics(synced=v) for v in versions])
    monkeypatch.setattr(lyrics_routes, '_read_existing_lyrics', lambda full, a, t: kept_text)
    written, prefs = [], []
    monkeypatch.setattr(lyrics_routes, '_persist_lyrics', lambda full, a, t, text: written.append((a, t, text)))
    monkeypatch.setattr(lyrics_routes.lyrics_offsets, 'set', lambda t, a, o, v: prefs.append((t, a, v)))
    monkeypatch.setattr(lyrics_routes.lyrics_offsets, 'get_prefs', lambda t, a: {'offset': 0.0, 'version': chosen})
    return written, prefs


def test_a_saved_song_lists_its_versions_and_marks_the_one_kept(monkeypatch, tmp_path):
    _saved_song(monkeypatch, tmp_path, kept_text=V2)
    out = asyncio.run(lyrics_routes.lyrics_versions_endpoint(
        title='Calm Down', artist='Rema', album='', duration=239, url='', file='Rema - Calm Down.dnf'))
    assert len(out['versions']) == 2
    assert out['version'] == 1
    assert out['artist'] == 'Rema'


def test_of_two_uploads_that_differ_by_a_comma_the_one_picked_is_marked(monkeypatch, tmp_path):
    twin = '[00:01.50] one,\n[00:02.50] two'
    _saved_song(monkeypatch, tmp_path, kept_text=twin, chosen=2, versions=(V1, V2, twin))
    out = asyncio.run(lyrics_routes.lyrics_versions_endpoint(
        title='Calm Down', artist='Rema', album='', duration=239, url='', file='Rema - Calm Down.dnf'))
    assert out['version'] == 2


def test_picking_a_version_keeps_it_beside_the_saved_song(monkeypatch, tmp_path):
    written, prefs = _saved_song(monkeypatch, tmp_path)
    out = asyncio.run(lyrics_routes.lyrics_keep_endpoint(
        _Req({'file': 'Rema - Calm Down.dnf', 'version': 1, 'artist': 'Rema', 'title': 'Calm Down'})))
    assert out == {'kept': True}
    assert written == [('Rema', 'Calm Down', V2)]
    assert prefs == [('Calm Down', 'Rema', 1)]


def test_a_version_that_is_not_there_keeps_nothing(monkeypatch, tmp_path):
    written, _ = _saved_song(monkeypatch, tmp_path)
    out = asyncio.run(lyrics_routes.lyrics_keep_endpoint(
        _Req({'file': 'Rema - Calm Down.dnf', 'version': 7, 'artist': 'Rema'})))
    assert out == {'kept': False} and written == []


def test_the_same_lyrics_timed_the_same_are_the_same_version():
    assert lyrics.same_words(V1, V1 + '\n')
    assert not lyrics.same_words(V1, V2)
    assert not lyrics.same_words('', '')
