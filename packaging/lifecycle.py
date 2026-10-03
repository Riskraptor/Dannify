"""Lifecycle checks for the installer, launcher and updater, in a sandbox.

Run after build.ps1, from anywhere:

    python packaging/lifecycle.py install launch update restart rollback uninstall
    set LIFE_NAME=mig & set LIFE_LEGACY=<an installed 3.x folder, or packaging\\out\\files-3.x.y.zip> & python packaging/lifecycle.py migrate
    set LIFE_NAME=up & python packaging/lifecycle.py upgrade restart_previous setup_over_previous rollback_previous

The *_previous stages and upgrade start from the release before this one
(LIFE_FROM, 4.0.0 by default), installed by its own setup from packaging\\out
with a library it made itself, and let that copy find and apply this build's
package (packaging\\out\\package-<version>.*) the way a user's does. They check
the running app through what it does for a person (opening a .dnf through the
launcher) and what it writes in its log: its server's session key is its
window's alone.

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
OUT = REPO / 'packaging' / 'out'
# The release users are upgrading from, as it shipped.
PREVIOUS = os.environ.get('LIFE_FROM', '4.0.0')
PREVIOUS_SETUP = OUT / f'Dannify-Setup-{PREVIOUS}.exe'
FFMPEG = REPO / 'packaging' / 'ffmpeg' / 'ffmpeg.exe'

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


def offline(e):
    """*e* with every proxy pointed at a closed port on this machine, so a
    process started with it cannot reach the internet (loopback still can)."""
    dead = 'http://127.0.0.1:9'
    return {**e, 'HTTP_PROXY': dead, 'HTTPS_PROXY': dead, 'ALL_PROXY': dead, 'NO_PROXY': '127.0.0.1,localhost,::1'}


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
# Watching the running app
# ---------------------------------------------------------------------------
# The app's server answers nothing without the session key it hands only to
# its own window, and a test has no business holding that key. So a test
# asks the app to do things the way a person does (open a .dnf the way
# Explorer does, through the launcher) and reads what the app wrote in its
# log in the sandbox data folder.
def app_log():
    try:
        return (DATA / 'dannify.log').read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def open_with_app(path, port, timeout=45):
    """Open *path* the way double-clicking it does, and return what the app
    logged about it: its own requests for the file and any complaint.

    Only tickets handed out for this file count: a file opened just before
    is still being played, and its player keeps asking for more of it (the
    audio is never cached, so it asks again as it buffers)."""
    before = app_log()
    mark = len(before)
    earlier = set(re.findall(r'GET /opened/([A-Za-z0-9_-]+)', before))

    def requests(text):
        return [
            line for line in text.splitlines()
            if 'GET /opened/' in line and 'cover=1' not in line
            and not any(f'/opened/{k}' in line for k in earlier)
        ]

    launch(port, str(path))
    t, name = time.time(), Path(path).name
    while time.time() - t < timeout:
        new = app_log()[mark:]
        served = requests(new)
        refused = [line for line in new.splitlines() if 'cannot open' in line and name in line]
        if refused or any(re.search(r' (200|206) ', line) for line in served):
            return served, refused
        time.sleep(1)
    new = app_log()[mark:]
    return requests(new), [line for line in new.splitlines() if 'cannot open' in line and name in line]


def open_with_vault(data, songs):
    """What this build's vault (Backend/dannify/vault.py, the source it was
    built from) makes of *songs* with the keys in *data*: {name: (problem,
    sha256 of what it decrypts to)}. In a process of its own, so nothing of
    the app's is loaded into this one."""
    code = '; '.join([
        'import hashlib, json, sys',
        'sys.path.insert(0, sys.argv[1])',
        'from pathlib import Path',
        'from dannify import vault',
        'vault.init(Path(sys.argv[2]))',
        'heads = {p: vault.inspect(p) for p in map(Path, sys.argv[3:])}',
        'print(json.dumps({p.name: [problem, hashlib.sha256(b"".join(vault.open_range(p)) if not problem else b"")'
        '.hexdigest()] for p, (head, problem) in heads.items()}))',
    ])
    r = subprocess.run([PYTHON, '-c', code, str(REPO / 'Backend'), str(data), *map(str, songs)],
                       capture_output=True, text=True, timeout=120, env=env())
    try:
        return {k: tuple(v) for k, v in json.loads(r.stdout.strip().splitlines()[-1]).items()}
    except (ValueError, IndexError):
        return {'error': (r.stderr.strip()[-300:], '')}


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


def serve(version, notes='Faster starts.\nA new look for the queue.', folder=None):
    """GitHub's latest-release answer and downloads, with byte ranges.

    The assets come from RELEASES, or from *folder* (packaging\\out, to serve
    a release exactly as it was built)."""
    global _server
    if _server is not None:
        _server.shutdown()
    source = Path(folder or RELEASES)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _file(self, head=False):
            data = (source / self.path.split('/dl/', 1)[1]).read_bytes()
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
            assets = [{'name': n, 'browser_download_url': base + n, 'size': (source / n).stat().st_size}
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
def build_files(version=VERSION):
    """{path: (size, sha256)} of a release's app folder: this build, or an
    earlier release's package list."""
    if version == VERSION:
        return {p.relative_to(DIST).as_posix(): (p.stat().st_size, sha(p)) for p in DIST.rglob('*') if p.is_file()}
    files = json.loads((OUT / f'package-{version}.json').read_text(encoding='utf-8'))['files']
    return {rel: (meta['size'], meta['sha256']) for rel, meta in files.items()}


def installed_files(folder):
    folder = Path(folder)
    return {p.relative_to(folder).as_posix(): p for p in folder.rglob('*') if p.is_file()} if folder.exists() else {}


def same_files(folder, expected):
    """How many files of *folder* are exactly the release's, and how many it has."""
    have = installed_files(folder)
    return sum(1 for k, (_, h) in expected.items() if k in have and sha(have[k]) == h), len(have)


def stage_install(setup=SETUP, version=VERSION):
    shutil.rmtree(SCR / NAME, ignore_errors=True)
    MUSIC.mkdir(parents=True)
    code, took = run([str(setup), '--quiet', '--sandbox', NAME, '--root', str(ROOT), '--data', str(DATA)])
    check('quiet install exits 0', code == 0, f'{version}: {code} in {took:.1f}s')
    launcher = ROOT / 'Dannify.exe'
    expected = build_files(version)
    check('launcher is the engine without the app packed on',
          launcher.is_file() and launcher.stat().st_size == expected['runtime/launcher.exe'][0])
    same, count = same_files(ROOT / 'app', expected)
    check('app folder identical to the build', same == len(expected) == count,
          f'{same}/{len(expected)}, {count} installed')
    leftovers = sorted(p.name for p in ROOT.iterdir() if p.name not in ('Dannify.exe', 'app'))
    check('nothing else in the install folder', not leftovers, str(leftovers))
    u = reg_values(REG + r'\Uninstall\Dannify') or {}
    check('Apps entry written', u.get('DisplayVersion') == version and u.get('InstallLocation') == str(ROOT),
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
        # One file that was already there changes too, not only a new one.
        changed = src / 'runtime' / 'webview' / 'js' / 'state.js'
        changed.write_text(changed.read_text(encoding='utf-8').rstrip() + '\n', encoding='utf-8')

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


def stage_restart(new=None, folder=None, arrived=None):
    """What "Restart to update" does: the app starts the launcher with --after
    its own pid, then closes. *new* served from *folder* (a release as built)
    and *arrived* (how to tell it is running) are for starting from another
    release; by default it is a tweaked copy of this build."""
    new = new or later(1)
    if folder is None and not (RELEASES / f'package-{new}.zip').exists():
        build_release(new, lambda src: (src / 'runtime' / 'marker.txt').write_text(new))
    arrived = arrived or (lambda: (ROOT / 'app' / 'runtime' / 'marker.txt').exists())
    port = serve(new, folder=folder)
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
    check('now on the new version', arrived())
    check('splash pictured', (SCR / 'restart-splash.png').exists(), str(SCR / 'restart-splash.png'))
    check('quits', quit_app())


def stage_rollback(bad=None):
    """An update whose app cannot start: the launcher must bring back the
    version before it and not fetch the bad one again."""
    bad = bad or later(2)
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


# ---------------------------------------------------------------------------
# From the release before this one
# ---------------------------------------------------------------------------
SONG_ID = 'LfCyUpgr4x0'  # the video id tag every download carries
# What 4.0 saved when anything in Settings changed: all of this, merged.
PREVIOUS_DEFAULTS = {
    'audio_providers': ['youtube-music'], 'lyrics_providers': ['lrclib'], 'download_lyrics': True,
    'format': 'mp3', 'bitrate': '320', 'output': '{artists} - {title}.{output-ext}', 'generate_m3u': True,
    'max_parallel_downloads': 3, 'organize_by_artist': True, 'download_dir': '', 'lyrics_storage': 'sidecar',
}


def make_song(path, title, artist, video_id=''):
    """A few seconds of real audio, tagged the way a download is (or not)."""
    args = [str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
            # Quiet: the sandbox app plays it on this PC's speakers.
            '-i', 'sine=frequency=440:duration=6', '-af', 'volume=0.03', '-ac', '2', '-ar', '44100', '-b:a', '128k',
            '-id3v2_version', '3', '-metadata', f'title={title}', '-metadata', f'artist={artist}',
            '-metadata', 'album=Upgrade Sessions']
    if video_id:
        args += ['-metadata', f'DANNIFY_VIDEO_ID={video_id}']
    subprocess.run(args + [str(path)], check=True, capture_output=True, timeout=60)
    return Path(path).read_bytes()


def music_files(folder):
    """{path: sha256} of what a person keeps in a music folder: everything but
    the app's own bookkeeping in .dannify."""
    folder = Path(folder)
    return {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*')
            if p.is_file() and '.dannify' not in p.relative_to(folder).parts}


def chose(saved, choices):
    """Whether a settings dict holds these choices (folders compared as folders)."""
    return all((Path(saved.get(k) or '.') == Path(v)) if k == 'download_dir' else saved.get(k) == v
               for k, v in choices.items())


def file_version(path):
    return powershell(f"(Get-Item '{path}').VersionInfo.ProductVersion")


def ready_marker(folder):
    try:
        return json.loads((Path(folder) / '.ready').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


class Library:
    """A library made by the previous release, and what it looked like."""
    folder = sealed = copy = original = choices = None
    keys = shelf = settings = None


def previous_library(port):
    """The previous release makes its data folder and key, is given its own
    music folder and choices, and seals a song into it. Left running."""
    lib = Library()
    lib.folder = SCR / NAME / 'My Music'
    # 1. First start: the previous version makes its data folder and its key.
    launch(port)
    check(f'{PREVIOUS} is up', app_pid() is not None)
    time.sleep(5)
    check('quits', quit_app())
    store = DATA / 'store'
    check(f'{PREVIOUS} made its key', any(store.glob('*.dat')), str(sorted(p.name for p in store.glob('*'))))
    # Its own music folder and the choices 4.0 still offered, in the file it
    # keeps them in, the way it writes it (everything, merged, indented).
    lib.folder.mkdir(parents=True, exist_ok=True)
    lib.choices = {'download_dir': str(lib.folder), 'format': 'mp3', 'bitrate': '320', 'generate_m3u': True}
    settings = DATA / 'settings.json'
    try:
        mine = json.loads(settings.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        mine = {}
    settings.write_text(json.dumps({**PREVIOUS_DEFAULTS, **mine, **lib.choices}, indent=2), encoding='utf-8')

    # 2. A song saved by the previous version. A download it had not sealed
    #    yet is sealed at its next start, with its key (vault.migrate), and
    #    that start also joins it to the music folder chosen above.
    plain = lib.folder / 'Lifecycle Test - Upgrade Tone.mp3'
    lib.original = make_song(plain, 'Upgrade Tone', 'Lifecycle Test', SONG_ID)
    check('test song is tagged as a download', SONG_ID.encode() in lib.original[:4096])
    (lib.folder / 'Lifecycle Test - Upgrade Tone.lrc').write_text('[00:00.00]one\n[00:03.00]two\n', encoding='utf-8')
    (lib.folder / 'Road Trip.m3u').write_text(
        '#EXTM3U\n#EXTINF:6,Lifecycle Test - Upgrade Tone\nLifecycle Test - Upgrade Tone.mp3\n', encoding='utf-8')
    lib.sealed = plain.with_suffix('.dnf')
    launch(port)
    check(f'{PREVIOUS} is up', app_pid() is not None)
    t = time.time()
    while time.time() - t < 90 and not (lib.sealed.exists() and not plain.exists()):
        time.sleep(1)
    check(f'{PREVIOUS} sealed the song in the chosen folder with its own key',
          lib.sealed.exists() and not plain.exists() and lib.sealed.read_bytes()[:4] == b'DNF2'
          and any((lib.folder / '.dannify').glob('*.dat')), f'{time.time() - t:.0f}s')
    # The same song somewhere else, as it would be after being copied to
    # another folder: opening it gets it a ticket (/opened/...) instead of
    # its library address, and the window's request for it is in the log.
    elsewhere = SCR / NAME / 'Elsewhere'
    elsewhere.mkdir(parents=True, exist_ok=True)
    lib.copy = elsewhere / 'Shared - Upgrade Tone.dnf'
    shutil.copy2(lib.sealed, lib.copy)
    served, refused = open_with_app(lib.copy, port)
    check(f'{PREVIOUS} plays it when it is opened (the log check works)',
          any(re.search(r' (200|206) ', line) for line in served) and not refused,
          ' | '.join(line[20:] for line in (served + refused)[-3:]))
    lib.keys = {p.name: sha(p) for p in store.glob('*')}
    lib.shelf = {p.name: sha(p) for p in (lib.folder / '.dannify').glob('*.dat')}
    lib.settings = settings.read_text(encoding='utf-8')
    return lib


def add_own_file(lib):
    """A file somebody put in the folder themselves. Not a download, so not
    the app's to convert: it must be left exactly as it is. Returns what the
    folder holds now."""
    make_song(lib.folder / 'Somebody Else - Their Own Recording.mp3', 'Their Own Recording', 'Somebody Else')
    return music_files(lib.folder)


def library_survived(lib, port, mark, music_before):
    """With this build running on a library the previous release made."""
    since = app_log()[mark:]
    check(f'{VERSION} kept the music folder chosen in Settings',
          'is not usable' not in since, next((line for line in since.splitlines() if 'is not usable' in line), ''))
    check(f'{VERSION} opened the keys {PREVIOUS} made',
          'could not be opened on this account' not in since and 'Could not set up saved music' not in since)
    settings = DATA / 'settings.json'
    after = json.loads(settings.read_text(encoding='utf-8'))
    check(f'settings.json from {PREVIOUS} kept, choices and all', chose(after, lib.choices),
          'unchanged' if settings.read_text(encoding='utf-8') == lib.settings
          else str({k: after.get(k) for k in lib.choices}))
    store = DATA / 'store'
    check(f'every key {PREVIOUS} made is still there, unchanged',
          all((store / n).is_file() and sha(store / n) == h for n, h in lib.keys.items()),
          f'{sorted(lib.keys)} -> {sorted(p.name for p in store.glob("*"))}')
    check('and the music folder still carries its keys',
          all((lib.folder / '.dannify' / n).is_file() for n in lib.shelf), str(sorted(lib.shelf)))

    # The song, through the running app, the way a person plays it.
    served, refused = open_with_app(lib.copy, port)
    check(f'{VERSION} plays the song {PREVIOUS} sealed',
          any(re.search(r' (200|206) ', line) for line in served) and not refused,
          ' | '.join(line[20:] for line in (served + refused)[-3:]))
    served, refused = open_with_app(lib.sealed, port, timeout=15)
    check('and the one in the music folder opens as a library track (not from outside it)',
          not served and not refused, ' | '.join(line[20:] for line in (served + refused)[-3:]))
    # And byte for byte, through this build's own vault code with the keys
    # the previous release left in the data folder.
    opened = open_with_vault(DATA, [lib.sealed, lib.copy])
    want = hashlib.sha256(lib.original).hexdigest()
    check(f"{VERSION}'s vault opens it with no problem, and it is exactly the song that was saved",
          all(opened.get(p.name) == ('', want) for p in (lib.sealed, lib.copy)),
          str({k: (v[0] or 'ok', v[1] == want) for k, v in opened.items()}))

    music_after = music_files(lib.folder)
    gone = sorted(set(music_before) - set(music_after))
    check('nothing in the music folder was deleted', not gone, str(gone))
    changed = sorted(k for k in music_before if k in music_after and music_after[k] != music_before[k])
    check('nothing in it was rewritten', not changed, str(changed))
    own = lib.folder / 'Somebody Else - Their Own Recording.mp3'
    check('a file the user put there themselves is left as it was',
          own.is_file() and not own.with_suffix('.dnf').exists(), str(sorted(music_after)))


def launcher_refreshed(timeout=90):
    engine = build_files(VERSION)['runtime/launcher.exe'][1]
    t = time.time()
    while time.time() - t < timeout and sha(ROOT / 'Dannify.exe') != engine:
        time.sleep(2)
    check(f'the launcher itself became the {VERSION} one', sha(ROOT / 'Dannify.exe') == engine,
          f'{time.time() - t:.0f}s')


def stage_upgrade():
    """What most users do: the release before this one, installed by its own
    setup and holding a library it made, finds this build by itself, gets it
    ready while it runs, and the next start (through the launcher it
    installed) comes up on it with everything as it was."""
    if not PREVIOUS_SETUP.exists() or not (OUT / f'package-{VERSION}.zip').exists():
        print(f'SKIP upgrade: needs {PREVIOUS_SETUP.name} and package-{VERSION}.json/.zip in {OUT}')
        return
    stage_install(PREVIOUS_SETUP, PREVIOUS)
    old, new = build_files(PREVIOUS), build_files(VERSION)
    # While the library is made, the stand-in's latest release is the one
    # running, so nothing is fetched before this build is published.
    lib = previous_library(serve(PREVIOUS, folder=OUT))
    check('quits', quit_app())

    # 3. The release. The previous version finds this build and gets it ready.
    port = serve(VERSION, folder=OUT)
    SERVED.clear()
    old_exe = sha(ROOT / 'app' / 'Dannify.exe')
    launch(port)
    check(f'{PREVIOUS} is up', app_pid() is not None)
    t = time.time()
    check(f'{PREVIOUS} found {VERSION} and got it ready by itself', wait_ready(), f'{time.time() - t:.0f}s')
    marker = ready_marker(ROOT / 'app-next')
    check(f'what is waiting says {VERSION}', marker.get('version') == VERSION, str(marker))
    same, count = same_files(ROOT / 'app-next', new)
    check(f'what is waiting is exactly the {VERSION} build', same == len(new) and count == len(new) + 1,
          f'{same}/{len(new)}, {count - 1} files')
    fetched = sum(n for p, n in SERVED if p.endswith('.zip'))
    size = (OUT / f'package-{VERSION}.zip').stat().st_size
    check('only the changed files were downloaded', 0 < fetched < size * 0.5,
          f'{fetched} of {size} bytes, {len(SERVED)} requests')
    check('the running copy was not touched', sha(ROOT / 'app' / 'Dannify.exe') == old_exe)
    check('quits', quit_app())
    music_before = add_own_file(lib)

    # 4. The next start, through the launcher the previous setup installed.
    mark = len(app_log())
    t = time.time()
    code = launch(port, wait=90)
    pid = app_pid()
    check(f'next start comes up on {VERSION}',
          pid is not None and sha(ROOT / 'app' / 'Dannify.exe') == new['Dannify.exe'][1]
          and file_version(ROOT / 'app' / 'Dannify.exe') == VERSION, f'{time.time() - t:.1f}s, exit {code}')
    same, count = same_files(ROOT / 'app', new)
    check(f'app folder is the {VERSION} build', same == len(new), f'{same}/{len(new)}')
    parked = list(ROOT.glob('app-old-*'))
    check(f'{PREVIOUS} is kept for going back',
          len(parked) == 1 and sha(parked[0] / 'Dannify.exe') == old['Dannify.exe'][1], str([p.name for p in parked]))
    check('nothing left waiting', not (ROOT / 'app-next').exists())
    u = reg_values(REG + r'\Uninstall\Dannify') or {}
    check(f'Apps entry says {VERSION}', u.get('DisplayVersion') == VERSION, str(u.get('DisplayVersion')))
    library_survived(lib, port, mark, music_before)
    launcher_refreshed()
    check('the interface showed what is new and acknowledged it', not (ROOT / 'app' / '.ready').exists())
    errors = [line[20:] for line in app_log()[mark:].splitlines() if ' ERROR ' in line]
    check(f'no errors in the log since {VERSION} started', not errors, ' | '.join(errors[-3:]))
    check('quits', quit_app())

    # 5. And once more, now that the new launcher starts it.
    launch(port, wait=60)
    pid = app_pid()
    check(f'{VERSION} starts again through its own launcher', pid is not None
          and sha(ROOT / 'app' / 'Dannify.exe') == new['Dannify.exe'][1])
    check('quits', quit_app())


def stage_setup_over_previous():
    """The other way an existing user gets this build: this setup, from the
    downloads page, run over the previous release while it is open."""
    if not PREVIOUS_SETUP.exists():
        print(f'SKIP setup_over_previous: needs {PREVIOUS_SETUP.name} in {OUT}')
        return
    stage_install(PREVIOUS_SETUP, PREVIOUS)
    new = build_files(VERSION)
    port = serve(PREVIOUS, folder=OUT)
    lib = previous_library(port)  # and still open
    music_before = add_own_file(lib)
    mark = len(app_log())
    code, took = run([str(SETUP), '--quiet', '--sandbox', NAME, '--root', str(ROOT), '--data', str(DATA)])
    check(f'quiet setup over a running {PREVIOUS} exits 0', code == 0, f'{code} in {took:.1f}s')
    check(f'{PREVIOUS} was closed for it', not procs_under(ROOT / 'app'))
    same, count = same_files(ROOT / 'app', new)
    check(f'app folder is the {VERSION} build', same == len(new) == count, f'{same}/{len(new)}, {count} installed')
    check('launcher replaced too', (ROOT / 'Dannify.exe').stat().st_size == new['runtime/launcher.exe'][0])
    u = reg_values(REG + r'\Uninstall\Dannify') or {}
    check(f'Apps entry says {VERSION}', u.get('DisplayVersion') == VERSION, str(u.get('DisplayVersion')))
    check('shortcuts still there', (SIDE / 'Programs' / 'Dannify.lnk').exists() and (SIDE / 'Desktop' / 'Dannify.lnk').exists())
    launch(port, wait=60)
    check(f'{VERSION} is up', app_pid() is not None)
    library_survived(lib, port, mark, music_before)
    check('quits', quit_app())


def stage_restart_previous():
    """The previous release has this build ready and the person presses
    "Restart now": its app hands over to the launcher it installed, which
    swaps in this build and opens it."""
    if not PREVIOUS_SETUP.exists():
        print(f'SKIP restart_previous: needs {PREVIOUS_SETUP.name} in {OUT}')
        return
    stage_install(PREVIOUS_SETUP, PREVIOUS)
    want = build_files(VERSION)['Dannify.exe'][1]
    stage_restart(VERSION, OUT, lambda: sha(ROOT / 'app' / 'Dannify.exe') == want)


def stage_rollback_previous():
    """The release before this one fetches this build, and this build cannot
    start on this PC: the version they had must come back, and this one must
    not be fetched again. The mechanism is the rollback stage's; what is new
    here is that the launcher and updater doing it are the previous release's."""
    if not PREVIOUS_SETUP.exists():
        print(f'SKIP rollback_previous: needs {PREVIOUS_SETUP.name} in {OUT}')
        return
    stage_install(PREVIOUS_SETUP, PREVIOUS)
    stage_rollback(VERSION)
    check(f'what came back is {PREVIOUS}', file_version(ROOT / 'app' / 'Dannify.exe') == PREVIOUS,
          file_version(ROOT / 'app' / 'Dannify.exe'))


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
    Setup put in Programs\\Dannify), or a 3.x files-<version>.zip from
    packaging\\out, which holds exactly that folder; LIFE_LEGACY_VERSION says
    which (3.18.1, or the zip's version).

    The 3.x copy runs with no way out to the internet. It only knows the real
    release server, and one that found an update there would download the
    real setup and run it, without --sandbox, as it closed.
    """
    legacy = os.environ.get('LIFE_LEGACY')
    zipped = re.match(r'files-(\d+(?:\.\d+)*)\.zip$', Path(legacy or '').name)
    if legacy and zipped and Path(legacy).is_file():
        folder = SCR / 'legacy' / zipped.group(1)
        if not (folder / 'Dannify.exe').exists():
            import zipfile
            shutil.rmtree(folder, ignore_errors=True)
            with zipfile.ZipFile(legacy) as z:
                z.extractall(folder)
        legacy = str(folder)
    if not legacy or not Path(legacy, 'Dannify.exe').exists():
        print('SKIP migrate: set LIFE_LEGACY to an installed 3.x folder')
        return
    old_version = os.environ.get('LIFE_LEGACY_VERSION', zipped.group(1) if zipped else '3.18.1')
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

    old = subprocess.Popen([str(ROOT / 'Dannify.exe')], env=offline(env()))
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
    first = subprocess.Popen([str(setup), '--sandbox', NAME, '--root', str(ROOT)], env=offline(env()))
    time.sleep(0.4)
    signal_quit()
    second = subprocess.Popen([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '--sandbox', NAME,
                               '--root', str(ROOT)], env=offline(env()))
    codes = (first.wait(240), second.wait(240))
    check('both setups finish cleanly', codes == (0, 0), f'{codes} in {time.time() - t:.1f}s')
    fetched = sorted(p.name for p in updates_dir.iterdir() if p.name != setup.name)
    check(f'{old_version} downloaded nothing of its own', not fetched, str(fetched))
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
    sys.stdout.reconfigure(errors='backslashreplace')  # the app's log lines carry icons
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
