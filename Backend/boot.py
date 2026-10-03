"""What Dannify.exe runs first, in a shipped build.

The program is three pieces, so an update only brings the one that changed:

* ``Dannify.pkg``: Python itself and the libraries the app is built on. They
  change rarely, so most updates do not touch it.
* ``runtime/ytdlp.pyz``: yt-dlp, which changes whenever YouTube does.
* ``runtime/app.pyz``: Dannify's own code, which changes every release.

All three are compiled bytecode: nothing in them is source anyone can read or
edit. This puts the last two where Python looks for modules and starts the
app, exactly as running desktop.py does in development.
"""

import os
import sys


def _runtime() -> str:
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


for _archive in ('ytdlp.pyz', 'app.pyz'):
    _path = os.path.join(_runtime(), _archive)
    if os.path.isfile(_path):
        sys.path.insert(0, _path)

import desktop  # noqa: E402

desktop.entry()
