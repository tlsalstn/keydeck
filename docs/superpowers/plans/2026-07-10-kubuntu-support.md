# keydeck Kubuntu 지원 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** keydeck을 클라이언트·호스트 양쪽에서 Kubuntu(KDE Plasma)를 지원하도록 확장한다 — 서버 `key` 이름 프로토콜, 호스트 오디오 백엔드 폴백, evdev 기반 리눅스 클라이언트 신규.

**Architecture:** 서버는 "물리 키 이름 + 액션" 계약만 알고, 플랫폼별 키코드 변환은 각 클라이언트가 책임진다. 리눅스 클라이언트는 순수 로직(keymap·mode)과 evdev/WS I/O를 분리해 앞의 둘을 evdev 없이 단위 테스트한다. KDE 결합 코드(KWin·kglobalaccel)는 Fedora·Kubuntu 공통이라 무손상.

**Tech Stack:** Python 3 (`/usr/bin/python3`), FastAPI(서버), python3-evdev + python3-websockets(리눅스 클라이언트), libnotify(notify-send). 전부 Fedora/Ubuntu 공식 패키지.

**Spec:** `docs/superpowers/specs/2026-07-10-kubuntu-support-design.md`

## Global Constraints

- **공식 패키지만**: Fedora `dnf` / Kubuntu `apt`. pip/venv/npm 금지. 인터프리터는 `/usr/bin/python3` 절대 경로.
- **키 프로토콜 A**: 클라이언트는 물리 키 **이름**(`"F1"`,`"Grave"`,`"Digit1"` … = `server/keycodes.py`의 `KVK_TO_NAME` 값과 동일 이름 공간)을 보낼 수 있고, 서버 `handle_key`는 `key`(문자열)가 있으면 그대로, 없으면 `code`(kVK 정수)→이름. **Mac 클라이언트(code 전송) 무손상.**
- **리눅스 클라이언트 역할**: 키 캡처·차단·전송만. 매핑 해석·실행은 서버.
- **토글 키**: Ctrl+Alt+M. **grab 범위**: 모든 키보드 장치. **상태 표시**: `notify-send`만(트레이 없음).
- **페일세이프**: WS 끊김/종료/크래시 시 반드시 ungrab → 로컬 키보드 복구.
- 테스트: 리포 루트에서 `/usr/bin/python3 -m pytest tests/ -v`.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

```
client/
├── __init__.py            # 신규 (패키지화 — 테스트 임포트용)
└── linux/
    ├── __init__.py        # 신규
    ├── keymap.py          # 신규: evdev 코드 → keydeck 이름 (순수, 하드코딩 정수)
    ├── mode.py            # 신규: 토글/전송 상태 머신 (순수)
    └── keydeck_client.py  # 신규: evdev/WS/notify I/O 배선
server/
├── main.py                # 수정: handle_key가 key 이름 수용
└── actions.py             # 수정: exec_media 오디오 백엔드 폴백
systemd/
└── keydeck-client.service # 신규: 클라이언트 user 서비스
tests/
├── test_linux_keymap.py   # 신규
├── test_linux_mode.py     # 신규
├── test_ws.py             # 수정: key 이름 경로
└── test_actions.py        # 수정: 오디오 백엔드 선택
README.md                  # 수정: 배포판별 설치 + 리눅스 클라이언트 셋업
```

---

### Task 1: 서버 — handle_key가 key 이름 수용 (프로토콜 A)

**Files:**
- Modify: `server/main.py` (`handle_key`, 현재 시작 `try: code = int(msg.get("code", -1))`)
- Test: `tests/test_ws.py` (기존 `client`/`ran` 픽스처 재사용)

**Interfaces:**
- Consumes: 기존 `key_name`, `state`, `broadcast`, `handle_nav`, `run_action`, `switch_page`.
- Produces: 없음 (동작 확장만). 클라이언트는 `{"type":"key","key":"F1","event":"down","repeat":false,"shift":false}` 또는 기존 `{"type":"key","code":122,...}` 둘 다 사용 가능.

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_ws.py` 끝에

```python
def test_key_by_name_dispatches(ran):
    """key 이름 직접 전송 경로 (리눅스 클라이언트)."""
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "key": "F5", "event": "down", "repeat": False})
        c.send_json({"type": "ping"})
    assert ran == ["play-pause"]


def test_key_by_name_navigation(on_default_page):
    """이름 경로에서도 Tab 페이지 내비게이션 동작."""
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "key": "Tab", "event": "down", "repeat": False})
            assert dash.receive_json()["type"] == "key"
            assert dash.receive_json() == {"type": "page_changed", "page": "second"}


def test_code_path_still_works(ran):
    """기존 kVK code 경로 회귀 (Mac 클라이언트)."""
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
        c.send_json({"type": "ping"})
    assert ran == ["play-pause"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/usr/bin/python3 -m pytest tests/test_ws.py::test_key_by_name_dispatches -v`
Expected: FAIL — 현재 `handle_key`는 `key`를 무시하고 `code` 기본 -1 → name None → 미매핑, `ran`이 빈 리스트.

- [ ] **Step 3: 구현** — `server/main.py`의 `handle_key` 시작부 교체

기존:
```python
async def handle_key(msg: dict) -> None:
    try:
        code = int(msg.get("code", -1))
    except (TypeError, ValueError):
        return
    name = key_name(code)
```
교체:
```python
async def handle_key(msg: dict) -> None:
    name = msg.get("key")
    if not isinstance(name, str):
        try:
            code = int(msg.get("code", -1))
        except (TypeError, ValueError):
            return
        name = key_name(code)
```
(이후 `binding = state.config.pages[...]...` 이하는 그대로 둔다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `/usr/bin/python3 -m pytest tests/test_ws.py -v`
Expected: 전체 PASS (신규 3개 포함).

- [ ] **Step 5: Commit**

```bash
git add server/main.py tests/test_ws.py
git commit -m "feat: 서버가 key 이름 직접 수용 (프로토콜 A) — code 경로 무손상

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 호스트 — 오디오 백엔드 폴백 (wpctl/pactl)

**Files:**
- Modify: `server/actions.py` (`MEDIA_OPS` 정의부, 현재 dict 리터럴)
- Test: `tests/test_actions.py`

**Interfaces:**
- Consumes: 기존 `_run`, `ActionError`.
- Produces: `_media_ops() -> dict[str, list[str]]` — `shutil.which`로 백엔드 감지. 모듈 로드 시 `MEDIA_OPS = _media_ops()`. `exec_media`는 변경 없음(계속 `MEDIA_OPS` 사용).

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_actions.py` 끝에

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/usr/bin/python3 -m pytest tests/test_actions.py::test_media_ops_pulseaudio -v`
Expected: FAIL — `AttributeError: module 'server.actions' has no attribute '_media_ops'`.

- [ ] **Step 3: 구현** — `server/actions.py`

파일 상단 import에 `shutil` 추가 (기존 `import asyncio` 등 옆):
```python
import shutil
```
기존 `MEDIA_OPS = { ... }` 블록 전체를 아래로 교체:
```python
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
```
`exec_media` 함수는 그대로 둔다 (이미 `MEDIA_OPS.get(action["op"])` 사용).

- [ ] **Step 4: 테스트 통과 확인**

Run: `/usr/bin/python3 -m pytest tests/test_actions.py -v`
Expected: 전체 PASS. 기존 `test_media_ops`(이 Fedora 호스트에 wpctl 존재)도 계속 통과.

- [ ] **Step 5: Commit**

```bash
git add server/actions.py tests/test_actions.py
git commit -m "feat: 오디오 백엔드 폴백 — wpctl(PipeWire) 없으면 pactl(PulseAudio)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 리눅스 클라이언트 — keymap.py (evdev 코드 → 이름)

**Files:**
- Create: `client/__init__.py` (빈 파일), `client/linux/__init__.py` (빈 파일), `client/linux/keymap.py`
- Test: `tests/test_linux_keymap.py`

**Interfaces:**
- Produces: `EVDEV_TO_NAME: dict[int, str]`, `key_name(code: int) -> str | None`. 반환 이름은 `KVK_TO_NAME` 값과 동일 공간(`"F1"`,`"Grave"`,`"Digit1"`,`"A"`,`"Comma"`,`"Period"` …). 모디파이어는 side-collapsed 이름(`"Ctrl"`,`"Alt"`,`"Shift"`,`"Meta"`)으로 매핑되어 mode.py가 상태/토글용으로 소비.
- **의존성 없음** (evdev 미설치 상태에서도 임포트·테스트 가능 — 정수 코드 하드코딩).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_linux_keymap.py`

```python
from client.linux.keymap import key_name


def test_letter_and_digit():
    assert key_name(30) == "A"      # KEY_A
    assert key_name(50) == "M"      # KEY_M
    assert key_name(2) == "Digit1"  # KEY_1
    assert key_name(11) == "Digit0" # KEY_0


def test_function_keys():
    assert key_name(59) == "F1"
    assert key_name(88) == "F12"


def test_punctuation_and_specials():
    assert key_name(41) == "Grave"     # KEY_GRAVE
    assert key_name(51) == "Comma"     # KEY_COMMA
    assert key_name(52) == "Period"    # KEY_DOT
    assert key_name(28) == "Return"    # KEY_ENTER
    assert key_name(40) == "Quote"     # KEY_APOSTROPHE
    assert key_name(15) == "Tab"
    assert key_name(57) == "Space"
    assert key_name(1) == "Escape"


def test_modifiers_side_collapsed():
    assert key_name(29) == "Ctrl"   # KEY_LEFTCTRL
    assert key_name(97) == "Ctrl"   # KEY_RIGHTCTRL
    assert key_name(42) == "Shift"  # KEY_LEFTSHIFT
    assert key_name(54) == "Shift"  # KEY_RIGHTSHIFT
    assert key_name(56) == "Alt"    # KEY_LEFTALT
    assert key_name(100) == "Alt"   # KEY_RIGHTALT


def test_unknown_code_none():
    assert key_name(9999) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/usr/bin/python3 -m pytest tests/test_linux_keymap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'client.linux.keymap'`.

- [ ] **Step 3: 구현**

`client/__init__.py`, `client/linux/__init__.py` — 빈 파일 생성.

`client/linux/keymap.py`:
```python
"""리눅스 evdev 키코드 → keydeck 물리 키 이름. input-event-codes.h 기준, 하드코딩(안정 ABI).

반환 이름은 server/keycodes.py의 KVK_TO_NAME 값과 동일 이름 공간. 모디파이어는
좌우 구분 없이 Ctrl/Alt/Shift/Meta로 접어 mode.py가 상태/토글 감지에 쓴다."""

EVDEV_TO_NAME: dict[int, str] = {
    1: "Escape",
    2: "Digit1", 3: "Digit2", 4: "Digit3", 5: "Digit4", 6: "Digit5",
    7: "Digit6", 8: "Digit7", 9: "Digit8", 10: "Digit9", 11: "Digit0",
    12: "Minus", 13: "Equal", 14: "Backspace", 15: "Tab",
    16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y", 22: "U",
    23: "I", 24: "O", 25: "P", 26: "LeftBracket", 27: "RightBracket",
    28: "Return", 29: "Ctrl",
    30: "A", 31: "S", 32: "D", 33: "F", 34: "G", 35: "H", 36: "J",
    37: "K", 38: "L", 39: "Semicolon", 40: "Quote", 41: "Grave",
    42: "Shift", 43: "Backslash",
    44: "Z", 45: "X", 46: "C", 47: "V", 48: "B", 49: "N", 50: "M",
    51: "Comma", 52: "Period", 53: "Slash", 54: "Shift", 56: "Alt",
    57: "Space",
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6",
    65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    97: "Ctrl", 100: "Alt",
    102: "Home", 103: "Up", 104: "PageUp", 105: "Left", 106: "Right",
    107: "End", 108: "Down", 109: "PageDown", 111: "ForwardDelete",
    125: "Meta", 126: "Meta",
}


def key_name(code: int) -> str | None:
    return EVDEV_TO_NAME.get(code)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/usr/bin/python3 -m pytest tests/test_linux_keymap.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add client/__init__.py client/linux/__init__.py client/linux/keymap.py tests/test_linux_keymap.py
git commit -m "feat: 리눅스 클라이언트 keymap — evdev 코드→keydeck 이름

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 리눅스 클라이언트 — mode.py (토글/전송 상태 머신)

**Files:**
- Create: `client/linux/mode.py`
- Test: `tests/test_linux_mode.py`

**Interfaces:**
- Consumes: 없음 (순수 로직, 이름 문자열만 다룸).
- Produces: `MacroMode` 클래스.
  - `.macro_on: bool` (현재 매크로 모드; 클라이언트가 grab 여부 판단에 읽음)
  - `.process(name: str | None, event: str) -> dict` — `event` in `{"down","up","repeat"}`. 반환 `{"toggle": bool, "message": dict | None}`. `toggle=True`면 클라이언트가 `macro_on`에 맞춰 grab/ungrab. `message`가 있으면 그대로 WS로 전송(`{"type":"key","key","event"("down"/"up"),"repeat","shift"}`).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_linux_mode.py`

```python
from client.linux.mode import MacroMode


def toggle_on(m):
    m.process("Ctrl", "down")
    m.process("Alt", "down")
    return m.process("M", "down")


def test_starts_off_sends_nothing():
    m = MacroMode()
    assert m.macro_on is False
    d = m.process("F5", "down")
    assert d == {"toggle": False, "message": None}


def test_toggle_on_via_ctrl_alt_m():
    m = MacroMode()
    d = toggle_on(m)
    assert d["toggle"] is True
    assert m.macro_on is True


def test_toggle_key_up_and_repeat_swallowed():
    m = MacroMode()
    toggle_on(m)
    assert m.process("M", "repeat") == {"toggle": False, "message": None}
    assert m.process("M", "up") == {"toggle": False, "message": None}
    assert m.macro_on is True  # 홀드 중 repeat로 재토글 안 됨


def test_sends_mapped_key_when_on():
    m = MacroMode()
    toggle_on(m)
    m.process("M", "up")            # 토글 키 정리
    m.process("Ctrl", "up")
    m.process("Alt", "up")
    d = m.process("F5", "down")
    assert d["toggle"] is False
    assert d["message"] == {"type": "key", "key": "F5", "event": "down",
                            "repeat": False, "shift": False}


def test_repeat_event_maps_to_down_with_repeat():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    d = m.process("F6", "repeat")
    assert d["message"]["event"] == "down" and d["message"]["repeat"] is True


def test_shift_flag():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    m.process("Shift", "down")
    d = m.process("Tab", "down")
    assert d["message"]["shift"] is True


def test_up_event_sent_when_on():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    d = m.process("F5", "up")
    assert d["message"] == {"type": "key", "key": "F5", "event": "up",
                            "repeat": False, "shift": False}


def test_m_as_normal_key_without_combo():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    d = m.process("M", "down")  # Ctrl+Alt 없이 M → 일반 매크로 키
    assert d["message"]["key"] == "M"


def test_toggle_off_returns_to_silent():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    toggle_on(m)  # 다시 Ctrl+Alt+M → OFF
    assert m.macro_on is False
    m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    assert m.process("F5", "down") == {"toggle": False, "message": None}


def test_none_name_noop():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    assert m.process(None, "down") == {"toggle": False, "message": None}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/usr/bin/python3 -m pytest tests/test_linux_mode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'client.linux.mode'`.

- [ ] **Step 3: 구현** — `client/linux/mode.py`

```python
"""매크로 모드 상태 머신 (순수). evdev·WS I/O 없음 — 클라이언트가 결정을 실행한다.

토글 = Ctrl+Alt 가 눌린 상태에서 M down. 토글 키(M)의 repeat·up은 삼켜서
홀드 중 재토글·잔여 전송을 막는다. 모디파이어는 매크로 키로 전송하지 않는다."""

MODIFIERS = {"Ctrl", "Alt", "Shift", "Meta"}
TOGGLE_MODS = frozenset({"Ctrl", "Alt"})
TOGGLE_KEY = "M"
NOOP = {"toggle": False, "message": None}


class MacroMode:
    def __init__(self):
        self.mods: set[str] = set()
        self.macro_on = False
        self._toggling = False

    def process(self, name, event):
        if name is None:
            return dict(NOOP)
        if name in MODIFIERS:
            if event == "down":
                self.mods.add(name)
            elif event == "up":
                self.mods.discard(name)
            return dict(NOOP)
        if name == TOGGLE_KEY:
            if not self._toggling and event == "down" and TOGGLE_MODS <= self.mods:
                self.macro_on = not self.macro_on
                self._toggling = True
                return {"toggle": True, "message": None}
            if self._toggling:
                if event == "up":
                    self._toggling = False
                return dict(NOOP)  # 토글 키의 repeat·up 삼킴
        if not self.macro_on:
            return dict(NOOP)
        if event == "repeat":
            msg_event, repeat = "down", True
        elif event == "down":
            msg_event, repeat = "down", False
        else:
            msg_event, repeat = "up", False
        return {"toggle": False, "message": {
            "type": "key", "key": name, "event": msg_event,
            "repeat": repeat, "shift": "Shift" in self.mods}}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/usr/bin/python3 -m pytest tests/test_linux_mode.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add client/linux/mode.py tests/test_linux_mode.py
git commit -m "feat: 리눅스 클라이언트 mode — 토글/전송 상태 머신 (순수, 테스트 가능)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 리눅스 클라이언트 I/O 배선 + systemd + README

**Files:**
- Create: `client/linux/keydeck_client.py`, `systemd/keydeck-client.service`
- Modify: `README.md`

**Interfaces:**
- Consumes: `client.linux.keymap.key_name`, `client.linux.mode.MacroMode`, `evdev`, `websockets`.
- Produces: `find_keyboards() -> list`, `Client` 클래스, `main()`. `python3 -m client.linux.keydeck_client`로 실행. 환경변수 `KEYDECK_HOST`/`KEYDECK_PORT`(기본 8787)/`KEYDECK_TOKEN`.
- **검증**: 이 파일은 evdev/실장치 I/O라 단위 테스트 대신 (a) import 스모크, (b) Kubuntu 실기기 체크리스트로 확인.

- [ ] **Step 1: python3-evdev 설치 (import 스모크·실행용, 공식 패키지)**

Fedora 개발 호스트:
```bash
sudo dnf install -y python3-evdev
```
Expected: 설치 완료. `/usr/bin/python3 -c "import evdev; print(evdev.__version__)"` → 버전 출력.

- [ ] **Step 2: 클라이언트 구현** — `client/linux/keydeck_client.py`

```python
"""keydeck 리눅스 클라이언트: evdev로 키 캡처+grab, WS로 호스트 전송. 매핑 해석은 서버.

필요: python3-evdev, python3-websockets, libnotify(notify-send). 사용자는 input 그룹.
환경변수: KEYDECK_HOST, KEYDECK_PORT(기본 8787), KEYDECK_TOKEN."""
import asyncio
import json
import os
import signal

import websockets
from evdev import InputDevice, ecodes, list_devices

from .keymap import key_name
from .mode import MacroMode

HOST = os.environ.get("KEYDECK_HOST", "CHANGE-ME-host-ip")
PORT = int(os.environ.get("KEYDECK_PORT", "8787"))
TOKEN = os.environ.get("KEYDECK_TOKEN", "CHANGE-ME-token")

EVENT_NAMES = {0: "up", 1: "down", 2: "repeat"}


def find_keyboards() -> list:
    """A~Z 키를 가진 evdev 장치 = 키보드로 판정, 전부 반환."""
    kbds = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            continue
        keys = dev.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
            kbds.append(dev)
    return kbds


def notify(summary: str, body: str = "") -> None:
    try:
        os.spawnlp(os.P_NOWAIT, "notify-send", "notify-send", "-a", "keydeck", summary, body)
    except OSError:
        pass


class Client:
    def __init__(self, devices):
        self.devices = devices
        self.mode = MacroMode()
        self.ws = None
        self.grabbed = False

    def _set_grab(self, on: bool) -> None:
        if on == self.grabbed:
            return
        for dev in self.devices:
            try:
                dev.grab() if on else dev.ungrab()
            except OSError:
                pass
        self.grabbed = on

    def _fail_open(self) -> None:
        """연결 끊김/종료 시 즉시 로컬 키보드 복구."""
        self.mode.macro_on = False
        self._set_grab(False)

    async def _handle(self, ev) -> None:
        if ev.type != ecodes.EV_KEY:
            return
        event = EVENT_NAMES.get(ev.value)
        if event is None:
            return
        decision = self.mode.process(key_name(ev.code), event)
        if decision["toggle"]:
            self._set_grab(self.mode.macro_on)
            notify("keydeck", "매크로 모드 ON" if self.mode.macro_on else "매크로 모드 OFF")
        msg = decision["message"]
        if msg is not None and self.ws is not None:
            try:
                await self.ws.send(json.dumps(msg))
            except Exception:
                pass

    async def _read(self, dev) -> None:
        try:
            async for ev in dev.async_read_loop():
                await self._handle(ev)
        except OSError:
            pass  # 장치 분리 등

    async def run(self) -> None:
        readers = [asyncio.create_task(self._read(d)) for d in self.devices]
        try:
            while True:
                try:
                    uri = f"ws://{HOST}:{PORT}/ws/client?token={TOKEN}"
                    async with websockets.connect(uri) as ws:
                        self.ws = ws
                        await ws.send(json.dumps(
                            {"type": "hello", "client": "linux", "version": 1}))
                        notify("keydeck", "서버 연결됨")
                        async for _ in ws:  # 서버 push는 무시, 연결 유지 (라이브러리가 ping 처리)
                            pass
                except Exception:
                    pass
                self.ws = None
                self._fail_open()
                notify("keydeck", "서버 연결 끊김 — 재연결 중")
                await asyncio.sleep(2)
        finally:
            for r in readers:
                r.cancel()
            self._set_grab(False)


def main() -> None:
    devices = find_keyboards()
    if not devices:
        raise SystemExit("키보드 장치를 찾지 못했습니다 (input 그룹 소속 확인)")
    client = Client(devices)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [t.cancel() for t in asyncio.all_tasks(loop)])
    try:
        loop.run_until_complete(client.run())
    except asyncio.CancelledError:
        pass
    finally:
        client._set_grab(False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: import 스모크 확인**

Run: `/usr/bin/python3 -c "import client.linux.keydeck_client as c; print('import ok', bool(c.find_keyboards))"`
Expected: `import ok True` (구문·의존성 오류 없음). 리포 루트에서 실행.

- [ ] **Step 4: systemd user 유닛 작성** — `systemd/keydeck-client.service`

```ini
[Unit]
Description=keydeck Linux client (evdev macro pad)
After=graphical-session.target

[Service]
Environment=KEYDECK_HOST=CHANGE-ME-host-ip
Environment=KEYDECK_PORT=8787
Environment=KEYDECK_TOKEN=CHANGE-ME-token
WorkingDirectory=%h/Documents/macpad
ExecStart=/usr/bin/python3 -m client.linux.keydeck_client
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

- [ ] **Step 5: README에 배포판별 설치 + 리눅스 클라이언트 섹션 추가**

`README.md`의 기존 "## 호스트 셋업 (Fedora)" 제목을 "## 호스트 셋업"으로 바꾸고, 바로 아래에 배포판별 설치 표를 추가:

```markdown
### 의존성 설치 (공식 패키지만)

| 역할 | Fedora (dnf) | Kubuntu (apt) |
|---|---|---|
| 서버 | `python3-fastapi python3-uvicorn python3-websockets python3-pyyaml playerctl wireplumber ydotool` | `python3-fastapi python3-uvicorn python3-websockets python3-yaml playerctl wireplumber ydotool` |
| 리눅스 클라이언트 | `python3-evdev python3-websockets libnotify` | `python3-evdev python3-websockets libnotify` |

- Kubuntu는 `python3-yaml`(Fedora는 `python3-pyyaml`)로 패키지명이 다릅니다.
- 오디오: PipeWire면 `wpctl`, PulseAudio면 `pactl`을 자동 감지합니다(볼륨 액션).
- 창 포커스·`kde` 액션은 KWin/kglobalaccel 기반이라 Kubuntu(KDE)에서 동일하게 동작합니다. GNOME은 미지원.
```

그리고 "## Mac 셋업" 섹션 뒤에 리눅스 클라이언트 섹션 추가:

```markdown
## 리눅스 클라이언트 셋업 (Kubuntu 등)

MacBook 대신 여분의 리눅스 노트북을 매크로 패드로 쓸 때:

1. `sudo dnf install python3-evdev python3-websockets libnotify` (Kubuntu: `sudo apt install ...`)
2. 사용자를 `input` 그룹에 추가(최초 1회): `sudo usermod -aG input $USER` 후 재로그인
3. 리포를 `~/Documents/macpad`에 클론
4. systemd user 서비스 등록:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/keydeck-client.service ~/.config/systemd/user/
   # 유닛의 KEYDECK_HOST/KEYDECK_TOKEN을 실제 값으로 편집
   systemctl --user daemon-reload && systemctl --user enable --now keydeck-client
   ```
5. **Ctrl+Alt+M** 으로 매크로 모드 ON/OFF. ON이면 이 노트북의 키보드가 전부 매크로 패드가 되고(로컬 세션에는 키가 전달되지 않음), OFF면 일반 키보드로 복귀합니다.

동작 확인: 대시보드(`http://<host-ip>:8787`)에서 "연결됨" 배지 + 키 누름 하이라이트.
```

- [ ] **Step 6: 전체 테스트 + 커밋**

Run: `/usr/bin/python3 -m pytest tests/ -v`
Expected: 전체 PASS (기존 + Task 1~4 신규).

```bash
git add client/linux/keydeck_client.py systemd/keydeck-client.service README.md
git commit -m "feat: 리눅스 클라이언트 I/O 배선 + systemd 유닛 + 배포판별 README

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Kubuntu 실기기 통합 체크리스트** (사용자와 함께, 문서화 산출물)

클라이언트(Kubuntu):
1. `input` 그룹·의존성 설치 후 서비스 시작 → "서버 연결됨" 알림
2. Ctrl+Alt+M → "매크로 모드 ON" 알림, 대시보드 "연결됨"
3. 매크로 모드 중 매핑된 키 → 호스트에서 액션 실행 + 대시보드 타일 발광
4. 매크로 모드 중 일반 키(예: 편집기 타이핑) → **로컬 세션에 입력 안 됨**(grab 확인)
5. Ctrl+Alt+M → OFF, 로컬 키보드 정상 복귀
6. 서버 중지 → "연결 끊김" 알림 + 즉시 키보드 복귀(ungrab), 재시작 → 자동 재연결
7. 서비스 kill → 커널이 grab 해제, 키보드 복귀 확인

호스트(Kubuntu로 운영 시):
8. 볼륨 액션(pactl 경로) 동작
9. launch/url 창 포커스(KWin) 동작, `kde` 액션 동작

---

## Self-Review 결과

- **스펙 커버리지**: §3 프로토콜 A(Task 1), §4 리눅스 클라이언트 keymap/mode/I·O(Task 3·4·5), §5 오디오 폴백(Task 2), §6 배포·systemd·README(Task 5), §7 에러 처리(Task 5 클라이언트 fail-open/signal), §8 테스트 전략(각 Task TDD + Task 5 체크리스트). 갭 없음.
- **타입/이름 일관성**: keymap 반환 이름(F1/Grave/Digit1/Comma/Period/Ctrl/Alt/Shift)이 mode.py의 MODIFIERS·TOGGLE_KEY 및 서버 `KVK_TO_NAME` 값 공간과 일치. `MacroMode.process(name,event)` 반환 `{"toggle","message"}` 형태가 Task 4 정의·Task 5 소비에서 동일. WS 메시지 필드(`type/key/event/repeat/shift`)가 mode.py 생성·서버 `handle_key` 수신에서 일치. 서버 `handle_key`의 `key` 우선 로직이 Task 1 구현·테스트와 일치.
- **범위 밖 유지**: GNOME·트레이·핫플러그·클라이언트 매핑편집 미포함 확인.
- evdev 미설치로도 keymap/mode 단위 테스트가 도는지 확인(정수 하드코딩·순수 로직 — Task 3·4는 evdev 불필요, Task 5만 evdev 필요).
