"""Installing a downloaded update on Linux: the signed .deb, through apt.

The file was checked against the release signature when it was downloaded
(updates.download) and is only ever taken from our own updates folder
(core.vetted_update). Installing a package needs root, so the system asks
for the password itself (pkexec, the same prompt Software uses); Dannify
never sees or handles it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger

# pkexec's own exit codes for "the user said no" and "not allowed".
_REFUSED = (126, 127)


def install_deb(path: Path) -> bool:
    """Install *path* with apt. True once the new version is in place."""

    pkexec, apt = shutil.which('pkexec'), shutil.which('apt-get')
    if not (pkexec and apt):
        logger.info('cannot install the update: pkexec or apt-get is missing')
        return False
    # apt-get takes a file when the path is absolute; it then installs any
    # new dependency from the system's own sources, which dpkg -i would not.
    cmd = [pkexec, apt, 'install', '-y', '--allow-downgrades', '-o', 'Dpkg::Use-Pty=0', str(path)]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=30 * 60)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        logger.opt(exception=True).info('the update could not be installed')
        return False
    if done.returncode in _REFUSED:
        logger.info('the update was not authorised')
        return False
    if done.returncode != 0:
        logger.warning('apt could not install the update ({}): {}', done.returncode,
                       (done.stderr or done.stdout or '')[-600:])
        return False
    logger.info('Update installed from {}', path.name)
    return True
