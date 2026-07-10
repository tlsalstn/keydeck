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

    def reset(self) -> None:
        """연결 끊김 등 fail-open 시 호출 — 유령 모디파이어/토글 상태 제거."""
        self.mods.clear()
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
