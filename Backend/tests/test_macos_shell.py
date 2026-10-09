"""The macOS shell's parts that are files, paths and processes (the updater,
the login item, how a copy starts again), checked on every platform, and a
few that need AppKit, checked on a Mac."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# The shell's core picks its data folder when first imported: a throwaway one.
_saved = {k: os.environ.get(k) for k in ('DANNIFY_DATA_DIR', 'DANNIFY_LOG_FILE')}
os.environ['DANNIFY_DATA_DIR'] = tempfile.mkdtemp(prefix='dannify-macos-')
from dannify.shell import core  # noqa: E402
from dannify.shell.macos import desktop, updater  # noqa: E402

for _key, _value in _saved.items():
    if _value is None:
        os.environ.pop(_key, None)
    else:
        os.environ[_key] = _value

POSIX = pytest.mark.skipif(os.name == 'nt', reason='runs a POSIX shell script')
MAC = pytest.mark.skipif(sys.platform != 'darwin', reason='needs macOS')


def _fake_app(where: Path, version: str, body: str) -> Path:
    """A bundle shaped like Dannify.app whose program is a shell script."""

    app = where / 'Dannify.app'
    (app / 'Contents' / 'MacOS').mkdir(parents=True)
    (app / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': updater.BUNDLE_ID,
        'CFBundleExecutable': 'Dannify',
        'CFBundleShortVersionString': version,
    }))
    program = app / 'Contents' / 'MacOS' / 'Dannify'
    program.write_text('#!/bin/sh\n' + body, encoding='utf-8')
    program.chmod(0o755)
    return app


# A program that does what the real one does once its server answers
# (updater.started): leave the marker, and say which version ran.
_STARTS = ('mkdir -p "$DANNIFY_DATA_DIR/updates"\n'
           'echo "{{}}" > "$DANNIFY_DATA_DIR/updates/.launched"\n'
           'echo {name} > "$DANNIFY_DATA_DIR/ran"\n')


def _gone_pid() -> int:
    """The id of a process that has already exited (and been reaped)."""

    done = subprocess.Popen([sys.executable, '-c', 'pass'])
    done.wait()
    return done.pid


def _swap(tmp_path: Path, new_body: str, wait: int = 10):
    # Spaces and a quote in the folder: every path in the script must be quoted.
    place = tmp_path / "Apps & 'Things'"
    place.mkdir()
    app = _fake_app(place, '4.7.0', _STARTS.format(name='old'))
    work = place / (updater.WORK_PREFIX + 'test')
    work.mkdir()
    new = _fake_app(work, '4.8.0', new_body)
    data = tmp_path / 'data'
    (data / 'updates').mkdir(parents=True)
    script = data / 'updates' / 'swap-app.sh'
    script.write_text(updater.helper_script(
        pid=_gone_pid(), app=app, new=new, data_dir=data, version='4.8.0', launch=True, wait=wait,
    ), encoding='utf-8')
    env = dict(os.environ, DANNIFY_DATA_DIR=str(data))
    done = subprocess.run(['/bin/sh', str(script)], env=env, capture_output=True, text=True, timeout=60)
    return place, app, work, data, done


def _ran(data: Path) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            text = (data / 'ran').read_text().strip()
            if text:
                return text
        except OSError:
            pass
        time.sleep(0.05)
    return ''


# ---------------------------------------------------------------------------
# The updater
# ---------------------------------------------------------------------------
def test_a_copy_that_cannot_replace_itself_says_why(tmp_path, monkeypatch):
    assert updater.refuse_reason(None)
    translocated = Path('/private/var/folders/xy/T/AppTranslocation/1234-5678/d/Dannify.app')
    assert 'translocated' in updater.refuse_reason(translocated)
    app = tmp_path / 'Applications' / 'Dannify.app'
    app.mkdir(parents=True)
    assert updater.refuse_reason(app) == ''
    monkeypatch.setattr(updater.os, 'access', lambda path, mode: Path(path) != app.parent)
    assert 'not writable' in updater.refuse_reason(app)


def test_install_refuses_before_touching_anything(tmp_path):
    archive = tmp_path / 'macos-Dannify-4.8.0-arm64.zip'
    archive.write_bytes(b'PK')
    assert updater.install(archive, None, pid=1, data_dir=tmp_path, launch=True) is False
    translocated = tmp_path / 'AppTranslocation' / 'Dannify.app'
    translocated.mkdir(parents=True)
    assert updater.install(archive, translocated, pid=1, data_dir=tmp_path, launch=True) is False
    assert sorted(p.name for p in translocated.parent.iterdir()) == ['Dannify.app']


def test_the_swap_script_says_what_it_works_on(tmp_path):
    app = _fake_app(tmp_path / 'My Apps', '4.7.0', 'exit 0\n')
    new = _fake_app(tmp_path / 'My Apps' / '.dannify-update-x', '4.8.0', 'exit 0\n')
    text = updater.helper_script(pid=4321, app=app, new=new, data_dir=tmp_path / 'data',
                                 version='4.8.0', launch=False)
    assert text.startswith('#!/bin/sh\n')
    assert 'PID=4321\n' in text
    assert f"APP='{app}'\n" in text
    assert f"BACKUP='{app}.old'\n" in text
    assert "NEW_EXE=Contents/MacOS/Dannify\n" in text
    assert 'LAUNCH=0\n' in text and 'VERSION=4.8.0\n' in text
    assert f"WAIT={updater.WAIT_FOR_START}\n" in text


@POSIX
def test_the_swap_script_puts_the_new_version_in_place_and_starts_it(tmp_path):
    place, app, work, data, done = _swap(tmp_path, _STARTS.format(name='new'))
    assert done.returncode == 0, done.stderr
    assert _ran(data) == 'new'
    info = plistlib.loads((app / 'Contents' / 'Info.plist').read_bytes())
    assert info['CFBundleShortVersionString'] == '4.8.0'
    assert not work.exists()
    # Kept until the new version is up and removes it itself (updater.started).
    assert (place / 'Dannify.app.old').is_dir()
    assert 'version 4.8.0 started' in (data / 'updates' / 'update.log').read_text()
    assert not (data / 'updates' / updater.SKIP).exists()


@POSIX
def test_the_swap_script_goes_back_when_the_new_version_cannot_start(tmp_path):
    place, app, work, data, done = _swap(tmp_path, 'exit 3\n', wait=5)
    assert done.returncode == 0, done.stderr
    assert _ran(data) == 'old'
    info = plistlib.loads((app / 'Contents' / 'Info.plist').read_bytes())
    assert info['CFBundleShortVersionString'] == '4.7.0'
    assert not (place / 'Dannify.app.old').exists()
    assert not work.exists()
    assert (data / 'updates' / updater.SKIP).read_text().strip() == '4.8.0'
    assert 'going back' in (data / 'updates' / 'update.log').read_text()


@POSIX
def test_the_swap_script_waits_for_the_app_to_quit(tmp_path):
    place = tmp_path / 'Applications'
    place.mkdir()
    app = _fake_app(place, '4.7.0', 'exit 0\n')
    new = _fake_app(place / '.dannify-update-x', '4.8.0', 'exit 0\n')
    data = tmp_path / 'data'
    (data / 'updates').mkdir(parents=True)
    running = subprocess.Popen(['sleep', '2'])
    script = data / 'updates' / 'swap-app.sh'
    script.write_text(updater.helper_script(pid=running.pid, app=app, new=new, data_dir=data,
                                            version='4.8.0', launch=False), encoding='utf-8')
    helper = subprocess.Popen(['/bin/sh', str(script)])
    time.sleep(0.8)
    # Still the old version while the app runs.
    assert plistlib.loads((app / 'Contents' / 'Info.plist').read_bytes())[
        'CFBundleShortVersionString'] == '4.7.0'
    running.wait()
    assert helper.wait(30) == 0
    assert plistlib.loads((app / 'Contents' / 'Info.plist').read_bytes())[
        'CFBundleShortVersionString'] == '4.8.0'


def test_a_started_copy_leaves_the_marker_and_drops_the_backup(tmp_path):
    place = tmp_path / 'Applications'
    app = place / 'Dannify.app'
    app.mkdir(parents=True)
    (place / 'Dannify.app.old' / 'Contents').mkdir(parents=True)
    stale = place / (updater.WORK_PREFIX + 'old')
    stale.mkdir()
    os.utime(stale, (time.time() - 7200, time.time() - 7200))
    fresh = place / (updater.WORK_PREFIX + 'now')
    fresh.mkdir()
    updater.started(app, tmp_path / 'data')
    assert (tmp_path / 'data' / 'updates' / updater.MARKER).is_file()
    assert not (place / 'Dannify.app.old').exists()
    assert not stale.exists()
    assert fresh.exists()  # an update being got ready right now


def test_a_rolled_back_version_is_not_offered_again(tmp_path, monkeypatch):
    from dannify import layout

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'Dannify.app' / 'Contents' / 'MacOS' / 'Dannify'))
    monkeypatch.setenv('DANNIFY_DATA_DIR', str(tmp_path / 'data'))
    assert layout.skipped_version() == ''
    (tmp_path / 'data' / 'updates').mkdir(parents=True)
    (tmp_path / 'data' / 'updates' / updater.SKIP).write_text('4.8.0\n')
    assert layout.skipped_version() == '4.8.0'


def test_only_a_real_app_in_a_writable_place_updates_itself(tmp_path, monkeypatch):
    from dannify import osenv, updates

    monkeypatch.setattr(osenv, 'IS_WINDOWS', False)
    monkeypatch.setattr(osenv, 'IS_MAC', True)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    program = tmp_path / 'Applications' / 'Dannify.app' / 'Contents' / 'MacOS' / 'Dannify'
    program.parent.mkdir(parents=True)
    program.write_bytes(b'')
    monkeypatch.setattr(sys, 'executable', str(program))
    assert updates.self_updatable() is True
    moved = tmp_path / 'AppTranslocation' / 'X' / 'd' / 'Dannify.app' / 'Contents' / 'MacOS' / 'Dannify'
    moved.parent.mkdir(parents=True)
    moved.write_bytes(b'')
    monkeypatch.setattr(sys, 'executable', str(moved))
    assert updates.self_updatable() is False
    monkeypatch.setattr(sys, 'frozen', False)
    monkeypatch.setattr(sys, 'executable', str(program))
    assert updates.self_updatable() is False


# ---------------------------------------------------------------------------
# Opening at login, and starting again
# ---------------------------------------------------------------------------
def test_the_login_item_opens_the_app_hidden(tmp_path):
    app = Path('/Applications/Dannify.app')
    data = plistlib.loads(desktop.launch_agent_plist(app))
    assert data['Label'] == desktop.BUNDLE_ID
    assert data['ProgramArguments'] == ['/usr/bin/open', str(app), '--args', '--minimized']
    assert data['RunAtLoad'] is True
    assert data['LimitLoadToSessionType'] == 'Aqua'
    assert 'KeepAlive' not in data  # quitting Dannify must not bring it back


def test_the_login_item_is_written_and_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop.Path, 'home', lambda: tmp_path)
    app = tmp_path / 'Applications' / 'Dannify.app'
    desktop.set_autostart(True, app)
    agent = tmp_path / 'Library' / 'LaunchAgents' / f'{desktop.BUNDLE_ID}.plist'
    assert plistlib.loads(agent.read_bytes())['ProgramArguments'][1] == str(app)
    desktop.set_autostart(False)
    assert not agent.exists()


def test_where_the_app_is_found():
    assert desktop.bundle_path('/Applications/Dannify.app/Contents/MacOS/Dannify').name == 'Dannify.app'
    assert desktop.bundle_path('/usr/local/bin/python3') is None
    assert desktop.bundle_path('/Applications/Dannify/Contents/MacOS/Dannify') is None


def test_a_mac_app_starts_again_through_launchservices(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', '/Applications/Dannify.app/Contents/MacOS/Dannify')
    monkeypatch.setattr(sys, 'argv', ['Dannify', '--minimized', '/Music/a.dnf'])
    env = {'DANNIFY_DATA_DIR': '/tmp/d d', 'DANNIFY_WAIT_PID': '77', 'HOME': '/Users/x', 'PATH': '/bin'}
    cmd = core.relaunch_command(env)
    app = str(Path('/Applications/Dannify.app/Contents/MacOS/Dannify').resolve().parents[2])
    assert cmd[:2] == ['/usr/bin/open', '-n']
    assert cmd[cmd.index(app):] == [app, '--args', '/Music/a.dnf']
    passed = [cmd[i + 1] for i, part in enumerate(cmd) if part == '--env']
    assert passed == ['DANNIFY_DATA_DIR=/tmp/d d', 'DANNIFY_WAIT_PID=77']


def test_elsewhere_a_frozen_copy_starts_its_own_program(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', '/opt/x/Dannify')
    monkeypatch.setattr(sys, 'argv', ['Dannify', '--minimized'])
    assert core.relaunch_command() == ['/opt/x/Dannify']


# ---------------------------------------------------------------------------
# On a Mac
# ---------------------------------------------------------------------------
@MAC
def test_the_menu_bar_menu_has_the_tray_rows():
    from dannify.shell.macos.tray import Tray

    seen = []
    tray = Tray(seen.append)
    tray.set_track('Inauma', 'Bien', playing=True, has_track=True)
    menu = tray.dock_menu()
    titles = [str(menu.itemAtIndex_(i).title()) for i in range(menu.numberOfItems())]
    assert titles[0] == 'Inauma \N{MIDDLE DOT} Bien'
    assert 'Pause' in titles and 'Next' in titles
    assert 'Quit Dannify' not in titles  # the Dock has its own
    pause = menu.itemAtIndex_(titles.index('Pause'))
    pause.target().menuAction_(pause)
    assert seen == ['toggle']


@MAC
def test_sign_in_cookies_are_the_ones_youtube_music_gets():
    from dannify.shell.macos import login

    assert login._for_site('.youtube.com')
    assert login._for_site('music.youtube.com')
    assert not login._for_site('.google.com')
    assert not login._for_site('youtube.com.evil.example')


@MAC
def test_global_shortcuts_register_and_let_go():
    hotkeys = desktop.Hotkeys(lambda command: None)
    taken = hotkeys.register()
    assert isinstance(taken, list) and len(taken) <= len(core.HOTKEYS)
    hotkeys.dispose()


@MAC
def test_the_menu_bar_item_comes_and_goes():
    from dannify.shell.macos.cocoa import AppKit
    from dannify.shell.macos.tray import Tray

    AppKit.NSApplication.sharedApplication()
    tray = Tray(lambda command: None)
    assert tray.install() and tray.showing
    tray.set_track('Inauma', 'Bien', playing=False, has_track=True)
    tray.dispose()
    assert not tray.showing


@MAC
def test_now_playing_takes_the_song_its_cover_and_the_keys():
    import base64

    import MediaPlayer

    from dannify.shell.macos.nowplaying import NowPlaying

    seen = []
    now = NowPlaying(seen.append)
    now.start()
    now.update(playing=True, has_track=True, title='Inauma', artist='Bien', album='Bien',
               duration=200.0, position=12.0, key='k1')
    center = MediaPlayer.MPNowPlayingInfoCenter.defaultCenter()
    info = center.nowPlayingInfo()
    assert info[MediaPlayer.MPMediaItemPropertyTitle] == 'Inauma'
    assert info[MediaPlayer.MPMediaItemPropertyPlaybackDuration] == 200.0
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf'
                           'DwAChwGA60e6kgAAAABJRU5ErkJggg==')
    now.set_art('k1', png)
    assert MediaPlayer.MPMediaItemPropertyArtwork in center.nowPlayingInfo()
    now.set_art('another song', png)  # late for a song that is gone: ignored
    assert now._handler('next')(None) == 0 and seen == ['next']
    now.stop()
    assert center.nowPlayingInfo() is None


@MAC
def test_the_dock_progress_draws():
    from dannify.shell.macos.cocoa import AppKit

    AppKit.NSApplication.sharedApplication()
    view = desktop._dock_view_class().alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 128, 128))
    view.value = 0.4
    image = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(128, 128))
    image.lockFocus()
    try:
        view.drawRect_(view.bounds())
    finally:
        image.unlockFocus()
    progress = desktop.DockProgress()
    progress.set(0.5, True)
    progress.set(0.0, False)


@MAC
def test_sign_in_takes_the_youtube_session_and_webkit_takes_our_blocks():
    import Foundation
    import WebKit

    from dannify.shell.macos import login
    from dannify.shell.macos.cocoa import os_major

    def cookie(domain, name, value):
        return Foundation.NSHTTPCookie.cookieWithProperties_({
            Foundation.NSHTTPCookieDomain: domain, Foundation.NSHTTPCookiePath: '/',
            Foundation.NSHTTPCookieName: name, Foundation.NSHTTPCookieValue: value,
        })

    window = login.LoginWindow('dark')
    window._collect([cookie('.google.com', 'SID', 'g')])
    assert window.cookies == {}  # not signed in to YouTube yet
    window._collect([cookie('.youtube.com', 'SAPISID', 'abc'), cookie('.google.com', 'SAPISID', 'other'),
                     cookie('music.youtube.com', 'PREF', 'x')])
    assert window.cookies == {'SAPISID': 'abc', 'PREF': 'x'}

    # The completion blocks the sign-in and sign-out code hands WebKit.
    store = WebKit.WKWebsiteDataStore.nonPersistentDataStore()
    store.httpCookieStore().getAllCookies_(window._collect)
    store.removeDataOfTypes_modifiedSince_completionHandler_(
        WebKit.WKWebsiteDataStore.allWebsiteDataTypes(), Foundation.NSDate.distantPast(), lambda: None)
    if os_major() >= 14:
        WebKit.WKWebsiteDataStore.removeDataStoreForIdentifier_completionHandler_(
            Foundation.NSUUID.UUID(), lambda _error: None)
    delegate = type(login._delegate())
    assert delegate.webView_didFinishNavigation_.signature.startswith(b'v')
    assert delegate.webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_.signature.startswith(b'@')


@MAC
def test_the_app_delegate_answers_appkit_in_its_own_types():
    from dannify.shell.macos import app as mac_app
    from dannify.shell.macos.tray import Tray

    class Api:
        _quitting = False
        _tray = Tray(lambda command: None)
        shown = 0

        def win_show(self):
            self.shown += 1

    api = Api()
    opened = []
    delegate = mac_app._app_delegate(api, None, opened.append)
    kind = type(delegate)
    assert kind.applicationShouldTerminate_.signature[:1] in (b'Q', b'L', b'I')  # NSApplicationTerminateReply
    assert kind.applicationShouldHandleReopen_hasVisibleWindows_.signature[:1] in (b'Z', b'c')  # BOOL
    assert kind.applicationDockMenu_.signature[:1] == b'@'
    assert kind.application_openFiles_.signature[:1] == b'v'
    assert delegate.applicationShouldHandleReopen_hasVisibleWindows_(None, False) and api.shown == 1
    assert delegate.applicationDockMenu_(None).numberOfItems() > 0
