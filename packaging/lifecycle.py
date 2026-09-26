"""Lifecycle checks for the installer, launcher and updater, in a sandbox.

Run after build.ps1, from anywhere:

    python packaging/lifecycle.py install launch update restart rollback uninstall
    set LIFE_NAME=mig & set LIFE_LEGACY=<an installed 3.x folder> & python packaging/lifecycle.py migrate

Everything lives under %TEMP%\\dannify-life\\<LIFE_NAME>. The installer and
launcher get --sandbox, which moves every registry key under
HKCU\\Software\\DannifySetupTest\\<name> and every shortcut into a folder
beside the install. Every app process gets DANNIFY_DATA_DIR, DOWNLOAD_DIR and
DANNIFY_INSTANCE in its own environment only, so it can never reach a real
library or clash with a copy that is open. Never set those in a shell.

Updates come from a stand-in for GitHub's release API on 127.0.0.1 (the app
only honours DANNIFY_UPDATE_API for localhost), serving releases made from
the real build with a few files changed. Windows of the sandbox app appear on
screen while the stages run.

Exits 1 if any check fails.
"""
import ctypes
import ctypes.wintypes as wt
import hashlib
import http.server
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import winreg
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERSION = re.search(r"__version__\s*=\s*'([^']+)'",
                    (REPO / 'Backend' / 'dannify' / '__init__.py').read_text(encoding='utf-8')).group(1)
SETUP = REPO / 'packaging' / 'out' / f'Dannify-Setup-{VERSION}.exe'
DIST = REPO / 'Backend' / 'dist' / 'Dannify'
_VENV = REPO / 'Backend' / 'venv' / 'Scripts' / 'python.exe'
PYTHON = str(_VENV if _VENV.exists() else sys.executable)

SCR = Path(os.path.realpath(os.environ['TEMP'])) / 'dannify-life'
NAME = os.environ.get('LIFE_NAME', 'life')
ROOT = SCR / NAME / 'Programs' / 'Dannify'
SIDE = Path(str(ROOT) + '.sandbox')
DATA = SCR / NAME / 'data'
MUSIC = SCR / NAME / 'Music'
REG = rf'Software\DannifySetupTest\{NAME}'
RELEASES = SCR / 'releases'
INNO = r'{7E1D8F0C-5A53-4D7B-9C2B-DA221F900001}_is1'

user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
try:
    # Real pixel sizes, or window pictures come out cropped on a scaled display.
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
FAILED = []


def later(n):
    """The version n patch releases after this one."""
    major, minor, patch = (int(x) for x in VERSION.split('.')[:3])
    return f'{major}.{minor}.{patch + n}'


def env():
    e = {k: v for k, v in os.environ.items() if not k.upper().startswith(('DANNIFY_', 'DOWNTIFY_'))}
    e.pop('DATABASE_DIR', None)
    e.update(DANNIFY_DATA_DIR=str(DATA), DOWNLOAD_DIR=str(MUSIC), DANNIFY_INSTANCE=NAME)
    return e


def app_env(port):
    e = env()
    e['DANNIFY_UPDATE_API'] = f'http://127.0.0.1:{port}'
    return e


def run(args, timeout=180):
    t = time.time()
    r = subprocess.run(args, env=env(), timeout=timeout)
    return r.returncode, time.time() - t


def launch(port=None, *extra, wait=30):
    """Start the installed app the way a shortcut does."""
    args = [str(ROOT / 'Dannify.exe'), *extra, '--sandbox', NAME]
    return subprocess.Popen(args, env=app_env(port) if port else env()).wait(wait)


def check(label, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + label + (f'  [{detail}]' if detail else ''), flush=True)
    if not ok:
        FAILED.append(label)
    return ok


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def reg_values(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            out, i = {}, 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    return out
                out[name] = value
                i += 1
    except OSError:
        return None


def powershell(script):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def lnk_info(path):
    """'<target>|<app identity>' of a shortcut."""
    path = Path(path)
    return powershell(
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{path}');"
        f"$f=(New-Object -ComObject Shell.Application).NameSpace('{path.parent}').ParseName('{path.name}');"
        "Write-Output ($s.TargetPath + '|' + $f.ExtendedProperty('System.AppUserModel.ID'))"
    )


def make_lnk(path, target):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    powershell(f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{path}');$s.TargetPath='{target}';$s.Save()")


def procs_under(folder):
    out = powershell("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like '" + str(folder)
                     + "\\*' } | ForEach-Object { \"$($_.ProcessId)|$($_.ExecutablePath)\" }")
    return [line for line in out.splitlines() if line.strip()]


def windows_of(pid):
    """Visible top-level windows of a process, largest first."""
    found = []
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def each(h, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(h):
            r = wt.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), h))
        return True

    user32.EnumWindows(proc(each), 0)
    return [h for _, h in sorted(found, reverse=True)]


def app_pid(timeout=60):
    """The installed app's process once its window is up."""
    t = time.time()
    while time.time() - t < timeout:
        for line in procs_under(ROOT / 'app'):
            pid = int(line.split('|')[0])
            if line.lower().endswith('\\app\\dannify.exe') and windows_of(pid):
                return pid
        time.sleep(0.5)
    return None


def signal_quit():
    """The app's own quit request, as the installer sends it."""
    kernel32.OpenEventW.restype = ctypes.c_void_p
    h = kernel32.OpenEventW(0x0002, False, 'Local\\DannifyQuitRequest' + NAME)
    if h:
        kernel32.SetEvent(ctypes.c_void_p(h))
        kernel32.CloseHandle(ctypes.c_void_p(h))


def quit_app(timeout=30):
    signal_quit()
    t = time.time()
    while time.time() - t < timeout:
        if not procs_under(ROOT):
            return True
        time.sleep(0.5)
    return False


def wait_ready(timeout=150):
    ready = ROOT / 'app-next' / '.ready'
    t = time.time()
    while time.time() - t < timeout and not ready.exists():
        time.sleep(0.5)
    return ready.exists()


class _BIH(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                ('biBitCount', wt.WORD), ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG), ('biClrUsed', wt.DWORD),
                ('biClrImportant', wt.DWORD)]


def snap(hwnd, out):
    """A PNG of one window, drawn by the window itself (works when covered)."""
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(_BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    rows = []
    for y in range(h):
        line = buf.raw[y * w * 4:(y + 1) * w * 4]
        rgb = bytearray(w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = line[2::4], line[1::4], line[0::4]
        rows.append(b'\x00' + bytes(rgb))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)

    Path(out).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                          + chunk(b'IDAT', zlib.compress(b''.join(rows), 6)) + chunk(b'IEND', b''))


# ---------------------------------------------------------------------------
# A stand-in for the release server
# ---------------------------------------------------------------------------
SERVED = []
_server = None


def build_release(version, tweak):
    """A release made from the real build with a few files changed."""
    src = SCR / f'app-{version}'
    shutil.rmtree(src, ignore_errors=True)
    shutil.copytree(DIST, src)
    tweak(src)
    RELEASES.mkdir(parents=True, exist_ok=True)
    subprocess.run([PYTHON, str(REPO / 'packaging' / 'make_update_assets.py'), str(src), version, str(RELEASES)],
                   check=True, capture_output=True)
    return src


def serve(version, notes='Faster starts.\nA new look for the queue.'):
    """GitHub's latest-release answer and downloads, with byte ranges."""
    global _server
    if _server is not None:
        _server.shutdown()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _file(self, head=False):
            data = (RELEASES / self.path.split('/dl/', 1)[1]).read_bytes()
            rng = self.headers.get('Range')
            if rng:
                a, _, b = rng.split('=', 1)[1].partition('-')
                a, b = int(a), (int(b) if b else len(data) - 1)
                body = data[a:b + 1]
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {a}-{a + len(body) - 1}/{len(data)}')
            else:
                body = data
                self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            if not head:
                self.wfile.write(body)
            SERVED.append((self.path, 0 if head else len(body)))

        def do_HEAD(self):
            self._file(head=True)

        def do_GET(self):
            if '/dl/' in self.path:
                return self._file()
            base = f'http://127.0.0.1:{self.server.server_port}/dl/'
            assets = [{'name': n, 'browser_download_url': base + n, 'size': (RELEASES / n).stat().st_size}
                      for n in (f'package-{version}.json', f'package-{version}.zip')]
            body = json.dumps({'tag_name': f'v{version}', 'name': f'Dannify {version}', 'body': notes,
                               'html_url': 'http://127.0.0.1/', 'published_at': '2026-01-01T00:00:00Z',
                               'assets': assets}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    _server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return _server.server_port


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------
def stage_install():
    shutil.rmtree(SCR / NAME, ignore_errors=True)
    MUSIC.mkdir(parents=True)
    code, took = run([str(SETUP), '--quiet', '--sandbox', NAME, '--root', str(ROOT), '--data', str(DATA)])
    check('quiet install exits 0', code == 0, f'{code} in {took:.1f}s')
    launcher = ROOT / 'Dannify.exe'
    engine = DIST / 'runtime' / 'launcher.exe'
    check('launcher is the engine without the app packed on',
          launcher.is_file() and launcher.stat().st_size == engine.stat().st_size)
    dist = {p.relative_to(DIST).as_posix(): p for p in DIST.rglob('*') if p.is_file()}
    app_dir = ROOT / 'app'
    app = {p.relative_to(app_dir).as_posix(): p for p in app_dir.rglob('*') if p.is_file()} if app_dir.exists() else {}
    same = sum(1 for k in dist if k in app and sha(dist[k]) == sha(app[k]))
    check('app folder identical to the build', same == len(dist) == len(app), f'{same}/{len(dist)}, {len(app)} installed')
    leftovers = sorted(p.name for p in ROOT.iterdir() if p.name not in ('Dannify.exe', 'app'))
    check('nothing else in the install folder', not leftovers, str(leftovers))
    u = reg_values(REG + r'\Uninstall\Dannify') or {}
    check('Apps entry written', u.get('DisplayVersion') == VERSION and u.get('InstallLocation') == str(ROOT),
          str({k: u.get(k) for k in ('DisplayName', 'DisplayVersion', 'InstallLocation')}))
    check('uninstall command', u.get('UninstallString') == f'"{ROOT}\\Dannify.exe" --uninstall', str(u.get('UninstallString')))
    cmd = (reg_values(REG + r'\Classes\Dannify.Track\shell\open\command') or {}).get('')
    check('.dnf opens with the launcher', cmd == f'"{ROOT}\\Dannify.exe" "%1"', str(cmd))
    ap = reg_values(REG + r'\App Paths\Dannify.exe') or {}
    check('Run box entry', ap.get('') == str(launcher), str(ap.get('')))
    start = SIDE / 'Programs' / 'Dannify.lnk'
    si = lnk_info(start) if start.exists() else ''
    check('Start menu shortcut with the app identity', si == f'{launcher}|Dannify.Player', si)
    check('desktop shortcut', (SIDE / 'Desktop' / 'Dannify.lnk').exists())
    real = reg_values(r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Dannify')
    check('the real Apps entry was not touched by the sandbox', real is None or real.get('InstallLocation') != str(ROOT))


def stage_launch():
    t = time.time()
    code = launch()
    check('launcher returns straight away', code == 0, f'{code} in {time.time() - t:.2f}s')
    pid = app_pid(45)
    check('app window up from app\\Dannify.exe', pid is not None, f'{time.time() - t:.1f}s')
    check('app used the sandbox data folder', (DATA / 'instance.json').exists())
    time.sleep(3)
    check('quits when asked', quit_app())


def stage_update():
    new = later(1)

    def tweak(src):
        (src / 'runtime' / 'marker.txt').write_text(new)
        support = src / 'config' / 'support.json'
        support.write_text(support.read_text(encoding='utf-8').rstrip() + '\n', encoding='utf-8')

    build_release(new, tweak)
    port = serve(new)
    SERVED.clear()
    launch(port)
    check('app is up', app_pid() is not None)
    t = time.time()
    check('the app found the update and got it ready by itself', wait_ready(), f'{time.time() - t:.0f}s')
    fetched = sum(n for p, n in SERVED if p.endswith('.zip'))
    size = (RELEASES / f'package-{new}.zip').stat().st_size
    check('only the changed files were downloaded', 0 < fetched < size * 0.05,
          f'{fetched} of {size} bytes, {len(SERVED)} requests')
    if (ROOT / 'app-next').exists():
        dll = next((ROOT / 'app' / 'runtime').glob('python3*.dll'))
        check('unchanged files are shared, not copied',
              os.path.samefile(ROOT / 'app-next' / 'runtime' / dll.name, dll))
    pid = app_pid(5)
    if pid:
        time.sleep(5)  # the title bar offers the update once it is ready
        snap(windows_of(pid)[0], SCR / 'update-ready.png')
        print(f'     picture of the window: {SCR / "update-ready.png"}')
    check('the running app was not touched', not (ROOT / 'app' / 'runtime' / 'marker.txt').exists())
    check('quits', quit_app())
    t = time.time()
    launch(port, wait=60)
    pid = app_pid()
    check('next start comes up on the new version',
          pid is not None and (ROOT / 'app' / 'runtime' / 'marker.txt').exists(), f'{time.time() - t:.1f}s')
    check('the previous version is kept for going back', len(list(ROOT.glob('app-old-*'))) == 1)
    check('nothing left waiting', not (ROOT / 'app-next').exists())
    t = time.time()
    while time.time() - t < 30 and (ROOT / 'app' / '.ready').exists():
        time.sleep(1)
    check('the interface showed what is new and acknowledged it', not (ROOT / 'app' / '.ready').exists())
    check('quits', quit_app())


def stage_restart():
    """What "Restart to update" does: the app starts the launcher with --after
    its own pid, then closes."""
    new = later(1)
    if not (RELEASES / f'package-{new}.zip').exists():
        build_release(new, lambda src: (src / 'runtime' / 'marker.txt').write_text(new))
    port = serve(new)
    # The app still reports the version it was built as, so the same release
    # counts as new again, whatever stage ran before.
    launch(port)
    pid = app_pid()
    check('app is up', pid is not None)
    check('update ready', wait_ready())
    before = sorted(p.name for p in ROOT.glob('app-old-*'))
    t = time.time()
    helper = subprocess.Popen([str(ROOT / 'Dannify.exe'), '--after', str(pid), '--sandbox', NAME], env=app_env(port))
    time.sleep(0.25)
    signal_quit()
    for _ in range(40):
        hwnds = windows_of(helper.pid)
        if hwnds:
            time.sleep(0.4)
            snap(hwnds[0], SCR / 'restart-splash.png')
            break
        time.sleep(0.05)
    code = helper.wait(90)
    again = app_pid(10)
    check('launcher waited, swapped and reopened', code == 0 and again is not None and again != pid,
          f'{time.time() - t:.1f}s, exit {code}')
    after = sorted(p.name for p in ROOT.glob('app-old-*'))
    check('one previous version kept, the one just replaced', len(after) == 1 and after != before,
          f'{before} -> {after}')
    check('now on the new version', (ROOT / 'app' / 'runtime' / 'marker.txt').exists())
    check('splash pictured', (SCR / 'restart-splash.png').exists(), str(SCR / 'restart-splash.png'))
    check('quits', quit_app())


def stage_rollback():
    """An update whose app cannot start: the launcher must bring back the
    version before it and not fetch the bad one again."""
    bad = later(2)
    good_hash = sha(ROOT / 'app' / 'Dannify.exe')
    # A program that exits with an error straight away, like a broken build.
    build_release(bad, lambda src: shutil.copy2(r'C:\Windows\System32\findstr.exe', src / 'Dannify.exe'))
    port = serve(bad)
    launch(port)
    check('app is up', app_pid() is not None)
    check('bad update ready', wait_ready())
    check('quits', quit_app())
    t = time.time()
    code = launch(port, wait=180)
    again = app_pid(20)
    check('the good version came back and runs',
          again is not None and sha(ROOT / 'app' / 'Dannify.exe') == good_hash, f'{time.time() - t:.1f}s, exit {code}')
    skip = ROOT / '.skip-version'
    check('the bad version is remembered', skip.exists() and skip.read_text().strip() == bad,
          skip.read_text() if skip.exists() else '')
    time.sleep(45)  # the app checks 8 s after start and would fetch again 30 s later
    check('and not fetched again', not (ROOT / 'app-next').exists())
    check('quits', quit_app())


def stage_uninstall():
    (DATA / 'settings.json').write_text(json.dumps({'download_dir': str(MUSIC)}))
    (DATA / 'store').mkdir(exist_ok=True)
    (DATA / 'store' / 'keep.dat').write_bytes(b'k')
    (MUSIC / 'song.dnf').write_bytes(b'DNF2 music')
    code, took = run([str(ROOT / 'Dannify.exe'), '--uninstall', '--quiet', '--sandbox', NAME])
    check('quiet uninstall exits 0', code == 0, f'{code} in {took:.1f}s')
    time.sleep(4)  # the last clean-up runs a moment after it exits
    check('install folder gone', not ROOT.exists(), str(list(ROOT.iterdir())) if ROOT.exists() else '')
    check('Apps entry gone', reg_values(REG + r'\Uninstall\Dannify') is None)
    check('file association gone', reg_values(REG + r'\Classes\Dannify.Track') is None)
    check('shortcuts gone', not (SIDE / 'Programs' / 'Dannify.lnk').exists() and not (SIDE / 'Desktop' / 'Dannify.lnk').exists())
    check('sign-in and caches removed', not (DATA / 'WebView2').exists() and not (DATA / 'session.json').exists())
    check('settings kept', (DATA / 'settings.json').exists())
    check('song store kept', (DATA / 'store' / 'keep.dat').exists())
    check('music untouched', (MUSIC / 'song.dnf').read_bytes() == b'DNF2 music')


def stage_migrate():
    """A 3.x copy installed by the old Setup pressing "Restart to update".

    LIFE_LEGACY names a folder holding an installed 3.x copy (what the old
    Setup put in Programs\\Dannify); LIFE_LEGACY_VERSION says which (3.18.1).
    """
    legacy = os.environ.get('LIFE_LEGACY')
    if not legacy or not Path(legacy, 'Dannify.exe').exists():
        print('SKIP migrate: set LIFE_LEGACY to an installed 3.x folder')
        return
    old_version = os.environ.get('LIFE_LEGACY_VERSION', '3.18.1')
    shutil.rmtree(SCR / NAME, ignore_errors=True)
    MUSIC.mkdir(parents=True)
    shutil.copytree(legacy, ROOT)
    (ROOT / 'unins000.exe').write_bytes(b'old uninstaller')
    (ROOT / 'unins000.dat').write_bytes(b'old uninstaller data')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG + '\\Uninstall\\' + INNO) as k:
        winreg.SetValueEx(k, 'InstallLocation', 0, winreg.REG_SZ, str(ROOT) + '\\')
        winreg.SetValueEx(k, 'DisplayVersion', 0, winreg.REG_SZ, old_version)
        winreg.SetValueEx(k, 'DisplayName', 0, winreg.REG_SZ, f'Dannify version {old_version}')
    make_lnk(SIDE / 'Programs' / 'Dannify' / 'Dannify.lnk', ROOT / 'Dannify.exe')
    make_lnk(SIDE / 'Programs' / 'Dannify' / 'Uninstall Dannify.lnk', ROOT / 'unins000.exe')
    make_lnk(SIDE / 'Desktop' / 'Dannify.lnk', ROOT / 'Dannify.exe')
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'settings.json').write_text(json.dumps({'download_dir': str(MUSIC), 'theme': 'dark'}))

    old = subprocess.Popen([str(ROOT / 'Dannify.exe')], env=env())
    t = time.time()
    while time.time() - t < 60 and not windows_of(old.pid):
        time.sleep(0.3)
    check(f'{old_version} is running', bool(windows_of(old.pid)))
    time.sleep(4)

    # What 3.18 does on "Restart to update": open the downloaded setup with no
    # switches, quit 0.4 s later, and on the way out start it again with
    # /VERYSILENT. The sandbox switches only keep the test away from real keys
    # (a sandbox must name its folder; 3.18 names none, and the setup treats
    # both the same way).
    updates_dir = DATA / 'updates'
    updates_dir.mkdir(parents=True, exist_ok=True)
    setup = updates_dir / SETUP.name
    shutil.copy2(SETUP, setup)
    t = time.time()
    first = subprocess.Popen([str(setup), '--sandbox', NAME, '--root', str(ROOT)], env=env())
    time.sleep(0.4)
    signal_quit()
    second = subprocess.Popen([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '--sandbox', NAME,
                               '--root', str(ROOT)], env=env())
    codes = (first.wait(240), second.wait(240))
    check('both setups finish cleanly', codes == (0, 0), f'{codes} in {time.time() - t:.1f}s')
    check(f'{VERSION} is running from the new layout', app_pid(30) is not None)
    check('Dannify.exe in the folder is now the launcher',
          (ROOT / 'Dannify.exe').stat().st_size == (DIST / 'runtime' / 'launcher.exe').stat().st_size)
    check('the old files are gone', not (ROOT / 'runtime').exists() and not (ROOT / 'config').exists()
          and not list(ROOT.glob('unins*')), str(sorted(p.name for p in ROOT.iterdir())))
    check('old Apps entry gone', reg_values(REG + '\\Uninstall\\' + INNO) is None)
    u = reg_values(REG + r'\Uninstall\Dannify') or {}
    check('new Apps entry', u.get('DisplayVersion') == VERSION and u.get('InstallLocation') == str(ROOT))
    check('old Start menu folder replaced by one shortcut',
          not (SIDE / 'Programs' / 'Dannify').exists() and (SIDE / 'Programs' / 'Dannify.lnk').exists())
    di = lnk_info(SIDE / 'Desktop' / 'Dannify.lnk')
    check('desktop shortcut kept, now with the app identity', di == f'{ROOT}\\Dannify.exe|Dannify.Player', di)
    check('settings untouched', json.loads((DATA / 'settings.json').read_text())['download_dir'] == str(MUSIC))
    log = (DATA / 'setup.log').read_text(encoding='utf-8', errors='replace') if (DATA / 'setup.log').exists() else ''
    check('installed once, the second setup found nothing to do',
          log.count(f'] installed {VERSION}') == 1, ' | '.join(line[24:] for line in log.splitlines()[-6:]))
    check('quits', quit_app())


if __name__ == '__main__':
    stages = sys.argv[1:] or ['install', 'launch', 'update', 'restart', 'rollback', 'uninstall']
    if not SETUP.exists():
        sys.exit(f'{SETUP} not found: run packaging\\build.ps1 first')
    for stage in stages:
        print(f'--- {stage}', flush=True)
        globals()[f'stage_{stage}']()
    if _server is not None:
        _server.shutdown()
    print(f'{len(FAILED)} failed' if FAILED else 'all passed')
    sys.exit(1 if FAILED else 0)
