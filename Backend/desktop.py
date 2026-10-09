"""Dannify desktop launcher: the native window around the interface.

What running this file starts, and what a shipped build's boot.py calls.
Each platform has its own shell under dannify/shell (windows, linux, macos)
answering the same bridge calls; this only picks the right one.
"""

from __future__ import annotations

import os
import sys


def _proof_of_work_worker() -> None:
    """Chase one lyrics-publish nonce and exit, when spawned for that.

    A frozen build has no separate Python to run a worker script with, so
    lyrics_publish respawns the app itself with these two variables set. No
    server, no window, no log file: just the search loop.
    """

    job = os.environ.get('DANNIFY_POW_WORKER')
    out = os.environ.get('DANNIFY_POW_OUT')
    if not (job and out):
        return
    import hashlib

    try:
        prefix, target_hex, start, stride = job.split('|')
        target = bytes.fromhex(target_hex)
        # lrclib hashes ``prefix + nonce`` with NO separator. The
        # colon-separated form is only used for the X-Publish-Token header.
        # The Rust reference is the source of truth:
        # https://github.com/tranxuanthang/lrcget/blob/main/src-tauri/src/lrclib/challenge_solver.rs
        pre = prefix.encode()
        sha = hashlib.sha256
        n, step = int(start), int(stride)
        while True:
            if sha(pre + str(n).encode()).digest() < target:
                # A windowed build has no stdout: the answer goes to the file
                # the caller named.
                with open(out, 'w', encoding='utf-8') as f:
                    f.write(str(n))
                break
            n += step
    except Exception:
        pass
    sys.exit(0)


def entry() -> None:
    _proof_of_work_worker()
    if os.name == 'nt':
        from dannify.shell.windows.app import run
    elif sys.platform == 'darwin':
        from dannify.shell.macos.app import run
    else:
        from dannify.shell.linux.app import run
    run()


if __name__ == '__main__':
    entry()
