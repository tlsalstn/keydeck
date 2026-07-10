"""매크로 모드 상태 머신 (순수). evdev·WS I/O 없음 — 클라이언트가 결정을 실행한다.

토글 = Ctrl+Alt 가 눌린 상태에서 M down. 토글 키(M)의 repeat·up은 삼켜서
홀드 중 재토글·잔여 전송을 막는다. 모디파이어는 매크로 키로 전송하지 않는다.

grab 타이밍: 토글 ON 시점엔 Ctrl+Alt+M이 아직 눌려 있어 즉시 grab하면 릴리스가
삼켜져 로컬 세션에 유령 모디파이어가 남는다. 그래서 ON은 콤보가 완전히 풀린 뒤
(decision["grab"] is True) grab하고, OFF는 즉시(False) ungrab한다. pending 동안은
키가 로컬로도 전달되므로 매크로 메시지를 보내지 않는다."""

MODIFIERS = {"Ctrl", "Alt", "Shift", "Meta"}
TOGGLE_MODS = frozenset({"Ctrl", "Alt"})
TOGGLE_KEY = "M"


class MacroMode:
    def __init__(self):
        self.mods: set[str] = set()
        self.macro_on = False
        self._toggling = False
        self._pending_grab = False

    @staticmethod
    def _decision(toggle=False, grab=None, message=None):
        return {"toggle": toggle, "grab": grab, "message": message}

    def _engage_if_settled(self):
        """토글 콤보(Ctrl/Alt/M)가 전부 풀렸을 때만 grab 시작."""
        if self._pending_grab and not self.mods and not self._toggling:
            self._pending_grab = False
            return True
        return None

    def process(self, name, event):
        if name is None:
            return self._decision()
        if name in MODIFIERS:
            if event == "down":
                self.mods.add(name)
            elif event == "up":
                self.mods.discard(name)
            return self._decision(grab=self._engage_if_settled())
        if name == TOGGLE_KEY:
            if not self._toggling and event == "down" and TOGGLE_MODS <= self.mods:
                self.macro_on = not self.macro_on
                self._toggling = True
                if self.macro_on:
                    self._pending_grab = True  # 콤보 해제 후 grab
                    return self._decision(toggle=True)
                self._pending_grab = False
                return self._decision(toggle=True, grab=False)  # OFF는 즉시 ungrab
            if self._toggling:
                if event == "up":
                    self._toggling = False
                    return self._decision(grab=self._engage_if_settled())
                return self._decision()  # 토글 키 repeat 삼킴
        if not self.macro_on or self._pending_grab:
            return self._decision()
        if event == "repeat":
            msg_event, repeat = "down", True
        elif event == "down":
            msg_event, repeat = "down", False
        else:
            msg_event, repeat = "up", False
        return self._decision(message={
            "type": "key", "key": name, "event": msg_event,
            "repeat": repeat, "shift": "Shift" in self.mods})

    def reset(self) -> None:
        """연결 끊김 등 fail-open 시 호출 — 유령 모디파이어/토글 상태 제거."""
        self.mods.clear()
        self.macro_on = False
        self._toggling = False
        self._pending_grab = False
