"""One copy at a time: the single-instance lock, quitting on request, and
files handed over by a second launch.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any
from loguru import logger

from .base import (
    _DATA_DIR,
    _INSTANCE_FILE,
    logger_print,
)
from .win32 import (
    GW_OWNER,
    SW_RESTORE,
    SW_SHOW,
    _EnumWindowsProc,
    _WIN,
    _proto,
    kernel32,
    user32,
)


# ---------------------------------------------------------------------------
# Single instance (Windows named mutex)
# ---------------------------------------------------------------------------
def _wait_for_parent_exit() -> bool:
    """A relaunch waits for the old process before claiming the mutex.

    The wait used to be twenty seconds with the result thrown away, so a
    timeout looked exactly like the parent having exited and the helper went
    on to replace files underneath a process that was still running. Renaming
    a running executable succeeds on Windows, which leaves that process
    executing against an archive that is no longer the one it was started
    from: the "Error -3 while decompressing data" failure, in the copy the
    user is still looking at.

    Waiting forever is not the answer either, because a parent that never
    exits would hang the update for good. Five minutes, and the result is
    returned so the caller can decline to touch anything.
    """

    pid = os.environ.pop('DANNIFY_WAIT_PID', '')
    if not (_WIN and pid.isdigit()):
        return True
    handle = kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
    if not handle:
        return True  # already gone
    try:
        waited = 0
        while waited < 300_000:
            if kernel32.WaitForSingleObject(handle, 5000) != 0x102:  # WAIT_TIMEOUT
                return True
            waited += 5000
            if waited % 30_000 == 0:
                logger_print(f'still waiting for the old copy to exit ({waited // 1000}s)')
    finally:
        kernel32.CloseHandle(handle)
    logger_print('the old copy is still running; not touching any files')
    return False


# A name the installer can signal to ask us to shut down. Without this the
# only way to close a running copy is a window message, and close-to-tray
# swallows those: the app hides instead of exiting and the installer sits
# there waiting for a process that is never going to leave.
_QUIT_EVENT_NAME = r'Local\DannifyQuitRequest'


def _quit_event_name() -> str:
    return _QUIT_EVENT_NAME + os.environ.get('DANNIFY_INSTANCE', '')


def _watch_for_quit_request(on_quit) -> None:
    """Quit when something outside asks us to, properly rather than to tray."""

    if not _WIN:
        return

    def run() -> None:
        try:
            _proto(kernel32.CreateEventW, wintypes.HANDLE,
                   ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
            _proto(kernel32.WaitForSingleObject, wintypes.DWORD,
                   wintypes.HANDLE, wintypes.DWORD)
            handle = kernel32.CreateEventW(None, True, False, _quit_event_name())
            if not handle:
                return
            # INFINITE; the thread is a daemon so it dies with the process.
            if kernel32.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
                logger.info('Shutdown requested from outside; closing')
                on_quit()
        except Exception:
            logger.opt(exception=True).debug('quit watcher failed')

    threading.Thread(target=run, name='dannify-quit-watch', daemon=True).start()


def _quit_until_gone(api) -> None:  # noqa: ANN001
    """Close for good, however early the request came.

    A request that arrived in the first moments of a start was lost: there was
    no window yet to send the close to, so nothing happened. The app said it
    was closing and went on running, and whatever had asked (the installer,
    an update) sat waiting for a process that was never going to leave. So it
    is asked again until the window is really going, and if it still has not
    gone after a while, the window is closed directly.
    """

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        api._quit()
        settle = time.monotonic() + 1.0
        while time.monotonic() < settle:
            if api._closing:
                return
            time.sleep(0.05)
    logger.warning('The window did not close when asked to; closing it directly')
    try:
        if api._window is not None:
            api._window.destroy()
    except Exception:
        logger.opt(exception=True).debug('could not close the window')


def _signal_quit_request() -> bool:
    """Ask a running copy to exit. True if one was there to ask."""

    if not _WIN:
        return False
    try:
        _proto(kernel32.OpenEventW, wintypes.HANDLE,
               wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        _proto(kernel32.SetEvent, wintypes.BOOL, wintypes.HANDLE)
        EVENT_MODIFY_STATE = 0x0002
        handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, _quit_event_name())
        if not handle:
            return False
        kernel32.SetEvent(handle)
        kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


def _acquire_single_instance() -> bool:
    """Return True if we are the first instance; focus the other otherwise.

    ``DANNIFY_INSTANCE`` suffixes the mutex so developers can run a second
    copy side by side (it is never set in shipped builds).
    """
    if not _WIN:
        return True
    _wait_for_parent_exit()
    suffix = os.environ.get('DANNIFY_INSTANCE', '')
    name = f'Local\\DannifyAppMutex{suffix}'

    def claim() -> bool:
        handle = kernel32.CreateMutexW(None, False, name)
        taken = ctypes.get_last_error() == 183 or kernel32.GetLastError() == 183
        if taken and handle:
            # Our handle would keep the other copy's mutex alive after it
            # exits; hold one only while we own it.
            kernel32.CloseHandle(handle)
        return not taken

    if claim():
        return True
    if _running_instance_window():
        _focus_existing_window()
        return False
    # Another copy holds the mutex but has no window any more: it is on its
    # way out (closed a moment ago). Opening Dannify again straight after
    # closing it used to do nothing at all; wait for it to finish instead.
    for _ in range(40):
        time.sleep(0.1)
        if claim():
            return True
    _focus_existing_window()
    return False


def _running_instance_window() -> int:
    """The main window of the instance already running, or 0.

    Prefers the handle it wrote down; falls back to walking its windows.
    Deliberately does not filter on visibility: the whole point is to find
    the window when it has been hidden into the tray.
    """

    pid = 0
    hwnd = 0
    try:
        note = json.loads(_INSTANCE_FILE.read_text(encoding='utf-8'))
        pid = int(note.get('pid', 0) or 0)
        hwnd = int(note.get('hwnd', 0) or 0)
    except Exception:
        pass

    if hwnd and user32.IsWindow(wintypes.HWND(hwnd)):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(owner))
        if not pid or owner.value == pid:
            return hwnd

    if not pid:
        return 0
    found: list[int] = []

    def visit(candidate, _):  # noqa: ANN001
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(candidate, ctypes.byref(owner))
        if owner.value != pid or user32.GetWindow(candidate, GW_OWNER):
            return True
        name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(candidate, name, 128)
        # The app's own frame, not an IME or message-only helper window.
        if name.value.startswith('WindowsForms10.Window.8'):
            found.append(candidate)
            return False
        return True

    try:
        user32.EnumWindows(_EnumWindowsProc(visit), 0)
    except Exception:
        return 0
    return found[0] if found else 0


def _focus_existing_window() -> None:
    """Bring the running instance forward, from wherever it is.

    Launching the app again when it is already running should behave like
    every other Windows application: the window you already have comes
    back. It used to do nothing at all when the window had been hidden into
    the tray, which left people with no way to find the app they could hear
    playing.
    """

    hwnd = _running_instance_window()
    if not hwnd:
        return
    handle = wintypes.HWND(hwnd)
    try:
        # SW_SHOW un-hides; SW_RESTORE un-minimises. A window can need both.
        if not user32.IsWindowVisible(handle):
            user32.ShowWindow(handle, SW_SHOW)
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, SW_RESTORE)
        # Windows refuses a foreground steal unless the calling thread is
        # attached to the one that owns the window. We were just launched by
        # the user, so we are entitled to it; the attach is what makes the
        # entitlement transfer.
        target_thread = user32.GetWindowThreadProcessId(handle, None)
        our_thread = kernel32.GetCurrentThreadId()
        attached = False
        if target_thread and target_thread != our_thread:
            attached = bool(user32.AttachThreadInput(our_thread, target_thread, True))
        try:
            user32.BringWindowToTop(handle)
            user32.SetForegroundWindow(handle)
            user32.SetActiveWindow(handle)
        finally:
            if attached:
                user32.AttachThreadInput(our_thread, target_thread, False)
    except Exception:
        pass


_OPEN_FILE = _DATA_DIR / 'open.json'


# When this copy started. A file handed over by a second copy is always
# written after that (the second copy only hands over once it finds this one
# running), so anything older was left by an earlier run.
_STARTED_NS = time.time_ns()


def _file_from_note(note: Any, started_ns: int) -> str:
    """The file a hand-over note asks this copy to play, or ''.

    The note stays on disk after it is read. Each new run read it afresh and
    played it: a song double-clicked days ago began by itself the next time
    Dannify was opened.
    """

    if not isinstance(note, dict):
        return ''
    try:
        stamp = int(note.get('n') or 0)
    except (TypeError, ValueError):
        return ''
    if stamp < started_ns:
        return ''
    return str(note.get('path') or '')


def _file_argument() -> str:
    """The file Explorer handed us, if it did.

    Double-clicking a .dnf runs the app with the path as its only argument,
    so anything that is not one of our own switches and is a file on disk is
    that. Checked against the disk rather than by extension so a rename does
    not make the association stop working.
    """

    for arg in sys.argv[1:]:
        if arg.startswith('-'):
            continue
        try:
            if Path(arg).is_file():
                return str(Path(arg).resolve())
        except OSError:
            continue
    return ''


def _hand_file_to_running_instance(path: str) -> None:
    """Pass the file to the copy already running, then bring it forward."""

    try:
        _OPEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _OPEN_FILE.write_text(
            json.dumps({'path': path, 'n': time.time_ns()}), encoding='utf-8',
        )
    except OSError:
        logger_print('could not pass the file to the running copy')


def _watch_for_opened_files() -> None:
    """Play files handed over by a second copy started from Explorer.

    Windows starts a whole new process for every double-click. That copy
    finds the mutex taken, drops the path here and brings the existing window
    forward, and this is the end that notices. One stat call every half second
    costs nothing and works whether or not the window handle can be found.
    """

    import main as backend

    last = ''
    while True:
        time.sleep(0.5)
        try:
            if not _OPEN_FILE.is_file():
                continue
            note = json.loads(_OPEN_FILE.read_text(encoding='utf-8'))
            stamp = str(note.get('n') or '')
            if not stamp or stamp == last:
                continue
            last = stamp
            wanted = _file_from_note(note, _STARTED_NS)
        except Exception:
            continue
        if wanted:
            try:
                backend.open_external(wanted)
            except Exception:
                logger_print('could not open', wanted)
