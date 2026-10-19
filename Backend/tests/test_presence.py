"""Discord presence: what the profile shows, when it is told, and the pipe
or socket it is told over. Discord itself is played by fakes: one in memory
for what is said and when, and real pipes and sockets for how."""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import tempfile
import threading
import uuid

import pytest

from dannify import presence
from dannify.presence import CLOSE, FRAME, HANDSHAKE, LOGO, MIN_GAP, PAUSE_GRACE, RETRY, Presence

COVER = 'https://lh3.googleusercontent.com/abcDEF123=w120-h120-l90-rj'
SONG = {
    'title': 'Suzanna', 'artist': 'Sauti Sol', 'album': 'Midnight Train', 'cover': COVER,
    'video_id': 'KNEd-OkExKY', 'duration': 230, 'position': 30, 'playing': True,
}


def song(now, **changes):
    return presence.clean({**SONG, **changes}, now)


# ---------------------------------------------------------------------------
# A Discord in memory
# ---------------------------------------------------------------------------


class FakeDiscord:
    """Answers the way Discord's desktop app does, and remembers what it got."""

    def __init__(self) -> None:
        self.running = True
        self.client_ok = True
        self.plain_only = False  # an older Discord: no activity type, no buttons
        self.frames: list[tuple[int, dict]] = []
        self.connections: list[FakeRaw] = []

    def open(self):
        if not self.running:
            return None
        raw = FakeRaw(self)
        self.connections.append(raw)
        return presence.Channel(raw)

    def activities(self):
        """What was asked of SET_ACTIVITY, in order: None for clearing."""

        return [
            p['args'].get('activity') for op, p in self.frames
            if op == FRAME and p.get('cmd') == 'SET_ACTIVITY'
        ]


class FakeRaw:
    def __init__(self, discord: FakeDiscord) -> None:
        self.discord = discord
        self.out = bytearray()
        self.closed = False

    def _reply(self, op, payload):
        self.out += presence.encode(op, payload)

    def send(self, data: bytes) -> None:
        if self.closed or not self.discord.running:
            raise BrokenPipeError('Discord is gone')
        op, size = struct.unpack('<II', data[:8])
        payload = json.loads(data[8:8 + size])
        self.discord.frames.append((op, payload))
        if op == HANDSHAKE:
            if payload.get('client_id') != presence.CLIENT_ID or not self.discord.client_ok:
                self._reply(CLOSE, {'code': 4000, 'message': 'Invalid Client ID'})
            else:
                self._reply(FRAME, {'cmd': 'DISPATCH', 'evt': 'READY', 'data': {'v': 1}})
            return
        activity = payload['args'].get('activity') or {}
        if self.discord.plain_only and ('type' in activity or 'buttons' in activity):
            self._reply(FRAME, {'cmd': 'SET_ACTIVITY', 'evt': 'ERROR', 'nonce': payload['nonce'],
                                'data': {'code': 4000, 'message': 'child "activity" fails'}})
            return
        # Something else Discord says now and then, before the answer.
        self._reply(FRAME, {'cmd': 'DISPATCH', 'evt': 'ACTIVITY_JOIN', 'data': {}})
        self._reply(FRAME, {'cmd': 'SET_ACTIVITY', 'evt': None, 'nonce': payload['nonce'], 'data': activity})

    def recv(self, size: int) -> bytes:
        if not self.out and (self.closed or not self.discord.running):
            return b''
        part = bytes(self.out[:size])
        del self.out[:size]
        return part

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def discord():
    return FakeDiscord()


@pytest.fixture
def p(discord):
    looked_up = []

    def find_cover(video_id):
        looked_up.append(video_id)
        return 'https://lh3.googleusercontent.com/found=w60-h60'

    out = Presence(opener=discord.open, cover_finder=find_cover)
    out.looked_up = looked_up
    return out


# ---------------------------------------------------------------------------
# What the profile shows
# ---------------------------------------------------------------------------


def test_a_song_playing_shows_as_listening_with_its_progress():
    activity = presence.activity_for(song(1000.0))
    assert activity['type'] == presence.LISTENING
    assert activity['details'] == 'Suzanna'
    assert activity['state'] == 'Sauti Sol'
    assert activity['assets'] == {
        'large_image': 'https://lh3.googleusercontent.com/abcDEF123=w544-h544-l90-rj',
        'large_text': 'Midnight Train',
        'small_image': LOGO,
        'small_text': 'Dannify',
    }
    # Thirty seconds in when the window said so: started at 970, ends 230 later.
    assert activity['timestamps'] == {'start': 970_000, 'end': 1_200_000}
    assert activity['buttons'] == [
        {'label': 'Play on YouTube Music', 'url': 'https://music.youtube.com/watch?v=KNEd-OkExKY'}
    ]


def test_texts_are_kept_to_what_discord_takes():
    long = 'x' * 300
    activity = presence.activity_for(song(0.0, title=long, artist='A', album='', button='Écouter sur YouTube Music et ailleurs'))
    assert len(activity['details']) == presence.TEXT_MOST
    assert activity['details'].endswith('…')
    assert len(activity['state']) == 2  # one character is too few for Discord
    assert activity['assets']['large_text'] == activity['details']
    assert len(activity['buttons'][0]['label']) <= presence.LABEL_MOST


def test_artwork_discord_cannot_reach_shows_the_logo():
    for cover in ('/cover?file=a.dnf', 'http://example.com/a.jpg', 'file:///c:/a.jpg', ''):
        activity = presence.activity_for(song(0.0, cover=cover))
        assert activity['assets'] == {'large_image': LOGO, 'large_text': 'Midnight Train'}


def test_nothing_shows_without_a_song_or_while_paused():
    assert presence.activity_for(None) is None
    assert presence.activity_for(song(0.0, playing=False)) is None
    assert presence.clean({'title': '   '}) is None
    assert presence.clean('nonsense') is None


def test_odd_numbers_from_the_window_are_ignored():
    cleaned = presence.clean({'title': 'T', 'duration': 'abc', 'position': -5, 'playing': 1}, 5.0)
    assert cleaned['duration'] == 0 and cleaned['position'] == 0
    activity = presence.activity_for(cleaned)
    assert activity['timestamps'] == {'start': 5000}
    assert 'buttons' not in activity  # no video id


def test_a_song_without_a_youtube_id_gets_no_button():
    activity = presence.activity_for(song(0.0, video_id='not-an-id'))
    assert 'buttons' not in activity


def test_where_discord_is_looked_for(monkeypatch):
    if sys.platform == 'win32':
        assert presence.candidates()[0] == r'\\.\pipe\discord-ipc-0'
        assert len(presence.candidates()) == 10
        return
    monkeypatch.setenv('XDG_RUNTIME_DIR', '/run/user/1000')
    found = presence.candidates()
    assert found[0] == '/run/user/1000/discord-ipc-0'
    assert '/run/user/1000/app/com.discordapp.Discord/discord-ipc-0' in found
    assert '/run/user/1000/snap.discord/discord-ipc-0' in found
    assert '/tmp/discord-ipc-9' in found


# ---------------------------------------------------------------------------
# When Discord is told
# ---------------------------------------------------------------------------


def test_nothing_happens_while_it_is_off(p, discord):
    p.hear(song(0.0), 0.0)
    assert p.step(0.0) is None
    assert discord.connections == []


def test_on_it_connects_as_dannify_and_shows_the_song(p, discord):
    p.enabled = True
    assert p.step(0.0) is None  # nothing playing: connected, nothing shown
    assert p.status() == {'enabled': True, 'connected': True}
    assert discord.frames[0] == (HANDSHAKE, {'v': 1, 'client_id': presence.CLIENT_ID})
    assert discord.activities() == []

    p.hear(song(10.0), 10.0)
    p.step(10.0)
    assert discord.activities()[-1]['details'] == 'Suzanna'
    sent = [pl for op, pl in discord.frames if op == FRAME][-1]
    assert sent['args']['pid'] == os.getpid()
    # Asked again with nothing new: Discord is not told again.
    p.step(11.0)
    assert len(discord.activities()) == 1


def test_discord_not_running_is_looked_for_again_later(p, discord):
    discord.running = False
    p.enabled = True
    assert p.step(0.0) == RETRY
    assert p.status()['connected'] is False
    assert p.step(5.0) == pytest.approx(RETRY - 5)  # not yet
    discord.running = True
    p.hear(song(15.0), 15.0)
    p.step(15.0)
    assert p.status()['connected'] is True
    assert discord.activities()[-1]['details'] == 'Suzanna'


def test_quick_skips_are_gathered_into_one_update(p, discord):
    p.enabled = True
    p.hear(song(0.0, title='One'), 0.0)
    p.step(0.0)
    p.hear(song(1.0, title='Two'), 1.0)
    assert p.step(1.0) == pytest.approx(MIN_GAP - 1)
    p.hear(song(2.0, title='Three'), 2.0)
    assert p.step(2.0) == pytest.approx(MIN_GAP - 2)
    p.step(4.0)
    assert [a['details'] for a in discord.activities()] == ['One', 'Three']


def test_a_pause_takes_the_song_off_after_a_moment(p, discord):
    p.enabled = True
    p.hear(song(0.0), 0.0)
    p.step(0.0)
    p.hear(song(5.0, playing=False), 5.0)
    assert p.step(5.0) == pytest.approx(PAUSE_GRACE)
    assert len(discord.activities()) == 1  # a short pause changes nothing
    # Playing again within the moment: the progress bar is put right.
    p.hear(song(8.0, position=33), 8.0)
    p.step(9.0)
    assert discord.activities()[-1]['timestamps']['start'] == (8 - 33) * 1000
    p.hear(song(10.0, playing=False), 10.0)
    p.step(10.0)
    p.step(10.0 + PAUSE_GRACE)
    assert discord.activities()[-1] is None  # taken off


def test_turning_it_off_closes_the_connection(p, discord):
    p.enabled = True
    p.hear(song(0.0), 0.0)
    p.step(0.0)
    p.enabled = False
    assert p.step(1.0) is None
    assert discord.connections[-1].closed  # Discord clears the profile itself
    assert p.status() == {'enabled': False, 'connected': False}


def test_an_older_discord_gets_the_activity_without_the_extras(p, discord):
    discord.plain_only = True
    p.enabled = True
    p.hear(song(0.0), 0.0)
    p.step(0.0)
    full, plain = discord.activities()
    assert 'type' in full and 'buttons' in full
    assert 'type' not in plain and 'buttons' not in plain
    assert plain['details'] == 'Suzanna'
    # From then on it is sent plain straight away.
    p.hear(song(10.0, title='Next'), 10.0)
    p.step(10.0)
    assert 'type' not in discord.activities()[-1]
    assert len(discord.activities()) == 3


def test_discord_closing_mid_song_is_reconnected(p, discord):
    p.enabled = True
    p.hear(song(0.0), 0.0)
    p.step(0.0)
    discord.connections[-1].closed = True  # Discord restarted
    p.hear(song(10.0, title='After'), 10.0)
    assert p.step(10.0) == 1.0
    assert p.status()['connected'] is False
    p.step(11.0)
    assert len(discord.connections) == 2
    assert discord.activities()[-1]['details'] == 'After'


def test_an_application_discord_does_not_know_is_not_asked_again_soon(p, discord):
    discord.client_ok = False
    p.enabled = True
    wait = p.step(0.0)
    assert wait >= RETRY * 10
    assert 'Invalid Client ID' in p.refused
    assert discord.connections[-1].closed


def test_a_saved_song_gets_its_artwork_looked_up_once(p, discord):
    p.enabled = True
    p.hear(song(0.0, cover='/cover?file=Suzanna.dnf'), 0.0)
    assert p.step(0.0) == 0.0  # shown with the logo, then the artwork looked up
    assert discord.activities()[-1]['assets']['large_image'] == LOGO
    assert p.looked_up == ['KNEd-OkExKY']
    p.step(MIN_GAP)
    assert discord.activities()[-1]['assets']['large_image'] == (
        'https://lh3.googleusercontent.com/found=w544-h544-l90-rj'
    )
    p.hear(song(20.0, cover='/cover?file=Suzanna.dnf', position=0), 20.0)
    p.step(20.0)
    assert p.looked_up == ['KNEd-OkExKY']


# ---------------------------------------------------------------------------
# The pipe (Windows) and the socket (Linux, macOS)
# ---------------------------------------------------------------------------


def _serve(read_exactly, write, close):
    """A Discord on the other end: READY, then an answer to each command."""

    def frame():
        op, size = struct.unpack('<II', read_exactly(8))
        return op, json.loads(read_exactly(size))

    got = []
    try:
        op, hello = frame()
        got.append((op, hello))
        write(presence.encode(FRAME, {'cmd': 'DISPATCH', 'evt': 'READY', 'data': {'v': 1}}))
        op, command = frame()
        got.append((op, command))
        write(presence.encode(FRAME, {'cmd': 'SET_ACTIVITY', 'nonce': command['nonce'], 'data': {}}))
    finally:
        close()
    return got


@pytest.mark.skipif(sys.platform != 'win32', reason='named pipes are Windows')
def test_talking_over_a_real_named_pipe(monkeypatch):
    import _winapi

    name = rf'\\.\pipe\dannify-test-{uuid.uuid4().hex}'
    handle = _winapi.CreateNamedPipe(
        name, _winapi.PIPE_ACCESS_DUPLEX, _winapi.PIPE_WAIT, 1, 65536, 65536, 0, _winapi.NULL,
    )
    result = {}

    def read_exactly(size):
        got = b''
        while len(got) < size:
            data, _ = _winapi.ReadFile(handle, size - len(got))
            if not data:
                raise EOFError
            got += data
        return got

    def server():
        try:
            _winapi.ConnectNamedPipe(handle, False)
        except OSError as exc:
            if getattr(exc, 'winerror', None) != 535:  # already connected
                raise
        result['got'] = _serve(read_exactly, lambda d: _winapi.WriteFile(handle, d), lambda: _winapi.CloseHandle(handle))

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    monkeypatch.setattr(presence, 'candidates', lambda: [rf'\\.\pipe\nothing-{uuid.uuid4().hex}', name])
    channel = presence.open_channel()
    assert channel is not None
    presence.handshake(channel)
    assert presence.set_activity(channel, presence.activity_for(song(0.0))) == ''
    thread.join(10)
    hello, command = result['got']
    assert hello == (HANDSHAKE, {'v': 1, 'client_id': presence.CLIENT_ID})
    assert command[1]['args']['activity']['details'] == 'Suzanna'
    # The far end has gone: reading says so instead of hanging.
    with pytest.raises(presence.Closed):
        channel.recv()
    channel.close()


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix sockets are Linux and macOS')
def test_talking_over_a_real_unix_socket(monkeypatch):
    # A short folder: a socket's path is limited to about a hundred characters.
    folder = tempfile.mkdtemp(prefix='dn', dir='/tmp')
    path = os.path.join(folder, 'discord-ipc-0')
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(path)
    server_sock.listen(1)
    result = {}

    def server():
        conn, _ = server_sock.accept()

        def read_exactly(size):
            got = b''
            while len(got) < size:
                part = conn.recv(size - len(got))
                if not part:
                    raise EOFError
                got += part
            return got

        result['got'] = _serve(read_exactly, conn.sendall, conn.close)

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    monkeypatch.setattr(presence, 'candidates', lambda: [os.path.join(folder, 'missing'), path])
    try:
        channel = presence.open_channel()
        assert channel is not None
        presence.handshake(channel)
        assert presence.set_activity(channel, presence.activity_for(song(0.0))) == ''
        thread.join(10)
        hello, command = result['got']
        assert hello == (HANDSHAKE, {'v': 1, 'client_id': presence.CLIENT_ID})
        assert command[1]['args']['activity']['details'] == 'Suzanna'
        with pytest.raises(presence.Closed):
            channel.recv()
        channel.close()
    finally:
        server_sock.close()
        os.unlink(path)
        os.rmdir(folder)


def test_no_discord_running_means_no_channel(monkeypatch):
    monkeypatch.setattr(presence, 'candidates', lambda: [
        rf'\\.\pipe\nothing-{uuid.uuid4().hex}' if sys.platform == 'win32' else f'/tmp/nothing-{uuid.uuid4().hex}'
    ])
    assert presence.open_channel() is None


# ---------------------------------------------------------------------------
# The switch in Settings, and what the window sends
# ---------------------------------------------------------------------------


@pytest.fixture
def module(tmp_path, monkeypatch, discord):
    """The module's own state, with the fake Discord and no thread."""

    fresh = Presence(opener=discord.open, cover_finder=lambda vid: '')
    monkeypatch.setattr(presence, '_presence', fresh)
    monkeypatch.setattr(presence, '_ensure_thread', lambda: None)
    presence.init(tmp_path)
    return fresh, tmp_path


def test_the_switch_is_off_until_turned_on_and_remembered(module):
    fresh, folder = module
    assert presence.status()['enabled'] is False
    assert presence.set_enabled(True)['enabled'] is True
    assert json.loads((folder / 'discord.json').read_text()) == {'enabled': True}
    fresh.enabled = False
    presence.init(folder)  # the next run
    assert fresh.enabled is True
    presence.set_enabled(False)
    presence.init(folder)
    assert fresh.enabled is False


def test_what_is_playing_is_kept_while_off_and_shown_when_turned_on(module, discord):
    from dannify.routes import presence as routes

    fresh, _ = module
    assert routes.discord_now_playing_endpoint(dict(SONG)) == {'ok': True}
    assert fresh.song['title'] == 'Suzanna'
    fresh.step(1000.0)
    assert discord.connections == []
    presence.set_enabled(True)
    fresh.step(1000.0)
    assert discord.activities()[-1]['details'] == 'Suzanna'
    routes.discord_now_playing_endpoint({'playing': False})
    fresh.step(1000.0 + MIN_GAP)
    assert discord.activities()[-1] is None
