"""Start a built Dannify.app the way a person would, and check it holds up.

    python packaging/macos/smoke_test.py packaging/macos/out/macos-Dannify-<v>-<arch>.zip

Run by CI on each Mac it builds for, with the app taken out of the release
zip exactly as the updater and the download page hand it over:

1. The bundled tools run, and the app is signed whole.
2. The app starts, its server comes up, it stays up, it says it started (the
   updater's marker), and it quits when asked through its instance socket.
3. Started through LaunchServices with `open -n --env` (how a restart starts
   it), it keeps the data folder it was given.
4. The real updater (dannify/shell/macos/updater.py) puts an update in place
   over a copy of it: the new version starts and removes the backup.
5. A broken update is taken back out: the previous version returns and starts
   again, and the bad version is noted so it is not offered again.

Each copy gets a data folder of its own: nothing here touches a real one.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Backend'))

STARTED = 'Application startup complete'
WORK = Path(tempfile.mkdtemp(prefix='dnf', dir='/tmp'))  # short: socket paths are limited
DATA_DIRS: list[Path] = []


def step(text: str) -> None:
    print(f'\n== {text}', flush=True)


def fail(text: str) -> None:
    print(f'\nFAILED: {text}', flush=True)
    screenshot('failed')
    for data in DATA_DIRS:
        for name in ('dannify.log', 'updates/update.log', 'stdout.log'):
            path = data / name
            if path.is_file():
                print(f'\n--- {path} (last 80 lines)')
                print('\n'.join(path.read_text(errors='replace').splitlines()[-80:]))
    reports = Path.home() / 'Library' / 'Logs' / 'DiagnosticReports'
    for report in sorted(reports.glob('Dannify*'))[-2:]:
        print(f'\n--- {report}')
        print(report.read_text(errors='replace')[:6000])
    sys.exit(1)


def screenshot(name: str) -> None:
    """The screen as it is, for a person to look at afterwards (CI uploads
    DANNIFY_SMOKE_SHOTS). Never a reason to fail."""

    folder = os.environ.get('DANNIFY_SMOKE_SHOTS')
    if not folder:
        return
    Path(folder).mkdir(parents=True, exist_ok=True)
    subprocess.run(['/usr/sbin/screencapture', '-x', str(Path(folder) / f'{name}.png')],
                   capture_output=True, timeout=30)


def windows_of(pid: int) -> list:
    """The ordinary windows process *pid* has on screen (not its menu bar item)."""

    import Quartz

    found = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID) or []
    return [w for w in found if int(w.get('kCGWindowOwnerPID', 0)) == pid
            and int(w.get('kCGWindowLayer', 0)) == 0]


def wait_until(check, timeout: float, what: str, step_s: float = 0.25):  # noqa: ANN001
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(step_s)
    fail(f'timed out after {timeout:.0f}s waiting for {what}')
    return None


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class Copy:
    """One running copy of the app, with a data folder of its own."""

    def __init__(self, app: Path, name: str) -> None:
        self.app = app
        self.data = WORK / name
        self.data.mkdir(parents=True, exist_ok=True)
        DATA_DIRS.append(self.data)
        self.proc = None

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith(('PYTHON', 'VIRTUAL_ENV'))}
        env['DANNIFY_DATA_DIR'] = str(self.data)
        return env

    def starts(self) -> int:
        try:
            return (self.data / 'dannify.log').read_text(errors='replace').count(STARTED)
        except OSError:
            return 0

    def start(self) -> None:
        before = self.starts()
        out = open(self.data / 'stdout.log', 'ab')  # noqa: SIM115
        exe = self.app / 'Contents' / 'MacOS' / 'Dannify'
        self.proc = subprocess.Popen([str(exe)], env=self.env(), stdout=out, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL)
        self.wait_started(before)

    def wait_started(self, before: int, timeout: float = 120) -> None:
        def up() -> bool:
            if self.proc is not None and self.proc.poll() is not None:
                fail(f'the app exited with {self.proc.returncode} before its server came up')
            return self.starts() > before
        wait_until(up, timeout, f'"{STARTED}" in {self.data}/dannify.log')

    def pid(self) -> int:
        return int(json.loads((self.data / 'instance.json').read_text())['pid'])

    def send(self, message: dict) -> dict:
        path = self.data / 'instance.sock'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect(str(path))
            s.sendall(json.dumps(message).encode() + b'\n')
            reply = s.makefile('rb').readline()
        return json.loads(reply or b'{}')

    def quit(self) -> None:
        pid = self.pid()
        if not self.send({'cmd': 'quit'}).get('ok'):
            fail('the app did not take the quit message')
        if self.proc is not None and self.proc.pid == pid:
            try:
                code = self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                fail('the app did not quit within 30s of being asked')
            if code != 0:
                fail(f'the app quit with {code}')
        else:
            wait_until(lambda: not alive(pid), 30, f'process {pid} to quit')
        self.proc = None


def ditto(*args: str) -> None:
    subprocess.run(['/usr/bin/ditto', *args], check=True)


def run(cmd: list, **kw) -> subprocess.CompletedProcess:  # noqa: ANN003
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)


def check_bundle(app: Path) -> None:
    step('the bundle and its tools')
    done = run(['/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=1', str(app)])
    if done.returncode != 0:
        fail(f'codesign --verify: {done.stderr}')
    info = plistlib.loads((app / 'Contents' / 'Info.plist').read_bytes())
    print('bundle', info['CFBundleIdentifier'], info['CFBundleShortVersionString'],
          'min macOS', info.get('LSMinimumSystemVersion'))
    media = next((p for p in app.rglob('dnfmedia') if p.is_file() and not p.is_symlink()), None)
    js = next((p for p in app.rglob('dnfjs') if p.is_file() and not p.is_symlink()), None)
    if media is None or js is None:
        fail('dnfmedia or dnfjs is not in the app')
    version = run([str(media), '-hide_banner', '-version'])
    if version.returncode != 0:
        fail(f'dnfmedia -version: {version.stderr}')
    print(version.stdout.splitlines()[0])
    if 'enable-gpl' in version.stdout or 'enable-nonfree' in version.stdout:
        fail('dnfmedia is not an LGPL build')
    if 'https' not in run([str(media), '-hide_banner', '-protocols']).stdout:
        fail('dnfmedia cannot read https')
    if 'libmp3lame' not in run([str(media), '-hide_banner', '-encoders']).stdout:
        fail('dnfmedia has no MP3 encoder')
    script = WORK / 'check.js'
    script.write_text('print([1, 2, 3].map(x => x * 2).join(","))\n')
    out = run([str(js), str(script)])
    if out.returncode != 0 or out.stdout.strip() != '2,4,6':
        fail(f'dnfjs: {out.returncode} {out.stdout!r} {out.stderr!r}')
    print('dnfmedia and dnfjs run')
    oldest = tuple(int(p) for p in str(info.get('LSMinimumSystemVersion', '11.0')).split('.'))
    newer = []
    count = 0
    for path in app.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        for found in macho_minimums(path):
            count += 1
            if found > oldest:
                newer.append(f'{path.relative_to(app)} needs macOS {".".join(map(str, found))}')
    if newer:
        fail('built for a newer macOS than the app says it supports:\n  ' + '\n  '.join(newer))
    print(f'{count} programs and libraries, none needing more than macOS {".".join(map(str, oldest))}')


_FAT = (0xCAFEBABE, 0xCAFEBABF)
_THIN = {0xFEEDFACF: 32, 0xFEEDFACE: 28}  # header sizes, 64- and 32-bit


def macho_minimums(path: Path) -> list:
    """The oldest macOS each slice of a Mach-O file runs on (empty if it is
    not one): LC_BUILD_VERSION or LC_VERSION_MIN_MACOSX."""

    import struct

    with open(path, 'rb') as fh:
        head = fh.read(8)
        if len(head) < 8:
            return []
        offsets = []
        if struct.unpack('>I', head[:4])[0] in _FAT:
            count = struct.unpack('>I', head[4:8])[0]
            wide = struct.unpack('>I', head[:4])[0] == 0xCAFEBABF
            for i in range(min(count, 16)):
                fh.seek(8 + i * (32 if wide else 20))
                entry = fh.read(32 if wide else 20)
                offsets.append(struct.unpack('>Q', entry[8:16])[0] if wide
                               else struct.unpack('>I', entry[8:12])[0])
        else:
            offsets.append(0)
        found = []
        for base in offsets:
            fh.seek(base)
            header = fh.read(32)
            magic = struct.unpack('<I', header[:4])[0] if len(header) >= 32 else 0
            if magic not in _THIN:
                continue
            ncmds, sizeofcmds = struct.unpack('<II', header[16:24])
            fh.seek(base + _THIN[magic])
            commands = fh.read(sizeofcmds)
            at = 0
            for _ in range(ncmds):
                if at + 16 > len(commands):
                    break
                cmd, size = struct.unpack('<II', commands[at:at + 8])
                if cmd in (0x32, 0x24):  # LC_BUILD_VERSION, LC_VERSION_MIN_MACOSX
                    value = struct.unpack('<I', commands[at + (12 if cmd == 0x32 else 8):][:4])[0]
                    found.append((value >> 16, (value >> 8) & 0xFF))
                    break
                at += size
        return found


def check_disk_image(dmg: Path) -> None:
    step('the disk image')
    mount = WORK / 'dmg'
    mount.mkdir()
    done = run(['/usr/bin/hdiutil', 'attach', '-nobrowse', '-readonly', '-mountpoint', str(mount), str(dmg)])
    if done.returncode != 0:
        fail(f'hdiutil attach: {done.stderr}')
    try:
        names = sorted(p.name for p in mount.iterdir())
        print('holds', names)
        if 'Dannify.app' not in names or not (mount / 'Applications').is_symlink():
            fail('the disk image should hold Dannify.app and a link to Applications')
        check = run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(mount / 'Dannify.app')])
        if check.returncode != 0:
            fail(f'the app in the disk image does not verify: {check.stderr}')
    finally:
        run(['/usr/bin/hdiutil', 'detach', str(mount)])


def first_start(app: Path) -> None:
    step('starts, stays up, quits when asked')
    copy = Copy(app, 'first')
    copy.start()
    print(f'up (process {copy.proc.pid}); watching it for 20s')
    time.sleep(20)
    screenshot('first-start')
    if copy.proc.poll() is not None:
        fail(f'the app exited with {copy.proc.returncode} after starting')
    if not windows_of(copy.proc.pid):
        fail('the app has no window on screen')
    if not (copy.data / 'updates' / '.launched').is_file():
        fail('the app did not write its start marker')
    if copy.send({'cmd': 'ping'}) != {'ok': True}:
        fail('the instance socket does not answer')
    errors = [line for line in (copy.data / 'dannify.log').read_text(errors='replace').splitlines()
              if ' | ERROR ' in line or ' | CRITICAL ' in line or 'Traceback' in line]
    if errors:
        print('errors in the log (shown, not fatal):\n  ' + '\n  '.join(errors[:20]))
    copy.quit()
    print('quit cleanly')


def started_by_launchservices(app: Path) -> None:
    step('open -n --env keeps the data folder; started hidden, it shows when asked')
    copy = Copy(app, 'opened')
    before = copy.starts()
    # Hidden, as at login (the login item passes --minimized the same way).
    done = run(['/usr/bin/open', '-n', '--env', f'DANNIFY_DATA_DIR={copy.data}', str(app),
                '--args', '--minimized'])
    if done.returncode != 0:
        fail(f'open -n --env: {done.stderr}')
    copy.wait_started(before)
    if 'Window hidden until asked' not in (copy.data / 'dannify.log').read_text(errors='replace'):
        fail('the copy started with --minimized did not start hidden')
    time.sleep(3)
    screenshot('started-hidden')
    shown_early = 'Window shown again' in (copy.data / 'dannify.log').read_text(errors='replace')
    if windows_of(copy.pid()):
        fail('the copy started hidden has a window on screen'
             + (' (it showed itself)' if shown_early else ' (not shown by the shell)'))
    if copy.send({'cmd': 'show', 'file': ''}) != {'ok': True}:
        fail('the hidden copy did not take the show message')
    wait_until(lambda: windows_of(copy.pid()), 10, 'the window to show')
    time.sleep(2)
    screenshot('shown')
    copy.quit()
    print('started with its own data folder, showed itself, and quit')


def update_over(installed: Path, copy: Copy, archive: Path) -> None:
    """Have the running *copy* hand over to the updater for *archive*, and quit."""

    from dannify.shell.macos import updater

    os.environ['DANNIFY_DATA_DIR'] = str(copy.data)  # what the helper passes on
    if not updater.install(archive, installed, pid=copy.proc.pid, data_dir=copy.data, launch=True):
        fail('the updater refused the update')
    copy.quit()


def good_update(app: Path, archive: Path) -> Path:
    step('an update goes in and starts')
    place = WORK / 'Applications'
    place.mkdir()
    installed = place / 'Dannify.app'
    ditto(str(app), str(installed))
    copy = Copy(installed, 'updating')
    copy.start()
    # Long enough for the page to load and keep what it stores, so the
    # version after the update opens past the first-run welcome.
    time.sleep(10)
    old_pid = copy.proc.pid
    before = copy.starts()
    update_over(installed, copy, archive)
    log = copy.data / 'updates' / 'update.log'
    wait_until(lambda: log.is_file() and 'started' in log.read_text(), 90, 'the updater to start the new version')
    copy.wait_started(before)
    time.sleep(6)
    # Same data folder, so past the first-run welcome: the main window.
    screenshot('after-update')
    ports = [line.rsplit(':', 1)[-1].split()[0] for line in
             (copy.data / 'dannify.log').read_text(errors='replace').splitlines()
             if 'Uvicorn running on' in line]
    print('ports used, before and after the update:', ports)
    wait_until(lambda: not (place / 'Dannify.app.old').exists(), 30, 'the new version to remove the backup')
    leftovers = [p.name for p in place.iterdir() if p.name != 'Dannify.app']
    if leftovers:
        fail(f'the update left {leftovers} behind')
    if copy.pid() == old_pid:
        fail('the same process is still running')
    print(log.read_text().strip())
    copy.quit()
    return installed


def broken_update(installed: Path) -> None:
    step('a version that cannot start is taken back out')
    broken = WORK / 'broken' / 'Dannify.app'
    ditto(str(installed), str(broken))
    program = broken / 'Contents' / 'MacOS' / 'Dannify'
    program.unlink()
    # A real program (a script's signature would not survive the zip) that
    # fails at once, as a version that cannot start would.
    subprocess.run(['/usr/bin/clang', '-x', 'c', '-', '-o', str(program)],
                   input=b'int main(void) { return 3; }\n', check=True)
    plist = broken / 'Contents' / 'Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info['CFBundleShortVersionString'] = '99.0.0'
    plist.write_bytes(plistlib.dumps(info))
    subprocess.run(['/usr/bin/codesign', '--force', '--deep', '-s', '-', str(broken)], check=True)
    archive = WORK / 'macos-Dannify-99.0.0-test.zip'
    ditto('-c', '-k', '--keepParent', str(broken), str(archive))

    copy = Copy(installed, 'updating')
    copy.start()
    before = copy.starts()
    update_over(installed, copy, archive)
    log = copy.data / 'updates' / 'update.log'
    wait_until(lambda: log.is_file() and 'going back' in log.read_text(), 120, 'the updater to give up')
    copy.wait_started(before)  # the previous version, started again
    version = plistlib.loads((installed / 'Contents' / 'Info.plist').read_bytes())
    if version['CFBundleShortVersionString'] == '99.0.0':
        fail('the broken version is still in place')
    skip = (copy.data / 'updates' / '.skip-version').read_text().strip()
    if skip != '99.0.0':
        fail(f'the bad version was noted as {skip!r}')
    if (installed.parent / 'Dannify.app.old').exists():
        fail('the backup is still there after going back')
    print(log.read_text().strip())
    copy.quit()


def main() -> None:
    archive = Path(sys.argv[1]).resolve()
    step(f'unpacking {archive.name}')
    unpacked = WORK / 'unpacked'
    ditto('-x', '-k', str(archive), str(unpacked))
    app = unpacked / 'Dannify.app'
    if not app.is_dir():
        fail('the zip holds no Dannify.app')
    check_bundle(app)
    dmg = archive.with_suffix('.dmg')
    if dmg.is_file():
        check_disk_image(dmg)
    first_start(app)
    started_by_launchservices(app)
    installed = good_update(app, archive)
    broken_update(installed)
    step('all good')
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == '__main__':
    main()
