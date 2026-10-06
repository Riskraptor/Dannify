"""dannify.tags: song details read from and written into MP4 files."""

from __future__ import annotations

import struct

import pytest

from dannify import tags

MARK = b'AUDIO-CHUNK-ONE!'
COVER = bytes.fromhex('ffd8ffe000104a464946000101') + bytes(range(64)) + bytes.fromhex('ffd9')


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack('>I4s', 8 + len(payload), kind) + payload


def full(kind: bytes, payload: bytes) -> bytes:
    return box(kind, b'\0\0\0\0' + payload)


def mp4(moov_first: bool) -> bytes:
    """A minimal MP4 with one track whose one chunk is MARK, in mdat."""

    ftyp = box(b'ftyp', b'M4A \0\0\0\0M4A mp42isom')
    mdat_payload = MARK + bytes(64)

    def build(offset: int) -> bytes:
        stco = full(b'stco', struct.pack('>II', 1, offset))
        stbl = box(b'stbl', stco)
        trak = box(b'trak', box(b'mdia', box(b'minf', stbl)))
        mvhd = full(b'mvhd', struct.pack('>IIII', 0, 0, 1000, 3000) + bytes(80))
        return box(b'moov', mvhd + trak)

    if moov_first:
        size = len(build(0))
        offset = len(ftyp) + size + 8
        return ftyp + build(offset) + box(b'mdat', mdat_payload)
    offset = len(ftyp) + 8
    return ftyp + box(b'mdat', mdat_payload) + build(offset)


def chunk_offset(data: bytes) -> int:
    at = data.index(b'stco')
    return struct.unpack_from('>I', data, at + 12)[0]


@pytest.mark.parametrize('moov_first', [True, False])
def test_details_go_in_and_come_back_out_and_the_audio_stays_put(tmp_path, moov_first):
    song = tmp_path / 'song.m4a'
    song.write_bytes(mp4(moov_first))
    tags.write_mp4(
        song,
        title='Suzanna', artists=['Sauti Sol', 'Bien'], album='Midnight Train', date='2020',
        genre='Afropop', track=(3, 12), cover=(COVER, 'image/jpeg'),
        lyrics='Oh, Suzanna', video_id='KNEd-OkExKY',
    )
    found = tags.details(song)
    assert found['title'] == 'Suzanna'
    assert found['artist'] == 'Sauti Sol'
    assert found['albumartist'] == 'Sauti Sol'
    assert found['album'] == 'Midnight Train'
    assert (found['year'], found['genre'], found['track']) == ('2020', 'Afropop', 3)
    assert found['video_id'] == 'KNEd-OkExKY'
    assert found['lyrics'] == 'Oh, Suzanna'
    assert tags.cover(song) == (COVER, 'image/jpeg')
    assert tags.video_id(song) == 'KNEd-OkExKY'
    assert tags.lyrics(song) == 'Oh, Suzanna'
    # Wherever the metadata grew, the track still points at its audio.
    data = song.read_bytes()
    assert data[chunk_offset(data) : chunk_offset(data) + len(MARK)] == MARK


def test_a_second_write_changes_only_what_it_names(tmp_path):
    song = tmp_path / 'song.m4a'
    song.write_bytes(mp4(True))
    tags.write_mp4(song, title='Suzanna', album='Midnight Train', video_id='KNEd-OkExKY', cover=(COVER, 'image/png'))
    tags.write_mp4(song, title='Suzanna (Live)', video_id='KNEd-OkExKY')
    found = tags.details(song)
    assert (found['title'], found['album'], found['video_id']) == ('Suzanna (Live)', 'Midnight Train', 'KNEd-OkExKY')
    assert tags.cover(song) == (COVER, 'image/png')
    data = song.read_bytes()
    assert data.count(b'VIDEO_ID') == 1, 'the id was written twice'
    assert data[chunk_offset(data) : chunk_offset(data) + len(MARK)] == MARK


def test_an_empty_value_takes_the_detail_out(tmp_path):
    song = tmp_path / 'song.m4a'
    song.write_bytes(mp4(False))
    tags.write_mp4(song, title='Suzanna', genre='Afropop')
    tags.write_mp4(song, genre='')
    found = tags.details(song)
    assert (found['title'], found['genre']) == ('Suzanna', '')


def test_only_mp4_is_written(tmp_path):
    other = tmp_path / 'song.mp3'
    other.write_bytes(b'ID3')
    assert not tags.writable(other)
    with pytest.raises(tags.Unsupported):
        tags.write_mp4(other, title='x')


def fragmented(base_offset: bool) -> tuple[bytes, int]:
    """moov, sidx, then a moof and its mdat, the way YouTube serves a song.

    Returns the file and where MARK sits in it.
    """

    ftyp = box(b'ftyp', b'M4A \0\0\0\0M4A dashiso6')
    moov = box(b'moov', full(b'mvhd', struct.pack('>IIII', 0, 0, 1000, 3000) + bytes(80)))
    sidx = full(b'sidx', bytes(24))
    head = ftyp + moov + sidx

    def moof(base: int) -> bytes:
        if base_offset:
            tfhd = box(b'tfhd', struct.pack('>I', 0x000001) + struct.pack('>IQ', 1, base))
        else:
            tfhd = box(b'tfhd', struct.pack('>I', 0x020000) + struct.pack('>I', 1))
        return box(b'moof', box(b'traf', tfhd))

    size = len(moof(0))
    mark_at = len(head) + size + 8
    data = head + moof(mark_at) + box(b'mdat', MARK + bytes(32))
    return data, mark_at


def base_offset_of(data: bytes) -> int:
    at = data.index(b'tfhd')
    return struct.unpack_from('>Q', data, at + 12)[0]


def test_a_song_as_youtube_serves_it_takes_its_details(tmp_path):
    """Fragments that count from themselves move with the file as it is."""

    song = tmp_path / 'song.m4a'
    data, _ = fragmented(base_offset=False)
    song.write_bytes(data)
    tags.write_mp4(song, title='Suzanna', cover=(COVER, 'image/jpeg'), video_id='KNEd-OkExKY')
    assert tags.details(song)['title'] == 'Suzanna'
    assert tags.cover(song) == (COVER, 'image/jpeg')
    after = song.read_bytes()
    grown = len(after) - len(data)
    # Everything after the moov is the same bytes, just further along.
    assert after[-(len(data) - data.index(b'sidx') + 4):] == data[data.index(b'sidx') - 4:]
    assert grown > 0


def test_a_fragment_with_an_absolute_offset_is_moved_with_it(tmp_path):
    song = tmp_path / 'song.m4a'
    data, mark_at = fragmented(base_offset=True)
    assert data[mark_at : mark_at + len(MARK)] == MARK
    song.write_bytes(data)
    tags.write_mp4(song, title='Suzanna', cover=(COVER, 'image/jpeg'))
    after = song.read_bytes()
    moved = base_offset_of(after)
    assert after[moved : moved + len(MARK)] == MARK


def test_a_random_access_table_is_refused_and_the_file_left_alone(tmp_path):
    song = tmp_path / 'song.m4a'
    data, _ = fragmented(base_offset=False)
    data += box(b'mfra', full(b'tfra', bytes(16)))
    song.write_bytes(data)
    with pytest.raises(tags.Unsupported):
        tags.write_mp4(song, title='Suzanna')
    assert song.read_bytes() == data, 'a refused write must not touch the file'


def test_nothing_to_read_is_not_an_error(tmp_path):
    junk = tmp_path / 'song.m4a'
    junk.write_bytes(b'not audio at all')
    assert not any(tags.details(junk).values())
    assert tags.cover(junk) is None
    assert tags.video_id(junk) == ''
