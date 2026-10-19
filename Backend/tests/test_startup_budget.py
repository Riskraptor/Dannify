"""What starting the app costs: nothing loaded that a session may never use."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def loaded_after(statement: str) -> set[str]:
    code = f'import sys; {statement}; print("\\n".join(sorted(sys.modules)))'
    done = subprocess.run(
        [sys.executable, '-c', code], cwd=BACKEND, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return set(done.stdout.split())


def test_the_app_starts_without_yt_dlp():
    # yt-dlp is the slow way to a stream and the way a download's bytes are
    # fetched; it loads when one of those first happens (see lazy.py).
    modules = loaded_after('import dannify.api')
    assert 'yt_dlp' not in modules
    assert 'dannify.streaming' in modules  # the module itself is there


def test_yt_dlp_loads_when_it_is_first_needed():
    modules = loaded_after('from dannify import downloader; downloader.yt_dlp.YoutubeDL')
    assert 'yt_dlp' in modules
