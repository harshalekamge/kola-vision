"""Tests for the executor's scrolling, with pyautogui replaced by a recorder (no screen needed).

    python tests/test_executor.py
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

calls = []
fake = types.ModuleType("pyautogui")
fake.FAILSAFE, fake.PAUSE, fake.easeInOutQuad = True, 0, None
fake.position = lambda: (0, 0)
fake.moveTo = lambda *a, **k: None
fake.scroll = lambda n: calls.append(n)
sys.modules["pyautogui"] = fake

import kola.executor as ex  # noqa: E402

ex.time.sleep = lambda s: None


def scroll_on(platform, clicks):
    calls.clear()
    real = ex.sys.platform
    ex.sys.platform = platform
    try:
        ex.Executor().scroll(100, 400, clicks)
    finally:
        ex.sys.platform = real
    return list(calls)


def test_windows_sends_real_wheel_notches():
    # one notch on Windows is 120 wheel units; scroll(5) must not become 5 units
    assert scroll_on("win32", -5) == [-120] * 5
    assert scroll_on("win32", 3) == [120] * 3


def test_mac_and_linux_pass_notches_through():
    assert scroll_on("linux", -5) == [-5]
    assert scroll_on("darwin", 4) == [4]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
