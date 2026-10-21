"""Songs from a watch list (a song's radio, autoplay), which YouTube Music
describes with other names than a search: every one came without its
picture and its length."""

from dannify import account, explorer


# Shaped as ytmusicapi's parse_watch_track gives it.
WATCH_TRACK = {
    'videoId': 'abc123DEF45',
    'title': 'Sura Yako',
    'length': '3:58',
    'thumbnail': [
        {'url': 'https://lh3.googleusercontent.com/x=w60-h60-l90-rj', 'width': 60, 'height': 60},
        {'url': 'https://lh3.googleusercontent.com/x=w120-h120-l90-rj', 'width': 120, 'height': 120},
    ],
    'artists': [{'name': 'Sauti Sol', 'id': 'UCx'}],
    'album': {'name': 'Live and Die in Afrika', 'id': 'MPRE1'},
}


def test_a_radio_song_has_its_picture_and_its_length():
    song = account.song_from_item(WATCH_TRACK)
    assert song['cover_url'] == 'https://lh3.googleusercontent.com/x=w544-h544-l90-rj'
    assert song['duration'] == 238
    assert song['name'] == 'Sura Yako' and song['artists'] == ['Sauti Sol']


def test_a_search_song_reads_as_before():
    item = {**WATCH_TRACK, 'thumbnails': WATCH_TRACK['thumbnail'], 'duration': '1:02:03'}
    del item['thumbnail'], item['length']
    song = account.song_from_item(item)
    assert song['cover_url'].endswith('=w544-h544-l90-rj')
    assert song['duration'] == 3723


def test_lengths_that_are_not_lengths_are_nothing():
    for text in ('', None, 'live', '3:4x', '1:2:3:4'):
        assert account._seconds_of(text) == 0


def test_the_browse_side_reads_either_name_too():
    assert explorer._thumb({'thumbnail': WATCH_TRACK['thumbnail']})
    assert explorer._thumb({'thumbnails': WATCH_TRACK['thumbnail']})
    assert explorer._thumb({}) == ''
