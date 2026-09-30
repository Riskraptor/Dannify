"""A download is put together away from the music folder.

The folder watcher and the library read the music folder while a download is
running. They used to find the raw stream, then a plain untagged copy, then a
tagged one, and only then the sealed song: a new artist appeared with a
picture pointing at a file that had no art yet and was gone a moment later,
and the song was listed twice. Nothing but the finished container may appear.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from dannify import downloader, library, vault
from dannify import lyrics as lyrics_mod

MP3 = b'ID3\x03\x00\x00\x00\x00\x00\x0f' + b'\xff\xfb\x90\x64' + bytes(range(256)) * 40
AUDIO = {'.mp3', '.m4a', '.flac', '.ogg', '.opus', '.webm', '.wav', '.aac', '.part', '.dnf'}


@pytest.fixture(autouse=True)
def fresh_vault():
    saved = (vault._master, vault._keys, vault._state, vault._key_path, vault._library, vault._busy)
    vault._master, vault._keys, vault._state = None, [], 'unknown'
    vault._key_path = vault._library = None
    vault._busy = False
    with vault._opened_lock:
        vault._opened.clear()
    library.invalidate_cache()
    yield
    (vault._master, vault._keys, vault._state, vault._key_path, vault._library, vault._busy) = saved
    library.invalidate_cache()


@pytest.fixture
def music(tmp_path, monkeypatch):
    data, music = tmp_path / 'data', tmp_path / 'Music'
    music.mkdir()
    vault.init(data)
    vault.attach(music)
    assert vault.ready()

    # No network: every outside lookup is stubbed.
    monkeypatch.setattr(downloader, '_fetch_itunes_genre', lambda song: '')
    monkeypatch.setattr(downloader, '_download_cover', lambda url: None)
    monkeypatch.setattr(downloader, 'find_match_for_video', lambda song, vid: None)
    from dannify import streaming

    monkeypatch.setattr(streaming, 'resolve_for_download', lambda vid: None)
    monkeypatch.setattr(
        lyrics_mod, 'fetch',
        lambda song, providers: lyrics_mod.Lyrics(plain='la la', synced='[00:01.00]la la'),
    )
    return music


def _audio_in(folder: Path) -> list[str]:
    return sorted(
        p.relative_to(folder).as_posix()
        for p in folder.rglob('*')
        if p.is_file() and (p.suffix.lower() in AUDIO or p.name.lower().endswith('.part'))
    )


class _FakeYDL:
    """Writes what yt-dlp would, and looks at the music folder while it does."""

    seen: list[list[str]] = []
    music: Path

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        out = Path(self.opts['outtmpl'] % {'ext': 'webm'})
        out.with_name(out.name + '.part').write_bytes(b'partial')
        _FakeYDL.seen.append(_audio_in(_FakeYDL.music))
        out.with_name(out.name + '.part').unlink()
        out.with_suffix('.mp3').write_bytes(MP3)
        _FakeYDL.seen.append(_audio_in(_FakeYDL.music))


def test_only_the_sealed_song_reaches_the_music_folder(music, monkeypatch):
    _FakeYDL.seen = []
    _FakeYDL.music = music
    monkeypatch.setattr(downloader.yt_dlp, 'YoutubeDL', _FakeYDL)

    # Watch the folder while tagging and sealing happen, too.
    real_seal = vault.seal
    during_seal: list[list[str]] = []

    def watching_seal(source, target, meta):
        during_seal.append(_audio_in(music))
        return real_seal(source, target, meta)

    monkeypatch.setattr(vault, 'seal', watching_seal)

    d = downloader.Downloader(music, lyrics_providers=['stub'], organize_by_artist=True)
    song = {
        'name': 'Suzanna', 'artists': ['Sauti Sol'], 'youtube_id': 'KNEd-OkExKY',
        'album_name': 'Midnight Train', 'cover_url': 'https://example.invalid/c.jpg',
        'genre': 'Afro-Pop',
    }
    name = d.download(song)

    assert name == 'Sauti Sol/Sauti Sol - Suzanna.dnf'
    # Nothing half-made was ever visible in the music folder.
    assert _FakeYDL.seen == [[], []]
    assert during_seal == [[]]
    # Afterwards: the song, its lyrics beside it, and nothing else.
    assert _audio_in(music) == ['Sauti Sol/Sauti Sol - Suzanna.dnf']
    assert (music / 'Sauti Sol' / 'Sauti Sol - Suzanna.lrc').read_text(encoding='utf-8') == '[00:01.00]la la'
    head, problem = vault.inspect(music / name)
    assert problem == '' or problem is None
    assert head['video_id'] == 'KNEd-OkExKY'

    # And the library sees one finished song by one artist.
    lib = library.library(music)
    assert [t['file'] for t in lib['tracks']] == [name]
    assert [a['name'] for a in lib['artists']] == ['Sauti Sol']
    assert lib['artists'][0]['cover'] == name


def test_a_failed_download_leaves_nothing_behind(music, monkeypatch, tmp_path):
    class Broken(_FakeYDL):
        def download(self, urls):
            out = Path(self.opts['outtmpl'] % {'ext': 'mp3'})
            out.write_bytes(MP3)
            _FakeYDL.bench = out.parent
            raise RuntimeError('network went away')

    _FakeYDL.music = music
    monkeypatch.setattr(downloader.yt_dlp, 'YoutubeDL', Broken)
    d = downloader.Downloader(music)
    with pytest.raises(RuntimeError):
        d.download({'name': 'X', 'artists': ['A'], 'youtube_id': 'aaaaaaaaaaa',
                    'album_name': 'Y', 'cover_url': 'c'})
    assert _audio_in(music) == []
    # The bench went with it.
    assert not _FakeYDL.bench.exists()


def test_brackets_in_a_title_do_not_lose_the_file(music, monkeypatch):
    # The encoder's output used to be found with a glob, and "[Live]" is a
    # glob pattern that matches nothing.
    class OddExt(_FakeYDL):
        def download(self, urls):
            Path(self.opts['outtmpl'] % {'ext': 'opus'}).write_bytes(b'OggS' + bytes(200))

    _FakeYDL.music = music
    monkeypatch.setattr(downloader.yt_dlp, 'YoutubeDL', OddExt)
    d = downloader.Downloader(music, audio_format='mp3')
    name = d.download({'name': 'Song [Live]', 'artists': ['A'], 'youtube_id': 'bbbbbbbbbbb',
                       'album_name': 'Y', 'cover_url': 'c'})
    assert name == 'A - Song [Live].dnf'
    assert (music / name).is_file()


def test_sweep_removes_only_old_benches(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.tempfile, 'gettempdir', lambda: str(tmp_path))
    old = tmp_path / 'dnf-dl-old'
    fresh = tmp_path / 'dnf-dl-fresh'
    other = tmp_path / 'someone-elses'
    for folder in (old, fresh, other):
        folder.mkdir()
        (folder / 'x.mp3').write_bytes(b'x')
    past = time.time() - 7 * 3600
    os.utime(old, (past, past))
    os.utime(other, (past, past))

    assert downloader.sweep_benches() == 1
    assert not old.exists()
    assert fresh.exists() and other.exists()


def test_a_rename_changes_the_fingerprint(tmp_path):
    (tmp_path / 'A - One.mp3').write_bytes(MP3)
    (tmp_path / 'B - Two.mp3').write_bytes(MP3)
    before = library.signature(tmp_path)
    # Same count, same newest time: only the name moved.
    os.replace(tmp_path / 'A - One.mp3', tmp_path / 'A - Uno.mp3')
    assert library.signature(tmp_path) != before


def test_concurrent_reads_scan_once(tmp_path, monkeypatch):
    import threading

    (tmp_path / 'A - One.mp3').write_bytes(MP3)
    calls = []
    real = library._build

    def slow_build(base):
        calls.append(base)
        time.sleep(0.2)
        return real(base)

    monkeypatch.setattr(library, '_build', slow_build)
    threads = [threading.Thread(target=library.library, args=(tmp_path,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_artist_folders_keep_their_letters(music, monkeypatch):
    _FakeYDL.music = music
    _FakeYDL.seen = []
    monkeypatch.setattr(downloader.yt_dlp, 'YoutubeDL', _FakeYDL)
    d = downloader.Downloader(music, organize_by_artist=True)
    names = []
    for i, artist in enumerate(['Beyoncé', '米津玄師', '아이유']):
        names.append(d.download({
            'name': f'Song {i}', 'artists': [artist], 'youtube_id': f'vid{i:08d}',
            'album_name': 'A', 'cover_url': 'c',
        }))
    assert [n.split('/')[0] for n in names] == ['Beyoncé', '米津玄師', '아이유']


def test_a_different_recording_with_the_same_name_does_not_replace_the_first(music, monkeypatch):
    # "Intro" on two albums by the same artist.
    _FakeYDL.music = music
    _FakeYDL.seen = []
    monkeypatch.setattr(downloader.yt_dlp, 'YoutubeDL', _FakeYDL)
    d = downloader.Downloader(music, organize_by_artist=True)
    first = d.download({'name': 'Intro', 'artists': ['The xx'], 'youtube_id': 'aaaaaaaaaaa',
                        'album_name': 'xx', 'cover_url': 'c'})
    second = d.download({'name': 'Intro', 'artists': ['The xx'], 'youtube_id': 'bbbbbbbbbbb',
                         'album_name': 'Coexist', 'cover_url': 'c'})
    again = d.download({'name': 'Intro', 'artists': ['The xx'], 'youtube_id': 'bbbbbbbbbbb',
                        'album_name': 'Coexist', 'cover_url': 'c'})

    assert first == 'The xx/The xx - Intro.dnf'
    assert second == 'The xx/The xx - Intro (2).dnf'
    # The same recording again is found, not saved a third time.
    assert again == second
    heads = {n: vault.inspect(music / n)[0]['video_id'] for n in (first, second)}
    assert heads == {first: 'aaaaaaaaaaa', second: 'bbbbbbbbbbb'}
