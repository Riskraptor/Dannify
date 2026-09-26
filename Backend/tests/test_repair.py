"""Telling a broken saved track from a good one, and putting it back.

Nothing here touches the network: the downloader is replaced with one that
writes a small made-up track, which is all a repair needs to be exercised end
to end, from the problem being found to the new file sitting at the old path.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path

import pytest

from dannify import library, repair, vault

MP3 = b'ID3\x03\x00\x00\x00\x00\x00\x0f' + b'\xff\xfb\x90\x64' + bytes(range(256)) * 40
# Not audio of any kind, and not by chance: random bytes start like an MP3
# frame one time in two thousand, which is a test that fails once a month.
NOISE = b'\x12\x34\x56\x78' * 1000


@pytest.fixture(autouse=True)
def key():
    """A key of our own for every test, and the real module state put back."""

    saved = (vault._master, vault._state, vault._busy, vault._keys, vault._key_path)
    vault._master = secrets.token_bytes(32)
    vault._state = 'ready'
    vault._busy = False
    vault._keys = []
    vault._key_path = None
    library.invalidate_cache()
    yield vault._master
    vault._master, vault._state, vault._busy, vault._keys, vault._key_path = saved
    library.invalidate_cache()


def sealed(folder: Path, name: str, payload: bytes = MP3, ext: str = '.mp3', **meta) -> Path:
    """A container holding *payload*, sealed with whatever key is loaded."""

    folder.mkdir(parents=True, exist_ok=True)
    plain = folder / (Path(name).stem + ext)
    plain.write_bytes(payload)
    head = {'title': Path(name).stem.partition(' - ')[2] or Path(name).stem, 'artist': 'Someone'}
    head.update(meta)
    return vault.seal(plain, folder / name, head)


def locked(folder: Path, name: str, **meta) -> Path:
    """A container sealed with a key that is not the loaded one."""

    mine = vault._master
    vault._master = secrets.token_bytes(32)
    try:
        return sealed(folder, name, **meta)
    finally:
        vault._master = mine


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------
def test_a_good_track_is_fine(tmp_path):
    path = sealed(tmp_path, 'A - Good.dnf')
    head, problem = vault.inspect(path)
    assert problem == ''
    assert head['title'] == 'Good'


def test_a_track_sealed_with_another_key_is_locked(tmp_path):
    path = locked(tmp_path, 'A - Theirs.dnf')
    head, problem = vault.inspect(path)
    assert (head, problem) == (None, vault.LOCKED)


def test_every_track_is_locked_when_there_is_no_key(tmp_path):
    path = sealed(tmp_path, 'A - Mine.dnf')
    vault._master = None
    assert vault.inspect(path) == (None, vault.LOCKED)


def test_a_track_cut_short_is_damaged(tmp_path):
    path = sealed(tmp_path, 'A - Short.dnf')
    data = path.read_bytes()
    path.write_bytes(data[: len(data) - 500])
    head, problem = vault.inspect(path)
    assert problem == vault.DAMAGED
    assert head is not None  # the header still reads, and names the track


def test_a_track_ending_in_unwritten_space_is_damaged(tmp_path):
    path = sealed(tmp_path, 'A - Zeros.dnf')
    data = bytearray(path.read_bytes())
    data[-64:] = bytes(64)
    path.write_bytes(bytes(data))
    assert vault.inspect(path)[1] == vault.DAMAGED


def test_a_payload_that_is_not_audio_is_damaged(tmp_path):
    path = sealed(tmp_path, 'A - Noise.dnf', payload=NOISE)
    assert vault.inspect(path)[1] == vault.DAMAGED


def test_a_kind_it_does_not_know_is_given_the_benefit_of_the_doubt(tmp_path):
    path = sealed(tmp_path, 'A - Odd.dnf', payload=secrets.token_bytes(4000), ext='.webm')
    assert vault.inspect(path)[1] == ''


@pytest.mark.parametrize('content', [b'', b'DNF1', b'not a container at all' * 10])
def test_things_that_are_not_containers_are_damaged(tmp_path, content):
    path = tmp_path / 'x.dnf'
    path.write_bytes(content)
    assert vault.inspect(path) == (None, vault.DAMAGED)


def test_a_header_length_past_the_end_is_damaged(tmp_path):
    path = sealed(tmp_path, 'A - Head.dnf')
    data = path.read_bytes()
    path.write_bytes(data[:24 + 10])
    assert vault.inspect(path)[1] == vault.DAMAGED


@pytest.mark.parametrize(
    'ext,lead,ok',
    [
        ('.mp3', b'ID3\x04\x00\x00\x00\x00', True),
        ('.mp3', b'\xff\xfb\x90\x00\x00\x00\x00\x00', True),
        ('.mp3', b'RIFF\x00\x00\x00\x00', True),
        ('.mp3', b'\x12\x34\x56\x78\x9a\xbc\xde\xf0', False),
        ('.m4a', b'\x00\x00\x00\x20ftypM4A ', True),
        ('.m4a', b'ID3\x04\x00\x00\x00\x00', False),
        ('.flac', b'fLaC\x00\x00\x00\x22', True),
        ('.opus', b'OggS\x00\x02\x00\x00', True),
        ('.ogg', b'fLaC\x00\x00\x00\x22', False),
        ('.wav', b'RIFF\x24\x08\x00\x00', True),
        ('.aac', b'\xff\xf1\x50\x80\x00\x1f\xfc\x00', True),
        ('.xyz', b'\x00\x00\x00\x00\x00\x00\x00\x00', True),
    ],
)
def test_audio_signatures(ext, lead, ok):
    assert vault._looks_like(ext, lead + bytes(8)) is ok


def test_a_file_that_cannot_be_opened_is_not_called_broken(tmp_path):
    assert vault.inspect(tmp_path / 'not-there.dnf') == (None, '')


# ---------------------------------------------------------------------------
# The library says which tracks are broken, and does not play them
# ---------------------------------------------------------------------------
def test_the_library_marks_broken_tracks_and_keeps_them_out_of_lookups(tmp_path):
    sealed(tmp_path / 'A', 'A - Good.dnf', video_id='GOODGOODGOO', artist='A')
    locked(tmp_path / 'B', 'B - Locked.dnf', video_id='LOCKLOCKLOC')
    short = sealed(tmp_path / 'C', 'C - Short.dnf', video_id='SHORTSHORTS', artist='C')
    short.write_bytes(short.read_bytes()[:-300])

    data = library.library(tmp_path)
    problems = {t['file']: t['problem'] for t in data['tracks']}
    assert problems == {
        'A/A - Good.dnf': '',
        'B/B - Locked.dnf': vault.LOCKED,
        'C/C - Short.dnf': vault.DAMAGED,
    }
    # Playing "Short" from search must stream it, not hand over the broken file.
    assert set(data['by_video_id']) == {'GOODGOODGOO'}
    assert library.locate(tmp_path, video_id='SHORTSHORTS') is None
    assert library.locate(tmp_path, artist='C', title='Short') is None
    assert library.locate(tmp_path, video_id='GOODGOODGOO')['file'] == 'A/A - Good.dnf'


# ---------------------------------------------------------------------------
# identify: what to download again
# ---------------------------------------------------------------------------
def test_identify_prefers_the_header(tmp_path):
    path = sealed(
        tmp_path, 'A, B - Song.dnf', title='Song', artist='A', artists=['A', 'B'],
        album='Album', duration=201, track_number=4, video_id='HEADHEADHEA',
    )
    head, _ = vault.inspect(path)
    song = repair.identify(tmp_path, path, head)
    assert song['name'] == 'Song'
    assert song['artists'] == ['A', 'B']
    assert song['album_name'] == 'Album'
    assert song['duration'] == 201
    assert song['track_number'] == 4
    assert song['youtube_id'] == 'HEADHEADHEA'


def test_identify_reads_the_folder_index_for_a_locked_track(tmp_path):
    folder = tmp_path / 'dancelo musiq'
    path = locked(folder, 'dancelo musiq - Nobody.dnf')
    (folder / vault.INDEX).write_text(json.dumps({
        'dancelo musiq - Nobody.dnf': {
            'title': 'Nobody', 'artist': 'dancelo musiq', 'video_id': 'EjreKstObTM',
        },
    }), encoding='utf-8')
    song = repair.identify(tmp_path, path, None)
    assert song['name'] == 'Nobody'
    assert song['artists'] == ['dancelo musiq']
    assert song['youtube_id'] == 'EjreKstObTM'


def test_identify_reads_the_top_index_keyed_by_path(tmp_path):
    path = locked(tmp_path / 'X', 'X - Tune.dnf')
    (tmp_path / vault.INDEX).write_text(json.dumps({
        'X/X - Tune.dnf': {'title': 'Tune', 'artist': 'X', 'video_id': 'TOPTOPTOPTO'},
    }), encoding='utf-8')
    assert repair.identify(tmp_path, path, None)['youtube_id'] == 'TOPTOPTOPTO'


def test_identify_falls_back_to_the_filename(tmp_path):
    path = locked(tmp_path, 'Bensoul, Vic West - Nairobi.dnf')
    song = repair.identify(tmp_path, path, None)
    assert song['name'] == 'Nairobi'
    assert song['artists'] == ['Bensoul', 'Vic West']
    assert 'youtube_id' not in song  # a search, then


def test_identify_ignores_a_video_id_that_is_not_one(tmp_path):
    path = locked(tmp_path, 'A - B.dnf')
    (tmp_path / vault.INDEX).write_text(json.dumps({
        'A - B.dnf': {'video_id': 'nope'},
    }), encoding='utf-8')
    assert 'youtube_id' not in repair.identify(tmp_path, path, None)


# ---------------------------------------------------------------------------
# fix: one track, in place
# ---------------------------------------------------------------------------
class FakeDownloader:
    """Stands in for the real one: writes a sealed track and a lyrics file."""

    audio_format = 'mp3'
    audio_bitrate = '320'
    output_template = '{artists} - {title}'
    lyrics_providers = ['lrclib']
    lyrics_storage = 'sidecar'
    organize_by_artist = True


@pytest.fixture
def downloads(monkeypatch):
    """Replace Downloader.download; record what it was asked for."""

    from dannify import downloader as dl

    asked: list[dict] = []
    behaviour = {'fail': None, 'lyrics': True, 'payload': MP3}

    def download(self, song, progress_cb=None, subdir=None):
        asked.append(dict(song))
        if progress_cb:
            progress_cb(50.0, 'Downloading')
        if behaviour['fail'] is not None:
            raise behaviour['fail']
        base = self._format_basename(song)
        plain = self.download_dir / f'{base}.mp3'
        plain.write_bytes(behaviour['payload'])
        if behaviour['lyrics']:
            plain.with_suffix('.lrc').write_text('[00:01.00]la la', encoding='utf-8')
        vid = song.get('youtube_id') or 'FOUNDFOUNDF'
        out = vault.seal(plain, plain.with_suffix('.dnf'), {
            'title': song['name'], 'artist': (song.get('artists') or [''])[0],
            'artists': song.get('artists') or [], 'video_id': vid,
        })
        # Nothing plain may be left where the download happened either.
        assert not plain.exists()
        return out.name

    monkeypatch.setattr(dl.Downloader, 'download', download)
    # Whether this machine is online is not what these tests are about.
    behaviour['online'] = True
    monkeypatch.setattr(repair, '_online', lambda: behaviour['online'])

    # A search that finds the track itself, unless a test says otherwise.
    from dannify import providers

    searched: list[dict] = []
    behaviour['match'] = lambda song: {
        'videoId': 'FOUNDFOUNDF',
        'title': song['name'],
        'artists': [{'name': a} for a in song['artists']],
    }

    def find_match(song):
        searched.append(dict(song))
        hit = behaviour['match'](song)
        return (hit or {}).get('videoId'), hit

    monkeypatch.setattr(providers, 'find_match', find_match)
    monkeypatch.setattr(providers, 'enrich_from_match', lambda song, match: dict(song))
    behaviour['searched'] = searched
    return asked, behaviour


def test_fix_replaces_a_locked_track_in_place(tmp_path, downloads):
    asked, _ = downloads
    music, data = tmp_path / 'music', tmp_path / 'data'
    folder = music / 'dancelo musiq'
    path = locked(folder, 'dancelo musiq - Nobody.dnf')
    (folder / vault.INDEX).write_text(json.dumps({
        'dancelo musiq - Nobody.dnf': {'title': 'Nobody', 'artist': 'dancelo musiq', 'video_id': 'EjreKstObTM'},
    }), encoding='utf-8')
    before = path.read_bytes()
    seen = []

    state, reason = repair.fix(
        music, 'dancelo musiq/dancelo musiq - Nobody.dnf', FakeDownloader(), data,
        progress=lambda pct, msg: seen.append(pct),
    )

    assert (state, reason) == ('fixed', '')
    assert asked[0]['youtube_id'] == 'EjreKstObTM'  # the same recording, not a search
    head, problem = vault.inspect(path)
    assert problem == '' and head['video_id'] == 'EjreKstObTM'
    assert b''.join(vault.open_range(path)) == MP3
    # The old one is kept, byte for byte, in the data folder, not the music.
    kept = data / repair.KEPT / 'dancelo musiq' / 'dancelo musiq - Nobody.dnf'
    assert kept.read_bytes() == before
    # Lyrics came along, named after the track.
    assert (folder / 'dancelo musiq - Nobody.lrc').is_file()
    # Nothing else was left in the music folder.
    assert sorted(p.name for p in folder.iterdir()) == [
        'dancelo musiq - Nobody.dnf', 'dancelo musiq - Nobody.lrc', vault.INDEX,
    ]
    # Both indexes know what is there now.
    assert vault.read_index(folder / vault.INDEX)['dancelo musiq - Nobody.dnf']['video_id'] == 'EjreKstObTM'
    top = vault.read_index(vault.index_path(music))
    assert top['dancelo musiq/dancelo musiq - Nobody.dnf']['title'] == 'Nobody'
    assert not (music / vault.INDEX).exists()  # nothing new is written in the open
    assert seen == [50.0]


def test_fix_repairs_a_damaged_track_from_its_own_header(tmp_path, downloads):
    asked, _ = downloads
    path = sealed(tmp_path, 'A - Short.dnf', title='Short', artist='A', video_id='SHORTSHORTS', album='LP')
    path.write_bytes(path.read_bytes()[:-400])
    assert repair.fix(tmp_path, 'A - Short.dnf', FakeDownloader(), tmp_path / 'd') == ('fixed', '')
    assert asked[0]['youtube_id'] == 'SHORTSHORTS'
    assert asked[0]['album_name'] == 'LP'
    assert vault.inspect(path)[1] == ''


def test_fix_leaves_everything_alone_when_the_download_fails(tmp_path, downloads):
    _, behaviour = downloads
    behaviour['fail'] = RuntimeError("Could not find a YouTube match for 'x'")
    path = locked(tmp_path, 'A - Gone.dnf')
    before = path.read_bytes()
    state, reason = repair.fix(tmp_path, 'A - Gone.dnf', FakeDownloader(), tmp_path / 'data')
    assert (state, reason) == ('failed', repair.NOT_FOUND)
    assert path.read_bytes() == before
    assert not (tmp_path / 'data' / repair.KEPT).exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['A - Gone.dnf']


def test_fix_refuses_a_new_copy_that_does_not_check_out(tmp_path, downloads):
    _, behaviour = downloads
    behaviour['payload'] = NOISE  # sealed fine, but not audio
    path = locked(tmp_path, 'A - Bad.dnf')
    before = path.read_bytes()
    assert repair.fix(tmp_path, 'A - Bad.dnf', FakeDownloader(), tmp_path / 'd') == ('failed', repair.FAILED)
    assert path.read_bytes() == before


def test_fix_does_nothing_to_a_track_that_is_fine(tmp_path, downloads):
    asked, _ = downloads
    path = sealed(tmp_path, 'A - Fine.dnf')
    before = path.read_bytes()
    assert repair.fix(tmp_path, 'A - Fine.dnf', FakeDownloader(), tmp_path / 'd') == ('fine', '')
    assert asked == [] and path.read_bytes() == before


def test_fix_can_be_forced_on_a_track_that_looks_fine(tmp_path, downloads):
    asked, _ = downloads
    sealed(tmp_path, 'A - Fine.dnf', video_id='FINEFINEFIN')
    assert repair.fix(tmp_path, 'A - Fine.dnf', FakeDownloader(), tmp_path / 'd', force=True) == ('fixed', '')
    assert asked[0]['youtube_id'] == 'FINEFINEFIN'


@pytest.mark.parametrize('rel', ['../outside.dnf', 'nothing-here.dnf', 'A - Song.mp3', ''])
def test_fix_only_touches_saved_tracks_inside_the_folder(tmp_path, downloads, rel):
    asked, _ = downloads
    music = tmp_path / 'music'
    music.mkdir()
    (tmp_path / 'outside.dnf').write_bytes(b'DNF1')
    (music / 'A - Song.mp3').write_bytes(MP3)
    assert repair.fix(music, rel, FakeDownloader(), tmp_path / 'd') == ('failed', repair.MISSING)
    assert asked == []


def test_fix_says_so_when_there_is_no_key(tmp_path, downloads):
    path = locked(tmp_path, 'A - B.dnf')
    vault._master = None
    assert repair.fix(tmp_path, path.name, FakeDownloader(), tmp_path / 'd') == ('failed', repair.UNAVAILABLE)


def test_fix_gives_up_on_a_file_held_open_and_keeps_the_original(tmp_path, downloads, monkeypatch):
    if os.name != 'nt':
        pytest.skip('only Windows refuses to replace an open file')
    monkeypatch.setattr(repair.time, 'sleep', lambda s: None)
    path = locked(tmp_path / 'm', 'A - Busy.dnf')
    before = path.read_bytes()
    with open(path, 'rb'):
        state, reason = repair.fix(tmp_path / 'm', 'A - Busy.dnf', FakeDownloader(), tmp_path / 'd')
    assert (state, reason) == ('failed', repair.IN_USE)
    assert path.read_bytes() == before
    assert not list((tmp_path / 'm').glob('*.incoming'))
    assert not list((tmp_path / 'd').rglob('*.dnf'))  # the kept copy went too


def test_place_works_across_drives(tmp_path, monkeypatch):
    real = os.replace
    calls = []

    def no_cross_drive(src, dst):
        calls.append(Path(dst).name)
        if len(calls) == 1:
            raise OSError(17, 'The system cannot move the file to a different disk drive')
        return real(src, dst)

    monkeypatch.setattr(repair.os, 'replace', no_cross_drive)
    src = tmp_path / 'a' / 'new.dnf'
    src.parent.mkdir()
    src.write_bytes(b'new')
    dest = tmp_path / 'b' / 'old.dnf'
    dest.parent.mkdir()
    dest.write_bytes(b'old')
    repair._place(src, dest)
    assert dest.read_bytes() == b'new'
    assert not (tmp_path / 'b' / 'old.dnf.incoming').exists()


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------
def wait_until_idle(jobs, limit=20.0):
    began = time.monotonic()
    while time.monotonic() - began < limit:
        if not jobs.status()['running'] and jobs._threads == 0:
            return jobs.status()
        time.sleep(0.02)
    raise AssertionError('repairs did not finish')


def test_a_round_of_repairs_reports_as_it_goes(tmp_path, downloads):
    music = tmp_path / 'music'
    for n in range(5):
        locked(music, f'A - Song {n}.dnf')
    sealed(music, 'A - Fine.dnf')
    sent, changed = [], []
    jobs = repair._Jobs()
    jobs.configure(lambda: (music, FakeDownloader(), tmp_path / 'data'), sent.append, lambda: changed.append(1))

    files = [f'A - Song {n}.dnf' for n in range(5)] + ['A - Fine.dnf', 'missing.dnf']
    first = jobs.add(files)
    assert first['total'] == 7 and first['running']
    done = wait_until_idle(jobs)

    assert done['fixed'] == 5 and done['fine'] == 1 and done['failed'] == 1
    assert done['items']['missing.dnf']['reason'] == repair.MISSING
    assert all(vault.inspect(music / f)[1] == '' for f in files[:6])
    final = max(sent, key=lambda s: s['seq'])
    assert final['done'] == 7 and not final['running']
    assert changed  # the window was told to reload the library
    assert jobs._threads == 0


def held(gate, folder):
    """A context that makes each repair wait for *gate*, so a test can act
    while repairs are known to be in flight. Only the workers wait: asking for
    a repair reads the context too, and must not block."""

    def context():
        if threading.current_thread().name == 'repair':
            assert gate.wait(5)
        return folder, FakeDownloader(), None

    return context


def test_asking_twice_for_the_same_track_repairs_it_once(tmp_path, downloads):
    asked, _ = downloads
    locked(tmp_path, 'A - One.dnf')
    jobs = repair._Jobs()
    gate = threading.Event()
    jobs.configure(held(gate, tmp_path), lambda s: None, lambda: None)
    jobs.add(['A - One.dnf'])
    jobs.add(['A - One.dnf', 'A - One.dnf'])
    gate.set()
    wait_until_idle(jobs)
    assert len(asked) == 1


def test_stop_drops_what_has_not_started(tmp_path, downloads):
    for n in range(6):
        locked(tmp_path, f'A - {n}.dnf')
    jobs = repair._Jobs()
    gate = threading.Event()
    jobs.configure(held(gate, tmp_path), lambda s: None, lambda: None)
    jobs.add([f'A - {n}.dnf' for n in range(6)])
    began = time.monotonic()
    while sum(i['state'] == 'working' for i in jobs.status()['items'].values()) < jobs.WORKERS:
        assert time.monotonic() - began < 5
        time.sleep(0.01)
    stopped = jobs.stop()
    gate.set()
    done = wait_until_idle(jobs)
    assert stopped['total'] == jobs.WORKERS  # only the ones already started
    assert done['fixed'] == jobs.WORKERS


def test_a_repair_asked_for_as_the_last_worker_leaves_is_not_lost(tmp_path, downloads):
    """The race between a worker finding the queue empty and leaving."""

    for n in range(40):
        locked(tmp_path, f'A - {n}.dnf')
    jobs = repair._Jobs()
    jobs.configure(lambda: (tmp_path, FakeDownloader(), None), lambda s: None, lambda: None)
    for n in range(40):
        jobs.add([f'A - {n}.dnf'])
        time.sleep(0.003 * (n % 4))
    wait_until_idle(jobs)
    assert all(vault.inspect(tmp_path / f'A - {n}.dnf')[1] == '' for n in range(40))


def test_a_new_round_forgets_the_last_one(tmp_path, downloads):
    locked(tmp_path, 'A - 1.dnf')
    locked(tmp_path, 'A - 2.dnf')
    jobs = repair._Jobs()
    jobs.configure(lambda: (tmp_path, FakeDownloader(), None), lambda s: None, lambda: None)
    jobs.add(['A - 1.dnf'])
    wait_until_idle(jobs)
    jobs.add(['A - 2.dnf'])
    done = wait_until_idle(jobs)
    assert list(done['items']) == ['A - 2.dnf']


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------
def test_prune_clears_old_kept_copies_and_stray_halves(tmp_path):
    data, music = tmp_path / 'data', tmp_path / 'music'
    old = data / repair.KEPT / 'X' / 'old.dnf'
    new = data / repair.KEPT / 'Y' / 'new.dnf'
    for p in (old, new):
        p.parent.mkdir(parents=True)
        p.write_bytes(b'x')
    past = time.time() - (repair.KEEP_DAYS + 1) * 86400
    os.utime(old, (past, past))
    music.mkdir()
    (music / 'A - B.dnf.incoming').write_bytes(b'half')
    (music / 'keep.incoming').write_bytes(b'not ours')

    repair.prune(data, music)

    assert not old.exists() and not old.parent.exists()
    assert new.exists()
    assert not (music / 'A - B.dnf.incoming').exists()
    assert (music / 'keep.incoming').exists()


def test_a_failure_while_offline_says_offline(tmp_path, downloads):
    _, behaviour = downloads
    behaviour['online'] = False
    behaviour['fail'] = RuntimeError("Could not find a YouTube match for 'x'")
    path = locked(tmp_path, 'A - Net.dnf')
    assert repair.fix(tmp_path, path.name, FakeDownloader(), None) == ('failed', repair.OFFLINE)


@pytest.mark.parametrize(
    'message,reason',
    [
        ('ERROR: [youtube] abc: Video unavailable', repair.NOT_FOUND),
        ('ERROR: [youtube] abc: Private video. Sign in', repair.NOT_FOUND),
        ('ffmpeg: could not open the output file', repair.FAILED),
        ('ffmpeg exited with code 1', repair.FAILED),
    ],
)
def test_reasons(downloads, message, reason):
    assert repair._reason(RuntimeError(message)) == reason


# ---------------------------------------------------------------------------
# Repairing by search: only ever the track itself
# ---------------------------------------------------------------------------
def test_a_search_that_finds_some_other_song_is_not_used(tmp_path, downloads):
    asked, behaviour = downloads
    behaviour['match'] = lambda song: {
        'videoId': 'WRONGWRONGW', 'title': 'A Different Song', 'artists': [{'name': 'Someone Else'}],
    }
    path = locked(tmp_path, 'Bensoul - Nairobi.dnf')
    before = path.read_bytes()
    assert repair.fix(tmp_path, path.name, FakeDownloader(), None) == ('failed', repair.NOT_FOUND)
    assert asked == []  # nothing was even downloaded
    assert path.read_bytes() == before


def test_a_search_that_finds_the_track_downloads_exactly_that(tmp_path, downloads):
    asked, behaviour = downloads
    path = locked(tmp_path, 'Bensoul - Nairobi.dnf')
    assert repair.fix(tmp_path, path.name, FakeDownloader(), None) == ('fixed', '')
    assert behaviour['searched'][0]['name'] == 'Nairobi'
    assert asked[0]['youtube_id'] == 'FOUNDFOUNDF'


def test_a_known_video_is_not_searched_for(tmp_path, downloads):
    asked, behaviour = downloads
    path = locked(tmp_path, 'A - B.dnf')
    (tmp_path / vault.INDEX).write_text(json.dumps({'A - B.dnf': {'video_id': 'KNOWNKNOWNK'}}), encoding='utf-8')
    assert repair.fix(tmp_path, path.name, FakeDownloader(), None) == ('fixed', '')
    assert behaviour['searched'] == []
    assert asked[0]['youtube_id'] == 'KNOWNKNOWNK'


def test_a_search_with_nothing_found_offline_says_offline(tmp_path, downloads):
    asked, behaviour = downloads
    behaviour['match'] = lambda song: None
    behaviour['online'] = False
    path = locked(tmp_path, 'A - B.dnf')
    assert repair.fix(tmp_path, path.name, FakeDownloader(), None) == ('failed', repair.OFFLINE)
    assert asked == []


def hit(title, *artists, vid='XXXXXXXXXXX'):
    return {'videoId': vid, 'title': title, 'artists': [{'name': a} for a in artists]}


@pytest.mark.parametrize(
    'name,artists,match,ok',
    [
        ('Nobody', ['dancelo musiq'], hit('Nobody', 'Dancelo Musiq'), True),
        ('Nobody', ['dancelo musiq'], hit('Nobody (Official Audio)', 'dancelo musiq'), True),
        ('Malengo Ya Mungu', ['Israel Mbonyi'], hit('Malengo Ya Mungu (Live)', 'Israel Mbonyi'), True),
        ('Nobody', ['dancelo musiq'], hit('Somebody Else', 'dancelo musiq'), False),
        ('Nobody', ['dancelo musiq'], hit('Nobody', 'Some Other Artist'), False),
        ('Nairobi', ['Bensoul'], hit('Bensoul - Nairobi', 'Music Channel KE'), True),
        ('VILE NAPENDA', ['Bensoul', 'Vic West'], hit('Vile Napenda', 'Vic West'), True),
        ('夜に駆ける', ['YOASOBI'], hit('夜に駆ける', 'YOASOBI'), True),
        ('夜に駆ける', ['YOASOBI'], hit('群青', 'YOASOBI'), False),
        ('Tune', [], hit('Tune', 'Anyone'), True),
        ('Nobody', ['dancelo musiq'], {'title': 'Nobody', 'artists': [{'name': 'dancelo musiq'}]}, False),
        ('Nobody', ['dancelo musiq'], None, False),
    ],
)
def test_confident(name, artists, match, ok):
    assert repair._confident({'name': name, 'artists': artists}, match) is ok


def test_notes_written_at_the_same_time_all_survive(tmp_path):
    """Downloads and repairs finishing together in one folder."""

    index = tmp_path / vault.INDEX
    start = threading.Barrier(8)

    def writer(n):
        start.wait()
        for i in range(25):
            vault.remember(index, f'{n}-{i}.dnf', {'title': f'{n}-{i}', 'artist': '', 'video_id': ''})

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(vault.read_index(index)) == 8 * 25
    assert not (tmp_path / (vault.INDEX + '.tmp')).exists()


# ---------------------------------------------------------------------------
# A track deleted while its repair is under way stays deleted
# ---------------------------------------------------------------------------
def test_a_track_deleted_during_its_download_is_not_put_back(tmp_path, downloads, monkeypatch):
    from dannify import downloader as dl

    _, behaviour = downloads
    path = locked(tmp_path, 'A - Gone Soon.dnf')
    real = dl.Downloader.download

    def delete_then_download(self, song, progress_cb=None, subdir=None):
        path.unlink()  # the person deletes it while this is downloading
        return real(self, song, progress_cb, subdir)

    monkeypatch.setattr(dl.Downloader, 'download', delete_then_download)
    assert repair.fix(tmp_path, path.name, FakeDownloader(), tmp_path / 'd') == ('failed', repair.MISSING)
    assert not path.exists()
    assert not list(tmp_path.glob('*.incoming'))


def test_forgetting_a_waiting_repair_drops_it(tmp_path, downloads):
    asked, _ = downloads
    for n in range(4):
        locked(tmp_path, f'A - {n}.dnf')
    jobs = repair._Jobs()
    gate = threading.Event()
    jobs.configure(held(gate, tmp_path), lambda s: None, lambda: None)
    jobs.add([f'A - {n}.dnf' for n in range(4)])
    began = time.monotonic()
    while sum(i['state'] == 'working' for i in jobs.status()['items'].values()) < jobs.WORKERS:
        assert time.monotonic() - began < 5
        time.sleep(0.01)
    waiting = next(f for f, i in jobs.status()['items'].items() if i['state'] == 'queued')
    (tmp_path / waiting).unlink()
    jobs.forget(waiting)
    assert waiting not in jobs.status()['items']
    gate.set()
    done = wait_until_idle(jobs)
    assert waiting not in done['items']
    assert not (tmp_path / waiting).exists()
    assert done['total'] == 3 and done['fixed'] == 3


def test_forgetting_a_repair_in_progress_leaves_no_trace(tmp_path, downloads):
    locked(tmp_path, 'A - Busy.dnf')
    jobs = repair._Jobs()
    gate = threading.Event()
    sent = []
    jobs.configure(held(gate, tmp_path), sent.append, lambda: None)
    jobs.add(['A - Busy.dnf'])
    began = time.monotonic()
    while jobs.status()['items'].get('A - Busy.dnf', {}).get('state') != 'working':
        assert time.monotonic() - began < 5
        time.sleep(0.01)
    (tmp_path / 'A - Busy.dnf').unlink()
    jobs.forget('A - Busy.dnf')
    gate.set()
    done = wait_until_idle(jobs)
    assert not (tmp_path / 'A - Busy.dnf').exists()
    assert 'A - Busy.dnf' not in done['items']  # no "could not repair" for it
    assert not any(
        s['items'].get('A - Busy.dnf', {}).get('state') == 'failed' for s in sent
    )


def test_forgetting_something_never_asked_for_is_harmless(tmp_path, downloads):
    jobs = repair._Jobs()
    sent = []
    jobs.configure(lambda: (tmp_path, FakeDownloader(), None), sent.append, lambda: None)
    jobs.forget('nothing/here.dnf')
    assert sent == [] and jobs.status()['total'] == 0


def test_a_download_that_cannot_be_saved_says_so(downloads):
    assert repair._reason(vault.StorageUnavailable('x')) == repair.UNAVAILABLE
    wrapped = RuntimeError('This song downloaded but could not be saved')
    wrapped.__cause__ = vault.StorageUnavailable('x')
    assert repair._reason(wrapped) == repair.UNAVAILABLE
