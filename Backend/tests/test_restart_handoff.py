"""A restart on Windows waits for the old copy to exit, and stops if it never
does (issue #43): it used to carry on into claiming the single-instance
mutex either way."""

from __future__ import annotations

import ast
import os
import time

from tests._shell_source import windows_tree


class FakeKernel32:
    def __init__(self, taken: bool = False) -> None:
        self.calls: list[str] = []
        self.taken = taken

    def CreateMutexW(self, *args):  # noqa: N802
        self.calls.append('CreateMutexW')
        return 1

    def GetLastError(self):  # noqa: N802
        return 183 if self.taken else 0

    def CloseHandle(self, handle):  # noqa: N802
        self.calls.append('CloseHandle')


class FakeCtypes:
    @staticmethod
    def get_last_error():
        return 0


def _acquire(waited: bool, kernel32: FakeKernel32, focused: list) -> bool:
    tree = windows_tree()
    wanted = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == '_acquire_single_instance'
    ]
    printed: list = []
    namespace: dict = {
        'os': os,
        'time': time,
        'ctypes': FakeCtypes,
        '_WIN': True,
        'kernel32': kernel32,
        '_wait_for_parent_exit': lambda: waited,
        '_running_instance_window': lambda: 0,
        '_focus_existing_window': lambda: focused.append(True),
        'logger_print': lambda *a: printed.append(a),
    }
    exec(compile(ast.Module(body=wanted, type_ignores=[]), 'instance.py', 'exec'), namespace)
    return namespace['_acquire_single_instance']()


def test_an_old_copy_that_never_exits_stops_the_restart():
    kernel32, focused = FakeKernel32(), []
    assert _acquire(False, kernel32, focused) is False
    assert kernel32.calls == [], 'the mutex is not touched'
    assert focused == [], 'nothing is brought forward'


def test_an_old_copy_that_exits_lets_the_restart_go_on():
    kernel32, focused = FakeKernel32(), []
    assert _acquire(True, kernel32, focused) is True
    assert kernel32.calls == ['CreateMutexW']
