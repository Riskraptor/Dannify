"""The app's identity on the taskbar and in the media flyout."""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from loguru import logger

from .base import (
    APP_USER_MODEL_ID,
    state,
)
from .win32 import (
    _WIN,
    kernel32,
    ole32,
    shell32,
    user32,
)
from .taskbar import _GUID


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _claim_app_identity() -> None:
    """Tell Windows who we are, before any window or audio exists.

    Has to happen first: the shell caches the identity on the first window a
    process shows, so setting it later changes nothing.
    """

    if not _WIN:
        return
    try:
        fn = shell32.SetCurrentProcessExplicitAppUserModelID
        fn.argtypes = [ctypes.c_wchar_p]
        fn.restype = ctypes.c_long
        if fn(APP_USER_MODEL_ID) != 0:
            logger.debug('the shell refused our app identity')
    except Exception:
        logger.opt(exception=True).debug('could not set the app identity')


# --- The media flyout's "Unknown app" -------------------------------------
#
# Windows' now-playing flyout names the app that owns the media session. In a
# WebView2 app that is not us: Chromium registers the session from
# msedgewebview2.exe, which has no identity of its own, so Windows shows
# "Unknown app" over our title and artwork. It is a known WebView2 gap that
# Microsoft has acknowledged and not fixed (WebView2Feedback #2236).
#
# There is one lever available. Windows resolves a window's app identity from
# its shell property store before falling back to the process, so stamping
# PKEY_AppUserModel_ID onto the windows Chromium registers from can give the
# session a name. Strictly a best effort: it touches windows we do not own,
# only ever inside our own process tree, and every call is allowed to fail.

_PKEY_APPUSERMODEL_ID_FMTID = '{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}'


_PKEY_APPUSERMODEL_ID_PID = 5


_IID_IPROPERTYSTORE = '{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}'


# WebView2 builds its windows lazily and rebuilds them when the page
# navigates, so one pass at startup is not enough.
_TAG_DELAYS = (1.5, 5.0, 12.0, 30.0)


# _GUID is the one defined for the taskbar near the top of this file. This
# part used to define a second class of the same name, which silently replaced
# the first when the module loaded: the taskbar code then asked the
# replacement for a parse() it did not have, and the play, pause and skip
# buttons on the taskbar thumbnail, and its progress bar, never appeared.


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [('fmtid', _GUID), ('pid', ctypes.c_ulong)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ('vt', ctypes.c_ushort),
        ('r1', ctypes.c_ushort),
        ('r2', ctypes.c_ushort),
        ('r3', ctypes.c_ushort),
        ('data', ctypes.c_byte * 16),
    ]


def _guid(text: str) -> _GUID:
    return _GUID.parse(text)


def _our_process_tree() -> set[int]:
    """Every pid descended from this one, so we never touch another app's
    WebView2 (the user may well have several running)."""

    import collections

    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_char * 260),
        ]

    children: dict[int, list[int]] = collections.defaultdict(list)
    # Without these the returned HANDLE is truncated to 32 bits on a 64-bit
    # build and every snapshot looks like a failure.
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    kernel32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return {os.getpid()}
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while ok:
            children[entry.th32ParentProcessID].append(entry.th32ProcessID)
            ok = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    mine = {os.getpid()}
    queue = [os.getpid()]
    while queue:
        for child in children.get(queue.pop(), ()):
            if child not in mine:
                mine.add(child)
                queue.append(child)
    return mine


def _stamp_window_identity(hwnd: int) -> bool:
    ptr = ctypes.c_void_p()
    iid = _guid(_IID_IPROPERTYSTORE)
    if shell32.SHGetPropertyStoreForWindow(
        wintypes.HWND(hwnd), ctypes.byref(iid), ctypes.byref(ptr)
    ) != 0 or not ptr:
        return False
    try:
        # VT_LPWSTR: the store takes ownership of a CoTaskMemAlloc'd copy.
        size = (len(APP_USER_MODEL_ID) + 1) * 2
        ole32.CoTaskMemAlloc.restype = ctypes.c_void_p
        ole32.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]
        mem = ole32.CoTaskMemAlloc(ctypes.c_size_t(size))
        if not mem:
            return False
        ctypes.memmove(mem, ctypes.c_wchar_p(APP_USER_MODEL_ID), size)
        value = _PROPVARIANT()
        ctypes.memset(ctypes.byref(value), 0, ctypes.sizeof(value))
        value.vt = 31
        ctypes.memmove(
            ctypes.byref(value, 8),
            ctypes.byref(ctypes.c_void_p(mem)),
            ctypes.sizeof(ctypes.c_void_p),
        )
        table = ctypes.cast(
            ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        )[0]
        set_value = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(_PROPERTYKEY),
            ctypes.POINTER(_PROPVARIANT),
        )(table[6])
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(table[7])
        key = _PROPERTYKEY(
            _guid(_PKEY_APPUSERMODEL_ID_FMTID), _PKEY_APPUSERMODEL_ID_PID
        )
        ok = set_value(ptr, ctypes.byref(key), ctypes.byref(value)) == 0
        commit(ptr)
        return ok
    finally:
        table = ctypes.cast(
            ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        )[0]
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(ptr)


def _tag_media_windows() -> int:
    """Stamp our identity on every window in our tree that Windows might ask
    about. Returns how many took it."""

    if not _WIN:
        return 0
    try:
        mine = _our_process_tree()
        tagged = 0

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):  # noqa: ANN001
            nonlocal tagged
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in mine:
                return True
            name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, name, 64)
            # Chromium's own top-level windows, plus our real one.
            if name.value.startswith('Chrome_WidgetWin') or hwnd == _main_hwnd():
                if _stamp_window_identity(hwnd):
                    tagged += 1
            return True

        user32.EnumWindows(visit, 0)
        return tagged
    except Exception:
        logger.opt(exception=True).debug('could not tag the media windows')
        return 0


# The window's bridge object, once main() has made it. This used to read a
# name that only existed inside main(), so it always came back 0 and the
# main window was never among the windows stamped with our identity.


def _main_hwnd() -> int:
    try:
        return int(getattr(state.api, '_hwnd', 0) or 0)
    except Exception:
        return 0


def _schedule_media_identity() -> None:
    """Re-stamp a few times: WebView2 creates and replaces these windows
    after the app is already up."""

    def run(delay: float) -> None:
        time.sleep(delay)
        count = _tag_media_windows()
        if count:
            logger.debug('media identity applied to {} window(s)', count)

    for delay in _TAG_DELAYS:
        threading.Thread(
            target=run, args=(delay,), name='dannify-media-id', daemon=True
        ).start()
