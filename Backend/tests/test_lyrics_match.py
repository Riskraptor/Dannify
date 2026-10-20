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
