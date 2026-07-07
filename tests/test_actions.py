import asyncio

import pytest

from server import actions
from server.actions import ActionError, ydotool_key_args


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    async def fake_run(*argv, env=None):
        recorded.append((list(argv), env))

    async def fake_run_stdin(*argv, data):
        recorded.append((list(argv), data))

    monkeypatch.setattr(actions, "_run", fake_run)
    monkeypatch.setattr(actions, "_run_stdin", fake_run_stdin)
    return recorded


def test_ydotool_key_args_press_reverse_release():
    assert ydotool_key_args(["ctrl", "shift", "v"]) == [
        "ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0",
    ]


def test_ydotool_key_args_unknown_key():
    with pytest.raises(ActionError):
        ydotool_key_args(["ctrl", "hyper"])


def test_shell_exec_no_shell(calls):
    asyncio.run(actions.exec_shell({"type": "shell", "cmd": "notify-send hello world"}))
    assert calls[0][0] == ["notify-send", "hello", "world"]


def test_shell_expands_home(calls):
    asyncio.run(actions.exec_shell({"type": "shell", "cmd": "~/scripts/build.sh"}))
    assert calls[0][0][0].startswith("/") and calls[0][0][0].endswith("/scripts/build.sh")


def test_launch_resolves_desktop_file(calls, tmp_path, monkeypatch):
    (tmp_path / "org.kde.konsole.desktop").write_text("[Desktop Entry]")
    monkeypatch.setattr(actions, "APP_DIRS", [tmp_path])
    asyncio.run(actions.exec_launch({"type": "launch", "app": "org.kde.konsole"}))
    assert calls[0][0] == ["gio", "launch", str(tmp_path / "org.kde.konsole.desktop")]


def test_launch_missing_desktop_file(monkeypatch, tmp_path):
    monkeypatch.setattr(actions, "APP_DIRS", [tmp_path])
    with pytest.raises(ActionError):
        asyncio.run(actions.exec_launch({"type": "launch", "app": "nope"}))


def test_url(calls):
    asyncio.run(actions.exec_url({"type": "url", "url": "https://example.com"}))
    assert calls[0][0] == ["xdg-open", "https://example.com"]


def test_hotkey_sets_ydotool_socket(calls):
    asyncio.run(actions.exec_hotkey({"type": "hotkey", "keys": ["ctrl", "c"]}))
    argv, env = calls[0]
    assert argv[:2] == ["ydotool", "key"]
    assert "YDOTOOL_SOCKET" in env


def test_media_ops(calls):
    asyncio.run(actions.exec_media({"type": "media", "op": "play-pause"}))
    asyncio.run(actions.exec_media({"type": "media", "op": "volume-up"}))
    assert calls[0][0] == ["playerctl", "play-pause"]
    assert calls[1][0][0] == "wpctl"


def test_media_unknown_op():
    with pytest.raises(ActionError):
        asyncio.run(actions.exec_media({"type": "media", "op": "warp"}))


def test_kde_gdbus(calls):
    asyncio.run(actions.exec_kde({"type": "kde", "component": "kwin", "shortcut": "Overview"}))
    argv = calls[0][0]
    assert argv[0] == "gdbus" and "/component/kwin" in argv and argv[-1] == "Overview"


def test_registry_complete():
    assert set(actions.EXECUTORS) == {"shell", "launch", "url", "hotkey", "text", "media", "kde"}
    assert set(actions.REQUIRED_FIELDS) == set(actions.EXECUTORS)
