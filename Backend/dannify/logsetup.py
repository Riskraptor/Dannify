"""Logging: loguru for everything, with the standard library and uvicorn
routed into it, to the console and the log file."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from loguru import logger

from . import sealed
from .osenv import IS_ANDROID

# The log file is written from a queue of its own, so a slow disk never holds
# up a request. Not on Android: the queue is multiprocessing's, which needs
# the POSIX semaphores Android does not have, and the file sink failed to be
# added at all, so the app kept no log. One process there, and loguru's own
# lock keeps the file whole.
_QUEUED = not IS_ANDROID


class _InterceptHandler(logging.Handler):
    """Redirect all stdlib logging records into loguru."""

    @staticmethod
    def emit(record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


class _SealedFile:
    """The log file of a shipped copy: a sealed line for each record
    (sealed.py), with anything that signs in blanked first, turned over at
    5 MB with three kept, like the plain one."""

    def __init__(self, path: Path, limit: int = 5 * 1024 * 1024, keep: int = 3) -> None:
        self.path = Path(path)
        self.limit = limit
        self.keep = keep
        self._lock = threading.Lock()

    def __call__(self, message: str) -> None:
        from .report import scrub  # noqa: PLC0415  (not needed before the first line)

        line = sealed.line(scrub(str(message).rstrip('\n'))) + '\n'
        with self._lock:
            try:
                if self.path.exists() and self.path.stat().st_size + len(line) > self.limit:
                    self._turn_over()
                with open(self.path, 'a', encoding='utf-8') as f:
                    f.write(line)
            except OSError:
                pass

    def _turn_over(self) -> None:
        for n in range(self.keep, 0, -1):
            newer = self.path if n == 1 else self.path.with_name(f'{self.path.name}.{n - 1}')
            if newer.exists():
                os.replace(newer, self.path.with_name(f'{self.path.name}.{n}'))


def _setup_logging(level: str) -> None:
    logger.remove()

    def _patch(record: dict) -> None:
        """Attach a compact, friendly component name to every record."""

        name = record['name'] or ''
        if name.startswith('dannify.'):
            short = name.split('.', 1)[1]
        elif name.startswith('uvicorn'):
            short = 'http'
        elif name.startswith('websockets'):
            short = 'ws'
        elif name == '__main__':
            short = 'dannify'
        else:
            short = name.split('.')[-1]
        # Respect an explicit component already bound via logger.bind(...).
        if not record['extra'].get('component'):
            record['extra']['component'] = short[:12]

    logger.configure(patcher=_patch, extra={'component': ''})

    # Friendly level icons for at-a-glance scanning (set before adding sink).
    for lvl, icon in (
        ('TRACE', '·'),
        ('DEBUG', '•'),
        ('INFO', 'ℹ'),
        ('SUCCESS', '✓'),
        ('WARNING', '⚠'),
        ('ERROR', '✗'),
        ('CRITICAL', '‼'),
    ):
        try:
            logger.level(lvl, icon=icon)
        except Exception:
            pass

    # Console sink: only when a real console exists. Windowed desktop
    # builds (PyInstaller --noconsole) have ``sys.stderr = None``.
    if sys.stderr is not None:
        try:
            _colorize = bool(sys.stderr.isatty())
        except Exception:
            _colorize = False
        logger.add(
            sys.stderr,
            format=(
                '<dim>{time:HH:mm:ss}</dim> '
                '<level>{level.icon} {level: <7}</level> '
                '<magenta>{extra[component]: <12}</magenta> '
                '<level>{message}</level>'
            ),
            level=level.upper(),
            colorize=_colorize or None,
            backtrace=False,
            diagnose=False,
        )

    # File sink: used by the desktop build so users (and we) can debug
    # without a console. Rotates so it never grows unbounded. UTF-8 is
    # explicit because the icons in the log format (✓ ✗ ‼ ♪) crash a
    # cp1252 default sink on Windows.
    _log_file = os.getenv('DANNIFY_LOG_FILE')
    if _log_file and sealed.sealing():
        # A shipped copy's log is sealed: only the developer can read what
        # the app did (sealed.py).
        try:
            Path(_log_file).parent.mkdir(parents=True, exist_ok=True)
            logger.add(
                _SealedFile(Path(_log_file)),
                format=(
                    '{time:YYYY-MM-DD HH:mm:ss} '
                    '{level.icon} {level: <7} '
                    '{extra[component]: <12} {message}'
                ),
                level=level.upper(),
                colorize=False,
                backtrace=False,
                diagnose=False,
                enqueue=_QUEUED,
            )
        except Exception:
            pass
    elif _log_file:
        try:
            Path(_log_file).parent.mkdir(parents=True, exist_ok=True)
            logger.add(
                _log_file,
                format=(
                    '{time:YYYY-MM-DD HH:mm:ss} '
                    '{level.icon} {level: <7} '
                    '{extra[component]: <12} {message}'
                ),
                level=level.upper(),
                colorize=False,
                backtrace=False,
                diagnose=False,
                rotation='5 MB',
                retention=3,
                enqueue=_QUEUED,
                encoding='utf-8',
            )
        except Exception:
            pass

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    # Route uvicorn/fastapi logs through loguru; silence uvicorn's noisy
    # per-request access lines (we emit our own concise request logs).
    for _name in ('uvicorn', 'uvicorn.error', 'fastapi'):
        _log = logging.getLogger(_name)
        _log.handlers = [_InterceptHandler()]
        _log.propagate = False
    # Access logs: handled by our own concise middleware; silence the raw
    # uvicorn access logger to avoid duplicate, noisy per-asset lines.
    _access = logging.getLogger('uvicorn.access')
    _access.handlers = []
    _access.propagate = False
    _access.disabled = True
