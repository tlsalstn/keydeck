"""액션 레지스트리. 실행 내용은 호스트 로컬 설정에서만 온다 — 네트워크 입력은 키 코드뿐."""
import asyncio
import itertools
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path

YDOTOOL_ENV = {"YDOTOOL_SOCKET": os.environ.get("YDOTOOL_SOCKET", "/tmp/.ydotool_socket")}
APP_DIRS = [Path("/usr/share/applications"), Path.home() / ".local/share/applications"]


class ActionError(Exception):
    """액션 실행 실패. 메시지는 대시보드에 그대로 표시된다."""


async def _run(*argv: str, env: dict | None = None) -> None:
    """argv를 exec로 실행 (셸 경유 없음). 비정상 종료 시 ActionError."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        env={**os.environ, **(env or {})},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode(errors="replace").strip()[:200]
        raise ActionError(f"{argv[0]} 종료코드 {proc.returncode}: {detail}")


async def _run_stdin(*argv: str, data: bytes) -> None:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate(input=data)


async def _run_capture(*argv: str) -> tuple[int, bytes]:
    """argv 실행 후 (returncode, stdout) 반환. 클립보드 백업 등 출력이 필요한 경우용."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out


# Linux evdev 키코드 (ydotool key 용)
EVDEV = {
    "esc": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8,
    "8": 9, "9": 10, "0": 11, "minus": 12, "equal": 13, "backspace": 14,
    "tab": 15, "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21,
    "u": 22, "i": 23, "o": 24, "p": 25, "enter": 28, "ctrl": 29,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36,
    "k": 37, "l": 38, "shift": 42, "z": 44, "x": 45, "c": 46, "v": 47,
    "b": 48, "n": 49, "m": 50, "alt": 56, "space": 57,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "home": 102, "up": 103, "pageup": 104, "left": 105, "right": 106,
    "end": 107, "down": 108, "pagedown": 109, "insert": 110, "delete": 111,
    "meta": 125, "super": 125,
}


def ydotool_key_args(keys: list[str]) -> list[str]:
    codes = []
    for k in keys:
        code = EVDEV.get(str(k).lower())
        if code is None:
            raise ActionError(f"알 수 없는 hotkey 키: {k}")
        codes.append(code)
    presses = [f"{c}:1" for c in codes]
    releases = [f"{c}:0" for c in reversed(codes)]
    return ["ydotool", "key", *presses, *releases]


async def exec_shell(action: dict) -> None:
    try:
        argv = [os.path.expanduser(tok) for tok in shlex.split(action["cmd"])]
    except ValueError as e:
        raise ActionError(f"명령 파싱 실패: {e}") from e
    if not argv:
        raise ActionError("빈 명령")
    await _run(*argv)


_kwin_seq = itertools.count(1)

# 최근 포커스된(스태킹 최상위) 일치 창을 활성화. Wayland에선 KWin 스크립팅이 유일한 공식 경로.
KWIN_ACTIVATE_JS = """\
const target = %TARGET%;
const s = workspace.stackingOrder;
for (let i = s.length - 1; i >= 0; i--) {
    const w = s[i];
    if (w.normalWindow && w.resourceClass.toLowerCase().includes(target)) {
        workspace.activeWindow = w;
        break;
    }
}
"""


async def _process_running(pattern: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "pgrep", "-f", pattern,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    return proc.returncode == 0


async def _activate_window(win_class: str) -> None:
    script = KWIN_ACTIVATE_JS.replace("%TARGET%", json.dumps(win_class.lower()))
    fd, path = tempfile.mkstemp(prefix="macpad-kwin-", suffix=".js")
    try:
        os.write(fd, script.encode())
        os.close(fd)
        plugin = f"macpad-activate-{next(_kwin_seq)}"
        rc, out = await _run_capture(
            "gdbus", "call", "--session", "--dest", "org.kde.KWin",
            "--object-path", "/Scripting",
            "--method", "org.kde.kwin.Scripting.loadScript", path, plugin)
        m = re.search(r"-?\d+", out.decode(errors="replace"))
        sid = int(m.group()) if m else -1
        if rc != 0 or sid < 0:
            raise ActionError("KWin 스크립트 로드 실패 — 창 활성화 불가")
        obj = f"/Scripting/Script{sid}"
        await _run("gdbus", "call", "--session", "--dest", "org.kde.KWin",
                   "--object-path", obj, "--method", "org.kde.kwin.Script.run")
        await _run("gdbus", "call", "--session", "--dest", "org.kde.KWin",
                   "--object-path", obj, "--method", "org.kde.kwin.Script.stop")
    finally:
        os.unlink(path)


async def exec_launch(action: dict) -> None:
    """실행 중이면 해당 앱 창을 포커스, 아니면 새로 실행."""
    app = action["app"]
    if await _process_running(action.get("process", app)):
        await _activate_window(action.get("class", app))
        return
    for base in APP_DIRS:
        desktop = base / f"{app}.desktop"
        if desktop.exists():
            await _run("gio", "launch", str(desktop))
            return
    raise ActionError(f".desktop 파일 없음: {app}")


_bg_tasks: set = set()


async def _run_detached(*argv: str) -> None:
    """종료를 기다리지 않는 실행 — 브라우저 최초 기동처럼 장기 상주하는 프로세스용."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    reaper = asyncio.ensure_future(proc.wait())
    _bg_tasks.add(reaper)
    reaper.add_done_callback(_bg_tasks.discard)


async def exec_url(action: dict) -> None:
    """URL 열기. browser 지정 시 해당 브라우저로, class 지정 시 그 창을 포커스."""
    browser = action.get("browser")
    if browser:
        await _run_detached(browser, action["url"])
    else:
        await _run("xdg-open", action["url"])
    win_class = action.get("class")
    if win_class:
        await asyncio.sleep(0.4)  # 브라우저가 탭을 넘겨받을 시간
        await _activate_window(win_class)


async def exec_hotkey(action: dict) -> None:
    await _run(*ydotool_key_args(action["keys"]), env=YDOTOOL_ENV)


async def exec_text(action: dict) -> None:
    """클립보드 백업 → 스니펫 복사 → Ctrl+V 주입 → 클립보드 복원. 한글 등 레이아웃 무관."""
    rc, out = await _run_capture("wl-paste", "--no-newline")
    backup = out if rc == 0 else None
    await _run_stdin("wl-copy", data=action["text"].encode())
    await _run(*ydotool_key_args(["ctrl", "v"]), env=YDOTOOL_ENV)
    await asyncio.sleep(0.3)
    if backup is not None:
        await _run_stdin("wl-copy", data=backup)


def _media_ops() -> dict:
    """오디오 백엔드 감지: PipeWire(wpctl) 우선, 없으면 PulseAudio(pactl).
    playerctl(MPRIS)은 백엔드 무관이라 항상 포함."""
    ops = {
        "play-pause": ["playerctl", "play-pause"],
        "next": ["playerctl", "next"],
        "previous": ["playerctl", "previous"],
    }
    if shutil.which("wpctl"):
        ops["volume-up"] = ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+"]
        ops["volume-down"] = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"]
        ops["mute"] = ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
    elif shutil.which("pactl"):
        ops["volume-up"] = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"]
        ops["volume-down"] = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"]
        ops["mute"] = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]
    return ops


MEDIA_OPS = _media_ops()


async def exec_media(action: dict) -> None:
    argv = MEDIA_OPS.get(action["op"])
    if argv is None:
        raise ActionError(f"알 수 없는 media op: {action['op']} (지원: {', '.join(MEDIA_OPS)})")
    await _run(*argv)


async def exec_kde(action: dict) -> None:
    await _run(
        "gdbus", "call", "--session",
        "--dest", "org.kde.kglobalaccel",
        "--object-path", f"/component/{action['component']}",
        "--method", "org.kde.kglobalaccel.Component.invokeShortcut",
        action["shortcut"],
    )


EXECUTORS = {
    "shell": exec_shell,
    "launch": exec_launch,
    "url": exec_url,
    "hotkey": exec_hotkey,
    "text": exec_text,
    "media": exec_media,
    "kde": exec_kde,
}

REQUIRED_FIELDS = {
    "shell": ["cmd"],
    "launch": ["app"],
    "url": ["url"],
    "hotkey": ["keys"],
    "text": ["text"],
    "media": ["op"],
    "kde": ["component", "shortcut"],
}
