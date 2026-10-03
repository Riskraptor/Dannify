"""Where songs are worked on before they are sealed.

A download, a repair, a tag refresh: each has a song as a plain audio file
for a few seconds before it goes into the vault. That used to happen in the
system's temporary folder, which is the first place anyone looks for one. It
happens in the app's own data folder now (set at startup), in folders that
are removed when the work is done, and swept if a crash left any behind.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

PREFIXES = ('dnf-dl-', 'dnf-repair-', 'dnf-update-')

_root: Optional[Path] = None


def set_root(folder: Path) -> None:
    global _root
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        _root = Path(folder)
    except OSError:
        _root = None


def make(prefix: str = PREFIXES[0]) -> Path:
    """A fresh, empty folder to work in."""

    if _root is not None:
        try:
            return Path(tempfile.mkdtemp(prefix=prefix, dir=_root))
        except OSError:
            pass
    return Path(tempfile.mkdtemp(prefix=prefix))


def sweep(max_age: float = 6 * 3600) -> int:
    """Remove work folders a crash or a power cut left behind.

    Only old ones: a second copy of the app may be using a fresh one right
    now. The system's temporary folder too, where versions before 4.4 worked.
    """

    removed = 0
    cutoff = time.time() - max_age
    roots = [Path(tempfile.gettempdir())]
    if _root is not None:
        roots.append(_root)
    for root in roots:
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.name.startswith(PREFIXES):
                continue
            try:
                if not entry.is_dir() or entry.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed
