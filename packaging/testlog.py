"""A test's own key for the sealed log of the shipped copy it starts.

A shipped copy writes its log sealed for the developer (Backend/dannify/
sealed.py), and no test ever holds the developer's key. A test gives the copy
a public key of its own in DANNIFY_LOG_KEY instead: the log on disk is still
sealed, and only this test run, which made the key, can open it.

In Python (packaging/lifecycle.py, packaging/macos/smoke_test.py):

    import testlog
    env['DANNIFY_LOG_KEY'] = testlog.public_hex()
    text = testlog.read(data / 'dannify.log')

From a shell (packaging/linux/smoke_test.sh):

    eval "$(python3 packaging/testlog.py keys)"
    python3 packaging/testlog.py open "$DATA/dannify.log"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'Backend'))

from dannify import sealed  # noqa: E402  (plain Python: none of the app's libraries)

PRIVATE_ENV = 'DANNIFY_TEST_LOG_PRIVATE'


def private() -> bytes:
    """This run's private key: made once, and kept in the environment so the
    processes it starts (and a shell that asked for it) share it."""

    given = os.environ.get(PRIVATE_ENV, '').strip()
    if len(given) == 64:
        return bytes.fromhex(given)
    key = os.urandom(32)
    os.environ[PRIVATE_ENV] = key.hex()
    return key


def public_hex() -> str:
    return sealed.public_of(private()).hex()


def read(path) -> str:
    """The log at *path*, every line opened; a line still being written is
    left for the next read."""

    try:
        raw = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    raw = raw[: raw.rfind('\n') + 1]
    return sealed.Opener(private()).read(raw) + '\n' if raw else ''


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'keys':
        key = os.urandom(32)
        print(f'export {PRIVATE_ENV}={key.hex()}')
        print(f'export DANNIFY_LOG_KEY={sealed.public_of(key).hex()}')
    elif len(sys.argv) == 3 and sys.argv[1] == 'open':
        sys.stdout.write(read(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(2)
