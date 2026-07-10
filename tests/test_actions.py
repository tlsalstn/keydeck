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

    async def fake_capture(*argv):
        recorded.append((list(argv), "capture"))
        return 0, b""

    async def fake_not_running(pattern):
        recorded.append((["pgrep", "-f", pattern], "check"))
        return False

    monkeypatch.setattr(actions, "_run", fake_run)
    monkeypatch.setattr(actions, "_run_stdin", fake_run_stdin)
    monkeypatch.setattr(actions, "_run_capture", fake_capture)
    monkeypatch.setattr(actions, "_process_running", fake_not_running)
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
    gio = [c[0] for c in calls if c[0][0] == "gio"]
    assert gio == [["gio", "launch", str(tmp_path / "org.kde.konsole.desktop")]]


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


def test_text_backup_paste_restore(calls, monkeypatch):
    async def fake_capture(*argv):
        calls.append((list(argv), "capture"))
        return 0, b"OLD-CLIP"

    async def no_sleep(_):
        pass

    monkeypatch.setattr(actions, "_run_capture", fake_capture)
    monkeypatch.setattr(actions.asyncio, "sleep", no_sleep)
    asyncio.run(actions.exec_text({"type": "text", "text": "안녕하세요."}))
    assert calls[0] == (["wl-paste", "--no-newline"], "capture")
    assert calls[1] == (["wl-copy"], "안녕하세요.".encode())
    assert calls[2][0][:2] == ["ydotool", "key"]          # Ctrl+V 주입
    assert calls[3] == (["wl-copy"], b"OLD-CLIP")          # 복원


def test_text_no_restore_when_backup_failed(calls, monkeypatch):
    async def fake_capture(*argv):
        return 1, b""

    async def no_sleep(_):
        pass

    monkeypatch.setattr(actions, "_run_capture", fake_capture)
    monkeypatch.setattr(actions.asyncio, "sleep", no_sleep)
    asyncio.run(actions.exec_text({"type": "text", "text": "x"}))
    wl_copy_calls = [c for c in calls if c[0][0] == "wl-copy"]
    assert len(wl_copy_calls) == 1  # 백업 실패 시 복원 없음


def test_shell_malformed_cmd(calls):
    with pytest.raises(ActionError):
        asyncio.run(actions.exec_shell({"type": "shell", "cmd": "echo 'unbalanced"}))


def test_launch_focuses_running_app(calls, monkeypatch):
    """실행 중인 앱은 새로 열지 않고 창을 활성화한다."""
    activated = []

    async def running(pattern):
        return True

    async def fake_activate(cls):
        activated.append(cls)

    monkeypatch.setattr(actions, "_process_running", running)
    monkeypatch.setattr(actions, "_activate_window", fake_activate)
    asyncio.run(actions.exec_launch({
        "type": "launch", "app": "org.kde.konsole",
        "class": "konsole", "process": "^/usr/bin/konsole"}))
    assert activated == ["konsole"]
    assert not [c for c in calls if c[0][0] == "gio"]


def test_launch_class_process_default_to_app(monkeypatch):
    seen = {}

    async def running(pattern):
        seen["process"] = pattern
        return True

    async def fake_activate(cls):
        seen["class"] = cls

    monkeypatch.setattr(actions, "_process_running", running)
    monkeypatch.setattr(actions, "_activate_window", fake_activate)
    asyncio.run(actions.exec_launch({"type": "launch", "app": "firefox"}))
    assert seen == {"process": "firefox", "class": "firefox"}


def test_activate_window_gdbus_sequence(calls, monkeypatch):
    from pathlib import Path

    captured = {}

    async def fake_capture(*argv):
        captured["load_argv"] = list(argv)
        captured["script"] = Path(argv[-2]).read_text()
        return 0, b"(7,)"

    monkeypatch.setattr(actions, "_run_capture", fake_capture)
    asyncio.run(actions._activate_window("Konsole"))
    assert "loadScript" in " ".join(captured["load_argv"])
    assert '"konsole"' in captured["script"]          # 소문자 + JS 문자열 리터럴
    assert "stackingOrder" in captured["script"]
    gdbus = [" ".join(c[0]) for c in calls if c[0][0] == "gdbus"]
    assert any("/Scripting/Script7" in g and g.endswith("Script.run") for g in gdbus)
    assert any(g.endswith("Script.stop") for g in gdbus)


def test_activate_window_load_failure(monkeypatch):
    async def fake_capture(*argv):
        return 0, b"(-1,)"

    monkeypatch.setattr(actions, "_run_capture", fake_capture)
    with pytest.raises(ActionError):
        asyncio.run(actions._activate_window("konsole"))


def test_url_with_browser_and_focus(calls, monkeypatch):
    """browser 지정 시 해당 브라우저로 열고, class 지정 시 창을 포커스한다."""
    detached, activated = [], []

    async def fake_detached(*argv):
        detached.append(list(argv))

    async def fake_activate(cls):
        activated.append(cls)

    async def no_sleep(_):
        pass

    monkeypatch.setattr(actions, "_run_detached", fake_detached)
    monkeypatch.setattr(actions, "_activate_window", fake_activate)
    monkeypatch.setattr(actions.asyncio, "sleep", no_sleep)
    asyncio.run(actions.exec_url({
        "type": "url", "url": "https://gitlab.com/x",
        "browser": "firefox", "class": "firefox"}))
    assert detached == [["firefox", "https://gitlab.com/x"]]
    assert activated == ["firefox"]
    assert not [c for c in calls if c[0][0] == "xdg-open"]


def test_url_default_unchanged(calls):
    asyncio.run(actions.exec_url({"type": "url", "url": "https://example.com"}))
    assert calls[0][0] == ["xdg-open", "https://example.com"]


def test_media_ops_pipewire(monkeypatch):
    monkeypatch.setattr(actions.shutil, "which",
                        lambda c: "/usr/bin/wpctl" if c == "wpctl" else None)
    ops = actions._media_ops()
    assert ops["volume-up"][0] == "wpctl"
    assert ops["play-pause"] == ["playerctl", "play-pause"]


def test_media_ops_pulseaudio(monkeypatch):
    monkeypatch.setattr(actions.shutil, "which",
                        lambda c: None if c == "wpctl" else "/usr/bin/pactl")
    ops = actions._media_ops()
    assert ops["volume-up"] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"]
    assert ops["volume-down"] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"]
    assert ops["mute"] == ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]


def test_media_ops_no_backend_keeps_playerctl(monkeypatch):
    monkeypatch.setattr(actions.shutil, "which", lambda c: None)
    ops = actions._media_ops()
    assert ops["play-pause"] == ["playerctl", "play-pause"]
    assert "volume-up" not in ops  # 백엔드 없으면 볼륨 op 미제공
