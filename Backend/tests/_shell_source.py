"""The Windows shell's source, for tests that take single definitions out of
it without importing it (importing it starts setting up a window)."""

from __future__ import annotations

import ast
from pathlib import Path

WINDOWS_SHELL = Path(__file__).resolve().parents[1] / 'dannify' / 'shell' / 'windows'


def windows_tree() -> ast.Module:
    """Every top-level statement of every module of the Windows shell."""

    body = []
    for path in sorted(WINDOWS_SHELL.glob('*.py')):
        body.extend(ast.parse(path.read_text(encoding='utf-8')).body)
    return ast.Module(body=body, type_ignores=[])
