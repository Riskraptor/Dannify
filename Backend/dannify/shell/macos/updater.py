"""Installing a downloaded update on macOS: a whole new Dannify.app, swapped in.

The .zip was checked against the release signature when it was downloaded
(updates.download) and is only ever taken from our own updates folder
(core.vetted_update). It is unpacked beside the running app, on the same
disk, so putting it in place is two renames and never a half-copied app. Its
quarantine flag comes off (it is ours, and verified) and its code signature
must check out before anything is touched.

A running app cannot be replaced from inside, so the swap is done by a small
script started on its own. It waits for this copy to quit, renames
Dannify.app to Dannify.app.old, moves the new one into place and starts it.
If the new version has not said it is up within WAIT_FOR_START seconds (it
writes a marker in the data folder once its server answers), the old one is
put back and started instead, and the version is noted so it is not offered
again: what the Windows launcher does (installer/Core/LaunchCare.cs). The new
version deletes the backup once it is up.

Nothing here imports AppKit: it is files, paths and processes, and is
checked on every platform.
"""

from __future__ import annotations

import json
import os
import plistlib
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Sequence

from loguru import logger

BUNDLE_ID = 'io.github.danielmwendwa9451.dannify'
MARKER = '.launched'
SKIP = '.skip-version'  # the name layout.skipped_version reads
WORK_PREFIX = '.dannify-update-'
WAIT_FOR_START = 40
LSREGISTER = ('/System/Library/Frameworks/CoreServices.framework/Frameworks/'
              'LaunchServices.framework/Support/lsregister')


class UpdateError(Exception):
    pass


def refuse_reason(app: Optional[Path]) -> str:
    """Why this copy cannot put a new version in its own place ('' if it can)."""

    if app is None:
        return 'not running from Dannify.app'
    if '/AppTranslocation/' in app.as_posix():
        # Opened straight from a download: macOS runs a read-only copy from
        # a random place, and the real one cannot be found from here.
        return 'running translocated; move Dannify to Applications first'
    if not os.access(app.parent, os.W_OK | os.X_OK):
        return f'{app.parent} is not writable'
    if not os.access(app, os.W_OK):
        return f'{app} is not writable'
    return ''


def bundle_info(app: Path) -> dict:
    try:
        with open(app / 'Contents' / 'Info.plist', 'rb') as fh:
            data = plistlib.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}


def _executable(app: Path) -> str:
    """The program inside *app*, relative to it."""

    name = str(bundle_info(app).get('CFBundleExecutable') or 'Dannify')
    return f'Contents/MacOS/{Path(name).name}'


def _run(cmd: Sequence[str], check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(list(cmd), capture_output=True, text=True, timeout=300)  # noqa: S603
    if check and done.returncode != 0:
        raise UpdateError(f'{Path(cmd[0]).name} failed ({done.returncode}): '
                          f'{(done.stderr or done.stdout or "").strip()[-400:]}')
    return done


def unpack(archive: Path, app: Path) -> Path:
    """Unpack *archive* beside *app* and check it. Returns the new app."""

    work = Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=str(app.parent)))
    try:
        # ditto keeps what a .app needs that a plain unzip may not: its
        # symbolic links, permissions and extended attributes.
        _run(['/usr/bin/ditto', '-x', '-k', str(archive), str(work)])
        found = [p for p in work.iterdir() if p.suffix == '.app' and p.is_dir()]
        if len(found) != 1:
            raise UpdateError('the update does not hold exactly one app')
        new = found[0]
        if bundle_info(new).get('CFBundleIdentifier') != BUNDLE_ID:
            raise UpdateError('the update is not Dannify')
        if not (new / _executable(new)).is_file():
            raise UpdateError('the update has no program in it')
        # Ours and already verified: without this, the first start of the
        # new version would stop at Gatekeeper's warning about a download.
        _run(['/usr/bin/xattr', '-dr', 'com.apple.quarantine', str(new)], check=False)
        _run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(new)])
        return new
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def helper_script(*, pid: int, app: Path, new: Path, data_dir: Path, version: str,
                  launch: bool, wait: int = WAIT_FOR_START) -> str:
    """The script that swaps the apps once this copy has quit."""

    updates = Path(data_dir) / 'updates'
    values = {
        'PID': str(int(pid)),
        'APP': str(app),
        'NEW': str(new),
        'WORK': str(new.parent),
        'BACKUP': str(app.with_name(app.name + '.old')),
        'NEW_EXE': _executable(new),
        'OLD_EXE': _executable(app),
        'MARKER': str(updates / MARKER),
        'SKIP': str(updates / SKIP),
        'LOG': str(updates / 'update.log'),
        'VERSION': version or 'unknown',
        'LAUNCH': '1' if launch else '0',
        'WAIT': str(int(wait)),
        'LSREGISTER': LSREGISTER,
    }
    head = '\n'.join(f'{key}={shlex.quote(value)}' for key, value in values.items())
    return f"""#!/bin/sh
# Puts a new Dannify.app in place once the running one has quit.
# Written by Dannify's updater (dannify/shell/macos/updater.py).
{head}

log() {{ printf '%s %s\\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }}
# Start an app on its own (not as this script's child) and print its id.
start() {{ ( "$1" </dev/null >/dev/null 2>&1 & echo $! ); }}
register() {{ [ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$APP" >/dev/null 2>&1; return 0; }}

n=0
while kill -0 "$PID" 2>/dev/null; do
  n=$((n + 1))
  if [ "$n" -ge 600 ]; then
    log "Dannify did not quit; the update is left for later"
    rm -rf "$WORK"
    exit 1
  fi
  sleep 0.1
done

rm -rf "$BACKUP"
if ! mv "$APP" "$BACKUP"; then
  log "could not move the old version aside"
  rm -rf "$WORK"
  exit 1
fi
if ! mv "$NEW" "$APP"; then
  log "could not put version $VERSION in place"
  mv "$BACKUP" "$APP"
  rm -rf "$WORK"
  exit 1
fi
rm -rf "$WORK"
register
log "version $VERSION is in place"
[ "$LAUNCH" = 1 ] || exit 0

rm -f "$MARKER"
NEWPID=$(start "$APP/$NEW_EXE")
n=0
while [ "$n" -lt $((WAIT * 10)) ]; do
  if [ -f "$MARKER" ]; then
    log "version $VERSION started"
    exit 0
  fi
  kill -0 "$NEWPID" 2>/dev/null || break
  sleep 0.1
  n=$((n + 1))
done

log "version $VERSION did not start; going back to the previous one"
kill "$NEWPID" 2>/dev/null
sleep 1
kill -9 "$NEWPID" 2>/dev/null
rm -rf "$APP"
if mv "$BACKUP" "$APP"; then
  printf '%s\\n' "$VERSION" > "$SKIP"
  register
  start "$APP/$OLD_EXE" >/dev/null
else
  log "could not put the previous version back"
  exit 1
fi
"""


def child_environment() -> dict:
    """This copy's environment, for a new copy that must start as its own app.

    The frozen program's loader leaves notes for itself in the environment
    (_PYI_*); a new copy that inherited them would take itself for a child of
    this one.
    """

    env = {k: v for k, v in os.environ.items() if not k.startswith('_PYI_')}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env


def install(archive: Path, app: Optional[Path], *, pid: int, data_dir: Path,
            launch: bool) -> bool:
    """Get *archive* ready beside *app* and leave the swap to a helper that
    runs once process *pid* has quit. True when the helper is on its way."""

    reason = refuse_reason(app)
    if reason:
        logger.info('cannot install the update here: {}', reason)
        return False
    try:
        new = unpack(Path(archive), app)
    except (OSError, UpdateError, subprocess.SubprocessError) as exc:
        logger.warning('the update could not be prepared: {}', exc)
        return False
    version = str(bundle_info(new).get('CFBundleShortVersionString') or '')
    updates = Path(data_dir) / 'updates'
    try:
        updates.mkdir(parents=True, exist_ok=True)
        script = updates / 'swap-app.sh'
        script.write_text(helper_script(pid=pid, app=app, new=new, data_dir=data_dir,
                                        version=version, launch=launch), encoding='utf-8')
        subprocess.Popen(  # noqa: S603  (our own script, fixed interpreter)
            ['/bin/sh', str(script)], cwd='/', start_new_session=True, env=child_environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        logger.opt(exception=True).warning('the update could not be started')
        shutil.rmtree(new.parent, ignore_errors=True)
        return False
    logger.info('Version {} is ready; it goes in when this copy quits', version or '?')
    return True


def started(app: Optional[Path], data_dir: Path) -> None:
    """This copy is up: say so to an updater waiting for it, and drop the
    version it replaced (and anything an interrupted update left)."""

    updates = Path(data_dir) / 'updates'
    try:
        updates.mkdir(parents=True, exist_ok=True)
        (updates / MARKER).write_text(
            json.dumps({'pid': os.getpid(), 'at': time.time()}), encoding='utf-8')
    except OSError:
        logger.opt(exception=True).debug('could not write the start marker')
    if app is None:
        return
    backup = app.with_name(app.name + '.old')
    if backup.is_dir():
        shutil.rmtree(backup, ignore_errors=True)
        logger.info('Removed the previous version ({})', backup.name)
    try:
        for stale in app.parent.glob(WORK_PREFIX + '*'):
            if stale.is_dir() and time.time() - stale.stat().st_mtime > 3600:
                shutil.rmtree(stale, ignore_errors=True)
    except OSError:
        pass
